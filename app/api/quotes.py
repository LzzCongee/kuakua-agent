"""
夸夸接口路由模块

提供夸夸语录生成的 REST API 接口。

请求头说明：
- X-User-ID: 用户标识（用于数据隔离和个性化服务）
- X-Trace-ID: 请求追踪 ID（可选，用于日志关联）
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.dependencies import HeaderUserID
from ..core.logging import get_logger
from ..models.database import get_session
from ..models.schemas import ApiResponse, QuoteResponse
from ..providers.openai_compatible import OpenAICompatibleProvider
from ..services.memory_service import MemoryService
from ..services.quote_service import QuoteService

# 获取日志记录器
logger = get_logger(__name__)


# 创建路由实例
router = APIRouter(prefix="/api/quotes", tags=["夸夸生成"])


def get_memory_service(session: Annotated[AsyncSession, Depends(get_session)]) -> MemoryService:
    """获取 MemoryService 实例"""
    return MemoryService(session)


def get_quote_service() -> QuoteService:
    """
    获取 QuoteService 实例（依赖注入工厂函数）
    
    创建并配置 QuoteService，使用配置中的 API Key 初始化 Provider。

    Returns:
        QuoteService: 配置好的夸夸生成服务实例
    """
    settings = get_settings()
    provider = OpenAICompatibleProvider.from_config(settings.ai_chat)
    return QuoteService(provider)


# ---------- 依赖注入类型别名 ----------
QuoteServiceDep = Annotated[QuoteService, Depends(get_quote_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]


@router.get("/random", response_model=ApiResponse[QuoteResponse])
async def get_random_quote(
    service: QuoteServiceDep,
    memory_service: MemoryServiceDep,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[QuoteResponse]:
    """
    获取随机夸夸语录
    
    生成一条通用的随机夸赞文案，适合日常鼓励使用。
    支持根据用户历史偏好生成个性化夸夸。
    
    请求头：
        X-User-ID: 用户标识（用于加载用户偏好）
        X-Trace-ID: 请求追踪 ID（可选）
    """
    logger.info(f"获取随机夸夸 | user_id={user_id}")
    
    quote = await service.get_random_quote(user_id, memory_service)
    
    logger.info(f"随机夸夸生成完成 | user_id={user_id} | scene={quote.scene}")
    
    return ApiResponse(data=quote)


@router.get("/scene", response_model=ApiResponse[QuoteResponse])
async def get_scene_quote(
    scene_type: Annotated[
        Literal["career", "beauty", "love", "daily"],
        Query(alias="type", description="场景类型: career, beauty, love, daily")
    ],
    service: QuoteServiceDep,
    memory_service: MemoryServiceDep,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[QuoteResponse]:
    """
    获取指定场景的夸夸语录
    
    根据场景类型生成相应的夸赞文案，支持 career、beauty、love、daily 四种场景。
    如果传入无效的场景类型，会自动回退到通用场景。
    支持根据用户历史偏好生成个性化夸夸。
    
    请求头：
        X-User-ID: 用户标识（用于加载用户偏好）
        X-Trace-ID: 请求追踪 ID（可选）
    """
    logger.info(f"获取场景夸夸 | user_id={user_id} | scene={scene_type}")
    
    quote = await service.get_scene_quote(scene=scene_type, user_id=user_id, memory_service=memory_service)
    
    logger.info(f"场景夸夸生成完成 | user_id={user_id} | scene={quote.scene}")
    
    return ApiResponse(data=quote)
