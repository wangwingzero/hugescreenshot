# =====================================================
# =============== 聚光灯效果 ===============
# =====================================================

"""
聚光灯效果 - 暗化屏幕，突出鼠标区域

Feature: mouse-highlight
Requirements: 5.1, 5.2, 5.3, 5.4
"""

from PySide6.QtGui import QPainter, QColor, QPainterPath
from PySide6.QtCore import QRect, QRectF, Qt

from screenshot_tool.ui.effects.base_effect import BaseEffect


class SpotlightEffect(BaseEffect):
    """聚光灯效果
    
    绘制全屏半透明遮罩，在鼠标位置创建透明圆形区域。
    """
    
    def draw(self, painter: QPainter, mouse_x: int, mouse_y: int, screen_geometry: QRect):
        """绘制聚光灯效果
        
        Args:
            painter: QPainter 对象
            mouse_x: 鼠标本地 X 坐标
            mouse_y: 鼠标本地 Y 坐标
            screen_geometry: 屏幕几何区域
        """
        if not self._config.spotlight_enabled:
            return
        
        # 获取配置
        radius = self._config.spotlight_radius
        darkness = self._config.spotlight_darkness  # 0-100
        
        # 计算透明度 (darkness 100 = 完全不透明黑色)
        alpha = int(255 * darkness / 100)
        
        # 创建遮罩路径
        # 外部矩形（整个窗口）
        outer_path = QPainterPath()
        window_rect = QRectF(0, 0, screen_geometry.width(), screen_geometry.height())
        outer_path.addRect(window_rect)
        
        # 内部圆形（透明区域）
        inner_path = QPainterPath()
        inner_path.addEllipse(
            float(mouse_x - radius),
            float(mouse_y - radius),
            float(radius * 2),
            float(radius * 2)
        )
        
        # 从外部路径减去内部路径
        mask_path = outer_path.subtracted(inner_path)
        
        # 绘制遮罩
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawPath(mask_path)
