"""
ASR Implementations - 厂商实现包

各 ASR provider 实现：
- DoubaoASRProvider: 火山引擎 Doubao-Seed
"""

from .doubao import DoubaoASRProvider

__all__ = ["DoubaoASRProvider"]