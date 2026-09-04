# Changelog

本文件记录虎哥截图 Tauri 版本的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 变更

- 移除 VIP/支付/账号/设备限制模块，所有功能免费可用，不再需要登录、激活、次数配额或设备绑定。

---

## [0.1.26] - 2026-06-01

### 维护

- 版本号递增，确保已安装 0.1.25 的用户可通过软件内「检查更新」获取最新构建；功能与 0.1.25 一致（含旧版 Win10 双屏截图黑屏/壁纸修复）。

---

## [0.1.25] - 2026-06-01

### 修复

- **旧版 Win10 双屏截图/OCR 显示桌面壁纸或黑屏** — 根因：build<19041 跳过 WGC 后走 DXGI，DXGI 首帧常返回壁纸/累积帧，仅判全黑的黑帧检测拦不住，被当成有效截图落盘
  - 旧 Win10 改为**优先**整屏虚拟桌面 BitBlt（`GetDC(NULL)` 抓 DWM 合成全图再裁剪，`gdi-virtual-desktop`），DXGI 仅作兜底；预截图与区域截图路径策略一致
  - DXGI 兜底保留黑帧/超时多帧重试（最多 12 次）；旧 Win10 单次超时 100ms → 200ms

---

## [0.1.24] - 2026-05-25

### 修复

- **旧版 Win10 OCR/截图背景变成桌面壁纸** — build 19041 以下不再跳过 DXGI，恢复「DXGI + 黑帧检测 → GDI」；避免 GDI 只抓到壁纸层

---

## [0.1.23] - 2026-05-25

### 修复

- **工作台快捷键无法录制** — 设置页用 window 捕获阶段监听按键，避免按 Alt 时 blur 丢键；热键配置 JSON 与前端统一 camelCase
- **工作台默认热键** — 新安装/重置默认恢复为 `Alt+P`

---

## [0.1.22] - 2026-05-25

### 性能

- **现代 Windows 截图/OCR 弹出卡顿** — 在保留黑屏修复的前提下恢复接近旧版的响应速度
  - 支持 WDA 且已预加载时：预截图与 `overlay-reset` 并行；先显示遮罩，冻结背景异步加载
  - OCR 后隐藏复用 overlay 时跳过全桌面 `RedrawWindow`/`DwmFlush`（约省 2~3s）
- **overlay 热键预截图再提速** — WGC 成功后内存缓存立即可用，BMP 异步落盘，跳过 3K 屏同步 MD5
- **区域裁剪临时文件跳过 MD5** — 剪贴板/OCR 路径更快，历史入库仍单独算哈希
- **窗口探测** — 日志降为 DEBUG，前端节流 100ms

### 修复

- **第二次及后续截图选区框不出现** — 恢复 overlay 交互；hide/show 会话代守卫
- **截图高亮/标注后复制丢失** — 有标注时从合成 PNG 读剪贴板，不再误用无标注内存缓存
- **现代 Windows 第二次 OCR/截图卡顿甚至假死** — WDA 系统恢复 overlay 预加载与隐藏复用

---

## [0.1.21] - 2026-05-25

### 修复

- **旧版 Windows 10 截图/OCR 选区黑屏** — build 19041 以下优先 GDI，DXGI 全黑帧自动回退
  - Windows build 19041 以下跳过 WGC 后不再走 DXGI，直接使用 GDI 预截图与区域裁剪
  - 较新系统若 DXGI 返回近乎全黑帧，与 WGC 共用检测逻辑并回退 GDI

---

## [0.1.16] - 2026-05-16

### 修复

- **个别 Windows 用户截图 OCR 第二次黑屏** — 发布 overlay/WebView2 兼容修复
  - 应用启动时注入 WebView2 兼容参数，规避部分显卡驱动下的 WebView2 黑屏
  - 隐藏 overlay 后清除 `WDA_EXCLUDEFROMCAPTURE`，避免下次显示继承异常渲染状态
  - 接入单实例锁，重复启动时唤醒已有窗口并退出新进程，避免多个 overlay/热键状态互相干扰

---

## [0.1.15] - 2026-05-16

### 修复

- **手动下载链接证书报红** — 将手动更新和官网备用下载入口统一切换到有效证书域名 `hugescreenshot-dl.hudawang.cn`
  - 设置页“手动下载”不再指向旧的 `hugescreenshot.hudawang.cn`
  - 官网备用直连下载地址同步改为下载站域名
  - 官网默认备用版本号同步更新到 `v0.1.15`

---

## [0.1.14] - 2026-05-16

### 新增

- **应用内更新统一交互** — 顶部更新横幅与设置页“关于 > 更新”现在共享同一套状态与操作
  - 两处入口都支持检查更新、下载并安装、显示下载进度与安装状态
  - 任一入口触发下载后，另一处会同步显示相同的进度和状态
  - 保留手动下载链接作为兜底，不再是主更新路径

### 修复

- **设置页只提示新版本、无法直接更新** — `AboutSection` 改为复用 Tauri updater 共享状态，不再停留在文本提示
- **更新状态分裂** — `useAutoUpdate` 改为共享状态源，避免顶部横幅和设置页各自为政
- **主界面生命周期警告** — 移除异步初始化路径中的 `onUnmounted` 注册，避免测试与运行时 warning

---

## [0.1.13] - 2026-05-14

### 修复

- **第二次及后续截图黑屏、OCR 为空** — 预截图必须完成后才显示 overlay
  - 即使系统支持 `WDA_EXCLUDEFROMCAPTURE`，也不再与 overlay 显示并行截图
  - 规避用户机器上 WGC `0x80070005` 后回退 GDI 时捕获到全屏黑色 overlay 的问题
  - 新增截图显示顺序策略回归测试

---

## [0.1.12] - 2026-05-14

### 修复

- **第二次截图开始黑屏、OCR 识别为空** — 修复旧版 Windows 10 上 overlay 捕获排除标志不兼容导致预截图被黑屏遮罩污染的问题
  - Windows build 19041 以下不再设置 `WDA_EXCLUDEFROMCAPTURE`
  - 不支持该标志的系统会先完成预截图，再显示 overlay，避免 GDI 回退时捕获到覆盖窗口
  - 新增 Windows 版本兼容性回归测试

---

## [0.1.11] - 2026-05-14

### 修复

- **截图 overlay 崩溃与黑屏** — 修复预截图完成后通过全局事件广播触发 Tao/WebView 绘制事件循环重入的问题
  - `background-capture-ready`、`snapshot-ready` 仅发送给当前可见的 `overlay-*` 窗口，避免主窗口和其它 WebView 参与截图会话事件
  - Windows 刷新路径移除同步 `UpdateWindow`，改为异步重绘请求，降低 `WM_PAINT` 重入风险
  - 新增 overlay 事件目标回归测试

---

## [0.1.10] - 2026-05-12

### 修复

- **Anki 单词卡音标字段为空** — 修复有道 `fsearch` 响应解析逻辑
  - 旧正则强制要求 `<phonetic-symbol><![CDATA[...]]></phonetic-symbol>` 形式，但有道实际返回的是裸文本 `<phonetic-symbol>...</phonetic-symbol>`，导致音标字段始终为空
  - 现已切换到与 FastWordQuery 一致的完整 endpoint（带 `client=deskdict&doctype=xml&xmlVersion=3.2&le=eng&appVer=3.1.17.4208` 等参数），可同时获取 `<uk-phonetic-symbol>` 与 `<us-phonetic-symbol>`
  - 新增 `extract_xml_tag` 辅助函数，正则同时兼容裸文本与 CDATA 两种形式
  - 优先级：`UK [..]   US [..]` → `/us/` → `/uk/` → `/phonetic/`，行为对齐 FastWordQuery 的 `Youdao` 服务

---

## [0.1.1] - 2026-03-10

### 新增

#### OCR 工作台

- **添加编号功能** — 为识别文本逐行添加 `1. 2. 3.` 编号
  - 支持自动跳过空行
  - 智能替换已有编号格式（`1)` `1、` `1.` 等），统一为 `N. ` 格式

#### 规章管理系统

- **扫描+OCR 一键操作** — 合并本地扫描与 OCR 为单一命令
  - `regulation_scan_local_dir` 新增 `auto_ocr` 参数（默认 true），扫描完自动执行 OCR
  - 进度条支持扫描阶段和 OCR 阶段的连续显示
  - 移除独立的"OCR扫描版"按钮，简化用户操作
  - 新增 `regulation_retry_failed_ocr` 命令，支持重试失败的 OCR 文件
  - 扫描结果显示直接索引数、OCR 索引数，失败时显示重试按钮

### 优化

- **智能分段算法优化** — 提升 OCR 文本自动分段的准确性
  - 新增句末标点检测（。！？；…等），智能保留自然段落边界
  - 新增标题/标题行检测（如 "第X章"、"一、"、纯大写行等），标题前自动分段
  - 新增 Markdown 标题保护（`# ` 开头行独立成段）
  - 新增 CJK/Latin 混合边界处理，中英文衔接处不再误分段
  - 新增多空行压缩，连续空行合并为一个

### 修复

- **浅色/深色模式全面修复** — 修复 16+ 个文件中 80+ 处主题变量问题
  - 统一所有组件使用 `theme.css` 定义的 CSS 自定义属性
  - 修复浅色模式下出现黑色文字/背景的问题（根因：CSS 变量使用了深色硬编码回退值）
  - 涉及文件：ScheduledShutdownPanel、App.vue、HistoryListPanel、AnkiCardApp、AccountSection、DocumentFormatterDialog、SettingsGroup、MouseHighlightSettings、ToggleSwitch、SliderControl、ParameterSlider、PaymentDialog、SettingsPanel、OcrResultPanel 等
- **录制页面主题初始化修复** — `recording-control.html` 和 `recording-preview.html` 添加主题初始化脚本和 `theme.css` 导入
- **多个 HTML 入口主题修复** — `ocr-result.html`、`workbench.html`、`anki-card.html` 添加主题初始化脚本
- **更新进度百分比计算修复** — 进度值改为 0-100 百分比格式
- **截图引擎文档修正** — 统一为 WGC 优先、DXGI 仅用于录屏的准确描述
- **预截图缓存竞态修复** — `take_pre_capture_cache` 改为 `clone()`，避免 `capture_region` 找不到缓存

### 移除

- **移除 AI 智能分段功能** — 移除 `ai-smart-paragraphs` 格式化类型、`AI_FORMAT_PROMPT`、`formatTextAI()` 等相关代码，简化工具栏

### 性能优化

- **启动性能优化** — 解决应用启动时"未响应"黑屏问题
  - 将 `init_file_search_state` 缓存加载从主线程移到后台线程
  - 主线程 setup 从数秒优化到 0.05 秒完成
  - 新增 `app:ready` 事件，后台初始化完成后通知前端
  - 前端添加启动加载屏（splash screen），带动画和超时兜底

### 重构

- **规章状态管理重构** — 消除 store 和 composable 之间的职责混乱
  - store 添加 `startSyncCompare`/`finishSyncCompare` 封装方法
  - 组件统一通过 composable 访问 store 状态，移除直接 store 访问
  - 消除 `scanError`/`error` 重复状态复制

### 新增（之前）

#### 截图引擎

- **WGC (Windows Graphics Capture) 截图引擎** — 全新的截图捕获方案
  - 通过 HMONITOR 精确匹配显示器，彻底解决多显示器 ID 不一致问题
  - 支持 D3D11 设备缓存，重复截图性能极高
  - 截图策略升级为三级回退：WGC → DXGI → GDI (screenshots-rs)
  - 新增 `wgc_capture.rs` 模块（~310 行），支持 Windows 10 1903+

#### 规章管理系统

- **本地目录扫描** — 批量导入本地 PDF 规章文件
  - 支持递归扫描子目录，自动识别 PDF 文件
  - SHA256 文件哈希去重，避免重复入库
  - 文件名智能解析：自动提取文号（AC-xxx、CCAR-xxx、IB-xxx 等）和文档类型
  - pdf-extract 自动提取可选择文本，不可选择的标记为待 OCR
  - 实时进度事件 `regulation:scan-progress`，前端展示扫描进度条
  - 新增 `regulation_scan_local_dir` Tauri 命令

- **纯 Rust PDF OCR** — 替代 Python sidecar OCR 方案
  - 使用 pdfium-render 渲染 PDF 页面为图片，调用 PP-OCRv4 + OpenVINO 进行文字识别
  - 新增 `pdf_ocr.rs` 模块（~290 行），零外部 Python 依赖
  - 新增 `regulation_ocr_pending` / `regulation_ocr_update` / `regulation_get_ocr_queue` 命令
  - 捆绑 `pdfium.dll`（~5.5MB）作为 Tauri 资源

- **官网同步对比** — 与 CAAC 官网规章列表进行全量对比
  - Python sidecar 新增 `fetch_all` 方法，分页全量爬取规章列表
  - Rust 端 `regulation_sync_compare` 命令对比本地数据库差异
  - 展示新增规章、有效性变化、仅本地存在的文件

- **数据库统计仪表板** — 前端新增可视化统计
  - 显示总文件数、已索引、待处理、失败数量
  - 彩色进度条直观展示各状态占比（绿/黄/红）

- **搜索偏好持久化** — 自动记忆用户搜索设置
  - 搜索模式（在线/本地/混合）持久化到 localStorage
  - 筛选条件（文档类型、有效性、日期范围、关键词）自动保存和恢复

### 性能优化

- **截图复制/保存全面优化** — 消除巨型 JSON 序列化瓶颈
  - 新增 `save_screenshot_with_history_from_file` 命令，通过文件路径传递图像数据
  - 新增 `copy_file_to_clipboard` 命令，后端直接从磁盘读取文件写入剪贴板
  - 复制操作改为非阻塞：窗口立即关闭（~50ms），剪贴板写入在 Rust 后台完成
  - `handleCopy` 添加防重入保护（`isCopyInProgress`），防止双击触发多次调用
- **多场景统一优化** — OCR、钉图、Anki 等功能统一使用 `writeFile` 二进制 IPC
  - 替代 `Array.from(pngData)` + JSON 序列化的低效方案
  - 减少前后端数据传输量，尤其对大图像（>5MB）提升显著

### Bug 修复

- **DXGI 显示器匹配修复** — 改用屏幕坐标 (x, y, width, height) 匹配 DXGI 输出
  - 解决 screenshots-rs 原生 ID 与 DXGI 枚举索引不一致导致的截图黑屏/错屏问题
  - 录屏模块同步更新为坐标匹配方式
- **pdf-extract panic 防护** — 添加 `catch_unwind` 包裹
  - 修复不支持的 CID 字体编码（非 Identity-H）导致整个进程 crash
- **热键注册空值保护** — 跳过空字符串热键配置
  - 修复用户清空某个热键后保存导致启动异常
- **显示器索引回退** — `capture_screen` 增加按索引查找
  - 兼容 overlay 传入索引而非原生显示器 ID 的边界情况

### 依赖变更

- 新增 `pdfium-render = "0.8.37"`（PDF 渲染，用于规章 OCR）
- 新增 Windows API features：`Graphics_Capture`、`Graphics_DirectX`、`Win32_System_WinRT_Graphics_Capture` 等（WGC 截图引擎）
- 捆绑 `pdfium.dll`（Google PDFium 原生库，含许可证文件）

---

## [0.1.0] - 2026-01-24

### 新增

#### Rust 核心 (src-tauri)

- **截图引擎**
  - 使用 `screenshots-rs` 实现屏幕捕获
  - 支持多显示器截图
  - 支持高 DPI 场景（返回物理像素尺寸和 DPR）
  - 截图保存为临时文件，通过 `asset://` 协议访问

- **窗口检测**
  - 使用 Windows API 实现窗口边界检测
  - 支持获取窗口标题、类名、句柄
  - 支持指定坐标点的窗口查找

- **全局热键**
  - 使用 `tauri-plugin-global-shortcut` 注册热键
  - 默认截图热键 `Alt+A`
  - 支持热键配置持久化
  - 热键冲突检测和通知

- **窗口管理**
  - 覆盖窗口（截图选区）：全屏透明、置顶、捕获鼠标事件
  - 钉图窗口：支持调整大小、移动、透明度调节
  - 显示器信息获取：位置、尺寸、DPR、主显示器标识

- **Sidecar 管理器**
  - Python Sidecar 进程启动和停止
  - stdin/stdout JSON 通信协议
  - 请求/响应 ID 匹配
  - 崩溃自动重启机制（规划中）

- **数据库**
  - SQLite 历史记录表结构
  - 设置存储模块

- **设备管理**（独立模块，未集成）
  - 设备指纹生成（SMBIOS UUID + MAC + 磁盘序列号）
  - SHA-256 哈希

- **单实例锁**（独立模块，未集成）
  - Windows Mutex 实现
  - 重复启动检测

- **系统托盘**
  - 托盘图标配置
  - 托盘菜单

#### Vue 前端 (src)

- **状态管理 (Pinia)**
  - `screenshot.ts` - 截图状态
  - `annotation.ts` - 标注状态
  - `history.ts` - 历史记录状态
  - `settings.ts` - 设置状态
  - `sidecar.ts` - Sidecar 服务状态

- **截图组件**
  - `ScreenshotOverlay.vue` - 截图选区覆盖层

- **标注系统**
  - `AnnotationCanvas.vue` - 标注画布核心
  - `Toolbar.vue` - 工具栏组件
  - Command Pattern 实现 Undo/Redo

- **形状标注工具**
  - 矩形工具
  - 椭圆工具
  - 箭头工具
  - 直线工具
  - 支持颜色、线宽配置

- **文字标注工具**
  - 文字输入和编辑
  - 支持字体、颜色、大小配置

- **隐私工具**
  - 马赛克效果（像素化）
  - 高斯模糊效果

- **TypeScript 类型**
  - `screenshot.ts` - 截图相关类型
  - `annotation.ts` - 标注相关类型
  - `sidecar.ts` - Sidecar 协议类型
  - `config.ts` - 配置类型
  - `history.ts` - 历史记录类型

#### 文档

- `README.md` - 项目说明文档
- `CHANGELOG.md` - 版本变更记录

### 技术栈

#### Rust 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| tauri | 2.x | 应用框架 |
| screenshots | 0.8 | 屏幕捕获 |
| tauri-plugin-global-shortcut | 2.x | 全局热键 |
| tauri-plugin-fs | 2.x | 文件系统 |
| tauri-plugin-shell | 2.x | Shell 命令 |
| tauri-plugin-clipboard-manager | 2.x | 剪贴板 |
| tauri-plugin-dialog | 2.x | 对话框 |
| tokio | 1.x | 异步运行时 |
| rusqlite | 0.32 | SQLite |
| windows | 0.58 | Windows API |
| tracing | 0.1 | 日志 |
| thiserror | 2.x | 错误处理 |
| uuid | 1.x | UUID 生成 |
| proptest | 1.x | 属性测试 |

#### Vue 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| vue | 3.5 | UI 框架 |
| pinia | 3.x | 状态管理 |
| @tauri-apps/api | 2.x | Tauri IPC |
| typescript | 5.6 | 类型系统 |
| vite | 6.x | 构建工具 |

---

## 版本对比

| 版本 | 状态 | 说明 |
|------|------|------|
| Python v2.9.1 | 生产版本 | 当前稳定版本，功能完整 |
| Tauri v0.1.1 | 最新版本 | 主题修复、OCR 工作台优化、规章管理增强 |
| Tauri v0.1.0 | 初始发布 | 核心功能已实现 |

---

## 链接

- [Python 版本 README](../README.md)
- [设计文档](../.kiro/specs/tauri-rust-python-rewrite/design.md)
- [任务清单](../.kiro/specs/tauri-rust-python-rewrite/tasks.md)
