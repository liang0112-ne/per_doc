"""密码哈希、会话签名与 CSRF 工具。

密码一律使用 Argon2id；兼容 mindoc-master 的旧 MD5 hash，校验成功后
在调用方（auth_service）触发升级。
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.legacy_password import is_mindoc_hash, verify_mindoc_password

_hasher = PasswordHasher()

# 登录失败锁定参数，移植自重构方案 §5.3 的密码策略
MAX_LOGIN_ATTEMPTS = 5
LOCK_DURATION_SECONDS = 900


class LoginAttemptLimiter:
    """按账号统计登录失败次数，超过阈值后在窗口期内锁定。

    使用内存实现即可满足单机场景；多实例部署时应替换为 Redis 实现，
    保持相同的 ``is_locked`` / ``record_failure`` / ``reset`` 接口。
    """

    def __init__(
        self,
        max_attempts: int = MAX_LOGIN_ATTEMPTS,
        lock_seconds: int = LOCK_DURATION_SECONDS,
    ) -> None:
        self._max_attempts = max_attempts
        self._lock_seconds = lock_seconds
        self._records: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def is_locked(self, account: str) -> bool:
        """账号当前是否处于锁定状态。"""
        with self._lock:
            failures = self._records.get(account)
            if not failures:
                return False
            if not self._prune(account, failures):
                self._records.pop(account, None)
                return False
            return len(failures) >= self._max_attempts

    def record_failure(self, account: str) -> None:
        """记录一次登录失败。"""
        with self._lock:
            failures = self._records.get(account)
            if failures is None:
                failures = []
                self._records[account] = failures
            else:
                self._prune(account, failures)
            failures.append(time.monotonic())

    def reset(self, account: str) -> None:
        """登录成功后清空该账号的失败记录。"""
        with self._lock:
            self._records.pop(account, None)

    def remaining_seconds(self, account: str) -> int:
        """返回剩余锁定秒数，未锁定时为 0。"""
        with self._lock:
            failures = self._records.get(account)
            if not failures or len(failures) < self._max_attempts:
                return 0
            return max(0, int(self._lock_seconds - (time.monotonic() - failures[0])))

    def _prune(self, account: str, failures: list[float]) -> bool:
        """剔除过期失败记录；返回记录是否仍然有效。

        注意：这里**不能**把空列表从 ``_records`` 中移除——``record_failure``
        可能正持有该列表的引用，移除后新记录会挂在一个已脱钩的列表上，
        失败计数将永远停在 1。字典项的清理交由调用方在确认列表失效时处理。
        """
        now = time.monotonic()
        while failures and now - failures[0] > self._lock_seconds:
            failures.pop(0)
        return bool(failures)


login_limiter = LoginAttemptLimiter()


def hash_password(plain: str) -> str:
    """生成 Argon2id 密码哈希。"""
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    """校验密码。

    兼容 mindoc-master 的存量密码格式：校验成功时返回 True，
    调用方（auth_service）负责在下次登录时升级为 Argon2id。
    """
    if not stored_hash:
        return False
    if stored_hash.startswith("$argon2"):
        try:
            _hasher.verify(stored_hash, plain)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return True
    if is_mindoc_hash(stored_hash):
        return verify_mindoc_password(stored_hash, plain)
    return False


def is_legacy_hash(stored_hash: str) -> bool:
    """判断是否为需要升级的存量密码格式（非 Argon2id）。"""
    return bool(stored_hash) and not stored_hash.startswith("$argon2")


def needs_rehash(stored_hash: str) -> bool:
    """判断哈希是否需要用当前参数重新生成。"""
    if not stored_hash.startswith("$argon2"):
        return True
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def new_session_token() -> str:
    """生成随机会话标识。"""
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    """生成 CSRF Token（写入 Cookie 后要求请求头回传比对）。"""
    return secrets.token_urlsafe(32)


def sign_session(payload: dict[str, object], salt: str = "per_doc.session") -> str:
    """使用 itsdangerous 对会话负载签名。

    Args:
        payload: 待签名的负载。
        salt: 签名盐值。不同用途（会话 / 访问凭据）必须用不同 salt，
            否则同一份密钥下的两类令牌可以互相冒用。
    """
    from itsdangerous import URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(settings.secret_key, salt=salt)
    return serializer.dumps(payload)


def unsign_session(
    token: str,
    max_age: int | None = None,
    salt: str = "per_doc.session",
) -> dict[str, object] | None:
    """校验并还原会话负载，失败（过期或被篡改）返回 None。"""
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(settings.secret_key, salt=salt)
    try:
        data = serializer.loads(token, max_age=max_age or settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None
