//! 配置命令模块
//!
//! 提供应用配置的加载、保存、导入、导出功能。
//! 以及 Windows 自动启动设置。
//!
//! # 功能
//!
//! - 加载和保存应用配置
//! - 导入和导出配置文件
//! - Windows 自动启动设置（通过注册表）
//!
//! @validates Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6

use std::fs;
use std::path::Path;
use tauri::AppHandle;
use tracing::{debug, error, info, warn};

use crate::database::settings::{
    get_config_path, load_config as db_load_config, save_config as db_save_config, AppConfig,
};
use crate::error::{HuGeError, HuGeResult};

/// 加载应用配置
///
/// 从配置文件加载应用设置。如果文件不存在，返回默认配置。
///
/// # 返回
///
/// 返回完整的应用配置
///
/// @validates Requirements 17.1, 17.3
#[tauri::command]
pub async fn load_config(app: AppHandle) -> HuGeResult<AppConfig> {
    info!("加载应用配置...");

    let config_path = get_config_path(&app)?;
    let config = db_load_config(&config_path)?;

    debug!("配置加载成功: {:?}", config);
    Ok(config)
}

/// 保存应用配置
///
/// 将配置保存到配置文件。
///
/// # 参数
///
/// - `config`: 要保存的配置
///
/// @validates Requirements 17.3
#[tauri::command]
pub async fn save_config(app: AppHandle, config: AppConfig) -> HuGeResult<()> {
    info!("保存应用配置...");

    let config_path = get_config_path(&app)?;
    db_save_config(&config_path, &config)?;

    info!("配置保存成功");
    Ok(())
}

/// 导出配置到指定文件
///
/// 将当前配置导出到用户指定的文件路径。
///
/// # 参数
///
/// - `file_path`: 导出文件路径
/// - `config`: 要导出的配置
///
/// @validates Requirements 17.4
#[tauri::command]
pub async fn export_config(file_path: String, config: AppConfig) -> HuGeResult<()> {
    info!("导出配置到: {}", file_path);

    let path = Path::new(&file_path);

    // 确保目录存在
    if let Some(parent) = path.parent() {
        if !parent.exists() {
            fs::create_dir_all(parent).map_err(|e| {
                error!("创建导出目录失败: {}", e);
                HuGeError::ConfigError(format!("创建导出目录失败: {}", e))
            })?;
        }
    }

    // 序列化为 JSON
    let content = serde_json::to_string_pretty(&config).map_err(|e| {
        error!("序列化配置失败: {}", e);
        HuGeError::ConfigError(format!("序列化配置失败: {}", e))
    })?;

    // 写入文件
    fs::write(path, &content).map_err(|e| {
        error!("写入导出文件失败: {}", e);
        HuGeError::ConfigError(format!("写入导出文件失败: {}", e))
    })?;

    info!("配置导出成功");
    Ok(())
}

/// 从文件导入配置
///
/// 从用户指定的文件路径导入配置。
///
/// # 参数
///
/// - `file_path`: 导入文件路径
///
/// # 返回
///
/// 返回导入的配置
///
/// @validates Requirements 17.4
#[tauri::command]
pub async fn import_config(file_path: String) -> HuGeResult<AppConfig> {
    info!("从文件导入配置: {}", file_path);

    let path = Path::new(&file_path);

    // 检查文件是否存在
    if !path.exists() {
        error!("导入文件不存在: {}", file_path);
        return Err(HuGeError::ConfigError(format!("导入文件不存在: {}", file_path)));
    }

    // 读取文件内容
    let content = fs::read_to_string(path).map_err(|e| {
        error!("读取导入文件失败: {}", e);
        HuGeError::ConfigError(format!("读取导入文件失败: {}", e))
    })?;

    // 解析 JSON
    let config: AppConfig = serde_json::from_str(&content).map_err(|e| {
        error!("解析导入文件失败: {}", e);
        HuGeError::ConfigError(format!("配置文件格式错误: {}", e))
    })?;

    info!("配置导入成功");
    Ok(config)
}

/// 设置 Windows 自动启动
///
/// 通过 Windows 注册表设置应用开机自启动。
/// 使用 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
///
/// # 参数
///
/// - `enabled`: 是否启用自动启动
///
/// @validates Requirements 17.5
#[tauri::command]
pub async fn set_auto_start(_app: AppHandle, enabled: bool) -> HuGeResult<()> {
    info!("设置自动启动: {}", enabled);

    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;

        let hkcu = RegKey::predef(HKEY_CURRENT_USER);
        let run_key = hkcu
            .open_subkey_with_flags(
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                KEY_READ | KEY_WRITE,
            )
            .map_err(|e| {
                error!("打开注册表失败: {}", e);
                HuGeError::ConfigError(format!("打开注册表失败: {}", e))
            })?;

        let app_name = "HuGeScreenshot";

        if enabled {
            // 获取当前可执行文件路径
            let exe_path = std::env::current_exe().map_err(|e| {
                error!("获取可执行文件路径失败: {}", e);
                HuGeError::ConfigError(format!("获取可执行文件路径失败: {}", e))
            })?;

            let exe_path_str = exe_path.to_string_lossy().to_string();

            // 如果路径包含空格，需要加引号
            // 添加 --minimized 标志：开机自启动时静默启动到托盘（不显示主窗口）
            let value = if exe_path_str.contains(' ') {
                format!("\"{}\" --minimized", exe_path_str)
            } else {
                format!("{} --minimized", exe_path_str)
            };

            run_key.set_value(app_name, &value).map_err(|e| {
                error!("设置注册表值失败: {}", e);
                HuGeError::ConfigError(format!("设置自动启动失败: {}", e))
            })?;

            info!("自动启动已启用（静默模式）: {}", value);
        } else {
            // 删除注册表项（忽略不存在的情况）
            match run_key.delete_value(app_name) {
                Ok(_) => info!("自动启动已禁用"),
                Err(e) => {
                    // 如果键不存在，不算错误
                    if e.kind() != std::io::ErrorKind::NotFound {
                        warn!("删除注册表值失败（可能不存在）: {}", e);
                    }
                }
            }
        }

        Ok(())
    }

    #[cfg(not(windows))]
    {
        warn!("自动启动功能仅支持 Windows 平台");
        Err(HuGeError::ConfigError("自动启动功能仅支持 Windows 平台".to_string()))
    }
}

/// 检查自动启动状态
///
/// 检查应用是否已设置为开机自启动。
///
/// # 返回
///
/// 返回是否已启用自动启动
///
/// @validates Requirements 17.5
#[tauri::command]
pub async fn check_auto_start() -> HuGeResult<bool> {
    debug!("检查自动启动状态...");

    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;

        let hkcu = RegKey::predef(HKEY_CURRENT_USER);

        match hkcu.open_subkey(r"Software\Microsoft\Windows\CurrentVersion\Run") {
            Ok(run_key) => {
                let app_name = "HuGeScreenshot";
                match run_key.get_value::<String, _>(app_name) {
                    Ok(value) => {
                        debug!("自动启动已启用: {}", value);
                        Ok(true)
                    }
                    Err(_) => {
                        debug!("自动启动未启用");
                        Ok(false)
                    }
                }
            }
            Err(e) => {
                warn!("打开注册表失败: {}", e);
                Ok(false)
            }
        }
    }

    #[cfg(not(windows))]
    {
        warn!("自动启动功能仅支持 Windows 平台");
        Ok(false)
    }
}

/// 更新单个热键
///
/// 更新指定动作的热键配置。
///
/// # 参数
///
/// - `action`: 热键动作名称（screenshot, ocr, recording, pin）
/// - `shortcut`: 新的快捷键组合
///
/// @validates Requirements 17.2
#[tauri::command]
pub async fn update_hotkey(app: AppHandle, action: String, shortcut: String) -> HuGeResult<()> {
    info!("更新热键: {} -> {}", action, shortcut);

    // 获取旧的热键配置
    let config_path = get_config_path(&app)?;
    let mut config = db_load_config(&config_path)?;

    // 获取旧热键值
    let old_shortcut = match action.as_str() {
        "screenshot" => Some(config.hotkeys.screenshot.clone()),
        "workbench" => Some(config.hotkeys.workbench.clone()),
        "ocr" => Some(config.hotkeys.ocr.clone()),
        "recording" => Some(config.hotkeys.recording.clone()),
        "pin" => Some(config.hotkeys.pin.clone()),
        "mouseHighlight" => Some(config.hotkeys.mouse_highlight.clone()),
        _ => {
            warn!("未知的热键动作: {}", action);
            return Err(HuGeError::ConfigError(format!("未知的热键动作: {}", action)));
        }
    };

    // 空字符串表示清除热键
    if shortcut.is_empty() {
        info!("清除热键: {}", action);
        // 如果旧热键存在，先取消注册
        if let Some(ref old) = old_shortcut {
            if !old.is_empty() {
                if let Err(e) = crate::hotkey::unregister_hotkey(&app, old) {
                    warn!("取消注册热键失败: {}", e);
                    // 继续执行，不阻止清除配置
                }
            }
        }
    } else {
        // 调用热键模块的更新函数
        crate::hotkey::update_hotkey(&app, &action, old_shortcut.as_deref(), &shortcut)?;
    }

    // 更新配置
    match action.as_str() {
        "screenshot" => config.hotkeys.screenshot = shortcut,
        "workbench" => config.hotkeys.workbench = shortcut,
        "ocr" => config.hotkeys.ocr = shortcut,
        "recording" => config.hotkeys.recording = shortcut,
        "pin" => config.hotkeys.pin = shortcut,
        "mouseHighlight" => config.hotkeys.mouse_highlight = shortcut,
        _ => {} // 已经在上面处理过了
    }

    db_save_config(&config_path, &config)?;

    if let Err(e) = crate::tray::refresh_tray_menu(&app) {
        warn!("刷新托盘菜单失败: {}", e);
    }

    info!("热键更新成功");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_export_import_config() {
        let temp_dir = tempdir().unwrap();
        let export_path = temp_dir.path().join("exported_config.json");

        // 创建测试配置
        let mut config = AppConfig::default();
        config.general.language = "en-US".to_string();
        config.hotkeys.screenshot = "Ctrl+Alt+S".to_string();

        // 导出配置
        let content = serde_json::to_string_pretty(&config).unwrap();
        fs::write(&export_path, &content).unwrap();

        // 导入配置
        let imported_content = fs::read_to_string(&export_path).unwrap();
        let imported_config: AppConfig = serde_json::from_str(&imported_content).unwrap();

        // 验证
        assert_eq!(imported_config.general.language, "en-US");
        assert_eq!(imported_config.hotkeys.screenshot, "Ctrl+Alt+S");
    }

    #[cfg(windows)]
    #[test]
    fn test_auto_start_registry_path() {
        // 验证注册表路径格式正确
        let path = r"Software\Microsoft\Windows\CurrentVersion\Run";
        assert!(path.contains("Run"));
    }
}
