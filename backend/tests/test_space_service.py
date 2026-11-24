"""文档库模块单元测试（B5 service 层）。

覆盖：
- 标识生成与校验
- 文档库创建（标识推导、冲突、私有库密码、根文档）
- 更新（字段更新、权限、私有状态切换）
- 删除（级联清理）
- 可见性判定（登录用户 / 游客 / 访问密码）
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, PermissionError, ValidationError
from app.core.security import hash_password
from app.models.document import Document
from app.models.member import Member
from app.models.space import Space
from app.schemas.space import SpaceCreate, SpaceUpdate
from app.services import space_service
from app.utils.identifier import (
    generate_identify,
    is_valid_document_identify,
    is_valid_space_identify,
    suggest_identify,
)


@pytest.fixture()
def owner(session: Session) -> Member:
    """文档库的创建者。"""
    member = Member(
        account="owner",
        real_name="拥有者",
        password=hash_password("owner123"),
        status=0,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@pytest.fixture()
def other(session: Session) -> Member:
    """另一个登录用户。"""
    member = Member(
        account="other",
        real_name="别人",
        password=hash_password("other123"),
        status=0,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def make_payload(**overrides: object) -> SpaceCreate:
    """构造创建参数。"""
    data: dict[str, object] = {
        "space_name": "接口文档",
        "identify": "api-docs",
        "description": "RESTful API 说明",
    }
    data.update(overrides)
    return SpaceCreate(**data)


class TestIdentifier:
    """标识生成与校验。"""

    @pytest.mark.parametrize(
        "value",
        ["api-docs", "manual", "a", "a_b", "a-b-c", "abc123"],
    )
    def test_valid_space_identify(self, value: str) -> None:
        assert is_valid_space_identify(value) is True

    @pytest.mark.parametrize(
        "value",
        ["", "Api-Docs", "1abc", "-abc", "a b", "a" * 51, "a.b"],
    )
    def test_invalid_space_identify(self, value: str) -> None:
        assert is_valid_space_identify(value) is False

    @pytest.mark.parametrize(
        "value",
        ["doc", "user-login", "guide.install", "a_b-c.d"],
    )
    def test_valid_document_identify(self, value: str) -> None:
        assert is_valid_document_identify(value) is True

    @pytest.mark.parametrize(
        "value",
        ["", "Doc", "1doc", "-doc", "a b"],
    )
    def test_invalid_document_identify(self, value: str) -> None:
        assert is_valid_document_identify(value) is False

    def test_generate_identify_unique(self) -> None:
        ids = {generate_identify("doc") for _ in range(100)}
        assert len(ids) == 100

    def test_generate_identify_prefix(self) -> None:
        assert generate_identify("doc").startswith("doc-")

    def test_suggest_identify_from_ascii_name(self) -> None:
        assert suggest_identify("API Docs") == "api-docs"

    def test_suggest_identify_from_chinese_name(self) -> None:
        """中文名无法转出 ASCII 前缀，回退到默认前缀 + 随机串。"""
        result = suggest_identify("接口文档")
        assert result.startswith("doc-")
        assert is_valid_space_identify(result) is True

    def test_suggest_identify_strips_leading_digit(self) -> None:
        assert suggest_identify("2024 report").startswith("doc-")

    def test_suggest_identify_chinese_name_unique(self) -> None:
        """中文名推导出的标识应唯一（带随机后缀）。"""
        ids = {suggest_identify("接口文档") for _ in range(20)}
        assert len(ids) == 20


class TestCreateSpace:
    """创建文档库。"""

    def test_create_success(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        assert space.space_id > 0
        assert space.identify == "api-docs"
        assert space.member_id == owner.member_id
        assert space.is_private == 0
        assert space.password is None

    def test_create_creates_root_document(self, session: Session, owner: Member) -> None:
        """建库时自动创建根节点与空白文档（移植自 mindoc Book.Insert）。"""
        space = space_service.create_space(session, make_payload(), owner)
        docs = list(
            session.scalars(
                select(Document)
                .where(Document.space_id == space.space_id)
                .order_by(Document.order_sort)
            ).all()
        )
        assert len(docs) == 2
        assert docs[0].identify == "root"
        assert docs[0].parent_id == 0
        assert docs[1].document_name == "空白文档"
        assert docs[1].parent_id == docs[0].document_id

    def test_create_with_duplicate_identify(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(), owner)
        with pytest.raises(ConflictError):
            space_service.create_space(session, make_payload(space_name="另一本"), owner)

    def test_create_without_identify_generates_one(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(identify=None, space_name="API Docs"), owner
        )
        assert space.identify == "api-docs"

    def test_create_generated_identify_avoids_conflict(
        self, session: Session, owner: Member
    ) -> None:
        space_service.create_space(session, make_payload(), owner)
        second = space_service.create_space(
            session, make_payload(identify=None, space_name="API Docs"), owner
        )
        assert second.identify != "api-docs"
        assert is_valid_space_identify(second.identify) is True

    def test_create_private_requires_password(self, session: Session, owner: Member) -> None:
        with pytest.raises(ValidationError) as exc:
            space_service.create_space(session, make_payload(is_private=1), owner)
        assert "访问密码" in str(exc.value)

    def test_create_private_with_password(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space.is_private == 1
        assert space.password is not None
        assert space.password.startswith("$argon2")

    def test_create_public_ignores_password(self, session: Session, owner: Member) -> None:
        """公开库设置访问密码没有意义，应被忽略。"""
        space = space_service.create_space(
            session, make_payload(is_private=0, access_password="secret123"), owner
        )
        assert space.password is None

    def test_create_invalid_identify_rejected_by_schema(self) -> None:
        with pytest.raises(ValueError):
            make_payload(identify="Invalid-ID")


class TestUpdateSpace:
    """更新文档库。"""

    def test_update_name(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        updated = space_service.update_space(
            session, space, SpaceUpdate(space_name="新名称"), owner
        )
        assert updated.space_name == "新名称"

    def test_update_by_non_owner_rejected(
        self, session: Session, owner: Member, other: Member
    ) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        with pytest.raises(PermissionError):
            space_service.update_space(session, space, SpaceUpdate(space_name="劫持"), other)

    def test_update_to_private_requires_password(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        with pytest.raises(ValidationError):
            space_service.update_space(session, space, SpaceUpdate(is_private=1), owner)

    def test_update_to_private_with_password(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        updated = space_service.update_space(
            session, space, SpaceUpdate(is_private=1, access_password="secret123"), owner
        )
        assert updated.is_private == 1
        assert updated.password is not None

    def test_update_to_public_clears_password(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        updated = space_service.update_space(session, space, SpaceUpdate(is_private=0), owner)
        assert updated.is_private == 0
        assert updated.password is None

    def test_update_unset_fields_unchanged(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        updated = space_service.update_space(
            session, space, SpaceUpdate(description="新描述"), owner
        )
        assert updated.description == "新描述"
        assert updated.space_name == "接口文档"


class TestDeleteSpace:
    """删除文档库。"""

    def test_delete_removes_space_and_documents(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        space_service.delete_space(session, space, owner)
        assert session.get(Space, space.space_id) is None
        assert session.scalar(select(Document).where(Document.space_id == space.space_id)) is None

    def test_delete_by_non_owner_rejected(
        self, session: Session, owner: Member, other: Member
    ) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        with pytest.raises(PermissionError):
            space_service.delete_space(session, space, other)


class TestListSpaces:
    """文档库列表与可见性。"""

    def test_logged_in_member_sees_all(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(), owner)
        space_service.create_space(
            session,
            make_payload(identify="private-one", is_private=1, access_password="secret123"),
            owner,
        )
        spaces = space_service.list_spaces(session, owner)
        assert len(spaces) == 2

    def test_guest_sees_only_public(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(), owner)
        space_service.create_space(
            session,
            make_payload(identify="private-one", is_private=1, access_password="secret123"),
            owner,
        )
        spaces = space_service.list_spaces(session, None)
        assert len(spaces) == 1
        assert spaces[0].identify == "api-docs"

    def test_guest_sees_granted_private(self, session: Session, owner: Member) -> None:
        private = space_service.create_space(
            session,
            make_payload(identify="private-one", is_private=1, access_password="secret123"),
            owner,
        )
        spaces = space_service.list_spaces(session, None, granted_space_ids=[private.space_id])
        assert len(spaces) == 1
        assert spaces[0].identify == "private-one"

    def test_filter_by_group(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(group_name="默认分组"), owner)
        space_service.create_space(
            session, make_payload(identify="manual", group_name="产品"), owner
        )
        spaces = space_service.list_spaces(session, owner, group_name="产品")
        assert len(spaces) == 1
        assert spaces[0].identify == "manual"

    def test_filter_by_keyword(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(), owner)
        space_service.create_space(session, make_payload(identify="manual"), owner)
        spaces = space_service.list_spaces(session, owner, keyword="manual")
        assert len(spaces) == 1
        assert spaces[0].identify == "manual"

    def test_count_documents(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        # 建库自动创建了 2 篇文档（根节点 + 空白文档）
        assert space_service.count_documents(session, space.space_id) == 2

    def test_list_groups(self, session: Session, owner: Member) -> None:
        space_service.create_space(session, make_payload(group_name="默认分组"), owner)
        space_service.create_space(
            session, make_payload(identify="manual", group_name="产品"), owner
        )
        groups = space_service.list_space_groups(session, owner)
        assert set(groups) == {"默认分组", "产品"}


class TestAccessControl:
    """访问权限判定。"""

    def test_member_can_read_private(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space_service.can_read(space, owner, []) is True

    def test_guest_cannot_read_private(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space_service.can_read(space, None, []) is False

    def test_guest_with_grant_can_read_private(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space_service.can_read(space, None, [space.space_id]) is True

    def test_guest_can_read_public(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        assert space_service.can_read(space, None, []) is True

    def test_verify_access_password_correct(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space_service.verify_access_password(space, "secret123") is True

    def test_verify_access_password_wrong(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        assert space_service.verify_access_password(space, "wrong") is False

    def test_verify_access_password_on_public_space(self, session: Session, owner: Member) -> None:
        """公开库无需访问密码。"""
        space = space_service.create_space(session, make_payload(), owner)
        assert space_service.verify_access_password(space, "anything") is False

    def test_require_writable_rejects_guest(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        with pytest.raises(PermissionError):
            space_service.require_writable(space, None)

    def test_require_readable_raises_for_private_guest(
        self, session: Session, owner: Member
    ) -> None:
        space = space_service.create_space(
            session, make_payload(is_private=1, access_password="secret123"), owner
        )
        with pytest.raises(PermissionError):
            space_service.require_readable(space, None, [])


class TestLookup:
    """按标识 / 主键查询。"""

    def test_require_space_not_found(self, session: Session) -> None:
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            space_service.require_space(session, "missing")

    def test_get_space_by_identify(self, session: Session, owner: Member) -> None:
        space = space_service.create_space(session, make_payload(), owner)
        found = space_service.get_space_by_identify(session, "api-docs")
        assert found is not None
        assert found.space_id == space.space_id
