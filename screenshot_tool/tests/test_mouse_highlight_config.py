# =====================================================
# =============== 鼠标高亮配置测试 ===============
# =====================================================

"""
鼠标高亮配置测试 - 测试 MouseHighlightConfig 的配置验证和持久化

Feature: mouse-highlight
Requirements: 8.1, 8.3, 9.6
Property 3: State Persistence Round-Trip
Property 9: Effect Configuration Application
Property 10: Theme Color Application
"""

import json
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import (
    MouseHighlightConfig,
    MOUSE_HIGHLIGHT_THEMES,
    AppConfig,
    ConfigManager,
)


class TestMouseHighlightConfigDefaults:
    """测试 MouseHighlightConfig 默认值
    
    Validates: Requirements 8.1
    """
    
    def test_default_enabled_is_false(self):
        """测试 enabled 默认值为 False"""
        config = MouseHighlightConfig()
        assert config.enabled is False
    
    def test_default_hotkey_is_alt_m(self):
        """测试 hotkey 默认值为 alt+m"""
        config = MouseHighlightConfig()
        assert config.hotkey == "alt+m"
    
    def test_default_restore_on_startup_is_true(self):
        """测试 restore_on_startup 默认值为 True"""
        config = MouseHighlightConfig()
        assert config.restore_on_startup is True
    
    def test_default_circle_enabled_is_true(self):
        """测试 circle_enabled 默认值为 True"""
        config = MouseHighlightConfig()
        assert config.circle_enabled is True
    
    def test_default_spotlight_enabled_is_false(self):
        """测试 spotlight_enabled 默认值为 False"""
        config = MouseHighlightConfig()
        assert config.spotlight_enabled is False
    
    def test_default_cursor_magnify_enabled_is_false(self):
        """测试 cursor_magnify_enabled 默认值为 False"""
        config = MouseHighlightConfig()
        assert config.cursor_magnify_enabled is False
    
    def test_default_click_effect_enabled_is_true(self):
        """测试 click_effect_enabled 默认值为 True"""
        config = MouseHighlightConfig()
        assert config.click_effect_enabled is True
    
    def test_default_theme_is_classic_yellow(self):
        """测试 theme 默认值为 classic_yellow"""
        config = MouseHighlightConfig()
        assert config.theme == "classic_yellow"
    
    def test_default_circle_radius_is_40(self):
        """测试 circle_radius 默认值为 40"""
        config = MouseHighlightConfig()
        assert config.circle_radius == 40
    
    def test_default_circle_thickness_is_3(self):
        """测试 circle_thickness 默认值为 3"""
        config = MouseHighlightConfig()
        assert config.circle_thickness == 3
    
    def test_default_spotlight_radius_is_150(self):
        """测试 spotlight_radius 默认值为 150"""
        config = MouseHighlightConfig()
        assert config.spotlight_radius == 150
    
    def test_default_spotlight_darkness_is_60(self):
        """测试 spotlight_darkness 默认值为 60"""
        config = MouseHighlightConfig()
        assert config.spotlight_darkness == 60
    
    def test_default_cursor_scale_is_2(self):
        """测试 cursor_scale 默认值为 2.0"""
        config = MouseHighlightConfig()
        assert config.cursor_scale == 2.0
    
    def test_default_ripple_duration_is_500(self):
        """测试 ripple_duration 默认值为 500"""
        config = MouseHighlightConfig()
        assert config.ripple_duration == 500


class TestMouseHighlightConfigParameterValidation:
    """测试参数范围验证
    
    Property 9: Effect Configuration Application
    Validates: Requirements 4.2, 4.3, 5.3, 5.4, 6.2
    """
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_circle_radius_clamped_to_valid_range(self, value: int):
        """Property 9: 任意 circle_radius 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(circle_radius=value)
        assert MouseHighlightConfig.MIN_CIRCLE_RADIUS <= config.circle_radius <= MouseHighlightConfig.MAX_CIRCLE_RADIUS
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_circle_thickness_clamped_to_valid_range(self, value: int):
        """Property 9: 任意 circle_thickness 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(circle_thickness=value)
        assert MouseHighlightConfig.MIN_CIRCLE_THICKNESS <= config.circle_thickness <= MouseHighlightConfig.MAX_CIRCLE_THICKNESS
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_spotlight_radius_clamped_to_valid_range(self, value: int):
        """Property 9: 任意 spotlight_radius 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(spotlight_radius=value)
        assert MouseHighlightConfig.MIN_SPOTLIGHT_RADIUS <= config.spotlight_radius <= MouseHighlightConfig.MAX_SPOTLIGHT_RADIUS
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_spotlight_darkness_clamped_to_valid_range(self, value: int):
        """Property 9: 任意 spotlight_darkness 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(spotlight_darkness=value)
        assert MouseHighlightConfig.MIN_SPOTLIGHT_DARKNESS <= config.spotlight_darkness <= MouseHighlightConfig.MAX_SPOTLIGHT_DARKNESS
    
    @given(st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_cursor_scale_clamped_to_valid_range(self, value: float):
        """Property 9: 任意 cursor_scale 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(cursor_scale=value)
        assert MouseHighlightConfig.MIN_CURSOR_SCALE <= config.cursor_scale <= MouseHighlightConfig.MAX_CURSOR_SCALE
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_ripple_duration_clamped_to_valid_range(self, value: int):
        """Property 9: 任意 ripple_duration 值都应被限制在有效范围内"""
        config = MouseHighlightConfig(ripple_duration=value)
        assert MouseHighlightConfig.MIN_RIPPLE_DURATION <= config.ripple_duration <= MouseHighlightConfig.MAX_RIPPLE_DURATION
    
    def test_none_values_use_defaults(self):
        """测试 None 值使用默认值"""
        config = MouseHighlightConfig(
            circle_radius=None,
            circle_thickness=None,
            spotlight_radius=None,
            spotlight_darkness=None,
            cursor_scale=None,
            ripple_duration=None,
        )
        assert config.circle_radius == 40
        assert config.circle_thickness == 3
        assert config.spotlight_radius == 150
        assert config.spotlight_darkness == 60
        assert config.cursor_scale == 2.0
        assert config.ripple_duration == 500


class TestMouseHighlightConfigThemeValidation:
    """测试主题验证
    
    Property 10: Theme Color Application
    Validates: Requirements 4.4, 8.2, 8.3, 8.4
    """
    
    def test_valid_themes_accepted(self):
        """测试有效主题被接受"""
        for theme in MouseHighlightConfig.VALID_THEMES:
            config = MouseHighlightConfig(theme=theme)
            assert config.theme == theme
    
    def test_invalid_theme_uses_default(self):
        """测试无效主题使用默认值"""
        config = MouseHighlightConfig(theme="invalid_theme")
        assert config.theme == "classic_yellow"
    
    def test_none_theme_uses_default(self):
        """测试 None 主题使用默认值"""
        config = MouseHighlightConfig(theme=None)
        assert config.theme == "classic_yellow"
    
    def test_get_theme_colors_returns_correct_colors(self):
        """测试 get_theme_colors 返回正确的颜色"""
        for theme_name, expected_colors in MOUSE_HIGHLIGHT_THEMES.items():
            config = MouseHighlightConfig(theme=theme_name)
            colors = config.get_theme_colors()
            assert colors == expected_colors
    
    def test_all_themes_have_required_keys(self):
        """测试所有主题都包含必需的颜色键"""
        required_keys = {"name", "circle_color", "left_click_color", "right_click_color"}
        for theme_name, theme_colors in MOUSE_HIGHLIGHT_THEMES.items():
            assert required_keys.issubset(theme_colors.keys()), f"Theme {theme_name} missing keys"
    
    @given(st.sampled_from(list(MOUSE_HIGHLIGHT_THEMES.keys())))
    @settings(max_examples=10)
    def test_theme_colors_are_valid_hex(self, theme_name: str):
        """Property 10: 所有主题颜色都应是有效的十六进制颜色"""
        theme = MOUSE_HIGHLIGHT_THEMES[theme_name]
        for key in ["circle_color", "left_click_color", "right_click_color"]:
            color = theme[key]
            assert color.startswith("#"), f"{key} should start with #"
            assert len(color) == 7, f"{key} should be 7 characters"
            # 验证是有效的十六进制
            int(color[1:], 16)


class TestMouseHighlightConfigHotkeyValidation:
    """测试快捷键验证"""
    
    def test_valid_hotkey_accepted(self):
        """测试有效快捷键被接受"""
        config = MouseHighlightConfig(hotkey="ctrl+alt+h")
        assert config.hotkey == "ctrl+alt+h"
    
    def test_invalid_modifier_uses_default(self):
        """测试无效修饰键使用默认值"""
        config = MouseHighlightConfig(hotkey="invalid+m")
        assert config.hotkey == "alt+m"
    
    def test_invalid_key_uses_default(self):
        """测试无效主键使用默认值"""
        config = MouseHighlightConfig(hotkey="alt+!")
        assert config.hotkey == "alt+m"
    
    def test_none_hotkey_uses_default(self):
        """测试 None 快捷键使用默认值"""
        config = MouseHighlightConfig(hotkey=None)
        assert config.hotkey == "alt+m"
    
    def test_get_hotkey_parts(self):
        """测试 get_hotkey_parts 方法"""
        config = MouseHighlightConfig(hotkey="ctrl+alt+h")
        modifier, key = config.get_hotkey_parts()
        assert modifier == "ctrl+alt"
        assert key == "h"
    
    def test_hotkey_normalized_to_lowercase(self):
        """测试快捷键被规范化为小写"""
        config = MouseHighlightConfig(hotkey="ALT+M")
        assert config.hotkey == "alt+m"


class TestMouseHighlightConfigRoundTrip:
    """测试配置序列化往返
    
    Property 3: State Persistence Round-Trip
    Validates: Requirements 1.5, 1.6
    """
    
    @given(
        enabled=st.booleans(),
        circle_enabled=st.booleans(),
        spotlight_enabled=st.booleans(),
        cursor_magnify_enabled=st.booleans(),
        click_effect_enabled=st.booleans(),
        theme=st.sampled_from(list(MouseHighlightConfig.VALID_THEMES)),
        circle_radius=st.integers(min_value=10, max_value=100),
        circle_thickness=st.integers(min_value=1, max_value=10),
        spotlight_radius=st.integers(min_value=50, max_value=500),
        spotlight_darkness=st.integers(min_value=0, max_value=100),
        cursor_scale=st.floats(min_value=1.0, max_value=5.0),
        ripple_duration=st.integers(min_value=100, max_value=2000),
    )
    @settings(max_examples=100)
    def test_config_round_trip(
        self,
        enabled: bool,
        circle_enabled: bool,
        spotlight_enabled: bool,
        cursor_magnify_enabled: bool,
        click_effect_enabled: bool,
        theme: str,
        circle_radius: int,
        circle_thickness: int,
        spotlight_radius: int,
        spotlight_darkness: int,
        cursor_scale: float,
        ripple_duration: int,
    ):
        """Property 3: 序列化后反序列化应产生等价配置"""
        # 创建原始配置
        original = MouseHighlightConfig(
            enabled=enabled,
            circle_enabled=circle_enabled,
            spotlight_enabled=spotlight_enabled,
            cursor_magnify_enabled=cursor_magnify_enabled,
            click_effect_enabled=click_effect_enabled,
            theme=theme,
            circle_radius=circle_radius,
            circle_thickness=circle_thickness,
            spotlight_radius=spotlight_radius,
            spotlight_darkness=spotlight_darkness,
            cursor_scale=cursor_scale,
            ripple_duration=ripple_duration,
        )
        
        # 序列化为字典
        data = {
            "enabled": original.enabled,
            "hotkey": original.hotkey,
            "restore_on_startup": original.restore_on_startup,
            "circle_enabled": original.circle_enabled,
            "spotlight_enabled": original.spotlight_enabled,
            "cursor_magnify_enabled": original.cursor_magnify_enabled,
            "click_effect_enabled": original.click_effect_enabled,
            "theme": original.theme,
            "circle_radius": original.circle_radius,
            "circle_thickness": original.circle_thickness,
            "spotlight_radius": original.spotlight_radius,
            "spotlight_darkness": original.spotlight_darkness,
            "cursor_scale": original.cursor_scale,
            "ripple_duration": original.ripple_duration,
        }
        
        # 序列化为 JSON 再反序列化
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        # 从字典创建新配置
        restored = MouseHighlightConfig(**loaded_data)
        
        # 验证等价性
        assert restored.enabled == original.enabled
        assert restored.circle_enabled == original.circle_enabled
        assert restored.spotlight_enabled == original.spotlight_enabled
        assert restored.cursor_magnify_enabled == original.cursor_magnify_enabled
        assert restored.click_effect_enabled == original.click_effect_enabled
        assert restored.theme == original.theme
        assert restored.circle_radius == original.circle_radius
        assert restored.circle_thickness == original.circle_thickness
        assert restored.spotlight_radius == original.spotlight_radius
        assert restored.spotlight_darkness == original.spotlight_darkness
        assert abs(restored.cursor_scale - original.cursor_scale) < 0.01
        assert restored.ripple_duration == original.ripple_duration


class TestAppConfigMouseHighlightIntegration:
    """测试 AppConfig 中 mouse_highlight 的集成"""
    
    def test_app_config_has_mouse_highlight(self):
        """测试 AppConfig 包含 mouse_highlight 字段"""
        config = AppConfig()
        assert hasattr(config, "mouse_highlight")
        assert isinstance(config.mouse_highlight, MouseHighlightConfig)
    
    def test_app_config_to_dict_includes_mouse_highlight(self):
        """测试 to_dict 包含 mouse_highlight"""
        config = AppConfig()
        data = config.to_dict()
        assert "mouse_highlight" in data
        assert "enabled" in data["mouse_highlight"]
        assert "theme" in data["mouse_highlight"]
    
    def test_app_config_from_dict_loads_mouse_highlight(self):
        """测试 from_dict 正确加载 mouse_highlight"""
        data = {
            "mouse_highlight": {
                "enabled": True,
                "theme": "business_blue",
                "circle_radius": 50,
            }
        }
        config = AppConfig.from_dict(data)
        assert config.mouse_highlight.enabled is True
        assert config.mouse_highlight.theme == "business_blue"
        assert config.mouse_highlight.circle_radius == 50
    
    def test_app_config_from_dict_uses_defaults_for_missing(self):
        """测试 from_dict 对缺失字段使用默认值"""
        data = {}
        config = AppConfig.from_dict(data)
        assert config.mouse_highlight.enabled is False
        assert config.mouse_highlight.theme == "classic_yellow"
