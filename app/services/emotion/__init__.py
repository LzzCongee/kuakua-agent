"""
情绪服务模块包

包含：
- EmotionDetector：文本情绪检测（规则引擎）
- EmotionAnalyzer：语音/图片情绪分析（对接豆包 4.0 Lite）
- EmotionMiddleware：情绪检测中间件（独立 Pipeline 演进方向）
- EmotionContext：情绪上下文，附着在 Request.state 上供 handler 使用
"""

from app.services.emotion.analyzer import (
    EmotionAnalysisResult,
    EmotionAnalyzer,
)
from app.services.emotion.detector import (
    EmotionDetector,
    EmotionResult,
    EmotionType,
    emotion_detector,
)
from app.services.emotion.middleware import (
    EmotionContext,
    EmotionMiddleware,
    detect_emotion_from_request,
)

__all__ = [
    # 文本情绪检测（规则引擎）
    "EmotionDetector",
    "EmotionType",
    "EmotionResult",
    "emotion_detector",
    # 语音/图片情绪分析（LLM）
    "EmotionAnalyzer",
    "EmotionAnalysisResult",
    # 中间件和工具函数
    "EmotionMiddleware",
    "EmotionContext",
    "detect_emotion_from_request",
]