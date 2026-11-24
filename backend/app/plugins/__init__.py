"""后端插件包。

``base.py`` 是所有插件 Protocol 的唯一契约来源，``registry.py`` 是唯一注册入口。
具体插件实现放在 ``parser/ indexer/ agent/ tool/ renderer/ exporter/ storage/`` 子目录。

新增插件的五步（见 ``backend/rules/backend.mdc`` §13.5）：

1. 在 ``base.py`` 定义 Protocol（若已有则跳过）
2. 在对应子目录新建实现文件
3. 在本文件的 ``register_all()`` 中注册
4. 在对应子目录的 ``tests/`` 写单测
5. 跑通测试后，才在 service 中通过 registry 调用
"""

from app.plugins import base, registry
from app.plugins.base import (
    AgentTool,
    DocumentAgent,
    DocumentExporter,
    DocumentParser,
    MarkdownRenderer,
    PluginMeta,
    StorageBackend,
    VectorIndexer,
)

__all__ = [
    "AgentTool",
    "DocumentAgent",
    "DocumentExporter",
    "DocumentParser",
    "MarkdownRenderer",
    "PluginMeta",
    "StorageBackend",
    "VectorIndexer",
    "base",
    "register_all",
    "registry",
]


def register_all() -> None:
    """注册全部内置插件。

    启动时调用一次。当前尚无插件实现落位（渲染器 / 导出器 / 存储后端分别属
    B8 / B12 / B11），因此这里只保留唯一注册入口，待实现就绪后在此逐个注册。

    规则约束：插件实现之间禁止互相 import，只能通过 ``base.py`` 的 Protocol 交互；
    核心服务禁止直接 import 具体实现，必须走 ``registry``。
    """
    return None
