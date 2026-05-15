# === 构建阶段：安装编译依赖 + pip install ===
FROM python:3.12-slim AS builder

WORKDIR /install

# 安装编译依赖（仅此阶段使用，不进最终镜像）
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install/deps -r requirements.txt

# === 运行阶段：只包含运行时文件，体积更小 ===
FROM python:3.12-slim

WORKDIR /app

# 从构建阶段复制已编译的依赖（无需 gcc，无需重新编译）
COPY --from=builder /install/deps /usr/local

# 创建非 root 用户
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# 复制应用代码
COPY app/ ./app/

# 将应用目录归属给非 root 用户
RUN chown -R appuser:appuser /app

# 注意：环境变量通过 CloudBase 云托管的环境变量配置注入，不打包进镜像

# 切换到非 root 用户
USER appuser

# CloudBase 默认使用 8080 端口
EXPOSE 8080

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
