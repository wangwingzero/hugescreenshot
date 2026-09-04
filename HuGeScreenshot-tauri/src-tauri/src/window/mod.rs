//! 窗口管理模块
//!
//! 本模块负责窗口的创建和管理，包括：
//! - 显示器信息获取
//! - 覆盖窗口（截图选区）
//! - 钉图窗口
//! - 多窗口焦点管理
//!
//! # 子模块
//!
//! - `overlay`: 覆盖窗口管理
//! - `pin`: 钉图窗口管理
//! - `focus_manager`: 多窗口焦点状态管理

pub mod focus_manager;
#[cfg(test)]
mod focus_properties;
pub mod overlay;
pub mod pin;

use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::error::{HuGeError, HuGeResult};

/// 显示器信息
///
/// 包含显示器的位置、尺寸、DPR 等信息。
///
/// # 坐标系统
///
/// - `position`: 显示器左上角在虚拟屏幕坐标系中的位置（物理像素）
/// - `size`: 显示器的逻辑尺寸（物理像素 / scale_factor）
/// - `scale_factor`: 设备像素比，用于逻辑像素和物理像素之间的转换
///
/// # 注意事项
///
/// Tauri 的 Monitor API 返回的 position 和 size 都是物理像素。
/// 为了与前端 Vue 的逻辑像素坐标系统一致，我们将 size 转换为逻辑像素。
/// position 保持物理像素，因为它用于定位覆盖窗口。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MonitorInfo {
    /// 显示器 ID（基于索引）
    pub id: u32,
    /// 显示器名称（可能为空）
    pub name: String,
    /// 位置（物理像素，虚拟屏幕坐标系）
    pub position: (i32, i32),
    /// 尺寸（逻辑像素）
    pub size: (u32, u32),
    /// 物理尺寸（物理像素）
    pub physical_size: (u32, u32),
    /// 设备像素比 (DPR)
    pub scale_factor: f64,
    /// 是否为主显示器
    pub is_primary: bool,
}

/// 获取所有显示器信息
///
/// 使用 Tauri 的 `available_monitors()` API 获取系统中所有连接的显示器信息，
/// 并通过 `primary_monitor()` 判断哪个是主显示器。
///
/// # 返回
///
/// 返回所有连接的显示器信息列表。如果没有检测到显示器，返回空列表。
///
/// # 错误
///
/// - 如果获取显示器信息失败，返回 `HuGeError::WindowError`
///
/// # 示例
///
/// ```ignore
/// let monitors = get_monitors(app).await?;
/// for monitor in monitors {
///     println!("{}: {}x{} @ {:.1}x DPR, primary: {}",
///         monitor.name,
///         monitor.size.0,
///         monitor.size.1,
///         monitor.scale_factor,
///         monitor.is_primary
///     );
/// }
/// ```
///
/// # 高 DPI 处理
///
/// - `size` 返回逻辑像素尺寸，适合 UI 布局
/// - `physical_size` 返回物理像素尺寸，适合截图操作
/// - `scale_factor` 用于坐标转换：物理像素 = 逻辑像素 * scale_factor
#[tauri::command]
pub async fn get_monitors(app: tauri::AppHandle) -> HuGeResult<Vec<MonitorInfo>> {
    info!("获取显示器信息...");

    // 获取所有可用显示器
    let monitors = app
        .available_monitors()
        .map_err(|e| HuGeError::WindowError(format!("获取显示器列表失败: {}", e)))?;

    if monitors.is_empty() {
        warn!("未检测到任何显示器");
        return Ok(Vec::new());
    }

    debug!("检测到 {} 个显示器", monitors.len());

    // 获取主显示器信息用于判断
    let primary_monitor = app
        .primary_monitor()
        .map_err(|e| HuGeError::WindowError(format!("获取主显示器失败: {}", e)))?;

    // 获取主显示器的位置用于比较
    let primary_position = primary_monitor.as_ref().map(|m| (m.position().x, m.position().y));

    debug!("主显示器位置: {:?}", primary_position);

    // 转换为 MonitorInfo 列表
    let monitor_infos: Vec<MonitorInfo> = monitors
        .into_iter()
        .enumerate()
        .map(|(index, monitor)| {
            let position = monitor.position();
            let physical_size = monitor.size();
            let scale_factor = monitor.scale_factor();
            let name = monitor.name().cloned().unwrap_or_else(|| format!("显示器 {}", index + 1));

            // 判断是否为主显示器（通过位置比较）
            let is_primary = primary_position
                .map(|(px, py)| position.x == px && position.y == py)
                .unwrap_or(index == 0); // 如果无法获取主显示器，默认第一个为主显示器

            // 计算逻辑尺寸
            let logical_width = (physical_size.width as f64 / scale_factor).round() as u32;
            let logical_height = (physical_size.height as f64 / scale_factor).round() as u32;

            let info = MonitorInfo {
                id: index as u32,
                name,
                position: (position.x, position.y),
                size: (logical_width, logical_height),
                physical_size: (physical_size.width, physical_size.height),
                scale_factor,
                is_primary,
            };

            debug!(
                "显示器 {}: {} @ ({}, {}), 逻辑尺寸: {}x{}, 物理尺寸: {}x{}, DPR: {:.2}, 主显示器: {}",
                info.id,
                info.name,
                info.position.0,
                info.position.1,
                info.size.0,
                info.size.1,
                info.physical_size.0,
                info.physical_size.1,
                info.scale_factor,
                info.is_primary
            );

            info
        })
        .collect();

    info!("成功获取 {} 个显示器信息", monitor_infos.len());

    Ok(monitor_infos)
}

// 重新导出常用类型
pub use focus_manager::{emit_focus_change, emit_focus_change_to, FocusState, FOCUS_CHANGED_EVENT};
pub use overlay::{
    close_all_overlays, close_overlay_window, create_all_overlay_windows, create_overlay_window,
    get_overlay_windows, set_overlay_ignore_cursor,
};
pub use pin::{
    close_all_pin_windows, close_pin_window, create_pin_window, get_pin_window_init,
    get_pin_windows, set_pin_opacity,
};
