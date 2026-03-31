"""
SQLite 数据库管理模块

使用 aiosqlite 实现异步数据库操作，管理收藏表 favorites
"""

import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional


# 默认数据库路径
DEFAULT_DB_PATH = "./kuakua.db"


async def init_db(db_path: Optional[str] = None) -> None:
    """
    初始化数据库，创建 favorites 表
    
    Args:
        db_path: 数据库文件路径，默认为 "./kuakua.db"
    """
    path = db_path or DEFAULT_DB_PATH
    
    async with aiosqlite.connect(path) as db:
        # 创建 favorites 表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                content TEXT NOT NULL,
                scene TEXT NOT NULL DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: Optional[str] = None):
    """
    异步上下文管理器，获取数据库连接
    
    Args:
        db_path: 数据库文件路径，默认为 "./kuakua.db"
    
    Yields:
        aiosqlite.Connection: 数据库连接对象
    
    Example:
        async with get_db() as db:
            async with db.execute("SELECT * FROM favorites") as cursor:
                rows = await cursor.fetchall()
    """
    path = db_path or DEFAULT_DB_PATH
    async with aiosqlite.connect(path) as db:
        # 启用外键约束
        await db.execute("PRAGMA foreign_keys = ON")
        # 设置行工厂为 aiosqlite.Row，支持字典式访问
        db.row_factory = aiosqlite.Row
        yield db


async def get_db_connection(db_path: Optional[str] = None) -> aiosqlite.Connection:
    """
    获取数据库连接（非上下文管理器方式）
    
    注意：使用此函数后需要手动关闭连接
    
    Args:
        db_path: 数据库文件路径，默认为 "./kuakua.db"
    
    Returns:
        aiosqlite.Connection: 数据库连接对象
    """
    path = db_path or DEFAULT_DB_PATH
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db
