"""
记忆服务模块

提供三层记忆管理功能：
1. 短期会话记忆 - 用户单次会话的上下文
2. 用户偏好记忆 - 个性化偏好和标签
3. 高光里程碑记忆 - 用户的小成就、小骄傲

所有方法均为异步操作，支持 PostgreSQL 和 SQLite
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Session, UserProfile, Milestone
from app.models.database import get_db
from app.models.schemas import (
    MemorySummary,
    SessionCreate,
    SessionUpdate,
    UserProfileUpdate,
    MilestoneCreate,
)


class MemoryService:
    """
    记忆服务类
    
    提供记忆的 CRUD 操作，用于支持夸夸 Agent 的个性化生成。
    所有方法均支持异步操作。
    """

    def __init__(self, session: AsyncSession):
        """
        初始化 MemoryService
        
        Args:
            session: 数据库会话（由 FastAPI 依赖注入或 get_db() 获取）
        """
        self.session = session

    # ==================== 短期会话记忆 ====================

    async def get_or_create_session(
        self, user_id: str, session_id: str, scene: str = "general"
    ) -> Session:
        """
        获取或创建会话
        
        Args:
            user_id: 用户ID
            session_id: 会话ID（前端生成）
            scene: 场景标签
            
        Returns:
            Session: 会话记录
        """
        stmt = select(Session).where(Session.session_id == session_id)
        result = await self.session.execute(stmt)
        session_obj = result.scalar_one_or_none()
        
        if not session_obj:
            session_obj = Session(
                session_id=session_id,
                user_id=user_id,
                scene=scene,
                messages="[]"
            )
            self.session.add(session_obj)
            await self.session.flush()
        
        return session_obj

    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        根据 session_id 获取会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[Session]: 会话记录，不存在则返回 None
        """
        stmt = select(Session).where(Session.session_id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_session(self, session_id: str, messages: list[dict]) -> Optional[Session]:
        """
        更新会话消息
        
        Args:
            session_id: 会话ID
            messages: 新的消息列表
            
        Returns:
            Optional[Session]: 更新后的会话记录
        """
        session = await self.get_session(session_id)
        if session:
            session.messages = json.dumps(messages, ensure_ascii=False)
            session.updated_at = datetime.utcnow()
            await self.session.flush()
        return session

    async def get_recent_sessions(self, user_id: str, limit: int = 5) -> list[Session]:
        """
        获取用户最近的会话记录
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            list[Session]: 会话列表（按时间倒序）
        """
        stmt = (
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cleanup_expired_sessions(self, hours: int = 2) -> int:
        """
        清理过期的会话记录（默认2小时）
        
        Args:
            hours: 过期小时数
            
        Returns:
            int: 删除的记录数
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = delete(Session).where(Session.created_at < cutoff)
        result = await self.session.execute(stmt)
        return result.rowcount

    # ==================== 用户偏好记忆 ====================

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        获取用户偏好记录
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[UserProfile]: 用户偏好记录
        """
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_profile(self, user_id: str) -> UserProfile:
        """
        获取或创建用户偏好记录
        
        Args:
            user_id: 用户ID
            
        Returns:
            UserProfile: 用户偏好记录
        """
        profile = await self.get_user_profile(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def update_user_profile(self, user_id: str, data: UserProfileUpdate) -> UserProfile:
        """
        更新用户偏好
        
        Args:
            user_id: 用户ID
            data: 偏好更新数据
            
        Returns:
            UserProfile: 更新后的用户偏好
        """
        profile = await self.get_or_create_profile(user_id)
        
        # 更新字段（只更新非 None 的字段）
        if data.prefer_scene is not None:
            profile.prefer_scene = data.prefer_scene
        if data.prefer_style is not None:
            profile.prefer_style = data.prefer_style
        if data.user_tags is not None:
            profile.user_tags = json.dumps(data.user_tags, ensure_ascii=False)
        if data.avoid_words is not None:
            profile.avoid_words = json.dumps(data.avoid_words, ensure_ascii=False)
        if data.last_emotion is not None:
            profile.last_emotion = data.last_emotion
        
        # 更新活跃时间和对话计数
        profile.last_active = datetime.utcnow()
        profile.conversation_count = (profile.conversation_count or 0) + 1
        
        await self.session.flush()
        return profile

    async def increment_favorite_count(self, user_id: str) -> UserProfile:
        """
        增加用户收藏次数
        
        Args:
            user_id: 用户ID
            
        Returns:
            UserProfile: 更新后的用户偏好
        """
        profile = await self.get_or_create_profile(user_id)
        profile.favorite_count = (profile.favorite_count or 0) + 1
        profile.last_active = datetime.utcnow()
        await self.session.flush()
        return profile

    async def update_prefer_scene(self, user_id: str, scene: str) -> UserProfile:
        """
        更新用户偏好场景（根据使用频率自动调整）
        
        Args:
            user_id: 用户ID
            scene: 场景标签
            
        Returns:
            UserProfile: 更新后的用户偏好
        """
        profile = await self.get_or_create_profile(user_id)
        profile.prefer_scene = scene
        profile.last_active = datetime.utcnow()
        await self.session.flush()
        return profile

    # ==================== 高光里程碑记忆 ====================

    async def get_milestones(self, user_id: str, limit: int = 10) -> list[Milestone]:
        """
        获取用户的高光里程碑
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            list[Milestone]: 里程碑列表（按重要性降序）
        """
        stmt = (
            select(Milestone)
            .where(Milestone.user_id == user_id)
            .order_by(Milestone.importance.desc(), Milestone.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_milestone(self, data: MilestoneCreate) -> Milestone:
        """
        添加高光里程碑
        
        Args:
            data: 里程碑数据
            
        Returns:
            Milestone: 新增的里程碑记录
        """
        milestone = Milestone(
            user_id=data.user_id,
            content=data.content,
            source=data.source,
            importance=data.importance
        )
        self.session.add(milestone)
        await self.session.flush()
        return milestone

    async def extract_and_add_milestone(self, user_id: str, content: str) -> Optional[Milestone]:
        """
        从对话内容中提取并添加里程碑
        
        检测内容是否包含成就类关键词，如果是则自动创建里程碑。
        
        Args:
            user_id: 用户ID
            content: 对话内容
            
        Returns:
            Optional[Milestone]: 新增的里程碑（如果没有提取到成就则返回 None）
        """
        achievement_keywords = [
            "完成", "达成", "通过", "拿到", "获得",
            "坚持", "成功", "突破", "进步", "提升"
        ]
        
        # 简单检测是否有成就相关关键词
        has_achievement = any(kw in content for kw in achievement_keywords)
        
        if has_achievement:
            return await self.add_milestone(MilestoneCreate(
                user_id=user_id,
                content=content[:200],  # 截取前200字符
                source="user_input",
                importance=2
            ))
        
        return None

    # ==================== 记忆汇总（用于 Prompt 注入）====================

    async def get_memory_summary(self, user_id: str, session_id: Optional[str] = None) -> MemorySummary:
        """
        获取用户记忆汇总（用于注入到 Prompt）
        
        整合用户偏好、会话历史和里程碑，生成统一的记忆摘要。
        
        Args:
            user_id: 用户ID
            session_id: 可选的当前会话ID
            
        Returns:
            MemorySummary: 记忆汇总对象
        """
        # 获取用户偏好
        profile = await self.get_user_profile(user_id)
        
        # 解析 JSON 字段
        user_tags = []
        avoid_words = []
        if profile and profile.user_tags:
            try:
                user_tags = json.loads(profile.user_tags)
            except json.JSONDecodeError:
                user_tags = []
        if profile and profile.avoid_words:
            try:
                avoid_words = json.loads(profile.avoid_words)
            except json.JSONDecodeError:
                avoid_words = []
        
        # 获取最近会话
        recent_messages = []
        if session_id:
            session = await self.get_session(session_id)
            if session and session.messages:
                try:
                    recent_messages = json.loads(session.messages)
                except json.JSONDecodeError:
                    recent_messages = []
        
        # 获取高光里程碑
        milestones = await self.get_milestones(user_id, limit=5)
        milestone_contents = [m.content for m in milestones]
        
        return MemorySummary(
            prefer_scene=profile.prefer_scene if profile else None,
            prefer_style=profile.prefer_style if profile else None,
            user_tags=user_tags,
            recent_messages=recent_messages[-3:] if recent_messages else [],  # 只取最近3条
            milestones=milestone_contents,
            last_emotion=profile.last_emotion if profile else None
        )

    def format_memory_for_prompt(self, memory: MemorySummary) -> str:
        """
        将记忆汇总格式化为 Prompt 注入字符串
        
        Args:
            memory: 记忆汇总对象
            
        Returns:
            str: 格式化的记忆字符串
        """
        parts = []
        
        if memory.prefer_scene:
            parts.append(f"偏好场景：{memory.prefer_scene}")
        if memory.prefer_style:
            parts.append(f"喜欢风格：{memory.prefer_style}")
        if memory.user_tags:
            parts.append(f"用户标签：{', '.join(memory.user_tags[:5])}")  # 最多5个标签
        if memory.last_emotion:
            parts.append(f"当前情绪：{memory.last_emotion}")
        
        if memory.recent_messages:
            msg_str = "; ".join([
                f"{m.get('role', 'user')}: {m.get('content', '')[:50]}"
                for m in memory.recent_messages[-3:]
            ])
            parts.append(f"最近对话：{msg_str}")
        
        if memory.milestones:
            parts.append(f"高光时刻：{'; '.join(memory.milestones[:3])}")
        
        if not parts:
            return ""
        
        return "【用户记忆】\n" + "\n".join(parts)


# ==================== 便捷工厂函数（用于非依赖注入场景）====================

async def get_memory_service() -> MemoryService:
    """
    获取 MemoryService 实例（用于非 FastAPI 依赖注入场景）
    
    Returns:
        MemoryService: 记忆服务实例
    """
    async for session in get_db():
        return MemoryService(session)