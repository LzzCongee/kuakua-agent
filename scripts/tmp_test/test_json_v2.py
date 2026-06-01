"""
v2 测试:统一 max_tokens=500,加上 topic 定义,看真实服从率和准确率。
"""

import asyncio
import json
import re
import sys
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


# 12 topic 候选,带一句话定义(让 LLM 知道边界)
TOPIC_DEFS = """- general: 兜底,实在归不进其他类的闲聊/打招呼
- self_care: 用户身体/精力疲惫,需要被照顾和休息("好累"、"撑不住"、"想歇一歇")
- self_love: 用户怀疑/否定自己,需要被肯定("我是不是不够好"、"没人喜欢我")
- parenting: 涉及孩子(自己孩子/如何当父母)
- career: 工作、学习、面试、同事关系、能力成长
- beauty: 外貌、穿搭、化妆、身材
- love: 恋爱、伴侣、暗恋、表白(非亲子/非自我)
- daily: 日常生活的小确幸或普通分享(天气、吃饭、买咖啡)
- healing: 已经受伤/失去/结束,在慢慢修复中(分手后、亲人离世、挫败后)
- gratitude: 表达感恩、珍惜、感动
- new_day: 开启新一天/早安/晚安/打起精神
- rebuild: 处境艰难需要陪伴和重建(失业、失恋、抑郁)"""


def _extract_first_balanced_json(text: str) -> str | None:
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
    if not raw:
        return None
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    candidate = _extract_first_balanced_json(raw)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "reply" in obj and "topic" in obj:
                return obj
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
  "topic": "从下面 12 个话题中选最匹配的一个"
}}

【话题定义】
{topic_defs}

【用户消息】
{user_text}
"""


# (用户消息, 期望 topic)
TEST_CASES = [
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
    ("刚被分手,心好痛", "healing"),
    ("今天心情好,想找人聊天", "general"),
    ("和父母吵架了,觉得不被理解", "parenting"),
    ("想换个发型,不知道适合什么", "beauty"),
    ("在准备考研,压力好大", "career"),
]

ALLOWED = set(re.findall(r"^- (\w+):", TOPIC_DEFS, re.MULTILINE))


async def call_once(provider, system, user, max_tokens=500):
    return await provider.generate(
        prompt=user,
        system_prompt=system,
        temperature=0.7,
        max_tokens=max_tokens,
    )


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

    # 单条试看效果
    print("=" * 60)
    print("【单条样本】")
    print("=" * 60)
    user_text = "今天被同事抢了功劳,心里憋屈又不敢说"
    prompt = PROMPT.format(persona=PERSONA, topic_defs=TOPIC_DEFS, user_text=user_text)
    raw = await call_once(provider, PERSONA, prompt, max_tokens=500)
    print(f"raw: {raw}\n")
    parsed = parse_llm_output(raw)
    print(f"parsed: {parsed}\n")

    # 25 条准确率
    print("=" * 60)
    print("【Topic 分类 25 条,max_tokens=500,带 topic 定义】")
    print("=" * 60)
    hits = 0
    parse_fail = 0
    misses = []
    topic_dist = Counter()
    for i, (user_text, expected) in enumerate(TEST_CASES, 1):
        prompt = PROMPT.format(persona=PERSONA, topic_defs=TOPIC_DEFS, user_text=user_text)
        raw = await call_once(provider, PERSONA, prompt, max_tokens=500)
        parsed = parse_llm_output(raw)
        if not parsed:
            parse_fail += 1
            print(f"  [{i:02d}] PARSE_FAIL expect={expected:11s}")
            print(f"       raw: {raw!r}")
            continue
        actual = parsed.get("topic")
        if actual not in ALLOWED:
            print(f"  [{i:02d}] INVALID_TOPIC actual={actual!r}")
            continue
        topic_dist[actual] += 1
        if actual == expected:
            hits += 1
            print(f"  [{i:02d}] OK       expect={expected:11s} actual={actual:11s}")
        else:
            misses.append((user_text, expected, actual))
            print(f"  [{i:02d}] NO       expect={expected:11s} actual={actual:11s}  | {user_text[:30]}")

    total = len(TEST_CASES)
    print(f"\n  parse ok: {(total - parse_fail)}/{total}")
    print(f"  topic 准: {hits}/{total - parse_fail} = {hits/max((total-parse_fail),1)*100:.1f}%")
    print(f"  topic 分布: {dict(topic_dist)}")
    if misses:
        print("\n  误分类样本:")
        for u, e, a in misses:
            print(f"    期望 {e:11s} 实际 {a:11s} | {u}")

    # 压力测试
    print("\n" + "=" * 60)
    print("【压力测试 15 次同 prompt】")
    print("=" * 60)
    user_text = "今天跑完了 5 公里,虽然慢但没停"
    prompt = PROMPT.format(persona=PERSONA, topic_defs=TOPIC_DEFS, user_text=user_text)
    compliance = 0
    topic_stress_dist = Counter()
    for i in range(15):
        raw = await call_once(provider, PERSONA, prompt, max_tokens=500)
        parsed = parse_llm_output(raw)
        if parsed:
            compliance += 1
            t = parsed.get("topic")
            if t in ALLOWED:
                topic_stress_dist[t] += 1
        else:
            print(f"  [{i+1:02d}] FAIL raw: {raw!r}")
    print(f"  解析成功: {compliance}/15 = {compliance/15*100:.1f}%")
    print(f"  topic 分布: {dict(topic_stress_dist)}")


if __name__ == "__main__":
    asyncio.run(main())
