//! OCR 模块 (Rust 原生实现)
//!
//! 使用 PP-OCRv4 模型 + OpenVINO 实现原生 OCR 功能。
//! 无需 Python sidecar，直接在 Rust 中进行文字识别。
//!
//! # 架构
//!
//! ```text
//! OcrEngine (单例)
//!     ├── TextDetector (PP-OCRv4 检测模型)
//!     │   └── DBPostProcessor (DB 后处理)
//!     └── TextRecognizer (PP-OCRv4 识别模型)
//!         └── CTC 解码
//! ```
//!
//! # 推理引擎
//!
//! 使用 Intel OpenVINO 作为推理引擎：
//! - Intel CPU 上比 ONNX Runtime 快 2-3 倍
//! - 支持直接加载 ONNX 模型（无需转换为 IR 格式）
//! - AMD CPU 也能运行（无加速但不会更慢）
//!
//! # 模块说明
//!
//! - `background_cache`: 后台 OCR 缓存管理器，在系统空闲时自动执行 OCR
//! - `config`: OCR 配置管理（置信度阈值、图像尺寸等）
//! - `detector`: 文本检测模块（PP-OCRv4 检测模型）
//! - `engine`: OCR 引擎核心（整合检测和识别，单例模式）
//! - `models`: PP-OCRv4 模型文件嵌入（检测模型、识别模型、字符字典）
//! - `openvino_engine`: OpenVINO 推理引擎封装
//! - `postprocessor`: DB 后处理算法（二值化、轮廓提取、边界框生成）
//! - `preprocessor`: 图像预处理（缩放、归一化、NCHW 格式转换）
//! - `recognizer`: 文本识别模块（PP-OCRv4 识别模型 + CTC 解码）
//! - `types`: OCR 数据类型定义（OcrResult、OcrBox、OcrError 等）
//!
//! # 使用示例
//!
//! ```rust,ignore
//! use crate::ocr::OcrEngine;
//!
//! // 获取 OCR 引擎单例
//! let engine = OcrEngine::instance()?;
//!
//! // 执行 OCR
//! let result = engine.recognize("screenshot.png").await?;
//! println!("识别文本: {}", result.text);
//! for bbox in &result.boxes {
//!     println!("区域: {} (置信度: {:.2})", bbox.text, bbox.confidence);
//! }
//! ```
//!
//! # 性能目标
//!
//! - A4 截图 (1920x1080): < 200ms (OpenVINO on Intel CPU)
//! - 4K 截图 (3840x2160): < 500ms
//! - 内存占用: < 200MB
//!
//! # 迁移说明
//!
//! 此模块替代了原来的 Python sidecar OCR 服务：
//! - 原实现: Python sidecar OCR (RapidOCR，已移除)
//! - 新实现: `src/ocr/` (PP-OCRv4 + OpenVINO)
//!
//! 优势：
//! - 无需 Python 运行时
//! - 更快的启动速度（Intel CPU 快 2-3 倍）
//! - 更低的内存占用
//! - 更好的错误处理

pub mod background_cache;
pub mod config;
pub mod detector;
pub mod engine;
pub mod layout;
pub mod models;
pub mod openvino_engine;
pub mod postprocessor;
pub mod preprocessor;
pub mod recognizer;
pub mod types;

// 重新导出常用类型
pub use background_cache::BackgroundOcrCache;
pub use config::OcrConfig;
pub use detector::TextDetector;
pub use engine::OcrEngine;
pub use layout::LayoutProcessor;
pub use openvino_engine::{get_openvino_info, InferenceSession};
pub use postprocessor::DBPostProcessor;
pub use preprocessor::{
    crop_text_region, load_image, preprocess_for_detection, preprocess_for_recognition,
    resize_image, MEAN, STD,
};
pub use recognizer::TextRecognizer;
pub use types::{OcrBox, OcrError, OcrResult, TextBox, TextRegion};
