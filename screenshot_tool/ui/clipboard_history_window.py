# -*- coding: utf-8 -*-
"""
工作台窗口 - Flat Design 风格

基于 UI/UX Pro Max 设计规范:
- 配色: Productivity Tool (#3B82F6 Primary, #F8FAFC Background)
- 风格: Flat Design + Micro-interactions
- 字体: Segoe UI / Microsoft YaHei UI

Feature: clipboard-history, extreme-performance-optimization
Requirements: 11.1, 11.4, 11.8

性能优化（extreme-performance-optimization）：
- 使用 QListView + QAbstractListModel + QStyledItemDelegate 替代 QListWidget
- 只有可见项才会触发绘制（虚拟滚动）
- setUniformItemSizes(True) 避免计算每项几何
- 比 QListWidget 快 4 倍以上
"""

from datetime import datetime
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListView, QTextEdit, QLabel,
    QLineEdit, QPushButton, QMenu, QMessageBox,
    QStackedWidget, QFrame, QScrollArea,
    QApplication, QInputDialog, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent, QObject, QModelIndex
from PySide6.QtGui import QPixmap, QKeyEvent, QAction, QImage

# 高性能历史列表组件（Feature: extreme-performance-optimization）
from screenshot_tool.ui.history_list_model import HistoryListModel
from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
from screenshot_tool.core.history_item_data import HistoryItemData

# 延迟历史更新管理器（Feature: extreme-performance-optimization, Requirements: 11.9, 12.4）
from screenshot_tool.core.deferred_history_update import DeferredHistoryUpdate

# 保存工具栏（Feature: workbench-temporary-preview-python, Requirements: 5.1, 5.2）
from screenshot_tool.ui.save_toolbar import SaveToolbar

try:
    from screenshot_tool.core.clipboard_history_manager import (
        ClipboardHistoryManager, HistoryItem, ContentType
    )
except ImportError:
    class ContentType:
        TEXT = "text"
        IMAGE = "image"
    
    class HistoryItem:
        def __init__(self, _id, content, ctype, pinned=False):
            self.id = _id
            self.text_content = content
            self.preview_text = content
            self.content_type = ctype
            self.is_pinned = pinned
            self.timestamp = datetime.now()
            self.image_path = None

    class ClipboardHistoryManager:
        pass


# UI/UX Pro Max 配色 (Productivity Tool)
COLORS = {
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "primary_light": "#EFF6FF",
    "bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "text": "#1E293B",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    "border": "#E2E8F0",
    "danger": "#EF4444",
    "tag_pin_bg": "#FEF3C7",
    "tag_pin_text": "#D97706",
}

FONT = '"Segoe UI", "Microsoft YaHei UI", system-ui, sans-serif'


STYLESHEET = f"""
QWidget {{
    font-family: {FONT};
    color: {COLORS["text"]};
}}
QWidget#mainWindow {{
    background-color: {COLORS["bg"]};
}}
QLineEdit#searchBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}}
QLineEdit#searchBox:focus {{
    border-color: {COLORS["primary"]};
}}
QLineEdit#searchBox::placeholder {{
    color: {COLORS["text_muted"]};
}}
QPushButton {{
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    background-color: transparent;
    color: {COLORS["text_secondary"]};
}}
QPushButton:hover {{
    background-color: {COLORS["primary_light"]};
    color: {COLORS["primary"]};
}}
QPushButton#dangerBtn:hover {{
    background-color: #FEF2F2;
    color: {COLORS["danger"]};
}}
QFrame#card {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
}}
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    background-color: transparent;
    border-radius: 8px;
    margin: 2px 4px;
}}
QListWidget::item:hover {{
    background-color: {COLORS["bg"]};
}}
QListWidget::item:selected {{
    background-color: {COLORS["primary_light"]};
}}
QTextEdit#preview {{
    background-color: transparent;
    border: none;
    padding: 20px;
    font-size: 14px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["text_muted"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: none;
}}
QMenu {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 20px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLORS["primary"]};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {COLORS["border"]};
    margin: 4px 8px;
}}
QLabel#hint {{
    color: {COLORS["text_muted"]};
    font-size: 12px;
}}
QLabel#empty {{
    color: {COLORS["text_muted"]};
    font-size: 14px;
}}
QListView {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px;
}}
"""


def _convert_history_item_to_data(item: HistoryItem) -> HistoryItemData:
    """将 HistoryItem 转换为 HistoryItemData
    
    Feature: extreme-performance-optimization
    Requirements: 11.1
    
    Args:
        item: ClipboardHistoryManager 的 HistoryItem 对象
        
    Returns:
        HistoryItemData 纯数据对象
    """
    # 格式化时间戳
    now = datetime.now()
    dt = item.timestamp
    if dt.date() == now.date():
        time_str = dt.strftime("%H:%M")
    elif dt.year == now.year:
        time_str = dt.strftime("%m-%d %H:%M")
    else:
        time_str = dt.strftime("%Y-%m-%d")
    
    # 优先显示自定义名称，如果没有则显示预览文本
    if hasattr(item, 'custom_name') and item.custom_name:
        display_text = item.custom_name
    else:
        display_text = item.preview_text.replace('\n', ' ')
    
    if len(display_text) > 40:
        display_text = display_text[:40] + "..."
    if not display_text.strip():
        display_text = "(空内容)"
    
    # 检查是否有标注
    has_annotations = item.has_annotations() if hasattr(item, 'has_annotations') else False
    
    # 获取内容类型字符串
    content_type_str = "image" if item.content_type == ContentType.IMAGE else "text"
    
    return HistoryItemData(
        id=item.id,
        preview_text=display_text,
        timestamp=time_str,
        is_pinned=item.is_pinned,
        has_annotations=has_annotations,
        thumbnail_path=item.image_path if content_type_str == "image" else None,
        content_type=content_type_str
    )



class ClipboardHistoryWindow(QWidget):
    """工作台窗口
    
    Feature: screenshot-state-restore, clipboard-ocr-merge, workbench-temporary-preview-python
    Requirements: 4.1, 4.2, 4.3, 4.4, 1.1, 2.1
    
    性能优化：
    - 编辑区获得焦点时暂停剪贴板监听，避免 Ctrl+X/C/V 触发信号循环
    - 使用 500ms 防抖延迟保存，减少 IO 操作
    - textChanged 信号处理极简化，只重启定时器
    - OCR 预览面板延迟加载，首次点击"识别文字"时创建
    - 窗口可见且未最小化时暂停新增条目，避免列表刷新卡顿
    
    临时预览模式（Feature: workbench-temporary-preview-python）：
    - 截图确认后不立即写入历史数据库
    - 在工作台窗口显示临时预览
    - 用户确认保存或复制时才持久化
    """
    
    closed = Signal()
    
    # 新增信号（Feature: screenshot-state-restore, Requirements: 2.1, 3.1）
    edit_screenshot_requested = Signal(str)  # 请求编辑截图，参数为 item_id
    ding_screenshot_requested = Signal(str)  # 请求贴图，参数为 item_id
    
    # 临时预览模式信号（Feature: workbench-temporary-preview-python, Requirements: 1.1, 2.1）
    save_requested = Signal()  # 保存请求
    discard_requested = Signal()  # 丢弃请求
    
    # 预览模式常量（Feature: clipboard-ocr-merge, Requirements: 1.1, 2.1）
    PREVIEW_INDEX_IMAGE = 0      # 图片预览（带 OCR 按钮）
    PREVIEW_INDEX_OCR = 1        # OCR 预览面板
    PREVIEW_INDEX_TEXT = 2       # 文本预览
    PREVIEW_INDEX_EMPTY = 3      # 空状态
    
    def __init__(self, manager: ClipboardHistoryManager, parent=None, skip_initial_refresh: bool = False):
        """初始化工作台窗口
        
        Args:
            manager: 剪贴板历史管理器
            parent: 父窗口
            skip_initial_refresh: 是否跳过初始刷新（预加载时使用，避免阻塞）
                                  Feature: workbench-lazy-refresh
        """
        super().__init__(parent)
        self._manager = manager
        self._search_text = ""
        self._updating_preview = False  # 防止循环触发
        self._needs_refresh = False  # 延迟刷新标志
        self._clipboard_paused = False  # 剪贴板监听暂停标志
        self._refresh_signal_connected = False  # 刷新信号是否已连接
        self._is_local_operation = False  # 是否正在执行本地操作（不需要刷新）
        self._initial_refresh_done = False  # 是否已完成首次刷新（Feature: workbench-lazy-refresh）
        
        # OCR 管理器（由外部注入）
        self._ocr_manager = None
        
        # 预览模式跟踪（Feature: clipboard-ocr-merge, Requirements: 2.1）
        self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
        
        # OCR 预览面板（延迟加载，Requirements: 10.1）
        self._ocr_preview_panel = None
        
        # 自动 OCR 标志（Feature: clipboard-ocr-merge, Requirements: 9.1, 9.2）
        self._auto_ocr_item_id: Optional[str] = None
        
        # 实时预览模式（截图选区时同步显示预览）
        self._is_live_preview_mode: bool = False
        self._live_preview_image: Optional[QImage] = None
        self._skip_show_refresh: bool = False  # 跳过 showEvent 中的刷新（实时预览模式用）
        
        # 临时预览模式（Feature: workbench-temporary-preview-python）
        # Requirements: 1.1, 1.2, 1.3
        # 截图确认后不立即写入历史，而是显示临时预览
        self._is_temporary_mode: bool = False  # 是否处于临时预览模式
        self._temporary_image: Optional[QImage] = None  # 临时图像
        self._temporary_id: str = ""  # 临时 ID (temp_timestamp)
        self._temporary_ocr_text: Optional[str] = None  # 临时 OCR 结果
        self._temporary_annotations: Optional[List[dict]] = None  # 临时标注数据
        
        # 文本编辑防抖定时器（500ms 延迟保存）
        self._text_save_timer = QTimer(self)
        self._text_save_timer.setSingleShot(True)
        self._text_save_timer.setInterval(500)
        self._text_save_timer.timeout.connect(self._do_save_text_edit)
        
        # 刷新防抖定时器（200ms 延迟刷新）
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._do_refresh)
        
        # 延迟历史更新管理器集成（Feature: extreme-performance-optimization）
        # Requirements: 11.9, 12.4
        self._deferred_update_manager = DeferredHistoryUpdate.instance()
        self._deferred_update_manager.register_resume_callback(self._on_deferred_updates_resumed)
        
        self._init_ui()
        self._connect_signals()
        
        # Feature: workbench-lazy-refresh
        # 预加载时跳过初始刷新，延迟到首次显示时执行
        # 这样可以避免预加载时阻塞主线程
        if not skip_initial_refresh:
            self._refresh(force=True)
            self._initial_refresh_done = True
        
        self._search_input.setFocus()
    
    def set_ocr_manager(self, ocr_manager) -> None:
        """设置 OCR 管理器
        
        Args:
            ocr_manager: OCRManager 实例
        """
        self._ocr_manager = ocr_manager
        # 如果 OCR 预览面板已创建，也更新它的管理器
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.set_ocr_manager(ocr_manager)
    
    def _init_ui(self):
        self.setWindowTitle("工作台")
        self.setObjectName("mainWindow")
        self.resize(900, 600)
        # 保存原始窗口标志，用于退出实时预览模式时恢复
        self._normal_window_flags = (
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setWindowFlags(self._normal_window_flags)
        self.setStyleSheet(STYLESHEET)
        
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)  # 紧凑边距
        main.setSpacing(8)  # 紧凑间距
        
        self._setup_toolbar(main)
        self._setup_content(main)
        
        # 底部提示栏已移除，用户可通过右键菜单查看操作
    
    def _setup_toolbar(self, layout: QVBoxLayout):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)  # 紧凑间距
        
        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchBox")
        self._search_input.setPlaceholderText("搜索历史记录...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedHeight(36)  # 稍微减小高度
        toolbar.addWidget(self._search_input, 1)
        
        self._new_note_btn = QPushButton("+ 新建便签")
        self._new_note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_note_btn.setFixedHeight(36)  # 稍微减小高度
        self._new_note_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS["primary"]};
                color: white;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS["primary_hover"]};
            }}
        """)
        toolbar.addWidget(self._new_note_btn)
        
        self._clear_btn = QPushButton("清空全部")
        self._clear_btn.setObjectName("dangerBtn")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFixedHeight(36)  # 稍微减小高度
        toolbar.addWidget(self._clear_btn)
        
        layout.addLayout(toolbar)
    
    def _setup_content(self, layout: QVBoxLayout):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        
        # 左侧列表（使用高性能 QListView + Model/View 架构）
        # Feature: extreme-performance-optimization
        # Requirements: 11.1, 11.4, 11.8
        list_card = QFrame()
        list_card.setObjectName("card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 4, 0, 4)  # 紧凑边距
        list_layout.setSpacing(0)
        
        # 创建高性能列表视图
        self._list = QListView()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        # 关键性能优化：统一项高度，避免计算每项几何
        # Requirements: 11.8
        self._list.setUniformItemSizes(True)
        
        # 设置模型和委托
        self._list_model = HistoryListModel(self)
        self._list_delegate = HistoryItemDelegate(self._list)
        self._list.setModel(self._list_model)
        self._list.setItemDelegate(self._list_delegate)
        
        list_layout.addWidget(self._list)
        
        self._empty_label = QLabel("暂无记录")
        self._empty_label.setObjectName("empty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        list_layout.addWidget(self._empty_label)
        
        # 右侧预览
        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        # 保存工具栏（Feature: workbench-temporary-preview-python）
        # Requirements: 5.1, 5.3, 5.4
        # Property 5: Toolbar Visibility Matches Mode
        # - WHILE in temporary mode, the save toolbar SHALL be visible
        # - WHEN exiting temporary mode, the save toolbar SHALL be hidden
        self._save_toolbar = SaveToolbar(self)
        self._save_toolbar.setVisible(False)  # 初始隐藏，进入临时模式时显示
        preview_layout.addWidget(self._save_toolbar)
        
        self._preview_stack = QStackedWidget()
        
        # 页面 0 (PREVIEW_INDEX_IMAGE): 图片预览（带"识别文字"按钮）
        # Feature: clipboard-ocr-merge, Requirements: 1.1, 2.1
        self._image_preview_page = QWidget()
        image_preview_layout = QVBoxLayout(self._image_preview_page)
        image_preview_layout.setContentsMargins(0, 0, 0, 0)
        image_preview_layout.setSpacing(0)
        
        self._image_scroll = QScrollArea()
        self._image_scroll.setStyleSheet("background: transparent; border: none;")
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_scroll.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._image_scroll.customContextMenuRequested.connect(self._show_preview_menu)
        
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: transparent;")
        self._image_scroll.setWidget(self._image_label)
        image_preview_layout.addWidget(self._image_scroll, 1)
        
        # "识别文字"按钮区域（Feature: clipboard-ocr-merge, Requirements: 1.1）
        ocr_btn_container = QWidget()
        ocr_btn_container.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS["surface"]};
                border-top: 1px solid {COLORS["border"]};
            }}
        """)
        ocr_btn_layout = QHBoxLayout(ocr_btn_container)
        ocr_btn_layout.setContentsMargins(16, 12, 16, 12)
        ocr_btn_layout.setSpacing(0)
        
        ocr_btn_layout.addStretch()
        
        self._ocr_btn = QPushButton("识字")
        self._ocr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ocr_btn.setFixedHeight(36)
        self._ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS["primary"]};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS["primary_hover"]};
            }}
            QPushButton:pressed {{
                background-color: #1D4ED8;
            }}
        """)
        self._ocr_btn.clicked.connect(self._on_ocr_btn_clicked)
        ocr_btn_layout.addWidget(self._ocr_btn)
        
        ocr_btn_layout.addStretch()
        
        image_preview_layout.addWidget(ocr_btn_container)
        
        self._preview_stack.addWidget(self._image_preview_page)  # index 0
        
        # 页面 1 (PREVIEW_INDEX_OCR): OCR 预览面板占位符
        # 实际的 OCRPreviewPanel 延迟加载（Requirements: 10.1）
        self._ocr_placeholder = QWidget()
        ocr_placeholder_layout = QVBoxLayout(self._ocr_placeholder)
        ocr_placeholder_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_stack.addWidget(self._ocr_placeholder)  # index 1
        
        # 页面 2 (PREVIEW_INDEX_TEXT): 文本预览
        self._text_preview = QTextEdit()
        self._text_preview.setObjectName("preview")
        self._text_preview.setReadOnly(False)  # 允许编辑
        self._text_preview.setPlaceholderText("选择条目查看内容")
        # 自定义中文右键菜单
        self._text_preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text_preview.customContextMenuRequested.connect(self._show_text_preview_menu)
        # 安装事件过滤器：控制剪贴板监听（性能优化核心）
        self._text_preview.installEventFilter(self)
        self._preview_stack.addWidget(self._text_preview)  # index 2
        
        # 页面 3 (PREVIEW_INDEX_EMPTY): 空状态
        empty_page = QWidget()
        el = QVBoxLayout(empty_page)
        et = QLabel("选择条目查看详情")
        et.setObjectName("empty")
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(et)
        self._preview_stack.addWidget(empty_page)  # index 3
        
        preview_layout.addWidget(self._preview_stack)
        
        splitter.addWidget(list_card)
        splitter.addWidget(preview_card)
        splitter.setSizes([350, 550])
        
        layout.addWidget(splitter, 1)
    
    def _connect_signals(self):
        self._search_input.textChanged.connect(self._on_search)
        # QListView 使用 selectionModel 的 currentChanged 信号
        self._list.selectionModel().currentChanged.connect(self._on_selection_changed_model)
        # 双击不再自动复制，改为只打开/预览（符合 Windows 标准交互）
        # 复制操作统一使用 Ctrl+C
        self._list.customContextMenuRequested.connect(self._show_menu)
        self._new_note_btn.clicked.connect(self._create_blank_note)
        self._clear_btn.clicked.connect(self._clear_all)
        # 初始时连接刷新信号
        self._connect_refresh_signal()
        # 文本编辑后自动保存
        self._text_preview.textChanged.connect(self._on_text_edited)
        
        # 保存工具栏信号连接（Feature: workbench-temporary-preview-python）
        # Requirements: 5.1, 5.3, 5.4
        self._save_toolbar.save_clicked.connect(self._on_save_toolbar_save)
        self._save_toolbar.copy_clicked.connect(self._on_save_toolbar_copy)
        self._save_toolbar.discard_clicked.connect(self._on_save_toolbar_discard)
    
    def _on_selection_changed_model(self, current: QModelIndex, previous: QModelIndex):
        """QListView 选择变更回调（Model/View 架构）
        
        Feature: extreme-performance-optimization, workbench-temporary-preview-python
        Requirements: 11.1, 11.4, 4.2, 4.4, 4.5
        
        切换选择时检查是否有未保存的临时图像（Requirements: 4.2）。
        如果有，显示确认对话框让用户选择保存、丢弃或取消。
        
        延迟加载优化：如果 _needs_refresh 为 True，在用户选择其他条目时
        触发完整的历史列表刷新。
        """
        # 延迟加载优化：用户点击其他条目时触发完整刷新
        if self._needs_refresh and current.isValid():
            # 记住当前选中的条目 ID
            current_item_data = self._list_model.get_item_at(current.row())
            current_item_id = current_item_data.id if current_item_data else None
            
            # 重要：先清除标志，避免 _refresh 内部触发 setCurrentIndex 时再次进入此分支导致递归
            # Bug fix: RecursionError when taking screenshot (2026-01-23)
            self._needs_refresh = False
            
            # 执行完整刷新
            self._refresh(force=True)
            
            # 恢复选中状态（阻塞信号，因为 _refresh 已经调用了 _on_selection_changed）
            if current_item_id:
                self._select_item_by_id(current_item_id, block_signals=True)
            return
        
        # 检查是否有未保存的更改（Requirements: 4.2）
        # 注意：在临时模式下，列表应该是禁用的，但这里作为安全检查
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "未保存的截图",
                "当前截图尚未保存，是否保存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save  # 默认选中保存
            )
            
            if reply == QMessageBox.StandardButton.Save:
                # 保存临时图像（Requirements: 4.4）
                self.confirm_and_save()
                # 继续执行选择变更
            elif reply == QMessageBox.StandardButton.Discard:
                # 丢弃临时图像（Requirements: 4.4）
                self.discard_temporary()
                # 继续执行选择变更
            else:
                # 取消选择变更（Requirements: 4.5）
                # 恢复到之前的选择（如果有的话）
                if previous.isValid():
                    # 阻止信号循环
                    self._list.selectionModel().blockSignals(True)
                    self._list.setCurrentIndex(previous)
                    self._list.selectionModel().blockSignals(False)
                return
        
        self._on_selection_changed()
    
    def _connect_refresh_signal(self):
        """连接刷新信号"""
        if not self._refresh_signal_connected:
            self._manager.history_changed.connect(self._on_history_changed)
            self._refresh_signal_connected = True
    
    def _disconnect_refresh_signal(self):
        """断开刷新信号（窗口可见时使用，避免自动刷新导致卡顿）"""
        if self._refresh_signal_connected:
            try:
                self._manager.history_changed.disconnect(self._on_history_changed)
            except RuntimeError:
                pass  # 信号可能已断开
            self._refresh_signal_connected = False
    
    def _on_history_changed(self):
        """历史记录变化回调（带防抖和延迟更新支持）
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        
        如果处于截图模式（延迟模式），将更新暂存；
        否则使用防抖定时器延迟刷新。
        """
        # 如果是本地操作触发的变化，跳过刷新（已经手动更新了UI）
        if self._is_local_operation:
            return
        
        # 检查是否处于延迟模式（截图期间）
        # Requirements: 11.9 - 截图期间延迟历史更新
        if self._deferred_update_manager.is_deferred:
            # 暂存刷新回调，截图完成后执行
            self._deferred_update_manager.queue_callback(self._do_refresh)
            return
        
        # 使用防抖定时器延迟刷新
        self._refresh_timer.start()
    
    def _on_deferred_updates_resumed(self, pending_count: int) -> None:
        """延迟更新恢复回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        
        截图完成后调用，如果有暂存的更新则刷新列表。
        
        Args:
            pending_count: 暂存的更新数量
        """
        if pending_count > 0 and self.isVisible():
            # 有暂存的更新且窗口可见，执行刷新
            self._refresh(force=False)
    
    def _do_refresh(self):
        """实际执行刷新（由防抖定时器触发）"""
        self._refresh(force=False)
    
    def _refresh(self, force: bool = False):
        """刷新历史列表
        
        Feature: extreme-performance-optimization
        Requirements: 11.1, 11.4, 11.8
        
        使用 HistoryListModel 进行高性能刷新。
        
        Args:
            force: 强制刷新，忽略可见性检查（用于初始化）
        """
        # 窗口不可见时跳过刷新，避免不必要的 UI 操作导致卡顿
        # 但 force=True 时强制执行（用于初始化）
        if not force and not self.isVisible():
            self._needs_refresh = True  # 标记需要刷新，下次显示时执行
            return
        
        # 记住当前选中项的 ID
        selected_id = self._get_current_item_id()
        
        # 清空模型
        self._list_model.clear_all()
        
        items = self._manager.search(self._search_text) if self._search_text else self._manager.get_history()
        
        if not items:
            self._list.hide()
            self._empty_label.show()
            self._empty_label.setText(f'未找到 "{self._search_text}"' if self._search_text else "暂无记录")
            self._ocr_btn.hide()  # 空列表时隐藏 OCR 按钮（Requirements: 1.2）
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_EMPTY)
            self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
            return
        
        self._empty_label.hide()
        self._list.show()
        
        # 转换并添加所有条目到模型
        restore_row = 0
        for i, item in enumerate(items):
            item_data = _convert_history_item_to_data(item)
            self._list_model.add_item(item_data)
            # 找到之前选中的项
            if item.id == selected_id:
                restore_row = i
        
        # 强制立即执行插入（不等待防抖）
        self._list_model.force_flush()
        
        # 加载缩略图（后台加载）
        self._load_thumbnails_async(items)
        
        # 恢复选中项
        # 阻止信号循环：setCurrentIndex 会触发 selectionChanged 信号
        # Bug fix: RecursionError when taking screenshot (2026-01-23)
        if self._list_model.rowCount() > 0:
            self._list.selectionModel().blockSignals(True)
            index = self._list_model.index(restore_row, 0)
            self._list.setCurrentIndex(index)
            self._list.selectionModel().blockSignals(False)
            # 手动触发选择变更处理（因为信号被阻塞了）
            self._on_selection_changed()
    
    def _load_thumbnails_async(self, items: List[HistoryItem]):
        """异步加载缩略图
        
        Feature: extreme-performance-optimization
        Requirements: 11.5, 11.7
        
        在后台加载缩略图，避免阻塞主线程。
        
        Bug fix (2026-01-23): 加载完成后必须触发视图更新，
        否则缩略图不会显示（只显示占位符）。
        """
        import os
        try:
            from screenshot_tool.core.clipboard_history_manager import get_clipboard_data_dir
            data_dir = get_clipboard_data_dir()
        except ImportError:
            return
        
        loaded_count = 0
        for item in items:
            if item.content_type == ContentType.IMAGE and item.image_path:
                # 检查是否已缓存
                if self._list_delegate.has_thumbnail(item.image_path):
                    continue
                
                # 同步加载缩略图（简化实现，后续可改为后台线程）
                full_path = os.path.join(data_dir, item.image_path)
                if os.path.exists(full_path):
                    pixmap = QPixmap(full_path)
                    if not pixmap.isNull():
                        # 缩放到缩略图大小（高清缩略图）
                        thumb_size = HistoryItemDelegate.THUMB_SIZE
                        scaled = pixmap.scaled(
                            thumb_size, thumb_size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self._list_delegate.set_thumbnail(item.image_path, scaled)
                        loaded_count += 1
        
        # Bug fix: 加载缩略图后必须触发视图重绘
        # 否则 delegate 的 paint() 方法不会被重新调用，缩略图不显示
        if loaded_count > 0:
            self._list.viewport().update()
    
    def _on_search(self, text: str):
        self._search_text = text.strip()
        self._refresh()
    
    def _on_selection_changed(self):
        """选择变更回调
        
        Feature: clipboard-ocr-merge, extreme-performance-optimization
        Requirements: 2.4, 9.3, 9.4, 11.1
        
        切换选中项前保存未完成的编辑，
        选择不同条目时重置预览模式到图片预览。
        
        自动 OCR 取消逻辑（Requirements: 9.3, 9.4）：
        - 如果用户手动选择了与 _auto_ocr_item_id 不同的条目，
          则取消自动 OCR 并清除标志
        
        修复：每次切换条目时都取消正在进行的 OCR，
        避免快速切换时多个 OCR 线程同时运行导致崩溃。
        """
        # 切换选中项前，保存未完成的编辑
        if self._text_save_timer.isActive():
            self._text_save_timer.stop()
            self._do_save_text_edit()
        
        # 获取当前选中的条目 ID（使用 Model/View 架构）
        current_item_id = self._get_current_item_id()
        
        # 自动 OCR 取消逻辑（Requirements: 9.3, 9.4）
        # 如果用户手动选择了与 _auto_ocr_item_id 不同的条目，取消自动 OCR
        if self._auto_ocr_item_id is not None:
            if current_item_id != self._auto_ocr_item_id:
                # 用户选择了不同的条目，取消自动 OCR
                self._auto_ocr_item_id = None
        
        # 每次切换条目时都取消正在进行的 OCR（修复快速切换崩溃问题）
        # 不管当前是什么模式，都要取消，因为自动 OCR 会在 _show_image_preview 中启动
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.cancel_ocr()
        
        if current_item_id:
            self._show_preview(current_item_id)
    
    def _show_preview(self, item_id: str):
        """显示预览内容
        
        Feature: clipboard-ocr-merge
        Requirements: 1.1, 1.2
        
        OCR 按钮可见性规则：
        - 选中图片条目时显示（Requirements: 1.1）
        - 选中文本条目时隐藏（Requirements: 1.2）
        - 无选中项时隐藏
        """
        item = self._manager.get_item(item_id)
        if not item:
            self._ocr_btn.hide()  # 无选中项时隐藏 OCR 按钮
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_EMPTY)
            self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
            return
        
        if item.content_type == ContentType.IMAGE:
            self._show_image_preview(item)
        else:
            # 文本条目时隐藏 OCR 按钮（Requirements: 1.2）
            self._ocr_btn.hide()
            self._updating_preview = True  # 防止触发 textChanged
            self._text_preview.setPlainText(item.text_content or "")
            self._updating_preview = False
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_TEXT)
            self._current_preview_mode = self.PREVIEW_INDEX_TEXT
    
    def _show_image_preview(self, item: HistoryItem):
        """显示图片预览 - 默认自动触发 OCR 识别
        
        Feature: clipboard-ocr-merge, auto-ocr-on-select
        Requirements: 1.1, 1.2, 2.1
        
        改进：选中图片时默认显示 OCR 识别结果，而不是图片预览。
        这样用户可以直接看到文字内容，无需手动点击"识别文字"按钮。
        
        如果图片加载失败，则显示错误信息。
        """
        import os
        from screenshot_tool.core.clipboard_history_manager import get_clipboard_data_dir
        
        if not item.image_path:
            self._ocr_btn.hide()
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_EMPTY)
            self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
            return
        
        full_path = os.path.join(get_clipboard_data_dir(), item.image_path)
        if not os.path.exists(full_path):
            self._ocr_btn.hide()
            self._image_label.setText("图片文件不存在")
            self._image_label.setStyleSheet(f"color: {COLORS['danger']};")
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_IMAGE)
            self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
            return
        
        # 图片文件存在，自动切换到 OCR 预览模式
        # 隐藏 OCR 按钮（因为已经自动触发 OCR）
        self._ocr_btn.hide()
        
        # 直接触发 OCR 识别，显示文字结果
        # 注意：_switch_to_ocr_preview 内部会加载图片并处理加载失败的情况
        self._switch_to_ocr_preview()
    
    def _on_text_edited(self):
        """文本编辑后延迟保存到历史记录（防抖优化）
        
        使用 500ms 防抖，避免每次按键都触发保存操作。
        极致性能优化：只做最小必要操作，不访问任何数据。
        """
        if self._updating_preview:
            return
        
        # 极简处理：只重启定时器，不做任何其他操作
        # 所有数据访问延迟到 _do_save_text_edit 中执行
        self._text_save_timer.start()
    
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """事件过滤器：处理文本预览区的焦点事件
        
        这是性能优化的核心：用户在编辑区进行 Ctrl+X/C/V 操作时，
        完全暂停剪贴板监听，避免信号循环导致 UI 卡顿。
        
        Args:
            obj: 事件源对象
            event: 事件对象
            
        Returns:
            是否拦截事件（False 表示继续传递）
        """
        if obj is self._text_preview:
            if event.type() == QEvent.Type.FocusIn:
                # 完全暂停剪贴板监听（最彻底的方案）
                if not self._clipboard_paused:
                    self._manager.stop_monitoring()
                    self._clipboard_paused = True
            elif event.type() == QEvent.Type.FocusOut:
                # 恢复剪贴板监听
                if self._clipboard_paused:
                    self._manager.start_monitoring()
                    self._clipboard_paused = False
                # 如果有未保存的编辑，立即保存
                if self._text_save_timer.isActive():
                    self._text_save_timer.stop()
                    self._do_save_text_edit()
        
        return super().eventFilter(obj, event)
    
    def _do_save_text_edit(self):
        """实际执行文本保存（由防抖定时器触发）
        
        在定时器触发时才获取当前选中项和文本内容，
        避免在每次按键时访问数据。
        """
        # 获取当前选中项 ID
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item or item.content_type == ContentType.IMAGE:
            return
        
        # 更新文本内容
        new_text = self._text_preview.toPlainText()
        if item.text_content != new_text:
            item.text_content = new_text
            item.preview_text = HistoryItem.generate_preview(new_text)
            self._manager.save()
    
    def _get_current_item_id(self) -> Optional[str]:
        """获取当前选中项的 ID
        
        Feature: extreme-performance-optimization
        Requirements: 11.1
        
        Returns:
            当前选中项的 ID，无选中项时返回 None
        """
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        
        item_data = self._list_model.get_item_at(index.row())
        return item_data.id if item_data else None
    
    def _get_current_item_data(self) -> Optional[HistoryItemData]:
        """获取当前选中项的数据
        
        Feature: extreme-performance-optimization
        Requirements: 11.1
        
        Returns:
            当前选中项的 HistoryItemData，无选中项时返回 None
        """
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        
        return self._list_model.get_item_at(index.row())
    
    # ========== 截图工作台方法 ==========
    
    def open_and_select_item(
        self,
        item_id: str,
        compact_mode: bool = False,
        auto_ocr: bool = False,
        skip_history_load: bool = False
    ) -> None:
        """打开工作台并选中指定条目
        
        截图确认后调用此方法，打开工作台并选中刚添加的截图条目。
        工作台行为与主界面一致，用户可以自由选择历史记录中的其他条目。
        
        性能优化：当 skip_history_load=True 时，跳过历史列表的完整加载，
        只添加当前截图条目到列表中。其他历史内容在用户首次滚动或点击时才加载。
        
        Args:
            item_id: 要选中的历史记录条目 ID
            compact_mode: 是否使用紧凑模式（较小的窗口尺寸）
            auto_ocr: 是否自动触发 OCR 识别
            skip_history_load: 是否跳过历史列表加载（性能优化）
        """
        # 1. 设置窗口尺寸
        if compact_mode:
            # 截图时使用较小的窗口尺寸 (700x500)
            self.resize(700, 500)
        
        # 2. 加载历史列表
        if skip_history_load:
            # 性能优化：只添加当前截图到列表，不加载完整历史
            self._add_single_item_to_list(item_id)
            # 标记需要延迟刷新（用户滚动或点击其他区域时触发）
            self._needs_refresh = True
        else:
            # 完整刷新历史列表
            self._refresh(force=True)
        
        # 3. 选中指定条目
        self._select_item_by_id(item_id)
        
        # 4. 显示窗口
        # Bug fix (2026-01-23): 如果窗口最小化，show() 不会恢复窗口
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.activateWindow()
        self.raise_()
        
        # 5. 自动触发 OCR（如果请求）
        if auto_ocr:
            # 使用 QTimer.singleShot 延迟触发，确保窗口完全显示后再执行 OCR
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._trigger_auto_ocr_for_current)
    
    def _add_single_item_to_list(self, item_id: str) -> None:
        """只添加单个条目到列表（性能优化）
        
        截图时使用，避免加载完整历史列表。
        
        Args:
            item_id: 要添加的条目 ID
        """
        item = self._manager.get_item(item_id)
        if item is None:
            return
        
        # 清空当前列表
        self._list_model.clear_all()
        
        # 只添加这一个条目
        item_data = _convert_history_item_to_data(item)
        self._list_model.add_item(item_data)
        self._list_model.force_flush()
        
        # 加载缩略图
        if item.content_type == ContentType.IMAGE and item.image_path:
            self._load_thumbnails_async([item])
        
        # 显示列表，隐藏空标签
        self._empty_label.hide()
        self._list.show()
    
    def _trigger_auto_ocr_for_current(self) -> None:
        """为当前选中的条目触发自动 OCR
        
        检查当前选中的条目是否为图片类型，如果是则自动触发 OCR。
        """
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if item is None:
            return
        
        # 只对图片类型触发 OCR
        if item.content_type == ContentType.IMAGE:
            # 切换到 OCR 预览模式
            self._switch_to_ocr_preview()
    
    # ========== 临时预览模式方法 (Feature: workbench-temporary-preview-python) ==========
    
    def is_temporary_mode(self) -> bool:
        """检查是否处于临时预览模式
        
        Feature: workbench-temporary-preview-python
        Requirements: 1.1, 1.2, 1.3
        
        Returns:
            True 如果处于临时预览模式，否则 False
        """
        return self._is_temporary_mode
    
    def has_unsaved_changes(self) -> bool:
        """检查是否有未保存的更改
        
        Feature: workbench-temporary-preview-python
        Requirements: 1.1, 1.2, 1.3
        
        当处于临时预览模式且有临时图像时，表示有未保存的更改。
        
        Returns:
            True 如果有未保存的临时图像，否则 False
        """
        return self._is_temporary_mode and self._temporary_image is not None
    
    def open_with_temporary_image(
        self,
        image: QImage,
        annotations: Optional[List[dict]] = None,
        auto_ocr: bool = False
    ) -> None:
        """打开临时预览模式（或替换现有临时图像）
        
        Feature: workbench-temporary-preview-python
        Requirements: 1.1, 1.2, 1.3, 4.3
        
        截图确认后调用此方法，不写入历史数据库，而是在工作台显示临时预览。
        用户可以在临时预览模式下进行 OCR、编辑等操作，
        确认保存时才持久化到历史记录。
        
        Property 1: Temporary Mode Entry Preserves State
        - 工作台进入临时模式 (is_temporary_mode() == True)
        - 历史管理器不新增条目
        - 历史列表选择被清除
        
        Property 4: New Screenshot Replaces Without Prompt (Requirements 4.3)
        - 如果已经处于临时模式，新截图直接替换旧临时图像
        - 不显示确认对话框
        - 工作台保持在临时模式
        - 旧的 OCR 缓存被清除（新图像需要重新 OCR）
        - 生成新的临时 ID
        
        内存管理注意事项（基于 Google AI 搜索最佳实践）：
        - 使用 image.copy() 深拷贝，避免外部引用导致内存问题
        - 替换时旧的 QImage 会被 Python GC 自动回收
        - 不需要显式调用 deleteLater()，因为 QImage 不是 QObject
        
        Args:
            image: 截图图像（QImage）
            annotations: 标注数据列表（可选）
            auto_ocr: 是否自动触发 OCR 识别（默认 False）
        """
        if image is None or image.isNull():
            return
        
        # Property 4: New Screenshot Replaces Without Prompt (Requirements 4.3)
        # 如果已经处于临时模式，直接替换，不显示确认对话框
        # 这是设计决策：新截图总是替换旧的临时图像
        # 旧的 _temporary_image 会被 Python GC 自动回收
        
        # 1. 设置临时模式状态（如果已经是 True，保持不变）
        self._is_temporary_mode = True
        
        # 2. 存储临时图像（深拷贝避免外部修改）
        # 注意：旧的 _temporary_image 引用会被替换，Python GC 会自动回收
        self._temporary_image = image.copy()
        
        # 3. 生成新的临时 ID（每次新截图都生成新 ID）
        from datetime import datetime
        self._temporary_id = f"temp_{datetime.now().timestamp()}"
        
        # 4. 存储标注数据（替换旧的标注）
        if annotations:
            self._temporary_annotations = annotations.copy()
        else:
            self._temporary_annotations = None
        
        # 5. 清除临时 OCR 缓存（新图像需要重新 OCR）
        # Property 4 要求：新截图替换时清除旧的 OCR 结果
        self._temporary_ocr_text = None
        
        # 6. 清除历史列表选择
        self._list.clearSelection()
        
        # 7. 显示保存工具栏（Property 5: Toolbar Visibility Matches Mode）
        # Requirements: 5.1, 5.3 - 临时模式下显示工具栏并禁用历史列表选择
        self._update_save_toolbar_visibility()
        self._list.setEnabled(False)  # 禁用历史列表选择
        
        # 8. 显示临时图像预览
        self._show_temporary_image_preview()
        
        # 9. 显示窗口
        self.show()
        self.activateWindow()
        self.raise_()
        
        # 10. 自动触发 OCR（如果请求）
        # Feature: workbench-temporary-preview-python
        if auto_ocr:
            # 使用 QTimer.singleShot 延迟触发，确保窗口完全显示后再执行 OCR
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._trigger_temporary_ocr)
    
    def _show_temporary_image_preview(self) -> None:
        """显示临时图像预览
        
        Feature: workbench-temporary-preview-python
        Requirements: 1.2
        
        在预览区域显示临时图像。
        """
        if self._temporary_image is None or self._temporary_image.isNull():
            return
        
        from PySide6.QtGui import QPixmap
        
        pixmap = QPixmap.fromImage(self._temporary_image)
        if pixmap.isNull():
            return
        
        # 计算缩放尺寸
        dpr = self._image_label.devicePixelRatio()
        view_size = self._image_scroll.size()
        target_w = int((view_size.width() - 40) * dpr)
        target_h = int((view_size.height() - 40) * dpr)
        
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(dpr)
        self._image_label.setPixmap(scaled)
        
        # 显示 OCR 按钮（临时图像也可以进行 OCR）
        self._ocr_btn.show()
        
        # 切换到图片预览模式
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_IMAGE)
        self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
    
    def confirm_and_save(self) -> Optional[str]:
        """确认保存到历史
        
        Feature: workbench-temporary-preview-python
        Requirements: 2.1, 2.3, 2.4, 3.3, 6.2
        
        Property 2: Save Persists All Associated Data
        - 历史管理器包含新条目（带图像）
        - 保存的条目包含 OCR 缓存（如果有）
        - 保存的条目包含标注数据（如果有）
        - 工作台退出临时模式 (is_temporary_mode() == False)
        - 保存的条目在历史列表中被选中
        
        Returns:
            保存的条目 ID，失败返回 None
        """
        # 1. 检查是否处于临时模式且有临时图像
        if not self._is_temporary_mode or self._temporary_image is None:
            return None
        
        if self._temporary_image.isNull():
            return None
        
        try:
            # 2. 调用 manager.add_screenshot_item() 保存
            # Requirements: 2.1 - 保存临时图像到历史
            # Requirements: 3.3 - 持久化 OCR 缓存
            # Requirements: 6.2 - 持久化标注数据
            saved_id = self._manager.add_screenshot_item(
                image=self._temporary_image,
                annotations=self._temporary_annotations,
                ocr_cache=self._temporary_ocr_text,
            )
            
            if not saved_id:
                return None
            
            # 3. 清除临时状态（退出临时模式）
            # Requirements: 2.4 - 退出临时预览模式
            self._is_temporary_mode = False
            self._temporary_image = None
            self._temporary_id = ""
            self._temporary_ocr_text = None
            self._temporary_annotations = None
            
            # 4. 隐藏保存工具栏并恢复历史列表（Property 5: Toolbar Visibility Matches Mode）
            # Requirements: 5.4 - 退出临时模式时隐藏工具栏
            self._update_save_toolbar_visibility()
            self._list.setEnabled(True)  # 恢复历史列表选择
            
            # 5. 刷新历史列表以显示新条目
            # Requirements: 2.3 - 更新历史列表显示新条目
            self._refresh(force=True)
            
            # 6. 选中保存的条目
            # Requirements: 2.4 - 选中保存的条目
            self._select_item_by_id(saved_id)
            
            # 7. 发出保存请求信号
            self.save_requested.emit()
            
            # 8. 返回保存的条目 ID
            return saved_id
            
        except Exception as e:
            # 记录错误日志
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"保存临时截图失败: {e}")
            return None
    
    def discard_temporary(self) -> None:
        """丢弃临时条目
        
        Feature: workbench-temporary-preview-python
        Requirements: 2.5, 3.4, 6.3, 7.4
        
        Property 3: Discard Clears All Temporary Data
        - 工作台退出临时模式
        - 临时图像引用为 None
        - 临时 OCR 缓存为 None
        - 临时标注数据为 None
        - 历史管理器不新增任何条目
        
        此方法清除所有临时数据并退出临时模式，
        不会将任何数据写入历史记录。
        """
        # 1. 退出临时模式
        # Requirements: 2.5 - 退出临时预览模式
        self._is_temporary_mode = False
        
        # 2. 清除临时图像引用（释放内存）
        # Requirements: 7.4 - 退出临时模式时释放内存
        self._temporary_image = None
        
        # 3. 清除临时 ID
        self._temporary_id = ""
        
        # 4. 清除临时 OCR 缓存
        # Requirements: 3.4 - 丢弃时清除 OCR 缓存
        self._temporary_ocr_text = None
        
        # 5. 清除临时标注数据
        # Requirements: 6.3 - 丢弃时清除标注数据
        self._temporary_annotations = None
        
        # 6. 隐藏保存工具栏并恢复历史列表（Property 5: Toolbar Visibility Matches Mode）
        # Requirements: 5.4 - 退出临时模式时隐藏工具栏
        self._update_save_toolbar_visibility()
        self._list.setEnabled(True)  # 恢复历史列表选择
        
        # 7. 发出丢弃请求信号
        self.discard_requested.emit()
        
        # 8. 更新 UI 状态（切换到空状态或恢复正常模式）
        # 如果历史列表有条目，选中第一个；否则显示空状态
        if self._list_model.rowCount() > 0:
            # 选中第一个条目
            first_index = self._list_model.index(0, 0)
            self._list.setCurrentIndex(first_index)
            # _on_selection_changed 会自动更新预览
        else:
            # 显示空状态
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_EMPTY)
            self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
            self._ocr_btn.hide()
    
    # ========== 结束临时预览模式方法 ==========
    
    # ========== SaveToolbar 信号处理方法 (Feature: workbench-temporary-preview-python) ==========
    
    def _on_save_toolbar_save(self) -> None:
        """保存工具栏「保存」按钮点击处理
        
        Feature: workbench-temporary-preview-python
        Requirements: 5.1, 2.1
        
        调用 confirm_and_save() 保存临时图像到历史记录。
        """
        self.confirm_and_save()
    
    def _on_save_toolbar_copy(self) -> None:
        """保存工具栏「复制」按钮点击处理
        
        Feature: workbench-temporary-preview-python
        Requirements: 5.1, 2.2
        
        复制临时图像到剪贴板。
        """
        if self._is_temporary_mode and self._temporary_image is not None:
            from PySide6.QtGui import QGuiApplication
            clipboard = QGuiApplication.clipboard()
            clipboard.setImage(self._temporary_image)
    
    def _on_save_toolbar_discard(self) -> None:
        """保存工具栏「丢弃」按钮点击处理
        
        Feature: workbench-temporary-preview-python
        Requirements: 5.1, 2.5
        
        调用 discard_temporary() 丢弃临时图像。
        """
        self.discard_temporary()
    
    def _update_save_toolbar_visibility(self) -> None:
        """更新保存工具栏可见性
        
        Feature: workbench-temporary-preview-python
        Requirements: 5.1, 5.3, 5.4
        
        Property 5: Toolbar Visibility Matches Mode
        - WHILE in temporary mode, the save toolbar SHALL be visible
        - WHEN exiting temporary mode, the save toolbar SHALL be hidden
        """
        self._save_toolbar.setVisible(self._is_temporary_mode)
    
    # ========== 结束 SaveToolbar 信号处理方法 ==========
    
    def _copy_and_close(self):
        """双击复制并关闭
        
        对于带标注的截图，复制渲染后的图像（带标注）。
        
        Feature: screenshot-state-restore
        Requirements: 4.3
        """
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item:
            return
        
        # 如果是带标注的截图，复制渲染后的图像
        if item.content_type == ContentType.IMAGE and item.has_annotations():
            rendered_image = self._manager.render_screenshot_with_annotations(current_id)
            if rendered_image is not None:
                app = QApplication.instance()
                if app:
                    clipboard = app.clipboard()
                    clipboard.setImage(rendered_image)
                    self.close()
                    return
        
        # 其他情况使用默认复制
        if self._manager.copy_to_clipboard(current_id):
            self.close()
    
    def _on_ocr_btn_clicked(self):
        """识别文字按钮点击
        
        Feature: clipboard-ocr-merge
        Requirements: 1.1, 2.1
        
        点击后切换到 OCR 预览模式，触发 OCR 识别。
        """
        self._switch_to_ocr_preview()
    
    def _switch_to_ocr_preview(self):
        """切换到 OCR 预览模式
        
        Feature: clipboard-ocr-merge, background-ocr-cache
        Requirements: 2.1, 10.1
        
        延迟加载 OCRPreviewPanel（首次点击时创建），
        获取当前选中图片，启动 OCR 识别，切换到 OCR 预览页面。
        
        两级缓存读取策略：
        1. 检查 L1 内存缓存（OCRPreviewPanel._ocr_cache）
        2. 检查 L2 持久化缓存（HistoryItem.ocr_cache）
        3. 都没有则执行 OCR
        """
        # 获取当前选中的图片条目
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item or item.content_type != ContentType.IMAGE:
            return
        
        # 延迟加载 OCRPreviewPanel（Requirements: 10.1）
        if self._ocr_preview_panel is None:
            self._setup_ocr_preview_panel()
        
        # 获取图片
        image = self._get_item_image(item)
        if image is None or image.isNull():
            return
        
        # 两级缓存读取策略（Feature: background-ocr-cache）
        # 1. 检查 L1 内存缓存（OCRPreviewPanel 的会话缓存）
        if self._ocr_preview_panel.has_cached_result(current_id):
            # L1 命中，直接恢复
            self._ocr_preview_panel.restore_cached_result(current_id)
        # 2. 检查 L2 持久化缓存（HistoryItem 的 ocr_cache 字段）
        elif item.has_ocr_cache():
            # L2 命中，显示缓存结果并回填到 L1
            self._ocr_preview_panel.show_persistent_cache(
                current_id, 
                item.ocr_cache,
                "rapid"  # 后台 OCR 使用本地引擎
            )
        else:
            # 都没有，启动 OCR 识别
            self._ocr_preview_panel.start_ocr(image, current_id)
        
        # 切换到 OCR 预览页面
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_OCR)
        self._current_preview_mode = self.PREVIEW_INDEX_OCR
    
    def _switch_to_image_preview(self):
        """切换回图片预览模式
        
        Feature: clipboard-ocr-merge
        Requirements: 2.2, 2.3
        
        当用户点击"返回图片"按钮时调用，切换回图片预览页面。
        """
        # 取消正在进行的 OCR（如果有）
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.cancel_ocr()
        
        # 切换到图片预览页面
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_IMAGE)
        self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
    
    def open_with_auto_ocr(self, item_id: str):
        """打开窗口并自动对指定条目执行 OCR
        
        Feature: clipboard-ocr-merge
        Requirements: 9.1, 9.2
        
        Args:
            item_id: 要自动 OCR 的历史记录条目 ID
        """
        self._auto_ocr_item_id = item_id
        
        # 强制刷新列表，确保新添加的条目已显示
        self._refresh(force=True)
        
        self.show()
        self.activateWindow()
        self.raise_()
        
        # 选中该条目并自动触发 OCR
        if self._select_item_by_id(item_id):
            self._trigger_auto_ocr()
        else:
            # 如果未找到条目，清除自动 OCR 标志
            self._auto_ocr_item_id = None
    
    def enter_live_preview_mode(self):
        """进入实时预览模式（选区完成时调用）
        
        在截图选区确定后调用，打开窗口并进入 OCR 预览等待状态。
        此时列表显示历史记录，右侧显示 OCR 预览面板（等待截图）。
        
        关键改进（确保窗口置顶）：
        - 设置 WindowStaysOnTopHint 确保窗口显示在截图覆盖层上方
        - 调用 raise_() 强制提升到最前
        - 不调用 activateWindow()，让截图覆盖层保持焦点
        """
        import time
        from screenshot_tool.core.async_logger import async_debug_log
        
        start_time = time.perf_counter()
        async_debug_log("enter_live_preview_mode 开始", "LIVE-PREVIEW")
        
        # 确保 OCR 预览面板已创建
        if self._ocr_preview_panel is None:
            panel_start = time.perf_counter()
            self._setup_ocr_preview_panel()
            panel_ms = (time.perf_counter() - panel_start) * 1000
            async_debug_log(f"OCR 预览面板创建耗时: {panel_ms:.2f}ms", "LIVE-PREVIEW")
        
        # 设置 OCR 预览面板为等待状态
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.show_waiting_state()
        
        # 如果已经在实时预览模式且窗口可见，只需更新面板状态并确保置顶
        if self._is_live_preview_mode and self.isVisible():
            self.raise_()
            async_debug_log("已在实时预览模式，仅 raise", "LIVE-PREVIEW")
            return
        
        self._is_live_preview_mode = True
        self._live_preview_image = None
        
        # 取消正在进行的 OCR（如果有）
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.cancel_ocr()
        
        # 设置窗口置顶标志（确保显示在截图覆盖层上方）
        # Bug fix: 之前没有设置 WindowStaysOnTopHint，导致工作台被截图覆盖层遮挡
        topmost_flags = (
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlags(topmost_flags)
        
        # 显示窗口
        show_start = time.perf_counter()
        # 实时预览模式下跳过 showEvent 中的刷新（性能优化）
        # 历史列表会在退出实时预览模式后按需刷新
        self._skip_show_refresh = True
        self.show()
        show_ms = (time.perf_counter() - show_start) * 1000
        async_debug_log(f"窗口 show() 耗时: {show_ms:.2f}ms", "LIVE-PREVIEW")
        
        # 强制提升到最前
        self.raise_()
        # 不调用 activateWindow()，让截图覆盖层保持焦点
        
        # 取消列表选中状态，切换到 OCR 预览模式
        self._list.clearSelection()
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_OCR)
        self._current_preview_mode = self.PREVIEW_INDEX_OCR
        self._ocr_btn.hide()
        
        total_ms = (time.perf_counter() - start_time) * 1000
        async_debug_log(f"enter_live_preview_mode 完成，总耗时: {total_ms:.2f}ms", "LIVE-PREVIEW")
    
    def show_live_preview(self, image: QImage):
        """显示实时预览图片（选区完成时调用）
        
        在截图选区确定后调用，自动触发 OCR 识别。
        
        关键改进：
        - 不再切换到图片预览模式，始终保持 OCR 预览面板
        - 用户希望在截图时看到 OCR 结果，而不是图片预览
        
        Args:
            image: 截图图片
        """
        if image is None or image.isNull():
            return
        
        self._live_preview_image = image.copy()
        self._is_live_preview_mode = True
        
        # 取消列表选中状态
        self._list.clearSelection()
        
        # 直接触发 OCR，不切换到图片预览模式
        # 用户希望始终看到 OCR 预览面板
        self._trigger_live_ocr(image)
    
    def _show_live_image_preview(self, image: QImage):
        """显示实时预览图片
        
        Args:
            image: 要显示的图片
        """
        from PySide6.QtGui import QPixmap
        
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        
        dpr = self._image_label.devicePixelRatio()
        view_size = self._image_scroll.size()
        target_w = int((view_size.width() - 40) * dpr)
        target_h = int((view_size.height() - 40) * dpr)
        
        scaled = pixmap.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self._image_label.setPixmap(scaled)
        
        # 显示 OCR 按钮
        self._ocr_btn.show()
        
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_IMAGE)
        self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
    
    def _trigger_live_ocr(self, image: QImage):
        """触发实时预览的 OCR
        
        Args:
            image: 要识别的图片
        """
        # 确保 OCR 预览面板已创建
        if self._ocr_preview_panel is None:
            self._setup_ocr_preview_panel()
        
        if self._ocr_preview_panel is None:
            return
        
        # 使用临时 ID 开始 OCR（实时预览不需要缓存）
        live_preview_id = "_live_preview_temp"
        self._ocr_preview_panel.start_ocr(image, live_preview_id)
        
        # 切换到 OCR 预览模式
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_OCR)
        self._current_preview_mode = self.PREVIEW_INDEX_OCR
    
    def exit_live_preview_mode(self):
        """退出实时预览模式（截图取消或完成时调用）
        
        清除实时预览状态，隐藏窗口。
        
        关键改进：
        - 截图取消/完成时隐藏工作台窗口
        - 恢复正常窗口标志（移除置顶）
        - 下次打开时会重新设置置顶标志
        
        性能优化：
        - 如果之前跳过了刷新，使用 QTimer.singleShot 延迟执行，避免阻塞 UI
        """
        self._is_live_preview_mode = False
        self._live_preview_image = None
        
        # 取消正在进行的 OCR
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.cancel_ocr()
        
        # 隐藏窗口（截图取消/完成时工作台应该关闭）
        self.hide()
        
        # 恢复正常窗口标志（移除置顶）
        self.setWindowFlags(self._normal_window_flags)
        
        # 如果之前跳过了初始刷新，延迟执行（性能优化，避免阻塞 UI）
        if not self._initial_refresh_done:
            self._initial_refresh_done = True
            QTimer.singleShot(50, lambda: self._refresh(force=True))
        elif self._needs_refresh:
            self._needs_refresh = False
            QTimer.singleShot(50, self._refresh)
        
        # 恢复到空状态或选中第一项
        if self._list_model.rowCount() > 0:
            index = self._list_model.index(0, 0)
            self._list.setCurrentIndex(index)
        else:
            self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_EMPTY)
            self._current_preview_mode = self.PREVIEW_INDEX_EMPTY
    
    def _trigger_auto_ocr(self):
        """触发自动 OCR（仅对最新截图）
        
        Feature: clipboard-ocr-merge
        Requirements: 9.1, 9.2
        
        检查 _auto_ocr_item_id 标志，如果设置了则触发 OCR 识别，
        然后清除标志。
        """
        if self._auto_ocr_item_id:
            # 验证当前选中的条目是否是目标条目
            current_id = self._get_current_item_id()
            if current_id and current_id == self._auto_ocr_item_id:
                # 验证是图片条目
                item = self._manager.get_item(self._auto_ocr_item_id)
                if item and item.content_type == ContentType.IMAGE:
                    self._on_ocr_btn_clicked()
            # 清除标志
            self._auto_ocr_item_id = None
    
    def _trigger_temporary_ocr(self):
        """触发临时图像的 OCR 识别
        
        Feature: workbench-temporary-preview-python
        
        对临时预览模式下的图像执行 OCR 识别。
        OCR 结果存储在 _temporary_ocr_text 中，保存时会一并持久化。
        """
        if not self._is_temporary_mode or self._temporary_image is None:
            return
        
        if self._temporary_image.isNull():
            return
        
        # 延迟加载 OCRPreviewPanel
        if self._ocr_preview_panel is None:
            self._setup_ocr_preview_panel()
        
        # 再次检查（防止创建失败）
        if self._ocr_preview_panel is None:
            return
        
        # 使用临时 ID 作为缓存键
        temp_id = self._temporary_id or "temp_image"
        
        # 启动 OCR 识别
        self._ocr_preview_panel.start_ocr(self._temporary_image, temp_id)
        
        # 切换到 OCR 预览页面
        self._preview_stack.setCurrentIndex(self.PREVIEW_INDEX_OCR)
        self._current_preview_mode = self.PREVIEW_INDEX_OCR
    
    def _select_item_by_id(self, item_id: str, block_signals: bool = False) -> bool:
        """根据 ID 选中列表中的条目
        
        Feature: clipboard-ocr-merge, extreme-performance-optimization
        Requirements: 9.1, 11.1
        
        Args:
            item_id: 要选中的历史记录条目 ID
            block_signals: 是否阻塞信号（避免触发 selectionChanged）
            
        Returns:
            True 如果成功选中，False 如果未找到
        """
        # 使用 Model/View 架构查找条目
        for i in range(self._list_model.rowCount()):
            item_data = self._list_model.get_item_at(i)
            if item_data and item_data.id == item_id:
                index = self._list_model.index(i, 0)
                if block_signals:
                    self._list.selectionModel().blockSignals(True)
                self._list.setCurrentIndex(index)
                if block_signals:
                    self._list.selectionModel().blockSignals(False)
                return True
        return False
    
    def _setup_ocr_preview_panel(self):
        """设置 OCR 预览面板（延迟加载）
        
        Feature: clipboard-ocr-merge
        Requirements: 10.1
        
        首次点击"识别文字"按钮时创建 OCRPreviewPanel，
        并将其添加到预览堆栈的 OCR 占位符位置。
        """
        from screenshot_tool.ui.ocr_preview_panel import OCRPreviewPanel
        
        # 创建 OCR 预览面板
        self._ocr_preview_panel = OCRPreviewPanel(self)
        
        # 连接返回图片信号（Requirements: 2.2）
        self._ocr_preview_panel.back_to_image_requested.connect(self._switch_to_image_preview)
        
        # 设置 OCR 管理器（如果可用）
        # OCR 管理器通过 set_ocr_manager 方法从外部注入
        # 或者在首次 OCR 时延迟创建
        if self._ocr_manager is not None:
            self._ocr_preview_panel.set_ocr_manager(self._ocr_manager)
        
        # 将 OCR 预览面板添加到占位符的布局中
        layout = self._ocr_placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(self._ocr_placeholder)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ocr_preview_panel)
    
    def _get_item_image(self, item: HistoryItem) -> "QImage":
        """获取历史记录条目的图片
        
        Args:
            item: 历史记录条目
            
        Returns:
            QImage 对象，如果加载失败返回 None
        """
        import os
        from PySide6.QtGui import QImage
        from screenshot_tool.core.clipboard_history_manager import get_clipboard_data_dir
        
        if not item.image_path:
            return None
        
        full_path = os.path.join(get_clipboard_data_dir(), item.image_path)
        if not os.path.exists(full_path):
            return None
        
        image = QImage(full_path)
        if image.isNull():
            return None
        
        return image
    
    def _show_menu(self, pos):
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item:
            return
        
        menu = QMenu(self)
        
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)
        
        menu.addSeparator()
        
        # 置顶当前项
        top_action = QAction("⬆ 置顶", self)
        top_action.triggered.connect(self._move_to_top)
        menu.addAction(top_action)
        
        # 置顶所有钉住项
        top_all_pinned = QAction("⬆ 置顶所有钉住项", self)
        top_all_pinned.triggered.connect(self._move_all_pinned_to_top)
        menu.addAction(top_all_pinned)
        
        # 钉住/取消钉住
        pin_text = "📌 取消钉住" if item.is_pinned else "📌 钉住"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(self._toggle_pin)
        menu.addAction(pin_action)
        
        # 重命名
        rename_action = QAction("✏️ 重命名", self)
        rename_action.triggered.connect(self._rename_item)
        menu.addAction(rename_action)
        
        # 截图专用选项（Feature: screenshot-state-restore, Requirements: 4.2）
        if item.content_type == ContentType.IMAGE:
            menu.addSeparator()
            
            # 继续编辑
            edit_action = QAction("✏️ 继续编辑", self)
            edit_action.triggered.connect(self._edit_screenshot)
            menu.addAction(edit_action)
            
            # 贴图
            ding_action = QAction("📌 贴图", self)
            ding_action.triggered.connect(self._ding_screenshot)
            menu.addAction(ding_action)
        
        menu.addSeparator()
        
        del_action = QAction("删除", self)
        del_action.triggered.connect(self._delete_selected)
        menu.addAction(del_action)
        
        menu.exec(self._list.mapToGlobal(pos))
    
    def _show_text_preview_menu(self, pos):
        """文本预览区域的右键菜单（中文）"""
        menu = QMenu(self)
        
        # 撤销
        undo_action = QAction("撤销", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setEnabled(self._text_preview.document().isUndoAvailable())
        undo_action.triggered.connect(self._text_preview.undo)
        menu.addAction(undo_action)
        
        # 重做
        redo_action = QAction("重做", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setEnabled(self._text_preview.document().isRedoAvailable())
        redo_action.triggered.connect(self._text_preview.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        # 剪切
        cut_action = QAction("剪切", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.setEnabled(self._text_preview.textCursor().hasSelection())
        cut_action.triggered.connect(self._text_preview.cut)
        menu.addAction(cut_action)
        
        # 复制
        copy_action = QAction("复制", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setEnabled(self._text_preview.textCursor().hasSelection())
        copy_action.triggered.connect(self._text_preview.copy)
        menu.addAction(copy_action)
        
        # 粘贴
        paste_action = QAction("粘贴", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.setEnabled(self._text_preview.canPaste())
        paste_action.triggered.connect(self._text_preview.paste)
        menu.addAction(paste_action)
        
        # 删除
        delete_action = QAction("删除", self)
        delete_action.setEnabled(self._text_preview.textCursor().hasSelection())
        delete_action.triggered.connect(self._delete_selected_text)
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # 全选
        select_all_action = QAction("全选", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self._text_preview.selectAll)
        menu.addAction(select_all_action)
        
        menu.exec(self._text_preview.mapToGlobal(pos))
    
    def _delete_selected_text(self):
        """删除文本预览中选中的文字"""
        cursor = self._text_preview.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
    
    def _show_preview_menu(self, pos):
        """右侧预览区域的右键菜单"""
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item:
            return
        
        menu = QMenu(self)
        
        # 复制
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)
        
        # 截图专用选项
        if item.content_type == ContentType.IMAGE:
            menu.addSeparator()
            
            # 继续编辑
            edit_action = QAction("✏️ 继续编辑", self)
            edit_action.triggered.connect(self._edit_screenshot)
            menu.addAction(edit_action)
            
            # 贴图
            ding_action = QAction("📌 贴图", self)
            ding_action.triggered.connect(self._ding_screenshot)
            menu.addAction(ding_action)
        
        menu.addSeparator()
        
        # 钉住/取消钉住
        pin_text = "📌 取消钉住" if item.is_pinned else "📌 钉住"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(self._toggle_pin)
        menu.addAction(pin_action)
        
        menu.addSeparator()
        
        # 删除
        del_action = QAction("删除", self)
        del_action.triggered.connect(self._delete_selected)
        menu.addAction(del_action)
        
        # 根据发送者确定菜单位置
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(pos))
        else:
            menu.exec(self._preview_stack.mapToGlobal(pos))
    
    def _copy_selected(self):
        current_id = self._get_current_item_id()
        if current_id:
            self._manager.copy_to_clipboard(current_id)
    
    def _edit_screenshot(self):
        """继续编辑截图
        
        Feature: screenshot-state-restore
        Requirements: 2.1, 4.2
        """
        current_id = self._get_current_item_id()
        if current_id:
            self.edit_screenshot_requested.emit(current_id)
            self.close()
    
    def _ding_screenshot(self):
        """贴图
        
        Feature: screenshot-state-restore
        Requirements: 3.1, 4.2
        """
        current_id = self._get_current_item_id()
        if current_id:
            self.ding_screenshot_requested.emit(current_id)
    
    def _create_blank_note(self):
        """创建空白便签条目
        
        在历史记录列表中新增一个空白文本条目，用户可以直接编辑。
        """
        import uuid
        from datetime import datetime
        
        try:
            # 导入 ContentType
            from screenshot_tool.core.clipboard_history_manager import HistoryItem, ContentType
            
            # 生成唯一 ID
            note_id = str(uuid.uuid4())
            
            # 创建空白文本条目
            # 使用带时间戳的占位符避免去重逻辑合并多个空白便签
            timestamp = datetime.now()
            placeholder = f"便签 {timestamp.strftime('%H:%M:%S')}"
            
            item = HistoryItem(
                id=note_id,
                content_type=ContentType.TEXT,
                text_content="",  # 空内容，用户可编辑
                image_path=None,
                preview_text=placeholder,
                timestamp=timestamp,
                is_pinned=False,
            )
            
            # 直接添加到历史记录列表（绕过去重检查）
            self._manager._history.append(item)
            self._manager._enforce_limit()
            self._manager.history_changed.emit()
            self._manager.save()
            
            # 刷新列表并选中新条目
            self._refresh()
            
            # 选中第一个条目（新添加的在最后，但显示时是倒序）
            if self._list_model.rowCount() > 0:
                index = self._list_model.index(0, 0)
                self._list.setCurrentIndex(index)
                # 聚焦到文本编辑区
                self._text_preview.setFocus()
                
        except Exception as e:
            import traceback
            print(f"[空白便签] 创建失败: {e}")
            traceback.print_exc()
    
    def _move_to_top(self):
        """置顶：将选中项移到最前面"""
        current_id = self._get_current_item_id()
        if current_id:
            self._is_local_operation = True
            try:
                self._manager.move_to_top(current_id)
                self._manager.save()
                # 手动刷新列表（因为顺序变了）
                self._refresh(force=True)
            finally:
                self._is_local_operation = False
    
    def _move_all_pinned_to_top(self):
        """置顶所有钉住项"""
        self._is_local_operation = True
        try:
            count = self._manager.move_all_pinned_to_top()
            if count > 0:
                self._manager.save()
                # 手动刷新列表（因为顺序变了）
                self._refresh(force=True)
        finally:
            self._is_local_operation = False
    
    def _toggle_pin(self):
        current_id = self._get_current_item_id()
        if current_id:
            self._is_local_operation = True
            try:
                self._manager.toggle_pin(current_id)
                self._manager.save()
                # 更新模型中的数据并通知视图刷新
                self._update_current_item_in_model()
            finally:
                self._is_local_operation = False
    
    def _rename_item(self):
        """重命名条目"""
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item:
            return
        
        # 获取当前名称作为默认值
        current_name = item.custom_name or item.preview_text
        
        # 显示输入对话框
        new_name, ok = QInputDialog.getText(
            self,
            "重命名",
            "请输入新名称（留空则恢复默认）：",
            text=current_name
        )
        
        if ok:
            self._is_local_operation = True
            try:
                self._manager.rename_item(current_id, new_name)
                self._manager.save()
                # 更新模型中的数据并通知视图刷新
                self._update_current_item_in_model()
            finally:
                self._is_local_operation = False
    
    def _update_current_item_in_model(self):
        """更新当前选中项在模型中的数据（避免全量刷新）
        
        Feature: extreme-performance-optimization
        Requirements: 11.1, 11.6
        """
        current_id = self._get_current_item_id()
        if not current_id:
            return
        
        item = self._manager.get_item(current_id)
        if not item:
            return
        
        # 更新模型中的数据
        item_data = _convert_history_item_to_data(item)
        self._list_model.update_item(
            current_id,
            preview_text=item_data.preview_text,
            is_pinned=item_data.is_pinned,
            has_annotations=item_data.has_annotations
        )
    
    def _delete_selected(self):
        current_id = self._get_current_item_id()
        if current_id:
            self._is_local_operation = True
            try:
                self._manager.delete_item(current_id)
                self._manager.save()
                # 从模型中删除条目
                self._list_model.remove_item(current_id)
            finally:
                self._is_local_operation = False
    
    def _clear_all(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("确认清空")
        msg.setText("清空所有未钉住的历史记录？")
        msg.setInformativeText("钉住的记录会保留，此操作不可撤销。")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self._manager.clear_all(keep_pinned=True)
            self._manager.save()
    
    def showEvent(self, event):
        """窗口显示时检查是否需要刷新
        
        Feature: workbench-lazy-refresh
        如果是预加载的窗口（skip_initial_refresh=True），
        首次显示时执行延迟刷新。
        
        性能优化：实时预览模式下跳过刷新，避免阻塞。
        """
        super().showEvent(event)
        # 窗口显示时断开自动刷新信号，避免操作时卡顿
        self._disconnect_refresh_signal()
        
        # 实时预览模式下跳过刷新（性能优化）
        if self._skip_show_refresh:
            self._skip_show_refresh = False
            return
        
        # Feature: workbench-lazy-refresh
        # 预加载窗口首次显示时执行延迟刷新
        if not self._initial_refresh_done:
            self._initial_refresh_done = True
            self._refresh(force=True)
        elif self._needs_refresh:
            self._needs_refresh = False
            self._refresh()
    
    def changeEvent(self, event):
        """窗口状态变化事件
        
        Feature: smart-clipboard-monitoring
        当工作台窗口获得/失去焦点时，通知剪贴板管理器暂停/恢复监听，
        避免用户在工作台内部操作时触发不必要的剪贴板捕获。
        """
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.ActivationChange:
            is_active = self.isActiveWindow()
            if self._manager is not None:
                self._manager.set_history_window_focused(is_active)
        super().changeEvent(event)
    
    def keyPressEvent(self, event: QKeyEvent):
        # Ctrl+C 复制选中项（符合 Windows 标准交互）
        if event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._copy_selected()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._copy_and_close()
        elif event.key() == Qt.Key.Key_Delete:
            self._delete_selected()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    
    def hideEvent(self, event):
        """窗口隐藏时恢复自动刷新信号"""
        super().hideEvent(event)
        # 窗口隐藏时重新连接刷新信号
        self._connect_refresh_signal()
    
    def closeEvent(self, event):
        """窗口关闭事件
        
        Feature: workbench-temporary-preview-python
        Requirements: 4.1, 4.4, 4.5
        
        关闭窗口时检查是否有未保存的临时图像，
        如果有则显示确认对话框让用户选择：
        - 保存：保存临时图像到历史后关闭
        - 丢弃：丢弃临时图像后关闭
        - 取消：取消关闭操作
        
        最佳实践（来自 Google AI 搜索）：
        - 使用 event.ignore() 阻止窗口关闭
        - 始终使用 QMessageBox(self) 确保对话框在当前窗口中心弹出
        - 提供"取消"选项让用户能够回到当前编辑状态
        """
        # 检查是否有未保存的更改（Requirements: 4.1）
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "未保存的截图",
                "当前截图尚未保存，是否保存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save  # 默认选中保存
            )
            
            if reply == QMessageBox.StandardButton.Save:
                # 保存临时图像后关闭（Requirements: 4.4）
                self.confirm_and_save()
                # 继续执行关闭流程
            elif reply == QMessageBox.StandardButton.Discard:
                # 丢弃临时图像后关闭（Requirements: 4.4）
                self.discard_temporary()
                # 继续执行关闭流程
            else:
                # 取消关闭操作（Requirements: 4.5）
                event.ignore()
                return
        
        # 停止刷新定时器
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        # 窗口关闭前保存未完成的编辑
        if self._text_save_timer.isActive():
            self._text_save_timer.stop()
            self._do_save_text_edit()
        # 确保恢复剪贴板监听
        if self._clipboard_paused:
            self._manager.start_monitoring()
            self._clipboard_paused = False
        # 清理 OCR 预览面板缓存（Requirements: 8.3）
        if self._ocr_preview_panel is not None:
            self._ocr_preview_panel.cancel_ocr()
            self._ocr_preview_panel.clear_cache()
        # 取消注册延迟更新回调（Feature: extreme-performance-optimization）
        # Requirements: 11.9, 12.4
        self._deferred_update_manager.unregister_resume_callback(self._on_deferred_updates_resumed)
        # 重新连接刷新信号
        self._connect_refresh_signal()
        self.closed.emit()
        super().closeEvent(event)
