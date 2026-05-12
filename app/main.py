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

from app.api import admin, chat, favorites, memory, quotes
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import register_logging_middleware, get_logger
from app.core.mcp_client import mcp_client
from app.models.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理

    在应用启动时初始化数据库和 MCP 连接，关闭时执行清理操作。
    """
    # 启动时执行
    await init_db()
    await mcp_client.connect()  # 连接 supermemory MCP Server

    yield

    # 关闭时执行：断开 MCP 连接，关闭数据库连接池
    await mcp_client.disconnect()
    await close_db()


# 获取配置
settings = get_settings()

# 创建 FastAPI 应用实例
app = FastAPI(
    title=f"{settings.service_name} API",
    version="0.1.0",
    description=f"{settings.service_name} - 基于 AI 的夸夸生成服务",
    lifespan=lifespan,
    docs_url="/docs",      # Swagger UI (默认)
    redoc_url="/redoc",    # ReDoc (备选方案)
    openapi_url="/openapi.json"  # OpenAPI schema
)

# 配置 CORS 中间件（前后端分离必需）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境建议配置具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 注册日志中间件（必须在路由注册之前）
register_logging_middleware(app)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
app.include_router(quotes.router)
app.include_router(favorites.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(memory.router)


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


@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    logger = get_logger("app.startup")
    logger.info(f"服务启动 | {settings.service_name} | 环境: {settings.environment}")
    logger.info(f"日志配置 | 级别: {settings.log_level} | 文件: {settings.log_file_enabled}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理操作"""
    logger = get_logger("app.shutdown")
    logger.info(f"服务关闭 | {settings.service_name}")
