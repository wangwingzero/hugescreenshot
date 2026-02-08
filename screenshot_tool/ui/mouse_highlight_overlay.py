# =====================================================
# =============== 鼠标高亮覆盖层窗口 ===============
# =====================================================

"""
全屏透明覆盖层窗口 - 用于绘制鼠标高亮效果

使用 Qt.WindowTransparentForInput 实现真正的鼠标穿透，
通过 QPainter 绘制各种高亮效果。

Feature: mouse-highlight
Requirements: 3.1, 3.2, 3.3, 3.4, 10.4, 10.5, 11.2
"""

import time
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import QPainter, QPaintEvent, QColor, QScreen
from PySide6.QtWidgets import QWidget

from screenshot_tool.core.async_logger import async_debug_log
from screenshot_tool.core.topmost_window_manager import TopmostWindowManager

if TYPE_CHECKING:
    from screenshot_tool.ui.effects.base_effect import BaseEffect


class MouseHighlightOverlay(QWidget):
    """全屏透明覆盖层窗口
    
    负责在屏幕上绘制鼠标高亮效果。每个显示器一个实例。
    
    特性:
        - 全屏透明窗口
        - 鼠标穿透（不影响正常操作）
        - 60 FPS 定时器控制重绘
        - 支持多种效果组合
        - 空闲渲染优化（鼠标静止且无动画时暂停）
        - 效果故障隔离（单个效果异常不影响其他效果）
    
    使用示例:
        overlay = MouseHighlightOverlay(screen.geometry(), effects)
        overlay.show()
        overlay.update_mouse_position(x, y)
    """
    
    # 60 FPS 刷新间隔（毫秒）
    REFRESH_INTERVAL_MS = 16
    
    # 空闲超时（毫秒）- 鼠标静止多久后暂停渲染
    IDLE_TIMEOUT_MS = 100
    
    def __init__(
        self,
        screen_geometry: QRect,
        effects: Optional[List["BaseEffect"]] = None,
        parent: Optional[QWidget] = None
    ):
        """初始化覆盖层窗口
        
        Args:
            screen_geometry: 屏幕几何区域
            effects: 效果绘制器列表
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._screen_geometry = screen_geometry
        self._effects: List["BaseEffect"] = effects or []
        self._screen: Optional[QScreen] = None  # 关联的 QScreen 对象
        
        # 鼠标位置（全局坐标）
        self._mouse_x: int = 0
        self._mouse_y: int = 0
        
        # 上次鼠标位置（用于检测移动）
        self._last_mouse_x: int = 0
        self._last_mouse_y: int = 0
        
        # 上次鼠标移动时间
        self._last_mouse_move_time: float = 0
        
        # 是否有活动动画
        self._has_animation: bool = False
        
        # 是否暂停渲染（空闲优化）
        self._render_paused: bool = True
        
        # 设置窗口
        self._setup_window()
        
        # 设置刷新定时器
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh)
        self._refresh_timer.setInterval(self.REFRESH_INTERVAL_MS)
    
    def _setup_window(self):
        """设置窗口属性"""
        # 窗口标志（必须在 setAttribute 之前设置）
        # Qt.WindowTransparentForInput 是 Windows 平台实现真正鼠标穿透的关键
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |    # 始终置顶
            Qt.WindowType.FramelessWindowHint |     # 无边框
            Qt.WindowType.Tool |                    # 不在任务栏显示
            Qt.WindowType.WindowTransparentForInput # 鼠标穿透（关键！）
        )
        
        # 窗口属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)      # 背景透明
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # Qt 层面鼠标穿透
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)      # 显示时不获取焦点
        
        # 设置窗口几何
        self.setGeometry(self._screen_geometry)
        
        # 注册到全局置顶窗口管理器
        # Feature: emergency-esc-exit
        # Requirements: 3.1, 4.1
        # 注意：由于使用 WindowTransparentForInput，此窗口无法接收键盘事件
        # ESC 退出需要通过全局管理器或主窗口来处理
        TopmostWindowManager.instance().register_window(
            self,
            window_type="MouseHighlightOverlay",
            can_receive_focus=False  # 无法接收焦点
        )
        
        async_debug_log(f"覆盖层窗口创建: {self._screen_geometry}")
    
    def update_mouse_position(self, x: int, y: int):
        """更新鼠标位置
        
        Args:
            x: 全局 X 坐标（物理像素，来自 Windows 鼠标钩子）
            y: 全局 Y 坐标（物理像素，来自 Windows 鼠标钩子）
        
        Note:
            Windows 鼠标钩子返回的是物理像素坐标，需要转换为逻辑像素坐标
            以匹配 Qt 的屏幕几何。
        """
        # 检查是否真的移动了
        if x != self._mouse_x or y != self._mouse_y:
            self._last_mouse_x = self._mouse_x
            self._last_mouse_y = self._mouse_y
            self._mouse_x = x
            self._mouse_y = y
            self._last_mouse_move_time = time.time()
        
        # 恢复渲染
        if self._render_paused:
            self._render_paused = False
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
    
    def add_click_ripple(self, x: int, y: int, is_left: bool):
        """添加点击涟漪动画
        
        Args:
            x: 全局 X 坐标（物理像素）
            y: 全局 Y 坐标（物理像素）
            is_left: 是否左键点击
        """
        # 检查点击是否在当前屏幕范围内（需要 DPI 转换）
        if not self.is_mouse_in_screen(x, y):
            return
        
        # 通知涟漪效果
        for effect in self._effects:
            if hasattr(effect, 'add_ripple'):
                effect.add_ripple(x, y, is_left)
        
        # 确保渲染活跃
        self._has_animation = True
        if self._render_paused:
            self._render_paused = False
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
    
    def set_effects(self, effects: List["BaseEffect"]):
        """设置效果列表（热更新）
        
        Args:
            effects: 新的效果列表
        """
        self._effects = effects
        self.update()
    
    def start_rendering(self):
        """开始渲染"""
        self._render_paused = False
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()
    
    def stop_rendering(self):
        """停止渲染"""
        self._render_paused = True
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
    
    def is_mouse_in_screen(self, x: int, y: int) -> bool:
        """检查鼠标是否在当前屏幕范围内
        
        Args:
            x: 全局 X 坐标（物理像素）
            y: 全局 Y 坐标（物理像素）
            
        Returns:
            是否在屏幕范围内
        
        Note:
            需要将物理像素坐标转换为逻辑像素坐标进行比较。
        """
        # 获取设备像素比
        dpr = self.devicePixelRatio()
        # 将物理像素转换为逻辑像素
        logical_x = int(x / dpr)
        logical_y = int(y / dpr)
        return self._screen_geometry.contains(QPoint(logical_x, logical_y))
    
    def paintEvent(self, event: QPaintEvent):
        """绘制所有效果"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 清除背景（完全透明）
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        
        # 检查鼠标是否在当前屏幕
        mouse_in_screen = self.is_mouse_in_screen(self._mouse_x, self._mouse_y)
        
        # 获取设备像素比，将物理像素转换为逻辑像素
        dpr = self.devicePixelRatio()
        logical_mouse_x = int(self._mouse_x / dpr)
        logical_mouse_y = int(self._mouse_y / dpr)
        
        # 转换为本地坐标（相对于覆盖层窗口）
        local_x = logical_mouse_x - self._screen_geometry.x()
        local_y = logical_mouse_y - self._screen_geometry.y()
        
        # 绘制所有效果
        for effect in self._effects:
            try:
                # 只在鼠标在当前屏幕时绘制跟随效果
                # 涟漪效果有自己的坐标，不受此限制
                if mouse_in_screen or hasattr(effect, 'add_ripple'):
                    effect.draw(painter, local_x, local_y, self._screen_geometry)
            except Exception as e:
                # 单个效果失败不影响其他效果
                async_debug_log(f"效果绘制失败 [{effect.__class__.__name__}]: {e}")
        
        painter.end()
    
    def _on_refresh(self):
        """刷新定时器回调
        
        实现空闲渲染优化（Property 12）和动画清理（Property 13）。
        
        Feature: mouse-highlight
        Requirements: 10.4, 10.5
        """
        # 检查是否有活动动画
        self._has_animation = any(
            effect.is_animated() for effect in self._effects
            if hasattr(effect, 'is_animated')
        )
        
        # 触发重绘
        self.update()
        
        # 空闲优化：如果没有动画且鼠标静止超过阈值，暂停渲染
        if not self._has_animation:
            idle_time = (time.time() - self._last_mouse_move_time) * 1000
            if idle_time > self.IDLE_TIMEOUT_MS:
                self._render_paused = True
                self._refresh_timer.stop()
    
    def is_idle(self) -> bool:
        """检查是否处于空闲状态（用于测试）
        
        Returns:
            是否空闲（渲染已暂停）
        """
        return self._render_paused
    
    def get_last_mouse_move_time(self) -> float:
        """获取上次鼠标移动时间（用于测试）
        
        Returns:
            上次移动时间戳
        """
        return self._last_mouse_move_time
    
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 启动刷新定时器
        self.start_rendering()
    
    def hideEvent(self, event):
        """窗口隐藏事件"""
        super().hideEvent(event)
        # 停止刷新定时器
        self.stop_rendering()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 从全局置顶窗口管理器注销
        # Feature: emergency-esc-exit
        TopmostWindowManager.instance().unregister_window(self)
        # 停止定时器
        self.stop_rendering()
        super().closeEvent(event)
    
    @property
    def screen_geometry(self) -> QRect:
        """获取屏幕几何区域"""
        return self._screen_geometry
