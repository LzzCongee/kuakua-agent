"""
Topic 偏好聚合服务

负责:
- 收藏动作 = 对该回复 topic 的点赞,递增 like_count
- 取消收藏 = 撤销一次认同,递减 like_count
- 按 user × topic 维度聚合,生成衰减权重后的偏好快照
- 冷启动门控:总点赞 < 3 时不返回偏好

设计依据: docs/greeting-topic-personalization-design-v2.md 第九章
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..models.models import UserProfile, UserTopicPreference

logger = get_logger(__name__)


# 算法参数
HALF_LIFE_DAYS: int = 14
INJECTION_THRESHOLD_TOTAL: int = 3
CLEAR_LEAD_RATIO: float = 1.5
MAX_INJECTED_TOPICS: int = 3
STRONG_THRESHOLD: float = 5.0
MEDIUM_THRESHOLD: float = 2.0


class TopicPreferenceService:
    """
    Topic 偏好聚合服务

    使用方法:
        service = TopicPreferenceService()
        await service.on_favorite_added(user_id, "career", session)
        pref = await service.get_snapshot(user_id, session)
    """

    async def on_favorite_added(
        self, user_id: str, topic: str, session: AsyncSession
    ) -> None:
        """
        收藏(点赞)时调用:like_count +1 + 异步刷新 snapshot。

        Args:
            user_id: 用户 ID
            topic: 12 个话题之一
            session: 异步 DB 会话(调用方负责 commit)
        """
        if not topic or topic == "general":
            # general 是兜底,不算"有意义的点赞"
            return
        now = datetime.utcnow()
        stmt = sqlite_insert(UserTopicPreference).values(
            user_id=user_id,
            topic=topic,
            like_count=1,
            last_liked_at=now,
            first_liked_at=now,
        ).on_conflict_do_update(
            index_elements=["user_id", "topic"],
            set_={
                "like_count": UserTopicPreference.like_count + 1,
                "last_liked_at": now,
            },
        )
        await session.execute(stmt)
        logger.info(f"topic 点赞 +1 | user={user_id} | topic={topic}")
        # 立即刷新 snapshot(同事务内)
        await self.refresh_snapshot(user_id, session)

    async def on_favorite_removed(
        self, user_id: str, topic: str, session: AsyncSession
    ) -> None:
        """
        取消收藏(撤销认同)时调用:like_count -1,下限 0。

        Args:
            user_id: 用户 ID
            topic: 12 个话题之一
            session: 异步 DB 会话
        """
        if not topic or topic == "general":
            return
        row = (
            await session.execute(
                select(UserTopicPreference).where(
                    UserTopicPreference.user_id == user_id,
                    UserTopicPreference.topic == topic,
                )
            )
        ).scalar_one_or_none()
        if row and row.like_count > 0:
            row.like_count -= 1
            logger.info(f"topic 点赞 -1 | user={user_id} | topic={topic} | new_count={row.like_count}")
        await self.refresh_snapshot(user_id, session)

    async def compute_preference(
        self,
        user_id: str,
        session: AsyncSession,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """
        计算用户当前 topic 偏好(衰减权重 + 平局规则 + 强度标签)。

        Returns:
            None — 数据不足或无明显偏好
            {
                "topics": [{topic, weight, count, last_days_ago, intensity}, ...],
                "total_likes": int,
                "generated_at": iso str,
            }
        """
        now = now or datetime.utcnow()
        rows = (
            await session.execute(
                select(UserTopicPreference).where(
                    UserTopicPreference.user_id == user_id
                )
            )
        ).scalars().all()

        if not rows:
            return None

        total_likes = sum(r.like_count for r in rows)
        if total_likes < INJECTION_THRESHOLD_TOTAL:
            return None

        # 1) 衰减权重:weight = count * 0.5^(days_ago / 14)
        scored: list[dict[str, Any]] = []
        for r in rows:
            days_ago = max((now - r.last_liked_at).days, 0)
            weight = r.like_count * (0.5 ** (days_ago / HALF_LIFE_DAYS))
            scored.append({
                "topic": r.topic,
                "weight": round(weight, 2),
                "count": r.like_count,
                "last_days_ago": days_ago,
            })
        scored.sort(key=lambda x: -x["weight"])

        # 2) 平局规则
        if len(scored) == 1:
            lead_topics = scored
        elif scored[0]["weight"] >= CLEAR_LEAD_RATIO * scored[1]["weight"]:
            lead_topics = [scored[0]]
        else:
            lead_topics = scored[:MAX_INJECTED_TOPICS]

        # 3) 强度标签
        for t in lead_topics:
            if t["weight"] >= STRONG_THRESHOLD:
                t["intensity"] = "strong"
            elif t["weight"] >= MEDIUM_THRESHOLD:
                t["intensity"] = "medium"
            else:
                t["intensity"] = "weak"

        return {
            "topics": lead_topics,
            "total_likes": total_likes,
            "generated_at": now.isoformat(),
        }

    async def refresh_snapshot(
        self, user_id: str, session: AsyncSession
    ) -> dict[str, Any] | None:
        """
        重新计算偏好并写入 UserProfile.topic_preference_snapshot。
        返回写入的偏好 dict,无偏好时返回 None 并清空 snapshot。
        """
        pref = await self.compute_preference(user_id, session)
        snapshot = json.dumps(pref, ensure_ascii=False) if pref else None
        await session.execute(
            update(UserProfile)
            .where(UserProfile.user_id == user_id)
            .values(topic_preference_snapshot=snapshot)
        )
        return pref

    async def get_snapshot(
        self, user_id: str, session: AsyncSession
    ) -> dict[str, Any] | None:
        """
        读 snapshot(供 chat / greeting prompt 注入用)。

        无 snapshot → 返回 None。
        snapshot 格式异常 → 返回 None 并 log warning。
        """
        row = (
            await session.execute(
                select(UserProfile.topic_preference_snapshot).where(
                    UserProfile.user_id == user_id
                )
            )
        ).first()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"snapshot 格式异常,忽略 | user={user_id}")
            return None
