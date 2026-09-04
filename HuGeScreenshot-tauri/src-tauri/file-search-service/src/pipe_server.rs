//! Named pipe server for IPC communication
//!
//! Handles communication between the main app and index service.
//! Implements multi-client concurrent handling with JSON message protocol.
//!
//! **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::{NamedPipeServer, ServerOptions};
use tokio::sync::RwLock;

use crate::index::FileIndex;
use crate::protocol::{ErrorCode, Request, Response, ServiceStatus};
use crate::query::QueryEngine;
use crate::ServiceResult;

/// Maximum message size (10 MB)
const MAX_MESSAGE_SIZE: u32 = 10 * 1024 * 1024;

/// Read buffer size
const READ_BUFFER_SIZE: usize = 8192;

/// Named pipe server for handling client requests
///
/// The server accepts multiple concurrent client connections and processes
/// JSON-encoded Request messages, returning JSON-encoded Response messages.
///
/// ## Message Protocol
/// Messages use a length-prefixed format:
/// - 4 bytes: message length (little-endian u32)
/// - N bytes: JSON payload
///
/// ## Concurrency
/// Each client connection is handled in a separate tokio task, allowing
/// multiple clients to query the index simultaneously.
pub struct PipeServer {
    /// Pipe name (e.g., `\\.\pipe\HuGeScreenshot_FileSearch`)
    pipe_name: String,

    /// Reference to the file index (shared across all handlers)
    index: Arc<RwLock<FileIndex>>,

    /// Query engine for search operations
    query_engine: QueryEngine,

    /// Stop signal for graceful shutdown
    stop_signal: Arc<AtomicBool>,

    /// Flag to trigger index rebuild
    rebuild_requested: Arc<AtomicBool>,
}

impl PipeServer {
    /// Create a new pipe server
    ///
    /// # Arguments
    /// * `pipe_name` - The named pipe path (e.g., `\\.\pipe\HuGeScreenshot_FileSearch`)
    /// * `index` - Shared reference to the file index
    pub fn new(pipe_name: String, index: Arc<RwLock<FileIndex>>) -> Self {
        Self {
            pipe_name,
            index,
            query_engine: QueryEngine::new(),
            stop_signal: Arc::new(AtomicBool::new(false)),
            rebuild_requested: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Check if a rebuild has been requested
    pub fn is_rebuild_requested(&self) -> bool {
        self.rebuild_requested.load(Ordering::Relaxed)
    }

    /// Clear the rebuild request flag
    pub fn clear_rebuild_request(&self) {
        self.rebuild_requested.store(false, Ordering::Relaxed);
    }

    /// Start the pipe server
    ///
    /// This method runs the main server loop, accepting client connections
    /// and spawning handler tasks for each connection.
    ///
    /// **Validates: Requirements 4.1, 4.6**
    ///
    /// # Returns
    /// Returns when the stop signal is set or an unrecoverable error occurs.
    pub async fn start(&self) -> ServiceResult<()> {
        tracing::info!("Starting pipe server on {}", self.pipe_name);

        // Create the first pipe instance with first_pipe_instance flag
        // This ensures we own the pipe name
        let mut server = match ServerOptions::new()
            .first_pipe_instance(true)
            .reject_remote_clients(true) // Security: only local connections
            .create(&self.pipe_name)
        {
            Ok(s) => s,
            Err(e) => {
                tracing::error!("Failed to create named pipe: {}", e);
                return Err(crate::ServiceError::Ipc(format!(
                    "Failed to create named pipe: {}",
                    e
                )));
            }
        };

        tracing::info!("Pipe server listening on {}", self.pipe_name);

        // Main server loop
        while !self.stop_signal.load(Ordering::Relaxed) {
            // Wait for a client to connect with timeout
            // Use select to check stop signal periodically
            let connect_result = tokio::select! {
                result = server.connect() => result,
                _ = tokio::time::sleep(tokio::time::Duration::from_millis(100)) => {
                    // Check stop signal and continue loop
                    continue;
                }
            };

            match connect_result {
                Ok(()) => {
                    tracing::debug!("Client connected to pipe");

                    // Create the next server instance BEFORE spawning the handler
                    // This ensures there's always a listening instance available
                    let next_server = match ServerOptions::new()
                        .reject_remote_clients(true)
                        .create(&self.pipe_name)
                    {
                        Ok(s) => s,
                        Err(e) => {
                            tracing::error!("Failed to create next pipe instance: {}", e);
                            // Continue with current server, but log the error
                            continue;
                        }
                    };

                    // Swap the connected pipe with the new listening instance
                    let connected_pipe = std::mem::replace(&mut server, next_server);

                    // Spawn a task to handle this client
                    let index = Arc::clone(&self.index);
                    let query_engine = QueryEngine::new();
                    let rebuild_requested = Arc::clone(&self.rebuild_requested);

                    tokio::spawn(async move {
                        if let Err(e) =
                            Self::handle_client(connected_pipe, index, query_engine, rebuild_requested)
                                .await
                        {
                            tracing::warn!("Client handler error: {}", e);
                        }
                        tracing::debug!("Client disconnected");
                    });
                }
                Err(e) => {
                    // Check if it's a "pipe busy" or similar transient error
                    tracing::warn!("Error accepting connection: {}", e);
                    // Small delay before retrying
                    tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
                }
            }
        }

        tracing::info!("Pipe server stopped");
        Ok(())
    }

    /// Stop the pipe server
    pub fn stop(&self) {
        tracing::info!("Stopping pipe server");
        self.stop_signal.store(true, Ordering::Relaxed);
    }

    /// Handle a single client connection
    ///
    /// Reads requests from the client, processes them, and sends responses.
    /// The connection is kept open until the client disconnects or an error occurs.
    ///
    /// **Validates: Requirements 4.3, 4.4**
    async fn handle_client(
        mut pipe: NamedPipeServer,
        index: Arc<RwLock<FileIndex>>,
        query_engine: QueryEngine,
        rebuild_requested: Arc<AtomicBool>,
    ) -> ServiceResult<()> {
        loop {
            // Read the message length (4 bytes, little-endian)
            let mut len_buf = [0u8; 4];
            match pipe.read_exact(&mut len_buf).await {
                Ok(_) => {}
                Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => {
                    // Client disconnected gracefully
                    return Ok(());
                }
                Err(e) if e.kind() == std::io::ErrorKind::BrokenPipe => {
                    // Client disconnected
                    return Ok(());
                }
                Err(e) => {
                    return Err(crate::ServiceError::Ipc(format!(
                        "Failed to read message length: {}",
                        e
                    )));
                }
            }

            let msg_len = u32::from_le_bytes(len_buf);

            // Validate message length
            if msg_len == 0 {
                tracing::warn!("Received empty message");
                continue;
            }
            if msg_len > MAX_MESSAGE_SIZE {
                tracing::warn!("Message too large: {} bytes", msg_len);
                let response = Response::Error {
                    code: ErrorCode::InvalidQuery,
                    message: format!("Message too large: {} bytes (max: {})", msg_len, MAX_MESSAGE_SIZE),
                };
                Self::write_response(&mut pipe, &response).await?;
                continue;
            }

            // Read the message payload
            let mut payload = vec![0u8; msg_len as usize];
            if let Err(e) = pipe.read_exact(&mut payload).await {
                return Err(crate::ServiceError::Ipc(format!(
                    "Failed to read message payload: {}",
                    e
                )));
            }

            // Parse the request
            let request: Request = match serde_json::from_slice(&payload) {
                Ok(req) => req,
                Err(e) => {
                    tracing::warn!("Failed to parse request: {}", e);
                    let response = Response::Error {
                        code: ErrorCode::InvalidQuery,
                        message: format!("Invalid JSON: {}", e),
                    };
                    Self::write_response(&mut pipe, &response).await?;
                    continue;
                }
            };

            // Process the request
            let response =
                Self::handle_request(&index, &query_engine, &rebuild_requested, request).await;

            // Send the response
            Self::write_response(&mut pipe, &response).await?;
        }
    }

    /// Write a response to the pipe
    ///
    /// Serializes the response to JSON and sends it with length prefix.
    async fn write_response(
        pipe: &mut NamedPipeServer,
        response: &Response,
    ) -> ServiceResult<()> {
        let payload = serde_json::to_vec(response)?;
        let len = payload.len() as u32;

        // Write length prefix
        pipe.write_all(&len.to_le_bytes()).await.map_err(|e| {
            crate::ServiceError::Ipc(format!("Failed to write response length: {}", e))
        })?;

        // Write payload
        pipe.write_all(&payload).await.map_err(|e| {
            crate::ServiceError::Ipc(format!("Failed to write response payload: {}", e))
        })?;

        // Flush to ensure data is sent
        pipe.flush().await.map_err(|e| {
            crate::ServiceError::Ipc(format!("Failed to flush response: {}", e))
        })?;

        Ok(())
    }

    /// Handle a single request
    ///
    /// **Validates: Requirements 4.4**
    async fn handle_request(
        index: &Arc<RwLock<FileIndex>>,
        query_engine: &QueryEngine,
        rebuild_requested: &Arc<AtomicBool>,
        request: Request,
    ) -> Response {
        match request {
            Request::Search(query) => {
                tracing::debug!("Processing search request: {:?}", query.keyword);
                let start = Instant::now();

                let index_guard = index.read().await;
                let results = query_engine.search(&index_guard, &query);
                let total_count = results.len() as u64;
                let elapsed = start.elapsed().as_millis() as u64;

                tracing::debug!(
                    "Search completed: {} results in {}ms",
                    total_count,
                    elapsed
                );

                Response::SearchResult {
                    results,
                    total_count,
                    search_time_ms: elapsed,
                }
            }

            Request::GetStatus => {
                tracing::debug!("Processing status request");
                let index_guard = index.read().await;
                let stats = index_guard.stats();

                Response::Status(ServiceStatus::Running {
                    indexed_files: stats.total_files + stats.total_directories,
                    last_update: stats.last_update,
                })
            }

            Request::RebuildIndex => {
                tracing::info!("Index rebuild requested");
                rebuild_requested.store(true, Ordering::Relaxed);
                Response::Ok
            }

            Request::UpdateConfig(config) => {
                tracing::info!("Config update requested: {:?}", config);
                // TODO: Implement config update
                // For now, just acknowledge the request
                Response::Ok
            }

            Request::Cancel => {
                tracing::debug!("Cancel request received");
                // TODO: Implement cancellation of long-running operations
                Response::Ok
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::FileEntry;
    use chrono::Utc;

    fn create_test_index() -> Arc<RwLock<FileIndex>> {
        let mut index = FileIndex::new();
        index.insert(FileEntry::new(
            1,
            0,
            "test.txt".to_string(),
            1024,
            Utc::now(),
            Utc::now(),
            false,
            'C',
        ));
        index.insert(FileEntry::new(
            2,
            0,
            "document.pdf".to_string(),
            2048,
            Utc::now(),
            Utc::now(),
            false,
            'C',
        ));
        Arc::new(RwLock::new(index))
    }

    #[tokio::test]
    async fn test_pipe_server_creation() {
        let index = Arc::new(RwLock::new(FileIndex::new()));
        let server = PipeServer::new(r"\\.\pipe\test_creation".to_string(), index);

        assert!(!server.stop_signal.load(Ordering::Relaxed));
        assert!(!server.is_rebuild_requested());
    }

    #[tokio::test]
    async fn test_handle_get_status() {
        let index = create_test_index();
        let query_engine = QueryEngine::new();
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        let response =
            PipeServer::handle_request(&index, &query_engine, &rebuild_requested, Request::GetStatus)
                .await;

        match response {
            Response::Status(ServiceStatus::Running { indexed_files, .. }) => {
                assert_eq!(indexed_files, 2);
            }
            _ => panic!("Expected Status response"),
        }
    }

    #[tokio::test]
    async fn test_handle_search() {
        let index = create_test_index();
        let query_engine = QueryEngine::new();
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        let query = crate::protocol::SearchQuery {
            keyword: "test".to_string(),
            ..Default::default()
        };

        let response = PipeServer::handle_request(
            &index,
            &query_engine,
            &rebuild_requested,
            Request::Search(query),
        )
        .await;

        match response {
            Response::SearchResult {
                results,
                total_count,
                search_time_ms,
            } => {
                assert!(!results.is_empty());
                assert!(total_count > 0);
                assert!(search_time_ms < 1000); // Should be fast
            }
            _ => panic!("Expected SearchResult response"),
        }
    }

    #[tokio::test]
    async fn test_handle_rebuild_index() {
        let index = create_test_index();
        let query_engine = QueryEngine::new();
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        let response = PipeServer::handle_request(
            &index,
            &query_engine,
            &rebuild_requested,
            Request::RebuildIndex,
        )
        .await;

        assert!(matches!(response, Response::Ok));
        assert!(rebuild_requested.load(Ordering::Relaxed));
    }

    #[tokio::test]
    async fn test_handle_update_config() {
        let index = create_test_index();
        let query_engine = QueryEngine::new();
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        let config = crate::config::IndexConfig {
            volumes: vec!['C', 'D'],
            exclude_paths: vec![],
            result_limit: 100,
        };

        let response = PipeServer::handle_request(
            &index,
            &query_engine,
            &rebuild_requested,
            Request::UpdateConfig(config),
        )
        .await;

        assert!(matches!(response, Response::Ok));
    }

    #[tokio::test]
    async fn test_handle_cancel() {
        let index = create_test_index();
        let query_engine = QueryEngine::new();
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        let response =
            PipeServer::handle_request(&index, &query_engine, &rebuild_requested, Request::Cancel)
                .await;

        assert!(matches!(response, Response::Ok));
    }

    #[tokio::test]
    async fn test_stop_signal() {
        let index = Arc::new(RwLock::new(FileIndex::new()));
        let server = PipeServer::new(r"\\.\pipe\test_stop".to_string(), index);

        assert!(!server.stop_signal.load(Ordering::Relaxed));
        server.stop();
        assert!(server.stop_signal.load(Ordering::Relaxed));
    }

    #[tokio::test]
    async fn test_rebuild_request_flag() {
        let index = Arc::new(RwLock::new(FileIndex::new()));
        let server = PipeServer::new(r"\\.\pipe\test_rebuild".to_string(), index);

        assert!(!server.is_rebuild_requested());

        server.rebuild_requested.store(true, Ordering::Relaxed);
        assert!(server.is_rebuild_requested());

        server.clear_rebuild_request();
        assert!(!server.is_rebuild_requested());
    }

    #[test]
    fn test_message_length_encoding() {
        // Test that length encoding is correct
        let len: u32 = 12345;
        let bytes = len.to_le_bytes();
        let decoded = u32::from_le_bytes(bytes);
        assert_eq!(len, decoded);
    }

    #[test]
    fn test_max_message_size() {
        assert_eq!(MAX_MESSAGE_SIZE, 10 * 1024 * 1024);
    }
}

// =============================================================================
// Property-Based Tests for Concurrent Connection Support
// =============================================================================
//
// **Property 4: Concurrent Connection Support**
// **Validates: Requirements 4.6**
//
// For any number of concurrent client connections (up to the configured limit),
// all clients SHALL receive correct responses to their queries without interference.
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use crate::models::FileEntry;
    use crate::protocol::{MatchMode, Request, Response, SearchFilters, SearchQuery, SortField, SortOrder};
    use chrono::Utc;
    use proptest::prelude::*;
    use std::collections::HashSet;
    use std::sync::atomic::AtomicBool;

    // =========================================================================
    // Test Helpers
    // =========================================================================

    /// Create a test index with a specified number of files
    fn create_test_index_with_files(file_count: usize) -> Arc<RwLock<FileIndex>> {
        let mut index = FileIndex::new();
        let now = Utc::now();

        for i in 0..file_count {
            let name = format!("file_{:05}.txt", i);
            index.insert(FileEntry::new(
                i as u64 + 1,
                0,
                name,
                (i * 1024) as u64,
                now,
                now,
                false,
                'C',
            ));
        }

        Arc::new(RwLock::new(index))
    }

    /// Create a test index with specific file names for targeted searches
    fn create_test_index_with_names(names: &[&str]) -> Arc<RwLock<FileIndex>> {
        let mut index = FileIndex::new();
        let now = Utc::now();

        for (i, name) in names.iter().enumerate() {
            index.insert(FileEntry::new(
                i as u64 + 1,
                0,
                name.to_string(),
                1024,
                now,
                now,
                false,
                'C',
            ));
        }

        Arc::new(RwLock::new(index))
    }

    // =========================================================================
    // Arbitrary Strategies
    // =========================================================================

    /// Strategy for generating valid search keywords
    fn arb_search_keyword() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("file".to_string()),
            Just("test".to_string()),
            Just("doc".to_string()),
            Just("report".to_string()),
            Just("data".to_string()),
            "[a-z]{1,10}".prop_map(|s| s),
        ]
    }

    /// Strategy for generating arbitrary MatchMode
    fn arb_match_mode() -> impl Strategy<Value = MatchMode> {
        prop_oneof![
            Just(MatchMode::Exact),
            Just(MatchMode::Wildcard),
            Just(MatchMode::Fuzzy),
            // Skip Regex to avoid invalid regex patterns
        ]
    }

    /// Strategy for generating arbitrary SortField
    fn arb_sort_field() -> impl Strategy<Value = SortField> {
        prop_oneof![
            Just(SortField::Relevance),
            Just(SortField::Name),
            Just(SortField::Size),
            Just(SortField::Modified),
        ]
    }

    /// Strategy for generating arbitrary SortOrder
    fn arb_sort_order() -> impl Strategy<Value = SortOrder> {
        prop_oneof![Just(SortOrder::Asc), Just(SortOrder::Desc),]
    }

    /// Strategy for generating arbitrary SearchQuery
    fn arb_search_query() -> impl Strategy<Value = SearchQuery> {
        (
            arb_search_keyword(),
            arb_match_mode(),
            arb_sort_field(),
            arb_sort_order(),
            1usize..100usize,
            0usize..50usize,
        )
            .prop_map(|(keyword, match_mode, sort_by, sort_order, limit, offset)| SearchQuery {
                keyword,
                match_mode,
                filters: SearchFilters::default(),
                sort_by,
                sort_order,
                limit,
                offset,
            })
    }

    /// Strategy for generating arbitrary Request
    fn arb_request() -> impl Strategy<Value = Request> {
        prop_oneof![
            arb_search_query().prop_map(Request::Search),
            Just(Request::GetStatus),
            Just(Request::Cancel),
        ]
    }

    /// Strategy for generating number of concurrent requests (1-20)
    fn arb_concurrent_count() -> impl Strategy<Value = usize> {
        1usize..=20usize
    }

    // =========================================================================
    // Property Tests
    // =========================================================================

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 4.6**
        ///
        /// Property 4: Concurrent Connection Support - All requests receive valid responses
        ///
        /// For any number of concurrent client requests, all clients SHALL receive
        /// valid responses (not errors due to concurrency issues).
        #[test]
        fn prop_concurrent_requests_all_receive_valid_responses(
            concurrent_count in arb_concurrent_count(),
            requests in proptest::collection::vec(arb_request(), 1..=20)
        ) {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async {
                let index = create_test_index_with_files(100);
                let query_engine = QueryEngine::new();
                let rebuild_requested = Arc::new(AtomicBool::new(false));

                // Take only the number of requests we need
                let requests_to_run: Vec<_> = requests.into_iter().take(concurrent_count).collect();
                let request_count = requests_to_run.len();

                // Spawn concurrent tasks
                let mut handles = Vec::new();
                for request in requests_to_run {
                    let index_clone = Arc::clone(&index);
                    let rebuild_clone = Arc::clone(&rebuild_requested);
                    let qe = QueryEngine::new();

                    handles.push(tokio::spawn(async move {
                        PipeServer::handle_request(&index_clone, &qe, &rebuild_clone, request).await
                    }));
                }

                // Wait for all tasks to complete
                let results: Vec<Response> = futures::future::join_all(handles)
                    .await
                    .into_iter()
                    .map(|r| r.expect("Task should not panic"))
                    .collect();

                // Verify all responses are valid (not internal errors)
                prop_assert_eq!(results.len(), request_count,
                    "All requests should receive responses");

                for response in &results {
                    match response {
                        Response::SearchResult { .. } => { /* Valid */ }
                        Response::Status(_) => { /* Valid */ }
                        Response::Ok => { /* Valid */ }
                        Response::Error { code, message } => {
                            // Only InvalidQuery errors are acceptable (e.g., bad regex)
                            // InternalError would indicate a concurrency bug
                            prop_assert!(
                                *code != crate::protocol::ErrorCode::InternalError,
                                "Concurrent requests should not cause internal errors: {}",
                                message
                            );
                        }
                    }
                }

                Ok(())
            })?;
        }

        /// **Validates: Requirements 4.6**
        ///
        /// Property 4: Concurrent Connection Support - Search results are consistent
        ///
        /// For any search query executed concurrently multiple times, all executions
        /// SHALL return identical results (deterministic behavior).
        #[test]
        fn prop_concurrent_same_query_returns_consistent_results(
            query in arb_search_query(),
            concurrent_count in 2usize..=10usize
        ) {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async {
                let index = create_test_index_with_files(100);
                let rebuild_requested = Arc::new(AtomicBool::new(false));

                // Execute the same query concurrently multiple times
                let mut handles = Vec::new();
                for _ in 0..concurrent_count {
                    let index_clone = Arc::clone(&index);
                    let rebuild_clone = Arc::clone(&rebuild_requested);
                    let query_clone = query.clone();
                    let qe = QueryEngine::new();

                    handles.push(tokio::spawn(async move {
                        PipeServer::handle_request(
                            &index_clone,
                            &qe,
                            &rebuild_clone,
                            Request::Search(query_clone),
                        )
                        .await
                    }));
                }

                // Wait for all tasks to complete
                let results: Vec<Response> = futures::future::join_all(handles)
                    .await
                    .into_iter()
                    .map(|r| r.expect("Task should not panic"))
                    .collect();

                // Extract search results
                let search_results: Vec<_> = results
                    .iter()
                    .filter_map(|r| match r {
                        Response::SearchResult { results, total_count, .. } => {
                            Some((results.clone(), *total_count))
                        }
                        _ => None,
                    })
                    .collect();

                // All search results should be identical
                if !search_results.is_empty() {
                    let first = &search_results[0];
                    for (i, result) in search_results.iter().enumerate().skip(1) {
                        prop_assert_eq!(
                            first.1, result.1,
                            "Concurrent query {} should have same total_count as first",
                            i
                        );
                        prop_assert_eq!(
                            first.0.len(), result.0.len(),
                            "Concurrent query {} should have same result count as first",
                            i
                        );
                        // Compare file IDs to ensure same results
                        let first_ids: Vec<_> = first.0.iter().map(|r| r.file_id).collect();
                        let result_ids: Vec<_> = result.0.iter().map(|r| r.file_id).collect();
                        prop_assert_eq!(
                            first_ids, result_ids,
                            "Concurrent query {} should return same file IDs as first",
                            i
                        );
                    }
                }

                Ok(())
            })?;
        }

        /// **Validates: Requirements 4.6**
        ///
        /// Property 4: Concurrent Connection Support - No request interference
        ///
        /// For any set of different concurrent requests, each request SHALL receive
        /// the correct response for its specific query (no cross-contamination).
        #[test]
        fn prop_concurrent_different_queries_no_interference(
            queries in proptest::collection::vec(arb_search_query(), 2..=10)
        ) {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async {
                // Create index with distinct file names for each query keyword
                let names: Vec<&str> = vec![
                    "file_alpha.txt",
                    "file_beta.txt",
                    "test_gamma.txt",
                    "test_delta.txt",
                    "doc_epsilon.txt",
                    "doc_zeta.txt",
                    "report_eta.txt",
                    "report_theta.txt",
                    "data_iota.txt",
                    "data_kappa.txt",
                ];
                let index = create_test_index_with_names(&names);
                let rebuild_requested = Arc::new(AtomicBool::new(false));

                // First, execute each query sequentially to get expected results
                let mut expected_results = Vec::new();
                for query in &queries {
                    let qe = QueryEngine::new();
                    let response = PipeServer::handle_request(
                        &index,
                        &qe,
                        &rebuild_requested,
                        Request::Search(query.clone()),
                    )
                    .await;
                    expected_results.push(response);
                }

                // Now execute all queries concurrently
                let mut handles = Vec::new();
                for (i, query) in queries.iter().enumerate() {
                    let index_clone = Arc::clone(&index);
                    let rebuild_clone = Arc::clone(&rebuild_requested);
                    let query_clone = query.clone();
                    let qe = QueryEngine::new();

                    handles.push(tokio::spawn(async move {
                        let response = PipeServer::handle_request(
                            &index_clone,
                            &qe,
                            &rebuild_clone,
                            Request::Search(query_clone),
                        )
                        .await;
                        (i, response)
                    }));
                }

                // Wait for all concurrent tasks
                let concurrent_results: Vec<(usize, Response)> = futures::future::join_all(handles)
                    .await
                    .into_iter()
                    .map(|r| r.expect("Task should not panic"))
                    .collect();

                // Verify each concurrent result matches its expected result
                for (idx, concurrent_response) in concurrent_results {
                    let expected = &expected_results[idx];

                    match (expected, &concurrent_response) {
                        (
                            Response::SearchResult { results: exp_results, total_count: exp_count, .. },
                            Response::SearchResult { results: conc_results, total_count: conc_count, .. },
                        ) => {
                            prop_assert_eq!(
                                exp_count, conc_count,
                                "Query {} concurrent total_count should match sequential",
                                idx
                            );
                            prop_assert_eq!(
                                exp_results.len(), conc_results.len(),
                                "Query {} concurrent result count should match sequential",
                                idx
                            );
                            // Compare file IDs
                            let exp_ids: Vec<_> = exp_results.iter().map(|r| r.file_id).collect();
                            let conc_ids: Vec<_> = conc_results.iter().map(|r| r.file_id).collect();
                            prop_assert_eq!(
                                exp_ids, conc_ids,
                                "Query {} concurrent file IDs should match sequential",
                                idx
                            );
                        }
                        _ => {
                            // Both should be the same variant
                            let exp_json = serde_json::to_string(expected).unwrap();
                            let conc_json = serde_json::to_string(&concurrent_response).unwrap();
                            prop_assert_eq!(
                                exp_json, conc_json,
                                "Query {} concurrent response should match sequential",
                                idx
                            );
                        }
                    }
                }

                Ok(())
            })?;
        }

        /// **Validates: Requirements 4.6**
        ///
        /// Property 4: Concurrent Connection Support - Mixed request types
        ///
        /// For any mix of Search, GetStatus, and Cancel requests executed concurrently,
        /// all requests SHALL receive appropriate responses without interference.
        #[test]
        fn prop_concurrent_mixed_request_types(
            request_count in 5usize..=15usize
        ) {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async {
                let index = create_test_index_with_files(50);
                let rebuild_requested = Arc::new(AtomicBool::new(false));

                // Create a mix of request types
                let requests: Vec<Request> = (0..request_count)
                    .map(|i| match i % 3 {
                        0 => Request::Search(SearchQuery {
                            keyword: format!("file_{:02}", i),
                            ..Default::default()
                        }),
                        1 => Request::GetStatus,
                        _ => Request::Cancel,
                    })
                    .collect();

                // Execute all requests concurrently
                let mut handles = Vec::new();
                for (i, request) in requests.into_iter().enumerate() {
                    let index_clone = Arc::clone(&index);
                    let rebuild_clone = Arc::clone(&rebuild_requested);
                    let qe = QueryEngine::new();
                    let req_type = match &request {
                        Request::Search(_) => "Search",
                        Request::GetStatus => "GetStatus",
                        Request::Cancel => "Cancel",
                        _ => "Other",
                    };

                    handles.push(tokio::spawn(async move {
                        let response = PipeServer::handle_request(
                            &index_clone,
                            &qe,
                            &rebuild_clone,
                            request,
                        )
                        .await;
                        (i, req_type, response)
                    }));
                }

                // Wait for all tasks
                let results: Vec<(usize, &str, Response)> = futures::future::join_all(handles)
                    .await
                    .into_iter()
                    .map(|r| r.expect("Task should not panic"))
                    .collect();

                // Verify each response matches its request type
                for (idx, req_type, response) in results {
                    match (req_type, &response) {
                        ("Search", Response::SearchResult { .. }) => { /* Correct */ }
                        ("GetStatus", Response::Status(_)) => { /* Correct */ }
                        ("Cancel", Response::Ok) => { /* Correct */ }
                        (req, resp) => {
                            prop_assert!(
                                false,
                                "Request {} ({}) received unexpected response type: {:?}",
                                idx, req, resp
                            );
                        }
                    }
                }

                Ok(())
            })?;
        }

        /// **Validates: Requirements 4.6**
        ///
        /// Property 4: Concurrent Connection Support - Index read consistency
        ///
        /// For any number of concurrent read operations on the index,
        /// all reads SHALL see a consistent view of the index data.
        #[test]
        fn prop_concurrent_reads_see_consistent_index(
            read_count in 5usize..=20usize
        ) {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async {
                let index = create_test_index_with_files(100);
                let rebuild_requested = Arc::new(AtomicBool::new(false));

                // All queries search for the same thing
                let query = SearchQuery {
                    keyword: "file".to_string(),
                    match_mode: MatchMode::Fuzzy,
                    ..Default::default()
                };

                // Execute many concurrent reads
                let mut handles = Vec::new();
                for _ in 0..read_count {
                    let index_clone = Arc::clone(&index);
                    let rebuild_clone = Arc::clone(&rebuild_requested);
                    let query_clone = query.clone();
                    let qe = QueryEngine::new();

                    handles.push(tokio::spawn(async move {
                        PipeServer::handle_request(
                            &index_clone,
                            &qe,
                            &rebuild_clone,
                            Request::Search(query_clone),
                        )
                        .await
                    }));
                }

                // Wait for all tasks
                let results: Vec<Response> = futures::future::join_all(handles)
                    .await
                    .into_iter()
                    .map(|r| r.expect("Task should not panic"))
                    .collect();

                // Extract total counts from all results
                let total_counts: Vec<u64> = results
                    .iter()
                    .filter_map(|r| match r {
                        Response::SearchResult { total_count, .. } => Some(*total_count),
                        _ => None,
                    })
                    .collect();

                // All reads should see the same total count
                if !total_counts.is_empty() {
                    let first_count = total_counts[0];
                    for (i, count) in total_counts.iter().enumerate() {
                        prop_assert_eq!(
                            first_count, *count,
                            "Concurrent read {} should see same total_count as first",
                            i
                        );
                    }
                }

                Ok(())
            })?;
        }
    }

    // =========================================================================
    // Additional Unit Tests for Concurrency Edge Cases
    // =========================================================================

    #[tokio::test]
    async fn test_concurrent_status_requests() {
        let index = create_test_index_with_files(50);
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        // Execute 10 concurrent GetStatus requests
        let mut handles = Vec::new();
        for _ in 0..10 {
            let index_clone = Arc::clone(&index);
            let rebuild_clone = Arc::clone(&rebuild_requested);
            let qe = QueryEngine::new();

            handles.push(tokio::spawn(async move {
                PipeServer::handle_request(&index_clone, &qe, &rebuild_clone, Request::GetStatus)
                    .await
            }));
        }

        let results: Vec<Response> = futures::future::join_all(handles)
            .await
            .into_iter()
            .map(|r| r.unwrap())
            .collect();

        // All should return Status with same indexed_files count
        let mut indexed_counts = HashSet::new();
        for response in results {
            match response {
                Response::Status(crate::protocol::ServiceStatus::Running { indexed_files, .. }) => {
                    indexed_counts.insert(indexed_files);
                }
                _ => panic!("Expected Status response"),
            }
        }

        // All should report the same count
        assert_eq!(indexed_counts.len(), 1, "All status responses should report same file count");
    }

    #[tokio::test]
    async fn test_concurrent_rebuild_requests() {
        let index = create_test_index_with_files(10);
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        // Execute multiple concurrent RebuildIndex requests
        let mut handles = Vec::new();
        for _ in 0..5 {
            let index_clone = Arc::clone(&index);
            let rebuild_clone = Arc::clone(&rebuild_requested);
            let qe = QueryEngine::new();

            handles.push(tokio::spawn(async move {
                PipeServer::handle_request(&index_clone, &qe, &rebuild_clone, Request::RebuildIndex)
                    .await
            }));
        }

        let results: Vec<Response> = futures::future::join_all(handles)
            .await
            .into_iter()
            .map(|r| r.unwrap())
            .collect();

        // All should return Ok
        for response in results {
            assert!(matches!(response, Response::Ok));
        }

        // Rebuild flag should be set
        assert!(rebuild_requested.load(Ordering::Relaxed));
    }

    #[tokio::test]
    async fn test_concurrent_search_with_different_limits() {
        let index = create_test_index_with_files(100);
        let rebuild_requested = Arc::new(AtomicBool::new(false));

        // Execute searches with different limits concurrently
        let limits = vec![10, 20, 50, 100];
        let mut handles = Vec::new();

        for limit in limits.clone() {
            let index_clone = Arc::clone(&index);
            let rebuild_clone = Arc::clone(&rebuild_requested);
            let qe = QueryEngine::new();

            let query = SearchQuery {
                keyword: "file".to_string(),
                limit,
                ..Default::default()
            };

            handles.push(tokio::spawn(async move {
                let response = PipeServer::handle_request(
                    &index_clone,
                    &qe,
                    &rebuild_clone,
                    Request::Search(query),
                )
                .await;
                (limit, response)
            }));
        }

        let results: Vec<(usize, Response)> = futures::future::join_all(handles)
            .await
            .into_iter()
            .map(|r| r.unwrap())
            .collect();

        // Each result should respect its limit
        for (limit, response) in results {
            match response {
                Response::SearchResult { results, .. } => {
                    assert!(
                        results.len() <= limit,
                        "Results ({}) should not exceed limit ({})",
                        results.len(),
                        limit
                    );
                }
                _ => panic!("Expected SearchResult response"),
            }
        }
    }
}
