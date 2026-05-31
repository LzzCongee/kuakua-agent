"""
ASR Implementations - 厂商实现包

各 ASR provider 实现：
- BigModelFlashASRProvider (默认): 火山引擎 BigModel Flash 纯 ASR
- DoubaoASRProvider: 火山引擎 Doubao-Seed Chat Completions
"""

from .bigmodel_flash import BigModelFlashASRProvider
from .doubao import DoubaoASRProvider

__all__ = ["BigModelFlashASRProvider", "DoubaoASRProvider"]