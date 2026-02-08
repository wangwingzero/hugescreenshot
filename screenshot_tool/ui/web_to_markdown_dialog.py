# =====================================================
# =============== 网页转 Markdown 对话框 ===============
# =====================================================

"""
网页转 Markdown 对话框

简化的 URL 输入对话框，转换结果通过系统通知显示。

Feature: web-to-markdown-dialog
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4
"""

import re
import html
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton,
    QGroupBox, QMessageBox, QLineEdit,
    QFileDialog
)
from PySide6.QtCore import Qt, Signal

from .styles import DIALOG_STYLE, GROUPBOX_STYLE, INPUT_STYLE
from .ui_components import ModernButton
from ..core.config_manager import MarkdownConfig


def extract_url_from_html(html_content: str) -> Optional[str]:
    """从 HTML 富文本中提取 URL
    
    Edge 浏览器复制 URL 时会生成类似这样的 HTML：
    <a href="https://...">页面标题</a>
    
    Args:
        html_content: HTML 富文本内容
        
    Returns:
        提取到的 URL，如果没有则返回 None
    """
    if not html_content:
        return None
    
    # 匹配 <a href="..."> 中的 URL
    match = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
    if match:
        url = match.group(1)
        # 使用标准库解码 HTML 实体（如 &amp; -> &）
        url = html.unescape(url)
        if url.startswith(('http://', 'https://')):
            return url
    
    return None


class SmartUrlTextEdit(QTextEdit):
    """智能 URL 输入框
    
    自动从剪贴板的 HTML 格式中提取真实 URL，
    解决 Edge 浏览器复制 URL 变成标题的问题。
    """
    
    def insertFromMimeData(self, source):
        """重写粘贴方法，智能提取 URL
        
        优先从 HTML 格式中提取 URL，如果没有则使用纯文本。
        """
        # 尝试从 HTML 中提取 URL
        if source.hasHtml():
            html_content = source.html()
            url = extract_url_from_html(html_content)
            if url:
                # 获取当前光标位置，插入提取到的 URL
                cursor = self.textCursor()
                cursor.insertText(url)
                return
        
        # 如果没有 HTML 或提取失败，使用默认行为（纯文本）
        if source.hasText():
            text = source.text()
            cursor = self.textCursor()
            cursor.insertText(text)
        else:
            super().insertFromMimeData(source)


def is_valid_url(url: str) -> bool:
    """验证 URL 是否有效
    
    URL 必须以 http:// 或 https:// 开头，且主机部分非空、无空格。
    
    Args:
        url: 要验证的 URL 字符串
        
    Returns:
        bool: URL 是否有效
        
    Feature: web-to-markdown-dialog
    Requirements: 4.1, 4.2
    **Validates: Requirements 4.1, 4.2**
    """
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    
    # 必须以 http:// 或 https:// 开头
    if url.startswith("https://"):
        rest = url[8:]
    elif url.startswith("http://"):
        rest = url[7:]
    else:
        return False
    
    # 主机部分不能为空
    if not rest:
        return False
    
    # 获取主机部分（到第一个 / 或结尾）
    slash_pos = rest.find("/")
    if slash_pos == -1:
        host = rest
    else:
        host = rest[:slash_pos]
    
    # 主机部分不能为空
    if not host:
        return False
    
    # 主机部分不能包含空格、换行符、回车符
    if " " in host or "\n" in host or "\r" in host:
        return False
    
    return True


def parse_urls(text: str) -> List[str]:
    """从多行文本中解析有效的 URL
    
    跳过空行和无效 URL，保持原始顺序。
    
    Args:
        text: 多行文本，每行一个 URL
        
    Returns:
        List[str]: 有效 URL 列表
        
    Feature: web-to-markdown-dialog
    Requirements: 4.3, 5.1
    **Validates: Requirements 4.3**
    """
    if not text:
        return []
    
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if line and is_valid_url(line):
            urls.append(line)
    
    return urls


class WebToMarkdownDialog(QDialog):
    """网页转 Markdown 对话框
    
    简化的 URL 输入对话框，转换结果通过系统通知显示。
    
    Feature: web-to-markdown-dialog
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
    """
    
    # 信号：请求转换 URL 列表，参数为 (urls, save_dir)
    conversion_requested = Signal(list, str)  # List[str], str
    
    def __init__(self, config: MarkdownConfig, parent=None):
        """初始化对话框
        
        Args:
            config: Markdown 配置
            parent: 父窗口
        """
        super().__init__(parent)
        self._config = config
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI
        
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
        """
        self.setWindowTitle("📝 网页转 Markdown")
        self.setMinimumSize(500, 450)
        self.resize(550, 500)
        self.setStyleSheet(DIALOG_STYLE)
        
        # 允许调整大小
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # URL 输入区域
        input_group = QGroupBox("输入 URL")
        input_group.setStyleSheet(GROUPBOX_STYLE)
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)
        
        # URL 输入框（多行）- 使用智能输入框自动提取 URL
        self._url_input = SmartUrlTextEdit()
        self._url_input.setStyleSheet(INPUT_STYLE + """
            QTextEdit {
                min-height: 180px;
            }
        """)
        self._url_input.setPlaceholderText(
            "输入要转换的网页 URL，每行一个\n\n"
            "示例：\n"
            "https://example.com/article1\n"
            "https://example.com/article2\n"
            "https://blog.example.org/post"
        )
        self._url_input.textChanged.connect(self._on_text_changed)
        input_layout.addWidget(self._url_input)
        
        # URL 计数标签
        self._count_label = QLabel("有效 URL: 0 个")
        self._count_label.setStyleSheet("color: #666;")
        input_layout.addWidget(self._count_label)
        
        layout.addWidget(input_group)
        
        # 保存路径区域
        save_group = QGroupBox("保存位置")
        save_group.setStyleSheet(GROUPBOX_STYLE)
        save_layout = QHBoxLayout(save_group)
        save_layout.setSpacing(8)
        
        # 保存路径输入框
        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.setStyleSheet(INPUT_STYLE)
        self._save_dir_edit.setPlaceholderText("选择保存文件夹...")
        # 使用配置中的保存目录，如果为空则使用默认目录
        self._save_dir_edit.setText(self._config.get_save_dir())
        save_layout.addWidget(self._save_dir_edit)
        
        # 浏览按钮
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setStyleSheet(INPUT_STYLE)
        self._browse_btn.clicked.connect(self._browse_save_dir)
        save_layout.addWidget(self._browse_btn)
        
        layout.addWidget(save_group)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # 关闭按钮
        self._close_btn = ModernButton("关闭", ModernButton.SECONDARY)
        self._close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._close_btn)
        
        # 开始转换按钮
        self._start_btn = ModernButton("🚀 开始转换", ModernButton.PRIMARY)
        self._start_btn.clicked.connect(self._on_start_conversion)
        btn_layout.addWidget(self._start_btn)
        
        layout.addLayout(btn_layout)
    
    def _browse_save_dir(self):
        """浏览选择保存目录"""
        current_dir = self._save_dir_edit.text().strip()
        if not current_dir:
            current_dir = self._config.get_save_dir()
        
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择保存位置",
            current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if dir_path:
            self._save_dir_edit.setText(dir_path)
    
    def _on_text_changed(self):
        """文本变化时更新 URL 计数
        
        Requirements: 3.4, 3.5
        """
        text = self._url_input.toPlainText()
        urls = parse_urls(text)
        count = len(urls)
        self._count_label.setText(f"有效 URL: {count} 个")
    
    def _on_start_conversion(self):
        """开始转换
        
        验证 URL，发送信号，关闭对话框。
        
        Requirements: 4.4, 5.1
        """
        text = self._url_input.toPlainText()
        urls = parse_urls(text)
        
        if not urls:
            QMessageBox.warning(
                self,
                "没有有效 URL 🔗",
                "链接格式不太对，要以 http:// 或 https:// 开头哦～"
            )
            return
        
        # 获取保存目录
        save_dir = self._save_dir_edit.text().strip()
        if not save_dir:
            save_dir = self._config.get_save_dir()
        
        # 更新配置中的保存目录（记住用户选择）
        self._config.save_dir = save_dir
        
        # 发送转换请求信号（包含保存目录）
        self.conversion_requested.emit(urls, save_dir)
        
        # 关闭对话框
        self.accept()
    
    # 以下方法用于测试和兼容性
    def _is_valid_url(self, url: str) -> bool:
        """验证 URL 是否有效（实例方法，用于测试兼容性）"""
        return is_valid_url(url)
    
    def _parse_urls(self, text: str) -> List[str]:
        """解析 URL 列表（实例方法，用于测试兼容性）"""
        return parse_urls(text)
