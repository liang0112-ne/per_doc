"""Markdown 渲染器插槽。

用途：Markdown → HTML。

实现约定：
- 必须实现 ``base.MarkdownRenderer``：``meta`` + ``render()``
- 渲染失败抛 ``app.core.exceptions.RenderError``
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
