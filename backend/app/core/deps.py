"""依赖注入。

本模块是 FastAPI 与业务层之间唯一的装配点：
- 数据库 Session 由 ``get_db`` 提供
- 会话身份由 ``read_session`` 解析 Cookie
- 写操作由 ``require_csrf`` 校验 CSRF Token
- 登录用户由 ``current_user`` / ``current_user_optional`` 提供

服务层不感知 FastAPI，依赖只在本模块与 ``app.api`` 中出现。
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError, PermissionError
from app.core.security import new_csrf_token, unsign_session
from app.core.session import CSRF_TOKEN_KEY
from app.db.session import SessionLocal
from app.models.member import Member

__all__ = [
    "get_db",
    "read_session",
    "read_csrf_token",
    "verify_csrf",
    "issue_csrf_token",
    "require_csrf",
    "require_csrf_if_present",
    "current_user",
    "current_user_optional",
]


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供一个请求级 Session。

    异常时回滚，正常结束时提交；service 层若已自行提交，这里是无害的空提交。
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def read_session(request: Request) -> dict[str, object]:
    """解析会话 Cookie，返回会话负载；无有效会话时返回空字典。"""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return {}
    payload = unsign_session(token)
    return payload or {}


def read_csrf_token(request: Request) -> str:
    """读取请求头中的 CSRF Token。"""
    return request.headers.get(settings.csrf_header_name, "")


def issue_csrf_token() -> str:
    """生成一个新的 CSRF Token。"""
    return new_csrf_token()


def verify_csrf(request: Request, session: dict[str, object]) -> None:
    """校验写操作的 CSRF Token。

    Args:
        request: 当前请求，用于读取请求头中的 CSRF Token。
        session: 已解析的会话负载，会话内保存期望的 CSRF Token。

    Raises:
        PermissionError: Token 缺失或不匹配。
    """
    expected = str(session.get("csrf_token", ""))
    actual = read_csrf_token(request)
    if not expected or not actual or actual != expected:
        raise PermissionError("CSRF 校验失败，请刷新页面后重试")


def require_csrf(
    request: Request,
    session: dict[str, object] = Depends(read_session),
) -> None:
    """写操作依赖：校验请求头中的 CSRF Token。

    Token 由 ``GET /api/auth/csrf`` 下发并存入会话负载，
    前端在每次写请求的 ``X-CSRF-Token`` 头中原样回传。
    """
    verify_csrf(request, session)


def require_csrf_if_present(
    request: Request,
    session: dict[str, object] = Depends(read_session),
) -> None:
    """会话存在时才校验 CSRF Token。

    用于登出这类「即便会话已失效也应放行」的写操作：
    没有会话说明本就没有可被 CSRF 利用的登录态。
    """
    if not session.get(CSRF_TOKEN_KEY):
        return
    verify_csrf(request, session)


def current_user(
    db: Session = Depends(get_db),
    session: dict[str, object] = Depends(read_session),
) -> Member:
    """当前登录用户；未登录或账号不可用时抛 ``AuthError``。

    Raises:
        AuthError: 会话无效、用户不存在或账号被禁用。
    """
    member = _resolve_member(db, session)
    if member is None:
        raise AuthError()
    if not member.is_active:
        raise AuthError("账号已被禁用，请联系管理员")
    return member


def current_user_optional(
    db: Session = Depends(get_db),
    session: dict[str, object] = Depends(read_session),
) -> Member | None:
    """当前登录用户；未登录返回 ``None``（供游客可访问的接口使用）。"""
    return _resolve_member(db, session)


def _resolve_member(db: Session, session: dict[str, object]) -> Member | None:
    """按会话负载中的 member_id 查用户。"""
    member_id = session.get("member_id")
    if member_id is None:
        return None
    if not isinstance(member_id, int | str):
        return None
    try:
        resolved_id = int(member_id)
    except (TypeError, ValueError):
        return None
    return db.get(Member, resolved_id)
