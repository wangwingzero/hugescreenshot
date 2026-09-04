//! 静态截图快照模块
//!
//! 本模块定义了静态截图快照的数据结构，用于在截图前捕获屏幕静态图像，
//! 解决透明覆盖层显示实时桌面变化的问题。
//!
//! # 功能特性
//!
//! - 支持多显示器快照捕获
//! - 正确处理不同 DPR（设备像素比）的显示器
//! - 提供快照元数据供前端使用
//!
//! # 数据流
//!
//! 1. 用户按下截图热键
//! 2. 系统捕获所有显示器的静态快照
//! 3. 快照保存为临时文件
//! 4. 通过 Tauri Event 将快照路径和元数据发送给前端
//! 5. 前端加载快照作为 Canvas 背景
//! 6. 截图会话结束后清理临时文件
//!
//! # 相关需求
//!
//! - Requirements 1.1: 截图热键按下时捕获静态快照
//! - Requirements 2.1: 捕获所有连接的显示器
//! - Requirements 2.2: 正确处理不同 DPR 值
//! - Requirements 3.1: 保存快照到临时文件

use image::ImageEncoder;
use image::{ExtendedColorType, RgbaImage};
use serde::{Deserialize, Serialize};
use std::io::BufWriter;
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};
use tracing::{debug, error, info, warn};

use crate::error::{HuGeError, HuGeResult};
use crate::screenshot::capture::{capture_all_screens_sync, CaptureResult};

fn cleanup_intermediate_capture_files(paths: &[String]) {
    for source_path in paths {
        if let Err(e) = std::fs::remove_file(source_path) {
            warn!("清理中间显示器截图失败: {} ({})", source_path, e);
        }
    }
}

/// 快照捕获结果
///
/// 包含快照文件路径和元数据，用于前端加载和显示静态截图背景。
///
/// # 字段说明
///
/// - `path`: 临时快照文件的绝对路径，前端通过 `convertFileSrc` 转换为 asset URL
/// - `width`: 合并后快照的总宽度（物理像素）
/// - `height`: 合并后快照的总高度（物理像素）
/// - `dpr`: 主显示器的设备像素比，用于前端坐标转换
/// - `monitors`: 各显示器的详细信息，用于多显示器场景下的正确渲染
///
/// # 示例
///
/// ```ignore
/// let result = SnapshotResult {
///     path: "C:\\Users\\xxx\\AppData\\Local\\com.wangh.hugescreenshot\\cache\\snapshot_1234567890.png".to_string(),
///     width: 3840,
///     height: 2160,
///     dpr: 1.5,
///     monitors: vec![
///         MonitorSnapshot {
///             monitor_id: 0,
///             x: 0,
///             y: 0,
///             width: 2560,
///             height: 1440,
///             dpr: 1.5,
///         },
///         MonitorSnapshot {
///             monitor_id: 1,
///             x: 2560,
///             y: 0,
///             width: 1920,
///             height: 1080,
///             dpr: 1.0,
///         },
///     ],
/// };
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SnapshotResult {
    /// 临时快照文件的绝对路径
    ///
    /// 文件格式为 PNG，保存在应用缓存目录中。
    /// 前端需要使用 `@tauri-apps/api/core` 的 `convertFileSrc` 函数
    /// 将此路径转换为 `asset://` 协议的 URL 才能加载。
    pub path: String,

    /// 合并后快照的总宽度（物理像素）
    ///
    /// 对于多显示器设置，这是所有显示器组成的虚拟桌面的总宽度。
    /// 注意：这是物理像素值，不是逻辑像素。
    pub width: u32,

    /// 合并后快照的总高度（物理像素）
    ///
    /// 对于多显示器设置，这是所有显示器组成的虚拟桌面的总高度。
    /// 注意：这是物理像素值，不是逻辑像素。
    pub height: u32,

    /// 主显示器的设备像素比 (DPR)
    ///
    /// 用于前端进行逻辑像素和物理像素之间的转换。
    /// 典型值：1.0（100% 缩放）、1.25（125%）、1.5（150%）、2.0（200%）
    pub dpr: f64,

    /// 各显示器的详细信息
    ///
    /// 包含每个显示器的位置、尺寸和 DPR 信息，
    /// 用于多显示器场景下正确计算每个覆盖层窗口应显示的快照区域。
    pub monitors: Vec<MonitorSnapshot>,
}

/// 单个显示器的快照信息
///
/// 描述单个显示器在虚拟桌面中的位置和属性，
/// 用于多显示器场景下的正确渲染和坐标计算。
///
/// # 坐标系统
///
/// - 坐标原点 (0, 0) 通常是主显示器的左上角
/// - 副显示器可能有负坐标（位于主显示器左侧或上方时）
/// - 所有坐标和尺寸都是物理像素值
///
/// # 示例
///
/// ```ignore
/// // 主显示器（2K，150% 缩放）
/// let primary = MonitorSnapshot {
///     monitor_id: 0,
///     x: 0,
///     y: 0,
///     width: 2560,
///     height: 1440,
///     dpr: 1.5,
/// };
///
/// // 副显示器（1080p，100% 缩放，位于主显示器右侧）
/// let secondary = MonitorSnapshot {
///     monitor_id: 1,
///     x: 2560,  // 紧邻主显示器右边
///     y: 0,
///     width: 1920,
///     height: 1080,
///     dpr: 1.0,
/// };
///
/// // 副显示器（位于主显示器左侧，有负 x 坐标）
/// let left_monitor = MonitorSnapshot {
///     monitor_id: 2,
///     x: -1920,  // 负坐标表示在主显示器左侧
///     y: 0,
///     width: 1920,
///     height: 1080,
///     dpr: 1.0,
/// };
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitorSnapshot {
    /// 显示器 ID
    ///
    /// 对应 DXGI 输出索引或 screenshots-rs 的显示器 ID。
    /// 主显示器通常是 ID 0。
    pub monitor_id: u32,

    /// 显示器左上角的 X 坐标（物理像素）
    ///
    /// 相对于虚拟桌面原点的水平位置。
    /// 可能为负值（当显示器位于主显示器左侧时）。
    pub x: i32,

    /// 显示器左上角的 Y 坐标（物理像素）
    ///
    /// 相对于虚拟桌面原点的垂直位置。
    /// 可能为负值（当显示器位于主显示器上方时）。
    pub y: i32,

    /// 显示器宽度（物理像素）
    ///
    /// 这是显示器的实际物理分辨率宽度，
    /// 不受 Windows 缩放设置影响。
    pub width: u32,

    /// 显示器高度（物理像素）
    ///
    /// 这是显示器的实际物理分辨率高度，
    /// 不受 Windows 缩放设置影响。
    pub height: u32,

    /// 此显示器的设备像素比 (DPR)
    ///
    /// 每个显示器可能有不同的 DPR 设置。
    /// 用于计算此显示器上的逻辑像素到物理像素的转换。
    pub dpr: f64,
}

impl SnapshotResult {
    /// 创建新的快照结果
    ///
    /// # 参数
    ///
    /// - `path`: 快照文件路径
    /// - `width`: 总宽度（物理像素）
    /// - `height`: 总高度（物理像素）
    /// - `dpr`: 主显示器 DPR
    /// - `monitors`: 各显示器信息
    pub fn new(
        path: String,
        width: u32,
        height: u32,
        dpr: f64,
        monitors: Vec<MonitorSnapshot>,
    ) -> Self {
        Self { path, width, height, dpr, monitors }
    }

    /// 检查快照是否为多显示器配置
    pub fn is_multi_monitor(&self) -> bool {
        self.monitors.len() > 1
    }

    /// 获取主显示器信息
    ///
    /// 返回 monitor_id 为 0 的显示器，如果不存在则返回第一个显示器
    pub fn primary_monitor(&self) -> Option<&MonitorSnapshot> {
        self.monitors.iter().find(|m| m.monitor_id == 0).or_else(|| self.monitors.first())
    }
}

impl MonitorSnapshot {
    /// 创建新的显示器快照信息
    ///
    /// # 参数
    ///
    /// - `monitor_id`: 显示器 ID
    /// - `x`: X 坐标（物理像素）
    /// - `y`: Y 坐标（物理像素）
    /// - `width`: 宽度（物理像素）
    /// - `height`: 高度（物理像素）
    /// - `dpr`: 设备像素比
    pub fn new(monitor_id: u32, x: i32, y: i32, width: u32, height: u32, dpr: f64) -> Self {
        Self { monitor_id, x, y, width, height, dpr }
    }

    /// 检查给定的物理像素坐标是否在此显示器范围内
    ///
    /// # 参数
    ///
    /// - `px`: X 坐标（物理像素）
    /// - `py`: Y 坐标（物理像素）
    ///
    /// # 返回
    ///
    /// 如果坐标在显示器范围内返回 `true`
    pub fn contains_point(&self, px: i32, py: i32) -> bool {
        px >= self.x
            && px < self.x + self.width as i32
            && py >= self.y
            && py < self.y + self.height as i32
    }

    /// 计算显示器的右边界 X 坐标
    pub fn right(&self) -> i32 {
        self.x + self.width as i32
    }

    /// 计算显示器的下边界 Y 坐标
    pub fn bottom(&self) -> i32 {
        self.y + self.height as i32
    }

    /// 将逻辑像素坐标转换为此显示器的物理像素坐标
    ///
    /// # 参数
    ///
    /// - `logical_x`: 逻辑 X 坐标
    /// - `logical_y`: 逻辑 Y 坐标
    ///
    /// # 返回
    ///
    /// 物理像素坐标 (x, y)
    pub fn logical_to_physical(&self, logical_x: f64, logical_y: f64) -> (i32, i32) {
        let physical_x = (logical_x * self.dpr).round() as i32;
        let physical_y = (logical_y * self.dpr).round() as i32;
        (physical_x, physical_y)
    }

    /// 将物理像素坐标转换为此显示器的逻辑像素坐标
    ///
    /// # 参数
    ///
    /// - `physical_x`: 物理 X 坐标
    /// - `physical_y`: 物理 Y 坐标
    ///
    /// # 返回
    ///
    /// 逻辑像素坐标 (x, y)
    pub fn physical_to_logical(&self, physical_x: i32, physical_y: i32) -> (f64, f64) {
        let logical_x = physical_x as f64 / self.dpr;
        let logical_y = physical_y as f64 / self.dpr;
        (logical_x, logical_y)
    }
}

// ============================================================================
// 快照捕获命令
// ============================================================================

/// 捕获所有屏幕的静态快照并保存到临时文件
///
/// 此命令捕获所有连接的显示器，将它们合并为单个 PNG 图像，
/// 并保存到应用缓存目录。返回快照元数据供前端使用。
///
/// # 参数
///
/// - `app`: Tauri AppHandle，用于获取应用缓存目录
///
/// # 返回
///
/// 成功返回 `SnapshotResult`，包含快照文件路径和元数据
///
/// # 错误
///
/// - 无法获取缓存目录
/// - 无法检测到显示器
/// - 截图捕获失败
/// - 文件保存失败
///
/// # 性能目标
///
/// - 单显示器 1080p: < 50ms
/// - 双显示器 4K: < 100ms
/// - 总耗时（含保存）: < 200ms
///
/// **Validates: Requirements 1.1, 2.1, 2.4, 3.1**
#[tauri::command]
pub async fn capture_static_snapshot(app: AppHandle) -> HuGeResult<SnapshotResult> {
    let start = Instant::now();
    info!("开始捕获静态快照...");

    // 1. 获取应用缓存目录
    let cache_dir = app.path().app_cache_dir().map_err(|e| {
        error!("获取应用缓存目录失败: {}", e);
        HuGeError::CaptureError(format!("获取应用缓存目录失败: {}", e))
    })?;

    // 确保缓存目录存在
    if !cache_dir.exists() {
        std::fs::create_dir_all(&cache_dir).map_err(|e| {
            error!("创建缓存目录失败: {:?}, 错误: {}", cache_dir, e);
            HuGeError::FileError(e)
        })?;
    }

    // 2. 获取所有屏幕截图（与 overlay 预截图复用同一条回退链）
    let capture_results: Vec<CaptureResult> = capture_all_screens_sync(false).map_err(|e| {
        let error_msg = format!("静态快照捕获失败: {}", e);
        error!("{}", error_msg);
        HuGeError::CaptureError(error_msg)
    })?;

    if capture_results.is_empty() {
        let error_msg = "未检测到任何显示器。请检查显示器连接和显示设置。";
        error!("{}", error_msg);
        return Err(HuGeError::CaptureError(error_msg.to_string()));
    }

    info!("检测到 {} 个显示器", capture_results.len());

    // 3. 计算虚拟桌面的边界（所有显示器的组合区域）
    let min_x = capture_results.iter().map(|s| s.x).min().unwrap_or(0);
    let min_y = capture_results.iter().map(|s| s.y).min().unwrap_or(0);
    let max_x = capture_results.iter().map(|s| s.x + s.width as i32).max().unwrap_or(0);
    let max_y = capture_results.iter().map(|s| s.y + s.height as i32).max().unwrap_or(0);

    let total_width = (max_x - min_x) as u32;
    let total_height = (max_y - min_y) as u32;

    debug!(
        "虚拟桌面边界: ({}, {}) -> ({}, {}), 总尺寸: {}x{}",
        min_x, min_y, max_x, max_y, total_width, total_height
    );

    // 4. 创建合并画布
    let mut canvas = RgbaImage::new(total_width, total_height);

    // 5. 捕获每个显示器并合并到画布
    let mut monitors = Vec::with_capacity(capture_results.len());
    let mut primary_dpr = 1.0f64;

    let mut source_paths_to_cleanup = Vec::with_capacity(capture_results.len());

    for capture in &capture_results {
        source_paths_to_cleanup.push(capture.path.clone());
        debug!(
            "合并显示器 {}: {}x{} @ ({}, {}), DPR: {}",
            capture.monitor_id, capture.width, capture.height, capture.x, capture.y, capture.dpr
        );

        if capture.x == 0 && capture.y == 0 {
            primary_dpr = capture.dpr;
        }

        let x_offset = (capture.x - min_x) as u32;
        let y_offset = (capture.y - min_y) as u32;

        let capture_image = match image::open(&capture.path) {
            Ok(image) => image,
            Err(e) => {
                let error_msg = format!(
                    "读取显示器 {} 快照失败: {}。路径: {}",
                    capture.monitor_id, e, capture.path
                );
                error!("{}", error_msg);
                cleanup_intermediate_capture_files(&source_paths_to_cleanup);
                return Err(HuGeError::CaptureError(error_msg));
            }
        };
        let rgba_image = capture_image.to_rgba8();
        let img_width = rgba_image.width();
        let img_height = rgba_image.height();

        let img_raw = rgba_image.as_raw();
        let canvas_raw = canvas.as_mut();
        let canvas_stride = total_width as usize * 4;
        let img_stride = img_width as usize * 4;

        for py in 0..img_height as usize {
            let src_start = py * img_stride;
            let dst_start = (y_offset as usize + py) * canvas_stride + x_offset as usize * 4;
            let len = img_stride;
            if dst_start + len <= canvas_raw.len() && src_start + len <= img_raw.len() {
                canvas_raw[dst_start..dst_start + len]
                    .copy_from_slice(&img_raw[src_start..src_start + len]);
            }
        }

        monitors.push(MonitorSnapshot::new(
            capture.monitor_id,
            capture.x,
            capture.y,
            capture.width,
            capture.height,
            capture.dpr,
        ));
    }

    if capture_results.len() < app.available_monitors().unwrap_or_default().len().max(1) {
        let error_msg = format!(
            "静态快照不完整：期望 {} 个显示器，实际仅捕获到 {} 个",
            app.available_monitors().unwrap_or_default().len(),
            capture_results.len()
        );
        error!("{}", error_msg);
        for source_path in &source_paths_to_cleanup {
            if let Err(e) = std::fs::remove_file(source_path) {
                warn!("清理中间显示器截图失败: {} ({})", source_path, e);
            }
        }
        return Err(HuGeError::CaptureError(error_msg));
    }

    // 6. 生成文件名并保存
    let timestamp =
        SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);

    let filename = format!("snapshot_{}.bmp", timestamp);
    let snapshot_path = cache_dir.join(&filename);

    debug!("保存快照到: {:?}", snapshot_path);

    let save_start = Instant::now();

    // 【性能优化】使用 BMP 无压缩保存，写入极快（~10ms vs PNG ~500ms）
    let file = match std::fs::File::create(&snapshot_path) {
        Ok(file) => file,
        Err(e) => {
            error!("创建快照文件失败: {:?}, 错误: {}", snapshot_path, e);
            cleanup_intermediate_capture_files(&source_paths_to_cleanup);
            return Err(HuGeError::CaptureError(format!("创建快照文件失败: {}", e)));
        }
    };
    let mut writer = BufWriter::new(file);
    let encoder = image::codecs::bmp::BmpEncoder::new(&mut writer);
    if let Err(e) =
        encoder.write_image(canvas.as_raw(), total_width, total_height, ExtendedColorType::Rgba8)
    {
        error!("保存快照失败: {:?}, 错误: {}", snapshot_path, e);
        cleanup_intermediate_capture_files(&source_paths_to_cleanup);
        return Err(HuGeError::CaptureError(format!("保存快照失败: {}", e)));
    }
    let save_time = save_start.elapsed();

    let total_time = start.elapsed();

    for source_path in &source_paths_to_cleanup {
        if let Err(e) = std::fs::remove_file(source_path) {
            warn!("清理中间显示器截图失败: {} ({})", source_path, e);
        }
    }

    info!(
        "静态快照捕获完成: {:?}, 尺寸: {}x{}, 显示器数: {}, 保存耗时: {:?}, 总耗时: {:?}",
        snapshot_path,
        total_width,
        total_height,
        monitors.len(),
        save_time,
        total_time
    );

    // 性能警告：超过 200ms 记录警告
    if total_time.as_millis() > 200 {
        warn!("静态快照捕获耗时 {}ms，超过 200ms 阈值", total_time.as_millis());
    }

    // 7. 返回结果
    Ok(SnapshotResult::new(
        snapshot_path.to_string_lossy().to_string(),
        total_width,
        total_height,
        primary_dpr,
        monitors,
    ))
}

/// 清理临时快照文件
///
/// 删除指定路径的快照文件。如果文件不存在，静默成功。
///
/// # 参数
///
/// - `app`: Tauri AppHandle（保留以便将来扩展）
/// - `path`: 要删除的快照文件路径
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误
///
/// # 安全性
///
/// 此命令只允许删除应用缓存目录下的文件，防止恶意删除。
///
/// **Validates: Requirements 3.4**
#[tauri::command]
pub async fn cleanup_snapshot(app: AppHandle, path: String) -> HuGeResult<()> {
    info!("清理快照文件: {}", path);

    let snapshot_path = std::path::Path::new(&path);

    // 安全检查：确保路径在应用缓存目录下
    let cache_dir = app.path().app_cache_dir().map_err(|e| {
        error!("获取应用缓存目录失败: {}", e);
        HuGeError::CaptureError(format!("获取应用缓存目录失败: {}", e))
    })?;

    // 规范化路径进行比较
    let canonical_path = snapshot_path.canonicalize().ok();
    let canonical_cache = cache_dir.canonicalize().ok();

    let is_safe = match (&canonical_path, &canonical_cache) {
        (Some(p), Some(c)) => p.starts_with(c),
        _ => {
            // 如果无法规范化，检查路径字符串是否包含缓存目录
            path.contains("hugescreenshot") || path.contains("com.wangh.hugescreenshot")
        }
    };

    if !is_safe {
        warn!("拒绝删除不安全的路径: {}", path);
        return Err(HuGeError::CaptureError("只能删除应用缓存目录下的文件".to_string()));
    }

    // 删除文件
    if snapshot_path.exists() {
        std::fs::remove_file(snapshot_path).map_err(|e| {
            // 文件不存在不算错误
            if e.kind() == std::io::ErrorKind::NotFound {
                debug!("快照文件已不存在: {}", path);
                return HuGeError::Unknown("".to_string()); // 这个错误会被忽略
            }
            error!("删除快照文件失败: {}, 错误: {}", path, e);
            HuGeError::FileError(e)
        })?;
        info!("快照文件已删除: {}", path);
    } else {
        debug!("快照文件不存在，跳过删除: {}", path);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_snapshot_result_creation() {
        let monitors = vec![
            MonitorSnapshot::new(0, 0, 0, 2560, 1440, 1.5),
            MonitorSnapshot::new(1, 2560, 0, 1920, 1080, 1.0),
        ];

        let result =
            SnapshotResult::new("/tmp/snapshot.png".to_string(), 4480, 1440, 1.5, monitors);

        assert_eq!(result.path, "/tmp/snapshot.png");
        assert_eq!(result.width, 4480);
        assert_eq!(result.height, 1440);
        assert_eq!(result.dpr, 1.5);
        assert!(result.is_multi_monitor());
    }

    #[test]
    fn test_single_monitor() {
        let monitors = vec![MonitorSnapshot::new(0, 0, 0, 1920, 1080, 1.0)];

        let result =
            SnapshotResult::new("/tmp/snapshot.png".to_string(), 1920, 1080, 1.0, monitors);

        assert!(!result.is_multi_monitor());
    }

    #[test]
    fn test_primary_monitor() {
        let monitors = vec![
            MonitorSnapshot::new(1, 1920, 0, 1920, 1080, 1.0),
            MonitorSnapshot::new(0, 0, 0, 2560, 1440, 1.5),
        ];

        let result =
            SnapshotResult::new("/tmp/snapshot.png".to_string(), 4480, 1440, 1.5, monitors);

        let primary = result.primary_monitor().unwrap();
        assert_eq!(primary.monitor_id, 0);
        assert_eq!(primary.width, 2560);
    }

    #[test]
    fn test_monitor_contains_point() {
        let monitor = MonitorSnapshot::new(0, 0, 0, 1920, 1080, 1.0);

        // 左上角
        assert!(monitor.contains_point(0, 0));
        // 中心
        assert!(monitor.contains_point(960, 540));
        // 右下角边界内
        assert!(monitor.contains_point(1919, 1079));
        // 右下角边界外
        assert!(!monitor.contains_point(1920, 1080));
        // 负坐标
        assert!(!monitor.contains_point(-1, 0));
    }

    #[test]
    fn test_monitor_with_negative_coordinates() {
        // 模拟位于主显示器左侧的副显示器
        let monitor = MonitorSnapshot::new(1, -1920, 0, 1920, 1080, 1.0);

        assert!(monitor.contains_point(-1920, 0));
        assert!(monitor.contains_point(-1, 540));
        assert!(!monitor.contains_point(0, 0)); // 主显示器区域
        assert_eq!(monitor.right(), 0);
    }

    #[test]
    fn test_coordinate_conversion() {
        let monitor = MonitorSnapshot::new(0, 0, 0, 2560, 1440, 1.5);

        // 逻辑 -> 物理
        let (px, py) = monitor.logical_to_physical(100.0, 100.0);
        assert_eq!(px, 150);
        assert_eq!(py, 150);

        // 物理 -> 逻辑
        let (lx, ly) = monitor.physical_to_logical(150, 150);
        assert_eq!(lx, 100.0);
        assert_eq!(ly, 100.0);
    }

    #[test]
    fn test_monitor_boundaries() {
        let monitor = MonitorSnapshot::new(0, 100, 200, 1920, 1080, 1.0);

        assert_eq!(monitor.right(), 2020);
        assert_eq!(monitor.bottom(), 1280);
    }

    #[test]
    fn test_serialization() {
        let monitor = MonitorSnapshot::new(0, 0, 0, 1920, 1080, 1.5);
        let result =
            SnapshotResult::new("/tmp/test.png".to_string(), 1920, 1080, 1.5, vec![monitor]);

        // 测试序列化
        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"path\":\"/tmp/test.png\""));
        assert!(json.contains("\"width\":1920"));
        assert!(json.contains("\"dpr\":1.5"));

        // 测试反序列化
        let deserialized: SnapshotResult = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.path, result.path);
        assert_eq!(deserialized.width, result.width);
        assert_eq!(deserialized.monitors.len(), 1);
    }
}
