"""附件表。

对应 mindoc-master 的 ``md_attachment``，``book_id`` 更名为 ``space_id``。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, table_name


class Attachment(Base):
    """上传的附件记录。"""

    __tablename__ = table_name("attachments")

    attachment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{table_name('spaces')}.space_id"), nullable=False, index=True
    )
    # 附件可挂在文档下，也可只属于文档库
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(f"{table_name('documents')}.document_id", ondelete="CASCADE"),
        nullable=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 相对存储路径，避免把绝对路径写入数据库
    file_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    file_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    http_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    file_ext: Mapped[str | None] = mapped_column(String(50), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # 上传人 id
    create_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
