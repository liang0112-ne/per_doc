"""会话 Cookie 的签发与清除。

会话负载本身由 ``app.core.security`` 的 itsdangerous 签名实现，
本模块只负责「把负载写进 Cookie / 把 Cookie 清掉」这类 HTTP 语义，
与认证业务规则无关，故与 ``auth_service`` 分开。

会话负载格式::

    {"member_id": int | None, "csrf_token": str, "login_at": int}
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import Response

from app.core.config import settings
from app.core.security import sign_session

# 会话负载中的固定键名，避免各处硬编码字符串
MEMBER_ID_KEY = "member_id"
CSRF_TOKEN_KEY = "csrf_token"  # noqa: S105 - 这是会话负载的键名，不是密码
LOGIN_AT_KEY = "login_at"


def build_session_payload(member_id: int | None, csrf_token: str) -> dict[str, Any]:
    """构造会话负载。

    Args:
        member_id: 登录用户主键；``None`` 表示仅携带 CSRF Token 的匿名会话。
        csrf_token: 当前会话的 CSRF Token。

    Returns:
        可被 itsdangerous 签名的负载字典。
    """
    return {
        MEMBER_ID_KEY: member_id,
        CSRF_TOKEN_KEY: csrf_token,
        LOGIN_AT_KEY: int(time.time()),
    }


def write_session_cookie(response: Response, payload: dict[str, Any], persistent: bool) -> None:
    """把会话负载签入 Cookie 写入响应。

    Cookie 固定使用 HttpOnly + SameSite=Lax，避免脚本读取与跨站携带。

    Args:
        response: 目标响应对象。
        payload: 会话负载。
        persistent: 为 True 时写入持久化 Cookie（关闭浏览器仍有效），
            为 False 时只写会话 Cookie（浏览器关闭即失效）。
    """
    token = sign_session(payload)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age if persistent else None,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """清除会话 Cookie（登出时调用）。"""
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def build_access_payload(space_ids: list[int]) -> dict[str, Any]:
    """构造私有文档库的访问凭据负载。

    负载记录「游客已通过访问密码校验的文档库 id 列表」，
    整体签名进单个 Cookie，避免为每个文档库各发一个 Cookie。
    """
    return {"spaces": sorted(set(space_ids)), "issued_at": int(time.time())}


def sign_access(payload: dict[str, Any]) -> str:
    """为访问凭据负载签名（使用独立 salt，避免与会话令牌混淆）。"""
    return sign_session(payload, salt="per_doc.access")


def unsign_access(token: str, max_age: int | None = None) -> dict[str, Any] | None:
    """校验并还原访问凭据负载；失败返回 ``None``。"""
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(settings.secret_key, salt="per_doc.access")
    try:
        data = serializer.loads(token, max_age=max_age or settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None


def write_access_cookie(response: Response, space_ids: list[int]) -> None:
    """把访问凭据写入 Cookie。"""
    token = sign_access(build_access_payload(space_ids))
    response.set_cookie(
        key=settings.access_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def clear_access_cookie(response: Response) -> None:
    """清除访问凭据 Cookie。"""
    response.delete_cookie(
        key=settings.access_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def read_granted_space_ids(token: str | None) -> list[int]:
    """从访问凭据 Cookie 中解析已授权的文档库 id 列表。"""
    if not token:
        return []
    payload = unsign_access(token)
    if not payload:
        return []
    spaces = payload.get("spaces")
    if not isinstance(spaces, list):
        return []
    result: list[int] = []
    for item in spaces:
        if isinstance(item, int):
            result.append(item)
    return result
