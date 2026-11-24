"""认证模块单元测试（B4）。

覆盖：
- 身份格式校验（账号 / 邮箱 / 密码强度）
- 登录成功、密码错误、账号禁用、锁定策略
- 存量 mindoc 密码首登升级为 Argon2id
- 注册（成功 / 重复账号 / 密码不一致 / 强度不足 / 注册关闭）
- 修改密码（原密码错误 / 两次不一致 / 强度不足 / 与原密码相同）
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ConflictError, ValidationError
from app.core.identity import (
    is_valid_account,
    is_valid_email,
    validate_password_strength,
)
from app.core.legacy_password import build_mindoc_password
from app.core.security import hash_password, is_legacy_hash, login_limiter
from app.models.member import Member
from app.services import auth_service


@pytest.fixture(autouse=True)
def clear_login_limiter() -> Generator[None, None, None]:
    """每个用例前后清空登录失败记录，避免用例间互相影响。"""
    login_limiter.reset("admin")
    login_limiter.reset("ghost")
    yield
    login_limiter.reset("admin")
    login_limiter.reset("ghost")


def make_member(
    session: Session,
    account: str = "admin",
    password: str = "admin123",  # noqa: S107 - 测试夹具的默认密码
    status: int = 0,
    email: str | None = None,
) -> Member:
    """构造一条会员记录。"""
    member = Member(
        account=account,
        real_name=account,
        password=hash_password(password),
        email=email,
        status=status,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


class TestIdentityRules:
    """账号 / 邮箱 / 密码格式规则。"""

    @pytest.mark.parametrize(
        "account",
        ["admin", "user01", "a.b-c", "x" * 51],
    )
    def test_valid_account(self, account: str) -> None:
        assert is_valid_account(account) is True

    @pytest.mark.parametrize(
        "account",
        ["", "ab", "-abc", "a b", "a" * 52, "中文账号"],
    )
    def test_invalid_account(self, account: str) -> None:
        assert is_valid_account(account) is False

    @pytest.mark.parametrize(
        "email",
        ["a@b.com", "first.last@sub.domain.org", "user+tag@example.cn"],
    )
    def test_valid_email(self, email: str) -> None:
        assert is_valid_email(email) is True

    @pytest.mark.parametrize(
        "email",
        # 注意：mindoc 原正则不强制域名带点，"a@b" 合法，此处保持一致
        ["", "a@@b.com", "@b.com", "a b@c.com", "a@b.c@d"],
    )
    def test_invalid_email(self, email: str) -> None:
        assert is_valid_email(email) is False

    def test_password_strength_ok(self) -> None:
        assert validate_password_strength("admin123") == []

    def test_password_too_short(self) -> None:
        problems = validate_password_strength("a1")
        assert any("长度" in p for p in problems)

    def test_password_too_long(self) -> None:
        problems = validate_password_strength("a1" * 40)
        assert any("长度" in p for p in problems)

    def test_password_without_digit(self) -> None:
        problems = validate_password_strength("abcdefgh")
        assert any("数字" in p for p in problems)

    def test_password_without_alpha(self) -> None:
        problems = validate_password_strength("12345678")
        assert any("字母" in p for p in problems)


class TestAuthenticate:
    """登录校验。"""

    def test_login_success(self, session: Session) -> None:
        make_member(session)
        member = auth_service.authenticate(session, "admin", "admin123")
        assert member.account == "admin"

    def test_login_with_wrong_password(self, session: Session) -> None:
        make_member(session)
        with pytest.raises(AuthError) as exc:
            auth_service.authenticate(session, "admin", "wrong-pass")
        assert "账号或密码错误" in str(exc.value)

    def test_login_with_unknown_account(self, session: Session) -> None:
        """账号不存在与密码错误返回同一提示，避免暴露账号是否存在。"""
        with pytest.raises(AuthError) as exc:
            auth_service.authenticate(session, "ghost", "whatever")
        assert "账号或密码错误" in str(exc.value)

    def test_login_with_disabled_account(self, session: Session) -> None:
        make_member(session, status=1)
        with pytest.raises(AuthError) as exc:
            auth_service.authenticate(session, "admin", "admin123")
        assert "禁用" in str(exc.value)

    def test_lock_after_five_failures(self, session: Session) -> None:
        make_member(session)
        for _ in range(5):
            with pytest.raises(AuthError):
                auth_service.authenticate(session, "admin", "bad")
        # 第六次即使密码正确也应被锁定拦截
        with pytest.raises(AuthError) as exc:
            auth_service.authenticate(session, "admin", "admin123")
        assert "登录失败次数过多" in str(exc.value)

    def test_successful_login_resets_failures(self, session: Session) -> None:
        make_member(session)
        for _ in range(3):
            with pytest.raises(AuthError):
                auth_service.authenticate(session, "admin", "bad")
        auth_service.authenticate(session, "admin", "admin123")
        # 计数已清空，再错 4 次不应触发锁定
        for _ in range(4):
            with pytest.raises(AuthError):
                auth_service.authenticate(session, "admin", "bad")
        assert login_limiter.is_locked("admin") is False

    def test_legacy_password_upgraded_on_login(self, session: Session) -> None:
        """存量 mindoc 密码首登后应改写为 Argon2id。"""
        legacy = build_mindoc_password("legacy123")
        member = Member(
            account="legacy",
            real_name="legacy",
            password=legacy,
            status=0,
        )
        session.add(member)
        session.commit()
        session.refresh(member)
        assert is_legacy_hash(member.password) is True

        auth_service.authenticate(session, "legacy", "legacy123")
        session.refresh(member)
        assert is_legacy_hash(member.password) is False
        assert member.password.startswith("$argon2")

    def test_legacy_password_wrong_keeps_hash(self, session: Session) -> None:
        """存量密码校验失败时不改写哈希。"""
        legacy = build_mindoc_password("legacy123")
        member = Member(account="legacy2", real_name="legacy2", password=legacy, status=0)
        session.add(member)
        session.commit()
        session.refresh(member)

        with pytest.raises(AuthError):
            auth_service.authenticate(session, "legacy2", "wrong")
        session.refresh(member)
        assert member.password == legacy


class TestRegister:
    """注册。"""

    def test_register_success(self, session: Session) -> None:
        member = auth_service.register_member(
            db=session,
            account="newbie",
            password="newbie123",
            password_confirm="newbie123",
            email="newbie@example.com",
            real_name="新用户",
        )
        assert member.member_id > 0
        assert member.password.startswith("$argon2")
        assert member.status == 0

    def test_register_duplicated_account(self, session: Session) -> None:
        make_member(session, account="admin")
        with pytest.raises(ConflictError):
            auth_service.register_member(
                db=session,
                account="admin",
                password="admin123",
                password_confirm="admin123",
                email=None,
                real_name="",
            )

    def test_register_duplicated_email(self, session: Session) -> None:
        make_member(session, account="a1", email="dup@example.com")
        with pytest.raises(ConflictError):
            auth_service.register_member(
                db=session,
                account="a2",
                password="admin123",
                password_confirm="admin123",
                email="dup@example.com",
                real_name="",
            )

    def test_register_password_mismatch(self, session: Session) -> None:
        with pytest.raises(ValidationError) as exc:
            auth_service.register_member(
                db=session,
                account="newbie",
                password="newbie123",
                password_confirm="newbie124",
                email=None,
                real_name="",
            )
        assert "不一致" in str(exc.value)

    def test_register_weak_password(self, session: Session) -> None:
        with pytest.raises(ValidationError):
            auth_service.register_member(
                db=session,
                account="newbie",
                password="weak",
                password_confirm="weak",
                email=None,
                real_name="",
            )

    def test_register_disabled_by_config(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "allow_register", False)
        with pytest.raises(ValidationError) as exc:
            auth_service.register_member(
                db=session,
                account="newbie",
                password="newbie123",
                password_confirm="newbie123",
                email=None,
                real_name="",
            )
        assert "未开放注册" in str(exc.value)


class TestChangePassword:
    """修改密码。"""

    def test_change_password_success(self, session: Session) -> None:
        member = make_member(session)
        auth_service.change_password(
            db=session,
            member=member,
            old_password="admin123",
            new_password="newpass123",
            new_password_confirm="newpass123",
        )
        session.refresh(member)
        assert member.password.startswith("$argon2")
        assert auth_service.authenticate(session, "admin", "newpass123") is not None

    def test_change_password_wrong_old(self, session: Session) -> None:
        member = make_member(session)
        with pytest.raises(AuthError):
            auth_service.change_password(
                db=session,
                member=member,
                old_password="wrong",
                new_password="newpass123",
                new_password_confirm="newpass123",
            )

    def test_change_password_mismatch(self, session: Session) -> None:
        member = make_member(session)
        with pytest.raises(ValidationError):
            auth_service.change_password(
                db=session,
                member=member,
                old_password="admin123",
                new_password="newpass123",
                new_password_confirm="newpass124",
            )

    def test_change_password_weak(self, session: Session) -> None:
        member = make_member(session)
        with pytest.raises(ValidationError):
            auth_service.change_password(
                db=session,
                member=member,
                old_password="admin123",
                new_password="weak",
                new_password_confirm="weak",
            )

    def test_change_password_same_as_old(self, session: Session) -> None:
        member = make_member(session)
        with pytest.raises(ValidationError) as exc:
            auth_service.change_password(
                db=session,
                member=member,
                old_password="admin123",
                new_password="admin123",
                new_password_confirm="admin123",
            )
        assert "不能与原密码相同" in str(exc.value)


class TestTouchLastLogin:
    """最后登录时间。"""

    def test_touch_last_login(self, session: Session) -> None:
        member = make_member(session)
        assert member.last_login_time is None
        auth_service.touch_last_login(session, member)
        session.refresh(member)
        assert member.last_login_time is not None
