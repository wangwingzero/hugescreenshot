# =====================================================
# =============== 基础UI组件 ===============
# =====================================================

"""
基础UI组件 - 现代化按钮、工具栏、颜色选择器等

Requirements: 8.1, 3.2
"""

from typing import Optional, List, Callable
from PySide6.QtWidgets import (
    QPushButton, QToolBar, QToolButton, QWidget,
    QHBoxLayout, QVBoxLayout, QLabel, QButtonGroup,
    QSizePolicy, QCheckBox, QStyle, QStyleOptionButton,
    QGroupBox
)
from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QIcon, QAction, QPainter, QPen, QColor

from .styles import (
    COLORS,
    BUTTON_PRIMARY_STYLE,
    BUTTON_SECONDARY_STYLE,
    BUTTON_DANGER_STYLE,
    TOOLBAR_STYLE,
    TOOLBUTTON_STYLE,
    COLOR_PICKER_BUTTON_STYLE,
)


class ModernButton(QPushButton):
    """现代化按钮"""
    
    # 按钮类型
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DANGER = "danger"
    
    def __init__(
        self,
        text: str = "",
        button_type: str = PRIMARY,
        icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None
    ):
        """
        初始化现代化按钮
        
        Args:
            text: 按钮文字
            button_type: 按钮类型 (primary/secondary/danger)
            icon: 按钮图标
            parent: 父组件
        """
        super().__init__(text, parent)
        
        if icon:
            self.setIcon(icon)
            self.setIconSize(QSize(16, 16))
        
        self.set_button_type(button_type)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def set_button_type(self, button_type: str):
        """设置按钮类型"""
        if button_type == self.PRIMARY:
            self.setStyleSheet(BUTTON_PRIMARY_STYLE)
        elif button_type == self.SECONDARY:
            self.setStyleSheet(BUTTON_SECONDARY_STYLE)
        elif button_type == self.DANGER:
            self.setStyleSheet(BUTTON_DANGER_STYLE)


class ModernToolButton(QToolButton):
    """现代化工具按钮"""
    
    def __init__(
        self,
        text: str = "",
        icon: Optional[QIcon] = None,
        checkable: bool = False,
        tooltip: str = "",
        parent: Optional[QWidget] = None
    ):
        """
        初始化工具按钮
        
        Args:
            text: 按钮文字
            icon: 按钮图标
            checkable: 是否可选中
            tooltip: 提示文字
            parent: 父组件
        """
        super().__init__(parent)
        
        self.setText(text)
        if icon:
            self.setIcon(icon)
            self.setIconSize(QSize(20, 20))
        
        self.setCheckable(checkable)
        self.setToolTip(tooltip)
        self.setStyleSheet(TOOLBUTTON_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)


class ModernToolBar(QToolBar):
    """现代化工具栏"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化工具栏"""
        super().__init__(parent)
        
        self.setStyleSheet(TOOLBAR_STYLE)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(20, 20))
        
        # 存储工具按钮
        self._buttons: dict = {}
    
    def add_tool_button(
        self,
        name: str,
        text: str,
        icon: Optional[QIcon] = None,
        checkable: bool = False,
        tooltip: str = "",
        callback: Optional[Callable] = None
    ) -> ModernToolButton:
        """
        添加工具按钮
        
        Args:
            name: 按钮名称（用于后续获取）
            text: 按钮文字
            icon: 按钮图标
            checkable: 是否可选中
            tooltip: 提示文字
            callback: 点击回调
            
        Returns:
            ModernToolButton: 创建的按钮
        """
        button = ModernToolButton(text, icon, checkable, tooltip)
        
        if callback:
            if checkable:
                button.toggled.connect(callback)
            else:
                button.clicked.connect(callback)
        
        self.addWidget(button)
        self._buttons[name] = button
        return button
    
    def add_separator(self):
        """添加分隔符"""
        self.addSeparator()
    
    def add_stretch(self):
        """添加弹性空间"""
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        self.addWidget(spacer)
    
    def get_button(self, name: str) -> Optional[ModernToolButton]:
        """获取指定名称的按钮"""
        return self._buttons.get(name)
    
    def set_button_enabled(self, name: str, enabled: bool):
        """设置按钮启用状态"""
        button = self._buttons.get(name)
        if button:
            button.setEnabled(enabled)
    
    def set_button_checked(self, name: str, checked: bool):
        """设置按钮选中状态"""
        button = self._buttons.get(name)
        if button and button.isCheckable():
            button.setChecked(checked)


class ColorPickerButton(QPushButton):
    """颜色选择按钮"""
    
    def __init__(
        self,
        color_name: str,
        color_hex: str,
        tooltip: str = "",
        parent: Optional[QWidget] = None
    ):
        """
        初始化颜色按钮
        
        Args:
            color_name: 颜色名称
            color_hex: 颜色十六进制值
            tooltip: 提示文字
            parent: 父组件
        """
        super().__init__(parent)
        
        self.color_name = color_name
        self.color_hex = color_hex
        
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(32, 32)
        
        # 设置样式
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                border: 2px solid transparent;
                border-radius: 16px;
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }}
            QPushButton:checked {{
                border-color: {COLORS['primary']};
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_hint']};
            }}
        """)


class ColorPicker(QWidget):
    """高亮颜色选择器"""
    
    # 颜色改变信号
    colorChanged = Signal(str)  # 发送颜色名称
    
    # 预定义颜色
    COLORS_LIST = [
        ("yellow", COLORS["highlight_yellow"], "黄色"),
        ("green", COLORS["highlight_green"], "绿色"),
        ("pink", COLORS["highlight_pink"], "粉色"),
        ("blue", COLORS["highlight_blue"], "蓝色"),
    ]
    
    def __init__(
        self,
        default_color: str = "yellow",
        show_label: bool = True,
        parent: Optional[QWidget] = None
    ):
        """
        初始化颜色选择器
        
        Args:
            default_color: 默认选中的颜色
            show_label: 是否显示标签
            parent: 父组件
        """
        super().__init__(parent)
        
        self._current_color = default_color
        self._buttons: dict = {}
        
        self._setup_ui(show_label)
        self._select_color(default_color)
    
    def _setup_ui(self, show_label: bool):
        """设置UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 标签
        if show_label:
            label = QLabel("颜色:")
            label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
            layout.addWidget(label)
        
        # 按钮组
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        
        # 创建颜色按钮
        for color_name, color_hex, tooltip in self.COLORS_LIST:
            button = ColorPickerButton(color_name, color_hex, tooltip)
            self._button_group.addButton(button)
            self._buttons[color_name] = button
            layout.addWidget(button)
            
            # 连接信号
            button.clicked.connect(lambda checked, c=color_name: self._on_color_clicked(c))
    
    def _select_color(self, color_name: str):
        """选中指定颜色"""
        button = self._buttons.get(color_name)
        if button:
            button.setChecked(True)
            self._current_color = color_name
    
    def _on_color_clicked(self, color_name: str):
        """颜色按钮点击处理"""
        if color_name != self._current_color:
            self._current_color = color_name
            self.colorChanged.emit(color_name)
    
    def get_current_color(self) -> str:
        """获取当前选中的颜色名称"""
        return self._current_color
    
    def set_current_color(self, color_name: str):
        """设置当前颜色"""
        if color_name in self._buttons:
            self._select_color(color_name)
            self.colorChanged.emit(color_name)
    
    @staticmethod
    def get_color_hex(color_name: str) -> str:
        """获取颜色的十六进制值"""
        for name, hex_val, _ in ColorPicker.COLORS_LIST:
            if name == color_name:
                return hex_val
        return COLORS["highlight_yellow"]


class IconLabel(QWidget):
    """带图标的标签"""
    
    def __init__(
        self,
        text: str = "",
        icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None
    ):
        """
        初始化带图标的标签
        
        Args:
            text: 文字
            icon: 图标
            parent: 父组件
        """
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(icon.pixmap(16, 16))
            layout.addWidget(icon_label)
        
        self._text_label = QLabel(text)
        layout.addWidget(self._text_label)
        layout.addStretch()
    
    def set_text(self, text: str):
        """设置文字"""
        self._text_label.setText(text)
    
    def text(self) -> str:
        """获取文字"""
        return self._text_label.text()


class Separator(QWidget):
    """分隔线"""
    
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    
    def __init__(
        self,
        orientation: str = HORIZONTAL,
        parent: Optional[QWidget] = None
    ):
        """
        初始化分隔线
        
        Args:
            orientation: 方向 (horizontal/vertical)
            parent: 父组件
        """
        super().__init__(parent)
        
        if orientation == self.HORIZONTAL:
            self.setFixedHeight(1)
            self.setStyleSheet(f"background-color: {COLORS['border']};")
        else:
            self.setFixedWidth(1)
            self.setStyleSheet(f"background-color: {COLORS['border']};")


class ModernSwitch(QWidget):
    """现代化开关组件 - iOS 风格的滑动开关
    
    Feature: mouse-highlight
    Requirements: 9.1
    """
    
    # 信号
    toggled = Signal(bool)
    
    # 颜色常量
    _COLOR_ON = QColor("#3B82F6")
    _COLOR_OFF = QColor("#D1D5DB")
    _COLOR_THUMB = QColor("white")
    _COLOR_DISABLED = QColor("#E5E7EB")
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._checked = False
        self._animation_progress = 0.0
        
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def isChecked(self) -> bool:
        """获取选中状态"""
        return self._checked
    
    def setChecked(self, checked: bool) -> None:
        """设置选中状态"""
        if self._checked != checked:
            self._checked = checked
            self._animation_progress = 1.0 if checked else 0.0
            self.update()
            self.toggled.emit(checked)
    
    def mousePressEvent(self, event):
        """鼠标点击切换状态"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
    
    def paintEvent(self, event):
        """绘制开关"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_enabled = self.isEnabled()
        
        # 背景颜色
        if not is_enabled:
            bg_color = self._COLOR_DISABLED
        elif self._checked:
            bg_color = self._COLOR_ON
        else:
            bg_color = self._COLOR_OFF
        
        # 绘制背景（圆角矩形）
        bg_rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(bg_rect, bg_rect.height() // 2, bg_rect.height() // 2)
        
        # 绘制滑块
        thumb_diameter = bg_rect.height() - 4
        thumb_x = bg_rect.x() + 2 + (bg_rect.width() - thumb_diameter - 4) * (1.0 if self._checked else 0.0)
        thumb_y = bg_rect.y() + 2
        
        painter.setBrush(self._COLOR_THUMB)
        # 添加阴影效果
        shadow_color = QColor(0, 0, 0, 30)
        painter.setBrush(shadow_color)
        painter.drawEllipse(int(thumb_x) + 1, int(thumb_y) + 1, thumb_diameter, thumb_diameter)
        painter.setBrush(self._COLOR_THUMB)
        painter.drawEllipse(int(thumb_x), int(thumb_y), thumb_diameter, thumb_diameter)


class ModernCheckBox(QCheckBox):
    """现代化复选框 - 选中时显示勾号（支持高DPI）"""
    
    # 颜色常量
    _COLOR_PRIMARY = QColor("#3B82F6")
    _COLOR_BORDER = QColor("#CED4DA")
    _COLOR_BORDER_DISABLED = QColor("#E9ECEF")
    _COLOR_TEXT = QColor("#212529")
    _COLOR_TEXT_DISABLED = QColor("#ADB5BD")
    _COLOR_BG = QColor("white")
    _COLOR_BG_DISABLED = QColor("#F8F9FA")
    
    # 默认复选框大小（当无法从系统获取时使用）
    _DEFAULT_BOX_SIZE = 16
    
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QCheckBox {
                font-size: 10pt;
                color: #212529;
                spacing: 8px;
            }
        """)
    
    def paintEvent(self, event):
        """自定义绘制（支持高DPI）"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_enabled = self.isEnabled()
        is_checked = self.isChecked()
        is_hovered = self.underMouse() and is_enabled
        
        # 获取复选框指示器的位置
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        indicator_rect = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, opt, self
        )
        
        # 使用指示器矩形的实际大小，确保有效值
        box_size = min(indicator_rect.width(), indicator_rect.height())
        if box_size <= 0:
            box_size = self._DEFAULT_BOX_SIZE
        
        box_x = indicator_rect.x() + (indicator_rect.width() - box_size) // 2
        box_y = indicator_rect.y() + (indicator_rect.height() - box_size) // 2
        box_rect = QRect(box_x, box_y, box_size, box_size)
        
        # 根据box_size计算边框和勾号的粗细
        border_width = max(1, box_size // 8)
        check_width = max(1.5, box_size / 6)
        corner_radius = max(2, box_size // 5)
        
        # 确定颜色
        if not is_enabled:
            border_color = self._COLOR_BORDER_DISABLED
            bg_color = self._COLOR_BG_DISABLED
            check_color = self._COLOR_BORDER_DISABLED
            text_color = self._COLOR_TEXT_DISABLED
        elif is_hovered or is_checked:
            border_color = self._COLOR_PRIMARY
            bg_color = self._COLOR_BG
            check_color = self._COLOR_PRIMARY
            text_color = self._COLOR_TEXT
        else:
            border_color = self._COLOR_BORDER
            bg_color = self._COLOR_BG
            check_color = self._COLOR_PRIMARY
            text_color = self._COLOR_TEXT
        
        # 绘制背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(box_rect, corner_radius, corner_radius)
        
        # 绘制边框
        pen = QPen(border_color, border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box_rect, corner_radius, corner_radius)
        
        # 如果选中，绘制勾号
        if is_checked:
            check_pen = QPen(check_color, check_width)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            
            # 勾号路径 - 根据box_size动态计算，确保padding不会过大
            padding = min(box_size // 4, max(2, box_size // 5))
            x, y = box_x + padding, box_y + padding
            w = max(1, box_size - padding * 2)
            h = max(1, box_size - padding * 2)
            # 勾号起点、拐点、终点
            p1_x, p1_y = x, y + h // 2
            p2_x, p2_y = x + int(w * 0.35), y + int(h * 0.8)
            p3_x, p3_y = x + w, y + int(h * 0.15)
            painter.drawLine(p1_x, p1_y, p2_x, p2_y)
            painter.drawLine(p2_x, p2_y, p3_x, p3_y)
        
        # 绘制文字
        text_rect = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxContents, opt, self
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self.text())


# ========================= 帮助组件 =========================

class InfoIconLabel(QWidget):
    """带信息图标的标签组件
    
    在标签旁边显示 ℹ️ 图标，悬停时显示帮助提示。
    
    Feature: settings-help-improvement
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    """
    
    # 提示框样式（字号 11pt，最大宽度 300px，浅色背景）
    TOOLTIP_STYLE = """
        QToolTip {
            font-size: 11pt;
            color: #212529;
            background-color: #FFFEF0;
            border: 1px solid #E9ECEF;
            border-radius: 6px;
            padding: 8px 12px;
            max-width: 300px;
        }
    """
    
    def __init__(
        self,
        text: str,
        help_text: str = "",
        parent: Optional[QWidget] = None
    ):
        """
        初始化带信息图标的标签
        
        Args:
            text: 标签文字
            help_text: 帮助提示文字（1-2句话）
            parent: 父组件
        """
        super().__init__(parent)
        
        self._help_text = help_text
        self._setup_ui(text)
    
    def _setup_ui(self, text: str):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 标签文字
        self._text_label = QLabel(text)
        self._text_label.setStyleSheet("font-size: 10pt; color: #212529;")
        layout.addWidget(self._text_label)
        
        # 信息图标（只在有帮助文字时显示）
        if self._help_text:
            self._info_icon = QLabel("ℹ️")
            self._info_icon.setStyleSheet("""
                QLabel {
                    font-size: 12pt;
                    color: #3B82F6;
                    padding: 0 2px;
                }
                QLabel:hover {
                    color: #2563EB;
                }
            """)
            self._info_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
            self._info_icon.setToolTip(self._help_text)
            # 应用提示框样式
            self._info_icon.setStyleSheet(
                self._info_icon.styleSheet() + self.TOOLTIP_STYLE
            )
            layout.addWidget(self._info_icon)
        
        layout.addStretch()
    
    def set_help_text(self, text: str) -> None:
        """更新帮助文字
        
        Args:
            text: 新的帮助文字
        """
        self._help_text = text
        if hasattr(self, '_info_icon'):
            self._info_icon.setToolTip(text)
    
    def text(self) -> str:
        """获取标签文字"""
        return self._text_label.text()
    
    def help_text(self) -> str:
        """获取帮助文字"""
        return self._help_text
    
    def has_info_icon(self) -> bool:
        """是否有信息图标"""
        return hasattr(self, '_info_icon') and self._info_icon is not None


class CollapsibleHelpPanel(QWidget):
    """可折叠帮助面板
    
    显示帮助项列表，当项数超过阈值时默认折叠。
    
    Feature: settings-help-improvement
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """
    
    # 面板样式
    PANEL_STYLE = """
        QWidget#helpPanel {
            background-color: #F0F7FF;
            border: 1px solid #CCE5FF;
            border-radius: 8px;
            padding: 12px;
        }
    """
    
    def __init__(
        self,
        title: str = "说明",
        items: Optional[List[str]] = None,
        collapsed_threshold: int = 3,
        parent: Optional[QWidget] = None
    ):
        """
        初始化可折叠帮助面板
        
        Args:
            title: 面板标题
            items: 帮助项列表
            collapsed_threshold: 超过此数量时默认折叠
            parent: 父组件
        """
        super().__init__(parent)
        
        self._title = title
        self._items = items or []
        self._collapsed_threshold = collapsed_threshold
        self._is_collapsed = len(self._items) > collapsed_threshold
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setObjectName("helpPanel")
        self.setStyleSheet(self.PANEL_STYLE)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 标题行（带折叠按钮）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # 折叠/展开按钮
        self._toggle_btn = QPushButton("▶" if self._is_collapsed else "▼")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 10pt;
                color: #3B82F6;
            }
            QPushButton:hover {
                color: #2563EB;
            }
        """)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(self._toggle_btn)
        
        # 标题
        title_label = QLabel(self._title)
        title_label.setStyleSheet("""
            font-size: 10pt;
            font-weight: bold;
            color: #3B82F6;
        """)
        header_layout.addWidget(title_label)
        
        # 折叠时显示项数
        self._count_label = QLabel(f"({len(self._items)} 项)")
        self._count_label.setStyleSheet("font-size: 9pt; color: #94A3B8;")
        self._count_label.setVisible(self._is_collapsed)
        header_layout.addWidget(self._count_label)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 内容区域
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(24, 4, 0, 0)
        content_layout.setSpacing(6)
        
        # 添加帮助项
        for item in self._items:
            item_label = QLabel(f"• {item}")
            item_label.setStyleSheet("""
                font-size: 10pt;
                color: #555;
                line-height: 1.4;
            """)
            item_label.setWordWrap(True)
            content_layout.addWidget(item_label)
        
        self._content_widget.setVisible(not self._is_collapsed)
        layout.addWidget(self._content_widget)
    
    def set_items(self, items: List[str]) -> None:
        """设置帮助项
        
        Args:
            items: 帮助项列表
        """
        self._items = items
        self._is_collapsed = len(items) > self._collapsed_threshold
        
        # 清空并重建内容
        content_layout = self._content_widget.layout()
        while content_layout.count():
            item = content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for item in items:
            item_label = QLabel(f"• {item}")
            item_label.setStyleSheet("""
                font-size: 10pt;
                color: #555;
                line-height: 1.4;
            """)
            item_label.setWordWrap(True)
            content_layout.addWidget(item_label)
        
        self._count_label.setText(f"({len(items)} 项)")
        self._count_label.setVisible(self._is_collapsed)
        self._content_widget.setVisible(not self._is_collapsed)
        self._toggle_btn.setText("▶" if self._is_collapsed else "▼")
    
    def toggle_collapsed(self) -> None:
        """切换折叠状态"""
        self._is_collapsed = not self._is_collapsed
        self._content_widget.setVisible(not self._is_collapsed)
        self._count_label.setVisible(self._is_collapsed)
        self._toggle_btn.setText("▶" if self._is_collapsed else "▼")
    
    def is_collapsed(self) -> bool:
        """是否处于折叠状态"""
        return self._is_collapsed
    
    def item_count(self) -> int:
        """获取帮助项数量"""
        return len(self._items)


class HelpGroupBox(QWidget):
    """带描述的分组框
    
    在标题下方显示一行简短描述，帮助用户理解该分组的用途。
    
    Feature: settings-help-improvement
    Requirements: 4.1, 4.2, 4.3
    """
    
    def __init__(
        self,
        title: str,
        description: str = "",
        parent: Optional[QWidget] = None
    ):
        """
        初始化带描述的分组框
        
        Args:
            title: 分组标题
            description: 分组描述（一行）
            parent: 父组件
        """
        super().__init__(parent)
        
        self._title = title
        self._description = description
        self._content_layout = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 内部分组框
        self._group_box = QGroupBox(self._title)
        self._group_box.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 10pt;
                border: 1px solid #E9ECEF;
                border-radius: 8px;
                margin-top: 16px;
                padding: 16px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 8px;
                color: #212529;
            }
        """)
        
        group_layout = QVBoxLayout(self._group_box)
        group_layout.setContentsMargins(12, 8, 12, 12)
        group_layout.setSpacing(12)
        
        # 描述标签（如果有）
        if self._description:
            self._desc_label = QLabel(self._description)
            self._desc_label.setStyleSheet("""
                font-size: 9pt;
                color: #64748B;
                padding: 0 0 8px 0;
            """)
            self._desc_label.setWordWrap(True)
            group_layout.addWidget(self._desc_label)
        
        # 内容区域
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        group_layout.addWidget(self._content_widget)
        
        main_layout.addWidget(self._group_box)
    
    def set_description(self, text: str) -> None:
        """设置描述文字
        
        Args:
            text: 描述文字
        """
        self._description = text
        if hasattr(self, '_desc_label'):
            self._desc_label.setText(text)
            self._desc_label.setVisible(bool(text))
        elif text:
            # 如果初始化时没有描述，但现在需要添加
            self._desc_label = QLabel(text)
            self._desc_label.setStyleSheet("""
                font-size: 9pt;
                color: #64748B;
                padding: 0 0 8px 0;
            """)
            self._desc_label.setWordWrap(True)
            # 插入到内容区域之前
            group_layout = self._group_box.layout()
            group_layout.insertWidget(0, self._desc_label)
    
    def content_layout(self) -> QVBoxLayout:
        """获取内容布局，用于添加设置项
        
        Returns:
            内容区域的 QVBoxLayout
        """
        return self._content_layout
    
    def add_widget(self, widget: QWidget) -> None:
        """添加组件到内容区域
        
        Args:
            widget: 要添加的组件
        """
        if self._content_layout:
            self._content_layout.addWidget(widget)
    
    def add_layout(self, layout) -> None:
        """添加布局到内容区域
        
        Args:
            layout: 要添加的布局
        """
        if self._content_layout:
            self._content_layout.addLayout(layout)
    
    def title(self) -> str:
        """获取标题"""
        return self._title
    
    def description(self) -> str:
        """获取描述"""
        return self._description

