# =====================================================
# =============== Markdown 转换器测试 ===============
# =====================================================

"""
Markdown 转换器属性测试

Feature: web-to-markdown
Property 3: Filename Sanitization
Property 4: Duplicate Filename Handling
Property 5: Markdown Output Validity
Validates: Requirements 3.1, 3.3, 4.2, 4.3
"""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.core.config_manager import MarkdownConfig
from screenshot_tool.services.markdown_converter import MarkdownConverter, ConversionResult


def create_converter():
    """创建测试用的转换器（用于 hypothesis 测试）"""
    config = MarkdownConfig(
        save_dir="",
        include_images=True,
        include_links=True,
        timeout=30
    )
    return MarkdownConverter(config)


@pytest.fixture
def markdown_config():
    """创建测试用的 Markdown 配置"""
    return MarkdownConfig(
        save_dir="",
        include_images=True,
        include_links=True,
        timeout=30
    )


@pytest.fixture
def converter(markdown_config):
    """创建测试用的转换器"""
    return MarkdownConverter(markdown_config)


class TestFilenameSanitization:
    """Property 3: Filename Sanitization 测试
    
    *For any* string input as title, the `_sanitize_filename` function SHALL return 
    a string containing only valid filename characters (alphanumeric, spaces, hyphens, 
    underscores, Chinese characters) with a maximum length of 100 characters.
    
    **Validates: Requirements 4.2**
    """
    
    # 非法文件名字符
    INVALID_CHARS = '<>:"/\\|?*'
    
    @given(st.text(min_size=0, max_size=300))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_filename_no_invalid_chars(self, title):
        """Feature: web-to-markdown, Property 3: Filename Sanitization
        
        验证清理后的文件名不包含非法字符
        """
        converter = create_converter()
        result = converter._sanitize_filename(title)
        
        # 结果不包含非法字符
        for char in self.INVALID_CHARS:
            assert char not in result, f"文件名包含非法字符: {char}"
    
    @given(st.text(min_size=0, max_size=300))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_filename_max_length(self, title):
        """Feature: web-to-markdown, Property 3: Filename Sanitization
        
        验证清理后的文件名长度不超过 100
        """
        converter = create_converter()
        result = converter._sanitize_filename(title)
        
        # 结果长度不超过 100
        assert len(result) <= 100, f"文件名长度超过 100: {len(result)}"
    
    @given(st.text(min_size=0, max_size=300))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_filename_non_empty(self, title):
        """Feature: web-to-markdown, Property 3: Filename Sanitization
        
        验证清理后的文件名非空（至少有 "untitled"）
        """
        converter = create_converter()
        result = converter._sanitize_filename(title)
        
        # 结果非空
        assert len(result) > 0, "文件名为空"
    
    def test_sanitize_filename_examples(self, converter):
        """具体示例测试"""
        # 正常标题
        assert converter._sanitize_filename("Hello World") == "Hello World"
        
        # 包含非法字符
        assert converter._sanitize_filename("Test<>File") == "TestFile"
        assert converter._sanitize_filename('File:Name/Path') == "FileNamePath"
        
        # 空字符串
        assert converter._sanitize_filename("") == "untitled"
        assert converter._sanitize_filename("   ") == "untitled"
        
        # 只有非法字符
        assert converter._sanitize_filename("<>:") == "untitled"
        
        # 中文标题
        assert converter._sanitize_filename("测试文章标题") == "测试文章标题"
        
        # 超长标题
        long_title = "A" * 200
        result = converter._sanitize_filename(long_title)
        assert len(result) <= 100


class TestDuplicateFilenameHandling:
    """Property 4: Duplicate Filename Handling 测试
    
    *For any* directory and base filename, if a file with that name already exists, 
    the `_get_unique_filepath` function SHALL return a path with a numeric suffix 
    (e.g., "title (1).md", "title (2).md") that does not exist.
    
    **Validates: Requirements 4.3**
    """
    
    @given(st.text(alphabet=st.characters(whitelist_categories=('L', 'N')), min_size=1, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unique_filepath_when_exists(self, base_name):
        """Feature: web-to-markdown, Property 4: Duplicate Filename Handling
        
        验证当文件存在时，返回唯一路径
        """
        converter = create_converter()
        with tempfile.TemporaryDirectory() as tmpdir:
            # 清理文件名
            safe_name = converter._sanitize_filename(base_name)
            filename = f"{safe_name}.md"
            existing_path = os.path.join(tmpdir, filename)
            
            # 创建已存在的文件
            Path(existing_path).touch()
            
            # 获取唯一路径
            result = converter._get_unique_filepath(tmpdir, filename)
            
            # 结果路径不等于已存在的路径
            assert result != existing_path, "返回的路径与已存在的路径相同"
            
            # 结果路径不存在
            assert not os.path.exists(result), "返回的路径已存在"
    
    def test_unique_filepath_no_conflict(self, converter):
        """当文件不存在时，直接返回原路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = "test_file.md"
            result = converter._get_unique_filepath(tmpdir, filename)
            
            expected = os.path.join(tmpdir, filename)
            assert result == expected
    
    def test_unique_filepath_multiple_conflicts(self, converter):
        """多个冲突文件时，正确递增后缀"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = "test.md"
            
            # 创建多个冲突文件
            Path(os.path.join(tmpdir, "test.md")).touch()
            Path(os.path.join(tmpdir, "test (1).md")).touch()
            Path(os.path.join(tmpdir, "test (2).md")).touch()
            
            result = converter._get_unique_filepath(tmpdir, filename)
            
            # 应该返回 test (3).md
            expected = os.path.join(tmpdir, "test (3).md")
            assert result == expected
            assert not os.path.exists(result)


class TestConversionResult:
    """ConversionResult 数据类测试"""
    
    def test_success_result(self):
        """成功结果"""
        result = ConversionResult(
            success=True,
            markdown="# Test",
            title="Test Title",
            file_path="/path/to/file.md"
        )
        assert result.success is True
        assert result.markdown == "# Test"
        assert result.title == "Test Title"
        assert result.error == ""
    
    def test_failure_result(self):
        """失败结果"""
        result = ConversionResult(
            success=False,
            error="无法访问该网页"
        )
        assert result.success is False
        assert result.markdown == ""
        assert result.error == "无法访问该网页"


class TestFilenameFromUrl:
    """URL 生成文件名测试
    
    当标题提取失败时，使用 URL 的域名和路径生成文件名。
    
    **Validates: Requirements 4.2**
    """
    
    def test_simple_domain(self, converter):
        """简单域名"""
        result = converter._generate_filename_from_url("https://example.com")
        assert result == "example.com"
    
    def test_domain_with_path(self, converter):
        """域名带路径"""
        result = converter._generate_filename_from_url("https://news.sina.com.cn/china/")
        assert result == "news.sina.com.cn_china"
    
    def test_domain_with_deep_path(self, converter):
        """域名带深层路径"""
        result = converter._generate_filename_from_url("https://example.com/path/to/page")
        assert result == "example.com_path_to_page"
    
    def test_domain_with_trailing_slash(self, converter):
        """域名带尾部斜杠"""
        result = converter._generate_filename_from_url("https://example.com/")
        assert result == "example.com"
    
    def test_subdomain(self, converter):
        """子域名"""
        result = converter._generate_filename_from_url("https://blog.example.com/post")
        assert result == "blog.example.com_post"
    
    def test_invalid_url(self, converter):
        """无效 URL 返回默认值"""
        result = converter._generate_filename_from_url("")
        assert result == "webpage"
    
    def test_none_like_url(self, converter):
        """空白 URL 返回默认值"""
        result = converter._generate_filename_from_url("   ")
        assert result == "webpage"
    
    def test_url_with_query_params(self, converter):
        """URL 带查询参数（只使用路径部分）"""
        result = converter._generate_filename_from_url("https://example.com/page?id=123")
        assert result == "example.com_page"
    
    def test_url_with_html_extension(self, converter):
        """URL 带 .html 扩展名（应移除）"""
        result = converter._generate_filename_from_url("https://example.com/article.html")
        assert result == "example.com_article"
    
    def test_url_with_php_extension(self, converter):
        """URL 带 .php 扩展名（应移除）"""
        result = converter._generate_filename_from_url("https://example.com/index.php")
        assert result == "example.com_index"
    
    def test_url_with_encoded_chars(self, converter):
        """URL 带编码字符（应解码）"""
        result = converter._generate_filename_from_url("https://example.com/hello%20world")
        assert result == "example.com_hello world"
    
    def test_url_with_chinese_path(self, converter):
        """URL 带中文路径（编码后）"""
        # %E6%96%87%E7%AB%A0 是 "文章" 的 URL 编码
        result = converter._generate_filename_from_url("https://example.com/%E6%96%87%E7%AB%A0")
        assert result == "example.com_文章"
    
    @given(st.from_regex(r'https?://[a-z0-9.-]+(/[a-z0-9/_-]*)?', fullmatch=True))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_url_generates_valid_filename(self, url):
        """Feature: web-to-markdown, Property: URL Filename Generation
        
        验证从 URL 生成的文件名是有效的
        """
        converter = create_converter()
        result = converter._generate_filename_from_url(url)
        
        # 结果非空
        assert len(result) > 0, "文件名为空"
        
        # 结果不包含非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            assert char not in result, f"文件名包含非法字符: {char}"
        
        # 结果长度不超过 100
        assert len(result) <= 100, f"文件名长度超过 100: {len(result)}"


class TestMarkdownConfig:
    """MarkdownConfig 配置测试"""
    
    def test_default_values(self):
        """默认值测试"""
        config = MarkdownConfig()
        assert config.save_dir == ""
        assert config.include_images is True
        assert config.include_links is True
        assert config.timeout == 30
    
    def test_get_save_dir_default(self):
        """默认保存目录"""
        config = MarkdownConfig()
        save_dir = config.get_save_dir()
        
        expected = os.path.join(os.path.expanduser("~"), "Documents", "Markdown")
        assert save_dir == expected
    
    def test_get_save_dir_custom(self):
        """自定义保存目录"""
        config = MarkdownConfig(save_dir="/custom/path")
        assert config.get_save_dir() == "/custom/path"
    
    def test_timeout_validation(self):
        """超时值验证"""
        # 正常值
        config = MarkdownConfig(timeout=60)
        assert config.timeout == 60
        
        # 超出范围 - 应该被限制
        config = MarkdownConfig(timeout=1)  # 小于最小值
        assert config.timeout == 5  # 被限制到最小值
        
        config = MarkdownConfig(timeout=200)  # 大于最大值
        assert config.timeout == 120  # 被限制到最大值
