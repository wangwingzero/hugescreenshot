# OpenVINO 开发启动脚本
# 设置 OpenVINO 环境变量和 DLL 路径

$openvinoPath = Join-Path $PSScriptRoot "src-tauri\openvino"
$targetDebugPath = Join-Path $PSScriptRoot "src-tauri\target\debug"

# 设置 OPENVINO_DIR 环境变量（openvino-finder crate 会搜索这个目录）
$env:OPENVINO_DIR = $openvinoPath

# 添加到 PATH（Windows DLL 加载需要）
$env:PATH = "$openvinoPath;$targetDebugPath;$env:PATH"

Write-Host "✅ OpenVINO 环境变量已设置:"
Write-Host "   OPENVINO_DIR = $openvinoPath"
Write-Host ""
Write-Host "✅ DLL 路径已添加到 PATH:"
Write-Host "   - $openvinoPath"
Write-Host "   - $targetDebugPath"
Write-Host ""

# 启动 Tauri 开发服务器
npm run tauri dev
