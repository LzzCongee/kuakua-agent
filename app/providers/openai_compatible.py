"""
OpenAI 兼容 AI Provider 实现

适用于所有提供 OpenAI 兼容 API 的模型服务，包括但不限于：
- MiniMax (https://api.minimax.chat/v1)
- ModelScope (https://api-inference.modelscope.cn/v1)
- DeepSeek (https://api.deepseek.com/v1)
- 通义千问 / DashScope (https://dashscope.aliyuncs.com/compatible-mode/v1)
- 任何 OpenAI 兼容的第三方服务
"""

from typing import AsyncGenerator, Optional  # noqa: UP035

import httpx
from openai import APIError, AsyncOpenAI, AuthenticationError, RateLimitError

from .base import AIProviderException, BaseAIProvider


class OpenAICompatibleProvider(BaseAIProvider):
    """
    OpenAI 兼容 AI Provider

    通过 OpenAI 兼容接口调用各种大模型。
    只要服务商提供 OpenAI 格式的 /chat/completions 接口，即可直接使用。

    通过修改 .env 配置即可切换不同厂商，无需改动代码：
        AI_BASE_URL=https://api.minimax.chat/v1
        MODELSCOPE_API_KEY=your-api-key
        AI_MODEL=MiniMax-Text-01

    Attributes:
        client: AsyncOpenAI 异步客户端实例
        timeout: 请求超时秒数

    Example:
        >>> provider = OpenAICompatibleProvider(
        ...     api_key="your-api-key",
        ...     base_url="https://api.minimax.chat/v1",
        ...     model="MiniMax-Text-01"
        ... )
        >>> result = await provider.generate("你好")
        >>> print(result)
    """

    # 默认模型
    DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"

    # 默认超时配置（秒）
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, api_key: str, base_url: str, model: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        """
        初始化 OpenAI 兼容 Provider

        Args:
            api_key: API Key
            base_url: OpenAI 兼容接口地址，如 https://api.minimax.chat/v1
            model: 模型名称，如 MiniMax-Text-01、deepseek-ai/DeepSeek-V3.2
            timeout: API 调用超时秒数（默认 30s）
        """
        super().__init__(api_key=api_key, model=model or self.DEFAULT_MODEL)

        self.timeout = timeout
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> str:
        """
        调用模型生成文本

        Args:
            prompt: 用户输入提示词
            system_prompt: 系统提示词（可选），用于设定 AI 角色和行为
            temperature: 采样温度，控制输出随机性（0-2，默认 0.7）
            max_tokens: 最大生成 token 数（默认 150）

        Returns:
            AI 生成的文本内容

        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            return content.strip() if content else ""

        except Exception as e:
            raise self._handle_api_error(e)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
    ) -> AsyncGenerator[str, None]:
        """
        流式生成文本

        使用 OpenAI SDK 的 stream 模式，逐步 yield 生成内容。

        Args:
            prompt: 用户输入提示词
            system_prompt: 系统提示词（可选）
            temperature: 采样温度（默认 0.7）
            max_tokens: 最大生成 token 数（默认 150）

        Yields:
            str: 逐步生成的文本片段

        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            raise self._handle_api_error(e)

    def _handle_api_error(self, error: Exception) -> AIProviderException:
        """统一处理 API 错误"""
        if isinstance(error, AuthenticationError):
            return AIProviderException(
                "API 密钥认证失败，请检查 API Key 是否正确",
                original_error=error
            )
        elif isinstance(error, RateLimitError):
            return AIProviderException(
                "请求过于频繁，请稍后再试",
                original_error=error
            )
        elif isinstance(error, APIError):
            return AIProviderException(
                f"AI API 调用失败: {error.message}",
                original_error=error
            )
        else:
            return AIProviderException(
                f"调用 AI 服务时发生未知错误: {str(error)}",
                original_error=error
            )

    async def generate_multimodal(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> str:
        """
        多模态生成（支持文本+图片）

        Args:
            messages: 消息列表，格式兼容 OpenAI Vision API
            model: 模型名称，None 时使用默认模型
            temperature: 采样温度（默认 0.7）
            max_tokens: 最大生成 token 数（默认 150）

        Returns:
            AI 生成的文本内容

        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        try:
            actual_model = model if model is not None else self.model

            response = await self.client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            return content.strip() if content else ""

        except Exception as e:
            raise self._handle_api_error(e)
