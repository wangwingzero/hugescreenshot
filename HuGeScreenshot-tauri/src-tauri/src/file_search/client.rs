//! Search Client for communicating with the file search index service
//!
//! This module implements the client-side of the named pipe IPC protocol
//! for communicating with the file search Windows service.
//!
//! **Validates: Requirements 4.2, 4.5**
//! - 4.2: THE Search_Client SHALL connect to the named pipe for sending queries
//! - 4.5: IF connection is lost, THEN THE Search_Client SHALL attempt reconnection
//!   with exponential backoff

use std::io::{self, ErrorKind};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::{ClientOptions, NamedPipeClient};
use tokio::time::{sleep, timeout};
use tracing::{debug, error, info, warn};

use super::types::{
    ErrorCode, IndexConfig, Request, Response, RetryConfig, SearchQuery, SearchResult,
    ServiceStatus,
};

/// Named pipe path for the file search service
pub const PIPE_NAME: &str = r"\\.\pipe\HuGeScreenshot_FileSearch";

/// Windows error code for pipe busy
const ERROR_PIPE_BUSY: i32 = 231;

/// Default timeout for operations in milliseconds
const DEFAULT_TIMEOUT_MS: u64 = 30_000;

/// Maximum message size (16 MB)
const MAX_MESSAGE_SIZE: usize = 16 * 1024 * 1024;

/// Error type for search client operations
#[derive(Debug, thiserror::Error)]
pub enum SearchClientError {
    /// Connection to the service failed
    #[error("连接索引服务失败: {0}")]
    ConnectionFailed(String),

    /// Connection was lost during operation
    #[error("与索引服务的连接已断开")]
    ConnectionLost,

    /// Service is not running
    #[error("索引服务未运行")]
    ServiceNotRunning,

    /// Request timed out
    #[error("请求超时")]
    Timeout,

    /// Invalid response from service
    #[error("服务返回无效响应: {0}")]
    InvalidResponse(String),

    /// Service returned an error
    #[error("服务错误 ({code:?}): {message}")]
    ServiceError { code: ErrorCode, message: String },

    /// IO error
    #[error("IO 错误: {0}")]
    Io(#[from] io::Error),

    /// JSON serialization error
    #[error("JSON 序列化错误: {0}")]
    Json(#[from] serde_json::Error),

    /// Maximum retries exceeded
    #[error("重试次数已达上限 ({attempts} 次)")]
    MaxRetriesExceeded { attempts: u32 },

    /// Message too large
    #[error("消息过大: {size} 字节 (最大 {max} 字节)")]
    MessageTooLarge { size: usize, max: usize },

    /// Not connected
    #[error("未连接到索引服务")]
    NotConnected,
}

/// Result type for search client operations
pub type SearchClientResult<T> = Result<T, SearchClientError>;

/// Search client for communicating with the file search index service
///
/// The client manages a connection to the named pipe server and handles
/// automatic reconnection with exponential backoff when the connection is lost.
///
/// # Example
///
/// ```no_run
/// use hugescreenshot_tauri_lib::file_search::{SearchClient, SearchQuery};
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     let mut client = SearchClient::new();
///     client.connect().await?;
///     
///     let results = client.search(SearchQuery::default()).await?;
///     println!("Found {} files", results.len());
///     
///     client.disconnect().await;
///     Ok(())
/// }
/// ```
pub struct SearchClient {
    /// Named pipe path
    pipe_name: String,

    /// Active connection to the pipe server
    connection: Option<NamedPipeClient>,

    /// Retry configuration for connection attempts
    retry_config: RetryConfig,

    /// Operation timeout
    timeout_ms: u64,
}

impl SearchClient {
    /// Create a new SearchClient with default configuration
    ///
    /// The client is not connected after creation. Call `connect()` to
    /// establish a connection to the index service.
    pub fn new() -> Self {
        Self {
            pipe_name: PIPE_NAME.to_string(),
            connection: None,
            retry_config: RetryConfig::default(),
            timeout_ms: DEFAULT_TIMEOUT_MS,
        }
    }

    /// Create a new SearchClient with custom configuration
    ///
    /// # Arguments
    ///
    /// * `pipe_name` - Custom named pipe path
    /// * `retry_config` - Custom retry configuration
    pub fn with_config(pipe_name: String, retry_config: RetryConfig) -> Self {
        Self { pipe_name, connection: None, retry_config, timeout_ms: DEFAULT_TIMEOUT_MS }
    }

    /// Set the operation timeout
    pub fn set_timeout(&mut self, timeout_ms: u64) {
        self.timeout_ms = timeout_ms;
    }

    /// Check if the client is currently connected
    pub fn is_connected(&self) -> bool {
        self.connection.is_some()
    }

    /// Connect to the index service
    ///
    /// This method attempts to connect to the named pipe server with
    /// exponential backoff retry logic. If the connection fails after
    /// all retry attempts, an error is returned.
    ///
    /// **Validates: Requirements 4.2, 4.5**
    pub async fn connect(&mut self) -> SearchClientResult<()> {
        // If already connected, return success
        if self.connection.is_some() {
            debug!("Already connected to index service");
            return Ok(());
        }

        info!("Connecting to index service at {}", self.pipe_name);

        let mut last_error = None;

        for attempt in 0..=self.retry_config.max_retries {
            if attempt > 0 {
                let delay = self.retry_config.delay_for_attempt(attempt - 1);
                debug!("Retry attempt {} after {:?} delay", attempt, delay);
                sleep(delay).await;
            }

            match self.try_connect().await {
                Ok(client) => {
                    self.connection = Some(client);
                    info!("Successfully connected to index service");
                    return Ok(());
                }
                Err(e) => {
                    warn!("Connection attempt {} failed: {}", attempt + 1, e);
                    last_error = Some(e);

                    // Check if this is a retryable error
                    if !Self::is_retryable_error(last_error.as_ref().unwrap()) {
                        break;
                    }
                }
            }
        }

        // All retries exhausted
        let error = last_error
            .unwrap_or_else(|| SearchClientError::ConnectionFailed("Unknown error".to_string()));

        error!("Failed to connect after {} attempts: {}", self.retry_config.max_retries + 1, error);

        Err(SearchClientError::MaxRetriesExceeded { attempts: self.retry_config.max_retries + 1 })
    }

    /// Attempt a single connection to the named pipe
    async fn try_connect(&self) -> SearchClientResult<NamedPipeClient> {
        // Use timeout for the connection attempt
        let connect_timeout = Duration::from_millis(5000);

        match timeout(connect_timeout, async { ClientOptions::new().open(&self.pipe_name) }).await {
            Ok(Ok(client)) => Ok(client),
            Ok(Err(e)) => {
                // Check for specific Windows errors
                if e.kind() == ErrorKind::NotFound {
                    Err(SearchClientError::ServiceNotRunning)
                } else if e.raw_os_error() == Some(ERROR_PIPE_BUSY) {
                    Err(SearchClientError::ConnectionFailed(
                        "Pipe busy, server may be handling other clients".to_string(),
                    ))
                } else {
                    Err(SearchClientError::Io(e))
                }
            }
            Err(_) => Err(SearchClientError::Timeout),
        }
    }

    /// Check if an error is retryable
    fn is_retryable_error(error: &SearchClientError) -> bool {
        matches!(
            error,
            SearchClientError::ServiceNotRunning
                | SearchClientError::Timeout
                | SearchClientError::ConnectionFailed(_)
                | SearchClientError::Io(_)
        )
    }

    /// Disconnect from the index service
    ///
    /// This method closes the connection to the named pipe server.
    /// It is safe to call even if not connected.
    pub async fn disconnect(&mut self) {
        if let Some(mut conn) = self.connection.take() {
            debug!("Disconnecting from index service");
            // Attempt graceful shutdown
            let _ = conn.shutdown().await;
            info!("Disconnected from index service");
        }
    }

    /// Send a request and receive a response
    ///
    /// This is the core method for IPC communication. It serializes the
    /// request to JSON, sends it over the pipe, and deserializes the response.
    async fn send_request(&mut self, request: &Request) -> SearchClientResult<Response> {
        let conn = self.connection.as_mut().ok_or(SearchClientError::NotConnected)?;

        // Serialize request to JSON
        let request_json = serde_json::to_string(request)?;
        let request_bytes = request_json.as_bytes();

        // Check message size
        if request_bytes.len() > MAX_MESSAGE_SIZE {
            return Err(SearchClientError::MessageTooLarge {
                size: request_bytes.len(),
                max: MAX_MESSAGE_SIZE,
            });
        }

        // Send length-prefixed message
        // Format: [4 bytes length (little-endian)] [JSON payload]
        let len = request_bytes.len() as u32;
        let len_bytes = len.to_le_bytes();

        debug!("Sending request: {} bytes", request_bytes.len());

        // Write with timeout
        let write_result = timeout(Duration::from_millis(self.timeout_ms), async {
            conn.write_all(&len_bytes).await?;
            conn.write_all(request_bytes).await?;
            conn.flush().await?;
            Ok::<_, io::Error>(())
        })
        .await;

        match write_result {
            Ok(Ok(())) => {}
            Ok(Err(_e)) => {
                // Connection lost during write
                self.connection = None;
                return Err(SearchClientError::ConnectionLost);
            }
            Err(_) => {
                return Err(SearchClientError::Timeout);
            }
        }

        // Read response with timeout
        let read_result = timeout(Duration::from_millis(self.timeout_ms), async {
            // Read length prefix
            let mut len_buf = [0u8; 4];
            conn.read_exact(&mut len_buf).await?;
            let response_len = u32::from_le_bytes(len_buf) as usize;

            // Validate response size
            if response_len > MAX_MESSAGE_SIZE {
                return Err(io::Error::new(
                    ErrorKind::InvalidData,
                    format!("Response too large: {} bytes", response_len),
                ));
            }

            // Read response body
            let mut response_buf = vec![0u8; response_len];
            conn.read_exact(&mut response_buf).await?;

            Ok(response_buf)
        })
        .await;

        let response_buf = match read_result {
            Ok(Ok(buf)) => buf,
            Ok(Err(e)) => {
                // Connection lost during read
                if e.kind() == ErrorKind::UnexpectedEof {
                    self.connection = None;
                    return Err(SearchClientError::ConnectionLost);
                }
                return Err(SearchClientError::Io(e));
            }
            Err(_) => {
                return Err(SearchClientError::Timeout);
            }
        };

        // Deserialize response
        let response: Response = serde_json::from_slice(&response_buf).map_err(|e| {
            SearchClientError::InvalidResponse(format!("Failed to parse response: {}", e))
        })?;

        debug!("Received response");

        // Check for error response
        if let Response::Error { code, message } = &response {
            return Err(SearchClientError::ServiceError { code: *code, message: message.clone() });
        }

        Ok(response)
    }

    /// Send a request with automatic reconnection on failure
    async fn send_request_with_reconnect(
        &mut self,
        request: &Request,
    ) -> SearchClientResult<Response> {
        // First attempt
        match self.send_request(request).await {
            Ok(response) => Ok(response),
            Err(SearchClientError::ConnectionLost) | Err(SearchClientError::NotConnected) => {
                // Try to reconnect
                warn!("Connection lost, attempting to reconnect");
                self.connection = None;
                self.connect().await?;
                // Retry the request
                self.send_request(request).await
            }
            Err(e) => Err(e),
        }
    }

    /// Search for files matching the query
    ///
    /// **Validates: Requirements 5.1**
    ///
    /// # Arguments
    ///
    /// * `query` - Search query parameters
    ///
    /// # Returns
    ///
    /// A vector of search results matching the query
    pub async fn search(&mut self, query: SearchQuery) -> SearchClientResult<Vec<SearchResult>> {
        debug!("Searching for: {}", query.keyword);

        let request = Request::Search(query);
        let response = self.send_request_with_reconnect(&request).await?;

        match response {
            Response::SearchResult { results, total_count, search_time_ms } => {
                debug!(
                    "Search completed: {} results (total: {}) in {}ms",
                    results.len(),
                    total_count,
                    search_time_ms
                );
                Ok(results)
            }
            _ => Err(SearchClientError::InvalidResponse(
                "Expected SearchResult response".to_string(),
            )),
        }
    }

    /// Get the current service status
    ///
    /// **Validates: Requirements 1.6**
    ///
    /// # Returns
    ///
    /// The current status of the index service
    pub async fn get_status(&mut self) -> SearchClientResult<ServiceStatus> {
        debug!("Getting service status");

        let request = Request::GetStatus;
        let response = self.send_request_with_reconnect(&request).await?;

        match response {
            Response::Status(status) => {
                debug!("Service status: {:?}", status);
                Ok(status)
            }
            _ => Err(SearchClientError::InvalidResponse("Expected Status response".to_string())),
        }
    }

    /// Trigger a full index rebuild
    ///
    /// **Validates: Requirements 9.5**
    ///
    /// This operation may take several seconds to complete depending on
    /// the number of files on the system.
    pub async fn rebuild_index(&mut self) -> SearchClientResult<()> {
        info!("Requesting index rebuild");

        let request = Request::RebuildIndex;
        let response = self.send_request_with_reconnect(&request).await?;

        match response {
            Response::Ok => {
                info!("Index rebuild started");
                Ok(())
            }
            _ => Err(SearchClientError::InvalidResponse("Expected Ok response".to_string())),
        }
    }

    /// Update the index service configuration
    ///
    /// **Validates: Requirements 9.6**
    ///
    /// # Arguments
    ///
    /// * `config` - New configuration to apply
    pub async fn update_config(&mut self, config: IndexConfig) -> SearchClientResult<()> {
        info!("Updating index configuration");
        debug!("New config: {:?}", config);

        let request = Request::UpdateConfig(config);
        let response = self.send_request_with_reconnect(&request).await?;

        match response {
            Response::Ok => {
                info!("Configuration updated successfully");
                Ok(())
            }
            _ => Err(SearchClientError::InvalidResponse("Expected Ok response".to_string())),
        }
    }

    /// Cancel the current operation
    ///
    /// **Validates: Requirements 5.8**
    ///
    /// This can be used to cancel long-running searches or index rebuilds.
    pub async fn cancel(&mut self) -> SearchClientResult<()> {
        debug!("Cancelling current operation");

        let request = Request::Cancel;
        let response = self.send_request_with_reconnect(&request).await?;

        match response {
            Response::Ok => {
                debug!("Operation cancelled");
                Ok(())
            }
            _ => Err(SearchClientError::InvalidResponse("Expected Ok response".to_string())),
        }
    }
}

impl Default for SearchClient {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for SearchClient {
    fn drop(&mut self) {
        // Note: We can't do async cleanup in Drop, but the OS will clean up
        // the pipe handle when the process exits
        if self.connection.is_some() {
            debug!("SearchClient dropped with active connection");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_search_client_creation() {
        let client = SearchClient::new();
        assert_eq!(client.pipe_name, PIPE_NAME);
        assert!(!client.is_connected());
    }

    #[test]
    fn test_search_client_with_config() {
        let retry_config = RetryConfig {
            max_retries: 3,
            initial_delay_ms: 50,
            max_delay_ms: 1000,
            backoff_multiplier: 1.5,
        };

        let client = SearchClient::with_config(r"\\.\pipe\TestPipe".to_string(), retry_config);

        assert_eq!(client.pipe_name, r"\\.\pipe\TestPipe");
        assert_eq!(client.retry_config.max_retries, 3);
    }

    #[test]
    fn test_is_retryable_error() {
        assert!(SearchClient::is_retryable_error(&SearchClientError::ServiceNotRunning));
        assert!(SearchClient::is_retryable_error(&SearchClientError::Timeout));
        assert!(SearchClient::is_retryable_error(&SearchClientError::ConnectionFailed(
            "test".to_string()
        )));

        // Non-retryable errors
        assert!(!SearchClient::is_retryable_error(&SearchClientError::InvalidResponse(
            "test".to_string()
        )));
        assert!(!SearchClient::is_retryable_error(&SearchClientError::ServiceError {
            code: ErrorCode::InvalidQuery,
            message: "test".to_string(),
        }));
    }

    #[test]
    fn test_default_timeout() {
        let client = SearchClient::new();
        assert_eq!(client.timeout_ms, DEFAULT_TIMEOUT_MS);
    }

    #[test]
    fn test_set_timeout() {
        let mut client = SearchClient::new();
        client.set_timeout(5000);
        assert_eq!(client.timeout_ms, 5000);
    }

    #[tokio::test]
    async fn test_connect_service_not_running() {
        // This test expects the service to not be running
        let mut client = SearchClient::with_config(
            r"\\.\pipe\NonExistentPipe_Test".to_string(),
            RetryConfig {
                max_retries: 1,
                initial_delay_ms: 10,
                max_delay_ms: 100,
                backoff_multiplier: 2.0,
            },
        );

        let result = client.connect().await;
        assert!(result.is_err());

        match result {
            Err(SearchClientError::MaxRetriesExceeded { attempts }) => {
                assert_eq!(attempts, 2); // 1 initial + 1 retry
            }
            Err(e) => {
                // Other errors are also acceptable (service not running)
                println!("Got expected error: {}", e);
            }
            Ok(_) => panic!("Expected connection to fail"),
        }
    }

    #[tokio::test]
    async fn test_disconnect_when_not_connected() {
        let mut client = SearchClient::new();
        // Should not panic
        client.disconnect().await;
        assert!(!client.is_connected());
    }
}
