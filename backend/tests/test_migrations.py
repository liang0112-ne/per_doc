"""B2 迁移专项自测：真实执行 Alembic upgrade / downgrade。

使用临时目录的独立 SQLite 文件，绝不触碰开发数据。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import BASE_DIR


@pytest.fixture()
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """指向临时数据库的 Alembic 配置。"""
    db_path = tmp_path / "migrate_test.db"
    monkeypatch.setenv("PER_DOC_DB_PATH", str(db_path))
    monkeypatch.setenv("PER_DOC_DB_URL", "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "app" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path.as_posix()}")
    yield config
    get_settings.cache_clear()


def _table_names(config: Config) -> set[str]:
    """读取目标库的表清单。"""
    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_head_creates_all_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    tables = _table_names(alembic_config)
    expected = {
        "md_members",
        "md_spaces",
        "md_documents",
        "md_document_history",
        "md_attachments",
        "md_options",
        "md_logs",
    }
    assert expected.issubset(tables)
    assert "alembic_version" in tables


def test_upgrade_is_idempotent(alembic_config: Config) -> None:
    """重复执行 upgrade 不应报错。"""
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    assert "md_documents" in _table_names(alembic_config)


def test_downgrade_base_removes_all_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    tables = _table_names(alembic_config)
    assert "md_documents" not in tables
    assert "md_members" not in tables
    assert tables == {"alembic_version"}


def test_upgrade_downgrade_cycle(alembic_config: Config) -> None:
    """升级 → 回滚 → 再升级，结构应可重复构建。"""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert "md_spaces" in _table_names(alembic_config)


def test_migrated_schema_accepts_raw_insert(alembic_config: Config) -> None:
    """迁移产出的结构可直接承载裸 SQL 插入（server_default 生效）。"""
    command.upgrade(alembic_config, "head")
    url = alembic_config.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO md_spaces (space_name, identify, member_id) "
                    "VALUES ('迁移验证', 'migrated', 1)"
                )
            )
            row = conn.execute(
                text("SELECT editor, theme, auto_save FROM md_spaces WHERE identify='migrated'")
            ).one()
        assert row.editor == "markdown"
        assert row.theme == "default"
        assert row.auto_save == 1
    finally:
        engine.dispose()


def test_version_table_records_head(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    url = alembic_config.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0001"
    finally:
        engine.dispose()
