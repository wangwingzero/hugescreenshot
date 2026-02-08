# =====================================================
# =============== 浏览器模式网页获取服务 ===============
# =====================================================

"""
浏览器模式网页获取服务

使用 Patchright（Playwright 的防检测分支）获取网页内容，
支持反爬虫网站和动态加载内容。

特点：
- 使用 Patchright 绕过 Cloudflare、DataDome 等反爬检测
- 修复了 CDP 泄露、navigator.webdriver 等自动化特征
- 使用用户已安装的浏览器，无需额外下载
- 可以复用浏览器的 Cookie（获取登录状态）
- 支持 JavaScript 渲染的动态页面
"""

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import Optional, List

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


@dataclass
class BrowserInfo:
    """浏览器信息"""
    name: str
    executable_path: str
    user_data_dir: str


@dataclass
class FetchResult:
    """获取结果"""
    success: bool
    html: str = ""
    title: str = ""
    error: str = ""
    markdown: str = ""  # Playwright 直接提取的 Markdown 内容


class BrowserFetcher:
    """浏览器模式网页获取器
    
    使用用户已安装的 Chrome/Edge 浏览器获取网页内容。
    """
    
    # Chrome 可能的安装路径
    CHROME_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    
    # Edge 可能的安装路径
    EDGE_PATHS = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    
    # Chrome 用户数据目录
    CHROME_USER_DATA = os.path.expanduser(
        r"~\AppData\Local\Google\Chrome\User Data"
    )
    
    # Edge 用户数据目录
    EDGE_USER_DATA = os.path.expanduser(
        r"~\AppData\Local\Microsoft\Edge\User Data"
    )
    
    def __init__(self, timeout: int = 30):
        """初始化
        
        Args:
            timeout: 页面加载超时时间（秒）
        """
        self.timeout = timeout
    
    @classmethod
    def find_browser(cls, prefer_edge: bool = True) -> Optional[BrowserInfo]:
        """查找用户已安装的浏览器
        
        默认优先使用 Edge（Windows 预装），其次使用 Chrome。
        
        Args:
            prefer_edge: 是否优先使用 Edge，默认 True
            
        Returns:
            BrowserInfo 或 None
        """
        # 根据优先级排列查找顺序
        finders = [cls._find_edge, cls._find_chrome] if prefer_edge else [cls._find_chrome, cls._find_edge]
        
        for finder in finders:
            browser = finder()
            if browser:
                return browser
        
        _debug_log("未找到可用的浏览器", "BROWSER")
        return None
    
    @classmethod
    def _find_chrome(cls) -> Optional[BrowserInfo]:
        """查找 Chrome 浏览器"""
        for path in cls.CHROME_PATHS:
            if os.path.exists(path):
                _debug_log(f"找到 Chrome: {path}", "BROWSER")
                return BrowserInfo(
                    name="Chrome",
                    executable_path=path,
                    user_data_dir=cls.CHROME_USER_DATA
                )
        return None
    
    @classmethod
    def _find_edge(cls) -> Optional[BrowserInfo]:
        """查找 Edge 浏览器"""
        for path in cls.EDGE_PATHS:
            if os.path.exists(path):
                _debug_log(f"找到 Edge: {path}", "BROWSER")
                return BrowserInfo(
                    name="Edge",
                    executable_path=path,
                    user_data_dir=cls.EDGE_USER_DATA
                )
        return None
    
    @classmethod
    def is_available(cls) -> bool:
        """检查浏览器模式是否可用
        
        Returns:
            是否可用
        """
        # 先检查是否有可用浏览器
        if cls.find_browser() is None:
            return False
        
        # 检查 patchright 是否安装（优先），否则检查 playwright
        try:
            import patchright  # noqa: F401
            return True
        except ImportError:
            try:
                import playwright  # noqa: F401
                _debug_log("Patchright 未安装，回退到 Playwright", "BROWSER")
                return True
            except ImportError:
                return False
    
    def fetch(self, url: str, use_cookies: bool = True, extract_markdown: bool = False) -> FetchResult:
        """获取网页内容
        
        Args:
            url: 网页 URL
            use_cookies: 是否使用浏览器的 Cookie
            extract_markdown: 是否直接提取 Markdown（使用 accessibility tree）
            
        Returns:
            FetchResult 包含获取结果
        """
        browser_info = self.find_browser()
        if not browser_info:
            return FetchResult(
                success=False,
                error="未找到可用的浏览器（Chrome 或 Edge）"
            )
        
        _debug_log(f"使用 {browser_info.name} 获取: {url}", "BROWSER")
        
        try:
            # 优先使用 Patchright（防检测），否则回退到 Playwright
            try:
                from patchright.sync_api import sync_playwright
                _debug_log("使用 Patchright（防检测模式）", "BROWSER")
            except ImportError:
                from playwright.sync_api import sync_playwright
                _debug_log("Patchright 未安装，使用 Playwright", "BROWSER")
            
            with sync_playwright() as p:
                # 使用用户已安装的浏览器（executable_path）
                # 这样可以直接使用系统浏览器，无需额外安装驱动
                browser = p.chromium.launch(
                    executable_path=browser_info.executable_path,
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-infobars',
                        '--no-sandbox',
                    ]
                )
                
                try:
                    # 创建上下文
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        locale='zh-CN',
                    )
                    
                    # 如果需要使用 Cookie，尝试加载
                    if use_cookies:
                        cookies = self._load_cookies(browser_info, url)
                        if cookies:
                            context.add_cookies(cookies)
                            _debug_log(f"已加载 {len(cookies)} 个 Cookie", "BROWSER")
                    
                    # 创建页面并访问
                    page = context.new_page()
                    
                    try:
                        page.goto(url, timeout=self.timeout * 1000, wait_until='networkidle')
                    except Exception as e:
                        # 如果 networkidle 超时，尝试 domcontentloaded
                        _debug_log(f"networkidle 超时，尝试 domcontentloaded: {e}", "BROWSER")
                        page.goto(url, timeout=self.timeout * 1000, wait_until='domcontentloaded')
                    
                    # 等待页面稳定
                    page.wait_for_timeout(1000)
                    
                    # 获取标题
                    title = page.title()
                    
                    # 获取 HTML 内容
                    html = page.content()
                    
                    markdown = ""
                    if extract_markdown:
                        # 使用 accessibility tree 提取内容
                        markdown = self._extract_markdown_from_page(page)
                        _debug_log(f"Markdown 提取完成: {len(markdown)} 字符", "BROWSER")
                    
                    _debug_log(f"获取成功: HTML {len(html)} 字符, 标题: {title}", "BROWSER")
                    
                    return FetchResult(
                        success=True,
                        html=html,
                        title=title,
                        markdown=markdown
                    )
                finally:
                    # 确保浏览器关闭，避免资源泄漏
                    browser.close()
                
        except Exception as e:
            error_msg = str(e)
            _debug_log(f"浏览器获取失败: {error_msg}", "BROWSER")
            return FetchResult(success=False, error=error_msg)
    
    def _extract_markdown_from_page(self, page) -> str:
        """从页面提取 Markdown 内容
        
        使用 Playwright 遍历所有 frame，提取文本内容并转换为 Markdown。
        这种方法可以正确处理 iframe 内容。
        
        Args:
            page: Playwright Page 对象
            
        Returns:
            Markdown 格式的内容
        """
        try:
            frames = page.frames
            _debug_log(f"页面包含 {len(frames)} 个 frame", "BROWSER")
            
            all_content = []
            
            for i, frame in enumerate(frames):
                try:
                    frame_url = frame.url or ""
                    # 安全截取 URL 用于日志
                    url_preview = frame_url[:100] if len(frame_url) > 100 else frame_url
                    _debug_log(f"处理 frame {i}: {url_preview}...", "BROWSER")
                    
                    # 使用 JavaScript 提取结构化内容
                    content = self._extract_content_from_frame(frame)
                    if content and len(content.strip()) > 100:
                        all_content.append(content)
                        _debug_log(f"Frame {i} 提取到 {len(content)} 字符", "BROWSER")
                except Exception as e:
                    _debug_log(f"Frame {i} 提取失败: {e}", "BROWSER")
                    continue
            
            # 合并所有内容，选择最长的（通常是主内容）
            if all_content:
                # 按长度排序，取最长的内容
                all_content.sort(key=len, reverse=True)
                return all_content[0]
            
            return ""
            
        except Exception as e:
            _debug_log(f"Markdown 提取异常: {e}", "BROWSER")
            return ""
    
    def _extract_content_from_frame(self, frame) -> str:
        """从单个 frame 提取内容并转换为 Markdown
        
        Args:
            frame: Playwright Frame 对象
            
        Returns:
            Markdown 格式的内容
        """
        # 使用 JavaScript 提取页面结构化内容
        js_code = """
        () => {
            const result = [];
            
            // 辅助函数：清理文本
            function cleanText(text) {
                return text ? text.trim().replace(/\\s+/g, ' ') : '';
            }
            
            // 辅助函数：获取元素的纯文本
            function getTextContent(el) {
                return cleanText(el.textContent || '');
            }
            
            // 处理代码块
            function processCodeBlock(el) {
                const code = el.querySelector('code') || el;
                const text = code.textContent || '';
                // 检测语言
                const langClass = code.className.match(/language-(\\w+)/);
                const lang = langClass ? langClass[1] : '';
                return '```' + lang + '\\n' + text + '\\n```';
            }
            
            // 处理表格
            function processTable(table) {
                const rows = [];
                const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
                
                if (headerRow) {
                    const headers = Array.from(headerRow.querySelectorAll('th, td')).map(cell => cleanText(cell.textContent));
                    if (headers.length > 0) {
                        rows.push('| ' + headers.join(' | ') + ' |');
                        rows.push('| ' + headers.map(() => '---').join(' | ') + ' |');
                    }
                }
                
                const bodyRows = table.querySelectorAll('tbody tr');
                bodyRows.forEach(row => {
                    const cells = Array.from(row.querySelectorAll('td, th')).map(cell => cleanText(cell.textContent).replace(/\\|/g, '\\\\|'));
                    if (cells.length > 0) {
                        rows.push('| ' + cells.join(' | ') + ' |');
                    }
                });
                
                return rows.join('\\n');
            }
            
            // 处理列表
            function processList(list, indent = '') {
                const items = [];
                const isOrdered = list.tagName === 'OL';
                let index = 1;
                
                Array.from(list.children).forEach(li => {
                    if (li.tagName === 'LI') {
                        const prefix = isOrdered ? (index++ + '. ') : '- ';
                        const text = cleanText(li.firstChild?.textContent || li.textContent);
                        items.push(indent + prefix + text);
                        
                        // 处理嵌套列表
                        const nestedList = li.querySelector('ul, ol');
                        if (nestedList) {
                            items.push(processList(nestedList, indent + '  '));
                        }
                    }
                });
                
                return items.join('\\n');
            }
            
            // 主要内容区域选择器
            const mainSelectors = [
                'main', 'article', '[role="main"]', '.main-content', '.content',
                '.markdown-body', '.documentation', '.docs-content', '#content'
            ];
            
            let mainContent = null;
            for (const selector of mainSelectors) {
                mainContent = document.querySelector(selector);
                if (mainContent) break;
            }
            
            // 如果没找到主内容区域，使用 body
            const container = mainContent || document.body;
            
            // 遍历所有元素
            const walker = document.createTreeWalker(
                container,
                NodeFilter.SHOW_ELEMENT,
                {
                    acceptNode: function(node) {
                        // 跳过隐藏元素和脚本/样式
                        const style = window.getComputedStyle(node);
                        if (style.display === 'none' || style.visibility === 'hidden') {
                            return NodeFilter.FILTER_REJECT;
                        }
                        const tag = node.tagName.toLowerCase();
                        if (['script', 'style', 'noscript', 'svg', 'path', 'button', 'nav', 'footer', 'header'].includes(tag)) {
                            return NodeFilter.FILTER_REJECT;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );
            
            const processedElements = new Set();
            
            while (walker.nextNode()) {
                const el = walker.currentNode;
                const tag = el.tagName.toLowerCase();
                
                // 避免重复处理
                if (processedElements.has(el)) continue;
                
                // 处理标题
                if (/^h[1-6]$/.test(tag)) {
                    const level = parseInt(tag[1]);
                    const text = getTextContent(el);
                    if (text && text.length > 0) {
                        result.push('\\n' + '#'.repeat(level) + ' ' + text + '\\n');
                        processedElements.add(el);
                    }
                }
                // 处理段落
                else if (tag === 'p') {
                    const text = getTextContent(el);
                    if (text && text.length > 10) {
                        result.push('\\n' + text + '\\n');
                        processedElements.add(el);
                    }
                }
                // 处理代码块
                else if (tag === 'pre') {
                    result.push('\\n' + processCodeBlock(el) + '\\n');
                    processedElements.add(el);
                    // 标记子元素为已处理
                    el.querySelectorAll('*').forEach(child => processedElements.add(child));
                }
                // 处理表格
                else if (tag === 'table') {
                    const tableContent = processTable(el);
                    if (tableContent) {
                        result.push('\\n' + tableContent + '\\n');
                    }
                    processedElements.add(el);
                    el.querySelectorAll('*').forEach(child => processedElements.add(child));
                }
                // 处理列表
                else if (tag === 'ul' || tag === 'ol') {
                    // 只处理顶级列表
                    if (!el.parentElement || !['ul', 'ol', 'li'].includes(el.parentElement.tagName.toLowerCase())) {
                        result.push('\\n' + processList(el) + '\\n');
                        processedElements.add(el);
                        el.querySelectorAll('*').forEach(child => processedElements.add(child));
                    }
                }
                // 处理引用
                else if (tag === 'blockquote') {
                    const text = getTextContent(el);
                    if (text) {
                        const lines = text.split('\\n').map(line => '> ' + line.trim()).join('\\n');
                        result.push('\\n' + lines + '\\n');
                        processedElements.add(el);
                    }
                }
            }
            
            // 如果标准提取没有内容，尝试提取 div 中的文本作为后备
            if (result.length === 0) {
                const divs = container.querySelectorAll('div');
                const seenTexts = new Set();
                divs.forEach(div => {
                    // 跳过已处理的元素
                    if (processedElements.has(div)) return;
                    // 跳过包含子 div 的元素（避免重复）
                    if (div.querySelector('div')) return;
                    
                    const text = cleanText(div.textContent);
                    // 只保留有意义的文本（长度 > 30 且不重复）
                    if (text && text.length > 30 && !seenTexts.has(text)) {
                        seenTexts.add(text);
                        result.push('\\n' + text + '\\n');
                    }
                });
            }
            
            return result.join('').replace(/\\n{3,}/g, '\\n\\n').trim();
        }
        """
        
        try:
            content = frame.evaluate(js_code)
            return content or ""
        except Exception as e:
            _debug_log(f"JavaScript 提取失败: {e}", "BROWSER")
            return ""
    
    def _load_cookies(self, browser_info: BrowserInfo, url: str) -> List[dict]:
        """加载浏览器的 Cookie
        
        Args:
            browser_info: 浏览器信息
            url: 目标 URL（用于过滤 Cookie）
            
        Returns:
            Cookie 列表
        """
        from urllib.parse import urlparse
        
        try:
            domain = urlparse(url).netloc
            # 提取主域名（如 zhihu.com）
            parts = domain.split('.')
            if len(parts) >= 2:
                main_domain = '.'.join(parts[-2:])
            else:
                main_domain = domain
            
            _debug_log(f"尝试加载 {main_domain} 的 Cookie", "BROWSER")
            
            # Cookie 文件路径
            cookie_path = os.path.join(
                browser_info.user_data_dir,
                "Default",
                "Network",
                "Cookies"
            )
            
            if not os.path.exists(cookie_path):
                _debug_log(f"Cookie 文件不存在: {cookie_path}", "BROWSER")
                return []
            
            # 读取 Cookie（SQLite 数据库）
            # 注意：Chrome 的 Cookie 是加密的，需要解密
            # 这里简化处理，只读取未加密的部分
            cookies = self._read_chrome_cookies(cookie_path, main_domain)
            return cookies
            
        except Exception as e:
            _debug_log(f"加载 Cookie 失败: {e}", "BROWSER")
            return []
    
    def _read_chrome_cookies(self, cookie_path: str, domain: str) -> List[dict]:
        """读取 Chrome Cookie
        
        注意：Chrome 80+ 的 Cookie 是加密的，需要使用 DPAPI 解密。
        这里提供一个简化版本，可能无法读取所有 Cookie。
        
        Args:
            cookie_path: Cookie 数据库路径
            domain: 域名
            
        Returns:
            Cookie 列表
        """
        cookies = []
        temp_dir = None
        conn = None
        
        try:
            # 复制 Cookie 文件（因为原文件可能被锁定）
            temp_dir = tempfile.mkdtemp()
            temp_cookie = os.path.join(temp_dir, "Cookies")
            shutil.copy2(cookie_path, temp_cookie)
            
            conn = sqlite3.connect(temp_cookie)
            cursor = conn.cursor()
            
            # 查询指定域名的 Cookie
            # 使用参数化查询防止 SQL 注入
            cursor.execute("""
                SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly
                FROM cookies
                WHERE host_key LIKE ?
            """, (f'%{domain}%',))
            
            for row in cursor.fetchall():
                host_key, name, value, path, expires_utc, is_secure, is_httponly = row
                
                # 注意：value 可能是加密的（encrypted_value 字段）
                # 这里只使用未加密的 value
                if value:
                    cookies.append({
                        'name': name,
                        'value': value,
                        'domain': host_key,
                        'path': path,
                        'secure': bool(is_secure),
                        'httpOnly': bool(is_httponly),
                    })
            
            _debug_log(f"读取到 {len(cookies)} 个 Cookie", "BROWSER")
            return cookies
            
        except Exception as e:
            _debug_log(f"读取 Cookie 数据库失败: {e}", "BROWSER")
            return []
        finally:
            # 确保资源正确释放
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)


def test_browser_fetcher():
    """测试浏览器获取器"""
    print("=" * 60)
    print("浏览器模式网页获取测试")
    print("=" * 60)
    
    # 检查可用性
    print(f"\n浏览器模式可用: {BrowserFetcher.is_available()}")
    
    browser_info = BrowserFetcher.find_browser()
    if browser_info:
        print(f"找到浏览器: {browser_info.name}")
        print(f"路径: {browser_info.executable_path}")
    else:
        print("未找到可用浏览器")
        return
    
    # 测试获取知乎页面
    fetcher = BrowserFetcher(timeout=30)
    
    print("\n测试获取知乎专栏...")
    result = fetcher.fetch("https://zhuanlan.zhihu.com/p/25228075", use_cookies=False)
    
    if result.success:
        print(f"✅ 成功!")
        print(f"   标题: {result.title}")
        print(f"   HTML 长度: {len(result.html)} 字符")
    else:
        print(f"❌ 失败: {result.error}")


if __name__ == "__main__":
    test_browser_fetcher()
