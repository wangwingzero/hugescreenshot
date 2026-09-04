//! OCR 布局处理模块
//!
//! 实现文本区域的行合并和空格插入，保持原图排版布局。
//!
//! # 算法流程
//!
//! 1. 按 Y 坐标对文本区域进行行分组
//! 2. 行内按 X 坐标排序
//! 3. 根据相邻区域的间距计算空格数量
//! 4. 合并同一行的文本，插入适当数量的空格
//!
//! # 参考
//!
//! - 垂直重叠度算法判断同一行
//! - 动态空格计算基于字符高度

use super::types::OcrBox;
use unicode_width::UnicodeWidthStr;

/// 行分组结果
#[derive(Debug)]
struct TextLine {
    /// 该行的所有文本框（已按 X 坐标排序）
    boxes: Vec<OcrBox>,
    /// 该行的 Y 中心坐标
    y_center: f64,
    /// 该行的平均高度
    avg_height: f64,
}

/// 布局处理器
///
/// 将 OCR 识别结果按原图布局重新排版。
pub struct LayoutProcessor {
    /// 垂直重叠阈值（默认 0.5）
    /// 两个文本框的垂直重叠度超过此值时，视为同一行
    y_overlap_threshold: f64,

    /// 空格宽度系数（默认 0.5）
    /// 空格宽度 = 字符高度 * 此系数
    space_width_ratio: f64,

    /// 最大空格数（默认 20）
    /// 防止间距过大时插入过多空格
    max_spaces: usize,
}

impl Default for LayoutProcessor {
    fn default() -> Self {
        Self { y_overlap_threshold: 0.5, space_width_ratio: 0.5, max_spaces: 20 }
    }
}

impl LayoutProcessor {
    /// 创建新的布局处理器
    pub fn new() -> Self {
        Self::default()
    }

    /// 设置垂直重叠阈值
    pub fn with_y_overlap_threshold(mut self, threshold: f64) -> Self {
        self.y_overlap_threshold = threshold.clamp(0.1, 0.9);
        self
    }

    /// 设置空格宽度系数
    pub fn with_space_width_ratio(mut self, ratio: f64) -> Self {
        self.space_width_ratio = ratio.clamp(0.2, 1.0);
        self
    }

    /// 设置最大空格数
    pub fn with_max_spaces(mut self, max: usize) -> Self {
        self.max_spaces = max.max(1);
        self
    }

    /// 处理 OCR 结果，生成保持原图布局的文本
    ///
    /// # 参数
    ///
    /// - `boxes`: OCR 识别的文本框列表
    ///
    /// # 返回
    ///
    /// 保持原图布局的文本字符串
    pub fn process(&self, boxes: &[OcrBox]) -> String {
        if boxes.is_empty() {
            return String::new();
        }

        // 使用全局字符宽度估计，减少行间抖动导致的列错位
        let global_char_width = self.estimate_char_width(boxes);

        // 1. 按行分组
        let lines = self.group_into_lines(boxes);

        // 2. 生成带空格的文本
        self.generate_text(&lines, global_char_width)
    }

    /// 将文本框按行分组
    fn group_into_lines(&self, boxes: &[OcrBox]) -> Vec<TextLine> {
        if boxes.is_empty() {
            return Vec::new();
        }

        // 提取边界框信息并按 Y 坐标排序
        let mut box_infos: Vec<(usize, f64, f64, f64, f64)> = boxes
            .iter()
            .enumerate()
            .map(|(i, b)| {
                let (y_min, y_max, y_center, height) = self.get_y_info(b);
                (i, y_min, y_max, y_center, height)
            })
            .collect();

        box_infos.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

        let mut lines: Vec<TextLine> = Vec::new();

        for (idx, y_min, y_max, y_center, height) in box_infos {
            // 查找是否有垂直重叠的现有行
            let matched_line = lines.iter_mut().find(|line| {
                self.is_same_line(y_min, y_max, height, line.y_center, line.avg_height)
            });

            match matched_line {
                Some(line) => {
                    // 添加到现有行
                    line.boxes.push(boxes[idx].clone());
                    // 更新行的 Y 中心和平均高度
                    let n = line.boxes.len() as f64;
                    line.y_center = (line.y_center * (n - 1.0) + y_center) / n;
                    line.avg_height = (line.avg_height * (n - 1.0) + height) / n;
                }
                None => {
                    // 创建新行
                    lines.push(TextLine {
                        boxes: vec![boxes[idx].clone()],
                        y_center,
                        avg_height: height,
                    });
                }
            }
        }

        // 按 Y 坐标排序行
        lines.sort_by(|a, b| {
            a.y_center.partial_cmp(&b.y_center).unwrap_or(std::cmp::Ordering::Equal)
        });

        // 行内按 X 坐标排序
        for line in &mut lines {
            line.boxes.sort_by(|a, b| {
                let a_x = self.get_x_min(a);
                let b_x = self.get_x_min(b);
                a_x.partial_cmp(&b_x).unwrap_or(std::cmp::Ordering::Equal)
            });
        }

        lines
    }

    /// 判断是否属于同一行
    fn is_same_line(
        &self,
        y_min: f64,
        y_max: f64,
        height: f64,
        line_y_center: f64,
        line_avg_height: f64,
    ) -> bool {
        // 计算垂直重叠度
        let box_center = (y_min + y_max) / 2.0;
        let center_diff = (box_center - line_y_center).abs();
        let threshold = (height.min(line_avg_height)) * self.y_overlap_threshold;

        center_diff < threshold
    }

    /// 获取文本框的 Y 坐标信息
    fn get_y_info(&self, b: &OcrBox) -> (f64, f64, f64, f64) {
        if b.box_coords.len() < 4 {
            return (0.0, 0.0, 0.0, 0.0);
        }

        let y_coords: Vec<f64> =
            b.box_coords.iter().map(|p| p.get(1).copied().unwrap_or(0.0)).collect();
        let y_min = y_coords.iter().cloned().fold(f64::INFINITY, f64::min);
        let y_max = y_coords.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let y_center = (y_min + y_max) / 2.0;
        let height = y_max - y_min;

        (y_min, y_max, y_center, height)
    }

    /// 获取文本框的 X 最小坐标
    fn get_x_min(&self, b: &OcrBox) -> f64 {
        b.box_coords.iter().map(|p| p.first().copied().unwrap_or(0.0)).fold(f64::INFINITY, f64::min)
    }

    /// 获取文本框的 X 最大坐标
    fn get_x_max(&self, b: &OcrBox) -> f64 {
        b.box_coords
            .iter()
            .map(|p| p.first().copied().unwrap_or(0.0))
            .fold(f64::NEG_INFINITY, f64::max)
    }

    /// 生成带空格的文本（含智能段落分隔）
    fn generate_text(&self, lines: &[TextLine], global_char_width: Option<f64>) -> String {
        let mut result = String::new();
        let char_width = global_char_width.filter(|w| *w > 0.0);
        let global_origin_x = char_width.map(|_| self.get_global_min_x(lines)).unwrap_or(0.0);

        // 智能段落检测：计算典型行间距和左边距
        let typical_line_gap = self.calculate_typical_line_gap(lines);
        let typical_left_margin = self.calculate_typical_left_margin(lines);

        for (line_idx, line) in lines.iter().enumerate() {
            if line_idx > 0 {
                let is_paragraph_break = self.detect_paragraph_break(
                    &lines[line_idx - 1],
                    line,
                    typical_line_gap,
                    typical_left_margin,
                );
                if is_paragraph_break {
                    result.push_str("\n\n");
                } else {
                    result.push('\n');
                }
            }

            let mut line_text = String::new();

            if let Some(width) = char_width {
                // 绝对列对齐：使用全局字符宽度将 x 坐标映射到列索引
                for bbox in &line.boxes {
                    if bbox.text.is_empty() {
                        continue;
                    }

                    let x_min = self.get_x_min(bbox);
                    let column = self.calculate_column_index(x_min, global_origin_x, width);
                    self.pad_to_column(&mut line_text, column);
                    line_text.push_str(&bbox.text);
                }
            } else {
                // 退化路径：按相邻间距插入空格
                for (i, bbox) in line.boxes.iter().enumerate() {
                    line_text.push_str(&bbox.text);

                    if i < line.boxes.len() - 1 {
                        let current_x_max = self.get_x_max(bbox);
                        let next_x_min = self.get_x_min(&line.boxes[i + 1]);
                        let gap = next_x_min - current_x_max;

                        let space_width = line.avg_height * self.space_width_ratio;
                        let space_count = self.calculate_space_count_with_width(gap, space_width);
                        if space_count > 0 {
                            line_text.push_str(&" ".repeat(space_count));
                        }
                    }
                }
            }

            result.push_str(&line_text);
        }

        result
    }

    /// 计算应插入的空格数量
    #[allow(dead_code)]
    fn calculate_space_count(&self, gap: f64, char_height: f64) -> usize {
        if gap <= 0.0 || char_height <= 0.0 {
            return 0;
        }

        // 空格宽度 = 字符高度 * 空格宽度系数
        let space_width = char_height * self.space_width_ratio;

        self.calculate_space_count_with_width(gap, space_width)
    }

    /// 使用指定空格宽度计算空格数
    fn calculate_space_count_with_width(&self, gap: f64, space_width: f64) -> usize {
        if gap <= 0.0 || space_width <= 0.0 {
            return 0;
        }

        // 计算空格数量
        let count = (gap / space_width).round() as usize;

        // 限制最大空格数
        count.min(self.max_spaces)
    }

    /// 估算全局字符宽度（中位数），用于列对齐
    fn estimate_char_width(&self, boxes: &[OcrBox]) -> Option<f64> {
        let mut widths: Vec<f64> = Vec::new();

        for b in boxes {
            let text_len = UnicodeWidthStr::width(b.text.as_str());
            if text_len == 0 {
                continue;
            }

            let x_min = self.get_x_min(b);
            let x_max = self.get_x_max(b);
            let width = x_max - x_min;
            if width > 0.0 {
                widths.push(width / text_len as f64);
            }
        }

        if widths.is_empty() {
            return None;
        }

        widths.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        Some(widths[widths.len() / 2])
    }

    /// 获取全局最小 X（用于列对齐的起点）
    fn get_global_min_x(&self, lines: &[TextLine]) -> f64 {
        let mut min_x = f64::INFINITY;
        for line in lines {
            for bbox in &line.boxes {
                let x = self.get_x_min(bbox);
                if x < min_x {
                    min_x = x;
                }
            }
        }
        if min_x.is_finite() {
            min_x
        } else {
            0.0
        }
    }

    /// 将 x 坐标映射为列索引（等宽字符网格）
    fn calculate_column_index(&self, x: f64, origin_x: f64, char_width: f64) -> usize {
        if char_width <= 0.0 {
            return 0;
        }
        let col = ((x - origin_x) / char_width).round() as isize;
        if col < 0 {
            0
        } else {
            col as usize
        }
    }

    /// 计算典型行间距（相邻行 Y 中心的间距中位数）
    fn calculate_typical_line_gap(&self, lines: &[TextLine]) -> f64 {
        if lines.len() < 2 {
            return 0.0;
        }

        let mut gaps: Vec<f64> = Vec::new();
        for i in 1..lines.len() {
            let gap = (lines[i].y_center - lines[i - 1].y_center).abs();
            if gap > 0.0 {
                gaps.push(gap);
            }
        }

        if gaps.is_empty() {
            return 0.0;
        }

        gaps.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        gaps[gaps.len() / 2]
    }

    /// 计算典型左边距（所有行首个文本框的 X 坐标最小值）
    ///
    /// 使用最小值而非中位数，因为缩进行是例外，不应影响基准边距。
    fn calculate_typical_left_margin(&self, lines: &[TextLine]) -> f64 {
        lines
            .iter()
            .filter(|l| !l.boxes.is_empty())
            .map(|l| self.get_x_min(&l.boxes[0]))
            .fold(f64::INFINITY, f64::min)
            .min(f64::MAX) // 避免空集返回 INFINITY
    }

    /// 检测是否为段落分隔
    ///
    /// 通过以下信号判断段落边界：
    /// 1. 行间距显著大于典型行间距（> 1.8 倍）
    /// 2. 当前行有首行缩进（相对于典型左边距偏移 > 1.5 个字符高度）
    fn detect_paragraph_break(
        &self,
        prev_line: &TextLine,
        curr_line: &TextLine,
        typical_gap: f64,
        typical_left: f64,
    ) -> bool {
        if typical_gap <= 0.0 {
            return false;
        }

        // 信号 1：行间距显著大于典型值
        let actual_gap = (curr_line.y_center - prev_line.y_center).abs();
        if actual_gap > typical_gap * 1.8 {
            return true;
        }

        // 信号 2：当前行有首行缩进
        if !curr_line.boxes.is_empty() {
            let curr_left = self.get_x_min(&curr_line.boxes[0]);
            let indent = curr_left - typical_left;
            let char_height = curr_line.avg_height;

            // 缩进 > 1.5 个字符高度视为首行缩进
            if char_height > 0.0 && indent > char_height * 1.5 {
                return true;
            }
        }

        false
    }

    /// 将行文本补齐到指定列（含最大空格限制）
    fn pad_to_column(&self, line_text: &mut String, target_col: usize) {
        let current_len = UnicodeWidthStr::width(line_text.as_str());

        if target_col > current_len {
            let mut spaces = target_col - current_len;
            spaces = spaces.min(self.max_spaces);
            if spaces > 0 {
                line_text.push_str(&" ".repeat(spaces));
            }
            return;
        }

        if current_len > 0 && !line_text.ends_with(' ') {
            line_text.push(' ');
        }
    }
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;

    fn create_box(text: &str, x: f64, y: f64, w: f64, h: f64) -> OcrBox {
        OcrBox {
            text: text.to_string(),
            confidence: 0.95,
            box_coords: vec![
                vec![x, y],         // 左上
                vec![x + w, y],     // 右上
                vec![x + w, y + h], // 右下
                vec![x, y + h],     // 左下
            ],
        }
    }

    #[test]
    fn test_empty_boxes() {
        let processor = LayoutProcessor::new();
        let result = processor.process(&[]);
        assert!(result.is_empty());
    }

    #[test]
    fn test_single_box() {
        let processor = LayoutProcessor::new();
        let boxes = vec![create_box("Hello", 0.0, 0.0, 100.0, 30.0)];
        let result = processor.process(&boxes);
        assert_eq!(result, "Hello");
    }

    #[test]
    fn test_same_line_merge() {
        let processor = LayoutProcessor::new();
        // 两个文本框在同一行，间距较小
        let boxes = vec![
            create_box("Hello", 0.0, 0.0, 100.0, 30.0),
            create_box("World", 120.0, 0.0, 100.0, 30.0),
        ];
        let result = processor.process(&boxes);
        // 间距 20px，字符高度 30px，空格宽度 15px，应该插入 1 个空格
        assert!(result.contains("Hello"));
        assert!(result.contains("World"));
        assert!(!result.contains('\n'));
    }

    #[test]
    fn test_different_lines() {
        let processor = LayoutProcessor::new();
        // 两个文本框在不同行
        let boxes = vec![
            create_box("Line1", 0.0, 0.0, 100.0, 30.0),
            create_box("Line2", 0.0, 50.0, 100.0, 30.0),
        ];
        let result = processor.process(&boxes);
        assert_eq!(result, "Line1\nLine2");
    }

    #[test]
    fn test_large_gap_multiple_spaces() {
        let processor = LayoutProcessor::new();
        // 两个文本框在同一行，间距较大
        let boxes = vec![
            create_box("Left", 0.0, 0.0, 50.0, 30.0),
            create_box("Right", 200.0, 0.0, 50.0, 30.0),
        ];
        let result = processor.process(&boxes);
        // 间距 150px，字符高度 30px，空格宽度 15px，应该插入 10 个空格
        let space_count = result.matches(' ').count();
        assert!(space_count >= 5, "Expected at least 5 spaces, got {}", space_count);
    }

    #[test]
    fn test_max_spaces_limit() {
        let processor = LayoutProcessor::new().with_max_spaces(5);
        // 两个文本框在同一行，间距非常大
        let boxes =
            vec![create_box("A", 0.0, 0.0, 20.0, 30.0), create_box("B", 500.0, 0.0, 20.0, 30.0)];
        let result = processor.process(&boxes);
        let space_count = result.matches(' ').count();
        assert!(space_count <= 5, "Expected at most 5 spaces, got {}", space_count);
    }

    #[test]
    fn test_complex_layout() {
        let processor = LayoutProcessor::new();
        // 模拟复杂布局：两行，每行两个文本框
        let boxes = vec![
            create_box("A1", 0.0, 0.0, 50.0, 30.0),
            create_box("A2", 100.0, 0.0, 50.0, 30.0),
            create_box("B1", 0.0, 50.0, 50.0, 30.0),
            create_box("B2", 100.0, 50.0, 50.0, 30.0),
        ];
        let result = processor.process(&boxes);
        let lines: Vec<&str> = result.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("A1"));
        assert!(lines[0].contains("A2"));
        assert!(lines[1].contains("B1"));
        assert!(lines[1].contains("B2"));
    }

    #[test]
    fn test_paragraph_break_by_large_gap() {
        let processor = LayoutProcessor::new();
        // 两个段落，中间有较大间距
        let boxes = vec![
            create_box("段落一第一行", 0.0, 0.0, 200.0, 30.0),
            create_box("段落一第二行", 0.0, 40.0, 200.0, 30.0),
            // 间距 80px vs 典型 40px → 段落分隔
            create_box("段落二第一行", 0.0, 120.0, 200.0, 30.0),
            create_box("段落二第二行", 0.0, 160.0, 200.0, 30.0),
        ];
        let result = processor.process(&boxes);
        // 应该有段落分隔（\n\n）
        assert!(result.contains("\n\n"), "Should contain paragraph break, got: {}", result);
    }

    #[test]
    fn test_paragraph_break_by_indent() {
        let processor = LayoutProcessor::new();
        // 第二行有首行缩进
        let boxes = vec![
            create_box("第一段结尾", 0.0, 0.0, 200.0, 30.0),
            // 缩进 60px > 30px * 1.5 = 45px → 新段落
            create_box("第二段开始", 60.0, 40.0, 200.0, 30.0),
        ];
        let result = processor.process(&boxes);
        assert!(
            result.contains("\n\n"),
            "Should detect indent as paragraph break, got: {}",
            result
        );
    }

    #[test]
    fn test_no_paragraph_break_normal_spacing() {
        let processor = LayoutProcessor::new();
        // 正常行间距，不应有段落分隔
        let boxes = vec![
            create_box("第一行", 0.0, 0.0, 200.0, 30.0),
            create_box("第二行", 0.0, 40.0, 200.0, 30.0),
            create_box("第三行", 0.0, 80.0, 200.0, 30.0),
        ];
        let result = processor.process(&boxes);
        assert!(
            !result.contains("\n\n"),
            "Should not have paragraph break with normal spacing, got: {}",
            result
        );
    }

    #[test]
    fn test_unsorted_input() {
        let processor = LayoutProcessor::new();
        // 输入顺序打乱
        let boxes = vec![
            create_box("B2", 100.0, 50.0, 50.0, 30.0),
            create_box("A1", 0.0, 0.0, 50.0, 30.0),
            create_box("B1", 0.0, 50.0, 50.0, 30.0),
            create_box("A2", 100.0, 0.0, 50.0, 30.0),
        ];
        let result = processor.process(&boxes);
        let lines: Vec<&str> = result.lines().collect();
        assert_eq!(lines.len(), 2);
        // 第一行应该是 A1 A2
        assert!(lines[0].starts_with("A1"));
        // 第二行应该是 B1 B2
        assert!(lines[1].starts_with("B1"));
    }
}
