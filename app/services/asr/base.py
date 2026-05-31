"""
ASR 语音识别服务抽象基类

提供统一的 ASR 转写接口，支持多种后端实现。
通过工厂函数动态切换不同的 ASR provider。

设计原则：
1. 所有 ASR Provider 实现统一的抽象基类
2. 支持同时返回转写文本和情绪信息（Doubao-Seed 特有能力）
3. 配置驱动，通过环境变量切换不同实现
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ASRException(Exception):
    """ASR 服务异常基类"""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (原错误: {self.original_error})"
        return self.message


@dataclass
class ASRResult:
    """ASR 转写结果

    Attributes:
        text: 转写的文本内容
        emotion: 情绪类型 (happy/excited/exhausted/sad/frustrated/calm)，如果不支持则为空
        confidence: 置信度 0.0-1.0，如果不支持则为空
    """

    text: str
    emotion: str | None = None
    confidence: float | None = None

    def __repr__(self) -> str:
        emotion_part = f", emotion={self.emotion}" if self.emotion else ""
        conf_part = f", confidence={self.confidence:.2f}" if self.confidence else ""
        return f"ASRResult(text={self.text[:30]}...{emotion_part}{conf_part})"


class BaseASRProvider(ABC):
    """
    ASR Provider 抽象基类

    所有 ASR 实现必须继承此类并实现抽象方法。
    设计参考 providers/base.py 的 AI Provider 模式。
    """

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        format: str = "mp3",
    ) -> ASRResult:
        """
        将音频转换为文字

        Args:
            audio: 原始音频数据（bytes）
            format: 音频格式 (mp3/wav/m4a)

        Returns:
            ASRResult: 转写结果

        Raises:
            ASRException: 当转写失败时抛出
        """
        ...

    async def transcribe_from_base64(
        self,
        audio_base64: str,
        format: str | None = None,
    ) -> ASRResult:
        """
        从 base64 编码的音频转换（便捷方法）

        Args:
            audio_base64: base64 编码的音频字符串或 data URL
            format: 音频格式（如果传入 data URL 则自动推断）

        Returns:
            ASRResult: 转写结果
        """
        import base64

        # 处理 data URL 格式：data:audio/ogg;base64,xxxxx
        audio_data = audio_base64
        audio_format = format or "ogg"
        if audio_base64.startswith("data:audio/"):
            remaining = audio_base64[len("data:audio/") :]
            semi_colon_idx = remaining.find(";")
            if semi_colon_idx > 0:
                audio_format = remaining[:semi_colon_idx]
                audio_data = remaining[semi_colon_idx + 1 :]  # 移除 ";base64," 前缀
                if audio_data.startswith("base64,"):
                    audio_data = audio_data[len("base64,") :]

        audio = base64.b64decode(audio_data)
        return await self.transcribe(audio, audio_format)

    async def transcribe_with_emotion_from_base64(
        self,
        audio_base64: str,
        format: str | None = None,
    ) -> ASRResult:
        """
        从 base64 编码的音频转换，带情绪信息

        Args:
            audio_base64: base64 编码的音频字符串或 data URL
            format: 音频格式（如果传入 data URL 则自动推断）

        Returns:
            ASRResult: 转写结果（含情绪）
        """
        import base64

        # 处理 data URL 格式：data:audio/ogg;base64,xxxxx
        audio_data = audio_base64
        audio_format = format or "ogg"
        if audio_base64.startswith("data:audio/"):
            remaining = audio_base64[len("data:audio/") :]
            semi_colon_idx = remaining.find(";")
            if semi_colon_idx > 0:
                audio_format = remaining[:semi_colon_idx]
                audio_data = remaining[semi_colon_idx + 1 :]
                if audio_data.startswith("base64,"):
                    audio_data = audio_data[len("base64,") :]

        audio = base64.b64decode(audio_data)
        return await self.transcribe_with_emotion(audio, audio_format)