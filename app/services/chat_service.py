"""
交互式夸夸服务模块

提供基于文字和图片的多模态夸夸生成功能
"""

from datetime import datetime
from typing import Literal

from app.models.schemas import ChatRequest, ChatResponse
from app.providers.base import BaseAIProvider
from app.prompts.templates import get_chat_prompt


class ChatService:
    """
    交互式夸夸服务类
    
    处理用户发送的文字和图片，调用 AI 模型生成个性化的夸赞文案。
    支持纯文字、纯图片、图文混合三种输入模式。
    
    Attributes:
        provider: AI Provider 实例，用于调用大模型
        vision_model: 视觉模型名称，用于处理图片输入
    """
    
    def __init__(self, provider: BaseAIProvider, vision_model: str):
        """
        初始化 ChatService
        
        Args:
            provider: AI Provider 实例
            vision_model: 视觉模型名称，用于处理图片输入
        """
        self.provider = provider
        self.vision_model = vision_model
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        处理用户输入，生成夸赞文案
        
        根据输入类型（纯文字、纯图片、图文混合）选择不同的处理方式，
        调用相应的 AI 模型生成个性化的夸赞内容。
        
        Args:
            request: 包含 text、image、scene 的请求对象
            
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
        prompt_template = get_chat_prompt(input_type)
        system_prompt = prompt_template["system"]
        
        # 根据输入类型调用不同的生成方法
        if input_type == "text_only":
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
            created_at=datetime.now()
        )
    
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
        messages = []
        
        # 添加 system message
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # 构建 user message content（支持多模态）
        user_content = []
        
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
