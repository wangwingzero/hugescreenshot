# =====================================================
# =============== 代码块组件 ===============
# =====================================================

"""
代码块显示组件 - VS Code 风格

提供精美的代码块显示和一键复制功能：
- Monokai 深色主题背景
- Pygments 语法高亮（可选）
- 一键复制按钮
- "Done!" 反馈动画

Feature: code-block-copy
Requirements: 1.1-1.8, 2.1-2.8, 3.1-3.6
"""

from typing import Optional, Union

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QGuiApplication, QFont, QColor, QTextCharFormat, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QPlainTextEdit,
    QWidget,
)


# =====================================================
# =============== 配置常量 ===============
# =====================================================

# Monokai 主题颜色
# 基于 2026 年深色模式最佳实践 - "layered darkness" 方法，避免纯黑背景
CODE_COLORS = {
    "background": "#272822",      # 代码区背景 - Monokai 经典背景色
    "header_bg": "#3E3D32",        # 头部栏背景 - 略浅于代码区
    "text": "#F8F8F2",             # 代码文字 - off-white 减少眩光
    "text_muted": "#75715E",       # 语言标签文字 - 灰色
    "button_bg": "#333333",        # 按钮背景
    "button_hover": "#444444",     # 按钮悬停
    "button_success": "#0E639C",   # 复制成功 - VS Code 蓝色
}

# 字体配置
CODE_FONT = {
    "family": "'Consolas', 'Monaco', 'Courier New', monospace",
    "size": 13,  # px
    "line_height": 1.6,
}

# 布局配置
CODE_LAYOUT = {
    "border_radius": 8,   # px - 现代 UI 标准圆角
    "padding": 16,        # px - 内部呼吸空间
    "header_height": 36,  # px
    "button_width": 60,   # px
    "button_height": 24,  # px
}

# 动画配置
CODE_ANIMATION = {
    "feedback_duration": 1500,  # ms - 复制反馈持续时间
}


# =====================================================
# =============== 语法高亮函数 ===============
# =====================================================

# 性能优化：缓存 lexer 实例，避免重复创建
_lexer_cache: dict = {}

# 性能优化：大代码块阈值（超过此行数跳过语法高亮）
LARGE_CODE_THRESHOLD = 300


def get_highlighted_html(code: str, language: str, skip_highlighting: bool = False) -> str:
    """生成带语法高亮的 HTML
    
    使用 Pygments 生成带内联样式的 HTML。
    如果 Pygments 未安装或语言未知，则降级为纯文本显示。
    
    性能优化：
    - 缓存 lexer 实例
    - 可选跳过语法高亮（用于大代码块）
    
    Args:
        code: 原始代码文本
        language: 编程语言名称（如 "python", "javascript"）
        skip_highlighting: 是否跳过语法高亮（性能优化）
        
    Returns:
        带内联样式的 HTML 字符串
        
    Validates: Requirements 3.1-3.6
    """
    # 性能优化：跳过语法高亮时直接返回转义后的纯文本
    if skip_highlighting:
        import html
        escaped = html.escape(code)
        return f'<pre style="margin: 0;">{escaped}</pre>'
    
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name, TextLexer
        from pygments.formatters import HtmlFormatter
        from pygments.util import ClassNotFound
        
        # 获取词法分析器（使用缓存）
        # Requirements 3.1: 使用 get_lexer_by_name() 获取适当的 lexer
        # Requirements 3.2, 3.4: 未知语言降级到 TextLexer
        lang_key = language.strip().lower() if language else ""
        
        if lang_key in _lexer_cache:
            lexer = _lexer_cache[lang_key]
        else:
            try:
                if lang_key:
                    lexer = get_lexer_by_name(lang_key)
                else:
                    lexer = TextLexer()
            except ClassNotFound:
                lexer = TextLexer()
            _lexer_cache[lang_key] = lexer
        
        # 生成 HTML（内联样式）
        # Requirements 3.3: 使用 HtmlFormatter(style='monokai', noclasses=True)
        formatter = HtmlFormatter(
            style='monokai',
            noclasses=True,
            nowrap=False
        )
        highlighted = highlight(code, lexer, formatter)
        
        # Requirements 3.6: 包装在带样式的 body 中
        return highlighted
        
    except ImportError:
        # Requirements 3.5: Pygments 未安装时降级显示
        import html
        escaped = html.escape(code)
        return f'<pre style="margin: 0; white-space: pre-wrap;">{escaped}</pre>'


# =====================================================
# =============== CodeBlockWidget 组件 ===============
# =====================================================

class CodeBlockWidget(QFrame):
    """代码块组件 - VS Code 风格
    
    提供精美的代码块显示和一键复制功能：
    - Monokai 深色主题背景
    - Pygments 语法高亮（可选）
    - 一键复制按钮
    - "Done!" 反馈动画
    
    Signals:
        copied: 复制成功时发出，携带代码内容
    
    Feature: code-block-copy
    Validates: Requirements 1.1-1.8, 2.1-2.8, 3.1-3.6
    """
    
    # 信号：复制成功时发出，携带代码内容
    copied = Signal(str)
    
    def __init__(
        self,
        code: str,
        language: str = "",
        font_size: int = 13,
        parent: Optional[QWidget] = None
    ):
        """初始化代码块组件
        
        Args:
            code: 原始代码文本（不含 HTML）
            language: 编程语言名称（如 "python", "javascript"）
            font_size: 字体大小（pt），默认 13
            parent: 父组件
        """
        super().__init__(parent)
        
        # 存储原始代码（用于复制）
        # 处理空代码块
        self._code = code if code.strip() else "# (empty)"
        self._language = language.strip() if language else ""
        self._font_size = font_size
        
        # UI 组件引用
        self._copy_button: Optional[QPushButton] = None
        self._code_display: Optional[Union[QTextEdit, QPlainTextEdit]] = None
        self._language_label: Optional[QLabel] = None
        
        # 性能优化：检查是否为大代码块
        self._is_large_code = self._code.count('\n') + 1 > LARGE_CODE_THRESHOLD
        
        # 设置 UI
        self._setup_ui()
    
    def set_font_size(self, font_size: int) -> None:
        """设置字体大小
        
        Args:
            font_size: 字体大小（pt）
        """
        self._font_size = font_size
        
        # 更新代码显示区字体
        if self._code_display:
            font = self._code_display.font()
            font.setPointSize(font_size)
            self._code_display.setFont(font)
            
            # 如果不是大代码块，重新应用语法高亮
            if not self._is_large_code:
                self._highlight_code(self._code, self._language)
    
    def _setup_ui(self) -> None:
        """设置 UI 布局
        
        布局结构：
        - QVBoxLayout (主布局)
          - Header (QFrame): 语言标签 + 复制按钮
          - Code Display (QTextEdit): 代码内容
        
        Validates: Requirements 1.1-1.8
        """
        # 设置框架样式
        # Requirements 1.1: Monokai 背景色
        # Requirements 1.2: 8px 圆角
        self.setStyleSheet(f"""
            CodeBlockWidget {{
                background-color: {CODE_COLORS['background']};
                border-radius: {CODE_LAYOUT['border_radius']}px;
                border: none;
            }}
        """)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建头部栏
        header = self._create_header()
        main_layout.addWidget(header)
        
        # 创建代码显示区
        code_display = self._create_code_display()
        main_layout.addWidget(code_display)
        
        # 应用语法高亮
        self._highlight_code(self._code, self._language)
    
    def _create_header(self) -> QFrame:
        """创建头部栏（语言标签 + 复制按钮）
        
        Returns:
            头部栏 QFrame
            
        Validates: Requirements 1.3, 2.1, 2.5, 2.6, 2.8
        """
        header = QFrame()
        header.setFixedHeight(CODE_LAYOUT['header_height'])
        
        # Requirements 1.3: 头部栏背景色略浅
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {CODE_COLORS['header_bg']};
                border-top-left-radius: {CODE_LAYOUT['border_radius']}px;
                border-top-right-radius: {CODE_LAYOUT['border_radius']}px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
        """)
        
        # 头部布局
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(CODE_LAYOUT['padding'], 0, CODE_LAYOUT['padding'], 0)
        
        # 语言标签
        # Requirements 1.3: 左侧显示语言名称，使用 muted 颜色
        self._language_label = QLabel(self._language if self._language else "text")
        self._language_label.setStyleSheet(f"""
            QLabel {{
                color: {CODE_COLORS['text_muted']};
                font-size: 12px;
                font-family: {CODE_FONT['family']};
            }}
        """)
        header_layout.addWidget(self._language_label)
        
        # 弹性空间
        header_layout.addStretch()
        
        # 复制按钮
        # Requirements 2.1: 右上角显示复制按钮
        # Requirements 2.5: hover 效果
        # Requirements 2.6: cursor pointer
        # Requirements 2.8: 可见的 focus 指示器
        self._copy_button = QPushButton("复制")
        self._copy_button.setFixedSize(
            CODE_LAYOUT['button_width'],
            CODE_LAYOUT['button_height']
        )
        self._copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {CODE_COLORS['button_bg']};
                color: {CODE_COLORS['text']};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background-color: {CODE_COLORS['button_hover']};
            }}
            QPushButton:focus {{
                outline: 2px solid {CODE_COLORS['button_success']};
                outline-offset: 2px;
            }}
            QPushButton:disabled {{
                opacity: 0.7;
            }}
        """)
        self._copy_button.clicked.connect(self._on_copy_clicked)
        header_layout.addWidget(self._copy_button)
        
        return header
    
    def _create_code_display(self) -> Union[QTextEdit, QPlainTextEdit]:
        """创建代码显示区域
        
        Returns:
            代码显示组件（QTextEdit 或 QPlainTextEdit）
            
        Validates: Requirements 1.5, 1.6, 1.7, 5.4
        
        性能优化：
        - 大代码块使用 QPlainTextEdit（更快）
        - 小代码块使用 QTextEdit（支持 HTML 语法高亮）
        """
        # 性能优化：大代码块使用 QPlainTextEdit
        if self._is_large_code:
            self._code_display = QPlainTextEdit()
            self._code_display.setReadOnly(True)
            
            # 设置字体
            font = QFont()
            font.setFamilies(['Consolas', 'Monaco', 'Courier New', 'monospace'])
            font.setPointSize(self._font_size)
            self._code_display.setFont(font)
            
            # 设置样式
            self._code_display.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {CODE_COLORS['background']};
                    color: {CODE_COLORS['text']};
                    border: none;
                    border-bottom-left-radius: {CODE_LAYOUT['border_radius']}px;
                    border-bottom-right-radius: {CODE_LAYOUT['border_radius']}px;
                    padding: {CODE_LAYOUT['padding']}px;
                    selection-background-color: #49483E;
                }}
                QScrollBar:vertical {{
                    background-color: {CODE_COLORS['background']};
                    width: 10px;
                    margin: 0px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: #555555;
                    border-radius: 5px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: #666666;
                }}
                QScrollBar:horizontal {{
                    background-color: {CODE_COLORS['background']};
                    height: 10px;
                    margin: 0px;
                }}
                QScrollBar::handle:horizontal {{
                    background-color: #555555;
                    border-radius: 5px;
                    min-width: 20px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background-color: #666666;
                }}
                QScrollBar::add-line, QScrollBar::sub-line {{
                    height: 0px;
                    width: 0px;
                }}
                QScrollBar::add-page, QScrollBar::sub-page {{
                    background: none;
                }}
            """)
        else:
            # Requirements 1.7: 使用 QTextEdit 只读模式
            self._code_display = QTextEdit()
            self._code_display.setReadOnly(True)
            
            # Requirements 1.5: 等宽字体
            font = QFont()
            font.setFamilies(['Consolas', 'Monaco', 'Courier New', 'monospace'])
            font.setPointSize(self._font_size)
            self._code_display.setFont(font)
            
            # Requirements 1.6: 内部 padding
            # Requirements 5.4: 支持水平滚动
            self._code_display.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {CODE_COLORS['background']};
                    color: {CODE_COLORS['text']};
                    border: none;
                    border-bottom-left-radius: {CODE_LAYOUT['border_radius']}px;
                    border-bottom-right-radius: {CODE_LAYOUT['border_radius']}px;
                    padding: {CODE_LAYOUT['padding']}px;
                    selection-background-color: #49483E;
                }}
                QScrollBar:vertical {{
                    background-color: {CODE_COLORS['background']};
                    width: 10px;
                    margin: 0px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: #555555;
                    border-radius: 5px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: #666666;
                }}
                QScrollBar:horizontal {{
                    background-color: {CODE_COLORS['background']};
                    height: 10px;
                    margin: 0px;
                }}
                QScrollBar::handle:horizontal {{
                    background-color: #555555;
                    border-radius: 5px;
                    min-width: 20px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background-color: #666666;
                }}
                QScrollBar::add-line, QScrollBar::sub-line {{
                    height: 0px;
                    width: 0px;
                }}
                QScrollBar::add-page, QScrollBar::sub-page {{
                    background: none;
                }}
            """)
        
        return self._code_display
    
    def _highlight_code(self, code: str, language: str) -> None:
        """应用语法高亮到代码显示区
        
        Args:
            code: 原始代码
            language: 编程语言
            
        Validates: Requirements 1.4, 1.8, 3.1-3.6
        
        性能优化：
        - 大代码块（>300行）使用 QPlainTextEdit.setPlainText()
        - 小代码块使用 QTextEdit.setHtml() 支持语法高亮
        """
        # 性能优化：大代码块直接设置纯文本
        if self._is_large_code:
            self._code_display.setPlainText(code)
            return
        
        # 小代码块使用语法高亮
        highlighted_html = get_highlighted_html(code, language, skip_highlighting=False)
        
        # Requirements 1.8: off-white 文字颜色
        full_html = f"""
        <html>
        <head>
            <style>
                body {{
                    background-color: {CODE_COLORS['background']};
                    color: {CODE_COLORS['text']};
                    font-family: {CODE_FONT['family']};
                    font-size: {self._font_size}pt;
                    line-height: {CODE_FONT['line_height']};
                    margin: 0;
                    padding: 0;
                }}
                pre {{
                    margin: 0;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
            </style>
        </head>
        <body>
            {highlighted_html}
        </body>
        </html>
        """
        
        self._code_display.setHtml(full_html)
    
    def _on_copy_clicked(self) -> None:
        """处理复制按钮点击
        
        Validates: Requirements 2.2, 2.3, 2.4, 2.7
        """
        try:
            # Requirements 2.2: 复制原始代码到剪贴板
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(self._code)
            
            # Requirements 2.7: 禁用按钮防止重复点击
            self._copy_button.setEnabled(False)
            
            # Requirements 2.3: 显示成功反馈
            self._copy_button.setText("Done!")
            self._copy_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {CODE_COLORS['button_success']};
                    color: {CODE_COLORS['text']};
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                    padding: 2px 8px;
                }}
                QPushButton:disabled {{
                    background-color: {CODE_COLORS['button_success']};
                    color: {CODE_COLORS['text']};
                }}
            """)
            
            # 发出复制成功信号
            self.copied.emit(self._code)
            
            # Requirements 2.4: 1.5 秒后恢复原状
            QTimer.singleShot(
                CODE_ANIMATION['feedback_duration'],
                self._restore_copy_button
            )
            
        except Exception as e:
            # 复制失败时不显示成功反馈
            import logging
            logging.warning(f"复制到剪贴板失败: {e}")
    
    def _restore_copy_button(self) -> None:
        """恢复复制按钮原始状态
        
        Validates: Requirements 2.4
        """
        self._copy_button.setText("复制")
        self._copy_button.setEnabled(True)
        self._copy_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {CODE_COLORS['button_bg']};
                color: {CODE_COLORS['text']};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background-color: {CODE_COLORS['button_hover']};
            }}
            QPushButton:focus {{
                outline: 2px solid {CODE_COLORS['button_success']};
                outline-offset: 2px;
            }}
            QPushButton:disabled {{
                opacity: 0.7;
            }}
        """)
    
    def resizeEvent(self, event) -> None:
        """处理窗口大小变化
        
        Validates: Requirements 5.5
        """
        super().resizeEvent(event)
        # 按钮位置由布局自动管理，无需手动调整
    
    @property
    def code(self) -> str:
        """获取原始代码内容"""
        return self._code
    
    @property
    def language(self) -> str:
        """获取编程语言"""
        return self._language
