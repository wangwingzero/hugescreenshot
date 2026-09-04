# 开发构建脚本 - 带日志记录
# 用法: .\scripts\build-dev.ps1 [dev|build|check]

param(
    [string]$Mode = "dev"
)

# 设置 UTF-8 编码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# 日志目录
$logDir = "D:\screenshot\日志\Rust版本日志"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 日志文件名
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "$logDir\build-$timestamp.log"

# 写入构建开始信息
$startTime = Get-Date
$header = @"
================================================================================
虎哥截图 Tauri 构建日志
时间: $startTime
模式: $Mode
================================================================================

"@
$header | Out-File -FilePath $logFile -Encoding UTF8

Write-Host "构建日志将保存到: $logFile" -ForegroundColor Cyan

# 切换到 src-tauri 目录
Push-Location $PSScriptRoot\..\src-tauri

try {
    switch ($Mode) {
        "dev" {
            Write-Host "运行 cargo check..." -ForegroundColor Yellow
            cargo check --color never 2>&1 | Tee-Object -FilePath $logFile -Append
        }
        "build" {
            Write-Host "运行 cargo build..." -ForegroundColor Yellow
            cargo build --color never 2>&1 | Tee-Object -FilePath $logFile -Append
        }
        "release" {
            Write-Host "运行 cargo build --release..." -ForegroundColor Yellow
            cargo build --release --color never 2>&1 | Tee-Object -FilePath $logFile -Append
        }
        "check" {
            Write-Host "运行 cargo check..." -ForegroundColor Yellow
            cargo check --color never 2>&1 | Tee-Object -FilePath $logFile -Append
        }
        default {
            Write-Host "未知模式: $Mode，使用 cargo check" -ForegroundColor Yellow
            cargo check --color never 2>&1 | Tee-Object -FilePath $logFile -Append
        }
    }
    
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

# 写入构建结束信息
$endTime = Get-Date
$duration = $endTime - $startTime
$footer = @"

================================================================================
构建结束: $endTime
耗时: $($duration.TotalSeconds.ToString("F2")) 秒
退出码: $exitCode
================================================================================
"@
$footer | Out-File -FilePath $logFile -Encoding UTF8 -Append

if ($exitCode -eq 0) {
    Write-Host "`n构建成功! 耗时 $($duration.TotalSeconds.ToString("F2")) 秒" -ForegroundColor Green
} else {
    Write-Host "`n构建失败! 查看日志: $logFile" -ForegroundColor Red
}

exit $exitCode
