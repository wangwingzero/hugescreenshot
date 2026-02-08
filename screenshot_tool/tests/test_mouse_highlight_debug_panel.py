# =====================================================
# =============== 鼠标高亮调试面板测试 ===============
# =====================================================

"""
MouseHighlightDebugPanel 的单元测试和属性测试

Feature: mouse-highlight-debug-panel
Requirements: 1.1-1.5, 2.1-2.5, 3.1-3.4, 4.1-4.4, 5.1-5.7, 6.1-6.4, 7.1-7.3
"""

import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from screenshot_tool.core.config_manager import (
    MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES, AppConfig, ConfigManager
)


@pytest.fixture(scope="module")
def app():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_config_manager():
    """创建模拟的配置管理器"""
    config_manager = MagicMock(spec=ConfigManager)
    config_manager.config = MagicMock()
    config_manager.config.mouse_highlight = MouseHighlightConfig()
    return config_manager


@pytest.fixture
def mock_highlight_manager():
    """创建模拟的高亮管理器"""
    manager = MagicMock()
    manager.is_enabled.return_value = False
    manager.enable.return_value = True
    manager.update_config = MagicMock()
    return manager


@pytest.fixture
def debug_panel(app, mock_config_manager, mock_highlight_manager):
    """创建调试面板实例"""
    from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
    
    # 清除单例
    MouseHighlightDebugPanel._instance = None
    
    panel = MouseHighlightDebugPanel(
        mock_config_manager,
        mock_highlight_manager
    )
    yield panel
    panel.close()
    MouseHighlightDebugPanel._instance = None


class TestMouseHighlightDebugPanelBasic:
    """MouseHighlightDebugPanel 基础功能测试"""
    
    def test_init_creates_panel(self, debug_panel):
        """测试面板初始化"""
        assert debug_panel is not None
        assert debug_panel.windowTitle() == "鼠标高亮调试"
    
    def test_non_modal_window(self, debug_panel):
        """测试非模态窗口属性"""
        assert debug_panel.windowModality() == Qt.WindowModality.NonModal
    
    def test_auto_enable_highlight(self, debug_panel, mock_highlight_manager):
        """测试自动启用鼠标高亮 (Requirement 1.3)"""
        mock_highlight_manager.enable.assert_called_once()
    
    def test_theme_buttons_created(self, debug_panel):
        """测试主题按钮创建"""
        assert len(debug_panel._theme_buttons) == len(MOUSE_HIGHLIGHT_THEMES)
        for theme_key in MOUSE_HIGHLIGHT_THEMES:
            assert theme_key in debug_panel._theme_buttons
    
    def test_effect_checkboxes_created(self, debug_panel):
        """测试效果开关创建"""
        expected_effects = ["circle", "spotlight", "cursor_magnify", "click_effect"]
        for effect in expected_effects:
            assert effect in debug_panel._effect_checkboxes
    
    def test_parameter_sliders_created(self, debug_panel):
        """测试参数滑块创建"""
        expected_params = [
            "circle_radius", "circle_thickness",
            "spotlight_radius", "spotlight_darkness",
            "cursor_scale", "ripple_duration"
        ]
        for param in expected_params:
            assert param in debug_panel._parameter_sliders


class TestMouseHighlightDebugPanelSingleton:
    """单例模式测试
    
    Feature: mouse-highlight-debug-panel
    Property 8: 单例窗口行为
    """
    
    def test_singleton_instance(self, app, mock_config_manager, mock_highlight_manager):
        """测试单例模式"""
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 第一次创建
        panel1 = MouseHighlightDebugPanel.show_panel(
            mock_config_manager, mock_highlight_manager
        )
        
        # 第二次调用应返回同一实例
        panel2 = MouseHighlightDebugPanel.show_panel(
            mock_config_manager, mock_highlight_manager
        )
        
        assert panel1 is panel2
        
        panel1.close()
        MouseHighlightDebugPanel._instance = None
    
    def test_singleton_after_close(self, app, mock_config_manager, mock_highlight_manager):
        """测试关闭后重新创建"""
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 创建并关闭
        panel1 = MouseHighlightDebugPanel.show_panel(
            mock_config_manager, mock_highlight_manager
        )
        panel1.close()
        
        # 重新创建应该是新实例
        panel2 = MouseHighlightDebugPanel.show_panel(
            mock_config_manager, mock_highlight_manager
        )
        
        assert panel1 is not panel2
        
        panel2.close()
        MouseHighlightDebugPanel._instance = None


class TestMouseHighlightDebugPanelRealtime:
    """实时更新测试
    
    Feature: mouse-highlight-debug-panel
    Property 2: 参数变化即时传播
    Property 4: 效果开关即时生效
    Property 5: 主题切换即时生效
    """
    
    def test_parameter_change_updates_manager(self, debug_panel, mock_highlight_manager):
        """Property 2: 参数变化即时传播"""
        # 重置调用计数
        mock_highlight_manager.update_config.reset_mock()
        
        # 改变参数
        debug_panel._parameter_sliders["circle_radius"]._slider.setValue(60)
        
        # 验证管理器被调用
        mock_highlight_manager.update_config.assert_called()
    
    def test_effect_toggle_updates_manager(self, debug_panel, mock_highlight_manager):
        """Property 4: 效果开关即时生效"""
        # 重置调用计数
        mock_highlight_manager.update_config.reset_mock()
        
        # 切换效果开关
        debug_panel._effect_checkboxes["spotlight"].setChecked(True)
        
        # 验证管理器被调用
        mock_highlight_manager.update_config.assert_called()
    
    def test_theme_change_updates_manager(self, debug_panel, mock_highlight_manager, mock_config_manager):
        """Property 5: 主题切换即时生效"""
        # 重置调用计数
        mock_highlight_manager.update_config.reset_mock()
        
        # 切换主题
        debug_panel._on_theme_changed("business_blue")
        
        # 验证配置更新
        assert mock_config_manager.config.mouse_highlight.theme == "business_blue"
        
        # 验证管理器被调用
        mock_highlight_manager.update_config.assert_called()


class TestMouseHighlightDebugPanelReset:
    """重置功能测试
    
    Feature: mouse-highlight-debug-panel
    Property 7: 重置恢复默认值
    """
    
    def test_reset_restores_defaults(self, debug_panel, mock_config_manager):
        """Property 7: 重置恢复默认值"""
        # 修改一些参数
        debug_panel._parameter_sliders["circle_radius"].set_value(80)
        debug_panel._parameter_sliders["spotlight_radius"].set_value(300)
        debug_panel._effect_checkboxes["spotlight"].setChecked(True)
        
        # 点击重置
        debug_panel._on_reset_clicked()
        
        # 验证恢复默认值
        config = mock_config_manager.config.mouse_highlight
        default = MouseHighlightConfig()
        
        assert config.circle_radius == default.circle_radius
        assert config.spotlight_radius == default.spotlight_radius
        assert config.spotlight_enabled == default.spotlight_enabled
    
    @given(
        circle_radius=st.integers(min_value=10, max_value=100),
        circle_thickness=st.integers(min_value=1, max_value=10),
        spotlight_radius=st.integers(min_value=50, max_value=500),
        spotlight_darkness=st.integers(min_value=0, max_value=100),
        cursor_scale=st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        ripple_duration=st.integers(min_value=100, max_value=2000),
        circle_enabled=st.booleans(),
        spotlight_enabled=st.booleans(),
        cursor_magnify_enabled=st.booleans(),
        click_effect_enabled=st.booleans()
    )
    @settings(max_examples=20, deadline=None)
    def test_reset_restores_all_defaults_property(
        self, app, circle_radius, circle_thickness, spotlight_radius,
        spotlight_darkness, cursor_scale, ripple_duration,
        circle_enabled, spotlight_enabled, cursor_magnify_enabled, click_effect_enabled
    ):
        """Property 7: 重置恢复默认值（属性测试）
        
        For any configuration state, clicking the reset button SHALL restore
        all parameters to their default values as defined in MouseHighlightConfig.
        
        **Validates: Requirements 6.3, 6.4**
        """
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 创建带有随机值的配置
        config = MouseHighlightConfig(
            circle_radius=circle_radius,
            circle_thickness=circle_thickness,
            spotlight_radius=spotlight_radius,
            spotlight_darkness=spotlight_darkness,
            cursor_scale=round(cursor_scale, 1),
            ripple_duration=ripple_duration,
            circle_enabled=circle_enabled,
            spotlight_enabled=spotlight_enabled,
            cursor_magnify_enabled=cursor_magnify_enabled,
            click_effect_enabled=click_effect_enabled
        )
        
        # 创建模拟对象
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.config = MagicMock()
        config_manager.config.mouse_highlight = config
        
        highlight_manager = MagicMock()
        highlight_manager.is_enabled.return_value = True
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 创建面板
        panel = MouseHighlightDebugPanel(config_manager, highlight_manager)
        
        # 执行重置
        panel._on_reset_clicked()
        
        # 获取默认配置
        default = MouseHighlightConfig()
        
        # 验证所有参数都恢复为默认值
        result_config = config_manager.config.mouse_highlight
        assert result_config.circle_radius == default.circle_radius
        assert result_config.circle_thickness == default.circle_thickness
        assert result_config.spotlight_radius == default.spotlight_radius
        assert result_config.spotlight_darkness == default.spotlight_darkness
        assert abs(result_config.cursor_scale - default.cursor_scale) < 0.01
        assert result_config.ripple_duration == default.ripple_duration
        assert result_config.circle_enabled == default.circle_enabled
        assert result_config.spotlight_enabled == default.spotlight_enabled
        assert result_config.cursor_magnify_enabled == default.cursor_magnify_enabled
        assert result_config.click_effect_enabled == default.click_effect_enabled
        
        panel.close()
        MouseHighlightDebugPanel._instance = None


class TestMouseHighlightDebugPanelProperty:
    """属性测试
    
    Feature: mouse-highlight-debug-panel
    Property 1: 配置持久化往返
    """
    
    @given(
        circle_radius=st.integers(min_value=10, max_value=100),
        circle_thickness=st.integers(min_value=1, max_value=10),
        spotlight_radius=st.integers(min_value=50, max_value=500),
        spotlight_darkness=st.integers(min_value=0, max_value=100),
        ripple_duration=st.integers(min_value=100, max_value=2000)
    )
    @settings(max_examples=20, deadline=None)
    def test_config_round_trip(
        self, app, circle_radius, circle_thickness,
        spotlight_radius, spotlight_darkness, ripple_duration
    ):
        """Property 1: 配置持久化往返
        
        For any set of valid parameter values, if the user sets those values
        in the debug panel, closes the panel, and reopens it, the panel
        SHALL display the same values.
        """
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 创建配置
        config = MouseHighlightConfig(
            circle_radius=circle_radius,
            circle_thickness=circle_thickness,
            spotlight_radius=spotlight_radius,
            spotlight_darkness=spotlight_darkness,
            ripple_duration=ripple_duration
        )
        
        # 创建模拟对象
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.config = MagicMock()
        config_manager.config.mouse_highlight = config
        
        highlight_manager = MagicMock()
        highlight_manager.is_enabled.return_value = True
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 创建面板
        panel = MouseHighlightDebugPanel(config_manager, highlight_manager)
        
        # 验证 UI 显示正确的值
        assert panel._parameter_sliders["circle_radius"].value() == circle_radius
        assert panel._parameter_sliders["circle_thickness"].value() == circle_thickness
        assert panel._parameter_sliders["spotlight_radius"].value() == spotlight_radius
        assert panel._parameter_sliders["spotlight_darkness"].value() == spotlight_darkness
        assert panel._parameter_sliders["ripple_duration"].value() == ripple_duration
        
        panel.close()
        MouseHighlightDebugPanel._instance = None
    
    @given(st.sampled_from(list(MOUSE_HIGHLIGHT_THEMES.keys())))
    @settings(max_examples=10, deadline=None)
    def test_theme_selection_persists(self, app, theme_key):
        """测试主题选择持久化"""
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 创建配置
        config = MouseHighlightConfig(theme=theme_key)
        
        # 创建模拟对象
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.config = MagicMock()
        config_manager.config.mouse_highlight = config
        
        highlight_manager = MagicMock()
        highlight_manager.is_enabled.return_value = True
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 创建面板
        panel = MouseHighlightDebugPanel(config_manager, highlight_manager)
        
        # 验证正确的主题按钮被选中
        assert panel._theme_buttons[theme_key].is_selected()
        
        # 验证其他主题按钮未选中
        for key, btn in panel._theme_buttons.items():
            if key != theme_key:
                assert not btn.is_selected()
        
        panel.close()
        MouseHighlightDebugPanel._instance = None
    
    @given(
        circle_enabled=st.booleans(),
        spotlight_enabled=st.booleans(),
        cursor_magnify_enabled=st.booleans(),
        click_effect_enabled=st.booleans()
    )
    @settings(max_examples=16, deadline=None)
    def test_effect_toggles_persist(
        self, app, circle_enabled, spotlight_enabled,
        cursor_magnify_enabled, click_effect_enabled
    ):
        """测试效果开关持久化"""
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        # 创建配置
        config = MouseHighlightConfig(
            circle_enabled=circle_enabled,
            spotlight_enabled=spotlight_enabled,
            cursor_magnify_enabled=cursor_magnify_enabled,
            click_effect_enabled=click_effect_enabled
        )
        
        # 创建模拟对象
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.config = MagicMock()
        config_manager.config.mouse_highlight = config
        
        highlight_manager = MagicMock()
        highlight_manager.is_enabled.return_value = True
        
        # 清除单例
        MouseHighlightDebugPanel._instance = None
        
        # 创建面板
        panel = MouseHighlightDebugPanel(config_manager, highlight_manager)
        
        # 验证效果开关状态
        assert panel._effect_checkboxes["circle"].isChecked() == circle_enabled
        assert panel._effect_checkboxes["spotlight"].isChecked() == spotlight_enabled
        assert panel._effect_checkboxes["cursor_magnify"].isChecked() == cursor_magnify_enabled
        assert panel._effect_checkboxes["click_effect"].isChecked() == click_effect_enabled
        
        panel.close()
        MouseHighlightDebugPanel._instance = None


class TestMouseHighlightDebugPanelParameterControls:
    """参数控件状态测试"""
    
    def test_disabled_effect_dims_parameters(self, debug_panel):
        """测试禁用效果时参数控件变灰"""
        # 禁用聚光灯
        debug_panel._effect_checkboxes["spotlight"].setChecked(False)
        debug_panel._update_parameter_controls_state()
        
        # 验证聚光灯参数组被禁用
        assert not debug_panel._parameter_groups["spotlight"].isEnabled()
    
    def test_enabled_effect_enables_parameters(self, debug_panel):
        """测试启用效果时参数控件可用"""
        # 启用聚光灯
        debug_panel._effect_checkboxes["spotlight"].setChecked(True)
        debug_panel._update_parameter_controls_state()
        
        # 验证聚光灯参数组被启用
        assert debug_panel._parameter_groups["spotlight"].isEnabled()
