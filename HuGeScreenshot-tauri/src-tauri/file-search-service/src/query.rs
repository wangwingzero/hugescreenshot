//! Query engine for file searching
//!
//! Implements fuzzy matching, wildcard, regex, and pinyin search.
//!
//! **Validates: Requirements 5.1, 5.2**

use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use regex::Regex;
use std::path::PathBuf;

use crate::index::FileIndex;
use crate::models::FileEntry;
use crate::protocol::{MatchMode, SearchFilters, SearchQuery, SearchResult, SortField, SortOrder};

/// Query engine for searching the file index
pub struct QueryEngine {
    /// Fuzzy matcher instance
    matcher: SkimMatcherV2,
}

impl Default for QueryEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Match result containing score and match indices
#[derive(Debug, Clone)]
struct MatchResult {
    /// Match score (higher is better)
    score: i64,
    /// Match indices for highlighting (start, end) pairs
    indices: Vec<(usize, usize)>,
}

impl QueryEngine {
    /// Create a new query engine
    pub fn new() -> Self {
        Self {
            matcher: SkimMatcherV2::default(),
        }
    }

    /// Execute a search query against the index
    ///
    /// **Validates: Requirements 5.1, 5.2**
    pub fn search(&self, index: &FileIndex, query: &SearchQuery) -> Vec<SearchResult> {
        tracing::debug!("Searching for: {} (mode: {:?})", query.keyword, query.match_mode);

        // Handle empty keyword
        if query.keyword.trim().is_empty() {
            return Vec::new();
        }

        // Pre-compile regex if needed (fail fast on invalid regex)
        let compiled_regex = if query.match_mode == MatchMode::Regex {
            match Regex::new(&query.keyword) {
                Ok(re) => Some(re),
                Err(e) => {
                    tracing::warn!("Invalid regex pattern '{}': {}", query.keyword, e);
                    return Vec::new();
                }
            }
        } else {
            None
        };

        // Collect matching results
        let mut results: Vec<SearchResult> = index
            .entries()
            .iter()
            .filter_map(|(&file_id, entry)| {
                // Apply filters first (fast rejection)
                if !self.matches_filters(entry, &query.filters) {
                    return None;
                }

                // Calculate match score and get indices
                let match_result = self.calculate_match(
                    entry,
                    &query.keyword,
                    query.match_mode,
                    compiled_regex.as_ref(),
                );

                match_result.map(|mr| {
                    // Get path (use readonly to avoid mutable borrow)
                    let path = index
                        .get_path_readonly(file_id)
                        .unwrap_or_else(|| PathBuf::from(&entry.name));

                    SearchResult {
                        file_id,
                        name: entry.name.clone(),
                        path,
                        size: entry.size,
                        modified: entry.modified,
                        is_directory: entry.is_directory,
                        score: mr.score,
                        match_indices: mr.indices,
                    }
                })
            })
            .collect();

        // Sort results
        self.sort_results(&mut results, query.sort_by, query.sort_order);

        // Apply pagination
        let total = results.len();
        let start = query.offset.min(total);
        let end = (query.offset + query.limit).min(total);

        tracing::debug!(
            "Search completed: {} total matches, returning {} results (offset: {}, limit: {})",
            total,
            end - start,
            query.offset,
            query.limit
        );

        results[start..end].to_vec()
    }

    /// Calculate match score and indices for a file entry
    ///
    /// Returns None if no match, Some(MatchResult) with score and indices if matched
    fn calculate_match(
        &self,
        entry: &FileEntry,
        keyword: &str,
        mode: MatchMode,
        compiled_regex: Option<&Regex>,
    ) -> Option<MatchResult> {
        // Try name match first
        let name_match = self.calculate_score_with_indices(entry, keyword, mode, compiled_regex);

        // Try pinyin match if name didn't match
        let pinyin_match = if name_match.is_none() {
            self.matches_pinyin_with_indices(entry, keyword)
        } else {
            None
        };

        // Return the better match (name match preferred)
        name_match.or(pinyin_match)
    }

    /// Calculate match score with indices for highlighting
    fn calculate_score_with_indices(
        &self,
        entry: &FileEntry,
        keyword: &str,
        mode: MatchMode,
        compiled_regex: Option<&Regex>,
    ) -> Option<MatchResult> {
        match mode {
            MatchMode::Exact => self.exact_match_with_indices(&entry.name_lower, keyword),
            MatchMode::Wildcard => self.wildcard_match_with_indices(&entry.name_lower, keyword),
            MatchMode::Fuzzy => self.fuzzy_match_with_indices(&entry.name_lower, keyword),
            MatchMode::Regex => self.regex_match_with_indices(&entry.name, compiled_regex),
        }
    }

    /// Exact match: substring match (case-insensitive)
    fn exact_match_with_indices(&self, name_lower: &str, keyword: &str) -> Option<MatchResult> {
        let keyword_lower = keyword.to_lowercase();
        
        // Find all occurrences
        let mut indices = Vec::new();
        let mut start = 0;
        
        while let Some(pos) = name_lower[start..].find(&keyword_lower) {
            let abs_pos = start + pos;
            indices.push((abs_pos, abs_pos + keyword_lower.len()));
            start = abs_pos + 1;
            
            // Limit to first 10 matches to avoid performance issues
            if indices.len() >= 10 {
                break;
            }
        }

        if indices.is_empty() {
            None
        } else {
            // Score based on position (earlier = better) and match count
            let first_pos = indices[0].0;
            let score = 100 - (first_pos as i64).min(50) + (indices.len() as i64 * 5);
            Some(MatchResult { score, indices })
        }
    }

    /// Wildcard match: supports * (any chars) and ? (single char)
    fn wildcard_match_with_indices(&self, name_lower: &str, pattern: &str) -> Option<MatchResult> {
        let pattern_lower = pattern.to_lowercase();
        
        // Convert wildcard pattern to regex
        let regex_pattern = Self::wildcard_to_regex(&pattern_lower);
        
        match Regex::new(&regex_pattern) {
            Ok(re) => {
                if let Some(m) = re.find(name_lower) {
                    let indices = vec![(m.start(), m.end())];
                    // Score based on match position and length
                    let score = 90 - (m.start() as i64).min(40);
                    Some(MatchResult { score, indices })
                } else {
                    None
                }
            }
            Err(_) => {
                // Fallback to fuzzy match if regex conversion fails
                self.fuzzy_match_with_indices(name_lower, pattern)
            }
        }
    }

    /// Convert wildcard pattern to regex pattern
    fn wildcard_to_regex(pattern: &str) -> String {
        let mut regex = String::with_capacity(pattern.len() * 2);
        regex.push_str("(?i)"); // Case insensitive
        
        for c in pattern.chars() {
            match c {
                '*' => regex.push_str(".*"),
                '?' => regex.push('.'),
                // Escape regex special characters
                '.' | '+' | '^' | '$' | '(' | ')' | '[' | ']' | '{' | '}' | '|' | '\\' => {
                    regex.push('\\');
                    regex.push(c);
                }
                _ => regex.push(c),
            }
        }
        
        regex
    }

    /// Fuzzy match using SkimMatcherV2
    fn fuzzy_match_with_indices(&self, name_lower: &str, keyword: &str) -> Option<MatchResult> {
        // Use fuzzy_indices to get both score and match positions
        self.matcher
            .fuzzy_indices(name_lower, keyword)
            .map(|(score, char_indices)| {
                // Convert character indices to byte ranges for UTF-8 safety
                let match_indices = Self::char_indices_to_byte_ranges(name_lower, &char_indices);
                MatchResult {
                    score,
                    indices: match_indices,
                }
            })
    }

    /// Convert character indices to byte ranges for UTF-8 strings
    /// This is necessary because fuzzy_matcher returns character indices,
    /// but we need byte indices for string slicing.
    /// 
    /// Takes character indices and converts them to contiguous byte ranges.
    /// e.g., for "一二三" with char_indices [0, 2], returns byte ranges
    /// for the first and third characters.
    fn char_indices_to_byte_ranges(s: &str, char_indices: &[usize]) -> Vec<(usize, usize)> {
        if char_indices.is_empty() {
            return Vec::new();
        }

        // Build a mapping from character index to (byte_start, byte_end)
        let char_byte_ranges: Vec<(usize, usize)> = s
            .char_indices()
            .map(|(byte_idx, ch)| (byte_idx, byte_idx + ch.len_utf8()))
            .collect();
        
        // Group consecutive character indices into ranges
        let mut ranges = Vec::new();
        let mut i = 0;
        
        while i < char_indices.len() {
            let start_char_idx = char_indices[i];
            let mut end_char_idx = start_char_idx;
            
            // Find consecutive character indices
            while i + 1 < char_indices.len() && char_indices[i + 1] == end_char_idx + 1 {
                i += 1;
                end_char_idx = char_indices[i];
            }
            
            // Convert to byte range
            if let (Some(&(start_byte, _)), Some(&(_, end_byte))) = (
                char_byte_ranges.get(start_char_idx),
                char_byte_ranges.get(end_char_idx),
            ) {
                ranges.push((start_byte, end_byte));
            }
            
            i += 1;
        }
        
        ranges
    }

    /// Convert individual byte indices to contiguous ranges (for ASCII-only use)
    /// e.g., [0, 1, 2, 5, 6] -> [(0, 3), (5, 7)]
    /// Note: This function assumes ASCII where each character is 1 byte.
    /// For UTF-8 strings with multi-byte characters, use char_indices_to_byte_ranges instead.
    #[allow(dead_code)]
    fn indices_to_ranges(byte_indices: &[usize]) -> Vec<(usize, usize)> {
        if byte_indices.is_empty() {
            return Vec::new();
        }

        let mut ranges = Vec::new();
        let mut start = byte_indices[0];
        let mut end = byte_indices[0] + 1;

        for &idx in byte_indices.iter().skip(1) {
            if idx == end {
                // Contiguous, extend the range
                end = idx + 1;
            } else {
                // Gap found, save current range and start new one
                ranges.push((start, end));
                start = idx;
                end = idx + 1;
            }
        }
        
        // Don't forget the last range
        ranges.push((start, end));
        
        ranges
    }

    /// Regex match
    fn regex_match_with_indices(
        &self,
        name: &str,
        compiled_regex: Option<&Regex>,
    ) -> Option<MatchResult> {
        let re = compiled_regex?;
        
        // Find all matches
        let mut indices = Vec::new();
        for m in re.find_iter(name) {
            indices.push((m.start(), m.end()));
            
            // Limit to first 10 matches
            if indices.len() >= 10 {
                break;
            }
        }

        if indices.is_empty() {
            None
        } else {
            // Score based on match count and position
            let first_pos = indices[0].0;
            let score = 85 - (first_pos as i64).min(35) + (indices.len() as i64 * 3);
            Some(MatchResult { score, indices })
        }
    }

    /// Check if entry matches pinyin search and return indices
    fn matches_pinyin_with_indices(&self, entry: &FileEntry, keyword: &str) -> Option<MatchResult> {
        let keyword_lower = keyword.to_lowercase();

        // Match against pinyin abbreviation (first letters) - higher priority
        if let Some(pos) = entry.pinyin_abbr.find(&keyword_lower) {
            // For pinyin abbr match, we need to map back to original name positions
            // This is approximate - we highlight the first N characters where N = keyword length
            let indices = self.map_pinyin_to_name_indices(entry, pos, keyword_lower.len(), true);
            return Some(MatchResult {
                score: 80,
                indices,
            });
        }

        // Match against full pinyin - lower priority
        if let Some(pos) = entry.pinyin.find(&keyword_lower) {
            let indices = self.map_pinyin_to_name_indices(entry, pos, keyword_lower.len(), false);
            return Some(MatchResult {
                score: 60,
                indices,
            });
        }

        None
    }

    /// Map pinyin match position back to original name character positions
    /// This is an approximation since pinyin length varies per character
    fn map_pinyin_to_name_indices(
        &self,
        entry: &FileEntry,
        _pinyin_pos: usize,
        match_len: usize,
        is_abbr: bool,
    ) -> Vec<(usize, usize)> {
        // For abbreviation match, each pinyin char maps to one name char
        // For full pinyin, it's more complex - we approximate
        
        let name = &entry.name;
        let char_count = name.chars().count();
        
        if is_abbr {
            // Each abbr char corresponds to one name char
            // Highlight the first `match_len` characters
            let end_char = match_len.min(char_count);
            let end_byte = name
                .char_indices()
                .nth(end_char)
                .map(|(i, _)| i)
                .unwrap_or(name.len());
            vec![(0, end_byte)]
        } else {
            // For full pinyin, approximate by highlighting proportionally
            // This is a rough approximation
            let pinyin_len = entry.pinyin.len();
            if pinyin_len == 0 {
                return vec![];
            }
            
            let ratio = match_len as f64 / pinyin_len as f64;
            let end_char = ((char_count as f64 * ratio).ceil() as usize).min(char_count);
            let end_byte = name
                .char_indices()
                .nth(end_char)
                .map(|(i, _)| i)
                .unwrap_or(name.len());
            vec![(0, end_byte)]
        }
    }

    /// Apply filters to check if entry should be included
    fn matches_filters(&self, entry: &FileEntry, filters: &SearchFilters) -> bool {
        // Check directory filter
        if !filters.include_directories && entry.is_directory {
            return false;
        }

        // Check extension filter
        if let Some(ref extensions) = filters.extensions {
            if !entry.is_directory {
                let ext = entry
                    .name
                    .rsplit('.')
                    .next()
                    .map(|s| s.to_lowercase())
                    .unwrap_or_default();
                if !extensions.iter().any(|e| e.to_lowercase() == ext) {
                    return false;
                }
            }
        }

        // Check size filters
        if let Some(min_size) = filters.min_size {
            if entry.size < min_size {
                return false;
            }
        }
        if let Some(max_size) = filters.max_size {
            if entry.size > max_size {
                return false;
            }
        }

        // Check date filters
        if let Some(ref after) = filters.modified_after {
            if entry.modified < *after {
                return false;
            }
        }
        if let Some(ref before) = filters.modified_before {
            if entry.modified > *before {
                return false;
            }
        }

        // Check volume filter
        if let Some(ref volumes) = filters.volumes {
            if !volumes.contains(&entry.volume) {
                return false;
            }
        }

        true
    }

    /// Sort results according to query parameters
    fn sort_results(&self, results: &mut [SearchResult], sort_by: SortField, sort_order: SortOrder) {
        results.sort_by(|a, b| {
            let cmp = match sort_by {
                // Relevance: higher scores are "better", so default is descending
                // When user asks for Desc, we want higher scores first (b.cmp(a))
                // When user asks for Asc, we want lower scores first (a.cmp(b))
                SortField::Relevance => match sort_order {
                    SortOrder::Desc => b.score.cmp(&a.score),
                    SortOrder::Asc => a.score.cmp(&b.score),
                },
                // For other fields, apply sort_order normally
                SortField::Name => {
                    let cmp = a.name.to_lowercase().cmp(&b.name.to_lowercase());
                    match sort_order {
                        SortOrder::Asc => cmp,
                        SortOrder::Desc => cmp.reverse(),
                    }
                }
                SortField::Path => {
                    let cmp = a.path.cmp(&b.path);
                    match sort_order {
                        SortOrder::Asc => cmp,
                        SortOrder::Desc => cmp.reverse(),
                    }
                }
                SortField::Size => {
                    let cmp = a.size.cmp(&b.size);
                    match sort_order {
                        SortOrder::Asc => cmp,
                        SortOrder::Desc => cmp.reverse(),
                    }
                }
                SortField::Modified => {
                    let cmp = a.modified.cmp(&b.modified);
                    match sort_order {
                        SortOrder::Asc => cmp,
                        SortOrder::Desc => cmp.reverse(),
                    }
                }
            };

            cmp
        });
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    fn create_test_entry(name: &str) -> FileEntry {
        FileEntry::new(1, 0, name.to_string(), 1024, Utc::now(), Utc::now(), false, 'C')
    }

    fn create_test_entry_with_id(id: u64, name: &str) -> FileEntry {
        FileEntry::new(id, 0, name.to_string(), 1024, Utc::now(), Utc::now(), false, 'C')
    }

    #[test]
    fn test_exact_match() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test.txt");

        let result = engine.exact_match_with_indices(&entry.name_lower, "test");
        assert!(result.is_some());
        let mr = result.unwrap();
        assert!(mr.score > 0);
        assert!(!mr.indices.is_empty());
        assert_eq!(mr.indices[0], (0, 4)); // "test" at position 0-4

        let result = engine.exact_match_with_indices(&entry.name_lower, "xyz");
        assert!(result.is_none());
    }

    #[test]
    fn test_exact_match_multiple_occurrences() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test_test_test.txt");

        let result = engine.exact_match_with_indices(&entry.name_lower, "test");
        assert!(result.is_some());
        let mr = result.unwrap();
        assert_eq!(mr.indices.len(), 3); // Three occurrences
    }

    #[test]
    fn test_fuzzy_match() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("document.pdf");

        let result = engine.fuzzy_match_with_indices(&entry.name_lower, "doc");
        assert!(result.is_some());
        let mr = result.unwrap();
        assert!(mr.score > 0);
        assert!(!mr.indices.is_empty());
    }

    #[test]
    fn test_fuzzy_match_non_contiguous() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("document.pdf");

        // "dmt" should match d-ocu-m-en-t
        let result = engine.fuzzy_match_with_indices(&entry.name_lower, "dmt");
        assert!(result.is_some());
    }

    #[test]
    fn test_wildcard_match_asterisk() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("document.pdf");

        let result = engine.wildcard_match_with_indices(&entry.name_lower, "doc*");
        assert!(result.is_some());

        let result = engine.wildcard_match_with_indices(&entry.name_lower, "*.pdf");
        assert!(result.is_some());

        let result = engine.wildcard_match_with_indices(&entry.name_lower, "doc*.pdf");
        assert!(result.is_some());
    }

    #[test]
    fn test_wildcard_match_question_mark() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test.txt");

        let result = engine.wildcard_match_with_indices(&entry.name_lower, "t?st");
        assert!(result.is_some());

        let result = engine.wildcard_match_with_indices(&entry.name_lower, "????.txt");
        assert!(result.is_some());
    }

    #[test]
    fn test_regex_match() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("document123.pdf");

        let re = Regex::new(r"\d+").unwrap();
        let result = engine.regex_match_with_indices(&entry.name, Some(&re));
        assert!(result.is_some());
        let mr = result.unwrap();
        assert!(!mr.indices.is_empty());
    }

    #[test]
    fn test_regex_match_case_insensitive() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("Document.PDF");

        let re = Regex::new(r"(?i)document").unwrap();
        let result = engine.regex_match_with_indices(&entry.name, Some(&re));
        assert!(result.is_some());
    }

    #[test]
    fn test_pinyin_match() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("文档.pdf");

        // Should match pinyin abbreviation "wd"
        let result = engine.matches_pinyin_with_indices(&entry, "wd");
        assert!(result.is_some());
        let mr = result.unwrap();
        assert_eq!(mr.score, 80); // Abbr match score
    }

    #[test]
    fn test_pinyin_full_match() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("文件夹");

        // Should match full pinyin
        let result = engine.matches_pinyin_with_indices(&entry, "wenjian");
        assert!(result.is_some());
        let mr = result.unwrap();
        assert_eq!(mr.score, 60); // Full pinyin match score
    }

    #[test]
    fn test_filter_extension() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test.pdf");

        let mut filters = SearchFilters::default();
        filters.extensions = Some(vec!["pdf".to_string()]);

        assert!(engine.matches_filters(&entry, &filters));

        filters.extensions = Some(vec!["doc".to_string()]);
        assert!(!engine.matches_filters(&entry, &filters));
    }

    #[test]
    fn test_filter_size() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test.txt"); // size = 1024

        let mut filters = SearchFilters::default();
        filters.min_size = Some(500);
        filters.max_size = Some(2000);

        assert!(engine.matches_filters(&entry, &filters));

        filters.min_size = Some(2000);
        assert!(!engine.matches_filters(&entry, &filters));
    }

    #[test]
    fn test_filter_directories() {
        let engine = QueryEngine::new();
        let mut entry = create_test_entry("folder");
        entry.is_directory = true;

        let mut filters = SearchFilters::default();
        filters.include_directories = true;
        assert!(engine.matches_filters(&entry, &filters));

        filters.include_directories = false;
        assert!(!engine.matches_filters(&entry, &filters));
    }

    #[test]
    fn test_filter_volume() {
        let engine = QueryEngine::new();
        let entry = create_test_entry("test.txt"); // volume = 'C'

        let mut filters = SearchFilters::default();
        filters.volumes = Some(vec!['C', 'D']);
        assert!(engine.matches_filters(&entry, &filters));

        filters.volumes = Some(vec!['D', 'E']);
        assert!(!engine.matches_filters(&entry, &filters));
    }

    #[test]
    fn test_indices_to_ranges() {
        // Contiguous indices
        let indices = vec![0, 1, 2, 3];
        let ranges = QueryEngine::indices_to_ranges(&indices);
        assert_eq!(ranges, vec![(0, 4)]);

        // Non-contiguous indices
        let indices = vec![0, 1, 2, 5, 6];
        let ranges = QueryEngine::indices_to_ranges(&indices);
        assert_eq!(ranges, vec![(0, 3), (5, 7)]);

        // Single index
        let indices = vec![5];
        let ranges = QueryEngine::indices_to_ranges(&indices);
        assert_eq!(ranges, vec![(5, 6)]);

        // Empty
        let indices: Vec<usize> = vec![];
        let ranges = QueryEngine::indices_to_ranges(&indices);
        assert!(ranges.is_empty());
    }

    #[test]
    fn test_wildcard_to_regex() {
        assert_eq!(QueryEngine::wildcard_to_regex("test"), "(?i)test");
        assert_eq!(QueryEngine::wildcard_to_regex("*.txt"), "(?i).*\\.txt");
        assert_eq!(QueryEngine::wildcard_to_regex("test?"), "(?i)test.");
        assert_eq!(QueryEngine::wildcard_to_regex("a*b?c"), "(?i)a.*b.c");
    }

    #[test]
    fn test_search_integration() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();

        // Add test entries
        index.insert(create_test_entry_with_id(1, "document.pdf"));
        index.insert(create_test_entry_with_id(2, "readme.txt"));
        index.insert(create_test_entry_with_id(3, "test_document.pdf"));
        index.insert(create_test_entry_with_id(4, "文档.pdf"));

        // Test fuzzy search
        let query = SearchQuery {
            keyword: "doc".to_string(),
            match_mode: MatchMode::Fuzzy,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert!(!results.is_empty());
        assert!(results.iter().any(|r| r.name.contains("document")));

        // Test exact search
        let query = SearchQuery {
            keyword: "readme".to_string(),
            match_mode: MatchMode::Exact,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].name, "readme.txt");

        // Test pinyin search
        let query = SearchQuery {
            keyword: "wd".to_string(),
            match_mode: MatchMode::Fuzzy,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert!(results.iter().any(|r| r.name == "文档.pdf"));
    }

    #[test]
    fn test_search_with_filters() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();

        index.insert(create_test_entry_with_id(1, "doc1.pdf"));
        index.insert(create_test_entry_with_id(2, "doc2.txt"));
        index.insert(create_test_entry_with_id(3, "doc3.pdf"));

        let query = SearchQuery {
            keyword: "doc".to_string(),
            match_mode: MatchMode::Fuzzy,
            filters: SearchFilters {
                extensions: Some(vec!["pdf".to_string()]),
                ..Default::default()
            },
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results.len(), 2);
        assert!(results.iter().all(|r| r.name.ends_with(".pdf")));
    }

    #[test]
    fn test_search_pagination() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();

        // Add many entries
        for i in 1..=20 {
            index.insert(create_test_entry_with_id(i, &format!("test{}.txt", i)));
        }

        // Get first page
        let query = SearchQuery {
            keyword: "test".to_string(),
            match_mode: MatchMode::Exact,
            limit: 5,
            offset: 0,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results.len(), 5);

        // Get second page
        let query = SearchQuery {
            keyword: "test".to_string(),
            match_mode: MatchMode::Exact,
            limit: 5,
            offset: 5,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results.len(), 5);
    }

    #[test]
    fn test_search_sorting() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();

        index.insert(FileEntry::new(1, 0, "b.txt".to_string(), 100, Utc::now(), Utc::now(), false, 'C'));
        index.insert(FileEntry::new(2, 0, "a.txt".to_string(), 200, Utc::now(), Utc::now(), false, 'C'));
        index.insert(FileEntry::new(3, 0, "c.txt".to_string(), 50, Utc::now(), Utc::now(), false, 'C'));

        // Sort by name ascending
        let query = SearchQuery {
            keyword: ".txt".to_string(),
            match_mode: MatchMode::Exact,
            sort_by: SortField::Name,
            sort_order: SortOrder::Asc,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results[0].name, "a.txt");
        assert_eq!(results[1].name, "b.txt");
        assert_eq!(results[2].name, "c.txt");

        // Sort by size descending
        let query = SearchQuery {
            keyword: ".txt".to_string(),
            match_mode: MatchMode::Exact,
            sort_by: SortField::Size,
            sort_order: SortOrder::Desc,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert_eq!(results[0].size, 200);
        assert_eq!(results[1].size, 100);
        assert_eq!(results[2].size, 50);
    }

    #[test]
    fn test_empty_keyword() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();
        index.insert(create_test_entry_with_id(1, "test.txt"));

        let query = SearchQuery {
            keyword: "".to_string(),
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert!(results.is_empty());

        let query = SearchQuery {
            keyword: "   ".to_string(),
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert!(results.is_empty());
    }

    #[test]
    fn test_invalid_regex() {
        let engine = QueryEngine::new();
        let mut index = FileIndex::new();
        index.insert(create_test_entry_with_id(1, "test.txt"));

        let query = SearchQuery {
            keyword: "[invalid".to_string(), // Invalid regex
            match_mode: MatchMode::Regex,
            ..Default::default()
        };
        let results = engine.search(&index, &query);
        assert!(results.is_empty()); // Should return empty, not panic
    }
}


// =============================================================================
// Property-Based Tests for Search Match Modes
// =============================================================================
//
// **Property 6: Search Match Modes Correctness**
// **Validates: Requirements 5.2**
//
// For any search query with a specified match mode (exact, wildcard, fuzzy, regex),
// the returned results SHALL only contain files that match according to that mode's
// semantics.
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use crate::index::FileIndex;
    use crate::models::FileEntry;
    use crate::protocol::{MatchMode, SearchFilters, SearchQuery, SortField, SortOrder};
    use chrono::{DateTime, Utc};
    use proptest::prelude::*;
    use proptest::strategy::BoxedStrategy;
    use regex::Regex;

    // =========================================================================
    // Arbitrary Strategies for Test Data Generation
    // =========================================================================

    /// Strategy for generating valid file names
    /// Generates alphanumeric names with some special characters and Chinese characters
    fn arb_file_name() -> impl Strategy<Value = String> {
        prop_oneof![
            // English names with extensions
            "[a-zA-Z][a-zA-Z0-9_-]{0,20}\\.[a-z]{1,4}",
            // Simple names without extension
            "[a-zA-Z][a-zA-Z0-9_-]{0,15}",
            // Names with numbers
            "[a-zA-Z]{1,5}[0-9]{1,5}\\.[a-z]{1,3}",
            // Chinese file names (common characters)
            "[\\u4e00-\\u9fa5]{1,8}\\.[a-z]{1,4}",
            // Mixed Chinese and English
            "[a-zA-Z]{1,3}[\\u4e00-\\u9fa5]{1,4}[0-9]{0,3}\\.[a-z]{1,3}",
        ]
        .prop_filter("non-empty name", |s| !s.is_empty() && s.len() <= 50)
    }

    /// Strategy for generating search keywords
    fn arb_keyword() -> impl Strategy<Value = String> {
        prop_oneof![
            // Short keywords (1-3 chars)
            "[a-zA-Z]{1,3}",
            // Medium keywords (4-8 chars)
            "[a-zA-Z]{4,8}",
            // Keywords with numbers
            "[a-zA-Z]{1,4}[0-9]{1,2}",
            // Chinese keywords
            "[\\u4e00-\\u9fa5]{1,4}",
        ]
        .prop_filter("non-empty keyword", |s| !s.is_empty())
    }

    /// Strategy for generating wildcard patterns
    fn arb_wildcard_pattern() -> impl Strategy<Value = String> {
        prop_oneof![
            // Prefix wildcard: *suffix
            Just("*".to_string()).prop_flat_map(|prefix| {
                "[a-zA-Z]{1,5}".prop_map(move |suffix| format!("{}{}", prefix, suffix))
            }),
            // Suffix wildcard: prefix*
            "[a-zA-Z]{1,5}".prop_map(|prefix| format!("{}*", prefix)),
            // Middle wildcard: prefix*suffix
            ("[a-zA-Z]{1,3}", "[a-zA-Z]{1,3}").prop_map(|(prefix, suffix)| {
                format!("{}*{}", prefix, suffix)
            }),
            // Single char wildcard: pre?ix
            "[a-zA-Z]{1,3}".prop_map(|prefix| format!("{}?", prefix)),
            // Extension wildcard: *.ext
            "[a-z]{1,4}".prop_map(|ext| format!("*.{}", ext)),
        ]
    }

    /// Strategy for generating valid regex patterns
    /// All patterns are case-insensitive to match the QueryEngine behavior
    fn arb_regex_pattern() -> impl Strategy<Value = String> {
        prop_oneof![
            // Simple literal match (case insensitive)
            "[a-z]{2,6}".prop_map(|s| format!("(?i){}", s)),
            // Case insensitive prefix
            "[a-z]{2,5}".prop_map(|s| format!("(?i){}", s)),
            // Digit pattern
            Just(r"\d+".to_string()),
            // Word boundary (case insensitive)
            "[a-z]{2,5}".prop_map(|s| format!(r"(?i)\b{}\b", s)),
            // Character class (already case insensitive by nature)
            Just(r"[a-zA-Z]+".to_string()),
            // Extension pattern (case insensitive)
            "[a-z]{1,4}".prop_map(|ext| format!(r"(?i)\.{}$", ext)),
        ]
    }

    /// Create a FileEntry for testing
    fn create_test_entry(file_id: u64, name: &str, volume: char) -> FileEntry {
        FileEntry::new(
            file_id,
            0,
            name.to_string(),
            1024,
            Utc::now(),
            Utc::now(),
            false,
            volume,
        )
    }

    /// Create a default SearchQuery with the given keyword and match mode
    fn create_query(keyword: &str, match_mode: MatchMode) -> SearchQuery {
        SearchQuery {
            keyword: keyword.to_string(),
            match_mode,
            filters: SearchFilters::default(),
            sort_by: SortField::Relevance,
            sort_order: SortOrder::Desc,
            limit: 1000,
            offset: 0,
        }
    }

    // =========================================================================
    // Helper Functions for Match Verification
    // =========================================================================

    /// Verify that a file name matches according to exact match semantics
    /// Exact match: the keyword must appear as a substring (case-insensitive)
    fn verify_exact_match(name: &str, keyword: &str) -> bool {
        name.to_lowercase().contains(&keyword.to_lowercase())
    }

    /// Verify that a file name matches according to wildcard semantics
    /// Wildcard: * matches any sequence, ? matches single character
    fn verify_wildcard_match(name: &str, pattern: &str) -> bool {
        // Convert wildcard pattern to regex
        let mut regex_pattern = String::from("(?i)");
        for c in pattern.chars() {
            match c {
                '*' => regex_pattern.push_str(".*"),
                '?' => regex_pattern.push('.'),
                '.' | '+' | '^' | '$' | '(' | ')' | '[' | ']' | '{' | '}' | '|' | '\\' => {
                    regex_pattern.push('\\');
                    regex_pattern.push(c);
                }
                _ => regex_pattern.push(c),
            }
        }

        match Regex::new(&regex_pattern) {
            Ok(re) => re.is_match(name),
            Err(_) => false,
        }
    }

    /// Verify that a file name matches according to fuzzy match semantics
    /// Fuzzy match: uses SkimMatcherV2, returns true if score > 0
    fn verify_fuzzy_match(name: &str, keyword: &str) -> bool {
        let matcher = SkimMatcherV2::default();
        matcher.fuzzy_match(&name.to_lowercase(), keyword).is_some()
    }

    /// Verify that a file name matches according to regex semantics
    fn verify_regex_match(name: &str, pattern: &str) -> bool {
        match Regex::new(pattern) {
            Ok(re) => re.is_match(name),
            Err(_) => false,
        }
    }

    // =========================================================================
    // Property Tests
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Exact Match Mode Correctness
        ///
        /// For any search query with exact match mode, all returned results SHALL
        /// contain the keyword as a substring (case-insensitive).
        #[test]
        fn prop_exact_match_returns_only_matching_files(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            keyword in arb_keyword(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create exact match query
            let query = create_query(&keyword, MatchMode::Exact);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all returned results must contain the keyword as substring
            for result in &results {
                let matches = verify_exact_match(&result.name, &keyword);
                // Also check pinyin match for Chinese names
                let entry = index.get(result.file_id);
                let pinyin_matches = entry.map(|e| {
                    e.pinyin_abbr.contains(&keyword.to_lowercase()) ||
                    e.pinyin.contains(&keyword.to_lowercase())
                }).unwrap_or(false);

                prop_assert!(
                    matches || pinyin_matches,
                    "Exact match result '{}' should contain keyword '{}' or match pinyin",
                    result.name,
                    keyword
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Exact Match Mode Does Not Return Non-Matching Files
        ///
        /// For any file that does NOT contain the keyword as substring,
        /// it SHALL NOT be returned in exact match results.
        #[test]
        fn prop_exact_match_excludes_non_matching_files(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in "[xyz]{3,6}", // Use rare characters to minimize accidental matches
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create exact match query
            let query = create_query(&keyword, MatchMode::Exact);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: no result should be a non-matching file
            for result in &results {
                let entry = index.get(result.file_id).unwrap();
                let name_matches = verify_exact_match(&result.name, &keyword);
                let pinyin_matches = entry.pinyin_abbr.contains(&keyword.to_lowercase()) ||
                                    entry.pinyin.contains(&keyword.to_lowercase());

                prop_assert!(
                    name_matches || pinyin_matches,
                    "Non-matching file '{}' should not be in exact match results for '{}'",
                    result.name,
                    keyword
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Wildcard Match Mode Correctness
        ///
        /// For any search query with wildcard match mode, all returned results SHALL
        /// match the wildcard pattern (* = any sequence, ? = single char).
        #[test]
        fn prop_wildcard_match_returns_only_matching_files(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            pattern in arb_wildcard_pattern(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create wildcard match query
            let query = create_query(&pattern, MatchMode::Wildcard);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all returned results must match the wildcard pattern
            for result in &results {
                let matches = verify_wildcard_match(&result.name, &pattern);
                // Also check pinyin match
                let entry = index.get(result.file_id);
                let pinyin_matches = entry.map(|e| {
                    verify_wildcard_match(&e.pinyin_abbr, &pattern) ||
                    verify_wildcard_match(&e.pinyin, &pattern)
                }).unwrap_or(false);

                prop_assert!(
                    matches || pinyin_matches,
                    "Wildcard match result '{}' should match pattern '{}' or pinyin",
                    result.name,
                    pattern
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Fuzzy Match Mode Correctness
        ///
        /// For any search query with fuzzy match mode, all returned results SHALL
        /// have a positive fuzzy match score.
        #[test]
        fn prop_fuzzy_match_returns_only_matching_files(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            keyword in arb_keyword(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create fuzzy match query
            let query = create_query(&keyword, MatchMode::Fuzzy);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all returned results must have positive fuzzy match score
            for result in &results {
                let matches = verify_fuzzy_match(&result.name, &keyword);
                // Also check pinyin match
                let entry = index.get(result.file_id);
                let pinyin_matches = entry.map(|e| {
                    e.pinyin_abbr.contains(&keyword.to_lowercase()) ||
                    e.pinyin.contains(&keyword.to_lowercase())
                }).unwrap_or(false);

                prop_assert!(
                    matches || pinyin_matches,
                    "Fuzzy match result '{}' should have positive score for keyword '{}' or match pinyin",
                    result.name,
                    keyword
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Fuzzy Match Returns Results with Positive Scores
        ///
        /// All results from fuzzy match should have score > 0.
        #[test]
        fn prop_fuzzy_match_results_have_positive_scores(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in arb_keyword(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create fuzzy match query
            let query = create_query(&keyword, MatchMode::Fuzzy);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all results should have positive scores
            for result in &results {
                prop_assert!(
                    result.score > 0,
                    "Fuzzy match result '{}' should have positive score, got {}",
                    result.name,
                    result.score
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Regex Match Mode Correctness
        ///
        /// For any search query with regex match mode, all returned results SHALL
        /// match the regex pattern.
        #[test]
        fn prop_regex_match_returns_only_matching_files(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            pattern in arb_regex_pattern(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create regex match query
            let query = create_query(&pattern, MatchMode::Regex);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all returned results must match the regex pattern
            for result in &results {
                let matches = verify_regex_match(&result.name, &pattern);
                // Also check pinyin match
                let entry = index.get(result.file_id);
                let pinyin_matches = entry.map(|e| {
                    verify_regex_match(&e.pinyin_abbr, &pattern) ||
                    verify_regex_match(&e.pinyin, &pattern)
                }).unwrap_or(false);

                prop_assert!(
                    matches || pinyin_matches,
                    "Regex match result '{}' should match pattern '{}' or pinyin",
                    result.name,
                    pattern
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Invalid Regex Returns Empty Results
        ///
        /// For any invalid regex pattern, the search should return empty results
        /// without panicking.
        #[test]
        fn prop_invalid_regex_returns_empty(
            file_names in proptest::collection::vec(arb_file_name(), 3..10),
            // Generate invalid regex patterns
            invalid_pattern in prop_oneof![
                Just("[invalid".to_string()),
                Just("(unclosed".to_string()),
                Just("*invalid".to_string()),
                Just("+invalid".to_string()),
                Just("(?P<>)".to_string()),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create regex match query with invalid pattern
            let query = create_query(&invalid_pattern, MatchMode::Regex);

            // Execute search - should not panic
            let results = engine.search(&index, &query);

            // Verify: should return empty results for invalid regex
            prop_assert!(
                results.is_empty(),
                "Invalid regex '{}' should return empty results, got {} results",
                invalid_pattern,
                results.len()
            );
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Match Mode Consistency - Same Files, Different Modes
        ///
        /// For a file that matches in exact mode, it should also match in fuzzy mode
        /// (fuzzy is more permissive than exact).
        #[test]
        fn prop_exact_match_implies_fuzzy_match(
            base_name in "[a-zA-Z]{3,8}",
            extension in "[a-z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            let file_name = format!("{}.{}", base_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Use the base_name as keyword (should match exactly)
            let exact_query = create_query(&base_name, MatchMode::Exact);
            let fuzzy_query = create_query(&base_name, MatchMode::Fuzzy);

            let exact_results = engine.search(&index, &exact_query);
            let fuzzy_results = engine.search(&index, &fuzzy_query);

            // If exact match finds the file, fuzzy should also find it
            if !exact_results.is_empty() {
                prop_assert!(
                    !fuzzy_results.is_empty(),
                    "File '{}' matched by exact mode should also match in fuzzy mode for keyword '{}'",
                    file_name,
                    base_name
                );
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Match Indices Are Valid
        ///
        /// For any search result, the match_indices should be valid byte positions
        /// within the file name.
        #[test]
        fn prop_match_indices_are_valid(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in arb_keyword(),
            match_mode in prop_oneof![
                Just(MatchMode::Exact),
                Just(MatchMode::Fuzzy),
                Just(MatchMode::Wildcard),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create query
            let query = create_query(&keyword, match_mode);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: all match indices should be valid
            for result in &results {
                for (start, end) in &result.match_indices {
                    prop_assert!(
                        *start <= *end,
                        "Match index start ({}) should be <= end ({}) for '{}'",
                        start,
                        end,
                        result.name
                    );
                    prop_assert!(
                        *end <= result.name.len(),
                        "Match index end ({}) should be <= name length ({}) for '{}'",
                        end,
                        result.name.len(),
                        result.name
                    );
                }
            }
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Empty Keyword Returns Empty Results
        ///
        /// For any match mode, an empty keyword should return empty results.
        #[test]
        fn prop_empty_keyword_returns_empty(
            file_names in proptest::collection::vec(arb_file_name(), 3..10),
            match_mode in prop_oneof![
                Just(MatchMode::Exact),
                Just(MatchMode::Fuzzy),
                Just(MatchMode::Wildcard),
                Just(MatchMode::Regex),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create query with empty keyword
            let query = create_query("", match_mode);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: should return empty results
            prop_assert!(
                results.is_empty(),
                "Empty keyword should return empty results for {:?} mode, got {} results",
                match_mode,
                results.len()
            );
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Whitespace-Only Keyword Returns Empty Results
        ///
        /// For any match mode, a whitespace-only keyword should return empty results.
        #[test]
        fn prop_whitespace_keyword_returns_empty(
            file_names in proptest::collection::vec(arb_file_name(), 3..10),
            whitespace in "[ \\t\\n]{1,5}",
            match_mode in prop_oneof![
                Just(MatchMode::Exact),
                Just(MatchMode::Fuzzy),
                Just(MatchMode::Wildcard),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert all files into the index
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Create query with whitespace keyword
            let query = create_query(&whitespace, match_mode);

            // Execute search
            let results = engine.search(&index, &query);

            // Verify: should return empty results
            prop_assert!(
                results.is_empty(),
                "Whitespace keyword '{}' should return empty results for {:?} mode, got {} results",
                whitespace.escape_debug(),
                match_mode,
                results.len()
            );
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Case Insensitivity for Exact and Wildcard Modes
        ///
        /// Exact and wildcard matches should be case-insensitive.
        #[test]
        fn prop_case_insensitive_matching(
            base_name in "[a-zA-Z]{3,8}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file with mixed case
            let file_name = format!("{}.txt", base_name);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search with uppercase keyword
            let upper_keyword = base_name.to_uppercase();
            let lower_keyword = base_name.to_lowercase();

            let upper_exact = engine.search(&index, &create_query(&upper_keyword, MatchMode::Exact));
            let lower_exact = engine.search(&index, &create_query(&lower_keyword, MatchMode::Exact));

            // Both should find the same results
            prop_assert_eq!(
                upper_exact.len(),
                lower_exact.len(),
                "Case should not affect exact match results: upper={}, lower={}",
                upper_exact.len(),
                lower_exact.len()
            );
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Wildcard * Matches Any Sequence
        ///
        /// The * wildcard should match any sequence of characters (including empty).
        #[test]
        fn prop_wildcard_asterisk_matches_any_sequence(
            prefix in "[a-zA-Z]{1,4}",
            middle in "[a-zA-Z0-9]{0,10}",
            suffix in "[a-zA-Z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file with prefix + middle + suffix
            let file_name = format!("{}{}{}.txt", prefix, middle, suffix);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search with prefix*suffix pattern
            let pattern = format!("{}*{}", prefix, suffix);
            let query = create_query(&pattern, MatchMode::Wildcard);

            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                !results.is_empty(),
                "Wildcard pattern '{}' should match file '{}'",
                pattern,
                file_name
            );
        }

        /// **Validates: Requirements 5.2**
        ///
        /// Property 6: Wildcard ? Matches Single Character
        ///
        /// The ? wildcard should match exactly one character.
        #[test]
        fn prop_wildcard_question_matches_single_char(
            prefix in "[a-zA-Z]{1,4}",
            single_char in "[a-zA-Z0-9]",
            suffix in "[a-zA-Z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file with prefix + single char + suffix
            let file_name = format!("{}{}{}.txt", prefix, single_char, suffix);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search with prefix?suffix pattern
            let pattern = format!("{}?{}", prefix, suffix);
            let query = create_query(&pattern, MatchMode::Wildcard);

            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                !results.is_empty(),
                "Wildcard pattern '{}' should match file '{}'",
                pattern,
                file_name
            );
        }
    }

    // =========================================================================
    // Property-Based Tests for Pinyin Search
    // =========================================================================
    //
    // **Property 7: Pinyin Search Correctness**
    // **Validates: Requirements 5.3**
    //
    // For any Chinese filename in the index, searching by its pinyin abbreviation
    // (first letters) or full pinyin SHALL return that file in the results.
    // =========================================================================

    /// Strategy for generating Chinese characters from CJK Unified Ideographs block
    fn arb_chinese_char() -> impl Strategy<Value = char> {
        // CJK Unified Ideographs: U+4E00 to U+9FFF
        proptest::char::range('\u{4E00}', '\u{9FFF}')
    }

    /// Strategy for generating Chinese strings of specified length
    fn arb_chinese_string(min_len: usize, max_len: usize) -> impl Strategy<Value = String> {
        proptest::collection::vec(arb_chinese_char(), min_len..=max_len)
            .prop_map(|chars| chars.into_iter().collect())
    }

    /// Strategy for generating Chinese filenames with extensions
    fn arb_chinese_filename() -> impl Strategy<Value = String> {
        (arb_chinese_string(1, 6), prop_oneof![
            Just("txt".to_string()),
            Just("pdf".to_string()),
            Just("doc".to_string()),
            Just("png".to_string()),
            Just("jpg".to_string()),
        ]).prop_map(|(name, ext)| format!("{}.{}", name, ext))
    }

    /// Strategy for generating mixed Chinese/English filenames
    fn arb_mixed_filename() -> impl Strategy<Value = String> {
        prop_oneof![
            // Chinese only
            arb_chinese_filename(),
            // English prefix + Chinese
            ("[a-zA-Z]{1,3}", arb_chinese_string(1, 4), "[a-z]{1,3}")
                .prop_map(|(prefix, chinese, ext)| format!("{}{}.{}", prefix, chinese, ext)),
            // Chinese + English suffix
            (arb_chinese_string(1, 4), "[a-zA-Z0-9]{1,4}", "[a-z]{1,3}")
                .prop_map(|(chinese, suffix, ext)| format!("{}{}.{}", chinese, suffix, ext)),
            // Interleaved
            ("[a-zA-Z]{1,2}", arb_chinese_string(1, 3), "[a-zA-Z0-9]{1,2}", "[a-z]{1,3}")
                .prop_map(|(p1, chinese, p2, ext)| format!("{}{}{}.{}", p1, chinese, p2, ext)),
        ]
    }

    /// Get pinyin abbreviation for a string using the same logic as FileEntry
    fn get_pinyin_abbr(name: &str) -> String {
        use pinyin::ToPinyin;
        
        let mut abbr = String::new();
        for c in name.chars() {
            if let Some(py) = c.to_pinyin() {
                if let Some(first) = py.plain().chars().next() {
                    abbr.push(first);
                }
            } else if c.is_alphanumeric() {
                abbr.push(c.to_ascii_lowercase());
            }
        }
        abbr
    }

    /// Get full pinyin for a string using the same logic as FileEntry
    fn get_full_pinyin(name: &str) -> String {
        use pinyin::ToPinyin;
        
        let mut full_pinyin = String::new();
        for c in name.chars() {
            if let Some(py) = c.to_pinyin() {
                full_pinyin.push_str(py.plain());
            } else {
                full_pinyin.push(c);
            }
        }
        full_pinyin.to_lowercase()
    }

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Pinyin Abbreviation Search Finds Chinese Files
        ///
        /// For any Chinese filename in the index, searching by its pinyin abbreviation
        /// (first letters of each character's pinyin) SHALL return that file in the results.
        #[test]
        fn prop_pinyin_abbr_search_finds_chinese_file(
            chinese_name in arb_chinese_string(2, 5),
            extension in prop_oneof![
                Just("txt".to_string()),
                Just("pdf".to_string()),
                Just("doc".to_string()),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create Chinese filename
            let file_name = format!("{}.{}", chinese_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            
            // Get the pinyin abbreviation
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            // Skip if pinyin abbreviation is empty (shouldn't happen for Chinese chars)
            prop_assume!(!pinyin_abbr.is_empty());
            
            index.insert(entry);

            // Search using pinyin abbreviation
            let query = create_query(&pinyin_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                results.iter().any(|r| r.name == file_name),
                "Pinyin abbreviation '{}' should find Chinese file '{}' (pinyin_abbr: {})",
                pinyin_abbr,
                file_name,
                pinyin_abbr
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Full Pinyin Search Finds Chinese Files
        ///
        /// For any Chinese filename in the index, searching by its full pinyin
        /// SHALL return that file in the results.
        #[test]
        fn prop_full_pinyin_search_finds_chinese_file(
            chinese_name in arb_chinese_string(1, 4),
            extension in prop_oneof![
                Just("txt".to_string()),
                Just("pdf".to_string()),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create Chinese filename
            let file_name = format!("{}.{}", chinese_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            
            // Get the full pinyin
            let full_pinyin = entry.pinyin.clone();
            
            // Skip if pinyin is empty
            prop_assume!(!full_pinyin.is_empty());
            // Skip if pinyin is too long (would be slow to search)
            prop_assume!(full_pinyin.len() <= 30);
            
            index.insert(entry);

            // Search using full pinyin
            let query = create_query(&full_pinyin, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                results.iter().any(|r| r.name == file_name),
                "Full pinyin '{}' should find Chinese file '{}'",
                full_pinyin,
                file_name
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Partial Pinyin Abbreviation Search Works
        ///
        /// For any Chinese filename, searching by a prefix of its pinyin abbreviation
        /// SHALL return that file in the results.
        #[test]
        fn prop_partial_pinyin_abbr_search_finds_file(
            chinese_name in arb_chinese_string(3, 6),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create Chinese filename
            let file_name = format!("{}.txt", chinese_name);
            let entry = create_test_entry(1, &file_name, 'C');
            
            // Get the pinyin abbreviation
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            // Skip if pinyin abbreviation is too short
            prop_assume!(pinyin_abbr.len() >= 2);
            
            // Use first 2 characters of pinyin abbreviation
            let partial_abbr: String = pinyin_abbr.chars().take(2).collect();
            
            index.insert(entry);

            // Search using partial pinyin abbreviation
            let query = create_query(&partial_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                results.iter().any(|r| r.name == file_name),
                "Partial pinyin abbreviation '{}' should find Chinese file '{}' (full abbr: {})",
                partial_abbr,
                file_name,
                pinyin_abbr
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Mixed Chinese/English Filename Pinyin Search
        ///
        /// For mixed Chinese/English filenames, searching by pinyin should find the file.
        #[test]
        fn prop_mixed_filename_pinyin_search(
            mixed_name in arb_mixed_filename(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            let entry = create_test_entry(1, &mixed_name, 'C');
            
            // Get the pinyin abbreviation
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            // Skip if pinyin abbreviation is empty or too short
            prop_assume!(pinyin_abbr.len() >= 2);
            
            index.insert(entry);

            // Search using pinyin abbreviation
            let query = create_query(&pinyin_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // Should find the file
            prop_assert!(
                results.iter().any(|r| r.name == mixed_name),
                "Pinyin abbreviation '{}' should find mixed file '{}'",
                pinyin_abbr,
                mixed_name
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Pinyin Search Score Lower Than Exact Name Match
        ///
        /// When a file matches both by name and by pinyin, the name match should
        /// have a higher score than a pure pinyin match.
        #[test]
        fn prop_pinyin_match_score_lower_than_name_match(
            chinese_name in arb_chinese_string(2, 4),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create Chinese filename
            let file_name = format!("{}.txt", chinese_name);
            let entry = create_test_entry(1, &file_name, 'C');
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            // Create another file that contains the pinyin abbreviation in its name
            let english_file = format!("{}.txt", pinyin_abbr);
            let entry2 = create_test_entry(2, &english_file, 'C');
            
            // Skip if pinyin abbreviation is empty
            prop_assume!(!pinyin_abbr.is_empty());
            
            index.insert(entry);
            index.insert(entry2);

            // Search using pinyin abbreviation
            let query = create_query(&pinyin_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // Both files should be found
            let chinese_result = results.iter().find(|r| r.name == file_name);
            let english_result = results.iter().find(|r| r.name == english_file);

            // If both are found, the exact name match should have higher score
            if let (Some(chinese), Some(english)) = (chinese_result, english_result) {
                prop_assert!(
                    english.score >= chinese.score,
                    "Exact name match '{}' (score: {}) should have >= score than pinyin match '{}' (score: {})",
                    english_file,
                    english.score,
                    file_name,
                    chinese.score
                );
            }
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Pinyin Search Among Multiple Chinese Files
        ///
        /// When multiple Chinese files are in the index, pinyin search should
        /// correctly find files that match the pinyin pattern.
        #[test]
        fn prop_pinyin_search_among_multiple_files(
            chinese_names in proptest::collection::vec(arb_chinese_string(2, 4), 3..8),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create multiple Chinese files
            let mut file_entries: Vec<(String, String)> = Vec::new();
            for (i, name) in chinese_names.iter().enumerate() {
                let file_name = format!("{}.txt", name);
                let entry = create_test_entry(i as u64 + 1, &file_name, 'C');
                let pinyin_abbr = entry.pinyin_abbr.clone();
                file_entries.push((file_name, pinyin_abbr));
                index.insert(entry);
            }

            // Pick the first file's pinyin abbreviation to search
            let (target_file, target_abbr) = &file_entries[0];
            
            // Skip if pinyin abbreviation is empty
            prop_assume!(!target_abbr.is_empty());

            // Search using the target's pinyin abbreviation
            let query = create_query(target_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            // The target file should be in the results
            prop_assert!(
                results.iter().any(|r| &r.name == target_file),
                "Pinyin abbreviation '{}' should find target file '{}' among {} files",
                target_abbr,
                target_file,
                chinese_names.len()
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Pinyin Search Case Insensitivity
        ///
        /// Pinyin search should be case-insensitive.
        #[test]
        fn prop_pinyin_search_case_insensitive(
            chinese_name in arb_chinese_string(2, 4),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create Chinese filename
            let file_name = format!("{}.txt", chinese_name);
            let entry = create_test_entry(1, &file_name, 'C');
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            // Skip if pinyin abbreviation is empty
            prop_assume!(!pinyin_abbr.is_empty());
            
            index.insert(entry);

            // Search with uppercase pinyin
            let upper_abbr = pinyin_abbr.to_uppercase();
            let query_upper = create_query(&upper_abbr, MatchMode::Fuzzy);
            let results_upper = engine.search(&index, &query_upper);

            // Search with lowercase pinyin
            let lower_abbr = pinyin_abbr.to_lowercase();
            let query_lower = create_query(&lower_abbr, MatchMode::Fuzzy);
            let results_lower = engine.search(&index, &query_lower);

            // Both should find the file
            let found_upper = results_upper.iter().any(|r| r.name == file_name);
            let found_lower = results_lower.iter().any(|r| r.name == file_name);

            prop_assert!(
                found_upper == found_lower,
                "Case should not affect pinyin search: upper='{}' found={}, lower='{}' found={}",
                upper_abbr,
                found_upper,
                lower_abbr,
                found_lower
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Pinyin Abbreviation Stored Correctly
        ///
        /// The pinyin abbreviation stored in FileEntry should match the expected
        /// first letters of each character's pinyin.
        #[test]
        fn prop_pinyin_abbr_stored_correctly(
            chinese_name in arb_chinese_string(1, 6),
        ) {
            let file_name = format!("{}.txt", chinese_name);
            let entry = create_test_entry(1, &file_name, 'C');
            
            // Calculate expected pinyin abbreviation
            let expected_abbr = get_pinyin_abbr(&file_name);
            
            prop_assert_eq!(
                entry.pinyin_abbr,
                expected_abbr,
                "Stored pinyin abbreviation should match expected for '{}'",
                file_name
            );
        }

        /// **Validates: Requirements 5.3**
        ///
        /// Property 7: Full Pinyin Stored Correctly
        ///
        /// The full pinyin stored in FileEntry should match the expected
        /// pinyin conversion.
        #[test]
        fn prop_full_pinyin_stored_correctly(
            chinese_name in arb_chinese_string(1, 4),
        ) {
            let file_name = format!("{}.txt", chinese_name);
            let entry = create_test_entry(1, &file_name, 'C');
            
            // Calculate expected full pinyin
            let expected_pinyin = get_full_pinyin(&file_name);
            
            prop_assert_eq!(
                entry.pinyin,
                expected_pinyin,
                "Stored full pinyin should match expected for '{}'",
                file_name
            );
        }
    }

    // =========================================================================
    // Property-Based Tests for Sorting and Filtering
    // =========================================================================
    //
    // **Property 8: Search Result Ordering**
    // **Property 9: Search Filtering Correctness**
    // **Property 10: Pagination Correctness**
    // **Validates: Requirements 5.4, 5.5, 5.6, 5.7**
    //
    // These tests verify that sorting, filtering, and pagination work correctly
    // across all valid inputs.
    // =========================================================================

    /// Strategy for generating arbitrary file sizes
    fn arb_file_size() -> impl Strategy<Value = u64> {
        prop_oneof![
            // Small files (0 - 1KB)
            0u64..1024u64,
            // Medium files (1KB - 1MB)
            1024u64..1_048_576u64,
            // Large files (1MB - 1GB)
            1_048_576u64..1_073_741_824u64,
        ]
    }

    /// Strategy for generating arbitrary DateTime<Utc>
    fn arb_datetime_for_filter() -> impl Strategy<Value = DateTime<Utc>> {
        // Generate timestamps between 2020-01-01 and 2025-12-31
        (1577836800i64..1767225600i64).prop_map(|ts| {
            DateTime::from_timestamp(ts, 0).unwrap_or_else(|| Utc::now())
        })
    }

    /// Strategy for generating file entries with various attributes
    fn arb_file_entry_with_attrs() -> BoxedStrategy<(String, u64, DateTime<Utc>, bool, char)> {
        (
            arb_file_name(),
            arb_file_size(),
            arb_datetime_for_filter(),
            any::<bool>(), // is_directory
            prop_oneof![Just('C'), Just('D'), Just('E')], // volume
        ).boxed()
    }

    /// Create a FileEntry with specific attributes for testing
    fn create_entry_with_attrs(
        file_id: u64,
        name: &str,
        size: u64,
        modified: DateTime<Utc>,
        is_directory: bool,
        volume: char,
    ) -> FileEntry {
        let mut entry = FileEntry::new(
            file_id,
            0,
            name.to_string(),
            size,
            modified,
            modified,
            is_directory,
            volume,
        );
        entry.size = size;
        entry.modified = modified;
        entry.is_directory = is_directory;
        entry.volume = volume;
        entry
    }

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        // =====================================================================
        // Property 8: Search Result Ordering
        // **Validates: Requirements 5.4, 5.5**
        // =====================================================================

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Name Ascending
        ///
        /// For any search query sorted by name ascending, the results SHALL be
        /// in alphabetical order (case-insensitive).
        #[test]
        fn prop_sort_by_name_ascending(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Insert files with unique IDs
            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Search with sort by name ascending
            let query = SearchQuery {
                keyword: ".".to_string(), // Match most files
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify ordering: each result should be <= next result (case-insensitive)
            for i in 0..results.len().saturating_sub(1) {
                let current = results[i].name.to_lowercase();
                let next = results[i + 1].name.to_lowercase();
                prop_assert!(
                    current <= next,
                    "Results not sorted by name ascending: '{}' should come before '{}'",
                    results[i].name,
                    results[i + 1].name
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Name Descending
        ///
        /// For any search query sorted by name descending, the results SHALL be
        /// in reverse alphabetical order (case-insensitive).
        #[test]
        fn prop_sort_by_name_descending(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Desc,
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify ordering: each result should be >= next result
            for i in 0..results.len().saturating_sub(1) {
                let current = results[i].name.to_lowercase();
                let next = results[i + 1].name.to_lowercase();
                prop_assert!(
                    current >= next,
                    "Results not sorted by name descending: '{}' should come after '{}'",
                    results[i].name,
                    results[i + 1].name
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Size Ascending
        ///
        /// For any search query sorted by size ascending, smaller files SHALL
        /// appear before larger files.
        #[test]
        fn prop_sort_by_size_ascending(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Size,
                sort_order: SortOrder::Asc,
                limit: 1000,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify ordering: each result's size should be <= next result's size
            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].size <= results[i + 1].size,
                    "Results not sorted by size ascending: {} should come before {}",
                    results[i].size,
                    results[i + 1].size
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Size Descending
        ///
        /// For any search query sorted by size descending, larger files SHALL
        /// appear before smaller files.
        #[test]
        fn prop_sort_by_size_descending(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Size,
                sort_order: SortOrder::Desc,
                limit: 1000,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].size >= results[i + 1].size,
                    "Results not sorted by size descending: {} should come after {}",
                    results[i].size,
                    results[i + 1].size
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Modified Time Ascending
        ///
        /// For any search query sorted by modified time ascending, older files
        /// SHALL appear before newer files.
        #[test]
        fn prop_sort_by_modified_ascending(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Modified,
                sort_order: SortOrder::Asc,
                limit: 1000,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].modified <= results[i + 1].modified,
                    "Results not sorted by modified ascending: {:?} should come before {:?}",
                    results[i].modified,
                    results[i + 1].modified
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Modified Time Descending
        ///
        /// For any search query sorted by modified time descending, newer files
        /// SHALL appear before older files.
        #[test]
        fn prop_sort_by_modified_descending(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Modified,
                sort_order: SortOrder::Desc,
                limit: 1000,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].modified >= results[i + 1].modified,
                    "Results not sorted by modified descending: {:?} should come after {:?}",
                    results[i].modified,
                    results[i + 1].modified
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Path Ascending
        ///
        /// For any search query sorted by path ascending, results SHALL be
        /// ordered by their full path.
        #[test]
        fn prop_sort_by_path_ascending(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Path,
                sort_order: SortOrder::Asc,
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].path <= results[i + 1].path,
                    "Results not sorted by path ascending: {:?} should come before {:?}",
                    results[i].path,
                    results[i + 1].path
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sort by Relevance Descending (Default)
        ///
        /// For any search query sorted by relevance descending, higher scoring
        /// results SHALL appear before lower scoring results.
        #[test]
        fn prop_sort_by_relevance_descending(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            keyword in "[a-zA-Z]{2,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: keyword.clone(),
                match_mode: MatchMode::Fuzzy,
                sort_by: SortField::Relevance,
                sort_order: SortOrder::Desc,
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify ordering: each result's score should be >= next result's score
            for i in 0..results.len().saturating_sub(1) {
                prop_assert!(
                    results[i].score >= results[i + 1].score,
                    "Results not sorted by relevance descending: score {} should come before {}",
                    results[i].score,
                    results[i + 1].score
                );
            }
        }

        /// **Validates: Requirements 5.4, 5.5**
        ///
        /// Property 8: Sorting is Idempotent
        ///
        /// Applying the same sort twice should produce the same result.
        #[test]
        fn prop_sorting_is_idempotent(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            sort_field in prop_oneof![
                Just(SortField::Name),
                Just(SortField::Size),
                Just(SortField::Modified),
                Just(SortField::Path),
            ],
            sort_order in prop_oneof![Just(SortOrder::Asc), Just(SortOrder::Desc)],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: sort_field,
                sort_order,
                limit: 1000,
                ..Default::default()
            };

            let results1 = engine.search(&index, &query);
            let results2 = engine.search(&index, &query);

            // Results should be identical
            prop_assert_eq!(
                results1.len(),
                results2.len(),
                "Idempotent search should return same number of results"
            );

            for (r1, r2) in results1.iter().zip(results2.iter()) {
                prop_assert_eq!(
                    r1.file_id,
                    r2.file_id,
                    "Idempotent search should return same results in same order"
                );
            }
        }

        // =====================================================================
        // Property 9: Search Filtering Correctness
        // **Validates: Requirements 5.6**
        // =====================================================================

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Extension Filter Correctness
        ///
        /// For any search query with extension filters, all returned results
        /// SHALL have one of the specified extensions.
        #[test]
        fn prop_filter_by_extension(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 10..30),
            filter_extensions in proptest::collection::vec(
                prop_oneof![
                    Just("txt".to_string()),
                    Just("pdf".to_string()),
                    Just("doc".to_string()),
                    Just("jpg".to_string()),
                    Just("png".to_string()),
                ],
                1..3
            ),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    extensions: Some(filter_extensions.clone()),
                    include_directories: false,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: all results must have one of the specified extensions
            for result in &results {
                let ext = result.name
                    .rsplit('.')
                    .next()
                    .map(|s| s.to_lowercase())
                    .unwrap_or_default();

                prop_assert!(
                    filter_extensions.iter().any(|e| e.to_lowercase() == ext),
                    "Result '{}' has extension '{}' which is not in filter {:?}",
                    result.name,
                    ext,
                    filter_extensions
                );
            }
        }

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Size Range Filter Correctness
        ///
        /// For any search query with size range filters, all returned results
        /// SHALL have sizes within the specified range.
        #[test]
        fn prop_filter_by_size_range(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 10..25),
            min_size in 0u64..500_000u64,
            size_range in 1000u64..1_000_000u64,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let max_size = min_size.saturating_add(size_range);

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    min_size: Some(min_size),
                    max_size: Some(max_size),
                    include_directories: true,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: all results must have size within range
            for result in &results {
                prop_assert!(
                    result.size >= min_size,
                    "Result '{}' has size {} which is less than min_size {}",
                    result.name,
                    result.size,
                    min_size
                );
                prop_assert!(
                    result.size <= max_size,
                    "Result '{}' has size {} which is greater than max_size {}",
                    result.name,
                    result.size,
                    max_size
                );
            }
        }

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Date Range Filter Correctness
        ///
        /// For any search query with date range filters, all returned results
        /// SHALL have modification times within the specified range.
        #[test]
        fn prop_filter_by_date_range(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 10..25),
            start_ts in 1577836800i64..1700000000i64, // 2020-01-01 to ~2023
            range_days in 30i64..365i64,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let modified_after = DateTime::from_timestamp(start_ts, 0).unwrap();
            let modified_before = DateTime::from_timestamp(start_ts + range_days * 86400, 0).unwrap();

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    modified_after: Some(modified_after),
                    modified_before: Some(modified_before),
                    include_directories: true,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: all results must have modified time within range
            for result in &results {
                prop_assert!(
                    result.modified >= modified_after,
                    "Result '{}' modified {:?} is before filter {:?}",
                    result.name,
                    result.modified,
                    modified_after
                );
                prop_assert!(
                    result.modified <= modified_before,
                    "Result '{}' modified {:?} is after filter {:?}",
                    result.name,
                    result.modified,
                    modified_before
                );
            }
        }

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Volume Filter Correctness
        ///
        /// For any search query with volume filters, all returned results
        /// SHALL be from one of the specified volumes.
        #[test]
        fn prop_filter_by_volume(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 10..25),
            filter_volumes in proptest::collection::vec(
                prop_oneof![Just('C'), Just('D'), Just('E')],
                1..3
            ),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    volumes: Some(filter_volumes.clone()),
                    include_directories: true,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: all results must be from specified volumes
            // Note: We need to check the original entry's volume
            for result in &results {
                let entry = index.get(result.file_id).unwrap();
                prop_assert!(
                    filter_volumes.contains(&entry.volume),
                    "Result '{}' is from volume '{}' which is not in filter {:?}",
                    result.name,
                    entry.volume,
                    filter_volumes
                );
            }
        }

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Directory Exclusion Filter Correctness
        ///
        /// When include_directories is false, no directories SHALL be returned.
        #[test]
        fn prop_filter_exclude_directories(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 10..25),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    include_directories: false,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: no directories in results
            for result in &results {
                prop_assert!(
                    !result.is_directory,
                    "Result '{}' is a directory but include_directories is false",
                    result.name
                );
            }
        }

        /// **Validates: Requirements 5.6**
        ///
        /// Property 9: Combined Filters Correctness
        ///
        /// When multiple filters are applied, all returned results SHALL
        /// satisfy ALL filter conditions.
        #[test]
        fn prop_combined_filters(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 15..30),
            min_size in 0u64..100_000u64,
            max_size in 500_000u64..2_000_000u64,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            let filter_volumes = vec!['C', 'D'];

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                filters: SearchFilters {
                    min_size: Some(min_size),
                    max_size: Some(max_size),
                    volumes: Some(filter_volumes.clone()),
                    include_directories: false,
                    ..Default::default()
                },
                limit: 1000,
                ..Default::default()
            };

            let results = engine.search(&index, &query);

            // Verify: all results must satisfy ALL conditions
            for result in &results {
                let entry = index.get(result.file_id).unwrap();

                prop_assert!(
                    result.size >= min_size && result.size <= max_size,
                    "Result '{}' size {} not in range [{}, {}]",
                    result.name,
                    result.size,
                    min_size,
                    max_size
                );

                prop_assert!(
                    filter_volumes.contains(&entry.volume),
                    "Result '{}' volume '{}' not in {:?}",
                    result.name,
                    entry.volume,
                    filter_volumes
                );

                prop_assert!(
                    !result.is_directory,
                    "Result '{}' is a directory",
                    result.name
                );
            }
        }

        // =====================================================================
        // Property 10: Pagination Correctness
        // **Validates: Requirements 5.7**
        // =====================================================================

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Pagination Returns Correct Subset
        ///
        /// For any search query with limit and offset, the returned results
        /// SHALL be a correct subset of the full result set.
        #[test]
        fn prop_pagination_returns_correct_subset(
            file_names in proptest::collection::vec(arb_file_name(), 20..50),
            page_size in 5usize..15usize,
            page_num in 0usize..5usize,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Get full results (no pagination)
            let full_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: 10000,
                offset: 0,
                ..Default::default()
            };
            let full_results = engine.search(&index, &full_query);

            // Get paginated results
            let offset = page_num * page_size;
            let paginated_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: page_size,
                offset,
                ..Default::default()
            };
            let paginated_results = engine.search(&index, &paginated_query);

            // Calculate expected slice
            let expected_start = offset.min(full_results.len());
            let expected_end = (offset + page_size).min(full_results.len());
            let expected_len = expected_end - expected_start;

            // Verify length
            prop_assert_eq!(
                paginated_results.len(),
                expected_len,
                "Paginated results length {} != expected {} (offset={}, limit={}, total={})",
                paginated_results.len(),
                expected_len,
                offset,
                page_size,
                full_results.len()
            );

            // Verify content matches expected slice
            for (i, result) in paginated_results.iter().enumerate() {
                let expected_idx = expected_start + i;
                prop_assert_eq!(
                    result.file_id,
                    full_results[expected_idx].file_id,
                    "Paginated result at index {} doesn't match full result at index {}",
                    i,
                    expected_idx
                );
            }
        }

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Pagination Completeness
        ///
        /// Iterating through all pages should return all results exactly once.
        #[test]
        fn prop_pagination_completeness(
            file_names in proptest::collection::vec(arb_file_name(), 10..40),
            page_size in 3usize..10usize,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Get full results
            let full_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: 10000,
                offset: 0,
                ..Default::default()
            };
            let full_results = engine.search(&index, &full_query);

            // Collect all paginated results
            let mut all_paginated: Vec<u64> = Vec::new();
            let mut offset = 0;

            loop {
                let query = SearchQuery {
                    keyword: ".".to_string(),
                    match_mode: MatchMode::Exact,
                    sort_by: SortField::Name,
                    sort_order: SortOrder::Asc,
                    limit: page_size,
                    offset,
                    ..Default::default()
                };
                let page_results = engine.search(&index, &query);

                if page_results.is_empty() {
                    break;
                }

                for result in &page_results {
                    all_paginated.push(result.file_id);
                }

                offset += page_size;

                // Safety limit to prevent infinite loops
                if offset > full_results.len() + page_size {
                    break;
                }
            }

            // Verify completeness: all paginated results should match full results
            prop_assert_eq!(
                all_paginated.len(),
                full_results.len(),
                "Total paginated results {} != full results {}",
                all_paginated.len(),
                full_results.len()
            );

            for (i, file_id) in all_paginated.iter().enumerate() {
                prop_assert_eq!(
                    *file_id,
                    full_results[i].file_id,
                    "Paginated result at index {} doesn't match full result",
                    i
                );
            }
        }

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Offset Beyond Results Returns Empty
        ///
        /// When offset is greater than or equal to total results, an empty
        /// result set SHALL be returned.
        #[test]
        fn prop_pagination_offset_beyond_results(
            file_names in proptest::collection::vec(arb_file_name(), 5..20),
            extra_offset in 0usize..100usize,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            // Get total count
            let count_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                limit: 10000,
                offset: 0,
                ..Default::default()
            };
            let total = engine.search(&index, &count_query).len();

            // Query with offset beyond total
            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                limit: 10,
                offset: total + extra_offset,
                ..Default::default()
            };
            let results = engine.search(&index, &query);

            prop_assert!(
                results.is_empty(),
                "Offset {} beyond total {} should return empty, got {} results",
                total + extra_offset,
                total,
                results.len()
            );
        }

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Zero Limit Returns Empty
        ///
        /// When limit is 0, an empty result set SHALL be returned.
        #[test]
        fn prop_pagination_zero_limit(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                limit: 0,
                offset: 0,
                ..Default::default()
            };
            let results = engine.search(&index, &query);

            prop_assert!(
                results.is_empty(),
                "Zero limit should return empty results, got {}",
                results.len()
            );
        }

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Pagination with Sorting Consistency
        ///
        /// Pagination should work correctly with any sort order.
        #[test]
        fn prop_pagination_with_sorting(
            entries in proptest::collection::vec(arb_file_entry_with_attrs(), 15..30),
            page_size in 5usize..10usize,
            sort_field in prop_oneof![
                Just(SortField::Name),
                Just(SortField::Size),
                Just(SortField::Modified),
            ],
            sort_order in prop_oneof![Just(SortOrder::Asc), Just(SortOrder::Desc)],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, (name, size, modified, is_dir, volume)) in entries.iter().enumerate() {
                let entry = create_entry_with_attrs(
                    i as u64 + 1,
                    name,
                    *size,
                    *modified,
                    *is_dir,
                    *volume,
                );
                index.insert(entry);
            }

            // Get full sorted results
            let full_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: sort_field,
                sort_order,
                limit: 10000,
                offset: 0,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };
            let full_results = engine.search(&index, &full_query);

            // Get first page
            let page1_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: sort_field,
                sort_order,
                limit: page_size,
                offset: 0,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };
            let page1 = engine.search(&index, &page1_query);

            // Get second page
            let page2_query = SearchQuery {
                keyword: ".".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: sort_field,
                sort_order,
                limit: page_size,
                offset: page_size,
                filters: SearchFilters {
                    include_directories: true,
                    ..Default::default()
                },
                ..Default::default()
            };
            let page2 = engine.search(&index, &page2_query);

            // Verify page 1 matches first slice of full results
            for (i, result) in page1.iter().enumerate() {
                if i < full_results.len() {
                    prop_assert_eq!(
                        result.file_id,
                        full_results[i].file_id,
                        "Page 1 result {} doesn't match full result",
                        i
                    );
                }
            }

            // Verify page 2 matches second slice of full results
            for (i, result) in page2.iter().enumerate() {
                let full_idx = page_size + i;
                if full_idx < full_results.len() {
                    prop_assert_eq!(
                        result.file_id,
                        full_results[full_idx].file_id,
                        "Page 2 result {} doesn't match full result at {}",
                        i,
                        full_idx
                    );
                }
            }
        }

        /// **Validates: Requirements 5.7**
        ///
        /// Property 10: Last Page Boundary Correctness
        ///
        /// The last page should correctly handle cases where remaining items
        /// are less than page size.
        #[test]
        fn prop_pagination_last_page_boundary(
            file_count in 10usize..30usize,
            page_size in 3usize..8usize,
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create exactly file_count files
            for i in 0..file_count {
                let name = format!("file{:03}.txt", i);
                let entry = create_test_entry(i as u64 + 1, &name, 'C');
                index.insert(entry);
            }

            // Get full results to know total
            let full_query = SearchQuery {
                keyword: "file".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: 10000,
                offset: 0,
                ..Default::default()
            };
            let full_results = engine.search(&index, &full_query);
            let total = full_results.len();

            // Calculate last page offset
            let last_page_offset = (total / page_size) * page_size;
            let expected_last_page_size = total - last_page_offset;

            // Get last page
            let last_page_query = SearchQuery {
                keyword: "file".to_string(),
                match_mode: MatchMode::Exact,
                sort_by: SortField::Name,
                sort_order: SortOrder::Asc,
                limit: page_size,
                offset: last_page_offset,
                ..Default::default()
            };
            let last_page = engine.search(&index, &last_page_query);

            // Verify last page size
            prop_assert_eq!(
                last_page.len(),
                expected_last_page_size,
                "Last page size {} != expected {} (total={}, page_size={}, offset={})",
                last_page.len(),
                expected_last_page_size,
                total,
                page_size,
                last_page_offset
            );
        }

        // =====================================================================
        // Property 12: Match Highlighting Correctness
        // **Validates: Requirements 6.4**
        //
        // For any search result, the match_indices SHALL correctly identify
        // the positions in the filename where the query matches.
        // =====================================================================

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Match Indices Point to Matching Text (Exact Mode)
        ///
        /// For exact match mode, extracting text at match_indices positions
        /// SHALL produce substrings that contain the query (case-insensitive).
        #[test]
        fn prop_match_indices_contain_query_exact(
            base_name in "[a-zA-Z]{3,8}",
            extension in "[a-z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create a file that will definitely match
            let file_name = format!("{}.{}", base_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search for the base name (should match)
            let query = create_query(&base_name, MatchMode::Exact);
            let results = engine.search(&index, &query);

            // Should find the file
            prop_assume!(!results.is_empty());

            for result in &results {
                // Verify match_indices are non-empty for matching results
                prop_assert!(
                    !result.match_indices.is_empty(),
                    "Exact match result '{}' should have non-empty match_indices for query '{}'",
                    result.name,
                    base_name
                );

                // Verify each match index range contains the query
                for (start, end) in &result.match_indices {
                    prop_assert!(
                        *start <= *end,
                        "Match index start ({}) should be <= end ({})",
                        start,
                        end
                    );
                    prop_assert!(
                        *end <= result.name.len(),
                        "Match index end ({}) should be <= name length ({})",
                        end,
                        result.name.len()
                    );

                    // Extract the matched substring
                    let matched_text = &result.name[*start..*end];
                    
                    // For exact match, the matched text should equal the query (case-insensitive)
                    prop_assert!(
                        matched_text.to_lowercase() == base_name.to_lowercase(),
                        "Matched text '{}' at [{}, {}) should equal query '{}' (case-insensitive) in '{}'",
                        matched_text,
                        start,
                        end,
                        base_name,
                        result.name
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Match Indices Are Valid UTF-8 Boundaries
        ///
        /// For any search result, match_indices SHALL point to valid UTF-8
        /// character boundaries in the filename.
        #[test]
        fn prop_match_indices_valid_utf8_boundaries(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in arb_keyword(),
            match_mode in prop_oneof![
                Just(MatchMode::Exact),
                Just(MatchMode::Fuzzy),
                Just(MatchMode::Wildcard),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = create_query(&keyword, match_mode);
            let results = engine.search(&index, &query);

            for result in &results {
                for (start, end) in &result.match_indices {
                    // Verify start is a valid char boundary
                    prop_assert!(
                        result.name.is_char_boundary(*start),
                        "Match index start {} is not a valid UTF-8 boundary in '{}'",
                        start,
                        result.name
                    );

                    // Verify end is a valid char boundary
                    prop_assert!(
                        result.name.is_char_boundary(*end),
                        "Match index end {} is not a valid UTF-8 boundary in '{}'",
                        end,
                        result.name
                    );

                    // Verify we can safely slice the string
                    let slice_result = std::panic::catch_unwind(|| {
                        let _ = &result.name[*start..*end];
                    });
                    prop_assert!(
                        slice_result.is_ok(),
                        "Slicing '{}' at [{}, {}) should not panic",
                        result.name,
                        start,
                        end
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Match Indices Non-Overlapping
        ///
        /// For any search result, match_indices ranges SHALL NOT overlap.
        #[test]
        fn prop_match_indices_non_overlapping(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in arb_keyword(),
            match_mode in prop_oneof![
                Just(MatchMode::Exact),
                Just(MatchMode::Fuzzy),
                Just(MatchMode::Wildcard),
            ],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = create_query(&keyword, match_mode);
            let results = engine.search(&index, &query);

            for result in &results {
                // Sort indices by start position for overlap checking
                let mut sorted_indices = result.match_indices.clone();
                sorted_indices.sort_by_key(|(start, _)| *start);

                // Check for overlaps
                for i in 0..sorted_indices.len().saturating_sub(1) {
                    let (_, end1) = sorted_indices[i];
                    let (start2, _) = sorted_indices[i + 1];

                    prop_assert!(
                        end1 <= start2,
                        "Match indices overlap in '{}': [{}, {}) overlaps with [{}, {})",
                        result.name,
                        sorted_indices[i].0,
                        end1,
                        start2,
                        sorted_indices[i + 1].1
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Fuzzy Match Indices Cover Query Characters
        ///
        /// For fuzzy match mode, the total characters covered by match_indices
        /// SHALL be at least as many as the query length (since fuzzy matching
        /// finds all query characters in the target).
        #[test]
        fn prop_fuzzy_match_indices_cover_query(
            base_name in "[a-zA-Z]{5,12}",
            extension in "[a-z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            let file_name = format!("{}.{}", base_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Use first 3 characters as keyword (should fuzzy match)
            let keyword: String = base_name.chars().take(3).collect();
            prop_assume!(keyword.len() >= 2);

            let query = create_query(&keyword, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            prop_assume!(!results.is_empty());

            for result in &results {
                // Calculate total characters covered by match indices
                let total_covered: usize = result.match_indices
                    .iter()
                    .map(|(start, end)| end - start)
                    .sum();

                // For fuzzy match, we should cover at least as many chars as the keyword
                // (though they may be spread across multiple ranges)
                prop_assert!(
                    total_covered >= keyword.len(),
                    "Fuzzy match indices for '{}' should cover at least {} chars (query '{}'), but only covered {}",
                    result.name,
                    keyword.len(),
                    keyword,
                    total_covered
                );
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Wildcard Match Indices Point to Matched Region
        ///
        /// For wildcard match mode, the match_indices SHALL point to the
        /// region that matches the wildcard pattern.
        #[test]
        fn prop_wildcard_match_indices_valid(
            prefix in "[a-zA-Z]{2,5}",
            middle in "[a-zA-Z0-9]{1,5}",
            suffix in "[a-zA-Z]{2,5}",
            extension in "[a-z]{1,3}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file: prefix + middle + suffix.extension
            let file_name = format!("{}{}{}.{}", prefix, middle, suffix, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search with wildcard: prefix*suffix
            let pattern = format!("{}*{}", prefix, suffix);
            let query = create_query(&pattern, MatchMode::Wildcard);
            let results = engine.search(&index, &query);

            prop_assume!(!results.is_empty());

            for result in &results {
                prop_assert!(
                    !result.match_indices.is_empty(),
                    "Wildcard match result '{}' should have non-empty match_indices for pattern '{}'",
                    result.name,
                    pattern
                );

                // Verify match indices are valid
                for (start, end) in &result.match_indices {
                    prop_assert!(
                        *start <= *end && *end <= result.name.len(),
                        "Invalid match indices [{}, {}) for name '{}' (len={})",
                        start,
                        end,
                        result.name,
                        result.name.len()
                    );

                    // The matched region should contain both prefix and suffix
                    let matched_text = &result.name[*start..*end];
                    let matched_lower = matched_text.to_lowercase();
                    let prefix_lower = prefix.to_lowercase();
                    let suffix_lower = suffix.to_lowercase();

                    prop_assert!(
                        matched_lower.starts_with(&prefix_lower) && matched_lower.ends_with(&suffix_lower),
                        "Wildcard matched text '{}' should start with '{}' and end with '{}'",
                        matched_text,
                        prefix,
                        suffix
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Regex Match Indices Point to Matched Text
        ///
        /// For regex match mode, extracting text at match_indices positions
        /// SHALL produce substrings that match the regex pattern.
        #[test]
        fn prop_regex_match_indices_match_pattern(
            base_name in "[a-zA-Z]{3,8}",
            numbers in "[0-9]{2,4}",
            extension in "[a-z]{1,3}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file with numbers
            let file_name = format!("{}{}.{}", base_name, numbers, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search for digits with regex
            let pattern = r"\d+";
            let query = create_query(pattern, MatchMode::Regex);
            let results = engine.search(&index, &query);

            prop_assume!(!results.is_empty());

            let re = Regex::new(pattern).unwrap();

            for result in &results {
                prop_assert!(
                    !result.match_indices.is_empty(),
                    "Regex match result '{}' should have non-empty match_indices for pattern '{}'",
                    result.name,
                    pattern
                );

                // Verify each match index points to text that matches the regex
                for (start, end) in &result.match_indices {
                    let matched_text = &result.name[*start..*end];

                    prop_assert!(
                        re.is_match(matched_text),
                        "Regex matched text '{}' at [{}, {}) should match pattern '{}' in '{}'",
                        matched_text,
                        start,
                        end,
                        pattern,
                        result.name
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Chinese Filename Match Indices Valid
        ///
        /// For Chinese filenames matched via pinyin, match_indices SHALL
        /// point to valid character boundaries.
        #[test]
        fn prop_chinese_match_indices_valid(
            chinese_name in arb_chinese_string(2, 5),
            extension in prop_oneof![Just("txt".to_string()), Just("pdf".to_string())],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            let file_name = format!("{}.{}", chinese_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            let pinyin_abbr = entry.pinyin_abbr.clone();
            
            prop_assume!(!pinyin_abbr.is_empty());
            
            index.insert(entry);

            // Search using pinyin abbreviation
            let query = create_query(&pinyin_abbr, MatchMode::Fuzzy);
            let results = engine.search(&index, &query);

            prop_assume!(!results.is_empty());

            for result in &results {
                for (start, end) in &result.match_indices {
                    // Verify valid UTF-8 boundaries for Chinese text
                    prop_assert!(
                        result.name.is_char_boundary(*start),
                        "Match index start {} is not a valid UTF-8 boundary in Chinese filename '{}'",
                        start,
                        result.name
                    );
                    prop_assert!(
                        result.name.is_char_boundary(*end),
                        "Match index end {} is not a valid UTF-8 boundary in Chinese filename '{}'",
                        end,
                        result.name
                    );
                    prop_assert!(
                        *start <= *end && *end <= result.name.len(),
                        "Invalid match indices [{}, {}) for Chinese filename '{}' (len={})",
                        start,
                        end,
                        result.name,
                        result.name.len()
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Multiple Occurrences Have Multiple Match Indices
        ///
        /// When a keyword appears multiple times in a filename, match_indices
        /// SHALL contain entries for each occurrence.
        #[test]
        fn prop_multiple_occurrences_multiple_indices(
            keyword in "[a-zA-Z]{2,4}",
            separator in prop_oneof![Just("_"), Just("-"), Just("")],
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            // Create file with keyword appearing twice
            let file_name = format!("{}{}{}.txt", keyword, separator, keyword);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            let query = create_query(&keyword, MatchMode::Exact);
            let results = engine.search(&index, &query);

            prop_assume!(!results.is_empty());

            for result in &results {
                // Should have at least 2 match indices (one for each occurrence)
                prop_assert!(
                    result.match_indices.len() >= 2,
                    "File '{}' with keyword '{}' appearing twice should have >= 2 match indices, got {}",
                    result.name,
                    keyword,
                    result.match_indices.len()
                );

                // Verify each match index points to the keyword
                for (start, end) in &result.match_indices {
                    let matched_text = &result.name[*start..*end];
                    prop_assert!(
                        matched_text.to_lowercase() == keyword.to_lowercase(),
                        "Each match index should point to '{}', but got '{}' at [{}, {})",
                        keyword,
                        matched_text,
                        start,
                        end
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Match Indices Ordered by Position
        ///
        /// Match indices SHOULD be ordered by their start position.
        #[test]
        fn prop_match_indices_ordered(
            file_names in proptest::collection::vec(arb_file_name(), 5..15),
            keyword in arb_keyword(),
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            for (i, name) in file_names.iter().enumerate() {
                let entry = create_test_entry(i as u64 + 1, name, 'C');
                index.insert(entry);
            }

            let query = create_query(&keyword, MatchMode::Exact);
            let results = engine.search(&index, &query);

            for result in &results {
                // Check that indices are ordered by start position
                for i in 0..result.match_indices.len().saturating_sub(1) {
                    let (start1, _) = result.match_indices[i];
                    let (start2, _) = result.match_indices[i + 1];

                    prop_assert!(
                        start1 <= start2,
                        "Match indices should be ordered: {} should come before {} in '{}'",
                        start1,
                        start2,
                        result.name
                    );
                }
            }
        }

        /// **Validates: Requirements 6.4**
        ///
        /// Property 12: Empty Match Indices Only for Non-Matching Results
        ///
        /// A result with empty match_indices should only occur for pinyin matches
        /// where the original text doesn't directly contain the query.
        #[test]
        fn prop_empty_match_indices_only_for_pinyin(
            base_name in "[a-zA-Z]{4,10}",
            extension in "[a-z]{1,4}",
        ) {
            let engine = QueryEngine::new();
            let mut index = FileIndex::new();

            let file_name = format!("{}.{}", base_name, extension);
            let entry = create_test_entry(1, &file_name, 'C');
            index.insert(entry);

            // Search for exact substring
            let keyword: String = base_name.chars().take(3).collect();
            let query = create_query(&keyword, MatchMode::Exact);
            let results = engine.search(&index, &query);

            // If we find the file via exact match, it should have match indices
            for result in &results {
                if result.name.to_lowercase().contains(&keyword.to_lowercase()) {
                    prop_assert!(
                        !result.match_indices.is_empty(),
                        "Exact match result '{}' containing '{}' should have non-empty match_indices",
                        result.name,
                        keyword
                    );
                }
            }
        }
    }
}
