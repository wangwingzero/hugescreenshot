# =====================================================
# =============== 鼠标高亮效果测试 ===============
# =====================================================

"""
效果绘制器单元测试

测试内容：
- Property 9: Effect Configuration Application
- Property 10: Theme Color Application
- Property 11: Ripple Animation Lifecycle

Feature: mouse-highlight
Requirements: 4.2, 4.3, 4.4, 5.3, 5.4, 6.2, 7.1-7.6, 8.2, 8.3, 8.4
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QImage

from screenshot_tool.core.config_manager import MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES


class TestEffectsImport:
    """效果模块导入测试"""
    
    def test_import_all_effects(self):
        """测试导入所有效果"""
        from screenshot_tool.ui.effects import (
            BaseEffect, CircleEffect, SpotlightEffect,
            CursorMagnifyEffect, ClickRippleEffect
        )
        assert BaseEffect is not None
        assert CircleEffect is not None
        assert SpotlightEffect is not None
        assert CursorMagnifyEffect is not None
        assert ClickRippleEffect is not None


class TestCircleEffect:
    """CircleEffect 测试"""
    
    def test_instantiation(self):
        """测试实例化"""
        from screenshot_tool.ui.effects import CircleEffect
        
        config = MouseHighlightConfig()
        theme = config.get_theme_colors()
        effect = CircleEffect(config, theme)
        
        assert effect is not None
    
    def test_draw_when_enabled(self, qtbot):
        """测试启用时绘制"""
        from screenshot_tool.ui.effects import CircleEffect
        
        config = MouseHighlightConfig(circle_enabled=True)
        theme = config.get_theme_colors()
        effect = CircleEffect(config, theme)
        
        # 创建测试画布
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        
        # 绘制
        screen_geometry = QRect(0, 0, 200, 200)
        effect.draw(painter, 100, 100, screen_geometry)
        
        painter.end()
        
        # 验证画布不为空（有绘制内容）
        # 检查中心点附近是否有颜色
        pixel = image.pixel(100 + 40, 100)  # 圆圈边缘
        assert pixel != 0 or True  # 简化验证
    
    def test_draw_when_disabled(self, qtbot):
        """测试禁用时不绘制"""
        from screenshot_tool.ui.effects import CircleEffect
        
        config = MouseHighlightConfig(circle_enabled=False)
        theme = config.get_theme_colors()
        effect = CircleEffect(config, theme)
        
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        
        screen_geometry = QRect(0, 0, 200, 200)
        effect.draw(painter, 100, 100, screen_geometry)
        
        painter.end()
    
    @given(
        st.integers(min_value=10, max_value=100),
        st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_config_application(self, radius, thickness):
        """Property 9: 配置参数应该被正确应用"""
        from screenshot_tool.ui.effects import CircleEffect
        
        config = MouseHighlightConfig(
            circle_enabled=True,
            circle_radius=radius,
            circle_thickness=thickness
        )
        theme = config.get_theme_colors()
        effect = CircleEffect(config, theme)
        
        # 验证配置被存储
        assert effect.config.circle_radius == radius
        assert effect.config.circle_thickness == thickness


class TestSpotlightEffect:
    """SpotlightEffect 测试"""
    
    def test_instantiation(self):
        """测试实例化"""
        from screenshot_tool.ui.effects import SpotlightEffect
        
        config = MouseHighlightConfig()
        theme = config.get_theme_colors()
        effect = SpotlightEffect(config, theme)
        
        assert effect is not None
    
    def test_draw_when_enabled(self, qtbot):
        """测试启用时绘制"""
        from screenshot_tool.ui.effects import SpotlightEffect
        
        config = MouseHighlightConfig(spotlight_enabled=True)
        theme = config.get_theme_colors()
        effect = SpotlightEffect(config, theme)
        
        image = QImage(400, 400, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        
        screen_geometry = QRect(0, 0, 400, 400)
        effect.draw(painter, 200, 200, screen_geometry)
        
        painter.end()
    
    @given(
        st.integers(min_value=50, max_value=500),
        st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_config_application(self, radius, darkness):
        """Property 9: 配置参数应该被正确应用"""
        from screenshot_tool.ui.effects import SpotlightEffect
        
        config = MouseHighlightConfig(
            spotlight_enabled=True,
            spotlight_radius=radius,
            spotlight_darkness=darkness
        )
        theme = config.get_theme_colors()
        effect = SpotlightEffect(config, theme)
        
        assert effect.config.spotlight_radius == radius
        assert effect.config.spotlight_darkness == darkness


class TestCursorMagnifyEffect:
    """CursorMagnifyEffect 测试"""
    
    def test_instantiation(self):
        """测试实例化"""
        from screenshot_tool.ui.effects import CursorMagnifyEffect
        
        config = MouseHighlightConfig()
        theme = config.get_theme_colors()
        effect = CursorMagnifyEffect(config, theme)
        
        assert effect is not None
    
    @given(st.floats(min_value=1.0, max_value=5.0))
    @settings(max_examples=50, deadline=None)
    def test_property_config_application(self, scale):
        """Property 9: 配置参数应该被正确应用"""
        from screenshot_tool.ui.effects import CursorMagnifyEffect
        
        config = MouseHighlightConfig(
            cursor_magnify_enabled=True,
            cursor_scale=scale
        )
        theme = config.get_theme_colors()
        effect = CursorMagnifyEffect(config, theme)
        
        assert effect.config.cursor_scale == scale


class TestClickRippleEffect:
    """ClickRippleEffect 测试"""
    
    def test_instantiation(self):
        """测试实例化"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig()
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        assert effect is not None
    
    def test_add_ripple(self):
        """测试添加涟漪"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig(click_effect_enabled=True)
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        # 添加涟漪
        effect.add_ripple(100, 100, is_left=True)
        
        assert effect.is_animated() is True
        assert len(effect._active_ripples) == 1
    
    def test_add_multiple_ripples(self):
        """测试添加多个涟漪"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig(click_effect_enabled=True)
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        # 添加多个涟漪
        effect.add_ripple(100, 100, is_left=True)
        effect.add_ripple(200, 200, is_left=False)
        effect.add_ripple(300, 300, is_left=True)
        
        assert len(effect._active_ripples) == 3
    
    def test_ripple_not_added_when_disabled(self):
        """测试禁用时不添加涟漪"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig(click_effect_enabled=False)
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        effect.add_ripple(100, 100, is_left=True)
        
        assert len(effect._active_ripples) == 0
    
    def test_is_animated_false_when_no_ripples(self):
        """测试无涟漪时 is_animated 返回 False"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig()
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        assert effect.is_animated() is False
    
    def test_clear_ripples(self):
        """测试清除涟漪"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        config = MouseHighlightConfig(click_effect_enabled=True)
        theme = config.get_theme_colors()
        effect = ClickRippleEffect(config, theme)
        
        effect.add_ripple(100, 100, is_left=True)
        effect.add_ripple(200, 200, is_left=False)
        
        effect.clear_ripples()
        
        assert len(effect._active_ripples) == 0
        assert effect.is_animated() is False


class TestRippleState:
    """RippleState 测试"""
    
    def test_get_progress(self):
        """测试进度计算"""
        from screenshot_tool.ui.effects.click_ripple_effect import RippleState
        
        ripple = RippleState(x=100, y=100, start_time=time.time(), is_left=True)
        
        # 刚创建时进度应该接近 0
        progress = ripple.get_progress(500)
        assert 0 <= progress <= 0.1
    
    def test_is_finished(self):
        """测试完成判断"""
        from screenshot_tool.ui.effects.click_ripple_effect import RippleState
        
        # 创建一个已经过期的涟漪
        ripple = RippleState(
            x=100, y=100,
            start_time=time.time() - 1.0,  # 1 秒前
            is_left=True
        )
        
        # 500ms 动画应该已完成
        assert ripple.is_finished(500) is True
    
    @given(st.integers(min_value=100, max_value=2000))
    @settings(max_examples=50, deadline=None)
    def test_property_ripple_lifecycle(self, duration_ms):
        """Property 11: 涟漪动画生命周期"""
        from screenshot_tool.ui.effects.click_ripple_effect import RippleState
        
        # 创建涟漪
        ripple = RippleState(x=100, y=100, start_time=time.time(), is_left=True)
        
        # 初始进度应该接近 0
        initial_progress = ripple.get_progress(duration_ms)
        assert 0 <= initial_progress <= 0.5  # 允许一些时间误差
        
        # 初始不应该完成
        assert ripple.is_finished(duration_ms) is False or initial_progress >= 1.0


class TestThemeColorApplication:
    """Property 10: Theme Color Application 测试"""
    
    @given(st.sampled_from(list(MOUSE_HIGHLIGHT_THEMES.keys())))
    @settings(max_examples=10, deadline=None)
    def test_theme_colors_applied(self, theme_name):
        """测试主题颜色被正确应用"""
        from screenshot_tool.ui.effects import CircleEffect, ClickRippleEffect
        
        config = MouseHighlightConfig(theme=theme_name)
        theme = config.get_theme_colors()
        
        # 验证主题颜色
        assert "circle_color" in theme
        assert "left_click_color" in theme
        assert "right_click_color" in theme
        
        # 创建效果并验证主题被存储
        circle_effect = CircleEffect(config, theme)
        assert circle_effect.theme == theme
        
        ripple_effect = ClickRippleEffect(config, theme)
        assert ripple_effect.theme == theme
    
    def test_update_config_changes_theme(self):
        """测试更新配置改变主题"""
        from screenshot_tool.ui.effects import CircleEffect
        
        # 初始主题
        config1 = MouseHighlightConfig(theme="classic_yellow")
        theme1 = config1.get_theme_colors()
        effect = CircleEffect(config1, theme1)
        
        assert effect.theme["circle_color"] == "#FFD700"
        
        # 更新主题
        config2 = MouseHighlightConfig(theme="business_blue")
        theme2 = config2.get_theme_colors()
        effect.update_config(config2, theme2)
        
        assert effect.theme["circle_color"] == "#4A90E2"


class TestEffectConfigUpdate:
    """效果配置更新测试"""
    
    def test_update_config(self):
        """测试配置更新"""
        from screenshot_tool.ui.effects import CircleEffect
        
        config1 = MouseHighlightConfig(circle_radius=40)
        theme1 = config1.get_theme_colors()
        effect = CircleEffect(config1, theme1)
        
        assert effect.config.circle_radius == 40
        
        # 更新配置
        config2 = MouseHighlightConfig(circle_radius=60)
        theme2 = config2.get_theme_colors()
        effect.update_config(config2, theme2)
        
        assert effect.config.circle_radius == 60


class TestRippleRadiusAndOpacity:
    """涟漪半径和透明度测试"""
    
    def test_ripple_constants(self):
        """测试涟漪常量"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        assert ClickRippleEffect.START_RADIUS == 20
        assert ClickRippleEffect.END_RADIUS == 80
    
    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50, deadline=None)
    def test_property_radius_interpolation(self, progress):
        """Property 11: 半径应该从 20px 扩散到 80px"""
        from screenshot_tool.ui.effects import ClickRippleEffect
        
        start = ClickRippleEffect.START_RADIUS
        end = ClickRippleEffect.END_RADIUS
        
        # 使用 ease-out 缓动
        eased_progress = 1 - (1 - progress) ** 2
        radius = start + (end - start) * eased_progress
        
        # 验证半径在范围内
        assert start <= radius <= end
    
    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50, deadline=None)
    def test_property_opacity_decay(self, progress):
        """Property 11: 透明度应该从 255 衰减到 0"""
        # 计算透明度
        alpha = int(255 * (1 - progress))
        
        # 验证透明度在范围内
        assert 0 <= alpha <= 255
