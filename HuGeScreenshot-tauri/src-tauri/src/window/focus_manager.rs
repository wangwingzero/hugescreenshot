//! 多窗口焦点管理模块
//!
//! 本模块负责管理多个窗口之间的焦点状态通信，解决以下问题：
//! - 截图覆盖窗口与 OCR 结果面板的焦点冲突
//! - 窗口间的焦点状态同步
//! - 确保用户可以在多个窗口之间自由切换
//!
//! # 设计原则
//!
//! - 使用 Tauri Events 进行窗口间通信
//! - 焦点变化时发送 `focus-changed` 事件
//! - 所有窗口都可以监听焦点状态变化
//!
//! # 事件流
//!
//! ```text
//! 窗口 A 获得焦点
//!     ↓
//! emit_focus_change(app, "window-a", true)
//!     ↓
//! 所有窗口收到 focus-changed 事件
//!     ↓
//! 各窗口根据事件更新自身状态
//! ```
//!
//! **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter};
use tracing::{debug, warn};

/// 窗口焦点状态
///
/// 用于窗口间焦点状态通信的事件载荷。
/// 当窗口获得或失去焦点时，通过 Tauri Event 广播此状态。
///
/// # 字段
///
/// - `window_label`: 窗口标签，如 "overlay-0"、"ocr-result" 等
/// - `is_focused`: 是否获得焦点
/// - `timestamp`: 事件时间戳（Unix 毫秒），用于事件排序和去重
///
/// # 示例
///
/// ```ignore
/// let state = FocusState {
///     window_label: "overlay-0".to_string(),
///     is_focused: true,
///     timestamp: 1234567890123,
/// };
/// ```
///
/// **Validates: Requirements 5.1**
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FocusState {
    /// 窗口标签（唯一标识符）
    pub window_label: String,
    /// 是否获得焦点
    pub is_focused: bool,
    /// 事件时间戳（Unix 毫秒）
    pub timestamp: u64,
}

impl FocusState {
    /// 创建新的焦点状态
    ///
    /// # 参数
    ///
    /// - `window_label`: 窗口标签
    /// - `is_focused`: 是否获得焦点
    ///
    /// # 返回
    ///
    /// 返回带有当前时间戳的 `FocusState` 实例
    pub fn new(window_label: impl Into<String>, is_focused: bool) -> Self {
        let timestamp =
            SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0);

        Self { window_label: window_label.into(), is_focused, timestamp }
    }
}

/// 焦点变化事件名称
pub const FOCUS_CHANGED_EVENT: &str = "focus-changed";

/// 发送焦点变化事件
///
/// 当窗口获得或失去焦点时，调用此函数广播焦点状态变化。
/// 所有监听 `focus-changed` 事件的窗口都会收到通知。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `window_label`: 发生焦点变化的窗口标签
/// - `focused`: 是否获得焦点（true = 获得焦点，false = 失去焦点）
///
/// # 示例
///
/// ```ignore
/// // 窗口获得焦点时
/// emit_focus_change(&app, "overlay-0", true);
///
/// // 窗口失去焦点时
/// emit_focus_change(&app, "overlay-0", false);
/// ```
///
/// # 注意事项
///
/// - 此函数不会阻塞，事件发送失败只会记录警告日志
/// - 事件会广播给所有窗口，包括发送者自身
/// - 前端应根据 `window_label` 判断是否需要响应
///
/// **Validates: Requirements 5.1, 5.4**
pub fn emit_focus_change(app: &AppHandle, window_label: &str, focused: bool) {
    let state = FocusState::new(window_label, focused);

    debug!(
        "发送焦点变化事件: window={}, focused={}, timestamp={}",
        state.window_label, state.is_focused, state.timestamp
    );

    // 使用 emit 广播给所有窗口
    if let Err(e) = app.emit(FOCUS_CHANGED_EVENT, &state) {
        warn!("发送焦点变化事件失败: window={}, error={}", window_label, e);
    }
}

/// 发送焦点变化事件到指定窗口
///
/// 与 `emit_focus_change` 不同，此函数只向指定窗口发送事件。
/// 适用于需要精确控制事件接收者的场景。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `target_window`: 目标窗口标签
/// - `source_window`: 发生焦点变化的窗口标签
/// - `focused`: 是否获得焦点
///
/// # 示例
///
/// ```ignore
/// // 通知 OCR 面板：overlay 窗口失去了焦点
/// emit_focus_change_to(&app, "ocr-result", "overlay-0", false);
/// ```
pub fn emit_focus_change_to(
    app: &AppHandle,
    target_window: &str,
    source_window: &str,
    focused: bool,
) {
    let state = FocusState::new(source_window, focused);

    debug!(
        "发送焦点变化事件到 {}: source={}, focused={}, timestamp={}",
        target_window, state.window_label, state.is_focused, state.timestamp
    );

    // 使用 emit_to 发送给指定窗口
    if let Err(e) = app.emit_to(target_window, FOCUS_CHANGED_EVENT, &state) {
        warn!("发送焦点变化事件到 {} 失败: source={}, error={}", target_window, source_window, e);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_focus_state_new() {
        let state = FocusState::new("overlay-0", true);
        assert_eq!(state.window_label, "overlay-0");
        assert!(state.is_focused);
        assert!(state.timestamp > 0);
    }

    #[test]
    fn test_focus_state_serialization() {
        let state = FocusState {
            window_label: "ocr-result".to_string(),
            is_focused: false,
            timestamp: 1234567890123,
        };

        let json = serde_json::to_string(&state).unwrap();
        assert!(json.contains("windowLabel"));
        assert!(json.contains("isFocused"));
        assert!(json.contains("timestamp"));

        // 验证 camelCase 序列化
        assert!(json.contains("\"windowLabel\":\"ocr-result\""));
        assert!(json.contains("\"isFocused\":false"));
    }

    #[test]
    fn test_focus_state_deserialization() {
        let json = r#"{"windowLabel":"overlay-1","isFocused":true,"timestamp":9876543210}"#;
        let state: FocusState = serde_json::from_str(json).unwrap();

        assert_eq!(state.window_label, "overlay-1");
        assert!(state.is_focused);
        assert_eq!(state.timestamp, 9876543210);
    }

    #[test]
    fn test_focus_changed_event_name() {
        assert_eq!(FOCUS_CHANGED_EVENT, "focus-changed");
    }
}
