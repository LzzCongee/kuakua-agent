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
| GET | `/api/quotes/random` | 随机夸夸 |
| GET | `/api/quotes/scene?type=career` | 场景夸夸 |
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

部署时配置了以下环境变量：

| 变量名 | 值 |
|--------|------|
| `MODELSCOPE_API_KEY` | 魔搭社区 API Key |
| `AI_BASE_URL` | `https://api-inference.modelscope.cn/v1` |
| `AI_MODEL` | `deepseek-ai/DeepSeek-V3.2` |
| `AI_VISION_MODEL` | `Qwen/Qwen2.5-VL-72B-Instruct` |
| `DATABASE_URL` | `sqlite:///./kuakua.db` |
| `USE_CLOUDBASE` | `true` |
| `CLOUDBASE_ENV_ID` | `dev-kuakua-d1gmvqyrha28477fe` |
| `SUPERMEMORY_URL` | `http://106.55.151.27/sse` |
| `SUPERMEMORY_ENABLED` | `true` |
| `ENVIRONMENT` | `production` |

### 控制台

- 云托管服务管理: `https://tcb.cloud.tencent.com/dev?envId=dev-kuakua-d1gmvqyrha28477fe#/platform-run`
