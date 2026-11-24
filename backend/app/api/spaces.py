"""文档库接口。

只做「参数解析 → 校验 → 调 service → 组装响应」，
ORM 查询与事务边界都在 ``app.services.space_service`` 中。

接口清单：
- ``GET    /api/spaces``           文档库列表
- ``POST   /api/spaces``           创建文档库
- ``GET    /api/spaces/{key}``     文档库详情
- ``PUT    /api/spaces/{key}``     更新文档库
- ``DELETE /api/spaces/{key}``     删除文档库
- ``GET    /api/spaces/{key}/access``  查询访问授权状态
- ``POST   /api/spaces/{key}/access``  提交访问密码
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import current_user_optional, get_db, require_csrf
from app.core.exceptions import PermissionError
from app.core.session import read_granted_space_ids, write_access_cookie
from app.models.member import Member
from app.models.space import Space
from app.schemas.space import (
    AccessCheckOut,
    AccessSubmit,
    SpaceBrief,
    SpaceCreate,
    SpaceListOut,
    SpaceOut,
    SpaceUpdate,
)
from app.services import space_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.get("", response_model=SpaceListOut)
def list_spaces(
    request: Request,
    group_name: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
) -> SpaceListOut:
    """文档库列表。

    登录用户看到全部文档库；游客只看到公开库与已通过访问密码的私有库。
    """
    granted = read_granted_space_ids(request.cookies.get(settings.access_cookie_name))
    spaces = space_service.list_spaces(
        db=db,
        member=member,
        granted_space_ids=granted,
        group_name=group_name,
        keyword=keyword,
    )
    items = [_to_brief(space, member, db) for space in spaces]
    return SpaceListOut(
        total=len(items),
        items=items,
        groups=space_service.list_space_groups(db, member),
    )


@router.post("", response_model=SpaceOut, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: SpaceCreate,
    db: Session = Depends(get_db),
    member: Member = Depends(current_user_optional),
    _csrf: None = Depends(require_csrf),
) -> SpaceOut:
    """创建文档库。"""
    if member is None:
        raise PermissionError("请先登录后再创建文档库")
    space = space_service.create_space(db, payload, member)
    return _to_out(space, member, db)


@router.get("/{key}", response_model=SpaceOut)
def get_space(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
) -> SpaceOut:
    """文档库详情。"""
    space = space_service.require_space(db, key)
    granted = read_granted_space_ids(request.cookies.get(settings.access_cookie_name))
    space_service.require_readable(space, member, granted)
    return _to_out(space, member, db)


@router.put("/{key}", response_model=SpaceOut)
def update_space(
    key: str,
    payload: SpaceUpdate,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
    _csrf: None = Depends(require_csrf),
) -> SpaceOut:
    """更新文档库。"""
    # 先校验登录态再查库，避免未登录者通过 404/403 的差异探测文档库是否存在
    operator = _require_operator(member)
    space = space_service.require_space(db, key)
    updated = space_service.update_space(db, space, payload, operator)
    return _to_out(updated, member, db)


@router.delete("/{key}", status_code=status.HTTP_200_OK)
def delete_space(
    key: str,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
    _csrf: None = Depends(require_csrf),
) -> dict[str, bool]:
    """删除文档库及其全部文档。"""
    # 先校验登录态再查库，避免未登录者通过 404/403 的差异探测文档库是否存在
    operator = _require_operator(member)
    space = space_service.require_space(db, key)
    space_service.delete_space(db, space, operator)
    return {"success": True}


@router.get("/{key}/access", response_model=AccessCheckOut)
def check_access(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
) -> AccessCheckOut:
    """查询当前请求者对私有库的访问授权状态。"""
    space = space_service.require_space(db, key)
    granted = read_granted_space_ids(request.cookies.get(settings.access_cookie_name))
    has_access = space_service.can_read(space, member, granted)
    return AccessCheckOut(
        granted=has_access,
        space_id=space.space_id,
        identify=space.identify,
    )


@router.post("/{key}/access", response_model=AccessCheckOut)
def submit_access(
    key: str,
    request: Request,
    response: Response,
    payload: AccessSubmit,
    db: Session = Depends(get_db),
    member: Member | None = Depends(current_user_optional),
) -> AccessCheckOut:
    """提交访问密码，通过后把授权写入 Cookie。"""
    space = space_service.require_space(db, key)
    if not space_service.verify_access_password(space, payload.password):
        raise PermissionError("访问密码错误")

    granted = read_granted_space_ids(request.cookies.get(settings.access_cookie_name))
    if space.space_id not in granted:
        granted.append(space.space_id)
    write_access_cookie(response, granted)

    return AccessCheckOut(
        granted=True,
        space_id=space.space_id,
        identify=space.identify,
    )


def _require_operator(member: Member | None) -> Member:
    """取出写操作的操作者；未登录时抛 ``PermissionError``。"""
    if member is None:
        raise PermissionError("请先登录后再操作文档库")
    return member


def _to_out(space: Space, member: Member | None, db: Session) -> SpaceOut:
    """组装文档库详情响应。"""
    result = SpaceOut.model_validate(space)
    result.doc_count = space_service.count_documents(db, space.space_id)
    result.is_owner = member is not None and member.member_id == space.member_id
    return result


def _to_brief(space: Space, member: Member | None, db: Session) -> SpaceBrief:
    """组装文档库列表项。"""
    result = SpaceBrief.model_validate(space)
    result.doc_count = space_service.count_documents(db, space.space_id)
    result.is_owner = member is not None and member.member_id == space.member_id
    return result
