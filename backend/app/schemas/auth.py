"""认证模块的数据契约。

请求与响应分离（见 ``backend/rules/backend.mdc`` §4）：
- ``XxxCreate`` / ``XxxUpdate``：请求体
- ``XxxOut``：响应体，``from_attributes=True``，ORM 对象直接序列化

响应 schema 显式声明字段，不直接返回 ORM 对象，避免泄露内部字段
（如密码哈希）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.identity import is_valid_account, is_valid_email


class LoginRequest(BaseModel):
    """登录请求。"""

    account: str = Field(min_length=1, max_length=100, description="登录名")
    password: str = Field(min_length=1, max_length=64, description="明文密码")
    remember: bool = Field(default=False, description="是否记住登录状态")

    @field_validator("account")
    @classmethod
    def _check_account(cls, value: str) -> str:
        """账号格式非法时直接拒绝，避免无谓的数据库查询。"""
        if not is_valid_account(value):
            raise ValueError("账号格式不正确")
        return value


class RegisterRequest(BaseModel):
    """注册请求。"""

    account: str = Field(min_length=3, max_length=51, description="登录名")
    password: str = Field(min_length=8, max_length=64, description="明文密码")
    password_confirm: str = Field(min_length=8, max_length=64, description="确认密码")
    email: str | None = Field(default=None, max_length=100, description="邮箱")
    real_name: str = Field(default="", max_length=255, description="昵称")

    @field_validator("account")
    @classmethod
    def _check_account(cls, value: str) -> str:
        """账号格式校验。"""
        if not is_valid_account(value):
            raise ValueError("账号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str | None) -> str | None:
        """邮箱格式校验；未填时跳过。"""
        if value is None or value == "":
            return None
        if not is_valid_email(value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("real_name")
    @classmethod
    def _strip_real_name(cls, value: str) -> str:
        """昵称去除首尾空白。"""
        return value.strip()


class PasswordChangeRequest(BaseModel):
    """修改密码请求。"""

    old_password: str = Field(min_length=1, max_length=64, description="原密码")
    new_password: str = Field(min_length=8, max_length=64, description="新密码")
    new_password_confirm: str = Field(min_length=8, max_length=64, description="确认新密码")


class MemberOut(BaseModel):
    """用户信息响应体。

    只暴露展示所需字段，不含密码哈希等敏感信息。
    """

    model_config = ConfigDict(from_attributes=True)

    member_id: int
    account: str
    real_name: str
    email: str | None
    phone: str | None
    avatar: str | None
    status: int
    create_time: datetime
    last_login_time: datetime | None


class LoginResponse(BaseModel):
    """登录响应体。"""

    user: MemberOut
    csrf_token: str = Field(description="写操作需回传的 CSRF Token")


class CsrfResponse(BaseModel):
    """CSRF Token 响应体。"""

    csrf_token: str
    header_name: str = Field(description="请求头名称，前端需原样回传")
