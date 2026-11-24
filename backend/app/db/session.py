"""Engine 与 Session 工厂。

engine 全局复用（连接池由 SQLAlchemy 管理），Session 由依赖注入按请求创建。
事务边界统一在 service 层，本模块只提供提交/回滚的上下文工具。

engine 采用惰性构建：连接串在首次使用时才从配置解析，
这样测试中通过环境变量覆盖配置可以立即生效，而不必重载整个模块。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def build_engine() -> Engine:
    """按配置创建 engine。

    SQLite 需要开启外键约束（默认关闭），否则级联删除与引用完整性不生效。
    """
    url = settings.database_url
    settings.ensure_runtime_dirs()

    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(url, echo=settings.db_echo, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _record: object) -> None:
            """SQLite 连接建立时开启外键约束与 WAL 日志模式。"""
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def get_engine() -> Engine:
    """返回进程内唯一的 engine，首次调用时才构建。"""
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def reset_engine() -> None:
    """丢弃当前 engine（配置变更或测试隔离时使用）。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def _build_session_factory() -> sessionmaker[Session]:
    """按当前配置构建 Session 工厂。"""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


class _LazySessionFactory:
    """Session 工厂惰性代理。

    代理而非直接暴露 ``sessionmaker``，是为了让配置变更后无需重载模块，
    同时保留 ``SessionLocal.configure(...)`` 等标准用法。
    """

    def __init__(self) -> None:
        self._factory: sessionmaker[Session] | None = None

    def _resolve(self) -> sessionmaker[Session]:
        if self._factory is None:
            self._factory = _build_session_factory()
        return self._factory

    def __call__(self, **kwargs: object) -> Session:
        return self._resolve()(**kwargs)

    def configure(self, **kwargs: object) -> None:
        """重新绑定 Session 工厂（测试中用于指定内存库）。"""
        factory = self._resolve()
        factory.configure(**kwargs)

    def reset(self) -> None:
        """丢弃缓存的 Session 工厂，下次调用时按当前配置重建。"""
        self._factory = None


SessionLocal = _LazySessionFactory()


@contextmanager
def session_scope() -> Iterator[Session]:
    """脚本/后台任务用的 Session 上下文，自带提交与回滚。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """按模型元数据建表。

    仅供首次初始化与测试使用；生产环境的结构变更必须走 Alembic
    （见 ``backend/rules/backend.mdc`` §9）。
    """
    import app.models  # noqa: F401 - 触发模型注册，确保元数据完整

    Base.metadata.create_all(bind=get_engine())


def drop_all() -> None:
    """删除所有表（仅测试与本地重置使用）。"""
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=get_engine())
