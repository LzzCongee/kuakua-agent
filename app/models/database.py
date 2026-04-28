"""
PostgreSQL 数据库管理模块

使用 asyncpg + SQLAlchemy 实现异步数据库操作
支持 PostgreSQL（生产）和 SQLite（开发回退）
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# 全局引擎和会话工厂，在 init_db 时初始化
_engine = None
_session_factory = None


def _get_database_url() -> str:
    """获取数据库连接 URL"""
    settings = get_settings()
    return settings.database_url


def _is_postgresql(url: str) -> bool:
    """判断是否为 PostgreSQL 连接"""
    return url.startswith("postgresql") or url.startswith("postgres")


def _convert_to_asyncpg_url(url: str) -> str:
    """
    将 postgresql:// 转换为 postgresql+asyncpg://
    
    支持用户在 .env 中写 postgresql:// 或 postgresql+asyncpg://
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def init_db(db_url: Optional[str] = None) -> None:
    """
    初始化数据库，创建所有表
    
    Args:
        db_url: 数据库连接 URL，默认从配置读取
    """
    global _engine, _session_factory
    
    url = db_url or _get_database_url()
    
    if _is_postgresql(url):
        async_url = _convert_to_asyncpg_url(url)
        _engine = create_async_engine(
            async_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    else:
        # SQLite 回退（开发环境）
        _engine = create_async_engine(
            url.replace("sqlite:///", "sqlite+aiosqlite:///"),
            echo=False,
        )
    
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # 确保 ORM 模型被导入，这样 create_all 才能创建对应的表
    import app.models.models  # noqa: F401

    # 创建所有表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（FastAPI 依赖注入用）
    
    Yields:
        AsyncSession: 数据库会话对象
    """
    if _session_factory is None:
        await init_db()
    
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    异步上下文管理器，获取数据库会话
    
    兼容旧代码风格，内部使用 SQLAlchemy AsyncSession
    
    Yields:
        AsyncSession: 数据库会话对象
    """
    if _session_factory is None:
        await init_db()
    
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """关闭数据库连接池（应用关闭时调用）"""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
