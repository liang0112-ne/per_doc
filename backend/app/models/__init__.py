"""SQLAlchemy 表映射。

本模块只声明表结构，不写业务逻辑。
导入本包即完成全部模型的注册，供 Alembic autogenerate 与
``Base.metadata.create_all`` 收集元数据。
"""

from app.db.base import Base, table_name
from app.models.attachment import Attachment
from app.models.document import Document
from app.models.history import DocumentHistory
from app.models.log import Log
from app.models.member import Member
from app.models.option import Option
from app.models.space import Space

__all__ = [
    "Attachment",
    "Base",
    "Document",
    "DocumentHistory",
    "Log",
    "Member",
    "Option",
    "Space",
    "table_name",
]
