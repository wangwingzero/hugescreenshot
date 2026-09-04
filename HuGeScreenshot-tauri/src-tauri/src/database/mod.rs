//! 数据库模块
//!
//! 本模块负责数据持久化，包括：
//! - 历史记录存储（SQLite）
//! - 应用配置存储
//! - 规章文件存储（用于全文搜索）
//!
//! # 子模块
//!
//! - `history`: 历史记录数据库
//! - `settings`: 设置持久化

pub mod history;
pub mod settings;

// 重新导出常用类型
pub use history::{
    HistoryDatabase, HistoryStats, PoolStatus, ScreenshotRecord, ScreenshotRecordUpdate,
    SearchParams, SearchResult,
};
pub use settings::{
    get_cached_config, get_config_path, init_config, load_config, load_hotkey_config, save_config,
    save_hotkey_config, update_cached_config, AppConfig,
};
