//! 截图引擎模块
//!
//! 本模块负责屏幕捕获和窗口检测功能。
//!
//! # 子模块
//!
//! - `capture`: 屏幕捕获功能，支持单显示器和多显示器捕获
//! - `window_detect`: 窗口检测功能，获取指定坐标下的窗口信息
//! - `image_hash`: 图片哈希计算，用于去重检测
//! - `snapshot`: 静态截图快照数据结构，用于解决透明覆盖层问题
//! - `capture_properties`: 截图引擎属性测试（仅测试时编译）

pub mod capture;
pub(crate) mod frame_validity;
#[cfg(windows)]
pub(crate) mod gdi_virtual_desktop;
pub mod image_hash;
pub mod snapshot;
#[cfg(windows)]
pub mod wgc_capture;
pub mod window_detect;

// 属性测试模块（仅在测试时编译）
#[cfg(test)]
mod capture_properties;
#[cfg(test)]
mod snapshot_properties;

// 重新导出常用类型
pub use capture::{
    capture_all_monitors, capture_region_impl, capture_screen, get_screen_info, CaptureResult,
    Rect, ScreenInfo,
};
pub use image_hash::{
    compute_bytes_hash, compute_file_hash, compute_quick_hash, DEFAULT_QUICK_HASH_BYTES,
};
pub use snapshot::{capture_static_snapshot, cleanup_snapshot, MonitorSnapshot, SnapshotResult};
pub use window_detect::{detect_window_at, get_all_windows, WindowInfo};

// Windows 平台特定导出
#[cfg(windows)]
pub use wgc_capture::pre_warm_d3d_devices;
#[cfg(windows)]
pub use window_detect::get_window_info_by_hwnd;
