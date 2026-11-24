"""文档导出器插槽。

用途：文档导出为 PDF 等外部格式。

实现约定：
- 必须实现 ``base.DocumentExporter``：``meta`` + ``supported_formats()`` + ``export()``
- 导出失败抛 ``app.core.exceptions.ExportError``
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
