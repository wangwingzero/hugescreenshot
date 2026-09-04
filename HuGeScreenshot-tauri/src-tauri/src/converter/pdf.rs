//! PDF 文件解析模块
//!
//! 使用 pdfium-render（Google PDFium 引擎）提取 PDF 文本内容。
//! 相比 pdf-extract，pdfium-render 对 CJK 字体（CID/CMap）的支持更完善，
//! 不会因为不支持的字体编码而 panic。

use pdfium_render::prelude::*;
use std::path::Path;
use tracing::{debug, warn};

use super::ConverterError;

/// 从 PDF 文件提取文本
///
/// 使用 pdfium-render 逐页提取 PDF 原生文本。
/// 对于文本型 PDF，这比 OCR 快得多且更准确。
pub fn extract_text<P: AsRef<Path>>(path: P) -> Result<String, ConverterError> {
    let path = path.as_ref();
    debug!("开始解析 PDF: {:?}", path);

    let pdfium = create_pdfium()
        .map_err(|e| ConverterError::PdfError(format!("PDFium 初始化失败: {}", e)))?;

    // 打开 PDF 文件
    let document = pdfium
        .load_pdf_from_file(path.to_str().unwrap_or(""), None)
        .map_err(|e| ConverterError::PdfError(format!("打开 PDF 失败: {:?}", e)))?;

    let page_count = document.pages().len();
    let mut all_texts: Vec<String> = Vec::with_capacity(page_count as usize);

    // 逐页提取文本
    for i in 0..page_count {
        match document.pages().get(i) {
            Ok(page) => {
                let page_text = page.text().map(|t| t.all()).unwrap_or_default();

                if !page_text.trim().is_empty() {
                    all_texts.push(page_text);
                }
            }
            Err(e) => {
                warn!("PDF 第 {} 页文本提取失败: {:?}", i + 1, e);
            }
        }
    }

    let full_text = all_texts.join("\n");

    // 清理文本
    let cleaned = clean_pdf_text(&full_text);

    debug!("PDF 解析完成，提取 {} 字符", cleaned.len());
    Ok(cleaned)
}

fn create_pdfium() -> Result<Pdfium, String> {
    let mut search_paths = Vec::new();

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            search_paths.push(exe_dir.join("pdfium").join("pdfium.dll"));
            search_paths.push(exe_dir.join("pdfium.dll"));
        }
    }

    search_paths.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("pdfium").join("pdfium.dll"));

    for path in &search_paths {
        if !path.exists() {
            continue;
        }
        let parent_dir = path.parent().unwrap_or(Path::new("."));
        match Pdfium::bind_to_library(Pdfium::pdfium_platform_library_name_at_path(
            parent_dir.to_str().unwrap_or("."),
        )) {
            Ok(bindings) => return Ok(Pdfium::new(bindings)),
            Err(err) => {
                warn!("从 {:?} 加载 PDFium 失败: {:?}", path, err);
            }
        }
    }

    Pdfium::bind_to_system_library()
        .map(Pdfium::new)
        .map_err(|err| format!("无法加载 pdfium.dll: {:?}", err))
}

/// 清理 PDF 提取的文本
fn clean_pdf_text(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    let mut newline_count = 0u8;
    let mut prev_was_space = false;

    for ch in text.chars() {
        match ch {
            // 合并连续空行，最多保留一个空行（即连续两个 '\n'）
            '\n' => {
                if newline_count < 2 {
                    result.push('\n');
                }
                newline_count = newline_count.saturating_add(1);
                prev_was_space = false;
            }
            // 合并连续空格
            ' ' | '\t' => {
                if !prev_was_space && newline_count == 0 {
                    result.push(' ');
                    prev_was_space = true;
                }
            }
            // 移除控制字符
            c if c.is_control() && c != '\n' => {}
            // 保留其他字符
            c => {
                result.push(c);
                newline_count = 0;
                prev_was_space = false;
            }
        }
    }

    // 移除首尾空白
    result.trim().to_string()
}

/// 从文本中提取标题
pub fn extract_title(text: &str) -> Option<String> {
    // 尝试从第一行提取标题
    let first_line = text.lines().next()?;
    let trimmed = first_line.trim();

    // 如果第一行太短或太长，可能不是标题
    if trimmed.len() < 2 || trimmed.len() > 200 {
        return None;
    }

    // 如果第一行看起来像标题（不以标点结尾）
    if !trimmed.ends_with('.') && !trimmed.ends_with('。') {
        Some(trimmed.to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clean_pdf_text() {
        let input = "Hello  World\n\n\nTest\t\tContent";
        let output = clean_pdf_text(input);
        assert_eq!(output, "Hello World\n\nTest Content");
    }

    #[test]
    fn test_extract_title() {
        assert_eq!(
            extract_title("My Document Title\n\nContent here"),
            Some("My Document Title".to_string())
        );
        assert_eq!(
            extract_title("This is a sentence.\n\nMore content"),
            None // 以句号结尾，不是标题
        );
    }
}
