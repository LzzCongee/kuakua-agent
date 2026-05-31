"""
应用配置模块
使用 pydantic-settings 从环境变量和 .env 文件读取配置

微服务架构：所有配置通过环境变量或 .env 文件管理，
遵循十二要素应用（The Twelve-Factor App）最佳实践
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """单个模型调用场景的配置（API Key / 接口地址 / 模型名 / 超时）"""

    api_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="API Key",
    )
    base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        description="OpenAI 兼容接口地址",
    )
    model: str = Field(
        default="deepseek-ai/DeepSeek-V4-Flash",
        description="模型名称",
    )
    timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=120.0,
        description="调用超时秒数",
    )


class PureASRConfig(BaseModel):
    """纯 ASR 专用配置（使用火山引擎 BigModel Flash ASR API，与 AI 模型配置完全分离）

    新版控制台只需 app_key，不需要 access_key。

    环境变量：
    - PURE_ASR__APP_KEY: 火山引擎 App Key（新版控制台 API Key）
    - PURE_ASR__BASE_URL: BigModel Flash ASR 端点
    - PURE_ASR__RESOURCE_ID: 资源 ID（默认 volc.bigasr.auc_turbo）
    - PURE_ASR__MODEL: 模型名称（默认 bigmodel）
    - PURE_ASR__TIMEOUT: 超时秒数（默认 30s）
    """

    app_key: str = Field(default="", description="火山引擎 App Key（新版控制台 API Key）")
    base_url: str = Field(
        default="https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
        description="BigModel Flash ASR 端点",
    )
    resource_id: str = Field(
        default="volc.bigasr.auc_turbo",
        description="ASR 资源 ID",
    )
    model: str = Field(
        default="bigmodel",
        description="ASR 模型名称",
    )
    timeout: float = Field(default=30.0, ge=5.0, le=120.0, description="调用超时秒数")


class Settings(BaseSettings):
    """
    应用配置类
    优先从环境变量读取，其次从 .env 文件读取

    配置项可通过以下方式设置（优先级从高到低）：
    1. 环境变量
    2. .env 文件
    3. 默认值

    模型配置按任务分组（ai_chat / ai_vision / ai_extract），
    每组独立拥有 api_key、base_url、model、timeout，
    环境变量使用双下划线嵌套：AI_CHAT__API_KEY、AI_VISION__MODEL 等。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ==================== 应用基础配置 ====================

    service_name: str = Field(default="kuakua-agent", description="服务名称")
    environment: str = Field(default="development", description="运行环境")

    # ==================== 日志配置 ====================

    log_level: str = Field(default="INFO", description="日志级别")
    log_dir: str = Field(default="logs", description="日志文件目录")
    log_filename: str = Field(default="kuakua-agent", description="日志文件名前缀")
    log_file_enabled: bool = Field(default=True, description="是否启用日志文件输出")
    log_backup_count: int = Field(default=30, description="日志文件保留天数")
    log_console_enabled: bool = Field(default=True, description="是否在控制台输出日志")

    # ==================== 模型配置（分组） ====================

    # 聊天文本生成
    ai_chat: ModelConfig = Field(
        default_factory=ModelConfig,
        description="聊天文本生成模型配置",
    )

    # 视觉多模态
    ai_vision: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="Qwen/Qwen3-VL-8B-Instruct",
            timeout=60.0,
        ),
        description="视觉多模态模型配置",
    )

    # 记忆提取
    ai_extract: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="deepseek-ai/DeepSeek-V4-Flash",
            timeout=15.0,
        ),
        description="记忆提取模型配置",
    )

    # ASR 语音识别（复用 AI vision 配置，因为 Doubao-Seed 支持音频输入）
    ai_asr: ModelConfig = Field(
        default_factory=ModelConfig,
        description="ASR 语音识别模型配置（已废弃，请使用 pure_asr）",
    )

    # 纯 ASR 专用配置（使用火山引擎 ARK API，与其他 AI 模型配置分离）
    pure_asr: PureASRConfig = Field(
        default_factory=PureASRConfig,
        description="纯 ASR 专用配置（使用火山引擎 ARK API）",
    )

    # ==================== AI 记忆提取控制参数 ====================

    ai_extract_enabled: bool = Field(
        default=True,
        description="是否启用 AI 记忆提取",
    )
    ai_extract_keyword_fallback: bool = Field(
        default=True,
        description="是否启用关键词兜底提取",
    )
    ai_extract_temperature: float = Field(
        default=0.1,
        description="提取 LLM 的 temperature",
    )
    ai_extract_max_tokens: int = Field(
        default=200,
        description="提取 LLM 的 max_tokens",
    )

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

    # ==================== 微信小程序配置 ====================

    wechat_app_id: str = Field(
        default="",
        description="微信小程序 AppID（wx开头）",
    )
    wechat_app_secret: str = Field(
        default="",
        description="微信小程序 AppSecret",
    )

    # ==================== supermemory MCP 配置 ====================

    # supermemory MCP Server SSE 地址
    supermemory_url: str = Field(
        default="http://106.55.151.27/sse",
        description="supermemory MCP Server SSE 地址"
    )

    # SSE 连接 token（作为 header 传递，用于服务端标识调用方）
    supermemory_token: str = Field(
        default="kuakua-agent",
        description="MCP 连接 token，作为请求头传递给 MCP Server"
    )

    # SSE 连接附加请求头（如需额外 header）
    supermemory_headers: Optional[dict[str, Any]] = Field(
        default=None,
        description="SSE 连接附加请求头（优先级高于 supermemory_token）"
    )

    # 是否启用 supermemory MCP
    supermemory_enabled: bool = Field(
        default=True,
        description="是否启用 supermemory MCP"
    )

    # 单次 MCP 工具调用超时（秒）
    supermemory_timeout: float = Field(
        default=15.0,
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


@lru_cache()  # noqa: UP011
def get_settings() -> Settings:
    """
    获取配置实例（使用 lru_cache 缓存，避免重复读取）

    Returns:
        Settings: 应用配置实例
    """
    return Settings()
