//! Type definitions for the file search client
//!
//! These types are compatible with the file-search-service protocol.
//! They are re-exported from the service's protocol module for consistency.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// =============================================================================
// Search Query Types
// =============================================================================

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

// =============================================================================
// Search Result Types
// =============================================================================

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

// =============================================================================
// Service Status Types
// =============================================================================

/// Service status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ServiceStatus {
    /// Service is starting up
    Starting,

    /// Service is running normally
    Running { indexed_files: u64, last_update: DateTime<Utc> },

    /// Service is scanning/indexing
    Scanning { progress: f32, scanned_files: u64 },

    /// Service is stopping
    Stopping,

    /// Service is stopped
    Stopped,
}

// =============================================================================
// Configuration Types
// =============================================================================

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

// =============================================================================
// Protocol Types (IPC Messages)
// =============================================================================

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
    SearchResult { results: Vec<SearchResult>, total_count: u64, search_time_ms: u64 },

    /// Service status
    Status(ServiceStatus),

    /// Operation completed successfully
    Ok,

    /// Error occurred
    Error { code: ErrorCode, message: String },
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

// =============================================================================
// Retry Configuration
// =============================================================================

/// Configuration for connection retry with exponential backoff
#[derive(Debug, Clone)]
pub struct RetryConfig {
    /// Maximum number of retry attempts
    pub max_retries: u32,

    /// Initial delay in milliseconds before first retry
    pub initial_delay_ms: u64,

    /// Maximum delay in milliseconds between retries
    pub max_delay_ms: u64,

    /// Multiplier for exponential backoff (e.g., 2.0 doubles delay each retry)
    pub backoff_multiplier: f64,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_retries: 5,
            initial_delay_ms: 100,
            max_delay_ms: 10_000, // 10 seconds max
            backoff_multiplier: 2.0,
        }
    }
}

impl RetryConfig {
    /// Calculate the delay for a given retry attempt (0-indexed)
    pub fn delay_for_attempt(&self, attempt: u32) -> std::time::Duration {
        let delay_ms =
            (self.initial_delay_ms as f64) * self.backoff_multiplier.powi(attempt as i32);
        let capped_delay_ms = delay_ms.min(self.max_delay_ms as f64) as u64;
        std::time::Duration::from_millis(capped_delay_ms)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_retry_config_default() {
        let config = RetryConfig::default();
        assert_eq!(config.max_retries, 5);
        assert_eq!(config.initial_delay_ms, 100);
        assert_eq!(config.max_delay_ms, 10_000);
        assert_eq!(config.backoff_multiplier, 2.0);
    }

    #[test]
    fn test_retry_config_delay_calculation() {
        let config = RetryConfig {
            max_retries: 5,
            initial_delay_ms: 100,
            max_delay_ms: 5000,
            backoff_multiplier: 2.0,
        };

        // Attempt 0: 100ms
        assert_eq!(config.delay_for_attempt(0), std::time::Duration::from_millis(100));
        // Attempt 1: 200ms
        assert_eq!(config.delay_for_attempt(1), std::time::Duration::from_millis(200));
        // Attempt 2: 400ms
        assert_eq!(config.delay_for_attempt(2), std::time::Duration::from_millis(400));
        // Attempt 3: 800ms
        assert_eq!(config.delay_for_attempt(3), std::time::Duration::from_millis(800));
        // Attempt 4: 1600ms
        assert_eq!(config.delay_for_attempt(4), std::time::Duration::from_millis(1600));
        // Attempt 5: 3200ms
        assert_eq!(config.delay_for_attempt(5), std::time::Duration::from_millis(3200));
        // Attempt 6: capped at 5000ms
        assert_eq!(config.delay_for_attempt(6), std::time::Duration::from_millis(5000));
    }

    #[test]
    fn test_search_query_default() {
        let query = SearchQuery::default();
        assert_eq!(query.keyword, "");
        assert!(matches!(query.match_mode, MatchMode::Fuzzy));
        assert_eq!(query.limit, 100);
        assert_eq!(query.offset, 0);
    }

    #[test]
    fn test_index_config_default() {
        let config = IndexConfig::default();
        assert!(!config.volumes.is_empty());
        assert!(config.volumes.contains(&'C'));
        assert_eq!(config.result_limit, 100);
    }

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
        let response =
            Response::SearchResult { results: vec![], total_count: 0, search_time_ms: 5 };
        let json = serde_json::to_string(&response).unwrap();
        let parsed: Response = serde_json::from_str(&json).unwrap();

        match parsed {
            Response::SearchResult { search_time_ms, .. } => {
                assert_eq!(search_time_ms, 5);
            }
            _ => panic!("Expected SearchResult response"),
        }
    }
}
