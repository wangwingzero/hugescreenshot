# =====================================================
# =============== 动画按钮组件 ===============
# =====================================================

"""
带有悬停和点击动画的按钮组件。

使用 QPropertyAnimation 实现平滑的状态过渡：
- 悬停动画：150ms (AnimationConstants.FAST)
- 点击动画：50ms (AnimationConstants.INSTANT)

Feature: performance-ui-optimization
Requirements: 7.1, 7.2, 8.5
"""

from typing import Optional

from PySide6.QtCore import (
    Qt,
    Property,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont
from PySide6.QtWidgets import QPushButton, QWidget, QGraphicsOpacityEffect

from screenshot_tool.ui.styles import (
    AnimationConstants,
    COLORS,
    RADIUS,
    SPACING,
    FONT,
    FONT_FAMILY,
)
from screenshot_tool.core.accessibility_manager import AccessibilityManager


class AnimatedButton(QPushButton):
    """带动画效果的按钮
    
    实现悬停过渡动画（150ms）和点击反馈动画（50ms）。
    使用 QPropertyAnimation 实现平滑的颜色过渡。
    
    UI/UX 最佳实践：
    - 悬停状态在 150ms 内完成过渡
    - 点击反馈在 50ms 内完成
    - 使用 ease-out 缓动曲线进入，ease-in 退出
    - 不使用 scale 变换避免布局抖动
    
    Feature: performance-ui-optimization
    Requirements: 7.1, 7.2
    
    Attributes:
        _hover_progress: 悬停动画进度 (0.0 - 1.0)
        _press_progress: 点击动画进度 (0.0 - 1.0)
    """
    
    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        style: str = "primary"
    ):
        """初始化动画按钮
        
        Args:
            text: 按钮文字
            parent: 父窗口
            style: 按钮样式 ("primary", "secondary", "danger")
        """
        super().__init__(text, parent)
        
        self._style = style
        self._hover_progress = 0.0
        self._press_progress = 0.0
        self._is_hovered = False
        self._is_pressed = False
        
        # 设置基本属性
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)
        
        # 创建悬停动画
        self._hover_animation = QPropertyAnimation(self, b"hover_progress")
        self._hover_animation.setDuration(AnimationConstants.FAST)  # 150ms
        self._hover_animation.setEasingCurve(AnimationConstants.EASE_OUT)
        
        # 创建点击动画
        self._press_animation = QPropertyAnimation(self, b"press_progress")
        self._press_animation.setDuration(AnimationConstants.INSTANT)  # 50ms
        self._press_animation.setEasingCurve(AnimationConstants.EASE_OUT)
        
        # 获取样式颜色
        self._setup_colors()
        
        # 注册到无障碍管理器以响应 reduced-motion 设置
        # Requirements: 8.5 - 尊重系统 reduced-motion 偏好
        self._accessibility_manager = AccessibilityManager.instance()
        self._accessibility_manager.register_animated_component(self)
        # 立即应用当前设置
        self.set_animations_enabled(self._accessibility_manager.animations_enabled)
    
    def _setup_colors(self):
        """根据样式设置颜色"""
        if self._style == "primary":
            self._bg_normal = QColor(COLORS["primary"])
            self._bg_hover = QColor(COLORS["primary_hover"])
            self._bg_pressed = QColor("#1E40AF")  # 更深的蓝色
            self._text_color = QColor("#FFFFFF")
            self._border_color = None
        elif self._style == "secondary":
            self._bg_normal = QColor(COLORS["surface"])
            self._bg_hover = QColor(COLORS["primary_light"])
            self._bg_pressed = QColor(COLORS["primary_light"])
            self._text_color = QColor(COLORS["text"])
            self._text_hover = QColor(COLORS["primary"])
            self._border_color = QColor(COLORS["border"])
            self._border_hover = QColor(COLORS["primary"])
        elif self._style == "danger":
            self._bg_normal = QColor(COLORS["error"])
            self._bg_hover = QColor("#DC2626")
            self._bg_pressed = QColor("#B91C1C")
            self._text_color = QColor("#FFFFFF")
            self._border_color = None
        else:
            # 默认使用 primary 样式
            self._bg_normal = QColor(COLORS["primary"])
            self._bg_hover = QColor(COLORS["primary_hover"])
            self._bg_pressed = QColor("#1E40AF")
            self._text_color = QColor("#FFFFFF")
            self._border_color = None
    
    # =====================================================
    # Qt Property 定义
    # =====================================================
    
    def get_hover_progress(self) -> float:
        """获取悬停动画进度"""
        return self._hover_progress
    
    def set_hover_progress(self, value: float):
        """设置悬停动画进度并触发重绘"""
        self._hover_progress = value
        self.update()
    
    hover_progress = Property(float, get_hover_progress, set_hover_progress)
    
    def get_press_progress(self) -> float:
        """获取点击动画进度"""
        return self._press_progress
    
    def set_press_progress(self, value: float):
        """设置点击动画进度并触发重绘"""
        self._press_progress = value
        self.update()
    
    press_progress = Property(float, get_press_progress, set_press_progress)
    
    # =====================================================
    # 事件处理
    # =====================================================
    
    def enterEvent(self, event):
        """鼠标进入事件 - 启动悬停动画
        
        Requirements: 7.1 - 悬停状态过渡在 150ms 内完成
        """
        super().enterEvent(event)
        self._is_hovered = True
        
        # 停止当前动画并启动新动画
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(1.0)
        self._hover_animation.setEasingCurve(AnimationConstants.EASE_OUT)
        self._hover_animation.start()
    
    def leaveEvent(self, event):
        """鼠标离开事件 - 反向悬停动画
        
        Requirements: 7.1 - 悬停状态过渡在 150ms 内完成
        """
        super().leaveEvent(event)
        self._is_hovered = False
        
        # 停止当前动画并启动反向动画
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(0.0)
        self._hover_animation.setEasingCurve(AnimationConstants.EASE_IN)
        self._hover_animation.start()
    
    def mousePressEvent(self, event):
        """鼠标按下事件 - 启动点击动画
        
        Requirements: 7.2 - 点击反馈在 50ms 内完成
        """
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            
            # 启动点击动画
            self._press_animation.stop()
            self._press_animation.setStartValue(self._press_progress)
            self._press_animation.setEndValue(1.0)
            self._press_animation.start()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 反向点击动画
        
        Requirements: 7.2 - 点击反馈在 50ms 内完成
        """
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            
            # 启动反向点击动画
            self._press_animation.stop()
            self._press_animation.setStartValue(self._press_progress)
            self._press_animation.setEndValue(0.0)
            self._press_animation.start()
    
    # =====================================================
    # 绘制
    # =====================================================
    
    def paintEvent(self, event):
        """自定义绘制 - 实现动画颜色过渡"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        radius = RADIUS["md"]
        
        # 计算当前背景颜色（基于动画进度插值）
        bg_color = self._interpolate_color(
            self._bg_normal,
            self._bg_hover,
            self._hover_progress
        )
        
        # 如果有点击动画，进一步插值到 pressed 颜色
        if self._press_progress > 0:
            bg_color = self._interpolate_color(
                bg_color,
                self._bg_pressed,
                self._press_progress
            )
        
        # 绘制背景
        painter.setBrush(QBrush(bg_color))
        
        # 绘制边框（如果有）
        if self._border_color:
            if self._style == "secondary" and self._hover_progress > 0:
                border_color = self._interpolate_color(
                    self._border_color,
                    self._border_hover,
                    self._hover_progress
                )
            else:
                border_color = self._border_color
            painter.setPen(QPen(border_color, 1))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        
        painter.drawRoundedRect(rect, radius, radius)
        
        # 计算文字颜色
        if self._style == "secondary" and hasattr(self, "_text_hover"):
            text_color = self._interpolate_color(
                self._text_color,
                self._text_hover,
                self._hover_progress
            )
        else:
            text_color = self._text_color
        
        # 绘制文字
        painter.setPen(text_color)
        font = QFont()
        font.setFamily(FONT_FAMILY.split(",")[0].strip('"'))
        font.setPointSize(FONT["sm"])
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        
        painter.end()
    
    def _interpolate_color(
        self,
        color1: QColor,
        color2: QColor,
        progress: float
    ) -> QColor:
        """在两个颜色之间插值
        
        Args:
            color1: 起始颜色
            color2: 结束颜色
            progress: 插值进度 (0.0 - 1.0)
            
        Returns:
            插值后的颜色
        """
        r = int(color1.red() + (color2.red() - color1.red()) * progress)
        g = int(color1.green() + (color2.green() - color1.green()) * progress)
        b = int(color1.blue() + (color2.blue() - color1.blue()) * progress)
        a = int(color1.alpha() + (color2.alpha() - color1.alpha()) * progress)
        return QColor(r, g, b, a)
    
    # =====================================================
    # 公共方法
    # =====================================================
    
    def __del__(self):
        """析构函数 - 从无障碍管理器取消注册
        
        避免内存泄漏和悬空引用。
        """
        try:
            if hasattr(self, '_accessibility_manager') and self._accessibility_manager:
                self._accessibility_manager.unregister_animated_component(self)
        except Exception:
            # 忽略析构时的异常
            pass
    
    def set_style(self, style: str):
        """设置按钮样式
        
        Args:
            style: 按钮样式 ("primary", "secondary", "danger")
        """
        self._style = style
        self._setup_colors()
        self.update()
    
    def set_animations_enabled(self, enabled: bool):
        """启用或禁用动画
        
        用于支持系统 reduced-motion 偏好设置。
        
        Requirements: 8.5 - 尊重系统 reduced-motion 偏好
        
        Args:
            enabled: 是否启用动画
        """
        if enabled:
            self._hover_animation.setDuration(AnimationConstants.FAST)
            self._press_animation.setDuration(AnimationConstants.INSTANT)
        else:
            # 禁用动画时设置时长为 0
            self._hover_animation.setDuration(0)
            self._press_animation.setDuration(0)
