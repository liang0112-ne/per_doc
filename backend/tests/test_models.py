"""B2 数据层自测：模型结构、约束、级联、Alembic 迁移。"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base, table_name
from app.models import (
    Attachment,
    Document,
    DocumentHistory,
    Log,
    Member,
    Option,
    Space,
)

EXPECTED_TABLES = {
    "md_members",
    "md_spaces",
    "md_documents",
    "md_document_history",
    "md_attachments",
    "md_options",
    "md_logs",
}


@pytest.fixture()
def member(session: Session) -> Member:
    user = Member(account="tester", real_name="测试", password="hash", status=0)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def space(session: Session, member: Member) -> Space:
    item = Space(
        space_name="接口文档",
        identify="api-docs",
        member_id=member.member_id,
        create_time=datetime.now(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


class TestTableNames:
    """表名与前缀。"""

    def test_all_seven_tables_registered(self) -> None:
        actual = set(Base.metadata.tables)
        assert actual == EXPECTED_TABLES

    def test_table_name_uses_configured_prefix(self) -> None:
        assert table_name("members") == "md_members"

    def test_no_hardcoded_prefix_in_model_files(self) -> None:
        """模型层不得出现硬编码的 md_ 字面量。"""
        import inspect as py_inspect

        import app.models as models_pkg

        for obj in vars(models_pkg).values():
            if not isinstance(obj, type) or not issubclass(obj, Base):
                continue
            module = py_inspect.getfile(obj)
            if module.endswith("__init__.py"):
                continue
            with open(module, encoding="utf-8") as handle:
                content = handle.read()
            assert '"md_' not in content and "'md_" not in content, module


class TestMember:
    """用户表行为。"""

    def test_insert_and_read(self, session: Session, member: Member) -> None:
        found = session.scalar(select(Member).where(Member.account == "tester"))
        assert found is not None
        assert found.member_id == member.member_id
        assert found.is_active is True

    def test_account_is_unique(self, session: Session, member: Member) -> None:
        session.add(Member(account="tester", real_name="重复", password="x"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_status_disabled_is_inactive(self, session: Session) -> None:
        user = Member(account="disabled", real_name="禁用", password="x", status=1)
        session.add(user)
        session.commit()
        assert user.is_active is False

    def test_defaults_applied(self, session: Session) -> None:
        user = Member(account="defaults", real_name="默认", password="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.status == 0
        assert user.create_time is not None


class TestSpace:
    """文档库表行为。"""

    def test_insert_and_defaults(self, session: Session, space: Space) -> None:
        session.refresh(space)
        assert space.editor == "markdown"
        assert space.theme == "default"
        assert space.auto_save == 1
        assert space.group_name == "默认分组"
        assert space.is_public is True

    def test_private_space_not_public(self, session: Session, member: Member) -> None:
        item = Space(
            space_name="私有库",
            identify="private",
            member_id=member.member_id,
            is_private=1,
            create_time=datetime.now(),
        )
        session.add(item)
        session.commit()
        assert item.is_public is False

    def test_identify_is_unique(self, session: Session, space: Space) -> None:
        session.add(
            Space(
                space_name="重复",
                identify="api-docs",
                member_id=space.member_id,
                create_time=datetime.now(),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_documents_relationship(self, session: Session, space: Space) -> None:
        doc = Document(
            document_name="根目录",
            identify="root",
            space_id=space.space_id,
            markdown="# hi",
            member_id=space.member_id,
        )
        session.add(doc)
        session.commit()
        session.refresh(space)
        assert len(space.documents) == 1


class TestDocument:
    """文档表行为。"""

    def test_insert_with_defaults(self, session: Session, space: Space) -> None:
        doc = Document(
            document_name="用户登录",
            identify="user-login",
            space_id=space.space_id,
            markdown="## 接口说明",
            member_id=space.member_id,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        assert doc.parent_id == 0
        assert doc.order_sort == 0
        assert doc.version == 1
        assert doc.is_open == 0
        assert doc.markdown_theme == "theme__light"

    def test_space_identify_unique(self, session: Session, space: Space) -> None:
        """同一空间内 identify 唯一；不同空间可重复。"""
        session.add(
            Document(
                document_name="a",
                identify="same",
                space_id=space.space_id,
                member_id=space.member_id,
            )
        )
        session.commit()

        other = Space(
            space_name="另一个库",
            identify="other-space",
            member_id=space.member_id,
            create_time=datetime.now(),
        )
        session.add(other)
        session.flush()
        session.add(
            Document(
                document_name="b",
                identify="same",
                space_id=other.space_id,
                member_id=space.member_id,
            )
        )
        session.commit()

        session.add(
            Document(
                document_name="c",
                identify="same",
                space_id=space.space_id,
                member_id=space.member_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_cascade_delete_history(self, session: Session, space: Space) -> None:
        doc = Document(
            document_name="待删",
            identify="to-delete",
            space_id=space.space_id,
            member_id=space.member_id,
        )
        session.add(doc)
        session.flush()
        session.add(
            DocumentHistory(
                document_id=doc.document_id,
                markdown="v1",
                member_id=space.member_id,
                version=1,
            )
        )
        session.commit()

        session.delete(doc)
        session.commit()
        remaining = session.scalar(
            select(DocumentHistory).where(DocumentHistory.document_id == doc.document_id)
        )
        assert remaining is None

    def test_foreign_key_to_space(self, session: Session) -> None:
        session.add(
            Document(
                document_name="孤儿",
                identify="orphan",
                space_id=9999,
                member_id=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestAttachment:
    """附件表行为。"""

    def test_optional_document_id(self, session: Session, space: Space) -> None:
        item = Attachment(
            space_id=space.space_id,
            file_name="a.png",
            file_path="uploads/a.png",
            file_size=1024.0,
            create_at=space.member_id,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        assert item.document_id is None
        assert item.file_size == 1024.0

    def test_cascade_delete_with_document(self, session: Session, space: Space) -> None:
        doc = Document(
            document_name="带附件",
            identify="with-attach",
            space_id=space.space_id,
            member_id=space.member_id,
        )
        session.add(doc)
        session.flush()
        session.add(
            Attachment(
                space_id=space.space_id,
                document_id=doc.document_id,
                file_name="a.png",
                file_path="uploads/a.png",
                create_at=space.member_id,
            )
        )
        session.commit()

        session.delete(doc)
        session.commit()
        assert session.scalar(select(Attachment)) is None


class TestOptionAndLog:
    """配置与日志表。"""

    def test_option_key_unique(self, session: Session) -> None:
        session.add(Option(option_key="site_name", option_value="per_doc"))
        session.commit()
        session.add(Option(option_key="site_name", option_value="other"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_log_insert(self, session: Session, member: Member) -> None:
        session.add(
            Log(
                user_id=member.member_id,
                username=member.account,
                action="login",
                detail="登录成功",
                ip="127.0.0.1",
            )
        )
        session.commit()
        assert session.scalar(select(Log)) is not None


class TestMigrationParity:
    """模型元数据与实际库结构一致。"""

    def test_tables_created_in_memory_db(self, session: Session) -> None:
        inspector = inspect(session.get_bind())
        actual = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(actual)

    def test_column_types_match_models(self, session: Session) -> None:
        inspector = inspect(session.get_bind())
        columns = {col["name"]: col for col in inspector.get_columns("md_documents")}
        assert columns["version"]["type"].__class__.__name__ == "BIGINT"
        assert columns["markdown"]["type"].__class__.__name__ == "TEXT"
        assert columns["order_sort"]["type"].__class__.__name__ == "INTEGER"

    def test_foreign_keys_present(self, session: Session) -> None:
        inspector = inspect(session.get_bind())
        fks = inspector.get_foreign_keys("md_document_history")
        assert any(fk["referred_table"] == "md_documents" for fk in fks)

    def test_indexes_present(self, session: Session) -> None:
        inspector = inspect(session.get_bind())
        indexes = {idx["name"] for idx in inspector.get_indexes("md_documents")}
        assert "ix_md_documents_space_id" in indexes
        assert "ix_md_documents_parent_id" in indexes

    def test_server_defaults_present(self, session: Session) -> None:
        """建表语句含 server_default，裸 SQL 插入也能落默认值。"""
        session.execute(
            text(
                "INSERT INTO md_spaces (space_name, identify, member_id) "
                "VALUES ('裸插入', 'raw-insert', 1)"
            )
        )
        session.commit()
        row = session.execute(
            text("SELECT editor, auto_save, is_private FROM md_spaces WHERE identify='raw-insert'")
        ).one()
        assert row.editor == "markdown"
        assert row.auto_save == 1
        assert row.is_private == 0
