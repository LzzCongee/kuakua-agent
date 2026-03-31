"""
通义千问 (Qwen) AI Provider 实现

使用 OpenAI 兼容接口调用通义千问模型
"""

from typing import Optional

from openai import AsyncOpenAI, APIError, AuthenticationError, RateLimitError

from .base import BaseAIProvider, AIProviderException


class QwenProvider(BaseAIProvider):
    """
    通义千问 AI Provider
    
    通过 OpenAI 兼容接口调用通义千问模型。
    支持 Qwen/Qwen-Turbo、Qwen/Qwen-Plus 等多种模型。
    
    Attributes:
        client: AsyncOpenAI 异步客户端实例
        base_url: OpenAI 兼容接口地址
        
    Example:
        >>> provider = QwenProvider(api_key="your-api-key", base_url="https://api-inference.modelscope.cn/v1", model="Qwen/Qwen-Turbo")
        >>> result = await provider.generate("你好")
        >>> print(result)
    """
    
    # 默认模型
    DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"
    
    def __init__(self, api_key: str, base_url: str, model: Optional[str] = None):
        """
        初始化通义千问 Provider
        
        Args:
            api_key: API Key
            base_url: OpenAI 兼容接口地址
            model: 模型名称，默认使用 Qwen/Qwen-Turbo
                   可选值：Qwen/Qwen-Turbo, Qwen/Qwen-Plus, Qwen/Qwen-Max 等
        """
        super().__init__(api_key=api_key, model=model or self.DEFAULT_MODEL)
        
        # 初始化 OpenAI 兼容客户端
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> str:
        """
        调用通义千问模型生成文本
        
        Args:
            prompt: 用户输入提示词
            system_prompt: 系统提示词（可选），用于设定 AI 角色和行为
            temperature: 采样温度，控制输出随机性（0-2，默认 0.7）
            max_tokens: 最大生成 token 数（默认 150）
            
        Returns:
            AI 生成的文本内容
            
        Raises:
            AIProviderException: 当 API 调用失败时抛出，包含详细的错误信息
        """
        try:
            # 构建消息列表
            messages = []
            
            # 添加系统提示词（如果有）
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            # 添加用户提示词
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            # 调用 API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # 提取生成的内容
            content = response.choices[0].message.content
            
            # 去除首尾空白
            return content.strip() if content else ""
            
        except Exception as e:
            # 使用统一的错误处理方法
            raise self._handle_api_error(e)
    
    async def generate_quote(self, scene: str, system_prompt: Optional[str] = None) -> str:
        """
        生成特定场景的夸赞文案
        
        便捷方法，支持传入系统提示词来设定 AI 角色。
        
        Args:
            scene: 场景描述（如用户状态、时间等上下文）
            system_prompt: 系统提示词，定义 AI 角色和生成规则
            
        Returns:
            生成的夸赞文案
        """
        return await self.generate(
            prompt=scene,
            system_prompt=system_prompt,
            temperature=0.8,  # 夸赞可以稍微有创意一些
            max_tokens=100    # 夸赞文案通常较短
        )
    
    def _handle_api_error(self, error: Exception) -> AIProviderException:
        """
        统一处理 API 错误
        
        将不同类型的 API 异常转换为统一的 AIProviderException。
        
        Args:
            error: 原始异常对象
            
        Returns:
            包装后的 AIProviderException
        """
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
                f"通义千问 API 调用失败: {error.message}",
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
        调用通义千问模型进行多模态生成（支持文本+图片）
        
        支持传入包含图片的多模态消息，兼容 OpenAI Vision API 格式。
        
        Args:
            messages: 消息列表，格式兼容 OpenAI Vision API
            model: 模型名称，None 时使用默认模型 self.model
            temperature: 采样温度，控制输出随机性（0-2，默认 0.7）
            max_tokens: 最大生成 token 数（默认 150）
            
        Returns:
            AI 生成的文本内容
            
        Raises:
            AIProviderException: 当 API 调用失败时抛出
        """
        try:
            # 确定使用的模型
            actual_model = model if model is not None else self.model
            
            # 调用 API
            response = await self.client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # 提取生成的内容
            content = response.choices[0].message.content
            
            # 去除首尾空白
            return content.strip() if content else ""
            
        except Exception as e:
            # 使用统一的错误处理方法
            raise self._handle_api_error(e)
