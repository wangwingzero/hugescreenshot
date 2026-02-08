# =====================================================
# =============== 极简工具栏 ===============
# =====================================================

"""
极简工具栏窗口

提供快捷键按钮的紧凑视图，可拖动、可置顶。
采用 Flat Design + Glassmorphism 混合风格。

Feature: mini-toolbar
Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
"""

import os
import sys
from typing import Callable, Optional, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QApplication,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QMouseEvent, QIcon

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import ConfigManager


# =====================================================
# 颜色和样式常量
# =====================================================

MINI_TOOLBAR_COLORS = {
    "background": "rgba(255, 255, 255, 0.95)",
    "border": "#E2E8F0",
    "shadow": "rgba(0, 0, 0, 0.15)",
    "button_primary": "#3B82F6",
    "button_hover": "#60A5FA",
    "button_pressed": "#2563EB",
    "button_text": "#FFFFFF",
    "pin_active_bg": "#FEF3C7",
    "pin_active_icon": "#F59E0B",
    "pin_inactive_icon": "#94A3B8",
    "expand_border": "#E2E8F0",
    "expand_hover": "#F1F5F9",
    "text": "#1E293B",
}

SPACING = {
    "xs": 4,
    "sm": 6,
    "md": 8,
}


# =====================================================
# MiniToolbarButton 组件
# =====================================================

class MiniToolbarButton(QPushButton):
    """极简工具栏按钮
    
    紧凑的按钮样式，显示标签和快捷键。
    
    Feature: mini-toolbar
    Requirements: 3.1, 3.2
    """
    
    def __init__(self, feature_id: str, label: str, hotkey: str, parent=None):
        """初始化按钮
        
        Args:
            feature_id: 功能ID
            label: 显示标签
            hotkey: 快捷键显示
            parent: 父窗口
        """
        super().__init__(f"{label} ({hotkey})", parent)
        self._feature_id = feature_id
        self._setup_style()
    
    @property
    def feature_id(self) -> str:
        """获取功能ID"""
        return self._feature_id
    
    def _setup_style(self):
        """设置样式"""
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {MINI_TOOLBAR_COLORS['button_primary']};
                color: {MINI_TOOLBAR_COLORS['button_text']};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {MINI_TOOLBAR_COLORS['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {MINI_TOOLBAR_COLORS['button_pressed']};
            }}
        """)


# =====================================================
# PinButton 组件
# =====================================================

class PinButton(QPushButton):
    """置顶按钮
    
    用于切换窗口置顶状态。
    
    Feature: mini-toolbar
    Requirements: 2.1, 2.3
    """
    
    def __init__(self, parent=None):
        """初始化置顶按钮"""
        super().__init__(parent)
        self._is_pinned = False
        self._setup_ui()
        self._update_style()
    
    @property
    def is_pinned(self) -> bool:
        """获取置顶状态"""
        return self._is_pinned
    
    @is_pinned.setter
    def is_pinned(self, value: bool):
        """设置置顶状态"""
        self._is_pinned = value
        self._update_style()
    
    def _setup_ui(self):
        """设置UI"""
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("置顶窗口")
    
    def _update_style(self):
        """更新样式"""
        if self._is_pinned:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {MINI_TOOLBAR_COLORS['pin_active_bg']};
                    border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: #FDE68A;
                }}
            """)
            self.setText("📌")
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {MINI_TOOLBAR_COLORS['border']};
                    border-radius: 6px;
                    color: {MINI_TOOLBAR_COLORS['pin_inactive_icon']};
                }}
                QPushButton:hover {{
                    background-color: {MINI_TOOLBAR_COLORS['expand_hover']};
                }}
            """)
            self.setText("📍")


# =====================================================
# ExpandButton 组件
# =====================================================

class ExpandButton(QPushButton):
    """展开按钮
    
    用于切换到完整主窗口。
    
    Feature: mini-toolbar
    Requirements: 4.3
    """
    
    def __init__(self, parent=None):
        """初始化展开按钮"""
        super().__init__("⬜", parent)
        self._setup_style()
        self.setToolTip("展开主窗口")
    
    def _setup_style(self):
        """设置样式"""
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {MINI_TOOLBAR_COLORS['border']};
                border-radius: 6px;
                color: {MINI_TOOLBAR_COLORS['text']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {MINI_TOOLBAR_COLORS['expand_hover']};
                border-color: {MINI_TOOLBAR_COLORS['button_primary']};
            }}
        """)


# =====================================================
# DragHandle 组件
# =====================================================

class DragHandle(QWidget):
    """拖动手柄
    
    提供明显的拖动区域，显示抓取图标。
    
    Feature: mini-toolbar
    Requirements: 1.2
    """
    
    def __init__(self, parent=None):
        """初始化拖动手柄"""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setFixedSize(24, 32)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("拖动移动窗口")
        self.setStyleSheet(f"""
            QWidget {{
                background-color: transparent;
                border: none;
            }}
        """)
    
    def paintEvent(self, event):
        """绘制拖动手柄图案（6个小圆点）"""
        from PySide6.QtGui import QPainter, QBrush
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制 6 个小圆点（2列3行）
        dot_color = QColor(MINI_TOOLBAR_COLORS['pin_inactive_icon'])
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_radius = 2
        col_spacing = 6
        row_spacing = 6
        
        # 计算起始位置（居中）
        total_width = col_spacing + dot_radius * 4
        total_height = row_spacing * 2 + dot_radius * 6
        start_x = (self.width() - total_width) // 2 + dot_radius
        start_y = (self.height() - total_height) // 2 + dot_radius
        
        for row in range(3):
            for col in range(2):
                x = start_x + col * col_spacing
                y = start_y + row * row_spacing
                painter.drawEllipse(x, y, dot_radius * 2, dot_radius * 2)
        
        painter.end()


# =====================================================
# MiniToolbar 主窗口
# =====================================================

class MiniToolbar(QWidget):
    """极简工具栏窗口
    
    小巧的浮动窗口，提供快捷键按钮的紧凑视图。
    可拖动、可置顶。
    
    Feature: mini-toolbar
    Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4
    """
    
    # 信号
    feature_triggered = Signal(str)      # 功能触发，参数为功能ID
    screenshot_requested = Signal()       # 请求截图
    expand_requested = Signal()           # 请求展开到主窗口
    pin_state_changed = Signal(bool)      # 置顶状态变化
    
    def __init__(self, config_manager: Optional["ConfigManager"] = None, parent=None):
        """初始化极简工具栏
        
        Args:
            config_manager: 配置管理器
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        self._feature_callbacks: Dict[str, Callable] = {}
        self._buttons: Dict[str, MiniToolbarButton] = {}
        
        # 拖动状态
        self._is_dragging = False
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_window_pos: Optional[QPoint] = None
        
        self._setup_window()
        self._setup_ui()
        self._setup_shadow()
        self._restore_state()
    
    def _setup_window(self):
        """设置窗口属性
        
        Feature: mini-toolbar
        Requirements: 1.1, 5.2
        """
        # 无边框窗口
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint  # 初始置顶，后续根据配置调整
        )
        
        # 设置窗口属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 设置窗口标题（用于任务栏识别）
        self.setWindowTitle("虎哥截图 - 极简工具栏")
        
        # 设置窗口图标
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        icon_path = os.path.join(base_path, "resources", "虎哥截图.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
    
    def _setup_ui(self):
        """设置UI布局
        
        Feature: mini-toolbar
        Requirements: 5.1, 5.3, 5.4
        """
        # 主容器（用于绘制背景）
        self._container = QWidget(self)
        self._container.setStyleSheet(f"""
            QWidget {{
                background-color: {MINI_TOOLBAR_COLORS['background']};
                border: 1px solid {MINI_TOOLBAR_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        # 安装事件过滤器，让容器的鼠标事件传递给父窗口处理拖动
        self._container.installEventFilter(self)
        
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(self._container)
        
        # 容器布局
        container_layout = QHBoxLayout(self._container)
        container_layout.setContentsMargins(SPACING["sm"], SPACING["sm"], SPACING["sm"], SPACING["sm"])
        container_layout.setSpacing(SPACING["sm"])
        
        # 拖动手柄（左侧）- 更容易拖动
        self._drag_handle = DragHandle()
        self._drag_handle.installEventFilter(self)
        container_layout.addWidget(self._drag_handle)
        
        # 置顶按钮
        self._pin_button = PinButton()
        self._pin_button.clicked.connect(self._on_pin_clicked)
        container_layout.addWidget(self._pin_button)
        
        # 快捷键按钮容器
        self._button_container = QWidget()
        self._button_layout = QHBoxLayout(self._button_container)
        self._button_layout.setContentsMargins(0, 0, 0, 0)
        self._button_layout.setSpacing(SPACING["sm"])
        container_layout.addWidget(self._button_container)
        
        # 创建快捷键按钮
        self._create_buttons()
        
        # 展开按钮
        self._expand_button = ExpandButton()
        self._expand_button.clicked.connect(self._on_expand_clicked)
        container_layout.addWidget(self._expand_button)
        
        # 调整窗口大小
        self.adjustSize()
    
    def _setup_shadow(self):
        """设置阴影效果
        
        Feature: mini-toolbar
        Requirements: 5.2
        """
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 38))  # 约 15% 透明度
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)
    
    def _create_buttons(self):
        """创建快捷键按钮
        
        Feature: mini-toolbar
        Requirements: 3.1
        """
        # 清除现有按钮
        for button in self._buttons.values():
            button.deleteLater()
        self._buttons.clear()
        
        # 清除布局中的所有项
        while self._button_layout.count():
            item = self._button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 获取快捷键配置
        hotkey_configs = self._get_hotkey_configs()
        
        # 创建按钮
        for feature_id, label, hotkey_display, enabled in hotkey_configs:
            if enabled:
                button = MiniToolbarButton(feature_id, label, hotkey_display)
                button.clicked.connect(lambda checked=False, fid=feature_id: self._on_button_clicked(fid))
                self._button_layout.addWidget(button)
                self._buttons[feature_id] = button
    
    def _get_hotkey_configs(self) -> list:
        """获取快捷键配置列表
        
        Returns:
            [(feature_id, label, hotkey_display, enabled), ...]
        """
        configs = []
        
        # 截图按钮始终显示
        screenshot_hotkey = "Alt+X"
        if self._config_manager:
            modifier = self._config_manager.config.hotkey.screenshot_modifier
            key = self._config_manager.config.hotkey.screenshot_key
            screenshot_hotkey = self._format_hotkey(modifier, key)
        configs.append(("screenshot", "截图", screenshot_hotkey, True))
        
        # 其他快捷键根据配置显示
        if self._config_manager:
            config = self._config_manager.config
            
            # 主界面快捷键
            if config.main_window_hotkey.enabled:
                hotkey = self._format_hotkey(
                    config.main_window_hotkey.modifier,
                    config.main_window_hotkey.key
                )
                configs.append(("main_window", "主界面", hotkey, True))
            
            # 工作台快捷键
            if config.clipboard_hotkey.enabled:
                hotkey = self._format_hotkey(
                    config.clipboard_hotkey.modifier,
                    config.clipboard_hotkey.key
                )
                configs.append(("clipboard", "剪贴板", hotkey, True))
            
            # 识别文字快捷键
            if config.ocr_panel_hotkey.enabled:
                hotkey = self._format_hotkey(
                    config.ocr_panel_hotkey.modifier,
                    config.ocr_panel_hotkey.key
                )
                configs.append(("ocr_panel", "识别", hotkey, True))
            
            # 聚光灯快捷键
            if config.spotlight_hotkey.enabled:
                hotkey = self._format_hotkey(
                    config.spotlight_hotkey.modifier,
                    config.spotlight_hotkey.key
                )
                configs.append(("spotlight", "聚光灯", hotkey, True))
            
            # 鼠标高亮快捷键
            if config.mouse_highlight_hotkey.enabled:
                hotkey = self._format_hotkey(
                    config.mouse_highlight_hotkey.modifier,
                    config.mouse_highlight_hotkey.key
                )
                configs.append(("mouse_highlight", "鼠标高亮", hotkey, True))
        
        return configs
    
    def _format_hotkey(self, modifier: str, key: str) -> str:
        """格式化快捷键显示
        
        Args:
            modifier: 修饰键 (alt, ctrl+alt, etc.)
            key: 主键
            
        Returns:
            格式化的快捷键字符串 (Alt+X)
        """
        modifier_display = "+".join(part.capitalize() for part in modifier.split("+"))
        key_display = key.upper()
        return f"{modifier_display}+{key_display}"
    
    def _restore_state(self):
        """恢复窗口状态
        
        Feature: mini-toolbar
        Requirements: 1.3, 1.4, 2.4
        """
        if not self._config_manager:
            self._center_on_screen()
            return
        
        try:
            config = self._config_manager.config.mini_toolbar
            
            # 恢复置顶状态
            self._set_pinned_internal(config.is_pinned)
            
            # 恢复窗口位置
            if config.window_x >= 0 and config.window_y >= 0:
                # 验证位置是否在屏幕范围内
                screen = QApplication.primaryScreen()
                if screen:
                    screen_geo = screen.availableGeometry()
                    x = config.window_x
                    y = config.window_y
                    
                    # 确保窗口至少部分可见
                    if x + self.width() > screen_geo.right():
                        x = screen_geo.right() - self.width()
                    if y + self.height() > screen_geo.bottom():
                        y = screen_geo.bottom() - self.height()
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
        
        Feature: mini-toolbar
        Requirements: 1.4
        """
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2 + screen_geo.x()
            y = (screen_geo.height() - self.height()) // 2 + screen_geo.y()
            self.move(x, y)
    
    def _save_state(self):
        """保存窗口状态
        
        Feature: mini-toolbar
        Requirements: 1.3, 2.4
        """
        if not self._config_manager:
            return
        
        try:
            pos = self.pos()
            self._config_manager.config.mini_toolbar.window_x = pos.x()
            self._config_manager.config.mini_toolbar.window_y = pos.y()
            self._config_manager.config.mini_toolbar.is_pinned = self._pin_button.is_pinned
            self._config_manager.save()
        except Exception:
            pass  # 忽略保存失败
    
    def _set_pinned_internal(self, pinned: bool):
        """内部设置置顶状态（不触发信号）
        
        Args:
            pinned: 是否置顶
        """
        self._pin_button.is_pinned = pinned
        
        # 更新窗口标志
        flags = self.windowFlags()
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        
        # 保持其他标志
        flags |= Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        
        self.setWindowFlags(flags)
        
        # 重新显示窗口（setWindowFlags 会隐藏窗口）
        if self.isVisible():
            self.show()
    
    # =====================================================
    # 公共方法
    # =====================================================
    
    def show_and_activate(self):
        """显示并激活窗口
        
        Feature: mini-toolbar
        """
        self.show()
        self.raise_()
        self.activateWindow()
    
    def refresh_buttons(self):
        """刷新按钮显示（配置变更后调用）
        
        Feature: mini-toolbar
        Requirements: 3.3
        """
        self._create_buttons()
        self.adjustSize()
    
    def is_pinned(self) -> bool:
        """获取当前置顶状态
        
        Returns:
            是否置顶
        """
        return self._pin_button.is_pinned
    
    def set_pinned(self, pinned: bool):
        """设置置顶状态
        
        Args:
            pinned: 是否置顶
        """
        if self._pin_button.is_pinned != pinned:
            self._set_pinned_internal(pinned)
            self.pin_state_changed.emit(pinned)
    
    def register_feature_callback(self, feature_id: str, callback: Callable):
        """注册功能回调
        
        Args:
            feature_id: 功能ID
            callback: 点击时执行的回调函数
        """
        self._feature_callbacks[feature_id] = callback
    
    def get_button_count(self) -> int:
        """获取当前显示的按钮数量（用于测试）
        
        Returns:
            按钮数量
        """
        return len(self._buttons)
    
    def get_button_ids(self) -> list:
        """获取当前显示的按钮ID列表（用于测试）
        
        Returns:
            按钮ID列表
        """
        return list(self._buttons.keys())
    
    # =====================================================
    # 事件处理
    # =====================================================
    
    def eventFilter(self, watched, event):
        """事件过滤器 - 处理容器和拖动手柄的鼠标事件以实现拖动
        
        Feature: mini-toolbar
        Requirements: 1.2
        """
        from PySide6.QtCore import QEvent
        
        # 处理拖动手柄和容器的鼠标事件
        is_drag_source = watched == self._container or watched == self._drag_handle
        
        if is_drag_source:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._is_dragging = True
                    self._drag_start_pos = event.globalPosition().toPoint()
                    self._drag_start_window_pos = self.pos()
                    # 拖动手柄完全拦截事件，容器不拦截
                    return watched == self._drag_handle
            elif event.type() == QEvent.Type.MouseMove:
                if self._is_dragging and self._drag_start_pos and self._drag_start_window_pos:
                    delta = event.globalPosition().toPoint() - self._drag_start_pos
                    new_pos = self._drag_start_window_pos + delta
                    self.move(new_pos)
                    return True  # 拦截移动事件
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._is_dragging = False
                    self._drag_start_pos = None
                    self._drag_start_window_pos = None
                    return watched == self._drag_handle
        
        return super().eventFilter(watched, event)
    
    def _on_pin_clicked(self):
        """处理置顶按钮点击
        
        Feature: mini-toolbar
        Requirements: 2.2
        """
        new_state = not self._pin_button.is_pinned
        self._set_pinned_internal(new_state)
        self.pin_state_changed.emit(new_state)
    
    def _on_expand_clicked(self):
        """处理展开按钮点击
        
        Feature: mini-toolbar
        Requirements: 4.3
        """
        self.expand_requested.emit()
    
    def _on_button_clicked(self, feature_id: str):
        """处理快捷键按钮点击
        
        Feature: mini-toolbar
        Requirements: 3.2, 3.4
        """
        if feature_id == "screenshot":
            # 截图前先隐藏工具栏
            self.hide()
            self.screenshot_requested.emit()
        else:
            self.feature_triggered.emit(feature_id)
            
            # 调用注册的回调
            if feature_id in self._feature_callbacks:
                try:
                    self._feature_callbacks[feature_id]()
                except Exception:
                    pass  # 忽略回调错误
    
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件 - 开始拖动
        
        Feature: mini-toolbar
        Requirements: 1.2
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_window_pos = self.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件 - 拖动窗口
        
        Feature: mini-toolbar
        Requirements: 1.2
        """
        if self._is_dragging and self._drag_start_pos and self._drag_start_window_pos:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            new_pos = self._drag_start_window_pos + delta
            self.move(new_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件 - 结束拖动
        
        Feature: mini-toolbar
        Requirements: 1.2
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._drag_start_pos = None
            self._drag_start_window_pos = None
        super().mouseReleaseEvent(event)
    
    def hideEvent(self, event):
        """窗口隐藏时保存状态
        
        Feature: mini-toolbar
        Requirements: 1.3
        """
        super().hideEvent(event)
        self._save_state()
    
    def closeEvent(self, event):
        """窗口关闭时保存状态
        
        Feature: mini-toolbar
        Requirements: 1.3
        """
        self._save_state()
        super().closeEvent(event)
