"""HTTP 接口层。

本层是 HTTP 边界：参数解析 → 校验 → 调 service → 组装响应。
所有路由在 ``app.api.router`` 统一汇总挂载。
"""
