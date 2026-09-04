//! 托盘相关命令
//!
//! 提供前端调用的托盘控制命令

use std::sync::Arc;
use tauri::{AppHandle, Manager, Wry};

use crate::tray::{self, TrayState, TrayStateManager};

/// 设置托盘状态
///
/// # Arguments
/// * `state` - 状态字符串: "idle", "recording", "processing"
#[tauri::command]
pub async fn set_tray_state(app: AppHandle<Wry>, state: String) -> Result<(), String> {
    let tray_state = match state.as_str() {
        "idle" => TrayState::Idle,
        "recording" => TrayState::Recording,
        "processing" => TrayState::Processing,
        _ => {
            return Err(format!("未知的托盘状态: {}", state));
        }
    };

    tray::set_tray_state(&app, tray_state)
}

/// 显示主窗口
#[tauri::command]
pub async fn show_main_window(app: AppHandle<Wry>) -> Result<(), String> {
    tray::show_main_window(&app);
    Ok(())
}

/// 隐藏主窗口到托盘
#[tauri::command]
pub async fn hide_to_tray(app: AppHandle<Wry>) -> Result<(), String> {
    tray::hide_to_tray(&app);
    Ok(())
}

/// 获取当前托盘状态
#[tauri::command]
pub async fn get_tray_state(app: AppHandle<Wry>) -> Result<String, String> {
    if let Some(state_manager) = app.try_state::<Arc<TrayStateManager>>() {
        let state = state_manager.get_state();
        let state_str = match state {
            TrayState::Idle => "idle",
            TrayState::Recording => "recording",
            TrayState::Processing => "processing",
        };
        Ok(state_str.to_string())
    } else {
        Ok("idle".to_string())
    }
}
