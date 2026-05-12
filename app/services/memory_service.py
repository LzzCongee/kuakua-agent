"""
记忆服务模块

提供三层记忆管理功能：
1. 短期会话记忆 - 用户单次会话的上下文
2. 用户偏好记忆 - 个性化偏好和标签
3. 高光里程碑记忆 - 用户的小成就、小骄傲

所有方法均为异步操作，支持 PostgreSQL 和 SQLite
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Session, UserProfile, Milestone 
from ..models.schemas import (  
    MemorySummary,
    UserProfileUpdate,
    MilestoneCreate,
)


class MemoryService:
    """
    记忆服务类
    
    提供记忆的 CRUD 操作，用于支持夸夸 Agent 的个性化生成。
    所有方法均支持异步操作。
    """

    def __init__(self, session: AsyncSession, mcp: Any = None):
        """
        初始化 MemoryService

        Args:
            session: 数据库会话（由 FastAPI 依赖注入或 get_db() 获取）
            mcp: MCP Client 实例（可选，默认使用全局单例）
        """
        self.session = session
        self._mcp = mcp

    @property
    def mcp(self) -> Any:
        """获取 MCP Client（延迟导入避免循环依赖）"""
        if self._mcp is not None:
            return self._mcp
        from app.core.mcp_client import mcp_client  # pyright: ignore
        return mcp_client

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

    async def get_session(self, session_id: str) -> Session | None:
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

    async def update_session(self, session_id: str, messages: list[dict[str, Any]]) -> Session | None:
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
            session.messages = json.dumps(messages, ensure_ascii=False)  # pyright: ignore[reportAttributeAccessIssue]
            session.updated_at = datetime.now(timezone.utc)  # pyright: ignore[reportAttributeAccessIssue]
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
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = delete(Session).where(Session.created_at < cutoff)
        result = await self.session.execute(stmt)
        return result.rowcount  # pyright: ignore[reportAttributeAccessIssue]

    # ==================== 用户偏好记忆 ====================

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
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
            profile.prefer_scene = data.prefer_scene  # pyright: ignore[reportAttributeAccessIssue]
        if data.prefer_style is not None:
            profile.prefer_style = data.prefer_style  # pyright: ignore[reportAttributeAccessIssue]
        if data.user_tags is not None:
            profile.user_tags = json.dumps(data.user_tags, ensure_ascii=False)  # pyright: ignore[reportAttributeAccessIssue]
        if data.avoid_words is not None:
            profile.avoid_words = json.dumps(data.avoid_words, ensure_ascii=False)  # pyright: ignore[reportAttributeAccessIssue]
        if data.last_emotion is not None:
            profile.last_emotion = data.last_emotion  # pyright: ignore[reportAttributeAccessIssue]
        
        # 更新活跃时间和对话计数
        profile.last_active = datetime.now(timezone.utc)  # pyright: ignore[reportAttributeAccessIssue]
        profile.conversation_count = (profile.conversation_count or 0) + 1  # pyright: ignore[reportAttributeAccessIssue]
        
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
        profile.favorite_count = (profile.favorite_count or 0) + 1  # pyright: ignore[reportAttributeAccessIssue]
        profile.last_active = datetime.now(timezone.utc)  # pyright: ignore[reportAttributeAccessIssue]
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
        profile.prefer_scene = scene  # pyright: ignore[reportAttributeAccessIssue]
        profile.last_active = datetime.now(timezone.utc)  # pyright: ignore[reportAttributeAccessIssue]
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

    async def extract_and_add_milestone(self, user_id: str, content: str) -> Milestone | None:
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

    # ==================== supermemory 语义记忆 ====================

    async def _get_semantic_memories(self, user_id: str) -> list[str]:
        """
        基于用户画像构建查询，通过 MCP 调用 search_memory

        Args:
            user_id: 用户ID

        Returns:
            List[str]: 语义相关记忆列表
        """
        profile = await self.get_user_profile(user_id)
        if not profile:
            return []

        # 构建语义查询：结合用户标签 + 偏好场景 + 最近情绪
        query_parts: list[str] = []
        if str(profile.user_tags):  # pyright: ignore[reportGeneralTypeIssues]
            try:
                tags = json.loads(str(profile.user_tags))
                query_parts.extend(tags[:3])
            except json.JSONDecodeError:
                pass
        if str(profile.prefer_scene):  # pyright: ignore[reportGeneralTypeIssues]
            query_parts.append(str(profile.prefer_scene))
        if str(profile.last_emotion):  # pyright: ignore[reportGeneralTypeIssues]
            query_parts.append(str(profile.last_emotion))

        if not query_parts:
            return []

        query = " ".join(query_parts)

        # 通过 MCP SDK 调用 search_memory 工具
        result = await self.mcp.call(
            "search_memory",
            query=query,
            user_id=user_id,
            top_k=3,
        )

        if not result:
            return []

        # 解析返回结果
        return [item.get("content", "") for item in result.get("results", [])]

    async def save_chat_to_supermemory(
        self,
        user_id: str,
        user_message: str,
        ai_response: str,
        scene: str = "general",
        emotion: str | None = None,
    ) -> None:
        """
        通过 MCP 调用 add_memory 将对话保存到语义记忆

        Args:
            user_id: 用户ID
            user_message: 用户消息
            ai_response: AI 回复
            scene: 场景标签
            emotion: 情绪标签
        """
        content = f"用户说：{user_message}\nAI回复：{ai_response}"

        await self.mcp.call(
            "add_memory",
            content=content,
            user_id=user_id,
            metadata={
                "type": "chat",
                "scene": scene,
                "emotion": emotion,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ==================== 记忆汇总（用于 Prompt 注入）====================

    async def get_memory_summary(self, user_id: str, session_id: str | None = None) -> MemorySummary:
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
        user_tags: list[str] = []
        avoid_words: list[str] = []
        prefer_scene: str | None = None
        prefer_style: str | None = None
        last_emotion: str | None = None
        
        if profile:
            prefer_scene = str(profile.prefer_scene) if str(profile.prefer_scene) else None  # pyright: ignore[reportAttributeAccessIssue]
            prefer_style = str(profile.prefer_style) if str(profile.prefer_style) else None  # pyright: ignore[reportAttributeAccessIssue]
            last_emotion = str(profile.last_emotion) if str(profile.last_emotion) else None  # pyright: ignore[reportAttributeAccessIssue]
            if str(profile.user_tags):  # pyright: ignore[reportGeneralTypeIssues]
                try:
                    user_tags = json.loads(str(profile.user_tags))
                except (json.JSONDecodeError, TypeError):
                    user_tags = []
            if str(profile.avoid_words):  # pyright: ignore[reportGeneralTypeIssues]
                try:
                    avoid_words = json.loads(str(profile.avoid_words))
                except (json.JSONDecodeError, TypeError):
                    avoid_words = []
        
        # 获取最近会话
        recent_messages: list[dict[str, Any]] = []
        if session_id:
            session = await self.get_session(session_id)
            if session and str(session.messages):  # pyright: ignore[reportGeneralTypeIssues]
                try:
                    recent_messages = json.loads(str(session.messages))
                except (json.JSONDecodeError, TypeError):
                    recent_messages = []
        
        # 获取高光里程碑
        milestones = await self.get_milestones(user_id, limit=5)
        milestone_contents = [str(m.content) for m in milestones]
        
        # 获取语义记忆（supermemory）
        semantic_memories = await self._get_semantic_memories(user_id)
        
        return MemorySummary(
            prefer_scene=prefer_scene,
            prefer_style=prefer_style,
            user_tags=user_tags,
            avoid_words=avoid_words,
            recent_messages=recent_messages[-3:] if recent_messages else [],
            milestones=milestone_contents,
            last_emotion=last_emotion,
            semantic_memories=semantic_memories,
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

        # 语义记忆（来自 supermemory）
        if memory.semantic_memories:
            parts.append(f"相关记忆：{'; '.join(memory.semantic_memories[:2])}")

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
    # 注意：此函数需要在异步上下文中使用，并且 get_db() 是生成器
    # 实际使用时应该通过依赖注入获取 session
    raise NotImplementedError("请通过 FastAPI 依赖注入使用 MemoryService")