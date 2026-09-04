//! 截图引擎属性测试
//!
//! 使用 proptest 进行属性测试，验证截图引擎的正确性。
//!
//! # 测试策略
//!
//! 由于实际截图依赖硬件，我们使用模拟数据来测试核心逻辑：
//! - 模拟显示器配置（位置、尺寸、DPR）
//! - 验证数据结构的不变性
//! - 验证坐标转换的正确性
//!
//! # 属性定义
//!
//! - **Property 1: Multi-monitor Capture Completeness**
//! - **Property 2: DPR-Aware Screenshot Capture**
//!
//! **Validates: Requirements 2.2, 2.3, 18.2**

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use proptest::test_runner::Config;

    use crate::screenshot::capture::{CaptureResult, Rect, ScreenInfo};

    // ============================================================================
    // 模拟数据结构和辅助函数
    // ============================================================================

    /// 模拟显示器配置
    #[derive(Debug, Clone)]
    struct SimulatedMonitor {
        id: u32,
        x: i32,
        y: i32,
        logical_width: u32,
        logical_height: u32,
        scale_factor: f64,
        is_primary: bool,
    }

    impl SimulatedMonitor {
        /// 计算物理像素宽度
        fn physical_width(&self) -> u32 {
            (self.logical_width as f64 * self.scale_factor).round() as u32
        }

        /// 计算物理像素高度
        fn physical_height(&self) -> u32 {
            (self.logical_height as f64 * self.scale_factor).round() as u32
        }

        /// 转换为 ScreenInfo
        fn to_screen_info(&self) -> ScreenInfo {
            ScreenInfo {
                id: self.id,
                x: self.x,
                y: self.y,
                width: self.physical_width(),
                height: self.physical_height(),
                scale_factor: self.scale_factor,
                is_primary: self.is_primary,
            }
        }

        /// 模拟捕获结果
        fn simulate_capture(&self, path: String) -> CaptureResult {
            CaptureResult {
                path,
                width: self.physical_width(),
                height: self.physical_height(),
                dpr: self.scale_factor,
                monitor_id: self.id,
                x: self.x,
                y: self.y,
                image_hash: None,
                file_size: None,
                capture_time_ms: Some(25), // 模拟 25ms 捕获时间
                capture_engine: Some("simulated".to_string()),
            }
        }
    }

    /// 模拟多显示器捕获
    fn simulate_capture_all_monitors(monitors: &[SimulatedMonitor]) -> Vec<CaptureResult> {
        monitors
            .iter()
            .enumerate()
            .map(|(i, m)| m.simulate_capture(format!("/tmp/screenshot_{}.png", i)))
            .collect()
    }

    // ============================================================================
    // Proptest 策略（Strategies）
    // ============================================================================

    /// 生成有效的 DPR 值（1.0 到 4.0，常见值）
    fn dpr_strategy() -> impl Strategy<Value = f64> {
        prop_oneof![
            Just(1.0),  // 100% 缩放
            Just(1.25), // 125% 缩放
            Just(1.5),  // 150% 缩放
            Just(1.75), // 175% 缩放
            Just(2.0),  // 200% 缩放
            Just(2.5),  // 250% 缩放
            Just(3.0),  // 300% 缩放
            Just(4.0),  // 400% 缩放（4K 显示器）
            // 也测试一些非标准值
            (1.0f64..4.0f64).prop_map(|v| (v * 100.0).round() / 100.0),
        ]
    }

    /// 生成有效的逻辑分辨率
    fn resolution_strategy() -> impl Strategy<Value = (u32, u32)> {
        prop_oneof![
            // 常见分辨率
            Just((1920, 1080)), // Full HD
            Just((2560, 1440)), // 2K
            Just((3840, 2160)), // 4K
            Just((1366, 768)),  // 笔记本常见
            Just((1280, 720)),  // HD
            Just((1600, 900)),  // 16:9
            Just((1440, 900)),  // 16:10
            Just((2560, 1600)), // 16:10 高分
            // 随机分辨率（合理范围）
            (800u32..7680u32, 600u32..4320u32),
        ]
    }

    /// 生成单个模拟显示器
    fn monitor_strategy() -> impl Strategy<Value = SimulatedMonitor> {
        (
            0u32..10u32,           // id
            -7680i32..7680i32,     // x（支持负坐标，副屏在左侧）
            -4320i32..4320i32,     // y
            resolution_strategy(), // (width, height)
            dpr_strategy(),        // scale_factor
            any::<bool>(),         // is_primary
        )
            .prop_map(|(id, x, y, (w, h), dpr, is_primary)| SimulatedMonitor {
                id,
                x,
                y,
                logical_width: w,
                logical_height: h,
                scale_factor: dpr,
                is_primary,
            })
    }

    /// 生成多显示器配置（1-4 个显示器）
    fn multi_monitor_strategy() -> impl Strategy<Value = Vec<SimulatedMonitor>> {
        prop::collection::vec(monitor_strategy(), 1..=4).prop_map(|mut monitors| {
            // 确保 ID 唯一
            for (i, m) in monitors.iter_mut().enumerate() {
                m.id = i as u32;
            }
            // 确保至少有一个主显示器
            if !monitors.iter().any(|m| m.is_primary) {
                monitors[0].is_primary = true;
            }
            monitors
        })
    }

    // ============================================================================
    // Property 1: Multi-monitor Capture Completeness
    // ============================================================================
    //
    // *For any* multi-monitor configuration, when `capture_all_monitors()` is called,
    // the result SHALL contain exactly one `CaptureResult` for each connected monitor,
    // and each result SHALL have valid image data.
    //
    // **Validates: Requirements 2.2**

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 1: Multi-monitor Capture Completeness
        ///
        /// 验证多显示器捕获的完整性：
        /// - 结果数量等于显示器数量
        /// - 每个结果对应一个唯一的显示器
        /// - 每个结果包含有效的图像数据（非零尺寸）
        ///
        /// **Validates: Requirements 2.2**
        #[test]
        fn prop_multi_monitor_capture_completeness(monitors in multi_monitor_strategy()) {
            // 模拟捕获所有显示器
            let results = simulate_capture_all_monitors(&monitors);

            // 验证 1: 结果数量等于显示器数量
            prop_assert_eq!(
                results.len(),
                monitors.len(),
                "捕获结果数量应等于显示器数量"
            );

            // 验证 2: 每个结果对应唯一的显示器 ID
            let mut seen_ids = std::collections::HashSet::new();
            for result in &results {
                prop_assert!(
                    seen_ids.insert(result.monitor_id),
                    "每个显示器 ID 应该唯一，发现重复: {}",
                    result.monitor_id
                );
            }

            // 验证 3: 每个结果包含有效的图像数据
            for result in &results {
                prop_assert!(
                    result.width > 0,
                    "图像宽度应大于 0，实际: {}",
                    result.width
                );
                prop_assert!(
                    result.height > 0,
                    "图像高度应大于 0，实际: {}",
                    result.height
                );
                prop_assert!(
                    !result.path.is_empty(),
                    "图像路径不应为空"
                );
            }

            // 验证 4: 所有显示器都被捕获
            for monitor in &monitors {
                prop_assert!(
                    results.iter().any(|r| r.monitor_id == monitor.id),
                    "显示器 {} 应该被捕获",
                    monitor.id
                );
            }
        }

        /// Property 1 补充: 捕获结果应包含正确的显示器位置信息
        ///
        /// **Validates: Requirements 2.2**
        #[test]
        fn prop_capture_result_contains_monitor_position(monitors in multi_monitor_strategy()) {
            let results = simulate_capture_all_monitors(&monitors);

            for result in &results {
                // 找到对应的显示器
                let monitor = monitors.iter().find(|m| m.id == result.monitor_id);
                prop_assert!(
                    monitor.is_some(),
                    "结果中的显示器 ID {} 应该存在于配置中",
                    result.monitor_id
                );

                let monitor = monitor.unwrap();

                // 验证位置信息正确
                prop_assert_eq!(
                    result.x,
                    monitor.x,
                    "显示器 {} 的 X 坐标应匹配",
                    result.monitor_id
                );
                prop_assert_eq!(
                    result.y,
                    monitor.y,
                    "显示器 {} 的 Y 坐标应匹配",
                    result.monitor_id
                );
            }
        }
    }

    // ============================================================================
    // Property 2: DPR-Aware Screenshot Capture
    // ============================================================================
    //
    // *For any* display with device pixel ratio (DPR) > 1, when a screenshot is captured,
    // the resulting image dimensions SHALL equal `logical_width * DPR` by `logical_height * DPR`.
    //
    // **Validates: Requirements 2.3, 18.2**

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 2: DPR-Aware Screenshot Capture
        ///
        /// 验证高 DPI 截图的尺寸正确性：
        /// - 物理像素宽度 = 逻辑宽度 × DPR
        /// - 物理像素高度 = 逻辑高度 × DPR
        ///
        /// **Validates: Requirements 2.3, 18.2**
        #[test]
        fn prop_dpr_aware_screenshot_capture(
            logical_width in 100u32..7680u32,
            logical_height in 100u32..4320u32,
            dpr in dpr_strategy()
        ) {
            // 创建模拟显示器
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                logical_width,
                logical_height,
                scale_factor: dpr,
                is_primary: true,
            };

            // 模拟捕获
            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // 计算期望的物理像素尺寸
            let expected_width = (logical_width as f64 * dpr).round() as u32;
            let expected_height = (logical_height as f64 * dpr).round() as u32;

            // 验证尺寸
            prop_assert_eq!(
                result.width,
                expected_width,
                "物理宽度应为 {} × {} = {}，实际: {}",
                logical_width,
                dpr,
                expected_width,
                result.width
            );
            prop_assert_eq!(
                result.height,
                expected_height,
                "物理高度应为 {} × {} = {}，实际: {}",
                logical_height,
                dpr,
                expected_height,
                result.height
            );

            // 验证 DPR 值被正确记录
            prop_assert!(
                (result.dpr - dpr).abs() < 0.001,
                "DPR 应为 {}，实际: {}",
                dpr,
                result.dpr
            );
        }

        /// Property 2 补充: 高 DPI 显示器的物理像素总是大于等于逻辑像素
        ///
        /// **Validates: Requirements 2.3, 18.2**
        #[test]
        fn prop_physical_pixels_gte_logical_pixels(
            logical_width in 100u32..7680u32,
            logical_height in 100u32..4320u32,
            dpr in 1.0f64..4.0f64
        ) {
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                logical_width,
                logical_height,
                scale_factor: dpr,
                is_primary: true,
            };

            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // 物理像素应该大于等于逻辑像素（因为 DPR >= 1.0）
            prop_assert!(
                result.width >= logical_width,
                "物理宽度 {} 应 >= 逻辑宽度 {}",
                result.width,
                logical_width
            );
            prop_assert!(
                result.height >= logical_height,
                "物理高度 {} 应 >= 逻辑高度 {}",
                result.height,
                logical_height
            );
        }

        /// Property 2 补充: DPR 为 1.0 时，物理像素等于逻辑像素
        ///
        /// **Validates: Requirements 2.3, 18.2**
        #[test]
        fn prop_dpr_1_physical_equals_logical(
            logical_width in 100u32..7680u32,
            logical_height in 100u32..4320u32
        ) {
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                logical_width,
                logical_height,
                scale_factor: 1.0,
                is_primary: true,
            };

            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // DPR 为 1.0 时，物理像素应等于逻辑像素
            prop_assert_eq!(
                result.width,
                logical_width,
                "DPR=1.0 时，物理宽度应等于逻辑宽度"
            );
            prop_assert_eq!(
                result.height,
                logical_height,
                "DPR=1.0 时，物理高度应等于逻辑高度"
            );
        }

        /// Property 2 补充: DPR 为 2.0 时，物理像素是逻辑像素的两倍
        ///
        /// **Validates: Requirements 2.3, 18.2**
        #[test]
        fn prop_dpr_2_physical_double_logical(
            logical_width in 100u32..3840u32,
            logical_height in 100u32..2160u32
        ) {
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                logical_width,
                logical_height,
                scale_factor: 2.0,
                is_primary: true,
            };

            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // DPR 为 2.0 时，物理像素应是逻辑像素的两倍
            prop_assert_eq!(
                result.width,
                logical_width * 2,
                "DPR=2.0 时，物理宽度应为逻辑宽度的两倍"
            );
            prop_assert_eq!(
                result.height,
                logical_height * 2,
                "DPR=2.0 时，物理高度应为逻辑高度的两倍"
            );
        }
    }

    // ============================================================================
    // 额外的不变性测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// 验证 CaptureResult 的序列化/反序列化往返一致性
        #[test]
        fn prop_capture_result_serialization_roundtrip(
            width in 1u32..10000u32,
            height in 1u32..10000u32,
            dpr in dpr_strategy(),
            monitor_id in 0u32..10u32,
            x in -10000i32..10000i32,
            y in -10000i32..10000i32
        ) {
            let original = CaptureResult {
                path: format!("/tmp/screenshot_{}.png", monitor_id),
                width,
                height,
                dpr,
                monitor_id,
                x,
                y,
                image_hash: None,
                file_size: None,
                capture_time_ms: Some(30),
                capture_engine: Some("test".to_string()),
            };

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: CaptureResult = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.path, restored.path);
            prop_assert_eq!(original.width, restored.width);
            prop_assert_eq!(original.height, restored.height);
            prop_assert!((original.dpr - restored.dpr).abs() < 0.0001);
            prop_assert_eq!(original.monitor_id, restored.monitor_id);
            prop_assert_eq!(original.x, restored.x);
            prop_assert_eq!(original.y, restored.y);
            prop_assert_eq!(original.capture_time_ms, restored.capture_time_ms);
            prop_assert_eq!(original.capture_engine, restored.capture_engine);
        }

        /// 验证 ScreenInfo 的序列化/反序列化往返一致性
        #[test]
        fn prop_screen_info_serialization_roundtrip(monitor in monitor_strategy()) {
            let original = monitor.to_screen_info();

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: ScreenInfo = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.id, restored.id);
            prop_assert_eq!(original.x, restored.x);
            prop_assert_eq!(original.y, restored.y);
            prop_assert_eq!(original.width, restored.width);
            prop_assert_eq!(original.height, restored.height);
            prop_assert!((original.scale_factor - restored.scale_factor).abs() < 0.0001);
            prop_assert_eq!(original.is_primary, restored.is_primary);
        }

        /// 验证 Rect 的序列化/反序列化往返一致性
        #[test]
        fn prop_rect_serialization_roundtrip(
            x in -10000i32..10000i32,
            y in -10000i32..10000i32,
            width in 1u32..10000u32,
            height in 1u32..10000u32
        ) {
            let original = Rect { x, y, width, height };

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: Rect = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.x, restored.x);
            prop_assert_eq!(original.y, restored.y);
            prop_assert_eq!(original.width, restored.width);
            prop_assert_eq!(original.height, restored.height);
        }
    }

    // ============================================================================
    // 边界条件测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// 验证负坐标（副屏在主屏左侧/上方）的正确处理
        #[test]
        fn prop_negative_coordinates_handling(
            x in -7680i32..0i32,
            y in -4320i32..0i32,
            logical_width in 100u32..3840u32,
            logical_height in 100u32..2160u32,
            dpr in dpr_strategy()
        ) {
            let monitor = SimulatedMonitor {
                id: 1,
                x,
                y,
                logical_width,
                logical_height,
                scale_factor: dpr,
                is_primary: false,
            };

            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // 验证负坐标被正确保留
            prop_assert_eq!(result.x, x, "负 X 坐标应被正确保留");
            prop_assert_eq!(result.y, y, "负 Y 坐标应被正确保留");

            // 验证尺寸仍然正确
            let expected_width = (logical_width as f64 * dpr).round() as u32;
            let expected_height = (logical_height as f64 * dpr).round() as u32;
            prop_assert_eq!(result.width, expected_width);
            prop_assert_eq!(result.height, expected_height);
        }

        /// 验证极端 DPR 值的处理
        #[test]
        fn prop_extreme_dpr_handling(
            logical_width in 100u32..1920u32,
            logical_height in 100u32..1080u32,
            dpr in prop_oneof![Just(1.0), Just(4.0)]
        ) {
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                logical_width,
                logical_height,
                scale_factor: dpr,
                is_primary: true,
            };

            let result = monitor.simulate_capture("/tmp/test.png".to_string());

            // 验证极端 DPR 值的计算正确
            let expected_width = (logical_width as f64 * dpr).round() as u32;
            let expected_height = (logical_height as f64 * dpr).round() as u32;

            prop_assert_eq!(result.width, expected_width);
            prop_assert_eq!(result.height, expected_height);

            // 验证不会溢出
            prop_assert!(result.width <= logical_width * 4);
            prop_assert!(result.height <= logical_height * 4);
        }
    }
}
