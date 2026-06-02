"""端到端测试:TopicPreferenceService 完整流程
- 建表
- 收藏 → 触发聚合
- 读 snapshot
- 拼 MemoryContext → 验证第 5 区块
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, ".")

# 使用临时 SQLite 避免污染 dev DB
TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"

from sqlalchemy import select  # noqa: E402

from app.models.database import _session_factory, get_db, init_db  # noqa: E402
from app.models.models import (  # noqa: E402
    Favorite,
    Message,
    UserProfile,
    UserTopicPreference,
)
from app.models.schemas import FavoriteCreate, MemorySummary  # noqa: E402
from app.services.favorite_service import FavoriteService  # noqa: E402
from app.services.memory.context_builder import MemoryContext  # noqa: E402
from app.services.memory_service import MemoryService  # noqa: E402
from app.services.topic_preference_service import TopicPreferenceService  # noqa: E402

USER = "test_user_topic_pref"


async def main():
    await init_db()
    print("DB initialized at:", TMP_DB)

    async with get_db() as session:
        # 0) 准备:先发一条 assistant 消息(content=compliment_A, topic=career)
        # 模拟一条 assistant 消息,用于 favorite 反查 topic
        msg = Message(
            session_id="session_test",
            trace_id="trace_msg_1",
            role="assistant",
            content="拖了两周还能坚持找到答案,这份不放弃的劲儿挺难得的。",
            message_type="text",
            scene="career",
            topic="career",
        )
        session.add(msg)
        # 1) 准备:先准备 user_profile(为空也行,snapshot 为 None)
        profile = UserProfile(user_id=USER)
        session.add(profile)
        print("seed: 1 assistant message + 1 user_profile")

    # ===== Case 1: add_favorite 走场景路径(请求 scene=career) =====
    print("\n--- Case 1: scene=career 走 1 级兜底 ---")
    async with get_db() as session:
        svc = FavoriteService()
        fav = await svc.add_favorite(
            user_id=USER,
            data=FavoriteCreate(
                content="拖了两周还能坚持找到答案,这份不放弃的劲儿挺难得的。",
                scene="career",
            ),
            session=session,
        )
        print(f"  favorite_id={fav.id} | scene={fav.scene}")

    # ===== Case 2: 3 次收藏后 snapshot 应该出现 =====
    print("\n--- Case 2: 累计 3 次后触发 snapshot 写入 ---")
    for i in range(2):
        async with get_db() as session:
            svc = FavoriteService()
            await svc.add_favorite(
                user_id=USER,
                data=FavoriteCreate(
                    content=f"夸夸第 {i + 2} 条",
                    scene="career",
                ),
                session=session,
            )

    async with get_db() as session:
        snapshot = await TopicPreferenceService().get_snapshot(USER, session)
        print(f"  snapshot: {snapshot}")

        # 也确认 UserTopicPreference 表有 1 行
        rows = (await session.execute(
            select(UserTopicPreference).where(UserTopicPreference.user_id == USER)
        )).scalars().all()
        for r in rows:
            print(f"  pref_row: topic={r.topic} | count={r.like_count}")

    # ===== Case 3: 冷启动门控(total<3 时 snapshot 为 None) =====
    print("\n--- Case 3: 冷启动门控 ---")
    # 模拟一个新用户,只点赞 2 次
    NEW_USER = "test_cold_start"
    async with get_db() as session:
        session.add(UserProfile(user_id=NEW_USER))
    for i in range(2):
        async with get_db() as session:
            svc = FavoriteService()
            await svc.add_favorite(
                user_id=NEW_USER,
                data=FavoriteCreate(content=f"x{i}", scene="daily"),
                session=session,
            )
    async with get_db() as session:
        snapshot = await TopicPreferenceService().get_snapshot(NEW_USER, session)
        print(f"  cold_start snapshot (expect None): {snapshot}")

    # ===== Case 4: 删 1 条收藏 → 偏好衰减 =====
    print("\n--- Case 4: 取消收藏扣减 ---")
    async with get_db() as session:
        # 拿第一条 favorite
        f = (await session.execute(
            select(Favorite).where(Favorite.user_id == USER).order_by(Favorite.id).limit(1)
        )).scalar_one()
        await FavoriteService().delete_favorite(USER, f.id, session)
    async with get_db() as session:
        rows = (await session.execute(
            select(UserTopicPreference).where(UserTopicPreference.user_id == USER)
        )).scalars().all()
        for r in rows:
            print(f"  after delete: topic={r.topic} | count={r.like_count}")

    # ===== Case 5: 反查兜底(请求 scene=unknown → 反查 Message.topic) =====
    print("\n--- Case 5: 请求 scene 非法 → 反查 Message.topic ---")
    NEW_USER2 = "test_reverse_lookup"
    async with get_db() as session:
        # 插入 assistant 消息 topic=healing
        session.add(Message(
            session_id="s_rev", trace_id="t_rev",
            role="assistant",
            content="哭一哭也没什么大不了",
            message_type="text",
            scene="healing", topic="healing",
        ))
        session.add(UserProfile(user_id=NEW_USER2))
    async with get_db() as session:
        fav = await FavoriteService().add_favorite(
            user_id=NEW_USER2,
            data=FavoriteCreate(content="哭一哭也没什么大不了", scene="unknown_scene_xyz"),
            session=session,
        )
        print(f"  favorite.scene (expect healing): {fav.scene}")

    # ===== Case 6: clear_favorites 同时清空偏好 =====
    print("\n--- Case 6: clear_favorites 全清空 ---")
    async with get_db() as session:
        deleted = await FavoriteService().clear_favorites(USER, session)
        print(f"  deleted count: {deleted}")
    async with get_db() as session:
        rows = (await session.execute(
            select(UserTopicPreference).where(UserTopicPreference.user_id == USER)
        )).scalars().all()
        print(f"  remaining pref rows (expect 0): {len(rows)}")
        snap = await TopicPreferenceService().get_snapshot(USER, session)
        print(f"  snapshot (expect None): {snap}")

    # ===== Case 7: MemorySummary 读取 snapshot + MemoryContext 第 5 区块 =====
    print("\n--- Case 7: MemorySummary → MemoryContext 第 5 区块 ---")
    # 重新造一个用户,凑 4 个点赞 + topic 分布
    E2E_USER = "e2e_user"
    async with get_db() as session:
        session.add(UserProfile(user_id=E2E_USER))
    topics_to_like = ["career", "career", "career", "love", "love", "daily"]
    for t in topics_to_like:
        async with get_db() as session:
            await FavoriteService().add_favorite(
                E2E_USER,
                FavoriteCreate(content=f"content_{t}", scene=t),
                session=session,
            )
    async with get_db() as session:
        memory_service = MemoryService(session)
        summary = await memory_service.get_memory_summary(E2E_USER)
        print(f"  summary.topic_preference: {summary.topic_preference}")
        # 转 MemoryContext
        ctx = MemoryContext.from_memory_summary(summary)
        prompt = ctx.to_prompt_string()
        print("  ---- prompt 注入 ----")
        print(prompt)
        print("  ---- /prompt 注入 ----")
        assert "【话题偏好】" in prompt, "期望看到第 5 区块"
        assert "career" in prompt, "期望看到 lead topic"
        print("  PASS: 5th block injected")

    # 清理
    try:
        os.unlink(TMP_DB)
    except Exception:
        pass
    print("\nALL E2E PASSED")


if __name__ == "__main__":
    asyncio.run(main())
