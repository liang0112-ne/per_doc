"""文档树接口。

只做「参数解析 → 校验 → 调 service → 组装响应」，
ORM 查询与事务边界都在 ``app.services.tree_service`` 中。

接口清单：
- ``GET /api/spaces/{key}/tree``  读取文档树

说明：节点移动（``POST /api/spaces/{key}/documents/{id}/move``）
按方案归属 B7 的文档路由，其排序维护逻辑已在本模块的
``tree_service`` 中实现，B7 直接调用即可。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import current_user_optional, get_db
from app.core.session import read_granted_space_ids
from app.models.member import Member
from app.schemas.tree import SpaceTreeOut, TreeNodeOut, TreeSpaceOut
from app.services import space_service, tree_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spaces/{key}/tree", tags=["tree"])


@router.get("", response_model=SpaceTreeOut)
def get_tree(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
) -> SpaceTreeOut:
    """读取文档库的文档树。

    读取权限与文档库一致：公开库任何人可读，私有库需登录或已提交访问密码。
    """
    space = space_service.require_space(db, key)
    granted = read_granted_space_ids(request.cookies.get(settings.access_cookie_name))
    space_service.require_readable(space, member, granted)

    nodes = tree_service.build_tree(db, space.space_id)
    return SpaceTreeOut(
        space=TreeSpaceOut(
            space_id=space.space_id,
            space_name=space.space_name,
            identify=space.identify,
            description=space.description,
        ),
        tree=[_to_node(node) for node in nodes],
        total=tree_service.count_documents(db, space.space_id),
    )


def _to_node(node: tree_service.TreeNode) -> TreeNodeOut:
    """把 service 层的树节点转换为响应节点。"""
    return TreeNodeOut(
        document_id=node.document_id,
        document_name=node.document_name,
        identify=node.identify,
        parent_id=node.parent_id,
        order_sort=node.order_sort,
        is_open=node.is_open,
        is_dir=node.is_dir,
        version=node.version,
        children=[_to_node(child) for child in node.children],
    )
