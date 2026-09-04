//! 自动更新命令模块
//!
//! 本模块提供自动更新相关的 Tauri 命令。
//!
//! # 功能
//!
//! - 检查更新
//! - 下载并安装更新
//! - 获取更新状态
//! - 获取/设置自动更新配置
//!
//! # Requirements
//!
//! - 19.1: 启动时和定期检查更新
//! - 19.2: 更新可用时通知用户并显示发布说明
//! - 19.3: 后台下载和安装更新
//! - 19.4: 更新失败时回滚到上一版本
//! - 19.5: 支持增量更新以减少下载大小
//! - 19.6: 用户可以在设置中禁用自动更新

use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_updater::UpdaterExt;
use tracing::info;

/// 更新信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateInfo {
    /// 新版本号
    pub version: String,
    /// 发布说明
    pub notes: Option<String>,
    /// 发布日期
    pub date: Option<String>,
    /// 下载大小（字节）
    pub download_size: Option<u64>,
}

/// 更新状态
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status")]
pub enum UpdateStatus {
    /// 空闲状态
    Idle,
    /// 正在检查更新
    Checking,
    /// 有可用更新
    Available { info: UpdateInfo },
    /// 正在下载
    Downloading { progress: f64 },
    /// 下载完成，准备安装
    Ready { info: UpdateInfo },
    /// 正在安装
    Installing,
    /// 更新完成，需要重启
    PendingRestart,
    /// 没有可用更新
    UpToDate,
    /// 更新失败
    Error { message: String },
}

/// 自动更新配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateConfig {
    /// 是否启用自动更新
    pub auto_update_enabled: bool,
    /// 检查更新间隔（小时）
    pub check_interval_hours: u32,
    /// 是否在启动时检查更新
    pub check_on_startup: bool,
    /// 是否自动下载更新
    pub auto_download: bool,
    /// 是否自动安装更新
    pub auto_install: bool,
}

impl Default for UpdateConfig {
    fn default() -> Self {
        Self {
            auto_update_enabled: true,
            check_interval_hours: 24,
            check_on_startup: true,
            auto_download: true,
            auto_install: false, // 默认不自动安装，让用户确认
        }
    }
}

fn build_update_info(update: &tauri_plugin_updater::Update) -> UpdateInfo {
    UpdateInfo {
        version: update.version.clone(),
        notes: update.body.clone(),
        date: update.date.map(|date| date.to_string()),
        download_size: None,
    }
}

/// 检查更新
///
/// # Requirements
/// - 19.1: 检查更新
/// - 19.2: 返回更新信息和发布说明
#[tauri::command]
pub async fn check_for_update(app: AppHandle) -> Result<UpdateStatus, String> {
    info!("检查更新...");

    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater.check().await.map_err(|e| e.to_string())?;

    if let Some(update) = update {
        let info = build_update_info(&update);
        info!("发现新版本: {}", info.version);
        Ok(UpdateStatus::Available { info })
    } else {
        info!("更新检查完成：当前已是最新版本");
        Ok(UpdateStatus::UpToDate)
    }
}

/// 下载并安装更新
///
/// # Requirements
/// - 19.3: 后台下载和安装更新
/// - 19.4: 更新失败时返回错误（回滚由服务器端处理）
#[tauri::command]
pub async fn download_and_install_update(app: AppHandle) -> Result<UpdateStatus, String> {
    info!("下载并安装更新...");

    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater.check().await.map_err(|e| e.to_string())?;

    let Some(update) = update else {
        info!("未发现可安装的更新");
        return Ok(UpdateStatus::UpToDate);
    };

    let info = build_update_info(&update);
    update
        .download_and_install(
            |chunk_length, content_length| {
                info!("更新下载中: chunk={} total={:?}", chunk_length, content_length);
            },
            || {
                info!("更新下载完成，开始安装");
            },
        )
        .await
        .map_err(|e| e.to_string())?;

    info!("更新安装已触发，等待应用重启");
    Ok(UpdateStatus::Ready { info })
}

/// 重启应用以完成更新
///
/// # Requirements
/// - 19.3: 完成更新安装
#[tauri::command]
pub async fn restart_app(app: AppHandle) -> Result<(), String> {
    info!("重启应用以完成更新...");

    app.request_restart();
    Ok(())
}

/// 获取当前版本
#[tauri::command]
pub fn get_current_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// 获取更新配置
///
/// # Requirements
/// - 19.6: 用户可以在设置中禁用自动更新
#[tauri::command]
pub async fn get_update_config(app: AppHandle) -> Result<UpdateConfig, String> {
    use crate::database::settings::{get_config_path, load_config};

    let config_path = get_config_path(&app).map_err(|e| e.to_string())?;
    let app_config = load_config(&config_path).map_err(|e| e.to_string())?;

    // 从 AppConfig 中提取更新配置
    Ok(UpdateConfig {
        auto_update_enabled: app_config.general.auto_update_enabled.unwrap_or(true),
        check_interval_hours: app_config.general.update_check_interval_hours.unwrap_or(24),
        check_on_startup: app_config.general.check_update_on_startup.unwrap_or(true),
        auto_download: app_config.general.auto_download_update.unwrap_or(true),
        auto_install: app_config.general.auto_install_update.unwrap_or(false),
    })
}

/// 设置更新配置
///
/// # Requirements
/// - 19.6: 用户可以在设置中禁用自动更新
#[tauri::command]
pub async fn set_update_config(app: AppHandle, config: UpdateConfig) -> Result<(), String> {
    use crate::database::settings::{get_config_path, load_config, save_config};

    let config_path = get_config_path(&app).map_err(|e| e.to_string())?;
    let mut app_config = load_config(&config_path).map_err(|e| e.to_string())?;

    // 更新 AppConfig 中的更新配置
    app_config.general.auto_update_enabled = Some(config.auto_update_enabled);
    app_config.general.update_check_interval_hours = Some(config.check_interval_hours);
    app_config.general.check_update_on_startup = Some(config.check_on_startup);
    app_config.general.auto_download_update = Some(config.auto_download);
    app_config.general.auto_install_update = Some(config.auto_install);

    save_config(&config_path, &app_config).map_err(|e| e.to_string())?;

    info!("更新配置已保存: {:?}", config);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_update_config_default() {
        let config = UpdateConfig::default();
        assert!(config.auto_update_enabled);
        assert_eq!(config.check_interval_hours, 24);
        assert!(config.check_on_startup);
        assert!(config.auto_download);
        assert!(!config.auto_install);
    }

    #[test]
    fn test_get_current_version() {
        let version = get_current_version();
        assert!(!version.is_empty());
    }

    #[test]
    fn test_update_status_serialization() {
        let status = UpdateStatus::Available {
            info: UpdateInfo {
                version: "1.0.0".to_string(),
                notes: Some("Bug fixes".to_string()),
                date: Some("2024-01-01".to_string()),
                download_size: Some(1024),
            },
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("Available"));
        assert!(json.contains("1.0.0"));
    }
}
