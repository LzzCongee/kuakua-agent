# 元气夸夸搭子 · 情绪优先版 实现计划方案

> 本文档基于「元气夸夸搭子 语音情绪优先版 需求文档」和现有架构实现，提供完整的工程实现方案。
> 遵循最佳工程实践：模块化、可测试、可观测、可维护。
>
> **版本**：v1.0
> **日期**：2026-05-15

---

## 一、需求理解与当前架构审阅

### 1.1 核心需求摘要（来自 PRD）

| 需求 | 说明 | 优先级 |
|------|------|--------|
| 语音情绪识别 | 识别用户语音的情绪（happy/excited/exhausted/sad/frustrated/calm） | P0 |
| 任务拆分架构 | 豆包 4.0 Lite（情绪+ASR）+ 豆包 3.5（生成），成本降 18 倍 | P0 |
| 情绪自适应夸夸 | 根据情绪状态调整夸夸风格和内容 | P0 |
| 三层记忆管理 | 短期会话 + 用户偏好 + 高光里程碑，对接 Supermemory MCP | P1 |
| 动态 Icon 联动 | 前端根据情绪切换 Icon 状态和背景色 | P1 |

### 1.2 当前架构优点

```
✅ 已实现：
- 三层记忆基础结构（Session/UserProfile/Milestone）
- 记忆汇总注入 Prompt（MemorySummary）
- 完整的 REST API（/api/memory/*）
- 结构化日志 + trace_id
- A/B 测试框架
- 工厂模式支持多数据库（SQL/CloudBase）

✅ PRD 新增：
- 情绪识别 + ASR 统一接口（豆包 4.0 Lite）
- 夸夸生成接口（豆包 3.5）
- Supermemory MCP 集成
- 收藏管理（增加 emotion 字段）
```

### 1.3 当前架构缺口

```
❌ 待完善：
1. 情绪检测服务：缺乏结构化情绪识别，只有简单的关键词匹配
2. 记忆闭环不完整：采集→存储有，检索→更新→遗忘→评估缺失
3. Supermemory MCP 集成：add/search 已对接，update_memory 未调用
4. 观测层薄弱：只有日志，缺少指标监控
5. 评测体系未建立：缺乏 Prompt 效果评测机制
6. 上下文构建分散：ChatService 直接注入记忆，缺乏统一管理
7. 类型安全不足：记忆上下文使用字符串拼接，无 Pydantic 校验
```

### 1.4 当前项目已有实现（vs 计划新增模块）

| 已有模块 | 文件 | 说明 |
|---------|------|------|
| `MemoryService` | `app/services/memory_service.py` | 单文件多方法，含三层记忆 CRUD |
| `MemoryExtractor` | `app/services/memory_extractor.py` | 混合提取引擎（关键词+LLM） |
| `MCPClient` | `app/core/mcp_client.py` | SSE 长连接，支持 add/search |
| `format_memory_for_prompt` | `MemoryService` 内 | 字符串拼接方式 |

| 计划新增（本次改进） | 说明 |
|---------------------|------|
| `MemoryManager` | 统一入口，协调三层记忆 |
| `ContextBuilder` | 类型安全上下文构建，Pydantic 校验 |
| `update_memory` 调用 | Supermemory 偏好更新 |

---

### 1.5 三个关键问题解答

#### Q1: 记忆闭环是否已结合当前项目实际？

**已结合**，不是另起炉灶。当前实现基础：

| 现有能力 | 对应闭环环节 | 状态 |
|---------|-------------|------|
| `MemoryService._get_semantic_memories()` | 检索 | ✅ 已有 |
| `MemoryService.save_chat_to_supermemory()` | 存储 | ✅ 已有 |
| `MemoryExtractor._extract_by_keywords()` | 编码/提取 | ✅ 已有 |
| `MemoryService.add_milestone()` | 里程碑存储 | ✅ 已有 |

**缺失环节**：
- **遗忘**：短期会话 2 小时 TTL 有清理逻辑，但偏好/里程碑无 TTL 评估
- **更新**：Supermemory 的 `update_memory` 未调用，用户偏好变了 AI 不知道
- **评估**：Prompt 效果无量化评测机制

**改进策略**：复用现有 `MemoryService`，在其基础上新增 `MemoryManager` 统一编排，`ContextBuilder` 替换字符串拼接。

---

#### Q2: Supermemory `update_memory` 在哪里调用？

**调用时机**：用户偏好发生变化时。

具体场景：

| 场景 | 调用位置 | 说明 |
|------|---------|------|
| 用户收藏夸夸 | `favorite_service.py` 的 `add` 方法后 | 用户主动认可，偏好更新最可靠 |
| 用户多次选择同一场景 | `chat.py` 累计场景计数超阈值后 | 行为比口述更可信 |
| 用户明确表达 avoid_words | `MemoryExtractor` 提取到 `avoid_words` 时 | 显式反馈 |

**推荐优先实现（最小闭环）**：

```python
# favorite_service.py - 收藏时更新偏好
async def add(self, user_id: str, content: str, emotion: str):
    # 原有逻辑...
    favorite = await self.create(...)
    
    # ★ 新增：用户收藏时，更新 Supermemory 偏好记忆
    if favorite:
        await self.mcp.call(
            "update_memory",
            user_id=user_id,
            updates={
                "preferred_emotion_style": emotion,
                "last_favorite_at": datetime.now().isoformat(),
            }
        )
    return favorite
```

**不要在每次对话时调用 update_memory**——对话内容变化频繁，频繁更新会导致语义记忆抖动。

---

#### Q3: ContextBuilder 做什么？有无类型检查？

**ContextBuilder 职责**：将多层记忆聚合为结构化对象，供 Prompt 调用。替换 `format_memory_for_prompt()` 的字符串拼接。

**类型安全设计**：

```python
# app/services/memory/context_builder.py

from pydantic import BaseModel, Field
from typing import Optional

class SemanticMemory(BaseModel):
    """单条语义记忆"""
    memory_id: str
    content: str
    timestamp: Optional[str] = None

class MemoryContext(BaseModel):
    """
    记忆上下文（最终注入 Prompt 的结构）
    
    使用 Pydantic 校验，确保字段完整性和类型安全，
    避免字符串拼接遗漏或格式错误。
    """
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景")
    prefer_style: Optional[str] = Field(default=None, description="喜欢风格")
    user_tags: list[str] = Field(default_factory=list, max_length=5)
    avoid_words: list[str] = Field(default_factory=list)
    last_emotion: Optional[str] = None
    milestones: list[str] = Field(default_factory=list, max_length=3)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    semantic_memories: list[SemanticMemory] = Field(default_factory=list)
    
    def to_prompt_string(self) -> str:
        """转换为 Prompt 注入字符串"""
        parts = []
        if self.prefer_scene:
            parts.append(f"- 偏好场景：{self.prefer_scene}")
        if self.prefer_style:
            parts.append(f"- 喜欢风格：{self.prefer_style}")
        # ... 其他字段
        if not parts:
            return ""
        return "【用户个性化信息】\n" + "\n".join(parts)
```

**为什么比字符串拼接好**：
1. **字段完整性**：Pydantic 强制校验，遗漏字段会被 mypy/pyright 检测
2. **类型校验**：`list[str]` vs `Any`，避免传入 dict 而非 string 的 bug
3. **可测试**：直接 `assert context.user_tags == ["程序员"]`，无需解析字符串
4. **可扩展**：新增字段只需在 model 加 Field，不破坏现有调用

---

### 1.4 架构改进方向

```
改进前：                              改进后：
┌─────────────┐                     ┌─────────────────────────────────┐
│ ChatService │                     │      EmotionService             │
│   直接调用  │                     │  (情绪识别 + 文本生成统一入口)   │
│  MemorySvc  │                     │                                 │
└─────────────┘                     │  ┌───────────┬───────────┬─────┐ │
                                    │  │ Doubao4   │ Doubao35  │MCP  │ │
                                    │  │ (Lite)    │           │     │ │
                                    │  └───────────┴───────────┴─────┘ │
                                    └─────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      MemoryManager                               │
│  (统一入口，分层管理)                                            │
│  ┌───────────┬───────────┬───────────┬────────────────────────┐  │
│  │ ShortTerm │ Working   │ LongTerm  │ Supermemory MCP       │  │
│  │ (Session) │ (Profile) │ (Milestone│ (长期记忆)            │  │
│  └───────────┴───────────┴───────────┴────────────────────────┘  │
│  ┌───────────┬───────────┬───────────┬────────────────────────┐  │
│  │Extractor  │Evaluator  │Logger     │ ContextBuilder          │  │
│  │(情绪提取) │(评测)     │(观测)     │ (上下文构建)            │  │
│  └───────────┴───────────┴───────────┴────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、工程实现方案

### 2.1 目录结构

```
kuakua-agent/
├── app/
│   ├── services/
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py          # ★ 统一入口
│   │   │   ├── short_term.py       # 短期记忆（会话）
│   │   │   ├── working.py         # 工作记忆（偏好）
│   │   │   ├── long_term.py       # 长期记忆（里程碑）
│   │   │   ├── extractor.py        # ★ 信息提取
│   │   │   ├── context_builder.py # ★ 上下文构建
│   │   │   └── evaluator.py       # ★ Prompt 评测
│   │   │
│   │   ├── emotion/
│   │   │   ├── __init__.py
│   │   │   ├── detector.py         # ★ 情绪检测（规则引擎）
│   │   │   ├── analyzer.py         # ★ 情绪分析（对接豆包4.0 Lite）
│   │   │   └── adapter.py          # ★ 情绪自适应响应
│   │   │
│   │   └── supermarket/
│   │       ├── __init__.py
│   │       ├── client.py           # ★ Supermemory MCP 客户端
│   │       └── memory_sync.py      # ★ 记忆同步服务
│   │
│   ├── api/
│   │   ├── memory.py               # 已有
│   │   ├── emotion.py              # ★ 新增：情绪相关 API
│   │   ├── chat.py                 # ★ 重构：统一聊天入口
│   │   └── evaluation.py           # ★ 新增：评测 API
│   │
│   ├── schemas/
│   │   ├── memory.py              # 已有
│   │   ├── emotion.py             # ★ 新增：情绪模型
│   │   └── chat.py                # ★ 新增：聊天模型
│   │
│   └── core/
│       ├── logging.py             # 已有
│       ├── dependencies.py        # 依赖注入
│       └── config.py              # 配置管理
│
├── tests/
│   ├── memory/
│   └── emotion/
│
└── docs/
    └── implementation-plan.md     # 本文档
```

### 2.2 核心模块实现

#### 2.2.1 情绪检测服务（EmotionDetector）

```python
# app/services/emotion/detector.py

"""
情绪检测服务

负责从文本中识别情绪状态。
使用规则 + 关键词双重检测，保证准确性和召回率。
"""

import re
from enum import Enum
from pydantic import BaseModel
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmotionType(str, Enum):
    """情绪类型枚举（与 PRD 一致）"""
    HAPPY = "happy"           # 开心
    EXCITED = "excited"       # 兴奋
    EXHAUSTED = "exhausted"   # 疲惫
    SAD = "sad"               # 难过
    FRUSTRATED = "frustrated" # 烦躁
    CALM = "calm"             # 平静


class EmotionResult(BaseModel):
    """情绪检测结果"""
    emotion: EmotionType
    intensity: float          # 0-1，置信度
    keywords: list[str]       # 触发关键词
    text: str = ""            # ASR 提取的文本


class EmotionDetector:
    """
    情绪检测器（规则引擎版本）
    
    用于文本输入的情绪检测。
    语音输入的情绪检测由 Doubao4.0 Lite 完成后传入。
    """
    
    # 情绪关键词映射
    EMOTION_PATTERNS = {
        EmotionType.HAPPY: [
            r"开心|高兴|快乐|棒|厉害|赞|优秀|完美|好开心",
            r"太好了|不错|挺棒的|真不错"
        ],
        EmotionType.EXCITED: [
            r"激动|兴奋|超赞|炸裂|太厉害了|绝了",
            r"飙升|沸腾|简直了|太牛了"
        ],
        EmotionType.EXHAUSTED: [
            r"累|困|疲惫|辛苦了|好困|没精神|熬夜",
            r"熬|通宵|秃了|快累死了|撑不住了"
        ],
        EmotionType.SAD: [
            r"难过|伤心|哭|委屈|不甘心|失落",
            r"沮丧|郁闷|惆怅|忧伤|心塞"
        ],
        EmotionType.FRUSTRATED: [
            r"烦躁|生气|恼火|郁闷|烦死了",
            r"崩溃|心态崩|想发火|气死了"
        ],
        EmotionType.CALM: [
            r"平静|淡定|还好|一般|普通",
            r"没什么|就那样|正常"
        ]
    }
    
    def detect(self, text: str) -> EmotionResult:
        """
        检测文本的情绪类型
        
        Args:
            text: 用户输入文本
            
        Returns:
            EmotionResult: 情绪检测结果
        """
        if not text or not text.strip():
            return EmotionResult(
                emotion=EmotionType.CALM,
                intensity=0.5,
                keywords=[],
                text=""
            )
        
        text_lower = text.lower()
        emotion_scores = {}
        
        # 1. 规则匹配
        for emotion, patterns in self.EMOTION_PATTERNS.items():
            score = 0
            matched_keywords = []
            for pattern in patterns:
                matches = re.findall(pattern, text_lower)
                if matches:
                    score += len(matches)
                    matched_keywords.extend(matches)
            
            if score > 0:
                emotion_scores[emotion] = (score, matched_keywords)
        
        # 2. 确定主要情绪
        if emotion_scores:
            main_emotion = max(emotion_scores.items(), key=lambda x: x[1][0])
            emotion_type = main_emotion[0]
            matched_kw = main_emotion[1][1]
            intensity = min(0.5 + main_emotion[1][0] * 0.1, 1.0)
        else:
            emotion_type = EmotionType.CALM
            matched_kw = []
            intensity = 0.5
        
        logger.info(
            f"情绪检测 | text={text[:50]}... | "
            f"emotion={emotion_type.value} | intensity={intensity:.2f}"
        )
        
        return EmotionResult(
            emotion=emotion_type,
            intensity=intensity,
            keywords=matched_kw,
            text=text
        )
```

#### 2.2.2 情绪分析服务（EmotionAnalyzer）

```python
# app/services/emotion/analyzer.py

"""
情绪分析服务

对接豆包 4.0 Lite，负责：
1. 语音输入的情绪识别 + ASR 转文本
2. 图片输入的情绪分析

统一输出 EmotionResult 格式。
"""

from pydantic import BaseModel
from typing import Optional, Literal

from app.core.logging import get_logger
from app.providers.base import BaseAIProvider

logger = get_logger(__name__)


class EmotionAnalysisResult(BaseModel):
    """情绪分析结果（来自豆包 4.0 Lite）"""
    text: str                    # ASR 提取的文本
    emotion: str                 # happy/excited/exhausted/sad/frustrated/calm
    intensity: float             # 0.0-1.0


class EmotionAnalyzer:
    """
    情绪分析服务（对接豆包 4.0 Lite）
    
    处理语音和图片输入的场景。
    """
    
    # 情绪识别 Prompt
    EMOTION_DETECTION_PROMPT = """分析音频，严格输出JSON，不要任何额外文字：
{"text":"ASR完整文本","emotion":"happy/excited/exhausted/sad/frustrated/calm","intensity":0.0-1.0}"""
    
    def __init__(self, provider: BaseAIProvider, model_name: str):
        self.provider = provider
        self.model_name = model_name
    
    async def analyze_audio(self, audio_base64: str) -> EmotionAnalysisResult:
        """
        分析语音输入的情绪
        
        Args:
            audio_base64: base64 编码的音频数据
            
        Returns:
            EmotionAnalysisResult: 情绪分析结果
        """
        logger.info(f"分析语音输入 | audio_length={len(audio_base64)}")
        
        # 构建消息
        messages = [
            {"role": "system", "content": self.EMOTION_DETECTION_PROMPT},
            {"role": "user", "content": [
                {"type": "input_audio", "input_audio": {
                    "data": audio_base64,
                    "format": "mp3"
                }}
            ]}
        ]
        
        # 调用豆包 4.0 Lite
        response = await self.provider.generate(
            prompt=messages,
            model=self.model_name
        )
        
        # 解析 JSON 响应
        import json
        try:
            result = json.loads(response)
            logger.info(f"语音分析结果 | emotion={result['emotion']} | text={result['text'][:30]}...")
            return EmotionAnalysisResult(
                text=result.get("text", ""),
                emotion=result.get("emotion", "calm"),
                intensity=float(result.get("intensity", 0.5))
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"解析失败: {e}, response={response}")
            # 失败时返回默认
            return EmotionAnalysisResult(
                text="",
                emotion="calm",
                intensity=0.5
            )
    
    async def analyze_image(self, image_base64: str) -> EmotionAnalysisResult:
        """
        分析图片输入
        
        Args:
            image_base64: base64 编码的图片数据
            
        Returns:
            EmotionAnalysisResult: 情绪分析结果
        """
        logger.info(f"分析图片输入 | image_length={len(image_base64)}")
        
        # 图片情绪分析 Prompt
        image_prompt = """分析这张图片中的情绪和内容，严格输出JSON：
{"text":"描述图片内容","emotion":"happy/excited/exhausted/sad/frustrated/calm","intensity":0.0-1.0}"""
        
        messages = [
            {"role": "system", "content": image_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }}
            ]}
        ]
        
        response = await self.provider.generate(messages=messages, model=self.model_name)
        
        import json
        try:
            result = json.loads(response)
            return EmotionAnalysisResult(
                text=result.get("text", ""),
                emotion=result.get("emotion", "calm"),
                intensity=float(result.get("intensity", 0.5))
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"解析失败: {e}, response={response}")
            return EmotionAnalysisResult(text="", emotion="calm", intensity=0.5)
```

#### 2.2.3 Supermemory MCP 客户端

```python
# app/services/supermarket/client.py

"""
Supermemory MCP 客户端

对接 Supermemory MCP，实现长期记忆的读写操作。
"""

import subprocess
import json
from typing import Optional, List
from app.core.logging import get_logger

logger = get_logger(__name__)


class SupermemoryClient:
    """
    Supermemory MCP 客户端
    
    通过命令行调用 Supermemory MCP 工具。
    """
    
    def __init__(self):
        self.mcp_tools_path = "npx"  # 或本地安装的路径
    
    async def add_memory(
        self,
        content: str,
        user_id: str,
        category: str = "general",
        intensity: float = 0.5
    ) -> bool:
        """
        添加记忆到 Supermemory
        
        Args:
            content: 记忆内容
            user_id: 用户ID
            category: 分类 (emotion/event/preference)
            intensity: 强度 (0-1)
            
        Returns:
            bool: 是否成功
        """
        cmd = f'/mem-add {content} --user {user_id} --meta {{"category":"{category}","intensity":{intensity}}}'
        
        logger.info(f"添加记忆 | user_id={user_id} | category={category} | content={content[:50]}...")
        
        try:
            result = subprocess.run(
                ["npx", "-y", "@supermemoryai/mcp", cmd],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info(f"记忆添加成功: {result.stdout}")
                return True
            else:
                logger.error(f"记忆添加失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"记忆添加异常: {e}")
            return False
    
    async def search_memories(
        self,
        query: str,
        user_id: str,
        top: int = 3
    ) -> List[str]:
        """
        搜索相关记忆
        
        Args:
            query: 查询文本
            user_id: 用户ID
            top: 返回数量
            
        Returns:
            List[str]: 记忆内容列表
        """
        cmd = f'/mem-search {query} --user {user_id} --top {top}'
        
        logger.info(f"搜索记忆 | user_id={user_id} | query={query[:50]}...")
        
        try:
            result = subprocess.run(
                ["npx", "-y", "@supermemoryai/mcp", cmd],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # 解析返回的记忆
                memories = result.stdout.strip().split("\n")
                logger.info(f"找到 {len(memories)} 条记忆")
                return memories
            else:
                logger.error(f"记忆搜索失败: {result.stderr}")
                return []
                
        except Exception as e:
            logger.error(f"记忆搜索异常: {e}")
            return []
    
    async def sync_from_session(
        self,
        user_id: str,
        session_data: dict,
        emotion: str,
        intensity: float
    ) -> None:
        """
        从会话同步重要记忆到 Supermemory
        
        当情绪强度 >= 0.8 时调用。
        
        Args:
            user_id: 用户ID
            session_data: 会话数据
            emotion: 情绪类型
            intensity: 情绪强度
        """
        if intensity >= 0.8:
            content = f"用户在 {session_data.get('time', '未知时间')} 感到 {emotion}"
            await self.add_memory(
                content=content,
                user_id=user_id,
                category="emotion",
                intensity=intensity
            )
            logger.info(f"高强度情绪同步到 Supermemory | intensity={intensity}")
```

#### 2.2.4 统一记忆管理器（MemoryManager）

```python
# app/services/memory/manager.py

"""
记忆管理器

三层记忆 + Supermemory 的统一入口，协调各层记忆的读写操作。
提供完整的记忆生命周期管理。
"""

from typing import Optional
from datetime import datetime

from app.core.logging import get_logger
from app.services.memory.short_term import ShortTermMemory
from app.services.memory.working import WorkingMemory
from app.services.memory.long_term import LongTermMemory
from app.services.memory.extractor import MemoryExtractor, ExtractedFacts
from app.services.memory.context_builder import ContextBuilder
from app.services.supermarket.client import SupermemoryClient

logger = get_logger(__name__)


class MemoryManager:
    """
    记忆管理器
    
    统一管理三层记忆（短期/工作/长期）和 Supermemory MCP，提供：
    1. 记忆的读取和更新
    2. 上下文构建
    3. 与外部服务的集成
    """
    
    def __init__(
        self,
        short_term: ShortTermMemory,
        working: WorkingMemory,
        long_term: LongTermMemory,
        supermarket: Optional[SupermemoryClient] = None
    ):
        self.short_term = short_term
        self.working = working
        self.long_term = long_term
        self.supermarket = supermarket or SupermemoryClient()
        self.extractor = MemoryExtractor()
        self.context_builder = ContextBuilder()
    
    async def on_user_message(
        self,
        user_id: str,
        session_id: str,
        content: str,
        emotion: Optional[str] = None,
        emotion_intensity: float = 0.5
    ) -> ExtractedFacts:
        """
        处理用户消息
        
        流程：
        1. 保存到短期记忆
        2. 提取信息更新工作记忆
        3. 检查是否创建里程碑
        4. 高强度情绪同步到 Supermemory
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            content: 用户输入内容
            emotion: 情绪类型（可选）
            emotion_intensity: 情绪强度（可选）
            
        Returns:
            ExtractedFacts: 提取的事实
        """
        logger.info(
            f"处理用户消息 | user_id={user_id} | session_id={session_id} | "
            f"content={content[:50]}... | emotion={emotion}"
        )
        
        # 1. 保存短期记忆
        await self.short_term.add_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=content,
            emotion=emotion,
            emotion_intensity=emotion_intensity
        )
        
        # 2. 提取记忆信息
        facts = await self.extractor.extract(content, emotion)
        
        # 3. 更新用户画像（工作记忆）
        if facts.identity_facts or facts.tags or facts.preferences:
            await self.working.update_profile(user_id, facts)
        
        # 4. 记录情绪
        if emotion:
            await self.working.update_emotion(user_id, emotion)
        
        # 5. 检查是否创建里程碑
        if self.extractor.should_create_milestone(content, emotion):
            for achievement in facts.achievements:
                await self.long_term.add_milestone(
                    user_id=user_id,
                    content=achievement,
                    source="user_input",
                    importance=2
                )
            logger.info(f"创建里程碑: {facts.achievements}")
        
        # 6. 高强度情绪同步到 Supermemory
        if emotion and emotion_intensity >= 0.8:
            await self.supermarket.sync_from_session(
                user_id=user_id,
                session_data={"content": content, "time": datetime.now().isoformat()},
                emotion=emotion,
                intensity=emotion_intensity
            )
        
        return facts
    
    async def on_assistant_response(
        self,
        session_id: str,
        content: str,
        emotion: Optional[str] = None
    ) -> None:
        """
        处理助手回复
        
        Args:
            session_id: 会话ID
            content: 助手回复内容
            emotion: 使用的情绪策略
        """
        logger.info(f"处理助手回复 | session_id={session_id} | content={content[:50]}...")
        
        await self.short_term.add_message(
            session_id=session_id,
            role="assistant",
            content=content,
            emotion=emotion
        )
    
    async def build_context(
        self,
        user_id: str,
        session_id: str,
        current_input: str = ""
    ) -> dict:
        """
        构建完整上下文
        
        整合记忆摘要、会话历史、Supermemory 检索结果。
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            current_input: 当前输入（可选）
            
        Returns:
            dict: 完整上下文
        """
        logger.info(f"构建上下文 | user_id={user_id} | session_id={session_id}")
        
        # 获取记忆摘要
        memory = await self.working.get_memory_summary(user_id, session_id)
        
        # 检索 Supermemory 相关记忆
        supermarket_memories = []
        if current_input:
            supermarket_memories = await self.supermarket.search_memories(
                query=current_input,
                user_id=user_id,
                top=3
            )
        
        # 构建上下文
        return self.context_builder.build(memory, supermarket_memories, current_input)
    
    async def get_memory_for_prompt(self, user_id: str, session_id: str) -> str:
        """
        获取格式化后的记忆字符串，用于注入 Prompt
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            
        Returns:
            str: 格式化的记忆字符串
        """
        context = await self.build_context(user_id, session_id)
        memory_str = context.get("memory", "")
        
        logger.info(f"记忆注入 | user_id={user_id} | memory_length={len(memory_str)}")
        
        return memory_str
```

---

## 三、接口定义

### 3.1 统一聊天接口（重构）

```python
# app/api/chat.py

"""
统一聊天 API（重构）

支持语音/文字/图片三种输入，统一经过：
1. 情绪检测（豆包 4.0 Lite）
2. 记忆读取（MemoryManager）
3. 夸夸生成（豆包 3.5）
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Literal

from app.core.logging import get_logger, get_trace_id
from app.services.emotion.analyzer import EmotionAnalyzer
from app.services.memory.manager import MemoryManager
from app.services.chat_service import ChatService
from app.providers.base import BaseAIProvider

router = APIRouter(prefix="/api/chat", tags=["聊天"])
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    """聊天请求"""
    user_id: str
    type: Literal["audio", "text", "image"]  # 输入类型
    content: str                              # audio: base64 mp3 / text: 文本 / image: base64
    scene: str = "general"                    # 场景类型


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str                    # 生成的夸夸文案
    emotion: str                    # 检测到的情绪
    intensity: float                # 情绪强度
    created_at: str


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    emotion_analyzer: EmotionAnalyzer = Depends(),
    memory_manager: MemoryManager = Depends(),
    chat_service: ChatService = Depends()
) -> dict:
    """
    统一聊天入口
    
    支持语音、文字、图片三种输入方式。
    
    流程：
    1. 情绪检测（语音/图片由豆包4.0 Lite处理）
    2. 记忆读取
    3. 夸夸生成（豆包3.5）
    4. 记忆更新
    
    Returns:
        生成的夸夸文案和情绪信息
    """
    trace_id = get_trace_id()
    logger.info(
        f"[{trace_id}] 聊天请求 | type={request.type} | "
        f"user_id={request.user_id} | content_length={len(request.content)}"
    )
    
    emotion_result = None
    input_text = request.content
    
    # 1. 情绪检测
    if request.type == "audio":
        # 语音输入：豆包 4.0 Lite 分析
        emotion_result = await emotion_analyzer.analyze_audio(request.content)
        input_text = emotion_result.text
        logger.info(f"[{trace_id}] 语音分析 | emotion={emotion_result.emotion} | text={input_text[:50]}...")
        
    elif request.type == "image":
        # 图片输入：豆包 4.0 Lite 分析
        emotion_result = await emotion_analyzer.analyze_image(request.content)
        input_text = emotion_result.text
        logger.info(f"[{trace_id}] 图片分析 | emotion={emotion_result.emotion} | text={input_text[:50]}...")
        
    else:
        # 文字输入：使用规则引擎检测情绪
        from app.services.emotion.detector import EmotionDetector
        detector = EmotionDetector()
        emotion_rule = detector.detect(request.content)
        emotion_result = type('obj', (object,), {
            'emotion': emotion_rule.emotion.value,
            'intensity': emotion_rule.intensity,
            'text': request.content
        })()
    
    # 2. 记忆读取
    memory_summary = await memory_manager.working.get_memory_summary(
        request.user_id,
        session_id=f"{request.user_id}_{request.type}"
    )
    
    # 3. 构建上下文
    context = await memory_manager.build_context(
        request.user_id,
        session_id=f"{request.user_id}_{request.type}",
        current_input=input_text
    )
    
    # 4. 调用聊天服务生成
    response = await chat_service.chat(
        text=input_text,
        scene=request.scene,
        emotion=emotion_result.emotion,
        emotion_intensity=emotion_result.intensity,
        memory_summary=memory_summary
    )
    
    # 5. 更新记忆
    session_id = f"{request.user_id}_{request.type}"
    await memory_manager.on_user_message(
        user_id=request.user_id,
        session_id=session_id,
        content=input_text,
        emotion=emotion_result.emotion,
        emotion_intensity=emotion_result.intensity
    )
    await memory_manager.on_assistant_response(
        session_id=session_id,
        content=response.content,
        emotion=emotion_result.emotion
    )
    
    logger.info(
        f"[{trace_id}] 聊天完成 | emotion={emotion_result.emotion} | "
        f"content={response.content[:30]}..."
    )
    
    return ChatResponse(
        content=response.content,
        emotion=emotion_result.emotion,
        intensity=emotion_result.intensity,
        created_at=response.created_at.isoformat()
    )
```

### 3.2 情绪检测 API

```python
# app/api/emotion.py

"""
情绪管理 API
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.emotion.detector import EmotionDetector, EmotionResult
from app.core.logging import get_logger, get_trace_id

router = APIRouter(prefix="/api/emotion", tags=["情绪管理"])
logger = get_logger(__name__)

emotion_detector = EmotionDetector()


class EmotionDetectRequest(BaseModel):
    """情绪检测请求"""
    text: str


class EmotionDetectResponse(BaseModel):
    """情绪检测响应"""
    emotion: str
    intensity: float
    keywords: list[str]
    style_guidance: str


@router.post("/detect", response_model=EmotionDetectResponse)
async def detect_emotion(request: EmotionDetectRequest) -> dict:
    """
    检测文本情绪（规则引擎）
    
    Returns:
        情绪检测结果，包含类型、置信度、关键词和建议
    """
    trace_id = get_trace_id()
    result = emotion_detector.detect(request.text)
    
    # 根据情绪类型给出风格指导（与 PRD 一致）
    if result.emotion.value in ["exhausted", "sad", "frustrated"]:
        guidance = "温柔安慰，缓解情绪，再适当鼓励"
    elif result.emotion.value == "excited":
        guidance = "热情共鸣，分享喜悦"
    else:
        guidance = "正常夸赞风格"
    
    logger.info(
        f"[{trace_id}] 情绪检测 API | text={request.text[:30]}... | "
        f"emotion={result.emotion.value}"
    )
    
    return EmotionDetectResponse(
        emotion=result.emotion.value,
        intensity=result.intensity,
        keywords=result.keywords,
        style_guidance=guidance
    )
```

### 3.3 收藏管理（增强）

```python
# app/api/favorites.py

class FavoriteCreate(BaseModel):
    """创建收藏请求模型（增强）"""
    user_id: str
    content: str
    emotion: str = "calm"           # ★ 新增：记录情绪
    scene: str = "general"


class FavoriteResponse(BaseModel):
    """收藏响应模型（增强）"""
    id: int
    user_id: str
    content: str
    emotion: str                    # ★ 新增
    scene: str
    created_at: datetime
```

---

## 四、观测层设计

### 4.1 日志规范

```python
# 统一日志格式（包含 trace_id）
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(trace_id)s | "
    "%(name)s | %(message)s"
)

# 关键日志点
# 1. 请求入口：chat, emotion/detect
# 2. 情绪检测：analyze_audio, analyze_image, detect
# 3. 记忆操作：on_user_message, on_assistant_response, build_context
# 4. LLM 调用：generate, generate_multimodal
```

### 4.2 结构化日志字段

```python
# 情绪检测日志
emotion_log = {
    "trace_id": "abc123",
    "event": "emotion_detect",
    "input_type": "audio",  # audio/text/image
    "emotion": "exhausted",
    "intensity": 0.9,
    "asr_text": "今天加班到很晚...",
    "processing_ms": 150.5
}

# 聊天日志
chat_log = {
    "trace_id": "abc123",
    "event": "chat_complete",
    "user_id": "user_123",
    "input_type": "audio",
    "emotion": "exhausted",
    "memory_used": ["prefer_scene:career", "milestone:完成项目"],
    "output_length": 45,
    "generation_ms": 1200.5,
    "total_ms": 1500.0
}

# 记忆操作日志
memory_log = {
    "trace_id": "abc123",
    "event": "memory_save",
    "user_id": "user_123",
    "memory_type": "short_term",
    "action": "create",
    "success": True
}
```

### 4.3 关键指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `chat.request.count` | Counter | 聊天请求次数 |
| `chat.request.duration` | Histogram | 请求处理耗时 |
| `emotion.detect.count` | Counter | 情绪检测次数 |
| `emotion.detect.by_type` | Counter | 按情绪类型统计 |
| `llm.call.count` | Counter | LLM 调用次数 |
| `llm.call.duration` | Histogram | LLM 调用耗时 |
| `memory.ops.count` | Counter | 记忆操作次数 |

---

## 五、Debug 与日志方案

### 5.1 请求追踪

```python
# 所有日志自动包含 trace_id
logger.info(
    f"[{get_trace_id()}] 处理用户消息 | "
    f"user_id={user_id} | session_id={session_id}"
)

# 响应头返回 trace_id
response.headers["X-Trace-ID"] = trace_id
response.headers["X-Request-Time-Ms"] = f"{elapsed_ms:.2f}"
```

### 5.2 Debug 模式

```python
# app/core/config.py

class Settings(BaseSettings):
    log_level: str = "INFO"
    debug_mode: bool = False        # 额外输出详细日志
    log_full_prompt: bool = False   # 谨慎使用

# Debug 模式下的额外日志
if get_settings().debug_mode:
    logger.debug(
        f"[DEBUG] 记忆更新 | profile_updated={updated} | "
        f"milestone_created={created}"
    )
```

### 5.3 错误追踪

```python
try:
    result = await emotion_analyzer.analyze_audio(audio_data)
except Exception as e:
    logger.error(
        f"[{get_trace_id()}] 情绪分析失败 | "
        f"error={str(e)} | user_id={user_id}",
        exc_info=True
    )
    # 返回默认，确保服务不中断
    result = EmotionAnalysisResult(text="", emotion="calm", intensity=0.5)
```

---

## 六、实施计划

### Phase 1: 情绪检测基础（1天）

| 任务 | 产出 | 负责人 |
|------|------|--------|
| 实现 EmotionDetector | `app/services/emotion/detector.py` | 后端 |
| 实现 EmotionAnalyzer | `app/services/emotion/analyzer.py` | 后端 |
| 实现情绪 API | `/api/emotion/detect` | 后端 |
| 单元测试 | `tests/emotion/test_detector.py` | 后端 |

### Phase 2: Supermemory 集成（0.5天）

| 任务 | 产出 | 负责人 |
|------|------|--------|
| 实现 SupermemoryClient | `app/services/supermarket/client.py` | 后端 |
| 集成到 MemoryManager | `app/services/memory/manager.py` | 后端 |

### Phase 3: 聊天接口重构（1天）

| 任务 | 产出 | 负责人 |
|------|------|--------|
| 重构 ChatService | `app/services/chat_service.py` | 后端 |
| 重构 /api/chat | `app/api/chat.py` | 后端 |
| 端到端测试 | 验证完整流程 | 后端 |

### Phase 4: 记忆管理完善（1天）

| 任务 | 产出 | 负责人 |
|------|------|--------|
| 完善 ContextBuilder | `app/services/memory/context_builder.py` | 后端 |
| 实现 MemoryExtractor | `app/services/memory/extractor.py` | 后端 |
| 完善 MemoryManager | `app/services/memory/manager.py` | 后端 |

### Phase 5: 观测层与联调（0.5天）

| 任务 | 产出 | 负责人 |
|------|------|--------|
| 结构化日志 | 日志字段规范 | 后端 |
| 前后端联调 | 验证完整流程 | 全团队 |

---

## 七、关键技术决策

### 7.1 情绪检测策略

| 方案 | 适用场景 | 选择 |
|------|----------|------|
| 规则引擎 | 文字输入 | EmotionDetector |
| 豆包 4.0 Lite | 语音/图片输入 | EmotionAnalyzer |

### 7.2 记忆存储策略

| 层级 | 存储 | TTL | 用途 |
|------|------|-----|------|
| 短期记忆 | PostgreSQL | 2小时 | 会话上下文 |
| 工作记忆 | PostgreSQL JSONB | 永久 | 用户偏好 |
| 长期记忆 | PostgreSQL + Supermemory MCP | 永久 | 高光里程碑 |

### 7.3 向量检索

**当前阶段不需要 Supermemory 以外的向量检索**，原因：
1. MVP 数据量有限，Supermemory MCP 足以支撑
2. 用户画像简单，JSONB 查询足够
3. 后续如需语义检索，可快速集成 pgvector

---

## 八、Token 成本优化（来自 PRD）

### 8.1 单次调用成本

| 环节 | Token 消耗 | 成本 |
|------|------------|------|
| 情绪识别输入 | ~1200 token | ¥0.0012 |
| 情绪识别输出 | ~50 token | ¥0.00015 |
| 夸夸生成输入 | ~300 token | ¥0.00003 |
| 夸夸生成输出 | ~80 token | ¥0.000024 |
| **总计** | ~1630 token | **¥0.0014** |

### 8.2 优化措施

1. **Prompt 精简**：避免冗余，最大化复用
2. **记忆压缩**：只注入相关记忆，避免全量加载
3. **缓存策略**：相同输入返回缓存结果（待实现）

---

## 九、文档关联

| 文档 | 说明 |
|------|------|
| [需求文档](./元气夸夸搭子%20语音情绪优先版%20需求文档.md) | 产品需求 |
| [API 文档](./api.md) | 接口定义 |
| [记忆管理详解](./memory_management.md) | 四层记忆详细设计 |
| [架构设计](./ref-memory-architecture.md) | 前沿架构参考 |
| [本文档] | 工程实现方案 |

---

## 十、总结

本方案遵循以下原则：

1. **模块化**：各服务职责清晰，易于测试和维护
2. **可观测**：结构化日志 + trace_id + 关键指标
3. **可扩展**：工厂模式支持多数据库，后续易扩展
4. **工程化**：完整的目录结构、接口定义、测试计划
5. **渐进式**：分 Phase 实施，每阶段可验证、可回滚

关键改进点：
- 新增 `EmotionDetector` 处理文本情绪检测
- 新增 `EmotionAnalyzer` 对接豆包 4.0 Lite
- 新增 `SupermemoryClient` 对接长期记忆
- 重构 `MemoryManager` 作为统一入口
- 重构 `/api/chat` 作为统一聊天入口
- 新增 `/api/emotion/*` 情绪相关 API
- 完善观测层，结构化日志 + 关键指标