"""认证接口。

只做「参数解析 → 校验 → 调 service → 组装响应」，
ORM 查询与事务边界都在 ``app.services.auth_service`` 中。

接口清单见重构方案 §6.2：
- ``POST /api/auth/login`` 登录
- ``POST /api/auth/logout`` 登出
- ``GET  /api/auth/me`` 当前用户信息
- ``POST /api/auth/register`` 注册
- ``PUT  /api/auth/password`` 修改密码
- ``GET  /api/auth/csrf`` 获取 CSRF Token
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import (
    current_user,
    get_db,
    issue_csrf_token,
    read_session,
    require_csrf,
    require_csrf_if_present,
)
from app.core.session import (
    CSRF_TOKEN_KEY,
    build_session_payload,
    clear_session_cookie,
    write_session_cookie,
)
from app.models.member import Member
from app.schemas.auth import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    MemberOut,
    PasswordChangeRequest,
    RegisterRequest,
)
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """登录并写入会话 Cookie。"""
    member = auth_service.authenticate(db, payload.account, payload.password)
    auth_service.touch_last_login(db, member)

    csrf_token = issue_csrf_token()
    session_payload = build_session_payload(member.member_id, csrf_token)
    write_session_cookie(response, session_payload, persistent=payload.remember)

    logger.info("用户 %s 登录成功", member.account)
    return LoginResponse(user=MemberOut.model_validate(member), csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    response: Response,
    _csrf: None = Depends(require_csrf_if_present),
) -> dict[str, bool]:
    """登出并清除会话 Cookie。

    会话已失效时也允许登出（幂等），因此此处不强制校验 CSRF。
    """
    clear_session_cookie(response)
    return {"success": True}


@router.get("/me", response_model=MemberOut)
def me(user: Member = Depends(current_user)) -> MemberOut:
    """返回当前登录用户信息。"""
    return MemberOut.model_validate(user)


@router.post("/register", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> MemberOut:
    """注册新账号。

    注册成功后不自动登录，前端需再调一次登录接口。
    """
    member = auth_service.register_member(
        db=db,
        account=payload.account,
        password=payload.password,
        password_confirm=payload.password_confirm,
        email=payload.email,
        real_name=payload.real_name,
    )
    return MemberOut.model_validate(member)


@router.put("/password", status_code=status.HTTP_200_OK)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    user: Member = Depends(current_user),
    _csrf: None = Depends(require_csrf),
) -> dict[str, bool]:
    """修改当前登录用户的密码。"""
    auth_service.change_password(
        db=db,
        member=user,
        old_password=payload.old_password,
        new_password=payload.new_password,
        new_password_confirm=payload.new_password_confirm,
    )
    return {"success": True}


@router.get("/csrf", response_model=CsrfResponse)
def csrf(
    response: Response,
    session: dict[str, object] = Depends(read_session),
) -> CsrfResponse:
    """下发 CSRF Token。

    已登录会话沿用原 Token（保证同一页面多个写请求都通过校验）；
    无会话或 Token 缺失时生成新的，并写入匿名会话 Cookie。
    """
    token = str(session.get(CSRF_TOKEN_KEY, ""))
    if not token:
        token = issue_csrf_token()
        write_session_cookie(
            response,
            build_session_payload(None, token),
            persistent=False,
        )
    return CsrfResponse(csrf_token=token, header_name=settings.csrf_header_name)
