# 虎哥截图 (HuGe Screenshot)

> 极致生产力体验 — 截图 + OCR 文字识别 + 翻译 + 文件搜索 + 录屏，一气呵成。

基于 **Rust + Tauri v2** 构建的高性能桌面效率工具。

## ✨ 功能特性

| 功能 | 完整版 | 精简版 |
|------|--------|--------|
| 截图 / OCR / 钉图 | ✅ | ✅ |
| 文件搜索（全盘秒搜） | ✅ | ✅ |
| 多引擎聚合翻译 | ✅ | ✅ |
| 文档检测（Word/WPS） | ✅ | ✅ |
| 公文格式化 | ✅ | ❌ |
| Anki 制卡 | ✅ | ❌ |
| 录屏 | ✅ | ❌ |

## 📥 下载安装

前往 [Releases](https://github.com/wangwingzero/hugescreenshot/releases) 下载最新版本。

- **完整版 (Full)** — 包含 Python Sidecar，支持全部功能
- **精简版 (Lite)** — 纯 Rust 实现，无 Python 依赖，体积更小启动更快

> 如果不需要公文格式化、Anki 制卡、录屏等功能，选择精简版即可。

## 🏗️ 技术栈

- **后端**: Rust (Tauri v2)
- **前端**: Vue 3 + TypeScript + Vite
- **OCR**: OpenVINO (本地离线)
- **数据库**: SQLite

## 📖 使用说明

详见 [使用指南](https://hudawang.cn/guide.html)

## 📄 License

[MIT](LICENSE)
