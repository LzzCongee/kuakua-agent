"""
收藏接口路由模块

提供用户收藏夸夸语录的 REST API 接口，包括列表查询、添加、删除等功能。

请求头说明：
- X-User-ID: 用户标识（用于数据隔离）
- X-Trace-ID: 请求追踪 ID（可选，用于日志关联）
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database import get_session
from app.models.schemas import ApiResponse, FavoriteCreate, FavoriteResponse
from app.services.favorite_service import FavoriteService

# 获取日志记录器
logger = get_logger(__name__)


# 创建路由实例
router = APIRouter(prefix="/api/favorites", tags=["收藏管理"])


def get_favorite_service() -> FavoriteService:
    """
    获取 FavoriteService 实例（依赖注入工厂函数）
    
    Returns:
        FavoriteService: 配置好的收藏管理服务实例
    """
    return FavoriteService()


async def get_user_id_from_header(
    x_user_id: Annotated[
        Optional[str],
        Header(description="用户标识，用于数据隔离")
    ] = "anonymous"
) -> str:
    """从请求头获取用户 ID"""
    return x_user_id or "anonymous"


@router.get("", response_model=ApiResponse[list[FavoriteResponse]])
async def list_favorites(
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
) -> ApiResponse[list[FavoriteResponse]]:
    """
    获取用户收藏列表
    
    查询指定用户的所有收藏记录，按创建时间倒序排列。
    
    请求头：
        X-User-ID: 用户标识
    """
    logger.info(f"获取收藏列表 | user_id={user_id}")
    
    favorites = await service.list_favorites(user_id=user_id, session=session)
    
    logger.info(f"收藏列表获取完成 | user_id={user_id} | count={len(favorites)}")
    
    return ApiResponse(data=favorites)


@router.post("", response_model=ApiResponse[FavoriteResponse])
async def add_favorite(
    data: FavoriteCreate,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
) -> ApiResponse[FavoriteResponse]:
    """
    添加收藏记录
    
    为指定用户添加一条新的夸夸语录收藏。
    
    请求头：
        X-User-ID: 用户标识
    """
    logger.info(f"添加收藏 | user_id={user_id} | scene={data.scene}")
    
    favorite = await service.add_favorite(user_id=user_id, data=data, session=session)
    
    logger.info(f"收藏添加完成 | user_id={user_id} | favorite_id={favorite.id}")
    
    return ApiResponse(data=favorite)


@router.delete("/{favorite_id}", response_model=ApiResponse)
async def delete_favorite(
    favorite_id: int,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
) -> ApiResponse:
    """
    删除单条收藏记录
    
    删除指定用户的特定收藏记录。
    
    请求头：
        X-User-ID: 用户标识
    """
    logger.info(f"删除收藏 | user_id={user_id} | favorite_id={favorite_id}")
    
    await service.delete_favorite(user_id=user_id, favorite_id=favorite_id, session=session)
    
    logger.info(f"收藏删除完成 | user_id={user_id} | favorite_id={favorite_id}")
    
    return ApiResponse(message="删除成功")


@router.delete("", response_model=ApiResponse)
async def clear_favorites(
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
) -> ApiResponse:
    """
    清空用户所有收藏
    
    删除指定用户的所有收藏记录。
    
    请求头：
        X-User-ID: 用户标识
    """
    logger.info(f"清空收藏 | user_id={user_id}")
    
    deleted_count = await service.clear_favorites(user_id=user_id, session=session)
    
    logger.info(f"收藏清空完成 | user_id={user_id} | deleted_count={deleted_count}")
    
    return ApiResponse(message="清空成功", data={"deleted_count": deleted_count})
