"""认证接口测试（B4 API 层）。

用 ``TestClient`` + ``dependency_overrides`` 打真实 HTTP 请求，
覆盖登录 / 登出 / 当前用户 / 注册 / 改密 / CSRF 的接口契约。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.security import hash_password
from app.models.member import Member


@pytest.fixture()
def api_client(session: Session) -> Generator[TestClient, None, None]:
    """把 ``get_db`` 覆盖到测试 Session 上。"""
    from app.main import app

    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def member(session: Session) -> Member:
    """一个已启用的测试用户。"""
    user = Member(
        account="admin",
        real_name="管理员",
        password=hash_password("admin123"),
        status=0,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class TestCsrf:
    """CSRF Token 下发。"""

    def test_get_csrf_returns_token(self, api_client: TestClient) -> None:
        response = api_client.get("/api/auth/csrf")
        assert response.status_code == 200
        data = response.json()
        assert data["csrf_token"]
        assert data["header_name"] == "X-CSRF-Token"

    def test_csrf_token_is_stable_in_session(self, api_client: TestClient) -> None:
        first = api_client.get("/api/auth/csrf").json()["csrf_token"]
        second = api_client.get("/api/auth/csrf").json()["csrf_token"]
        assert first == second


class TestLogin:
    """登录。"""

    def test_login_success(self, api_client: TestClient, member: Member) -> None:
        response = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["account"] == "admin"
        assert "password" not in data["user"]
        assert data["csrf_token"]

    def test_login_sets_cookie(self, api_client: TestClient, member: Member) -> None:
        response = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        assert "per_doc_session" in response.cookies

    def test_login_wrong_password(self, api_client: TestClient, member: Member) -> None:
        response = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "wrong"},
        )
        assert response.status_code == 401
        assert response.json()["message"] == "账号或密码错误"

    def test_login_invalid_account_format(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/auth/login",
            json={"account": "a", "password": "admin123"},
        )
        assert response.status_code == 422

    def test_login_unknown_account(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/auth/login",
            json={"account": "nobody", "password": "admin123"},
        )
        assert response.status_code == 401


class TestMe:
    """当前用户信息。"""

    def test_me_requires_login(self, api_client: TestClient) -> None:
        response = api_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_user(self, api_client: TestClient, member: Member) -> None:
        api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        response = api_client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["account"] == "admin"

    def test_me_rejects_disabled_account(self, api_client: TestClient, member: Member) -> None:
        api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        member.status = 1
        # 依赖从同一个 Session 读取，禁用后应返回 401
        response = api_client.get("/api/auth/me")
        assert response.status_code == 401


class TestLogout:
    """登出。"""

    def test_logout_clears_cookie(self, api_client: TestClient, member: Member) -> None:
        login = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        csrf_token = login.json()["csrf_token"]
        response = api_client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200
        assert api_client.get("/api/auth/me").status_code == 401

    def test_logout_without_session_is_allowed(self, api_client: TestClient) -> None:
        response = api_client.post("/api/auth/logout")
        assert response.status_code == 200

    def test_logout_with_session_requires_csrf(
        self, api_client: TestClient, member: Member
    ) -> None:
        """会话有效但缺少 CSRF 头时拒绝登出，避免被跨站请求强制登出。"""
        api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        response = api_client.post("/api/auth/logout")
        assert response.status_code == 403


class TestRegister:
    """注册。"""

    def test_register_success(self, api_client: TestClient) -> None:
        csrf_token = api_client.get("/api/auth/csrf").json()["csrf_token"]
        response = api_client.post(
            "/api/auth/register",
            json={
                "account": "newbie",
                "password": "newbie123",
                "password_confirm": "newbie123",
                "email": "newbie@example.com",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 201
        assert response.json()["account"] == "newbie"

    def test_register_requires_csrf(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/auth/register",
            json={
                "account": "newbie",
                "password": "newbie123",
                "password_confirm": "newbie123",
            },
        )
        assert response.status_code == 403

    def test_register_duplicated_account(self, api_client: TestClient, member: Member) -> None:
        csrf_token = api_client.get("/api/auth/csrf").json()["csrf_token"]
        response = api_client.post(
            "/api/auth/register",
            json={
                "account": "admin",
                "password": "newbie123",
                "password_confirm": "newbie123",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 409

    def test_register_password_mismatch(self, api_client: TestClient) -> None:
        csrf_token = api_client.get("/api/auth/csrf").json()["csrf_token"]
        response = api_client.post(
            "/api/auth/register",
            json={
                "account": "newbie",
                "password": "newbie123",
                "password_confirm": "other12345",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 400


class TestChangePassword:
    """修改密码。"""

    def test_change_password_success(self, api_client: TestClient, member: Member) -> None:
        login = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        csrf_token = login.json()["csrf_token"]
        response = api_client.put(
            "/api/auth/password",
            json={
                "old_password": "admin123",
                "new_password": "newpass123",
                "new_password_confirm": "newpass123",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200

        api_client.post("/api/auth/logout")
        relogin = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "newpass123"},
        )
        assert relogin.status_code == 200

    def test_change_password_requires_login(self, api_client: TestClient) -> None:
        response = api_client.put(
            "/api/auth/password",
            json={
                "old_password": "admin123",
                "new_password": "newpass123",
                "new_password_confirm": "newpass123",
            },
        )
        assert response.status_code == 401

    def test_change_password_wrong_old(self, api_client: TestClient, member: Member) -> None:
        login = api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        csrf_token = login.json()["csrf_token"]
        response = api_client.put(
            "/api/auth/password",
            json={
                "old_password": "wrong",
                "new_password": "newpass123",
                "new_password_confirm": "newpass123",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 401


class TestConfigIsolation:
    """配置读取回归。"""

    def test_allow_register_read_from_settings(self) -> None:
        assert isinstance(get_settings().allow_register, bool)
