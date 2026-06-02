# kuakua-agent × supermemory MCP 集成方案

> 本文档深度分析 kuakua-agent 当前记忆管理现状，提出基于 supermemory MCP 的语义记忆增强方案，并给出具体的代码改造计划。
>
> 文档状态：分析阶段 | 待评审 | 预计实施周期：2-3 天

---

## 一、现状诊断：当前记忆管理做到了什么程度？

### 1.1 已实现的三层记忆架构

kuakua-agent **已经实现了完整的三层记忆架构**，并非"还没做"。具体包括：

| 层级 | 数据表 | 存储内容 | 生命周期 | 代码位置 |
|------|--------|----------|----------|----------|
| **短期会话记忆** | `sessions` | 对话消息 JSON、场景标签 | 2 小时自动过期 | `app/services/memory_service.py:50-145` |
| **用户偏好记忆** | `user_profiles` | 偏好场景、风格、标签、情绪 | 永久 | `app/services/memory_service.py:147-243` |
| **高光里程碑记忆** | `milestones` | 成就事件、重要性评分 | 永久 | `app/services/memory_service.py:245-316` |

### 1.2 记忆注入流程已打通

当前记忆已经**完全融入生成流程**，以一个完整对话为例：

#### 对话示例流程

**用户**：`user_123` 发送消息 `"今天加班到很晚，好累啊"`，`session_id="sess_abc"`

**Step 1: 获取记忆**（`app/api/chat.py:88-89`）
```python
memory_summary = await _get_user_memory(user_id, session_id, session)
# 调用 MemoryService.get_memory_summary("user_123", "sess_abc")
```

**Step 2: 查询三层记忆**（`app/services/memory_service.py:320-371`）

| 记忆层 | 查询方式 | 返回内容示例 |
|--------|----------|-------------|
| **用户偏好** (`user_profiles`) | `SELECT * FROM user_profiles WHERE user_id="user_123"` | `{"prefer_scene": "career", "prefer_style": "温柔治愈", "user_tags": ["程序员", "熬夜"], "last_emotion": "tired"}` |
| **短期会话** (`sessions`) | `SELECT * FROM sessions WHERE session_id="sess_abc"` | `messages: [{"role":"user","content":"今天项目上线"},{"role":"assistant","content":"你真厉害..."}]` |
| **高光里程碑** (`milestones`) | `SELECT * FROM milestones WHERE user_id="user_123" ORDER BY importance DESC LIMIT 5` | `["完成项目上线", "坚持跑步3km"]` |

**Step 3: 组装 MemorySummary**（`app/models/schemas.py:281-288`）
```python
MemorySummary(
    prefer_scene="career",
    prefer_style="温柔治愈",
    user_tags=["程序员", "熬夜"],
    recent_messages=[{"role":"user","content":"今天项目上线"}, ...],  # 最近3条
    milestones=["完成项目上线", "坚持跑步3km"],
    last_emotion="tired"
)
```

**Step 4: 注入 Prompt**（`app/services/memory_service.py:373-407`）

`format_memory_for_prompt()` 将 MemorySummary 格式化为字符串：
```
【用户记忆】
偏好场景：career
喜欢风格：温柔治愈
用户标签：程序员, 熬夜
当前情绪：tired
最近对话：user: 今天项目上线 | assistant: 你真厉害...
高光时刻：完成项目上线; 坚持跑步3km
```

这个字符串被拼接到 System Prompt 末尾：
```python
# ChatService._inject_memory() (已统一)
full_prompt = f"{system_prompt}\n\n【用户个性化信息】...\n{memory_block}"
```

**Step 5: AI 生成回复**
AI 基于完整 Prompt（含记忆）生成个性化回复。

**Step 6: 双写存储**（`app/api/chat.py:243-310`）

对话结束后，`_update_session_after_chat()` 执行：

```python
# 1. 写入 SQL sessions 表（短期记忆）—— 无需提取，直接原样写入
session_obj.messages = json.dumps([
    {"role": "user", "content": "今天项目上线", "timestamp": "2026-05-08T10:00:00"},
    {"role": "assistant", "content": "你真厉害...", "timestamp": "2026-05-08T10:00:05"},
    {"role": "user", "content": "今天加班到很晚，好累啊", "timestamp": "2026-05-08T22:00:00"},
    {"role": "assistant", "content": "[本次生成的回复]", "timestamp": "2026-05-08T22:00:03"}
], ensure_ascii=False)
await session.commit()

# 2. 创建里程碑 —— 不是请求模型提取，而是关键词规则匹配
# 底层逻辑：achievement_keywords = ["完成", "达成", "通过", "拿到", ...]
#           has_achievement = any(kw in content for kw in achievement_keywords)
# 用户说"今天加班到很晚" → 无匹配关键词 → 不创建
# 用户说"我完成了项目上线" → 匹配"完成" → 截取前200字符 → 写入 milestones 表
await memory_service.extract_and_add_milestone("user_123", "今天加班到很晚，好累啊")
```

**关键代码位置**：

- `app/api/chat.py:88-89` - 每次聊天前获取记忆汇总
- `app/api/chat.py:91-95` - 将记忆注入到生成流程
- `app/api/chat.py:243-310` - 聊天后更新会话并提取里程碑
- `app/services/memory_service.py:320-371` - 三层记忆查询与组装
- `app/services/memory_service.py:373-407` - 记忆格式化为 Prompt 字符串
- `app/models/schemas.py:281-288` - MemorySummary 数据模型

### 1.3 当前架构的局限性

尽管基础架构已完整，但存在以下**关键短板**：

| 问题 | 现状 | 影响 |
|------|------|------|
| **无语义检索能力** | 记忆基于精确字段匹配（`user_id`、`session_id`） | 无法根据"用户当前情绪"语义检索"过去类似情绪时的对话" |
| **非结构化记忆缺失** | 只能存储预定义字段（场景、风格、标签） | 用户说"我最近总是失眠"这类非结构化信息无法有效存储和检索 |
| **跨会话关联弱** | 仅取最近 3 条消息 | 无法关联"上周用户提到加班"与"今天用户说累" |
| **记忆无权重衰减** | 所有里程碑同等重要 | 早期记忆和近期记忆无区分，可能召回过时信息 |
| **无记忆去重/合并** | 相同信息多次存储 | 用户多次提到"我是程序员"会存储多条重复记录 |

### 1.4 核心结论

> **当前记忆管理已完成 70%**：结构化记忆（偏好、会话、里程碑）已落地并运行。
>
> **缺失的 30% 是语义记忆层**：需要引入向量语义存储，实现非结构化记忆的语义检索、关联和去重。

---

## 二、supermemory MCP 能力分析

### 2.1 supermemory 是什么？

supermemory 是一个基于 **mem0** 的语义记忆 MCP Server，提供：

> **什么是 mem0？**
> mem0 是一个开源的**智能记忆层**，专为 AI Agent 设计。它的核心能力是：
> 1. **向量嵌入**：将文本转为高维向量，实现语义理解
> 2. **语义检索**：基于向量相似度搜索，而非关键词匹配
> 3. **自动去重**：自动识别并合并重复或相似的记忆内容
> 4. **自适应学习**：根据用户交互不断优化记忆权重
>
> 简单说：mem0 让 AI 能够"理解"记忆的含义，而不是死记硬背。

| 工具 | 功能 | 适用场景 |
|------|------|----------|
| `add_memory` | 添加记忆（自动提炼、去重） | 存储用户对话、偏好、事件 |
| `search_memory` | 语义搜索记忆 | 根据当前上下文检索相关历史 |
| `update_memory` | 更新已有记忆 | 修正或补充已有记忆 |
| `delete_memory` | 删除记忆 | 清理过期或错误记忆 |

**核心优势**：
- **语义理解**：基于向量相似度，不是关键词匹配
- **自动去重**：mem0 会自动提炼并合并重复内容
- **用户隔离**：通过 `user_id` 隔离不同用户数据
- **元数据支持**：可附加 JSON 元数据（场景、情绪、来源等）

### 2.2 supermemory 与当前架构的关系

```
┌─────────────────────────────────────────────────────────────┐
│                    记忆金字塔（四层）                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: supermemory 语义记忆（新增）                        │
│  ├─ 非结构化对话内容                                          │
│  ├─ 语义关联检索                                              │
│  ├─ 自动去重/提炼                                             │
│  └─ 向量相似度匹配                                            │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: milestones 高光里程碑（已有）                       │
│  ├─ 结构化成就事件                                            │
│  └─ 重要性评分 + 关键词匹配                                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: user_profiles 用户偏好（已有）                      │
│  ├─ 结构化偏好字段（场景、风格、标签）                         │
│  └─ 精确查询                                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: sessions 短期会话（已有）                           │
│  ├─ 最近对话上下文                                            │
│  └─ 2 小时 TTL                                               │
└─────────────────────────────────────────────────────────────┘
```

**定位**：supermemory 作为**第四层语义记忆**，与现有三层**互补而非替代**。

---

## 三、集成方案设计

### 3.1 设计原则

1. **不破坏现有架构**：已有三层记忆保持不动，supermemory 作为增强层
2. **降级容错**：supermemory 服务不可用时，回退到现有三层记忆
3. **最小侵入**：仅修改 `MemoryService` 和 `chat.py`，其他模块不受影响
4. **渐进实施**：先实现存储和检索，再优化去重和关联

### 3.2 数据流设计（含双写存储详解）

```
用户请求
   │
   ▼
┌─────────────────────────────────────┐
│  1. 获取本地记忆（SQL 三层）         │
│     - user_profiles（偏好）          │
│     - sessions（最近 3 条）          │
│     - milestones（高光）             │
└─────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────┐
│  2. 获取语义记忆（supermemory）      │
│     - 基于用户当前输入语义搜索       │
│     - 返回最相关的 N 条历史记忆      │
└─────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────┐
│  3. 合并注入 Prompt                  │
│     - 结构化记忆（原有）→ 用户画像   │
│     - 语义记忆（新增）→ 相关历史     │
└─────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────┐
│  4. AI 生成回复                      │
└─────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────┐
│  5. 双写存储                         │
│     ├─ SQL: sessions（短期记忆）     │
│     ├─ SQL: milestones（成就提取）   │
│     └─ supermemory: 语义向量（新增） │
└─────────────────────────────────────┘
```

#### 双写存储详解

**什么是双写存储？**

双写存储 = 一次对话结束后，**同时写入两个存储系统**：
1. **SQL 数据库**（已有）：存储结构化数据（会话消息、里程碑）
2. **supermemory**（新增）：存储语义向量（完整对话内容）

**为什么要双写？**

| 存储系统 | 存储内容 | 用途 | 查询方式 |
|----------|----------|------|----------|
| **SQL** | 结构化字段（场景、标签、情绪） | 精确查询用户偏好 | `WHERE user_id = ?` |
| **supermemory** | 非结构化文本（完整对话） | 语义检索相关历史 | 向量相似度搜索 |

两者互补：SQL 负责"精确知道用户偏好什么场景"，supermemory 负责"理解用户过去说过什么相关的话"。

**当前已有双写（SQL 内部）**：

以用户 `"user_123"` 发送 `"今天加班到很晚"` 为例：

```python
# app/api/chat.py:243-310 _update_session_after_chat()
async def _update_session_after_chat(user_id, session_id, request, response):
    # 写入 1: sessions 表（短期记忆）
    session_obj.messages = json.dumps([
        {"role": "user", "content": "今天加班到很晚", "timestamp": "..."},
        {"role": "assistant", "content": "[AI回复]", "timestamp": "..."}
    ])
    await session.commit()  # → SQLite/PostgreSQL
    
    # 写入 2: milestones 表（如果检测到成就关键词）
    await memory_service.extract_and_add_milestone(user_id, request.text)
    # → INSERT INTO milestones (user_id, content, ...)
```

**新增 supermemory 双写后**：

```python
# 在 _update_session_after_chat() 中增加第 3 个写入
async def _update_session_after_chat(user_id, session_id, request, response):
    # 写入 1: SQL sessions 表（已有）
    ...
    
    # 写入 2: SQL milestones 表（已有）
    ...
    
    # 写入 3: supermemory 语义记忆（新增）
    await sm_client.add_memory(
        content="用户说：今天加班到很晚\nAI回复：[生成的回复]",
        user_id="user_123",
        metadata={
            "type": "chat",
            "scene": "career",
            "emotion": "tired",
            "timestamp": "2026-05-08T22:00:00Z"
        }
    )
    # → supermemory 自动转为向量存储
```

**双写的容错设计**：

```python
# 核心原则：supermemory 写入失败不能影响 SQL 写入

# 方式 1: 异步写入（不阻塞主流程）
asyncio.create_task(
    save_to_supermemory(user_id, request, response)
)

# 方式 2: try-catch 静默失败
try:
    await sm_client.add_memory(...)
except Exception:
    logger.warning("supermemory 写入失败，已跳过")
    # 不抛异常，不影响 SQL 写入
```

### 3.3 MCP 调用模式设计（关键决策）

#### 为什么不需要模型自主调用？

MCP 工具调用存在两种模式，需根据工具特性选择：

| 调用模式 | 机制 | 适用场景 | supermemory 是否适用 |
|----------|------|----------|---------------------|
| **模型自主决策**（Function Calling） | 模型根据上下文自己决定"是否调用、调用哪个、传什么参数" | **决策型工具**：查天气、算数学、搜资料、调 API | ❌ 不适用 |
| **代码编排调用**（Hard-coded / Orchestrated） | 开发者在代码的固定节点直接调用，不经过模型决策 | **确定性流程**：每次对话前读记忆、对话后存记忆、记录日志 | ✅ **适用** |

supermemory 属于**确定性基础设施**，不是决策型工具：

- `search_memory`：**每次对话前必须执行**（获取上下文记忆）→ 无决策空间
- `add_memory`：**每次对话后必须执行**（保存对话记录）→ 无决策空间

类比：你不会让模型决定"是否连接数据库"，记忆管理同理。

#### 在 Chat 流程的哪个节点调用？

在 `app/api/chat.py` 的**两个固定节点**直接硬编码调用：

```
用户请求
    │
    ▼
┌─────────────────────────────┐
│ 节点 A：对话开始前           │
│ _get_user_memory()          │
│ ├── 查询 SQL 三层记忆（已有）│
│ └── 调用 search_memory（新增）│ ← 硬编码，无需模型决策
└─────────────────────────────┘
    │
    ▼
AI 生成回复
    │
    ▼
┌─────────────────────────────┐
│ 节点 B：对话结束后           │
│ _update_session_after_chat() │
│ ├── 写入 SQL sessions（已有）│
│ ├── 提取 milestones（已有）  │
│ └── 调用 add_memory（新增）  │ ← 硬编码，无需模型决策
└─────────────────────────────┘
```

#### 这是否是 Agent 最佳实践？

**对于记忆管理类 MCP，代码编排调用是业界最佳实践。**

依据：

| 维度 | 模型自主调用 | 代码编排调用（推荐） |
|------|-------------|---------------------|
| **延迟** | 增加一轮模型决策，延迟 +200-500ms | 直接调用，无额外延迟 |
| **Token 消耗** | 需将工具描述注入 Prompt，消耗 token | 无需注入工具描述 |
| **可靠性** | 模型可能"忘记"调用或调错参数 | 100% 执行，参数由代码精确控制 |
| **可观测性** | 难以追踪模型决策逻辑 | 标准日志，易于监控和调试 |
| **成本** | 更高（多轮交互） | 更低（单次 HTTP 调用） |

**反例**（需要模型自主决策的场景）：
- 用户问"北京明天天气怎么样"→ 模型需要**决定**是否调用天气工具
- 用户问"3的平方根是多少"→ 模型需要**决定**是否调用计算器

这些场景有明确的"有时需要、有时不需要"的决策空间，才适合模型自主调用。

#### 调用方式：直接函数调用 vs 装饰器 vs 依赖注入 vs 中间件

业界常见的四种 MCP 调用方式对比：

| 调用方式 | 机制 | 适用场景 | 记忆管理是否适用 |
|----------|------|----------|-----------------|
| **直接函数调用**（当前方案） | 在业务函数内部直接 `await mcp.call(...)` | **确定性流程**：需要精确控制参数和时机 | ✅ **适用** |
| **依赖注入**（FastAPI Depends） | `mcp_client = Depends(get_mcp_client)` | **服务对象获取**：数据库连接、配置对象 | ⚠️ 可选（MCP 是全局单例，不需要每次请求注入） |
| **装饰器模式**（Interceptor） | `@with_memory` / `@before_chat` / `@after_chat` | **横切关注点**：日志、权限、缓存、重试 | ❌ 不适用 |
| **中间件模式**（Middleware） | 在请求/响应管道中统一拦截处理 | **请求前后统一操作**：CORS、认证、计时 | ❌ 不适用 |

**为什么记忆管理不适合装饰器和中间件？**

```python
# ❌ 装饰器模式：参数不可控，无法构建语义查询
@with_memory  # 装饰器无法知道要用什么 query 搜索
async def chat(request: ChatRequest):
    ...

# ❌ 中间件模式：无法区分 search（请求前）和 add（响应后）
@app.middleware("http")
async def memory_middleware(request, call_next):
    # 这里无法获取业务参数构建 search query
    response = await call_next(request)
    # 这里无法获取 AI 生成的 response.content
    ...

# ✅ 直接函数调用：精确控制参数和时机
async def _get_user_memory(user_id, session_id, session):
    # 节点 A：请求前，基于用户画像构建 query
    query = f"{profile.prefer_scene} {profile.last_emotion}"
    result = await mcp_client.call("search_memory", query=query, user_id=user_id, top_k=3)
    ...

async def _update_session_after_chat(user_id, session_id, request, response):
    # 节点 B：响应后，写入完整对话
    await mcp_client.call(
        "add_memory",
        content=f"用户：{request.text}\nAI：{response.content}",
        user_id=user_id,
        metadata={"scene": request.scene}
    )
```

**核心原因**：

1. **参数依赖业务上下文**：`search_memory` 的 `query` 需要从 `user_profile` 动态构建（标签+场景+情绪），装饰器和中间件无法获取这些业务参数
2. **调用点分散**：`search` 在请求前、`add` 在响应后，中间件只能处理单一入口/出口
3. **记忆是业务逻辑，不是横切关注点**：日志、权限、缓存才是横切关注点，适合装饰器/中间件；记忆注入直接参与 Prompt 构建，是业务核心逻辑

**业界最佳实践参考**：

- **OpenAI Assistants API**：记忆存储在 `run` 生命周期中直接调用（`thread.messages.create`），非装饰器
- **LangChain Memory**：在 `Runnable` 的 `invoke()` 方法内直接读写记忆（`memory.load_memory_variables` / `memory.save_context`），非装饰器
- **CrewAI Memory**：在 `Agent.execute_task()` 方法内直接调用记忆层（`self.memory.search` / `self.memory.store`），非装饰器

**结论**：记忆管理类 MCP 调用应采用**直接函数调用**，在业务代码的精确节点同步/异步调用，这是业界通用做法。

---

### 3.4 模块改造计划

#### 改造 1：新增 MCPClient 封装（基于 `mcp` SDK）

**新建文件**：`app/core/mcp_client.py`

> **为什么用 `mcp` SDK 而非裸调 HTTP？**
>
> | 维度 | 裸调 HTTP (`httpx`) | MCP SDK Client (`mcp.client.sse`) |
> |------|---------------------|-----------------------------------|
> | **协议合规** | 需手动处理 JSON-RPC、initialize 握手 | SDK 自动完成 MCP 协议握手 |
> | **工具发现** | 硬编码工具名 | 动态发现可用工具，兼容接口变更 |
> | **连接管理** | 需手动维护 SSE 长连接 | 自动心跳、断线重连 |
> | **类型安全** | 无 | `CallToolResult` 类型校验 |
> | **扩展性** | 每个 Server 需独立封装 | 统一接口，复用同一 Client 连接多个 Server |
>
> 安装依赖：`pip install mcp>=1.6.0`

**职责**：
- 通过 `mcp.client.sse` 建立 SSE 长连接
- 封装 MCP 协议握手（`initialize` → `list_tools` → `call_tool`）
- 对外暴露 `call(tool_name, **kwargs)` 统一调用接口
- 实现连接生命周期管理（启动连接、关闭连接、超时降级）
- 静默失败：服务不可用时返回 `None`，不抛异常

**关键设计**：

```python
import asyncio
from contextlib import asynccontextmanager
from mcp.client.sse import sse_client
from mcp import ClientSession
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MCPClient:
    """
    基于官方 mcp SDK 的 MCP Client 封装
    
    支持 SSE 长连接，自动协议握手，工具动态发现。
    设计为单例，由 FastAPI lifespan 统一管理生命周期。
    """
    
    def __init__(self):
        self.url = settings.supermemory_url          # e.g. http://106.55.151.27/sse
        self.headers = settings.supermemory_headers   # e.g. {"token": "linzz"}
        self.timeout = settings.supermemory_timeout   # e.g. 5.0
        self.enabled = settings.supermemory_enabled   # e.g. True
        
        self._session: ClientSession | None = None
        self._client_ctx = None
    
    async def connect(self):
        """建立 SSE 连接并完成 MCP 协议握手（应用启动时调用）"""
        if not self.enabled:
            logger.info("supermemory MCP 已禁用，跳过连接")
            return
        
        try:
            self._client_ctx = sse_client(self.url, headers=self.headers)
            read, write = await self._client_ctx.__aenter__()
            self._session = ClientSession(read, write)
            
            # MCP 协议握手：initialize → list_tools
            await self._session.initialize()
            tools = await self._session.list_tools()
            logger.info(f"MCP 连接已建立 | 可用工具: {[t.name for t in tools]}")
        except Exception as e:
            logger.error(f"MCP 连接失败: {e}")
            self._session = None
    
    async def call(self, tool_name: str, **kwargs) -> dict | None:
        """
        调用 MCP 工具，带超时和静默降级
        
        Args:
            tool_name: MCP 工具名（如 add_memory、search_memory）
            **kwargs: 工具参数
        
        Returns:
            dict: 工具返回结果（已解析 content）
            None: 调用失败或降级时
        """
        if not self.enabled or not self._session:
            return None
        
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments=kwargs),
                timeout=self.timeout
            )
            
            # 解析 CallToolResult → dict
            # result.content 是 list[TextContent | ImageContent]
            if result.content and hasattr(result.content[0], "text"):
                import json
                return json.loads(result.content[0].text)
            return {}
            
        except asyncio.TimeoutError:
            logger.warning(f"MCP 调用超时 [{tool_name}]")
            return None
        except Exception as e:
            logger.warning(f"MCP 调用失败 [{tool_name}]: {e}")
            return None
    
    async def disconnect(self):
        """关闭 SSE 连接（应用关闭时调用）"""
        if self._client_ctx:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_ctx = None
            self._session = None
            logger.info("MCP 连接已关闭")


# 全局单例（由 lifespan 管理生命周期）
mcp_client = MCPClient()
```

#### 改造 1.5：FastAPI 生命周期管理

**修改文件**：`app/main.py`

**在 lifespan 中集成 MCP 连接**：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.mcp_client import mcp_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== 启动阶段 =====
    await init_database()          # 原有：初始化数据库
    await mcp_client.connect()     # 新增：连接 supermemory MCP Server
    
    yield
    
    # ===== 关闭阶段 =====
    await mcp_client.disconnect()  # 新增：断开 MCP 连接
    await close_database()         # 原有：关闭数据库

app = FastAPI(lifespan=lifespan)
```

**最佳实践依据**：
- SSE 是**长连接**，应在应用启动时建立、关闭时释放，避免每次请求都新建连接
- 单例模式确保全应用共享同一 `ClientSession`，减少连接开销
- `lifespan` 管理保证连接状态与 FastAPI 应用生命周期同步

#### 改造 2：扩展配置

**修改文件**：`app/config.py`

**新增配置项**：
```python
from typing import Optional, Dict, Any

# supermemory MCP Server 配置
supermemory_url: str = Field(
    default="http://106.55.151.27/sse",
    description="supermemory MCP Server SSE 地址"
)
supermemory_headers: Optional[Dict[str, Any]] = Field(
    default=None,
    description="SSE 连接附加请求头（如 token 鉴权）"
)
supermemory_enabled: bool = Field(
    default=True,
    description="是否启用 supermemory MCP"
)
supermemory_timeout: float = Field(
    default=5.0,
    description="单次 MCP 工具调用超时（秒）"
)
supermemory_top_k: int = Field(
    default=3,
    description="语义搜索返回数量"
)
```

**修改文件**：`.env` 和 `.env.example`
```bash
# supermemory MCP 配置（与 mcp.json 保持一致）
SUPERMEMORY_URL=http://106.55.151.27/sse
# SSE 鉴权头，JSON 格式（与 mcp.json headers 对应）
SUPERMEMORY_HEADERS={"token":"linzz"}
SUPERMEMORY_ENABLED=true
SUPERMEMORY_TIMEOUT=5.0
SUPERMEMORY_TOP_K=3
```

**修改文件**：`pyproject.toml` / `requirements.txt`
```toml
# pyproject.toml
[tool.poetry.dependencies]
mcp = "^1.6.0"   # 官方 MCP Python SDK，支持 SSE Client

# 或 requirements.txt
mcp>=1.6.0
```

#### 改造 3：MemoryService 集成语义记忆

**修改文件**：`app/services/memory_service.py`

**改造点**：

1. **构造函数注入 MCPClient**
   ```python
   from app.core.mcp_client import mcp_client

   class MemoryService:
       def __init__(self, session: AsyncSession, mcp: MCPClient = None):
           self.session = session
           self.mcp = mcp or mcp_client  # 使用全局单例（lifespan 已初始化）
   ```

2. **get_memory_summary() 增加语义记忆检索**
   ```python
   async def get_memory_summary(self, user_id: str, session_id: Optional[str] = None) -> MemorySummary:
       # 原有逻辑：获取 SQL 三层记忆
       profile = await self.get_user_profile(user_id)
       recent_messages = ...
       milestones = ...
       
       # 新增：从 supermemory 获取语义相关记忆
       semantic_memories = await self._get_semantic_memories(user_id)
       
       return MemorySummary(
           # ... 原有字段
           semantic_memories=semantic_memories  # 新增字段
       )
   ```

3. **新增语义记忆检索方法**
   ```python
   async def _get_semantic_memories(self, user_id: str) -> List[str]:
       """基于用户画像构建查询，通过 MCP 调用 search_memory"""
       if not self.mcp:  # MCP 未连接或已禁用
           return []
       
       profile = await self.get_user_profile(user_id)
       if not profile:
           return []
       
       # 构建语义查询：结合用户标签 + 偏好场景 + 最近情绪
       query_parts = []
       if profile.user_tags:
           tags = json.loads(profile.user_tags)
           query_parts.extend(tags[:3])
       if profile.prefer_scene:
           query_parts.append(profile.prefer_scene)
       if profile.last_emotion:
           query_parts.append(profile.last_emotion)
       
       if not query_parts:
           return []
       
       query = " ".join(query_parts)
       
       # 通过 MCP SDK 调用 search_memory 工具
       result = await self.mcp.call(
           "search_memory",
           query=query,
           user_id=user_id,
           top_k=settings.supermemory_top_k
       )
       
       if not result:
           return []
       
       # 解析返回结果
       return [item.get("content", "") for item in result.get("results", [])]
   ```

4. **新增保存对话到 supermemory 方法**
   ```python
   async def save_chat_to_supermemory(
       self, user_id: str, user_message: str, 
       ai_response: str, scene: str = "general", emotion: Optional[str] = None
   ):
       """通过 MCP 调用 add_memory 将对话保存到语义记忆"""
       if not self.mcp:  # MCP 未连接或已禁用
           return
       
       content = f"用户说：{user_message}\nAI回复：{ai_response}"
       
       # 通过 MCP SDK 调用 add_memory 工具（静默降级由 MCPClient.call 内部处理）
       await self.mcp.call(
           "add_memory",
           content=content,
           user_id=user_id,
           metadata={
               "type": "chat",
               "scene": scene,
               "emotion": emotion,
               "timestamp": datetime.utcnow().isoformat()
           }
       )
   ```

#### 改造 4：Chat API 双写逻辑

**修改文件**：`app/api/chat.py`

**改造点**：

1. **_get_user_memory() 复用全局 MCPClient**
   ```python
   from app.core.mcp_client import mcp_client

   async def _get_user_memory(user_id, session_id, session):
       try:
           # 直接传入 lifespan 管理的全局 MCPClient 单例
           memory_service = MemoryService(session, mcp_client)
           return await memory_service.get_memory_summary(user_id, session_id)
       except Exception:
           return None
   ```

2. **_update_session_after_chat() 通过 MCP 写入 supermemory**
   ```python
   from app.core.mcp_client import mcp_client

   async def _update_session_after_chat(user_id, session_id, request, response):
       # 原有逻辑：更新 SQL sessions 表
       ...
       
       # 新增：通过 MCP 保存到 supermemory
       # 降级逻辑已内置于 MCPClient.call()，无需外层 try-catch
       memory_service = MemoryService(session, mcp_client)
       await memory_service.save_chat_to_supermemory(
           user_id=user_id,
           user_message=request.text,
           ai_response=response.content,
           scene=request.scene
       )
   ```

3. **_inject_memory_to_prompt() 增加语义记忆注入**
   ```python
   def _inject_memory_to_prompt(system_prompt, memory):
       # 原有逻辑：注入结构化记忆
       parts = []
       if memory.prefer_scene:
           parts.append(f"- 偏好场景：{memory.prefer_scene}")
       ...
       
       # 新增：注入语义记忆
       if memory.semantic_memories:
           semantic_str = "; ".join(memory.semantic_memories[:3])
           parts.append(f"- 相关记忆：{semantic_str}")
       
       ...
   ```

#### 改造 5：MemorySummary Schema 扩展

**修改文件**：`app/models/schemas.py`

**新增字段**：
```python
class MemorySummary(BaseModel):
    # 原有字段
    prefer_scene: Optional[str] = None
    prefer_style: Optional[str] = None
    user_tags: list[str] = []
    recent_messages: list[dict] = []
    milestones: list[str] = []
    last_emotion: Optional[str] = None
    
    # 新增字段
    semantic_memories: list[str] = []  # supermemory 检索到的语义记忆
```

#### 改造 6：Prompt 模板增强

**修改文件**：`app/prompts/templates.py`

**在 system prompt 中增加语义记忆使用说明**：
```python
# 在原有 prompt 基础上增加：
"""
【相关历史记忆】（如果有以下相关记忆，请结合使用，让夸夸更贴心）
{semantic_memories}

注意：
- 如果用户提到的事情与历史记忆相关，可以自然地带入
- 不要生硬地复述记忆，而是融入语气中
- 如果记忆已经过时（如用户已改变状态），以当前输入为准
"""
```

---

## 四、API 接口影响分析

### 4.1 现有接口行为变化

| 接口 | 变化 | 影响 |
|------|------|------|
| `POST /api/chat` | 生成前增加语义记忆检索 | 回复更关联历史 |
| `POST /api/chat/stream` | 同上 | 同上 |
| `GET /api/chat/greeting` | 同上 | 主动问候更个性化 |
| `POST /api/favorites` | 收藏时同步到 supermemory | 收藏内容可被语义检索 |

### 4.2 新增 Admin 接口（可选）

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/admin/supermemory/status` | GET | 查看 supermemory 连接状态 |
| `/api/admin/supermemory/search` | POST | 手动测试语义搜索 |
| `/api/admin/supermemory/sync` | POST | 手动同步 SQL 记忆到 supermemory |

---

## 五、实施路线图

### Phase 1：基础集成（1 天）

| 任务 | 文件 | 工时 |
|------|------|------|
| 创建 MCPClient 封装（基于 mcp SDK） | `app/core/mcp_client.py` | 2h |
| 扩展配置（config.py + .env） | `app/config.py`, `.env.example` | 30min |
| MemoryService 集成语义检索 | `app/services/memory_service.py` | 2h |
| Chat API 双写逻辑 | `app/api/chat.py` | 1h |
| Schema 扩展 | `app/models/schemas.py` | 30min |

### Phase 2：优化打磨（1 天）

| 任务 | 文件 | 工时 |
|------|------|------|
| Prompt 模板增强（语义记忆注入格式） | `app/prompts/templates.py` | 1h |
| 降级容错优化（网络超时处理） | `app/core/mcp_client.py` | 1h |
| 日志和监控（记忆命中率追踪） | `app/core/logging.py` | 1h |
| 单元测试 | `tests/` | 2h |

### Phase 3：高级特性（可选，1 天）

| 任务 | 说明 |
|------|------|
| 收藏同步到语义记忆 | 用户收藏时自动 add_memory |
| 里程碑自动语义化 | 提取里程碑时同步到 supermemory |
| 记忆去重策略 | 利用 mem0 自动去重能力 |
| Admin 管理接口 | 查看 supermemory 状态、手动同步 |

---

## 六、风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| supermemory 服务不可用 | 中 | 高 | **降级设计**：所有调用 try-catch，失败时返回空结果，不影响主流程 |
| 网络延迟增加响应时间 | 中 | 中 | **短超时**：设置 3-5 秒超时；**异步写入**：检索同步、存储异步 |
| 语义记忆召回质量差 | 中 | 中 | **A/B 测试**：对比带/不带语义记忆的效果；**调参**：调整 top_k 和查询构建策略 |
| 记忆数据膨胀 | 低 | 中 | **定期清理**：利用 supermemory 的去重能力；**TTL 策略**：设置记忆过期时间 |
| 隐私合规风险 | 低 | 高 | **用户隔离**：严格按 user_id 隔离；**删除接口**：提供用户数据删除能力 |

---

## 七、最佳实践建议

### 7.1 查询构建策略

语义搜索的质量取决于查询构建。建议：

```python
# 构建语义查询时，优先使用高信息密度字段
query_parts = []

# 1. 用户标签（最高优先级）
if profile.user_tags:
    tags = json.loads(profile.user_tags)
    query_parts.extend(tags[:3])  # 最多 3 个标签

# 2. 当前情绪（次优先级）
if profile.last_emotion:
    query_parts.append(profile.last_emotion)

# 3. 偏好场景（辅助）
if profile.prefer_scene:
    query_parts.append(profile.prefer_scene)

query = " ".join(query_parts)
```

### 7.2 元数据设计

存储记忆时附加丰富元数据，便于后续过滤：

```python
metadata = {
    "type": "chat",           # chat / favorite / milestone / profile_update
    "scene": "career",        # 场景标签
    "emotion": "tired",       # 情绪标签
    "source": "user_input",   # 来源
    "timestamp": "2026-05-08T16:00:00Z",
    "importance": 3,          # 重要性 1-5
}
```

### 7.3 降级策略

```python
# 核心原则：supermemory 是"锦上添花"，不是"不可或缺"

async def get_semantic_memories(user_id: str) -> List[str]:
    try:
        # 短超时，快速失败
        return await asyncio.wait_for(
            _fetch_from_supermemory(user_id), 
            timeout=3.0
        )
    except Exception:
        # 任何错误都返回空列表，不影响主流程
        logger.debug(f"supermemory 检索失败，已降级 | user_id={user_id}")
        return []
```

### 7.4 监控指标

建议追踪以下指标：

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `supermemory_latency_ms` | 单次调用延迟 | > 5000ms |
| `supermemory_error_rate` | 错误率 | > 5% |
| `semantic_memory_hit_rate` | 语义记忆命中率 | < 30%（可能查询构建有问题） |
| `memory_injection_tokens` | 注入记忆增加的 token 数 | > 500（可能记忆过长） |

---

## 八、总结

### 核心结论

1. **当前记忆管理已完成 70%**：三层结构化记忆（会话、偏好、里程碑）已落地并运行良好
2. **supermemory 补充剩余的 30%**：提供语义检索、非结构化记忆存储、自动去重能力
3. **集成方案是"增强层模式"**：不改变现有架构，supermemory 作为第四层语义记忆
4. **实施周期 2-3 天**：Phase 1（1天）+ Phase 2（1天）+ 测试优化（0.5-1天）

### 预期效果

| 指标 | 当前 | 集成后 |
|------|------|--------|
| 记忆类型 | 结构化（字段固定） | 结构化 + 非结构化（语义） |
| 检索方式 | 精确匹配 | 精确匹配 + 语义相似度 |
| 跨会话关联 | 弱（仅最近3条） | 强（语义关联） |
| 个性化程度 | 基于标签 | 基于标签 + 语义上下文 |
| 记忆去重 | 无 | 自动（mem0 能力） |

### 下一步行动

1. **评审本方案**：确认是否采纳增强层模式
2. **确认 supermemory 服务状态**：确保 `http://10.31.25.63:8000` 可访问
3. **实施 Phase 1**：按路线图逐步改造
4. **A/B 测试**：对比集成前后的生成效果

---

## 附录：相关文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 记忆管理方案 | `docs/memory_management.md` | 产品层面的三层记忆设计 |
| 记忆架构参考 | `docs/ref-memory-architecture.md` | 四层架构设计、团队协作 |
| 记忆管理详解 | `docs/ref-memory-management.md` | 全生命周期闭环、Prompt 评测 |
| supermemory 技能 | `.codebuddy/rules/tcb/rules/supermemory.mdc` | MCP 工具使用规范 |
| MCP 配置 | `~/.codebuddy/mcp.json` | supermemory MCP Server 配置 |

---

*文档版本：v1.0 | 创建时间：2026-05-08 | 作者：CodeBuddy*
