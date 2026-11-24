"""文件解析器插槽。

用途：PDF / Word / Excel / 图片 OCR → Markdown。

实现约定：
- 单文件 ≤ 400 行，超了按解析器拆分
- 必须实现 ``base.DocumentParser``：``meta`` + ``supported_extensions()`` + ``parse()``
- 解析失败抛 ``app.core.exceptions.ParserError``，不裸抛 Exception
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
