"""
ASR 语音识别 API 接口

提供语音转文字 REST API 接口。
前端录音后发送 base64 音频，后端返回转写文本。

请求头说明：
- X-User-ID: 用户标识（必填）
- X-Trace-ID: 请求追踪 ID（可选）
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.dependencies import HeaderUserID
from app.models.schemas import ApiResponse
from app.services.asr import ASRException, ASRResult, get_asr_provider

logger = logging.getLogger(__name__)

# 创建路由实例
router: APIRouter = APIRouter(prefix="/api/asr", tags=["语音识别"])


# ========== Schemas ==========


class ASRRequest(BaseModel):
    """ASR 请求模型"""

    audio: str
    format: str = "mp3"


class ASRResponse(BaseModel):
    """ASR 响应模型"""

    model_config = {"arbitrary_types_allowed": True}

    text: str
    emotion: str | None = None
    confidence: float | None = None

    @classmethod
    def from_result(cls, result: ASRResult) -> "ASRResponse":
        return cls(
            text=result.text,
            emotion=result.emotion,
            confidence=result.confidence,
        )


# ========== Routes ==========


@router.post("")
async def speech_to_text(
    request: ASRRequest,
    with_emotion: Annotated[bool, Query(description="是否返回情绪信息")] = False,
    user_id: HeaderUserID = None,
) -> ApiResponse[ASRResponse]:
    """
    语音转文字接口

    接收 base64 编码的音频，返回转写的文本。
    可选返回情绪信息（需要更多 token，时间稍长）。

    请求体：
        audio: base64 编码的音频字符串
        format: 音频格式，默认 mp3

    查询参数：
        with_emotion: 是否返回情绪信息，默认 False

    返回：
        text: 转写的文本
        emotion: 情绪类型（如果 with_emotion=True）
        confidence: 置信度（如果 with_emotion=True）
    """
    logger.info(f"收到 ASR 请求 | user_id={user_id} | format={request.format} | with_emotion={with_emotion}")

    asr = get_asr_provider()

    try:
        if with_emotion:
            # 带情绪的转写
            result = await asr.transcribe_with_emotion_from_base64(request.audio, format=request.format)
        else:
            # 普通转写
            result = await asr.transcribe_from_base64(request.audio, format=request.format)

        logger.info(f"ASR 完成 | user_id={user_id} | text={result.text[:30]}...")
        return ApiResponse(data=ASRResponse.from_result(result))

    except ASRException as e:
        logger.error(f"ASR 失败 | user_id={user_id} | error={e}")
        return ApiResponse(code=500, message=str(e), data=None)