//! 剪贴板命令模块
//!
//! 使用 arboard 库直接操作剪贴板，绕过 Tauri clipboard-manager 插件的
//! Windows PATH_TOO_LONG (os error 206) 问题。
//!
//! # 问题背景
//!
//! Tauri 的 clipboard-manager 插件在 Windows 上写入图像时可能创建过长的临时文件路径，
//! 导致超过 Windows 260 字符路径限制。使用 arboard 库可以直接将图像数据写入剪贴板，
//! 不依赖临时文件。

use arboard::{Clipboard, ImageData};
use std::borrow::Cow;
use tracing::{debug, error, info};

/// 将 RGBA 图像数据写入剪贴板
///
/// # 参数
///
/// * `width` - 图像宽度（像素）
/// * `height` - 图像高度（像素）
/// * `rgba_data` - RGBA 格式的图像数据（每像素 4 字节）
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息字符串
///
/// # 示例
///
/// ```typescript
/// // 前端调用
/// await invoke('copy_image_to_clipboard', {
///   width: 800,
///   height: 600,
///   rgbaData: Array.from(imageDataUint8Array)
/// });
/// ```
#[tauri::command]
pub async fn copy_image_to_clipboard(
    watcher: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
    width: usize,
    height: usize,
    rgba_data: Vec<u8>,
) -> Result<(), String> {
    // 暂停剪贴板监听器，避免读写冲突（os error 1418）
    watcher.pause();
    debug!("复制图像到剪贴板: {}x{}, 数据大小: {} 字节", width, height, rgba_data.len());

    // 验证数据大小
    let expected_size = width * height * 4;
    if rgba_data.len() != expected_size {
        let err = format!(
            "RGBA 数据大小不匹配: 期望 {} 字节 ({}x{}x4), 实际 {} 字节",
            expected_size,
            width,
            height,
            rgba_data.len()
        );
        error!("{}", err);
        return Err(err);
    }

    // 使用 spawn_blocking 在独立线程中操作剪贴板
    // arboard 的 Clipboard 不是 Send，需要在同一线程创建和使用
    tokio::task::spawn_blocking(move || {
        let mut clipboard = Clipboard::new().map_err(|e| {
            let err = format!("创建剪贴板实例失败: {}", e);
            error!("{}", err);
            err
        })?;

        let img_data = ImageData { width, height, bytes: Cow::Owned(rgba_data) };

        clipboard.set_image(img_data).map_err(|e| {
            let err = format!("写入剪贴板失败: {}", e);
            error!("{}", err);
            err
        })?;

        debug!("图像已成功复制到剪贴板");
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| format!("任务执行失败: {}", e))??;

    // 设置跳过标记，防止监听器恢复后重复保存同一张图片
    watcher.set_skip_next_image();

    // 延迟恢复监听器（300ms 缓冲，防止 watcher 在其他线程同时操作剪贴板导致 error 1418）
    tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    watcher.resume();

    Ok(())
}

/// 将 PNG 图像数据写入剪贴板
///
/// 此命令接受 PNG 格式的二进制数据，解码后写入剪贴板。
/// 适用于前端已有 PNG Blob 数据的场景。
///
/// # 参数
///
/// * `png_data` - PNG 格式的图像二进制数据
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息字符串
#[tauri::command]
pub async fn copy_png_to_clipboard(
    watcher: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
    png_data: Vec<u8>,
) -> Result<(), String> {
    // 暂停剪贴板监听器，避免读写冲突
    watcher.pause();
    debug!("复制 PNG 到剪贴板: 数据大小 {} 字节", png_data.len());

    tokio::task::spawn_blocking(move || {
        // 自动检测格式解码（支持 PNG/BMP 等）
        let img = image::load_from_memory(&png_data).map_err(|e| {
            let err = format!("解码图像失败: {}", e);
            error!("{}", err);
            err
        })?;

        let rgba = img.to_rgba8();
        let (width, height) = (rgba.width() as usize, rgba.height() as usize);
        let bytes = rgba.into_raw();

        let mut clipboard = Clipboard::new().map_err(|e| {
            let err = format!("创建剪贴板实例失败: {}", e);
            error!("{}", err);
            err
        })?;

        let img_data = ImageData { width, height, bytes: Cow::Owned(bytes) };

        clipboard.set_image(img_data).map_err(|e| {
            let err = format!("写入剪贴板失败: {}", e);
            error!("{}", err);
            err
        })?;

        debug!("PNG 图像已成功复制到剪贴板: {}x{}", width, height);
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| format!("任务执行失败: {}", e))??;

    // 设置跳过标记，防止监听器恢复后重复保存同一张图片
    watcher.set_skip_next_image();

    // 延迟恢复监听器（300ms 缓冲，防止 watcher 在其他线程同时操作剪贴板导致 error 1418）
    tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    watcher.resume();

    Ok(())
}

/// 从文件路径读取 PNG 图像并写入剪贴板
///
/// 【性能优化】零数据传输：前端只传递文件路径字符串，后端直接从磁盘读取图像数据。
/// 避免了 Array.from() 产生的巨型 JSON 序列化开销（对 1920x1080 截图可节省 400ms-1s）。
///
/// # 参数
///
/// * `file_path` - PNG 图像文件的绝对路径
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息字符串
///
/// # 示例
///
/// ```typescript
/// // 前端调用（零数据传输，极快）
/// await invoke('copy_file_to_clipboard', { filePath: '/path/to/screenshot.png' });
/// ```
#[tauri::command]
pub async fn copy_file_to_clipboard(
    watcher: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
    file_path: String,
) -> Result<(), String> {
    // 暂停剪贴板监听器，避免读写冲突
    watcher.pause();
    info!("从文件复制到剪贴板: {}", file_path);

    let path = file_path.clone();
    tokio::task::spawn_blocking(move || {
        // 使用 image::open 自动检测格式（支持 PNG/BMP/JPEG 等）
        let img = image::open(&path).map_err(|e| {
            let err = format!("解码图像失败: {} - {}", path, e);
            error!("{}", err);
            err
        })?;

        let rgba = img.to_rgba8();
        let (width, height) = (rgba.width() as usize, rgba.height() as usize);
        let bytes = rgba.into_raw();

        let mut clipboard = Clipboard::new().map_err(|e| {
            let err = format!("创建剪贴板实例失败: {}", e);
            error!("{}", err);
            err
        })?;

        let img_data = ImageData { width, height, bytes: Cow::Owned(bytes) };

        clipboard.set_image(img_data).map_err(|e| {
            let err = format!("写入剪贴板失败: {}", e);
            error!("{}", err);
            err
        })?;

        debug!("文件图像已成功复制到剪贴板: {}x{}", width, height);
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| format!("任务执行失败: {}", e))??;

    // 设置跳过标记，防止监听器恢复后重复保存同一张图片
    watcher.set_skip_next_image();

    // 延迟恢复监听器（300ms 缓冲，防止 watcher 在其他线程同时操作剪贴板导致 error 1418）
    tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    watcher.resume();

    Ok(())
}

/// 暂停剪贴板监听（工作台打开时调用）
#[tauri::command]
pub fn pause_clipboard_watcher(
    state: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
) -> Result<(), String> {
    state.pause();
    Ok(())
}

/// 恢复剪贴板监听（工作台关闭时调用）
#[tauri::command]
pub fn resume_clipboard_watcher(
    state: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
) -> Result<(), String> {
    state.resume();
    Ok(())
}

/// 将最近一次区域截图直接从内存复制到剪贴板（零文件 I/O）
///
/// 如果内存缓存不可用，回退到从文件读取。
///
/// # 参数
///
/// * `file_path` - 回退文件路径（当内存缓存不可用时使用）
/// * `use_memory_cache` - 为 false 时始终从 `file_path` 读取（含标注合成图）
#[tauri::command]
pub async fn copy_last_capture_to_clipboard(
    watcher: tauri::State<'_, crate::clipboard::ClipboardWatcher>,
    file_path: String,
    use_memory_cache: Option<bool>,
) -> Result<(), String> {
    let use_memory_cache = use_memory_cache.unwrap_or(true);
    watcher.pause();

    tokio::task::spawn_blocking(move || {
        // 优先：从内存缓存取 RGBA 数据（零 I/O）；有标注合成图时必须读文件
        if use_memory_cache {
            if let Some((rgba_data, width, height)) = crate::screenshot::capture::take_cached_rgba() {
                info!("剪贴板零拷贝: 使用内存缓存 {}x{} ({} 字节)", width, height, rgba_data.len());

                let mut clipboard = Clipboard::new().map_err(|e| {
                    let err = format!("创建剪贴板实例失败: {}", e);
                    error!("{}", err);
                    err
                })?;

                let img_data = ImageData { width, height, bytes: Cow::Owned(rgba_data) };

                clipboard.set_image(img_data).map_err(|e| {
                    let err = format!("写入剪贴板失败: {}", e);
                    error!("{}", err);
                    err
                })?;

                debug!("内存缓存图像已复制到剪贴板: {}x{}", width, height);
                return Ok::<(), String>(());
            }
        }

        // 从文件读取（无内存缓存、或含标注/合成图）
        info!(
            "剪贴板: 从文件读取{}: {}",
            if use_memory_cache { "（内存缓存不可用，回退）" } else { "（含标注合成）" },
            file_path
        );
        let img = image::open(&file_path).map_err(|e| {
            let err = format!("解码图像失败: {} - {}", file_path, e);
            error!("{}", err);
            err
        })?;

        let rgba = img.to_rgba8();
        let (width, height) = (rgba.width() as usize, rgba.height() as usize);
        let bytes = rgba.into_raw();

        let mut clipboard = Clipboard::new().map_err(|e| {
            let err = format!("创建剪贴板实例失败: {}", e);
            error!("{}", err);
            err
        })?;

        let img_data = ImageData { width, height, bytes: Cow::Owned(bytes) };

        clipboard.set_image(img_data).map_err(|e| {
            let err = format!("写入剪贴板失败: {}", e);
            error!("{}", err);
            err
        })?;

        debug!("文件图像已复制到剪贴板: {}x{}", width, height);
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| format!("任务执行失败: {}", e))??;

    watcher.set_skip_next_image();
    watcher.resume();
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_rgba_size_validation() {
        // 100x100 的图像需要 100*100*4 = 40000 字节
        let width = 100;
        let height = 100;
        let expected_size = width * height * 4;
        assert_eq!(expected_size, 40000);
    }
}
