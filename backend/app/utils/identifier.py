"""URL 短标识（identify）的生成与校验。

``identify`` 是文档库与文档在 URL 中的唯一标识，全局唯一。
规则说明：

- 文档库：``^[a-z]+[a-zA-Z0-9_\\-]*$``，人工填写的短横线风格
- 文档：``^[a-z][a-zA-Z0-9_.-]*$``

两者只差「是否允许点号」，因为存量文档的 identify 可能形如
``guide.install``，而文档库标识是人工填写的短横线风格。
"""

from __future__ import annotations

import re
import secrets
import time

# 文档库标识：小写字母开头，允许字母数字、下划线、短横线
SPACE_IDENTIFY_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9_-]*$")

# 文档标识：小写字母开头，额外允许点号
DOCUMENT_IDENTIFY_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9_.-]*$")

# 标识最大长度，与存量数据的 50 字符上限一致
IDENTIFY_MAX_LENGTH = 50

# 生成标识时保留的随机字节数，32 bit 熵足够在单库内避免碰撞
_RANDOM_BYTES = 5

_BASE36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def is_valid_space_identify(value: str) -> bool:
    """文档库标识是否符合格式要求。"""
    return (
        bool(value)
        and len(value) <= IDENTIFY_MAX_LENGTH
        and bool(SPACE_IDENTIFY_PATTERN.match(value))
    )


def is_valid_document_identify(value: str) -> bool:
    """文档标识是否符合格式要求。"""
    return (
        bool(value)
        and len(value) <= IDENTIFY_MAX_LENGTH
        and bool(DOCUMENT_IDENTIFY_PATTERN.match(value))
    )


def generate_identify(prefix: str = "doc") -> str:
    """生成一个全局唯一的标识。

    由「毫秒时间戳（base36）+ 随机串（base36）」组成：
    时间戳保证可读性与大致有序，随机串保证同一毫秒内的并发不冲突。

    Args:
        prefix: 标识前缀，只能含小写字母与短横线。

    Returns:
        形如 ``doc-lf3k9a-x7q2b`` 的标识。
    """
    safe_prefix = re.sub(r"[^a-z-]", "", prefix.lower()) or "doc"
    stamp = _to_base36(int(time.time() * 1000))
    rand = _to_base36(int.from_bytes(secrets.token_bytes(_RANDOM_BYTES), "big"))
    return f"{safe_prefix}-{stamp}-{rand}"


def suggest_identify(name: str, prefix: str = "doc") -> str:
    """从名称推导一个候选标识。

    用于「用户只填了名称」的场景：把名称转成合法的小写短横线形式。
    结果不保证唯一，调用方仍需做冲突检查。

    Args:
        name: 原始名称，可含中文与空格。
        prefix: 当名称无法转换出合法前缀时使用的兜底前缀。

    Returns:
        符合格式要求的候选标识。
    """
    normalized = name.strip().lower()
    # 非 ASCII 字符（如中文）统一丢弃，只保留 ASCII 字母数字
    ascii_only = "".join(char for char in normalized if char.isascii())
    replaced = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if not replaced:
        # 名称里没有可用字符（如纯中文），用兜底前缀 + 随机串保证唯一性
        return f"{prefix}-{secrets.token_hex(3)}"
    if not replaced[0].isalpha():
        replaced = f"{prefix}-{replaced}"
    return replaced[:IDENTIFY_MAX_LENGTH]


def _to_base36(number: int) -> str:
    """把非负整数转成 base36 字符串。"""
    if number == 0:
        return "0"
    digits: list[str] = []
    while number > 0:
        number, remainder = divmod(number, 36)
        digits.append(_BASE36_DIGITS[remainder])
    return "".join(reversed(digits))
