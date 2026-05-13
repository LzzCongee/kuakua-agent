"""
AI Provider 抽象基类模块

定义所有 AI Provider 必须实现的接口规范，支持多种大模型后端（通义千问、GPT 等）
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Protocol, runtime_checkable


@runtime_checkable
class AIProviderProtocol(Protocol):
    """
    AI Provider 协议定义（结构化子类型）
    
    基于 PEP 544 的 Protocol，用于类型检查的鸭子类型约束。
    任何实现了相同方法签名的类都自动满足此协议，无需显式继承。
    
    与 BaseAIProvider (ABC) 的区别：
    - ABC 要求显式继承，Protocol 基于方法签名自动匹配
    - Protocol 更适合用于类型注解和依赖注入的参数类型
    """
    
    async def generate(self, prompt: str, **kwargs: object) -> str: ...
    async def generate_multimodal(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
    ) -> str: ...
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[str, None]: ...


class BaseAIProvider(ABC):
    """
    AI Provider 抽象基类
    
    所有 AI 提供商（通义千问、OpenAI 等）都需要继承此类并实现抽象方法。
    提供统一的生成接口，便于业务层切换不同模型后端。
    
    Attributes:
        api_key: API 密钥，由子类在初始化时保存
        model: 使用的模型名称，默认由子类定义
    """
    
    def __init__(self, api_key: str, model: Optional[str] = None):
        """
        初始化 Provider
        
        Args:
            api_key: API 密钥
            model: 模型名称，None 表示使用默认值
        """
        self.api_key = api_key
        self.model = model
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
    ) -> str:
        """
        调用 AI 模型生成文本
        
        Args:
            prompt: 输入提示词
            system_prompt: 系统提示词（可选）
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            
        Returns:
            AI 生成的文本内容
            
        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        pass
    
    @abstractmethod
    async def generate_multimodal(self, messages: list[dict], model: str | None = None) -> str:
        """
        调用 AI 模型进行多模态生成（支持文本+图片）
        
        messages 格式兼容 OpenAI Vision API 标准，示例：
        [
            {"role": "system", "content": "你是一个暖心的夸夸助手"},
            {"role": "user", "content": [
                {"type": "text", "text": "夸夸这张照片里的我"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
            ]}
        ]
        
        Args:
            messages: 消息列表，包含角色和内容（支持多模态内容）
            model: 模型名称，None 表示使用默认模型
            
        Returns:
            AI 生成的文本内容
            
        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        pass

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
    ) -> AsyncGenerator[str, None]:
        """
        调用 AI 模型流式生成文本
        
        默认实现：调用 generate 并一次性返回结果。
        子类应重写此方法以实现真正的流式输出。
        
        Args:
            prompt: 输入提示词
            system_prompt: 系统提示词（可选）
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            
        Yields:
            str: 逐步生成的文本片段
        """
        result = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield result
    
    async def generate_quote(self, scene: str) -> str:
        """
        生成特定场景的夸赞文案（便捷方法）
        
        子类可重写此方法以实现更复杂的场景处理逻辑。
        默认实现直接使用 scene 作为 prompt 调用 generate。
        
        Args:
            scene: 场景描述或场景类型标识
            
        Returns:
            生成的夸赞文案
        """
        return await self.generate(scene)


class AIProviderException(Exception):
    """
    AI Provider 异常基类
    
    用于封装各种 AI API 调用过程中可能出现的错误，
    提供统一的错误处理接口。
    
    Attributes:
        message: 错误描述信息
        original_error: 原始异常对象（如果有）
    """
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error
    
    def __str__(self) -> str:
        if self.original_error:
            return (
                f"{self.message} "
                f"(原始错误：{type(self.original_error).__name__}: {self.original_error})"
            )
        return self.message
