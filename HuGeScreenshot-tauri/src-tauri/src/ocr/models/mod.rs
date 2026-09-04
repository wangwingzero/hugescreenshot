//! PP-OCRv4 模型文件嵌入
//!
//! 使用 `include_bytes!` 和 `include_str!` 宏将模型和字符字典
//! 嵌入到二进制文件中，实现无外部依赖的 OCR 功能。
//!
//! ## 模型来源
//!
//! 模型文件来自 [RapidOCR](https://github.com/RapidAI/RapidOCR) 项目
//!
//! ## PP-OCRv4 特性
//!
//! - PP-OCRv4 相比 v3 有更好的识别精度
//! - 识别模型输出 6625 个字符类别，与标准字典匹配
//! - 仅需要检测模型 (det) 和识别模型 (rec)
//!
//! ## 模型格式
//!
//! 使用 OpenVINO IR 格式（预处理已注入模型）：
//! - **INT8 量化** (默认): 速度快 ~1.9x，适合日常使用
//! - **FP16 preprocessed**: 精度更高（94% vs 90%），速度较慢
//!
//! ## IR 模型优化
//!
//! 使用 `convert_models.py` 脚本生成的 IR 模型包含预处理逻辑：
//! - 输入类型: `u8` (原始像素值 0-255)
//! - 输入布局: `NHWC` (Height, Width, Channel)
//! - 预处理已内置: BGR->RGB 转换、归一化 (x/127.5-1.0)
//!
//! ## 混合精度策略
//!
//! 采用混合精度策略，兼顾速度和精度：
//! - **检测模型**: INT8 量化（速度快 ~1.9x，检测精度足够）
//! - **识别模型**: preprocessed/FP16（精度优先，避免字符丢失）
//!
//! ## 文件大小
//!
//! | 文件 | 精度 | 大小 |
//! |------|------|------|
//! | det INT8 .bin | INT8 | ~1.2 MB |
//! | rec preprocessed .bin | FP16 | ~2.7 MB |
//! | ppocr_keys_v1.txt | - | ~33 KB |

// ============================================
// IR 模型（预处理优化，推荐使用）
// ============================================

/// 检测模型 (PP-OCRv4) - IR 格式（预处理已注入）
///
/// 预处理已内置到模型中，Rust 代码只需传入原始 u8 数据。
///
/// ## 模型规格
///
/// - 输入: `[1, H, W, 3]` (u8, NHWC, 原始像素值 0-255, BGR)
/// - 输出: `[1, 1, H, W]` 概率图
/// - 预处理: BGR->RGB, 归一化 (x/127.5-1.0)
///
/// ## 使用方式
///
/// ```rust,ignore
/// use crate::ocr::openvino_engine::InferenceSession;
/// use crate::ocr::models::{DET_MODEL_IR_XML, DET_MODEL_IR_BIN};
///
/// let session = InferenceSession::from_ir_bytes(DET_MODEL_IR_XML, DET_MODEL_IR_BIN, "detection")?;
/// ```
/// 检测模型：始终使用 INT8 量化（速度快 ~1.9x，检测精度足够）
///
/// 检测模型只需要定位文字位置，对精度要求较低。
/// INT8 量化在检测阶段几乎无精度损失，但速度提升显著。
pub const DET_MODEL_IR_XML: &[u8] = include_bytes!("ch_PP-OCRv4_det_int8.xml");
pub const DET_MODEL_IR_BIN: &[u8] = include_bytes!("ch_PP-OCRv4_det_int8.bin");

/// 识别模型 (PP-OCRv4) - IR 格式（预处理已注入）
///
/// 预处理已内置到模型中，Rust 代码只需传入原始 u8 数据。
///
/// ## 模型规格
///
/// - 输入: `[N, 48, W, 3]` (u8, NHWC, 原始像素值 0-255, BGR)
/// - 输出: `[N, T, 6625]` 字符概率分布
/// - 预处理: BGR->RGB, 归一化 (x/127.5-1.0)
///
/// ## 使用方式
///
/// ```rust,ignore
/// use crate::ocr::openvino_engine::InferenceSession;
/// use crate::ocr::models::{REC_MODEL_IR_XML, REC_MODEL_IR_BIN};
///
/// let session = InferenceSession::from_ir_bytes(REC_MODEL_IR_XML, REC_MODEL_IR_BIN, "recognition")?;
/// ```
/// 识别模型：始终使用 preprocessed/FP16（精度优先）
///
/// 识别模型需要精确读出每个字符，对精度要求极高。
/// INT8 量化会导致每个词丢失 1-3 个字符，严重影响识别质量。
/// 使用 preprocessed (FP16) 模型确保 94% 置信度。
pub const REC_MODEL_IR_XML: &[u8] = include_bytes!("ch_PP-OCRv4_rec_preprocessed.xml");
pub const REC_MODEL_IR_BIN: &[u8] = include_bytes!("ch_PP-OCRv4_rec_preprocessed.bin");

/// 字符字典 (v1)
///
/// 包含识别模型支持的所有字符，用于将模型输出的索引转换为实际字符。
/// PP-OCRv4 模型使用 v1 字典，包含 6623 个字符。
///
/// ## 字符范围
///
/// - 中文常用字（简体）
/// - 英文字母（大小写）
/// - 数字 (0-9)
/// - 常用标点符号
/// - 特殊符号
///
/// ## 使用方式
///
/// ```rust,ignore
/// use crate::ocr::models::CHAR_DICT;
///
/// let chars: Vec<&str> = CHAR_DICT.lines().collect();
/// // 索引 0 通常是空白/填充字符
/// let recognized_char = chars[predicted_index];
/// ```
pub const CHAR_DICT: &str = include_str!("ppocr_keys_v1.txt");

#[cfg(test)]
mod tests {
    use super::*;

    /// 验证检测模型 IR 格式已正确嵌入
    #[test]
    fn test_det_model_ir_embedded() {
        // 检查 XML 模型数据不为空
        assert!(!DET_MODEL_IR_XML.is_empty(), "检测模型 XML 数据不应为空");
        assert!(!DET_MODEL_IR_BIN.is_empty(), "检测模型 BIN 数据不应为空");

        // 检查 XML 文件以 <?xml 开头
        let xml_header = std::str::from_utf8(&DET_MODEL_IR_XML[..5]).unwrap_or("");
        assert!(xml_header == "<?xml", "检测模型 XML 应以 <?xml 开头，实际: {:?}", xml_header);

        // PP-OCRv4 检测模型 IR 格式：
        // - preprocessed (FP16 压缩): ~1.2MB
        // - INT8 量化: ~1.2MB
        assert!(
            DET_MODEL_IR_BIN.len() > 500_000 && DET_MODEL_IR_BIN.len() < 5_000_000,
            "检测模型 BIN 大小应在 0.5-5MB 范围内，实际: {} bytes",
            DET_MODEL_IR_BIN.len()
        );
    }

    /// 验证识别模型 IR 格式已正确嵌入
    #[test]
    fn test_rec_model_ir_embedded() {
        // 检查 XML 模型数据不为空
        assert!(!REC_MODEL_IR_XML.is_empty(), "识别模型 XML 数据不应为空");
        assert!(!REC_MODEL_IR_BIN.is_empty(), "识别模型 BIN 数据不应为空");

        // 检查 XML 文件以 <?xml 开头
        let xml_header = std::str::from_utf8(&REC_MODEL_IR_XML[..5]).unwrap_or("");
        assert!(xml_header == "<?xml", "识别模型 XML 应以 <?xml 开头，实际: {:?}", xml_header);

        // PP-OCRv4 识别模型 IR 格式：
        // - preprocessed (FP16 压缩): ~2.7MB
        // - INT8 量化: ~2.7MB
        assert!(
            REC_MODEL_IR_BIN.len() > 1_000_000 && REC_MODEL_IR_BIN.len() < 8_000_000,
            "识别模型 BIN 大小应在 1-8MB 范围内，实际: {} bytes",
            REC_MODEL_IR_BIN.len()
        );
    }

    /// 验证字符字典已正确嵌入
    #[test]
    fn test_char_dict_embedded() {
        // 检查字典不为空
        assert!(!CHAR_DICT.is_empty(), "字符字典不应为空");

        // 检查字典行数（PP-OCRv4 字典通常有 6000+ 个字符）
        let line_count = CHAR_DICT.lines().count();
        assert!(line_count > 1000, "字符字典应包含超过 1000 个字符，实际: {} 行", line_count);

        // 检查是否包含基本字符
        let chars: Vec<&str> = CHAR_DICT.lines().collect();

        // 检查是否包含数字
        assert!(chars.contains(&"0"), "字符字典应包含数字 '0'");
        assert!(chars.contains(&"9"), "字符字典应包含数字 '9'");

        // 检查是否包含英文字母
        assert!(chars.contains(&"a"), "字符字典应包含小写字母 'a'");
        assert!(chars.contains(&"A"), "字符字典应包含大写字母 'A'");

        // 检查是否包含中文字符（常用字）
        assert!(chars.contains(&"的"), "字符字典应包含常用中文字 '的'");
    }

    /// 验证字符字典格式正确
    ///
    /// PP-OCRv4 字典中大部分是单字符
    #[test]
    fn test_char_dict_format() {
        let mut single_char_count = 0;
        let mut multi_char_count = 0;

        for line in CHAR_DICT.lines() {
            let char_count = line.chars().count();
            if char_count == 1 {
                single_char_count += 1;
            } else if char_count > 1 {
                multi_char_count += 1;
            }
        }

        // 大部分应该是单字符
        let total_lines = CHAR_DICT.lines().count();
        let single_char_ratio = single_char_count as f64 / total_lines as f64;
        assert!(
            single_char_ratio > 0.95,
            "单字符比例应大于 95%，实际: {:.1}% ({}/{})",
            single_char_ratio * 100.0,
            single_char_count,
            total_lines
        );

        // 打印字典统计信息
        println!(
            "字典统计: 总行数={}, 单字符={}, 多字符={}",
            total_lines, single_char_count, multi_char_count
        );
    }
}
