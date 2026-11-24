"""文档库（Space）模块的数据契约。

请求与响应分离（见 ``backend/rules/backend.mdc`` §4）：
- ``SpaceCreate`` / ``SpaceUpdate``：请求体
- ``SpaceOut`` / ``SpaceBrief``：响应体
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.identifier import is_valid_space_identify


class SpaceCreate(BaseModel):
    """创建文档库请求。"""

    space_name: str = Field(min_length=1, max_length=500, description="文档库名称")
    identify: str | None = Field(default=None, max_length=50, description="URL 短标识")
    description: str = Field(default="", max_length=2000, description="文档库描述")
    group_name: str = Field(default="默认分组", max_length=100, description="分组名")
    cover: str | None = Field(default=None, max_length=1000, description="封面图地址")
    editor: str = Field(default="markdown", max_length=50, description="默认编辑器")
    theme: str = Field(default="default", max_length=255, description="主题风格")
    is_private: int = Field(default=0, ge=0, le=1, description="0 公开 / 1 需访问密码")
    access_password: str | None = Field(default=None, max_length=64, description="访问密码明文")
    auto_save: int = Field(default=1, ge=0, le=1, description="0 关闭 / 1 开启自动保存")
    history_count: int = Field(default=0, ge=0, description="每个文档保留的历史版本数，0 不限")

    @field_validator("is_private")
    @classmethod
    def _check_private(cls, value: int) -> int:
        """私有标记只允许 0 或 1。"""
        if value not in (0, 1):
            raise ValueError("is_private 只能是 0 或 1")
        return value

    @field_validator("identify")
    @classmethod
    def _check_identify(cls, value: str | None) -> str | None:
        """标识格式校验；未填时由 service 自动生成。"""
        if value is None or value == "":
            return None
        if not is_valid_space_identify(value):
            raise ValueError("标识只能以小写字母开头，可包含字母、数字、下划线和短横线")
        return value

    @field_validator("space_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        """名称去除首尾空白。"""
        stripped = value.strip()
        if not stripped:
            raise ValueError("文档库名称不能为空")
        return stripped


class SpaceUpdate(BaseModel):
    """更新文档库请求。

    所有字段可选，只更新传入的项。
    """

    space_name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    group_name: str | None = Field(default=None, max_length=100)
    cover: str | None = Field(default=None, max_length=1000)
    editor: str | None = Field(default=None, max_length=50)
    theme: str | None = Field(default=None, max_length=255)
    is_private: int | None = Field(default=None, ge=0, le=1)
    access_password: str | None = Field(default=None, max_length=64)
    auto_save: int | None = Field(default=None, ge=0, le=1)
    history_count: int | None = Field(default=None, ge=0)

    @field_validator("space_name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        """名称去除首尾空白；空字符串视为非法。"""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("文档库名称不能为空")
        return stripped


class SpaceOut(BaseModel):
    """文档库详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    space_id: int
    space_name: str
    identify: str
    group_name: str
    description: str | None
    cover: str | None
    editor: str
    theme: str
    is_private: int
    auto_save: int
    history_count: int
    order_index: int
    member_id: int
    create_time: datetime
    modify_time: datetime | None
    doc_count: int = Field(default=0, description="文档数（实时统计）")
    is_owner: bool = Field(default=False, description="当前请求者是否为创建者")


class SpaceBrief(BaseModel):
    """文档库列表项（首页卡片用）。"""

    model_config = ConfigDict(from_attributes=True)

    space_id: int
    space_name: str
    identify: str
    group_name: str
    description: str | None
    cover: str | None
    is_private: int
    member_id: int
    create_time: datetime
    modify_time: datetime | None
    doc_count: int = Field(default=0, description="文档数（实时统计）")
    is_owner: bool = Field(default=False, description="当前请求者是否为创建者")


class SpaceListOut(BaseModel):
    """文档库列表响应。"""

    total: int = Field(description="文档库总数")
    items: list[SpaceBrief] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list, description="全部分组名")


class AccessCheckOut(BaseModel):
    """访问密码校验结果。"""

    granted: bool = Field(description="是否已获得访问权限")
    space_id: int
    identify: str


class AccessSubmit(BaseModel):
    """提交访问密码请求。"""

    password: str = Field(min_length=1, max_length=64, description="访问密码明文")


class GroupName(BaseModel):
    """分组名。"""

    group_name: str
    count: int = Field(default=0, description="该分组下的文档库数量")
