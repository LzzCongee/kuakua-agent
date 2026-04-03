"""
夸夸生成服务模块

提供夸夸语录的生成功能，支持通用随机生成和指定场景生成。
"""

from datetime import datetime
from typing import Literal

from app.models.schemas import QuoteResponse
from app.providers.base import BaseAIProvider, AIProviderException
from app.prompts.templates import (
    SceneType, 
    get_prompt, 
    get_scene_by_value,
    SYSTEM_PROMPTS,
    USER_PROMPTS
)
from app.core.exceptions import AIServiceException


class QuoteService:
    """
    夸夸生成服务类
    
    封装夸夸语录的生成逻辑，支持多种场景和 AI Provider。
    
    Attributes:
        provider: AI Provider 实例，用于生成文案
        
    Example:
        >>> from app.providers.qwen import QwenProvider
        >>> provider = QwenProvider(api_key="your-key")
        >>> service = QuoteService(provider)
        >>> quote = await service.get_random_quote()
    """
    
    def __init__(self, provider: BaseAIProvider):
        """
        初始化夸夸生成服务
        
        Args:
            provider: AI Provider 实例，用于调用大模型生成文案
        """
        self.provider = provider
    
    async def get_random_quote(self) -> QuoteResponse:
        """
        生成通用随机夸夸
        
        使用 GENERAL 场景的 Prompt 模板生成一条随机的夸赞文案。
        
        Returns:
            QuoteResponse: 包含夸夸内容、场景标签和创建时间的响应对象
            
        Raises:
            AIServiceException: 当 AI 服务调用失败时抛出
        """
        try:
            prompt = get_prompt(SceneType.GENERAL)
            content = await self.provider.generate(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                temperature=0.8,
                max_tokens=100
            )
            
            return QuoteResponse(
                content=content,
                scene=SceneType.GENERAL.value,
                created_at=datetime.now()
            )
        except AIProviderException as e:
            raise AIServiceException(f"生成随机夸夸失败: {e.message}")
        except Exception as e:
            raise AIServiceException(f"生成随机夸夸时发生错误: {str(e)}")
    
    async def get_scene_quote(
        self,
        scene: Literal["career", "beauty", "love", "daily", "general"],
    ) -> QuoteResponse:
        """
        生成指定场景的夸夸
        
        根据用户指定的场景类型生成相应的夸赞文案。
        如果场景参数无效，自动回退到通用场景。
        
        Args:
            scene: 场景类型字符串，可选值：career, beauty, love, daily
            
        Returns:
            QuoteResponse: 包含夸夸内容、场景标签和创建时间的响应对象
            
        Raises:
            AIServiceException: 当 AI 服务调用失败时抛出
        """
        # 尝试解析场景类型，无效则使用通用场景
        try:
            scene_type = get_scene_by_value(scene)
        except ValueError:
            # 无效场景，回退到通用场景
            scene_type = SceneType.GENERAL
        
        try:
            prompt = get_prompt(scene_type)
            content = await self.provider.generate(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                temperature=0.8,
                max_tokens=100
            )
            
            return QuoteResponse(
                content=content,
                scene=scene_type.value,
                created_at=datetime.now()
            )
        except AIProviderException as e:
            raise AIServiceException(f"生成场景夸夸失败: {e.message}")
        except Exception as e:
            raise AIServiceException(f"生成场景夸夸时发生错误: {str(e)}")
