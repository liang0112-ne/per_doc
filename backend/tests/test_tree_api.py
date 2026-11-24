"""文档树接口测试（B6 API 层）。

用 ``TestClient`` 打真实 HTTP 请求，覆盖 ``GET /api/spaces/{key}/tree``
的契约与权限。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.security import hash_password
from app.models.document import Document
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
    """通过接口创建一个文档库。"""
    payload: dict[str, object] = {
        "space_name": "接口文档",
        "identify": "api-docs",
        "description": "RESTful API 说明",
    }
    payload.update(overrides)
    response = api_client.post(
        "/api/spaces",
        json=payload,
        headers={"X-CSRF-Token": csrf_of(api_client)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_document(
    session: Session,
    space_id: int,
    name: str,
    parent_id: int = 0,
    order_sort: int = 0,
    member_id: int = 1,
) -> Document:
    """插入一个测试文档节点。"""
    document = Document(
        document_name=name,
        identify=f"{name}-{order_sort}",
        space_id=space_id,
        parent_id=parent_id,
        order_sort=order_sort,
        markdown="",
        content="",
        member_id=member_id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


class TestGetTree:
    """读取文档树。"""

    def test_empty_tree(self, login: TestClient) -> None:
        create_space(login)
        response = login.get("/api/spaces/api-docs/tree")
        assert response.status_code == 200
        data = response.json()
        # 建库时自动创建了根节点与空白文档，因此树不为空
        assert data["total"] == 2
        assert len(data["tree"]) == 1
        root = data["tree"][0]
        assert root["document_name"] == "root"
        assert root["is_dir"] is True
        assert [child["document_name"] for child in root["children"]] == ["空白文档"]

    def test_tree_structure(self, login: TestClient, session: Session) -> None:
        created = create_space(login)
        space_id = int(created["space_id"])
        root = add_document(session, space_id, "根", 0, 1)
        child = add_document(session, space_id, "子", root.document_id, 1)

        data = login.get("/api/spaces/api-docs/tree").json()
        names = [node["document_name"] for node in data["tree"]]
        assert "根" in names

        root_node = next(node for node in data["tree"] if node["document_name"] == "根")
        assert root_node["is_dir"] is True
        assert root_node["children"][0]["document_id"] == child.document_id
        assert root_node["children"][0]["is_dir"] is False

    def test_node_fields(self, login: TestClient, session: Session) -> None:
        created = create_space(login)
        space_id = int(created["space_id"])
        root = add_document(session, space_id, "根", 0, 1)

        data = login.get("/api/spaces/api-docs/tree").json()
        node = next(item for item in data["tree"] if item["document_id"] == root.document_id)
        assert node["identify"] == "根-1"
        assert node["parent_id"] == 0
        assert node["order_sort"] == 1
        assert node["is_open"] == 0
        assert "version" in node

    def test_space_not_found(self, login: TestClient) -> None:
        assert login.get("/api/spaces/missing/tree").status_code == 404

    def test_guest_can_read_public_tree(self, login: TestClient) -> None:
        create_space(login)
        guest = TestClient(login.app)
        response = guest.get("/api/spaces/api-docs/tree")
        assert response.status_code == 200

    def test_guest_denied_for_private_tree(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        response = guest.get("/api/spaces/private-one/tree")
        assert response.status_code == 403

    def test_guest_allowed_after_password(self, login: TestClient) -> None:
        create_space(
            login,
            space_name="私有库",
            identify="private-one",
            is_private=1,
            access_password="secret123",
        )
        guest = TestClient(login.app)
        guest.post("/api/spaces/private-one/access", json={"password": "secret123"})
        response = guest.get("/api/spaces/private-one/tree")
        assert response.status_code == 200
