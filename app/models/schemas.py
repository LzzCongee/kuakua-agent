"""
Pydantic 模型定义模块

定义 API 请求和响应的数据模型
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, Optional, TypedDict, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PromptContent(TypedDict):
    """Prompt 内容结构类型（用于类型安全的 prompt 字典传递）"""
    system: str
    user: str


def _utc_now() -> datetime:
    """返回带时区信息的 UTC 当前时间"""
    return datetime.now(UTC)


class QuoteResponse(BaseModel):
    """
    夸夸语录响应模型

    用于返回生成的夸夸内容
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "examples": [
                {
                    "content": "拖了两周还能坚持找到答案，这份不放弃的劲儿挺难得的。",
                    "scene": "career",
                    "created_at": "2025-05-13T12:00:00+00:00",
                }
            ]
        },
    )
    
    content: str = Field(..., description="夸夸语录内容")
    scene: str = Field(
        default="general",
        description="场景标签：general(通用), career(事业), beauty(颜值), love(恋爱), daily(日常)",
    )
    created_at: datetime = Field(default_factory=_utc_now, description="创建时间")


class FavoriteCreate(BaseModel):
    """
    创建收藏请求模型

    用于接收用户收藏夸夸语录的请求
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "content": "拖了两周还能坚持找到答案，这份不放弃的劲儿挺难得的。",
                    "scene": "career",
                }
            ]
        },
    )
    content: str = Field(..., min_length=1, description="夸夸语录内容")
    scene: str = Field(
        default="general",
        description="场景标签：general(通用), career(事业), beauty(颜值), love(恋爱), daily(日常)",
    )


class FavoriteResponse(BaseModel):
    """
    收藏响应模型

    用于返回收藏记录的完整信息
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "content": "拖了两周还能坚持找到答案，这份不放弃的劲儿挺难得的。",
                    "scene": "career",
                    "created_at": "2025-05-13T12:00:00+00:00",
                }
            ]
        },
    )
    
    id: int = Field(..., description="收藏记录 ID")
    content: str = Field(..., description="夸夸语录内容")
    scene: str = Field(..., description="场景标签")
    created_at: datetime = Field(..., description="创建时间")


# 泛型类型变量
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    统一 API 响应包装模型

    所有 API 响应都使用此模型进行包装，提供统一的响应格式

    Type Parameters:
        T: 响应数据的类型

    Example:
        # 成功响应
        ApiResponse(data={"message": "Hello"})

        # 错误响应
        ApiResponse(code=400, message="参数错误")
    """
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "examples": [
                {
                    "code": 0,
                    "message": "success",
                    "data": {},
                },
                {
                    "code": 400,
                    "message": "参数错误：text 和 image 至少要有一个不为空",
                    "data": None,
                },
            ]
        },
    )
    
    code: int = Field(default=0, description="状态码，0 表示成功")
    message: str = Field(default="success", description="状态消息")
    data: Optional[T] = Field(default=None, description="响应数据")


class ChatRequest(BaseModel):
    """
    交互式夸夸请求模型

    用于接收用户发送的文字、图片或音频，生成个性化的夸赞文案
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "今天终于把那个拖了两周的 bug 修好了",
                    "scene": "career",
                },
                {
                    "text": "今天的穿搭怎么样",
                    "image": "base64编码的图片数据...",
                    "scene": "beauty",
                },
            ]
        },
    )
    text: Optional[str] = Field(default=None, description="用户输入的文字")
    image: Optional[str] = Field(
        default=None,
        description=(
            "base64 编码的图片数据。支持 png/jpg/jpeg/gif/webp/bmp 格式。"
            "直接传 base64 字符串即可，不需要 data:image/... 前缀。"
        ),
    )
    audio: Optional[str] = Field(
        default=None,
        description="base64 编码的音频数据（mp3/wav/m4a 格式），用于语音输入",
    )
    scene: str = Field(
        default="general",
        description="场景标签，可选值：general(通用), career(事业), beauty(颜值), love(恋爱), daily(日常)",
    )

    @model_validator(mode='after')
    def validate_text_or_image_or_audio(self):
        """
        验证 text、image、audio 至少要有一个不为空
        """
        if not self.text and not self.image and not self.audio:
            raise ValueError("text、image、audio 至少要有一个不为空")

        if self.image:
            img = self.image.strip()
            if not img:
                raise ValueError("image 字段不能为空字符串")
            if img.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                raise ValueError(
                    "image 字段似乎是文件名，请传入 base64 编码的图片数据，"
                    "而非文件路径"
                )

        return self


class ChatResponse(BaseModel):
    """
    交互式夸夸响应模型

    用于返回 AI 生成的夸夸文案
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "examples": [
                {
                    "content": "拖了两周还能坚持找到答案，这份不放弃的劲儿挺难得的。",
                    "scene": "career",
                    "has_image": False,
                    "image_desc": None,
                    "created_at": "2025-05-13T12:00:00+00:00",
                }
            ]
        },
    )
    
    content: str = Field(..., description="AI 生成的夸夸文案")
    scene: str = Field(
        ...,
        description="场景标签：general(通用), career(事业), beauty(颜值), love(恋爱), daily(日常)",
    )
    has_image: bool = Field(default=False, description="是否包含图片输入")
    image_desc: str | None = Field(default=None, description="AI 对图片的简短描述（仅多模态输入时有值）")
    is_random_mode: bool = Field(default=False, description="是否为随机模式生成的回复（A/B 测试埋点）")
    created_at: datetime = Field(default_factory=_utc_now, description="创建时间")
    debug: Optional[ChatDebugInfo] = Field(default=None, description="调试信息（仅 debug=true 时返回）")


# ==================== Admin 相关模型 ====================


class PromptUpdate(BaseModel):
    """更新 Prompt 请求模型"""
    system_prompt: str = Field(..., min_length=1, description="系统提示词")
    user_prompt: str = Field(default="", description="用户提示词")
    input_type: str = Field(default="text_only", description="输入类型")
    updated_by: str = Field(default="admin", description="更新者")


class PromptResponse(BaseModel):
    """Prompt 响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="Prompt ID")
    scene: str = Field(..., description="场景标识")
    system_prompt: str = Field(..., description="系统提示词")
    user_prompt: str = Field(default="", description="用户提示词")
    input_type: str = Field(default="text_only", description="输入类型")
    version: int = Field(default=1, description="版本号")
    is_active: bool = Field(default=True, description="是否激活")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")
    updated_by: str = Field(default="system", description="更新者")


class PromptTestRequest(BaseModel):
    """Prompt 测试请求模型"""
    test_input: str = Field(..., min_length=1, description="测试输入文本")
    temperature: float = Field(default=0.7, ge=0, le=2, description="采样温度")


class PromptTestResponse(BaseModel):
    """Prompt 测试响应模型"""
    output: str = Field(..., description="AI 生成输出")
    scene: str = Field(..., description="场景标识")
    prompt_version: int = Field(..., description="Prompt 版本号")


class ABTestCreate(BaseModel):
    """创建 AB 测试请求模型"""
    name: str = Field(..., min_length=1, description="测试名称")
    scene: str = Field(..., min_length=1, description="场景标识")
    prompt_a_id: int = Field(..., description="对照组 Prompt ID")
    prompt_b_id: int = Field(..., description="实验组 Prompt ID")
    traffic_ratio: float = Field(default=0.5, ge=0, le=1, description="实验组流量比例")


class ABTestUpdate(BaseModel):
    """更新 AB 测试请求模型"""
    name: Optional[str] = Field(default=None, description="测试名称")
    traffic_ratio: Optional[float] = Field(default=None, ge=0, le=1, description="实验组流量比例")
    status: Optional[str] = Field(default=None, description="状态: running/stopped")


class ABTestResponse(BaseModel):
    """AB 测试响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="测试 ID")
    name: str = Field(..., description="测试名称")
    scene: str = Field(..., description="场景标识")
    prompt_a_id: int = Field(..., description="对照组 Prompt ID")
    prompt_b_id: int = Field(..., description="实验组 Prompt ID")
    traffic_ratio: float = Field(..., description="实验组流量比例")
    status: str = Field(..., description="状态")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")


# ==================== 记忆模块相关模型 ====================


class SessionCreate(BaseModel):
    """创建短期会话请求模型"""
    session_id: str = Field(..., min_length=1, description="会话ID")
    user_id: str = Field(default="default", description="用户ID")


class SessionUpdate(BaseModel):
    """更新会话请求模型"""
    pass


class SessionResponse(BaseModel):
    """会话响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="会话记录 ID")
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    message_count: int = Field(default=0, description="消息总数")
    last_message_at: Optional[datetime] = Field(default=None, description="最后消息时间")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="消息列表（仅详情接口返回）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class UserProfileUpdate(BaseModel):
    """更新用户偏好请求模型"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prefer_scene": "career",
                    "prefer_style": "温柔治愈",
                    "user_tags": ["程序员", "内向"],
                    "last_emotion": "tired",
                }
            ]
        },
    )
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景，如 career/beauty/love/daily")
    prefer_style: Optional[str] = Field(default=None, description="喜欢的夸夸风格")
    user_tags: Optional[list[str]] = Field(default=None, description="用户标签列表")
    avoid_words: Optional[list[str]] = Field(default=None, description="避免的词汇")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
    personality_prefer: Optional[str] = Field(default=None, description="喜欢的人格类型：default/witty/chill/enthusiastic")
    humor_taste: Optional[str] = Field(default=None, description="喜欢的幽默类型：teasing/insightful/meme/ironic")
    tone_shift: Optional[bool] = Field(default=None, description="是否接受语气变化（有时正经有时搞笑）")


class UserProfileResponse(BaseModel):
    """用户偏好响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "user_id": "user_abc123",
                    "prefer_scene": "career",
                    "prefer_style": "温柔治愈",
                    "user_tags": ["程序员", "内向"],
                    "avoid_words": [],
                    "last_emotion": "tired",
                    "conversation_count": 15,
                    "favorite_count": 3,
                    "last_active": "2025-05-13T12:00:00+00:00",
                }
            ]
        },
    )

    id: int = Field(..., description="记录 ID")
    user_id: str = Field(..., description="用户ID")
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景，如 career/beauty/love/daily")
    prefer_style: Optional[str] = Field(default=None, description="喜欢的夸夸风格，如 温柔治愈/幽默搞笑/理性分析")
    user_tags: list[str] = Field(default_factory=list, description="用户标签")
    avoid_words: list[str] = Field(default_factory=list, description="避免词汇")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
    conversation_count: int = Field(default=0, description="对话次数")
    favorite_count: int = Field(default=0, description="收藏次数")
    last_active: Optional[datetime] = Field(default=None, description="最后活跃时间")
    personality_prefer: str = Field(default="default", description="喜欢的人格类型：default/witty/chill/enthusiastic")
    humor_taste: Optional[str] = Field(default=None, description="喜欢的幽默类型：teasing/insightful/meme/ironic")
    tone_shift: bool = Field(default=True, description="是否接受语气变化")


class MilestoneCreate(BaseModel):
    """创建里程碑请求模型"""
    user_id: str = Field(default="default", description="用户ID")
    content: str = Field(..., min_length=1, description="里程碑内容")
    source: str = Field(default="user_input", description="来源")
    importance: int = Field(default=1, ge=1, le=5, description="重要性")


class MilestoneResponse(BaseModel):
    """里程碑响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="记录 ID")
    user_id: str = Field(..., description="用户ID")
    content: str = Field(..., description="里程碑内容")
    source: Optional[str] = Field(default=None, description="来源")
    importance: int = Field(..., description="重要性")
    is_achieved: bool = Field(default=False, description="是否达成")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")


class ChatDebugInfo(BaseModel):
    """对话调试信息模型"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    system_prompt: str = Field(..., description="最终 system prompt（含记忆注入）")
    user_message: str = Field(..., description="发送给模型的用户消息")
    prompt_source: str = Field(..., description="prompt 来源：ab_test / db / template")
    input_type: str = Field(..., description="输入类型：text_only / image_only / mixed")
    memory_summary: Optional[dict[str, Any]] = Field(default=None, description="记忆汇总快照")
    mcp_connected: bool = Field(default=False, description="MCP 连接状态")
    mcp_calls: list[dict[str, Any]] = Field(default_factory=list, description="MCP 调用记录")
    extraction: Optional[dict[str, Any]] = Field(default=None, description="记忆提取结果")


class MemorySummary(BaseModel):
    """用户记忆汇总模型（用于注入Prompt）"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prefer_scene": "career",
                    "prefer_style": "温柔治愈",
                    "user_tags": ["程序员", "内向"],
                    "avoid_words": [],
                    "recent_messages": [
                        {"role": "user", "content": "今天加班到很晚"},
                        {"role": "assistant", "content": "加班到现在确实挺累的..."},
                    ],
                    "milestones": ["坚持跑步30天"],
                    "last_emotion": "tired",
                    "semantic_memories": ["用户之前提到喜欢简洁的夸赞风格"],
                    "personality_prefer": "default",
                    "humor_taste": None,
                    "tone_shift": False,
                }
            ]
        },
    )
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景，如 career/beauty/love/daily")
    prefer_style: Optional[str] = Field(default=None, description="偏好风格，如 温柔治愈/幽默搞笑")
    user_tags: list[str] = Field(default_factory=list, description="用户标签")
    avoid_words: list[str] = Field(default_factory=list, description="避免词汇")
    recent_messages: list[dict[str, Any]] = Field(default_factory=list, description="最近消息")
    milestones: list[str] = Field(default_factory=list, description="高光里程碑")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
    semantic_memories: list[str] = Field(default_factory=list, description="语义记忆（supermemory）")

    # 人格偏好（新增）
    personality_prefer: str = Field(
        default="default",
        description="喜欢的人格类型：default/witty/chill/enthusiastic"
    )
    humor_taste: Optional[str] = Field(
        default=None,
        description="喜欢的幽默类型：teasing/insightful/meme/ironic"
    )
    tone_shift: bool = Field(
        default=True,
        description="是否接受语气转变（有时正经有时搞笑）"
    )
