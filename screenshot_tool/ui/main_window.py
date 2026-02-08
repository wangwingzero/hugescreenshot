# =====================================================
# =============== 虎哥截图主界面 ===============
# =====================================================

"""
虎哥截图主界面窗口

提供所有功能的入口，让用户能够快速访问各项功能。
采用 Flat Design + Minimalism 风格。

Feature: main-window
"""

from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, TYPE_CHECKING
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QGridLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QKeyEvent,
    QCloseEvent, QEnterEvent, QMouseEvent, QPalette
)

if TYPE_CHECKING:
    from screenshot_tool.overlay_main import OverlayScreenshotApp

from screenshot_tool import __version__, __app_name__
from screenshot_tool.ui.dialog_factory import DialogFactory, DialogIds
from screenshot_tool.core.resource_cache import ResourceCache
from screenshot_tool.core.async_logger import async_debug_log

# =====================================================
# 颜色和样式常量
# =====================================================

COLORS = {
    "primary": "#3B82F6",      # 主色调（蓝色）
    "secondary": "#60A5FA",    # 次要色
    "cta": "#F97316",          # 行动按钮（橙色）
    "background": "#F8FAFC",   # 背景色
    "text": "#1E293B",         # 主文本色
    "text_muted": "#64748B",   # 次要文本色
    "border": "#E2E8F0",       # 边框色
    "success": "#16A34A",      # 成功状态（深绿色，对比度 >= 3.0）
    "warning": "#EA580C",      # 警告状态（深橙色，对比度 >= 3.0）
    "card_bg": "#FFFFFF",      # 卡片背景
    "card_hover": "#F1F5F9",   # 卡片悬停背景
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}


# =====================================================
# 数据模型
# =====================================================

def get_screenshot_hotkey_display(config_manager=None) -> str:
    """获取截图热键的显示字符串
    
    Args:
        config_manager: 配置管理器实例，如果为 None 则使用默认值
        
    Returns:
        热键显示字符串，如 "Alt+X"
    """
    if config_manager is not None:
        modifier = config_manager.config.hotkey.screenshot_modifier
        key = config_manager.config.hotkey.screenshot_key
        # 格式化为首字母大写
        modifier_display = "+".join(part.capitalize() for part in modifier.split("+"))
        key_display = key.upper()
        return f"{modifier_display}+{key_display}"
    return "Alt+X"  # 默认值


@dataclass
class FeatureDefinition:
    """功能定义数据类
    
    Feature: main-window
    Requirements: 2.1, 2.5
    """
    id: str                      # 功能标识符
    title: str                   # 显示名称
    description: str             # 功能描述
    icon_name: str               # 图标名称（不含路径和扩展名）
    group: str                   # 所属分组
    action: Optional[Callable[[], None]] = None  # 点击时执行的回调
    hotkey: Optional[str] = None # 快捷键显示（如 "Alt+A"）
    vip_only: bool = False       # 是否仅VIP可用


# 功能列表定义
FEATURES: List[FeatureDefinition] = [
    # 截图工具
    FeatureDefinition(
        id="screenshot",
        title="截图",
        description="快速截取屏幕区域",
        icon_name="camera",
        group="截图工具",
        hotkey=None  # 运行时从配置动态获取
    ),
    FeatureDefinition(
        id="clipboard",
        title="工作台",
        description="查看截图历史记录",
        icon_name="clipboard",
        group="截图工具"
    ),
    # 文档处理
    # Note: ocr_panel 已移除，OCR 功能已集成到工作台窗口
    # Feature: clipboard-ocr-merge, Requirements: 7.1, 7.2
    FeatureDefinition(
        id="web_to_md",
        title="网页转MD",
        description="将网页转换为Markdown",
        icon_name="globe",
        group="文档处理"
    ),
    FeatureDefinition(
        id="file_to_md",
        title="文件转MD",
        description="将PDF/Word转换为Markdown",
        icon_name="file-text",
        group="文档处理"
    ),
    FeatureDefinition(
        id="word_format",
        title="Word排版",
        description="格式化Word文档",
        icon_name="file-word",
        group="文档处理"
    ),
    # 辅助功能
    FeatureDefinition(
        id="regulation",
        title="规章查询",
        description="查询CAAC规章文件",
        icon_name="book-open",
        group="辅助功能"
    ),
    # 录屏功能已移至截图工具栏，从主界面移除
    # Feature: recording-settings-panel, Requirements: 6.1
    FeatureDefinition(
        id="mouse_highlight",
        title="鼠标高亮",
        description="高亮显示鼠标位置",
        icon_name="mouse-pointer",
        group="辅助功能"
    ),
    FeatureDefinition(
        id="power_manager",
        title="预约关机",
        description="设置定时关机",
        icon_name="power",
        group="辅助功能"
    ),
]

# 功能分组顺序
FEATURE_GROUPS = ["截图工具", "文档处理", "辅助功能"]

# 主窗口使用的图标名称列表（用于异步预加载）
# Feature: performance-ui-optimization
# Requirements: 1.5
# Note: scan 图标已移除，OCR 功能已集成到工作台窗口
# Feature: clipboard-ocr-merge, Requirements: 7.1
MAIN_WINDOW_ICONS = [
    "camera",        # 截图
    "clipboard",     # 工作台
    "globe",         # 网页转MD
    "file-text",     # 文件转MD
    "file-word",     # Word排版
    "book-open",     # 规章查询
    "mouse-pointer", # 鼠标高亮
    "power",         # 预约关机
]


def get_features_by_group() -> Dict[str, List[FeatureDefinition]]:
    """按分组获取功能列表"""
    result = {group: [] for group in FEATURE_GROUPS}
    for feature in FEATURES:
        if feature.group in result:
            result[feature.group].append(feature)
    return result


# =====================================================
# FeatureCard 组件
# =====================================================

class FeatureCard(QFrame):
    """功能卡片组件
    
    可点击的功能入口，显示图标、名称和描述。
    
    Feature: main-window
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.6
    """
    
    clicked = Signal()  # 点击信号
    
    def __init__(self, 
                 feature_id: str,
                 icon_name: str,
                 title: str,
                 description: str,
                 hotkey: Optional[str] = None,
                 parent=None):
        """初始化功能卡片
        
        Args:
            feature_id: 功能标识符
            icon_name: 图标名称（不含路径和扩展名）
            title: 功能名称
            description: 功能描述
            hotkey: 快捷键显示（如 "Alt+A"）
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._feature_id = feature_id
        self._icon_name = icon_name
        self._title = title
        self._description = description
        self._hotkey = hotkey
        self._is_hovered = False
        
        self._setup_ui()
        self._apply_style()
        
        # 设置可聚焦和鼠标追踪
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    @property
    def feature_id(self) -> str:
        """获取功能ID"""
        return self._feature_id
    
    @property
    def title(self) -> str:
        """获取标题"""
        return self._title
    
    @property
    def description(self) -> str:
        """获取描述"""
        return self._description
    
    @property
    def icon_name(self) -> str:
        """获取图标名称"""
        return self._icon_name
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        layout.setSpacing(SPACING["sm"])
        
        # 图标
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(48, 48)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_icon()
        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 标题（可能包含快捷键）
        title_text = self._title
        if self._hotkey:
            title_text = f"{self._title} ({self._hotkey})"
        
        self._title_label = QLabel(title_text)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {COLORS['text']};
        """)
        layout.addWidget(self._title_label)
        
        # 描述
        self._desc_label = QLabel(self._description)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS['text_muted']};
        """)
        layout.addWidget(self._desc_label)
        
        # 设置最小大小和弹性大小策略
        self.setMinimumSize(140, 120)
        self.setMaximumHeight(160)
        # 让卡片水平方向自动扩展填满可用空间
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    
    def _load_icon(self):
        """加载图标
        
        优先从 ResourceCache 获取缓存的图标，如果未缓存则尝试从文件加载。
        如果都失败则使用占位符图标。
        
        Feature: performance-ui-optimization
        Requirements: 1.5
        """
        # 首先尝试从缓存获取
        cached_icon = ResourceCache.get_icon(self._icon_name)
        if cached_icon is not None and not cached_icon.isNull():
            pixmap = cached_icon.pixmap(40, 40)
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
                return
        
        # 缓存中没有，尝试从文件加载
        import os
        import sys
        
        # 获取图标路径
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        icon_path = os.path.join(base_path, "resources", "icons", f"{self._icon_name}.svg")
        
        # 尝试加载 SVG 图标
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._icon_label.setPixmap(scaled)
                return
        
        # 如果没有图标文件，使用占位符
        self._create_placeholder_icon()
    
    def update_icon_from_cache(self):
        """从缓存更新图标
        
        当异步加载完成后调用此方法更新图标显示。
        
        Feature: performance-ui-optimization
        Requirements: 1.5
        """
        cached_icon = ResourceCache.get_icon(self._icon_name)
        if cached_icon is not None and not cached_icon.isNull():
            pixmap = cached_icon.pixmap(40, 40)
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
    
    def _create_placeholder_icon(self):
        """创建占位符图标"""
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制圆形背景
        painter.setBrush(QColor(COLORS["primary"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 32, 32)
        
        # 绘制首字母
        painter.setPen(QColor("#FFFFFF"))
        font = painter.font()
        font.setPixelSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, self._title[0])
        
        painter.end()
        self._icon_label.setPixmap(pixmap)
    
    def _apply_style(self):
        """应用样式"""
        self._update_style()
    
    def _update_style(self):
        """更新样式（根据悬停状态）"""
        if self._is_hovered:
            bg_color = COLORS["card_hover"]
            border_color = COLORS["primary"]
        else:
            bg_color = COLORS["card_bg"]
            border_color = COLORS["border"]
        
        self.setStyleSheet(f"""
            FeatureCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)
    
    def enterEvent(self, event: QEnterEvent):
        """鼠标进入事件"""
        self._is_hovered = True
        self._update_style()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开事件"""
        self._is_hovered = False
        self._update_style()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)
    
    def focusInEvent(self, event):
        """获得焦点事件"""
        self._is_hovered = True
        self._update_style()
        super().focusInEvent(event)
    
    def focusOutEvent(self, event):
        """失去焦点事件"""
        self._is_hovered = False
        self._update_style()
        super().focusOutEvent(event)



# =====================================================
# FeatureGroup 组件
# =====================================================

class FlowLayout(QVBoxLayout):
    """响应式流式布局
    
    根据容器宽度自动调整列数，卡片会自动换行。
    最小卡片宽度为 160px，最大列数为 4。
    """
    
    MIN_CARD_WIDTH = 160  # 卡片最小宽度
    MAX_COLUMNS = 4       # 最大列数
    
    def __init__(self, parent=None, columns: int = 3):
        super().__init__(parent)
        self._default_columns = columns
        self._widgets: List[QWidget] = []
        self._grid = QGridLayout()
        self._grid.setSpacing(SPACING["md"])
        self._current_columns = columns
        # 让列等宽分布
        for i in range(columns):
            self._grid.setColumnStretch(i, 1)
        self.addLayout(self._grid)
    
    def add_widget(self, widget: QWidget):
        """添加 widget 到布局"""
        self._widgets.append(widget)
        self._relayout()
    
    def _relayout(self):
        """重新排列所有 widget"""
        # 清空网格布局
        while self._grid.count():
            self._grid.takeAt(0)
        
        # 重新添加所有 widget
        for i, widget in enumerate(self._widgets):
            row = i // self._current_columns
            col = i % self._current_columns
            self._grid.addWidget(widget, row, col)
    
    def update_columns(self, available_width: int) -> None:
        """根据可用宽度更新列数
        
        Args:
            available_width: 可用宽度（像素）
        """
        if available_width <= 0:
            return
        
        # 计算可容纳的列数
        spacing = self._grid.spacing() or SPACING["md"]
        new_columns = max(1, (available_width + spacing) // (self.MIN_CARD_WIDTH + spacing))
        new_columns = min(new_columns, self.MAX_COLUMNS, len(self._widgets) if self._widgets else self._default_columns)
        
        if new_columns != self._current_columns:
            self._current_columns = new_columns
            # 更新列拉伸因子
            for i in range(self.MAX_COLUMNS):
                self._grid.setColumnStretch(i, 1 if i < new_columns else 0)
            self._relayout()


class FeatureGroup(QWidget):
    """功能分组容器
    
    将相关功能卡片组织在一起，带有分组标题。
    
    Feature: main-window
    Requirements: 2.5
    """
    
    def __init__(self, title: str, parent=None):
        """初始化功能分组
        
        Args:
            title: 分组标题
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._title = title
        self._cards: List[FeatureCard] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, SPACING["lg"])
        layout.setSpacing(SPACING["md"])
        
        # 分组标题
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS['text']};
            padding-bottom: {SPACING['sm']}px;
            border-bottom: 1px solid {COLORS['border']};
        """)
        layout.addWidget(self._title_label)
        
        # 卡片容器
        self._card_container = QWidget()
        self._card_layout = FlowLayout(columns=3)
        self._card_layout.setContentsMargins(0, SPACING["sm"], 0, 0)
        self._card_container.setLayout(self._card_layout)
        layout.addWidget(self._card_container)
    
    def add_card(self, card: FeatureCard):
        """添加功能卡片到分组
        
        Args:
            card: 功能卡片
        """
        self._cards.append(card)
        self._card_layout.add_widget(card)
    
    @property
    def cards(self) -> List[FeatureCard]:
        """获取所有卡片"""
        return self._cards.copy()
    
    @property
    def title(self) -> str:
        """获取分组标题"""
        return self._title
    
    def resizeEvent(self, event):
        """窗口大小改变时更新布局列数"""
        super().resizeEvent(event)
        # 获取卡片容器的可用宽度
        available_width = self._card_container.width()
        self._card_layout.update_columns(available_width)



# =====================================================
# StatusBar 组件
# =====================================================

class StatusBar(QWidget):
    """状态栏组件
    
    显示热键状态、极简/设置/VIP 按钮。
    
    Feature: main-window
    Requirements: 6.1, 6.2, 6.3
    """
    
    # 状态常量
    STATUS_REGISTERED = "registered"
    STATUS_WAITING = "waiting"
    STATUS_FAILED = "failed"
    
    # 信号
    settings_clicked = Signal()
    mini_mode_requested = Signal()
    
    def __init__(self, parent=None):
        """初始化状态栏"""
        super().__init__(parent)
        
        self._hotkey_status = self.STATUS_REGISTERED
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        
        # 左侧：热键状态
        self._hotkey_container = QWidget()
        hotkey_layout = QHBoxLayout(self._hotkey_container)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_layout.setSpacing(SPACING["xs"])
        
        # 状态指示器（圆点）
        self._status_indicator = QLabel("●")
        self._status_indicator.setFixedWidth(16)
        hotkey_layout.addWidget(self._status_indicator)
        
        # 状态文字
        self._hotkey_label = QLabel("热键已注册")
        hotkey_layout.addWidget(self._hotkey_label)
        
        layout.addWidget(self._hotkey_container)
        
        # 弹性空间
        layout.addStretch()
        
        # 极简模式按钮
        self._mini_btn = QPushButton("极简")
        self._mini_btn.setFixedHeight(28)
        self._mini_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mini_btn.setToolTip("切换到极简工具栏")
        self._mini_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-size: 12px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['card_hover']};
                color: {COLORS['text']};
                border-color: {COLORS['primary']};
            }}
        """)
        layout.addWidget(self._mini_btn)
        
        # 设置按钮
        self._settings_btn = QPushButton("设置")
        self._settings_btn.setFixedHeight(28)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-size: 12px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['card_hover']};
                color: {COLORS['text']};
                border-color: {COLORS['primary']};
            }}
        """)
        layout.addWidget(self._settings_btn)
        
        # 应用初始样式
        self._update_hotkey_style()
        
        # 设置背景
        self.setStyleSheet(f"""
            StatusBar {{
                background-color: {COLORS['background']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
    
    def _connect_signals(self):
        """连接信号"""
        self._mini_btn.clicked.connect(self.mini_mode_requested.emit)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
    
    def update_hotkey_status(self, status: str):
        """更新热键状态显示
        
        Args:
            status: 状态字符串 (registered/waiting/failed)
            
        Feature: main-window
        Requirements: 6.2, 6.3
        """
        self._hotkey_status = status
        self._update_hotkey_style()
    
    def _update_hotkey_style(self):
        """更新热键状态样式"""
        if self._hotkey_status == self.STATUS_REGISTERED:
            color = COLORS["success"]
            text = "热键已注册"
        elif self._hotkey_status == self.STATUS_WAITING:
            color = COLORS["warning"]
            text = "等待注册..."
        else:  # failed
            color = COLORS["warning"]
            text = "热键冲突"
        
        self._status_indicator.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
        """)
        self._hotkey_label.setText(text)
        self._hotkey_label.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 12px;
        """)
    
    @property
    def hotkey_status(self) -> str:
        """获取当前热键状态"""
        return self._hotkey_status
    
    def get_indicator_color(self) -> str:
        """获取当前指示器颜色（用于测试）"""
        if self._hotkey_status == self.STATUS_REGISTERED:
            return COLORS["success"]
        else:
            return COLORS["warning"]
    
    def get_status_text(self) -> str:
        """获取当前状态文字（用于测试）"""
        return self._hotkey_label.text()


# =====================================================
# WelcomeOverlay 组件
# =====================================================

class WelcomeOverlay(QWidget):
    """欢迎提示覆盖层
    
    首次启动时显示，介绍热键和托盘功能。
    
    Feature: main-window
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """
    
    dismissed = Signal()  # 用户关闭提示时发出
    
    def __init__(self, hotkey: str = "Alt+X", parent=None):
        """初始化欢迎覆盖层
        
        Args:
            hotkey: 截图热键显示文本
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._hotkey = hotkey
        self._setup_ui()
        
        # 设置为覆盖整个父窗口
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    def _setup_ui(self):
        """设置UI布局"""
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 半透明背景
        self._background = QFrame(self)
        self._background.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, 0.5);
            }}
        """)
        
        # 欢迎卡片
        self._card = QFrame(self)
        self._card.setFixedSize(400, 300)
        self._card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['card_bg']};
                border-radius: 12px;
            }}
        """)
        
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        card_layout.setSpacing(SPACING["lg"])
        
        # 标题
        title = QLabel(f"欢迎使用 {__app_name__}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 600;
            color: {COLORS['text']};
        """)
        card_layout.addWidget(title)
        
        # 热键说明
        hotkey_info = QLabel(f"按 {self._hotkey} 快速截图")
        hotkey_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hotkey_info.setStyleSheet(f"""
            font-size: 16px;
            color: {COLORS['primary']};
            font-weight: 500;
        """)
        card_layout.addWidget(hotkey_info)
        
        # 托盘说明
        tray_info = QLabel("程序会最小化到系统托盘\n点击托盘图标打开主界面")
        tray_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tray_info.setWordWrap(True)
        tray_info.setStyleSheet(f"""
            font-size: 14px;
            color: {COLORS['text_muted']};
            line-height: 1.5;
        """)
        card_layout.addWidget(tray_info)
        
        card_layout.addStretch()
        
        # "知道了"按钮
        self._dismiss_btn = QPushButton("知道了")
        self._dismiss_btn.setFixedSize(120, 40)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['secondary']};
            }}
            QPushButton:pressed {{
                background-color: #2563EB;
            }}
        """)
        self._dismiss_btn.clicked.connect(self._on_dismiss_clicked)
        card_layout.addWidget(self._dismiss_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    
    def _on_dismiss_clicked(self):
        """处理"知道了"按钮点击"""
        self.dismissed.emit()
        self.hide()
    
    def resizeEvent(self, event):
        """调整大小时重新布局"""
        super().resizeEvent(event)
        
        # 背景覆盖整个区域
        self._background.setGeometry(0, 0, self.width(), self.height())
        
        # 卡片居中
        card_x = (self.width() - self._card.width()) // 2
        card_y = (self.height() - self._card.height()) // 2
        self._card.move(card_x, card_y)
    
    def showEvent(self, event):
        """显示时调整布局"""
        super().showEvent(event)
        self.resizeEvent(None)


# =====================================================
# HotkeyChip 组件
# =====================================================

class HotkeyChip(QPushButton):
    """快捷键按钮组件
    
    显示功能名称和快捷键，可点击触发功能。
    使用 Flat Design 风格。
    
    Feature: extended-hotkeys
    Requirements: 3.4, 3.5, 3.6, 6.1, 6.2, 6.3
    """
    
    clicked_with_id = Signal(str)  # 点击时发出功能ID
    
    def __init__(self, feature_id: str, label: str, hotkey: str, parent=None):
        """初始化快捷键按钮
        
        Args:
            feature_id: 功能标识符 (screenshot, main_window, clipboard, ocr, spotlight)
            label: 显示标签 (截图, 主界面, 剪贴板, 识别, 聚光灯)
            hotkey: 快捷键显示 (Alt+X)
            parent: 父窗口
        """
        super().__init__(f"{label} ({hotkey})", parent)
        self._feature_id = feature_id
        self._setup_style()
        self.clicked.connect(lambda: self.clicked_with_id.emit(self._feature_id))
    
    @property
    def feature_id(self) -> str:
        """获取功能ID"""
        return self._feature_id
    
    def _setup_style(self):
        """设置样式"""
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['secondary']};
            }}
            QPushButton:pressed {{
                background-color: #2563EB;
            }}
        """)


# =====================================================
# QuickActionBar 组件
# =====================================================

class QuickActionBar(QWidget):
    """快捷操作栏
    
    显示极简模式和设置按钮。
    快捷键提示已移至功能卡片上显示。
    
    Feature: main-window, mini-toolbar
    Requirements: 4.1
    """
    
    screenshot_clicked = Signal()
    settings_clicked = Signal()
    mini_mode_requested = Signal()  # 请求切换到极简模式
    feature_triggered = Signal(str)  # 功能触发信号，参数为功能ID
    
    def __init__(self, hotkey: str = "Alt+X", config_manager=None, parent=None):
        """初始化快捷操作栏
        
        Args:
            hotkey: 截图热键显示文本（保留参数兼容性）
            config_manager: 配置管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._hotkey = hotkey
        self._config_manager = config_manager
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])
        layout.setSpacing(SPACING["sm"])
        
        # 左侧弹性空间
        layout.addStretch()
        
        # 极简模式按钮
        # Feature: mini-toolbar
        # Requirements: 4.1
        self._mini_btn = QPushButton("极简")
        self._mini_btn.setFixedHeight(40)
        self._mini_btn.setMinimumWidth(60)
        self._mini_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mini_btn.setToolTip("切换到极简工具栏")
        self._mini_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['card_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-size: 14px;
                padding: 0 {SPACING['md']}px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['card_hover']};
                border-color: {COLORS['primary']};
            }}
        """)
        self._mini_btn.clicked.connect(self.mini_mode_requested.emit)
        layout.addWidget(self._mini_btn)
        
        # 设置按钮
        self._settings_btn = QPushButton("设置")
        self._settings_btn.setFixedHeight(40)
        self._settings_btn.setMinimumWidth(80)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['card_bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-size: 14px;
                padding: 0 {SPACING['md']}px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['card_hover']};
                border-color: {COLORS['primary']};
            }}
        """)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self._settings_btn)
        
        # 设置背景和固定高度
        # 按钮高度 40px + 上下边距 SPACING["md"]*2 = 40 + 16*2 = 72px
        self.setFixedHeight(72)
        self.setStyleSheet(f"""
            QuickActionBar {{
                background-color: {COLORS['card_bg']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
    
    def refresh(self):
        """刷新操作栏（保留接口兼容性）"""
        # 更新截图热键显示
        if self._config_manager:
            self._hotkey = get_screenshot_hotkey_display(self._config_manager)
    
    def get_chip_count(self) -> int:
        """获取当前显示的按钮数量（用于测试，保留兼容性）"""
        return 0  # 不再显示快捷键按钮


# =====================================================
# MainWindow 主窗口
# =====================================================

class MainWindow(QMainWindow):
    """主界面窗口
    
    提供所有功能的入口，让用户能够快速访问各项功能。
    
    Feature: main-window, mini-toolbar
    Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 4.4, 9.1, 9.4
    """
    
    feature_activated = Signal(str)  # 功能被激活时发出，参数为功能ID
    screenshot_requested = Signal()  # 请求截图
    settings_requested = Signal()    # 请求打开设置
    mini_mode_requested = Signal()   # 请求切换到极简模式
    window_closed = Signal()         # 窗口关闭时发出（用于保存位置）
    
    def __init__(self, config_manager=None, parent=None):
        """初始化主窗口
        
        Args:
            config_manager: 配置管理器，用于保存/恢复窗口位置
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        self._feature_callbacks: Dict[str, Callable] = {}
        
        self._setup_window()
        self._start_async_icon_loading()  # 启动异步图标加载
        self._setup_ui()
        self._setup_welcome_overlay()
        self._register_dialog_creators()
        self._restore_window_geometry()
    
    def _start_async_icon_loading(self):
        """启动异步图标预加载
        
        在后台线程中加载主窗口使用的所有图标，避免阻塞 UI。
        加载完成后通过回调更新 FeatureCard 的图标显示。
        
        Feature: performance-ui-optimization
        Requirements: 1.5
        """
        import os
        import sys
        
        # 获取应用程序基础路径
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 设置图标加载完成回调
        ResourceCache.set_on_icon_loaded(self._on_icon_loaded)
        
        # 启动异步预加载
        ResourceCache.preload_icons(
            icon_names=MAIN_WINDOW_ICONS,
            base_path=base_path,
            icon_subdir="resources/icons",
            icon_extension=".svg"
        )
    
    def _on_icon_loaded(self, icon_name: str, icon: QIcon):
        """图标加载完成回调
        
        当异步加载完成一个图标时，更新对应 FeatureCard 的图标显示。
        
        Args:
            icon_name: 图标名称
            icon: 加载完成的 QIcon 对象
            
        Feature: performance-ui-optimization
        Requirements: 1.5
        """
        # 查找使用此图标的 FeatureCard 并更新
        if hasattr(self, '_feature_cards'):
            for card in self._feature_cards.values():
                if card.icon_name == icon_name:
                    card.update_icon_from_cache()
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        # 最小尺寸：功能卡片 3 列布局需要约 550px 宽度
        self.setMinimumSize(550, 400)
        self.resize(750, 600)
        
        # 设置窗口图标
        import os
        import sys
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        icon_path = os.path.join(base_path, "resources", "虎哥截图.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
    
    def _setup_ui(self):
        """设置UI布局"""
        # 中央 widget
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 功能面板（可滚动）
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLORS['background']};
                border: none;
            }}
        """)
        
        # 功能容器
        feature_container = QWidget()
        feature_layout = QVBoxLayout(feature_container)
        feature_layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        feature_layout.setSpacing(0)
        
        # 按分组添加功能卡片
        self._feature_groups: Dict[str, FeatureGroup] = {}
        self._feature_cards: Dict[str, FeatureCard] = {}
        
        grouped_features = get_features_by_group()
        for group_name in FEATURE_GROUPS:
            features = grouped_features.get(group_name, [])
            if not features:
                continue
            
            group = FeatureGroup(group_name)
            self._feature_groups[group_name] = group
            
            for feature in features:
                # 根据功能ID获取对应的快捷键
                display_hotkey = self._get_feature_hotkey(feature.id)
                card = FeatureCard(
                    feature_id=feature.id,
                    icon_name=feature.icon_name,
                    title=feature.title,
                    description=feature.description,
                    hotkey=display_hotkey
                )
                card.clicked.connect(lambda fid=feature.id: self._on_feature_clicked(fid))
                group.add_card(card)
                self._feature_cards[feature.id] = card
            
            feature_layout.addWidget(group)
        
        feature_layout.addStretch()
        scroll_area.setWidget(feature_container)
        main_layout.addWidget(scroll_area, 1)
        
        # 状态栏（包含极简/设置按钮）
        self._status_bar = StatusBar()
        self._status_bar.settings_clicked.connect(self.settings_requested.emit)
        self._status_bar.mini_mode_requested.connect(self.mini_mode_requested.emit)
        main_layout.addWidget(self._status_bar)
        
        # 设置背景色
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['background']};
            }}
        """)
    
    def _setup_welcome_overlay(self):
        """设置欢迎覆盖层"""
        hotkey_display = get_screenshot_hotkey_display(self._config_manager)
        self._welcome_overlay = WelcomeOverlay(hotkey=hotkey_display, parent=self)
        self._welcome_overlay.dismissed.connect(self._on_welcome_dismissed)
        self._welcome_overlay.hide()
    
    def _register_dialog_creators(self):
        """注册对话框创建函数
        
        使用 DialogFactory 延迟创建对话框，首次访问时才实例化。
        
        Feature: performance-ui-optimization
        Requirements: 1.4, 9.1
        """
        # 注册设置对话框
        # 注意：设置对话框需要 config 和 update_service，这些在 overlay_main 中提供
        # 这里只注册创建函数的占位符，实际创建函数由 overlay_main 注册
        
        # 注册网页转 Markdown 对话框
        if self._config_manager:
            DialogFactory.register(
                DialogIds.WEB_TO_MARKDOWN,
                lambda: self._create_web_to_markdown_dialog()
            )
        
        # 注册文件转 Markdown 对话框
        if self._config_manager:
            DialogFactory.register(
                DialogIds.FILE_TO_MARKDOWN,
                lambda: self._create_file_to_markdown_dialog()
            )
    
    def _create_web_to_markdown_dialog(self):
        """创建网页转 Markdown 对话框
        
        Feature: performance-ui-optimization
        Requirements: 1.4
        """
        from screenshot_tool.ui.web_to_markdown_dialog import WebToMarkdownDialog
        
        dialog = WebToMarkdownDialog(self._config_manager.config.markdown)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 不自动删除，由工厂管理
        return dialog
    
    def _create_file_to_markdown_dialog(self):
        """创建文件转 Markdown 对话框
        
        Feature: performance-ui-optimization
        Requirements: 1.4
        """
        from screenshot_tool.ui.file_to_markdown_dialog import FileToMarkdownDialog
        
        dialog = FileToMarkdownDialog(self._config_manager.config.mineru)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 不自动删除，由工厂管理
        return dialog
    
    def register_settings_dialog_creator(self, creator: Callable):
        """注册设置对话框创建函数
        
        由 overlay_main 调用，因为设置对话框需要 update_service 等依赖。
        
        Args:
            creator: 创建设置对话框的工厂函数
            
        Feature: performance-ui-optimization
        Requirements: 1.4
        """
        DialogFactory.register(DialogIds.SETTINGS, creator)
    
    def get_dialog(self, dialog_id: str):
        """获取对话框实例
        
        通过 DialogFactory 获取延迟创建的对话框。
        
        Args:
            dialog_id: 对话框 ID（使用 DialogIds 常量）
            
        Returns:
            对话框实例，如果未注册则返回 None
            
        Feature: performance-ui-optimization
        Requirements: 1.4, 9.1
        """
        return DialogFactory.get(dialog_id)
    
    def _get_feature_hotkey(self, feature_id: str) -> Optional[str]:
        """根据功能ID获取对应的快捷键显示
        
        Args:
            feature_id: 功能标识符
            
        Returns:
            快捷键显示字符串（如 "Alt+X"），如果未启用则返回 None
        """
        if not self._config_manager:
            # 没有配置管理器时，截图功能使用默认值
            if feature_id == "screenshot":
                return "Alt+X"
            return None
        
        config = self._config_manager.config
        
        def format_hotkey(modifier: str, key: str) -> str:
            """格式化快捷键显示"""
            modifier_display = "+".join(part.capitalize() for part in modifier.split("+"))
            key_display = key.upper()
            return f"{modifier_display}+{key_display}"
        
        # 截图功能始终显示快捷键
        if feature_id == "screenshot":
            return format_hotkey(
                config.hotkey.screenshot_modifier,
                config.hotkey.screenshot_key
            )
        
        # 工作台
        if feature_id == "clipboard":
            if config.clipboard_hotkey.enabled:
                return format_hotkey(
                    config.clipboard_hotkey.modifier,
                    config.clipboard_hotkey.key
                )
            return None
        
        # 识别文字
        if feature_id == "ocr_panel":
            if config.ocr_panel_hotkey.enabled:
                return format_hotkey(
                    config.ocr_panel_hotkey.modifier,
                    config.ocr_panel_hotkey.key
                )
            return None
        
        # 鼠标高亮
        if feature_id == "mouse_highlight":
            if config.mouse_highlight_hotkey.enabled:
                return format_hotkey(
                    config.mouse_highlight_hotkey.modifier,
                    config.mouse_highlight_hotkey.key
                )
            return None
        
        # 其他功能暂无快捷键
        return None
    
    def _on_feature_clicked(self, feature_id: str):
        """功能卡片点击处理"""
        print(f"[MainWindow] _on_feature_clicked: {feature_id}")  # 调试日志
        self.feature_activated.emit(feature_id)
        
        # 调用注册的回调
        print(f"[MainWindow] 已注册的回调: {list(self._feature_callbacks.keys())}")  # 调试日志
        if feature_id in self._feature_callbacks:
            print(f"[MainWindow] 找到回调，正在执行: {feature_id}")  # 调试日志
            try:
                self._feature_callbacks[feature_id]()
                print(f"[MainWindow] 回调执行完成: {feature_id}")  # 调试日志
            except Exception as e:
                print(f"[MainWindow] 回调执行失败: {feature_id}, 错误: {e}")  # 调试日志
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "功能启动失败",
                    f"无法启动 {feature_id}：{str(e)}"
                )
        else:
            print(f"[MainWindow] 未找到回调: {feature_id}")  # 调试日志
    
    def _on_welcome_dismissed(self):
        """欢迎提示关闭处理"""
        # 由外部保存配置
        pass
    
    def register_feature_callback(self, feature_id: str, callback: Callable):
        """注册功能回调
        
        Args:
            feature_id: 功能ID
            callback: 点击时执行的回调函数
        """
        self._feature_callbacks[feature_id] = callback
    
    def show_welcome(self):
        """显示欢迎提示"""
        self._welcome_overlay.show()
        self._welcome_overlay.raise_()
    
    def show_and_activate(self):
        """显示并激活窗口（置于最前）
        
        处理各种窗口状态：
        - 最小化：恢复到正常状态
        - 隐藏：显示窗口
        - 已显示：激活并置顶
        """
        async_debug_log(f"show_and_activate: isMinimized={self.isMinimized()}, isVisible={self.isVisible()}, isHidden={self.isHidden()}", "MAIN-WINDOW")
        
        # 如果窗口最小化，先恢复
        if self.isMinimized():
            async_debug_log("show_and_activate: 窗口最小化，调用 showNormal()", "MAIN-WINDOW")
            self.showNormal()
        else:
            async_debug_log("show_and_activate: 调用 show()", "MAIN-WINDOW")
            self.show()
        self.raise_()
        self.activateWindow()
        async_debug_log(f"show_and_activate 完成: isVisible={self.isVisible()}", "MAIN-WINDOW")
    
    def update_hotkey_status(self, status: str):
        """更新热键状态显示
        
        Args:
            status: 状态字符串 (registered/waiting/failed)
        """
        self._status_bar.update_hotkey_status(status)
    
    def closeEvent(self, event: QCloseEvent):
        """处理关闭事件
        
        普通关闭：隐藏窗口，最小化到托盘
        Shift+关闭：真正退出应用
        
        Feature: main-window
        Requirements: 4.1, 4.4
        """
        modifiers = QApplication.keyboardModifiers()
        async_debug_log(f"closeEvent: modifiers={modifiers}", "MAIN-WINDOW")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift+关闭：真正退出
            async_debug_log("closeEvent: Shift+关闭，退出应用", "MAIN-WINDOW")
            event.accept()
            QApplication.quit()
        else:
            # 普通关闭：隐藏到托盘
            async_debug_log("closeEvent: 普通关闭，隐藏到托盘", "MAIN-WINDOW")
            event.ignore()
            self.hide()
            async_debug_log(f"closeEvent 完成: isVisible={self.isVisible()}, isHidden={self.isHidden()}", "MAIN-WINDOW")
    
    def keyPressEvent(self, event: QKeyEvent):
        """处理键盘事件
        
        Escape: 最小化到托盘
        
        Feature: main-window
        Requirements: 9.4
        """
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
    
    def resizeEvent(self, event):
        """调整大小时更新欢迎覆盖层"""
        super().resizeEvent(event)
        if hasattr(self, '_welcome_overlay'):
            self._welcome_overlay.setGeometry(self.centralWidget().geometry())
    
    def _restore_window_geometry(self):
        """恢复窗口位置和大小
        
        Feature: main-window
        Requirements: 1.4
        """
        if not self._config_manager:
            self._center_on_screen()
            return
        
        try:
            config = self._config_manager.config.main_window
            
            # 恢复窗口大小
            width = config.window_width
            height = config.window_height
            self.resize(width, height)
            
            # 恢复窗口位置
            if config.window_x >= 0 and config.window_y >= 0:
                # 验证位置是否在屏幕范围内
                screen = QApplication.primaryScreen()
                if screen:
                    screen_geo = screen.availableGeometry()
                    x = config.window_x
                    y = config.window_y
                    
                    # 确保窗口至少部分可见
                    if x + width > screen_geo.right():
                        x = screen_geo.right() - width
                    if y + height > screen_geo.bottom():
                        y = screen_geo.bottom() - height
                    if x < screen_geo.left():
                        x = screen_geo.left()
                    if y < screen_geo.top():
                        y = screen_geo.top()
                    
                    self.move(x, y)
                else:
                    self._center_on_screen()
            else:
                self._center_on_screen()
        except Exception:
            self._center_on_screen()
    
    def _center_on_screen(self):
        """将窗口居中显示在主屏幕上
        
        Feature: main-window
        Requirements: 1.4
        """
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2 + screen_geo.x()
            y = (screen_geo.height() - self.height()) // 2 + screen_geo.y()
            self.move(x, y)
    
    def _save_window_geometry(self):
        """保存窗口位置和大小
        
        Feature: main-window
        Requirements: 1.4
        """
        if not self._config_manager:
            return
        
        try:
            geo = self.geometry()
            self._config_manager.config.main_window.window_x = geo.x()
            self._config_manager.config.main_window.window_y = geo.y()
            self._config_manager.config.main_window.window_width = geo.width()
            self._config_manager.config.main_window.window_height = geo.height()
            self._config_manager.save()
        except Exception:
            pass  # 忽略保存失败
    
    def hideEvent(self, event):
        """窗口隐藏时保存位置"""
        async_debug_log(f"hideEvent: 窗口隐藏", "MAIN-WINDOW")
        super().hideEvent(event)
        self._save_window_geometry()
        async_debug_log(f"hideEvent 完成: isVisible={self.isVisible()}", "MAIN-WINDOW")
