"""
情绪服务模块包

包含：
- EmotionDetector：文本情绪检测（规则引擎）
- EmotionAnalyzer：语音/图片情绪分析（对接豆包 4.0 Lite）
"""

from app.services.emotion.detector import EmotionDetector, EmotionType, EmotionResult, emotion_detector
from app.services.emotion.analyzer import EmotionAnalyzer, EmotionAnalysisResult

__all__ = [
    "EmotionDetector",
    "EmotionType",
    "EmotionResult",
    "emotion_detector",
    "EmotionAnalyzer",
    "EmotionAnalysisResult",
]