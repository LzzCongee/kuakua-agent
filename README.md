# 夸夸Agent 后端服务

> 基于 AI 的正向能量夸夸生成服务，让每一天都充满正能量！

## 特性

- 随机/场景化 AI 夸夸生成（事业、颜值、恋爱、日常）
- 多模态输入支持（文字 + 图片）
- 收藏管理
- 基于 FastAPI，自带交互式 API 文档

## 技术栈

Python 3.12 + FastAPI + SQLite + 魔搭社区 AI 模型

## 快速启动

### 1. 环境准备

```bash
conda create -n kuakua python=3.12 -y
conda activate kuakua
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填写 MODELSCOPE_API_KEY（魔搭社区访问令牌）
```

### 3. 启动

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问 **http://localhost:8000/docs** 查看交互式 API 文档。

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
