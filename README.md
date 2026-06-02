# 夸夸Agent 后端服务

> 基于 AI 的正向能量夸夸生成服务，让每一天都充满正能量！

## 特性

- 随机/场景化 AI 夸夸生成（事业、颜值、恋爱、日常）
- 多模态输入支持（文字 + 图片）
- 收藏管理
- 基于 FastAPI，自带交互式 API 文档

## 技术栈

Python 3.12 + FastAPI + SQLite + 魔搭社区 AI 模型

### 开发工具

- **包管理器**: uv (推荐) 或 pip
- **代码格式化**: ruff (自动修复导入排序和行长度)
- **类型检查**: mypy (strict 模式)
- **虚拟环境**: .venv (uv venv 或 conda)

## 快速启动

### 方式一：使用 uv（推荐 🚀）

`uv` 是超快的 Python 包管理器，比传统 pip 快 10-100 倍。

#### 1. 安装 uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# 或使用 pip（任意平台）
pip install uv
```

#### 2. 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境（默认目录为 .venv）
uv venv --python 3.12
# 安装依赖（使用 uv.lock 锁定版本，更稳定）
uv sync --python 3.12 --frozen
```

#### 3. 配置

```bash
# macOS/Linux
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

```text
# 编辑 .env，填写 MODELSCOPE_API_KEY（魔搭社区访问令牌）
```

#### 4. 启动服务

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

启动后访问 **http://127.0.0.1:8080/docs** 查看交互式 API 文档。

---

### 方式二：传统 pip/conda

```bash
# pip + venv
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# 或 conda
conda create -n kuakua python=3.12 -y
conda activate kuakua
pip install -r requirements.txt
```

#### 2. 配置

```bash
# macOS/Linux
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

```text
# 编辑 .env，填写 MODELSCOPE_API_KEY（魔搭社区访问令牌）
```

#### 3. 启动

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

启动后访问 **http://127.0.0.1:8080/docs** 查看交互式 API 文档。

---

## 💡 开发小贴士

### 使用 uv 的快捷命令

```bash
# 安装依赖（自动创建虚拟环境）
uv pip install -r requirements.txt

# 运行服务（无需手动激活虚拟环境）
uv run uvicorn app.main:app --reload

# 运行类型检查
uv run mypy app

# 格式化代码（需要先安装 ruff）
uv run ruff format app/
uv run ruff check app/ --fix

# 运行 Python 脚本
uv run python your_script.py
```

### uv 的优势

- ⚡ **超快速度**: 比 pip 快 10-100 倍
- 🔒 **自动管理**: 自动处理虚拟环境和依赖
- 🎯 **零配置**: `uv run` 自动检测并使用 `.venv`
- 📦 **兼容性好**: 完全兼容现有 pip 工作流

### 🌏 国内加速镜像

#### 方式 A：使用项目 pip.ini（推荐）

项目已包含 `pip.ini` 配置文件，会自动使用清华镜像源。

#### 方式 B：临时指定镜像源

```bash
# pip 方式
pip install -r requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/ \
  --trusted-host mirrors.aliyun.com

# uv 方式
uv pip install -r requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/ \
  --trusted-host mirrors.aliyun.com
```

**注意**: OpenAI 包可能需要编译，如果安装失败，可以：
1. 安装 Visual Studio Build Tools（Windows）
2. 或使用预编译版本：`pip install "openai>=1.51.0,<2.0.0"`

#### 其他可用镜像源

- 阿里云：`https://mirrors.aliyun.com/pypi/simple/`
- 中科大：`https://pypi.mirrors.ustc.edu.cn/simple/`
- 豆瓣：`https://pypi.doubanio.com/simple/`

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 交互式夸夸（文字/图片） |
| GET | `/api/favorites` | 收藏列表 |
| POST | `/api/favorites` | 添加收藏 |

## 文档

- [开发者上手指南](docs/getting-started.md) - 完整的环境配置、API 接口详情和常见问题
- [产品需求文档](docs/prd.md) - PRD 产品设计文档

---

## CloudBase 云托管部署

### 部署信息

| 项目 | 值 |
|------|------|
| 服务名称 | `kuakua-api` |
| 服务类型 | 容器型 (container) |
| 环境 ID | `dev-kuakua-d1gmvqyrha28477fe` |
| 默认域名 | `https://kuakua-api-257074-7-1308646910.sh.run.tcloudbase.com` |
| 端口 | 8080 |
| CPU / 内存 | 0.5 核 / 1 GB |
| 实例数 | 最小 1，最大 5 |
| 访问类型 | PUBLIC / MINIAPP / OA |

### API 地址

- 健康检查: `https://kuakua-api-257074-7-1308646910.sh.run.tcloudbase.com/health`
- API 文档: `https://kuakua-api-257074-7-1308646910.sh.run.tcloudbase.com/docs`

### 环境变量

部署时配置了以下环境变量（分组模型配置，双下划线 `__` 表示嵌套）：

**AI 模型配置**

| 变量名 | 值 | 说明 |
|--------|------|------|
| `AI_CHAT__API_KEY` | DeepSeek API Key | 对话模型密钥 |
| `AI_CHAT__BASE_URL` | `https://api.deepseek.com/v1` | 对话模型地址 |
| `AI_CHAT__MODEL` | `deepseek-v4-flash` | 对话模型 |
| `AI_CHAT__TIMEOUT` | `30` | 对话超时(秒) |
| `AI_VISION__API_KEY` | SiliconFlow API Key | 视觉模型密钥 |
| `AI_VISION__BASE_URL` | `https://api.siliconflow.cn/v1` | 视觉模型地址 |
| `AI_VISION__MODEL` | `Qwen/Qwen3-VL-8B-Instruct` | 视觉模型 |
| `AI_VISION__TIMEOUT` | `60` | 视觉超时(秒) |
| `AI_EXTRACT__API_KEY` | DeepSeek API Key | 提取模型密钥 |
| `AI_EXTRACT__BASE_URL` | `https://api.deepseek.com/v1` | 提取模型地址 |
| `AI_EXTRACT__MODEL` | `deepseek-v4-flash` | 提取模型 |
| `AI_EXTRACT__TIMEOUT` | `15` | 提取超时(秒) |
| `AI_EXTRACT_ENABLED` | `true` | 启用 AI 提取 |
| `AI_EXTRACT_KEYWORD_FALLBACK` | `true` | 提取失败回退关键词 |
| `AI_EXTRACT_TEMPERATURE` | `0.1` | 提取温度 |
| `AI_EXTRACT_MAX_TOKENS` | `200` | 提取最大 token |

**SuperMemory 记忆配置**

| 变量名 | 值 | 说明 |
|--------|------|------|
| `SUPERMEMORY_URL` | `http://106.55.151.27/sse` | SuperMemory 服务地址 |
| `SUPERMEMORY_TOKEN` | `kuakua-agent` | SuperMemory 访问令牌 |
| `SUPERMEMORY_ENABLED` | `true` | 启用记忆功能 |
| `SUPERMEMORY_TIMEOUT` | `15.0` | 超时(秒) |
| `SUPERMEMORY_TOP_K` | `3` | 检索条数 |

**基础配置**

| 变量名 | 值 | 说明 |
|--------|------|------|
| `DATABASE_URL` | `sqlite:///./kuakua.db` | 数据库连接 |
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8080` | 监听端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `ADMIN_API_KEY` | (自定义) | 管理后台认证密钥 |
| `ENVIRONMENT` | `production` | 运行环境 |
| `USE_CLOUDBASE` | `true` | 启用 CloudBase |
| `CLOUDBASE_ENV_ID` | `dev-kuakua-d1gmvqyrha28477fe` | CloudBase 环境 ID |

### 一键部署

代码变更后，使用部署脚本一键重新部署到 CloudBase：

```bash
# macOS/Linux
chmod +x scripts/deploy-cloudbase.sh
bash scripts/deploy-cloudbase.sh

# Windows PowerShell
.\scripts\deploy-cloudbase.ps1

# 部署并等待完成
bash scripts/deploy-cloudbase.sh --watch     # macOS/Linux
.\scripts\deploy-cloudbase.ps1 -Watch        # Windows
```

脚本会自动从 `.env` 读取所有环境变量（含双下划线嵌套格式），无需手动修改。

> 前置条件：安装 CloudBase CLI (`npm i -g @cloudbase/cli`) 并登录 (`tcb login`)

### 日志查看

**方式一：CloudBase 控制台（推荐）**

控制台自动收集 stdout 日志，支持按时间、关键词搜索：

- 云托管日志: `https://tcb.cloud.tencent.com/dev?envId=dev-kuakua-d1gmvqyrha28477fe#/platform-run`
- 点击「kuakua-api」服务 → 「日志」标签页

**方式二：日志查询 API**

通过管理后台接口查询服务日志，需要 `X-Admin-Key` 认证：

```bash
# 查询最近 200 行日志
curl -H "X-Admin-Key: <你的ADMIN_API_KEY>" \
  "https://kuakua-api-257074-7-1308646910.sh.run.tcloudbase.com/api/admin/logs"

# 按关键词搜索
curl -H "X-Admin-Key: <你的ADMIN_API_KEY>" \
  ".../api/admin/logs?keyword=请求开始"

# 按级别过滤
curl -H "X-Admin-Key: <你的ADMIN_API_KEY>" \
  ".../api/admin/logs?level=ERROR"

# 按 trace_id 追踪
curl -H "X-Admin-Key: <你的ADMIN_API_KEY>" \
  ".../api/admin/logs?trace_id=abc12345"

# 分页查询
curl -H "X-Admin-Key: <你的ADMIN_API_KEY>" \
  ".../api/admin/logs?tail=500&page=2&page_size=20"
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keyword` | string | - | 关键词搜索（不区分大小写） |
| `level` | string | - | 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `trace_id` | string | - | 按 trace_id 过滤 |
| `tail` | int | 200 | 读取最后 N 行（1-2000） |
| `page` | int | 1 | 页码 |
| `page_size` | int | 50 | 每页条数 |

### 控制台

- 云托管服务管理: `https://tcb.cloud.tencent.com/dev?envId=dev-kuakua-d1gmvqyrha28477fe#/platform-run`
