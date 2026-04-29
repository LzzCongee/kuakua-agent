# AI Agent 记忆管理与 Prompt 评测

> kuakua-agent 项目中记忆管理机制设计、工业界最佳实践、团队协工作流的完整指南。

---

## 一、为什么需要记忆管理？

### 1.1 核心痛点

大语言模型（LLM）本身是**无状态**的。每次请求对模型来说都是全新对话，它不会自动记住用户之前说过什么、偏好什么、历史交互内容。

如果没有记忆管理，Agent 只能做到：
- 单轮问答（一问一答）
- 无法根据用户历史行为个性化回复
- 无法实现"越用越懂你"的智能体验

### 1.2 记忆管理的价值

| 能力 | 无记忆 | 有记忆 |
|------|--------|--------|
| 个性化 | 每次都是全新用户 | 根据历史交互生成个性化内容 |
| 上下文理解 | 只看当前输入 | 理解对话历史、用户偏好 |
| 连续性 | 无法跨会话保持 | 用户隔几天再来也能接上 |
| 知识积累 | 不学习 | 从交互中提取有价值的信息存储 |

---

## 二、记忆的分类（工业界标准）

### 2.1 三层记忆模型

工业界（如 LangChain、LangGraph、OpenAI Assistants API）通常采用以下分层架构：

```
┌───────────────────────────────────────────────────┐
│                   用户交互                          │
└──────────────────────┬────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
  ┌──────────┐  ┌────────────┐  ┌───────────┐
  │ 短期记忆  │  │  工作记忆   │  │  长期记忆  │
  │ (Short-  │  │  (Working  │  │ (Long-    │
  │  Term)   │  │   Memory)  │  │  Term)    │
  └──────────┘  └────────────┘  └───────────┘
```

### 2.2 各层记忆详解

#### 短期记忆（Short-term Memory）

**存储内容**：当前对话/会话的消息历史

**作用**：让模型理解上下文，实现多轮对话

**实现方式**：
- 简单的消息列表（message history）
- 存储在 Redis / 内存 / 本地数据库
- 按 `session_id` 或 `conversation_id` 索引

**容量限制**：受限于模型上下文窗口（通常 8K-128K tokens）

**示例**：
```
Session: user_123_session_456
Messages: [
  {role: "user", content: "今天好累"},
  {role: "assistant", content: "辛苦啦！来夸夸你..."},
  {role: "user", content: "再多夸一点"},
  // ... 最近 N 条消息
]
```

#### 工作记忆（Working Memory）

**存储内容**：从对话中提取的关键事实、意图、情绪状态

**作用**：
- 提取用户信息（"我是程序员"、"我喜欢画画"）
- 跟踪情绪状态（开心、沮丧、焦虑）
- 记录任务进度（"用户正在准备面试"）

**实现方式**：
- 结构化数据（JSON / 数据库表）
- 通过 LLM 自动提取，或规则提取
- 每次对话后更新

**示例**：
```json
{
  "user_id": "user_123",
  "facts": [
    {"key": "occupation", "value": "程序员", "confidence": 0.9},
    {"key": "hobby", "value": "画画", "confidence": 0.8}
  ],
  "emotional_state": "tired",
  "current_task": "preparing_for_interview",
  "last_updated": "2024-01-15T10:30:00"
}
```

#### 长期记忆（Long-term Memory）

**存储内容**：用户画像、历史交互摘要、重要里程碑

**作用**：
- 跨会话保持用户画像
- 记住重要事件（"用户上次说面试成功了"）
- 支持"越用越懂你"

**实现方式**：
- 向量数据库（FAISS、Chroma、Pinecone、Weaviate）
- 关系数据库 + 摘要生成
- 定期压缩和更新

**示例**：
```json
{
  "user_id": "user_123",
  "profile": {
    "name": "小明",
    "interests": ["编程", "画画", "音乐"],
    "personality_traits": ["内向", "追求完美"]
  },
  "milestones": [
    {"event": "完成第一个项目", "date": "2024-01-10"},
    {"event": "面试成功", "date": "2024-01-20"}
  ],
  "interaction_summary": "用户喜欢被夸赞创造力和毅力"
}
```

---

## 三、上下文管理策略

### 3.1 问题：上下文窗口有限

模型上下文窗口有限（如 8K、32K、128K tokens），不能把所有历史都塞进去。

### 3.2 工业界常用策略

#### 策略 1：滑动窗口（Sliding Window）

保留最近 N 条消息，超出窗口就丢弃。

**适用场景**：简单对话，不需要长期记忆

**实现**：
```python
# 只保留最近 10 条消息
recent_messages = conversation_history[-10:]
```

**优点**：简单、高效  
**缺点**：会丢失早期重要信息

---

#### 策略 2：摘要压缩（Summary Compression）

将早期对话压缩成摘要，放入上下文。

**实现**：
```
完整上下文 = [
  "对话摘要：用户正在准备面试，情绪焦虑",  # LLM 生成的摘要
  {"role": "user", content": "今天模拟面试怎么样？"},  # 最近对话
  {"role": "assistant", content": "上次你说..."},
]
```

**优点**：保留核心信息，节省 tokens  
**缺点**：需要额外调用 LLM 生成摘要

---

#### 策略 3：检索增强（Retrieval-Augmented）

使用向量数据库存储历史，按需检索相关记忆。

**实现**：
```python
# 用户输入
query = "上次说的面试准备得怎么样？"

# 从向量数据库检索相关记忆
memories = vector_db.search(query, top_k=3)
# 返回: ["用户提到面试在周三", "用户准备了算法题", ...]

# 组合上下文
context = build_context(memories, recent_messages)
```

**优点**：灵活、可扩展、支持大量历史  
**缺点**：需要向量数据库、实现复杂

---

#### 策略 4：分层混合（Hybrid）

**最佳实践**：结合以上所有策略

```
┌─────────────────────────────────────────────┐
│  系统 Prompt + 用户画像 (长期)                │
├─────────────────────────────────────────────┤
│  检索到的相关记忆 (向量检索)                   │
├─────────────────────────────────────────────┤
│  对话摘要 (中期)                              │
├─────────────────────────────────────────────┤
│  最近 N 条消息 (短期)                         │
└─────────────────────────────────────────────┘
              ↓
        组合成完整 Context
              ↓
           发送给 LLM
```

---

## 四、kuakua-agent 中的记忆管理架构设计

### 4.1 当前项目状态

当前项目实现了**基础会话管理**（通过 `user_id`），但缺少：
- 多轮对话历史管理
- 用户画像/偏好提取
- 长期记忆存储与检索

### 4.2 推荐的数据库表设计

在现有数据库基础上，新增以下表：

```sql
-- 对话会话表
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    scene VARCHAR(50) NOT NULL DEFAULT 'general',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- 对话消息表（短期记忆）
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    role VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',  -- 扩展字段（情绪、标签等）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户画像/工作记忆表
CREATE TABLE user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL UNIQUE,
    profile_data JSONB NOT NULL,  -- 存储提取的事实、偏好
    emotional_state VARCHAR(50),
    last_interaction TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 长期记忆向量表（如果用 pgvector 扩展）
-- 或使用外部向量数据库
CREATE TABLE long_term_memories (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI embedding 维度
    memory_type VARCHAR(50),  -- 'fact', 'event', 'preference'
    importance FLOAT DEFAULT 0.5,  -- 重要性评分
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 推荐的 Python 服务层设计

```python
# app/services/memory_service.py

class MemoryService:
    """
    记忆管理服务
    
    负责：
    1. 短期记忆：管理对话历史
    2. 工作记忆：提取和存储用户信息
    3. 长期记忆：向量检索相关记忆
    """
    
    async def add_message(self, conversation_id, role, content):
        """添加消息到短期记忆"""
        pass
    
    async def get_recent_messages(self, conversation_id, limit=10):
        """获取最近 N 条消息"""
        pass
    
    async def extract_facts(self, messages):
        """从对话中提取用户事实/偏好"""
        # 调用 LLM 提取
        pass
    
    async def update_user_profile(self, user_id, facts):
        """更新用户画像（工作记忆）"""
        pass
    
    async def retrieve_relevant_memories(self, user_id, query, top_k=3):
        """检索相关长期记忆"""
        # 向量检索
        pass
    
    async def build_context(self, user_id, conversation_id, current_input):
        """构建完整上下文"""
        recent = await self.get_recent_messages(conversation_id)
        profile = await self.get_user_profile(user_id)
        memories = await self.retrieve_relevant_memories(user_id, current_input)
        
        return combine_context(recent, profile, memories)
```

### 4.4 推荐的 API 接口设计

在现有 admin API 基础上，新增记忆管理接口：

```python
# app/api/memory.py
router = APIRouter(prefix="/api/memory", tags=["记忆管理"])

# 对话管理
GET    /api/memory/conversations?user_id=xxx    # 获取用户对话列表
POST   /api/memory/conversations                 # 创建新对话
GET    /api/memory/conversations/{id}/messages   # 获取对话消息历史

# 用户画像
GET    /api/memory/profile?user_id=xxx           # 获取用户画像
PUT    /api/memory/profile                       # 更新用户画像

# 记忆检索
GET    /api/memory/retrieve?user_id=xxx&q=xxx    # 检索相关记忆
DELETE /api/memory/{id}                          # 删除记忆
```

---

## 五、Prompt 评测方法论

### 5.1 什么是 Prompt 评测？

Prompt 评测是系统性地测试和比较不同 Prompt 模板的效果，确保输出质量符合预期。

### 5.2 评测维度

| 维度 | 说明 | 评估方式 |
|------|------|----------|
| 相关性 | 输出是否与输入相关 | LLM 自动评分 |
| 情感温度 | 夸赞是否真诚、温暖 | LLM 评分 + 人工抽查 |
| 个性化 | 是否根据用户信息定制 | A/B 测试对比 |
| 多样性 | 多次生成是否不重复 | 去重率计算 |
| 安全性 | 是否包含不当内容 | 规则过滤 + LLM 检测 |
| 长度 | 输出长度是否合适 | 统计 tokens |

### 5.3 评测流程

```
┌─────────────────────────────────────────────────┐
│  1. 准备测试集 (Test Dataset)                     │
│     - 100 条真实用户输入                            │
│     - 覆盖不同场景（事业、颜值、恋爱、日常）           │
│     - 包含边界情况（敏感词、空输入等）               │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  2. 批量生成 (Batch Generation)                   │
│     - 用 Prompt V1 对测试集生成输出                │
│     - 用 Prompt V2 对同一测试集生成输出             │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  3. 自动评分 (Automatic Scoring)                  │
│     - 用 LLM-as-Judge 对每个输出评分               │
│     - 维度：相关性、情感、个性化等                   │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  4. 统计分析 (Statistical Analysis)               │
│     - 计算平均分、方差                              │
│     - V1 vs V2 显著性检验                          │
│     - 生成对比报告                                  │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  5. 人工抽查 (Human Review)                       │
│     - 随机抽取 10% 输出人工审核                     │
│     - 确认自动评分与人工判断一致                     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  6. 上线/迭代 (Deploy or Iterate)                 │
│     - 评分高：部署到生产                            │
│     - 评分低：修改 Prompt，重新评测                 │
└─────────────────────────────────────────────────┘
```

### 5.4 实现示例（LLM-as-Judge）

```python
# app/services/prompt_evaluator.py

class PromptEvaluator:
    """
    Prompt 评测服务
    
    使用 LLM 作为评判者（LLM-as-Judge）对输出质量评分
    """
    
    async def evaluate(
        self,
        input_text: str,
        output_text: str,
        criteria: list[str] = ["relevance", "warmth", "personalization"]
    ) -> dict:
        """
        对单个输出进行多维度评分
        
        Returns:
            {
                "relevance": 0.85,
                "warmth": 0.92,
                "personalization": 0.78,
                "overall": 0.85
            }
        """
        judge_prompt = f"""
        你是一个专业的 Prompt 评测专家。请对以下 AI 生成的夸赞文案进行评分。
        
        用户输入：{input_text}
        AI 输出：{output_text}
        
        请从以下维度评分（0-1 分）：
        - 相关性：输出是否与用户输入相关
        - 温暖度：夸赞是否真诚、温暖
        - 个性化：是否根据用户信息定制
        
        请以 JSON 格式返回评分。
        """
        
        response = await self.provider.generate(judge_prompt)
        scores = json.loads(response)
        scores["overall"] = sum(scores.values()) / len(scores)
        
        return scores
    
    async def batch_evaluate(
        self,
        test_dataset: list[dict],
        prompt_version: str
    ) -> dict:
        """
        批量评测测试集
        
        Returns:
            {
                "prompt_version": "v1",
                "total_samples": 100,
                "average_scores": {...},
                "results": [...]
            }
        """
        results = []
        for sample in test_dataset:
            output = await self.generate(sample["input"], prompt_version)
            scores = await self.evaluate(sample["input"], output)
            results.append({
                "input": sample["input"],
                "output": output,
                "scores": scores
            })
        
        return self._calculate_statistics(results)
```

### 5.5 A/B 测试与灰度发布

在现有 `/api/admin/ab-tests` 基础上，增加评测数据收集：

```python
# 在 chat 接口中记录 A/B 测试结果
async def chat_stream(request, session):
    # 获取 prompt（可能走 A 组或 B 组）
    prompt = await self.get_prompt_with_ab(request.scene, request.user_id, session)
    
    # 生成输出
    output = await provider.generate(...)
    
    # 记录日志
    await self.log_ab_test(
        user_id=request.user_id,
        ab_test_id=prompt.ab_test_id,
        group=prompt.group,  # 'A' or 'B'
        output=output,
        timestamp=datetime.now()
    )
    
    return output

# Admin 接口查看 A/B 测试结果
GET /api/admin/ab-tests/{id}/results    # 查看 A/B 组对比数据
GET /api/admin/ab-tests/{id}/metrics    # 查看关键指标（点赞率、收藏率等）
```

---

## 六、团队协作工作流

### 6.1 角色分工

```
┌──────────────────────────────────────────────────┐
│              你（后端开发）                         │
│  - 记忆管理服务开发                                │
│  - 数据库设计与管理                                │
│  - API 接口暴露                                   │
│  - 部署运维                                      │
└────────────┬───────────────────┬─────────────────┘
             │                   │
             ▼                   ▼
┌───────────────────┐ ┌─────────────────────────────┐
│  前端队友          │ │  记忆管理 + Prompt 评测队友   │
│  - 小程序/Web 开发 │ │  - 记忆策略设计               │
│  - 调用后端 API   │ │  - Prompt 优化与迭代          │
│  - 展示记忆/画像   │ │  - 评测测试集维护             │
│                   │ │  - 调用 admin 接口测试        │
└───────────────────┘ └─────────────────────────────┘
```

### 6.2 协作者工作流

#### Prompt 评测队友的日常操作

```bash
# 1. 查看所有 prompt
curl http://localhost:8000/api/admin/prompts \
  -H "X-Admin-Key: your_admin_key"

# 2. 获取事业场景 prompt
curl http://localhost:8000/api/admin/prompts/career \
  -H "X-Admin-Key: your_admin_key"

# 3. 测试 prompt 效果
curl -X POST http://localhost:8000/api/admin/prompts/career/test \
  -H "X-Admin-Key: your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "test_input": "今天完成了一个重要项目",
    "temperature": 0.8
  }'

# 4. 更新 prompt
curl -X PUT http://localhost:8000/api/admin/prompts/career \
  -H "X-Admin-Key: your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "system_prompt": "新的 prompt 内容...",
    "updated_by": "prompt_evaluator"
  }'

# 5. 创建 A/B 测试
curl -X POST http://localhost:8000/api/admin/ab-tests \
  -H "X-Admin-Key: your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "事业场景 prompt 优化",
    "scene": "career",
    "prompt_a_id": 1,
    "prompt_b_id": 2,
    "traffic_ratio": 0.5
  }'
```

### 6.3 记忆管理队友的职责

1. **设计记忆提取规则**
   - 定义从对话中提取哪些信息（职业、兴趣、情绪等）
   - 设计 Prompt 让 LLM 自动提取

2. **维护用户画像 schema**
   - 定义用户画像的 JSON 结构
   - 定期更新和优化

3. **管理长期记忆策略**
   - 决定什么信息需要长期存储
   - 设计记忆重要性评分算法

4. **执行 Prompt 评测**
   - 维护测试集
   - 运行批量评测
   - 分析结果，迭代 Prompt

---

## 七、工业界最佳实践参考

### 7.1 LangChain Memory 模块

LangChain 提供多种记忆实现：

```python
from langchain.memory import (
    ConversationBufferMemory,     # 简单消息历史
    ConversationSummaryMemory,    # 摘要记忆
    ConversationBufferWindowMemory,  # 滑动窗口
    VectorStoreRetrieverMemory,   # 向量检索记忆
)
```

**适用场景**：快速原型、简单项目

**缺点**：不够灵活，难以定制化

---

### 7.2 LangGraph 状态管理

LangGraph 使用图结构管理 Agent 状态：

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    messages: list
    user_profile: dict
    memories: list

# 定义节点
def extract_memory(state):
    # 提取记忆
    pass

def retrieve_memory(state):
    # 检索记忆
    pass

def generate_response(state):
    # 生成回复
    pass

# 构建图
graph = StateGraph(AgentState)
graph.add_node("extract", extract_memory)
graph.add_node("retrieve", retrieve_memory)
graph.add_node("generate", generate_response)
graph.set_entry_point("extract")
graph.add_edge("extract", "retrieve")
graph.add_edge("retrieve", "generate")
graph.add_edge("generate", END)
```

**适用场景**：复杂 Agent、需要多步推理

---

### 7.3 OpenAI Assistants API

OpenAI 原生支持记忆管理：

```python
from openai import OpenAI

client = OpenAI()

# 创建 Thread（自动管理对话历史）
thread = client.beta.threads.create()

# 添加消息
client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content="你好！"
)

# 运行 Assistant（自动检索记忆、生成回复）
run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id="asst_xxx"
)
```

**优点**：开箱即用、无需自己实现记忆

**缺点**：锁定 OpenAI 生态、成本高

---

### 7.4 推荐方案：混合架构

对于 kuakua-agent 项目，推荐采用**混合架构**：

```
┌──────────────────────────────────────────────┐
│  FastAPI (你的后端)                            │
│  ├── 短期记忆：PostgreSQL (messages 表)       │
│  ├── 工作记忆：PostgreSQL (user_profiles 表)  │
│  ├── 长期记忆：PostgreSQL + pgvector 扩展     │
│  │              或外部向量数据库                │
│  └── 记忆服务层：MemoryService                │
└──────────────────────────────────────────────┘
```

**原因**：
1. 灵活可控，不依赖特定平台
2. 代码完全自主，便于定制
3. 成本低（PostgreSQL 免费、pgvector 免费）
4. 团队协作者只需调用 API，无需关心实现细节

---

## 八、实施路线图

### Phase 1: 基础记忆管理（1-2 周）

| 任务 | 负责人 | 预计工时 |
|------|--------|----------|
| 设计并创建 conversations、messages 表 | 后端 | 0.5 天 |
| 实现 MemoryService 基础方法 | 后端 | 1 天 |
| 修改 chat 接口，支持多轮对话 | 后端 | 1 天 |
| 新增 /api/memory/* 接口 | 后端 | 0.5 天 |
| 前端接入对话历史 | 前端 | 1 天 |

### Phase 2: 工作记忆与用户画像（1-2 周）

| 任务 | 负责人 | 预计工时 |
|------|--------|----------|
| 设计用户画像 schema | 记忆管理 | 0.5 天 |
| 实现事实提取 Prompt | 记忆管理 | 1 天 |
| 实现 user_profiles 表和服务 | 后端 | 1 天 |
| 对话后自动提取并更新画像 | 后端 | 0.5 天 |
| 前端展示用户画像 | 前端 | 1 天 |

### Phase 3: 长期记忆与向量检索（2-3 周）

| 任务 | 负责人 | 预计工时 |
|------|--------|----------|
| 安装 pgvector 扩展或部署向量数据库 | 后端 | 1 天 |
| 实现 embedding 生成服务 | 后端 | 1 天 |
| 实现向量检索和记忆存储 | 后端 | 2 天 |
| 设计记忆重要性评分算法 | 记忆管理 | 1 天 |
| 集成到 chat 上下文构建 | 后端 | 1 天 |
| Prompt 评测服务开发 | 记忆管理 | 2 天 |

### Phase 4: 评测体系与优化（持续）

| 任务 | 负责人 | 预计工时 |
|------|--------|----------|
| 构建测试集（100 条） | 记忆管理 | 2 天 |
| 实现 LLM-as-Judge 自动评分 | 记忆管理 | 2 天 |
| A/B 测试框架完善 | 后端 | 1 天 |
| 建立评测报告生成 | 记忆管理 | 1 天 |
| 定期评测与 Prompt 迭代 | 记忆管理 | 持续 |

---

## 九、常见问题与陷阱

### 9.1 记忆爆炸

**问题**：随着对话增加，记忆数据无限增长，导致：
- 上下文超出模型限制
- 检索速度慢
- 存储成本高

**解决**：
1. 设置记忆 TTL（过期时间），自动清理旧记忆
2. 实现记忆压缩/摘要，定期归档
3. 按重要性分级，只保留高重要性记忆

```python
# 定期清理过期记忆
async def cleanup_old_memories(user_id, days=30):
    cutoff = datetime.now() - timedelta(days=days)
    await db.delete(
        "DELETE FROM messages WHERE created_at < $1 AND user_id = $2",
        cutoff, user_id
    )
```

### 9.2 记忆冲突

**问题**：用户信息变化，但旧记忆未更新（如用户换了工作）

**解决**：
1. 为记忆添加 `confidence` 和 `last_verified` 字段
2. 新信息覆盖旧信息时，降低旧信息权重
3. 定期让 LLM 判断哪些记忆需要更新

### 9.3 隐私与安全

**问题**：用户敏感信息存储风险

**解决**：
1. 不存储明确的敏感信息（身份证号、密码等）
2. 用户可删除自己的记忆数据（GDPR 合规）
3. 记忆数据加密存储

```sql
-- 提供记忆删除接口
DELETE /api/memory/user-data?user_id=xxx
```

### 9.4 Prompt 评测的陷阱

**问题**：LLM-as-Judge 评分不一定可靠

**解决**：
1. 始终保留人工抽查环节
2. 使用多个 Judge Prompt 取平均
3. 监控评分与实际用户反馈（点赞/收藏）的相关性

---

## 十、总结

| 维度 | 推荐方案 |
|------|----------|
| **短期记忆** | PostgreSQL messages 表 + 滑动窗口 |
| **工作记忆** | PostgreSQL user_profiles 表 + LLM 提取 |
| **长期记忆** | pgvector 向量检索 或 外部向量数据库 |
| **上下文构建** | 分层混合（画像 + 检索 + 摘要 + 最近消息） |
| **Prompt 评测** | LLM-as-Judge + A/B 测试 + 人工抽查 |
| **团队协作** | Admin API 暴露 + 测试集共享 |

**核心原则**：
1. 从简单开始，逐步迭代
2. 记忆管理是持续优化的过程，不是一次性工作
3. 评测数据驱动决策，不凭感觉改 Prompt
4. 保护用户隐私，提供数据删除能力

---

## 附录：参考资料 & 关联文档

### 参考资料

- [LangChain Memory 文档](https://python.langchain.com/docs/modules/memory/)
- [LangGraph 状态管理](https://langchain-ai.github.io/langgraph/)
- [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview)
- [LLM-as-Judge 论文](https://arxiv.org/abs/2306.05685)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [RAG (Retrieval-Augmented Generation) 最佳实践](https://docs.llamaindex.ai/en/stable/)

### 关联文档

| 文档 | 说明 |
|------|------|
| **[记忆管理架构设计](./memory-architecture.md)** | 架构设计、前沿趋势、团队协作指南 |
| [API 接口文档](./api.md) | 现有 API 接口定义 |
| [部署指南](./deployment-guide.md) | 服务部署与运维 |
