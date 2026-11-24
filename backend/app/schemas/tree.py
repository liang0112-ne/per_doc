"""文档树数据契约。

请求与响应分离（见 ``backend/rules/backend.mdc`` §4）：
- ``TreeNodeOut``：树节点响应
- ``SpaceTreeOut``：文档树整体响应
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TreeNodeOut(BaseModel):
    """文档树节点。

    结构为：节点自带 ``children`` 递归数组，
    ``is_dir`` 表示该节点是否是目录（含子节点）。
    """

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    document_name: str
    identify: str
    parent_id: int
    order_sort: int
    # 0 收起 / 1 展开 / 2 空目录
    is_open: int = 0
    # 是否为目录（有子节点）
    is_dir: bool = False
    version: int = 1
    children: list[TreeNodeOut] = Field(default_factory=list)


class TreeSpaceOut(BaseModel):
    """文档树所属文档库的基本信息。"""

    space_id: int
    space_name: str
    identify: str
    description: str | None = None


class SpaceTreeOut(BaseModel):
    """文档树响应。"""

    space: TreeSpaceOut = Field(description="所属文档库")
    tree: list[TreeNodeOut] = Field(default_factory=list, description="顶层节点列表")
    total: int = Field(default=0, description="文档总数")


TreeNodeOut.model_rebuild()
