# =====================================================
# =============== 主题选择按钮 ===============
# =====================================================

"""
主题选择按钮，显示主题名称和颜色预览圆点。

Feature: mouse-highlight-debug-panel
Requirements: 4.2, 4.3
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import QPushButton, QWidget


class ThemeButton(QPushButton):
    """主题选择按钮
    
    显示主题名称和颜色预览圆点。
    选中状态有明显的视觉区分（边框高亮）。
    
    UI/UX 最佳实践：
    - 不仅用颜色传达信息，配合文字标签
    - hover 状态有视觉反馈
    - 选中状态使用边框而非仅颜色变化
    
    Feature: mouse-highlight-debug-panel
    Requirements: 4.2, 4.3
    """
    
    def __init__(
        self,
        theme_key: str,
        theme_data: dict,
        parent: Optional[QWidget] = None
    ):
        """初始化主题按钮
        
        Args:
            theme_key: 主题键名（如 "classic_yellow"）
            theme_data: 主题数据字典，包含 name, circle_color 等
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._theme_key = theme_key
        self._theme_data = theme_data
        self._selected = False
        
        # 设置按钮文字
        self.setText(theme_data.get("name", theme_key))
        self.setCheckable(True)
        self.setMinimumHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 设置样式
        self._update_style()
    
    @property
    def theme_key(self) -> str:
        """获取主题键名"""
        return self._theme_key
    
    def set_selected(self, selected: bool):
        """设置选中状态"""
        self._selected = selected
        self.setChecked(selected)
        self._update_style()
    
    def is_selected(self) -> bool:
        """获取选中状态"""
        return self._selected
    
    def _update_style(self):
        """更新按钮样式
        
        选中状态：蓝色边框 + 浅蓝背景
        未选中状态：灰色边框 + 白色背景
        hover 状态：浅灰背景
        """
        if self._selected:
            self.setStyleSheet("""
                QPushButton {
                    border: 2px solid #1890ff;
                    border-radius: 6px;
                    background-color: #e6f7ff;
                    padding: 6px 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #bae7ff;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    border: 1px solid #d9d9d9;
                    border-radius: 6px;
                    background-color: white;
                    padding: 6px 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    border-color: #1890ff;
                    background-color: #fafafa;
                }
            """)
    
    def paintEvent(self, event):
        """绘制事件：添加颜色预览圆点"""
        super().paintEvent(event)
        
        # 在按钮右侧绘制颜色预览圆点
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        color = QColor(self._theme_data.get("circle_color", "#FFD700"))
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        # 圆点位置：右侧居中
        radius = 8
        x = self.width() - radius * 2 - 10
        y = (self.height() - radius * 2) // 2
        painter.drawEllipse(x, y, radius * 2, radius * 2)
        
        painter.end()
