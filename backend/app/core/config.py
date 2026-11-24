"""应用配置。

所有配置只从 ``Settings`` 读取，业务代码禁止直接访问 ``os.environ``。
新增配置项需同步三处：``Settings``、``.env.example``、总体设计文档。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# 项目根目录（backend/），用于把相对路径锚定到工程目录下
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """per_doc 全局配置，环境变量前缀 ``PER_DOC_``。"""

    model_config = SettingsConfigDict(
        env_prefix="PER_DOC_",
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 站点 ----------
    site_name: str = "per_doc"
    host: str = "0.0.0.0"  # noqa: S104 - 由部署方决定监听地址
    port: int = 8181
    debug: bool = False
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    default_cover: str = "/static/images/default-cover.svg"

    # ---------- 数据库 ----------
    db_adapter: str = "sqlite"
    db_path: str = "./data/per_doc.db"
    db_url: str | None = None
    db_prefix: str = "md_"
    db_echo: bool = False

    # ---------- 会话与安全 ----------
    secret_key: str = "change-me-to-a-long-random-string"  # noqa: S105 - 占位默认值，生产必须覆盖
    session_backend: str = "cookie"
    session_max_age: int = 604800
    session_cookie_name: str = "per_doc_session"
    csrf_header_name: str = "X-CSRF-Token"
    session_cookie_secure: bool = False
    # 私有文档库的访问凭据 Cookie 名（游客通过访问密码后写入）
    access_cookie_name: str = "per_doc_access"
    allow_register: bool = True

    # ---------- 附件 ----------
    upload_dir: str = "./data/uploads"
    max_upload_size: int = 104857600
    upload_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["txt", "md", "pdf", "png", "jpg", "jpeg", "gif", "zip"]
    )

    # ---------- 其他 ----------
    enable_export: bool = False
    weasyprint_bin: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str | None = None

    @field_validator("cors_origins", "upload_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """允许用逗号分隔的字符串配置列表，便于 .env 直接书写。"""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("db_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        """表前缀统一以 ``_`` 结尾拼接，避免出现 ``mddocuments``。"""
        if not value:
            return ""
        return value if value.endswith("_") else f"{value}_"

    @property
    def sqlite_path(self) -> Path:
        """SQLite 数据库文件的绝对路径。"""
        path = Path(self.db_path)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def upload_path(self) -> Path:
        """附件存储目录的绝对路径。"""
        path = Path(self.upload_dir)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def database_url(self) -> str:
        """最终生效的数据库连接串。"""
        if self.db_url:
            return self.db_url
        if self.db_adapter == "sqlite":
            return f"sqlite+pysqlite:///{self.sqlite_path.as_posix()}"
        raise ValueError(f"未配置 {self.db_adapter} 的连接串，请设置 PER_DOC_DB_URL")

    def ensure_runtime_dirs(self) -> None:
        """创建运行期需要的目录（SQLite 文件所在目录、附件目录）。"""
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程内唯一的配置实例（测试中可通过 ``cache_clear`` 重置）。"""
    return Settings()


class _SettingsProxy:
    """配置惰性代理。

    直接在模块导入期读取配置会让「测试改环境变量」与「运行时改配置」都失效，
    因此统一改为属性访问时才解析，保证 ``settings.xxx`` 始终取到当前配置。
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)

    def __repr__(self) -> str:
        return repr(get_settings())

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(get_settings(), name, value)


settings = _SettingsProxy()
