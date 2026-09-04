//! IPC Protocol definitions for named pipe communication
//!
//! Defines the message format for communication between the main app and index service.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::config::IndexConfig;
use crate::models::IndexStats;

/// Request message from client to service
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Request {
    /// Search for files matching the query
    Search(SearchQuery),

    /// Get current service status
    GetStatus,

    /// Trigger a full index rebuild
    RebuildIndex,

    /// Update service configuration
    UpdateConfig(IndexConfig),

    /// Cancel the current operation
    Cancel,
}

/// Response message from service to client
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Response {
    /// Search results
    SearchResult {
        results: Vec<SearchResult>,
        total_count: u64,
        search_time_ms: u64,
    },

    /// Service status
    Status(ServiceStatus),

    /// Operation completed successfully
    Ok,

    /// Error occurred
    Error { code: ErrorCode, message: String },
}

/// Search query parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchQuery {
    /// Search keyword
    pub keyword: String,

    /// Matching mode
    pub match_mode: MatchMode,

    /// Search filters
    pub filters: SearchFilters,

    /// Sort field
    pub sort_by: SortField,

    /// Sort order
    pub sort_order: SortOrder,

    /// Maximum results to return
    pub limit: usize,

    /// Offset for pagination
    pub offset: usize,
}

impl Default for SearchQuery {
    fn default() -> Self {
        Self {
            keyword: String::new(),
            match_mode: MatchMode::Fuzzy,
            filters: SearchFilters::default(),
            sort_by: SortField::Relevance,
            sort_order: SortOrder::Desc,
            limit: 100,
            offset: 0,
        }
    }
}

/// Search matching mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MatchMode {
    /// Exact string match
    Exact,

    /// Wildcard matching (* and ?)
    Wildcard,

    /// Fuzzy matching (typo-tolerant)
    Fuzzy,

    /// Regular expression matching
    Regex,
}

/// Search filters
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SearchFilters {
    /// Filter by file extensions (e.g., ["pdf", "doc", "txt"])
    pub extensions: Option<Vec<String>>,

    /// Minimum file size in bytes
    pub min_size: Option<u64>,

    /// Maximum file size in bytes
    pub max_size: Option<u64>,

    /// Modified after this time
    pub modified_after: Option<DateTime<Utc>>,

    /// Modified before this time
    pub modified_before: Option<DateTime<Utc>>,

    /// Include directories in results
    pub include_directories: bool,

    /// Limit search to specific volumes
    pub volumes: Option<Vec<char>>,
}

/// Sort field for search results
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SortField {
    /// Sort by relevance score
    Relevance,

    /// Sort by file name
    Name,

    /// Sort by full path
    Path,

    /// Sort by file size
    Size,

    /// Sort by modification time
    Modified,
}

/// Sort order
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SortOrder {
    /// Ascending order
    Asc,

    /// Descending order
    Desc,
}

/// A single search result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    /// File ID
    pub file_id: u64,

    /// File name
    pub name: String,

    /// Full file path
    pub path: PathBuf,

    /// File size in bytes
    pub size: u64,

    /// Last modification time
    pub modified: DateTime<Utc>,

    /// Whether this is a directory
    pub is_directory: bool,

    /// Relevance score (higher is better)
    pub score: i64,

    /// Match positions in the name for highlighting
    /// Each tuple is (start_index, end_index)
    pub match_indices: Vec<(usize, usize)>,
}

/// Service status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ServiceStatus {
    /// Service is starting up
    Starting,

    /// Service is running normally
    Running {
        indexed_files: u64,
        last_update: DateTime<Utc>,
    },

    /// Service is scanning/indexing
    Scanning { progress: f32, scanned_files: u64 },

    /// Service is stopping
    Stopping,

    /// Service is stopped
    Stopped,
}

/// Error codes for error responses
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ErrorCode {
    /// Index is not ready (still scanning)
    NotReady,

    /// Invalid query syntax
    InvalidQuery,

    /// Operation timed out
    Timeout,

    /// Internal service error
    InternalError,

    /// Permission denied
    PermissionDenied,

    /// Service is shutting down
    ShuttingDown,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_request_serialization() {
        let request = Request::Search(SearchQuery::default());
        let json = serde_json::to_string(&request).unwrap();
        let parsed: Request = serde_json::from_str(&json).unwrap();

        match parsed {
            Request::Search(query) => {
                assert_eq!(query.limit, 100);
            }
            _ => panic!("Expected Search request"),
        }
    }

    #[test]
    fn test_response_serialization() {
        let response = Response::SearchResult {
            results: vec![],
            total_count: 0,
            search_time_ms: 5,
        };
        let json = serde_json::to_string(&response).unwrap();
        let parsed: Response = serde_json::from_str(&json).unwrap();

        match parsed {
            Response::SearchResult { search_time_ms, .. } => {
                assert_eq!(search_time_ms, 5);
            }
            _ => panic!("Expected SearchResult response"),
        }
    }

    #[test]
    fn test_all_request_variants() {
        let requests = vec![
            Request::Search(SearchQuery::default()),
            Request::GetStatus,
            Request::RebuildIndex,
            Request::UpdateConfig(IndexConfig::default()),
            Request::Cancel,
        ];

        for request in requests {
            let json = serde_json::to_string(&request).unwrap();
            let _: Request = serde_json::from_str(&json).unwrap();
        }
    }

    #[test]
    fn test_all_response_variants() {
        let responses = vec![
            Response::SearchResult {
                results: vec![],
                total_count: 0,
                search_time_ms: 0,
            },
            Response::Status(ServiceStatus::Running {
                indexed_files: 1000,
                last_update: Utc::now(),
            }),
            Response::Ok,
            Response::Error {
                code: ErrorCode::NotReady,
                message: "Index not ready".to_string(),
            },
        ];

        for response in responses {
            let json = serde_json::to_string(&response).unwrap();
            let _: Response = serde_json::from_str(&json).unwrap();
        }
    }
}

// =============================================================================
// Property-Based Tests for Protocol Serialization
// =============================================================================
//
// **Property 5: Message Serialization Round-Trip**
// **Validates: Requirements 4.7**
//
// For any valid Request or Response message, serializing to JSON and
// deserializing back SHALL produce an equivalent message.
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use proptest::prelude::*;
    use std::path::PathBuf;

    // =========================================================================
    // Arbitrary Strategies for Protocol Types
    // =========================================================================

    /// Strategy for generating arbitrary MatchMode
    fn arb_match_mode() -> impl Strategy<Value = MatchMode> {
        prop_oneof![
            Just(MatchMode::Exact),
            Just(MatchMode::Wildcard),
            Just(MatchMode::Fuzzy),
            Just(MatchMode::Regex),
        ]
    }

    /// Strategy for generating arbitrary SortField
    fn arb_sort_field() -> impl Strategy<Value = SortField> {
        prop_oneof![
            Just(SortField::Relevance),
            Just(SortField::Name),
            Just(SortField::Path),
            Just(SortField::Size),
            Just(SortField::Modified),
        ]
    }

    /// Strategy for generating arbitrary SortOrder
    fn arb_sort_order() -> impl Strategy<Value = SortOrder> {
        prop_oneof![Just(SortOrder::Asc), Just(SortOrder::Desc),]
    }

    /// Strategy for generating arbitrary ErrorCode
    fn arb_error_code() -> impl Strategy<Value = ErrorCode> {
        prop_oneof![
            Just(ErrorCode::NotReady),
            Just(ErrorCode::InvalidQuery),
            Just(ErrorCode::Timeout),
            Just(ErrorCode::InternalError),
            Just(ErrorCode::PermissionDenied),
            Just(ErrorCode::ShuttingDown),
        ]
    }

    /// Strategy for generating arbitrary DateTime<Utc>
    /// Constrained to reasonable timestamp range to avoid edge cases
    fn arb_datetime() -> impl Strategy<Value = DateTime<Utc>> {
        // Generate timestamps between 2000-01-01 and 2100-01-01
        (946684800i64..4102444800i64).prop_map(|ts| {
            DateTime::from_timestamp(ts, 0).unwrap_or_else(|| Utc::now())
        })
    }

    /// Strategy for generating arbitrary volume letters (A-Z)
    fn arb_volume() -> impl Strategy<Value = char> {
        // proptest doesn't implement Strategy for RangeInclusive<char>
        // so we use u8 range and convert to char
        (b'A'..=b'Z').prop_map(|b| b as char)
    }

    /// Strategy for generating arbitrary file extensions
    fn arb_extension() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("txt".to_string()),
            Just("pdf".to_string()),
            Just("doc".to_string()),
            Just("docx".to_string()),
            Just("jpg".to_string()),
            Just("png".to_string()),
            Just("exe".to_string()),
            Just("rs".to_string()),
            Just("py".to_string()),
            Just("md".to_string()),
            "[a-z]{1,5}".prop_map(|s| s),
        ]
    }

    /// Strategy for generating arbitrary SearchFilters
    fn arb_search_filters() -> impl Strategy<Value = SearchFilters> {
        (
            proptest::option::of(proptest::collection::vec(arb_extension(), 0..5)),
            proptest::option::of(0u64..1_000_000_000u64),
            proptest::option::of(0u64..1_000_000_000u64),
            proptest::option::of(arb_datetime()),
            proptest::option::of(arb_datetime()),
            any::<bool>(),
            proptest::option::of(proptest::collection::vec(arb_volume(), 0..5)),
        )
            .prop_map(
                |(
                    extensions,
                    min_size,
                    max_size,
                    modified_after,
                    modified_before,
                    include_directories,
                    volumes,
                )| {
                    SearchFilters {
                        extensions,
                        min_size,
                        max_size,
                        modified_after,
                        modified_before,
                        include_directories,
                        volumes,
                    }
                },
            )
    }

    /// Strategy for generating arbitrary SearchQuery
    fn arb_search_query() -> impl Strategy<Value = SearchQuery> {
        (
            ".*",                              // keyword - any string
            arb_match_mode(),                  // match_mode
            arb_search_filters(),              // filters
            arb_sort_field(),                  // sort_by
            arb_sort_order(),                  // sort_order
            1usize..1000usize,                 // limit (reasonable range)
            0usize..10000usize,                // offset
        )
            .prop_map(
                |(keyword, match_mode, filters, sort_by, sort_order, limit, offset)| SearchQuery {
                    keyword,
                    match_mode,
                    filters,
                    sort_by,
                    sort_order,
                    limit,
                    offset,
                },
            )
    }

    /// Strategy for generating arbitrary PathBuf
    fn arb_pathbuf() -> impl Strategy<Value = PathBuf> {
        // Generate reasonable Windows-style paths
        (arb_volume(), proptest::collection::vec("[a-zA-Z0-9_-]{1,20}", 1..5)).prop_map(
            |(volume, segments)| {
                let path_str = format!("{}:\\{}", volume, segments.join("\\"));
                PathBuf::from(path_str)
            },
        )
    }

    /// Strategy for generating arbitrary IndexConfig
    fn arb_index_config() -> impl Strategy<Value = IndexConfig> {
        (
            proptest::collection::vec(arb_volume(), 1..5),
            proptest::collection::vec(arb_pathbuf(), 0..5),
            1usize..1000usize,
        )
            .prop_map(|(volumes, exclude_paths, result_limit)| IndexConfig {
                volumes,
                exclude_paths,
                result_limit,
            })
    }

    /// Strategy for generating arbitrary SearchResult
    fn arb_search_result() -> impl Strategy<Value = SearchResult> {
        (
            any::<u64>(),                      // file_id
            "[a-zA-Z0-9_.-]{1,50}",            // name
            arb_pathbuf(),                     // path
            any::<u64>(),                      // size
            arb_datetime(),                    // modified
            any::<bool>(),                     // is_directory
            any::<i64>(),                      // score
            proptest::collection::vec((0usize..100usize, 0usize..100usize), 0..10), // match_indices
        )
            .prop_map(
                |(file_id, name, path, size, modified, is_directory, score, match_indices)| {
                    SearchResult {
                        file_id,
                        name,
                        path,
                        size,
                        modified,
                        is_directory,
                        score,
                        match_indices,
                    }
                },
            )
    }

    /// Strategy for generating arbitrary ServiceStatus
    fn arb_service_status() -> impl Strategy<Value = ServiceStatus> {
        prop_oneof![
            Just(ServiceStatus::Starting),
            (any::<u64>(), arb_datetime()).prop_map(|(indexed_files, last_update)| {
                ServiceStatus::Running {
                    indexed_files,
                    last_update,
                }
            }),
            (0.0f32..1.0f32, any::<u64>()).prop_map(|(progress, scanned_files)| {
                ServiceStatus::Scanning {
                    progress,
                    scanned_files,
                }
            }),
            Just(ServiceStatus::Stopping),
            Just(ServiceStatus::Stopped),
        ]
    }

    /// Strategy for generating arbitrary Request
    fn arb_request() -> impl Strategy<Value = Request> {
        prop_oneof![
            arb_search_query().prop_map(Request::Search),
            Just(Request::GetStatus),
            Just(Request::RebuildIndex),
            arb_index_config().prop_map(Request::UpdateConfig),
            Just(Request::Cancel),
        ]
    }

    /// Strategy for generating arbitrary Response
    fn arb_response() -> impl Strategy<Value = Response> {
        prop_oneof![
            // SearchResult variant
            (
                proptest::collection::vec(arb_search_result(), 0..10),
                any::<u64>(),
                any::<u64>(),
            )
                .prop_map(|(results, total_count, search_time_ms)| {
                    Response::SearchResult {
                        results,
                        total_count,
                        search_time_ms,
                    }
                }),
            // Status variant
            arb_service_status().prop_map(Response::Status),
            // Ok variant
            Just(Response::Ok),
            // Error variant
            (arb_error_code(), ".*").prop_map(|(code, message)| Response::Error { code, message }),
        ]
    }

    // =========================================================================
    // Property Tests
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: Message Serialization Round-Trip for Request
        ///
        /// For any valid Request message, serializing to JSON and deserializing
        /// back SHALL produce an equivalent message.
        #[test]
        fn prop_request_serialization_roundtrip(request in arb_request()) {
            // Serialize to JSON
            let json = serde_json::to_string(&request)
                .expect("Request should serialize to JSON");

            // Deserialize back
            let deserialized: Request = serde_json::from_str(&json)
                .expect("JSON should deserialize back to Request");

            // Verify round-trip produces equivalent message
            // We serialize both again to compare, since Request doesn't implement PartialEq
            let json_original = serde_json::to_string(&request).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "Request round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: Message Serialization Round-Trip for Response
        ///
        /// For any valid Response message, serializing to JSON and deserializing
        /// back SHALL produce an equivalent message.
        #[test]
        fn prop_response_serialization_roundtrip(response in arb_response()) {
            // Serialize to JSON
            let json = serde_json::to_string(&response)
                .expect("Response should serialize to JSON");

            // Deserialize back
            let deserialized: Response = serde_json::from_str(&json)
                .expect("JSON should deserialize back to Response");

            // Verify round-trip produces equivalent message
            let json_original = serde_json::to_string(&response).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "Response round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: SearchQuery Serialization Round-Trip
        ///
        /// For any valid SearchQuery, serializing to JSON and deserializing
        /// back SHALL produce an equivalent query.
        #[test]
        fn prop_search_query_serialization_roundtrip(query in arb_search_query()) {
            let json = serde_json::to_string(&query)
                .expect("SearchQuery should serialize to JSON");

            let deserialized: SearchQuery = serde_json::from_str(&json)
                .expect("JSON should deserialize back to SearchQuery");

            let json_original = serde_json::to_string(&query).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "SearchQuery round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: SearchResult Serialization Round-Trip
        ///
        /// For any valid SearchResult, serializing to JSON and deserializing
        /// back SHALL produce an equivalent result.
        #[test]
        fn prop_search_result_serialization_roundtrip(result in arb_search_result()) {
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            let deserialized: SearchResult = serde_json::from_str(&json)
                .expect("JSON should deserialize back to SearchResult");

            let json_original = serde_json::to_string(&result).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "SearchResult round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: ServiceStatus Serialization Round-Trip
        ///
        /// For any valid ServiceStatus, serializing to JSON and deserializing
        /// back SHALL produce an equivalent status.
        #[test]
        fn prop_service_status_serialization_roundtrip(status in arb_service_status()) {
            let json = serde_json::to_string(&status)
                .expect("ServiceStatus should serialize to JSON");

            let deserialized: ServiceStatus = serde_json::from_str(&json)
                .expect("JSON should deserialize back to ServiceStatus");

            let json_original = serde_json::to_string(&status).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "ServiceStatus round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: IndexConfig Serialization Round-Trip
        ///
        /// For any valid IndexConfig, serializing to JSON and deserializing
        /// back SHALL produce an equivalent config.
        #[test]
        fn prop_index_config_serialization_roundtrip(config in arb_index_config()) {
            let json = serde_json::to_string(&config)
                .expect("IndexConfig should serialize to JSON");

            let deserialized: IndexConfig = serde_json::from_str(&json)
                .expect("JSON should deserialize back to IndexConfig");

            let json_original = serde_json::to_string(&config).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "IndexConfig round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: SearchFilters Serialization Round-Trip
        ///
        /// For any valid SearchFilters, serializing to JSON and deserializing
        /// back SHALL produce equivalent filters.
        #[test]
        fn prop_search_filters_serialization_roundtrip(filters in arb_search_filters()) {
            let json = serde_json::to_string(&filters)
                .expect("SearchFilters should serialize to JSON");

            let deserialized: SearchFilters = serde_json::from_str(&json)
                .expect("JSON should deserialize back to SearchFilters");

            let json_original = serde_json::to_string(&filters).unwrap();
            let json_roundtrip = serde_json::to_string(&deserialized).unwrap();
            prop_assert_eq!(json_original, json_roundtrip,
                "SearchFilters round-trip should produce equivalent JSON");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: All MatchMode variants serialize correctly
        #[test]
        fn prop_match_mode_serialization_roundtrip(mode in arb_match_mode()) {
            let json = serde_json::to_string(&mode)
                .expect("MatchMode should serialize to JSON");

            let deserialized: MatchMode = serde_json::from_str(&json)
                .expect("JSON should deserialize back to MatchMode");

            prop_assert_eq!(mode, deserialized,
                "MatchMode round-trip should produce equivalent value");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: All SortField variants serialize correctly
        #[test]
        fn prop_sort_field_serialization_roundtrip(field in arb_sort_field()) {
            let json = serde_json::to_string(&field)
                .expect("SortField should serialize to JSON");

            let deserialized: SortField = serde_json::from_str(&json)
                .expect("JSON should deserialize back to SortField");

            prop_assert_eq!(field, deserialized,
                "SortField round-trip should produce equivalent value");
        }

        /// **Validates: Requirements 4.7**
        ///
        /// Property 5: All ErrorCode variants serialize correctly
        #[test]
        fn prop_error_code_serialization_roundtrip(code in arb_error_code()) {
            let json = serde_json::to_string(&code)
                .expect("ErrorCode should serialize to JSON");

            let deserialized: ErrorCode = serde_json::from_str(&json)
                .expect("JSON should deserialize back to ErrorCode");

            prop_assert_eq!(code, deserialized,
                "ErrorCode round-trip should produce equivalent value");
        }

        // =====================================================================
        // Property 11: Search Response Completeness
        // **Feature: everything-file-search, Property 11: Search response completeness**
        // **Validates: Requirements 6.1, 6.7**
        //
        // For any search response, it SHALL contain all required fields:
        // results array, total_count, and search_time_ms.
        // Each result SHALL contain file_id, name, path, size, modified,
        // is_directory, score, and match_indices.
        // =====================================================================

        /// **Validates: Requirements 6.1, 6.7**
        ///
        /// Property 11: Search Response Contains All Required Fields
        ///
        /// For any SearchResult response, the serialized JSON SHALL contain
        /// all required top-level fields: results, total_count, search_time_ms.
        #[test]
        fn prop_search_response_contains_required_fields(
            results in proptest::collection::vec(arb_search_result(), 0..20),
            total_count in any::<u64>(),
            search_time_ms in any::<u64>(),
        ) {
            // Create a SearchResult response
            let response = Response::SearchResult {
                results,
                total_count,
                search_time_ms,
            };

            // Serialize to JSON
            let json = serde_json::to_string(&response)
                .expect("Response should serialize to JSON");

            // Parse as generic JSON Value to inspect structure
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            // Verify it's a SearchResult variant
            prop_assert!(value.get("SearchResult").is_some(),
                "Response should be SearchResult variant");

            let search_result = value.get("SearchResult").unwrap();

            // Verify all required top-level fields are present
            prop_assert!(search_result.get("results").is_some(),
                "SearchResult should contain 'results' field");
            prop_assert!(search_result.get("total_count").is_some(),
                "SearchResult should contain 'total_count' field");
            prop_assert!(search_result.get("search_time_ms").is_some(),
                "SearchResult should contain 'search_time_ms' field");

            // Verify results is an array
            prop_assert!(search_result.get("results").unwrap().is_array(),
                "'results' field should be an array");

            // Verify total_count is a number
            prop_assert!(search_result.get("total_count").unwrap().is_number(),
                "'total_count' field should be a number");

            // Verify search_time_ms is a number
            prop_assert!(search_result.get("search_time_ms").unwrap().is_number(),
                "'search_time_ms' field should be a number");
        }

        /// **Validates: Requirements 6.1, 6.7**
        ///
        /// Property 11: Each SearchResult Contains All Required Fields
        ///
        /// For any SearchResult in the results array, it SHALL contain all
        /// required fields: file_id, name, path, size, modified, is_directory,
        /// score, and match_indices.
        #[test]
        fn prop_each_search_result_contains_required_fields(
            result in arb_search_result(),
        ) {
            // Serialize the SearchResult to JSON
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            // Parse as generic JSON Value to inspect structure
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            // Verify all required fields are present
            prop_assert!(value.get("file_id").is_some(),
                "SearchResult should contain 'file_id' field");
            prop_assert!(value.get("name").is_some(),
                "SearchResult should contain 'name' field");
            prop_assert!(value.get("path").is_some(),
                "SearchResult should contain 'path' field");
            prop_assert!(value.get("size").is_some(),
                "SearchResult should contain 'size' field");
            prop_assert!(value.get("modified").is_some(),
                "SearchResult should contain 'modified' field");
            prop_assert!(value.get("is_directory").is_some(),
                "SearchResult should contain 'is_directory' field");
            prop_assert!(value.get("score").is_some(),
                "SearchResult should contain 'score' field");
            prop_assert!(value.get("match_indices").is_some(),
                "SearchResult should contain 'match_indices' field");

            // Verify field types
            prop_assert!(value.get("file_id").unwrap().is_number(),
                "'file_id' should be a number");
            prop_assert!(value.get("name").unwrap().is_string(),
                "'name' should be a string");
            prop_assert!(value.get("path").unwrap().is_string(),
                "'path' should be a string");
            prop_assert!(value.get("size").unwrap().is_number(),
                "'size' should be a number");
            prop_assert!(value.get("modified").unwrap().is_string(),
                "'modified' should be a string (ISO 8601 datetime)");
            prop_assert!(value.get("is_directory").unwrap().is_boolean(),
                "'is_directory' should be a boolean");
            prop_assert!(value.get("score").unwrap().is_number(),
                "'score' should be a number");
            prop_assert!(value.get("match_indices").unwrap().is_array(),
                "'match_indices' should be an array");
        }

        /// **Validates: Requirements 6.1, 6.7**
        ///
        /// Property 11: Search Response Results Array Completeness
        ///
        /// For any search response with multiple results, every result in the
        /// array SHALL contain all required fields.
        #[test]
        fn prop_all_results_in_response_are_complete(
            results in proptest::collection::vec(arb_search_result(), 1..15),
            total_count in any::<u64>(),
            search_time_ms in any::<u64>(),
        ) {
            // Create a SearchResult response with multiple results
            let response = Response::SearchResult {
                results: results.clone(),
                total_count,
                search_time_ms,
            };

            // Serialize to JSON
            let json = serde_json::to_string(&response)
                .expect("Response should serialize to JSON");

            // Parse as generic JSON Value
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            let search_result = value.get("SearchResult").unwrap();
            let results_array = search_result.get("results").unwrap().as_array().unwrap();

            // Verify each result in the array has all required fields
            for (i, result_value) in results_array.iter().enumerate() {
                // Required fields for each SearchResult (per Requirements 6.1)
                let required_fields = [
                    ("file_id", "number"),
                    ("name", "string"),
                    ("path", "string"),
                    ("size", "number"),
                    ("modified", "string"),
                    ("is_directory", "boolean"),
                    ("score", "number"),
                    ("match_indices", "array"),
                ];

                for (field_name, expected_type) in required_fields.iter() {
                    let field = result_value.get(*field_name);
                    prop_assert!(field.is_some(),
                        "Result {} should contain '{}' field", i, field_name);

                    let field_value = field.unwrap();
                    let type_matches = match *expected_type {
                        "number" => field_value.is_number(),
                        "string" => field_value.is_string(),
                        "boolean" => field_value.is_boolean(),
                        "array" => field_value.is_array(),
                        _ => false,
                    };
                    prop_assert!(type_matches,
                        "Result {} field '{}' should be a {}, got {:?}",
                        i, field_name, expected_type, field_value);
                }
            }

            // Verify the number of results matches
            prop_assert_eq!(results_array.len(), results.len(),
                "Number of results in JSON should match original");
        }

        /// **Validates: Requirements 6.1, 6.7**
        ///
        /// Property 11: Match Indices Array Elements Are Valid Tuples
        ///
        /// For any SearchResult, the match_indices array SHALL contain valid
        /// (start, end) tuples where each element is a 2-element array of numbers.
        #[test]
        fn prop_match_indices_are_valid_tuples(
            result in arb_search_result(),
        ) {
            // Serialize the SearchResult to JSON
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            // Parse as generic JSON Value
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            let match_indices = value.get("match_indices").unwrap().as_array().unwrap();

            // Verify each match index is a valid (start, end) tuple
            for (i, index_tuple) in match_indices.iter().enumerate() {
                prop_assert!(index_tuple.is_array(),
                    "match_indices[{}] should be an array (tuple)", i);

                let tuple_array = index_tuple.as_array().unwrap();
                prop_assert_eq!(tuple_array.len(), 2,
                    "match_indices[{}] should have exactly 2 elements (start, end)", i);

                prop_assert!(tuple_array[0].is_number(),
                    "match_indices[{}][0] (start) should be a number", i);
                prop_assert!(tuple_array[1].is_number(),
                    "match_indices[{}][1] (end) should be a number", i);
            }
        }

        /// **Validates: Requirements 6.7**
        ///
        /// Property 11: Search Response Displays Total Count and Search Time
        ///
        /// For any search response, total_count and search_time_ms SHALL be
        /// non-negative values that can be displayed to the user.
        #[test]
        fn prop_search_response_has_displayable_stats(
            results in proptest::collection::vec(arb_search_result(), 0..10),
            total_count in any::<u64>(),
            search_time_ms in any::<u64>(),
        ) {
            let response = Response::SearchResult {
                results,
                total_count,
                search_time_ms,
            };

            // Serialize and deserialize to verify the values are preserved
            let json = serde_json::to_string(&response)
                .expect("Response should serialize to JSON");

            let deserialized: Response = serde_json::from_str(&json)
                .expect("JSON should deserialize back to Response");

            // Extract and verify the stats
            if let Response::SearchResult {
                total_count: tc,
                search_time_ms: stm,
                ..
            } = deserialized {
                prop_assert_eq!(tc, total_count,
                    "total_count should be preserved after serialization");
                prop_assert_eq!(stm, search_time_ms,
                    "search_time_ms should be preserved after serialization");
            } else {
                prop_assert!(false, "Response should be SearchResult variant");
            }
        }

        /// **Validates: Requirements 6.1**
        ///
        /// Property 11: SearchResult Path Is Valid Path String
        ///
        /// For any SearchResult, the path field SHALL be a valid path string
        /// that can be used to locate the file.
        #[test]
        fn prop_search_result_path_is_valid(
            result in arb_search_result(),
        ) {
            // Serialize the SearchResult to JSON
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            // Parse as generic JSON Value
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            let path_value = value.get("path").unwrap();
            prop_assert!(path_value.is_string(),
                "path should be a string");

            let path_str = path_value.as_str().unwrap();
            prop_assert!(!path_str.is_empty(),
                "path should not be empty");

            // Verify path can be parsed back to PathBuf
            let path_buf = PathBuf::from(path_str);
            prop_assert!(!path_buf.as_os_str().is_empty(),
                "path should be parseable as PathBuf");
        }

        /// **Validates: Requirements 6.1**
        ///
        /// Property 11: SearchResult Name Is Non-Empty String
        ///
        /// For any SearchResult, the name field SHALL be a non-empty string
        /// representing the file name.
        #[test]
        fn prop_search_result_name_is_non_empty(
            result in arb_search_result(),
        ) {
            // Serialize the SearchResult to JSON
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            // Parse as generic JSON Value
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            let name_value = value.get("name").unwrap();
            prop_assert!(name_value.is_string(),
                "name should be a string");

            let name_str = name_value.as_str().unwrap();
            prop_assert!(!name_str.is_empty(),
                "name should not be empty");
        }

        /// **Validates: Requirements 6.1**
        ///
        /// Property 11: SearchResult Modified Is Valid ISO 8601 DateTime
        ///
        /// For any SearchResult, the modified field SHALL be a valid ISO 8601
        /// datetime string that can be parsed and displayed.
        #[test]
        fn prop_search_result_modified_is_valid_datetime(
            result in arb_search_result(),
        ) {
            // Serialize the SearchResult to JSON
            let json = serde_json::to_string(&result)
                .expect("SearchResult should serialize to JSON");

            // Parse as generic JSON Value
            let value: serde_json::Value = serde_json::from_str(&json)
                .expect("JSON should parse as Value");

            let modified_value = value.get("modified").unwrap();
            prop_assert!(modified_value.is_string(),
                "modified should be a string");

            let modified_str = modified_value.as_str().unwrap();

            // Verify it can be parsed as DateTime
            let parsed: Result<DateTime<Utc>, _> = modified_str.parse();
            prop_assert!(parsed.is_ok(),
                "modified '{}' should be parseable as DateTime<Utc>", modified_str);
        }
    }
}
