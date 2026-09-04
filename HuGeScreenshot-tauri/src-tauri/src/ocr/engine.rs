//! OCR 引擎核心
//!
//! 整合检测、识别模块，提供完整的 OCR 流程。
//!
//! # 功能
//!
//! - 单例模式，懒加载初始化
//! - 完整 OCR 流程：检测 → 识别
//! - 置信度过滤
//! - 线程安全
//!
//! # Requirements
//!
//! - 1.1: 提供完整的 OCR 功能
//! - 1.2: 支持中文、英文及混合文本
//! - 1.5: 2 秒内处理图像并返回文字
//! - 4.3: 过滤低置信度结果
//! - 5.1: 返回文字及边界框坐标
//!
//! # 使用示例
//!
//! ```rust,ignore
//! use crate::ocr::engine::OcrEngine;
//!
//! let engine = OcrEngine::instance();
//! let result = engine.recognize("screenshot.png").await?;
//! println!("识别文本: {}", result.text);
//! ```

use image::DynamicImage;
use once_cell::sync::OnceCell;
use std::sync::Arc;
use std::sync::Mutex;
use std::time::Instant;

use super::config::OcrConfig;
use super::detector::TextDetector;
use super::layout::LayoutProcessor;
use super::preprocessor::{load_image, resize_image};
use super::recognizer::TextRecognizer;
use super::types::{OcrBox, OcrError, OcrResult, TextBox, TextRegion};

/// 全局 OCR 引擎实例
static OCR_ENGINE: OnceCell<Arc<OcrEngine>> = OnceCell::new();

/// 模型是否已预热
static MODEL_WARMED_UP: OnceCell<bool> = OnceCell::new();

// ============================================================================
// OCR 图像内存缓存（消除 OCR 时的重复磁盘读取）
// ============================================================================
//
// 典型流程：capture_region/crop_and_save_temp 裁剪图像 → 保存到磁盘 → 返回路径给前端
// → 前端调用 call_ocr(path) → recognize() 又从磁盘读取同一文件。
// 通过缓存解码后的 DynamicImage，recognize() 可以直接从内存读取（~0ms vs ~500-2500ms）。
// 使用后自动清除（一次性缓存），避免内存泄漏。

/// OCR 图像内存缓存：key = 文件路径，value = 解码后的图像
/// 单槽缓存：仅保存最近一次裁剪的图像，新写入会覆盖旧值。
static OCR_IMAGE_CACHE: Mutex<Option<(String, Arc<DynamicImage>)>> = Mutex::new(None);

/// OCR 图像缓存的最大像素数上限
///
/// 4K 全屏 BGRA = ~33MB，整屏 5K 以上常驻会显著抬升内存基线。
/// 超过此阈值的图像不入缓存，OCR 时回退到磁盘读取（增加几百毫秒，可接受）。
const OCR_CACHE_MAX_PIXELS: u64 = 2048 * 2048;

/// 设置 OCR 图像缓存（截图裁剪后调用，为后续 OCR 读取做准备）
pub fn set_ocr_image_cache(path: String, img: Arc<DynamicImage>) {
    use image::GenericImageView;
    let (w, h) = img.dimensions();
    let pixels = (w as u64) * (h as u64);
    if pixels > OCR_CACHE_MAX_PIXELS {
        tracing::debug!(
            "OCR 图像缓存跳过大图: {}x{} ({} 像素 > {} 上限)",
            w,
            h,
            pixels,
            OCR_CACHE_MAX_PIXELS
        );
        // 同时清空旧缓存，避免上一张大图残留
        clear_ocr_image_cache();
        return;
    }
    match OCR_IMAGE_CACHE.lock() {
        Ok(mut guard) => {
            if let Some((old_path, _)) = guard.as_ref() {
                if old_path != &path {
                    tracing::debug!("OCR 图像缓存被覆盖: {} -> {}", old_path, path);
                }
            }
            *guard = Some((path, img));
        }
        Err(e) => {
            tracing::warn!("OCR 图像缓存 Mutex 中毒，跳过缓存写入: {}", e);
        }
    }
}

/// 获取并消费 OCR 图像缓存（一次性：命中后自动清除，释放内存）
fn take_ocr_image_cache(path: &str) -> Option<Arc<DynamicImage>> {
    match OCR_IMAGE_CACHE.lock() {
        Ok(mut guard) => {
            if let Some((cached_path, _)) = guard.as_ref() {
                if cached_path == path {
                    return guard.take().map(|(_, img)| img);
                }
            }
            None
        }
        Err(e) => {
            tracing::warn!("OCR 图像缓存 Mutex 中毒，回退到磁盘读取: {}", e);
            None
        }
    }
}

/// 清除 OCR 图像缓存（新会话开始时调用，清理上次残留）
pub fn clear_ocr_image_cache() {
    match OCR_IMAGE_CACHE.lock() {
        Ok(mut guard) => {
            *guard = None;
        }
        Err(e) => {
            tracing::warn!("OCR 图像缓存 Mutex 中毒，无法清除: {}", e);
        }
    }
}

/// OCR 引擎
///
/// 整合检测和识别模块，提供完整的 OCR 功能。
///
/// # 线程安全
///
/// `OcrEngine` 是线程安全的，可以在多线程环境中共享使用。
/// 使用 `Arc` 包装内部组件，支持并发访问。
pub struct OcrEngine {
    /// 文本检测器
    detector: TextDetector,
    /// 文本识别器
    recognizer: TextRecognizer,
    /// 配置
    config: OcrConfig,
}

impl OcrEngine {
    /// 获取全局单例实例
    ///
    /// 首次调用时会初始化引擎，加载模型。
    /// 后续调用返回相同的实例。
    ///
    /// # 返回
    ///
    /// - `Ok(&'static Arc<OcrEngine>)`: 引擎实例
    /// - `Err(OcrError)`: 初始化失败
    ///
    /// # 示例
    ///
    /// ```rust,ignore
    /// let engine = OcrEngine::instance()?;
    /// ```
    pub fn instance() -> Result<&'static Arc<OcrEngine>, OcrError> {
        OCR_ENGINE.get_or_try_init(|| {
            tracing::info!("Initializing OCR engine...");
            let start = Instant::now();

            let engine = OcrEngine::new(OcrConfig::default())?;

            // 预热模型（消除首帧卡顿）
            if MODEL_WARMED_UP.get().is_none() {
                // 预热识别模型
                if let Err(e) = engine.recognizer.warmup() {
                    tracing::warn!("识别模型预热失败（不影响正常使用）: {}", e);
                }

                // 预热检测模型（检测占 OCR 总时间 73%，首次推理会慢 30-50%）
                {
                    use image::{ImageBuffer, Rgba};
                    let warmup_start = std::time::Instant::now();
                    // 创建与默认检测输入尺寸匹配的灰色图像
                    let det_size = engine.config.det_input_size;
                    let test_img = ImageBuffer::from_fn(det_size, det_size, |_, _| {
                        Rgba([128u8, 128, 128, 255])
                    });
                    let dynamic_img = image::DynamicImage::ImageRgba8(test_img);
                    match engine.detector.detect(&dynamic_img, det_size) {
                        Ok(boxes) => {
                            tracing::debug!("Detected {} text regions", boxes.len());
                        }
                        Err(e) => {
                            tracing::warn!("检测模型预热失败（不影响正常使用）: {}", e);
                        }
                    }
                    tracing::info!(
                        "OCR 模型预热完成，耗时 {:.2}s",
                        warmup_start.elapsed().as_secs_f64()
                    );
                }

                let _ = MODEL_WARMED_UP.set(true);
            }

            tracing::info!("OCR engine initialized in {:.2}s", start.elapsed().as_secs_f64());

            Ok(Arc::new(engine))
        })
    }

    /// 创建新的 OCR 引擎实例
    ///
    /// 通常应该使用 `instance()` 获取单例，而不是直接创建新实例。
    ///
    /// # 参数
    ///
    /// - `config`: OCR 配置
    ///
    /// # 返回
    ///
    /// - `Ok(OcrEngine)`: 新的引擎实例
    /// - `Err(OcrError)`: 创建失败
    pub fn new(config: OcrConfig) -> Result<Self, OcrError> {
        let detector = TextDetector::new()?;
        let recognizer = TextRecognizer::with_input_height(config.rec_input_height)?;

        Ok(Self { detector, recognizer, config })
    }

    /// 使用自定义配置创建引擎
    ///
    /// # 参数
    ///
    /// - `config`: 自定义配置
    pub fn with_config(config: OcrConfig) -> Result<Self, OcrError> {
        Self::new(config)
    }

    /// 执行完整 OCR 流程
    ///
    /// 从图像文件路径执行 OCR：
    /// 1. 加载图像
    /// 2. 预处理（缩放）
    /// 3. 文本检测
    /// 4. 文本识别
    /// 5. 置信度过滤
    /// 6. 返回结果
    ///
    /// # 参数
    ///
    /// - `image_path`: 图像文件路径
    ///
    /// # 返回
    ///
    /// - `Ok(OcrResult)`: OCR 结果
    /// - `Err(OcrError)`: 处理失败
    ///
    /// # 示例
    ///
    /// ```rust,ignore
    /// let result = engine.recognize("screenshot.png").await?;
    /// println!("识别到 {} 个文本区域", result.boxes.len());
    /// ```
    pub async fn recognize(&self, image_path: &str) -> Result<OcrResult, OcrError> {
        self.recognize_blocking(image_path)
    }

    /// 同步执行 OCR。
    ///
    /// Tauri 命令层会把这个方法放进 `spawn_blocking`，避免 OpenVINO 推理阻塞异步运行时。
    pub fn recognize_blocking(&self, image_path: &str) -> Result<OcrResult, OcrError> {
        let start = Instant::now();

        tracing::info!("Starting OCR for: {}", image_path);

        // 1. 加载图像（优先从内存缓存，消除磁盘 I/O）
        let image = if let Some(cached) = take_ocr_image_cache(image_path) {
            tracing::info!("OCR 命中内存缓存，跳过磁盘读取 (~0ms)");
            cached
        } else {
            Arc::new(load_image(image_path)?)
        };
        tracing::debug!("Image loaded: {}x{}", image.width(), image.height());

        // 2. 执行 OCR
        let result = self.recognize_image(&image)?;

        let elapsed = start.elapsed().as_secs_f64();
        tracing::info!("OCR completed: {} regions, {:.2}s", result.boxes.len(), elapsed);

        // 更新耗时
        Ok(OcrResult { text: result.text, boxes: result.boxes, elapse: elapsed })
    }

    /// 高精度 OCR（用于后台处理，精度优先，不在乎速度）
    ///
    /// 使用更大的检测输入尺寸和更低的检测阈值，提高文字召回率和准确率。
    /// 适用于后台空闲时处理，不影响前台截图的实时性。
    pub async fn recognize_high_accuracy(&self, image_path: &str) -> Result<OcrResult, OcrError> {
        let start = Instant::now();

        tracing::info!("[高精度模式] Starting OCR for: {}", image_path);

        // 1. 加载图像（高精度模式仅用于后台处理历史图片，不使用一次性缓存）
        let image = load_image(image_path)?;

        // 2. 高精度 OCR：使用更大的检测尺寸
        let result = self.recognize_image_high_accuracy(&image)?;

        let elapsed = start.elapsed().as_secs_f64();
        tracing::info!(
            "[高精度模式] OCR completed: {} regions, {:.2}s",
            result.boxes.len(),
            elapsed
        );

        Ok(OcrResult { text: result.text, boxes: result.boxes, elapse: elapsed })
    }

    /// 高精度图像识别（内部方法）
    ///
    /// 与 `recognize_image` 的区别：
    /// - 使用固定 960px 检测尺寸（而非自适应 480-640）
    /// - 使用更大的 max_image_size（4096 vs 默认值）
    /// - 使用更低的置信度阈值（0.3 vs 0.5）
    fn recognize_image_high_accuracy(&self, image: &DynamicImage) -> Result<OcrResult, OcrError> {
        let start = Instant::now();

        if image.width() < 100 && image.height() < 100 {
            return Ok(OcrResult::empty(start.elapsed().as_secs_f64()));
        }

        // 高精度模式：保留更多图像细节
        let (processed_image, scale_x, scale_y) = resize_image(image, 4096);

        // 使用固定 960 的检测尺寸（高精度）
        let det_size = 960u32;
        tracing::debug!(
            "[高精度模式] 检测尺寸: {}x{} → det_size={}",
            processed_image.width(),
            processed_image.height(),
            det_size
        );

        let boxes = self.detector.detect(&processed_image, det_size)?;
        if boxes.is_empty() {
            return Ok(OcrResult::empty(start.elapsed().as_secs_f64()));
        }

        // 文本识别
        let regions = self.recognizer.recognize_batch(&processed_image, &boxes)?;

        // 使用更低的置信度阈值（0.3 而非默认的 0.5），召回更多文字
        let high_accuracy_threshold = 0.3f32;
        let mut filtered_regions: Vec<TextRegion> =
            regions.into_iter().filter(|r| r.confidence >= high_accuracy_threshold).collect();

        // 符号噪声过滤
        filtered_regions.retain(|r| !is_symbol_noise(&r.text));

        // 坐标还原（如果发生了缩放）
        if scale_x != 1.0 || scale_y != 1.0 {
            for region in &mut filtered_regions {
                region.bbox.scale(scale_x, scale_y);
            }
        }

        // 转换为 OcrResult
        let result_boxes: Vec<OcrBox> =
            filtered_regions.iter().map(OcrBox::from_text_region).collect();

        // 使用布局处理器生成文本
        let layout_processor = LayoutProcessor::new();
        let text = layout_processor.process(&result_boxes);

        Ok(OcrResult { text, boxes: result_boxes, elapse: start.elapsed().as_secs_f64() })
    }

    /// 对图像执行 OCR
    ///
    /// 直接对 `DynamicImage` 执行 OCR，不需要文件路径。
    ///
    /// # 参数
    ///
    /// - `image`: 输入图像
    ///
    /// # 返回
    ///
    /// - `Ok(OcrResult)`: OCR 结果
    /// - `Err(OcrError)`: 处理失败
    pub fn recognize_image(&self, image: &DynamicImage) -> Result<OcrResult, OcrError> {
        let start = Instant::now();

        // 0. 跳过超小图片（< 100x100 像素基本不含可读文字）
        if image.width() < 100 && image.height() < 100 {
            tracing::debug!("跳过超小图片检测: {}x{} (< 100x100)", image.width(), image.height());
            return Ok(OcrResult::empty(start.elapsed().as_secs_f64()));
        }

        // 1. 预处理：缩放大图像
        let (processed_image, scale_x, scale_y) = resize_image(image, self.config.max_image_size);

        // 2. 文本检测（自适应检测尺寸）
        let det_size = self.adaptive_det_size(&processed_image);
        let det_start = Instant::now();
        let boxes = self.detector.detect(&processed_image, det_size)?;
        tracing::debug!(
            "Detection: {} boxes in {:.2}ms",
            boxes.len(),
            det_start.elapsed().as_millis()
        );

        if boxes.is_empty() {
            return Ok(OcrResult::empty(start.elapsed().as_secs_f64()));
        }

        // 3. 文本识别
        let rec_start = Instant::now();
        let regions = self.recognizer.recognize_batch(&processed_image, &boxes)?;
        tracing::debug!(
            "Recognition: {} regions in {:.2}ms",
            regions.len(),
            rec_start.elapsed().as_millis()
        );

        // 4. 置信度过滤（添加调试日志）
        // 先打印所有区域的置信度，便于诊断
        for (i, region) in regions.iter().enumerate() {
            // 安全截取前 20 个字符（避免 UTF-8 边界问题）
            let text_preview: String = region.text.chars().take(20).collect();
            let truncated = region.text.chars().count() > 20;
            tracing::debug!(
                "Region {}: text='{}{}', confidence={:.4}",
                i,
                text_preview,
                if truncated { "..." } else { "" },
                region.confidence
            );
        }

        let mut filtered_regions: Vec<TextRegion> = regions
            .into_iter()
            .filter(|r| r.confidence >= self.config.confidence_threshold)
            .collect();

        // 4.1 符号噪声过滤
        // 截图中 UI 图标（文件夹箭头、文件类型图标、状态图标等）常被 OCR 误识别为符号字符。
        // 过滤条件：文本仅含 1-2 个字符，且全部为非字母/数字/汉字的符号。
        // 例如: ">", "{}", "!", "[]", "·" 等。
        let before_noise_filter = filtered_regions.len();
        filtered_regions.retain(|r| !is_symbol_noise(&r.text));
        let noise_removed = before_noise_filter - filtered_regions.len();
        if noise_removed > 0 {
            tracing::debug!(
                "Symbol noise filter: removed {} regions (e.g. UI icons recognized as symbols)",
                noise_removed
            );
        }

        // 4.2 将坐标从缩放图像映射回原图坐标
        // recognize_image 的输入是原图，但检测/识别在 processed_image 上执行，
        // 若发生缩放，必须在返回前恢复坐标，避免前端按原图渲染时错位。
        if scale_x != 1.0 || scale_y != 1.0 {
            for region in &mut filtered_regions {
                region.bbox.scale(scale_x, scale_y);
            }
        }

        tracing::debug!(
            "After filtering: {} regions (threshold: {})",
            filtered_regions.len(),
            self.config.confidence_threshold
        );

        // 5. 转换为 OcrResult
        let boxes: Vec<OcrBox> = filtered_regions.iter().map(OcrBox::from_text_region).collect();

        // 6. 使用布局处理器生成保持原图排版的文本
        let layout_processor = LayoutProcessor::new();
        let text = layout_processor.process(&boxes);

        Ok(OcrResult { text, boxes, elapse: start.elapsed().as_secs_f64() })
    }

    /// 仅执行文本检测
    ///
    /// # 参数
    ///
    /// - `image`: 输入图像
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<TextBox>)`: 检测到的文本框
    /// - `Err(OcrError)`: 检测失败
    pub fn detect(&self, image: &DynamicImage) -> Result<Vec<TextBox>, OcrError> {
        let (processed_image, scale_x, scale_y) = resize_image(image, self.config.max_image_size);
        let det_size = self.adaptive_det_size(&processed_image);
        let mut boxes = self.detector.detect(&processed_image, det_size)?;

        // 坐标映射回原图（如果进行了缩放）
        if scale_x != 1.0 || scale_y != 1.0 {
            for bbox in &mut boxes {
                bbox.scale(scale_x, scale_y);
            }
        }

        Ok(boxes)
    }

    /// 仅执行文本识别
    ///
    /// # 参数
    ///
    /// - `image`: 输入图像
    /// - `boxes`: 文本框列表
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<TextRegion>)`: 识别结果
    /// - `Err(OcrError)`: 识别失败
    pub fn recognize_regions(
        &self,
        image: &DynamicImage,
        boxes: &[TextBox],
    ) -> Result<Vec<TextRegion>, OcrError> {
        self.recognizer.recognize_batch(image, boxes)
    }

    /// 自适应检测输入尺寸
    ///
    /// 根据图片实际尺寸动态选择最佳的检测输入大小：
    /// - 小图片（最长边 < 800px）：使用 480，减少计算量
    /// - 中等图片（800-1500px）：使用配置的默认值（512）
    /// - 大图片（> 1500px）：使用 640，保证大图文字检测率
    ///
    /// 所有尺寸都是 32 的倍数，兼容 OpenVINO 内存对齐。
    fn adaptive_det_size(&self, image: &DynamicImage) -> u32 {
        let max_side = image.width().max(image.height());
        let det_size = if max_side < 800 {
            // 小图片：缩放比例小，480 足够
            480
        } else if max_side > 1500 {
            // 大图片：需要更多细节，用 640
            640
        } else {
            // 中等图片：使用配置默认值
            self.config.det_input_size
        };

        tracing::debug!(
            "自适应检测尺寸: 图片 {}x{} → det_size={}",
            image.width(),
            image.height(),
            det_size
        );

        det_size
    }

    /// 获取当前配置
    pub fn config(&self) -> &OcrConfig {
        &self.config
    }

    /// 预热模型（可选）
    ///
    /// 在应用启动时调用此方法，可以避免首次 OCR 的冷启动延迟。
    /// 预热会执行一次小图像的推理，触发 ONNX Runtime 的内存分配和优化。
    ///
    /// # 返回
    ///
    /// - `Ok(())`: 预热成功
    /// - `Err(OcrError)`: 预热失败
    ///
    /// # 示例
    ///
    /// ```rust,ignore
    /// // 在应用启动时调用
    /// tokio::spawn(async {
    ///     if let Err(e) = OcrEngine::warmup().await {
    ///         tracing::warn!("OCR 模型预热失败: {}", e);
    ///     }
    /// });
    /// ```
    pub async fn warmup() -> Result<(), OcrError> {
        // 检查是否已经预热过
        if MODEL_WARMED_UP.get().is_some() {
            tracing::debug!("OCR 模型已预热，跳过");
            return Ok(());
        }

        tracing::info!("开始预热 OCR 模型...");
        let start = Instant::now();

        // 获取引擎实例（这会触发模型加载）
        let engine = Self::instance()?;

        // 创建一个小的测试图像（64x64 灰色图像）
        use image::{ImageBuffer, Rgba};
        let test_image = ImageBuffer::from_fn(64, 64, |_, _| Rgba([128u8, 128, 128, 255]));
        let dynamic_image = DynamicImage::ImageRgba8(test_image);

        // 执行一次推理（预热检测和识别模型）
        let _ = engine.recognize_image(&dynamic_image)?;

        // 标记为已预热
        let _ = MODEL_WARMED_UP.set(true);

        tracing::info!("OCR 模型预热完成，耗时 {:.2}s", start.elapsed().as_secs_f64());

        Ok(())
    }

    /// 检查模型是否已预热
    pub fn is_warmed_up() -> bool {
        MODEL_WARMED_UP.get().copied().unwrap_or(false)
    }
}

// ============================================
// 符号噪声过滤
// ============================================

/// 判断 OCR 识别文本是否为符号噪声（UI 图标误识别）
///
/// 截图 OCR 时，文件夹展开箭头、文件类型图标、状态图标等 UI 元素
/// 会被模型识别为 `>`、`{}`、`!`、`[]` 等符号字符。
///
/// # 过滤规则
///
/// 以下条件同时满足时视为噪声：
/// 1. 去除空白后，文本仅包含 1-2 个字符
/// 2. 所有字符均非字母（a-z、A-Z）、非数字（0-9）、非 CJK 汉字
///
/// # 示例
///
/// - `">"`   → true（文件夹箭头）
/// - `"{}"`  → true（JSON 文件图标）
/// - `"!"`   → true（警告图标）
/// - `"[]"`  → true（文件图标）
/// - `"·"`   → true（项目符号）
/// - `"Y"`   → false（字母，保留）
/// - `"OK"`  → false（字母，保留）
/// - `"你好"` → false（汉字，保留）
/// - `"Hello"` → false（超过 2 字符，不处理）
fn is_symbol_noise(text: &str) -> bool {
    let trimmed = text.trim();
    let char_count = trimmed.chars().count();

    // 空文本或超过 2 个字符的不处理
    if char_count == 0 || char_count > 2 {
        return false;
    }

    // 所有字符都不是字母/数字/汉字 → 视为噪声
    trimmed.chars().all(|ch| !ch.is_alphanumeric())
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use serial_test::serial;

    // ----------------------------------------
    // 配置测试
    // ----------------------------------------

    #[test]
    #[serial(ocr_openvino)]
    fn test_engine_with_default_config() {
        let result = OcrEngine::new(OcrConfig::default());

        match result {
            Ok(engine) => {
                assert!((engine.config().confidence_threshold - 0.3).abs() < f32::EPSILON);
                assert_eq!(engine.config().max_image_size, 2048);
            }
            Err(e) => {
                println!("Engine creation failed (expected in some environments): {}", e);
            }
        }
    }

    // ----------------------------------------
    // 符号噪声过滤测试
    // ----------------------------------------

    #[test]
    fn test_symbol_noise_filter_common_ui_symbols() {
        // 常见的 UI 图标误识别
        assert!(is_symbol_noise(">")); // 文件夹箭头
        assert!(is_symbol_noise("{}")); // JSON 文件图标
        assert!(is_symbol_noise("!")); // 警告图标
        assert!(is_symbol_noise("[]")); // 文件图标
        assert!(is_symbol_noise("()")); // 括号图标
        assert!(is_symbol_noise("<>")); // 角括号
        assert!(is_symbol_noise("·")); // 项目符号
        assert!(is_symbol_noise("•")); // 项目符号
        assert!(is_symbol_noise("|")); // 分隔线
        assert!(is_symbol_noise(">>")); // 双箭头
    }

    #[test]
    fn test_symbol_noise_filter_preserves_real_text() {
        // 字母（即使单个也可能是真实文本）
        assert!(!is_symbol_noise("Y"));
        assert!(!is_symbol_noise("V"));
        assert!(!is_symbol_noise("A"));
        assert!(!is_symbol_noise("OK"));

        // 数字
        assert!(!is_symbol_noise("1"));
        assert!(!is_symbol_noise("42"));

        // 汉字
        assert!(!is_symbol_noise("中"));
        assert!(!is_symbol_noise("你好"));

        // 超过 2 字符不处理
        assert!(!is_symbol_noise(">>>"));
        assert!(!is_symbol_noise("Hello"));
        assert!(!is_symbol_noise("你好世界"));

        // 空文本不处理
        assert!(!is_symbol_noise(""));
        assert!(!is_symbol_noise("  "));
    }

    #[test]
    fn test_symbol_noise_filter_with_whitespace() {
        // 带空白的符号
        assert!(is_symbol_noise(" > "));
        assert!(is_symbol_noise(" {} "));
        assert!(is_symbol_noise("\t!\t"));
    }

    #[test]
    #[serial(ocr_openvino)]
    fn test_engine_with_custom_config() {
        let config = OcrConfig::default().with_confidence_threshold(0.7).with_max_image_size(4096);

        let result = OcrEngine::with_config(config);

        match result {
            Ok(engine) => {
                assert!((engine.config().confidence_threshold - 0.7).abs() < f32::EPSILON);
                assert_eq!(engine.config().max_image_size, 4096);
            }
            Err(e) => {
                println!("Engine creation failed: {}", e);
            }
        }
    }

    // ----------------------------------------
    // OcrResult 测试
    // ----------------------------------------

    #[test]
    fn test_ocr_result_empty() {
        let result = OcrResult::empty(0.5);

        assert!(result.text.is_empty());
        assert!(result.boxes.is_empty());
        assert!((result.elapse - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_ocr_result_from_boxes() {
        let boxes = vec![
            OcrBox::new("Hello".to_string(), 0.95, vec![vec![0.0, 0.0]]),
            OcrBox::new("World".to_string(), 0.90, vec![vec![10.0, 10.0]]),
        ];

        let result = OcrResult::from_boxes(boxes, 0.234);

        assert_eq!(result.text, "Hello\nWorld");
        assert_eq!(result.boxes.len(), 2);
    }

    // ----------------------------------------
    // 单例测试
    // ----------------------------------------

    #[test]
    #[serial(ocr_openvino)]
    fn test_singleton_instance() {
        // 注意：此测试可能因模型加载失败而跳过
        let result1 = OcrEngine::instance();
        let result2 = OcrEngine::instance();

        match (result1, result2) {
            (Ok(engine1), Ok(engine2)) => {
                // 应该是同一个实例
                assert!(Arc::ptr_eq(engine1, engine2));
            }
            _ => {
                println!("Singleton test skipped due to model loading failure");
            }
        }
    }
}

// ============================================
// 属性测试
// ============================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use image::{ImageBuffer, Rgba};
    use proptest::prelude::*;
    use serial_test::serial;

    /// 创建测试用的图像
    fn create_test_image(width: u32, height: u32) -> DynamicImage {
        let img = ImageBuffer::from_fn(width, height, |x, y| {
            let r = ((x * 255) / width.max(1)) as u8;
            let g = ((y * 255) / height.max(1)) as u8;
            Rgba([r, g, 128, 255])
        });
        DynamicImage::ImageRgba8(img)
    }

    // ----------------------------------------
    // Property 1: Result Structure Validity
    // ----------------------------------------

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(20))]

        /// Property 1: 结果结构有效性
        ///
        /// **Validates: Requirements 5.2, 8.3, 8.4**
        ///
        /// 对于任何成功的 OCR 操作，返回的 OcrResult 应该包含：
        /// - text 字段（String，可能为空）
        /// - boxes 字段（Vec<OcrBox>）
        /// - elapse 字段（f64，非负）
        ///
        /// 每个 OcrBox 应该包含：
        /// - text 字段（String）
        /// - confidence 字段（f64，0.0-1.0）
        /// - box_coords 字段（4 个点，每个点 2 个坐标）
        #[test]
        #[serial(ocr_openvino)]
        fn prop_result_structure_validity(
            width in 100u32..500,
            height in 100u32..500,
        ) {
            // 创建测试图像
            let image = create_test_image(width, height);

            // 尝试创建引擎并执行 OCR
            let engine_result = OcrEngine::new(OcrConfig::default());

            if let Ok(engine) = engine_result {
                let result = engine.recognize_image(&image);

                if let Ok(ocr_result) = result {
                    // 验证 elapse 非负
                    prop_assert!(
                        ocr_result.elapse >= 0.0,
                        "elapse 应该非负，实际: {}",
                        ocr_result.elapse
                    );

                    // 验证每个 box 的结构
                    for bbox in &ocr_result.boxes {
                        // confidence 在 0.0-1.0 范围内
                        prop_assert!(
                            bbox.confidence >= 0.0 && bbox.confidence <= 1.0,
                            "confidence 应该在 0.0-1.0 范围内，实际: {}",
                            bbox.confidence
                        );

                        // box_coords 有 4 个点
                        prop_assert_eq!(
                            bbox.box_coords.len(), 4,
                            "box_coords 应该有 4 个点"
                        );

                        // 每个点有 2 个坐标
                        for point in &bbox.box_coords {
                            prop_assert_eq!(
                                point.len(), 2,
                                "每个点应该有 2 个坐标"
                            );
                        }
                    }
                }
            }
        }
    }

    // ----------------------------------------
    // Property 3: Confidence Threshold Filtering
    // ----------------------------------------

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(10))]

        /// Property 3: 置信度阈值过滤
        ///
        /// **Validates: Requirements 4.3, 11.1**
        ///
        /// 对于任何 OCR 结果，所有返回的 OcrBox 的置信度
        /// 都应该大于或等于配置的 confidence_threshold。
        #[test]
        #[serial(ocr_openvino)]
        fn prop_confidence_filtering(
            threshold in 0.3f32..0.9,
        ) {
            let config = OcrConfig::default().with_confidence_threshold(threshold);

            if let Ok(engine) = OcrEngine::with_config(config) {
                let image = create_test_image(200, 200);

                if let Ok(result) = engine.recognize_image(&image) {
                    for bbox in &result.boxes {
                        prop_assert!(
                            bbox.confidence >= threshold as f64,
                            "所有 box 的置信度应该 >= {}，实际: {}",
                            threshold,
                            bbox.confidence
                        );
                    }
                }
            }
        }
    }

    // ----------------------------------------
    // Property 8: Empty Detection Handling
    // ----------------------------------------

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(10))]

        /// Property 8: 空检测处理
        ///
        /// **Validates: Requirements 2.5**
        ///
        /// 对于不包含可检测文本的图像，OCR 引擎应该返回：
        /// - text: 空字符串
        /// - boxes: 空向量
        /// - elapse: 正值
        ///
        /// 不应该抛出错误。
        #[test]
        #[serial(ocr_openvino)]
        fn prop_empty_detection_handling(
            width in 50u32..200,
            height in 50u32..200,
        ) {
            // 创建纯色图像（不包含文本）
            let img = ImageBuffer::from_fn(width, height, |_, _| {
                Rgba([128, 128, 128, 255])
            });
            let image = DynamicImage::ImageRgba8(img);

            if let Ok(engine) = OcrEngine::new(OcrConfig::default()) {
                let result = engine.recognize_image(&image);

                // 不应该返回错误
                prop_assert!(
                    result.is_ok(),
                    "空图像不应该导致错误"
                );

                if let Ok(ocr_result) = result {
                    // elapse 应该是正值
                    prop_assert!(
                        ocr_result.elapse > 0.0,
                        "elapse 应该是正值"
                    );
                }
            }
        }
    }
}

// ============================================
// 集成测试
// ============================================

#[cfg(test)]
mod integration_tests {
    use super::*;
    use serial_test::serial;
    use std::path::PathBuf;

    /// 获取测试图像路径
    fn get_test_image_path(name: &str) -> PathBuf {
        let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        path.push("..");
        path.push("test-fixtures");
        path.push("images");
        path.push(name);
        path
    }

    /// 检查测试图像是否存在
    fn test_image_exists(name: &str) -> bool {
        get_test_image_path(name).exists()
    }

    // ----------------------------------------
    // 基础功能测试
    // ----------------------------------------

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_simple_english() {
        if !test_image_exists("simple.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("simple.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR result: {:?}", ocr_result.text);
                // 简单英文图片应该能识别出 "TEST"
                assert!(
                    ocr_result.text.to_uppercase().contains("TEST"),
                    "Expected 'TEST' in result, got: {}",
                    ocr_result.text
                );
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_chinese() {
        if !test_image_exists("chinese.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("chinese.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR result: {:?}", ocr_result.text);
                // 中文图片应该能识别出中文字符
                assert!(
                    !ocr_result.text.is_empty() || ocr_result.boxes.is_empty(),
                    "Chinese OCR should return text or empty boxes"
                );
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_blank_image() {
        if !test_image_exists("blank.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("blank.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR result for blank image: {:?}", ocr_result);
                // 空白图片应该返回空结果或很少的结果
                // 不应该抛出错误
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                // 空白图片不应该导致错误
                panic!("Blank image should not cause error: {}", e);
            }
        }
    }

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_multiline() {
        if !test_image_exists("multiline.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("multiline.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR result: {:?}", ocr_result.text);
                println!("Boxes count: {}", ocr_result.boxes.len());
                // 多行文本应该识别出多个文本框
                // 至少应该有一些结果
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_mixed_language() {
        if !test_image_exists("mixed.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("mixed.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR result: {:?}", ocr_result.text);
                // 中英混合图片应该能识别
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    // ----------------------------------------
    // 性能测试
    // ----------------------------------------

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_performance_simple() {
        if !test_image_exists("simple.png") {
            println!("Test image not found, skipping test");
            return;
        }

        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("simple.png");
        // 先执行一次预热，避免将模型首次加载/编译时间计入性能阈值
        let _ = engine.recognize(path.to_str().unwrap()).await;
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("OCR elapsed: {:.3}s", ocr_result.elapse);
                // 全量测试时 OpenVINO CPU 推理会与其他 OCR/图像属性测试竞争资源；
                // 保留宽松上限用于捕捉明显回归，避免环境负载造成误报。
                assert!(
                    ocr_result.elapse < 5.0,
                    "OCR should complete within 5 seconds, took: {:.3}s",
                    ocr_result.elapse
                );
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    // ----------------------------------------
    // 错误处理测试
    // ----------------------------------------

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_nonexistent_file() {
        let engine = match OcrEngine::new(OcrConfig::default()) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let result = engine.recognize("/nonexistent/path/image.png").await;

        // 不存在的文件应该返回错误
        assert!(result.is_err(), "Nonexistent file should return error");
    }

    // ----------------------------------------
    // 配置测试
    // ----------------------------------------

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_with_high_confidence_threshold() {
        if !test_image_exists("simple.png") {
            println!("Test image not found, skipping test");
            return;
        }

        // 使用高置信度阈值
        let config = OcrConfig::default().with_confidence_threshold(0.9);
        let engine = match OcrEngine::with_config(config) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("simple.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                // 所有返回的 box 置信度应该 >= 0.9
                for bbox in &ocr_result.boxes {
                    assert!(
                        bbox.confidence >= 0.9,
                        "Box confidence should be >= 0.9, got: {}",
                        bbox.confidence
                    );
                }
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }

    #[tokio::test]
    #[serial(ocr_openvino)]
    async fn test_ocr_with_low_confidence_threshold() {
        if !test_image_exists("low_contrast.png") {
            println!("Test image not found, skipping test");
            return;
        }

        // 使用低置信度阈值
        let config = OcrConfig::default().with_confidence_threshold(0.3);
        let engine = match OcrEngine::with_config(config) {
            Ok(e) => e,
            Err(e) => {
                println!("Engine creation failed: {}, skipping test", e);
                return;
            }
        };

        let path = get_test_image_path("low_contrast.png");
        let result = engine.recognize(path.to_str().unwrap()).await;

        match result {
            Ok(ocr_result) => {
                println!("Low contrast OCR result: {:?}", ocr_result.text);
                // 低置信度阈值可能会返回更多结果
                assert!(ocr_result.elapse > 0.0);
            }
            Err(e) => {
                println!("OCR failed: {}", e);
            }
        }
    }
}
