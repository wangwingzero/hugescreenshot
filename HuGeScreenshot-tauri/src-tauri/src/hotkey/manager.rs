//! 热键管理器
//!
//! 使用 tauri-plugin-global-shortcut 实现全局热键功能，支持：
//! - 热键注册和注销
//! - 热键冲突检测
//! - 运行时热键更新
//! - 热键触发事件发送到前端
//!
//! # 最佳实践（基于搜索结果）
//!
//! 1. 只处理 `ShortcutState::Pressed` 状态，避免 macOS 上的双触发问题
//! 2. 使用 `is_registered()` 检查冲突，但注意它只能检测当前应用的注册
//! 3. 在回调中只发送事件，让前端异步处理复杂业务逻辑
//! 4. 使用 try-catch 捕获注册错误，提示用户热键可能被占用

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Runtime};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tracing::{debug, error, info, warn};

use crate::error::{HuGeError, HuGeResult};

/// 热键配置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HotkeyConfig {
    /// 截图热键，默认: "Alt+X"
    pub screenshot: String,
    /// 工作台热键，默认: ""（未设置）
    #[serde(default)]
    pub workbench: String,
    /// OCR 热键，默认: "Ctrl+Shift+O"
    pub ocr: String,
    /// 录屏热键，默认: "Ctrl+Shift+R"
    pub recording: String,
    /// 钉图热键，默认: "Ctrl+Shift+P"
    pub pin: String,
    /// 鼠标高亮热键，默认: ""（未设置）
    #[serde(default, alias = "mouse_highlight")]
    pub mouse_highlight: String,
    /// 文件搜索热键，默认: "Alt+Space"
    /// **Validates: Requirements 8.1**
    #[serde(default = "default_file_search_hotkey", alias = "file_search")]
    pub file_search: String,
}

/// 默认文件搜索热键
fn default_file_search_hotkey() -> String {
    "Alt+Space".to_string()
}

impl Default for HotkeyConfig {
    fn default() -> Self {
        Self {
            screenshot: "Alt+X".to_string(),
            workbench: "Alt+P".to_string(),
            ocr: "Ctrl+Shift+O".to_string(),
            recording: "Ctrl+Shift+R".to_string(),
            pin: "Ctrl+Shift+P".to_string(),
            mouse_highlight: String::new(),
            file_search: default_file_search_hotkey(),
        }
    }
}

/// 热键动作类型
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum HotkeyAction {
    Screenshot,
    Workbench,
    Ocr,
    Recording,
    Pin,
    /// 文件搜索热键动作
    /// **Validates: Requirements 8.1**
    FileSearch,
}

impl HotkeyAction {
    /// 从字符串解析热键动作
    pub fn parse(s: &str) -> Option<Self> {
        s.parse().ok()
    }

    /// 转换为字符串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Screenshot => "screenshot",
            Self::Workbench => "workbench",
            Self::Ocr => "ocr",
            Self::Recording => "recording",
            Self::Pin => "pin",
            Self::FileSearch => "filesearch",
        }
    }
}

impl std::str::FromStr for HotkeyAction {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "screenshot" => Ok(Self::Screenshot),
            "workbench" => Ok(Self::Workbench),
            "ocr" => Ok(Self::Ocr),
            "recording" => Ok(Self::Recording),
            "pin" => Ok(Self::Pin),
            "filesearch" | "file_search" => Ok(Self::FileSearch),
            _ => Err(()),
        }
    }
}

/// 热键触发事件（发送到前端）
#[derive(Debug, Clone, Serialize)]
pub struct HotkeyEvent {
    /// 触发的动作
    pub action: HotkeyAction,
    /// 热键字符串
    pub shortcut: String,
    /// 时间戳（毫秒）
    pub timestamp: u64,
}

/// 热键冲突事件（发送到前端）
#[derive(Debug, Clone, Serialize)]
pub struct HotkeyConflictEvent {
    /// 冲突的热键
    pub shortcut: String,
    /// 对应的动作
    pub action: String,
    /// 错误信息
    pub error: String,
}

/// 获取当前时间戳（毫秒）
fn current_timestamp_ms() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

/// 设置全局热键
///
/// 在应用启动时调用，注册所有配置的热键。
///
/// # 参数
///
/// - `app`: Tauri 应用实例
/// - `config`: 热键配置
///
/// # 返回
///
/// 成功返回 Ok(())，失败返回错误信息
///
/// # 示例
///
/// ```ignore
/// let config = HotkeyConfig::default();
/// setup_hotkeys(&app, config)?;
/// ```
pub fn setup_hotkeys<R: Runtime>(app: &AppHandle<R>, config: HotkeyConfig) -> HuGeResult<()> {
    info!("开始注册全局热键...");
    debug!("热键配置: {:?}", config);

    // 注册截图热键
    if !config.screenshot.is_empty() {
        register_single_hotkey(app, &config.screenshot, HotkeyAction::Screenshot)?;
    }

    // 注册工作台热键
    if !config.workbench.is_empty() {
        register_single_hotkey(app, &config.workbench, HotkeyAction::Workbench)?;
    }

    // 注册 OCR 热键
    if !config.ocr.is_empty() {
        register_single_hotkey(app, &config.ocr, HotkeyAction::Ocr)?;
    }

    // 注册录屏热键
    if !config.recording.is_empty() {
        register_single_hotkey(app, &config.recording, HotkeyAction::Recording)?;
    }

    // 注册钉图热键
    if !config.pin.is_empty() {
        register_single_hotkey(app, &config.pin, HotkeyAction::Pin)?;
    }

    // 注册文件搜索热键 (Alt+Space)
    // **Validates: Requirements 8.1**
    if !config.file_search.is_empty() {
        register_single_hotkey(app, &config.file_search, HotkeyAction::FileSearch)?;
    }

    info!("全局热键注册完成");
    Ok(())
}

/// 注册单个热键
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `shortcut`: 热键字符串（如 "Ctrl+Shift+A"）
/// - `action`: 热键对应的动作
fn register_single_hotkey<R: Runtime>(
    app: &AppHandle<R>,
    shortcut: &str,
    action: HotkeyAction,
) -> HuGeResult<()> {
    let global_shortcut = app.global_shortcut();
    let action_str = action.as_str();

    // 检查热键是否已被当前应用注册
    // is_registered 返回 bool，不是 Result
    if global_shortcut.is_registered(shortcut) {
        warn!("热键 {} 已被注册，跳过", shortcut);
        return Ok(());
    }
    debug!("热键 {} 未被注册，准备注册", shortcut);

    // 克隆需要在闭包中使用的值
    let shortcut_clone = shortcut.to_string();
    let action_clone = action.clone();
    let app_handle = app.clone();

    // 注册热键并设置处理器
    match global_shortcut.on_shortcut(shortcut, move |_app, _shortcut, event| {
        // 只处理按下事件，避免 macOS 上的双触发问题
        if event.state == ShortcutState::Pressed {
            debug!("热键触发: {} -> {:?}", shortcut_clone, action_clone);

            // 发送事件到前端
            let hotkey_event = HotkeyEvent {
                action: action_clone.clone(),
                shortcut: shortcut_clone.clone(),
                timestamp: current_timestamp_ms(),
            };

            if let Err(e) = app_handle.emit("hotkey-triggered", &hotkey_event) {
                error!("发送热键事件失败: {}", e);
            }
        }
    }) {
        Ok(_) => {
            info!("热键注册成功: {} -> {}", shortcut, action_str);
            Ok(())
        }
        Err(e) => {
            let error_msg = format!("热键 {} 注册失败: {}", shortcut, e);
            error!("{}", error_msg);

            // 发送冲突事件到前端
            let conflict_event = HotkeyConflictEvent {
                shortcut: shortcut.to_string(),
                action: action_str.to_string(),
                error: e.to_string(),
            };

            if let Err(emit_err) = app.emit("hotkey-conflict", &conflict_event) {
                error!("发送热键冲突事件失败: {}", emit_err);
            }

            Err(HuGeError::HotkeyError(error_msg))
        }
    }
}

/// 更新单个热键
///
/// 先注销旧热键，再注册新热键。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `action`: 热键动作名称（screenshot, ocr, recording, pin）
/// - `shortcut`: 新的热键组合
///
/// # 返回
///
/// 成功返回 Ok(())，失败返回错误信息
///
/// # 示例
///
/// ```ignore
/// update_hotkey(&app, "screenshot", "Ctrl+Alt+S")?;
/// ```
pub fn update_hotkey<R: Runtime>(
    app: &AppHandle<R>,
    action: &str,
    old_shortcut: Option<&str>,
    new_shortcut: &str,
) -> HuGeResult<()> {
    info!("更新热键: {} -> {} (旧: {:?})", action, new_shortcut, old_shortcut);

    let global_shortcut = app.global_shortcut();

    // 解析动作类型
    let hotkey_action = HotkeyAction::parse(action)
        .ok_or_else(|| HuGeError::HotkeyError(format!("未知的热键动作: {}", action)))?;

    // 如果提供了旧热键，先注销
    if let Some(old) = old_shortcut {
        if !old.is_empty() {
            match global_shortcut.unregister(old) {
                Ok(_) => {
                    debug!("旧热键 {} 注销成功", old);
                }
                Err(e) => {
                    warn!("旧热键 {} 注销失败: {}", old, e);
                    // 继续尝试注册新热键
                }
            }
        }
    }

    // 注册新热键
    register_single_hotkey(app, new_shortcut, hotkey_action)?;

    info!("热键更新完成: {} -> {}", action, new_shortcut);
    Ok(())
}

/// 注销所有热键
///
/// 在应用退出时调用，确保所有热键被正确释放。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
pub fn unregister_all_hotkeys<R: Runtime>(app: &AppHandle<R>) -> HuGeResult<()> {
    info!("注销所有全局热键...");

    let global_shortcut = app.global_shortcut();

    match global_shortcut.unregister_all() {
        Ok(_) => {
            info!("所有热键注销成功");
            Ok(())
        }
        Err(e) => {
            let error_msg = format!("注销热键失败: {}", e);
            error!("{}", error_msg);
            Err(HuGeError::HotkeyError(error_msg))
        }
    }
}

/// 检查热键是否可用
///
/// 检查指定的热键是否已被注册（仅限当前应用）。
/// 注意：无法检测其他应用是否占用了该热键。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `shortcut`: 热键字符串
///
/// # 返回
///
/// 返回热键是否可用（未被当前应用注册）
pub fn is_hotkey_available<R: Runtime>(app: &AppHandle<R>, shortcut: &str) -> HuGeResult<bool> {
    let global_shortcut = app.global_shortcut();

    // is_registered 返回 bool，不是 Result
    let registered = global_shortcut.is_registered(shortcut);
    debug!("热键 {} 注册状态: {}", shortcut, registered);
    Ok(!registered)
}

/// 注销指定热键
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `shortcut`: 热键字符串
pub fn unregister_hotkey<R: Runtime>(app: &AppHandle<R>, shortcut: &str) -> HuGeResult<()> {
    let global_shortcut = app.global_shortcut();

    match global_shortcut.unregister(shortcut) {
        Ok(_) => {
            info!("热键 {} 注销成功", shortcut);
            Ok(())
        }
        Err(e) => {
            let error_msg = format!("热键 {} 注销失败: {}", shortcut, e);
            warn!("{}", error_msg);
            Err(HuGeError::HotkeyError(error_msg))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hotkey_config_default() {
        let config = HotkeyConfig::default();
        assert_eq!(config.screenshot, "Alt+X");
        assert_eq!(config.workbench, "Alt+P");
        assert_eq!(config.ocr, "Ctrl+Shift+O");
        assert_eq!(config.recording, "Ctrl+Shift+R");
        assert_eq!(config.pin, "Ctrl+Shift+P");
        assert_eq!(config.file_search, "Alt+Space");
    }

    #[test]
    fn test_hotkey_config_serialize() {
        let config = HotkeyConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        assert!(json.contains("Alt+X"));
        assert!(json.contains("screenshot"));
        assert!(json.contains("workbench"));
        assert!(json.contains("Alt+Space"));
        assert!(json.contains("fileSearch"));
    }

    #[test]
    fn test_hotkey_action_from_str() {
        assert_eq!(HotkeyAction::parse("screenshot"), Some(HotkeyAction::Screenshot));
        assert_eq!(HotkeyAction::parse("workbench"), Some(HotkeyAction::Workbench));
        assert_eq!(HotkeyAction::parse("OCR"), Some(HotkeyAction::Ocr));
        assert_eq!(HotkeyAction::parse("Recording"), Some(HotkeyAction::Recording));
        assert_eq!(HotkeyAction::parse("PIN"), Some(HotkeyAction::Pin));
        assert_eq!(HotkeyAction::parse("file_search"), Some(HotkeyAction::FileSearch));
        assert_eq!(HotkeyAction::parse("filesearch"), Some(HotkeyAction::FileSearch));
        assert_eq!(HotkeyAction::parse("unknown"), None);
    }

    #[test]
    fn test_hotkey_action_as_str() {
        assert_eq!(HotkeyAction::Screenshot.as_str(), "screenshot");
        assert_eq!(HotkeyAction::Workbench.as_str(), "workbench");
        assert_eq!(HotkeyAction::Ocr.as_str(), "ocr");
        assert_eq!(HotkeyAction::Recording.as_str(), "recording");
        assert_eq!(HotkeyAction::Pin.as_str(), "pin");
        assert_eq!(HotkeyAction::FileSearch.as_str(), "filesearch");
    }

    #[test]
    fn test_hotkey_event_serialize() {
        let event = HotkeyEvent {
            action: HotkeyAction::Screenshot,
            shortcut: "Ctrl+Shift+A".to_string(),
            timestamp: 1234567890,
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("screenshot"));
        assert!(json.contains("Ctrl+Shift+A"));
        assert!(json.contains("1234567890"));
    }

    #[test]
    fn test_hotkey_event_file_search_serialize() {
        let event = HotkeyEvent {
            action: HotkeyAction::FileSearch,
            shortcut: "Alt+Space".to_string(),
            timestamp: 1234567890,
        };
        let json = serde_json::to_string(&event).unwrap();
        // Note: serde rename_all = "lowercase" converts FileSearch to "filesearch"
        assert!(json.contains("filesearch"));
        assert!(json.contains("Alt+Space"));
    }

    #[test]
    fn test_hotkey_conflict_event_serialize() {
        let event = HotkeyConflictEvent {
            shortcut: "Ctrl+Shift+A".to_string(),
            action: "screenshot".to_string(),
            error: "热键已被占用".to_string(),
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("Ctrl+Shift+A"));
        assert!(json.contains("screenshot"));
        assert!(json.contains("热键已被占用"));
    }
}
