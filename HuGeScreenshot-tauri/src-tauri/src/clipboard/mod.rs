//! 剪贴板监听器模块
//!
//! 监听系统剪贴板变化，将文字和图片内容自动保存到历史记录。
//! 支持暂停/恢复监听（工作台打开时暂停，避免干扰用户操作）。
//!
//! ## 支持的剪贴板格式
//!
//! - **文字**: 自动保存到历史记录（content_type: "text"）
//! - **图片**: 自动保存为 PNG 文件并添加到历史记录（content_type: "image"）
//!   - 支持从 Word、浏览器、画图等应用复制的图片
//!   - 使用 Windows 原生剪贴板序列号检测变化（不做重复的大数据读取）
//!   - PNG 编码和文件保存在独立线程中异步完成，不阻塞监听循环

use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};
#[cfg(not(windows))]
use std::sync::atomic::AtomicU32;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use arboard::Clipboard;
use image::codecs::png::PngEncoder;
use image::{ColorType, GenericImageView, ImageEncoder};
use tauri::{AppHandle, Manager};
use tracing::{debug, error, info, warn};

use crate::database::history::ScreenshotRecord;

/// 剪贴板监听器
pub struct ClipboardWatcher {
    /// 是否暂停监听
    paused: Arc<AtomicBool>,
    /// 是否已停止
    stopped: Arc<AtomicBool>,
    /// 是否正在处理图片（防止并发处理）
    processing_image: Arc<AtomicBool>,
    /// 跳过下一次图片检测（用于 copy_file_to_clipboard 后避免重复保存）
    skip_next_image: Arc<AtomicBool>,
}

impl ClipboardWatcher {
    /// 创建新的剪贴板监听器
    pub fn new() -> Self {
        Self {
            paused: Arc::new(AtomicBool::new(false)),
            stopped: Arc::new(AtomicBool::new(false)),
            processing_image: Arc::new(AtomicBool::new(false)),
            skip_next_image: Arc::new(AtomicBool::new(false)),
        }
    }

    /// 设置跳过下一次图片检测
    /// 在 copy_file_to_clipboard 等操作后调用，防止监听器重复保存
    pub fn set_skip_next_image(&self) {
        self.skip_next_image.store(true, Ordering::Relaxed);
        debug!("[ClipboardWatcher] 已设置跳过下一次图片检测");
    }

    /// 暂停监听
    pub fn pause(&self) {
        self.paused.store(true, Ordering::Relaxed);
        info!("[ClipboardWatcher] 监听已暂停");
    }

    /// 恢复监听
    pub fn resume(&self) {
        self.paused.store(false, Ordering::Relaxed);
        info!("[ClipboardWatcher] 监听已恢复");
    }

    /// 停止监听
    pub fn stop(&self) {
        self.stopped.store(true, Ordering::Relaxed);
        info!("[ClipboardWatcher] 监听已停止");
    }

    /// 是否已暂停
    pub fn is_paused(&self) -> bool {
        self.paused.load(Ordering::Relaxed)
    }

    /// 启动监听线程
    pub fn start(&self, app: AppHandle) {
        let paused = self.paused.clone();
        let stopped = self.stopped.clone();
        let processing_image = self.processing_image.clone();
        let skip_next_image = self.skip_next_image.clone();

        thread::spawn(move || {
            info!("[ClipboardWatcher] 监听线程启动");

            let mut clipboard = match Clipboard::new() {
                Ok(c) => c,
                Err(e) => {
                    error!("[ClipboardWatcher] 无法访问剪贴板: {}", e);
                    return;
                }
            };

            let mut last_text = String::new();
            // 使用 Windows 剪贴板序列号来检测变化（轻量级，不读取数据）
            let mut last_seq_number = get_clipboard_sequence_number();
            // 上次保存图片的时间（防抖：至少间隔 1 秒）
            let mut last_image_save_time = Instant::now();

            // 初始化时读取当前剪贴板文字，避免启动时重复记录
            if let Ok(text) = clipboard.get_text() {
                last_text = text;
            }

            loop {
                if stopped.load(Ordering::Relaxed) {
                    info!("[ClipboardWatcher] 监听线程退出");
                    break;
                }

                if paused.load(Ordering::Relaxed) {
                    thread::sleep(Duration::from_millis(500));
                    continue;
                }

                // 使用剪贴板序列号检测变化（Windows 原生 API，极其轻量）
                let current_seq = get_clipboard_sequence_number();
                if current_seq == last_seq_number {
                    // 剪贴板未变化，跳过
                    thread::sleep(Duration::from_millis(300));
                    continue;
                }
                last_seq_number = current_seq;

                debug!("[ClipboardWatcher] 检测到剪贴板变化 (seq: {})", current_seq);

                // 剪贴板有变化，先检查文字（轻量）
                match clipboard.get_text() {
                    Ok(text) => {
                        if !text.is_empty() && text != last_text {
                            let trimmed = text.trim();
                            if !trimmed.is_empty() {
                                debug!("[ClipboardWatcher] 新文字 ({}字符)", trimmed.len());
                                save_text_to_history(&app, &text);
                                last_text = text;
                            }
                        }
                    }
                    Err(_) => {
                        // 非文字内容，检查是否为图片

                        // 跳过标记：copy_file_to_clipboard 等操作后设置，防止重复保存截图
                        if skip_next_image
                            .compare_exchange(true, false, Ordering::Relaxed, Ordering::Relaxed)
                            .is_ok()
                        {
                            debug!("[ClipboardWatcher] 跳过本次图片检测（截图已通过其他方式保存）");
                            thread::sleep(Duration::from_millis(300));
                            continue;
                        }

                        // 防抖：至少间隔 1 秒才保存图片
                        if last_image_save_time.elapsed() < Duration::from_secs(1) {
                            debug!("[ClipboardWatcher] 图片保存冷却中，跳过");
                            thread::sleep(Duration::from_millis(300));
                            continue;
                        }

                        // 检查是否已有图片在处理中
                        if processing_image.load(Ordering::Relaxed) {
                            debug!("[ClipboardWatcher] 上一张图片仍在处理中，跳过");
                            thread::sleep(Duration::from_millis(300));
                            continue;
                        }

                        // 读取图片数据
                        match clipboard.get_image() {
                            Ok(img) => {
                                info!(
                                    "[ClipboardWatcher] 检测到剪贴板图片 ({}x{}, {:.1} MB RGBA)",
                                    img.width,
                                    img.height,
                                    img.bytes.len() as f64 / 1_048_576.0
                                );

                                last_image_save_time = Instant::now();
                                last_text.clear();

                                // 将重型操作（PNG 编码+保存）放到独立线程，不阻塞监听循环
                                let app_clone = app.clone();
                                let width = img.width;
                                let height = img.height;
                                let rgba_data = img.bytes.into_owned();
                                let processing = processing_image.clone();

                                processing.store(true, Ordering::Relaxed);

                                thread::spawn(move || {
                                    save_image_to_history(&app_clone, &rgba_data, width, height);
                                    processing.store(false, Ordering::Relaxed);
                                });
                            }
                            Err(_) => {
                                // 既不是文字也不是图片（可能是文件等其他格式），跳过
                            }
                        }
                    }
                }

                thread::sleep(Duration::from_millis(300));
            }
        });
    }
}

impl Default for ClipboardWatcher {
    fn default() -> Self {
        Self::new()
    }
}

/// 获取 Windows 剪贴板序列号
///
/// 每次剪贴板内容变化时，序列号会递增。
/// 这是最轻量的剪贴板变化检测方式，不需要读取剪贴板数据。
#[cfg(windows)]
fn get_clipboard_sequence_number() -> u32 {
    // Windows API: GetClipboardSequenceNumber
    // 返回值：当前剪贴板序列号，每次内容变化时递增
    extern "system" {
        fn GetClipboardSequenceNumber() -> u32;
    }
    unsafe { GetClipboardSequenceNumber() }
}

#[cfg(not(windows))]
fn get_clipboard_sequence_number() -> u32 {
    // 非 Windows 平台回退：使用递增计数器（总是触发检查）
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    COUNTER.fetch_add(1, Ordering::Relaxed)
}

/// 将剪贴板图片保存到历史记录（在独立线程中执行）
///
/// 处理流程：
/// 1. 将 RGBA 原始数据编码为 PNG（CPU 密集型，异步执行）
/// 2. 保存到历史截图目录
/// 3. 生成缩略图
/// 4. 添加到历史记录数据库
fn save_image_to_history(app: &AppHandle, rgba_data: &[u8], width: usize, height: usize) {
    use crate::commands::history_cmd::HistoryState;
    use crate::database::settings::{get_config_path, load_config};
    use chrono::Local;

    let start = Instant::now();

    // 1. 将 RGBA 数据编码为 PNG
    let png_data = match encode_rgba_to_png(rgba_data, width as u32, height as u32) {
        Ok(data) => data,
        Err(e) => {
            warn!("[ClipboardWatcher] 编码图片为 PNG 失败: {}", e);
            return;
        }
    };

    debug!(
        "[ClipboardWatcher] PNG 编码完成 ({:.1} MB → {:.1} MB, 耗时 {}ms)",
        rgba_data.len() as f64 / 1_048_576.0,
        png_data.len() as f64 / 1_048_576.0,
        start.elapsed().as_millis()
    );

    // 2. 计算 PNG 的哈希（用于数据库去重，PNG 比 RGBA 小很多）
    let image_hash = {
        let digest = md5::compute(&png_data);
        format!("{:x}", digest)
    };

    // 3. 确定保存目录
    let config_path = match get_config_path(app) {
        Ok(p) => p,
        Err(e) => {
            warn!("[ClipboardWatcher] 获取配置路径失败: {}", e);
            return;
        }
    };

    let config = match load_config(&config_path) {
        Ok(c) => c,
        Err(e) => {
            warn!("[ClipboardWatcher] 加载配置失败: {}", e);
            return;
        }
    };

    let base_dir = if config.screenshot.save_location.is_empty() {
        match app.path().picture_dir() {
            Ok(p) => p,
            Err(e) => {
                warn!("[ClipboardWatcher] 获取图片目录失败: {}", e);
                return;
            }
        }
    } else {
        PathBuf::from(&config.screenshot.save_location)
    };

    // 4. 创建 历史截图/YYYY年M月D日/ 目录结构
    let now = Local::now();
    let date_folder = now.format("%Y年%-m月%-d日").to_string();
    let history_dir = base_dir.join("历史截图").join(&date_folder);

    if !history_dir.exists() {
        if let Err(e) = fs::create_dir_all(&history_dir) {
            warn!("[ClipboardWatcher] 创建历史截图目录失败: {}", e);
            return;
        }
    }

    // 5. 生成文件名并保存
    let timestamp = now.format("%Y%m%d_%H%M%S_%3f").to_string();
    let filename = format!("clipboard_{}.png", timestamp);
    let file_path = history_dir.join(&filename);

    if let Err(e) = fs::write(&file_path, &png_data) {
        warn!("[ClipboardWatcher] 保存剪贴板图片失败: {}", e);
        return;
    }

    let file_path_str = file_path.to_string_lossy().to_string();
    info!(
        "[ClipboardWatcher] 剪贴板图片已保存: {} ({}x{}, {:.1} KB, 总耗时 {}ms)",
        file_path_str,
        width,
        height,
        png_data.len() as f64 / 1024.0,
        start.elapsed().as_millis()
    );

    // 6. 生成缩略图
    // 【性能优化】直接从 RGBA 原始数据构建 DynamicImage，跳过 PNG→解码 的冗余往返
    let thumbnail_path = if let Some(rgba_image) =
        image::RgbaImage::from_raw(width as u32, height as u32, rgba_data.to_vec())
    {
        let img = image::DynamicImage::ImageRgba8(rgba_image);
        generate_clipboard_thumbnail(&img, &history_dir, &timestamp)
    } else {
        warn!("[ClipboardWatcher] 从 RGBA 数据构建图像失败，尝试从 PNG 解码");
        match image::load_from_memory(&png_data) {
            Ok(img) => generate_clipboard_thumbnail(&img, &history_dir, &timestamp),
            Err(e) => {
                warn!("[ClipboardWatcher] 解析图片生成缩略图失败: {}", e);
                None
            }
        }
    };

    // 7. 添加到历史记录数据库
    if let Some(state) = app.try_state::<HistoryState>() {
        let record = ScreenshotRecord {
            file_path: file_path_str,
            thumbnail_path,
            width: width as u32,
            height: height as u32,
            file_size: Some(png_data.len() as i64),
            content_type: "image".to_string(),
            image_hash: Some(image_hash),
            metadata: Some(r#"{"captureMode":"clipboard"}"#.to_string()),
            ..Default::default()
        };

        let state_clone = state.inner().clone();
        tauri::async_runtime::spawn(async move {
            match state_clone.add_record(record).await {
                Ok(id) => {
                    info!("[ClipboardWatcher] 剪贴板图片已保存到历史记录 (id: {})", id);
                }
                Err(e) => {
                    warn!("[ClipboardWatcher] 保存剪贴板图片到数据库失败: {}", e);
                }
            }
        });
    }
}

/// 将 RGBA 原始数据编码为 PNG 格式
fn encode_rgba_to_png(rgba_data: &[u8], width: u32, height: u32) -> Result<Vec<u8>, String> {
    let mut png_buffer = Vec::with_capacity(rgba_data.len() / 4); // 预分配（PNG 通常比 RGBA 小很多）
    let cursor = Cursor::new(&mut png_buffer);
    let encoder = PngEncoder::new(cursor);

    encoder
        .write_image(rgba_data, width, height, ColorType::Rgba8.into())
        .map_err(|e| format!("PNG 编码失败: {}", e))?;

    Ok(png_buffer)
}

/// 为剪贴板图片生成缩略图
///
/// 缩略图存放在 thumbnails/ 子目录，最大尺寸 200px，JPEG 格式
fn generate_clipboard_thumbnail(
    img: &image::DynamicImage,
    history_dir: &Path,
    timestamp: &str,
) -> Option<String> {
    let thumbnails_dir = history_dir.join("thumbnails");
    if !thumbnails_dir.exists() {
        if let Err(e) = fs::create_dir_all(&thumbnails_dir) {
            warn!("[ClipboardWatcher] 创建缩略图目录失败: {}", e);
            return None;
        }
    }

    const MAX_THUMBNAIL_SIZE: u32 = 200;
    let (width, height) = img.dimensions();
    let (thumb_width, thumb_height) = if width > height {
        let ratio = MAX_THUMBNAIL_SIZE as f64 / width as f64;
        (MAX_THUMBNAIL_SIZE, (height as f64 * ratio) as u32)
    } else {
        let ratio = MAX_THUMBNAIL_SIZE as f64 / height as f64;
        ((width as f64 * ratio) as u32, MAX_THUMBNAIL_SIZE)
    };

    let thumbnail = img.thumbnail(thumb_width, thumb_height);
    let thumb_filename = format!("clipboard_{}_thumb.jpg", timestamp);
    let thumb_path = thumbnails_dir.join(&thumb_filename);

    if let Err(e) = thumbnail.save(&thumb_path) {
        warn!("[ClipboardWatcher] 保存缩略图失败: {}", e);
        return None;
    }

    Some(thumb_path.to_string_lossy().to_string())
}

/// 将文字保存到历史记录
fn save_text_to_history(app: &AppHandle, text: &str) {
    use crate::commands::history_cmd::HistoryState;

    if let Some(state) = app.try_state::<HistoryState>() {
        let preview = if text.len() > 100 {
            // 确保截断位置在字符边界上（不会切断多字节 UTF-8 字符）
            let mut end = 100;
            while !text.is_char_boundary(end) && end > 0 {
                end -= 1;
            }
            format!("{}...", &text[..end])
        } else {
            text.to_string()
        };

        let record = ScreenshotRecord {
            file_path: String::new(), // 文字类型无文件路径
            width: 0,
            height: 0,
            content_type: "text".to_string(),
            text_content: Some(text.to_string()),
            ocr_text: Some(preview), // 用 ocr_text 字段做搜索
            ..Default::default()
        };

        // 使用 tokio runtime 执行异步操作
        let state_clone: crate::commands::history_cmd::HistoryState = state.inner().clone();
        tauri::async_runtime::spawn(async move {
            match state_clone.add_record(record).await {
                Ok(id) => {
                    debug!("[ClipboardWatcher] 文字已保存到历史记录 (id: {})", id);
                }
                Err(e) => {
                    warn!("[ClipboardWatcher] 保存文字失败: {}", e);
                }
            }
        });
    }
}
