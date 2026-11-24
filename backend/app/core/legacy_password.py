"""存量密码兼容校验。

用于存量用户首次登录时校验旧密码哈希，校验成功后由调用方
升级为 Argon2id。新系统不再产生这种格式的密码。

历史密码格式为 ``salt_secret$interation$hash$salt``，其中 hash 由
SHA-512 → 倍增迭代 → SHA-256 → SHA-256/224 三段拉伸得到。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# 与历史实现保持一致的算法常量
SALT_LOCAL_SECRET = "ahfw*&TGdsfnbi*^Wt"  # noqa: S105 - 算法常量，不可变更
STRETCHING_PASSWORD = 500
SALT_SIZE = 16
DELIMITER = "$"

# 随机盐值长度区间
_SALT_SECRET_MIN_LEN = 10
_SALT_SECRET_MAX_LEN = 100


def verify_legacy_password(stored_hash: str, plain: str) -> bool:
    """按历史算法校验存量密码。

    Args:
        stored_hash: 数据库中保存的 ``salt_secret$interation$hash$salt``。
        plain: 用户输入的明文密码。

    Returns:
        校验通过返回 True，格式非法或密码不匹配返回 False。
    """
    parts = stored_hash.split(DELIMITER)
    if len(parts) != 4:
        return False
    salt_secret, interation_str, expected, salt = parts
    try:
        interation = int(interation_str)
    except ValueError:
        return False
    if interation < 0:
        return False
    computed = _hash(plain, salt_secret, salt, interation)
    return hmac.compare_digest(computed, expected)


def is_legacy_hash_format(stored_hash: str) -> bool:
    """判断是否为存量密码格式。"""
    parts = stored_hash.split(DELIMITER)
    return len(parts) == 4 and parts[0] != "" and parts[3] != ""


def _hash(plain: str, salt_secret: str, salt: str, interation: int) -> str:
    """复刻历史密码拉伸算法。"""
    pass_salt = salt_secret + plain + salt + salt_secret + plain + salt + plain + plain + salt

    hash_pass = SALT_LOCAL_SECRET
    sha512_state = hashlib.sha512()
    for _ in range(STRETCHING_PASSWORD + 1):
        sha512_state.update((pass_salt + hash_pass).encode("utf-8"))
        hash_pass = sha512_state.hexdigest()

    for _ in range(interation + 1):
        hash_pass = hash_pass + hash_pass

    sha256_state = hashlib.sha256()
    for _ in range(STRETCHING_PASSWORD + 1):
        sha256_state.update((hash_pass + salt_secret).encode("utf-8"))
        hash_pass = sha256_state.hexdigest()

    # SHA-224 为 SHA-256 的截断变体，此处用 hashlib 直接计算
    sha224_state = hashlib.sha224()
    sha224_state.update((hash_pass + SALT_LOCAL_SECRET).encode("utf-8"))
    return sha224_state.hexdigest()


def _new_salt_secret() -> str:
    """生成随机盐值（仅用于自测构造存量数据）。"""
    length = secrets.randbelow(_SALT_SECRET_MAX_LEN - _SALT_SECRET_MIN_LEN) + _SALT_SECRET_MIN_LEN
    return base64.urlsafe_b64encode(secrets.token_bytes(length)).decode("ascii")


def _new_salt() -> str:
    """生成随机盐（仅用于自测构造存量数据）。"""
    buf = secrets.token_bytes(SALT_SIZE)
    digest = hashlib.md5(buf + SALT_LOCAL_SECRET.encode("utf-8")).digest()  # noqa: S324
    return (buf + digest).hex()


def build_legacy_password(plain: str, interation: int = 3) -> str:
    """构造一条存量格式的密码记录（供迁移脚本与自测使用）。"""
    salt_secret = _new_salt_secret()
    salt = _new_salt()
    hashed = _hash(plain, salt_secret, salt, interation)
    return DELIMITER.join([salt_secret, str(interation), hashed, salt])
