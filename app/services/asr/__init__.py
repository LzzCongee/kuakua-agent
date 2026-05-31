"""
ASR 语音识别服务模块

提供统一的 ASR 接口，支持多种后端实现。
通过工厂函数 `get_asr_provider()` 获取当前配置的 ASR provider。

使用示例：
```python
from app.services.asr import get_asr_provider, ASRResult

# 获取 ASR provider
asr = get_asr_provider()

# 转写音频
result = await asr.transcribe_from_base64(audio_b64, format="mp3")
print(result.text)
```

配置（环境变量）：
- ASR_PROVIDER: ASR 实现类型 (doubao/mock)
- AI_ASR__API_KEY: API 密钥
- AI_ASR__BASE_URL: API 端点
- AI_ASR__MODEL: 模型名称
- AI_ASR__TIMEOUT: 超时秒数
"""

import logging
from functools import lru_cache

from ...config import get_settings
from .base import ASRException, ASRResult, BaseASRProvider

logger = logging.getLogger(__name__)


def _get_default_provider() -> str:
    """获取默认 ASR provider"""
    settings = get_settings()
    return getattr(settings, "asr_provider", "doubao")


@lru_cache(maxsize=1)
def get_asr_provider() -> BaseASRProvider:
    """
    获取 ASR Provider 实例

    根据配置返回对应的 ASR provider 实现。
    使用 lru_cache 缓存实例，避免重复创建。

    Returns:
        BaseASRProvider: ASR provider 实例
    """
    from .implementations import DoubaoASRProvider

    settings = get_settings()
    provider_type = getattr(settings, "asr_provider", "doubao")

    logger.info(f"创建 ASR Provider | type={provider_type}")

    if provider_type == "doubao":
        # 复用 AI vision 配置（因为 Doubao-Seed 支持音频输入）
        return DoubaoASRProvider.from_config(settings.ai_asr)

    # 默认使用 doubao
    logger.warning(f"未知的 ASR provider 类型: {provider_type}，使用默认的 doubao")
    return DoubaoASRProvider.from_config(settings.ai_asr)


__all__ = [
    "ASRException",
    "ASRResult",
    "BaseASRProvider",
    "get_asr_provider",
]