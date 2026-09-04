# 虎哥截图 (HuGe Screenshot)

<p align="center">
  <img src="resources/虎哥截图.ico" alt="虎哥截图" width="128" height="128">
</p>

<p align="center">
  <strong>极致生产力体验</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.10.1-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.8+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-CC%20BY--NC--ND%204.0-red.svg" alt="License">
</p>

---

## ✨ 功能特性

### 📸 截图功能
- 全屏截图 / 区域选择
- 智能窗口检测
- 多显示器支持
- 全局热键（默认 `Alt+A`）

### 🎨 标注工具
- 矩形、椭圆、箭头、直线
- 画笔自由绘制
- 文字标注（支持内联编辑，点击已有文字可直接修改）
- 马赛克打码

### 🔤 OCR 文字识别
- **本地识别**：RapidOCR（OpenVINO 后端）
- **跨平台支持**：支持 Intel 和 AMD CPU
- **OCR 评分显示**：显示识别置信度，帮助评估识别质量
- **后端信息显示**：显示当前使用的 OCR 后端类型
- **内存优化**：OpenVINO 缓存容量限制，解决动态形状内存泄漏
- **扁平图像优化**：自动放大矮小图像、边距填充、放大后锐化
- **云端识别**：百度云 / 腾讯云 OCR API（可选）

### 🌐 翻译功能
- 自动降级：主引擎失败自动切换备用引擎
- 增强翻译：支持定时翻译、翻译缓存

### 🖥️ 屏幕翻译器
- 实时翻译屏幕文字
- 支持选区翻译

### 📌 贴图功能
- 将截图钉在桌面任意位置
- 支持透明度调节
- 支持缩放

### 📚 Anki 制卡
- 与 AnkiConnect 集成
- 一键创建单词卡片
- 支持图片 + 文字 + 翻译
- 后台导入：不阻塞截图操作
- **单词卡图片 API**：支持 Unsplash/Pixabay 配置，多 Key 轮换

### 🖼️ 图片拼接
- 多张截图垂直/水平拼接
- 支持自定义间距

###  🎬 录屏功能
- 区域录制 / 全屏录制
- H.264 编码，高质量低体积
- 支持暂停/继续录制
- 录制时红色边框指示
- 录制完成后预览、另存为、复制
- 可选依赖：需安装 dxcam 和 av

### 📜 CAAC 规章查询
- 在线搜索民航规章和规范性文件
- 支持按标题、文号、发布单位搜索
- 支持按文档类型、有效性、日期范围筛选
- 日期快捷预设：近3天、近7天、近30天、自定义
- PDF 下载，自动按文档类型分类保存
- 批量下载：支持多选文档批量下载
- 文件命名规则：[失效!]文号标题.pdf

### 📝 网页转 Markdown
- 点击浏览器窗口自动获取当前页面 URL
- 使用 Trafilatura 提取网页正文
- 自动保存为 Markdown 文件
- 内容自动复制到剪贴板
- 支持 Chrome、Edge、Firefox 等主流浏览器
- **智能反爬虫**：自动检测反爬虫网站，使用浏览器模式获取
- **自学习域名**：HTTP 失败后自动记住该域名，下次直接用浏览器模式
- **批量转换**：支持多个 URL 排队转换，完成后显示汇总通知

### 📄 Word/WPS 公文格式化
- 在主界面侧边栏打开 `Word排版`
- 请选择已保存且已关闭的 `.docx` 文档进行排版
- 排版结果会在原文件同目录生成新的 `*_formatted.docx` 文件，不覆盖原文件
- 自动设置字体、字号、行距、页边距等
- 符合《党政机关公文格式》国家标准

### 🔄 自动更新
- 启动时自动检查新版本
- 托盘菜单手动检查更新
- 设置页面查看版本信息和更新说明
- 非模态下载进度窗口，不阻塞主程序
- **代理自动切换**：下载超时时自动尝试其他代理
- **自动重启更新**：下载完成后自动启动新版本并清理旧版本

### 🎯 鼠标高亮
- 演示增强工具，适用于录屏和直播
- 多种效果：光圈、聚光灯、指针放大、点击动效
- 可自由组合效果
- 三种预设配色主题
- 全局快捷键 (Alt+M) 快速开关
- 多显示器支持

### 🛠️ 系统工具
- **电源管理**：关机、重启、睡眠、锁屏、定时关机
- **闹钟提醒**：设置提醒时间，支持重复提醒
- **番茄钟**：专注工作计时器，工作/休息自动切换
- **网络测速**：测试下载/上传速度，保存历史记录

### 👤 使用说明
- 所有功能免费使用
- 无需登录、注册或激活
- 无每日次数和设备数量限制

---

## 📦 下载

下载 `HuGeScreenshot-x.x.x.exe` 即可使用，支持所有 CPU（Intel/AMD）。

> ⚠️ **重要提示**：请勿修改 EXE 文件名，否则自动更新功能可能无法正常工作。

---

## 🚀 快速开始

### 从源码运行

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r screenshot_tool/requirements.txt

# 运行
python 虎哥截图.pyw
```

---

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt+A` | 开始截图 |
| `Alt+M` | 启用/禁用鼠标高亮 |
| `Esc` | 取消截图 / 退出模式 |
| `Enter` | 确认截图 |
| `Ctrl+C` | 复制到剪贴板 |
| `Ctrl+S` | 保存到文件 |

托盘菜单功能：
- 📝 网页转MD - 网页转 Markdown 模式
- 📜 规章查询 - CAAC 规章和规范性文件查询

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | PySide6 (Qt6) |
| 图像处理 | OpenCV, Pillow |
| 屏幕截图 | mss |
| OCR 引擎 | RapidOCR (OpenVINO) |
| 网页提取 | Trafilatura |
| Windows API | pywin32 |
| Office 自动化 | pywin32 (COM) |
| 后端服务 | Supabase (认证、数据库) |

---

## 📁 项目结构

```
├── 虎哥截图.pyw              # 主入口
├── screenshot_tool/          # 源代码包
│   ├── core/                # 核心功能模块
│   │   ├── config_manager.py        # 配置管理
│   │   ├── screenshot_manager.py    # 截图管理
│   │   ├── markdown_mode_manager.py # 网页转 Markdown 模式
│   │   ├── gongwen_mode_manager.py  # 公文模式管理
│   │   └── ...
│   ├── services/            # 外部服务
│   │   ├── ocr_manager.py          # OCR 引擎调度
│   │   ├── rapid_ocr_service.py    # RapidOCR 本地引擎
│   │   ├── backend_selector.py     # OCR 后端选择
│   │   ├── openvino_optimizer.py   # OpenVINO 优化
│   │   ├── markdown_converter.py   # 网页转 Markdown 转换器
│   │   ├── browser_fetcher.py      # 浏览器模式获取网页
│   │   ├── update_service.py       # 自动更新服务
│   │   ├── image_stitcher.py       # 图片拼接
│   │   ├── enhanced_translation_service.py # 增强翻译
│   │   ├── background_anki_importer.py # 后台 Anki 导入
│   │   └── ...
│   ├── ui/                  # 用户界面
│   │   ├── screen_translator.py    # 屏幕翻译器
│   │   └── ...
│   └── tests/               # 测试文件
├── build/                   # 打包配置
│   └── 虎哥截图-dir.spec     # PyInstaller 配置
├── resources/               # 资源文件
└── docs/                    # 文档
```

---

## 🔧 配置

配置文件位置：`~/.screenshot_tool/config.json`

支持便携模式：将 `config.json` 放在程序同目录下即可。

---

## 📦 打包

```powershell
# 激活虚拟环境
.venv\Scripts\activate

# 一键构建安装包（推荐）
python build/build_installer.py

# 或分步执行：
# 1. PyInstaller 目录模式打包
pyinstaller build/虎哥截图-dir.spec --noconfirm --clean

# 2. Inno Setup 编译安装包
iscc build/虎哥截图.iss
```

输出文件：`dist/HuGeScreenshot-{版本号}-Setup.exe`

---

## 📄 许可证

本项目采用 [CC BY-NC-ND 4.0](LICENSE) 许可证。

- ✅ 允许个人学习和非商业使用
- ❌ 禁止商业使用
- ❌ 禁止修改和分发衍生作品

---

## 👤 作者

虎大王

## 🙏 致谢

- [梦想的边缘](https://github.com/sunwocd) - 民航大百科老师
