"""E2E:主动声明 topic 走完整链路
- set_declared_topics → UserProfile.declared_topics
- compute_preference 合并 + 写 snapshot
- MemoryService.get_memory_summary 读取
- MemoryContext.to_prompt_string 注入第 5 区块
- 验证 declared-only(0 收藏)和混合两种场景
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, ".")

TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"

from sqlalchemy import select  # noqa: E402

from app.models.database import get_db, init_db  # noqa: E402
from app.models.models import (  # noqa: E402
    UserProfile,
    UserTopicPreference,
)
from app.services.memory.context_builder import MemoryContext  # noqa: E402
from app.services.memory_service import MemoryService  # noqa: E402
from app.services.topic_preference_service import TopicPreferenceService  # noqa: E402


async def case_declared_only():
    """纯主动声明(0 收藏)→ 第 5 区块应输出"""
    print("\n--- Case 1: 纯主动声明(0 收藏) ---")
    await init_db()
    USER = "u_decl_only"
    async with get_db() as session:
        await TopicPreferenceService().set_declared_topics(
            USER, ["career", "healing"], session
        )
    async with get_db() as session:
        summary = await MemoryService(session).get_memory_summary(USER)
        ctx = MemoryContext.from_memory_summary(summary)
        prompt = ctx.to_prompt_string()
        print(prompt)
        assert "【话题偏好】" in prompt
        assert "career" in prompt
        assert "healing" in prompt
        assert "主动声明" in prompt, "应提示'主动声明'而不是'基于 0 次收藏'"
        assert "career(medium, 主动声明)" in prompt
    print("  PASS: declared-only 注入正确")


async def case_declared_plus_favorite():
    """主动声明 + 收藏 → 合并权重"""
    print("\n--- Case 2: 主动声明 + 收藏(混合) ---")
    USER = "u_mixed"
    async with get_db() as session:
        await TopicPreferenceService().set_declared_topics(
            USER, ["career", "love"], session
        )
        # career 3 次 (weight=3) + boost 2.0 = 5.0 (strong)
        for _ in range(3):
            await TopicPreferenceService().on_favorite_added(USER, "career", session)
        # love 2 次 (weight=2) + boost 2.0 = 4.0 (medium)
        # 5.0/4.0=1.25 < 1.5 → 平局,两个都在 snapshot
        for _ in range(2):
            await TopicPreferenceService().on_favorite_added(USER, "love", session)
    async with get_db() as session:
        summary = await MemoryService(session).get_memory_summary(USER)
        ctx = MemoryContext.from_memory_summary(summary)
        prompt = ctx.to_prompt_string()
        print(prompt)
        assert "基于 5 次收藏" in prompt, f"应显示'基于 5 次收藏',prompt={prompt}"
        # career weight = 3+2=5.0 → strong
        assert "career(strong, weight=5.0)" in prompt, "career 应为 strong"
        # love weight = 2+2=4.0 → medium(count=2,不是纯 declared,显示 weight)
        assert "love(medium, weight=4.0)" in prompt, "love 应为 medium weight=4.0"
    print("  PASS: mixed 注入正确")


async def case_undeclare_keeps_history():
    """取消声明后,UserTopicPreference 历史保留"""
    print("\n--- Case 3: 取消声明保留历史 ---")
    USER = "u_undeclare"
    async with get_db() as session:
        for _ in range(3):
            await TopicPreferenceService().on_favorite_added(USER, "career", session)
        await TopicPreferenceService().set_declared_topics(USER, ["career"], session)
        # 验证:行还在,declaration 也写了
        await TopicPreferenceService().set_declared_topics(USER, [], session)
    async with get_db() as session:
        row = (await session.execute(
            select(UserTopicPreference).where(
                UserTopicPreference.user_id == USER,
                UserTopicPreference.topic == "career",
            )
        )).scalar_one()
        assert row.like_count == 3, "历史 like_count 应保留为 3"
        # 再次算
        summary = await MemoryService(session).get_memory_summary(USER)
        ctx = MemoryContext.from_memory_summary(summary)
        prompt = ctx.to_prompt_string()
        assert "career(medium, weight=3.0)" in prompt, \
            f"取消声明后 weight 应为 3.0(无 boost),prompt={prompt}"
    print("  PASS: undeclare 保留历史")


async def case_invalid_filtered():
    """非法 topic 在 set 时被过滤"""
    print("\n--- Case 4: 非法 topic 过滤 ---")
    USER = "u_filter"
    async with get_db() as session:
        result = await TopicPreferenceService().set_declared_topics(
            USER, ["career", "fake_topic_xyz", "love", "general"], session
        )
        assert result == ["career", "love"], f"应过滤为 [career, love],实际 {result}"
    print("  PASS: 非法 topic 过滤正确")


async def main():
    failed = 0
    cases = [
        case_declared_only,
        case_declared_plus_favorite,
        case_undeclare_keeps_history,
        case_invalid_filtered,
    ]
    for c in cases:
        try:
            await c()
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
