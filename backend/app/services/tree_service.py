"""文档树业务逻辑。

职责边界：
- 文档树的构建（扁平记录 → 递归嵌套结构）
- 同级排序值的分配与重排
- 节点移动（换父级 / 调整顺序）所需的校验与排序维护

本模块不感知 HTTP（不抛 ``HTTPException``、不 import ``Depends``），
也不直接产出响应 schema —— 响应组装由 ``app.api`` 层完成。

算法说明：
- 拉取全部节点时按 ``order_sort``、``document_id`` 排序，保证顺序稳定
- 新节点的 ``order_sort`` 取同级最大值 + 1，避免同级出现重复值
- 拖拽排序后把受影响的同级节点重排为连续的 1..N

与常见做法的差异：常见做法是返回**扁平**节点列表交给前端树组件自行拼装，
per_doc 直接在服务端拼成递归结构，前端只负责渲染与拖拽。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.document import Document

logger = logging.getLogger(__name__)

# 根节点的 parent_id 取值
ROOT_PARENT_ID = 0


@dataclass
class TreeNode:
    """文档树节点（service 层内部结构）。

    ``children`` 为空列表表示叶子节点。
    """

    document_id: int
    document_name: str
    identify: str
    parent_id: int
    order_sort: int
    is_open: int = 0
    version: int = 1
    is_dir: bool = False
    children: list[TreeNode] = field(default_factory=list)


def list_documents(db: Session, space_id: int) -> list[Document]:
    """按库取出全部文档节点，按 ``order_sort``、``document_id`` 排序。

    排序规则：先按 ``order_sort`` 升序，同值时按 ``document_id`` 升序，
    保证顺序稳定。

    Args:
        db: 数据库会话。
        space_id: 文档库 id。

    Returns:
        该库下的全部文档节点。
    """
    stmt = (
        select(Document)
        .where(Document.space_id == space_id)
        .order_by(Document.order_sort.asc(), Document.document_id.asc())
    )
    return list(db.scalars(stmt).all())


def build_tree(db: Session, space_id: int) -> list[TreeNode]:
    """构建文档库的递归树结构。

    算法：
    1. 一次性拉取该库全部节点（避免 N+1 查询）
    2. 先建立 ``document_id → 节点`` 的索引
    3. 再按 ``parent_id`` 把节点挂到父节点下，``parent_id`` 为 0 的节点作为顶层
    4. 若某节点的父节点不存在（脏数据），降级为顶层节点，避免整棵子树丢失

    Args:
        db: 数据库会话。
        space_id: 文档库 id。

    Returns:
        顶层节点列表，每个节点内含递归的 ``children``。
    """
    documents = list_documents(db, space_id)
    if not documents:
        return []

    nodes: dict[int, TreeNode] = {}
    for document in documents:
        nodes[document.document_id] = TreeNode(
            document_id=document.document_id,
            document_name=document.document_name,
            identify=document.identify,
            parent_id=document.parent_id,
            order_sort=document.order_sort,
            is_open=document.is_open,
            version=document.version,
        )

    roots: list[TreeNode] = []
    for document in documents:
        node = nodes[document.document_id]
        parent = nodes.get(document.parent_id) if document.parent_id else None
        if parent is None:
            # 顶层节点，或父节点缺失的脏数据节点
            roots.append(node)
        else:
            parent.children.append(node)
            parent.is_dir = True

    return roots


def count_documents(db: Session, space_id: int) -> int:
    """统计文档库下的节点总数。"""
    return int(
        db.scalar(select(func.count()).select_from(Document).where(Document.space_id == space_id))
        or 0
    )


def next_order_sort(db: Session, space_id: int, parent_id: int) -> int:
    """计算新节点在同一父级下的排序值。

    ``order_sort`` 取「同级已有节点数 + 1」。此处改为取同级最大值 + 1，
    避免同级节点被外部批量改写 ``order_sort`` 后出现重复。

    Args:
        db: 数据库会话。
        space_id: 文档库 id。
        parent_id: 父节点 id，0 表示顶层。

    Returns:
        可用的排序值，最小为 1。
    """
    max_sort = db.scalar(
        select(func.max(Document.order_sort)).where(
            Document.space_id == space_id,
            Document.parent_id == parent_id,
        )
    )
    return int(max_sort or 0) + 1


def reorder_siblings(
    db: Session,
    space_id: int,
    parent_id: int,
    exclude_id: int | None = None,
) -> list[int]:
    """把某父节点下的子节点排序值重排为连续的 1..N。

    拖拽排序后同级可能出现空洞或重复，调用此函数可恢复为连续序号，
    顺序沿用当前的 ``order_sort``、``document_id`` 次序。

    Args:
        db: 数据库会话。
        space_id: 文档库 id。
        parent_id: 父节点 id，0 表示顶层。
        exclude_id: 需要排除的节点 id；移动场景下排除正在移动的节点。

    Returns:
        被重排的节点 id 列表（按新顺序）。
    """
    stmt = (
        select(Document)
        .where(Document.space_id == space_id, Document.parent_id == parent_id)
        .order_by(Document.order_sort.asc(), Document.document_id.asc())
    )
    if exclude_id is not None:
        stmt = stmt.where(Document.document_id != exclude_id)

    documents = list(db.scalars(stmt).all())
    reordered: list[int] = []
    for index, document in enumerate(documents, start=1):
        if document.order_sort != index:
            document.order_sort = index
        reordered.append(document.document_id)
    return reordered


def validate_move(
    db: Session,
    space_id: int,
    document_id: int,
    target_parent_id: int,
) -> Document:
    """校验一次节点移动是否合法。

    校验内容：
    1. 目标节点必须存在且属于该库
    2. 不能挂到自己的子节点下（会形成环）
    3. 目标父节点必须存在且属于该库（0 表示顶层）

    Args:
        db: 数据库会话。
        space_id: 文档库 id。
        document_id: 被移动的节点 id。
        target_parent_id: 目标父节点 id。

    Returns:
        被移动的节点。

    Raises:
        NotFoundError: 节点或目标父节点不存在。
        ValidationError: 移动会形成环。
    """
    document = db.get(Document, document_id)
    if document is None or document.space_id != space_id:
        raise NotFoundError("文档不存在")

    if target_parent_id == ROOT_PARENT_ID:
        return document

    if target_parent_id == document_id:
        raise ValidationError("不能将文档移动到自身之下")

    parent = db.get(Document, target_parent_id)
    if parent is None or parent.space_id != space_id:
        raise NotFoundError("目标父级不存在")

    if _is_descendant(db, space_id, target_parent_id, document_id):
        raise ValidationError("不能将文档移动到其子节点之下")

    return document


def move_document(
    db: Session,
    space_id: int,
    document_id: int,
    target_parent_id: int,
    target_order: int | None = None,
) -> Document:
    """移动节点：换父级 + 调整同级顺序。

    Args:
        db: 数据库会话。
        space_id: 文档库 id。
        document_id: 被移动的节点 id。
        target_parent_id: 目标父节点 id，0 表示顶层。
        target_order: 目标同级位置（从 1 开始）；``None`` 表示追加到末尾。

    Returns:
        移动后的节点。

    Raises:
        NotFoundError: 节点或目标父节点不存在。
        ValidationError: 移动会形成环或目标位置非法。
    """
    document = validate_move(
        db,
        space_id=space_id,
        document_id=document_id,
        target_parent_id=target_parent_id,
    )

    old_parent_id = document.parent_id
    # 先按旧父级重排（排除正在移动的节点），再改父级，
    # 否则查询条件会因父级已变更而漏掉旧父级下的其它节点
    if old_parent_id != target_parent_id:
        reorder_siblings(db, space_id, old_parent_id, exclude_id=document_id)
    document.parent_id = target_parent_id

    siblings = list(
        db.scalars(
            select(Document)
            .where(
                Document.space_id == space_id,
                Document.parent_id == target_parent_id,
                Document.document_id != document_id,
            )
            .order_by(Document.order_sort.asc(), Document.document_id.asc())
        ).all()
    )

    if target_order is None:
        position = len(siblings) + 1
    else:
        position = target_order
        if position < 1 or position > len(siblings) + 1:
            raise ValidationError("目标排序位置超出范围")

    siblings.insert(position - 1, document)
    for index, sibling in enumerate(siblings, start=1):
        sibling.order_sort = index

    return document


def _is_descendant(
    db: Session,
    space_id: int,
    candidate_id: int,
    ancestor_id: int,
) -> bool:
    """判断 ``candidate_id`` 是否是 ``ancestor_id`` 的后代（不含自身）。

    沿 ``parent_id`` 向上回溯，最多回溯到根节点。

    Args:
        db: 数据库会话。
        space_id: 文档库 id。
        candidate_id: 待判断的节点 id。
        ancestor_id: 祖先节点 id。

    Returns:
        是祖先的后代返回 True。
    """
    current = db.get(Document, candidate_id)
    seen: set[int] = set()
    while current is not None and current.parent_id != ROOT_PARENT_ID:
        if current.parent_id in seen:
            # 已存在环，视为非法数据，直接判定为后代以阻止移动
            return True
        seen.add(current.parent_id)
        if current.parent_id == ancestor_id:
            return True
        parent = db.get(Document, current.parent_id)
        if parent is None or parent.space_id != space_id:
            return False
        current = parent
    return False
