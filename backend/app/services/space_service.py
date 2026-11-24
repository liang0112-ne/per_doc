"""文档库（Space）业务逻辑。

职责边界：
- 文档库的增删改查与可见性判定
- 访问密码的设置与校验
- 事务边界（``commit`` / ``rollback``）统一在本模块

本模块不感知 HTTP（不抛 ``HTTPException``、不 import ``Depends``）。

权限模型（重构方案 §5.4，per_doc 只有两种身份）：

| 身份 | 判定 | 权限 |
|---|---|---|
| 登录用户 | Session 有效 | 读写全部文档库 |
| 游客 | 无 Session | 只读公开库；私有库需通过访问密码 |

移植自 mindoc-master/controllers/BookController.go 与
models/BookModel.go，但删除了团队 / 角色矩阵 / 分享 / 导入导出等特性。
"""

from __future__ import annotations

import logging

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from app.core.security import hash_password, verify_password
from app.models.document import Document
from app.models.member import Member
from app.models.space import Space
from app.schemas.space import SpaceCreate, SpaceUpdate
from app.utils.identifier import generate_identify, suggest_identify

logger = logging.getLogger(__name__)

# 文档树的根节点标识，新建文档库时写入
ROOT_DOCUMENT_IDENTIFY = "root"

# 新建文档库时自动创建的空白文档名称
INITIAL_DOCUMENT_NAME = "空白文档"


def get_space_by_identify(db: Session, identify: str) -> Space | None:
    """按标识查询文档库；不存在返回 ``None``。"""
    return db.scalar(select(Space).where(Space.identify == identify))


def get_space_by_id(db: Session, space_id: int) -> Space | None:
    """按主键查询文档库；不存在返回 ``None``。"""
    return db.get(Space, space_id)


def require_space(db: Session, identify: str) -> Space:
    """按标识取文档库，不存在则抛 ``NotFoundError``。"""
    space = get_space_by_identify(db, identify)
    if space is None:
        raise NotFoundError("文档库不存在")
    return space


def list_spaces(
    db: Session,
    member: Member | None,
    granted_space_ids: list[int] | None = None,
    group_name: str | None = None,
    keyword: str | None = None,
) -> list[Space]:
    """列出当前请求者可见的文档库。

    可见性规则：
    - 登录用户：全部文档库
    - 游客：公开库 + 已通过访问密码校验的私有库

    Args:
        db: 数据库会话。
        member: 当前登录用户；``None`` 表示游客。
        granted_space_ids: 游客已通过访问密码校验的文档库 id 列表。
        group_name: 按分组过滤；``None`` 表示不过滤。
        keyword: 按名称 / 标识模糊匹配；``None`` 表示不过滤。

    Returns:
        按 ``order_index`` 升序、主键降序排列的文档库列表。
    """
    stmt: Select[tuple[Space]] = select(Space)

    if member is None:
        granted = granted_space_ids or []
        if granted:
            stmt = stmt.where((Space.is_private == 0) | (Space.space_id.in_(granted)))
        else:
            stmt = stmt.where(Space.is_private == 0)

    if group_name:
        stmt = stmt.where(Space.group_name == group_name)

    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(Space.space_name.like(pattern) | Space.identify.like(pattern))

    stmt = stmt.order_by(Space.order_index.asc(), Space.space_id.desc())
    return list(db.scalars(stmt).all())


def count_documents(db: Session, space_id: int) -> int:
    """统计文档库下的文档数（实时统计，不做缓存）。"""
    return int(
        db.scalar(select(func.count()).select_from(Document).where(Document.space_id == space_id))
        or 0
    )


def list_space_groups(db: Session, member: Member | None) -> list[str]:
    """列出当前请求者可见文档库涉及的分组名。"""
    spaces = list_spaces(db, member)
    groups: list[str] = []
    for space in spaces:
        name = space.group_name or "默认分组"
        if name not in groups:
            groups.append(name)
    return groups


def create_space(
    db: Session,
    payload: SpaceCreate,
    owner: Member,
) -> Space:
    """创建文档库。

    创建时会：
    1. 生成或校验唯一标识
    2. 若设为私有库，必须提供访问密码
    3. 自动创建根目录节点与一篇空白文档（对应 mindoc 的建库行为）

    Args:
        db: 数据库会话。
        payload: 创建参数。
        owner: 创建者。

    Returns:
        新建的文档库。

    Raises:
        ValidationError: 标识格式非法、私有库缺访问密码等。
        ConflictError: 标识已被占用。
    """
    identify = _resolve_identify(db, payload)
    access_password = payload.access_password
    is_private = payload.is_private

    if is_private == 1 and not access_password:
        raise ValidationError("私有文档库必须设置访问密码")
    if is_private == 0 and access_password:
        # 公开库设置访问密码没有意义，直接忽略以免留下隐患
        access_password = None

    space = Space(
        space_name=payload.space_name,
        identify=identify,
        group_name=payload.group_name or "默认分组",
        description=payload.description or "",
        cover=payload.cover,
        editor=payload.editor or "markdown",
        theme=payload.theme or "default",
        is_private=is_private,
        password=hash_password(access_password) if access_password else None,
        auto_save=payload.auto_save,
        history_count=payload.history_count,
        member_id=owner.member_id,
    )
    db.add(space)
    db.flush()

    _create_root_document(db, space, owner.member_id)

    db.commit()
    db.refresh(space)
    logger.info("文档库创建成功 (space_id=%s, identify=%s)", space.space_id, space.identify)
    return space


def update_space(
    db: Session,
    space: Space,
    payload: SpaceUpdate,
    operator: Member,
) -> Space:
    """更新文档库。

    只更新传入的字段；未传的字段保持原值。

    Args:
        db: 数据库会话。
        space: 目标文档库。
        payload: 更新参数。
        operator: 操作者（须为文档库创建者）。

    Returns:
        更新后的文档库。

    Raises:
        PermissionError: 操作者不是创建者。
        ValidationError: 私有库缺少访问密码等。
    """
    _require_owner(space, operator)

    if payload.is_private is not None:
        # 切到私有且尚未设置过密码时，必须同时提供访问密码
        if payload.is_private == 1 and not space.password and not payload.access_password:
            raise ValidationError("私有文档库必须设置访问密码")
        space.is_private = payload.is_private
        if payload.is_private == 0:
            # 切回公开时清除访问密码，避免残留凭据
            space.password = None

    if payload.access_password:
        space.password = hash_password(payload.access_password)

    for field in ("space_name", "description", "group_name", "cover", "editor", "theme"):
        value = getattr(payload, field)
        if value is not None:
            setattr(space, field, value)

    if payload.auto_save is not None:
        space.auto_save = payload.auto_save
    if payload.history_count is not None:
        space.history_count = payload.history_count

    db.commit()
    db.refresh(space)
    logger.info("文档库更新成功 (space_id=%s)", space.space_id)
    return space


def delete_space(db: Session, space: Space, operator: Member) -> None:
    """删除文档库及其全部文档。

    数据库层已配置 ``md_documents.space_id`` 不级联，因此这里显式
    递归清理子节点、历史版本与附件，避免留下孤儿数据。

    Args:
        db: 数据库会话。
        space: 目标文档库。
        operator: 操作者（须为文档库创建者）。

    Raises:
        PermissionError: 操作者不是创建者。
    """
    _require_owner(space, operator)

    document_ids = list(
        db.scalars(select(Document.document_id).where(Document.space_id == space.space_id)).all()
    )

    if document_ids:
        # 历史版本与附件已在表上配置 ondelete=CASCADE，随文档删除一并清理
        db.execute(delete(Document).where(Document.space_id == space.space_id))

    db.delete(space)
    db.commit()
    logger.info("文档库删除成功 (space_id=%s, documents=%s)", space.space_id, len(document_ids))


def verify_access_password(space: Space, password: str) -> bool:
    """校验私有文档库的访问密码。

    Args:
        space: 目标文档库。
        password: 访问密码明文。

    Returns:
        校验通过返回 True。公开库视为无需密码，返回 False。
    """
    if space.is_private != 1 or not space.password:
        return False
    return verify_password(space.password, password)


def can_read(space: Space, member: Member | None, granted_space_ids: list[int]) -> bool:
    """判定当前请求者是否有权读取该文档库。

    Args:
        space: 目标文档库。
        member: 当前登录用户；``None`` 表示游客。
        granted_space_ids: 游客已通过访问密码校验的文档库 id 列表。

    Returns:
        有读权限返回 True。
    """
    if member is not None:
        return True
    if space.is_private == 0:
        return True
    return space.space_id in granted_space_ids


def require_readable(
    space: Space,
    member: Member | None,
    granted_space_ids: list[int],
) -> None:
    """读权限校验，不通过则抛 ``PermissionError``。"""
    if not can_read(space, member, granted_space_ids):
        raise PermissionError("该文档库需要访问密码")


def require_writable(space: Space, member: Member | None) -> None:
    """写权限校验。

    per_doc 只有两种身份：登录用户可读写全部文档库；游客一律只读。
    """
    if member is None:
        raise PermissionError("请先登录后再操作文档库")


def _require_owner(space: Space, operator: Member) -> None:
    """文档库创建者校验，不通过则抛 ``PermissionError``。"""
    if space.member_id != operator.member_id:
        raise PermissionError("只能操作自己创建的文档库")


def _resolve_identify(db: Session, payload: SpaceCreate) -> str:
    """确定文档库的最终标识。

    优先使用用户填写的标识；未填时从名称推导，推导结果冲突则追加随机后缀。

    Raises:
        ConflictError: 用户填写的标识已被占用。
    """
    if payload.identify:
        if get_space_by_identify(db, payload.identify) is not None:
            raise ConflictError("该标识已被使用")
        return payload.identify

    base = suggest_identify(payload.space_name)
    candidate = base
    # 名称推导的标识可能与存量库冲突，最多尝试 10 次
    for _ in range(10):
        if get_space_by_identify(db, candidate) is None:
            return candidate
        candidate = f"{base}-{generate_identify('x').split('-')[-1]}"
    return generate_identify("space")


def _create_root_document(db: Session, space: Space, member_id: int) -> None:
    """为新建文档库创建根目录节点与初始空白文档。

    移植自 mindoc-master/models/BookModel.go 的 ``Book.Insert``：
    建库时插入一篇名为「空白文档」的根节点，作为后续文档的挂载点。
    """
    root = Document(
        document_name=ROOT_DOCUMENT_IDENTIFY,
        identify=ROOT_DOCUMENT_IDENTIFY,
        space_id=space.space_id,
        parent_id=0,
        order_sort=0,
        markdown="",
        content="",
        member_id=member_id,
        is_open=1,
    )
    db.add(root)
    db.flush()

    blank = Document(
        document_name=INITIAL_DOCUMENT_NAME,
        identify=generate_identify("doc"),
        space_id=space.space_id,
        parent_id=root.document_id,
        order_sort=0,
        markdown="",
        content="",
        member_id=member_id,
        is_open=0,
    )
    db.add(blank)
