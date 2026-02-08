# =====================================================
# =============== 批量 URL 转 Markdown 测试 ===============
# =====================================================

"""
批量 URL 转 Markdown 功能测试

Feature: batch-url-markdown
"""

import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.ui.batch_url_dialog import (
    BatchUrlDialog,
    BatchConversionState,
)


class TestUrlValidation:
    """URL 验证测试
    
    Property 1: URL Validation Correctness
    """
    
    def test_valid_http_url(self):
        """测试有效的 http URL"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        assert dialog._is_valid_url("http://example.com") is True
        assert dialog._is_valid_url("http://example.com/path") is True
        assert dialog._is_valid_url("http://example.com/path?query=1") is True
    
    def test_valid_https_url(self):
        """测试有效的 https URL"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        assert dialog._is_valid_url("https://example.com") is True
        assert dialog._is_valid_url("https://www.example.com/path") is True
        assert dialog._is_valid_url("https://sub.domain.example.com") is True
    
    def test_invalid_urls(self):
        """测试无效的 URL"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        assert dialog._is_valid_url("") is False
        assert dialog._is_valid_url("example.com") is False
        assert dialog._is_valid_url("ftp://example.com") is False
        assert dialog._is_valid_url("http://") is False
        assert dialog._is_valid_url("https://") is False
        assert dialog._is_valid_url("http:// space.com") is False
        assert dialog._is_valid_url("not a url") is False
        assert dialog._is_valid_url(None) is False
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_url_validation_property(self, text):
        """属性测试：URL 验证正确性
        
        Feature: batch-url-markdown, Property 1: URL Validation Correctness
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        result = dialog._is_valid_url(text)
        
        # 如果返回 True，必须以 http:// 或 https:// 开头
        if result:
            assert text.strip().startswith("http://") or text.strip().startswith("https://")
            # 协议后必须有内容
            if text.strip().startswith("https://"):
                rest = text.strip()[8:]
            else:
                rest = text.strip()[7:]
            assert len(rest) > 0
            assert not rest.startswith("/")


class TestUrlParsing:
    """URL 解析测试
    
    Property 2: URL Parsing Completeness
    """
    
    def test_parse_single_url(self):
        """测试解析单个 URL"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        urls = dialog._parse_urls("https://example.com")
        assert urls == ["https://example.com"]
    
    def test_parse_multiple_urls(self):
        """测试解析多个 URL"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        text = """https://example.com
https://test.com
http://another.com"""
        urls = dialog._parse_urls(text)
        assert urls == ["https://example.com", "https://test.com", "http://another.com"]
    
    def test_parse_with_invalid_lines(self):
        """测试解析包含无效行的文本"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        text = """https://example.com
invalid line
https://test.com
not a url
http://another.com"""
        urls = dialog._parse_urls(text)
        assert urls == ["https://example.com", "https://test.com", "http://another.com"]
    
    def test_parse_empty_lines(self):
        """测试解析包含空行的文本"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        text = """https://example.com

https://test.com

"""
        urls = dialog._parse_urls(text)
        assert urls == ["https://example.com", "https://test.com"]
    
    def test_parse_empty_text(self):
        """测试解析空文本"""
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        assert dialog._parse_urls("") == []
        assert dialog._parse_urls("   ") == []
        assert dialog._parse_urls("\n\n") == []
    
    @given(st.lists(st.sampled_from([
        "https://example.com",
        "http://test.com",
        "invalid",
        "",
        "not a url",
        "https://valid.org/path",
    ]), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_url_parsing_property(self, lines):
        """属性测试：URL 解析完整性
        
        Feature: batch-url-markdown, Property 2: URL Parsing Completeness
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        text = "\n".join(lines)
        parsed = dialog._parse_urls(text)
        
        # 计算预期的有效 URL 数量
        expected_count = sum(1 for line in lines if dialog._is_valid_url(line))
        assert len(parsed) == expected_count
        
        # 验证顺序保持
        valid_lines = [line.strip() for line in lines if dialog._is_valid_url(line)]
        assert parsed == valid_lines


class TestResultFormatting:
    """结果格式化测试
    
    Property 3, 4, 5: Result Formatting
    """
    
    def test_success_result_format(self):
        """测试成功结果格式
        
        Property 4: Success Result Formatting
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        result = dialog._format_success_result("https://example.com", "article.md")
        assert "✓" in result
        assert "https://example.com" in result
        assert "article.md" in result
    
    def test_failure_result_format(self):
        """测试失败结果格式
        
        Property 5: Failure Result Formatting
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        result = dialog._format_failure_result("https://example.com", "网络超时")
        assert "✗" in result
        assert "https://example.com" in result
        assert "网络超时" in result
    
    def test_summary_format(self):
        """测试摘要格式
        
        Property 3: Summary Generation Accuracy
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        summary = dialog._generate_summary(8, 2)
        assert "8" in summary
        assert "2" in summary
        assert "成功" in summary
        assert "失败" in summary
    
    @given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
    @settings(max_examples=100)
    def test_summary_property(self, success, failure):
        """属性测试：摘要生成准确性
        
        Feature: batch-url-markdown, Property 3: Summary Generation Accuracy
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        summary = dialog._generate_summary(success, failure)
        
        # 摘要必须包含正确的数字
        assert str(success) in summary
        assert str(failure) in summary
        assert "成功" in summary
        assert "失败" in summary
    
    @given(st.text(min_size=1, max_size=200), st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_success_format_property(self, url, filename):
        """属性测试：成功结果格式
        
        Feature: batch-url-markdown, Property 4: Success Result Formatting
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        result = dialog._format_success_result(url, filename)
        
        assert "✓" in result
        assert url in result
        assert filename in result
    
    @given(st.text(min_size=1, max_size=200), st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_failure_format_property(self, url, error):
        """属性测试：失败结果格式
        
        Feature: batch-url-markdown, Property 5: Failure Result Formatting
        """
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        result = dialog._format_failure_result(url, error)
        
        assert "✗" in result
        assert url in result
        assert error in result


class TestBatchConversionState:
    """批量转换状态测试
    
    Property 7: Retry List Correctness
    """
    
    def test_initial_state(self):
        """测试初始状态"""
        state = BatchConversionState()
        assert state.urls == []
        assert state.results == {}
        assert state.current_index == 0
        assert state.is_running is False
        assert state.is_cancelled is False
        assert state.success_count == 0
        assert state.failure_count == 0
        assert state.failed_urls == []
    
    def test_success_failure_counts(self):
        """测试成功/失败计数"""
        from screenshot_tool.services.markdown_converter import ConversionResult
        
        state = BatchConversionState()
        state.urls = ["url1", "url2", "url3"]
        state.results = {
            "url1": ConversionResult(success=True, file_path="file1.md"),
            "url2": ConversionResult(success=False, error="error"),
            "url3": ConversionResult(success=True, file_path="file3.md"),
        }
        
        assert state.success_count == 2
        assert state.failure_count == 1
    
    def test_failed_urls_order(self):
        """测试失败 URL 列表保持原始顺序
        
        Property 7: Retry List Correctness
        """
        from screenshot_tool.services.markdown_converter import ConversionResult
        
        state = BatchConversionState()
        state.urls = ["url1", "url2", "url3", "url4", "url5"]
        state.results = {
            "url1": ConversionResult(success=True, file_path="file1.md"),
            "url2": ConversionResult(success=False, error="error2"),
            "url3": ConversionResult(success=True, file_path="file3.md"),
            "url4": ConversionResult(success=False, error="error4"),
            "url5": ConversionResult(success=False, error="error5"),
        }
        
        # 失败的 URL 应该保持原始顺序
        assert state.failed_urls == ["url2", "url4", "url5"]
    
    def test_reset(self):
        """测试重置状态"""
        from screenshot_tool.services.markdown_converter import ConversionResult
        
        state = BatchConversionState()
        state.urls = ["url1", "url2"]
        state.results = {"url1": ConversionResult(success=True)}
        state.current_index = 1
        state.is_running = True
        state.is_cancelled = True
        
        state.reset()
        
        assert state.urls == []
        assert state.results == {}
        assert state.current_index == 0
        assert state.is_running is False
        assert state.is_cancelled is False
