"""数据访问基础设施：Declarative Base、engine、Session。

只负责连接与事务的底座，不包含任何业务查询。
"""

from app.db.base import Base
from app.db.session import (
    SessionLocal,
    build_engine,
    get_engine,
    reset_engine,
    session_scope,
)

__all__ = [
    "Base",
    "SessionLocal",
    "build_engine",
    "get_engine",
    "reset_engine",
    "session_scope",
]
