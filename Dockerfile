# === 构建阶段：安装编译依赖 + pip install ===
FROM python:3.12-slim AS builder

WORKDIR /install

# 使用国内 Debian 镜像源加速 apt
RUN sed -i 's|deb.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list 2>/dev/null || true

# 安装编译依赖（仅此阶段使用，不进最终镜像）
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 使用国内 pip 镜像源加速安装
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --prefix=/install/deps -r requirements.txt

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

# 切换到非 root 用户
USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
