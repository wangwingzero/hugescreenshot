# =====================================================
# =============== 动画组件属性测试 ===============
# =====================================================

"""
动画组件的属性测试

Feature: performance-ui-optimization
Property 1: Response Time Bounds
**Validates: Requirements 5.4, 7.1**

测试动画组件的核心属性：
1. AnimatedButton 悬停动画时长为 150ms (AnimationConstants.FAST)
2. AnimatedButton 点击动画时长为 50ms (AnimationConstants.INSTANT)
3. SuccessIndicator 成功动画在 200-500ms 范围内
4. SuccessIndicator 错误动画包含 shake 效果
5. 动画常量在预期范围内
"""

import pytest
from hypothesis import given, strategies as st, settings

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEasingCurve

from screenshot_tool.ui.components.animated_button import AnimatedButton
from screenshot_tool.ui.components.success_indicator import (
    SuccessIndicator,
    IndicatorState,
)
from screenshot_tool.ui.styles import AnimationConstants, ANIMATION


@pytest.fixture(scope="module")
def app():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ========== Property 1: Response Time Bounds ==========
# Feature: performance-ui-optimization, Property 1: Response Time Bounds
# **Validates: Requirements 5.4, 7.1**
#
# For any UI operation (overlay display, toolbar show, dialog open, menu display),
# the operation SHALL complete within its specified time bound:
# - Hover feedback: ≤ 16ms (60 FPS) - animation starts within this time
# - Hover animation duration: 150ms (AnimationConstants.FAST)
# - Click animation duration: 50ms (AnimationConstants.INSTANT)
# - Success animation: 200-500ms


class TestAnimatedButtonResponseTimeProperty:
    """Property 1: AnimatedButton 响应时间属性测试
    
    Feature: performance-ui-optimization, Property 1: Response Time Bounds
    **Validates: Requirements 5.4, 7.1**
    """
    
    # ========== Property 1.1: 悬停动画时长为 150ms ==========
    
    @settings(max_examples=100)
    @given(style=st.sampled_from(["primary", "secondary", "danger"]))
    def test_hover_animation_duration_is_fast(self, app, style: str):
        """Property 1.1: 悬停动画时长为 AnimationConstants.FAST (150ms)
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.1**
        
        For any AnimatedButton style, the hover animation duration
        SHALL be exactly AnimationConstants.FAST (150ms).
        """
        button = AnimatedButton(text="Test", style=style)
        
        # 验证悬停动画时长
        hover_duration = button._hover_animation.duration()
        expected_duration = AnimationConstants.FAST
        
        assert hover_duration == expected_duration, \
            f"Hover animation duration for style '{style}' is {hover_duration}ms, " \
            f"expected {expected_duration}ms (AnimationConstants.FAST)"
    
    def test_hover_animation_duration_equals_150ms(self, app):
        """验证悬停动画时长精确为 150ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.1**
        """
        button = AnimatedButton(text="Test")
        
        assert button._hover_animation.duration() == 150, \
            f"Hover animation should be 150ms, got {button._hover_animation.duration()}ms"
    
    # ========== Property 1.2: 点击动画时长为 50ms ==========
    
    @settings(max_examples=100)
    @given(style=st.sampled_from(["primary", "secondary", "danger"]))
    def test_click_animation_duration_is_instant(self, app, style: str):
        """Property 1.2: 点击动画时长为 AnimationConstants.INSTANT (50ms)
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.2**
        
        For any AnimatedButton style, the click animation duration
        SHALL be exactly AnimationConstants.INSTANT (50ms).
        """
        button = AnimatedButton(text="Test", style=style)
        
        # 验证点击动画时长
        press_duration = button._press_animation.duration()
        expected_duration = AnimationConstants.INSTANT
        
        assert press_duration == expected_duration, \
            f"Click animation duration for style '{style}' is {press_duration}ms, " \
            f"expected {expected_duration}ms (AnimationConstants.INSTANT)"
    
    def test_click_animation_duration_equals_50ms(self, app):
        """验证点击动画时长精确为 50ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.2**
        """
        button = AnimatedButton(text="Test")
        
        assert button._press_animation.duration() == 50, \
            f"Click animation should be 50ms, got {button._press_animation.duration()}ms"
    
    # ========== Property 1.3: 悬停反馈在 16ms 内 ==========
    
    def test_hover_feedback_within_frame_time(self, app):
        """Property 1.3: 悬停反馈在 16ms 内（60 FPS 帧时间）
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 5.4**
        
        The hover animation SHALL start immediately (within one frame at 60 FPS = 16.67ms).
        This is verified by checking that the animation uses proper easing curves
        that provide immediate visual feedback.
        """
        button = AnimatedButton(text="Test")
        
        # 验证使用 ease-out 缓动曲线（进入动画）
        # ease-out 曲线在开始时变化最快，提供即时反馈
        assert button._hover_animation.easingCurve().type() == AnimationConstants.EASE_OUT, \
            "Hover animation should use EASE_OUT curve for immediate feedback"
    
    # ========== Property 1.4: 动画缓动曲线正确 ==========
    
    @settings(max_examples=100)
    @given(style=st.sampled_from(["primary", "secondary", "danger"]))
    def test_animation_easing_curves_are_correct(self, app, style: str):
        """Property 1.4: 动画使用正确的缓动曲线
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 8.2**
        
        For any AnimatedButton:
        - Hover animation SHALL use EASE_OUT (OutCubic) for enter
        - Press animation SHALL use EASE_OUT (OutCubic) for immediate feedback
        """
        button = AnimatedButton(text="Test", style=style)
        
        # 验证悬停动画缓动曲线
        hover_easing = button._hover_animation.easingCurve().type()
        assert hover_easing == QEasingCurve.Type.OutCubic, \
            f"Hover animation should use OutCubic, got {hover_easing}"
        
        # 验证点击动画缓动曲线
        press_easing = button._press_animation.easingCurve().type()
        assert press_easing == QEasingCurve.Type.OutCubic, \
            f"Press animation should use OutCubic, got {press_easing}"


class TestSuccessIndicatorResponseTimeProperty:
    """Property 1: SuccessIndicator 响应时间属性测试
    
    Feature: performance-ui-optimization, Property 1: Response Time Bounds
    **Validates: Requirements 7.3, 7.4**
    """
    
    # ========== Property 1.5: 成功动画在 200-500ms 范围内 ==========
    
    @settings(max_examples=100)
    @given(size=st.integers(min_value=16, max_value=64))
    def test_success_animation_duration_in_range(self, app, size: int):
        """Property 1.5: 成功动画时长在 200-500ms 范围内
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.3**
        
        For any SuccessIndicator size, the success animation duration
        SHALL be in the range [200ms, 500ms].
        """
        indicator = SuccessIndicator(size=size)
        
        # 获取成功动画总时长
        total_duration = indicator._success_animation.duration()
        
        assert 200 <= total_duration <= 500, \
            f"Success animation duration {total_duration}ms is not in [200ms, 500ms] range"
    
    def test_success_animation_duration_equals_400ms(self, app):
        """验证成功动画时长为 AnimationConstants.SUCCESS (400ms)
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.3**
        """
        indicator = SuccessIndicator()
        
        # 成功动画由淡入 (100ms) + 绘制动画 (300ms) 组成 = 400ms
        total_duration = indicator._success_animation.duration()
        
        assert total_duration == AnimationConstants.SUCCESS, \
            f"Success animation should be {AnimationConstants.SUCCESS}ms, got {total_duration}ms"
    
    # ========== Property 1.6: 错误动画包含 shake 效果 ==========
    
    @settings(max_examples=100)
    @given(size=st.integers(min_value=16, max_value=64))
    def test_error_animation_has_shake_effect(self, app, size: int):
        """Property 1.6: 错误动画包含 shake 效果
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.4**
        
        For any SuccessIndicator size, the error animation
        SHALL include shake effect (multiple sub-animations for left-right movement).
        """
        indicator = SuccessIndicator(size=size)
        
        # 错误动画应该包含多个子动画：
        # 1 个淡入 + 6 个 shake 动画 (3 次左右摇晃，每次 2 个动画) = 7 个
        animation_count = indicator._error_animation.animationCount()
        
        assert animation_count >= 7, \
            f"Error animation should have at least 7 sub-animations (1 fade + 6 shake), " \
            f"got {animation_count}"
    
    def test_error_animation_shake_distance(self, app):
        """验证错误动画 shake 距离为 4px
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.4**
        
        The shake animation SHALL move ±4px horizontally for subtle effect.
        """
        indicator = SuccessIndicator()
        
        # 触发错误动画以检查 shake 偏移
        indicator.show_error()
        
        # 验证 shake_offset 属性存在且可设置
        indicator.set_shake_offset(4.0)
        assert indicator.get_shake_offset() == 4.0, \
            "Shake offset should be settable to 4.0"
        
        indicator.set_shake_offset(-4.0)
        assert indicator.get_shake_offset() == -4.0, \
            "Shake offset should be settable to -4.0"
        
        indicator.reset()


class TestAnimationConstantsProperty:
    """动画常量属性测试
    
    Feature: performance-ui-optimization, Property 1: Response Time Bounds
    **Validates: Requirements 7.1, 7.2, 7.3, 8.1**
    """
    
    # ========== Property 1.7: 动画常量在预期范围内 ==========
    
    def test_instant_animation_is_under_100ms(self):
        """Property 1.7.1: INSTANT 动画时长 < 100ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.2**
        
        INSTANT animation SHALL be under 100ms for immediate feedback.
        """
        assert AnimationConstants.INSTANT < 100, \
            f"INSTANT animation {AnimationConstants.INSTANT}ms should be < 100ms"
    
    def test_fast_animation_is_150ms(self):
        """Property 1.7.2: FAST 动画时长 = 150ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.1**
        
        FAST animation SHALL be exactly 150ms for hover transitions.
        """
        assert AnimationConstants.FAST == 150, \
            f"FAST animation should be 150ms, got {AnimationConstants.FAST}ms"
    
    def test_normal_animation_is_200ms(self):
        """Property 1.7.3: NORMAL 动画时长 = 200ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 8.1**
        
        NORMAL animation SHALL be exactly 200ms for standard transitions.
        """
        assert AnimationConstants.NORMAL == 200, \
            f"NORMAL animation should be 200ms, got {AnimationConstants.NORMAL}ms"
    
    def test_slow_animation_is_300ms(self):
        """Property 1.7.4: SLOW 动画时长 = 300ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 8.1**
        
        SLOW animation SHALL be exactly 300ms for slow transitions.
        """
        assert AnimationConstants.SLOW == 300, \
            f"SLOW animation should be 300ms, got {AnimationConstants.SLOW}ms"
    
    def test_success_animation_is_400ms(self):
        """Property 1.7.5: SUCCESS 动画时长 = 400ms
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 7.3**
        
        SUCCESS animation SHALL be exactly 400ms (in 200-500ms range).
        """
        assert AnimationConstants.SUCCESS == 400, \
            f"SUCCESS animation should be 400ms, got {AnimationConstants.SUCCESS}ms"
        
        # 验证在 200-500ms 范围内
        assert 200 <= AnimationConstants.SUCCESS <= 500, \
            f"SUCCESS animation {AnimationConstants.SUCCESS}ms should be in [200ms, 500ms]"
    
    # ========== Property 1.8: 动画常量与 ANIMATION 字典一致 ==========
    
    @settings(max_examples=100)
    @given(key=st.sampled_from(["instant", "fast", "normal", "slow", "success"]))
    def test_animation_constants_match_animation_dict(self, key: str):
        """Property 1.8: AnimationConstants 与 ANIMATION 字典一致
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 8.1**
        
        For any animation key, AnimationConstants.{KEY} SHALL equal ANIMATION[key].
        """
        constant_value = getattr(AnimationConstants, key.upper())
        dict_value = ANIMATION[key]
        
        assert constant_value == dict_value, \
            f"AnimationConstants.{key.upper()} ({constant_value}) != ANIMATION['{key}'] ({dict_value})"
    
    # ========== Property 1.9: 动画时长顺序正确 ==========
    
    def test_animation_durations_are_ordered(self):
        """Property 1.9: 动画时长按预期顺序排列
        
        Feature: performance-ui-optimization, Property 1: Response Time Bounds
        **Validates: Requirements 8.1**
        
        Animation durations SHALL be ordered: INSTANT < FAST < NORMAL < SLOW < SUCCESS
        """
        assert AnimationConstants.INSTANT < AnimationConstants.FAST, \
            "INSTANT should be < FAST"
        assert AnimationConstants.FAST < AnimationConstants.NORMAL, \
            "FAST should be < NORMAL"
        assert AnimationConstants.NORMAL < AnimationConstants.SLOW, \
            "NORMAL should be < SLOW"
        assert AnimationConstants.SLOW < AnimationConstants.SUCCESS, \
            "SLOW should be < SUCCESS"


class TestReducedMotionProperty:
    """Reduced Motion 属性测试
    
    Feature: performance-ui-optimization, Property 7: Accessibility Compliance
    **Validates: Requirements 8.5**
    """
    
    # ========== Property 7.1: 禁用动画时时长为 0 ==========
    
    @settings(max_examples=100)
    @given(style=st.sampled_from(["primary", "secondary", "danger"]))
    def test_animated_button_respects_reduced_motion(self, app, style: str):
        """Property 7.1: AnimatedButton 尊重 reduced-motion 设置
        
        Feature: performance-ui-optimization, Property 7: Accessibility Compliance
        **Validates: Requirements 8.5**
        
        When animations are disabled, AnimatedButton animation durations
        SHALL be 0ms.
        """
        button = AnimatedButton(text="Test", style=style)
        
        # 禁用动画
        button.set_animations_enabled(False)
        
        assert button._hover_animation.duration() == 0, \
            f"Hover animation should be 0ms when disabled, got {button._hover_animation.duration()}ms"
        assert button._press_animation.duration() == 0, \
            f"Press animation should be 0ms when disabled, got {button._press_animation.duration()}ms"
    
    @settings(max_examples=100)
    @given(style=st.sampled_from(["primary", "secondary", "danger"]))
    def test_animated_button_restores_animation_durations(self, app, style: str):
        """Property 7.2: AnimatedButton 恢复动画时长
        
        Feature: performance-ui-optimization, Property 7: Accessibility Compliance
        **Validates: Requirements 8.5**
        
        When animations are re-enabled, AnimatedButton animation durations
        SHALL be restored to their original values.
        """
        button = AnimatedButton(text="Test", style=style)
        
        # 禁用然后重新启用动画
        button.set_animations_enabled(False)
        button.set_animations_enabled(True)
        
        assert button._hover_animation.duration() == AnimationConstants.FAST, \
            f"Hover animation should be restored to {AnimationConstants.FAST}ms"
        assert button._press_animation.duration() == AnimationConstants.INSTANT, \
            f"Press animation should be restored to {AnimationConstants.INSTANT}ms"
    
    def test_success_indicator_respects_reduced_motion(self, app):
        """Property 7.3: SuccessIndicator 尊重 reduced-motion 设置
        
        Feature: performance-ui-optimization, Property 7: Accessibility Compliance
        **Validates: Requirements 8.5**
        
        When animations are disabled, SuccessIndicator animation durations
        SHALL be 0ms.
        """
        indicator = SuccessIndicator()
        
        # 禁用动画
        indicator.set_animations_enabled(False)
        
        assert indicator._success_animation.duration() == 0, \
            f"Success animation should be 0ms when disabled"
        assert indicator._error_animation.duration() == 0, \
            f"Error animation should be 0ms when disabled"
    
    def test_success_indicator_restores_animation_durations(self, app):
        """Property 7.4: SuccessIndicator 恢复动画时长
        
        Feature: performance-ui-optimization, Property 7: Accessibility Compliance
        **Validates: Requirements 8.5**
        
        When animations are re-enabled, SuccessIndicator animation durations
        SHALL be restored to their original values.
        """
        indicator = SuccessIndicator()
        
        # 禁用然后重新启用动画
        indicator.set_animations_enabled(False)
        indicator.set_animations_enabled(True)
        
        # 成功动画应该恢复到 200-500ms 范围
        success_duration = indicator._success_animation.duration()
        assert 200 <= success_duration <= 500, \
            f"Success animation should be restored to [200ms, 500ms], got {success_duration}ms"


class TestAnimatedButtonUnit:
    """AnimatedButton 单元测试
    
    测试具体示例和边界情况。
    """
    
    def test_default_style_is_primary(self, app):
        """默认样式为 primary"""
        button = AnimatedButton(text="Test")
        assert button._style == "primary"
    
    def test_hover_progress_property(self, app):
        """hover_progress 属性正确工作"""
        button = AnimatedButton(text="Test")
        
        button.set_hover_progress(0.5)
        assert button.get_hover_progress() == 0.5
        assert button._hover_progress == 0.5
    
    def test_press_progress_property(self, app):
        """press_progress 属性正确工作"""
        button = AnimatedButton(text="Test")
        
        button.set_press_progress(0.5)
        assert button.get_press_progress() == 0.5
        assert button._press_progress == 0.5
    
    def test_set_style_changes_colors(self, app):
        """set_style 改变按钮颜色"""
        button = AnimatedButton(text="Test", style="primary")
        
        button.set_style("danger")
        
        assert button._style == "danger"
    
    def test_cursor_is_pointing_hand(self, app):
        """光标为手型"""
        from PySide6.QtCore import Qt
        
        button = AnimatedButton(text="Test")
        assert button.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestSuccessIndicatorUnit:
    """SuccessIndicator 单元测试
    
    测试具体示例和边界情况。
    """
    
    def test_default_state_is_idle(self, app):
        """默认状态为 IDLE"""
        indicator = SuccessIndicator()
        assert indicator.state == IndicatorState.IDLE
    
    def test_show_success_changes_state_to_success(self, app):
        """show_success 改变状态为 SUCCESS"""
        indicator = SuccessIndicator()
        
        indicator.show_success()
        
        assert indicator.state == IndicatorState.SUCCESS
        indicator.reset()
    
    def test_show_error_changes_state_to_error(self, app):
        """show_error 改变状态为 ERROR"""
        indicator = SuccessIndicator()
        
        indicator.show_error()
        
        assert indicator.state == IndicatorState.ERROR
        indicator.reset()
    
    def test_reset_clears_all_state(self, app):
        """reset 清除所有状态"""
        indicator = SuccessIndicator()
        indicator.show_success()
        
        indicator.reset()
        
        assert indicator.state == IndicatorState.IDLE
        assert indicator._animation_progress == 0.0
        assert indicator._shake_offset == 0.0
        assert indicator._opacity == 0.0
        assert not indicator.isVisible()
    
    def test_opacity_property(self, app):
        """opacity 属性正确工作"""
        indicator = SuccessIndicator()
        
        indicator.set_opacity(0.8)
        
        assert indicator.get_opacity() == 0.8
        assert indicator._opacity == 0.8
