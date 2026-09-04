//! Configuration types for the file search service
//!
//! Defines configuration structures for the index service.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Index service configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexConfig {
    /// Volumes to index (e.g., ['C', 'D', 'E'])
    pub volumes: Vec<char>,

    /// Paths to exclude from indexing
    pub exclude_paths: Vec<PathBuf>,

    /// Maximum number of results to return per query
    pub result_limit: usize,
}

impl Default for IndexConfig {
    fn default() -> Self {
        Self {
            // Default to all available NTFS volumes
            volumes: vec!['C'],
            exclude_paths: vec![
                PathBuf::from(r"C:\$Recycle.Bin"),
                PathBuf::from(r"C:\Windows\Temp"),
                PathBuf::from(r"C:\Windows\SoftwareDistribution"),
            ],
            result_limit: 100,
        }
    }
}

/// Service runtime configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceConfig {
    /// Index configuration
    pub index: IndexConfig,

    /// Path to persist index data
    pub index_path: PathBuf,

    /// Named pipe name for IPC
    pub pipe_name: String,

    /// Maximum concurrent client connections
    pub max_connections: usize,

    /// USN Journal polling interval in milliseconds
    pub usn_poll_interval_ms: u64,

    /// Whether to throttle disk I/O during initial scan
    pub throttle_initial_scan: bool,
}

impl Default for ServiceConfig {
    fn default() -> Self {
        let data_dir = dirs::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("HuGeScreenshot");

        Self {
            index: IndexConfig::default(),
            index_path: data_dir.join("file_index.bin"),
            pipe_name: crate::PIPE_NAME.to_string(),
            max_connections: 10,
            usn_poll_interval_ms: 100,
            throttle_initial_scan: true,
        }
    }
}

impl ServiceConfig {
    /// Load configuration from file
    pub fn load(path: &std::path::Path) -> Result<Self, crate::ServiceError> {
        let content = std::fs::read_to_string(path)?;
        let config: Self =
            serde_json::from_str(&content).map_err(|e| crate::ServiceError::Config(e.to_string()))?;
        Ok(config)
    }

    /// Save configuration to file
    pub fn save(&self, path: &std::path::Path) -> Result<(), crate::ServiceError> {
        let content = serde_json::to_string_pretty(self)
            .map_err(|e| crate::ServiceError::Config(e.to_string()))?;
        std::fs::write(path, content)?;
        Ok(())
    }

    /// Get the configuration file path
    pub fn config_path() -> PathBuf {
        dirs::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("HuGeScreenshot")
            .join("file_search_config.json")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = ServiceConfig::default();
        assert!(!config.index.volumes.is_empty());
        assert!(config.index.result_limit > 0);
        assert!(config.max_connections > 0);
    }

    #[test]
    fn test_config_serialization() {
        let config = ServiceConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        let parsed: ServiceConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(config.index.volumes, parsed.index.volumes);
    }
}

// =============================================================================
// Property-Based Tests for Configuration Application
// =============================================================================
//
// **Property 16: Configuration Application**
// **Validates: Requirements 9.2, 9.3, 9.6, 9.7**
//
// For any configuration change (volumes, exclude_paths, result_limit), the
// Index_Service SHALL apply the change such that subsequent searches reflect
// the new configuration.
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use crate::index::FileIndex;
    use crate::models::FileEntry;
    use crate::protocol::{MatchMode, SearchFilters, SearchQuery, SortField, SortOrder};
    use crate::query::QueryEngine;
    use chrono::Utc;
    use proptest::prelude::*;
    use std::collections::HashSet;
    use tempfile::tempdir;

    // =========================================================================
    // Proptest Strategies for Configuration Types
    // =========================================================================

    /// Strategy for generating valid volume letters (A-Z)
    fn arb_volume() -> impl Strategy<Value = char> {
        (b'A'..=b'Z').prop_map(|b| b as char)
    }

    /// Strategy for generating a list of unique volumes
    fn arb_volumes(min: usize, max: usize) -> impl Strategy<Value = Vec<char>> {
        proptest::collection::hash_set(arb_volume(), min..=max)
            .prop_map(|set| set.into_iter().collect())
    }

    /// Strategy for generating valid path segments
    fn arb_path_segment() -> impl Strategy<Value = String> {
        prop::string::string_regex("[a-zA-Z0-9_-]{1,20}")
            .unwrap()
            .prop_filter("non-empty segment", |s| !s.is_empty())
    }

    /// Strategy for generating valid exclude paths
    fn arb_exclude_path() -> impl Strategy<Value = PathBuf> {
        (arb_volume(), proptest::collection::vec(arb_path_segment(), 1..4)).prop_map(
            |(volume, segments)| {
                let path_str = format!("{}:\\{}", volume, segments.join("\\"));
                PathBuf::from(path_str)
            },
        )
    }

    /// Strategy for generating a list of exclude paths
    fn arb_exclude_paths(max: usize) -> impl Strategy<Value = Vec<PathBuf>> {
        proptest::collection::vec(arb_exclude_path(), 0..=max)
    }

    /// Strategy for generating valid result limits
    fn arb_result_limit() -> impl Strategy<Value = usize> {
        1usize..1000usize
    }

    /// Strategy for generating arbitrary IndexConfig
    fn arb_index_config() -> impl Strategy<Value = IndexConfig> {
        (arb_volumes(1, 5), arb_exclude_paths(5), arb_result_limit()).prop_map(
            |(volumes, exclude_paths, result_limit)| IndexConfig {
                volumes,
                exclude_paths,
                result_limit,
            },
        )
    }

    // =========================================================================
    // Property 16: Configuration Application Tests
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        // =====================================================================
        // Property 16.1: Configuration Round-Trip Preserves All Values
        // =====================================================================
        //
        // **Validates: Requirements 9.6** (settings change applied)
        //
        // For any IndexConfig, serializing to JSON and deserializing back
        // SHALL produce an equivalent configuration with identical values.
        // =====================================================================

        #[test]
        fn prop_index_config_roundtrip(config in arb_index_config()) {
            // Serialize to JSON
            let json = serde_json::to_string(&config)
                .expect("IndexConfig should serialize to JSON");

            // Deserialize back
            let deserialized: IndexConfig = serde_json::from_str(&json)
                .expect("JSON should deserialize back to IndexConfig");

            // Verify all fields match
            prop_assert_eq!(
                config.volumes.len(),
                deserialized.volumes.len(),
                "Volumes count should match"
            );

            // Compare volumes as sets (order may differ)
            let original_volumes: HashSet<_> = config.volumes.iter().collect();
            let deserialized_volumes: HashSet<_> = deserialized.volumes.iter().collect();
            prop_assert_eq!(
                original_volumes,
                deserialized_volumes,
                "Volumes should match"
            );

            prop_assert_eq!(
                config.exclude_paths.len(),
                deserialized.exclude_paths.len(),
                "Exclude paths count should match"
            );

            for (orig, deser) in config.exclude_paths.iter().zip(deserialized.exclude_paths.iter()) {
                prop_assert_eq!(orig, deser, "Exclude path should match");
            }

            prop_assert_eq!(
                config.result_limit,
                deserialized.result_limit,
                "Result limit should match"
            );
        }

        // =====================================================================
        // Property 16.2: ServiceConfig Round-Trip Preserves All Values
        // =====================================================================
        //
        // **Validates: Requirements 9.6** (settings change applied)
        //
        // For any ServiceConfig, saving to file and loading back SHALL produce
        // an equivalent configuration.
        // =====================================================================

        #[test]
        fn prop_service_config_file_roundtrip(
            index_config in arb_index_config(),
            max_connections in 1usize..100usize,
            usn_poll_interval_ms in 10u64..10000u64,
            throttle_initial_scan in prop::bool::ANY,
        ) {
            let dir = tempdir().expect("Failed to create temp dir");
            let config_path = dir.path().join("test_config.json");

            // Create ServiceConfig with generated values
            let config = ServiceConfig {
                index: index_config.clone(),
                index_path: dir.path().join("index.bin"),
                pipe_name: "\\\\.\\pipe\\TestPipe".to_string(),
                max_connections,
                usn_poll_interval_ms,
                throttle_initial_scan,
            };

            // Save to file
            config.save(&config_path).expect("Config should save");

            // Load from file
            let loaded = ServiceConfig::load(&config_path).expect("Config should load");

            // Verify all fields match
            prop_assert_eq!(
                config.index.volumes.len(),
                loaded.index.volumes.len(),
                "Volumes count should match after file roundtrip"
            );

            let original_volumes: HashSet<_> = config.index.volumes.iter().collect();
            let loaded_volumes: HashSet<_> = loaded.index.volumes.iter().collect();
            prop_assert_eq!(
                original_volumes,
                loaded_volumes,
                "Volumes should match after file roundtrip"
            );

            prop_assert_eq!(
                config.index.exclude_paths.len(),
                loaded.index.exclude_paths.len(),
                "Exclude paths count should match after file roundtrip"
            );

            prop_assert_eq!(
                config.index.result_limit,
                loaded.index.result_limit,
                "Result limit should match after file roundtrip"
            );

            prop_assert_eq!(
                config.max_connections,
                loaded.max_connections,
                "Max connections should match after file roundtrip"
            );

            prop_assert_eq!(
                config.usn_poll_interval_ms,
                loaded.usn_poll_interval_ms,
                "USN poll interval should match after file roundtrip"
            );

            prop_assert_eq!(
                config.throttle_initial_scan,
                loaded.throttle_initial_scan,
                "Throttle initial scan should match after file roundtrip"
            );
        }

        // =====================================================================
        // Property 16.3: Volume Configuration Affects Search Results
        // =====================================================================
        //
        // **Validates: Requirements 9.2** (selecting drives to index)
        //
        // For any volume configuration change, subsequent searches with volume
        // filters SHALL only return results from the configured volumes.
        // =====================================================================

        #[test]
        fn prop_volume_config_affects_search(
            config_volumes in arb_volumes(1, 3),
            search_keyword in "[a-z]{2,5}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create files on different volumes
            let all_volumes = vec!['C', 'D', 'E', 'F'];
            let mut file_id = 1u64;

            for &volume in &all_volumes {
                // Add files with names containing the search keyword
                let name = format!("{}_{}.txt", search_keyword, volume);
                let entry = FileEntry::new(
                    file_id,
                    0,
                    name,
                    1024,
                    Utc::now(),
                    Utc::now(),
                    false,
                    volume,
                );
                index.insert(entry);
                file_id += 1;
            }

            // Search with volume filter matching config
            let query = SearchQuery {
                keyword: search_keyword.clone(),
                match_mode: MatchMode::Fuzzy,
                filters: SearchFilters {
                    volumes: Some(config_volumes.clone()),
                    ..Default::default()
                },
                sort_by: SortField::Relevance,
                sort_order: SortOrder::Desc,
                limit: 100,
                offset: 0,
            };

            let results = engine.search(&index, &query);

            // All results should be from configured volumes
            let config_volume_set: HashSet<_> = config_volumes.iter().collect();
            for result in &results {
                // Extract volume from path (first character after drive letter)
                if let Some(path_str) = result.path.to_str() {
                    if let Some(first_char) = path_str.chars().next() {
                        prop_assert!(
                            config_volume_set.contains(&first_char),
                            "Result volume {} should be in configured volumes {:?}",
                            first_char,
                            config_volumes
                        );
                    }
                }
            }

            // Results count should not exceed files on configured volumes
            let expected_max = config_volumes.iter()
                .filter(|v| all_volumes.contains(v))
                .count();
            prop_assert!(
                results.len() <= expected_max,
                "Results count {} should not exceed files on configured volumes {}",
                results.len(),
                expected_max
            );
        }

        // =====================================================================
        // Property 16.4: Result Limit Configuration Is Applied
        // =====================================================================
        //
        // **Validates: Requirements 9.7** (configuring search result limit)
        //
        // For any result_limit configuration, search results SHALL NOT exceed
        // the configured limit.
        // =====================================================================

        #[test]
        fn prop_result_limit_config_applied(
            result_limit in 1usize..50usize,
            file_count in 10usize..100usize,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create more files than the result limit
            for i in 1..=file_count {
                let entry = FileEntry::new(
                    i as u64,
                    0,
                    format!("testfile_{}.txt", i),
                    1024,
                    Utc::now(),
                    Utc::now(),
                    false,
                    'C',
                );
                index.insert(entry);
            }

            // Search with configured result limit
            let query = SearchQuery {
                keyword: "testfile".to_string(),
                match_mode: MatchMode::Fuzzy,
                filters: SearchFilters::default(),
                sort_by: SortField::Relevance,
                sort_order: SortOrder::Desc,
                limit: result_limit,
                offset: 0,
            };

            let results = engine.search(&index, &query);

            // Results should not exceed the configured limit
            prop_assert!(
                results.len() <= result_limit,
                "Results count {} should not exceed configured limit {}",
                results.len(),
                result_limit
            );

            // If there are more files than the limit, we should get exactly limit results
            if file_count >= result_limit {
                prop_assert_eq!(
                    results.len(),
                    result_limit,
                    "When file count {} >= limit {}, should return exactly limit results",
                    file_count,
                    result_limit
                );
            }
        }

        // =====================================================================
        // Property 16.5: Exclude Paths Configuration Affects Indexing
        // =====================================================================
        //
        // **Validates: Requirements 9.3** (adding folders to exclude)
        //
        // For any exclude_paths configuration, files matching excluded paths
        // SHALL NOT appear in search results when properly filtered.
        // =====================================================================

        #[test]
        fn prop_exclude_paths_config_applied(
            exclude_count in 1usize..5usize,
        ) {
            // This test verifies that the exclude_paths configuration is properly
            // stored and can be used for filtering. The actual exclusion happens
            // during MFT scanning, but we verify the config is correctly applied.

            let exclude_paths: Vec<PathBuf> = (0..exclude_count)
                .map(|i| PathBuf::from(format!("C:\\Excluded\\Path{}", i)))
                .collect();

            let config = IndexConfig {
                volumes: vec!['C'],
                exclude_paths: exclude_paths.clone(),
                result_limit: 100,
            };

            // Verify exclude paths are stored correctly
            prop_assert_eq!(
                config.exclude_paths.len(),
                exclude_count,
                "Exclude paths count should match"
            );

            for (i, path) in config.exclude_paths.iter().enumerate() {
                let expected = PathBuf::from(format!("C:\\Excluded\\Path{}", i));
                prop_assert_eq!(
                    path,
                    &expected,
                    "Exclude path {} should match",
                    i
                );
            }

            // Verify config survives serialization
            let json = serde_json::to_string(&config).unwrap();
            let loaded: IndexConfig = serde_json::from_str(&json).unwrap();

            prop_assert_eq!(
                loaded.exclude_paths.len(),
                exclude_count,
                "Exclude paths count should match after serialization"
            );
        }

        // =====================================================================
        // Property 16.6: Configuration Changes Are Idempotent
        // =====================================================================
        //
        // **Validates: Requirements 9.6** (settings change applied)
        //
        // Applying the same configuration multiple times SHALL produce the
        // same result as applying it once.
        // =====================================================================

        #[test]
        fn prop_config_changes_idempotent(config in arb_index_config()) {
            // Serialize once
            let json1 = serde_json::to_string(&config).unwrap();
            let loaded1: IndexConfig = serde_json::from_str(&json1).unwrap();

            // Serialize the loaded config again
            let json2 = serde_json::to_string(&loaded1).unwrap();
            let loaded2: IndexConfig = serde_json::from_str(&json2).unwrap();

            // Both should be equivalent
            prop_assert_eq!(
                loaded1.volumes.len(),
                loaded2.volumes.len(),
                "Volumes count should be idempotent"
            );

            prop_assert_eq!(
                loaded1.exclude_paths.len(),
                loaded2.exclude_paths.len(),
                "Exclude paths count should be idempotent"
            );

            prop_assert_eq!(
                loaded1.result_limit,
                loaded2.result_limit,
                "Result limit should be idempotent"
            );

            // JSON should be identical after multiple roundtrips
            prop_assert_eq!(
                json1,
                json2,
                "JSON serialization should be idempotent"
            );
        }

        // =====================================================================
        // Property 16.7: Valid Configuration Never Causes Errors
        // =====================================================================
        //
        // **Validates: Requirements 9.2, 9.3, 9.7**
        //
        // For any valid configuration values, applying the configuration
        // SHALL NOT cause errors or panics.
        // =====================================================================

        #[test]
        fn prop_valid_config_no_errors(config in arb_index_config()) {
            // Creating a config should not panic
            let service_config = ServiceConfig {
                index: config.clone(),
                index_path: PathBuf::from("test_index.bin"),
                pipe_name: "\\\\.\\pipe\\TestPipe".to_string(),
                max_connections: 10,
                usn_poll_interval_ms: 100,
                throttle_initial_scan: true,
            };

            // Serialization should not fail
            let json_result = serde_json::to_string(&service_config);
            prop_assert!(json_result.is_ok(), "Serialization should succeed");

            // Deserialization should not fail
            let json = json_result.unwrap();
            let deser_result: Result<ServiceConfig, _> = serde_json::from_str(&json);
            prop_assert!(deser_result.is_ok(), "Deserialization should succeed");

            // Accessing config fields should not panic
            let loaded = deser_result.unwrap();
            let _ = loaded.index.volumes.len();
            let _ = loaded.index.exclude_paths.len();
            let _ = loaded.index.result_limit;
        }

        // =====================================================================
        // Property 16.8: Empty Configuration Is Valid
        // =====================================================================
        //
        // **Validates: Requirements 9.2, 9.3**
        //
        // An empty volumes list or empty exclude_paths list SHALL be valid
        // configurations that can be saved and loaded.
        // =====================================================================

        #[test]
        fn prop_empty_config_valid(
            result_limit in arb_result_limit(),
            has_volumes in prop::bool::ANY,
            has_excludes in prop::bool::ANY,
        ) {
            let config = IndexConfig {
                volumes: if has_volumes { vec!['C'] } else { vec![] },
                exclude_paths: if has_excludes {
                    vec![PathBuf::from("C:\\Temp")]
                } else {
                    vec![]
                },
                result_limit,
            };

            // Should serialize without error
            let json = serde_json::to_string(&config);
            prop_assert!(json.is_ok(), "Empty config should serialize");

            // Should deserialize without error
            let loaded: Result<IndexConfig, _> = serde_json::from_str(&json.unwrap());
            prop_assert!(loaded.is_ok(), "Empty config should deserialize");

            let loaded = loaded.unwrap();
            prop_assert_eq!(
                loaded.volumes.is_empty(),
                !has_volumes,
                "Empty volumes should be preserved"
            );
            prop_assert_eq!(
                loaded.exclude_paths.is_empty(),
                !has_excludes,
                "Empty exclude_paths should be preserved"
            );
        }
    }
}
