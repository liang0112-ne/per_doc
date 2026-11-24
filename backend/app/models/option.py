"""系统配置表（KV）。

对应 mindoc-master 的 ``md_options``。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, table_name


class Option(Base):
    """一条系统配置项。"""

    __tablename__ = table_name("options")

    option_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    option_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    option_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    modify_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.now()
    )
