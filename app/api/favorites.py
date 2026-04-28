"""
收藏接口路由模块

提供用户收藏夸夸语录的 REST API 接口，包括列表查询、添加、删除等功能。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.models.schemas import ApiResponse, FavoriteCreate, FavoriteResponse
from app.services.favorite_service import FavoriteService


# 创建路由实例
router = APIRouter(prefix="/api/favorites", tags=["收藏管理"])


def get_favorite_service() -> FavoriteService:
    """
    获取 FavoriteService 实例（依赖注入工厂函数）
    
    Returns:
        FavoriteService: 配置好的收藏管理服务实例
    """
    return FavoriteService()


@router.get("", response_model=ApiResponse[list[FavoriteResponse]])
async def list_favorites(
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Query(description="用户标识")] = "default"
) -> ApiResponse[list[FavoriteResponse]]:
    """
    获取用户收藏列表
    
    查询指定用户的所有收藏记录，按创建时间倒序排列。
    """
    favorites = await service.list_favorites(user_id=user_id, session=session)
    return ApiResponse(data=favorites)


@router.post("", response_model=ApiResponse[FavoriteResponse])
async def add_favorite(
    data: FavoriteCreate,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Query(description="用户标识")] = "default"
) -> ApiResponse[FavoriteResponse]:
    """
    添加收藏记录
    
    为指定用户添加一条新的夸夸语录收藏。
    """
    favorite = await service.add_favorite(user_id=user_id, data=data, session=session)
    return ApiResponse(data=favorite)


@router.delete("/{favorite_id}", response_model=ApiResponse)
async def delete_favorite(
    favorite_id: int,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Query(description="用户标识")] = "default"
) -> ApiResponse:
    """
    删除单条收藏记录
    
    删除指定用户的特定收藏记录。
    """
    await service.delete_favorite(user_id=user_id, favorite_id=favorite_id, session=session)
    return ApiResponse(message="删除成功")


@router.delete("", response_model=ApiResponse)
async def clear_favorites(
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Query(description="用户标识")] = "default"
) -> ApiResponse:
    """
    清空用户所有收藏
    
    删除指定用户的所有收藏记录。
    """
    deleted_count = await service.clear_favorites(user_id=user_id, session=session)
    return ApiResponse(message="清空成功", data={"deleted_count": deleted_count})
