//! HTML 文件转换模块
//!
//! 使用 htmd 将 HTML 转换为 Markdown

use std::path::Path;
use tracing::debug;

use super::ConverterError;

/// 将 HTML 文件转换为 Markdown
pub fn convert_to_markdown<P: AsRef<Path>>(path: P) -> Result<String, ConverterError> {
    let path = path.as_ref();
    debug!("开始转换 HTML: {:?}", path);

    // 读取 HTML 文件
    let html = std::fs::read_to_string(path)?;

    // 使用 htmd 转换
    let markdown = htmd::convert(&html).map_err(|e| ConverterError::HtmlError(e.to_string()))?;

    // 清理 Markdown
    let cleaned = clean_markdown(&markdown);

    debug!("HTML 转换完成，{} 字符", cleaned.len());
    Ok(cleaned)
}

/// 从 HTML 字符串转换为 Markdown
pub fn html_string_to_markdown(html: &str) -> Result<String, ConverterError> {
    let markdown = htmd::convert(html).map_err(|e| ConverterError::HtmlError(e.to_string()))?;

    Ok(clean_markdown(&markdown))
}

/// 从 HTML 字符串提取标题
pub fn extract_title_from_string(html: &str) -> Option<String> {
    // 查找 <title> 标签
    if let Some(start) = html.find("<title>") {
        if let Some(end) = html[start..].find("</title>") {
            let title = &html[start + 7..start + end];
            let title = title.trim();
            if !title.is_empty() {
                return Some(title.to_string());
            }
        }
    }

    // 尝试查找 <h1> 标签
    if let Some(start) = html.find("<h1") {
        if let Some(tag_end) = html[start..].find('>') {
            let content_start = start + tag_end + 1;
            if let Some(end) = html[content_start..].find("</h1>") {
                let title = &html[content_start..content_start + end];
                let title = strip_html_tags(title);
                let title = title.trim().to_string();
                if !title.is_empty() {
                    return Some(title);
                }
            }
        }
    }

    None
}

/// 从 HTML 文件提取标题
pub fn extract_title<P: AsRef<Path>>(path: P) -> Result<String, ConverterError> {
    let html = std::fs::read_to_string(path.as_ref())?;

    // 简单的标题提取（查找 <title> 标签）
    if let Some(start) = html.find("<title>") {
        if let Some(end) = html[start..].find("</title>") {
            let title = &html[start + 7..start + end];
            let title = title.trim();
            if !title.is_empty() {
                return Ok(title.to_string());
            }
        }
    }

    // 尝试查找 <h1> 标签
    if let Some(start) = html.find("<h1") {
        if let Some(tag_end) = html[start..].find('>') {
            let content_start = start + tag_end + 1;
            if let Some(end) = html[content_start..].find("</h1>") {
                let title = &html[content_start..content_start + end];
                // 移除内部 HTML 标签
                let title = strip_html_tags(title);
                let title = title.trim();
                if !title.is_empty() {
                    return Ok(title.to_string());
                }
            }
        }
    }

    Err(ConverterError::HtmlError("无法提取标题".to_string()))
}

/// 移除 HTML 标签
fn strip_html_tags(html: &str) -> String {
    let mut result = String::with_capacity(html.len());
    let mut in_tag = false;

    for ch in html.chars() {
        match ch {
            '<' => in_tag = true,
            '>' => in_tag = false,
            _ if !in_tag => result.push(ch),
            _ => {}
        }
    }

    result
}

/// 清理 Markdown 文本
fn clean_markdown(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    let mut prev_was_empty = false;

    for line in text.lines() {
        let trimmed = line.trim_end();
        let is_empty = trimmed.is_empty();

        if is_empty {
            if !prev_was_empty {
                result.push('\n');
                prev_was_empty = true;
            }
        } else {
            result.push_str(trimmed);
            result.push('\n');
            prev_was_empty = false;
        }
    }

    result.trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_html_string_to_markdown() {
        let html = "<h1>Title</h1><p>Hello <strong>World</strong></p>";
        let md = html_string_to_markdown(html).unwrap();
        assert!(md.contains("Title"));
        assert!(md.contains("Hello"));
        assert!(md.contains("**World**"));
    }

    #[test]
    fn test_strip_html_tags() {
        assert_eq!(strip_html_tags("<p>Hello</p>"), "Hello");
        assert_eq!(strip_html_tags("<a href='#'>Link</a>"), "Link");
        assert_eq!(strip_html_tags("No tags"), "No tags");
    }

    #[test]
    fn test_clean_markdown() {
        let input = "Line 1\n\n\n\nLine 2\n\n";
        let output = clean_markdown(input);
        assert_eq!(output, "Line 1\n\nLine 2");
    }
}
