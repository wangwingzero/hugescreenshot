//! Core data models for the file search service
//!
//! Defines the main data structures used throughout the service.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// A file entry in the index
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    /// Unique file ID from NTFS MFT
    pub file_id: u64,

    /// Parent directory's file ID
    pub parent_id: u64,

    /// File name (without path)
    pub name: String,

    /// Lowercase name for case-insensitive matching
    pub name_lower: String,

    /// Full pinyin representation
    pub pinyin: String,

    /// Pinyin abbreviation (first letters)
    pub pinyin_abbr: String,

    /// File size in bytes
    pub size: u64,

    /// Creation time
    pub created: DateTime<Utc>,

    /// Last modification time
    pub modified: DateTime<Utc>,

    /// Whether this is a directory
    pub is_directory: bool,

    /// Volume letter (e.g., 'C', 'D')
    pub volume: char,
}

impl FileEntry {
    /// Create a new FileEntry with pinyin indexing
    pub fn new(
        file_id: u64,
        parent_id: u64,
        name: String,
        size: u64,
        created: DateTime<Utc>,
        modified: DateTime<Utc>,
        is_directory: bool,
        volume: char,
    ) -> Self {
        let name_lower = name.to_lowercase();
        let (pinyin, pinyin_abbr) = Self::generate_pinyin(&name);

        Self {
            file_id,
            parent_id,
            name,
            name_lower,
            pinyin,
            pinyin_abbr,
            size,
            created,
            modified,
            is_directory,
            volume,
        }
    }

    /// Generate pinyin and abbreviation for a name
    fn generate_pinyin(name: &str) -> (String, String) {
        use pinyin::ToPinyin;

        let mut full_pinyin = String::new();
        let mut abbr = String::new();

        for c in name.chars() {
            if let Some(py) = c.to_pinyin() {
                full_pinyin.push_str(py.plain());
                if let Some(first) = py.plain().chars().next() {
                    abbr.push(first);
                }
            } else {
                // Non-Chinese character, keep as-is
                full_pinyin.push(c);
                if c.is_alphanumeric() {
                    abbr.push(c.to_ascii_lowercase());
                }
            }
        }

        (full_pinyin.to_lowercase(), abbr.to_lowercase())
    }
}

/// Index statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct IndexStats {
    /// Total number of files indexed
    pub total_files: u64,

    /// Total number of directories indexed
    pub total_directories: u64,

    /// Approximate index size in bytes
    pub index_size_bytes: u64,

    /// Time of last full scan
    pub last_full_scan: Option<DateTime<Utc>>,

    /// Time of last update (including incremental)
    pub last_update: DateTime<Utc>,
}

/// Scan progress information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanProgress {
    /// Volume being scanned
    pub volume: char,

    /// Number of files scanned so far
    pub scanned_files: u64,

    /// Estimated total files (may be inaccurate)
    pub total_estimate: u64,

    /// Elapsed time in milliseconds
    pub elapsed_ms: u64,
}

/// USN Journal change event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum UsnEvent {
    /// File was created
    FileCreated {
        file_id: u64,
        parent_id: u64,
        name: String,
    },

    /// File was deleted
    FileDeleted { file_id: u64 },

    /// File was renamed
    FileRenamed {
        file_id: u64,
        old_name: String,
        new_name: String,
    },

    /// File was moved to a different directory
    FileMoved {
        file_id: u64,
        old_parent: u64,
        new_parent: u64,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_entry_creation() {
        let entry = FileEntry::new(
            1,
            0,
            "测试文件.txt".to_string(),
            1024,
            Utc::now(),
            Utc::now(),
            false,
            'C',
        );

        assert_eq!(entry.file_id, 1);
        assert_eq!(entry.name, "测试文件.txt");
        assert!(!entry.pinyin.is_empty());
        assert!(!entry.pinyin_abbr.is_empty());
    }

    #[test]
    fn test_pinyin_generation() {
        let entry = FileEntry::new(
            1,
            0,
            "文件夹".to_string(),
            0,
            Utc::now(),
            Utc::now(),
            true,
            'C',
        );

        // "文件夹" -> "wenjianjia" (pinyin), "wjj" (abbr)
        assert!(entry.pinyin.contains("wen"));
        assert!(entry.pinyin_abbr.starts_with('w'));
    }

    #[test]
    fn test_mixed_name_pinyin() {
        let entry = FileEntry::new(
            1,
            0,
            "My文档2024".to_string(),
            0,
            Utc::now(),
            Utc::now(),
            true,
            'D',
        );

        // Should contain both English and pinyin
        assert!(entry.pinyin.contains("my"));
        assert!(entry.pinyin.contains("2024"));
    }
}
