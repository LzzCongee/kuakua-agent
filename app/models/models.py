"""
SQLAlchemy ORM 模型定义

定义数据库表结构，支持 PostgreSQL 和 SQLite
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.models.database import Base


class Favorite(Base):
    """收藏表 ORM 模型"""
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="default", index=True)
    content = Column(Text, nullable=False)
    scene = Column(String(50), nullable=False, default="general")
    created_at = Column(DateTime, default=datetime.utcnow)


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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    prompt_a = relationship("Prompt", foreign_keys=[prompt_a_id])
    prompt_b = relationship("Prompt", foreign_keys=[prompt_b_id])
