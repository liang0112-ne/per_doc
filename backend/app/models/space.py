"""文档库（空间）表。

对应 mindoc-master 的 ``md_books``。原表的多级项目空间（``md_itemsets``）
降级为 ``group_name`` 字段，评论、分享、打印等特性已裁剪。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, table_name

if TYPE_CHECKING:
    from app.models.document import Document


class Space(Base):
    """文档库，per_doc 中的顶层内容容器。"""

    __tablename__ = table_name("spaces")

    space_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # URL 短标识，全局唯一
    identify: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # 原 md_itemsets 降级后的分组名
    group_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="默认分组", server_default="默认分组"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # 默认编辑器：markdown / html
    editor: Mapped[str] = mapped_column(
        String(50), nullable=False, default="markdown", server_default="markdown"
    )
    theme: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", server_default="default"
    )
    # 0 公开 / 1 需访问密码
    is_private: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # 访问密码哈希（Argon2id）
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 0 关闭 / 1 开启
    auto_save: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # 每个文档保留的历史版本数，0 表示不限制
    history_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    member_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    modify_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.now()
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="space",
        cascade="all, delete-orphan",
    )

    @property
    def is_public(self) -> bool:
        """文档库是否公开可读。"""
        return self.is_private == 0
