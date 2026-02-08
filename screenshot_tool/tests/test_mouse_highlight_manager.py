# =====================================================
# =============== 鼠标高亮管理器测试 ===============
# =====================================================

"""
MouseHighlightManager 单元测试

测试内容：
- Property 1: Toggle State Consistency (切换状态一致性)
- 基本功能测试
- 配置更新测试

Feature: mouse-highlight
Requirements: 1.1, 1.2
"""

import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

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


class TestMouseHighlightManagerBasic:
    """MouseHighlightManager 基本功能测试"""
    
    def test_import(self):
        """测试模块导入"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        assert MouseHighlightManager is not None
    
    def test_instantiation(self, qtbot):
        """测试实例化"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        assert manager is not None
        assert not manager.is_enabled()
    
    def test_initial_state_disabled(self, qtbot):
        """测试初始状态为禁用"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        assert manager.is_enabled() is False
    
    def test_state_changed_signal_exists(self, qtbot):
        """测试状态变化信号存在"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        assert hasattr(manager, 'state_changed')


class TestToggleStateConsistency:
    """Property 1: Toggle State Consistency 测试
    
    验证：调用 toggle() 后状态翻转，再次调用返回原状态
    """
    
    def test_toggle_from_disabled(self, qtbot):
        """测试从禁用状态切换"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 初始状态：禁用
        assert manager.is_enabled() is False
        
        # 切换：应该启用
        new_state = manager.toggle()
        assert new_state is True
        assert manager.is_enabled() is True
        
        # 清理
        manager.cleanup()
    
    def test_toggle_from_enabled(self, qtbot):
        """测试从启用状态切换"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 先启用
        manager.enable()
        assert manager.is_enabled() is True
        
        # 切换：应该禁用
        new_state = manager.toggle()
        assert new_state is False
        assert manager.is_enabled() is False
    
    def test_toggle_twice_returns_to_original(self, qtbot):
        """测试两次切换返回原状态"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 初始状态
        initial_state = manager.is_enabled()
        
        # 切换两次
        manager.toggle()
        manager.toggle()
        
        # 应该返回原状态
        assert manager.is_enabled() == initial_state
    
    @given(st.lists(st.booleans(), min_size=1, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_property_toggle_sequence(self, toggle_sequence):
        """Property 1: 任意切换序列后状态应该正确"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        from PySide6.QtWidgets import QApplication
        
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        try:
            # 计算预期状态
            # 初始状态为 False，每次 toggle 翻转
            expected_state = False
            toggle_count = sum(1 for t in toggle_sequence if t)
            expected_state = (toggle_count % 2) == 1
            
            # 执行切换
            for should_toggle in toggle_sequence:
                if should_toggle:
                    manager.toggle()
            
            # 验证状态
            assert manager.is_enabled() == expected_state
        finally:
            manager.cleanup()


class TestEnableDisable:
    """启用/禁用功能测试"""
    
    def test_enable_success(self, qtbot):
        """测试启用成功"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        result = manager.enable()
        
        assert result is True
        assert manager.is_enabled() is True
        
        manager.cleanup()
    
    def test_enable_twice(self, qtbot):
        """测试重复启用"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 第一次启用
        result1 = manager.enable()
        assert result1 is True
        
        # 第二次启用应该返回 True（已启用）
        result2 = manager.enable()
        assert result2 is True
        
        manager.cleanup()
    
    def test_disable_success(self, qtbot):
        """测试禁用成功"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        manager.disable()
        
        assert manager.is_enabled() is False
    
    def test_disable_without_enable(self, qtbot):
        """测试未启用时禁用"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 未启用时禁用不应该报错
        manager.disable()
        assert manager.is_enabled() is False


class TestStateChangedSignal:
    """状态变化信号测试"""
    
    def test_signal_emitted_on_enable(self, qtbot):
        """测试启用时发射信号"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        signals = []
        manager.state_changed.connect(lambda s: signals.append(s))
        
        manager.enable()
        
        assert len(signals) == 1
        assert signals[0] is True
        
        manager.cleanup()
    
    def test_signal_emitted_on_disable(self, qtbot):
        """测试禁用时发射信号"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        
        signals = []
        manager.state_changed.connect(lambda s: signals.append(s))
        
        manager.disable()
        
        assert len(signals) == 1
        assert signals[0] is False
    
    def test_signal_emitted_on_toggle(self, qtbot):
        """测试切换时发射信号"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        signals = []
        manager.state_changed.connect(lambda s: signals.append(s))
        
        manager.toggle()  # False -> True
        manager.toggle()  # True -> False
        
        assert len(signals) == 2
        assert signals[0] is True
        assert signals[1] is False


class TestConfigUpdate:
    """配置更新测试"""
    
    def test_update_config(self, qtbot):
        """测试配置更新"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        from screenshot_tool.core.config_manager import MouseHighlightConfig
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        
        # 更新配置
        new_config = MouseHighlightConfig(
            circle_radius=60,
            theme="business_blue"
        )
        manager.update_config(new_config)
        
        # 不应该报错
        manager.cleanup()
    
    def test_update_config_without_enable(self, qtbot):
        """测试未启用时更新配置"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        from screenshot_tool.core.config_manager import MouseHighlightConfig
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        # 未启用时更新配置不应该报错
        new_config = MouseHighlightConfig(circle_radius=60)
        manager.update_config(new_config)


class TestConfigPersistence:
    """配置持久化测试"""
    
    def test_enable_saves_config(self, qtbot):
        """测试启用时保存配置"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        
        assert config_manager._saved is True
        assert config_manager.config.mouse_highlight.enabled is True
        
        manager.cleanup()
    
    def test_disable_saves_config(self, qtbot):
        """测试禁用时保存配置"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        config_manager._saved = False  # 重置
        
        manager.disable()
        
        assert config_manager._saved is True
        assert config_manager.config.mouse_highlight.enabled is False


class TestRestoreState:
    """状态恢复测试"""
    
    def test_restore_state_when_enabled(self, qtbot):
        """测试恢复启用状态"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        config_manager.config.mouse_highlight.enabled = True
        config_manager.config.mouse_highlight.restore_on_startup = True
        
        manager = MouseHighlightManager(config_manager)
        manager.restore_state()
        
        assert manager.is_enabled() is True
        
        manager.cleanup()
    
    def test_restore_state_when_disabled(self, qtbot):
        """测试恢复禁用状态"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        config_manager.config.mouse_highlight.enabled = False
        config_manager.config.mouse_highlight.restore_on_startup = True
        
        manager = MouseHighlightManager(config_manager)
        manager.restore_state()
        
        assert manager.is_enabled() is False
    
    def test_restore_state_disabled_option(self, qtbot):
        """测试禁用恢复选项"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        config_manager.config.mouse_highlight.enabled = True
        config_manager.config.mouse_highlight.restore_on_startup = False
        
        manager = MouseHighlightManager(config_manager)
        manager.restore_state()
        
        # 即使 enabled=True，但 restore_on_startup=False，不应该恢复
        assert manager.is_enabled() is False


class TestCleanup:
    """资源清理测试"""
    
    def test_cleanup_releases_resources(self, qtbot):
        """测试清理释放资源"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        assert manager.is_enabled() is True
        
        manager.cleanup()
        
        assert manager.is_enabled() is False
        assert manager._listener is None
        assert len(manager._overlays) == 0
        assert len(manager._effects) == 0
    
    def test_cleanup_multiple_times(self, qtbot):
        """测试多次清理"""
        from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
        
        config_manager = MockConfigManager()
        manager = MouseHighlightManager(config_manager)
        
        manager.enable()
        manager.cleanup()
        manager.cleanup()  # 第二次清理不应该报错
        
        assert manager.is_enabled() is False
