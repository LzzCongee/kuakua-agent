"""
测试 DeepSeek-v4-flash 在 kuakua-agent 上下文下输出 JSON 格式的服从性。

5 个测试场景:
  A. 纯 JSON 指令(无 kuakua 上下文) - 基线
  B. JSON 指令 + markdown 代码块容忍
  C. 嵌入真实 kuakua 人格的 system prompt
  D. Topic 分类准确率(20 条用户输入 × 12 个候选)
  E. 压力测试:连续 20 次同 prompt,统计服从率
"""

import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 强制 stdout 用 UTF-8,避免 Windows GBK 编码炸 Unicode
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 让脚本能从项目根 import
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402


# 12 个 topic 候选(与方案对齐)
ALLOWED_TOPICS = {
    "general", "self_care", "self_love", "parenting",
    "career", "beauty", "love", "daily",
    "healing", "gratitude", "new_day", "rebuild",
}
TOPIC_LIST_STR = " / ".join(sorted(ALLOWED_TOPICS))


# ---------- 解析工具 ----------

CODE_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
ANY_JSON_OBJ = re.compile(r"\{[^{}]*?\"reply\"[^{}]*?\}", re.DOTALL)
# 宽松匹配:reply 字段值里有大括号或嵌套的情况
ANY_JSON_OBJ_LOOSE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_first_balanced_json(text: str) -> str | None:
    """手写括号配对:找到第一个平衡的 {...} 块。处理字符串内的花括号。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
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
                return text[start : i + 1]
    return None


def parse_llm_output(raw: str) -> dict | None:
    """尽可能宽容地从 LLM 输出中提取 {reply, topic} 结构。
    返回 dict 或 None。"""
    if not raw:
        return {"__raw__": raw, "__error__": "empty"}
    raw = raw.strip()

    # 1) 直接 JSON 解析
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # 2) ```json ... ``` 围栏
    m = CODE_FENCE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "reply" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 3) 文本里嵌入的 {...} 块(手写括号配对,处理嵌套和字符串内花括号)
    candidate = _extract_first_balanced_json(raw)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "reply" in obj and "topic" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    return {"__raw__": raw, "__error__": "no_valid_json"}


def parse_llm_output(raw: str) -> dict | None:
    """尽可能宽容地从 LLM 输出中提取 {reply, topic} 结构。
    返回 dict 或 None。"""
    if not raw:
        return None
    raw = raw.strip()

    # 1) 直接 JSON 解析
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # 2) ```json ... ``` 围栏
    m = CODE_FENCE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "reply" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 3) 文本里嵌入的 {...} 块
    for pattern in (ANY_JSON_OBJ, ANY_JSON_OBJ_LOOSE):
        for m in pattern.finditer(raw):
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict) and "reply" in obj and "topic" in obj:
                    return obj
            except json.JSONDecodeError:
                continue

    return None


def validate_topic(t: str | None) -> str | None:
    if t and t in ALLOWED_TOPICS:
        return t
    return None


# ---------- Prompt 构造 ----------

PERSONA_BLOCK = """你是一个真诚、温暖的朋友，善于发现别人身上被忽略的闪光点。

【核心方法论】
- 夸努力和选择,不夸天赋
- 先验证情绪,再给予肯定
- 像朋友私下聊天的语气,不是颁奖致辞
- 30字以内,口语化
"""


PROMPT_PLAIN = """请按以下 JSON 结构输出你的回复(不要任何其他内容、不要 markdown 代码块):
{{
  "reply": "你的回复内容,20-100字,口语化,必须以问句或邀请结尾",
  "topic": "从以下 12 个话题中选最匹配的一个: {topics}"
}}

用户说: {user_text}
"""


PROMPT_STRICT = """严格输出:从你的下一条消息起,只输出一个 JSON 对象,{{ 和 }} 之外不出现任何字符,不能有解释、不能有 markdown 代码块、不能有前言后语。

格式:
{{
  "reply": "string,20-100字,口语化",
  "topic": "从以下 12 个话题中选最匹配的一个: {topics}"
}}

用户说: {user_text}
"""


PROMPT_WITH_PERSONA = """{persona}

【输出格式要求】
请用以下 JSON 结构输出(不要有其他内容、不要 markdown 代码块、不要解释):
{{
  "reply": "你的回复内容,20-100字,口语化",
  "topic": "从以下 12 个话题中选最匹配的一个: {topics}"
}}

用户说: {user_text}
"""


# ---------- 测试用例 ----------

# (用户消息, 期望 topic)
TOPIC_TEST_CASES = [
    ("今天又被 leader 阴阳怪气了,真的想辞职", "career"),
    ("加班到十一点,回到家什么都不想干", "self_care"),
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


# ---------- 测试 Runner ----------

async def call_once(provider: OpenAICompatibleProvider, system: str, user: str, max_tokens: int = 300) -> str:
    return await provider.generate(
        prompt=user,
        system_prompt=system,
        temperature=0.7,
        max_tokens=max_tokens,
    )


async def test_a_plain_json(provider):
    """A. 纯 JSON 指令(无 persona), 看基础服从率"""
    print("\n" + "=" * 60)
    print("【A. 纯 JSON 指令(无 persona)】")
    print("=" * 60)
    user_text = "今天加班到十一点,回到家什么都不想干,觉得自己像个废物"
    prompt = PROMPT_PLAIN.format(topics=TOPIC_LIST_STR, user_text=user_text)
    raw = await call_once(provider, system="", user=prompt)
    print(f"\n[LLM 原始输出]\n{raw}\n")
    parsed = parse_llm_output(raw)
    if parsed:
        print(f"[解析成功] reply={parsed.get('reply')[:60]!r}")
        print(f"            topic={validate_topic(parsed.get('topic'))!r}")
    else:
        print("[解析失败] 无法从输出中提取 {reply, topic} 结构")
    return parsed is not None


async def test_b_markdown_tolerance(provider):
    """B. 提示 LLM 输出 markdown 围栏,看解析器能否处理"""
    print("\n" + "=" * 60)
    print("【B. Markdown 围栏格式(LLM 自由发挥但用围栏)】")
    print("=" * 60)
    user_text = "我家孩子这次考试进步了 20 名,想夸夸他"
    # 不主动要求 JSON,看 LLM 自由发挥时是否仍会输出可解析结构
    prompt = f"用户说:{user_text}\n\n请用 JSON 回答(可以用 markdown 代码块包裹)。"
    raw = await call_once(provider, system="", user=prompt)
    print(f"\n[LLM 原始输出]\n{raw}\n")
    parsed = parse_llm_output(raw)
    if parsed:
        print(f"[解析成功] topic={validate_topic(parsed.get('topic'))!r}")
    else:
        print("[解析失败]")
    return parsed is not None


async def test_c_with_kuakua_persona(provider):
    """C. 嵌入真实 kuakua 人格 system prompt"""
    print("\n" + "=" * 60)
    print("【C. 嵌入真实 kuakua 人格后的输出】")
    print("=" * 60)
    user_text = "今天被同事抢了功劳,心里憋屈又不敢说"
    system = PERSONA_BLOCK
    prompt = PROMPT_PLAIN.format(topics=TOPIC_LIST_STR, user_text=user_text)
    raw = await call_once(provider, system=system, user=prompt, max_tokens=500)
    print(f"\n[LLM 原始输出](len={len(raw)})\n{raw}\n")
    parsed = parse_llm_output(raw)
    if parsed and "__error__" not in parsed:
        print(f"[解析成功] reply={parsed.get('reply')[:80]!r}")
        print(f"            topic={validate_topic(parsed.get('topic'))!r}")
    else:
        print(f"[解析失败] {parsed.get('__error__') if isinstance(parsed, dict) else 'unknown'}")
    return parsed is not None and "__error__" not in parsed


async def test_c2_strict_prompt(provider):
    """C2. 超严格 JSON 指令"""
    print("\n" + "=" * 60)
    print("【C2. 超严格 JSON 指令(禁止任何额外字符)】")
    print("=" * 60)
    user_text = "今天被同事抢了功劳,心里憋屈又不敢说"
    prompt = PROMPT_STRICT.format(topics=TOPIC_LIST_STR, user_text=user_text)
    raw = await call_once(provider, system=PERSONA_BLOCK, user=prompt, max_tokens=500)
    print(f"\n[LLM 原始输出](len={len(raw)})\n{raw}\n")
    parsed = parse_llm_output(raw)
    if parsed and "__error__" not in parsed:
        print(f"[解析成功] reply={parsed.get('reply')[:80]!r}")
        print(f"            topic={validate_topic(parsed.get('topic'))!r}")
    else:
        print(f"[解析失败] {parsed.get('__error__') if isinstance(parsed, dict) else 'unknown'}")
    return parsed is not None and "__error__" not in parsed


async def test_d_topic_accuracy(provider):
    """D. Topic 分类准确率(20 条)"""
    print("\n" + "=" * 60)
    print("【D. Topic 分类准确率(20 条)】")
    print("=" * 60)
    hits = 0
    misses = []
    parse_fail = 0
    for i, (user_text, expected) in enumerate(TOPIC_TEST_CASES, 1):
        prompt = PROMPT_PLAIN.format(topics=TOPIC_LIST_STR, user_text=user_text)
        raw = await call_once(provider, system=PERSONA_BLOCK, user=prompt, max_tokens=200)
        parsed = parse_llm_output(raw)
        if not parsed or "__error__" in parsed:
            parse_fail += 1
            err = parsed.get("__error__") if isinstance(parsed, dict) else "unknown"
            print(f"  [{i:02d}] 解析失败({err}) | {user_text[:30]!r}")
            print(f"       FULL raw: {raw!r}")
            continue
        actual = validate_topic(parsed.get("topic"))
        if actual == expected:
            hits += 1
            mark = "OK"
        else:
            misses.append((user_text, expected, actual))
            mark = "NO"
        print(f"  [{i:02d}] {mark} expect={expected:11s} actual={actual or 'NULL':11s} | {user_text[:25]!r}")
    print(f"\n准确率: {hits}/{len(TOPIC_TEST_CASES)} = {hits/len(TOPIC_TEST_CASES)*100:.1f}%")
    print(f"解析失败: {parse_fail}/{len(TOPIC_TEST_CASES)}")
    if misses:
        print("\n误分类样本:")
        for u, e, a in misses:
            print(f"  期望 {e:11s} 实际 {a or 'NULL':11s} | {u}")
    return hits / len(TOPIC_TEST_CASES)


async def test_e_stress_compliance(provider, n: int = 20):
    """E. 压力测试: 同一 prompt 跑 N 次, 统计 JSON 服从率"""
    print("\n" + "=" * 60)
    print(f"【E. 压力测试: 同 prompt × {n} 次, JSON 服从率】")
    print("=" * 60)
    user_text = "今天跑完了 5 公里,虽然慢但没停"
    prompt = PROMPT_PLAIN.format(topics=TOPIC_LIST_STR, user_text=user_text)
    system = PERSONA_BLOCK

    compliance = 0
    markdown_violation = 0
    valid_topic = 0
    topic_dist = Counter()

    for i in range(n):
        raw = await call_once(provider, system=system, user=prompt, max_tokens=200)
        parsed = parse_llm_output(raw)
        if parsed:
            compliance += 1
        if "```" in raw:
            markdown_violation += 1
        topic = validate_topic((parsed or {}).get("topic"))
        if topic:
            valid_topic += 1
            topic_dist[topic] += 1
        # 打印前 3 个原始输出做样本
        if i < 3:
            print(f"\n  [样本 {i+1}] raw: {raw[:120]!r}")

    print(f"\n  解析成功: {compliance}/{n} = {compliance/n*100:.1f}%")
    print(f"  含 markdown 围栏(不致命,解析器能处理): {markdown_violation}/{n}")
    print(f"  topic 有效: {valid_topic}/{n}")
    print(f"  topic 分布: {dict(topic_dist)}")
    return compliance / n


async def main():
    settings = get_settings()
    cfg = settings.ai_chat
    print(f"使用模型: {cfg.model} @ {cfg.base_url}")
    print(f"API Key 前 8 位: {cfg.api_key[:8]}...")

    provider = OpenAICompatibleProvider(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
    )

    # 跑一遍
    a_ok = await test_a_plain_json(provider)
    b_ok = await test_b_markdown_tolerance(provider)
    c_ok = await test_c_with_kuakua_persona(provider)
    c2_ok = await test_c2_strict_prompt(provider)
    d_acc = await test_d_topic_accuracy(provider)
    e_rate = await test_e_stress_compliance(provider, n=20)

    print("\n" + "=" * 60)
    print("【总览】")
    print("=" * 60)
    print(f"  A. 纯 JSON 指令     : {'通过' if a_ok else '失败'}")
    print(f"  B. Markdown 围栏    : {'通过' if b_ok else '失败'}")
    print(f"  C. 带 kuakua 人格   : {'通过' if c_ok else '失败'}")
    print(f"  C2. 超严格 JSON 指令: {'通过' if c2_ok else '失败'}")
    print(f"  D. Topic 准确率     : {d_acc*100:.1f}%")
    print(f"  E. JSON 服从率(20次): {e_rate*100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
