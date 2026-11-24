"""pytest 全局夹具。

测试使用独立的 SQLite 临时库，绝不触碰开发数据。
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import reset_engine


@pytest.fixture(autouse=True)
def isolated_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[object, None, None]:
    """把配置指向临时目录，并重置配置与 engine 缓存。

    该夹具为 autouse，保证任何测试都不会写到开发库。
    """
    monkeypatch.setenv("PER_DOC_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PER_DOC_DB_URL", "")
    monkeypatch.setenv("PER_DOC_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PER_DOC_SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()
    reset_engine()
    yield get_settings()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def engine() -> Generator[object, None, None]:
    """内存 SQLite engine，带外键约束。"""
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture()
def session(engine: object) -> Generator[Session, None, None]:
    """与内存 engine 绑定的 Session。"""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """FastAPI 测试客户端（仅依赖健康检查与异常处理）。"""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
