"""向量索引器插槽。

用途：文档切片 → Embedding → 向量库。

实现约定：
- 必须实现 ``base.VectorIndexer``：``meta`` + ``index()`` + ``remove()`` + ``search()``
- 失败抛 ``app.core.exceptions.StorageError``
- 在 ``app/plugins/__init__.py`` 的 ``register_all()`` 中注册
"""
