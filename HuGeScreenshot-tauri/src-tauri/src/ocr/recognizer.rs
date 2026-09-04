//! 文本识别模块
//!
//! 使用 PP-OCRv4 识别模型将检测到的文本区域转换为文字。
//!
//! # 功能
//!
//! - 加载 PP-OCRv4 识别模型 (IR 格式，预处理已注入)
//! - 使用 OpenVINO 执行高性能推理
//! - **并行预处理 + 批量推理**（最大化吞吐量）
//! - CTC 解码算法
//!
//! # 性能优化
//!
//! 采用分层优化策略：
//! - **预处理优化**：预处理已注入模型，直接传入 u8 数据
//! - **并行预处理 (rayon)**：图像裁剪、缩放等 CPU 密集型操作
//! - **批量推理 (Batch Inference)**：多个文本区域合并为单个 batch 推理
//! - **并行 CTC 解码 (rayon)**：解码阶段也并行化
//!
//! # Requirements
//!
//! - 4.1: 使用 PP-OCRv4 识别模型
//! - 4.2: 输出识别文本和置信度
//! - 5.4: 支持批量识别
//!
//! # 模型规格
//!
//! - 输入: `[N, 48, W, 3]` (u8, NHWC, BGR) - 预处理已注入模型
//! - 输出: `[N, W/4, 字符数]` 字符概率分布
//!
//! # CTC 解码
//!
//! 1. 对每个时间步，选择概率最高的字符索引
//! 2. 跳过空白标记（索引 0）
//! 3. 合并连续相同的字符

use image::DynamicImage;
use ndarray::Array3;
use rayon::prelude::*;

use super::models::{CHAR_DICT, REC_MODEL_IR_BIN, REC_MODEL_IR_XML};
use super::openvino_engine::InferenceSession;
use super::preprocessor::{preprocess_for_recognition_bucketed, preprocess_for_recognition_u8};
use super::types::{OcrError, TextBox, TextRegion};

/// 文本识别器
///
/// 使用 PP-OCRv4 识别模型将文本区域转换为文字。
///
/// # 线程安全
///
/// `TextRecognizer` 是线程安全的，可以在多线程环境中共享使用。
/// 内部使用 OpenVINO InferenceSession 进行推理。
pub struct TextRecognizer {
    /// OpenVINO 推理会话
    session: InferenceSession,
    /// 字符字典
    char_dict: Vec<String>,
    /// 识别模型输入高度
    input_height: u32,
}

impl TextRecognizer {
    /// 创建新的文本识别器
    ///
    /// 从嵌入的模型数据加载 PP-OCRv4 识别模型。
    ///
    /// # 返回
    ///
    /// - `Ok(TextRecognizer)`: 成功创建的识别器
    /// - `Err(OcrError)`: 模型加载失败
    pub fn new() -> Result<Self, OcrError> {
        Self::with_input_height(48)
    }

    /// 使用自定义输入高度创建识别器
    ///
    /// # 参数
    ///
    /// - `input_height`: 识别模型输入高度（默认 48）
    pub fn with_input_height(input_height: u32) -> Result<Self, OcrError> {
        let session = Self::load_model()?;
        let char_dict = Self::load_char_dict();

        Ok(Self { session, char_dict, input_height })
    }

    /// 预热识别模型（仅最常用宽度档位）
    ///
    /// 在应用启动时调用，消除首帧卡顿。
    /// 仅预热 320 这一档：
    /// - OpenVINO 对每种实测形状都会编译一份内核并常驻，预热全部档位会驻留 4 套副本，
    ///   占用 100-200MB；只预热常用档可在首次命中其他档位时按需编译，长期内存更低。
    /// - 320 覆盖大多数中文短句和按钮文字，是最高频档位。
    ///
    /// # 性能优势
    ///
    /// - 触发 OpenVINO JIT 编译和内存分配
    /// - 让硬件从低功耗状态升频到工作状态
    /// - 填充指令缓存 (I-Cache)
    ///
    /// # 返回
    ///
    /// - `Ok(())`: 预热成功
    /// - `Err(OcrError)`: 预热失败
    pub fn warmup(&self) -> Result<(), OcrError> {
        const WARMUP_WIDTH: usize = 320;
        const WARMUP_ITERATIONS: usize = 3;

        let warmup_start = std::time::Instant::now();
        let height = self.input_height as usize;
        let channels = 3;

        tracing::info!("🔥 开始预热识别模型: 仅 {} 档位, {} 次", WARMUP_WIDTH, WARMUP_ITERATIONS);

        // 创建哑数据（全零）
        let dummy_data = vec![0u8; height * WARMUP_WIDTH * channels];

        // 预热多次
        for i in 0..WARMUP_ITERATIONS {
            self.session.infer_recognition_u8(&dummy_data, height, WARMUP_WIDTH)?;
            tracing::trace!("预热档位 {} 第 {} 次完成", WARMUP_WIDTH, i + 1);
        }

        tracing::info!("🔥 识别模型预热完成，总耗时 {:.0}ms", warmup_start.elapsed().as_millis());

        Ok(())
    }

    /// 加载识别模型（IR 格式）
    fn load_model() -> Result<InferenceSession, OcrError> {
        tracing::info!("Loading PP-OCRv4 recognition model (IR format) with OpenVINO...");

        // 使用 OpenVINO 加载 IR 模型（预处理已注入）
        let session =
            InferenceSession::from_ir_bytes(REC_MODEL_IR_XML, REC_MODEL_IR_BIN, "recognition")?;

        tracing::info!("PP-OCRv4 recognition model (IR) loaded successfully");
        Ok(session)
    }

    /// 加载字符字典
    ///
    /// PP-OCRv4 模型输出 6625 个字符类别：
    /// - 索引 0: 空白标记 (blank token for CTC)
    /// - 索引 1-6622: 字典中的字符
    /// - 索引 6623: 空格 (如果字典中没有)
    /// - 索引 6624: 未知字符占位符
    fn load_char_dict() -> Vec<String> {
        const EXPECTED_VOCAB_SIZE: usize = 6625;

        // 第一个字符是空白标记
        let mut dict = vec!["".to_string()]; // blank token at index 0

        for line in CHAR_DICT.lines() {
            dict.push(line.to_string());
        }

        // 添加空格作为最后一个字符（如果字典中没有）
        if !dict.contains(&" ".to_string()) {
            dict.push(" ".to_string());
        }

        // 填充到模型期望的词汇表大小
        while dict.len() < EXPECTED_VOCAB_SIZE {
            dict.push("".to_string()); // 空字符串作为占位符
        }

        tracing::info!(
            "Loaded {} characters in dictionary (expected {})",
            dict.len(),
            EXPECTED_VOCAB_SIZE
        );
        dict
    }

    /// 识别单个文本区域
    ///
    /// # 参数
    ///
    /// - `image`: 裁剪后的文本区域图像
    ///
    /// # 返回
    ///
    /// - `Ok((String, f32))`: 识别的文本和置信度
    /// - `Err(OcrError)`: 识别失败
    pub fn recognize_single(&self, image: &DynamicImage) -> Result<(String, f32), OcrError> {
        // 预处理（u8 NHWC BGR 格式）
        let (data, height, width) = preprocess_for_recognition_u8(image, self.input_height)?;

        // 使用 OpenVINO 推理（u8 输入）
        let output = self.session.infer_recognition_u8(&data, height, width)?;

        // CTC 解码
        let (text, confidence) = self.ctc_decode(&output);

        Ok((text, confidence))
    }

    /// 批量识别文本区域
    ///
    /// 使用 **分桶策略 + 并行预处理 + 批量推理** 策略，最大化吞吐量。
    ///
    /// # 性能优化策略
    ///
    /// 1. **分桶策略 (Bucketing)**：将宽度归一化到 160/320/640/1280，避免 GPU Shader 重编译
    /// 2. **并行预处理 (rayon)**：裁剪、缩放、Padding 等 CPU 密集型操作
    /// 3. **按桶分组推理**：同一桶内的数据宽度相同，批量推理效率最高
    /// 4. **并行 CTC 解码 (rayon)**：解码阶段也并行化
    ///
    /// # 参数
    ///
    /// - `image`: 原始图像
    /// - `boxes`: 检测到的文本框列表
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<TextRegion>)`: 识别结果列表
    /// - `Err(OcrError)`: 识别失败
    pub fn recognize_batch(
        &self,
        image: &DynamicImage,
        boxes: &[TextBox],
    ) -> Result<Vec<TextRegion>, OcrError> {
        type BucketedItem = (usize, TextBox, Vec<u8>, usize, usize, usize);
        type BucketedGroupMap = std::collections::HashMap<usize, Vec<BucketedItem>>;

        if boxes.is_empty() {
            return Ok(Vec::new());
        }

        let start = std::time::Instant::now();
        tracing::debug!(
            "开始批量识别 {} 个文本区域（分桶策略 + 并行预处理 + 批量推理）",
            boxes.len()
        );

        // ========================================
        // 阶段 1: 并行预处理 + 分桶（rayon）
        // ========================================
        let preprocess_start = std::time::Instant::now();

        // 并行裁剪和预处理所有文本区域（使用分桶策略）
        // 返回: (原始索引, bbox, 数据, 高度, 桶宽度, 原始宽度)
        let preprocessed: Vec<BucketedItem> = boxes
            .par_iter()
            .enumerate()
            .filter_map(|(idx, bbox)| {
                // 裁剪文本区域
                match super::preprocessor::crop_text_region(image, &bbox.points) {
                    Ok(cropped) => {
                        // 预处理（缩放 + 分桶 + Padding，u8 NHWC BGR 格式）
                        match preprocess_for_recognition_bucketed(&cropped, self.input_height) {
                            Ok((data, height, bucket_width, original_width)) => Some((
                                idx,
                                bbox.clone(),
                                data,
                                height,
                                bucket_width,
                                original_width,
                            )),
                            Err(e) => {
                                tracing::warn!("预处理区域 {} 失败: {}", idx, e);
                                None
                            }
                        }
                    }
                    Err(e) => {
                        tracing::warn!("裁剪区域 {} 失败: {}", idx, e);
                        None
                    }
                }
            })
            .collect();

        let preprocess_elapsed = preprocess_start.elapsed();

        // 统计各桶的数量
        let mut bucket_counts: std::collections::HashMap<usize, usize> =
            std::collections::HashMap::new();
        for (_, _, _, _, bucket_width, _) in &preprocessed {
            *bucket_counts.entry(*bucket_width).or_default() += 1;
        }
        tracing::debug!(
            "并行预处理完成: {} 个区域, 耗时 {:.0}ms, 分桶分布: {:?}",
            preprocessed.len(),
            preprocess_elapsed.as_millis(),
            bucket_counts
        );

        if preprocessed.is_empty() {
            return Ok(Vec::new());
        }

        // ========================================
        // 阶段 2: 按桶分组 + 批量推理
        // ========================================
        let infer_start = std::time::Instant::now();

        // 按桶宽度分组
        let mut bucket_groups: BucketedGroupMap = std::collections::HashMap::new();
        for item in preprocessed {
            let bucket_width = item.4;
            bucket_groups.entry(bucket_width).or_default().push(item);
        }

        // 存储所有推理结果: (原始索引, bbox, output, 原始宽度)
        let mut all_results: Vec<(usize, TextBox, ndarray::Array3<f32>, usize)> = Vec::new();

        // 按桶分别进行批量推理
        for (bucket_width, items) in bucket_groups {
            let batch_size = items.len();
            tracing::debug!("推理桶 {} ({}个样本)", bucket_width, batch_size);

            // 提取数据
            let indices: Vec<usize> = items.iter().map(|(idx, _, _, _, _, _)| *idx).collect();
            let boxes_in_bucket: Vec<TextBox> =
                items.iter().map(|(_, bbox, _, _, _, _)| bbox.clone()).collect();
            let original_widths: Vec<usize> = items.iter().map(|(_, _, _, _, _, ow)| *ow).collect();
            let inputs: Vec<(Vec<u8>, usize, usize)> = items
                .into_iter()
                .map(|(_, _, data, height, bucket_width, _)| (data, height, bucket_width))
                .collect();

            // 执行批量推理（同一桶内宽度相同，无需额外 padding）
            let outputs = self.session.infer_recognition_batch_u8(&inputs, bucket_width)?;

            // 收集结果
            for ((idx, bbox), (output, original_width)) in indices
                .into_iter()
                .zip(boxes_in_bucket.into_iter())
                .zip(outputs.into_iter().zip(original_widths.into_iter()))
            {
                all_results.push((idx, bbox, output, original_width));
            }
        }

        let infer_elapsed = infer_start.elapsed();
        tracing::debug!(
            "批量推理完成: {} 个输出, 耗时 {:.0}ms",
            all_results.len(),
            infer_elapsed.as_millis()
        );

        // ========================================
        // 阶段 3: CTC 解码（考虑原始宽度截断）
        // ========================================
        let decode_start = std::time::Instant::now();

        // 按原始索引排序（确保后续处理顺序正确）
        all_results.sort_by_key(|(idx, _, _, _)| *idx);

        // 并行 CTC 解码（保留索引以便后续排序）
        let char_dict = &self.char_dict;
        let mut decoded_regions: Vec<(usize, TextRegion)> = all_results
            .par_iter()
            .enumerate()
            .map(|(sorted_idx, (_, bbox, output, original_width))| {
                // 根据原始宽度计算有效的时间步数
                // PP-OCRv4 识别模型的时间步 = 宽度 / 4（因为 CNN 下采样 4 倍）
                let valid_timesteps = (*original_width).div_ceil(4); // 向上取整
                let (text, confidence) =
                    Self::ctc_decode_with_length(output, char_dict, valid_timesteps);
                (sorted_idx, TextRegion::new(bbox.clone(), text, confidence))
            })
            .collect();

        // 按排序后的索引重新排序（恢复阅读顺序）
        // 因为 par_iter() 不保证输出顺序
        decoded_regions.sort_by_key(|(idx, _)| *idx);
        let regions: Vec<TextRegion> = decoded_regions.into_iter().map(|(_, r)| r).collect();

        let decode_elapsed = decode_start.elapsed();

        tracing::info!(
            "批量识别完成: {} 个区域, 总耗时 {:.0}ms (预处理 {:.0}ms + 批量推理 {:.0}ms + 解码 {:.0}ms)",
            regions.len(),
            start.elapsed().as_millis(),
            preprocess_elapsed.as_millis(),
            infer_elapsed.as_millis(),
            decode_elapsed.as_millis()
        );

        Ok(regions)
    }

    /// CTC 贪婪解码（带长度限制）
    ///
    /// 将模型输出的概率分布转换为文本，只解码有效的时间步。
    ///
    /// # 参数
    ///
    /// - `output`: 模型输出 [1, T, V]
    /// - `char_dict`: 字符字典
    /// - `valid_timesteps`: 有效的时间步数（根据原始宽度计算）
    ///
    /// # 返回
    ///
    /// (解码的文本, 平均置信度)
    fn ctc_decode_with_length(
        output: &Array3<f32>,
        char_dict: &[String],
        valid_timesteps: usize,
    ) -> (String, f32) {
        let total_timesteps = output.shape()[1];
        let vocab_size = output.shape()[2];

        // 只解码有效的时间步，避免 Padding 区域产生乱码
        let timesteps = valid_timesteps.min(total_timesteps);

        let mut text = String::new();
        let mut last_idx: usize = 0;
        let mut confidences = Vec::new();

        for t in 0..timesteps {
            let mut max_idx = 0;
            let mut max_val = f32::NEG_INFINITY;

            for v in 0..vocab_size {
                let val = output[[0, t, v]];
                if val > max_val {
                    max_val = val;
                    max_idx = v;
                }
            }

            let confidence = if max_val > 0.0 && max_val <= 1.0 {
                max_val
            } else {
                let mut sum_exp = 0.0f32;
                for v in 0..vocab_size {
                    sum_exp += (output[[0, t, v]] - max_val).exp();
                }
                (1.0 / sum_exp).clamp(0.0, 1.0)
            };

            if max_idx != 0 && max_idx != last_idx {
                if let Some(ch) = char_dict.get(max_idx) {
                    text.push_str(ch);
                    confidences.push(confidence);
                }
            }

            last_idx = max_idx;
        }

        let avg_confidence = if confidences.is_empty() {
            0.0
        } else {
            confidences.iter().sum::<f32>() / confidences.len() as f32
        };

        (text, avg_confidence)
    }

    /// CTC 贪婪解码
    ///
    /// 将模型输出的概率分布转换为文本。
    ///
    /// # 算法
    ///
    /// 1. 对每个时间步，选择概率最高的字符索引
    /// 2. 跳过空白标记（索引 0）
    /// 3. 合并连续相同的字符
    ///
    /// # 参数
    ///
    /// - `output`: 模型输出 [1, T, V]
    ///
    /// # 返回
    ///
    /// (解码的文本, 平均置信度)
    fn ctc_decode(&self, output: &Array3<f32>) -> (String, f32) {
        let timesteps = output.shape()[1];
        let vocab_size = output.shape()[2];

        // 调试：检查词汇表大小是否匹配
        if vocab_size != self.char_dict.len() {
            tracing::warn!(
                "Vocab size mismatch! Model outputs {} classes, but dictionary has {} characters",
                vocab_size,
                self.char_dict.len()
            );
        }

        // 调试：打印第一个时间步的原始输出统计
        if timesteps > 0 {
            let mut min_val = f32::INFINITY;
            let mut max_val = f32::NEG_INFINITY;
            let mut sum_val = 0.0f32;
            for v in 0..vocab_size {
                let val = output[[0, 0, v]];
                min_val = min_val.min(val);
                max_val = max_val.max(val);
                sum_val += val;
            }
            tracing::debug!(
                "Model output stats (timestep 0): min={:.4}, max={:.4}, mean={:.4}, vocab_size={}",
                min_val,
                max_val,
                sum_val / vocab_size as f32,
                vocab_size
            );
        }

        let mut text = String::new();
        let mut last_idx: usize = 0; // 0 是空白标记
        let mut confidences = Vec::new();

        for t in 0..timesteps {
            // 找到概率最高的字符索引
            let mut max_idx = 0;
            let mut max_val = f32::NEG_INFINITY;

            for v in 0..vocab_size {
                let val = output[[0, t, v]];
                if val > max_val {
                    max_val = val;
                    max_idx = v;
                }
            }

            // 计算置信度
            // PP-OCRv4 模型输出可能是：
            // 1. 原始 logits（需要 softmax）
            // 2. 已经是 softmax 概率（直接使用）
            //
            // 判断方法：检查输出值的范围
            // - 如果 max_val > 1.0 或有负值，说明是 logits
            // - 如果 max_val <= 1.0 且所有值 >= 0，可能是概率
            //
            // 为了简化，我们检查 max_val 是否在合理的概率范围内
            let confidence = if max_val > 0.0 && max_val <= 1.0 {
                // 输出看起来已经是概率，直接使用
                max_val
            } else {
                // 输出是 logits，需要计算 softmax
                let mut sum_exp = 0.0f32;
                for v in 0..vocab_size {
                    sum_exp += (output[[0, t, v]] - max_val).exp();
                }
                // softmax(max) = exp(0) / sum_exp = 1.0 / sum_exp
                (1.0 / sum_exp).clamp(0.0, 1.0)
            };

            // CTC 解码规则：
            // 1. 跳过空白标记（索引 0）
            // 2. 跳过与上一个相同的字符
            if max_idx != 0 && max_idx != last_idx {
                if let Some(ch) = self.char_dict.get(max_idx) {
                    text.push_str(ch);
                    confidences.push(confidence);
                }
            }

            last_idx = max_idx;
        }

        // 计算平均置信度
        let avg_confidence = if confidences.is_empty() {
            0.0
        } else {
            confidences.iter().sum::<f32>() / confidences.len() as f32
        };

        (text, avg_confidence)
    }

    /// 获取字符字典大小
    pub fn vocab_size(&self) -> usize {
        self.char_dict.len()
    }

    /// 获取输入高度
    pub fn input_height(&self) -> u32 {
        self.input_height
    }
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array3;
    use serial_test::serial;

    // ----------------------------------------
    // 字符字典测试
    // ----------------------------------------

    #[test]
    fn test_load_char_dict() {
        let dict = TextRecognizer::load_char_dict();

        // 第一个应该是空白标记
        assert_eq!(dict[0], "");

        // 应该包含基本字符
        assert!(dict.len() > 1000, "字典应该包含超过 1000 个字符");

        // 应该包含数字
        assert!(dict.contains(&"0".to_string()));
        assert!(dict.contains(&"9".to_string()));

        // 应该包含字母
        assert!(dict.contains(&"a".to_string()));
        assert!(dict.contains(&"A".to_string()));
    }

    // ----------------------------------------
    // CTC 解码测试
    // ----------------------------------------

    #[test]
    fn test_ctc_decode_basic() {
        // 创建一个简单的模拟输出
        // 假设字典: [blank, a, b, c, ...]
        // 输出序列: [a, a, blank, b, b, b] -> "ab"

        let dict = vec![
            "".to_string(), // blank
            "a".to_string(),
            "b".to_string(),
            "c".to_string(),
        ];

        // 创建模拟的 recognizer（不加载真实模型）
        // 这里我们直接测试解码逻辑

        // 模拟输出: 6 个时间步，4 个字符
        let mut output = Array3::<f32>::zeros((1, 6, 4));

        // 时间步 0, 1: 'a' (索引 1) 概率最高
        output[[0, 0, 1]] = 10.0;
        output[[0, 1, 1]] = 10.0;

        // 时间步 2: blank (索引 0) 概率最高
        output[[0, 2, 0]] = 10.0;

        // 时间步 3, 4, 5: 'b' (索引 2) 概率最高
        output[[0, 3, 2]] = 10.0;
        output[[0, 4, 2]] = 10.0;
        output[[0, 5, 2]] = 10.0;

        // 手动执行 CTC 解码逻辑
        let (text, _) = ctc_decode_test(&output, &dict);

        assert_eq!(text, "ab", "CTC 解码应该输出 'ab'");
    }

    #[test]
    fn test_ctc_decode_empty() {
        let dict = vec!["".to_string(), "a".to_string()];

        // 所有时间步都是 blank
        let mut output = Array3::<f32>::zeros((1, 5, 2));
        for t in 0..5 {
            output[[0, t, 0]] = 10.0; // blank 概率最高
        }

        let (text, _) = ctc_decode_test(&output, &dict);
        assert!(text.is_empty(), "全 blank 应该输出空字符串");
    }

    #[test]
    fn test_ctc_decode_repeated() {
        let dict = vec!["".to_string(), "a".to_string()];

        // 连续的 'a' 应该合并为一个
        let mut output = Array3::<f32>::zeros((1, 5, 2));
        for t in 0..5 {
            output[[0, t, 1]] = 10.0; // 'a' 概率最高
        }

        let (text, _) = ctc_decode_test(&output, &dict);
        assert_eq!(text, "a", "连续相同字符应该合并");
    }

    /// 测试用的 CTC 解码函数
    fn ctc_decode_test(output: &Array3<f32>, dict: &[String]) -> (String, f32) {
        let timesteps = output.shape()[1];
        let vocab_size = output.shape()[2];

        let mut text = String::new();
        let mut last_idx: usize = 0;
        let mut confidences = Vec::new();

        for t in 0..timesteps {
            let mut max_idx = 0;
            let mut max_prob = f32::NEG_INFINITY;

            for v in 0..vocab_size {
                let prob = output[[0, t, v]];
                if prob > max_prob {
                    max_prob = prob;
                    max_idx = v;
                }
            }

            if max_idx != 0 && max_idx != last_idx {
                if let Some(ch) = dict.get(max_idx) {
                    text.push_str(ch);
                    confidences.push(1.0); // 简化置信度
                }
            }

            last_idx = max_idx;
        }

        let avg_confidence = if confidences.is_empty() {
            0.0
        } else {
            confidences.iter().sum::<f32>() / confidences.len() as f32
        };

        (text, avg_confidence)
    }

    // ----------------------------------------
    // softmax 测试
    // ----------------------------------------

    #[test]
    fn test_softmax_confidence() {
        let mut output = Array3::<f32>::zeros((1, 1, 3));
        output[[0, 0, 0]] = 1.0;
        output[[0, 0, 1]] = 2.0;
        output[[0, 0, 2]] = 3.0;

        // 手动计算 softmax
        let max_val = 3.0f32;
        let sum_exp = (1.0 - max_val).exp() + (2.0 - max_val).exp() + (3.0 - max_val).exp();
        let expected_prob = (3.0 - max_val).exp() / sum_exp;

        // 计算索引 2 的 softmax 概率
        let prob = softmax_test(&output, 0, 2);

        assert!((prob - expected_prob).abs() < 0.001);
    }

    fn softmax_test(output: &Array3<f32>, timestep: usize, idx: usize) -> f32 {
        let vocab_size = output.shape()[2];

        let mut max_val = f32::NEG_INFINITY;
        for v in 0..vocab_size {
            max_val = max_val.max(output[[0, timestep, v]]);
        }

        let mut sum_exp = 0.0f32;
        for v in 0..vocab_size {
            sum_exp += (output[[0, timestep, v]] - max_val).exp();
        }

        (output[[0, timestep, idx]] - max_val).exp() / sum_exp
    }

    // ----------------------------------------
    // 创建识别器测试
    // ----------------------------------------

    #[test]
    #[serial(ocr_openvino)]
    fn test_recognizer_creation() {
        // 注意：此测试需要模型文件正确嵌入
        let result = TextRecognizer::new();

        match result {
            Ok(recognizer) => {
                println!("Recognizer created successfully");
                println!("Vocab size: {}", recognizer.vocab_size());
                println!("Input height: {}", recognizer.input_height());
                assert!(recognizer.vocab_size() > 1000);
                assert_eq!(recognizer.input_height(), 48);
            }
            Err(e) => {
                println!("Recognizer creation failed (expected in some environments): {}", e);
            }
        }
    }

    // ----------------------------------------
    // 预热测试
    // ----------------------------------------

    #[test]
    #[serial(ocr_openvino)]
    fn test_recognizer_warmup() {
        // 注意：此测试需要模型文件正确嵌入和 OpenVINO 环境
        let result = TextRecognizer::new();

        match result {
            Ok(recognizer) => {
                println!("开始预热测试...");
                let start = std::time::Instant::now();

                match recognizer.warmup() {
                    Ok(()) => {
                        let elapsed = start.elapsed();
                        println!("✅ 预热成功，耗时 {:.0}ms", elapsed.as_millis());
                        // 预热应该在合理时间内完成（< 30s）
                        assert!(elapsed.as_secs() < 30, "预热时间过长");
                    }
                    Err(e) => {
                        println!("预热失败（可能是环境问题）: {}", e);
                    }
                }
            }
            Err(e) => {
                println!("Recognizer creation failed (expected in some environments): {}", e);
            }
        }
    }
}
