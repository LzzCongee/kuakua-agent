"""
夸夸接口路由模块

提供夸夸语录生成的 REST API 接口。

请求头说明：
- X-User-ID: 用户标识（用于数据隔离和个性化服务）
- X-Trace-ID: 请求追踪 ID（可选，用于日志关联）
"""

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, Query

from app.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import ApiResponse, QuoteResponse
from app.providers.qwen import QwenProvider
from app.services.quote_service import QuoteService
from app.services.memory_service import MemoryService
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_session

# 获取日志记录器
logger = get_logger(__name__)


# 创建路由实例
router = APIRouter(prefix="/api/quotes", tags=["夸夸生成"])


def get_memory_service(session: AsyncSession = Depends(get_session)) -> MemoryService:
    """获取 MemoryService 实例"""
    return MemoryService(session)


def get_quote_service() -> QuoteService:
    """
    获取 QuoteService 实例（依赖注入工厂函数）
    
    创建并配置 QuoteService，使用配置中的 API Key 初始化 QwenProvider。
    
    Returns:
        QuoteService: 配置好的夸夸生成服务实例
    """
    settings = get_settings()
    provider = QwenProvider(
        api_key=settings.modelscope_api_key,
        base_url=settings.ai_base_url,
        model=settings.ai_model
    )
    return QuoteService(provider)


async def get_user_id_from_header(
    x_user_id: Annotated[
        Optional[str],
        Header(description="用户标识，用于数据隔离和个性化服务")
    ] = "anonymous"
) -> str:
    """从请求头获取用户 ID"""
    return x_user_id or "anonymous"


@router.get("/random", response_model=ApiResponse[QuoteResponse])
async def get_random_quote(
    service: Annotated[QuoteService, Depends(get_quote_service)],
    memory_service: MemoryService = Depends(get_memory_service),
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
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
    service: Annotated[QuoteService, Depends(get_quote_service)],
    memory_service: MemoryService = Depends(get_memory_service),
    user_id: Annotated[str, Depends(get_user_id_from_header)] = "anonymous",
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
