//! 应用全局状态管理
//!
//! 存储需要跨窗口/命令共享的状态

use crate::commands::window_cmd::OcrResultPayload;
use tokio::sync::Mutex;

/// 应用全局状态
pub struct AppState {
    /// 待处理的 OCR 结果
    /// 用于 OCR 结果窗口创建后获取数据
    pub pending_ocr_result: Mutex<Option<OcrResultPayload>>,
}

impl AppState {
    /// 创建新的应用状态
    pub fn new() -> Self {
        Self { pending_ocr_result: Mutex::new(None) }
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}
