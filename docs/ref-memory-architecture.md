# AI Agent 记忆管理架构设计 & 前沿探索

> 本文档聚焦于 Agent 记忆管理的**架构设计**、**前沿趋势**与**团队协作**，与 [记忆管理机制详解](./memory-management.md) 形成互补。

---

## 一、前沿探索：2024-2025 Agent 记忆管理新趋势

### 1.1 Memory as a Service (MaaS)

**核心理念**：将记忆管理独立为专门的服务层，多个 Agent 共享同一记忆基础设施。

```
┌─────────────────────────────────────────────────────┐
│                    Agent                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Planner    │  │   Tool Use   │  │  Memory   │ │
│  └─────────────┘  └──────────────┘  │   Client  │ │
│                                      └─────┬─────┘ │
└──────────────────────────────────────────────┼──────┘
                                               │
                        ┌──────────────────────▼───────┐
                        │      Memory Service          │
                        │  ┌─────────────────────────┐ │
                        │  │  Short-term (Redis)     │ │
                        │  │  Working (PostgreSQL)   │ │
                        │  │  Long-term (Vector DB)  │ │
                        │  │  Episodic (Events)      │ │
                        │  └─────────────────────────┘ │
                        └──────────────────────────────┘
```

**优势**：
- **解耦**：记忆存储与 Agent 逻辑分离
- **共享**：多个 Agent 可访问同一记忆
- **可扩展**：独立扩缩容和维护
- **标准化**：统一的记忆 API 接口

### 1.2 新兴的记忆类型

传统三层之外，前沿研究增加了：

| 类型 | 描述 | 存储方式 | 示例 |
|------|------|----------|------|
| **情景记忆** (Episodic) | 事件序列 + 时间线 | 事件日志 + 时序数据库 | "用户昨天完成了XX" |
| **语义记忆** (Semantic) | 客观知识、事实 | 知识图谱 | "编程是一项技能" |
| **程序记忆** (Procedural) | Agent 学到的操作流程 | 工作流模板 | "如何安慰焦虑用户" |

### 1.3 多模态记忆

前沿 Agent 开始支持**多模态记忆**：

```
记忆类型 ──── 模态 ──── 存储格式
─────────────────────────────────
对话内容    文本     消息历史
用户照片    图片     对象存储 + 视觉 Embedding
语音交互    音频     音频特征向量
情绪变化    时序     多维向量序列
```

---

## 二、夸夸机器人记忆架构设计

### 2.1 夸夸场景的核心需求

```
用户画像 ──────────→ 用于个性化夸赞风格
      ↓
情绪状态 ──────────→ 用于调整语气（焦虑时安慰、开心时共鸣）
      ↓
历史亮点 ──────────→ 记住用户成就，持续正向反馈
      ↓
偏好模式 ──────────→ 喜欢被夸的方向（努力/天赋/创意...）
```

### 2.2 四层记忆架构

针对夸夸场景优化的四层架构：

```
┌────────────────────────────────────────────────────┐
│ Layer 1: 即时上下文 (Immediate Context)            │
│ ┌──────────────────────────────────────────────┐ │
│ │ • 当前输入的情绪分析                          │ │
│ │ • 场景识别 (career/looks/relationship/daily)  │ │
│ │ • 关键词提取                                  │ │
│ │ • 情绪强度评分 (0-1)                         │ │
│ └──────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────┤
│ Layer 2: 对话历史 (Conversation History)           │
│ ┌──────────────────────────────────────────────┐ │
│ │ • 本次会话的对话轮次                          │ │
│ │ • 会话 ID 与时间戳                            │ │
│ │ • 存储：Redis                                │ │
│ └──────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────┤
│ Layer 3: 用户画像 (User Profile)                   │
│ ┌──────────────────────────────────────────────┐ │
│ │ • 身份事实 {职业、兴趣、生活状态}              │ │
│ │ • 情绪模式 {常出现的情绪类型}                  │ │
│ │ • 夸赞偏好 {喜欢具体的/抽象的夸法}            │ │
│ │ • 存储：PostgreSQL JSONB                     │ │
│ └──────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────┤
│ Layer 4: 里程碑记忆 (Milestone Memory)             │
│ ┌──────────────────────────────────────────────┐ │
│ │ • 用户的重要事件/成就                          │ │
│ │ • 高光时刻记录                                │ │
│ │ • 重要性评分 + 被引用次数                      │ │
│ │ • 存储：PostgreSQL / Vector DB                │ │
│ └──────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

### 2.3 记忆数据模型

```python
# app/schemas/memory.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ImmediateContext(BaseModel):
    """即时上下文 - Layer 1"""
    sentiment: str                    # positive/negative/neutral
    keywords: list[str]               # 关键词列表
    scene: str                         # career/looks/relationship/daily
    intensity: float                  # 情绪强度 0-1
    extracted_facts: list[str]         # 提取的事实

class ConversationTurn(BaseModel):
    """对话轮次 - Layer 2"""
    turn_id: int
    user_input: str
    assistant_response: str
    timestamp: datetime
    context_snapshot: ImmediateContext

class UserProfile(BaseModel):
    """用户画像 - Layer 3"""
    user_id: str
    
    identity_facts: dict = {}         # {职业、年龄、兴趣...}
    emotional_patterns: dict = {}     # {常出现的情绪类型}
    praise_preferences: dict = {}     # {喜欢的夸法}
    
    interaction_count: int = 0
    last_active: datetime
    updated_at: datetime
    
    extraction_history: list[dict] = []  # 提取历史记录

class MilestoneMemory(BaseModel):
    """里程碑记忆 - Layer 4"""
    id: Optional[int]
    user_id: str
    event: str                        # 事件描述
    date: datetime
    importance: float                 # 0-1 重要性
    access_count: int = 0
    last_accessed: datetime
    memory_type: str = "milestone"   # milestone/event/preference
    
    # 向量检索用
    embedding: Optional[list[float]] = None
```

### 2.4 上下文构建流程

```
用户输入
    │
    ▼
┌────────────────┐
│ 1. 即时理解    │───▶ 当前情绪、场景、关键词
└───────┬────────┘
        ▼
┌────────────────┐
│ 2. 短期记忆   │───▶ 最近对话、上下文窗口
│   (Redis)      │
└───────┬────────┘
        ▼
┌────────────────┐
│ 3. 中期记忆   │───▶ 用户画像、偏好、模式
│   (PostgreSQL) │
└───────┬────────┘
        ▼
┌────────────────┐
│ 4. 长期记忆   │───▶ 历史里程碑、成就回顾
│   (Vector DB)  │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Context 组装   │───▶ 组合成完整上下文
└───────┬────────┘
        │
        ▼
    生成回复
```

---

## 三、后端架构调整

### 3.1 推荐目录结构

```
kuakua-agent/
├── app/
│   ├── services/
│   │   ├── memory/              # ★ 记忆管理模块
│   │   │   ├── __init__.py
│   │   │   ├── short_term.py        # 短期记忆（Redis）
│   │   │   ├── working.py            # 工作记忆（PostgreSQL）
│   │   │   ├── long_term.py         # 长期记忆（向量检索）
│   │   │   ├── extractor.py         # 记忆提取（LLM调用）
│   │   │   ├── context_builder.py   # 上下文构建
│   │   │   └── manager.py           # 统一管理入口
│   │   │
│   │   ├── evaluation/          # ★ Prompt 评测模块
│   │   │   ├── __init__.py
│   │   │   ├── judge.py              # LLM-as-Judge
│   │   │   ├── batch_runner.py       # 批量测试
│   │   │   └── reporter.py           # 报告生成
│   │   │
│   │   └── ...existing...
│   │
│   ├── api/
│   │   ├── memory.py            # ★ 记忆管理 API
│   │   ├── evaluation.py        # ★ 评测 API
│   │   └── ...existing...
│   │
│   └── schemas/
│       ├── memory.py             # ★ 记忆数据模型
│       └── evaluation.py         # ★ 评测数据模型
│
├── tests/
│   ├── memory/                   # ★ 记忆模块测试
│   └── evaluation/              # ★ 评测模块测试
│
└── docs/
    ├── memory-management.md      # 记忆管理详解
    └── memory-architecture.md    # 本文档：架构设计
```

### 3.2 核心服务实现

```python
# app/services/memory/manager.py

from app.services.memory.short_term import ShortTermMemory
from app.services.memory.working import WorkingMemory
from app.services.memory.long_term import LongTermMemory
from app.services.memory.extractor import MemoryExtractor
from app.services.memory.context_builder import ContextBuilder

class MemoryManager:
    """
    记忆管理统一入口
    
    协作说明：
    - 后端开发：负责实现存储层和 API
    - 评测团队：通过 Admin API 操作，无需了解内部实现
    """
    
    def __init__(self, redis, db, vector_store):
        self.short_term = ShortTermMemory(redis)
        self.working = WorkingMemory(db)
        self.long_term = LongTermMemory(vector_store)
        self.extractor = MemoryExtractor()
        self.builder = ContextBuilder()
    
    async def on_user_message(self, user_id: str, session_id: str, content: str):
        """
        用户发消息时的处理流程
        """
        # 1. 即时理解
        immediate = await self.extractor.extract_immediate(content)
        
        # 2. 保存短期记忆
        await self.short_term.add_message(session_id, "user", content, immediate)
        
        # 3. 尝试更新用户画像（定期或关键信息时）
        if immediate.important_update:
            await self.working.update_profile(user_id, immediate.facts)
        
        # 4. 提取里程碑记忆
        if immediate.is_milestone:
            await self.long_term.add_memory(user_id, immediate.milestone)
        
        return immediate
    
    async def on_assistant_response(self, session_id: str, content: str):
        """助手回复时的处理"""
        await self.short_term.add_message(session_id, "assistant", content)
    
    async def build_context(self, user_id: str, session_id: str) -> dict:
        """
        构建完整上下文供 LLM 使用
        """
        # 1. 获取各层记忆
        recent = await self.short_term.get_recent(session_id, limit=10)
        profile = await self.working.get_profile(user_id)
        memories = await self.long_term.get_relevant(user_id, query=profile.interests)
        
        # 2. 组装
        return self.builder.build(
            immediate=None,  # 当前输入单独传入
            short_term=recent,
            user_profile=profile,
            long_term_memories=memories
        )
```

### 3.3 协作友好的 API 设计

```python
# app/api/memory.py - Admin/运营使用的 API

from fastapi import APIRouter, Depends, UploadFile, File
from typing import Optional

router = APIRouter(prefix="/api/memory", tags=["记忆管理"])

# ===== 记忆管理 API =====

@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str):
    """获取用户画像 - 评测人员查看"""
    return await memory_service.working.get_profile(user_id)

@router.put("/profile/{user_id}")
async def update_profile(user_id: str, profile: dict):
    """更新用户画像 - 可批量导入"""
    return await memory_service.working.update_profile(user_id, profile)

@router.get("/history/{user_id}")
async def get_conversation_history(user_id: str, limit: int = 50):
    """获取对话历史"""
    return await memory_service.short_term.get_user_history(user_id, limit)

@router.delete("/{memory_id}")
async def delete_memory(memory_id: int):
    """删除特定记忆"""
    return await memory_service.long_term.delete(memory_id)


# ===== 评测 API =====

@router.post("/eval/run")
async def run_single_eval(input_text: str, scene: str = "general"):
    """运行单次评测 - 测试 Prompt 效果"""
    return await evaluation_service.run(input_text, scene)

@router.post("/eval/batch")
async def batch_evaluate(
    test_set: UploadFile = File(...),  # 上传测试集 JSON
    scene: str = "general"
):
    """批量评测"""
    data = await test_set.read()
    test_set = json.loads(data)
    return await evaluation_service.batch_run(test_set, scene)

@router.get("/eval/results/{test_id}")
async def get_eval_results(test_id: str):
    """查看评测结果"""
    return await evaluation_service.get_results(test_id)

@router.get("/eval/report/{test_id}")
async def generate_report(test_id: str):
    """生成评测报告"""
    return await evaluation_service.generate_report(test_id)


# ===== 数据导入导出 =====

@router.get("/export/{user_id}")
async def export_user_data(user_id: str):
    """导出用户所有数据 - 用于协作/备份"""
    return await memory_service.export_all(user_id)

@router.post("/import/{user_id}")
async def import_user_data(user_id: str, data: dict):
    """导入用户数据 - 批量初始化测试数据"""
    return await memory_service.import_all(user_id, data)
```

### 3.4 标准化协作接口

**核心目标**：解耦记忆管理与评测模块，通过标准化接口高效协作。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         标准化协作接口设计                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐              ┌─────────────────┐                      │
│  │  记忆管理模块    │              │  评测管理模块     │                      │
│  │                 │              │                 │                      │
│  │  • 采集/存储    │◀────────────▶│  • 测试集管理    │                      │
│  │  • 检索/更新    │              │  • 评分/报告     │                      │
│  │  • 遗忘清理    │              │  • A/B 测试      │                      │
│  └────────┬────────┘              └────────┬────────┘                      │
│           │                                │                               │
│           │    ┌──────────────────────┐    │                               │
│           │    │  标准化接口层        │    │                               │
│           │    ├──────────────────────┤    │                               │
│           │    │  Memory→Eval:       │    │                               │
│           │    │  - 记忆-任务关联API  │    │                               │
│           │    │  - 记忆内容查询API  │    │                               │
│           │    ├──────────────────────┤    │                               │
│           │    │  Eval→Memory:       │    │                               │
│           │    │  - 回调评测结果API  │    │                               │
│           │    │  - 驱动记忆更新/遗忘 │    │                               │
│           │    └──────────────────────┘    │                               │
│           │                                │                               │
└───────────┼────────────────────────────────┼───────────────────────────────┘
            │                                │
            ▼                                ▼
     ┌─────────────────────────────────────────────────┐
     │              观测层 (Observability)               │
     │  日志系统 │ 指标监控 │ 全链路追踪 │ 共享看板      │
     └─────────────────────────────────────────────────┘
```

**接口定义示例**：

```python
# ===== 记忆→评测：数据共享接口 =====

@router.get("/api/memory/eval/link/{task_id}")
async def get_memory_task_link(task_id: str):
    """
    获取记忆-任务关联数据
    供评测验证记忆有效性
    """
    return {
        "task_id": task_id,
        "used_memories": [
            {
                "memory_id": "mem-001",
                "content": "用户是程序员",
                "memory_type": "semantic",
                "scene": "career"
            }
        ],
        "agent_decision": "选择夸赞用户的专业技术能力"
    }

# ===== 评测→记忆：回调更新接口 =====

@router.post("/api/memory/eval/callback")
async def eval_result_callback(result: EvalCallback):
    """
    评测结果回调
    驱动记忆更新/遗忘策略优化
    """
    # 1. 记录评测得分
    await memory_service.record_eval_score(
        memory_id=result.memory_id,
        score=result.score,
        feedback=result.feedback
    )
    
    # 2. 如果得分低，标记为待遗忘
    if result.score < 0.5:
        await memory_service.mark_for_forgetting(result.memory_id)
    
    # 3. 如果发现新模式，更新画像
    if result.new_pattern:
        await memory_service.update_profile(result.user_id, result.new_pattern)
```

### 3.5 观测层设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           观测层 (Observability)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐  │
│  │   日志系统    │  │   指标监控    │  │   全链路追踪                      │  │
│  │              │  │              │  │                                  │  │
│  │ • 记忆操作   │  │ • 检索准确率  │  │ Agent → Memory → Evaluation      │  │
│  │   日志       │  │ • 评测得分   │  │     ↓         ↓           ↓      │  │
│  │ • 评测记录   │  │ • 任务完成率 │  │   Request  →  Store    →  Score  │  │
│  │ • Agent交互  │  │ • 记忆新鲜度 │  │                                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                          共享看板 (Dashboard)                          │  │
│  │                                                                       │  │
│  │   记忆团队视角：                    评测团队视角：                      │  │
│  │   • 记忆使用率                      • 评测得分趋势                      │  │
│  │   • 检索命中率                      • A/B 测试对比                      │  │
│  │   • 遗忘清理效果                    • 低分样本分析                      │  │
│  │                                                                       │  │
│  │   ┌─────────────────┐    ┌─────────────────┐                        │  │
│  │   │   脱敏后记忆     │◄──▶│   脱敏后评测     │                        │  │
│  │   │   数据展示       │    │   结果展示       │                        │  │
│  │   └─────────────────┘    └─────────────────┘                        │  │
│  │                                                                       │  │
│  │   人工标注回流：评测团队标注的低质量记忆 → 回流到记忆管理器优化抽取策略     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**日志字段规范**：

```python
# 记忆操作日志
memory_log = {
    "timestamp": "2024-05-20T10:30:00Z",
    "event_type": "memory_retrieve",  # save/retrieve/update/forget
    "user_id": "user_123",
    "memory_id": "mem-001",
    "memory_type": "semantic",
    "scene": "career",
    "retrieved_count": 5,
    "latency_ms": 12,
    "trace_id": "trace-xxx-yyy",
    "eval_triggered": True,
    "eval_score": 0.88
}

# 评测任务日志
eval_log = {
    "timestamp": "2024-05-20T10:30:00Z",
    "test_id": "test-001",
    "prompt_version": "v2.1",
    "input": "今天被老板骂了",
    "output": "虽然被批评了...",
    "scores": {
        "relevance": 0.92,
        "warmth": 0.85,
        "personalization": 0.78
    },
    "memory_used": ["mem-001", "mem-003"],
    "user_feedback": None  # 后续补充
}
```

**版本化管理**：

```python
# Prompt 版本管理
class PromptVersion:
    version: str          # v1.0, v2.1
    prompt_template: str
    created_at: datetime
    created_by: str
    eval_scores: list[float]
    status: str           # draft/active/deprecated

# 记忆模板版本管理
class MemoryTemplate:
    version: str          # mt-v1.0
    extraction_rules: dict
    importance_threshold: float
    ttl_days: int
    created_at: datetime
    eval_feedback: dict
```

---

## 四、团队协作模式

### 4.1 角色分工

```
┌──────────────────────────────────────────────────┐
│              后端开发                             │
│  • 记忆存储层实现                                 │
│  • API 接口开发                                  │
│  • 数据库设计与维护                              │
│  • 部署运维                                      │
└────────────┬──────────────────┬──────────────────┘
             │                  │
             ▼                  ▼
┌───────────────────┐  ┌────────────────────────────┐
│   前端开发        │  │  记忆管理 + Prompt 评测   │
│   • 小程序/Web    │  │  • 记忆策略设计           │
│   • 调用后端 API  │  │  • Prompt 优化与迭代      │
│   • 展示用户画像  │  │  • 评测测试集维护         │
│                  │  │  • 数据分析与报告         │
└──────────────────┘  └────────────────────────────┘
```

### 4.2 协作工作流

```
1. 评测团队准备测试集
   ↓ (上传 JSON 测试集)
2. 运行批量评测
   ↓ (生成结果)
3. 分析评测报告
   ↓ (发现 Prompt 问题)
4. 调整 Prompt 模板
   ↓ (通过 Admin API)
5. 再次评测验证
   ↓ (A/B 测试)
6. 灰度/全量发布
```

### 4.3 协作命令参考

```bash
# 1. 查看所有 prompt
curl http://localhost:8000/api/admin/prompts \
  -H "X-Admin-Key: your_admin_key"

# 2. 测试 prompt 效果
curl -X POST http://localhost:8000/api/memory/eval/run \
  -H "X-Admin-Key: your_admin_key" \
  -d '{"input_text": "今天被老板骂了", "scene": "career"}'

# 3. 批量评测（上传测试集）
curl -X POST http://localhost:8000/api/memory/eval/batch \
  -H "X-Admin-Key: your_admin_key" \
  -F "test_set=@./test_data/career_test_set.json" \
  -F "scene=career"

# 4. 查看评测报告
curl http://localhost:8000/api/memory/eval/report/test_001 \
  -H "X-Admin-Key: your_admin_key"

# 5. 查看用户画像
curl http://localhost:8000/api/memory/profile/user_123 \
  -H "X-Admin-Key: your_admin_key"

# 6. 导出测试数据
curl http://localhost:8000/api/memory/export/user_123 \
  -H "X-Admin-Key: your_admin_key" -o user_123_backup.json
```

---

## 五、存储方案选型

### 5.1 自建方案对比

| 方案 | 适用场景 | 优点 | 缺点 | 成本 |
|------|----------|------|------|------|
| **Redis + PostgreSQL** | 中小规模、快速启动 | 简单、运维轻量 | 无原生向量检索 | 低 |
| **PostgreSQL + pgvector** | 中等规模、一体化 | SQL 能力强、统一存储 | 性能不如专业向量库 | 低 |
| **Chroma/FAISS** | 向量为主 | 高性能、简单 API | 分布式弱 | 中 |
| **Pinecone/Milvus** | 大规模生产 | 云原生、高可用 | 需要维护 | 高 |
| **混合方案** | 推荐 | 各取所长 | 复杂度略高 | 中 |

### 5.2 BaaS 方案对比（Cloudbase vs Supabase）

| 确认维度 | Supabase | Cloudbase |
|----------|----------|-----------|
| **向量存储** | PG+pgvector 原生支持 | 需额外插件适配 |
| **Redis 缓存** | 可通过第三方服务 | 云开发缓存 API |
| **对象存储** | S3 兼容存储 | 腾讯云 COS |
| **协作权限** | 细粒度 RLS 策略 | 身份认证+安全规则 |
| **实时同步** | Realtime 原生支持 | 实时数据库能力 |
| **可扩展性** | 自动扩缩容 | 按量计费弹性 |
| **SDK 支持** | Python/Node.js/Flutter | Python/Node.js |
| **合规/区域** | 开源可控、多区域 | 国内合规、微信生态 |

**选型建议**：
- **Supabase**：开源可控，适合技术团队自主定制，适配开源 Agent 框架
- **Cloudbase**：国内访问快，集成微信生态（如面向小程序场景）

### 5.3 夸夸机器人推荐方案

**Phase 1（0-10万用户）**：
```
短期记忆：Redis（TTL 自动过期）
中期记忆：PostgreSQL JSONB
长期记忆：PostgreSQL + 全文检索（暂不加向量）
```

**Phase 2（10万+用户或需要语义检索）**：
```
添加 pgvector 或使用 Supabase/Cloudbase 向量能力
```

---

## 六、文档关联

| 文档 | 内容 |
|------|------|
| **[记忆管理机制详解](./memory-management.md)** | 四层模型、全生命周期闭环、Prompt 评测方法论 |
| **本文档** | 架构设计、前沿趋势、团队协作指南、存储选型 |

---

## 七、延伸阅读

- [LangGraph 状态管理](https://langchain-ai.github.io/langgraph/)
- [LLM-as-Judge 论文](https://arxiv.org/abs/2306.05685)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [RAG 最佳实践](https://docs.llamaindex.ai/en/stable/)
- [Supabase 向量检索](https://supabase.com/docs/guides/database/postgres/vector)
- [神经符号记忆 (Google Sparrow)](https://arxiv.org/abs/2204.01691)
- [Meta Agent 记忆架构](https://arxiv.org/abs/2308.00352)
- [Claude Context Compression](https://www.anthropic.com/news/context-windows)
