//! OCR 面板焦点独立性和双向焦点切换属性测试
//!
//! 使用 proptest 进行属性测试，验证 OCR 面板创建时的焦点独立性和双向焦点切换。
//!
//! # 测试策略
//!
//! 由于实际窗口焦点依赖 GUI 系统，我们使用模拟数据来测试核心逻辑：
//! - 模拟窗口配置（标签、焦点状态、可见性）
//! - 验证 FocusState 序列化/反序列化的正确性
//! - 验证 OCR 面板创建配置的焦点独立性
//! - 验证焦点状态转换的不变性
//! - 验证双向焦点切换的正确性
//!
//! # 属性定义
//!
//! - **Property 4: OCR Panel Focus Independence**
//!
//! *For any* OCR panel creation from the overlay, the overlay window SHALL retain
//! its visible state and the OCR panel SHALL be created without automatically
//! receiving focus.
//!
//! **Validates: Requirements 4.1, 4.2**
//!
//! - **Property 5: Bidirectional Focus Switching**
//!
//! *For any* pair of (overlay, OCR panel) windows, clicking on either window SHALL
//! transfer focus to that window while the other remains visible and interactive.
//!
//! **Validates: Requirements 4.3, 4.4**

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use proptest::test_runner::Config;
    use serde::{Deserialize, Serialize};

    use crate::window::focus_manager::FocusState;

    // ============================================================================
    // 模拟数据结构和辅助函数
    // ============================================================================

    /// 模拟窗口配置（用于测试）
    #[derive(Debug, Clone, PartialEq)]
    struct SimulatedWindow {
        /// 窗口标签（唯一标识符）
        label: String,
        /// 是否可见
        visible: bool,
        /// 是否获得焦点
        focused: bool,
        /// 窗口类型
        window_type: WindowType,
    }

    /// 窗口类型
    #[derive(Debug, Clone, Copy, PartialEq)]
    enum WindowType {
        /// 截图覆盖窗口
        Overlay,
        /// OCR 结果面板
        OcrPanel,
    }

    /// OCR 面板创建配置
    #[derive(Debug, Clone, Serialize, Deserialize)]
    struct OcrPanelConfig {
        /// 窗口标签
        label: String,
        /// 是否自动获得焦点（应为 false）
        focused: bool,
        /// 是否可见
        visible: bool,
        /// 是否置顶
        always_on_top: bool,
    }

    impl OcrPanelConfig {
        /// 创建符合焦点独立性要求的 OCR 面板配置
        ///
        /// 根据 Property 4，OCR 面板创建时不应自动获得焦点
        fn new_no_focus(label: impl Into<String>) -> Self {
            Self {
                label: label.into(),
                focused: false, // 关键：不自动获得焦点
                visible: true,
                always_on_top: true,
            }
        }
    }

    /// 模拟多窗口系统状态
    #[derive(Debug, Clone)]
    struct WindowSystem {
        windows: Vec<SimulatedWindow>,
    }

    impl WindowSystem {
        fn new() -> Self {
            Self { windows: vec![] }
        }

        /// 添加覆盖窗口
        fn add_overlay(&mut self, label: &str) {
            self.windows.push(SimulatedWindow {
                label: label.to_string(),
                visible: true,
                focused: true,
                window_type: WindowType::Overlay,
            });
        }

        /// 创建 OCR 面板（不获取焦点）
        ///
        /// 根据 Property 4，OCR 面板创建时：
        /// - 覆盖窗口保持可见状态
        /// - OCR 面板不自动获得焦点
        fn create_ocr_panel_no_focus(&mut self, label: &str) -> OcrPanelConfig {
            let config = OcrPanelConfig::new_no_focus(label);

            self.windows.push(SimulatedWindow {
                label: config.label.clone(),
                visible: config.visible,
                focused: config.focused, // false
                window_type: WindowType::OcrPanel,
            });

            config
        }

        /// 获取覆盖窗口
        fn get_overlay(&self) -> Option<&SimulatedWindow> {
            self.windows.iter().find(|w| w.window_type == WindowType::Overlay)
        }

        /// 获取 OCR 面板
        fn get_ocr_panel(&self) -> Option<&SimulatedWindow> {
            self.windows.iter().find(|w| w.window_type == WindowType::OcrPanel)
        }

        /// 获取当前获得焦点的窗口数量
        fn focused_window_count(&self) -> usize {
            self.windows.iter().filter(|w| w.focused).count()
        }
    }

    // ============================================================================
    // Proptest 策略（Strategies）
    // ============================================================================

    /// 生成有效的窗口标签
    fn window_label_strategy() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("overlay-0".to_string()),
            Just("overlay-1".to_string()),
            Just("overlay-2".to_string()),
            Just("ocr-result".to_string()),
            Just("ocr-panel-0".to_string()),
            Just("ocr-panel-1".to_string()),
            Just("main".to_string()),
            // 也测试一些随机标签
            "[a-z][a-z0-9-]{0,20}".prop_map(|s| s),
        ]
    }

    /// 生成有效的时间戳
    fn timestamp_strategy() -> impl Strategy<Value = u64> {
        prop_oneof![Just(0u64), Just(1u64), Just(1234567890123u64), Just(u64::MAX), 0u64..u64::MAX,]
    }

    /// 生成 FocusState
    fn focus_state_strategy() -> impl Strategy<Value = FocusState> {
        (window_label_strategy(), any::<bool>(), timestamp_strategy()).prop_map(
            |(label, focused, timestamp)| FocusState {
                window_label: label,
                is_focused: focused,
                timestamp,
            },
        )
    }

    /// 生成多个覆盖窗口标签（模拟多显示器）
    fn overlay_labels_strategy() -> impl Strategy<Value = Vec<String>> {
        prop::collection::vec(0u32..10u32, 1..=4)
            .prop_map(|ids| ids.into_iter().map(|id| format!("overlay-{}", id)).collect())
    }

    /// 生成 OCR 面板标签
    fn ocr_panel_label_strategy() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("ocr-result".to_string()),
            (0u32..10u32).prop_map(|id| format!("ocr-panel-{}", id)),
        ]
    }

    // ============================================================================
    // Property 4: OCR Panel Focus Independence
    // ============================================================================
    //
    // *For any* OCR panel creation from the overlay, the overlay window SHALL
    // retain its visible state and the OCR panel SHALL be created without
    // automatically receiving focus.
    //
    // **Validates: Requirements 4.1, 4.2**

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 4: OCR 面板创建时不自动获得焦点
        ///
        /// 验证：当从覆盖窗口创建 OCR 面板时，OCR 面板的 focused 配置为 false
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_ocr_panel_created_without_focus(
            overlay_label in window_label_strategy(),
            ocr_label in ocr_panel_label_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 添加覆盖窗口（初始有焦点）
            system.add_overlay(&overlay_label);

            // 验证覆盖窗口初始状态
            let overlay_before = system.get_overlay().unwrap();
            prop_assert!(overlay_before.visible, "覆盖窗口应该可见");
            prop_assert!(overlay_before.focused, "覆盖窗口初始应有焦点");

            // 创建 OCR 面板（不获取焦点）
            let config = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证 1: OCR 面板配置的 focused 为 false
            prop_assert!(
                !config.focused,
                "OCR 面板创建配置的 focused 应为 false，实际为 {}",
                config.focused
            );

            // 验证 2: OCR 面板实际状态的 focused 为 false
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(
                !ocr_panel.focused,
                "OCR 面板不应自动获得焦点"
            );

            // 验证 3: OCR 面板应该可见
            prop_assert!(
                ocr_panel.visible,
                "OCR 面板应该可见"
            );
        }

        /// Property 4: 覆盖窗口在 OCR 面板创建后保持可见
        ///
        /// 验证：创建 OCR 面板后，覆盖窗口的可见状态不变
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_overlay_remains_visible_after_ocr_panel_creation(
            overlay_label in window_label_strategy(),
            ocr_label in ocr_panel_label_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 添加覆盖窗口
            system.add_overlay(&overlay_label);

            // 记录覆盖窗口创建前的可见状态
            let visible_before = system.get_overlay().unwrap().visible;

            // 创建 OCR 面板
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证覆盖窗口可见状态不变
            let overlay_after = system.get_overlay().unwrap();
            prop_assert_eq!(
                overlay_after.visible,
                visible_before,
                "覆盖窗口的可见状态应保持不变"
            );
            prop_assert!(
                overlay_after.visible,
                "覆盖窗口应保持可见"
            );
        }

        /// Property 4: 多显示器场景下的焦点独立性
        ///
        /// 验证：在多显示器场景下，创建 OCR 面板不影响任何覆盖窗口的可见性
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_multi_monitor_ocr_panel_focus_independence(
            overlay_labels in overlay_labels_strategy(),
            ocr_label in ocr_panel_label_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 添加多个覆盖窗口（模拟多显示器）
            for label in &overlay_labels {
                system.add_overlay(label);
            }

            // 记录所有覆盖窗口的可见状态
            let visible_states_before: Vec<bool> = system
                .windows
                .iter()
                .filter(|w| w.window_type == WindowType::Overlay)
                .map(|w| w.visible)
                .collect();

            // 创建 OCR 面板
            let config = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证 1: OCR 面板不自动获得焦点
            prop_assert!(
                !config.focused,
                "OCR 面板不应自动获得焦点"
            );

            // 验证 2: 所有覆盖窗口的可见状态保持不变
            let visible_states_after: Vec<bool> = system
                .windows
                .iter()
                .filter(|w| w.window_type == WindowType::Overlay)
                .map(|w| w.visible)
                .collect();

            // 验证 3: 所有覆盖窗口都应该可见
            for (i, visible) in visible_states_after.iter().enumerate() {
                prop_assert!(
                    *visible,
                    "覆盖窗口 {} 应保持可见",
                    i
                );
            }

            prop_assert_eq!(
                visible_states_before,
                visible_states_after,
                "所有覆盖窗口的可见状态应保持不变"
            );
        }

        /// Property 4: OcrPanelConfig 的 focused 字段始终为 false
        ///
        /// 验证：使用 new_no_focus 创建的配置，focused 始终为 false
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_ocr_panel_config_focused_always_false(
            label in ocr_panel_label_strategy()
        ) {
            let config = OcrPanelConfig::new_no_focus(&label);

            prop_assert!(
                !config.focused,
                "OcrPanelConfig::new_no_focus 创建的配置，focused 应始终为 false"
            );
            prop_assert!(
                config.visible,
                "OCR 面板应该可见"
            );
            prop_assert!(
                config.always_on_top,
                "OCR 面板应该置顶"
            );
            prop_assert_eq!(
                config.label,
                label,
                "标签应匹配"
            );
        }
    }

    // ============================================================================
    // FocusState 序列化/反序列化往返测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// FocusState 序列化/反序列化往返一致性
        ///
        /// 验证：FocusState 序列化后再反序列化，数据保持一致
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_focus_state_serialization_roundtrip(state in focus_state_strategy()) {
            // 序列化
            let json = serde_json::to_string(&state).expect("序列化失败");

            // 反序列化
            let restored: FocusState = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(
                state.window_label,
                restored.window_label,
                "window_label 应保持一致"
            );
            prop_assert_eq!(
                state.is_focused,
                restored.is_focused,
                "is_focused 应保持一致"
            );
            prop_assert_eq!(
                state.timestamp,
                restored.timestamp,
                "timestamp 应保持一致"
            );
        }

        /// FocusState 使用 camelCase 序列化
        ///
        /// 验证：FocusState 序列化时使用 camelCase 命名
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_focus_state_uses_camel_case(state in focus_state_strategy()) {
            let json = serde_json::to_string(&state).expect("序列化失败");

            // 验证使用 camelCase
            prop_assert!(
                json.contains("windowLabel"),
                "应使用 camelCase: windowLabel，实际 JSON: {}",
                json
            );
            prop_assert!(
                json.contains("isFocused"),
                "应使用 camelCase: isFocused，实际 JSON: {}",
                json
            );
            prop_assert!(
                json.contains("timestamp"),
                "应包含 timestamp，实际 JSON: {}",
                json
            );

            // 验证不使用 snake_case
            prop_assert!(
                !json.contains("window_label"),
                "不应使用 snake_case: window_label"
            );
            prop_assert!(
                !json.contains("is_focused"),
                "不应使用 snake_case: is_focused"
            );
        }

        /// FocusState::new 创建的状态时间戳有效
        ///
        /// 验证：使用 FocusState::new 创建的状态，时间戳大于 0
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_focus_state_new_has_valid_timestamp(
            label in window_label_strategy(),
            focused in any::<bool>()
        ) {
            let state = FocusState::new(&label, focused);

            prop_assert!(
                state.timestamp > 0,
                "FocusState::new 创建的状态，时间戳应大于 0"
            );
            prop_assert_eq!(
                state.window_label,
                label,
                "window_label 应匹配"
            );
            prop_assert_eq!(
                state.is_focused,
                focused,
                "is_focused 应匹配"
            );
        }
    }

    // ============================================================================
    // OcrPanelConfig 序列化/反序列化往返测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// OcrPanelConfig 序列化/反序列化往返一致性
        ///
        /// 验证：OcrPanelConfig 序列化后再反序列化，数据保持一致
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_ocr_panel_config_serialization_roundtrip(
            label in ocr_panel_label_strategy()
        ) {
            let original = OcrPanelConfig::new_no_focus(&label);

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: OcrPanelConfig = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.label, restored.label);
            prop_assert_eq!(original.focused, restored.focused);
            prop_assert_eq!(original.visible, restored.visible);
            prop_assert_eq!(original.always_on_top, restored.always_on_top);

            // 关键验证：focused 始终为 false
            prop_assert!(
                !restored.focused,
                "反序列化后 focused 应仍为 false"
            );
        }
    }

    // ============================================================================
    // 焦点状态不变性测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// 焦点排他性：系统中最多只有一个窗口有焦点
        ///
        /// 验证：在正常操作下，系统中最多只有一个窗口获得焦点
        /// （OCR 面板创建时不获取焦点，所以覆盖窗口保持焦点）
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_focus_exclusivity_after_ocr_panel_creation(
            overlay_label in window_label_strategy(),
            ocr_label in ocr_panel_label_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 添加覆盖窗口（有焦点）
            system.add_overlay(&overlay_label);

            // 创建 OCR 面板（不获取焦点）
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证：系统中只有一个窗口有焦点（覆盖窗口）
            let focused_count = system.focused_window_count();
            prop_assert_eq!(
                focused_count,
                1,
                "系统中应只有一个窗口有焦点，实际有 {} 个",
                focused_count
            );

            // 验证：有焦点的是覆盖窗口
            let overlay = system.get_overlay().unwrap();
            prop_assert!(
                overlay.focused,
                "覆盖窗口应保持焦点"
            );

            // 验证：OCR 面板没有焦点
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(
                !ocr_panel.focused,
                "OCR 面板不应有焦点"
            );
        }

        /// 窗口可见性不变性：创建 OCR 面板不影响其他窗口可见性
        ///
        /// **Validates: Requirements 4.1, 4.2**
        #[test]
        fn prop_visibility_invariant_after_ocr_panel_creation(
            overlay_labels in overlay_labels_strategy(),
            ocr_label in ocr_panel_label_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 添加多个覆盖窗口
            for label in &overlay_labels {
                system.add_overlay(label);
            }

            // 记录窗口数量
            let window_count_before = system.windows.len();

            // 创建 OCR 面板
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证：窗口数量增加 1
            prop_assert_eq!(
                system.windows.len(),
                window_count_before + 1,
                "窗口数量应增加 1"
            );

            // 验证：所有覆盖窗口仍然可见
            for window in &system.windows {
                if window.window_type == WindowType::Overlay {
                    prop_assert!(
                        window.visible,
                        "覆盖窗口 {} 应保持可见",
                        window.label
                    );
                }
            }

            // 验证：OCR 面板可见
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(
                ocr_panel.visible,
                "OCR 面板应可见"
            );
        }
    }

    // ============================================================================
    // Property 5: Bidirectional Focus Switching
    // ============================================================================
    //
    // *For any* pair of (overlay, OCR panel) windows, clicking on either window
    // SHALL transfer focus to that window while the other remains visible and
    // interactive.
    //
    // **Validates: Requirements 4.3, 4.4**

    impl WindowSystem {
        /// 模拟点击窗口获取焦点
        ///
        /// 根据 Property 5，点击任一窗口应：
        /// 1. 该窗口获得焦点
        /// 2. 其他窗口失去焦点但保持可见
        fn click_window(&mut self, label: &str) -> Option<FocusState> {
            // 找到目标窗口
            let target_exists = self.windows.iter().any(|w| w.label == label);
            if !target_exists {
                return None;
            }

            // 更新所有窗口的焦点状态
            for window in &mut self.windows {
                window.focused = window.label == label;
                // 关键：所有窗口保持可见
                // window.visible 不变
            }

            // 返回焦点变化事件
            Some(FocusState::new(label, true))
        }

        /// 获取当前有焦点的窗口标签
        fn get_focused_window_label(&self) -> Option<&str> {
            self.windows.iter().find(|w| w.focused).map(|w| w.label.as_str())
        }

        /// 检查所有窗口是否都可见
        fn all_windows_visible(&self) -> bool {
            self.windows.iter().all(|w| w.visible)
        }
    }

    /// 生成焦点切换序列（模拟用户在窗口间点击）
    fn focus_switch_sequence_strategy() -> impl Strategy<Value = Vec<bool>> {
        // true = 点击 overlay, false = 点击 OCR panel
        prop::collection::vec(any::<bool>(), 1..=20)
    }

    /// 生成不同的 overlay 和 OCR 面板标签对
    fn different_window_labels_strategy() -> impl Strategy<Value = (String, String)> {
        (window_label_strategy(), ocr_panel_label_strategy())
            .prop_filter("overlay 和 OCR 面板标签必须不同", |(overlay, ocr)| {
                overlay != ocr
            })
    }

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 5: 双向焦点切换 - 点击 overlay 获得焦点
        ///
        /// 验证：点击 overlay 窗口后，overlay 获得焦点，OCR 面板失去焦点但保持可见
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_click_overlay_transfers_focus(
            (overlay_label, ocr_label) in different_window_labels_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态：overlay 有焦点
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 模拟点击 OCR 面板（先让 OCR 获得焦点）
            system.click_window(&ocr_label);

            // 验证 OCR 面板现在有焦点
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(ocr_panel.focused, "点击后 OCR 面板应有焦点");

            // 模拟点击 overlay
            let focus_event = system.click_window(&overlay_label);

            // 验证 1: 返回了焦点事件
            prop_assert!(focus_event.is_some(), "应返回焦点事件");
            let event = focus_event.unwrap();
            prop_assert_eq!(event.window_label, overlay_label);
            prop_assert!(event.is_focused);

            // 验证 2: overlay 获得焦点
            let overlay = system.get_overlay().unwrap();
            prop_assert!(overlay.focused, "点击后 overlay 应有焦点");

            // 验证 3: OCR 面板失去焦点
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(!ocr_panel.focused, "点击 overlay 后 OCR 面板应失去焦点");

            // 验证 4: 两个窗口都保持可见
            prop_assert!(overlay.visible, "overlay 应保持可见");
            prop_assert!(ocr_panel.visible, "OCR 面板应保持可见");
        }

        /// Property 5: 双向焦点切换 - 点击 OCR 面板获得焦点
        ///
        /// 验证：点击 OCR 面板后，OCR 面板获得焦点，overlay 失去焦点但保持可见
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_click_ocr_panel_transfers_focus(
            (overlay_label, ocr_label) in different_window_labels_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态：overlay 有焦点
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 验证初始状态：overlay 有焦点，OCR 面板无焦点
            let overlay = system.get_overlay().unwrap();
            prop_assert!(overlay.focused, "初始状态 overlay 应有焦点");

            // 模拟点击 OCR 面板
            let focus_event = system.click_window(&ocr_label);

            // 验证 1: 返回了焦点事件
            prop_assert!(focus_event.is_some(), "应返回焦点事件");
            let event = focus_event.unwrap();
            prop_assert_eq!(event.window_label, ocr_label);
            prop_assert!(event.is_focused);

            // 验证 2: OCR 面板获得焦点
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(ocr_panel.focused, "点击后 OCR 面板应有焦点");

            // 验证 3: overlay 失去焦点
            let overlay = system.get_overlay().unwrap();
            prop_assert!(!overlay.focused, "点击 OCR 面板后 overlay 应失去焦点");

            // 验证 4: 两个窗口都保持可见
            prop_assert!(overlay.visible, "overlay 应保持可见");
            prop_assert!(ocr_panel.visible, "OCR 面板应保持可见");
        }

        /// Property 5: 多次焦点切换后窗口保持可见
        ///
        /// 验证：无论焦点如何切换，所有窗口始终保持可见
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_windows_remain_visible_after_multiple_focus_switches(
            (overlay_label, ocr_label) in different_window_labels_strategy(),
            switch_sequence in focus_switch_sequence_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 执行焦点切换序列
            for click_overlay in switch_sequence {
                let target = if click_overlay {
                    &overlay_label
                } else {
                    &ocr_label
                };
                system.click_window(target);

                // 每次切换后验证所有窗口可见
                prop_assert!(
                    system.all_windows_visible(),
                    "焦点切换后所有窗口应保持可见"
                );
            }

            // 最终验证
            let overlay = system.get_overlay().unwrap();
            let ocr_panel = system.get_ocr_panel().unwrap();
            prop_assert!(overlay.visible, "最终 overlay 应可见");
            prop_assert!(ocr_panel.visible, "最终 OCR 面板应可见");
        }

        /// Property 5: 焦点排他性 - 任意时刻只有一个窗口有焦点
        ///
        /// 验证：无论如何切换焦点，系统中始终只有一个窗口有焦点
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_focus_exclusivity_during_switching(
            (overlay_label, ocr_label) in different_window_labels_strategy(),
            switch_sequence in focus_switch_sequence_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 初始状态：只有 overlay 有焦点
            prop_assert_eq!(
                system.focused_window_count(),
                1,
                "初始状态应只有一个窗口有焦点"
            );

            // 执行焦点切换序列
            for click_overlay in switch_sequence {
                let target = if click_overlay {
                    &overlay_label
                } else {
                    &ocr_label
                };
                system.click_window(target);

                // 每次切换后验证焦点排他性
                prop_assert_eq!(
                    system.focused_window_count(),
                    1,
                    "焦点切换后应只有一个窗口有焦点"
                );
            }
        }

        /// Property 5: 焦点切换正确性 - 点击的窗口获得焦点
        ///
        /// 验证：点击哪个窗口，哪个窗口就获得焦点
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_clicked_window_gets_focus(
            (overlay_label, ocr_label) in different_window_labels_strategy(),
            switch_sequence in focus_switch_sequence_strategy()
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            // 执行焦点切换序列
            for click_overlay in switch_sequence {
                let target = if click_overlay {
                    &overlay_label
                } else {
                    &ocr_label
                };
                system.click_window(target);

                // 验证点击的窗口获得焦点
                let focused_label = system.get_focused_window_label();
                prop_assert!(focused_label.is_some(), "应有窗口获得焦点");
                prop_assert_eq!(
                    focused_label.unwrap(),
                    target.as_str(),
                    "点击的窗口应获得焦点"
                );
            }
        }

        /// Property 5: 焦点事件时间戳递增
        ///
        /// 验证：连续的焦点事件时间戳应该递增（或相等，如果在同一毫秒内）
        ///
        /// **Validates: Requirements 4.3, 4.4**
        #[test]
        fn prop_focus_event_timestamps_non_decreasing(
            (overlay_label, ocr_label) in different_window_labels_strategy(),
            switch_count in 2usize..10usize
        ) {
            let mut system = WindowSystem::new();

            // 设置初始状态
            system.add_overlay(&overlay_label);
            let _ = system.create_ocr_panel_no_focus(&ocr_label);

            let mut last_timestamp = 0u64;

            // 执行多次焦点切换
            for i in 0..switch_count {
                let target = if i % 2 == 0 {
                    &ocr_label
                } else {
                    &overlay_label
                };

                if let Some(event) = system.click_window(target) {
                    // 验证时间戳非递减
                    prop_assert!(
                        event.timestamp >= last_timestamp,
                        "焦点事件时间戳应非递减: {} >= {}",
                        event.timestamp,
                        last_timestamp
                    );
                    last_timestamp = event.timestamp;
                }
            }
        }
    }
}
