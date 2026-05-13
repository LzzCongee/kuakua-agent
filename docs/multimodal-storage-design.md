# 多模态对话存储方案设计

> 本文档记录夸夸 Agent 中图片+文本混合对话的存储策略、行业调研与技术设计。
> 对应实施：test.html 多模态输入、会话消息格式升级、图片描述提取。

---

## 一、现状分析

### 1.1 已实现

| 模块 | 状态 | 说明 |
|------|------|------|
| `ChatRequest.image` | 已实现 | 接受 base64 或 data-URI 格式的图片 |
| `ChatService` 视觉路由 | 已实现 | 自动分类 text_only / image_only / mixed，路由到 vision model |
| `QwenProvider.generate_multimodal()` | 已实现 | OpenAI Vision 格式消息组装 |
| `/api/chat` 和 `/api/chat/stream` | 已实现 | 均支持图片输入 |

### 1.2 关键缺失

| 缺失项 | 影响 |
|--------|------|
| `test.html` 无图片上传 | 无法测试多模态功能 |
| `_update_session_after_chat` 丢弃图片 | 图片对话上下文丢失 |
| 无图片存储机制 | 无法回看历史图片对话 |
| 消息格式不支持图片类型 | JSON 只存纯文本 content |

---

## 二、行业调研：图片对话怎么存

### 2.1 产品对比

| 产品 | 图片存储策略 | 上下文保留 | 长期存储 |
|------|------------|-----------|---------|
| **ChatGPT** | 会话内保留原图，跨会话不持久化 | 会话内可引用原图 | 不保留原图 |
| **Claude** | 会话上下文内保留，会话结束丢弃 | 同上 | 不保留 |
| **Gemini** | 会话内保留，支持多图输入 | 会话内完整 | 不保留 |
| **微信/飞书** | 对象存储（OSS/CDN）+ URL 引用 | 永久 | 永久（付费扩容） |
| **Character.AI** | 不支持图片输入 | N/A | N/A |

### 2.2 共同规律

1. **会话内保留原图**：当前对话的上下文中需要原始图片数据，用于多轮引用
2. **长期存储只保留语义信息**：图片的"记忆价值"在于 AI 看到了什么，而非像素本身
3. **对象存储是规模化的选择**：日活过万时，数据库存 base64 不可接受

### 2.3 夸夸场景的特殊性

夸夸 Agent 中图片的核心作用：

```
用户发图 → AI 看到图片 → 生成夸赞 → 后续对话需要知道"图片里有什么"
                                      ↓
                              需要的是描述，不是像素
```

- 用户发自拍 → AI 夸穿搭/气质 → 后续需要知道"用户穿了什么"
- 用户发美食 → AI 夸生活品味 → 后续需要知道"用户做了什么菜"
- 用户发风景 → AI 夸摄影/生活 → 后续需要知道"用户去了哪里"

**关键洞察**：图片对记忆系统的价值 = AI 对图片的理解（描述），而非图片数据本身。

---

## 三、技术方案

### 3.1 方案选型

| 方案 | 存储内容 | 消息大小 | 可检索性 | 工程复杂度 |
|------|---------|---------|---------|-----------|
| A. 存 base64 到消息 JSON | 原图 base64 | 2-5MB/条 | 不可检索 | 低 |
| B. 存描述 + 丢弃原图 | AI 生成的图片描述 | <500B/条 | 可检索 | 中 |
| C. 描述存消息 + 原图存 OSS | 描述 + OSS URL | <1KB/条 | 可检索 | 高 |

**选择方案 B**，理由：

1. **轻量**：每条消息 <500 字节，vs base64 的 2-5MB
2. **可检索**：图片描述是纯文本，可被记忆系统索引和搜索
3. **无需额外基础设施**：不需要 OSS/CDN 配置
4. **符合行业实践**：ChatGPT/Claude 的长期记忆也是存语义信息而非原图
5. **可升级**：未来需要原图时，可加 OSS 层（方案 C），消息格式不变

### 3.2 消息格式设计

```python
# 纯文本消息（不变）
{
    "role": "user",
    "content": "今天好累啊",
    "type": "text",
    "timestamp": "2026-05-13T10:00:00Z"
}

# 纯图片消息（新增）
{
    "role": "user",
    "content": "用户发了一张自拍，穿着白色连衣裙，背景是海边夕阳",
    "type": "image",
    "has_image": True,
    "timestamp": "2026-05-13T10:00:00Z"
}

# 文字+图片混合消息（新增）
{
    "role": "user",
    "content": "今天的穿搭\n[图片：白色连衣裙，海边夕阳背景，整体风格清新]",
    "type": "mixed",
    "has_image": True,
    "timestamp": "2026-05-13T10:00:00Z"
}

# AI 回复（不变）
{
    "role": "assistant",
    "content": "这件白裙子选得真好，海边的光...",
    "timestamp": "2026-05-13T10:00:00Z"
}
```

### 3.3 图片描述从哪来

**核心问题**：vision model 生成的是夸赞文案，不是图片描述。需要额外获取描述。

**方案：复用夸赞生成的上下文，从 AI 回复中提取描述片段**

```
用户发图
    │
    ▼
┌─────────────────────────────────┐
│ Vision Model 生成夸赞             │
│ (同时在 system prompt 中要求      │
│  返回 JSON: {compliment, desc})  │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ 解析返回                         │
│ - compliment → 发给用户           │
│ - desc → 存入会话消息             │
└─────────────────────────────────┘
```

**为什么不让 vision model 单独生成描述？**
- 多一次 API 调用 = 多一倍成本 + 延迟
- 夸赞生成时 vision model 已经"看到"了图片，描述信息已经在上下文中
- 通过 prompt 工程让它同时返回描述，零额外成本

**Prompt 设计**：

对于 image_only 和 mixed 场景，在 system prompt 中追加：

```
【输出格式要求】
请严格按以下 JSON 格式返回，不要添加其他内容：
{
  "compliment": "你的夸赞文案",
  "image_desc": "图片的简短客观描述（30字以内，用于记忆上下文，不包含主观评价）"
}
```

**降级策略**：
- JSON 解析失败 → 整个响应作为 compliment，image_desc 为 None
- image_desc 为 None → 消息中不存图片描述，标记 `"desc_available": false`

### 3.4 会话存储流程改造

```python
# 当前流程（丢失图片）
if request.text:
    messages.append({"role": "user", "content": request.text, ...})

# 改造后流程
if request.image and request.text:
    # 混合输入
    desc = extract_image_desc(response)  # 从 AI 回复中提取
    content = request.text
    if desc:
        content += f"\n[图片：{desc}]"
    messages.append({
        "role": "user", "content": content,
        "type": "mixed", "has_image": True, ...
    })
elif request.image:
    # 纯图片
    desc = extract_image_desc(response)
    messages.append({
        "role": "user", "content": desc or "[图片]",
        "type": "image", "has_image": True, ...
    })
elif request.text:
    # 纯文本（不变）
    messages.append({"role": "user", "content": request.text, ...})
```

### 3.5 记忆注入时的处理

图片消息在注入记忆时的处理：

```python
# 获取最近消息时
for msg in messages[-3:]:
    if msg.get("has_image"):
        # 图片消息已有描述，正常注入
        content = msg["content"]  # 已包含描述
    else:
        content = msg["content"]
```

由于描述已经内联在 `content` 中，记忆注入逻辑无需修改。

### 3.6 test.html 改造

新增功能：
1. 图片上传区域（拖拽 + 粘贴 + 文件选择）
2. 图片预览（缩略图 + 删除按钮）
3. base64 转换（FileReader.readAsDataURL）
4. 发送时携带 image 字段
5. 对话历史中图片消息的展示（显示描述 + 图片标记）

---

## 四、改动范围

| 文件 | 改动 |
|------|------|
| `app/services/chat_service.py` | 多模态生成时同时返回图片描述 |
| `app/api/chat.py` | `_update_session_after_chat` 支持存储图片描述 |
| `app/static/test.html` | 新增图片上传 UI |
| `app/prompts/templates.toml` | 多模态 prompt 追加描述输出要求 |

**不需要改的**：
- `ChatRequest` / `ChatResponse` schema（已支持 image 字段）
- `MemoryService`（图片描述内联在 content 中，无需特殊处理）
- `MemoryExtractor`（描述在 content 中，正常提取）
- 数据库模型（消息格式兼容，无需 migration）

---

## 五、成本影响

| 项目 | 当前 | 改造后 |
|------|------|--------|
| 多模态 API 调用次数 | 1 次 | 1 次（不变） |
| 输出 token | ~100 | ~150（多了 image_desc） |
| 单次成本增量 | - | +~¥0.0001 |
| 会话存储大小 | 丢弃图片 | <500 字节/条（描述） |

---

## 六、后续演进

| 阶段 | 内容 | 时机 |
|------|------|------|
| **Phase 1（当前）** | 描述存储 + test.html 多模态 | 即刻 |
| **Phase 2** | OSS 原图存储（可选） | 需要图片回看功能时 |
| **Phase 3** | 图片内容索引（按描述搜索历史图片对话） | 记忆搜索增强时 |
