//! Tauri 命令模块
//!
//! 本模块定义所有暴露给前端的 Tauri 命令。
//! 命令按功能分类到不同的子模块中。
//!
//! # 子模块
//!
//! - `screenshot_cmd`: 截图相关命令
//! - `hotkey_cmd`: 热键相关命令
//! - `window_cmd`: 窗口相关命令
//! - `native_cmd`: OCR / 翻译 / 文档检测（原生 Rust 实现，原 Sidecar 已废弃）
//! - `history_cmd`: 历史记录相关命令
//! - `tray_cmd`: 托盘相关命令
//! - `config_cmd`: 配置相关命令
//! - `update_cmd`: 自动更新相关命令
//! - `mouse_highlight_cmd`: 鼠标高亮相关命令
//! - `clipboard_cmd`: 剪贴板相关命令
//! - `shutdown_cmd`: 定时关机相关命令
//! - `file_search_cmd`: 文件搜索相关命令
//! - `file_cmd`: 文件操作相关命令
//! - `converter_cmd`: 文件转 Markdown 命令（纯 Rust 实现）

pub mod clipboard_cmd;
pub mod config_cmd;
pub mod converter_cmd;
pub mod file_cmd;
pub mod file_search_cmd;
pub mod history_cmd;
pub mod hotkey_cmd;
pub mod mouse_highlight_cmd;
pub mod native_cmd;
pub mod recording_cmd; // 原生录屏命令
pub mod screenshot_cmd;
pub mod shutdown_cmd;
pub mod tray_cmd;
pub mod update_cmd;
pub mod window_cmd;

// 重新导出所有命令，方便在 lib.rs 中注册
pub use clipboard_cmd::*;
pub use config_cmd::*;
pub use converter_cmd::*;
pub use file_cmd::*;
pub use file_search_cmd::*;
pub use history_cmd::*;
pub use hotkey_cmd::*;
pub use mouse_highlight_cmd::*;
pub use native_cmd::*;
pub use screenshot_cmd::*;
pub use shutdown_cmd::*;
pub use tray_cmd::*;
pub use update_cmd::*;
pub use window_cmd::*;
