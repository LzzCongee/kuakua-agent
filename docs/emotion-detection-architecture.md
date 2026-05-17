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

### 5.5 重试机制设计

**业界最佳实践（参考 OpenAI SDK）**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 最大重试次数 | 2-3 次 | 总共 3-4 次尝试 |
| 初始退避间隔 | 0.5s | 首次重试等待 |
| 最大退避间隔 | 8-16s | 防止过长等待 |
| 退避策略 | 指数退避 + 随机抖动 | `min(0.5 * 2^attempt, max_delay)` |
| 触发条件 | HTTP 408、429、500+ | 不处理用户取消 |

**重试触发判断**：

```python
def should_retry(status_code: int, retry_after: str | None) -> bool:
    """判断是否应该重试"""
    # 显式拒绝
    if status_code in (400, 401, 403, 404, 422):
        return False
    # 服务端错误，可重试
    if status_code >= 500:
        return True
    # 限流，尊重 Retry-After
    if status_code == 429:
        return True
    return False
```

**共用重试模块设计**：

建议提取为共用模块 `app/core/retry.py`：

```python
"""
通用重试装饰器模块

基于指数退避算法，支持 httpx 请求的自动重试。
"""

import asyncio
import random
from functools import wraps
from typing import TypeVar, ParamSpec
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec('P')
T = TypeVar('T')

DEFAULT_MAX_RETRIES = 2
DEFAULT_INITIAL_DELAY = 0.5
DEFAULT_MAX_DELAY = 16.0


class RetryConfig:
    """重试配置"""
    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.retry_on_status = retry_on_status


def with_retry(config: RetryConfig | None = None):
    """
    通用重试装饰器

    使用方式：
        @with_retry(RetryConfig(max_retries=3))
        async def call_api():
            ...
    """
    cfg = config or RetryConfig()

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(cfg.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code not in cfg.retry_on_status:
                        raise
                    last_exception = e
                    delay = min(cfg.initial_delay * (2 ** attempt), cfg.max_delay)
                    # 加随机抖动（25%）
                    delay = delay * (1 + random.random() * 0.25)

                    logger.warning(
                        f"[RETRY] attempt={attempt + 1}/{cfg.max_retries + 1} | "
                        f"status={e.response.status_code} | "
                        f"delay={delay:.2f}s | "
                        f"func={func.__name__}"
                    )
                    if attempt < cfg.max_retries:
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[RETRY] 全部重试失败 | func={func.__name__}")

                except (asyncio.TimeoutError, httpx.TimeoutException) as e:
                    last_exception = e
                    delay = min(cfg.initial_delay * (2 ** attempt), cfg.max_delay)
                    logger.warning(
                        f"[RETRY] attempt={attempt + 1}/{cfg.max_retries + 1} | "
                        f"timeout | delay={delay:.2f}s"
                    )
                    if attempt < cfg.max_retries:
                        await asyncio.sleep(delay)

            # 所有重试都失败，抛出最后一次异常
            raise last_exception

        return wrapper
    return decorator


# 预定义重试配置
RETRY_DEFAULT = RetryConfig()
RETRY_LONG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=32.0)
RETRY_QUICK = RetryConfig(max_retries=1, initial_delay=0.25, max_delay=4.0)
```

**情绪检测中的重试配置**：

```python
# 情绪检测模型调用
emotion_retry_config = RetryConfig(
    max_retries=2,
    initial_delay=0.5,
    max_delay=8.0,
    retry_on_status=(429, 500, 502, 503, 504),
)

# 文本检测器降级
text_detector_retry = RetryConfig(
    max_retries=1,
    initial_delay=0.25,
    max_delay=4.0,
)
```

**重试与降级的区别**：

| 机制 | 触发条件 | 行为 | 关系 |
|------|----------|------|------|
| 重试 | 429/5xx/超时 | 同一模型重试 | 降级前最后一道保障 |
| 降级 | 重试全部失败 | 切换到备选模型 | 重试失败后的最终保障 |

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

### 6.2 Prompt模板设计

**统一 Prompt 策略**：所有模态（text/audio/image/video）共用同一个任务指令 Prompt，模型自动联合理解。

```
app/prompts/emotion/
└── templates.toml
```

```toml
[emotion_analysis]
system = "你是一个情绪分析助手，擅长从多种输入中准确识别情绪。"
user = """请分析以下内容的情绪，输出所有可能的情绪及对应的置信度。

要求：
1. 情绪类型：happy/excited/exhausted/sad/frustrated/calm
2. 置信度：0-1之间的浮点数，所有情绪的置信度之和为1
3. 输出格式为JSON：{"emotions": {"情绪类型": 置信度, ...}}
4. 如无法确定，默认为 neutral，置信度为0.5

Few-shot 示例：
输入：今天考试考砸了，心情很低落
输出：{"emotions": {"sad": 0.6, "exhausted": 0.3, "calm": 0.1}}

输入：收到offer了！太开心了！
输出：{"emotions": {"happy": 0.7, "excited": 0.3}}

请分析：{input_text}"""
```

**Prompt 约束说明**：
- 情绪类型固定为 6 种，便于归一化处理
- 要求输出 JSON 并给出 few-shot 示例，稳定输出格式
- 降级兜底：无法确定时默认 `neutral, 0.5`

### 6.3 JSON 解析降级策略

模型输出可能因格式偏差导致解析失败，需完备的降级提取策略：

```python
async def parse_emotion_response(raw_output: str) -> dict[str, float]:
    """
    JSON 解析降级策略
    """
    try:
        # 1. 直接解析
        data = json.loads(raw_output)
        if "emotions" in data:
            return data["emotions"]
        if "emotion" in data and "confidence" in data:
            return {data["emotion"]: data["confidence"]}
    except json.JSONDecodeError:
        pass

    try:
        # 2. 尝试提取 JSON 代码块
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if "emotions" in data:
                return data["emotions"]
    except (json.JSONDecodeError, AttributeError):
        pass

    try:
        # 3. 穷举式 key 提取
        patterns = [
            r'"(\w+)":\s*([\d.]+)',           # "happy": 0.7
            r'(\w+)\s*[:：]\s*([\d.]+)',       # happy: 0.7
        ]
        for pattern in patterns:
            matches = re.findall(pattern, raw_output)
            if matches:
                result = {}
                for emotion, score in matches:
                    if emotion in EMOTION_TYPES:
                        result[emotion] = float(score)
                if result:
                    # 归一化
                    total = sum(result.values())
                    return {k: v/total for k, v in result.items()}
    except Exception:
        pass

    # 4. 降级兜底：返回默认情绪
    logger.warning(f"JSON解析全部失败，降级为默认情绪 | raw={raw_output[:100]}")
    return {"neutral": 1.0}

EMOTION_TYPES = {"happy", "excited", "exhausted", "sad", "frustrated", "calm", "neutral"}
```

**降级层级**：
1. 直接解析 JSON
2. 提取 JSON 代码块
3. 穷举式正则 key 提取
4. 降级兜底返回 `{"neutral": 1.0}`

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

**架构设计参考**：
- [火山引擎 ARK API 文档](https://www.volcengine.com/docs/82379/1494384)
- 现有 `app/prompts/templates.py` - Prompt管理参考
- 现有 `app/config.py` - 配置管理参考

**重试机制参考**：
- [OpenAI Python SDK 源码 - 重试逻辑](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py)
- [httpx Timeout 文档](https://www.python-httpx.org/advanced/timeout/)
- [Python tenacity 库](https://github.com/jd/tenacity) - 通用重试库
- [LangChain 超时配置](https://python.langchain.com/docs/concepts/chat_models/#timeout)
- [Dify LLM 节点超时](https://docs.dify.ai/guides/workflow/node/llm)