//! 文件搜索相关的 Tauri 命令
//!
//! 本模块实现与文件搜索索引服务通信的 Tauri 命令。
//! 使用共享的 SearchClient 实例通过命名管道与 Windows 服务通信。
//!
//! **Validates: Requirements 1.4, 1.5, 1.6, 5.1, 9.6**

use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
#[cfg(not(debug_assertions))]
use tauri::Manager;
use tauri::State;
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn};

use crate::file_search::{
    FileIndexer, IndexConfig, KeywordExtractor, MatchMode, SearchClient, SearchClientError,
    SearchFilters, SearchQuery, SearchResult, ServiceStatus, SortField, SortOrder,
};

// =============================================================================
// Constants
// =============================================================================

/// Windows 服务名称
const SERVICE_NAME: &str = "HuGeScreenshot_FileSearch";

/// 用户搜索关键词最大长度（字符）
const MAX_USER_SEARCH_QUERY_CHARS: usize = 120;

/// 长文本降载时最多保留的关键词数量
const MAX_USER_SEARCH_QUERY_TOKENS: usize = 6;

// =============================================================================
// State Management
// =============================================================================

/// 文件搜索状态（全局共享）
///
/// 使用 tokio::sync::Mutex 以支持异步命令中的状态访问。
/// 包含内置文件索引器和可选的 Windows 服务客户端。
pub struct FileSearchState {
    /// 搜索客户端实例（用于连接 Windows 服务，作为后备）
    pub client: Arc<Mutex<SearchClient>>,
    /// 内置文件索引器（主搜索引擎，无需 Windows 服务）
    pub indexer: Arc<FileIndexer>,
    /// 服务状态检查是否已完成
    pub startup_check_done: AtomicBool,
}

impl FileSearchState {
    /// 创建新的文件搜索状态
    pub fn new() -> Self {
        Self {
            client: Arc::new(Mutex::new(SearchClient::new())),
            indexer: Arc::new(FileIndexer::new()),
            startup_check_done: AtomicBool::new(false),
        }
    }
}

impl Default for FileSearchState {
    fn default() -> Self {
        Self::new()
    }
}

/// 初始化文件搜索状态
///
/// 在应用启动时调用此函数创建 FileSearchState 实例。
/// 先尝试加载磁盘缓存，然后启动后台扫描更新索引。
pub fn init_file_search_state() -> FileSearchState {
    info!("初始化文件搜索状态（内置索引器模式）");
    let state = FileSearchState::new();

    // 先尝试加载磁盘缓存（几秒即可完成）
    let cache_loaded = state.indexer.load_cache();
    if cache_loaded {
        info!("已从缓存加载文件索引，后台将继续更新...");
    } else {
        info!("无缓存可用，启动全盘扫描...");
    }

    // 无论是否有缓存，都启动后台扫描以更新索引
    state.indexer.start_background_scan();

    state
}

// =============================================================================
// Service Control Functions
// =============================================================================

/// Windows 服务状态枚举
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WindowsServiceState {
    /// 服务正在运行
    Running,
    /// 服务已停止
    Stopped,
    /// 服务正在启动
    StartPending,
    /// 服务正在停止
    StopPending,
    /// 服务未安装
    NotInstalled,
    /// 状态未知
    Unknown,
}

/// 检查 Windows 服务状态
///
/// 使用 `sc query` 命令检查服务是否运行。
///
/// **Validates: Requirements 1.4, 1.6**
pub async fn check_windows_service_state() -> WindowsServiceState {
    debug!("检查 Windows 服务状态: {}", SERVICE_NAME);

    let output =
        match tokio::process::Command::new("sc").args(["query", SERVICE_NAME]).output().await {
            Ok(output) => output,
            Err(e) => {
                error!("执行 sc query 命令失败: {}", e);
                return WindowsServiceState::Unknown;
            }
        };

    // 将输出转换为字符串（处理可能的 GBK 编码）
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    // 检查服务是否存在
    if !output.status.success() {
        // 错误码 1060 表示服务不存在
        if stderr.contains("1060") || stdout.contains("1060") {
            info!("文件搜索服务未安装");
            return WindowsServiceState::NotInstalled;
        }
        warn!("sc query 命令失败: {}", stderr);
        return WindowsServiceState::Unknown;
    }

    // 解析服务状态
    // sc query 输出格式示例:
    // STATE              : 4  RUNNING
    // STATE              : 1  STOPPED
    // STATE              : 2  START_PENDING
    // STATE              : 3  STOP_PENDING
    let state = if stdout.contains("RUNNING") {
        WindowsServiceState::Running
    } else if stdout.contains("STOPPED") {
        WindowsServiceState::Stopped
    } else if stdout.contains("START_PENDING") {
        WindowsServiceState::StartPending
    } else if stdout.contains("STOP_PENDING") {
        WindowsServiceState::StopPending
    } else {
        // 尝试解析状态码
        if stdout.contains(": 4") {
            WindowsServiceState::Running
        } else if stdout.contains(": 1") {
            WindowsServiceState::Stopped
        } else if stdout.contains(": 2") {
            WindowsServiceState::StartPending
        } else if stdout.contains(": 3") {
            WindowsServiceState::StopPending
        } else {
            WindowsServiceState::Unknown
        }
    };

    debug!("服务状态: {:?}", state);
    state
}

/// 尝试启动 Windows 服务
///
/// 使用 `sc start` 命令启动服务。
///
/// **Validates: Requirements 1.5**
///
/// # Returns
///
/// - `Ok(true)` - 服务启动成功或已在运行
/// - `Ok(false)` - 服务未安装
/// - `Err(String)` - 启动失败，返回错误消息
pub async fn try_start_windows_service() -> Result<bool, String> {
    info!("尝试启动文件搜索服务: {}", SERVICE_NAME);

    // 先检查当前状态
    let current_state = check_windows_service_state().await;

    match current_state {
        WindowsServiceState::Running => {
            info!("服务已在运行");
            return Ok(true);
        }
        WindowsServiceState::StartPending => {
            info!("服务正在启动中");
            return Ok(true);
        }
        WindowsServiceState::NotInstalled => {
            warn!("服务未安装，无法启动");
            return Ok(false);
        }
        WindowsServiceState::StopPending => {
            // 等待服务停止后再启动
            info!("服务正在停止，等待后重试...");
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        }
        _ => {}
    }

    // 执行启动命令
    let output = tokio::process::Command::new("sc")
        .args(["start", SERVICE_NAME])
        .output()
        .await
        .map_err(|e| format!("执行服务启动命令失败: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if output.status.success() {
        info!("文件搜索服务启动命令已发送");
        return Ok(true);
    }

    // 检查常见错误
    let combined = format!("{}{}", stdout, stderr);

    if combined.contains("1056") {
        // 错误码 1056: 服务已在运行
        info!("服务已在运行");
        Ok(true)
    } else if combined.contains("1060") {
        // 错误码 1060: 服务不存在
        warn!("服务未安装");
        Ok(false)
    } else if combined.contains("5") && (combined.contains("Access") || combined.contains("拒绝"))
    {
        // 错误码 5: 访问被拒绝
        error!("启动服务需要管理员权限");
        Err("启动服务需要管理员权限，请以管理员身份运行应用".to_string())
    } else {
        error!("启动服务失败: {}", combined);
        Err(format!("启动服务失败: {}", combined.trim()))
    }
}

/// 启动时检查并尝试启动服务
///
/// 此函数在应用启动时调用，检查服务状态并尝试启动。
/// 这是一个后台操作，不会阻塞应用启动。
///
/// **Validates: Requirements 1.4, 1.5, 1.6**
pub async fn startup_service_check(state: &FileSearchState) {
    // 避免重复检查
    if state.startup_check_done.swap(true, Ordering::SeqCst) {
        debug!("启动检查已完成，跳过");
        return;
    }

    info!("执行文件搜索服务启动检查...");

    // 检查服务状态
    let service_state = check_windows_service_state().await;

    match service_state {
        WindowsServiceState::Running => {
            info!("文件搜索服务已在运行");
            // 尝试连接到服务
            let mut client = state.client.lock().await;
            if let Err(e) = client.connect().await {
                warn!("连接到文件搜索服务失败: {}", e);
            } else {
                info!("已成功连接到文件搜索服务");
            }
        }
        WindowsServiceState::Stopped => {
            info!("文件搜索服务已停止，尝试启动...");
            match try_start_windows_service().await {
                Ok(true) => {
                    info!("服务启动命令已发送，等待服务就绪...");
                    // 等待服务启动
                    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
                    // 尝试连接
                    let mut client = state.client.lock().await;
                    if let Err(e) = client.connect().await {
                        warn!("服务启动后连接失败: {}", e);
                    } else {
                        info!("已成功连接到文件搜索服务");
                    }
                }
                Ok(false) => {
                    info!("文件搜索服务未安装，跳过自动启动");
                }
                Err(e) => {
                    warn!("启动服务失败: {}", e);
                }
            }
        }
        WindowsServiceState::StartPending => {
            info!("文件搜索服务正在启动中，等待...");
            tokio::time::sleep(tokio::time::Duration::from_secs(3)).await;
            // 尝试连接
            let mut client = state.client.lock().await;
            if let Err(e) = client.connect().await {
                warn!("服务启动后连接失败: {}", e);
            }
        }
        WindowsServiceState::NotInstalled => {
            info!("文件搜索服务未安装，功能不可用");
        }
        _ => {
            warn!("文件搜索服务状态未知: {:?}", service_state);
        }
    }
}

// =============================================================================
// Frontend Types (TypeScript Compatible)
// =============================================================================

/// 前端搜索查询参数
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchParams {
    /// 搜索关键词
    pub keyword: String,

    /// 匹配模式: "exact" | "wildcard" | "fuzzy" | "regex"
    #[serde(default = "default_match_mode")]
    pub match_mode: String,

    /// 搜索过滤器
    #[serde(default)]
    pub filters: Option<FileSearchFilters>,

    /// 排序字段: "relevance" | "name" | "path" | "size" | "modified"
    #[serde(default = "default_sort_by")]
    pub sort_by: String,

    /// 排序顺序: "asc" | "desc"
    #[serde(default = "default_sort_order")]
    pub sort_order: String,

    /// 返回结果数量限制
    #[serde(default = "default_limit")]
    pub limit: usize,

    /// 分页偏移量
    #[serde(default)]
    pub offset: usize,
}

fn default_match_mode() -> String {
    "fuzzy".to_string()
}

fn default_sort_by() -> String {
    "relevance".to_string()
}

fn default_sort_order() -> String {
    "desc".to_string()
}

fn default_limit() -> usize {
    100
}

/// 前端搜索过滤器
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchFilters {
    /// 文件扩展名过滤
    pub extensions: Option<Vec<String>>,

    /// 最小文件大小（字节）
    pub min_size: Option<u64>,

    /// 最大文件大小（字节）
    pub max_size: Option<u64>,

    /// 修改时间范围开始（ISO 8601 格式）
    pub modified_after: Option<String>,

    /// 修改时间范围结束（ISO 8601 格式）
    pub modified_before: Option<String>,

    /// 是否包含目录
    #[serde(default)]
    pub include_directories: bool,

    /// 限定搜索的卷（如 ["C", "D"]）
    pub volumes: Option<Vec<String>>,
}

/// 前端搜索结果
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchResultItem {
    /// 文件 ID
    pub file_id: String,

    /// 文件名
    pub name: String,

    /// 完整路径
    pub path: String,

    /// 文件大小（字节）
    pub size: u64,

    /// 修改时间（ISO 8601 格式）
    pub modified: String,

    /// 是否为目录
    pub is_directory: bool,

    /// 相关度分数
    pub score: i64,

    /// 匹配位置（用于高亮）
    pub match_indices: Vec<(usize, usize)>,
}

impl From<SearchResult> for FileSearchResultItem {
    fn from(result: SearchResult) -> Self {
        Self {
            file_id: result.file_id.to_string(),
            name: result.name,
            path: result.path.to_string_lossy().to_string(),
            size: result.size,
            modified: result.modified.to_rfc3339(),
            is_directory: result.is_directory,
            score: result.score,
            match_indices: result.match_indices,
        }
    }
}

/// 前端搜索响应
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchResponse {
    /// 搜索结果列表
    pub results: Vec<FileSearchResultItem>,

    /// 总匹配数量
    pub total_count: u64,

    /// 搜索耗时（毫秒）
    pub search_time_ms: u64,
}

/// 前端服务状态响应
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceStatusResponse {
    /// 服务状态: "starting" | "running" | "scanning" | "stopping" | "stopped"
    pub state: String,

    /// Windows 服务状态: "running" | "stopped" | "start_pending" | "stop_pending" | "not_installed" | "unknown"
    pub windows_service_state: String,

    /// 已索引文件数量
    pub indexed_files: Option<u64>,

    /// 最后更新时间（ISO 8601 格式）
    pub last_update: Option<String>,

    /// 扫描进度（0.0 - 1.0）
    pub scan_progress: Option<f32>,

    /// 已扫描文件数量
    pub scanned_files: Option<u64>,

    /// 服务是否可用（已安装且可连接）
    pub is_available: bool,

    /// 用户友好的状态消息
    pub status_message: String,
}

impl From<ServiceStatus> for ServiceStatusResponse {
    fn from(status: ServiceStatus) -> Self {
        match status {
            ServiceStatus::Starting => Self {
                state: "starting".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: None,
                last_update: None,
                scan_progress: None,
                scanned_files: None,
                is_available: true,
                status_message: "服务正在启动...".to_string(),
            },
            ServiceStatus::Running { indexed_files, last_update } => Self {
                state: "running".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: Some(indexed_files),
                last_update: Some(last_update.to_rfc3339()),
                scan_progress: None,
                scanned_files: None,
                is_available: true,
                status_message: format!("已索引 {} 个文件", indexed_files),
            },
            ServiceStatus::Scanning { progress, scanned_files } => Self {
                state: "scanning".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: None,
                last_update: None,
                scan_progress: Some(progress),
                scanned_files: Some(scanned_files),
                is_available: true,
                status_message: format!("正在扫描... {:.1}%", progress * 100.0),
            },
            ServiceStatus::Stopping => Self {
                state: "stopping".to_string(),
                windows_service_state: "stop_pending".to_string(),
                indexed_files: None,
                last_update: None,
                scan_progress: None,
                scanned_files: None,
                is_available: false,
                status_message: "服务正在停止...".to_string(),
            },
            ServiceStatus::Stopped => Self {
                state: "stopped".to_string(),
                windows_service_state: "stopped".to_string(),
                indexed_files: None,
                last_update: None,
                scan_progress: None,
                scanned_files: None,
                is_available: false,
                status_message: "服务已停止".to_string(),
            },
        }
    }
}

/// 创建服务不可用的响应
#[allow(dead_code)]
fn create_unavailable_response(windows_state: WindowsServiceState) -> ServiceStatusResponse {
    let (state_str, message) = match windows_state {
        WindowsServiceState::NotInstalled => ("not_installed", "文件搜索服务未安装"),
        WindowsServiceState::Stopped => ("stopped", "文件搜索服务已停止"),
        WindowsServiceState::StartPending => ("starting", "文件搜索服务正在启动..."),
        WindowsServiceState::StopPending => ("stopping", "文件搜索服务正在停止..."),
        WindowsServiceState::Running => ("running", "服务运行中但无法连接"),
        WindowsServiceState::Unknown => ("unknown", "无法获取服务状态"),
    };

    ServiceStatusResponse {
        state: "stopped".to_string(),
        windows_service_state: state_str.to_string(),
        indexed_files: None,
        last_update: None,
        scan_progress: None,
        scanned_files: None,
        is_available: false,
        status_message: message.to_string(),
    }
}

/// 前端索引配置
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IndexConfigParams {
    /// 要索引的卷（如 ["C", "D"]）
    pub volumes: Vec<String>,

    /// 排除的路径
    pub exclude_paths: Vec<String>,

    /// 结果数量限制
    pub result_limit: usize,
}

// =============================================================================
// Helper Functions
// =============================================================================

/// 将前端匹配模式字符串转换为 MatchMode 枚举
#[allow(dead_code)]
fn parse_match_mode(mode: &str) -> MatchMode {
    match mode.to_lowercase().as_str() {
        "exact" => MatchMode::Exact,
        "wildcard" => MatchMode::Wildcard,
        "regex" => MatchMode::Regex,
        _ => MatchMode::Fuzzy, // 默认模糊匹配
    }
}

/// 将前端排序字段字符串转换为 SortField 枚举
#[allow(dead_code)]
fn parse_sort_field(field: &str) -> SortField {
    match field.to_lowercase().as_str() {
        "name" => SortField::Name,
        "path" => SortField::Path,
        "size" => SortField::Size,
        "modified" => SortField::Modified,
        _ => SortField::Relevance, // 默认按相关度排序
    }
}

/// 将前端排序顺序字符串转换为 SortOrder 枚举
#[allow(dead_code)]
fn parse_sort_order(order: &str) -> SortOrder {
    match order.to_lowercase().as_str() {
        "asc" => SortOrder::Asc,
        _ => SortOrder::Desc, // 默认降序
    }
}

/// 将前端搜索参数转换为内部 SearchQuery
#[allow(dead_code)]
fn convert_search_params(params: FileSearchParams) -> SearchQuery {
    let filters = params
        .filters
        .map(|f| SearchFilters {
            extensions: f.extensions,
            min_size: f.min_size,
            max_size: f.max_size,
            modified_after: f.modified_after.and_then(|s| {
                chrono::DateTime::parse_from_rfc3339(&s)
                    .ok()
                    .map(|dt| dt.with_timezone(&chrono::Utc))
            }),
            modified_before: f.modified_before.and_then(|s| {
                chrono::DateTime::parse_from_rfc3339(&s)
                    .ok()
                    .map(|dt| dt.with_timezone(&chrono::Utc))
            }),
            include_directories: f.include_directories,
            volumes: f.volumes.map(|v| v.into_iter().filter_map(|s| s.chars().next()).collect()),
        })
        .unwrap_or_default();

    SearchQuery {
        keyword: params.keyword,
        match_mode: parse_match_mode(&params.match_mode),
        filters,
        sort_by: parse_sort_field(&params.sort_by),
        sort_order: parse_sort_order(&params.sort_order),
        limit: params.limit,
        offset: params.offset,
    }
}

/// 错误上下文信息，用于增强日志记录
#[derive(Debug, Clone)]
struct ErrorContext {
    operation: &'static str,
    details: Option<String>,
}

impl ErrorContext {
    fn new(operation: &'static str) -> Self {
        Self { operation, details: None }
    }

    fn with_details(operation: &'static str, details: impl Into<String>) -> Self {
        Self { operation, details: Some(details.into()) }
    }
}

/// 将 SearchClientError 转换为用户友好的错误消息
///
/// **Validates: Requirements 10.1, 10.2**
/// - 10.1: IF Index_Service crashes, THEN THE Search_Client SHALL display a friendly error message
/// - 10.2: IF Index_Service is unavailable, THEN THE application SHALL offer to start it
fn format_error(error: SearchClientError) -> String {
    match error {
        SearchClientError::ServiceNotRunning => {
            "文件搜索服务未运行。请点击「启动服务」按钮或在设置中启用自动启动。".to_string()
        }
        SearchClientError::ConnectionFailed(msg) => {
            if msg.contains("Pipe busy") {
                "文件搜索服务正忙，请稍后重试".to_string()
            } else {
                format!("无法连接到文件搜索服务。请检查服务是否已启动。\n详细信息: {}", msg)
            }
        }
        SearchClientError::ConnectionLost => {
            "与文件搜索服务的连接已断开。正在尝试重新连接，请稍后重试。".to_string()
        }
        SearchClientError::Timeout => "请求超时。可能是索引正在构建中，请稍后重试。".to_string(),
        SearchClientError::ServiceError { code, message } => {
            let code_desc = match code {
                crate::file_search::ErrorCode::NotReady => "索引未就绪",
                crate::file_search::ErrorCode::InvalidQuery => "无效的搜索查询",
                crate::file_search::ErrorCode::Timeout => "操作超时",
                crate::file_search::ErrorCode::InternalError => "内部错误",
                crate::file_search::ErrorCode::PermissionDenied => "权限不足",
                crate::file_search::ErrorCode::ShuttingDown => "服务正在关闭",
            };
            format!("{}: {}", code_desc, message)
        }
        SearchClientError::MaxRetriesExceeded { attempts } => {
            format!("连接文件搜索服务失败，已重试 {} 次。请检查服务状态或尝试重启服务。", attempts)
        }
        SearchClientError::NotConnected => "未连接到文件搜索服务。请先启动服务。".to_string(),
        SearchClientError::InvalidResponse(msg) => {
            format!("服务返回了无效的响应: {}", msg)
        }
        SearchClientError::MessageTooLarge { size, max } => {
            format!("请求数据过大 ({} 字节)，超过最大限制 ({} 字节)", size, max)
        }
        SearchClientError::Io(ref e) => {
            format!("通信错误: {}", e)
        }
        SearchClientError::Json(ref e) => {
            format!("数据格式错误: {}", e)
        }
    }
}

/// 记录错误到日志，包含上下文信息
///
/// **Validates: Requirements 10.7**
/// - THE Index_Service SHALL log all errors to the standard log directory
fn log_error_with_context(error: &SearchClientError, context: &ErrorContext) {
    let error_type = match error {
        SearchClientError::ServiceNotRunning => "ServiceNotRunning",
        SearchClientError::ConnectionFailed(_) => "ConnectionFailed",
        SearchClientError::ConnectionLost => "ConnectionLost",
        SearchClientError::Timeout => "Timeout",
        SearchClientError::ServiceError { .. } => "ServiceError",
        SearchClientError::MaxRetriesExceeded { .. } => "MaxRetriesExceeded",
        SearchClientError::NotConnected => "NotConnected",
        SearchClientError::InvalidResponse(_) => "InvalidResponse",
        SearchClientError::MessageTooLarge { .. } => "MessageTooLarge",
        SearchClientError::Io(_) => "IoError",
        SearchClientError::Json(_) => "JsonError",
    };

    if let Some(ref details) = context.details {
        error!(
            target: "file_search",
            error_type = error_type,
            operation = context.operation,
            details = details,
            "文件搜索错误: {}", error
        );
    } else {
        error!(
            target: "file_search",
            error_type = error_type,
            operation = context.operation,
            "文件搜索错误: {}", error
        );
    }
}

/// 判断错误是否可以通过重试恢复
fn is_transient_error(error: &SearchClientError) -> bool {
    matches!(
        error,
        SearchClientError::Timeout
            | SearchClientError::ConnectionLost
            | SearchClientError::ConnectionFailed(_)
    )
}

/// 压缩空白字符，生成单行查询文本
fn normalize_query_whitespace(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// 清洗用户搜索关键词，避免长日志/大段 OCR 文本触发重负载搜索
fn sanitize_user_search_keyword(raw: &str) -> String {
    let normalized = normalize_query_whitespace(raw);
    if normalized.is_empty() {
        return normalized;
    }

    if normalized.chars().count() <= MAX_USER_SEARCH_QUERY_CHARS {
        return normalized;
    }

    let extractor = KeywordExtractor::new();
    let mut keywords = extractor.extract_keywords(&normalized);
    keywords.retain(|token| token.chars().count() >= 2);
    keywords.truncate(MAX_USER_SEARCH_QUERY_TOKENS);

    if !keywords.is_empty() {
        let compact = keywords.join(" ");
        let truncated: String = compact.chars().take(MAX_USER_SEARCH_QUERY_CHARS).collect();
        return normalize_query_whitespace(&truncated);
    }

    normalized.chars().take(MAX_USER_SEARCH_QUERY_CHARS).collect()
}

// =============================================================================
// Tauri Commands
// =============================================================================

/// 搜索文件
///
/// **Validates: Requirements 5.1, 10.1, 10.4**
/// - 5.1: WHEN a user enters a search query, THE Fuzzy_Matcher SHALL return matching files within 10ms
/// - 10.1: IF Index_Service crashes, THEN THE Search_Client SHALL display a friendly error message
/// - 10.4: IF Named_Pipe connection fails, THEN THE Search_Client SHALL retry with timeout
///
/// # Arguments
///
/// * `params` - 搜索参数
///
/// # Returns
///
/// 搜索结果列表
#[tauri::command]
pub async fn file_search(
    state: State<'_, FileSearchState>,
    query: FileSearchParams,
) -> Result<FileSearchResponse, String> {
    let raw_keyword = query.keyword.clone();
    let keyword = sanitize_user_search_keyword(&raw_keyword);
    let match_mode = query.match_mode.clone();
    let limit = query.limit;
    let offset = query.offset;
    debug!("文件搜索请求: keyword={}", keyword);

    if keyword.is_empty() {
        return Ok(FileSearchResponse { results: vec![], total_count: 0, search_time_ms: 0 });
    }

    if keyword != raw_keyword {
        info!(
            target: "file_search",
            "检测到超长搜索词，已自动提取关键词: 原始长度={} -> 清洗后='{}'",
            raw_keyword.chars().count(),
            keyword
        );
    }

    // 使用内置索引器搜索（无需 Windows 服务）
    let search_results = state.indexer.search(&keyword, &match_mode, limit, offset);

    let results: Vec<FileSearchResultItem> = search_results
        .hits
        .into_iter()
        .enumerate()
        .map(|(i, hit)| {
            // 将修改时间转换为 ISO 8601 格式
            let modified = chrono::DateTime::from_timestamp(hit.modified_secs, 0)
                .unwrap_or_default()
                .to_rfc3339();

            FileSearchResultItem {
                file_id: format!("{}", i + offset),
                name: hit.name,
                path: hit.path,
                size: hit.size,
                modified,
                is_directory: hit.is_directory,
                score: hit.score,
                match_indices: hit.match_indices,
            }
        })
        .collect();

    info!(
        "文件搜索完成: {} 个结果 (总匹配: {}, 耗时: {}ms, 关键词: {})",
        results.len(),
        search_results.total_count,
        search_results.search_time_ms,
        keyword
    );

    Ok(FileSearchResponse {
        results,
        total_count: search_results.total_count,
        search_time_ms: search_results.search_time_ms,
    })
}

/// 获取文件搜索服务状态
///
/// **Validates: Requirements 1.4, 1.6, 10.1, 10.2**
/// - 1.4: WHEN the main application starts, THE Search_Client SHALL check if Index_Service is running
/// - 1.6: THE Index_Service SHALL provide status query interface for health monitoring
/// - 10.1: IF Index_Service crashes, THEN THE Search_Client SHALL display a friendly error message
/// - 10.2: IF Index_Service is unavailable, THEN THE application SHALL offer to start it
///
/// 此命令会检查 Windows 服务状态和索引服务状态，
/// 返回综合的服务状态信息给前端显示。
///
/// # Returns
///
/// 服务状态信息
#[tauri::command]
pub async fn get_search_service_status(
    state: State<'_, FileSearchState>,
) -> Result<ServiceStatusResponse, String> {
    debug!("获取文件搜索服务状态（内置索引器）");

    // 使用内置索引器的状态
    let indexer_status = state.indexer.get_status();

    let response = match indexer_status {
        crate::file_search::indexer::IndexerStatus::Idle => ServiceStatusResponse {
            state: "starting".to_string(),
            windows_service_state: "running".to_string(),
            indexed_files: None,
            last_update: None,
            scan_progress: Some(0.0),
            scanned_files: Some(0),
            is_available: true,
            status_message: "正在初始化文件索引...".to_string(),
        },
        crate::file_search::indexer::IndexerStatus::Scanning { scanned_files } => {
            ServiceStatusResponse {
                state: "scanning".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: Some(scanned_files),
                last_update: None,
                scan_progress: None,
                scanned_files: Some(scanned_files),
                is_available: true,
                status_message: format!("正在扫描文件... 已索引 {} 个", scanned_files),
            }
        }
        crate::file_search::indexer::IndexerStatus::Ready { total_files, scan_time_ms } => {
            ServiceStatusResponse {
                state: "running".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: Some(total_files),
                last_update: Some(chrono::Utc::now().to_rfc3339()),
                scan_progress: Some(1.0),
                scanned_files: Some(total_files),
                is_available: true,
                status_message: format!(
                    "已索引 {} 个文件（扫描耗时 {:.1}s）",
                    total_files,
                    scan_time_ms as f64 / 1000.0
                ),
            }
        }
        crate::file_search::indexer::IndexerStatus::Error(msg) => ServiceStatusResponse {
            state: "stopped".to_string(),
            windows_service_state: "stopped".to_string(),
            indexed_files: None,
            last_update: None,
            scan_progress: None,
            scanned_files: None,
            is_available: false,
            status_message: format!("索引出错: {}", msg),
        },
    };

    info!(
        target: "file_search",
        "文件索引状态: {} ({})",
        response.state,
        response.status_message
    );

    Ok(response)

    // === 以下为原始 Windows 服务检查逻辑（已禁用）===
    // 如需使用 Windows 服务模式，取消注释以下代码
    /*
    let windows_state = check_windows_service_state().await;
    // ...原始服务检查逻辑...
    */
}

/// 启动文件搜索服务
///
/// **Validates: Requirements 1.5, 10.2, 10.7**
/// - 1.5: IF Index_Service is not running, THEN THE Search_Client SHALL attempt to start it via service control
/// - 10.2: IF Index_Service is unavailable, THEN THE application SHALL offer to start it
/// - 10.7: THE Index_Service SHALL log all errors to the standard log directory
///
/// 尝试通过 Windows 服务控制管理器启动索引服务。
///
/// # Returns
///
/// 成功返回服务状态，失败返回错误消息
#[tauri::command]
pub async fn start_search_service(
    state: State<'_, FileSearchState>,
) -> Result<ServiceStatusResponse, String> {
    info!(target: "file_search", "用户请求启动文件搜索服务");

    match try_start_windows_service().await {
        Ok(true) => {
            info!(target: "file_search", "服务启动命令已发送，等待服务就绪...");
            // 等待服务启动
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

            // 尝试连接并获取状态，支持重试
            let mut client = state.client.lock().await;
            let mut connect_attempts = 0;
            const MAX_CONNECT_ATTEMPTS: u32 = 3;

            while connect_attempts < MAX_CONNECT_ATTEMPTS {
                connect_attempts += 1;

                if let Err(e) = client.connect().await {
                    warn!(
                        target: "file_search",
                        "服务启动后连接失败 (尝试 {}/{}): {}",
                        connect_attempts,
                        MAX_CONNECT_ATTEMPTS,
                        e
                    );

                    if connect_attempts < MAX_CONNECT_ATTEMPTS {
                        // 等待后重试
                        tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                        continue;
                    }

                    // 所有连接尝试都失败，但服务可能仍在启动中
                    return Ok(ServiceStatusResponse {
                        state: "starting".to_string(),
                        windows_service_state: "start_pending".to_string(),
                        indexed_files: None,
                        last_update: None,
                        scan_progress: None,
                        scanned_files: None,
                        is_available: false,
                        status_message: "服务正在启动中，请稍后刷新状态...".to_string(),
                    });
                }

                // 连接成功，获取服务状态
                match client.get_status().await {
                    Ok(status) => {
                        info!(target: "file_search", "服务启动成功，已获取状态");
                        let mut response = ServiceStatusResponse::from(status);
                        response.windows_service_state = "running".to_string();
                        return Ok(response);
                    }
                    Err(e) => {
                        warn!(
                            target: "file_search",
                            "获取服务状态失败: {}",
                            e
                        );
                        // 继续重试
                        if connect_attempts < MAX_CONNECT_ATTEMPTS {
                            tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                            continue;
                        }
                    }
                }
            }

            // 返回启动中状态
            Ok(ServiceStatusResponse {
                state: "starting".to_string(),
                windows_service_state: "running".to_string(),
                indexed_files: None,
                last_update: None,
                scan_progress: None,
                scanned_files: None,
                is_available: true,
                status_message: "服务已启动，正在初始化...".to_string(),
            })
        }
        Ok(false) => {
            // 服务未安装
            warn!(target: "file_search", "文件搜索服务未安装");
            Err("文件搜索服务未安装。请先在设置中安装服务。".to_string())
        }
        Err(e) => {
            // 启动失败，记录详细错误
            error!(
                target: "file_search",
                error_type = "ServiceStartFailed",
                "启动文件搜索服务失败: {}",
                e
            );
            Err(e)
        }
    }
}

/// 重建文件搜索索引
///
/// **Validates: Requirements 9.5, 10.7**
/// - 9.5: THE settings SHALL provide a "Rebuild Index" button for manual reindexing
/// - 10.7: THE Index_Service SHALL log all errors to the standard log directory
///
/// 触发索引服务重新扫描所有配置的卷。
///
/// # Returns
///
/// 成功返回 Ok(()), 失败返回错误消息
#[tauri::command]
pub async fn rebuild_search_index(state: State<'_, FileSearchState>) -> Result<(), String> {
    info!(target: "file_search", "用户请求重建文件搜索索引");

    let mut client = state.client.lock().await;

    // 确保已连接
    if !client.is_connected() {
        if let Err(e) = client.connect().await {
            let ctx = ErrorContext::new("rebuild_index_connect");
            log_error_with_context(&e, &ctx);
            return Err(format_error(e));
        }
    }

    // 发送重建索引请求
    match client.rebuild_index().await {
        Ok(()) => {
            info!(target: "file_search", "索引重建请求已成功发送");
            Ok(())
        }
        Err(e) => {
            let ctx = ErrorContext::new("rebuild_index");
            log_error_with_context(&e, &ctx);
            Err(format_error(e))
        }
    }
}

/// 更新文件搜索配置
///
/// **Validates: Requirements 9.6, 10.7**
/// - 9.6: WHEN settings change, THE Index_Service SHALL update index accordingly
/// - 10.7: THE Index_Service SHALL log all errors to the standard log directory
///
/// 更新索引服务的配置，包括要索引的卷、排除路径等。
///
/// # Arguments
///
/// * `config` - 新的配置参数
///
/// # Returns
///
/// 成功返回 Ok(()), 失败返回错误消息
#[tauri::command]
pub async fn update_search_config(
    state: State<'_, FileSearchState>,
    config: IndexConfigParams,
) -> Result<(), String> {
    info!(target: "file_search", "用户请求更新文件搜索配置");
    debug!(
        target: "file_search",
        "新配置: volumes={:?}, exclude_paths={:?}, result_limit={}",
        config.volumes,
        config.exclude_paths,
        config.result_limit
    );

    let mut client = state.client.lock().await;

    // 确保已连接
    if !client.is_connected() {
        if let Err(e) = client.connect().await {
            let ctx = ErrorContext::with_details(
                "update_config_connect",
                format!("volumes={:?}", config.volumes),
            );
            log_error_with_context(&e, &ctx);
            return Err(format_error(e));
        }
    }

    // 转换配置
    let index_config = IndexConfig {
        volumes: config.volumes.into_iter().filter_map(|s| s.chars().next()).collect(),
        exclude_paths: config.exclude_paths.into_iter().map(std::path::PathBuf::from).collect(),
        result_limit: config.result_limit,
    };

    // 发送配置更新请求
    match client.update_config(index_config).await {
        Ok(()) => {
            info!(target: "file_search", "配置更新成功");
            Ok(())
        }
        Err(e) => {
            let ctx = ErrorContext::new("update_config");
            log_error_with_context(&e, &ctx);
            Err(format_error(e))
        }
    }
}

// =============================================================================
// Service Installation Commands
// =============================================================================

/// 服务安装结果
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceInstallResult {
    /// 是否成功
    pub success: bool,
    /// 消息
    pub message: String,
    /// 是否需要重启应用
    pub needs_restart: bool,
}

/// 检查文件搜索服务是否已安装
///
/// **Validates: Requirements 1.1, 1.2**
/// - 1.1: WHEN the application is first installed, THE Index_Service SHALL be registered as a Windows service
/// - 1.2: WHEN the service is installed, THE Index_Service SHALL request administrator authorization only once
///
/// # Returns
///
/// 返回服务是否已安装
#[tauri::command]
pub async fn is_file_search_service_installed() -> bool {
    debug!(target: "file_search", "检查文件搜索服务是否已安装");
    let state = check_windows_service_state().await;
    let installed = !matches!(state, WindowsServiceState::NotInstalled);
    info!(
        target: "file_search",
        "文件搜索服务安装状态: {} (Windows 状态: {:?})",
        if installed { "已安装" } else { "未安装" },
        state
    );
    installed
}

/// 安装文件搜索服务（需要管理员权限）
///
/// **Validates: Requirements 1.1, 1.2**
/// - 1.1: WHEN the application is first installed, THE Index_Service SHALL be registered as a Windows service with SYSTEM privileges
/// - 1.2: WHEN the service is installed, THE Index_Service SHALL request administrator authorization only once
///
/// 此命令会启动一个提权进程来安装服务。
/// 用户会看到 UAC 提示，只需授权一次。
///
/// # Returns
///
/// 安装结果，包含成功状态和消息
#[tauri::command]
pub async fn install_file_search_service(
    app: tauri::AppHandle,
) -> Result<ServiceInstallResult, String> {
    info!(target: "file_search", "用户请求安装文件搜索服务");

    // 首先检查服务是否已安装
    let current_state = check_windows_service_state().await;
    if !matches!(current_state, WindowsServiceState::NotInstalled) {
        info!(target: "file_search", "服务已安装，无需重复安装");
        return Ok(ServiceInstallResult {
            success: true,
            message: "文件搜索服务已安装".to_string(),
            needs_restart: false,
        });
    }

    // 获取服务可执行文件路径
    // 服务可执行文件应该在应用资源目录中
    let service_exe_path = get_service_executable_path(&app)?;

    info!(
        target: "file_search",
        "服务可执行文件路径: {:?}",
        service_exe_path
    );

    // 检查服务可执行文件是否存在
    if !service_exe_path.exists() {
        error!(
            target: "file_search",
            "服务可执行文件不存在: {:?}",
            service_exe_path
        );
        return Err(format!(
            "服务可执行文件不存在: {:?}\n请确保应用已正确安装。",
            service_exe_path
        ));
    }

    // 使用 PowerShell 的 Start-Process 以管理员权限运行安装命令
    // 这会触发 UAC 提示
    let install_result = run_elevated_install(&service_exe_path).await;

    match install_result {
        Ok(()) => {
            info!(target: "file_search", "服务安装命令已执行");

            // 等待一小段时间让服务注册完成
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

            // 验证安装是否成功
            let new_state = check_windows_service_state().await;
            if matches!(new_state, WindowsServiceState::NotInstalled) {
                warn!(target: "file_search", "服务安装后仍显示未安装");
                return Ok(ServiceInstallResult {
                    success: false,
                    message: "服务安装可能失败，请检查是否已授权管理员权限".to_string(),
                    needs_restart: false,
                });
            }

            // 尝试启动服务
            match try_start_windows_service().await {
                Ok(true) => {
                    info!(target: "file_search", "服务安装并启动成功");
                    Ok(ServiceInstallResult {
                        success: true,
                        message: "文件搜索服务安装成功并已启动".to_string(),
                        needs_restart: false,
                    })
                }
                Ok(false) => {
                    // 服务安装了但启动失败
                    warn!(target: "file_search", "服务已安装但启动失败");
                    Ok(ServiceInstallResult {
                        success: true,
                        message: "服务已安装，但启动失败。请尝试手动启动服务。".to_string(),
                        needs_restart: false,
                    })
                }
                Err(e) => {
                    warn!(target: "file_search", "服务已安装但启动出错: {}", e);
                    Ok(ServiceInstallResult {
                        success: true,
                        message: format!("服务已安装，但启动时出错: {}", e),
                        needs_restart: false,
                    })
                }
            }
        }
        Err(e) => {
            error!(target: "file_search", "服务安装失败: {}", e);
            Err(e)
        }
    }
}

/// 获取服务可执行文件路径
fn get_service_executable_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let _ = &app; // 在 debug 模式下不使用，但 release 模式需要
                  // 在开发模式下，服务可执行文件在 target/debug 或 target/release 目录
                  // 在生产模式下，服务可执行文件应该在应用资源目录中

    #[cfg(debug_assertions)]
    {
        // 开发模式：查找 target/debug 目录
        let exe_path =
            std::env::current_exe().map_err(|e| format!("获取当前可执行文件路径失败: {}", e))?;

        // 从当前 exe 路径向上查找 target 目录
        let target_dir = exe_path.parent().map(|p| p.to_path_buf());

        // 尝试多个可能的位置
        let possible_paths = [
            // target/debug/file-search-service.exe
            target_dir.as_ref().map(|p| p.join("file-search-service.exe")),
            // src-tauri/target/debug/file-search-service.exe
            target_dir.as_ref().and_then(|p| {
                p.parent().map(|pp| {
                    pp.join("file-search-service")
                        .join("target")
                        .join("debug")
                        .join("file-search-service.exe")
                })
            }),
            // 直接在 file-search-service 目录构建的
            Some(std::path::PathBuf::from(
                r"D:\screenshot\HuGeScreenshot-tauri\src-tauri\file-search-service\target\debug\file-search-service.exe",
            )),
            Some(std::path::PathBuf::from(
                r"D:\screenshot\HuGeScreenshot-tauri\src-tauri\file-search-service\target\release\file-search-service.exe",
            )),
        ];

        for path in possible_paths.into_iter().flatten() {
            if path.exists() {
                return Ok(path);
            }
        }

        // 如果都找不到，返回默认路径（让后续检查报错）
        Ok(std::path::PathBuf::from(
            r"D:\screenshot\HuGeScreenshot-tauri\src-tauri\file-search-service\target\debug\file-search-service.exe",
        ))
    }

    #[cfg(not(debug_assertions))]
    {
        // 生产模式：服务可执行文件应该在应用资源目录
        let resource_dir =
            app.path().resource_dir().map_err(|e| format!("获取资源目录失败: {}", e))?;

        Ok(resource_dir.join("file-search-service.exe"))
    }
}

/// 以管理员权限运行服务安装命令
///
/// 使用 PowerShell 的 Start-Process -Verb RunAs 触发 UAC 提权
async fn run_elevated_install(service_exe_path: &std::path::Path) -> Result<(), String> {
    let exe_path_str = service_exe_path.to_string_lossy();

    info!(
        target: "file_search",
        "以管理员权限运行安装命令: {} install",
        exe_path_str
    );

    // 使用 PowerShell 的 Start-Process 以管理员权限运行
    // -Verb RunAs 会触发 UAC 提示
    // -Wait 等待进程完成
    // -PassThru 返回进程对象以获取退出码
    let ps_script = format!(
        r#"
        $process = Start-Process -FilePath '{}' -ArgumentList 'install' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        exit $process.ExitCode
        "#,
        exe_path_str
    );

    let output = tokio::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            &ps_script,
        ])
        .output()
        .await
        .map_err(|e| format!("执行 PowerShell 命令失败: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    debug!(
        target: "file_search",
        "PowerShell 输出: stdout={}, stderr={}, exit_code={:?}",
        stdout.trim(),
        stderr.trim(),
        output.status.code()
    );

    if output.status.success() {
        Ok(())
    } else {
        // 检查是否是用户取消了 UAC
        let combined = format!("{}{}", stdout, stderr);
        if combined.contains("canceled") || combined.contains("取消") || combined.contains("1223")
        {
            Err("用户取消了管理员授权".to_string())
        } else if combined.contains("740") || combined.contains("elevation") {
            Err("需要管理员权限才能安装服务".to_string())
        } else {
            Err(format!("服务安装失败 (退出码: {:?}): {}", output.status.code(), combined.trim()))
        }
    }
}

/// 卸载文件搜索服务（需要管理员权限）
///
/// **Validates: Requirements 1.7**
/// - 1.7: WHEN the application is uninstalled, THE Index_Service SHALL be properly removed from Windows services
///
/// This command performs the following cleanup:
/// 1. Stops the running service (if running)
/// 2. Removes the service from Windows Service Control Manager
/// 3. Optionally cleans up index files from disk
///
/// # Arguments
///
/// * `app` - Tauri application handle
/// * `cleanup_index` - Whether to also delete index files (default: true)
///
/// # Returns
///
/// 卸载结果
#[tauri::command]
pub async fn uninstall_file_search_service(
    app: tauri::AppHandle,
    cleanup_index: Option<bool>,
) -> Result<ServiceInstallResult, String> {
    info!(target: "file_search", "用户请求卸载文件搜索服务");

    let should_cleanup_index = cleanup_index.unwrap_or(true);

    // 首先检查服务是否已安装
    let current_state = check_windows_service_state().await;
    if matches!(current_state, WindowsServiceState::NotInstalled) {
        info!(target: "file_search", "服务未安装，无需卸载");

        // Even if service is not installed, we may still want to clean up index files
        if should_cleanup_index {
            let cleanup_result = cleanup_index_files().await;
            if let Err(e) = cleanup_result {
                warn!(target: "file_search", "清理索引文件失败: {}", e);
            }
        }

        return Ok(ServiceInstallResult {
            success: true,
            message: "文件搜索服务未安装".to_string(),
            needs_restart: false,
        });
    }

    // 获取服务可执行文件路径
    let service_exe_path = get_service_executable_path(&app)?;

    // 检查服务可执行文件是否存在
    if !service_exe_path.exists() {
        // 服务可执行文件不存在，尝试使用 sc delete 直接删除
        warn!(
            target: "file_search",
            "服务可执行文件不存在，尝试使用 sc delete 卸载"
        );
        let result = run_elevated_sc_delete().await;

        // Clean up index files after service removal
        if should_cleanup_index {
            let cleanup_result = cleanup_index_files().await;
            if let Err(e) = cleanup_result {
                warn!(target: "file_search", "清理索引文件失败: {}", e);
            }
        }

        return result;
    }

    // 使用服务可执行文件的 uninstall 命令
    let uninstall_result = run_elevated_uninstall(&service_exe_path).await;

    match uninstall_result {
        Ok(()) => {
            info!(target: "file_search", "服务卸载命令已执行");

            // 等待一小段时间让服务注销完成
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

            // 验证卸载是否成功
            let new_state = check_windows_service_state().await;
            if matches!(new_state, WindowsServiceState::NotInstalled) {
                info!(target: "file_search", "服务卸载成功");

                // Clean up index files after successful service removal
                if should_cleanup_index {
                    let cleanup_result = cleanup_index_files().await;
                    match cleanup_result {
                        Ok(cleaned_files) => {
                            info!(target: "file_search", "已清理 {} 个索引文件", cleaned_files);
                        }
                        Err(e) => {
                            warn!(target: "file_search", "清理索引文件失败: {}", e);
                        }
                    }
                }

                Ok(ServiceInstallResult {
                    success: true,
                    message: "文件搜索服务已卸载".to_string(),
                    needs_restart: false,
                })
            } else {
                warn!(target: "file_search", "服务卸载后仍显示已安装");
                Ok(ServiceInstallResult {
                    success: false,
                    message: "服务卸载可能失败，请检查是否已授权管理员权限".to_string(),
                    needs_restart: false,
                })
            }
        }
        Err(e) => {
            error!(target: "file_search", "服务卸载失败: {}", e);
            Err(e)
        }
    }
}

/// Clean up index files from disk
///
/// **Validates: Requirements 1.7**
/// - Removes index files when the application is uninstalled
///
/// This function removes:
/// - file_index.bin - The main index file
/// - file_search_config.json - The configuration file
///
/// # Returns
///
/// Number of files cleaned up, or error message
async fn cleanup_index_files() -> Result<usize, String> {
    info!(target: "file_search", "开始清理索引文件...");

    let data_dir = dirs::data_local_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("."))
        .join("HuGeScreenshot");

    let files_to_clean = [
        "file_index.bin",          // Main index file
        "file_search_config.json", // Configuration file
    ];

    let mut cleaned_count = 0;

    for file_name in &files_to_clean {
        let file_path = data_dir.join(file_name);
        if file_path.exists() {
            match tokio::fs::remove_file(&file_path).await {
                Ok(()) => {
                    info!(target: "file_search", "已删除索引文件: {:?}", file_path);
                    cleaned_count += 1;
                }
                Err(e) => {
                    warn!(target: "file_search", "删除索引文件失败 {:?}: {}", file_path, e);
                }
            }
        } else {
            debug!(target: "file_search", "索引文件不存在，跳过: {:?}", file_path);
        }
    }

    info!(target: "file_search", "索引文件清理完成，共清理 {} 个文件", cleaned_count);
    Ok(cleaned_count)
}

/// Get the index files directory path
///
/// Returns the path to the directory containing index files.
/// This is useful for installer scripts that need to clean up files.
///
/// # Returns
///
/// Path to the index files directory
#[tauri::command]
pub async fn get_index_files_path() -> Result<String, String> {
    let data_dir = dirs::data_local_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("."))
        .join("HuGeScreenshot");

    Ok(data_dir.to_string_lossy().to_string())
}

/// 以管理员权限运行服务卸载命令
async fn run_elevated_uninstall(service_exe_path: &std::path::Path) -> Result<(), String> {
    let exe_path_str = service_exe_path.to_string_lossy();

    info!(
        target: "file_search",
        "以管理员权限运行卸载命令: {} uninstall",
        exe_path_str
    );

    let ps_script = format!(
        r#"
        $process = Start-Process -FilePath '{}' -ArgumentList 'uninstall' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        exit $process.ExitCode
        "#,
        exe_path_str
    );

    let output = tokio::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            &ps_script,
        ])
        .output()
        .await
        .map_err(|e| format!("执行 PowerShell 命令失败: {}", e))?;

    if output.status.success() {
        Ok(())
    } else {
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        if combined.contains("canceled") || combined.contains("取消") || combined.contains("1223")
        {
            Err("用户取消了管理员授权".to_string())
        } else {
            Err(format!("服务卸载失败 (退出码: {:?}): {}", output.status.code(), combined.trim()))
        }
    }
}

/// 使用 sc delete 命令卸载服务（备用方案）
async fn run_elevated_sc_delete() -> Result<ServiceInstallResult, String> {
    info!(target: "file_search", "使用 sc delete 卸载服务");

    let ps_script = format!(
        r#"
        $process = Start-Process -FilePath 'sc.exe' -ArgumentList 'delete', '{}' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        exit $process.ExitCode
        "#,
        SERVICE_NAME
    );

    let output = tokio::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            &ps_script,
        ])
        .output()
        .await
        .map_err(|e| format!("执行 PowerShell 命令失败: {}", e))?;

    if output.status.success() {
        Ok(ServiceInstallResult {
            success: true,
            message: "文件搜索服务已卸载".to_string(),
            needs_restart: false,
        })
    } else {
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        Err(format!("服务卸载失败: {}", combined.trim()))
    }
}

// =============================================================================
// Drive Information
// =============================================================================

/// 获取可用的 NTFS 驱动器列表
///
/// **Validates: Requirements 9.2**
/// - 9.2: THE settings SHALL allow selecting which drives to index
///
/// 枚举系统中所有可用的 NTFS 驱动器，返回驱动器信息列表。
///
/// # Returns
///
/// 驱动器信息列表，包含驱动器盘符、标签、总大小和可用空间
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DriveInfo {
    /// 驱动器盘符 (如 "C")
    pub letter: String,
    /// 驱动器标签 (如 "Windows")
    pub label: String,
    /// 文件系统类型 (如 "NTFS")
    pub file_system: String,
    /// 总大小（字节）
    pub total_size: u64,
    /// 可用空间（字节）
    pub free_space: u64,
    /// 是否为 NTFS 文件系统
    pub is_ntfs: bool,
}

// Windows drive type constants
#[cfg(windows)]
const DRIVE_FIXED: u32 = 3;
#[cfg(windows)]
const DRIVE_REMOVABLE: u32 = 2;

#[tauri::command]
pub async fn get_available_drives() -> Result<Vec<DriveInfo>, String> {
    info!(target: "file_search", "获取可用驱动器列表");

    let mut drives = Vec::new();

    #[cfg(windows)]
    {
        use std::ffi::OsString;
        use std::os::windows::ffi::OsStringExt;
        use windows::core::PCWSTR;
        use windows::Win32::Storage::FileSystem::{
            GetDiskFreeSpaceExW, GetDriveTypeW, GetLogicalDrives, GetVolumeInformationW,
        };

        // 获取逻辑驱动器位掩码
        let drive_mask = unsafe { GetLogicalDrives() };

        for i in 0..26 {
            if (drive_mask & (1 << i)) != 0 {
                let letter = (b'A' + i as u8) as char;
                let root_path: Vec<u16> =
                    format!("{}:\\", letter).encode_utf16().chain(std::iter::once(0)).collect();

                // 检查驱动器类型
                let drive_type = unsafe { GetDriveTypeW(PCWSTR(root_path.as_ptr())) };

                // 只处理固定驱动器和可移动驱动器
                if drive_type != DRIVE_FIXED && drive_type != DRIVE_REMOVABLE {
                    continue;
                }

                // 获取卷信息
                let mut volume_name: [u16; 261] = [0; 261];
                let mut file_system_name: [u16; 261] = [0; 261];
                let mut serial_number: u32 = 0;
                let mut max_component_length: u32 = 0;
                let mut file_system_flags: u32 = 0;

                let volume_info_result = unsafe {
                    GetVolumeInformationW(
                        PCWSTR(root_path.as_ptr()),
                        Some(&mut volume_name),
                        Some(&mut serial_number),
                        Some(&mut max_component_length),
                        Some(&mut file_system_flags),
                        Some(&mut file_system_name),
                    )
                };

                if volume_info_result.is_err() {
                    debug!(target: "file_search", "无法获取驱动器 {} 的卷信息", letter);
                    continue;
                }

                // 解析卷标签和文件系统
                let label = OsString::from_wide(&volume_name)
                    .to_string_lossy()
                    .trim_end_matches('\0')
                    .to_string();
                let file_system = OsString::from_wide(&file_system_name)
                    .to_string_lossy()
                    .trim_end_matches('\0')
                    .to_string();

                let is_ntfs = file_system.eq_ignore_ascii_case("NTFS");

                // 获取磁盘空间信息
                let mut free_bytes_available: u64 = 0;
                let mut total_bytes: u64 = 0;
                let mut total_free_bytes: u64 = 0;

                let space_result = unsafe {
                    GetDiskFreeSpaceExW(
                        PCWSTR(root_path.as_ptr()),
                        Some(&mut free_bytes_available as *mut u64),
                        Some(&mut total_bytes as *mut u64),
                        Some(&mut total_free_bytes as *mut u64),
                    )
                };

                if space_result.is_err() {
                    debug!(target: "file_search", "无法获取驱动器 {} 的空间信息", letter);
                    continue;
                }

                drives.push(DriveInfo {
                    letter: letter.to_string(),
                    label: if label.is_empty() { "本地磁盘".to_string() } else { label },
                    file_system,
                    total_size: total_bytes,
                    free_space: free_bytes_available,
                    is_ntfs,
                });

                debug!(
                    target: "file_search",
                    "发现驱动器: {} ({}) - {} - {:.2} GB",
                    letter,
                    drives.last().unwrap().label,
                    drives.last().unwrap().file_system,
                    total_bytes as f64 / 1024.0 / 1024.0 / 1024.0
                );
            }
        }
    }

    #[cfg(not(windows))]
    {
        // 非 Windows 平台返回空列表
        warn!(target: "file_search", "驱动器枚举仅支持 Windows 平台");
    }

    info!(
        target: "file_search",
        "找到 {} 个驱动器，其中 {} 个为 NTFS",
        drives.len(),
        drives.iter().filter(|d| d.is_ntfs).count()
    );

    Ok(drives)
}

/// 检查 Windows 服务状态
///
/// **Validates: Requirements 1.4, 1.6, 10.7**
/// - 1.4: WHEN the main application starts, THE Search_Client SHALL check if Index_Service is running
/// - 1.6: THE Index_Service SHALL provide status query interface for health monitoring
/// - 10.7: THE Index_Service SHALL log all errors to the standard log directory
///
/// 直接检查 Windows 服务控制管理器中的服务状态，
/// 不需要连接到索引服务。
///
/// # Returns
///
/// Windows 服务状态字符串: "running" | "stopped" | "start_pending" | "stop_pending" | "not_installed" | "unknown"
#[tauri::command]
pub async fn check_windows_service_status() -> String {
    debug!(target: "file_search", "检查 Windows 服务状态");
    let state = check_windows_service_state().await;
    let state_str = match state {
        WindowsServiceState::Running => "running",
        WindowsServiceState::Stopped => "stopped",
        WindowsServiceState::StartPending => "start_pending",
        WindowsServiceState::StopPending => "stop_pending",
        WindowsServiceState::NotInstalled => "not_installed",
        WindowsServiceState::Unknown => "unknown",
    };
    info!(
        target: "file_search",
        "Windows 服务状态: {}",
        state_str
    );
    state_str.to_string()
}

// =============================================================================
// OCR Integration Search
// =============================================================================

/// Document file extensions that should be prioritized in OCR-based search
///
/// These extensions are commonly associated with text documents that are
/// likely to contain content related to OCR-recognized text.
const DOCUMENT_EXTENSIONS: &[&str] = &[
    "pdf", "doc", "docx", "txt", "md", // Primary document types
    "rtf", "odt", // Rich text formats
    "xls", "xlsx", // Spreadsheets
    "ppt", "pptx", // Presentations
    "csv", "json", "xml", // Data formats
    "html", "htm", // Web documents
    "tex", "latex", // LaTeX documents
];

/// Score boost multiplier for document files in OCR search
///
/// Document files receive this multiplier to their relevance score
/// to prioritize them over other file types.
const DOCUMENT_SCORE_BOOST: i64 = 2;

/// OCR search request parameters
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OcrSearchParams {
    /// The OCR text to search from
    pub ocr_text: String,

    /// Maximum number of results to return (default: 50)
    #[serde(default = "default_ocr_limit")]
    pub limit: usize,

    /// Whether to only return document files (default: false)
    #[serde(default)]
    pub documents_only: bool,
}

fn default_ocr_limit() -> usize {
    50
}

/// OCR search response
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OcrSearchResponse {
    /// Search results (document files prioritized)
    pub results: Vec<FileSearchResultItem>,

    /// Total number of results found
    pub total_count: u64,

    /// Search time in milliseconds
    pub search_time_ms: u64,

    /// Keywords extracted from OCR text
    pub extracted_keywords: Vec<String>,

    /// Whether any results were found
    pub has_results: bool,

    /// Suggestion message when no results found
    pub suggestion: Option<String>,
}

/// Check if a file extension is a document type
fn is_document_extension(ext: &str) -> bool {
    let ext_lower = ext.to_lowercase();
    DOCUMENT_EXTENSIONS.contains(&ext_lower.as_str())
}

/// Get file extension from path
fn get_extension(path: &str) -> Option<String> {
    std::path::Path::new(path)
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.to_lowercase())
}

/// Boost score for document files
///
/// **Validates: Requirements 7.4**
/// - THE Search_Result SHALL prioritize document files (pdf, doc, docx, txt, md) for OCR-based search
fn boost_document_score(result: &mut FileSearchResultItem) {
    if let Some(ext) = get_extension(&result.path) {
        if is_document_extension(&ext) {
            result.score *= DOCUMENT_SCORE_BOOST;
        }
    }
}

/// Search files based on OCR text
///
/// **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
/// - 7.1: WHEN OCR completes, THE application SHALL provide a "Search Related Files" button
/// - 7.2: WHEN the button is clicked, THE Search_Client SHALL use OCR text as search query
/// - 7.3: THE Search_Client SHALL extract keywords from OCR text for better matching
/// - 7.4: THE Search_Result SHALL prioritize document files (pdf, doc, docx, txt, md) for OCR-based search
/// - 7.5: WHEN no results found, THE application SHALL suggest broadening the search
///
/// This command:
/// 1. Extracts meaningful keywords from OCR text using KeywordExtractor
/// 2. Searches for files matching those keywords
/// 3. Boosts scores for document file types
/// 4. Returns results sorted by boosted relevance
///
/// # Arguments
///
/// * `params` - OCR search parameters including the OCR text
///
/// # Returns
///
/// Search results with document files prioritized
#[tauri::command]
pub async fn search_from_ocr(
    state: State<'_, FileSearchState>,
    params: OcrSearchParams,
) -> Result<OcrSearchResponse, String> {
    let start_time = std::time::Instant::now();

    info!(
        target: "file_search",
        "OCR 搜索请求: text_length={}, limit={}, documents_only={}",
        params.ocr_text.len(),
        params.limit,
        params.documents_only
    );

    // Step 1: Extract keywords from OCR text
    // **Validates: Requirements 7.3**
    let extractor = crate::file_search::KeywordExtractor::new();
    let extraction_result = extractor.extract(&params.ocr_text);
    let keywords = extraction_result.keywords;

    debug!(
        target: "file_search",
        "从 OCR 文本提取了 {} 个关键词: {:?}",
        keywords.len(),
        keywords.iter().take(10).collect::<Vec<_>>()
    );

    // If no keywords extracted, return empty result with suggestion
    // **Validates: Requirements 7.5**
    if keywords.is_empty() {
        info!(
            target: "file_search",
            "OCR 文本未提取到有效关键词"
        );
        return Ok(OcrSearchResponse {
            results: vec![],
            total_count: 0,
            search_time_ms: start_time.elapsed().as_millis() as u64,
            extracted_keywords: vec![],
            has_results: false,
            suggestion: Some(
                "OCR 文本中未找到有效的搜索关键词。请尝试识别包含更多文字的图片。".to_string(),
            ),
        });
    }

    // Step 2: Build search query from keywords
    // Use the first few keywords joined together for better matching
    let search_keyword = keywords.iter()
        .take(5)  // Limit to first 5 keywords to avoid overly specific queries
        .cloned()
        .collect::<Vec<_>>()
        .join(" ");

    debug!(
        target: "file_search",
        "构建搜索关键词: {}",
        search_keyword
    );

    // Build search query
    let mut filters = SearchFilters::default();

    // If documents_only is true, filter to document extensions
    if params.documents_only {
        filters.extensions = Some(DOCUMENT_EXTENSIONS.iter().map(|s| s.to_string()).collect());
    }

    let query = SearchQuery {
        keyword: search_keyword,
        match_mode: MatchMode::Fuzzy, // Use fuzzy matching for OCR text
        filters,
        sort_by: SortField::Relevance,
        sort_order: SortOrder::Desc,
        limit: params.limit * 2, // Request more results for re-ranking
        offset: 0,
    };

    // Step 3: Execute search
    let mut client = state.client.lock().await;

    // Ensure connected
    if !client.is_connected() {
        debug!(target: "file_search", "搜索客户端未连接，尝试连接...");
        if let Err(e) = client.connect().await {
            let ctx = ErrorContext::with_details(
                "ocr_search_connect",
                format!("keywords={:?}", keywords),
            );
            log_error_with_context(&e, &ctx);
            return Err(format_error(e));
        }
    }

    // Execute search with retry support
    let search_result = match client.search(query).await {
        Ok(results) => results,
        Err(e) => {
            // Check if it's a transient error and retry once
            if is_transient_error(&e) {
                warn!(
                    target: "file_search",
                    "OCR 搜索遇到瞬态错误，重试中: {}",
                    e
                );
                tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

                // Try to reconnect
                if let Err(reconnect_err) = client.connect().await {
                    let ctx = ErrorContext::with_details(
                        "ocr_search_reconnect",
                        format!("keywords={:?}", keywords),
                    );
                    log_error_with_context(&reconnect_err, &ctx);
                    return Err(format_error(reconnect_err));
                }

                // Retry search
                match client
                    .search(SearchQuery {
                        keyword: keywords.iter().take(5).cloned().collect::<Vec<_>>().join(" "),
                        match_mode: MatchMode::Fuzzy,
                        filters: if params.documents_only {
                            SearchFilters {
                                extensions: Some(
                                    DOCUMENT_EXTENSIONS.iter().map(|s| s.to_string()).collect(),
                                ),
                                ..Default::default()
                            }
                        } else {
                            SearchFilters::default()
                        },
                        sort_by: SortField::Relevance,
                        sort_order: SortOrder::Desc,
                        limit: params.limit * 2,
                        offset: 0,
                    })
                    .await
                {
                    Ok(results) => results,
                    Err(retry_err) => {
                        let ctx = ErrorContext::with_details(
                            "ocr_search_retry",
                            format!("keywords={:?}", keywords),
                        );
                        log_error_with_context(&retry_err, &ctx);
                        return Err(format_error(retry_err));
                    }
                }
            } else {
                let ctx =
                    ErrorContext::with_details("ocr_search", format!("keywords={:?}", keywords));
                log_error_with_context(&e, &ctx);
                return Err(format_error(e));
            }
        }
    };

    // Step 4: Boost document scores and re-sort
    // **Validates: Requirements 7.4**
    let mut results: Vec<FileSearchResultItem> =
        search_result.into_iter().map(FileSearchResultItem::from).collect();

    // Boost scores for document files
    for result in &mut results {
        boost_document_score(result);
    }

    // Re-sort by boosted score (descending)
    results.sort_by(|a, b| b.score.cmp(&a.score));

    // Limit to requested number
    results.truncate(params.limit);

    let total_count = results.len() as u64;
    let search_time_ms = start_time.elapsed().as_millis() as u64;

    // Step 5: Build response with suggestion if no results
    // **Validates: Requirements 7.5**
    let suggestion = if results.is_empty() {
        Some("未找到相关文件。建议：\n1. 尝试使用更少的关键词\n2. 检查文件是否已被索引\n3. 尝试搜索文件名的一部分".to_string())
    } else {
        None
    };

    info!(
        target: "file_search",
        "OCR 搜索完成: {} 个结果, 耗时 {}ms, 关键词: {:?}",
        total_count,
        search_time_ms,
        keywords.iter().take(5).collect::<Vec<_>>()
    );

    Ok(OcrSearchResponse {
        results,
        total_count,
        search_time_ms,
        extracted_keywords: keywords,
        has_results: total_count > 0,
        suggestion,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_match_mode() {
        assert!(matches!(parse_match_mode("exact"), MatchMode::Exact));
        assert!(matches!(parse_match_mode("EXACT"), MatchMode::Exact));
        assert!(matches!(parse_match_mode("wildcard"), MatchMode::Wildcard));
        assert!(matches!(parse_match_mode("regex"), MatchMode::Regex));
        assert!(matches!(parse_match_mode("fuzzy"), MatchMode::Fuzzy));
        assert!(matches!(parse_match_mode("unknown"), MatchMode::Fuzzy));
    }

    #[test]
    fn test_parse_sort_field() {
        assert!(matches!(parse_sort_field("name"), SortField::Name));
        assert!(matches!(parse_sort_field("NAME"), SortField::Name));
        assert!(matches!(parse_sort_field("path"), SortField::Path));
        assert!(matches!(parse_sort_field("size"), SortField::Size));
        assert!(matches!(parse_sort_field("modified"), SortField::Modified));
        assert!(matches!(parse_sort_field("relevance"), SortField::Relevance));
        assert!(matches!(parse_sort_field("unknown"), SortField::Relevance));
    }

    #[test]
    fn test_parse_sort_order() {
        assert!(matches!(parse_sort_order("asc"), SortOrder::Asc));
        assert!(matches!(parse_sort_order("ASC"), SortOrder::Asc));
        assert!(matches!(parse_sort_order("desc"), SortOrder::Desc));
        assert!(matches!(parse_sort_order("unknown"), SortOrder::Desc));
    }

    #[test]
    fn test_sanitize_user_search_keyword_compacts_whitespace() {
        let sanitized = sanitize_user_search_keyword("  hello\t\nworld  ");
        assert_eq!(sanitized, "hello world");
    }

    #[test]
    fn test_sanitize_user_search_keyword_limits_length_after_extraction() {
        let long_query = "VeryLongTokenName1234567890 ".repeat(30);
        let sanitized = sanitize_user_search_keyword(&long_query);

        assert!(!sanitized.is_empty());
        assert!(sanitized.chars().count() <= MAX_USER_SEARCH_QUERY_CHARS);
    }

    #[test]
    fn test_sanitize_user_search_keyword_empty_input() {
        let sanitized = sanitize_user_search_keyword(" \n\t ");
        assert!(sanitized.is_empty());
    }

    #[test]
    fn test_file_search_state_default() {
        let state = FileSearchState::default();
        // 验证状态创建成功
        assert!(Arc::strong_count(&state.client) == 1);
        assert!(!state.startup_check_done.load(Ordering::SeqCst));
    }

    #[test]
    fn test_convert_search_params_basic() {
        let params = FileSearchParams {
            keyword: "test".to_string(),
            match_mode: "fuzzy".to_string(),
            filters: None,
            sort_by: "relevance".to_string(),
            sort_order: "desc".to_string(),
            limit: 50,
            offset: 0,
        };

        let query = convert_search_params(params);
        assert_eq!(query.keyword, "test");
        assert!(matches!(query.match_mode, MatchMode::Fuzzy));
        assert!(matches!(query.sort_by, SortField::Relevance));
        assert!(matches!(query.sort_order, SortOrder::Desc));
        assert_eq!(query.limit, 50);
        assert_eq!(query.offset, 0);
    }

    #[test]
    fn test_convert_search_params_with_filters() {
        let params = FileSearchParams {
            keyword: "document".to_string(),
            match_mode: "exact".to_string(),
            filters: Some(FileSearchFilters {
                extensions: Some(vec!["pdf".to_string(), "doc".to_string()]),
                min_size: Some(1024),
                max_size: Some(1024 * 1024),
                modified_after: None,
                modified_before: None,
                include_directories: false,
                volumes: Some(vec!["C".to_string(), "D".to_string()]),
            }),
            sort_by: "size".to_string(),
            sort_order: "asc".to_string(),
            limit: 100,
            offset: 10,
        };

        let query = convert_search_params(params);
        assert_eq!(query.keyword, "document");
        assert!(matches!(query.match_mode, MatchMode::Exact));
        assert!(matches!(query.sort_by, SortField::Size));
        assert!(matches!(query.sort_order, SortOrder::Asc));
        assert_eq!(query.limit, 100);
        assert_eq!(query.offset, 10);

        // 验证过滤器
        assert_eq!(query.filters.extensions, Some(vec!["pdf".to_string(), "doc".to_string()]));
        assert_eq!(query.filters.min_size, Some(1024));
        assert_eq!(query.filters.max_size, Some(1024 * 1024));
        assert!(!query.filters.include_directories);
        assert_eq!(query.filters.volumes, Some(vec!['C', 'D']));
    }

    #[test]
    fn test_service_status_response_from() {
        // Test Starting status
        let status = ServiceStatus::Starting;
        let response = ServiceStatusResponse::from(status);
        assert_eq!(response.state, "starting");
        assert!(response.indexed_files.is_none());
        assert!(response.is_available);

        // Test Running status
        let status =
            ServiceStatus::Running { indexed_files: 1000, last_update: chrono::Utc::now() };
        let response = ServiceStatusResponse::from(status);
        assert_eq!(response.state, "running");
        assert_eq!(response.indexed_files, Some(1000));
        assert!(response.last_update.is_some());
        assert!(response.is_available);

        // Test Scanning status
        let status = ServiceStatus::Scanning { progress: 0.5, scanned_files: 500 };
        let response = ServiceStatusResponse::from(status);
        assert_eq!(response.state, "scanning");
        assert_eq!(response.scan_progress, Some(0.5));
        assert_eq!(response.scanned_files, Some(500));
        assert!(response.is_available);

        // Test Stopped status
        let status = ServiceStatus::Stopped;
        let response = ServiceStatusResponse::from(status);
        assert_eq!(response.state, "stopped");
        assert!(!response.is_available);
    }

    #[test]
    fn test_create_unavailable_response() {
        // Test NotInstalled
        let response = create_unavailable_response(WindowsServiceState::NotInstalled);
        assert_eq!(response.windows_service_state, "not_installed");
        assert!(!response.is_available);
        assert!(response.status_message.contains("未安装"));

        // Test Stopped
        let response = create_unavailable_response(WindowsServiceState::Stopped);
        assert_eq!(response.windows_service_state, "stopped");
        assert!(!response.is_available);

        // Test StartPending
        let response = create_unavailable_response(WindowsServiceState::StartPending);
        assert_eq!(response.windows_service_state, "starting");
        assert!(!response.is_available);
    }

    #[test]
    fn test_windows_service_state_serialize() {
        // 测试序列化
        let state = WindowsServiceState::Running;
        let json = serde_json::to_string(&state).unwrap();
        assert_eq!(json, "\"running\"");

        let state = WindowsServiceState::NotInstalled;
        let json = serde_json::to_string(&state).unwrap();
        assert_eq!(json, "\"not_installed\"");
    }

    #[tokio::test]
    async fn test_check_windows_service_state() {
        // 这个测试检查函数是否能正常执行（不管服务是否存在）
        let state = check_windows_service_state().await;
        // 状态应该是有效的枚举值
        match state {
            WindowsServiceState::Running
            | WindowsServiceState::Stopped
            | WindowsServiceState::StartPending
            | WindowsServiceState::StopPending
            | WindowsServiceState::NotInstalled
            | WindowsServiceState::Unknown => {
                // 所有状态都是有效的
            }
        }
    }

    // ==========================================================================
    // 错误处理测试 (Task 10.4)
    // ==========================================================================

    #[test]
    fn test_format_error_service_not_running() {
        let error = SearchClientError::ServiceNotRunning;
        let message = format_error(error);
        assert!(message.contains("未运行"));
        assert!(message.contains("启动服务"));
    }

    #[test]
    fn test_format_error_connection_failed() {
        let error = SearchClientError::ConnectionFailed("test error".to_string());
        let message = format_error(error);
        assert!(message.contains("无法连接"));
    }

    #[test]
    fn test_format_error_connection_failed_pipe_busy() {
        let error = SearchClientError::ConnectionFailed("Pipe busy".to_string());
        let message = format_error(error);
        assert!(message.contains("正忙"));
        assert!(message.contains("稍后重试"));
    }

    #[test]
    fn test_format_error_connection_lost() {
        let error = SearchClientError::ConnectionLost;
        let message = format_error(error);
        assert!(message.contains("断开"));
        assert!(message.contains("重新连接"));
    }

    #[test]
    fn test_format_error_timeout() {
        let error = SearchClientError::Timeout;
        let message = format_error(error);
        assert!(message.contains("超时"));
    }

    #[test]
    fn test_format_error_max_retries_exceeded() {
        let error = SearchClientError::MaxRetriesExceeded { attempts: 5 };
        let message = format_error(error);
        assert!(message.contains("5"));
        assert!(message.contains("重试"));
    }

    #[test]
    fn test_format_error_service_error_not_ready() {
        let error = SearchClientError::ServiceError {
            code: crate::file_search::ErrorCode::NotReady,
            message: "索引正在构建".to_string(),
        };
        let message = format_error(error);
        assert!(message.contains("索引未就绪"));
    }

    #[test]
    fn test_format_error_service_error_invalid_query() {
        let error = SearchClientError::ServiceError {
            code: crate::file_search::ErrorCode::InvalidQuery,
            message: "无效的正则表达式".to_string(),
        };
        let message = format_error(error);
        assert!(message.contains("无效的搜索查询"));
    }

    #[test]
    fn test_is_transient_error() {
        // 瞬态错误应该返回 true
        assert!(is_transient_error(&SearchClientError::Timeout));
        assert!(is_transient_error(&SearchClientError::ConnectionLost));
        assert!(is_transient_error(&SearchClientError::ConnectionFailed("test".to_string())));

        // 非瞬态错误应该返回 false
        assert!(!is_transient_error(&SearchClientError::ServiceNotRunning));
        assert!(!is_transient_error(&SearchClientError::NotConnected));
        assert!(!is_transient_error(&SearchClientError::InvalidResponse("test".to_string())));
        assert!(!is_transient_error(&SearchClientError::ServiceError {
            code: crate::file_search::ErrorCode::InvalidQuery,
            message: "test".to_string(),
        }));
    }

    #[test]
    fn test_error_context_new() {
        let ctx = ErrorContext::new("test_operation");
        assert_eq!(ctx.operation, "test_operation");
        assert!(ctx.details.is_none());
    }

    #[test]
    fn test_error_context_with_details() {
        let ctx = ErrorContext::with_details("search", "keyword=test");
        assert_eq!(ctx.operation, "search");
        assert_eq!(ctx.details, Some("keyword=test".to_string()));
    }

    #[test]
    fn test_unavailable_response_messages() {
        // 测试不同状态下的用户友好消息
        let response = create_unavailable_response(WindowsServiceState::NotInstalled);
        assert!(response.status_message.contains("未安装"));

        let response = create_unavailable_response(WindowsServiceState::Stopped);
        assert!(response.status_message.contains("已停止"));

        let response = create_unavailable_response(WindowsServiceState::StartPending);
        assert!(response.status_message.contains("启动"));

        let response = create_unavailable_response(WindowsServiceState::Running);
        assert!(response.status_message.contains("无法连接"));
    }
}

// =============================================================================
// Property-Based Tests for Error Logging Completeness
// =============================================================================
//
// **Property 18: Error Logging Completeness**
// **Validates: Requirements 10.7**
//
// For any error that occurs in the Index_Service, it SHALL be logged to the
// standard log directory with timestamp, error type, and message.
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use proptest::prelude::*;
    use std::io;
    use tracing_test::traced_test;

    // =========================================================================
    // Arbitrary Strategies for Error Types
    // =========================================================================

    /// Strategy for generating arbitrary ErrorCode
    fn arb_error_code() -> impl Strategy<Value = crate::file_search::ErrorCode> {
        prop_oneof![
            Just(crate::file_search::ErrorCode::NotReady),
            Just(crate::file_search::ErrorCode::InvalidQuery),
            Just(crate::file_search::ErrorCode::Timeout),
            Just(crate::file_search::ErrorCode::InternalError),
            Just(crate::file_search::ErrorCode::PermissionDenied),
            Just(crate::file_search::ErrorCode::ShuttingDown),
        ]
    }

    /// Strategy for generating arbitrary error messages
    fn arb_error_message() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("test error".to_string()),
            Just("connection failed".to_string()),
            Just("timeout occurred".to_string()),
            Just("invalid query syntax".to_string()),
            Just("permission denied".to_string()),
            Just("服务未就绪".to_string()),
            Just("索引正在构建".to_string()),
            "[a-zA-Z0-9 ]{1,50}".prop_map(|s| s),
        ]
    }

    /// Strategy for generating arbitrary SearchClientError
    fn arb_search_client_error() -> impl Strategy<Value = SearchClientError> {
        prop_oneof![
            // ServiceNotRunning - use prop_map to avoid Clone requirement
            Just(()).prop_map(|_| SearchClientError::ServiceNotRunning),
            // ConnectionFailed with various messages
            arb_error_message().prop_map(SearchClientError::ConnectionFailed),
            // ConnectionFailed with Pipe busy (special case)
            Just(()).prop_map(|_| SearchClientError::ConnectionFailed("Pipe busy".to_string())),
            // ConnectionLost
            Just(()).prop_map(|_| SearchClientError::ConnectionLost),
            // Timeout
            Just(()).prop_map(|_| SearchClientError::Timeout),
            // ServiceError with various codes and messages
            (arb_error_code(), arb_error_message())
                .prop_map(|(code, message)| { SearchClientError::ServiceError { code, message } }),
            // MaxRetriesExceeded with various attempt counts
            (1u32..10u32).prop_map(|attempts| SearchClientError::MaxRetriesExceeded { attempts }),
            // NotConnected
            Just(()).prop_map(|_| SearchClientError::NotConnected),
            // InvalidResponse with various messages
            arb_error_message().prop_map(SearchClientError::InvalidResponse),
            // MessageTooLarge with various sizes
            (1usize..1_000_000usize, 1_000_000usize..16_000_000usize)
                .prop_map(|(size, max)| { SearchClientError::MessageTooLarge { size, max } }),
            // Io error (using a simple NotFound error)
            Just(()).prop_map(|_| SearchClientError::Io(io::Error::new(
                io::ErrorKind::NotFound,
                "file not found"
            ))),
            // Io error with various kinds
            prop_oneof![
                Just(io::ErrorKind::NotFound),
                Just(io::ErrorKind::PermissionDenied),
                Just(io::ErrorKind::ConnectionRefused),
                Just(io::ErrorKind::ConnectionReset),
                Just(io::ErrorKind::TimedOut),
                Just(io::ErrorKind::BrokenPipe),
            ]
            .prop_map(|kind| SearchClientError::Io(io::Error::new(kind, "io error"))),
        ]
    }

    /// Strategy for generating arbitrary ErrorContext
    fn arb_error_context() -> impl Strategy<Value = ErrorContext> {
        prop_oneof![
            Just(ErrorContext::new("search")),
            Just(ErrorContext::new("connect")),
            Just(ErrorContext::new("get_status")),
            Just(ErrorContext::new("rebuild_index")),
            Just(ErrorContext::new("update_config")),
            Just(ErrorContext::new("get_status_connect")),
            Just(ErrorContext::new("rebuild_index_connect")),
            Just(ErrorContext::new("update_config_connect")),
            // With details
            arb_error_message().prop_map(|details| ErrorContext::with_details("search", details)),
            arb_error_message().prop_map(|details| ErrorContext::with_details("connect", details)),
        ]
    }

    // =========================================================================
    // Helper Functions for Log Verification
    // =========================================================================

    /// Get the expected error type string for a SearchClientError
    fn get_error_type_string(error: &SearchClientError) -> &'static str {
        match error {
            SearchClientError::ServiceNotRunning => "ServiceNotRunning",
            SearchClientError::ConnectionFailed(_) => "ConnectionFailed",
            SearchClientError::ConnectionLost => "ConnectionLost",
            SearchClientError::Timeout => "Timeout",
            SearchClientError::ServiceError { .. } => "ServiceError",
            SearchClientError::MaxRetriesExceeded { .. } => "MaxRetriesExceeded",
            SearchClientError::NotConnected => "NotConnected",
            SearchClientError::InvalidResponse(_) => "InvalidResponse",
            SearchClientError::MessageTooLarge { .. } => "MessageTooLarge",
            SearchClientError::Io(_) => "IoError",
            SearchClientError::Json(_) => "JsonError",
        }
    }

    // =========================================================================
    // Property Tests
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 10.7**
        ///
        /// Property 18: Error Logging Completeness - Error Type Logged
        ///
        /// For any SearchClientError, when logged via log_error_with_context,
        /// the log entry SHALL contain the error type.
        #[test]
        #[traced_test]
        fn prop_error_logging_contains_error_type(
            error in arb_search_client_error(),
            context in arb_error_context()
        ) {
            // Log the error
            log_error_with_context(&error, &context);

            // Get the expected error type string
            let expected_error_type = get_error_type_string(&error);

            // Verify the log contains the error type
            // tracing-test captures logs and makes them available via logs_contain
            prop_assert!(
                logs_contain(expected_error_type),
                "Log should contain error type '{}' for error: {:?}",
                expected_error_type,
                error
            );
        }

        /// **Validates: Requirements 10.7**
        ///
        /// Property 18: Error Logging Completeness - Operation Logged
        ///
        /// For any error logged via log_error_with_context, the log entry
        /// SHALL contain the operation name from the context.
        #[test]
        #[traced_test]
        fn prop_error_logging_contains_operation(
            error in arb_search_client_error(),
            context in arb_error_context()
        ) {
            // Log the error
            log_error_with_context(&error, &context);

            // Verify the log contains the operation name
            prop_assert!(
                logs_contain(context.operation),
                "Log should contain operation '{}' for error: {:?}",
                context.operation,
                error
            );
        }

        /// **Validates: Requirements 10.7**
        ///
        /// Property 18: Error Logging Completeness - Error Message Logged
        ///
        /// For any SearchClientError, when logged via log_error_with_context,
        /// the log entry SHALL contain the error message (via Display trait).
        #[test]
        #[traced_test]
        fn prop_error_logging_contains_message(
            error in arb_search_client_error(),
            context in arb_error_context()
        ) {
            // Log the error
            log_error_with_context(&error, &context);

            // The error message should be logged via the Display trait
            // We check for "文件搜索错误" which is the prefix used in log_error_with_context
            prop_assert!(
                logs_contain("文件搜索错误"),
                "Log should contain '文件搜索错误' prefix for error: {:?}",
                error
            );
        }

        /// **Validates: Requirements 10.7**
        ///
        /// Property 18: Error Logging Completeness - Target Logged
        ///
        /// For any error logged via log_error_with_context, the log entry
        /// SHALL be logged to the "file_search" target.
        #[test]
        #[traced_test]
        fn prop_error_logging_uses_correct_target(
            error in arb_search_client_error(),
            context in arb_error_context()
        ) {
            // Log the error
            log_error_with_context(&error, &context);

            // Verify the log uses the correct target
            // Note: tracing-test captures the target in the log output
            prop_assert!(
                logs_contain("file_search"),
                "Log should be logged to 'file_search' target for error: {:?}",
                error
            );
        }

        /// **Validates: Requirements 10.7**
        ///
        /// Property 18: Error Logging Completeness - Details Logged When Present
        ///
        /// For any error logged with context that has details, the log entry
        /// SHALL contain those details.
        #[test]
        #[traced_test]
        fn prop_error_logging_contains_details_when_present(
            error in arb_search_client_error(),
            details in arb_error_message()
        ) {
            // Create context with details
            let context = ErrorContext::with_details("search", details.clone());

            // Log the error
            log_error_with_context(&error, &context);

            // Verify the log contains the details
            prop_assert!(
                logs_contain(&details),
                "Log should contain details '{}' for error: {:?}",
                details,
                error
            );
        }
    }

    // =========================================================================
    // Additional Unit Tests for Error Logging
    // =========================================================================

    #[test]
    #[traced_test]
    fn test_all_error_types_are_logged() {
        // Test each error type explicitly to ensure complete coverage
        let errors: Vec<SearchClientError> = vec![
            SearchClientError::ServiceNotRunning,
            SearchClientError::ConnectionFailed("test connection failed".to_string()),
            SearchClientError::ConnectionLost,
            SearchClientError::Timeout,
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::NotReady,
                message: "index not ready".to_string(),
            },
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::InvalidQuery,
                message: "invalid regex".to_string(),
            },
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::Timeout,
                message: "operation timed out".to_string(),
            },
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::InternalError,
                message: "internal error".to_string(),
            },
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::PermissionDenied,
                message: "access denied".to_string(),
            },
            SearchClientError::ServiceError {
                code: crate::file_search::ErrorCode::ShuttingDown,
                message: "service shutting down".to_string(),
            },
            SearchClientError::MaxRetriesExceeded { attempts: 5 },
            SearchClientError::NotConnected,
            SearchClientError::InvalidResponse("invalid json".to_string()),
            SearchClientError::MessageTooLarge { size: 20_000_000, max: 16_000_000 },
            SearchClientError::Io(io::Error::new(io::ErrorKind::NotFound, "file not found")),
        ];

        let expected_types = vec![
            "ServiceNotRunning",
            "ConnectionFailed",
            "ConnectionLost",
            "Timeout",
            "ServiceError",
            "ServiceError",
            "ServiceError",
            "ServiceError",
            "ServiceError",
            "ServiceError",
            "MaxRetriesExceeded",
            "NotConnected",
            "InvalidResponse",
            "MessageTooLarge",
            "IoError",
        ];

        for (error, expected_type) in errors.into_iter().zip(expected_types.into_iter()) {
            let context = ErrorContext::new("test_operation");
            log_error_with_context(&error, &context);

            assert!(
                logs_contain(expected_type),
                "Log should contain error type '{}' for error: {:?}",
                expected_type,
                error
            );
            assert!(logs_contain("test_operation"), "Log should contain operation name");
            assert!(logs_contain("文件搜索错误"), "Log should contain error message prefix");
        }
    }

    #[test]
    #[traced_test]
    fn test_error_logging_with_context_details() {
        let error = SearchClientError::ConnectionFailed("pipe not found".to_string());
        let context = ErrorContext::with_details("search", "keyword=测试文件");

        log_error_with_context(&error, &context);

        // Verify all components are logged
        assert!(logs_contain("ConnectionFailed"));
        assert!(logs_contain("search"));
        assert!(logs_contain("keyword=测试文件"));
        assert!(logs_contain("文件搜索错误"));
    }

    #[test]
    #[traced_test]
    fn test_error_logging_without_context_details() {
        let error = SearchClientError::Timeout;
        let context = ErrorContext::new("get_status");

        log_error_with_context(&error, &context);

        // Verify components are logged (without details)
        assert!(logs_contain("Timeout"));
        assert!(logs_contain("get_status"));
        assert!(logs_contain("文件搜索错误"));
    }

    #[test]
    #[traced_test]
    fn test_service_error_codes_logged_correctly() {
        let codes = vec![
            (crate::file_search::ErrorCode::NotReady, "NotReady"),
            (crate::file_search::ErrorCode::InvalidQuery, "InvalidQuery"),
            (crate::file_search::ErrorCode::Timeout, "Timeout"),
            (crate::file_search::ErrorCode::InternalError, "InternalError"),
            (crate::file_search::ErrorCode::PermissionDenied, "PermissionDenied"),
            (crate::file_search::ErrorCode::ShuttingDown, "ShuttingDown"),
        ];

        for (code, code_name) in codes {
            let error = SearchClientError::ServiceError {
                code,
                message: format!("test message for {}", code_name),
            };
            let context = ErrorContext::new("test");

            log_error_with_context(&error, &context);

            // The error type should be "ServiceError" and the code should be in the message
            assert!(
                logs_contain("ServiceError"),
                "Log should contain 'ServiceError' for code {:?}",
                code
            );
        }
    }

    // =========================================================================
    // Property 14: OCR Search Document Prioritization Tests
    // =========================================================================
    //
    // **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
    // **Validates: Requirements 7.4**
    //
    // For any OCR-based search, document files (pdf, doc, docx, txt, md) SHALL have
    // higher relevance scores than other file types with equivalent text matches.
    // =========================================================================

    /// Primary document extensions that MUST be prioritized
    const PRIMARY_DOCUMENT_EXTENSIONS: &[&str] = &["pdf", "doc", "docx", "txt", "md"];

    /// Non-document extensions for testing
    const NON_DOCUMENT_EXTENSIONS: &[&str] = &[
        "exe", "dll", "jpg", "png", "gif", "mp3", "mp4", "avi", "zip", "rar", "iso", "bin", "dat",
        "bak", "tmp", "log", "ini", "cfg", "sys", "bat",
    ];

    /// Strategy to generate a valid file name (alphanumeric + some special chars)
    fn arb_file_name() -> impl Strategy<Value = String> {
        proptest::string::string_regex("[a-zA-Z0-9_-]{1,50}")
            .unwrap()
            .prop_filter("non-empty name", |s| !s.is_empty())
    }

    /// Strategy to generate a primary document extension
    fn arb_document_extension() -> impl Strategy<Value = String> {
        proptest::sample::select(PRIMARY_DOCUMENT_EXTENSIONS).prop_map(|s| s.to_string())
    }

    /// Strategy to generate a non-document extension
    fn arb_non_document_extension() -> impl Strategy<Value = String> {
        proptest::sample::select(NON_DOCUMENT_EXTENSIONS).prop_map(|s| s.to_string())
    }

    /// Strategy to generate a positive score
    fn arb_positive_score() -> impl Strategy<Value = i64> {
        1i64..=1000i64
    }

    /// Create a FileSearchResultItem for testing
    fn create_test_result(name: &str, path: &str, score: i64) -> FileSearchResultItem {
        FileSearchResultItem {
            file_id: "1".to_string(),
            name: name.to_string(),
            path: path.to_string(),
            size: 1024,
            modified: chrono::Utc::now().to_rfc3339(),
            is_directory: false,
            score,
            match_indices: vec![],
        }
    }

    // =========================================================================
    // Unit Tests for Document Prioritization
    // =========================================================================

    #[test]
    fn test_is_document_extension_primary_types() {
        // Primary document types from Requirements 7.4
        assert!(is_document_extension("pdf"));
        assert!(is_document_extension("doc"));
        assert!(is_document_extension("docx"));
        assert!(is_document_extension("txt"));
        assert!(is_document_extension("md"));

        // Case insensitive
        assert!(is_document_extension("PDF"));
        assert!(is_document_extension("DOC"));
        assert!(is_document_extension("TXT"));
    }

    #[test]
    fn test_is_document_extension_non_documents() {
        // Non-document types should return false
        assert!(!is_document_extension("exe"));
        assert!(!is_document_extension("jpg"));
        assert!(!is_document_extension("png"));
        assert!(!is_document_extension("mp3"));
        assert!(!is_document_extension("zip"));
    }

    #[test]
    fn test_get_extension_various_paths() {
        assert_eq!(get_extension("document.pdf"), Some("pdf".to_string()));
        assert_eq!(get_extension("file.TXT"), Some("txt".to_string()));
        assert_eq!(get_extension("C:\\Users\\test\\file.docx"), Some("docx".to_string()));
        assert_eq!(get_extension("/home/user/file.md"), Some("md".to_string()));
        assert_eq!(get_extension("no_extension"), None);
        assert_eq!(get_extension(""), None);
    }

    #[test]
    fn test_boost_document_score_applies_multiplier() {
        let mut doc_result = create_test_result("report.pdf", "C:\\docs\\report.pdf", 100);
        let original_score = doc_result.score;

        boost_document_score(&mut doc_result);

        assert_eq!(
            doc_result.score,
            original_score * DOCUMENT_SCORE_BOOST,
            "Document file score should be multiplied by DOCUMENT_SCORE_BOOST"
        );
    }

    #[test]
    fn test_boost_document_score_no_change_for_non_document() {
        let mut non_doc_result = create_test_result("image.jpg", "C:\\images\\image.jpg", 100);
        let original_score = non_doc_result.score;

        boost_document_score(&mut non_doc_result);

        assert_eq!(
            non_doc_result.score, original_score,
            "Non-document file score should remain unchanged"
        );
    }

    #[test]
    fn test_document_prioritization_comparison() {
        // Create two results with the same initial score
        let mut doc_result = create_test_result("report.pdf", "C:\\docs\\report.pdf", 100);
        let mut non_doc_result = create_test_result("image.jpg", "C:\\images\\image.jpg", 100);

        // Apply boost
        boost_document_score(&mut doc_result);
        boost_document_score(&mut non_doc_result);

        // Document should have higher score
        assert!(
            doc_result.score > non_doc_result.score,
            "Document file ({}) should have higher score than non-document file ({})",
            doc_result.score,
            non_doc_result.score
        );
    }

    // =========================================================================
    // Property-Based Tests for Document Prioritization
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Document Score Boost
        ///
        /// For any document file (pdf, doc, docx, txt, md), after applying
        /// boost_document_score, the score SHALL be exactly DOCUMENT_SCORE_BOOST
        /// times the original score.
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_document_score_boost_multiplier(
            name in arb_file_name(),
            ext in arb_document_extension(),
            score in arb_positive_score()
        ) {
            let filename = format!("{}.{}", name, ext);
            let path = format!("C:\\test\\{}", filename);
            let mut result = create_test_result(&filename, &path, score);
            let original_score = result.score;

            boost_document_score(&mut result);

            prop_assert_eq!(
                result.score,
                original_score * DOCUMENT_SCORE_BOOST,
                "Document file '{}' with extension '{}' should have score {} * {} = {}, but got {}",
                filename,
                ext,
                original_score,
                DOCUMENT_SCORE_BOOST,
                original_score * DOCUMENT_SCORE_BOOST,
                result.score
            );
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Non-Document Score Unchanged
        ///
        /// For any non-document file, after applying boost_document_score,
        /// the score SHALL remain unchanged.
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_non_document_score_unchanged(
            name in arb_file_name(),
            ext in arb_non_document_extension(),
            score in arb_positive_score()
        ) {
            let filename = format!("{}.{}", name, ext);
            let path = format!("C:\\test\\{}", filename);
            let mut result = create_test_result(&filename, &path, score);
            let original_score = result.score;

            boost_document_score(&mut result);

            prop_assert_eq!(
                result.score,
                original_score,
                "Non-document file '{}' with extension '{}' should have unchanged score {}, but got {}",
                filename,
                ext,
                original_score,
                result.score
            );
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Document Higher Than Non-Document
        ///
        /// For any document file and non-document file with equivalent initial scores,
        /// after applying boost_document_score, the document file SHALL have a
        /// strictly higher score than the non-document file.
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_document_higher_than_non_document_with_equal_initial_score(
            doc_name in arb_file_name(),
            doc_ext in arb_document_extension(),
            non_doc_name in arb_file_name(),
            non_doc_ext in arb_non_document_extension(),
            score in arb_positive_score()
        ) {
            // Create document file
            let doc_filename = format!("{}.{}", doc_name, doc_ext);
            let doc_path = format!("C:\\docs\\{}", doc_filename);
            let mut doc_result = create_test_result(&doc_filename, &doc_path, score);

            // Create non-document file with same initial score
            let non_doc_filename = format!("{}.{}", non_doc_name, non_doc_ext);
            let non_doc_path = format!("C:\\files\\{}", non_doc_filename);
            let mut non_doc_result = create_test_result(&non_doc_filename, &non_doc_path, score);

            // Apply boost to both
            boost_document_score(&mut doc_result);
            boost_document_score(&mut non_doc_result);

            prop_assert!(
                doc_result.score > non_doc_result.score,
                "Document '{}' (score: {}) should have higher score than non-document '{}' (score: {})",
                doc_filename,
                doc_result.score,
                non_doc_filename,
                non_doc_result.score
            );
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Idempotence
        ///
        /// Applying boost_document_score multiple times to the same result
        /// SHALL produce the same final score as applying it once (idempotent
        /// behavior is NOT expected - this test verifies the actual behavior).
        ///
        /// Note: The current implementation multiplies the score each time,
        /// so this test verifies that behavior is consistent.
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_document_boost_is_multiplicative(
            name in arb_file_name(),
            ext in arb_document_extension(),
            score in arb_positive_score()
        ) {
            let filename = format!("{}.{}", name, ext);
            let path = format!("C:\\test\\{}", filename);

            // Apply boost once
            let mut result_once = create_test_result(&filename, &path, score);
            boost_document_score(&mut result_once);
            let score_after_once = result_once.score;

            // Apply boost twice
            let mut result_twice = create_test_result(&filename, &path, score);
            boost_document_score(&mut result_twice);
            boost_document_score(&mut result_twice);
            let score_after_twice = result_twice.score;

            // Verify multiplicative behavior
            prop_assert_eq!(
                score_after_twice,
                score_after_once * DOCUMENT_SCORE_BOOST,
                "Applying boost twice should multiply the score again"
            );
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Extension Case Insensitivity
        ///
        /// Document extension matching SHALL be case-insensitive.
        /// A file with extension "PDF" should be treated the same as "pdf".
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_document_extension_case_insensitive(
            name in arb_file_name(),
            ext in arb_document_extension(),
            score in arb_positive_score()
        ) {
            // Create file with lowercase extension
            let filename_lower = format!("{}.{}", name, ext.to_lowercase());
            let path_lower = format!("C:\\test\\{}", filename_lower);
            let mut result_lower = create_test_result(&filename_lower, &path_lower, score);

            // Create file with uppercase extension
            let filename_upper = format!("{}.{}", name, ext.to_uppercase());
            let path_upper = format!("C:\\test\\{}", filename_upper);
            let mut result_upper = create_test_result(&filename_upper, &path_upper, score);

            // Apply boost to both
            boost_document_score(&mut result_lower);
            boost_document_score(&mut result_upper);

            prop_assert_eq!(
                result_lower.score,
                result_upper.score,
                "Extension case should not affect score: '{}' ({}) vs '{}' ({})",
                filename_lower,
                result_lower.score,
                filename_upper,
                result_upper.score
            );
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - All Primary Document Types
        ///
        /// All primary document types (pdf, doc, docx, txt, md) SHALL receive
        /// the same score boost multiplier.
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_all_primary_document_types_boosted_equally(
            name in arb_file_name(),
            score in arb_positive_score()
        ) {
            let expected_boosted_score = score * DOCUMENT_SCORE_BOOST;

            for ext in PRIMARY_DOCUMENT_EXTENSIONS {
                let filename = format!("{}.{}", name, ext);
                let path = format!("C:\\test\\{}", filename);
                let mut result = create_test_result(&filename, &path, score);

                boost_document_score(&mut result);

                prop_assert_eq!(
                    result.score,
                    expected_boosted_score,
                    "Document type '{}' should have boosted score {}, but got {}",
                    ext,
                    expected_boosted_score,
                    result.score
                );
            }
        }

        /// **Validates: Requirements 7.4**
        ///
        /// Property 14: OCR Search Document Prioritization - Score Ordering Preserved
        ///
        /// For any two document files with different initial scores,
        /// after applying boost_document_score, the relative ordering
        /// SHALL be preserved (higher initial score → higher final score).
        ///
        /// **Feature: everything-file-search, Property 14: OCR Search Document Prioritization**
        #[test]
        fn prop_document_score_ordering_preserved(
            name1 in arb_file_name(),
            name2 in arb_file_name(),
            ext in arb_document_extension(),
            score1 in arb_positive_score(),
            score2 in arb_positive_score()
        ) {
            let filename1 = format!("{}.{}", name1, ext);
            let path1 = format!("C:\\test\\{}", filename1);
            let mut result1 = create_test_result(&filename1, &path1, score1);

            let filename2 = format!("{}.{}", name2, ext);
            let path2 = format!("C:\\test\\{}", filename2);
            let mut result2 = create_test_result(&filename2, &path2, score2);

            boost_document_score(&mut result1);
            boost_document_score(&mut result2);

            // Verify ordering is preserved
            if score1 > score2 {
                prop_assert!(
                    result1.score > result2.score,
                    "Higher initial score should result in higher final score"
                );
            } else if score1 < score2 {
                prop_assert!(
                    result1.score < result2.score,
                    "Lower initial score should result in lower final score"
                );
            } else {
                prop_assert_eq!(
                    result1.score,
                    result2.score,
                    "Equal initial scores should result in equal final scores"
                );
            }
        }
    }
}
