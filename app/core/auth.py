"""
Admin API Key 认证中间件

通过 X-Admin-Key header 进行简单的 API Key 认证
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def verify_admin_key(
    x_admin_key: Annotated[str, Header(description="管理后台 API Key")],
) -> str:
    """
    验证 Admin API Key
    
    从请求头 X-Admin-Key 读取 key，与配置中的 admin_api_key 比对。
    
    Args:
        x_admin_key: 请求头中的 API Key
        
    Returns:
        str: 验证通过的 API Key
        
    Raises:
        HTTPException: 认证失败时抛出 401
    """
    settings = get_settings()
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Admin API Key",
        )
    return x_admin_key
