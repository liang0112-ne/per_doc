"""插件契约的唯一来源。

本模块定义所有插件的 Protocol，是核心代码与具体插件实现之间的**唯一**契约。
规则要点（见 ``backend/rules/backend.mdc`` §13.2）：

- 用 ``typing.Protocol`` 声明，不用抽象基类 ABC（不强制继承，支持鸭子类型）
- 每个插件必须携带 ``meta: PluginMeta``（含 name / version / description）
- 接口方法只描述「能力」，不描述实现细节

新增插件类型时，先在这里加 Protocol，再写实现，最后到 ``registry.py`` 注册。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PluginMeta:
    """插件元信息。

    Attributes:
        name: 插件唯一名，注册表的键。
        version: 插件版本号，语义化字符串。
        description: 插件用途说明，面向人类阅读。
        capabilities: 插件额外声明的能力标签，便于按能力筛选。
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """校验元信息的必填项。"""
        if not self.name:
            raise ValueError("插件 name 不能为空")


@runtime_checkable
class DocumentParser(Protocol):
    """文件解析器：把非 Markdown 文件解析为 Markdown。

    对应扩展方向：PDF / Word / Excel / 图片 OCR → Markdown。
    """

    meta: PluginMeta

    def supported_extensions(self) -> list[str]:
        """返回本解析器支持的文件后缀（含点，如 ``['.pdf', '.docx']``）。"""
        ...

    def parse(self, file_path: str, options: dict[str, Any] | None = None) -> str:
        """解析文件返回 Markdown 源码。

        Args:
            file_path: 待解析文件的绝对路径。
            options: 解析选项，插件自行定义语义。

        Raises:
            ParserError: 解析失败。
        """
        ...


@runtime_checkable
class VectorIndexer(Protocol):
    """向量索引器：切片 → Embedding → 向量库。

    对应扩展方向：文档语义检索与检索增强问答的底层支撑。
    """

    meta: PluginMeta

    def index(self, document_id: int, markdown: str) -> int:
        """把文档写入索引。

        Args:
            document_id: 文档主键。
            markdown: 文档 Markdown 源码。

        Returns:
            写入的切片数量。

        Raises:
            StorageError: 写入索引失败。
        """
        ...

    def remove(self, document_id: int) -> None:
        """从索引中移除文档。

        Raises:
            StorageError: 移除失败。
        """
        ...

    def search(self, query: str, limit: int = 10) -> list[tuple[int, float]]:
        """按语义检索，返回 ``(document_id, 相似度)`` 列表。

        Raises:
            StorageError: 检索失败。
        """
        ...


@runtime_checkable
class DocumentAgent(Protocol):
    """文档智能体：基于文档的检索增强问答。"""

    meta: PluginMeta

    def chat(self, question: str, space_id: int | None = None) -> str:
        """回答一个问题。

        Args:
            question: 用户提问。
            space_id: 限定检索范围的文档库 id，None 表示全库。

        Raises:
            AppError: 智能体执行失败。
        """
        ...


@runtime_checkable
class AgentTool(Protocol):
    """智能体可调用的外部工具。"""

    meta: PluginMeta

    def name(self) -> str:
        """工具唯一名，供智能体按名调用。"""
        ...

    def parameters(self) -> dict[str, Any]:
        """返回工具入参的 JSON Schema 描述。"""
        ...

    def execute(self, **kwargs: Any) -> Any:
        """执行工具。

        Raises:
            AppError: 工具执行失败。
        """
        ...


@runtime_checkable
class MarkdownRenderer(Protocol):
    """Markdown 渲染器：Markdown → HTML。"""

    meta: PluginMeta

    def render(self, markdown: str, options: dict[str, Any] | None = None) -> str:
        """把 Markdown 渲染为 HTML。

        Args:
            markdown: Markdown 源码。
            options: 渲染选项（如主题名）。

        Raises:
            RenderError: 渲染失败。
        """
        ...


@runtime_checkable
class DocumentExporter(Protocol):
    """文档导出器：把文档导出为其他格式。"""

    meta: PluginMeta

    def supported_formats(self) -> list[str]:
        """返回本导出器支持的格式标识（如 ``['pdf']``）。"""
        ...

    def export(
        self,
        source: str,
        output_path: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        """执行导出。

        Args:
            source: 源文档 Markdown 源码。
            output_path: 输出文件路径。
            options: 导出选项。

        Returns:
            实际写入的文件路径。

        Raises:
            ExportError: 导出失败。
        """
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """存储后端：本地文件系统 / 对象存储。"""

    meta: PluginMeta

    def save(self, file_name: str, data: bytes) -> str:
        """保存文件，返回可访问的相对路径。

        Args:
            file_name: 原始文件名，插件需自行做安全化处理。
            data: 文件内容。

        Raises:
            StorageError: 写入失败。
        """
        ...

    def read(self, file_path: str) -> bytes:
        """读取文件内容。

        Raises:
            StorageError: 文件不存在或读取失败。
        """
        ...

    def delete(self, file_path: str) -> None:
        """删除文件（不存在时静默返回）。

        Raises:
            StorageError: 删除失败。
        """
        ...

    def exists(self, file_path: str) -> bool:
        """判断文件是否存在。"""
        ...
