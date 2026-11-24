"""存量密码兼容校验自测。

验证存量哈希格式的自洽性：
构造 → 校验通过 → 错误密码被拒绝 → 非法格式被拒绝。
"""

from __future__ import annotations

from app.core.legacy_password import (
    build_legacy_password,
    is_legacy_hash_format,
    verify_legacy_password,
)
from app.core.security import hash_password, is_legacy_hash, needs_rehash, verify_password


def test_build_and_verify_roundtrip() -> None:
    stored = build_legacy_password("secret123")
    assert verify_legacy_password(stored, "secret123") is True
    assert verify_legacy_password(stored, "wrong") is False


def test_format_detection() -> None:
    stored = build_legacy_password("secret123")
    assert is_legacy_hash_format(stored) is True
    assert is_legacy_hash_format("not-a-hash") is False
    assert is_legacy_hash_format(hash_password("x")) is False


def test_invalid_format_rejected() -> None:
    assert verify_legacy_password("a$b$c", "x") is False
    assert verify_legacy_password("a$b$notint$d", "x") is False
    assert verify_legacy_password("", "x") is False


def test_verify_password_dispatches_to_legacy() -> None:
    stored = build_legacy_password("secret123")
    assert verify_password(stored, "secret123") is True
    assert verify_password(stored, "nope") is False


def test_argon2_takes_precedence() -> None:
    stored = hash_password("secret123")
    assert verify_password(stored, "secret123") is True
    assert is_legacy_hash(stored) is False
    assert needs_rehash(stored) is False


def test_legacy_needs_rehash() -> None:
    stored = build_legacy_password("secret123")
    assert is_legacy_hash(stored) is True
    assert needs_rehash(stored) is True
