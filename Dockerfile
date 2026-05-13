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
