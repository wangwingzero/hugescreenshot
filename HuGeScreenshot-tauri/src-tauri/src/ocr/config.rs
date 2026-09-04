//! OCR 配置管理
//!
//! 本模块定义了 OCR 引擎的配置选项：
//!
//! - `OcrConfig`: OCR 配置结构体
//!
//! # Requirements
//!
//! - 11.1: 可配置的置信度阈值（默认 0.5）
//! - 11.2: 可配置的最大图像尺寸（默认 2048）
//!
//! # 示例
//!
//! ```rust
//! use hugescreenshot_tauri_lib::ocr::OcrConfig;
//!
//! // 使用默认配置
//! let config = OcrConfig::default();
//!
//! // 使用 builder 模式自定义配置
//! let config = OcrConfig::default()
//!     .with_confidence_threshold(0.7)
//!     .with_max_image_size(4096);
//! ```

/// OCR 配置
///
/// 定义了 OCR 引擎的各项配置参数。PP-OCRv4 移除了独立的方向分类模型，
/// 因此不再需要 `enable_cls` 配置项。
///
/// # 字段
///
/// - `confidence_threshold`: 置信度阈值，低于此值的识别结果将被过滤
/// - `max_image_size`: 最大图像尺寸，超过此尺寸的图像将被等比例缩放
/// - `det_input_size`: 检测模型输入尺寸
/// - `rec_input_height`: 识别模型输入高度
///
/// # 默认值
///
/// | 参数 | 默认值 | 说明 |
/// |------|--------|------|
/// | confidence_threshold | 0.3 | 过滤低置信度结果（宁可多识别，不要漏检） |
/// | max_image_size | 2048 | 防止内存溢出 |
/// | det_input_size | 512 | 截图场景优化（960→640→512） |
/// | rec_input_height | 48 | PP-OCRv4 标准高度 |
#[derive(Debug, Clone)]
pub struct OcrConfig {
    /// 置信度阈值（默认 0.5）
    ///
    /// 识别结果的置信度低于此阈值时将被过滤。
    /// 有效范围：0.0 - 1.0
    pub confidence_threshold: f32,

    /// 最大图像尺寸（默认 2048）
    ///
    /// 当图像的最长边超过此值时，将等比例缩放图像。
    /// 这有助于控制内存使用和处理时间。
    pub max_image_size: u32,

    /// 检测模型输入尺寸（默认 960）
    ///
    /// 检测模型的输入图像尺寸，必须是 32 的倍数。
    /// PP-OCR 推荐使用 960。
    pub det_input_size: u32,

    /// 识别模型输入高度（默认 48）
    ///
    /// 识别模型的输入图像高度。
    /// PP-OCRv4 使用 48 作为标准高度。
    pub rec_input_height: u32,
}

impl Default for OcrConfig {
    /// 创建默认配置
    ///
    /// 默认值：
    /// - confidence_threshold: 0.3（从 0.5 降低，减少文字缺失）
    /// - max_image_size: 2048
    /// - det_input_size: 512（从 640 进一步降低以提升速度）
    /// - rec_input_height: 48
    ///
    /// # 性能说明
    ///
    /// det_input_size 优化历程：
    /// - 960 → 640: 速度提升约 2.25 倍
    /// - 640 → 512: 像素量减少 36%，检测速度再提升 30-40%
    ///
    /// 对于截图 OCR 场景（文字清晰、对比度高），512 足够保证识别精度。
    /// 512 是 32 的倍数，能利用 OpenVINO 的内存对齐优化。
    ///
    /// # 准确性说明
    ///
    /// confidence_threshold 从 0.5 降到 0.3，宁可多识别一些低置信度结果，
    /// 也不要漏掉文字。用户可以接受少量 OCR 错误，但不能接受文字缺失。
    fn default() -> Self {
        Self {
            confidence_threshold: 0.3,
            max_image_size: 2048,
            det_input_size: 512, // 从 640 进一步降低到 512，检测速度再提升 30-40%
            rec_input_height: 48,
        }
    }
}

impl OcrConfig {
    /// 创建新的配置实例
    ///
    /// 使用指定的参数创建配置。如果只需要修改部分参数，
    /// 建议使用 `Default::default()` 配合 builder 方法。
    ///
    /// # 参数
    ///
    /// - `confidence_threshold`: 置信度阈值 (0.0 - 1.0)
    /// - `max_image_size`: 最大图像尺寸
    /// - `det_input_size`: 检测模型输入尺寸
    /// - `rec_input_height`: 识别模型输入高度
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::new(0.6, 4096, 960, 48);
    /// ```
    pub fn new(
        confidence_threshold: f32,
        max_image_size: u32,
        det_input_size: u32,
        rec_input_height: u32,
    ) -> Self {
        Self { confidence_threshold, max_image_size, det_input_size, rec_input_height }
    }

    /// 设置置信度阈值（Builder 模式）
    ///
    /// # 参数
    ///
    /// - `threshold`: 置信度阈值 (0.0 - 1.0)
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::default().with_confidence_threshold(0.7);
    /// ```
    ///
    /// # 注意
    ///
    /// 阈值会被限制在 0.0 - 1.0 范围内。
    pub fn with_confidence_threshold(mut self, threshold: f32) -> Self {
        self.confidence_threshold = threshold.clamp(0.0, 1.0);
        self
    }

    /// 设置最大图像尺寸（Builder 模式）
    ///
    /// # 参数
    ///
    /// - `size`: 最大图像尺寸（像素）
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::default().with_max_image_size(4096);
    /// ```
    ///
    /// # 注意
    ///
    /// 尺寸会被限制在 256 - 8192 范围内。
    pub fn with_max_image_size(mut self, size: u32) -> Self {
        self.max_image_size = size.clamp(256, 8192);
        self
    }

    /// 设置检测模型输入尺寸（Builder 模式）
    ///
    /// # 参数
    ///
    /// - `size`: 检测模型输入尺寸（像素），必须是 32 的倍数
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::default().with_det_input_size(1280);
    /// ```
    ///
    /// # 注意
    ///
    /// 尺寸会被调整为最接近的 32 的倍数，并限制在 320 - 2560 范围内。
    pub fn with_det_input_size(mut self, size: u32) -> Self {
        // 调整为 32 的倍数
        let adjusted = ((size + 16) / 32) * 32;
        self.det_input_size = adjusted.clamp(320, 2560);
        self
    }

    /// 设置识别模型输入高度（Builder 模式）
    ///
    /// # 参数
    ///
    /// - `height`: 识别模型输入高度（像素）
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::default().with_rec_input_height(32);
    /// ```
    ///
    /// # 注意
    ///
    /// 高度会被限制在 32 - 64 范围内。PP-OCRv4 推荐使用 48。
    pub fn with_rec_input_height(mut self, height: u32) -> Self {
        self.rec_input_height = height.clamp(32, 64);
        self
    }

    /// 验证配置是否有效
    ///
    /// 检查所有配置参数是否在有效范围内。
    ///
    /// # 返回
    ///
    /// - `Ok(())`: 配置有效
    /// - `Err(String)`: 配置无效，返回错误描述
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::default();
    /// assert!(config.validate().is_ok());
    /// ```
    pub fn validate(&self) -> Result<(), String> {
        if self.confidence_threshold < 0.0 || self.confidence_threshold > 1.0 {
            return Err(format!(
                "置信度阈值必须在 0.0 - 1.0 之间，当前值: {}",
                self.confidence_threshold
            ));
        }

        if self.max_image_size < 256 || self.max_image_size > 8192 {
            return Err(format!(
                "最大图像尺寸必须在 256 - 8192 之间，当前值: {}",
                self.max_image_size
            ));
        }

        if self.det_input_size < 320 || self.det_input_size > 2560 {
            return Err(format!(
                "检测模型输入尺寸必须在 320 - 2560 之间，当前值: {}",
                self.det_input_size
            ));
        }

        if !self.det_input_size.is_multiple_of(32) {
            return Err(format!(
                "检测模型输入尺寸必须是 32 的倍数，当前值: {}",
                self.det_input_size
            ));
        }

        if self.rec_input_height < 32 || self.rec_input_height > 64 {
            return Err(format!(
                "识别模型输入高度必须在 32 - 64 之间，当前值: {}",
                self.rec_input_height
            ));
        }

        Ok(())
    }

    /// 获取用于高精度模式的配置
    ///
    /// 返回一个优化了精度的配置：
    /// - 更高的置信度阈值 (0.7)
    /// - 更大的检测输入尺寸 (1280)
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::high_accuracy();
    /// assert_eq!(config.confidence_threshold, 0.7);
    /// ```
    pub fn high_accuracy() -> Self {
        Self {
            confidence_threshold: 0.7,
            max_image_size: 4096,
            det_input_size: 1280,
            rec_input_height: 48,
        }
    }

    /// 获取用于高速模式的配置
    ///
    /// 返回一个优化了速度的配置：
    /// - 较低的置信度阈值 (0.3)
    /// - 较小的检测输入尺寸 (480)
    /// - 较小的最大图像尺寸 (1024)
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::high_speed();
    /// assert_eq!(config.det_input_size, 480);
    /// ```
    pub fn high_speed() -> Self {
        Self {
            confidence_threshold: 0.3,
            max_image_size: 1024,
            det_input_size: 480,
            rec_input_height: 48,
        }
    }

    /// 获取用于截图场景的优化配置
    ///
    /// 针对截图 OCR 场景优化，平衡速度和精度：
    /// - 适中的置信度阈值 (0.3)
    /// - 检测输入尺寸 (512)
    /// - 适中的最大图像尺寸 (1920)
    ///
    /// # 性能说明
    ///
    /// 此配置配合优化后的后处理参数，可以：
    /// - 减少检测到的区域数量（过滤低置信度和小面积区域）
    /// - 每减少一个区域，节省约 70ms 识别时间
    /// - 目标：A4 截图 (1920x1080) OCR 时间 < 2s
    ///
    /// # 示例
    ///
    /// ```rust
    /// # use hugescreenshot_tauri_lib::ocr::OcrConfig;
    /// let config = OcrConfig::screenshot_optimized();
    /// ```
    pub fn screenshot_optimized() -> Self {
        Self {
            confidence_threshold: 0.3, // 宁可多识别，不要漏检
            max_image_size: 1920,
            det_input_size: 512,
            rec_input_height: 48,
        }
    }
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;

    // ----------------------------------------
    // Default 测试
    // ----------------------------------------

    #[test]
    fn test_default_config() {
        let config = OcrConfig::default();

        assert!((config.confidence_threshold - 0.3).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 2048);
        assert_eq!(config.det_input_size, 512); // 从 960→640→512 以提升速度
        assert_eq!(config.rec_input_height, 48);
    }

    #[test]
    fn test_default_config_is_valid() {
        let config = OcrConfig::default();
        assert!(config.validate().is_ok());
    }

    // ----------------------------------------
    // new() 测试
    // ----------------------------------------

    #[test]
    fn test_new_config() {
        let config = OcrConfig::new(0.6, 4096, 1280, 32);

        assert!((config.confidence_threshold - 0.6).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 4096);
        assert_eq!(config.det_input_size, 1280);
        assert_eq!(config.rec_input_height, 32);
    }

    // ----------------------------------------
    // Builder 模式测试
    // ----------------------------------------

    #[test]
    fn test_with_confidence_threshold() {
        let config = OcrConfig::default().with_confidence_threshold(0.8);
        assert!((config.confidence_threshold - 0.8).abs() < f32::EPSILON);
    }

    #[test]
    fn test_with_confidence_threshold_clamped() {
        // 测试下限
        let config = OcrConfig::default().with_confidence_threshold(-0.5);
        assert!((config.confidence_threshold - 0.0).abs() < f32::EPSILON);

        // 测试上限
        let config = OcrConfig::default().with_confidence_threshold(1.5);
        assert!((config.confidence_threshold - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_with_max_image_size() {
        let config = OcrConfig::default().with_max_image_size(4096);
        assert_eq!(config.max_image_size, 4096);
    }

    #[test]
    fn test_with_max_image_size_clamped() {
        // 测试下限
        let config = OcrConfig::default().with_max_image_size(100);
        assert_eq!(config.max_image_size, 256);

        // 测试上限
        let config = OcrConfig::default().with_max_image_size(10000);
        assert_eq!(config.max_image_size, 8192);
    }

    #[test]
    fn test_with_det_input_size() {
        let config = OcrConfig::default().with_det_input_size(1280);
        assert_eq!(config.det_input_size, 1280);
    }

    #[test]
    fn test_with_det_input_size_adjusted_to_multiple_of_32() {
        // 950 应该调整为 960 (最接近的 32 的倍数)
        let config = OcrConfig::default().with_det_input_size(950);
        assert_eq!(config.det_input_size, 960);

        // 970 应该调整为 960
        let config = OcrConfig::default().with_det_input_size(970);
        assert_eq!(config.det_input_size, 960);

        // 980 应该调整为 992
        let config = OcrConfig::default().with_det_input_size(980);
        assert_eq!(config.det_input_size, 992);
    }

    #[test]
    fn test_with_det_input_size_clamped() {
        // 测试下限
        let config = OcrConfig::default().with_det_input_size(100);
        assert_eq!(config.det_input_size, 320);

        // 测试上限
        let config = OcrConfig::default().with_det_input_size(5000);
        assert_eq!(config.det_input_size, 2560);
    }

    #[test]
    fn test_with_rec_input_height() {
        let config = OcrConfig::default().with_rec_input_height(32);
        assert_eq!(config.rec_input_height, 32);
    }

    #[test]
    fn test_with_rec_input_height_clamped() {
        // 测试下限
        let config = OcrConfig::default().with_rec_input_height(16);
        assert_eq!(config.rec_input_height, 32);

        // 测试上限
        let config = OcrConfig::default().with_rec_input_height(128);
        assert_eq!(config.rec_input_height, 64);
    }

    #[test]
    fn test_builder_chain() {
        let config = OcrConfig::default()
            .with_confidence_threshold(0.7)
            .with_max_image_size(4096)
            .with_det_input_size(1280)
            .with_rec_input_height(32);

        assert!((config.confidence_threshold - 0.7).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 4096);
        assert_eq!(config.det_input_size, 1280);
        assert_eq!(config.rec_input_height, 32);
    }

    // ----------------------------------------
    // validate() 测试
    // ----------------------------------------

    #[test]
    fn test_validate_valid_config() {
        let config = OcrConfig::default();
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_validate_invalid_confidence_threshold() {
        // 使用 new() 绕过 builder 的 clamp
        let config = OcrConfig::new(-0.1, 2048, 960, 48);
        assert!(config.validate().is_err());

        let config = OcrConfig::new(1.1, 2048, 960, 48);
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_validate_invalid_max_image_size() {
        let config = OcrConfig::new(0.5, 100, 960, 48);
        assert!(config.validate().is_err());

        let config = OcrConfig::new(0.5, 10000, 960, 48);
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_validate_invalid_det_input_size() {
        // 太小
        let config = OcrConfig::new(0.5, 2048, 100, 48);
        assert!(config.validate().is_err());

        // 太大
        let config = OcrConfig::new(0.5, 2048, 5000, 48);
        assert!(config.validate().is_err());

        // 不是 32 的倍数
        let config = OcrConfig::new(0.5, 2048, 950, 48);
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_validate_invalid_rec_input_height() {
        let config = OcrConfig::new(0.5, 2048, 960, 16);
        assert!(config.validate().is_err());

        let config = OcrConfig::new(0.5, 2048, 960, 128);
        assert!(config.validate().is_err());
    }

    // ----------------------------------------
    // 预设配置测试
    // ----------------------------------------

    #[test]
    fn test_high_accuracy_config() {
        let config = OcrConfig::high_accuracy();

        assert!((config.confidence_threshold - 0.7).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 4096);
        assert_eq!(config.det_input_size, 1280);
        assert_eq!(config.rec_input_height, 48);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_high_speed_config() {
        let config = OcrConfig::high_speed();

        assert!((config.confidence_threshold - 0.3).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 1024);
        assert_eq!(config.det_input_size, 480);
        assert_eq!(config.rec_input_height, 48);
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_screenshot_optimized_config() {
        let config = OcrConfig::screenshot_optimized();

        assert!((config.confidence_threshold - 0.3).abs() < f32::EPSILON);
        assert_eq!(config.max_image_size, 1920);
        assert_eq!(config.det_input_size, 512);
        assert_eq!(config.rec_input_height, 48);
        assert!(config.validate().is_ok());
    }

    // ----------------------------------------
    // Clone 和 Debug 测试
    // ----------------------------------------

    #[test]
    fn test_config_clone() {
        let config = OcrConfig::default().with_confidence_threshold(0.8);
        let cloned = config.clone();

        assert!((cloned.confidence_threshold - 0.8).abs() < f32::EPSILON);
        assert_eq!(cloned.max_image_size, config.max_image_size);
    }

    #[test]
    fn test_config_debug() {
        let config = OcrConfig::default();
        let debug_str = format!("{:?}", config);

        assert!(debug_str.contains("OcrConfig"));
        assert!(debug_str.contains("confidence_threshold"));
        assert!(debug_str.contains("max_image_size"));
    }
}
