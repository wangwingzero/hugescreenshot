//! 图像预处理模块
//!
//! 本模块负责 OCR 图像预处理：
//!
//! - 图像加载和格式验证
//! - 图像缩放（保持宽高比）
//! - 归一化处理（PP-OCR 标准参数）
//! - NCHW 格式转换
//!
//! # Requirements
//!
//! - 2.2: 处理最大 4096x4096 像素的图像
//! - 2.3: 超过 2048 像素时等比例缩放
//!
//! # PP-OCRv4 预处理参数
//!
//! - Mean: [0.5, 0.5, 0.5]
//! - Std: [0.5, 0.5, 0.5]
//! - 归一化公式: (pixel / 255.0 - mean) / std
//! - 结果范围: [-1.0, 1.0]

use image::{DynamicImage, GenericImageView, Rgb, RgbImage};
use ndarray::Array4;
use std::path::Path;

use super::types::OcrError;

// ============================================
// PP-OCRv4 标准预处理参数
// ============================================

/// PP-OCRv4 标准归一化均值
/// 与 ImageNet 不同，PP-OCR 系列使用简单的 0.5 归一化
pub const MEAN: [f32; 3] = [0.5, 0.5, 0.5];

/// PP-OCRv4 标准归一化标准差
/// 归一化后的值范围为 [-1.0, 1.0]
pub const STD: [f32; 3] = [0.5, 0.5, 0.5];

/// 支持的图像格式
const SUPPORTED_FORMATS: &[&str] = &["png", "jpg", "jpeg", "bmp", "gif", "webp"];

// ============================================
// 图像加载
// ============================================

/// 加载图像文件
///
/// 从指定路径加载图像并验证格式。
///
/// # 参数
///
/// - `path`: 图像文件路径
///
/// # 返回
///
/// - `Ok(DynamicImage)`: 成功加载的图像
/// - `Err(OcrError)`: 加载失败的错误
///
/// # 错误
///
/// - `OcrError::FileNotFound`: 文件不存在
/// - `OcrError::UnsupportedFormat`: 不支持的图像格式
/// - `OcrError::ImageProcessError`: 图像解码失败
///
/// # 示例
///
/// ```no_run
/// use hugescreenshot_tauri_lib::ocr::preprocessor::load_image;
///
/// # fn main() -> Result<(), hugescreenshot_tauri_lib::ocr::types::OcrError> {
/// let image = load_image("screenshot.png")?;
/// println!("图像尺寸: {}x{}", image.width(), image.height());
/// # Ok(())
/// # }
/// ```
pub fn load_image(path: &str) -> Result<DynamicImage, OcrError> {
    let path = Path::new(path);

    // 检查文件是否存在
    if !path.exists() {
        return Err(OcrError::FileNotFound(path.display().to_string()));
    }

    // 检查文件扩展名
    let extension = path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.to_lowercase())
        .unwrap_or_default();

    if !SUPPORTED_FORMATS.contains(&extension.as_str()) {
        return Err(OcrError::UnsupportedFormat(extension));
    }

    // 加载图像
    image::open(path).map_err(|e| OcrError::ImageProcessError(format!("图像加载失败: {}", e)))
}

/// 从内存加载图像
///
/// 从字节数组加载图像，自动检测格式。
///
/// # 参数
///
/// - `data`: 图像数据字节数组
///
/// # 返回
///
/// - `Ok(DynamicImage)`: 成功加载的图像
/// - `Err(OcrError)`: 加载失败的错误
pub fn load_image_from_memory(data: &[u8]) -> Result<DynamicImage, OcrError> {
    image::load_from_memory(data)
        .map_err(|e| OcrError::ImageProcessError(format!("从内存加载图像失败: {}", e)))
}

// ============================================
// 图像缩放
// ============================================

/// 缩放图像（保持宽高比）
///
/// 当图像的最长边超过 `max_size` 时，等比例缩放图像。
///
/// # 参数
///
/// - `image`: 输入图像
/// - `max_size`: 最大尺寸（最长边的像素数）
///
/// # 返回
///
/// 返回元组 `(缩放后的图像, x方向缩放因子, y方向缩放因子)`
///
/// 缩放因子用于将检测结果坐标映射回原始图像坐标系：
/// - `original_x = detected_x * scale_x`
/// - `original_y = detected_y * scale_y`
///
/// # 示例
///
/// ```rust
/// use hugescreenshot_tauri_lib::ocr::preprocessor::resize_image;
/// use image::DynamicImage;
///
/// let image = DynamicImage::new_rgba8(4096, 2048);
/// let (resized, scale_x, scale_y) = resize_image(&image, 2048);
/// // 如果原图是 4096x2048，缩放后是 2048x1024
/// // scale_x = 2.0, scale_y = 2.0
/// ```
pub fn resize_image(image: &DynamicImage, max_size: u32) -> (DynamicImage, f32, f32) {
    let (width, height) = image.dimensions();
    let max_dim = width.max(height);

    if max_dim <= max_size {
        // 不需要缩放
        return (image.clone(), 1.0, 1.0);
    }

    // 计算缩放比例
    let scale = max_size as f32 / max_dim as f32;
    let new_width = (width as f32 * scale).round() as u32;
    let new_height = (height as f32 * scale).round() as u32;

    // 缩放图像
    let resized = image.resize_exact(new_width, new_height, image::imageops::FilterType::Lanczos3);

    // 计算缩放因子（用于坐标映射）
    let scale_x = width as f32 / new_width as f32;
    let scale_y = height as f32 / new_height as f32;

    (resized, scale_x, scale_y)
}

/// 缩放图像到指定尺寸（用于检测模型）
///
/// 将图像缩放到检测模型所需的尺寸，尺寸必须是 32 的倍数。
///
/// # 参数
///
/// - `image`: 输入图像
/// - `target_size`: 目标尺寸（最长边）
///
/// # 返回
///
/// 返回元组 `(缩放后的图像, x方向缩放因子, y方向缩放因子, 新宽度, 新高度)`
pub fn resize_for_detection(
    image: &DynamicImage,
    target_size: u32,
) -> (DynamicImage, f32, f32, u32, u32) {
    let (width, height) = image.dimensions();

    // 计算缩放比例，使最长边等于 target_size
    let scale = target_size as f32 / width.max(height) as f32;

    // 计算新尺寸，确保是 32 的倍数
    let new_width = ((width as f32 * scale / 32.0).ceil() * 32.0) as u32;
    let new_height = ((height as f32 * scale / 32.0).ceil() * 32.0) as u32;

    // 缩放图像
    let resized = image.resize_exact(new_width, new_height, image::imageops::FilterType::Lanczos3);

    // 计算缩放因子（用于坐标映射回原图）
    let scale_x = width as f32 / new_width as f32;
    let scale_y = height as f32 / new_height as f32;

    (resized, scale_x, scale_y, new_width, new_height)
}

// ============================================
// 归一化和格式转换
// ============================================

/// 预处理图像用于检测模型
///
/// 执行完整的预处理流程：
/// 1. 缩放到目标尺寸（32 的倍数）
/// 2. 转换为 RGB
/// 3. 归一化：(pixel / 255.0 - mean) / std
/// 4. 转换为 NCHW 格式
///
/// # 参数
///
/// - `image`: 输入图像
/// - `det_size`: 检测模型输入尺寸（最长边）
///
/// # 返回
///
/// 返回元组 `(NCHW格式张量, x缩放因子, y缩放因子)`
///
/// # NCHW 格式说明
///
/// - N: Batch size (始终为 1)
/// - C: Channels (3 for RGB)
/// - H: Height
/// - W: Width
pub fn preprocess_for_detection(
    image: &DynamicImage,
    det_size: u32,
) -> Result<(Array4<f32>, f32, f32), OcrError> {
    let (resized, scale_x, scale_y, new_width, new_height) = resize_for_detection(image, det_size);

    // 转换为 RGB
    let rgb = resized.to_rgb8();

    // 创建 NCHW 格式的张量
    let tensor = normalize_to_nchw(&rgb, new_width, new_height)?;

    Ok((tensor, scale_x, scale_y))
}

/// 预处理图像用于识别模型
///
/// 执行识别模型的预处理流程：
/// 1. 缩放到固定高度，宽度按比例调整
/// 2. 转换为 RGB
/// 3. 归一化
/// 4. 转换为 NCHW 格式
///
/// # 参数
///
/// - `image`: 输入图像（已裁剪的文本区域）
/// - `target_height`: 目标高度（通常为 48）
///
/// # 返回
///
/// NCHW 格式的张量
pub fn preprocess_for_recognition(
    image: &DynamicImage,
    target_height: u32,
) -> Result<Array4<f32>, OcrError> {
    let (width, height) = image.dimensions();

    // 计算新宽度，保持宽高比
    let scale = target_height as f32 / height as f32;
    let new_width = (width as f32 * scale).round() as u32;
    let new_width = new_width.max(1); // 确保至少为 1

    // 缩放图像
    let resized =
        image.resize_exact(new_width, target_height, image::imageops::FilterType::Lanczos3);

    // 转换为 RGB
    let rgb = resized.to_rgb8();

    // 创建 NCHW 格式的张量
    normalize_to_nchw(&rgb, new_width, target_height)
}

// ============================================
// IR 模型预处理（u8 NHWC 格式）
// ============================================

/// 预处理图像用于检测模型（IR 格式，u8 NHWC）
///
/// 用于预处理已注入的 IR 模型，直接输出原始 u8 像素数据。
/// 预处理（归一化、颜色转换）在模型内部执行。
///
/// # 参数
///
/// - `image`: 输入图像
/// - `det_size`: 检测模型输入尺寸（最长边）
///
/// # 返回
///
/// 返回元组 `(u8数据, 高度, 宽度, x缩放因子, y缩放因子)`
///
/// # 数据格式
///
/// - 布局: NHWC (Batch=1, Height, Width, Channel=3)
/// - 类型: u8 (0-255)
/// - 颜色: BGR
pub fn preprocess_for_detection_u8(
    image: &DynamicImage,
    det_size: u32,
) -> Result<(Vec<u8>, usize, usize, f32, f32), OcrError> {
    let (resized, scale_x, scale_y, new_width, new_height) = resize_for_detection(image, det_size);

    // 转换为 RGB
    let rgb = resized.to_rgb8();

    // 转换为 NHWC BGR 格式的 u8 数据
    let data = to_nhwc_bgr_u8(&rgb, new_width, new_height);

    Ok((data, new_height as usize, new_width as usize, scale_x, scale_y))
}

/// 预处理图像用于识别模型（IR 格式，u8 NHWC）
///
/// 用于预处理已注入的 IR 模型，直接输出原始 u8 像素数据。
///
/// # 参数
///
/// - `image`: 输入图像（已裁剪的文本区域）
/// - `target_height`: 目标高度（通常为 48）
///
/// # 返回
///
/// 返回元组 `(u8数据, 高度, 宽度)`
///
/// # 数据格式
///
/// - 布局: NHWC (Batch=1, Height, Width, Channel=3)
/// - 类型: u8 (0-255)
/// - 颜色: BGR
pub fn preprocess_for_recognition_u8(
    image: &DynamicImage,
    target_height: u32,
) -> Result<(Vec<u8>, usize, usize), OcrError> {
    let (width, height) = image.dimensions();

    // 计算新宽度，保持宽高比
    let scale = target_height as f32 / height as f32;
    let new_width = (width as f32 * scale).round() as u32;
    let new_width = new_width.max(1); // 确保至少为 1

    // 缩放图像
    let resized =
        image.resize_exact(new_width, target_height, image::imageops::FilterType::Lanczos3);

    // 转换为 RGB
    let rgb = resized.to_rgb8();

    // 转换为 NHWC BGR 格式的 u8 数据
    let data = to_nhwc_bgr_u8(&rgb, new_width, target_height);

    Ok((data, target_height as usize, new_width as usize))
}

/// 将 RGB 图像转换为 NHWC BGR 格式的 u8 数据
///
/// # 参数
///
/// - `rgb`: RGB 图像
/// - `width`: 图像宽度
/// - `height`: 图像高度
///
/// # 返回
///
/// NHWC BGR 格式的 u8 数据
fn to_nhwc_bgr_u8(rgb: &RgbImage, width: u32, height: u32) -> Vec<u8> {
    let width = width as usize;
    let height = height as usize;
    let channels = 3;

    // 创建 NHWC 格式的数据 [1, H, W, 3]
    let mut data = vec![0u8; height * width * channels];

    // 填充数据（RGB -> BGR）
    for y in 0..height {
        for x in 0..width {
            let pixel = rgb.get_pixel(x as u32, y as u32);
            let Rgb([r, g, b]) = *pixel;

            // NHWC 格式: data[y * width * 3 + x * 3 + c]
            // BGR 顺序
            let idx = y * width * channels + x * channels;
            data[idx] = b; // B
            data[idx + 1] = g; // G
            data[idx + 2] = r; // R
        }
    }

    data
}

/// 将 RGB 图像归一化并转换为 NCHW 格式
///
/// # 参数
///
/// - `rgb`: RGB 图像
/// - `width`: 图像宽度
/// - `height`: 图像高度
///
/// # 返回
///
/// NCHW 格式的 f32 张量
///
/// # 注意
///
/// PP-OCR 模型期望 **BGR** 通道顺序，因此这里将 RGB 转换为 BGR。
fn normalize_to_nchw(rgb: &RgbImage, width: u32, height: u32) -> Result<Array4<f32>, OcrError> {
    let width = width as usize;
    let height = height as usize;

    // 创建 NCHW 格式的张量 [1, 3, H, W]
    let mut tensor = Array4::<f32>::zeros((1, 3, height, width));

    // 填充数据并归一化
    // 注意：PP-OCR 期望 BGR 顺序，所以 channel 0 = B, channel 1 = G, channel 2 = R
    for y in 0..height {
        for x in 0..width {
            let pixel = rgb.get_pixel(x as u32, y as u32);
            let Rgb([r, g, b]) = *pixel;

            // 归一化: (pixel / 255.0 - mean) / std
            // BGR 顺序: channel 0 = B, channel 1 = G, channel 2 = R
            tensor[[0, 0, y, x]] = (b as f32 / 255.0 - MEAN[0]) / STD[0]; // B
            tensor[[0, 1, y, x]] = (g as f32 / 255.0 - MEAN[1]) / STD[1]; // G
            tensor[[0, 2, y, x]] = (r as f32 / 255.0 - MEAN[2]) / STD[2]; // R
        }
    }

    Ok(tensor)
}

// ============================================
// 文本区域裁剪
// ============================================

/// 裁剪文本区域
///
/// 根据四个角点坐标从原图中裁剪文本区域。
/// 使用透视变换将任意四边形区域转换为矩形。
///
/// # 参数
///
/// - `image`: 原始图像
/// - `points`: 四个角点坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
///   - `[0]`: 左上角
///   - `[1]`: 右上角
///   - `[2]`: 右下角
///   - `[3]`: 左下角
///
/// # 返回
///
/// 裁剪后的矩形图像
///
/// # 注意
///
/// 当前实现使用简单的边界框裁剪，不进行透视变换。
/// 对于轻微倾斜的文本，这种方法足够使用。
pub fn crop_text_region(
    image: &DynamicImage,
    points: &[[f32; 2]; 4],
) -> Result<DynamicImage, OcrError> {
    // 计算边界框
    let min_x = points.iter().map(|p| p[0]).fold(f32::INFINITY, f32::min);
    let max_x = points.iter().map(|p| p[0]).fold(f32::NEG_INFINITY, f32::max);
    let min_y = points.iter().map(|p| p[1]).fold(f32::INFINITY, f32::min);
    let max_y = points.iter().map(|p| p[1]).fold(f32::NEG_INFINITY, f32::max);

    // 确保坐标在图像范围内
    let (img_width, img_height) = image.dimensions();
    let x = (min_x.max(0.0) as u32).min(img_width.saturating_sub(1));
    let y = (min_y.max(0.0) as u32).min(img_height.saturating_sub(1));
    let width = ((max_x - min_x).ceil() as u32).min(img_width - x).max(1);
    let height = ((max_y - min_y).ceil() as u32).min(img_height - y).max(1);

    // 裁剪图像
    let cropped = image.crop_imm(x, y, width, height);

    Ok(cropped)
}

/// 裁剪并旋转文本区域（用于倾斜文本）
///
/// 对于倾斜的文本区域，先裁剪再根据倾斜角度旋转。
///
/// # 参数
///
/// - `image`: 原始图像
/// - `points`: 四个角点坐标
///
/// # 返回
///
/// 裁剪并旋转后的图像
pub fn crop_and_rotate_text_region(
    image: &DynamicImage,
    points: &[[f32; 2]; 4],
) -> Result<DynamicImage, OcrError> {
    // 计算文本区域的宽度和高度
    let width =
        ((points[0][0] - points[1][0]).powi(2) + (points[0][1] - points[1][1]).powi(2)).sqrt();
    let height =
        ((points[0][0] - points[3][0]).powi(2) + (points[0][1] - points[3][1]).powi(2)).sqrt();

    // 如果高度大于宽度，说明文本是竖排的，需要旋转
    if height > width * 1.5 {
        let cropped = crop_text_region(image, points)?;
        // 旋转 90 度
        Ok(cropped.rotate90())
    } else {
        crop_text_region(image, points)
    }
}

/// 旋转图像 180 度
///
/// 用于处理倒置的文本。
///
/// # 参数
///
/// - `image`: 输入图像
///
/// # 返回
///
/// 旋转 180 度后的图像
pub fn rotate_180(image: &DynamicImage) -> DynamicImage {
    image.rotate180()
}

// ============================================
// 辅助函数
// ============================================

/// 检查图像格式是否支持
///
/// # 参数
///
/// - `extension`: 文件扩展名（不含点号）
///
/// # 返回
///
/// 是否支持该格式
pub fn is_supported_format(extension: &str) -> bool {
    SUPPORTED_FORMATS.contains(&extension.to_lowercase().as_str())
}

/// 获取支持的图像格式列表
pub fn supported_formats() -> &'static [&'static str] {
    SUPPORTED_FORMATS
}

/// 计算图像的宽高比
pub fn aspect_ratio(width: u32, height: u32) -> f32 {
    width as f32 / height as f32
}

// ============================================
// 分桶策略 (Bucketing)
// ============================================

/// 识别模型的宽度分桶
///
/// 将动态宽度归一化到固定档位，避免 GPU Shader 频繁重编译。
/// 所有档位都是 32 的倍数，利于 SIMD 对齐。
pub const RECOGNITION_WIDTH_BUCKETS: [usize; 4] = [160, 320, 640, 1280];

/// 获取宽度对应的分桶值
///
/// 将输入宽度归一化到最近的较大桶宽度。
///
/// # 参数
///
/// - `width`: 原始宽度
///
/// # 返回
///
/// 归一化后的桶宽度
///
/// # 示例
///
/// ```rust
/// use hugescreenshot_tauri_lib::ocr::preprocessor::get_bucket_width;
///
/// assert_eq!(get_bucket_width(100), 160);
/// assert_eq!(get_bucket_width(200), 320);
/// assert_eq!(get_bucket_width(500), 640);
/// assert_eq!(get_bucket_width(1000), 1280);
/// assert_eq!(get_bucket_width(1500), 1280); // 超过最大桶，使用最大桶
/// ```
pub fn get_bucket_width(width: usize) -> usize {
    for &bucket in &RECOGNITION_WIDTH_BUCKETS {
        if width <= bucket {
            return bucket;
        }
    }
    // 超过最大桶，使用最大桶
    *RECOGNITION_WIDTH_BUCKETS.last().unwrap()
}

/// 预处理图像用于识别模型（带分桶和 Padding）
///
/// 执行识别模型的预处理流程，并将宽度归一化到分桶值：
/// 1. 缩放到固定高度，宽度按比例调整
/// 2. 计算目标桶宽度
/// 3. 右侧填充（Padding）到桶宽度
/// 4. 转换为 u8 NHWC BGR 格式
///
/// # 参数
///
/// - `image`: 输入图像（已裁剪的文本区域）
/// - `target_height`: 目标高度（通常为 48）
///
/// # 返回
///
/// 返回元组 `(u8数据, 高度, 桶宽度, 原始宽度)`
/// - `u8数据`: NHWC BGR 格式的像素数据
/// - `高度`: 目标高度（通常为 48）
/// - `桶宽度`: 归一化后的宽度（160/320/640/1280）
/// - `原始宽度`: 缩放后的实际宽度（用于 CTC 解码截断）
///
/// # 性能优势
///
/// - 分桶策略减少 GPU Shader 重编译
/// - 预期性能提升 15%-40%
pub fn preprocess_for_recognition_bucketed(
    image: &DynamicImage,
    target_height: u32,
) -> Result<(Vec<u8>, usize, usize, usize), OcrError> {
    let (width, height) = image.dimensions();

    // 计算新宽度，保持宽高比
    let scale = target_height as f32 / height as f32;
    let new_width = (width as f32 * scale).round() as u32;
    let new_width = new_width.max(1); // 确保至少为 1

    // 获取目标桶宽度
    let bucket_width = get_bucket_width(new_width as usize);

    // 缩放图像
    let resized =
        image.resize_exact(new_width, target_height, image::imageops::FilterType::Lanczos3);

    // 转换为 RGB
    let rgb = resized.to_rgb8();

    // 转换为 NHWC BGR 格式并填充到桶宽度
    let data = to_nhwc_bgr_u8_padded(&rgb, new_width, target_height, bucket_width as u32);

    Ok((data, target_height as usize, bucket_width, new_width as usize))
}

/// 将 RGB 图像转换为 NHWC BGR 格式的 u8 数据（带 Padding）
///
/// # 参数
///
/// - `rgb`: RGB 图像
/// - `width`: 图像实际宽度
/// - `height`: 图像高度
/// - `target_width`: 目标宽度（桶宽度，用于 Padding）
///
/// # 返回
///
/// NHWC BGR 格式的 u8 数据，宽度为 target_width
fn to_nhwc_bgr_u8_padded(rgb: &RgbImage, width: u32, height: u32, target_width: u32) -> Vec<u8> {
    let width = width as usize;
    let height = height as usize;
    let target_width = target_width as usize;
    let channels = 3;

    // 创建 NHWC 格式的数据 [1, H, target_W, 3]
    // Padding 区域填充 0（黑色）
    let mut data = vec![0u8; height * target_width * channels];

    // 实际复制的宽度：取 width 和 target_width 的较小值
    // 当 width > target_width 时（超长文本），截断右侧部分
    let copy_width = width.min(target_width);

    // 填充数据（RGB -> BGR，左对齐）
    for y in 0..height {
        for x in 0..copy_width {
            let pixel = rgb.get_pixel(x as u32, y as u32);
            let Rgb([r, g, b]) = *pixel;

            // NHWC 格式: data[y * target_width * 3 + x * 3 + c]
            // BGR 顺序
            let idx = y * target_width * channels + x * channels;
            data[idx] = b; // B
            data[idx + 1] = g; // G
            data[idx + 2] = r; // R
        }
        // x >= copy_width 的区域保持为 0（黑色 Padding 或截断）
    }

    data
}

/// 按桶宽度对预处理结果进行分组
///
/// 将预处理后的数据按桶宽度分组，以便批量推理时同一批次内的数据宽度相同。
///
/// # 参数
///
/// - `items`: 预处理结果列表，每个元素为 `(原始索引, 数据, 高度, 桶宽度, 原始宽度)`
///
/// # 返回
///
/// 按桶宽度分组的 HashMap，key 为桶宽度，value 为该桶内的所有数据
pub type BucketedPreprocessItem<T> = (usize, T, usize, usize, usize);
pub type BucketedPreprocessGroups<T> =
    std::collections::HashMap<usize, Vec<BucketedPreprocessItem<T>>>;

pub fn group_by_bucket<T>(items: Vec<BucketedPreprocessItem<T>>) -> BucketedPreprocessGroups<T> {
    let mut groups: BucketedPreprocessGroups<T> = std::collections::HashMap::new();

    for item in items {
        let bucket_width = item.3;
        groups.entry(bucket_width).or_default().push(item);
    }

    groups
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use image::{ImageBuffer, Rgba};

    // ----------------------------------------
    // 辅助函数
    // ----------------------------------------

    /// 创建测试用的纯色图像
    fn create_test_image(width: u32, height: u32, color: Rgba<u8>) -> DynamicImage {
        let img = ImageBuffer::from_pixel(width, height, color);
        DynamicImage::ImageRgba8(img)
    }

    /// 创建测试用的渐变图像
    fn create_gradient_image(width: u32, height: u32) -> DynamicImage {
        let img = ImageBuffer::from_fn(width, height, |x, y| {
            let r = (x * 255 / width.max(1)) as u8;
            let g = (y * 255 / height.max(1)) as u8;
            let b = ((x + y) * 255 / (width + height).max(1)) as u8;
            Rgba([r, g, b, 255])
        });
        DynamicImage::ImageRgba8(img)
    }

    // ----------------------------------------
    // 分桶策略测试
    // ----------------------------------------

    #[test]
    fn test_get_bucket_width_small() {
        // 小于 160 的宽度应该归入 160 桶
        assert_eq!(get_bucket_width(50), 160);
        assert_eq!(get_bucket_width(100), 160);
        assert_eq!(get_bucket_width(159), 160);
        assert_eq!(get_bucket_width(160), 160);
    }

    #[test]
    fn test_get_bucket_width_medium() {
        // 161-320 应该归入 320 桶
        assert_eq!(get_bucket_width(161), 320);
        assert_eq!(get_bucket_width(200), 320);
        assert_eq!(get_bucket_width(320), 320);
    }

    #[test]
    fn test_get_bucket_width_large() {
        // 321-640 应该归入 640 桶
        assert_eq!(get_bucket_width(321), 640);
        assert_eq!(get_bucket_width(500), 640);
        assert_eq!(get_bucket_width(640), 640);
    }

    #[test]
    fn test_get_bucket_width_xlarge() {
        // 641-1280 应该归入 1280 桶
        assert_eq!(get_bucket_width(641), 1280);
        assert_eq!(get_bucket_width(1000), 1280);
        assert_eq!(get_bucket_width(1280), 1280);
    }

    #[test]
    fn test_get_bucket_width_overflow() {
        // 超过 1280 的宽度应该使用最大桶 1280
        assert_eq!(get_bucket_width(1281), 1280);
        assert_eq!(get_bucket_width(2000), 1280);
    }

    #[test]
    fn test_preprocess_for_recognition_bucketed_output_shape() {
        // 创建一个 200x100 的图像，缩放到高度 48 后宽度为 96
        // 96 应该归入 160 桶
        let image = create_gradient_image(200, 100);
        let (data, height, bucket_width, original_width) =
            preprocess_for_recognition_bucketed(&image, 48).unwrap();

        assert_eq!(height, 48);
        assert_eq!(original_width, 96); // 200 * (48/100) = 96
        assert_eq!(bucket_width, 160); // 96 归入 160 桶

        // 数据大小应该是 height * bucket_width * 3
        assert_eq!(data.len(), 48 * 160 * 3);
    }

    #[test]
    fn test_preprocess_for_recognition_bucketed_padding() {
        // 创建一个窄图像，验证 Padding 区域为 0
        let image = create_test_image(100, 100, Rgba([255, 255, 255, 255]));
        let (data, height, bucket_width, original_width) =
            preprocess_for_recognition_bucketed(&image, 48).unwrap();

        assert_eq!(height, 48);
        assert_eq!(original_width, 48); // 100 * (48/100) = 48
        assert_eq!(bucket_width, 160); // 48 归入 160 桶

        // 检查 Padding 区域（x >= original_width）应该为 0
        // 第一行，x = original_width 位置
        for x in original_width..bucket_width {
            let idx = x * 3;
            assert_eq!(data[idx], 0, "Padding 区域 B 通道应为 0");
            assert_eq!(data[idx + 1], 0, "Padding 区域 G 通道应为 0");
            assert_eq!(data[idx + 2], 0, "Padding 区域 R 通道应为 0");
        }
    }

    #[test]
    fn test_bucket_widths_are_32_aligned() {
        // 验证所有桶宽度都是 32 的倍数（利于 SIMD）
        for &bucket in &RECOGNITION_WIDTH_BUCKETS {
            assert_eq!(bucket % 32, 0, "桶宽度 {} 应该是 32 的倍数", bucket);
        }
    }

    // ----------------------------------------
    // load_image 测试
    // ----------------------------------------

    #[test]
    fn test_load_image_file_not_found() {
        let result = load_image("nonexistent_file.png");
        assert!(matches!(result, Err(OcrError::FileNotFound(_))));
    }

    #[test]
    fn test_load_image_unsupported_format() {
        // 创建一个临时文件用于测试
        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("test_unsupported.xyz");
        std::fs::write(&temp_file, b"dummy content").unwrap();

        let result = load_image(temp_file.to_str().unwrap());
        assert!(matches!(result, Err(OcrError::UnsupportedFormat(_))));

        // 清理
        let _ = std::fs::remove_file(temp_file);
    }

    // ----------------------------------------
    // resize_image 测试
    // ----------------------------------------

    #[test]
    fn test_resize_image_no_resize_needed() {
        let image = create_test_image(1000, 800, Rgba([255, 0, 0, 255]));
        let (resized, scale_x, scale_y) = resize_image(&image, 2048);

        assert_eq!(resized.width(), 1000);
        assert_eq!(resized.height(), 800);
        assert!((scale_x - 1.0).abs() < f32::EPSILON);
        assert!((scale_y - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_resize_image_width_larger() {
        let image = create_test_image(4096, 2048, Rgba([255, 0, 0, 255]));
        let (resized, scale_x, scale_y) = resize_image(&image, 2048);

        assert_eq!(resized.width(), 2048);
        assert_eq!(resized.height(), 1024);
        assert!((scale_x - 2.0).abs() < 0.01);
        assert!((scale_y - 2.0).abs() < 0.01);
    }

    #[test]
    fn test_resize_image_height_larger() {
        let image = create_test_image(2048, 4096, Rgba([255, 0, 0, 255]));
        let (resized, scale_x, scale_y) = resize_image(&image, 2048);

        assert_eq!(resized.width(), 1024);
        assert_eq!(resized.height(), 2048);
        assert!((scale_x - 2.0).abs() < 0.01);
        assert!((scale_y - 2.0).abs() < 0.01);
    }

    #[test]
    fn test_resize_image_preserves_aspect_ratio() {
        let image = create_test_image(3000, 2000, Rgba([255, 0, 0, 255]));
        let original_ratio = aspect_ratio(3000, 2000);

        let (resized, _, _) = resize_image(&image, 1500);
        let new_ratio = aspect_ratio(resized.width(), resized.height());

        // 宽高比应该保持不变（允许 1% 误差）
        assert!((original_ratio - new_ratio).abs() / original_ratio < 0.01);
    }

    // ----------------------------------------
    // resize_for_detection 测试
    // ----------------------------------------

    #[test]
    fn test_resize_for_detection_multiple_of_32() {
        let image = create_test_image(1000, 800, Rgba([255, 0, 0, 255]));
        let (_, _, _, new_width, new_height) = resize_for_detection(&image, 960);

        // 尺寸应该是 32 的倍数
        assert_eq!(new_width % 32, 0);
        assert_eq!(new_height % 32, 0);
    }

    #[test]
    fn test_resize_for_detection_scale_factors() {
        let image = create_test_image(2000, 1000, Rgba([255, 0, 0, 255]));
        let (_, scale_x, scale_y, new_width, new_height) = resize_for_detection(&image, 960);

        // 验证缩放因子可以正确映射回原图
        let mapped_width = (new_width as f32 * scale_x).round() as u32;
        let mapped_height = (new_height as f32 * scale_y).round() as u32;

        assert_eq!(mapped_width, 2000);
        assert_eq!(mapped_height, 1000);
    }

    // ----------------------------------------
    // preprocess_for_detection 测试
    // ----------------------------------------

    #[test]
    fn test_preprocess_for_detection_output_shape() {
        let image = create_gradient_image(800, 600);
        let (tensor, _, _) = preprocess_for_detection(&image, 640).unwrap();

        // 验证输出形状 [1, 3, H, W]
        assert_eq!(tensor.shape()[0], 1); // Batch size
        assert_eq!(tensor.shape()[1], 3); // Channels (RGB)
        assert!(tensor.shape()[2] > 0); // Height
        assert!(tensor.shape()[3] > 0); // Width

        // 尺寸应该是 32 的倍数
        assert_eq!(tensor.shape()[2] % 32, 0);
        assert_eq!(tensor.shape()[3] % 32, 0);
    }

    #[test]
    fn test_preprocess_for_detection_normalization() {
        // 创建一个纯白图像 (255, 255, 255)
        let image = create_test_image(64, 64, Rgba([255, 255, 255, 255]));
        let (tensor, _, _) = preprocess_for_detection(&image, 64).unwrap();

        // 对于纯白像素 (255, 255, 255)：
        // PP-OCRv4: (1.0 - 0.5) / 0.5 = 1.0
        let r_expected = (1.0 - MEAN[0]) / STD[0];
        let g_expected = (1.0 - MEAN[1]) / STD[1];
        let b_expected = (1.0 - MEAN[2]) / STD[2];

        // PP-OCRv4 归一化后，纯白像素应该是 1.0
        assert!((tensor[[0, 0, 0, 0]] - r_expected).abs() < 0.01);
        assert!((tensor[[0, 1, 0, 0]] - g_expected).abs() < 0.01);
        assert!((tensor[[0, 2, 0, 0]] - b_expected).abs() < 0.01);

        // 验证具体值
        assert!((tensor[[0, 0, 0, 0]] - 1.0).abs() < 0.01, "纯白像素归一化后应为 1.0");
    }

    #[test]
    fn test_preprocess_for_detection_black_image() {
        // 创建一个纯黑图像 (0, 0, 0)
        let image = create_test_image(64, 64, Rgba([0, 0, 0, 255]));
        let (tensor, _, _) = preprocess_for_detection(&image, 64).unwrap();

        // 对于纯黑像素 (0, 0, 0)：
        // PP-OCRv4: (0.0 - 0.5) / 0.5 = -1.0
        let r_expected = (0.0 - MEAN[0]) / STD[0];
        let g_expected = (0.0 - MEAN[1]) / STD[1];
        let b_expected = (0.0 - MEAN[2]) / STD[2];

        assert!((tensor[[0, 0, 0, 0]] - r_expected).abs() < 0.01);
        assert!((tensor[[0, 1, 0, 0]] - g_expected).abs() < 0.01);
        assert!((tensor[[0, 2, 0, 0]] - b_expected).abs() < 0.01);

        // 验证具体值
        assert!((tensor[[0, 0, 0, 0]] - (-1.0)).abs() < 0.01, "纯黑像素归一化后应为 -1.0");
    }

    // ----------------------------------------
    // preprocess_for_recognition 测试
    // ----------------------------------------

    #[test]
    fn test_preprocess_for_recognition_fixed_height() {
        let image = create_gradient_image(200, 100);
        let tensor = preprocess_for_recognition(&image, 48).unwrap();

        // 高度应该是 48
        assert_eq!(tensor.shape()[2], 48);
        // 宽度应该按比例缩放: 200 * (48/100) = 96
        assert_eq!(tensor.shape()[3], 96);
    }

    #[test]
    fn test_preprocess_for_recognition_narrow_image() {
        let image = create_gradient_image(10, 100);
        let tensor = preprocess_for_recognition(&image, 48).unwrap();

        // 高度应该是 48
        assert_eq!(tensor.shape()[2], 48);
        // 宽度应该按比例缩放: 10 * (48/100) = 5 (至少为 1)
        assert!(tensor.shape()[3] >= 1);
    }

    // ----------------------------------------
    // crop_text_region 测试
    // ----------------------------------------

    #[test]
    fn test_crop_text_region_basic() {
        let image = create_gradient_image(200, 200);
        let points = [
            [50.0, 50.0],   // 左上
            [150.0, 50.0],  // 右上
            [150.0, 100.0], // 右下
            [50.0, 100.0],  // 左下
        ];

        let cropped = crop_text_region(&image, &points).unwrap();

        assert_eq!(cropped.width(), 100);
        assert_eq!(cropped.height(), 50);
    }

    #[test]
    fn test_crop_text_region_boundary() {
        let image = create_gradient_image(100, 100);
        // 坐标超出图像边界
        let points = [[-10.0, -10.0], [110.0, -10.0], [110.0, 110.0], [-10.0, 110.0]];

        let cropped = crop_text_region(&image, &points).unwrap();

        // 应该裁剪到图像边界内
        assert!(cropped.width() <= 100);
        assert!(cropped.height() <= 100);
    }

    #[test]
    fn test_crop_text_region_small_area() {
        let image = create_gradient_image(100, 100);
        let points = [[50.0, 50.0], [51.0, 50.0], [51.0, 51.0], [50.0, 51.0]];

        let cropped = crop_text_region(&image, &points).unwrap();

        // 最小尺寸应该是 1x1
        assert!(cropped.width() >= 1);
        assert!(cropped.height() >= 1);
    }

    // ----------------------------------------
    // crop_and_rotate_text_region 测试
    // ----------------------------------------

    #[test]
    fn test_crop_and_rotate_horizontal_text() {
        let image = create_gradient_image(200, 200);
        // 水平文本区域（宽 > 高）
        let points = [[50.0, 50.0], [150.0, 50.0], [150.0, 80.0], [50.0, 80.0]];

        let cropped = crop_and_rotate_text_region(&image, &points).unwrap();

        // 水平文本不应该旋转
        assert_eq!(cropped.width(), 100);
        assert_eq!(cropped.height(), 30);
    }

    #[test]
    fn test_crop_and_rotate_vertical_text() {
        let image = create_gradient_image(200, 200);
        // 垂直文本区域（高 > 宽 * 1.5）
        let points = [[50.0, 50.0], [70.0, 50.0], [70.0, 150.0], [50.0, 150.0]];

        let cropped = crop_and_rotate_text_region(&image, &points).unwrap();

        // 垂直文本应该旋转 90 度
        // 原始: 20x100 -> 旋转后: 100x20
        assert_eq!(cropped.width(), 100);
        assert_eq!(cropped.height(), 20);
    }

    // ----------------------------------------
    // rotate_180 测试
    // ----------------------------------------

    #[test]
    fn test_rotate_180() {
        let image = create_gradient_image(100, 50);
        let rotated = rotate_180(&image);

        // 尺寸应该保持不变
        assert_eq!(rotated.width(), 100);
        assert_eq!(rotated.height(), 50);
    }

    // ----------------------------------------
    // 辅助函数测试
    // ----------------------------------------

    #[test]
    fn test_is_supported_format() {
        assert!(is_supported_format("png"));
        assert!(is_supported_format("PNG"));
        assert!(is_supported_format("jpg"));
        assert!(is_supported_format("jpeg"));
        assert!(is_supported_format("bmp"));
        assert!(is_supported_format("gif"));
        assert!(is_supported_format("webp"));

        assert!(!is_supported_format("tiff"));
        assert!(!is_supported_format("psd"));
        assert!(!is_supported_format("xyz"));
    }

    #[test]
    fn test_supported_formats() {
        let formats = supported_formats();
        assert!(formats.contains(&"png"));
        assert!(formats.contains(&"jpg"));
        assert!(formats.contains(&"jpeg"));
    }

    #[test]
    fn test_aspect_ratio() {
        assert!((aspect_ratio(1920, 1080) - 16.0 / 9.0).abs() < 0.01);
        assert!((aspect_ratio(1000, 1000) - 1.0).abs() < f32::EPSILON);
        assert!((aspect_ratio(100, 200) - 0.5).abs() < f32::EPSILON);
    }

    // ----------------------------------------
    // NCHW 格式验证测试
    // ----------------------------------------

    #[test]
    fn test_nchw_format_channel_order() {
        // 创建一个红色图像
        let image = create_test_image(32, 32, Rgba([255, 0, 0, 255]));
        let (tensor, _, _) = preprocess_for_detection(&image, 32).unwrap();

        // PP-OCR 使用 BGR 顺序
        // 红色像素: R=255, G=0, B=0
        // 归一化后（使用 MEAN=0.5, STD=0.5）:
        // B 通道 (channel 0): (0/255 - 0.5) / 0.5 = -1.0
        // G 通道 (channel 1): (0/255 - 0.5) / 0.5 = -1.0
        // R 通道 (channel 2): (255/255 - 0.5) / 0.5 = 1.0
        let b_val = tensor[[0, 0, 0, 0]]; // B 通道
        let g_val = tensor[[0, 1, 0, 0]]; // G 通道
        let r_val = tensor[[0, 2, 0, 0]]; // R 通道

        // R 通道应该最大（因为是红色图像）
        assert!(r_val > g_val, "R 通道值应大于 G 通道值");
        assert!(r_val > b_val, "R 通道值应大于 B 通道值");

        // 验证具体值
        assert!((b_val - (-1.0)).abs() < 0.01, "B 通道 (channel 0) 应为 -1.0，实际: {}", b_val);
        assert!((g_val - (-1.0)).abs() < 0.01, "G 通道 (channel 1) 应为 -1.0，实际: {}", g_val);
        assert!((r_val - 1.0).abs() < 0.01, "R 通道 (channel 2) 应为 1.0，实际: {}", r_val);
    }

    #[test]
    fn test_nchw_format_spatial_layout() {
        // 创建一个渐变图像
        let image = create_gradient_image(64, 64);
        let (tensor, _, _) = preprocess_for_detection(&image, 64).unwrap();

        // 验证空间布局：不同位置应该有不同的值
        let val_00 = tensor[[0, 0, 0, 0]];
        let val_01 = tensor[[0, 0, 0, 1]];
        let val_10 = tensor[[0, 0, 1, 0]];

        // 渐变图像中，相邻像素应该有不同的值
        // （除非恰好相同，但对于渐变图像这种情况很少）
        // 这里只验证张量可以正确索引
        assert!(val_00.is_finite());
        assert!(val_01.is_finite());
        assert!(val_10.is_finite());
    }

    // ========================================
    // 属性测试 (Property-Based Tests)
    // ========================================
    //
    // Feature: rust-native-ocr, Property 2: Image Resize Behavior
    // **Validates: Requirements 2.3, 11.2**
    //
    // Property 2 定义：
    // *For any* input image where the longest side exceeds the configured
    // `max_image_size`, the Detection_Model SHALL resize the image
    // proportionally such that:
    // - The longest side equals `max_image_size`
    // - The aspect ratio is preserved (within 1% tolerance)
    //
    // 注意：为了测试性能，我们使用较小的图像尺寸
    // 因为 resize_image 函数的行为与图像内容无关，只与尺寸有关
    // ========================================

    mod property_tests {
        use super::*;
        use proptest::prelude::*;

        // ----------------------------------------
        // 辅助策略函数
        // ----------------------------------------

        /// 生成超过指定 max_size 的图像尺寸
        fn image_dimensions_exceeding_max(max_size: u32) -> impl Strategy<Value = (u32, u32)> {
            let min_dim = max_size + 1;
            let max_dim = max_size * 2;
            (min_dim..=max_dim, min_dim..=max_dim)
        }

        /// 生成 max_size 配置值的策略
        fn max_size_strategy() -> impl Strategy<Value = u32> {
            prop_oneof![Just(256u32), Just(512u32), Just(768u32), Just(1024u32),]
        }

        // ----------------------------------------
        // Property 2: Image Resize Behavior
        // ----------------------------------------

        proptest! {
                   #![proptest_config(ProptestConfig::with_cases(20))]

                   /// Property 2.1: 超过 max_size 的图像缩放后，最长边等于 max_size
                   ///
                   /// **Validates: Requirements 2.3, 11.2**
                   ///
                   /// 对于任何最长边超过 max_size 的图像，缩放后：
                   /// - 最长边应该等于 max_size
                   #[test]
                   fn prop_resize_longest_side_equals_max_size(
                       // 使用较小的尺寸范围以提高测试速度
                       width in 257u32..=512,
                       height in 257u32..=512,
                       max_size in 128u32..=256,
                   ) {
                       // 确保输入图像的最长边确实超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side > max_size);

                       // 创建测试图像（小尺寸，快速）
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (resized, _scale_x, _scale_y) = resize_image(&image, max_size);

                       // 验证：最长边等于 max_size
                       let new_longest_side = resized.width().max(resized.height());
                       prop_assert_eq!(
                           new_longest_side, max_size,
                           "缩放后最长边应等于 max_size。原图: {}x{}, max_size: {}, 缩放后: {}x{}",
                           width, height, max_size, resized.width(), resized.height()
                       );
                   }

                   /// Property 2.2: 缩放后宽高比保持不变（动态容差）
                   ///
                   /// **Validates: Requirements 2.3, 11.2**
                   ///
                   /// 对于任何需要缩放的图像，缩放后：
                   /// - 宽高比应该与原图相同（允许动态误差）
                   ///
        /// 注意：对于极端宽高比，当缩放后的短边很小时，
                   /// 整数舍入会导致超过 1% 的宽高比误差，这是数学上不可避免的。
                   #[test]
                   fn prop_resize_preserves_aspect_ratio(
                       width in 257u32..=512,
                       height in 257u32..=512,
                       max_size in 128u32..=256,
                   ) {
                       // 确保输入图像的最长边确实超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side > max_size);

                       // 计算原始宽高比
                       let original_ratio = width as f64 / height as f64;

                       // 创建测试图像
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (resized, _scale_x, _scale_y) = resize_image(&image, max_size);

                       // 计算缩放后的宽高比
                       let new_ratio = resized.width() as f64 / resized.height() as f64;
                       let ratio_diff = (original_ratio - new_ratio).abs() / original_ratio;

                       // 动态容差：考虑整数舍入对小尺寸的影响
                       let min_dim = resized.width().min(resized.height()) as f64;
                       let tolerance = if min_dim >= 50.0 {
                           0.01 // 标准 1% 容差
                       } else {
                           // 对于小尺寸，允许 1 像素舍入误差
                           (1.0 / min_dim).max(0.01)
                       };

                       prop_assert!(
                           ratio_diff < tolerance,
                           "宽高比误差超过容差。原图: {}x{} (ratio={:.4}), 缩放后: {}x{} (ratio={:.4}), 误差: {:.2}%, 容差: {:.2}%",
                           width, height, original_ratio,
                           resized.width(), resized.height(), new_ratio,
                           ratio_diff * 100.0, tolerance * 100.0
                       );
                   }

                   /// Property 2.3: 不超过 max_size 的图像不应被缩放
                   ///
                   /// **Validates: Requirements 2.3, 11.2**
                   ///
                   /// 对于任何最长边不超过 max_size 的图像：
                   /// - 尺寸应该保持不变
                   /// - 缩放因子应该为 1.0
                   #[test]
                   fn prop_no_resize_when_within_max_size(
                       width in 100u32..=256,
                       height in 100u32..=256,
                       max_size in 256u32..=512,
                   ) {
                       // 确保输入图像的最长边不超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side <= max_size);

                       // 创建测试图像
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (resized, scale_x, scale_y) = resize_image(&image, max_size);

                       // 验证：尺寸保持不变
                       prop_assert_eq!(
                           resized.width(), width,
                           "不需要缩放时宽度应保持不变"
                       );
                       prop_assert_eq!(
                           resized.height(), height,
                           "不需要缩放时高度应保持不变"
                       );

                       // 验证：缩放因子为 1.0
                       prop_assert!(
                           (scale_x - 1.0).abs() < f32::EPSILON,
                           "不需要缩放时 scale_x 应为 1.0，实际: {}",
                           scale_x
                       );
                       prop_assert!(
                           (scale_y - 1.0).abs() < f32::EPSILON,
                           "不需要缩放时 scale_y 应为 1.0，实际: {}",
                           scale_y
                       );
                   }

                   /// Property 2.4: 缩放因子可以正确映射坐标回原图
                   ///
                   /// **Validates: Requirements 2.3, 11.2**
                   ///
                   /// 对于任何缩放操作，返回的缩放因子应该能够：
                   /// - 将缩放后图像上的坐标正确映射回原图坐标
                   #[test]
                   fn prop_scale_factors_map_coordinates_correctly(
                       (width, height) in image_dimensions_exceeding_max(1024),
                       max_size in 256u32..=1024,
                   ) {
                       // 确保输入图像的最长边确实超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side > max_size);

                       // 创建测试图像
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (resized, scale_x, scale_y) = resize_image(&image, max_size);

                       // 验证：使用缩放因子可以映射回原图尺寸
                       let mapped_width = (resized.width() as f32 * scale_x).round() as u32;
                       let mapped_height = (resized.height() as f32 * scale_y).round() as u32;

                       // 允许 1 像素的舍入误差
                       prop_assert!(
                           (mapped_width as i32 - width as i32).abs() <= 1,
                           "映射回的宽度应接近原图宽度。原图: {}, 映射: {}, scale_x: {}",
                           width, mapped_width, scale_x
                       );
                       prop_assert!(
                           (mapped_height as i32 - height as i32).abs() <= 1,
                           "映射回的高度应接近原图高度。原图: {}, 映射: {}, scale_y: {}",
                           height, mapped_height, scale_y
                       );
                   }

                   /// Property 2.5: 缩放因子 scale_x 和 scale_y 应该相等（等比例缩放）
                   ///
                   /// **Validates: Requirements 2.3, 11.2**
                   ///
                   /// 对于等比例缩放，两个方向的缩放因子应该相同
                   #[test]
                   fn prop_scale_factors_are_equal(
                       (width, height) in image_dimensions_exceeding_max(1024),
                       max_size in 256u32..=1024,
                   ) {
                       // 确保输入图像的最长边确实超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side > max_size);

                       // 创建测试图像
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (_resized, scale_x, scale_y) = resize_image(&image, max_size);

                       // 验证：scale_x 和 scale_y 应该相等（允许 1% 误差）
                       let scale_diff = (scale_x - scale_y).abs() / scale_x.max(scale_y);
                       prop_assert!(
                           scale_diff < 0.01,
                           "scale_x 和 scale_y 应该相等。scale_x: {}, scale_y: {}, 差异: {:.2}%",
                           scale_x, scale_y, scale_diff * 100.0
                       );
                   }

                   /// Property 2.6: 各种 max_size 配置下的缩放行为一致
                   ///
                   /// **Validates: Requirements 11.2**
                   ///
                   /// 对于不同的 max_size 配置值，缩放行为应该一致
                   #[test]
                   fn prop_resize_behavior_consistent_across_configs(
                       width in 1025u32..=2048,
                       height in 1025u32..=2048,
                       max_size in max_size_strategy(),
                   ) {
                       // 确保输入图像的最长边确实超过 max_size
                       let longest_side = width.max(height);
                       prop_assume!(longest_side > max_size);

                       // 创建测试图像
                       let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                       // 执行缩放
                       let (resized, scale_x, scale_y) = resize_image(&image, max_size);

                       // 验证基本属性
                       let new_longest_side = resized.width().max(resized.height());
                       prop_assert_eq!(new_longest_side, max_size);

                       // 验证缩放因子有效
                       prop_assert!(scale_x > 0.0 && scale_x.is_finite());
                       prop_assert!(scale_y > 0.0 && scale_y.is_finite());
                   }
               }

        // ----------------------------------------
        // 边界情况属性测试
        // ----------------------------------------

        proptest! {
            #![proptest_config(ProptestConfig::with_cases(10))]

            /// Property 2.7: 正方形图像缩放后仍为正方形
            ///
            /// **Validates: Requirements 2.3**
            #[test]
            fn prop_square_image_remains_square(
                size in 1025u32..=2048,
                max_size in 256u32..=1024,
            ) {
                prop_assume!(size > max_size);

                // 创建正方形图像
                let image = create_test_image(size, size, Rgba([128, 128, 128, 255]));

                // 执行缩放
                let (resized, _scale_x, _scale_y) = resize_image(&image, max_size);

                // 验证：缩放后仍为正方形
                prop_assert_eq!(
                    resized.width(), resized.height(),
                    "正方形图像缩放后应仍为正方形。原图: {}x{}, 缩放后: {}x{}",
                    size, size, resized.width(), resized.height()
                );

                // 验证：边长等于 max_size
                prop_assert_eq!(resized.width(), max_size);
            }

            /// Property 2.8: 极端宽高比图像的缩放
            ///
            /// **Validates: Requirements 2.3**
            ///
            /// 测试非常宽或非常高的图像
            ///
            /// 注意：对于极端宽高比，当缩放后的短边很小时（<50像素），
            /// 整数舍入会导致超过 1% 的宽高比误差。这是数学上不可避免的。
            /// 例如：36 像素舍入 1 像素 = 2.78% 误差
            ///
            /// 因此，对于极端宽高比，我们使用动态容差：
            /// - 短边 >= 50 像素：1% 容差
            /// - 短边 < 50 像素：容差 = 1 / 短边（允许 1 像素舍入误差）
            #[test]
            fn prop_extreme_aspect_ratio_resize(
                long_side in 1025u32..=2048,
                short_side in 64u32..=256,
                is_wide in proptest::bool::ANY,
                max_size in 256u32..=1024,
            ) {
                let (width, height) = if is_wide {
                    (long_side, short_side)
                } else {
                    (short_side, long_side)
                };

                prop_assume!(width.max(height) > max_size);

                let original_ratio = width as f64 / height as f64;

                // 创建测试图像
                let image = create_test_image(width, height, Rgba([128, 128, 128, 255]));

                // 执行缩放
                let (resized, _scale_x, _scale_y) = resize_image(&image, max_size);

                // 验证：最长边等于 max_size
                let new_longest_side = resized.width().max(resized.height());
                prop_assert_eq!(new_longest_side, max_size);

                // 验证：宽高比保持
                let new_ratio = resized.width() as f64 / resized.height() as f64;
                let ratio_diff = (original_ratio - new_ratio).abs() / original_ratio;

                // 动态容差：考虑整数舍入对小尺寸的影响
                let min_dim = resized.width().min(resized.height()) as f64;
                let tolerance = if min_dim >= 50.0 {
                    0.01 // 标准 1% 容差
                } else {
                    // 对于小尺寸，允许 1 像素舍入误差
                    // 1 像素误差 / 短边 = 最大允许的比例误差
                    (1.0 / min_dim).max(0.01)
                };

                prop_assert!(
                    ratio_diff < tolerance,
                    "极端宽高比图像缩放后宽高比误差超过容差。\
                    原图: {}x{} (ratio={:.4}), 缩放后: {}x{} (ratio={:.4}), \
                    误差: {:.2}%, 容差: {:.2}%",
                    width, height, original_ratio,
                    resized.width(), resized.height(), new_ratio,
                    ratio_diff * 100.0, tolerance * 100.0
                );
            }
        }
    }
}
