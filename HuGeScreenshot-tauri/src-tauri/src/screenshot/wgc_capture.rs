//! Windows Graphics Capture (WGC) 截图引擎
//!
//! 使用 WGC API 实现高性能屏幕捕获，替代 DXGI Desktop Duplication。
//!
//! # 优势
//!
//! - 通过 HMONITOR 精确匹配显示器，无 ID 不一致问题
//! - 原生支持多显示器和 DPI 缩放
//! - 无需处理 DXGI_ERROR_ACCESS_LOST
//! - D3D11 设备缓存，重复截图极快
//!
//! # 要求
//!
//! - Windows 10 2004 (Build 19041) 或更高版本使用 WGC
//! - 更旧的 Windows 10 版本直接走 DXGI，避免 WGC 拒绝访问后残留图形资源

use std::sync::{mpsc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use tracing::{debug, info, warn};

use crate::error::{HuGeError, HuGeResult};

use windows::core::Interface;
use windows::Foundation::{EventRegistrationToken, TypedEventHandler};
use windows::Graphics::Capture::Direct3D11CaptureFrame;
use windows::Graphics::Capture::Direct3D11CaptureFramePool;
use windows::Graphics::Capture::GraphicsCaptureItem;
use windows::Graphics::Capture::GraphicsCaptureSession;
use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
use windows::Graphics::DirectX::DirectXPixelFormat;
use windows::Graphics::SizeInt32;
use windows::Win32::Foundation::POINT;
use windows::Win32::Graphics::Direct3D::{D3D_DRIVER_TYPE_HARDWARE, D3D_FEATURE_LEVEL_11_0};
use windows::Win32::Graphics::Direct3D11::{
    D3D11CreateDevice, ID3D11Device, ID3D11DeviceContext, ID3D11Multithread, ID3D11Texture2D,
    D3D11_CPU_ACCESS_READ, D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_MAP_READ, D3D11_SDK_VERSION,
    D3D11_TEXTURE2D_DESC, D3D11_USAGE_STAGING,
};
use windows::Win32::Graphics::Dxgi::IDXGIDevice;
use windows::Win32::Graphics::Gdi::{MonitorFromPoint, HMONITOR, MONITOR_DEFAULTTONEAREST};
use windows::Win32::System::SystemInformation::OSVERSIONINFOW;
use windows::Win32::System::WinRT::Direct3D11::CreateDirect3D11DeviceFromDXGIDevice;
use windows::Win32::System::WinRT::Graphics::Capture::IGraphicsCaptureItemInterop;
use windows::Wdk::System::SystemServices::RtlGetVersion;

// ============================================================================
// D3D11 设备缓存（避免每次截图都重新创建）
// ============================================================================

struct CachedDevices {
    d3d_device: ID3D11Device,
    winrt_device: IDirect3DDevice,
    context: ID3D11DeviceContext,
}

// SAFETY: CachedDevices 中的 COM 对象是引用计数的。
// - ID3D11Device: 天然多线程安全（内部有锁）
// - IDirect3DDevice: WinRT COM 引用，线程安全
// - ID3D11DeviceContext（即时上下文）：本身非线程安全，但我们在 create_d3d_devices()
//   中通过 SetMultithreadProtected(true) 启用了 D3D11 内部多线程保护，
//   使 Context 的所有调用都经过 D3D11 内部临界区保护。
unsafe impl Send for CachedDevices {}
unsafe impl Sync for CachedDevices {}

// 全局缓存（线程安全）
static CACHED_DEVICES: OnceLock<Mutex<Option<CachedDevices>>> = OnceLock::new();
static WGC_ACCESS_DENIED_DISABLED_UNTIL: OnceLock<Mutex<Option<Instant>>> = OnceLock::new();

const WGC_ACCESS_DENIED_COOLDOWN: Duration = Duration::from_secs(10 * 60);
const WGC_SAFE_WINDOWS_BUILD: u32 = 19041;

fn is_wgc_access_denied_message(message: &str) -> bool {
    let normalized = message.to_ascii_lowercase();
    normalized.contains("0x80070005")
        || message.contains("拒绝访问")
        || normalized.contains("access is denied")
        || normalized.contains("e_accessdenied")
}

/// 旧版 Windows（build < 19041）上 WGC 易失败；DXGI 仍应尝试（黑帧再回退 GDI）。
pub(crate) fn is_legacy_windows_capture_build(major: u32, minor: u32, build: u32) -> bool {
    major < 10 || (major == 10 && minor == 0 && build < WGC_SAFE_WINDOWS_BUILD)
}

fn should_skip_wgc_for_windows_version(major: u32, minor: u32, build: u32) -> bool {
    is_legacy_windows_capture_build(major, minor, build)
}

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
            warn!("WGC: 获取 Windows 版本失败: {:?}", status);
            None
        }
    }
}

/// 当前系统是否为旧版 Windows（build < 19041），需优先虚拟桌面 GDI 回退。
pub(crate) fn is_legacy_windows_capture_build_on_current_system() -> bool {
    current_windows_version()
        .map(|(major, minor, build)| is_legacy_windows_capture_build(major, minor, build))
        .unwrap_or(true)
}

fn should_skip_wgc_for_current_windows_version() -> bool {
    static SKIP_WGC_FOR_WINDOWS_VERSION: OnceLock<bool> = OnceLock::new();

    *SKIP_WGC_FOR_WINDOWS_VERSION.get_or_init(|| {
        let Some((major, minor, build)) = current_windows_version() else {
            warn!("WGC: 无法确认 Windows 版本，跳过 WGC 并直接使用 DXGI 以避免黑屏风险");
            return true;
        };

        let should_skip = should_skip_wgc_for_windows_version(major, minor, build);
        if should_skip {
            warn!(
                "WGC: Windows {}.{} build {} 低于安全基线 build {}，跳过 WGC；预截图将尝试 DXGI（全黑帧再回退 GDI）",
                major,
                minor,
                build,
                WGC_SAFE_WINDOWS_BUILD
            );
        }
        should_skip
    })
}

fn should_skip_wgc_due_to_access_denied(
    now: Instant,
    disabled_until: Option<Instant>,
) -> bool {
    matches!(disabled_until, Some(until) if now < until)
}

fn wgc_access_denied_disabled_until() -> Option<Instant> {
    let state = WGC_ACCESS_DENIED_DISABLED_UNTIL.get_or_init(|| Mutex::new(None));
    state.lock().ok().and_then(|guard| *guard)
}

fn mark_wgc_access_denied(error: &HuGeError) {
    let disabled_until = Instant::now() + WGC_ACCESS_DENIED_COOLDOWN;
    let state = WGC_ACCESS_DENIED_DISABLED_UNTIL.get_or_init(|| Mutex::new(None));

    if let Ok(mut guard) = state.lock() {
        *guard = Some(disabled_until);
    }

    warn!(
        "WGC 捕获被系统拒绝，{} 秒内跳过 WGC 并直接回退 DXGI，避免反复创建图形捕获资源: {}",
        WGC_ACCESS_DENIED_COOLDOWN.as_secs(),
        error
    );
}

fn clear_wgc_access_denied() {
    let state = WGC_ACCESS_DENIED_DISABLED_UNTIL.get_or_init(|| Mutex::new(None));
    if let Ok(mut guard) = state.lock() {
        *guard = None;
    }
}

fn get_or_create_devices() -> HuGeResult<(ID3D11Device, IDirect3DDevice, ID3D11DeviceContext)> {
    let cache = CACHED_DEVICES.get_or_init(|| Mutex::new(None));
    let mut guard =
        cache.lock().map_err(|e| HuGeError::CaptureError(format!("设备缓存锁获取失败: {}", e)))?;

    if let Some(ref cached) = *guard {
        debug!("WGC: 使用缓存的 D3D11 设备");
        return Ok((
            cached.d3d_device.clone(),
            cached.winrt_device.clone(),
            cached.context.clone(),
        ));
    }

    info!("WGC: 首次创建 D3D11 设备（将被缓存）");
    let (d3d_device, winrt_device) = create_d3d_devices()?;
    let context: ID3D11DeviceContext = unsafe {
        d3d_device
            .GetImmediateContext()
            .map_err(|e| HuGeError::CaptureError(format!("获取 D3D11 上下文失败: {:?}", e)))?
    };

    *guard = Some(CachedDevices {
        d3d_device: d3d_device.clone(),
        winrt_device: winrt_device.clone(),
        context: context.clone(),
    });

    Ok((d3d_device, winrt_device, context))
}

// ============================================================================
// 核心函数
// ============================================================================

/// WGC 截图结果
pub struct WgcCaptureResult {
    /// BGRA 像素数据
    pub data: Vec<u8>,
    /// 图像宽度
    pub width: u32,
    /// 图像高度
    pub height: u32,
}

use super::frame_validity::is_probably_black_frame_bgra;
/// 通过屏幕坐标获取 HMONITOR
fn get_hmonitor_from_position(x: i32, y: i32) -> HuGeResult<HMONITOR> {
    let point = POINT { x, y };
    let hmonitor = unsafe { MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST) };
    if hmonitor.is_invalid() {
        return Err(HuGeError::CaptureError(format!(
            "无法获取坐标 ({}, {}) 对应的 HMONITOR",
            x, y
        )));
    }
    Ok(hmonitor)
}

/// 创建 D3D11 设备和 WinRT Direct3D 设备
fn create_d3d_devices() -> HuGeResult<(ID3D11Device, IDirect3DDevice)> {
    let mut d3d_device: Option<ID3D11Device> = None;

    unsafe {
        D3D11CreateDevice(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            None,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            Some(&[D3D_FEATURE_LEVEL_11_0]),
            D3D11_SDK_VERSION,
            Some(&mut d3d_device),
            None,
            None,
        )
        .map_err(|e| HuGeError::CaptureError(format!("D3D11 设备创建失败: {:?}", e)))?;
    }

    let d3d_device =
        d3d_device.ok_or_else(|| HuGeError::CaptureError("D3D11 设备为空".to_string()))?;

    // 启用 D3D11 多线程保护，使 ImmediateContext 可安全跨线程使用
    unsafe {
        if let Ok(multithread) = d3d_device.cast::<ID3D11Multithread>() {
            let _ = multithread.SetMultithreadProtected(true);
            debug!("WGC: D3D11 多线程保护已启用");
        }
    }

    let dxgi_device: IDXGIDevice = d3d_device
        .cast()
        .map_err(|e| HuGeError::CaptureError(format!("转换为 IDXGIDevice 失败: {:?}", e)))?;

    let winrt_device = unsafe {
        CreateDirect3D11DeviceFromDXGIDevice(&dxgi_device)
            .map_err(|e| HuGeError::CaptureError(format!("创建 WinRT D3D 设备失败: {:?}", e)))?
    };

    let winrt_d3d_device: IDirect3DDevice = winrt_device
        .cast()
        .map_err(|e| HuGeError::CaptureError(format!("转换为 IDirect3DDevice 失败: {:?}", e)))?;

    Ok((d3d_device, winrt_d3d_device))
}

/// 从 HMONITOR 创建 GraphicsCaptureItem
fn create_capture_item_for_monitor(hmonitor: HMONITOR) -> HuGeResult<GraphicsCaptureItem> {
    let interop = windows::core::factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>()
        .map_err(|e| HuGeError::CaptureError(format!("获取 Interop 接口失败: {:?}", e)))?;

    let item: GraphicsCaptureItem = unsafe {
        interop
            .CreateForMonitor(hmonitor)
            .map_err(|e| HuGeError::CaptureError(format!("CreateForMonitor 失败: {:?}", e)))?
    };

    Ok(item)
}

/// 使用 WGC 捕获单帧屏幕截图
///
/// 使用缓存的 D3D11 设备，首次调用后性能显著提升。
pub fn capture_monitor_wgc(
    screen_x: i32,
    screen_y: i32,
    expected_width: u32,
    expected_height: u32,
) -> HuGeResult<WgcCaptureResult> {
    if should_skip_wgc_for_current_windows_version() {
        return Err(HuGeError::CaptureError(
            "当前 Windows 版本已跳过 WGC，直接回退 DXGI".to_string(),
        ));
    }

    if should_skip_wgc_due_to_access_denied(Instant::now(), wgc_access_denied_disabled_until()) {
        return Err(HuGeError::CaptureError(
            "WGC 因此前被系统拒绝访问已临时跳过，直接回退 DXGI".to_string(),
        ));
    }

    let result = capture_monitor_wgc_inner(screen_x, screen_y, expected_width, expected_height);

    match &result {
        Ok(_) => clear_wgc_access_denied(),
        Err(error) if is_wgc_access_denied_message(&error.to_string()) => {
            mark_wgc_access_denied(error);
        }
        Err(_) => {}
    }

    result
}

fn capture_monitor_wgc_inner(
    screen_x: i32,
    screen_y: i32,
    expected_width: u32,
    expected_height: u32,
) -> HuGeResult<WgcCaptureResult> {
    let total_start = std::time::Instant::now();
    let mut t = std::time::Instant::now();

    // 1. 获取 HMONITOR（< 1ms）
    let center_x = screen_x + (expected_width as i32) / 2;
    let center_y = screen_y + (expected_height as i32) / 2;
    let hmonitor = get_hmonitor_from_position(center_x, center_y)?;
    let t_hmonitor = t.elapsed();
    t = std::time::Instant::now();

    // 2. 获取/创建 D3D 设备（缓存后 < 1ms）
    let (d3d_device, winrt_device, context) = get_or_create_devices()?;
    let t_device = t.elapsed();
    t = std::time::Instant::now();

    // 3. 创建 CaptureItem + FramePool（~5ms）
    let item = create_capture_item_for_monitor(hmonitor)?;
    let size = item
        .Size()
        .map_err(|e| HuGeError::CaptureError(format!("获取 CaptureItem 尺寸失败: {:?}", e)))?;

    let frame_pool = Direct3D11CaptureFramePool::CreateFreeThreaded(
        &winrt_device,
        DirectXPixelFormat::B8G8R8A8UIntNormalized,
        1,
        SizeInt32 { Width: size.Width, Height: size.Height },
    )
    .map_err(|e| HuGeError::CaptureError(format!("创建 FramePool 失败: {:?}", e)))?;

    let t_setup = t.elapsed();
    t = std::time::Instant::now();

    // RAII guard: 确保 frame_pool 一创建就在任何退出路径（包括 CreateCaptureSession 失败）被关闭。
    struct WgcSessionGuard {
        session: Option<GraphicsCaptureSession>,
        frame_pool: Option<Direct3D11CaptureFramePool>,
        frame_arrived_token: Option<EventRegistrationToken>,
    }
    impl Drop for WgcSessionGuard {
        fn drop(&mut self) {
            if let (Some(pool), Some(token)) =
                (self.frame_pool.as_ref(), self.frame_arrived_token.take())
            {
                let _ = pool.RemoveFrameArrived(token);
            }
            if let Some(ref session) = self.session {
                let _ = session.Close();
            }
            if let Some(ref pool) = self.frame_pool {
                let _ = pool.Close();
            }
        }
    }
    let mut guard = WgcSessionGuard {
        session: None,
        frame_pool: Some(frame_pool.clone()),
        frame_arrived_token: None,
    };

    // 4. 同步捕获一帧
    let (tx, rx) = mpsc::channel();
    let session = frame_pool
        .CreateCaptureSession(&item)
        .map_err(|e| HuGeError::CaptureError(format!("创建 CaptureSession 失败: {:?}", e)))?;
    guard.session = Some(session.clone());

    let frame_arrived_token = frame_pool
        .FrameArrived(&TypedEventHandler::new(
            move |pool: &Option<Direct3D11CaptureFramePool>, _| {
                if let Some(pool) = pool {
                    if let Ok(frame) = pool.TryGetNextFrame() {
                        let _ = tx.send(frame);
                    }
                }
                Ok(())
            },
        ))
        .map_err(|e| HuGeError::CaptureError(format!("注册回调失败: {:?}", e)))?;
    guard.frame_arrived_token = Some(frame_arrived_token);

    session
        .StartCapture()
        .map_err(|e| HuGeError::CaptureError(format!("StartCapture 失败: {:?}", e)))?;

    let frame = rx
        .recv_timeout(Duration::from_secs(3))
        .map_err(|e| HuGeError::CaptureError(format!("WGC 捕获超时: {:?}", e)))?;
    struct WgcFrameGuard {
        frame: Direct3D11CaptureFrame,
    }
    impl Drop for WgcFrameGuard {
        fn drop(&mut self) {
            let _ = self.frame.Close();
        }
    }
    let frame_guard = WgcFrameGuard { frame };

    let t_capture = t.elapsed();
    t = std::time::Instant::now();

    // 5. 提取像素数据（GPU → CPU）
    let surface = frame_guard
        .frame
        .Surface()
        .map_err(|e| HuGeError::CaptureError(format!("获取 Surface 失败: {:?}", e)))?;

    let access: windows::Win32::System::WinRT::Direct3D11::IDirect3DDxgiInterfaceAccess =
        surface.cast().map_err(|e| HuGeError::CaptureError(format!("转换接口失败: {:?}", e)))?;

    let source_texture: ID3D11Texture2D = unsafe {
        access
            .GetInterface()
            .map_err(|e| HuGeError::CaptureError(format!("获取 D3D11 纹理失败: {:?}", e)))?
    };

    let mut tex_desc = D3D11_TEXTURE2D_DESC::default();
    unsafe { source_texture.GetDesc(&mut tex_desc) };
    let width = tex_desc.Width;
    let height = tex_desc.Height;

    // 创建 Staging 纹理
    let staging_desc = D3D11_TEXTURE2D_DESC {
        Width: width,
        Height: height,
        MipLevels: 1,
        ArraySize: 1,
        Format: tex_desc.Format,
        SampleDesc: windows::Win32::Graphics::Dxgi::Common::DXGI_SAMPLE_DESC {
            Count: 1,
            Quality: 0,
        },
        Usage: D3D11_USAGE_STAGING,
        CPUAccessFlags: D3D11_CPU_ACCESS_READ.0 as u32,
        ..Default::default()
    };

    let staging_texture: ID3D11Texture2D = unsafe {
        let mut tex = None;
        d3d_device
            .CreateTexture2D(&staging_desc, None, Some(&mut tex))
            .map_err(|e| HuGeError::CaptureError(format!("创建 Staging 纹理失败: {:?}", e)))?;
        tex.unwrap()
    };

    unsafe {
        context.CopyResource(&staging_texture, &source_texture);
    }

    // Map 并读取像素数据
    let data = unsafe {
        let mut mapped = windows::Win32::Graphics::Direct3D11::D3D11_MAPPED_SUBRESOURCE::default();
        context
            .Map(&staging_texture, 0, D3D11_MAP_READ, 0, Some(&mut mapped))
            .map_err(|e| HuGeError::CaptureError(format!("Map 纹理失败: {:?}", e)))?;

        let row_pitch = mapped.RowPitch as usize;
        let pixel_width = (width * 4) as usize;
        let mut pixels = Vec::with_capacity((width * height * 4) as usize);

        let src = mapped.pData as *const u8;
        for row in 0..height as usize {
            let row_start = src.add(row * row_pitch);
            pixels.extend_from_slice(std::slice::from_raw_parts(row_start, pixel_width));
        }

        context.Unmap(&staging_texture, 0);
        pixels
    };

    let t_copy = t.elapsed();
    let t_total = total_start.elapsed();

    if is_probably_black_frame_bgra(&data, width, height) {
        warn!(
            "WGC: 捕获到近乎全黑帧 {}x{}，判定为无效截图并触发回退，总耗时: {:?}",
            width, height, t_total
        );
        return Err(HuGeError::CaptureError(
            "WGC 捕获到近乎全黑帧，可能是 WDA/显卡驱动返回的无效画面".to_string(),
        ));
    }

    info!(
        "WGC: 截图完成 {}x{}, 总耗时: {:?} (HMONITOR: {:?}, 设备: {:?}, 初始化: {:?}, 捕获: {:?}, 拷贝: {:?})",
        width, height, t_total, t_hmonitor, t_device, t_setup, t_capture, t_copy
    );

    Ok(WgcCaptureResult { data, width, height })
}

/// 检测系统是否支持 WGC
pub fn is_wgc_supported() -> bool {
    !should_skip_wgc_for_current_windows_version()
        && windows::core::factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>().is_ok()
}

/// 预热 D3D11 设备（应用启动时后台调用）
///
/// 首次创建 D3D11 设备约需 1.3 秒，后续调用因缓存而几乎为零。
/// 在应用启动时预热可以消除首次截图的延迟。
///
/// 此函数是幂等的，多次调用不会重复创建设备。
pub fn pre_warm_d3d_devices() {
    let start = std::time::Instant::now();
    if should_skip_wgc_for_current_windows_version() {
        info!("WGC: 当前 Windows 版本已跳过 WGC，取消 D3D11 预热");
        return;
    }

    if should_skip_wgc_due_to_access_denied(Instant::now(), wgc_access_denied_disabled_until()) {
        info!("WGC: access denied 冷却期内，取消 D3D11 预热");
        return;
    }

    info!("WGC: 开始预热 D3D11 设备...");

    match get_or_create_devices() {
        Ok(_) => {
            info!("WGC: D3D11 设备预热完成，耗时: {:?}", start.elapsed());
        }
        Err(e) => {
            tracing::warn!("WGC: D3D11 设备预热失败（首次截图时会重试）: {}", e);
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::{Duration, Instant};

    use serial_test::serial;

    use super::{
        clear_wgc_access_denied, is_wgc_access_denied_message,
        mark_wgc_access_denied, should_skip_wgc_due_to_access_denied,
        should_skip_wgc_for_windows_version, wgc_access_denied_disabled_until,
    };
    use crate::screenshot::frame_validity::is_probably_black_frame_bgra;
    use crate::error::HuGeError;

    #[test]
    fn detects_all_black_frame() {
        let data = vec![0u8; 32 * 24 * 4];

        assert!(is_probably_black_frame_bgra(&data, 32, 24));
    }

    #[test]
    fn accepts_frame_with_visible_content() {
        let mut data = vec![0u8; 100 * 100 * 4];
        for pixel_index in 0..20 {
            let offset = pixel_index * 4;
            data[offset] = 255;
            data[offset + 1] = 255;
            data[offset + 2] = 255;
            data[offset + 3] = 255;
        }

        assert!(!is_probably_black_frame_bgra(&data, 100, 100));
    }

    #[test]
    fn ignores_short_buffers() {
        assert!(!is_probably_black_frame_bgra(&[0, 0, 0], 10, 10));
    }

    #[test]
    fn detects_wgc_access_denied_errors() {
        assert!(is_wgc_access_denied_message(
            r#"创建 CaptureSession 失败: Error { code: HRESULT(0x80070005), message: "拒绝访问。" }"#
        ));
        assert!(is_wgc_access_denied_message("E_ACCESSDENIED while creating capture session"));
        assert!(is_wgc_access_denied_message("Access is denied"));
        assert!(is_wgc_access_denied_message("HRESULT(0X80070005)"));
        assert!(!is_wgc_access_denied_message("WGC 捕获超时: timed out waiting for frame"));
    }

    #[test]
    fn skips_wgc_only_during_access_denied_cooldown() {
        let now = Instant::now();
        let disabled_until = now + Duration::from_secs(60);

        assert!(should_skip_wgc_due_to_access_denied(now, Some(disabled_until)));
        assert!(!should_skip_wgc_due_to_access_denied(
            now + Duration::from_secs(61),
            Some(disabled_until)
        ));
        assert!(!should_skip_wgc_due_to_access_denied(now, None));
    }

    #[test]
    #[serial]
    fn access_denied_error_marks_and_clear_resets_global_cooldown() {
        clear_wgc_access_denied();
        assert!(wgc_access_denied_disabled_until().is_none());

        mark_wgc_access_denied(&HuGeError::CaptureError(
            "创建 CaptureSession 失败: HRESULT(0x80070005)".to_string(),
        ));

        let disabled_until =
            wgc_access_denied_disabled_until().expect("access denied should set cooldown");
        assert!(should_skip_wgc_due_to_access_denied(Instant::now(), Some(disabled_until)));

        clear_wgc_access_denied();
        assert!(wgc_access_denied_disabled_until().is_none());
    }

    #[test]
    fn skips_old_windows_10_builds_before_attempting_wgc() {
        assert!(should_skip_wgc_for_windows_version(10, 0, 18363));
        assert!(should_skip_wgc_for_windows_version(10, 0, 18362));
        assert!(!should_skip_wgc_for_windows_version(10, 0, 19041));
        assert!(!should_skip_wgc_for_windows_version(10, 0, 22631));
        assert!(!should_skip_wgc_for_windows_version(11, 0, 22000));
    }
}
