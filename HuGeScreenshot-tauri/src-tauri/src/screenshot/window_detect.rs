//! 窗口检测功能
//!
//! 使用 Windows API 实现窗口检测，支持：
//! - 检测指定坐标下的窗口
//! - 获取所有可见窗口列表
//!
//! # 重要说明
//!
//! - 使用 `DwmGetWindowAttribute` 获取真实窗口边界（排除阴影边框）
//! - 坐标系统：逻辑像素用于交互，物理像素用于截图
//! - 窗口句柄可能随时失效，需要检查有效性

use serde::{Deserialize, Serialize};
use tracing::{debug, error, info, warn};

use crate::error::{HuGeError, HuGeResult};
use crate::screenshot::capture::Rect;

#[cfg(windows)]
use std::ffi::OsString;
#[cfg(windows)]
use std::mem::size_of;
#[cfg(windows)]
use std::os::windows::ffi::OsStringExt;
#[cfg(windows)]
use windows::Win32::Foundation::{BOOL, HWND, LPARAM, POINT, RECT, TRUE};
#[cfg(windows)]
use windows::Win32::Graphics::Dwm::{
    DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS,
};
// 注：MonitorFromWindow 和 MONITOR_DEFAULTTONEAREST 保留用于未来 DPI 感知实现
// #[cfg(windows)]
// use windows::Win32::Graphics::Gdi::{MonitorFromWindow, MONITOR_DEFAULTTONEAREST};
#[cfg(windows)]
use windows::Win32::UI::HiDpi::GetDpiForWindow;
#[cfg(windows)]
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetAncestor, GetClassNameW, GetWindowLongW, GetWindowRect, GetWindowTextLengthW,
    GetWindowTextW, IsWindowVisible, WindowFromPoint, GA_ROOT, GWL_EXSTYLE, GWL_STYLE,
    WS_EX_TOOLWINDOW, WS_VISIBLE,
};

/// 窗口信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WindowInfo {
    /// 窗口句柄
    pub hwnd: isize,
    /// 窗口标题
    pub title: String,
    /// 窗口类名
    pub class_name: String,
    /// 窗口边界（逻辑像素坐标）
    pub rect: Rect,
    /// 窗口边界（物理像素坐标）
    pub physical_rect: Rect,
}

/// 检测指定坐标下的窗口
///
/// # 参数
///
/// - `x`: X 坐标（屏幕坐标，物理像素）
/// - `y`: Y 坐标（屏幕坐标，物理像素）
///
/// # 返回
///
/// 返回该坐标下最顶层窗口的信息，如果没有窗口则返回 None
///
/// # 示例
///
/// ```ignore
/// if let Some(window) = detect_window_at(500, 300).await? {
///     println!("窗口标题: {}", window.title);
/// }
/// ```
///
/// # 注意事项
///
/// - 坐标应为屏幕物理像素坐标
/// - 返回的是最顶层可见窗口的根窗口
/// - 如果坐标下没有窗口，返回 None
#[tauri::command]
pub async fn detect_window_at(x: i32, y: i32) -> HuGeResult<Option<WindowInfo>> {
    #[cfg(windows)]
    {
        detect_window_at_impl(x, y)
    }

    #[cfg(not(windows))]
    {
        let _ = (x, y);
        Err(HuGeError::WindowError("窗口检测仅支持 Windows 平台".to_string()))
    }
}

/// 获取所有可见窗口
///
/// # 返回
///
/// 返回所有可见窗口的信息列表
///
/// # 示例
///
/// ```ignore
/// let windows = get_all_windows().await?;
/// for window in windows {
///     println!("{}: {}x{}", window.title, window.rect.width, window.rect.height);
/// }
/// ```
///
/// # 注意事项
///
/// - 只返回可见的顶级窗口
/// - 排除工具窗口（如任务栏按钮）
/// - 排除无标题的窗口
#[tauri::command]
pub async fn get_all_windows() -> HuGeResult<Vec<WindowInfo>> {
    #[cfg(windows)]
    {
        get_all_windows_impl()
    }

    #[cfg(not(windows))]
    {
        Err(HuGeError::WindowError("窗口检测仅支持 Windows 平台".to_string()))
    }
}

/// 根据窗口句柄获取窗口信息
///
/// # 参数
///
/// - `hwnd`: 窗口句柄
///
/// # 返回
///
/// 返回窗口信息，如果窗口无效则返回错误
///
/// # 示例
///
/// ```ignore
/// let info = get_window_info_by_hwnd(hwnd)?;
/// println!("窗口标题: {}", info.title);
/// ```
#[cfg(windows)]
pub fn get_window_info_by_hwnd(hwnd: HWND) -> HuGeResult<WindowInfo> {
    use windows::Win32::UI::WindowsAndMessaging::IsWindow;

    // 验证窗口有效性
    if unsafe { !IsWindow(hwnd).as_bool() } {
        return Err(HuGeError::WindowError(format!("无效的窗口句柄: {:?}", hwnd)));
    }

    get_window_info(hwnd)
}

// ============================================================================
// Windows 平台实现
// ============================================================================

#[cfg(windows)]
fn detect_window_at_impl(x: i32, y: i32) -> HuGeResult<Option<WindowInfo>> {
    debug!("检测坐标 ({}, {}) 下的窗口", x, y);

    let point = POINT { x, y };

    // 使用 WindowFromPoint 获取坐标下的窗口
    let hwnd = unsafe { WindowFromPoint(point) };

    if hwnd.0.is_null() {
        debug!("坐标 ({}, {}) 下没有窗口", x, y);
        return Ok(None);
    }

    // 获取根窗口（顶级窗口）
    let root_hwnd = unsafe { GetAncestor(hwnd, GA_ROOT) };
    let target_hwnd = if !root_hwnd.0.is_null() { root_hwnd } else { hwnd };

    // 检查窗口是否可见
    if unsafe { !IsWindowVisible(target_hwnd).as_bool() } {
        debug!("窗口 {:?} 不可见", target_hwnd);
        return Ok(None);
    }

    // 获取窗口信息
    match get_window_info(target_hwnd) {
        Ok(info) => {
            // 过滤掉自己的覆盖窗口（标题以"截图覆盖"开头）
            if info.title.starts_with("截图覆盖") {
                debug!("跳过自己的覆盖窗口: {}", info.title);
                // 需要遍历查找下一个窗口
                return find_window_below_overlay(x, y);
            }

            info!(
                "检测到窗口: {} ({}), 位置: ({}, {}), 尺寸: {}x{}",
                info.title,
                info.class_name,
                info.rect.x,
                info.rect.y,
                info.rect.width,
                info.rect.height
            );
            Ok(Some(info))
        }
        Err(e) => {
            warn!("获取窗口信息失败: {}", e);
            Ok(None)
        }
    }
}

/// 在覆盖窗口下方查找实际窗口
///
/// 当 WindowFromPoint 返回我们自己的覆盖窗口时，
/// 需要遍历所有窗口（按 Z-order）找到第一个包含该点的非覆盖窗口。
#[cfg(windows)]
fn find_window_below_overlay(x: i32, y: i32) -> HuGeResult<Option<WindowInfo>> {
    use std::cell::RefCell;

    debug!("遍历查找覆盖窗口下方的窗口，搜索点: ({}, {})", x, y);

    // 使用 RefCell 在回调中存储结果
    thread_local! {
        static FOUND_WINDOW: RefCell<Option<WindowInfo>> = const { RefCell::new(None) };
        static SEARCH_POINT: RefCell<(i32, i32)> = const { RefCell::new((0, 0)) };
        static CHECKED_COUNT: RefCell<u32> = const { RefCell::new(0) };
    }

    FOUND_WINDOW.with(|f| *f.borrow_mut() = None);
    SEARCH_POINT.with(|p| *p.borrow_mut() = (x, y));
    CHECKED_COUNT.with(|c| *c.borrow_mut() = 0);

    // 遍历所有窗口（按 Z-order，最顶层在前）
    unsafe extern "system" fn find_callback(hwnd: HWND, _lparam: LPARAM) -> BOOL {
        // 检查窗口是否可见
        if !IsWindowVisible(hwnd).as_bool() {
            return TRUE; // 继续枚举
        }

        // 获取窗口样式
        let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
        let ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE) as u32;

        // 排除不可见窗口
        if (style & WS_VISIBLE.0) == 0 {
            return TRUE;
        }

        // 排除工具窗口
        if (ex_style & WS_EX_TOOLWINDOW.0) != 0 {
            return TRUE;
        }

        // 检查窗口是否被隐藏（Cloaked）- UWP 应用或虚拟桌面后台窗口
        let mut cloaked: u32 = 0;
        let _ = DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            &mut cloaked as *mut u32 as *mut _,
            size_of::<u32>() as u32,
        );
        if cloaked != 0 {
            return TRUE; // 跳过隐藏的窗口
        }

        // 获取窗口信息
        if let Ok(info) = get_window_info(hwnd) {
            // 跳过覆盖窗口
            if info.title.starts_with("截图覆盖") {
                return TRUE;
            }

            // 跳过尺寸为 0 的窗口
            if info.rect.width == 0 || info.rect.height == 0 {
                return TRUE;
            }

            // 检查点是否在窗口内（使用物理像素坐标，因为输入坐标是物理像素）
            let (px, py) = SEARCH_POINT.with(|p| *p.borrow());
            let rect = &info.physical_rect;

            CHECKED_COUNT.with(|c| *c.borrow_mut() += 1);

            // 添加详细日志用于调试
            let contains = px >= rect.x
                && px < rect.x + rect.width as i32
                && py >= rect.y
                && py < rect.y + rect.height as i32;

            if contains {
                // 找到了！
                FOUND_WINDOW.with(|f| *f.borrow_mut() = Some(info));
                return BOOL(0); // 停止枚举
            }
        }

        TRUE // 继续枚举
    }

    let _ = unsafe { EnumWindows(Some(find_callback), LPARAM(0)) };

    let checked = CHECKED_COUNT.with(|c| *c.borrow());
    debug!("遍历检查了 {} 个窗口", checked);

    let result = FOUND_WINDOW.with(|f| f.borrow().clone());

    if let Some(ref info) = result {
        debug!(
            "遍历找到窗口: {} ({}), 位置: ({}, {}), 尺寸: {}x{}",
            info.title,
            info.class_name,
            info.rect.x,
            info.rect.y,
            info.rect.width,
            info.rect.height
        );
    } else {
        debug!("遍历未找到合适的窗口");
    }

    Ok(result)
}

#[cfg(windows)]
fn get_all_windows_impl() -> HuGeResult<Vec<WindowInfo>> {
    debug!("开始枚举所有可见窗口");

    let mut windows: Vec<WindowInfo> = Vec::new();

    // 使用 Box 包装 Vec，通过 LPARAM 传递
    let windows_ptr = &mut windows as *mut Vec<WindowInfo>;

    let result = unsafe { EnumWindows(Some(enum_windows_callback), LPARAM(windows_ptr as isize)) };

    if let Err(e) = result {
        error!("EnumWindows 失败: {:?}", e);
        return Err(HuGeError::WindowError(format!("枚举窗口失败: {:?}", e)));
    }

    info!("枚举到 {} 个可见窗口", windows.len());
    Ok(windows)
}

/// EnumWindows 回调函数
#[cfg(windows)]
unsafe extern "system" fn enum_windows_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let windows = &mut *(lparam.0 as *mut Vec<WindowInfo>);

    // 检查窗口是否可见
    if !IsWindowVisible(hwnd).as_bool() {
        return TRUE; // 继续枚举
    }

    // 获取窗口样式
    let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
    let ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE) as u32;

    // 排除不可见窗口
    if (style & WS_VISIBLE.0) == 0 {
        return TRUE;
    }

    // 排除工具窗口（如任务栏按钮）
    if (ex_style & WS_EX_TOOLWINDOW.0) != 0 {
        return TRUE;
    }

    // 获取窗口标题长度
    let title_len = GetWindowTextLengthW(hwnd);
    if title_len == 0 {
        return TRUE; // 排除无标题窗口
    }

    // 获取窗口信息
    if let Ok(info) = get_window_info(hwnd) {
        // 排除尺寸为 0 的窗口
        if info.rect.width > 0 && info.rect.height > 0 {
            windows.push(info);
        }
    }

    TRUE // 继续枚举
}

/// 获取单个窗口的详细信息
#[cfg(windows)]
fn get_window_info(hwnd: HWND) -> HuGeResult<WindowInfo> {
    // 获取窗口标题
    let title = get_window_title(hwnd)?;

    // 获取窗口类名
    let class_name = get_window_class_name(hwnd)?;

    // 获取窗口边界（使用 DwmGetWindowAttribute 获取真实边界）
    let physical_rect =
        get_window_extended_frame_bounds(hwnd).or_else(|_| get_window_rect_fallback(hwnd))?;

    // 计算逻辑像素坐标（简化处理，假设 DPR = 1）
    // 实际应用中应该根据窗口所在显示器的 DPR 进行转换
    let dpr = get_window_dpr(hwnd);
    let rect = Rect {
        x: (physical_rect.x as f64 / dpr) as i32,
        y: (physical_rect.y as f64 / dpr) as i32,
        width: (physical_rect.width as f64 / dpr) as u32,
        height: (physical_rect.height as f64 / dpr) as u32,
    };

    Ok(WindowInfo { hwnd: hwnd.0 as isize, title, class_name, rect, physical_rect })
}

/// 获取窗口标题
#[cfg(windows)]
fn get_window_title(hwnd: HWND) -> HuGeResult<String> {
    let len = unsafe { GetWindowTextLengthW(hwnd) };
    if len == 0 {
        return Ok(String::new());
    }

    // 分配缓冲区（+1 用于 null 终止符）
    let mut buffer: Vec<u16> = vec![0; (len + 1) as usize];

    let copied = unsafe { GetWindowTextW(hwnd, &mut buffer) };
    if copied == 0 {
        return Ok(String::new());
    }

    // 转换为 Rust 字符串，截断到实际长度
    let os_string = OsString::from_wide(&buffer[..copied as usize]);
    Ok(os_string.to_string_lossy().to_string())
}

/// 获取窗口类名
#[cfg(windows)]
fn get_window_class_name(hwnd: HWND) -> HuGeResult<String> {
    let mut buffer: Vec<u16> = vec![0; 256];

    let len = unsafe { GetClassNameW(hwnd, &mut buffer) };
    if len == 0 {
        return Ok(String::new());
    }

    let os_string = OsString::from_wide(&buffer[..len as usize]);
    Ok(os_string.to_string_lossy().to_string())
}

/// 使用 DwmGetWindowAttribute 获取窗口真实边界
///
/// 这个方法返回用户视觉上看到的真实窗口位置，排除了 Windows 10/11 的阴影边框
#[cfg(windows)]
fn get_window_extended_frame_bounds(hwnd: HWND) -> HuGeResult<Rect> {
    let mut rect = RECT::default();

    let result = unsafe {
        DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            &mut rect as *mut RECT as *mut _,
            size_of::<RECT>() as u32,
        )
    };

    if let Err(e) = result {
        return Err(HuGeError::WindowError(format!("DwmGetWindowAttribute 失败: {:?}", e)));
    }

    Ok(Rect {
        x: rect.left,
        y: rect.top,
        width: (rect.right - rect.left) as u32,
        height: (rect.bottom - rect.top) as u32,
    })
}

/// 使用 GetWindowRect 作为后备方案
#[cfg(windows)]
fn get_window_rect_fallback(hwnd: HWND) -> HuGeResult<Rect> {
    let mut rect = RECT::default();

    let result = unsafe { GetWindowRect(hwnd, &mut rect) };

    if let Err(e) = result {
        return Err(HuGeError::WindowError(format!("GetWindowRect 失败: {:?}", e)));
    }

    Ok(Rect {
        x: rect.left,
        y: rect.top,
        width: (rect.right - rect.left) as u32,
        height: (rect.bottom - rect.top) as u32,
    })
}

/// 获取窗口所在显示器的 DPR
///
/// 使用 GetDpiForWindow API 获取窗口的实际 DPI，然后转换为 DPR。
/// 标准 DPI 为 96，DPR = DPI / 96.0
///
/// # 参数
///
/// - `hwnd`: 窗口句柄
///
/// # 返回
///
/// 返回窗口的设备像素比 (DPR)
///
/// # 示例
///
/// | DPI | DPR | 缩放比例 |
/// |-----|-----|---------|
/// | 96  | 1.0 | 100%    |
/// | 120 | 1.25| 125%    |
/// | 144 | 1.5 | 150%    |
/// | 192 | 2.0 | 200%    |
#[cfg(windows)]
fn get_window_dpr(hwnd: HWND) -> f64 {
    // 标准 DPI 值
    const STANDARD_DPI: f64 = 96.0;

    let dpi = unsafe { GetDpiForWindow(hwnd) };

    if dpi == 0 {
        // 如果获取失败（无效窗口句柄），返回默认值 1.0
        warn!("GetDpiForWindow 返回 0，使用默认 DPR 1.0");
        return 1.0;
    }

    let dpr = dpi as f64 / STANDARD_DPI;
    debug!("窗口 {:?} DPI: {}, DPR: {:.2}", hwnd, dpi, dpr);
    dpr
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_window_info_serialize() {
        let info = WindowInfo {
            hwnd: 12345,
            title: "测试窗口".to_string(),
            class_name: "TestClass".to_string(),
            rect: Rect { x: 0, y: 0, width: 800, height: 600 },
            physical_rect: Rect { x: 0, y: 0, width: 1200, height: 900 },
        };
        let json = serde_json::to_string(&info).unwrap();
        assert!(json.contains("测试窗口"));
        assert!(json.contains("12345"));
    }

    #[test]
    fn test_rect_conversion() {
        let physical = Rect { x: 100, y: 200, width: 1920, height: 1080 };

        // 模拟 DPR = 1.5 的转换
        let dpr = 1.5;
        let logical = Rect {
            x: (physical.x as f64 / dpr) as i32,
            y: (physical.y as f64 / dpr) as i32,
            width: (physical.width as f64 / dpr) as u32,
            height: (physical.height as f64 / dpr) as u32,
        };

        assert_eq!(logical.x, 66);
        assert_eq!(logical.y, 133);
        assert_eq!(logical.width, 1280);
        assert_eq!(logical.height, 720);
    }

    #[cfg(windows)]
    #[test]
    fn test_get_all_windows_returns_vec() {
        // 这个测试只验证函数能正常运行，不验证具体结果
        let result = get_all_windows_impl();
        assert!(result.is_ok());
        let windows = result.unwrap();
        // 至少应该有一些窗口（桌面、任务栏等）
        // 但由于过滤条件，可能为空
        println!("检测到 {} 个窗口", windows.len());
    }
}
