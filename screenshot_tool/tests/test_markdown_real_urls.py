# =====================================================
# =============== 真实 URL 转换测试 ===============
# =====================================================

"""
真实 URL 转换测试 - 测试多种类型网站的 Markdown 转换效果

这个测试文件用于验证 Markdown 转换功能在各种真实网站上的效果。
运行方式: pytest screenshot_tool/tests/test_markdown_real_urls.py -v -s

Feature: batch-url-markdown
"""

import os
import tempfile
import pytest
from dataclasses import dataclass
from typing import List, Tuple

# 测试 URL 列表 - 覆盖多种类型的网站
TEST_URLS = [
    # 技术博客
    ("https://blog.rust-lang.org/", "Rust Blog"),
    ("https://go.dev/blog/", "Go Blog"),
    
    # 新闻网站
    ("https://www.bbc.com/news", "BBC News"),
    
    # 文档网站
    ("https://docs.python.org/3/tutorial/index.html", "Python Tutorial"),
    
    # GitHub
    ("https://github.com/microsoft/vscode", "VS Code GitHub"),
    
    # 维基百科
    ("https://en.wikipedia.org/wiki/Python_(programming_language)", "Wikipedia Python"),
    
    # 技术文章
    ("https://martinfowler.com/articles/injection.html", "Martin Fowler"),
]


@dataclass
class UrlConversionResult:
    """URL 转换测试结果（避免与 pytest 的 TestResult 冲突）"""
    url: str
    name: str
    success: bool
    content_length: int = 0
    title: str = ""
    error: str = ""


class TestMarkdownConversion:
    """真实 URL 转换测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def mock_config(self, temp_dir):
        """创建模拟配置"""
        class MockConfig:
            def __init__(self, save_dir):
                self.save_dir = save_dir
                self.include_images = True
                self.include_links = True
                self.timeout = 30
            
            def get_save_dir(self):
                return self.save_dir
        
        return MockConfig(temp_dir)
    
    def test_url_validation(self):
        """测试 URL 验证"""
        from screenshot_tool.ui.batch_url_dialog import BatchUrlDialog
        
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        
        for url, name in TEST_URLS:
            assert dialog._is_valid_url(url), f"URL should be valid: {url}"
    
    def test_url_parsing(self):
        """测试 URL 解析"""
        from screenshot_tool.ui.batch_url_dialog import BatchUrlDialog
        
        dialog = BatchUrlDialog.__new__(BatchUrlDialog)
        
        # 构建多行文本
        text = "\n".join([url for url, _ in TEST_URLS])
        parsed = dialog._parse_urls(text)
        
        assert len(parsed) == len(TEST_URLS)
        for i, (url, _) in enumerate(TEST_URLS):
            assert parsed[i] == url
    
    @pytest.mark.skip(reason="需要网络连接，手动运行")
    def test_single_url_conversion(self, mock_config):
        """测试单个 URL 转换（需要网络）"""
        from screenshot_tool.services.markdown_converter import MarkdownConverter
        
        converter = MarkdownConverter(mock_config)
        
        # 测试一个简单的 URL
        url = "https://example.com"
        result = converter.convert(url)
        
        print(f"\nURL: {url}")
        print(f"Success: {result.success}")
        print(f"Title: {result.title}")
        print(f"Content length: {len(result.markdown)}")
        if result.error:
            print(f"Error: {result.error}")
    
    @pytest.mark.skip(reason="需要网络连接，手动运行")
    def test_batch_conversion(self, mock_config):
        """测试批量 URL 转换（需要网络）"""
        from screenshot_tool.services.markdown_converter import MarkdownConverter
        
        converter = MarkdownConverter(mock_config)
        results: List[UrlConversionResult] = []
        
        for url, name in TEST_URLS:
            print(f"\n正在测试: {name} ({url})")
            
            try:
                result = converter.convert(url)
                test_result = UrlConversionResult(
                    url=url,
                    name=name,
                    success=result.success,
                    content_length=len(result.markdown) if result.markdown else 0,
                    title=result.title,
                    error=result.error
                )
            except Exception as e:
                test_result = UrlConversionResult(
                    url=url,
                    name=name,
                    success=False,
                    error=str(e)
                )
            
            results.append(test_result)
            
            # 打印结果
            status = "✓" if test_result.success else "✗"
            print(f"  {status} 标题: {test_result.title}")
            print(f"    内容长度: {test_result.content_length} 字符")
            if test_result.error:
                print(f"    错误: {test_result.error}")
        
        # 打印摘要
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        
        print(f"\n{'='*60}")
        print(f"测试摘要: {success_count} 成功, {failure_count} 失败")
        print(f"{'='*60}")
        
        # 打印失败的 URL
        if failure_count > 0:
            print("\n失败的 URL:")
            for r in results:
                if not r.success:
                    print(f"  - {r.name}: {r.error}")


# 用于手动运行的测试函数
def run_manual_test():
    """手动运行测试"""
    import tempfile
    from screenshot_tool.services.markdown_converter import MarkdownConverter
    
    class MockConfig:
        def __init__(self, save_dir):
            self.save_dir = save_dir
            self.include_images = True
            self.include_links = True
            self.timeout = 30
        
        def get_save_dir(self):
            return self.save_dir
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MockConfig(tmpdir)
        converter = MarkdownConverter(config)
        
        results = []
        
        for url, name in TEST_URLS:
            print(f"\n正在测试: {name}")
            print(f"  URL: {url}")
            
            try:
                result = converter.convert(url)
                success = result.success
                content_len = len(result.markdown) if result.markdown else 0
                title = result.title
                error = result.error
            except Exception as e:
                success = False
                content_len = 0
                title = ""
                error = str(e)
            
            results.append({
                "url": url,
                "name": name,
                "success": success,
                "content_length": content_len,
                "title": title,
                "error": error
            })
            
            status = "✓" if success else "✗"
            print(f"  {status} 标题: {title}")
            print(f"    内容长度: {content_len} 字符")
            if error:
                print(f"    错误: {error}")
        
        # 打印摘要
        success_count = sum(1 for r in results if r["success"])
        failure_count = len(results) - success_count
        
        print(f"\n{'='*60}")
        print(f"测试摘要: {success_count} 成功, {failure_count} 失败")
        print(f"{'='*60}")
        
        return results


if __name__ == "__main__":
    run_manual_test()
