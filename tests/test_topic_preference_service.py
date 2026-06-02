"""
TopicPreferenceService 单元测试

测试目标:
1. 衰减权重公式:weight = count * 0.5^(days_ago / 14)
2. 平局规则:1.5x lead ratio + max 3 topics
3. 强度标签:strong(>=5) / medium(>=2) / weak(<2)
4. 冷启动门控:total_likes < 3 → None
5. 异常 snapshot 容错:JSON 损坏 → None + log warning
6. on_favorite_added/removed:SQLite upsert + 扣减
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, ".")

# 临时 SQLite DB(避免污染 dev DB)
TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"

from sqlalchemy import select  # noqa: E402

from app.models.database import get_db, init_db  # noqa: E402
from app.models.models import (  # noqa: E402
    UserProfile,
    UserTopicPreference,
)
from app.services.topic_preference_service import (  # noqa: E402
    CLEAR_LEAD_RATIO,
    HALF_LIFE_DAYS,
    INJECTION_THRESHOLD_TOTAL,
    MAX_INJECTED_TOPICS,
    MEDIUM_THRESHOLD,
    STRONG_THRESHOLD,
    TopicPreferenceService,
)


async def reset_db():
    """每个 case 独立的 user_id 避免污染"""
    await init_db()


async def test_decay_weight_exact():
    """衰减权重公式:0.5^(days/14) 精确性"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_decay"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        # 1 个 career,7 天前 → weight = 1 * 0.5^0.5 ≈ 0.71
        session.add(UserTopicPreference(
            user_id=USER, topic="career", like_count=1,
            last_liked_at=datetime.utcnow() - timedelta(days=7),
            first_liked_at=datetime.utcnow() - timedelta(days=7),
        ))
        # 1 个 daily,14 天前 → weight = 1 * 0.5^1 = 0.5
        session.add(UserTopicPreference(
            user_id=USER, topic="daily", like_count=1,
            last_liked_at=datetime.utcnow() - timedelta(days=14),
            first_liked_at=datetime.utcnow() - timedelta(days=14),
        ))
        # 1 个 love,28 天前 → weight = 1 * 0.5^2 = 0.25
        session.add(UserTopicPreference(
            user_id=USER, topic="love", like_count=1,
            last_liked_at=datetime.utcnow() - timedelta(days=28),
            first_liked_at=datetime.utcnow() - timedelta(days=28),
        ))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        assert pref is not None, "3 个 total_likes 应该过冷启动门控"
        topics = {t["topic"]: t for t in pref["topics"]}
        # career (7d) 应排第一
        assert topics["career"]["weight"] == 0.71, f"career weight 应为 0.71,实际 {topics['career']['weight']}"
        assert topics["daily"]["weight"] == 0.5, f"daily weight 应为 0.5,实际 {topics['daily']['weight']}"
        assert topics["love"]["weight"] == 0.25, f"love weight 应为 0.25,实际 {topics['love']['weight']}"
        # 排序:career > daily > love
        assert pref["topics"][0]["topic"] == "career"
        assert pref["topics"][1]["topic"] == "daily"
        assert pref["topics"][2]["topic"] == "love"
    print("  PASS: test_decay_weight_exact")


async def test_cold_start_gate():
    """冷启动门控:total_likes < 3 → None"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_cold"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        session.add(UserTopicPreference(
            user_id=USER, topic="career", like_count=2,  # total=2
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        assert pref is None, f"total=2 应该返回 None,实际 {pref}"
    print(f"  PASS: test_cold_start_gate (INJECTION_THRESHOLD_TOTAL={INJECTION_THRESHOLD_TOTAL})")


async def test_clear_lead_ratio():
    """平局规则:lead_weight >= 1.5x second_weight → 单 lead"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_lead"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        # career: 5 个 0d → weight=5
        # love: 3 个 0d → weight=3
        # 5/3 = 1.67 > 1.5 → 单 lead career
        session.add(UserTopicPreference(
            user_id=USER, topic="career", like_count=5,
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
        session.add(UserTopicPreference(
            user_id=USER, topic="love", like_count=3,
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        assert len(pref["topics"]) == 1
        assert pref["topics"][0]["topic"] == "career"
    print(f"  PASS: test_clear_lead_ratio (CLEAR_LEAD_RATIO={CLEAR_LEAD_RATIO})")


async def test_tie_returns_top_n():
    """平局场景:lead 不够 1.5x → 返回 top 3"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_tie"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        # career=4, love=3, daily=3, beauty=2 → 4/3 = 1.33 < 1.5 → 平局
        for t, c in [("career", 4), ("love", 3), ("daily", 3), ("beauty", 2)]:
            session.add(UserTopicPreference(
                user_id=USER, topic=t, like_count=c,
                last_liked_at=datetime.utcnow(),
                first_liked_at=datetime.utcnow(),
            ))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        # 平局时返回 top MAX_INJECTED_TOPICS=3
        assert len(pref["topics"]) == MAX_INJECTED_TOPICS, \
            f"应返回 {MAX_INJECTED_TOPICS},实际 {len(pref['topics'])}"
        topics = [t["topic"] for t in pref["topics"]]
        assert "career" in topics and "love" in topics and "daily" in topics
        assert "beauty" not in topics, "beauty count=2 排在第 4,应被截断"
    print(f"  PASS: test_tie_returns_top_n (MAX_INJECTED_TOPICS={MAX_INJECTED_TOPICS})")


async def test_intensity_thresholds():
    """强度标签:strong(>=5) / medium(>=2) / weak(<2)

    为触发平局路径(让 3 个 topic 都进 lead_topics),
    把 lead ratio 控制在 < 1.5,例如 career=4, love=3, daily=2 (4/3=1.33<1.5)
    """
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_intensity"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        # strong: career weight=4(>=5 不达,改为用 clear_lead 单 lead 验证 5)
        # 这里通过平局触发,让 3 个都进 lead_topics
        session.add(UserTopicPreference(
            user_id=USER, topic="career", like_count=4,  # weight=4 → strong(>=5) 不达
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
        session.add(UserTopicPreference(
            user_id=USER, topic="love", like_count=3,  # weight=3 → medium
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
        session.add(UserTopicPreference(
            user_id=USER, topic="daily", like_count=2,  # weight=2 → medium(boundary)
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
        # 加一个 weak(<2):用 28 天前 weight=0.5
        session.add(UserTopicPreference(
            user_id=USER, topic="beauty", like_count=1,
            last_liked_at=datetime.utcnow() - timedelta(days=28),
            first_liked_at=datetime.utcnow() - timedelta(days=28),
        ))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        # 平局时 MAX_INJECTED_TOPICS=3,beauty 排第 4 被截断
        topics = {t["topic"]: t for t in pref["topics"]}
        # career/love/daily 应在,beauty 应不在
        assert "career" in topics, f"career 应在 lead,实际 topics={list(topics)}"
        assert "love" in topics
        assert "daily" in topics
        # intensity 边界:career=4 → medium(因为 STRONG>=5 不满足)
        # 改成单独验证 strong:在另一个 user 上加 weight=5
        # 删掉 beauty(进不去 snapshot,因为 MAX_INJECTED_TOPICS=3)
        # 改成单独 case 验证 strong
        assert topics["career"]["intensity"] == "medium", \
            f"career weight=4 应为 medium(5 是 strong 阈值),实际 {topics['career']['intensity']}"
        assert topics["love"]["intensity"] == "medium"
        assert topics["daily"]["intensity"] == "medium"

    # 单独 case:验证 strong(weight=5)
    USER2 = "u_strong"
    async with get_db() as session:
        session.add(UserProfile(user_id=USER2))
        # 5 个 career → weight=5 → strong
        session.add(UserTopicPreference(
            user_id=USER2, topic="career", like_count=5,
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
    async with get_db() as session:
        pref = await svc.compute_preference(USER2, session)
        assert pref["topics"][0]["intensity"] == "strong"

    # 单独 case:验证 weak(weight<2)— 3 个 topic weight 都在 < 2
    USER3 = "u_weak"
    async with get_db() as session:
        session.add(UserProfile(user_id=USER3))
        # career: 1 个 14d 前 → weight=0.5 → weak
        # daily:  1 个 0d → weight=1 → weak
        # love:   1 个 0d → weight=1 → weak
        # 平局(1/0.5=2>1.5,还是 clear lead),但 3 个都 weak
        # 改用 7d 前 1 个 + 0d 1 个:0.71/1=0.71<1.5 → 平局
        session.add(UserTopicPreference(
            user_id=USER3, topic="career", like_count=1,
            last_liked_at=datetime.utcnow() - timedelta(days=14),  # weight=0.5
            first_liked_at=datetime.utcnow() - timedelta(days=14),
        ))
        session.add(UserTopicPreference(
            user_id=USER3, topic="daily", like_count=1,
            last_liked_at=datetime.utcnow(),  # weight=1
            first_liked_at=datetime.utcnow(),
        ))
        session.add(UserTopicPreference(
            user_id=USER3, topic="love", like_count=1,
            last_liked_at=datetime.utcnow(),  # weight=1
            first_liked_at=datetime.utcnow(),
        ))
    async with get_db() as session:
        pref = await svc.compute_preference(USER3, session)
        topics = {t["topic"]: t for t in pref["topics"]}
        assert "career" in topics, f"career 应在 lead,实际 topics={list(topics)}"
        assert topics["career"]["intensity"] == "weak"
        assert topics["daily"]["intensity"] == "weak"
        assert topics["love"]["intensity"] == "weak"
    print(f"  PASS: test_intensity_thresholds (STRONG={STRONG_THRESHOLD}, MEDIUM={MEDIUM_THRESHOLD})")


async def test_on_favorite_added_upsert():
    """on_favorite_added:首次 +1,重复 +1,trigger snapshot"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_upsert"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))

    # 第 1 次:insert
    async with get_db() as session:
        await svc.on_favorite_added(USER, "career", session)
    # 第 2 次:upsert +1
    async with get_db() as session:
        await svc.on_favorite_added(USER, "career", session)
    # 第 3 次:upsert +1
    async with get_db() as session:
        await svc.on_favorite_added(USER, "career", session)

    async with get_db() as session:
        row = (await session.execute(
            select(UserTopicPreference).where(
                UserTopicPreference.user_id == USER,
                UserTopicPreference.topic == "career",
            )
        )).scalar_one()
        assert row.like_count == 3, f"应有 3 次点赞,实际 {row.like_count}"
        # snapshot 已经被 refresh 到 UserProfile
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == USER)
        )).scalar_one()
        assert profile.topic_preference_snapshot is not None
        snap = json.loads(profile.topic_preference_snapshot)
        assert snap["total_likes"] == 3
    print("  PASS: test_on_favorite_added_upsert")


async def test_on_favorite_removed_decrement():
    """on_favorite_removed:扣减,下限 0"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_remove"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
    # 加 3 次
    for _ in range(3):
        async with get_db() as session:
            await svc.on_favorite_added(USER, "love", session)
    # 减 1 次
    async with get_db() as session:
        await svc.on_favorite_removed(USER, "love", session)
    # 再减 5 次(确保下限 0)
    for _ in range(5):
        async with get_db() as session:
            await svc.on_favorite_removed(USER, "love", session)

    async with get_db() as session:
        row = (await session.execute(
            select(UserTopicPreference).where(
                UserTopicPreference.user_id == USER,
                UserTopicPreference.topic == "love",
            )
        )).scalar_one()
        assert row.like_count == 0, f"扣减后应为 0,实际 {row.like_count}"
    print("  PASS: test_on_favorite_removed_decrement (floor=0)")


async def test_general_topic_ignored():
    """general topic 不参与聚合(冷启动兜底不应被计为偏好)"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_general"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
    for _ in range(5):
        async with get_db() as session:
            await svc.on_favorite_added(USER, "general", session)

    async with get_db() as session:
        rows = (await session.execute(
            select(UserTopicPreference).where(UserTopicPreference.user_id == USER)
        )).scalars().all()
        # 5 个 general 不应写入 UserTopicPreference
        assert len(rows) == 0, f"general 不应被记录,实际有 {len(rows)} 行"
    print("  PASS: test_general_topic_ignored")


async def test_snapshot_corrupt_returns_none():
    """snapshot JSON 损坏 → get_snapshot 返回 None + log warning"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_corrupt"

    async with get_db() as session:
        profile = UserProfile(user_id=USER, topic_preference_snapshot="not valid json {{")
        session.add(profile)

    async with get_db() as session:
        result = await svc.get_snapshot(USER, session)
        assert result is None, f"损坏 snapshot 应返回 None,实际 {result}"
    print("  PASS: test_snapshot_corrupt_returns_none")


async def test_snapshot_empty_returns_none():
    """snapshot 为空 → 返回 None"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_empty"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER, topic_preference_snapshot=None))

    async with get_db() as session:
        result = await svc.get_snapshot(USER, session)
        assert result is None
    print("  PASS: test_snapshot_empty_returns_none")


async def test_refresh_snapshot_writes_to_profile():
    """refresh_snapshot 把 compute 结果写入 UserProfile.topic_preference_snapshot"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_refresh"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
    # 攒 3 个 career
    for _ in range(3):
        async with get_db() as session:
            await svc.on_favorite_added(USER, "career", session)

    async with get_db() as session:
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == USER)
        )).scalar_one()
        snap = json.loads(profile.topic_preference_snapshot)
        assert snap["total_likes"] == 3
        assert snap["topics"][0]["topic"] == "career"
        assert snap["topics"][0]["intensity"] == "medium"
    print("  PASS: test_refresh_snapshot_writes_to_profile")


async def test_no_data_returns_none():
    """无 UserTopicPreference 行 → None"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_nodata"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        assert pref is None
    print("  PASS: test_no_data_returns_none")


# ==================== 主动声明 topic 合并 ====================


async def test_declared_only_passes_cold_start():
    """纯主动声明(0 收藏)能通过冷启动门控"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_decl_only"

    async with get_db() as session:
        await svc.set_declared_topics(USER, ["career", "love"], session)

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        assert pref is not None, "纯主动声明应通过冷启动门控"
        topics = {t["topic"]: t for t in pref["topics"]}
        assert "career" in topics and "love" in topics
        # 都是纯声明 → weight = DECLARED_TOPIC_BOOST
        assert topics["career"]["weight"] == 2.0
        assert topics["love"]["count"] == 0
        assert topics["love"]["last_days_ago"] == -1
        assert topics["love"]["declared"] is True
        # 平局 2.0/2.0 = 1.0 < 1.5 → 取 top 3
        assert len(pref["topics"]) == 2
        assert pref["total_likes"] == 0
    print("  PASS: test_declared_only_passes_cold_start")


async def test_declared_boost_overlays_passive_weight():
    """主动声明的 topic 叠加在被动权重之上"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_boost"

    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
        # 被动:career 1 次(0d)→ weight = 1.0
        session.add(UserTopicPreference(
            user_id=USER, topic="career", like_count=1,
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))
        # 被动:love 1 次(0d)→ weight = 1.0
        # 用 love 也收藏 1 次,让 lead ratio 落在 [1.0, 1.5) 之间,
        # 否则 1+2=3.0 vs 2.0 正好 1.5x 触发 clear lead,love 被裁掉
        session.add(UserTopicPreference(
            user_id=USER, topic="love", like_count=1,
            last_liked_at=datetime.utcnow(),
            first_liked_at=datetime.utcnow(),
        ))

    async with get_db() as session:
        # 主动声明 career + love
        await svc.set_declared_topics(USER, ["career", "love"], session)

    async with get_db() as session:
        pref = await svc.compute_preference(USER, session)
        topics = {t["topic"]: t for t in pref["topics"]}
        # career: 被动 1.0 + boost 2.0 = 3.0
        assert topics["career"]["weight"] == 3.0, \
            f"career 应为 1.0+2.0=3.0,实际 {topics['career']['weight']}"
        # love: 被动 1.0 + boost 2.0 = 3.0
        assert topics["love"]["weight"] == 3.0, \
            f"love 应为 1.0+2.0=3.0,实际 {topics['love']['weight']}"
        # 平局 3.0/3.0=1.0 < 1.5 → 两个都在
        assert "career" in topics and "love" in topics
        # declared 标记
        assert topics["career"]["declared"] is True
        assert topics["love"]["declared"] is True
    print("  PASS: test_declared_boost_overlays_passive_weight")


async def test_undeclare_keeps_favorite_history():
    """取消声明某个 topic,不删 UserTopicPreference 历史"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_undeclare"

    # 1) 3 次 career 收藏
    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
    for _ in range(3):
        async with get_db() as session:
            await svc.on_favorite_added(USER, "career", session)

    # 2) 主动声明 career
    async with get_db() as session:
        await svc.set_declared_topics(USER, ["career"], session)

    # 3) 取消声明(空列表)
    async with get_db() as session:
        await svc.set_declared_topics(USER, [], session)

    # 4) 验证:UserTopicPreference 行还在(like_count=3),但 weight 不再加 boost
    async with get_db() as session:
        row = (await session.execute(
            select(UserTopicPreference).where(
                UserTopicPreference.user_id == USER,
                UserTopicPreference.topic == "career",
            )
        )).scalar_one()
        assert row.like_count == 3, "被动历史应保留"

        pref = await svc.compute_preference(USER, session)
        topics = {t["topic"]: t for t in pref["topics"]}
        # weight = 1+1+1 = 3.0(无 boost)
        assert topics["career"]["weight"] == 3.0
        assert topics["career"]["declared"] is False
    print("  PASS: test_undeclare_keeps_favorite_history")


async def test_invalid_topics_filtered():
    """非法 topic 被静默过滤,合法值保留"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_filter"

    async with get_db() as session:
        result = await svc.set_declared_topics(
            USER, ["career", "invalid_topic_xyz", "love", "general"], session
        )
    # general 和非法值都被过滤,只留 career + love
    assert result == ["career", "love"], \
        f"应过滤为 [career, love],实际 {result}"
    print("  PASS: test_invalid_topics_filtered")


async def test_set_declared_creates_profile_if_missing():
    """用户无 profile 时,set_declared_topics 应自动创建"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_new_no_profile"

    async with get_db() as session:
        result = await svc.set_declared_topics(USER, ["career"], session)
        assert result == ["career"]
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == USER)
        )).scalar_one()
        assert profile.declared_topics is not None
        import json as _json
        assert _json.loads(profile.declared_topics) == ["career"]
    print("  PASS: test_set_declared_creates_profile_if_missing")


async def test_set_declared_dedupes_preserving_order():
    """去重时保留插入顺序"""
    await reset_db()
    svc = TopicPreferenceService()
    USER = "u_dedup"

    async with get_db() as session:
        result = await svc.set_declared_topics(
            USER, ["love", "career", "love", "daily", "career"], session
        )
    assert result == ["love", "career", "daily"], \
        f"应去重并保序为 [love, career, daily],实际 {result}"
    print("  PASS: test_set_declared_dedupes_preserving_order")


async def main():
    tests = [
        test_decay_weight_exact,
        test_cold_start_gate,
        test_clear_lead_ratio,
        test_tie_returns_top_n,
        test_intensity_thresholds,
        test_on_favorite_added_upsert,
        test_on_favorite_removed_decrement,
        test_general_topic_ignored,
        test_snapshot_corrupt_returns_none,
        test_snapshot_empty_returns_none,
        test_refresh_snapshot_writes_to_profile,
        test_no_data_returns_none,
        # 主动声明相关
        test_declared_only_passes_cold_start,
        test_declared_boost_overlays_passive_weight,
        test_undeclare_keeps_favorite_history,
        test_invalid_topics_filtered,
        test_set_declared_creates_profile_if_missing,
        test_set_declared_dedupes_preserving_order,
    ]
    failed = 0
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            await t()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n=== {'ALL PASS' if failed == 0 else f'{failed} FAILED'} ===")
    try:
        os.unlink(TMP_DB)
    except Exception:
        pass
    return failed


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
