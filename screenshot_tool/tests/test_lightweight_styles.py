# -*- coding: utf-8 -*-
"""
轻量级样式单元测试

Feature: extreme-performance-optimization
Requirements: 7.1, 7.2, 7.3, 7.4

测试内容：
1. 验证样式不包含 transform/scale（Requirements 7.4）
2. 验证纯色变化反馈（Requirements 7.1）
3. 验证边框焦点指示器（Requirements 7.3）
4. 验证微交互常量 < 100ms（Requirements 7.2）
"""

import pytest


class TestLightweightAnimationConstants:
    """测试轻量级动画常量"""
    
    def test_all_animation_durations_under_100ms(self):
        """验证所有动画时长 < 100ms
        
        **Validates: Requirements 7.2**
        """
        from screenshot_tool.ui.lightweight_styles import LightweightAnimationConstants
        
        assert LightweightAnimationConstants.INSTANT < 100
        assert LightweightAnimationConstants.MICRO < 100
        assert LightweightAnimationConstants.FAST < 100
        assert LightweightAnimationConstants.MAX_MICRO <= 100
    
    def test_instant_is_zero(self):
        """验证即时反馈为 0ms"""
        from screenshot_tool.ui.lightweight_styles import LightweightAnimationConstants
        
        assert LightweightAnimationConstants.INSTANT == 0


class TestNoTransformStyles:
    """测试样式不包含 transform 属性
    
    **Validates: Requirements 7.4**
    """
    
    def test_button_primary_no_transform(self):
        """验证主按钮样式不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_BUTTON_PRIMARY, validate_no_transform
        )
        
        assert validate_no_transform(LIGHTWEIGHT_BUTTON_PRIMARY)
        assert "transform" not in LIGHTWEIGHT_BUTTON_PRIMARY.lower()
        assert "scale" not in LIGHTWEIGHT_BUTTON_PRIMARY.lower()

    
    def test_button_secondary_no_transform(self):
        """验证次要按钮样式不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_BUTTON_SECONDARY, validate_no_transform
        )
        
        assert validate_no_transform(LIGHTWEIGHT_BUTTON_SECONDARY)
        assert "transform" not in LIGHTWEIGHT_BUTTON_SECONDARY.lower()
        assert "scale" not in LIGHTWEIGHT_BUTTON_SECONDARY.lower()
    
    def test_button_danger_no_transform(self):
        """验证危险按钮样式不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_BUTTON_DANGER, validate_no_transform
        )
        
        assert validate_no_transform(LIGHTWEIGHT_BUTTON_DANGER)
        assert "transform" not in LIGHTWEIGHT_BUTTON_DANGER.lower()
        assert "scale" not in LIGHTWEIGHT_BUTTON_DANGER.lower()
    
    def test_list_no_transform(self):
        """验证列表样式不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_LIST, validate_no_transform
        )
        
        assert validate_no_transform(LIGHTWEIGHT_LIST)
        assert "transform" not in LIGHTWEIGHT_LIST.lower()
        assert "scale" not in LIGHTWEIGHT_LIST.lower()
    
    def test_input_no_transform(self):
        """验证输入框样式不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_INPUT, validate_no_transform
        )
        
        assert validate_no_transform(LIGHTWEIGHT_INPUT)
        assert "transform" not in LIGHTWEIGHT_INPUT.lower()
        assert "scale" not in LIGHTWEIGHT_INPUT.lower()
    
    def test_all_styles_no_transform(self):
        """验证所有样式都不包含 transform"""
        from screenshot_tool.ui.lightweight_styles import (
            get_all_lightweight_styles, validate_no_transform
        )
        
        all_styles = get_all_lightweight_styles()
        for name, style in all_styles.items():
            assert validate_no_transform(style), f"Style '{name}' contains transform"
            assert "transform" not in style.lower(), f"Style '{name}' contains 'transform'"
            assert "scale(" not in style.lower(), f"Style '{name}' contains 'scale('"
            assert "translate(" not in style.lower(), f"Style '{name}' contains 'translate('"
            assert "rotate(" not in style.lower(), f"Style '{name}' contains 'rotate('"



class TestColorOnlyFeedback:
    """测试纯色变化反馈
    
    **Validates: Requirements 7.1**
    """
    
    def test_button_hover_uses_color_change(self):
        """验证按钮悬停使用颜色变化"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_BUTTON_PRIMARY
        
        # 验证 hover 状态存在
        assert ":hover" in LIGHTWEIGHT_BUTTON_PRIMARY
        # 验证使用 background-color 变化
        assert "background-color" in LIGHTWEIGHT_BUTTON_PRIMARY
    
    def test_button_pressed_uses_color_change(self):
        """验证按钮按下使用颜色变化"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_BUTTON_PRIMARY
        
        # 验证 pressed 状态存在
        assert ":pressed" in LIGHTWEIGHT_BUTTON_PRIMARY
    
    def test_input_hover_uses_border_color_change(self):
        """验证输入框悬停使用边框颜色变化"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_INPUT
        
        # 验证 hover 状态存在
        assert ":hover" in LIGHTWEIGHT_INPUT
        # 验证使用 border-color 变化
        assert "border-color" in LIGHTWEIGHT_INPUT
    
    def test_list_item_hover_uses_background_color(self):
        """验证列表项悬停使用背景色变化"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_LIST
        
        # 验证 hover 状态存在
        assert ":hover" in LIGHTWEIGHT_LIST
        # 验证使用 background-color 变化
        assert "background-color" in LIGHTWEIGHT_LIST
    
    def test_validate_color_only_feedback_function(self):
        """测试 validate_color_only_feedback 函数"""
        from screenshot_tool.ui.lightweight_styles import validate_color_only_feedback
        
        # 合规样式
        valid_style = """
        QPushButton:hover {
            background-color: #1D4ED8;
        }
        """
        assert validate_color_only_feedback(valid_style)
        
        # 不合规样式（包含 transform）
        invalid_style = """
        QPushButton:hover {
            transform: scale(1.05);
        }
        """
        assert not validate_color_only_feedback(invalid_style)



class TestBorderFocusIndicator:
    """测试边框焦点指示器
    
    **Validates: Requirements 7.3**
    """
    
    def test_button_focus_uses_border(self):
        """验证按钮焦点使用边框指示"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_BUTTON_PRIMARY
        
        # 验证 focus 状态存在
        assert ":focus" in LIGHTWEIGHT_BUTTON_PRIMARY
        # 验证使用 border 而非 shadow
        assert "border:" in LIGHTWEIGHT_BUTTON_PRIMARY or "border-color" in LIGHTWEIGHT_BUTTON_PRIMARY
        # 验证不使用 box-shadow
        assert "box-shadow" not in LIGHTWEIGHT_BUTTON_PRIMARY.lower()
    
    def test_input_focus_uses_border(self):
        """验证输入框焦点使用边框指示"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_INPUT
        
        # 验证 focus 状态存在
        assert ":focus" in LIGHTWEIGHT_INPUT
        # 验证使用 border
        assert "border:" in LIGHTWEIGHT_INPUT
        # 验证不使用 box-shadow
        assert "box-shadow" not in LIGHTWEIGHT_INPUT.lower()
    
    def test_checkbox_focus_uses_border(self):
        """验证复选框焦点使用边框指示"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_CHECKBOX
        
        # 验证 focus 状态存在
        assert ":focus" in LIGHTWEIGHT_CHECKBOX
        # 验证使用 border
        assert "border:" in LIGHTWEIGHT_CHECKBOX
    
    def test_combobox_focus_uses_border(self):
        """验证下拉框焦点使用边框指示"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_COMBOBOX
        
        # 验证 focus 状态存在
        assert ":focus" in LIGHTWEIGHT_COMBOBOX
        # 验证使用 border
        assert "border:" in LIGHTWEIGHT_COMBOBOX
    
    def test_toolbutton_focus_uses_border(self):
        """验证工具按钮焦点使用边框指示"""
        from screenshot_tool.ui.lightweight_styles import LIGHTWEIGHT_TOOLBUTTON
        
        # 验证 focus 状态存在
        assert ":focus" in LIGHTWEIGHT_TOOLBUTTON
        # 验证使用 border
        assert "border:" in LIGHTWEIGHT_TOOLBUTTON
    
    def test_no_shadow_in_any_style(self):
        """验证所有样式都不使用 box-shadow"""
        from screenshot_tool.ui.lightweight_styles import get_all_lightweight_styles
        
        all_styles = get_all_lightweight_styles()
        for name, style in all_styles.items():
            assert "box-shadow" not in style.lower(), f"Style '{name}' contains box-shadow"
            assert "shadow" not in style.lower() or "text-shadow" not in style.lower(), \
                f"Style '{name}' may contain shadow"



class TestStyleFunctions:
    """测试样式工具函数"""
    
    def test_get_lightweight_stylesheet_returns_string(self):
        """验证 get_lightweight_stylesheet 返回字符串"""
        from screenshot_tool.ui.lightweight_styles import get_lightweight_stylesheet
        
        stylesheet = get_lightweight_stylesheet()
        assert isinstance(stylesheet, str)
        assert len(stylesheet) > 0
    
    def test_get_lightweight_stylesheet_contains_font_family(self):
        """验证全局样式表包含字体设置"""
        from screenshot_tool.ui.lightweight_styles import get_lightweight_stylesheet
        
        stylesheet = get_lightweight_stylesheet()
        assert "font-family" in stylesheet
    
    def test_get_lightweight_button_style_variants(self):
        """验证按钮样式变体函数"""
        from screenshot_tool.ui.lightweight_styles import (
            get_lightweight_button_style,
            LIGHTWEIGHT_BUTTON_PRIMARY,
            LIGHTWEIGHT_BUTTON_SECONDARY,
            LIGHTWEIGHT_BUTTON_DANGER,
        )
        
        assert get_lightweight_button_style("primary") == LIGHTWEIGHT_BUTTON_PRIMARY
        assert get_lightweight_button_style("secondary") == LIGHTWEIGHT_BUTTON_SECONDARY
        assert get_lightweight_button_style("danger") == LIGHTWEIGHT_BUTTON_DANGER
        # 默认返回 primary
        assert get_lightweight_button_style("unknown") == LIGHTWEIGHT_BUTTON_PRIMARY
    
    def test_get_lightweight_input_style_variants(self):
        """验证输入框样式变体函数"""
        from screenshot_tool.ui.lightweight_styles import (
            get_lightweight_input_style,
            LIGHTWEIGHT_INPUT,
            LIGHTWEIGHT_TEXTEDIT,
            LIGHTWEIGHT_COMBOBOX,
        )
        
        assert get_lightweight_input_style("lineedit") == LIGHTWEIGHT_INPUT
        assert get_lightweight_input_style("textedit") == LIGHTWEIGHT_TEXTEDIT
        assert get_lightweight_input_style("combobox") == LIGHTWEIGHT_COMBOBOX
        # 默认返回 lineedit
        assert get_lightweight_input_style("unknown") == LIGHTWEIGHT_INPUT
    
    def test_get_all_lightweight_styles_returns_dict(self):
        """验证 get_all_lightweight_styles 返回字典"""
        from screenshot_tool.ui.lightweight_styles import get_all_lightweight_styles
        
        all_styles = get_all_lightweight_styles()
        assert isinstance(all_styles, dict)
        assert len(all_styles) > 0
    
    def test_get_all_lightweight_styles_contains_expected_keys(self):
        """验证 get_all_lightweight_styles 包含预期的键"""
        from screenshot_tool.ui.lightweight_styles import get_all_lightweight_styles
        
        all_styles = get_all_lightweight_styles()
        expected_keys = [
            "button_primary", "button_secondary", "button_danger",
            "list", "input", "textedit", "checkbox", "combobox",
            "toolbutton", "scrollbar", "menu", "tabwidget",
            "groupbox", "card", "dialog"
        ]
        for key in expected_keys:
            assert key in all_styles, f"Missing key: {key}"


class TestStyleConstants:
    """测试样式常量"""
    
    def test_lightweight_button_is_alias(self):
        """验证 LIGHTWEIGHT_BUTTON 是 PRIMARY 的别名"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_BUTTON, LIGHTWEIGHT_BUTTON_PRIMARY
        )
        
        assert LIGHTWEIGHT_BUTTON == LIGHTWEIGHT_BUTTON_PRIMARY
    
    def test_all_style_constants_are_strings(self):
        """验证所有样式常量都是字符串"""
        from screenshot_tool.ui.lightweight_styles import (
            LIGHTWEIGHT_BUTTON_PRIMARY,
            LIGHTWEIGHT_BUTTON_SECONDARY,
            LIGHTWEIGHT_BUTTON_DANGER,
            LIGHTWEIGHT_LIST,
            LIGHTWEIGHT_INPUT,
            LIGHTWEIGHT_TEXTEDIT,
            LIGHTWEIGHT_CHECKBOX,
            LIGHTWEIGHT_COMBOBOX,
            LIGHTWEIGHT_TOOLBUTTON,
            LIGHTWEIGHT_SCROLLBAR,
            LIGHTWEIGHT_MENU,
            LIGHTWEIGHT_TABWIDGET,
            LIGHTWEIGHT_GROUPBOX,
            LIGHTWEIGHT_CARD,
            LIGHTWEIGHT_DIALOG,
        )
        
        styles = [
            LIGHTWEIGHT_BUTTON_PRIMARY,
            LIGHTWEIGHT_BUTTON_SECONDARY,
            LIGHTWEIGHT_BUTTON_DANGER,
            LIGHTWEIGHT_LIST,
            LIGHTWEIGHT_INPUT,
            LIGHTWEIGHT_TEXTEDIT,
            LIGHTWEIGHT_CHECKBOX,
            LIGHTWEIGHT_COMBOBOX,
            LIGHTWEIGHT_TOOLBUTTON,
            LIGHTWEIGHT_SCROLLBAR,
            LIGHTWEIGHT_MENU,
            LIGHTWEIGHT_TABWIDGET,
            LIGHTWEIGHT_GROUPBOX,
            LIGHTWEIGHT_CARD,
            LIGHTWEIGHT_DIALOG,
        ]
        
        for style in styles:
            assert isinstance(style, str)
            assert len(style) > 0
