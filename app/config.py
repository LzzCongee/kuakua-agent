"""
应用配置模块
使用 pydantic-settings 从环境变量和 .env 文件读取配置

微服务架构：所有配置通过环境变量或 .env 文件管理，
遵循十二要素应用（The Twelve-Factor App）最佳实践
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    优先从环境变量读取，其次从 .env 文件读取
    
    配置项可通过以下方式设置（优先级从高到低）：
    1. 环境变量
    2. .env 文件
    3. 默认值
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # 忽略未定义的配置项
    )

    # ==================== 应用基础配置 ====================
    
    # 服务名称（用于日志、服务发现）
    service_name: str = Field(default="kuakua-agent", description="服务名称")
    
    # 环境（development/staging/production）
    environment: str = Field(default="development", description="运行环境")

    # ==================== 日志配置 ====================
    
    # 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    log_level: str = Field(
        default="INFO",
        description="日志级别"
    )
    
    # 日志文件目录（相对于项目根目录）
    log_dir: str = Field(
        default="logs",
        description="日志文件目录"
    )
    
    # 日志文件名前缀
    log_filename: str = Field(
        default="kuakua-agent",
        description="日志文件名前缀"
    )
    
    # 是否启用日志文件输出
    log_file_enabled: bool = Field(
        default=True,
        description="是否启用日志文件输出"
    )
    
    # 日志文件保留天数
    log_backup_count: int = Field(
        default=30,
        description="日志文件保留天数"
    )
    
    # 是否在控制台输出日志
    log_console_enabled: bool = Field(
        default=True,
        description="是否在控制台输出日志"
    )

    # ==================== API 配置 ====================

    # 魔搭社区 API Key（必填，需要从 https://modelscope.cn/services/api 申请）
    modelscope_api_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="魔搭社区 API Key（生产环境必须修改）"
    )

    # AI 服务基础 URL，默认为魔搭社区 OpenAI 兼容接口
    ai_base_url: str = Field(
        default="https://api-inference.modelscope.cn/v1",
        description="AI 服务基础 URL"
    )

    # AI 模型名称，默认为魔搭社区 DeepSeek-R1-Distill-Qwen-7B 模型
    ai_model: str = Field(default="deepseek-ai/DeepSeek-V3.2", description="AI 模型名称")

    # AI 视觉模型名称，用于处理图片等视觉任务
    ai_vision_model: str = Field(default="Qwen/Qwen2.5-VL-72B-Instruct", description="AI 视觉模型名称")

    # ==================== 数据库配置 ====================
    
    # 数据库连接 URL，默认为本地 SQLite 数据库
    database_url: str = Field(default="sqlite:///./kuakua.db", description="数据库连接 URL")

    # ==================== 服务配置 ====================
    
    # 应用监听主机
    app_host: str = Field(default="0.0.0.0", description="应用监听主机")

    # 应用监听端口
    app_port: int = Field(default=8000, ge=1, le=65535, description="应用监听端口")

    # ==================== 安全配置 ====================
    
    # 管理后台 API Key（用于 admin 接口认证）
    admin_api_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="管理后台 API Key，用于 X-Admin-Key header 认证（生产环境必须修改）"
    )

    # ==================== supermemory MCP 配置 ====================

    # supermemory MCP Server SSE 地址
    supermemory_url: str = Field(
        default="http://106.55.151.27/sse",
        description="supermemory MCP Server SSE 地址"
    )

    # SSE 连接附加请求头（如 token 鉴权）
    supermemory_headers: Optional[Dict[str, Any]] = Field(
        default=None,
        description="SSE 连接附加请求头（如 token 鉴权）"
    )

    # 是否启用 supermemory MCP
    supermemory_enabled: bool = Field(
        default=True,
        description="是否启用 supermemory MCP"
    )

    # 单次 MCP 工具调用超时（秒）
    supermemory_timeout: float = Field(
        default=5.0,
        description="单次 MCP 工具调用超时（秒）"
    )

    # 语义搜索返回数量
    supermemory_top_k: int = Field(
        default=3,
        description="语义搜索返回数量"
    )

    # ==================== CloudBase 配置 ====================
    
    # 是否使用 CloudBase 作为数据服务
    use_cloudbase: bool = Field(
        default=True,
        description="是否使用 CloudBase NoSQL 数据库"
    )
    
    # CloudBase 环境 ID
    cloudbase_env_id: str = Field(
        default="dev-kuakua-d1gmvqyrha28477fe",
        description="CloudBase 环境 ID"
    )
    
    # CloudBase API 密钥 ID
    cloudbase_secret_id: str = Field(
        default="",
        description="CloudBase API 密钥 ID"
    )
    
    # CloudBase API 密钥 Key
    cloudbase_secret_key: str = Field(
        default="",
        description="CloudBase API 密钥 Key"
    )

    @property
    def log_dir_path(self) -> Path:
        """
        获取日志目录的绝对路径
        
        Returns:
            Path: 日志目录的绝对路径
        """
        # 如果是绝对路径，直接返回
        if Path(self.log_dir).is_absolute():
            return Path(self.log_dir)
        # 否则相对于项目根目录
        return Path(__file__).parent.parent / self.log_dir


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置实例（使用 lru_cache 缓存，避免重复读取）

    Returns:
        Settings: 应用配置实例
    """
    return Settings()
