//! DB 后处理模块
//!
//! 实现 Differentiable Binarization (DB) 后处理算法，
//! 将检测模型输出的概率图转换为文本边界框。
//!
//! # 算法流程
//!
//! 1. 概率阈值化：将概率图二值化
//! 2. 连通区域分析：找到所有连通的文本区域
//! 3. 轮廓提取：提取每个区域的轮廓
//! 4. 多边形扩展（Unclipping）：扩展收缩的文本区域
//! 5. 边界框过滤：移除过小或置信度过低的区域
//!
//! # Requirements
//!
//! - 2.4: 输出文本区域边界框坐标
//!
//! # 参考
//!
//! - [DB Paper](https://arxiv.org/abs/1911.08947)
//! - [PaddleOCR DB Post-processing](https://github.com/PaddlePaddle/PaddleOCR)

use ndarray::Array4;

use super::types::{OcrError, TextBox};

/// DB 后处理器
///
/// 将检测模型输出的概率图转换为文本边界框。
#[derive(Debug, Clone)]
pub struct DBPostProcessor {
    /// 概率阈值（默认 0.3）
    ///
    /// 用于将概率图二值化，低于此值的像素被视为背景。
    threshold: f32,

    /// 边界框阈值（默认 0.6）
    ///
    /// 用于过滤低置信度的边界框。
    box_threshold: f32,

    /// 最小边界框面积（默认 3）
    ///
    /// 小于此面积的边界框将被过滤。
    min_area: f32,

    /// Unclip 比例（默认 1.5）
    ///
    /// 用于扩展收缩的文本区域。
    /// 公式：expansion_distance = (area * unclip_ratio) / perimeter
    unclip_ratio: f32,

    /// 最大候选框数量（默认 1000）
    max_candidates: usize,
}

impl Default for DBPostProcessor {
    /// 创建默认后处理器
    ///
    /// # 性能优化说明
    ///
    /// 默认参数已针对截图 OCR 场景优化：
    /// - `threshold: 0.3`：二值化阈值，保持较低以检测更多区域
    /// - `box_threshold: 0.5`（从 0.7 降低）：宁可多检测，不要漏检
    /// - `min_area: 10.0`（从 3.0 提高）：过滤过小的碎片区域
    ///
    /// # 准确性说明
    ///
    /// box_threshold 从 0.7 降到 0.5，减少文字漏检。
    /// 用户可以接受少量 OCR 错误，但不能接受文字缺失。
    fn default() -> Self {
        Self {
            threshold: 0.3,     // 二值化阈值
            box_threshold: 0.5, // 从 0.7 降低到 0.5，减少漏检
            min_area: 10.0,     // 从 3.0 提高到 10.0，过滤碎片
            unclip_ratio: 1.5,
            max_candidates: 1000,
        }
    }
}

impl DBPostProcessor {
    /// 创建新的后处理器
    pub fn new(
        threshold: f32,
        box_threshold: f32,
        min_area: f32,
        unclip_ratio: f32,
        max_candidates: usize,
    ) -> Self {
        Self { threshold, box_threshold, min_area, unclip_ratio, max_candidates }
    }

    /// 设置概率阈值（Builder 模式）
    pub fn with_threshold(mut self, threshold: f32) -> Self {
        self.threshold = threshold.clamp(0.0, 1.0);
        self
    }

    /// 设置边界框阈值（Builder 模式）
    pub fn with_box_threshold(mut self, threshold: f32) -> Self {
        self.box_threshold = threshold.clamp(0.0, 1.0);
        self
    }

    /// 设置最小面积（Builder 模式）
    pub fn with_min_area(mut self, area: f32) -> Self {
        self.min_area = area.max(0.0);
        self
    }

    /// 设置 Unclip 比例（Builder 模式）
    pub fn with_unclip_ratio(mut self, ratio: f32) -> Self {
        self.unclip_ratio = ratio.clamp(1.0, 3.0);
        self
    }

    /// 设置最大候选框数量（Builder 模式）
    pub fn with_max_candidates(mut self, max: usize) -> Self {
        self.max_candidates = max.max(1);
        self
    }

    /// 处理概率图，提取文本边界框
    ///
    /// # 参数
    ///
    /// - `prob_map`: 检测模型输出的概率图 [1, 1, H, W]
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<TextBox>)`: 提取的文本边界框列表
    /// - `Err(OcrError)`: 处理失败
    pub fn process(&self, prob_map: &Array4<f32>) -> Result<Vec<TextBox>, OcrError> {
        let shape = prob_map.shape();
        if shape.len() != 4 || shape[0] != 1 || shape[1] != 1 {
            return Err(OcrError::ImageProcessError(format!(
                "Invalid probability map shape: {:?}, expected [1, 1, H, W]",
                shape
            )));
        }

        let height = shape[2];
        let width = shape[3];

        // 1. 二值化
        let binary_map = self.binarize(prob_map, height, width);

        // 2. 查找轮廓
        let contours = self.find_contours(&binary_map, width, height);

        // 3. 处理每个轮廓，生成边界框
        let mut boxes = Vec::new();
        for contour in contours.iter().take(self.max_candidates) {
            if let Some(bbox) = self.contour_to_box(contour, prob_map, width, height) {
                boxes.push(bbox);
            }
        }

        // 4. 按阅读顺序排序（从上到下，从左到右）
        // 这样 OCR 结果的顺序与原图中文本的视觉顺序一致
        boxes.sort_by(|a, b| {
            let (ax, ay, _, _) = a.bounding_rect();
            let (bx, by, _, _) = b.bounding_rect();

            // 首先按 Y 坐标分行（容差 10 像素），再按 X 坐标排序
            // 使用 total_cmp 保证全序，避免排序比较器 panic
            let y_tolerance = 10.0f32;
            let ay_bucket =
                if ay.is_finite() { (ay / y_tolerance).floor() as i32 } else { i32::MAX };
            let by_bucket =
                if by.is_finite() { (by / y_tolerance).floor() as i32 } else { i32::MAX };

            ay_bucket
                .cmp(&by_bucket)
                .then_with(|| ax.total_cmp(&bx))
                .then_with(|| ay.total_cmp(&by))
        });

        Ok(boxes)
    }

    /// 二值化概率图
    fn binarize(&self, prob_map: &Array4<f32>, height: usize, width: usize) -> Vec<u8> {
        let mut binary = vec![0u8; width * height];

        for y in 0..height {
            for x in 0..width {
                let prob = prob_map[[0, 0, y, x]];
                if prob > self.threshold {
                    binary[y * width + x] = 255;
                }
            }
        }

        binary
    }

    /// 查找连通区域轮廓
    ///
    /// 使用简单的连通区域标记算法。
    fn find_contours(&self, binary: &[u8], width: usize, height: usize) -> Vec<Vec<[f32; 2]>> {
        // 使用 flood fill 算法查找连通区域
        let mut visited = vec![false; width * height];
        let mut contours = Vec::new();

        for y in 0..height {
            for x in 0..width {
                let idx = y * width + x;
                if binary[idx] == 255 && !visited[idx] {
                    // 找到新的连通区域
                    let (region_points, boundary) =
                        self.flood_fill(binary, &mut visited, x, y, width, height);

                    if !boundary.is_empty() {
                        // 计算区域面积
                        let area = region_points.len() as f32;
                        if area >= self.min_area {
                            contours.push(boundary);
                        }
                    }
                }
            }
        }

        contours
    }

    /// Flood fill 算法查找连通区域
    ///
    /// 返回 (区域内所有点, 边界点)
    fn flood_fill(
        &self,
        binary: &[u8],
        visited: &mut [bool],
        start_x: usize,
        start_y: usize,
        width: usize,
        height: usize,
    ) -> (Vec<[usize; 2]>, Vec<[f32; 2]>) {
        let mut region_points = Vec::new();
        let mut boundary_points = Vec::new();
        let mut stack = vec![(start_x, start_y)];

        while let Some((x, y)) = stack.pop() {
            let idx = y * width + x;
            if visited[idx] {
                continue;
            }
            visited[idx] = true;

            if binary[idx] == 255 {
                region_points.push([x, y]);

                // 检查是否是边界点（至少有一个邻居是背景）
                let is_boundary = self.is_boundary_point(binary, x, y, width, height);
                if is_boundary {
                    boundary_points.push([x as f32, y as f32]);
                }

                // 添加 4-邻域
                if x > 0 {
                    stack.push((x - 1, y));
                }
                if x + 1 < width {
                    stack.push((x + 1, y));
                }
                if y > 0 {
                    stack.push((x, y - 1));
                }
                if y + 1 < height {
                    stack.push((x, y + 1));
                }
            }
        }

        (region_points, boundary_points)
    }

    /// 检查点是否是边界点
    fn is_boundary_point(
        &self,
        binary: &[u8],
        x: usize,
        y: usize,
        width: usize,
        height: usize,
    ) -> bool {
        // 检查 8-邻域
        let neighbors = [
            (x.wrapping_sub(1), y.wrapping_sub(1)),
            (x, y.wrapping_sub(1)),
            (x + 1, y.wrapping_sub(1)),
            (x.wrapping_sub(1), y),
            (x + 1, y),
            (x.wrapping_sub(1), y + 1),
            (x, y + 1),
            (x + 1, y + 1),
        ];

        for (nx, ny) in neighbors {
            if nx >= width || ny >= height {
                return true; // 图像边缘
            }
            if binary[ny * width + nx] == 0 {
                return true; // 邻居是背景
            }
        }

        false
    }

    /// 将轮廓转换为边界框
    fn contour_to_box(
        &self,
        contour: &[[f32; 2]],
        prob_map: &Array4<f32>,
        width: usize,
        height: usize,
    ) -> Option<TextBox> {
        if contour.len() < 4 {
            return None;
        }

        // 计算最小外接矩形
        let rect = self.min_area_rect(contour);

        // 计算区域平均置信度
        let score = self.calculate_score(&rect, prob_map, width, height);

        if score < self.box_threshold {
            return None;
        }

        // 扩展边界框（Unclip）
        let expanded = self.unclip(&rect);

        Some(TextBox::new(expanded, score))
    }

    /// 计算最小外接矩形
    ///
    /// 返回四个角点坐标
    fn min_area_rect(&self, points: &[[f32; 2]]) -> [[f32; 2]; 4] {
        if points.is_empty() {
            return [[0.0, 0.0]; 4];
        }

        // NOTE: 当前使用轴对齐边界框，旋转矩形精度更高但实现复杂度较大
        let mut min_x = f32::INFINITY;
        let mut max_x = f32::NEG_INFINITY;
        let mut min_y = f32::INFINITY;
        let mut max_y = f32::NEG_INFINITY;

        for point in points {
            min_x = min_x.min(point[0]);
            max_x = max_x.max(point[0]);
            min_y = min_y.min(point[1]);
            max_y = max_y.max(point[1]);
        }

        [
            [min_x, min_y], // 左上
            [max_x, min_y], // 右上
            [max_x, max_y], // 右下
            [min_x, max_y], // 左下
        ]
    }

    /// 计算区域平均置信度
    fn calculate_score(
        &self,
        rect: &[[f32; 2]; 4],
        prob_map: &Array4<f32>,
        width: usize,
        height: usize,
    ) -> f32 {
        let min_x = rect[0][0].max(0.0) as usize;
        let max_x = (rect[1][0] as usize).min(width - 1);
        let min_y = rect[0][1].max(0.0) as usize;
        let max_y = (rect[2][1] as usize).min(height - 1);

        if min_x >= max_x || min_y >= max_y {
            return 0.0;
        }

        let mut sum = 0.0;
        let mut count = 0;

        for y in min_y..=max_y {
            for x in min_x..=max_x {
                sum += prob_map[[0, 0, y, x]];
                count += 1;
            }
        }

        if count > 0 {
            sum / count as f32
        } else {
            0.0
        }
    }

    /// 扩展边界框（Unclip）
    ///
    /// 使用 Vatti clipping 算法的简化版本扩展多边形。
    fn unclip(&self, rect: &[[f32; 2]; 4]) -> [[f32; 2]; 4] {
        // 计算面积和周长
        let width = rect[1][0] - rect[0][0];
        let height = rect[3][1] - rect[0][1];
        let area = width * height;
        let perimeter = 2.0 * (width + height);

        if perimeter <= 0.0 {
            return *rect;
        }

        // 计算扩展距离
        let distance = area * self.unclip_ratio / perimeter;

        // 扩展矩形
        [
            [rect[0][0] - distance, rect[0][1] - distance],
            [rect[1][0] + distance, rect[1][1] - distance],
            [rect[2][0] + distance, rect[2][1] + distance],
            [rect[3][0] - distance, rect[3][1] + distance],
        ]
    }
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array4;

    /// 创建测试用的概率图
    fn create_test_prob_map(width: usize, height: usize, value: f32) -> Array4<f32> {
        Array4::from_elem((1, 1, height, width), value)
    }

    /// 创建带有文本区域的概率图
    fn create_prob_map_with_region(
        width: usize,
        height: usize,
        region: (usize, usize, usize, usize), // (x, y, w, h)
        prob: f32,
    ) -> Array4<f32> {
        let mut map = Array4::zeros((1, 1, height, width));
        let (rx, ry, rw, rh) = region;

        for y in ry..(ry + rh).min(height) {
            for x in rx..(rx + rw).min(width) {
                map[[0, 0, y, x]] = prob;
            }
        }

        map
    }

    // ----------------------------------------
    // Default 和 Builder 测试
    // ----------------------------------------

    #[test]
    fn test_default_postprocessor() {
        let pp = DBPostProcessor::default();
        // 优化后的默认值（针对截图 OCR 场景）
        assert!((pp.threshold - 0.3).abs() < f32::EPSILON);
        assert!((pp.box_threshold - 0.5).abs() < f32::EPSILON);
        assert!((pp.min_area - 10.0).abs() < f32::EPSILON);
        assert!((pp.unclip_ratio - 1.5).abs() < f32::EPSILON);
        assert_eq!(pp.max_candidates, 1000);
    }

    #[test]
    fn test_builder_pattern() {
        let pp = DBPostProcessor::default()
            .with_threshold(0.5)
            .with_box_threshold(0.7)
            .with_min_area(10.0)
            .with_unclip_ratio(2.0)
            .with_max_candidates(500);

        assert!((pp.threshold - 0.5).abs() < f32::EPSILON);
        assert!((pp.box_threshold - 0.7).abs() < f32::EPSILON);
        assert!((pp.min_area - 10.0).abs() < f32::EPSILON);
        assert!((pp.unclip_ratio - 2.0).abs() < f32::EPSILON);
        assert_eq!(pp.max_candidates, 500);
    }

    #[test]
    fn test_builder_clamping() {
        let pp = DBPostProcessor::default()
            .with_threshold(1.5) // 应该被限制到 1.0
            .with_box_threshold(-0.5) // 应该被限制到 0.0
            .with_unclip_ratio(5.0); // 应该被限制到 3.0

        assert!((pp.threshold - 1.0).abs() < f32::EPSILON);
        assert!((pp.box_threshold - 0.0).abs() < f32::EPSILON);
        assert!((pp.unclip_ratio - 3.0).abs() < f32::EPSILON);
    }

    // ----------------------------------------
    // process 测试
    // ----------------------------------------

    #[test]
    fn test_process_empty_prob_map() {
        let pp = DBPostProcessor::default();
        let prob_map = create_test_prob_map(100, 100, 0.0);

        let result = pp.process(&prob_map).unwrap();
        assert!(result.is_empty(), "空概率图应该返回空结果");
    }

    #[test]
    fn test_process_full_prob_map() {
        let pp = DBPostProcessor::default().with_box_threshold(0.3);
        let prob_map = create_test_prob_map(100, 100, 0.8);

        let result = pp.process(&prob_map).unwrap();
        // 整个图像都是高概率，应该检测到一个大区域
        assert!(!result.is_empty(), "高概率图应该检测到区域");
    }

    #[test]
    fn test_process_with_region() {
        let pp = DBPostProcessor::default().with_threshold(0.3).with_box_threshold(0.5);

        // 创建一个 100x100 的概率图，中间有一个 20x10 的高概率区域
        let prob_map = create_prob_map_with_region(100, 100, (40, 45, 20, 10), 0.9);

        let result = pp.process(&prob_map).unwrap();
        assert!(!result.is_empty(), "应该检测到文本区域");

        // 验证检测到的区域大致在正确位置
        let bbox = &result[0];
        let (x, y, _, _) = bbox.bounding_rect();
        assert!((30.0..=50.0).contains(&x), "x 坐标应该接近 40");
        assert!((35.0..=55.0).contains(&y), "y 坐标应该接近 45");
    }

    #[test]
    fn test_process_invalid_shape() {
        let pp = DBPostProcessor::default();

        // 错误的形状
        let prob_map = Array4::zeros((2, 1, 100, 100)); // batch != 1
        let result = pp.process(&prob_map);
        assert!(result.is_err());

        let prob_map = Array4::zeros((1, 2, 100, 100)); // channels != 1
        let result = pp.process(&prob_map);
        assert!(result.is_err());
    }

    // ----------------------------------------
    // binarize 测试
    // ----------------------------------------

    #[test]
    fn test_binarize() {
        let pp = DBPostProcessor::default().with_threshold(0.5);
        let prob_map = create_prob_map_with_region(10, 10, (2, 2, 6, 6), 0.8);

        let binary = pp.binarize(&prob_map, 10, 10);

        // 检查区域内的像素
        assert_eq!(binary[2 * 10 + 2], 255); // (2, 2) 应该是 255
        assert_eq!(binary[5 * 10 + 5], 255); // (5, 5) 应该是 255

        // 检查区域外的像素
        assert_eq!(binary[0], 0); // (0, 0) 应该是 0
        assert_eq!(binary[9 * 10 + 9], 0); // (9, 9) 应该是 0
    }

    // ----------------------------------------
    // min_area_rect 测试
    // ----------------------------------------

    #[test]
    fn test_min_area_rect() {
        let pp = DBPostProcessor::default();

        let points = vec![[10.0, 20.0], [50.0, 20.0], [50.0, 40.0], [10.0, 40.0]];

        let rect = pp.min_area_rect(&points);

        assert!((rect[0][0] - 10.0).abs() < f32::EPSILON); // min_x
        assert!((rect[0][1] - 20.0).abs() < f32::EPSILON); // min_y
        assert!((rect[1][0] - 50.0).abs() < f32::EPSILON); // max_x
        assert!((rect[2][1] - 40.0).abs() < f32::EPSILON); // max_y
    }

    #[test]
    fn test_min_area_rect_empty() {
        let pp = DBPostProcessor::default();
        let points: Vec<[f32; 2]> = vec![];

        let rect = pp.min_area_rect(&points);

        // 空输入应该返回零矩形
        assert_eq!(rect, [[0.0, 0.0]; 4]);
    }

    // ----------------------------------------
    // unclip 测试
    // ----------------------------------------

    #[test]
    fn test_unclip() {
        let pp = DBPostProcessor::default().with_unclip_ratio(1.5);

        let rect = [[10.0, 10.0], [50.0, 10.0], [50.0, 30.0], [10.0, 30.0]];

        let expanded = pp.unclip(&rect);

        // 扩展后的矩形应该更大
        assert!(expanded[0][0] < rect[0][0]); // 左边界向左扩展
        assert!(expanded[1][0] > rect[1][0]); // 右边界向右扩展
        assert!(expanded[0][1] < rect[0][1]); // 上边界向上扩展
        assert!(expanded[2][1] > rect[2][1]); // 下边界向下扩展
    }

    // ----------------------------------------
    // calculate_score 测试
    // ----------------------------------------

    #[test]
    fn test_calculate_score() {
        let pp = DBPostProcessor::default();
        // 创建一个更大的区域确保完全覆盖测试矩形
        let prob_map = create_prob_map_with_region(100, 100, (19, 19, 22, 22), 0.9);

        let rect = [[20.0, 20.0], [40.0, 20.0], [40.0, 40.0], [20.0, 40.0]];

        let score = pp.calculate_score(&rect, &prob_map, 100, 100);

        // 区域内大部分是 0.9，平均分应该较高
        assert!(score > 0.5, "score should be > 0.5, got {}", score);
    }

    #[test]
    fn test_calculate_score_partial_overlap() {
        let pp = DBPostProcessor::default();
        let prob_map = create_prob_map_with_region(100, 100, (20, 20, 20, 20), 0.9);

        // 矩形只有一半在高概率区域内
        let rect = [[10.0, 20.0], [30.0, 20.0], [30.0, 40.0], [10.0, 40.0]];

        let score = pp.calculate_score(&rect, &prob_map, 100, 100);

        // 一半是 0.9，一半是 0.0，平均应该接近 0.45
        assert!(score > 0.3 && score < 0.6);
    }
}
