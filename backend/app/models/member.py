"""用户表。

只保留本地账号体系，不引入角色矩阵与多认证方式。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, table_name


class Member(Base):
    """per_doc 用户。"""

    __tablename__ = table_name("members")

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    real_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # 0 启用 / 1 禁用
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_login_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_active(self) -> bool:
        """账号是否处于启用状态。"""
        return self.status == 0
