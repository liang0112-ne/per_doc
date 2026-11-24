"""存储后端插槽。

用途：本地文件系统 / 对象存储。

实现约定：
- 必须实现 ``base.StorageBackend``：``meta`` + ``save()`` + ``read()`` + ``delete()`` + ``exists()``
- 文件名必须随机化存储，防路径穿越
- 失败抛 ``app.core.exceptions.StorageError``
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
