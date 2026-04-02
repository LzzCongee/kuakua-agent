"""
夸夸接口路由模块

提供夸夸语录生成的 REST API 接口。
"""

from fastapi import APIRouter, Depends, Query
from typing import Annotated, Literal

from app.models.schemas import ApiResponse, QuoteResponse
from app.services.quote_service import QuoteService
from app.providers.qwen import QwenProvider
from app.config import get_settings


# 创建路由实例
router = APIRouter(prefix="/api/quotes", tags=["夸夸生成"])


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


@router.get("/random", response_model=ApiResponse[QuoteResponse])
async def get_random_quote(
    service: Annotated[QuoteService, Depends(get_quote_service)]
) -> ApiResponse[QuoteResponse]:
    """
    获取随机夸夸语录
    
    生成一条通用的随机夸赞文案，适合日常鼓励使用。
    
    Returns:
        ApiResponse[QuoteResponse]: 包含夸夸内容的统一响应格式
        
    Example:
        >>> GET /api/quotes/random
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": {
        >>>         "content": "你今天的状态真好，像阳光一样温暖！",
        >>>         "scene": "general",
        >>>         "created_at": "2024-01-15T10:30:00"
        >>>     }
        >>> }
    """
    quote = await service.get_random_quote()
    return ApiResponse(data=quote)


@router.get("/scene", response_model=ApiResponse[QuoteResponse])
async def get_scene_quote(
    scene_type: Annotated[
        Literal["career", "beauty", "love", "daily"],
        Query(alias="type", description="场景类型: career, beauty, love, daily")
    ],
    service: Annotated[QuoteService, Depends(get_quote_service)]
) -> ApiResponse[QuoteResponse]:
    """
    获取指定场景的夸夸语录
    
    根据场景类型生成相应的夸赞文案，支持 career、beauty、love、daily 四种场景。
    如果传入无效的场景类型，会自动回退到通用场景。
    
    Args:
        scene_type: 场景类型，可选值：
            - career: 事业搞钱场景
            - beauty: 颜值气质场景
            - love: 甜蜜恋爱场景
            - daily: 日常治愈场景
            
    Returns:
        ApiResponse[QuoteResponse]: 包含夸夸内容的统一响应格式
        
    Example:
        >>> GET /api/quotes/scene?type=career
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": {
        >>>         "content": "你的努力一定会有回报，继续加油！",
        >>>         "scene": "career",
        >>>         "created_at": "2024-01-15T10:30:00"
        >>>     }
        >>> }
    """
    quote = await service.get_scene_quote(scene=scene_type)
    return ApiResponse(data=quote)
