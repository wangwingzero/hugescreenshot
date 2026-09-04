//! 文本文件处理模块
//!
//! 处理 TXT、MD 等纯文本文件

use std::path::Path;
use tracing::debug;

use super::ConverterError;

/// 读取文本文件
pub fn read_text_file<P: AsRef<Path>>(path: P) -> Result<String, ConverterError> {
    let path = path.as_ref();
    debug!("读取文本文件: {:?}", path);

    // 读取文件内容
    let bytes = std::fs::read(path)?;

    // 尝试 UTF-8 解码
    if let Ok(text) = String::from_utf8(bytes.clone()) {
        debug!("UTF-8 解码成功，{} 字符", text.len());
        return Ok(text);
    }

    // 回退：尝试有损 UTF-8 解码
    let text = String::from_utf8_lossy(&bytes).to_string();
    debug!("有损 UTF-8 解码，{} 字符", text.len());
    Ok(text)
}

/// 从文本中提取标题
pub fn extract_title(text: &str) -> Option<String> {
    // 对于 Markdown 文件，查找第一个标题
    for line in text.lines() {
        let trimmed = line.trim();

        // Markdown 标题
        if let Some(stripped) = trimmed.strip_prefix("# ") {
            return Some(stripped.trim().to_string());
        }
        if let Some(stripped) = trimmed.strip_prefix("## ") {
            return Some(stripped.trim().to_string());
        }
    }

    // 对于普通文本，使用第一行非空内容
    for line in text.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && trimmed.len() < 200 {
            // 排除看起来像代码或配置的行
            if !trimmed.starts_with('{')
                && !trimmed.starts_with('[')
                && !trimmed.starts_with('<')
                && !trimmed.starts_with('#') // 注释
                && !trimmed.starts_with("//")
                && !trimmed.starts_with("/*")
                && !trimmed.starts_with('\"')
                && !trimmed.contains("\":")
                && !trimmed.ends_with(',')
                && trimmed.chars().any(|c| c.is_alphanumeric() || ('\u{4e00}'..='\u{9fff}').contains(&c))
            {
                return Some(trimmed.to_string());
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_read_utf8_file() {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all("Hello, 世界!".as_bytes()).unwrap();

        let content = read_text_file(file.path()).unwrap();
        assert_eq!(content, "Hello, 世界!");
    }

    #[test]
    fn test_extract_title_markdown() {
        assert_eq!(extract_title("# My Title\n\nContent"), Some("My Title".to_string()));
        assert_eq!(extract_title("## Subtitle\n\nContent"), Some("Subtitle".to_string()));
    }

    #[test]
    fn test_extract_title_plain_text() {
        assert_eq!(
            extract_title("Document Title\n\nParagraph content"),
            Some("Document Title".to_string())
        );
    }

    #[test]
    fn test_extract_title_skip_code() {
        assert_eq!(
            extract_title("{\n  \"key\": \"value\"\n}"),
            None // JSON 不应该被当作标题
        );
    }
}
