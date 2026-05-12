"""
SQLAlchemy ORM 模型定义

定义数据库表结构，支持 PostgreSQL 和 SQLite
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.models.database import Base


def _utc_now() -> datetime:
    """返回带时区信息的 UTC 时间"""
    return datetime.now(timezone.utc)


class Favorite(Base):
    """收藏表 ORM 模型"""
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="default", index=True)
    content = Column(Text, nullable=False)
    scene = Column(String(50), nullable=False, default="general")
    created_at = Column(DateTime, default=_utc_now)


class Prompt(Base):
    """Prompt 模板表 ORM 模型 - 支持 prompt 热更新"""
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene = Column(String(50), nullable=False, unique=True, index=True)
    system_prompt = Column(Text, nullable=False)
    user_prompt = Column(Text, nullable=False, default="")
    input_type = Column(String(20), nullable=False, default="text_only")
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
    updated_by = Column(String(100), nullable=False, default="system")


class ABTest(Base):
    """AB 测试配置表 ORM 模型"""
    __tablename__ = "ab_tests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    scene = Column(String(50), nullable=False, index=True)
    prompt_a_id = Column(Integer, ForeignKey("prompts.id"), nullable=True)
    prompt_b_id = Column(Integer, ForeignKey("prompts.id"), nullable=True)
    traffic_ratio = Column(Float, nullable=False, default=0.5)
    status = Column(String(20), nullable=False, default="running")
    created_at = Column(DateTime, default=_utc_now)

    # 关系
    prompt_a = relationship("Prompt", foreign_keys=[prompt_a_id])
    prompt_b = relationship("Prompt", foreign_keys=[prompt_b_id])


class Session(Base):
    """
    短期会话记忆表 ORM 模型
    
    存储用户单次打开小程序的对话上下文，包括最近3-5轮对话、场景和情绪状态。
    会话2小时后自动过期（通过 created_at 字段计算）。
    """
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    user_id = Column(String(100), nullable=False, default="default", index=True)
    scene = Column(String(50), nullable=False, default="general")
    messages = Column(Text, nullable=False, default="[]")  # JSON格式存储消息列表
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class UserProfile(Base):
    """
    用户偏好记忆表 ORM 模型
    
    核心层：存储用户的个性化偏好，用于生成千人千面的夸夸内容。
    包括最喜欢的场景、喜欢的风格、用户标签、避免的词汇、最近情绪状态。
    """
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, unique=True, index=True)
    prefer_scene = Column(String(50), nullable=True)  # 最喜欢的场景
    prefer_style = Column(String(50), nullable=True)  # 喜欢的夸夸风格（温柔/元气/搞笑等）
    user_tags = Column(Text, nullable=True, default="[]")  # JSON格式，自动提取的用户标签
    avoid_words = Column(Text, nullable=True, default="[]")  # JSON格式，用户不喜欢的词
    last_emotion = Column(String(50), nullable=True)  # 最近一次情绪状态
    conversation_count = Column(Integer, nullable=False, default=0)  # 对话次数累计
    favorite_count = Column(Integer, nullable=False, default=0)  # 收藏次数累计
    last_active = Column(DateTime, default=_utc_now)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class Milestone(Base):
    """
    高光里程碑记忆表 ORM 模型
    
    存储用户的小成就、小骄傲、高光时刻，用于夸得真诚不油腻。
    例如：完成项目上线、坚持跑步、学习进步等。
    """
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    content = Column(Text, nullable=False)  # 里程碑内容
    source = Column(String(50), nullable=True)  # 来源：user_input / favorite / manual
    importance = Column(Integer, nullable=False, default=1)  # 重要性：1-5
    is_achieved = Column(Boolean, nullable=False, default=False)  # 是否已达成
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


