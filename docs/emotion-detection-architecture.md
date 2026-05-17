# 情绪检测架构设计文档

> 创建时间：2026-05-17
> 状态：已评审待实现

## 一、背景与目标

### 1.1 问题背景

当前 `app/services/emotion/` 目录下的实现存在以下问题：

1. **职责混淆**：`detector`（规则引擎）和 `analyzer`（LLM）的命名容易造成困惑，不清楚业务边界
2. **多模态检测不完整**：middleware 只处理 text 和 audio，缺少 image 检测
3. **音频输入格式不匹配**：analyzer 使用 base64 传给 `generate_multimodal`，但 Doubao-Seed-2.0-mini 验证的是 URL 方式
4. **缺乏降级策略**：没有完善的降级机制和日志记录
5. **融合策略缺失**：多输入同时存在时如何融合没有明确方案

### 1.2 设计目标

1. **清晰职责分离**：按输入类型（text/audio/image）分离检测器
2. **多模态融合**：文本为主，音图辅助，支持权重配置
3. **完善的降级机制**：超时、限流、API错误等情况的自动降级
4. **可配置的Prompt管理**：支持文件版本追踪
5. **灵活的模型选择**：文本优先规则引擎，降级用 DeepSeek；音频/图片用 Doubao-Seed-2.0-mini

---

## 二、架构设计

### 2.1 整体架构

```
app/
├── config.py                     # 新增 ai_emotion 配置组
├── prompts/
│   ├── templates.toml            # 现有（夸夸模板）
│   └── emotion/                  # 情绪检测专用prompt
│       └── templates.toml
├── providers/
│   └── volcengine.py             # 火山引擎Provider（支持音频输入）
└── services/
    └── emotion/
        ├── __init__.py
        ├── service.py            # 统一入口 EmotionService
        ├── fusion.py             # 多模态融合策略
        ├── models.py             # 数据模型定义
        ├── detectors/            # 按输入类型分离
        │   ├── base.py           # 基类
        │   ├── text.py           # 文本检测器
        │   ├── audio.py           # 音频检测器
        │   └── image.py          # 图片检测器
        └── fallback.py           # 降级策略管理
```

### 2.2 现有架构评估

| 现有组件 | 文件 | 评估 |
|----------|------|------|
| EmotionMiddleware | middleware.py | 协调调度层，可简化为路由 |
| EmotionDetector | detector.py | 规则引擎，保留（text专用） |
| EmotionAnalyzer | analyzer.py | LLM分析，需重构 |

**现有优势**：
- `templates.toml` 模式可复用
- `ai_vision` 配置已支持多模态，可扩展
- Provider 抽象层已完成

---

## 三、输入格式最佳实践

### 3.1 音频/图片格式对比

| 格式 | 适用场景 | 限制 | 推荐 |
|------|----------|------|------|
| **URL** | 公开可访问资源、文件较小 | 需要公网可访问 | 通用场景 |
| **Base64** | 私有/本地文件、即时短音频、隐私内容 | 增加请求体积，约33% overhead | **即时对话场景** |

**本项目决策：即时对话的夸夸类助手场景采用 Base64**

原因：
1. 音频通常较短（几秒~十几秒），Base64 体积可控
2. 无需先上传再获取URL，减少一次 HTTP 往返
3. 用户隐私音频不经过额外存储中转
4. 即时性要求高，降低总响应时间

### 3.2 火山引擎 Doubao-Seed-2.0-mini 支持情况

**音频输入格式（已验证）**：

**URL方式**：
```python
{
    "model": "doubao-seed-2-0-mini-260428",
    "messages": [{
        "role": "user",
        "content": [
            {
                "type": "input_audio",
                "input_audio": {
                    "url": "https://example.com/audio.mp3",
                    "format": "mp3"
                }
            },
            {
                "type": "text",
                "text": "请分析音频中的情绪"
            }
        ]
    }]
}
```

**Base64方式**：
```python
{
    "model": "doubao-seed-2-0-mini-260428",
    "messages": [{
        "role": "user",
        "content": [
            {
                "type": "input_audio",
                "input_audio": {
                    "data": "<base64编码的音频>",
                    "format": "mp3"
                }
            },
            {
                "type": "text",
                "text": "请简短分析音频中的情绪"
            }
        ]
    }]
}
```

**支持的音频格式**：`mp3`, `wav`, `m4a`, `mp4`, `mov`, `ogg`

**关键发现**：
- Responses API 不支持 `input_audio` 字段
- 必须使用 Chat Completions API (`/api/v3/chat/completions`)
- 音频解析返回包含 `audio_tokens` 字段

### 3.3 模型输出格式控制

**Doubao-Seed-2.0-mini 支持通过 Prompt 控制输出格式**：

| 输出模式 | Prompt 示例 | 返回格式 |
|----------|-------------|----------|
| 单一主情绪 | `请分析以下内容的情绪，输出最主要的情绪类型` | `{"emotion": "happy"}` |
| 多情绪带权重 | `请输出所有可能的情绪及对应置信度，格式为JSON` | `{"emotions": {"happy": 0.7, "excited": 0.2, "calm": 0.1}}` |

**统一 Prompt 设计**：
```python
# 所有模态共用同一个 Prompt，模型自动联合理解
prompt = """请分析以下内容的情绪，输出所有可能的情绪及对应置信度。
要求：
1. 情绪类型：happy/excited/exhausted/sad/frustrated/calm
2. 置信度：0-1之间的浮点数，所有置信度之和为1
3. 输出格式为JSON：{"emotions": {"情绪": 置信度, ...}}"""

content = [
    {"type": "text", "text": prompt},
    # 可选：图片、音频、视频输入
    {"type": "image_url", "image_url": {"url": "..."}},
    {"type": "input_audio", "input_audio": {"data": "...", "format": "mp3"}},
]
```

**优势**：
1. 一个 Prompt 通用处理所有模态输入
2. 模型原生支持多情绪权重输出，无需后处理融合
3. 可通过 few-shot 示例进一步稳定输出格式

### 3.4 本项目方案

**即时对话场景：前端 → Base64 编码 → 直接发送**

流程：
```
用户录音 → 前端Base64编码 → API请求体直接附带 → 火山引擎API处理
```

好处：
1. 减少上传中转步骤（省去一次HTTP请求）
2. 体积可控（短音频Base64约几十KB）
3. 隐私保护（音频不经过额外存储）

---

## 四、融合策略设计

### 4.1 多模态融合机制

**核心变化**：Doubao-Seed-2.0-mini 支持多模态联合推理，可同时接收 text、audio、image、video 输入，模型自动融合并输出统一的情绪权重。

**融合策略**：

| 输入组合 | 处理方式 | 说明 |
|----------|----------|------|
| 单模态（仅文本/音频/图片） | 直接调用模型，返回多情绪权重 | 模型原生输出 |
| 多模态（文本+音频+图片等） | 同时发送给模型，联合推理 | 模型自动融合，输出统一结果 |
| 多模态 + 文本检测器降级 | 规则引擎结果与模型结果加权融合 | 降级链路下的二次融合 |

### 4.2 融合权重配置（仅降级链路使用）

```yaml
emotion:
  fusion:
    weights:
      text: 0.6    # 文本检测器结果权重
      audio: 0.2    # 音频模型结果权重
      image: 0.2   # 图片模型结果权重
```

**说明**：仅在文本检测器降级到规则引擎时需要手动融合。正常链路中，多模态输入直接由模型联合推理，无需额外融合。

### 4.3 融合算法（降级链路专用）

```python
def fuse_llm_with_detector(
    llm_result: dict[str, float],     # 模型输出的情绪权重
    detector_result: EmotionResult,     # 规则引擎结果
    weights: dict[str, float]
) -> EmotionResult:
    """
    降级链路融合：模型结果 + 规则引擎结果

    用于文本检测降级到规则引擎的场景。
    正常链路不需要此融合。
    """
    scores = defaultdict(float)

    # 模型结果（正常权重）
    for emotion, weight in llm_result.items():
        scores[emotion] += weight * weights.get("audio", 0.4) + weight * weights.get("image", 0.4)

    # 规则引擎结果（文本权重）
    scores[detector_result.emotion] += detector_result.intensity * weights["text"]

    # 归一化
    total = sum(scores.values())
    if total > 0:
        scores = {k: v/total for k, v in scores.items()}

    primary = max(scores.items(), key=lambda x: x[1])

    return EmotionResult(
        primary_emotion=primary[0],
        primary_intensity=primary[1],
        details=MultimodalEmotionDetails(
            raw_scores=dict(scores),
            fusion_method="llm_plus_detector"
        )
    )
```

### 4.4 返回格式设计

```python
@dataclass
class EmotionResult:
    # 最终结果
    primary_emotion: str           # "happy"
    primary_intensity: float       # 0.85

    # 多情绪权重（模型原生输出）
    emotion_weights: dict[str, float] | None = None  # {"happy": 0.7, "excited": 0.2}

    # 详细信息（可选，用于调试）
    details: MultimodalEmotionDetails | None

@dataclass
class MultimodalEmotionDetails:
    # 各模态输入是否参与推理
    text_used: bool = False
    audio_used: bool = False
    image_used: bool = False

    # 融合信息
    fusion_method: str = "llm_joint"  # "llm_joint" | "llm_plus_detector"
    raw_scores: dict[str, float]     # 归一化前的分数
```

**说明**：模型原生输出多情绪权重（`emotion_weights`），业务可按需使用单一主情绪或多情绪组合。

---

## 五、降级策略设计

### 5.1 降级触发条件

| 触发条件 | 处理方式 | 日志级别 |
|----------|----------|----------|
| **Timeout** | 降级到备选模型 | WARNING |
| **Rate Limit (429)** | 降级 + 记录 + 触发熔断 | ERROR |
| **API Error (5xx)** | 降级到备选模型 | ERROR |
| **Invalid Response** | 降级到规则引擎 | WARNING |
| **Model Unavailable** | 尝试备选模型 | ERROR |

### 5.2 降级记录模型

```python
@dataclass
class FallbackRecord:
    """降级事件记录"""
    trigger: str              # "timeout" | "rate_limit" | "api_error" | "invalid_response"
    detail: str              # 具体原因
    original_model: str      # 原计划使用的模型
    fallback_model: str      # 降级到的模型
    timestamp: datetime
    recovered: bool           # 是否已恢复

    def to_log(self) -> str:
        return (
            f"[EMOTION_FALLBACK] trigger={self.trigger} | "
            f"from={self.original_model} to={self.fallback_model} | "
            f"detail={self.detail} | recovered={self.recovered}"
        )
```

### 5.3 降级执行示例

```python
class EmotionFallbackManager:
    async def detect_with_fallback(
        self,
        detector: BaseDetector,
        primary_model: str,
        fallback_model: str,
        *args, **kwargs
    ) -> EmotionResult:
        try:
            return await detector.detect(*args, model=primary_model, **kwargs)

        except asyncio.TimeoutError:
            self._log_fallback(
                trigger="timeout",
                detail=f"模型 {primary_model} 调用超时({TIMEOUT}s)",
                primary=primary_model,
                fallback=fallback_model
            )
            return await detector.detect(*args, model=fallback_model, **kwargs)

        except RateLimitError:
            self._log_fallback(
                trigger="rate_limit",
                detail=f"模型 {primary_model} 触发限流",
                primary=primary_model,
                fallback=fallback_model
            )
            # 额外：记录熔断状态
            self.circuit_breaker.record_failure(primary_model)
            return await detector.detect(*args, model=fallback_model, **kwargs)

        except APIError as e:
            self._log_fallback(
                trigger="api_error",
                detail=f"API错误: {e.message}",
                primary=primary_model,
                fallback=fallback_model
            )
            return await detector.detect(*args, model=fallback_model, **kwargs)
```

### 5.4 模型降级链

```
文本检测：
  Doubao-Seed-2.0-mini → DeepSeek-V3 → 规则引擎（兜底）

音频检测：
  Doubao-Seed-2.0-mini → （失败则返回默认 calm, 0.5）

图片检测：
  Doubao-Seed-2.0-mini → （失败则返回默认 calm, 0.5）
```

---

## 六、配置设计

### 6.1 config.py 新增配置

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # 情绪检测配置
    ai_emotion: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="doubao-seed-2-0-mini-260428",
            timeout=30.0,
        ),
        description="情绪检测模型配置（多模态）",
    )

    # 情绪检测专用：文本模型（降级用）
    ai_emotion_text: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="deepseek-ai/DeepSeek-V4-Flash",
            timeout=10.0,
        ),
        description="文本情绪检测模型（降级用）",
    )

    # 融合权重
    emotion_fusion_weights: dict[str, float] = Field(
        default={"text": 0.6, "audio": 0.2, "image": 0.2},
        description="多模态融合权重",
    )
```

### 6.2 Prompt模板位置

```
app/prompts/emotion/
└── templates.toml
```

```toml
[text]
system = "你是一个情绪分析助手，严格输出JSON。"
user = "分析这段文本的情绪：{text}\n\n情绪类型：happy/excited/exhausted/sad/frustrated/calm"

[audio]
system = "你是一个音频情绪分析助手，严格输出JSON。"
user = "分析这段音频的情绪，输出：{\"text\":\"ASR转写\",\"emotion\":\"情绪类型\",\"intensity\":0.0-1.0}"

[image]
system = "你是一个图片情绪分析助手，严格输出JSON。"
user = "分析图片中人物的情绪，输出：{\"text\":\"图片描述\",\"emotion\":\"情绪类型\",\"intensity\":0.0-1.0}"
```

---

## 七、实现计划

### 阶段一：基础架构（预计2小时）

1. [ ] 创建 `app/services/emotion/models.py` - 数据模型
2. [ ] 创建 `app/services/emotion/fusion.py` - 融合策略
3. [ ] 创建 `app/services/emotion/fallback.py` - 降级管理
4. [ ] 创建 `app/services/emotion/detectors/base.py` - 基类

### 阶段二：检测器实现（预计3小时）

1. [ ] 创建 `app/services/emotion/detectors/text.py` - 文本检测器
2. [ ] 创建 `app/services/emotion/detectors/audio.py` - 音频检测器
3. [ ] 创建 `app/services/emotion/detectors/image.py` - 图片检测器
4. [ ] 创建 `app/prompts/emotion/templates.toml` - Prompt模板

### 阶段三：服务集成（预计2小时）

1. [ ] 创建 `app/services/emotion/service.py` - 统一入口
2. [ ] 更新 `app/config.py` - 新增 ai_emotion 配置
3. [ ] 更新 `app/services/emotion/__init__.py` - 导出新接口
4. [ ] 更新 middleware 调用新服务

### 阶段四：测试与优化（预计1小时）

1. [ ] 单元测试
2. [ ] 融合策略调优
3. [ ] 降级日志验证

---

## 八、关键技术决策

### 8.1 为什么保留 detector 和 analyzer 的区分？

当前区分是基于**实现方式不同**（规则 vs LLM），不是业务目的不同：

- `detector`：文本 → 规则引擎（<1ms，低延迟）
- `analyzer`：音频/图片 → LLM（多模态能力）

**建议**：重命名以澄清职责：
- `TextRuleDetector`（规则引擎）
- `MultimodalAnalyzer`（LLM多模态）

### 8.2 为什么不用 Responses API？

经验证，Responses API 不支持 `input_audio` 字段。必须使用 Chat Completions API。

### 8.3 为什么文本检测还要降级到DeepSeek？

Doubao-Seed-2.0-mini 虽然支持文本输入，但：
1. 规则引擎更快（<1ms vs LLM 500ms+）
2. 文本情绪简单，规则足够
3. 节省 Doubao-Seed-2.0-mini 的 API 调用配额

---

## 九、附录

### 9.1 验证过的API调用格式

**Chat Completions API 音频输入**：
```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seed-2-0-mini-260428",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "input_audio", "input_audio": {"url": "https://...", "format": "mp3"}},
        {"type": "text", "text": "请简短分析音频中的情绪"}
      ]
    }]
  }'
```

### 9.2 参考资料

- [火山引擎 ARK API 文档](https://www.volcengine.com/docs/82379/1494384)
- 现有 `app/prompts/templates.py` - Prompt管理参考
- 现有 `app/config.py` - 配置管理参考