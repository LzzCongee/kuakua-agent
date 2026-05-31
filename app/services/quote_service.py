"""
夸夸生成服务模块

提供夸夸语录的生成功能，支持通用随机生成和指定场景生成。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

from ..core.exceptions import AIServiceException
from ..core.logging import get_logger
from ..models.schemas import MemorySummary, QuoteResponse
from ..prompts.templates import (
    SceneType,
    get_prompt,
    get_scene_by_value,
)
from ..providers.base import AIProviderException, BaseAIProvider
from ..services.memory_service import MemoryService

logger = get_logger(__name__)


class QuoteService:
    """
    夸夸生成服务类

    封装夸夸语录的生成逻辑，支持多种场景和 AI Provider。

    Attributes:
        provider: AI Provider 实例，用于生成文案

    Example:
        >>> from app.providers.openai_compatible import OpenAICompatibleProvider
        >>> provider = OpenAICompatibleProvider(api_key="your-key", base_url="https://api.minimax.chat/v1")
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

    def _build_user_prompt(self, base_user_prompt: str, memory_summary: MemorySummary | None) -> str:
        """构建 user prompt，将记忆上下文放在 base 之前"""
        if not memory_summary:
            return base_user_prompt
        try:
            from app.services.memory import MemoryContext
            context = MemoryContext.from_memory_summary(memory_summary)
            memory_str = context.to_prompt_string()
            if memory_str:
                return f"{memory_str}\n\n{base_user_prompt}"
        except Exception:
            logger.warning("记忆上下文构建失败，使用 base prompt", exc_info=True)
        return base_user_prompt

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

            # 尝试获取用户偏好
            memory_summary = None
            if memory_service and user_id != "default":
                try:
                    memory_summary = await memory_service.get_memory_summary(user_id, None)
                except Exception:
                    logger.warning(f"记忆注入降级（随机夸夸）| user_id={user_id}", exc_info=True)

            # 构建 user prompt（记忆上下文拼入 user message，不注入 system_prompt）
            user_prompt = self._build_user_prompt(prompt["user"], memory_summary)

            content = await self.provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=100
            )

            return QuoteResponse(
                content=content,
                scene=SceneType.GENERAL.value,
                created_at=datetime.now(UTC)
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
            scene_type = SceneType.GENERAL

        try:
            prompt = get_prompt(scene_type)
            system_prompt = prompt["system"]

            # 尝试获取用户偏好
            memory_summary = None
            if memory_service and user_id != "default":
                try:
                    memory_summary = await memory_service.get_memory_summary(user_id, None)
                except Exception:
                    logger.warning(f"记忆注入降级（场景夸夸）| user_id={user_id} | scene={scene}", exc_info=True)

            # 构建 user prompt（记忆上下文拼入 user message，不注入 system_prompt）
            user_prompt = self._build_user_prompt(prompt["user"], memory_summary)

            content = await self.provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=100
            )

            return QuoteResponse(
                content=content,
                scene=scene_type.value,
                created_at=datetime.now(UTC)
            )
        except AIProviderException as e:
            raise AIServiceException(f"生成场景夸夸失败: {e.message}")
        except Exception as e:
            raise AIServiceException(f"生成场景夸夸时发生错误: {str(e)}")
