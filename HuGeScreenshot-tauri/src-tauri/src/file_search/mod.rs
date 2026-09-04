//! File Search Client Module
//!
//! This module provides the client-side implementation for communicating with
//! the file search index service via named pipes.
//!
//! ## Architecture
//!
//! The file search feature uses a Windows service (Index Service) that runs with
//! SYSTEM privileges to read NTFS MFT data. The main application communicates
//! with this service through a named pipe at `\\.\pipe\HuGeScreenshot_FileSearch`.
//!
//! ## Components
//!
//! - `client`: Named pipe client with connection management and retry logic
//! - `types`: Protocol types compatible with the file-search-service
//! - `keyword_extractor`: Extract meaningful keywords from OCR text for search
//!
//! ## Usage
//!
//! ```no_run
//! use hugescreenshot_tauri_lib::file_search::{SearchClient, SearchQuery};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let mut client = SearchClient::new();
//!     client.connect().await?;
//!     
//!     let query = SearchQuery {
//!         keyword: "document".to_string(),
//!         ..Default::default()
//!     };
//!     let results = client.search(query).await?;
//!     
//!     for result in results {
//!         println!("{}: {}", result.name, result.path.display());
//!     }
//!     
//!     client.disconnect().await;
//!     Ok(())
//! }
//! ```
//!
//! **Validates: Requirements 4.2, 4.5, 7.3**

mod client;
pub mod indexer;
mod keyword_extractor;
mod types;

pub use client::{SearchClient, SearchClientError, SearchClientResult, PIPE_NAME};
pub use indexer::FileIndexer;
pub use keyword_extractor::{KeywordExtractionResult, KeywordExtractor};
pub use types::{
    ErrorCode, IndexConfig, MatchMode, Request, Response, RetryConfig, SearchFilters, SearchQuery,
    SearchResult, ServiceStatus, SortField, SortOrder,
};
