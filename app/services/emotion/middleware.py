"""
情绪检测中间件

在请求到达 handler 之前完成情绪检测，结果存入 request.state.emotion_context。
handler 可通过 `request.state.emotion_context` 访问情绪信息。

架构演进：
1. 独立的 Emotion Pipeline（当前）
2. 中间件前置（本次实现）
3. 独立的 Emotion Service（微服务化）

检测策略：
- 文本情绪：使用 EmotionDetector（规则引擎，<1ms）
- 音频情绪：使用 EmotionAnalyzer（LLM，仅当有音频且无文本时启用）
"""

import json

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...config import get_settings
from ...core.logging import get_logger
from ...providers.openai_compatible import OpenAICompatibleProvider
from .analyzer import EmotionAnalyzer
from .detector import emotion_detector

logger = get_logger(__name__)


class EmotionContext:
    """
    情绪上下文 - 附着在 Request.state 上供后续 handler 使用
    """

    def __init__(
        self,
        text_emotion: str | None = None,
        audio_emotion: str | None = None,
        audio_intensity: float = 0.5,
        audio_text: str | None = None,  # ASR 提取的文本（如果有）
    ):
        self.text_emotion = text_emotion
        self.audio_emotion = audio_emotion
        self.audio_intensity = audio_intensity
        self.audio_text = audio_text

    @property
    def primary_emotion(self) -> str | None:
        """主要情绪：优先使用音频情绪，其次文本情绪"""
        return self.audio_emotion or self.text_emotion

    def to_dict(self) -> dict:
        return {
            "text_emotion": self.text_emotion,
            "audio_emotion": self.audio_emotion,
            "audio_intensity": self.audio_intensity,
            "audio_text": self.audio_text,
            "primary_emotion": self.primary_emotion,
        }


def get_emotion_analyzer() -> EmotionAnalyzer:
    """
    获取 EmotionAnalyzer 实例

    使用 ai_vision 配置（支持多模态）进行音频分析。
    如果没有配置 vision，则降级使用 ai_chat。
    """
    settings = get_settings()
    vision_key = settings.ai_vision.api_key
    if vision_key and vision_key != "CHANGE_ME_IN_PRODUCTION":
        provider = OpenAICompatibleProvider.from_config(settings.ai_vision)
    else:
        provider = OpenAICompatibleProvider.from_config(settings.ai_chat)
    return EmotionAnalyzer(provider=provider)


async def _detect_text_emotion(text: str) -> str | None:
    """检测文本情绪（规则引擎，无延迟）"""
    if not text or not text.strip():
        return None
    result = emotion_detector.detect(text)
    logger.debug(
        f"文本情绪检测完成 | emotion={result.emotion.value} | "
        f"intensity={result.intensity}"
    )
    return result.emotion.value


async def _detect_audio_emotion(audio: str) -> tuple[str | None, float, str | None]:
    """
    检测音频情绪（LLM，有延迟）

    Returns:
        tuple[emotion, intensity, audio_text]
    """
    logger.info(f"检测到纯音频输入，进行 LLM 情绪分析 | audio_length={len(audio)}")
    try:
        analyzer = get_emotion_analyzer()
        audio_result = await analyzer.analyze_audio(audio)
        logger.info(
            f"音频情绪检测完成 | emotion={audio_result.emotion} | "
            f"intensity={audio_result.intensity}"
        )
        return (
            audio_result.emotion,
            audio_result.intensity,
            audio_result.text if audio_result.text else None,
        )
    except Exception as e:
        logger.warning(f"音频情绪检测失败，降级为默认情绪 | error={e}")
        return "calm", 0.5, None


async def detect_emotion_from_request(
    request: Request,
    text: str | None = None,
    audio: str | None = None,
) -> EmotionContext:
    """
    从请求中检测情绪

    辅助函数，供 chat handler 调用（兼容当前调用方式）。
    封装了完整的情绪检测逻辑。

    检测策略：
    1. 文本情绪：始终使用规则引擎检测
    2. 音频情绪：仅当有音频且无文本时使用 LLM 分析
    """
    emotion_context = EmotionContext()

    if text and text.strip():
        emotion_context.text_emotion = await _detect_text_emotion(text)

    if audio and audio.strip() and not text:
        audio_emotion, audio_intensity, audio_text = await _detect_audio_emotion(audio)
        emotion_context.audio_emotion = audio_emotion
        emotion_context.audio_intensity = audio_intensity
        emotion_context.audio_text = audio_text

    return emotion_context


class EmotionMiddleware(BaseHTTPMiddleware):
    """
    情绪检测中间件

    在请求到达 handler 之前完成情绪检测，结果存入 request.state.emotion_context。
    handler 可通过 `request.state.emotion_context` 访问情绪信息。

    工作流程：
    1. 读取请求体，解析 JSON
    2. 提取 text、audio 字段
    3. 执行情绪检测
    4. 存入 request.state.emotion_context
    5. 继续处理请求（call_next）
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        emotion_context: EmotionContext | None = None

        # 仅对 /api/chat 路径进行情绪检测
        if not request.url.path.startswith("/api/chat"):
            return await call_next(request)

        try:
            # 读取请求体
            body = await request.body()
            if body:
                data = json.loads(body)
                text = data.get("text") or None
                audio = data.get("audio") or None

                logger.debug(
                    f"中间件解析请求 | has_text={bool(text)} | has_audio={bool(audio)}"
                )

                emotion_context = EmotionContext()

                # 1. 文本情绪检测（规则引擎，无延迟）
                if text and isinstance(text, str) and text.strip():
                    emotion_context.text_emotion = await _detect_text_emotion(text)

                # 2. 音频情绪检测（LLM，有延迟）
                if audio and isinstance(audio, str) and audio.strip() and not text:
                    (
                        audio_emotion,
                        audio_intensity,
                        audio_text,
                    ) = await _detect_audio_emotion(audio)
                    emotion_context.audio_emotion = audio_emotion
                    emotion_context.audio_intensity = audio_intensity
                    emotion_context.audio_text = audio_text

                logger.info(
                    f"中间件情绪检测完成 | primary={emotion_context.primary_emotion} | "
                    f"text={emotion_context.text_emotion} | "
                    f"audio={emotion_context.audio_emotion}"
                )
        except json.JSONDecodeError:
            logger.warning(f"中间件无法解析请求体为 JSON | path={request.url.path}")
        except Exception as e:
            logger.warning(f"中间件情绪检测失败 | error={e}")

        # 存储情绪上下文到 request state（即使失败也为 None）
        request.state.emotion_context = emotion_context

        response = await call_next(request)
        return response