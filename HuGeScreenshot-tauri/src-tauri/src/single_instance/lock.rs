//! 单实例锁实现
//!
//! 使用 Windows CreateMutexW API 创建全局互斥锁，
//! 防止应用重复启动并激活已有窗口。

use std::ffi::OsStr;
use std::iter::once;
use std::os::windows::ffi::OsStrExt;

use windows::core::PCWSTR;
use windows::Win32::Foundation::{
    CloseHandle, GetLastError, BOOL, ERROR_ALREADY_EXISTS, HANDLE, HWND, LPARAM,
};
use windows::Win32::System::Threading::CreateMutexW;
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, FindWindowW, GetWindowTextW, IsIconic, SetForegroundWindow, ShowWindow,
    SW_RESTORE, SW_SHOW,
};

/// 应用唯一标识符（全局 Mutex 名称）
const MUTEX_NAME: &str = "Global\\HuGeScreenshot_SingleInstance_Mutex";

/// 应用窗口标题（用于查找已有窗口）
const WINDOW_TITLE: &str = "虎哥截图";

/// WebView2 子进程不应该参与主程序单实例锁竞争。
pub fn is_webview_child_process() -> bool {
    is_webview_child_process_args(std::env::args())
}

pub fn is_webview_child_process_args<I, S>(args: I) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    args.into_iter().any(|arg| {
        let arg = arg.as_ref();
        arg.starts_with("--type=") || arg.starts_with("--embedded-browser-")
    })
}

pub fn should_exit_for_single_instance_error(error: &SingleInstanceError) -> bool {
    matches!(error, SingleInstanceError::AlreadyRunning)
}

/// 单实例锁错误
#[derive(Debug, thiserror::Error)]
pub enum SingleInstanceError {
    /// 应用已在运行
    #[error("应用已在运行")]
    AlreadyRunning,

    /// Windows API 错误
    #[error("系统错误: {0}")]
    WindowsError(String),
}

/// 单实例锁
///
/// 在应用启动时创建，持有 Mutex 句柄直到应用退出。
/// 应用退出时自动释放 Mutex。
pub struct SingleInstanceLock {
    handle: HANDLE,
}

impl SingleInstanceLock {
    /// 尝试获取单实例锁
    ///
    /// # Returns
    /// - `Ok(Self)` - 成功获取锁，这是第一个实例
    /// - `Err(SingleInstanceError::AlreadyRunning)` - 已有实例运行
    ///
    /// # Example
    /// ```ignore
    /// use hugescreenshot_tauri_lib::single_instance::{SingleInstanceLock, SingleInstanceError};
    ///
    /// fn main() {
    ///     let _lock = match SingleInstanceLock::acquire() {
    ///         Ok(lock) => lock,
    ///         Err(SingleInstanceError::AlreadyRunning) => {
    ///             println!("应用已在运行");
    ///             return;
    ///         }
    ///         Err(e) => {
    ///             eprintln!("获取锁失败: {}", e);
    ///             return;
    ///         }
    ///     };
    ///
    ///     // 正常运行应用...
    /// }
    /// ```
    pub fn acquire() -> Result<Self, SingleInstanceError> {
        let mutex_name = to_wide_string(MUTEX_NAME);

        unsafe {
            let handle = CreateMutexW(None, true, PCWSTR(mutex_name.as_ptr()))
                .map_err(|e| SingleInstanceError::WindowsError(e.to_string()))?;

            if GetLastError() == ERROR_ALREADY_EXISTS {
                // 关闭我们刚创建的句柄
                let _ = CloseHandle(handle);

                // 激活已有窗口
                Self::activate_existing_window();

                return Err(SingleInstanceError::AlreadyRunning);
            }

            Ok(Self { handle })
        }
    }

    /// 激活已有窗口
    ///
    /// 通过窗口标题查找已有窗口并将其置于前台
    fn activate_existing_window() {
        let window_title = to_wide_string(WINDOW_TITLE);

        unsafe {
            // 方法 1：通过窗口标题查找
            if let Ok(hwnd) = FindWindowW(None, PCWSTR(window_title.as_ptr())) {
                if !hwnd.is_invalid() {
                    Self::bring_window_to_front(hwnd);
                    return;
                }
            }

            // 方法 2：枚举所有窗口查找包含标题的窗口
            if let Some(hwnd) = Self::find_window_by_partial_title(WINDOW_TITLE) {
                Self::bring_window_to_front(hwnd);
            }
        }
    }

    /// 将窗口置于前台
    fn bring_window_to_front(hwnd: HWND) {
        unsafe {
            // 如果窗口最小化，先恢复
            if IsIconic(hwnd).as_bool() {
                let _ = ShowWindow(hwnd, SW_RESTORE);
            } else {
                // 主窗口关闭时会隐藏到托盘，重复启动时必须重新显示。
                let _ = ShowWindow(hwnd, SW_SHOW);
            }

            // 将窗口置于前台
            let _ = SetForegroundWindow(hwnd);
        }
    }

    /// 通过部分标题查找窗口
    fn find_window_by_partial_title(partial_title: &str) -> Option<HWND> {
        use std::sync::atomic::{AtomicIsize, Ordering};

        // 用于在回调中存储找到的窗口句柄（原子操作安全跨线程）
        static FOUND_HWND: AtomicIsize = AtomicIsize::new(0);
        FOUND_HWND.store(0, Ordering::SeqCst);

        let search_title = partial_title.to_string();

        unsafe extern "system" fn enum_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
            let search_ptr = lparam.0 as *const String;
            let search_title = &*search_ptr;

            let mut title_buffer = [0u16; 256];
            let len = GetWindowTextW(hwnd, &mut title_buffer);

            if len > 0 {
                let title = String::from_utf16_lossy(&title_buffer[..len as usize]);
                if title.contains(search_title.as_str()) {
                    FOUND_HWND.store(hwnd.0 as isize, Ordering::SeqCst);
                    return BOOL(0); // 停止枚举
                }
            }

            BOOL(1) // 继续枚举
        }

        unsafe {
            let _ =
                EnumWindows(Some(enum_callback), LPARAM(&search_title as *const String as isize));
        }

        let hwnd_value = FOUND_HWND.load(Ordering::SeqCst);
        if hwnd_value != 0 {
            Some(HWND(hwnd_value as *mut std::ffi::c_void))
        } else {
            None
        }
    }

    /// 等待另一个实例退出
    ///
    /// 用于更新场景，等待旧版本退出后再启动新版本
    ///
    /// # Arguments
    /// * `timeout_secs` - 超时时间（秒）
    ///
    /// # Returns
    /// * `true` - 旧实例已退出
    /// * `false` - 超时
    pub fn wait_for_exit(timeout_secs: u64) -> bool {
        use std::thread;
        use std::time::{Duration, Instant};

        let start = Instant::now();
        let timeout = Duration::from_secs(timeout_secs);

        while start.elapsed() < timeout {
            match Self::acquire() {
                Ok(lock) => {
                    // 成功获取锁，说明旧实例已退出
                    // 立即释放锁
                    drop(lock);
                    return true;
                }
                Err(SingleInstanceError::AlreadyRunning) => {
                    // 旧实例仍在运行，等待一段时间后重试
                    thread::sleep(Duration::from_millis(500));
                }
                Err(_) => {
                    // 其他错误，返回 false
                    return false;
                }
            }
        }

        false
    }
}

impl Drop for SingleInstanceLock {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}

/// 将 &str 转换为 Windows 宽字符串
fn to_wide_string(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(once(0)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serial_test::serial;

    /// 测试专用的 Mutex 名称，避免与生产环境冲突
    const TEST_MUTEX_NAME: &str = "Global\\HuGeScreenshot_SingleInstance_TEST_Mutex";

    /// 测试用的单实例锁
    fn acquire_test_lock() -> Result<SingleInstanceLock, SingleInstanceError> {
        let mutex_name = to_wide_string(TEST_MUTEX_NAME);

        unsafe {
            let handle = CreateMutexW(None, false, PCWSTR(mutex_name.as_ptr()));

            match handle {
                Ok(h) if !h.is_invalid() => {
                    let last_error = GetLastError();
                    if last_error == ERROR_ALREADY_EXISTS {
                        let _ = CloseHandle(h);
                        Err(SingleInstanceError::AlreadyRunning)
                    } else {
                        Ok(SingleInstanceLock { handle: h })
                    }
                }
                Ok(_) => Err(SingleInstanceError::WindowsError(
                    "CreateMutex returned invalid handle".to_string(),
                )),
                Err(e) => {
                    Err(SingleInstanceError::WindowsError(format!("CreateMutex failed: {}", e)))
                }
            }
        }
    }

    #[test]
    #[serial]
    fn test_acquire_single_instance() {
        // 第一次获取应该成功（使用测试专用 Mutex）
        let lock1 = acquire_test_lock();
        assert!(lock1.is_ok(), "第一次获取锁应该成功");

        // 第二次获取应该失败（已有实例）
        let lock2 = acquire_test_lock();
        assert!(
            matches!(lock2, Err(SingleInstanceError::AlreadyRunning)),
            "第二次获取锁应该返回 AlreadyRunning"
        );

        // 释放第一个锁
        drop(lock1);

        // 现在应该可以再次获取
        let lock3 = acquire_test_lock();
        assert!(lock3.is_ok(), "释放后应该可以再次获取锁");
    }

    #[test]
    fn test_to_wide_string() {
        let wide = to_wide_string("Hello");
        // "Hello" + null terminator = 6 个 u16
        assert_eq!(wide.len(), 6);
        assert_eq!(wide.last(), Some(&0));
    }

    #[test]
    fn test_webview_child_process_args_skip_single_instance_lock() {
        assert!(is_webview_child_process_args(["app.exe", "--type=renderer"]));
        assert!(is_webview_child_process_args(["app.exe", "--type=utility"]));
        assert!(!is_webview_child_process_args(["app.exe", "--from-shortcut"]));
    }

    #[test]
    fn test_only_already_running_requests_process_exit() {
        assert!(should_exit_for_single_instance_error(&SingleInstanceError::AlreadyRunning));
        assert!(!should_exit_for_single_instance_error(&SingleInstanceError::WindowsError(
            "CreateMutex failed".to_string(),
        )));
    }
}
