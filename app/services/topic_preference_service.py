"""
Topic 偏好聚合服务

负责:
- 收藏动作 = 对该回复 topic 的点赞,递增 like_count
- 取消收藏 = 撤销一次认同,递减 like_count
- 用户主动声明 = 写入 UserProfile.declared_topics,在 compute 时叠加固定 boost
- 按 user × topic 维度聚合,生成衰减权重后的偏好快照
- 冷启动门控:total_likes < 3 且无 declared_topics 时不返回偏好

设计依据: docs/greeting-topic-personalization-design-v2.md 第九章 + 第十一章
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
from .chat_service import ALLOWED_TOPICS

logger = get_logger(__name__)


# 算法参数
HALF_LIFE_DAYS: int = 14
INJECTION_THRESHOLD_TOTAL: int = 3
CLEAR_LEAD_RATIO: float = 1.5
MAX_INJECTED_TOPICS: int = 3
STRONG_THRESHOLD: float = 5.0
MEDIUM_THRESHOLD: float = 2.0
# 用户主动声明的 topic 在合并时的固定 boost(叠加在被动权重之上)
DECLARED_TOPIC_BOOST: float = 2.0


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
        计算用户当前 topic 偏好(被动衰减权重 + 主动声明 boost + 平局规则 + 强度标签)。

        Returns:
            None — 既无 declared_topics 也无足够的被动点赞
            {
                "topics": [{topic, weight, count, last_days_ago, intensity, declared}, ...],
                "total_likes": int,  # 仅被动收藏计数
                "declared_topics": list[str],  # 用户主动声明的 topic
                "generated_at": iso str,
            }
        """
        now = now or datetime.utcnow()

        # 1) 读 declared_topics(主动声明)
        profile_row = (
            await session.execute(
                select(UserProfile.declared_topics).where(
                    UserProfile.user_id == user_id
                )
            )
        ).first()
        declared_topics: list[str] = []
        if profile_row and profile_row[0]:
            try:
                declared_topics = json.loads(profile_row[0])
                if not isinstance(declared_topics, list):
                    declared_topics = []
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"declared_topics JSON 解析失败 | user={user_id}")
                declared_topics = []
        declared_set = set(declared_topics)

        # 2) 读 UserTopicPreference(被动)
        rows = (
            await session.execute(
                select(UserTopicPreference).where(
                    UserTopicPreference.user_id == user_id
                )
            )
        ).scalars().all()

        total_likes = sum(r.like_count for r in rows)

        # 3) 冷启动门控:declared_topics 非空 OR total_likes >= 3
        if not declared_topics and total_likes < INJECTION_THRESHOLD_TOTAL:
            return None

        # 4) 被动权重
        passive_by_topic: dict[str, dict[str, Any]] = {}
        for r in rows:
            days_ago = max((now - r.last_liked_at).days, 0)
            weight = r.like_count * (0.5 ** (days_ago / HALF_LIFE_DAYS))
            passive_by_topic[r.topic] = {
                "topic": r.topic,
                "weight": round(weight, 2),
                "count": r.like_count,
                "last_days_ago": days_ago,
                "declared": r.topic in declared_set,
            }

        # 5) 合并:被声明的 topic 叠加 boost,未收藏的声明 topic 直接以 boost 入榜
        scored: list[dict[str, Any]] = []
        for info in passive_by_topic.values():
            if info["declared"]:
                info["weight"] = round(info["weight"] + DECLARED_TOPIC_BOOST, 2)
            scored.append(info)
        for t in declared_topics:
            if t not in passive_by_topic:
                scored.append({
                    "topic": t,
                    "weight": DECLARED_TOPIC_BOOST,
                    "count": 0,
                    "last_days_ago": -1,  # 表示从未收藏
                    "declared": True,
                })
        scored.sort(key=lambda x: -x["weight"])

        # 6) 平局规则
        if not scored:
            return None
        if len(scored) == 1:
            lead_topics = scored
        elif scored[0]["weight"] >= CLEAR_LEAD_RATIO * scored[1]["weight"]:
            lead_topics = [scored[0]]
        else:
            lead_topics = scored[:MAX_INJECTED_TOPICS]

        # 7) 强度标签
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
            "declared_topics": declared_topics,
            "generated_at": now.isoformat(),
        }

    async def set_declared_topics(
        self,
        user_id: str,
        topics: list[str],
        session: AsyncSession,
    ) -> list[str]:
        """
        覆盖式设置用户主动声明的 topic 列表。

        流程:
        1) 过滤 + 去重(只保留 ALLOWED_TOPICS 之一,排除 general)
        2) 写入 UserProfile.declared_topics(无 profile 则创建)
        3) 刷新 snapshot(合并后的新权重)

        Args:
            user_id: 用户 ID
            topics: 用户提交的 topic 列表(可能含非法值)
            session: 异步 DB 会话(调用方负责 commit)

        Returns:
            list[str]: 过滤后实际生效的 topic 列表
        """
        # 1) 过滤 + 去重(保留插入顺序)
        valid_topics = list(dict.fromkeys(
            t for t in topics if t in ALLOWED_TOPICS and t != "general"
        ))
        json_value = json.dumps(valid_topics, ensure_ascii=False) if valid_topics else None

        # 2) upsert UserProfile
        profile = (
            await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile:
            profile.declared_topics = json_value
        else:
            profile = UserProfile(user_id=user_id, declared_topics=json_value)
            session.add(profile)
        await session.flush()
        logger.info(
            f"主动声明 topic 已更新 | user={user_id} | topics={valid_topics}"
        )

        # 3) 刷新 snapshot(同事务内)
        await self.refresh_snapshot(user_id, session)
        return valid_topics

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
