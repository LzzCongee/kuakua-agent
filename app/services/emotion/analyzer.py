"""
情绪分析服务

对接大模型，负责：
1. 语音输入的情绪识别 + ASR 转文本
2. 图片输入的情绪分析

统一输出 EmotionAnalysisResult 格式。

适用于语音/图片输入的情绪检测。文字输入由 EmotionDetector（规则引擎）处理。
"""

import json
import re
from typing import Optional

from app.core.logging import get_logger
from app.providers.base import BaseAIProvider

logger = get_logger(__name__)


class EmotionAnalysisResult:
    """
    情绪分析结果（来自大模型）

    Attributes:
        text: ASR 提取的文本（语音输入）或图片描述（图片输入）
        emotion: 情绪类型 (happy/excited/exhausted/sad/frustrated/calm)
        intensity: 置信度 0.0-1.0
    """

    def __init__(self, text: str, emotion: str, intensity: float):
        self.text = text
        self.emotion = emotion
        self.intensity = intensity

    def __repr__(self) -> str:
        return f"EmotionAnalysisResult(text={self.text[:30]}..., emotion={self.emotion}, intensity={self.intensity})"


class EmotionAnalyzer:
    """
    情绪分析服务（对接大模型）

    处理语音和图片输入的场景，使用 LLM 进行情绪识别。
    规则引擎 <1ms 延迟，可做 LLM 提取的兜底方案。

    检测策略：
    1. 规则匹配：关键词正则匹配，计算得分
    2. 置信度计算：命中越多 intensity 越高
    3. 未命中时默认返回 calm
    """

    # 情绪分析 Prompt（语音/图片输入）
    EMOTION_DETECTION_PROMPT = """分析这段音频/图片中的情绪，严格输出JSON，不要任何额外文字：
{"text":"ASR完整文本或图片描述","emotion":"happy/excited/exhausted/sad/frustrated/calm","intensity":0.0-1.0}

情绪类型说明：
- happy: 开心、高兴、快乐
- excited: 兴奋、激动、超赞
- exhausted: 疲惫、累、困
- sad: 难过、伤心、失落
- frustrated: 烦躁、生气、郁闷
- calm: 平静、淡定、还好"""

    def __init__(self, provider: BaseAIProvider, model_name: Optional[str] = None):
        """
        初始化情绪分析服务

        Args:
            provider: AI Provider 实例
            model_name: 模型名称（可选，默认使用 provider 的默认模型）
        """
        self.provider = provider
        self.model_name = model_name

    async def analyze_audio(self, audio_base64: str) -> EmotionAnalysisResult:
        """
        分析语音输入的情绪

        Args:
            audio_base64: base64 编码的音频数据

        Returns:
            EmotionAnalysisResult: 情绪分析结果
        """
        logger.info(f"分析语音输入 | audio_length={len(audio_base64)}")

        # 构建消息（兼容 OpenAI Vision API 格式的音频）
        messages = [
            {"role": "system", "content": self.EMOTION_DETECTION_PROMPT},
            {"role": "user", "content": [
                {"type": "input_audio", "input_audio": {
                    "data": audio_base64,
                    "format": "mp3"
                }}
            ]}
        ]

        # 调用大模型
        try:
            response = await self.provider.generate_multimodal(
                messages=messages,
                model=self.model_name,
            )

            logger.debug(f"语音分析原始响应 | response={response[:200] if response else 'empty'}")

            # 解析 JSON 响应
            result = self._parse_json_response(response)
            if result:
                logger.info(
                    f"语音分析完成 | emotion={result['emotion']} | "
                    f"intensity={result['intensity']:.2f} | text={result['text'][:30]}..."
                )
                return EmotionAnalysisResult(
                    text=result.get("text", ""),
                    emotion=result.get("emotion", "calm"),
                    intensity=float(result.get("intensity", 0.5))
                )

        except Exception as e:
            logger.error(f"语音分析异常 | error={type(e).__name__}: {e}")

        # 失败时返回默认
        return EmotionAnalysisResult(text="", emotion="calm", intensity=0.5)

    async def analyze_image(self, image_base64: str) -> EmotionAnalysisResult:
        """
        分析图片输入的情绪

        Args:
            image_base64: base64 编码的图片数据

        Returns:
            EmotionAnalysisResult: 情绪分析结果
        """
        logger.info(f"分析图片输入 | image_length={len(image_base64)}")

        # 构建消息（兼容 OpenAI Vision API）
        messages = [
            {"role": "system", "content": self.EMOTION_DETECTION_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }}
            ]}
        ]

        # 调用大模型
        try:
            response = await self.provider.generate_multimodal(
                messages=messages,
                model=self.model_name,
            )

            logger.debug(f"图片分析原始响应 | response={response[:200] if response else 'empty'}")

            # 解析 JSON 响应
            result = self._parse_json_response(response)
            if result:
                logger.info(
                    f"图片分析完成 | emotion={result['emotion']} | "
                    f"intensity={result['intensity']:.2f} | text={result['text'][:30]}..."
                )
                return EmotionAnalysisResult(
                    text=result.get("text", ""),
                    emotion=result.get("emotion", "calm"),
                    intensity=float(result.get("intensity", 0.5))
                )

        except Exception as e:
            logger.error(f"图片分析异常 | error={type(e).__name__}: {e}")

        # 失败时返回默认
        return EmotionAnalysisResult(text="", emotion="calm", intensity=0.5)

    def _parse_json_response(self, response: str) -> dict | None:
        """
        解析 JSON 响应，处理各种边界情况

        Args:
            response: API 返回的原始响应字符串

        Returns:
            dict: 解析后的结果，或 None 如果解析失败
        """
        if not response:
            return None

        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 对象（处理 markdown 代码块等情况）
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, response)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # 尝试更宽松的匹配
        brace_start = response.find('{')
        brace_end = response.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_start < brace_end:
            potential_json = response[brace_start:brace_end + 1]
            try:
                return json.loads(potential_json)
            except json.JSONDecodeError:
                pass

        logger.warning(f"JSON 解析失败 | response={response[:100]}")
        return None