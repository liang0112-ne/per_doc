"""SQLAlchemy Declarative Base 与公共元数据。

所有模型必须从 ``app.db.base`` 继承 ``Base``，便于 Alembic 的
``target_metadata`` 统一收集。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 统一命名约定，便于 Alembic 生成可回滚的迁移脚本
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def table_name(name: str) -> str:
    """拼接带配置前缀的表名。

    表前缀通过 ``settings.db_prefix`` 统一控制，禁止在代码里硬编码
    ``md_`` 字面量（见 ``backend/rules/backend.mdc`` §7）。
    """
    return f"{settings.db_prefix}{name}"


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
