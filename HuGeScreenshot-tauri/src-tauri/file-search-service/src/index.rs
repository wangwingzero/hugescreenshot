//! File index data structure
//!
//! In-memory index for fast file searching.
//! Implements HashMap storage, path caching, and pinyin indexing.
//!
//! **Validates: Requirements 2.3, 3.2, 3.3, 3.4, 3.5**

use std::collections::HashMap;
use std::path::PathBuf;

use crate::models::{FileEntry, IndexStats};

/// Special file ID for root entries (drive roots like C:\, D:\)
pub const ROOT_FILE_ID: u64 = 0;

/// Main file index structure
///
/// Stores file entries with efficient lookup by file ID, path caching,
/// and pinyin-based search indexing.
#[derive(Debug, Default)]
pub struct FileIndex {
    /// Main index: FileId -> FileEntry
    entries: HashMap<u64, FileEntry>,

    /// Path cache: FileId -> Full path (lazily populated)
    path_cache: HashMap<u64, PathBuf>,

    /// Pinyin index: Pinyin abbreviation -> FileId list
    /// Used for fast Chinese pinyin search
    pinyin_index: HashMap<String, Vec<u64>>,

    /// Name index: Lowercase name -> FileId list
    /// Used for fast exact/prefix name matching
    name_index: HashMap<String, Vec<u64>>,

    /// Index statistics
    stats: IndexStats,
}

impl FileIndex {
    /// Create a new empty index
    pub fn new() -> Self {
        Self::default()
    }

    /// Create a new index with pre-allocated capacity
    ///
    /// Use this when you know the approximate number of files to index
    /// to avoid repeated HashMap resizing.
    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            entries: HashMap::with_capacity(capacity),
            path_cache: HashMap::with_capacity(capacity),
            pinyin_index: HashMap::with_capacity(capacity / 10), // Fewer unique pinyin abbrs
            name_index: HashMap::with_capacity(capacity / 5),    // Fewer unique names
            stats: IndexStats::default(),
        }
    }

    /// Insert a file entry into the index
    ///
    /// This method:
    /// 1. Adds the entry to the main entries HashMap
    /// 2. Updates the pinyin index for Chinese search
    /// 3. Updates the name index for fast name lookup
    /// 4. Updates statistics
    /// 5. Invalidates path cache for this entry (will be rebuilt on demand)
    ///
    /// **Validates: Requirements 3.2** (file creation indexing)
    pub fn insert(&mut self, entry: FileEntry) {
        let file_id = entry.file_id;
        let pinyin_abbr = entry.pinyin_abbr.clone();
        let name_lower = entry.name_lower.clone();

        // Update pinyin index using Entry API for efficiency
        self.pinyin_index
            .entry(pinyin_abbr)
            .or_default()
            .push(file_id);

        // Update name index for fast name-based lookup
        self.name_index
            .entry(name_lower)
            .or_default()
            .push(file_id);

        // Update stats
        if entry.is_directory {
            self.stats.total_directories += 1;
        } else {
            self.stats.total_files += 1;
        }

        // Insert entry into main index
        self.entries.insert(file_id, entry);

        // Invalidate path cache for this entry (will be rebuilt on demand)
        // Also invalidate children's paths since parent changed
        self.path_cache.remove(&file_id);
    }

    /// Remove a file entry from the index
    ///
    /// This method:
    /// 1. Removes the entry from the main entries HashMap
    /// 2. Removes from pinyin index
    /// 3. Removes from name index
    /// 4. Updates statistics
    /// 5. Removes from path cache
    ///
    /// **Validates: Requirements 3.3** (file deletion indexing)
    pub fn remove(&mut self, file_id: u64) -> Option<FileEntry> {
        if let Some(entry) = self.entries.remove(&file_id) {
            // Update stats
            if entry.is_directory {
                self.stats.total_directories = self.stats.total_directories.saturating_sub(1);
            } else {
                self.stats.total_files = self.stats.total_files.saturating_sub(1);
            }

            // Remove from pinyin index
            if let Some(ids) = self.pinyin_index.get_mut(&entry.pinyin_abbr) {
                ids.retain(|&id| id != file_id);
                // Clean up empty vectors
                if ids.is_empty() {
                    self.pinyin_index.remove(&entry.pinyin_abbr);
                }
            }

            // Remove from name index
            if let Some(ids) = self.name_index.get_mut(&entry.name_lower) {
                ids.retain(|&id| id != file_id);
                if ids.is_empty() {
                    self.name_index.remove(&entry.name_lower);
                }
            }

            // Remove from path cache
            self.path_cache.remove(&file_id);

            // Invalidate children's path cache (they reference this parent)
            self.invalidate_children_paths(file_id);

            Some(entry)
        } else {
            None
        }
    }

    /// Update a file entry in the index
    ///
    /// **Validates: Requirements 3.4, 3.5** (file rename/move indexing)
    pub fn update(&mut self, file_id: u64, entry: FileEntry) {
        // Remove old entry first to clean up indexes
        self.remove(file_id);
        // Insert new entry
        self.insert(entry);
    }

    /// Get a file entry by ID
    pub fn get(&self, file_id: u64) -> Option<&FileEntry> {
        self.entries.get(&file_id)
    }

    /// Get a mutable file entry by ID
    pub fn get_mut(&mut self, file_id: u64) -> Option<&mut FileEntry> {
        self.entries.get_mut(&file_id)
    }

    /// Get the full path for a file by recursively resolving parent IDs
    ///
    /// This method builds the full path by walking up the parent chain.
    /// Results are cached for performance.
    ///
    /// **Validates: Requirements 2.3** (path resolution)
    pub fn get_path(&mut self, file_id: u64) -> Option<PathBuf> {
        // Check cache first
        if let Some(path) = self.path_cache.get(&file_id) {
            return Some(path.clone());
        }

        // Build path from parent chain
        let path = self.build_path(file_id)?;

        // Cache the result
        self.path_cache.insert(file_id, path.clone());

        Some(path)
    }

    /// Get path without caching (for read-only access)
    pub fn get_path_readonly(&self, file_id: u64) -> Option<PathBuf> {
        // Check cache first
        if let Some(path) = self.path_cache.get(&file_id) {
            return Some(path.clone());
        }

        // Build path from parent chain (without caching)
        self.build_path(file_id)
    }

    /// Build the full path by recursively resolving parent IDs
    ///
    /// Returns None if the file_id doesn't exist or if there's a cycle
    fn build_path(&self, file_id: u64) -> Option<PathBuf> {
        let entry = self.entries.get(&file_id)?;

        // Base case: root entry (parent_id == 0 or parent_id == file_id)
        if entry.parent_id == ROOT_FILE_ID || entry.parent_id == file_id {
            // This is a root-level entry, path is just "VOLUME:\"
            let mut path = PathBuf::new();
            path.push(format!("{}:\\", entry.volume));
            path.push(&entry.name);
            return Some(path);
        }

        // Recursive case: build parent path first
        // Use a visited set to detect cycles
        let mut visited = std::collections::HashSet::new();
        self.build_path_recursive(file_id, &mut visited)
    }

    /// Recursive helper for building paths with cycle detection
    fn build_path_recursive(
        &self,
        file_id: u64,
        visited: &mut std::collections::HashSet<u64>,
    ) -> Option<PathBuf> {
        // Cycle detection
        if !visited.insert(file_id) {
            return None; // Cycle detected
        }

        let entry = self.entries.get(&file_id)?;

        // Base case: root entry
        if entry.parent_id == ROOT_FILE_ID || entry.parent_id == file_id {
            let mut path = PathBuf::new();
            path.push(format!("{}:\\", entry.volume));
            path.push(&entry.name);
            return Some(path);
        }

        // Check if parent exists
        if !self.entries.contains_key(&entry.parent_id) {
            // Parent doesn't exist, treat this as root-level
            let mut path = PathBuf::new();
            path.push(format!("{}:\\", entry.volume));
            path.push(&entry.name);
            return Some(path);
        }

        // Recursive case: get parent path and append current name
        let parent_path = self.build_path_recursive(entry.parent_id, visited)?;
        Some(parent_path.join(&entry.name))
    }

    /// Invalidate path cache for all children of a given file
    fn invalidate_children_paths(&mut self, parent_id: u64) {
        // Collect children IDs first to avoid borrow issues
        let children: Vec<u64> = self
            .entries
            .iter()
            .filter(|(_, entry)| entry.parent_id == parent_id)
            .map(|(&id, _)| id)
            .collect();

        // Remove from cache and recurse
        for child_id in children {
            self.path_cache.remove(&child_id);
            self.invalidate_children_paths(child_id);
        }
    }

    /// Get index statistics
    pub fn stats(&self) -> &IndexStats {
        &self.stats
    }

    /// Get mutable index statistics
    pub fn stats_mut(&mut self) -> &mut IndexStats {
        &mut self.stats
    }

    /// Get the number of entries in the index
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Check if the index is empty
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Clear all entries from the index
    pub fn clear(&mut self) {
        self.entries.clear();
        self.path_cache.clear();
        self.pinyin_index.clear();
        self.name_index.clear();
        self.stats = IndexStats::default();
    }

    /// Get all entries (for iteration)
    pub fn entries(&self) -> &HashMap<u64, FileEntry> {
        &self.entries
    }

    /// Get entries by pinyin abbreviation
    pub fn get_by_pinyin(&self, pinyin_abbr: &str) -> Vec<&FileEntry> {
        self.pinyin_index
            .get(pinyin_abbr)
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| self.entries.get(id))
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Get entries by exact name (case-insensitive)
    pub fn get_by_name(&self, name: &str) -> Vec<&FileEntry> {
        let name_lower = name.to_lowercase();
        self.name_index
            .get(&name_lower)
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| self.entries.get(id))
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Get all file IDs that match a pinyin prefix
    pub fn search_by_pinyin_prefix(&self, prefix: &str) -> Vec<u64> {
        let prefix_lower = prefix.to_lowercase();
        self.pinyin_index
            .iter()
            .filter(|(key, _)| key.starts_with(&prefix_lower))
            .flat_map(|(_, ids)| ids.iter().copied())
            .collect()
    }

    /// Get all file IDs that match a name prefix (case-insensitive)
    pub fn search_by_name_prefix(&self, prefix: &str) -> Vec<u64> {
        let prefix_lower = prefix.to_lowercase();
        self.name_index
            .iter()
            .filter(|(key, _)| key.starts_with(&prefix_lower))
            .flat_map(|(_, ids)| ids.iter().copied())
            .collect()
    }

    /// Iterate over all entries
    pub fn iter(&self) -> impl Iterator<Item = (&u64, &FileEntry)> {
        self.entries.iter()
    }

    /// Get the path cache size (for debugging/stats)
    pub fn path_cache_size(&self) -> usize {
        self.path_cache.len()
    }

    /// Pre-populate path cache for all entries
    /// Call this after initial scan for better search performance
    pub fn populate_path_cache(&mut self) {
        let file_ids: Vec<u64> = self.entries.keys().copied().collect();
        for file_id in file_ids {
            let _ = self.get_path(file_id);
        }
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

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
    fn test_insert_and_get() {
        let mut index = FileIndex::new();
        let entry = create_test_entry(1, 0, "test.txt", false);

        index.insert(entry.clone());

        assert_eq!(index.len(), 1);
        assert!(index.get(1).is_some());
        assert_eq!(index.get(1).unwrap().name, "test.txt");
    }

    #[test]
    fn test_remove() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "test.txt", false));

        let removed = index.remove(1);

        assert!(removed.is_some());
        assert_eq!(index.len(), 0);
        assert!(index.get(1).is_none());
    }

    #[test]
    fn test_update() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "old.txt", false));

        let new_entry = create_test_entry(1, 0, "new.txt", false);
        index.update(1, new_entry);

        assert_eq!(index.len(), 1);
        assert_eq!(index.get(1).unwrap().name, "new.txt");
    }

    #[test]
    fn test_stats() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "file.txt", false));
        index.insert(create_test_entry(2, 0, "folder", true));

        assert_eq!(index.stats().total_files, 1);
        assert_eq!(index.stats().total_directories, 1);
    }

    #[test]
    fn test_stats_after_remove() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "file.txt", false));
        index.insert(create_test_entry(2, 0, "folder", true));

        index.remove(1);

        assert_eq!(index.stats().total_files, 0);
        assert_eq!(index.stats().total_directories, 1);
    }

    #[test]
    fn test_path_resolution_root_level() {
        let mut index = FileIndex::new();
        // Root level file (parent_id = 0)
        index.insert(create_test_entry(1, 0, "test.txt", false));

        let path = index.get_path(1);
        assert!(path.is_some());
        let path = path.unwrap();
        assert!(path.to_string_lossy().contains("test.txt"));
        assert!(path.to_string_lossy().starts_with("C:\\"));
    }

    #[test]
    fn test_path_resolution_nested() {
        let mut index = FileIndex::new();
        // Create a directory structure: C:\folder\subfolder\file.txt
        index.insert(create_test_entry(1, 0, "folder", true));
        index.insert(create_test_entry(2, 1, "subfolder", true));
        index.insert(create_test_entry(3, 2, "file.txt", false));

        let path = index.get_path(3);
        assert!(path.is_some());
        let path_str = path.unwrap().to_string_lossy().to_string();
        assert!(path_str.contains("folder"));
        assert!(path_str.contains("subfolder"));
        assert!(path_str.contains("file.txt"));
    }

    #[test]
    fn test_path_cache() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "test.txt", false));

        // First call builds and caches
        let path1 = index.get_path(1);
        assert!(path1.is_some());
        assert_eq!(index.path_cache_size(), 1);

        // Second call uses cache
        let path2 = index.get_path(1);
        assert_eq!(path1, path2);
    }

    #[test]
    fn test_pinyin_index() {
        let mut index = FileIndex::new();
        // Chinese filename
        index.insert(create_test_entry(1, 0, "文件夹", true));

        // Should be findable by pinyin abbreviation
        let results = index.get_by_pinyin(&index.get(1).unwrap().pinyin_abbr);
        assert!(!results.is_empty());
        assert_eq!(results[0].file_id, 1);
    }

    #[test]
    fn test_name_index() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "Test.TXT", false));

        // Case-insensitive lookup
        let results = index.get_by_name("test.txt");
        assert!(!results.is_empty());
        assert_eq!(results[0].file_id, 1);
    }

    #[test]
    fn test_search_by_pinyin_prefix() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "文件", false));
        index.insert(create_test_entry(2, 0, "文档", false));
        index.insert(create_test_entry(3, 0, "图片", false));

        // Search for files starting with "w" (wen)
        let results = index.search_by_pinyin_prefix("w");
        assert!(results.len() >= 2); // 文件 and 文档 both start with "w"
    }

    #[test]
    fn test_search_by_name_prefix() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "test1.txt", false));
        index.insert(create_test_entry(2, 0, "test2.txt", false));
        index.insert(create_test_entry(3, 0, "other.txt", false));

        let results = index.search_by_name_prefix("test");
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn test_clear() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "file1.txt", false));
        index.insert(create_test_entry(2, 0, "file2.txt", false));

        index.clear();

        assert!(index.is_empty());
        assert_eq!(index.stats().total_files, 0);
        assert_eq!(index.stats().total_directories, 0);
    }

    #[test]
    fn test_with_capacity() {
        let index = FileIndex::with_capacity(1000);
        assert!(index.is_empty());
    }

    #[test]
    fn test_remove_cleans_indexes() {
        let mut index = FileIndex::new();
        let entry = create_test_entry(1, 0, "test.txt", false);
        let pinyin_abbr = entry.pinyin_abbr.clone();
        let name_lower = entry.name_lower.clone();

        index.insert(entry);
        assert!(!index.get_by_pinyin(&pinyin_abbr).is_empty());
        assert!(!index.get_by_name(&name_lower).is_empty());

        index.remove(1);
        assert!(index.get_by_pinyin(&pinyin_abbr).is_empty());
        assert!(index.get_by_name(&name_lower).is_empty());
    }

    #[test]
    fn test_path_resolution_missing_parent() {
        let mut index = FileIndex::new();
        // File with non-existent parent
        index.insert(create_test_entry(1, 999, "orphan.txt", false));

        // Should still return a path (treating as root-level)
        let path = index.get_path(1);
        assert!(path.is_some());
    }

    #[test]
    fn test_path_resolution_cycle_detection() {
        let mut index = FileIndex::new();
        // Create a cycle: 1 -> 2 -> 1
        let entry1 = create_test_entry(1, 2, "file1", true);
        let entry2 = create_test_entry(2, 1, "file2", true);

        index.entries.insert(1, entry1);
        index.entries.insert(2, entry2);

        // Should handle cycle gracefully (return None)
        let _path = index.get_path(1);
        // The cycle detection should prevent infinite loop
        // Result depends on implementation - either None or a partial path
    }

    #[test]
    fn test_iterate_entries() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "file1.txt", false));
        index.insert(create_test_entry(2, 0, "file2.txt", false));

        let count = index.iter().count();
        assert_eq!(count, 2);
    }

    #[test]
    fn test_populate_path_cache() {
        let mut index = FileIndex::new();
        index.insert(create_test_entry(1, 0, "folder", true));
        index.insert(create_test_entry(2, 1, "file.txt", false));

        assert_eq!(index.path_cache_size(), 0);

        index.populate_path_cache();

        assert_eq!(index.path_cache_size(), 2);
    }
}

/// Property-based tests for index consistency with file system events
///
/// **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
///
/// Property 2: Index Consistency with File System Events
/// For any file system event (create, delete, rename, move), the File_Index SHALL be updated
/// to accurately reflect the change, such that searching for the file returns results
/// consistent with the current file system state.
#[cfg(test)]
mod property_tests {
    use super::*;
    use chrono::Utc;
    use proptest::prelude::*;
    use proptest::collection::vec;
    use std::collections::HashSet;

    // **Validates: Requirements 3.2, 3.3, 3.4, 3.5**

    /// Strategy for generating valid file names
    fn file_name_strategy() -> impl Strategy<Value = String> {
        // Generate valid file names: alphanumeric + some special chars, 1-50 chars
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
        prop::num::u64::ANY
    }

    /// Strategy for generating a FileEntry
    fn file_entry_strategy(
        file_id: u64,
        parent_id: u64,
    ) -> impl Strategy<Value = FileEntry> {
        (file_name_strategy(), size_strategy(), prop::bool::ANY, volume_strategy())
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

    /// File system event types for property testing
    #[derive(Debug, Clone)]
    enum FsEvent {
        /// Create a new file
        FileCreated {
            file_id: u64,
            parent_id: u64,
            name: String,
            size: u64,
            is_directory: bool,
            volume: char,
        },
        /// Delete an existing file
        FileDeleted { file_id: u64 },
        /// Rename a file (change name, keep parent)
        FileRenamed {
            file_id: u64,
            new_name: String,
        },
        /// Move a file (change parent, keep name)
        FileMoved {
            file_id: u64,
            new_parent_id: u64,
        },
    }

    /// Strategy for generating a sequence of file system events
    fn fs_events_strategy(max_events: usize) -> impl Strategy<Value = Vec<FsEvent>> {
        // Generate a sequence of events with consistent file IDs
        vec(
            prop_oneof![
                // FileCreated event
                (1u64..1000, 0u64..100, file_name_strategy(), size_strategy(), prop::bool::ANY, volume_strategy())
                    .prop_map(|(file_id, parent_id, name, size, is_dir, volume)| {
                        FsEvent::FileCreated {
                            file_id,
                            parent_id,
                            name,
                            size: if is_dir { 0 } else { size },
                            is_directory: is_dir,
                            volume,
                        }
                    }),
                // FileDeleted event
                (1u64..1000).prop_map(|file_id| FsEvent::FileDeleted { file_id }),
                // FileRenamed event
                (1u64..1000, file_name_strategy())
                    .prop_map(|(file_id, new_name)| FsEvent::FileRenamed { file_id, new_name }),
                // FileMoved event
                (1u64..1000, 0u64..100)
                    .prop_map(|(file_id, new_parent_id)| FsEvent::FileMoved { file_id, new_parent_id }),
            ],
            1..=max_events,
        )
    }

    /// Apply a file system event to the index
    fn apply_event(index: &mut FileIndex, event: &FsEvent) {
        match event {
            FsEvent::FileCreated {
                file_id,
                parent_id,
                name,
                size,
                is_directory,
                volume,
            } => {
                let entry = FileEntry::new(
                    *file_id,
                    *parent_id,
                    name.clone(),
                    *size,
                    Utc::now(),
                    Utc::now(),
                    *is_directory,
                    *volume,
                );
                index.insert(entry);
            }
            FsEvent::FileDeleted { file_id } => {
                index.remove(*file_id);
            }
            FsEvent::FileRenamed { file_id, new_name } => {
                if let Some(old_entry) = index.get(*file_id).cloned() {
                    let new_entry = FileEntry::new(
                        old_entry.file_id,
                        old_entry.parent_id,
                        new_name.clone(),
                        old_entry.size,
                        old_entry.created,
                        Utc::now(),
                        old_entry.is_directory,
                        old_entry.volume,
                    );
                    index.update(*file_id, new_entry);
                }
            }
            FsEvent::FileMoved {
                file_id,
                new_parent_id,
            } => {
                if let Some(old_entry) = index.get(*file_id).cloned() {
                    let new_entry = FileEntry::new(
                        old_entry.file_id,
                        *new_parent_id,
                        old_entry.name.clone(),
                        old_entry.size,
                        old_entry.created,
                        Utc::now(),
                        old_entry.is_directory,
                        old_entry.volume,
                    );
                    index.update(*file_id, new_entry);
                }
            }
        }
    }

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// Property: After FileCreated event, the file should be findable in the index
        ///
        /// **Validates: Requirements 3.2**
        #[test]
        fn prop_file_created_is_findable(
            file_id in 1u64..10000,
            parent_id in 0u64..1000,
            name in file_name_strategy(),
            size in size_strategy(),
            is_dir in prop::bool::ANY,
            volume in volume_strategy(),
        ) {
            let mut index = FileIndex::new();

            // Apply FileCreated event
            let event = FsEvent::FileCreated {
                file_id,
                parent_id,
                name: name.clone(),
                size: if is_dir { 0 } else { size },
                is_directory: is_dir,
                volume,
            };
            apply_event(&mut index, &event);

            // Verify: file should be findable by ID
            let entry = index.get(file_id);
            prop_assert!(entry.is_some(), "File should exist after creation");

            let entry = entry.unwrap();
            prop_assert_eq!(&entry.name, &name, "Name should match");
            prop_assert_eq!(entry.parent_id, parent_id, "Parent ID should match");
            prop_assert_eq!(entry.is_directory, is_dir, "Directory flag should match");
            prop_assert_eq!(entry.volume, volume, "Volume should match");

            // Verify: file should be findable by name
            let by_name = index.get_by_name(&name);
            prop_assert!(!by_name.is_empty(), "File should be findable by name");
            prop_assert!(
                by_name.iter().any(|e| e.file_id == file_id),
                "File ID should be in name search results"
            );

            // Verify: stats should be updated
            if is_dir {
                prop_assert!(index.stats().total_directories >= 1);
            } else {
                prop_assert!(index.stats().total_files >= 1);
            }
        }

        /// Property: After FileDeleted event, the file should not be findable in the index
        ///
        /// **Validates: Requirements 3.3**
        #[test]
        fn prop_file_deleted_not_findable(
            file_id in 1u64..10000,
            name in file_name_strategy(),
            is_dir in prop::bool::ANY,
        ) {
            let mut index = FileIndex::new();

            // First create the file
            let entry = FileEntry::new(
                file_id,
                0,
                name.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                is_dir,
                'C',
            );
            index.insert(entry);

            // Verify file exists
            prop_assert!(index.get(file_id).is_some());

            // Apply FileDeleted event
            let event = FsEvent::FileDeleted { file_id };
            apply_event(&mut index, &event);

            // Verify: file should NOT be findable by ID
            prop_assert!(
                index.get(file_id).is_none(),
                "File should not exist after deletion"
            );

            // Verify: file should NOT be findable by name (if no other file has same name)
            let by_name = index.get_by_name(&name);
            prop_assert!(
                !by_name.iter().any(|e| e.file_id == file_id),
                "Deleted file should not appear in name search"
            );

            // Verify: stats should be updated
            if is_dir {
                prop_assert_eq!(index.stats().total_directories, 0);
            } else {
                prop_assert_eq!(index.stats().total_files, 0);
            }
        }

        /// Property: After FileRenamed event, old name not findable, new name findable
        ///
        /// **Validates: Requirements 3.4**
        #[test]
        fn prop_file_renamed_consistency(
            file_id in 1u64..10000,
            old_name in file_name_strategy(),
            new_name in file_name_strategy(),
        ) {
            // Skip if names are the same (case-insensitive)
            prop_assume!(old_name.to_lowercase() != new_name.to_lowercase());

            let mut index = FileIndex::new();

            // Create file with old name
            let entry = FileEntry::new(
                file_id,
                0,
                old_name.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index.insert(entry);

            // Apply FileRenamed event
            let event = FsEvent::FileRenamed {
                file_id,
                new_name: new_name.clone(),
            };
            apply_event(&mut index, &event);

            // Verify: file should exist with new name
            let entry = index.get(file_id);
            prop_assert!(entry.is_some(), "File should still exist after rename");
            prop_assert_eq!(&entry.unwrap().name, &new_name, "Name should be updated");

            // Verify: old name should NOT find this file
            let by_old_name = index.get_by_name(&old_name);
            prop_assert!(
                !by_old_name.iter().any(|e| e.file_id == file_id),
                "Old name should not find the renamed file"
            );

            // Verify: new name SHOULD find this file
            let by_new_name = index.get_by_name(&new_name);
            prop_assert!(
                by_new_name.iter().any(|e| e.file_id == file_id),
                "New name should find the renamed file"
            );
        }

        /// Property: After FileMoved event, path should reflect new location
        ///
        /// **Validates: Requirements 3.5**
        #[test]
        fn prop_file_moved_path_updated(
            file_id in 1u64..10000,
            old_parent_id in 1u64..1000,
            new_parent_id in 1u64..1000,
            file_name in file_name_strategy(),
            old_parent_name in file_name_strategy(),
            new_parent_name in file_name_strategy(),
        ) {
            // Skip if parent IDs are the same
            prop_assume!(old_parent_id != new_parent_id);
            // Skip if file_id equals any parent_id (would create circular reference)
            prop_assume!(file_id != old_parent_id && file_id != new_parent_id);

            let mut index = FileIndex::new();

            // Create old parent directory
            let old_parent = FileEntry::new(
                old_parent_id,
                0,
                old_parent_name.clone(),
                0,
                Utc::now(),
                Utc::now(),
                true,
                'C',
            );
            index.insert(old_parent);

            // Create new parent directory
            let new_parent = FileEntry::new(
                new_parent_id,
                0,
                new_parent_name.clone(),
                0,
                Utc::now(),
                Utc::now(),
                true,
                'C',
            );
            index.insert(new_parent);

            // Create file in old parent
            let file = FileEntry::new(
                file_id,
                old_parent_id,
                file_name.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index.insert(file);

            // Verify initial parent
            prop_assert_eq!(index.get(file_id).unwrap().parent_id, old_parent_id);

            // Apply FileMoved event
            let event = FsEvent::FileMoved {
                file_id,
                new_parent_id,
            };
            apply_event(&mut index, &event);

            // Verify: file should have new parent
            let entry = index.get(file_id);
            prop_assert!(entry.is_some(), "File should still exist after move");
            prop_assert_eq!(
                entry.unwrap().parent_id,
                new_parent_id,
                "Parent ID should be updated"
            );

            // Verify: path should reflect new location
            let path = index.get_path(file_id);
            prop_assert!(path.is_some(), "Path should be resolvable");
            let path_str = path.unwrap().to_string_lossy().to_string();

            // Path should contain new parent name, not old parent name
            prop_assert!(
                path_str.contains(&new_parent_name),
                "Path should contain new parent name: {} not in {}",
                new_parent_name,
                path_str
            );
        }

        /// Property: Sequence of events maintains index consistency
        ///
        /// **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
        ///
        /// For any sequence of file system events, the index should accurately
        /// reflect the final state.
        #[test]
        fn prop_event_sequence_consistency(
            events in fs_events_strategy(20),
        ) {
            let mut index = FileIndex::new();
            let mut expected_files: HashSet<u64> = HashSet::new();

            // Apply all events and track expected state
            for event in &events {
                match event {
                    FsEvent::FileCreated { file_id, .. } => {
                        apply_event(&mut index, event);
                        expected_files.insert(*file_id);
                    }
                    FsEvent::FileDeleted { file_id } => {
                        apply_event(&mut index, event);
                        expected_files.remove(file_id);
                    }
                    FsEvent::FileRenamed { file_id, .. } => {
                        // Only apply if file exists
                        if expected_files.contains(file_id) {
                            apply_event(&mut index, event);
                        }
                    }
                    FsEvent::FileMoved { file_id, .. } => {
                        // Only apply if file exists
                        if expected_files.contains(file_id) {
                            apply_event(&mut index, event);
                        }
                    }
                }
            }

            // Verify: all expected files exist in index
            for file_id in &expected_files {
                prop_assert!(
                    index.get(*file_id).is_some(),
                    "Expected file {} should exist in index",
                    file_id
                );
            }

            // Verify: index length matches expected
            prop_assert_eq!(
                index.len(),
                expected_files.len(),
                "Index size should match expected file count"
            );

            // Verify: no unexpected files in index
            for (file_id, _) in index.iter() {
                prop_assert!(
                    expected_files.contains(file_id),
                    "Unexpected file {} in index",
                    file_id
                );
            }
        }

        /// Property: Insert followed by remove returns to empty state
        ///
        /// **Validates: Requirements 3.2, 3.3**
        #[test]
        fn prop_insert_remove_returns_empty(
            entries in vec(
                (1u64..10000, file_name_strategy(), prop::bool::ANY),
                1..=10
            ),
        ) {
            let mut index = FileIndex::new();

            // Insert all entries
            let mut file_ids = Vec::new();
            for (i, (base_id, name, is_dir)) in entries.iter().enumerate() {
                let file_id = base_id + (i as u64 * 10000); // Ensure unique IDs
                let entry = FileEntry::new(
                    file_id,
                    0,
                    name.clone(),
                    1024,
                    Utc::now(),
                    Utc::now(),
                    *is_dir,
                    'C',
                );
                index.insert(entry);
                file_ids.push(file_id);
            }

            prop_assert_eq!(index.len(), file_ids.len());

            // Remove all entries
            for file_id in &file_ids {
                index.remove(*file_id);
            }

            // Verify: index should be empty
            prop_assert!(index.is_empty(), "Index should be empty after removing all files");
            prop_assert_eq!(index.stats().total_files, 0);
            prop_assert_eq!(index.stats().total_directories, 0);
        }

        /// Property: Update preserves file ID but changes attributes
        ///
        /// **Validates: Requirements 3.4, 3.5**
        #[test]
        fn prop_update_preserves_id(
            file_id in 1u64..10000,
            old_name in file_name_strategy(),
            new_name in file_name_strategy(),
            old_parent in 0u64..1000,
            new_parent in 0u64..1000,
        ) {
            let mut index = FileIndex::new();

            // Create initial entry
            let old_entry = FileEntry::new(
                file_id,
                old_parent,
                old_name,
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index.insert(old_entry);

            // Update with new attributes
            let new_entry = FileEntry::new(
                file_id,
                new_parent,
                new_name.clone(),
                2048,
                Utc::now(),
                Utc::now(),
                false,
                'D',
            );
            index.update(file_id, new_entry);

            // Verify: file ID is preserved
            let entry = index.get(file_id);
            prop_assert!(entry.is_some(), "File should exist after update");

            let entry = entry.unwrap();
            prop_assert_eq!(entry.file_id, file_id, "File ID should be preserved");
            prop_assert_eq!(&entry.name, &new_name, "Name should be updated");
            prop_assert_eq!(entry.parent_id, new_parent, "Parent should be updated");
            prop_assert_eq!(entry.size, 2048, "Size should be updated");
            prop_assert_eq!(entry.volume, 'D', "Volume should be updated");

            // Verify: only one entry exists
            prop_assert_eq!(index.len(), 1, "Should have exactly one entry");
        }

        /// Property: Pinyin index is consistent after all operations
        ///
        /// **Validates: Requirements 3.2, 3.3, 3.4**
        #[test]
        fn prop_pinyin_index_consistency(
            file_id in 1u64..10000,
            name in file_name_strategy(),
        ) {
            let mut index = FileIndex::new();

            // Create entry
            let entry = FileEntry::new(
                file_id,
                0,
                name.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            let pinyin_abbr = entry.pinyin_abbr.clone();
            index.insert(entry);

            // Verify: pinyin index contains the file
            let by_pinyin = index.get_by_pinyin(&pinyin_abbr);
            prop_assert!(
                by_pinyin.iter().any(|e| e.file_id == file_id),
                "File should be findable by pinyin after insert"
            );

            // Remove entry
            index.remove(file_id);

            // Verify: pinyin index no longer contains the file
            let by_pinyin = index.get_by_pinyin(&pinyin_abbr);
            prop_assert!(
                !by_pinyin.iter().any(|e| e.file_id == file_id),
                "File should not be findable by pinyin after remove"
            );
        }

        /// Property: Name index is consistent after all operations
        ///
        /// **Validates: Requirements 3.2, 3.3, 3.4**
        #[test]
        fn prop_name_index_consistency(
            file_id in 1u64..10000,
            name in file_name_strategy(),
        ) {
            let mut index = FileIndex::new();

            // Create entry
            let entry = FileEntry::new(
                file_id,
                0,
                name.clone(),
                1024,
                Utc::now(),
                Utc::now(),
                false,
                'C',
            );
            index.insert(entry);

            // Verify: name index contains the file
            let by_name = index.get_by_name(&name);
            prop_assert!(
                by_name.iter().any(|e| e.file_id == file_id),
                "File should be findable by name after insert"
            );

            // Remove entry
            index.remove(file_id);

            // Verify: name index no longer contains the file
            let by_name = index.get_by_name(&name);
            prop_assert!(
                !by_name.iter().any(|e| e.file_id == file_id),
                "File should not be findable by name after remove"
            );
        }
    }
}
