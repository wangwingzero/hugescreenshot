# 上传安装包到中国科技云数据胶囊
# 使用方法: .\scripts\upload_to_cstcloud.ps1 -Version "2.9.2"

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

# 配置
$BUCKET = "51a1fba687344079882622a15083f0d9"
$RCLONE = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\rclone.exe"
$EXE_PATH = "D:\screenshot\dist\HuGeScreenshot-$Version-Setup.exe"

Write-Host "🚀 开始上传安装包到中国科技云..." -ForegroundColor Cyan

# 检查文件是否存在
if (-not (Test-Path $EXE_PATH)) {
    Write-Host "❌ 错误: 找不到安装包 $EXE_PATH" -ForegroundColor Red
    exit 1
}

$fileSize = (Get-Item $EXE_PATH).Length / 1MB
Write-Host "📦 文件: HuGeScreenshot-$Version-Setup.exe ($([math]::Round($fileSize, 2)) MB)" -ForegroundColor Yellow

# 上传文件
Write-Host "📤 正在上传..." -ForegroundColor Cyan
& $RCLONE copy $EXE_PATH "cstcloud:$BUCKET/" --progress

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ 上传完成!" -ForegroundColor Green
    Write-Host "📥 下载链接: https://data.cstcloud.cn/s/yIbpfSGNLZZD" -ForegroundColor Cyan
    Write-Host "🔑 密码: uk2G" -ForegroundColor Cyan
} else {
    Write-Host "❌ 上传失败" -ForegroundColor Red
    exit 1
}
