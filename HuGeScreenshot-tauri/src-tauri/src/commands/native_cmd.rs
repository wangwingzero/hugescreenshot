//! Tauri 命令（OCR / 翻译 / 文档检测，原生 Rust 实现）
//!
//! 历史沿革：原本通过 Python Sidecar 实现的服务现已全部迁移到 Rust 原生：
//! - OCR：OpenVINO 推理（call_ocr）+ 百度云端 OCR
//! - 翻译：HTTP 直接调用免费翻译 API（translate_text_direct）
//! - 文档检测：Windows 原生 API（get_open_documents_native）
//! - 录屏：原生 Windows API（commands/recording_cmd.rs）

use crate::database::settings::{
    get_config_path, load_config as load_app_config, OcrConfig as AppOcrConfig,
};
use crate::error::{HuGeError, HuGeResult};
use std::fmt::Display;
use tauri::AppHandle;
use tracing::{info, warn};

/// OCR 识别结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OcrResult {
    /// 识别的文本
    pub text: String,
    /// 文本区域列表
    pub boxes: Vec<OcrBox>,
    /// 处理耗时（秒）
    pub elapse: f64,
    /// 使用的 OCR 引擎
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub engine: Option<String>,
}

/// OCR 文本区域
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OcrBox {
    /// 文本内容
    pub text: String,
    /// 置信度 (0.0 - 1.0)
    pub confidence: f64,
    /// 边界框坐标
    pub box_coords: Vec<Vec<f64>>,
}

const LOCAL_OCR_RUNTIME_GUIDANCE: &str = "本地 OCR 运行库加载失败，请重新安装虎哥截图，或安装 Microsoft Visual C++ 2015-2022 Redistributable x64 后重试";
const LOCAL_OCR_CPU_GUIDANCE: &str = "当前设备的 CPU 或指令集暂不兼容本地 OCR，请切换到百度 OCR，或在支持 AVX2 的 64 位 Windows 设备上使用本地 OCR";

fn is_local_ocr_runtime_load_error(message: &str) -> bool {
    let lower = message.to_ascii_lowercase();
    lower.contains("openvino core 初始化失败")
        || lower.contains("openvino_c.dll")
        || lower.contains("loadlibraryexw failed")
        || lower.contains("could not be opened")
        || lower.contains("shared library")
        || lower.contains("vcruntime140")
        || lower.contains("msvcp140")
}

fn is_local_ocr_cpu_compatibility_error(message: &str) -> bool {
    let lower = message.to_ascii_lowercase();
    lower.contains("avx2")
        || lower.contains("sse4")
        || lower.contains("unsupported cpu")
        || lower.contains("instruction set")
        || lower.contains("illegal instruction")
        || lower.contains("not supported on this cpu")
        || lower.contains("platform doesn't support")
}

fn is_local_ocr_recoverable_error(message: &str) -> bool {
    is_local_ocr_runtime_load_error(message) || is_local_ocr_cpu_compatibility_error(message)
}

fn format_local_ocr_error(stage: &str, error: &impl Display) -> String {
    let raw = error.to_string();
    if is_local_ocr_runtime_load_error(&raw) {
        format!("{}。技术细节：{}", LOCAL_OCR_RUNTIME_GUIDANCE, raw)
    } else if is_local_ocr_cpu_compatibility_error(&raw) {
        format!("{}。技术细节：{}", LOCAL_OCR_CPU_GUIDANCE, raw)
    } else {
        format!("{}: {}", stage, raw)
    }
}

fn should_fallback_to_baidu(
    engine: &str,
    app_config: Option<&crate::database::settings::AppConfig>,
) -> bool {
    if matches!(engine, "baiduAccurate" | "baidu_accurate" | "baidu") {
        return false;
    }

    let Some(config) = app_config else {
        return false;
    };

    !config.ocr.baidu_api_key.trim().is_empty() && !config.ocr.baidu_secret_key.trim().is_empty()
}

fn normalize_requested_engine(
    engine: Option<String>,
    app_config: Option<&crate::database::settings::AppConfig>,
) -> String {
    engine
        .or_else(|| app_config.map(|config| config.ocr.engine.clone()))
        .unwrap_or_else(|| "local".to_string())
}

const OVERLAY_DWM_RELEASE_WAIT_MS: u64 = 160;

fn should_release_overlay_before_ocr(has_overlay_windows: bool) -> bool {
    has_overlay_windows
}

fn should_copy_ocr_text(copy_text: bool, text: &str) -> bool {
    copy_text && !text.trim().is_empty()
}

fn should_fail_on_clipboard_error(copy_failed: bool, open_panel: bool) -> bool {
    copy_failed && !open_panel
}

fn should_continue_after_ocr_panel_error(open_panel: bool) -> bool {
    open_panel
}

fn ocr_boxes_payload(result: &OcrResult) -> HuGeResult<Option<Vec<serde_json::Value>>> {
    match serde_json::to_value(&result.boxes)? {
        serde_json::Value::Array(boxes) => Ok(Some(boxes)),
        _ => Ok(Some(Vec::new())),
    }
}

async fn wait_for_overlay_dwm_release() {
    tokio::time::sleep(std::time::Duration::from_millis(overlay_dwm_release_wait_ms())).await;
}

fn overlay_dwm_release_wait_ms() -> u64 {
    OVERLAY_DWM_RELEASE_WAIT_MS
}

async fn release_overlay_before_direct_ocr(app: &AppHandle) -> HuGeResult<()> {
    if !should_release_overlay_before_ocr(crate::window::overlay::has_overlay_windows(app)) {
        return Ok(());
    }

    info!("直接 OCR 前检测到 overlay 窗口，先释放 overlay 以避免桌面黑屏");
    crate::window::overlay::hide_overlay_windows(app.clone()).await?;
    wait_for_overlay_dwm_release().await;
    Ok(())
}

async fn copy_ocr_text_to_clipboard(text: String) -> HuGeResult<()> {
    tokio::task::spawn_blocking(move || {
        let mut clipboard = arboard::Clipboard::new()
            .map_err(|e| HuGeError::OcrError(format!("访问剪贴板失败: {}", e)))?;
        clipboard.set_text(text).map_err(|e| HuGeError::OcrError(format!("写入剪贴板失败: {}", e)))
    })
    .await
    .map_err(|e| HuGeError::OcrError(format!("剪贴板后台线程执行失败: {}", e)))?
}

async fn present_ocr_result(
    app: AppHandle,
    text: String,
    boxes: Option<Vec<serde_json::Value>>,
    elapse: Option<f64>,
    image_path: Option<String>,
    open_panel: bool,
    copy_text: bool,
) -> HuGeResult<()> {
    let mut clipboard_error = None;
    if should_copy_ocr_text(copy_text, &text) {
        if let Err(error) = copy_ocr_text_to_clipboard(text.clone()).await {
            warn!("OCR 文本复制失败，继续尝试展示结果面板: {}", error);
            clipboard_error = Some(error);
        }
    }

    if open_panel {
        if let Err(error) = crate::commands::window_cmd::open_ocr_panel_no_focus(
            app, text, boxes, elapse, image_path,
        )
        .await
        {
            warn!("打开 OCR 结果面板失败，保留 OCR 结果并继续返回: {}", error);
            if !should_continue_after_ocr_panel_error(open_panel) {
                return Err(error);
            }
        }
    }

    if should_fail_on_clipboard_error(clipboard_error.is_some(), open_panel) {
        if let Some(error) = clipboard_error {
            return Err(error);
        }
    }

    Ok(())
}

// 录屏相关类型和命令已迁移到 recording_cmd.rs（原生 Rust 实现）

/// 调用 OCR 服务（原生 Rust 实现）
///
/// 使用 PP-OCRv5 模型进行文字识别，无需 Python Sidecar。
///
/// # 参数
///
/// - `image_path`: 图像文件路径
///
/// # 返回
///
/// 返回 OCR 识别结果，包含识别的文本、文本区域边界框和处理耗时
///
/// # 示例
///
/// ```ignore
/// let result = call_ocr("/tmp/screenshot.png").await?;
/// println!("识别到的文字: {}", result.text);
/// for box in result.boxes {
///     println!("区域: {} (置信度: {})", box.text, box.confidence);
/// }
/// ```
#[tauri::command]
pub async fn call_ocr(
    app: AppHandle,
    image_path: String,
    engine: Option<String>,
) -> HuGeResult<OcrResult> {
    release_overlay_before_direct_ocr(&app).await?;

    let app_config = match get_config_path(&app).and_then(|path| load_app_config(&path)) {
        Ok(config) => Some(config),
        Err(e) => {
            warn!("加载 OCR 配置失败，将回退到本地 OCR: {}", e);
            None
        }
    };

    let selected_engine = normalize_requested_engine(engine, app_config.as_ref());

    match selected_engine.as_str() {
        "baiduAccurate" | "baidu_accurate" | "baidu" => {
            let config = app_config
                .as_ref()
                .ok_or_else(|| HuGeError::ConfigError("无法加载百度 OCR 配置".to_string()))?;
            call_baidu_accurate_ocr(&image_path, &config.ocr).await
        }
        _ => match call_local_ocr(image_path.clone()).await {
            Ok(result) => Ok(result),
            Err(error) => {
                let raw = error.to_string();
                if is_local_ocr_recoverable_error(&raw)
                    && should_fallback_to_baidu(&selected_engine, app_config.as_ref())
                {
                    warn!("本地 OCR 不可用，自动回退到百度 OCR: {}", raw);
                    let config = app_config.as_ref().expect("已验证百度 OCR 配置存在");
                    return call_baidu_accurate_ocr(&image_path, &config.ocr).await;
                }
                Err(error)
            }
        },
    }
}

#[tauri::command]
pub async fn safe_ocr_after_overlay_hidden(
    app: AppHandle,
    image_path: String,
    engine: Option<String>,
    open_panel: bool,
    copy_text: bool,
) -> HuGeResult<OcrResult> {
    info!("安全 OCR 流程启动：先释放 overlay，再执行 OCR: {}", image_path);
    crate::window::overlay::hide_overlay_windows(app.clone()).await?;
    wait_for_overlay_dwm_release().await;

    let result = call_ocr(app.clone(), image_path.clone(), engine).await?;
    let boxes = ocr_boxes_payload(&result)?;

    present_ocr_result(
        app,
        result.text.clone(),
        boxes,
        Some(result.elapse),
        Some(image_path),
        open_panel,
        copy_text,
    )
    .await?;

    Ok(result)
}

#[tauri::command]
pub async fn present_ocr_result_after_overlay_hidden(
    app: AppHandle,
    text: String,
    boxes: Option<Vec<serde_json::Value>>,
    elapse: Option<f64>,
    image_path: Option<String>,
    open_panel: bool,
    copy_text: bool,
) -> HuGeResult<()> {
    info!("安全展示 OCR 结果：先释放 overlay，再复制/打开面板");
    crate::window::overlay::hide_overlay_windows(app.clone()).await?;
    wait_for_overlay_dwm_release().await;

    present_ocr_result(app, text, boxes, elapse, image_path, open_panel, copy_text).await
}

async fn call_local_ocr(image_path: String) -> HuGeResult<OcrResult> {
    use crate::ocr::OcrEngine;

    info!("调用原生 OCR 服务: {}", image_path);

    let native_result = tokio::task::spawn_blocking(move || {
        let engine = OcrEngine::instance().map_err(|e| {
            crate::error::HuGeError::OcrError(format_local_ocr_error("OCR 引擎初始化失败", &e))
        })?;

        engine.recognize_blocking(&image_path).map_err(|e| {
            crate::error::HuGeError::OcrError(format_local_ocr_error("OCR 识别失败", &e))
        })
    })
    .await
    .map_err(|e| crate::error::HuGeError::OcrError(format!("OCR 后台线程执行失败: {}", e)))??;

    info!("OCR 完成: {} 个文本区域, 耗时 {:.2}s", native_result.boxes.len(), native_result.elapse);

    // 转换为命令返回类型
    let boxes: Vec<OcrBox> = native_result
        .boxes
        .into_iter()
        .map(|b| OcrBox { text: b.text, confidence: b.confidence, box_coords: b.box_coords })
        .collect();

    Ok(OcrResult {
        text: native_result.text,
        boxes,
        elapse: native_result.elapse,
        engine: Some("local".to_string()),
    })
}

#[derive(Debug, serde::Deserialize)]
struct BaiduTokenResponse {
    access_token: Option<String>,
    error: Option<String>,
    error_description: Option<String>,
}

#[derive(Debug, serde::Deserialize)]
struct BaiduOcrResponse {
    words_result: Option<Vec<BaiduWordResult>>,
    error_code: Option<i64>,
    error_msg: Option<String>,
}

#[derive(Debug, serde::Deserialize)]
struct BaiduWordResult {
    words: String,
    #[serde(default)]
    probability: Option<BaiduProbability>,
    #[serde(default)]
    location: Option<BaiduLocation>,
}

#[derive(Debug, serde::Deserialize)]
struct BaiduProbability {
    #[serde(default)]
    average: Option<f64>,
}

#[derive(Debug, serde::Deserialize)]
struct BaiduLocation {
    left: f64,
    top: f64,
    width: f64,
    height: f64,
}

async fn call_baidu_accurate_ocr(image_path: &str, config: &AppOcrConfig) -> HuGeResult<OcrResult> {
    use base64::{engine::general_purpose, Engine as _};
    use reqwest::header::CONTENT_TYPE;
    use std::time::Instant;
    use tracing::info;

    let api_key = config.baidu_api_key.trim();
    let secret_key = config.baidu_secret_key.trim();
    if api_key.is_empty() || secret_key.is_empty() {
        return Err(HuGeError::OcrError(
            "请先在设置 > OCR 中填写百度 OCR API Key 和 Secret Key".to_string(),
        ));
    }

    info!("调用百度高精度 OCR 服务: {}", image_path);
    let start = Instant::now();

    let image_data = tokio::fs::read(image_path).await.map_err(HuGeError::FileError)?;
    let image_base64 = general_purpose::STANDARD.encode(image_data);

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| HuGeError::OcrError(format!("创建百度 OCR 客户端失败: {}", e)))?;

    let access_token = fetch_baidu_access_token(&client, api_key, secret_key).await?;
    let url = format!(
        "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={}",
        urlencoding::encode(&access_token)
    );

    let body = format!(
        "image={}&detect_direction={}&probability={}",
        urlencoding::encode(&image_base64),
        if config.baidu_detect_direction { "true" } else { "false" },
        if config.baidu_probability { "true" } else { "false" },
    );

    let response = client
        .post(url)
        .header(CONTENT_TYPE, "application/x-www-form-urlencoded")
        .body(body)
        .send()
        .await
        .map_err(|e| HuGeError::OcrError(format!("百度 OCR 请求失败: {}", e)))?;

    let status = response.status();
    let response_text = response
        .text()
        .await
        .map_err(|e| HuGeError::OcrError(format!("读取百度 OCR 响应失败: {}", e)))?;

    if !status.is_success() {
        return Err(HuGeError::OcrError(format!("百度 OCR HTTP 错误: {}", status)));
    }

    let baidu_result: BaiduOcrResponse = serde_json::from_str(&response_text)
        .map_err(|e| HuGeError::OcrError(format!("解析百度 OCR 响应失败: {}", e)))?;

    if let Some(error_code) = baidu_result.error_code {
        let message = baidu_result.error_msg.unwrap_or_else(|| "未知错误".to_string());
        return Err(HuGeError::OcrError(format!("百度 OCR 错误 {}: {}", error_code, message)));
    }

    let words = baidu_result.words_result.unwrap_or_default();
    let boxes: Vec<OcrBox> = words
        .iter()
        .filter(|item| !item.words.trim().is_empty())
        .map(|item| OcrBox {
            text: item.words.trim().to_string(),
            confidence: item
                .probability
                .as_ref()
                .and_then(|probability| probability.average)
                .unwrap_or(1.0),
            box_coords: item.location.as_ref().map(location_to_box_coords).unwrap_or_default(),
        })
        .collect();

    let text = boxes.iter().map(|item| item.text.as_str()).collect::<Vec<_>>().join("\n");

    let elapse = start.elapsed().as_secs_f64();
    info!("百度高精度 OCR 完成: {} 个文本区域, 耗时 {:.2}s", boxes.len(), elapse);

    Ok(OcrResult { text, boxes, elapse, engine: Some("baiduAccurate".to_string()) })
}

async fn fetch_baidu_access_token(
    client: &reqwest::Client,
    api_key: &str,
    secret_key: &str,
) -> HuGeResult<String> {
    let response = client
        .post("https://aip.baidubce.com/oauth/2.0/token")
        .query(&[
            ("grant_type", "client_credentials"),
            ("client_id", api_key),
            ("client_secret", secret_key),
        ])
        .send()
        .await
        .map_err(|e| HuGeError::OcrError(format!("获取百度 access_token 失败: {}", e)))?;

    let status = response.status();
    let response_text = response
        .text()
        .await
        .map_err(|e| HuGeError::OcrError(format!("读取百度 token 响应失败: {}", e)))?;

    if !status.is_success() {
        return Err(HuGeError::OcrError(format!("百度 token HTTP 错误: {}", status)));
    }

    let token_response: BaiduTokenResponse = serde_json::from_str(&response_text)
        .map_err(|e| HuGeError::OcrError(format!("解析百度 token 响应失败: {}", e)))?;

    if let Some(token) = token_response.access_token {
        return Ok(token);
    }

    let message = token_response
        .error_description
        .or(token_response.error)
        .unwrap_or_else(|| "未返回 access_token".to_string());
    Err(HuGeError::OcrError(format!("获取百度 access_token 失败: {}", message)))
}

fn location_to_box_coords(location: &BaiduLocation) -> Vec<Vec<f64>> {
    let left = location.left;
    let top = location.top;
    let right = location.left + location.width;
    let bottom = location.top + location.height;

    vec![vec![left, top], vec![right, top], vec![right, bottom], vec![left, bottom]]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::settings::{AppConfig, OcrConfig as AppOcrConfig};

    fn configured_app_config() -> AppConfig {
        AppConfig {
            ocr: AppOcrConfig {
                engine: "local".to_string(),
                default_language: "zh-CN".to_string(),
                auto_translate: false,
                translate_provider: "".to_string(),
                translate_target_lang: "".to_string(),
                baidu_api_key: "key".to_string(),
                baidu_secret_key: "secret".to_string(),
                baidu_detect_direction: true,
                baidu_probability: true,
            },
            ..Default::default()
        }
    }

    #[test]
    fn cpu_compatibility_errors_are_marked_recoverable() {
        assert!(is_local_ocr_cpu_compatibility_error(
            "OpenVINO failed: unsupported CPU without AVX2"
        ));
        assert!(is_local_ocr_recoverable_error(
            "Illegal instruction while initializing OCR runtime"
        ));
        assert!(!is_local_ocr_cpu_compatibility_error("network timeout"));
    }

    #[test]
    fn local_ocr_cpu_errors_return_cpu_guidance() {
        let message = format_local_ocr_error("OCR 引擎初始化失败", &"unsupported CPU without AVX2");
        assert!(message.contains("CPU 或指令集暂不兼容本地 OCR"));
        assert!(message.contains("AVX2"));
    }

    #[test]
    fn normalize_requested_engine_prefers_explicit_value() {
        let config = configured_app_config();
        assert_eq!(
            normalize_requested_engine(Some("baiduAccurate".to_string()), Some(&config)),
            "baiduAccurate"
        );
        assert_eq!(normalize_requested_engine(None, Some(&config)), "local");
        assert_eq!(normalize_requested_engine(None, None), "local");
    }

    #[test]
    fn baidu_fallback_requires_credentials_and_non_baidu_request() {
        let config = configured_app_config();
        assert!(should_fallback_to_baidu("local", Some(&config)));
        assert!(!should_fallback_to_baidu("baiduAccurate", Some(&config)));

        let mut no_secret = configured_app_config();
        no_secret.ocr.baidu_api_key.clear();
        assert!(!should_fallback_to_baidu("local", Some(&no_secret)));
        assert!(!should_fallback_to_baidu("local", None));
    }

    #[test]
    fn copy_text_requires_non_empty_ocr_text() {
        assert!(should_copy_ocr_text(true, "识别结果"));
        assert!(!should_copy_ocr_text(true, "   \n"));
        assert!(!should_copy_ocr_text(false, "识别结果"));
    }

    #[test]
    fn clipboard_error_is_ignored_when_result_panel_opens() {
        assert!(should_fail_on_clipboard_error(true, false));
        assert!(!should_fail_on_clipboard_error(true, true));
        assert!(!should_fail_on_clipboard_error(false, false));
    }

    #[test]
    fn panel_open_error_does_not_discard_completed_ocr_result() {
        assert!(should_continue_after_ocr_panel_error(true));
        assert!(!should_continue_after_ocr_panel_error(false));
    }

    #[test]
    fn direct_ocr_releases_overlay_only_when_overlay_exists() {
        assert!(should_release_overlay_before_ocr(true));
        assert!(!should_release_overlay_before_ocr(false));
    }

    #[test]
    fn overlay_dwm_release_wait_is_long_enough_for_webview2_teardown() {
        assert!(overlay_dwm_release_wait_ms() >= 160);
    }

    #[test]
    fn ocr_boxes_payload_serializes_command_boxes() {
        let result = OcrResult {
            text: "hello".to_string(),
            boxes: vec![OcrBox {
                text: "hello".to_string(),
                confidence: 0.98,
                box_coords: vec![vec![0.0, 0.0], vec![10.0, 0.0]],
            }],
            elapse: 0.12,
            engine: Some("local".to_string()),
        };

        let boxes = ocr_boxes_payload(&result).expect("boxes should serialize").expect("array");

        assert_eq!(boxes.len(), 1);
        assert_eq!(boxes[0]["text"], "hello");
    }
}

// ============================================
// 直接翻译（不依赖 Sidecar）
// ============================================
//
// 使用免费翻译 API 直接翻译，无需 Python Sidecar。
// 支持多引擎回退：简心翻译（国内首选）→ MyMemory（海外备用）
// 支持智能语言检测：中文→英语，英语/其他→中文。

/// 直接翻译结果（不依赖 Sidecar，字段与前端 TranslateResult 类型对齐）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DirectTranslationResult {
    /// 翻译后的文本
    pub translated_text: String,
    /// 检测到的源语言
    pub source_lang: String,
    /// 目标语言
    pub target_lang: String,
    /// 使用的翻译提供商
    pub provider: String,
}

/// 简心翻译 API 响应结构
#[derive(Debug, serde::Deserialize)]
struct JianxinResponse {
    data: Option<JianxinResponseData>,
}

#[derive(Debug, serde::Deserialize)]
struct JianxinResponseData {
    #[serde(rename = "targetText")]
    target_text: Option<String>,
    text: Option<String>,
}

/// DeepLX API 响应结构
#[derive(Debug, serde::Deserialize)]
#[allow(dead_code)]
struct DeepLxResponse {
    code: Option<u32>,
    data: Option<String>,
    alternatives: Option<Vec<String>>,
}

/// MyMemory API 响应结构
#[derive(Debug, serde::Deserialize)]
struct MyMemoryResponse {
    #[serde(rename = "responseData")]
    response_data: MyMemoryResponseData,
    #[serde(rename = "responseStatus")]
    response_status: Option<u32>,
}

#[derive(Debug, serde::Deserialize)]
struct MyMemoryResponseData {
    #[serde(rename = "translatedText")]
    translated_text: String,
}

/// 直接翻译文本（不依赖 Sidecar）
///
/// 使用免费翻译 API 进行翻译，无需 Python Sidecar。
/// 多引擎回退：简心翻译（国内首选）→ MyMemory（海外备用）
/// 支持智能语言检测：
/// - 文本包含中文 → 翻译为英语
/// - 文本不含中文 → 翻译为中文
///
/// # 参数
///
/// - `text`: 要翻译的文本
/// - `target_lang`: 目标语言代码（可选，不提供时自动检测）
///
/// # 返回
///
/// 返回翻译结果，字段名使用 camelCase 以匹配前端 TranslateResult 类型
#[tauri::command]
pub async fn translate_text_direct(
    text: String,
    target_lang: Option<String>,
) -> HuGeResult<DirectTranslationResult> {
    use tracing::info;

    let text = text.trim().to_string();
    if text.is_empty() {
        return Err(crate::error::HuGeError::Unknown("没有可翻译的文字".to_string()));
    }

    // 智能语言检测（参考 Python 版本的 _do_smart_translate）
    let has_chinese = text.chars().any(|c| ('\u{4e00}'..='\u{9fff}').contains(&c));

    let (source, target) = match target_lang {
        Some(ref lang) if !lang.is_empty() => {
            if has_chinese {
                ("zh-CN".to_string(), lang.clone())
            } else {
                ("en".to_string(), lang.clone())
            }
        }
        _ => {
            // 智能检测：中文→英语，非中文→中文
            if has_chinese {
                ("zh-CN".to_string(), "en".to_string())
            } else {
                ("en".to_string(), "zh-CN".to_string())
            }
        }
    };

    info!("直接翻译: {} 字符, {} -> {}", text.len(), source, target);

    // 多引擎回退翻译
    let (translated, provider) = translate_with_fallback(&text, &source, &target).await?;

    info!("翻译完成({}): {} -> {} 字符", provider, text.len(), translated.len());

    Ok(DirectTranslationResult {
        translated_text: translated,
        source_lang: source,
        target_lang: target,
        provider,
    })
}

/// 多引擎回退翻译
///
/// 按优先级尝试：DeepLX（DeepL 引擎，翻译质量最高）→ 简心翻译（国内可用）→ MyMemory（海外备用）
/// 对长文本自动分段翻译。
async fn translate_with_fallback(
    text: &str,
    source: &str,
    target: &str,
) -> HuGeResult<(String, String)> {
    use tracing::warn;

    // 引擎 1：DeepLX（DeepL 引擎，翻译质量最高）
    match call_deeplx_api_chunked(text, source, target).await {
        Ok(translated) => return Ok((translated, "DeepLX".to_string())),
        Err(e) => {
            warn!("DeepLX 翻译失败，尝试简心翻译: {}", e);
        }
    }

    // 引擎 2：简心翻译（国内首选）
    match call_jianxin_api_chunked(text, source, target).await {
        Ok(translated) => return Ok((translated, "Jianxin".to_string())),
        Err(e) => {
            warn!("简心翻译失败，尝试 MyMemory: {}", e);
        }
    }

    // 引擎 3：MyMemory（海外备用）
    match call_mymemory_api_chunked(text, source, target).await {
        Ok(translated) => return Ok((translated, "MyMemory".to_string())),
        Err(e) => {
            warn!("MyMemory 翻译也失败: {}", e);
        }
    }

    Err(crate::error::HuGeError::Unknown("所有翻译引擎均失败，请检查网络连接".to_string()))
}

/// DeepLX 翻译（支持长文本分段）
async fn call_deeplx_api_chunked(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    if text.len() > 2000 {
        let chunks = split_text_into_chunks(text, 2000);
        let mut results = Vec::with_capacity(chunks.len());
        for chunk in &chunks {
            let translated = call_deeplx_api(chunk, source, target).await?;
            results.push(translated);
        }
        Ok(results.join(""))
    } else {
        call_deeplx_api(text, source, target).await
    }
}

/// 调用 DeepLX 翻译 API
///
/// DeepLX 是 DeepL 的免费代理，翻译质量极高。
/// 必须通过环境变量 DEEPLX_URL / DEEPLX_URL_FALLBACK 配置，仓库不内置任何代理地址。

async fn call_deeplx_api(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    let mut urls = Vec::new();
    for key in ["DEEPLX_URL", "DEEPLX_URL_FALLBACK"] {
        if let Ok(value) = std::env::var(key) {
            let value = value.trim();
            if !value.is_empty() {
                urls.push(value.to_string());
            }
        }
    }
    if urls.is_empty() {
        return Err(crate::error::HuGeError::Unknown(
            "DeepLX 未配置，请设置 DEEPLX_URL/DEEPLX_URL_FALLBACK".to_string(),
        ));
    }

    // DeepLX 语言代码映射（使用 DeepL 的语言代码）
    let source_lower = source.to_lowercase();
    let source_code = match source_lower.as_str() {
        "zh-cn" | "zh" => "ZH",
        "en" => "EN",
        "ja" => "JA",
        "ko" => "KO",
        "fr" => "FR",
        "de" => "DE",
        "es" => "ES",
        "ru" => "RU",
        "auto" | "" => "auto",
        _ => source,
    };

    let target_lower = target.to_lowercase();
    let target_code = match target_lower.as_str() {
        "zh-cn" | "zh" => "ZH",
        "en" => "EN",
        "ja" => "JA",
        "ko" => "KO",
        "fr" => "FR",
        "de" => "DE",
        "es" => "ES",
        "ru" => "RU",
        _ => target,
    };

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| crate::error::HuGeError::Unknown(format!("HTTP 客户端创建失败: {}", e)))?;

    let body = serde_json::json!({
        "text": text,
        "source_lang": source_code,
        "target_lang": target_code,
    });

    let mut last_err = String::new();
    for url in &urls {
        match client.post(url).json(&body).send().await {
            Ok(resp) if resp.status().is_success() => match resp.json::<DeepLxResponse>().await {
                Ok(api_resp) if api_resp.code == Some(200) => {
                    let translated = api_resp.data.unwrap_or_default();
                    if !translated.is_empty() {
                        return Ok(translated);
                    }
                    last_err = "DeepLX 返回空结果".to_string();
                }
                Ok(api_resp) => {
                    last_err = format!("DeepLX 返回错误码: {:?}", api_resp.code);
                }
                Err(e) => {
                    last_err = format!("DeepLX 响应解析失败: {}", e);
                }
            },
            Ok(resp) => {
                last_err = format!("DeepLX 返回错误状态: {}", resp.status());
            }
            Err(e) => {
                last_err = format!("DeepLX 请求失败: {}", e);
            }
        }
        tracing::warn!("DeepLX URL {} 失败: {}, 尝试下一个", url, last_err);
    }

    Err(crate::error::HuGeError::Unknown(last_err))
}

/// 简心翻译（支持长文本分段）
async fn call_jianxin_api_chunked(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    if text.len() > 1000 {
        let chunks = split_text_into_chunks(text, 1000);
        let mut results = Vec::with_capacity(chunks.len());
        for chunk in &chunks {
            let translated = call_jianxin_api(chunk, source, target).await?;
            results.push(translated);
        }
        Ok(results.join(""))
    } else {
        call_jianxin_api(text, source, target).await
    }
}

/// MyMemory 翻译（支持长文本分段）
async fn call_mymemory_api_chunked(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    if text.len() > 400 {
        let chunks = split_text_into_chunks(text, 400);
        let mut results = Vec::with_capacity(chunks.len());
        for chunk in &chunks {
            let translated = call_mymemory_api(chunk, source, target).await?;
            results.push(translated);
        }
        Ok(results.join(""))
    } else {
        call_mymemory_api(text, source, target).await
    }
}

/// 调用简心翻译 API
///
/// API 文档: https://api.qvqa.cn/api/fanyi
/// 国内免费翻译 API，无需 API Key，响应速度快。
async fn call_jianxin_api(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| crate::error::HuGeError::Unknown(format!("HTTP 客户端创建失败: {}", e)))?;

    // 简心翻译语言代码映射
    let target_lower = target.to_lowercase();
    let target_code = match target_lower.as_str() {
        "zh-cn" | "zh" => "zh",
        "zh-tw" => "zh",
        "en" => "en",
        "ja" => "ja",
        "ko" => "ko",
        "fr" => "fr",
        "de" => "de",
        "es" => "es",
        "ru" => "ru",
        other => other,
    };

    let source_lower = source.to_lowercase();
    let source_code = match source_lower.as_str() {
        "zh-cn" | "zh" => "zh",
        "en" => "en",
        "auto" | "" => "auto",
        other => other,
    };

    let mut params = vec![("text", text), ("target", target_code)];
    if source_code != "auto" {
        params.push(("source", source_code));
    }

    let resp = client
        .get("https://api.qvqa.cn/api/fanyi")
        .query(&params)
        .send()
        .await
        .map_err(|e| crate::error::HuGeError::Unknown(format!("简心翻译请求失败: {}", e)))?;

    if !resp.status().is_success() {
        return Err(crate::error::HuGeError::Unknown(format!(
            "简心翻译返回错误状态: {}",
            resp.status()
        )));
    }

    let api_resp: JianxinResponse = resp
        .json()
        .await
        .map_err(|e| crate::error::HuGeError::Unknown(format!("简心翻译响应解析失败: {}", e)))?;

    let translated = api_resp.data.and_then(|d| d.target_text.or(d.text)).unwrap_or_default();

    if translated.is_empty() {
        return Err(crate::error::HuGeError::Unknown("简心翻译返回空结果".to_string()));
    }

    Ok(translated)
}

/// 调用 MyMemory 翻译 API
///
/// API 文档: https://mymemory.translated.net/doc/spec.php
/// 免费额度: 5000 字符/天（匿名），50000 字符/天（提供邮箱）
async fn call_mymemory_api(text: &str, source: &str, target: &str) -> HuGeResult<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| crate::error::HuGeError::Unknown(format!("HTTP 客户端创建失败: {}", e)))?;

    let lang_pair = format!("{}|{}", source, target);

    let resp = client
        .get("https://api.mymemory.translated.net/get")
        .query(&[("q", text), ("langpair", &lang_pair)])
        .send()
        .await
        .map_err(|e| crate::error::HuGeError::Unknown(format!("翻译请求失败: {}", e)))?;

    if !resp.status().is_success() {
        return Err(crate::error::HuGeError::Unknown(format!(
            "翻译服务返回错误状态: {}",
            resp.status()
        )));
    }

    let api_resp: MyMemoryResponse = resp
        .json()
        .await
        .map_err(|e| crate::error::HuGeError::Unknown(format!("翻译响应解析失败: {}", e)))?;

    // 检查 API 状态
    if let Some(status) = api_resp.response_status {
        if status != 200 {
            return Err(crate::error::HuGeError::Unknown(format!(
                "翻译服务返回错误: status={}",
                status
            )));
        }
    }

    let translated = api_resp.response_data.translated_text;

    // 检查是否返回了警告信息（超出额度时 MyMemory 会返回警告文本而非翻译结果）
    if translated.contains("MYMEMORY WARNING") {
        return Err(crate::error::HuGeError::Unknown(
            "翻译服务今日免费额度已用完，请明天再试".to_string(),
        ));
    }

    if translated.is_empty() {
        return Err(crate::error::HuGeError::Unknown("翻译服务返回空结果".to_string()));
    }

    Ok(translated)
}

/// 将文本按段落/换行分割为不超过指定长度的块
fn split_text_into_chunks(text: &str, max_len: usize) -> Vec<String> {
    let mut chunks = Vec::new();
    let mut current = String::new();

    for line in text.lines() {
        // 如果加上当前行会超过限制，先保存已有内容
        if !current.is_empty() && current.len() + line.len() + 1 > max_len {
            chunks.push(current.clone());
            current.clear();
        }

        // 如果单行本身就超过限制，按字符分割
        if line.len() > max_len {
            if !current.is_empty() {
                chunks.push(current.clone());
                current.clear();
            }
            let mut remaining = line;
            while remaining.len() > max_len {
                // 在字符边界处分割
                let split_at = remaining
                    .char_indices()
                    .take_while(|(i, _)| *i <= max_len)
                    .last()
                    .map(|(i, c)| i + c.len_utf8())
                    .unwrap_or(max_len);
                chunks.push(remaining[..split_at].to_string());
                remaining = &remaining[split_at..];
            }
            if !remaining.is_empty() {
                current = remaining.to_string();
            }
        } else {
            if !current.is_empty() {
                current.push('\n');
            }
            current.push_str(line);
        }
    }

    if !current.is_empty() {
        chunks.push(current);
    }

    chunks
}

// 录屏命令已迁移到 recording_cmd.rs（原生 Rust 实现）

// ============================================
// 打开文档检测（不依赖 Sidecar，纯 Rust 实现）
// ============================================
//
// 使用 Win32 API EnumWindows 枚举窗口标题来检测打开的 Word/WPS 文档。
// 此方法不依赖 COM 或 Sidecar，不受管理员/普通用户权限隔离影响。

/// 打开的文档信息
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OpenDocumentInfo {
    /// 文档名称
    pub name: String,
    /// 完整路径（可能为空，窗口枚举无法获取完整路径）
    pub full_path: String,
    /// 应用类型 ("word" 或 "wps")
    pub app_type: String,
}

/// 获取打开的文档列表结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OpenDocumentsResult {
    pub success: bool,
    pub documents: Vec<OpenDocumentInfo>,
    pub available: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// 获取打开的 Word/WPS 文档列表（纯 Rust 实现，不依赖 Sidecar）
///
/// 使用 Win32 API 枚举窗口标题，从 WPS (wps.exe) 和 Word (WINWORD.EXE) 的
/// 窗口标题中提取文档名称。不受管理员/普通用户权限隔离影响。
#[tauri::command]
pub async fn get_open_documents_native() -> HuGeResult<OpenDocumentsResult> {
    use tracing::info;
    info!("纯 Rust 实现: 获取打开的 Word/WPS 文档列表");

    #[cfg(windows)]
    {
        get_open_documents_impl()
    }

    #[cfg(not(windows))]
    {
        Ok(OpenDocumentsResult {
            success: false,
            documents: vec![],
            available: false,
            error: Some("仅支持 Windows 平台".to_string()),
        })
    }
}

#[cfg(windows)]
fn get_open_documents_impl() -> HuGeResult<OpenDocumentsResult> {
    use std::collections::HashSet;
    use tracing::{debug, info};
    use windows::Win32::Foundation::{BOOL, HWND, LPARAM, TRUE};
    use windows::Win32::UI::WindowsAndMessaging::{
        EnumWindows, GetClassNameW, GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId,
        IsWindowVisible,
    };

    // Step 1: 获取 WPS 和 Word 进程 PID
    let mut word_pids: HashSet<u32> = HashSet::new();
    let mut wps_pids: HashSet<u32> = HashSet::new();

    // 使用 CreateToolhelp32Snapshot 枚举进程
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };

    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0).map_err(|e| {
            crate::error::HuGeError::WindowError(format!("CreateToolhelp32Snapshot 失败: {}", e))
        })?;

        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };

        if Process32FirstW(snapshot, &mut entry).is_ok() {
            loop {
                let exe_name: String = entry
                    .szExeFile
                    .iter()
                    .take_while(|&&c| c != 0)
                    .map(|&c| c as u8 as char)
                    .collect();
                let exe_lower = exe_name.to_lowercase();

                if exe_lower == "winword.exe" {
                    word_pids.insert(entry.th32ProcessID);
                } else if exe_lower == "wps.exe" {
                    wps_pids.insert(entry.th32ProcessID);
                }

                if Process32NextW(snapshot, &mut entry).is_err() {
                    break;
                }
            }
        }

        let _ = windows::Win32::Foundation::CloseHandle(snapshot);
    }

    if word_pids.is_empty() && wps_pids.is_empty() {
        info!("未检测到 Word 或 WPS 进程");
        return Ok(OpenDocumentsResult {
            success: true,
            documents: vec![],
            available: true,
            error: None,
        });
    }

    debug!("检测到进程 - Word PIDs: {:?}, WPS PIDs: {:?}", word_pids, wps_pids);

    let target_pids: HashSet<u32> = word_pids.union(&wps_pids).cloned().collect();

    // Step 2: 枚举窗口，提取文档信息
    struct WindowData {
        title: String,
        app_type: String,
    }

    let mut found_windows: Vec<WindowData> = Vec::new();
    let found_ptr = &mut found_windows as *mut Vec<WindowData>;

    // 在回调外部准备所需数据
    struct CallbackData {
        windows: *mut Vec<WindowData>,
        target_pids: HashSet<u32>,
        word_pids: HashSet<u32>,
    }

    let mut callback_data =
        CallbackData { windows: found_ptr, target_pids, word_pids: word_pids.clone() };
    let data_ptr = &mut callback_data as *mut CallbackData;

    unsafe extern "system" fn enum_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let data = &mut *(lparam.0 as *mut CallbackData);

        if !IsWindowVisible(hwnd).as_bool() {
            return TRUE;
        }

        let mut pid: u32 = 0;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));

        if !data.target_pids.contains(&pid) {
            return TRUE;
        }

        let length = GetWindowTextLengthW(hwnd);
        if length <= 0 {
            return TRUE;
        }

        let mut buf = vec![0u16; (length + 1) as usize];
        let actual_len = GetWindowTextW(hwnd, &mut buf);
        if actual_len <= 0 {
            return TRUE;
        }
        let title = String::from_utf16_lossy(&buf[..actual_len as usize]);

        // 获取窗口类名
        let mut class_buf = [0u16; 256];
        let class_len = GetClassNameW(hwnd, &mut class_buf);
        let class_name = if class_len > 0 {
            String::from_utf16_lossy(&class_buf[..class_len as usize])
        } else {
            String::new()
        };

        let app_type = if data.word_pids.contains(&pid) { "word" } else { "wps" };

        // 过滤：只保留主文档窗口
        let is_doc_window = if app_type == "word" {
            class_name.contains("OpusApp")
        } else {
            // WPS: Qt 窗口且标题包含文档后缀
            (class_name.contains("Qt") && class_name.contains("QWindow"))
                && (title.to_lowercase().contains(".doc")
                    || title.to_lowercase().contains(".docx")
                    || title.to_lowercase().contains(".wps"))
        };

        if is_doc_window {
            let windows = &mut *data.windows;
            windows.push(WindowData { title, app_type: app_type.to_string() });
        }

        TRUE
    }

    unsafe {
        let _ = EnumWindows(Some(enum_callback), LPARAM(data_ptr as isize));
    }

    // Step 3: 从窗口标题提取文档名
    let mut documents: Vec<OpenDocumentInfo> = Vec::new();
    let mut seen_names: HashSet<String> = HashSet::new();

    for win in &found_windows {
        if let Some(doc_name) = extract_doc_name_from_title(&win.title) {
            if !seen_names.contains(&doc_name) {
                seen_names.insert(doc_name.clone());
                documents.push(OpenDocumentInfo {
                    name: doc_name,
                    full_path: String::new(),
                    app_type: win.app_type.clone(),
                });
            }
        }
    }

    info!("纯 Rust 实现: 找到 {} 个打开的文档", documents.len());
    for doc in &documents {
        info!("  [{}] {}", doc.app_type, doc.name);
    }

    Ok(OpenDocumentsResult { success: true, documents, available: true, error: None })
}

/// 从窗口标题提取文档名
///
/// 支持的标题格式：
/// - Word: "文档名.docx - Word" 或 "文档名.docx  -  兼容模式 - Word"
/// - WPS:  "文档名.docx - WPS Office"
#[cfg(windows)]
fn extract_doc_name_from_title(title: &str) -> Option<String> {
    let extensions = [".docx", ".doc", ".docm", ".dotx", ".dotm", ".dot", ".wps", ".wpt"];

    let title_lower = title.to_lowercase();
    for ext in &extensions {
        if let Some(idx) = title_lower.rfind(ext) {
            let doc_name = title[..idx + ext.len()].trim().to_string();
            if !doc_name.is_empty() {
                return Some(doc_name);
            }
        }
    }

    None
}
