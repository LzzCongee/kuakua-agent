# 夸夸 Agent Prompt 个性化改进方案

基于心理学研究，改进夸夸 Agent 的人格和回复多样性。

---

## 一、问题诊断

### 1.1 当前系统状态

- 5 个固定场景（general / career / beauty / love / daily），每个场景有固定风格的 system prompt
- 所有回复都是**同质化的夸赞语气**，缺乏棱角和惊喜感
- 没有幽默/搞笑/意外的机制
- 用户标签只有 `prefer_scene`、`prefer_style`，缺少**性格偏好**维度

### 1.2 用户体验问题

1. **缺乏记忆点**：用户记不住 AI 的回复，因为太"标准"了
2. **无差异化**：不同用户收到几乎相同的回复体验
3. **无法留住"不想被夸"的用户**：有些用户只是随便发发，但当前的 system prompt 强制要求"给夸"
4. **无趣味性**：只有暖，没有笑

---

## 二、心理学研究支撑

详见 [psychology-research.md](./psychology-research.md)，核心结论：

| 研究 | 结论 | 产品设计映射 |
|------|------|--------------|
| Incongruity Theory | 意外和反差产生幽默 | 回复要有反差感 |
| Broaden-and-Build | 笑比夸更能留存 | 增加随机搞笑模式 |
| Self-Determination | 归属感来自被理解+被逗乐 | 不能只夸，要有趣 |
| Dweck 成长型思维 | 夸努力不夸天赋 | SBI 框架 |
| 具体性原则 | 越具体越真诚 | 锚定细节 |
| 情绪验证优先 | 先共情再肯定 | 先承认感受再夸 |
| 差异心理学 | 不同人需不同方式 | 增加人格变体 |

---

## 三、改进方案

### 3.1 人格变体系统

**思路**：同一个"夸夸朋友"的身份，可以有不同的**人格棱角**。

#### 3.1.1 人格变体定义

在 `templates.toml` 中新增 `[personalities]` 配置：

```toml
[personalities.default]
role = "你是一个真诚、温暖的朋友，善于发现别人身上被忽略的闪光点。"
tone = "温暖、直接、真诚"
trigger_tags = []

[personalities.witty]
role = "你是一个嘴贱但内心温暖的朋友。说话像吐槽，其实每句都在夸人。偶尔毒舌，但从不刻薄。"
tone = "调侃但不伤人，偶尔自嘲"
trigger_tags = ["吐槽", "毒舌", "嘴贱"]

[personalities.chill]
role = "你是一个见过很多事的淡定朋友。话不多，但每句都戳中要害。慵懒但精准。"
tone = "慵懒、精准、不废话"
trigger_tags = ["高冷", "淡定", "话少"]

[personalities.enthusiastic]
role = "你是一个热血中二的朋友。说话夸张但真诚，偶尔戏精上身，让人忍不住笑。"
tone = "热血、中二、夸张但真诚"
trigger_tags = ["戏精", "热血", "中二"]
```

#### 3.1.2 人格切换逻辑

在 `MemoryContext` 中增加 `personality_prefer` 字段：

```python
class MemoryContext(BaseModel):
    # ... 已有字段 ...
    personality_prefer: str = Field(default="default", description="喜欢的人格类型")
    humor_taste: str = Field(default=None, description="喜欢的幽默类型")
    tone_shift: bool = Field(default=False, description="是否接受语气转变")
```

人格切换规则：
- 用户有 `personality_witty` 标签 → 使用 witty 人格
- 用户有 `personality_chill` 标签 → 使用 chill 人格
- 新用户默认 default人格
- 通过 AB Test 验证不同人格的留存效果

#### 3.1.3 Prompt 组装变更

修改 `chat_service.py` 中的 `_inject_memory`，在记忆注入时同时注入人格：

```python
def _inject_personality(self, system_prompt: str, memory: MemorySummary) -> str:
    personality = memory.personality_prefer or "default"
    if personality == "default":
        return system_prompt

    personality_data = get_personality(personality)  # 从 templates.toml 读取
    return f"{system_prompt}\n\n【人格模式】\n{personality_data.role}"
```

---

### 3.2 随机模式触发机制

**思路**：当用户 query **不是明显求夸**时（只是在随便聊聊），使用随机回复来留住用户。

#### 3.2.1 触发条件判断

```python
def _should_use_random_mode(text: str, memory: MemoryContext) -> bool:
    """
    判断是否使用随机模式

    触发条件：
    1. 用户 query 中没有明显的求夸意图（如"求夸"、"让我开心一下"）
    2. 用户没有设置 prefer_scene 为特定场景
    3. 用户 tone_shift=True，或者用户有"接受随机"的标签
    """
    # 明显的求夸关键词
    obvious_praise_triggers = ["求夸", "夸夸我", "让我开心", "夸一下", "开心一下"]

    for trigger in obvious_praise_triggers:
        if trigger in text:
            return False  # 明显求夸 → 不随机

    # 检查用户偏好
    if memory.tone_shift is False:
        return False  # 用户明确不想随机

    # 30% 概率触发（可配置）
    import random
    return random.random() < 0.3
```

#### 3.2.2 随机模式分类

```toml
# 在 templates.toml 中新增

[random_modes]
category_distribution = [
    {type = "witty_teasing", weight = 0.35, desc = "调侃式回应（看似吐槽，实则肯定）"},
    {type = "insightful", weight = 0.25, desc = "洞察式反问（让用户自己回想）"},
    {type = "meme", weight = 0.20, desc = "梗/段子（结合时事或流行语）"},
    {type = "ironic_warm", weight = 0.20, desc = "故意反差（用户以为你会夸，但你偏不）"},
]

[random_modes.prompts.witty_teasing]
template = "你是一个嘴贱的朋友。有人发了「{user_input}」，你要用调侃的方式回应，看似吐槽实则夸人。30字以内。"
trigger_hint = "用户自嘲时、用户明显在装时"

[random_modes.prompts.insightful]
template = "你是一个洞察力很强的朋友。有人发了「{user_input}」，你要说一句让人愣住的洞察，不是夸但让人想继续聊。20字以内。"
trigger_hint = "用户分享经历时"

[random_modes.prompts.meme]
template = "你是一个紧跟潮流的朋友。有人发了「{user_input}」，你要用当前流行的梗或段子来回应，结合时事。30字以内。"
trigger_hint = "任何非求夸的场景"

[random_modes.prompts.ironic_warm]
template = "你是一个故意反差的朋友。有人发了「{user_input}」，你偏不按他们预期的方式回应，出乎意料但暖心。25字以内。"
trigger_hint = "用户期望被夸时"
```

#### 3.2.3 随机模式实现

```python
async def _generate_random_mode(
    self,
    text: str,
    personality: str,
    humor_taste: str | None
) -> str:
    """生成随机模式的回复"""
    import random

    # 根据 humor_taste 调整分布
    distribution = [
        ("witty_teasing", 0.35),
        ("insightful", 0.25),
        ("meme", 0.20),
        ("ironic_warm", 0.20),
    ]

    if humor_taste == "chill":
        distribution = [
            ("witty_teasing", 0.15),
            ("insightful", 0.35),  # 喜欢深度
            ("meme", 0.20),
            ("ironic_warm", 0.30),
        ]

    # 按权重随机选择
    rand = random.random()
    cumulative = 0.0
    selected_type = "ironic_warm"
    for mode_type, weight in distribution:
        cumulative += weight
        if rand <= cumulative:
            selected_type = mode_type
            break

    # 获取对应 prompt 并渲染
    mode_prompt = get_random_mode_prompt(selected_type, text, personality)
    return await self.provider.generate(mode_prompt)
```

---

### 3.3 MemoryContext 扩展

在 `app/services/memory/context_builder.py` 中扩展 MemoryContext：

```python
class MemoryContext(BaseModel):
    # === 已有字段 ===
    prefer_scene: Optional[str] = Field(default=None)
    prefer_style: Optional[str] = Field(default=None)
    user_tags: list[str] = Field(default_factory=list, max_length=5)
    avoid_words: list[str] = Field(default_factory=list, max_length=10)
    last_emotion: Optional[str] = Field(default=None)
    milestones: list[str] = Field(default_factory=list, max_length=3)
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    semantic_memories: list[SemanticMemory] = Field(default_factory=list, max_length=3)

    # === 新增字段 ===
    personality_prefer: str = Field(
        default="default",
        description="喜欢的人格类型：default/witty/chill/enthusiastic"
    )
    humor_taste: str = Field(
        default=None,
        description="喜欢的幽默类型：teasing/insightful/meme/ironic"
    )
    tone_shift: bool = Field(
        default=False,
        description="是否接受语气转变（有时正经有时搞笑）"
    )
    interaction_count: int = Field(
        default=0,
        description="累计交互次数，用于判断用户是否活跃"
    )
```

---

### 3.4 Prompt 组装逻辑改进

修改 `chat_service.py` 中的 prompt 组装：

```python
def _build_system_prompt(
    self,
    base_prompt: str,
    memory: MemorySummary,
    personality: str,
    scene: str
) -> str:
    """组装完整的 system prompt"""

    parts = [base_prompt]

    # 1. 人格注入
    if personality != "default":
        personality_data = get_personality(personality)
        parts.append(f"\n\n【人格模式】\n{personality_data.role}")

    # 2. 记忆上下文注入
    context = MemoryContext.from_memory_summary(memory)
    memory_str = context.to_prompt_string()
    if memory_str:
        parts.append(f"\n\n{memory_str}")

    # 3. 场景注意事项
    scene_notes = get_scene_notes(scene)
    if scene_notes:
        parts.append(f"\n\n【场景注意】\n{scene_notes}")

    return "\n".join(parts)
```

---

## 四、实施计划

### 4.1 优先级与工作量

| 优先级 | 改动 | 复杂度 | 效果 | 依赖 |
|--------|------|--------|------|------|
| **P0** | templates.toml 增加人格变体配置 | 低 | 快速见效 | 无 |
| **P0** | templates.toml 增加随机模式 prompt | 低 | 快速见效 | 无 |
| **P1** | MemoryContext 增加 personality_prefer / humor_taste / tone_shift 字段 | 低 | 个性化基础 | 无 |
| **P1** | chat_service.py 增加 `_should_use_random_mode` 判断逻辑 | 中 | 核心机制 | P0 |
| **P1** | chat_service.py 增加 `_generate_random_mode` 方法 | 中 | 核心机制 | P0 |
| **P2** | chat_service.py 实现人格切换逻辑 | 中 | 差异化 | P0+P1 |
| **P2** | AB Test 系统验证人格变体效果 | 高 | 数据驱动 | P1完成 |

### 4.2 具体任务分解

#### Task 1: templates.toml 人格变体配置

文件：`app/prompts/templates.toml`

```toml
# 在文件末尾新增

# -------------------- 人格变体 --------------------
[personalities.default]
role = "你是一个真诚、温暖的朋友，善于发现别人身上被忽略的闪光点。"
tone = "温暖、直接、真诚"
trigger_tags = []

[personalities.witty]
role = "你是一个嘴贱但内心温暖的朋友。说话像吐槽，其实每句都在夸人。偶尔毒舌，但从不刻薄。"
tone = "调侃但不伤人，偶尔自嘲"
trigger_tags = ["吐槽", "嘴贱"]

[personalities.chill]
role = "你是一个见过很多事的淡定朋友。话不多，但每句都戳中要害。慵懒但精准。"
tone = "慵懒、精准、不废话"
trigger_tags = ["高冷", "淡定"]

[personalities.enthusiastic]
role = "你是一个热血中二的朋友。说话夸张但真诚，偶尔戏精上身，让人忍不住笑。"
tone = "热血、中二、夸张但真诚"
trigger_tags = ["戏精", "热血"]

# -------------------- 随机模式 --------------------
[random_modes]
enabled = true
trigger_probability = 0.3

[random_modes.categories.witty_teasing]
weight = 0.35
desc = "调侃式回应（看似吐槽，实则肯定）"

[random_modes.categories.insightful]
weight = 0.25
desc = "洞察式反问"

[random_modes.categories.meme]
weight = 0.20
desc = "梗/段子"

[random_modes.categories.ironic_warm]
weight = 0.20
desc = "故意反差暖心"
```

#### Task 2: templates.py 读取人格和随机模式

文件：`app/prompts/templates.py`

```python
def get_personality(personality: str) -> dict:
    """获取人格变体配置"""
    personalities = _data.get("personalities", {})
    return personalities.get(personality, personalities.get("default"))

def get_random_mode_prompt(mode_type: str, user_input: str, personality: str) -> str:
    """生成随机模式的 prompt"""
    random_modes = _data.get("random_modes", {})
    categories = random_modes.get("categories", {})

    if mode_type not in categories:
        mode_type = "ironic_warm"

    # 根据人格调整语气
    personality_data = get_personality(personality)
    tone = personality_data.get("tone", "")

    return f"【语气：{tone}】\n用户说：{user_input}\n你的回应："
```

#### Task 3: MemoryContext 扩展

文件：`app/services/memory/context_builder.py`

```python
class MemoryContext(BaseModel):
    # ... 已有字段保持 ...

    # === 新增字段 ===
    personality_prefer: str = Field(default="default")
    humor_taste: str = Field(default=None)
    tone_shift: bool = Field(default=False)
    interaction_count: int = Field(default=0)
```

#### Task 4: chat_service.py 实现随机模式

文件：`app/services/chat_service.py`

```python
async def chat(self, request: ChatRequest, ...) -> ChatResponse:
    # ... 现有逻辑 ...

    # 新增：判断是否使用随机模式
    if self._should_use_random_mode(request.text, memory_summary):
        content = await self._generate_random_mode(
            request.text,
            memory_summary.personality_prefer or "default",
            memory_summary.humor_taste
        )
        return ChatResponse(content=content, scene=request.scene, ...)

    # ... 现有逻辑 ...
```

---

## 五、预期效果

### 5.1 量化指标（AB Test）

- **3 日留存率**：预期提升 5-10%
- **平均对话轮次**：预期提升 0.5-1 轮
- **用户满意度**：通过 side-by-side 评测

### 5.2 定性效果

- 用户能记住 AI 的「人格」—— 有人会专门回来找「那个毒舌的朋友」
- 解决「不想被夸」用户的需求 —— 随便聊聊也能有收获
- 差异化体验 —— 不同用户有不同风格，增加产品趣味性

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 人格变体导致回复不稳定 | 中 | 高 | AB Test，灰度发布，监控 NPS |
| 随机模式触发过于频繁 | 低 | 中 | trigger_probability 可配置，默认为 0.3 |
| 毒舌人格过度冒犯用户 | 低 | 高 | 限制 witty 人格仅对明确选择的用户启用 |
| 搞笑回复质量参差 | 中 | 低 | 通过评测反馈持续优化 prompt |
---

## 六、实施记录（2026-05-31 更新）

### 6.1 已完成代码改动 ✅

| 改动 | 文件 |
|------|------|
| templates.toml 增加 [personalities] 和 [random_modes] 配置 | app/prompts/templates.toml |
| templates.py 增加 get_personality()、get_random_mode_config()、get_random_mode_prompt() | app/prompts/templates.py |
| MemoryContext 增加 personality_prefer/humor_taste/tone_shift/interaction_count 字段 | app/services/memory/context_builder.py |
| MemorySummary 增加 personality_prefer/humor_taste/tone_shift 字段 | app/models/schemas.py |
| chat_service.py 增加 _should_use_random_mode() 和 _generate_random_mode() 方法 | app/services/chat_service.py |
| chat_service.py 实现人格注入 _inject_personality() 方法 | app/services/chat_service.py |
| chat_service.py chat() 方法支持人格注入和随机模式触发 | app/services/chat_service.py |
| api/chat.py _inject_memory_to_prompt() 支持人格注入 | app/api/chat.py |
| to_prompt_string() 输出人格偏好和幽默偏好信息 | app/services/memory/context_builder.py |

### 6.2 验证状态

- Python 语法验证：通过 ✅
- Ruff lint 检查：全部通过 ✅（本次修改的文件）
- 函数导入/调用测试：通过 ✅

---

## 七、Prompt 前缀 Cache 优化

### 7.1 现有结构分析

当前每次请求的 prompt 组装：
```
system_prompt = 基础模板（来自 get_chat_prompt(input_type)）
             + 人格注入（来自 get_personality(personality)，仅非 default 时）
             + 记忆上下文（来自 MemoryContext.to_prompt_string()）
```

### 7.2 Cache 优化策略

**问题**：相同人格 + 相同输入类型的请求，可以共享基础 prompt 前缀。

**优化方案**：在 chat_service.py 中增加模块级缓存：

```python
from functools import lru_cache

# 模块级缓存：input_type + personality -> base_system_prompt
_BASE_PROMPT_CACHE: dict[tuple[str, str], str] = {}

def _get_cached_base_prompt(input_type: str, personality: str) -> str:
    """获取带人格的基础 system prompt（可缓存）"""
    cache_key = (input_type, personality)
    if cache_key not in _BASE_PROMPT_CACHE:
        base = get_chat_prompt(input_type)["system"]
        if personality != "default":
            personality_data = get_personality(personality)
            tone = personality_data.get("tone", "")
            role = personality_data.get("role", "")
            if role:
                base = f"{base}\n\n【人格模式：{tone}】\n{role}"
        _BASE_PROMPT_CACHE[cache_key] = base
    return _BASE_PROMPT_CACHE[cache_key]
```

**预期效果**：
- 减少重复的 prompt 拼接
- AI 模型更容易识别一致的模式
- 提升推理缓存命中率（如果有上游 KV 缓存）

---

## 八、待完成

### 8.1 P1 后续任务

- [ ] **AB Test 人格变体验证**：创建 AB 测试，对比 default vs witty vs chill 的留存和对话轮次
- [ ] PersonalityResolver：从 user_tags 自动推断人格偏好（如有"吐槽"标签自动切换 witty）
- [ ] 根据使用数据，调整随机模式的 trigger_probability

### 8.2 P2 任务

- [ ] 根据用户反馈，优化各随机模式的 prompt 模板
- [ ] 完善 AB Test 监控面板，追踪各人格的 NPS 和留存率
