"""文档表。

除 ``book_id`` 更名为 ``space_id`` 外，其余列名保持 snake_case 风格，
便于存量数据直接导入。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, table_name

if TYPE_CHECKING:
    from app.models.history import DocumentHistory
    from app.models.space import Space


class Document(Base):
    """文档节点，同时承载目录与正文两种角色。"""

    __tablename__ = table_name("documents")
    __table_args__ = (UniqueConstraint("space_id", "identify", name="uq_document_space_identify"),)

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    identify: Mapped[str] = mapped_column(String(100), nullable=False)
    space_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{table_name('spaces')}.space_id"), nullable=False, index=True
    )
    # 父级文档 id，0 表示根节点
    parent_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", index=True
    )
    # 同级排序，小到大
    order_sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 渲染后的 HTML
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_theme: Mapped[str] = mapped_column(
        String(50), nullable=False, default="theme__light", server_default="theme__light"
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    member_id: Mapped[int] = mapped_column(Integer, nullable=False)
    modify_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # 最后修改人 id
    modify_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # 版本号，乐观锁依据
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1, server_default="1")
    # 0 收起 / 1 展开 / 2 空目录
    is_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    space: Mapped[Space] = relationship(back_populates="documents")
    histories: Mapped[list[DocumentHistory]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
