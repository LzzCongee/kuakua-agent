# 全链路超时与韧性设计：AI Agent 产品方法论

> 本文档沉淀了 kuakua-agent 项目超时管理、取消机制、降级策略背后的设计方法论，
> 基于对 OpenAI、Anthropic、LangChain、AutoGen、Dify、FastGPT 等主流产品的源码和文档研究。

---

## 核心问题

AI Agent 面临的超时挑战与传统 Web 服务不同：

| 挑战 | 原因 |
|------|------|
| 响应时间不可预测 | LLM 生成时间从 1 秒到数分钟不等，取决于模型大小、token 数、负载 |
| 流式连接易被中间层断开 | Nginx/Cloudflare/负载均衡器默认 60s 超时 |
| 视觉模型显著更慢 | 72B 视觉模型处理图片可能需要 30-60 秒 |
| 客户端可能随时断开 | 用户关闭页面、切换 app、网络中断 |
| 部分响应仍有价值 | 用户可能只想要前几句话，不一定要完整回答 |

---

## 超时分层架构

业界共识：超时不是单一配置，而是贯穿整个请求链路的分层防护。

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: 用户操作层（前端）                                │
│  - AbortController 取消请求                               │
│  - 停止按钮保留已接收内容                                   │
├─────────────────────────────────────────────────────────┤
│  Layer 4: API 网关 / SSE 连接层                           │
│  - SSE 心跳 keepalive（每 15s）                           │
│  - 连接断开检测                                            │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 应用业务层                                      │
│  - asyncio.timeout() 包裹整个生成操作                      │
│  - 超时后返回 error 事件而非静默挂起                        │
├─────────────────────────────────────────────────────────┤
│  Layer 2: SDK / Provider 层                               │
│  - httpx.Timeout（connect + read + write + pool）         │
│  - 自动重试（指数退避，429/5xx 触发）                       │
├─────────────────────────────────────────────────────────┤
│  Layer 1: HTTP 传输层                                     │
│  - TCP keepalive                                          │
│  - 连接池限制                                              │
└─────────────────────────────────────────────────────────┘
```

---

## 各产品实现对比

### 1. OpenAI（ChatGPT / API）

**SDK 超时配置**（源码验证自 `.venv/Lib/site-packages/openai/_constants.py`）：

```python
DEFAULT_TIMEOUT = httpx.Timeout(timeout=600, connect=5.0)  # 10 分钟总超时，5 秒连接超时
DEFAULT_MAX_RETRIES = 2  # 最多重试 2 次（共 3 次尝试）
INITIAL_RETRY_DELAY = 0.5  # 首次重试等待 0.5 秒
MAX_RETRY_DELAY = 8.0  # 最大重试间隔 8 秒
```

**重试逻辑**（源码验证自 `_base_client.py:773-806`）：
- 触发条件：HTTP 408、429、500+
- 退避策略：`min(0.5 * 2^attempt, 8.0)` 秒，加 25% 随机抖动
- 尊重服务端 `retry-after` 和 `x-should-retry` 响应头

**取消机制**：
- 前端：`AbortController` + `fetch({ signal })`
- Python：`Stream.close()` 关闭底层 httpx 响应
- 服务端检测连接断开后停止生成

**目的与匹配度**：
| 措施 | 目的 | 是否匹配 |
|------|------|----------|
| 600s 超时 | 防止无限挂起 | 匹配，但对用户交互场景太长 |
| 2 次自动重试 | 应对临时性故障 | 匹配，429/5xx 确实可能恢复 |
| AbortController | 用户主动取消 | 完全匹配 |

**参考源码**：
- `openai/_constants.py` — 超时常量定义
- `openai/_base_client.py:773-806` — 重试逻辑实现
- `openai/_base_client.py:1010-1023` — 超时异常处理
- `openai/_streaming.py` — 流式取消和清理

---

### 2. Anthropic（Claude）

**SDK 设计**（基于同一 Stainless 生成框架）：

与 OpenAI SDK 结构相同：
- 默认超时：600s，连接超时 5s
- 默认重试：2 次
- 同样使用 `httpx` 作为 HTTP 传输层

**Claude.ai 前端**：
- "Stop" 按钮使用 `AbortController` 取消 SSE 流
- 已渲染的部分文本保留，不回滚
- 中断的消息保存到对话历史

**目的与匹配度**：
| 措施 | 目的 | 是否匹配 |
|------|------|----------|
| 600s 超时 | 与 OpenAI 对齐，兼容长文本生成 | 匹配 |
| Stop 按钮 | 用户控制生成长度 | 完全匹配 |
| 保留中断内容 | 部分回答仍有价值 | 匹配 |

---

### 3. LangChain / LangGraph

**双层超时**：

```python
# Layer 1: LLM 调用超时（传递到底层 SDK）
llm = ChatOpenAI(model="gpt-4", request_timeout=120)

# Layer 2: Agent 执行超时（LangChain 层面）
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    max_execution_time=300,  # 整体执行 5 分钟上限
    max_iterations=15,       # 最多 15 步
)
```

**LangGraph 超时**：
- `recursion_limit`: 控制最大超步数（默认 25）
- `step_timeout`（仅 LangGraph Platform）：单节点执行超时
- 开源 SDK 不支持单节点超时，需自行用 `asyncio.wait_for()` 实现

**目的与匹配度**：
| 措施 | 目的 | 是否匹配 |
|------|------|----------|
| LLM 层超时 | 防止单次 API 调用挂起 | 匹配 |
| max_iterations | 防止 Agent 死循环 | 匹配，迭代次数限制 |
| max_execution_time | 防止整体任务超时 | 匹配，时间维度兜底 |

**参考文档**：
- LangChain: `https://python.langchain.com/docs/concepts/chat_models/#timeout`
- LangGraph: `https://langchain-ai.github.io/langgraph/concepts/low_level/#recursion-limit`

---

### 4. AutoGen（Microsoft）

**迭代限制而非时间限制**：

```python
assistant = AssistantAgent(
    name="assistant",
    max_consecutive_auto_reply=5,  # 最多 5 轮自动回复
)
user_proxy = UserProxyAgent(
    name="user_proxy",
    human_input_mode="TERMINATE",  # 需要用户输入时停止
    max_consecutive_auto_reply=10,
)
```

**关键机制**：
- `max_consecutive_auto_reply`: 连续自动回复次数上限
- `is_termination_msg`: 自定义终止消息判断函数
- **没有内置的墙钟超时**（wall-clock timeout）

**目的与匹配度**：
| 措施 | 目的 | 是否匹配 |
|------|------|----------|
| max_consecutive_auto_reply | 防止 Agent 无限循环 | 部分匹配，只限制次数不限制时间 |
| human_input_mode | 人机协作控制 | 匹配 |
| 无墙钟超时 | — | 不匹配，长任务无法中断 |

**参考文档**：
- `https://microsoft.github.io/autogen/docs/reference/agentchat/conversable_agent`

---

### 5. Dify

**运行时层超时**：
- LLM 节点超时通过环境变量配置（`LLM_REQUEST_TIMEOUT`）
- 模型运行时层实现指数退避重试
- 工作流引擎管理整体执行生命周期

**参考文档**：
- `https://docs.dify.ai/guides/workflow/node/llm`

---

### 6. FastGPT

**SSE 心跳保活**：
- 每 15 秒发送 SSE 注释行（`:\n\n`）作为心跳
- 防止 Nginx/Cloudflare 等代理断开空闲连接
- 前端使用 `AbortController` 取消
- 服务端检测连接断开后清理资源

**参考文档**：
- `https://doc.fastgpt.in/docs/development/faq/`
- GitHub: `https://github.com/labring/FastGPT`

---

## 设计决策框架

面对超时问题时，按以下框架决策：

### 第一步：识别超时类型

| 类型 | 表现 | 根因 |
|------|------|------|
| 连接超时 | 请求发出后长时间无响应 | 服务不可达、DNS 解析慢 |
| 读取超时 | 连接建立后数据传输中断 | 模型推理慢、网络抖动 |
| 业务超时 | API 返回但前端仍在等待 | 视觉模型 72B 推理耗时 |
| 用户取消 | 用户主动停止 | 不需要生成完整回答 |

### 第二步：选择对应的超时策略

| 超时类型 | 推荐策略 | 参考值 |
|----------|----------|--------|
| 连接超时 | `httpx.Timeout(connect=10s)` | OpenAI 用 5s |
| 读取超时 | SDK 级别 `timeout=30s` | 用户交互场景 |
| 业务超时 | `asyncio.timeout(60s)` | 视觉模型专用 |
| 用户取消 | `AbortController` + 保留部分文本 | 业界统一做法 |

### 第三步：确定取消后的行为

| 行业实践 | 做法 | 原因 |
|----------|------|------|
| 保留已生成文本 | ChatGPT/Claude/Kimi 都保留 | 部分回答仍有价值 |
| 保存到历史 | 中断消息作为正常 assistant 消息保存 | 保持对话连贯性 |
| 不标记中断状态 | 无产品特殊标记"中断" | 用户不需要知道技术细节 |
| 不自动重试 | 用户手动点"重新生成" | 尊重用户意图 |

---

## kuakua-agent 当前实现

### 超时配置

| 层级 | 位置 | 配置 | 默认值 |
|------|------|------|--------|
| SDK 客户端 | `providers/qwen.py` | `httpx.Timeout(timeout, connect=10.0)` | 30s |
| 多模态业务层 | `api/chat.py` | `asyncio.timeout(multimodal_timeout)` | max(ai_timeout, 60s) |
| 文本流式 | `api/chat.py` | 依赖 SDK 超时 | 30s |
| 前端取消 | `test.html` | `AbortController` | 用户触发 |

### 取消后行为

| 场景 | 行为 |
|------|------|
| 用户点击停止 | AbortController 取消请求，保留已接收文本 |
| 后端超时 | 返回 SSE error 事件，前端显示错误提示 |
| 服务端错误 | 返回 SSE error 事件 |

### 待改进

| 项目 | 当前状态 | 建议 |
|------|----------|------|
| SSE 心跳 | 未实现 | 多模态等待期间每 15s 发送心跳 |
| 重试机制 | 未实现 | 对 429/5xx 可加入 1 次自动重试 |
| 前端超时 | 未实现 | fetch 请求加 AbortSignal timeout |

---

## 参考链接

| 资源 | 链接 |
|------|------|
| OpenAI Python SDK 源码 | `https://github.com/openai/openai-python` |
| OpenAI API 超时文档 | `https://platform.openai.com/docs/libraries` |
| Anthropic Python SDK | `https://github.com/anthropics/anthropic-sdk-python` |
| Anthropic API 文档 | `https://docs.anthropic.com/en/api/messages-streaming` |
| LangChain 超时配置 | `https://python.langchain.com/docs/concepts/chat_models/#timeout` |
| LangGraph 递归限制 | `https://langchain-ai.github.io/langgraph/concepts/low_level/#recursion-limit` |
| AutoGen Agent 配置 | `https://microsoft.github.io/autogen/docs/reference/agentchat/conversable_agent` |
| Dify LLM 节点 | `https://docs.dify.ai/guides/workflow/node/llm` |
| FastGPT 文档 | `https://doc.fastgpt.in/` |
| httpx Timeout 文档 | `https://www.python-httpx.org/advanced/timeout/` |
| MDN AbortController | `https://developer.mozilla.org/en-US/docs/Web/API/AbortController` |
| Python asyncio.timeout | `https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout` |
