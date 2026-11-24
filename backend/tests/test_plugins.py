"""B3 插件骨架自测：Protocol 契约与注册表行为。"""

from __future__ import annotations

from typing import Any, Protocol

import pytest

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

PROTOCOL_NAMES = [
    "DocumentParser",
    "VectorIndexer",
    "DocumentAgent",
    "AgentTool",
    "MarkdownRenderer",
    "DocumentExporter",
    "StorageBackend",
]


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    """每个用例前后清空注册表，避免互相污染。"""
    registry.clear_all()
    yield
    registry.clear_all()


class TestPluginMeta:
    """插件元信息。"""

    def test_fields(self) -> None:
        meta = PluginMeta(name="pdf", version="1.2.0", description="PDF 解析")
        assert meta.name == "pdf"
        assert meta.version == "1.2.0"
        assert meta.description == "PDF 解析"
        assert meta.capabilities == ()

    def test_defaults(self) -> None:
        meta = PluginMeta(name="x")
        assert meta.version == "1.0.0"
        assert meta.description == ""

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            PluginMeta(name="")

    def test_is_frozen(self) -> None:
        meta = PluginMeta(name="x")
        with pytest.raises(AttributeError):
            meta.name = "y"  # type: ignore[misc]


class TestProtocols:
    """Protocol 定义符合规则要求。"""

    @pytest.mark.parametrize("name", PROTOCOL_NAMES)
    def test_protocol_exists(self, name: str) -> None:
        proto = getattr(base, name)
        assert isinstance(proto, type)
        assert issubclass(proto, Protocol)

    @pytest.mark.parametrize("name", PROTOCOL_NAMES)
    def test_protocol_is_runtime_checkable(self, name: str) -> None:
        proto = getattr(base, name)
        assert proto._is_runtime_protocol is True  # type: ignore[attr-defined]

    @pytest.mark.parametrize("name", PROTOCOL_NAMES)
    def test_no_abc_base(self, name: str) -> None:
        """插件接口不得使用自定义抽象基类强制继承。

        Protocol 自身继承自 typing 内部的 ABC，这是标准库行为；
        需要保证的是不额外定义业务 ABC 作为基类。
        """
        proto = getattr(base, name)
        for klass in proto.__mro__:
            if klass.__module__.startswith("typing"):
                continue
            if klass is object or klass.__module__ == "abc":
                continue
            assert not klass.__abstractmethods__, f"{name} 继承了抽象基类 {klass}"

    def test_parser_methods(self) -> None:
        assert hasattr(DocumentParser, "supported_extensions")
        assert hasattr(DocumentParser, "parse")

    def test_indexer_methods(self) -> None:
        assert hasattr(VectorIndexer, "index")
        assert hasattr(VectorIndexer, "remove")
        assert hasattr(VectorIndexer, "search")

    def test_agent_methods(self) -> None:
        assert hasattr(DocumentAgent, "chat")

    def test_tool_methods(self) -> None:
        assert hasattr(AgentTool, "name")
        assert hasattr(AgentTool, "parameters")
        assert hasattr(AgentTool, "execute")

    def test_renderer_methods(self) -> None:
        assert hasattr(MarkdownRenderer, "render")

    def test_exporter_methods(self) -> None:
        assert hasattr(DocumentExporter, "supported_formats")
        assert hasattr(DocumentExporter, "export")

    def test_storage_methods(self) -> None:
        assert hasattr(StorageBackend, "save")
        assert hasattr(StorageBackend, "read")
        assert hasattr(StorageBackend, "delete")
        assert hasattr(StorageBackend, "exists")


class TestStructuralTyping:
    """鸭子类型：不继承 Protocol 也能被识别。"""

    def test_duck_typed_parser_satisfies_protocol(self) -> None:
        class DuckParser:
            meta = PluginMeta(name="duck")

            def supported_extensions(self) -> list[str]:
                return [".pdf"]

            def parse(self, file_path: str, options: dict[str, Any] | None = None) -> str:
                return "# ok"

        assert isinstance(DuckParser(), DocumentParser)

    def test_incomplete_object_not_matching(self) -> None:
        class NotAParser:
            meta = PluginMeta(name="bad")

        assert not isinstance(NotAParser(), DocumentParser)


class FakeParser:
    """测试用的解析器桩（仅在测试中出现，不是生产空壳）。"""

    meta = PluginMeta(name="fake", description="测试用解析器")

    def __init__(self, extensions: list[str] | None = None) -> None:
        self._extensions = extensions or [".pdf", ".docx"]

    def supported_extensions(self) -> list[str]:
        return self._extensions

    def parse(self, file_path: str, options: dict[str, Any] | None = None) -> str:
        return f"# parsed {file_path}"


class FakeRenderer:
    """测试用的渲染器桩。"""

    meta = PluginMeta(name="fake-renderer")

    def render(self, markdown: str, options: dict[str, Any] | None = None) -> str:
        return f"<p>{markdown}</p>"


class FakeExporter:
    """测试用的导出器桩。"""

    meta = PluginMeta(name="fake-exporter")

    def supported_formats(self) -> list[str]:
        return ["pdf", "epub"]

    def export(self, source: str, output_path: str, options: dict[str, Any] | None = None) -> str:
        return output_path


class FakeStorage:
    """测试用的存储后端桩。"""

    meta = PluginMeta(name="fake-storage")

    def save(self, file_name: str, data: bytes) -> str:
        return file_name

    def read(self, file_path: str) -> bytes:
        return b""

    def delete(self, file_path: str) -> None:
        return None

    def exists(self, file_path: str) -> bool:
        return False


class BrokenPlugin:
    """构造时抛异常的插件，验证实例化失败不冒泡。"""

    meta = PluginMeta(name="broken")

    def __init__(self) -> None:
        raise RuntimeError("boom")


class TestRegistry:
    """注册表读写行为。"""

    def test_empty_registry_returns_none(self) -> None:
        assert registry.get_parser("none") is None
        assert registry.get_renderer("none") is None
        assert registry.get_storage("none") is None
        assert registry.get_exporter("none") is None
        assert registry.get_indexer("none") is None
        assert registry.get_agent("none") is None
        assert registry.get_tool("none") is None

    def test_register_and_get_parser(self) -> None:
        registry.register_parser("fake", FakeParser)
        found = registry.get_parser("fake")
        assert found is not None
        assert found.meta.name == "fake"

    def test_register_and_get_renderer(self) -> None:
        registry.register_renderer("r", FakeRenderer)
        assert registry.get_renderer("r") is not None

    def test_register_and_get_exporter(self) -> None:
        registry.register_exporter("e", FakeExporter)
        assert registry.get_exporter("e") is not None

    def test_register_and_get_storage(self) -> None:
        registry.register_storage("s", FakeStorage)
        assert registry.get_storage("s") is not None

    def test_get_parser_by_extension(self) -> None:
        registry.register_parser("fake", FakeParser)
        assert registry.get_parser_by_extension(".pdf") is not None
        assert registry.get_parser_by_extension("PDF") is not None
        assert registry.get_parser_by_extension("pdf") is not None
        assert registry.get_parser_by_extension(".xls") is None

    def test_get_exporter_by_format(self) -> None:
        registry.register_exporter("e", FakeExporter)
        assert registry.get_exporter_by_format("pdf") is not None
        assert registry.get_exporter_by_format(".epub") is not None
        assert registry.get_exporter_by_format("docx") is None

    def test_default_renderer_and_storage(self) -> None:
        assert registry.get_default_renderer() is None
        registry.register_renderer("r", FakeRenderer)
        assert registry.get_default_renderer() is not None

        assert registry.get_default_storage() is None
        registry.register_storage("s", FakeStorage)
        assert registry.get_default_storage() is not None

    def test_all_listers(self) -> None:
        registry.register_parser("fake", FakeParser)
        registry.register_renderer("r", FakeRenderer)
        registry.register_exporter("e", FakeExporter)
        registry.register_storage("s", FakeStorage)
        assert len(registry.all_parsers()) == 1
        assert len(registry.all_renderers()) == 1
        assert len(registry.all_exporters()) == 1
        assert len(registry.all_storages()) == 1
        assert registry.all_indexers() == []
        assert registry.all_agents() == []
        assert registry.all_tools() == []

    def test_snapshot_reflects_registrations(self) -> None:
        registry.register_parser("fake", FakeParser)
        snapshot = registry.registry_snapshot()
        assert snapshot["parsers"] == ["fake"]
        assert snapshot["renderers"] == []

    def test_duplicate_registration_overwrites(self) -> None:
        registry.register_parser("dup", FakeParser)
        registry.register_parser("dup", FakeParser)
        assert len(registry.all_parsers()) == 1

    def test_broken_plugin_returns_none(self) -> None:
        registry.register_parser("broken", BrokenPlugin)
        assert registry.get_parser("broken") is None

    def test_clear_all(self) -> None:
        registry.register_parser("fake", FakeParser)
        registry.clear_all()
        assert registry.get_parser("fake") is None

    def test_describe(self) -> None:
        parser = FakeParser()
        assert "fake" in registry.describe(parser)

    def test_describe_without_meta(self) -> None:
        assert registry.describe(object()) != ""


class TestNoStubImplementations:
    """规则 §13.6：未实现的插件不得写空壳类。"""

    def test_no_builtin_plugin_classes(self) -> None:
        """除 Protocol 与 PluginMeta 外，base.py 不得定义具体插件类。"""
        for name, obj in vars(base).items():
            if name.startswith("_") or name in PROTOCOL_NAMES + ["PluginMeta"]:
                continue
            if isinstance(obj, type) and issubclass(obj, Protocol):
                continue
            if isinstance(obj, type) and not issubclass(obj, Protocol):
                assert name == "Any", f"base.py 不应包含具体实现类：{name}"

    def test_registry_starts_empty(self) -> None:
        assert registry.registry_snapshot() == {
            "parsers": [],
            "indexers": [],
            "agents": [],
            "tools": [],
            "renderers": [],
            "exporters": [],
            "storages": [],
        }

    def test_register_all_is_noop(self) -> None:
        from app.plugins import register_all

        register_all()
        assert registry.registry_snapshot()["renderers"] == []


class TestNoConcreteImports:
    """规则 §13.4：核心层不得直接 import 具体插件实现。"""

    def test_core_does_not_import_plugin_implementations(self) -> None:
        from pathlib import Path

        import app.core as core_pkg

        root = Path(core_pkg.__file__).parent
        for path in root.glob("*.py"):
            content = path.read_text(encoding="utf-8")
            assert "app.plugins.parser." not in content, path.name
            assert "app.plugins.renderer." not in content, path.name
            assert "app.plugins.storage." not in content, path.name
            assert "app.plugins.exporter." not in content, path.name
