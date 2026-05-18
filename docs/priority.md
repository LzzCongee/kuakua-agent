# 功能确定性与优先级排序

> 基于 `implementation-plan.md` 分析，区分确定/不确定功能，排优先级。
>
> **版本**：v1.0
> **日期**：2026-05-15

---

## 一、功能分类总览

| 分类 | 数量 | 说明 |
|------|------|------|
| **A. 已完成** | 8 | 现有稳定实现，无需改动 |
| **B. 确定新增** | 4 | 需求明确，实现路径清晰，可立即开发 |
| **C. 待定/重构** | 3 | 需求模糊或需要较大架构调整，暂缓 |
| **D. 长期规划** | 2 | 未来方向，当前不实现 |

---

## 二、A. 已完成（无需改动）

| 功能 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 三层记忆基础结构 | `app/services/memory_service.py` | ✅ 稳定 | Session/UserProfile/Milestone CRUD |
| 记忆汇总注入 | `MemoryService.get_memory_summary()` | ✅ 稳定 | MemorySummary 组装 |
| 记忆格式化为 Prompt | `MemoryService.format_memory_for_prompt()` | ✅ 稳定 | 字符串拼接（待优化） |
| REST API | `app/api/memory.py` | ✅ 稳定 | /api/memory/* |
| 结构化日志 + trace_id | `app/core/logging.py` | ✅ 稳定 | RequestLoggingMiddleware |
| A/B 测试框架 | `app/services/ab_test_service.py` | ✅ 稳定 | 随机/场景分流 |
| 工厂模式多数据库 | `app/services/memory_factory.py` | ✅ 稳定 | SQL/CloudBase 切换 |
| MCPClient 基础连接 | `app/core/mcp_client.py` | ✅ 稳定 | SSE 长连接，add/search 已通 |

---

## 三、B. 确定新增（可立即开发）

按优先级排序：

### B-1: ContextBuilder（类型安全上下文）

**优先级**：P0 | **工时**：0.5天 | **风险**：低

**需求**：将 `format_memory_for_prompt()` 的字符串拼接替换为 Pydantic 模型。

**确定理由**：
- 现有 `format_memory_for_prompt()` 逻辑清晰，只需迁移
- Pydantic 模型可直接复用现有字段
- 可测试性强，IDE 支持好

**文件**：`app/services/memory/context_builder.py`（新）

```python
class MemoryContext(BaseModel):
    prefer_scene: Optional[str] = None
    prefer_style: Optional[str] = None
    user_tags: list[str] = Field(default_factory=list, max_length=5)
    avoid_words: list[str] = Field(default_factory=list)
    last_emotion: Optional[str] = None
    milestones: list[str] = Field(default_factory=list, max_length=3)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    semantic_memories: list[SemanticMemory] = Field(default_factory=list)
    
    def to_prompt_string(self) -> str: ...
```

---

### B-2: EmotionDetector（文本情绪检测）

**优先级**：P0 | **工时**：0.5天 | **风险**：低

**需求**：为文字输入提供规则引擎情绪检测，补充 LLM 提取的不足。

**确定理由**：
- PRD 定义 6 种情绪，规则模式覆盖核心场景
- 语音/图片走 EmotionAnalyzer（LLM），文字走规则（低成本）
- 规则匹配 <1ms，可做兜底

**文件**：`app/services/emotion/detector.py`（新）

---

### B-3: update_memory 调用（情绪趋势稳定后触发）

**优先级**：P1 | **工时**：0.5天 | **风险**：低

**需求**：当同一情绪连续出现 3+ 次，更新 Supermemory 偏好记忆。

**确定理由**：
- 现有 `chat.py:592-600` 已有提取逻辑，只需追加更新逻辑
- 情绪历史用 Redis List 存储，实现简单
- 不在每次对话时调用，避免语义记忆抖动

**文件**：`app/api/chat.py`（修改）

```python
# 在 _update_session_after_chat 末尾追加
emotion_history_key = f"emotion_history_{user_id}"
emotion_history = await redis.lrange(emotion_history_key, 0, -1) or []
current_emotion = extraction_result.emotion if extraction_result else None
if current_emotion and current_emotion != "neutral":
    emotion_history.append(current_emotion)
    await redis.ltrim(emotion_history_key, -5, -1)
    if len(emotion_history) >= 3 and len(set(emotion_history[-3:])) == 1:
        await mcp_client.call("update_memory", ...)
```

---

### B-4: EmotionAnalyzer（语音/图片情绪分析）

**优先级**：P1 | **工时**：1天 | **风险**：中

**需求**：对接豆包 4.0 Lite，提供语音/图片输入的情绪分析。

**确定理由**：
- PRD 明确要求"豆包 4.0 Lite 负责情绪识别 + ASR"
- MCPClient 已支持，可复用 SSE 长连接
- 输出格式固定（JSON: text/emotion/intensity）

**文件**：`app/services/emotion/analyzer.py`（新）

---

## 四、C. 待定/重构（暂缓）

### C-1: 评测体系

**优先级**：P2 | **风险**：高

**问题**：
- PRD 要求"Prompt 效果评测机制"，但无具体指标
- 如何量化"夸得准/夸得真"？
- A/B 测试需要流量，成本高

**建议**：MVP 先不做，收集用户反馈后再设计。

---

### C-2: 情绪自适应响应 adapter

**优先级**：P2 | **风险**：中

**问题**：
- PRD 定义了 6 种情绪的 Icon 状态，但 adapter 如何影响生成？
- 情绪 → 生成风格的映射关系未定义
- 可能在 ChatService._inject_memory() 中已覆盖

**建议**：先观察 EmotionDetector + LLM 提取是否足够，再决定是否需要专门 adapter。

---

### C-3: 观测层指标监控

**优先级**：P3 | **风险**：低

**问题**：
- PRD 要求"结构化日志 + 关键指标"，日志已有
- 但指标（Counter/Histogram）需要额外服务（如 Prometheus）
- 当前阶段日志足够

**建议**：上线稳定后再说。

---

## 五、D. 长期规划（未来方向）

### D-1: 记忆权重衰减策略

- 早期记忆 vs 近期记忆区分
- 需要 Supermemory 层面支持，当前 MVP 不需要

### D-2: 语义记忆去重/合并

- mem0 自动去重，MVP 阶段不依赖
- 当前 SQL 结构足够

---

## 六、优先级排序总结

| 优先级 | 功能 | 类型 | 工时 | 状态 |
|--------|------|------|------|------|
| P0 | ContextBuilder | 确定新增 | 0.5天 | 待开发 |
| P0 | EmotionDetector | 确定新增 | 0.5天 | 待开发 |
| P1 | update_memory 调用 | 确定新增 | 0.5天 | 待开发 |
| P1 | EmotionAnalyzer | 确定新增 | 1天 | 待开发 |
| P2 | 评测体系 | 待定 | - | 暂缓 |
| P2 | 情绪 adapter | 待定 | - | 暂缓 |
| P3 | 观测层指标 | 待定 | - | 暂缓 |

---

## 七、开发顺序建议

```
Week 1 (2天)
├── B-1: ContextBuilder（0.5天）
├── B-2: EmotionDetector（0.5天）
└── B-3: update_memory 调用（0.5天）
    └── 预留 buffer（0.5天）

Week 2 (1天)
└── B-4: EmotionAnalyzer（1天）
    └── 语音/图片输入联调

暂不排期
├── C-1: 评测体系
├── C-2: 情绪 adapter
└── C-3: 观测层指标
```

---

## 八、文档关联

| 文档 | 说明 |
|------|------|
| [实现计划](./implementation-plan.md) | 原始需求和方案 |
| [优先级排序](./priority.md) | 本文档，功能确定性和优先级 |
| [需求文档](./元气夸夸搭子%20语音情绪优先版%20需求文档.md) | PRD |