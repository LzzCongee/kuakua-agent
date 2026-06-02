"""
交互式夸夸服务模块

提供基于文字和图片的多模态夸夸生成功能
支持记忆注入，实现个性化夸夸
"""

from __future__ import annotations

import json
import random
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from ..config import ModelConfig
from ..core.logging import get_logger
from ..models.schemas import ChatRequest, ChatResponse, MemorySummary, PromptContent
from ..prompts.templates import get_chat_prompt, get_personality, get_random_mode_config, get_random_mode_prompt
from ..providers.base import BaseAIProvider

logger = get_logger(__name__)

# 负面情感关键词——检测到这些词时跳过随机模式
# 用户处于脆弱/负面情绪时，需要情感支持而非意外感
_NEGATIVE_EMOTION_KEYWORDS: set[str] = {
    "难过", "伤心", "哭了", "哭", "难受", "郁闷", "焦虑", "崩溃",
    "失望", "孤独", "寂寞", "委屈", "心累", "无助", "迷茫",
    "生气", "愤怒", "烦死了", "受不了", "讨厌",
    "压力大", "累死了", "好累", "疲惫", "失眠", "睡不着",
    "生病", "病了", "不舒服", "疼",
    "失败", "被骂", "裁员", "分手", "吵架", "被坑", "被骗",
    "没意思", "没劲", "算了", "就这样吧",
}

# 12 个固定 topic(LLM 强制从列表选)
# 设计依据: docs/greeting-topic-personalization-design-v2.md
ALLOWED_TOPICS: set[str] = {
    "general", "self_care", "self_love", "parenting",
    "career", "beauty", "love", "daily",
    "healing", "gratitude", "new_day", "rebuild",
}

# LLM 调用参数(降低温度 + 提升 max_tokens 以保证 JSON 输出完整)
CHAT_TEMPERATURE: float = 0.3
CHAT_MAX_TOKENS: int = 500


def _extract_first_balanced_json(text: str) -> str | None:
    """手写括号配对,找到第一个平衡的 {...} 块。
    处理字符串内花括号、转义符、嵌套对象。
    """
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_chat_response(raw: str) -> tuple[str, str]:
    """从 LLM 输出中解析 (reply, topic)。
    三级兜底: 严格 JSON → 平衡花括号提取 → 整段当 reply + general。
    topic 必须是 ALLOWED_TOPICS 之一,否则降级为 general。

    Returns:
        (reply_text, topic) — reply 永远非空,topic 是 12 个之一或 general
    """
    if not raw:
        return "", "general"
    raw = raw.strip()

    # 1) 严格 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            topic = obj.get("topic", "general")
            return obj["reply"], topic if topic in ALLOWED_TOPICS else "general"
    except json.JSONDecodeError:
        pass

    # 2) 平衡花括号提取(处理 markdown 围栏、嵌入文本等)
    candidate = _extract_first_balanced_json(raw)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "reply" in obj and "topic" in obj:
                topic = obj["topic"]
                return obj["reply"], topic if topic in ALLOWED_TOPICS else "general"
        except json.JSONDecodeError:
            pass

    # 3) 兜底: 整段当 reply,topic = general
    return raw, "general"


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

        如果提供了 memory_summary，会从中构建结构化记忆上下文，
        放入 user message 而非 system_prompt。

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

        # 获取 system prompt（干净，不含记忆上下文）
        if prompt_override:
            system_prompt = prompt_override["system"]
            logger.debug(f"使用外部传入 Prompt（AB测试/DB/模板）| scene={request.scene}")
        else:
            prompt_template = get_chat_prompt(input_type)
            system_prompt = prompt_template["system"]
            logger.debug(f"使用默认 Prompt | input_type={input_type}")

        # 人格注入(可选)— 拼到 system_prompt 末尾
        # 仅当 personality_prefer 非 default 时追加,确保基础模板稳定可缓存
        personality_used = (
            getattr(memory_summary, "personality_prefer", "default")
            if memory_summary else "default"
        )
        system_prompt = self._inject_personality(system_prompt, personality_used)

        # 构建记忆上下文（放入 user message，不注入 system_prompt）
        memory_context_str = ""
        if memory_summary:
            from app.services.memory import MemoryContext

            context = MemoryContext.from_memory_summary(memory_summary)
            memory_context_str = context.to_prompt_string()
            logger.debug(f"记忆上下文构建 | 场景={memory_summary.prefer_scene} | 标签数={len(memory_summary.user_tags)} | 里程碑数={len(memory_summary.milestones)}")
        else:
            logger.debug("无记忆上下文")

        logger.info(f"人格记录 | personality={personality_used} | tone_shift={getattr(memory_summary, 'tone_shift', False) if memory_summary else False}")

        # 判断是否使用随机模式
        random_mode_triggered = self._should_use_random_mode(request.text, memory_summary)
        if random_mode_triggered:
            logger.info(f"触发随机模式 | personality={personality_used} | mode_type={self._get_random_mode_type(memory_summary)}")
            content = await self._generate_random_mode(
                request.text or "",
                personality_used,
                getattr(memory_summary, 'humor_taste', None) if memory_summary else None,
            )
            return ChatResponse(
                content=content,
                scene=request.scene,
                has_image=has_image,
                image_desc=None,
                is_random_mode=True,
                created_at=datetime.now(UTC)
            )

        # 根据输入类型调用不同的生成方法
        image_desc = None
        topic = "general"
        if input_type == "text_only":
            text_content = request.text or ""
            logger.debug("开始纯文字生成")
            content, topic = await self._generate_text_only(system_prompt, text_content, memory_context_str)
            logger.debug(f"纯文字生成完成 | content_length={len(content)} | topic={topic}")
        else:
            logger.debug(f"开始多模态生成 | text={has_text} | image={has_image}")
            multimodal_result = await self._generate_multimodal(
                system_prompt,
                request.text if has_text else None,
                request.image if has_image else None,
                memory_context_str,
            )
            content = multimodal_result["content"]
            image_desc = multimodal_result.get("image_desc")
            topic = multimodal_result.get("topic", "general")
            logger.debug(f"多模态生成完成 | content_length={len(content)} | topic={topic} | has_desc={image_desc is not None}")

        return ChatResponse(
            content=content,
            scene=topic,  # 改用 LLM 自报 topic,不再用 request.scene
            has_image=has_image,
            image_desc=image_desc,
            created_at=datetime.now(UTC)
        )

    @staticmethod
    def _inject_personality(system_prompt: str, personality: str) -> str:
        """
        把用户人格偏好拼到 system_prompt 末尾(仅非 default 时)。

        设计依据: docs/greeting-personality-design.md §3.1.3
        - default / 空值 / 未知值: 不动 system_prompt(保持基础模板稳定可缓存)
        - witty/chill/enthusiastic: 追加【人格模式】块,带 tone 描述 + role 指令
        """
        if not personality or personality == "default":
            return system_prompt
        personality_data = get_personality(personality)
        if not personality_data:
            return system_prompt
        tone = personality_data.get("tone", personality)
        role = personality_data.get("role", "")
        if not role:
            return system_prompt
        return f"{system_prompt}\n\n【人格模式:{tone}】\n{role}"

    async def _generate_text_only(
        self, system_prompt: str, text: str, memory_context: str = ""
    ) -> tuple[str, str]:
        """
        纯文字场景生成

        system_prompt 通过 system role 传递，
        memory_context 拼入 user message（按结构化格式）。
        避免将 system_prompt 内容混入 user message。

        Args:
            system_prompt: 系统提示词（通过 system role 传递）
            text: 用户输入的文字
            memory_context: 结构化的记忆上下文（放入 user message）

        Returns:
            str: AI 生成的文本内容
        """
        if memory_context:
            user_prompt = f"{memory_context}\n\n用户说：{text}"
        else:
            user_prompt = f"用户说：{text}"
        logger.debug(f"调用 provider.generate | prompt_length={len(user_prompt)} | text_length={len(text)} | memory={bool(memory_context)}")
        raw = await self.provider.generate(
            user_prompt,
            system_prompt=system_prompt,
            temperature=CHAT_TEMPERATURE,
            max_tokens=CHAT_MAX_TOKENS,
        )

        if not raw or not raw.strip():
            logger.warning(f"AI 返回空内容,使用默认回复 | text={text[:30]}...")
            return "我是一个夸夸小助手,专注于发现你身上的闪光点~ 随时在听你分享。", "general"

        reply, topic = parse_chat_response(raw)
        logger.debug(f"JSON 解析 | topic={topic} | reply_len={len(reply)}")
        return reply, topic

    async def _generate_multimodal(
        self,
        system_prompt: str,
        text: str | None,
        image: str | None,
        memory_context: str = "",
    ) -> dict[str, str]:
        """
        多模态场景生成（含图片）

        组装 OpenAI Vision 格式的 messages，调用 provider.generate_multimodal()
        要求 AI 同时返回夸赞文案和图片描述（JSON 格式）。

        Args:
            system_prompt: 系统提示词
            text: 用户输入的文字（可选）
            image: 用户输入的图片 base64 数据（可选）
            memory_context: 结构化的记忆上下文（放入 user message 首段）

        Returns:
            dict: {"content": 夸赞文案, "image_desc": 图片描述或None}
        """
        # 在 system prompt 末尾追加 JSON 输出要求
        json_instruction = (
            "\n\n【输出格式要求】\n"
            "请严格按以下 JSON 格式返回,不要添加其他内容:\n"
            '{"compliment": "你的夸赞文案", "image_desc": "图片的简短客观描述(30字以内,用于记忆上下文)", '
            '"topic": "从以下 12 个话题中选最匹配的一个: general / self_care / self_love / parenting / '
            'career / beauty / love / daily / healing / gratitude / new_day / rebuild"}'
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

        # 记忆上下文作为首段文字（放在用户输入之前）
        if memory_context:
            user_content.append({
                "type": "text",
                "text": memory_context
            })

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

    def _parse_multimodal_response(self, raw: str) -> dict[str, str]:
        """
        解析多模态生成的 JSON 响应

        尝试从 AI 返回中提取 {"compliment": ..., "image_desc": ..., "topic": ...}。
        解析失败时将整个响应作为夸赞文案,image_desc 为 None,topic 用 general。

        Args:
            raw: AI 返回的原始文本

        Returns:
            dict: {"content": 夸赞文案, "image_desc": 图片描述或None, "topic": 12 话题之一}
        """
        text = raw.strip()

        def _build(data: dict) -> dict[str, str]:
            topic = str(data.get("topic", "general"))
            if topic not in ALLOWED_TOPICS:
                topic = "general"
            return {
                "content": str(data["compliment"]),
                "image_desc": str(data["image_desc"]) if data.get("image_desc") else None,
                "topic": topic,
            }

        # 尝试直接解析
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "compliment" in data:
                return _build(data)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块（AI 有时会包裹在 ```json ... ``` 中）
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and "compliment" in data:
                    return _build(data)
            except json.JSONDecodeError:
                pass

        # 降级：整个响应作为夸赞文案
        logger.debug(f"多模态响应 JSON 解析失败，降级为纯文本 | raw={text[:100]}")
        return {"content": text, "image_desc": None, "topic": "general"}

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

    def _should_use_random_mode(
        self,
        text: str | None,
        memory_summary: MemorySummary | None
    ) -> bool:
        """
        判断是否使用随机模式

        触发条件：
        1. 用户 query 中没有明显的求夸意图
        2. 未检测到负面情感关键词
        3. 30% 概率触发（可配置）
        """
        if not text or not text.strip():
            return False

        # 明显的求夸关键词
        obvious_praise_triggers = ["求夸", "夸夸我", "让我开心", "夸一下", "开心一下", "夸夸", "夸人"]
        for trigger in obvious_praise_triggers:
            if trigger in text:
                return False

        # 情感状态门控：检测负面情感关键词，脆弱情绪时跳过随机模式
        text_lower = text.lower()
        for keyword in _NEGATIVE_EMOTION_KEYWORDS:
            if keyword in text_lower:
                logger.debug(f"情感门控拦截随机模式 | keyword={keyword} | text={text[:50]}")
                return False

        # 获取配置
        config = get_random_mode_config()
        if not config.get("enabled", False):
            return False

        trigger_prob = config.get("trigger_probability", 0.3)

        # 按概率触发
        return random.random() < trigger_prob

    def _get_random_mode_type(self, memory_summary: MemorySummary | None) -> str:
        """
        获取随机模式的类型（用于日志记录）

        根据 humor_taste 返回会选择的随机模式类型。
        """
        humor_taste = getattr(memory_summary, 'humor_taste', None) if memory_summary else None

        distribution = [
            ("witty_teasing", 0.35),
            ("insightful", 0.35),
            ("meme", 0.05),
            ("ironic_warm", 0.25),
        ]

        if humor_taste == "chill":
            distribution = [
                ("witty_teasing", 0.15),
                ("insightful", 0.40),
                ("meme", 0.05),
                ("ironic_warm", 0.40),
            ]
        elif humor_taste == "teasing":
            distribution = [
                ("witty_teasing", 0.50),
                ("insightful", 0.20),
                ("meme", 0.05),
                ("ironic_warm", 0.25),
            ]

        rand = random.random()
        cumulative = 0.0
        selected_type = "ironic_warm"
        for mode_type, weight in distribution:
            cumulative += weight
            if rand <= cumulative:
                selected_type = mode_type
                break

        return selected_type

    async def _generate_random_mode(
        self,
        text: str,
        personality: str,
        humor_taste: str | None
    ) -> str:
        """
        生成随机模式的回复

        Args:
            text: 用户输入的文本
            personality: 人格类型（主导分布权重）
            humor_taste: 喜欢的幽默类型（微调分布）

        Returns:
            str: 随机模式生成的回复
        """
        # personality 主导分布，humor_taste 在此基础上微调
        personality_distributions = {
            "witty": [
                ("witty_teasing", 0.55),
                ("insightful", 0.25),
                ("meme", 0.05),
                ("ironic_warm", 0.15),
            ],
            "chill": [
                ("witty_teasing", 0.10),
                ("insightful", 0.50),
                ("meme", 0.05),
                ("ironic_warm", 0.35),
            ],
            "enthusiastic": [
                ("witty_teasing", 0.30),
                ("insightful", 0.30),
                ("meme", 0.15),
                ("ironic_warm", 0.25),
            ],
            "default": [
                ("witty_teasing", 0.35),
                ("insightful", 0.35),
                ("meme", 0.05),
                ("ironic_warm", 0.25),
            ],
        }

        distribution = personality_distributions.get(personality, personality_distributions["default"])

        # humor_taste 微调分布
        if humor_taste == "teasing":
            # 加强 witty_teasing
            distribution = [
                ("witty_teasing", min(d[1] + 0.20, 0.70)) if d[0] == "witty_teasing" else (d[0], max(d[1] - 0.05, 0.0))
                for d in distribution
            ]
            # 重新归一化
            total = sum(w for _, w in distribution)
            distribution = [(t, w / total) for t, w in distribution]
        elif humor_taste == "chill":
            # 加强 insightful
            distribution = [
                ("insightful", min(d[1] + 0.20, 0.60)) if d[0] == "insightful" else (d[0], max(d[1] - 0.05, 0.0))
                for d in distribution
            ]
            total = sum(w for _, w in distribution)
            distribution = [(t, w / total) for t, w in distribution]

        # 按权重随机选择
        rand = random.random()
        cumulative = 0.0
        selected_type = "ironic_warm"
        for mode_type, weight in distribution:
            cumulative += weight
            if rand <= cumulative:
                selected_type = mode_type
                break

        # 生成 prompt 并调用
        mode_prompt = get_random_mode_prompt(selected_type, text, personality)
        logger.debug(f"随机模式生成 | type={selected_type} | personality={personality} | humor={humor_taste}")

        try:
            content = await self.provider.generate(mode_prompt)
            if content and content.strip():
                return content
        except Exception as e:
            logger.warning(f"随机模式生成失败，降级为默认回复 | error={e}")

        # 降级：返回默认回复
        return "今天想说点什么？我在听~"

    async def generate_greeting(
        self,
        user_type: str,
        memory_summary: MemorySummary | None = None,
        last_topic: str | None = None,
    ) -> str:
        """
        根据用户类型和时间间隔生成主动问候

        用户类型决定了问候的语气和内容：
        - new_user: 首次打开，引导式夸夸
        - light_return: 5min~24h 再次打开，简单问候
        - medium_frequency: 24h~7d 未互动，日常问候
        - low_frequency: >7 天未互动，回归问候
        - high_frequency: <24h 不触发

        All greetings must end with an open question to guide user toward sharing.
        """
        # 构建场景描述——所有 prompt 强制要求以问句结尾，引导用户倾诉
        type_prompts = {
            "new_user": (
                "用户是第一次打开夸夸助手，还完全不知道这个产品能做什么。"
                "请先简要说明自己的角色和价值（可以听分享、给鼓励、陪聊天），再发一句温暖的欢迎语。"
                "一定要让用户清楚地知道：这里是一个可以聊开心事、吐露烦恼、或者随便说说话的安全空间。"
                "以一句简单的开放式问题结尾，让用户有话可说。"
            ),
            "light_return": (
                "用户5分钟到24小时前刚来过，请发一句简单的'回来啦'问候，自然不刻意。"
                "结尾带一个开放式问题，像朋友看到你回来时随口问一句近况。"
            ),
            "medium_frequency": (
                "用户上次来是1-7天前，请发一句日常问候。"
                "结尾用一个具体的开放式问题引导用户分享近况。"
            ),
            "low_frequency": (
                "用户很久没来了（超过7天），请发一句想念式的回归问候。"
                "结尾引导用户分享这段时间的经历，让用户感到被惦记。"
            ),
        }
        scene_desc = type_prompts.get(user_type, type_prompts["medium_frequency"])

        # 构建记忆上下文（让问候有「它记得我」的感觉）
        memory_lines: list[str] = []
        if memory_summary:
            tags = memory_summary.user_tags or []
            if tags:
                memory_lines.append(f"用户标签：{', '.join(tags)}")
            milestones = memory_summary.milestones or []
            if milestones:
                memory_lines.append(f"用户高光：{'；'.join(milestones[:2])}")
            if memory_summary.prefer_scene:
                memory_lines.append(f"偏好场景：{memory_summary.prefer_scene}")

            # topic 偏好(来自收藏聚合,衰减权重后的 lead topics)
            # 强偏好话题:用 lead topic 直接做"上次聊到",避免被 last_topic 覆盖
            topic_pref = getattr(memory_summary, "topic_preference", None)
            if topic_pref:
                lead_topics = topic_pref.get("topics") or []
                if lead_topics:
                    lead = lead_topics[0]
                    topic_name = lead.get("topic", "")
                    intensity = lead.get("intensity", "weak")
                    if topic_name and topic_name != "general":
                        total = topic_pref.get("total_likes", 0) or 0
                        count = lead.get("count", 0) or 0
                        # 纯主动声明(count=0)不显示"累计 0 次",与 context_builder 5 区块语义一致
                        if total > 0:
                            memory_lines.append(
                                f"用户偏好话题:{topic_name}(强度 {intensity}, 累计 {total} 次)"
                            )
                        elif count == 0 and lead.get("declared"):
                            memory_lines.append(
                                f"用户主动关注话题:{topic_name}(强度 {intensity})"
                            )
                        else:
                            memory_lines.append(
                                f"用户偏好话题:{topic_name}(强度 {intensity})"
                            )

        # 如果上次对话有具体话题，优先使用话题上下文
        if last_topic:
            memory_lines.append(f"上次聊到：{last_topic}")

        memory_context = "\n".join(memory_lines) if memory_lines else ""

        # 人格注入:基础问候 prompt + 用户人格偏好(若非 default)
        personality_used = (
            getattr(memory_summary, "personality_prefer", "default")
            if memory_summary else "default"
        )
        base_greeting_prompt = "你是一个温暖真诚的朋友。请根据用户情况和记忆信息，发一句简短的主动问候。必须要以问句结尾，自然引导对方分享。"
        system_prompt = self._inject_personality(base_greeting_prompt, personality_used)
        if personality_used != "default":
            logger.info(f"问候应用人格 | personality={personality_used}")

        prompt_parts = [f"用户类型：{user_type}"]
        if memory_context:
            prompt_parts.append(memory_context)
        prompt_parts.append(scene_desc)
        prompt_parts.append(
            "要求：20字以内，口语化，像朋友发微信。必须以问句结尾——让对方忍不住想接着说下去。"
            "根据用户类型决定是否使用适当的表情符号。"
        )
        prompt = "\n".join(prompt_parts)

        try:
            content = await self.provider.generate(prompt, system_prompt=system_prompt)
            if content and content.strip():
                return content
        except Exception as e:
            logger.warning(f"问候生成失败，使用默认回复 | error={e}")

        # 降级默认回复（全部以问句结尾，引导用户继续说下去）
        defaults = {
            "new_user": "嗨～我是夸夸助手，当你开心时可以一起笑，低落时给你打打气，也可以就随便聊聊天。今天想聊点什么？😊",
            "light_return": "回来啦～刚才在忙什么呢？",
            "medium_frequency": "今天过得怎么样？有没有什么新鲜事想聊聊？",
            "low_frequency": "好久不见～最近过得怎么样？我很想知道你过得好不好✨",
        }
        return defaults.get(user_type, "今天想说点什么？我在听～")
