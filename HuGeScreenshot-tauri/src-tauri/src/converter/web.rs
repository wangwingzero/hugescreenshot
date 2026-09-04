//! 网页 URL 转 Markdown 模块
//!
//! 使用 reqwest 抓取网页，正则+scraper 清理噪音，htmd 转换为 Markdown。
//! 纯 Rust 实现，无需 Python Sidecar。
//!
//! 清理策略（三层）：
//! 1. 正则预清理：可靠移除 script/style/noscript/iframe 标签及内容、HTML 注释
//! 2. 正文定位：尝试 article/main 等语义选择器，优先提取正文区域
//! 3. DOM 降噪：用 scraper 节点 ID 标记 nav/header/footer/aside 等，重建时跳过

use std::collections::HashSet;
use std::time::Instant;

use regex::Regex;
use scraper::{Html, Node, Selector};
use tracing::{debug, info};

use super::html;
use super::ConverterError;

const USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const REQUEST_TIMEOUT_SECS: u64 = 30;

/// URL 转换结果
#[derive(Debug, Clone)]
pub struct UrlConversionResult {
    /// 转换后的 Markdown 内容
    pub markdown: String,
    /// 页面标题
    pub title: String,
    /// 原始 URL
    pub url: String,
    /// 转换耗时（秒）
    pub elapsed_secs: f64,
}

/// 抓取网页并转换为 Markdown
pub async fn fetch_url_to_markdown(url: &str) -> Result<UrlConversionResult, ConverterError> {
    let start = Instant::now();

    info!("开始抓取网页: {}", url);

    // 构建 HTTP 客户端
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(REQUEST_TIMEOUT_SECS))
        .redirect(reqwest::redirect::Policy::limited(10))
        .build()
        .map_err(|e| ConverterError::NetworkError(format!("HTTP 客户端创建失败: {}", e)))?;

    // 发送 GET 请求
    let response = client
        .get(url)
        .header("User-Agent", USER_AGENT)
        .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .send()
        .await
        .map_err(|e| {
            if e.is_timeout() {
                ConverterError::NetworkError(format!(
                    "请求超时 ({}s): {}",
                    REQUEST_TIMEOUT_SECS, url
                ))
            } else if e.is_connect() {
                ConverterError::NetworkError(format!("连接失败: {}", url))
            } else {
                ConverterError::NetworkError(format!("请求失败: {}", e))
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        return Err(ConverterError::NetworkError(format!("HTTP {}: {}", status.as_u16(), url)));
    }

    debug!("HTTP {} - 开始读取响应体", status.as_u16());

    // 读取响应体
    let raw_html = response
        .text()
        .await
        .map_err(|e| ConverterError::NetworkError(format!("读取响应失败: {}", e)))?;

    debug!("获取到 HTML: {} 字符", raw_html.len());

    // 提取标题（在清理之前）
    let title = html::extract_title_from_string(&raw_html).unwrap_or_default();

    // 第一层：正则预清理（移除 script/style/noscript/iframe/注释）
    let pre_cleaned = regex_strip_noise(&raw_html);
    debug!("正则预清理后: {} 字符", pre_cleaned.len());

    // 第二层：尝试正文定位（article/main 等语义选择器）
    // 第三层（回退）：DOM 降噪（移除 nav/header/footer/aside 等）
    let content_html = extract_content_or_denoise(&pre_cleaned);
    debug!("内容提取后: {} 字符", content_html.len());

    // 转换为 Markdown
    let markdown = html::html_string_to_markdown(&content_html)?;

    let elapsed_secs = start.elapsed().as_secs_f64();

    info!(
        "网页转换完成: {}, 耗时: {:.2}s, 标题: {}, 输出: {} 字符",
        url,
        elapsed_secs,
        if title.is_empty() { "(无)" } else { &title },
        markdown.len()
    );

    Ok(UrlConversionResult { markdown, title, url: url.to_string(), elapsed_secs })
}

// =========================================================================
// 第一层：正则预清理
// =========================================================================

/// 使用正则表达式移除 HTML 中不可能出现在正文中的标签及其内容。
///
/// script/style/noscript/iframe 不会自我嵌套，正则匹配安全可靠，
/// 这是解决 scraper 序列化不一致导致脚本泄露的根本修复。
fn regex_strip_noise(raw_html: &str) -> String {
    // (?is) = 忽略大小写 + 点匹配换行
    let patterns = [
        r"(?is)<script[\s>].*?</script>",
        r"(?is)<style[\s>].*?</style>",
        r"(?is)<noscript[\s>].*?</noscript>",
        r"(?is)<iframe[\s>].*?</iframe>",
        r"(?s)<!--.*?-->",
    ];

    let mut result = raw_html.to_string();
    for pattern in &patterns {
        if let Ok(re) = Regex::new(pattern) {
            result = re.replace_all(&result, "").to_string();
        }
    }
    result
}

// =========================================================================
// 第二层 + 第三层：正文定位 / DOM 降噪
// =========================================================================

/// 正文定位选择器（按优先级排列）
const CONTENT_SELECTORS: &[&str] = &[
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".markdown-body",
    ".prose",
];

/// 要从 DOM 中移除的噪音元素选择器（用于回退路径）
const NOISE_SELECTORS: &[&str] = &[
    "nav",
    "header",
    "footer",
    "aside",
    ".sidebar",
    ".ads",
    ".ad",
    ".advertisement",
    ".social-share",
    ".comments",
    ".comment",
    ".related-posts",
    ".cookie-banner",
    ".popup",
    ".modal",
    ".navigation",
    ".menu",
    ".breadcrumb",
    "[role='navigation']",
    "[role='banner']",
    "[role='contentinfo']",
];

/// 内容长度阈值：低于此值认为提取的内容不充分
const MIN_CONTENT_LEN: usize = 200;

/// 尝试提取正文内容，如果没有语义化容器则进行 DOM 降噪。
///
/// 策略：
/// 1. 尝试 article/main 等语义选择器 → 如果内容充分，返回其 inner_html
/// 2. 回退：从 body 中排除 nav/header/footer/aside 等噪音节点，重建 HTML
fn extract_content_or_denoise(html: &str) -> String {
    let document = Html::parse_document(html);

    // 第二层：尝试正文定位
    for selector_str in CONTENT_SELECTORS {
        if let Ok(selector) = Selector::parse(selector_str) {
            for element in document.select(&selector) {
                let inner = element.inner_html();
                if inner.trim().len() >= MIN_CONTENT_LEN {
                    debug!("正文定位命中: {}", selector_str);
                    return inner;
                }
            }
        }
    }

    // 第三层：DOM 降噪 — 收集噪音节点 ID，重建 HTML 时跳过
    let mut noise_ids: HashSet<ego_tree::NodeId> = HashSet::new();

    for selector_str in NOISE_SELECTORS {
        if let Ok(selector) = Selector::parse(selector_str) {
            for element in document.select(&selector) {
                collect_subtree_ids(element.id(), &document, &mut noise_ids);
            }
        }
    }

    // 重建 body 内容，跳过噪音子树
    if let Ok(body_sel) = Selector::parse("body") {
        if let Some(body) = document.select(&body_sel).next() {
            let mut output = String::with_capacity(html.len() / 2);
            serialize_without_noise(body.id(), &document, &noise_ids, &mut output);
            return output;
        }
    }

    // 最终回退：返回预清理后的原始 HTML
    html.to_string()
}

/// 递归收集一个节点及其所有后代的 NodeId
fn collect_subtree_ids(
    node_id: ego_tree::NodeId,
    document: &Html,
    ids: &mut HashSet<ego_tree::NodeId>,
) {
    ids.insert(node_id);
    if let Some(node) = document.tree.get(node_id) {
        for child in node.children() {
            collect_subtree_ids(child.id(), document, ids);
        }
    }
}

/// 序列化 DOM 子树，跳过噪音节点集合中的节点
fn serialize_without_noise(
    node_id: ego_tree::NodeId,
    document: &Html,
    noise_ids: &HashSet<ego_tree::NodeId>,
    output: &mut String,
) {
    let Some(node_ref) = document.tree.get(node_id) else {
        return;
    };

    match node_ref.value() {
        Node::Element(elem) => {
            // 跳过 head 元素
            if elem.name() == "head" {
                return;
            }

            // 不要输出 body/html 标签本身，只递归其子节点
            let is_wrapper = elem.name() == "body" || elem.name() == "html";

            if !is_wrapper {
                // 开始标签
                output.push('<');
                output.push_str(elem.name());
                for (key, val) in elem.attrs() {
                    output.push(' ');
                    output.push_str(key);
                    output.push_str("=\"");
                    output.push_str(val);
                    output.push('"');
                }
                output.push('>');
            }

            // 递归子节点，跳过噪音
            for child in node_ref.children() {
                if !noise_ids.contains(&child.id()) {
                    serialize_without_noise(child.id(), document, noise_ids, output);
                }
            }

            if !is_wrapper {
                // 结束标签
                output.push_str("</");
                output.push_str(elem.name());
                output.push('>');
            }
        }
        Node::Text(text) => {
            output.push_str(text);
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_regex_strip_noise() {
        let html = r#"<html><body>
            <script>alert('x')</script>
            <p>Content</p>
            <style>.foo { color: red; }</style>
            <!-- comment -->
        </body></html>"#;

        let cleaned = regex_strip_noise(html);
        assert!(!cleaned.contains("alert"));
        assert!(!cleaned.contains("color: red"));
        assert!(!cleaned.contains("comment"));
        assert!(cleaned.contains("Content"));
    }

    #[test]
    fn test_regex_strip_multiline_script() {
        let html = r#"<html><body>
            <script type="text/javascript">
            //<!-- (function(){var an="V=2.1.16";
            var x = 1;
            })(); //-->
            </script>
            <p>Hello World</p>
        </body></html>"#;

        let cleaned = regex_strip_noise(html);
        assert!(!cleaned.contains("V=2.1.16"));
        assert!(!cleaned.contains("var x"));
        assert!(cleaned.contains("Hello World"));
    }

    #[test]
    fn test_extract_content_with_article() {
        let html = r#"<html><body>
            <nav>Navigation</nav>
            <article><h1>Title</h1><p>This is the main article content that should be extracted as it is long enough to meet the minimum threshold for content extraction.</p></article>
            <footer>Footer</footer>
        </body></html>"#;

        let pre_cleaned = regex_strip_noise(html);
        let content = extract_content_or_denoise(&pre_cleaned);
        assert!(content.contains("Title"));
        assert!(content.contains("main article content"));
        assert!(!content.contains("Navigation"));
        assert!(!content.contains("Footer"));
    }

    #[test]
    fn test_extract_content_with_main() {
        let html = r#"<html><body>
            <header>Header</header>
            <main><h1>Main Content</h1><p>This is the main content area that contains enough text to be considered a valid content extraction result by the algorithm.</p></main>
            <aside>Sidebar</aside>
        </body></html>"#;

        let pre_cleaned = regex_strip_noise(html);
        let content = extract_content_or_denoise(&pre_cleaned);
        assert!(content.contains("Main Content"));
        assert!(!content.contains("Header"));
        assert!(!content.contains("Sidebar"));
    }

    #[test]
    fn test_denoise_fallback() {
        let html = r#"<html><head><title>Test</title></head><body>
            <nav>Navigation</nav>
            <div><h1>Title</h1><p>Content</p></div>
            <footer>Footer</footer>
        </body></html>"#;

        let pre_cleaned = regex_strip_noise(html);
        let content = extract_content_or_denoise(&pre_cleaned);
        assert!(content.contains("Title"));
        assert!(content.contains("Content"));
        assert!(!content.contains("Navigation"));
        assert!(!content.contains("Footer"));
    }

    #[test]
    fn test_remove_noise_class_selectors() {
        let html = r#"<html><body>
            <div class="sidebar">Sidebar</div>
            <div class="ads">Ad content</div>
            <div class="content"><p>Main content</p></div>
        </body></html>"#;

        let pre_cleaned = regex_strip_noise(html);
        let content = extract_content_or_denoise(&pre_cleaned);
        assert!(!content.contains("Sidebar"));
        assert!(!content.contains("Ad content"));
        assert!(content.contains("Main content"));
    }

    #[test]
    fn test_full_pipeline_sina_like() {
        let html = r#"<html><head><title>Test</title></head><body>
            <script type="text/javascript">
            //<!-- (function(){var an="V=2.1.16";var ah=window;})(); //-->
            </script>
            <nav><a href="/">Home</a><a href="/news">News</a></nav>
            <header><div class="logo">Logo</div></header>
            <div class="main-content">
                <h1>Important Title</h1>
                <p>This is a long article content that should be preserved during conversion.
                The article should remain while scripts, navigation, headers and footers are removed.
                This text needs to be long enough to exceed the minimum content length threshold.</p>
            </div>
            <footer><p>Copyright 2026</p></footer>
            <style>.foo { display: none; }</style>
        </body></html>"#;

        let pre_cleaned = regex_strip_noise(html);
        let content = extract_content_or_denoise(&pre_cleaned);

        // script must be removed
        assert!(!content.contains("V=2.1.16"), "script leak: V=2.1.16");
        assert!(!content.contains("var ah=window"), "script leak: var ah");
        // style must be removed
        assert!(!content.contains("display: none"), "style leak");
        // main content must remain
        assert!(content.contains("Important Title"), "missing title");
        assert!(content.contains("article content"), "missing content");
        // nav/header/footer must be removed
        assert!(!content.contains("Home"), "nav leak: Home");
        assert!(!content.contains("Logo"), "header leak: Logo");
        assert!(!content.contains("Copyright"), "footer leak: Copyright");
    }
}
