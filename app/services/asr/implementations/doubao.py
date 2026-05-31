"""
Doubao-Seed ASR 实现

使用火山引擎的 Doubao-Seed-2.0-mini 模型进行语音转写。
支持同时返回转写文本和情绪信息（复用 vision provider）。

配置（环境变量）：
- AI_ASR__API_KEY: API 密钥
- AI_ASR__BASE_URL: API 端点（默认火山引擎 ARK）
- AI_ASR__MODEL: 模型名称
- AI_ASR__TIMEOUT: 超时秒数
"""

import base64
import json
import logging
import re
from typing import TYPE_CHECKING, cast, override

from ....providers.openai_compatible import OpenAICompatibleProvider
from ..base import ASRException, ASRResult, BaseASRProvider

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ....config import ModelConfig

# ASR 转写 Prompt
TRANSCRIBE_PROMPT = """准确转写这段音频中的文字，严格输出JSON格式，不要任何额外文字：
{"text":"转写的完整文本"}

要求：
1. 只返回语音中实际说的话，不要推断或补充
2. 如果音频是纯音乐或无有效语音，返回空文本
3. 确保JSON格式正确"""


class DoubaoASRProvider(BaseASRProvider):
    """Doubao-Seed ASR Provider

    复用 OpenAICompatibleProvider 进行语音转写。
    支持同时返回情绪信息（Doubao-Seed 特有能力）。
    """

    def __init__(self, provider: OpenAICompatibleProvider):
        """
        初始化 ASR Provider

        Args:
            provider: OpenAI 兼容的 AI Provider 实例
        """
        self.provider: OpenAICompatibleProvider = provider

    @classmethod
    def from_config(cls, config: "ModelConfig") -> "DoubaoASRProvider":
        """从配置创建 Provider 实例"""
        provider = OpenAICompatibleProvider.from_config(config)
        return cls(provider=provider)

    @override
    async def transcribe(
        self,
        audio: bytes,
        format: str = "mp3",
    ) -> ASRResult:
        """
        使用 Doubao-Seed 转写音频

        Args:
            audio: 原始音频数据
            format: 音频格式

        Returns:
            ASRResult: 转写结果
        """
        logger.info(f"Doubao ASR 开始转写 | format={format}, size={len(audio)}")

        # 转为 base64
        audio_b64 = base64.b64encode(audio).decode("utf-8")

        # 构建消息（兼容 OpenAI Vision API 格式的音频输入）
        messages: list[dict[str, object]] = [
            {"role": "system", "content": TRANSCRIBE_PROMPT},
            {"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": format}}
            ]},
        ]

        try:
            # 调用模型
            response = await self.provider.generate_multimodal(messages=messages)

            logger.debug(f"Doubao ASR 原始响应 | {response[:200] if response else 'empty'}")

            # 解析 JSON
            result = self._parse_json_response(response)
            if result:
                text = result.get("text", "")
                logger.info(f"Doubao ASR 完成 | text={text[:50]}...")
                return ASRResult(text=text)

            # 解析失败，使用原始响应作为文本
            return ASRResult(text=response.strip())

        except Exception as e:
            logger.error(f"Doubao ASR 异常 | {type(e).__name__}: {e}")
            raise ASRException(f"语音转写失败: {e}", original_error=e) from e

    async def transcribe_with_emotion(
        self,
        audio: bytes,
        format: str = "mp3",
    ) -> ASRResult:
        """
        带情绪��息的转写（Doubao-Seed 特有）

        使用更丰富的 Prompt 同时返回转写和情绪。

        Args:
            audio: 原始音频数据
            format: 音频格式

        Returns:
            ASRResult: 含情绪的转写结果
        """
        logger.info(f"Doubao ASR(情绪版) 开始 | format={format}, size={len(audio)}")

        audio_b64 = base64.b64encode(audio).decode("utf-8")

        # 带情绪检测的 Prompt
        prompt = """分析这段音频，严格输出JSON：
{"text":"转写的完整文本","emotion":"happy/excited/exhausted/sad/frustrated/calm","confidence":0.0-1.0}

情绪类型说明：
- happy: 开心、高兴
- excited: 兴奋、激动
- exhausted: 疲惫、累
- sad: 难过、伤心
- frustrated: 烦躁、生气
- calm: 平静、正常"""

        messages: list[dict[str, object]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": format}}
            ]},
        ]

        try:
            response = await self.provider.generate_multimodal(messages=messages)

            logger.debug(f"Doubao ASR(情绪版) 原始响应 | {response[:200] if response else 'empty'}")

            result = self._parse_json_response(response)
            if result:
                logger.info(
                    "Doubao ASR(情绪版) 完成 | text=%s..., emotion=%s",
                    result.get("text", "")[:30],
                    result.get("emotion"),
                )
                return ASRResult(
                    text=result.get("text", ""),
                    emotion=result.get("emotion"),
                    confidence=float(result.get("confidence", 0.5)),
                )

            return ASRResult(text=response.strip())

        except Exception as e:
            logger.error(f"Doubao ASR(情绪版) 异常 | {type(e).__name__}: {e}")
            raise ASRException(f"语音转写失败: {e}", original_error=e) from e

    def _parse_json_response(self, response: str) -> dict[str, str] | None:
        """解析 JSON 响应"""
        # 尝试提取 JSON 块
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            try:
                return cast(dict[str, str], json.loads(json_match.group()))
            except json.JSONDecodeError:
                pass

        # 尝试直接解析整个响应
        try:
            return cast(dict[str, str], json.loads(response))
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败 | response={response[:100]}...")
            return None