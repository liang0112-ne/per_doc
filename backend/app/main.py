"""应用入口：创建 FastAPI 实例、注册全局异常处理器与业务路由。

业务路由在 ``app.api.router`` 统一挂载；此处保留健康检查与插件清单等
系统级接口，保证 B1 阶段即可启动并验证基础设施。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.plugins import register_all, registry

logger = logging.getLogger(__name__)

setup_logging()

# 插件注册是唯一入口，启动时统一执行（规则 §13.3）
register_all()

app = FastAPI(
    title=settings.site_name,
    version="0.1.0",
    description="轻量级文档管理与录入系统",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务路由统一挂载（规则 §5：分组用 APIRouter，统一 include）
app.include_router(api_router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """把业务异常转换为统一响应体，不暴露堆栈与内部细节。"""
    logger.info("业务异常 %s %s -> %s", request.method, request.url.path, exc.code)
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """把 Pydantic 校验错误转换为统一响应体。

    ``exc.errors()`` 的 ``ctx`` 中可能带有原始异常对象（如自定义校验器抛出的
    ``ValueError``），这些对象无法 JSON 序列化，必须转成字符串后再返回，
    否则序列化阶段会抛出二次异常。
    """
    return JSONResponse(
        status_code=422,
        content={"code": 4000, "message": "参数校验失败", "detail": _safe_errors(exc)},
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """屏蔽数据库原始异常，仅记录日志并返回通用提示。"""
    logger.exception("数据库异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 5000, "message": "数据操作失败", "detail": None},
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """把框架级 HTTP 异常也收敛到统一响应结构。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code * 10, "message": str(exc.detail), "detail": None},
    )


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """健康检查，供 Docker 与负载均衡探活使用。"""
    return {"status": "ok", "app": settings.site_name}


@app.get("/api/plugins", tags=["system"])
def list_plugins() -> dict[str, list[str]]:
    """返回各插槽已注册的插件清单。

    用于自检与后台展示，核心业务不依赖此接口。
    """
    return registry.registry_snapshot()


def _safe_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """把校验错误转换成可 JSON 序列化的结构。

    Pydantic 的错误上下文里可能带有原始异常对象，直接返回会触发序列化异常。
    """
    safe: list[dict[str, object]] = []
    for error in exc.errors():
        item: dict[str, object] = {
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        context = error.get("ctx")
        if isinstance(context, dict):
            item["ctx"] = {key: str(value) for key, value in context.items()}
        safe.append(item)
    return safe
