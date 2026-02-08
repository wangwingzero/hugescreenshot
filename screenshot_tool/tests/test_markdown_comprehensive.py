# =====================================================
# =============== Markdown 转换综合测试 ===============
# =====================================================

"""
Markdown 转换综合测试 - 测试多种类型的网站

这是一个手动运行的测试脚本，用于测试真实网站的 Markdown 转换效果。
运行方式: python -m screenshot_tool.tests.test_markdown_comprehensive

Feature: batch-url-markdown
"""

import os
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class UrlTestResult:
    """URL 测试结果（避免与 pytest 的 TestResult 冲突）"""
    url: str
    success: bool
    content_length: int = 0
    title: str = ""
    error: str = ""
    time_seconds: float = 0.0


# 测试 URL 列表 - 按类别分组
TEST_URLS = {
    "技术博客": [
        "https://www.ruanyifeng.com/blog/2024/01/weekly-issue-285.html",
        "https://coolshell.cn/articles/22298.html",
        "https://blog.csdn.net/qq_41854911/article/details/121375260",
        "https://www.zhihu.com/question/19732473/answer/241673170",
        "https://juejin.cn/post/7000000000000000000",  # 可能失败
    ],
    "官方文档": [
        "https://docs.python.org/3/tutorial/index.html",
        "https://docs.python.org/3/library/functions.html",
        "https://peps.python.org/pep-0008/",
        "https://doc.qt.io/qtforpython-6/quickstart.html",
    ],
    "GitHub": [
        "https://github.com/python/cpython",
        "https://github.com/microsoft/vscode/blob/main/README.md",
        "https://raw.githubusercontent.com/python/cpython/main/README.rst",
    ],
    "新闻网站": [
        "https://www.theverge.com/",
        "https://arstechnica.com/",
        "https://www.wired.com/",
    ],
    "中文网站": [
        "https://www.163.com/",
        "https://www.sina.com.cn/",
        "https://www.qq.com/",
        "https://www.baidu.com/",
    ],
    "维基百科": [
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://zh.wikipedia.org/wiki/Python",
    ],
    "Stack Overflow": [
        "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python",
    ],
    "其他": [
        "https://httpbin.org/html",  # 简单测试页面
        "https://example.com/",  # 最简单的测试页面
    ],
}


def run_comprehensive_test():
    """运行综合测试"""
    from screenshot_tool.core.config_manager import MarkdownConfig
    from screenshot_tool.services.markdown_converter import MarkdownConverter
    
    # 创建临时配置
    config = MarkdownConfig()
    config.save_dir = os.path.join(os.path.dirname(__file__), "test_output")
    
    # 确保输出目录存在
    os.makedirs(config.save_dir, exist_ok=True)
    
    converter = MarkdownConverter(config)
    
    results: List[UrlTestResult] = []
    
    print("=" * 70)
    print("Markdown 转换综合测试")
    print("=" * 70)
    
    total_urls = sum(len(urls) for urls in TEST_URLS.values())
    current = 0
    
    for category, urls in TEST_URLS.items():
        print(f"\n📁 {category}")
        print("-" * 50)
        
        for url in urls:
            current += 1
            print(f"  [{current}/{total_urls}] 测试: {url[:60]}...")
            
            start_time = time.time()
            try:
                result = converter.convert(url)
                elapsed = time.time() - start_time
                
                if result.success:
                    test_result = UrlTestResult(
                        url=url,
                        success=True,
                        content_length=len(result.markdown),
                        title=result.title,
                        time_seconds=elapsed
                    )
                    print(f"      ✓ 成功 - {len(result.markdown)} 字符, {elapsed:.2f}s")
                else:
                    test_result = UrlTestResult(
                        url=url,
                        success=False,
                        error=result.error,
                        time_seconds=elapsed
                    )
                    print(f"      ✗ 失败 - {result.error}")
                    
            except Exception as e:
                elapsed = time.time() - start_time
                test_result = UrlTestResult(
                    url=url,
                    success=False,
                    error=str(e),
                    time_seconds=elapsed
                )
                print(f"      ✗ 异常 - {e}")
            
            results.append(test_result)
            
            # 避免请求过快
            time.sleep(0.5)
    
    # 打印统计
    print("\n" + "=" * 70)
    print("测试统计")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count
    
    print(f"\n总计: {len(results)} 个 URL")
    print(f"成功: {success_count} ({success_count/len(results)*100:.1f}%)")
    print(f"失败: {failure_count} ({failure_count/len(results)*100:.1f}%)")
    
    if failure_count > 0:
        print("\n失败的 URL:")
        for r in results:
            if not r.success:
                print(f"  - {r.url}")
                print(f"    错误: {r.error}")
    
    # 按内容长度排序成功的结果
    successful = [r for r in results if r.success]
    if successful:
        print("\n成功转换的内容长度排名:")
        successful.sort(key=lambda x: x.content_length, reverse=True)
        for i, r in enumerate(successful[:10], 1):
            print(f"  {i}. {r.content_length:,} 字符 - {r.url[:50]}...")
    
    return results


if __name__ == "__main__":
    run_comprehensive_test()
