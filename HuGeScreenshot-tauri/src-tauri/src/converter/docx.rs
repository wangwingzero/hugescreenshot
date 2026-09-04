//! DOCX 文件解析模块
//!
//! 使用 docx-rs 提取 Word 文档内容并转换为 Markdown

use std::path::Path;
use tracing::debug;

use super::ConverterError;

/// 从 DOCX 文件提取文本并转换为 Markdown
pub fn extract_text<P: AsRef<Path>>(path: P) -> Result<String, ConverterError> {
    let path = path.as_ref();
    debug!("开始解析 DOCX: {:?}", path);

    // 读取 DOCX 文件
    let bytes = std::fs::read(path)?;

    // 使用 docx-rs 解析
    let docx = docx_rs::read_docx(&bytes)
        .map_err(|e| ConverterError::DocxError(format!("解析 DOCX 失败: {:?}", e)))?;

    // 提取文本内容
    let mut markdown = String::new();

    for child in docx.document.children {
        match child {
            docx_rs::DocumentChild::Paragraph(para) => {
                let para_text = extract_paragraph_text(&para);
                if para_text.is_empty() {
                    // 空段落，添加换行
                    if !markdown.is_empty() && !markdown.ends_with("\n\n") {
                        markdown.push('\n');
                    }
                    continue;
                }

                // 检查段落样式（标题等）
                let style = para.property.style.as_ref().map(|s| s.val.as_str());
                let heading_level = detect_heading_level(style);

                if let Some(level) = heading_level {
                    // 标题
                    let prefix = "#".repeat(level);
                    markdown.push_str(&format!("\n{} {}\n\n", prefix, para_text));
                } else {
                    // 普通段落
                    markdown.push_str(&para_text);
                    markdown.push_str("\n\n");
                }
            }
            docx_rs::DocumentChild::Table(table) => {
                // 表格转换为 Markdown 表格
                let table_md = convert_table_to_markdown(&table);
                markdown.push_str(&table_md);
                markdown.push_str("\n\n");
            }
            _ => {}
        }
    }

    // 清理多余空行
    let cleaned = clean_markdown(&markdown);
    debug!("DOCX 解析完成，提取 {} 字符", cleaned.len());
    Ok(cleaned)
}

/// 提取段落文本
fn extract_paragraph_text(para: &docx_rs::Paragraph) -> String {
    let mut text = String::new();

    for child in &para.children {
        if let docx_rs::ParagraphChild::Run(run) = child {
            for run_child in &run.children {
                match run_child {
                    docx_rs::RunChild::Text(t) => {
                        text.push_str(&t.text);
                    }
                    docx_rs::RunChild::Tab(_) => {
                        text.push('\t');
                    }
                    docx_rs::RunChild::Break(_) => {
                        text.push('\n');
                    }
                    _ => {}
                }
            }
        }
    }

    text.trim().to_string()
}

/// 检测标题级别
fn detect_heading_level(style: Option<&str>) -> Option<usize> {
    let style = style?;
    let style_lower = style.to_lowercase();

    // 常见的标题样式名称
    if style_lower.starts_with("heading") || style_lower.starts_with("标题") {
        // 尝试提取数字
        for ch in style.chars() {
            if let Some(digit) = ch.to_digit(10) {
                return Some(digit as usize);
            }
        }
        // 默认为一级标题
        return Some(1);
    }

    // Title 样式
    if style_lower == "title" || style_lower == "标题" {
        return Some(1);
    }

    // Subtitle 样式
    if style_lower == "subtitle" || style_lower == "副标题" {
        return Some(2);
    }

    None
}

/// 将表格转换为 Markdown 格式
fn convert_table_to_markdown(table: &docx_rs::Table) -> String {
    let mut rows: Vec<Vec<String>> = Vec::new();

    for table_child in &table.rows {
        // table.rows 是 Vec<TableChild>，TableChild 只有 TableRow 一个变体
        let docx_rs::TableChild::TableRow(row) = table_child;
        let mut cells: Vec<String> = Vec::new();

        // row.cells 是 Vec<TableRowChild>，TableRowChild 只有 TableCell 一个变体
        for row_child in &row.cells {
            let docx_rs::TableRowChild::TableCell(cell) = row_child;
            let cell_text = extract_table_cell_text(cell);
            cells.push(cell_text);
        }

        if !cells.is_empty() {
            rows.push(cells);
        }
    }

    if rows.is_empty() {
        return String::new();
    }

    // 计算列数
    let col_count = rows.iter().map(|r| r.len()).max().unwrap_or(0);
    if col_count == 0 {
        return String::new();
    }

    let mut md = String::new();

    // 表头
    if let Some(header) = rows.first() {
        md.push('|');
        for cell in header.iter() {
            md.push_str(&format!(" {} |", cell));
        }
        // 补齐缺少的列
        for _ in header.len()..col_count {
            md.push_str(" |");
        }
        md.push('\n');

        // 分隔行
        md.push('|');
        for _ in 0..col_count {
            md.push_str(" --- |");
        }
        md.push('\n');
    }

    // 数据行
    for row in rows.iter().skip(1) {
        md.push('|');
        for cell in row {
            md.push_str(&format!(" {} |", cell));
        }
        // 补齐缺少的列
        for _ in row.len()..col_count {
            md.push_str(" |");
        }
        md.push('\n');
    }

    md
}

/// 提取表格单元格文本
fn extract_table_cell_text(cell: &docx_rs::TableCell) -> String {
    let mut text = String::new();

    for child in &cell.children {
        if let docx_rs::TableCellContent::Paragraph(para) = child {
            let para_text = extract_paragraph_text(para);
            if !para_text.is_empty() {
                if !text.is_empty() {
                    text.push(' ');
                }
                text.push_str(&para_text);
            }
        }
    }

    // 转义 Markdown 表格中的特殊字符
    text.replace('|', "\\|").replace('\n', " ")
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

/// 从文本中提取标题
pub fn extract_title(text: &str) -> Option<String> {
    // 尝试找到第一个 Markdown 标题
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(stripped) = trimmed.strip_prefix("# ") {
            return Some(stripped.trim().to_string());
        }
    }

    // 回退到第一行非空文本
    for line in text.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && trimmed.len() < 200 {
            return Some(trimmed.to_string());
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_heading_level() {
        assert_eq!(detect_heading_level(Some("Heading1")), Some(1));
        assert_eq!(detect_heading_level(Some("Heading2")), Some(2));
        assert_eq!(detect_heading_level(Some("标题1")), Some(1));
        assert_eq!(detect_heading_level(Some("Title")), Some(1));
        assert_eq!(detect_heading_level(Some("Normal")), None);
    }

    #[test]
    fn test_clean_markdown() {
        let input = "Line 1\n\n\n\nLine 2\n\nLine 3";
        let output = clean_markdown(input);
        assert_eq!(output, "Line 1\n\nLine 2\n\nLine 3");
    }

    #[test]
    fn test_extract_title() {
        assert_eq!(extract_title("# My Title\n\nContent"), Some("My Title".to_string()));
        assert_eq!(extract_title("First Line\n\nMore content"), Some("First Line".to_string()));
    }
}
