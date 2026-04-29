"""
Pydantic 模型定义模块

定义 API 请求和响应的数据模型
"""

from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuoteResponse(BaseModel):
    """
    夸夸语录响应模型
    
    用于返回生成的夸夸内容
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )
    
    content: str = Field(..., description="夸夸语录内容")
    scene: str = Field(default="general", description="场景标签")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class FavoriteCreate(BaseModel):
    """
    创建收藏请求模型
    
    用于接收用户收藏夸夸语录的请求
    """
    content: str = Field(..., min_length=1, description="夸夸语录内容")
    scene: str = Field(default="general", description="场景标签")


class FavoriteResponse(BaseModel):
    """
    收藏响应模型
    
    用于返回收藏记录的完整信息
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
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
        json_encoders={datetime: lambda v: v.isoformat()}
    )
    
    code: int = Field(default=0, description="状态码，0 表示成功")
    message: str = Field(default="success", description="状态消息")
    data: Optional[T] = Field(default=None, description="响应数据")


class ChatRequest(BaseModel):
    """
    交互式夸夸请求模型
    
    用于接收用户发送的文字和图片，生成个性化的夸赞文案
    """
    text: Optional[str] = Field(default=None, description="用户输入的文字")
    image: Optional[str] = Field(default=None, description="base64 编码的图片数据")
    scene: str = Field(default="general", description="可选场景标签")
    
    @model_validator(mode='after')
    def validate_text_or_image(self):
        """
        验证 text 和 image 至少要有一个不为空
        """
        if not self.text and not self.image:
            raise ValueError("text 和 image 至少要有一个不为空")
        return self


class ChatResponse(BaseModel):
    """
    交互式夸夸响应模型
    
    用于返回 AI 生成的夸夸文案
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )
    
    content: str = Field(..., description="AI 生成的夸夸文案")
    scene: str = Field(..., description="场景标签")
    has_image: bool = Field(default=False, description="是否包含图片输入")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


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
    scene: str = Field(default="general", description="场景标签")
    messages: list[dict] = Field(default_factory=list, description="消息列表")


class SessionUpdate(BaseModel):
    """更新会话请求模型"""
    messages: list[dict] = Field(..., description="消息列表")
    scene: Optional[str] = Field(default=None, description="场景标签")


class SessionResponse(BaseModel):
    """会话响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="会话记录 ID")
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    scene: str = Field(..., description="场景标签")
    messages: list[dict] = Field(default_factory=list, description="消息列表")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class UserProfileUpdate(BaseModel):
    """更新用户偏好请求模型"""
    prefer_scene: Optional[str] = Field(default=None, description="喜欢的场景")
    prefer_style: Optional[str] = Field(default=None, description="喜欢的夸夸风格")
    user_tags: Optional[list[str]] = Field(default=None, description="用户标签列表")
    avoid_words: Optional[list[str]] = Field(default=None, description="避免的词汇")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")


class UserProfileResponse(BaseModel):
    """用户偏好响应模型"""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: int = Field(..., description="记录 ID")
    user_id: str = Field(..., description="用户ID")
    prefer_scene: Optional[str] = Field(default=None, description="喜欢的场景")
    prefer_style: Optional[str] = Field(default=None, description="喜欢的风格")
    user_tags: list[str] = Field(default_factory=list, description="用户标签")
    avoid_words: list[str] = Field(default_factory=list, description="避免词汇")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
    conversation_count: int = Field(default=0, description="对话次数")
    favorite_count: int = Field(default=0, description="收藏次数")
    last_active: Optional[datetime] = Field(default=None, description="最后活跃时间")


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
    created_at: datetime = Field(..., description="创建时间")


class MemorySummary(BaseModel):
    """用户记忆汇总模型（用于注入Prompt）"""
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景")
    prefer_style: Optional[str] = Field(default=None, description="偏好风格")
    user_tags: list[str] = Field(default_factory=list, description="用户标签")
    recent_messages: list[dict] = Field(default_factory=list, description="最近消息")
    milestones: list[str] = Field(default_factory=list, description="高光里程碑")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
