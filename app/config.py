"""
应用配置模块
使用 pydantic-settings 从环境变量和 .env 文件读取配置
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    优先从环境变量读取，其次从 .env 文件读取
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # 忽略未定义的配置项
    )

    # 魔搭社区 API Key
    modelscope_api_key: str

    # AI 服务基础 URL，默认为魔搭社区 OpenAI 兼容接口
    ai_base_url: str = "https://api-inference.modelscope.cn/v1"

    # AI 模型名称，默认为魔搭社区 DeepSeek-R1-Distill-Qwen-7B 模型
    ai_model: str = "deepseek-ai/DeepSeek-V3.2"

    # AI 视觉模型名称，用于处理图片等视觉任务
    ai_vision_model: str = "Qwen/Qwen2.5-VL-72B-Instruct"

    # 数据库连接 URL，默认为本地 SQLite 数据库
    database_url: str = "sqlite:///./kuakua.db"

    # 应用监听主机
    app_host: str = "0.0.0.0"

    # 应用监听端口
    app_port: int = 8000


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置实例（使用 lru_cache 缓存，避免重复读取）

    Returns:
        Settings: 应用配置实例
    """
    return Settings()
