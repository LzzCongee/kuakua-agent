# 夸夸Agent 部署指南

> 本文档详细介绍 CloudBase (云开发) 和 Lighthouse (轻量应用服务器) 两种部署方案，以及为微信小程序提供后端服务的接入方式。

---

## 📋 目录

1. [方案对比与选择建议](#方案对比与选择建议)
2. [CloudBase (云开发) 部署](#cloudbase-云开发-部署)
   - [部署的本质](#1-cloudbase-部署的本质是什么)
   - [服务提供方式](#2-cloudbase-给小程序提供服务的方式)
   - [域名分配机制](#3-关于域名分配和访问方式)
   - [小程序调用方法](#4-小程序如何调用-cloudbase-服务)
   - [部署步骤](#5-cloudbase-部署步骤)
3. [Lighthouse (轻量服务器) 部署](#lighthouse-轻量服务器-部署)
4. [多环境管理（测试/生产/灰度）](#多环境管理测试生产灰度)
5. [小程序接入说明](#小程序接入说明)
6. [常见问题 FAQ](#常见问题-faq)

---

## 方案对比与选择建议

### 快速对比

| 维度 | CloudBase (推荐) | Lighthouse |
|------|------------------|------------|
| **部署复杂度** | ⭐ 低 | ⭐⭐⭐ 中 |
| **运维成本** | 免运维 | 需自行维护 |
| **多环境支持** | ✅ 内置环境隔离 | ⚠️ 需手动配置 |
| **小程序适配** | ✅ 微信生态原生支持 | ⚠️ 需额外配置 |
| **公网访问** | ✅ 自动分配域名 | ✅ 独立公网IP |
| **自动扩缩容** | ✅ 自动弹性伸缩 | ❌ 手动升级配置 |
| **成本** | 按量付费，有免费额度 | 固定月费 |

### 选择建议

**选择 CloudBase 如果：**
- 希望快速上线，减少运维工作
- 需要与微信小程序深度集成
- 团队没有专职运维人员
- 业务流量波动大，需要自动扩缩容

**选择 Lighthouse 如果：**
- 需要完整的服务器控制权
- 有复杂的自定义环境需求
- 需要运行长时间后台任务
- 希望固定成本预算

---

## CloudBase (云开发) 部署

### 1. CloudBase 部署的本质是什么？

CloudBase 部署的本质是 **"将你的应用代码托管到腾讯云的 Serverless 容器/函数平台，由平台自动分配访问入口（域名），并提供弹性计算资源"**。

简单理解：
```
传统部署: 你买服务器 → 装环境 → 部署代码 → 配置域名 → 维护服务器
CloudBase: 你写代码 → 执行部署命令 → 平台自动给你分配域名和计算资源
```

**核心特点：**
- **无服务器运维**：不需要买服务器、装系统、配环境
- **自动分配域名**：部署成功后自动生成可访问的 HTTPS 域名
- **弹性伸缩**：流量大了自动扩容，流量小了自动缩容
- **按量付费**：用多少付多少，有免费额度

### 2. CloudBase 给小程序提供服务的方式

```
┌─────────────────────────────────────────────────────────────┐
│                        微信小程序                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   首页      │  │   场景页    │  │      历史页         │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          └────────────────┴────────────────────┘
                           │
          ┌────────────────▼────────────────────┐
          │      微信客户端 (内置安全验证)       │
          └────────────────┬────────────────────┘
                           │ HTTPS
          ┌────────────────▼────────────────────┐
          │     CloudBase HTTP 访问服务         │
          │  (自动分配域名: xxx.cloudbase.net)  │
          └────────────────┬────────────────────┘
                           │
          ┌────────────────▼────────────────────┐
          │      云函数 / 云托管容器            │
          │    ┌─────────────────────────┐      │
          │    │    FastAPI 应用         │      │
          │    │  ┌─────┐ ┌─────┐ ┌────┐ │      │
          │    │  │/api │ │/health│ │/docs│ │      │
          │    │  └─────┘ └─────┘ └────┘ │      │
          │    └─────────────────────────┘      │
          └─────────────────────────────────────┘
                           │
          ┌────────────────▼────────────────────┐
          │    CloudBase 数据库 (可选)          │
          │    - MongoDB / MySQL / PostgreSQL   │
          └─────────────────────────────────────┘
```

### 3. 关于域名分配和访问方式

#### 域名是自动分配的吗？

**是的，CloudBase 会自动分配一个固定的域名。**

部署成功后，你会得到一个类似这样的域名：
```
https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com
                      ↑
                      └── 这是自动分配的，固定不变
```

**域名特点：**
| 特性 | 说明 |
|-----|------|
| **自动生成** | 部署时自动创建，无需手动配置 |
| **固定不变** | 只要不删除环境，域名永久有效 |
| **HTTPS 支持** | 自动配置 SSL 证书，自动续期 |
| **多环境隔离** | 每个环境有独立的域名 |

#### 多环境 = 多个域名

创建多个环境 = 自动获得多个独立域名：

```
测试环境 (dev)     →  https://kuakua-agent-dev-xxx.ap-shanghai.app.tcloudbase.com
灰度环境 (gray)    →  https://kuakua-agent-gray-xxx.ap-shanghai.app.tcloudbase.com
生产环境 (prod)    →  https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com
```

**只需要更换 API 接口端点（域名），就能访问不同的服务环境。**

#### CloudBase 不提供独立公网 IP

| 访问方式 | 地址格式 | 说明 |
|---------|---------|------|
| **默认域名** | `https://{env-id}-{app-id}.ap-shanghai.app.tcloudbase.com` | 自动分配，HTTPS 证书自动续期 |
| **自定义域名** | `https://api.yourdomain.com` | 可绑定自己的域名，需备案 |
| **内网访问** | 通过云函数调用 | 同环境下的服务内网互通，免流量费 |

**小程序访问 CloudBase 的优势：**
- ✅ 微信客户端内置安全域名验证
- ✅ 免鉴权调用（使用微信登录态）
- ✅ 请求自动走微信加密通道
- ✅ 支持订阅消息推送

### 4. 小程序如何调用 CloudBase 服务？

小程序调用 CloudBase 服务非常简单，**本质上就是普通的 HTTPS 请求**，只是域名是 CloudBase 自动分配的。

#### 调用流程

```
小程序代码
    ↓ 发起 HTTPS 请求
wx.request({ url: "https://kuakua-agent-prod-xxx.app.tcloudbase.com/api/quotes/random" })
    ↓
微信客户端（自动处理域名安全校验）
    ↓
CloudBase 网关
    ↓
你的 FastAPI 应用
    ↓
返回 JSON 数据
```

#### 小程序调用示例

**第一步：配置合法域名**

登录微信公众平台 → 开发 → 开发设置 → 服务器域名：

| 类型 | 填写内容 |
|-----|---------|
| request 合法域名 | `https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com` |

**第二步：封装请求方法**

```javascript
// utils/request.js

// 根据小程序版本自动选择环境
const getBaseUrl = () => {
  const info = wx.getAccountInfoSync();
  const envVersion = info.miniProgram.envVersion;
  
  // 不同环境对应不同的 CloudBase 域名
  const envUrls = {
    'develop': 'https://kuakua-agent-dev-xxx.ap-shanghai.app.tcloudbase.com',  // 开发版
    'trial': 'https://kuakua-agent-gray-xxx.ap-shanghai.app.tcloudbase.com',   // 体验版（灰度）
    'release': 'https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com'  // 正式版
  };
  
  return envUrls[envVersion] || envUrls['develop'];
};

// 封装请求方法
const request = (options) => {
  return new Promise((resolve, reject) => {
    wx.request({
      url: getBaseUrl() + options.url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...options.header
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(res.data.message || '请求失败'));
        }
      },
      fail: reject
    });
  });
};

// API 方法封装
const api = {
  // 获取随机夸夸
  getRandomQuote: () => request({ url: '/api/quotes/random' }),
  
  // 获取场景夸夸
  getSceneQuote: (type) => request({ url: `/api/quotes/scene?type=${type}` }),
  
  // 收藏夸夸
  addFavorite: (data) => request({
    url: '/api/favorites',
    method: 'POST',
    data
  })
};

module.exports = { request, api };
```

**第三步：在页面中使用**

```javascript
// pages/index/index.js
const { api } = require('../../utils/request');

Page({
  data: {
    quote: null,
    loading: false
  },
  
  async onLoad() {
    await this.loadQuote();
  },
  
  async loadQuote() {
    this.setData({ loading: true });
    try {
      const res = await api.getRandomQuote();
      if (res.code === 0) {
        this.setData({ quote: res.data });
      }
    } catch (error) {
      wx.showToast({ title: '加载失败', icon: 'error' });
    } finally {
      this.setData({ loading: false });
    }
  },
  
  // 点击"再夸我一次"
  async onRefresh() {
    await this.loadQuote();
  }
});
```

#### 关键要点

| 问题 | 答案 |
|-----|------|
| 需要特殊 SDK 吗？ | **不需要**，普通 `wx.request` 即可 |
| 需要处理鉴权吗？ | CloudBase 支持微信免鉴权，如需用户身份，调用 `wx.login` 获取 code 传给后端 |
| 支持 HTTPS 吗？ | **必须**，小程序只支持 HTTPS，CloudBase 自动提供 |
| 域名会变吗？ | **不会**，只要不删除环境，域名永久固定 |

---

### 5. CloudBase 部署步骤

#### 步骤 1: 准备工作

```bash
# 安装 CloudBase CLI
npm install -g @cloudbase/cli

# 登录腾讯云账号
tcb login
```

#### 步骤 2: 项目改造

创建 `Dockerfile`（项目根目录）：

```dockerfile
# 使用 Python 3.12 官方镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY .env .

# 暴露端口（CloudBase 默认使用 8080）
EXPOSE 8080

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

创建 `cloudbaserc.json` 配置文件：

```json
{
  "version": "2.0",
  "envId": "kuakua-agent-{环境标识}",
  "framework": {
    "name": "kuakua-agent",
    "plugins": {
      "container": {
        "use": "@cloudbase/framework-plugin-container",
        "inputs": {
          "serviceName": "kuakua-api",
          "servicePath": "/",
          "localPath": ".",
          "dockerfile": "Dockerfile",
          "containerPort": 8080,
          "envVariables": {
            "MODELSCOPE_API_KEY": "${MODELSCOPE_API_KEY}",
            "AI_BASE_URL": "${AI_BASE_URL}",
            "AI_MODEL": "${AI_MODEL}",
            "DATABASE_URL": "${DATABASE_URL}"
          }
        }
      }
    }
  }
}
```

#### 步骤 3: 创建多环境

```bash
# 创建测试环境
tcb env:create kuakua-agent-dev --region ap-shanghai

# 创建生产环境
tcb env:create kuakua-agent-prod --region ap-shanghai

# 创建灰度环境
tcb env:create kuakua-agent-gray --region ap-shanghai
```

#### 步骤 4: 部署应用

```bash
# 部署到测试环境
tcb framework:deploy --env-id kuakua-agent-dev

# 部署到生产环境
tcb framework:deploy --env-id kuakua-agent-prod
```

#### 步骤 5: 小程序配置

在小程序 `app.js` 或请求封装文件中：

```javascript
// config.js
const ENV_CONFIG = {
  dev: {
    baseUrl: 'https://kuakua-agent-dev-xxx.ap-shanghai.app.tcloudbase.com',
    envId: 'kuakua-agent-dev'
  },
  gray: {
    baseUrl: 'https://kuakua-agent-gray-xxx.ap-shanghai.app.tcloudbase.com',
    envId: 'kuakua-agent-gray'
  },
  prod: {
    baseUrl: 'https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com',
    envId: 'kuakua-agent-prod'
  }
};

// 根据小程序版本自动选择环境
const getEnv = () => {
  const accountInfo = wx.getAccountInfoSync();
  const envType = accountInfo.miniProgram.envVersion;
  
  switch(envType) {
    case 'develop': return ENV_CONFIG.dev;      // 开发版
    case 'trial': return ENV_CONFIG.gray;       // 体验版（灰度）
    case 'release': return ENV_CONFIG.prod;     // 正式版
    default: return ENV_CONFIG.dev;
  }
};

module.exports = { getEnv, ENV_CONFIG };
```

请求封装示例：

```javascript
// utils/request.js
const { getEnv } = require('../config');

const request = (options) => {
  const env = getEnv();
  
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${env.baseUrl}${options.url}`,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...options.header
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res);
        }
      },
      fail: reject
    });
  });
};

// API 封装
const api = {
  // 获取随机夸夸
  getRandomQuote: () => request({ url: '/api/quotes/random' }),
  
  // 获取场景夸夸
  getSceneQuote: (type) => request({ 
    url: '/api/quotes/scene?type=' + type 
  }),
  
  // 收藏夸夸
  addFavorite: (data) => request({
    url: '/api/favorites',
    method: 'POST',
    data
  })
};

module.exports = { request, api };
```

---

## Lighthouse (轻量服务器) 部署

### 1. 什么是 Lighthouse？

腾讯云轻量应用服务器 (Lighthouse) 是一种**轻量级云服务器**，提供独立的计算资源和公网 IP，适合需要完整服务器控制权的场景。

### 2. Lighthouse 提供服务的方式

```
┌─────────────────────────────────────────────────────────────┐
│                        微信小程序                            │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS
          ┌─────────────────▼──────────────────┐
          │      腾讯云 Lighthouse 服务器       │
          │      公网 IP: 123.45.67.89         │
          │      域名: api.kuakua-app.com      │
          ├────────────────────────────────────┤
          │  ┌──────────────────────────────┐  │
          │  │      Nginx (反向代理)        │  │
          │  │   - SSL 证书管理             │  │
          │  │   - 负载均衡                 │  │
          │  └──────────────┬───────────────┘  │
          │                 │                  │
          │  ┌──────────────▼───────────────┐  │
          │  │   Docker Compose             │  │
          │  │   ┌─────────────────────┐    │  │
          │  │   │  FastAPI 容器       │    │  │
          │  │   │  - 端口: 8000       │    │  │
          │  │   │  - 环境变量配置     │    │  │
          │  │   └─────────────────────┘    │  │
          │  │   ┌─────────────────────┐    │  │
          │  │   │  SQLite/PostgreSQL  │    │  │
          │  │   │  - 数据持久化       │    │  │
          │  │   └─────────────────────┘    │  │
          │  └──────────────────────────────┘  │
          └────────────────────────────────────┘
```

### 3. 关于公网 IP

**Lighthouse 提供独立公网 IP**，特点如下：

| 特性 | 说明 |
|-----|------|
| **独立公网 IP** | 每台实例分配一个固定的公网 IPv4 地址 |
| **带宽** | 根据配置提供 3Mbps-30Mbps 不等 |
| **流量包** | 每月固定流量包，超出后按量计费 |
| **域名绑定** | 可将域名解析到该 IP，需备案 |
| **防火墙** | 控制台可配置端口开放规则 |

### 4. Lighthouse 部署步骤

#### 步骤 1: 创建服务器实例

1. 登录腾讯云控制台 → 轻量应用服务器
2. 选择地域（建议选择靠近用户的地域，如上海/广州）
3. 选择镜像：**Docker 基础镜像** 或 **Ubuntu 22.04**
4. 选择配置：建议 2核4G 起步
5. 购买并启动实例

#### 步骤 2: 服务器环境配置

SSH 连接到服务器后执行：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker（如未预装）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 创建应用目录
mkdir -p /opt/kuakua-agent
cd /opt/kuakua-agent
```

#### 步骤 3: 上传项目代码

```bash
# 在本地项目目录执行，将代码上传到服务器
scp -r app/ docker-compose.yml Dockerfile .env root@<服务器IP>:/opt/kuakua-agent/
```

#### 步骤 4: 创建 Docker Compose 配置

创建 `/opt/kuakua-agent/docker-compose.yml`：

```yaml
version: '3.8'

services:
  api:
    build: .
    container_name: kuakua-api
    restart: always
    ports:
      - "8000:8000"
    environment:
      - MODELSCOPE_API_KEY=${MODELSCOPE_API_KEY}
      - AI_BASE_URL=${AI_BASE_URL}
      - AI_MODEL=${AI_MODEL}
      - DATABASE_URL=${DATABASE_URL}
      - APP_HOST=0.0.0.0
      - APP_PORT=8000
      - ENVIRONMENT=${ENVIRONMENT:-production}
    volumes:
      - ./data:/app/data  # 数据持久化
    networks:
      - kuakua-network

  nginx:
    image: nginx:alpine
    container_name: kuakua-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl  # SSL 证书
    depends_on:
      - api
    networks:
      - kuakua-network

networks:
  kuakua-network:
    driver: bridge
```

创建 `/opt/kuakua-agent/nginx.conf`：

```nginx
events {
    worker_connections 1024;
}

http {
    upstream api {
        server api:8000;
    }

    # HTTP 重定向到 HTTPS
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # HTTPS 配置
    server {
        listen 443 ssl;
        server_name _;

        # SSL 证书（需自行申请并放置到 ssl 目录）
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # 安全头
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        location / {
            proxy_pass http://api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # CORS 配置（允许小程序域名访问）
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
        }
    }
}
```

#### 步骤 5: 配置多环境

创建环境配置文件：

```bash
# /opt/kuakua-agent/.env.dev
ENVIRONMENT=development
MODELSCOPE_API_KEY=your_api_key_here
AI_BASE_URL=https://api-inference.modelscope.cn/v1
AI_MODEL=deepseek-ai/DeepSeek-V3.2
DATABASE_URL=sqlite:///./data/kuakua_dev.db

# /opt/kuakua-agent/.env.prod
ENVIRONMENT=production
MODELSCOPE_API_KEY=your_api_key_here
AI_BASE_URL=https://api-inference.modelscope.cn/v1
AI_MODEL=deepseek-ai/DeepSeek-V3.2
DATABASE_URL=sqlite:///./data/kuakua_prod.db
```

使用不同端口运行多环境：

```bash
# 测试环境（端口 8001）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 生产环境（端口 8000）
docker-compose up -d
```

#### 步骤 6: 启动服务

```bash
cd /opt/kuakua-agent

# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f api

# 验证服务
curl http://localhost:8000/health
```

#### 步骤 7: 配置防火墙

在 Lighthouse 控制台 → 防火墙 → 添加规则：

| 协议 | 端口 | 策略 | 备注 |
|-----|------|------|------|
| TCP | 80 | 允许 | HTTP |
| TCP | 443 | 允许 | HTTPS |
| TCP | 8000 | 允许 | API 直接访问（可选） |

#### 步骤 8: 域名与 SSL 配置

1. **域名解析**：在 DNS 服务商添加 A 记录指向服务器 IP
2. **申请 SSL 证书**：使用 Certbot 免费申请

```bash
# 安装 Certbot
sudo apt install certbot

# 申请证书（需先停止 Nginx）
sudo certbot certonly --standalone -d api.kuakua-app.com

# 复制证书到项目目录
sudo cp /etc/letsencrypt/live/api.kuakua-app.com/fullchain.pem /opt/kuakua-agent/ssl/cert.pem
sudo cp /etc/letsencrypt/live/api.kuakua-app.com/privkey.pem /opt/kuakua-agent/ssl/key.pem

# 设置自动续期
sudo certbot renew --dry-run
```

---

## 多环境管理（测试/生产/灰度）

### 环境定义

| 环境 | 用途 | 数据隔离 | 访问控制 |
|-----|------|---------|---------|
| **开发环境 (dev)** | 本地/日常开发 | 独立测试数据 | 开发者内部 |
| **测试环境 (test)** | 功能测试/集成测试 | 模拟生产数据 | 测试团队 |
| **灰度环境 (gray)** | 小范围用户验证 | 生产数据子集 | 特定用户体验 |
| **生产环境 (prod)** | 正式对外服务 | 真实用户数据 | 全体用户 |

### CloudBase 多环境方案

```
┌─────────────────────────────────────────────────────────────┐
│                     小程序客户端                            │
│              （根据版本自动路由到不同环境）                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
   │  开发版  │        │ 体验版  │        │ 正式版  │
   │ (develop)│       │ (trial) │        │(release)│
   └────┬────┘        └────┬────┘        └────┬────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ kuakua-agent  │   │ kuakua-agent  │   │ kuakua-agent  │
│     -dev      │   │    -gray      │   │    -prod      │
│               │   │               │   │               │
│ • 最新功能     │   │ • 待发布功能   │   │ • 稳定版本    │
│ • 调试日志     │   │ • 小流量验证   │   │ • 全量用户    │
│ • 测试数据     │   │ • 生产数据     │   │ • 生产数据    │
└───────────────┘   └───────────────┘   └───────────────┘
```

**实现代码**（小程序端）：

```javascript
// utils/env.js
const ENVIRONMENTS = {
  dev: {
    name: 'development',
    baseUrl: 'https://kuakua-agent-dev-xxx.ap-shanghai.app.tcloudbase.com',
    cloudbaseEnv: 'kuakua-agent-dev',
    features: {
      debugLog: true,
      mockData: true
    }
  },
  gray: {
    name: 'gray',
    baseUrl: 'https://kuakua-agent-gray-xxx.ap-shanghai.app.tcloudbase.com',
    cloudbaseEnv: 'kuakua-agent-gray',
    features: {
      debugLog: false,
      grayRelease: true
    }
  },
  prod: {
    name: 'production',
    baseUrl: 'https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com',
    cloudbaseEnv: 'kuakua-agent-prod',
    features: {
      debugLog: false,
      analytics: true
    }
  }
};

const getCurrentEnv = () => {
  const info = wx.getAccountInfoSync();
  const envVersion = info.miniProgram.envVersion;
  
  const envMap = {
    'develop': 'dev',
    'trial': 'gray',
    'release': 'prod'
  };
  
  return ENVIRONMENTS[envMap[envVersion] || 'dev'];
};

module.exports = { ENVIRONMENTS, getCurrentEnv };
```

### Lighthouse 多环境方案

```
                    Nginx 路由层
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
   │  :8001  │      │  :8002  │      │  :8000  │
   │  /api   │      │  /api   │      │  /api   │
   │ (dev)   │      │ (gray)  │      │ (prod)  │
   └────┬────┘      └────┬────┘      └────┬────┘
        │                │                │
   ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
   │ FastAPI │      │ FastAPI │      │ FastAPI │
   │  Dev    │      │  Gray   │      │  Prod   │
   └─────────┘      └─────────┘      └─────────┘
```

**Nginx 多环境路由配置**：

```nginx
http {
    # 上游服务定义
    upstream api_dev {
        server localhost:8001;
    }
    upstream api_gray {
        server localhost:8002;
    }
    upstream api_prod {
        server localhost:8000;
    }

    # 根据 Header 路由到不同环境
    map $http_x_env $backend {
        default api_prod;
        "dev" api_dev;
        "gray" api_gray;
        "prod" api_prod;
    }

    server {
        listen 443 ssl;
        server_name api.kuakua-app.com;

        location /api/ {
            proxy_pass http://$backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Env $http_x_env;
        }
    }
}
```

---

## 小程序接入说明

### 1. 配置合法域名

登录微信公众平台 → 开发 → 开发设置 → 服务器域名：

| 类型 | 域名示例 |
|-----|---------|
| request 合法域名 | `https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com` |
| uploadFile 合法域名 | （如需要上传功能） |
| downloadFile 合法域名 | （如需要下载功能） |

### 2. 小程序代码示例

```javascript
// app.js
App({
  onLaunch() {
    // 初始化云开发（如使用 CloudBase）
    wx.cloud.init({
      env: this.getEnv().cloudbaseEnv,
      traceUser: true
    });
  },
  
  getEnv() {
    const info = wx.getAccountInfoSync();
    const envMap = {
      'develop': {
        baseUrl: 'https://kuakua-agent-dev-xxx.ap-shanghai.app.tcloudbase.com',
        cloudbaseEnv: 'kuakua-agent-dev'
      },
      'trial': {
        baseUrl: 'https://kuakua-agent-gray-xxx.ap-shanghai.app.tcloudbase.com',
        cloudbaseEnv: 'kuakua-agent-gray'
      },
      'release': {
        baseUrl: 'https://kuakua-agent-prod-xxx.ap-shanghai.app.tcloudbase.com',
        cloudbaseEnv: 'kuakua-agent-prod'
      }
    };
    return envMap[info.miniProgram.envVersion] || envMap['develop'];
  },
  
  globalData: {
    userInfo: null
  }
});
```

```javascript
// services/api.js
const app = getApp();

class ApiService {
  constructor() {
    this.baseUrl = app.getEnv().baseUrl;
  }
  
  async request(url, options = {}) {
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${this.baseUrl}${url}`,
        method: options.method || 'GET',
        data: options.data,
        header: {
          'Content-Type': 'application/json',
          ...options.header
        },
        success: (res) => {
          if (res.statusCode === 200) {
            resolve(res.data);
          } else {
            reject(new Error(res.data.message || '请求失败'));
          }
        },
        fail: reject
      });
    });
  }
  
  // 获取随机夸夸
  async getRandomQuote() {
    return this.request('/api/quotes/random');
  }
  
  // 获取场景夸夸
  async getSceneQuote(type) {
    return this.request(`/api/quotes/scene?type=${type}`);
  }
  
  // 添加到收藏
  async addFavorite(quoteId) {
    return this.request('/api/favorites', {
      method: 'POST',
      data: { quote_id: quoteId }
    });
  }
}

module.exports = new ApiService();
```

```javascript
// pages/index/index.js
const api = require('../../services/api');

Page({
  data: {
    quote: null,
    loading: false
  },
  
  async onLoad() {
    await this.loadRandomQuote();
  },
  
  async loadRandomQuote() {
    this.setData({ loading: true });
    try {
      const res = await api.getRandomQuote();
      if (res.code === 0) {
        this.setData({ quote: res.data });
      }
    } catch (error) {
      wx.showToast({
        title: '加载失败',
        icon: 'error'
      });
    } finally {
      this.setData({ loading: false });
    }
  },
  
  async onRefresh() {
    await this.loadRandomQuote();
  },
  
  async onFavorite() {
    if (!this.data.quote) return;
    try {
      await api.addFavorite(this.data.quote.id);
      wx.showToast({ title: '收藏成功' });
    } catch (error) {
      wx.showToast({ title: '收藏失败', icon: 'error' });
    }
  }
});
```

---

## 常见问题 FAQ

### CloudBase 相关

**Q: CloudBase 有公网 IP 吗？**
> A: CloudBase **不提供独立公网 IP**，而是提供自动分配的域名访问。你可以：
> 1. 使用自动分配的 `xxx.cloudbase.net` 域名
> 2. 绑定自己的自定义域名（需备案）
> 3. 小程序访问时，微信客户端会自动处理域名解析

**Q: CloudBase 的费用如何？**
> A: CloudBase 采用按量付费，有免费额度：
> - 云函数：每月 500 万次免费调用
> - 云托管：每月 1000 分钟免费 CPU/内存资源
> - 数据库：每月 1GB 免费存储
> - 超出部分按实际使用量计费

**Q: CloudBase 支持 WebSocket 吗？**
> A: 支持。CloudBase 云托管和云函数都支持 WebSocket，适合实时聊天场景。

### Lighthouse 相关

**Q: Lighthouse 的公网 IP 是固定的吗？**
> A: 是的，Lighthouse 实例分配**固定的公网 IP**，除非你销毁重建实例。

**Q: 如何备份 Lighthouse 上的数据？**
> A: 建议方案：
> 1. 使用 Docker Volume 挂载数据目录
> 2. 配置定时任务自动备份到 COS
> 3. 使用 Lighthouse 快照功能定期创建系统镜像

**Q: Lighthouse 可以升级配置吗？**
> A: 可以，支持在线升级 CPU、内存、带宽配置，升级后 IP 不变。

### 小程序接入相关

**Q: 小程序如何区分测试/生产环境？**
> A: 使用 `wx.getAccountInfoSync()` 获取当前版本：
> - `develop` - 开发版（开发者工具/预览）
> - `trial` - 体验版（上传后的体验版本）
> - `release` - 正式版（已发布版本）

**Q: 小程序访问后端需要配置 HTTPS 吗？**
> A: **必须**。小程序只支持 HTTPS 协议，且域名需要在微信公众平台配置为合法域名。

**Q: 如何实现灰度发布？**
> A: 推荐方案：
> 1. 通过体验版 (trial) 进行小范围测试
> 2. 使用用户 ID 哈希值控制流量比例（如 ID % 100 < 10 的用户走灰度环境）
> 3. 使用 feature flag 控制功能开关

---

## 附录

### 快速命令参考

```bash
# ===== CloudBase =====
# 登录
tcb login

# 部署
tcb framework:deploy --env-id kuakua-agent-prod

# 查看日志
tcb fn log --env-id kuakua-agent-prod --name kuakua-api

# ===== Lighthouse =====
# 连接服务器
ssh root@<服务器IP>

# Docker 常用命令
docker-compose up -d          # 启动
docker-compose down           # 停止
docker-compose logs -f api    # 查看日志
docker-compose pull && docker-compose up -d  # 更新

# Nginx 重载
nginx -s reload
```

### 相关链接

- [CloudBase 官方文档](https://docs.cloudbase.net/)
- [Lighthouse 官方文档](https://cloud.tencent.com/document/product/1207)
- [微信小程序开发文档](https://developers.weixin.qq.com/miniprogram/dev/framework/)
