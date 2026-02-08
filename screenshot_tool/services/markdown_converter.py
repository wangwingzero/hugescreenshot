# =====================================================
# =============== Markdown 转换服务 ===============
# =====================================================

"""
Markdown 转换服务 - 网页转 Markdown 的核心服务模块

使用 Trafilatura 获取网页内容，提取正文并转换为 Markdown，
生成安全文件名，保存到配置目录，复制到剪贴板。

Feature: web-to-markdown
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5
"""

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple, Optional, Any, Set

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import MarkdownConfig


@dataclass
class ConversionResult:
    """转换结果数据类
    
    Feature: web-to-markdown
    Requirements: 3.1, 3.3
    """
    success: bool
    markdown: str = ""
    title: str = ""
    file_path: str = ""
    error: str = ""
    used_browser: bool = False  # 是否使用了浏览器模式


class MarkdownConverter:
    """网页转 Markdown 转换器
    
    使用 Trafilatura 获取网页内容，提取正文并转换为 Markdown。
    
    Feature: web-to-markdown
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.5
    """
    
    # 文件名非法字符
    INVALID_FILENAME_CHARS = r'<>:"/\\|?*'
    # 文件名最大长度
    MAX_FILENAME_LENGTH = 100
    
    # 需要浏览器模式的域名（反爬虫网站）
    # 这些网站会直接使用浏览器模式，跳过 HTTP 尝试
    BROWSER_REQUIRED_DOMAINS = {
        # 知乎
        'zhihu.com', 'zhuanlan.zhihu.com',
        # CSDN
        'csdn.net', 'blog.csdn.net',
        # 简书
        'jianshu.com',
        # 掘金
        'juejin.cn',
        # SegmentFault
        'segmentfault.com',
        # 微信公众号
        'mp.weixin.qq.com',
        # 今日头条
        'toutiao.com',
        # 百度百家号
        'baijiahao.baidu.com',
        # 豆瓣
        'douban.com',
        # 雪球
        'xueqiu.com',
        # Stack Overflow（返回 403）
        'stackoverflow.com',
    }
    
    # HTTP 模式内容质量阈值（字符数）
    # 低于此值会自动尝试浏览器模式以获取更完整内容
    MIN_CONTENT_LENGTH = 200
    
    # 学习到的反爬虫域名文件名
    LEARNED_DOMAINS_FILENAME = "learned_browser_domains.json"
    
    def __init__(self, config: "MarkdownConfig"):
        """初始化转换器
        
        Args:
            config: Markdown 配置对象
        """
        self.config = config
        self._browser_fetcher = None
        self._learned_domains: Optional[Set[str]] = None  # 懒加载
    
    def _get_learned_domains_path(self) -> str:
        """获取学习域名列表文件路径
        
        Returns:
            学习域名列表文件的完整路径
        """
        from screenshot_tool.core.config_manager import get_app_dir
        return os.path.join(get_app_dir(), self.LEARNED_DOMAINS_FILENAME)
    
    def _load_learned_domains(self) -> Set[str]:
        """加载学习到的反爬虫域名列表
        
        Returns:
            域名集合
        """
        if self._learned_domains is not None:
            return self._learned_domains
        
        self._learned_domains = set()
        filepath = self._get_learned_domains_path()
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._learned_domains = set(data)
                        _debug_log(f"加载学习域名列表: {len(self._learned_domains)} 个域名", "MARKDOWN")
            except Exception as e:
                _debug_log(f"加载学习域名列表失败: {e}", "MARKDOWN")
        
        return self._learned_domains
    
    def _save_learned_domain(self, domain: str) -> None:
        """保存新学习到的反爬虫域名
        
        Args:
            domain: 域名（如 stackoverflow.com）
        """
        # 确保已加载
        domains = self._load_learned_domains()
        
        # 如果已存在，不重复保存
        if domain in domains:
            return
        
        # 添加新域名
        domains.add(domain)
        
        # 保存到文件
        filepath = self._get_learned_domains_path()
        try:
            # 确保目录存在
            dir_path = os.path.dirname(filepath)
            if dir_path:  # 避免空字符串导致的错误
                os.makedirs(dir_path, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(sorted(list(domains)), f, ensure_ascii=False, indent=2)
            
            _debug_log(f"已学习新的反爬虫域名: {domain}", "MARKDOWN")
        except Exception as e:
            _debug_log(f"保存学习域名失败: {e}", "MARKDOWN")
    
    def _needs_browser_mode(self, url: str) -> bool:
        """判断是否需要浏览器模式
        
        检查内置反爬虫列表和学习到的反爬虫列表。
        
        Args:
            url: 网页 URL
            
        Returns:
            是否需要浏览器模式
        """
        from urllib.parse import urlparse
        
        try:
            domain = urlparse(url).netloc.lower()
            
            # 检查内置列表
            for browser_domain in self.BROWSER_REQUIRED_DOMAINS:
                if browser_domain in domain:
                    return True
            
            # 检查学习列表
            learned_domains = self._load_learned_domains()
            for learned_domain in learned_domains:
                if learned_domain in domain:
                    _debug_log(f"命中学习列表: {learned_domain}", "MARKDOWN")
                    return True
            
            return False
        except Exception:
            return False
    
    def _extract_domain(self, url: str) -> str:
        """从 URL 提取主域名
        
        例如：https://www.example.com/path -> example.com
        
        Args:
            url: 网页 URL
            
        Returns:
            主域名
        """
        from urllib.parse import urlparse
        
        try:
            netloc = urlparse(url).netloc.lower()
            
            # 移除 www. 前缀
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            
            # 处理子域名，保留主域名
            # 例如：blog.example.com -> example.com
            # 但保留特殊情况：github.io, blogspot.com 等
            parts = netloc.split('.')
            if len(parts) > 2:
                # 检查是否是特殊的二级域名
                special_tlds = {'co.uk', 'com.cn', 'org.cn', 'net.cn', 'gov.cn',
                               'github.io', 'blogspot.com', 'wordpress.com'}
                last_two = '.'.join(parts[-2:])
                if last_two in special_tlds:
                    # 保留三级域名
                    return '.'.join(parts[-3:]) if len(parts) > 2 else netloc
                else:
                    # 只保留主域名
                    return '.'.join(parts[-2:])
            
            return netloc
        except Exception:
            return ""
    
    def _get_browser_fetcher(self) -> Optional[Any]:
        """获取浏览器获取器（懒加载）
        
        Returns:
            BrowserFetcher 实例或 None
        """
        if self._browser_fetcher is None:
            try:
                from screenshot_tool.services.browser_fetcher import BrowserFetcher
                if BrowserFetcher.is_available():
                    self._browser_fetcher = BrowserFetcher(
                        timeout=getattr(self.config, 'timeout', 30)
                    )
            except ImportError:
                _debug_log("browser_fetcher 模块不可用", "MARKDOWN")
        return self._browser_fetcher

    def convert(self, url: str, force_browser: bool = False, save_dir: str = "") -> ConversionResult:
        """转换网页为 Markdown
        
        优先级策略（v1.12.0 更新）：
        1. 纯文本文件（.md/.rst/.txt）→ 直接返回原内容
        2. 所有网页 → 使用 Playwright 浏览器模式提取（效果最好）
        3. Playwright 不可用时 → 降级到 HTTP + trafilatura
        
        Args:
            url: 网页 URL
            force_browser: 已废弃，现在默认使用浏览器模式
            save_dir: 自定义保存目录，为空则使用配置中的目录
            
        Returns:
            ConversionResult 包含转换结果
            
        Requirements: 3.1, 3.3, 4.1, 4.5, 5.1, 5.2, 5.3
        """
        _debug_log(f"开始转换网页: {url}", "MARKDOWN")
        
        used_browser = False
        
        try:
            # 策略 1: 纯文本文件直接返回
            if self._is_raw_text_url(url):
                _debug_log("检测到纯文本文件，直接获取原内容", "MARKDOWN")
                markdown, title = self._fetch_raw_text(url)
                if markdown:
                    return self._save_and_return(url, markdown, title, used_browser=False, save_dir=save_dir)
            
            # 策略 2: 优先使用 Playwright 浏览器模式（效果最好）
            browser_fetcher = self._get_browser_fetcher()
            if browser_fetcher:
                _debug_log("使用 Playwright 浏览器模式提取内容", "MARKDOWN")
                try:
                    markdown, title = self._fetch_with_playwright(url, browser_fetcher)
                    used_browser = True
                    if markdown and len(markdown) >= self.MIN_CONTENT_LENGTH:
                        return self._save_and_return(url, markdown, title, used_browser=True, save_dir=save_dir)
                    else:
                        _debug_log(f"Playwright 提取内容较少（{len(markdown) if markdown else 0} 字符），尝试 trafilatura 降级", "MARKDOWN")
                except Exception as e:
                    _debug_log(f"Playwright 模式失败: {e}，尝试降级", "MARKDOWN")
            else:
                _debug_log("Playwright 不可用，使用 HTTP + trafilatura 降级模式", "MARKDOWN")
            
            # 策略 3: 降级到 HTTP + trafilatura
            _debug_log("使用 HTTP + trafilatura 降级模式", "MARKDOWN")
            try:
                http_markdown, http_title = self._fetch_and_extract(url)
                if http_markdown and len(http_markdown) >= self.MIN_CONTENT_LENGTH:
                    return self._save_and_return(url, http_markdown, http_title, used_browser=False, save_dir=save_dir)
            except Exception as http_error:
                _debug_log(f"HTTP 模式也失败: {http_error}", "MARKDOWN")
            
            # 所有方式都失败
            _debug_log("所有获取方式都失败", "MARKDOWN")
            return ConversionResult(success=False, error="未能提取到有效内容")
            
        except Exception as e:
            error_msg = str(e)
            _debug_log(f"Markdown 转换异常: {error_msg}", "MARKDOWN")
            
            # 识别特定错误类型
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return ConversionResult(success=False, error="网络超时，请稍后重试")
            elif "connection" in error_msg.lower() or "unreachable" in error_msg.lower():
                return ConversionResult(success=False, error="无法访问该网页")
            else:
                return ConversionResult(success=False, error=f"转换失败: {error_msg}")
    
    def _save_and_return(self, url: str, markdown: str, title: str, used_browser: bool, save_dir: str = "") -> ConversionResult:
        """保存内容并返回结果
        
        Args:
            url: 原始 URL
            markdown: Markdown 内容
            title: 标题
            used_browser: 是否使用了浏览器模式
            save_dir: 自定义保存目录，为空则使用配置中的目录
            
        Returns:
            ConversionResult
        """
        # 获取保存目录（优先使用传入的目录）
        if save_dir:
            actual_save_dir = save_dir
        else:
            actual_save_dir = self.config.get_save_dir()
        
        # 确保目录存在
        if not os.path.exists(actual_save_dir):
            os.makedirs(actual_save_dir, exist_ok=True)
            _debug_log(f"创建保存目录: {actual_save_dir}", "MARKDOWN")
        
        # 生成文件名
        if title == "untitled" or not title.strip():
            filename = self._generate_filename_from_url(url) + ".md"
            _debug_log(f"标题为空，使用 URL 生成文件名: {filename}", "MARKDOWN")
        else:
            filename = self._sanitize_filename(title) + ".md"
        filepath = self._get_unique_filepath(actual_save_dir, filename)
        
        # 保存文件
        self._save_to_file(markdown, filepath)
        _debug_log(f"文件已保存: {filepath}", "MARKDOWN")
        
        # 复制到剪贴板
        self._copy_to_clipboard(markdown)
        _debug_log("内容已复制到剪贴板", "MARKDOWN")
        
        return ConversionResult(
            success=True,
            markdown=markdown,
            title=title,
            file_path=filepath,
            used_browser=used_browser
        )
    
    def _fetch_raw_text(self, url: str) -> Tuple[str, str]:
        """获取纯文本文件内容
        
        Args:
            url: 文件 URL
            
        Returns:
            (content, title) 元组
            
        Raises:
            ConnectionError: 网络请求失败
            requests.RequestException: HTTP 请求异常
        """
        import requests
        
        _debug_log(f"获取纯文本文件: {url}", "MARKDOWN")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        timeout = getattr(self.config, 'timeout', 30)
        
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            _debug_log(f"纯文本获取失败: {e}", "MARKDOWN")
            raise ConnectionError(f"无法获取文件: {e}")
        
        # 处理编码（安全检查 response.encoding）
        encoding = response.encoding
        if encoding and encoding.lower() != 'utf-8':
            response.encoding = response.apparent_encoding or 'utf-8'
        
        content = response.text
        title = self._extract_title_from_content(url, content)
        
        _debug_log(f"纯文本获取成功: {len(content)} 字符, 标题: {title}", "MARKDOWN")
        return content, title
    
    def _extract_title_from_content(self, url: str, content: str) -> str:
        """从内容中提取标题
        
        Args:
            url: 文件 URL
            content: 文件内容
            
        Returns:
            提取的标题
        """
        title = self._generate_title_from_url(url)
        
        # 如果是 Markdown 文件，尝试从第一行提取标题
        if url.lower().endswith(('.md', '.markdown')):
            lines = content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
        
        return title
    
    def _fetch_with_browser(self, url: str, browser_fetcher: Any) -> Tuple[str, str]:
        """使用浏览器模式获取并提取内容（旧方法，使用 trafilatura）
        
        Args:
            url: 网页 URL
            browser_fetcher: 浏览器获取器实例
            
        Returns:
            (markdown_content, title) 元组
            
        Raises:
            ConnectionError: 浏览器获取失败
        """
        import trafilatura
        
        _debug_log(f"浏览器模式获取（trafilatura）: {url}", "MARKDOWN")
        
        # 使用浏览器获取 HTML
        result = browser_fetcher.fetch(url, use_cookies=True)
        
        if not result.success:
            raise ConnectionError(f"浏览器获取失败: {result.error}")
        
        html = result.html
        title = result.title or "untitled"
        
        _debug_log(f"浏览器获取成功: {len(html)} 字符, 标题: {title}", "MARKDOWN")
        
        # 使用 trafilatura 提取正文
        markdown = trafilatura.extract(
            html,
            output_format='markdown',
            include_images=self.config.include_images,
            include_links=self.config.include_links,
            include_tables=True,
            include_comments=False,
            favor_recall=True,
        )
        
        if not markdown:
            # 尝试默认模式
            markdown = trafilatura.extract(
                html,
                output_format='markdown',
                include_images=self.config.include_images,
                include_links=self.config.include_links,
                include_tables=True,
                include_comments=False,
            )
        
        if not markdown:
            _debug_log("trafilatura 提取失败", "MARKDOWN")
            return "", title
        
        _debug_log(f"提取内容长度: {len(markdown)} 字符", "MARKDOWN")
        return markdown, title
    
    def _fetch_with_playwright(self, url: str, browser_fetcher: Any) -> Tuple[str, str]:
        """使用 Playwright 浏览器模式直接提取 Markdown 内容
        
        这是新的首选方法，使用 Playwright 遍历 frame 提取内容，
        可以正确处理 iframe、动态加载内容等复杂页面。
        
        Args:
            url: 网页 URL
            browser_fetcher: 浏览器获取器实例
            
        Returns:
            (markdown_content, title) 元组
            
        Raises:
            ConnectionError: 浏览器获取失败
        """
        _debug_log(f"Playwright 模式获取: {url}", "MARKDOWN")
        
        # 使用浏览器获取并直接提取 Markdown
        result = browser_fetcher.fetch(url, use_cookies=True, extract_markdown=True)
        
        if not result.success:
            raise ConnectionError(f"Playwright 获取失败: {result.error}")
        
        title = result.title or "untitled"
        markdown = result.markdown or ""
        
        _debug_log(f"Playwright 获取成功: {len(markdown)} 字符, 标题: {title}", "MARKDOWN")
        
        # 如果 Playwright 提取的内容太少，尝试用 trafilatura 作为补充
        if len(markdown) < self.MIN_CONTENT_LENGTH:
            _debug_log("Playwright 提取内容较少，尝试 trafilatura 补充", "MARKDOWN")
            import trafilatura
            
            html = result.html
            if html:
                trafilatura_markdown = trafilatura.extract(
                    html,
                    output_format='markdown',
                    include_images=self.config.include_images,
                    include_links=self.config.include_links,
                    include_tables=True,
                    include_comments=False,
                    favor_recall=True,
                )
                
                # 选择内容更多的结果
                if trafilatura_markdown and len(trafilatura_markdown) > len(markdown):
                    _debug_log(f"使用 trafilatura 结果: {len(trafilatura_markdown)} 字符", "MARKDOWN")
                    markdown = trafilatura_markdown
        
        return markdown, title
    
    # 纯文本文件扩展名（直接返回原内容）
    RAW_TEXT_EXTENSIONS = {
        '.md', '.markdown', '.txt', '.rst', '.asciidoc', '.adoc',
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp',
        '.go', '.rs', '.rb', '.php', '.sh', '.bash', '.zsh',
        '.css', '.scss', '.less', '.xml', '.svg', '.csv',
    }
    
    # 纯文本 Content-Type（直接返回原内容）
    RAW_TEXT_CONTENT_TYPES = {
        'text/plain', 'text/markdown', 'text/x-markdown',
        'text/x-rst', 'text/x-python', 'text/x-java',
        'application/json', 'application/yaml', 'application/x-yaml',
        'text/yaml', 'text/x-yaml',
    }

    def _is_raw_text_url(self, url: str) -> bool:
        """判断 URL 是否指向纯文本文件
        
        Args:
            url: 网页 URL
            
        Returns:
            是否为纯文本文件
        """
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # 检查文件扩展名
        for ext in self.RAW_TEXT_EXTENSIONS:
            if path.endswith(ext):
                return True
        
        # 检查是否为 GitHub/GitLab raw 文件
        if 'raw.githubusercontent.com' in url:
            return True
        if 'raw.gitlab.com' in url:
            return True
        if '/raw/' in url or '/-/raw/' in url:
            return True
            
        return False
    
    def _is_raw_text_content_type(self, content_type: str) -> bool:
        """判断 Content-Type 是否为纯文本
        
        Args:
            content_type: HTTP Content-Type 头
            
        Returns:
            是否为纯文本类型
        """
        if not content_type:
            return False
        
        # 提取主类型（去掉 charset 等参数）
        main_type = content_type.split(';')[0].strip().lower()
        
        return main_type in self.RAW_TEXT_CONTENT_TYPES
    
    def _generate_title_from_url(self, url: str) -> str:
        """从 URL 生成标题
        
        Args:
            url: 网页 URL
            
        Returns:
            基于 URL 的标题
        """
        from urllib.parse import urlparse, unquote
        
        try:
            parsed = urlparse(url)
            path = unquote(parsed.path)
            
            # 获取文件名
            if '/' in path:
                filename = path.split('/')[-1]
            else:
                filename = path
            
            # 移除扩展名
            if '.' in filename:
                filename = filename.rsplit('.', 1)[0]
            
            return filename if filename else "untitled"
        except Exception:
            return "untitled"

    def _fetch_and_extract(self, url: str) -> Tuple[str, str]:
        """获取网页并提取内容
        
        Args:
            url: 网页 URL
            
        Returns:
            (markdown_content, title) 元组
            
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
        """
        import trafilatura
        
        _debug_log(f"获取网页内容: {url}", "MARKDOWN")
        
        # 自定义 User-Agent，模拟真实浏览器
        custom_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        # 检查是否为纯文本文件 URL
        is_raw_url = self._is_raw_text_url(url)
        if is_raw_url:
            _debug_log("检测到纯文本文件 URL，将直接返回原内容", "MARKDOWN")
        
        html = None
        content_type = None
        response = None
        
        # 优先使用 requests 获取（可以获取 Content-Type）
        try:
            import requests
            _debug_log("使用 requests 获取网页", "MARKDOWN")
            timeout = getattr(self.config, 'timeout', 30)
            response = requests.get(url, headers=custom_headers, timeout=timeout)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            
            # 处理编码
            if response.encoding and response.encoding.lower() != 'utf-8':
                # 尝试检测正确的编码
                if 'charset' in content_type.lower():
                    html = response.text
                else:
                    # 尝试从内容检测编码
                    response.encoding = response.apparent_encoding or 'utf-8'
                    html = response.text
            else:
                html = response.text
            
            _debug_log(f"requests 获取成功: {len(html)} 字符, Content-Type: {content_type}", "MARKDOWN")
        except Exception as e:
            _debug_log(f"requests 获取失败: {e}", "MARKDOWN")
        
        # 如果 requests 失败，尝试 trafilatura
        if html is None:
            try:
                html = trafilatura.fetch_url(url)
                if html:
                    _debug_log(f"trafilatura.fetch_url 成功: {len(html)} 字符", "MARKDOWN")
            except Exception as e:
                _debug_log(f"trafilatura.fetch_url 失败: {e}", "MARKDOWN")
        
        if html is None:
            _debug_log("获取网页失败", "MARKDOWN")
            raise ConnectionError("无法访问该网页")
        
        _debug_log(f"获取到内容长度: {len(html)} 字符", "MARKDOWN")
        
        # 判断是否为纯文本内容（通过 URL 或 Content-Type）
        is_raw_content = is_raw_url or self._is_raw_text_content_type(content_type)
        
        if is_raw_content:
            # 纯文本文件：直接返回原内容
            _debug_log("纯文本文件，直接返回原内容", "MARKDOWN")
            title = self._extract_title_from_content(url, html)
            return html, title
        
        # HTML 内容：使用 trafilatura 提取
        # 提取元数据获取标题
        metadata = trafilatura.extract_metadata(html)
        title = "untitled"
        if metadata and metadata.title:
            title = metadata.title
        _debug_log(f"网页标题: {title}", "MARKDOWN")
        
        # 第一次尝试：使用 favor_recall=True 提取更多内容
        # 这对于新闻网站等复杂页面结构更有效
        markdown = trafilatura.extract(
            html,
            output_format='markdown',
            include_images=self.config.include_images,
            include_links=self.config.include_links,
            include_tables=True,
            include_comments=False,
            favor_recall=True,  # 优先召回更多内容
        )
        
        # 如果 favor_recall 提取的内容太少或为空，尝试默认模式
        markdown_len = len(markdown) if markdown else 0
        if markdown_len < 500:
            _debug_log(f"favor_recall 提取内容较少 ({markdown_len} 字符)，尝试默认模式", "MARKDOWN")
            markdown_default = trafilatura.extract(
                html,
                output_format='markdown',
                include_images=self.config.include_images,
                include_links=self.config.include_links,
                include_tables=True,
                include_comments=False,
            )
            # 使用内容更多的结果
            default_len = len(markdown_default) if markdown_default else 0
            if default_len > markdown_len:
                markdown = markdown_default
                _debug_log(f"使用默认模式结果: {default_len} 字符", "MARKDOWN")
        
        if not markdown:
            _debug_log("内容提取失败", "MARKDOWN")
            return "", title
        
        _debug_log(f"提取内容长度: {len(markdown)} 字符", "MARKDOWN")
        return markdown, title

    def _sanitize_filename(self, title: str) -> str:
        """生成安全的文件名
        
        移除非法字符，限制长度，确保文件名有效。
        
        Args:
            title: 原始标题
            
        Returns:
            安全的文件名（不含扩展名）
            
        Requirements: 4.2
        Property 3: Filename Sanitization
        """
        if not title or not title.strip():
            return "untitled"
        
        # 移除非法字符
        filename = title
        for char in self.INVALID_FILENAME_CHARS:
            filename = filename.replace(char, "")
        
        # 移除控制字符和其他不可见字符
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        
        # 移除首尾空格和点
        filename = filename.strip().strip('.')
        
        # 如果清理后为空，使用默认名称
        if not filename:
            return "untitled"
        
        # 限制长度
        if len(filename) > self.MAX_FILENAME_LENGTH:
            filename = filename[:self.MAX_FILENAME_LENGTH].rstrip()
        
        return filename
    
    def _generate_filename_from_url(self, url: str) -> str:
        """从 URL 生成文件名
        
        当标题提取失败时，使用 URL 的域名和路径生成文件名。
        例如：https://news.sina.com.cn/china/ -> news.sina.com.cn_china
        
        Args:
            url: 网页 URL
            
        Returns:
            基于 URL 的安全文件名（不含扩展名）
        """
        if not url or not url.strip():
            return "webpage"
        
        try:
            from urllib.parse import urlparse, unquote
            
            parsed = urlparse(url)
            
            # 获取域名
            domain = parsed.netloc or ""
            
            # 获取路径（移除首尾斜杠，解码 URL 编码字符）
            path = unquote(parsed.path.strip("/"))
            
            # 移除常见的网页扩展名
            common_extensions = ('.html', '.htm', '.php', '.asp', '.aspx', '.jsp', '.shtml')
            for ext in common_extensions:
                if path.lower().endswith(ext):
                    path = path[:-len(ext)]
                    break
            
            # 组合域名和路径
            if path:
                # 将路径中的斜杠替换为下划线
                path_part = path.replace("/", "_")
                filename = f"{domain}_{path_part}"
            else:
                filename = domain
            
            # 清理文件名
            filename = self._sanitize_filename(filename)
            
            # 如果清理后为空，使用默认名称
            if not filename or filename == "untitled":
                return "webpage"
            
            return filename
            
        except Exception as e:
            _debug_log(f"从 URL 生成文件名失败: {e}", "MARKDOWN")
            return "webpage"
    
    def _get_unique_filepath(self, directory: str, filename: str) -> str:
        """获取唯一的文件路径，避免覆盖
        
        如果文件已存在，添加数字后缀 (1), (2), ...
        
        Args:
            directory: 目录路径
            filename: 文件名（含扩展名）
            
        Returns:
            唯一的文件完整路径
            
        Requirements: 4.3
        Property 4: Duplicate Filename Handling
        """
        filepath = os.path.join(directory, filename)
        
        if not os.path.exists(filepath):
            return filepath
        
        # 分离文件名和扩展名
        name, ext = os.path.splitext(filename)
        
        # 尝试添加数字后缀
        counter = 1
        while True:
            new_filename = f"{name} ({counter}){ext}"
            new_filepath = os.path.join(directory, new_filename)
            if not os.path.exists(new_filepath):
                return new_filepath
            counter += 1
            # 防止无限循环
            if counter > 10000:
                # 使用时间戳作为后备方案
                import time
                timestamp = int(time.time())
                return os.path.join(directory, f"{name}_{timestamp}{ext}")
    
    def _save_to_file(self, content: str, filepath: str) -> None:
        """保存内容到文件
        
        Args:
            content: Markdown 内容
            filepath: 文件完整路径
            
        Requirements: 4.1
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def _copy_to_clipboard(self, content: str) -> None:
        """复制内容到剪贴板
        
        Args:
            content: 要复制的文本内容
            
        Requirements: 4.5
        """
        try:
            from PySide6.QtWidgets import QApplication
            
            app = QApplication.instance()
            if app:
                clipboard = app.clipboard()
                clipboard.setText(content)
            else:
                _debug_log("QApplication 实例不存在，无法复制到剪贴板", "MARKDOWN")
        except Exception as e:
            _debug_log(f"复制到剪贴板失败: {e}", "MARKDOWN")
