# =====================================================
# =============== 样式定义 v2.0 ===============
# =====================================================

"""
样式定义 - 简洁高级感 + 极致性能

设计原则：
1. Flat Design - 无阴影、无渐变、纯色块
2. 8px 间距系统 - 所有间距为 8 的倍数
3. 6 色精简配色 - 减少视觉噪音
4. 性能优先 - 避免触发重排的属性变化

Requirements: 7.1, 7.2, 8.1
"""

from PySide6.QtCore import QEasingCurve

# =====================================================
# 动画常量 - Animation Constants
# =====================================================

class AnimationConstants:
    """动画常量定义
    
    Feature: performance-ui-optimization
    Requirements: 7.1, 7.2, 7.3, 8.1, 8.2
    
    基于 UX 最佳实践：
    - 微交互: 150-300ms
    - 状态过渡: 200ms
    - 成功动画: 200-500ms
    """
    
    # 时长常量 (毫秒)
    INSTANT = 50          # 即时反馈 (点击)
    FAST = 150            # 快速过渡 (悬停)
    NORMAL = 200          # 标准过渡
    SLOW = 300            # 慢速过渡
    SUCCESS = 400         # 成功动画
    
    # 缓动曲线
    EASE_OUT = QEasingCurve.Type.OutCubic      # 进入动画
    EASE_IN = QEasingCurve.Type.InCubic        # 退出动画
    EASE_IN_OUT = QEasingCurve.Type.InOutCubic # 双向动画
    
    # CSS 时长字符串 (用于 QSS)
    CSS_INSTANT = "50ms"
    CSS_FAST = "150ms"
    CSS_NORMAL = "200ms"
    CSS_SLOW = "300ms"


# 动画时长字典 (便于动态访问)
ANIMATION = {
    "instant": 50,    # 即时反馈
    "fast": 150,      # 快速过渡
    "normal": 200,    # 标准过渡
    "slow": 300,      # 慢速过渡
    "success": 400,   # 成功动画
}


# =====================================================
# 设计系统 - Design Tokens
# =====================================================

# 间距系统（8px 基准）
SPACING = {
    "xs": 4,    # 0.5x - 紧凑间距
    "sm": 8,    # 1x   - 小间距
    "md": 16,   # 2x   - 中等间距
    "lg": 24,   # 3x   - 大间距
    "xl": 32,   # 4x   - 超大间距
}

# 圆角系统
RADIUS = {
    "sm": 4,    # 小圆角 - 输入框内部元素
    "md": 6,    # 中圆角 - 按钮、输入框
    "lg": 8,    # 大圆角 - 卡片
    "xl": 12,   # 超大圆角 - 对话框、大卡片
}

# 字体大小（pt）
FONT = {
    "xs": 9,    # 辅助文字
    "sm": 10,   # 正文
    "md": 11,   # 小标题
    "lg": 13,   # 标题
    "xl": 16,   # 大标题
}

# =====================================================
# 配色方案 - 精简 6 色系统
# =====================================================

COLORS = {
    # 基础色（3色）
    "bg": "#F8FAFC",            # 背景 - 极淡灰
    "surface": "#FFFFFF",        # 表面 - 纯白
    "border": "#E2E8F0",         # 边框 - 浅灰
    
    # 主色（1色 + 2变体）
    "primary": "#2563EB",        # 主色 - 蓝
    "primary_hover": "#1D4ED8",  # 主色悬停
    "primary_light": "#EFF6FF",  # 主色浅底
    
    # 文字色（3色）
    "text": "#1E293B",           # 主文字 - 深灰
    "text_secondary": "#64748B", # 次要文字
    "text_muted": "#94A3B8",     # 提示文字
    
    # 状态色（4色）
    "success": "#10B981",        # 成功 - 绿
    "warning": "#F59E0B",        # 警告 - 橙
    "error": "#EF4444",          # 错误 - 红
    "info": "#3B82F6",           # 信息 - 蓝
    
    # 禁用色
    "disabled": "#CBD5E1",       # 禁用边框/文字
    "disabled_bg": "#F1F5F9",    # 禁用背景
    
    # 高亮色（用于标注工具）
    "highlight_yellow": "#FEF3C7",
    "highlight_green": "#D1FAE5",
    "highlight_pink": "#FCE7F3",
    "highlight_blue": "#DBEAFE",
    "highlight_yellow_border": "#F59E0B",
    "highlight_green_border": "#10B981",
    "highlight_pink_border": "#EC4899",
    "highlight_blue_border": "#3B82F6",
}

# 兼容旧代码的别名
COLORS.update({
    "background": COLORS["bg"],
    "text_primary": COLORS["text"],
    "text_hint": COLORS["text_muted"],
    "text_white": "#FFFFFF",
    "primary_pressed": "#1E40AF",
    "param_row_bg": "#F8FAFC",
    "card_hover_bg": "#F1F5F9",
    "card_hover_border": COLORS["primary"],
})

# =====================================================
# 深色主题配色 - Dark Theme Colors
# =====================================================

COLORS_DARK = {
    # 基础色
    "bg": "#1E293B",
    "surface": "#334155",
    "border": "#475569",
    
    # 主色
    "primary": "#3B82F6",
    "primary_hover": "#60A5FA",
    "primary_light": "#1E3A5F",
    
    # 文字色
    "text": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    
    # 状态色 (保持不变)
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#EF4444",
    "info": "#3B82F6",
    
    # 禁用色
    "disabled": "#475569",
    "disabled_bg": "#1E293B",
    
    # 高亮色（用于标注工具）- 深色主题适配
    "highlight_yellow": "#78350F",
    "highlight_green": "#064E3B",
    "highlight_pink": "#831843",
    "highlight_blue": "#1E3A8A",
    "highlight_yellow_border": "#F59E0B",
    "highlight_green_border": "#10B981",
    "highlight_pink_border": "#EC4899",
    "highlight_blue_border": "#3B82F6",
}

# 深色主题兼容旧代码的别名
COLORS_DARK.update({
    "background": COLORS_DARK["bg"],
    "text_primary": COLORS_DARK["text"],
    "text_hint": COLORS_DARK["text_muted"],
    "text_white": "#FFFFFF",
    "primary_pressed": "#2563EB",
    "param_row_bg": "#334155",
    "card_hover_bg": "#475569",
    "card_hover_border": COLORS_DARK["primary"],
})

# 字体栈
FONT_FAMILY = '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'


# =====================================================
# 按钮样式 - 无布局变化，纯色块切换
# =====================================================

BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['md']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    font-weight: 600;
    min-height: 32px;
    outline: none;
}}
QPushButton:hover {{
    background-color: {COLORS['primary_hover']};
}}
QPushButton:focus {{
    border: 2px solid #1E40AF;
    padding: {SPACING['sm'] - 2}px {SPACING['md'] - 2}px;
}}
QPushButton:pressed {{
    background-color: #1E40AF;
}}
QPushButton:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['disabled']};
}}
"""

BUTTON_SECONDARY_STYLE = f"""
QPushButton {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['md']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    font-weight: 500;
    min-height: 32px;
    outline: none;
}}
QPushButton:hover {{
    border-color: {COLORS['primary']};
    color: {COLORS['primary']};
}}
QPushButton:focus {{
    border: 2px solid {COLORS['primary']};
    padding: {SPACING['sm'] - 1}px {SPACING['md'] - 1}px;
}}
QPushButton:pressed {{
    background-color: {COLORS['primary_light']};
    border-color: {COLORS['primary']};
}}
QPushButton:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['disabled']};
    border-color: {COLORS['border']};
}}
"""

BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background-color: {COLORS['error']};
    color: white;
    border: none;
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['md']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    font-weight: 600;
    min-height: 32px;
    outline: none;
}}
QPushButton:hover {{
    background-color: #DC2626;
}}
QPushButton:focus {{
    border: 2px solid #B91C1C;
    padding: {SPACING['sm'] - 2}px {SPACING['md'] - 2}px;
}}
QPushButton:pressed {{
    background-color: #B91C1C;
}}
QPushButton:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['disabled']};
}}
"""


# =====================================================
# 工具栏样式
# =====================================================

TOOLBAR_STYLE = f"""
QToolBar {{
    background-color: {COLORS['surface']};
    border-bottom: 1px solid {COLORS['border']};
    padding: {SPACING['sm']}px {SPACING['md']}px;
    spacing: {SPACING['sm']}px;
}}
QToolBar::separator {{
    background-color: {COLORS['border']};
    width: 1px;
    margin: {SPACING['xs']}px {SPACING['sm']}px;
}}
"""

TOOLBUTTON_STYLE = f"""
QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['sm']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    color: {COLORS['text_secondary']};
    outline: none;
}}
QToolButton:hover {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['primary']};
}}
QToolButton:focus {{
    border: 2px solid {COLORS['primary']};
    padding: {SPACING['sm'] - 2}px {SPACING['sm'] - 2}px;
}}
QToolButton:pressed, QToolButton:checked {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['primary']};
}}
QToolButton:disabled {{
    color: {COLORS['disabled']};
}}
"""


# =====================================================
# 画布样式
# =====================================================

CANVAS_STYLE = f"""
QWidget {{
    background-color: {COLORS['bg']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['lg']}px;
}}
"""

CANVAS_EMPTY_STYLE = f"""
QLabel {{
    color: {COLORS['text_muted']};
    font-size: {FONT['lg']}pt;
    font-family: {FONT_FAMILY};
}}
"""


# =====================================================
# 结果面板样式
# =====================================================

RESULT_PANEL_STYLE = f"""
QWidget {{
    background-color: {COLORS['surface']};
    border-left: 1px solid {COLORS['border']};
}}
"""

TEXT_AREA_STYLE = f"""
QTextEdit {{
    background-color: {COLORS['bg']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['md']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    color: {COLORS['text']};
    selection-background-color: #BFDBFE;
    selection-color: #1E3A8A;
}}
QTextEdit:focus {{
    border-color: {COLORS['primary']};
}}
QTextEdit:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['text_muted']};
}}
"""

LABEL_TITLE_STYLE = f"""
QLabel {{
    font-family: {FONT_FAMILY};
    font-size: {FONT['md']}pt;
    font-weight: 600;
    color: {COLORS['text']};
    padding: {SPACING['sm']}px 0;
}}
"""

LABEL_SECONDARY_STYLE = f"""
QLabel {{
    font-family: {FONT_FAMILY};
    font-size: {FONT['xs']}pt;
    color: {COLORS['text_secondary']};
}}
"""


# =====================================================
# 对话框样式
# =====================================================

DIALOG_STYLE = f"""
QDialog {{
    background-color: {COLORS['bg']};
    font-family: {FONT_FAMILY};
}}
QLabel {{
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
}}
"""

# 卡片式 GroupBox - 简洁无阴影
GROUPBOX_STYLE = f"""
QGroupBox {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['xl']}px;
    margin-top: {SPACING['md']}px;
    padding: 40px {SPACING['md']}px {SPACING['md']}px {SPACING['md']}px;
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    padding: 0 {SPACING['sm']}px;
    left: {SPACING['md']}px;
    top: {SPACING['md']}px;
    color: {COLORS['text']};
    font-weight: 600;
    font-size: {FONT['md']}pt;
    background-color: transparent;
}}
"""


# =====================================================
# 输入框样式 - 统一高度，边框变色反馈
# =====================================================

INPUT_STYLE = f"""
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['sm'] + 4}px;
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    min-height: 20px;
    selection-background-color: #BFDBFE;
    outline: none;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {COLORS['text_muted']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {COLORS['primary']};
    padding: {SPACING['sm'] - 1}px {SPACING['sm'] + 3}px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['text_muted']};
    border-color: {COLORS['border']};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    border: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {COLORS['text_secondary']};
    margin-right: {SPACING['sm']}px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['xs']}px;
    selection-background-color: {COLORS['primary_light']};
    selection-color: {COLORS['primary']};
}}
"""

# CheckBox 样式 - 简洁方块
CHECKBOX_STYLE = f"""
QCheckBox {{
    color: {COLORS['text']};
    spacing: {SPACING['sm']}px;
    padding: {SPACING['sm']}px 0;
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    outline: none;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['sm']}px;
    background-color: {COLORS['surface']};
}}
QCheckBox::indicator:hover {{
    border-color: {COLORS['primary']};
}}
QCheckBox:focus {{
    outline: none;
}}
QCheckBox:focus::indicator {{
    border: 2px solid {COLORS['primary']};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary']};
}}
QCheckBox:focus::indicator:checked {{
    border: 2px solid #1E40AF;
}}
QCheckBox::indicator:disabled {{
    background-color: {COLORS['disabled_bg']};
    border-color: {COLORS['border']};
}}
"""


# =====================================================
# 滚动区域样式
# =====================================================

SCROLLAREA_STYLE = """
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
"""


# =====================================================
# 设置页专用样式
# =====================================================

NUMBER_INPUT_STYLE = f"""
QLineEdit {{
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    padding: {SPACING['sm']}px {SPACING['sm']}px;
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    min-width: 60px;
    max-width: 100px;
    outline: none;
}}
QLineEdit:hover {{
    border-color: {COLORS['text_muted']};
}}
QLineEdit:focus {{
    border: 2px solid {COLORS['primary']};
    padding: {SPACING['sm'] - 1}px {SPACING['sm'] - 1}px;
}}
QLineEdit:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['text_muted']};
}}
"""

PARAMETER_ROW_STYLE = f"""
QFrame {{
    background: {COLORS['bg']};
    border-radius: {RADIUS['md']}px;
}}
"""

# 效果卡片 - 边框加粗代替阴影
EFFECT_CARD_STYLE = f"""
QFrame {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['lg']}px;
}}
QFrame:hover {{
    border: 2px solid {COLORS['primary']};
    margin: -1px;
}}
"""

# 主题按钮
THEME_BUTTON_STYLE = f"""
QPushButton {{
    padding: {SPACING['sm'] + 4}px {SPACING['md']}px;
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['md']}px;
    background-color: {COLORS['surface']};
    font-family: {FONT_FAMILY};
    font-size: {FONT['sm']}pt;
    font-weight: 500;
    color: {COLORS['text']};
    outline: none;
}}
QPushButton:hover {{
    border-color: {COLORS['primary']};
    color: {COLORS['primary']};
}}
QPushButton:focus {{
    border: 2px solid {COLORS['primary']};
    padding: {SPACING['sm'] + 3}px {SPACING['md'] - 1}px;
}}
QPushButton:checked {{
    border: 2px solid {COLORS['primary']};
    background-color: {COLORS['primary_light']};
    color: {COLORS['primary']};
    margin: -1px;
}}
QPushButton:disabled {{
    background-color: {COLORS['disabled_bg']};
    color: {COLORS['disabled']};
}}
"""


# =====================================================
# 颜色选择器样式
# =====================================================

COLOR_PICKER_BUTTON_STYLE = f"""
QPushButton {{
    border: 2px solid transparent;
    border-radius: 14px;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    outline: none;
}}
QPushButton:checked {{
    border-color: {COLORS['primary']};
}}
QPushButton:hover {{
    border-color: {COLORS['text_muted']};
}}
QPushButton:focus {{
    border-color: {COLORS['primary']};
}}
"""


# =====================================================
# 状态栏样式
# =====================================================

STATUSBAR_STYLE = f"""
QStatusBar {{
    background-color: {COLORS['surface']};
    border-top: 1px solid {COLORS['border']};
    padding: {SPACING['sm']}px {SPACING['md']}px;
    font-family: {FONT_FAMILY};
    font-size: {FONT['xs']}pt;
    color: {COLORS['text_secondary']};
}}
QStatusBar::item {{
    border: none;
}}
"""


# =====================================================
# 滚动条样式 - 极简细滚动条
# =====================================================

SCROLLBAR_STYLE = f"""
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {COLORS['disabled']};
    border-radius: 4px;
    min-height: 32px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {COLORS['text_muted']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {COLORS['disabled']};
    border-radius: 4px;
    min-width: 32px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {COLORS['text_muted']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}
"""


# =====================================================
# 菜单样式
# =====================================================

MENU_STYLE = f"""
QMenu {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: {RADIUS['lg']}px;
    padding: {SPACING['xs']}px;
}}
QMenu::item {{
    padding: {SPACING['sm']}px {SPACING['lg']}px {SPACING['sm']}px {SPACING['md']}px;
    border-radius: {RADIUS['md']}px;
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
}}
QMenu::item:selected {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['primary']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {COLORS['border']};
    margin: {SPACING['xs']}px {SPACING['sm']}px;
}}
"""


# =====================================================
# 标签页样式 - 色块风格
# =====================================================

TABWIDGET_STYLE = f"""
QTabWidget::pane {{
    border: none;
    background-color: transparent;
    top: {SPACING['sm']}px;
}}
QTabWidget::tab-bar {{
    alignment: left;
}}
QTabBar::tab {{
    background-color: transparent;
    border: none;
    margin-right: {SPACING['sm']}px;
    padding: {SPACING['sm']}px {SPACING['md']}px;
    color: {COLORS['text_secondary']};
    font-family: {FONT_FAMILY};
    font-weight: 500;
    font-size: {FONT['sm']}pt;
    border-radius: {RADIUS['md']}px;
}}
QTabBar::tab:hover {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
}}
QTabBar::tab:selected {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['primary']};
    font-weight: 600;
}}

QTabBar::scroller {{
    width: 48px;
}}
QTabBar QToolButton {{
    border: 1px solid {COLORS['border']};
    background-color: {COLORS['surface']};
    border-radius: {RADIUS['sm']}px;
    margin: 2px;
    padding: 2px;
}}
QTabBar QToolButton:hover {{
    background-color: {COLORS['bg']};
    border-color: {COLORS['text_muted']};
}}
"""


# =====================================================
# 应用全局样式
# =====================================================

def get_app_stylesheet() -> str:
    """获取应用全局样式表
    
    性能优化：
    - 只设置必要的全局样式
    - 避免通配符选择器
    - 使用继承减少重复
    """
    return f"""
        QMainWindow {{
            background-color: {COLORS['bg']};
        }}
        QWidget {{
            font-family: {FONT_FAMILY};
        }}
        {SCROLLBAR_STYLE}
        {MENU_STYLE}
    """


# =====================================================
# 工具函数
# =====================================================

def get_color(name: str) -> str:
    """获取颜色值
    
    Args:
        name: 颜色名称
        
    Returns:
        颜色十六进制值
    """
    return COLORS.get(name, COLORS['text'])


def get_spacing(size: str) -> int:
    """获取间距值
    
    Args:
        size: 间距大小 (xs, sm, md, lg, xl)
        
    Returns:
        间距像素值
    """
    return SPACING.get(size, SPACING['md'])


def get_theme_colors(dark_mode: bool = False) -> dict:
    """获取主题配色
    
    Feature: performance-ui-optimization
    Requirements: 6.5
    
    Args:
        dark_mode: 是否使用深色主题
        
    Returns:
        配色字典 (COLORS 或 COLORS_DARK)
    """
    return COLORS_DARK if dark_mode else COLORS
