"""智能体工具插槽。

用途：智能体可调用的外部能力（查库、调接口等）。

实现约定：
- 必须实现 ``base.AgentTool``：``meta`` + ``name()`` + ``parameters()`` + ``execute()``
- 工具之间禁止互相 import
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
