//! 文件转换 Tauri 命令
//!
//! 提供纯 Rust 实现的文件转 Markdown 功能

use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::converter::web;
use crate::converter::{ConversionResult, ConverterError, FileConverter, FileFormat};

/// 转换结果（前端友好格式）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConversionResponse {
    /// 是否成功
    pub success: bool,
    /// Markdown 内容
    pub markdown: String,
    /// 文档标题
    pub title: Option<String>,
    /// 原始文件路径
    pub source_path: String,
    /// 转换耗时（毫秒）
    pub elapsed_ms: u64,
    /// 原始文件大小（字节）
    pub file_size: u64,
    /// 错误信息（如果失败）
    pub error: Option<String>,
}

impl From<ConversionResult> for ConversionResponse {
    fn from(result: ConversionResult) -> Self {
        Self {
            success: true,
            markdown: result.markdown,
            title: result.title,
            source_path: result.source_path,
            elapsed_ms: result.elapsed_ms,
            file_size: result.file_size,
            error: None,
        }
    }
}

impl From<ConverterError> for ConversionResponse {
    fn from(err: ConverterError) -> Self {
        Self {
            success: false,
            markdown: String::new(),
            title: None,
            source_path: String::new(),
            elapsed_ms: 0,
            file_size: 0,
            error: Some(err.to_string()),
        }
    }
}

/// 文件格式信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileFormatInfo {
    /// 格式名称
    pub format: String,
    /// 是否支持
    pub supported: bool,
    /// 文件扩展名
    pub extension: String,
}

/// 将文件转换为 Markdown
///
/// # Arguments
/// * `file_path` - 文件路径
///
/// # Returns
/// 转换结果，包含 Markdown 内容和元数据
#[tauri::command]
pub async fn convert_file_to_markdown(file_path: String) -> ConversionResponse {
    info!("收到文件转换请求: {}", file_path);

    let converter = FileConverter::new();

    match converter.convert_to_markdown(&file_path).await {
        Ok(result) => {
            info!("文件转换成功: {}, 耗时: {}ms", file_path, result.elapsed_ms);
            result.into()
        }
        Err(e) => {
            error!("文件转换失败: {}, 错误: {}", file_path, e);
            e.into()
        }
    }
}

/// 批量转换文件为 Markdown
///
/// # Arguments
/// * `file_paths` - 文件路径列表
///
/// # Returns
/// 转换结果列表
#[tauri::command]
pub async fn convert_files_to_markdown(file_paths: Vec<String>) -> Vec<ConversionResponse> {
    info!("收到批量文件转换请求: {} 个文件", file_paths.len());

    let converter = FileConverter::new();
    let mut results = Vec::with_capacity(file_paths.len());

    for path in file_paths {
        let response = match converter.convert_to_markdown(&path).await {
            Ok(result) => {
                info!("文件转换成功: {}", path);
                result.into()
            }
            Err(e) => {
                error!("文件转换失败: {}, 错误: {}", path, e);
                ConversionResponse {
                    success: false,
                    markdown: String::new(),
                    title: None,
                    source_path: path,
                    elapsed_ms: 0,
                    file_size: 0,
                    error: Some(e.to_string()),
                }
            }
        };
        results.push(response);
    }

    info!("批量转换完成: {} 个文件", results.len());
    results
}

/// 检测文件格式
///
/// # Arguments
/// * `file_path` - 文件路径
///
/// # Returns
/// 文件格式信息
#[tauri::command]
pub fn detect_file_format(file_path: String) -> FileFormatInfo {
    let path = std::path::Path::new(&file_path);
    let extension = path.extension().and_then(|e| e.to_str()).unwrap_or("").to_string();

    let format = FileFormat::from_extension(&extension);

    FileFormatInfo { format: format!("{:?}", format), supported: format.is_supported(), extension }
}

/// 获取支持的文件格式列表
#[tauri::command]
pub fn get_supported_formats() -> Vec<FileFormatInfo> {
    vec![
        FileFormatInfo { format: "PDF".to_string(), supported: true, extension: "pdf".to_string() },
        FileFormatInfo {
            format: "DOCX".to_string(),
            supported: true,
            extension: "docx".to_string(),
        },
        FileFormatInfo { format: "TXT".to_string(), supported: true, extension: "txt".to_string() },
        FileFormatInfo {
            format: "Markdown".to_string(),
            supported: true,
            extension: "md".to_string(),
        },
        FileFormatInfo {
            format: "HTML".to_string(),
            supported: true,
            extension: "html".to_string(),
        },
        FileFormatInfo { format: "HTM".to_string(), supported: true, extension: "htm".to_string() },
        FileFormatInfo {
            format: "DOC".to_string(),
            supported: false,
            extension: "doc".to_string(),
        },
        FileFormatInfo {
            format: "RTF".to_string(),
            supported: false,
            extension: "rtf".to_string(),
        },
    ]
}

/// 网页转 Markdown 结果（与前端 UrlToMarkdownResult 接口对齐）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UrlToMarkdownResponse {
    pub success: bool,
    pub url: String,
    pub title: String,
    pub markdown: String,
    pub images: Vec<()>,
    pub elapse: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// 将网页 URL 转换为 Markdown（纯 Rust 实现）
#[tauri::command]
pub async fn convert_url_to_markdown(url: String) -> UrlToMarkdownResponse {
    info!("收到网页转 Markdown 请求: {}", url);

    match web::fetch_url_to_markdown(&url).await {
        Ok(result) => {
            info!("网页转换成功: {}, 耗时: {:.2}s", url, result.elapsed_secs);
            UrlToMarkdownResponse {
                success: true,
                url: result.url,
                title: result.title,
                markdown: result.markdown,
                images: vec![],
                elapse: result.elapsed_secs,
                error: None,
            }
        }
        Err(e) => {
            error!("网页转换失败: {}, 错误: {}", url, e);
            UrlToMarkdownResponse {
                success: false,
                url,
                title: String::new(),
                markdown: String::new(),
                images: vec![],
                elapse: 0.0,
                error: Some(e.to_string()),
            }
        }
    }
}

/// 列出目录中的所有 Markdown 文件
///
/// # Arguments
/// * `dir_path` - 目录路径
///
/// # Returns
/// .md 文件的绝对路径列表
#[tauri::command]
pub fn list_md_files(dir_path: String) -> Result<Vec<String>, String> {
    let dir = std::path::Path::new(&dir_path);
    if !dir.is_dir() {
        return Err(format!("不是有效的目录: {}", dir_path));
    }

    let mut md_files: Vec<String> = Vec::new();

    let entries = std::fs::read_dir(dir).map_err(|e| format!("读取目录失败: {}", e))?;

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                if ext.eq_ignore_ascii_case("md") || ext.eq_ignore_ascii_case("markdown") {
                    md_files.push(path.display().to_string());
                }
            }
        }
    }

    md_files.sort();
    info!("目录 {} 中找到 {} 个 Markdown 文件", dir_path, md_files.len());
    Ok(md_files)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_file_format() {
        let info = detect_file_format("test.pdf".to_string());
        assert_eq!(info.format, "Pdf");
        assert!(info.supported);

        let info = detect_file_format("test.docx".to_string());
        assert_eq!(info.format, "Docx");
        assert!(info.supported);

        let info = detect_file_format("test.xyz".to_string());
        assert_eq!(info.format, "Unknown");
        assert!(!info.supported);
    }

    #[test]
    fn test_get_supported_formats() {
        let formats = get_supported_formats();
        assert!(!formats.is_empty());

        let pdf = formats.iter().find(|f| f.extension == "pdf");
        assert!(pdf.is_some());
        assert!(pdf.unwrap().supported);
    }
}
