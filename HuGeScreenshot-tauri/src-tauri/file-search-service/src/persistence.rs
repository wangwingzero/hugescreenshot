//! Index persistence
//!
//! Save and load the file index to/from disk using bincode serialization.
//! Implements atomic writes (write to temp file, then rename) for data safety.
//!
//! **Validates: Requirements 10.5** - Index persistence for faster startup
//!
//! ## File Format
//! ```text
//! [4 bytes] Magic: "HGFS"
//! [4 bytes] Version: u32 (little-endian)
//! [8 bytes] Entry count: u64 (little-endian)
//! [8 bytes] Created timestamp: i64 (little-endian, Unix timestamp)
//! [...] Serialized entries (bincode)
//! ```

use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::Path;

use chrono::{DateTime, TimeZone, Utc};
use serde::{Deserialize, Serialize};

use crate::error::{ServiceError, ServiceResult};
use crate::index::FileIndex;
use crate::models::{FileEntry, IndexStats};

/// Index file header magic bytes - "HGFS" (HuGe File Search)
pub const INDEX_MAGIC: [u8; 4] = *b"HGFS";

/// Current index file format version
pub const INDEX_VERSION: u32 = 1;

/// File header structure
#[derive(Debug, Clone)]
pub struct IndexFileHeader {
    /// Magic bytes (should be "HGFS")
    pub magic: [u8; 4],
    /// Format version
    pub version: u32,
    /// Number of entries in the index
    pub entry_count: u64,
    /// Timestamp when the index was created (Unix timestamp)
    pub created_timestamp: i64,
}

impl IndexFileHeader {
    /// Create a new header with current timestamp
    pub fn new(entry_count: u64) -> Self {
        Self {
            magic: INDEX_MAGIC,
            version: INDEX_VERSION,
            entry_count,
            created_timestamp: Utc::now().timestamp(),
        }
    }

    /// Write header to a writer
    pub fn write_to<W: Write>(&self, writer: &mut W) -> std::io::Result<()> {
        writer.write_all(&self.magic)?;
        writer.write_all(&self.version.to_le_bytes())?;
        writer.write_all(&self.entry_count.to_le_bytes())?;
        writer.write_all(&self.created_timestamp.to_le_bytes())?;
        Ok(())
    }

    /// Read header from a reader
    pub fn read_from<R: Read>(reader: &mut R) -> std::io::Result<Self> {
        let mut magic = [0u8; 4];
        reader.read_exact(&mut magic)?;

        let mut version_bytes = [0u8; 4];
        reader.read_exact(&mut version_bytes)?;
        let version = u32::from_le_bytes(version_bytes);

        let mut entry_count_bytes = [0u8; 8];
        reader.read_exact(&mut entry_count_bytes)?;
        let entry_count = u64::from_le_bytes(entry_count_bytes);

        let mut timestamp_bytes = [0u8; 8];
        reader.read_exact(&mut timestamp_bytes)?;
        let created_timestamp = i64::from_le_bytes(timestamp_bytes);

        Ok(Self {
            magic,
            version,
            entry_count,
            created_timestamp,
        })
    }

    /// Validate the header
    pub fn validate(&self) -> ServiceResult<()> {
        // Check magic bytes
        if self.magic != INDEX_MAGIC {
            return Err(ServiceError::Persistence(format!(
                "Invalid magic bytes: expected {:?}, got {:?}",
                INDEX_MAGIC, self.magic
            )));
        }

        // Check version
        if self.version > INDEX_VERSION {
            return Err(ServiceError::Persistence(format!(
                "Unsupported index version: {} (max supported: {})",
                self.version, INDEX_VERSION
            )));
        }

        Ok(())
    }

    /// Get the created time as DateTime
    pub fn created_time(&self) -> Option<DateTime<Utc>> {
        Utc.timestamp_opt(self.created_timestamp, 0).single()
    }
}

/// Persisted index data structure
/// This is a compact representation for serialization
#[derive(Debug, Clone, Serialize, Deserialize)]
struct PersistedIndex {
    /// All file entries
    entries: Vec<FileEntry>,
    /// Index statistics
    stats: IndexStats,
}

impl FileIndex {
    /// Save the index to disk
    ///
    /// Uses atomic write pattern: write to temp file, then rename.
    /// This ensures the index file is never left in a corrupted state.
    ///
    /// **Validates: Requirements 10.5**
    pub fn save_to_disk(&self, path: &Path) -> ServiceResult<()> {
        tracing::info!("Saving index to {:?} ({} entries)", path, self.len());

        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| {
                ServiceError::Persistence(format!("Failed to create directory: {}", e))
            })?;
        }

        // Create temp file in the same directory (for atomic rename)
        let temp_path = path.with_extension("tmp");

        // Write to temp file
        let result = self.write_to_file(&temp_path);

        if let Err(e) = result {
            // Clean up temp file on error
            let _ = fs::remove_file(&temp_path);
            return Err(e);
        }

        // Atomic rename: replace target with temp file
        // On Windows, we need to remove the target first if it exists
        if path.exists() {
            fs::remove_file(path).map_err(|e| {
                // Clean up temp file
                let _ = fs::remove_file(&temp_path);
                ServiceError::Persistence(format!("Failed to remove old index file: {}", e))
            })?;
        }

        fs::rename(&temp_path, path).map_err(|e| {
            // Clean up temp file
            let _ = fs::remove_file(&temp_path);
            ServiceError::Persistence(format!("Failed to rename temp file: {}", e))
        })?;

        tracing::info!("Index saved successfully to {:?}", path);
        Ok(())
    }

    /// Write index data to a file
    fn write_to_file(&self, path: &Path) -> ServiceResult<()> {
        let file = File::create(path).map_err(|e| {
            ServiceError::Persistence(format!("Failed to create file: {}", e))
        })?;

        let mut writer = BufWriter::new(file);

        // Write header
        let header = IndexFileHeader::new(self.len() as u64);
        header.write_to(&mut writer).map_err(|e| {
            ServiceError::Persistence(format!("Failed to write header: {}", e))
        })?;

        // Prepare data for serialization
        let persisted = PersistedIndex {
            entries: self.entries().values().cloned().collect(),
            stats: self.stats().clone(),
        };

        // Serialize with bincode
        bincode::serialize_into(&mut writer, &persisted).map_err(|e| {
            ServiceError::Persistence(format!("Failed to serialize index: {}", e))
        })?;

        // Flush and sync to ensure data is written to disk
        writer.flush().map_err(|e| {
            ServiceError::Persistence(format!("Failed to flush writer: {}", e))
        })?;

        // Get inner file and sync
        let file = writer.into_inner().map_err(|e| {
            ServiceError::Persistence(format!("Failed to get inner file: {}", e))
        })?;

        file.sync_all().map_err(|e| {
            ServiceError::Persistence(format!("Failed to sync file: {}", e))
        })?;

        Ok(())
    }

    /// Load the index from disk
    ///
    /// Returns an error if the file is corrupted or has an incompatible version.
    ///
    /// **Validates: Requirements 10.5, 10.6**
    pub fn load_from_disk(path: &Path) -> ServiceResult<Self> {
        tracing::info!("Loading index from {:?}", path);

        if !path.exists() {
            return Err(ServiceError::Persistence(format!(
                "Index file not found: {:?}",
                path
            )));
        }

        let file = File::open(path).map_err(|e| {
            ServiceError::Persistence(format!("Failed to open file: {}", e))
        })?;

        let mut reader = BufReader::new(file);

        // Read and validate header
        let header = IndexFileHeader::read_from(&mut reader).map_err(|e| {
            ServiceError::Persistence(format!("Failed to read header: {}", e))
        })?;

        header.validate()?;

        tracing::debug!(
            "Index header: version={}, entries={}, created={:?}",
            header.version,
            header.entry_count,
            header.created_time()
        );

        // Deserialize index data
        let persisted: PersistedIndex = bincode::deserialize_from(&mut reader).map_err(|e| {
            ServiceError::Persistence(format!(
                "Failed to deserialize index (file may be corrupted): {}",
                e
            ))
        })?;

        // Verify entry count matches header
        if persisted.entries.len() as u64 != header.entry_count {
            tracing::warn!(
                "Entry count mismatch: header says {}, but found {}",
                header.entry_count,
                persisted.entries.len()
            );
        }

        // Rebuild the index from persisted data
        let mut index = FileIndex::with_capacity(persisted.entries.len());

        for entry in persisted.entries {
            index.insert(entry);
        }

        // Restore stats (but update counts from actual data)
        let mut stats = persisted.stats;
        stats.total_files = index.stats().total_files;
        stats.total_directories = index.stats().total_directories;
        *index.stats_mut() = stats;

        tracing::info!(
            "Index loaded successfully: {} files, {} directories",
            index.stats().total_files,
            index.stats().total_directories
        );

        Ok(index)
    }

    /// Check if an index file exists and is valid
    pub fn index_file_exists(path: &Path) -> bool {
        if !path.exists() {
            return false;
        }

        // Try to read and validate header
        match File::open(path) {
            Ok(file) => {
                let mut reader = BufReader::new(file);
                match IndexFileHeader::read_from(&mut reader) {
                    Ok(header) => header.validate().is_ok(),
                    Err(_) => false,
                }
            }
            Err(_) => false,
        }
    }

    /// Get metadata about an index file without loading it
    pub fn get_index_file_info(path: &Path) -> ServiceResult<IndexFileHeader> {
        let file = File::open(path).map_err(|e| {
            ServiceError::Persistence(format!("Failed to open file: {}", e))
        })?;

        let mut reader = BufReader::new(file);
        let header = IndexFileHeader::read_from(&mut reader).map_err(|e| {
            ServiceError::Persistence(format!("Failed to read header: {}", e))
        })?;

        header.validate()?;
        Ok(header)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use tempfile::tempdir;

    fn create_test_entry(file_id: u64, parent_id: u64, name: &str, is_dir: bool) -> FileEntry {
        FileEntry::new(
            file_id,
            parent_id,
            name.to_string(),
            if is_dir { 0 } else { 1024 },
            Utc::now(),
            Utc::now(),
            is_dir,
            'C',
        )
    }

    #[test]
    fn test_magic_bytes() {
        assert_eq!(&INDEX_MAGIC, b"HGFS");
    }

    #[test]
    fn test_header_write_read_roundtrip() {
        let header = IndexFileHeader::new(100);

        let mut buffer = Vec::new();
        header.write_to(&mut buffer).unwrap();

        let mut cursor = std::io::Cursor::new(buffer);
        let read_header = IndexFileHeader::read_from(&mut cursor).unwrap();

        assert_eq!(read_header.magic, INDEX_MAGIC);
        assert_eq!(read_header.version, INDEX_VERSION);
        assert_eq!(read_header.entry_count, 100);
        assert_eq!(read_header.created_timestamp, header.created_timestamp);
    }

    #[test]
    fn test_header_validation_invalid_magic() {
        let header = IndexFileHeader {
            magic: *b"XXXX",
            version: INDEX_VERSION,
            entry_count: 0,
            created_timestamp: 0,
        };

        assert!(header.validate().is_err());
    }

    #[test]
    fn test_header_validation_future_version() {
        let header = IndexFileHeader {
            magic: INDEX_MAGIC,
            version: INDEX_VERSION + 100,
            entry_count: 0,
            created_timestamp: 0,
        };

        assert!(header.validate().is_err());
    }

    #[test]
    fn test_save_and_load_empty_index() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        let index = FileIndex::new();
        index.save_to_disk(&path).unwrap();

        assert!(path.exists());

        let loaded = FileIndex::load_from_disk(&path).unwrap();
        assert_eq!(loaded.len(), 0);
    }

    #[test]
    fn test_save_and_load_with_entries() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "folder", true));
        index.insert(create_test_entry(2, 1, "file.txt", false));
        index.insert(create_test_entry(3, 1, "文件.doc", false));

        index.save_to_disk(&path).unwrap();

        let loaded = FileIndex::load_from_disk(&path).unwrap();

        assert_eq!(loaded.len(), 3);
        assert!(loaded.get(1).is_some());
        assert!(loaded.get(2).is_some());
        assert!(loaded.get(3).is_some());

        // Verify entry data
        let entry1 = loaded.get(1).unwrap();
        assert_eq!(entry1.name, "folder");
        assert!(entry1.is_directory);

        let entry2 = loaded.get(2).unwrap();
        assert_eq!(entry2.name, "file.txt");
        assert!(!entry2.is_directory);

        let entry3 = loaded.get(3).unwrap();
        assert_eq!(entry3.name, "文件.doc");
    }

    #[test]
    fn test_save_and_load_preserves_stats() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "folder", true));
        index.insert(create_test_entry(2, 1, "file.txt", false));

        // Modify stats
        index.stats_mut().last_full_scan = Some(Utc::now());

        index.save_to_disk(&path).unwrap();

        let loaded = FileIndex::load_from_disk(&path).unwrap();

        assert_eq!(loaded.stats().total_files, 1);
        assert_eq!(loaded.stats().total_directories, 1);
        assert!(loaded.stats().last_full_scan.is_some());
    }

    #[test]
    fn test_save_overwrites_existing() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        // Save first version
        let mut index1 = FileIndex::new();
        index1.insert(create_test_entry(1, 0, "old.txt", false));
        index1.save_to_disk(&path).unwrap();

        // Save second version
        let mut index2 = FileIndex::new();
        index2.insert(create_test_entry(2, 0, "new.txt", false));
        index2.save_to_disk(&path).unwrap();

        // Load and verify
        let loaded = FileIndex::load_from_disk(&path).unwrap();
        assert_eq!(loaded.len(), 1);
        assert!(loaded.get(1).is_none());
        assert!(loaded.get(2).is_some());
        assert_eq!(loaded.get(2).unwrap().name, "new.txt");
    }

    #[test]
    fn test_load_nonexistent_file() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("nonexistent.hgfs");

        let result = FileIndex::load_from_disk(&path);
        assert!(result.is_err());
    }

    #[test]
    fn test_load_corrupted_file() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("corrupted.hgfs");

        // Write garbage data
        fs::write(&path, b"not a valid index file").unwrap();

        let result = FileIndex::load_from_disk(&path);
        assert!(result.is_err());
    }

    #[test]
    fn test_index_file_exists() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        assert!(!FileIndex::index_file_exists(&path));

        let index = FileIndex::new();
        index.save_to_disk(&path).unwrap();

        assert!(FileIndex::index_file_exists(&path));
    }

    #[test]
    fn test_index_file_exists_invalid_file() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("invalid.hgfs");

        // Write invalid data
        fs::write(&path, b"invalid").unwrap();

        assert!(!FileIndex::index_file_exists(&path));
    }

    #[test]
    fn test_get_index_file_info() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");

        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "file.txt", false));
        index.insert(create_test_entry(2, 0, "folder", true));
        index.save_to_disk(&path).unwrap();

        let info = FileIndex::get_index_file_info(&path).unwrap();
        assert_eq!(info.magic, INDEX_MAGIC);
        assert_eq!(info.version, INDEX_VERSION);
        assert_eq!(info.entry_count, 2);
        assert!(info.created_time().is_some());
    }

    #[test]
    fn test_atomic_write_no_temp_file_left() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_index.hgfs");
        let temp_path = path.with_extension("tmp");

        let index = FileIndex::new();
        index.save_to_disk(&path).unwrap();

        // Temp file should not exist after successful save
        assert!(!temp_path.exists());
        assert!(path.exists());
    }

    #[test]
    fn test_large_index_save_load() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("large_index.hgfs");

        let mut index = FileIndex::new();

        // Create 1000 entries
        for i in 1..=1000 {
            let is_dir = i % 10 == 0;
            index.insert(create_test_entry(
                i,
                if i > 1 { (i - 1) / 10 } else { 0 },
                &format!("file_{}.txt", i),
                is_dir,
            ));
        }

        index.save_to_disk(&path).unwrap();

        let loaded = FileIndex::load_from_disk(&path).unwrap();
        assert_eq!(loaded.len(), 1000);

        // Verify some random entries
        assert!(loaded.get(1).is_some());
        assert!(loaded.get(500).is_some());
        assert!(loaded.get(1000).is_some());
    }

    #[test]
    fn test_chinese_filenames_persistence() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("chinese_index.hgfs");

        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "文档", true));
        index.insert(create_test_entry(2, 1, "测试文件.txt", false));
        index.insert(create_test_entry(3, 1, "报告2024.docx", false));

        index.save_to_disk(&path).unwrap();

        let loaded = FileIndex::load_from_disk(&path).unwrap();

        assert_eq!(loaded.get(1).unwrap().name, "文档");
        assert_eq!(loaded.get(2).unwrap().name, "测试文件.txt");
        assert_eq!(loaded.get(3).unwrap().name, "报告2024.docx");

        // Verify pinyin was regenerated correctly
        let entry2 = loaded.get(2).unwrap();
        assert!(!entry2.pinyin.is_empty());
        assert!(!entry2.pinyin_abbr.is_empty());
    }
}


/// Property-based tests for index persistence round-trip
///
/// **Validates: Requirements 10.5**
///
/// Property 17: Index Persistence Round-Trip
/// For any File_Index state, saving to disk and loading back SHALL produce an equivalent
/// index that returns identical search results.
#[cfg(test)]
mod property_tests {
    use super::*;
    use crate::index::FileIndex;
    use crate::models::FileEntry;
    use chrono::Utc;
    use proptest::prelude::*;
    use proptest::collection::vec;
    use tempfile::tempdir;

    // **Validates: Requirements 10.5**

    /// Strategy for generating valid file names
    fn file_name_strategy() -> impl Strategy<Value = String> {
        // Generate valid file names: alphanumeric + some special chars, 1-30 chars
        // Avoid characters that are invalid in Windows file names: \ / : * ? " < > |
        prop::string::string_regex("[a-zA-Z0-9_\\-\\.\\u4e00-\\u9fa5]{1,30}")
            .unwrap()
            .prop_filter("non-empty name", |s| !s.is_empty() && !s.trim().is_empty())
    }

    /// Strategy for generating valid volume letters
    fn volume_strategy() -> impl Strategy<Value = char> {
        prop::sample::select(vec!['C', 'D', 'E', 'F'])
    }

    /// Strategy for generating file sizes
    fn size_strategy() -> impl Strategy<Value = u64> {
        // Use reasonable file sizes (0 to 10GB)
        0u64..10_000_000_000u64
    }

    /// Strategy for generating a FileEntry
    fn file_entry_strategy(file_id: u64, parent_id: u64) -> impl Strategy<Value = FileEntry> {
        (
            file_name_strategy(),
            size_strategy(),
            prop::bool::ANY,
            volume_strategy(),
        )
            .prop_map(move |(name, size, is_dir, volume)| {
                FileEntry::new(
                    file_id,
                    parent_id,
                    name,
                    if is_dir { 0 } else { size },
                    Utc::now(),
                    Utc::now(),
                    is_dir,
                    volume,
                )
            })
    }

    /// Strategy for generating a list of unique file entries
    fn file_entries_strategy(max_entries: usize) -> impl Strategy<Value = Vec<FileEntry>> {
        vec(
            (
                file_name_strategy(),
                size_strategy(),
                prop::bool::ANY,
                volume_strategy(),
                0u64..100, // parent_id range
            ),
            0..=max_entries,
        )
        .prop_map(|entries| {
            entries
                .into_iter()
                .enumerate()
                .map(|(i, (name, size, is_dir, volume, parent_id))| {
                    // Use index + 1 as file_id to ensure uniqueness (0 is reserved for root)
                    let file_id = (i + 1) as u64;
                    FileEntry::new(
                        file_id,
                        parent_id,
                        name,
                        if is_dir { 0 } else { size },
                        Utc::now(),
                        Utc::now(),
                        is_dir,
                        volume,
                    )
                })
                .collect()
        })
    }

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// Property 17: Index Persistence Round-Trip - Empty Index
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// An empty index saved and loaded back should remain empty.
        #[test]
        fn prop_empty_index_roundtrip(_seed in any::<u64>()) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let original = FileIndex::new();
            original.save_to_disk(&path).unwrap();

            let loaded = FileIndex::load_from_disk(&path).unwrap();

            prop_assert_eq!(loaded.len(), 0, "Loaded index should be empty");
            prop_assert_eq!(loaded.stats().total_files, 0);
            prop_assert_eq!(loaded.stats().total_directories, 0);
        }

        /// Property 17: Index Persistence Round-Trip - Single Entry
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// A single file entry saved and loaded back should be identical.
        #[test]
        fn prop_single_entry_roundtrip(
            name in file_name_strategy(),
            size in size_strategy(),
            is_dir in prop::bool::ANY,
            volume in volume_strategy(),
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            let entry = FileEntry::new(
                1,
                0,
                name.clone(),
                if is_dir { 0 } else { size },
                Utc::now(),
                Utc::now(),
                is_dir,
                volume,
            );
            original.insert(entry);

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify entry count
            prop_assert_eq!(loaded.len(), 1, "Loaded index should have 1 entry");

            // Verify entry exists and has correct attributes
            let loaded_entry = loaded.get(1);
            prop_assert!(loaded_entry.is_some(), "Entry should exist after load");

            let loaded_entry = loaded_entry.unwrap();
            prop_assert_eq!(&loaded_entry.name, &name, "Name should match");
            prop_assert_eq!(loaded_entry.is_directory, is_dir, "is_directory should match");
            prop_assert_eq!(loaded_entry.volume, volume, "Volume should match");

            if !is_dir {
                prop_assert_eq!(loaded_entry.size, size, "Size should match");
            }

            // Verify stats
            if is_dir {
                prop_assert_eq!(loaded.stats().total_directories, 1);
                prop_assert_eq!(loaded.stats().total_files, 0);
            } else {
                prop_assert_eq!(loaded.stats().total_files, 1);
                prop_assert_eq!(loaded.stats().total_directories, 0);
            }
        }

        /// Property 17: Index Persistence Round-Trip - Multiple Entries
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// For any File_Index state with multiple entries, saving to disk and loading back
        /// SHALL produce an equivalent index with the same entries.
        #[test]
        fn prop_multiple_entries_roundtrip(
            entries in file_entries_strategy(50),
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            for entry in &entries {
                original.insert(entry.clone());
            }

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify entry count
            prop_assert_eq!(
                loaded.len(),
                entries.len(),
                "Loaded index should have same number of entries"
            );

            // Verify each entry exists with correct attributes
            for entry in &entries {
                let loaded_entry = loaded.get(entry.file_id);
                prop_assert!(
                    loaded_entry.is_some(),
                    "Entry {} should exist after load",
                    entry.file_id
                );

                let loaded_entry = loaded_entry.unwrap();
                prop_assert_eq!(
                    &loaded_entry.name,
                    &entry.name,
                    "Name should match for entry {}",
                    entry.file_id
                );
                prop_assert_eq!(
                    loaded_entry.parent_id,
                    entry.parent_id,
                    "Parent ID should match for entry {}",
                    entry.file_id
                );
                prop_assert_eq!(
                    loaded_entry.is_directory,
                    entry.is_directory,
                    "is_directory should match for entry {}",
                    entry.file_id
                );
                prop_assert_eq!(
                    loaded_entry.volume,
                    entry.volume,
                    "Volume should match for entry {}",
                    entry.file_id
                );
                prop_assert_eq!(
                    loaded_entry.size,
                    entry.size,
                    "Size should match for entry {}",
                    entry.file_id
                );
            }

            // Verify stats match
            prop_assert_eq!(
                loaded.stats().total_files,
                original.stats().total_files,
                "Total files should match"
            );
            prop_assert_eq!(
                loaded.stats().total_directories,
                original.stats().total_directories,
                "Total directories should match"
            );
        }

        /// Property 17: Index Persistence Round-Trip - Search Results Identical
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// For any File_Index state, saving to disk and loading back SHALL produce
        /// an equivalent index that returns identical search results.
        #[test]
        fn prop_search_results_identical_after_roundtrip(
            entries in file_entries_strategy(30),
            search_prefix in "[a-zA-Z]{1,3}",
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            for entry in &entries {
                original.insert(entry.clone());
            }

            // Get search results from original index
            let original_by_name = original.search_by_name_prefix(&search_prefix);
            let original_by_pinyin = original.search_by_pinyin_prefix(&search_prefix);

            // Save and load
            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Get search results from loaded index
            let loaded_by_name = loaded.search_by_name_prefix(&search_prefix);
            let loaded_by_pinyin = loaded.search_by_pinyin_prefix(&search_prefix);

            // Verify name search results are identical
            let mut original_name_ids: Vec<u64> = original_by_name.clone();
            let mut loaded_name_ids: Vec<u64> = loaded_by_name.clone();
            original_name_ids.sort();
            loaded_name_ids.sort();

            prop_assert_eq!(
                original_name_ids,
                loaded_name_ids,
                "Name search results should be identical after roundtrip"
            );

            // Verify pinyin search results are identical
            let mut original_pinyin_ids: Vec<u64> = original_by_pinyin.clone();
            let mut loaded_pinyin_ids: Vec<u64> = loaded_by_pinyin.clone();
            original_pinyin_ids.sort();
            loaded_pinyin_ids.sort();

            prop_assert_eq!(
                original_pinyin_ids,
                loaded_pinyin_ids,
                "Pinyin search results should be identical after roundtrip"
            );
        }

        /// Property 17: Index Persistence Round-Trip - Chinese Filenames
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// Chinese filenames should be preserved correctly through save/load cycle,
        /// including their pinyin indexing.
        #[test]
        fn prop_chinese_filenames_roundtrip(
            chinese_chars in prop::string::string_regex("[\\u4e00-\\u9fa5]{1,10}").unwrap(),
            file_id in 1u64..10000,
        ) {
            prop_assume!(!chinese_chars.is_empty());

            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            let entry = FileEntry::new(
                file_id,
                0,
                chinese_chars.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            let original_pinyin = entry.pinyin.clone();
            let original_pinyin_abbr = entry.pinyin_abbr.clone();
            original.insert(entry);

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify entry exists
            let loaded_entry = loaded.get(file_id);
            prop_assert!(loaded_entry.is_some(), "Chinese filename entry should exist");

            let loaded_entry = loaded_entry.unwrap();

            // Verify Chinese name is preserved
            prop_assert_eq!(
                &loaded_entry.name,
                &chinese_chars,
                "Chinese filename should be preserved"
            );

            // Verify pinyin is regenerated correctly
            prop_assert_eq!(
                &loaded_entry.pinyin,
                &original_pinyin,
                "Pinyin should be regenerated correctly"
            );
            prop_assert_eq!(
                &loaded_entry.pinyin_abbr,
                &original_pinyin_abbr,
                "Pinyin abbreviation should be regenerated correctly"
            );

            // Verify searchable by pinyin
            let by_pinyin = loaded.get_by_pinyin(&original_pinyin_abbr);
            prop_assert!(
                by_pinyin.iter().any(|e| e.file_id == file_id),
                "Chinese file should be searchable by pinyin after roundtrip"
            );
        }

        /// Property 17: Index Persistence Round-Trip - Directory Structure
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// Parent-child relationships should be preserved through save/load cycle.
        #[test]
        fn prop_directory_structure_roundtrip(
            parent_name in file_name_strategy(),
            child_names in vec(file_name_strategy(), 1..=5),
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();

            // Create parent directory
            let parent_entry = FileEntry::new(
                1,
                0,
                parent_name.clone(),
                0,
                Utc::now(),
                Utc::now(),
                true,
                'C',
            );
            original.insert(parent_entry);

            // Create child files
            for (i, child_name) in child_names.iter().enumerate() {
                let child_entry = FileEntry::new(
                    (i + 2) as u64, // file_id starts from 2
                    1,              // parent_id is 1 (the parent directory)
                    child_name.clone(),
                    1024,
                    Utc::now(),
                    Utc::now(),
                    false,
                    'C',
                );
                original.insert(child_entry);
            }

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify parent exists
            let loaded_parent = loaded.get(1);
            prop_assert!(loaded_parent.is_some(), "Parent directory should exist");
            prop_assert_eq!(&loaded_parent.unwrap().name, &parent_name);
            prop_assert!(loaded_parent.unwrap().is_directory);

            // Verify all children exist with correct parent_id
            for (i, child_name) in child_names.iter().enumerate() {
                let child_id = (i + 2) as u64;
                let loaded_child = loaded.get(child_id);
                prop_assert!(
                    loaded_child.is_some(),
                    "Child {} should exist",
                    child_id
                );

                let loaded_child = loaded_child.unwrap();
                prop_assert_eq!(
                    &loaded_child.name,
                    child_name,
                    "Child name should match"
                );
                prop_assert_eq!(
                    loaded_child.parent_id,
                    1,
                    "Child parent_id should be preserved"
                );
            }
        }

        /// Property 17: Index Persistence Round-Trip - Stats Preservation
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// Index statistics should be preserved through save/load cycle.
        #[test]
        fn prop_stats_preserved_after_roundtrip(
            num_files in 0usize..20,
            num_dirs in 0usize..10,
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();

            // Add files
            for i in 0..num_files {
                let entry = FileEntry::new(
                    (i + 1) as u64,
                    0,
                    format!("file_{}.txt", i),
                    1024,
                    Utc::now(),
                    Utc::now(),
                    false,
                    'C',
                );
                original.insert(entry);
            }

            // Add directories
            for i in 0..num_dirs {
                let entry = FileEntry::new(
                    (num_files + i + 1) as u64,
                    0,
                    format!("dir_{}", i),
                    0,
                    Utc::now(),
                    Utc::now(),
                    true,
                    'C',
                );
                original.insert(entry);
            }

            // Set last_full_scan
            original.stats_mut().last_full_scan = Some(Utc::now());

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify stats
            prop_assert_eq!(
                loaded.stats().total_files,
                num_files as u64,
                "Total files should be preserved"
            );
            prop_assert_eq!(
                loaded.stats().total_directories,
                num_dirs as u64,
                "Total directories should be preserved"
            );
            prop_assert!(
                loaded.stats().last_full_scan.is_some(),
                "last_full_scan should be preserved"
            );
        }

        /// Property 17: Index Persistence Round-Trip - Idempotent Save/Load
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// Multiple save/load cycles should produce identical results.
        #[test]
        fn prop_idempotent_save_load(
            entries in file_entries_strategy(20),
        ) {
            let dir = tempdir().unwrap();
            let path1 = dir.path().join("test_index_1.hgfs");
            let path2 = dir.path().join("test_index_2.hgfs");

            let mut original = FileIndex::new();
            for entry in &entries {
                original.insert(entry.clone());
            }

            // First save/load cycle
            original.save_to_disk(&path1).unwrap();
            let loaded1 = FileIndex::load_from_disk(&path1).unwrap();

            // Second save/load cycle
            loaded1.save_to_disk(&path2).unwrap();
            let loaded2 = FileIndex::load_from_disk(&path2).unwrap();

            // Verify both loaded indexes are identical
            prop_assert_eq!(
                loaded1.len(),
                loaded2.len(),
                "Entry count should be identical after multiple cycles"
            );

            for entry in &entries {
                let entry1 = loaded1.get(entry.file_id);
                let entry2 = loaded2.get(entry.file_id);

                prop_assert!(entry1.is_some() && entry2.is_some());

                let entry1 = entry1.unwrap();
                let entry2 = entry2.unwrap();

                prop_assert_eq!(&entry1.name, &entry2.name);
                prop_assert_eq!(entry1.parent_id, entry2.parent_id);
                prop_assert_eq!(entry1.size, entry2.size);
                prop_assert_eq!(entry1.is_directory, entry2.is_directory);
                prop_assert_eq!(entry1.volume, entry2.volume);
                prop_assert_eq!(&entry1.pinyin, &entry2.pinyin);
                prop_assert_eq!(&entry1.pinyin_abbr, &entry2.pinyin_abbr);
            }
        }

        /// Property 17: Index Persistence Round-Trip - Name Index Consistency
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// The name index should be correctly rebuilt after loading.
        #[test]
        fn prop_name_index_rebuilt_after_load(
            entries in file_entries_strategy(20),
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            for entry in &entries {
                original.insert(entry.clone());
            }

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify each entry is findable by name
            for entry in &entries {
                let by_name = loaded.get_by_name(&entry.name);
                prop_assert!(
                    by_name.iter().any(|e| e.file_id == entry.file_id),
                    "Entry {} should be findable by name '{}' after load",
                    entry.file_id,
                    entry.name
                );
            }
        }

        /// Property 17: Index Persistence Round-Trip - Pinyin Index Consistency
        ///
        /// **Validates: Requirements 10.5**
        ///
        /// The pinyin index should be correctly rebuilt after loading.
        #[test]
        fn prop_pinyin_index_rebuilt_after_load(
            entries in file_entries_strategy(20),
        ) {
            let dir = tempdir().unwrap();
            let path = dir.path().join("test_index.hgfs");

            let mut original = FileIndex::new();
            for entry in &entries {
                original.insert(entry.clone());
            }

            original.save_to_disk(&path).unwrap();
            let loaded = FileIndex::load_from_disk(&path).unwrap();

            // Verify each entry is findable by pinyin abbreviation
            for entry in &entries {
                let by_pinyin = loaded.get_by_pinyin(&entry.pinyin_abbr);
                prop_assert!(
                    by_pinyin.iter().any(|e| e.file_id == entry.file_id),
                    "Entry {} should be findable by pinyin '{}' after load",
                    entry.file_id,
                    entry.pinyin_abbr
                );
            }
        }
    }
}
