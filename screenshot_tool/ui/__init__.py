# =====================================================
# =============== UI模块 ===============
# =====================================================

"""
UI模块 - 用户界面组件

包含:
- styles: 样式定义
- components: 基础组件
- dialogs: 对话框
"""

from .styles import (
    COLORS,
    BUTTON_PRIMARY_STYLE,
    BUTTON_SECONDARY_STYLE,
    BUTTON_DANGER_STYLE,
    TOOLBAR_STYLE,
    TOOLBUTTON_STYLE,
    DIALOG_STYLE,
    GROUPBOX_STYLE,
    INPUT_STYLE,
    CHECKBOX_STYLE,
    COLOR_PICKER_BUTTON_STYLE,
    STATUSBAR_STYLE,
    SCROLLBAR_STYLE,
    MENU_STYLE,
    TABWIDGET_STYLE,
    get_app_stylesheet,
)

# 从 ui_components.py 文件导入基础组件
from .ui_components import (
    ModernButton,
    ModernToolButton,
    ModernToolBar,
    ColorPickerButton,
    ColorPicker,
    IconLabel,
    Separator,
    ModernSwitch,
    ModernCheckBox,
)

from .dialogs import SettingsDialog, AnkiCardDialog

__all__ = [
    # 样式
    "COLORS",
    "BUTTON_PRIMARY_STYLE",
    "BUTTON_SECONDARY_STYLE",
    "BUTTON_DANGER_STYLE",
    "TOOLBAR_STYLE",
    "TOOLBUTTON_STYLE",
    "DIALOG_STYLE",
    "GROUPBOX_STYLE",
    "INPUT_STYLE",
    "CHECKBOX_STYLE",
    "COLOR_PICKER_BUTTON_STYLE",
    "STATUSBAR_STYLE",
    "SCROLLBAR_STYLE",
    "MENU_STYLE",
    "TABWIDGET_STYLE",
    "get_app_stylesheet",
    # 组件
    "ModernButton",
    "ModernToolButton",
    "ModernToolBar",
    "ColorPickerButton",
    "ColorPicker",
    "IconLabel",
    "Separator",
    "ModernSwitch",
    "ModernCheckBox",
    # 对话框
    "SettingsDialog",
    "AnkiCardDialog",
]
