"""
SQLAlchemy ORM 模型定义

使用 SQLAlchemy 2.0 声明式风格（Mapped + mapped_column），
提供完整的类型推断支持，让 mypy/pyright 能正确推导属性类型。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..models.database import Base


def _utc_now() -> datetime:
    """返回带时区信息的 UTC 时间"""
    return datetime.now(UTC)


class Favorite(Base):
    """收藏表 ORM 模型"""
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scene: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


class Prompt(Base):
    """Prompt 模板表 ORM 模型 - 支持 prompt 热更新"""
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text_only")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")


class ABTest(Base):
    """AB 测试配置表 ORM 模型"""
    __tablename__ = "ab_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scene: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt_a_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("prompts.id"), nullable=True)
    prompt_b_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("prompts.id"), nullable=True)
    traffic_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now)

    # 关系
    prompt_a: Mapped[Prompt | None] = relationship("Prompt", foreign_keys=[prompt_a_id])
    prompt_b: Mapped[Prompt | None] = relationship("Prompt", foreign_keys=[prompt_b_id])


class Session(Base):
    """
    会话记忆表 ORM 模型

    存储用户会话的元数据（一个用户对应一个持续会话）。
    具体消息内容存储在 messages 表中。
    """
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default", index=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)

    # 关系
    messages: Mapped[list[Message]] = relationship("Message", back_populates="session", lazy="selectin")


class Message(Base):
    """
    消息表 ORM 模型

    存储每条对话消息，支持请求追踪和独立操作。
    每条消息都有唯一的 trace_id 用于关联日志和错误追踪。
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), ForeignKey("sessions.session_id"), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # 请求追踪ID
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 消息内容
    message_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text / image / mixed
    has_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_desc: Mapped[str | None] = mapped_column(Text, nullable=True)  # 图片描述（多模态）
    scene: Mapped[str] = mapped_column(String(50), nullable=False, default="general")  # 场景标签
    emotion: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 检测到的情绪
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)  # token消耗（可选）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)

    # 关系
    session: Mapped[Session] = relationship("Session", back_populates="messages")


class UserProfile(Base):
    """
    用户偏好记忆表 ORM 模型
    
    核心层：存储用户的个性化偏好，用于生成千人千面的夸夸内容。
    包括最喜欢的场景、喜欢的风格、用户标签、避免的词汇、最近情绪状态。
    """
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    prefer_scene: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prefer_style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_tags: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")
    avoid_words: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")
    last_emotion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conversation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    favorite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


class Milestone(Base):
    """
    高光里程碑记忆表 ORM 模型
    
    存储用户的小成就、小骄傲、高光时刻，用于夸得真诚不油腻。
    例如：完成项目上线、坚持跑步、学习进步等。
    """
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_achieved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)
