//! 窗口相关 Tauri 命令
//!
//! 封装窗口管理功能，暴露给前端调用。

// 窗口命令直接使用 window 模块中定义的 tauri::command
// 这里可以添加额外的命令封装

use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use tracing::{debug, info};

use crate::database::settings::get_cached_config;
use crate::error::{HuGeError, HuGeResult};

/// 根据配置获取 Tauri 窗口主题
///
/// 从缓存配置中读取用户设置的主题，映射为 Tauri 原生窗口主题。
/// - "light" → Light
/// - "dark" → Dark
/// - "system" 或未知 → None（跟随系统）
fn resolve_window_theme() -> Option<tauri::Theme> {
    match get_cached_config() {
        Some(config) => match config.general.theme.as_str() {
            "light" => Some(tauri::Theme::Light),
            "dark" => Some(tauri::Theme::Dark),
            _ => None, // "system" 或其他值，跟随系统
        },
        None => None, // 配置未加载，跟随系统
    }
}

/// 开始截图模式
///
/// 创建覆盖窗口并进入截图选区模式
#[tauri::command]
pub async fn start_capture_mode(app: tauri::AppHandle) -> HuGeResult<()> {
    // FUTURE: 实现截图模式（获取所有显示器、捕获截图、创建覆盖窗口）
    let _ = app;
    Err(crate::error::HuGeError::WindowError("尚未实现".to_string()))
}

/// 退出截图模式
///
/// 关闭所有覆盖窗口
#[tauri::command]
pub async fn exit_capture_mode(app: tauri::AppHandle) -> HuGeResult<()> {
    // FUTURE: 关闭所有覆盖窗口
    let _ = app;
    Err(crate::error::HuGeError::WindowError("尚未实现".to_string()))
}

/// OCR 结果数据
#[derive(Clone, serde::Serialize, serde::Deserialize)]
pub struct OcrResultPayload {
    pub text: String,
    pub boxes: Option<Vec<serde_json::Value>>,
    pub elapse: Option<f64>,
    /// OCR 对应的原始截图路径（用于面板对齐渲染）
    pub image_path: Option<String>,
}

/// 打开 OCR 结果弹窗
///
/// 创建独立的 OCR 结果窗口，显示识别结果
/// 参考 Python 版本的 OCRResultWindow
#[tauri::command]
pub async fn open_ocr_result_window(
    app: tauri::AppHandle,
    text: String,
    boxes: Option<Vec<serde_json::Value>>,
    elapse: Option<f64>,
    image_path: Option<String>,
) -> HuGeResult<()> {
    const WINDOW_LABEL: &str = "ocr-result";

    info!("打开 OCR 结果窗口...");

    // 检查窗口是否已存在
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        info!("OCR 结果窗口已存在，更新内容并激活");
        // 发送新的 OCR 结果到已有窗口
        let payload = OcrResultPayload { text, boxes, elapse, image_path };
        window
            .emit("ocr-result", payload)
            .map_err(|e| HuGeError::WindowError(format!("发送 OCR 结果失败: {}", e)))?;
        window.show().map_err(|e| HuGeError::WindowError(format!("显示窗口失败: {}", e)))?;
        window.set_focus().map_err(|e| HuGeError::WindowError(format!("聚焦窗口失败: {}", e)))?;
        return Ok(());
    }

    // 将 OCR 结果存储到 app state，前端可以通过命令获取
    // 这比事件推送更可靠，因为前端可以在准备好后主动获取
    {
        let state = app.state::<crate::state::AppState>();
        let mut ocr_result = state.pending_ocr_result.lock().await;
        *ocr_result = Some(OcrResultPayload {
            text: text.clone(),
            boxes: boxes.clone(),
            elapse,
            image_path: image_path.clone(),
        });
    }

    // 创建新窗口
    let _window = WebviewWindowBuilder::new(
        &app,
        WINDOW_LABEL,
        WebviewUrl::App("ocr-result.html".into()),
    )
    .title("识别结果")
    .inner_size(500.0, 400.0)
    .center()
    .resizable(true)
    .decorations(false) // 使用自定义标题栏
    .visible(true) // 直接显示窗口
    .focused(true)
    .always_on_top(true) // 默认置顶
    .theme(resolve_window_theme())
    .build()
    .map_err(|e| HuGeError::WindowError(format!("创建 OCR 结果窗口失败: {}", e)))?;

    info!("OCR 结果窗口创建成功");

    Ok(())
}

/// 获取待处理的 OCR 结果
///
/// 前端在 mounted 后调用此命令获取 OCR 结果
/// 比事件推送更可靠
#[tauri::command]
pub async fn get_pending_ocr_result(app: tauri::AppHandle) -> HuGeResult<Option<OcrResultPayload>> {
    let state = app.state::<crate::state::AppState>();
    let mut ocr_result = state.pending_ocr_result.lock().await;
    let result = ocr_result.take(); // 取出并清空
    Ok(result)
}

/// OCR 面板打开事件载荷
///
/// 当 OCR 面板创建成功后，通过 Tauri Event 通知 overlay 窗口
#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OcrPanelOpenedPayload {
    /// OCR 面板窗口标签
    pub window_label: String,
}

/// OCR 面板打开事件名称
pub const OCR_PANEL_OPENED_EVENT: &str = "ocr-panel-opened";

/// 打开 OCR 结果面板（不抢占焦点）
///
/// 创建 OCR 结果窗口，但不从 overlay 窗口抢占焦点。
/// 这允许用户在查看 OCR 结果的同时继续操作截图 overlay。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `text`: OCR 识别的文本内容
/// - `boxes`: 可选的文字框位置信息
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息
///
/// # 事件
///
/// 成功创建窗口后，会发送 `ocr-panel-opened` 事件，载荷为 `OcrPanelOpenedPayload`
///
/// # 注意事项
///
/// - 使用 `focused(false)` 创建窗口，避免抢占 overlay 焦点
/// - 窗口创建后立即可见，但不会自动获得焦点
/// - 用户点击 OCR 面板后才会获得焦点
///
/// **Validates: Requirements 4.1, 4.2**
#[tauri::command]
pub async fn open_ocr_panel_no_focus(
    app: tauri::AppHandle,
    text: String,
    boxes: Option<Vec<serde_json::Value>>,
    elapse: Option<f64>,
    image_path: Option<String>,
) -> HuGeResult<()> {
    const WINDOW_LABEL: &str = "ocr-result";

    info!("打开 OCR 结果面板（不抢占焦点）...");

    // 检查窗口是否已存在
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        info!("OCR 结果窗口已存在，更新内容（不抢占焦点）");
        // 发送新的 OCR 结果到已有窗口
        let payload = OcrResultPayload { text, boxes, elapse, image_path };
        window
            .emit("ocr-result", payload)
            .map_err(|e| HuGeError::WindowError(format!("发送 OCR 结果失败: {}", e)))?;
        window.show().map_err(|e| HuGeError::WindowError(format!("显示窗口失败: {}", e)))?;
        // 注意：不调用 set_focus()，保持 overlay 的焦点

        // 发送 ocr-panel-opened 事件通知 overlay
        let opened_payload = OcrPanelOpenedPayload { window_label: WINDOW_LABEL.to_string() };
        if let Err(e) = app.emit(OCR_PANEL_OPENED_EVENT, &opened_payload) {
            debug!("发送 ocr-panel-opened 事件失败: {}", e);
        }

        return Ok(());
    }

    // 将 OCR 结果存储到 app state，前端可以通过命令获取
    {
        let state = app.state::<crate::state::AppState>();
        let mut ocr_result = state.pending_ocr_result.lock().await;
        *ocr_result = Some(OcrResultPayload {
            text: text.clone(),
            boxes: boxes.clone(),
            elapse,
            image_path: image_path.clone(),
        });
    }

    // 创建新窗口（关键：focused(false) 不抢占焦点）
    // 根据 Tauri 2.0 最佳实践，使用 WebviewWindowBuilder 并设置 focused(false)
    let _window = WebviewWindowBuilder::new(
        &app,
        WINDOW_LABEL,
        WebviewUrl::App("ocr-result.html".into()),
    )
    .title("识别结果")
    .inner_size(500.0, 400.0)
    .center()
    .resizable(true)
    .decorations(false) // 使用自定义标题栏
    .visible(true) // 直接显示窗口
    .focused(false) // 关键：不抢占焦点，保持 overlay 的焦点
    .always_on_top(true) // 默认置顶
    .theme(resolve_window_theme())
    .build()
    .map_err(|e| HuGeError::WindowError(format!("创建 OCR 结果窗口失败: {}", e)))?;

    info!("OCR 结果面板创建成功（不抢占焦点）");

    // 发送 ocr-panel-opened 事件通知 overlay
    let opened_payload = OcrPanelOpenedPayload { window_label: WINDOW_LABEL.to_string() };
    if let Err(e) = app.emit(OCR_PANEL_OPENED_EVENT, &opened_payload) {
        debug!("发送 ocr-panel-opened 事件失败: {}", e);
    } else {
        debug!("已发送 ocr-panel-opened 事件: {:?}", WINDOW_LABEL);
    }

    Ok(())
}

/// 关闭 OCR 结果窗口
#[tauri::command]
pub async fn close_ocr_result_window(app: tauri::AppHandle) -> HuGeResult<()> {
    const WINDOW_LABEL: &str = "ocr-result";

    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        window
            .close()
            .map_err(|e| HuGeError::WindowError(format!("关闭 OCR 结果窗口失败: {}", e)))?;
    }

    Ok(())
}

/// 打开工作台窗口
///
/// 创建或激活工作台窗口，显示截图历史记录
#[tauri::command]
pub async fn open_workbench_window(app: tauri::AppHandle) -> HuGeResult<()> {
    const WINDOW_LABEL: &str = "workbench";

    info!("打开工作台窗口...");

    // 检查窗口是否已存在
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        info!("工作台窗口已存在，激活窗口");
        window.show().map_err(|e| HuGeError::WindowError(format!("显示窗口失败: {}", e)))?;
        window.set_focus().map_err(|e| HuGeError::WindowError(format!("聚焦窗口失败: {}", e)))?;
        return Ok(());
    }

    // 创建新窗口（初始隐藏，等前端渲染完成后再显示，避免白屏闪烁）
    // 使用 decorations(false) 实现自定义标题栏，与内容区域颜色一致
    let _window = WebviewWindowBuilder::new(
        &app,
        WINDOW_LABEL,
        WebviewUrl::App("workbench.html".into()),
    )
    .title("工作台")
    .inner_size(1000.0, 700.0)
    .center()
    .resizable(true)
    .decorations(false) // 禁用原生标题栏，使用自定义标题栏
    .visible(false) // 初始隐藏，前端 mounted 后调用 show()
    .focused(true)
    .theme(resolve_window_theme())
    .build()
    .map_err(|e| HuGeError::WindowError(format!("创建工作台窗口失败: {}", e)))?;

    info!("工作台窗口创建成功，等待前端渲染完成后显示");

    Ok(())
}
