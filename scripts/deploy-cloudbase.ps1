<#
.SYNOPSIS
    CloudBase 云托管一键部署脚本 (PowerShell)

.DESCRIPTION
    将 kuakua-agent 部署到腾讯云 CloudBase 云托管服务

.EXAMPLE
    .\scripts\deploy-cloudbase.ps1
    .\scripts\deploy-cloudbase.ps1 -Watch

.PARAMETER Watch
    部署后等待并监控部署状态

.PARAMETER EnvId
    CloudBase 环境 ID（默认: dev-kuakua-d1gmvqyrha28477fe）

.PARAMETER ServerName
    服务名称（默认: kuakua-api）
#>

param(
    [switch]$Watch,
    [string]$EnvId = "dev-kuakua-d1gmvqyrha28477fe",
    [string]$ServerName = "kuakua-api"
)

$ErrorActionPreference = "Stop"

# ==================== 配置 ====================

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cpu = 0.5
$Mem = 1
$MinNum = 1
$MaxNum = 5
$Port = 8080

# ==================== 辅助函数 ====================

function Write-Info($msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Blue }
function Write-Ok($msg)    { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ==================== 前置检查 ====================

Write-Info "项目目录: $ProjectDir"
Write-Info "环境 ID: $EnvId"
Write-Info "服务名称: $ServerName"

# 检查 Dockerfile
if (-not (Test-Path "$ProjectDir\Dockerfile")) {
    Write-Err "未找到 Dockerfile: $ProjectDir\Dockerfile"
}

# 检查 .env
$envFile = "$ProjectDir\.env"
if (-not (Test-Path $envFile)) {
    Write-Warn "未找到 .env 文件，将使用默认配置"
}

# ==================== 构建环境变量 ====================

function Build-EnvParams {
    $params = @{}

    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $parts = $line -split "=", 2
                if ($parts.Length -eq 2) {
                    $key = $parts[0].Trim()
                    $value = $parts[1].Trim()
                    $params[$key] = $value
                }
            }
        }
    }

    return $params | ConvertTo-Json -Compress
}

$EnvParams = Build-EnvParams
Write-Info "环境变量已从 .env 加载"

# ==================== 部署 ====================

Write-Info "开始部署 $ServerName 到 CloudBase..."

Set-Location $ProjectDir

# 使用 tcb CLI 部署
tcb cloudrun deploy `
    --envId $EnvId `
    --serviceName $ServerName `
    --serverType container `
    --cpu $Cpu `
    --mem $Mem `
    --minNum $MinNum `
    --maxNum $MaxNum `
    --port $Port `
    --dockerfile "Dockerfile" `
    --openAccessTypes "PUBLIC" `
    --envParams $EnvParams

Write-Ok "部署命令已提交！"

# ==================== 可选: 等待部署完成 ====================

if ($Watch) {
    Write-Info "等待部署完成..."

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 10
        Write-Host -NoNewline "`r⏳ 已等待 $($i * 10)s ... "

        try {
            $status = tcb cloudrun info --envId $EnvId --serviceName $ServerName 2>$null
            if ($status -match "normal") {
                Write-Host ""
                Write-Ok "部署完成！"
                break
            }
        } catch {}

        if ($i -eq 30) {
            Write-Host ""
            Write-Warn "等待超时（5分钟），请到控制台确认部署状态"
        }
    }
}

# ==================== 输出访问信息 ====================

Write-Host ""
Write-Host "========================================="
Write-Ok "部署信息:"
Write-Host "  服务名称: $ServerName"
Write-Host "  环境 ID:  $EnvId"
Write-Host "  访问地址:  https://${ServerName}-257074-7-1308646910.sh.run.tcloudbase.com"
Write-Host "  API 文档:  https://${ServerName}-257074-7-1308646910.sh.run.tcloudbase.com/docs"
Write-Host "  控制台:    https://tcb.cloud.tencent.com/dev?envId=${EnvId}#/platform-run"
Write-Host "========================================="
