//! 虎哥截图文件搜索索引服务
//!
//! Windows Service for fast file indexing using NTFS MFT and USN Journal.
//! Communicates with the main application via named pipes.
//!
//! # Architecture
//! - Runs as a Windows service with SYSTEM privileges
//! - Reads NTFS MFT for fast initial file scanning
//! - Monitors USN Journal for real-time file change updates
//! - Provides search functionality via named pipe IPC
//!
//! # Usage
//! This binary should not be run directly. Use the service installer:
//! ```
//! file-search-service.exe install  # Install as Windows service
//! file-search-service.exe uninstall  # Remove Windows service
//! ```

#![windows_subsystem = "windows"]

use std::ffi::OsString;
use tracing::{error, info};

mod config;
mod error;
mod index;
mod models;
mod monitor;
mod persistence;
mod pipe_server;
mod protocol;
mod query;
mod scanner;
mod service;

pub use config::*;
pub use error::*;
pub use index::*;
pub use models::*;
pub use monitor::*;
pub use persistence::*;
pub use pipe_server::*;
pub use protocol::*;
pub use query::*;
pub use scanner::*;
pub use service::*;

/// Service name used for Windows Service registration
pub const SERVICE_NAME: &str = "HuGeScreenshotFileSearch";

/// Display name shown in Windows Services management console
pub const SERVICE_DISPLAY_NAME: &str = "虎哥截图文件搜索服务";

/// Service description
pub const SERVICE_DESCRIPTION: &str =
    "提供快速文件搜索功能，通过读取 NTFS MFT 实现毫秒级全盘扫描";

/// Named pipe path for IPC communication
pub const PIPE_NAME: &str = r"\\.\pipe\HuGeScreenshot_FileSearch";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    init_logging()?;

    // Parse command line arguments
    let args: Vec<String> = std::env::args().collect();

    if args.len() > 1 {
        match args[1].as_str() {
            "install" => {
                info!("Installing service...");
                service::install_service()?;
                println!("Service installed successfully.");
                return Ok(());
            }
            "uninstall" => {
                info!("Uninstalling service...");
                service::uninstall_service()?;
                println!("Service uninstalled successfully.");
                return Ok(());
            }
            "run" => {
                // Run in foreground mode for debugging
                info!("Running in foreground mode...");
                run_foreground()?;
                return Ok(());
            }
            _ => {
                eprintln!("Usage: {} [install|uninstall|run]", args[0]);
                eprintln!("  install   - Install as Windows service");
                eprintln!("  uninstall - Remove Windows service");
                eprintln!("  run       - Run in foreground (for debugging)");
                return Ok(());
            }
        }
    }

    // No arguments - run as Windows service
    info!("Starting as Windows service...");
    service::run_service()?;

    Ok(())
}

/// Initialize logging to file
fn init_logging() -> Result<(), Box<dyn std::error::Error>> {
    use tracing_subscriber::{fmt, prelude::*, EnvFilter};

    // Determine log directory based on environment
    let log_dir = if cfg!(debug_assertions) {
        // Development: use project log directory
        std::path::PathBuf::from(r"D:\screenshot\日志\Rust版本日志")
    } else {
        // Production: use AppData directory
        dirs::data_local_dir()
            .unwrap_or_else(|| std::path::PathBuf::from("."))
            .join("HuGeScreenshot")
            .join("logs")
    };

    // Ensure log directory exists
    std::fs::create_dir_all(&log_dir)?;

    // Create file appender with daily rotation
    let file_appender = tracing_appender::rolling::daily(&log_dir, "file-search-service");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);

    // Build subscriber
    let subscriber = tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| {
            if cfg!(debug_assertions) {
                EnvFilter::new("debug")
            } else {
                EnvFilter::new("info")
            }
        }))
        .with(fmt::layer().with_writer(non_blocking).with_ansi(false));

    tracing::subscriber::set_global_default(subscriber)?;

    // Keep the guard alive for the lifetime of the program
    // Note: In a real service, we'd need to store this guard somewhere
    std::mem::forget(_guard);

    Ok(())
}

/// Run the service in foreground mode (for debugging)
fn run_foreground() -> Result<(), Box<dyn std::error::Error>> {
    use tokio::runtime::Runtime;

    let rt = Runtime::new()?;
    rt.block_on(async {
        info!("File search service starting in foreground mode...");

        // Create and start service runtime
        let config = ServiceConfig::default();
        let mut service_runtime = ServiceRuntime::new(config);
        let stop_signal = service_runtime.stop_signal();

        // Start all components
        service_runtime.start().await?;

        info!("Service running. Press Ctrl+C to stop.");

        // Wait for Ctrl+C
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                info!("Received Ctrl+C, stopping...");
            }
            _ = async {
                // Also check for rebuild requests periodically
                loop {
                    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                    if stop_signal.load(std::sync::atomic::Ordering::Relaxed) {
                        break;
                    }
                }
            } => {}
        }

        // Stop gracefully
        service_runtime.stop().await?;

        info!("Service stopped.");
        Ok::<(), Box<dyn std::error::Error>>(())
    })?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constants() {
        assert!(!SERVICE_NAME.is_empty());
        assert!(!SERVICE_DISPLAY_NAME.is_empty());
        assert!(PIPE_NAME.starts_with(r"\\.\pipe\"));
    }
}
