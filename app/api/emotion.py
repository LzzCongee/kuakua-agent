"""
情绪管理 API

提供情绪检测接口，用于：
1. 文本情绪检测（规则引擎）
2. 语音/图片情绪分析（LLM，需接入）
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.logging import get_logger, get_trace_id
from app.services.emotion import EmotionDetector, EmotionType, emotion_detector

router = APIRouter(prefix="/api/emotion", tags=["情绪管理"])
logger = get_logger(__name__)


class EmotionDetectRequest(BaseModel):
    """情绪检测请求"""
    text: str = Field(..., min_length=1, description="待检测文本")


class EmotionDetectResponse(BaseModel):
    """情绪检测响应"""
    emotion: str = Field(description="情绪类型 (happy/excited/exhausted/sad/frustrated/calm)")
    intensity: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    keywords: list[str] = Field(default_factory=list, description="触发关键词")
    style_guidance: str = Field(description="生成风格指导建议")


@router.post("/detect", response_model=EmotionDetectResponse)
async def detect_emotion(request: EmotionDetectRequest) -> EmotionDetectResponse:
    """
    检测文本情绪（规则引擎）

    使用关键词匹配检测文本情绪，适用于文字输入。
    语音/图片输入的情绪分析需要接入 LLM（待实现）。

    Returns:
        情绪检测结果，包含类型、置信度、关键词和建议
    """
    trace_id = get_trace_id()
    result = emotion_detector.detect(request.text)

    # 根据情绪类型给出风格指导
    style_guidance = emotion_detector.get_style_guidance(result.emotion)

    logger.info(
        f"[{trace_id}] 情绪检测 API | text={request.text[:30]}... | "
        f"emotion={result.emotion.value} | intensity={result.intensity:.2f}"
    )

    return EmotionDetectResponse(
        emotion=result.emotion.value,
        intensity=result.intensity,
        keywords=result.keywords,
        style_guidance=style_guidance,
    )


@router.get("/types")
async def get_emotion_types() -> dict:
    """
    获取支持的情绪类型列表

    Returns:
        6 种核心情绪类型
    """
    return {
        "types": [
            {"value": e.value, "description": _get_emotion_description(e)}
            for e in EmotionType
        ]
    }


def _get_emotion_description(emotion: EmotionType) -> str:
    """获取情绪类型的中文描述"""
    descriptions = {
        EmotionType.HAPPY: "开心、高兴、快乐",
        EmotionType.EXCITED: "兴奋、激动、超赞",
        EmotionType.EXHAUSTED: "疲惫、累、困",
        EmotionType.SAD: "难过、伤心、失落",
        EmotionType.FRUSTRATED: "烦躁、生气、郁闷",
        EmotionType.CALM: "平静、淡定、还好",
    }
    return descriptions.get(emotion, "")