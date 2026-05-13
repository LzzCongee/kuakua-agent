# Python 后端开发规范

> 适用于 FastAPI + Pydantic v2 + Python 3.10+ 项目，AI agent 可直接引用执行。
> 兼顾快速开发与方便 debug 排查，在严谨性和开发效率之间取得平衡。

---

## 1. 类型注解规范

- 所有公开函数/方法必须标注参数类型和返回类型
- 使用 PEP 604 联合类型语法：`str | None`，不推荐 `Optional[str]`
- 使用小写泛型：`list[str]`、`dict[str, int]`，不推荐 `List[str]`、`Dict[str, int]`
- 类属性必须声明类型注解
- 异步生成器使用 `AsyncGenerator[YieldType, SendType]`
- `asyncio.Task` 必须显式标注返回类型，如 `asyncio.Task[Any]`
- **类型别名**：
    - 一般类型别名：Python 3.12+ 统一使用新的 `type` 关键字声明（取代 `TypeAlias`）。
    - **FastAPI 依赖注入别名（重要）**：由于 FastAPI/Pydantic 目前对 `TypeAliasType` 的反射支持尚不完善，**禁止**在 `Depends` 相关的 `Annotated` 别名上使用 `type` 关键字。请使用传统的赋值方式，以确保 OpenAPI Schema 生成正常。

```python
# 推荐：通用类型别名 (Python 3.12+)
type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]

# 推荐：FastAPI 依赖注入别名（使用赋值方式，避免 TypeAliasType 报错）
UserDep = Annotated[User, Depends(get_current_user)]

# 不推荐（会导致 FastAPIError: Invalid args for response field!）
type UserDep = Annotated[User, Depends(get_current_user)]
```

---

## 2. Pydantic 模型规范

- 使用 Pydantic v2，禁止 v1 语法
- 使用 `model_config = ConfigDict(...)` 替代内部 `class Config`
- **对外 API 模型**（Request/Response）：所有字段必须使用 `Field(...)` 并提供 `description` 和验证约束
- **内部传输模型**：`description` 为推荐项，不强求；验证约束仍需标注
- 必填字段用 `Field(...)` 显式标记（无默认值）
- ORM 模型启用 `from_attributes=True`
- 跨字段验证使用 `@model_validator(mode="after")`

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator

# 对外 API 模型：Field + description + 约束 全部必填
class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱地址")
    age: int = Field(..., ge=0, le=150, description="年龄")

    @model_validator(mode="after")
    def validate_fields(self) -> "UserCreate":
        # 跨字段校验逻辑
        return self

# 内部传输模型：description 可选，约束仍需
class MemorySummary(BaseModel):
    prefer_scene: str | None = Field(default=None, description="偏好场景")
    user_tags: list[str] = Field(default_factory=list)  # 内部使用，description 可省
```

---

## 3. FastAPI 路由规范

- 所有路由必须声明 `response_model`
- **SSE/WebSocket 接口豁免**：无法声明 `response_model` 时，在 docstring 中注明响应格式
- `router` 实例建议显式标注类型 `router: APIRouter = APIRouter(...)`，防止 IDE 丢失类型推导
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

# SSE 接口：豁免 response_model，但需注明格式
@router.post("/chat/stream")
async def chat_stream(...) -> EventSourceResponse:
    """流式聊天接口（SSE）
    
    响应格式：
    - event: chunk, data: {"content": "..."}
    - event: done, data: {"content": "完整内容", ...}
    - event: error, data: {"message": "..."}
    """
```

---

## 4. Protocol 与抽象基类规范

- 对外暴露的接口类型使用 `Protocol`（结构化子类型，无需继承）
- 内部继承体系使用 `ABC + @abstractmethod`
- Protocol 类必须添加 `@runtime_checkable` 装饰器
- Protocol 方法体使用 `...`（Ellipsis），不写 `pass`
- ABC 抽象方法体使用 `...`，不写 `pass`

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

- 定义应用级异常基类，**业务错误码（`code: str`）和 HTTP 状态码（`status_code: int`）分离**
- 业务错误码使用 `UPPER_SNAKE_CASE`，如 `NOT_FOUND`、`AI_SERVICE_ERROR`
- 按业务领域派生子异常类，子类只需指定 `code` 和默认 `status_code`
- FastAPI 使用全局异常处理器统一响应格式
- 异常处理器函数必须标注返回类型 `JSONResponse`
- 禁止裸 `except Exception`，优先捕获具体异常

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    """应用异常基类
    
    Attributes:
        code: 业务错误码（如 NOT_FOUND），用于问题域定位
        message: 用户友好的错误描述
        status_code: HTTP 状态码
    """
    
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

class NotFoundError(AppException):
    def __init__(self, resource: str = "资源") -> None:
        super().__init__(code="NOT_FOUND", message=f"{resource} 不存在", status_code=404)

class AIServiceException(AppException):
    def __init__(self, message: str = "AI 服务调用失败") -> None:
        super().__init__(code="AI_SERVICE_ERROR", message=message, status_code=503)

# 全局处理器注册
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
```

---

## 6. 静态类型检查

- 使用 mypy 进行类型检查，**推荐 pragmatic 模式**（非 strict）
- 配置 `pydantic.mypy` 插件
- CI 中 `disallow_untyped_defs` 强制通过，其余规则渐进式启用
- `# type: ignore` 是合理的逃生阀，但需注释忽略原因

```ini
[mypy]
# 核心：必须标注类型，禁止裸 def
disallow_untyped_defs = true
disallow_any_generics = true
no_implicit_optional = true
warn_return_any = true
warn_redundant_casts = true

# 不强制（快速开发时的逃生阀）
# warn_unused_ignores = true
# strict = true

plugins = pydantic.mypy

[pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

- CI 执行命令：`mypy app/`

---

## 7. 代码风格

- 模块顶部使用三引号 docstring 说明模块用途
- 公开类/函数使用 Google Style docstring（含 Args、Returns、Raises）
- import 顺序：标准库 → 第三方库 → 项目内部，各组之间空一行（使用 ruff isort 自动管理）
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
    secret_key: str = ""  # 必须通过环境变量设置，禁止硬编码默认值
    token_expire_minutes: int = 60

    model_config = ConfigDict(env_prefix="AUTH_")
```

---

## 8. 日志规范

- 使用 `logging` + `logging.yaml` 配置，配置与代码分离
- 每个请求自动生成 `trace_id`（基于 `contextvars`，协程安全）
- 响应头中返回 `X-Trace-ID`，便于客户端关联排查
- **关键业务操作必须记录日志**，包含 `user_id` / `trace_id` 等上下文
- 错误日志必须包含 `exc_info=True` 以输出堆栈

```python
from app.core.logging import get_logger, get_trace_id

logger = get_logger(__name__)

# 结构化日志：关键信息用 | 分隔
logger.info(f"夸夸生成完成 | user_id={user_id} | scene={scene} | length={len(content)}")

# 错误日志：必须带堆栈
logger.error(f"AI 调用失败 | user_id={user_id} | error={e}", exc_info=True)

# 获取 trace_id（用于跨服务传递）
trace_id = get_trace_id()
```

---

## 9. 降级容错规范

- `except Exception` 静默吞掉异常是**危险**的，必须满足以下条件之一：
  1. 记录日志（`logger.exception(...)` 或 `logger.error(..., exc_info=True)`）
  2. 明确标注降级原因和影响范围
- **允许静默的场景**：非关键辅助功能（如收藏计数更新），但需注释说明
- **禁止静默的场景**：数据写入、支付、状态变更等关键操作

```python
# ✅ 正确：记录日志
try:
    await update_user_stats(user_id)
except Exception:
    logger.exception(f"用户统计更新失败（降级，不影响主流程） | user_id={user_id}")

# ✅ 正确：明确降级原因
try:
    memory_summary = await get_memory(user_id)
except Exception:
    # 记忆获取失败时降级为无记忆模式，不影响核心夸夸功能
    logger.warning(f"记忆获取降级 | user_id={user_id}")
    memory_summary = None

# ❌ 错误：静默吞掉
try:
    await save_to_database(data)
except Exception:
    pass  # 数据丢失无感知！
```

---

## 10. 后台任务规范

- 使用 `asyncio.create_task` 时，**必须处理异常**，否则会产生 "Task exception was never retrieved" 警告
- 推荐模式：后台任务函数内部自行捕获异常并记录日志
- 如需外部捕获，使用 `add_done_callback`

```python
import asyncio

# ✅ 推荐：后台任务内部自行处理异常
async def _background_save(user_id: str, data: dict) -> None:
    try:
        await save_to_database(data)
        logger.info(f"后台保存成功 | user_id={user_id}")
    except Exception:
        logger.exception(f"后台保存失败 | user_id={user_id}")

# 创建任务
task = asyncio.create_task(_background_save(user_id, data))

# ✅ 可选：额外保险，防止未捕获异常
task.add_done_callback(_handle_task_exception)

def _handle_task_exception(task: asyncio.Task) -> None:
    """处理后台任务中未捕获的异常"""
    if not task.cancelled() and task.exception():
        logger.error(f"后台任务异常 | error={task.exception()}")
```

---

## 11. 敏感配置规范

- 密钥、Token 等敏感配置**禁止硬编码默认值**，必须通过环境变量设置
- 配置缺失时应**快速失败**（启动报错），而非静默使用空值
- `.env.example` 中提供配置模板和说明，`.env` 文件加入 `.gitignore`
- 开发环境可用占位值，但必须醒目（如 `"CHANGE_ME_IN_PRODUCTION"`）

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ✅ 正确：必填项无默认值，启动时缺失即报错
    api_key: str = Field(..., description="API Key（必须通过环境变量设置）")
    
    # ✅ 正确：有合理默认值的非敏感配置
    app_port: int = Field(default=8000, description="应用端口")
    
    # ❌ 错误：敏感信息有真实默认值
    admin_api_key: str = Field(default="changeme", description="管理密钥")
    
    # ✅ 正确：敏感信息用醒目占位值
    admin_api_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION", 
        description="管理密钥（生产环境必须修改）"
    )
```

---

## 快速检查清单

| 检查项 | 要求 |
|--------|------|
| 函数类型注解 | 参数 + 返回值全部标注 |
| Pydantic 版本 | v2，使用 `ConfigDict` |
| API 模型 Field | 对外 API 必须 `description` + 约束；内部模型推荐 |
| 路由 response_model | 每个路由必须声明（SSE/WS 豁免） |
| 依赖注入 | 使用 `Annotated[..., Depends(...)]` |
| 异常体系 | 业务码（str）+ HTTP 状态码（int）分离 |
| 异常容错 | 禁止裸 `except: pass`，必须记录日志 |
| 后台任务 | `create_task` 必须有异常处理 |
| 日志 | 关键操作记录结构化日志，错误带堆栈 |
| 敏感配置 | 禁止硬编码默认值，启动时缺失即报错 |
| mypy | `disallow_untyped_defs` + `disallow_any_generics`，非 strict |
| import 顺序 | 标准库 > 第三方 > 内部（ruff isort） |
