"""文档树模块单元测试（B6 service 层）。

覆盖：
- 树构建（层级挂载、排序、脏数据降级）
- 排序值分配与同级重排
- 节点移动（换父级、调序、成环校验、越界校验）
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.document import Document
from app.models.member import Member
from app.models.space import Space
from app.services import tree_service


@pytest.fixture()
def owner(session: Session) -> Member:
    """文档库创建者。"""
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
def space(session: Session, owner: Member) -> Space:
    """一个空的文档库。"""
    item = Space(
        space_name="接口文档",
        identify="api-docs",
        group_name="默认分组",
        description="RESTful API 说明",
        member_id=owner.member_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def add_document(
    session: Session,
    space: Space,
    name: str,
    parent_id: int = 0,
    order_sort: int = 0,
    member_id: int = 1,
) -> Document:
    """插入一个测试文档节点。"""
    document = Document(
        document_name=name,
        identify=f"{name}-{order_sort}",
        space_id=space.space_id,
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


class TestBuildTree:
    """树构建。"""

    def test_empty_space(self, session: Session, space: Space) -> None:
        assert tree_service.build_tree(session, space.space_id) == []

    def test_flat_nodes_become_roots(self, session: Session, space: Space, owner: Member) -> None:
        add_document(session, space, "根", 0, 1, owner.member_id)
        add_document(session, space, "另一根", 0, 2, owner.member_id)
        nodes = tree_service.build_tree(session, space.space_id)
        assert len(nodes) == 2
        assert [node.document_name for node in nodes] == ["根", "另一根"]

    def test_nested_children(self, session: Session, space: Space, owner: Member) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        child = add_document(session, space, "子", root.document_id, 1, owner.member_id)
        grand = add_document(session, space, "孙", child.document_id, 1, owner.member_id)

        nodes = tree_service.build_tree(session, space.space_id)
        assert len(nodes) == 1
        assert nodes[0].is_dir is True
        assert nodes[0].children[0].document_id == child.document_id
        assert nodes[0].children[0].children[0].document_id == grand.document_id
        assert nodes[0].children[0].is_dir is True

    def test_leaf_is_not_dir(self, session: Session, space: Space, owner: Member) -> None:
        add_document(session, space, "叶子", 0, 1, owner.member_id)
        nodes = tree_service.build_tree(session, space.space_id)
        assert nodes[0].is_dir is False
        assert nodes[0].children == []

    def test_sibling_order_follows_order_sort(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        add_document(session, space, "第二", 0, 2, owner.member_id)
        add_document(session, space, "第一", 0, 1, owner.member_id)
        nodes = tree_service.build_tree(session, space.space_id)
        assert [node.document_name for node in nodes] == ["第一", "第二"]

    def test_same_order_sort_falls_back_to_document_id(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        first = add_document(session, space, "甲", 0, 1, owner.member_id)
        second = add_document(session, space, "乙", 0, 1, owner.member_id)
        nodes = tree_service.build_tree(session, space.space_id)
        assert [node.document_id for node in nodes] == [first.document_id, second.document_id]

    def test_orphan_node_degrades_to_root(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        """父节点缺失的脏数据降级为顶层，不丢失节点。"""
        add_document(session, space, "孤儿", 9999, 1, owner.member_id)
        nodes = tree_service.build_tree(session, space.space_id)
        assert len(nodes) == 1
        assert nodes[0].document_name == "孤儿"

    def test_count_documents(self, session: Session, space: Space, owner: Member) -> None:
        add_document(session, space, "一", 0, 1, owner.member_id)
        add_document(session, space, "二", 0, 2, owner.member_id)
        assert tree_service.count_documents(session, space.space_id) == 2

    def test_only_current_space(self, session: Session, space: Space, owner: Member) -> None:
        add_document(session, space, "本库", 0, 1, owner.member_id)
        other = Space(
            space_name="另一个库",
            identify="other",
            group_name="默认分组",
            member_id=owner.member_id,
        )
        session.add(other)
        session.commit()
        session.refresh(other)
        add_document(session, other, "他库文档", 0, 1, owner.member_id)

        nodes = tree_service.build_tree(session, space.space_id)
        assert len(nodes) == 1
        assert nodes[0].document_name == "本库"


class TestOrderSort:
    """排序值分配与重排。"""

    def test_next_order_sort_empty_parent(self, session: Session, space: Space) -> None:
        assert tree_service.next_order_sort(session, space.space_id, 0) == 1

    def test_next_order_sort_after_existing(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        add_document(session, space, "一", 0, 1, owner.member_id)
        add_document(session, space, "二", 0, 5, owner.member_id)
        # 取同级最大值 + 1，避免与既有值重复
        assert tree_service.next_order_sort(session, space.space_id, 0) == 6

    def test_next_order_sort_is_scoped_to_parent(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        add_document(session, space, "子", root.document_id, 3, owner.member_id)
        assert tree_service.next_order_sort(session, space.space_id, 0) == 2
        assert tree_service.next_order_sort(session, space.space_id, root.document_id) == 4

    def test_reorder_siblings_makes_continuous(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        first = add_document(session, space, "一", 0, 10, owner.member_id)
        second = add_document(session, space, "二", 0, 20, owner.member_id)
        third = add_document(session, space, "三", 0, 30, owner.member_id)

        reordered = tree_service.reorder_siblings(session, space.space_id, 0)
        assert reordered == [first.document_id, second.document_id, third.document_id]
        session.commit()

        assert first.order_sort == 1
        assert second.order_sort == 2
        assert third.order_sort == 3


class TestMoveDocument:
    """节点移动。"""

    def test_move_to_top_level(self, session: Session, space: Space, owner: Member) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        child = add_document(session, space, "子", root.document_id, 1, owner.member_id)

        tree_service.move_document(session, space.space_id, child.document_id, target_parent_id=0)
        session.commit()

        assert child.parent_id == 0
        nodes = tree_service.build_tree(session, space.space_id)
        assert len(nodes) == 2

    def test_move_under_another_parent(self, session: Session, space: Space, owner: Member) -> None:
        root_a = add_document(session, space, "A", 0, 1, owner.member_id)
        root_b = add_document(session, space, "B", 0, 2, owner.member_id)
        child = add_document(session, space, "子", root_a.document_id, 1, owner.member_id)

        tree_service.move_document(
            session, space.space_id, child.document_id, target_parent_id=root_b.document_id
        )
        session.commit()

        assert child.parent_id == root_b.document_id
        assert child.order_sort == 1

    def test_move_with_target_order(self, session: Session, space: Space, owner: Member) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        first = add_document(session, space, "一", root.document_id, 1, owner.member_id)
        second = add_document(session, space, "二", root.document_id, 2, owner.member_id)
        third = add_document(session, space, "三", root.document_id, 3, owner.member_id)

        tree_service.move_document(
            session,
            space.space_id,
            third.document_id,
            target_parent_id=root.document_id,
            target_order=1,
        )
        session.commit()

        assert third.order_sort == 1
        assert first.order_sort == 2
        assert second.order_sort == 3

    def test_move_appends_when_order_is_none(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        add_document(session, space, "一", root.document_id, 1, owner.member_id)
        second = add_document(session, space, "二", root.document_id, 2, owner.member_id)

        tree_service.move_document(
            session, space.space_id, second.document_id, target_parent_id=root.document_id
        )
        session.commit()

        assert second.order_sort == 2

    def test_old_parent_siblings_reordered(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        root_a = add_document(session, space, "A", 0, 1, owner.member_id)
        root_b = add_document(session, space, "B", 0, 2, owner.member_id)
        first = add_document(session, space, "一", root_a.document_id, 5, owner.member_id)
        second = add_document(session, space, "二", root_a.document_id, 9, owner.member_id)

        tree_service.move_document(
            session, space.space_id, second.document_id, target_parent_id=root_b.document_id
        )
        session.commit()

        # 旧父级只剩一个子节点，排序值被归一为 1
        assert first.order_sort == 1
        assert second.order_sort == 1

    def test_move_to_itself_rejected(self, session: Session, space: Space, owner: Member) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        with pytest.raises(ValidationError):
            tree_service.move_document(
                session, space.space_id, root.document_id, target_parent_id=root.document_id
            )

    def test_move_under_own_child_rejected(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        child = add_document(session, space, "子", root.document_id, 1, owner.member_id)

        with pytest.raises(ValidationError):
            tree_service.move_document(
                session, space.space_id, root.document_id, target_parent_id=child.document_id
            )

    def test_move_under_deep_descendant_rejected(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        child = add_document(session, space, "子", root.document_id, 1, owner.member_id)
        grand = add_document(session, space, "孙", child.document_id, 1, owner.member_id)

        with pytest.raises(ValidationError):
            tree_service.move_document(
                session, space.space_id, root.document_id, target_parent_id=grand.document_id
            )

    def test_move_missing_document(self, session: Session, space: Space) -> None:
        with pytest.raises(NotFoundError):
            tree_service.move_document(session, space.space_id, 999999, target_parent_id=0)

    def test_move_missing_parent(self, session: Session, space: Space, owner: Member) -> None:
        child = add_document(session, space, "子", 0, 1, owner.member_id)
        with pytest.raises(NotFoundError):
            tree_service.move_document(
                session, space.space_id, child.document_id, target_parent_id=888888
            )

    def test_move_out_of_space_rejected(
        self, session: Session, space: Space, owner: Member
    ) -> None:
        other = Space(
            space_name="另一个库",
            identify="other",
            group_name="默认分组",
            member_id=owner.member_id,
        )
        session.add(other)
        session.commit()
        session.refresh(other)
        foreign = add_document(session, other, "他库", 0, 1, owner.member_id)

        with pytest.raises(NotFoundError):
            tree_service.move_document(
                session, space.space_id, foreign.document_id, target_parent_id=0
            )

    def test_target_order_out_of_range(self, session: Session, space: Space, owner: Member) -> None:
        root = add_document(session, space, "根", 0, 1, owner.member_id)
        child = add_document(session, space, "子", root.document_id, 1, owner.member_id)

        with pytest.raises(ValidationError):
            tree_service.move_document(
                session,
                space.space_id,
                child.document_id,
                target_parent_id=root.document_id,
                target_order=5,
            )
