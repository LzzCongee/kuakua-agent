"""
交互式夸夸服务模块

提供基于文字和图片的多模态夸夸生成功能
支持记忆注入，实现个性化夸夸
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from ..config import ModelConfig
from ..core.logging import get_logger
from ..models.schemas import ChatRequest, ChatResponse, MemorySummary, PromptContent
from ..prompts.templates import get_chat_prompt
from ..providers.base import BaseAIProvider

logger = get_logger(__name__)

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
    _vision_config: ModelConfig
    memory_service: MemoryService | None

    def __init__(
        self,
        provider: BaseAIProvider,
        vision_config: ModelConfig,
        memory_service: MemoryService | None = None
    ):
        """
        初始化 ChatService

        Args:
            provider: AI Provider 实例
            vision_config: 视觉模型配置（包含 model、api_key 等）
            memory_service: 可选的 MemoryService 实例
        """
        self.provider = provider
        self._vision_config = vision_config
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
        
        logger.debug(f"输入类型判定 | has_text={has_text} | has_image={has_image} | input_type={input_type}")
        
        # 获取对应的 system prompt
        if prompt_override:
            system_prompt = prompt_override["system"]
            logger.debug(f"使用 AB 测试 Prompt | scene={request.scene}")
        else:
            prompt_template = get_chat_prompt(input_type)
            system_prompt = prompt_template["system"]
            logger.debug(f"使用默认 Prompt | input_type={input_type}")
        
        # 注入记忆上下文
        if memory_summary:
            system_prompt = self._inject_memory(system_prompt, memory_summary)
            logger.debug(f"记忆注入完成 | 场景={memory_summary.prefer_scene} | 标签数={len(memory_summary.user_tags)} | 里程碑数={len(memory_summary.milestones)}")
        else:
            logger.debug("无记忆注入")
        
        # 根据输入类型调用不同的生成方法
        image_desc = None
        if input_type == "text_only":
            # 根据逻辑，text_only 模式时 text 一定不为空
            assert request.text is not None
            logger.debug("开始纯文字生成")
            content = await self._generate_text_only(system_prompt, request.text)
            logger.debug(f"纯文字生成完成 | content_length={len(content)}")
        else:
            logger.debug(f"开始多模态生成 | text={has_text} | image={has_image}")
            multimodal_result = await self._generate_multimodal(
                system_prompt,
                request.text if has_text else None,
                request.image if has_image else None
            )
            content = multimodal_result["content"]
            image_desc = multimodal_result.get("image_desc")
            logger.debug(f"多模态生成完成 | content_length={len(content)} | has_desc={image_desc is not None}")

        return ChatResponse(
            content=content,
            scene=request.scene,
            has_image=has_image,
            image_desc=image_desc,
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
        
        # 最近对话（用于保持上下文连贯，按完整轮次拼接）
        if memory.recent_messages:
            from datetime import datetime as _dt
            msg_list: list[str] = []
            msgs = memory.recent_messages
            last_assistant_idx = None
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].get("role") == "assistant":
                    last_assistant_idx = i
                    break
            if last_assistant_idx is not None:
                start = max(0, last_assistant_idx - 1)
                first_msg = msgs[start]
                ts = first_msg.get("timestamp", "")
                time_str = ""
                if ts:
                    try:
                        dt = _dt.fromisoformat(ts)
                        time_str = f"({dt.strftime('%H:%M')}) "
                    except (ValueError, TypeError):
                        pass
                for idx, msg in enumerate(msgs[start:last_assistant_idx + 1]):
                    role = "用户" if msg.get("role") == "user" else "夸夸"
                    content = str(msg.get("content") or "")[:80]
                    prefix = time_str if idx == 0 else ""
                    msg_list.append(f"{prefix}{role}：{content}")
            if msg_list:
                parts.append(f"- 最近对话：{' | '.join(msg_list)}")
        
        # 高光里程碑（用于夸得真诚）
        if memory.milestones:
            milestones_str = "; ".join(memory.milestones[:3])
            parts.append(f"- 高光时刻：{milestones_str}")
        
        if not parts:
            logger.debug("记忆注入: 无内容可注入")
            return system_prompt

        memory_block = "\n".join(parts)
        logger.debug(f"记忆注入: 最终注入内容 | {memory_block[:300]}")
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
        logger.debug(f"调用 provider.generate | prompt_length={len(full_prompt)} | text_length={len(text)}")
        return await self.provider.generate(full_prompt)
    
    async def _generate_multimodal(
        self,
        system_prompt: str,
        text: str | None,
        image: str | None
    ) -> dict[str, str | None]:
        """
        多模态场景生成（含图片）

        组装 OpenAI Vision 格式的 messages，调用 provider.generate_multimodal()
        要求 AI 同时返回夸赞文案和图片描述（JSON 格式）。

        Args:
            system_prompt: 系统提示词
            text: 用户输入的文字（可选）
            image: 用户输入的图片 base64 数据（可选）

        Returns:
            dict: {"content": 夸赞文案, "image_desc": 图片描述或None}
        """
        # 在 system prompt 末尾追加 JSON 输出要求
        json_instruction = (
            "\n\n【输出格式要求】\n"
            "请严格按以下 JSON 格式返回，不要添加其他内容：\n"
            '{"compliment": "你的夸赞文案", "image_desc": "图片的简短客观描述（30字以内，用于记忆上下文）"}'
        )
        full_system_prompt = system_prompt + json_instruction

        # 构建消息列表
        messages: list[dict[str, object]] = []

        # 添加 system message
        messages.append({
            "role": "system",
            "content": full_system_prompt
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
            logger.debug(f"图片处理完成 | has_data_uri_prefix={image.startswith('data:image')}")

        # 添加 user message
        messages.append({
            "role": "user",
            "content": user_content
        })

        # 调用多模态生成
        logger.debug(f"调用 provider.generate_multimodal | messages_count={len(messages)} | 模型={self._vision_config.model}")
        raw = await self.provider.generate_multimodal(
            messages=messages,
            model=self._vision_config.model
        )

        # 解析 JSON 响应，提取夸赞文案和图片描述
        return self._parse_multimodal_response(raw)
    
    def _parse_multimodal_response(self, raw: str) -> dict[str, str | None]:
        """
        解析多模态生成的 JSON 响应

        尝试从 AI 返回中提取 {"compliment": ..., "image_desc": ...}。
        解析失败时将整个响应作为夸赞文案，image_desc 为 None。

        Args:
            raw: AI 返回的原始文本

        Returns:
            dict: {"content": 夸赞文案, "image_desc": 图片描述或None}
        """
        text = raw.strip()

        # 尝试直接解析
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "compliment" in data:
                return {
                    "content": str(data["compliment"]),
                    "image_desc": str(data["image_desc"]) if data.get("image_desc") else None,
                }
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块（AI 有时会包裹在 ```json ... ``` 中）
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and "compliment" in data:
                    return {
                        "content": str(data["compliment"]),
                        "image_desc": str(data["image_desc"]) if data.get("image_desc") else None,
                    }
            except json.JSONDecodeError:
                pass

        # 降级：整个响应作为夸赞文案
        logger.debug(f"多模态响应 JSON 解析失败，降级为纯文本 | raw={text[:100]}")
        return {"content": text, "image_desc": None}

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
