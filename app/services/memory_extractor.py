"""
混合记忆提取引擎

三层提取策略：
1. 关键词快速匹配（<1ms，兜底）
2. LLM 结构化提取（200-500ms，主力）
3. 降级为无提取（不影响主流程）

单次 LLM 调用同时提取：情绪、偏好标签、里程碑、场景倾向
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..config import get_settings
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..providers.base import BaseAIProvider

logger = get_logger(__name__)

# ==================== 提取 Prompt ====================

EXTRACTION_SYSTEM_PROMPT = """你是一个记忆提取助手。分析用户消息和AI回复，提取结构化信息。

返回严格JSON格式，不要任何解释：
{
  "has_milestone": false,
  "milestone_content": null,
  "milestone_importance": 0,
  "emotion": "neutral",
  "emotion_intensity": 0.5,
  "tags": [],
  "scene_hint": null,
  "avoid_words": []
}

字段说明：
- has_milestone: 用户是否提到了自己的成就、进步、突破
- milestone_content: 成就的简短描述（20字以内），无成就时为null
- milestone_importance: 1-5，1=小事，5=人生大事
- emotion: 用户当前情绪，用一个词描述（开心/焦虑/疲惫/平静/兴奋/低落/自信/迷茫...）
- emotion_intensity: 0-1，情绪强度
- tags: 从对话中提取的用户标签（职业、兴趣、状态等），最多3个
- scene_hint: 推断场景 career/beauty/love/daily/null
- avoid_words: 用户表达反感的词汇，没有则为空数组

注意：
- 只提取用户明确表达或强烈暗示的信息，不要过度推断
- "还行""一般""凑合"这类模糊表达，emotion应为"neutral"
- 反讽、自嘲（"我真是个天才"在失败语境下）不要误判为正面情绪"""

# ==================== 关键词配置 ====================

# 成就关键词
ACHIEVEMENT_KEYWORDS = [
    "完成", "达成", "通过", "拿到", "获得", "坚持", "成功",
    "突破", "进步", "提升", "搞定", "拿下", "上岸", "过线",
    "录用", "offer", "录取", "升职", "加薪", "获奖",
]

# 否定前缀（用于排除误判，如"没有完成"）
NEGATION_PREFIXES = ["没有", "没", "不", "未", "还没"]

# 情绪关键词映射
EMOTION_KEYWORDS: dict[str, list[str]] = {
    "开心": ["开心", "高兴", "快乐", "爽", "太好了", "哈哈", "嘿嘿", "好开心"],
    "焦虑": ["焦虑", "紧张", "担心", "怕", "慌", "压力大", "不安"],
    "疲惫": ["累", "疲惫", "加班", "熬夜", "撑不住", "倦", "好困"],
    "低落": ["难过", "丧", "低落", "不开心", "烦", "郁闷", "emo"],
    "自信": ["自信", "有底气", "感觉不错", "稳了", "有把握"],
    "兴奋": ["兴奋", "激动", "期待", "迫不及待", "太棒了"],
    "迷茫": ["迷茫", "不知道", "纠结", "选择困难", "不确定"],
}


@dataclass
class ExtractionResult:
    """记忆提取结果"""
    has_milestone: bool = False
    milestone_content: str | None = None
    milestone_importance: int = 0
    emotion: str = "neutral"
    emotion_intensity: float = 0.5
    tags: list[str] = field(default_factory=list)
    scene_hint: str | None = None
    avoid_words: list[str] = field(default_factory=list)
    source: str = "keyword"  # "keyword" | "llm" | "none"


class MemoryExtractor:
    """
    混合记忆提取引擎

    使用策略：
    1. 关键词快速匹配（兜底，always-on）
    2. LLM 结构化提取（主力，可配置关闭）
    3. 降级为无提取（异常时自动降级）

    Args:
        provider: AI Provider 实例（可选，不传则只用关键词）
        enabled: 是否启用 LLM 提取
        keyword_fallback: 是否启用关键词兜底
        temperature: LLM 采样温度
        max_tokens: LLM 最大输出 token
    """

    def __init__(
        self,
        provider: BaseAIProvider | None = None,
        enabled: bool = True,
        keyword_fallback: bool = True,
        temperature: float = 0.1,
        max_tokens: int = 200,
    ):
        self.provider = provider
        self.enabled = enabled
        self.keyword_fallback = keyword_fallback
        self.temperature = temperature
        self.max_tokens = max_tokens

    @classmethod
    def from_settings(cls, provider: BaseAIProvider | None = None) -> MemoryExtractor:
        """从全局配置创建实例，provider 为 None 时自动使用 settings.ai_extract 构造"""
        settings = get_settings()
        if provider is None:
            from ..providers.openai_compatible import OpenAICompatibleProvider
            provider = OpenAICompatibleProvider.from_config(settings.ai_extract)
        return cls(
            provider=provider,
            enabled=settings.ai_extract_enabled,
            keyword_fallback=settings.ai_extract_keyword_fallback,
            temperature=settings.ai_extract_temperature,
            max_tokens=settings.ai_extract_max_tokens,
        )

    async def extract(
        self,
        user_message: str,
        ai_response: str = "",
    ) -> ExtractionResult:
        """
        从对话中提取记忆信息

        流程：关键词匹配 → (未命中且启用LLM) → LLM提取 → (失败) → 降级

        Args:
            user_message: 用户消息
            ai_response: AI 回复（可选，用于上下文）

        Returns:
            ExtractionResult: 提取结果
        """
        # 第1层：关键词快速匹配
        if self.keyword_fallback:
            keyword_result = self._extract_by_keywords(user_message)
            if keyword_result.has_milestone:
                logger.info(f"关键词命中里程碑 | content={keyword_result.milestone_content}")
                return keyword_result
            # 关键词未命中里程碑，但可能有情绪命中
            if keyword_result.emotion != "neutral":
                logger.debug(f"关键词命中情绪 | emotion={keyword_result.emotion}")
                # 情绪命中了，但里程碑没命中，继续尝试 LLM 提取里程碑
                if self.enabled and self.provider:
                    llm_result = await self._extract_by_llm(user_message, ai_response)
                    if llm_result:
                        # 合并：LLM 的里程碑 + 关键词的情绪（关键词情绪更确定）
                        llm_result.emotion = keyword_result.emotion
                        llm_result.emotion_intensity = keyword_result.emotion_intensity
                        return llm_result
                return keyword_result

        # 第2层：LLM 结构化提取
        if self.enabled and self.provider:
            llm_result = await self._extract_by_llm(user_message, ai_response)
            if llm_result:
                return llm_result

        # 第3层：降级为无提取
        logger.debug("提取降级为无操作")
        return ExtractionResult(source="none")

    def _extract_by_keywords(self, text: str) -> ExtractionResult:
        """关键词快速匹配提取"""
        result = ExtractionResult(source="keyword")

        # 里程碑检测（带否定排除）
        for keyword in ACHIEVEMENT_KEYWORDS:
            if keyword in text:
                # 检查是否被否定（如"没有完成"）
                idx = text.index(keyword)
                prefix = text[max(0, idx - 3):idx]
                if any(neg in prefix for neg in NEGATION_PREFIXES):
                    logger.debug(f"关键词被否定排除 | keyword={keyword} | prefix={prefix}")
                    continue
                result.has_milestone = True
                result.milestone_content = text[:20]
                result.milestone_importance = 2
                break

        # 情绪检测
        for emotion, keywords in EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    result.emotion = emotion
                    result.emotion_intensity = 0.7
                    break
            if result.emotion != "neutral":
                break

        return result

    async def _extract_by_llm(
        self,
        user_message: str,
        ai_response: str,
    ) -> ExtractionResult | None:
        """LLM 结构化提取"""
        try:
            prompt = f"用户说：{user_message}"
            if ai_response:
                prompt += f"\nAI回复：{ai_response}"

            raw = await self.provider.generate(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # 解析 JSON（容错处理）
            result = self._parse_llm_output(raw)
            if result:
                result.source = "llm"
                logger.info(
                    f"LLM 提取成功 | emotion={result.emotion} | "
                    f"milestone={result.has_milestone} | tags={result.tags}"
                )
            return result

        except Exception:
            logger.warning("LLM 提取失败，降级为无提取", exc_info=True)
            return None

    def _parse_llm_output(self, raw: str) -> ExtractionResult | None:
        """解析 LLM 输出的 JSON（容错处理）"""
        # 尝试直接解析
        try:
            data = json.loads(raw.strip())
            return self._dict_to_result(data)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块（LLM 有时会包裹在 ```json ... ``` 中）
        match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return self._dict_to_result(data)
            except json.JSONDecodeError:
                pass

        logger.warning(f"LLM 输出 JSON 解析失败 | raw={raw[:200]}")
        return None

    def _dict_to_result(self, data: dict) -> ExtractionResult:
        """将字典转换为 ExtractionResult"""
        return ExtractionResult(
            has_milestone=bool(data.get("has_milestone", False)),
            milestone_content=data.get("milestone_content"),
            milestone_importance=int(data.get("milestone_importance", 0)),
            emotion=str(data.get("emotion", "neutral")),
            emotion_intensity=float(data.get("emotion_intensity", 0.5)),
            tags=list(data.get("tags", []))[:3],
            scene_hint=data.get("scene_hint"),
            avoid_words=list(data.get("avoid_words", [])),
        )
