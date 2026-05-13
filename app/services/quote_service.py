"""
夸夸生成服务模块

提供夸夸语录的生成功能，支持通用随机生成和指定场景生成。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from ..models.schemas import QuoteResponse
from ..providers.base import BaseAIProvider, AIProviderException
from ..prompts.templates import (
    SceneType, 
    get_prompt, 
    get_scene_by_value,
    SYSTEM_PROMPTS,
    USER_PROMPTS
)
from ..core.exceptions import AIServiceException
from ..core.logging import get_logger
from ..services.memory_service import MemoryService
from ..models.schemas import MemorySummary

logger = get_logger(__name__)


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
    
    async def get_random_quote(
        self, 
        user_id: str = "default",
        memory_service: Optional[MemoryService] = None
    ) -> QuoteResponse:
        """
        生成通用随机夸夸
        
        使用 GENERAL 场景的 Prompt 模板生成一条随机的夸赞文案。
        如果提供了用户上下文，会尝试注入用户偏好生成个性化夸夸。
        
        Args:
            user_id: 用户ID，用于获取用户偏好
            memory_service: 记忆服务实例，用于获取用户偏好
            
        Returns:
            QuoteResponse: 包含夸夸内容、场景标签和创建时间的响应对象
            
        Raises:
            AIServiceException: 当 AI 服务调用失败时抛出
        """
        try:
            prompt = get_prompt(SceneType.GENERAL)
            system_prompt = prompt["system"]
            
            # 尝试注入用户偏好
            memory_summary = None
            if memory_service and user_id != "default":
                try:
                    memory_summary = await memory_service.get_memory_summary(user_id, None)
                except Exception:
                    logger.warning(f"记忆注入降级（随机夸夸）| user_id={user_id}", exc_info=True)
            
            # 如果有用户偏好，注入到 system prompt
            if memory_summary:
                system_prompt = self._inject_memory_to_prompt(system_prompt, memory_summary)
            
            content = await self.provider.generate(
                prompt=prompt["user"],
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=100
            )
            
            return QuoteResponse(
                content=content,
                scene=SceneType.GENERAL.value,
                created_at=datetime.now(timezone.utc)
            )
        except AIProviderException as e:
            raise AIServiceException(f"生成随机夸夸失败: {e.message}")
        except Exception as e:
            raise AIServiceException(f"生成随机夸夸时发生错误: {str(e)}")
    
    async def get_scene_quote(
        self,
        scene: Literal["career", "beauty", "love", "daily", "general"],
        user_id: str = "default",
        memory_service: Optional[MemoryService] = None
    ) -> QuoteResponse:
        """
        生成指定场景的夸夸
        
        根据用户指定的场景类型生成相应的夸赞文案。
        如果场景参数无效，自动回退到通用场景。
        如果提供了用户上下文，会尝试注入用户偏好生成个性化夸夸。
        
        Args:
            scene: 场景类型字符串，可选值：career, beauty, love, daily
            user_id: 用户ID，用于获取用户偏好
            memory_service: 记忆服务实例，用于获取用户偏好
            
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
            system_prompt = prompt["system"]
            
            # 尝试注入用户偏好
            memory_summary = None
            if memory_service and user_id != "default":
                try:
                    memory_summary = await memory_service.get_memory_summary(user_id, None)
                except Exception:
                    logger.warning(f"记忆注入降级（场景夸夸）| user_id={user_id} | scene={scene}", exc_info=True)
            
            # 如果有用户偏好，注入到 system prompt
            if memory_summary:
                system_prompt = self._inject_memory_to_prompt(system_prompt, memory_summary)
            
            content = await self.provider.generate(
                prompt=prompt["user"],
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=100
            )
            
            return QuoteResponse(
                content=content,
                scene=scene_type.value,
                created_at=datetime.now(timezone.utc)
            )
        except AIProviderException as e:
            raise AIServiceException(f"生成场景夸夸失败: {e.message}")
        except Exception as e:
            raise AIServiceException(f"生成场景夸夸时发生错误: {str(e)}")
    
    def _inject_memory_to_prompt(self, system_prompt: str, memory: MemorySummary) -> str:
        """
        将用户记忆注入到 system prompt
        
        Args:
            system_prompt: 原始 system prompt
            memory: 用户记忆汇总
            
        Returns:
            str: 注入记忆后的 system prompt
        """
        parts = []
        
        # 偏好场景
        if memory.prefer_scene:
            parts.append(f"- 偏好场景：{memory.prefer_scene}")
        
        # 喜欢的风格
        if memory.prefer_style:
            parts.append(f"- 喜欢风格：{memory.prefer_style}")
        
        # 用户标签
        if memory.user_tags:
            tags_str = ", ".join(memory.user_tags[:5])
            parts.append(f"- 用户标签：{tags_str}")
        
        # 高光里程碑
        if memory.milestones:
            milestones_str = "; ".join(memory.milestones[:2])
            parts.append(f"- 高光时刻：{milestones_str}")
        
        if not parts:
            return system_prompt
        
        memory_block = "\n".join(parts)
        return f"{system_prompt}\n\n【用户偏好信息】（请结合以下信息生成更贴合用户的夸夸）\n{memory_block}"
