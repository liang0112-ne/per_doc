"""插件注册表：唯一的注册入口与查询出口。

规则要点（见 ``backend/rules/backend.mdc`` §13.3）：

- 注册表是**唯一**的插件存放处，不允许在别处另写 dict 存插件
- 核心服务只通过本模块的查询函数获取插件，**不 import 具体实现**
- 插件之间不互相 import，只能通过 ``base.py`` 的 Protocol 交互

查询函数在没有匹配插件时返回 ``None``，由调用方决定降级策略。
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from app.plugins.base import (
    AgentTool,
    DocumentAgent,
    DocumentExporter,
    DocumentParser,
    MarkdownRenderer,
    StorageBackend,
    VectorIndexer,
)

logger = logging.getLogger(__name__)

_P = TypeVar("_P")

# 各插槽的注册表：插件名 → 插件类
_PARSERS: dict[str, type[DocumentParser]] = {}
_INDEXERS: dict[str, type[VectorIndexer]] = {}
_AGENTS: dict[str, type[DocumentAgent]] = {}
_TOOLS: dict[str, type[AgentTool]] = {}
_RENDERERS: dict[str, type[MarkdownRenderer]] = {}
_EXPORTERS: dict[str, type[DocumentExporter]] = {}
_STORAGES: dict[str, type[StorageBackend]] = {}


def _register(table: dict[str, type[_P]], name: str, plugin_cls: type[_P]) -> None:
    """通用注册逻辑：同名覆盖并记录日志。"""
    if name in table:
        logger.warning("插件 %s 被覆盖：%s → %s", name, table[name], plugin_cls)
    table[name] = plugin_cls
    logger.info("注册插件 %s -> %s", name, plugin_cls)


def register_parser(name: str, parser_cls: type[DocumentParser]) -> None:
    """注册文件解析器。"""
    _register(_PARSERS, name, parser_cls)


def register_indexer(name: str, indexer_cls: type[VectorIndexer]) -> None:
    """注册向量索引器。"""
    _register(_INDEXERS, name, indexer_cls)


def register_agent(name: str, agent_cls: type[DocumentAgent]) -> None:
    """注册文档智能体。"""
    _register(_AGENTS, name, agent_cls)


def register_tool(name: str, tool_cls: type[AgentTool]) -> None:
    """注册智能体工具。"""
    _register(_TOOLS, name, tool_cls)


def register_renderer(name: str, renderer_cls: type[MarkdownRenderer]) -> None:
    """注册 Markdown 渲染器。"""
    _register(_RENDERERS, name, renderer_cls)


def register_exporter(name: str, exporter_cls: type[DocumentExporter]) -> None:
    """注册文档导出器。"""
    _register(_EXPORTERS, name, exporter_cls)


def register_storage(name: str, storage_cls: type[StorageBackend]) -> None:
    """注册存储后端。"""
    _register(_STORAGES, name, storage_cls)


def get_parser(name: str) -> DocumentParser | None:
    """按名称获取解析器实例。"""
    return _instantiate(_PARSERS.get(name))


def get_parser_by_extension(extension: str) -> DocumentParser | None:
    """按文件后缀获取匹配的解析器。

    后缀比较忽略大小写，且容忍调用方传入 ``pdf`` 或 ``.pdf`` 两种写法。
    """
    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    for parser_cls in _PARSERS.values():
        parser = parser_cls()
        if ext in {item.lower() for item in parser.supported_extensions()}:
            return parser
    return None


def get_indexer(name: str) -> VectorIndexer | None:
    """按名称获取向量索引器实例。"""
    return _instantiate(_INDEXERS.get(name))


def get_agent(name: str) -> DocumentAgent | None:
    """按名称获取智能体实例。"""
    return _instantiate(_AGENTS.get(name))


def get_tool(name: str) -> AgentTool | None:
    """按名称获取工具实例。"""
    return _instantiate(_TOOLS.get(name))


def get_renderer(name: str) -> MarkdownRenderer | None:
    """按名称获取渲染器实例。"""
    return _instantiate(_RENDERERS.get(name))


def get_default_renderer() -> MarkdownRenderer | None:
    """获取默认渲染器（注册顺序中的第一个）。"""
    return _instantiate(next(iter(_RENDERERS.values()), None))


def get_exporter(name: str) -> DocumentExporter | None:
    """按名称获取导出器实例。"""
    return _instantiate(_EXPORTERS.get(name))


def get_exporter_by_format(fmt: str) -> DocumentExporter | None:
    """按格式标识获取导出器。"""
    target = fmt.lower().lstrip(".")
    for exporter_cls in _EXPORTERS.values():
        exporter = exporter_cls()
        if target in {item.lower().lstrip(".") for item in exporter.supported_formats()}:
            return exporter
    return None


def get_storage(name: str) -> StorageBackend | None:
    """按名称获取存储后端实例。"""
    return _instantiate(_STORAGES.get(name))


def get_default_storage() -> StorageBackend | None:
    """获取默认存储后端（注册顺序中的第一个）。"""
    return _instantiate(next(iter(_STORAGES.values()), None))


def all_parsers() -> list[DocumentParser]:
    """返回全部解析器实例。"""
    return [cls() for cls in _PARSERS.values()]


def all_indexers() -> list[VectorIndexer]:
    """返回全部向量索引器实例。"""
    return [cls() for cls in _INDEXERS.values()]


def all_agents() -> list[DocumentAgent]:
    """返回全部智能体实例。"""
    return [cls() for cls in _AGENTS.values()]


def all_tools() -> list[AgentTool]:
    """返回全部工具实例。"""
    return [cls() for cls in _TOOLS.values()]


def all_renderers() -> list[MarkdownRenderer]:
    """返回全部渲染器实例。"""
    return [cls() for cls in _RENDERERS.values()]


def all_exporters() -> list[DocumentExporter]:
    """返回全部导出器实例。"""
    return [cls() for cls in _EXPORTERS.values()]


def all_storages() -> list[StorageBackend]:
    """返回全部存储后端实例。"""
    return [cls() for cls in _STORAGES.values()]


def registry_snapshot() -> dict[str, list[str]]:
    """返回各插槽已注册的插件名，用于自检与后台展示。"""
    return {
        "parsers": list(_PARSERS),
        "indexers": list(_INDEXERS),
        "agents": list(_AGENTS),
        "tools": list(_TOOLS),
        "renderers": list(_RENDERERS),
        "exporters": list(_EXPORTERS),
        "storages": list(_STORAGES),
    }


def clear_all() -> None:
    """清空所有注册表（仅测试使用）。"""
    for table in (_PARSERS, _INDEXERS, _AGENTS, _TOOLS, _RENDERERS, _EXPORTERS, _STORAGES):
        table.clear()


def _instantiate(plugin_cls: type[_P] | None) -> _P | None:
    """实例化插件类，失败时记录日志并返回 None。"""
    if plugin_cls is None:
        return None
    try:
        return plugin_cls()
    except Exception:
        logger.exception("插件实例化失败：%s", plugin_cls)
        return None


def describe(plugin: Any) -> str:
    """返回插件的可读描述，用于日志与后台展示。"""
    meta = getattr(plugin, "meta", None)
    if meta is None:
        return repr(plugin)
    return f"{meta.name}@{meta.version} — {meta.description}"
