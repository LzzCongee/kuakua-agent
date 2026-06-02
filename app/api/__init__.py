"""
API 路由模块

导出所有 API 路由子模块，便于统一导入。
"""

from __future__ import annotations

from . import admin, chat, favorites, memory

__all__ = ["admin", "chat", "favorites", "memory"]
