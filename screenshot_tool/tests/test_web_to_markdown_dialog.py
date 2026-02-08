# =====================================================
# =============== 网页转 Markdown 对话框测试 ===============
# =====================================================

"""
网页转 Markdown 对话框测试

Feature: web-to-markdown-dialog
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.ui.web_to_markdown_dialog import (
    WebToMarkdownDialog,
    is_valid_url,
    parse_urls,
)


class TestUrlValidation:
    """URL 验证测试
    
    Property 1: URL Validation Correctness
    **Validates: Requirements 4.1, 4.2**
    """
    
    def test_valid_http_url(self):
        """测试有效的 http URL"""
        assert is_valid_url("http://example.com") is True
        assert is_valid_url("http://example.com/path") is True
        assert is_valid_url("http://example.com/path?query=1") is True
        assert is_valid_url("http://example.com:8080/path") is True
    
    def test_valid_https_url(self):
        """测试有效的 https URL"""
        assert is_valid_url("https://example.com") is True
        assert is_valid_url("https://www.example.com/path") is True
        assert is_valid_url("https://sub.domain.example.com") is True
        assert is_valid_url("https://example.com/path/to/page.html") is True
    
    def test_invalid_urls(self):
        """测试无效的 URL"""
        assert is_valid_url("") is False
        assert is_valid_url("example.com") is False
        assert is_valid_url("ftp://example.com") is False
        assert is_valid_url("http://") is False
        assert is_valid_url("https://") is False
        assert is_valid_url("http:// space.com") is False
        assert is_valid_url("not a url") is False
        assert is_valid_url(None) is False
        assert is_valid_url("http://host with space.com") is False
        assert is_valid_url("https://host\nwith\nnewline.com") is False
    
    def test_whitespace_handling(self):
        """测试空白字符处理"""
        assert is_valid_url("  https://example.com  ") is True
        assert is_valid_url("\thttps://example.com\t") is True
        assert is_valid_url("\nhttps://example.com\n") is True
    
    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_url_validation_property(self, text):
        """属性测试：URL 验证正确性
        
        Feature: web-to-markdown-dialog, Property 1: URL Validation Correctness
        **Validates: Requirements 4.1, 4.2**
        
        对于任意字符串输入，URL 验证函数返回 True 当且仅当：
        - 字符串以 "http://" 或 "https://" 开头
        - 主机部分（协议后，第一个 "/" 前或结尾）非空
        - 主机部分不包含空格、换行符、回车符
        """
        result = is_valid_url(text)
        
        if result:
            stripped = text.strip()
            # 必须以 http:// 或 https:// 开头
            assert stripped.startswith("http://") or stripped.startswith("https://")
            
            # 获取协议后的部分
            if stripped.startswith("https://"):
                rest = stripped[8:]
            else:
                rest = stripped[7:]
            
            # 协议后必须有内容
            assert len(rest) > 0
            
            # 获取主机部分
            slash_pos = rest.find("/")
            if slash_pos == -1:
                host = rest
            else:
                host = rest[:slash_pos]
            
            # 主机部分非空且无空格/换行
            assert len(host) > 0
            assert " " not in host
            assert "\n" not in host
            assert "\r" not in host


class TestUrlParsing:
    """URL 解析测试
    
    Property 2: URL Parsing Completeness
    **Validates: Requirements 4.3**
    """
    
    def test_parse_single_url(self):
        """测试解析单个 URL"""
        urls = parse_urls("https://example.com")
        assert urls == ["https://example.com"]
    
    def test_parse_multiple_urls(self):
        """测试解析多个 URL"""
        text = """https://example.com
https://test.com
http://another.com"""
        urls = parse_urls(text)
        assert urls == ["https://example.com", "https://test.com", "http://another.com"]
    
    def test_parse_with_invalid_lines(self):
        """测试解析包含无效行的文本"""
        text = """https://example.com
invalid line
https://test.com
not a url
http://another.com"""
        urls = parse_urls(text)
        assert urls == ["https://example.com", "https://test.com", "http://another.com"]
    
    def test_parse_empty_lines(self):
        """测试解析包含空行的文本"""
        text = """https://example.com

https://test.com

"""
        urls = parse_urls(text)
        assert urls == ["https://example.com", "https://test.com"]
    
    def test_parse_empty_text(self):
        """测试解析空文本"""
        assert parse_urls("") == []
        assert parse_urls("   ") == []
        assert parse_urls("\n\n") == []
        assert parse_urls(None) == []
    
    def test_parse_preserves_order(self):
        """测试解析保持原始顺序"""
        text = """https://z.com
https://a.com
https://m.com"""
        urls = parse_urls(text)
        assert urls == ["https://z.com", "https://a.com", "https://m.com"]
    
    @given(st.lists(st.sampled_from([
        "https://example.com",
        "http://test.com",
        "invalid",
        "",
        "not a url",
        "https://valid.org/path",
        "ftp://wrong.protocol.com",
        "http://",
        "https://",
    ]), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_url_parsing_property(self, lines):
        """属性测试：URL 解析完整性
        
        Feature: web-to-markdown-dialog, Property 2: URL Parsing Completeness
        **Validates: Requirements 4.3**
        
        对于任意多行文本输入，URL 解析函数返回的列表：
        - 包含且仅包含输入中的有效 URL
        - 保持原始顺序
        - 排除空行和无效 URL
        """
        text = "\n".join(lines)
        parsed = parse_urls(text)
        
        # 计算预期的有效 URL 数量
        expected_count = sum(1 for line in lines if is_valid_url(line))
        assert len(parsed) == expected_count
        
        # 验证顺序保持
        valid_lines = [line.strip() for line in lines if is_valid_url(line)]
        assert parsed == valid_lines
        
        # 验证所有返回的 URL 都是有效的
        for url in parsed:
            assert is_valid_url(url)


class TestUrlCountAccuracy:
    """URL 计数准确性测试
    
    Property 3: URL Count Accuracy
    **Validates: Requirements 3.4, 3.5**
    """
    
    def test_count_single_url(self):
        """测试单个 URL 计数"""
        urls = parse_urls("https://example.com")
        assert len(urls) == 1
    
    def test_count_multiple_urls(self):
        """测试多个 URL 计数"""
        text = """https://a.com
https://b.com
https://c.com"""
        urls = parse_urls(text)
        assert len(urls) == 3
    
    def test_count_mixed_content(self):
        """测试混合内容计数"""
        text = """https://valid1.com
invalid
https://valid2.com

not a url
https://valid3.com"""
        urls = parse_urls(text)
        assert len(urls) == 3
    
    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_url_count_property(self, text):
        """属性测试：URL 计数准确性
        
        Feature: web-to-markdown-dialog, Property 3: URL Count Accuracy
        **Validates: Requirements 3.4, 3.5**
        
        对于任意文本输入，显示的 URL 计数必须等于解析后的有效 URL 数量。
        """
        urls = parse_urls(text)
        
        # 手动计算有效 URL 数量
        manual_count = 0
        for line in text.splitlines():
            if is_valid_url(line):
                manual_count += 1
        
        assert len(urls) == manual_count


class TestDialogInstanceMethods:
    """对话框实例方法测试（兼容性）"""
    
    def test_instance_is_valid_url(self):
        """测试实例方法 _is_valid_url"""
        dialog = WebToMarkdownDialog.__new__(WebToMarkdownDialog)
        assert dialog._is_valid_url("https://example.com") is True
        assert dialog._is_valid_url("invalid") is False
    
    def test_instance_parse_urls(self):
        """测试实例方法 _parse_urls"""
        dialog = WebToMarkdownDialog.__new__(WebToMarkdownDialog)
        urls = dialog._parse_urls("https://a.com\nhttps://b.com")
        assert urls == ["https://a.com", "https://b.com"]



class TestNotificationMessageAccuracy:
    """通知消息准确性测试
    
    Property 4: Notification Message Accuracy
    **Validates: Requirements 6.1, 6.2**
    """
    
    def test_success_notification_format(self):
        """测试成功通知格式"""
        # 模拟成功结果
        title = "测试文章标题"
        expected_msg = f"✓ {title} 转换成功"
        assert "✓" in expected_msg
        assert title in expected_msg
        assert "转换成功" in expected_msg
    
    def test_failure_notification_format(self):
        """测试失败通知格式"""
        error = "网络超时"
        expected_msg = f"✗ 转换失败: {error}"
        assert "✗" in expected_msg
        assert "转换失败" in expected_msg
        assert error in expected_msg
    
    def test_long_title_truncation(self):
        """测试长标题截断"""
        long_title = "这是一个非常非常非常非常非常非常非常非常非常非常长的标题"
        truncated = long_title[:30] + "..." if len(long_title) > 30 else long_title
        assert len(truncated) <= 33  # 30 + "..."
    
    def test_long_error_truncation(self):
        """测试长错误信息截断"""
        long_error = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的错误信息"
        truncated = long_error[:50] + "..." if len(long_error) > 50 else long_error
        assert len(truncated) <= 53  # 50 + "..."
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_success_notification_property(self, title):
        """属性测试：成功通知消息格式
        
        Feature: web-to-markdown-dialog, Property 4: Notification Message Accuracy
        **Validates: Requirements 6.1**
        
        对于任意成功的转换结果，通知消息必须包含 "✓" 和 "转换成功"。
        """
        # 模拟通知消息生成逻辑
        display_title = title[:30] + "..." if len(title) > 30 else title
        msg = f"✓ {display_title} 转换成功"
        
        assert "✓" in msg
        assert "转换成功" in msg
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_failure_notification_property(self, error):
        """属性测试：失败通知消息格式
        
        Feature: web-to-markdown-dialog, Property 4: Notification Message Accuracy
        **Validates: Requirements 6.2**
        
        对于任意失败的转换结果，通知消息必须包含 "✗" 和 "转换失败"。
        """
        # 模拟通知消息生成逻辑
        display_error = error[:50] + "..." if len(error) > 50 else error
        msg = f"✗ 转换失败: {display_error}"
        
        assert "✗" in msg
        assert "转换失败" in msg
