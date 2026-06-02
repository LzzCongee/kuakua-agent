# 夸夸Agent 开发者上手指南

> 一个基于 AI 的夸夸生成服务，让你的每一天都充满正能量！

## 项目简介

夸夸Agent 后端服务是一个基于 Python + FastAPI 开发的 AI 夸夸生成 API 服务。它集成了魔搭社区（ModelScope）的 AI 模型，能够根据用户输入生成个性化的夸赞文案，支持多种场景（事业、颜值、恋爱、日常）和多模态输入（文字+图片）。

## 技术栈

| 技术 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 编程语言 |
| FastAPI | 0.115.0 | Web 框架 |
| Uvicorn | 0.30.6 | ASGI 服务器 |
| Pydantic | 2.x | 数据验证与序列化 |
| OpenAI SDK | >=1.51.0 | AI 模型调用 |
| aiosqlite | 0.20.0 | 异步 SQLite 数据库 |
| ModelScope | - | 魔搭社区 AI 模型 |

## 项目结构

```
kuakua-agent/
├── app/                    # 应用主目录
│   ├── api/               # API 路由层
│   │   ├── chat.py        # 交互式夸夸接口(含主动问候)
│   │   └── favorites.py   # 收藏管理接口
│   ├── core/              # 核心模块
│   │   └── exceptions.py  # 全局异常处理
│   ├── models/            # 数据模型层
│   │   ├── database.py    # 数据库初始化
│   │   └── schemas.py     # Pydantic 模型
│   ├── prompts/           # AI 提示词模板
│   │   └── templates.py   # 提示词定义
│   ├── providers/         # AI 提供商封装
│   │   ├── base.py        # 基础 Provider 接口
│   │   └── qwen.py        # 通义千问 Provider
│   ├── services/          # 业务逻辑层
│   │   ├── chat_service.py    # 交互式夸夸服务(含主动问候生成)
│   │   └── favorite_service.py # 收藏服务
│   ├── config.py          # 应用配置
│   └── main.py            # 应用入口
├── docs/                  # 文档目录
│   └── README.md          # 本文档
├── .env                   # 环境变量配置（需创建）
├── .env.example           # 环境变量示例
├── requirements.txt       # Python 依赖
└── kuakua.db              # SQLite 数据库（自动创建）
```

## 环境准备

### 1. 安装 Conda/Miniconda

如果尚未安装 Conda，请从以下地址下载并安装：

- **Miniconda**: https://docs.conda.io/en/latest/miniconda.html
- **Anaconda**: https://www.anaconda.com/download

安装完成后，确保 `conda` 命令可用：

```bash
conda --version
```

### 2. 创建并激活虚拟环境

```bash
# 创建 Python 3.12 环境
conda create -n kuakua python=3.12 -y

# 激活环境
conda activate kuakua
```

## 安装依赖

在激活的 conda 环境中，安装项目依赖：

```bash
pip install -r requirements.txt
```

依赖列表：
- `fastapi==0.115.0` - 高性能 Web 框架
- `uvicorn==0.30.6` - ASGI 服务器
- `openai>=1.51.0` - OpenAI 兼容 API 客户端
- `pydantic-settings==2.5.2` - 配置管理
- `aiosqlite==0.20.0` - 异步 SQLite 支持

## 配置说明

### 1. 复制环境变量文件

```bash
cp .env.example .env
```

### 2. 编辑 .env 文件

打开 `.env` 文件，填写必要的配置项：

```env
# 魔搭社区 API Key（必填）
# 获取方式：访问 https://modelscope.cn 注册并创建访问令牌
MODELSCOPE_API_KEY=your_api_key_here

# AI 服务基础 URL（默认即可）
AI_BASE_URL=https://api-inference.modelscope.cn/v1

# AI 模型名称（默认即可）
# 可选模型：https://modelscope.cn/models
AI_MODEL=deepseek-ai/DeepSeek-V3.2

# AI 视觉模型名称（用于处理图片）
AI_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct

# 数据库路径（默认即可）
DATABASE_URL=sqlite:///./kuakua.db

# 服务配置（默认即可）
APP_HOST=0.0.0.0
APP_PORT=8000
```

### 配置项说明

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MODELSCOPE_API_KEY` | 是 | - | 魔搭社区访问令牌，用于调用 AI 模型 |
| `AI_BASE_URL` | 否 | `https://api-inference.modelscope.cn/v1` | 魔搭社区 OpenAI 兼容接口地址 |
| `AI_MODEL` | 否 | `deepseek-ai/DeepSeek-V3.2` | 文本生成模型名称 |
| `AI_VISION_MODEL` | 否 | `Qwen/Qwen2.5-VL-72B-Instruct` | 视觉理解模型名称 |
| `DATABASE_URL` | 否 | `sqlite:///./kuakua.db` | SQLite 数据库连接 URL |
| `APP_HOST` | 否 | `0.0.0.0` | 服务监听主机地址 |
| `APP_PORT` | 否 | `8000` | 服务监听端口 |

### 获取 MODELSCOPE_API_KEY

1. 访问 [魔搭社区](https://modelscope.cn)
2. 注册/登录账号
3. 进入「个人中心」→「访问令牌」
4. 创建新的访问令牌并复制

## 启动服务

### 开发模式（推荐）

启用热重载，代码修改后自动重启：

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### 生产模式

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### 验证启动

服务启动后，访问健康检查接口：

```bash
curl http://localhost:8000/health
```

预期响应：

```json
{
  "status": "healthy",
  "service": "夸夸Agent API",
  "version": "0.1.0"
}
```

## API 接口文档

### Swagger UI

启动服务后，访问自动生成的 API 文档：

**http://127.0.0.1:8080/docs**

### 接口概览

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 健康检查 | GET | `/health` | 服务状态检查 |
| 主动问候 | GET | `/api/chat/greeting` | 主动问候生成(替代旧版随机夸夸) |
| 交互式夸夸 | POST | `/api/chat` | 基于文字/图片生成夸赞 |
| 收藏列表 | GET | `/api/favorites` | 获取用户收藏列表 |
| 添加收藏 | POST | `/api/favorites` | 添加夸夸语录到收藏 |
| 删除收藏 | DELETE | `/api/favorites/{id}` | 删除单条收藏记录 |
| 清空收藏 | DELETE | `/api/favorites` | 清空用户所有收藏 |

### 接口测试示例

#### 1. 健康检查

```bash
curl -X GET "http://localhost:8000/health"
```

#### 2. 获取主动问候

```bash
curl -X GET "http://localhost:8000/api/chat/greeting?last_active_at=$(date +%s)000" \
  -H "X-User-ID: your-user-id"
```

#### 3. 交互式夸夸（文字）

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "今天完成了一个重要项目！",
    "scene": "career"
  }'
```

#### 5. 交互式夸夸（图文）

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "看看我今天的穿搭",
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...",
    "scene": "beauty"
  }'
```

#### 6. 获取收藏列表

```bash
curl -X GET "http://localhost:8000/api/favorites?user_id=default"
```

#### 7. 添加收藏

```bash
curl -X POST "http://localhost:8000/api/favorites?user_id=default" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "你真棒！",
    "scene": "general"
  }'
```

#### 8. 删除收藏

```bash
curl -X DELETE "http://localhost:8000/api/favorites/1?user_id=default"
```

#### 9. 清空收藏

```bash
curl -X DELETE "http://localhost:8000/api/favorites?user_id=default"
```

## 接口详情

### 通用响应格式

所有 API 响应均采用统一格式：

```json
{
  "code": 0,           // 状态码，0 表示成功
  "message": "success", // 状态消息
  "data": { ... }      // 响应数据（可选）
}
```

### 1. 主动问候接口

#### GET /api/chat/greeting

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 否 | 会话 ID |
| last_active_at | number | 否 | 上次活跃时间(Unix 毫秒) |

**响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_type": "light_return",
    "should_greet": true,
    "greeting": "回来啦～刚才在忙什么呢？",
    "reason": "用户 0.5 小时未互动（5min~24h），发送轻问候"
  }
}
```

### 2. 交互式夸夸接口

#### POST /api/chat

**请求体：**

```json
{
  "text": "用户输入的文字（可选，与 image 至少填一个）",
  "image": "base64 编码的图片数据（可选）",
  "scene": "场景标签（可选，默认 general）"
}
```

**响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "content": "太棒了！完成重要项目的你真的很厉害！",
    "scene": "career",
    "has_image": false,
    "created_at": "2024-01-15T10:30:00"
  }
}
```

### 3. 收藏管理接口

#### GET /api/favorites

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 否 | 用户标识，默认 "default" |

**响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": 1,
      "content": "你真棒！",
      "scene": "general",
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

#### POST /api/favorites

**请求体：**

```json
{
  "content": "夸夸语录内容（必填）",
  "scene": "场景标签（可选，默认 general）"
}
```

**响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "content": "你真棒！",
    "scene": "general",
    "created_at": "2024-01-15T10:30:00"
  }
}
```

#### DELETE /api/favorites/{favorite_id}

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| favorite_id | integer | 收藏记录 ID |

**响应格式：**

```json
{
  "code": 0,
  "message": "删除成功",
  "data": null
}
```

#### DELETE /api/favorites

**响应格式：**

```json
{
  "code": 0,
  "message": "清空成功",
  "data": {
    "deleted_count": 5
  }
}
```

## 常见问题

### 1. 启动时报错 "MODELSCOPE_API_KEY" 未设置

确保已创建 `.env` 文件并正确填写了 `MODELSCOPE_API_KEY`。

### 2. API 调用返回 401 或 403 错误

检查 `MODELSCOPE_API_KEY` 是否有效，或是否已过期。前往魔搭社区重新生成令牌。

### 3. 数据库权限错误

确保项目目录有写入权限，SQLite 数据库文件 `kuakua.db` 会自动创建。

### 4. 端口被占用

修改 `.env` 文件中的 `APP_PORT` 为其他端口，如 `8001`。

## 开发建议

1. **使用虚拟环境**：始终使用 conda 虚拟环境隔离项目依赖
2. **代码热重载**：开发时使用 `--reload` 参数自动重启服务
3. **API 测试**：使用 Swagger UI (`/docs`) 进行接口调试
4. **日志查看**：启动时会显示详细的请求日志，便于调试

## 相关链接

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [魔搭社区](https://modelscope.cn)
- [Pydantic 文档](https://docs.pydantic.dev/)
