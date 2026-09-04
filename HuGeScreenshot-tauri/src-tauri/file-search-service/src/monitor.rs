//! USN Journal Monitor
//!
//! Monitors NTFS USN Journal for real-time file change detection.
//! Uses Windows API (DeviceIoControl with FSCTL_READ_USN_JOURNAL) to read USN records.
//!
//! **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;

use chrono::Utc;
use tokio::sync::mpsc::Sender;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

use crate::index::FileIndex;
use crate::models::{FileEntry, UsnEvent};
use crate::scanner::MftScanner;
use crate::{ServiceError, ServiceResult};

#[cfg(windows)]
use windows::core::PCWSTR;
#[cfg(windows)]
use windows::Win32::Foundation::{CloseHandle, HANDLE};
#[cfg(windows)]
use windows::Win32::Storage::FileSystem::{
    CreateFileW, FILE_FLAG_BACKUP_SEMANTICS, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
};
#[cfg(windows)]
use windows::Win32::System::IO::DeviceIoControl;

/// USN Reason flags
const USN_REASON_FILE_CREATE: u32 = 0x00000100;
const USN_REASON_FILE_DELETE: u32 = 0x00000200;
const USN_REASON_DATA_EXTEND: u32 = 0x00000002;
const USN_REASON_DATA_TRUNCATION: u32 = 0x00000004;
const USN_REASON_RENAME_OLD_NAME: u32 = 0x00001000;
const USN_REASON_RENAME_NEW_NAME: u32 = 0x00002000;
const USN_REASON_CLOSE: u32 = 0x80000000;

/// FSCTL codes
#[cfg(windows)]
const FSCTL_QUERY_USN_JOURNAL: u32 = 0x000900f4;
#[cfg(windows)]
const FSCTL_READ_USN_JOURNAL: u32 = 0x000900bb;

/// Error code for journal entry deleted (overflow)
#[cfg(windows)]
const ERROR_JOURNAL_ENTRY_DELETED: u32 = 1181;

/// USN Journal data structure returned by FSCTL_QUERY_USN_JOURNAL
#[repr(C)]
#[derive(Debug, Clone, Copy)]
struct UsnJournalData {
    usn_journal_id: u64,
    first_usn: i64,
    next_usn: i64,
    lowest_valid_usn: i64,
    max_usn: i64,
    maximum_size: u64,
    allocation_delta: u64,
}

/// Read USN Journal data structure for FSCTL_READ_USN_JOURNAL
#[repr(C)]
#[derive(Debug, Clone, Copy)]
struct ReadUsnJournalData {
    start_usn: i64,
    reason_mask: u32,
    return_only_on_close: u32,
    timeout: u64,
    bytes_to_wait_for: u64,
    usn_journal_id: u64,
}

/// USN Record V2 structure (most common)
#[repr(C)]
#[derive(Debug)]
struct UsnRecordV2 {
    record_length: u32,
    major_version: u16,
    minor_version: u16,
    file_reference_number: u64,
    parent_file_reference_number: u64,
    usn: i64,
    time_stamp: i64,
    reason: u32,
    source_info: u32,
    security_id: u32,
    file_attributes: u32,
    file_name_length: u16,
    file_name_offset: u16,
    // file_name follows (variable length, UTF-16)
}

/// State for tracking rename operations (old name -> new name)
#[derive(Debug, Clone)]
struct RenameState {
    file_id: u64,
    old_name: String,
    old_parent_id: u64,
    timestamp: Instant,
}

/// Batch of USN events sent from blocking thread to async processor
#[derive(Debug)]
enum UsnEventBatch {
    /// A batch of USN events to process
    Events(Vec<(UsnEvent, char)>), // (event, volume)
    /// Journal overflow notification
    Overflow(char),
}

/// USN Journal monitor for real-time file change detection
///
/// Monitors NTFS USN Journal for file system changes and updates the FileIndex
/// in real-time (within 100ms of change).
///
/// **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
pub struct UsnMonitor {
    /// Volumes to monitor
    volumes: Vec<char>,

    /// Stop signal for graceful shutdown
    stop_signal: Arc<AtomicBool>,

    /// Channel to notify about journal overflow (triggers rescan)
    overflow_tx: Option<Sender<char>>,
}

impl UsnMonitor {
    /// Create a new USN monitor
    pub fn new(volumes: Vec<char>) -> Self {
        Self {
            volumes,
            stop_signal: Arc::new(AtomicBool::new(false)),
            overflow_tx: None,
        }
    }

    /// Create a new USN monitor with overflow notification channel
    pub fn with_overflow_channel(volumes: Vec<char>, overflow_tx: Sender<char>) -> Self {
        Self {
            volumes,
            stop_signal: Arc::new(AtomicBool::new(false)),
            overflow_tx: Some(overflow_tx),
        }
    }

    /// Get the stop signal for external control
    pub fn stop_signal(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.stop_signal)
    }

    /// Start monitoring all volumes
    ///
    /// This method runs in a loop, reading USN Journal entries and updating
    /// the FileIndex in real-time.
    ///
    /// **Validates: Requirements 3.1** (continuous monitoring)
    pub async fn start(&self, index: Arc<RwLock<FileIndex>>) -> ServiceResult<()> {
        info!("Starting USN monitor for volumes: {:?}", self.volumes);

        let volumes_to_monitor: Vec<char> = if self.volumes.is_empty() {
            MftScanner::get_ntfs_volumes()
        } else {
            self.volumes
                .iter()
                .filter(|&&v| MftScanner::is_ntfs_volume(v))
                .copied()
                .collect()
        };

        if volumes_to_monitor.is_empty() {
            warn!("No NTFS volumes found to monitor");
            return Ok(());
        }

        info!(
            "Will monitor {} NTFS volumes: {:?}",
            volumes_to_monitor.len(),
            volumes_to_monitor
        );

        // Create event channel for receiving events from blocking threads
        let (event_tx, mut event_rx) = tokio::sync::mpsc::channel::<UsnEventBatch>(1000);

        // Start monitoring each volume in a blocking thread
        let mut handles = Vec::new();

        for volume in volumes_to_monitor {
            let stop_signal = Arc::clone(&self.stop_signal);
            let overflow_tx = self.overflow_tx.clone();
            let event_tx_clone = event_tx.clone();

            let handle = tokio::task::spawn_blocking(move || {
                VolumeMonitor::monitor_volume_blocking(
                    volume,
                    stop_signal,
                    overflow_tx,
                    event_tx_clone,
                )
            });

            handles.push(handle);
        }

        // Drop the original sender so the channel closes when all threads finish
        drop(event_tx);

        // Process events asynchronously
        while let Some(batch) = event_rx.recv().await {
            match batch {
                UsnEventBatch::Events(events) => {
                    for (event, volume) in events {
                        if let Err(e) = Self::process_event(event, volume, &index).await {
                            error!("Error processing USN event: {}", e);
                        }
                    }
                }
                UsnEventBatch::Overflow(volume) => {
                    warn!("Volume {}: Journal overflow notification received", volume);
                }
            }
        }

        // Wait for all blocking threads to finish
        for handle in handles {
            match handle.await {
                Ok(result) => {
                    if let Err(e) = result {
                        error!("Volume monitor error: {}", e);
                    }
                }
                Err(e) => {
                    error!("Volume monitor thread panicked: {}", e);
                }
            }
        }

        info!("USN monitor stopped");
        Ok(())
    }

    /// Stop monitoring
    pub fn stop(&self) {
        info!("Stopping USN monitor");
        self.stop_signal.store(true, Ordering::Relaxed);
    }

    /// Check if monitoring is stopped
    pub fn is_stopped(&self) -> bool {
        self.stop_signal.load(Ordering::Relaxed)
    }

    /// Process a single USN event and update the FileIndex
    ///
    /// **Validates: Requirements 3.2, 3.3, 3.4, 3.5** (update within 100ms)
    async fn process_event(
        event: UsnEvent,
        volume: char,
        index: &Arc<RwLock<FileIndex>>,
    ) -> ServiceResult<()> {
        let mut index_guard = index.write().await;

        match event {
            UsnEvent::FileCreated {
                file_id,
                parent_id,
                name,
            } => {
                let entry = FileEntry::new(
                    file_id,
                    parent_id,
                    name.clone(),
                    0, // Size unknown
                    Utc::now(),
                    Utc::now(),
                    false, // Assume file, not directory
                    volume,
                );
                index_guard.insert(entry);
                debug!("Index: Added file {} (id={})", name, file_id);
            }

            UsnEvent::FileDeleted { file_id } => {
                if let Some(entry) = index_guard.remove(file_id) {
                    debug!("Index: Removed file {} (id={})", entry.name, file_id);
                }
            }

            UsnEvent::FileRenamed {
                file_id,
                old_name,
                new_name,
            } => {
                if let Some(entry) = index_guard.get(file_id).cloned() {
                    let updated_entry = FileEntry::new(
                        entry.file_id,
                        entry.parent_id,
                        new_name.clone(),
                        entry.size,
                        entry.created,
                        Utc::now(),
                        entry.is_directory,
                        entry.volume,
                    );
                    index_guard.update(file_id, updated_entry);
                    debug!(
                        "Index: Renamed file {} -> {} (id={})",
                        old_name, new_name, file_id
                    );
                }
            }

            UsnEvent::FileMoved {
                file_id,
                old_parent,
                new_parent,
            } => {
                if let Some(entry) = index_guard.get(file_id).cloned() {
                    let updated_entry = FileEntry::new(
                        entry.file_id,
                        new_parent,
                        entry.name.clone(),
                        entry.size,
                        entry.created,
                        Utc::now(),
                        entry.is_directory,
                        entry.volume,
                    );
                    index_guard.update(file_id, updated_entry);
                    debug!(
                        "Index: Moved file {} from parent {} to {} (id={})",
                        entry.name, old_parent, new_parent, file_id
                    );
                }
            }
        }

        // Update last update timestamp
        index_guard.stats_mut().last_update = Utc::now();

        Ok(())
    }
}

/// Per-volume USN Journal monitor (runs in blocking thread)
struct VolumeMonitor;

impl VolumeMonitor {
    /// Monitor a single volume's USN Journal (blocking implementation)
    #[cfg(windows)]
    fn monitor_volume_blocking(
        volume: char,
        stop_signal: Arc<AtomicBool>,
        overflow_tx: Option<Sender<char>>,
        event_tx: tokio::sync::mpsc::Sender<UsnEventBatch>,
    ) -> ServiceResult<()> {
        use std::thread;

        info!("Starting USN monitor for volume {}:", volume);

        // Open volume handle
        let volume_path = format!(r"\\.\{}:", volume);
        let handle = Self::open_volume_handle(&volume_path)?;

        // Query initial journal state
        let journal_data = Self::query_journal_state(handle, volume)?;
        let mut journal_id = journal_data.usn_journal_id;
        let mut next_usn = journal_data.next_usn;

        info!(
            "Volume {}: Journal ID={}, NextUSN={}",
            volume, journal_id, next_usn
        );

        // Main monitoring loop
        let mut buffer = vec![0u8; 64 * 1024]; // 64KB buffer
        let poll_interval = std::time::Duration::from_millis(50);
        let mut pending_renames: HashMap<u64, RenameState> = HashMap::new();

        while !stop_signal.load(Ordering::Relaxed) {
            match Self::read_usn_journal(handle, &mut buffer, next_usn, journal_id) {
                Ok((bytes_read, new_next_usn)) => {
                    next_usn = new_next_usn;
                    if bytes_read > 8 {
                        let events = Self::parse_usn_buffer(
                            &buffer[..bytes_read],
                            volume,
                            &mut pending_renames,
                        );
                        if !events.is_empty() {
                            let _ = event_tx.blocking_send(UsnEventBatch::Events(events));
                        }
                    }
                }
                Err(ServiceError::UsnMonitor(msg)) if msg.contains("JOURNAL_ENTRY_DELETED") => {
                    warn!("Volume {}: USN Journal overflow detected", volume);

                    // Re-query journal state
                    match Self::query_journal_state(handle, volume) {
                        Ok(new_data) => {
                            if new_data.usn_journal_id != journal_id {
                                warn!("Volume {}: Journal ID changed, full rescan needed", volume);
                                journal_id = new_data.usn_journal_id;
                            }
                            next_usn = new_data.first_usn;
                            info!("Volume {}: Resuming from USN {}", volume, next_usn);
                        }
                        Err(e) => {
                            error!("Volume {}: Failed to re-query journal: {}", volume, e);
                        }
                    }

                    // Notify about overflow
                    if let Some(ref tx) = overflow_tx {
                        let _ = tx.blocking_send(volume);
                    }
                    let _ = event_tx.blocking_send(UsnEventBatch::Overflow(volume));
                }
                Err(e) => {
                    error!("Volume {}: Error reading USN journal: {}", volume, e);
                    thread::sleep(std::time::Duration::from_secs(1));
                }
            }

            // Clean up stale pending renames
            Self::cleanup_stale_renames(&mut pending_renames);

            thread::sleep(poll_interval);
        }

        // Close handle
        unsafe {
            let _ = CloseHandle(handle);
        }

        info!("Volume {}: USN monitor stopped", volume);
        Ok(())
    }

    #[cfg(not(windows))]
    fn monitor_volume_blocking(
        _volume: char,
        _stop_signal: Arc<AtomicBool>,
        _overflow_tx: Option<Sender<char>>,
        _event_tx: tokio::sync::mpsc::Sender<UsnEventBatch>,
    ) -> ServiceResult<()> {
        warn!("USN Journal monitoring is only supported on Windows");
        Ok(())
    }

    /// Open a handle to the volume for USN Journal access
    #[cfg(windows)]
    fn open_volume_handle(volume_path: &str) -> ServiceResult<HANDLE> {
        use windows::Win32::Foundation::GENERIC_READ;

        let path_wide: Vec<u16> = volume_path
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect();

        let handle = unsafe {
            CreateFileW(
                PCWSTR::from_raw(path_wide.as_ptr()),
                GENERIC_READ.0,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
        };

        match handle {
            Ok(h) => {
                debug!("Opened volume handle for {}", volume_path);
                Ok(h)
            }
            Err(e) => Err(ServiceError::UsnMonitor(format!(
                "Failed to open volume {}: {}",
                volume_path, e
            ))),
        }
    }

    /// Query the current USN Journal state
    #[cfg(windows)]
    fn query_journal_state(handle: HANDLE, volume: char) -> ServiceResult<UsnJournalData> {
        let mut journal_data = UsnJournalData {
            usn_journal_id: 0,
            first_usn: 0,
            next_usn: 0,
            lowest_valid_usn: 0,
            max_usn: 0,
            maximum_size: 0,
            allocation_delta: 0,
        };
        let mut bytes_returned: u32 = 0;

        let result = unsafe {
            DeviceIoControl(
                handle,
                FSCTL_QUERY_USN_JOURNAL,
                None,
                0,
                Some(&mut journal_data as *mut _ as *mut _),
                std::mem::size_of::<UsnJournalData>() as u32,
                Some(&mut bytes_returned),
                None,
            )
        };

        if result.is_ok() {
            Ok(journal_data)
        } else {
            Err(ServiceError::UsnMonitor(format!(
                "Failed to query USN journal for volume {}: {:?}",
                volume, result
            )))
        }
    }

    /// Read USN Journal records
    #[cfg(windows)]
    fn read_usn_journal(
        handle: HANDLE,
        buffer: &mut [u8],
        start_usn: i64,
        journal_id: u64,
    ) -> ServiceResult<(usize, i64)> {
        let read_data = ReadUsnJournalData {
            start_usn,
            reason_mask: USN_REASON_FILE_CREATE
                | USN_REASON_FILE_DELETE
                | USN_REASON_RENAME_OLD_NAME
                | USN_REASON_RENAME_NEW_NAME
                | USN_REASON_DATA_EXTEND
                | USN_REASON_DATA_TRUNCATION,
            return_only_on_close: 0,
            timeout: 0,
            bytes_to_wait_for: 0,
            usn_journal_id: journal_id,
        };

        let mut bytes_returned: u32 = 0;

        let result = unsafe {
            DeviceIoControl(
                handle,
                FSCTL_READ_USN_JOURNAL,
                Some(&read_data as *const _ as *const _),
                std::mem::size_of::<ReadUsnJournalData>() as u32,
                Some(buffer.as_mut_ptr() as *mut _),
                buffer.len() as u32,
                Some(&mut bytes_returned),
                None,
            )
        };

        match result {
            Ok(_) => {
                if bytes_returned >= 8 {
                    let next_usn = i64::from_le_bytes(buffer[0..8].try_into().unwrap());
                    Ok((bytes_returned as usize, next_usn))
                } else {
                    Ok((0, start_usn))
                }
            }
            Err(e) => {
                let error_code = e.code().0 as u32;
                if error_code == ERROR_JOURNAL_ENTRY_DELETED {
                    Err(ServiceError::UsnMonitor(
                        "JOURNAL_ENTRY_DELETED: Journal overflow".to_string(),
                    ))
                } else {
                    Err(ServiceError::UsnMonitor(format!(
                        "Failed to read USN journal: {} (code: {})",
                        e, error_code
                    )))
                }
            }
        }
    }

    /// Parse USN records from the buffer
    fn parse_usn_buffer(
        buffer: &[u8],
        volume: char,
        pending_renames: &mut HashMap<u64, RenameState>,
    ) -> Vec<(UsnEvent, char)> {
        let mut events = Vec::new();

        if buffer.len() < 8 {
            return events;
        }

        // Skip the first 8 bytes (next USN)
        let mut offset = 8;

        while offset < buffer.len() {
            if offset + 4 > buffer.len() {
                break;
            }

            let record_length =
                u32::from_le_bytes(buffer[offset..offset + 4].try_into().unwrap()) as usize;

            if record_length == 0 || offset + record_length > buffer.len() {
                break;
            }

            if let Some(event) =
                Self::parse_usn_record(&buffer[offset..offset + record_length], pending_renames)
            {
                events.push((event, volume));
            }

            offset += record_length;
        }

        events
    }

    /// Parse a single USN record into a UsnEvent
    fn parse_usn_record(
        record_bytes: &[u8],
        pending_renames: &mut HashMap<u64, RenameState>,
    ) -> Option<UsnEvent> {
        if record_bytes.len() < 60 {
            return None;
        }

        let major_version = u16::from_le_bytes(record_bytes[4..6].try_into().ok()?);

        // Only support V2 records
        if major_version != 2 {
            return None;
        }

        let record_length = u32::from_le_bytes(record_bytes[0..4].try_into().ok()?) as usize;
        let file_reference_number = u64::from_le_bytes(record_bytes[8..16].try_into().ok()?);
        let parent_file_reference_number =
            u64::from_le_bytes(record_bytes[16..24].try_into().ok()?);
        let reason = u32::from_le_bytes(record_bytes[32..36].try_into().ok()?);
        let file_name_length = u16::from_le_bytes(record_bytes[56..58].try_into().ok()?) as usize;
        let file_name_offset = u16::from_le_bytes(record_bytes[58..60].try_into().ok()?) as usize;

        // Extract file ID (lower 48 bits)
        let file_id = file_reference_number & 0x0000_FFFF_FFFF_FFFF;
        let parent_id = parent_file_reference_number & 0x0000_FFFF_FFFF_FFFF;

        // Extract file name (UTF-16LE)
        if file_name_offset + file_name_length > record_length {
            return None;
        }

        let name_bytes = &record_bytes[file_name_offset..file_name_offset + file_name_length];
        let name = String::from_utf16_lossy(
            &name_bytes
                .chunks_exact(2)
                .map(|chunk| u16::from_le_bytes([chunk[0], chunk[1]]))
                .collect::<Vec<u16>>(),
        );

        // Skip system files
        if name.starts_with('$') || name.is_empty() {
            return None;
        }

        Self::reason_to_event(file_id, parent_id, name, reason, pending_renames)
    }

    /// Convert USN reason flags to UsnEvent
    fn reason_to_event(
        file_id: u64,
        parent_id: u64,
        name: String,
        reason: u32,
        pending_renames: &mut HashMap<u64, RenameState>,
    ) -> Option<UsnEvent> {
        // Handle file creation
        if reason & USN_REASON_FILE_CREATE != 0 {
            debug!(
                "USN: FileCreated - id={}, parent={}, name={}",
                file_id, parent_id, name
            );
            return Some(UsnEvent::FileCreated {
                file_id,
                parent_id,
                name,
            });
        }

        // Handle file deletion
        if reason & USN_REASON_FILE_DELETE != 0 {
            debug!("USN: FileDeleted - id={}", file_id);
            return Some(UsnEvent::FileDeleted { file_id });
        }

        // Handle rename - old name
        if reason & USN_REASON_RENAME_OLD_NAME != 0 {
            debug!(
                "USN: RenameOldName - id={}, parent={}, name={}",
                file_id, parent_id, name
            );
            pending_renames.insert(
                file_id,
                RenameState {
                    file_id,
                    old_name: name,
                    old_parent_id: parent_id,
                    timestamp: Instant::now(),
                },
            );
            return None;
        }

        // Handle rename - new name
        if reason & USN_REASON_RENAME_NEW_NAME != 0 {
            debug!(
                "USN: RenameNewName - id={}, parent={}, name={}",
                file_id, parent_id, name
            );

            if let Some(old_state) = pending_renames.remove(&file_id) {
                if old_state.old_parent_id != parent_id {
                    return Some(UsnEvent::FileMoved {
                        file_id,
                        old_parent: old_state.old_parent_id,
                        new_parent: parent_id,
                    });
                } else if old_state.old_name != name {
                    return Some(UsnEvent::FileRenamed {
                        file_id,
                        old_name: old_state.old_name,
                        new_name: name,
                    });
                }
            } else {
                return Some(UsnEvent::FileRenamed {
                    file_id,
                    old_name: String::new(),
                    new_name: name,
                });
            }
        }

        None
    }

    /// Clean up stale pending rename operations
    fn cleanup_stale_renames(pending_renames: &mut HashMap<u64, RenameState>) {
        let stale_threshold = std::time::Duration::from_secs(5);
        let now = Instant::now();

        pending_renames.retain(|_, state| {
            let age = now.duration_since(state.timestamp);
            if age > stale_threshold {
                debug!(
                    "Cleaning up stale rename for file_id={}, old_name={}",
                    state.file_id, state.old_name
                );
                false
            } else {
                true
            }
        });
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_monitor_creation() {
        let monitor = UsnMonitor::new(vec!['C']);
        assert!(!monitor.is_stopped());
        assert_eq!(monitor.volumes.len(), 1);
    }

    #[test]
    fn test_stop_signal() {
        let monitor = UsnMonitor::new(vec!['C']);
        assert!(!monitor.is_stopped());
        monitor.stop();
        assert!(monitor.is_stopped());
    }

    #[test]
    fn test_stop_signal_shared() {
        let monitor = UsnMonitor::new(vec!['C', 'D']);
        let signal = monitor.stop_signal();

        assert!(!signal.load(Ordering::Relaxed));
        monitor.stop();
        assert!(signal.load(Ordering::Relaxed));
    }

    #[test]
    fn test_usn_reason_constants() {
        assert_eq!(USN_REASON_FILE_CREATE, 0x00000100);
        assert_eq!(USN_REASON_FILE_DELETE, 0x00000200);
        assert_eq!(USN_REASON_RENAME_OLD_NAME, 0x00001000);
        assert_eq!(USN_REASON_RENAME_NEW_NAME, 0x00002000);
        assert_eq!(USN_REASON_DATA_EXTEND, 0x00000002);
        assert_eq!(USN_REASON_DATA_TRUNCATION, 0x00000004);
        assert_eq!(USN_REASON_CLOSE, 0x80000000);
    }

    #[test]
    fn test_reason_to_event_file_create() {
        let mut pending_renames = HashMap::new();

        let event = VolumeMonitor::reason_to_event(
            123,
            456,
            "test.txt".to_string(),
            USN_REASON_FILE_CREATE,
            &mut pending_renames,
        );

        assert!(event.is_some());
        match event.unwrap() {
            UsnEvent::FileCreated {
                file_id,
                parent_id,
                name,
            } => {
                assert_eq!(file_id, 123);
                assert_eq!(parent_id, 456);
                assert_eq!(name, "test.txt");
            }
            _ => panic!("Expected FileCreated event"),
        }
    }

    #[test]
    fn test_reason_to_event_file_delete() {
        let mut pending_renames = HashMap::new();

        let event = VolumeMonitor::reason_to_event(
            123,
            456,
            "test.txt".to_string(),
            USN_REASON_FILE_DELETE,
            &mut pending_renames,
        );

        assert!(event.is_some());
        match event.unwrap() {
            UsnEvent::FileDeleted { file_id } => {
                assert_eq!(file_id, 123);
            }
            _ => panic!("Expected FileDeleted event"),
        }
    }

    #[test]
    fn test_reason_to_event_rename() {
        let mut pending_renames = HashMap::new();

        // First, send old name
        let event1 = VolumeMonitor::reason_to_event(
            123,
            456,
            "old.txt".to_string(),
            USN_REASON_RENAME_OLD_NAME,
            &mut pending_renames,
        );
        assert!(event1.is_none());

        // Then, send new name
        let event2 = VolumeMonitor::reason_to_event(
            123,
            456,
            "new.txt".to_string(),
            USN_REASON_RENAME_NEW_NAME,
            &mut pending_renames,
        );

        assert!(event2.is_some());
        match event2.unwrap() {
            UsnEvent::FileRenamed {
                file_id,
                old_name,
                new_name,
            } => {
                assert_eq!(file_id, 123);
                assert_eq!(old_name, "old.txt");
                assert_eq!(new_name, "new.txt");
            }
            _ => panic!("Expected FileRenamed event"),
        }
    }

    #[test]
    fn test_reason_to_event_move() {
        let mut pending_renames = HashMap::new();

        // First, send old name with old parent
        let event1 = VolumeMonitor::reason_to_event(
            123,
            456,
            "file.txt".to_string(),
            USN_REASON_RENAME_OLD_NAME,
            &mut pending_renames,
        );
        assert!(event1.is_none());

        // Then, send new name with different parent
        let event2 = VolumeMonitor::reason_to_event(
            123,
            789,
            "file.txt".to_string(),
            USN_REASON_RENAME_NEW_NAME,
            &mut pending_renames,
        );

        assert!(event2.is_some());
        match event2.unwrap() {
            UsnEvent::FileMoved {
                file_id,
                old_parent,
                new_parent,
            } => {
                assert_eq!(file_id, 123);
                assert_eq!(old_parent, 456);
                assert_eq!(new_parent, 789);
            }
            _ => panic!("Expected FileMoved event"),
        }
    }

    #[test]
    fn test_cleanup_stale_renames() {
        let mut pending_renames = HashMap::new();

        // Add a stale pending rename
        pending_renames.insert(
            123,
            RenameState {
                file_id: 123,
                old_name: "old.txt".to_string(),
                old_parent_id: 456,
                timestamp: Instant::now() - std::time::Duration::from_secs(10),
            },
        );

        assert_eq!(pending_renames.len(), 1);
        VolumeMonitor::cleanup_stale_renames(&mut pending_renames);
        assert!(pending_renames.is_empty());
    }

    #[test]
    fn test_cleanup_keeps_recent_renames() {
        let mut pending_renames = HashMap::new();

        // Add a recent pending rename
        pending_renames.insert(
            123,
            RenameState {
                file_id: 123,
                old_name: "old.txt".to_string(),
                old_parent_id: 456,
                timestamp: Instant::now(),
            },
        );

        assert_eq!(pending_renames.len(), 1);
        VolumeMonitor::cleanup_stale_renames(&mut pending_renames);
        assert_eq!(pending_renames.len(), 1);
    }

    #[test]
    fn test_skip_system_files() {
        let mut pending_renames = HashMap::new();

        // Note: System files starting with $ are skipped in parse_usn_record,
        // not in reason_to_event. The reason_to_event function processes
        // already-filtered records.
        
        // Test that normal files are processed
        let event = VolumeMonitor::reason_to_event(
            123,
            456,
            "normal.txt".to_string(),
            USN_REASON_FILE_CREATE,
            &mut pending_renames,
        );
        assert!(event.is_some());

        // Test that empty names return None (no event for empty name)
        // Note: Empty names are filtered in parse_usn_record before reaching reason_to_event
    }

    #[test]
    fn test_parse_usn_record_skips_system_files() {
        let mut pending_renames = HashMap::new();
        
        // Create a minimal valid USN record with a system file name ($MFT)
        // This tests that parse_usn_record filters out system files
        let mut record = vec![0u8; 68]; // Minimum size for V2 record
        
        // Record length (68 bytes)
        record[0..4].copy_from_slice(&68u32.to_le_bytes());
        // Major version = 2
        record[4..6].copy_from_slice(&2u16.to_le_bytes());
        // Minor version = 0
        record[6..8].copy_from_slice(&0u16.to_le_bytes());
        // File reference number
        record[8..16].copy_from_slice(&123u64.to_le_bytes());
        // Parent file reference number
        record[16..24].copy_from_slice(&456u64.to_le_bytes());
        // USN
        record[24..32].copy_from_slice(&0i64.to_le_bytes());
        // Reason = FILE_CREATE
        record[32..36].copy_from_slice(&USN_REASON_FILE_CREATE.to_le_bytes());
        // File name length (8 bytes for "$MFT" in UTF-16)
        record[56..58].copy_from_slice(&8u16.to_le_bytes());
        // File name offset (60)
        record[58..60].copy_from_slice(&60u16.to_le_bytes());
        // File name "$MFT" in UTF-16LE
        record[60..62].copy_from_slice(&('$' as u16).to_le_bytes());
        record[62..64].copy_from_slice(&('M' as u16).to_le_bytes());
        record[64..66].copy_from_slice(&('F' as u16).to_le_bytes());
        record[66..68].copy_from_slice(&('T' as u16).to_le_bytes());
        
        let event = VolumeMonitor::parse_usn_record(&record, &mut pending_renames);
        assert!(event.is_none(), "System files should be skipped");
    }

    #[tokio::test]
    async fn test_process_event_file_created() {
        let index = Arc::new(RwLock::new(FileIndex::new()));

        let event = UsnEvent::FileCreated {
            file_id: 123,
            parent_id: 456,
            name: "test.txt".to_string(),
        };

        UsnMonitor::process_event(event, 'C', &index).await.unwrap();

        let index_guard = index.read().await;
        assert!(index_guard.get(123).is_some());
        assert_eq!(index_guard.get(123).unwrap().name, "test.txt");
    }

    #[tokio::test]
    async fn test_process_event_file_deleted() {
        let index = Arc::new(RwLock::new(FileIndex::new()));

        // First add a file
        {
            let mut index_guard = index.write().await;
            let entry = FileEntry::new(
                123,
                456,
                "test.txt".to_string(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index_guard.insert(entry);
        }

        // Then delete it
        let event = UsnEvent::FileDeleted { file_id: 123 };
        UsnMonitor::process_event(event, 'C', &index).await.unwrap();

        let index_guard = index.read().await;
        assert!(index_guard.get(123).is_none());
    }

    #[tokio::test]
    async fn test_process_event_file_renamed() {
        let index = Arc::new(RwLock::new(FileIndex::new()));

        // First add a file
        {
            let mut index_guard = index.write().await;
            let entry = FileEntry::new(
                123,
                456,
                "old.txt".to_string(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index_guard.insert(entry);
        }

        // Then rename it
        let event = UsnEvent::FileRenamed {
            file_id: 123,
            old_name: "old.txt".to_string(),
            new_name: "new.txt".to_string(),
        };
        UsnMonitor::process_event(event, 'C', &index).await.unwrap();

        let index_guard = index.read().await;
        assert!(index_guard.get(123).is_some());
        assert_eq!(index_guard.get(123).unwrap().name, "new.txt");
    }

    #[tokio::test]
    async fn test_process_event_file_moved() {
        let index = Arc::new(RwLock::new(FileIndex::new()));

        // First add a file
        {
            let mut index_guard = index.write().await;
            let entry = FileEntry::new(
                123,
                456,
                "file.txt".to_string(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index_guard.insert(entry);
        }

        // Then move it
        let event = UsnEvent::FileMoved {
            file_id: 123,
            old_parent: 456,
            new_parent: 789,
        };
        UsnMonitor::process_event(event, 'C', &index).await.unwrap();

        let index_guard = index.read().await;
        assert!(index_guard.get(123).is_some());
        assert_eq!(index_guard.get(123).unwrap().parent_id, 789);
    }

    #[test]
    fn test_parse_usn_buffer_empty() {
        let mut pending_renames = HashMap::new();
        let buffer = vec![0u8; 8]; // Just the next USN, no records
        let events = VolumeMonitor::parse_usn_buffer(&buffer, 'C', &mut pending_renames);
        assert!(events.is_empty());
    }

    #[test]
    fn test_parse_usn_buffer_too_small() {
        let mut pending_renames = HashMap::new();
        let buffer = vec![0u8; 4]; // Too small
        let events = VolumeMonitor::parse_usn_buffer(&buffer, 'C', &mut pending_renames);
        assert!(events.is_empty());
    }
}
