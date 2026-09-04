//! Error types for the file search service
//!
//! Defines all error types used throughout the service.

use thiserror::Error;

/// Main error type for the file search service
#[derive(Error, Debug)]
pub enum ServiceError {
    /// Service registration/control errors
    #[error("Service error: {0}")]
    Service(String),

    /// MFT scanning errors
    #[error("MFT scan error: {0}")]
    MftScan(String),

    /// USN Journal monitoring errors
    #[error("USN monitor error: {0}")]
    UsnMonitor(String),

    /// Index operation errors
    #[error("Index error: {0}")]
    Index(String),

    /// Query/search errors
    #[error("Query error: {0}")]
    Query(String),

    /// IPC/pipe communication errors
    #[error("IPC error: {0}")]
    Ipc(String),

    /// Configuration errors
    #[error("Config error: {0}")]
    Config(String),

    /// Persistence/storage errors
    #[error("Persistence error: {0}")]
    Persistence(String),

    /// IO errors
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    /// Serialization errors
    #[error("Serialization error: {0}")]
    Serialization(String),

    /// Windows API errors
    #[error("Windows API error: {0}")]
    WindowsApi(String),

    /// Access denied errors
    #[error("Access denied: {0}")]
    AccessDenied(String),

    /// Volume not NTFS
    #[error("Volume {0}: is not NTFS format")]
    VolumeNotNtfs(char),

    /// Volume offline/unavailable
    #[error("Volume {0}: is offline or unavailable")]
    VolumeOffline(char),
}

/// Result type alias for service operations
pub type ServiceResult<T> = Result<T, ServiceError>;

impl From<serde_json::Error> for ServiceError {
    fn from(err: serde_json::Error) -> Self {
        ServiceError::Serialization(err.to_string())
    }
}

impl From<bincode::Error> for ServiceError {
    fn from(err: bincode::Error) -> Self {
        ServiceError::Serialization(err.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = ServiceError::Service("test error".to_string());
        assert!(err.to_string().contains("test error"));
    }

    #[test]
    fn test_error_from_io() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file not found");
        let err: ServiceError = io_err.into();
        assert!(matches!(err, ServiceError::Io(_)));
    }
}
