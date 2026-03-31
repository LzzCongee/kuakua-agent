"""
API 路由模块

导出所有 API 路由子模块，便于统一导入。
"""

from app.api import quotes, favorites

__all__ = ["quotes", "favorites"]
