# -*- coding: utf-8 -*-
"""
CAAC 规章查询窗口 - 简洁卡片式 UI

参考 FlightToolbox 小程序的设计风格：
- 简洁的搜索框
- 统计卡片（全部/有效/失效）
- 卡片式列表项
- 日期范围筛选

Feature: caac-regulation-download-enhancement
"""

import re
import webbrowser
from datetime import date, timedelta
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox,
    QGraphicsDropShadowEffect, QSizePolicy,
    QComboBox, QDateEdit, QCheckBox,
    QFileDialog, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer, QDate
from PySide6.QtGui import QColor, QCursor, QAction

from ..core.config_manager import ConfigManager
from ..services.regulation_service import (
    RegulationService, RegulationDocument, BatchDownloadManager
)

# ==========================================
#  UI 常量与配色 (Modern Professional Palette)
#  参考: Swiss Modernism + SaaS Dashboard 风格
#  遵循 UI/UX Pro Max 设计规范
# ==========================================

THEME_COLORS = {
    # 背景色系 - 更柔和的层次感
    "bg_app": "#F9FAFB",            # 整体背景 (与 styles.py 一致)
    "bg_surface": "#FFFFFF",        # 卡片表面 (纯白)
    "bg_input": "#F3F4F6",          # 输入框背景 (Gray-100)
    "bg_hover": "#F9FAFB",          # 悬停背景
    
    # 边框色系
    "border_light": "#E5E7EB",      # 极淡边框 (与 styles.py 一致)
    "border_focus": "#2563EB",      # 聚焦边框 (Blue-600)
    "border_hover": "#D1D5DB",      # 悬停边框 (Gray-300)
    
    # 文字色系 - 更好的对比度 (WCAG AA 标准)
    "text_main": "#111827",         # 主要文字 (Gray-900) - 高对比度
    "text_sub": "#4B5563",          # 次要文字 (Gray-600) - 符合 4.5:1 对比度
    "text_hint": "#6B7280",         # 提示文字 (Gray-500) - 提升可读性
    
    # 主题色系 - 专业蓝 (与 styles.py 一致)
    "primary": "#2563EB",           # 主题色 (Blue-600)
    "primary_light": "#3B82F6",     # 主题色浅 (Blue-500)
    "primary_bg": "#EFF6FF",        # 主题色背景 (Blue-50)
    "primary_hover": "#1D4ED8",     # 主题色悬停 (Blue-700)
    
    # 功能色系 (与 styles.py 一致)
    "success": "#10B981",           # 成功绿 (Emerald-500)
    "success_bg": "#ECFDF5",        # 成功背景 (Emerald-50)
    "success_hover": "#059669",     # 成功悬停 (Emerald-600)
    
    "danger": "#EF4444",            # 危险红 (Red-500)
    "danger_bg": "#FEF2F2",         # 危险背景 (Red-50)
    
    "warning": "#F59E0B",           # 警告橙 (Amber-500)
    "warning_bg": "#FFFBEB",        # 警告背景 (Amber-50)
    
    # CTA 强调色
    "cta": "#F97316",               # 行动按钮 (Orange-500)
    "cta_hover": "#EA580C",         # 行动悬停 (Orange-600)
}

# 字体栈优化 - 与 styles.py 保持一致
FONT_FAMILY = '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'

# 动画时长常量 - 遵循 UX 最佳实践 (150-300ms)
ANIMATION_FAST = "150ms"
ANIMATION_NORMAL = "200ms"
ANIMATION_SLOW = "300ms"



def calculate_date_preset(preset: str) -> tuple[str, str]:
    """计算日期预设的日期范围
    
    Args:
        preset: 预设类型 ("all", "1day", "7days", "30days", "custom")
        
    Returns:
        (start_date, end_date) 元组，格式为 YYYY-MM-DD
        如果是 "all" 或 "custom"，返回 ("", "")
        
    Feature: caac-regulation-download-enhancement
    Property 1: Date Preset Calculation
    Validates: Requirements 1.4
    """
    if preset in ("all", "custom"):
        return ("", "")
    
    today = date.today()
    end_date = today.strftime("%Y-%m-%d")
    
    # 天数预设
    days_map = {
        "1day": 1,
        "7days": 7,
        "30days": 30,
    }
    
    days = days_map.get(preset, 0)
    if days > 0:
        start_date_obj = today - timedelta(days=days)
        start_date = start_date_obj.strftime("%Y-%m-%d")
        return (start_date, end_date)
    
    return ("", "")


def filter_documents_by_date(
    documents: List[RegulationDocument],
    start_date: str,
    end_date: str
) -> List[RegulationDocument]:
    """按日期范围筛选文档
    
    Args:
        documents: 文档列表
        start_date: 起始日期 (YYYY-MM-DD)，空字符串表示不限制
        end_date: 结束日期 (YYYY-MM-DD)，空字符串表示不限制
        
    Returns:
        筛选后的文档列表
        
    Feature: caac-regulation-download-enhancement
    Property 2: Date Range Filtering
    Validates: Requirements 1.5, 1.6, 1.7
    """
    # 如果没有日期限制，返回所有文档
    if not start_date and not end_date:
        return documents
    
    filtered = []
    for doc in documents:
        # 获取文档日期（优先 publish_date，其次 sign_date）
        doc_date = doc.publish_date or doc.sign_date
        
        # 没有日期的文档也显示（CCAR 规章可能没有日期字段）
        if not doc_date:
            filtered.append(doc)
            continue
        
        # 比较日期字符串（YYYY-MM-DD 格式可以直接比较）
        if start_date and doc_date < start_date:
            continue
        if end_date and doc_date > end_date:
            continue
        
        filtered.append(doc)
    
    return filtered


class DateRangeFilter(QWidget):
    """日期范围筛选组件
    
    使用按钮组的方式展示时间预设选项，更加直观友好。
    
    Feature: caac-regulation-download-enhancement
    Validates: Requirements 1.1, 1.2, 1.3
    """
    
    # 信号：日期范围变化 (start_date, end_date)
    dateRangeChanged = Signal(str, str)
    
    # 预设选项
    PRESETS = [
        ("all", "全部"),
        ("1day", "近1日"),
        ("7days", "近7日"),
        ("30days", "近30日"),
        ("custom", "自定义"),
    ]
    
    # 颜色定义
    COLORS = THEME_COLORS
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_preset = "all"
        self._preset_buttons: dict[str, QPushButton] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 日期标签（移除 emoji，使用文字）
        date_label = QLabel("时间")
        date_label.setStyleSheet(f"""
            font-size: 13px; 
            font-weight: 600;
            background: transparent; 
            color: {THEME_COLORS['text_sub']};
        """)
        layout.addWidget(date_label)
        
        # 预设按钮组
        for key, label in self.PRESETS:
            btn = QPushButton(label)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setProperty("preset_key", key)
            btn.clicked.connect(lambda checked=False, k=key: self._on_preset_clicked(k))
            self._preset_buttons[key] = btn
            layout.addWidget(btn)
        
        # 更新按钮样式
        self._update_button_styles()
        
        # 自定义日期选择器容器
        self._custom_container = QWidget()
        custom_layout = QHBoxLayout(self._custom_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)
        
        # 日期选择器样式
        date_edit_style = f"""
            QDateEdit {{
                background: {THEME_COLORS['bg_surface']};
                border: 1px solid {THEME_COLORS['border_light']};
                border-radius: 8px;
                padding: 6px 10px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                color: {THEME_COLORS['text_main']};
                selection-background-color: {THEME_COLORS['primary']};
                min-width: 100px;
            }}
            QDateEdit:hover {{
                border-color: {THEME_COLORS['primary']};
            }}
            QDateEdit::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border-left: none;
            }}
            QDateEdit::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {THEME_COLORS['text_sub']};
                margin-right: 6px;
            }}
        """
        
        # 日历弹窗样式
        calendar_style = f"""
            QCalendarWidget {{
                background-color: {THEME_COLORS['bg_surface']};
                border: 1px solid {THEME_COLORS['border_light']};
                border-radius: 8px;
            }}
            QCalendarWidget QWidget {{
                alternate-background-color: {THEME_COLORS['bg_app']};
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                background-color: {THEME_COLORS['bg_surface']};
                color: {THEME_COLORS['text_main']};
                selection-background-color: {THEME_COLORS['primary']};
                selection-color: white;
                border-radius: 4px;
            }}
            QCalendarWidget QAbstractItemView:disabled {{
                color: {THEME_COLORS['text_hint']};
            }}
            QCalendarWidget QToolButton {{
                color: {THEME_COLORS['text_main']};
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }}
            QCalendarWidget QToolButton:hover {{
                background-color: {THEME_COLORS['bg_app']};
            }}
            QCalendarWidget QSpinBox {{
                background-color: {THEME_COLORS['bg_surface']};
                color: {THEME_COLORS['text_main']};
                border: 1px solid {THEME_COLORS['border_light']};
                border-radius: 4px;
            }}
            QCalendarWidget #qt_calendar_navigationbar {{
                background-color: {THEME_COLORS['bg_surface']};
                border-bottom: 1px solid {THEME_COLORS['border_light']};
            }}
        """
        
        # 起始日期
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate().addYears(-1))
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._start_date.setStyleSheet(date_edit_style)
        # 设置日历弹窗样式
        start_calendar = self._start_date.calendarWidget()
        if start_calendar:
            start_calendar.setStyleSheet(calendar_style)
        self._start_date.dateChanged.connect(self._on_custom_date_changed)
        custom_layout.addWidget(self._start_date)
        
        # 分隔符
        separator = QLabel("至")
        separator.setStyleSheet(f"color: {THEME_COLORS['text_sub']}; font-size: 12px;")
        custom_layout.addWidget(separator)
        
        # 结束日期
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setStyleSheet(date_edit_style)
        # 设置日历弹窗样式
        end_calendar = self._end_date.calendarWidget()
        if end_calendar:
            end_calendar.setStyleSheet(calendar_style)
        self._end_date.dateChanged.connect(self._on_custom_date_changed)
        custom_layout.addWidget(self._end_date)
        
        self._custom_container.setVisible(False)
        layout.addWidget(self._custom_container)
        
        layout.addStretch()
    
    def _update_button_styles(self):
        """更新所有按钮样式"""
        for key, btn in self._preset_buttons.items():
            is_active = key == self._current_preset
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {THEME_COLORS['primary']};
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 6px 14px;
                        font-family: {FONT_FAMILY};
                        font-size: 12px;
                        font-weight: 600;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {THEME_COLORS['bg_surface']};
                        color: {THEME_COLORS['text_main']};
                        border: 1px solid {THEME_COLORS['border_light']};
                        border-radius: 6px;
                        padding: 6px 14px;
                        font-family: {FONT_FAMILY};
                        font-size: 12px;
                    }}
                    QPushButton:hover {{
                        background: {THEME_COLORS['bg_app']};
                        color: {THEME_COLORS['primary']};
                        border-color: {THEME_COLORS['primary']};
                    }}
                """)
    
    def _on_preset_clicked(self, preset_key: str):
        """预设按钮点击"""
        self._current_preset = preset_key
        self._update_button_styles()
        
        # 显示/隐藏自定义日期选择器
        is_custom = preset_key == "custom"
        self._custom_container.setVisible(is_custom)
        
        if is_custom:
            # 自定义模式，使用日期选择器的值
            self._emit_date_range()
        else:
            # 预设模式，计算日期范围
            start, end = calculate_date_preset(preset_key)
            self.dateRangeChanged.emit(start, end)
    
    def _on_custom_date_changed(self):
        """自定义日期变化"""
        if self._current_preset == "custom":
            self._emit_date_range()
    
    def _emit_date_range(self):
        """发送日期范围信号"""
        start = self._start_date.date().toString("yyyy-MM-dd")
        end = self._end_date.date().toString("yyyy-MM-dd")
        self.dateRangeChanged.emit(start, end)
    
    def get_date_range(self) -> tuple[str, str]:
        """获取当前日期范围
        
        Returns:
            (start_date, end_date) 元组
        """
        if self._current_preset == "custom":
            return (
                self._start_date.date().toString("yyyy-MM-dd"),
                self._end_date.date().toString("yyyy-MM-dd")
            )
        return calculate_date_preset(self._current_preset)


class RegulationSearchWindow(QWidget):
    """规章查询窗口 - 简洁卡片式 UI"""
    
    _instance: Optional["RegulationSearchWindow"] = None
    downloadCompleted = Signal(str)
    downloadFailed = Signal(str)
    
    # 颜色定义
    COLORS = THEME_COLORS
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self._config_manager = config_manager
        save_path = config_manager.config.regulation.get_save_path()
        
        self._service = RegulationService(save_path=save_path)
        self._service.searchFinished.connect(self._on_search_finished)
        self._service.searchError.connect(self._on_search_error)
        self._service.searchProgress.connect(self._on_search_progress)
        self._service.downloadProgress.connect(self._on_download_progress)
        self._service.downloadComplete.connect(self._on_download_complete)
        self._service.downloadError.connect(self._on_download_error)
        
        self._current_results: list[RegulationDocument] = []
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_search)
        
        # 搜索结果缓存：key = (keyword, doc_type, start_date, end_date), value = list[RegulationDocument]
        # 缓存搜索结果，避免切换文档类型时重复搜索
        self._search_cache: dict[tuple[str, str, str, str], list[RegulationDocument]] = {}
        self._last_search_keyword = ""  # 上次搜索的关键词
        self._last_search_date_range = ("", "")  # 上次搜索的日期范围
        
        # 批量下载管理器
        self._batch_manager = BatchDownloadManager(self._service)
        self._batch_manager.progressChanged.connect(self._on_batch_progress)
        self._batch_manager.documentCompleted.connect(self._on_batch_doc_completed)
        self._batch_manager.documentFailed.connect(self._on_batch_doc_failed)
        self._batch_manager.allCompleted.connect(self._on_batch_completed)
        
        # 选中的文档
        self._selected_documents: dict[str, RegulationDocument] = {}  # url -> document
        
        # 当前正在下载的按钮（用于恢复状态）
        self._current_download_btn: Optional[QPushButton] = None
        
        # 统计数据
        self._total_count = 0
        self._valid_count = 0
        self._invalid_count = 0
        
        # 当前筛选
        self._current_validity_filter = "all"
        self._current_doc_type = "normative"  # 默认只搜索规范性文件
        self._current_date_start = ""  # 日期筛选起始
        self._current_date_end = ""    # 日期筛选结束
        
        self._setup_ui()
        self._restore_window_state()

    @classmethod
    def show_and_activate(cls, config_manager: ConfigManager, parent=None):
        """显示并激活窗口（单例模式）"""
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(config_manager, parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("CAAC 规章查询")
        self.setMinimumSize(520, 620)
        self.resize(580, 720)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        self.setStyleSheet(f"QWidget {{ background-color: {THEME_COLORS['bg_app']}; font-family: {FONT_FAMILY}; }}")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 顶部蓝色渐变区域
        header = self._create_header()
        layout.addWidget(header)
        
        # 文档类型切换
        doc_type_bar = self._create_doc_type_bar()
        layout.addWidget(doc_type_bar)
        
        # 日期筛选
        date_filter_bar = self._create_date_filter()
        layout.addWidget(date_filter_bar)
        
        # 统计卡片
        stats_card = self._create_stats_card()
        layout.addWidget(stats_card)
        
        # 保存路径设置
        save_path_bar = self._create_save_path_bar()
        layout.addWidget(save_path_bar)
        
        # 操作栏：状态提示 + 批量下载按钮
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(20, 10, 20, 0)
        
        self._status_label = QLabel("输入关键词搜索规章或规范性文件")
        self._status_label.setStyleSheet(f"color: {THEME_COLORS['text_sub']}; font-size: 13px;")
        self._status_label.setWordWrap(True)
        action_bar.addWidget(self._status_label, 1)
        
        # 搜索中的加载指示器（初始隐藏）
        self._loading_indicator = QLabel("⏳")
        self._loading_indicator.setStyleSheet(f"""
            font-size: 16px;
            color: {THEME_COLORS['primary']};
            padding: 0 8px;
        """)
        self._loading_indicator.setVisible(False)
        action_bar.addWidget(self._loading_indicator)
        
        # 批量下载按钮 - 移除 emoji，使用纯文字
        self._batch_download_btn = QPushButton("批量下载")
        self._batch_download_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._batch_download_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_COLORS['success']};
                color: white;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                font-weight: 600;
                padding: 8px 20px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['success_hover']};
            }}
            QPushButton:pressed {{
                background: #047857;
            }}
            QPushButton:disabled {{
                background: {THEME_COLORS['border_light']};
                color: {THEME_COLORS['text_hint']};
            }}
        """)
        self._batch_download_btn.clicked.connect(self._batch_download_selected)
        self._batch_download_btn.setVisible(False)  # 初始隐藏，有选中时显示
        action_bar.addWidget(self._batch_download_btn)
        
        layout.addLayout(action_bar)
        
        # 结果列表区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setSpacing(12)
        self._results_layout.setContentsMargins(16, 8, 16, 16)
        self._results_layout.addStretch()
        
        scroll_area.setWidget(self._results_container)
        layout.addWidget(scroll_area, 1)
    
    def _create_header(self) -> QWidget:
        """创建顶部区域 - 现代简洁风格
        
        设计理念：
        - 简洁的白色背景 + 精致阴影
        - 嵌入式搜索框设计
        - 清晰的视觉层次
        """
        header = QWidget()
        header.setFixedHeight(100)
        header.setStyleSheet(f"""
            QWidget {{
                background: {THEME_COLORS['bg_surface']};
                border-bottom: 1px solid {THEME_COLORS['border_light']};
            }}
        """)
        
        layout = QVBoxLayout(header)
        layout.setContentsMargins(24, 20, 24, 16)
        
        # 搜索框容器 - 嵌入式设计
        search_container = QFrame()
        search_container.setStyleSheet(f"""
            QFrame {{ 
                background: {THEME_COLORS['bg_input']}; 
                border-radius: 12px;
                border: 1px solid {THEME_COLORS['border_light']};
            }}
            QFrame:focus-within {{
                border: 1px solid {THEME_COLORS['border_focus']};
                background: {THEME_COLORS['bg_surface']};
            }}
        """)
        
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(16, 8, 8, 8)
        search_layout.setSpacing(12)
        
        # 搜索图标 - 使用 Unicode 符号替代 emoji
        search_icon = QLabel("⌕")
        search_icon.setStyleSheet(f"""
            font-size: 20px; 
            font-weight: 300;
            background: transparent; 
            color: {THEME_COLORS['text_hint']};
            padding-left: 2px;
        """)
        search_layout.addWidget(search_icon)
        
        # 搜索输入框
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索规章或规范性文件...")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{ 
                border: none; 
                background: transparent; 
                font-family: {FONT_FAMILY};
                font-size: 14px; 
                color: {THEME_COLORS['text_main']}; 
                padding: 6px 0;
                selection-background-color: {THEME_COLORS['primary_bg']};
            }}
            QLineEdit::placeholder {{ 
                color: {THEME_COLORS['text_hint']}; 
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_input_changed)
        self._search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self._search_input, 1)
        
        # 搜索按钮 - 更圆润的设计
        search_btn = QPushButton("搜索")
        search_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: {THEME_COLORS['primary']}; 
                color: white; 
                border: none; 
                border-radius: 8px; 
                padding: 10px 24px; 
                font-size: 13px; 
                font-weight: 600; 
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{ 
                background: {THEME_COLORS['primary_hover']}; 
            }}
            QPushButton:pressed {{
                background: #1E40AF;
            }}
        """)
        search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(search_btn)
        
        layout.addWidget(search_container)
        return header

    def _create_doc_type_bar(self) -> QWidget:
        """创建文档类型切换栏 - Pill 按钮组风格"""
        bar = QFrame()
        bar.setStyleSheet(f"QFrame {{ background: transparent; margin: 8px 20px 0 20px; }}")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 规范性文件按钮（默认选中）- 移除 emoji
        self._normative_btn = QPushButton("规范性文件")
        self._normative_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._normative_btn.setCheckable(True)
        self._normative_btn.setChecked(True)
        self._normative_btn.clicked.connect(lambda: self._on_doc_type_changed("normative"))
        layout.addWidget(self._normative_btn)
        
        # CCAR 规章按钮 - 移除 emoji
        self._regulation_btn = QPushButton("CCAR 规章")
        self._regulation_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._regulation_btn.setCheckable(True)
        self._regulation_btn.setChecked(False)
        self._regulation_btn.clicked.connect(lambda: self._on_doc_type_changed("regulation"))
        layout.addWidget(self._regulation_btn)
        
        # 全部按钮 - 移除 emoji
        self._all_type_btn = QPushButton("全部")
        self._all_type_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._all_type_btn.setCheckable(True)
        self._all_type_btn.setChecked(False)
        self._all_type_btn.clicked.connect(lambda: self._on_doc_type_changed("all"))
        layout.addWidget(self._all_type_btn)
        
        layout.addStretch()
        
        self._update_doc_type_buttons()
        return bar
    
    def _update_doc_type_buttons(self):
        """更新文档类型按钮样式 - Pill 风格"""
        active_style = f"""
            QPushButton {{ 
                background: {THEME_COLORS['primary']}; 
                color: white; 
                border: none; 
                border-radius: 6px; 
                padding: 8px 16px; 
                font-size: 13px; 
                font-weight: 600; 
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{ 
                background: {THEME_COLORS['primary_hover']}; 
            }}
        """
        inactive_style = f"""
            QPushButton {{ 
                background: {THEME_COLORS['bg_surface']}; 
                color: {THEME_COLORS['text_sub']}; 
                border: 1px solid {THEME_COLORS['border_light']}; 
                border-radius: 6px; 
                padding: 8px 16px; 
                font-size: 13px; 
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{ 
                background: {THEME_COLORS['primary_bg']}; 
                color: {THEME_COLORS['primary']};
                border-color: {THEME_COLORS['primary']};
            }}
        """
        
        self._normative_btn.setChecked(self._current_doc_type == "normative")
        self._regulation_btn.setChecked(self._current_doc_type == "regulation")
        self._all_type_btn.setChecked(self._current_doc_type == "all")
        
        self._normative_btn.setStyleSheet(active_style if self._current_doc_type == "normative" else inactive_style)
        self._regulation_btn.setStyleSheet(active_style if self._current_doc_type == "regulation" else inactive_style)
        self._all_type_btn.setStyleSheet(active_style if self._current_doc_type == "all" else inactive_style)
    
    def _on_doc_type_changed(self, doc_type: str):
        """文档类型切换
        
        使用缓存机制：如果缓存中有对应的搜索结果，直接使用缓存，不重新搜索。
        """
        if self._current_doc_type == doc_type:
            return  # 没有变化，不处理
        
        self._current_doc_type = doc_type
        self._update_doc_type_buttons()
        
        # 清空选中状态
        self._selected_documents.clear()
        self._batch_download_btn.setVisible(False)
        
        # 检查缓存（包含日期参数）
        keyword = self._search_input.text().strip()
        cache_key = (keyword, doc_type, self._current_date_start, self._current_date_end)
        
        if cache_key in self._search_cache:
            # 使用缓存的结果
            self._current_results = self._search_cache[cache_key]
            self._filter_and_display_results()
        elif doc_type == "all" and keyword == self._last_search_keyword and (self._current_date_start, self._current_date_end) == self._last_search_date_range:
            # "全部"模式：合并规范性文件和 CCAR 规章的缓存
            normative_key = (keyword, "normative", self._current_date_start, self._current_date_end)
            regulation_key = (keyword, "regulation", self._current_date_start, self._current_date_end)
            
            combined = []
            if normative_key in self._search_cache:
                combined.extend(self._search_cache[normative_key])
            if regulation_key in self._search_cache:
                combined.extend(self._search_cache[regulation_key])
            
            if combined:
                self._current_results = combined
                self._search_cache[cache_key] = combined  # 缓存合并结果
                self._filter_and_display_results()
            else:
                # 没有缓存，需要搜索
                self._reset_stats_to_zero()
                self._clear_results_list()
                if keyword or self._current_date_start or self._current_date_end:
                    self._do_search()
        else:
            # 没有缓存，需要搜索
            self._current_results = []
            self._reset_stats_to_zero()
            self._clear_results_list()
            
            if keyword or self._current_date_start or self._current_date_end:
                self._do_search()
    
    def _reset_stats_to_zero(self):
        """重置统计数字为 0"""
        self._total_count = 0
        self._valid_count = 0
        self._invalid_count = 0
        self._all_btn.setProperty("count", "0")
        self._valid_btn.setProperty("count", "0")
        self._invalid_btn.setProperty("count", "0")
        self._update_stat_button_style(self._all_btn)
        self._update_stat_button_style(self._valid_btn)
        self._update_stat_button_style(self._invalid_btn)
    
    def _create_date_filter(self) -> QWidget:
        """创建日期筛选区域
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 1.1, 1.2, 1.3
        """
        container = QFrame()
        container.setStyleSheet("QFrame { background: transparent; margin: 4px 16px 0 16px; }")
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 日期筛选组件
        self._date_filter = DateRangeFilter()
        self._date_filter.dateRangeChanged.connect(self._on_date_range_changed)
        layout.addWidget(self._date_filter)
        
        return container
    
    def _on_date_range_changed(self, start_date: str, end_date: str):
        """日期范围变化处理
        
        日期筛选现在是 API 级别的，当日期范围变化时需要重新搜索。
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 1.5
        """
        # 如果日期范围没有变化，不处理
        if start_date == self._current_date_start and end_date == self._current_date_end:
            return
        
        self._current_date_start = start_date
        self._current_date_end = end_date
        
        # 检查缓存
        keyword = self._search_input.text().strip()
        cache_key = (keyword, self._current_doc_type, start_date, end_date)
        
        if cache_key in self._search_cache:
            # 使用缓存的结果
            self._current_results = self._search_cache[cache_key]
            self._filter_and_display_results()
        elif keyword or start_date or end_date:
            # 有关键词或日期筛选，需要重新搜索
            self._do_search()
        elif self._current_results:
            # 切换到"全部"日期预设，且之前有搜索结果
            # 需要重新搜索以获取无日期限制的结果
            self._do_search(force=True)
    
    def _create_stats_card(self) -> QWidget:
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {THEME_COLORS['bg_surface']};
                border-radius: 10px;
                border: 1px solid {THEME_COLORS['border_light']};
                margin: 8px 16px;
            }}
        """)
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        self._all_btn = self._create_stat_button("全部", "0", True, "all")
        layout.addWidget(self._all_btn)
        
        self._valid_btn = self._create_stat_button("有效", "0", False, "valid")
        layout.addWidget(self._valid_btn)
        
        self._invalid_btn = self._create_stat_button("失效", "0", False, "invalid")
        layout.addWidget(self._invalid_btn)
        
        return card
    
    def _create_save_path_bar(self) -> QWidget:
        """创建保存路径设置栏"""
        container = QFrame()
        container.setStyleSheet(f"QFrame {{ background: transparent; margin: 4px 16px 0 16px; }}")
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 文件夹图标 - 使用文字替代 emoji
        folder_label = QLabel("保存位置")
        folder_label.setStyleSheet(f"""
            color: {THEME_COLORS['text_sub']}; 
            font-size: 13px; 
            font-weight: 600;
            background: transparent;
        """)
        layout.addWidget(folder_label)
        
        # 路径显示（支持文本省略）
        current_path = self._config_manager.config.regulation.get_save_path()
        self._save_path_label = QLabel(current_path)
        self._save_path_label.setStyleSheet(f"""
            color: {THEME_COLORS['text_main']};
            font-size: 13px;
            background: {THEME_COLORS['bg_surface']};
            border: 1px solid {THEME_COLORS['border_light']};
            border-radius: 6px;
            padding: 4px 10px;
        """)
        self._save_path_label.setToolTip(current_path)
        # 设置文本省略，避免路径过长撑开布局
        self._save_path_label.setMinimumWidth(100)
        self._save_path_label.setMaximumWidth(350)
        layout.addWidget(self._save_path_label, 1)
        
        # 选择按钮
        select_btn = QPushButton("选择")
        select_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        select_btn = QPushButton("选择")
        select_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        select_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_COLORS['bg_surface']};
                color: {THEME_COLORS['primary']};
                font-size: 12px;
                padding: 4px 12px;
                border: 1px solid {THEME_COLORS['primary']};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['primary']};
                color: white;
            }}
        """)
        select_btn.clicked.connect(self._on_select_save_path)
        layout.addWidget(select_btn)
        
        return container
    
    def _on_select_save_path(self):
        """选择保存路径"""
        current_path = self._config_manager.config.regulation.get_save_path()
        
        new_path = QFileDialog.getExistingDirectory(
            self,
            "选择保存位置",
            current_path,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if new_path:
            # 保存到配置
            self._config_manager.config.regulation.save_path = new_path
            self._config_manager.save()
            
            # 更新 UI
            self._save_path_label.setText(new_path)
            self._save_path_label.setToolTip(new_path)
            
            # 更新服务的保存路径
            self._service.set_save_path(new_path)
    
    def _create_stat_button(self, label: str, count: str, active: bool, filter_type: str) -> QPushButton:
        """创建统计按钮"""
        btn = QPushButton()
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setProperty("label", label)
        btn.setProperty("count", count)
        btn.setProperty("active", active)
        btn.setProperty("filter_type", filter_type)
        btn.setFixedHeight(56)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, ft=filter_type: self._on_validity_filter(ft))
        
        self._update_stat_button_style(btn)
        
        return btn
    
    def _update_stat_button_style(self, btn: QPushButton) -> None:
        """更新统计按钮样式"""
        label = btn.property("label") or ""
        count = btn.property("count") or "0"
        active = btn.property("active") or False
        
        if active:
            bg_color = THEME_COLORS['primary']
            text_color = "white"
            count_color = "white"
            border = "none"
        else:
            bg_color = THEME_COLORS['bg_app']
            text_color = THEME_COLORS['text_sub']
            count_color = THEME_COLORS['text_main']
            border = f"1px solid {THEME_COLORS['border_light']}"
        
        btn.setText(f"{label}\n{count}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: {count_color};
                font-size: 16px;
                font-family: {FONT_FAMILY};
                font-weight: bold;
                border: {border};
                border-radius: 8px;
                padding: 10px;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['primary'] if active else THEME_COLORS['border_light']};
            }}
        """)
    
    def _add_shadow(self, widget: QWidget, blur: int = 10, offset: int = 2, opacity: float = 0.1):
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, offset)
        shadow.setColor(QColor(0, 0, 0, int(255 * opacity)))
        widget.setGraphicsEffect(shadow)

    
    def _on_validity_filter(self, filter_type: str):
        """有效性筛选"""
        self._current_validity_filter = filter_type
        
        self._all_btn.setProperty("active", filter_type == "all")
        self._valid_btn.setProperty("active", filter_type == "valid")
        self._invalid_btn.setProperty("active", filter_type == "invalid")
        
        self._update_stat_button_style(self._all_btn)
        self._update_stat_button_style(self._valid_btn)
        self._update_stat_button_style(self._invalid_btn)
        
        self._filter_and_display_results()
    
    def _filter_and_display_results(self):
        """根据当前筛选条件显示结果
        
        日期筛选已在 API 层面完成，这里主要处理有效性筛选。
        本地日期筛选作为备用（如果 API 日期筛选不生效）。
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 1.5, 1.6, 1.7
        """
        # API 已经按日期筛选，这里的本地筛选作为备用
        # 如果 API 日期筛选生效，本地筛选不会过滤掉任何结果
        date_filtered = filter_documents_by_date(
            self._current_results,
            self._current_date_start,
            self._current_date_end
        )
        
        # 更新统计数字（基于日期筛选后的结果）
        self._update_stats_for_filtered(date_filtered)
        
        # 再按有效性筛选
        if self._current_validity_filter == "all":
            filtered = date_filtered
        elif self._current_validity_filter == "valid":
            filtered = [d for d in date_filtered if d.validity == "有效"]
        else:
            filtered = [d for d in date_filtered if d.validity in ("失效", "废止")]
        
        # 更新状态标签
        total = len(self._current_results)
        date_filtered_count = len(date_filtered)
        shown = len(filtered)
        
        if self._current_date_start or self._current_date_end:
            date_hint = self._get_date_hint()
            if total == 0:
                # API 返回 0 个结果，说明所选时间段内没有发布新文件
                self._set_normal_status(f"{date_hint} 内无新发布")
            elif shown < date_filtered_count:
                self._set_normal_status(f"显示 {shown}/{date_filtered_count} 个结果（{date_hint}）")
            else:
                self._set_normal_status(f"找到 {date_filtered_count} 个结果（{date_hint}）")
        else:
            self._set_normal_status(f"找到 {total} 个结果")
        
        # 传递日期筛选后的数量，用于显示更友好的提示
        self._update_results_list(filtered, date_filtered_count)
    
    def _update_stats_for_filtered(self, documents: List[RegulationDocument]):
        """更新统计数字（基于筛选后的文档列表）
        
        Args:
            documents: 日期筛选后的文档列表
        """
        total = len(documents)
        valid = sum(1 for d in documents if d.validity == "有效")
        invalid = sum(1 for d in documents if d.validity in ("失效", "废止"))
        
        self._all_btn.setProperty("count", str(total))
        self._valid_btn.setProperty("count", str(valid))
        self._invalid_btn.setProperty("count", str(invalid))
        
        self._update_stat_button_style(self._all_btn)
        self._update_stat_button_style(self._valid_btn)
        self._update_stat_button_style(self._invalid_btn)
    
    def _on_search_input_changed(self, text: str):
        """搜索输入变化（带防抖）"""
        self._debounce_timer.stop()
        
        # 关键词变化时清除缓存
        new_keyword = text.strip()
        if new_keyword != self._last_search_keyword:
            self._search_cache.clear()
        
        if new_keyword:
            self._debounce_timer.start(800)  # 800ms 防抖，避免中文输入时过早触发
    
    def _normalize_ccar_keyword(self, keyword: str) -> tuple:
        """规范化 CCAR 部号关键词
        
        如果输入是纯数字（如 121、91），自动转换为 CCAR-121、CCAR-91 格式，
        并自动切换到 CCAR 规章搜索模式。
        
        Args:
            keyword: 用户输入的关键词
            
        Returns:
            tuple: (规范化后的关键词, 建议的文档类型或None)
        """
        # 检查是否是纯数字（可能带有字母后缀如 121R8、91R2）
        if re.match(r'^\d+[A-Za-z]*\d*$', keyword):
            # 纯数字或数字+字母后缀，转换为 CCAR-xxx 格式
            return f"CCAR-{keyword}", "regulation"
        
        # 检查是否已经是 CCAR-xxx 格式（不区分大小写）
        if re.match(r'^ccar-?\d+', keyword, re.IGNORECASE):
            return keyword, "regulation"
        
        # 其他情况保持原样
        return keyword, None
    
    def _get_date_hint(self) -> str:
        """获取日期范围提示文本"""
        if self._current_date_start and self._current_date_end:
            return f"{self._current_date_start} 至 {self._current_date_end}"
        elif self._current_date_start:
            return f"{self._current_date_start} 之后"
        elif self._current_date_end:
            return f"{self._current_date_end} 之前"
        return "全部时间"
    
    def _set_loading_status(self, text: str):
        """设置加载中状态 - 更醒目的样式
        
        搜索/下载进行中时使用，让用户明确知道正在等待。
        """
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"""
            color: {THEME_COLORS['primary']};
            font-size: 14px;
            font-weight: 600;
            padding: 4px 0;
        """)
        self._loading_indicator.setVisible(True)
    
    def _set_normal_status(self, text: str):
        """设置普通状态 - 恢复默认样式"""
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {THEME_COLORS['text_sub']}; font-size: 13px;")
        self._loading_indicator.setVisible(False)
    
    def _do_search_without_keyword(self):
        """无关键词搜索 - 用于日期筛选场景
        
        直接将日期参数传递给 CAAC 官方 API，由服务端进行筛选。
        """
        # 搜索开始时清零统计数字
        self._reset_stats_to_zero()
        
        doc_type_names = {"all": "全部", "regulation": "CCAR 规章", "normative": "规范性文件"}
        date_hint = self._get_date_hint()
        
        self._set_loading_status(f"正在获取 {doc_type_names.get(self._current_doc_type, '')} ({date_hint})...")
        
        # 将日期参数传递给 API
        self._service.search(
            keyword="",
            doc_type=self._current_doc_type,
            validity="all",
            start_date=self._current_date_start,
            end_date=self._current_date_end
        )
    
    def _do_search(self, force: bool = False):
        """执行搜索
        
        Args:
            force: 是否强制搜索（即使无关键词和日期筛选）
        """
        keyword = self._search_input.text().strip()
        
        # 允许无关键词搜索（当有日期筛选或强制搜索时）
        if not keyword and not self._current_date_start and not self._current_date_end and not force:
            return
        
        # 智能识别 CCAR 部号
        if keyword:
            normalized_keyword, suggested_doc_type = self._normalize_ccar_keyword(keyword)
            
            # 如果识别为 CCAR 部号，自动切换到规章搜索
            if suggested_doc_type == "regulation" and self._current_doc_type != "regulation":
                self._current_doc_type = "regulation"
                self._update_doc_type_buttons()
        else:
            normalized_keyword = ""
        
        # 搜索开始时清零统计数字
        self._reset_stats_to_zero()
        
        # 记录本次搜索的关键词
        self._last_search_keyword = normalized_keyword
        
        doc_type_names = {"all": "全部", "regulation": "CCAR 规章", "normative": "规范性文件"}
        
        if keyword:
            display_keyword = normalized_keyword if normalized_keyword != keyword else keyword
            self._set_loading_status(f"正在搜索 {doc_type_names.get(self._current_doc_type, '')}：{display_keyword}...")
        else:
            # 无关键词时显示日期范围
            date_hint = self._get_date_hint()
            self._set_loading_status(f"正在获取 {doc_type_names.get(self._current_doc_type, '')} ({date_hint})...")
        
        # 将日期参数传递给 API
        self._service.search(
            keyword=normalized_keyword,
            doc_type=self._current_doc_type,
            validity="all",
            start_date=self._current_date_start,
            end_date=self._current_date_end
        )
    
    def _on_search_finished(self, documents: list):
        """搜索完成"""
        self._current_results = documents
        
        # 缓存搜索结果（包含日期参数）
        keyword = self._last_search_keyword
        cache_key = (keyword, self._current_doc_type, self._current_date_start, self._current_date_end)
        self._search_cache[cache_key] = documents
        
        # 记录本次搜索的日期范围
        self._last_search_date_range = (self._current_date_start, self._current_date_end)
        
        # 清空之前的选中状态
        self._selected_documents.clear()
        self._batch_download_btn.setVisible(False)
        
        # 保存原始统计（用于显示"共获取 X 个文件"）
        self._total_count = len(documents)
        self._valid_count = sum(1 for d in documents if d.validity == "有效")
        self._invalid_count = sum(1 for d in documents if d.validity in ("失效", "废止"))
        
        # 统计数字和结果列表都由 _filter_and_display_results 统一处理
        # 这样可以确保日期筛选后统计数字正确反映筛选结果
        self._filter_and_display_results()
    
    def _on_search_error(self, error_msg: str):
        """搜索错误"""
        self._set_normal_status(f"搜索失败: {error_msg}")
        QMessageBox.warning(self, "搜索失败", f"搜索出错：{error_msg}")
    
    def _on_search_progress(self, current: int, total: int, message: str):
        """搜索进度"""
        self._set_loading_status(message)

    
    def _clear_results_list(self) -> None:
        """清空结果列表"""
        # 清空现有结果（保留最后的 stretch）
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # 清理阴影效果，避免内存泄漏
                widget.setGraphicsEffect(None)
                widget.deleteLater()
    
    def _update_results_list(self, documents: List[RegulationDocument], total_before_date_filter: int = 0) -> None:
        """更新结果列表
        
        Args:
            documents: 筛选后的文档列表
            total_before_date_filter: 日期筛选前的文档数量，用于显示更友好的提示
        """
        # 清空现有结果
        self._clear_results_list()
        
        # 添加新结果
        for doc in documents:
            card = self._create_result_card(doc)
            self._results_layout.insertWidget(self._results_layout.count() - 1, card)
        
        # 如果没有结果，显示空状态
        if not documents:
            # 根据情况显示不同的提示
            if total_before_date_filter > 0 and (self._current_date_start or self._current_date_end):
                # 有搜索结果但日期筛选后为空 - 说明所选时间段内没有新发布
                date_hint = self._get_date_hint()
                empty_text = f"{date_hint} 内没有新发布的文件\n\n已获取 {total_before_date_filter} 个文件，但都不在此时间段内\n点击「全部」可查看所有文件"
            elif self._current_date_start or self._current_date_end:
                # 无关键词搜索，日期筛选后为空
                date_hint = self._get_date_hint()
                empty_text = f"{date_hint} 内没有新发布的文件\n\n点击「全部」可查看最新发布的文件"
            else:
                empty_text = "未找到匹配的规章"
            
            empty_label = QLabel(empty_text)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet(f"color: {THEME_COLORS['text_hint']}; font-size: 14px; padding: 40px 20px; line-height: 1.6; font-family: {FONT_FAMILY};")
            self._results_layout.insertWidget(0, empty_label)
    
    def _create_result_card(self, doc: RegulationDocument) -> QFrame:
        """创建结果卡片
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.1
        """
        card = QFrame()
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.setStyleSheet(f"""
            QFrame {{ 
                background: {THEME_COLORS['bg_surface']}; 
                border-radius: 10px; 
                border: 1px solid {THEME_COLORS['border_light']};
            }}
            QFrame:hover {{ 
                background: {THEME_COLORS['bg_surface']};
                border-color: {THEME_COLORS['primary']};
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        
        # 顶部：复选框和有效性标签
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        
        # 复选框
        checkbox = QCheckBox()
        checkbox.setStyleSheet(f"""
            QCheckBox {{
                spacing: 0px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {THEME_COLORS['border_light']};
                border-radius: 6px;
                background: {THEME_COLORS['bg_surface']};
            }}
            QCheckBox::indicator:checked {{
                background: {THEME_COLORS['primary']};
                border-color: {THEME_COLORS['primary']};
                image: url(checkbox_checked.png); /* 这里需确保有check图标，或者靠 PySide 默认行为，通常颜色够了 */
            }}
        """)
        checkbox.setProperty("doc_url", doc.url)
        checkbox.stateChanged.connect(lambda state, d=doc: self._on_card_checkbox_changed(d, state))
        # 恢复选中状态
        if doc.url in self._selected_documents:
            checkbox.setChecked(True)
        top_layout.addWidget(checkbox)
        
        # 有效性标签（仅在有值时显示）
        if doc.validity:
            validity_label = QLabel(doc.validity)
            if doc.validity == "有效":
                validity_color = THEME_COLORS['success']
                validity_bg = THEME_COLORS['success_bg']
            elif doc.validity in ("废止", "失效"):
                validity_color = THEME_COLORS['danger']
                validity_bg = THEME_COLORS['danger_bg']
            else:
                validity_color = THEME_COLORS['text_sub']
                validity_bg = THEME_COLORS['bg_app']
            
            validity_label.setStyleSheet(f"""
                background: {validity_bg}; color: {validity_color};
                font-size: 11px; font-weight: bold;
                padding: 3px 10px; border-radius: 6px;
            """)
            validity_label.setFixedHeight(20)
            top_layout.addWidget(validity_label)
        
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        # 标题
        title_label = QLabel(doc.title)
        title_label.setWordWrap(True)
        title_label = QLabel(doc.title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"""
            color: {THEME_COLORS['text_main']};
            font-size: 15px; font-weight: 600; font-family: {FONT_FAMILY};
            background: transparent;
        """)
        layout.addWidget(title_label)
        
        # 底部：文号、发布单位、发文日期
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(8)
        
        if doc.doc_number:
            doc_num_label = QLabel(doc.doc_number)
            doc_num_label = QLabel(doc.doc_number)
            doc_num_label.setStyleSheet(f"""
                background: {THEME_COLORS['primary_bg']};
                color: {THEME_COLORS['primary']};
                font-size: 12px; font-weight: 600;
                padding: 4px 8px; border-radius: 6px;
            """)
            meta_layout.addWidget(doc_num_label)
        
        if doc.office_unit:
            office_label = QLabel(doc.office_unit)
            office_label = QLabel(doc.office_unit)
            office_label.setStyleSheet(f"""
                background: {THEME_COLORS['bg_app']};
                color: {THEME_COLORS['text_sub']};
                font-size: 12px;
                padding: 4px 8px; border-radius: 6px;
            """)
            meta_layout.addWidget(office_label)
        
        # 发文日期（优先显示 publish_date，其次 sign_date）- 移除 emoji
        display_date = doc.publish_date or doc.sign_date
        if display_date:
            date_label = QLabel(display_date)
            date_label.setStyleSheet(f"""
                background: transparent;
                color: {THEME_COLORS['text_hint']};
                font-size: 12px;
                padding: 4px 6px;
            """)
            meta_layout.addWidget(date_label)
        
        meta_layout.addStretch()
        
        # 打开网页链接 - 移除 emoji
        open_link = QPushButton("打开网页")
        open_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_link.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {THEME_COLORS['primary']};
                font-size: 12px;
                font-family: {FONT_FAMILY};
                padding: 4px 8px;
                border: none;
            }}
            QPushButton:hover {{
                color: {THEME_COLORS['primary_hover']};
                text-decoration: underline;
            }}
        """)
        open_link.clicked.connect(lambda checked=False, d=doc: self._open_url(d.url))
        meta_layout.addWidget(open_link)
        
        # 下载按钮 - 点击后立即显示反馈
        download_btn = QPushButton("下载 PDF")
        download_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        download_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_COLORS['primary_bg']};
                color: {THEME_COLORS['primary']};
                font-size: 12px;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['primary']};
                color: white;
            }}
            QPushButton:disabled {{
                background: {THEME_COLORS['border_light']};
                color: {THEME_COLORS['text_hint']};
            }}
        """)
        download_btn.clicked.connect(lambda checked=False, d=doc, btn=download_btn: self._on_download_btn_clicked(d, btn))
        meta_layout.addWidget(download_btn)
        
        layout.addLayout(meta_layout)
        
        # 双击打开网页
        card.mouseDoubleClickEvent = lambda e, d=doc: self._open_url(d.url)
        
        return card
    
    def _on_card_checkbox_changed(self, doc: RegulationDocument, state: int):
        """卡片复选框状态变化
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.1
        """
        if state == Qt.CheckState.Checked.value:
            self._selected_documents[doc.url] = doc
        else:
            self._selected_documents.pop(doc.url, None)
        
        # 更新状态栏显示选中数量（使用普通样式）
        count = len(self._selected_documents)
        if count > 0:
            self._set_normal_status(f"已选择 {count} 个文档")
            self._batch_download_btn.setText(f"批量下载 ({count})")
            self._batch_download_btn.setVisible(True)
        else:
            self._set_normal_status(f"找到 {self._total_count} 个结果")
            self._batch_download_btn.setVisible(False)

    
    def _on_card_context_menu(self, card: QFrame, pos, doc: RegulationDocument):
        """卡片右键菜单
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.2
        """
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {THEME_COLORS['bg_surface']};
                border: 1px solid {THEME_COLORS['border_light']};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 20px;
                border-radius: 6px;
                color: {THEME_COLORS['text_main']};
            }}
            QMenu::item:selected {{
                background: {THEME_COLORS['primary_bg']};
                color: {THEME_COLORS['primary']};
            }}
        """)
        
        download_action = QAction("下载 PDF", self)
        download_action.triggered.connect(lambda: self._download_pdf(doc))
        menu.addAction(download_action)
        
        # 批量下载选项（当有选中的文档时显示）
        if len(self._selected_documents) > 0:
            batch_action = QAction(f"批量下载 ({len(self._selected_documents)} 个)", self)
            batch_action.triggered.connect(self._batch_download_selected)
            menu.addAction(batch_action)
        
        open_action = QAction("打开网页", self)
        open_action.triggered.connect(lambda: self._open_url(doc.url))
        menu.addAction(open_action)
        
        menu.exec(card.mapToGlobal(pos))
    
    def _batch_download_selected(self):
        """批量下载选中的文档
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.2, 7.3
        """
        if not self._selected_documents:
            QMessageBox.information(self, "提示", "请先选择要下载的文档")
            return
        
        documents = list(self._selected_documents.values())
        self._set_loading_status(f"开始批量下载 {len(documents)} 个文档...")
        self._batch_manager.start_batch_download(documents)
    
    def _on_batch_progress(self, current: int, total: int, message: str):
        """批量下载进度
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.4
        """
        self._set_loading_status(message)
    
    def _on_batch_doc_completed(self, title: str, file_path: str):
        """单个文档下载完成"""
        pass  # 可以在这里添加日志或通知
    
    def _on_batch_doc_failed(self, title: str, error_msg: str):
        """单个文档下载失败"""
        pass  # 可以在这里添加日志或通知
    
    def _on_batch_completed(self, success_count: int, fail_count: int):
        """批量下载完成
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 7.5
        """
        # 清空选中状态
        self._selected_documents.clear()
        self._batch_download_btn.setVisible(False)  # 隐藏批量下载按钮
        self._filter_and_display_results()  # 刷新列表以更新复选框状态
        
        if fail_count == 0:
            self._set_normal_status(f"批量下载完成，成功 {success_count} 个")
            QMessageBox.information(
                self, "下载完成",
                f"批量下载完成\n成功下载 {success_count} 个文件"
            )
        else:
            self._set_normal_status(f"批量下载完成，成功 {success_count} 个，失败 {fail_count} 个")
            QMessageBox.warning(
                self, "下载完成",
                f"批量下载完成\n成功: {success_count} 个\n失败: {fail_count} 个"
            )
    
    def _on_download_btn_clicked(self, doc: RegulationDocument, btn: QPushButton):
        """下载按钮点击处理 - 立即给用户反馈
        
        点击后立即禁用按钮并显示"正在下载..."，防止重复点击。
        """
        # 立即禁用按钮并更新文字
        btn.setEnabled(False)
        btn.setText("下载中...")
        
        # 保存按钮引用，下载完成后恢复
        self._current_download_btn = btn
        
        # 开始下载
        self._download_pdf(doc)
    
    def _download_pdf(self, doc: RegulationDocument):
        """下载 PDF"""
        self._set_loading_status(f"正在下载: {doc.title}...")
        self._service.download_pdf(doc)
    
    def _on_download_progress(self, current: int, total: int, message: str):
        """下载进度
        
        Feature: caac-regulation-download-enhancement
        Validates: Requirements 6.1, 6.2
        """
        if message:
            self._set_loading_status(message)
        elif total > 0:
            percent = int(current / total * 100)
            self._set_loading_status(f"正在下载... {percent}%")
    
    def _on_download_complete(self, file_path: str):
        """下载完成"""
        self._set_normal_status(f"下载完成: {file_path}")
        self._restore_download_btn()
        self.downloadCompleted.emit(file_path)
        if self.isVisible():
            QMessageBox.information(self, "下载完成", f"文件已保存至：\n{file_path}")
    
    def _on_download_error(self, error_msg: str):
        """下载失败"""
        self._set_normal_status(f"下载失败: {error_msg}")
        self._restore_download_btn()
        self.downloadFailed.emit(error_msg)
        QMessageBox.warning(self, "下载失败", f"下载出错：{error_msg}")
    
    def _restore_download_btn(self):
        """恢复下载按钮状态"""
        if self._current_download_btn:
            self._current_download_btn.setEnabled(True)
            self._current_download_btn.setText("下载 PDF")
            self._current_download_btn = None
            self._current_download_btn = None
    
    def _open_url(self, url: str) -> None:
        """打开网页"""
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开浏览器：{e}")
    
    def _restore_window_state(self):
        """恢复窗口状态"""
        reg_config = self._config_manager.config.regulation
        if reg_config.window_width > 0 and reg_config.window_height > 0:
            self.setGeometry(
                reg_config.window_x, reg_config.window_y,
                reg_config.window_width, reg_config.window_height
            )
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 保存窗口状态
        reg_config = self._config_manager.config.regulation
        geometry = self.geometry()
        reg_config.window_x = geometry.x()
        reg_config.window_y = geometry.y()
        reg_config.window_width = geometry.width()
        reg_config.window_height = geometry.height()
        
        self._config_manager.save()
        
        # 清理资源
        self._debounce_timer.stop()
        self._service.cleanup()
        RegulationSearchWindow._instance = None
        
        super().closeEvent(event)
