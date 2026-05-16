# === 构建阶段：安装编译依赖 + pip install ===
FROM python:3.12-slim AS builder

WORKDIR /install

# 使用国内 Debian 镜像源加速 apt
RUN sed -i 's|deb.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tencent.com|g' /etc/apt/sources.list 2>/dev/null || true

# 安装编译依赖（仅此阶段使用，不进最终镜像）
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# pip 镜像源配置：支持多源自动回退，也可通过构建参数覆盖主镜像源
# 用法：docker build --build-arg PIP_INDEX_URL=https://xxx/simple
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

RUN set -e; \
    echo "==> 尝试主镜像源: ${PIP_INDEX_URL}"; \
    pip install --no-cache-dir \
        -i "${PIP_INDEX_URL}" \
        --trusted-host "${PIP_TRUSTED_HOST}" \
        --prefix=/install/deps -r requirements.txt \
    || { echo "==> 主镜像源失败，尝试腾讯云镜像"; \
         pip install --no-cache-dir \
             -i https://mirrors.cloud.tencent.com/pypi/simple \
             --trusted-host mirrors.cloud.tencent.com \
             --prefix=/install/deps -r requirements.txt; } \
    || { echo "==> 腾讯云镜像失败，尝试阿里云镜像"; \
         pip install --no-cache-dir \
             -i https://mirrors.aliyun.com/pypi/simple \
             --trusted-host mirrors.aliyun.com \
             --prefix=/install/deps -r requirements.txt; } \
    || { echo "==> 阿里云镜像失败，尝试清华镜像"; \
         pip install --no-cache-dir \
             -i https://pypi.tuna.tsinghua.edu.cn/simple \
             --trusted-host pypi.tuna.tsinghua.edu.cn \
             --prefix=/install/deps -r requirements.txt; } \
    || { echo "==> 国内镜像均失败，使用官方 PyPI"; \
         pip install --no-cache-dir \
             --prefix=/install/deps -r requirements.txt; }

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
