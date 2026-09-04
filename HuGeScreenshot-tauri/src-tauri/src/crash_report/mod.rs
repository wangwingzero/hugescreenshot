//! 崩溃报告系统
//!
//! 本模块提供应用程序崩溃报告功能，包括：
//! - 捕获未处理的 panic
//! - 生成崩溃报告文件（包含时间戳、错误信息、堆栈跟踪、系统信息）
//! - 显示用户友好的错误对话框
//!
//! # 功能
//!
//! - **Panic Hook**: 捕获所有未处理的 panic，生成崩溃报告
//! - **系统信息收集**: 收集 OS 版本、内存使用、CPU 信息等
//! - **崩溃报告文件**: 保存到日志目录，便于问题诊断
//! - **用户友好对话框**: 显示简洁的错误信息，引导用户报告问题
//!
//! # 使用示例
//!
//! ```ignore
//! use crate::crash_report::{setup_crash_handler, CrashReportConfig};
//! use std::path::PathBuf;
//!
//! // 初始化崩溃处理器
//! let config = CrashReportConfig {
//!     report_dir: PathBuf::from("logs"),
//!     app_name: "虎哥截图".to_string(),
//!     app_version: "2.0.0".to_string(),
//!     show_dialog: true,
//! };
//! setup_crash_handler(config);
//! ```
//!
//! # 崩溃报告格式
//!
//! 崩溃报告文件包含以下信息：
//! - 时间戳
//! - 应用名称和版本
//! - 错误消息
//! - 堆栈跟踪
//! - 系统信息（OS、架构、内存等）
//!
//! # 满足需求
//!
//! - Requirement 20.4: IF a critical error occurs, THEN THE Tauri_App SHALL display a user-friendly error dialog
//! - Requirement 20.6: WHEN the application crashes, THE Tauri_App SHALL generate a crash report with system information

use std::backtrace::Backtrace;
use std::fs::{self, File};
use std::io::Write;
use std::panic::{self, PanicHookInfo};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

use chrono::Local;
use tracing::{error, info};

/// 崩溃报告配置
#[derive(Debug, Clone)]
pub struct CrashReportConfig {
    /// 崩溃报告保存目录
    pub report_dir: PathBuf,
    /// 应用名称
    pub app_name: String,
    /// 应用版本
    pub app_version: String,
    /// 是否显示错误对话框
    pub show_dialog: bool,
}

impl Default for CrashReportConfig {
    fn default() -> Self {
        Self {
            report_dir: PathBuf::from("logs"),
            app_name: "虎哥截图".to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
            show_dialog: true,
        }
    }
}

/// 系统信息
#[derive(Debug, Clone)]
pub struct SystemInfo {
    /// 操作系统
    pub os: String,
    /// 操作系统版本
    pub os_version: String,
    /// CPU 架构
    pub arch: String,
    /// 主机名
    pub hostname: String,
    /// 当前工作目录
    pub cwd: String,
    /// 可执行文件路径
    pub exe_path: String,
    /// Rust 版本
    pub rust_version: String,
}

impl SystemInfo {
    /// 收集系统信息
    pub fn collect() -> Self {
        Self {
            os: std::env::consts::OS.to_string(),
            os_version: get_os_version(),
            arch: std::env::consts::ARCH.to_string(),
            hostname: hostname::get()
                .map(|h| h.to_string_lossy().to_string())
                .unwrap_or_else(|_| "unknown".to_string()),
            cwd: std::env::current_dir()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|_| "unknown".to_string()),
            exe_path: std::env::current_exe()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|_| "unknown".to_string()),
            rust_version: get_rust_version(),
        }
    }

    /// 格式化为字符串
    pub fn format(&self) -> String {
        format!(
            "操作系统: {} {}\n\
             CPU 架构: {}\n\
             主机名: {}\n\
             工作目录: {}\n\
             可执行文件: {}\n\
             Rust 版本: {}",
            self.os,
            self.os_version,
            self.arch,
            self.hostname,
            self.cwd,
            self.exe_path,
            self.rust_version
        )
    }
}

/// 崩溃报告
#[derive(Debug, Clone)]
pub struct CrashReport {
    /// 时间戳
    pub timestamp: String,
    /// 应用名称
    pub app_name: String,
    /// 应用版本
    pub app_version: String,
    /// 错误消息
    pub error_message: String,
    /// 错误位置（文件:行号）
    pub error_location: Option<String>,
    /// 堆栈跟踪
    pub backtrace: String,
    /// 系统信息
    pub system_info: SystemInfo,
}

impl CrashReport {
    /// 从 panic 信息创建崩溃报告
    pub fn from_panic(panic_info: &PanicHookInfo<'_>, config: &CrashReportConfig) -> Self {
        let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S%.3f").to_string();

        // 获取错误消息
        let error_message = if let Some(s) = panic_info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = panic_info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic payload".to_string()
        };

        // 获取错误位置
        let error_location = panic_info
            .location()
            .map(|loc| format!("{}:{}:{}", loc.file(), loc.line(), loc.column()));

        // 捕获堆栈跟踪
        let backtrace = Backtrace::force_capture().to_string();

        // 收集系统信息
        let system_info = SystemInfo::collect();

        Self {
            timestamp,
            app_name: config.app_name.clone(),
            app_version: config.app_version.clone(),
            error_message,
            error_location,
            backtrace,
            system_info,
        }
    }

    /// 格式化为完整报告字符串
    pub fn format(&self) -> String {
        let separator = "=".repeat(80);
        let sub_separator = "-".repeat(40);

        let location_str = self
            .error_location
            .as_ref()
            .map(|loc| format!("错误位置: {}\n", loc))
            .unwrap_or_default();

        format!(
            "{separator}\n\
             崩溃报告 - {app_name} v{app_version}\n\
             {separator}\n\n\
             时间: {timestamp}\n\
             {location_str}\
             错误信息: {error_message}\n\n\
             {sub_separator}\n\
             系统信息\n\
             {sub_separator}\n\
             {system_info}\n\n\
             {sub_separator}\n\
             堆栈跟踪\n\
             {sub_separator}\n\
             {backtrace}\n\n\
             {separator}\n\
             请将此报告发送给开发者以帮助修复问题\n\
             {separator}\n",
            separator = separator,
            sub_separator = sub_separator,
            app_name = self.app_name,
            app_version = self.app_version,
            timestamp = self.timestamp,
            location_str = location_str,
            error_message = self.error_message,
            system_info = self.system_info.format(),
            backtrace = self.backtrace
        )
    }

    /// 保存崩溃报告到文件
    pub fn save_to_file(&self, report_dir: &Path) -> Result<PathBuf, std::io::Error> {
        // 确保目录存在
        if !report_dir.exists() {
            fs::create_dir_all(report_dir)?;
        }

        // 生成文件名
        let timestamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
        let filename = format!("crash_report_{}.txt", timestamp);
        let file_path = report_dir.join(filename);

        // 写入文件
        let mut file = File::create(&file_path)?;
        file.write_all(self.format().as_bytes())?;
        file.flush()?;

        Ok(file_path)
    }

    /// 获取用户友好的错误摘要
    pub fn get_user_friendly_summary(&self) -> String {
        format!(
            "应用程序遇到了一个意外错误并需要关闭。\n\n\
             错误信息: {}\n\n\
             崩溃报告已保存，请将报告发送给开发者以帮助修复此问题。",
            self.error_message
        )
    }
}

/// 全局配置存储
static CRASH_CONFIG: OnceLock<CrashReportConfig> = OnceLock::new();

/// 防止重复显示对话框的标志
static DIALOG_SHOWN: AtomicBool = AtomicBool::new(false);

// ============================================================================
// 线程局部标记：抑制可预期 panic 的崩溃对话框
// ============================================================================

thread_local! {
    /// 当前线程是否抑制崩溃对话框
    ///
    /// 用于 `catch_unwind` 场景：第三方库可能在内部 panic，
    /// 但调用方已用 `catch_unwind` 包裹。此时 panic hook 仍会触发，
    /// 但不应弹出阻塞式对话框，否则会导致用户误以为应用崩溃。
    ///
    /// 使用方法：
    /// ```ignore
    /// use crate::crash_report::suppress_crash_dialog_guard;
    /// let _guard = suppress_crash_dialog_guard();
    /// let result = std::panic::catch_unwind(|| { /* 可能 panic 的代码 */ });
    /// // guard drop 时自动恢复
    /// ```
    static SUPPRESS_CRASH_DIALOG: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

/// RAII guard: 在作用域内抑制崩溃对话框，离开作用域自动恢复
pub struct SuppressCrashDialogGuard;

impl SuppressCrashDialogGuard {
    fn new() -> Self {
        SUPPRESS_CRASH_DIALOG.with(|flag| flag.set(true));
        Self
    }
}

impl Drop for SuppressCrashDialogGuard {
    fn drop(&mut self) {
        SUPPRESS_CRASH_DIALOG.with(|flag| flag.set(false));
    }
}

/// 创建一个 RAII guard，在作用域内抑制崩溃对话框
///
/// 当使用 `catch_unwind` 包裹可能 panic 的第三方库调用时，
/// 应先创建此 guard 以防止 panic hook 弹出阻塞式错误对话框。
///
/// # 示例
///
/// ```ignore
/// let _guard = suppress_crash_dialog_guard();
/// let result = std::panic::catch_unwind(|| {
///     // 第三方库调用，可能 panic
///     some_third_party_call(&bytes)
/// });
/// // _guard 在这里 drop，自动恢复对话框行为
/// ```
pub fn suppress_crash_dialog_guard() -> SuppressCrashDialogGuard {
    SuppressCrashDialogGuard::new()
}

/// 检查当前线程是否应显示崩溃对话框
fn should_show_crash_dialog() -> bool {
    SUPPRESS_CRASH_DIALOG.with(|flag| !flag.get())
}

/// 设置崩溃处理器
///
/// 注册 panic hook，在应用崩溃时：
/// 1. 生成崩溃报告文件
/// 2. 显示用户友好的错误对话框
///
/// # 参数
///
/// - `config`: 崩溃报告配置
///
/// # 注意
///
/// 此函数应该在应用启动时尽早调用，且只调用一次。
pub fn setup_crash_handler(config: CrashReportConfig) {
    // 保存配置
    let _ = CRASH_CONFIG.set(config.clone());

    // 获取默认的 panic hook
    let default_hook = panic::take_hook();

    // 设置自定义 panic hook
    panic::set_hook(Box::new(move |panic_info| {
        // 获取配置
        let config = CRASH_CONFIG.get().cloned().unwrap_or_default();

        // 创建崩溃报告
        let report = CrashReport::from_panic(panic_info, &config);

        // 记录到日志
        error!(
            target: "crash",
            error = %report.error_message,
            location = ?report.error_location,
            "应用程序崩溃"
        );

        // 检查是否为可预期的 panic（如 pdf-extract 的 catch_unwind 场景）
        let is_expected_panic = !should_show_crash_dialog();

        if is_expected_panic {
            // 可预期的 panic：只记录日志和保存报告，不弹出对话框
            info!(
                target: "crash",
                "检测到可预期的 panic（已被 catch_unwind 包裹），跳过崩溃对话框"
            );
            if let Ok(path) = report.save_to_file(&config.report_dir) {
                info!(
                    target: "crash",
                    path = %path.display(),
                    "崩溃报告已保存（仅供调试参考）"
                );
            }
        } else {
            // 非预期的 panic：保存报告并显示对话框
            match report.save_to_file(&config.report_dir) {
                Ok(path) => {
                    info!(
                        target: "crash",
                        path = %path.display(),
                        "崩溃报告已保存"
                    );

                    // 显示用户友好的错误对话框
                    if config.show_dialog && !DIALOG_SHOWN.swap(true, Ordering::SeqCst) {
                        show_crash_dialog(&report, &path);
                    }
                }
                Err(e) => {
                    error!(
                        target: "crash",
                        error = %e,
                        "保存崩溃报告失败"
                    );

                    // 即使保存失败，也尝试显示对话框
                    if config.show_dialog && !DIALOG_SHOWN.swap(true, Ordering::SeqCst) {
                        show_crash_dialog_without_file(&report);
                    }
                }
            }
        }

        // 调用默认的 panic hook（打印到 stderr）
        default_hook(panic_info);
    }));

    info!("崩溃处理器已设置");
}

/// 显示崩溃对话框（带文件路径）
fn show_crash_dialog(report: &CrashReport, report_path: &Path) {
    let title = format!("{} - 应用程序错误", report.app_name);
    let message = format!(
        "{}\n\n崩溃报告已保存到:\n{}",
        report.get_user_friendly_summary(),
        report_path.display()
    );

    // 使用 Windows 原生对话框
    #[cfg(windows)]
    {
        show_windows_error_dialog(&title, &message);
    }

    // 非 Windows 平台使用简单的控制台输出
    #[cfg(not(windows))]
    {
        eprintln!("\n{}\n{}\n", title, message);
    }
}

/// 显示崩溃对话框（无文件路径）
fn show_crash_dialog_without_file(report: &CrashReport) {
    let title = format!("{} - 应用程序错误", report.app_name);
    let message = report.get_user_friendly_summary();

    #[cfg(windows)]
    {
        show_windows_error_dialog(&title, &message);
    }

    #[cfg(not(windows))]
    {
        eprintln!("\n{}\n{}\n", title, message);
    }
}

/// 使用 Windows API 显示错误对话框
#[cfg(windows)]
fn show_windows_error_dialog(title: &str, message: &str) {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};

    // 转换为宽字符串
    fn to_wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    let title_wide = to_wide(title);
    let message_wide = to_wide(message);

    unsafe {
        let _ = MessageBoxW(
            None,
            windows::core::PCWSTR(message_wide.as_ptr()),
            windows::core::PCWSTR(title_wide.as_ptr()),
            MB_OK | MB_ICONERROR,
        );
    }
}

/// 获取操作系统版本
fn get_os_version() -> String {
    #[cfg(windows)]
    {
        // 尝试从注册表获取 Windows 版本
        if let Ok(hklm) = winreg::RegKey::predef(winreg::enums::HKEY_LOCAL_MACHINE)
            .open_subkey("SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion")
        {
            let product_name: String = hklm.get_value("ProductName").unwrap_or_default();
            let build: String = hklm.get_value("CurrentBuild").unwrap_or_default();
            if !product_name.is_empty() {
                return format!("{} (Build {})", product_name, build);
            }
        }
        "Windows (版本未知)".to_string()
    }

    #[cfg(not(windows))]
    {
        "Unknown".to_string()
    }
}

/// 获取 Rust 版本信息
fn get_rust_version() -> String {
    // 编译时的 Rust 版本
    format!(
        "rustc {} (编译于 {})",
        env!("CARGO_PKG_RUST_VERSION", "unknown"),
        env!("CARGO_PKG_VERSION")
    )
}

/// 手动触发崩溃报告（用于测试或手动报告严重错误）
///
/// # 参数
///
/// - `error_message`: 错误消息
/// - `report_dir`: 报告保存目录
///
/// # 返回
///
/// 返回崩溃报告文件路径
pub fn generate_crash_report(
    error_message: &str,
    report_dir: &Path,
) -> Result<PathBuf, std::io::Error> {
    let config = CRASH_CONFIG.get().cloned().unwrap_or_default();

    let report = CrashReport {
        timestamp: Local::now().format("%Y-%m-%d %H:%M:%S%.3f").to_string(),
        app_name: config.app_name,
        app_version: config.app_version,
        error_message: error_message.to_string(),
        error_location: None,
        backtrace: Backtrace::force_capture().to_string(),
        system_info: SystemInfo::collect(),
    };

    report.save_to_file(report_dir)
}

/// 显示用户友好的错误对话框（Tauri 命令）
///
/// 此函数可以从前端调用，显示一个原生错误对话框。
///
/// # 参数
///
/// - `title`: 对话框标题
/// - `message`: 错误消息
#[tauri::command]
pub async fn show_error_dialog(title: String, message: String) {
    #[cfg(windows)]
    {
        show_windows_error_dialog(&title, &message);
    }

    #[cfg(not(windows))]
    {
        eprintln!("\n{}\n{}\n", title, message);
    }
}

/// 获取崩溃报告目录
#[tauri::command]
pub fn get_crash_report_dir() -> Option<String> {
    CRASH_CONFIG.get().map(|c| c.report_dir.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_system_info_collect() {
        let info = SystemInfo::collect();
        assert!(!info.os.is_empty());
        assert!(!info.arch.is_empty());
    }

    #[test]
    fn test_system_info_format() {
        let info = SystemInfo::collect();
        let formatted = info.format();
        assert!(formatted.contains("操作系统"));
        assert!(formatted.contains("CPU 架构"));
    }

    #[test]
    fn test_crash_report_format() {
        let report = CrashReport {
            timestamp: "2024-01-01 12:00:00.000".to_string(),
            app_name: "测试应用".to_string(),
            app_version: "1.0.0".to_string(),
            error_message: "测试错误".to_string(),
            error_location: Some("test.rs:10:5".to_string()),
            backtrace: "backtrace here".to_string(),
            system_info: SystemInfo::collect(),
        };

        let formatted = report.format();
        assert!(formatted.contains("崩溃报告"));
        assert!(formatted.contains("测试应用"));
        assert!(formatted.contains("测试错误"));
        assert!(formatted.contains("test.rs:10:5"));
    }

    #[test]
    fn test_crash_report_save_to_file() {
        let temp_dir = tempdir().unwrap();

        let report = CrashReport {
            timestamp: "2024-01-01 12:00:00.000".to_string(),
            app_name: "测试应用".to_string(),
            app_version: "1.0.0".to_string(),
            error_message: "测试错误".to_string(),
            error_location: None,
            backtrace: "backtrace".to_string(),
            system_info: SystemInfo::collect(),
        };

        let path = report.save_to_file(temp_dir.path()).unwrap();
        assert!(path.exists());

        let content = fs::read_to_string(&path).unwrap();
        assert!(content.contains("测试应用"));
        assert!(content.contains("测试错误"));
    }

    #[test]
    fn test_crash_report_config_default() {
        let config = CrashReportConfig::default();
        assert_eq!(config.app_name, "虎哥截图");
        assert!(config.show_dialog);
    }

    #[test]
    fn test_user_friendly_summary() {
        let report = CrashReport {
            timestamp: "2024-01-01 12:00:00.000".to_string(),
            app_name: "测试应用".to_string(),
            app_version: "1.0.0".to_string(),
            error_message: "内存不足".to_string(),
            error_location: None,
            backtrace: "".to_string(),
            system_info: SystemInfo::collect(),
        };

        let summary = report.get_user_friendly_summary();
        assert!(summary.contains("内存不足"));
        assert!(summary.contains("崩溃报告已保存"));
    }

    #[test]
    fn test_generate_crash_report() {
        let temp_dir = tempdir().unwrap();

        let path = generate_crash_report("手动触发的错误", temp_dir.path()).unwrap();
        assert!(path.exists());

        let content = fs::read_to_string(&path).unwrap();
        assert!(content.contains("手动触发的错误"));
    }
}
