# =====================================================
# =============== 点击涟漪效果 ===============
# =====================================================

"""
点击涟漪效果 - 点击时显示扩散动画

Feature: mouse-highlight
Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import time
from dataclasses import dataclass
from typing import List

from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import QRect, Qt

from screenshot_tool.ui.effects.base_effect import BaseEffect


@dataclass
class RippleState:
    """单个涟漪动画状态"""
    x: int                    # 中心 X 坐标（全局）
    y: int                    # 中心 Y 坐标（全局）
    start_time: float         # 开始时间 (time.time())
    is_left: bool             # 是否左键点击
    
    def get_progress(self, duration_ms: int) -> float:
        """获取动画进度 (0.0 - 1.0)
        
        Args:
            duration_ms: 动画时长（毫秒）
            
        Returns:
            进度值，0.0 表示开始，1.0 表示结束
        """
        elapsed = (time.time() - self.start_time) * 1000
        return min(1.0, elapsed / duration_ms)
    
    def is_finished(self, duration_ms: int) -> bool:
        """动画是否已完成
        
        Args:
            duration_ms: 动画时长（毫秒）
            
        Returns:
            是否已完成
        """
        return self.get_progress(duration_ms) >= 1.0


class ClickRippleEffect(BaseEffect):
    """点击涟漪效果
    
    点击时显示从中心向外扩散的圆圈动画。
    支持多个涟漪并发显示。
    """
    
    # 涟漪半径范围
    START_RADIUS = 20
    END_RADIUS = 80
    
    def __init__(self, config, theme):
        super().__init__(config, theme)
        self._active_ripples: List[RippleState] = []
    
    def add_ripple(self, x: int, y: int, is_left: bool):
        """添加一个涟漪动画
        
        Args:
            x: 全局 X 坐标
            y: 全局 Y 坐标
            is_left: 是否左键点击
        """
        if not self._config.click_effect_enabled:
            return
        
        ripple = RippleState(
            x=x,
            y=y,
            start_time=time.time(),
            is_left=is_left
        )
        self._active_ripples.append(ripple)
    
    def draw(self, painter: QPainter, mouse_x: int, mouse_y: int, screen_geometry: QRect):
        """绘制所有活动的涟漪
        
        Args:
            painter: QPainter 对象
            mouse_x: 鼠标本地 X 坐标（未使用）
            mouse_y: 鼠标本地 Y 坐标（未使用）
            screen_geometry: 屏幕几何区域
        """
        if not self._config.click_effect_enabled:
            return
        
        duration = self._config.ripple_duration
        
        # 清理已完成的涟漪
        self._active_ripples = [
            r for r in self._active_ripples
            if not r.is_finished(duration)
        ]
        
        # 绘制每个涟漪
        for ripple in self._active_ripples:
            self._draw_ripple(painter, ripple, screen_geometry, duration)
    
    def _draw_ripple(
        self,
        painter: QPainter,
        ripple: RippleState,
        screen_geometry: QRect,
        duration: int
    ):
        """绘制单个涟漪
        
        Args:
            painter: QPainter 对象
            ripple: 涟漪状态（坐标为物理像素）
            screen_geometry: 屏幕几何区域（逻辑像素）
            duration: 动画时长
        
        Note:
            涟漪坐标来自 Windows 鼠标钩子，是物理像素。
            需要转换为逻辑像素以匹配 Qt 的屏幕几何。
        """
        # 获取设备像素比，将物理像素转换为逻辑像素
        dpr = painter.device().devicePixelRatio() if painter.device() else 1.0
        logical_x = int(ripple.x / dpr)
        logical_y = int(ripple.y / dpr)
        
        # 检查涟漪是否在当前屏幕（使用逻辑坐标）
        if not screen_geometry.contains(logical_x, logical_y):
            return
        
        # 转换为本地坐标（相对于覆盖层窗口）
        local_x = logical_x - screen_geometry.x()
        local_y = logical_y - screen_geometry.y()
        
        # 计算进度
        progress = ripple.get_progress(duration)
        
        # 使用缓动函数（ease-out）
        eased_progress = 1 - (1 - progress) ** 2
        
        # 计算当前半径
        radius = self.START_RADIUS + (self.END_RADIUS - self.START_RADIUS) * eased_progress
        
        # 计算透明度（从 255 衰减到 0）
        alpha = int(255 * (1 - progress))
        
        # 获取颜色
        if ripple.is_left:
            color_hex = self._theme.get("left_click_color", "#FFD700")
        else:
            color_hex = self._theme.get("right_click_color", "#FF6B6B")
        
        color = QColor(color_hex)
        color.setAlpha(alpha)
        
        # 设置画笔
        pen = QPen(color)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # 绘制圆圈
        painter.drawEllipse(
            int(local_x - radius),
            int(local_y - radius),
            int(radius * 2),
            int(radius * 2)
        )
    
    def is_animated(self) -> bool:
        """是否有活动动画"""
        return len(self._active_ripples) > 0
    
    def clear_ripples(self):
        """清除所有涟漪"""
        self._active_ripples.clear()
