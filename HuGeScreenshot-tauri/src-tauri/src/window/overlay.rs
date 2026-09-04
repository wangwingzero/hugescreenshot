//! 覆盖窗口管理
//!
//! 创建全屏透明覆盖窗口，用于截图选区显示。
//!
//! # 设计原则
//!
//! - 每个显示器创建一个独立的覆盖窗口
//! - 窗口透明、无边框、置顶显示
//! - 窗口覆盖整个显示器区域
//! - 支持捕获鼠标事件进行选区操作
//!
//! # 生命周期策略
//!
//! 全屏透明 WebView2 覆盖窗口不复用：
//! 1. 热键触发时先完成预截图，再按需创建覆盖窗口
//! 2. 截图完成、取消或 OCR 前物理关闭窗口
//! 3. 避免隐藏的置顶透明窗口残留 DWM/GPU 表面导致桌面黑屏
//!
//! # 坐标系统
//!
//! - 窗口位置使用物理像素（虚拟屏幕坐标系）
//! - 窗口尺寸使用物理像素
//! - 前端 Vue 使用逻辑像素，需要通过 scale_factor 转换
//!
//! # 焦点管理（关键！）
//!
//! Windows 系统对焦点抢夺有严格限制，需要使用特殊技巧：
//! 1. AttachThreadInput - 将当前线程与前台窗口线程关联
//! 2. SetForegroundWindow - 强制设置前台窗口
//! 3. eval("window.focus()") - 确保 WebView 内部获得焦点
//! 4. DwmFlush - 刷新 DWM 合成器，避免渲染问题

use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tracing::{debug, error, info, warn};

#[cfg(windows)]
use windows::core::PCWSTR;
#[cfg(windows)]
use windows::{
    Wdk::System::SystemServices::RtlGetVersion,
    Win32::{
        Foundation::{HWND, LPARAM, WPARAM},
        Graphics::Dwm::DwmFlush,
        Graphics::Gdi::{
            InvalidateRect, RedrawWindow, HRGN, RDW_ALLCHILDREN, RDW_ERASE, RDW_INVALIDATE,
            RDW_UPDATENOW,
        },
        System::{
            SystemInformation::OSVERSIONINFOW,
            Threading::{AttachThreadInput, GetCurrentThreadId},
        },
        UI::WindowsAndMessaging::{
            FindWindowExW, GetForegroundWindow, GetWindowThreadProcessId, SendMessageTimeoutW,
            SetForegroundWindow, SetWindowDisplayAffinity, SetWindowPos, HWND_BROADCAST,
            HWND_NOTOPMOST, HWND_TOPMOST, SET_WINDOW_POS_FLAGS, SMTO_ABORTIFHUNG, SWP_HIDEWINDOW,
            SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW, WINDOW_DISPLAY_AFFINITY,
            WM_SETTINGCHANGE,
        },
    },
};

use crate::error::{HuGeError, HuGeResult};
use crate::screenshot::snapshot::capture_static_snapshot;

/// 全局覆盖窗口管理器
///
/// 存储所有已创建的覆盖窗口标签，用于统一管理和关闭
static OVERLAY_WINDOWS: Mutex<Vec<String>> = Mutex::new(Vec::new());

/// 窗口是否已预加载的标志
static OVERLAYS_PRELOADED: AtomicBool = AtomicBool::new(false);

/// WebView 就绪状态（每个窗口的就绪标志）
static OVERLAY_READY: std::sync::LazyLock<Mutex<std::collections::HashSet<String>>> =
    std::sync::LazyLock::new(|| Mutex::new(std::collections::HashSet::new()));

/// Overlay 背景图是否已在前端加载完成（每个窗口一条记录）
static OVERLAY_BACKGROUND_READY: std::sync::LazyLock<Mutex<std::collections::HashSet<String>>> =
    std::sync::LazyLock::new(|| Mutex::new(std::collections::HashSet::new()));

/// 静态快照是否正在后台捕获
static SNAPSHOT_CAPTURE_IN_PROGRESS: AtomicBool = AtomicBool::new(false);

/// 正在使用 overlay 预截图缓存执行区域裁剪的任务数。
static OVERLAY_REGION_CAPTURE_IN_PROGRESS: AtomicUsize = AtomicUsize::new(0);

/// overlay teardown 正在等待区域裁剪排空，此时拒绝新的区域裁剪。
static OVERLAY_REGION_CAPTURE_DRAINING: AtomicBool = AtomicBool::new(false);

/// Overlay teardown 已完成，但旧的区域裁剪仍未释放；最后一个裁剪 guard 释放时再打开闸门。
static OVERLAY_REGION_CAPTURE_RELEASE_DRAIN_ON_ZERO: AtomicBool = AtomicBool::new(false);

static OVERLAY_REGION_CAPTURE_NOTIFY: std::sync::LazyLock<tokio::sync::Notify> =
    std::sync::LazyLock::new(tokio::sync::Notify::new);

const OVERLAY_REGION_CAPTURE_DRAIN_TIMEOUT_MS: u64 = 800;

/// Overlay 会话代（每次 show 时递增，用于使旧的 Escape 超时失效）
static OVERLAY_GENERATION: AtomicU64 = AtomicU64::new(0);

/// 预截图缓存（在 overlay 显示前为每个显示器分别捕获的全屏截图）
///
/// 修复截图穿透问题：在 overlay 显示前对**所有**显示器各截一张，确保包含所有窗口；
/// 副屏 overlay 也能拿到自己屏的冻结背景，副屏选区裁剪也能命中缓存。
/// `capture_screen_for_overlay` 和 `capture_region` 会优先使用此缓存。
static PRE_CAPTURE_CACHES: Mutex<Vec<crate::screenshot::CaptureResult>> = Mutex::new(Vec::new());
/// 预截图缓存生成时间（Unix 毫秒）
static PRE_CAPTURE_CACHE_AT_MS: AtomicU64 = AtomicU64::new(0);
/// 预截图可接受的最大年龄（毫秒）
/// 设为 30 秒：覆盖整个截图会话周期。
/// 会话结束时 clear_pre_capture_cache() 会主动清除，无需靠过期淘汰。
const MAX_PRE_CAPTURE_AGE_MS: u64 = 30_000;

fn now_unix_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

pub(crate) struct OverlayRegionCaptureGuard;

impl Drop for OverlayRegionCaptureGuard {
    fn drop(&mut self) {
        let previous = OVERLAY_REGION_CAPTURE_IN_PROGRESS.fetch_sub(1, Ordering::SeqCst);
        debug_assert!(previous > 0, "overlay region capture guard dropped without active capture");
        if previous <= 1 {
            if OVERLAY_REGION_CAPTURE_RELEASE_DRAIN_ON_ZERO.swap(false, Ordering::SeqCst) {
                OVERLAY_REGION_CAPTURE_DRAINING.store(false, Ordering::SeqCst);
                debug!("旧区域截图裁剪已排空，overlay capture 闸门已重新打开");
            }
            OVERLAY_REGION_CAPTURE_NOTIFY.notify_waiters();
        }
    }
}

pub(crate) fn begin_overlay_region_capture() -> HuGeResult<OverlayRegionCaptureGuard> {
    OVERLAY_REGION_CAPTURE_IN_PROGRESS.fetch_add(1, Ordering::SeqCst);
    let guard = OverlayRegionCaptureGuard;

    if OVERLAY_REGION_CAPTURE_DRAINING.load(Ordering::SeqCst) {
        drop(guard);
        return Err(HuGeError::WindowError(
            "overlay 正在关闭，已拒绝新的区域截图以避免桌面黑屏".to_string(),
        ));
    }

    Ok(guard)
}

async fn wait_for_overlay_region_captures(timeout: std::time::Duration) -> bool {
    let deadline = tokio::time::Instant::now() + timeout;

    loop {
        if OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst) == 0 {
            return true;
        }

        let now = tokio::time::Instant::now();
        if now >= deadline {
            return false;
        }

        let notified = OVERLAY_REGION_CAPTURE_NOTIFY.notified();
        if OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst) == 0 {
            return true;
        }

        if tokio::time::timeout(deadline.saturating_duration_since(now), notified).await.is_err() {
            return OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst) == 0;
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OverlayRegionDrainOutcome {
    Drained,
    TimedOut { active: usize },
}

async fn drain_overlay_region_captures_for_teardown(
    timeout: std::time::Duration,
) -> OverlayRegionDrainOutcome {
    OVERLAY_REGION_CAPTURE_DRAINING.store(true, Ordering::SeqCst);

    if wait_for_overlay_region_captures(timeout).await {
        OverlayRegionDrainOutcome::Drained
    } else {
        let active = OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst);
        OverlayRegionDrainOutcome::TimedOut { active }
    }
}

fn finish_overlay_region_capture_drain() {
    let active = OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst);
    if active == 0 {
        OVERLAY_REGION_CAPTURE_RELEASE_DRAIN_ON_ZERO.store(false, Ordering::SeqCst);
        OVERLAY_REGION_CAPTURE_DRAINING.store(false, Ordering::SeqCst);
    } else {
        OVERLAY_REGION_CAPTURE_RELEASE_DRAIN_ON_ZERO.store(true, Ordering::SeqCst);
        warn!("overlay 已释放，仍有 {} 个旧区域截图裁剪未结束；暂时拒绝新的区域截图", active);
    }
}

fn reset_overlay_region_capture_gate_for_new_session() -> HuGeResult<()> {
    let active = OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst);
    if active > 0 {
        return Err(HuGeError::WindowError(format!(
            "{} 个区域截图裁剪仍在进行，已拒绝启动新的 overlay 会话以避免桌面黑屏",
            active
        )));
    }

    finish_overlay_region_capture_drain();
    Ok(())
}

/// 存储多显示器预截图缓存（覆盖式写入）
pub fn set_pre_capture_caches(results: Vec<crate::screenshot::CaptureResult>) {
    if let Ok(mut cache) = PRE_CAPTURE_CACHES.lock() {
        *cache = results;
        PRE_CAPTURE_CACHE_AT_MS.store(now_unix_ms(), Ordering::SeqCst);
    }
}

fn pre_capture_caches_if_fresh() -> Option<Vec<crate::screenshot::CaptureResult>> {
    let cached_at = PRE_CAPTURE_CACHE_AT_MS.load(Ordering::SeqCst);
    if cached_at == 0 {
        return None;
    }
    let age_ms = now_unix_ms().saturating_sub(cached_at);
    if age_ms > MAX_PRE_CAPTURE_AGE_MS {
        info!("预截图缓存已过期（age={}ms > {}ms），跳过", age_ms, MAX_PRE_CAPTURE_AGE_MS);
        return None;
    }
    PRE_CAPTURE_CACHES.lock().ok().map(|c| c.clone()).filter(|v| !v.is_empty())
}

pub(crate) fn find_pre_capture_for_rect_in(
    caches: &[crate::screenshot::CaptureResult],
    rect: &crate::screenshot::capture::Rect,
) -> Option<crate::screenshot::CaptureResult> {
    let rect_right = rect.x.checked_add(i32::try_from(rect.width).ok()?)?;
    let rect_bottom = rect.y.checked_add(i32::try_from(rect.height).ok()?)?;

    caches
        .iter()
        .find(|capture| {
            let Some(width) = i32::try_from(capture.width).ok() else {
                return false;
            };
            let Some(height) = i32::try_from(capture.height).ok() else {
                return false;
            };
            let Some(capture_right) = capture.x.checked_add(width) else {
                return false;
            };
            let Some(capture_bottom) = capture.y.checked_add(height) else {
                return false;
            };

            rect.x >= capture.x
                && rect.y >= capture.y
                && rect_right <= capture_right
                && rect_bottom <= capture_bottom
        })
        .cloned()
}

/// 获取全部可用的预截图缓存（仅返回未过期数据）
pub fn get_pre_capture_caches() -> Option<Vec<crate::screenshot::CaptureResult>> {
    pre_capture_caches_if_fresh()
}

/// 查找完整包含指定矩形的单屏预截图缓存
pub fn find_pre_capture_for_rect(
    rect: &crate::screenshot::capture::Rect,
) -> Option<crate::screenshot::CaptureResult> {
    let caches = pre_capture_caches_if_fresh()?;
    find_pre_capture_for_rect_in(&caches, rect)
}

/// 按显示器原生 ID 查找预截图缓存
pub fn find_pre_capture_by_monitor_id(monitor_id: u32) -> Option<crate::screenshot::CaptureResult> {
    let caches = pre_capture_caches_if_fresh()?;
    caches.into_iter().find(|r| r.monitor_id == monitor_id)
}

/// 获取主显示器（含 0,0 点）的预截图，无则返回第一张
pub fn primary_pre_capture() -> Option<crate::screenshot::CaptureResult> {
    let caches = pre_capture_caches_if_fresh()?;
    caches
        .iter()
        .find(|r| r.x <= 0 && r.y <= 0 && (r.x + r.width as i32) > 0 && (r.y + r.height as i32) > 0)
        .or_else(|| caches.first())
        .cloned()
}

/// 清除预截图缓存
pub fn clear_pre_capture_cache() {
    if let Ok(mut cache) = PRE_CAPTURE_CACHES.lock() {
        cache.clear();
    }
    PRE_CAPTURE_CACHE_AT_MS.store(0, Ordering::SeqCst);
    // 同步清除解码后的内存缓存（避免内存泄漏）
    crate::screenshot::capture::clear_decoded_pre_capture();
    crate::screenshot::capture::clear_crop_source_cache();
}

type PreCaptureTask = tokio::task::JoinHandle<HuGeResult<Vec<crate::screenshot::CaptureResult>>>;

async fn await_pre_capture_task(
    task: PreCaptureTask,
) -> HuGeResult<Vec<crate::screenshot::CaptureResult>> {
    match task.await {
        Ok(Ok(results)) if !results.is_empty() => Ok(results),
        Ok(Ok(_)) => {
            clear_pre_capture_cache();
            Err(HuGeError::CaptureError("预截图返回空列表，已取消显示覆盖窗口".to_string()))
        }
        Ok(Err(e)) => {
            warn!("预截图失败，已取消显示覆盖窗口: {}", e);
            clear_pre_capture_cache();
            Err(e)
        }
        Err(e) => {
            warn!("预截图任务异常: {}", e);
            clear_pre_capture_cache();
            Err(HuGeError::CaptureError(format!("预截图任务异常，已取消显示覆盖窗口: {}", e)))
        }
    }
}

fn cleanup_pre_capture_results(results: &[crate::screenshot::CaptureResult], reason: &str) {
    for result in results {
        if result.path.trim().is_empty() {
            continue;
        }

        match std::fs::remove_file(&result.path) {
            Ok(()) => debug!("已清理未发布预截图文件: {} ({})", result.path, reason),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                debug!("未发布预截图文件已不存在: {} ({})", result.path, reason);
            }
            Err(e) => warn!("清理未发布预截图文件失败: {}, 错误: {}", result.path, e),
        }
    }
}

/// 把多屏预截图分别推送给对应的 overlay 窗口
fn publish_pre_capture_results(
    app: &tauri::AppHandle,
    results: Vec<crate::screenshot::CaptureResult>,
    session_started_at: Instant,
) -> HuGeResult<()> {
    info!("预截图完成: {} 个显示器, 总耗时: {:?}", results.len(), session_started_at.elapsed());

    let paths: Vec<String> = results.iter().map(|r| r.path.clone()).collect();
    crate::screenshot::capture::wait_pre_capture_files_ready(&paths, PRE_CAPTURE_FILE_WAIT_MS)?;

    // 先缓存供 capture_region / capture_screen_for_overlay 使用
    set_pre_capture_caches(results.clone());

    // 按 overlay 窗口的显示器位置匹配对应截图
    let monitors = app.available_monitors().unwrap_or_default();
    let window_labels = tracked_overlay_window_labels();
    if window_labels.is_empty() {
        return Err(HuGeError::WindowError("没有可接收背景图的 overlay 窗口".to_string()));
    }

    let mut emitted = 0usize;
    let mut errors = Vec::new();
    for label in &window_labels {
        let Some(window) = app.get_webview_window(label) else {
            errors.push(format!("{} 不存在", label));
            continue;
        };

        // 从窗口标签解析显示器索引
        let monitor_index: usize =
            label.strip_prefix("overlay-").and_then(|s| s.parse().ok()).unwrap_or(0);

        // 按显示器物理位置匹配（最稳的 join key：x/y 坐标完全相同）
        let payload = monitors.get(monitor_index).and_then(|m| {
            let pos = m.position();
            results.iter().find(|r| r.x == pos.x && r.y == pos.y).cloned()
        });

        // 回退：按 monitor_index 直接取第 N 张（顺序通常一致）
        let payload = payload.or_else(|| results.get(monitor_index).cloned());

        let Some(payload) = payload else {
            errors.push(format!("没有找到 {} 对应的预截图", label));
            continue;
        };

        if let Err(e) = window.emit("background-capture-ready", payload) {
            errors.push(format!("发送 background-capture-ready 到 {} 失败: {}", label, e));
        } else {
            emitted += 1;
        }
    }

    if emitted != window_labels.len() || !errors.is_empty() {
        return Err(HuGeError::WindowError(format!(
            "overlay 背景图推送不完整，已取消显示以避免黑屏: {}",
            errors.join("; ")
        )));
    }

    Ok(())
}

/// Escape 快捷键是否已注册的标志
static ESCAPE_REGISTERED: AtomicBool = AtomicBool::new(false);

fn is_overlay_event_target(label: &str) -> bool {
    label
        .strip_prefix("overlay-")
        .is_some_and(|suffix| !suffix.is_empty() && suffix.chars().all(|c| c.is_ascii_digit()))
}

fn clear_overlay_session_ready_state() {
    if let Ok(mut ready) = OVERLAY_READY.lock() {
        ready.clear();
    }
    if let Ok(mut background_ready) = OVERLAY_BACKGROUND_READY.lock() {
        background_ready.clear();
    }
}

fn tracked_overlay_window_labels() -> Vec<String> {
    if let Ok(windows) = OVERLAY_WINDOWS.lock() {
        windows.iter().filter(|label| is_overlay_event_target(label)).cloned().collect()
    } else {
        Vec::new()
    }
}

fn merge_overlay_window_labels(
    tracked_labels: Vec<String>,
    runtime_labels: Vec<String>,
) -> Vec<String> {
    let mut labels = Vec::new();

    for label in tracked_labels.into_iter().chain(runtime_labels) {
        if is_overlay_event_target(&label) && !labels.contains(&label) {
            labels.push(label);
        }
    }

    labels
}

fn runtime_overlay_window_labels(app: &tauri::AppHandle) -> Vec<String> {
    app.webview_windows().values().map(|window| window.label().to_string()).collect()
}

fn teardown_overlay_window_labels(app: &tauri::AppHandle) -> Vec<String> {
    merge_overlay_window_labels(tracked_overlay_window_labels(), runtime_overlay_window_labels(app))
}

pub fn has_overlay_windows(app: &tauri::AppHandle) -> bool {
    teardown_overlay_window_labels(app).iter().any(|label| {
        app.get_webview_window(label)
            .is_some_and(|window| window.is_visible().unwrap_or(false))
    })
}

fn overlay_hide_superseded_by_new_session(teardown_generation: u64) -> bool {
    OVERLAY_GENERATION.load(Ordering::SeqCst) != teardown_generation
}

fn overlay_ready_missing_labels(
    window_labels: &[String],
    ready_set: &std::collections::HashSet<String>,
) -> Vec<String> {
    window_labels
        .iter()
        .filter(|label| is_overlay_event_target(label) && !ready_set.contains(*label))
        .cloned()
        .collect()
}

fn overlay_window_label_is_current(app: &tauri::AppHandle, window: &tauri::WebviewWindow) -> bool {
    let label = window.label();
    if !is_overlay_event_target(label) {
        return false;
    }

    let Some(current_window) = app.get_webview_window(label) else {
        return false;
    };

    #[cfg(windows)]
    {
        match (window.hwnd(), current_window.hwnd()) {
            (Ok(window_hwnd), Ok(current_hwnd)) => window_hwnd.0 == current_hwnd.0,
            _ => false,
        }
    }

    #[cfg(not(windows))]
    {
        current_window.label() == label
    }
}

const OVERLAY_READY_WAIT_TIMEOUT_MS: u64 = 1_500;
const OVERLAY_READY_POLL_INTERVAL_MS: u64 = 25;
const OVERLAY_BACKGROUND_WAIT_TIMEOUT_MS: u64 = 3_000;
const PRE_CAPTURE_FILE_WAIT_MS: u64 = 800;
const OVERLAY_DESTROY_TRANSPARENT_FRAME_SETTLE_MS: u64 = 50;

async fn wait_for_overlay_frontends_ready(window_labels: &[String]) -> HuGeResult<()> {
    if window_labels.is_empty() {
        return Ok(());
    }

    let started_at = Instant::now();

    loop {
        let missing = if let Ok(ready) = OVERLAY_READY.lock() {
            overlay_ready_missing_labels(window_labels, &ready)
        } else {
            window_labels.to_vec()
        };

        if missing.is_empty() {
            return Ok(());
        }

        if started_at.elapsed() >= std::time::Duration::from_millis(OVERLAY_READY_WAIT_TIMEOUT_MS) {
            return Err(HuGeError::WindowError(format!(
                "overlay 前端未就绪，已取消显示以避免黑屏背景丢失: {}",
                missing.join(", ")
            )));
        }

        tokio::time::sleep(std::time::Duration::from_millis(OVERLAY_READY_POLL_INTERVAL_MS)).await;
    }
}

async fn wait_for_overlay_backgrounds_ready(window_labels: &[String]) -> HuGeResult<()> {
    if window_labels.is_empty() {
        return Ok(());
    }

    let started_at = Instant::now();

    loop {
        let missing = if let Ok(background_ready) = OVERLAY_BACKGROUND_READY.lock() {
            overlay_ready_missing_labels(window_labels, &background_ready)
        } else {
            window_labels.to_vec()
        };

        if missing.is_empty() {
            return Ok(());
        }

        if started_at.elapsed()
            >= std::time::Duration::from_millis(OVERLAY_BACKGROUND_WAIT_TIMEOUT_MS)
        {
            return Err(HuGeError::WindowError(format!(
                "overlay 背景未加载完成，已取消显示以避免黑屏: {}",
                missing.join(", ")
            )));
        }

        tokio::time::sleep(std::time::Duration::from_millis(OVERLAY_READY_POLL_INTERVAL_MS)).await;
    }
}

fn emit_overlay_init_to_tracked_windows(app: &tauri::AppHandle) -> usize {
    let monitors = app.available_monitors().unwrap_or_default();
    let window_labels = tracked_overlay_window_labels();
    let mut emitted = 0usize;

    for label in &window_labels {
        let Some(window) = app.get_webview_window(label) else { continue };

        let monitor_id: usize =
            label.strip_prefix("overlay-").and_then(|s| s.parse().ok()).unwrap_or(0);

        let Some(monitor) = monitors.get(monitor_id) else {
            warn!("无法获取 {} 对应的显示器信息，monitors.len()={}", label, monitors.len());
            continue;
        };

        let position = monitor.position();
        let size = monitor.size();
        let scale_factor = monitor.scale_factor();
        let monitor_name =
            monitor.name().cloned().unwrap_or_else(|| format!("显示器 {}", monitor_id));

        let monitor_info = serde_json::json!({
            "monitorId": monitor_id,
            "position": { "x": position.x, "y": position.y },
            "size": { "width": size.width, "height": size.height },
            "scaleFactor": scale_factor,
            "name": monitor_name,
        });

        debug!("发送 overlay-init 事件: {} -> {:?}", label, monitor_info);
        if let Err(e) = window.emit("overlay-init", monitor_info) {
            warn!("发送 overlay-init 事件到 {} 失败: {}", label, e);
        } else {
            emitted += 1;
        }
    }

    emitted
}

async fn ensure_overlay_frontends_ready_or_cleanup(app: tauri::AppHandle) -> HuGeResult<()> {
    let window_labels = tracked_overlay_window_labels();

    if let Err(e) = wait_for_overlay_frontends_ready(&window_labels).await {
        warn!("overlay 前端未全部就绪，开始清理已显示窗口: {}", e);
        if let Err(cleanup_error) = hide_overlay_windows(app).await {
            warn!("清理未就绪 overlay 失败: {}", cleanup_error);
        }
        return Err(e);
    }

    let emitted = emit_overlay_init_to_tracked_windows(&app);
    if emitted == 0 {
        warn!("没有 overlay 窗口接收 overlay-init 事件");
    }

    Ok(())
}

async fn prepare_overlay_frontends_for_show(app: tauri::AppHandle) -> HuGeResult<()> {
    clear_overlay_session_ready_state();

    if !OVERLAYS_PRELOADED.load(Ordering::SeqCst) {
        warn!("覆盖窗口未预加载，将创建隐藏窗口（可能有延迟）");
        Box::pin(create_all_overlay_windows(app.clone())).await?;
    } else {
        for label in tracked_overlay_window_labels() {
            if let Some(window) = app.get_webview_window(&label) {
                if let Err(e) = window.emit("overlay-reset", ()) {
                    warn!("发送 overlay-reset 事件失败: {}", e);
                }
            }
        }
    }

    if tracked_overlay_window_labels().is_empty() {
        return Err(HuGeError::WindowError("没有可显示的 overlay 窗口".to_string()));
    }

    ensure_overlay_frontends_ready_or_cleanup(app).await
}

async fn show_tracked_overlay_windows(
    app: &tauri::AppHandle,
    window_labels: &[String],
) -> HuGeResult<u32> {
    let mut shown_count = 0u32;
    let mut errors = Vec::new();

    for label in window_labels {
        let Some(window) = app.get_webview_window(label) else {
            errors.push(format!("{} 不存在", label));
            continue;
        };

        if let Err(e) = window.show() {
            errors.push(format!("显示 {} 失败: {}", label, e));
            continue;
        }

        #[cfg(windows)]
        {
            if let Ok(hwnd) = window.hwnd() {
                let hwnd = HWND(hwnd.0);
                refresh_window_dwm(hwnd);
                if should_force_overlay_focus_automatically() {
                    force_foreground_window(hwnd);
                }
                set_exclude_from_capture(hwnd);
            }
        }

        if should_force_overlay_focus_automatically() {
            if let Err(e) = window.set_focus() {
                warn!("设置覆盖窗口 {} 焦点失败: {}", label, e);
            }

            if let Err(e) = window.eval(
                "window.focus(); document.body.focus(); if(document.querySelector('.overlay-mask')) document.querySelector('.overlay-mask').focus();",
            ) {
                warn!("执行 WebView 焦点脚本失败: {}", e);
            }
        }

        shown_count += 1;
        debug!("覆盖窗口 {} 已显示", label);
    }

    if shown_count != window_labels.len() as u32 || !errors.is_empty() {
        return Err(HuGeError::WindowError(format!(
            "overlay 显示不完整，已取消以避免黑屏: {}",
            errors.join("; ")
        )));
    }

    Ok(shown_count)
}

fn emit_to_visible_overlay_windows<S>(app: &tauri::AppHandle, event: &str, payload: S) -> usize
where
    S: serde::Serialize + Clone,
{
    let window_labels = tracked_overlay_window_labels();

    let mut emitted = 0usize;

    for label in window_labels {
        let Some(window) = app.get_webview_window(&label) else {
            continue;
        };

        if !window.is_visible().unwrap_or(false) {
            continue;
        }

        if let Err(e) = window.emit(event, payload.clone()) {
            warn!("发送 {} 事件到 {} 失败: {}", event, label, e);
        } else {
            emitted += 1;
        }
    }

    emitted
}

/// 后台捕获静态快照并广播事件（不阻塞 overlay 显示）
fn spawn_snapshot_capture(app: tauri::AppHandle, generation: u64) {
    // 避免重复并发捕获
    if SNAPSHOT_CAPTURE_IN_PROGRESS.swap(true, Ordering::SeqCst) {
        debug!("静态快照捕获已在进行，跳过本次触发");
        return;
    }

    tauri::async_runtime::spawn(async move {
        let start = Instant::now();
        info!("后台开始捕获静态快照...");

        match capture_static_snapshot(app.clone()).await {
            Ok(result) => {
                if OVERLAY_GENERATION.load(Ordering::SeqCst) != generation {
                    debug!(
                        "静态快照属于过期会话 generation={}，跳过发送: path={}",
                        generation, result.path
                    );
                    if let Err(e) = std::fs::remove_file(&result.path) {
                        warn!("清理过期静态快照失败: {}, 错误: {}", result.path, e);
                    }
                } else if emit_to_visible_overlay_windows(&app, "snapshot-ready", result.clone())
                    == 0
                {
                    warn!("没有可见 overlay 窗口接收 snapshot-ready 事件: path={}", result.path);
                } else {
                    debug!("snapshot-ready 事件已发送: path={}", result.path);
                }
                info!("静态快照后台捕获完成，耗时 {:?}", start.elapsed());
            }
            Err(e) => {
                error!("静态快照后台捕获失败: {}", e);
                let error_payload = serde_json::json!({
                    "error": format!("{}", e)
                });
                if emit_to_visible_overlay_windows(&app, "snapshot-error", error_payload) == 0 {
                    warn!("没有可见 overlay 窗口接收 snapshot-error 事件");
                }
            }
        }

        SNAPSHOT_CAPTURE_IN_PROGRESS.store(false, Ordering::SeqCst);
    });
}

/// 注册临时 Escape 快捷键（overlay 显示时）
///
/// 作为键盘事件捕获的备用方案，确保用户始终能通过 Escape 取消截图。
///
/// # 工作流程
///
/// 1. 先发送 `overlay-force-close` 事件通知前端
/// 2. 前端收到事件后会自动复制截图到剪贴板（如果有截图结果）
/// 3. 然后前端自行关闭窗口
/// 4. 如果前端未能在 1.5 秒内响应，Rust 端作为兜底直接隐藏窗口
fn register_escape_shortcut(app: &tauri::AppHandle) {
    // 避免重复注册
    if ESCAPE_REGISTERED.load(Ordering::SeqCst) {
        return;
    }

    let global_shortcut = app.global_shortcut();

    // 检查 Escape 是否已被注册
    if global_shortcut.is_registered("Escape") {
        debug!("Escape 快捷键已被注册，跳过");
        return;
    }

    // 克隆 app handle 用于闭包
    let app_clone = app.clone();

    // 注册 Escape 快捷键
    match global_shortcut.on_shortcut("Escape", move |_app, _shortcut, event| {
        // 只处理 Pressed 状态，避免双触发
        if event.state != ShortcutState::Pressed {
            return;
        }

        info!("[备用] Escape 快捷键触发，通知前端处理关闭");

        let app_handle = app_clone.clone();
        tauri::async_runtime::spawn(async move {
            // 记录当前会话代，用于后续检查超时是否属于当前会话
            let generation_at_escape = OVERLAY_GENERATION.load(Ordering::SeqCst);

            // 第一步：发送事件通知前端，让前端处理剪贴板复制和关闭
            let mut frontend_handled = false;
            if let Ok(windows) = OVERLAY_WINDOWS.lock() {
                for label in windows.iter() {
                    if let Some(window) = app_handle.get_webview_window(label) {
                        if window.is_visible().unwrap_or(false) {
                            if let Err(e) = window.emit("overlay-force-close", ()) {
                                warn!("[备用] 发送 overlay-force-close 事件失败: {}", e);
                            } else {
                                debug!("[备用] 已发送 overlay-force-close 事件到 {}", label);
                                frontend_handled = true;
                            }
                        }
                    }
                }
            }

            // 第二步：等待 1.5 秒，给前端处理剪贴板复制 + 关闭的时间
            if frontend_handled {
                tokio::time::sleep(std::time::Duration::from_millis(1500)).await;

                // 检查会话代：如果 overlay 已被重新打开（新会话），不要隐藏新窗口
                let current_generation = OVERLAY_GENERATION.load(Ordering::SeqCst);
                if current_generation != generation_at_escape {
                    debug!(
                        "[备用] 会话代已变更 ({} -> {})，跳过兜底隐藏",
                        generation_at_escape, current_generation
                    );
                    return;
                }

                // 检查 overlay 是否仍然可见（前端可能已经关闭了）
                let still_visible = if let Ok(windows) = OVERLAY_WINDOWS.lock() {
                    windows.iter().any(|label| {
                        app_handle
                            .get_webview_window(label)
                            .and_then(|w| w.is_visible().ok())
                            .unwrap_or(false)
                    })
                } else {
                    false
                };

                if still_visible {
                    warn!("[备用] 前端未在 1.5s 内关闭 overlay，兜底直接隐藏");
                    if let Err(e) = hide_overlay_windows(app_handle).await {
                        error!("[备用] 兜底隐藏 overlay 失败: {}", e);
                    }
                } else {
                    info!("[备用] 前端已成功处理关闭");
                }
            } else {
                // 无法通知前端，直接隐藏
                warn!("[备用] 无法通知前端，直接隐藏 overlay");
                if let Err(e) = hide_overlay_windows(app_handle).await {
                    error!("[备用] 隐藏 overlay 失败: {}", e);
                }
            }
        });
    }) {
        Ok(()) => {
            ESCAPE_REGISTERED.store(true, Ordering::SeqCst);
            info!("临时 Escape 快捷键注册成功");
        }
        Err(e) => {
            warn!("注册 Escape 快捷键失败: {}", e);
        }
    }
}

/// 取消注册临时 Escape 快捷键（overlay 隐藏时）
fn unregister_escape_shortcut(app: &tauri::AppHandle) {
    if !ESCAPE_REGISTERED.load(Ordering::SeqCst) {
        return;
    }

    let global_shortcut = app.global_shortcut();

    if global_shortcut.is_registered("Escape") {
        match global_shortcut.unregister("Escape") {
            Ok(()) => {
                ESCAPE_REGISTERED.store(false, Ordering::SeqCst);
                info!("临时 Escape 快捷键已取消注册");
            }
            Err(e) => {
                warn!("取消注册 Escape 快捷键失败: {}", e);
            }
        }
    }
}

/// 强制窗口获取前台焦点（Windows 专用）
///
/// Windows 系统为防止"焦点抢夺"，对 SetForegroundWindow 有严格限制。
/// 此函数使用 AttachThreadInput 技巧绕过限制。
#[cfg(windows)]
fn force_foreground_window(hwnd: HWND) {
    unsafe {
        // 获取当前前台窗口的线程 ID
        let foreground_hwnd = GetForegroundWindow();
        let foreground_thread = GetWindowThreadProcessId(foreground_hwnd, None);
        let current_thread = GetCurrentThreadId();

        // 如果不是同一线程，需要 AttachThreadInput
        if foreground_thread != current_thread {
            // 将当前线程与前台窗口线程关联
            if !AttachThreadInput(current_thread, foreground_thread, true).as_bool() {
                warn!("AttachThreadInput(attach) 失败: {:?}", hwnd);
            }

            // 设置为前台窗口
            // 注意：SetForegroundWindow 返回 BOOL，FALSE 表示系统拒绝了焦点请求（非致命）
            if !SetForegroundWindow(hwnd).as_bool() {
                debug!(
                    "SetForegroundWindow 未能设置前台窗口（系统可能拒绝了焦点请求）: {:?}",
                    hwnd
                );
            }

            // 强制置顶
            if let Err(e) = SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            ) {
                warn!("SetWindowPos(TOPMOST) 失败: {:?}, error: {}", hwnd, e);
            }

            // 解除线程关联
            if !AttachThreadInput(current_thread, foreground_thread, false).as_bool() {
                warn!("AttachThreadInput(detach) 失败: {:?}", hwnd);
            }
        } else if !SetForegroundWindow(hwnd).as_bool() {
            debug!("SetForegroundWindow 未能设置前台窗口: {:?}", hwnd);
        }

        debug!("强制前台焦点设置完成: {:?}", hwnd);
    }
}

/// 在 OCR 面板可见且正在交互时，禁止 overlay 抢焦点
///
/// 场景：用户在 OCR 面板中拖拽/选中文本时，overlay 的强制聚焦会打断交互，
/// 甚至导致 OCR 面板被 overlay 全屏遮挡，看起来像“消失”。
fn should_skip_overlay_focus_restore(app: &tauri::AppHandle, source: &str) -> bool {
    // 在录制控制面板或录制预览窗口可见时，不允许 overlay 抢焦点
    for window_label in &["recording-control", "recording-preview"] {
        if let Some(window) = app.get_webview_window(window_label) {
            if window.is_visible().unwrap_or(false) {
                debug!("跳过 overlay 强制聚焦（{}）：{} 可见", source, window_label);
                return true;
            }
        }
    }

    let Some(ocr_window) = app.get_webview_window("ocr-result") else {
        return false;
    };

    let ocr_visible = ocr_window.is_visible().unwrap_or(false);
    if !ocr_visible {
        return false;
    }

    let ocr_focused = ocr_window.is_focused().unwrap_or(false);

    #[cfg(windows)]
    let ocr_foreground = if let Ok(ocr_hwnd) = ocr_window.hwnd() {
        unsafe { GetForegroundWindow().0 == ocr_hwnd.0 }
    } else {
        false
    };
    #[cfg(not(windows))]
    let ocr_foreground = false;

    // 只要 OCR 面板可见，就不允许 overlay 抢焦点。
    // 这样可以覆盖拖拽时焦点抖动/短暂失焦的场景，避免 OCR 面板被 overlay 全屏遮挡。
    debug!(
        "跳过 overlay 强制聚焦（{}）：ocr-result 可见 (visible={}, focused={}, foreground={})",
        source, ocr_visible, ocr_focused, ocr_foreground
    );
    true
}

/// 刷新窗口和 DWM 合成器（Windows 专用）
///
/// 强制刷新窗口内容和 DWM 合成队列，避免渲染缓存导致的显示问题。
#[cfg(windows)]
fn refresh_window_dwm(hwnd: HWND) {
    unsafe {
        // 只请求异步重绘。不要调用 UpdateWindow：它会同步发送 WM_PAINT，
        // 容易在 Tao 正在整理 redraw 事件时触发重入断言。
        if !InvalidateRect(hwnd, None, false).as_bool() {
            warn!("InvalidateRect 失败: {:?}", hwnd);
        }

        // 刷新 DWM 合成器队列
        if let Err(e) = DwmFlush() {
            warn!("DwmFlush 失败: {}", e);
        }

        debug!("DWM 异步刷新请求完成: {:?}", hwnd);
    }
}

#[cfg(windows)]
fn desktop_repaint_target_class_names() -> &'static [&'static str] {
    &["Progman", "WorkerW", "SHELLDLL_DefView"]
}

#[cfg(windows)]
fn to_wide_null(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
fn push_unique_hwnd(targets: &mut Vec<HWND>, hwnd: HWND) {
    if hwnd.is_invalid() || hwnd.0.is_null() || targets.iter().any(|existing| existing.0 == hwnd.0)
    {
        return;
    }

    targets.push(hwnd);
}

#[cfg(windows)]
fn find_top_level_windows_by_class(class_name: &str) -> Vec<HWND> {
    let class_name = to_wide_null(class_name);
    let class_name = PCWSTR(class_name.as_ptr());
    let mut windows = Vec::new();
    let mut after = HWND(std::ptr::null_mut());

    loop {
        let found =
            unsafe { FindWindowExW(HWND(std::ptr::null_mut()), after, class_name, PCWSTR::null()) };

        match found {
            Ok(hwnd) if !hwnd.is_invalid() && !hwnd.0.is_null() => {
                push_unique_hwnd(&mut windows, hwnd);
                after = hwnd;
            }
            _ => break,
        }
    }

    windows
}

#[cfg(windows)]
fn find_child_windows_by_class(parent: HWND, class_name: &str) -> Vec<HWND> {
    let class_name = to_wide_null(class_name);
    let class_name = PCWSTR(class_name.as_ptr());
    let mut windows = Vec::new();
    let mut after = HWND(std::ptr::null_mut());

    loop {
        let found = unsafe { FindWindowExW(parent, after, class_name, PCWSTR::null()) };

        match found {
            Ok(hwnd) if !hwnd.is_invalid() && !hwnd.0.is_null() => {
                push_unique_hwnd(&mut windows, hwnd);
                after = hwnd;
            }
            _ => break,
        }
    }

    windows
}

#[cfg(windows)]
fn desktop_repaint_targets() -> Vec<HWND> {
    let mut targets = Vec::new();

    for class_name in desktop_repaint_target_class_names()
        .iter()
        .copied()
        .filter(|class_name| *class_name != "SHELLDLL_DefView")
    {
        for hwnd in find_top_level_windows_by_class(class_name) {
            push_unique_hwnd(&mut targets, hwnd);
        }
    }

    let parents = targets.clone();
    for parent in parents {
        for hwnd in find_child_windows_by_class(parent, "SHELLDLL_DefView") {
            push_unique_hwnd(&mut targets, hwnd);
        }
    }

    targets
}

#[cfg(windows)]
fn force_desktop_repaint_after_teardown() {
    unsafe {
        let flags = RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW;
        for hwnd in desktop_repaint_targets() {
            if !RedrawWindow(hwnd, None, HRGN(std::ptr::null_mut()), flags).as_bool() {
                warn!("RedrawWindow 桌面窗口刷新失败: {:?}", hwnd);
            }
        }

        if !RedrawWindow(HWND(std::ptr::null_mut()), None, HRGN(std::ptr::null_mut()), flags)
            .as_bool()
        {
            warn!("RedrawWindow 全桌面刷新失败");
        }

        let mut result = 0usize;
        let _ = SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            WPARAM(0),
            LPARAM(0),
            SMTO_ABORTIFHUNG,
            200,
            Some(&mut result),
        );

        if let Err(e) = DwmFlush() {
            warn!("overlay teardown 后 DwmFlush 失败: {}", e);
        }
    }
}

#[cfg(not(windows))]
fn force_desktop_repaint_after_teardown() {}

/// WDA_EXCLUDEFROMCAPTURE 常量值 (Windows 10 2004+)
///
/// 将窗口标记为"从截图捕获中排除"。设置此标志后：
/// - 窗口对用户仍然可见（遮罩层正常显示）
/// - 但 DXGI/WGC 等截图 API 不会捕获此窗口
/// - 这确保截图结果是原始屏幕内容，不包含遮罩层的变暗效果
///
/// 参考: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
#[cfg(windows)]
const WDA_EXCLUDEFROMCAPTURE: WINDOW_DISPLAY_AFFINITY = WINDOW_DISPLAY_AFFINITY(0x11);
#[cfg(windows)]
const WDA_NONE: WINDOW_DISPLAY_AFFINITY = WINDOW_DISPLAY_AFFINITY(0);

const WDA_EXCLUDEFROMCAPTURE_MIN_BUILD: u32 = 19041;

fn is_wda_exclude_supported_by_version(major: u32, minor: u32, build: u32) -> bool {
    major > 10 || (major == 10 && (minor > 0 || build >= WDA_EXCLUDEFROMCAPTURE_MIN_BUILD))
}

fn should_preload_overlay_windows(wda_exclude_unsupported: bool) -> bool {
    // 旧版 Windows 无 WDA 时不预加载：隐藏的全屏 WebView2 可能被 GDI 截进预截图导致黑屏。
    // 支持 WDA 的现代系统可安全预加载，避免每次热键都重建 WebView2（高分辨率下极慢）。
    !wda_exclude_unsupported
}

const SHOULD_CLEAR_CAPTURE_EXCLUSION_AFTER_HIDE: bool = true;

fn should_clear_capture_exclusion_after_hide(wda_exclude_supported: bool) -> bool {
    SHOULD_CLEAR_CAPTURE_EXCLUSION_AFTER_HIDE && wda_exclude_supported
}

fn should_destroy_overlay_windows_on_hide(
    overlays_preloaded: bool,
    wda_exclude_supported: bool,
) -> bool {
    let _ = overlays_preloaded;
    // 无 WDA 的旧系统必须销毁，否则 DWM/GPU 表面残留导致黑屏；
    // 有 WDA 时隐藏复用即可，避免反复 destroy/create WebView2 造成卡顿甚至假死。
    !wda_exclude_supported
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OverlayTeardownMethod {
    Hide,
    Destroy,
}

fn overlay_teardown_method(destroy_windows: bool) -> OverlayTeardownMethod {
    if destroy_windows {
        OverlayTeardownMethod::Destroy
    } else {
        OverlayTeardownMethod::Hide
    }
}

fn should_reuse_existing_overlay_window() -> bool {
    false
}

fn forget_overlay_window_label(window_label: &str) {
    if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
        windows.retain(|label| label != window_label);
    }
    if let Ok(mut ready) = OVERLAY_READY.lock() {
        ready.retain(|label| label != window_label);
    }
}

fn retained_overlay_labels_after_close_attempts(close_attempts: &[(String, bool)]) -> Vec<String> {
    close_attempts
        .iter()
        .filter_map(|(label, closed)| if *closed { None } else { Some(label.clone()) })
        .collect()
}

fn visible_overlay_teardown_error(failed_labels: &[String]) -> HuGeResult<()> {
    if failed_labels.is_empty() {
        Ok(())
    } else {
        Err(HuGeError::WindowError(format!(
            "{} 个 overlay 窗口未能彻底释放，已阻止后续 OCR 以避免黑屏残留: {}",
            failed_labels.len(),
            failed_labels.join(", ")
        )))
    }
}

fn overlay_region_drain_teardown_error(outcome: OverlayRegionDrainOutcome) -> HuGeResult<()> {
    match outcome {
        OverlayRegionDrainOutcome::Drained | OverlayRegionDrainOutcome::TimedOut { active: 0 } => {
            Ok(())
        }
        OverlayRegionDrainOutcome::TimedOut { active } => Err(HuGeError::WindowError(format!(
            "{} 个区域截图裁剪仍未结束，overlay 已释放但已阻止 OCR，避免截图资源与 OCR 重叠导致桌面黑屏",
            active
        ))),
    }
}

fn overlay_destroy_failure_blocks_ocr(hide_fallback_succeeded: bool) -> bool {
    let _ = hide_fallback_succeeded;
    true
}

fn overlay_destroy_failure_detail(
    label: &str,
    destroy_error: impl std::fmt::Display,
    hide_fallback_succeeded: bool,
) -> String {
    if hide_fallback_succeeded {
        format!("{} (destroy: {}; hide fallback succeeded)", label, destroy_error)
    } else {
        format!("{} (destroy: {}; hide fallback failed)", label, destroy_error)
    }
}

fn should_capture_static_snapshot_after_overlay() -> bool {
    // 用户机器上 WGC 可能因权限被拒绝而回退到 DXGI/GDI。
    // overlay 已显示后再捕获桌面，会让透明置顶窗口和捕获链重叠，容易触发 DWM 黑屏。
    false
}

/// 预加载且 WDA 有效时，隐藏中的 overlay 不会进入预截图，可与前端重置并行。
fn should_overlap_pre_capture_with_overlay_prep(
    wda_exclude_supported: bool,
    overlays_preloaded: bool,
) -> bool {
    wda_exclude_supported && overlays_preloaded
}

fn should_force_desktop_repaint_after_teardown(
    teardown_method: OverlayTeardownMethod,
    wda_exclude_supported: bool,
) -> bool {
    match teardown_method {
        OverlayTeardownMethod::Destroy => true,
        // 0.1.16+ 在支持 WDA 的系统上隐藏复用 overlay；全桌面 RedrawWindow + DwmFlush 约 2~3s，OCR 后体感极卡。
        OverlayTeardownMethod::Hide => !wda_exclude_supported,
    }
}

fn should_create_overlay_window_focused() -> bool {
    false
}

fn should_force_overlay_focus_automatically() -> bool {
    false
}

fn should_hide_overlay_hwnd_before_destroy() -> bool {
    true
}

#[cfg(windows)]
fn overlay_destroy_window_pos_flags() -> SET_WINDOW_POS_FLAGS {
    let mut flags = SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE;
    if should_hide_overlay_hwnd_before_destroy() {
        flags |= SWP_HIDEWINDOW;
    }
    flags
}

#[cfg(windows)]
fn overlay_destroy_window_insert_after() -> HWND {
    HWND_NOTOPMOST
}

#[cfg(all(test, windows))]
fn overlay_destroy_window_pos_preserves_bounds() -> bool {
    let flags = overlay_destroy_window_pos_flags();
    (flags.0 & SWP_NOMOVE.0) == SWP_NOMOVE.0 && (flags.0 & SWP_NOSIZE.0) == SWP_NOSIZE.0
}

#[cfg(all(test, windows))]
fn overlay_destroy_window_pos_hides_without_activation() -> bool {
    let flags = overlay_destroy_window_pos_flags();
    (flags.0 & SWP_NOACTIVATE.0) == SWP_NOACTIVATE.0
        && (flags.0 & SWP_HIDEWINDOW.0) == SWP_HIDEWINDOW.0
}

#[cfg(all(test, windows))]
fn overlay_destroy_window_pos_clears_topmost() -> bool {
    use windows::Win32::UI::WindowsAndMessaging::SWP_NOZORDER;

    let flags = overlay_destroy_window_pos_flags();
    (flags.0 & SWP_NOZORDER.0) == 0 && overlay_destroy_window_insert_after().0 == HWND_NOTOPMOST.0
}

fn overlay_destroy_transparent_frame_settle_ms() -> u64 {
    OVERLAY_DESTROY_TRANSPARENT_FRAME_SETTLE_MS
}

#[cfg(test)]
fn overlay_destroy_settle_window_count() -> usize {
    2
}

async fn prepare_webview_for_overlay_destroy(window: &tauri::WebviewWindow) {
    let _ = window.eval(
        "(() => { \
         const nodes = [document.documentElement, document.body, document.getElementById('overlay-app')]; \
         for (const node of nodes) { \
           if (!node) continue; \
           node.style.transition = 'none'; \
           node.style.opacity = '0'; \
           node.style.background = 'transparent'; \
           node.style.pointerEvents = 'none'; \
         } \
         for (const canvas of document.querySelectorAll('canvas')) { \
           const ctx = canvas.getContext && canvas.getContext('2d'); \
           if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height); \
           canvas.style.opacity = '0'; \
         } \
       })();",
    );

    tokio::time::sleep(std::time::Duration::from_millis(
        overlay_destroy_transparent_frame_settle_ms(),
    ))
    .await;
}

#[cfg(windows)]
fn current_windows_version() -> Option<(u32, u32, u32)> {
    unsafe {
        let mut info = OSVERSIONINFOW {
            dwOSVersionInfoSize: std::mem::size_of::<OSVERSIONINFOW>() as u32,
            ..Default::default()
        };

        let status = RtlGetVersion(&mut info);
        if status.is_ok() {
            Some((info.dwMajorVersion, info.dwMinorVersion, info.dwBuildNumber))
        } else {
            warn!("获取 Windows 版本失败: {:?}", status);
            None
        }
    }
}

#[cfg(windows)]
fn is_wda_exclude_supported() -> bool {
    static SUPPORTED: std::sync::LazyLock<bool> = std::sync::LazyLock::new(|| {
        let Some((major, minor, build)) = current_windows_version() else {
            warn!("无法确认 Windows 版本，禁用 WDA_EXCLUDEFROMCAPTURE 以避免黑屏截图");
            return false;
        };

        let supported = is_wda_exclude_supported_by_version(major, minor, build);
        if supported {
            info!("Windows {}.{} build {} 支持 WDA_EXCLUDEFROMCAPTURE", major, minor, build);
        } else {
            warn!(
                "Windows {}.{} build {} 不支持 WDA_EXCLUDEFROMCAPTURE，\
                 将先完成预截图再显示 overlay，避免捕获到黑屏遮罩",
                major, minor, build
            );
        }
        supported
    });

    *SUPPORTED
}

/// 设置窗口为"从截图捕获中排除"（Windows 专用）
///
/// 调用 SetWindowDisplayAffinity 使 overlay 窗口对截图 API 不可见。
/// 这是解决"截图范围内屏幕变暗"问题的核心方案：
/// - 用户仍然能看到半透明遮罩层（视觉提示正在截图）
/// - 但 DXGI/WGC 截图不会包含遮罩层，保持原始屏幕颜色
///
/// 如果设置失败（如系统版本不支持），仅输出警告，不影响功能。
#[cfg(windows)]
fn set_exclude_from_capture(hwnd: HWND) {
    if !is_wda_exclude_supported() {
        debug!("跳过 WDA_EXCLUDEFROMCAPTURE（当前 Windows 版本不支持）: {:?}", hwnd);
        return;
    }

    unsafe {
        match SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) {
            Ok(()) => {
                info!(
                    "已设置 WDA_EXCLUDEFROMCAPTURE（overlay 窗口将从截图捕获中排除）: {:?}",
                    hwnd
                );
            }
            Err(e) => {
                warn!(
                    "设置 WDA_EXCLUDEFROMCAPTURE 失败: {}。\
                     截图可能包含遮罩层导致颜色偏暗。\
                     此功能需要 Windows 10 2004 (Build 19041) 或更高版本。",
                    e
                );
            }
        }
    }
}

#[cfg(windows)]
fn clear_exclude_from_capture(hwnd: HWND) {
    if !should_clear_capture_exclusion_after_hide(is_wda_exclude_supported()) {
        debug!("跳过清除 WDA_EXCLUDEFROMCAPTURE（当前 Windows 版本不支持）: {:?}", hwnd);
        return;
    }

    unsafe {
        match SetWindowDisplayAffinity(hwnd, WDA_NONE) {
            Ok(()) => {
                info!("已清除 WDA_EXCLUDEFROMCAPTURE（overlay 隐藏后释放渲染状态）: {:?}", hwnd);
                refresh_window_dwm(hwnd);
            }
            Err(e) => {
                warn!("清除 WDA_EXCLUDEFROMCAPTURE 失败: {}", e);
            }
        }
    }
}

#[cfg(windows)]
fn prepare_overlay_window_for_destroy(hwnd: HWND) {
    unsafe {
        let flags = overlay_destroy_window_pos_flags();
        if let Err(e) = SetWindowPos(hwnd, overlay_destroy_window_insert_after(), 0, 0, 0, 0, flags)
        {
            warn!("overlay 销毁前隐藏/取消置顶失败: {:?}, error: {}", hwnd, e);
        }

        refresh_window_dwm(hwnd);
    }
}

#[cfg(windows)]
fn restore_overlay_window_for_show(hwnd: HWND, x: i32, y: i32, width: u32, height: u32) {
    unsafe {
        if let Err(e) =
            SetWindowPos(hwnd, HWND_TOPMOST, x, y, width as i32, height as i32, SWP_SHOWWINDOW)
        {
            warn!("恢复 overlay 窗口位置/置顶失败: {:?}, error: {}", hwnd, e);
        }

        refresh_window_dwm(hwnd);
    }
}

/// 覆盖窗口配置
#[derive(Debug, Clone)]
pub struct OverlayConfig {
    /// 窗口标签前缀
    pub label_prefix: &'static str,
    /// 前端页面 URL
    pub url: &'static str,
    /// 是否跳过任务栏
    pub skip_taskbar: bool,
    /// 是否可调整大小
    pub resizable: bool,
    /// 是否可最大化
    pub maximizable: bool,
    /// 是否可最小化
    pub minimizable: bool,
}

impl Default for OverlayConfig {
    fn default() -> Self {
        Self {
            label_prefix: "overlay",
            url: "overlay.html",
            skip_taskbar: true,
            resizable: false,
            maximizable: false,
            minimizable: false,
        }
    }
}

/// 预加载所有显示器的覆盖窗口（应用启动时调用）
///
/// 在应用启动时预创建隐藏的覆盖窗口，以便热键触发时能够立即显示。
/// 这是性能优化的关键：WebView 初始化是耗时操作，提前完成可避免热键延迟。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功返回预加载的窗口数量，失败返回错误信息
pub fn preload_overlay_windows(app: &tauri::AppHandle) -> HuGeResult<u32> {
    // 检查是否已预加载
    if OVERLAYS_PRELOADED.load(Ordering::SeqCst) {
        debug!("覆盖窗口已预加载，跳过");
        return Ok(0);
    }

    #[cfg(windows)]
    if !should_preload_overlay_windows(!is_wda_exclude_supported()) {
        info!("安全策略已禁用 overlay 预加载，改为截图时按需创建并在结束后销毁");
        return Ok(0);
    }

    info!("预加载覆盖窗口...");

    let monitors = app
        .available_monitors()
        .map_err(|e| HuGeError::WindowError(format!("获取显示器列表失败: {}", e)))?;

    let monitor_count = monitors.len() as u32;
    info!("检测到 {} 个显示器，开始预加载覆盖窗口", monitor_count);

    let mut created_count = 0u32;
    let config = OverlayConfig::default();

    for (index, monitor) in monitors.iter().enumerate() {
        let monitor_id = index as u32;
        let window_label = format!("overlay-{}", monitor_id);

        // 检查窗口是否已存在
        if app.get_webview_window(&window_label).is_some() {
            debug!("覆盖窗口 {} 已存在，跳过", window_label);
            continue;
        }

        // 获取显示器信息
        let position = monitor.position();
        let size = monitor.size();
        let scale_factor = monitor.scale_factor();
        let monitor_name =
            monitor.name().cloned().unwrap_or_else(|| format!("显示器 {}", monitor_id));

        // 关键：将物理像素转换为逻辑像素
        // Tauri 的 position() 和 inner_size() 接受逻辑像素
        let logical_width = size.width as f64 / scale_factor;
        let logical_height = size.height as f64 / scale_factor;
        let logical_x = position.x as f64 / scale_factor;
        let logical_y = position.y as f64 / scale_factor;

        debug!(
            "预加载覆盖窗口: {} @ ({}, {}), 物理尺寸: {}x{}, 逻辑尺寸: {:.0}x{:.0}, DPR: {:.2}",
            monitor_name,
            position.x,
            position.y,
            size.width,
            size.height,
            logical_width,
            logical_height,
            scale_factor
        );

        // 创建隐藏的覆盖窗口
        match WebviewWindowBuilder::new(
            app,
            &window_label,
            WebviewUrl::App(config.url.into()),
        )
        // 核心属性：透明、无边框、置顶、无阴影
        .transparent(true)
        .decorations(false)
        .shadow(false)  // 关键：禁用窗口阴影，避免位置偏移
        .always_on_top(true)
        // 窗口位置和尺寸（逻辑像素）
        .position(logical_x, logical_y)
        .inner_size(logical_width, logical_height)
        // 窗口行为
        .skip_taskbar(config.skip_taskbar)
        .resizable(config.resizable)
        .maximizable(config.maximizable)
        .minimizable(config.minimizable)
        // 关键：预加载时隐藏窗口
        .visible(false)
        .focused(false)
        // 窗口标题（调试用）
        .title(format!("截图覆盖 - {}", monitor_name))
        .build()
        {
            Ok(window) => {
                // 关键：设置 WDA_EXCLUDEFROMCAPTURE，使 overlay 不被截图捕获
                // 这样 DXGI/WGC 截图不会包含遮罩层的变暗效果
                #[cfg(windows)]
                {
                    if let Ok(hwnd) = window.hwnd() {
                        set_exclude_from_capture(HWND(hwnd.0));
                    }
                }

                // 记录窗口标签
                if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
                    windows.push(window_label.clone());
                }
                created_count += 1;
                debug!("覆盖窗口 {} 预加载成功", window_label);
            }
            Err(e) => {
                error!("预加载覆盖窗口 {} 失败: {}", window_label, e);
            }
        }
    }

    // 标记为已预加载
    OVERLAYS_PRELOADED.store(true, Ordering::SeqCst);
    info!("覆盖窗口预加载完成，成功 {}/{} 个", created_count, monitor_count);

    Ok(created_count)
}

/// 显示所有预加载的覆盖窗口（热键触发时调用）
///
/// 如果窗口已预加载，直接显示；否则创建新窗口。
/// 这是热键响应的入口点，性能关键路径。
///
/// # 流程（修复截图穿透问题）
///
/// 1. **先截图**：在显示 overlay 之前，使用 WGC 捕获全屏截图
///    - 确保截图包含所有窗口（聊天窗口等不会被 overlay 遮挡）
/// 2. **再显示 overlay**：将预截的图像路径传递给前端
/// 3. 前端用预截的图像作为冻结背景
/// 4. 区域截图从预截的图像裁剪，而不是重新截图
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功返回显示的窗口数量，失败返回错误信息
///
/// **Validates: Requirements 1.1, 3.2**
#[tauri::command]
pub async fn show_overlay_windows(app: tauri::AppHandle) -> HuGeResult<u32> {
    let start = Instant::now();
    info!("显示覆盖窗口...");

    reset_overlay_region_capture_gate_for_new_session()?;

    // 递增会话代，使旧的 Escape 超时回调和异步快照回调失效
    let generation = OVERLAY_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;

    // 清除上一次会话可能残留的旧缓存（防止竞态：上次 step3 在 hide 之后才完成）
    clear_pre_capture_cache();
    // 清除上一次会话未消费的 OCR 图像缓存
    crate::ocr::engine::clear_ocr_image_cache();

    #[cfg(windows)]
    let wda_exclude_supported = is_wda_exclude_supported();
    #[cfg(not(windows))]
    let wda_exclude_supported = true;

    let overlays_preloaded = OVERLAYS_PRELOADED.load(Ordering::SeqCst);
    let overlap_pre_capture_with_prep =
        should_overlap_pre_capture_with_overlay_prep(wda_exclude_supported, overlays_preloaded);

    // 预截图必须在 overlay **显示** 前完成。0.1.13 起为防 GDI 回退拍到可见 overlay 而全程串行；
    // 支持 WDA 且已预加载（隐藏态）时，可与 overlay-reset 并行以缩短热键响应。
    info!("启动预截图（后台线程）...");
    let mut capture_handle = Some(tokio::task::spawn_blocking(|| {
        use crate::screenshot::capture::capture_all_screens_sync;
        capture_all_screens_sync(true)
    }));

    let pre_capture_results = if overlap_pre_capture_with_prep {
        info!("WDA 预加载路径：预截图与 overlay 重置并行");
        let task = capture_handle.take().ok_or_else(|| {
            HuGeError::CaptureError("预截图任务未启动，已取消显示覆盖窗口".to_string())
        })?;
        let (capture_result, prep_result) = tokio::join!(
            await_pre_capture_task(task),
            prepare_overlay_frontends_for_show(app.clone()),
        );
        if prep_result.is_err() {
            if let Ok(result) = &capture_result {
                cleanup_pre_capture_results(result, "overlay 前端未就绪");
            }
        }
        prep_result?;
        capture_result?
    } else {
        info!("等待预截图完成后再准备 overlay，避免 GDI 回退捕获到黑屏 overlay");
        let task = capture_handle.take().ok_or_else(|| {
            HuGeError::CaptureError("预截图任务未启动，已取消显示覆盖窗口".to_string())
        })?;
        let capture_result = match await_pre_capture_task(task).await {
            Ok(result) => result,
            Err(e) => return Err(e),
        };
        if let Err(e) = prepare_overlay_frontends_for_show(app.clone()).await {
            cleanup_pre_capture_results(&capture_result, "overlay 前端未就绪");
            return Err(e);
        }
        capture_result
    };

    let window_labels = tracked_overlay_window_labels();
    if window_labels.is_empty() {
        cleanup_pre_capture_results(&pre_capture_results, "overlay 窗口缺失");
        return Err(HuGeError::WindowError("没有可显示的 overlay 窗口".to_string()));
    }

    let result = pre_capture_results;

    let shown_count = match show_tracked_overlay_windows(&app, &window_labels).await {
        Ok(count) => count,
        Err(e) => {
            cleanup_pre_capture_results(&result, "overlay 显示失败");
            clear_pre_capture_cache();
            let _ = hide_overlay_windows(app.clone()).await;
            return Err(e);
        }
    };

    if let Err(e) = publish_pre_capture_results(&app, result.clone(), start) {
        cleanup_pre_capture_results(&result, "overlay 背景推送失败");
        clear_pre_capture_cache();
        let _ = hide_overlay_windows(app.clone()).await;
        return Err(e);
    }

    let elapsed = start.elapsed();
    info!("覆盖窗口显示完成，显示 {} 个窗口，耗时 {:?}", shown_count, elapsed);

    let background_labels = window_labels.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(e) = wait_for_overlay_backgrounds_ready(&background_labels).await {
            warn!("overlay 冻结背景加载较慢或未就绪（选区仍可用预截图缓存）: {}", e);
        }
    });

    if should_capture_static_snapshot_after_overlay() {
        spawn_snapshot_capture(app.clone(), generation);
    } else {
        debug!("跳过 overlay 显示后的静态快照捕获，避免透明置顶窗口与 DXGI/GDI 捕获重叠");
    }

    if shown_count > 0 {
        register_escape_shortcut(&app);
    }

    Ok(shown_count)
}

/// 隐藏或销毁所有覆盖窗口（截图完成或取消时调用）
///
/// 当前安全策略统一销毁全屏 WebView2 overlay，避免 DWM/GPU 表面残留导致桌面黑屏。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息
#[tauri::command]
pub async fn hide_overlay_windows(app: tauri::AppHandle) -> HuGeResult<()> {
    info!("隐藏覆盖窗口...");

    // 会话结束，失效仍在后台运行的快照捕获结果。
    let teardown_generation = OVERLAY_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;

    let region_drain_outcome = drain_overlay_region_captures_for_teardown(
        std::time::Duration::from_millis(OVERLAY_REGION_CAPTURE_DRAIN_TIMEOUT_MS),
    )
    .await;

    match region_drain_outcome {
        OverlayRegionDrainOutcome::Drained => {}
        OverlayRegionDrainOutcome::TimedOut { active } => {
            warn!(
                "{} 个区域截图裁剪超过 {}ms 未结束，继续销毁 overlay 以优先恢复桌面显示",
                active, OVERLAY_REGION_CAPTURE_DRAIN_TIMEOUT_MS
            );
        }
    }

    if overlay_hide_superseded_by_new_session(teardown_generation) {
        info!("overlay 隐藏已取消：新的截图会话已开始");
        return Ok(());
    }

    // 清除预截图缓存（此次截图会话结束）
    clear_pre_capture_cache();

    // 取消注册临时 Escape 快捷键
    unregister_escape_shortcut(&app);

    // 获取所有覆盖窗口。除了内部记录，也扫描运行时真实存在的 overlay-* 窗口，
    // 避免记录不同步时遗漏全屏透明窗口，造成桌面黑屏残留。
    let window_labels = teardown_overlay_window_labels(&app);

    let overlays_preloaded = OVERLAYS_PRELOADED.load(Ordering::SeqCst);
    #[cfg(windows)]
    let wda_exclude_supported = is_wda_exclude_supported();
    #[cfg(windows)]
    let destroy_windows =
        should_destroy_overlay_windows_on_hide(overlays_preloaded, wda_exclude_supported);
    #[cfg(not(windows))]
    let destroy_windows = should_destroy_overlay_windows_on_hide(overlays_preloaded, true);
    let teardown_method = overlay_teardown_method(destroy_windows);

    let mut hidden_count = 0;
    let mut closed_count = 0;
    let mut close_attempts = Vec::new();
    let mut visible_overlay_errors = Vec::new();

    for label in &window_labels {
        if overlay_hide_superseded_by_new_session(teardown_generation) {
            info!("overlay 隐藏已取消：新的截图会话已开始");
            return Ok(());
        }

        if let Some(window) = app.get_webview_window(label) {
            #[cfg(windows)]
            let hwnd_raw = window.hwnd().ok().map(|tauri_hwnd| tauri_hwnd.0 as isize);

            if teardown_method == OverlayTeardownMethod::Destroy {
                prepare_webview_for_overlay_destroy(&window).await;

                #[cfg(windows)]
                if let Some(hwnd_raw) = hwnd_raw {
                    let hwnd = HWND(hwnd_raw as _);
                    prepare_overlay_window_for_destroy(hwnd);
                    if should_clear_capture_exclusion_after_hide(wda_exclude_supported) {
                        clear_exclude_from_capture(hwnd);
                    }
                }

                tokio::time::sleep(std::time::Duration::from_millis(
                    overlay_destroy_transparent_frame_settle_ms(),
                ))
                .await;

                match window.destroy() {
                    Ok(()) => {
                        closed_count += 1;
                        close_attempts.push((label.clone(), true));
                        debug!("覆盖窗口 {} 已强制销毁并释放 WebView2/DWM 资源", label);
                    }
                    Err(e) => {
                        error!("强制销毁覆盖窗口 {} 失败: {}", label, e);
                        if let Err(hide_error) = window.hide() {
                            error!("销毁失败后降级隐藏覆盖窗口 {} 仍失败: {}", label, hide_error);
                            visible_overlay_errors.push(overlay_destroy_failure_detail(
                                label,
                                format!("{}; hide: {}", e, hide_error),
                                false,
                            ));
                        } else {
                            hidden_count += 1;
                            warn!("销毁失败后已降级隐藏覆盖窗口 {}，避免黑屏遮罩继续可见", label);
                            if overlay_destroy_failure_blocks_ocr(true) {
                                visible_overlay_errors
                                    .push(overlay_destroy_failure_detail(label, &e, true));
                            }
                        }
                        close_attempts.push((label.clone(), false));
                    }
                }
            } else if let Err(e) = window.hide() {
                error!("隐藏覆盖窗口 {} 失败: {}", label, e);
            } else {
                hidden_count += 1;
                debug!("覆盖窗口 {} 已隐藏", label);

                #[cfg(windows)]
                if should_clear_capture_exclusion_after_hide(wda_exclude_supported) {
                    if let Some(hwnd_raw) = hwnd_raw {
                        clear_exclude_from_capture(HWND(hwnd_raw as _));
                    }
                }
            }
        }
    }

    if teardown_method == OverlayTeardownMethod::Destroy {
        let remaining_window_labels = retained_overlay_labels_after_close_attempts(&close_attempts);
        if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
            *windows = remaining_window_labels.clone();
        }
        if let Ok(mut ready) = OVERLAY_READY.lock() {
            ready.retain(|label| remaining_window_labels.contains(label));
        }
        OVERLAYS_PRELOADED.store(false, Ordering::SeqCst);
        if !remaining_window_labels.is_empty() {
            warn!(
                "{} 个 overlay 窗口关闭失败，保留跟踪以便下次恢复/清理",
                remaining_window_labels.len()
            );
        }
    }

    // 同步关闭 OCR 结果窗口
    if let Some(ocr_window) = app.get_webview_window("ocr-result") {
        if let Err(e) = ocr_window.close() {
            warn!("关闭 OCR 结果窗口失败: {}", e);
        }
    }

    if teardown_method == OverlayTeardownMethod::Destroy {
        info!("已强制销毁 {} 个覆盖窗口（释放 WebView2/DWM 资源，避免黑屏残留）", closed_count);
    } else {
        info!("已隐藏 {} 个覆盖窗口", hidden_count);
    }

    if should_force_desktop_repaint_after_teardown(teardown_method, wda_exclude_supported) {
        force_desktop_repaint_after_teardown();
    } else {
        debug!("WDA 隐藏复用路径跳过全桌面 RedrawWindow，避免 OCR 后 2~3s 卡顿");
    }

    let visible_overlay_result = visible_overlay_teardown_error(&visible_overlay_errors);
    let region_drain_result = overlay_region_drain_teardown_error(region_drain_outcome);
    finish_overlay_region_capture_drain();

    visible_overlay_result?;
    region_drain_result
}

/// 创建覆盖窗口
///
/// 在指定显示器上创建全屏透明覆盖窗口，用于截图选区。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `monitor_id`: 目标显示器 ID（从 `get_monitors()` 获取）
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息
///
/// # 窗口属性
///
/// - `transparent`: true - 允许窗口透明
/// - `decorations`: false - 无边框、无标题栏
/// - `always_on_top`: true - 置顶显示
/// - `skip_taskbar`: true - 不在任务栏显示
/// - `resizable`: false - 不可调整大小
/// - `focused`: false - 不抢系统焦点，避免和 OCR/结果面板争抢前台
///
/// # 高 DPI 处理
///
/// 窗口位置和尺寸都使用物理像素，确保在高 DPI 显示器上正确覆盖整个屏幕。
///
/// # 示例
///
/// ```ignore
/// // 在主显示器上创建覆盖窗口
/// create_overlay_window(app, 0).await?;
///
/// // 在所有显示器上创建覆盖窗口
/// let monitors = get_monitors(app.clone()).await?;
/// for monitor in monitors {
///     create_overlay_window(app.clone(), monitor.id).await?;
/// }
/// ```
#[tauri::command]
pub async fn create_overlay_window(app: tauri::AppHandle, monitor_id: u32) -> HuGeResult<()> {
    info!("创建覆盖窗口，目标显示器: {}", monitor_id);

    // 获取所有显示器
    let monitors = app
        .available_monitors()
        .map_err(|e| HuGeError::WindowError(format!("获取显示器列表失败: {}", e)))?;

    if monitors.is_empty() {
        return Err(HuGeError::WindowError("未检测到任何显示器".to_string()));
    }

    // 查找目标显示器
    let target_monitor = monitors.get(monitor_id as usize).ok_or_else(|| {
        HuGeError::WindowError(format!(
            "显示器 {} 不存在，可用显示器数量: {}",
            monitor_id,
            monitors.len()
        ))
    })?;

    // 获取显示器位置和尺寸（物理像素）
    let position = target_monitor.position();
    let size = target_monitor.size();
    let scale_factor = target_monitor.scale_factor();
    let monitor_name =
        target_monitor.name().cloned().unwrap_or_else(|| format!("显示器 {}", monitor_id));

    // 关键：将物理像素转换为逻辑像素
    // Tauri 的 position() 和 inner_size() 接受逻辑像素
    let logical_width = size.width as f64 / scale_factor;
    let logical_height = size.height as f64 / scale_factor;
    let logical_x = position.x as f64 / scale_factor;
    let logical_y = position.y as f64 / scale_factor;

    debug!(
        "目标显示器: {} @ ({}, {}), 物理尺寸: {}x{}, 逻辑尺寸: {:.0}x{:.0}, DPR: {:.2}",
        monitor_name,
        position.x,
        position.y,
        size.width,
        size.height,
        logical_width,
        logical_height,
        scale_factor
    );

    // 生成唯一的窗口标签
    let window_label = format!("overlay-{}", monitor_id);

    // 检查窗口是否已存在
    if let Some(window) = app.get_webview_window(&window_label) {
        if should_reuse_existing_overlay_window() {
            warn!("覆盖窗口 {} 已存在，直接显示", window_label);
            // 发送重置事件
            if let Err(e) = window.emit("overlay-reset", ()) {
                warn!("发送 overlay-reset 事件失败: {}", e);
            }

            let _ = window.eval(
                "document.documentElement.style.opacity='1';document.body.style.opacity='1';",
            );

            #[cfg(windows)]
            if let Ok(hwnd) = window.hwnd() {
                let hwnd = HWND(hwnd.0);
                restore_overlay_window_for_show(
                    hwnd,
                    position.x,
                    position.y,
                    size.width,
                    size.height,
                );
                set_exclude_from_capture(hwnd);
                if should_force_overlay_focus_automatically() {
                    force_foreground_window(hwnd);
                }
            }

            window.show().map_err(|e| HuGeError::WindowError(format!("显示窗口失败: {}", e)))?;
            if should_force_overlay_focus_automatically() {
                window
                    .set_focus()
                    .map_err(|e| HuGeError::WindowError(format!("聚焦窗口失败: {}", e)))?;
            }
            if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
                if !windows.contains(&window_label) {
                    windows.push(window_label.clone());
                }
            }
            return Ok(());
        }

        warn!("覆盖窗口 {} 已存在，将强制销毁后重建，避免复用 DWM 残留表面", window_label);
        prepare_webview_for_overlay_destroy(&window).await;

        #[cfg(windows)]
        if let Ok(hwnd) = window.hwnd() {
            let hwnd = HWND(hwnd.0);
            prepare_overlay_window_for_destroy(hwnd);
            clear_exclude_from_capture(hwnd);
        }

        tokio::time::sleep(std::time::Duration::from_millis(
            overlay_destroy_transparent_frame_settle_ms(),
        ))
        .await;

        window
            .destroy()
            .map_err(|e| HuGeError::WindowError(format!("销毁旧覆盖窗口失败: {}", e)))?;

        forget_overlay_window_label(&window_label);
        OVERLAYS_PRELOADED.store(false, Ordering::SeqCst);

        tokio::time::sleep(std::time::Duration::from_millis(
            overlay_destroy_transparent_frame_settle_ms(),
        ))
        .await;
    }

    // 创建覆盖窗口
    let config = OverlayConfig::default();

    let window = WebviewWindowBuilder::new(
        &app,
        &window_label,
        WebviewUrl::App(config.url.into()),
    )
    // 核心属性：透明、无边框、置顶、无阴影
    .transparent(true)
    .decorations(false)
    .shadow(false)  // 关键：禁用窗口阴影，避免位置偏移
    .always_on_top(true)
    // 窗口位置和尺寸（逻辑像素）
    .position(logical_x, logical_y)
    .inner_size(logical_width, logical_height)
    // 窗口行为
    .skip_taskbar(config.skip_taskbar)
    .resizable(config.resizable)
    .maximizable(config.maximizable)
    .minimizable(config.minimizable)
    // 初始状态：先隐藏，等前端加载完成后再显示（避免 WebView2 白屏问题）
    .visible(false)
    .focused(should_create_overlay_window_focused())
    // 窗口标题（调试用）
    .title(format!("截图覆盖 - {}", monitor_name))
    .build()
    .map_err(|e| HuGeError::WindowError(format!("创建覆盖窗口失败: {}", e)))?;

    // 关键：设置 WDA_EXCLUDEFROMCAPTURE，使 overlay 不被截图捕获
    #[cfg(windows)]
    {
        if let Ok(hwnd) = window.hwnd() {
            set_exclude_from_capture(HWND(hwnd.0));
        }
    }

    // 记录窗口标签
    if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
        if !windows.contains(&window_label) {
            windows.push(window_label.clone());
        }
    }

    info!(
        "覆盖窗口 {} 创建成功，逻辑位置: ({:.0}, {:.0}), 逻辑尺寸: {:.0}x{:.0}",
        window_label, logical_x, logical_y, logical_width, logical_height
    );

    // 注意：这里只创建隐藏窗口。show_overlay_windows 会等前端 ready、背景图加载完成后再显示，
    // 避免慢加载或事件丢失时暴露黑色 WebView2 透明层。
    Ok(())
}

/// 创建所有显示器的覆盖窗口
///
/// 在所有连接的显示器上创建覆盖窗口，用于多显示器截图场景。
/// 如果窗口已预加载，则直接显示。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功返回创建/显示的窗口数量，失败返回错误信息
#[tauri::command]
pub async fn create_all_overlay_windows(app: tauri::AppHandle) -> HuGeResult<u32> {
    // 如果已预加载，直接显示
    // 使用 Box::pin 避免 async 递归导致的无限大小 Future
    if OVERLAYS_PRELOADED.load(Ordering::SeqCst) {
        return Box::pin(show_overlay_windows(app)).await;
    }

    info!("创建所有显示器的覆盖窗口...");

    let monitors = app
        .available_monitors()
        .map_err(|e| HuGeError::WindowError(format!("获取显示器列表失败: {}", e)))?;

    let monitor_count = monitors.len() as u32;
    info!("检测到 {} 个显示器", monitor_count);

    let mut created_count = 0u32;
    let mut errors = Vec::new();

    for (index, _monitor) in monitors.iter().enumerate() {
        match create_overlay_window(app.clone(), index as u32).await {
            Ok(()) => {
                created_count += 1;
            }
            Err(e) => {
                error!("创建显示器 {} 的覆盖窗口失败: {}", index, e);
                errors.push(format!("显示器 {}: {}", index, e));
            }
        }
    }

    if !errors.is_empty() {
        warn!("部分覆盖窗口创建失败: {:?}", errors);
    }

    info!("成功创建 {}/{} 个覆盖窗口", created_count, monitor_count);
    Ok(created_count)
}

/// 关闭指定的覆盖窗口
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `monitor_id`: 目标显示器 ID
#[tauri::command]
pub async fn close_overlay_window(app: tauri::AppHandle, monitor_id: u32) -> HuGeResult<()> {
    let window_label = format!("overlay-{}", monitor_id);
    info!("销毁覆盖窗口: {}", window_label);

    if let Some(window) = app.get_webview_window(&window_label) {
        prepare_webview_for_overlay_destroy(&window).await;

        #[cfg(windows)]
        if let Ok(tauri_hwnd) = window.hwnd() {
            let hwnd = HWND(tauri_hwnd.0);
            prepare_overlay_window_for_destroy(hwnd);
            clear_exclude_from_capture(hwnd);
        }

        tokio::time::sleep(std::time::Duration::from_millis(
            overlay_destroy_transparent_frame_settle_ms(),
        ))
        .await;

        window.destroy().map_err(|e| HuGeError::WindowError(format!("销毁窗口失败: {}", e)))?;

        // 从记录中移除
        forget_overlay_window_label(&window_label);

        force_desktop_repaint_after_teardown();

        info!("覆盖窗口 {} 已强制销毁", window_label);
    } else {
        debug!("覆盖窗口 {} 不存在，无需关闭", window_label);
    }

    // 如果所有窗口都关闭了，重置预加载标志
    if let Ok(windows) = OVERLAY_WINDOWS.lock() {
        if windows.is_empty() {
            OVERLAYS_PRELOADED.store(false, Ordering::SeqCst);
        }
    }

    Ok(())
}

/// 关闭所有覆盖窗口
///
/// 关闭所有截图选区覆盖窗口，通常在截图完成或取消时调用。
/// 注意：推荐使用 `hide_overlay_windows` 而不是此函数，以保持预加载状态。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 成功返回 `Ok(())`，失败返回错误信息
#[tauri::command]
pub async fn close_all_overlays(app: tauri::AppHandle) -> HuGeResult<()> {
    info!("关闭所有覆盖窗口...");

    // 获取所有覆盖窗口。除了内部记录，也扫描运行时真实存在的 overlay-* 窗口，
    // 避免记录不同步时遗漏全屏透明窗口，造成桌面黑屏残留。
    let window_labels = teardown_overlay_window_labels(&app);

    let mut closed_count = 0;
    let mut hidden_count = 0;
    let mut errors = Vec::new();
    let mut close_attempts = Vec::new();
    let mut visible_overlay_errors = Vec::new();

    for label in &window_labels {
        if let Some(window) = app.get_webview_window(label) {
            prepare_webview_for_overlay_destroy(&window).await;

            #[cfg(windows)]
            if let Ok(tauri_hwnd) = window.hwnd() {
                let hwnd = HWND(tauri_hwnd.0);
                prepare_overlay_window_for_destroy(hwnd);
                clear_exclude_from_capture(hwnd);
            }

            tokio::time::sleep(std::time::Duration::from_millis(
                overlay_destroy_transparent_frame_settle_ms(),
            ))
            .await;

            match window.destroy() {
                Ok(()) => {
                    closed_count += 1;
                    close_attempts.push((label.clone(), true));
                    debug!("覆盖窗口 {} 已强制销毁", label);
                }
                Err(e) => {
                    error!("强制销毁覆盖窗口 {} 失败: {}", label, e);
                    if let Err(hide_error) = window.hide() {
                        error!("销毁失败后降级隐藏覆盖窗口 {} 仍失败: {}", label, hide_error);
                        visible_overlay_errors.push(overlay_destroy_failure_detail(
                            label,
                            format!("{}; hide: {}", e, hide_error),
                            false,
                        ));
                    } else {
                        hidden_count += 1;
                        warn!("销毁失败后已降级隐藏覆盖窗口 {}，避免黑屏遮罩继续可见", label);
                        if overlay_destroy_failure_blocks_ocr(true) {
                            visible_overlay_errors
                                .push(overlay_destroy_failure_detail(label, &e, true));
                        }
                    }
                    close_attempts.push((label.clone(), false));
                    errors.push(format!("{}: {}", label, e));
                }
            }
        }
    }

    let remaining_window_labels = retained_overlay_labels_after_close_attempts(&close_attempts);
    if let Ok(mut windows) = OVERLAY_WINDOWS.lock() {
        *windows = remaining_window_labels.clone();
    }
    if let Ok(mut ready) = OVERLAY_READY.lock() {
        ready.retain(|label| remaining_window_labels.contains(label));
    }
    OVERLAYS_PRELOADED.store(false, Ordering::SeqCst);
    force_desktop_repaint_after_teardown();

    if !errors.is_empty() {
        warn!("部分覆盖窗口关闭失败: {:?}", errors);
        warn!(
            "{} 个 overlay 窗口关闭失败，保留跟踪以便下次恢复/清理",
            remaining_window_labels.len()
        );
    }

    info!("已强制销毁 {} 个覆盖窗口，降级隐藏 {} 个覆盖窗口", closed_count, hidden_count);

    visible_overlay_teardown_error(&visible_overlay_errors)
}

/// 获取所有覆盖窗口的标签
///
/// 用于调试和状态查询
#[tauri::command]
pub async fn get_overlay_windows() -> HuGeResult<Vec<String>> {
    let windows = OVERLAY_WINDOWS
        .lock()
        .map_err(|e| HuGeError::WindowError(format!("获取窗口列表失败: {}", e)))?;
    Ok(windows.clone())
}

/// 设置覆盖窗口是否忽略鼠标事件
///
/// 当设置为 true 时，鼠标事件会穿透窗口传递给下层窗口。
/// 这在某些场景下有用，比如只显示选区预览而不需要交互。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `monitor_id`: 目标显示器 ID
/// - `ignore`: 是否忽略鼠标事件
#[tauri::command]
pub async fn set_overlay_ignore_cursor(
    app: tauri::AppHandle,
    monitor_id: u32,
    ignore: bool,
) -> HuGeResult<()> {
    let window_label = format!("overlay-{}", monitor_id);
    debug!("设置覆盖窗口 {} 忽略鼠标事件: {}", window_label, ignore);

    let window = app
        .get_webview_window(&window_label)
        .ok_or_else(|| HuGeError::WindowError(format!("覆盖窗口 {} 不存在", window_label)))?;

    window
        .set_ignore_cursor_events(ignore)
        .map_err(|e| HuGeError::WindowError(format!("设置忽略鼠标事件失败: {}", e)))?;

    Ok(())
}

/// 检查覆盖窗口是否已预加载
#[tauri::command]
pub async fn is_overlay_preloaded() -> bool {
    OVERLAYS_PRELOADED.load(Ordering::SeqCst)
}

/// 前端通知后端 overlay 已就绪
///
/// 前端在 DOM 加载完成并准备好接收事件后调用此命令。
/// 后端记录就绪状态，用于判断是否可以安全显示窗口。
#[tauri::command]
pub async fn overlay_ready(app: tauri::AppHandle, window: tauri::WebviewWindow) -> HuGeResult<()> {
    if !overlay_window_label_is_current(&app, &window) {
        return Err(HuGeError::WindowError(format!(
            "忽略非当前 overlay 窗口的 ready 事件: {}",
            window.label()
        )));
    }

    let window_label = window.label().to_string();

    // 记录就绪状态（overlay-reset 与 overlay-init 可能各通知一次）
    let newly_ready = if let Ok(mut ready_set) = OVERLAY_READY.lock() {
        ready_set.insert(window_label.clone())
    } else {
        false
    };
    if newly_ready {
        info!("前端 {} 已就绪", window_label);
    } else {
        debug!("前端 {} 重复就绪通知，已忽略", window_label);
    }

    // 再次确保焦点（前端就绪后的双保险）
    if let Some(window) = app.get_webview_window(&window_label) {
        // 如果窗口可见，再次强制焦点
        if window.is_visible().unwrap_or(false) {
            if !should_force_overlay_focus_automatically() {
                debug!("跳过 overlay 自动抢焦点: {}", window_label);
                return Ok(());
            }

            if should_skip_overlay_focus_restore(&app, "overlay_ready") {
                return Ok(());
            }

            #[cfg(windows)]
            {
                if let Ok(hwnd) = window.hwnd() {
                    let hwnd = HWND(hwnd.0);
                    force_foreground_window(hwnd);
                }
            }

            if let Err(e) = window.set_focus() {
                warn!("overlay_ready 设置焦点失败: {}", e);
            }

            // 再次执行 WebView 焦点脚本
            if let Err(e) = window.eval("window.focus(); document.body.focus(); if(document.querySelector('.overlay-mask')) document.querySelector('.overlay-mask').focus();") {
                warn!("overlay_ready 执行焦点脚本失败: {}", e);
            }
        }
    }

    Ok(())
}

/// 前端通知后端 overlay 背景图已加载完成，可以安全显示窗口。
#[tauri::command]
pub async fn overlay_background_ready(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
) -> HuGeResult<()> {
    if !overlay_window_label_is_current(&app, &window) {
        return Err(HuGeError::WindowError(format!(
            "忽略非当前 overlay 窗口的背景就绪事件: {}",
            window.label()
        )));
    }

    let window_label = window.label().to_string();
    info!("前端 {} 背景已加载完成", window_label);

    if let Ok(mut ready_set) = OVERLAY_BACKGROUND_READY.lock() {
        ready_set.insert(window_label);
    }

    Ok(())
}

/// 强制恢复 overlay 窗口焦点
///
/// 当 overlay 在截图会话中丢失焦点时，前端调用此命令
/// 使用 Windows API 强制将窗口设为前台并置顶。
#[tauri::command]
pub async fn overlay_force_focus(app: tauri::AppHandle) -> HuGeResult<()> {
    if should_skip_overlay_focus_restore(&app, "overlay_force_focus") {
        return Ok(());
    }

    // 查找当前活跃的 overlay 窗口
    for window in app.webview_windows().values() {
        let label = window.label();
        if label.starts_with("overlay-") {
            if let Ok(true) = window.is_visible() {
                debug!("强制恢复 overlay 焦点: {}", label);

                // 使用 Windows API 强制前台焦点
                #[cfg(windows)]
                {
                    if let Ok(tauri_hwnd) = window.hwnd() {
                        // Tauri 的 HWND (windows 0.61) 和项目的 HWND (windows 0.58)
                        // 类型不同，通过原始指针转换
                        let raw_hwnd = tauri_hwnd.0;
                        let hwnd = HWND(raw_hwnd);
                        force_foreground_window(hwnd);
                    }
                }

                // Tauri 层面也设置焦点
                let _ = window.set_focus();

                // WebView 焦点
                let _ = window.eval("window.focus();");

                break;
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::screenshot::CaptureResult;
    use serial_test::serial;

    #[test]
    #[serial]
    fn test_pre_capture_lookup_rejects_spanning_selection() {
        clear_pre_capture_cache();
        set_pre_capture_caches(vec![
            CaptureResult {
                path: "left.bmp".to_string(),
                width: 1600,
                height: 900,
                dpr: 1.0,
                x: 0,
                y: 0,
                monitor_id: 0,
                image_hash: None,
                file_size: None,
                capture_time_ms: None,
                capture_engine: Some("pre_capture".to_string()),
            },
            CaptureResult {
                path: "right.bmp".to_string(),
                width: 1600,
                height: 900,
                dpr: 1.25,
                x: 1600,
                y: 0,
                monitor_id: 1,
                image_hash: None,
                file_size: None,
                capture_time_ms: None,
                capture_engine: Some("pre_capture".to_string()),
            },
        ]);

        let rect = crate::screenshot::capture::Rect { x: 1400, y: 120, width: 500, height: 220 };
        assert!(find_pre_capture_for_rect(&rect).is_none());

        clear_pre_capture_cache();
    }

    #[test]
    #[serial]
    fn test_pre_capture_lookup_returns_single_monitor_cache_when_fully_contained() {
        clear_pre_capture_cache();
        set_pre_capture_caches(vec![CaptureResult {
            path: "single.bmp".to_string(),
            width: 1600,
            height: 900,
            dpr: 1.0,
            x: -1600,
            y: 0,
            monitor_id: 2,
            image_hash: None,
            file_size: None,
            capture_time_ms: None,
            capture_engine: Some("pre_capture".to_string()),
        }]);

        let rect = crate::screenshot::capture::Rect { x: -1200, y: 80, width: 300, height: 160 };
        let hit = find_pre_capture_for_rect(&rect).expect("应该命中单屏预截图缓存");
        assert_eq!(hit.monitor_id, 2);

        clear_pre_capture_cache();
    }

    #[test]
    fn test_overlay_config_default() {
        let config = OverlayConfig::default();
        assert_eq!(config.label_prefix, "overlay");
        assert!(config.skip_taskbar);
        assert!(!config.resizable);
    }

    #[test]
    fn test_window_label_format() {
        let label = format!("overlay-{}", 0);
        assert_eq!(label, "overlay-0");

        let label = format!("overlay-{}", 1);
        assert_eq!(label, "overlay-1");
    }

    #[test]
    fn test_overlay_event_targets_only_overlay_windows() {
        assert!(is_overlay_event_target("overlay-0"));
        assert!(is_overlay_event_target("overlay-12"));
        assert!(!is_overlay_event_target("main"));
        assert!(!is_overlay_event_target("ocr-result"));
        assert!(!is_overlay_event_target("overlay-preview"));
        assert!(!is_overlay_event_target("overlay-"));
    }

    #[test]
    fn test_overlay_background_publish_waits_for_all_ready_windows() {
        let mut ready = std::collections::HashSet::new();
        ready.insert("overlay-1".to_string());

        let labels = vec!["overlay-0".to_string(), "overlay-1".to_string()];

        assert_eq!(overlay_ready_missing_labels(&labels, &ready), vec!["overlay-0".to_string()]);

        ready.insert("overlay-0".to_string());

        assert!(overlay_ready_missing_labels(&labels, &ready).is_empty());
    }

    #[test]
    #[serial]
    fn test_overlay_session_ready_state_is_cleared_between_sessions() {
        OVERLAY_READY.lock().expect("overlay ready lock").insert("overlay-0".to_string());
        OVERLAY_BACKGROUND_READY
            .lock()
            .expect("overlay background ready lock")
            .insert("overlay-0".to_string());

        clear_overlay_session_ready_state();

        assert!(OVERLAY_READY.lock().expect("overlay ready lock").is_empty());
        assert!(OVERLAY_BACKGROUND_READY.lock().expect("overlay background ready lock").is_empty());
    }

    #[test]
    fn test_cleanup_pre_capture_results_removes_unpublished_files() {
        let temp_dir = tempfile::tempdir().expect("tempdir");
        let path = temp_dir.path().join("pre-capture.bmp");
        std::fs::write(&path, b"bmp").expect("write temp pre-capture");

        let results = vec![CaptureResult {
            path: path.to_string_lossy().to_string(),
            width: 10,
            height: 10,
            dpr: 1.0,
            x: 0,
            y: 0,
            monitor_id: 0,
            image_hash: None,
            file_size: None,
            capture_time_ms: None,
            capture_engine: Some("pre_capture".to_string()),
        }];

        cleanup_pre_capture_results(&results, "test");

        assert!(!path.exists());
    }

    #[test]
    fn test_wda_exclude_supported_only_on_windows_10_2004_or_newer() {
        assert!(!is_wda_exclude_supported_by_version(10, 0, 18363));
        assert!(is_wda_exclude_supported_by_version(10, 0, 19041));
        assert!(is_wda_exclude_supported_by_version(10, 0, 22631));
        assert!(is_wda_exclude_supported_by_version(11, 0, 22000));
    }

    #[test]
    fn test_overlay_preload_follows_wda_support() {
        assert!(!should_preload_overlay_windows(true));
        assert!(should_preload_overlay_windows(false));
    }

    #[test]
    fn test_overlay_hide_superseded_when_new_session_starts() {
        let previous = OVERLAY_GENERATION.load(Ordering::SeqCst);
        let teardown_generation = OVERLAY_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;
        assert!(!overlay_hide_superseded_by_new_session(teardown_generation));

        let _ = OVERLAY_GENERATION.fetch_add(1, Ordering::SeqCst);
        assert!(overlay_hide_superseded_by_new_session(teardown_generation));

        OVERLAY_GENERATION.store(previous, Ordering::SeqCst);
    }

    #[test]
    fn test_overlay_destroy_on_hide_only_when_wda_unsupported() {
        assert!(!should_destroy_overlay_windows_on_hide(false, true));
        assert!(!should_destroy_overlay_windows_on_hide(true, true));
        assert!(should_destroy_overlay_windows_on_hide(false, false));
        assert!(should_destroy_overlay_windows_on_hide(true, false));
    }

    #[test]
    fn test_capture_exclusion_clear_is_skipped_when_wda_exclude_is_unsupported() {
        assert!(!should_clear_capture_exclusion_after_hide(false));
        assert!(should_clear_capture_exclusion_after_hide(true));
    }

    #[test]
    fn test_overlay_destroy_path_uses_force_destroy() {
        assert_eq!(overlay_teardown_method(true), OverlayTeardownMethod::Destroy);
        assert_eq!(overlay_teardown_method(false), OverlayTeardownMethod::Hide);
    }

    #[test]
    fn test_region_capture_timeout_blocks_ocr_after_overlay_destroy() {
        let error =
            overlay_region_drain_teardown_error(OverlayRegionDrainOutcome::TimedOut { active: 1 })
                .expect_err("OCR must be blocked while old region capture is still active");

        assert!(error.to_string().contains("区域截图裁剪仍未结束"));
        assert!(error.to_string().contains("已阻止 OCR"));
    }

    #[test]
    fn test_region_capture_drain_allows_ocr() {
        assert!(overlay_region_drain_teardown_error(OverlayRegionDrainOutcome::Drained).is_ok());
    }

    #[cfg(windows)]
    #[test]
    fn test_desktop_repaint_targets_include_explorer_wallpaper_windows() {
        let targets = desktop_repaint_target_class_names();

        assert!(targets.contains(&"Progman"));
        assert!(targets.contains(&"WorkerW"));
        assert!(targets.contains(&"SHELLDLL_DefView"));
    }

    #[test]
    fn test_overlay_windows_are_created_without_initial_focus() {
        assert!(!should_create_overlay_window_focused());
    }

    #[test]
    fn test_overlay_does_not_force_focus_automatically() {
        assert!(!should_force_overlay_focus_automatically());
    }

    #[test]
    fn test_teardown_labels_include_untracked_runtime_overlays() {
        let labels = merge_overlay_window_labels(
            vec!["overlay-0".to_string(), "main".to_string(), "overlay-0".to_string()],
            vec!["overlay-1".to_string(), "ocr-result".to_string(), "overlay-preview".to_string()],
        );

        assert_eq!(labels, vec!["overlay-0".to_string(), "overlay-1".to_string()]);
    }

    #[test]
    fn test_overlay_hwnd_is_hidden_before_destroy() {
        assert!(should_hide_overlay_hwnd_before_destroy());
    }

    #[cfg(windows)]
    #[test]
    fn test_overlay_destroy_preserves_hwnd_bounds() {
        assert!(overlay_destroy_window_pos_preserves_bounds());
    }

    #[cfg(windows)]
    #[test]
    fn test_overlay_destroy_hides_without_activation() {
        assert!(overlay_destroy_window_pos_hides_without_activation());
    }

    #[cfg(windows)]
    #[test]
    fn test_overlay_destroy_clears_topmost_z_order() {
        assert!(overlay_destroy_window_pos_clears_topmost());
    }

    #[test]
    fn test_overlay_destroy_waits_for_transparent_frame_before_destroy() {
        assert!(overlay_destroy_transparent_frame_settle_ms() >= 50);
    }

    #[test]
    fn test_overlay_destroy_policy_uses_two_settle_windows() {
        assert_eq!(overlay_destroy_settle_window_count(), 2);
    }

    #[test]
    fn test_existing_overlay_window_is_recreated_not_reused() {
        assert!(!should_reuse_existing_overlay_window());
    }

    #[test]
    #[serial]
    fn test_forget_overlay_window_label_clears_all_tracking_state() {
        {
            let mut windows = OVERLAY_WINDOWS.lock().expect("overlay windows lock");
            windows.clear();
            windows.extend(["overlay-0".to_string(), "overlay-1".to_string()]);
        }
        {
            let mut ready = OVERLAY_READY.lock().expect("overlay ready lock");
            ready.clear();
            ready.extend(["overlay-0".to_string(), "overlay-1".to_string()]);
        }

        forget_overlay_window_label("overlay-0");

        assert_eq!(OVERLAY_WINDOWS.lock().expect("overlay windows lock").as_slice(), ["overlay-1"]);
        assert!(!OVERLAY_READY.lock().expect("overlay ready lock").contains("overlay-0"));
        assert!(OVERLAY_READY.lock().expect("overlay ready lock").contains("overlay-1"));

        OVERLAY_WINDOWS.lock().expect("overlay windows lock").clear();
        OVERLAY_READY.lock().expect("overlay ready lock").clear();
    }

    #[test]
    fn test_destroy_path_retains_only_failed_close_labels() {
        let retained = retained_overlay_labels_after_close_attempts(&[
            ("overlay-0".to_string(), true),
            ("overlay-1".to_string(), false),
            ("overlay-2".to_string(), true),
        ]);

        assert_eq!(retained, vec!["overlay-1".to_string()]);
    }

    #[test]
    fn test_visible_overlay_teardown_errors_fail_closed() {
        let failed = vec!["overlay-1".to_string()];
        let error = visible_overlay_teardown_error(&failed).expect_err("visible overlay must fail");

        assert!(error.to_string().contains("overlay-1"));
        assert!(error.to_string().contains("已阻止后续 OCR"));
    }

    #[test]
    fn test_visible_overlay_teardown_all_hidden_or_destroyed_is_ok() {
        assert!(visible_overlay_teardown_error(&[]).is_ok());
    }

    #[test]
    fn test_destroy_failure_with_hide_fallback_still_blocks_ocr() {
        assert!(overlay_destroy_failure_blocks_ocr(true));

        let detail = overlay_destroy_failure_detail("overlay-1", "destroy failed", true);
        let error =
            visible_overlay_teardown_error(&[detail]).expect_err("destroy failure is unsafe");

        assert!(error.to_string().contains("overlay-1"));
        assert!(error.to_string().contains("未能彻底释放"));
        assert!(error.to_string().contains("已阻止后续 OCR"));
    }

    #[test]
    fn test_overlay_never_captures_static_snapshot_after_showing_overlay() {
        assert!(!should_capture_static_snapshot_after_overlay());
    }

    #[test]
    fn test_overlay_desktop_repaint_policy() {
        assert!(should_force_desktop_repaint_after_teardown(
            OverlayTeardownMethod::Destroy,
            true,
        ));
        assert!(!should_force_desktop_repaint_after_teardown(
            OverlayTeardownMethod::Hide,
            true,
        ));
        assert!(should_force_desktop_repaint_after_teardown(
            OverlayTeardownMethod::Hide,
            false,
        ));
    }

    #[test]
    fn test_overlap_pre_capture_only_on_wda_preloaded_path() {
        assert!(should_overlap_pre_capture_with_overlay_prep(true, true));
        assert!(!should_overlap_pre_capture_with_overlay_prep(true, false));
        assert!(!should_overlap_pre_capture_with_overlay_prep(false, true));
        assert!(!should_overlap_pre_capture_with_overlay_prep(false, false));
    }

    #[tokio::test]
    async fn test_pre_capture_task_failure_blocks_overlay_session() {
        let task = tokio::task::spawn_blocking(|| {
            Err::<Vec<crate::screenshot::CaptureResult>, HuGeError>(HuGeError::CaptureError(
                "pre-capture failed".to_string(),
            ))
        });

        let result = await_pre_capture_task(task).await;

        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_empty_pre_capture_task_blocks_overlay_session() {
        let task = tokio::task::spawn_blocking(|| {
            Ok::<Vec<crate::screenshot::CaptureResult>, HuGeError>(Vec::new())
        });

        let result = await_pre_capture_task(task).await;

        assert!(result.is_err());
    }

    #[tokio::test]
    #[serial]
    async fn test_overlay_teardown_waits_for_active_region_capture() {
        let _guard = begin_overlay_region_capture().expect("capture guard");

        assert!(!wait_for_overlay_region_captures(std::time::Duration::from_millis(1)).await);
    }

    #[tokio::test]
    #[serial]
    async fn test_overlay_teardown_wait_succeeds_after_region_capture_finishes() {
        let guard = begin_overlay_region_capture().expect("capture guard");
        let drop_task = tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            drop(guard);
        });

        assert!(wait_for_overlay_region_captures(std::time::Duration::from_millis(500)).await);
        drop_task.await.expect("drop task should finish");
    }

    #[test]
    #[serial]
    fn test_overlay_teardown_draining_rejects_new_region_capture() {
        OVERLAY_REGION_CAPTURE_DRAINING.store(true, Ordering::SeqCst);

        let result = begin_overlay_region_capture();

        OVERLAY_REGION_CAPTURE_DRAINING.store(false, Ordering::SeqCst);
        assert!(result.is_err());
        assert_eq!(OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    #[serial]
    async fn test_overlay_teardown_timeout_is_reported_but_does_not_abort_teardown() {
        let guard = begin_overlay_region_capture().expect("capture guard");

        let outcome =
            drain_overlay_region_captures_for_teardown(std::time::Duration::from_millis(1)).await;

        assert_eq!(outcome, OverlayRegionDrainOutcome::TimedOut { active: 1 });
        finish_overlay_region_capture_drain();

        assert!(begin_overlay_region_capture().is_err());

        drop(guard);

        let next_guard = begin_overlay_region_capture().expect("old capture drain should reopen");
        drop(next_guard);

        assert_eq!(OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst), 0);
    }

    #[test]
    #[serial]
    fn test_new_overlay_session_resets_closed_region_capture_gate_after_drain() {
        OVERLAY_REGION_CAPTURE_DRAINING.store(true, Ordering::SeqCst);

        reset_overlay_region_capture_gate_for_new_session().expect("drained gate should reset");
        let guard = begin_overlay_region_capture().expect("new session should allow capture");
        drop(guard);

        assert_eq!(OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst), 0);
    }

    #[test]
    #[serial]
    fn test_new_overlay_session_rejects_reset_while_region_capture_active() {
        let guard = begin_overlay_region_capture().expect("capture guard");
        OVERLAY_REGION_CAPTURE_DRAINING.store(true, Ordering::SeqCst);

        assert!(reset_overlay_region_capture_gate_for_new_session().is_err());

        drop(guard);
        OVERLAY_REGION_CAPTURE_DRAINING.store(false, Ordering::SeqCst);
        assert_eq!(OVERLAY_REGION_CAPTURE_IN_PROGRESS.load(Ordering::SeqCst), 0);
    }
}
