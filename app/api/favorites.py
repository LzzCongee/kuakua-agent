"""
收藏接口路由模块

提供用户收藏夸夸语录的 REST API 接口，包括列表查询、添加、删除等功能。
"""

from fastapi import APIRouter, Depends
from typing import Annotated

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
    user_id: str = "default"
) -> ApiResponse[list[FavoriteResponse]]:
    """
    获取用户收藏列表
    
    查询指定用户的所有收藏记录，按创建时间倒序排列。
    
    Args:
        user_id: 用户标识，默认为 "default"
        
    Returns:
        ApiResponse[list[FavoriteResponse]]: 收藏列表的统一响应格式
        
    Example:
        >>> GET /api/favorites?user_id=default
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": [
        >>>         {
        >>>             "id": 1,
        >>>             "content": "你真棒！",
        >>>             "scene": "general",
        >>>             "created_at": "2024-01-15T10:30:00"
        >>>         }
        >>>     ]
        >>> }
    """
    favorites = await service.list_favorites(user_id=user_id)
    return ApiResponse(data=favorites)


@router.post("", response_model=ApiResponse[FavoriteResponse])
async def add_favorite(
    data: FavoriteCreate,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    user_id: str = "default"
) -> ApiResponse[FavoriteResponse]:
    """
    添加收藏记录
    
    为指定用户添加一条新的夸夸语录收藏。
    
    Args:
        data: 收藏创建数据，包含内容和场景
        user_id: 用户标识，默认为 "default"
        
    Returns:
        ApiResponse[FavoriteResponse]: 新创建收藏记录的统一响应格式
        
    Example:
        >>> POST /api/favorites?user_id=default
        >>> {
        >>>     "content": "你真棒！",
        >>>     "scene": "general"
        >>> }
        >>> 
        >>> Response:
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": {
        >>>         "id": 1,
        >>>         "content": "你真棒！",
        >>>         "scene": "general",
        >>>         "created_at": "2024-01-15T10:30:00"
        >>>     }
        >>> }
    """
    favorite = await service.add_favorite(user_id=user_id, data=data)
    return ApiResponse(data=favorite)


@router.delete("/{favorite_id}", response_model=ApiResponse)
async def delete_favorite(
    favorite_id: int,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    user_id: str = "default"
) -> ApiResponse:
    """
    删除单条收藏记录
    
    删除指定用户的特定收藏记录。
    
    Args:
        favorite_id: 收藏记录 ID
        user_id: 用户标识，默认为 "default"
        
    Returns:
        ApiResponse: 操作结果的统一响应格式
        
    Example:
        >>> DELETE /api/favorites/1?user_id=default
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": null
        >>> }
    """
    await service.delete_favorite(user_id=user_id, favorite_id=favorite_id)
    return ApiResponse(message="删除成功")


@router.delete("", response_model=ApiResponse)
async def clear_favorites(
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    user_id: str = "default"
) -> ApiResponse:
    """
    清空用户所有收藏
    
    删除指定用户的所有收藏记录。
    
    Args:
        user_id: 用户标识，默认为 "default"
        
    Returns:
        ApiResponse: 操作结果的统一响应格式，data 字段包含删除的记录数量
        
    Example:
        >>> DELETE /api/favorites?user_id=default
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": {
        >>>         "deleted_count": 5
        >>>     }
        >>> }
    """
    deleted_count = await service.clear_favorites(user_id=user_id)
    return ApiResponse(message="清空成功", data={"deleted_count": deleted_count})
