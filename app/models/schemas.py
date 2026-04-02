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
