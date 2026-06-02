"""
v3 测试:验证 stream 模式的可行方案
  T1. LLM 流式输出 JSON 时的样子(看 chunk 序列)
  T2. "非流式 + JSON + 解析 + SSE 包装" 方案的整体时序和 UX
  T3. 温度 0.3 下 JSON 服从率 + topic 准确率
  T4. 对比:"真流式 + 后置解析" vs "非流式 + 包装流式"
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import get_settings
from app.providers.openai_compatible import OpenAICompatibleProvider


ALLOWED = {
    "general", "self_care", "self_love", "parenting",
    "career", "beauty", "love", "daily",
    "healing", "gratitude", "new_day", "rebuild",
}
TOPIC_LIST = " / ".join(sorted(ALLOWED))


def _extract_first_balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json(raw):
    if not raw:
        return None
    try:
        obj = json.loads(raw.strip())
        return obj if isinstance(obj, dict) and "reply" in obj else None
    except json.JSONDecodeError:
        pass
    c = _extract_first_balanced_json(raw)
    if c:
        try:
            obj = json.loads(c)
            return obj if isinstance(obj, dict) and "reply" in obj and "topic" in obj else None
        except json.JSONDecodeError:
            pass
    return None


PERSONA = """你是一个真诚、温暖的朋友,善于发现别人身上被忽略的闪光点。
- 夸努力和选择,不夸天赋
- 先验证情绪,再给予肯定
- 像朋友私下聊天的语气,不是颁奖致辞
- 30字以内,口语化
"""

PROMPT = """{persona}

【输出格式】
请用以下 JSON 结构输出(不要有其他内容、不要 markdown 代码块):
{{
  "reply": "你的回复内容,20-100字,口语化,必须以问句或邀请结尾",
  "topic": "从以下 12 个话题中选最匹配的一个: {topics}"
}}

【话题边界定义】
- general: 兜底闲聊/打招呼(慎用,只有确实没有具体主题才用)
- self_care: 身体/精力疲惫,需要休息("好累"、"撑不住"、"想歇一歇")
- self_love: 怀疑/否定自我,需要被肯定("我不够好"、"没人喜欢我")
- parenting: 涉及孩子教养或作为父母的反思
- career: 工作、学习、面试、同事关系、能力成长
- beauty: 外貌、穿搭、化妆、身材
- love: 恋爱、伴侣(非亲子/非自我)
- daily: 日常生活小确幸或普通分享
- healing: 已经受伤/失去/结束,在慢慢修复中(分手后、亲人离世、挫败后)
- gratitude: 表达感恩、珍惜
- new_day: 早安/晚安/打起精神
- rebuild: 处境艰难需要陪伴(失业/抑郁/长期低落)

用户说: {user_text}
"""


# ============== T1: 流式 LLM 输出长啥样 ==============
async def test_t1_stream_chunks(provider):
    print("=" * 60)
    print("【T1. 流式 LLM 输出 JSON 时的 chunk 序列】")
    print("=" * 60)
    user_text = "今天加班到 11 点,回到家什么都不想干"
    prompt = PROMPT.format(persona=PERSONA, topics=TOPIC_LIST, user_text=user_text)
    print("场景: 客户端会看到什么?\n")

    chunks = []
    async for chunk in provider.generate_stream(
        prompt=prompt, system_prompt=PERSONA, temperature=0.3, max_tokens=500
    ):
        chunks.append(chunk)

    # 拼接
    full = "".join(chunks)
    print(f"收到 {len(chunks)} 个 chunk,总长度 {len(full)} 字符")
    print(f"\n前 10 个 chunk:")
    for i, c in enumerate(chunks[:10]):
        print(f"  [{i+1:02d}] {c!r}")
    print(f"\n后 5 个 chunk:")
    for i, c in enumerate(chunks[-5:]):
        print(f"  [{len(chunks)-5+i+1:02d}] {c!r}")

    print(f"\n[完整拼接]\n{full}\n")

    # 解析
    parsed = parse_json(full)
    if parsed:
        print(f"[解析成功] reply={parsed.get('reply')[:50]!r}... topic={parsed.get('topic')!r}")
    else:
        print("[解析失败]")

    # 关键问题:客户端看到的是不是 JSON 语法字符?
    syntax_chars = sum(1 for c in chunks if c in '{}":,')
    print(f"\n客户端会看到 {syntax_chars} 个 JSON 语法字符({{}}:,)\"等)穿插在文本中")
    print("→ 结论:流式 LLM 输出 JSON 时,直接 forward 给客户端体验很差")

    return parsed is not None


# ============== T2: 包装方案整体时序 ==============
async def fake_sse_emit(reply_text, topic, chunk_size=8, chunk_delay=0.04):
    """模拟 SSE 包装:解析完 LLM 响应后,把 reply 切成 chunk 发出。
    chunk_delay 控制每个 chunk 之间的延迟(秒)。"""
    emitted = []
    t0 = time.time()
    for i in range(0, len(reply_text), chunk_size):
        chunk = reply_text[i:i+chunk_size]
        elapsed = time.time() - t0
        await asyncio.sleep(chunk_delay)
        emitted.append({
            "event": "chunk",
            "data": json.dumps({"content": chunk}, ensure_ascii=False),
            "elapsed": round(elapsed, 3),
        })
    # done 事件
    elapsed = time.time() - t0
    emitted.append({
        "event": "done",
        "data": json.dumps({"scene": topic, "has_image": False}, ensure_ascii=False),
        "elapsed": round(elapsed, 3),
    })
    return emitted


async def test_t2_wrap_timing(provider):
    print("\n" + "=" * 60)
    print("【T2. 非流式 + 包装成 SSE 的整体时序】")
    print("=" * 60)
    user_text = "今天跑完了 5 公里,虽然慢但没停"
    prompt = PROMPT.format(persona=PERSONA, topics=TOPIC_LIST, user_text=user_text)

    # 模拟用户视角:从发请求到收到 SSE 事件
    print("\n[T+0.000] 客户端发起请求,显示 loading\n")
    t_request = time.time()

    # 后端:非流式调用
    raw = await provider.generate(
        prompt=prompt, system_prompt=PERSONA, temperature=0.3, max_tokens=500
    )
    t_llm_done = time.time()
    llm_elapsed = t_llm_done - t_request
    print(f"[T+{llm_elapsed:.2f}s] LLM 非流式调用完成 (收到完整响应,len={len(raw)})\n")

    parsed = parse_json(raw)
    if parsed:
        reply = parsed["reply"]
        topic = parsed["topic"]
    else:
        reply = raw
        topic = "general"
    print(f"[T+{llm_elapsed:.2f}s] 解析完成 → topic={topic!r}, reply={reply!r}\n")

    # 包装为 SSE
    print(f"[T+{llm_elapsed:.2f}s] 开始 yield SSE chunk ...")
    events = await fake_sse_emit(reply, topic, chunk_size=8, chunk_delay=0.04)
    for e in events[:3]:
        print(f"  [T+{llm_elapsed + e['elapsed']:.2f}s] event={e['event']} data={e['data'][:60]!r}")
    print(f"  ... (省略中间 {len(events)-5} 个 chunk)")
    for e in events[-2:]:
        print(f"  [T+{llm_elapsed + e['elapsed']:.2f}s] event={e['event']} data={e['data'][:60]!r}")

    total = time.time() - t_request
    print(f"\n[总耗时] {total:.2f}s")
    print(f"  - LLM 等待: {llm_elapsed:.2f}s ({llm_elapsed/total*100:.0f}%)")
    print(f"  - chunk yield: {total - llm_elapsed:.2f}s")

    return parsed is not None


# ============== T3: 温度 0.3 的稳定性 ==============
async def test_t3_temp_stability(provider):
    print("\n" + "=" * 60)
    print("【T3. 温度 0.3 下 JSON 服从率 + topic 准确率】")
    print("=" * 60)
    cases = [
        ("今天又被 leader 阴阳怪气了,真的想辞职", "career"),
        ("加班到十一点,回到家什么都不想干,觉得自己像个废物", "self_care"),
        ("我是不是不够好,为什么没人喜欢我", "self_love"),
        ("我家孩子这次考试进步了 20 名,想夸夸他", "parenting"),
        ("我今天化了妆出门,觉得自己好看了", "beauty"),
        ("和对象吵架了,他在冷战我该怎么办", "love"),
        ("今天早上买咖啡店员多送了一块饼干,开心", "daily"),
        ("分手两个月了,还是会想起他", "healing"),
        ("今天和妈妈视频了,突然很感恩她还在", "gratitude"),
        ("新的一天,想打起精神", "new_day"),
        ("失业三个月了,整个人都很丧", "rebuild"),
        ("刚跑完 5 公里,虽然慢但没停", "daily"),
        ("同事抢了我的功劳,我不敢说", "career"),
        ("每天都好累,觉得自己撑不住了", "rebuild"),
        ("今天穿了件新衣服,想听你夸夸", "beauty"),
        ("孩子不听话,我吼了他,现在很后悔", "parenting"),
        ("和男朋友在一起三年了,还是心动", "love"),
        ("下雨天窝在家里看书,真舒服", "daily"),
        ("失眠三个月,觉得自己快崩溃了", "rebuild"),
        ("今天工作得到客户表扬了!", "career"),
    ]
    hits = 0
    parse_fail = 0
    topic_dist = Counter()
    misses = []
    for i, (u, expected) in enumerate(cases, 1):
        prompt = PROMPT.format(persona=PERSONA, topics=TOPIC_LIST, user_text=u)
        raw = await provider.generate(
            prompt=prompt, system_prompt=PERSONA, temperature=0.3, max_tokens=500
        )
        parsed = parse_json(raw)
        if not parsed:
            parse_fail += 1
            print(f"  [{i:02d}] PARSE_FAIL | {u[:30]}")
            continue
        actual = parsed.get("topic")
        if actual not in ALLOWED:
            print(f"  [{i:02d}] INVALID_TOPIC={actual!r}")
            continue
        topic_dist[actual] += 1
        if actual == expected:
            hits += 1
        else:
            misses.append((u, expected, actual))
    total = len(cases)
    valid = total - parse_fail
    print(f"\n  parse ok: {valid}/{total}")
    print(f"  topic 准: {hits}/{valid} = {hits/max(valid,1)*100:.1f}%")
    print(f"  topic 分布: {dict(topic_dist)}")
    if misses:
        print("\n  误分类:")
        for u, e, a in misses:
            print(f"    期望 {e:11s} 实际 {a:11s} | {u}")
    return hits / max(valid, 1)


# ============== T4: 真流式 vs 包装流式 时序对比 ==============
async def test_t4_real_stream_vs_wrap(provider):
    print("\n" + "=" * 60)
    print("【T4. 真流式(LLM 层) vs 非流式+包装  时序对比】")
    print("=" * 60)
    user_text = "今天被同事抢了功劳,心里憋屈又不敢说"
    prompt = PROMPT.format(persona=PERSONA, topics=TOPIC_LIST, user_text=user_text)

    # 方案 A:真流式(LLM 层 stream=True)
    print("\n--- 方案 A: 真流式(LLM 层 stream) ---")
    t0 = time.time()
    first_chunk_at = None
    raw_chunks = []
    async for chunk in provider.generate_stream(
        prompt=prompt, system_prompt=PERSONA, temperature=0.3, max_tokens=500
    ):
        if first_chunk_at is None:
            first_chunk_at = time.time() - t0
        raw_chunks.append(chunk)
    full = "".join(raw_chunks)
    a_first = first_chunk_at
    a_total = time.time() - t0
    print(f"  首 chunk 延迟: {a_first:.2f}s")
    print(f"  总耗时: {a_total:.2f}s (含 stream 全部结束)")
    print(f"  拿到完整文本: {a_total:.2f}s")

    # 方案 B:非流式 + 包装 SSE
    print("\n--- 方案 B: 非流式 + 包装 SSE ---")
    t0 = time.time()
    raw = await provider.generate(
        prompt=prompt, system_prompt=PERSONA, temperature=0.3, max_tokens=500
    )
    t_llm = time.time() - t0
    parsed = parse_json(raw)
    reply = parsed["reply"] if parsed else raw
    # 模拟包装:yield 8 字符/40ms
    n_chunks = (len(reply) + 7) // 8
    yield_time = n_chunks * 0.04
    b_first = t_llm
    b_total = t_llm + yield_time
    print(f"  首 chunk 延迟: {b_first:.2f}s (LLM 完整响应后才开始)")
    print(f"  yield 总耗时: {yield_time:.2f}s")
    print(f"  拿到完整文本: {b_total:.2f}s")

    print("\n[对比]")
    print(f"  方案 A 首 chunk 早: {a_first:.2f}s")
    print(f"  方案 B 拿到完整早: {b_total:.2f}s vs A 的 {a_total:.2f}s")
    print(f"  方案 A 优点:打字机效果,从 {a_first:.2f}s 起用户开始看到内容")
    print(f"  方案 B 优点:JSON 解析 100% 可靠,无前导语法字符问题")
    print(f"  方案 A 缺点:用户先看到 JSON 语法({{}}:,\"\\n),需要客户端后处理才能显示")
    print(f"  方案 B 缺点: {t_llm:.2f}s 的完全静默期,用户只能看 loading")


async def main():
    settings = get_settings()
    cfg = settings.ai_chat
    print(f"模型: {cfg.model} @ {cfg.base_url}\n")
    provider = OpenAICompatibleProvider(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
    )

    t1_ok = await test_t1_stream_chunks(provider)
    await test_t2_wrap_timing(provider)
    t3_acc = await test_t3_temp_stability(provider)
    await test_t4_real_stream_vs_wrap(provider)

    print("\n" + "=" * 60)
    print("【总览】")
    print("=" * 60)
    print(f"  T1. 流式 LLM 输出 JSON 是否可用: {'是' if t1_ok else '否'}")
    print(f"  T3. 温度 0.3 准确率: {t3_acc*100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
