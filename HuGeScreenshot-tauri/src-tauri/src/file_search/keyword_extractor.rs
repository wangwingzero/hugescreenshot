//! Keyword Extractor for OCR Text
//!
//! This module extracts meaningful keywords from OCR text for file search.
//! It filters out common stop words (Chinese and English) and punctuation,
//! returning a list of meaningful search terms.
//!
//! **Validates: Requirements 7.3**
//! - THE Search_Client SHALL extract keywords from OCR text for better matching

use std::collections::HashSet;
use unicode_segmentation::UnicodeSegmentation;

/// Chinese stop words - common words that don't carry meaningful search value
const CHINESE_STOP_WORDS: &[&str] = &[
    // Pronouns
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "她们",
    "它们",
    "这",
    "那",
    "这个",
    "那个",
    "这些",
    "那些",
    "这里",
    "那里",
    // Auxiliary words
    "的",
    "地",
    "得",
    "了",
    "着",
    "过",
    "吗",
    "呢",
    "吧",
    "啊",
    "呀",
    "哦",
    "哈",
    // Prepositions and conjunctions
    "在",
    "于",
    "和",
    "与",
    "或",
    "及",
    "而",
    "但",
    "但是",
    "然而",
    "因为",
    "所以",
    "如果",
    "虽然",
    "虽",
    "即使",
    "不但",
    "而且",
    "以及",
    "或者",
    "并且",
    // Verbs (common auxiliary)
    "是",
    "有",
    "没有",
    "没",
    "不",
    "不是",
    "就是",
    "可以",
    "能",
    "能够",
    "会",
    "要",
    "想",
    "应该",
    "必须",
    "可能",
    "也许",
    "大概",
    // Adverbs
    "很",
    "非常",
    "十分",
    "特别",
    "更",
    "最",
    "太",
    "真",
    "真的",
    "确实",
    "已经",
    "正在",
    "将要",
    "刚刚",
    "刚",
    "才",
    "就",
    "都",
    "也",
    "还",
    "又",
    // Measure words
    "个",
    "只",
    "条",
    "张",
    "把",
    "件",
    "本",
    "台",
    "辆",
    "架",
    "座",
    "间",
    // Numbers (as words)
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "百",
    "千",
    "万",
    "亿",
    "第一",
    "第二",
    "第三",
    "第四",
    "第五",
    // Time words
    "年",
    "月",
    "日",
    "时",
    "分",
    "秒",
    "今天",
    "明天",
    "昨天",
    "现在",
    "以前",
    "以后",
    // Question words
    "什么",
    "怎么",
    "怎样",
    "如何",
    "为什么",
    "哪",
    "哪个",
    "哪里",
    "哪些",
    "谁",
    "多少",
    // Other common words
    "等",
    "等等",
    "之",
    "其",
    "某",
    "各",
    "每",
    "任何",
    "所有",
    "一些",
    "一点",
    "上",
    "下",
    "左",
    "右",
    "前",
    "后",
    "里",
    "外",
    "中",
    "内",
    "来",
    "去",
    "到",
    "从",
    "向",
    "往",
    "给",
    "把",
    "被",
    "让",
    "使",
    "叫",
    "说",
    "看",
    "做",
    "用",
    "知道",
    "觉得",
    "认为",
    "希望",
    "需要",
];

/// English stop words - common words that don't carry meaningful search value
const ENGLISH_STOP_WORDS: &[&str] = &[
    // Articles
    "a",
    "an",
    "the",
    // Pronouns
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
    // Verbs (auxiliary)
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "doing",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    // Prepositions
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "up",
    "down",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "over",
    "out",
    "off",
    "again",
    "further",
    "then",
    "once",
    // Conjunctions
    "and",
    "but",
    "or",
    "nor",
    "so",
    "yet",
    "both",
    "either",
    "neither",
    "not",
    "only",
    "own",
    "same",
    "than",
    "too",
    "very",
    "just",
    "if",
    "because",
    "as",
    "until",
    "while",
    "although",
    "though",
    "unless",
    // Adverbs
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "any",
    "some",
    "no",
    "more",
    "most",
    "other",
    "such",
    "now",
    "also",
    "always",
    "never",
    "often",
    "sometimes",
    "usually",
    // Common verbs
    "get",
    "got",
    "go",
    "goes",
    "went",
    "gone",
    "going",
    "come",
    "comes",
    "came",
    "coming",
    "make",
    "makes",
    "made",
    "making",
    "take",
    "takes",
    "took",
    "taken",
    "taking",
    "see",
    "sees",
    "saw",
    "seen",
    "seeing",
    "know",
    "knows",
    "knew",
    "known",
    "knowing",
    "think",
    "thinks",
    "thought",
    "thinking",
    "want",
    "wants",
    "wanted",
    "wanting",
    "use",
    "uses",
    "used",
    "using",
    "find",
    "finds",
    "found",
    "finding",
    "give",
    "gives",
    "gave",
    "given",
    "giving",
    "tell",
    "tells",
    "told",
    "telling",
    "say",
    "says",
    "said",
    "saying",
    "let",
    "lets",
    "letting",
    "put",
    "puts",
    "putting",
    "keep",
    "keeps",
    "kept",
    "keeping",
    // Other common words
    "like",
    "even",
    "well",
    "back",
    "still",
    "way",
    "much",
    "many",
    "first",
    "last",
    "long",
    "great",
    "little",
    "own",
    "old",
    "new",
    "good",
    "bad",
    "right",
    "left",
    "high",
    "low",
    "big",
    "small",
    "yes",
    "no",
    "ok",
    "okay",
];

/// Minimum keyword length (in characters for Chinese, words for English)
const MIN_KEYWORD_LENGTH: usize = 2;

/// Maximum keyword length
const MAX_KEYWORD_LENGTH: usize = 50;

/// Result of keyword extraction
#[derive(Debug, Clone)]
pub struct KeywordExtractionResult {
    /// Extracted keywords
    pub keywords: Vec<String>,
    /// Original text length
    pub original_length: usize,
    /// Number of tokens before filtering
    pub tokens_before_filter: usize,
}

/// Keyword extractor for OCR text
///
/// Extracts meaningful keywords from OCR text by:
/// 1. Tokenizing the text (handling both Chinese and English)
/// 2. Filtering out stop words
/// 3. Filtering out punctuation and special characters
/// 4. Removing duplicates while preserving order
///
/// # Example
///
/// ```
/// use hugescreenshot_tauri_lib::file_search::KeywordExtractor;
///
/// let extractor = KeywordExtractor::new();
/// let result = extractor.extract("这是一个测试文档 This is a test document");
/// assert!(!result.keywords.is_empty());
/// ```
pub struct KeywordExtractor {
    chinese_stop_words: HashSet<&'static str>,
    english_stop_words: HashSet<&'static str>,
}

impl KeywordExtractor {
    /// Create a new KeywordExtractor with default stop word lists
    pub fn new() -> Self {
        Self {
            chinese_stop_words: CHINESE_STOP_WORDS.iter().copied().collect(),
            english_stop_words: ENGLISH_STOP_WORDS.iter().copied().collect(),
        }
    }

    /// Extract keywords from OCR text
    ///
    /// **Validates: Requirements 7.3**
    ///
    /// # Arguments
    ///
    /// * `text` - The OCR text to extract keywords from
    ///
    /// # Returns
    ///
    /// A `KeywordExtractionResult` containing the extracted keywords and metadata
    pub fn extract(&self, text: &str) -> KeywordExtractionResult {
        let original_length = text.len();

        // Tokenize the text
        let tokens = self.tokenize(text);
        let tokens_before_filter = tokens.len();

        // Filter and deduplicate
        let mut seen = HashSet::new();
        let keywords: Vec<String> = tokens
            .into_iter()
            .filter(|token| self.is_meaningful_keyword(token))
            .filter(|token| seen.insert(token.to_lowercase()))
            .collect();

        KeywordExtractionResult { keywords, original_length, tokens_before_filter }
    }

    /// Extract keywords and return just the keyword list
    ///
    /// This is a convenience method that returns only the keywords.
    ///
    /// # Arguments
    ///
    /// * `text` - The OCR text to extract keywords from
    ///
    /// # Returns
    ///
    /// A vector of extracted keywords
    pub fn extract_keywords(&self, text: &str) -> Vec<String> {
        self.extract(text).keywords
    }

    /// Tokenize text into words/characters
    ///
    /// Handles both Chinese (character-based) and English (word-based) text.
    fn tokenize(&self, text: &str) -> Vec<String> {
        let mut tokens = Vec::new();
        let mut current_english_word = String::new();
        let mut current_chinese_word = String::new();

        for grapheme in text.graphemes(true) {
            let c = grapheme.chars().next().unwrap_or(' ');

            if self.is_chinese_char(c) {
                // Flush English word if any
                if !current_english_word.is_empty() {
                    tokens.push(std::mem::take(&mut current_english_word));
                }
                // Add to Chinese word buffer
                current_chinese_word.push(c);
                // Chinese words are typically 2-4 characters
                // We'll extract both individual characters and potential compound words
            } else if c.is_alphabetic() {
                // Flush Chinese word if any
                if !current_chinese_word.is_empty() {
                    self.extract_chinese_tokens(&current_chinese_word, &mut tokens);
                    current_chinese_word.clear();
                }
                // Build English word
                current_english_word.push(c);
            } else if c.is_ascii_digit() {
                // Numbers can be part of meaningful terms (e.g., "Windows10")
                if !current_english_word.is_empty() {
                    current_english_word.push(c);
                } else if !current_chinese_word.is_empty() {
                    // Flush Chinese and start number
                    self.extract_chinese_tokens(&current_chinese_word, &mut tokens);
                    current_chinese_word.clear();
                    current_english_word.push(c);
                }
            } else {
                // Punctuation or whitespace - flush both buffers
                if !current_english_word.is_empty() {
                    tokens.push(std::mem::take(&mut current_english_word));
                }
                if !current_chinese_word.is_empty() {
                    self.extract_chinese_tokens(&current_chinese_word, &mut tokens);
                    current_chinese_word.clear();
                }
            }
        }

        // Flush remaining buffers
        if !current_english_word.is_empty() {
            tokens.push(current_english_word);
        }
        if !current_chinese_word.is_empty() {
            self.extract_chinese_tokens(&current_chinese_word, &mut tokens);
        }

        tokens
    }

    /// Extract tokens from a Chinese text segment
    ///
    /// Since we don't have a full Chinese word segmentation library,
    /// we use a simple approach:
    /// - Extract 2-character combinations (most common Chinese word length)
    /// - Extract 3-character combinations
    /// - Extract 4-character combinations (for idioms)
    /// - Also include individual characters for single-character keywords
    fn extract_chinese_tokens(&self, text: &str, tokens: &mut Vec<String>) {
        let chars: Vec<char> = text.chars().collect();
        let len = chars.len();

        if len == 0 {
            return;
        }

        // For very short text, just add the whole thing
        if len <= 4 {
            tokens.push(text.to_string());
            return;
        }

        // Extract n-grams (2, 3, 4 characters)
        // 2-character combinations (most common)
        for i in 0..len.saturating_sub(1) {
            let word: String = chars[i..i + 2].iter().collect();
            tokens.push(word);
        }

        // 3-character combinations
        for i in 0..len.saturating_sub(2) {
            let word: String = chars[i..i + 3].iter().collect();
            tokens.push(word);
        }

        // 4-character combinations (for idioms)
        for i in 0..len.saturating_sub(3) {
            let word: String = chars[i..i + 4].iter().collect();
            tokens.push(word);
        }
    }

    /// Check if a character is Chinese
    fn is_chinese_char(&self, c: char) -> bool {
        matches!(c,
            '\u{4E00}'..='\u{9FFF}' |  // CJK Unified Ideographs
            '\u{3400}'..='\u{4DBF}' |  // CJK Unified Ideographs Extension A
            '\u{F900}'..='\u{FAFF}' |  // CJK Compatibility Ideographs
            '\u{FE30}'..='\u{FE4F}'    // CJK Compatibility Forms
        )
    }

    /// Check if a token is a meaningful keyword
    fn is_meaningful_keyword(&self, token: &str) -> bool {
        // Check length
        if token.len() < MIN_KEYWORD_LENGTH || token.len() > MAX_KEYWORD_LENGTH {
            return false;
        }

        // Check if it's all punctuation or special characters
        if !token.chars().any(|c| c.is_alphanumeric() || self.is_chinese_char(c)) {
            return false;
        }

        // Check if it's a pure number
        if token.chars().all(|c| c.is_ascii_digit()) {
            return false;
        }

        // Check stop words (case-insensitive for English)
        let lower = token.to_lowercase();
        if self.english_stop_words.contains(lower.as_str()) {
            return false;
        }

        // Check Chinese stop words
        if self.chinese_stop_words.contains(token) {
            return false;
        }

        true
    }

    /// Check if the extracted keywords are non-empty
    ///
    /// This is useful for validation in property-based tests.
    pub fn has_meaningful_keywords(&self, text: &str) -> bool {
        // Empty or whitespace-only text has no keywords
        if text.trim().is_empty() {
            return false;
        }

        // Text with only stop words or punctuation has no keywords
        let result = self.extract(text);
        !result.keywords.is_empty()
    }
}

impl Default for KeywordExtractor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // =========================================================================
    // Unit Tests
    // =========================================================================

    #[test]
    fn test_extract_english_keywords() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("This is a test document about programming");

        // Should extract meaningful words, not stop words
        assert!(!result.keywords.is_empty());
        assert!(result.keywords.iter().any(|k| k == "test"));
        assert!(result.keywords.iter().any(|k| k == "document"));
        assert!(result.keywords.iter().any(|k| k == "programming"));

        // Should not contain stop words
        assert!(!result.keywords.iter().any(|k| k.to_lowercase() == "this"));
        assert!(!result.keywords.iter().any(|k| k.to_lowercase() == "is"));
        assert!(!result.keywords.iter().any(|k| k.to_lowercase() == "a"));
    }

    #[test]
    fn test_extract_chinese_keywords() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("这是一个关于编程的测试文档");

        // Should extract meaningful Chinese words
        assert!(!result.keywords.is_empty());

        // Should contain compound words
        assert!(result.keywords.iter().any(|k| k.contains("编程")));
        assert!(result.keywords.iter().any(|k| k.contains("测试")));
        assert!(result.keywords.iter().any(|k| k.contains("文档")));
    }

    #[test]
    fn test_extract_mixed_language() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("Windows10 操作系统 installation guide 安装指南");

        assert!(!result.keywords.is_empty());

        // Should extract both English and Chinese keywords
        assert!(result.keywords.iter().any(|k| k.contains("Windows10")));
        assert!(result.keywords.iter().any(|k| k.contains("installation")));
        assert!(result.keywords.iter().any(|k| k.contains("guide")));
        assert!(result.keywords.iter().any(|k| k.contains("操作")));
        assert!(result.keywords.iter().any(|k| k.contains("安装")));
    }

    #[test]
    fn test_filter_punctuation() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("Hello, World! 你好，世界！@#$%^&*()");

        // Should not contain punctuation
        for keyword in &result.keywords {
            assert!(!keyword.contains(','));
            assert!(!keyword.contains('!'));
            assert!(!keyword.contains('@'));
            assert!(!keyword.contains('#'));
        }
    }

    #[test]
    fn test_deduplicate_keywords() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("test Test TEST document Document DOCUMENT");

        // Should deduplicate (case-insensitive)
        let lower_keywords: Vec<String> =
            result.keywords.iter().map(|k| k.to_lowercase()).collect();

        let unique_count = lower_keywords.iter().filter(|k| *k == "test").count();
        assert_eq!(unique_count, 1);
    }

    #[test]
    fn test_empty_input() {
        let extractor = KeywordExtractor::new();

        let result = extractor.extract("");
        assert!(result.keywords.is_empty());

        let result = extractor.extract("   ");
        assert!(result.keywords.is_empty());
    }

    #[test]
    fn test_only_stop_words() {
        let extractor = KeywordExtractor::new();

        // English only stop words
        let result = extractor.extract("the a an is are was were");
        assert!(result.keywords.is_empty());

        // Chinese only stop words
        let result = extractor.extract("的 是 在 了 和 与");
        assert!(result.keywords.is_empty());
    }

    #[test]
    fn test_only_punctuation() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("!@#$%^&*()_+-=[]{}|;':\",./<>?");
        assert!(result.keywords.is_empty());
    }

    #[test]
    fn test_only_numbers() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("123 456 789");
        assert!(result.keywords.is_empty());
    }

    #[test]
    fn test_alphanumeric_keywords() {
        let extractor = KeywordExtractor::new();
        let result = extractor.extract("Windows10 Python3 version2");

        // Alphanumeric combinations should be kept
        assert!(result.keywords.iter().any(|k| k == "Windows10"));
        assert!(result.keywords.iter().any(|k| k == "Python3"));
        assert!(result.keywords.iter().any(|k| k == "version2"));
    }

    #[test]
    fn test_has_meaningful_keywords() {
        let extractor = KeywordExtractor::new();

        assert!(extractor.has_meaningful_keywords("programming document"));
        assert!(extractor.has_meaningful_keywords("编程文档"));
        assert!(!extractor.has_meaningful_keywords(""));
        assert!(!extractor.has_meaningful_keywords("   "));
        assert!(!extractor.has_meaningful_keywords("the a an is"));
        assert!(!extractor.has_meaningful_keywords("!@#$%"));
    }

    #[test]
    fn test_real_ocr_text() {
        let extractor = KeywordExtractor::new();

        // Simulate real OCR output with mixed content
        let ocr_text = r#"
            发票代码：1234567890
            发票号码：00001234
            开票日期：2024年01月15日
            购买方名称：北京科技有限公司
            商品名称：办公用品
            金额：￥1,234.56
        "#;

        let result = extractor.extract(ocr_text);

        // Should extract meaningful terms
        assert!(!result.keywords.is_empty());
        assert!(result.keywords.iter().any(|k| k.contains("发票")));
        assert!(result.keywords.iter().any(|k| k.contains("科技")));
        assert!(result.keywords.iter().any(|k| k.contains("办公")));
    }

    #[test]
    fn test_extraction_result_metadata() {
        let extractor = KeywordExtractor::new();
        let text = "This is a test document";
        let result = extractor.extract(text);

        assert_eq!(result.original_length, text.len());
        assert!(result.tokens_before_filter > 0);
    }
}

// =============================================================================
// Property-Based Tests
// =============================================================================
//
// **Feature: everything-file-search, Property 13: OCR Keyword Extraction**
// **Validates: Requirements 7.3**
//
// *For any* OCR text input, the keyword extraction function SHALL produce a
// non-empty list of meaningful search terms (excluding common stop words and
// punctuation).
// =============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use proptest::prelude::*;

    // =========================================================================
    // Proptest Strategies
    // =========================================================================

    /// Strategy for generating Chinese characters (CJK Unified Ideographs)
    fn arb_chinese_char() -> impl Strategy<Value = char> {
        proptest::char::range('\u{4E00}', '\u{9FFF}')
    }

    /// Strategy for generating Chinese strings of specified length
    fn arb_chinese_string(min_len: usize, max_len: usize) -> impl Strategy<Value = String> {
        proptest::collection::vec(arb_chinese_char(), min_len..=max_len)
            .prop_map(|chars| chars.into_iter().collect())
    }

    /// Strategy for generating meaningful English words (not stop words)
    fn arb_meaningful_english_word() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("programming".to_string()),
            Just("document".to_string()),
            Just("software".to_string()),
            Just("computer".to_string()),
            Just("algorithm".to_string()),
            Just("database".to_string()),
            Just("network".to_string()),
            Just("security".to_string()),
            Just("interface".to_string()),
            Just("application".to_string()),
            Just("development".to_string()),
            Just("framework".to_string()),
            Just("library".to_string()),
            Just("function".to_string()),
            Just("variable".to_string()),
            Just("screenshot".to_string()),
            Just("Windows10".to_string()),
            Just("Python3".to_string()),
            Just("Rust2024".to_string()),
        ]
    }

    /// Strategy for generating random English words (may include stop words)
    fn arb_english_word() -> impl Strategy<Value = String> {
        "[a-zA-Z]{2,10}".prop_map(|s| s.to_string())
    }

    /// Strategy for generating punctuation strings
    fn arb_punctuation() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("!".to_string()),
            Just("@".to_string()),
            Just("#".to_string()),
            Just("$".to_string()),
            Just("%".to_string()),
            Just("^".to_string()),
            Just("&".to_string()),
            Just("*".to_string()),
            Just("(".to_string()),
            Just(")".to_string()),
            Just(",".to_string()),
            Just(".".to_string()),
            Just("?".to_string()),
            Just("!".to_string()),
            Just("，".to_string()),
            Just("。".to_string()),
            Just("？".to_string()),
            Just("！".to_string()),
            Just("、".to_string()),
            Just("：".to_string()),
        ]
    }

    /// Strategy for generating whitespace
    fn arb_whitespace() -> impl Strategy<Value = String> {
        prop_oneof![
            Just(" ".to_string()),
            Just("  ".to_string()),
            Just("\t".to_string()),
            Just("\n".to_string()),
            Just(" \t ".to_string()),
        ]
    }

    /// Strategy for generating OCR-like text with meaningful content
    /// This generates text that should produce non-empty keywords
    fn arb_meaningful_ocr_text() -> impl Strategy<Value = String> {
        prop_oneof![
            // English meaningful text
            proptest::collection::vec(arb_meaningful_english_word(), 1..5)
                .prop_map(|words| words.join(" ")),
            // Chinese meaningful text (2-4 character words are meaningful)
            arb_chinese_string(4, 12),
            // Mixed language text
            (arb_meaningful_english_word(), arb_chinese_string(2, 6))
                .prop_map(|(en, cn)| format!("{} {}", en, cn)),
            // Alphanumeric combinations
            "[a-zA-Z]{3,8}[0-9]{1,3}".prop_map(|s| s.to_string()),
        ]
    }

    /// Strategy for generating random OCR text (may or may not have meaningful content)
    fn arb_random_ocr_text() -> impl Strategy<Value = String> {
        prop_oneof![
            // Meaningful text
            arb_meaningful_ocr_text(),
            // Random English words
            proptest::collection::vec(arb_english_word(), 1..10).prop_map(|words| words.join(" ")),
            // Random Chinese text
            arb_chinese_string(1, 20),
            // Mixed with punctuation
            (arb_meaningful_english_word(), arb_punctuation(), arb_chinese_string(2, 4))
                .prop_map(|(en, punct, cn)| format!("{}{}{}", en, punct, cn)),
        ]
    }

    /// Strategy for generating text that should NOT produce keywords
    fn arb_non_meaningful_text() -> impl Strategy<Value = String> {
        prop_oneof![
            // Empty string
            Just("".to_string()),
            // Only whitespace
            arb_whitespace(),
            // Only punctuation
            proptest::collection::vec(arb_punctuation(), 1..5).prop_map(|puncts| puncts.join("")),
            // Only numbers
            "[0-9]{1,10}".prop_map(|s| s.to_string()),
            // Only English stop words
            prop_oneof![
                Just("the a an is are was were".to_string()),
                Just("this that these those".to_string()),
                Just("and but or if then".to_string()),
            ],
            // Only Chinese stop words
            prop_oneof![
                Just("的 是 在 了 和 与".to_string()),
                Just("我 你 他 她 它".to_string()),
                Just("这 那 这个 那个".to_string()),
            ],
        ]
    }

    // =========================================================================
    // Property 13: OCR Keyword Extraction
    // =========================================================================
    //
    // **Feature: everything-file-search, Property 13: OCR Keyword Extraction**
    // **Validates: Requirements 7.3**
    //
    // *For any* OCR text input, the keyword extraction function SHALL produce a
    // non-empty list of meaningful search terms (excluding common stop words and
    // punctuation).
    // =========================================================================

    proptest! {
        #![proptest_config(proptest::prelude::ProptestConfig::with_cases(20))]

        // =====================================================================
        // Property 13.1: Meaningful text produces non-empty keywords
        // =====================================================================
        //
        // For text containing meaningful words, keywords SHALL be extracted.
        // =====================================================================

        #[test]
        fn prop_meaningful_text_produces_keywords(
            text in arb_meaningful_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // Meaningful text should produce at least one keyword
            prop_assert!(
                !result.keywords.is_empty(),
                "Meaningful text '{}' should produce keywords, but got empty list",
                text
            );
        }

        // =====================================================================
        // Property 13.2: Extracted keywords don't contain stop words
        // =====================================================================
        //
        // Extracted keywords SHALL NOT contain common stop words.
        // =====================================================================

        #[test]
        fn prop_keywords_exclude_stop_words(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // Define stop words to check
            let english_stop_words: HashSet<&str> = [
                "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                "have", "has", "had", "do", "does", "did", "will", "would", "could",
                "should", "may", "might", "must", "can", "this", "that", "these",
                "those", "and", "but", "or", "if", "then", "so", "as", "at", "by",
                "for", "in", "of", "on", "to", "with", "from", "up", "down", "out",
            ].iter().copied().collect();

            let chinese_stop_words: HashSet<&str> = [
                "的", "是", "在", "了", "和", "与", "或", "及", "而", "但",
                "我", "你", "他", "她", "它", "这", "那", "个", "只", "条",
            ].iter().copied().collect();

            for keyword in &result.keywords {
                let lower = keyword.to_lowercase();
                prop_assert!(
                    !english_stop_words.contains(lower.as_str()),
                    "Keyword '{}' is an English stop word",
                    keyword
                );
                prop_assert!(
                    !chinese_stop_words.contains(keyword.as_str()),
                    "Keyword '{}' is a Chinese stop word",
                    keyword
                );
            }
        }

        // =====================================================================
        // Property 13.3: Extracted keywords don't contain pure punctuation
        // =====================================================================
        //
        // Extracted keywords SHALL NOT contain pure punctuation.
        // =====================================================================

        #[test]
        fn prop_keywords_exclude_punctuation(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            let punctuation_chars: HashSet<char> = [
                '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '-', '_', '+', '=',
                '[', ']', '{', '}', '|', '\\', ':', ';', '"', '\'', '<', '>', ',', '.',
                '?', '/', '`', '~', '，', '。', '？', '！', '、', '：', '；', '"', '"',
                '\u{2018}', '\u{2019}', '【', '】', '（', '）', '《', '》',
            ].iter().copied().collect();

            for keyword in &result.keywords {
                // Check that keyword is not pure punctuation
                let has_alphanumeric = keyword.chars().any(|c| {
                    c.is_alphanumeric() ||
                    // Chinese characters
                    ('\u{4E00}'..='\u{9FFF}').contains(&c)
                });

                prop_assert!(
                    has_alphanumeric,
                    "Keyword '{}' contains only punctuation",
                    keyword
                );

                // Check that keyword doesn't start or end with punctuation
                // (This is a softer check - some edge cases may be acceptable)
                if let Some(first_char) = keyword.chars().next() {
                    if punctuation_chars.contains(&first_char) {
                        // If starts with punctuation, must have meaningful content
                        prop_assert!(
                            keyword.len() > 1 && keyword.chars().skip(1).any(|c| c.is_alphanumeric()),
                            "Keyword '{}' starts with punctuation without meaningful content",
                            keyword
                        );
                    }
                }
            }
        }

        // =====================================================================
        // Property 13.4: Keywords are properly deduplicated
        // =====================================================================
        //
        // Extracted keywords SHALL be deduplicated (case-insensitive).
        // =====================================================================

        #[test]
        fn prop_keywords_are_deduplicated(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // Check for duplicates (case-insensitive)
            let mut seen: HashSet<String> = HashSet::new();
            for keyword in &result.keywords {
                let lower = keyword.to_lowercase();
                prop_assert!(
                    seen.insert(lower.clone()),
                    "Duplicate keyword found: '{}' (case-insensitive)",
                    keyword
                );
            }
        }

        // =====================================================================
        // Property 13.5: Extraction is deterministic
        // =====================================================================
        //
        // Extracting keywords from the same text twice SHALL produce identical results.
        // =====================================================================

        #[test]
        fn prop_extraction_is_deterministic(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();

            let result1 = extractor.extract(&text);
            let result2 = extractor.extract(&text);

            prop_assert_eq!(
                result1.keywords,
                result2.keywords,
                "Extraction should be deterministic for text: '{}'",
                text
            );
            prop_assert_eq!(
                result1.original_length,
                result2.original_length
            );
            prop_assert_eq!(
                result1.tokens_before_filter,
                result2.tokens_before_filter
            );
        }

        // =====================================================================
        // Property 13.6: Keywords have minimum length
        // =====================================================================
        //
        // Extracted keywords SHALL have at least MIN_KEYWORD_LENGTH characters.
        // =====================================================================

        #[test]
        fn prop_keywords_have_minimum_length(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            for keyword in &result.keywords {
                prop_assert!(
                    keyword.len() >= MIN_KEYWORD_LENGTH,
                    "Keyword '{}' is shorter than minimum length {}",
                    keyword,
                    MIN_KEYWORD_LENGTH
                );
            }
        }

        // =====================================================================
        // Property 13.7: Keywords have maximum length
        // =====================================================================
        //
        // Extracted keywords SHALL have at most MAX_KEYWORD_LENGTH characters.
        // =====================================================================

        #[test]
        fn prop_keywords_have_maximum_length(
            text in arb_random_ocr_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            for keyword in &result.keywords {
                prop_assert!(
                    keyword.len() <= MAX_KEYWORD_LENGTH,
                    "Keyword '{}' is longer than maximum length {}",
                    keyword,
                    MAX_KEYWORD_LENGTH
                );
            }
        }

        // =====================================================================
        // Property 13.8: Non-meaningful text produces empty keywords
        // =====================================================================
        //
        // Text containing only stop words, punctuation, or whitespace SHALL
        // produce an empty keyword list.
        // =====================================================================

        #[test]
        fn prop_non_meaningful_text_produces_empty_keywords(
            text in arb_non_meaningful_text()
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            prop_assert!(
                result.keywords.is_empty(),
                "Non-meaningful text '{}' should produce empty keywords, but got: {:?}",
                text,
                result.keywords
            );
        }

        // =====================================================================
        // Property 13.9: Extraction never panics
        // =====================================================================
        //
        // The extraction function SHALL NOT panic for any input.
        // =====================================================================

        #[test]
        fn prop_extraction_never_panics(
            text in ".*" // Any string
        ) {
            let extractor = KeywordExtractor::new();

            // This should not panic
            let _result = extractor.extract(&text);

            // If we reach here, the test passes
            prop_assert!(true);
        }

        // =====================================================================
        // Property 13.10: Keywords preserve meaningful alphanumeric combinations
        // =====================================================================
        //
        // Alphanumeric combinations (like "Windows10", "Python3") SHALL be
        // preserved as keywords.
        // =====================================================================

        #[test]
        fn prop_alphanumeric_combinations_preserved(
            prefix in "[a-zA-Z]{3,8}",
            suffix in "[0-9]{1,3}"
        ) {
            let text = format!("{}{}", prefix, suffix);
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // The alphanumeric combination should be in the keywords
            prop_assert!(
                result.keywords.iter().any(|k| k.contains(&text) || text.contains(k)),
                "Alphanumeric combination '{}' should be preserved in keywords: {:?}",
                text,
                result.keywords
            );
        }

        // =====================================================================
        // Property 13.11: Chinese text produces Chinese keywords
        // =====================================================================
        //
        // Chinese text SHALL produce keywords containing Chinese characters.
        // =====================================================================

        #[test]
        fn prop_chinese_text_produces_chinese_keywords(
            text in arb_chinese_string(4, 12)
        ) {
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // Should produce keywords
            prop_assert!(
                !result.keywords.is_empty(),
                "Chinese text '{}' should produce keywords",
                text
            );

            // At least one keyword should contain Chinese characters
            let has_chinese_keyword = result.keywords.iter().any(|k| {
                k.chars().any(|c| ('\u{4E00}'..='\u{9FFF}').contains(&c))
            });

            prop_assert!(
                has_chinese_keyword,
                "Chinese text '{}' should produce keywords with Chinese characters, got: {:?}",
                text,
                result.keywords
            );
        }

        // =====================================================================
        // Property 13.12: Mixed language text produces keywords from both languages
        // =====================================================================
        //
        // Mixed language text SHALL produce keywords from both languages.
        // =====================================================================

        #[test]
        fn prop_mixed_language_produces_mixed_keywords(
            english in arb_meaningful_english_word(),
            chinese in arb_chinese_string(2, 6)
        ) {
            let text = format!("{} {}", english, chinese);
            let extractor = KeywordExtractor::new();
            let result = extractor.extract(&text);

            // Should produce keywords
            prop_assert!(
                !result.keywords.is_empty(),
                "Mixed text '{}' should produce keywords",
                text
            );

            // Should have English keyword
            let has_english = result.keywords.iter().any(|k| {
                k.chars().any(|c| c.is_ascii_alphabetic())
            });

            // Should have Chinese keyword
            let has_chinese = result.keywords.iter().any(|k| {
                k.chars().any(|c| ('\u{4E00}'..='\u{9FFF}').contains(&c))
            });

            prop_assert!(
                has_english,
                "Mixed text '{}' should produce English keywords, got: {:?}",
                text,
                result.keywords
            );

            prop_assert!(
                has_chinese,
                "Mixed text '{}' should produce Chinese keywords, got: {:?}",
                text,
                result.keywords
            );
        }
    }
}
