# 话题偏好个性化设计 v2

> 本文定稿于 2026-06-02,在 v1 基础上修订,核心修正:① LLM 自报 topic(不再依赖前端 scene)② 固定 12 话题 + 强边界定义 ③ 流式接口改为"非流式+包装"架构 ④ 温度降到 0.3。

---

## 一、为什么需要这次改造

### 1.1 现状盘点

| 维度 | 当前实现 | 问题 |
|------|---------|------|
| 问候语类型 | 4 类(new/light_return/medium/low)按时间间隔分 | 类型合理,但**主题无差异** |
| 问候语主题 | 硬编码在 system prompt,不结合用户偏好 | 同质化,老用户无新鲜感 |
| Chat topic | 前端 `ChatRequest.scene` 用户选 | **是"用户意图"不是"内容 topic"** |
| 收藏(scene) | 前端 favorite 调用硬编码 `scene: 'general'` | **信号全污染,数据失真** |
| Like 信号 | 无 | 缺失 |
| Prompt 注入 | memory 4 区块(current/interaction/profile/deep) | 无 topic 偏好维度 |
| 流式接口 | LLM 真流式,纯文本 | 无法承载 JSON topic 解析 |

### 1.2 核心矛盾

**用户已经在告诉我们他们喜欢什么了(收藏行为),但我们没用这个信号。**

更进一步:**用户喜欢的"夸夸话题"应该是这条 AI 回复内容的 topic,而不是用户进会话时选的那个 scene**。用户在 general 场景聊加班,可能希望被以 self_care(被照顾)角度回应,而不是 general(兜底闲聊)。

### 1.3 改造目标

1. **AI 回复**自动输出其内容的 topic(LLM 自报)
2. **收藏动作** = 对该回复 topic 的"点赞"(语义升级,前端 0 改动)
3. **用户画像** 累积 topic 偏好,带衰减权重
4. **Prompt 注入** 第 5 区块【话题偏好】,影响 chat 和 greeting 的内容选择
5. **流式 UX** 保持,JSON 解析在服务端完成

---

## 二、核心概念

### 2.1 Topic 维度

**Topic = AI 回复内容的语义分类**,从固定的 12 个里选 1 个。**不是用户意图,不是用户标签**。

| 旧理解 | 新理解 |
|--------|--------|
| `ChatRequest.scene` = 用户期望聊的话题 | 不变,但只用于**选 prompt 模板**,不再决定 reply topic |
| `Message.topic` = 回复内容 topic | **新增字段**,LLM 自报 |
| `Favorite.scene` = 收藏时的话题 | **语义升级**为"点赞信号",值=被收藏回复的 topic |

### 2.2 Like 信号

**"收藏"语义升级为"对这条回复的 topic 表态认同"**。等价于点赞,但保留"持久化可回看"的能力。

| 操作 | 含义 | 数据用途 |
|------|------|---------|
| 收藏 + 留存 | 认同 + 想要再读 | 长期回看(原 PRD 需求) |
| 取消收藏 | 不再认同/不再需要 | like_count 扣减(平局回退) |
| 多次收藏同 topic | 持续认同 | 偏好权重持续上升 |

**为什么不新增 like 表**: 与 favorite 表语义重叠且能复用,改一个字段即可(`like_type` 暂不加,先复用 scene 字段填真实 topic)。

### 2.3 衰减权重

用户的偏好会随时间变化。**最近 14 天内**的点赞权重最大,更早的点赞线性衰减,14 天前的权重 = 50%。

```
weight = like_count × (0.5 ^ (days_since_last_like / 14))
```

不设硬窗口(全部历史参与计算),让衰减函数自然处理"老用户偏好转移"。

### 2.4 平局规则

| 第一名权重 vs 第二名 | 注入策略 |
|----------------------|---------|
| ≥ 1.5x | 单 topic 注入(强主导) |
| < 1.5x | 前 3 个 topic 一起注入(平局) |

### 2.5 冷启动

- 总点赞 < 3:不注入【话题偏好】区块,整段隐藏
- 不强制要求新用户先点赞,让偏好自然积累

---

## 三、Topic Taxonomy(12 个固定)

LLM 必须从这 12 个里选,语义边界在 prompt 中明确定义。

```python
ALLOWED_TOPICS = {
    "general", "self_care", "self_love", "parenting",
    "career", "beauty", "love", "daily",
    "healing", "gratitude", "new_day", "rebuild",
}
```

### 3.1 Topic 定义与边界

| Topic | 定义(给 LLM 看的) | 典型用户输入 |
|-------|-------------------|------------|
| `general` | 兜底闲聊/打招呼(慎用,只有确实没有具体主题才用) | "今天心情好,想找人聊天" |
| `self_care` | 身体/精力疲惫,需要休息 | "加班到 11 点,回到家什么都不想干" |
| `self_love` | 怀疑/否定自我,需要被肯定 | "我是不是不够好,为什么没人喜欢我" |
| `parenting` | 涉及孩子教养或作为父母的反思 | "我家孩子进步了 20 名"、"孩子不听话我吼了他" |
| `career` | 工作、学习、面试、同事关系、能力成长 | "被 leader 阴阳怪气"、"同事抢功劳" |
| `beauty` | 外貌、穿搭、化妆、身材 | "今天化了妆出门"、"穿了件新衣服" |
| `love` | 恋爱、伴侣(非亲子/非自我) | "和对象吵架"、"和男朋友三年了还心动" |
| `daily` | 日常生活小确幸或普通分享 | "买咖啡多送了一块饼干"、"下雨天窝在家看书" |
| `healing` | 已经受伤/失去/结束,在慢慢修复中 | "分手两个月了还会想起他"、"刚被分手" |
| `gratitude` | 表达感恩、珍惜 | "和妈妈视频了很感恩她还在" |
| `new_day` | 早安/晚安/打起精神 | "新的一天,想打起精神" |
| `rebuild` | **已陷入长期低落且无明显事件触发**(无差别疲惫、空虚、找不到意义) | "每天都好累,撑不住"、"失眠三个月快崩溃" |

### 3.2 关键边界(v1 误分类点)

**`rebuild` vs `self_care`**: "撑不住"是 `rebuild`(长期无差别低落)还是 `self_care`(具体事件触发的疲劳)?
- `self_care`:有明确诱因,休息就能恢复(加班 → 睡一觉)
- `rebuild`:无差别,不知道因为什么,持续 2 周以上

**`rebuild` vs `healing`**: 同样是低落?
- `healing`:有明确"已经发生的事件"(分手、亲人离世、挫败)
- `rebuild`:无事件,纯粹的"生活没意义感"

**`healing` vs `love`**: 分手后算哪个?
- 刚分手、心痛、刚开始接受 → `healing`
- 在和伴侣相处中(吵架、甜蜜) → `love`

**`parenting` vs `rebuild`**: 和父母吵架?
- 涉及"我作为父母对孩子的反思/行动" → `parenting`
- 和父母发生冲突,情绪反应为主 → `rebuild` 或其他

### 3.3 为什么不用 LLM 自由发挥

| 维度 | 固定 12 | 完全自由 |
|------|---------|---------|
| 聚合 | 直接 GROUP BY | 要做文本相似度聚类 |
| Prompt 注入 | 列表稳定 | 标签越积越多 |
| 缓存命中 | 模板稳定 | 每次可能新增 |
| A/B 测试 | 按 topic 切流 | 难以归因 |

**结论**:固定 12 个,LLM 强制从列表选。新增 topic 是受控产品决策。

### 3.4 为什么不用 `prefer_scene` 替代

`UserProfile.prefer_scene` 已存在,但:
- 粒度只有 5 个(general/career/beauty/love/daily)
- 来自 `MemoryExtractor` 自动推断,有滞后和误判
- 没有"用户主动点赞"的语义

新增的 topic 偏好是**用户显式表态**的累积,与 `prefer_scene` 互补:
- `prefer_scene` → 用户**经常聊**的话题(隐式)
- `topic_preference_snapshot` → 用户**认同**的回复话题(显式)

---

## 四、数据模型

### 4.1 Schema 变更

```sql
-- 1. Message 表新增 topic 字段(LLM 自报)
ALTER TABLE messages ADD COLUMN topic VARCHAR(50) DEFAULT 'general';
CREATE INDEX ix_messages_user_topic ON messages (user_id, topic);

-- 2. 新增 user_topic_preferences 聚合表
CREATE TABLE user_topic_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(100) NOT NULL,
    topic VARCHAR(50) NOT NULL,
    like_count INTEGER NOT NULL DEFAULT 0,
    last_liked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    first_liked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, topic)
);
CREATE INDEX ix_user_topic_count ON user_topic_preferences (user_id, like_count DESC);

-- 3. UserProfile 加 topic_preference_snapshot 字段(JSON 缓存)
ALTER TABLE user_profiles ADD COLUMN topic_preference_snapshot TEXT;
```

**无 Alembic 迁移,以上 SQL 需在 `migrate_db.py` 中手写执行。**

### 4.2 ORM 模型

```python
# app/models/models.py 新增

class UserTopicPreference(Base):
    __tablename__ = "user_topic_preferences"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(50))
    like_count: Mapped[int] = mapped_column(default=0)
    last_liked_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    first_liked_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

# Message 模型加 topic 字段
class Message(Base):
    # ... 现有字段 ...
    topic: Mapped[str] = mapped_column(String(50), default="general")

# UserProfile 加 topic_preference_snapshot 字段
class UserProfile(Base):
    # ... 现有字段 ...
    topic_preference_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
```

---

## 五、Prompt 改造

### 5.1 Chat Prompt 模板(`templates.toml`)

**在每个场景的 `task` 末尾追加 JSON 输出要求和 topic 定义**(`[scenes.general]`、`[scenes.career]` 等 5 个都改;`[multimodal.text_only]`、`[multimodal.mixed]` 等 3 个多模态也改):

```toml
[scenes.general]
role = "你是一个真诚、温暖的朋友,善于发现别人身上被忽略的闪光点。"
task = '''用户会分享生活中的片段,你的任务是给出一句让他们觉得「被真正看见了」的回应。

【输出格式要求 - 严格遵守】
请用以下 JSON 结构输出,不要有其他内容、不要 markdown 代码块、不要解释:
{
  "reply": "你的回复,20-100字,口语化,必须以问句或邀请结尾",
  "topic": "从下面 12 个话题中选最匹配的一个"
}

【话题边界定义 - 严格按边界选择】
- general: 兜底闲聊/打招呼(慎用,只有确实没有具体主题才用)
- self_care: 身体/精力疲惫,需要休息("好累"、"撑不住"、"想歇一歇")
- self_love: 怀疑/否定自我,需要被肯定("我不够好"、"没人喜欢我")
- parenting: 涉及孩子教养或作为父母的反思
- career: 工作、学习、面试、同事关系、能力成长
- beauty: 外貌、穿搭、化妆、身材
- love: 恋爱、伴侣(非亲子/非自我)
- daily: 日常生活小确幸或普通分享
- healing: 已经受伤/失去/结束,在慢慢修复中
- gratitude: 表达感恩、珍惜
- new_day: 早安/晚安/打起精神
- rebuild: 已陷入长期低落且无明显事件触发(无差别疲惫、空虚、找不到意义)'''
user = "从用户说的内容中找到一个具体细节,给一句真诚的回应。"
notes = [
    "从用户输入中找一个最打动你的细节,围绕它展开",
    "30字以内,像朋友发微信的语气",
    "如果用户表达的是负面情绪,先共情再肯定,不要硬夸",
]
```

**5 个 `[scenes.*]` + 3 个 `[multimodal.*]` 都要改,总共 8 处。**

### 5.2 温度与 max_tokens

| 参数 | 旧值 | 新值 | 依据 |
|------|------|------|------|
| temperature | 0.7 / 0.8 | **0.3** | 稳定性优于随机性,测试 85% vs 88% 可接受 |
| max_tokens | 300 | **500** | JSON 输出需 250-350 tokens,300 会被截断 |

### 5.3 Greeting Prompt 是否改

**greeting 是单次短文本输出,不需要 topic 字段**。`generate_greeting` 维持现状(纯文本输出),但 user prompt 末尾**追加【话题偏好】注入**(见 §7)。

---

## 六、Topic 解析工具

### 6.1 解析函数(放在 `app/services/chat_service.py`)

```python
import json
import re
from typing import Optional

ALLOWED_TOPICS = {
    "general", "self_care", "self_love", "parenting",
    "career", "beauty", "love", "daily",
    "healing", "gratitude", "new_day", "rebuild",
}


def _extract_first_balanced_json(text: str) -> Optional[str]:
    """手写括号配对:处理字符串内的花括号,找到第一个 {...} 块。"""
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
                return text[start : i + 1]
    return None


def parse_chat_response(raw: str) -> tuple[str, str]:
    """从 LLM 输出中解析 (reply, topic)。
    解析失败时:(raw, request.scene → general) 三级兜底。

    Returns:
        (reply_text, topic)
    """
    if not raw:
        return "", "general"
    raw = raw.strip()

    # 1) 直接 JSON 解析
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            topic = obj.get("topic", "general")
            return obj["reply"], topic if topic in ALLOWED_TOPICS else "general"
    except json.JSONDecodeError:
        pass

    # 2) 平衡花括号提取
    candidate = _extract_first_balanced_json(raw)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "reply" in obj and "topic" in obj:
                topic = obj["topic"]
                return obj["reply"], topic if topic in ALLOWED_TOPICS else "general"
        except json.JSONDecodeError:
            pass

    # 3) 兜底:把整段当 reply,topic 用 general
    return raw, "general"
```

### 6.2 Chat 入口改造(`app/api/chat.py`)

非流式 chat 端点(`chat()` 函数,line 537):

```python
# 原
content = await service.provider.generate(user_prompt, system_prompt=system_prompt)

# 新
raw = await service.provider.generate(
    user_prompt,
    system_prompt=system_prompt,
    temperature=0.3,
    max_tokens=500,
)
reply, topic = parse_chat_response(raw)

# 构造响应
response = ChatResponse(
    content=reply,
    scene=topic,  # 改用 LLM 自报 topic
    has_image=prep.has_image,
    image_desc=image_desc,
)

# 持久化时存 topic
await memory_service.add_message(
    session_id=session_id,
    user_id=user_id,
    role="assistant",
    content=reply,
    scene=topic,
    topic=topic,  # 新增
)
```

---

## 七、个性化注入

### 7.1 第 5 区块设计

`MemoryContext.to_prompt_string()` 末尾追加【话题偏好】区块。

```python
# app/services/memory/context_builder.py

class MemoryContext:
    # ... 现有字段 ...
    topic_preference: dict | None = None  # 新增

    def to_prompt_string(self) -> str:
        parts = []
        # 现有 4 个区块
        if self.current_state: parts.append(f"【当前状态】\n{...}")
        if self.interaction: parts.append(f"【交互设定】\n{...}")
        if self.profile: parts.append(f"【个人档案】\n{...}")
        if self.deep_memory: parts.append(f"【深度记忆】\n{...}")

        # 新增:第 5 区块
        if self.topic_preference and self.topic_preference.get("topics"):
            parts.append(self._render_topic_block())

        return "\n\n".join(parts)

    def _render_topic_block(self) -> str:
        topics = self.topic_preference["topics"]
        total = self.topic_preference["total_likes"]
        lines = []
        for t in topics:
            desc_map = {
                "strong": "用户特别认可这一类",
                "medium": "用户经常被这一类打动",
                "weak": "用户偶尔对这一类感兴趣",
            }
            lines.append(
                f"- {t['topic']}({t['count']} 次,{t['last_days_ago']} 天前,"
                f"{t['intensity']}):{desc_map[t['intensity']]}"
            )
        topics_str = "\n".join(lines)

        if len(topics) == 1:
            t = topics[0]
            return (
                f"【话题偏好】\n"
                f"用户累计点赞 {total} 次,主导偏好:{t['topic']}。"
                f"{desc_map[t['intensity']]}。\n"
                f"回复时优先围绕此话题展开,可以呼应用户过往的表达。"
            )
        else:
            return (
                f"【话题偏好】\n"
                f"用户累计点赞 {total} 次,以下话题都有兴趣(按强度排序):\n"
                f"{topics_str}\n"
                f"回复时按强度优先展开,强偏好话题可以深入,弱偏好话题点到为止。"
            )
```

### 7.2 注入示例

**强主导**(单 topic,权重 ≥ 1.5x 第二名):
```
【话题偏好】
用户累计点赞 6 次,主导偏好:career(5 次,2 天前)。用户特别认可这一类。
回复时优先围绕此话题展开,可以呼应用户过往的表达。
```

**平局**(2-3 topic,权重接近):
```
【话题偏好】
用户累计点赞 6 次,以下话题都有兴趣(按强度排序):
- career(3 次,1 天前,medium):用户经常被这一类打动
- self_care(3 次,2 天前,medium):用户经常被这一类打动
回复时按强度优先展开,强偏好话题可以深入,弱偏好话题点到为止。
```

**冷启动**(总点赞 < 3):**整段不输出**。

### 7.3 注入 chat 还是 greeting

| 入口 | 注入? | 原因 |
|------|------|------|
| `chat()` 非流式 | ✓ | 用户在主动对话,topic 偏好是引导回复方向的强信号 |
| `chat_stream()` 流式 | ✓ | 同上,prompt 组装逻辑共用 |
| `generate_greeting()` | ✓ | 问候语也应结合用户偏好(比如偏好 career 的人,问候可以问"最近工作怎么样") |
| `quote_service.py` 随机夸夸 | ✗ | 随机夸夸本质是"出乎意料",强加偏好反而破坏随机性。**注:`quote_service` 及 `/api/quotes/*` 已在 2026-06 下线,小程序只保留 `/api/chat/greeting` 和 `/api/chat` 两个入口,本行仅作历史决策记录。** |
| TTS / 语音 | 待定 | TTS 模块未启用,后续接入时复用 chat 注入 |

---

## 八、流式接口架构(非流式 + 包装)

### 8.1 架构对比

| 方案 | 首 chunk | 完整文本 | JSON 可靠 | 实现复杂度 |
|------|---------|---------|----------|-----------|
| 真流式(LLM 层 stream) | 1.65s | 1.95s | 需客户端后处理 | 高 |
| **非流式 + SSE 包装** | **1.52s** | **1.76s** | **后端 100% 可靠** | **低** |

**结论**:采用"非流式 + 包装"。LLM 调用一次性拿完整 JSON,后端解析后切成 SSE chunk yield 给前端。

### 8.2 实现(`app/api/chat.py` 的 `chat_stream` 端点)

```python
async def event_generator() -> AsyncGenerator[dict[str, str], None]:
    try:
        # 0ms: 立即 yield thinking 事件
        yield {
            "event": "thinking",
            "data": json.dumps({"status": "processing"}, ensure_ascii=False),
        }

        # 构造完整 prompt(包含 memory + topic 偏好)
        full_prompt = f"{memory_context_str}\n\n用户说:{text_input}"
        # 温度 0.3, max_tokens 500
        raw = await service.provider.generate(
            prompt=full_prompt,
            system_prompt=prep.system_prompt,
            temperature=0.3,
            max_tokens=500,
        )

        # 解析 JSON
        reply, topic = parse_chat_response(raw)

        # 包装 yield:每 8 字一个 chunk,40ms 间隔(伪打字机效果)
        chunk_size = 8
        for i in range(0, len(reply), chunk_size):
            await asyncio.sleep(0.04)
            yield {
                "event": "chunk",
                "data": json.dumps({"content": reply[i:i+chunk_size]}, ensure_ascii=False),
            }

        # done 事件:scene 字段改为 topic
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "scene": topic,  # LLM 自报,不再是 chat_request.scene
                    "has_image": prep.has_image,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
            ),
        }

        # 异步:更新 memory,持久化 message(带 topic)
        asyncio.create_task(
            _update_session_after_chat_bg_with_topic(
                user_id, session_id, chat_request, reply, topic
            )
        )
    except Exception as e:
        logger.error(f"流式生成异常 | error={str(e)}")
        yield {"event": "error", "data": json.dumps({"message": "生成失败"}, ensure_ascii=False)}
```

### 8.3 前端契约升级

| 事件 | 旧 | 新 | 处理 |
|------|---|---|------|
| `thinking` | 不存在 | 立即发出 | 渐进增强,旧前端忽略;新前端可显示"AI 在组织语言" |
| `chunk` | 多次 | 多次(8字/40ms) | 不变 |
| `done.scene` | `chat_request.scene`(用户选的) | **LLM 自报 topic** | **值变了**,前端应信任并用于后续 favorite 反查 |
| `error` | 不变 | 不变 | - |

**小程序改动**:
- 旧前端:完全无感(忽略 thinking 事件,done.scene 字段值变了但不影响原有逻辑)
- 新前端(可选):处理 thinking 事件显示 loading 动画

### 8.4 多模态(图片)兼容性

`chat_stream` 的多模态分支(line 708-742)**已经是"非流式 + 一次性 yield"**。直接复用 JSON 改造:`_generate_multimodal` 内部 prompt 也加 JSON 输出要求,解析逻辑共用 `parse_chat_response`。

---

## 九、Topic 偏好聚合服务

### 9.1 服务位置

新建 `app/services/topic_preference_service.py`。

### 9.2 核心方法

```python
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
import json

HALF_LIFE_DAYS = 14
INJECTION_THRESHOLD_TOTAL = 3
CLEAR_LEAD_RATIO = 1.5
MAX_INJECTED_TOPICS = 3


class TopicPreferenceService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def on_favorite_added(self, user_id: str, topic: str) -> None:
        """收藏(点赞)时调用:更新计数 + 异步刷新 snapshot。"""
        async with self.session_factory() as db:
            # upsert 计数
            stmt = sqlite_insert(UserTopicPreference).values(
                user_id=user_id, topic=topic, like_count=1,
                first_liked_at=datetime.utcnow(), last_liked_at=datetime.utcnow(),
            ).on_conflict_do_update(
                index_elements=["user_id", "topic"],
                set_={
                    "like_count": UserTopicPreference.like_count + 1,
                    "last_liked_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)
            await db.commit()
        # 异步刷新 snapshot(不阻塞 favorite 响应)
        await self._refresh_snapshot(user_id)

    async def on_favorite_removed(self, user_id: str, topic: str) -> None:
        """取消收藏时调用:扣减计数(下限 0)。"""
        async with self.session_factory() as db:
            row = await db.execute(
                select(UserTopicPreference)
                .where(UserTopicPreference.user_id == user_id,
                       UserTopicPreference.topic == topic)
            )
            pref = row.scalar_one_or_none()
            if pref and pref.like_count > 0:
                pref.like_count -= 1
                await db.commit()
        await self._refresh_snapshot(user_id)

    async def compute_preference(self, user_id: str, now: datetime | None = None) -> dict | None:
        """计算用户当前 topic 偏好。返回注入 prompt 用的结构化数据,无偏好返回 None。
        包含完整的衰减权重、强度标签、平局处理。
        """
        now = now or datetime.utcnow()
        async with self.session_factory() as db:
            rows = (await db.execute(
                select(UserTopicPreference)
                .where(UserTopicPreference.user_id == user_id)
            )).scalars().all()

        if not rows:
            return None

        total_likes = sum(r.like_count for r in rows)
        if total_likes < INJECTION_THRESHOLD_TOTAL:
            return None

        # 1) 衰减权重
        scored = []
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
            if t["weight"] >= 5.0:
                t["intensity"] = "strong"
            elif t["weight"] >= 2.0:
                t["intensity"] = "medium"
            else:
                t["intensity"] = "weak"

        return {
            "topics": lead_topics,
            "total_likes": total_likes,
            "generated_at": now.isoformat(),
        }

    async def _refresh_snapshot(self, user_id: str) -> None:
        """聚合 top 3 话题,写入 UserProfile.topic_preference_snapshot(避免每次 chat 全表聚合)。"""
        pref = await self.compute_preference(user_id)
        snapshot = json.dumps(pref, ensure_ascii=False) if pref else None
        async with self.session_factory() as db:
            await db.execute(
                update(UserProfile)
                .where(UserProfile.user_id == user_id)
                .values(topic_preference_snapshot=snapshot)
            )
            await db.commit()

    async def get_snapshot(self, user_id: str) -> dict | None:
        """读 snapshot(chat / greeting 路径调用,避免每次重算)。"""
        async with self.session_factory() as db:
            row = (await db.execute(
                select(UserProfile.topic_preference_snapshot)
                .where(UserProfile.user_id == user_id)
            )).first()
        if not row or not row[0]:
            return None
        return json.loads(row[0])
```

### 9.3 注入入口(`memory_service.get_memory_summary`)

```python
# app/services/memory_service.py 中扩展 MemorySummary

class MemorySummary(BaseModel):
    # ... 现有字段 ...
    topic_preference: dict | None = None  # 新增

# get_memory_summary 内,读 snapshot
async def get_memory_summary(self, user_id: str) -> MemorySummary | None:
    # ... 现有逻辑 ...
    summary = MemorySummary(...)
    # 新增:读 topic snapshot
    snapshot = await topic_pref_service.get_snapshot(user_id)
    if snapshot:
        summary.topic_preference = snapshot
    return summary
```

`MemoryContext.from_memory_summary` 中填 `topic_preference`。

---

## 十、Favorite 流程改造

### 10.1 `FavoriteService.add_favorite` 改造

```python
# app/services/favorite_service.py

async def add_favorite(self, user_id: str, data: FavoriteCreate) -> Favorite:
    # 1) 决定 topic(三级兜底)
    topic = data.scene  # 1. 优先用请求里的 scene
    if topic not in ALLOWED_TOPICS:
        # 2. 从最近的同 content 消息里反查
        msg = (await self.db.execute(
            select(Message)
            .where(Message.role == "assistant", Message.content == data.content)
            .order_by(Message.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        topic = msg.topic if msg and msg.topic in ALLOWED_TOPICS else "general"
        # 3. 兜底 general

    # 2) 写 favorite
    favorite = Favorite(user_id=user_id, content=data.content, scene=topic)
    self.db.add(favorite)
    await self.db.commit()

    # 3) 触发偏好聚合(异步)
    asyncio.create_task(
        topic_pref_service.on_favorite_added(user_id, topic)
    )

    return favorite
```

### 10.2 `FavoriteService.remove_favorite` 改造

删除收藏时同步扣减 `like_count`(语义:"撤销一次认同")。

```python
async def remove_favorite(self, user_id: str, favorite_id: int) -> bool:
    fav = (await self.db.execute(
        select(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == user_id)
    )).scalar_one_or_none()
    if not fav:
        return False
    topic = fav.scene if fav.scene in ALLOWED_TOPICS else "general"
    await self.db.delete(fav)
    await self.db.commit()
    # 异步扣减
    asyncio.create_task(
        topic_pref_service.on_favorite_removed(user_id, topic)
    )
    return True
```

### 10.3 索引补充

```sql
-- favorite.content 加索引(反查 messages 用)
CREATE INDEX IF NOT EXISTS ix_favorites_content ON favorites (content);
-- 不需要,Message.content 已经有索引?查一下
-- 实际只查 Message.content WHERE role='assistant' AND content=? ORDER BY created_at DESC
-- 这个查询走 (role, content) 复合索引最佳
```

---

## 十一、问候语是否要 topic 注入

### 11.1 结论

**问候语也需要注入【话题偏好】**。理由:
- 问候语是"主动引导对话",知道用户偏好什么话题能直接用上
- 例:用户偏好 career,greeting 可以问"最近工作怎么样?"
- greeting 的 LLM 调用共用 memory_summary,改造零成本

### 11.2 `generate_greeting` 改造

```python
async def generate_greeting(
    self,
    user_type: str,
    memory_summary: MemorySummary | None = None,
    last_topic: str | None = None,
) -> str:
    # ... 现有 memory_lines 构造 ...
    memory_lines = []

    if memory_summary:
        # ... 现有 user_tags / milestones / prefer_scene 注入 ...

        # 新增:topic 偏好
        if memory_summary.topic_preference:
            tp = memory_summary.topic_preference
            if tp.get("topics"):
                top = tp["topics"][0]
                memory_lines.append(
                    f"用户主导话题偏好:{top['topic']}。"
                    f"问候时可自然围绕此话题展开。"
                )

    if last_topic:
        memory_lines.append(f"上次聊到:{last_topic}")

    memory_context = "\n".join(memory_lines) if memory_lines else ""
    # ... 后续 LLM 调用 ...
```

**注意**:greeting 仍输出纯文本(不输出 JSON),不需要解析 topic。

---

## 十二、前端契约与小程序改动

### 12.1 改动清单

| 路径 | 改动 | 必需? |
|------|------|--------|
| `app/static/test.html` | 加测试面板,展示 topic 偏好状态、模拟点赞 | 仅本地测试 |
| 真实小程序 | **0 改动** | 渐进兼容 |

### 12.2 真实小程序零改动可行性

| 原契约 | 新契约 | 影响 |
|--------|--------|------|
| `POST /api/favorites { content }` | `POST /api/favorites { content, scene }` | scene 可选,后端有兜底 |
| `done.scene` 字段 | 值变了(原=用户选,新=LLM 自报) | 前端如不使用该字段则无感 |
| 流式 chunk 事件 | 多了一个 thinking 事件 | 旧前端忽略,无影响 |

**结论**:小程序可以不改一行代码就上线新版本。**强烈推荐**先用这个状态观察 1 周数据,再决定要不要利用 thinking 事件做更好的 UX。

### 12.3 `test.html` 测试面板

加一个折叠区,展示:
- 当前 `topic_preference_snapshot`(实时刷新)
- 模拟点赞按钮(调 `/api/favorites` 测试聚合)
- 完整 prompt 预览(memory + topic 偏好 + 用户消息)

---

## 十三、Feature Flag 与回滚

### 13.1 Feature Flag

| Flag | 默认 | 作用 |
|------|------|------|
| `TOPIC_OUTPUT_ENABLED` | true | chat 是否走 JSON 输出 |
| `TOPIC_INJECT_ENABLED` | true | memory 是否注入第 5 区块 |
| `TOPIC_DECAY_DAYS` | 14 | 衰减半衰期,可调 |
| `STREAMING_THINKING_EVENT` | true | 是否 yield thinking 事件 |
| `STREAMING_FAKE_TYPING` | true | 是否伪打字机效果 |

通过环境变量控制,代码中读取。

### 13.2 回滚路径

| 故障 | 回滚 |
|------|------|
| LLM 不输出 JSON(服从率暴跌) | 关 `TOPIC_OUTPUT_ENABLED`,回到纯文本 + request.scene |
| Topic 注入污染 chat 质量 | 关 `TOPIC_INJECT_ENABLED`,退化为 4 区块 |
| Snapshot 计算有 bug | 删 `topic_preference_snapshot` 字段,降级为实时聚合 |
| Thinking 事件前端报错 | 关 `STREAMING_THINKING_EVENT` |
| 整张 `user_topic_preferences` 表污染 | TRUNCATE 表 + 清 snapshot 字段 |

每步可独立回滚,不破坏现有功能。

### 13.3 数据迁移

```sql
-- migrate_db.py 新增
def upgrade_topic_preference():
    # 1. messages.topic 字段
    op.add_column('messages', sa.Column('topic', sa.String(50), default='general'))
    op.create_index('ix_messages_user_topic', 'messages', ['user_id', 'topic'])
    # 2. user_topic_preferences 表
    op.create_table('user_topic_preferences', ...)
    # 3. user_profiles.topic_preference_snapshot
    op.add_column('user_profiles', sa.Column('topic_preference_snapshot', sa.Text(), nullable=True))
    # 4. 反查索引
    op.create_index('ix_messages_role_content', 'messages', ['role', 'content'])
```

**历史数据兼容**:
- 旧 `favorites.scene = 'general'` 数据**不迁移**(历史已失真,无意义)
- 旧 `messages.topic` 默认为 `'general'`
- 旧 `user_profiles.topic_preference_snapshot` 为 NULL,新点赞后自动生成

---

## 十四、验证标准

### 14.1 单元测试(必须全过)

| 测试 | 验证内容 |
|------|---------|
| `test_parse_chat_response` | 各种 LLM 输出格式(JSON / 带围栏 / 嵌入文本 / 解析失败)→ 正确返回 (reply, topic) |
| `test_topic_validation` | 12 边界内/外 topic 字符串 → 返回对应 topic 或 general |
| `test_decay_weight` | 给定 last_liked_at 距今 X 天,weight 公式正确 |
| `test_tie_breaking` | 1.5x 门槛 / 最多 3 个 topic / 冷启动不注入 |
| `test_on_favorite_added` | 计数 +1 + snapshot 刷新 |
| `test_on_favorite_removed` | 计数 -1,下限 0 + snapshot 刷新 |

### 14.2 集成测试

| 测试 | 验证 |
|------|------|
| `test_chat_json_compliance` | 50 条不同输入,LLM 输出 95%+ 可解析 JSON |
| `test_topic_accuracy` | 25 条标注样本,LLM 85%+ topic 准确 |
| `test_stream_wrap_ux` | 首 chunk 延迟 < 2s,完整文本 < 2.5s |
| `test_favorite_topc_backfill` | 调用 `/api/favorites` 不传 scene,后端从 Message.topic 反查成功 |

### 14.3 端到端验证

| 验证项 | 怎么做 | 成功标准 |
|--------|-------|---------|
| LLM JSON 服从率 | 调 chat 接口 50 次 | ≥ 95% 响应可解析为 {reply, topic} |
| 真实数据修复 | 上线后看 `favorites.scene` 分布 | 不再 100% 是 'general' |
| 冷启动无污染 | 新用户跑 chat 10 次无点赞 | memory prompt 中**无**【话题偏好】区块 |
| 衰减生效 | 14 天前的 like 比新 like 权重低 | 单元测试 + 手工验证 |
| 流式时序 | 慢网(500kbps)模拟 | 首 chunk < 3s,完整 < 4s |
| 小程序契约不变 | 小程序代码 grep 改动 | 0 行改动 |

### 14.4 监控指标(上线后看)

| 指标 | 目标 |
|------|------|
| `parse_chat_response` 成功率 | ≥ 95% |
| `favorites.scene` 多样性 | ≥ 5 个不同 topic 都有数据 |
| `topic_preference_snapshot` 填充率 | ≥ 30% 用户在 1 周内有 snapshot |
| Chat 满意度(隐式:点赞率) | 不下降 |

---

## 十五、落地路线(5 步,3-4 天)

### Step 1:Schema 迁移(0.5 天)

```bash
python scripts/migrate_db.py upgrade_topic_preference
```

涉及:
- `migrations/versions/` 写新脚本
- ORM 模型加字段(`Message.topic` / `UserProfile.topic_preference_snapshot` / 新表 `UserTopicPreference`)

### Step 2:Prompt 改造(0.5 天)

涉及:
- `templates.toml` 改 5 个 `[scenes.*]` + 3 个 `[multimodal.*]` 任务定义
- 验证热重载可用,无需重启

### Step 3:解析服务 + Chat 改造(1 天)

涉及:
- `app/services/chat_service.py` 加 `parse_chat_response` 和 `_extract_first_balanced_json`
- `chat()` 端点和 `chat_stream()` 端点都用解析
- `chat_stream()` 改成"非流式 + 包装"架构
- 温度从 0.7/0.8 改 0.3,max_tokens 改 500

### Step 4:Topic 偏好服务(1 天)

涉及:
- 新建 `app/services/topic_preference_service.py`
- `FavoriteService.add/remove_favorite` 加 topic 兜底和聚合触发
- `memory_service.get_memory_summary` 读 snapshot
- `MemoryContext.to_prompt_string` 加第 5 区块
- `generate_greeting` 注入 topic 偏好

### Step 5:测试与上线(1 天)

涉及:
- 写单元测试 + 集成测试
- 端到端手工测试(test.html 模拟完整流程)
- 灰度:先开 10% 流量,看监控
- 全量

### 关键回滚点

- Step 2 后 LLM 不输出 JSON:关 `TOPIC_OUTPUT_ENABLED` flag
- Step 4 后 chat 质量下降:关 `TOPIC_INJECT_ENABLED` flag
- Step 3 后流式时序变慢:关 `STREAMING_FAKE_TYPING` 即可省 0.24s

---

## 十六、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM JSON 服从率低于 95% | 中 | 用户看到 JSON 语法字符 | 解析器三级兜底 + 强制 prompt + max_tokens 500 |
| Topic 边界不清导致误分类 | 高 | 用户画像不准 | 已用测试验证 85-88% 准确,可接受 |
| snapshot 字段膨胀 | 低 | DB 占用大 | JSON 限制 < 1KB,定时清理长期不活跃用户 |
| 流式 UX 改变用户感知 | 中 | 用户觉得"AI 慢了" | thinking 事件 + 伪打字机缓解,前 1 周监控反馈 |
| 历史 favorites 数据全污染 | 确定 | 统计失真 | **不修复**,新数据从改造日起重新累积 |
| 小程序兼容性问题 | 低 | 崩溃 | done.scene 字段值变化不影响功能,thinking 事件渐进增强 |
| 12 个 topic 边界争议持续 | 中 | LLM 持续误分类 | 收集误分类样本,定期调定义;新增/合并 topic 是产品决策 |

---

## 十七、决策记录(重要!)

| 决策 | 选择 | 否决项 | 理由 |
|------|------|--------|------|
| topic 是用户意图还是内容 | **内容**(LLM 自报) | 用户意图 | 用户在 general 聊工作,需要 self_care 角度回应 |
| topic 固定还是自由 | **固定 12** | 自由生成 | 聚合、注入、A/B 都依赖固定列表 |
| LLM 输出格式 | **JSON + topic 定义** | 纯文本 + 后处理分类 | 测试验证 JSON 100% 服从 |
| 收藏=点赞? | **是(语义升级)** | 新增点赞按钮 | 前端 0 改动;有需要再拆 |
| 流式接口实现 | **非流式 + SSE 包装** | LLM 真流式 | 快 0.19s,JSON 100% 可靠,实现简单 |
| 温度 | **0.3** | 0.7/0.8 | 稳定性优先,准确率仅降 3% |
| max_tokens | **500** | 300 | 300 会截断 JSON |
| 衰减半衰期 | **14 天** | 7/30 天 | 平衡"近期偏好"和"长期累积" |
| 平局门槛 | **1.5x** | 1.2/2.0x | 经验值,可调 |
| 冷启动门槛 | **总点赞 ≥ 3** | 1/5/10 | 1 太少,5+ 启动太慢 |
| rebuild 定义 | **已陷入长期低落且无明显事件触发** | 处境艰难需要陪伴 | 解决 v1 rebuild/self_care/healing 边界混淆 |
| like 计数是否衰减时扣减 | **基于 `like_count`,不基于权重** | 动态计算 | 简化存储,衰减时算权重即可 |
| snapshot 存储位置 | **UserProfile JSON 字段** | 独立表 | 一次读,无需 join |
| 取消收藏扣减? | **扣减** | 不扣减 | 语义一致,数据更准 |

---

## 十八、未来扩展(不在本次范围)

1. **I am 模式**:`UserTopic` 显式关注话题,作为 topic 偏好的补充信号
2. **TTS 集成**:`feat-tts-emotion` 分支合并后,greeting 走语音
3. **Topic 维度 A/B 测试**:按 topic 切流,验证不同 topic 偏好的商业价值
4. **跨用户 topic 推荐**:"和你类似的用户也喜欢 career",社交化路径
5. **自动 topic 扩展**:LLM 提议新 topic,产品审核后加入 enum

---

## 附录 A:测试脚本

`scripts/tmp_test/test_json_v2.py`(JSON 服从 + topic 准确)
`scripts/tmp_test/test_stream_wrap.py`(流式时序对比 + 温度稳定性)

两个脚本可保留作为回归测试,放在 `scripts/` 下,加 README 说明。

## 附录 B:相关文件清单

| 文件 | 改动 |
|------|------|
| `app/prompts/templates.toml` | 5 scenes + 3 multimodal 任务定义追加 JSON 要求 |
| `app/services/chat_service.py` | 加 `parse_chat_response`,`chat()` 用 |
| `app/api/chat.py` | `chat()` 和 `chat_stream()` 改造;新增 `thinking` 事件 |
| `app/services/topic_preference_service.py` | 新建 |
| `app/services/favorite_service.py` | `add/remove_favorite` 加 topic 兜底和聚合 |
| `app/services/memory_service.py` | `get_memory_summary` 读 snapshot |
| `app/services/memory/context_builder.py` | `to_prompt_string` 加第 5 区块 |
| `app/models/models.py` | `Message.topic` / 新表 `UserTopicPreference` / `UserProfile.topic_preference_snapshot` |
| `scripts/migrate_db.py` | 加迁移函数 |
| `app/static/test.html` | 加测试面板 |
| `docs/greeting-topic-personalization-design-v2.md` | 本文档 |

---

## 十一、主动声明话题(2026-06-02 增量)

### 11.1 背景

v2 的 topic 偏好完全来自"被动观察"(用户收藏了哪些 AI 回复)。这有两个问题:
- **冷启动慢**:新用户需要至少 3 次收藏才能看到 prompt 注入
- **方向被动**:用户即使想"我最近只想要 career 方向的夸夸",也只能等被动信号自然累积

小程序侧有"主动选择关注方向"的交互需求,所以新增一条"主动声明"通道,与被动信号**合并**计算。

### 11.2 数据流

```
POST /api/memory/topic-interests
Body: { "topics": ["career", "love", "healing"] }   (最多 5 个)
                    │
                    ▼
        ┌────────────────────────┐
        │ 过滤 / 去重 / 上限 5    │
        │ 排除 general 与非法值    │
        └────────────────────────┘
                    │
                    ▼
UserProfile.declared_topics (TEXT, JSON 数组)
                    │
                    ▼
TopicPreferenceService.set_declared_topics
                    │ 1) upsert UserProfile
                    │ 2) refresh_snapshot → 合并写 snapshot
                    ▼
topic_preference_snapshot (JSON,新增 declared_topics 字段)
```

### 11.3 合并算法

主动声明的 topic 在 `compute_preference` 里与被动权重**叠加**:

```
effective_weight(topic) = decay_weight(topic) + DECLARED_TOPIC_BOOST(2.0) [if declared]
```

| 场景 | passive weight | boost | effective | intensity | 备注 |
|------|---------------|-------|-----------|-----------|------|
| 0 收藏,声明 career | 0 | +2.0 | **2.0** | medium | 纯声明也能过冷启动 |
| 3 收藏(0d)career,声明 career | 3.0 | +2.0 | **5.0** | strong | 主动叠加 |
| 3 收藏(0d)career,未声明 career | 3.0 | 0 | **3.0** | medium | 跟旧版一致 |

**冷启动门控升级**:
- 旧版:`total_likes < 3` → 不返回
- 新版:`declared_topics 为空 AND total_likes < 3` → 不返回
- 即:有主动声明时,直接通过冷启动

**主动声明不影响被动数据**:
- `UserTopicPreference.like_count` 永远由"加/减收藏"维护,声明不增减
- 取消声明某个 topic(从列表移除)→ `effective_weight` 减去 2.0,但 `UserTopicPreference` 行不动
- 历史收藏数据**完整保留**,这是用户实打实的点赞历史,跟"是否还想看这个方向"是不同维度

### 11.4 快照结构变化

```diff
{
  "topics": [
-    { "topic": "career", "weight": 3.0, "count": 3, "last_days_ago": 0, "intensity": "medium" }
+    { "topic": "career", "weight": 3.0, "count": 3, "last_days_ago": 0, "intensity": "medium", "declared": false }
  ],
  "total_likes": 3,
+  "declared_topics": [],
  "generated_at": "..."
}
```

纯声明的 topic:
```json
{ "topic": "healing", "weight": 2.0, "count": 0, "last_days_ago": -1, "intensity": "medium", "declared": true }
```
- `count=0` + `last_days_ago=-1` 表示从未收藏,纯靠声明上榜
- `declared=true` 标记来源,供 5 区块 prompt 区分显示

### 11.5 5 区块 Prompt 适配

| 场景 | 旧版 | 新版 |
|------|------|------|
| 0 收藏,3 声明 | (无 5 区块) | `基于用户主动声明` + `career(medium, 主动声明)` |
| 3 收藏 + 1 声明同 topic | `基于 3 次收藏` + `career(medium, weight=3.0)` | `基于 3 次收藏` + `career(medium, weight=3.0)` (count=3 不显示"主动声明") |
| 3 收藏 + 1 声明**新** topic | `基于 3 次收藏` + `career(medium, weight=3.0)` | `基于 3 次收藏` + `career(medium, weight=3.0)` + `love(medium, 主动声明)` |
| 0 收藏,0 声明 | (无 5 区块) | (无 5 区块) |

判定规则:
- `count > 0` → 显示 `weight=X.X`
- `count == 0 && declared` → 显示 `主动声明` (避免出现 "weight=2.0 来自 0 收藏" 的矛盾信号)
- `total_likes > 0` → 显示"基于 X 次收藏"
- `total_likes == 0 && has_declared` → 显示"基于用户主动声明"

### 11.6 接口定义

```
PUT  /api/memory/topic-interests
Body: { "topics": ["career", "love"] }
Resp: { "code": 0, "data": { "declared_topics": ["career", "love"] } }

GET  /api/memory/topic-interests
Resp: { "code": 0, "data": { "declared_topics": ["career", "love"] } }
```

行为:
- 覆盖式写入(整个数组替换,不会"追加")
- 非法 topic(`非 ALLOWED_TOPICS` / `general` / `>5 个`)被静默过滤
- 重复值去重,保留插入顺序
- 写入后立即刷新 `topic_preference_snapshot`,下一次 chat / greeting 立即生效

### 11.7 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 存储位置 | `UserProfile.declared_topics` JSON 列 | 与 `topic_preference_snapshot` / `user_tags` 等保持一致,无 JOIN |
| 字段名 | `declared_topics`(而非 `prefer_topics` / `interested_topics`) | 与"主动声明"语义对齐;`prefer` 已被 UserProfile.prefer_scene 占用 |
| 合并权重 | 固定 2.0 | 低于 strong 阈值(5.0),允许被动信号继续超越主动声明;等于 medium 阈值 |
| 接口路径 | `PUT /api/memory/topic-interests` | 与现有 `/api/memory/*` 用户偏好接口保持前缀一致 |
| 取消声明 | 不动 UserTopicPreference | "撤销关注" ≠ "撤销点赞",历史是用户的真实表达 |
| 上限 | 5 个 | 12 个 topic 中筛掉 general 后 11 个,5 个够覆盖多方向用户;再大边际收益低 |

### 11.8 新增/修改文件

| 文件 | 改动 |
|------|------|
| `app/models/models.py` | `UserProfile` 新增 `declared_topics` 列 |
| `app/models/schemas.py` | 新增 `TopicInterestUpdate` / `TopicInterestResponse` |
| `app/services/topic_preference_service.py` | `set_declared_topics()` + `compute_preference` 合并 + 常量 `DECLARED_TOPIC_BOOST=2.0` |
| `app/api/memory.py` | `PUT/GET /api/memory/topic-interests` |
| `app/services/memory/context_builder.py` | 5 区块适配 declared-only 场景 |
| `app/models/database.py` | `init_db` 加 `_ensure_column` 兜底 ALTER TABLE |
| `tests/test_topic_preference_service.py` | 新增 6 个单元测试 (declared merge / undeclare / filter) |
| `scripts/tmp_test/test_topic_declared_e2e.py` | 新增 E2E 测试 |
| `docs/greeting-topic-personalization-design-v2.md` | 新增第十一章 |
