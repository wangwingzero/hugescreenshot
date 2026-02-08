"""
设计系统一致性属性测试

Feature: performance-ui-optimization
Property 4: Design System Consistency
**Validates: Requirements 6.2, 8.1**

测试设计系统的核心属性：
1. 所有间距值为 4 的倍数（允许 4px 基准单位）
2. 状态过渡动画时长在 [150ms, 300ms] 范围内
3. COLORS 和 COLORS_DARK 具有一致的键
4. get_theme_colors 返回正确的主题配色
"""

import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.ui.styles import (
    SPACING,
    RADIUS,
    FONT,
    COLORS,
    COLORS_DARK,
    ANIMATION,
    AnimationConstants,
    get_theme_colors,
    get_color,
    get_spacing,
)


# ========== Property 4: Design System Consistency ==========
# Feature: performance-ui-optimization, Property 4: Design System Consistency
# **Validates: Requirements 6.2, 8.1**
#
# For any UI component in the application:
# - All spacing values SHALL be multiples of 8px (or 4px base unit)
# - All animation durations SHALL be in range [150ms, 300ms] for state transitions
# - All colors SHALL be from the defined 6-color palette
# - No gradients or heavy shadows SHALL be used


class TestDesignSystemConsistencyProperty:
    """Property 4: Design System Consistency 属性测试
    
    Feature: performance-ui-optimization, Property 4: Design System Consistency
    **Validates: Requirements 6.2, 8.1**
    """
    
    # ========== Property 4.1: 间距值为 4 的倍数 ==========
    
    @settings(max_examples=100)
    @given(spacing_key=st.sampled_from(list(SPACING.keys())))
    def test_spacing_values_are_multiples_of_4(self, spacing_key: str):
        """Property 4.1: 所有间距值为 4 的倍数
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 6.2**
        
        For any spacing value in the design system, it SHALL be a multiple of 4.
        This allows for the 4px base unit while maintaining the 8px grid system.
        """
        value = SPACING[spacing_key]
        assert value % 4 == 0, \
            f"Spacing '{spacing_key}'={value} is not a multiple of 4"
    
    def test_all_spacing_values_are_multiples_of_4(self):
        """验证所有间距值都是 4 的倍数
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 6.2**
        """
        for name, value in SPACING.items():
            assert value % 4 == 0, \
                f"Spacing '{name}'={value} is not a multiple of 4"
    
    # ========== Property 4.2: 状态过渡动画时长在 [150ms, 300ms] ==========
    
    def test_state_transition_animation_durations_in_range(self):
        """Property 4.2: 状态过渡动画时长在 [150ms, 300ms] 范围内
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 8.1**
        
        For state transitions (fast, normal, slow), animation durations
        SHALL be in the range [150ms, 300ms].
        
        Note: 'instant' (50ms) is for immediate feedback (clicks),
        and 'success' (400ms) is for completion animations - these are
        not state transitions and have different timing requirements.
        """
        # 状态过渡动画键
        state_transition_keys = ["fast", "normal", "slow"]
        
        for key in state_transition_keys:
            duration = ANIMATION[key]
            assert 150 <= duration <= 300, \
                f"Animation '{key}'={duration}ms is not in [150ms, 300ms] range"
    
    def test_animation_constants_match_animation_dict(self):
        """验证 AnimationConstants 类常量与 ANIMATION 字典一致
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 8.1**
        """
        assert AnimationConstants.INSTANT == ANIMATION["instant"]
        assert AnimationConstants.FAST == ANIMATION["fast"]
        assert AnimationConstants.NORMAL == ANIMATION["normal"]
        assert AnimationConstants.SLOW == ANIMATION["slow"]
        assert AnimationConstants.SUCCESS == ANIMATION["success"]
    
    # ========== Property 4.3: COLORS 和 COLORS_DARK 键一致性 ==========
    
    def test_colors_and_colors_dark_have_consistent_core_keys(self):
        """Property 4.3: COLORS 和 COLORS_DARK 具有一致的核心键
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 6.2**
        
        Both light and dark themes SHALL have the same core color keys
        to ensure consistent theming across the application.
        """
        # 核心颜色键（必须在两个主题中都存在）
        core_keys = [
            # 基础色
            "bg", "surface", "border",
            # 主色
            "primary", "primary_hover", "primary_light",
            # 文字色
            "text", "text_secondary", "text_muted",
            # 状态色
            "success", "warning", "error", "info",
            # 禁用色
            "disabled", "disabled_bg",
        ]
        
        for key in core_keys:
            assert key in COLORS, \
                f"Core key '{key}' missing from COLORS"
            assert key in COLORS_DARK, \
                f"Core key '{key}' missing from COLORS_DARK"
    
    @settings(max_examples=100)
    @given(color_key=st.sampled_from([
        "bg", "surface", "border",
        "primary", "primary_hover", "primary_light",
        "text", "text_secondary", "text_muted",
        "success", "warning", "error", "info",
        "disabled", "disabled_bg",
    ]))
    def test_color_keys_exist_in_both_themes(self, color_key: str):
        """Property 4.3: 颜色键在两个主题中都存在
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 6.2**
        """
        assert color_key in COLORS, \
            f"Color key '{color_key}' missing from COLORS"
        assert color_key in COLORS_DARK, \
            f"Color key '{color_key}' missing from COLORS_DARK"
    
    # ========== Property 4.4: get_theme_colors 返回正确主题 ==========
    
    @settings(max_examples=100)
    @given(dark_mode=st.booleans())
    def test_get_theme_colors_returns_correct_theme(self, dark_mode: bool):
        """Property 4.4: get_theme_colors 返回正确的主题配色
        
        Feature: performance-ui-optimization, Property 4: Design System Consistency
        **Validates: Requirements 6.2**
        
        get_theme_colors(dark_mode=True) SHALL return COLORS_DARK
        get_theme_colors(dark_mode=False) SHALL return COLORS
        """
        result = get_theme_colors(dark_mode)
        
        if dark_mode:
            assert result is COLORS_DARK, \
                "get_theme_colors(dark_mode=True) should return COLORS_DARK"
        else:
            assert result is COLORS, \
                "get_theme_colors(dark_mode=False) should return COLORS"


class TestDesignSystemUnit:
    """设计系统单元测试
    
    测试具体示例和边界情况。
    """
    
    # ========== SPACING 测试 ==========
    
    def test_spacing_has_expected_keys(self):
        """SPACING 包含预期的键"""
        expected_keys = ["xs", "sm", "md", "lg", "xl"]
        for key in expected_keys:
            assert key in SPACING, f"SPACING missing key '{key}'"
    
    def test_spacing_values_are_positive(self):
        """所有间距值为正数"""
        for name, value in SPACING.items():
            assert value > 0, f"Spacing '{name}'={value} should be positive"
    
    def test_spacing_values_are_ordered(self):
        """间距值按大小排序：xs < sm < md < lg < xl"""
        assert SPACING["xs"] < SPACING["sm"]
        assert SPACING["sm"] < SPACING["md"]
        assert SPACING["md"] < SPACING["lg"]
        assert SPACING["lg"] < SPACING["xl"]
    
    def test_get_spacing_returns_correct_value(self):
        """get_spacing 返回正确的间距值"""
        assert get_spacing("xs") == SPACING["xs"]
        assert get_spacing("sm") == SPACING["sm"]
        assert get_spacing("md") == SPACING["md"]
        assert get_spacing("lg") == SPACING["lg"]
        assert get_spacing("xl") == SPACING["xl"]
    
    def test_get_spacing_returns_default_for_unknown(self):
        """get_spacing 对未知键返回默认值 (md)"""
        assert get_spacing("unknown") == SPACING["md"]
    
    # ========== RADIUS 测试 ==========
    
    def test_radius_has_expected_keys(self):
        """RADIUS 包含预期的键"""
        expected_keys = ["sm", "md", "lg", "xl"]
        for key in expected_keys:
            assert key in RADIUS, f"RADIUS missing key '{key}'"
    
    def test_radius_values_are_positive(self):
        """所有圆角值为正数"""
        for name, value in RADIUS.items():
            assert value > 0, f"Radius '{name}'={value} should be positive"
    
    # ========== FONT 测试 ==========
    
    def test_font_has_expected_keys(self):
        """FONT 包含预期的键"""
        expected_keys = ["xs", "sm", "md", "lg", "xl"]
        for key in expected_keys:
            assert key in FONT, f"FONT missing key '{key}'"
    
    def test_font_values_are_positive(self):
        """所有字体大小为正数"""
        for name, value in FONT.items():
            assert value > 0, f"Font '{name}'={value} should be positive"
    
    # ========== ANIMATION 测试 ==========
    
    def test_animation_has_expected_keys(self):
        """ANIMATION 包含预期的键"""
        expected_keys = ["instant", "fast", "normal", "slow", "success"]
        for key in expected_keys:
            assert key in ANIMATION, f"ANIMATION missing key '{key}'"
    
    def test_animation_values_are_positive(self):
        """所有动画时长为正数"""
        for name, value in ANIMATION.items():
            assert value > 0, f"Animation '{name}'={value} should be positive"
    
    def test_animation_instant_is_fastest(self):
        """instant 是最快的动画"""
        assert ANIMATION["instant"] < ANIMATION["fast"]
    
    def test_animation_success_is_slowest(self):
        """success 是最慢的动画"""
        assert ANIMATION["success"] > ANIMATION["slow"]
    
    # ========== COLORS 测试 ==========
    
    def test_colors_values_are_valid_hex(self):
        """所有颜色值是有效的十六进制格式"""
        import re
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        
        for name, value in COLORS.items():
            assert hex_pattern.match(value), \
                f"Color '{name}'='{value}' is not a valid hex color"
    
    def test_colors_dark_values_are_valid_hex(self):
        """所有深色主题颜色值是有效的十六进制格式"""
        import re
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        
        for name, value in COLORS_DARK.items():
            assert hex_pattern.match(value), \
                f"Color '{name}'='{value}' is not a valid hex color"
    
    def test_get_color_returns_correct_value(self):
        """get_color 返回正确的颜色值"""
        assert get_color("primary") == COLORS["primary"]
        assert get_color("text") == COLORS["text"]
        assert get_color("bg") == COLORS["bg"]
    
    def test_get_color_returns_default_for_unknown(self):
        """get_color 对未知键返回默认值 (text)"""
        assert get_color("unknown") == COLORS["text"]
    
    # ========== AnimationConstants 测试 ==========
    
    def test_animation_constants_css_strings_match_values(self):
        """CSS 时长字符串与数值匹配"""
        assert AnimationConstants.CSS_INSTANT == f"{AnimationConstants.INSTANT}ms"
        assert AnimationConstants.CSS_FAST == f"{AnimationConstants.FAST}ms"
        assert AnimationConstants.CSS_NORMAL == f"{AnimationConstants.NORMAL}ms"
        assert AnimationConstants.CSS_SLOW == f"{AnimationConstants.SLOW}ms"
    
    def test_animation_constants_easing_curves_exist(self):
        """缓动曲线常量存在"""
        from PySide6.QtCore import QEasingCurve
        
        assert AnimationConstants.EASE_OUT == QEasingCurve.Type.OutCubic
        assert AnimationConstants.EASE_IN == QEasingCurve.Type.InCubic
        assert AnimationConstants.EASE_IN_OUT == QEasingCurve.Type.InOutCubic


class TestThemeConsistency:
    """主题一致性测试
    
    验证浅色和深色主题的一致性。
    """
    
    def test_highlight_colors_exist_in_both_themes(self):
        """高亮颜色在两个主题中都存在"""
        highlight_keys = [
            "highlight_yellow", "highlight_green",
            "highlight_pink", "highlight_blue",
            "highlight_yellow_border", "highlight_green_border",
            "highlight_pink_border", "highlight_blue_border",
        ]
        
        for key in highlight_keys:
            assert key in COLORS, \
                f"Highlight key '{key}' missing from COLORS"
            assert key in COLORS_DARK, \
                f"Highlight key '{key}' missing from COLORS_DARK"
    
    def test_compatibility_aliases_exist_in_both_themes(self):
        """兼容性别名在两个主题中都存在"""
        alias_keys = [
            "background", "text_primary", "text_hint", "text_white",
            "primary_pressed", "param_row_bg", "card_hover_bg", "card_hover_border",
        ]
        
        for key in alias_keys:
            assert key in COLORS, \
                f"Alias key '{key}' missing from COLORS"
            assert key in COLORS_DARK, \
                f"Alias key '{key}' missing from COLORS_DARK"
    
    def test_status_colors_are_same_in_both_themes(self):
        """状态颜色在两个主题中相同（保持一致的语义）"""
        status_keys = ["success", "warning", "error", "info"]
        
        for key in status_keys:
            assert COLORS[key] == COLORS_DARK[key], \
                f"Status color '{key}' differs between themes: " \
                f"light={COLORS[key]}, dark={COLORS_DARK[key]}"
    
    @settings(max_examples=100)
    @given(dark_mode=st.booleans())
    def test_get_theme_colors_returns_dict(self, dark_mode: bool):
        """get_theme_colors 返回字典类型"""
        result = get_theme_colors(dark_mode)
        assert isinstance(result, dict), \
            f"get_theme_colors should return dict, got {type(result)}"
    
    @settings(max_examples=100)
    @given(dark_mode=st.booleans())
    def test_get_theme_colors_has_required_keys(self, dark_mode: bool):
        """get_theme_colors 返回的字典包含必需的键"""
        result = get_theme_colors(dark_mode)
        
        required_keys = ["bg", "surface", "border", "primary", "text"]
        for key in required_keys:
            assert key in result, \
                f"get_theme_colors result missing required key '{key}'"


class TestDesignSystemIntegrity:
    """设计系统完整性测试
    
    验证设计系统的整体完整性和一致性。
    """
    
    def test_spacing_follows_8px_grid(self):
        """间距系统遵循 8px 网格（sm 及以上）
        
        xs (4px) 是例外，用于紧凑间距。
        sm 及以上应为 8 的倍数。
        """
        for name, value in SPACING.items():
            if name != "xs":
                assert value % 8 == 0, \
                    f"Spacing '{name}'={value} should be a multiple of 8 (except xs)"
    
    def test_no_duplicate_spacing_values(self):
        """间距值不重复"""
        values = list(SPACING.values())
        assert len(values) == len(set(values)), \
            "SPACING contains duplicate values"
    
    def test_no_duplicate_radius_values(self):
        """圆角值不重复"""
        values = list(RADIUS.values())
        assert len(values) == len(set(values)), \
            "RADIUS contains duplicate values"
    
    def test_no_duplicate_font_values(self):
        """字体大小值不重复"""
        values = list(FONT.values())
        assert len(values) == len(set(values)), \
            "FONT contains duplicate values"
    
    def test_animation_values_are_reasonable(self):
        """动画时长在合理范围内 (0-1000ms)"""
        for name, value in ANIMATION.items():
            assert 0 < value <= 1000, \
                f"Animation '{name}'={value}ms is outside reasonable range (0-1000ms)"
    
    def test_primary_color_contrast_with_text(self):
        """主色与文字色不同（确保可区分）"""
        assert COLORS["primary"] != COLORS["text"], \
            "Primary color should differ from text color"
        assert COLORS_DARK["primary"] != COLORS_DARK["text"], \
            "Dark theme primary color should differ from text color"
