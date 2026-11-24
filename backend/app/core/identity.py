"""账号、邮箱与密码的格式规则。

这里只放「与存储、传输无关」的纯格式校验，供 Pydantic schema 与
service 层共用，避免同一套正则散落在多处。

账号与邮箱的正则移植自 mindoc-master/conf/enumerate.go 的
``RegexpAccount`` / ``RegexpEmail``；密码强度规则来自重构方案 §5.3。
"""

from __future__ import annotations

import re

# 账号规则：字母或数字开头，允许字母、数字、点、横线，长度 3~51
ACCOUNT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\.-]{2,50}$")

# 邮箱规则：移植自 mindoc-master/conf/enumerate.go 的 RegexpEmail
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

# 密码长度下限（重构方案 §5.3）
PASSWORD_MIN_LENGTH = 8
# 密码长度上限，防止超长输入拖慢 Argon2 计算
PASSWORD_MAX_LENGTH = 64

# 账号长度上限，与 ACCOUNT_PATTERN 的语义保持一致
ACCOUNT_MAX_LENGTH = 51


def is_valid_account(account: str) -> bool:
    """账号是否符合格式要求。"""
    return bool(account) and bool(ACCOUNT_PATTERN.match(account))


def is_valid_email(email: str) -> bool:
    """邮箱是否符合格式要求。"""
    return bool(email) and bool(EMAIL_PATTERN.match(email))


def validate_password_strength(password: str) -> list[str]:
    """检查密码强度，返回不满足的规则描述列表。

    规则：长度在 8~64 之间，且至少包含一个字母与一个数字。

    Returns:
        违规描述列表；空列表表示密码强度合格。
    """
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"密码长度不能少于 {PASSWORD_MIN_LENGTH} 位")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"密码长度不能超过 {PASSWORD_MAX_LENGTH} 位")
    if not any(char.isalpha() for char in password):
        problems.append("密码必须包含字母")
    if not any(char.isdigit() for char in password):
        problems.append("密码必须包含数字")
    return problems
