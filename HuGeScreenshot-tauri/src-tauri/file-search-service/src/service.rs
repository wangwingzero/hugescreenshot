//! Windows service implementation
//!
//! Handles service registration, lifecycle, and control.
//! Implements ServiceRuntime for managing MftScanner, UsnMonitor, and PipeServer.
//!
//! **Validates: Requirements 1.3, 1.6, 11.7**

use crate::config::ServiceConfig;
use crate::index::FileIndex;
use crate::models::ScanProgress;
use crate::monitor::UsnMonitor;
use crate::pipe_server::PipeServer;
use crate::scanner::MftScanner;
use crate::ServiceResult;

#[cfg(windows)]
use windows_service::{
    define_windows_service,
    service::{
        ServiceAccess, ServiceControl, ServiceControlAccept, ServiceErrorControl, ServiceExitCode,
        ServiceInfo, ServiceStartType, ServiceState, ServiceStatus, ServiceType,
    },
    service_control_handler::{self, ServiceControlHandlerResult, ServiceStatusHandle},
    service_dispatcher,
    service_manager::{ServiceManager, ServiceManagerAccess},
};

use std::ffi::OsString;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

// =============================================================================
// Service Logging Initialization
// =============================================================================

/// Initialize logging for the service thread
/// This must be called from within the service thread, not the main thread
#[cfg(windows)]
fn init_service_logging() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use tracing_subscriber::{fmt, prelude::*, EnvFilter};

    // Use ProgramData directory for service logs (service runs as SYSTEM)
    // IMPORTANT: Use environment variable, not hardcoded path!
    // Service's working directory is C:\Windows\System32, so relative paths won't work
    let program_data = std::env::var("ProgramData").unwrap_or_else(|_| "C:\\ProgramData".to_string());
    let log_dir = std::path::PathBuf::from(&program_data)
        .join("HuGeScreenshot")
        .join("logs");

    // Ensure log directory exists (create_dir_all handles missing parents)
    std::fs::create_dir_all(&log_dir)?;

    // Create file appender with daily rotation
    let file_appender = tracing_appender::rolling::daily(&log_dir, "file-search-service");
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    // Build subscriber
    let subscriber = tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with(fmt::layer().with_writer(non_blocking).with_ansi(false));

    // Try to set global default, ignore error if already set
    let _ = tracing::subscriber::set_global_default(subscriber);

    // Keep the guard alive for the lifetime of the service
    std::mem::forget(guard);

    Ok(())
}

// =============================================================================
// ServiceRuntime - Manages all service components
// =============================================================================

/// Service runtime that manages all components
///
/// Integrates MftScanner, UsnMonitor, and PipeServer for the file search service.
/// Handles startup (index loading/scanning) and graceful shutdown (index saving).
///
/// **Validates: Requirements 1.3, 1.6, 11.7**
pub struct ServiceRuntime {
    /// Service configuration
    config: ServiceConfig,

    /// File index (shared across all components)
    index: Arc<RwLock<FileIndex>>,

    /// MFT scanner for initial/rebuild scans
    mft_scanner: MftScanner,

    /// USN monitor for real-time updates
    usn_monitor: Option<UsnMonitor>,

    /// Pipe server for client communication
    pipe_server: Option<PipeServer>,

    /// Global stop signal
    stop_signal: Arc<AtomicBool>,

    /// Flag indicating if initial scan is complete
    scan_complete: Arc<AtomicBool>,
}

impl ServiceRuntime {
    /// Create a new service runtime with the given configuration
    ///
    /// Initializes all components but does not start them.
    pub fn new(config: ServiceConfig) -> Self {
        let index = Arc::new(RwLock::new(FileIndex::new()));
        let stop_signal = Arc::new(AtomicBool::new(false));

        // Create MFT scanner with configured volumes and exclusions
        let mft_scanner = MftScanner::new(
            config.index.volumes.clone(),
            config.index.exclude_paths.clone(),
        );

        Self {
            config,
            index,
            mft_scanner,
            usn_monitor: None,
            pipe_server: None,
            stop_signal,
            scan_complete: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Get the stop signal for external control
    pub fn stop_signal(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.stop_signal)
    }

    /// Check if the service is stopped
    pub fn is_stopped(&self) -> bool {
        self.stop_signal.load(Ordering::Relaxed)
    }

    /// Start all service components
    ///
    /// This method:
    /// 1. Loads existing index from disk if available
    /// 2. If no index exists, performs initial MFT scan
    /// 3. Starts USN monitor for real-time updates
    /// 4. Starts pipe server for client connections
    ///
    /// **Validates: Requirements 1.3** (auto-start), **1.6** (status query)
    pub async fn start(&mut self) -> ServiceResult<()> {
        info!("Starting service runtime...");

        // Step 1: Load or build index
        self.load_or_scan_index().await?;

        // Step 2: Start USN monitor
        self.start_usn_monitor().await?;

        // Step 3: Start pipe server
        self.start_pipe_server().await?;

        info!("Service runtime started successfully");
        Ok(())
    }

    /// Stop all service components gracefully
    ///
    /// This method:
    /// 1. Signals all components to stop
    /// 2. Waits for components to finish
    /// 3. Saves index to disk
    ///
    /// **Validates: Requirements 11.7** (graceful shutdown without data loss)
    pub async fn stop(&mut self) -> ServiceResult<()> {
        info!("Stopping service runtime...");

        // Signal all components to stop
        self.stop_signal.store(true, Ordering::Relaxed);

        // Stop USN monitor
        if let Some(ref monitor) = self.usn_monitor {
            info!("Stopping USN monitor...");
            monitor.stop();
        }

        // Stop pipe server
        if let Some(ref server) = self.pipe_server {
            info!("Stopping pipe server...");
            server.stop();
        }

        // Give components time to stop gracefully
        tokio::time::sleep(Duration::from_millis(500)).await;

        // Save index to disk
        self.save_index().await?;

        info!("Service runtime stopped successfully");
        Ok(())
    }

    /// Load existing index from disk or perform initial scan
    ///
    /// **Validates: Requirements 10.5** (persist index for faster startup)
    async fn load_or_scan_index(&mut self) -> ServiceResult<()> {
        let index_path = &self.config.index_path;

        // Try to load existing index
        if FileIndex::index_file_exists(index_path) {
            info!("Found existing index at {:?}, loading...", index_path);

            match FileIndex::load_from_disk(index_path) {
                Ok(loaded_index) => {
                    let stats = loaded_index.stats();
                    info!(
                        "Loaded index: {} files, {} directories",
                        stats.total_files, stats.total_directories
                    );

                    // Replace the index
                    let mut index_guard = self.index.write().await;
                    *index_guard = loaded_index;
                    drop(index_guard);

                    self.scan_complete.store(true, Ordering::Relaxed);
                    return Ok(());
                }
                Err(e) => {
                    warn!("Failed to load index: {}. Will perform fresh scan.", e);
                }
            }
        } else {
            info!("No existing index found at {:?}", index_path);
        }

        // Perform initial MFT scan
        self.perform_initial_scan().await
    }

    /// Perform initial MFT scan
    async fn perform_initial_scan(&mut self) -> ServiceResult<()> {
        info!("Starting initial MFT scan...");

        // Create progress channel
        let (progress_tx, mut progress_rx) = tokio::sync::mpsc::channel::<ScanProgress>(100);

        // Spawn progress reporter task
        let scan_complete = Arc::clone(&self.scan_complete);
        tokio::spawn(async move {
            while let Some(progress) = progress_rx.recv().await {
                debug!(
                    "Scan progress: volume={}, files={}, elapsed={}ms",
                    progress.volume, progress.scanned_files, progress.elapsed_ms
                );
            }
            scan_complete.store(true, Ordering::Relaxed);
        });

        // Perform scan
        let mut index_guard = self.index.write().await;
        self.mft_scanner.scan_all(&mut index_guard, progress_tx).await?;

        let stats = index_guard.stats();
        info!(
            "Initial scan complete: {} files, {} directories",
            stats.total_files, stats.total_directories
        );

        // Update last full scan timestamp
        index_guard.stats_mut().last_full_scan = Some(chrono::Utc::now());

        drop(index_guard);

        // Save index after initial scan
        self.save_index().await?;

        Ok(())
    }

    /// Start the USN monitor for real-time updates
    async fn start_usn_monitor(&mut self) -> ServiceResult<()> {
        info!("Starting USN monitor...");

        // Create overflow channel for journal overflow notifications
        let (overflow_tx, mut overflow_rx) = tokio::sync::mpsc::channel::<char>(10);

        // Create USN monitor
        let volumes = if self.config.index.volumes.is_empty() {
            MftScanner::get_ntfs_volumes()
        } else {
            self.config.index.volumes.clone()
        };

        let monitor = UsnMonitor::with_overflow_channel(volumes.clone(), overflow_tx);

        // Store the monitor
        self.usn_monitor = Some(monitor);

        // Spawn USN monitor task
        let index = Arc::clone(&self.index);

        // Create a new monitor instance for the task (since we can't move the reference)
        let task_monitor = UsnMonitor::new(volumes);
        let task_stop_signal = task_monitor.stop_signal();

        // Link the stop signals
        let linked_stop = Arc::clone(&self.stop_signal);
        tokio::spawn(async move {
            // Wait for global stop signal and propagate to monitor
            while !linked_stop.load(Ordering::Relaxed) {
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
            task_stop_signal.store(true, Ordering::Relaxed);
        });

        // Spawn the actual monitor task
        tokio::spawn(async move {
            if let Err(e) = task_monitor.start(index).await {
                error!("USN monitor error: {}", e);
            }
        });

        // Spawn overflow handler task
        let index_for_overflow = Arc::clone(&self.index);
        let config_excludes = self.config.index.exclude_paths.clone();

        tokio::spawn(async move {
            while let Some(volume) = overflow_rx.recv().await {
                warn!("USN Journal overflow on volume {}, triggering rescan", volume);

                // Perform partial rescan for the affected volume
                let scanner = MftScanner::new(vec![volume], config_excludes.clone());
                let (_tx, _rx) = tokio::sync::mpsc::channel::<ScanProgress>(1);

                let mut index_guard = index_for_overflow.write().await;
                if let Err(e) = scanner.scan_volume(volume, &mut index_guard).await {
                    error!("Failed to rescan volume {}: {}", volume, e);
                }
            }
        });

        info!("USN monitor started");
        Ok(())
    }

    /// Start the pipe server for client connections
    async fn start_pipe_server(&mut self) -> ServiceResult<()> {
        info!("Starting pipe server on {}...", self.config.pipe_name);

        let server = PipeServer::new(self.config.pipe_name.clone(), Arc::clone(&self.index));

        // Store the server
        self.pipe_server = Some(server);

        // Create a new server instance for the task
        let task_server = PipeServer::new(self.config.pipe_name.clone(), Arc::clone(&self.index));

        tokio::spawn(async move {
            // Start the server
            if let Err(e) = task_server.start().await {
                error!("Pipe server error: {}", e);
            }
        });

        info!("Pipe server started");
        Ok(())
    }

    /// Save the current index to disk
    ///
    /// **Validates: Requirements 11.7** (graceful shutdown without data loss)
    pub async fn save_index(&self) -> ServiceResult<()> {
        info!("Saving index to {:?}...", self.config.index_path);

        let index_guard = self.index.read().await;
        index_guard.save_to_disk(&self.config.index_path)?;

        let stats = index_guard.stats();
        info!(
            "Index saved: {} files, {} directories",
            stats.total_files, stats.total_directories
        );

        Ok(())
    }

    /// Trigger a full index rebuild
    pub async fn rebuild_index(&mut self) -> ServiceResult<()> {
        info!("Rebuilding index...");

        // Clear existing index
        {
            let mut index_guard = self.index.write().await;
            index_guard.clear();
        }

        // Perform fresh scan
        self.perform_initial_scan().await
    }

    /// Get the current index statistics
    pub async fn get_stats(&self) -> crate::models::IndexStats {
        let index_guard = self.index.read().await;
        index_guard.stats().clone()
    }

    /// Check if initial scan is complete
    pub fn is_scan_complete(&self) -> bool {
        self.scan_complete.load(Ordering::Relaxed)
    }
}

/// Run as a Windows service
#[cfg(windows)]
pub fn run_service() -> ServiceResult<()> {
    // Register the service entry point
    service_dispatcher::start(crate::SERVICE_NAME, ffi_service_main)
        .map_err(|e| crate::ServiceError::Service(format!("Failed to start service: {}", e)))?;
    Ok(())
}

#[cfg(not(windows))]
pub fn run_service() -> ServiceResult<()> {
    Err(crate::ServiceError::Service(
        "Windows service is only supported on Windows".to_string(),
    ))
}

/// Install the service
#[cfg(windows)]
pub fn install_service() -> ServiceResult<()> {
    let manager_access = ServiceManagerAccess::CONNECT | ServiceManagerAccess::CREATE_SERVICE;
    let service_manager = ServiceManager::local_computer(None::<&str>, manager_access)
        .map_err(|e| crate::ServiceError::Service(format!("Failed to connect to SCM: {}", e)))?;

    // Get the path to the current executable
    let service_binary_path = std::env::current_exe()
        .map_err(|e| crate::ServiceError::Service(format!("Failed to get exe path: {}", e)))?;

    let service_info = ServiceInfo {
        name: OsString::from(crate::SERVICE_NAME),
        display_name: OsString::from(crate::SERVICE_DISPLAY_NAME),
        service_type: ServiceType::OWN_PROCESS,
        start_type: ServiceStartType::AutoStart,
        error_control: ServiceErrorControl::Normal,
        executable_path: service_binary_path,
        launch_arguments: vec![],
        dependencies: vec![],
        account_name: None, // LocalSystem account
        account_password: None,
    };

    let service = service_manager
        .create_service(&service_info, ServiceAccess::CHANGE_CONFIG)
        .map_err(|e| crate::ServiceError::Service(format!("Failed to create service: {}", e)))?;

    // Set service description
    service
        .set_description(crate::SERVICE_DESCRIPTION)
        .map_err(|e| {
            crate::ServiceError::Service(format!("Failed to set description: {}", e))
        })?;

    info!("Service installed successfully");
    Ok(())
}

#[cfg(not(windows))]
pub fn install_service() -> ServiceResult<()> {
    Err(crate::ServiceError::Service(
        "Windows service is only supported on Windows".to_string(),
    ))
}

/// Uninstall the service
#[cfg(windows)]
pub fn uninstall_service() -> ServiceResult<()> {
    let manager_access = ServiceManagerAccess::CONNECT;
    let service_manager = ServiceManager::local_computer(None::<&str>, manager_access)
        .map_err(|e| crate::ServiceError::Service(format!("Failed to connect to SCM: {}", e)))?;

    let service_access = ServiceAccess::QUERY_STATUS | ServiceAccess::STOP | ServiceAccess::DELETE;
    let service = service_manager
        .open_service(crate::SERVICE_NAME, service_access)
        .map_err(|e| crate::ServiceError::Service(format!("Failed to open service: {}", e)))?;

    // Stop the service if it's running
    let service_status = service
        .query_status()
        .map_err(|e| crate::ServiceError::Service(format!("Failed to query status: {}", e)))?;

    if service_status.current_state != ServiceState::Stopped {
        service.stop().map_err(|e| {
            crate::ServiceError::Service(format!("Failed to stop service: {}", e))
        })?;

        // Wait for the service to stop
        let mut attempts = 0;
        while attempts < 30 {
            std::thread::sleep(Duration::from_secs(1));
            let status = service.query_status().map_err(|e| {
                crate::ServiceError::Service(format!("Failed to query status: {}", e))
            })?;
            if status.current_state == ServiceState::Stopped {
                break;
            }
            attempts += 1;
        }
    }

    // Delete the service
    service
        .delete()
        .map_err(|e| crate::ServiceError::Service(format!("Failed to delete service: {}", e)))?;

    info!("Service uninstalled successfully");
    Ok(())
}

#[cfg(not(windows))]
pub fn uninstall_service() -> ServiceResult<()> {
    Err(crate::ServiceError::Service(
        "Windows service is only supported on Windows".to_string(),
    ))
}

// Windows service entry point
#[cfg(windows)]
define_windows_service!(ffi_service_main, service_main);

#[cfg(windows)]
fn service_main(arguments: Vec<OsString>) {
    if let Err(e) = run_service_main(arguments) {
        error!("Service main error: {}", e);
    }
}

#[cfg(windows)]
fn run_service_main(_arguments: Vec<OsString>) -> ServiceResult<()> {
    // Initialize logging in the service thread
    // This is critical because the main thread's logging may not be available here
    if let Err(e) = init_service_logging() {
        // Can't log the error, but we can try to continue
        eprintln!("Failed to initialize service logging: {}", e);
    }

    // Write a debug marker to confirm logging is working
    info!("=== Service thread started, logging initialized ===");

    // Create a channel for shutdown signal
    let (shutdown_tx, shutdown_rx) = std::sync::mpsc::channel();
    info!("Shutdown channel created");

    // Register service control handler
    let event_handler = move |control_event| -> ServiceControlHandlerResult {
        match control_event {
            ServiceControl::Stop => {
                info!("Received stop signal");
                let _ = shutdown_tx.send(());
                ServiceControlHandlerResult::NoError
            }
            ServiceControl::Interrogate => ServiceControlHandlerResult::NoError,
            _ => ServiceControlHandlerResult::NotImplemented,
        }
    };

    info!("Registering service control handler...");
    let status_handle = service_control_handler::register(crate::SERVICE_NAME, event_handler)
        .map_err(|e| {
            error!("Failed to register control handler: {}", e);
            crate::ServiceError::Service(format!("Failed to register control handler: {}", e))
        })?;
    info!("Service control handler registered");

    // Report service as starting
    info!("Reporting StartPending status...");
    report_service_status(&status_handle, ServiceState::StartPending, 0, Duration::from_secs(30))?;
    info!("StartPending status reported");

    // Create tokio runtime for async operations
    info!("Creating tokio runtime...");
    let runtime = tokio::runtime::Runtime::new().map_err(|e| {
        error!("Failed to create tokio runtime: {}", e);
        crate::ServiceError::Service(format!("Failed to create tokio runtime: {}", e))
    })?;
    info!("Tokio runtime created");

    // Initialize service runtime
    info!("Creating ServiceConfig...");
    let config = ServiceConfig::default();
    info!("ServiceConfig created: index_path={:?}, pipe_name={}", config.index_path, config.pipe_name);
    
    info!("Creating ServiceRuntime...");
    let mut service_runtime = ServiceRuntime::new(config);
    let stop_signal = service_runtime.stop_signal();
    info!("ServiceRuntime created");

    // Start service components in the runtime
    info!("Starting service components...");
    let start_result = runtime.block_on(async {
        service_runtime.start().await
    });

    if let Err(e) = start_result {
        error!("Failed to start service runtime: {}", e);
        report_service_status(&status_handle, ServiceState::Stopped, 1, Duration::default())?;
        return Err(e);
    }

    // Report service as running
    report_service_status(&status_handle, ServiceState::Running, 0, Duration::default())?;
    info!("Service started successfully");

    // Spawn a task to wait for shutdown signal and trigger stop
    let stop_signal_clone = Arc::clone(&stop_signal);
    std::thread::spawn(move || {
        let _ = shutdown_rx.recv();
        info!("Shutdown signal received, triggering stop...");
        stop_signal_clone.store(true, Ordering::Relaxed);
    });

    // Run the main service loop
    runtime.block_on(async {
        // Wait for stop signal
        while !stop_signal.load(Ordering::Relaxed) {
            tokio::time::sleep(Duration::from_millis(100)).await;

            // Check for rebuild requests from pipe server
            if let Some(ref server) = service_runtime.pipe_server {
                if server.is_rebuild_requested() {
                    info!("Index rebuild requested via pipe server");
                    server.clear_rebuild_request();
                    if let Err(e) = service_runtime.rebuild_index().await {
                        error!("Failed to rebuild index: {}", e);
                    }
                }
            }
        }

        // Report service as stopping
        let _ = report_service_status(&status_handle, ServiceState::StopPending, 0, Duration::from_secs(30));

        // Stop service runtime gracefully
        if let Err(e) = service_runtime.stop().await {
            error!("Error during service shutdown: {}", e);
        }
    });

    // Report service as stopped
    report_service_status(&status_handle, ServiceState::Stopped, 0, Duration::default())?;
    info!("Service stopped");

    Ok(())
}

/// Helper function to report service status
#[cfg(windows)]
fn report_service_status(
    status_handle: &ServiceStatusHandle,
    current_state: ServiceState,
    exit_code: u32,
    wait_hint: Duration,
) -> ServiceResult<()> {
    let controls_accepted = if current_state == ServiceState::Running {
        ServiceControlAccept::STOP
    } else {
        ServiceControlAccept::empty()
    };

    status_handle
        .set_service_status(ServiceStatus {
            service_type: ServiceType::OWN_PROCESS,
            current_state,
            controls_accepted,
            exit_code: ServiceExitCode::Win32(exit_code),
            checkpoint: 0,
            wait_hint,
            process_id: None,
        })
        .map_err(|e| crate::ServiceError::Service(format!("Failed to set status: {}", e)))?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // Service tests require elevated privileges and are typically run manually
    // or in a CI environment with appropriate permissions

    #[test]
    fn test_service_constants() {
        assert!(!crate::SERVICE_NAME.is_empty());
        assert!(!crate::SERVICE_DISPLAY_NAME.is_empty());
    }

    #[test]
    fn test_service_runtime_creation() {
        let config = ServiceConfig::default();
        let runtime = ServiceRuntime::new(config);

        assert!(!runtime.is_stopped());
        assert!(!runtime.is_scan_complete());
    }

    #[test]
    fn test_service_runtime_stop_signal() {
        let config = ServiceConfig::default();
        let runtime = ServiceRuntime::new(config);

        let stop_signal = runtime.stop_signal();
        assert!(!stop_signal.load(Ordering::Relaxed));

        stop_signal.store(true, Ordering::Relaxed);
        assert!(runtime.is_stopped());
    }

    #[tokio::test]
    async fn test_service_runtime_get_stats() {
        let config = ServiceConfig::default();
        let runtime = ServiceRuntime::new(config);

        let stats = runtime.get_stats().await;
        assert_eq!(stats.total_files, 0);
        assert_eq!(stats.total_directories, 0);
    }

    #[tokio::test]
    async fn test_service_runtime_save_index_empty() {
        use tempfile::tempdir;

        let dir = tempdir().unwrap();
        let index_path = dir.path().join("test_index.hgfs");

        let mut config = ServiceConfig::default();
        config.index_path = index_path.clone();

        let runtime = ServiceRuntime::new(config);

        // Save empty index should succeed
        let result = runtime.save_index().await;
        assert!(result.is_ok());
        assert!(index_path.exists());
    }
}
