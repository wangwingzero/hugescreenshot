//! 文件转换模块
//!
//! 提供纯 Rust 实现的文件转 Markdown 功能，支持：
//! - PDF → Markdown
//! - DOCX → Markdown
//! - TXT/MD → Markdown（直接读取）
//! - HTML → Markdown
//!
//! # 性能优势
//!
//! 相比 Python sidecar 方案：
//! - 无进程间通信开销
//! - 无 Python 运行时开销
//! - 原生内存管理，更高效
//!
//! # 使用示例
//!
//! ```rust,ignore
//! use converter::FileConverter;
//!
//! let converter = FileConverter::new();
//! let result = converter.convert_to_markdown("document.pdf").await?;
//! println!("Markdown: {}", result.markdown);
//! ```

mod docx;
pub(crate) mod html;
pub(crate) mod pdf;
mod text;
pub(crate) mod web;

use std::path::Path;
use std::time::Instant;
use thiserror::Error;
use tracing::info;

/// 转换错误类型
#[derive(Error, Debug)]
pub enum ConverterError {
    #[error("文件不存在: {0}")]
    FileNotFound(String),

    #[error("不支持的文件格式: {0}")]
    UnsupportedFormat(String),

    #[error("PDF 解析错误: {0}")]
    PdfError(String),

    #[error("DOCX 解析错误: {0}")]
    DocxError(String),

    #[error("HTML 解析错误: {0}")]
    HtmlError(String),

    #[error("IO 错误: {0}")]
    IoError(#[from] std::io::Error),

    #[error("网络请求错误: {0}")]
    NetworkError(String),

    #[error("编码错误: {0}")]
    EncodingError(String),
}

/// 转换结果
#[derive(Debug, Clone)]
pub struct ConversionResult {
    /// 转换后的 Markdown 内容
    pub markdown: String,
    /// 文档标题（如果能提取）
    pub title: Option<String>,
    /// 原始文件路径
    pub source_path: String,
    /// 转换耗时（毫秒）
    pub elapsed_ms: u64,
    /// 原始文件大小（字节）
    pub file_size: u64,
}

/// 支持的文件格式
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileFormat {
    Pdf,
    Docx,
    Doc,
    Txt,
    Markdown,
    Html,
    Htm,
    Rtf,
    Unknown,
}

impl FileFormat {
    /// 从文件扩展名推断格式
    pub fn from_extension(ext: &str) -> Self {
        match ext.to_lowercase().as_str() {
            "pdf" => Self::Pdf,
            "docx" => Self::Docx,
            "doc" => Self::Doc,
            "txt" => Self::Txt,
            "md" | "markdown" => Self::Markdown,
            "html" => Self::Html,
            "htm" => Self::Htm,
            "rtf" => Self::Rtf,
            _ => Self::Unknown,
        }
    }

    /// 检查格式是否支持
    pub fn is_supported(&self) -> bool {
        matches!(self, Self::Pdf | Self::Docx | Self::Txt | Self::Markdown | Self::Html | Self::Htm)
    }
}

/// 文件转换器
pub struct FileConverter {
    /// 是否提取标题
    extract_title: bool,
}

impl Default for FileConverter {
    fn default() -> Self {
        Self::new()
    }
}

impl FileConverter {
    /// 创建新的转换器
    pub fn new() -> Self {
        Self { extract_title: true }
    }

    /// 设置是否提取标题
    pub fn with_title_extraction(mut self, extract: bool) -> Self {
        self.extract_title = extract;
        self
    }

    /// 转换文件为 Markdown
    pub async fn convert_to_markdown<P: AsRef<Path>>(
        &self,
        path: P,
    ) -> Result<ConversionResult, ConverterError> {
        let path = path.as_ref();
        let start = Instant::now();

        // 检查文件是否存在
        if !path.exists() {
            return Err(ConverterError::FileNotFound(path.display().to_string()));
        }

        // 获取文件大小
        let metadata = std::fs::metadata(path)?;
        let file_size = metadata.len();

        // 推断文件格式
        let format = path
            .extension()
            .and_then(|e| e.to_str())
            .map(FileFormat::from_extension)
            .unwrap_or(FileFormat::Unknown);

        if !format.is_supported() {
            return Err(ConverterError::UnsupportedFormat(format!("{:?}", format)));
        }

        info!("开始转换文件: {:?}, 格式: {:?}, 大小: {} bytes", path, format, file_size);

        // 根据格式选择转换器
        let (markdown, title) = match format {
            FileFormat::Pdf => {
                let content = pdf::extract_text(path)?;
                let title = if self.extract_title { pdf::extract_title(&content) } else { None };
                (content, title)
            }
            FileFormat::Docx => {
                let content = docx::extract_text(path)?;
                let title = if self.extract_title { docx::extract_title(&content) } else { None };
                (content, title)
            }
            FileFormat::Txt | FileFormat::Markdown => {
                let content = text::read_text_file(path)?;
                let title = if self.extract_title { text::extract_title(&content) } else { None };
                (content, title)
            }
            FileFormat::Html | FileFormat::Htm => {
                let content = html::convert_to_markdown(path)?;
                let title = if self.extract_title { html::extract_title(path).ok() } else { None };
                (content, title)
            }
            _ => {
                return Err(ConverterError::UnsupportedFormat(format!("{:?}", format)));
            }
        };

        let elapsed = start.elapsed();
        let elapsed_ms = elapsed.as_millis() as u64;

        info!("文件转换完成: {:?}, 耗时: {}ms, 输出: {} chars", path, elapsed_ms, markdown.len());

        Ok(ConversionResult {
            markdown,
            title,
            source_path: path.display().to_string(),
            elapsed_ms,
            file_size,
        })
    }

    /// 检测文件格式
    pub fn detect_format<P: AsRef<Path>>(&self, path: P) -> FileFormat {
        let path = path.as_ref();

        // 首先尝试通过扩展名
        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            let format = FileFormat::from_extension(ext);
            if format != FileFormat::Unknown {
                return format;
            }
        }

        // 尝试通过文件内容（magic bytes）
        if let Ok(data) = std::fs::read(path) {
            if let Some(kind) = infer::get(&data) {
                match kind.mime_type() {
                    "application/pdf" => return FileFormat::Pdf,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document" => {
                        return FileFormat::Docx
                    }
                    "text/html" => return FileFormat::Html,
                    "text/plain" => return FileFormat::Txt,
                    _ => {}
                }
            }
        }

        FileFormat::Unknown
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_format_from_extension() {
        assert_eq!(FileFormat::from_extension("pdf"), FileFormat::Pdf);
        assert_eq!(FileFormat::from_extension("PDF"), FileFormat::Pdf);
        assert_eq!(FileFormat::from_extension("docx"), FileFormat::Docx);
        assert_eq!(FileFormat::from_extension("txt"), FileFormat::Txt);
        assert_eq!(FileFormat::from_extension("md"), FileFormat::Markdown);
        assert_eq!(FileFormat::from_extension("html"), FileFormat::Html);
        assert_eq!(FileFormat::from_extension("xyz"), FileFormat::Unknown);
    }

    #[test]
    fn test_file_format_is_supported() {
        assert!(FileFormat::Pdf.is_supported());
        assert!(FileFormat::Docx.is_supported());
        assert!(FileFormat::Txt.is_supported());
        assert!(FileFormat::Html.is_supported());
        assert!(!FileFormat::Doc.is_supported()); // .doc 暂不支持
        assert!(!FileFormat::Unknown.is_supported());
    }
}
