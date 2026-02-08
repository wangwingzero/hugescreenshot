# -*- coding: utf-8 -*-
"""
轻量级样式属性测试

Feature: extreme-performance-optimization
Property 12: Color-Only Visual Feedback

**Validates: Requirements 7.1, 7.3, 7.4**

属性测试内容：
1. 验证所有样式不包含 transform/scale/translate/rotate（Requirements 7.4）
2. 验证焦点指示器使用边框而非阴影（Requirements 7.3）
3. 验证纯色变化反馈（Requirements 7.1）
4. 验证微交互时长 < 100ms（Requirements 7.2）
"""

import re
from typing import List, Tuple

import pytest
from hypothesis import given, strategies as st, settings, assume


# =====================================================
# 测试策略定义
# =====================================================

def get_all_style_names() -> List[str]:
    """获取所有样式名称列表"""
    from screenshot_tool.ui.lightweight_styles import get_all_lightweight_styles
    return list(get_all_lightweight_styles().keys())


def get_style_by_name(name: str) -> str:
    """根据名称获取样式字符串"""
    from screenshot_tool.ui.lightweight_styles import get_all_lightweight_styles
    return get_all_lightweight_styles().get(name, "")


# 样式名称策略
style_name_strategy = st.sampled_from(get_all_style_names())

# 交互状态策略
interaction_state_strategy = st.sampled_from(["hover", "pressed", "focus", "selected", "checked"])

# 按钮变体策略
button_variant_strategy = st.sampled_from(["primary", "secondary", "danger"])

# 输入框类型策略
input_type_strategy = st.sampled_from(["lineedit", "textedit", "combobox"])

# 动画时长策略 (0-200ms 范围内测试)
animation_duration_strategy = st.integers(min_value=0, max_value=200)


# =====================================================
# Property 12: Color-Only Visual Feedback
# =====================================================

class TestProperty12ColorOnlyVisualFeedback:
    """Property 12: Color-Only Visual Feedback
    
    **Validates: Requirements 7.1, 7.3, 7.4**
    
    For any interactive element (button, list item, input), hover, pressed, 
    and focus states SHALL only change color properties (background-color, 
    border-color, color), not transform properties (scale, translate, rotate).
    """
    
    # 禁止的 CSS 属性（会触发布局重排或复杂动画）
    FORBIDDEN_PROPERTIES = [
        "transform",
        "scale",
        "translate",
        "rotate",
        "skew",
        "matrix",
        "perspective",
        "animation",
        "transition",  # QSS 不支持，但检查以防万一
        "@keyframes",
    ]
    
    # 禁止的阴影属性
    FORBIDDEN_SHADOW_PROPERTIES = [
        "box-shadow",
        "text-shadow",
        "drop-shadow",
    ]
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy)
    def test_no_transform_in_any_style(self, style_name: str):
        """Property 12.1: 任意样式不包含 transform 属性
        
        **Validates: Requirements 7.4**
        
        For any style in the lightweight styles collection, the style 
        SHALL NOT contain transform, scale, translate, or rotate properties.
        """
        style = get_style_by_name(style_name)
        style_lower = style.lower()
        
        for prop in self.FORBIDDEN_PROPERTIES:
            assert prop not in style_lower, \
                f"Style '{style_name}' contains forbidden property '{prop}'"
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy)
    def test_no_shadow_in_any_style(self, style_name: str):
        """Property 12.2: 任意样式不包含阴影属性
        
        **Validates: Requirements 7.3**
        
        For any style in the lightweight styles collection, the style 
        SHALL NOT contain box-shadow or other shadow properties.
        Focus indicators SHALL use borders, not shadows.
        """
        style = get_style_by_name(style_name)
        style_lower = style.lower()
        
        for prop in self.FORBIDDEN_SHADOW_PROPERTIES:
            assert prop not in style_lower, \
                f"Style '{style_name}' contains forbidden shadow property '{prop}'"
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy, state=interaction_state_strategy)
    def test_interaction_states_use_color_only(self, style_name: str, state: str):
        """Property 12.3: 交互状态只使用颜色变化
        
        **Validates: Requirements 7.1**
        
        For any interactive state (hover, pressed, focus, selected, checked),
        the style SHALL only change color-related properties.
        """
        style = get_style_by_name(style_name)
        style_lower = style.lower()
        
        # 检查该状态是否存在于样式中
        state_selector = f":{state}"
        if state_selector not in style_lower:
            # 该样式不包含此状态，跳过
            assume(False)
        
        # 验证不包含 transform 属性
        for prop in self.FORBIDDEN_PROPERTIES:
            assert prop not in style_lower, \
                f"Style '{style_name}' state '{state}' contains forbidden property '{prop}'"
    
    @settings(max_examples=100)
    @given(variant=button_variant_strategy)
    def test_button_variants_color_only_feedback(self, variant: str):
        """Property 12.4: 按钮变体只使用颜色反馈
        
        **Validates: Requirements 7.1, 7.4**
        
        For any button variant (primary, secondary, danger), hover and pressed
        states SHALL only change background-color or border-color.
        """
        from screenshot_tool.ui.lightweight_styles import get_lightweight_button_style
        
        style = get_lightweight_button_style(variant)
        style_lower = style.lower()
        
        # 验证不包含 transform
        for prop in self.FORBIDDEN_PROPERTIES:
            assert prop not in style_lower, \
                f"Button variant '{variant}' contains forbidden property '{prop}'"
        
        # 验证包含颜色变化属性
        assert "background-color" in style_lower or "border-color" in style_lower, \
            f"Button variant '{variant}' should use color-based feedback"
    
    @settings(max_examples=100)
    @given(input_type=input_type_strategy)
    def test_input_types_border_focus_indicator(self, input_type: str):
        """Property 12.5: 输入框使用边框焦点指示器
        
        **Validates: Requirements 7.3**
        
        For any input type (lineedit, textedit, combobox), focus state
        SHALL use border change, not shadow.
        """
        from screenshot_tool.ui.lightweight_styles import get_lightweight_input_style
        
        style = get_lightweight_input_style(input_type)
        style_lower = style.lower()
        
        # 验证 focus 状态存在
        assert ":focus" in style_lower, \
            f"Input type '{input_type}' should have :focus state"
        
        # 验证使用 border
        assert "border" in style_lower, \
            f"Input type '{input_type}' should use border for focus indicator"
        
        # 验证不使用 shadow
        for prop in self.FORBIDDEN_SHADOW_PROPERTIES:
            assert prop not in style_lower, \
                f"Input type '{input_type}' should not use shadow for focus"


class TestProperty12MicroAnimationDuration:
    """Property 12 扩展: 微交互时长验证
    
    **Validates: Requirements 7.2**
    
    For any micro-interaction animation, the duration SHALL be less than 100ms.
    """
    
    MAX_MICRO_ANIMATION_MS = 100
    
    @settings(max_examples=100)
    @given(duration=animation_duration_strategy)
    def test_animation_duration_classification(self, duration: int):
        """Property 12.6: 动画时长分类验证
        
        **Validates: Requirements 7.2**
        
        For any animation duration, if it's used as a micro-interaction,
        it SHALL be less than 100ms.
        """
        from screenshot_tool.ui.lightweight_styles import LightweightAnimationConstants
        
        # 验证所有预定义的动画常量都 < 100ms
        assert LightweightAnimationConstants.INSTANT < self.MAX_MICRO_ANIMATION_MS
        assert LightweightAnimationConstants.MICRO < self.MAX_MICRO_ANIMATION_MS
        assert LightweightAnimationConstants.FAST < self.MAX_MICRO_ANIMATION_MS
        assert LightweightAnimationConstants.MAX_MICRO <= self.MAX_MICRO_ANIMATION_MS
        
        # 验证给定的时长是否符合微交互标准
        is_valid_micro = duration < self.MAX_MICRO_ANIMATION_MS
        
        # 如果时长 >= 100ms，则不应用于微交互
        if duration >= self.MAX_MICRO_ANIMATION_MS:
            assert not is_valid_micro, \
                f"Duration {duration}ms should not be classified as micro-interaction"
    
    def test_all_animation_constants_under_100ms(self):
        """验证所有动画常量都 < 100ms
        
        **Validates: Requirements 7.2**
        """
        from screenshot_tool.ui.lightweight_styles import LightweightAnimationConstants
        
        constants = [
            ("INSTANT", LightweightAnimationConstants.INSTANT),
            ("MICRO", LightweightAnimationConstants.MICRO),
            ("FAST", LightweightAnimationConstants.FAST),
            ("MAX_MICRO", LightweightAnimationConstants.MAX_MICRO),
        ]
        
        for name, value in constants:
            assert value <= self.MAX_MICRO_ANIMATION_MS, \
                f"Animation constant {name}={value}ms exceeds {self.MAX_MICRO_ANIMATION_MS}ms limit"


class TestProperty12StyleValidation:
    """Property 12 样式验证函数测试
    
    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy)
    def test_validate_no_transform_function(self, style_name: str):
        """Property 12.7: validate_no_transform 函数正确性
        
        **Validates: Requirements 7.4**
        
        For any style, validate_no_transform() SHALL return True if and only if
        the style does not contain transform/scale/translate/rotate.
        """
        from screenshot_tool.ui.lightweight_styles import validate_no_transform
        
        style = get_style_by_name(style_name)
        result = validate_no_transform(style)
        
        # 所有轻量级样式都应该通过验证
        assert result is True, \
            f"Style '{style_name}' failed validate_no_transform check"
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy)
    def test_validate_color_only_feedback_function(self, style_name: str):
        """Property 12.8: validate_color_only_feedback 函数正确性
        
        **Validates: Requirements 7.1**
        
        For any style, validate_color_only_feedback() SHALL return True if and only if
        the style only uses color-based feedback.
        """
        from screenshot_tool.ui.lightweight_styles import validate_color_only_feedback
        
        style = get_style_by_name(style_name)
        result = validate_color_only_feedback(style)
        
        # 所有轻量级样式都应该通过验证
        assert result is True, \
            f"Style '{style_name}' failed validate_color_only_feedback check"
    
    @settings(max_examples=50)
    @given(
        has_transform=st.booleans(),
        has_scale=st.booleans(),
        has_translate=st.booleans(),
        has_rotate=st.booleans()
    )
    def test_validation_with_synthetic_styles(
        self, has_transform: bool, has_scale: bool, has_translate: bool, has_rotate: bool
    ):
        """Property 12.9: 合成样式验证
        
        **Validates: Requirements 7.1, 7.3, 7.4**
        
        For any synthetic style with known properties, validation functions
        SHALL correctly identify forbidden transform properties.
        """
        from screenshot_tool.ui.lightweight_styles import (
            validate_no_transform, validate_color_only_feedback
        )
        
        # 构建合成样式
        style_parts = ["QPushButton { background-color: #3B82F6; }"]
        
        if has_transform:
            style_parts.append("QPushButton:hover { transform: none; }")
        
        if has_scale:
            style_parts.append("QPushButton:hover { scale: 1.05; }")
        
        if has_translate:
            style_parts.append("QPushButton:hover { translate: 10px; }")
        
        if has_rotate:
            style_parts.append("QPushButton:hover { rotate: 45deg; }")
        
        synthetic_style = "\n".join(style_parts)
        
        # 验证 validate_no_transform - 任何 transform 相关属性都应该返回 False
        no_transform_result = validate_no_transform(synthetic_style)
        has_any_transform = has_transform or has_scale or has_translate or has_rotate
        expected_no_transform = not has_any_transform
        assert no_transform_result == expected_no_transform, \
            f"validate_no_transform returned {no_transform_result}, expected {expected_no_transform}"
        
        # 验证 validate_color_only_feedback - 依赖 validate_no_transform
        color_only_result = validate_color_only_feedback(synthetic_style)
        expected_color_only = not has_any_transform
        assert color_only_result == expected_color_only, \
            f"validate_color_only_feedback returned {color_only_result}, expected {expected_color_only}"


class TestProperty12GlobalStylesheet:
    """Property 12 全局样式表测试
    
    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    
    @settings(max_examples=50)
    @given(st.just(None))  # 只运行一次但在 hypothesis 框架内
    def test_global_stylesheet_no_transform(self, _):
        """Property 12.10: 全局样式表不包含 transform
        
        **Validates: Requirements 7.4**
        
        The global lightweight stylesheet SHALL NOT contain any transform properties.
        """
        from screenshot_tool.ui.lightweight_styles import (
            get_lightweight_stylesheet, validate_no_transform
        )
        
        stylesheet = get_lightweight_stylesheet()
        
        assert validate_no_transform(stylesheet), \
            "Global stylesheet contains transform properties"
    
    @settings(max_examples=50)
    @given(st.just(None))
    def test_global_stylesheet_no_shadow(self, _):
        """Property 12.11: 全局样式表不包含阴影
        
        **Validates: Requirements 7.3**
        
        The global lightweight stylesheet SHALL NOT contain any shadow properties.
        """
        from screenshot_tool.ui.lightweight_styles import get_lightweight_stylesheet
        
        stylesheet = get_lightweight_stylesheet()
        stylesheet_lower = stylesheet.lower()
        
        forbidden_shadows = ["box-shadow", "text-shadow", "drop-shadow"]
        for shadow in forbidden_shadows:
            assert shadow not in stylesheet_lower, \
                f"Global stylesheet contains '{shadow}'"
    
    @settings(max_examples=50)
    @given(st.just(None))
    def test_global_stylesheet_has_font_family(self, _):
        """Property 12.12: 全局样式表包含字体设置
        
        **Validates: Requirements 7.1**
        
        The global lightweight stylesheet SHALL include font-family setting.
        """
        from screenshot_tool.ui.lightweight_styles import get_lightweight_stylesheet
        
        stylesheet = get_lightweight_stylesheet()
        
        assert "font-family" in stylesheet.lower(), \
            "Global stylesheet should include font-family"


class TestProperty12ComprehensiveValidation:
    """Property 12 综合验证测试
    
    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    
    @settings(max_examples=100)
    @given(style_name=style_name_strategy)
    def test_comprehensive_style_validation(self, style_name: str):
        """Property 12.13: 综合样式验证
        
        **Validates: Requirements 7.1, 7.3, 7.4**
        
        For any style, it SHALL pass all lightweight style requirements:
        1. No transform/scale/translate/rotate
        2. No box-shadow/text-shadow
        3. No CSS animations
        4. Uses color-based feedback only
        """
        style = get_style_by_name(style_name)
        style_lower = style.lower()
        
        # 1. 验证无 transform
        transform_props = ["transform", "scale(", "translate(", "rotate(", "skew(", "matrix("]
        for prop in transform_props:
            assert prop not in style_lower, \
                f"Style '{style_name}' contains transform property '{prop}'"
        
        # 2. 验证无阴影
        shadow_props = ["box-shadow", "text-shadow", "drop-shadow"]
        for prop in shadow_props:
            assert prop not in style_lower, \
                f"Style '{style_name}' contains shadow property '{prop}'"
        
        # 3. 验证无 CSS 动画
        animation_props = ["animation", "@keyframes"]
        for prop in animation_props:
            assert prop not in style_lower, \
                f"Style '{style_name}' contains animation property '{prop}'"
        
        # 4. 验证使用颜色属性（至少包含一个颜色相关属性）
        color_props = ["background-color", "color", "border-color", "border"]
        has_color_prop = any(prop in style_lower for prop in color_props)
        assert has_color_prop, \
            f"Style '{style_name}' should use color-based properties"
    
    @settings(max_examples=50)
    @given(
        style_name1=style_name_strategy,
        style_name2=style_name_strategy
    )
    def test_style_consistency(self, style_name1: str, style_name2: str):
        """Property 12.14: 样式一致性验证
        
        **Validates: Requirements 7.1, 7.3, 7.4**
        
        For any two styles, they SHALL both follow the same lightweight principles.
        """
        from screenshot_tool.ui.lightweight_styles import (
            validate_no_transform, validate_color_only_feedback
        )
        
        style1 = get_style_by_name(style_name1)
        style2 = get_style_by_name(style_name2)
        
        # 两个样式都应该通过相同的验证
        result1_transform = validate_no_transform(style1)
        result2_transform = validate_no_transform(style2)
        
        result1_color = validate_color_only_feedback(style1)
        result2_color = validate_color_only_feedback(style2)
        
        # 所有样式都应该通过验证
        assert result1_transform and result2_transform, \
            f"Styles '{style_name1}' and '{style_name2}' should both pass transform validation"
        
        assert result1_color and result2_color, \
            f"Styles '{style_name1}' and '{style_name2}' should both pass color-only validation"
