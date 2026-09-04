//! 截图相关 Tauri 命令
//!
//! 封装截图引擎功能，暴露给前端调用。

use chrono::Local;
use image::GenericImageView;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, State};
use tracing::{debug, error, info, warn};

use crate::commands::history_cmd::{AddHistoryItemParams, HistoryMetadata, HistoryState};
use crate::database::settings::{get_config_path, load_config};
use crate::error::{HuGeError, HuGeResult};
use crate::screenshot::capture::{capture_region_impl, capture_screen, CaptureResult, Rect};
use crate::screenshot::image_hash::compute_bytes_hash;

#[cfg(windows)]
use crate::screenshot::window_detect::get_window_info_by_hwnd;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PreCaptureCrop {
    x: u32,
    y: u32,
    width: u32,
    height: u32,
}

fn rect_end(start: i32, size: u32) -> Option<i32> {
    start.checked_add(i32::try_from(size).ok()?)
}

fn calculate_pre_capture_crop(
    rect: &Rect,
    cached: &CaptureResult,
    image_width: u32,
    image_height: u32,
) -> Option<PreCaptureCrop> {
    if rect.width < 2 || rect.height < 2 || image_width < 2 || image_height < 2 {
        return None;
    }

    let rect_right = rect_end(rect.x, rect.width)?;
    let rect_bottom = rect_end(rect.y, rect.height)?;
    let cached_right = rect_end(cached.x, cached.width)?;
    let cached_bottom = rect_end(cached.y, cached.height)?;

    if rect.x < cached.x
        || rect.y < cached.y
        || rect_right > cached_right
        || rect_bottom > cached_bottom
    {
        return None;
    }

    let crop_x = u32::try_from(rect.x.checked_sub(cached.x)?).ok()?;
    let crop_y = u32::try_from(rect.y.checked_sub(cached.y)?).ok()?;

    if crop_x.checked_add(rect.width)? > image_width
        || crop_y.checked_add(rect.height)? > image_height
    {
        return None;
    }

    Some(PreCaptureCrop { x: crop_x, y: crop_y, width: rect.width, height: rect.height })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct MultiCaptureCropSegment {
    monitor_id: u32,
    source_x: u32,
    source_y: u32,
    width: u32,
    height: u32,
    dest_x: u32,
    dest_y: u32,
}

fn calculate_multi_capture_segments(
    rect: &Rect,
    captures: &[CaptureResult],
) -> Option<Vec<MultiCaptureCropSegment>> {
    if rect.width < 2 || rect.height < 2 {
        return None;
    }

    let rect_right = rect_end(rect.x, rect.width)?;
    let rect_bottom = rect_end(rect.y, rect.height)?;
    let mut segments = Vec::new();
    let mut covered_area = 0u64;

    for capture in captures {
        let capture_right = rect_end(capture.x, capture.width)?;
        let capture_bottom = rect_end(capture.y, capture.height)?;

        let intersect_left = rect.x.max(capture.x);
        let intersect_top = rect.y.max(capture.y);
        let intersect_right = rect_right.min(capture_right);
        let intersect_bottom = rect_bottom.min(capture_bottom);

        if intersect_right <= intersect_left || intersect_bottom <= intersect_top {
            continue;
        }

        let width = u32::try_from(intersect_right - intersect_left).ok()?;
        let height = u32::try_from(intersect_bottom - intersect_top).ok()?;
        covered_area += u64::from(width) * u64::from(height);

        segments.push(MultiCaptureCropSegment {
            monitor_id: capture.monitor_id,
            source_x: u32::try_from(intersect_left - capture.x).ok()?,
            source_y: u32::try_from(intersect_top - capture.y).ok()?,
            width,
            height,
            dest_x: u32::try_from(intersect_left - rect.x).ok()?,
            dest_y: u32::try_from(intersect_top - rect.y).ok()?,
        });
    }

    let total_area = u64::from(rect.width) * u64::from(rect.height);
    if segments.len() < 2 || covered_area != total_area {
        return None;
    }

    segments.sort_by_key(|segment| (segment.dest_y, segment.dest_x, segment.monitor_id));
    Some(segments)
}

fn stitch_pre_capture_rect(
    rect: &Rect,
    captures: &[CaptureResult],
) -> HuGeResult<Option<CaptureResult>> {
    let Some(segments) = calculate_multi_capture_segments(rect, captures) else {
        return Ok(None);
    };

    let mut canvas = image::RgbaImage::new(rect.width, rect.height);
    let canvas_stride = rect.width as usize * 4;

    for segment in &segments {
        let capture = captures
            .iter()
            .find(|capture| capture.monitor_id == segment.monitor_id)
            .ok_or_else(|| {
                HuGeError::CaptureError(format!("未找到显示器 {} 的预截图缓存", segment.monitor_id))
            })?;

        let source_image = image::open(&capture.path)
            .map_err(|e| HuGeError::CaptureError(format!("打开预截图缓存失败: {}", e)))?
            .to_rgba8();
        let source_stride = source_image.width() as usize * 4;
        let source_raw = source_image.as_raw();
        let canvas_raw = canvas.as_mut();
        let copy_width = segment.width as usize * 4;

        for row in 0..segment.height as usize {
            let src_start =
                (segment.source_y as usize + row) * source_stride + segment.source_x as usize * 4;
            let dst_start =
                (segment.dest_y as usize + row) * canvas_stride + segment.dest_x as usize * 4;
            canvas_raw[dst_start..dst_start + copy_width]
                .copy_from_slice(&source_raw[src_start..src_start + copy_width]);
        }
    }

    let path = crate::screenshot::capture::generate_temp_path_pub(segments[0].monitor_id)?;
    let (file_size, image_hash) =
        crate::screenshot::capture::save_bmp_fast_with_hash_pub(&canvas, &path)?;
    crate::screenshot::capture::cache_rgba_pub(canvas.as_raw().clone(), rect.width, rect.height);
    crate::ocr::engine::set_ocr_image_cache(
        path.to_string_lossy().to_string(),
        std::sync::Arc::new(image::DynamicImage::ImageRgba8(canvas)),
    );

    Ok(Some(CaptureResult {
        path: path.to_string_lossy().to_string(),
        width: rect.width,
        height: rect.height,
        dpr: captures.first().map(|capture| capture.dpr).unwrap_or(1.0),
        x: rect.x,
        y: rect.y,
        monitor_id: segments[0].monitor_id,
        image_hash,
        file_size: Some(file_size as i64),
        capture_time_ms: None,
        capture_engine: Some("pre_capture_stitched".to_string()),
    }))
}

fn live_region_capture_fallback_error(reason: impl std::fmt::Display) -> HuGeError {
    HuGeError::CaptureError(format!(
        "{}，已取消实时截图，避免捕获 overlay 导致桌面黑屏；请重新触发截图",
        reason
    ))
}

/// 截取指定区域
///
/// # 参数
///
/// - `rect`: 截取区域（物理像素坐标，虚拟屏幕坐标系）
///
/// # 返回
///
/// 返回截图结果，包含临时文件路径和元数据
///
/// # 示例
///
/// ```ignore
/// let result = capture_region(Rect { x: 0, y: 0, width: 800, height: 600 }).await?;
/// println!("截图保存到: {}", result.path);
/// ```
///
/// # 注意事项
///
/// - 坐标使用虚拟屏幕坐标系（多显示器场景下，副屏可能有负坐标）
/// - 如果区域跨越多个显示器，只会截取主要显示器上的部分
#[tauri::command]
pub async fn capture_region(rect: Rect) -> HuGeResult<CaptureResult> {
    info!("命令调用: capture_region({}, {}, {}, {})", rect.x, rect.y, rect.width, rect.height);
    let _overlay_region_capture_guard = crate::window::overlay::begin_overlay_region_capture()?;

    // 【修复穿透】优先从预缓存的全屏截图裁剪
    // 预缓存截图在 overlay 显示前对每个显示器各截一张，按选区中心点查找匹配的那张。
    let pre_capture_caches = crate::window::overlay::get_pre_capture_caches();

    if let Some(pre_capture) = pre_capture_caches
        .as_ref()
        .and_then(|caches| crate::window::overlay::find_pre_capture_for_rect_in(caches, &rect))
    {
        let pre_capture_path = pre_capture.path.clone();
        info!(
            "从预缓存截图裁剪区域（修复穿透）: {} ({}x{} @ {},{})",
            pre_capture_path, pre_capture.width, pre_capture.height, pre_capture.x, pre_capture.y
        );

        let start = std::time::Instant::now();

        // 【性能优化】优先从内存解码缓存裁剪（~10ms），避免每次从磁盘读取 25MB BMP（~2500ms）
        let img_result = if let Some(cached_img) =
            crate::screenshot::capture::get_decoded_pre_capture(&pre_capture_path)
        {
            info!("命中内存解码缓存，直接裁剪");
            Ok(cached_img)
        } else {
            // 首次：从磁盘读取并解码，然后缓存
            info!("内存解码缓存未命中，从磁盘读取并缓存");
            match image::open(&pre_capture_path) {
                Ok(img) => {
                    let arc_img = std::sync::Arc::new(img);
                    crate::screenshot::capture::set_decoded_pre_capture(
                        pre_capture_path.clone(),
                        std::sync::Arc::clone(&arc_img),
                    );
                    info!("已缓存解码后的预截图图像到内存");
                    Ok(arc_img)
                }
                Err(e) => {
                    warn!("打开预缓存截图失败，回退到实时截图: {}", e);
                    Err(e)
                }
            }
        };

        if let Ok(img) = img_result {
            if let Some(crop) =
                calculate_pre_capture_crop(&rect, &pre_capture, img.width(), img.height())
            {
                let cropped = img.crop_imm(crop.x, crop.y, crop.width, crop.height);
                let cropped_rgba = cropped.to_rgba8();

                // 缓存 RGBA 数据供剪贴板零拷贝使用
                crate::screenshot::capture::cache_rgba_pub(
                    cropped_rgba.as_raw().clone(),
                    crop.width,
                    crop.height,
                );

                // 保存裁剪结果
                let path = crate::screenshot::capture::generate_temp_path_pub(0)?;
                let (file_size, image_hash) =
                    crate::screenshot::capture::save_overlay_temp_bmp_pub(&cropped_rgba, &path)?;

                // 【性能优化】缓存裁剪后的图像供 OCR 直接使用（~0ms vs ~500-2500ms 磁盘重新读取）
                crate::ocr::engine::set_ocr_image_cache(
                    path.to_string_lossy().to_string(),
                    std::sync::Arc::new(cropped),
                );

                let elapsed = start.elapsed().as_millis() as u64;
                info!(
                    "预缓存裁剪完成: {:?}, {}x{}, 耗时: {}ms",
                    path, crop.width, crop.height, elapsed
                );

                return Ok(CaptureResult {
                    path: path.to_string_lossy().to_string(),
                    width: crop.width,
                    height: crop.height,
                    dpr: 1.0,
                    x: rect.x,
                    y: rect.y,
                    monitor_id: pre_capture.monitor_id,
                    image_hash,
                    file_size: Some(file_size as i64),
                    capture_time_ms: Some(elapsed),
                    capture_engine: Some("pre_capture_crop".to_string()),
                });
            } else {
                warn!(
                    "选区不在预缓存截图范围内，回退到实时截图: rect=({}, {}, {}x{}), cached=({}, {}, {}x{}), image={}x{}",
                    rect.x,
                    rect.y,
                    rect.width,
                    rect.height,
                    pre_capture.x,
                    pre_capture.y,
                    pre_capture.width,
                    pre_capture.height,
                    img.width(),
                    img.height()
                );
            }
        }

        return Err(live_region_capture_fallback_error("预缓存裁剪失败"));
    } else if let Some(caches) = pre_capture_caches.as_ref() {
        match stitch_pre_capture_rect(&rect, caches) {
            Ok(Some(stitched)) => {
                info!(
                    "从多屏预缓存拼接区域（OCR 跨屏适配）: {}x{} @ ({}, {})",
                    stitched.width, stitched.height, stitched.x, stitched.y
                );
                return Ok(stitched);
            }
            Ok(None) => {
                return Err(live_region_capture_fallback_error("预缓存截图无法完整覆盖选区"));
            }
            Err(e) => {
                return Err(live_region_capture_fallback_error(format!(
                    "多屏预缓存拼接失败: {}",
                    e
                )));
            }
        }
    } else {
        return Err(live_region_capture_fallback_error("预缓存截图不可用或已过期"));
    }
}

/// 为 Overlay 捕获全屏截图
///
/// 在显示截图 overlay 之前调用，捕获指定显示器的全屏截图。
/// 返回的图片路径可以通过 `convertFileSrc()` 转换为前端可用的 URL。
///
/// # 参数
///
/// - `monitor_id`: 显示器 ID（可选，默认为主显示器）
///
/// # 返回
///
/// 返回截图结果，包含：
/// - `path`: 临时文件路径（需要用 `convertFileSrc()` 转换）
/// - `width`: 图片宽度（物理像素）
/// - `height`: 图片高度（物理像素）
/// - `dpr`: 设备像素比
/// - `x`, `y`: 显示器在虚拟屏幕中的位置
///
/// # 使用场景
///
/// 1. 热键触发截图
/// 2. 调用此命令捕获全屏
/// 3. 显示 overlay 窗口
/// 4. 将截图设置为 overlay 背景
/// 5. 用户在静态背景上选择区域
///
/// # 性能
///
/// - Windows: 使用 DXGI Desktop Duplication API，< 50ms
/// - 其他平台: 使用 screenshots-rs
#[tauri::command]
pub async fn capture_screen_for_overlay(monitor_id: Option<u32>) -> HuGeResult<CaptureResult> {
    info!("命令调用: capture_screen_for_overlay(monitor_id={:?})", monitor_id);

    // 【修复穿透】优先使用预缓存的截图（在 overlay 显示前对每屏各截一张，包含所有窗口）
    let cached = match monitor_id {
        Some(id) => crate::window::overlay::find_pre_capture_by_monitor_id(id)
            .or_else(crate::window::overlay::primary_pre_capture),
        None => crate::window::overlay::primary_pre_capture(),
    };

    if let Some(cached) = cached {
        info!(
            "使用预缓存截图（overlay 显示前已捕获）: {}x{} @ ({}, {})",
            cached.width, cached.height, cached.x, cached.y
        );
        return Ok(cached);
    }

    // 无缓存时回退到实时截图
    warn!("无预缓存截图，回退到实时截图");
    let start = std::time::Instant::now();
    let result = capture_screen(monitor_id).await;
    let elapsed = start.elapsed();

    match &result {
        Ok(r) => {
            info!(
                "全屏截图完成: {}x{} @ ({}, {}), DPR={}, 耗时: {:?}",
                r.width, r.height, r.x, r.y, r.dpr, elapsed
            );
        }
        Err(e) => {
            error!("全屏截图失败: {}", e);
        }
    }

    result
}

/// 截取指定窗口
///
/// # 参数
///
/// - `hwnd`: 窗口句柄（从 `detect_window_at` 或 `get_all_windows` 获取）
///
/// # 返回
///
/// 返回截图结果，包含临时文件路径和元数据
///
/// # 示例
///
/// ```ignore
/// // 先检测窗口
/// let window = detect_window_at(500, 300).await?.unwrap();
/// // 然后截取该窗口
/// let result = capture_window(window.hwnd).await?;
/// ```
///
/// # 注意事项
///
/// - 使用窗口的可视边界（排除 Windows 阴影边框）
/// - 如果窗口被其他窗口遮挡，截图可能包含遮挡内容
/// - 如果窗口无效或已关闭，返回错误
#[tauri::command]
pub async fn capture_window(hwnd: isize) -> HuGeResult<CaptureResult> {
    info!("命令调用: capture_window(hwnd={})", hwnd);

    #[cfg(windows)]
    {
        capture_window_impl(hwnd)
    }

    #[cfg(not(windows))]
    {
        let _ = hwnd;
        Err(HuGeError::CaptureError("窗口截图仅支持 Windows 平台".to_string()))
    }
}

/// Windows 平台窗口截图实现
#[cfg(windows)]
fn capture_window_impl(hwnd: isize) -> HuGeResult<CaptureResult> {
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::WindowsAndMessaging::IsWindow;

    // 验证窗口句柄
    let hwnd_win = HWND(hwnd as *mut std::ffi::c_void);

    let is_valid = unsafe { IsWindow(hwnd_win).as_bool() };
    if !is_valid {
        error!("无效的窗口句柄: {}", hwnd);
        return Err(HuGeError::CaptureError(format!("无效的窗口句柄: {}", hwnd)));
    }

    // 获取窗口信息（包含真实边界）
    let window_info = get_window_info_by_hwnd(hwnd_win)?;

    debug!(
        "窗口截图: {} ({}), 物理边界: ({}, {}) {}x{}",
        window_info.title,
        window_info.class_name,
        window_info.physical_rect.x,
        window_info.physical_rect.y,
        window_info.physical_rect.width,
        window_info.physical_rect.height
    );

    // 使用窗口的物理边界进行区域截图
    capture_region_impl(&window_info.physical_rect)
}

/// 自动保存截图到历史目录
///
/// 根据配置的保存位置，自动创建 `历史截图/YYYY年M月D日/` 目录结构，
/// 并保存截图文件。
///
/// # 参数
///
/// - `app`: Tauri AppHandle
/// - `image_data`: PNG 图片数据（字节数组）
///
/// # 返回
///
/// 返回保存的文件完整路径
///
/// # 目录结构
///
/// ```text
/// {保存位置}/
/// └── 历史截图/
///     └── 2026年1月25日/
///         ├── screenshot_20260125_143052.png
///         └── screenshot_20260125_143105.png
/// ```
#[tauri::command]
pub async fn auto_save_screenshot(
    app: AppHandle,
    image_data: Vec<u8>,
    format: String,
) -> HuGeResult<String> {
    let _ = &format; // 忽略前端传入的 format，统一使用 png
    info!("自动保存截图，格式: png");

    // 获取配置
    let config_path = get_config_path(&app)?;
    let config = load_config(&config_path)?;

    // 确定基础保存目录
    let base_dir = if config.screenshot.save_location.is_empty() {
        // 默认使用图片目录
        app.path().picture_dir().map_err(|e| {
            error!("获取图片目录失败: {}", e);
            HuGeError::CaptureError(format!("获取图片目录失败: {}", e))
        })?
    } else {
        PathBuf::from(&config.screenshot.save_location)
    };

    // 创建 历史截图/YYYY年M月D日/ 目录结构
    let now = Local::now();
    let date_folder = now.format("%Y年%-m月%-d日").to_string();
    let history_dir = base_dir.join("历史截图").join(&date_folder);

    // 确保目录存在
    if !history_dir.exists() {
        fs::create_dir_all(&history_dir).map_err(|e| {
            error!("创建历史截图目录失败: {:?}, 错误: {}", history_dir, e);
            HuGeError::CaptureError(format!("创建目录失败: {}", e))
        })?;
        info!("创建历史截图目录: {:?}", history_dir);
    }

    // 生成文件名: screenshot_YYYYMMDD_HHMMSS.{format}
    let timestamp = now.format("%Y%m%d_%H%M%S").to_string();
    let filename = format!("screenshot_{}.png", timestamp);
    let file_path = history_dir.join(&filename);

    // 写入文件
    fs::write(&file_path, &image_data).map_err(|e| {
        error!("保存截图失败: {:?}, 错误: {}", file_path, e);
        HuGeError::CaptureError(format!("保存截图失败: {}", e))
    })?;

    let path_str = file_path.to_string_lossy().to_string();
    info!("截图已保存到: {}", path_str);

    Ok(path_str)
}

/// 获取截图保存配置
///
/// 返回当前的截图保存设置，包括保存位置、是否自动保存等。
#[tauri::command]
pub async fn get_screenshot_save_config(app: AppHandle) -> HuGeResult<ScreenshotSaveConfig> {
    let config_path = get_config_path(&app)?;
    let config = load_config(&config_path)?;

    Ok(ScreenshotSaveConfig {
        save_location: config.screenshot.save_location,
        auto_save: config.screenshot.auto_save,
    })
}

/// 截图保存配置
#[derive(serde::Serialize, serde::Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ScreenshotSaveConfig {
    pub save_location: String,
    pub auto_save: bool,
}

/// 保存截图时的元数据
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveScreenshotMetadata {
    /// 截图模式：region, window, fullscreen
    pub capture_mode: Option<String>,
    /// 显示器 ID
    pub monitor_id: Option<u32>,
    /// 是否有标注
    pub has_annotations: Option<bool>,
    /// 应用名称
    pub app_name: Option<String>,
    /// 窗口标题
    pub window_title: Option<String>,
}

/// 保存截图并添加历史记录的结果
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveScreenshotResult {
    /// 保存的文件路径
    pub file_path: String,
    /// 历史记录 ID
    pub history_id: i64,
    /// 缩略图路径
    pub thumbnail_path: Option<String>,
}

/// 保存截图并添加到历史记录
///
/// 组合命令，原子化处理：
/// 1. 保存截图文件到历史截图目录
/// 2. 生成缩略图 (200px max, JPEG)
/// 3. 写入历史记录数据库
/// 4. 返回 { filePath, historyId, thumbnailPath }
///
/// # 参数
///
/// - `app`: Tauri AppHandle
/// - `state`: 历史记录状态
/// - `image_data`: PNG 图片数据（字节数组）
/// - `format`: 保存格式（统一使用 png）
/// - `metadata`: 可选的元数据
/// - `ocr_text`: 可选的 OCR 文本（如果已经执行过 OCR）
#[tauri::command]
pub async fn save_screenshot_with_history(
    app: AppHandle,
    state: State<'_, HistoryState>,
    image_data: Vec<u8>,
    format: String,
    metadata: Option<SaveScreenshotMetadata>,
    ocr_text: Option<String>,
) -> HuGeResult<SaveScreenshotResult> {
    let _ = &format; // 忽略前端传入的 format，统一使用 png
    info!("保存截图并添加历史记录，格式: png");

    // 获取配置
    let config_path = get_config_path(&app)?;
    let config = load_config(&config_path)?;

    // 确定基础保存目录
    let base_dir = if config.screenshot.save_location.is_empty() {
        // 默认使用图片目录
        app.path().picture_dir().map_err(|e| {
            error!("获取图片目录失败: {}", e);
            HuGeError::CaptureError(format!("获取图片目录失败: {}", e))
        })?
    } else {
        PathBuf::from(&config.screenshot.save_location)
    };

    // 创建 历史截图/YYYY年M月D日/ 目录结构
    let now = Local::now();
    let date_folder = now.format("%Y年%-m月%-d日").to_string();
    let history_dir = base_dir.join("历史截图").join(&date_folder);

    // 确保目录存在
    if !history_dir.exists() {
        fs::create_dir_all(&history_dir).map_err(|e| {
            error!("创建历史截图目录失败: {:?}, 错误: {}", history_dir, e);
            HuGeError::CaptureError(format!("创建目录失败: {}", e))
        })?;
        info!("创建历史截图目录: {:?}", history_dir);
    }

    // 生成文件名: screenshot_YYYYMMDD_HHMMSS.png
    let timestamp = now.format("%Y%m%d_%H%M%S").to_string();
    let filename = format!("screenshot_{}.png", timestamp);
    let file_path = history_dir.join(&filename);

    // 写入截图文件
    fs::write(&file_path, &image_data).map_err(|e| {
        error!("保存截图失败: {:?}, 错误: {}", file_path, e);
        HuGeError::CaptureError(format!("保存截图失败: {}", e))
    })?;

    let file_path_str = file_path.to_string_lossy().to_string();
    info!("截图已保存到: {}", file_path_str);

    // 【性能优化】只解码一次图像，同时获取尺寸和生成缩略图
    let img = image::load_from_memory(&image_data).map_err(|e| {
        error!("解析图片失败: {}", e);
        HuGeError::CaptureError(format!("解析图片失败: {}", e))
    })?;
    let (width, height) = img.dimensions();
    let file_size = image_data.len() as i64;

    // 【性能优化】直接从内存生成缩略图，避免重新读取文件
    let thumbnail_path = generate_thumbnail_from_memory(&img, &history_dir, &timestamp)?;

    // 构建历史记录元数据
    let history_metadata = metadata.map(|m| HistoryMetadata {
        capture_mode: m.capture_mode,
        monitor_id: m.monitor_id,
        app_name: m.app_name,
        window_title: m.window_title,
        has_annotations: m.has_annotations,
    });

    // 添加到历史记录数据库
    let history_params = AddHistoryItemParams {
        file_path: file_path_str.clone(),
        thumbnail_path: thumbnail_path.clone(),
        width,
        height,
        file_size: Some(file_size),
        ocr_text: ocr_text.clone(), // 使用传入的 OCR 文本
        tags: None,
        metadata: history_metadata,
        content_type: None, // 默认 image
        text_content: None,
    };

    // 计算图片哈希（用于去重）
    let image_hash = compute_bytes_hash(&image_data);
    debug!("图片哈希: {}", image_hash);

    // 获取数据库连接并插入记录（带去重逻辑）
    let history_id = {
        let db_guard = state.db.lock().await;
        let db = db_guard
            .as_ref()
            .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

        // 检查是否存在相同哈希的记录（连续复制去重）
        if let Some(existing_id) = db.find_by_hash(&image_hash)? {
            info!("检测到重复图片（哈希: {}），删除旧记录 ID: {}", image_hash, existing_id);

            // 获取旧记录以删除文件
            if let Some(old_record) = db.get(existing_id)? {
                // 删除旧的截图文件
                if let Err(e) = fs::remove_file(&old_record.file_path) {
                    warn!("删除旧截图文件失败: {} - {}", old_record.file_path, e);
                }
                // 删除旧的缩略图
                if let Some(ref thumb_path) = old_record.thumbnail_path {
                    if let Err(e) = fs::remove_file(thumb_path) {
                        warn!("删除旧缩略图失败: {} - {}", thumb_path, e);
                    }
                }
            }

            // 删除数据库记录
            db.delete(existing_id)?;
        }

        // 转换参数为数据库记录
        let tags_json =
            history_params.tags.as_ref().map(|t| serde_json::to_string(t).unwrap_or_default());
        let metadata_json =
            history_params.metadata.as_ref().map(|m| serde_json::to_string(m).unwrap_or_default());

        let record = crate::database::history::ScreenshotRecord {
            id: 0,
            created_at: String::new(),
            file_path: history_params.file_path.clone(),
            thumbnail_path: history_params.thumbnail_path.clone(),
            width: history_params.width,
            height: history_params.height,
            file_size: history_params.file_size,
            ocr_text: history_params.ocr_text.clone(),
            tags: tags_json,
            metadata: metadata_json,
            image_hash: Some(image_hash),
            is_pinned: false,
            ocr_cached_at: None,
            content_type: "image".to_string(),
            text_content: None,
        };

        db.insert(&record)?
    };

    info!("历史记录已添加，ID: {}", history_id);

    Ok(SaveScreenshotResult { file_path: file_path_str, history_id, thumbnail_path })
}

/// 从文件路径保存截图并添加历史记录
///
/// 【性能优化】前端只传递文件路径字符串，后端直接从磁盘读取图像数据。
/// 避免了 Array.from() 产生的巨型 JSON 序列化开销。
///
/// 适用场景：
/// - 有标注时：前端先将合成图像写入临时文件，再传递路径
/// - 无标注时：直接传递原始截图的路径
///
/// # 参数
///
/// * `file_path` - 要保存的 PNG 图像文件路径
/// * `format` - 保存格式（统一使用 png）
/// * `metadata` - 可选的截图元数据
/// * `ocr_text` - 可选的 OCR 文本
#[tauri::command]
pub async fn save_screenshot_with_history_from_file(
    app: AppHandle,
    state: State<'_, HistoryState>,
    file_path: String,
    format: String,
    metadata: Option<SaveScreenshotMetadata>,
    ocr_text: Option<String>,
) -> HuGeResult<SaveScreenshotResult> {
    info!("从文件保存截图并添加历史记录: {}", file_path);

    // 从磁盘读取图像数据
    let image_data = fs::read(&file_path).map_err(|e| {
        error!("读取图像文件失败: {} - {}", file_path, e);
        HuGeError::CaptureError(format!("读取图像文件失败: {}", e))
    })?;

    // 复用已有逻辑
    save_screenshot_with_history(app, state, image_data, format, metadata, ocr_text).await
}

/// 生成缩略图（从内存中的图像数据）
///
/// 缩略图存放在 thumbnails/ 子目录，最大尺寸 200px，JPEG 格式
///
/// # 性能优化
/// 直接从内存中的图像数据生成缩略图，避免重新从磁盘读取
fn generate_thumbnail_from_memory(
    img: &image::DynamicImage,
    history_dir: &std::path::Path,
    timestamp: &str,
) -> HuGeResult<Option<String>> {
    // 创建缩略图目录
    let thumbnails_dir = history_dir.join("thumbnails");
    if !thumbnails_dir.exists() {
        if let Err(e) = fs::create_dir_all(&thumbnails_dir) {
            warn!("创建缩略图目录失败: {}", e);
            return Ok(None);
        }
    }

    // 计算缩略图尺寸（最大边 200px）
    const MAX_THUMBNAIL_SIZE: u32 = 200;
    let (width, height) = img.dimensions();
    let (thumb_width, thumb_height) = if width > height {
        let ratio = MAX_THUMBNAIL_SIZE as f64 / width as f64;
        (MAX_THUMBNAIL_SIZE, (height as f64 * ratio) as u32)
    } else {
        let ratio = MAX_THUMBNAIL_SIZE as f64 / height as f64;
        ((width as f64 * ratio) as u32, MAX_THUMBNAIL_SIZE)
    };

    // 生成缩略图
    let thumbnail = img.thumbnail(thumb_width, thumb_height);

    // 保存为 JPEG
    let thumb_filename = format!("screenshot_{}_thumb.jpg", timestamp);
    let thumb_path = thumbnails_dir.join(&thumb_filename);

    if let Err(e) = thumbnail.save(&thumb_path) {
        warn!("保存缩略图失败: {}", e);
        return Ok(None);
    }

    let thumb_path_str = thumb_path.to_string_lossy().to_string();
    debug!("缩略图已生成: {}", thumb_path_str);

    Ok(Some(thumb_path_str))
}

/// 保存图像数据到临时文件
///
/// 用于钉图功能：将合成后的截图（包含标注）保存到临时文件，
/// 然后创建钉图窗口显示该图像。
///
/// # 参数
///
/// - `image_data`: PNG 图片数据（字节数组）
/// - `format`: 保存格式（统一使用 png）
///
/// # 返回
///
/// 返回临时文件的完整路径
///
/// # 示例
///
/// ```ignore
/// let temp_path = save_temp_image(image_data, "png").await?;
/// create_pin_window(temp_path, rect).await?;
/// ```
#[tauri::command]
pub async fn save_temp_image(image_data: Vec<u8>, format: String) -> HuGeResult<String> {
    use std::env;
    use std::time::{SystemTime, UNIX_EPOCH};

    let _ = &format; // 忽略前端传入的 format，统一使用 png
    info!("保存临时图像，格式: png, 大小: {} bytes", image_data.len());

    // 获取临时目录
    let temp_dir = env::temp_dir().join("hugescreenshot");

    // 确保目录存在
    if !temp_dir.exists() {
        fs::create_dir_all(&temp_dir).map_err(|e| {
            error!("创建临时目录失败: {:?}, 错误: {}", temp_dir, e);
            HuGeError::FileError(e)
        })?;
    }

    // 生成唯一文件名
    let timestamp =
        SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);

    let filename = format!("pin_{}.png", timestamp);
    let file_path = temp_dir.join(&filename);

    // 写入文件
    fs::write(&file_path, &image_data).map_err(|e| {
        error!("保存临时图像失败: {:?}, 错误: {}", file_path, e);
        HuGeError::FileError(e)
    })?;

    let path_str = file_path.to_string_lossy().to_string();
    info!("临时图像已保存到: {}", path_str);

    Ok(path_str)
}

/// 裁剪指定区域的截图
#[derive(Debug, serde::Deserialize)]
pub struct CropRect {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

/// 裁剪截图并保存到临时文件
///
/// 从原始截图中裁剪出指定区域，
/// 保存为临时文件后交给 OCR 引擎识别。
///
/// # 参数
///
/// - `source_path`: 原始截图路径
/// - `rect`: 裁剪区域（物理像素坐标）
///
/// # 返回
///
/// 返回裁剪后临时文件的路径
#[tauri::command]
pub async fn crop_and_save_temp(source_path: String, rect: CropRect) -> HuGeResult<String> {
    use std::env;
    use std::time::{SystemTime, UNIX_EPOCH};

    debug!("裁剪截图: {} -> ({}, {}) {}x{}", source_path, rect.x, rect.y, rect.width, rect.height);

    let start = std::time::Instant::now();

    // 【性能优化】优先从内存缓存获取解码后的源图像（~0ms vs ~2000ms 磁盘读取）
    let img =
        if let Some(cached_img) = crate::screenshot::capture::get_crop_source_cache(&source_path) {
            debug!("裁剪源图像命中内存缓存");
            cached_img
        } else {
            debug!("裁剪源图像缓存未命中，从磁盘读取并缓存");
            let loaded = image::open(&source_path).map_err(|e| {
                error!("打开截图失败: {} - {}", source_path, e);
                HuGeError::Unknown(format!("打开截图失败: {}", e))
            })?;
            let arc_img = std::sync::Arc::new(loaded);
            crate::screenshot::capture::set_crop_source_cache(
                source_path.clone(),
                std::sync::Arc::clone(&arc_img),
            );
            arc_img
        };

    // 确保裁剪区域在图像范围内
    let img_width = img.width();
    let img_height = img.height();
    let crop_x = rect.x.min(img_width.saturating_sub(1));
    let crop_y = rect.y.min(img_height.saturating_sub(1));
    let crop_w = rect.width.min(img_width - crop_x);
    let crop_h = rect.height.min(img_height - crop_y);

    if crop_w < 2 || crop_h < 2 {
        return Err(HuGeError::Unknown("裁剪区域太小".to_string()));
    }

    // 裁剪
    let cropped = img.crop_imm(crop_x, crop_y, crop_w, crop_h);

    // 保存到临时文件
    let temp_dir = env::temp_dir().join("hugescreenshot");
    if !temp_dir.exists() {
        fs::create_dir_all(&temp_dir).map_err(HuGeError::FileError)?;
    }

    let timestamp =
        SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);

    let filename = format!("crop_{}.png", timestamp);
    let file_path = temp_dir.join(&filename);

    cropped.save(&file_path).map_err(|e| {
        error!("保存裁剪图像失败: {:?} - {}", file_path, e);
        HuGeError::Unknown(format!("保存裁剪图像失败: {}", e))
    })?;

    let path_str = file_path.to_string_lossy().to_string();

    // 【性能优化】缓存裁剪后的图像供 OCR 直接使用（~0ms vs ~500ms 磁盘重新读取）
    crate::ocr::engine::set_ocr_image_cache(path_str.clone(), std::sync::Arc::new(cropped));

    debug!(
        "裁剪图像已保存: {} ({}x{}), 耗时: {}ms",
        path_str,
        crop_w,
        crop_h,
        start.elapsed().as_millis()
    );

    Ok(path_str)
}

#[cfg(test)]
mod tests {
    use super::*;

    use tempfile::tempdir;

    fn cached_capture(x: i32, y: i32, width: u32, height: u32) -> CaptureResult {
        CaptureResult {
            path: "cached.bmp".to_string(),
            width,
            height,
            dpr: 1.0,
            x,
            y,
            monitor_id: 1,
            image_hash: Some("hash".to_string()),
            file_size: Some(1),
            capture_time_ms: Some(1),
            capture_engine: Some("pre_capture".to_string()),
        }
    }

    #[test]
    fn multi_capture_segments_split_selection_across_two_monitors() {
        let rect = Rect { x: 1400, y: 120, width: 500, height: 220 };
        let captures = vec![
            cached_capture(0, 0, 1600, 900),
            CaptureResult {
                path: "cached-right.bmp".to_string(),
                width: 1600,
                height: 900,
                dpr: 1.25,
                x: 1600,
                y: 0,
                monitor_id: 2,
                image_hash: Some("hash2".to_string()),
                file_size: Some(1),
                capture_time_ms: Some(1),
                capture_engine: Some("pre_capture".to_string()),
            },
        ];

        assert_eq!(
            calculate_multi_capture_segments(&rect, &captures),
            Some(vec![
                MultiCaptureCropSegment {
                    monitor_id: 1,
                    source_x: 1400,
                    source_y: 120,
                    width: 200,
                    height: 220,
                    dest_x: 0,
                    dest_y: 0,
                },
                MultiCaptureCropSegment {
                    monitor_id: 2,
                    source_x: 0,
                    source_y: 120,
                    width: 300,
                    height: 220,
                    dest_x: 200,
                    dest_y: 0,
                },
            ])
        );
    }

    #[test]
    fn multi_capture_segments_require_full_coverage() {
        let rect = Rect { x: 1400, y: 120, width: 500, height: 220 };
        let captures = vec![cached_capture(0, 0, 1600, 900)];

        assert_eq!(calculate_multi_capture_segments(&rect, &captures), None);
    }

    #[test]
    fn stitch_pre_capture_rect_preserves_pixels_from_each_monitor() {
        let temp_dir = tempdir().unwrap();
        let left_path = temp_dir.path().join("left.bmp");
        let right_path = temp_dir.path().join("right.bmp");

        image::RgbaImage::from_pixel(2, 2, image::Rgba([255, 0, 0, 255])).save(&left_path).unwrap();
        image::RgbaImage::from_pixel(2, 2, image::Rgba([0, 255, 0, 255]))
            .save(&right_path)
            .unwrap();

        let captures = vec![
            CaptureResult {
                path: left_path.to_string_lossy().to_string(),
                width: 2,
                height: 2,
                dpr: 1.0,
                x: 0,
                y: 0,
                monitor_id: 0,
                image_hash: None,
                file_size: None,
                capture_time_ms: None,
                capture_engine: Some("pre_capture".to_string()),
            },
            CaptureResult {
                path: right_path.to_string_lossy().to_string(),
                width: 2,
                height: 2,
                dpr: 1.0,
                x: 2,
                y: 0,
                monitor_id: 1,
                image_hash: None,
                file_size: None,
                capture_time_ms: None,
                capture_engine: Some("pre_capture".to_string()),
            },
        ];

        let rect = Rect { x: 1, y: 0, width: 2, height: 2 };
        let stitched =
            stitch_pre_capture_rect(&rect, &captures).unwrap().expect("应该成功拼接多屏预截图");
        let stitched_image = image::open(stitched.path).unwrap().to_rgba8();

        assert_eq!(stitched_image.width(), 2);
        assert_eq!(stitched_image.height(), 2);
        assert_eq!(stitched_image.get_pixel(0, 0).0, [255, 0, 0, 255]);
        assert_eq!(stitched_image.get_pixel(1, 0).0, [0, 255, 0, 255]);
    }

    #[test]
    fn pre_capture_crop_rejects_selection_outside_cached_monitor() {
        let cached = cached_capture(0, 0, 1600, 900);
        let rect = Rect { x: -1131, y: 286, width: 516, height: 475 };

        assert_eq!(calculate_pre_capture_crop(&rect, &cached, 1600, 900), None);
    }

    #[test]
    fn pre_capture_crop_offsets_by_cached_monitor_origin() {
        let cached = cached_capture(-1600, 0, 1600, 900);
        let rect = Rect { x: -1131, y: 286, width: 516, height: 475 };

        assert_eq!(
            calculate_pre_capture_crop(&rect, &cached, 1600, 900),
            Some(PreCaptureCrop { x: 469, y: 286, width: 516, height: 475 })
        );
    }

    #[test]
    fn live_region_capture_fallback_is_blocked_during_overlay_session() {
        let error = live_region_capture_fallback_error("预截图缓存不可用");

        assert!(error.to_string().contains("已取消实时截图"));
        assert!(error.to_string().contains("避免捕获 overlay 导致桌面黑屏"));
    }
}
