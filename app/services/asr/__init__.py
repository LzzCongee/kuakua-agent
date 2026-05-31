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

Provider 类型：
- bigmodel (默认): BigModel Flash ASR，纯 ASR 接口，词级时间戳+置信度
- doubao: Doubao-Seed Chat Completions ASR，支持情绪识别

配置（环境变量）：
- ASR_PROVIDER: ASR 实现类型 (bigmodel/doubao)
- PURE_ASR__APP_ID: 火山引擎 APP ID
- PURE_ASR__ACCESS_TOKEN: 火山引擎 Access Token
- PURE_ASR__BASE_URL: BigModel Flash ASR 端点
- PURE_ASR__RESOURCE_ID: 资源 ID
- PURE_ASR__MODEL: 模型名称
- AI_ASR__API_KEY: Doubao API 密钥
- AI_ASR__BASE_URL: Doubao API 端点
"""

import logging
from functools import lru_cache

from ...config import get_settings
from .base import ASRException, ASRResult, BaseASRProvider

logger = logging.getLogger(__name__)


def _get_default_provider() -> str:
    """获取默认 ASR provider"""
    settings = get_settings()
    return getattr(settings, "asr_provider", "bigmodel")


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
    from .implementations.bigmodel_flash import BigModelFlashASRProvider

    settings = get_settings()
    provider_type = getattr(settings, "asr_provider", "bigmodel")

    logger.info(f"创建 ASR Provider | type={provider_type}")

    if provider_type == "bigmodel":
        return BigModelFlashASRProvider.from_config(settings.pure_asr)

    if provider_type == "doubao":
        return DoubaoASRProvider.from_config(settings.ai_asr)

    logger.warning(f"未知的 ASR provider 类型: {provider_type}，使用默认的 bigmodel")
    return BigModelFlashASRProvider.from_config(settings.pure_asr)


__all__ = [
    "ASRException",
    "ASRResult",
    "BaseASRProvider",
    "get_asr_provider",
]