"""B1 基础设施自测：应用入口、全局异常处理、依赖注入。"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.deps import issue_csrf_token, read_csrf_token, read_session, verify_csrf
from app.core.exceptions import ConflictError, NotFoundError, PermissionError


def test_health_endpoint_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_app_error_is_translated(client: TestClient) -> None:
    """业务异常由全局处理器转换为统一响应体。"""
    app = client.app

    @app.get("/_test/notfound")
    def _notfound() -> None:
        raise NotFoundError("文档不存在")

    resp = client.get("/_test/notfound")
    assert resp.status_code == 404
    assert resp.json() == {"code": 4004, "message": "文档不存在", "detail": None}


def test_conflict_error_status(client: TestClient) -> None:
    app = client.app

    @app.get("/_test/conflict")
    def _conflict() -> None:
        raise ConflictError("版本冲突")

    resp = client.get("/_test/conflict")
    assert resp.status_code == 409
    assert resp.json()["code"] == 4009


def test_validation_error_structure(client: TestClient) -> None:
    app = client.app

    @app.get("/_test/query")
    def _query(limit: int) -> dict[str, int]:
        return {"limit": limit}

    resp = client.get("/_test/query?limit=abc")
    assert resp.status_code == 422
    assert resp.json()["code"] == 4000


def test_unhandled_exception_not_leaking_traceback() -> None:
    """未捕获异常不得把内部细节返回给客户端。"""
    from app.main import app

    @app.get("/_test/boom")
    def _boom() -> None:
        raise RuntimeError("内部细节不应返回")

    with TestClient(app, raise_server_exceptions=False) as raw_client:
        resp = raw_client.get("/_test/boom")
    assert resp.status_code == 500
    assert "内部细节" not in resp.text


class TestDeps:
    """依赖注入行为。"""

    def test_read_session_without_cookie(self) -> None:
        class FakeRequest:
            cookies: dict[str, str] = {}

        assert read_session(FakeRequest()) == {}

    def test_read_session_with_valid_token(self) -> None:
        from app.core.security import sign_session

        class FakeRequest:
            cookies = {"per_doc_session": sign_session({"member_id": 3})}

        assert read_session(FakeRequest())["member_id"] == 3

    def test_read_csrf_token_from_header(self) -> None:
        class FakeRequest:
            headers = {"X-CSRF-Token": "abc"}

        assert read_csrf_token(FakeRequest()) == "abc"

    def test_verify_csrf_passes_on_match(self) -> None:
        class FakeRequest:
            headers = {"X-CSRF-Token": "abc"}

        verify_csrf(FakeRequest(), {"csrf_token": "abc"})

    def test_verify_csrf_rejects_mismatch(self) -> None:
        class FakeRequest:
            headers = {"X-CSRF-Token": "other"}

        try:
            verify_csrf(FakeRequest(), {"csrf_token": "abc"})
        except PermissionError as exc:
            assert exc.code == 4030
        else:  # pragma: no cover - 断言失败分支
            raise AssertionError("应当抛出 PermissionError")

    def test_issue_csrf_token_returns_nonempty(self) -> None:
        assert issue_csrf_token()


def test_depends_chain_works(client: TestClient) -> None:
    """依赖注入链路可正常装配（session → request）。"""
    app = client.app

    def fake_session() -> dict[str, object]:
        return {"member_id": 1}

    @app.get("/_test/chain")
    def _chain(payload: dict[str, object] = Depends(fake_session)) -> dict[str, object]:
        return payload

    resp = client.get("/_test/chain")
    assert resp.status_code == 200
    assert resp.json() == {"member_id": 1}


def test_app_is_fastapi_instance() -> None:
    assert isinstance(FastAPI(), FastAPI)
