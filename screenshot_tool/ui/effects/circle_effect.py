# =====================================================
# =============== 光圈效果 ===============
# =====================================================

"""
光圈效果 - 在鼠标周围绘制圆圈

Feature: mouse-highlight
Requirements: 4.1, 4.2, 4.3, 4.4
"""

from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import QRect, Qt

from screenshot_tool.ui.effects.base_effect import BaseEffect


class CircleEffect(BaseEffect):
    """光圈效果
    
    在鼠标位置周围绘制一个圆圈，支持配置半径、粗细和颜色。
    """
    
    def draw(self, painter: QPainter, mouse_x: int, mouse_y: int, screen_geometry: QRect):
        """绘制光圈
        
        Args:
            painter: QPainter 对象
            mouse_x: 鼠标本地 X 坐标
            mouse_y: 鼠标本地 Y 坐标
            screen_geometry: 屏幕几何区域
        """
        if not self._config.circle_enabled:
            return
        
        # 获取配置
        radius = self._config.circle_radius
        thickness = self._config.circle_thickness
        color_hex = self._theme.get("circle_color", "#FFD700")
        
        # 设置画笔
        color = QColor(color_hex)
        pen = QPen(color)
        pen.setWidth(thickness)
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # 绘制圆圈
        painter.drawEllipse(
            mouse_x - radius,
            mouse_y - radius,
            radius * 2,
            radius * 2
        )
