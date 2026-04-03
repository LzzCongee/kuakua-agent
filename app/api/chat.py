"""
交互式夸夸接口路由模块

提供基于文字和图片的多模态夸夸生成 REST API 接口
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.models.schemas import ApiResponse, ChatRequest, ChatResponse
from app.providers.qwen import QwenProvider
from app.services.chat_service import ChatService


# 创建路由实例
router = APIRouter(prefix="/api/chat", tags=["交互式夸夸"])


def get_chat_service() -> ChatService:
    """
    获取 ChatService 实例（依赖注入工厂函数）
    
    创建并配置 ChatService，使用配置中的 API Key 初始化 QwenProvider。
    
    Returns:
        ChatService: 配置好的交互式夸夸服务实例
    """
    settings = get_settings()
    provider = QwenProvider(
        api_key=settings.modelscope_api_key,
        base_url=settings.ai_base_url,
        model=settings.ai_model
    )
    return ChatService(
        provider=provider,
        vision_model=settings.ai_vision_model
    )


@router.post("", response_model=ApiResponse[ChatResponse])
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)]
) -> ApiResponse[ChatResponse]:
    """
    交互式夸夸接口
    
    接收用户发送的文字和/或图片，生成个性化的夸赞文案。
    支持三种输入模式：
    - 纯文字：用户分享心情、经历或想法
    - 纯图片：用户发送照片获得夸赞
    - 图文混合：用户发送文字+图片的组合
    
    Args:
        request: 包含 text（文字）、image（base64图片）、scene（场景）的请求体
        
    Returns:
        ApiResponse[ChatResponse]: 包含 AI 生成夸赞文案的统一响应格式
        
    Example:
        >>> POST /api/chat
        >>> {
        >>>     "text": "今天完成了一个重要项目！",
        >>>     "scene": "career"
        >>> }
        >>> 
        >>> Response:
        >>> {
        >>>     "code": 0,
        >>>     "message": "success",
        >>>     "data": {
        >>>         "content": "太棒了！完成重要项目的你真的很厉害，这种执行力值得骄傲！",
        >>>         "scene": "career",
        >>>         "has_image": false,
        >>>         "created_at": "2024-01-15T10:30:00"
        >>>     }
        >>> }
    """
    response = await service.chat(request)
    return ApiResponse(data=response)
