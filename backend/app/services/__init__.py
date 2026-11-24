"""业务服务层。

服务层负责业务规则、事务边界与权限判定：
- 不抛 ``HTTPException``，只抛 ``app.core.exceptions`` 中的业务异常
- 不 import ``Depends``，不感知 HTTP 细节
"""
