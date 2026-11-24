"""HTTP 边界层。

每个业务域一个 router 模块，统一在此汇总挂载到应用。
本层只做参数解析、校验、调用 service、组装响应：
- 禁止写 ORM 查询
- 禁止 ``db.commit()``（事务边界在 service）
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import auth, spaces, tree

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(spaces.router)
api_router.include_router(tree.router)

__all__ = ["api_router"]
