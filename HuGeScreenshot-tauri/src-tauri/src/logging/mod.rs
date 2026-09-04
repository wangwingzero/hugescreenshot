//! 日志系统
//!
//! 本模块提供应用程序的日志功能，包括：
//! - 日志文件轮转（每日轮转）
//! - 日志级别控制（通过环境变量）
//! - 自动清理旧日志（30天）
//! - 非阻塞日志写入
//!
//! # 日志文件位置
//!
//! 日志文件存储在 Tauri 的 app_log_dir 目录下：
//! - Windows: `%APPDATA%/com.wangh.hugescreenshot/logs/`
//! - macOS: `~/Library/Logs/com.wangh.hugescreenshot/`
//! - Linux: `~/.local/share/com.wangh.hugescreenshot/logs/`
//!
//! # 日志级别
//!
//! 通过环境变量 `HUGE_LOG` 控制日志级别：
//! - `HUGE_LOG=debug` - 调试级别（最详细）
//! - `HUGE_LOG=info` - 信息级别（默认）
//! - `HUGE_LOG=warn` - 警告级别
//! - `HUGE_LOG=error` - 错误级别
//!
//! # 使用示例
//!
//! ```ignore
//! use crate::logging::{setup_logging, cleanup_old_logs};
//! use std::path::PathBuf;
//!
//! // 初始化日志系统
//! let log_dir = PathBuf::from("logs");
//! let _guard = setup_logging(&log_dir)?;
//!
//! // 清理旧日志
//! cleanup_old_logs(&log_dir, 30)?;
//! ```

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use tracing::{debug, error, info, warn, Level};
use tracing_appender::non_blocking::WorkerGuard;
use tracing_appender::rolling::{RollingFileAppender, Rotation};
use tracing_subscriber::fmt::format::FmtSpan;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;
use tracing_subscriber::Layer;

use crate::error::{HuGeError, HuGeResult};

/// 日志文件前缀
const LOG_FILE_PREFIX: &str = "hugescreenshot";

/// 日志保留天数
pub const LOG_RETENTION_DAYS: u64 = 30;

/// 日志级别环境变量名
const LOG_LEVEL_ENV: &str = "HUGE_LOG";

/// 日志系统配置
#[derive(Debug, Clone)]
pub struct LogConfig {
    /// 日志目录
    pub log_dir: PathBuf,
    /// 日志级别（DEBUG, INFO, WARN, ERROR）
    pub level: Level,
    /// 日志保留天数
    pub retention_days: u64,
    /// 是否输出到控制台
    pub console_output: bool,
}

impl Default for LogConfig {
    fn default() -> Self {
        Self {
            log_dir: PathBuf::from("logs"),
            level: Level::INFO,
            retention_days: LOG_RETENTION_DAYS,
            console_output: cfg!(debug_assertions), // 调试模式下输出到控制台
        }
    }
}

/// 初始化日志系统
///
/// 设置日志文件轮转、日志级别和非阻塞写入。
/// 返回 WorkerGuard，必须保持其生命周期直到应用退出。
///
/// # 参数
///
/// - `log_dir`: 日志文件目录
///
/// # 返回
///
/// 返回 WorkerGuard，用于确保日志缓冲区在应用退出时被刷新
///
/// # 错误
///
/// - 无法创建日志目录时返回错误
///
/// # 注意
///
/// 返回的 WorkerGuard 必须保持存活，否则日志可能丢失。
/// 通常应该在 main 函数中保持其生命周期。
pub fn setup_logging(log_dir: &Path) -> HuGeResult<WorkerGuard> {
    setup_logging_with_config(&LogConfig { log_dir: log_dir.to_path_buf(), ..Default::default() })
}

/// 使用配置初始化日志系统
///
/// 提供更细粒度的日志配置控制。
///
/// # 参数
///
/// - `config`: 日志配置
///
/// # 返回
///
/// 返回 WorkerGuard，用于确保日志缓冲区在应用退出时被刷新
pub fn setup_logging_with_config(config: &LogConfig) -> HuGeResult<WorkerGuard> {
    // 确保日志目录存在
    if !config.log_dir.exists() {
        fs::create_dir_all(&config.log_dir)
            .map_err(|e| HuGeError::ConfigError(format!("创建日志目录失败: {}", e)))?;
    }

    // 创建日志文件轮转器（每日轮转，保留最近 31 个文件）
    // 使用 Builder 模式设置 max_log_files
    let file_appender = RollingFileAppender::builder()
        .rotation(Rotation::DAILY)
        .filename_prefix(LOG_FILE_PREFIX)
        .filename_suffix("log")
        .max_log_files(config.retention_days as usize + 1) // 保留 retention_days + 1 个文件
        .build(&config.log_dir)
        .map_err(|e| {
            HuGeError::ConfigError(format!("创建日志轮转器失败: {}", e))
        })?;

    // 创建非阻塞写入器
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    // 文件日志保留完整信息，控制台额外压制高频运行日志。
    let file_filter = build_file_env_filter(config.level);
    let console_filter = build_console_env_filter(config.level);

    // 创建文件日志层
    let file_layer = tracing_subscriber::fmt::layer()
        .with_writer(non_blocking)
        .with_ansi(false) // 文件中不使用 ANSI 颜色
        .with_target(true) // 显示目标模块
        .with_thread_ids(true) // 显示线程 ID
        .with_file(true) // 显示文件名
        .with_line_number(true) // 显示行号
        .with_span_events(FmtSpan::CLOSE); // 记录 span 关闭事件

    // 根据配置决定是否添加控制台输出
    if config.console_output {
        // 创建控制台日志层
        let console_layer = tracing_subscriber::fmt::layer()
            .with_ansi(true) // 控制台使用 ANSI 颜色
            .with_target(true)
            .with_thread_ids(false) // 控制台不显示线程 ID
            .with_file(false) // 控制台不显示文件名
            .with_line_number(false) // 控制台不显示行号
            .with_filter(console_filter);

        tracing_subscriber::registry()
            .with(file_filter)
            .with(file_layer)
            .with(console_layer)
            .init();
    } else {
        tracing_subscriber::registry().with(file_filter).with(file_layer).init();
    }

    Ok(guard)
}

fn build_file_env_filter(default_level: Level) -> EnvFilter {
    let env_filter = EnvFilter::try_from_env(LOG_LEVEL_ENV).unwrap_or_else(|_| {
        EnvFilter::new(format!(
            "{default_level},openvino_finder=warn,hyper_util=warn,reqwest=warn,hugescreenshot_tauri_lib::ocr::background_cache=warn,hugescreenshot_tauri_lib::ocr::engine=info,hugescreenshot_tauri_lib::ocr::detector=info,hugescreenshot_tauri_lib::ocr::recognizer=info,hugescreenshot_tauri_lib::ocr::openvino_engine=info,hugescreenshot_tauri_lib::screenshot::window_detect=info"
        ))
    });

    env_filter.add_directive(
        "hugescreenshot_tauri_lib::file_search::indexer=warn"
            .parse()
            .expect("valid file_search::indexer log directive"),
    )
}

fn build_console_env_filter(default_level: Level) -> EnvFilter {
    let env_filter = EnvFilter::try_from_env(LOG_LEVEL_ENV).unwrap_or_else(|_| {
        EnvFilter::new(format!("{default_level},openvino_finder=warn,hyper_util=warn,reqwest=warn"))
    });

    [
        "hugescreenshot_tauri_lib::file_search::indexer=warn",
        "hugescreenshot_tauri_lib::clipboard=warn",
        "hugescreenshot_tauri_lib::database::settings=warn",
        "hugescreenshot_tauri_lib::ocr::background_cache=warn",
        "hugescreenshot_tauri_lib::ocr::detector=warn",
        "hugescreenshot_tauri_lib::ocr::engine=warn",
        "hugescreenshot_tauri_lib::ocr::recognizer=warn",
        "hugescreenshot_tauri_lib::ocr::openvino_engine=warn",
    ]
    .into_iter()
    .fold(env_filter, |filter, directive| {
        filter.add_directive(directive.parse().expect("valid log directive"))
    })
}

/// 清理旧日志文件
///
/// 删除超过指定天数的日志文件。
/// 这是一个补充清理机制，因为 tracing-appender 的 max_log_files
/// 只在创建新日志文件时触发清理。
///
/// # 参数
///
/// - `log_dir`: 日志目录
/// - `retention_days`: 保留天数
///
/// # 返回
///
/// 返回删除的文件数量
///
/// # 错误
///
/// - 无法读取日志目录时返回错误
pub fn cleanup_old_logs(log_dir: &Path, retention_days: u64) -> HuGeResult<usize> {
    if !log_dir.exists() {
        debug!("日志目录不存在，跳过清理: {:?}", log_dir);
        return Ok(0);
    }

    let retention_duration = Duration::from_secs(retention_days * 24 * 60 * 60);
    let now = SystemTime::now();
    let mut deleted_count = 0;

    let entries = fs::read_dir(log_dir)
        .map_err(|e| HuGeError::ConfigError(format!("读取日志目录失败: {}", e)))?;

    for entry in entries.flatten() {
        let path = entry.path();

        // 只处理日志文件
        if !is_log_file(&path) {
            continue;
        }

        // 获取文件修改时间
        let metadata = match fs::metadata(&path) {
            Ok(m) => m,
            Err(e) => {
                warn!("无法获取文件元数据: {:?}, 错误: {}", path, e);
                continue;
            }
        };

        let modified = match metadata.modified() {
            Ok(t) => t,
            Err(e) => {
                warn!("无法获取文件修改时间: {:?}, 错误: {}", path, e);
                continue;
            }
        };

        // 检查文件是否过期
        if let Ok(age) = now.duration_since(modified) {
            if age > retention_duration {
                match fs::remove_file(&path) {
                    Ok(_) => {
                        info!("删除过期日志文件: {:?}", path);
                        deleted_count += 1;
                    }
                    Err(e) => {
                        error!("删除日志文件失败: {:?}, 错误: {}", path, e);
                    }
                }
            }
        }
    }

    if deleted_count > 0 {
        info!("日志清理完成，删除了 {} 个过期文件", deleted_count);
    } else {
        debug!("没有需要清理的过期日志文件");
    }

    Ok(deleted_count)
}

/// 检查文件是否是日志文件
fn is_log_file(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }

    // 检查文件名是否以日志前缀开头
    if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
        return file_name.starts_with(LOG_FILE_PREFIX) && file_name.ends_with(".log");
    }

    false
}

/// 获取日志目录路径
///
/// 使用 Tauri 的 app_log_dir 获取日志目录。
/// 如果无法获取，则使用应用数据目录下的 logs 子目录。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 返回日志目录路径
pub fn get_log_dir<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> HuGeResult<PathBuf> {
    use tauri::Manager;

    // 尝试获取 app_log_dir
    if let Ok(log_dir) = app.path().app_log_dir() {
        return Ok(log_dir);
    }

    // 回退到 app_data_dir/logs
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| HuGeError::ConfigError(format!("获取应用数据目录失败: {}", e)))?;

    Ok(app_data_dir.join("logs"))
}

/// 获取当前日志级别
///
/// 从环境变量读取当前配置的日志级别。
///
/// # 返回
///
/// 返回当前日志级别字符串
pub fn get_current_log_level() -> String {
    std::env::var(LOG_LEVEL_ENV).unwrap_or_else(|_| "info".to_string())
}

/// 设置日志级别
///
/// 通过设置环境变量来改变日志级别。
/// 注意：这只会影响新创建的日志订阅者，不会影响已经初始化的日志系统。
///
/// # 参数
///
/// - `level`: 日志级别（debug, info, warn, error）
pub fn set_log_level(level: &str) {
    std::env::set_var(LOG_LEVEL_ENV, level);
}

/// 记录 Python Sidecar 错误
///
/// 专门用于记录 Python Sidecar 的错误和 traceback。
/// 满足 Requirement 20.2: WHEN a Python_Sidecar error occurs,
/// THE Rust_Core SHALL capture and log the full traceback
///
/// # 参数
///
/// - `service`: 服务名称
/// - `method`: 方法名称
/// - `error_message`: 错误消息
/// - `traceback`: Python traceback（可选）
pub fn log_sidecar_error(
    service: &str,
    method: &str,
    error_message: &str,
    traceback: Option<&str>,
) {
    if let Some(tb) = traceback {
        error!(
            target: "sidecar",
            service = service,
            method = method,
            error = error_message,
            "Python Sidecar 错误:\n{}\n\nTraceback:\n{}",
            error_message,
            tb
        );
    } else {
        error!(
            target: "sidecar",
            service = service,
            method = method,
            error = error_message,
            "Python Sidecar 错误: {}",
            error_message
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use std::io::Write;
    use tempfile::tempdir;

    #[test]
    fn test_log_config_default() {
        let config = LogConfig::default();
        assert_eq!(config.retention_days, 30);
        assert_eq!(config.level, Level::INFO);
    }

    #[test]
    fn test_is_log_file() {
        let temp_dir = tempdir().unwrap();

        // 创建日志文件
        let log_file = temp_dir.path().join("hugescreenshot.2024-01-01.log");
        File::create(&log_file).unwrap();
        assert!(is_log_file(&log_file));

        // 创建非日志文件
        let other_file = temp_dir.path().join("other.txt");
        File::create(&other_file).unwrap();
        assert!(!is_log_file(&other_file));

        // 目录不是日志文件
        let sub_dir = temp_dir.path().join("subdir");
        fs::create_dir(&sub_dir).unwrap();
        assert!(!is_log_file(&sub_dir));
    }

    #[test]
    fn test_cleanup_old_logs_empty_dir() {
        let temp_dir = tempdir().unwrap();
        let result = cleanup_old_logs(temp_dir.path(), 30).unwrap();
        assert_eq!(result, 0);
    }

    #[test]
    fn test_cleanup_old_logs_nonexistent_dir() {
        let nonexistent = PathBuf::from("/nonexistent/path/to/logs");
        let result = cleanup_old_logs(&nonexistent, 30).unwrap();
        assert_eq!(result, 0);
    }

    #[test]
    fn test_cleanup_old_logs_with_files() {
        let temp_dir = tempdir().unwrap();

        // 创建一些日志文件
        for i in 0..5 {
            let log_file = temp_dir.path().join(format!("hugescreenshot.{}.log", i));
            let mut file = File::create(&log_file).unwrap();
            writeln!(file, "Test log content {}", i).unwrap();
        }

        // 创建一个非日志文件
        let other_file = temp_dir.path().join("other.txt");
        File::create(&other_file).unwrap();

        // 清理（由于文件刚创建，不会被删除）
        let result = cleanup_old_logs(temp_dir.path(), 30).unwrap();
        assert_eq!(result, 0);

        // 验证文件仍然存在
        assert_eq!(fs::read_dir(temp_dir.path()).unwrap().count(), 6);
    }

    #[test]
    fn test_get_current_log_level() {
        // 清除环境变量
        std::env::remove_var(LOG_LEVEL_ENV);
        assert_eq!(get_current_log_level(), "info");

        // 设置环境变量
        std::env::set_var(LOG_LEVEL_ENV, "debug");
        assert_eq!(get_current_log_level(), "debug");

        // 清理
        std::env::remove_var(LOG_LEVEL_ENV);
    }

    #[test]
    fn test_set_log_level() {
        set_log_level("warn");
        assert_eq!(std::env::var(LOG_LEVEL_ENV).unwrap(), "warn");

        // 清理
        std::env::remove_var(LOG_LEVEL_ENV);
    }
}
