//! 历史记录相关 Tauri 命令
//!
//! 封装历史记录数据库操作，暴露给前端调用。

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tauri::State;
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

use crate::database::history::{
    HistoryDatabase, HistoryStats, ScreenshotRecord, ScreenshotRecordUpdate, SearchParams,
};
use crate::error::{HuGeError, HuGeResult};

/// 历史记录数据库状态
#[derive(Clone)]
pub struct HistoryState {
    pub db: Arc<Mutex<Option<HistoryDatabase>>>,
}

impl HistoryState {
    pub fn new() -> Self {
        Self { db: Arc::new(Mutex::new(None)) }
    }

    /// 初始化数据库
    pub async fn init(&self, db_path: &str) -> HuGeResult<()> {
        let db = HistoryDatabase::open(db_path)?;
        let mut guard = self.db.lock().await;
        *guard = Some(db);
        info!("历史记录数据库已初始化: {}", db_path);
        Ok(())
    }

    /// 添加记录（供内部模块使用，如剪贴板监听器）
    pub async fn add_record(&self, record: ScreenshotRecord) -> HuGeResult<i64> {
        let db_guard = self.db.lock().await;
        let db = db_guard.as_ref().ok_or_else(|| {
            crate::error::HuGeError::ConfigError("历史记录数据库未初始化".to_string())
        })?;
        db.insert(&record)
    }
}

impl Default for HistoryState {
    fn default() -> Self {
        Self::new()
    }
}

/// 前端历史记录项格式
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HistoryItem {
    pub id: i64,
    pub created_at: String,
    pub file_path: String,
    pub thumbnail_path: Option<String>,
    pub width: u32,
    pub height: u32,
    pub file_size: Option<i64>,
    pub ocr_text: Option<String>,
    pub tags: Vec<String>,
    pub metadata: HistoryMetadata,
    pub content_type: String,
    pub text_content: Option<String>,
    pub is_pinned: bool,
}

/// 历史记录元数据
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HistoryMetadata {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub capture_mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub monitor_id: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub app_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub window_title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub has_annotations: Option<bool>,
}

/// 前端搜索结果格式
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HistorySearchResult {
    pub items: Vec<HistoryItem>,
    pub total: i64,
    pub has_more: bool,
}

/// 新增历史记录参数
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AddHistoryItemParams {
    pub file_path: String,
    pub thumbnail_path: Option<String>,
    pub width: u32,
    pub height: u32,
    pub file_size: Option<i64>,
    pub ocr_text: Option<String>,
    pub tags: Option<Vec<String>>,
    pub metadata: Option<HistoryMetadata>,
    /// 内容类型: "image" 或 "text"（默认 "image"）
    pub content_type: Option<String>,
    /// 文字内容（仅文字类型）
    pub text_content: Option<String>,
}

/// 更新历史记录参数
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateHistoryItemParams {
    pub ocr_text: Option<String>,
    pub tags: Option<Vec<String>>,
    pub metadata: Option<HistoryMetadata>,
}

// ============================================
// 辅助函数
// ============================================

/// 将数据库记录转换为前端格式
fn record_to_item(record: ScreenshotRecord) -> HistoryItem {
    // 解析 tags JSON
    let tags: Vec<String> =
        record.tags.as_ref().and_then(|s| serde_json::from_str(s).ok()).unwrap_or_default();

    // 解析 metadata JSON
    let metadata: HistoryMetadata =
        record.metadata.as_ref().and_then(|s| serde_json::from_str(s).ok()).unwrap_or_default();

    HistoryItem {
        id: record.id,
        created_at: record.created_at,
        file_path: record.file_path,
        thumbnail_path: record.thumbnail_path,
        width: record.width,
        height: record.height,
        file_size: record.file_size,
        ocr_text: record.ocr_text,
        tags,
        metadata,
        content_type: record.content_type,
        text_content: record.text_content,
        is_pinned: record.is_pinned,
    }
}

/// 将前端参数转换为数据库记录
fn params_to_record(params: &AddHistoryItemParams) -> ScreenshotRecord {
    let tags_json = params.tags.as_ref().map(|t| serde_json::to_string(t).unwrap_or_default());
    let metadata_json =
        params.metadata.as_ref().map(|m| serde_json::to_string(m).unwrap_or_default());

    ScreenshotRecord {
        id: 0,                     // 会被忽略
        created_at: String::new(), // 会被数据库自动设置
        file_path: params.file_path.clone(),
        thumbnail_path: params.thumbnail_path.clone(),
        width: params.width,
        height: params.height,
        file_size: params.file_size,
        ocr_text: params.ocr_text.clone(),
        tags: tags_json,
        metadata: metadata_json,
        image_hash: None,
        is_pinned: false,
        ocr_cached_at: None,
        content_type: params.content_type.clone().unwrap_or_else(|| "image".to_string()),
        text_content: params.text_content.clone(),
    }
}

// ============================================
// Tauri 命令
// ============================================

/// 搜索历史记录
///
/// # 参数
///
/// - `params`: 搜索参数
///
/// # 返回
///
/// 返回搜索结果，包含历史记录列表和分页信息
#[tauri::command]
pub async fn search_history(
    state: State<'_, HistoryState>,
    params: SearchParams,
) -> HuGeResult<HistorySearchResult> {
    debug!("搜索历史记录: {:?}", params);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let result = db.search_advanced(&params)?;

    let items: Vec<HistoryItem> = result.items.into_iter().map(record_to_item).collect();

    info!("搜索到 {} 条历史记录，共 {} 条", items.len(), result.total);

    Ok(HistorySearchResult { items, total: result.total, has_more: result.has_more })
}

/// 添加历史记录
///
/// # 参数
///
/// - `item`: 历史记录项
///
/// # 返回
///
/// 返回新增的历史记录（包含 ID 和创建时间）
#[tauri::command]
pub async fn add_history_item(
    state: State<'_, HistoryState>,
    item: AddHistoryItemParams,
) -> HuGeResult<HistoryItem> {
    info!("添加历史记录: {}", item.file_path);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let record = params_to_record(&item);
    let id = db.insert(&record)?;

    // 获取刚插入的记录（包含自动生成的字段）
    let inserted =
        db.get(id)?.ok_or_else(|| HuGeError::ConfigError("无法获取新插入的记录".to_string()))?;

    info!("历史记录已添加，ID: {}", id);

    Ok(record_to_item(inserted))
}

/// 更新历史记录
///
/// # 参数
///
/// - `id`: 记录 ID
/// - `updates`: 更新内容
#[tauri::command]
pub async fn update_history_item(
    state: State<'_, HistoryState>,
    id: i64,
    updates: UpdateHistoryItemParams,
) -> HuGeResult<()> {
    debug!("更新历史记录 {}: {:?}", id, updates);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let db_updates = ScreenshotRecordUpdate {
        ocr_text: updates.ocr_text,
        tags: updates.tags.map(|t| serde_json::to_string(&t).unwrap_or_default()),
        metadata: updates.metadata.map(|m| serde_json::to_string(&m).unwrap_or_default()),
        thumbnail_path: None,
        is_pinned: None,
        ocr_cached_at: None,
    };

    let updated = db.update(id, &db_updates)?;

    if updated {
        info!("历史记录 {} 已更新", id);
    } else {
        warn!("历史记录 {} 未找到或无更新", id);
    }

    Ok(())
}

/// 删除历史记录
///
/// # 参数
///
/// - `id`: 记录 ID
#[tauri::command]
pub async fn delete_history_item(state: State<'_, HistoryState>, id: i64) -> HuGeResult<()> {
    info!("删除历史记录: {}", id);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let deleted = db.delete(id)?;

    if deleted {
        info!("历史记录 {} 已删除", id);
    } else {
        warn!("历史记录 {} 未找到", id);
    }

    Ok(())
}

/// 批量删除历史记录
///
/// # 参数
///
/// - `ids`: 记录 ID 列表
#[tauri::command]
pub async fn delete_history_items(state: State<'_, HistoryState>, ids: Vec<i64>) -> HuGeResult<()> {
    info!("批量删除 {} 条历史记录", ids.len());

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let deleted = db.delete_batch(&ids)?;

    info!("成功删除 {} 条历史记录", deleted);

    Ok(())
}

/// 切换历史记录的钉住状态
#[tauri::command]
pub async fn toggle_pin_history_item(state: State<'_, HistoryState>, id: i64) -> HuGeResult<bool> {
    info!("切换钉住状态: id={}", id);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    db.toggle_pin(id)
}

/// 清除所有未钉住的历史记录
#[tauri::command]
pub async fn clear_unpinned_history(state: State<'_, HistoryState>) -> HuGeResult<usize> {
    info!("清除所有未钉住的历史记录");

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    db.clear_unpinned()
}

/// 获取历史记录统计
#[tauri::command]
pub async fn get_history_stats(state: State<'_, HistoryState>) -> HuGeResult<HistoryStats> {
    debug!("获取历史记录统计");

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let stats = db.get_stats()?;

    info!("历史记录统计: 总计 {} 条，大小 {} 字节", stats.total_count, stats.total_size);

    Ok(stats)
}

/// 导出历史记录
///
/// # 参数
///
/// - `ids`: 要导出的记录 ID 列表
/// - `output_dir`: 输出目录
///
/// # 返回
///
/// 返回导出的文件路径列表
#[tauri::command]
pub async fn export_history_items(
    state: State<'_, HistoryState>,
    ids: Vec<i64>,
    output_dir: String,
) -> HuGeResult<Vec<String>> {
    info!("导出 {} 条历史记录到: {}", ids.len(), output_dir);

    let db_guard = state.db.lock().await;
    let db = db_guard
        .as_ref()
        .ok_or_else(|| HuGeError::ConfigError("历史记录数据库未初始化".to_string()))?;

    let output_path = PathBuf::from(&output_dir);

    // 确保输出目录存在
    if !output_path.exists() {
        std::fs::create_dir_all(&output_path).map_err(HuGeError::FileError)?;
    }

    let mut exported_paths = Vec::new();

    for id in ids {
        if let Some(record) = db.get(id)? {
            let source_path = PathBuf::from(&record.file_path);

            if source_path.exists() {
                let filename = source_path
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_else(|| format!("screenshot_{}.png", id));

                let dest_path = output_path.join(&filename);

                std::fs::copy(&source_path, &dest_path).map_err(HuGeError::FileError)?;

                exported_paths.push(dest_path.to_string_lossy().to_string());
                debug!("导出: {} -> {}", record.file_path, dest_path.display());
            } else {
                warn!("源文件不存在，跳过: {}", record.file_path);
            }
        }
    }

    info!("成功导出 {} 个文件", exported_paths.len());

    Ok(exported_paths)
}

/// 初始化历史记录数据库
///
/// 应该在应用启动时调用
#[tauri::command]
pub async fn init_history_database(
    state: State<'_, HistoryState>,
    db_path: String,
) -> HuGeResult<()> {
    state.init(&db_path).await
}
