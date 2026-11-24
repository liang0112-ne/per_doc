"""文档库接口测试（B5 API 层）。

用 ``TestClient`` 打真实 HTTP 请求，覆盖 7 个接口的契约与权限。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


@pytest.fixture()
def login(api_client: TestClient, member: Member) -> TestClient:
    """已登录的客户端。"""
    api_client.post(
        "/api/auth/login",
        json={"account": "admin", "password": "admin123"},
    )
    return api_client


def csrf_of(api_client: TestClient) -> str:
    """取 CSRF Token。"""
    return api_client.get("/api/auth/csrf").json()["csrf_token"]


def create_space(api_client: TestClient, **overrides: object) -> dict[str, object]:
    """通过接口创建一个文档库，返回响应体。"""
    payload: dict[str, object] = {
        "space_name": "接口文档",
        "identify": "api-docs",
        "description": "RESTful API 说明",
    }
    payload.update(overrides)
    token = csrf_of(api_client)
    response = api_client.post(
        "/api/spaces",
        json=payload,
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateSpace:
    """创建文档库。"""

    def test_create_success(self, login: TestClient) -> None:
        data = create_space(login)
        assert data["identify"] == "api-docs"
        assert data["space_name"] == "接口文档"
        assert data["doc_count"] == 2
        assert data["is_owner"] is True

    def test_create_requires_login(self, api_client: TestClient) -> None:
        token = csrf_of(api_client)
        response = api_client.post(
            "/api/spaces",
            json={"space_name": "接口文档", "identify": "api-docs"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 403

    def test_create_requires_csrf(self, api_client: TestClient, member: Member) -> None:
        api_client.post(
            "/api/auth/login",
            json={"account": "admin", "password": "admin123"},
        )
        response = api_client.post(
            "/api/spaces",
            json={"space_name": "接口文档", "identify": "api-docs"},
        )
        assert response.status_code == 403

    def test_create_duplicate_identify(self, login: TestClient) -> None:
        create_space(login)
        response = login.post(
            "/api/spaces",
            json={"space_name": "另一本", "identify": "api-docs"},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 409

    def test_create_private_without_password(self, login: TestClient) -> None:
        response = login.post(
            "/api/spaces",
            json={"space_name": "私有库", "identify": "private-one", "is_private": 1},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 400

    def test_create_private_with_password(self, login: TestClient) -> None:
        data = create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        assert data["is_private"] == 1
        assert "password" not in data

    def test_create_invalid_identify(self, login: TestClient) -> None:
        response = login.post(
            "/api/spaces",
            json={"space_name": "接口文档", "identify": "Invalid-ID"},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 422

    def test_create_generates_identify(self, login: TestClient) -> None:
        data = create_space(login, identify=None, space_name="另一本")
        assert data["identify"]


class TestListSpaces:
    """文档库列表。"""

    def test_list_empty(self, login: TestClient) -> None:
        response = login.get("/api/spaces")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_as_owner(self, login: TestClient) -> None:
        create_space(login)
        data = login.get("/api/spaces").json()
        assert data["total"] == 1
        assert data["items"][0]["identify"] == "api-docs"
        assert data["items"][0]["is_owner"] is True

    def test_list_as_guest_sees_public_only(self, login: TestClient) -> None:
        create_space(login)
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        data = guest.get("/api/spaces").json()
        assert data["total"] == 1
        assert data["items"][0]["identify"] == "api-docs"

    def test_list_filter_by_group(self, login: TestClient) -> None:
        create_space(login, group_name="默认分组")
        create_space(login, space_name="手册", identify="manual", group_name="产品")
        data = login.get("/api/spaces", params={"group_name": "产品"}).json()
        assert data["total"] == 1
        assert data["items"][0]["identify"] == "manual"

    def test_list_filter_by_keyword(self, login: TestClient) -> None:
        create_space(login)
        create_space(login, space_name="手册", identify="manual")
        data = login.get("/api/spaces", params={"keyword": "manual"}).json()
        assert data["total"] == 1

    def test_list_returns_groups(self, login: TestClient) -> None:
        create_space(login, group_name="默认分组")
        create_space(login, space_name="手册", identify="manual", group_name="产品")
        data = login.get("/api/spaces").json()
        assert set(data["groups"]) == {"默认分组", "产品"}


class TestGetSpace:
    """文档库详情。"""

    def test_get_success(self, login: TestClient) -> None:
        create_space(login)
        response = login.get("/api/spaces/api-docs")
        assert response.status_code == 200
        assert response.json()["space_name"] == "接口文档"

    def test_get_not_found(self, login: TestClient) -> None:
        response = login.get("/api/spaces/missing")
        assert response.status_code == 404

    def test_get_private_denied_for_guest(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        response = guest.get("/api/spaces/private-one")
        assert response.status_code == 403


class TestUpdateSpace:
    """更新文档库。"""

    def test_update_success(self, login: TestClient) -> None:
        create_space(login)
        response = login.put(
            "/api/spaces/api-docs",
            json={"space_name": "新名称"},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 200
        assert response.json()["space_name"] == "新名称"

    def test_update_requires_login(self, api_client: TestClient) -> None:
        response = api_client.put(
            "/api/spaces/api-docs",
            json={"space_name": "新名称"},
            headers={"X-CSRF-Token": csrf_of(api_client)},
        )
        assert response.status_code == 403

    def test_update_not_found(self, login: TestClient) -> None:
        response = login.put(
            "/api/spaces/missing",
            json={"space_name": "新名称"},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 404

    def test_update_to_private_requires_password(self, login: TestClient) -> None:
        create_space(login)
        response = login.put(
            "/api/spaces/api-docs",
            json={"is_private": 1},
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 400


class TestDeleteSpace:
    """删除文档库。"""

    def test_delete_success(self, login: TestClient) -> None:
        create_space(login)
        response = login.delete(
            "/api/spaces/api-docs",
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 200
        assert login.get("/api/spaces/api-docs").status_code == 404

    def test_delete_requires_login(self, api_client: TestClient) -> None:
        response = api_client.delete(
            "/api/spaces/api-docs",
            headers={"X-CSRF-Token": csrf_of(api_client)},
        )
        assert response.status_code == 403

    def test_delete_not_found(self, login: TestClient) -> None:
        response = login.delete(
            "/api/spaces/missing",
            headers={"X-CSRF-Token": csrf_of(login)},
        )
        assert response.status_code == 404


class TestAccessControl:
    """私有库的访问密码。"""

    def test_check_access_denied_for_guest(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        data = guest.get("/api/spaces/private-one/access").json()
        assert data["granted"] is False

    def test_submit_correct_password(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        response = guest.post(
            "/api/spaces/private-one/access",
            json={"password": "secret123"},
        )
        assert response.status_code == 200
        assert response.json()["granted"] is True
        # 授权后应能读取详情
        assert guest.get("/api/spaces/private-one").status_code == 200

    def test_submit_wrong_password(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        response = guest.post(
            "/api/spaces/private-one/access",
            json={"password": "wrong"},
        )
        assert response.status_code == 403

    def test_granted_private_appears_in_list(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        guest.post("/api/spaces/private-one/access", json={"password": "secret123"})
        data = guest.get("/api/spaces").json()
        assert data["total"] == 1
        assert data["items"][0]["identify"] == "private-one"
