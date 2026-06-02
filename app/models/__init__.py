"""
数据模型模块

提供数据库管理和 Pydantic 模型定义
"""

from .database import close_db, get_db, get_session, init_db
from .models import Base, Favorite, User
from .schemas import (
    ApiResponse,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    FavoriteCreate,
    FavoriteResponse,
    LoginRequest,
    RegisterRequest,
)

__all__ = [
    # 数据库相关
    "init_db",
    "close_db",
    "get_db",
    "get_session",
    # ORM 模型
    "Base",
    "Favorite",
    "User",
    # Pydantic 模型
    "FavoriteCreate",
    "FavoriteResponse",
    "ApiResponse",
    "ChatRequest",
    "ChatResponse",
    # 认证
    "RegisterRequest",
    "LoginRequest",
    "AuthResponse",
]
