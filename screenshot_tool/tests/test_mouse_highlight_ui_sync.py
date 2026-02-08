# =====================================================
# =============== 鼠标高亮 UI 状态同步测试 ===============
# =====================================================

"""
鼠标高亮 UI 状态同步测试

测试内容：
- Property 2: UI State Synchronization (UI 状态同步)
- 托盘菜单勾选状态与管理器状态同步

Feature: mouse-highlight
Requirements: 1.3, 1.4
"""

import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

from PySide6.QtGui import QAction
from PySide6.QtCore import QObject


class MockConfigManager:
    """模拟配置管理器"""
    
    def __init__(self):
        from screenshot_tool.core.config_manager import MouseHighlightConfig
        
        class MockConfig:
            def __init__(self):
                self.mouse_highlight = MouseHighlightConfig()
        
        self.config = MockConfig()
        self._saved = False
    
    def save_config(self):
        self._saved = True


class TestUIStateSynchronization:
    """Property 2: UI State Synchronization 测试
    
    验证：托盘菜单勾选状态与管理器的 is_enabled() 返回值一致
    **Validates: Requirements 1.3, 1.4**
    """
    
    def test_menu_action_initial_state_unchecked(self, qtbot):
        """测试菜单项初始状态为未勾选"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 验证初始状态
        assert action.isChecked() is False
        assert manager.is_enabled() is False
        assert action.isChecked() == manager.is_enabled()
    
    def test_menu_action_syncs_on_enable(self, qtbot):
        """测试启用时菜单项同步勾选"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        # 启用
        manager.enable()
        
        # 验证同步
        assert action.isChecked() is True
        assert manager.is_enabled() is True
        assert action.isChecked() == manager.is_enabled()
        
        manager.cleanup()
    
    def test_menu_action_syncs_on_disable(self, qtbot):
        """测试禁用时菜单项同步取消勾选"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        # 先启用
        manager.enable()
        assert action.isChecked() is True
        
        # 禁用
        manager.disable()
        
        # 验证同步
        assert action.isChecked() is False
        assert manager.is_enabled() is False
        assert action.isChecked() == manager.is_enabled()
    
    def test_menu_action_syncs_on_toggle(self, qtbot):
        """测试切换时菜单项同步"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        # 切换多次
        for _ in range(5):
            manager.toggle()
            assert action.isChecked() == manager.is_enabled()
        
        manager.cleanup()
    
    @given(st.lists(st.booleans(), min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_property_ui_state_always_synced(self, toggle_sequence):
        """Property 2: 任意操作序列后 UI 状态始终与管理器同步
        
        **Feature: mouse-highlight, Property 2: UI State Synchronization**
        **Validates: Requirements 1.3, 1.4**
        """
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        from PySide6.QtWidgets import QApplication
        
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        try:
            # 执行操作序列
            for should_toggle in toggle_sequence:
                if should_toggle:
                    manager.toggle()
                
                # 每次操作后验证同步
                assert action.isChecked() == manager.is_enabled(), \
                    f"UI state {action.isChecked()} != manager state {manager.is_enabled()}"
        finally:
            manager.cleanup()


class TestMenuActionTrigger:
    """菜单项触发测试"""
    
    def test_menu_trigger_toggles_manager(self, qtbot):
        """测试点击菜单项切换管理器状态"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 模拟点击菜单项触发 toggle
        def on_action_triggered():
            new_state = manager.toggle()
            action.setChecked(new_state)
        
        action.triggered.connect(on_action_triggered)
        
        # 初始状态
        assert manager.is_enabled() is False
        assert action.isChecked() is False
        
        # 触发菜单项
        action.trigger()
        
        # 验证状态变化
        assert manager.is_enabled() is True
        assert action.isChecked() is True
        
        # 再次触发
        action.trigger()
        
        assert manager.is_enabled() is False
        assert action.isChecked() is False
        
        manager.cleanup()


class TestStateRestoreUISync:
    """状态恢复时 UI 同步测试"""
    
    def test_ui_syncs_on_restore_enabled(self, qtbot):
        """测试恢复启用状态时 UI 同步"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        config_manager.config.mouse_highlight.enabled = True
        config_manager.config.mouse_highlight.restore_on_startup = True
        
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        # 恢复状态
        manager.restore_state()
        
        # 验证同步
        assert action.isChecked() is True
        assert manager.is_enabled() is True
        assert action.isChecked() == manager.is_enabled()
        
        manager.cleanup()
    
    def test_ui_syncs_on_restore_disabled(self, qtbot):
        """测试恢复禁用状态时 UI 同步"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        config_manager.config.mouse_highlight.enabled = False
        config_manager.config.mouse_highlight.restore_on_startup = True
        
        manager = MouseHighlightManager(config_manager)
        
        # 创建菜单项
        action = QAction("🖱️ 鼠标高亮")
        action.setCheckable(True)
        action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(action.setChecked)
        
        # 恢复状态
        manager.restore_state()
        
        # 验证同步
        assert action.isChecked() is False
        assert manager.is_enabled() is False
        assert action.isChecked() == manager.is_enabled()


class TestMultipleUIElements:
    """多个 UI 元素同步测试"""
    
    def test_multiple_actions_sync(self, qtbot):
        """测试多个菜单项同步"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 创建多个菜单项（模拟托盘菜单和设置对话框）
        tray_action = QAction("🖱️ 鼠标高亮")
        tray_action.setCheckable(True)
        tray_action.setChecked(manager.is_enabled())
        
        settings_action = QAction("启用鼠标高亮")
        settings_action.setCheckable(True)
        settings_action.setChecked(manager.is_enabled())
        
        # 连接状态变化信号
        manager.state_changed.connect(tray_action.setChecked)
        manager.state_changed.connect(settings_action.setChecked)
        
        # 启用
        manager.enable()
        
        # 验证所有 UI 元素同步
        assert tray_action.isChecked() is True
        assert settings_action.isChecked() is True
        assert tray_action.isChecked() == manager.is_enabled()
        assert settings_action.isChecked() == manager.is_enabled()
        
        # 禁用
        manager.disable()
        
        assert tray_action.isChecked() is False
        assert settings_action.isChecked() is False
        
        manager.cleanup()

