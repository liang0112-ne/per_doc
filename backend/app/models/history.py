"""文档历史版本表。

记录每次内容变更的快照，供版本浏览、恢复与对比使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, table_name

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentHistory(Base):
    """文档的一个历史版本快照。"""

    __tablename__ = table_name("document_history")

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{table_name('documents')}.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 操作类型：create / modify / restore 等
    action: Mapped[str] = mapped_column(
        String(255), nullable=False, default="modify", server_default="modify"
    )
    action_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    member_id: Mapped[int] = mapped_column(Integer, nullable=False)
    modify_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    modify_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    document: Mapped[Document] = relationship(back_populates="histories")
