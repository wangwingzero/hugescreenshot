# 网站部署脚本 - 上传 website 目录到腾讯云服务器
# 使用方法: .\scripts\deploy_website.ps1

$ErrorActionPreference = "Stop"

# 服务器配置
$SERVER_IP = "122.51.187.21"
$SERVER_USER = "root"
$REMOTE_PATH = "/www/wwwroot/hudawang"
$LOCAL_PATH = "website"
$SSH_KEY = "$PSScriptRoot\..\baota.pem"

Write-Host "🚀 开始部署网站到腾讯云服务器..." -ForegroundColor Cyan

# 检查本地目录
if (-not (Test-Path $LOCAL_PATH)) {
    Write-Host "❌ 错误: 找不到 $LOCAL_PATH 目录" -ForegroundColor Red
    exit 1
}

# 需要上传的文件
$files = @(
    "index.html",
    "confirm.html",
    "guide.html",
    "payment-success.html",
    "flight-tools-qr.jpg",
    "history-map-qr.jpg",
    "QRcode.png"
)

Write-Host "📦 准备上传以下文件:" -ForegroundColor Yellow
$files | ForEach-Object { Write-Host "   - $_" }

# 使用 scp 上传文件
Write-Host "`n📤 正在上传文件..." -ForegroundColor Cyan

foreach ($file in $files) {
    $localFile = Join-Path $LOCAL_PATH $file
    if (Test-Path $localFile) {
        Write-Host "   上传 $file ..." -NoNewline
        scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$localFile" "${SERVER_USER}@${SERVER_IP}:${REMOTE_PATH}/"
        if ($LASTEXITCODE -eq 0) {
            Write-Host " ✅" -ForegroundColor Green
        } else {
            Write-Host " ❌" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "   跳过 $file (文件不存在)" -ForegroundColor Yellow
    }
}

Write-Host "`n✅ 部署完成!" -ForegroundColor Green
Write-Host "🌐 访问 https://hudawang.cn 查看更新" -ForegroundColor Cyan
