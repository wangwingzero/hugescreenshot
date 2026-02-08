# =====================================================
# =============== 成功/错误指示器组件 ===============
# =====================================================

"""
成功和错误状态指示器组件。

使用 QPropertyAnimation 实现平滑的状态动画：
- 成功动画：200-500ms (AnimationConstants.SUCCESS)
- 错误 shake 动画：300ms (AnimationConstants.SLOW)

Feature: performance-ui-optimization
Requirements: 7.3, 7.4, 8.5
"""

from typing import Optional
from enum import Enum

from PySide6.QtCore import (
    Qt,
    Property,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    Signal,
    QPoint,
    QSize,
    QRectF,
)
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget

from screenshot_tool.ui.styles import (
    AnimationConstants,
    COLORS,
    RADIUS,
)
from screenshot_tool.core.accessibility_manager import AccessibilityManager


class IndicatorState(Enum):
    """指示器状态枚举"""
    IDLE = "idle"
    SUCCESS = "success"
    ERROR = "error"


class SuccessIndicator(QWidget):
    """成功/错误状态指示器
    
    实现成功动画（200-500ms）和错误 shake 动画。
    使用 QPropertyAnimation 实现平滑的动画效果。
    
    UI/UX 最佳实践：
    - 成功动画持续 200-500ms，使用 checkmark 图标
    - 错误动画使用 subtle shake（水平位移 ±4px）
    - 使用 ease-out 缓动曲线
    - 动画完成后自动隐藏（可配置）
    
    Feature: performance-ui-optimization
    Requirements: 7.3, 7.4
    
    Signals:
        animation_finished: 动画完成信号
    """
    
    animation_finished = Signal()
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        size: int = 32,
        auto_hide: bool = True,
        auto_hide_delay: int = 1500
    ):
        """初始化成功指示器
        
        Args:
            parent: 父窗口
            size: 指示器大小（像素）
            auto_hide: 动画完成后是否自动隐藏
            auto_hide_delay: 自动隐藏延迟（毫秒）
        """
        super().__init__(parent)
        
        self._size = size
        self._auto_hide = auto_hide
        self._auto_hide_delay = auto_hide_delay
        self._state = IndicatorState.IDLE
        
        # 动画属性
        self._animation_progress = 0.0
        self._shake_offset = 0.0
        self._opacity = 0.0
        
        # 设置固定大小
        self.setFixedSize(size, size)
        
        # 默认隐藏
        self.hide()
        
        # 创建成功动画组
        self._success_animation = self._create_success_animation()
        
        # 创建错误 shake 动画组
        self._error_animation = self._create_error_animation()
        
        # 自动隐藏定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)
        
        # 注册到无障碍管理器以响应 reduced-motion 设置
        # Requirements: 8.5 - 尊重系统 reduced-motion 偏好
        self._accessibility_manager = AccessibilityManager.instance()
        self._accessibility_manager.register_animated_component(self)
        # 立即应用当前设置
        self.set_animations_enabled(self._accessibility_manager.animations_enabled)
    
    # =====================================================
    # 动画创建
    # =====================================================
    
    def _create_success_animation(self) -> QSequentialAnimationGroup:
        """创建成功动画组
        
        Requirements: 7.3 - 成功动画持续 200-500ms
        
        动画序列：
        1. 淡入 + 缩放进入 (100ms)
        2. Checkmark 绘制动画 (300ms)
        """
        group = QSequentialAnimationGroup(self)
        
        # 淡入动画
        fade_in = QPropertyAnimation(self, b"opacity")
        fade_in.setDuration(100)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(AnimationConstants.EASE_OUT)
        
        # Checkmark 绘制动画
        draw_anim = QPropertyAnimation(self, b"animation_progress")
        draw_anim.setDuration(AnimationConstants.SUCCESS - 100)  # 300ms
        draw_anim.setStartValue(0.0)
        draw_anim.setEndValue(1.0)
        draw_anim.setEasingCurve(AnimationConstants.EASE_OUT)
        
        group.addAnimation(fade_in)
        group.addAnimation(draw_anim)
        group.finished.connect(self._on_animation_finished)
        
        return group
    
    def _create_error_animation(self) -> QSequentialAnimationGroup:
        """创建错误 shake 动画组
        
        Requirements: 7.4 - 错误时显示 subtle shake 动画
        
        动画序列：
        1. 淡入 (50ms)
        2. Shake 左右摇晃 (250ms, 3次)
        """
        group = QSequentialAnimationGroup(self)
        
        # 淡入动画
        fade_in = QPropertyAnimation(self, b"opacity")
        fade_in.setDuration(50)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(AnimationConstants.EASE_OUT)
        group.addAnimation(fade_in)
        
        # Shake 动画 - 3次左右摇晃
        shake_duration = 80  # 每次摇晃时长
        shake_distance = 4   # 摇晃距离（像素）
        
        for i in range(3):
            # 向右
            shake_right = QPropertyAnimation(self, b"shake_offset")
            shake_right.setDuration(shake_duration // 2)
            shake_right.setStartValue(0.0 if i == 0 else -shake_distance)
            shake_right.setEndValue(shake_distance)
            shake_right.setEasingCurve(AnimationConstants.EASE_OUT)
            group.addAnimation(shake_right)
            
            # 向左
            shake_left = QPropertyAnimation(self, b"shake_offset")
            shake_left.setDuration(shake_duration // 2)
            shake_left.setStartValue(shake_distance)
            shake_left.setEndValue(-shake_distance if i < 2 else 0.0)
            shake_left.setEasingCurve(AnimationConstants.EASE_OUT)
            group.addAnimation(shake_left)
        
        group.finished.connect(self._on_animation_finished)
        
        return group
    
    # =====================================================
    # Qt Property 定义
    # =====================================================
    
    def get_animation_progress(self) -> float:
        """获取动画进度"""
        return self._animation_progress
    
    def set_animation_progress(self, value: float):
        """设置动画进度并触发重绘"""
        self._animation_progress = value
        self.update()
    
    animation_progress = Property(float, get_animation_progress, set_animation_progress)
    
    def get_shake_offset(self) -> float:
        """获取 shake 偏移量"""
        return self._shake_offset
    
    def set_shake_offset(self, value: float):
        """设置 shake 偏移量并触发重绘"""
        self._shake_offset = value
        self.update()
    
    shake_offset = Property(float, get_shake_offset, set_shake_offset)
    
    def get_opacity(self) -> float:
        """获取透明度"""
        return self._opacity
    
    def set_opacity(self, value: float):
        """设置透明度并触发重绘"""
        self._opacity = value
        self.update()
    
    opacity = Property(float, get_opacity, set_opacity)
    
    # =====================================================
    # 公共方法
    # =====================================================
    
    def show_success(self):
        """显示成功动画
        
        Requirements: 7.3 - 成功动画持续 200-500ms
        """
        self._stop_all_animations()
        self._state = IndicatorState.SUCCESS
        self._animation_progress = 0.0
        self._shake_offset = 0.0
        self._opacity = 0.0
        
        self.show()
        self._success_animation.start()
    
    def show_error(self):
        """显示错误 shake 动画
        
        Requirements: 7.4 - 错误时显示 subtle shake 动画
        """
        self._stop_all_animations()
        self._state = IndicatorState.ERROR
        self._animation_progress = 1.0  # 错误图标立即显示
        self._shake_offset = 0.0
        self._opacity = 0.0
        
        self.show()
        self._error_animation.start()
    
    def reset(self):
        """重置指示器状态"""
        self._stop_all_animations()
        self._hide_timer.stop()
        self._state = IndicatorState.IDLE
        self._animation_progress = 0.0
        self._shake_offset = 0.0
        self._opacity = 0.0
        self.hide()
    
    def set_auto_hide(self, enabled: bool, delay: int = 1500):
        """设置自动隐藏
        
        Args:
            enabled: 是否启用自动隐藏
            delay: 自动隐藏延迟（毫秒）
        """
        self._auto_hide = enabled
        self._auto_hide_delay = delay
    
    def set_animations_enabled(self, enabled: bool):
        """启用或禁用动画
        
        用于支持系统 reduced-motion 偏好设置。
        
        Requirements: 8.5 - 尊重系统 reduced-motion 偏好
        
        Args:
            enabled: 是否启用动画
        """
        if enabled:
            # 恢复正常动画时长
            self._success_animation = self._create_success_animation()
            self._error_animation = self._create_error_animation()
        else:
            # 禁用动画时创建即时动画
            self._success_animation = self._create_instant_animation()
            self._error_animation = self._create_instant_animation()
    
    def _create_instant_animation(self) -> QSequentialAnimationGroup:
        """创建即时动画（无动画效果）"""
        group = QSequentialAnimationGroup(self)
        
        # 即时显示
        instant = QPropertyAnimation(self, b"opacity")
        instant.setDuration(0)
        instant.setStartValue(1.0)
        instant.setEndValue(1.0)
        group.addAnimation(instant)
        
        # 即时完成进度
        progress = QPropertyAnimation(self, b"animation_progress")
        progress.setDuration(0)
        progress.setStartValue(1.0)
        progress.setEndValue(1.0)
        group.addAnimation(progress)
        
        group.finished.connect(self._on_animation_finished)
        
        return group
    
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
    
    @property
    def state(self) -> IndicatorState:
        """获取当前状态"""
        return self._state
    
    # =====================================================
    # 内部方法
    # =====================================================
    
    def _stop_all_animations(self):
        """停止所有动画"""
        self._success_animation.stop()
        self._error_animation.stop()
        self._hide_timer.stop()
    
    def _on_animation_finished(self):
        """动画完成回调"""
        self.animation_finished.emit()
        
        if self._auto_hide:
            self._hide_timer.start(self._auto_hide_delay)
    
    def _on_hide_timeout(self):
        """自动隐藏超时回调"""
        # 淡出动画
        fade_out = QPropertyAnimation(self, b"opacity")
        fade_out.setDuration(AnimationConstants.FAST)
        fade_out.setStartValue(self._opacity)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(AnimationConstants.EASE_IN)
        fade_out.finished.connect(self.hide)
        fade_out.start()
    
    # =====================================================
    # 绘制
    # =====================================================
    
    def paintEvent(self, event):
        """自定义绘制 - 绘制成功/错误图标"""
        if self._opacity <= 0:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 应用透明度
        painter.setOpacity(self._opacity)
        
        # 应用 shake 偏移
        if self._shake_offset != 0:
            painter.translate(self._shake_offset, 0)
        
        # 根据状态绘制
        if self._state == IndicatorState.SUCCESS:
            self._draw_success(painter)
        elif self._state == IndicatorState.ERROR:
            self._draw_error(painter)
        
        painter.end()
    
    def _draw_success(self, painter: QPainter):
        """绘制成功图标（带动画的 checkmark）
        
        Requirements: 7.3 - 成功动画
        """
        size = self._size
        center = size / 2
        
        # 绘制圆形背景
        bg_color = QColor(COLORS["success"])
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        
        # 绘制 checkmark（带动画进度）
        if self._animation_progress > 0:
            pen = QPen(QColor("#FFFFFF"))
            pen.setWidth(max(2, size // 12))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            
            # Checkmark 路径点（相对于中心）
            # 起点 -> 中点 -> 终点
            start_x = center - size * 0.2
            start_y = center
            mid_x = center - size * 0.05
            mid_y = center + size * 0.15
            end_x = center + size * 0.25
            end_y = center - size * 0.15
            
            # 根据动画进度绘制
            path = QPainterPath()
            path.moveTo(start_x, start_y)
            
            if self._animation_progress <= 0.4:
                # 第一段：起点到中点
                t = self._animation_progress / 0.4
                current_x = start_x + (mid_x - start_x) * t
                current_y = start_y + (mid_y - start_y) * t
                path.lineTo(current_x, current_y)
            else:
                # 第一段完成
                path.lineTo(mid_x, mid_y)
                
                # 第二段：中点到终点
                t = (self._animation_progress - 0.4) / 0.6
                current_x = mid_x + (end_x - mid_x) * t
                current_y = mid_y + (end_y - mid_y) * t
                path.lineTo(current_x, current_y)
            
            painter.drawPath(path)
    
    def _draw_error(self, painter: QPainter):
        """绘制错误图标（X 标记）
        
        Requirements: 7.4 - 错误指示器
        """
        size = self._size
        center = size / 2
        
        # 绘制圆形背景
        bg_color = QColor(COLORS["error"])
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        
        # 绘制 X 标记
        pen = QPen(QColor("#FFFFFF"))
        pen.setWidth(max(2, size // 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        # X 的两条线
        offset = size * 0.2
        painter.drawLine(
            int(center - offset), int(center - offset),
            int(center + offset), int(center + offset)
        )
        painter.drawLine(
            int(center + offset), int(center - offset),
            int(center - offset), int(center + offset)
        )
