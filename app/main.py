"""
夸夸Agent API 主入口
FastAPI 应用初始化与配置
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, chat, favorites, quotes
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.models.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理
    
    在应用启动时初始化数据库，关闭时执行清理操作。
    """
    # 启动时执行
    await init_db()
    yield
    # 关闭时执行：关闭数据库连接池
    await close_db()


# 创建 FastAPI 应用实例
app = FastAPI(
    title="夸夸 Agent API",
    version="0.1.0",
    description="一个基于 AI 的夸夸生成服务",
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

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
app.include_router(quotes.router)
app.include_router(favorites.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/health", tags=["健康检查"])
async def health_check() -> dict[str, str]:
    """
    健康检查接口

    Returns:
        dict: 服务状态信息
    """
    return {
        "status": "healthy",
        "service": "夸夸Agent API",
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True  # 开发模式启用热重载
    )
