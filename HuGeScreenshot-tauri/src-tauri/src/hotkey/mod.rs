//! 全局热键模块
//!
//! 本模块负责全局热键的注册、管理和事件处理。
//!
//! # 功能
//!
//! - 注册全局热键（即使应用不在前台也能响应）
//! - 热键冲突检测和通知
//! - 运行时热键更新
//! - 热键触发事件发送到前端
//!
//! # 子模块
//!
//! - `manager`: 热键管理器，负责热键的注册、注销和冲突检测
//!
//! # 使用示例
//!
//! ```ignore
//! use crate::hotkey::{HotkeyConfig, setup_hotkeys, update_hotkey};
//!
//! // 在应用启动时注册热键
//! let config = HotkeyConfig::default();
//! setup_hotkeys(&app, config)?;
//!
//! // 运行时更新热键
//! update_hotkey(&app, "screenshot", Some("Ctrl+Shift+A"), "Ctrl+Alt+S")?;
//! ```
//!
//! # 前端事件
//!
//! 热键触发时会发送以下事件到前端：
//!
//! - `hotkey-triggered`: 热键被按下时触发
//! - `hotkey-conflict`: 热键注册冲突时触发

pub mod manager;

// 重新导出常用类型
pub use manager::{
    is_hotkey_available, setup_hotkeys, unregister_all_hotkeys, unregister_hotkey, update_hotkey,
    HotkeyAction, HotkeyConfig, HotkeyConflictEvent, HotkeyEvent,
};
