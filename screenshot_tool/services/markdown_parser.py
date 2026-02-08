# =====================================================
# =============== Markdown 解析器 ===============
# =====================================================

"""
Markdown 解析器 - 将 Markdown 文本转换为 HTML

支持的语法：
- 粗体：**text** 或 __text__
- 斜体：*text* 或 _text_
- 删除线：~~text~~
- 标题：# H1, ## H2, ### H3, #### H4, ##### H5, ###### H6
- 无序列表：- item, * item, + item
- 有序列表：1. item, 2. item
- 行内代码：`code`
- 代码块：```code```
- 引用：> quote
- 分隔线：---, ***, ___
- 链接：[text](url)

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11
"""

import re
from typing import List, Tuple


class MarkdownParser:
    """Markdown 到 HTML 解析器"""
    
    # 预览区域的 CSS 样式 (Obsidian 风格)
    PREVIEW_CSS = """
    body {
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #1a1a1a;
        padding: 16px;
        margin: 0;
        background-color: #ffffff;
    }
    h1 { font-size: 20pt; font-weight: 700; margin: 20px 0 10px 0; color: #1a1a1a; }
    h2 { font-size: 16pt; font-weight: 600; margin: 18px 0 8px 0; color: #1a1a1a; }
    h3 { font-size: 14pt; font-weight: 600; margin: 14px 0 6px 0; color: #1a1a1a; }
    h4, h5, h6 { font-size: 12pt; font-weight: 600; margin: 12px 0 4px 0; color: #333333; }
    strong, b { font-weight: 700; }
    em, i { font-style: italic; }
    del, s { text-decoration: line-through; color: #6B7280; }
    code {
        background-color: #f6f8fa;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 10pt;
        color: #d63384;
    }
    .code-block-wrapper {
        position: relative;
        margin: 12px 0;
    }
    .code-lang-label {
        position: absolute;
        top: 0;
        right: 0;
        background-color: #e8e8e8;
        color: #666666;
        font-size: 9pt;
        padding: 2px 10px;
        border-radius: 0 6px 0 6px;
        font-family: "Microsoft YaHei", sans-serif;
    }
    pre {
        background-color: #f6f8fa;
        color: #24292e;
        padding: 16px;
        padding-top: 32px;
        border-radius: 6px;
        overflow-x: auto;
        margin: 0;
        border: 1px solid #e1e4e8;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 10pt;
        line-height: 1.5;
    }
    pre code {
        background-color: transparent;
        padding: 0;
        color: #24292e;
        font-size: 10pt;
    }
    /* 语法高亮 - 关键字 */
    .kw { color: #d73a49; }
    /* 语法高亮 - 字符串 */
    .str { color: #032f62; }
    /* 语法高亮 - 注释 */
    .cmt { color: #6a737d; }
    /* 语法高亮 - 数字 */
    .num { color: #005cc5; }
    /* 语法高亮 - 函数/命令 */
    .fn { color: #6f42c1; }
    /* 语法高亮 - 变量 */
    .var { color: #e36209; }
    /* 语法高亮 - 参数/标志 */
    .flag { color: #22863a; }
    blockquote {
        border-left: 4px solid #7c3aed;
        margin: 12px 0;
        padding: 8px 16px;
        background-color: #faf5ff;
        color: #374151;
    }
    ul, ol { margin: 8px 0; padding-left: 24px; }
    li { margin: 4px 0; }
    hr {
        border: none;
        border-top: 1px solid #e1e4e8;
        margin: 16px 0;
    }
    a {
        color: #7c3aed;
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }
    p { margin: 8px 0; }
    """
    
    def __init__(self):
        """初始化解析器"""
        # 行内元素正则表达式（按优先级排序）
        self._inline_patterns = [
            # 行内代码（最高优先级，避免内部被解析）
            (re.compile(r'`([^`]+)`'), r'<code>\1</code>'),
            # 粗体 **text** 或 __text__
            (re.compile(r'\*\*([^*]+)\*\*'), r'<strong>\1</strong>'),
            (re.compile(r'__([^_]+)__'), r'<strong>\1</strong>'),
            # 斜体 *text* 或 _text_（注意不要匹配 ** 或 __）
            (re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)'), r'<em>\1</em>'),
            (re.compile(r'(?<!_)_([^_]+)_(?!_)'), r'<em>\1</em>'),
            # 删除线 ~~text~~
            (re.compile(r'~~([^~]+)~~'), r'<del>\1</del>'),
            # 链接 [text](url)
            (re.compile(r'\[([^\]]+)\]\(([^)]+)\)'), r'<a href="\2">\1</a>'),
        ]
    
    def parse(self, text: str) -> str:
        """
        将 Markdown 文本解析为 HTML
        
        Args:
            text: Markdown 格式的文本
            
        Returns:
            完整的 HTML 文档字符串（包含样式）
        """
        if not text:
            return self._wrap_html("")
        
        # 分割成行
        lines = text.split('\n')
        
        # 解析块级元素
        html_content = self._parse_blocks(lines)
        
        # 包装成完整 HTML
        return self._wrap_html(html_content)
    
    def parse_to_body(self, text: str) -> str:
        """
        将 Markdown 文本解析为 HTML body 内容（不包含 html/head 标签）
        
        Args:
            text: Markdown 格式的文本
            
        Returns:
            HTML body 内容字符串
        """
        if not text:
            return ""
        
        lines = text.split('\n')
        return self._parse_blocks(lines)
    
    def _wrap_html(self, body_content: str) -> str:
        """包装成完整的 HTML 文档"""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{self.PREVIEW_CSS}
</style>
</head>
<body>
{body_content}
</body>
</html>"""
    
    def _parse_blocks(self, lines: List[str]) -> str:
        """解析块级元素"""
        result = []
        i = 0
        n = len(lines)
        
        while i < n:
            line = lines[i]
            
            # 空行
            if not line.strip():
                i += 1
                continue
            
            # 代码块 ```
            if line.strip().startswith('```'):
                code_lines, i = self._parse_code_block(lines, i)
                result.append(code_lines)
                continue
            
            # 标题 # ## ### etc.
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                content = self._parse_inline(heading_match.group(2))
                result.append(f'<h{level}>{content}</h{level}>')
                i += 1
                continue
            
            # 分隔线 --- *** ___
            if re.match(r'^[-*_]{3,}\s*$', line.strip()):
                result.append('<hr>')
                i += 1
                continue
            
            # 引用 >
            if line.strip().startswith('>'):
                quote_lines, i = self._parse_blockquote(lines, i)
                result.append(quote_lines)
                continue
            
            # 无序列表 - * +
            if re.match(r'^[\s]*[-*+]\s+', line):
                list_html, i = self._parse_unordered_list(lines, i)
                result.append(list_html)
                continue
            
            # 有序列表 1. 2. etc.
            if re.match(r'^[\s]*\d+\.\s+', line):
                list_html, i = self._parse_ordered_list(lines, i)
                result.append(list_html)
                continue
            
            # 普通段落
            para_lines, i = self._parse_paragraph(lines, i)
            result.append(para_lines)
        
        return '\n'.join(result)
    
    def _parse_code_block(self, lines: List[str], start: int) -> Tuple[str, int]:
        """解析代码块，支持语言标签和语法高亮"""
        # 提取语言标识
        first_line = lines[start].strip()
        lang = first_line[3:].strip().lower() if len(first_line) > 3 else ""
        
        # 语言显示名称映射
        lang_display = {
            "bash": "Shell", "sh": "Shell", "shell": "Shell", "zsh": "Shell",
            "powershell": "PowerShell", "ps1": "PowerShell", "pwsh": "PowerShell",
            "python": "Python", "py": "Python",
            "javascript": "JavaScript", "js": "JavaScript",
            "typescript": "TypeScript", "ts": "TypeScript",
            "json": "JSON", "yaml": "YAML", "yml": "YAML",
            "html": "HTML", "css": "CSS", "sql": "SQL",
            "java": "Java", "c": "C", "cpp": "C++", "csharp": "C#", "cs": "C#",
            "go": "Go", "rust": "Rust", "ruby": "Ruby", "php": "PHP",
            "markdown": "Markdown", "md": "Markdown",
            "xml": "XML", "toml": "TOML", "ini": "INI",
        }
        display_lang = lang_display.get(lang, lang.upper() if lang else "")
        
        i = start + 1
        n = len(lines)
        code_lines = []
        
        while i < n:
            if lines[i].strip().startswith('```'):
                i += 1
                break
            code_lines.append(self._escape_html(lines[i]))
            i += 1
        
        # 应用语法高亮
        highlighted_lines = [self._highlight_code(line, lang) for line in code_lines]
        code_content = '\n'.join(highlighted_lines)
        
        # 生成带语言标签的代码块
        if display_lang:
            return f'<div class="code-block-wrapper"><span class="code-lang-label">{display_lang}</span><pre><code>{code_content}</code></pre></div>', i
        else:
            return f'<pre><code>{code_content}</code></pre>', i
    
    def _highlight_code(self, line: str, lang: str) -> str:
        """对代码行应用基础语法高亮"""
        if not lang or not line.strip():
            return line
        
        # Shell/Bash 高亮
        if lang in ("bash", "sh", "shell", "zsh", "powershell", "ps1", "pwsh"):
            # 注释
            if line.strip().startswith('#'):
                return f'<span class="cmt">{line}</span>'
            # 命令和参数
            line = re.sub(r'\b(npm|pip|python|node|git|cd|ls|mkdir|rm|cp|mv|cat|echo|export|source|sudo|apt|brew|winget|irm|iex)\b', 
                         r'<span class="fn">\1</span>', line)
            line = re.sub(r'(\s)(-{1,2}[\w-]+)', r'\1<span class="flag">\2</span>', line)
            line = re.sub(r'(\$\w+|\$\{[^}]+\})', r'<span class="var">\1</span>', line)
            return line
        
        # Python 高亮
        if lang in ("python", "py"):
            if line.strip().startswith('#'):
                return f'<span class="cmt">{line}</span>'
            line = re.sub(r'\b(def|class|import|from|return|if|else|elif|for|while|try|except|finally|with|as|in|is|not|and|or|True|False|None|self|async|await|yield|lambda|raise|pass|break|continue)\b',
                         r'<span class="kw">\1</span>', line)
            line = re.sub(r'(&quot;[^&]*&quot;|&#39;[^&]*&#39;)', r'<span class="str">\1</span>', line)
            line = re.sub(r'\b(\d+\.?\d*)\b', r'<span class="num">\1</span>', line)
            return line
        
        # JavaScript/TypeScript 高亮
        if lang in ("javascript", "js", "typescript", "ts"):
            line = re.sub(r'\b(const|let|var|function|return|if|else|for|while|class|import|export|from|async|await|try|catch|finally|new|this|true|false|null|undefined)\b',
                         r'<span class="kw">\1</span>', line)
            line = re.sub(r'(&quot;[^&]*&quot;|&#39;[^&]*&#39;|`[^`]*`)', r'<span class="str">\1</span>', line)
            line = re.sub(r'\b(\d+\.?\d*)\b', r'<span class="num">\1</span>', line)
            return line
        
        return line
    
    def _parse_blockquote(self, lines: List[str], start: int) -> Tuple[str, int]:
        """解析引用块"""
        i = start
        n = len(lines)
        quote_lines = []
        
        while i < n:
            line = lines[i]
            if line.strip().startswith('>'):
                # 移除 > 前缀
                content = re.sub(r'^>\s?', '', line.strip())
                quote_lines.append(self._parse_inline(content))
                i += 1
            elif line.strip() == '' and i + 1 < n and lines[i + 1].strip().startswith('>'):
                # 空行但下一行还是引用
                quote_lines.append('')
                i += 1
            else:
                break
        
        quote_content = '<br>'.join(quote_lines)
        return f'<blockquote>{quote_content}</blockquote>', i
    
    def _parse_unordered_list(self, lines: List[str], start: int) -> Tuple[str, int]:
        """解析无序列表"""
        i = start
        n = len(lines)
        items = []
        
        while i < n:
            line = lines[i]
            match = re.match(r'^[\s]*[-*+]\s+(.+)$', line)
            if match:
                content = self._parse_inline(match.group(1))
                items.append(f'<li>{content}</li>')
                i += 1
            elif line.strip() == '':
                # 空行可能结束列表
                if i + 1 < n and re.match(r'^[\s]*[-*+]\s+', lines[i + 1]):
                    i += 1
                else:
                    break
            else:
                break
        
        return '<ul>' + ''.join(items) + '</ul>', i
    
    def _parse_ordered_list(self, lines: List[str], start: int) -> Tuple[str, int]:
        """解析有序列表"""
        i = start
        n = len(lines)
        items = []
        
        while i < n:
            line = lines[i]
            match = re.match(r'^[\s]*\d+\.\s+(.+)$', line)
            if match:
                content = self._parse_inline(match.group(1))
                items.append(f'<li>{content}</li>')
                i += 1
            elif line.strip() == '':
                # 空行可能结束列表
                if i + 1 < n and re.match(r'^[\s]*\d+\.\s+', lines[i + 1]):
                    i += 1
                else:
                    break
            else:
                break
        
        return '<ol>' + ''.join(items) + '</ol>', i
    
    def _parse_paragraph(self, lines: List[str], start: int) -> Tuple[str, int]:
        """解析段落"""
        i = start
        n = len(lines)
        para_lines = []
        
        while i < n:
            line = lines[i]
            # 遇到空行或特殊块级元素开始，结束段落
            if (not line.strip() or
                line.strip().startswith('#') or
                line.strip().startswith('>') or
                line.strip().startswith('```') or
                re.match(r'^[-*_]{3,}\s*$', line.strip()) or
                re.match(r'^[\s]*[-*+]\s+', line) or
                re.match(r'^[\s]*\d+\.\s+', line)):
                break
            para_lines.append(self._parse_inline(line))
            i += 1
        
        para_content = '<br>'.join(para_lines)
        return f'<p>{para_content}</p>', i
    
    def _parse_inline(self, text: str) -> str:
        """解析行内元素"""
        if not text:
            return ""
        
        # 先转义 HTML 特殊字符（但保留我们要生成的标签）
        # 这里需要小心处理，因为我们要生成 HTML 标签
        # 所以先处理 Markdown，再转义剩余的特殊字符
        
        result = text
        
        # 按顺序应用行内模式
        for pattern, replacement in self._inline_patterns:
            result = pattern.sub(replacement, result)
        
        return result
    
    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))


# 单例实例
_parser_instance = None


def get_markdown_parser() -> MarkdownParser:
    """获取 Markdown 解析器单例"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = MarkdownParser()
    return _parser_instance
