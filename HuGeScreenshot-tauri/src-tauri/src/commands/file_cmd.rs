//! 文件操作命令模块
//!
//! 提供文件读写功能，绕过前端 fs 插件的权限限制。

use std::path::Path;
use tokio::fs;
use tracing::{debug, error, info};

/// 保存文本文件到指定路径
///
/// # Arguments
/// * `path` - 文件保存路径
/// * `content` - 文件内容
///
/// # Returns
/// * `Ok(())` - 保存成功
/// * `Err(String)` - 保存失败，返回错误信息
#[tauri::command]
pub async fn save_text_file(path: String, content: String) -> Result<(), String> {
    info!("保存文本文件: {}", path);

    let file_path = Path::new(&path);

    // 确保父目录存在
    if let Some(parent) = file_path.parent() {
        if !parent.exists() {
            debug!("创建父目录: {:?}", parent);
            fs::create_dir_all(parent).await.map_err(|e| format!("创建目录失败: {}", e))?;
        }
    }

    // 写入文件
    fs::write(&path, content.as_bytes()).await.map_err(|e| {
        error!("写入文件失败: {} - {}", path, e);
        format!("写入文件失败: {}", e)
    })?;

    info!("文件保存成功: {}", path);
    Ok(())
}

/// 读取文本文件
///
/// # Arguments
/// * `path` - 文件路径
///
/// # Returns
/// * `Ok(String)` - 文件内容
/// * `Err(String)` - 读取失败，返回错误信息
#[tauri::command]
pub async fn read_text_file(path: String) -> Result<String, String> {
    debug!("读取文本文件: {}", path);

    let content = fs::read_to_string(&path).await.map_err(|e| {
        error!("读取文件失败: {} - {}", path, e);
        format!("读取文件失败: {}", e)
    })?;

    Ok(content)
}

/// 检查文件是否存在
#[tauri::command]
pub async fn file_exists(path: String) -> bool {
    Path::new(&path).exists()
}
