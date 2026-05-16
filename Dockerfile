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

# 复制应用代码（最常变动，放最后，不影响依赖缓存层）
COPY app/ ./app/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
