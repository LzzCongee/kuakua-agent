#!/usr/bin/env bash
#
# CloudBase 云托管一键部署脚本
#
# 用法:
#   ./scripts/deploy-cloudbase.sh           # 默认部署
#   ./scripts/deploy-cloudbase.sh --watch    # 部署并等待完成
#
# 前置条件:
#   1. 安装 CloudBase CLI: npm i -g @cloudbase/cli
#   2. 登录: tcb login
#
# 环境变量（可选，覆盖默认值）:
#   TCB_ENV_ID      - CloudBase 环境 ID
#   TCB_SERVER_NAME - 服务名称
#   TCB_CPU         - CPU 核心数
#   TCB_MEM         - 内存 GB
#   TCB_MIN_NUM     - 最小实例数
#   TCB_MAX_NUM     - 最大实例数
#

set -euo pipefail

# ==================== 配置 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 从 cloudbaserc.json 读取默认配置
ENV_ID="${TCB_ENV_ID:-dev-kuakua-d1gmvqyrha28477fe}"
SERVER_NAME="${TCB_SERVER_NAME:-kuakua-api}"
CPU="${TCB_CPU:-0.5}"
MEM="${TCB_MEM:-1}"
MIN_NUM="${TCB_MIN_NUM:-1}"
MAX_NUM="${TCB_MAX_NUM:-5}"
PORT=8080

# ==================== 颜色输出 ====================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ==================== 前置检查 ====================

info "项目目录: $PROJECT_DIR"
info "环境 ID: $ENV_ID"
info "服务名称: $SERVER_NAME"

# 检查 tcb CLI
if ! command -v tcb &> /dev/null; then
    error "未找到 tcb CLI，请先安装: npm i -g @cloudbase/cli"
fi

# 检查 Dockerfile
if [ ! -f "$PROJECT_DIR/Dockerfile" ]; then
    error "未找到 Dockerfile: $PROJECT_DIR/Dockerfile"
fi

# 检查 .env 文件
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    error "未找到 .env 文件: $ENV_FILE，请先从 .env.example 创建"
fi

# ==================== 构建环境变量 ====================

build_env_params() {
    # 使用 jq 如果可用，否则用 python
    local env_file="$PROJECT_DIR/.env"
    local tmp_json="/tmp/cloudbase-env-$$.json"

    # 1. 从 .env 文件读取
    echo "{" > "$tmp_json"
    local first=true
    while IFS='=' read -r key value; do
        # 跳过注释和空行
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)

        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> "$tmp_json"
        fi
        printf '  "%s": "%s"' "$key" "$value" >> "$tmp_json"
    done < "$env_file"

    # 2. 生产环境覆盖
    cat >> "$tmp_json" <<'OVERRIDES'
,
  "APP_PORT": "8080",
  "APP_HOST": "0.0.0.0",
  "ENVIRONMENT": "production",
  "LOG_LEVEL": "INFO",
  "USE_CLOUDBASE": "true",
  "CLOUDBASE_ENV_ID": "__ENV_ID__"
OVERRIDES

    echo "" >> "$tmp_json"
    echo "}" >> "$tmp_json"

    # 替换环境 ID 占位符
    sed -i.bak "s/__ENV_ID__/$ENV_ID/g" "$tmp_json" && rm -f "${tmp_json}.bak"

    # 用 python 验证 JSON 并压缩
    if command -v python3 &> /dev/null; then
        python3 -c "import json,sys; d=json.load(open('$tmp_json')); json.dump(d,sys.stdout,separators=(',',':'))" 2>/dev/null
    elif command -v python &> /dev/null; then
        python -c "import json,sys; d=json.load(open('$tmp_json')); json.dump(d,sys.stdout,separators=(',',':'))" 2>/dev/null
    else
        # 没有 python，直接输出（可能格式不完美）
        cat "$tmp_json" | tr -d '\n' | sed 's/  //g'
    fi

    rm -f "$tmp_json"
}

ENV_PARAMS=$(build_env_params)
info "环境变量已从 .env 加载"
info "生产环境覆盖: APP_PORT=8080, ENVIRONMENT=production, LOG_LEVEL=INFO"

# ==================== 部署 ====================

info "开始部署 $SERVER_NAME 到 CloudBase..."

cd "$PROJECT_DIR"

tcb cloudrun deploy \
    --envId "$ENV_ID" \
    --serviceName "$SERVER_NAME" \
    --serverType container \
    --cpu "$CPU" \
    --mem "$MEM" \
    --minNum "$MIN_NUM" \
    --maxNum "$MAX_NUM" \
    --port "$PORT" \
    --dockerfile "Dockerfile" \
    --openAccessTypes "PUBLIC" \
    --envParams "$ENV_PARAMS"

ok "部署命令已提交！"

# ==================== 可选: 等待部署完成 ====================

if [[ "${1:-}" == "--watch" ]]; then
    info "等待部署完成..."
    echo ""

    for i in $(seq 1 30); do
        sleep 10
        # 查询服务状态
        status=$(tcb cloudrun info --envId "$ENV_ID" --serviceName "$SERVER_NAME" 2>/dev/null || echo "unknown")
        echo -ne "\r⏳ 已等待 $((i * 10))s ... "

        if echo "$status" | grep -q "normal"; then
            echo ""
            ok "部署完成！"
            break
        fi

        if [ "$i" -eq 30 ]; then
            echo ""
            warn "等待超时（5分钟），请到控制台确认部署状态"
        fi
    done
fi

# ==================== 输出访问信息 ====================

echo ""
echo "========================================="
ok "部署信息:"
echo "  服务名称: $SERVER_NAME"
echo "  环境 ID:  $ENV_ID"
echo "  访问地址:  https://${SERVER_NAME}-257074-7-1308646910.sh.run.tcloudbase.com"
echo "  API 文档:  https://${SERVER_NAME}-257074-7-1308646910.sh.run.tcloudbase.com/docs"
echo "  控制台:    https://tcb.cloud.tencent.com/dev?envId=${ENV_ID}#/platform-run"
echo "========================================="
