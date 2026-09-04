//! 热键相关 Tauri 命令
//!
//! 封装热键管理功能，暴露给前端调用。
//!
//! # 命令列表
//!
//! - `get_hotkey_config`: 获取当前热键配置
//! - `set_hotkey_config`: 更新热键配置
//! - `check_hotkey_available`: 检查热键是否可用
//! - `update_single_hotkey`: 更新单个热键

use tauri::AppHandle;
use tracing::{debug, info, warn};

use crate::database::settings::{get_config_path, load_config, save_hotkey_config};
use crate::error::HuGeResult;
use crate::hotkey::{is_hotkey_available, update_hotkey, HotkeyConfig};

/// 获取当前热键配置
///
/// 从配置文件加载热键配置。如果配置文件不存在，返回默认配置。
///
/// # 返回
///
/// 返回当前的热键配置
#[tauri::command]
pub async fn get_hotkey_config(app: AppHandle) -> HuGeResult<HotkeyConfig> {
    debug!("获取热键配置");

    // 从配置文件加载热键配置
    let config_path = get_config_path(&app)?;
    let config = load_config(&config_path)?;

    debug!("热键配置: {:?}", config.hotkeys);
    Ok(config.hotkeys)
}

/// 更新热键配置
///
/// 更新所有热键配置，会先注销旧热键再注册新热键。
/// 配置会自动保存到配置文件。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `config`: 新的热键配置
#[tauri::command]
pub async fn set_hotkey_config(app: AppHandle, config: HotkeyConfig) -> HuGeResult<()> {
    info!("更新热键配置: {:?}", config);

    // 获取旧配置
    let config_path = get_config_path(&app)?;
    let old_config = load_config(&config_path)?.hotkeys;

    // 更新截图热键
    if config.screenshot != old_config.screenshot {
        if let Err(e) =
            update_hotkey(&app, "screenshot", Some(&old_config.screenshot), &config.screenshot)
        {
            warn!("更新截图热键失败: {}", e);
            // 继续尝试更新其他热键
        }
    }

    // 更新工作台热键
    if config.workbench != old_config.workbench {
        if let Err(e) =
            update_hotkey(&app, "workbench", Some(&old_config.workbench), &config.workbench)
        {
            warn!("更新工作台热键失败: {}", e);
        }
    }

    // 更新 OCR 热键
    if config.ocr != old_config.ocr {
        if let Err(e) = update_hotkey(&app, "ocr", Some(&old_config.ocr), &config.ocr) {
            warn!("更新 OCR 热键失败: {}", e);
        }
    }

    // 更新录屏热键
    if config.recording != old_config.recording {
        if let Err(e) =
            update_hotkey(&app, "recording", Some(&old_config.recording), &config.recording)
        {
            warn!("更新录屏热键失败: {}", e);
        }
    }

    // 更新钉图热键
    if config.pin != old_config.pin {
        if let Err(e) = update_hotkey(&app, "pin", Some(&old_config.pin), &config.pin) {
            warn!("更新钉图热键失败: {}", e);
        }
    }

    // 保存配置到文件
    save_hotkey_config(&app, config)?;

    if let Err(e) = crate::tray::refresh_tray_menu(&app) {
        warn!("刷新托盘菜单失败: {}", e);
    }

    info!("热键配置更新完成");
    Ok(())
}

/// 检查热键是否可用
///
/// 检查指定的热键是否可以被注册。
/// 注意：只能检测当前应用是否已注册该热键，无法检测其他应用。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `shortcut`: 热键组合字符串
///
/// # 返回
///
/// 返回热键是否可用（未被当前应用占用）
#[tauri::command]
pub async fn check_hotkey_available(app: AppHandle, shortcut: String) -> HuGeResult<bool> {
    debug!("检查热键可用性: {}", shortcut);
    is_hotkey_available(&app, &shortcut)
}

/// 更新单个热键
///
/// 更新指定动作的热键绑定。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `action`: 热键动作（screenshot, ocr, recording, pin）
/// - `old_shortcut`: 旧的热键组合（可选）
/// - `new_shortcut`: 新的热键组合
#[tauri::command]
pub async fn update_single_hotkey(
    app: AppHandle,
    action: String,
    old_shortcut: Option<String>,
    new_shortcut: String,
) -> HuGeResult<()> {
    info!("更新单个热键: {} -> {} (旧: {:?})", action, new_shortcut, old_shortcut);
    update_hotkey(&app, &action, old_shortcut.as_deref(), &new_shortcut)
}
