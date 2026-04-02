# Python 后端开发规范

> 适用于 FastAPI + Pydantic v2 + Python 3.10+ 项目，AI agent 可直接引用执行。

---

## 1. 类型注解规范

- 所有公开函数/方法必须标注参数类型和返回类型
- 使用 PEP 604 联合类型语法：`str | None`，禁止 `Optional[str]`
- 使用小写泛型：`list[str]`、`dict[str, int]`，禁止 `List[str]`、`Dict[str, int]`
- 类属性必须声明类型注解
- 异步生成器使用 `AsyncGenerator[YieldType, SendType]`
- 禁止使用 `Any`；确实需要时添加 `# type: ignore[assignment]` 并注释原因

```python
# 正确
async def get_user(user_id: int) -> User | None: ...

# 错误
async def get_user(user_id): ...
```

---

## 2. Pydantic 模型规范

- 使用 Pydantic v2，禁止 v1 语法
- 使用 `model_config = ConfigDict(...)` 替代内部 `class Config`
- 所有字段使用 `Field(...)` 并提供 `description` 和验证约束
- 必填字段用 `Field(...)` 显式标记（无默认值）
- ORM 模型启用 `from_attributes=True`
- 跨字段验证使用 `@model_validator(mode="after")`

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator

class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱地址")
    age: int = Field(..., ge=0, le=150, description="年龄")

    @model_validator(mode="after")
    def validate_fields(self) -> "UserCreate":
        # 跨字段校验逻辑
        return self
```

---

## 3. FastAPI 路由规范

- 所有路由必须声明 `response_model`
- 使用 `Annotated[Type, Depends(...)]` 进行依赖注入
- Query 参数使用 `Query(description=...)` 标记
- Path 参数使用 `Path(description=...)` 标记
- 枚举参数使用 `Literal[...]` 约束合法值
- 禁止使用 Python 内置名称作为参数名（`type`、`id`、`input`、`filter`）

```python
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path, Query

router = APIRouter()

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: Annotated[int, Path(description="用户 ID", ge=1)],
    status: Annotated[Literal["active", "inactive"], Query(description="账号状态")] = "active",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> UserResponse: ...
```

---

## 4. Protocol 与抽象基类规范

- 对外暴露的接口类型使用 `Protocol`（结构化子类型，无需继承）
- 内部继承体系使用 `ABC + @abstractmethod`
- Protocol 类必须添加 `@runtime_checkable` 装饰器
- Protocol 方法体使用 `...`（Ellipsis），不写 `pass`

```python
from typing import Protocol, runtime_checkable
from abc import ABC, abstractmethod

@runtime_checkable
class StorageProtocol(Protocol):
    async def save(self, key: str, value: bytes) -> None: ...
    async def load(self, key: str) -> bytes | None: ...

class BaseRepository(ABC):
    @abstractmethod
    async def find_by_id(self, record_id: int) -> dict | None: ...
```

---

## 5. 异常处理规范

- 定义应用级异常基类，包含 `code: str` 和 `message: str`
- 按业务领域派生子异常类
- FastAPI 使用全局异常处理器统一响应格式
- 异常处理器函数必须标注返回类型 `JSONResponse`
- 禁止裸 `except Exception`，优先捕获具体异常

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class AppError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(code="NOT_FOUND", message=f"{resource} 不存在")

# 全局处理器注册
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"code": exc.code, "message": exc.message},
    )
```

---

## 6. 静态类型检查

- 使用 mypy strict 模式，在 CI/CD 中强制通过
- 配置 `pydantic.mypy` 插件
- `mypy.ini` 或 `pyproject.toml` 关键配置：

```ini
[mypy]
strict = true
plugins = pydantic.mypy
disallow_untyped_defs = true
no_implicit_optional = true
warn_return_any = true
warn_unused_ignores = true

[pydantic-mypy]
init_forbid_extra = true
warn_required_dynamic_aliases = true
```

- CI 执行命令：`mypy app/ --strict`

---

## 7. 代码风格

- 模块顶部使用三引号 docstring 说明模块用途
- 公开类/函数使用 Google Style docstring（含 Args、Returns、Raises）
- import 顺序：标准库 → 第三方库 → 项目内部，各组之间空一行
- 常量命名使用 `UPPER_SNAKE_CASE`
- 所有异步函数统一使用 `async def`，不混用同步阻塞调用
- 配置类使用 pydantic-settings 的 `BaseSettings`，字段从环境变量读取

```python
"""用户认证模块：处理登录、注册及 Token 管理。"""

# 标准库
import hashlib
from datetime import datetime

# 第三方库
from fastapi import APIRouter
from pydantic_settings import BaseSettings

# 项目内部
from app.models.user import User

MAX_LOGIN_ATTEMPTS: int = 5

class AuthSettings(BaseSettings):
    secret_key: str = ""
    token_expire_minutes: int = 60

    model_config = ConfigDict(env_prefix="AUTH_")
```

---

## 快速检查清单

| 检查项 | 要求 |
|--------|------|
| 函数类型注解 | 参数 + 返回值全部标注 |
| Pydantic 版本 | v2，使用 `ConfigDict` |
| 路由 response_model | 每个路由必须声明 |
| 依赖注入 | 使用 `Annotated[..., Depends(...)]` |
| 异常处理 | 定义应用基类 + 全局处理器 |
| mypy | strict 模式，CI 强制通过 |
| import 顺序 | 标准库 > 第三方 > 内部 |
