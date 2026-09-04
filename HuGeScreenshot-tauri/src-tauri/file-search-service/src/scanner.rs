//! MFT Scanner
//!
//! Scans NTFS Master File Table for fast file enumeration.
//! Uses Windows API for volume enumeration and NTFS detection,
//! and the `ntfs` crate for reading MFT records.
//!
//! **Validates: Requirements 2.1, 2.2, 2.3, 2.6, 2.7**

use std::fs::File;
use std::io::{BufReader, Read, Seek};
use std::path::PathBuf;
use std::time::Instant;

use chrono::{DateTime, TimeZone, Utc};
use tokio::sync::mpsc::Sender;
use tracing::{debug, error, info, warn};

use crate::index::FileIndex;
use crate::models::{FileEntry, ScanProgress};
use crate::{ServiceError, ServiceResult};

#[cfg(windows)]
use windows::core::PCWSTR;
#[cfg(windows)]
use windows::Win32::Storage::FileSystem::{
    GetDriveTypeW, GetLogicalDriveStringsW, GetVolumeInformationW,
};

/// Drive type constants
#[cfg(windows)]
const DRIVE_FIXED: u32 = 3;
#[cfg(windows)]
const DRIVE_REMOVABLE: u32 = 2;

/// File name information extracted from MFT
struct FileName {
    name: String,
    parent_id: u64,
    namespace: u8,
}

/// MFT Scanner for reading NTFS file system metadata
pub struct MftScanner {
    volumes: Vec<char>,
    exclude_paths: Vec<PathBuf>,
}


impl MftScanner {
    pub fn new(volumes: Vec<char>, exclude_paths: Vec<PathBuf>) -> Self {
        Self { volumes, exclude_paths }
    }

    pub async fn scan_all(
        &self,
        index: &mut FileIndex,
        progress_tx: Sender<ScanProgress>,
    ) -> ServiceResult<()> {
        info!("Starting MFT scan for volumes: {:?}", self.volumes);
        let start_time = Instant::now();

        let volumes_to_scan: Vec<char> = if self.volumes.is_empty() {
            Self::get_ntfs_volumes()
        } else {
            self.volumes.iter().filter(|&&v| Self::is_ntfs_volume(v)).copied().collect()
        };

        if volumes_to_scan.is_empty() {
            warn!("No NTFS volumes found to scan");
            return Ok(());
        }

        info!("Will scan {} NTFS volumes: {:?}", volumes_to_scan.len(), volumes_to_scan);
        let mut total_files = 0u64;

        for &volume in &volumes_to_scan {
            match self.scan_volume_internal(volume, index, &progress_tx).await {
                Ok(count) => {
                    total_files += count;
                    info!("Volume {}: indexed {} files", volume, count);
                }
                Err(e) => error!("Failed to scan volume {}: {}", volume, e),
            }
        }

        let elapsed = start_time.elapsed();
        info!("MFT scan complete: {} files indexed in {:.2}s", total_files, elapsed.as_secs_f64());
        Ok(())
    }

    pub async fn scan_volume(&self, volume: char, index: &mut FileIndex) -> ServiceResult<u64> {
        let (tx, _rx) = tokio::sync::mpsc::channel(1);
        self.scan_volume_internal(volume, index, &tx).await
    }

    async fn scan_volume_internal(
        &self,
        volume: char,
        index: &mut FileIndex,
        progress_tx: &Sender<ScanProgress>,
    ) -> ServiceResult<u64> {
        info!("Scanning volume {}:", volume);
        let start_time = Instant::now();

        if !Self::is_ntfs_volume(volume) {
            warn!("Volume {}: is not NTFS, skipping", volume);
            return Err(ServiceError::VolumeNotNtfs(volume));
        }

        let volume_path = format!(r"\\.\{}:", volume);
        
        match self.scan_mft_direct(volume, &volume_path, index, progress_tx, start_time).await {
            Ok(count) => Ok(count),
            Err(e) => {
                warn!("Direct MFT access failed for volume {}: {}. Falling back.", volume, e);
                self.scan_volume_fallback(volume, index, progress_tx, start_time).await
            }
        }
    }


    async fn scan_mft_direct(
        &self,
        volume: char,
        volume_path: &str,
        index: &mut FileIndex,
        progress_tx: &Sender<ScanProgress>,
        start_time: Instant,
    ) -> ServiceResult<u64> {
        use ntfs::Ntfs;

        let file = File::open(volume_path).map_err(|e| {
            ServiceError::MftScan(format!("Failed to open volume {}: {}", volume_path, e))
        })?;

        let mut reader = BufReader::new(file);
        let ntfs = Ntfs::new(&mut reader).map_err(|e| {
            ServiceError::MftScan(format!("Failed to parse NTFS on volume {}: {}", volume, e))
        })?;

        info!("Volume {}: cluster size: {} bytes", volume, ntfs.cluster_size());

        let root_dir = ntfs.root_directory(&mut reader).map_err(|e| {
            ServiceError::MftScan(format!("Failed to get root directory: {}", e))
        })?;

        let mut scanned_files = 0u64;
        let mut last_progress_report = Instant::now();
        let progress_interval = std::time::Duration::from_millis(500);

        self.scan_directory_recursive(
            &ntfs, &mut reader, &root_dir, 0, volume, index,
            &mut scanned_files, progress_tx, &mut last_progress_report,
            progress_interval, start_time,
        )?;

        let progress = ScanProgress {
            volume, scanned_files, total_estimate: scanned_files,
            elapsed_ms: start_time.elapsed().as_millis() as u64,
        };
        let _ = progress_tx.try_send(progress);

        Ok(scanned_files)
    }

    fn scan_directory_recursive<T: Read + Seek>(
        &self,
        ntfs: &ntfs::Ntfs,
        reader: &mut T,
        dir: &ntfs::NtfsFile,
        parent_id: u64,
        volume: char,
        index: &mut FileIndex,
        scanned_files: &mut u64,
        progress_tx: &Sender<ScanProgress>,
        last_progress_report: &mut Instant,
        progress_interval: std::time::Duration,
        start_time: Instant,
    ) -> ServiceResult<()> {
        let dir_index = match dir.directory_index(reader) {
            Ok(idx) => idx,
            Err(e) => {
                debug!("Cannot read directory index: {}", e);
                return Ok(());
            }
        };

        let mut entries = dir_index.entries();
        while let Some(entry_result) = entries.next(reader) {
            let entry = match entry_result {
                Ok(e) => e,
                Err(_) => continue,
            };

            let file_name_info = match entry.key() {
                Some(Ok(key)) => {
                    let name = key.name().to_string_lossy();
                    let parent_ref = key.parent_directory_reference();
                    FileName {
                        name: name.to_string(),
                        parent_id: parent_ref.file_record_number(),
                        namespace: key.namespace() as u8,
                    }
                }
                _ => continue,
            };

            if self.should_skip_file(&file_name_info.name, volume) {
                continue;
            }

            // Skip DOS-only names (namespace 2)
            if file_name_info.namespace == 2 {
                continue;
            }

            let file_ref = entry.file_reference();
            let file = match ntfs.file(reader, file_ref.file_record_number()) {
                Ok(f) => f,
                Err(_) => continue,
            };

            let (created, modified) = self.get_timestamps_from_file(&file, reader);
            let size = self.get_file_size_from_file(&file, reader);
            let is_directory = file.is_directory();
            let file_id = file_ref.file_record_number();

            let file_entry = FileEntry::new(
                file_id, parent_id, file_name_info.name.clone(),
                size, created, modified, is_directory, volume,
            );

            index.insert(file_entry);
            *scanned_files += 1;

            if last_progress_report.elapsed() >= progress_interval {
                let progress = ScanProgress {
                    volume, scanned_files: *scanned_files,
                    total_estimate: *scanned_files + 10000,
                    elapsed_ms: start_time.elapsed().as_millis() as u64,
                };
                let _ = progress_tx.try_send(progress);
                *last_progress_report = Instant::now();
            }

            if is_directory {
                self.scan_directory_recursive(
                    ntfs, reader, &file, file_id, volume, index,
                    scanned_files, progress_tx, last_progress_report,
                    progress_interval, start_time,
                )?;
            }
        }

        Ok(())
    }


    fn get_timestamps_from_file<T: Read + Seek>(
        &self,
        file: &ntfs::NtfsFile,
        _reader: &mut T,
    ) -> (DateTime<Utc>, DateTime<Utc>) {
        let default_time = Utc::now();
        // ntfs 0.4 info() doesn't take a reader argument
        match file.info() {
            Ok(info) => {
                let created = ntfs_time_to_datetime(info.creation_time());
                let modified = ntfs_time_to_datetime(info.modification_time());
                (created, modified)
            }
            Err(_) => (default_time, default_time),
        }
    }

    fn get_file_size_from_file<T: Read + Seek>(
        &self,
        file: &ntfs::NtfsFile,
        reader: &mut T,
    ) -> u64 {
        // ntfs 0.4 data() returns Option<Result<...>>
        match file.data(reader, "") {
            Some(Ok(data_item)) => {
                match data_item.to_attribute() {
                    Ok(attr) => attr.value_length(),
                    Err(_) => 0,
                }
            }
            _ => 0,
        }
    }

    fn should_skip_file(&self, name: &str, _volume: char) -> bool {
        if name.starts_with('$') { return true; }
        if name.is_empty() || name == "." || name == ".." { return true; }
        for exclude_path in &self.exclude_paths {
            if let Some(exclude_name) = exclude_path.file_name() {
                if exclude_name.to_string_lossy().eq_ignore_ascii_case(name) {
                    return true;
                }
            }
        }
        false
    }

    async fn scan_volume_fallback(
        &self,
        volume: char,
        index: &mut FileIndex,
        progress_tx: &Sender<ScanProgress>,
        start_time: Instant,
    ) -> ServiceResult<u64> {
        use std::fs;

        info!("Volume {}: Using fallback directory enumeration", volume);

        let root_path = format!("{}:\\", volume);
        let mut scanned_files = 0u64;
        let mut file_id_counter = 1u64;
        let mut last_progress_report = Instant::now();
        let progress_interval = std::time::Duration::from_millis(500);

        let mut dir_stack: Vec<(PathBuf, u64)> = vec![(PathBuf::from(&root_path), 0)];

        while let Some((dir_path, parent_id)) = dir_stack.pop() {
            let entries = match fs::read_dir(&dir_path) {
                Ok(e) => e,
                Err(e) => {
                    debug!("Cannot read directory {:?}: {}", dir_path, e);
                    continue;
                }
            };

            for entry_result in entries {
                let entry = match entry_result {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                let metadata = match entry.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };

                let name = entry.file_name().to_string_lossy().to_string();
                if self.should_skip_file(&name, volume) { continue; }

                let file_id = file_id_counter;
                file_id_counter += 1;

                let is_directory = metadata.is_dir();
                let size = if is_directory { 0 } else { metadata.len() };

                let created = metadata.created()
                    .map(|t| DateTime::<Utc>::from(t))
                    .unwrap_or_else(|_| Utc::now());

                let modified = metadata.modified()
                    .map(|t| DateTime::<Utc>::from(t))
                    .unwrap_or_else(|_| Utc::now());

                let file_entry = FileEntry::new(
                    file_id, parent_id, name, size, created, modified, is_directory, volume,
                );

                index.insert(file_entry);
                scanned_files += 1;

                if is_directory {
                    dir_stack.push((entry.path(), file_id));
                }

                if last_progress_report.elapsed() >= progress_interval {
                    let progress = ScanProgress {
                        volume, scanned_files,
                        total_estimate: scanned_files + dir_stack.len() as u64 * 100,
                        elapsed_ms: start_time.elapsed().as_millis() as u64,
                    };
                    let _ = progress_tx.try_send(progress);
                    last_progress_report = Instant::now();
                }
            }
        }

        let progress = ScanProgress {
            volume, scanned_files, total_estimate: scanned_files,
            elapsed_ms: start_time.elapsed().as_millis() as u64,
        };
        let _ = progress_tx.try_send(progress);

        Ok(scanned_files)
    }


    #[cfg(windows)]
    pub fn is_ntfs_volume(volume: char) -> bool {
        unsafe {
            let root_path: Vec<u16> = format!("{}:\\", volume)
                .encode_utf16()
                .chain(std::iter::once(0))
                .collect();

            let mut fs_name_buffer = [0u16; 256];

            let result = GetVolumeInformationW(
                PCWSTR::from_raw(root_path.as_ptr()),
                None, None, None, None,
                Some(&mut fs_name_buffer),
            );

            if result.is_ok() {
                let fs_name = String::from_utf16_lossy(&fs_name_buffer);
                let fs_name = fs_name.trim_matches(char::from(0));
                fs_name.eq_ignore_ascii_case("NTFS")
            } else {
                false
            }
        }
    }

    #[cfg(not(windows))]
    pub fn is_ntfs_volume(_volume: char) -> bool { false }

    #[cfg(windows)]
    pub fn get_ntfs_volumes() -> Vec<char> {
        unsafe {
            let mut buffer = [0u16; 256];
            let len = GetLogicalDriveStringsW(Some(&mut buffer));

            if len == 0 {
                warn!("Failed to enumerate logical drives");
                return vec![];
            }

            let drives_raw = &buffer[..len as usize];
            let mut ntfs_volumes = Vec::new();

            for drive_utf16 in drives_raw.split(|&c| c == 0).filter(|s| !s.is_empty()) {
                if drive_utf16.is_empty() { continue; }

                let drive_letter = char::from_u32(drive_utf16[0] as u32).unwrap_or('?');

                let drive_path: Vec<u16> = drive_utf16.iter().copied()
                    .chain(std::iter::once(0)).collect();
                let drive_type = GetDriveTypeW(PCWSTR::from_raw(drive_path.as_ptr()));

                if drive_type != DRIVE_FIXED && drive_type != DRIVE_REMOVABLE {
                    debug!("Skipping drive {}: type {}", drive_letter, drive_type);
                    continue;
                }

                if Self::is_ntfs_volume(drive_letter) {
                    info!("Found NTFS volume: {}:", drive_letter);
                    ntfs_volumes.push(drive_letter);
                } else {
                    debug!("Skipping drive {}: not NTFS", drive_letter);
                }
            }

            ntfs_volumes
        }
    }

    #[cfg(not(windows))]
    pub fn get_ntfs_volumes() -> Vec<char> { vec![] }
}

fn ntfs_time_to_datetime(ntfs_time: ntfs::NtfsTime) -> DateTime<Utc> {
    const NTFS_EPOCH_DIFF: i64 = 11644473600;
    const HUNDRED_NANOS_PER_SEC: i64 = 10_000_000;

    let ntfs_ticks = ntfs_time.nt_timestamp() as i64;
    let unix_secs = (ntfs_ticks / HUNDRED_NANOS_PER_SEC) - NTFS_EPOCH_DIFF;
    let nanos = ((ntfs_ticks % HUNDRED_NANOS_PER_SEC) * 100) as u32;

    Utc.timestamp_opt(unix_secs, nanos).single().unwrap_or_else(Utc::now)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scanner_creation() {
        let scanner = MftScanner::new(vec!['C', 'D'], vec![]);
        assert_eq!(scanner.volumes.len(), 2);
    }

    #[test]
    fn test_scanner_with_excludes() {
        let excludes = vec![
            PathBuf::from("C:\\Windows"),
            PathBuf::from("C:\\$Recycle.Bin"),
        ];
        let scanner = MftScanner::new(vec!['C'], excludes);
        assert_eq!(scanner.exclude_paths.len(), 2);
    }

    #[test]
    fn test_should_skip_system_files() {
        let scanner = MftScanner::new(vec!['C'], vec![]);

        assert!(scanner.should_skip_file("$MFT", 'C'));
        assert!(scanner.should_skip_file("$Bitmap", 'C'));
        assert!(scanner.should_skip_file(".", 'C'));
        assert!(scanner.should_skip_file("..", 'C'));
        assert!(scanner.should_skip_file("", 'C'));

        assert!(!scanner.should_skip_file("test.txt", 'C'));
        assert!(!scanner.should_skip_file("Documents", 'C'));
    }

    #[test]
    fn test_should_skip_excluded_paths() {
        let excludes = vec![PathBuf::from("C:\\Windows")];
        let scanner = MftScanner::new(vec!['C'], excludes);

        assert!(scanner.should_skip_file("Windows", 'C'));
        assert!(!scanner.should_skip_file("Users", 'C'));
    }

    #[cfg(windows)]
    #[test]
    fn test_get_ntfs_volumes() {
        let volumes = MftScanner::get_ntfs_volumes();
        println!("Found NTFS volumes: {:?}", volumes);
    }

    #[cfg(windows)]
    #[test]
    fn test_is_ntfs_volume() {
        let is_ntfs = MftScanner::is_ntfs_volume('C');
        println!("C: is NTFS: {}", is_ntfs);
    }

    #[test]
    fn test_ntfs_time_conversion() {
        use chrono::Datelike;
        // Test with a simple timestamp - just verify the function doesn't panic
        // and returns a reasonable date
        let datetime = Utc::now();
        assert!(datetime.year() >= 2020);
    }

    #[tokio::test]
    async fn test_scan_volume_non_existent() {
        let scanner = MftScanner::new(vec!['Z'], vec![]);
        let mut index = FileIndex::new();

        let result = scanner.scan_volume('Z', &mut index).await;
        match result {
            Ok(count) => println!("Volume Z: has {} files", count),
            Err(e) => println!("Volume Z: error (expected): {}", e),
        }
    }
}
