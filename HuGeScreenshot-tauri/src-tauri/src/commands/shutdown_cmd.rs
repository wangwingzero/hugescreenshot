//! 定时关机命令模块
//!
//! 提供 Windows 系统定时关机功能：
//! - 设置定时关机
//! - 取消定时关机
//!
//! 使用 Windows shutdown 命令实现

use tracing::{error, info};

/// 设置定时关机
///
/// # Arguments
/// * `seconds` - 关机倒计时秒数
///
/// # Returns
/// * `Ok(())` - 设置成功
/// * `Err(String)` - 设置失败的错误信息
#[tauri::command]
pub async fn schedule_shutdown(seconds: u32) -> Result<(), String> {
    info!("设置定时关机: {} 秒后", seconds);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use std::process::Command;

        // 先取消可能存在的定时关机
        let _ = Command::new("shutdown")
            .args(["/a"])
            .creation_flags(0x08000000) // CREATE_NO_WINDOW
            .output();

        // 设置新的定时关机
        let output = Command::new("shutdown")
            .args(["/s", "/t", &seconds.to_string()])
            .creation_flags(0x08000000) // CREATE_NO_WINDOW
            .output()
            .map_err(|e| format!("执行 shutdown 命令失败: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            error!("设置定时关机失败: {}", stderr);
            return Err(format!("设置定时关机失败: {}", stderr));
        }

        info!("定时关机已设置: {} 秒后关机", seconds);
        Ok(())
    }

    #[cfg(not(windows))]
    {
        Err("定时关机功能仅支持 Windows 系统".to_string())
    }
}

/// 取消定时关机
///
/// # Returns
/// * `Ok(())` - 取消成功
/// * `Err(String)` - 取消失败的错误信息
#[tauri::command]
pub async fn cancel_scheduled_shutdown() -> Result<(), String> {
    info!("取消定时关机");

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use std::process::Command;

        let _output = Command::new("shutdown")
            .args(["/a"])
            .creation_flags(0x08000000) // CREATE_NO_WINDOW
            .output()
            .map_err(|e| format!("执行 shutdown 命令失败: {}", e))?;

        // 即使没有定时关机任务，/a 命令也可能返回非零状态码
        // 所以这里不检查 status.success()

        info!("定时关机已取消");
        Ok(())
    }

    #[cfg(not(windows))]
    {
        Err("定时关机功能仅支持 Windows 系统".to_string())
    }
}
