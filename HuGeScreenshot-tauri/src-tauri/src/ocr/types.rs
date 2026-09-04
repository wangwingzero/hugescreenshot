//! OCR 数据类型定义
//!
//! 本模块定义了 OCR 功能所需的所有数据类型：
//!
//! - `OcrResult`: OCR 识别结果（与现有 Python sidecar 接口兼容）
//! - `OcrBox`: 文本区域（与现有接口兼容）
//! - `TextBox`: 内部使用的文本框
//! - `TextRegion`: 内部使用的文本区域
//! - `OcrError`: OCR 错误类型
//!
//! # Requirements
//!
//! - 8.3: OcrResult 结构体包含 text, boxes, elapse
//! - 8.4: OcrBox 结构体包含 text, confidence, box_coords
//! - 10.1: 文件不存在错误
//! - 10.2: 不支持的图像格式错误
//! - 10.3: 推理失败错误

use serde::{Deserialize, Serialize};
use thiserror::Error;

// ============================================
// 公开类型（与现有接口兼容）
// ============================================

/// OCR 识别结果
///
/// 与现有 Python sidecar OCR 接口完全兼容，用于 Tauri 命令返回。
///
/// # 字段
///
/// - `text`: 识别的全部文本，多个区域用换行符连接
/// - `boxes`: 文本区域列表，包含每个区域的详细信息
/// - `elapse`: 处理耗时（秒）
///
/// # 示例
///
/// ```rust
/// use hugescreenshot_tauri_lib::ocr::types::OcrResult;
///
/// let result = OcrResult {
///     text: "Hello\n你好".to_string(),
///     boxes: vec![],
///     elapse: 0.234,
/// };
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrResult {
    /// 识别的全部文本
    pub text: String,
    /// 文本区域列表
    pub boxes: Vec<OcrBox>,
    /// 处理耗时（秒）
    pub elapse: f64,
}

impl OcrResult {
    /// 创建空结果
    ///
    /// 用于图像中没有检测到文本的情况。
    ///
    /// # 参数
    ///
    /// - `elapse`: 处理耗时（秒）
    pub fn empty(elapse: f64) -> Self {
        Self { text: String::new(), boxes: Vec::new(), elapse }
    }

    /// 从文本区域列表创建结果
    ///
    /// 自动将所有区域的文本用换行符连接。
    ///
    /// # 参数
    ///
    /// - `boxes`: 文本区域列表
    /// - `elapse`: 处理耗时（秒）
    pub fn from_boxes(boxes: Vec<OcrBox>, elapse: f64) -> Self {
        let text = boxes.iter().map(|b| b.text.as_str()).collect::<Vec<_>>().join("\n");

        Self { text, boxes, elapse }
    }
}

/// 文本区域
///
/// 与现有 Python sidecar OCR 接口完全兼容。
///
/// # 字段
///
/// - `text`: 文本内容
/// - `confidence`: 置信度 (0.0 - 1.0)
/// - `box_coords`: 边界框坐标，格式为 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
///
/// # 坐标说明
///
/// 四个角点按顺时针排列：
/// - `[0]`: 左上角
/// - `[1]`: 右上角
/// - `[2]`: 右下角
/// - `[3]`: 左下角
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrBox {
    /// 文本内容
    pub text: String,
    /// 置信度 (0.0 - 1.0)
    pub confidence: f64,
    /// 边界框坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    #[serde(rename = "box_coords")]
    pub box_coords: Vec<Vec<f64>>,
}

impl OcrBox {
    /// 创建新的文本区域
    ///
    /// # 参数
    ///
    /// - `text`: 文本内容
    /// - `confidence`: 置信度 (0.0 - 1.0)
    /// - `box_coords`: 边界框坐标
    pub fn new(text: String, confidence: f64, box_coords: Vec<Vec<f64>>) -> Self {
        Self { text, confidence, box_coords }
    }

    /// 从内部 TextRegion 转换
    ///
    /// 将内部使用的 TextRegion 转换为公开的 OcrBox 格式。
    pub fn from_text_region(region: &TextRegion) -> Self {
        Self {
            text: region.text.clone(),
            confidence: region.confidence as f64,
            box_coords: region.bbox.to_coords(),
        }
    }
}

// ============================================
// 内部类型
// ============================================

/// 内部使用的文本框
///
/// 用于检测模型输出，存储四个角点坐标和检测置信度。
///
/// # 字段
///
/// - `points`: 四个角点坐标，格式为 [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
/// - `score`: 检测置信度 (0.0 - 1.0)
#[derive(Debug, Clone)]
pub struct TextBox {
    /// 四个角点坐标
    pub points: [[f32; 2]; 4],
    /// 检测置信度
    pub score: f32,
}

impl TextBox {
    /// 创建新的文本框
    ///
    /// # 参数
    ///
    /// - `points`: 四个角点坐标
    /// - `score`: 检测置信度
    pub fn new(points: [[f32; 2]; 4], score: f32) -> Self {
        Self { points, score }
    }

    /// 转换为坐标数组格式
    ///
    /// 将内部的 [[f32; 2]; 4] 格式转换为 Vec<Vec<f64>> 格式，
    /// 用于与前端接口兼容。
    pub fn to_coords(&self) -> Vec<Vec<f64>> {
        self.points.iter().map(|p| vec![p[0] as f64, p[1] as f64]).collect()
    }

    /// 获取边界矩形
    ///
    /// 返回包围四个角点的最小矩形 (x, y, width, height)。
    pub fn bounding_rect(&self) -> (f32, f32, f32, f32) {
        let min_x = self.points.iter().map(|p| p[0]).fold(f32::INFINITY, f32::min);
        let max_x = self.points.iter().map(|p| p[0]).fold(f32::NEG_INFINITY, f32::max);
        let min_y = self.points.iter().map(|p| p[1]).fold(f32::INFINITY, f32::min);
        let max_y = self.points.iter().map(|p| p[1]).fold(f32::NEG_INFINITY, f32::max);

        (min_x, min_y, max_x - min_x, max_y - min_y)
    }

    /// 获取中心点
    pub fn center(&self) -> (f32, f32) {
        let sum_x: f32 = self.points.iter().map(|p| p[0]).sum();
        let sum_y: f32 = self.points.iter().map(|p| p[1]).sum();
        (sum_x / 4.0, sum_y / 4.0)
    }

    /// 获取宽度（基于上边和下边的平均长度）
    pub fn width(&self) -> f32 {
        let top_width = ((self.points[1][0] - self.points[0][0]).powi(2)
            + (self.points[1][1] - self.points[0][1]).powi(2))
        .sqrt();
        let bottom_width = ((self.points[2][0] - self.points[3][0]).powi(2)
            + (self.points[2][1] - self.points[3][1]).powi(2))
        .sqrt();
        (top_width + bottom_width) / 2.0
    }

    /// 获取高度（基于左边和右边的平均长度）
    pub fn height(&self) -> f32 {
        let left_height = ((self.points[3][0] - self.points[0][0]).powi(2)
            + (self.points[3][1] - self.points[0][1]).powi(2))
        .sqrt();
        let right_height = ((self.points[2][0] - self.points[1][0]).powi(2)
            + (self.points[2][1] - self.points[1][1]).powi(2))
        .sqrt();
        (left_height + right_height) / 2.0
    }

    /// 缩放坐标
    ///
    /// 将坐标按指定比例缩放，用于将检测结果从缩放后的图像
    /// 映射回原始图像坐标系。
    ///
    /// # 参数
    ///
    /// - `scale_x`: X 方向缩放比例
    /// - `scale_y`: Y 方向缩放比例
    pub fn scale(&mut self, scale_x: f32, scale_y: f32) {
        for point in &mut self.points {
            point[0] *= scale_x;
            point[1] *= scale_y;
        }
    }

    /// 创建缩放后的副本
    ///
    /// 返回一个新的 TextBox，坐标按指定比例缩放。
    pub fn scaled(&self, scale_x: f32, scale_y: f32) -> Self {
        let mut new_box = self.clone();
        new_box.scale(scale_x, scale_y);
        new_box
    }
}

/// 内部使用的文本区域
///
/// 包含检测到的文本框和识别结果。
///
/// # 字段
///
/// - `bbox`: 边界框
/// - `text`: 识别文本
/// - `confidence`: 识别置信度
#[derive(Debug, Clone)]
pub struct TextRegion {
    /// 边界框
    pub bbox: TextBox,
    /// 识别文本
    pub text: String,
    /// 识别置信度
    pub confidence: f32,
}

impl TextRegion {
    /// 创建新的文本区域
    ///
    /// # 参数
    ///
    /// - `bbox`: 边界框
    /// - `text`: 识别文本
    /// - `confidence`: 识别置信度
    pub fn new(bbox: TextBox, text: String, confidence: f32) -> Self {
        Self { bbox, text, confidence }
    }

    /// 转换为 OcrBox
    ///
    /// 将内部 TextRegion 转换为公开的 OcrBox 格式。
    pub fn to_ocr_box(&self) -> OcrBox {
        OcrBox::from_text_region(self)
    }
}

// ============================================
// 错误类型
// ============================================

/// OCR 错误类型
///
/// 定义了 OCR 处理过程中可能发生的所有错误。
///
/// # 错误码映射
///
/// | 错误类型 | 错误码 | 说明 |
/// |----------|--------|------|
/// | FileNotFound | FILE_NOT_FOUND | 图像文件不存在 |
/// | UnsupportedFormat | UNSUPPORTED_FORMAT | 不支持的图像格式 |
/// | ModelLoadError | MODEL_LOAD_ERROR | 模型加载失败 |
/// | InferenceError | INFERENCE_ERROR | 推理失败 |
/// | ImageProcessError | IMAGE_PROCESS_ERROR | 图像处理失败 |
#[derive(Debug, Error)]
pub enum OcrError {
    /// 文件不存在
    ///
    /// 当指定的图像文件路径不存在时返回此错误。
    #[error("文件不存在: {0}")]
    FileNotFound(String),

    /// 不支持的图像格式
    ///
    /// 当图像格式不被支持时返回此错误。
    /// 支持的格式：PNG, JPEG, BMP, GIF, WEBP
    #[error("不支持的图像格式: {0}")]
    UnsupportedFormat(String),

    /// 模型加载失败
    ///
    /// 当 ONNX 模型加载失败时返回此错误。
    #[error("模型加载失败: {0}")]
    ModelLoadError(String),

    /// 推理失败
    ///
    /// 当 ONNX 推理执行失败时返回此错误。
    #[error("推理失败: {0}")]
    InferenceError(String),

    /// 图像处理失败
    ///
    /// 当图像预处理或后处理失败时返回此错误。
    #[error("图像处理失败: {0}")]
    ImageProcessError(String),
}

impl OcrError {
    /// 获取错误码
    ///
    /// 返回与错误类型对应的错误码字符串。
    pub fn code(&self) -> &'static str {
        match self {
            OcrError::FileNotFound(_) => "FILE_NOT_FOUND",
            OcrError::UnsupportedFormat(_) => "UNSUPPORTED_FORMAT",
            OcrError::ModelLoadError(_) => "MODEL_LOAD_ERROR",
            OcrError::InferenceError(_) => "INFERENCE_ERROR",
            OcrError::ImageProcessError(_) => "IMAGE_PROCESS_ERROR",
        }
    }
}

// ============================================
// 类型转换实现
// ============================================

impl From<Vec<TextRegion>> for OcrResult {
    /// 从 TextRegion 列表转换为 OcrResult
    ///
    /// 自动计算总文本和转换所有区域。
    fn from(regions: Vec<TextRegion>) -> Self {
        let boxes: Vec<OcrBox> = regions.iter().map(|r| r.to_ocr_box()).collect();
        let text = boxes.iter().map(|b| b.text.as_str()).collect::<Vec<_>>().join("\n");

        Self {
            text,
            boxes,
            elapse: 0.0, // 需要外部设置
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
        assert!((result.elapse - 0.234).abs() < f64::EPSILON);
    }

    #[test]
    fn test_ocr_result_serialization() {
        let result = OcrResult {
            text: "测试文本".to_string(),
            boxes: vec![OcrBox::new(
                "测试".to_string(),
                0.98,
                vec![vec![0.0, 0.0], vec![100.0, 0.0], vec![100.0, 50.0], vec![0.0, 50.0]],
            )],
            elapse: 0.123,
        };

        let json = serde_json::to_string(&result).unwrap();
        let deserialized: OcrResult = serde_json::from_str(&json).unwrap();

        assert_eq!(deserialized.text, result.text);
        assert_eq!(deserialized.boxes.len(), 1);
        assert_eq!(deserialized.boxes[0].text, "测试");
    }

    // ----------------------------------------
    // OcrBox 测试
    // ----------------------------------------

    #[test]
    fn test_ocr_box_new() {
        let box_coords = vec![vec![0.0, 0.0], vec![100.0, 0.0], vec![100.0, 50.0], vec![0.0, 50.0]];
        let ocr_box = OcrBox::new("Hello".to_string(), 0.95, box_coords.clone());

        assert_eq!(ocr_box.text, "Hello");
        assert!((ocr_box.confidence - 0.95).abs() < f64::EPSILON);
        assert_eq!(ocr_box.box_coords, box_coords);
    }

    #[test]
    fn test_ocr_box_from_text_region() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        let region = TextRegion::new(text_box, "测试".to_string(), 0.95);
        let ocr_box = OcrBox::from_text_region(&region);

        assert_eq!(ocr_box.text, "测试");
        // Use a larger epsilon for f32 -> f64 conversion precision
        assert!((ocr_box.confidence - 0.95).abs() < 1e-6);
        assert_eq!(ocr_box.box_coords.len(), 4);
    }

    // ----------------------------------------
    // TextBox 测试
    // ----------------------------------------

    #[test]
    fn test_text_box_new() {
        let points = [[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]];
        let text_box = TextBox::new(points, 0.9);

        assert_eq!(text_box.points, points);
        assert!((text_box.score - 0.9).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_box_to_coords() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        let coords = text_box.to_coords();

        assert_eq!(coords.len(), 4);
        assert_eq!(coords[0], vec![0.0, 0.0]);
        assert_eq!(coords[1], vec![100.0, 0.0]);
        assert_eq!(coords[2], vec![100.0, 50.0]);
        assert_eq!(coords[3], vec![0.0, 50.0]);
    }

    #[test]
    fn test_text_box_bounding_rect() {
        let text_box =
            TextBox::new([[10.0, 20.0], [110.0, 20.0], [110.0, 70.0], [10.0, 70.0]], 0.9);
        let (x, y, w, h) = text_box.bounding_rect();

        assert!((x - 10.0).abs() < f32::EPSILON);
        assert!((y - 20.0).abs() < f32::EPSILON);
        assert!((w - 100.0).abs() < f32::EPSILON);
        assert!((h - 50.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_box_center() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]], 0.9);
        let (cx, cy) = text_box.center();

        assert!((cx - 50.0).abs() < f32::EPSILON);
        assert!((cy - 50.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_box_width_height() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);

        assert!((text_box.width() - 100.0).abs() < f32::EPSILON);
        assert!((text_box.height() - 50.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_box_scale() {
        let mut text_box =
            TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        text_box.scale(2.0, 3.0);

        assert!((text_box.points[1][0] - 200.0).abs() < f32::EPSILON);
        assert!((text_box.points[2][1] - 150.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_box_scaled() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        let scaled = text_box.scaled(0.5, 0.5);

        // 原始不变
        assert!((text_box.points[1][0] - 100.0).abs() < f32::EPSILON);
        // 新的已缩放
        assert!((scaled.points[1][0] - 50.0).abs() < f32::EPSILON);
        assert!((scaled.points[2][1] - 25.0).abs() < f32::EPSILON);
    }

    // ----------------------------------------
    // TextRegion 测试
    // ----------------------------------------

    #[test]
    fn test_text_region_new() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        let region = TextRegion::new(text_box, "Hello".to_string(), 0.95);

        assert_eq!(region.text, "Hello");
        assert!((region.confidence - 0.95).abs() < f32::EPSILON);
    }

    #[test]
    fn test_text_region_to_ocr_box() {
        let text_box = TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9);
        let region = TextRegion::new(text_box, "测试".to_string(), 0.95);
        let ocr_box = region.to_ocr_box();

        assert_eq!(ocr_box.text, "测试");
        // Use a larger epsilon for f32 -> f64 conversion precision
        assert!((ocr_box.confidence - 0.95).abs() < 1e-6);
        assert_eq!(ocr_box.box_coords.len(), 4);
    }

    // ----------------------------------------
    // OcrError 测试
    // ----------------------------------------

    #[test]
    fn test_ocr_error_file_not_found() {
        let err = OcrError::FileNotFound("/path/to/file.png".to_string());
        assert_eq!(err.code(), "FILE_NOT_FOUND");
        assert!(err.to_string().contains("文件不存在"));
        assert!(err.to_string().contains("/path/to/file.png"));
    }

    #[test]
    fn test_ocr_error_unsupported_format() {
        let err = OcrError::UnsupportedFormat("tiff".to_string());
        assert_eq!(err.code(), "UNSUPPORTED_FORMAT");
        assert!(err.to_string().contains("不支持的图像格式"));
    }

    #[test]
    fn test_ocr_error_model_load_error() {
        let err = OcrError::ModelLoadError("模型文件损坏".to_string());
        assert_eq!(err.code(), "MODEL_LOAD_ERROR");
        assert!(err.to_string().contains("模型加载失败"));
    }

    #[test]
    fn test_ocr_error_inference_error() {
        let err = OcrError::InferenceError("内存不足".to_string());
        assert_eq!(err.code(), "INFERENCE_ERROR");
        assert!(err.to_string().contains("推理失败"));
    }

    #[test]
    fn test_ocr_error_image_process_error() {
        let err = OcrError::ImageProcessError("图像尺寸过大".to_string());
        assert_eq!(err.code(), "IMAGE_PROCESS_ERROR");
        assert!(err.to_string().contains("图像处理失败"));
    }

    // ----------------------------------------
    // 类型转换测试
    // ----------------------------------------

    #[test]
    fn test_vec_text_region_to_ocr_result() {
        let regions = vec![
            TextRegion::new(
                TextBox::new([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]], 0.9),
                "Hello".to_string(),
                0.95,
            ),
            TextRegion::new(
                TextBox::new([[0.0, 60.0], [100.0, 60.0], [100.0, 110.0], [0.0, 110.0]], 0.85),
                "World".to_string(),
                0.90,
            ),
        ];

        let result: OcrResult = regions.into();

        assert_eq!(result.text, "Hello\nWorld");
        assert_eq!(result.boxes.len(), 2);
        assert_eq!(result.boxes[0].text, "Hello");
        assert_eq!(result.boxes[1].text, "World");
    }
}
