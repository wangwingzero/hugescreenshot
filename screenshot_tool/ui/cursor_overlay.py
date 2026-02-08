# =====================================================
# =============== 鼠标图标覆盖层 ===============
# =====================================================

"""
鼠标图标覆盖层 - 显示特殊图标跟随鼠标

用于公文格式化模式，在鼠标旁边显示📄图标，
指示当前处于公文格式化模式。

Feature: word-gongwen-format
Requirements: 2.2, 2.3, 2.5
"""

from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QFont


class CursorOverlay(QWidget):
    """鼠标图标覆盖层 - 显示特殊图标跟随鼠标
    
    用于公文格式化模式或AI模式，在鼠标旁边显示图标，
    指示当前处于特殊模式。
    
    使用方法：
        overlay = CursorOverlay()  # 默认显示📄
        overlay = CursorOverlay(text="🤖")  # 自定义图标
        overlay.show_overlay()  # 显示并开始跟随鼠标
        overlay.hide_overlay()  # 隐藏并停止跟随
        overlay.set_text("🤖")  # 动态更改图标
    
    Attributes:
        ICON_TEXT: 默认显示的图标文本
        OFFSET_X: 图标相对鼠标的X偏移
        OFFSET_Y: 图标相对鼠标的Y偏移
    """
    
    ICON_TEXT = "📄"  # 默认文档图标
    OFFSET_X = 20     # 图标相对鼠标的X偏移
    OFFSET_Y = 20     # 图标相对鼠标的Y偏移
    UPDATE_INTERVAL = 16  # 更新间隔（毫秒），约60fps
    
    def __init__(self, parent=None, text: str = None):
        """初始化覆盖层
        
        Args:
            parent: 父窗口，默认为 None
            text: 显示的图标文本，默认为 "📄"
        """
        super().__init__(parent)
        # 实例变量，允许每个实例独立配置
        self._offset_x = self.OFFSET_X
        self._offset_y = self.OFFSET_Y
        self._text = text if text else self.ICON_TEXT
        self._setup_window()
        self._setup_ui()
        self._setup_timer()
    
    def _setup_window(self):
        """设置窗口属性
        
        设置窗口为：
        - 始终置顶
        - 无边框
        - 工具窗口（不在任务栏显示）
        - 鼠标穿透（点击穿透到下层窗口）
        - 透明背景
        """
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput  # 鼠标穿透
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(48, 48)
    
    def _setup_ui(self):
        """设置UI组件"""
        self._label = QLabel(self._text, self)
        self._label.setFont(QFont("Segoe UI Emoji", 28))
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setGeometry(0, 0, 48, 48)
        
        # 设置样式，添加轻微阴影效果
        self._label.setStyleSheet("""
            QLabel {
                color: #333333;
                background: transparent;
            }
        """)
    
    def _setup_timer(self):
        """设置定时器跟随鼠标"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._follow_cursor)
        self._timer.setInterval(self.UPDATE_INTERVAL)
    
    def _follow_cursor(self):
        """跟随鼠标位置
        
        将窗口移动到鼠标位置的右下方
        """
        pos = QCursor.pos()
        self.move(pos.x() + self._offset_x, pos.y() + self._offset_y)
    
    def show_overlay(self):
        """显示覆盖层并开始跟随鼠标
        
        Requirements: 2.2, 2.3
        """
        self._follow_cursor()  # 先移动到当前位置
        self._timer.start()
        self.show()
        self.raise_()  # 确保在最上层
    
    def hide_overlay(self):
        """隐藏覆盖层并停止跟随
        
        Requirements: 2.5
        """
        self._timer.stop()
        self.hide()
    
    @property
    def is_visible(self) -> bool:
        """是否可见
        
        Returns:
            是否正在显示
        """
        return self.isVisible()
    
    def set_icon(self, icon_text: str) -> None:
        """设置图标文本
        
        Args:
            icon_text: 新的图标文本（emoji或字符）
        """
        if icon_text:
            self._text = icon_text
            self._label.setText(icon_text)
    
    def set_text(self, text: str) -> None:
        """设置显示文本（set_icon 的别名）
        
        Args:
            text: 新的显示文本（emoji或字符）
        """
        self.set_icon(text)
    
    def get_text(self) -> str:
        """获取当前显示文本
        
        Returns:
            当前显示的文本
        """
        return self._text
    
    def set_offset(self, x: int, y: int) -> None:
        """设置图标相对鼠标的偏移
        
        Args:
            x: X偏移量
            y: Y偏移量
        """
        self._offset_x = int(x)
        self._offset_y = int(y)
