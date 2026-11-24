"""认证业务逻辑。

职责边界：
- 校验账号密码、锁定策略、存量密码升级
- 账号注册与密码修改
- 事务边界（``commit`` / ``rollback``）统一在本模块

本模块不感知 HTTP（不抛 ``HTTPException``、不 import ``Depends``），
Cookie 的写入由 ``app.core.session`` 与 api 层配合完成。

移植自 mindoc-master/controllers/AccountController.go 的登录与注册规则，
但删除了验证码、第三方登录与找回密码（见重构方案 §2.2 项目边界）。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError, ValidationError
from app.core.identity import validate_password_strength
from app.core.security import (
    hash_password,
    is_legacy_hash,
    login_limiter,
    needs_rehash,
    verify_password,
)
from app.models.member import Member

logger = logging.getLogger(__name__)


def find_member_by_account(db: Session, account: str) -> Member | None:
    """按账号查询用户；不存在返回 ``None``。"""
    return db.scalar(select(Member).where(Member.account == account))


def authenticate(db: Session, account: str, password: str) -> Member:
    """校验账号密码并返回用户。

    业务规则：
    1. 账号被锁定时直接拒绝，提示剩余锁定时间
    2. 密码错误计入失败次数，连续 5 次失败锁定 15 分钟
    3. 存量 mindoc 密码校验通过后自动升级为 Argon2id

    Args:
        db: 数据库会话。
        account: 登录名。
        password: 明文密码。

    Returns:
        校验通过的会员记录。

    Raises:
        AuthError: 账号不存在、密码错误、账号被禁用或账号被锁定。
    """
    if login_limiter.is_locked(account):
        remaining = login_limiter.remaining_seconds(account)
        raise AuthError(f"登录失败次数过多，请 {remaining} 秒后再试")

    member = find_member_by_account(db, account)
    # 账号不存在与密码错误返回同一提示，避免暴露账号是否存在
    if member is None or not verify_password(member.password, password):
        login_limiter.record_failure(account)
        raise AuthError("账号或密码错误")

    if not member.is_active:
        raise AuthError("账号已被禁用，请联系管理员")

    login_limiter.reset(account)
    _upgrade_password_hash(db, member, password)
    return member


def register_member(
    db: Session,
    account: str,
    password: str,
    password_confirm: str,
    email: str | None,
    real_name: str,
) -> Member:
    """注册新账号。

    Args:
        db: 数据库会话。
        account: 登录名。
        password: 明文密码。
        password_confirm: 确认密码。
        email: 邮箱，可为空。
        real_name: 昵称。

    Returns:
        新建的会员记录。

    Raises:
        ValidationError: 两次密码不一致或密码强度不足。
        ConflictError: 账号或邮箱已被占用。
    """
    if not settings.allow_register:
        raise ValidationError("站点当前未开放注册")

    if password != password_confirm:
        raise ValidationError("两次输入的密码不一致")

    problems = validate_password_strength(password)
    if problems:
        raise ValidationError(problems[0])

    if find_member_by_account(db, account) is not None:
        raise ConflictError("该账号已被注册")

    if email:
        existing_email = db.scalar(select(Member).where(Member.email == email))
        if existing_email is not None:
            raise ConflictError("该邮箱已被注册")

    member = Member(
        account=account,
        real_name=real_name or account,
        password=hash_password(password),
        email=email,
        status=0,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    logger.info("新账号注册成功 (member_id=%s)", member.member_id)
    return member


def change_password(
    db: Session,
    member: Member,
    old_password: str,
    new_password: str,
    new_password_confirm: str,
) -> None:
    """修改当前登录用户的密码。

    Args:
        db: 数据库会话。
        member: 当前用户。
        old_password: 原密码。
        new_password: 新密码。
        new_password_confirm: 确认新密码。

    Raises:
        AuthError: 原密码错误。
        ValidationError: 两次新密码不一致或新密码强度不足。
    """
    if not verify_password(member.password, old_password):
        raise AuthError("原密码错误")

    if new_password != new_password_confirm:
        raise ValidationError("两次输入的新密码不一致")

    problems = validate_password_strength(new_password)
    if problems:
        raise ValidationError(problems[0])

    if new_password == old_password:
        raise ValidationError("新密码不能与原密码相同")

    member.password = hash_password(new_password)
    db.commit()
    logger.info("用户 %s 修改了密码", member.account)


def touch_last_login(db: Session, member: Member) -> None:
    """更新最后登录时间。

    时间由数据库的 ``func.now()`` 产生，与表上 ``create_time`` /
    ``modify_time`` 的 server_default 完全一致；若在 Python 侧用
    ``datetime.now()`` 写入本地时间，会出现「最后登录时间早于创建时间」的倒挂。
    """
    db.execute(
        update(Member)
        .where(Member.member_id == member.member_id)
        .values(last_login_time=func.now())
    )
    db.commit()
    db.refresh(member)


def _upgrade_password_hash(db: Session, member: Member, plain_password: str) -> None:
    """存量密码或参数过期的哈希升级为 Argon2id。

    移植自重构方案 §5.3：存量用户首次登录时用旧算法校验，
    校验成功后立即改写为 Argon2id，旧哈希不再保留。

    哈希不可逆，明文只能在「刚校验通过」的那一次调用里拿到，
    因此这里由调用方透传明文，而不是从库里反查。
    """
    if not is_legacy_hash(member.password) and not needs_rehash(member.password):
        return

    member.password = hash_password(plain_password)
    db.commit()
    logger.info("用户 %s 的密码哈希已升级为 Argon2id", member.account)
