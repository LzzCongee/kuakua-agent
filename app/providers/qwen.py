"""
向后兼容模块 - 已迁移至 openai_compatible.py

请使用 app.providers.openai_compatible.OpenAICompatibleProvider 代替。
"""

from .openai_compatible import OpenAICompatibleProvider

# 向后兼容别名
QwenProvider = OpenAICompatibleProvider

__all__ = ["QwenProvider", "OpenAICompatibleProvider"]
