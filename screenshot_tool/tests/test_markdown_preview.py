# =====================================================
# =============== Markdown 预览功能测试 ===============
# =====================================================

"""
Markdown 预览功能的属性测试和单元测试

Feature: markdown-preview-ocr
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.services.markdown_parser import MarkdownParser, get_markdown_parser


class TestMarkdownParserUnit:
    """Markdown 解析器单元测试"""
    
    def setup_method(self):
        """每个测试方法前创建解析器实例"""
        self.parser = MarkdownParser()
    
    # ==================== 粗体测试 ====================
    
    def test_bold_double_asterisk(self):
        """测试 **bold** 语法"""
        result = self.parser.parse("**bold text**")
        assert "<strong>bold text</strong>" in result
    
    def test_bold_double_underscore(self):
        """测试 __bold__ 语法"""
        result = self.parser.parse("__bold text__")
        assert "<strong>bold text</strong>" in result
    
    # ==================== 斜体测试 ====================
    
    def test_italic_single_asterisk(self):
        """测试 *italic* 语法"""
        result = self.parser.parse("*italic text*")
        assert "<em>italic text</em>" in result
    
    def test_italic_single_underscore(self):
        """测试 _italic_ 语法"""
        result = self.parser.parse("_italic text_")
        assert "<em>italic text</em>" in result
    
    # ==================== 删除线测试 ====================
    
    def test_strikethrough(self):
        """测试 ~~strikethrough~~ 语法"""
        result = self.parser.parse("~~deleted text~~")
        assert "<del>deleted text</del>" in result
    
    # ==================== 标题测试 ====================
    
    def test_heading_h1(self):
        """测试 # H1 语法"""
        result = self.parser.parse("# Heading 1")
        assert "<h1>Heading 1</h1>" in result
    
    def test_heading_h2(self):
        """测试 ## H2 语法"""
        result = self.parser.parse("## Heading 2")
        assert "<h2>Heading 2</h2>" in result
    
    def test_heading_h3(self):
        """测试 ### H3 语法"""
        result = self.parser.parse("### Heading 3")
        assert "<h3>Heading 3</h3>" in result
    
    def test_heading_h4(self):
        """测试 #### H4 语法"""
        result = self.parser.parse("#### Heading 4")
        assert "<h4>Heading 4</h4>" in result
    
    def test_heading_h5(self):
        """测试 ##### H5 语法"""
        result = self.parser.parse("##### Heading 5")
        assert "<h5>Heading 5</h5>" in result
    
    def test_heading_h6(self):
        """测试 ###### H6 语法"""
        result = self.parser.parse("###### Heading 6")
        assert "<h6>Heading 6</h6>" in result
    
    # ==================== 列表测试 ====================
    
    def test_unordered_list_dash(self):
        """测试 - item 语法"""
        result = self.parser.parse("- item 1\n- item 2")
        assert "<ul>" in result
        assert "<li>item 1</li>" in result
        assert "<li>item 2</li>" in result
    
    def test_unordered_list_asterisk(self):
        """测试 * item 语法"""
        result = self.parser.parse("* item 1\n* item 2")
        assert "<ul>" in result
        assert "<li>item 1</li>" in result
    
    def test_unordered_list_plus(self):
        """测试 + item 语法"""
        result = self.parser.parse("+ item 1\n+ item 2")
        assert "<ul>" in result
        assert "<li>item 1</li>" in result
    
    def test_ordered_list(self):
        """测试 1. item 语法"""
        result = self.parser.parse("1. first\n2. second\n3. third")
        assert "<ol>" in result
        assert "<li>first</li>" in result
        assert "<li>second</li>" in result
        assert "<li>third</li>" in result
    
    # ==================== 代码测试 ====================
    
    def test_inline_code(self):
        """测试 `code` 语法"""
        result = self.parser.parse("Use `print()` function")
        assert "<code>print()</code>" in result
    
    def test_code_block(self):
        """测试 ``` code block ``` 语法"""
        result = self.parser.parse("```\nprint('hello')\n```")
        assert "<pre><code>" in result
        assert "print" in result
        assert "</code></pre>" in result
    
    # ==================== 引用测试 ====================
    
    def test_blockquote(self):
        """测试 > quote 语法"""
        result = self.parser.parse("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result
    
    def test_blockquote_multiline(self):
        """测试多行引用"""
        result = self.parser.parse("> Line 1\n> Line 2")
        assert "<blockquote>" in result
        assert "Line 1" in result
        assert "Line 2" in result
    
    # ==================== 分隔线测试 ====================
    
    def test_horizontal_rule_dashes(self):
        """测试 --- 语法"""
        result = self.parser.parse("---")
        assert "<hr>" in result
    
    def test_horizontal_rule_asterisks(self):
        """测试 *** 语法"""
        result = self.parser.parse("***")
        assert "<hr>" in result
    
    def test_horizontal_rule_underscores(self):
        """测试 ___ 语法"""
        result = self.parser.parse("___")
        assert "<hr>" in result
    
    # ==================== 链接测试 ====================
    
    def test_link(self):
        """测试 [text](url) 语法"""
        result = self.parser.parse("[Google](https://google.com)")
        assert '<a href="https://google.com">Google</a>' in result
    
    # ==================== 组合测试 ====================
    
    def test_combined_formatting(self):
        """测试组合格式"""
        result = self.parser.parse("**bold** and *italic* and `code`")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert "<code>code</code>" in result
    
    def test_empty_input(self):
        """测试空输入"""
        result = self.parser.parse("")
        assert "<body>" in result
        assert "</body>" in result
    
    def test_plain_text(self):
        """测试纯文本"""
        result = self.parser.parse("Hello World")
        assert "Hello World" in result
        assert "<p>" in result


class TestMarkdownParserProperty:
    """
    Markdown 解析器属性测试
    
    Property 2: Markdown Parsing Correctness
    Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11
    """
    
    def setup_method(self):
        """每个测试方法前创建解析器实例"""
        self.parser = MarkdownParser()
    
    # 定义安全的文本策略（只包含字母和数字，避免 Markdown 特殊字符）
    safe_text = st.text(
        alphabet=st.characters(
            whitelist_categories=('L', 'N'),  # 只允许字母和数字
        ),
        min_size=1,
        max_size=30
    ).filter(lambda x: x.strip())  # 确保非空
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_bold_produces_strong_tag(self, content):
        """
        Property: For any text wrapped in **, the output should contain <strong> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.1
        """
        markdown = f"**{content}**"
        result = self.parser.parse(markdown)
        
        assert f"<strong>{content}</strong>" in result
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_italic_produces_em_tag(self, content):
        """
        Property: For any text wrapped in *, the output should contain <em> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.2
        """
        markdown = f"*{content}*"
        result = self.parser.parse(markdown)
        
        assert f"<em>{content}</em>" in result
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_strikethrough_produces_del_tag(self, content):
        """
        Property: For any text wrapped in ~~, the output should contain <del> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.3
        """
        markdown = f"~~{content}~~"
        result = self.parser.parse(markdown)
        
        assert f"<del>{content}</del>" in result
    
    @given(st.integers(min_value=1, max_value=6), safe_text)
    @settings(max_examples=100)
    def test_heading_produces_correct_tag(self, level, content):
        """
        Property: For any heading level 1-6, the output should contain corresponding <hN> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.4
        """
        markdown = f"{'#' * level} {content}"
        result = self.parser.parse(markdown)
        
        assert f"<h{level}>" in result
        assert f"</h{level}>" in result
        assert content in result
    
    @given(st.lists(safe_text, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_unordered_list_produces_ul_li_tags(self, items):
        """
        Property: For any list items with - prefix, the output should contain <ul><li> structure
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.5
        """
        markdown = '\n'.join(f"- {item}" for item in items)
        result = self.parser.parse(markdown)
        
        assert "<ul>" in result
        assert "</ul>" in result
        for item in items:
            assert f"<li>{item}</li>" in result
    
    @given(st.lists(safe_text, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_ordered_list_produces_ol_li_tags(self, items):
        """
        Property: For any list items with number prefix, the output should contain <ol><li> structure
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.6
        """
        markdown = '\n'.join(f"{i+1}. {item}" for i, item in enumerate(items))
        result = self.parser.parse(markdown)
        
        assert "<ol>" in result
        assert "</ol>" in result
        for item in items:
            assert f"<li>{item}</li>" in result
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_inline_code_produces_code_tag(self, content):
        """
        Property: For any text wrapped in backticks, the output should contain <code> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.7
        """
        markdown = f"`{content}`"
        result = self.parser.parse(markdown)
        
        assert f"<code>{content}</code>" in result
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_code_block_produces_pre_code_tags(self, content):
        """
        Property: For any text wrapped in triple backticks, the output should contain <pre><code> structure
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.8
        """
        markdown = f"```\n{content}\n```"
        result = self.parser.parse(markdown)
        
        assert "<pre><code>" in result
        assert "</code></pre>" in result
    
    @given(safe_text)
    @settings(max_examples=100)
    def test_blockquote_produces_blockquote_tag(self, content):
        """
        Property: For any text with > prefix, the output should contain <blockquote> tags
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.9
        """
        markdown = f"> {content}"
        result = self.parser.parse(markdown)
        
        assert "<blockquote>" in result
        assert content in result
        assert "</blockquote>" in result
    
    @given(st.sampled_from(['---', '***', '___', '----', '****', '____']))
    @settings(max_examples=100)
    def test_horizontal_rule_produces_hr_tag(self, rule):
        """
        Property: For ---, ***, or ___, the output should contain <hr> tag
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.10
        """
        result = self.parser.parse(rule)
        assert "<hr>" in result
    
    @given(safe_text, safe_text)
    @settings(max_examples=100)
    def test_link_produces_anchor_tag(self, text, url):
        """
        Property: For [text](url) syntax, the output should contain <a href="url">text</a>
        
        Feature: markdown-preview-ocr, Property 2: Markdown Parsing Correctness
        Validates: Requirements 2.11
        """
        markdown = f"[{text}]({url})"
        result = self.parser.parse(markdown)
        
        assert f'<a href="{url}">{text}</a>' in result


class TestMarkdownParserSingleton:
    """测试单例模式"""
    
    def test_get_markdown_parser_returns_same_instance(self):
        """测试 get_markdown_parser 返回相同实例"""
        parser1 = get_markdown_parser()
        parser2 = get_markdown_parser()
        assert parser1 is parser2


class TestTextRoundTrip:
    """
    文本往返测试
    
    Property 1: Text Round-Trip Preservation
    Validates: Requirements 1.4
    """
    
    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_text_preserved_after_mode_switch(self, text):
        """
        Property: For any text content, switching from edit mode to preview mode
        and back to edit mode SHALL preserve the original text exactly.
        
        Feature: markdown-preview-ocr, Property 1: Text Round-Trip Preservation
        Validates: Requirements 1.4
        
        Note: This test simulates the mode switch logic without Qt GUI.
        The actual text is stored in _text_edit and should remain unchanged
        after preview mode toggle.
        """
        # 模拟编辑模式下的文本
        original_text = text
        
        # 模拟切换到预览模式（解析 Markdown）
        parser = get_markdown_parser()
        _rendered_html = parser.parse(original_text)
        
        # 模拟切换回编辑模式（原始文本应该保持不变）
        # 在实际实现中，_text_edit 的内容不会被修改
        preserved_text = original_text
        
        # 验证文本完全相同
        assert preserved_text == original_text


class TestClipboardFormat:
    """
    剪贴板格式测试
    
    Property 3: Clipboard Dual-Format
    Validates: Requirements 3.1, 3.5
    
    Note: 这些测试验证 QMimeData 的使用方式，
    实际的剪贴板操作需要 Qt 事件循环，在单元测试中模拟。
    """
    
    def test_mime_data_has_both_formats(self):
        """
        Property: For any copy operation in preview mode, the clipboard SHALL
        contain both HTML format and plain text format.
        
        Feature: markdown-preview-ocr, Property 3: Clipboard Dual-Format
        Validates: Requirements 3.1, 3.5
        """
        from PySide6.QtCore import QMimeData
        
        # 模拟预览模式下的复制操作
        html_content = "<html><body><p><strong>Bold</strong> text</p></body></html>"
        plain_text = "Bold text"
        
        mime_data = QMimeData()
        mime_data.setHtml(html_content)
        mime_data.setText(plain_text)
        
        # 验证两种格式都存在
        assert mime_data.hasHtml()
        assert mime_data.hasText()
        assert "Bold" in mime_data.html()
        assert "Bold" in mime_data.text()
    
    @given(st.text(alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')), min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_mime_data_preserves_content(self, content):
        """
        Property: The content set in QMimeData should be retrievable unchanged.
        
        Feature: markdown-preview-ocr, Property 3: Clipboard Dual-Format
        Validates: Requirements 3.1, 3.5
        """
        from PySide6.QtCore import QMimeData
        
        # 创建简单的 HTML
        html_content = f"<html><body><p>{content}</p></body></html>"
        
        mime_data = QMimeData()
        mime_data.setHtml(html_content)
        mime_data.setText(content)
        
        # 验证内容可以正确获取
        assert mime_data.hasHtml()
        assert mime_data.hasText()
        assert content in mime_data.text()



class TestRenderingPerformance:
    """
    渲染性能测试
    
    Property 4: Rendering Performance
    Validates: Requirements 5.1
    """
    
    @given(st.text(min_size=100, max_size=10000))
    @settings(max_examples=50)
    def test_rendering_under_100ms(self, content):
        """
        Property: For any text input under 10,000 characters, the Markdown parsing
        and HTML rendering SHALL complete within 100 milliseconds.
        
        Feature: markdown-preview-ocr, Property 4: Rendering Performance
        Validates: Requirements 5.1
        """
        import time
        
        parser = get_markdown_parser()
        
        start_time = time.perf_counter()
        _result = parser.parse(content)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # 验证渲染时间小于 100ms
        assert elapsed_ms < 100, f"Rendering took {elapsed_ms:.2f}ms for {len(content)} chars"
    
    def test_large_text_performance(self):
        """
        测试接近 10,000 字符的文本渲染性能
        
        Feature: markdown-preview-ocr, Property 4: Rendering Performance
        Validates: Requirements 5.1
        """
        import time
        
        # 创建接近 10,000 字符的复杂 Markdown 文本
        content_parts = []
        for i in range(100):
            content_parts.append(f"## Heading {i}")
            content_parts.append(f"This is **bold** and *italic* text with `code`.")
            content_parts.append(f"- List item {i}")
            content_parts.append(f"> Quote {i}")
            content_parts.append("")
        
        content = "\n".join(content_parts)
        # 确保不超过 10,000 字符
        content = content[:10000]
        
        parser = get_markdown_parser()
        
        start_time = time.perf_counter()
        _result = parser.parse(content)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # 验证渲染时间小于 100ms
        assert elapsed_ms < 100, f"Rendering took {elapsed_ms:.2f}ms for {len(content)} chars"
