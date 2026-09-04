//! 内置文件索引器
//!
//! 使用 walkdir 遍历所有磁盘驱动器，构建内存文件名索引，
//! 提供类似 Everything 的快速文件名搜索功能。
//!
//! ## 特点
//!
//! - 启动时后台扫描所有 NTFS 驱动器
//! - 扫描过程中即可搜索（部分结果）
//! - 支持子串匹配和模糊匹配
//! - 使用 rayon 并行搜索，百万文件 <50ms
//! - 自动跳过系统目录和回收站

use std::io::{BufReader, BufWriter, Read as _, Write as _};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{Instant, UNIX_EPOCH};

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};
use walkdir::WalkDir;

/// 缓存文件版本号（变更结构时递增）
const CACHE_VERSION: u32 = 3;
/// 缓存文件名
const CACHE_FILENAME: &str = "file_index_cache.bin";
/// 查询关键词最大长度（字符）
const MAX_SEARCH_QUERY_CHARS: usize = 120;
/// 多关键词匹配时的最大关键词数量
const MAX_SEARCH_TOKENS: usize = 6;
/// 参与匹配的最小 token 长度
const MIN_SEARCH_TOKEN_CHARS: usize = 2;

// =============================================================================
// Types
// =============================================================================

/// 索引中的文件条目
///
/// 仅保存原始大小写的 name/path，搜索时用 ASCII 大小写无关比较。
/// 不保存 name_lower / path_lower：百万级条目下双份字符串副本会多占 200-400MB 内存，
/// 而中文字符大小写相同，ASCII 大小写折叠在比较时即时完成不会显著影响搜索性能。
#[derive(Clone, Serialize, Deserialize)]
struct FileEntry {
    /// 文件名（原始大小写）
    name: String,
    /// 完整路径字符串
    path: String,
    /// 文件大小（字节）
    size: u64,
    /// 修改时间（Unix 时间戳秒）
    modified_secs: i64,
    /// 是否为目录
    is_directory: bool,
}

/// 搜索命中结果
pub struct SearchHit {
    /// 文件名
    pub name: String,
    /// 完整路径
    pub path: String,
    /// 文件大小
    pub size: u64,
    /// 修改时间（Unix 时间戳秒）
    pub modified_secs: i64,
    /// 是否为目录
    pub is_directory: bool,
    /// 匹配得分（越高越好）
    pub score: i64,
    /// 匹配位置（用于高亮）
    pub match_indices: Vec<(usize, usize)>,
}

/// 索引器状态
#[derive(Debug, Clone)]
pub enum IndexerStatus {
    /// 空闲，未开始扫描
    Idle,
    /// 正在扫描
    Scanning {
        /// 已扫描文件数
        scanned_files: u64,
    },
    /// 扫描完成，索引就绪
    Ready {
        /// 索引中的文件总数
        total_files: u64,
        /// 扫描耗时（毫秒）
        scan_time_ms: u64,
    },
    /// 扫描出错
    Error(String),
}

/// 搜索结果（含元数据）
pub struct SearchResults {
    /// 命中列表
    pub hits: Vec<SearchHit>,
    /// 匹配总数（分页前）
    pub total_count: u64,
    /// 搜索耗时（毫秒）
    pub search_time_ms: u64,
}

// =============================================================================
// 需要跳过的目录
// =============================================================================

/// 需要跳过的目录名（小写）
const SKIP_DIRS: &[&str] = &[
    "$recycle.bin",
    "system volume information",
    "$windows.~bt",
    "$windows.~ws",
    "windows",
    "windows.old",
    "recovery",
    "perflogs",
    "config.msi",
    ".git",
    "node_modules",
    "__pycache__",
    ".cache",
    ".tmp",
    "thumbs.db",
];

// =============================================================================
// FileIndexer
// =============================================================================

/// 文件索引器
///
/// 在后台扫描所有磁盘，构建文件名索引，支持快速搜索。
pub struct FileIndexer {
    /// 文件条目列表（使用 RwLock 允许读写并发）
    entries: Arc<RwLock<Vec<FileEntry>>>,
    /// 索引器状态
    status: Arc<RwLock<IndexerStatus>>,
    /// 已扫描文件计数（原子操作，扫描时更新）
    scanned_count: Arc<AtomicU64>,
    /// 是否正在扫描
    is_scanning: Arc<AtomicBool>,
    /// 扫描完成时间戳（毫秒）
    scan_time_ms: Arc<AtomicU64>,
}

impl FileIndexer {
    /// 创建新的文件索引器
    pub fn new() -> Self {
        Self {
            entries: Arc::new(RwLock::new(Vec::new())),
            status: Arc::new(RwLock::new(IndexerStatus::Idle)),
            scanned_count: Arc::new(AtomicU64::new(0)),
            is_scanning: Arc::new(AtomicBool::new(false)),
            scan_time_ms: Arc::new(AtomicU64::new(0)),
        }
    }

    /// 获取缓存文件路径
    fn cache_path() -> Option<PathBuf> {
        dirs::data_local_dir().map(|d| d.join("hugescreenshot").join(CACHE_FILENAME))
    }

    /// 从磁盘加载缓存的索引
    pub fn load_cache(&self) -> bool {
        let path = match Self::cache_path() {
            Some(p) => p,
            None => return false,
        };

        if !path.exists() {
            info!("文件索引器: 无缓存文件");
            return false;
        }

        info!("文件索引器: 加载缓存 {:?}...", path);
        let start = Instant::now();

        let file = match std::fs::File::open(&path) {
            Ok(f) => f,
            Err(e) => {
                warn!("文件索引器: 打开缓存文件失败: {}", e);
                return false;
            }
        };

        let mut reader = BufReader::new(file);

        // 读取版本号
        let mut version_buf = [0u8; 4];
        if reader.read_exact(&mut version_buf).is_err() {
            warn!("文件索引器: 读取缓存版本失败");
            return false;
        }
        let version = u32::from_le_bytes(version_buf);
        if version != CACHE_VERSION {
            warn!("文件索引器: 缓存版本不匹配 (期望 {}, 实际 {})", CACHE_VERSION, version);
            return false;
        }

        // 读取条目数量
        let mut count_buf = [0u8; 8];
        if reader.read_exact(&mut count_buf).is_err() {
            warn!("文件索引器: 读取缓存条目数失败");
            return false;
        }
        let count = u64::from_le_bytes(count_buf) as usize;

        // 读取数据
        let mut data = Vec::new();
        if reader.read_to_end(&mut data).is_err() {
            warn!("文件索引器: 读取缓存数据失败");
            return false;
        }

        let cached_entries: Vec<FileEntry> = match bincode::deserialize(&data) {
            Ok(entries) => entries,
            Err(e) => {
                warn!("文件索引器: 反序列化缓存失败: {}", e);
                return false;
            }
        };

        let loaded_count = cached_entries.len();
        if loaded_count != count {
            warn!("文件索引器: 缓存条目数不匹配 (期望 {}, 实际 {})", count, loaded_count);
        }

        if let Ok(mut e) = self.entries.write() {
            *e = cached_entries;
        }

        self.scanned_count.store(loaded_count as u64, Ordering::Relaxed);
        if let Ok(mut s) = self.status.write() {
            *s = IndexerStatus::Ready {
                total_files: loaded_count as u64,
                scan_time_ms: start.elapsed().as_millis() as u64,
            };
        }

        info!(
            "文件索引器: 缓存加载完成！{} 个条目，耗时 {:.1}s",
            loaded_count,
            start.elapsed().as_secs_f64()
        );
        true
    }

    /// 将索引保存到磁盘缓存（委托给独立函数）
    #[allow(dead_code)]
    pub fn save_cache(&self) {
        save_cache_to_disk(&self.entries);
    }

    /// 获取当前状态
    pub fn get_status(&self) -> IndexerStatus {
        self.status
            .read()
            .unwrap_or_else(|e| {
                warn!("文件索引器: status RwLock 已中毒，恢复内部数据");
                e.into_inner()
            })
            .clone()
    }

    /// 获取已索引文件数
    pub fn indexed_count(&self) -> u64 {
        self.entries.read().map(|e| e.len() as u64).unwrap_or(0)
    }

    /// 是否正在扫描
    pub fn is_scanning(&self) -> bool {
        self.is_scanning.load(Ordering::Relaxed)
    }

    /// 启动后台扫描（非阻塞）
    ///
    /// 在新的 tokio 任务中扫描所有磁盘驱动器。
    /// 如果已经在扫描则跳过。
    pub fn start_background_scan(&self) {
        if self.is_scanning.swap(true, Ordering::SeqCst) {
            info!("文件索引器: 已有扫描任务在运行，跳过");
            return;
        }

        let entries = self.entries.clone();
        let status = self.status.clone();
        let scanned_count = self.scanned_count.clone();
        let is_scanning = self.is_scanning.clone();
        let scan_time_ms = self.scan_time_ms.clone();

        // 重置计数器
        scanned_count.store(0, Ordering::Relaxed);

        // 更新状态为扫描中
        if let Ok(mut s) = status.write() {
            *s = IndexerStatus::Scanning { scanned_files: 0 };
        } else {
            warn!("文件索引器: status RwLock 已中毒，跳过状态更新");
        }

        // 在独立线程中执行扫描（因为 walkdir 是同步阻塞的）
        // 策略：在独立的 Vec 中构建新索引，扫描完成后一次性替换旧数据。
        // 扫描期间旧缓存保持可搜索，避免 D 盘文件在 C 盘扫描期间不可用。
        std::thread::spawn(move || {
            info!("文件索引器: 开始全盘扫描（旧缓存保持可用）...");
            let start = Instant::now();

            let drives = get_all_drives();
            info!("文件索引器: 发现 {} 个驱动器: {:?}", drives.len(), drives);

            // 在独立的 Vec 中构建新索引
            let mut new_entries: Vec<FileEntry> = Vec::with_capacity(1_500_000);
            let mut total_scanned: u64 = 0;
            let mut total_errors: u64 = 0;

            for drive in &drives {
                info!("文件索引器: 扫描驱动器 {}...", drive.display());
                let drive_start = Instant::now();
                let mut drive_count: u64 = 0;

                let walker =
                    WalkDir::new(drive).follow_links(false).min_depth(1).into_iter().filter_entry(
                        |e| {
                            // 跳过需要排除的目录（不进入其子目录）
                            if e.file_type().is_dir() {
                                let name_lower = e.file_name().to_string_lossy().to_lowercase();
                                !SKIP_DIRS.contains(&name_lower.as_str())
                            } else {
                                true
                            }
                        },
                    );

                for entry_result in walker {
                    match entry_result {
                        Ok(entry) => {
                            let name = entry.file_name().to_string_lossy().to_string();
                            let path = entry.path().to_string_lossy().to_string();
                            let is_dir = entry.file_type().is_dir();

                            // 获取文件元数据
                            let (size, modified_secs) = match entry.metadata() {
                                Ok(meta) => {
                                    let size = if is_dir { 0 } else { meta.len() };
                                    let modified = meta
                                        .modified()
                                        .unwrap_or(UNIX_EPOCH)
                                        .duration_since(UNIX_EPOCH)
                                        .unwrap_or_default()
                                        .as_secs()
                                        as i64;
                                    (size, modified)
                                }
                                Err(_) => (0, 0),
                            };

                            new_entries.push(FileEntry {
                                name,
                                path,
                                size,
                                modified_secs,
                                is_directory: is_dir,
                            });

                            drive_count += 1;
                            total_scanned += 1;

                            // 每 5000 个文件更新扫描状态（不修改共享索引）
                            if total_scanned.is_multiple_of(5_000) {
                                scanned_count.store(total_scanned, Ordering::Relaxed);
                                if let Ok(mut s) = status.write() {
                                    *s = IndexerStatus::Scanning { scanned_files: total_scanned };
                                }
                            }
                        }
                        Err(_e) => {
                            total_errors += 1;
                            // 权限错误等是正常的，不需要逐个打印
                        }
                    }
                }

                scanned_count.store(total_scanned, Ordering::Relaxed);
                if let Ok(mut s) = status.write() {
                    *s = IndexerStatus::Scanning { scanned_files: total_scanned };
                }

                info!(
                    "文件索引器: 驱动器 {} 扫描完成，{} 个文件/目录，耗时 {:.1}s",
                    drive.display(),
                    drive_count,
                    drive_start.elapsed().as_secs_f64()
                );
            }

            // 全盘扫描完成，一次性替换旧索引
            let total = new_entries.len() as u64;
            if let Ok(mut e) = entries.write() {
                *e = new_entries;
            }

            let elapsed = start.elapsed();
            let elapsed_ms = elapsed.as_millis() as u64;

            info!(
                "文件索引器: 全盘扫描完成！共 {} 个文件/目录，{} 个错误，耗时 {:.1}s",
                total,
                total_errors,
                elapsed.as_secs_f64()
            );
            scan_time_ms.store(elapsed_ms, Ordering::Relaxed);
            scanned_count.store(total, Ordering::Relaxed);
            if let Ok(mut s) = status.write() {
                *s = IndexerStatus::Ready { total_files: total, scan_time_ms: elapsed_ms };
            }
            is_scanning.store(false, Ordering::SeqCst);

            info!("文件索引器: 索引就绪，共 {} 个条目", total);

            // 扫描完成后保存缓存到磁盘
            save_cache_to_disk(&entries);
        });
    }

    /// 搜索文件
    ///
    /// 在索引中查找匹配关键词的文件。
    /// 支持子串匹配和模糊匹配。
    ///
    /// # Arguments
    ///
    /// * `keyword` - 搜索关键词
    /// * `match_mode` - 匹配模式: "exact", "fuzzy", "wildcard", "regex"
    /// * `limit` - 最大返回结果数
    /// * `offset` - 分页偏移
    ///
    /// # Returns
    ///
    /// 搜索结果（含匹配高亮信息）
    pub fn search(
        &self,
        keyword: &str,
        match_mode: &str,
        limit: usize,
        offset: usize,
    ) -> SearchResults {
        let start = Instant::now();
        let keyword_normalized = keyword.split_whitespace().collect::<Vec<_>>().join(" ");

        if keyword_normalized.is_empty() {
            return SearchResults { hits: Vec::new(), total_count: 0, search_time_ms: 0 };
        }

        if keyword_normalized.chars().count() > MAX_SEARCH_QUERY_CHARS {
            debug!(
                "文件搜索跳过超长关键词: chars={}, keyword='{}'",
                keyword_normalized.chars().count(),
                keyword_normalized
            );
            return SearchResults { hits: Vec::new(), total_count: 0, search_time_ms: 0 };
        }

        let keyword_lower = keyword_normalized.to_lowercase();
        let keywords: Vec<&str> = keyword_lower
            .split_whitespace()
            .filter(|token| token.chars().count() >= MIN_SEARCH_TOKEN_CHARS)
            .take(MAX_SEARCH_TOKENS)
            .collect();

        if keywords.is_empty() {
            return SearchResults { hits: Vec::new(), total_count: 0, search_time_ms: 0 };
        }
        let multi_keyword = keywords.len() > 1;
        let primary_keyword = keywords[0];

        let entries = match self.entries.read() {
            Ok(e) => e,
            Err(_) => {
                return SearchResults { hits: Vec::new(), total_count: 0, search_time_ms: 0 };
            }
        };

        // 使用 rayon 并行搜索
        let mut matches: Vec<SearchHit> = entries
            .par_iter()
            .filter_map(|entry| {
                if multi_keyword {
                    // 多关键词：所有关键词都必须匹配
                    match_multi_keywords(entry, &keywords)
                } else {
                    match match_mode {
                        "exact" => match_exact(entry, primary_keyword),
                        "regex" => match_substring(entry, primary_keyword), // 简化处理
                        "wildcard" => match_substring(entry, primary_keyword), // 简化处理
                        _ => match_fuzzy(entry, primary_keyword),           // 默认 fuzzy
                    }
                }
            })
            .collect();

        let total_count = matches.len() as u64;

        // 按分数排序（降序）
        matches.par_sort_unstable_by(|a, b| b.score.cmp(&a.score));

        // 分页
        let hits: Vec<SearchHit> = matches.into_iter().skip(offset).take(limit).collect();

        let search_time_ms = start.elapsed().as_millis() as u64;

        debug!(
            "文件搜索完成: keyword='{}', mode='{}', 命中={}, 返回={}, 耗时={}ms",
            keyword_normalized,
            match_mode,
            total_count,
            hits.len(),
            search_time_ms
        );

        SearchResults { hits, total_count, search_time_ms }
    }
}

impl Default for FileIndexer {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// 匹配算法
// =============================================================================

/// ASCII 大小写无关的字节相等判断
#[inline]
fn ascii_ci_eq(a: u8, b: u8) -> bool {
    a.eq_ignore_ascii_case(&b)
}

/// ASCII 大小写无关的相等判断（仅在已知两侧都不含多字节字符时用作快速路径）
#[inline]
fn ascii_ci_str_eq(haystack: &str, needle: &str) -> bool {
    if haystack.len() != needle.len() {
        return false;
    }
    haystack.bytes().zip(needle.bytes()).all(|(a, b)| ascii_ci_eq(a, b))
}

/// ASCII 大小写无关的子串查找
///
/// 关键词调用方已确保为小写（见 [`FileIndexer::search`]），
/// 因此这里只需对 haystack 做大小写折叠。
/// 中文等多字节字符大小写一致，按字节比较仍然正确。
fn ascii_ci_find(haystack: &str, needle_lower: &str) -> Option<usize> {
    let h = haystack.as_bytes();
    let n = needle_lower.as_bytes();
    if n.is_empty() || n.len() > h.len() {
        return None;
    }
    let last = h.len() - n.len();
    let first = n[0];
    let mut i = 0;
    while i <= last {
        if ascii_ci_eq(h[i], first) {
            // 快速校验剩余字节
            let mut matched = true;
            for k in 1..n.len() {
                if !ascii_ci_eq(h[i + k], n[k]) {
                    matched = false;
                    break;
                }
            }
            if matched {
                return Some(i);
            }
        }
        i += 1;
    }
    None
}

/// 精确匹配（文件名完全等于关键词）
fn match_exact(entry: &FileEntry, keyword_lower: &str) -> Option<SearchHit> {
    if ascii_ci_str_eq(&entry.name, keyword_lower) {
        Some(SearchHit {
            name: entry.name.clone(),
            path: entry.path.clone(),
            size: entry.size,
            modified_secs: entry.modified_secs,
            is_directory: entry.is_directory,
            score: 10000,
            match_indices: vec![(0, entry.name.len())],
        })
    } else {
        None
    }
}

/// 子串匹配（文件名或路径包含关键词）
fn match_substring(entry: &FileEntry, keyword_lower: &str) -> Option<SearchHit> {
    // 优先匹配文件名
    if let Some(pos) = ascii_ci_find(&entry.name, keyword_lower) {
        let score = compute_substring_score(entry, keyword_lower, pos);
        let match_indices = vec![(pos, pos + keyword_lower.len())];
        Some(SearchHit {
            name: entry.name.clone(),
            path: entry.path.clone(),
            size: entry.size,
            modified_secs: entry.modified_secs,
            is_directory: entry.is_directory,
            score,
            match_indices,
        })
    } else {
        // 回退到路径匹配（分数较低）
        if ascii_ci_find(&entry.path, keyword_lower).is_some() {
            Some(SearchHit {
                name: entry.name.clone(),
                path: entry.path.clone(),
                size: entry.size,
                modified_secs: entry.modified_secs,
                is_directory: entry.is_directory,
                score: 200, // 路径匹配得分较低
                match_indices: vec![],
            })
        } else {
            None
        }
    }
}

/// 模糊匹配（包含子串匹配 + 路径匹配 + 分散字符匹配）
fn match_fuzzy(entry: &FileEntry, keyword_lower: &str) -> Option<SearchHit> {
    // 优先尝试文件名子串匹配（最高分）
    if let Some(pos) = ascii_ci_find(&entry.name, keyword_lower) {
        let score = compute_substring_score(entry, keyword_lower, pos);
        let match_indices = vec![(pos, pos + keyword_lower.len())];
        return Some(SearchHit {
            name: entry.name.clone(),
            path: entry.path.clone(),
            size: entry.size,
            modified_secs: entry.modified_secs,
            is_directory: entry.is_directory,
            score,
            match_indices,
        });
    }

    // 尝试分散字符匹配（fuzzy）
    if let Some((score, indices)) = fuzzy_match_chars(&entry.name, keyword_lower) {
        return Some(SearchHit {
            name: entry.name.clone(),
            path: entry.path.clone(),
            size: entry.size,
            modified_secs: entry.modified_secs,
            is_directory: entry.is_directory,
            score,
            match_indices: indices,
        });
    }

    // 最后尝试路径匹配（分数较低，但能找到路径中含关键词的文件）
    if ascii_ci_find(&entry.path, keyword_lower).is_some() {
        return Some(SearchHit {
            name: entry.name.clone(),
            path: entry.path.clone(),
            size: entry.size,
            modified_secs: entry.modified_secs,
            is_directory: entry.is_directory,
            score: 200,
            match_indices: vec![],
        });
    }

    None
}

/// 多关键词匹配（所有关键词都必须在文件名中出现）
fn match_multi_keywords(entry: &FileEntry, keywords: &[&str]) -> Option<SearchHit> {
    let mut total_score: i64 = 0;
    let mut all_indices: Vec<(usize, usize)> = Vec::new();

    for keyword in keywords {
        if let Some(pos) = ascii_ci_find(&entry.name, keyword) {
            total_score += compute_substring_score(entry, keyword, pos);
            all_indices.push((pos, pos + keyword.len()));
        } else {
            // 如果某个关键词不匹配，返回 None
            return None;
        }
    }

    // 多关键词全部匹配，额外加分
    total_score += 500;

    Some(SearchHit {
        name: entry.name.clone(),
        path: entry.path.clone(),
        size: entry.size,
        modified_secs: entry.modified_secs,
        is_directory: entry.is_directory,
        score: total_score,
        match_indices: all_indices,
    })
}

/// 计算子串匹配的分数
fn compute_substring_score(entry: &FileEntry, keyword_lower: &str, pos: usize) -> i64 {
    let name_len = entry.name.len();
    let keyword_len = keyword_lower.len();
    let mut score: i64 = 1000;

    // 完全匹配（文件名 == 关键词）：最高分
    if name_len == keyword_len {
        score += 5000;
    }

    // 从文件名开头匹配：高分
    if pos == 0 {
        score += 3000;
    }

    // 关键词长度占文件名比例越大，分数越高
    let ratio = keyword_len as f64 / name_len as f64;
    score += (ratio * 2000.0) as i64;

    // 在分隔符（点、下划线、横线）后开始匹配：额外加分
    if pos > 0 {
        let prev_char = entry.name.as_bytes()[pos - 1];
        if prev_char == b'.' || prev_char == b'_' || prev_char == b'-' || prev_char == b' ' {
            score += 1500;
        }
    }

    // 文件名较短的优先（更精确的匹配）
    if name_len < 20 {
        score += 500;
    } else if name_len < 50 {
        score += 200;
    }

    score
}

/// 分散字符模糊匹配
///
/// 关键词中的字符按顺序出现在文件名中，但不需要连续。
/// 例如 "abc" 匹配 "a_big_cat"
///
/// 关键词调用方传入小写形式，name 按 ASCII 大小写无关方式匹配。
///
/// 返回 (score, match_indices) 或 None
fn fuzzy_match_chars(name: &str, keyword_lower: &str) -> Option<(i64, Vec<(usize, usize)>)> {
    let name_bytes = name.as_bytes();
    let keyword_bytes = keyword_lower.as_bytes();

    if keyword_bytes.is_empty() || keyword_bytes.len() > name_bytes.len() {
        return None;
    }

    let mut indices: Vec<(usize, usize)> = Vec::with_capacity(keyword_bytes.len());
    let mut name_idx: usize = 0;
    let mut score: i64 = 100;
    let mut prev_match_idx: Option<usize> = None;
    let mut consecutive_count: usize = 0;

    for &kc in keyword_bytes {
        let mut found = false;
        while name_idx < name_bytes.len() {
            if ascii_ci_eq(name_bytes[name_idx], kc) {
                // 连续匹配加分
                if let Some(prev) = prev_match_idx {
                    if name_idx == prev + 1 {
                        consecutive_count += 1;
                        score += 50 * consecutive_count as i64;
                    } else {
                        consecutive_count = 0;
                        // 间隔越小越好
                        let gap = name_idx - prev - 1;
                        score -= (gap as i64) * 5;
                    }
                }

                // 在词首匹配（大写、分隔符后）加分
                if name_idx == 0 {
                    score += 100;
                } else {
                    let prev_char = name_bytes[name_idx - 1];
                    if prev_char == b'_'
                        || prev_char == b'-'
                        || prev_char == b'.'
                        || prev_char == b' '
                    {
                        score += 80;
                    }
                }

                indices.push((name_idx, name_idx + 1));
                prev_match_idx = Some(name_idx);
                name_idx += 1;
                found = true;
                break;
            }
            name_idx += 1;
        }

        if !found {
            return None; // 关键词字符未全部匹配
        }
    }

    // 匹配字符占文件名比例加分
    let coverage = keyword_bytes.len() as f64 / name_bytes.len() as f64;
    score += (coverage * 200.0) as i64;

    // 分数至少为正
    if score <= 0 {
        score = 1;
    }

    Some((score, indices))
}

// =============================================================================
// 缓存保存（独立函数，用于扫描线程内调用）
// =============================================================================

/// 将索引数据保存到磁盘缓存
fn save_cache_to_disk(entries: &Arc<RwLock<Vec<FileEntry>>>) {
    let path = match dirs::data_local_dir().map(|d| d.join("hugescreenshot").join(CACHE_FILENAME)) {
        Some(p) => p,
        None => return,
    };

    if let Some(parent) = path.parent() {
        if let Err(e) = std::fs::create_dir_all(parent) {
            warn!("文件索引器: 创建缓存目录失败: {}", e);
            return;
        }
    }

    let entries_data = match entries.read() {
        Ok(e) => e.clone(),
        Err(_) => return,
    };

    if entries_data.is_empty() {
        return;
    }

    info!("文件索引器: 保存缓存到 {:?} ({} 个条目)...", path, entries_data.len());
    let start = Instant::now();

    let data = match bincode::serialize(&entries_data) {
        Ok(d) => d,
        Err(e) => {
            warn!("文件索引器: 序列化缓存失败: {}", e);
            return;
        }
    };

    let file = match std::fs::File::create(&path) {
        Ok(f) => f,
        Err(e) => {
            warn!("文件索引器: 创建缓存文件失败: {}", e);
            return;
        }
    };

    let mut writer = BufWriter::new(file);
    let write_result = (|| -> std::io::Result<()> {
        writer.write_all(&CACHE_VERSION.to_le_bytes())?;
        writer.write_all(&(entries_data.len() as u64).to_le_bytes())?;
        writer.write_all(&data)?;
        writer.flush()
    })();
    if let Err(e) = write_result {
        warn!("文件索引器: 写入缓存文件失败: {}", e);
        return;
    }

    info!(
        "文件索引器: 缓存保存完成，{:.1}MB，耗时 {:.1}s",
        data.len() as f64 / 1024.0 / 1024.0,
        start.elapsed().as_secs_f64()
    );
}

// =============================================================================
// 驱动器枚举
// =============================================================================

/// 获取所有可用的磁盘驱动器
#[cfg(windows)]
fn get_all_drives() -> Vec<PathBuf> {
    let mut drives = Vec::new();

    // 使用 Windows API 获取所有逻辑驱动器
    unsafe {
        let bitmask = windows::Win32::Storage::FileSystem::GetLogicalDrives();
        for i in 0..26u32 {
            if bitmask & (1 << i) != 0 {
                let letter = (b'A' + i as u8) as char;
                let drive_path = format!("{}:\\", letter);
                let drive = PathBuf::from(&drive_path);

                // 检查是否可访问（跳过光驱等不可用驱动器）
                if drive.exists() {
                    // 获取驱动器类型
                    let drive_type = windows::Win32::Storage::FileSystem::GetDriveTypeW(
                        &windows::core::HSTRING::from(&drive_path),
                    );
                    // 只扫描固定磁盘和可移动磁盘
                    // DRIVE_FIXED = 3, DRIVE_REMOVABLE = 2
                    if drive_type == 3 || drive_type == 2 {
                        drives.push(drive);
                    } else {
                        debug!("文件索引器: 跳过驱动器 {} (类型: {})", drive_path, drive_type);
                    }
                }
            }
        }
    }

    drives
}

#[cfg(not(windows))]
fn get_all_drives() -> Vec<PathBuf> {
    // 非 Windows 系统，扫描根目录
    vec![PathBuf::from("/")]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fuzzy_match_chars() {
        // 基础匹配
        let result = fuzzy_match_chars("readme.md", "rm");
        assert!(result.is_some());

        // 连续匹配
        let result = fuzzy_match_chars("readme.md", "read");
        assert!(result.is_some());
        let (score, _) = result.unwrap();
        assert!(score > 100); // 连续匹配应该有高分

        // 不匹配
        let result = fuzzy_match_chars("readme.md", "xyz");
        assert!(result.is_none());

        // 空关键词
        let result = fuzzy_match_chars("readme.md", "");
        assert!(result.is_none());
    }

    #[test]
    fn test_match_substring() {
        let entry = FileEntry {
            name: "README.md".to_string(),
            path: "C:\\project\\README.md".to_string(),
            size: 1024,
            modified_secs: 0,
            is_directory: false,
        };

        // 子串匹配
        let result = match_substring(&entry, "readme");
        assert!(result.is_some());
        let hit = result.unwrap();
        assert_eq!(hit.match_indices, vec![(0, 6)]);
        assert!(hit.score > 3000); // 开头匹配应有高分

        // 不匹配
        let result = match_substring(&entry, "xyz");
        assert!(result.is_none());
    }

    #[test]
    fn test_match_exact() {
        let entry = FileEntry {
            name: "test.txt".to_string(),
            path: "C:\\test.txt".to_string(),
            size: 100,
            modified_secs: 0,
            is_directory: false,
        };

        let result = match_exact(&entry, "test.txt");
        assert!(result.is_some());
        assert_eq!(result.unwrap().score, 10000);

        let result = match_exact(&entry, "test");
        assert!(result.is_none());
    }

    #[test]
    fn test_multi_keywords() {
        let entry = FileEntry {
            name: "my_project_readme.md".to_string(),
            path: "C:\\my_project_readme.md".to_string(),
            size: 100,
            modified_secs: 0,
            is_directory: false,
        };

        let keywords = vec!["project", "readme"];
        let result = match_multi_keywords(&entry, &keywords);
        assert!(result.is_some());

        let keywords = vec!["project", "xyz"];
        let result = match_multi_keywords(&entry, &keywords);
        assert!(result.is_none());
    }
}
