"""
夸夸Agent API 主入口
FastAPI 应用初始化与配置

微服务架构设计：
- 配置通过环境变量和 .env 文件管理
- 统一的日志系统，支持 trace_id 追踪
- 标准化的请求中间件
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import admin, asr, auth, chat, emotion, favorites, memory
from .config import get_settings
from .core.exceptions import register_exception_handlers
from .core.logging import get_logger, register_logging_middleware
from .core.mcp_client import mcp_client
from .models.database import close_db, init_db
from .services.emotion.middleware import EmotionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理

    在应用启动时初始化数据库和 MCP 连接，关闭时执行清理操作。
    """
    # 启动时执行
    logger = get_logger("app.startup")
    logger.info(f"服务启动 | {settings.service_name} | 环境: {settings.environment}")
    logger.info(f"日志配置 | 级别: {settings.log_level} | 文件: {settings.log_file_enabled}")

    await init_db()
    await mcp_client.connect()  # 连接 supermemory MCP Server

    yield

    # 关闭时执行：断开 MCP 连接，关闭数据库连接池
    logger.info(f"服务关闭 | {settings.service_name}")
    await mcp_client.disconnect()
    await close_db()


# 获取配置
settings = get_settings()

# 创建 FastAPI 应用实例
_SERVICE_NAME = settings.service_name

app = FastAPI(
    title=f"{_SERVICE_NAME} API",
    version="0.1.0",
    description=(
        f"## {_SERVICE_NAME}\n\n"
        "基于 AI 的个性化夸夸生成服务，通过积极心理学方法论为用户生成真诚的赞美文案。\n\n"
        "### 认证方式\n\n"
        "| 请求头 | 说明 | 必填 |\n"
        "|--------|------|------|\n"
        "| `X-User-ID` | 用户标识，用于数据隔离和个性化服务 | 业务接口必填，未提供时默认 `anonymous` |\n"
        "| `X-Admin-Key` | 管理后台 API Key | 管理接口必填 |\n"
        "| `X-Trace-ID` | 请求追踪 ID，用于日志关联 | 可选 |\n\n"
        "### 登录方式\n\n"
        "小程序端调用 `wx.login()` 获取 `code`，请求 `POST /api/auth/login` 换取 `openid`，\n"
        "将返回的 `openid` 作为 `X-User-ID` 请求头发送后续请求。\n\n"
        "### 通用响应格式\n\n"
        "所有接口统一返回 `ApiResponse` 包装：\n\n"
        '```json\n'
        '{\n'
        '  "code": 0,\n'
        '  "message": "success",\n'
        '  "data": { ... }\n'
        '}\n'
        '```\n\n'
        "错误时 `code` 非 0，`data` 为 null。\n\n"
        "### 场景类型\n\n"
        "| 值 | 说明 |\n"
        "|----|------|\n"
        "| `general` | 通用场景（默认） |\n"
        "| `career` | 事业搞钱场景 |\n"
        "| `beauty` | 颜值气质场景 |\n"
        "| `love` | 甜蜜恋爱场景 |\n"
        "| `daily` | 日常治愈场景 |\n"
    ),
    lifespan=lifespan,
    docs_url="/docs",      # Swagger UI (默认)
    redoc_url="/redoc",    # ReDoc (备选方案)
    openapi_url="/openapi.json"  # OpenAPI schema
)

# 配置 CORS 中间件（前后端分离必需）
# 注意：allow_origins=["*"] 与 allow_credentials=True 不能同时使用
# 生产环境应配置具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议配置具体域名
    allow_credentials=False,  # 与 allow_origins=["*"] 不兼容，设为 False
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 注册日志中间件（必须在路由注册之前）
register_logging_middleware(app)

# 注册情绪检测中间件（仅对 /api/chat 路径生效）
app.add_middleware(EmotionMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
app.include_router(auth.router)
app.include_router(favorites.router)
app.include_router(chat.router)
app.include_router(asr.router)
app.include_router(admin.router)
app.include_router(memory.router)
app.include_router(emotion.router)


@app.get("/", tags=["首页"])
async def index():
    """首页 - 重定向到测试界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/test.html")


@app.get("/health", tags=["健康检查"])
async def health_check() -> dict[str, str]:
    """
    健康检查接口

    Returns:
        dict: 服务状态信息
    """
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": "0.1.0",
        "environment": settings.environment
    }


app.mount("/static", StaticFiles(directory="app/static", html=True), name="static")
