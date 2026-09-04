# 虎哥截图 (HuGe Screenshot)

<p align="center">
  <img src="HuGeScreenshot-tauri/resources/PNG/虎哥截图.png" alt="虎哥截图" width="128" height="128">
</p>

<p align="center">
  <strong>Windows 桌面截图与生产力工具</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.26-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tauri-2.0-24C8D8.svg" alt="Tauri">
  <img src="https://img.shields.io/badge/Rust-stable-DEA584.svg" alt="Rust">
  <img src="https://img.shields.io/badge/Vue-3.5-4FC08D.svg" alt="Vue">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Platform">
</p>

---

## 简介

虎哥截图是使用 Tauri 2 / Rust / Vue 3 / TypeScript 开发的 Windows 桌面截图工具。当前代码已完全迁移到 Rust 原生实现，不再依赖 Python Sidecar。

所有功能免费开放，无需登录、注册、VIP、激活码或设备数量限制。

---

## 功能

- 截图：全屏、区域、窗口检测、多显示器、高 DPI
- 标注：矩形、椭圆、箭头、直线、画笔、文字、马赛克
- OCR：本地 OpenVINO + PP-OCRv4，支持置信度、文字框、复制和再识别
- 翻译：OCR 结果翻译，支持多语言和翻译面板
- 工作台：截图历史、OCR 内容、搜索、复制、翻译、虚拟滚动
- 贴图：截图钉在桌面，支持透明度、缩放和鼠标穿透
- 录屏：区域/全屏录制、暂停/继续、录制边框、完成后预览
- 文件搜索：本地文件索引与全文搜索（独立 `file-search-service` Windows 服务）
- 鼠标高亮：光圈、聚光灯、指针放大、点击动效
- 预约关机/系统电源操作
- 文件转 Markdown：PDF、DOCX、HTML、纯文本
- 网页转 Markdown
- 系统托盘、全局热键、自动更新检查界面、崩溃报告

---

## 最新 Release

当前版本：`0.1.26`

GitHub Actions 的 `Build & Release` 工作流会构建 Windows NSIS 安装包并生成 Release 草稿。手动触发时可以直接传入版本号：

```powershell
gh workflow run build.yml -R wangwingzero/hugescreenshot
```

如需支持软件内自动更新，还需要：

1. 在 [tauri.conf.json](HuGeScreenshot-tauri/src-tauri/tauri.conf.json) 中开启 `createUpdaterArtifacts`
2. 在 GitHub Actions Secrets 配置 `TAURI_SIGNING_PRIVATE_KEY` 和 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
3. 将 updater endpoints 改为你自己的真实更新地址

---

## 开发环境

### 前置要求

- Windows 10/11
- Node.js 20+
- Rust stable
- npm

### 快速开始

```bash
cd HuGeScreenshot-tauri
npm install
npm run tauri:dev
```

### 常用命令

```bash
# 前端开发模式
npm run dev

# 前端类型检查与生产构建
npm run build

# 前端测试
npm run test:run

# Rust 测试
cd src-tauri
cargo test

# Rust 属性测试
cargo test --features proptest

# 本地打包 Windows 安装包
npm run release:local
```

### GitHub Actions 构建

根目录的 `.github/workflows/build.yml` 当前会：

1. 在 `windows-latest` 上安装 Node.js 和 Rust
2. 安装前端依赖
3. 准备 Windows 运行库
4. 构建 Tauri Release
5. 收集 NSIS 安装包并上传为 Actions Artifact
6. 创建 GitHub Release 草稿

注意：当前工作流为无签名验证配置，先保证 Action 可以跑通；正式发布软件内更新时按上面的签名配置启用。

---

## 项目结构

```text
.
├── .github/workflows/build.yml   # GitHub Actions Windows 构建
├── HuGeScreenshot-tauri/         # 实际应用
│   ├── src/                      # Vue 3 + TypeScript 前端
│   ├── src-tauri/                # Tauri Rust 后端
│   │   └── src/
│   │       ├── screenshot/       # WGC / DXGI / GDI 截图
│   │       ├── ocr/              # OpenVINO + PP-OCRv4
│   │       ├── recording/        # 录屏
│   │       ├── converter/        # 文档转 Markdown
│   │       ├── file_search/      # 文件搜索服务客户端
│   │       ├── hotkey/           # 全局热键
│   │       ├── window/           # 遮罩与贴图窗口
│   │       ├── database/         # SQLite 历史与设置
│   │       └── commands/         # Tauri 命令
│   ├── scripts/                  # 构建与发布脚本
│   ├── infra/                    # Cloudflare / R2 辅助
│   └── package.json              # 前端依赖与脚本
├── resources/                    # 图标与静态资源
└── docs/                         # 文档
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面框架 | Tauri 2.0 |
| 前端 | Vue 3.5 + TypeScript + Pinia + Vite |
| 原生后端 | Rust + Tokio |
| 截图 | Windows Graphics Capture / DXGI / GDI |
| OCR | OpenVINO + PP-OCRv4 |
| 数据库 | SQLite（rusqlite） |
| 录屏 | DXGI + FFmpeg |
| 文件索引 | Tantivy + NTFS 服务 |

---

## 许可证

以仓库根目录 [LICENSE](LICENSE) 为准：CC BY-NC-ND 4.0。

Copyright (c) 2024-2026 虎大王 (HuGe)
