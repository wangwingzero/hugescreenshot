//! 系统托盘模块
//!
//! 提供系统托盘功能，包括：
//! - 托盘图标显示
//! - 右键菜单
//! - 状态图标切换
//! - 最小化到托盘
//! - 双击显示主窗口

use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Arc;
use tauri::{
    image::Image,
    menu::{Menu, MenuBuilder, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, Runtime, Wry,
};
use tracing::{error, info, warn};

use crate::database::settings::load_hotkey_config;

/// 托盘状态枚举
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum TrayState {
    /// 空闲状态
    Idle = 0,
    /// 录制中
    Recording = 1,
    /// 处理中（OCR、翻译等）
    Processing = 2,
}

impl From<u8> for TrayState {
    fn from(value: u8) -> Self {
        match value {
            1 => TrayState::Recording,
            2 => TrayState::Processing,
            _ => TrayState::Idle,
        }
    }
}

/// 托盘状态管理器
pub struct TrayStateManager {
    state: AtomicU8,
}

impl Default for TrayStateManager {
    fn default() -> Self {
        Self::new()
    }
}

impl TrayStateManager {
    pub fn new() -> Self {
        Self { state: AtomicU8::new(TrayState::Idle as u8) }
    }

    pub fn get_state(&self) -> TrayState {
        TrayState::from(self.state.load(Ordering::SeqCst))
    }

    pub fn set_state(&self, state: TrayState) {
        self.state.store(state as u8, Ordering::SeqCst);
    }
}

/// 托盘图标 ID
pub const TRAY_ID: &str = "main-tray";

/// 菜单项 ID
pub mod menu_ids {
    pub const SCREENSHOT: &str = "screenshot";
    pub const WORKBENCH: &str = "workbench";
    pub const SHOW_WINDOW: &str = "show_window";
    pub const EXIT: &str = "exit";
}

/// 创建托盘菜单
fn create_tray_menu<R: Runtime>(app: &AppHandle<R>) -> Result<Menu<R>, String> {
    let hotkeys = load_hotkey_config(app).unwrap_or_default();
    let screenshot_label = menu_label_with_shortcut("截图", &hotkeys.screenshot);
    let workbench_label = menu_label_with_shortcut("工作台", &hotkeys.workbench);

    // 创建菜单项
    let screenshot_item =
        MenuItem::with_id(app, menu_ids::SCREENSHOT, screenshot_label, true, None::<&str>)
            .map_err(|e| format!("创建截图菜单项失败: {}", e))?;

    let workbench_item =
        MenuItem::with_id(app, menu_ids::WORKBENCH, workbench_label, true, None::<&str>)
            .map_err(|e| format!("创建工作台菜单项失败: {}", e))?;

    let show_window_item =
        MenuItem::with_id(app, menu_ids::SHOW_WINDOW, "显示主窗口", true, None::<&str>)
            .map_err(|e| format!("创建显示窗口菜单项失败: {}", e))?;

    let exit_item = MenuItem::with_id(app, menu_ids::EXIT, "退出", true, None::<&str>)
        .map_err(|e| format!("创建退出菜单项失败: {}", e))?;

    // 创建分隔符
    let separator1 =
        PredefinedMenuItem::separator(app).map_err(|e| format!("创建分隔符失败: {}", e))?;
    let separator2 =
        PredefinedMenuItem::separator(app).map_err(|e| format!("创建分隔符失败: {}", e))?;

    // 构建菜单
    MenuBuilder::new(app)
        .item(&screenshot_item)
        .item(&workbench_item)
        .item(&separator1)
        .item(&show_window_item)
        .item(&separator2)
        .item(&exit_item)
        .build()
        .map_err(|e| format!("构建托盘菜单失败: {}", e))
}

fn menu_label_with_shortcut(label: &str, shortcut: &str) -> String {
    let shortcut = shortcut.trim();
    if shortcut.is_empty() {
        label.to_string()
    } else {
        format!("{} ({})", label, shortcut)
    }
}

pub fn refresh_tray_menu<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    let tray = app.tray_by_id(TRAY_ID).ok_or_else(|| "找不到托盘图标".to_string())?;
    let menu = create_tray_menu(app)?;
    tray.set_menu(Some(menu)).map_err(|e| format!("刷新托盘菜单失败: {}", e))
}

/// 处理托盘菜单事件
fn handle_menu_event(app: &AppHandle<Wry>, event_id: &str) {
    info!("托盘菜单点击: {}", event_id);

    match event_id {
        menu_ids::SCREENSHOT => {
            // 触发截图
            info!("触发截图功能");
            if let Err(e) = app.emit("tray-action", "screenshot") {
                error!("发送截图事件失败: {}", e);
            }
        }
        menu_ids::WORKBENCH => {
            // 触发工作台
            info!("触发工作台功能");
            if let Err(e) = app.emit("tray-action", "workbench") {
                error!("发送工作台事件失败: {}", e);
            }
        }
        menu_ids::SHOW_WINDOW => {
            // 显示主窗口
            show_main_window(app);
        }
        menu_ids::EXIT => {
            // 退出应用
            info!("用户请求退出应用");
            app.exit(0);
        }
        _ => {
            warn!("未知的菜单项: {}", event_id);
        }
    }
}

/// 显示主窗口
pub fn show_main_window(app: &AppHandle<Wry>) {
    if let Some(window) = app.get_webview_window("main") {
        // 如果窗口最小化，先恢复
        if let Ok(true) = window.is_minimized() {
            if let Err(e) = window.unminimize() {
                error!("恢复窗口失败: {}", e);
            }
        }

        // 显示窗口
        if let Err(e) = window.show() {
            error!("显示窗口失败: {}", e);
        }

        // 设置焦点
        if let Err(e) = window.set_focus() {
            error!("设置窗口焦点失败: {}", e);
        }

        info!("主窗口已显示");
    } else {
        warn!("找不到主窗口");
    }
}

/// 隐藏主窗口到托盘
pub fn hide_to_tray(app: &AppHandle<Wry>) {
    if let Some(window) = app.get_webview_window("main") {
        if let Err(e) = window.hide() {
            error!("隐藏窗口失败: {}", e);
        } else {
            info!("主窗口已隐藏到托盘");
        }
    }
}

/// 设置托盘图标状态
pub fn set_tray_state(app: &AppHandle<Wry>, state: TrayState) -> Result<(), String> {
    // 更新状态管理器
    if let Some(state_manager) = app.try_state::<Arc<TrayStateManager>>() {
        state_manager.set_state(state);
    }

    // 获取托盘图标
    let tray = app.tray_by_id(TRAY_ID).ok_or_else(|| "找不到托盘图标".to_string())?;

    // 根据状态设置不同的提示
    let tooltip = match state {
        TrayState::Idle => "虎哥截图",
        TrayState::Recording => "虎哥截图 - 录制中...",
        TrayState::Processing => "虎哥截图 - 处理中...",
    };

    // 设置提示文字
    tray.set_tooltip(Some(tooltip)).map_err(|e| format!("设置托盘提示失败: {}", e))?;

    // TODO: 当有不同状态的图标时，可以在这里切换图标
    // 目前所有状态使用相同的图标

    info!("托盘状态已更新: {:?}", state);
    Ok(())
}

/// 初始化系统托盘
pub fn setup_tray(app: &AppHandle<Wry>) -> Result<(), String> {
    info!("初始化系统托盘...");

    // 创建托盘菜单
    let menu = create_tray_menu(app)?;

    // 使用嵌入的高清托盘图标 (128x128 for high DPI)
    let icon_data = include_bytes!("../../icons/tray-icon@2x.png");
    let icon = Image::from_bytes(icon_data).map_err(|e| format!("无法加载托盘图标: {}", e))?;

    // 创建托盘图标
    let _tray = TrayIconBuilder::with_id(TRAY_ID)
        .icon(icon)
        .menu(&menu)
        .tooltip("虎哥截图")
        .show_menu_on_left_click(false) // 左键不显示菜单，用于双击显示窗口
        .on_menu_event(|app, event| {
            handle_menu_event(app, event.id.as_ref());
        })
        .on_tray_icon_event(|tray, event| {
            let app = tray.app_handle();

            match event {
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } => {
                    // 左键单击 - 直接显示主窗口
                    info!("托盘图标左键单击，显示主窗口");
                    show_main_window(app);
                }
                TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                } => {
                    // 左键双击 - 也显示主窗口（兼容双击习惯）
                    info!("托盘图标双击");
                    show_main_window(app);
                }
                _ => {}
            }
        })
        .build(app)
        .map_err(|e| format!("创建托盘图标失败: {}", e))?;

    // 初始化状态管理器
    let state_manager = Arc::new(TrayStateManager::new());
    app.manage(state_manager);

    info!("系统托盘初始化完成");
    Ok(())
}

/// 处理窗口关闭事件 - 最小化到托盘而不是退出
pub fn handle_close_requested(app: &AppHandle<Wry>, label: &str) -> bool {
    if label == "main" {
        info!("主窗口关闭请求，最小化到托盘");
        hide_to_tray(app);
        true // 阻止默认关闭行为
    } else {
        false // 允许其他窗口正常关闭
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tray_state_conversion() {
        assert_eq!(TrayState::from(0), TrayState::Idle);
        assert_eq!(TrayState::from(1), TrayState::Recording);
        assert_eq!(TrayState::from(2), TrayState::Processing);
        assert_eq!(TrayState::from(255), TrayState::Idle); // 未知值默认为 Idle
    }

    #[test]
    fn test_tray_state_manager() {
        let manager = TrayStateManager::new();
        assert_eq!(manager.get_state(), TrayState::Idle);

        manager.set_state(TrayState::Recording);
        assert_eq!(manager.get_state(), TrayState::Recording);

        manager.set_state(TrayState::Processing);
        assert_eq!(manager.get_state(), TrayState::Processing);

        manager.set_state(TrayState::Idle);
        assert_eq!(manager.get_state(), TrayState::Idle);
    }
}
