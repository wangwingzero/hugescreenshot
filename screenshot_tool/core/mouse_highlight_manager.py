# =====================================================
# =============== 鼠标高亮管理器 ===============
# =====================================================

"""
鼠标高亮功能核心管理器

协调 MouseEventListener、MouseHighlightOverlay 和各种效果的生命周期。
支持多显示器和显示器热插拔。

Feature: mouse-highlight
Requirements: 1.1, 1.2, 1.5, 1.6, 3.5, 3.6, 3.7
"""

from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QRect
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication

from screenshot_tool.core.async_logger import async_debug_log
from screenshot_tool.core.mouse_event_listener import MouseEventListener
from screenshot_tool.core.config_manager import MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import ConfigManager
    from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
    from screenshot_tool.ui.effects.base_effect import BaseEffect


class MouseHighlightManager(QObject):
    """鼠标高亮功能核心管理器
    
    负责协调所有组件的生命周期：
    - MouseEventListener: 全局鼠标事件监听
    - MouseHighlightOverlay: 覆盖层窗口（每个显示器一个）
    - Effects: 效果绘制器
    
    多显示器支持：
    - 为每个显示器创建独立的覆盖层窗口
    - 监听显示器热插拔事件，动态添加/移除覆盖层
    - 鼠标位置自动映射到正确的显示器
    
    信号:
        state_changed(bool): 状态变化通知
    
    使用示例:
        manager = MouseHighlightManager(config_manager)
        manager.toggle()  # 切换启用状态
    """
    
    # 状态变化信号
    state_changed = Signal(bool)
    
    def __init__(self, config_manager: "ConfigManager", parent: Optional[QObject] = None):
        """初始化管理器
        
        Args:
            config_manager: 配置管理器
            parent: 父对象
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        self._enabled = False
        
        # 组件
        self._listener: Optional[MouseEventListener] = None
        self._overlays: List["MouseHighlightOverlay"] = []
        self._effects: List["BaseEffect"] = []
        
        # 显示器热插拔监听
        self._screen_connections: List = []
    
    def toggle(self) -> bool:
        """切换启用状态
        
        Returns:
            新的启用状态
        """
        if self._enabled:
            self.disable()
        else:
            self.enable()
        return self._enabled
    
    def enable(self) -> bool:
        """启用高亮功能
        
        Returns:
            是否成功启用
        """
        if self._enabled:
            return True
        
        try:
            # 延迟导入避免循环依赖
            from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
            from screenshot_tool.ui.effects import (
                CircleEffect, SpotlightEffect, CursorMagnifyEffect, ClickRippleEffect
            )
            
            # 获取配置
            config = self._get_config()
            theme = config.get_theme_colors()
            
            # 创建效果列表
            self._effects = [
                CircleEffect(config, theme),
                SpotlightEffect(config, theme),
                CursorMagnifyEffect(config, theme),
                ClickRippleEffect(config, theme),
            ]
            
            # 为每个显示器创建覆盖层
            app = QApplication.instance()
            if app is None:
                async_debug_log("QApplication 未初始化")
                return False
            
            screens = app.screens()
            for screen in screens:
                self._create_overlay_for_screen(screen)
            
            async_debug_log(f"创建了 {len(self._overlays)} 个覆盖层窗口")
            
            # 监听显示器热插拔事件
            self._connect_screen_signals(app)
            
            # 创建并启动监听器
            self._listener = MouseEventListener()
            self._listener.mouse_moved.connect(self._on_mouse_moved)
            self._listener.left_clicked.connect(self._on_left_clicked)
            self._listener.right_clicked.connect(self._on_right_clicked)
            
            if not self._listener.start():
                async_debug_log("监听器启动失败")
                self._cleanup()
                return False
            
            self._enabled = True
            self.state_changed.emit(True)
            
            # 保存状态到配置
            self._save_enabled_state(True)
            
            async_debug_log("鼠标高亮功能已启用")
            return True
            
        except Exception as e:
            async_debug_log(f"鼠标高亮启用失败: {e}")
            self._cleanup()
            return False
    
    def disable(self):
        """禁用高亮功能"""
        if not self._enabled:
            return
        
        self._cleanup()
        self._enabled = False
        self.state_changed.emit(False)
        
        # 保存状态到配置
        self._save_enabled_state(False)
        
        async_debug_log("鼠标高亮功能已禁用")
    
    def is_enabled(self) -> bool:
        """返回当前启用状态"""
        return self._enabled
    
    def update_config(self, config: Optional[MouseHighlightConfig] = None):
        """热更新配置（不重启）
        
        Args:
            config: 新配置，如果为 None 则从配置管理器获取
        """
        if config is None:
            config = self._get_config()
        
        theme = config.get_theme_colors()
        
        # 更新所有效果的配置
        for effect in self._effects:
            effect.update_config(config, theme)
        
        async_debug_log("鼠标高亮配置已更新")
    
    def cleanup(self):
        """清理所有资源（公共方法）"""
        self.disable()
    
    def _cleanup(self):
        """清理所有资源（内部方法）"""
        # 断开显示器信号连接
        self._disconnect_screen_signals()
        
        # 停止监听器
        if self._listener:
            self._listener.stop()
            self._listener = None
        
        # 关闭所有覆盖层
        for overlay in self._overlays:
            try:
                overlay.close()
                overlay.deleteLater()
            except Exception:
                pass
        self._overlays.clear()
        
        # 清理效果
        self._effects.clear()
    
    def _connect_screen_signals(self, app: QApplication):
        """连接显示器热插拔信号
        
        Args:
            app: QApplication 实例
            
        Feature: mouse-highlight
        Requirements: 3.5
        """
        # 断开旧连接
        self._disconnect_screen_signals()
        
        # 连接新信号
        conn1 = app.screenAdded.connect(self._on_screen_added)
        conn2 = app.screenRemoved.connect(self._on_screen_removed)
        self._screen_connections = [conn1, conn2]
        
        async_debug_log("已连接显示器热插拔信号")
    
    def _disconnect_screen_signals(self):
        """断开显示器热插拔信号"""
        app = QApplication.instance()
        if app and self._screen_connections:
            try:
                # 使用保存的槽函数精确断开连接
                app.screenAdded.disconnect(self._on_screen_added)
                app.screenRemoved.disconnect(self._on_screen_removed)
            except (RuntimeError, TypeError):
                # 信号可能已断开或对象已销毁
                pass
        self._screen_connections.clear()
    
    def _create_overlay_for_screen(self, screen: QScreen) -> Optional["MouseHighlightOverlay"]:
        """为指定显示器创建覆盖层
        
        Args:
            screen: QScreen 对象
            
        Returns:
            创建的覆盖层，失败返回 None
            
        Feature: mouse-highlight
        Requirements: 3.5
        
        Note:
            使用 availableGeometry() 而不是 geometry()，
            这样覆盖层不会遮挡任务栏。
        """
        try:
            from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
            
            # 使用 availableGeometry 排除任务栏区域
            geometry = screen.availableGeometry()
            overlay = MouseHighlightOverlay(geometry, self._effects)
            overlay._screen = screen  # 保存 screen 引用用于后续比较
            self._overlays.append(overlay)
            overlay.show()
            
            async_debug_log(f"为显示器创建覆盖层: {geometry}")
            return overlay
        except Exception as e:
            async_debug_log(f"创建覆盖层失败: {e}")
            return None
    
    def _remove_overlay_for_screen(self, screen: QScreen):
        """移除指定显示器的覆盖层
        
        Args:
            screen: QScreen 对象
            
        Feature: mouse-highlight
        Requirements: 3.7
        """
        # 查找并移除匹配的覆盖层（通过 screen 引用或 availableGeometry 匹配）
        geometry = screen.availableGeometry()
        
        overlays_to_remove = []
        for overlay in self._overlays:
            # 优先通过 screen 引用匹配
            if hasattr(overlay, '_screen') and overlay._screen == screen:
                overlays_to_remove.append(overlay)
            # 回退到几何匹配
            elif overlay.screen_geometry == geometry:
                overlays_to_remove.append(overlay)
        
        for overlay in overlays_to_remove:
            try:
                self._overlays.remove(overlay)
                overlay.close()
                overlay.deleteLater()
                async_debug_log(f"移除显示器覆盖层: {geometry}")
            except Exception as e:
                async_debug_log(f"移除覆盖层失败: {e}")
    
    def _on_screen_added(self, screen: QScreen):
        """显示器添加事件处理
        
        Args:
            screen: 新添加的显示器
            
        Feature: mouse-highlight
        Requirements: 3.5
        """
        if not self._enabled:
            return
        
        async_debug_log(f"检测到新显示器: {screen.geometry()}")
        self._create_overlay_for_screen(screen)
    
    def _on_screen_removed(self, screen: QScreen):
        """显示器移除事件处理
        
        Args:
            screen: 被移除的显示器
            
        Feature: mouse-highlight
        Requirements: 3.7
        """
        if not self._enabled:
            return
        
        async_debug_log(f"检测到显示器移除: {screen.geometry()}")
        self._remove_overlay_for_screen(screen)
    
    def _get_config(self) -> MouseHighlightConfig:
        """获取当前配置"""
        if self._config_manager:
            return self._config_manager.config.mouse_highlight
        return MouseHighlightConfig()
    
    def _save_enabled_state(self, enabled: bool):
        """保存启用状态到配置"""
        if self._config_manager:
            self._config_manager.config.mouse_highlight.enabled = enabled
            self._config_manager.save()
    
    def _on_mouse_moved(self, x: int, y: int):
        """鼠标移动事件处理"""
        for overlay in self._overlays:
            overlay.update_mouse_position(x, y)
    
    def _on_left_clicked(self, x: int, y: int):
        """左键点击事件处理"""
        for overlay in self._overlays:
            overlay.add_click_ripple(x, y, is_left=True)
    
    def _on_right_clicked(self, x: int, y: int):
        """右键点击事件处理"""
        for overlay in self._overlays:
            overlay.add_click_ripple(x, y, is_left=False)
    
    def restore_state(self):
        """恢复上次状态（启动时调用）"""
        config = self._get_config()
        if config.restore_on_startup and config.enabled:
            self.enable()
            async_debug_log("鼠标高亮状态已恢复")
    
    def get_overlay_count(self) -> int:
        """获取当前覆盖层数量
        
        Returns:
            覆盖层数量
            
        Feature: mouse-highlight
        Requirements: 3.5
        """
        return len(self._overlays)
    
    def get_overlays(self) -> List["MouseHighlightOverlay"]:
        """获取所有覆盖层（用于测试）
        
        Returns:
            覆盖层列表的副本
        """
        return list(self._overlays)
    
    def find_overlay_for_position(self, x: int, y: int) -> Optional["MouseHighlightOverlay"]:
        """查找包含指定坐标的覆盖层
        
        Args:
            x: 全局 X 坐标
            y: 全局 Y 坐标
            
        Returns:
            包含该坐标的覆盖层，如果没有则返回 None
            
        Feature: mouse-highlight
        Requirements: 3.6
        """
        for overlay in self._overlays:
            if overlay.is_mouse_in_screen(x, y):
                return overlay
        return None
    
    def toggle_spotlight(self) -> bool:
        """切换聚光灯效果的开关状态
        
        Returns:
            新的聚光灯状态（True=开启，False=关闭）
        """
        if not self._enabled or not self._config_manager:
            return False
        
        # 切换配置
        config = self._config_manager.config.mouse_highlight
        config.spotlight_enabled = not config.spotlight_enabled
        
        # 更新所有效果
        self.update_config(config)
        
        # 不保存到配置文件（临时切换）
        async_debug_log(f"聚光灯效果已{'开启' if config.spotlight_enabled else '关闭'}")
        return config.spotlight_enabled
    
    def is_spotlight_enabled(self) -> bool:
        """返回聚光灯是否开启"""
        if self._config_manager:
            return self._config_manager.config.mouse_highlight.spotlight_enabled
        return False
