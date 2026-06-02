"""
收藏管理服务模块

使用 SQLAlchemy AsyncSession 实现用户收藏的增删改查功能

收藏动作语义:对回复 topic 的点赞(对回复内容表示认同),
通过 TopicPreferenceService 聚合到 UserTopicPreference,
供后续 prompt 注入(上下文 cache 友好)。
设计依据: docs/greeting-topic-personalization-design-v2.md 第十章
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import DatabaseException, NotFoundException
from ..core.logging import get_logger
from ..models.models import Favorite, Message
from ..models.schemas import FavoriteCreate, FavoriteResponse
from .chat_service import ALLOWED_TOPICS
from .topic_preference_service import TopicPreferenceService

logger = get_logger(__name__)


class FavoriteService:
    """
    收藏管理服务类

    封装用户收藏夸夸语录的业务逻辑,包括列表查询、添加、删除等操作。
    收藏 = 对该回复 topic 的点赞,会触发 topic 偏好聚合。

    Example:
        >>> service = FavoriteService()
        >>> favorites = await service.list_favorites("user123", session)
        >>> new_favorite = await service.add_favorite("user123", FavoriteCreate(content="你真棒！"), session)
    """

    async def list_favorites(
        self, user_id: str, session: AsyncSession
    ) -> list[FavoriteResponse]:
        """
        获取用户的收藏列表

        查询指定用户的所有收藏记录，按创建时间倒序排列。

        Args:
            user_id: 用户标识
            session: 数据库会话

        Returns:
            list[FavoriteResponse]: 收藏记录列表

        Raises:
            DatabaseException: 当数据库查询失败时抛出
        """
        try:
            stmt = (
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                FavoriteResponse(
                    id=row.id,
                    content=row.content,
                    scene=row.scene,
                    created_at=row.created_at if isinstance(row.created_at, datetime) else datetime.fromisoformat(row.created_at),
                )
                for row in rows
            ]
        except Exception as e:
            raise DatabaseException(f"查询收藏列表失败: {str(e)}")

    async def add_favorite(
        self,
        user_id: str,
        data: FavoriteCreate,
        session: AsyncSession,
    ) -> FavoriteResponse:
        """
        添加收藏记录(语义:对回复 topic 的点赞)

        topic 解析 3 级兜底:
        1) 请求体里的 scene(若为 ALLOWED_TOPICS 之一)
        2) 从最近 assistant Message 按 content 反查(命中则用其 topic)
        3) 兜底 general

        触发 TopicPreferenceService 聚合,刷新 snapshot。

        Args:
            user_id: 用户标识
            data: 收藏创建数据,包含内容和场景
            session: 数据库会话(由调用方 commit)

        Returns:
            FavoriteResponse: 新创建的收藏记录(包含生成的 ID 和时间戳)

        Raises:
            DatabaseException: 当数据库插入失败时抛出
        """
        try:
            # 1) 决定 topic(3 级兜底)
            topic = await self._resolve_topic(data, session)
            if topic != data.scene:
                logger.debug(
                    f"topic 兜底 | user={user_id} | request_scene={data.scene} | resolved={topic}"
                )

            # 2) 写 favorite(resolved topic 作为 scene 持久化)
            favorite = Favorite(
                user_id=user_id,
                content=data.content,
                scene=topic,
            )
            session.add(favorite)
            await session.flush()

            # 3) 触发偏好聚合(同 session 内,调用方 commit)
            pref_service = TopicPreferenceService()
            await pref_service.on_favorite_added(user_id, topic, session)

            return FavoriteResponse(
                id=favorite.id,
                content=favorite.content,
                scene=favorite.scene,
                created_at=favorite.created_at,
            )
        except Exception as e:
            raise DatabaseException(f"添加收藏失败: {str(e)}")

    async def _resolve_topic(
        self,
        data: FavoriteCreate,
        session: AsyncSession,
    ) -> str:
        """
        解析收藏对应的 topic(3 级兜底)

        1) data.scene 命中 ALLOWED_TOPICS → 直接用
        2) 反查 Message 表(同 content 的最近 assistant 消息的 topic)→ 用其 topic
        3) 兜底 general
        """
        # 1) 请求里带的 scene
        if data.scene and data.scene in ALLOWED_TOPICS:
            return data.scene

        # 2) 反查 Message(同 content 的最近 assistant 消息的 topic)
        #    走 (role, content) 复合索引,O(log n) 定位
        row = (
            await session.execute(
                select(Message)
                .where(
                    Message.role == "assistant",
                    Message.content == data.content,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row and row.topic in ALLOWED_TOPICS:
            return row.topic

        # 3) 兜底
        return "general"

    async def delete_favorite(
        self, user_id: str, favorite_id: int, session: AsyncSession
    ) -> bool:
        """
        删除单条收藏记录(语义:撤销一次对该 topic 的认同)

        删除前先记录 topic,删除后触发 TopicPreferenceService 扣减并刷新 snapshot。

        Args:
            user_id: 用户标识
            favorite_id: 收藏记录 ID
            session: 数据库会话

        Returns:
            bool: 删除成功返回 True

        Raises:
            NotFoundException: 当收藏记录不存在时抛出
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            # 先检查记录是否存在且属于该用户
            stmt = select(Favorite).where(
                Favorite.id == favorite_id, Favorite.user_id == user_id
            )
            result = await session.execute(stmt)
            favorite = result.scalar_one_or_none()

            if not favorite:
                raise NotFoundException(f"收藏记录不存在: {favorite_id}")

            # 删除前捕获 topic(general 也会被减,但 is_general 守护在 service 内)
            topic = favorite.scene if favorite.scene in ALLOWED_TOPICS else "general"

            await session.delete(favorite)
            await session.flush()

            # 触发偏好聚合(同 session 内)
            pref_service = TopicPreferenceService()
            await pref_service.on_favorite_removed(user_id, topic, session)
            return True
        except NotFoundException:
            raise
        except Exception as e:
            raise DatabaseException(f"删除收藏失败: {str(e)}")

    async def clear_favorites(
        self, user_id: str, session: AsyncSession
    ) -> int:
        """
        清空用户所有收藏

        删除指定用户的所有收藏记录,同时清空该用户的 topic 偏好聚合
        (视为全部撤销,直接重置 snapshot)。

        Args:
            user_id: 用户标识
            session: 数据库会话

        Returns:
            int: 删除的记录数量

        Raises:
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            stmt = delete(Favorite).where(Favorite.user_id == user_id)
            result = await session.execute(stmt)
            await session.flush()

            # 重置 topic 偏好(简单粗暴:删除所有聚合行 + 清空 snapshot)
            # 比按条 decrement 快得多,且语义上"全部清空"就该抹除历史
            from ..models.models import UserProfile, UserTopicPreference

            await session.execute(
                delete(UserTopicPreference).where(
                    UserTopicPreference.user_id == user_id
                )
            )
            await session.execute(
                UserProfile.__table__.update()
                .where(UserProfile.user_id == user_id)
                .values(topic_preference_snapshot=None)
            )
            logger.info(f"清空 topic 偏好 | user={user_id}")
            return result.rowcount
        except Exception as e:
            raise DatabaseException(f"清空收藏失败: {str(e)}")
