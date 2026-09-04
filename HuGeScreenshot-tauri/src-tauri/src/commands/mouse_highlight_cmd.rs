//! 鼠标高亮相关 Tauri 命令
//!
//! 提供鼠标高亮效果的启动、停止和配置功能
//! 包括创建和管理透明 overlay 窗口

use std::sync::Arc;
use tauri::{AppHandle, Emitter, Manager, Runtime, State, WebviewUrl, WebviewWindowBuilder};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::error::{HuGeError, HuGeResult};
use crate::mouse_highlight::{HighlightConfig, MousePosition, MouseTracker};

/// Overlay 窗口标签
const OVERLAY_LABEL: &str = "mouse-highlight-overlay";

/// 鼠标高亮状态
pub struct MouseHighlightState {
    pub tracker: Arc<Mutex<Option<MouseTracker>>>,
    pub config: Arc<Mutex<HighlightConfig>>,
}

impl MouseHighlightState {
    pub fn new() -> Self {
        Self {
            tracker: Arc::new(Mutex::new(None)),
            config: Arc::new(Mutex::new(HighlightConfig::default())),
        }
    }
}

impl Default for MouseHighlightState {
    fn default() -> Self {
        Self::new()
    }
}

/// 创建鼠标高亮 overlay 窗口
fn create_overlay_window<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    // 检查窗口是否已存在
    if app.get_webview_window(OVERLAY_LABEL).is_some() {
        info!("鼠标高亮 overlay 窗口已存在");
        return Ok(());
    }

    info!("创建鼠标高亮 overlay 窗口");

    // 获取主显示器信息
    let monitors = app.available_monitors().map_err(|e| e.to_string())?;

    if monitors.is_empty() {
        return Err("没有可用的显示器".to_string());
    }

    // 计算覆盖所有显示器的区域
    let mut min_x = i32::MAX;
    let mut min_y = i32::MAX;
    let mut max_x = i32::MIN;
    let mut max_y = i32::MIN;

    for monitor in &monitors {
        let pos = monitor.position();
        let size = monitor.size();
        min_x = min_x.min(pos.x);
        min_y = min_y.min(pos.y);
        max_x = max_x.max(pos.x + size.width as i32);
        max_y = max_y.max(pos.y + size.height as i32);
    }

    let total_width = (max_x - min_x) as u32;
    let total_height = (max_y - min_y) as u32;

    // 确定 URL
    #[cfg(debug_assertions)]
    let url =
        WebviewUrl::External("http://localhost:1420/mouse-highlight-overlay.html".parse().unwrap());

    #[cfg(not(debug_assertions))]
    let url = WebviewUrl::App("mouse-highlight-overlay.html".into());

    // 创建透明、置顶、鼠标穿透的窗口
    let window = WebviewWindowBuilder::new(app, OVERLAY_LABEL, url)
        .title("Mouse Highlight")
        .inner_size(total_width as f64, total_height as f64)
        .position(min_x as f64, min_y as f64)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .shadow(false)
        .visible(false) // 先隐藏，等初始化完成再显示
        .build()
        .map_err(|e| e.to_string())?;

    // 设置鼠标穿透
    window.set_ignore_cursor_events(true).map_err(|e| e.to_string())?;

    info!(
        "鼠标高亮 overlay 窗口创建成功: {}x{} at ({}, {})",
        total_width, total_height, min_x, min_y
    );

    Ok(())
}

/// 显示 overlay 窗口
fn show_overlay_window<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(OVERLAY_LABEL) {
        window.show().map_err(|e| e.to_string())?;
        // 发送显示事件
        let _ = app.emit("show-highlight-overlay", ());
    }
    Ok(())
}

/// 隐藏 overlay 窗口（暂停高亮但保留窗口）
#[allow(dead_code)]
fn hide_overlay_window<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(OVERLAY_LABEL) {
        // 发送隐藏事件
        let _ = app.emit("hide-highlight-overlay", ());
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// 关闭 overlay 窗口
fn close_overlay_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window(OVERLAY_LABEL) {
        let _ = window.close();
        info!("鼠标高亮 overlay 窗口已关闭");
    }
}

/// 发送配置到 overlay 窗口
fn send_config_to_overlay<R: Runtime>(app: &AppHandle<R>, config: &HighlightConfig) {
    if let Err(e) = app.emit("mouse-highlight-config", config) {
        warn!("发送配置到 overlay 失败: {}", e);
    }
}

/// 启动鼠标高亮
///
/// # 参数
///
/// - `config`: 可选的高亮配置，如果不提供则使用默认配置
#[tauri::command]
pub async fn start_mouse_highlight<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, MouseHighlightState>,
    config: Option<HighlightConfig>,
) -> HuGeResult<()> {
    info!("启动鼠标高亮");

    let mut tracker_guard = state.tracker.lock().await;

    // 如果已有追踪器在运行，先停止
    if let Some(ref mut tracker) = *tracker_guard {
        if tracker.is_running() {
            tracker.stop();
        }
    }

    // 获取配置
    let highlight_config = if let Some(cfg) = config {
        // 更新保存的配置
        let mut config_guard = state.config.lock().await;
        *config_guard = cfg.clone();
        cfg
    } else {
        state.config.lock().await.clone()
    };

    // 创建 overlay 窗口
    if let Err(e) = create_overlay_window(&app) {
        error!("创建 overlay 窗口失败: {}", e);
        return Err(HuGeError::Unknown(e));
    }

    // 发送配置到 overlay
    send_config_to_overlay(&app, &highlight_config);

    // 创建新的追踪器
    let mut tracker = MouseTracker::new(highlight_config);
    tracker.start(app.clone()).map_err(HuGeError::Unknown)?;

    *tracker_guard = Some(tracker);

    // 显示 overlay 窗口
    if let Err(e) = show_overlay_window(&app) {
        warn!("显示 overlay 窗口失败: {}", e);
    }

    info!("鼠标高亮已启动");
    Ok(())
}

/// 停止鼠标高亮
#[tauri::command]
pub async fn stop_mouse_highlight<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, MouseHighlightState>,
) -> HuGeResult<()> {
    info!("停止鼠标高亮");

    let mut tracker_guard = state.tracker.lock().await;

    if let Some(ref mut tracker) = *tracker_guard {
        tracker.stop();
    }

    *tracker_guard = None;

    // 关闭 overlay 窗口
    close_overlay_window(&app);

    info!("鼠标高亮已停止");
    Ok(())
}

/// 获取鼠标高亮状态
#[tauri::command]
pub async fn get_mouse_highlight_status(state: State<'_, MouseHighlightState>) -> HuGeResult<bool> {
    let tracker_guard = state.tracker.lock().await;

    let is_running = tracker_guard.as_ref().map(|t| t.is_running()).unwrap_or(false);

    Ok(is_running)
}

/// 获取当前鼠标位置
#[tauri::command]
pub async fn get_mouse_position(
    state: State<'_, MouseHighlightState>,
) -> HuGeResult<MousePosition> {
    let tracker_guard = state.tracker.lock().await;

    if let Some(ref tracker) = *tracker_guard {
        Ok(tracker.get_position())
    } else {
        // 如果追踪器未启动，返回 (0, 0)
        Ok(MousePosition { x: 0, y: 0 })
    }
}

/// 获取鼠标高亮配置
#[tauri::command]
pub async fn get_mouse_highlight_config(
    state: State<'_, MouseHighlightState>,
) -> HuGeResult<HighlightConfig> {
    let config = state.config.lock().await.clone();
    Ok(config)
}

/// 更新鼠标高亮配置
///
/// 如果高亮正在运行，会自动重启以应用新配置
#[tauri::command]
pub async fn set_mouse_highlight_config<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, MouseHighlightState>,
    config: HighlightConfig,
) -> HuGeResult<()> {
    info!("更新鼠标高亮配置");

    // 保存配置
    {
        let mut config_guard = state.config.lock().await;
        *config_guard = config.clone();
    }

    // 发送配置到 overlay（实时更新）
    send_config_to_overlay(&app, &config);

    // 如果正在运行，重启以应用新配置
    let mut tracker_guard = state.tracker.lock().await;

    if let Some(ref mut tracker) = *tracker_guard {
        if tracker.is_running() {
            tracker.stop();

            let mut new_tracker = MouseTracker::new(config);
            new_tracker.start(app).map_err(HuGeError::Unknown)?;

            *tracker_guard = Some(new_tracker);
            info!("鼠标高亮已重启以应用新配置");
        } else {
            tracker.update_config(config);
        }
    }

    Ok(())
}
