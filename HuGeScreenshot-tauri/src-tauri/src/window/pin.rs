//! 钉图窗口管理
//!
//! 创建和管理钉图窗口，支持将截图固定在屏幕上。
//!
//! # 功能特性
//!
//! - 置顶显示：窗口始终在其他窗口之上
//! - 无边框：自定义外观，无系统标题栏
//! - 可调整大小：支持拖拽边缘调整窗口尺寸
//! - 可移动：支持拖拽窗口移动位置
//! - 透明度调整：支持 0.0 - 1.0 范围的透明度
//! - 双击关闭：双击窗口即可关闭
//! - 多窗口支持：可同时创建多个钉图窗口
//!
//! # 使用场景
//!
//! - 参考截图：将截图固定在屏幕上作为参考
//! - 对比查看：同时钉住多张截图进行对比
//! - 临时备忘：将重要信息截图钉在桌面上

use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{LazyLock, Mutex};

use serde::{Deserialize, Serialize};
use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use tracing::{debug, error, info, warn};

use crate::error::{HuGeError, HuGeResult};
use crate::screenshot::capture::Rect;

/// 钉图窗口计数器，用于生成唯一的窗口标签
static PIN_WINDOW_COUNTER: AtomicU32 = AtomicU32::new(0);

/// 全局钉图窗口管理器
///
/// 存储所有已创建的钉图窗口标签，用于统一管理
static PIN_WINDOWS: Mutex<Vec<String>> = Mutex::new(Vec::new());

/// 钉图窗口初始化数据缓存
///
/// 解决 pin-init 事件可能在前端监听器注册前就发送导致事件丢失的问题：
/// 前端可以通过命令主动拉取初始化数据，避免竞态。
static PIN_INIT_CACHE: LazyLock<Mutex<HashMap<String, PinWindowInitInfo>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

/// 钉图窗口配置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PinWindowConfig {
    /// 图像路径
    pub image_path: String,
    /// 窗口位置和大小
    pub rect: Rect,
    /// 初始透明度 (0.0 - 1.0)
    pub opacity: f64,
}

/// 钉图窗口初始化信息
///
/// 发送给前端的初始化数据
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PinWindowInitInfo {
    /// 窗口标签
    pub label: String,
    /// 图像路径（asset:// 协议）
    pub image_path: String,
    /// 窗口宽度
    pub width: u32,
    /// 窗口高度
    pub height: u32,
    /// 初始透明度
    pub opacity: f64,
}

/// 创建钉图窗口
///
/// 创建一个置顶的无边框窗口，显示指定的截图。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `image_path`: 截图文件路径（支持绝对路径或 asset:// 协议）
/// - `rect`: 窗口位置和大小
///
/// # 返回
///
/// 成功返回窗口标签（label），失败返回错误信息
///
/// # 窗口特性
///
/// - `transparent`: false - 钉图窗口不需要透明背景
/// - `decorations`: false - 无边框、无标题栏
/// - `always_on_top`: true - 置顶显示
/// - `resizable`: true - 可调整大小
/// - `skip_taskbar`: true - 不在任务栏显示
///
/// # 示例
///
/// ```ignore
/// let label = create_pin_window(
///     app,
///     "/tmp/screenshot.png".to_string(),
///     Rect { x: 100, y: 100, width: 400, height: 300 }
/// ).await?;
/// println!("创建钉图窗口: {}", label);
/// ```
#[tauri::command]
pub async fn create_pin_window(
    app: tauri::AppHandle,
    image_path: String,
    rect: Rect,
) -> HuGeResult<String> {
    info!(
        "创建钉图窗口，图像: {}, 位置: ({}, {}), 尺寸: {}x{}",
        image_path, rect.x, rect.y, rect.width, rect.height
    );

    // 验证参数
    if image_path.is_empty() {
        return Err(HuGeError::WindowError("图像路径不能为空".to_string()));
    }
    if rect.width == 0 || rect.height == 0 {
        return Err(HuGeError::WindowError("窗口尺寸不能为零".to_string()));
    }

    // 生成唯一的窗口标签
    let window_id = PIN_WINDOW_COUNTER.fetch_add(1, Ordering::SeqCst);
    let window_label = format!("pin-{}", window_id);

    debug!("生成窗口标签: {}", window_label);

    // 检查窗口是否已存在（理论上不应该发生）
    if app.get_webview_window(&window_label).is_some() {
        warn!("钉图窗口 {} 已存在，跳过创建", window_label);
        return Err(HuGeError::WindowError(format!("窗口 {} 已存在", window_label)));
    }

    // 转换图像路径：直接传递原始文件路径给前端
    // 前端会使用 convertFileSrc 正确转换为 asset:// 协议
    let asset_path = if image_path.starts_with("asset://") {
        // 如果已经是 asset:// 协议，提取原始路径
        image_path.replace("asset://localhost/", "").replace("asset://", "")
    } else {
        image_path.clone()
    };

    debug!("图像文件路径: {}", asset_path);

    // 创建钉图窗口
    // 注意：使用 WebviewWindowBuilder 创建窗口
    let window = WebviewWindowBuilder::new(
        &app,
        &window_label,
        WebviewUrl::App("pin.html".into()),
    )
    // 核心属性：无边框、置顶、无阴影
    .decorations(false)
    .shadow(false)
    .always_on_top(true)
    // 窗口位置和尺寸
    .position(rect.x as f64, rect.y as f64)
    .inner_size(rect.width as f64, rect.height as f64)
    // 窗口行为
    .resizable(true)
    .skip_taskbar(true)
    .maximizable(false)
    .minimizable(true)
    // 初始状态
    .visible(true)
    .focused(true)
    // 窗口标题（调试用）
    .title(format!("钉图 - {}", window_id))
    .build()
    .map_err(|e| HuGeError::WindowError(format!("创建钉图窗口失败: {}", e)))?;

    // 记录窗口标签
    if let Ok(mut windows) = PIN_WINDOWS.lock() {
        windows.push(window_label.clone());
        debug!("当前钉图窗口数量: {}", windows.len());
    }

    info!(
        "钉图窗口 {} 创建成功，位置: ({}, {}), 尺寸: {}x{}",
        window_label, rect.x, rect.y, rect.width, rect.height
    );

    // 发送初始化信息到前端
    let init_info = PinWindowInitInfo {
        label: window_label.clone(),
        image_path: asset_path,
        width: rect.width,
        height: rect.height,
        opacity: 1.0, // 默认完全不透明
    };

    // 缓存初始化数据，供前端在事件丢失时主动拉取
    match PIN_INIT_CACHE.lock() {
        Ok(mut cache) => {
            cache.insert(window_label.clone(), init_info.clone());
        }
        Err(e) => {
            warn!("写入钉图初始化缓存失败（锁中毒）: {}", e);
        }
    }

    if let Err(e) = window.emit("pin-init", init_info) {
        warn!("发送 pin-init 事件失败: {}", e);
    }

    Ok(window_label)
}

/// 设置钉图窗口透明度
///
/// 调整指定钉图窗口的透明度。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `label`: 窗口标签（从 `create_pin_window` 返回）
/// - `opacity`: 透明度值，范围 0.0（完全透明）到 1.0（完全不透明）
///
/// # 错误
///
/// - 如果窗口不存在，返回错误
/// - 如果透明度值超出范围，会被自动限制到 [0.0, 1.0]
///
/// # 实现说明
///
/// Tauri 2.0 的 WebviewWindow 没有直接的 `set_opacity` 方法。
/// 我们通过发送事件到前端，让前端通过 CSS opacity 来实现透明度调整。
///
/// # 示例
///
/// ```ignore
/// // 设置为半透明
/// set_pin_opacity(app, "pin-0".to_string(), 0.5).await?;
///
/// // 设置为完全不透明
/// set_pin_opacity(app, "pin-0".to_string(), 1.0).await?;
/// ```
#[tauri::command]
pub async fn set_pin_opacity(app: tauri::AppHandle, label: String, opacity: f64) -> HuGeResult<()> {
    debug!("设置钉图窗口 {} 透明度: {}", label, opacity);

    // 限制透明度范围
    let clamped_opacity = opacity.clamp(0.0, 1.0);
    if (clamped_opacity - opacity).abs() > f64::EPSILON {
        warn!("透明度值 {} 超出范围，已限制为 {}", opacity, clamped_opacity);
    }

    // 获取窗口
    let window = app
        .get_webview_window(&label)
        .ok_or_else(|| HuGeError::WindowError(format!("钉图窗口 {} 不存在", label)))?;

    // Tauri 2.0 没有直接的 set_opacity 方法
    // 我们通过发送事件到前端，让前端通过 CSS 来处理透明度
    // 前端会设置整个窗口内容的 opacity 样式
    window
        .emit("pin-opacity-changed", clamped_opacity)
        .map_err(|e| HuGeError::WindowError(format!("发送透明度事件失败: {}", e)))?;

    info!("钉图窗口 {} 透明度已设置为 {}", label, clamped_opacity);
    Ok(())
}

/// 获取钉图窗口初始化信息
///
/// 当前端未及时监听 `pin-init` 事件时，可通过该命令主动获取初始化数据。
///
/// # 参数
///
/// - `label`: 窗口标签
#[tauri::command]
pub async fn get_pin_window_init(label: String) -> HuGeResult<PinWindowInitInfo> {
    let cache = PIN_INIT_CACHE
        .lock()
        .map_err(|e| HuGeError::WindowError(format!("读取钉图初始化缓存失败: {}", e)))?;

    cache
        .get(&label)
        .cloned()
        .ok_or_else(|| HuGeError::WindowError(format!("未找到钉图窗口 {} 的初始化数据", label)))
}

/// 关闭钉图窗口
///
/// 关闭指定的钉图窗口并清理资源。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `label`: 窗口标签（从 `create_pin_window` 返回）
///
/// # 错误
///
/// - 如果窗口不存在，静默处理（不返回错误）
///
/// # 示例
///
/// ```ignore
/// close_pin_window(app, "pin-0".to_string()).await?;
/// ```
#[tauri::command]
pub async fn close_pin_window(app: tauri::AppHandle, label: String) -> HuGeResult<()> {
    info!("关闭钉图窗口: {}", label);

    // 从记录中移除
    match PIN_WINDOWS.lock() {
        Ok(mut windows) => {
            windows.retain(|w| w != &label);
            debug!("剩余钉图窗口数量: {}", windows.len());
        }
        Err(e) => {
            warn!("移除钉图窗口记录失败（锁中毒）: {}", e);
        }
    }

    // 移除初始化缓存
    match PIN_INIT_CACHE.lock() {
        Ok(mut cache) => {
            cache.remove(&label);
        }
        Err(e) => {
            warn!("移除钉图初始化缓存失败（锁中毒）: {}", e);
        }
    }

    // 获取并关闭窗口
    if let Some(window) = app.get_webview_window(&label) {
        window.close().map_err(|e| HuGeError::WindowError(format!("关闭窗口失败: {}", e)))?;
        info!("钉图窗口 {} 已关闭", label);
    } else {
        debug!("钉图窗口 {} 不存在，无需关闭", label);
    }

    Ok(())
}

/// 关闭所有钉图窗口
///
/// 关闭所有已创建的钉图窗口。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功关闭的窗口数量
#[tauri::command]
pub async fn close_all_pin_windows(app: tauri::AppHandle) -> HuGeResult<u32> {
    info!("关闭所有钉图窗口...");

    // 获取所有已记录的钉图窗口
    let window_labels: Vec<String> =
        if let Ok(windows) = PIN_WINDOWS.lock() { windows.clone() } else { Vec::new() };

    let mut closed_count = 0u32;
    let mut errors = Vec::new();

    for label in &window_labels {
        if let Some(window) = app.get_webview_window(label) {
            match window.close() {
                Ok(()) => {
                    closed_count += 1;
                    debug!("钉图窗口 {} 已关闭", label);
                }
                Err(e) => {
                    error!("关闭钉图窗口 {} 失败: {}", label, e);
                    errors.push(format!("{}: {}", label, e));
                }
            }
        }
    }

    // 清空记录
    if let Ok(mut windows) = PIN_WINDOWS.lock() {
        windows.clear();
    }
    if let Ok(mut cache) = PIN_INIT_CACHE.lock() {
        cache.clear();
    }

    if !errors.is_empty() {
        warn!("部分钉图窗口关闭失败: {:?}", errors);
    }

    info!("已关闭 {} 个钉图窗口", closed_count);
    Ok(closed_count)
}

/// 获取所有钉图窗口的标签
///
/// 用于调试和状态查询
#[tauri::command]
pub async fn get_pin_windows() -> HuGeResult<Vec<String>> {
    let windows = PIN_WINDOWS
        .lock()
        .map_err(|e| HuGeError::WindowError(format!("获取窗口列表失败: {}", e)))?;
    Ok(windows.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pin_window_config_serialize() {
        let config = PinWindowConfig {
            image_path: "/tmp/test.png".to_string(),
            rect: Rect { x: 100, y: 200, width: 400, height: 300 },
            opacity: 0.9,
        };
        let json = serde_json::to_string(&config).unwrap();
        assert!(json.contains("0.9"));
        assert!(json.contains("400"));
    }

    #[test]
    fn test_pin_window_init_info_serialize() {
        let info = PinWindowInitInfo {
            label: "pin-0".to_string(),
            image_path: "asset://localhost/tmp/test.png".to_string(),
            width: 800,
            height: 600,
            opacity: 1.0,
        };
        let json = serde_json::to_string(&info).unwrap();
        assert!(json.contains("pin-0"));
        assert!(json.contains("asset://localhost"));
        assert!(json.contains("800"));
    }

    #[test]
    fn test_window_label_format() {
        // 测试窗口标签格式
        let label = format!("pin-{}", 0);
        assert_eq!(label, "pin-0");

        let label = format!("pin-{}", 42);
        assert_eq!(label, "pin-42");
    }

    #[test]
    fn test_opacity_clamping() {
        // 测试透明度限制
        assert_eq!((-0.5f64).clamp(0.0, 1.0), 0.0);
        assert_eq!(0.5f64.clamp(0.0, 1.0), 0.5);
        assert_eq!(1.5f64.clamp(0.0, 1.0), 1.0);
    }

    #[test]
    fn test_asset_path_conversion() {
        // 测试路径转换
        let path = "C:\\Users\\test\\screenshot.png";
        let asset_path = format!("asset://localhost/{}", path.replace('\\', "/"));
        assert_eq!(asset_path, "asset://localhost/C:/Users/test/screenshot.png");
    }
}
