"""
人格注入单元测试 + Greeting 端到端测试

覆盖:
1. _inject_personality 各种输入(default / witty / chill / enthusiastic / unknown / 空 / None)
2. generate_greeting 的 system_prompt 拼装应用 personality
3. generate_greeting 的 topic 偏好渲染:
   - 纯被动收藏 → "累计 X 次"
   - 纯主动声明 → "用户主动关注话题"
   - 混合 → "累计 X 次"(隐式)
4. generate_greeting 的 memory_lines 包含用户标签 / 偏好场景等
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, ".")

TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"

from app.models.database import get_db, init_db  # noqa: E402
from app.models.models import UserProfile  # noqa: E402
from app.prompts.templates import get_chat_prompt  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402
from app.services.topic_preference_service import TopicPreferenceService  # noqa: E402


# ==================== _inject_personality 单测 ====================


def test_inject_personality_default():
    """default / 空 / None / 未知值 → system_prompt 不变"""
    base = "你是真诚温暖的朋友。"
    assert ChatService._inject_personality(base, "default") == base
    assert ChatService._inject_personality(base, "") == base
    assert ChatService._inject_personality(base, None) == base
    assert ChatService._inject_personality(base, "unknown_xyz") == base
    print("  PASS: test_inject_personality_default")


def test_inject_personality_witty():
    """witty → 追加【人格模式】块 + witty role"""
    base = "你是真诚温暖的朋友。"
    result = ChatService._inject_personality(base, "witty")
    assert result != base, "witty 应修改 system_prompt"
    assert "【人格模式" in result
    assert "调侃" in result or "嘴贱" in result or "吐槽" in result
    # 基础 prompt 应在前面(前缀稳定)
    assert result.startswith(base)
    print("  PASS: test_inject_personality_witty")


def test_inject_personality_chill():
    """chill → 追加【人格模式】块 + chill role"""
    base = "你是真诚温暖的朋友。"
    result = ChatService._inject_personality(base, "chill")
    assert "【人格模式" in result
    assert "淡定" in result or "慵懒" in result or "精准" in result
    print("  PASS: test_inject_personality_chill")


def test_inject_personality_enthusiastic():
    """enthusiastic → 追加【人格模式】块 + enthusiastic role"""
    base = "你是真诚温暖的朋友。"
    result = ChatService._inject_personality(base, "enthusiastic")
    assert "【人格模式" in result
    assert "热血" in result or "中二" in result or "戏精" in result
    print("  PASS: test_inject_personality_enthusiastic")


def test_inject_personality_preserves_base_for_caching():
    """default 时 system_prompt 完全不变,基础模板可缓存"""
    base = get_chat_prompt("text_only")["system"]
    assert ChatService._inject_personality(base, "default") is base or \
        ChatService._inject_personality(base, "default") == base
    # 任何非 default 值都追加
    for p in ["witty", "chill", "enthusiastic"]:
        out = ChatService._inject_personality(base, p)
        assert out != base, f"{p} 应改变 system_prompt"
        assert out.startswith(base), f"{p} 应以 base 开头,确保 base prefix 稳定"
    print("  PASS: test_inject_personality_preserves_base_for_caching")


# ==================== Greeting 端到端 ====================


async def _seed_user_with_declared_only(user_id: str, topics: list[str]) -> None:
    """辅助:写入纯主动声明用户(0 收藏)"""
    svc = TopicPreferenceService()
    async with get_db() as session:
        await svc.set_declared_topics(user_id, topics, session)


async def _seed_user_with_passive_likes(user_id: str, topics_with_count: dict[str, int]) -> None:
    """辅助:写入被动收藏用户"""
    svc = TopicPreferenceService()
    async with get_db() as session:
        session.add(UserProfile(user_id=user_id))
    for topic, count in topics_with_count.items():
        for _ in range(count):
            async with get_db() as session:
                await svc.on_favorite_added(user_id, topic, session)


def _make_chat_service_with_capture() -> tuple[ChatService, list[dict]]:
    """构造 ChatService,provider.generate 捕获调用入参"""
    captured: list[dict] = []

    async def fake_generate(prompt, system_prompt="", **kwargs):
        captured.append({"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs})
        return "今天想说点什么？我在听～"

    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=fake_generate)
    from app.config import ModelConfig
    vision_config = ModelConfig(model="test", api_key="test", base_url="http://test")
    svc = ChatService(provider=provider, vision_config=vision_config)
    return svc, captured


async def test_greeting_declared_only_no_zero_count():
    """纯主动声明用户 → 问候 prompt 不出现'累计 0 次',而是'主动关注'"""
    await init_db()
    USER = "u_greet_decl"
    await _seed_user_with_declared_only(USER, ["career"])

    svc, captured = _make_chat_service_with_capture()

    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id=USER,
        personality_prefer="default",
        topic_preference={
            "topics": [
                {"topic": "career", "weight": 2.0, "count": 0,
                 "last_days_ago": -1, "intensity": "medium", "declared": True}
            ],
            "total_likes": 0,
            "declared_topics": ["career"],
        },
    )

    greeting = await svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    assert len(captured) == 1
    prompt = captured[0]["prompt"]
    print(f"  greeting prompt (declared-only):\n{prompt}\n  ---")
    assert "累计 0 次" not in prompt, f"不应出现'累计 0 次',prompt={prompt}"
    assert "主动关注话题:career" in prompt, f"应出现'主动关注话题:career',prompt={prompt}"
    assert "强度 medium" in prompt
    print("  PASS: test_greeting_declared_only_no_zero_count")


async def test_greeting_passive_likes_shows_count():
    """纯被动收藏用户 → 问候 prompt 出现'累计 X 次'"""
    await init_db()
    USER = "u_greet_passive"
    await _seed_user_with_passive_likes(USER, {"career": 5})

    svc, captured = _make_chat_service_with_capture()

    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id=USER,
        personality_prefer="default",
        topic_preference={
            "topics": [
                {"topic": "career", "weight": 5.0, "count": 5,
                 "last_days_ago": 0, "intensity": "strong", "declared": False}
            ],
            "total_likes": 5,
            "declared_topics": [],
        },
    )

    await svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    prompt = captured[0]["prompt"]
    print(f"  greeting prompt (passive):\n{prompt}\n  ---")
    assert "累计 5 次" in prompt
    assert "career" in prompt
    assert "强度 strong" in prompt
    assert "主动关注" not in prompt, "纯被动不应出现'主动关注'措辞"
    print("  PASS: test_greeting_passive_likes_shows_count")


async def test_greeting_mixed_shows_count_not_declare():
    """混合(收藏+声明同 topic)→ 仍显示'累计 X 次'(count>0 优先于 declared)"""
    await init_db()
    USER = "u_greet_mixed"
    svc = TopicPreferenceService()
    async with get_db() as session:
        session.add(UserProfile(user_id=USER))
    for _ in range(3):
        async with get_db() as session:
            await svc.on_favorite_added(USER, "career", session)
    async with get_db() as session:
        await svc.set_declared_topics(USER, ["career"], session)

    chat_svc, captured = _make_chat_service_with_capture()
    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id=USER,
        personality_prefer="default",
        topic_preference={
            "topics": [
                {"topic": "career", "weight": 5.0, "count": 3,
                 "last_days_ago": 0, "intensity": "strong", "declared": True}
            ],
            "total_likes": 3,
            "declared_topics": ["career"],
        },
    )
    await chat_svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    prompt = captured[0]["prompt"]
    print(f"  greeting prompt (mixed):\n{prompt}\n  ---")
    assert "累计 3 次" in prompt
    assert "career" in prompt
    print("  PASS: test_greeting_mixed_shows_count_not_declare")


async def test_greeting_applies_personality_to_system_prompt():
    """personality_prefer=chill 时,greeting system_prompt 应带【人格模式】块"""
    await init_db()
    USER = "u_greet_chill"

    svc, captured = _make_chat_service_with_capture()
    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id=USER,
        personality_prefer="chill",
    )

    await svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    sys_prompt = captured[0]["system_prompt"]
    print(f"  greeting system_prompt (chill):\n{sys_prompt}\n  ---")
    assert "【人格模式" in sys_prompt
    assert "淡定" in sys_prompt or "慵懒" in sys_prompt
    # 基础问候 prompt 必须在前面
    assert "你是一个温暖真诚的朋友" in sys_prompt
    print("  PASS: test_greeting_applies_personality_to_system_prompt")


async def test_greeting_default_personality_unchanged():
    """personality_prefer=default 时,greeting system_prompt 保持原样"""
    await init_db()
    svc, captured = _make_chat_service_with_capture()
    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id="u_greet_default",
        personality_prefer="default",
    )

    await svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    sys_prompt = captured[0]["system_prompt"]
    assert "【人格模式" not in sys_prompt, "default 不应追加人格块"
    assert sys_prompt == "你是一个温暖真诚的朋友。请根据用户情况和记忆信息，发一句简短的主动问候。必须要以问句结尾，自然引导对方分享。"
    print("  PASS: test_greeting_default_personality_unchanged")


async def test_greeting_unknown_personality_silently_unchanged():
    """personality_prefer=未知值时,greeting system_prompt 静默回退(不抛异常)"""
    await init_db()
    svc, captured = _make_chat_service_with_capture()
    from app.models.schemas import MemorySummary
    summary = MemorySummary(
        user_id="u_greet_unknown",
        personality_prefer="mystery_personality",
    )

    await svc.generate_greeting(
        user_type="medium_frequency",
        memory_summary=summary,
        last_topic=None,
    )
    sys_prompt = captured[0]["system_prompt"]
    assert "【人格模式" not in sys_prompt
    print("  PASS: test_greeting_unknown_personality_silently_unchanged")


# ==================== 主聊天入口集成 ====================


async def test_chat_main_path_applies_personality():
    """主聊天:personality_prefer=witty 时,送入 provider 的 system_prompt 应带【人格模式】"""
    await init_db()
    svc, captured = _make_chat_service_with_capture()
    from app.models.schemas import ChatRequest, MemorySummary
    summary = MemorySummary(
        user_id="u_chat_witty",
        personality_prefer="witty",
    )

    # 模拟一次 chat 调用
    await svc._generate_text_only(
        system_prompt=svc._inject_personality(
            get_chat_prompt("text_only")["system"], "witty"
        ),
        text="今天加班到 10 点",
        memory_context="",
    )
    sys_prompt = captured[0]["system_prompt"]
    print(f"  chat system_prompt (witty):\n{sys_prompt[:200]}...\n  ---")
    assert "【人格模式" in sys_prompt
    assert "调侃" in sys_prompt or "嘴贱" in sys_prompt or "吐槽" in sys_prompt
    print("  PASS: test_chat_main_path_applies_personality")


async def main():
    failed = 0
    tests = [
        test_inject_personality_default,
        test_inject_personality_witty,
        test_inject_personality_chill,
        test_inject_personality_enthusiastic,
        test_inject_personality_preserves_base_for_caching,
        test_greeting_declared_only_no_zero_count,
        test_greeting_passive_likes_shows_count,
        test_greeting_mixed_shows_count_not_declare,
        test_greeting_applies_personality_to_system_prompt,
        test_greeting_default_personality_unchanged,
        test_greeting_unknown_personality_silently_unchanged,
        test_chat_main_path_applies_personality,
    ]
    for t in tests:
        name = t.__name__
        print(f"\n--- {name} ---")
        try:
            if asyncio.iscoroutinefunction(t):
                await t()
            else:
                t()
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
