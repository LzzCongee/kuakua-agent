"""
情绪检测服务

负责从文本中识别情绪状态。使用规则 + 关键词双重检测，保证准确性和召回率。

适用于文字输入的情绪检测。语音/图片输入由 EmotionAnalyzer（对接豆包 4.0 Lite）处理。
"""

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from ...core.logging import get_logger

logger = get_logger(__name__)


class EmotionType(StrEnum):
    """
    情绪类型枚举（与 PRD 一致）

    6 种核心情绪：开心、兴奋、疲惫、难过、烦躁、平静
    """
    HAPPY = "happy"           # 开心
    EXCITED = "excited"       # 兴奋
    EXHAUSTED = "exhausted"   # 疲惫
    SAD = "sad"               # 难过
    FRUSTRATED = "frustrated"  # 烦躁
    CALM = "calm"             # 平静


class EmotionResult(BaseModel):
    """
    情绪检测结果

    使用 Pydantic 校验确保类型安全。
    """
    emotion: EmotionType = Field(description="情绪类型")
    intensity: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    keywords: list[str] = Field(default_factory=list, description="触发关键词")
    text: str = Field(default="", description="原始文本")


class EmotionDetector:
    """
    情绪检测器（规则引擎版本）

    用于文本输入的情绪检测。语音/图片输入由 EmotionAnalyzer 处理。
    规则引擎 <1ms 延迟，可作为 LLM 提取的兜底方案。

    检测策略：
    1. 规则匹配：关键词正则匹配，计算得分
    2. 置信度计算：命中越多 intensity 越高
    3. 未命中或空输入时默认返回 calm
    """

    # 情绪关键词映射（与 PRD 6 种情绪一致）
    EMOTION_PATTERNS: dict[EmotionType, list[str]] = {
        EmotionType.HAPPY: [
            r"开心|高兴|快乐|棒|厉害|赞|优秀|完美|好开心",
            r"太好了|不错|挺棒的|真不错|太好了"
        ],
        EmotionType.EXCITED: [
            r"激动|兴奋|超赞|炸裂|太厉害了|绝了",
            r"飙升|沸腾|简直了|太牛了|太棒了"
        ],
        EmotionType.EXHAUSTED: [
            r"累|困|疲惫|辛苦了|好困|没精神|熬夜",
            r"熬|通宵|秃了|快累死了|撑不住了|心累"
        ],
        EmotionType.SAD: [
            r"难过|伤心|哭|委屈|不甘心|失落",
            r"沮丧|郁闷|惆怅|忧伤|心塞|想哭"
        ],
        EmotionType.FRUSTRATED: [
            r"烦躁|生气|恼火|郁闷|烦死了",
            r"崩溃|心态崩|想发火|气死了|不爽"
        ],
        EmotionType.CALM: [
            r"平静|淡定|还好|一般|普通",
            r"没什么|就那样|正常|还行|凑合"
        ]
    }

    # 否定前缀（用于排除误判，如"没有完成"）
    NEGATION_PREFIXES: list[str] = ["没有", "没", "不", "未", "不是", "别", "不要"]

    def detect(self, text: str) -> EmotionResult:
        """
        检测文本的情绪类型

        Args:
            text: 用户输入文本

        Returns:
            EmotionResult: 情绪检测结果
        """
        if not text or not text.strip():
            return EmotionResult(
                emotion=EmotionType.CALM,
                intensity=0.5,
                keywords=[],
                text=""
            )

        text_lower = text.lower()
        emotion_scores: dict[EmotionType, tuple[int, list[str]]] = {}

        # 1. 规则匹配
        for emotion, patterns in self.EMOTION_PATTERNS.items():
            score = 0
            matched_keywords: list[str] = []

            for pattern in patterns:
                # 检查是否有否定前缀在关键词前
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    # 简单否定检测：查找 match 前的 3 个字符
                    idx = text_lower.find(match)
                    if idx >= 0:
                        prefix = text_lower[max(0, idx - 3):idx]
                        # 如果有否定前缀，跳过这个匹配
                        if any(neg in prefix for neg in self.NEGATION_PREFIXES):
                            logger.debug(f"否定前缀排除 | emotion={emotion.value} | match={match} | prefix={prefix}")
                            continue
                    score += 1
                    matched_keywords.append(match)

            if score > 0:
                emotion_scores[emotion] = (score, matched_keywords)

        # 2. 确定主要情绪
        if emotion_scores:
            # 取得分最高的情绪
            main_emotion = max(emotion_scores.items(), key=lambda x: x[1][0])
            emotion_type = main_emotion[0]
            matched_kw = main_emotion[1][1]
            # 置信度：基础 0.5 + 得分 * 0.1，最高 1.0
            intensity = min(0.5 + main_emotion[1][0] * 0.1, 1.0)
        else:
            emotion_type = EmotionType.CALM
            matched_kw = []
            intensity = 0.5

        logger.info(
            f"情绪检测 | text={text[:50]}... | "
            f"emotion={emotion_type.value} | intensity={intensity:.2f}"
        )

        return EmotionResult(
            emotion=emotion_type,
            intensity=intensity,
            keywords=matched_kw,
            text=text
        )

    def get_style_guidance(self, emotion: EmotionType) -> str:
        """
        根据情绪类型返回生成风格指导

        Args:
            emotion: 情绪类型

        Returns:
            str: 风格指导建议
        """
        if emotion in [EmotionType.EXHAUSTED, EmotionType.SAD, EmotionType.FRUSTRATED]:
            return "温柔安慰，缓解情绪，再适当鼓励"
        elif emotion == EmotionType.EXCITED:
            return "热情共鸣，分享喜悦"
        elif emotion == EmotionType.HAPPY:
            return "积极回应，延续好心情"
        else:
            return "正常夸赞风格"


# 全局单例（无状态，可复用）
emotion_detector = EmotionDetector()