# 虎哥截图 - Tauri 版本

<p align="center">
  <img src="src-tauri/icons/icon.png" alt="虎哥截图" width="128" height="128">
</p>

<p align="center">
  <strong>高性能 Windows 桌面截图工具</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tauri-2.0-24C8D8.svg" alt="Tauri">
  <img src="https://img.shields.io/badge/Rust-1.70+-DEA584.svg" alt="Rust">
  <img src="https://img.shields.io/badge/Vue-3.5-4FC08D.svg" alt="Vue">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Platform">
</p>

---

## 简介

这是虎哥截图的 **Tauri 2.0 重写版本**，采用 Rust + Vue 3 + Python Sidecar 混合架构，相比原 Python 版本具有更快的启动速度和更低的内存占用。

### 与 Python 版本的区别

| 特性 | Python 版本 (v2.9.1) | Tauri 版本 (开发中) |
|------|---------------------|-------------------|
| 启动速度 | ~2-3 秒 | < 500ms |
| 内存占用 | ~150-200MB | < 50MB |
| 安装包大小 | ~80MB | ~15MB |
| GUI 框架 | PySide6 (Qt6) | Tauri + Vue 3 |
| 核心语言 | Python | Rust |
| AI 服务 | 内置 | Python Sidecar |

---

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vue 3 Frontend (WebView)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Screenshot│ │Annotation│ │ Toolbar  │ │ History  │ │Settings│ │
│  │ Overlay  │ │  Canvas  │ │          │ │  Panel   │ │ Panel  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│                    Pinia State Management                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Tauri IPC (invoke / events)
┌──────────────────────────────┴──────────────────────────────────┐
│                      Rust Core (Tauri 2.0)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Screenshot│ │ Hotkey   │ │ Window   │ │ Sidecar  │ │Database│ │
│  │  Engine  │ │ Manager  │ │ Manager  │ │ Manager  │ │ SQLite │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│                    Tokio Async Runtime                           │
└──────────────────────────────┬──────────────────────────────────┘
                               │ stdin/stdout JSON + 临时文件
┌──────────────────────────────┴──────────────────────────────────┐
│                   Python Sidecar (PyInstaller)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Translate │ │  Anki    │ │  Web     │ │ Document │ │ Record │ │
│  │ Service  │ │ Service  │ │ Scraper  │ │ Service  │ │ Service│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 职责划分

| 层级 | 职责 | 技术栈 |
|------|------|--------|
| **Vue Frontend** | UI 组件、状态管理、Canvas 标注 | Vue 3 + Pinia + TypeScript |
| **Rust Core** | 截图引擎、全局热键、窗口管理、IPC | Tauri 2.0 + Tokio + Windows API |
| **Python Sidecar** | 翻译、Anki、网页爬取、公文格式化 | Playwright + httpx |

---

## 功能状态

### 已完成

- [x] 屏幕截图（多显示器、高 DPI）
- [x] 窗口检测
- [x] 全局热键（Alt+A）
- [x] 覆盖窗口（截图选区）
- [x] 钉图窗口
- [x] 标注工具（矩形、椭圆、箭头、直线）
- [x] 文字标注
- [x] 马赛克/模糊工具
- [x] Pinia 状态管理
- [x] 系统托盘

### 开发中

- [ ] 图像导出（PNG/JPG/剪贴板）
- [ ] Python Sidecar 通信
- [ ] OCR 文字识别
- [ ] 翻译功能
- [ ] 历史记录
- [ ] 设置面板

### 计划中

- [ ] Anki 制卡
- [ ] 网页转 Markdown
- [ ] 公文格式化
- [ ] 录屏功能
- [ ] 自动更新

---

## 开发环境

### 前置要求

- **Node.js** 18+
- **Rust** 1.70+
- **pnpm** 或 **npm**
- **Windows 10/11**（仅支持 Windows）

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/HuGe/HuGeScreenshot.git
cd HuGeScreenshot/HuGeScreenshot-tauri

# 2. 安装前端依赖
npm install

# 3. 开发模式运行
npm run tauri dev

# 4. 生产构建
npm run tauri build

# 5. 本地模拟 GitHub Release 构建
npm run release:local

# 6. 本地构建并直接发布到 Cloudflare R2
npm run release:r2
```

### 常用命令

```bash
# 开发模式（热重载）
npm run tauri dev

# 生产构建
npm run tauri build

# 本地模拟 GitHub Release 构建（默认读取仓库根目录 .env）
npm run release:local

# 本地构建并上传到 Cloudflare R2（会覆盖根目录 latest.json）
npm run release:r2

# 本地构建并上传到自有 VPS 更新服务器（会覆盖站点根目录 latest.json）
npm run release:server

# 仅运行前端
npm run dev

# 仅运行 Rust 测试
cd src-tauri && cargo test

# 运行属性测试
cd src-tauri && cargo test --features proptest
```

### 本地发布到 R2

`release:r2` 会先调用本地发布构建，再按以下顺序发布：

1. 上传版本目录下的 `.exe` / `.sig` / `.nsis.zip` 等产物到 Cloudflare R2
2. 最后覆盖桶根目录的 `latest.json`
3. 可选镜像到自有服务器的 `latest.json`

这样可以避免 `latest.json` 先更新、安装包还没传完时客户端拿到坏链接。

默认发布链路使用本机 `rclone` 远程，生成的安装包下载地址会指向你在 `R2_PUBLIC_URL` 配置的公开域名：

```text
https://downloads.example.com
```

这个 Worker 只作为稳定入口；大文件请求会自动 307 跳转到 1 小时有效的 R2 签名直连地址，避免安装包经过 Worker 流式转发。当前已安装的客户端继续读取 VPS 上的 `latest.json`，但清单里的安装包 URL 会指向 Worker/R2 加速链路。

如果不用 `rclone`，可以加 `-UseAwsCli` 使用 AWS CLI。此时需要的环境变量：

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ACCOUNT_ID` 或 `R2_ENDPOINT`
- `R2_BUCKET` 或 `R2_BUCKET_NAME`
- `R2_PUBLIC_URL`，可选；默认是上面的 Worker 地址

可选环境变量：

- `CF_ZONE_ID`
- `CF_API_TOKEN`

示例：

```powershell
$env:R2_ACCESS_KEY_ID = "xxx"
$env:R2_SECRET_ACCESS_KEY = "xxx"
$env:R2_ACCOUNT_ID = "your-account-id"
$env:R2_BUCKET = "hugescreenshot"
powershell -ExecutionPolicy Bypass -File scripts/publish-release-r2-local.ps1 -UseAwsCli
```

### 本地发布到自有服务器

`release:server` 使用 `ssh`/`scp` 将本地发布产物上传到自有 VPS，并继续让应用内更新读取：

```text
https://downloads.example.com/latest.json
```

执行顺序与 R2 发布一致：先上传版本目录下的安装包和签名文件，最后原子覆盖站点根目录的 `latest.json`，避免客户端看到新版本但安装包还未上传完成。

注意：`latest.json` 里的安装包 URL 默认写入 Cloudflare Worker/R2 加速地址；VPS 主要保留官网、备案页和更新清单入口，不再让大安装包从 VPS 慢速直出。

SSH 参数不写入仓库，请通过 `scripts/release.env.ps1` 或环境变量提供：

- `RELEASE_SSH_HOST`
- `RELEASE_SSH_PORT`
- `RELEASE_SSH_USER`
- `RELEASE_SSH_KEY`
- `RELEASE_REMOTE_DIR`

示例：

```powershell
# 完整构建并发布
npm run release:server

# 只发布 build/local-release 中已经存在的产物，不重新构建
powershell -ExecutionPolicy Bypass -File scripts/publish-release-server-local.ps1 -SkipBuild
```

服务器需要先在 DNS/面板中把自己的发布域名指向该服务器，并配置 HTTPS。安装包目录可以长缓存，`latest.json` 建议配置 `no-store` 或很短缓存。

---

## 项目结构

```
HuGeScreenshot-tauri/
├── src-tauri/                    # Rust 后端
│   ├── src/
│   │   ├── main.rs               # 入口点
│   │   ├── lib.rs                # 库入口
│   │   ├── error.rs              # 统一错误类型
│   │   ├── screenshot/           # 截图引擎
│   │   │   ├── capture.rs        # 屏幕捕获
│   │   │   └── window_detect.rs  # 窗口检测
│   │   ├── hotkey/               # 全局热键
│   │   │   └── manager.rs        # 热键管理
│   │   ├── window/               # 窗口管理
│   │   │   ├── overlay.rs        # 覆盖窗口
│   │   │   └── pin.rs            # 钉图窗口
│   │   ├── sidecar/              # Python Sidecar
│   │   │   ├── manager.rs        # 进程管理
│   │   │   └── protocol.rs       # 通信协议
│   │   ├── database/             # SQLite 数据库
│   │   │   ├── history.rs        # 历史记录
│   │   │   └── settings.rs       # 设置存储
│   │   ├── single_instance/      # 单实例锁
│   │   │   └── lock.rs           # 互斥锁
│   │   └── commands/             # Tauri 命令
│   │       ├── screenshot_cmd.rs
│   │       ├── window_cmd.rs
│   │       ├── hotkey_cmd.rs
│   │       └── sidecar_cmd.rs
│   ├── Cargo.toml                # Rust 依赖
│   └── tauri.conf.json           # Tauri 配置
├── src/                          # Vue 前端
│   ├── main.ts                   # 主入口
│   ├── App.vue                   # 根组件
│   ├── components/               # Vue 组件
│   │   ├── screenshot/
│   │   │   └── ScreenshotOverlay.vue
│   │   └── annotation/
│   │       ├── AnnotationCanvas.vue
│   │       ├── Toolbar.vue
│   │       └── tools/            # 标注工具
│   ├── stores/                   # Pinia 状态
│   │   ├── screenshot.ts
│   │   ├── annotation.ts
│   │   ├── history.ts
│   │   ├── settings.ts
│   │   └── sidecar.ts
│   ├── types/                    # TypeScript 类型
│   ├── services/                 # 服务层
│   └── composables/              # Vue Composables
├── package.json                  # 前端依赖
└── vite.config.ts                # Vite 配置
```

---

## 技术栈

### Rust 后端

| 依赖 | 版本 | 用途 |
|------|------|------|
| `tauri` | 2.x | 应用框架 |
| `screenshots` | 0.8 | 屏幕捕获 |
| `tauri-plugin-global-shortcut` | 2.x | 全局热键 |
| `tokio` | 1.x | 异步运行时 |
| `rusqlite` | 0.32 | SQLite 数据库 |
| `windows` | 0.58 | Windows API |
| `tracing` | 0.1 | 日志系统 |
| `proptest` | 1.x | 属性测试 |

### Vue 前端

| 依赖 | 版本 | 用途 |
|------|------|------|
| `vue` | 3.5 | UI 框架 |
| `pinia` | 3.x | 状态管理 |
| `@tauri-apps/api` | 2.x | Tauri IPC |
| `typescript` | 5.6 | 类型系统 |
| `vite` | 6.x | 构建工具 |

---

## 性能目标

| 指标 | 目标值 | 红线值 |
|------|--------|--------|
| 启动时间 | < 500ms | < 1000ms |
| 截图延迟 | < 50ms | < 100ms |
| UI 响应 | < 16ms (60fps) | < 33ms (30fps) |
| 内存占用 | 30-50MB | < 200MB |

---

## 高 DPI 处理

> **原则**：「逻辑坐标负责交互，物理像素负责输出」

- **前端**：使用逻辑像素坐标，Tauri/WebView 自动处理映射
- **Rust 截图**：`CaptureResult` 包含 `dpr`，物理尺寸 = 逻辑尺寸 × DPR
- **导出**：导出时使用物理像素尺寸
- **禁止**：禁止在前端手动乘以 DPR

---

## 开发规范

### 代码风格

- **Rust**: 遵循 `rustfmt` 和 `clippy` 规范
- **TypeScript/Vue**: 遵循 ESLint + Prettier 规范
- **注释语言**: 中文

### 提交信息

使用中文，格式：`<类型>: <描述>`

```
feat: 添加马赛克工具
fix: 修复高 DPI 坐标计算问题
refactor: 重构截图引擎模块
docs: 更新 README
```

---

## 相关链接

- [Python 版本](../README.md) - 当前生产版本 v2.9.1
- [设计文档](../.kiro/specs/tauri-rust-python-rewrite/design.md)
- [任务清单](../.kiro/specs/tauri-rust-python-rewrite/tasks.md)

---

## 许可证

本项目采用 [CC BY-NC-ND 4.0](../LICENSE) 许可证。

- 允许个人学习和非商业使用
- 禁止商业使用
- 禁止修改和分发衍生作品

---

## 作者

虎大王
