# =====================================================
# =============== 鼠标高亮效果模块 ===============
# =====================================================

"""
鼠标高亮效果绘制器

包含四种效果：
- CircleEffect: 光圈效果
- SpotlightEffect: 聚光灯效果
- CursorMagnifyEffect: 指针放大效果
- ClickRippleEffect: 点击涟漪效果

Feature: mouse-highlight
"""

from screenshot_tool.ui.effects.base_effect import BaseEffect
from screenshot_tool.ui.effects.circle_effect import CircleEffect
from screenshot_tool.ui.effects.spotlight_effect import SpotlightEffect
from screenshot_tool.ui.effects.cursor_magnify_effect import CursorMagnifyEffect
from screenshot_tool.ui.effects.click_ripple_effect import ClickRippleEffect

__all__ = [
    "BaseEffect",
    "CircleEffect",
    "SpotlightEffect",
    "CursorMagnifyEffect",
    "ClickRippleEffect",
]
