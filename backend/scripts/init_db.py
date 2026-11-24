"""数据库初始化脚本。

用法：

```bash
python -m scripts.init_db --admin admin --password 'your-password'
```

脚本职责：
1. 执行 Alembic 迁移到 head（结构由迁移脚本统一管理，不使用 create_all）
2. 创建初始管理员账号（已存在则跳过）
3. 写入默认系统配置项
"""

from __future__ import annotations

import argparse
import logging
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Member, Option

logger = logging.getLogger("scripts.init_db")

# 默认系统配置项
DEFAULT_OPTIONS: dict[str, str] = {
    "site_name": settings.site_name,
    "default_cover": settings.default_cover,
    "allow_register": "true" if settings.allow_register else "false",
    "max_upload_size": str(settings.max_upload_size),
    "upload_extensions": ",".join(settings.upload_extensions),
    "markdown_theme": "theme__light",
}


def run_migrations() -> None:
    """把数据库升级到最新的迁移版本。"""
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "app" / "migrations"))
    command.upgrade(config, "head")
    logger.info("数据库结构已升级到 head")


def create_admin(db: Session, account: str, password: str) -> Member:
    """创建管理员账号；账号已存在时直接返回既有记录。"""
    existing = db.scalar(select(Member).where(Member.account == account))
    if existing is not None:
        logger.info("管理员账号 %s 已存在，跳过创建", account)
        return existing

    member = Member(
        account=account,
        real_name="管理员",
        password=hash_password(password),
        email=None,
        status=0,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    logger.info("管理员账号 %s 创建成功 (member_id=%s)", account, member.member_id)
    return member


def init_options(db: Session) -> int:
    """写入默认配置项，返回新增条数。"""
    created = 0
    for key, value in DEFAULT_OPTIONS.items():
        if db.scalar(select(Option).where(Option.option_key == key)) is not None:
            continue
        db.add(Option(option_key=key, option_value=value))
        created += 1
    if created:
        db.commit()
    logger.info("默认配置项写入完成，新增 %s 条", created)
    return created


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="per_doc 数据库初始化")
    parser.add_argument("--admin", default="admin", help="管理员登录名")
    parser.add_argument("--password", default=None, help="管理员密码，缺省时随机生成并打印")
    parser.add_argument("--skip-migrate", action="store_true", help="跳过 Alembic 迁移")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """脚本入口。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    args = parse_args(argv)

    password = args.password
    generated = False
    if not password:
        import secrets

        password = secrets.token_urlsafe(12)
        generated = True

    if not args.skip_migrate:
        run_migrations()

    with SessionLocal() as db:
        create_admin(db, args.admin, password)
        init_options(db)

    if generated:
        logger.warning("随机生成的初始密码：%s（请立即登录并修改）", password)
    logger.info("初始化完成，数据库：%s", settings.database_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
