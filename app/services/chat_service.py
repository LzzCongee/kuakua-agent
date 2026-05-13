"""
交互式夸夸服务模块

提供基于文字和图片的多模态夸夸生成功能
支持记忆注入，实现个性化夸夸
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from ..models.schemas import ChatRequest, ChatResponse, MemorySummary, PromptContent
from ..providers.base import BaseAIProvider
from ..prompts.templates import get_chat_prompt

if TYPE_CHECKING:
    from ..services.memory_service import MemoryService


class ChatService:
    """
    交互式夸夸服务类
    
    处理用户发送的文字和图片，调用 AI 模型生成个性化的夸赞文案。
    支持纯文字、纯图片、图文混合三种输入模式。
    支持记忆注入，实现千人千面的个性化夸夸。
    
    Attributes:
        provider: AI Provider 实例，用于调用大模型
        vision_model: 视觉模型名称，用于处理图片输入
        memory_service: 可选的 MemoryService 实例，用于获取用户记忆
    """
    
    # 类属性类型注解
    provider: BaseAIProvider
    vision_model: str
    memory_service: MemoryService | None
    
    def __init__(
        self, 
        provider: BaseAIProvider, 
        vision_model: str,
        memory_service: MemoryService | None = None
    ):
        """
        初始化 ChatService
        
        Args:
            provider: AI Provider 实例
            vision_model: 视觉模型名称，用于处理图片输入
            memory_service: 可选的 MemoryService 实例
        """
        self.provider = provider
        self.vision_model = vision_model
        self.memory_service = memory_service
    
    async def chat(
        self, 
        request: ChatRequest, 
        prompt_override: PromptContent | None = None,
        memory_summary: MemorySummary | None = None
    ) -> ChatResponse:
        """
        处理用户输入，生成夸赞文案
        
        根据输入类型（纯文字、纯图片、图文混合）选择不同的处理方式，
        调用相应的 AI 模型生成个性化的夸赞内容。
        
        如果提供了 memory_summary，会将其注入到 system prompt 中，
        实现基于用户偏好的个性化夸夸。
        
        Args:
            request: 包含 text、image、scene 的请求对象
            prompt_override: 可选的 prompt 覆盖
            memory_summary: 可选的用户记忆汇总，用于注入个性化信息
            
        Returns:
            ChatResponse: 包含 AI 生成的夸夸文案
            
        Raises:
            AIProviderException: 当 AI 调用失败时抛出
        """
        # 判断输入类型
        has_text = bool(request.text and request.text.strip())
        has_image = bool(request.image and request.image.strip())
        
        if has_text and has_image:
            input_type: Literal["mixed", "image_only", "text_only"] = "mixed"
        elif has_image:
            input_type = "image_only"
        else:
            input_type = "text_only"
        
        # 获取对应的 system prompt
        if prompt_override:
            system_prompt = prompt_override["system"]
        else:
            prompt_template = get_chat_prompt(input_type)
            system_prompt = prompt_template["system"]
        
        # 注入记忆上下文
        if memory_summary:
            system_prompt = self._inject_memory(system_prompt, memory_summary)
        
        # 根据输入类型调用不同的生成方法
        if input_type == "text_only":
            # 根据逻辑，text_only 模式时 text 一定不为空
            assert request.text is not None
            content = await self._generate_text_only(system_prompt, request.text)
        else:
            content = await self._generate_multimodal(
                system_prompt, 
                request.text if has_text else None,
                request.image if has_image else None
            )
        
        return ChatResponse(
            content=content,
            scene=request.scene,
            has_image=has_image,
            created_at=datetime.now(timezone.utc)
        )
    
    def _inject_memory(self, system_prompt: str, memory: MemorySummary) -> str:
        """
        将用户记忆注入到 system prompt
        
        Args:
            system_prompt: 原始 system prompt
            memory: 用户记忆汇总
            
        Returns:
            str: 注入记忆后的 system prompt
        """
        parts: list[str] = []
        
        # 偏好场景和风格
        if memory.prefer_scene:
            parts.append(f"- 偏好场景：{memory.prefer_scene}")
        if memory.prefer_style:
            parts.append(f"- 喜欢风格：{memory.prefer_style}")
        
        # 用户标签
        if memory.user_tags:
            tags_str = ", ".join(memory.user_tags[:5])
            parts.append(f"- 用户标签：{tags_str}")
        
        # 最近情绪
        if memory.last_emotion:
            parts.append(f"- 当前情绪：{memory.last_emotion}")
        
        # 最近对话（用于保持上下文连贯）
        if memory.recent_messages:
            msg_list: list[str] = []
            for msg in memory.recent_messages[-3:]:
                role = str(msg.get("role", "user"))
                content = str(msg.get("content", ""))[:50]
                msg_list.append(f"{role}: {content}")
            if msg_list:
                parts.append(f"- 最近对话：{' | '.join(msg_list)}")
        
        # 高光里程碑（用于夸得真诚）
        if memory.milestones:
            milestones_str = "; ".join(memory.milestones[:3])
            parts.append(f"- 高光时刻：{milestones_str}")
        
        if not parts:
            return system_prompt
        
        memory_block = "\n".join(parts)
        return f"{system_prompt}\n\n【用户个性化信息】（请结合以下信息生成更贴合用户的夸夸）\n{memory_block}"
    
    async def _generate_text_only(self, system_prompt: str, text: str) -> str:
        """
        纯文字场景生成
        
        将 system prompt 和用户文字组合后调用 provider.generate()
        
        Args:
            system_prompt: 系统提示词
            text: 用户输入的文字
            
        Returns:
            str: AI 生成的文本内容
        """
        # 组合 system prompt 和用户文字
        full_prompt = f"{system_prompt}\n\n用户说：{text}"
        return await self.provider.generate(full_prompt)
    
    async def _generate_multimodal(
        self, 
        system_prompt: str, 
        text: str | None,
        image: str | None
    ) -> str:
        """
        多模态场景生成（含图片）
        
        组装 OpenAI Vision 格式的 messages，调用 provider.generate_multimodal()
        
        Args:
            system_prompt: 系统提示词
            text: 用户输入的文字（可选）
            image: 用户输入的图片 base64 数据（可选）
            
        Returns:
            str: AI 生成的文本内容
        """
        # 构建消息列表
        messages: list[dict[str, object]] = []
        
        # 添加 system message
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # 构建 user message content（支持多模态）
        user_content: list[dict[str, object]] = []
        
        # 添加文字内容（如果有）
        if text:
            user_content.append({
                "type": "text",
                "text": text
            })
        
        # 添加图片内容（如果有）
        if image:
            # 确保图片 base64 有 data URI 前缀
            image_url = self._ensure_data_uri(image)
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        
        # 添加 user message
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        # 调用多模态生成
        return await self.provider.generate_multimodal(
            messages=messages,
            model=self.vision_model
        )
    
    def _ensure_data_uri(self, image_data: str) -> str:
        """
        确保图片 base64 数据有 data URI 前缀
        
        如果用户传入的 base64 数据没有 data URI 前缀，自动添加。
        默认使用 image/jpeg 类型。
        
        Args:
            image_data: base64 编码的图片数据
            
        Returns:
            str: 带有 data URI 前缀的完整图片 URL
        """
        if image_data.startswith("data:image"):
            return image_data
        return f"data:image/jpeg;base64,{image_data}"
