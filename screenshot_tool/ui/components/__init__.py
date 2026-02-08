# =====================================================
# =============== UI 组件模块 ===============
# =====================================================

"""
可复用的 UI 组件

Feature: mouse-highlight-debug-panel, performance-ui-optimization, code-block-copy
"""

from screenshot_tool.ui.components.parameter_slider_group import ParameterSliderGroup
from screenshot_tool.ui.components.theme_button import ThemeButton
from screenshot_tool.ui.components.animated_button import AnimatedButton
from screenshot_tool.ui.components.success_indicator import SuccessIndicator, IndicatorState

# 代码块组件 (Feature: code-block-copy)
from screenshot_tool.ui.components.code_block import (
    CodeBlockWidget,
    get_highlighted_html,
    CODE_COLORS,
    CODE_FONT,
    CODE_LAYOUT,
    CODE_ANIMATION,
)

# 从 core 模块导入无障碍管理器，方便 UI 组件使用
from screenshot_tool.core.accessibility_manager import (
    AccessibilityManager,
    AccessibilitySettings,
    detect_reduced_motion,
    is_reduced_motion_enabled,
    should_animate,
)

__all__ = [
    "ParameterSliderGroup",
    "ThemeButton",
    "AnimatedButton",
    "SuccessIndicator",
    "IndicatorState",
    # 代码块组件
    "CodeBlockWidget",
    "get_highlighted_html",
    "CODE_COLORS",
    "CODE_FONT",
    "CODE_LAYOUT",
    "CODE_ANIMATION",
    # 无障碍相关
    "AccessibilityManager",
    "AccessibilitySettings",
    "detect_reduced_motion",
    "is_reduced_motion_enabled",
    "should_animate",
]
