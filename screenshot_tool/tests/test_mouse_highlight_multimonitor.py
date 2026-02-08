# =====================================================
# =============== 鼠标高亮多显示器测试 ===============
# =====================================================

"""
多显示器支持测试

测试 Property 6, 7, 8:
- Property 6: Multi-Monitor Overlay Creation
- Property 7: Coordinate-to-Monitor Mapping
- Property 8: Overlay Cleanup on Disable

Feature: mouse-highlight
Requirements: 3.5, 3.6, 3.7
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import List

from PySide6.QtCore import QRect, Signal, QObject
from PySide6.QtWidgets import QApplication

from screenshot_tool.core.config_manager import MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES


class MockScreen:
    """模拟 QScreen 对象"""
    
    def __init__(self, geometry: QRect, available_geometry: QRect = None):
        self._geometry = geometry
        # 如果未指定 availableGeometry，默认与 geometry 相同（模拟无任务栏）
        self._available_geometry = available_geometry if available_geometry else geometry
    
    def geometry(self) -> QRect:
        return self._geometry
    
    def availableGeometry(self) -> QRect:
        return self._available_geometry


class MockOverlay:
    """模拟 MouseHighlightOverlay 对象"""
    
    def __init__(self, geometry: QRect, effects: List = None):
        self._screen_geometry = geometry
        self._effects = effects or []
        self._visible = False
        self._closed = False
    
    @property
    def screen_geometry(self) -> QRect:
        return self._screen_geometry
    
    def is_mouse_in_screen(self, x: int, y: int) -> bool:
        return self._screen_geometry.contains(x, y)
    
    def show(self):
        self._visible = True
    
    def close(self):
        self._visible = False
        self._closed = True
    
    def deleteLater(self):
        pass
    
    def update_mouse_position(self, x: int, y: int):
        pass
    
    def add_click_ripple(self, x: int, y: int, is_left: bool):
        pass


class TestMultiMonitorOverlayCreation:
    """Property 6: Multi-Monitor Overlay Creation
    
    For any number N of connected monitors (N >= 1), enabling the highlight
    SHALL create exactly N overlay windows, one for each monitor's geometry.
    """
    
    def test_single_monitor_creates_one_overlay(self, qtbot):
        """单显示器创建一个覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        # 模拟单显示器
        screen = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    result = manager.enable()
                    
                    assert result is True
                    assert manager.get_overlay_count() == 1
                    
                    manager.cleanup()
    
    def test_dual_monitor_creates_two_overlays(self, qtbot):
        """双显示器创建两个覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        # 模拟双显示器
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    result = manager.enable()
                    
                    assert result is True
                    assert manager.get_overlay_count() == 2
                    
                    manager.cleanup()
    
    def test_triple_monitor_creates_three_overlays(self, qtbot):
        """三显示器创建三个覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        # 模拟三显示器
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        screen3 = MockScreen(QRect(3840, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2, screen3]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    result = manager.enable()
                    
                    assert result is True
                    assert manager.get_overlay_count() == 3
                    
                    manager.cleanup()
    
    def test_each_overlay_has_correct_geometry(self, qtbot):
        """每个覆盖层有正确的几何区域"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        # 模拟不同尺寸的显示器
        geometries = [
            QRect(0, 0, 1920, 1080),      # 主显示器
            QRect(1920, 0, 2560, 1440),   # 右侧 2K 显示器
            QRect(-1080, 0, 1080, 1920),  # 左侧竖屏
        ]
        screens = [MockScreen(g) for g in geometries]
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = screens
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    overlays = manager.get_overlays()
                    overlay_geometries = [o.screen_geometry for o in overlays]
                    
                    for expected_geom in geometries:
                        assert expected_geom in overlay_geometries
                    
                    manager.cleanup()


class TestCoordinateToMonitorMapping:
    """Property 7: Coordinate-to-Monitor Mapping
    
    For any mouse position (x, y) within any monitor's bounds,
    exactly one overlay window SHALL render the effects at that position.
    """
    
    def test_position_in_primary_monitor(self, qtbot):
        """主显示器内的坐标映射到主显示器覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 主显示器中心点
                    overlay = manager.find_overlay_for_position(960, 540)
                    assert overlay is not None
                    assert overlay.screen_geometry == QRect(0, 0, 1920, 1080)
                    
                    manager.cleanup()
    
    def test_position_in_secondary_monitor(self, qtbot):
        """副显示器内的坐标映射到副显示器覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 副显示器中心点
                    overlay = manager.find_overlay_for_position(2880, 540)
                    assert overlay is not None
                    assert overlay.screen_geometry == QRect(1920, 0, 1920, 1080)
                    
                    manager.cleanup()
    
    def test_position_at_monitor_boundary(self, qtbot):
        """显示器边界坐标正确映射"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 主显示器右边界（1919 是最后一个像素）
                    overlay1 = manager.find_overlay_for_position(1919, 540)
                    assert overlay1 is not None
                    assert overlay1.screen_geometry == QRect(0, 0, 1920, 1080)
                    
                    # 副显示器左边界（1920 是第一个像素）
                    overlay2 = manager.find_overlay_for_position(1920, 540)
                    assert overlay2 is not None
                    assert overlay2.screen_geometry == QRect(1920, 0, 1920, 1080)
                    
                    manager.cleanup()
    
    def test_position_outside_all_monitors(self, qtbot):
        """所有显示器外的坐标返回 None"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 显示器外的坐标
                    overlay = manager.find_overlay_for_position(5000, 5000)
                    assert overlay is None
                    
                    manager.cleanup()
    
    def test_negative_coordinates_with_left_monitor(self, qtbot):
        """负坐标（左侧显示器）正确映射"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        # 左侧显示器在负坐标区域
        screen1 = MockScreen(QRect(-1920, 0, 1920, 1080))
        screen2 = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 左侧显示器中心点
                    overlay = manager.find_overlay_for_position(-960, 540)
                    assert overlay is not None
                    assert overlay.screen_geometry == QRect(-1920, 0, 1920, 1080)
                    
                    manager.cleanup()


class TestOverlayCleanupOnDisable:
    """Property 8: Overlay Cleanup on Disable
    
    For any number of overlay windows created during enable,
    calling disable() SHALL close all overlay windows and release all resources.
    """
    
    def test_disable_closes_all_overlays(self, qtbot):
        """禁用时关闭所有覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 保存覆盖层引用
                    overlays = manager.get_overlays()
                    assert len(overlays) == 2
                    
                    # 禁用
                    manager.disable()
                    
                    # 验证覆盖层已关闭
                    for overlay in overlays:
                        assert overlay._closed is True
                    
                    # 验证管理器内部列表已清空
                    assert manager.get_overlay_count() == 0
    
    def test_disable_stops_listener(self, qtbot):
        """禁用时停止监听器"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 禁用
                    manager.disable()
                    
                    # 验证监听器已停止
                    mock_listener.stop.assert_called_once()
    
    def test_cleanup_clears_effects(self, qtbot):
        """清理时清空效果列表"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    # 验证效果已创建
                    assert len(manager._effects) > 0
                    
                    # 清理
                    manager.cleanup()
                    
                    # 验证效果已清空
                    assert len(manager._effects) == 0
    
    def test_multiple_enable_disable_cycles(self, qtbot):
        """多次启用/禁用循环正常工作"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen = MockScreen(QRect(0, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    
                    # 第一次循环
                    manager.enable()
                    assert manager.get_overlay_count() == 1
                    manager.disable()
                    assert manager.get_overlay_count() == 0
                    
                    # 第二次循环
                    manager.enable()
                    assert manager.get_overlay_count() == 1
                    manager.disable()
                    assert manager.get_overlay_count() == 0
                    
                    # 第三次循环
                    manager.enable()
                    assert manager.get_overlay_count() == 1
                    manager.cleanup()
                    assert manager.get_overlay_count() == 0


class TestScreenHotplug:
    """显示器热插拔测试
    
    Feature: mouse-highlight
    Requirements: 3.5, 3.7
    """
    
    def test_screen_added_creates_overlay(self, qtbot):
        """添加显示器时创建新覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        new_screen = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    assert manager.get_overlay_count() == 1
                    
                    # 模拟添加新显示器
                    manager._on_screen_added(new_screen)
                    
                    assert manager.get_overlay_count() == 2
                    
                    manager.cleanup()
    
    def test_screen_removed_removes_overlay(self, qtbot):
        """移除显示器时删除对应覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        screen1 = MockScreen(QRect(0, 0, 1920, 1080))
        screen2 = MockScreen(QRect(1920, 0, 1920, 1080))
        
        with patch.object(QApplication, 'instance') as mock_app_instance:
            mock_app = MagicMock()
            mock_app.screens.return_value = [screen1, screen2]
            mock_app_instance.return_value = mock_app
            
            with patch('screenshot_tool.core.mouse_highlight_manager.MouseEventListener') as mock_listener_class:
                mock_listener = MagicMock()
                mock_listener.start.return_value = True
                mock_listener_class.return_value = mock_listener
                
                with patch('screenshot_tool.ui.mouse_highlight_overlay.MouseHighlightOverlay', MockOverlay):
                    manager = MouseHighlightManager(None)
                    manager.enable()
                    
                    assert manager.get_overlay_count() == 2
                    
                    # 模拟移除显示器
                    manager._on_screen_removed(screen2)
                    
                    assert manager.get_overlay_count() == 1
                    
                    # 验证剩余的是正确的覆盖层
                    remaining = manager.get_overlays()[0]
                    assert remaining.screen_geometry == QRect(0, 0, 1920, 1080)
                    
                    manager.cleanup()
    
    def test_hotplug_when_disabled_does_nothing(self, qtbot):
        """禁用状态下热插拔不创建覆盖层"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        new_screen = MockScreen(QRect(1920, 0, 1920, 1080))
        
        manager = MouseHighlightManager(None)
        
        # 未启用状态
        assert manager.is_enabled() is False
        assert manager.get_overlay_count() == 0
        
        # 模拟添加显示器
        manager._on_screen_added(new_screen)
        
        # 不应创建覆盖层
        assert manager.get_overlay_count() == 0
