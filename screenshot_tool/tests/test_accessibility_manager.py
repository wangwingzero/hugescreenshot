# =====================================================
# =============== 无障碍管理器测试 ===============
# =====================================================

"""
AccessibilityManager 单元测试

Feature: performance-ui-optimization
Requirements: 8.5 - 尊重系统 reduced-motion 偏好

测试内容：
1. detect_reduced_motion 函数正确检测系统设置
2. AccessibilityManager 单例模式
3. 组件注册和通知机制
4. 回调函数机制
5. 设置刷新功能
"""

import sys
from unittest.mock import MagicMock, patch
import pytest

from screenshot_tool.core.accessibility_manager import (
    AccessibilityManager,
    AccessibilitySettings,
    detect_reduced_motion,
    is_reduced_motion_enabled,
    should_animate,
    SPI_GETCLIENTAREAANIMATION,
)


class TestAccessibilitySettings:
    """AccessibilitySettings 数据类测试"""
    
    def test_default_settings(self):
        """测试默认设置"""
        settings = AccessibilitySettings()
        assert settings.reduced_motion is False
        assert settings.animations_enabled is True
    
    def test_reduced_motion_enabled(self):
        """测试 reduced_motion 启用时 animations_enabled 为 False"""
        settings = AccessibilitySettings(reduced_motion=True)
        assert settings.reduced_motion is True
        assert settings.animations_enabled is False
    
    def test_reduced_motion_disabled(self):
        """测试 reduced_motion 禁用时 animations_enabled 为 True"""
        settings = AccessibilitySettings(reduced_motion=False)
        assert settings.reduced_motion is False
        assert settings.animations_enabled is True


class TestDetectReducedMotion:
    """detect_reduced_motion 函数测试"""
    
    def test_non_windows_returns_false(self):
        """非 Windows 平台应返回 False"""
        with patch.object(sys, 'platform', 'linux'):
            result = detect_reduced_motion()
            assert result is False
        
        with patch.object(sys, 'platform', 'darwin'):
            result = detect_reduced_motion()
            assert result is False
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only test")
    def test_windows_api_call(self):
        """Windows 平台应调用 SystemParametersInfo API"""
        # 这个测试在 Windows 上运行，验证 API 调用不会崩溃
        result = detect_reduced_motion()
        assert isinstance(result, bool)
    
    def test_api_failure_returns_false(self):
        """API 调用失败时应返回 False"""
        with patch.object(sys, 'platform', 'win32'):
            with patch('ctypes.windll.user32.SystemParametersInfoW', return_value=0):
                result = detect_reduced_motion()
                assert result is False
    
    def test_exception_returns_false(self):
        """异常时应返回 False"""
        with patch.object(sys, 'platform', 'win32'):
            with patch('ctypes.windll.user32.SystemParametersInfoW', side_effect=Exception("Test error")):
                result = detect_reduced_motion()
                assert result is False


class TestAccessibilityManagerSingleton:
    """AccessibilityManager 单例模式测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_singleton_instance(self):
        """测试单例模式返回相同实例"""
        instance1 = AccessibilityManager.instance()
        instance2 = AccessibilityManager.instance()
        assert instance1 is instance2
    
    def test_reset_instance(self):
        """测试重置单例"""
        instance1 = AccessibilityManager.instance()
        AccessibilityManager.reset_instance()
        instance2 = AccessibilityManager.instance()
        assert instance1 is not instance2


class TestAccessibilityManagerProperties:
    """AccessibilityManager 属性测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_settings_property(self):
        """测试 settings 属性返回 AccessibilitySettings"""
        manager = AccessibilityManager.instance()
        settings = manager.settings
        assert isinstance(settings, AccessibilitySettings)
    
    def test_reduced_motion_property(self):
        """测试 reduced_motion 属性"""
        manager = AccessibilityManager.instance()
        assert isinstance(manager.reduced_motion, bool)
    
    def test_animations_enabled_property(self):
        """测试 animations_enabled 属性"""
        manager = AccessibilityManager.instance()
        assert isinstance(manager.animations_enabled, bool)
        # animations_enabled 应该是 reduced_motion 的反向
        assert manager.animations_enabled == (not manager.reduced_motion)


class TestAccessibilityManagerComponentRegistration:
    """AccessibilityManager 组件注册测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_register_component(self):
        """测试注册组件"""
        manager = AccessibilityManager.instance()
        mock_component = MagicMock()
        mock_component.set_animations_enabled = MagicMock()
        
        manager.register_animated_component(mock_component)
        
        assert manager.get_registered_component_count() == 1
        # 注册时应立即应用当前设置
        mock_component.set_animations_enabled.assert_called_once_with(manager.animations_enabled)
    
    def test_register_same_component_twice(self):
        """测试重复注册同一组件不会增加计数"""
        manager = AccessibilityManager.instance()
        mock_component = MagicMock()
        mock_component.set_animations_enabled = MagicMock()
        
        manager.register_animated_component(mock_component)
        manager.register_animated_component(mock_component)
        
        assert manager.get_registered_component_count() == 1
    
    def test_unregister_component(self):
        """测试取消注册组件"""
        manager = AccessibilityManager.instance()
        mock_component = MagicMock()
        mock_component.set_animations_enabled = MagicMock()
        
        manager.register_animated_component(mock_component)
        assert manager.get_registered_component_count() == 1
        
        manager.unregister_animated_component(mock_component)
        assert manager.get_registered_component_count() == 0
    
    def test_unregister_nonexistent_component(self):
        """测试取消注册不存在的组件不会报错"""
        manager = AccessibilityManager.instance()
        mock_component = MagicMock()
        
        # 不应抛出异常
        manager.unregister_animated_component(mock_component)
        assert manager.get_registered_component_count() == 0


class TestAccessibilityManagerCallbacks:
    """AccessibilityManager 回调函数测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_register_callback(self):
        """测试注册回调函数"""
        manager = AccessibilityManager.instance()
        callback = MagicMock()
        
        manager.register_callback(callback)
        
        # 回调应该在设置变化时被调用
        # 这里我们手动触发通知来测试
        manager._notify_callbacks()
        callback.assert_called_once_with(manager.animations_enabled)
    
    def test_unregister_callback(self):
        """测试取消注册回调函数"""
        manager = AccessibilityManager.instance()
        callback = MagicMock()
        
        manager.register_callback(callback)
        manager.unregister_callback(callback)
        
        manager._notify_callbacks()
        callback.assert_not_called()
    
    def test_callback_exception_ignored(self):
        """测试回调异常被忽略"""
        manager = AccessibilityManager.instance()
        bad_callback = MagicMock(side_effect=Exception("Test error"))
        good_callback = MagicMock()
        
        manager.register_callback(bad_callback)
        manager.register_callback(good_callback)
        
        # 不应抛出异常，且 good_callback 应该被调用
        manager._notify_callbacks()
        good_callback.assert_called_once()


class TestAccessibilityManagerRefresh:
    """AccessibilityManager 刷新功能测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_refresh_returns_false_when_no_change(self):
        """测试设置未变化时 refresh 返回 False"""
        manager = AccessibilityManager.instance()
        
        # 第一次刷新后设置应该相同
        result = manager.refresh()
        # 由于系统设置没有变化，应该返回 False
        assert result is False
    
    def test_refresh_notifies_components_on_change(self):
        """测试设置变化时通知组件"""
        manager = AccessibilityManager.instance()
        mock_component = MagicMock()
        mock_component.set_animations_enabled = MagicMock()
        
        manager.register_animated_component(mock_component)
        mock_component.set_animations_enabled.reset_mock()
        
        # 模拟设置变化
        old_reduced_motion = manager._settings.reduced_motion
        manager._settings = AccessibilitySettings(reduced_motion=not old_reduced_motion)
        
        # 手动调用通知
        manager._notify_components()
        
        mock_component.set_animations_enabled.assert_called_once()


class TestAccessibilityManagerApplyToAll:
    """AccessibilityManager apply_to_all_components 测试"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_apply_to_all_components(self):
        """测试批量应用设置到所有组件"""
        manager = AccessibilityManager.instance()
        
        mock_component1 = MagicMock()
        mock_component1.set_animations_enabled = MagicMock()
        mock_component2 = MagicMock()
        mock_component2.set_animations_enabled = MagicMock()
        
        manager.register_animated_component(mock_component1)
        manager.register_animated_component(mock_component2)
        
        # 重置 mock 调用记录
        mock_component1.set_animations_enabled.reset_mock()
        mock_component2.set_animations_enabled.reset_mock()
        
        manager.apply_to_all_components()
        
        mock_component1.set_animations_enabled.assert_called_once_with(manager.animations_enabled)
        mock_component2.set_animations_enabled.assert_called_once_with(manager.animations_enabled)


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_is_reduced_motion_enabled(self):
        """测试 is_reduced_motion_enabled 函数"""
        result = is_reduced_motion_enabled()
        assert isinstance(result, bool)
    
    def test_should_animate(self):
        """测试 should_animate 函数"""
        result = should_animate()
        assert isinstance(result, bool)
        # should_animate 应该是 is_reduced_motion_enabled 的反向
        assert result == (not is_reduced_motion_enabled())


class TestComponentWithoutSetAnimationsEnabled:
    """测试没有 set_animations_enabled 方法的组件"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    def test_component_without_method_ignored(self):
        """测试没有 set_animations_enabled 方法的组件被忽略"""
        manager = AccessibilityManager.instance()
        
        # 创建一个没有 set_animations_enabled 方法的对象
        mock_component = object()
        
        # 不应抛出异常
        manager.register_animated_component(mock_component)
        manager.apply_to_all_components()
        
        # 组件仍然被注册
        assert manager.get_registered_component_count() == 1


# =====================================================
# =============== 无障碍属性测试 (Property-Based Tests) ===============
# =====================================================

"""
Property-Based Tests for Accessibility Compliance

Feature: performance-ui-optimization
Property 7: Accessibility Compliance

使用 hypothesis 库进行属性测试，验证：
1. reduced-motion 启用时动画时长为 0
2. 焦点指示器样式存在于按钮样式中

**Validates: Requirements 8.4, 8.5**
"""

from hypothesis import given, strategies as st, settings, assume, HealthCheck
import pytest


class TestAccessibilityPropertyReducedMotion:
    """Property 7: Accessibility Compliance - Reduced Motion
    
    **Validates: Requirements 8.4, 8.5**
    
    验证 reduced-motion 启用时动画时长为 0。
    """
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    @settings(max_examples=100)
    @given(st.booleans())
    def test_animations_enabled_inverse_of_reduced_motion(self, reduced_motion: bool):
        """Property: animations_enabled SHALL be the inverse of reduced_motion
        
        **Validates: Requirements 8.5**
        
        For any reduced_motion setting, animations_enabled SHALL be its inverse.
        """
        settings_obj = AccessibilitySettings(reduced_motion=reduced_motion)
        assert settings_obj.animations_enabled == (not reduced_motion)
    
    @settings(max_examples=100)
    @given(st.booleans())
    def test_component_receives_correct_animation_state(self, animations_enabled: bool):
        """Property: Components SHALL receive correct animation state
        
        **Validates: Requirements 8.5**
        
        For any animations_enabled state, registered components SHALL receive
        the correct value via set_animations_enabled.
        """
        manager = AccessibilityManager.instance()
        
        # 创建 mock 组件
        mock_component = MagicMock()
        mock_component.set_animations_enabled = MagicMock()
        
        # 手动设置 manager 的状态
        manager._settings = AccessibilitySettings(reduced_motion=not animations_enabled)
        
        # 注册组件
        manager.register_animated_component(mock_component)
        
        # 验证组件收到正确的状态
        mock_component.set_animations_enabled.assert_called_with(animations_enabled)


class TestAccessibilityPropertyAnimatedButton:
    """Property 7: Accessibility Compliance - AnimatedButton
    
    **Validates: Requirements 8.4, 8.5**
    
    验证 AnimatedButton 在 reduced-motion 时动画时长为 0。
    """
    
    @pytest.fixture
    def qapp(self, qtbot):
        """确保 Qt 应用存在"""
        return qtbot
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.sampled_from(["primary", "secondary", "danger"]))
    def test_animated_button_respects_reduced_motion(self, qapp, style: str):
        """Property: AnimatedButton animation duration SHALL be 0 when reduced-motion is enabled
        
        **Validates: Requirements 8.5**
        
        For any button style, when reduced-motion is enabled,
        animation duration SHALL be 0.
        """
        from screenshot_tool.ui.components.animated_button import AnimatedButton
        
        # 创建按钮
        button = AnimatedButton(text="Test", style=style)
        
        # 禁用动画（模拟 reduced-motion）
        button.set_animations_enabled(False)
        
        # 验证动画时长为 0
        assert button._hover_animation.duration() == 0, \
            f"Hover animation duration should be 0 when reduced-motion is enabled, got {button._hover_animation.duration()}"
        assert button._press_animation.duration() == 0, \
            f"Press animation duration should be 0 when reduced-motion is enabled, got {button._press_animation.duration()}"
        
        # 清理
        button.deleteLater()
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.sampled_from(["primary", "secondary", "danger"]))
    def test_animated_button_restores_animation_duration(self, qapp, style: str):
        """Property: AnimatedButton animation duration SHALL be restored when reduced-motion is disabled
        
        **Validates: Requirements 8.5**
        
        For any button style, when reduced-motion is disabled,
        animation duration SHALL be restored to normal values.
        """
        from screenshot_tool.ui.components.animated_button import AnimatedButton
        from screenshot_tool.ui.styles import AnimationConstants
        
        # 创建按钮
        button = AnimatedButton(text="Test", style=style)
        
        # 先禁用动画
        button.set_animations_enabled(False)
        
        # 再启用动画
        button.set_animations_enabled(True)
        
        # 验证动画时长恢复
        assert button._hover_animation.duration() == AnimationConstants.FAST, \
            f"Hover animation duration should be {AnimationConstants.FAST}ms, got {button._hover_animation.duration()}"
        assert button._press_animation.duration() == AnimationConstants.INSTANT, \
            f"Press animation duration should be {AnimationConstants.INSTANT}ms, got {button._press_animation.duration()}"
        
        # 清理
        button.deleteLater()


class TestAccessibilityPropertySuccessIndicator:
    """Property 7: Accessibility Compliance - SuccessIndicator
    
    **Validates: Requirements 8.4, 8.5**
    
    验证 SuccessIndicator 在 reduced-motion 时动画时长为 0。
    """
    
    @pytest.fixture
    def qapp(self, qtbot):
        """确保 Qt 应用存在"""
        return qtbot
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.integers(min_value=16, max_value=64))
    def test_success_indicator_respects_reduced_motion(self, qapp, size: int):
        """Property: SuccessIndicator animation duration SHALL be 0 when reduced-motion is enabled
        
        **Validates: Requirements 8.5**
        
        For any indicator size, when reduced-motion is enabled,
        animation duration SHALL be 0.
        """
        from screenshot_tool.ui.components.success_indicator import SuccessIndicator
        
        # 创建指示器
        indicator = SuccessIndicator(size=size)
        
        # 禁用动画（模拟 reduced-motion）
        indicator.set_animations_enabled(False)
        
        # 验证动画组的总时长为 0
        # 检查成功动画组
        success_duration = indicator._success_animation.duration()
        assert success_duration == 0, \
            f"Success animation duration should be 0 when reduced-motion is enabled, got {success_duration}"
        
        # 检查错误动画组
        error_duration = indicator._error_animation.duration()
        assert error_duration == 0, \
            f"Error animation duration should be 0 when reduced-motion is enabled, got {error_duration}"
        
        # 清理
        indicator.deleteLater()


class TestAccessibilityPropertyFocusIndicators:
    """Property 7: Accessibility Compliance - Focus Indicators
    
    **Validates: Requirements 8.4**
    
    验证焦点指示器样式存在于按钮样式中。
    """
    
    @settings(max_examples=100)
    @given(st.sampled_from([
        "BUTTON_PRIMARY_STYLE",
        "BUTTON_SECONDARY_STYLE",
        "BUTTON_DANGER_STYLE",
        "TOOLBUTTON_STYLE",
        "THEME_BUTTON_STYLE",
    ]))
    def test_focus_indicator_exists_in_button_styles(self, style_name: str):
        """Property: Focus indicators SHALL be visible for keyboard navigation
        
        **Validates: Requirements 8.4**
        
        For any button style, :focus pseudo-class SHALL be defined
        to provide visible focus indicators.
        """
        from screenshot_tool.ui import styles
        
        style_content = getattr(styles, style_name)
        
        # 验证 :focus 伪类存在
        assert ":focus" in style_content, \
            f"Style {style_name} should contain :focus pseudo-class for keyboard navigation"
    
    @settings(max_examples=100)
    @given(st.sampled_from([
        "BUTTON_PRIMARY_STYLE",
        "BUTTON_SECONDARY_STYLE",
        "BUTTON_DANGER_STYLE",
        "TOOLBUTTON_STYLE",
        "THEME_BUTTON_STYLE",
    ]))
    def test_focus_indicator_has_border_style(self, style_name: str):
        """Property: Focus indicators SHALL have visible border styling
        
        **Validates: Requirements 8.4**
        
        For any button style with :focus, there SHALL be a border
        property defined to make focus visible.
        """
        from screenshot_tool.ui import styles
        
        style_content = getattr(styles, style_name)
        
        # 找到 :focus 块
        focus_start = style_content.find(":focus")
        if focus_start == -1:
            pytest.fail(f"Style {style_name} should contain :focus pseudo-class")
        
        # 找到 :focus 块的结束位置（下一个 } 或下一个选择器）
        focus_block_start = style_content.find("{", focus_start)
        focus_block_end = style_content.find("}", focus_block_start)
        
        if focus_block_start == -1 or focus_block_end == -1:
            pytest.fail(f"Style {style_name} has malformed :focus block")
        
        focus_block = style_content[focus_block_start:focus_block_end]
        
        # 验证 :focus 块包含 border 属性
        assert "border" in focus_block.lower(), \
            f"Style {style_name} :focus block should contain border property for visibility"


class TestAccessibilityPropertyInputFocus:
    """Property 7: Accessibility Compliance - Input Focus
    
    **Validates: Requirements 8.4**
    
    验证输入框焦点指示器样式存在。
    """
    
    @settings(max_examples=50)
    @given(st.sampled_from([
        "INPUT_STYLE",
        "NUMBER_INPUT_STYLE",
        "CHECKBOX_STYLE",
    ]))
    def test_input_focus_indicator_exists(self, style_name: str):
        """Property: Input focus indicators SHALL be visible
        
        **Validates: Requirements 8.4**
        
        For any input style, :focus pseudo-class SHALL be defined.
        """
        from screenshot_tool.ui import styles
        
        style_content = getattr(styles, style_name)
        
        # 验证 :focus 伪类存在
        assert ":focus" in style_content, \
            f"Style {style_name} should contain :focus pseudo-class for keyboard navigation"


class TestAccessibilityPropertyAnimationDurationZero:
    """Property 7: Accessibility Compliance - Animation Duration Zero
    
    **Validates: Requirements 8.5**
    
    综合测试：验证所有动画组件在 reduced-motion 时动画时长为 0。
    """
    
    @pytest.fixture
    def qapp(self, qtbot):
        """确保 Qt 应用存在"""
        return qtbot
    
    def setup_method(self):
        """每个测试前重置单例"""
        AccessibilityManager.reset_instance()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        AccessibilityManager.reset_instance()
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        st.sampled_from(["primary", "secondary", "danger"]),
        st.integers(min_value=16, max_value=64)
    )
    def test_all_animated_components_respect_reduced_motion(
        self, qapp, button_style: str, indicator_size: int
    ):
        """Property: ALL animated components SHALL have 0 duration when reduced-motion is enabled
        
        **Validates: Requirements 8.5**
        
        For any combination of animated components, when reduced-motion is enabled,
        ALL animation durations SHALL be 0.
        """
        from screenshot_tool.ui.components.animated_button import AnimatedButton
        from screenshot_tool.ui.components.success_indicator import SuccessIndicator
        
        # 创建组件
        button = AnimatedButton(text="Test", style=button_style)
        indicator = SuccessIndicator(size=indicator_size)
        
        # 禁用动画
        button.set_animations_enabled(False)
        indicator.set_animations_enabled(False)
        
        # 验证所有动画时长为 0
        assert button._hover_animation.duration() == 0
        assert button._press_animation.duration() == 0
        assert indicator._success_animation.duration() == 0
        assert indicator._error_animation.duration() == 0
        
        # 清理
        button.deleteLater()
        indicator.deleteLater()
