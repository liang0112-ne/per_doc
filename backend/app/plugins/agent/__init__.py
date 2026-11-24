"""文档智能体插槽。

用途：基于文档的检索增强问答。

实现约定：
- 必须实现 ``base.DocumentAgent``：``meta`` + ``chat()``
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
