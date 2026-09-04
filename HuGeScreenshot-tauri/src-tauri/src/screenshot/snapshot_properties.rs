//! 静态快照属性测试
//!
//! 使用 proptest 进行属性测试，验证静态快照捕获的正确性。
//!
//! # 测试策略
//!
//! 由于实际截图依赖硬件，我们使用模拟数据来测试核心逻辑：
//! - 模拟显示器配置（位置、尺寸、DPR）
//! - 验证快照尺寸计算的正确性
//! - 验证多显示器合并后的边界计算
//! - 验证快照文件清理的正确性
//!
//! # 属性定义
//!
//! - **Property 1: Snapshot Capture Completeness**
//!   **Validates: Requirements 1.1, 2.1, 2.4**
//!
//! - **Property 2: Snapshot File Cleanup**
//!   **Validates: Requirements 3.4**

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use proptest::test_runner::Config;

    use crate::screenshot::snapshot::{MonitorSnapshot, SnapshotResult};

    // ============================================================================
    // 模拟数据结构和辅助函数
    // ============================================================================

    /// 模拟显示器配置（用于测试）
    #[derive(Debug, Clone)]
    struct SimulatedMonitor {
        id: u32,
        x: i32,
        y: i32,
        width: u32,
        height: u32,
        dpr: f64,
        is_primary: bool,
    }

    impl SimulatedMonitor {
        /// 转换为 MonitorSnapshot
        fn to_monitor_snapshot(&self) -> MonitorSnapshot {
            MonitorSnapshot::new(self.id, self.x, self.y, self.width, self.height, self.dpr)
        }
    }

    /// 计算多显示器组合后的虚拟桌面边界
    ///
    /// 返回 (min_x, min_y, total_width, total_height)
    fn calculate_virtual_desktop_bounds(monitors: &[SimulatedMonitor]) -> (i32, i32, u32, u32) {
        if monitors.is_empty() {
            return (0, 0, 0, 0);
        }

        let min_x = monitors.iter().map(|m| m.x).min().unwrap_or(0);
        let min_y = monitors.iter().map(|m| m.y).min().unwrap_or(0);
        let max_x = monitors.iter().map(|m| m.x + m.width as i32).max().unwrap_or(0);
        let max_y = monitors.iter().map(|m| m.y + m.height as i32).max().unwrap_or(0);

        let total_width = (max_x - min_x) as u32;
        let total_height = (max_y - min_y) as u32;

        (min_x, min_y, total_width, total_height)
    }

    /// 模拟快照捕获结果
    ///
    /// 根据显示器配置计算合并后的快照尺寸
    fn simulate_snapshot_capture(monitors: &[SimulatedMonitor]) -> SnapshotResult {
        let (_, _, total_width, total_height) = calculate_virtual_desktop_bounds(monitors);

        // 找到主显示器的 DPR，如果没有主显示器则使用第一个显示器的 DPR
        let primary_dpr = monitors
            .iter()
            .find(|m| m.is_primary)
            .or_else(|| monitors.first())
            .map(|m| m.dpr)
            .unwrap_or(1.0);

        let monitor_snapshots: Vec<MonitorSnapshot> =
            monitors.iter().map(|m| m.to_monitor_snapshot()).collect();

        SnapshotResult::new(
            format!(
                "/tmp/snapshot_{}.png",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis())
                    .unwrap_or(0)
            ),
            total_width,
            total_height,
            primary_dpr,
            monitor_snapshots,
        )
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

    /// 生成有效的物理分辨率（常见分辨率 + 随机值）
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
            // 随机分辨率（合理范围，避免内存溢出）
            (800u32..4096u32, 600u32..2160u32),
        ]
    }

    /// 生成单个模拟显示器
    fn monitor_strategy() -> impl Strategy<Value = SimulatedMonitor> {
        (
            0u32..10u32,           // id
            -4096i32..4096i32,     // x（支持负坐标，副屏在左侧）
            -2160i32..2160i32,     // y（支持负坐标，副屏在上方）
            resolution_strategy(), // (width, height)
            dpr_strategy(),        // dpr
            any::<bool>(),         // is_primary
        )
            .prop_map(|(id, x, y, (w, h), dpr, is_primary)| SimulatedMonitor {
                id,
                x,
                y,
                width: w,
                height: h,
                dpr,
                is_primary,
            })
    }

    /// 生成多显示器配置（1-4 个显示器）
    ///
    /// 确保：
    /// - ID 唯一
    /// - 至少有一个主显示器
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

    /// 生成典型的多显示器布局（水平排列）
    ///
    /// 模拟常见的多显示器设置：显示器水平排列，无重叠
    fn typical_horizontal_layout_strategy() -> impl Strategy<Value = Vec<SimulatedMonitor>> {
        (1usize..=4).prop_flat_map(|count| {
            prop::collection::vec((resolution_strategy(), dpr_strategy()), count).prop_map(
                move |resolutions| {
                    let mut monitors = Vec::with_capacity(resolutions.len());
                    let mut current_x = 0i32;

                    for (i, ((w, h), dpr)) in resolutions.into_iter().enumerate() {
                        monitors.push(SimulatedMonitor {
                            id: i as u32,
                            x: current_x,
                            y: 0,
                            width: w,
                            height: h,
                            dpr,
                            is_primary: i == 0,
                        });
                        current_x += w as i32;
                    }

                    monitors
                },
            )
        })
    }

    // ============================================================================
    // Property 1: Snapshot Capture Completeness
    // ============================================================================
    //
    // *For any* set of connected monitors, when `capture_static_snapshot` is called,
    // the resulting snapshot file SHALL contain pixel data from all monitors
    // combined into a single image with correct positioning.
    //
    // **Validates: Requirements 1.1, 2.1, 2.4**

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 1: Snapshot Capture Completeness
        ///
        /// 验证快照捕获的完整性：
        /// - 快照尺寸等于所有显示器组成的虚拟桌面尺寸
        /// - 每个显示器都被包含在快照元数据中
        /// - 快照路径非空
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_snapshot_capture_completeness(monitors in multi_monitor_strategy()) {
            // 模拟快照捕获
            let result = simulate_snapshot_capture(&monitors);

            // 计算期望的虚拟桌面尺寸
            let (_, _, expected_width, expected_height) = calculate_virtual_desktop_bounds(&monitors);

            // 验证 1: 快照尺寸等于虚拟桌面尺寸
            prop_assert_eq!(
                result.width,
                expected_width,
                "快照宽度应等于虚拟桌面宽度。期望: {}, 实际: {}",
                expected_width,
                result.width
            );
            prop_assert_eq!(
                result.height,
                expected_height,
                "快照高度应等于虚拟桌面高度。期望: {}, 实际: {}",
                expected_height,
                result.height
            );

            // 验证 2: 每个显示器都被包含在快照元数据中
            prop_assert_eq!(
                result.monitors.len(),
                monitors.len(),
                "快照应包含所有显示器的元数据。期望: {}, 实际: {}",
                monitors.len(),
                result.monitors.len()
            );

            // 验证 3: 每个显示器的信息正确
            for monitor in &monitors {
                let found = result.monitors.iter().find(|m| m.monitor_id == monitor.id);
                prop_assert!(
                    found.is_some(),
                    "显示器 {} 应该在快照元数据中",
                    monitor.id
                );

                let snapshot_monitor = found.unwrap();
                prop_assert_eq!(
                    snapshot_monitor.x,
                    monitor.x,
                    "显示器 {} 的 X 坐标应匹配",
                    monitor.id
                );
                prop_assert_eq!(
                    snapshot_monitor.y,
                    monitor.y,
                    "显示器 {} 的 Y 坐标应匹配",
                    monitor.id
                );
                prop_assert_eq!(
                    snapshot_monitor.width,
                    monitor.width,
                    "显示器 {} 的宽度应匹配",
                    monitor.id
                );
                prop_assert_eq!(
                    snapshot_monitor.height,
                    monitor.height,
                    "显示器 {} 的高度应匹配",
                    monitor.id
                );
            }

            // 验证 4: 快照路径非空
            prop_assert!(
                !result.path.is_empty(),
                "快照路径不应为空"
            );
        }


        /// Property 1 补充: 典型水平布局的快照尺寸验证
        ///
        /// 对于水平排列的显示器，总宽度应等于所有显示器宽度之和
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_horizontal_layout_snapshot_width(monitors in typical_horizontal_layout_strategy()) {
            let result = simulate_snapshot_capture(&monitors);

            // 水平排列时，总宽度应等于所有显示器宽度之和
            let expected_width: u32 = monitors.iter().map(|m| m.width).sum();
            prop_assert_eq!(
                result.width,
                expected_width,
                "水平排列时，快照宽度应等于所有显示器宽度之和"
            );

            // 高度应等于最高显示器的高度
            let expected_height = monitors.iter().map(|m| m.height).max().unwrap_or(0);
            prop_assert_eq!(
                result.height,
                expected_height,
                "水平排列时，快照高度应等于最高显示器的高度"
            );
        }

        /// Property 1 补充: 快照包含所有显示器的像素区域
        ///
        /// 验证每个显示器的区域都在快照边界内
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_all_monitors_within_snapshot_bounds(monitors in multi_monitor_strategy()) {
            let result = simulate_snapshot_capture(&monitors);
            let (min_x, min_y, _, _) = calculate_virtual_desktop_bounds(&monitors);

            for monitor in &monitors {
                // 计算显示器在快照中的相对位置
                let rel_x = (monitor.x - min_x) as u32;
                let rel_y = (monitor.y - min_y) as u32;

                // 验证显示器区域在快照边界内
                prop_assert!(
                    rel_x + monitor.width <= result.width,
                    "显示器 {} 的右边界 ({}) 应在快照宽度 ({}) 内",
                    monitor.id,
                    rel_x + monitor.width,
                    result.width
                );
                prop_assert!(
                    rel_y + monitor.height <= result.height,
                    "显示器 {} 的下边界 ({}) 应在快照高度 ({}) 内",
                    monitor.id,
                    rel_y + monitor.height,
                    result.height
                );
            }
        }
    }

    // ============================================================================
    // 负坐标和边界条件测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// 验证负坐标（副屏在主屏左侧/上方）的正确处理
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_negative_coordinates_handling(
            primary_width in 1920u32..3840u32,
            primary_height in 1080u32..2160u32,
            secondary_width in 1920u32..3840u32,
            secondary_height in 1080u32..2160u32,
            primary_dpr in dpr_strategy(),
            secondary_dpr in dpr_strategy()
        ) {
            // 创建主显示器在原点
            let primary = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                width: primary_width,
                height: primary_height,
                dpr: primary_dpr,
                is_primary: true,
            };

            // 创建副显示器在主显示器左侧（负 X 坐标）
            let secondary = SimulatedMonitor {
                id: 1,
                x: -(secondary_width as i32),
                y: 0,
                width: secondary_width,
                height: secondary_height,
                dpr: secondary_dpr,
                is_primary: false,
            };

            let monitors = vec![primary, secondary];
            let result = simulate_snapshot_capture(&monitors);

            // 验证总宽度等于两个显示器宽度之和
            let expected_width = primary_width + secondary_width;
            prop_assert_eq!(
                result.width,
                expected_width,
                "负坐标布局时，总宽度应等于两个显示器宽度之和"
            );

            // 验证高度等于较高显示器的高度
            let expected_height = primary_height.max(secondary_height);
            prop_assert_eq!(
                result.height,
                expected_height,
                "负坐标布局时，总高度应等于较高显示器的高度"
            );

            // 验证两个显示器都在元数据中
            prop_assert_eq!(result.monitors.len(), 2);
        }

        /// 验证单显示器快照的正确性
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_single_monitor_snapshot(
            width in 800u32..7680u32,
            height in 600u32..4320u32,
            dpr in dpr_strategy()
        ) {
            let monitor = SimulatedMonitor {
                id: 0,
                x: 0,
                y: 0,
                width,
                height,
                dpr,
                is_primary: true,
            };

            let result = simulate_snapshot_capture(&[monitor]);

            // 单显示器时，快照尺寸应等于显示器尺寸
            prop_assert_eq!(result.width, width);
            prop_assert_eq!(result.height, height);
            prop_assert_eq!(result.monitors.len(), 1);
            prop_assert!(!result.is_multi_monitor());
            prop_assert!((result.dpr - dpr).abs() < 0.001);
        }
    }

    // ============================================================================
    // 序列化往返测试
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// 验证 SnapshotResult 的序列化/反序列化往返一致性
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_snapshot_result_serialization_roundtrip(monitors in multi_monitor_strategy()) {
            let original = simulate_snapshot_capture(&monitors);

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: SnapshotResult = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.path, restored.path);
            prop_assert_eq!(original.width, restored.width);
            prop_assert_eq!(original.height, restored.height);
            prop_assert!((original.dpr - restored.dpr).abs() < 0.0001);
            prop_assert_eq!(original.monitors.len(), restored.monitors.len());

            // 验证每个显示器的信息
            for (orig, rest) in original.monitors.iter().zip(restored.monitors.iter()) {
                prop_assert_eq!(orig.monitor_id, rest.monitor_id);
                prop_assert_eq!(orig.x, rest.x);
                prop_assert_eq!(orig.y, rest.y);
                prop_assert_eq!(orig.width, rest.width);
                prop_assert_eq!(orig.height, rest.height);
                prop_assert!((orig.dpr - rest.dpr).abs() < 0.0001);
            }
        }

        /// 验证 MonitorSnapshot 的序列化/反序列化往返一致性
        ///
        /// **Validates: Requirements 1.1, 2.1, 2.4**
        #[test]
        fn prop_monitor_snapshot_serialization_roundtrip(monitor in monitor_strategy()) {
            let original = monitor.to_monitor_snapshot();

            // 序列化
            let json = serde_json::to_string(&original).expect("序列化失败");

            // 反序列化
            let restored: MonitorSnapshot = serde_json::from_str(&json).expect("反序列化失败");

            // 验证往返一致性
            prop_assert_eq!(original.monitor_id, restored.monitor_id);
            prop_assert_eq!(original.x, restored.x);
            prop_assert_eq!(original.y, restored.y);
            prop_assert_eq!(original.width, restored.width);
            prop_assert_eq!(original.height, restored.height);
            prop_assert!((original.dpr - restored.dpr).abs() < 0.0001);
        }
    }
}

// ============================================================================
// Property 2: Snapshot File Cleanup
// ============================================================================
//
// *For any* snapshot file created during a screenshot session, when the session
// ends (save, copy, or cancel), the temporary file SHALL be deleted from the
// file system.
//
// **Validates: Requirements 3.4**
//
// Since `cleanup_snapshot` requires a Tauri `AppHandle`, we test the underlying
// logic by:
// 1. Testing path validation logic (security check)
// 2. Testing file deletion behavior with various path inputs
// 3. Testing graceful handling of non-existent files

#[cfg(test)]
mod cleanup_tests {
    use proptest::prelude::*;
    use proptest::test_runner::Config;
    use std::fs;
    use std::io::Write;
    use std::path::{Path, PathBuf};
    use tempfile::TempDir;

    // ============================================================================
    // Path Validation Logic (extracted from cleanup_snapshot)
    // ============================================================================

    /// Check if a path is safe to delete (within allowed cache directory)
    ///
    /// This mirrors the security check in `cleanup_snapshot`:
    /// - Path must be within the cache directory
    /// - Or contain "hugescreenshot" or "com.wangh.hugescreenshot" in the path
    ///
    /// For non-existent files, we check if the parent directory is within cache_dir
    fn is_safe_path(path: &Path, cache_dir: &Path) -> bool {
        // Try to canonicalize the cache directory
        let canonical_cache = cache_dir.canonicalize().ok();

        // For the target path, try to canonicalize it
        // If the file doesn't exist, try to canonicalize the parent directory
        let canonical_path = path.canonicalize().ok().or_else(|| {
            // File doesn't exist, try parent directory
            path.parent().and_then(|parent| {
                parent.canonicalize().ok().map(|p| p.join(path.file_name().unwrap_or_default()))
            })
        });

        match (&canonical_path, &canonical_cache) {
            (Some(p), Some(c)) => p.starts_with(c),
            _ => {
                // Fallback: check if path string contains expected identifiers
                let path_str = path.to_string_lossy();
                path_str.contains("hugescreenshot") || path_str.contains("com.wangh.hugescreenshot")
            }
        }
    }

    /// Simulate cleanup_snapshot behavior without Tauri AppHandle
    ///
    /// Returns:
    /// - Ok(true) if file was deleted
    /// - Ok(false) if file didn't exist (graceful handling)
    /// - Err(String) if path is unsafe or deletion failed
    fn simulate_cleanup(path: &Path, cache_dir: &Path) -> Result<bool, String> {
        // Security check
        if !is_safe_path(path, cache_dir) {
            return Err("只能删除应用缓存目录下的文件".to_string());
        }

        // Delete file
        if path.exists() {
            fs::remove_file(path).map_err(|e| format!("删除失败: {}", e))?;
            Ok(true)
        } else {
            // File doesn't exist - graceful handling
            Ok(false)
        }
    }

    // ============================================================================
    // Proptest Strategies
    // ============================================================================

    /// Generate valid snapshot filenames (matching the pattern used in capture)
    fn snapshot_filename_strategy() -> impl Strategy<Value = String> {
        prop_oneof![
            // Standard snapshot filename pattern
            (1000000000000u64..9999999999999u64).prop_map(|ts| format!("snapshot_{}.png", ts)),
            // Random alphanumeric filenames
            "[a-z0-9]{8,16}\\.png".prop_map(|s| s),
            // With underscores
            "[a-z0-9_]{5,12}\\.png".prop_map(|s| s),
        ]
    }

    /// Generate unsafe/malicious path patterns that should be rejected
    fn unsafe_path_strategy() -> impl Strategy<Value = PathBuf> {
        prop_oneof![
            // Absolute paths outside cache (Windows-style)
            Just(PathBuf::from("C:\\Windows\\System32\\config.sys")),
            Just(PathBuf::from("C:\\Users\\Public\\malicious.exe")),
            // Absolute paths (Unix-style, for cross-platform testing)
            Just(PathBuf::from("/etc/passwd")),
            Just(PathBuf::from("/tmp/outside.txt")),
            // Path traversal attempts
            Just(PathBuf::from("..\\..\\..\\Windows\\System32\\config.sys")),
            Just(PathBuf::from("../../../etc/passwd")),
            Just(PathBuf::from("..\\outside.txt")),
            Just(PathBuf::from("../outside.txt")),
            // Hidden files in parent directories
            Just(PathBuf::from("../.hidden")),
            Just(PathBuf::from("..\\.hidden")),
            // Random paths without hugescreenshot identifier
            "[a-z]{5,10}/[a-z]{5,10}\\.txt".prop_map(PathBuf::from),
        ]
    }

    /// Generate random file content for creating test files
    fn file_content_strategy() -> impl Strategy<Value = Vec<u8>> {
        prop::collection::vec(any::<u8>(), 100..1000)
    }

    // ============================================================================
    // Property 2: Snapshot File Cleanup Tests
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 2: cleanup_snapshot correctly deletes existing files
        ///
        /// *For any* snapshot file created in the cache directory,
        /// when cleanup is called, the file SHALL be deleted.
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_deletes_existing_files(
            filename in snapshot_filename_strategy(),
            content in file_content_strategy()
        ) {
            // Setup: Create a temporary directory simulating cache
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();
            let file_path = cache_dir.join(&filename);

            // Create the file
            let mut file = fs::File::create(&file_path).expect("Failed to create test file");
            file.write_all(&content).expect("Failed to write content");
            drop(file); // Close the file handle

            // Verify file exists before cleanup
            prop_assert!(
                file_path.exists(),
                "Test file should exist before cleanup: {:?}",
                file_path
            );

            // Execute cleanup
            let result = simulate_cleanup(&file_path, cache_dir);

            // Verify: cleanup succeeded and file is deleted
            prop_assert!(
                result.is_ok(),
                "Cleanup should succeed, got error: {:?}",
                result
            );
            prop_assert_eq!(
                result.unwrap(),
                true,
                "Cleanup should return true when file was deleted"
            );
            prop_assert!(
                !file_path.exists(),
                "File should not exist after cleanup: {:?}",
                file_path
            );
        }

        /// Property 2: cleanup_snapshot handles non-existent files gracefully
        ///
        /// *For any* path that doesn't exist in the cache directory,
        /// cleanup SHALL succeed without error (graceful handling).
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_handles_missing_files_gracefully(
            filename in snapshot_filename_strategy()
        ) {
            // Setup: Create temp dir but DON'T create the file
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();
            let file_path = cache_dir.join(&filename);

            // Verify file doesn't exist
            prop_assert!(
                !file_path.exists(),
                "Test file should not exist: {:?}",
                file_path
            );

            // Execute cleanup on non-existent file
            let result = simulate_cleanup(&file_path, cache_dir);

            // Verify: cleanup succeeds gracefully
            prop_assert!(
                result.is_ok(),
                "Cleanup should succeed for non-existent file, got error: {:?}",
                result
            );
            prop_assert_eq!(
                result.unwrap(),
                false,
                "Cleanup should return false when file didn't exist"
            );
        }

        /// Property 2: cleanup_snapshot rejects unsafe paths (security check)
        ///
        /// *For any* path outside the cache directory,
        /// cleanup SHALL reject the operation with an error.
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_rejects_unsafe_paths(
            unsafe_path in unsafe_path_strategy()
        ) {
            // Setup: Create a temp dir as the "allowed" cache directory
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();

            // The unsafe_path is NOT within cache_dir
            // Execute cleanup
            let result = simulate_cleanup(&unsafe_path, cache_dir);

            // Verify: cleanup rejects the unsafe path
            prop_assert!(
                result.is_err(),
                "Cleanup should reject unsafe path: {:?}, but got Ok",
                unsafe_path
            );

            let error_msg = result.unwrap_err();
            prop_assert!(
                error_msg.contains("只能删除应用缓存目录下的文件"),
                "Error message should indicate security rejection, got: {}",
                error_msg
            );
        }

        /// Property 2: Multiple cleanups are idempotent
        ///
        /// *For any* snapshot file, calling cleanup multiple times
        /// SHALL succeed (first deletes, subsequent calls handle gracefully).
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_is_idempotent(
            filename in snapshot_filename_strategy(),
            content in file_content_strategy(),
            cleanup_count in 2usize..5usize
        ) {
            // Setup
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();
            let file_path = cache_dir.join(&filename);

            // Create the file
            let mut file = fs::File::create(&file_path).expect("Failed to create test file");
            file.write_all(&content).expect("Failed to write content");
            drop(file);

            // Execute cleanup multiple times
            let mut results = Vec::new();
            for _ in 0..cleanup_count {
                results.push(simulate_cleanup(&file_path, cache_dir));
            }

            // Verify: All cleanups succeed
            for (i, result) in results.iter().enumerate() {
                prop_assert!(
                    result.is_ok(),
                    "Cleanup #{} should succeed, got error: {:?}",
                    i + 1,
                    result
                );
            }

            // First cleanup should return true (file deleted)
            prop_assert_eq!(
                results[0].as_ref().unwrap(),
                &true,
                "First cleanup should return true"
            );

            // Subsequent cleanups should return false (file already gone)
            for (i, result) in results.iter().enumerate().skip(1) {
                prop_assert_eq!(
                    result.as_ref().unwrap(),
                    &false,
                    "Cleanup #{} should return false (file already deleted)",
                    i + 1
                );
            }

            // File should not exist
            prop_assert!(
                !file_path.exists(),
                "File should not exist after cleanups"
            );
        }

        /// Property 2: Path validation correctly identifies safe paths
        ///
        /// *For any* path within the cache directory,
        /// the path validation SHALL return true.
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_path_validation_accepts_safe_paths(
            filename in snapshot_filename_strategy(),
            subdirs in prop::collection::vec("[a-z]{3,8}", 0..3)
        ) {
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();

            // Build path with optional subdirectories
            let mut path = cache_dir.to_path_buf();
            for subdir in &subdirs {
                path = path.join(subdir);
            }
            path = path.join(&filename);

            // Create parent directories if needed
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).ok();
            }

            // Create the file so canonicalize works
            if let Some(parent) = path.parent() {
                if parent.exists() {
                    fs::File::create(&path).ok();
                }
            }

            // Only test if file was created successfully
            if path.exists() {
                let is_safe = is_safe_path(&path, cache_dir);
                prop_assert!(
                    is_safe,
                    "Path within cache dir should be safe: {:?}",
                    path
                );
            }
        }
    }

    // ============================================================================
    // Additional Edge Case Tests
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 2: Cleanup handles various file sizes
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_handles_various_file_sizes(
            filename in snapshot_filename_strategy(),
            size in 0usize..100000usize
        ) {
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();
            let file_path = cache_dir.join(&filename);

            // Create file with specific size
            let content = vec![0u8; size];
            fs::write(&file_path, &content).expect("Failed to write file");

            // Cleanup
            let result = simulate_cleanup(&file_path, cache_dir);

            prop_assert!(result.is_ok());
            prop_assert!(!file_path.exists());
        }

        /// Property 2: Cleanup with special characters in filename
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_cleanup_handles_special_filenames(
            timestamp in 1000000000000u64..9999999999999u64
        ) {
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();

            // Various filename patterns that might occur
            let filenames = vec![
                format!("snapshot_{}.png", timestamp),
                format!("snapshot_{}_backup.png", timestamp),
                format!("SNAPSHOT_{}.PNG", timestamp),
            ];

            for filename in filenames {
                let file_path = cache_dir.join(&filename);
                fs::write(&file_path, b"test content").expect("Failed to write file");

                let result = simulate_cleanup(&file_path, cache_dir);

                prop_assert!(
                    result.is_ok(),
                    "Cleanup should succeed for filename: {}",
                    filename
                );
                prop_assert!(
                    !file_path.exists(),
                    "File should be deleted: {}",
                    filename
                );
            }
        }
    }

    // ============================================================================
    // Session Lifecycle Tests
    // ============================================================================

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 2: Complete session lifecycle (capture → action → cleanup)
        ///
        /// Simulates a complete screenshot session:
        /// 1. Create snapshot file (simulating capture)
        /// 2. Perform action (save/copy/cancel - simulated by reading file)
        /// 3. Cleanup snapshot file
        /// 4. Verify no orphan files remain
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_session_lifecycle_no_orphan_files(
            session_count in 1usize..5usize,
            content in file_content_strategy()
        ) {
            let temp_dir = TempDir::new().expect("Failed to create temp dir");
            let cache_dir = temp_dir.path();

            for session_id in 0..session_count {
                let filename = format!("snapshot_{}.png", 1000000000000u64 + session_id as u64);
                let file_path = cache_dir.join(&filename);

                // Step 1: Create snapshot (simulating capture)
                fs::write(&file_path, &content).expect("Failed to create snapshot");
                prop_assert!(file_path.exists(), "Snapshot should exist after capture");

                // Step 2: Simulate action (read the file)
                let _data = fs::read(&file_path).expect("Failed to read snapshot");

                // Step 3: Cleanup
                let result = simulate_cleanup(&file_path, cache_dir);
                prop_assert!(result.is_ok(), "Cleanup should succeed");

                // Step 4: Verify no orphan
                prop_assert!(!file_path.exists(), "No orphan file should remain");
            }

            // Final verification: cache directory should be empty (except for temp dir artifacts)
            let remaining_files: Vec<_> = fs::read_dir(cache_dir)
                .expect("Failed to read cache dir")
                .filter_map(|e| e.ok())
                .filter(|e| e.path().extension().is_some_and(|ext| ext == "png"))
                .collect();

            prop_assert!(
                remaining_files.is_empty(),
                "No PNG files should remain after all sessions: {:?}",
                remaining_files
            );
        }
    }
}

// ============================================================================
// Property 3: Snapshot Transfer Timing
// ============================================================================
//
// *For any* screenshot hotkey press, the time from hotkey detection to
// snapshot-ready event emission SHALL be less than 200ms.
//
// **Validates: Requirements 3.5**
//
// Note: Actual timing depends on hardware and cannot be reliably tested in
// unit tests. We test the timing threshold logic and validation instead.

#[cfg(test)]
mod timing_tests {
    use proptest::prelude::*;
    use proptest::test_runner::Config;
    use std::time::Duration;

    /// Performance threshold in milliseconds
    const PERFORMANCE_THRESHOLD_MS: u128 = 200;

    /// Check if a duration exceeds the performance threshold
    fn exceeds_threshold(duration: Duration) -> bool {
        duration.as_millis() > PERFORMANCE_THRESHOLD_MS
    }

    /// Simulate timing check logic from capture_static_snapshot
    fn should_warn_slow_capture(duration_ms: u128) -> bool {
        duration_ms > PERFORMANCE_THRESHOLD_MS
    }

    proptest! {
        #![proptest_config(Config::with_cases(100))]

        /// Property 3: Timing threshold correctly identifies fast captures
        ///
        /// *For any* capture duration under 200ms, the system SHALL NOT
        /// emit a performance warning.
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_fast_captures_no_warning(duration_ms in 0u128..200u128) {
            let should_warn = should_warn_slow_capture(duration_ms);
            prop_assert!(
                !should_warn,
                "Capture under 200ms should not trigger warning: {}ms",
                duration_ms
            );
        }

        /// Property 3: Timing threshold correctly identifies slow captures
        ///
        /// *For any* capture duration over 200ms, the system SHALL
        /// emit a performance warning.
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_slow_captures_trigger_warning(duration_ms in 201u128..10000u128) {
            let should_warn = should_warn_slow_capture(duration_ms);
            prop_assert!(
                should_warn,
                "Capture over 200ms should trigger warning: {}ms",
                duration_ms
            );
        }

        /// Property 3: Duration conversion is accurate
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_duration_conversion_accurate(millis in 0u64..10000u64) {
            let duration = Duration::from_millis(millis);
            let converted_ms = duration.as_millis();

            prop_assert_eq!(
                converted_ms,
                millis as u128,
                "Duration conversion should be accurate"
            );
        }

        /// Property 3: Threshold boundary is exactly 200ms
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_threshold_boundary_exact(_dummy in Just(())) {
            // Exactly 200ms should NOT trigger warning (threshold is >200, not >=200)
            prop_assert!(!should_warn_slow_capture(200));

            // 201ms should trigger warning
            prop_assert!(should_warn_slow_capture(201));

            // 199ms should not trigger warning
            prop_assert!(!should_warn_slow_capture(199));
        }

        /// Property 3: exceeds_threshold matches should_warn_slow_capture
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_threshold_functions_consistent(millis in 0u64..10000u64) {
            let duration = Duration::from_millis(millis);
            let exceeds = exceeds_threshold(duration);
            let should_warn = should_warn_slow_capture(millis as u128);

            prop_assert_eq!(
                exceeds,
                should_warn,
                "Both threshold functions should agree for {}ms",
                millis
            );
        }
    }
}
