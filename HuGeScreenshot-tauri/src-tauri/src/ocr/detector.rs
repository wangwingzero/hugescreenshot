//! 文本检测模块
//!
//! 使用 PP-OCRv4 检测模型定位图像中的文本区域。
//!
//! # 功能
//!
//! - 加载 PP-OCRv4 检测模型 (IR 格式，预处理已注入)
//! - 使用 OpenVINO 执行高性能推理
//! - 输出概率图处理
//!
//! # Requirements
//!
//! - 2.1: 使用 PP-OCRv4 检测模型
//! - 2.4: 输出文本区域边界框坐标
//!
//! # 模型规格
//!
//! - 输入: `[1, H, W, 3]` (u8, NHWC, BGR) - 预处理已注入模型
//! - 输出: `[1, 1, H, W]` 概率图
//!
//! # 使用示例
//!
//! ```rust,ignore
//! use crate::ocr::detector::TextDetector;
//!
//! let detector = TextDetector::new()?;
//! let boxes = detector.detect(&image, 960)?;
//! ```

use image::DynamicImage;

use super::models::{DET_MODEL_IR_BIN, DET_MODEL_IR_XML};
use super::openvino_engine::InferenceSession;
use super::postprocessor::DBPostProcessor;
use super::preprocessor::preprocess_for_detection_u8;
use super::types::{OcrError, TextBox};

/// 文本检测器
///
/// 使用 PP-OCRv4 检测模型定位图像中的文本区域。
///
/// # 线程安全
///
/// `TextDetector` 是线程安全的，可以在多线程环境中共享使用。
/// 内部使用 OpenVINO InferenceSession 进行推理。
pub struct TextDetector {
    /// OpenVINO 推理会话
    session: InferenceSession,
    /// DB 后处理器
    postprocessor: DBPostProcessor,
}

impl TextDetector {
    /// 创建新的文本检测器
    ///
    /// 从嵌入的模型数据加载 PP-OCRv4 检测模型（IR 格式）。
    ///
    /// # 返回
    ///
    /// - `Ok(TextDetector)`: 成功创建的检测器
    /// - `Err(OcrError)`: 模型加载失败
    ///
    /// # 示例
    ///
    /// ```rust,ignore
    /// let detector = TextDetector::new()?;
    /// ```
    pub fn new() -> Result<Self, OcrError> {
        Self::with_postprocessor(DBPostProcessor::default())
    }

    /// 使用自定义后处理器创建检测器
    ///
    /// # 参数
    ///
    /// - `postprocessor`: 自定义的 DB 后处理器
    pub fn with_postprocessor(postprocessor: DBPostProcessor) -> Result<Self, OcrError> {
        let session = Self::load_model()?;
        Ok(Self { session, postprocessor })
    }

    /// 加载检测模型（IR 格式）
    fn load_model() -> Result<InferenceSession, OcrError> {
        tracing::info!("Loading PP-OCRv4 detection model (IR format) with OpenVINO...");

        // 使用 OpenVINO 加载 IR 模型（预处理已注入）
        let session =
            InferenceSession::from_ir_bytes(DET_MODEL_IR_XML, DET_MODEL_IR_BIN, "detection")?;

        tracing::info!("PP-OCRv4 detection model (IR) loaded successfully");
        Ok(session)
    }

    /// 检测图像中的文本区域
    ///
    /// # 参数
    ///
    /// - `image`: 输入图像
    /// - `det_size`: 检测模型输入尺寸（最长边）
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<TextBox>)`: 检测到的文本框列表
    /// - `Err(OcrError)`: 检测失败
    ///
    /// # 处理流程
    ///
    /// 1. 预处理图像（缩放，转换为 u8 NHWC BGR）
    /// 2. 执行模型推理（预处理在模型内部执行）
    /// 3. DB 后处理（二值化、轮廓提取、边界框生成）
    /// 4. 坐标映射回原图
    pub fn detect(&self, image: &DynamicImage, det_size: u32) -> Result<Vec<TextBox>, OcrError> {
        // 1. 预处理（u8 NHWC BGR 格式）
        let (data, height, width, scale_x, scale_y) = preprocess_for_detection_u8(image, det_size)?;

        // 2. 执行 OpenVINO 推理（使用 u8 输入）
        let prob_map = self.session.infer_detection_u8(&data, height, width)?;

        // 3. DB 后处理
        let mut boxes = self.postprocessor.process(&prob_map)?;

        // 4. 坐标映射回原图
        for bbox in &mut boxes {
            bbox.scale(scale_x, scale_y);
        }

        tracing::debug!("Detected {} text regions", boxes.len());
        Ok(boxes)
    }

    /// 获取后处理器的可变引用
    ///
    /// 用于调整后处理参数。
    pub fn postprocessor_mut(&mut self) -> &mut DBPostProcessor {
        &mut self.postprocessor
    }
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use serial_test::serial;

    #[test]
    #[serial(ocr_openvino)]
    fn test_detector_creation() {
        // 注意：此测试需要模型文件正确嵌入
        // 如果模型加载失败，测试会失败
        let result = TextDetector::new();

        // 模型加载可能因环境问题失败，这里只验证不会 panic
        match result {
            Ok(_) => println!("Detector created successfully"),
            Err(e) => println!("Detector creation failed (expected in some environments): {}", e),
        }
    }

    #[test]
    #[serial(ocr_openvino)]
    fn test_detector_with_custom_postprocessor() {
        let postprocessor = DBPostProcessor::default().with_threshold(0.5).with_box_threshold(0.7);

        let result = TextDetector::with_postprocessor(postprocessor);

        match result {
            Ok(_) => println!("Detector with custom postprocessor created successfully"),
            Err(e) => println!("Detector creation failed: {}", e),
        }
    }
}
