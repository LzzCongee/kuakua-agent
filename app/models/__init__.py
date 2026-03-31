"""
数据模型模块

提供数据库管理和 Pydantic 模型定义
"""

from .database import init_db, get_db, get_db_connection, DEFAULT_DB_PATH
from .schemas import (
    QuoteResponse,
    FavoriteCreate,
    FavoriteResponse,
    ApiResponse,
)

__all__ = [
    # 数据库相关
    "init_db",
    "get_db",
    "get_db_connection",
    "DEFAULT_DB_PATH",
    # 模型相关
    "QuoteResponse",
    "FavoriteCreate",
    "FavoriteResponse",
    "ApiResponse",
]
