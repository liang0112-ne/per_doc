"""统一业务异常。

service 层只抛这里的异常类型，不感知 HTTP；api 层不捕获业务异常，
统一由 ``app.main`` 注册的全局处理器转换为标准响应体。
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类。

    Attributes:
        code: 业务错误码，随响应体返回给客户端。
        message: 面向用户的中文提示。
        detail: 可选的补充信息（不包含堆栈、SQL 等内部细节）。
    """

    code = 1000
    message = "操作失败"
    http_status = 400

    def __init__(self, message: str | None = None, detail: Any = None) -> None:
        resolved = message or self.message
        super().__init__(resolved)
        self.message = resolved
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        """转换为响应体结构。"""
        return {"code": self.code, "message": self.message, "detail": self.detail}


class ValidationError(AppError):
    """入参或业务规则校验不通过。"""

    code = 4000
    message = "参数校验失败"


class AuthError(AppError):
    """未登录、登录已过期或凭证无效。"""

    code = 4010
    message = "未登录或登录已过期"
    http_status = 401


class PermissionError(AppError):  # noqa: A001 - 语义化命名，覆盖内置 PermissionError
    """已登录但无权访问目标资源。"""

    code = 4030
    message = "没有操作权限"
    http_status = 403


class NotFoundError(AppError):
    """目标资源不存在。"""

    code = 4004
    message = "资源不存在"
    http_status = 404


class ConflictError(AppError):
    """资源状态冲突，例如乐观锁版本不一致。"""

    code = 4009
    message = "资源冲突"
    http_status = 409


class StorageError(AppError):
    """文件读写或外部存储失败。"""

    code = 5001
    message = "文件操作失败"
    http_status = 500


class RenderError(AppError):
    """Markdown 渲染失败。"""

    code = 5002
    message = "内容渲染失败"
    http_status = 500


class ParserError(AppError):
    """插件解析文件失败（对应 ``plugins.base`` 的解析插槽）。"""

    code = 5003
    message = "文件解析失败"
    http_status = 400


class ExportError(AppError):
    """导出失败。"""

    code = 5004
    message = "导出失败"
    http_status = 500


class DatabaseError(AppError):
    """数据库操作失败，屏蔽底层 SQLAlchemy 原始异常。"""

    code = 5000
    message = "数据操作失败"
    http_status = 500
