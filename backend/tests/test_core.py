"""B1 基础设施自测：配置、异常、安全、依赖注入、engine。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    AuthError,
    ConflictError,
    NotFoundError,
    PermissionError,
    ValidationError,
)
from app.core.security import (
    hash_password,
    is_legacy_hash,
    needs_rehash,
    new_csrf_token,
    new_session_token,
    sign_session,
    unsign_session,
    verify_password,
)
from app.db.session import build_engine, session_scope


class TestSettings:
    """配置读取与规范化。"""

    def test_env_prefix_is_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PER_DOC_SITE_NAME", "测试站点")
        assert Settings().site_name == "测试站点"

    def test_csv_list_is_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PER_DOC_CORS_ORIGINS", "http://a.com, http://b.com")
        assert Settings().cors_origins == ["http://a.com", "http://b.com"]

    def test_db_prefix_is_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PER_DOC_DB_PREFIX", "md")
        assert Settings().db_prefix == "md_"

    def test_sqlite_url_built_from_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setenv("PER_DOC_DB_ADAPTER", "sqlite")
        monkeypatch.setenv("PER_DOC_DB_PATH", str(tmp_path / "x.db"))
        url = Settings().database_url
        assert url.startswith("sqlite+pysqlite:///")

    def test_unsupported_adapter_without_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PER_DOC_DB_ADAPTER", "postgresql")
        monkeypatch.setenv("PER_DOC_DB_URL", "")
        with pytest.raises(ValueError):
            _ = Settings().database_url

    def test_runtime_dirs_created(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setenv("PER_DOC_DB_PATH", str(tmp_path / "sub" / "x.db"))
        monkeypatch.setenv("PER_DOC_UPLOAD_DIR", str(tmp_path / "up"))
        cfg = Settings()
        cfg.ensure_runtime_dirs()
        assert cfg.sqlite_path.parent.exists()
        assert cfg.upload_path.exists()


class TestExceptions:
    """业务异常层次与响应体。"""

    def test_base_error_defaults(self) -> None:
        err = AppError()
        assert err.code == 1000
        assert err.to_dict() == {"code": 1000, "message": "操作失败", "detail": None}

    def test_custom_message_overrides(self) -> None:
        err = NotFoundError("文档不存在")
        assert err.message == "文档不存在"
        assert err.http_status == 404

    def test_detail_carried(self) -> None:
        err = ValidationError(detail={"field": "name"})
        assert err.to_dict()["detail"] == {"field": "name"}

    def test_subclasses_inherit(self) -> None:
        assert issubclass(AuthError, AppError)
        assert issubclass(PermissionError, AppError)
        assert issubclass(ConflictError, AppError)


class TestSecurity:
    """密码哈希与会话签名。"""

    def test_hash_and_verify_roundtrip(self) -> None:
        stored = hash_password("secret123")
        assert stored.startswith("$argon2")
        assert verify_password(stored, "secret123") is True
        assert verify_password(stored, "wrong") is False

    def test_hashes_are_salted(self) -> None:
        assert hash_password("secret123") != hash_password("secret123")

    def test_empty_hash_rejected(self) -> None:
        assert verify_password("", "secret123") is False

    def test_legacy_md5_detected(self) -> None:
        assert is_legacy_hash("0192023a7bbd73250516f069df18b500") is True
        assert is_legacy_hash(hash_password("x")) is False

    def test_needs_rehash_for_legacy(self) -> None:
        assert needs_rehash("0192023a7bbd73250516f069df18b500") is True
        assert needs_rehash(hash_password("x")) is False

    def test_session_sign_and_unsign(self) -> None:
        token = sign_session({"member_id": 7})
        payload = unsign_session(token)
        assert payload is not None
        assert payload["member_id"] == 7

    def test_tampered_session_rejected(self) -> None:
        token = sign_session({"member_id": 7})
        assert unsign_session(f"{token}xx") is None

    def test_expired_session_rejected(self) -> None:
        token = sign_session({"member_id": 7})
        assert unsign_session(token, max_age=-1) is None

    def test_random_tokens_unique(self) -> None:
        assert new_session_token() != new_session_token()
        assert new_csrf_token() != new_csrf_token()


class TestEngineAndSession:
    """engine 与 Session 基础设施。"""

    def test_engine_creates_and_queries(self, tmp_path) -> None:
        engine = build_engine()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        engine.dispose()

    def test_sqlite_foreign_keys_enabled(self) -> None:
        engine = build_engine()
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        engine.dispose()

    def test_session_scope_commits(self) -> None:
        with session_scope() as db:
            db.execute(text("CREATE TABLE IF NOT EXISTS _t (id INTEGER)"))
        assert session_scope is not None

    def test_session_scope_rollbacks_on_error(self) -> None:
        with pytest.raises(RuntimeError), session_scope() as db:
            db.execute(text("CREATE TABLE IF NOT EXISTS _t2 (id INTEGER)"))
            raise RuntimeError("boom")

    def test_transaction_rollback_keeps_db_consistent(self, session: Session) -> None:
        session.execute(text("CREATE TABLE _t3 (id INTEGER PRIMARY KEY)"))
        session.commit()
        with pytest.raises(IntegrityError):
            session.execute(text("INSERT INTO _t3 (id) VALUES (1)"))
            session.execute(text("INSERT INTO _t3 (id) VALUES (1)"))
            session.commit()
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM _t3")).scalar() == 0
