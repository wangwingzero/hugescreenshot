# -*- coding: utf-8 -*-
"""
OCR 预览面板 - 嵌入式 OCR 结果显示组件

功能：
- 显示 OCR 识别结果
- 复制、排版、翻译功能
- OCR 引擎切换
- Markdown 预览
- 返回图片预览

Feature: clipboard-ocr-merge
Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2
"""

from dataclasses import dataclass
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QToolButton, QMenu, QApplication,
    QStackedWidget, QTextBrowser
)
from PySide6.QtCore import Qt, Signal, QMimeData, QThread
from PySide6.QtGui import QFont, QTextCursor, QImage, QAction
from typing import Optional, Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from screenshot_tool.services.ocr_manager import OCRManager


@dataclass
class CachedOCRResult:
    """缓存的 OCR 结果
    
    Feature: clipboard-ocr-merge
    Requirements: 4.3, 8.1, 8.2
    """
    item_id: str                    # 历史记录条目 ID
    engine: str                     # 使用的引擎
    text: str                       # 识别文本
    average_score: float            # 平均置信度
    backend_detail: str             # 后端详情
    elapsed_time: float             # 耗时
    timestamp: datetime             # 缓存时间


class OCRWorker(QThread):
    """OCR 后台线程
    
    Feature: clipboard-ocr-merge
    Requirements: 3.1
    
    复用 OCRResultWindow 的 OCRWorker 模式，在后台执行 OCR 识别。
    """
    finished = Signal(object)  # UnifiedOCRResult
    
    def __init__(self, image: QImage, engine: str, ocr_manager: "OCRManager"):
        super().__init__()
        # 复制图片以避免线程安全问题
        self._image = image.copy() if image and not image.isNull() else None
        self._engine = engine
        self._ocr_manager = ocr_manager
        self._should_stop = False
    
    def request_stop(self):
        """请求停止线程
        
        Requirements: 10.5
        """
        self._should_stop = True
    
    def run(self):
        """执行 OCR 识别
        
        在 finally 块中释放图片引用，确保内存被释放。
        Requirements: 3.1, 10.3
        """
        try:
            if self._should_stop:
                return
            
            if self._image is None or self._image.isNull():
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self.finished.emit(UnifiedOCRResult.error_result("图片为空", self._engine))
                return
            
            result = self._ocr_manager.recognize_with_engine(self._image, self._engine)
            if not self._should_stop:
                self.finished.emit(result)
        except Exception as e:
            if not self._should_stop:
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self.finished.emit(UnifiedOCRResult.error_result(str(e), self._engine))
        finally:
            # 释放图片内存 (Requirements: 10.3)
            self._image = None


class TranslationWorker(QThread):
    """翻译后台线程
    
    复用 OCRResultWindow 的翻译逻辑，使用 EnhancedTranslationService。
    """
    finished = Signal(object)  # TranslationResult
    
    def __init__(self, text: str, target_lang: str):
        super().__init__()
        self._text = text
        self._target_lang = target_lang
    
    def run(self):
        try:
            from screenshot_tool.services.enhanced_translation_service import (
                EnhancedTranslationService, TranslationResult
            )
            service = EnhancedTranslationService(timeout=30)
            result = service.translate(self._text, self._target_lang)
            self.finished.emit(result)
        except Exception as e:
            from screenshot_tool.services.enhanced_translation_service import TranslationResult
            self.finished.emit(TranslationResult.error_result(self._text, str(e)))


class OCRPreviewPanel(QWidget):
    """嵌入式 OCR 预览面板
    
    Feature: clipboard-ocr-merge
    Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2
    
    用于在工作台窗口中显示 OCR 识别结果，
    复用 OCRResultWindow 的核心逻辑，但以嵌入式面板形式呈现。
    """
    
    # 信号
    back_to_image_requested = Signal()  # 请求返回图片预览
    engine_switch_requested = Signal(str)  # 引擎切换请求信号，参数为引擎名称
    
    # OCR 缓存最大条目数（Requirements: 10.4）
    MAX_CACHE_SIZE = 20
    
    # OCR 引擎显示名称映射（类常量）
    ENGINE_DISPLAY_NAMES = {
        "baidu": "百度OCR",
        "tencent": "腾讯OCR",
        "rapid": "本地OCR",
    }
    
    # 评分颜色阈值（类常量）
    SCORE_COLOR_HIGH = (60, "#4CAF50")    # 绿色，60分及以上
    SCORE_COLOR_MEDIUM = (40, "#FF9800")  # 橙色，40-59分
    SCORE_COLOR_LOW = (0, "#F44336")      # 红色，40分以下

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化 OCR 预览面板
        
        Args:
            parent: 父组件
        """
        super().__init__(parent)
        
        # 状态变量
        self._original_text = ""      # OCR 原始文本
        self._ocr_text = ""           # 当前 OCR 文本（可能经过排版）
        self._translated_text = ""    # 翻译后的文本
        self._is_showing_translation = False  # 是否显示翻译结果
        self._current_engine = ""     # 当前使用的引擎
        self._is_preview_mode = False # 是否处于 Markdown 预览模式
        
        # OCR 管理器引用（延迟设置）
        self._ocr_manager: Optional["OCRManager"] = None
        
        # OCR 相关状态 (Requirements: 3.1, 4.3, 8.1, 8.2)
        self._ocr_worker: Optional[OCRWorker] = None
        self._current_image: Optional[QImage] = None  # 当前图片
        self._current_item_id: str = ""  # 当前条目 ID
        
        # OCR 缓存结构: Dict[item_id, Dict[engine, CachedOCRResult]]
        # Requirements: 4.3, 8.1, 8.2
        self._ocr_cache: Dict[str, Dict[str, CachedOCRResult]] = {}
        
        # 翻译相关状态
        self._translation_worker: Optional[TranslationWorker] = None
        self._translation_cache: Dict[Tuple[str, str], Dict[str, str]] = {}  # {(text, target_lang): {"text": ..., "source": ...}}
        self._pending_translation_key: Optional[Tuple[str, str]] = None
        
        # 孤儿线程列表（用于保持未能及时停止的线程引用，防止 GC 销毁运行中的 QThread）
        # Bug fix (2026-01-23): 避免 QThread: Destroyed while thread is still running 错误
        self._orphan_threads: list = []
        
        # 设置 UI
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面布局
        
        Requirements: 2.1, 2.2, 5.1, 5.2, 5.3, 5.4, 5.5
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 工具栏
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(12, 8, 12, 8)
        toolbar.setSpacing(4)
        
        # 复制按钮 (Requirement 5.1)
        self._copy_btn = self._create_button("复制", "复制全部文字")
        self._copy_btn.clicked.connect(self._copy_all)
        toolbar.addWidget(self._copy_btn)
        
        # 排版菜单 (Requirement 5.2)
        self._format_btn = self._create_button("排版", "文字排版选项")
        format_menu = QMenu(self)
        format_menu.setStyleSheet(self._get_menu_style())
        format_menu.addAction("合并为单行", self._merge_to_single_line)
        format_menu.addAction("智能分段", self._smart_paragraphs)
        format_menu.addAction("去除所有空格", self._remove_all_spaces)
        format_menu.addAction("去除多余空格", self._remove_extra_spaces)
        format_menu.addSeparator()
        format_menu.addAction("中文标点→英文", self._chinese_punct_to_english)
        format_menu.addAction("英文标点→中文", self._english_punct_to_chinese)
        self._format_btn.setMenu(format_menu)
        self._format_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(self._format_btn)
        
        toolbar.addSpacing(8)
        
        # 原文按钮 (Requirement 5.4)
        self._toggle_btn = self._create_button("原文", "恢复 OCR 原始结果")
        self._toggle_btn.clicked.connect(self._restore_original)
        self._toggle_btn.setEnabled(False)
        toolbar.addWidget(self._toggle_btn)
        
        # 翻译按钮 (Requirement 5.3)
        self._translate_btn = self._create_button("翻译", "智能翻译（中↔英）")
        self._translate_btn.clicked.connect(self._do_smart_translate)
        toolbar.addWidget(self._translate_btn)
        
        toolbar.addStretch()
        
        # OCR 引擎切换按钮 (Requirement 4.1, 4.4)
        self._rapid_btn = self._create_engine_button("本地", "使用本地 OCR 重新识别")
        self._rapid_btn.clicked.connect(lambda: self._switch_engine("rapid"))
        toolbar.addWidget(self._rapid_btn)
        
        self._tencent_btn = self._create_engine_button("腾讯", "使用腾讯 OCR 重新识别")
        self._tencent_btn.clicked.connect(lambda: self._switch_engine("tencent"))
        toolbar.addWidget(self._tencent_btn)
        
        self._baidu_btn = self._create_engine_button("百度", "使用百度 OCR 重新识别")
        self._baidu_btn.clicked.connect(lambda: self._switch_engine("baidu"))
        toolbar.addWidget(self._baidu_btn)
        
        toolbar.addSpacing(8)
        
        # MD 格式预览按钮 (Requirement 6.1)
        self._preview_btn = self._create_button("MD格式", "切换 Markdown 格式预览")
        self._preview_btn.setCheckable(True)
        self._preview_btn.clicked.connect(self._toggle_preview_mode)
        toolbar.addWidget(self._preview_btn)
        
        # 「返回图片」按钮已移除 - 右侧默认显示 OCR 内容，左侧缩略图已改为高清
        # 保留 _back_btn 属性以兼容现有代码
        self._back_btn = None
        
        layout.addWidget(toolbar_widget)

        # 内容区域堆栈（编辑/预览切换）
        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet("""
            QStackedWidget {
                background-color: #FFFFFF;
            }
        """)
        
        # 文本编辑区（索引 0）
        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont("Microsoft YaHei", 11))
        self._text_edit.setPlaceholderText("OCR 识别结果将显示在这里...")
        self._text_edit.setStyleSheet("""
            QTextEdit {
                border: none;
                padding: 16px;
                background-color: #FFFFFF;
                color: #1E293B;
            }
        """)
        self._text_edit.textChanged.connect(self._update_count)
        # 自定义中文右键菜单
        self._text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text_edit.customContextMenuRequested.connect(self._show_text_edit_menu)
        self._content_stack.addWidget(self._text_edit)
        
        # Markdown 预览区（索引 1）
        self._preview_browser = QTextBrowser()
        self._preview_browser.setFont(QFont("Microsoft YaHei", 11))
        self._preview_browser.setOpenExternalLinks(True)
        self._preview_browser.setStyleSheet("""
            QTextBrowser {
                border: none;
                padding: 16px;
                background-color: #FFFFFF;
            }
        """)
        self._content_stack.addWidget(self._preview_browser)
        
        layout.addWidget(self._content_stack, 1)  # stretch=1 让内容区域占据剩余空间
        
        # 底部状态栏 (Requirement 5.5)
        status_widget = QWidget()
        status_widget.setStyleSheet("""
            QWidget {
                background-color: #F8FAFC;
                border-top: 1px solid #E2E8F0;
            }
        """)
        status_bar = QHBoxLayout(status_widget)
        status_bar.setContentsMargins(12, 6, 12, 6)
        
        # 字数统计 (Requirement 5.5)
        self._count_label = QLabel("0 字")
        self._count_label.setStyleSheet("color: #64748B; font-size: 11px;")
        status_bar.addWidget(self._count_label)
        
        status_bar.addStretch()
        
        # 状态信息
        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        status_bar.addWidget(self._status_label)
        
        # 引擎信息
        self._engine_label = QLabel("")
        self._engine_label.setStyleSheet("color: #3B82F6; font-size: 11px;")
        status_bar.addWidget(self._engine_label)
        
        layout.addWidget(status_widget)
    
    def _create_button(self, text: str, tooltip: str) -> QToolButton:
        """创建工具按钮
        
        Args:
            text: 按钮文字
            tooltip: 提示文字
            
        Returns:
            QToolButton 实例
        """
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: #64748B;
            }
            QToolButton:hover {
                background-color: #EFF6FF;
                border-color: #3B82F6;
                color: #3B82F6;
            }
            QToolButton:pressed {
                background-color: #DBEAFE;
            }
            QToolButton:disabled {
                background-color: #F1F5F9;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
            QToolButton::menu-indicator {
                image: none;
            }
        """)
        return btn
    
    def _create_engine_button(self, text: str, tooltip: str) -> QToolButton:
        """创建引擎切换按钮
        
        Args:
            text: 按钮文字
            tooltip: 提示文字
            
        Returns:
            QToolButton 实例
        """
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                color: #64748B;
            }
            QToolButton:hover {
                background-color: #EFF6FF;
                border-color: #3B82F6;
                color: #3B82F6;
            }
            QToolButton:pressed {
                background-color: #DBEAFE;
            }
            QToolButton:checked {
                background-color: #3B82F6;
                color: white;
                border-color: #2563EB;
            }
            QToolButton:disabled {
                background-color: #F1F5F9;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
        """)
        return btn

    def _get_back_button_style(self) -> str:
        """获取返回按钮样式
        
        Returns:
            样式字符串
        """
        return """
            QToolButton {
                background-color: #EFF6FF;
                border: 1px solid #3B82F6;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: #3B82F6;
            }
            QToolButton:hover {
                background-color: #DBEAFE;
                border-color: #2563EB;
                color: #2563EB;
            }
            QToolButton:pressed {
                background-color: #BFDBFE;
            }
        """
    
    def _get_menu_style(self) -> str:
        """获取菜单样式
        
        Returns:
            样式字符串
        """
        return """
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px 8px 16px;
                border-radius: 4px;
                color: #1E293B;
            }
            QMenu::item:selected {
                background-color: #EFF6FF;
                color: #3B82F6;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E2E8F0;
                margin: 4px 8px;
            }
        """
    
    # =====================================================
    # 公共接口方法
    # =====================================================
    
    def set_ocr_manager(self, manager: "OCRManager"):
        """设置 OCR 管理器
        
        Args:
            manager: OCR 管理器实例
        """
        self._ocr_manager = manager
        self._update_engine_buttons()
    
    def set_text(self, text: str, engine: str = "", average_score: float = 0.0,
                 backend_detail: str = "", elapsed_time: float = 0.0):
        """设置 OCR 识别结果文本
        
        Args:
            text: OCR 识别的文本
            engine: 引擎名称 (rapid/baidu/tencent)
            average_score: 平均置信度分数 (0.0-1.0)
            backend_detail: 后端详细信息
            elapsed_time: OCR 耗时（秒）
        """
        self._original_text = text
        self._ocr_text = text
        self._translated_text = ""
        self._is_showing_translation = False
        self._current_engine = engine
        
        self._text_edit.setPlainText(text)
        if text:
            self._text_edit.setPlaceholderText("OCR 识别结果将显示在这里...")
        else:
            self._text_edit.setPlaceholderText("未识别到文字内容")
        
        self._toggle_btn.setEnabled(False)
        self._status_label.setText("识别完成" if text else "识别完成（无文字）")
        
        # 更新引擎标签显示
        self._update_engine_label(engine, average_score, backend_detail, elapsed_time)
        self._highlight_current_engine()
    
    def set_loading(self):
        """设置加载状态"""
        self._text_edit.setPlainText("")
        self._text_edit.setPlaceholderText("正在识别中...")
        self._status_label.setText("识别中...")
        self._engine_label.setText("")
    
    def show_waiting_state(self):
        """显示等待截图状态
        
        在截图开始时调用，显示等待用户完成选区的提示。
        """
        self._text_edit.setPlainText("")
        self._text_edit.setPlaceholderText("请框选截图区域，完成后自动识别...")
        self._status_label.setText("等待截图...")
        self._engine_label.setText("")
        self._count_label.setText("0 字")
        # 清空之前的状态
        self._original_text = ""
        self._ocr_text = ""
        self._translated_text = ""
        self._is_showing_translation = False
    
    def set_error(self, error: str):
        """设置错误状态
        
        Args:
            error: 错误信息
        """
        self._text_edit.setPlainText(f"识别失败: {error}")
        self._text_edit.setPlaceholderText("识别失败")
        self._status_label.setText("识别失败")
        self._engine_label.setText("")
    
    def get_text(self) -> str:
        """获取当前文本内容
        
        Returns:
            当前文本
        """
        return self._text_edit.toPlainText()
    
    def clear(self):
        """清空面板内容"""
        self._original_text = ""
        self._ocr_text = ""
        self._translated_text = ""
        self._is_showing_translation = False
        self._current_engine = ""
        self._current_item_id = ""
        self._current_image = None
        self._text_edit.clear()
        self._text_edit.setPlaceholderText("OCR 识别结果将显示在这里...")
        self._status_label.setText("就绪")
        self._engine_label.setText("")
        self._toggle_btn.setEnabled(False)
        self._highlight_current_engine()
        # 清空翻译缓存
        self._translation_cache.clear()
        self._pending_translation_key = None
    
    # =====================================================
    # OCR 识别和缓存方法 (Task 1.3)
    # Requirements: 3.1, 3.2, 3.3, 3.4, 4.2, 4.3, 8.1, 8.2
    # =====================================================
    
    def start_ocr(self, image: QImage, item_id: str):
        """开始 OCR 识别
        
        Args:
            image: 要识别的图片
            item_id: 历史记录条目 ID（用于缓存）
            
        Requirements: 3.1, 3.2, 3.3, 3.4, 4.3
        """
        if self._ocr_manager is None:
            self.set_error("OCR 管理器未设置")
            return
        
        if image is None or image.isNull():
            self.set_error("图片为空")
            return
        
        # 取消正在进行的 OCR
        self._cancel_ocr()
        
        # 保存当前图片和条目 ID
        self._current_image = image.copy()
        self._current_item_id = item_id
        
        # 确定使用的引擎（默认使用本地 OCR）
        engine = self._current_engine if self._current_engine else "rapid"
        
        # 检查缓存 (Requirements: 4.3, 8.1)
        if item_id in self._ocr_cache and engine in self._ocr_cache[item_id]:
            cached = self._ocr_cache[item_id][engine]
            self._apply_cached_result(cached)
            self._status_label.setText(f"使用缓存结果 [{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
            return
        
        # 检查引擎是否可用
        if not self._ocr_manager.is_engine_available(engine):
            status = self._ocr_manager.get_engine_status()
            msg = status.get(engine, {}).get("message", "不可用")
            self.set_error(f"{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}: {msg}")
            return
        
        # 显示加载状态 (Requirement 3.1)
        self.set_loading()
        self._disable_engine_buttons()
        
        # 启动后台 OCR 线程
        self._ocr_worker = OCRWorker(self._current_image, engine, self._ocr_manager)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.start()
    
    def restore_cached_result(self, item_id: str) -> bool:
        """恢复缓存的 OCR 结果
        
        Args:
            item_id: 历史记录条目 ID
            
        Returns:
            True 如果有缓存结果
            
        Requirements: 8.1, 8.2
        """
        if item_id not in self._ocr_cache:
            return False
        
        # 获取该条目的缓存（优先使用当前引擎的缓存）
        item_cache = self._ocr_cache[item_id]
        
        # 优先使用当前引擎的缓存
        engine = self._current_engine if self._current_engine else "rapid"
        if engine in item_cache:
            cached = item_cache[engine]
        else:
            # 使用任意可用的缓存
            cached = next(iter(item_cache.values()))
        
        self._current_item_id = item_id
        self._apply_cached_result(cached)
        self._status_label.setText(f"已恢复缓存结果 [{self.ENGINE_DISPLAY_NAMES.get(cached.engine, cached.engine)}]")
        return True
    
    def show_persistent_cache(self, item_id: str, ocr_text: str, engine: str = "rapid"):
        """显示持久化缓存的 OCR 结果
        
        Feature: background-ocr-cache
        
        用于显示后台 OCR 缓存的结果，并回填到 L1 内存缓存。
        
        Args:
            item_id: 历史记录条目 ID
            ocr_text: OCR 识别结果文本
            engine: 使用的引擎名称
        """
        # 创建缓存结果对象（后台缓存没有详细的评分信息）
        cached = CachedOCRResult(
            item_id=item_id,
            engine=engine,
            text=ocr_text,
            average_score=0.0,  # 后台缓存没有评分信息
            backend_detail="",
            elapsed_time=0.0,
            timestamp=datetime.now(),
        )
        
        # 回填到 L1 内存缓存
        if item_id not in self._ocr_cache:
            self._ocr_cache[item_id] = {}
        self._ocr_cache[item_id][engine] = cached
        
        # 更新当前条目 ID
        self._current_item_id = item_id
        
        # 应用缓存结果
        self._apply_cached_result(cached)
        self._status_label.setText(f"使用后台缓存 [{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
    
    def clear_cache(self):
        """清空所有缓存
        
        Requirements: 8.3
        """
        self._ocr_cache.clear()
    
    def has_cached_result(self, item_id: str) -> bool:
        """检查是否有缓存的 OCR 结果
        
        Args:
            item_id: 历史记录条目 ID
            
        Returns:
            True 如果有缓存结果
        """
        return item_id in self._ocr_cache
    
    def cancel_ocr(self):
        """取消正在进行的 OCR（公共接口）
        
        Requirements: 9.4, 10.5
        """
        self._cancel_ocr()
    
    def _cancel_ocr(self):
        """取消正在进行的 OCR（内部实现）
        
        Requirements: 9.4, 10.5
        
        Bug fix (2026-01-23): 移除 terminate() 调用，改用孤儿线程列表模式。
        terminate() 会导致 OpenVINO 内部状态不一致，最终导致程序崩溃。
        如果线程未能及时停止，将其移到孤儿线程列表，防止 GC 销毁运行中的 QThread。
        """
        if self._ocr_worker is not None:
            # 请求停止
            self._ocr_worker.request_stop()
            
            # 断开信号连接，避免回调到已销毁的对象
            try:
                self._ocr_worker.finished.disconnect(self._on_ocr_finished)
            except (RuntimeError, TypeError):
                pass
            
            # 等待线程结束
            if self._ocr_worker.isRunning():
                self._ocr_worker.quit()
                if not self._ocr_worker.wait(200):
                    # 不再使用 terminate()，因为它会导致 OpenVINO 崩溃
                    # 将线程移到孤儿列表，保持引用防止 GC 销毁运行中的 QThread
                    orphan = self._ocr_worker
                    self._ocr_worker = None
                    # 连接 finished 信号，线程完成后自动清理
                    try:
                        orphan.finished.connect(lambda: self._cleanup_orphan_thread(orphan))
                    except RuntimeError:
                        pass
                    self._orphan_threads.append(orphan)
                    return
            
            # 安全删除
            try:
                self._ocr_worker.deleteLater()
            except RuntimeError:
                pass
            self._ocr_worker = None
    
    def _cleanup_orphan_thread(self, thread):
        """清理孤儿线程"""
        try:
            if thread in self._orphan_threads:
                self._orphan_threads.remove(thread)
                thread.deleteLater()
        except (RuntimeError, ValueError):
            pass
    
    def _apply_cached_result(self, cached: CachedOCRResult):
        """应用缓存的 OCR 结果
        
        Args:
            cached: 缓存的 OCR 结果
        """
        self.set_text(
            cached.text,
            cached.engine,
            cached.average_score,
            cached.backend_detail,
            cached.elapsed_time
        )
    
    def _cache_result(self, item_id: str, engine: str, text: str,
                      average_score: float, backend_detail: str, elapsed_time: float):
        """缓存 OCR 结果
        
        Args:
            item_id: 历史记录条目 ID
            engine: 引擎名称
            text: 识别文本
            average_score: 平均置信度
            backend_detail: 后端详情
            elapsed_time: 耗时
            
        Requirements: 4.3, 8.1, 8.2, 10.4
        """
        # 检查缓存大小限制 (Requirements: 10.4)
        self._enforce_cache_limit()
        
        # 创建缓存条目
        cached = CachedOCRResult(
            item_id=item_id,
            engine=engine,
            text=text,
            average_score=average_score,
            backend_detail=backend_detail,
            elapsed_time=elapsed_time,
            timestamp=datetime.now()
        )
        
        # 存储到缓存
        if item_id not in self._ocr_cache:
            self._ocr_cache[item_id] = {}
        self._ocr_cache[item_id][engine] = cached
    
    def _enforce_cache_limit(self):
        """强制执行缓存大小限制
        
        超出限制时清理最旧的缓存。
        Requirements: 10.4
        """
        # 计算当前缓存条目总数
        total_entries = sum(len(engines) for engines in self._ocr_cache.values())
        
        if total_entries < self.MAX_CACHE_SIZE:
            return
        
        # 收集所有缓存条目并按时间排序
        all_entries = []
        for item_id, engines in self._ocr_cache.items():
            for engine, cached in engines.items():
                all_entries.append((item_id, engine, cached.timestamp))
        
        # 按时间排序（最旧的在前）
        all_entries.sort(key=lambda x: x[2])
        
        # 删除最旧的条目直到满足限制
        entries_to_remove = total_entries - self.MAX_CACHE_SIZE + 1
        for i in range(entries_to_remove):
            if i < len(all_entries):
                item_id, engine, _ = all_entries[i]
                if item_id in self._ocr_cache and engine in self._ocr_cache[item_id]:
                    del self._ocr_cache[item_id][engine]
                    # 如果该条目没有任何引擎缓存了，删除整个条目
                    if not self._ocr_cache[item_id]:
                        del self._ocr_cache[item_id]
    
    def _on_ocr_finished(self, result):
        """OCR 识别完成回调
        
        Requirements: 3.2, 3.3, 3.4
        """
        # 恢复按钮状态
        self._update_engine_buttons()
        
        if result is None:
            self.set_error("识别失败: 未知错误")
            return
        
        if result.success:
            # 提取结果信息
            text = result.text
            engine = result.engine
            average_score = getattr(result, 'average_score', 0.0)
            backend_detail = getattr(result, 'backend_detail', "")
            elapsed_time = getattr(result, 'elapsed_time', 0.0)
            
            # 缓存结果 (Requirements: 4.3, 8.1)
            if self._current_item_id:
                self._cache_result(
                    self._current_item_id, engine, text,
                    average_score, backend_detail, elapsed_time
                )
            
            # 显示结果 (Requirement 3.2)
            self.set_text(text, engine, average_score, backend_detail, elapsed_time)
            self._highlight_current_engine()
        else:
            # 显示错误 (Requirement 3.3)
            error = result.error or "识别失败"
            self.set_error(error)
        
        # 清理 worker
        self._cleanup_ocr_worker()
        
        # 释放图片内存 (Requirements: 10.3)
        self._current_image = None
    
    def _cleanup_ocr_worker(self):
        """清理 OCR worker"""
        if self._ocr_worker:
            try:
                self._ocr_worker.finished.disconnect(self._on_ocr_finished)
            except (RuntimeError, TypeError):
                pass
            if self._ocr_worker.isRunning():
                self._ocr_worker.quit()
                self._ocr_worker.wait(500)
            self._ocr_worker.deleteLater()
            self._ocr_worker = None
    
    def _disable_engine_buttons(self):
        """禁用引擎按钮（OCR 进行中）"""
        self._rapid_btn.setEnabled(False)
        if self._tencent_btn.isVisible():
            self._tencent_btn.setEnabled(False)
        if self._baidu_btn.isVisible():
            self._baidu_btn.setEnabled(False)

    # =====================================================
    # 内部方法
    # =====================================================
    
    def _update_count(self):
        """更新字数统计 (Requirement 5.5)"""
        text = self._text_edit.toPlainText()
        # 排除空白字符
        char_count = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        self._count_label.setText(f"{char_count} 字")
    
    def _update_engine_buttons(self):
        """更新引擎按钮状态（未配置 API 时隐藏按钮）"""
        if self._ocr_manager is None:
            self._rapid_btn.setEnabled(False)
            self._tencent_btn.hide()
            self._baidu_btn.hide()
            return
        
        # 获取引擎状态
        status = self._ocr_manager.get_engine_status()
        
        # RapidOCR 始终显示（本地引擎）
        rapid_available = status.get("rapid", {}).get("available", False)
        self._rapid_btn.setEnabled(rapid_available)
        rapid_msg = status.get("rapid", {}).get("message", "")
        self._rapid_btn.setToolTip(f"本地 OCR: {rapid_msg}")
        
        # 腾讯 OCR：未配置时隐藏按钮
        tencent_available = status.get("tencent", {}).get("available", False)
        tencent_msg = status.get("tencent", {}).get("message", "")
        if tencent_available:
            self._tencent_btn.show()
            self._tencent_btn.setEnabled(True)
            self._tencent_btn.setToolTip(f"腾讯 OCR: {tencent_msg}")
        else:
            self._tencent_btn.hide()
        
        # 百度 OCR：未配置时隐藏按钮
        baidu_available = status.get("baidu", {}).get("available", False)
        baidu_msg = status.get("baidu", {}).get("message", "")
        if baidu_available:
            self._baidu_btn.show()
            self._baidu_btn.setEnabled(True)
            self._baidu_btn.setToolTip(f"百度 OCR: {baidu_msg}")
        else:
            self._baidu_btn.hide()
        
        self._highlight_current_engine()
    
    def _highlight_current_engine(self):
        """高亮当前使用的引擎按钮"""
        engine = self._current_engine
        self._rapid_btn.setChecked(engine == "rapid")
        self._tencent_btn.setChecked(engine == "tencent")
        self._baidu_btn.setChecked(engine == "baidu")
    
    def _update_engine_label(self, engine: str, average_score: float,
                             backend_detail: str, elapsed_time: float):
        """更新引擎标签显示
        
        Args:
            engine: 引擎名称
            average_score: 平均置信度
            backend_detail: 后端详情
            elapsed_time: 耗时
        """
        if not engine:
            self._engine_label.setText("")
            self._engine_label.setTextFormat(Qt.TextFormat.PlainText)
            return
        
        # 对于本地 OCR，显示后端详情、评分和耗时
        if engine == "rapid":
            display_parts = []
            
            # 后端信息
            if backend_detail:
                display_parts.append(backend_detail)
            else:
                display_parts.append(self.ENGINE_DISPLAY_NAMES.get(engine, engine))
            
            # 构建显示文本
            html_parts = [f"[{display_parts[0]}]"]
            
            # 评分信息（仅当有有效分数时显示）
            if average_score > 0:
                score_text, score_color = self._format_score_display(average_score)
                html_parts.append(f"<span style='color: {score_color};'>{score_text}</span>")
            
            # 耗时信息（仅当有有效耗时时显示）
            if elapsed_time > 0:
                html_parts.append(f"<span style='color: #94A3B8;'>耗时 {elapsed_time:.2f}秒</span>")
            
            self._engine_label.setText(" ".join(html_parts))
            self._engine_label.setTextFormat(Qt.TextFormat.RichText)
        else:
            # 云端 OCR 只显示引擎名称
            self._engine_label.setText(f"[{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
            self._engine_label.setTextFormat(Qt.TextFormat.PlainText)
    
    def _format_score_display(self, score: float) -> tuple:
        """格式化评分显示
        
        Args:
            score: 0.0-1.0 的置信度分数
            
        Returns:
            Tuple[显示文本, 颜色代码]
        """
        import math
        
        # 处理无效分数
        if not math.isfinite(score):
            score = 0.0
        
        # 转换为百分制并取整
        score_100 = int(round(score * 100))
        score_100 = max(0, min(100, score_100))
        
        display_text = f"OCR评分 {score_100}/100"
        
        # 根据分数确定颜色
        if score_100 >= self.SCORE_COLOR_HIGH[0]:
            color = self.SCORE_COLOR_HIGH[1]
        elif score_100 >= self.SCORE_COLOR_MEDIUM[0]:
            color = self.SCORE_COLOR_MEDIUM[1]
        else:
            color = self.SCORE_COLOR_LOW[1]
        
        return display_text, color

    # =====================================================
    # 按钮回调方法
    # =====================================================
    
    def _on_back_clicked(self):
        """返回图片按钮点击回调 (Requirement 2.2)"""
        self.back_to_image_requested.emit()
    
    def _copy_all(self):
        """复制全部文字 (Requirement 5.1)
        
        预览模式下复制富文本，编辑模式下复制纯文本。
        """
        if self._is_preview_mode:
            self._copy_rich_text()
        else:
            text = self._text_edit.toPlainText()
            if text:
                QApplication.clipboard().setText(text)
                self._status_label.setText("已复制到剪贴板")
            else:
                self._status_label.setText("没有可复制的内容")
    
    def _copy_rich_text(self):
        """复制富文本到剪贴板"""
        html = self._preview_browser.toHtml()
        plain_text = self._preview_browser.toPlainText()
        
        if not plain_text:
            self._status_label.setText("没有可复制的内容")
            return
        
        mime_data = QMimeData()
        mime_data.setHtml(html)
        mime_data.setText(plain_text)
        
        QApplication.clipboard().setMimeData(mime_data)
        self._status_label.setText("已复制富文本到剪贴板")
    
    def _restore_original(self):
        """恢复 OCR 原始结果 (Requirement 5.4)"""
        if self._ocr_text:
            self._replace_text_with_undo(self._ocr_text)
            self._is_showing_translation = False
            self._toggle_btn.setEnabled(False)
            self._status_label.setText("已恢复原文")
    
    def _replace_text_with_undo(self, new_text: str):
        """替换文本内容，保留撤销历史
        
        Args:
            new_text: 新文本
        """
        if new_text is None:
            new_text = ""
        cursor = self._text_edit.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        self._text_edit.setTextCursor(cursor)
    
    def _do_smart_translate(self):
        """智能翻译 (Requirement 5.3)
        
        检测语言并自动翻译：中文→英文，英文→中文
        复用 OCRResultWindow 的翻译逻辑。
        """
        text = self._ocr_text.strip() if self._ocr_text else self._text_edit.toPlainText().strip()
        if not text:
            self._status_label.setText("没有可翻译的文字")
            return
        
        if self._translation_worker and self._translation_worker.isRunning():
            self._status_label.setText("翻译进行中，请稍候...")
            return
        
        # 检测语言，确定目标语言
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        target_lang = "英语" if has_chinese else "中文"
        
        # 调用内部翻译方法
        self._do_translate_internal(text, target_lang)
    
    def _do_translate_internal(self, text: str, target_lang: str):
        """执行翻译（内部实现）
        
        Args:
            text: 要翻译的文本（已去除首尾空格）
            target_lang: 目标语言（"英语" 或 "中文"）
        """
        # 检查翻译缓存
        cache_key = (text, target_lang)
        if cache_key in self._translation_cache:
            cached = self._translation_cache[cache_key]
            # 检查缓存的翻译结果是否和原文相同
            if cached["text"].strip() == text:
                self._status_label.setText("文本无需翻译（已是目标语言或无法翻译）")
                return
            self._translated_text = cached["text"]
            self._text_edit.setPlainText(cached["text"])
            self._is_showing_translation = True
            self._toggle_btn.setEnabled(True)
            self._status_label.setText(f"翻译完成 [{cached['source']}] (缓存)")
            return
        
        # 检查功能权限
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import (
                use_feature, Feature, get_feature_gate
            )
            gate = get_feature_gate()
            if gate:
                result = use_feature(Feature.TRANSLATION)
                if not result.allowed:
                    # 显示升级提示
                    from screenshot_tool.ui.upgrade_prompt import UpgradePromptDialog
                    status = gate.get_feature_status(Feature.TRANSLATION)
                    usage_info = None
                    if status.get("is_limited"):
                        usage_info = {
                            "usage": status.get("usage", 0),
                            "limit": status.get("limit", 0),
                            "remaining": status.get("remaining", 0),
                        }
                    dialog = UpgradePromptDialog(
                        feature_name="翻译",
                        reason=result.reason,
                        usage_info=usage_info,
                        parent=self
                    )
                    dialog.login_clicked.connect(self._show_login_dialog)
                    # 使用 show() 代替 exec()，避免阻塞热键
                    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
                    dialog.show()
                    dialog.activateWindow()
                    return
        except ImportError:
            pass  # 订阅模块未安装，允许使用
        
        display_lang = "英文" if target_lang == "英语" else "中文"
        self._status_label.setText(f"正在翻译到{display_lang}...")
        self._translate_btn.setEnabled(False)
        
        # 保存当前翻译的原文和目标语言，用于缓存
        self._pending_translation_key = cache_key
        
        self._translation_worker = TranslationWorker(text, target_lang)
        self._translation_worker.finished.connect(self._on_translation_finished)
        self._translation_worker.start()
    
    def _on_translation_finished(self, result) -> None:
        """翻译完成回调"""
        self._translate_btn.setEnabled(True)
        
        # 安全访问属性，防止 result 为 None 或属性不存在
        if result is None:
            self._status_label.setText("翻译失败: 未知错误")
            return
        
        translated_text = getattr(result, 'translated_text', None) or getattr(result, 'text', None)
        engine = getattr(result, 'engine', None) or getattr(result, 'source', None)
        is_success = getattr(result, 'success', False)
        
        if is_success and translated_text:
            # 获取原始文本用于比较
            original_text = self._ocr_text.strip() if self._ocr_text else ""
            
            # 检查翻译结果是否和原文相同
            if translated_text.strip() == original_text:
                self._status_label.setText("文本无需翻译（已是目标语言或无法翻译）")
                return
            
            self._translated_text = translated_text
            self._text_edit.setPlainText(translated_text)
            self._is_showing_translation = True
            self._toggle_btn.setEnabled(True)
            
            source_names = {
                "tencent": "腾讯", "youdao": "有道", "xiaoniu": "小牛",
                "youdao_dict": "有道词典", "google": "谷歌", "bing": "必应",
                "deepl": "DeepL", "baidu": "百度", "mymemory": "MyMemory",
                "papago": "Papago", "jianxin": "简心"
            }
            source_name = source_names.get(engine, engine) if engine else "未知"
            self._status_label.setText(f"翻译完成 [{source_name}]")
            
            # 缓存翻译结果
            if self._pending_translation_key:
                self._translation_cache[self._pending_translation_key] = {
                    "text": translated_text,
                    "source": source_name
                }
                self._pending_translation_key = None
        else:
            error = getattr(result, 'error', None) or "翻译失败"
            self._status_label.setText(f"翻译失败: {error}")
        
        # 清理 worker
        if self._translation_worker:
            try:
                self._translation_worker.finished.disconnect(self._on_translation_finished)
            except (RuntimeError, TypeError):
                pass
            if self._translation_worker.isRunning():
                self._translation_worker.quit()
                self._translation_worker.wait(500)
            self._translation_worker.deleteLater()
            self._translation_worker = None
    
    def _show_login_dialog(self):
        """显示登录对话框（用于升级提示）"""
        try:
            from screenshot_tool.ui.login_dialog import LoginDialog
            dialog = LoginDialog(parent=self)
            dialog.exec()
        except ImportError:
            self._status_label.setText("登录模块未安装")
    
    def _switch_engine(self, engine: str):
        """切换 OCR 引擎并重新识别
        
        Args:
            engine: 引擎名称 (rapid/baidu/tencent)
            
        Requirements: 4.2, 4.3
        """
        if self._ocr_manager is None:
            self._status_label.setText("OCR 管理器未设置")
            return
        
        if self._current_image is None or self._current_image.isNull():
            # 没有图片时，只更新当前引擎标记
            self._current_engine = engine
            self._highlight_current_engine()
            self._status_label.setText(f"已切换到 {self.ENGINE_DISPLAY_NAMES.get(engine, engine)}")
            return
        
        if self._ocr_worker and self._ocr_worker.isRunning():
            self._status_label.setText("正在识别中，请稍候...")
            return
        
        # 检查引擎是否可用
        if not self._ocr_manager.is_engine_available(engine):
            status = self._ocr_manager.get_engine_status()
            msg = status.get(engine, {}).get("message", "不可用")
            self._status_label.setText(f"{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}: {msg}")
            return
        
        # 更新当前引擎
        self._current_engine = engine
        
        # 检查缓存：如果已有该引擎的识别结果，直接使用 (Requirement 4.3)
        if self._current_item_id and self._current_item_id in self._ocr_cache:
            if engine in self._ocr_cache[self._current_item_id]:
                cached = self._ocr_cache[self._current_item_id][engine]
                self._apply_cached_result(cached)
                self._status_label.setText(f"使用缓存结果 [{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
                self._highlight_current_engine()
                return
        
        # 发出引擎切换信号
        self.engine_switch_requested.emit(engine)
        
        # 开始后台识别 (Requirement 4.2)
        self._status_label.setText(f"正在使用 {self.ENGINE_DISPLAY_NAMES.get(engine, engine)} 识别...")
        self._disable_engine_buttons()
        
        self._ocr_worker = OCRWorker(self._current_image, engine, self._ocr_manager)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.start()
    
    def _toggle_preview_mode(self):
        """切换 Markdown 预览模式 (Requirement 6.1)"""
        if self._is_preview_mode:
            # 切换到编辑模式
            self._is_preview_mode = False
            self._content_stack.setCurrentIndex(0)
            self._preview_btn.setText("MD格式")
            self._preview_btn.setChecked(False)
            self._status_label.setText("已切换到编辑模式")
        else:
            # 切换到预览模式
            self._render_markdown()
            self._is_preview_mode = True
            self._content_stack.setCurrentIndex(1)
            self._preview_btn.setText("普通")
            self._preview_btn.setChecked(True)
            self._status_label.setText("已切换到预览模式")
    
    def _render_markdown(self):
        """渲染 Markdown 到预览区域"""
        text = self._text_edit.toPlainText()
        if not text:
            self._preview_browser.setHtml("<p style='color: #94A3B8;'>无内容可预览</p>")
            return
        
        try:
            from screenshot_tool.services.markdown_parser import get_markdown_parser
            parser = get_markdown_parser()
            html = parser.parse(text)
            self._preview_browser.setHtml(html)
        except ImportError:
            # 如果 markdown_parser 不可用，显示纯文本
            self._preview_browser.setPlainText(text)

    # =====================================================
    # 排版功能方法 (Requirement 5.2)
    # =====================================================
    
    def _merge_to_single_line(self):
        """合并为单行"""
        text = self._text_edit.toPlainText()
        text = " ".join(text.split())
        self._replace_text_with_undo(text)
        self._status_label.setText("已合并为单行")
    
    def _smart_paragraphs(self):
        """智能分段"""
        import re
        text = self._text_edit.toPlainText()
        if not text.strip():
            return
        
        lines = text.split('\n')
        paragraphs = []
        current_para = []
        
        for line in lines:
            stripped = line.strip()
            
            # 空行表示段落结束
            if not stripped:
                if current_para:
                    paragraphs.append(current_para)
                    current_para = []
                continue
            
            # 判断是否是新段落的开始
            is_new_para = False
            if current_para:
                prev_line = current_para[-1]
                # 上一行以句号等结尾，且当前行有缩进或首字母大写
                if prev_line[-1] in '。！？.!?':
                    if line.startswith(' ') or line.startswith('\t'):
                        is_new_para = True
                    elif stripped[0].isupper():
                        is_new_para = True
                # 当前行以数字序号开头
                if re.match(r'^[\d一二三四五六七八九十]+[.、．]', stripped):
                    is_new_para = True
                # 当前行以项目符号开头
                if stripped[0] in '•·—●○◆◇▪▫' or re.match(r'^-\s', stripped):
                    is_new_para = True
            
            if is_new_para and current_para:
                paragraphs.append(current_para)
                current_para = []
            
            current_para.append(stripped)
        
        if current_para:
            paragraphs.append(current_para)
        
        # 合并每个段落内的行
        result_paras = []
        for para in paragraphs:
            para_text = ''.join(para)
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', para_text))
            is_chinese = chinese_chars > len(para_text) * 0.3
            
            if is_chinese:
                merged = ''.join(para)
            else:
                merged = ' '.join(para)
            result_paras.append(merged)
        
        result = '\n\n'.join(result_paras)
        result = re.sub(r' +', ' ', result)
        
        self._replace_text_with_undo(result)
        self._status_label.setText("已智能分段")
    
    def _remove_all_spaces(self):
        """去除所有空格"""
        text = self._text_edit.toPlainText()
        text = text.replace(" ", "").replace("\t", "")
        self._replace_text_with_undo(text)
        self._status_label.setText("已去除所有空格")
    
    def _remove_extra_spaces(self):
        """去除多余空格"""
        import re
        text = self._text_edit.toPlainText()
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\t+', ' ', text)
        self._replace_text_with_undo(text)
        self._status_label.setText("已去除多余空格")
    
    def _chinese_punct_to_english(self):
        """中文标点转英文标点"""
        text = self._text_edit.toPlainText()
        punct_map = [
            ('，', ','), ('。', '.'), ('！', '!'), ('？', '?'),
            ('；', ';'), ('：', ':'), ('"', '"'), ('"', '"'),
            (''', "'"), (''', "'"), ('【', '['), ('】', ']'),
            ('（', '('), ('）', ')'), ('《', '<'), ('》', '>'),
            ('、', ','), ('—', '-'), ('～', '~'), ('…', '...'),
        ]
        for cn, en in punct_map:
            text = text.replace(cn, en)
        self._replace_text_with_undo(text)
        self._status_label.setText("已转换为英文标点")
    
    def _english_punct_to_chinese(self):
        """英文标点转中文标点"""
        import re
        text = self._text_edit.toPlainText()
        punct_map = {
            ',': '，', '!': '！', '?': '？', ';': '；',
            '[': '【', ']': '】', '(': '（', ')': '）', '~': '～',
        }
        trans_map = str.maketrans(punct_map)
        text = text.translate(trans_map)
        
        # 句点：只转换句末的
        text = re.sub(r'(?<![0-9])\.(?=\s|$)', '。', text)
        # 冒号：只转换中文语境的
        text = re.sub(r'(?<=[\u4e00-\u9fff]):(?=[\u4e00-\u9fff\s])', '：', text)
        # 尖括号：只转换书名号语境
        text = re.sub(r'(?<=[\u4e00-\u9fff])<', '《', text)
        text = re.sub(r'>(?=[\u4e00-\u9fff])', '》', text)
        # 省略号
        text = text.replace('...', '…')
        
        self._replace_text_with_undo(text)
        self._status_label.setText("已转换为中文标点")

    def _show_text_edit_menu(self, pos):
        """文本编辑区域的右键菜单（中文）"""
        menu = QMenu(self)
        
        # 撤销
        undo_action = QAction("撤销", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setEnabled(self._text_edit.document().isUndoAvailable())
        undo_action.triggered.connect(self._text_edit.undo)
        menu.addAction(undo_action)
        
        # 重做
        redo_action = QAction("重做", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setEnabled(self._text_edit.document().isRedoAvailable())
        redo_action.triggered.connect(self._text_edit.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        # 剪切
        cut_action = QAction("剪切", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.setEnabled(self._text_edit.textCursor().hasSelection())
        cut_action.triggered.connect(self._text_edit.cut)
        menu.addAction(cut_action)
        
        # 复制
        copy_action = QAction("复制", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setEnabled(self._text_edit.textCursor().hasSelection())
        copy_action.triggered.connect(self._text_edit.copy)
        menu.addAction(copy_action)
        
        # 粘贴
        paste_action = QAction("粘贴", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.setEnabled(self._text_edit.canPaste())
        paste_action.triggered.connect(self._text_edit.paste)
        menu.addAction(paste_action)
        
        # 删除
        delete_action = QAction("删除", self)
        delete_action.setEnabled(self._text_edit.textCursor().hasSelection())
        delete_action.triggered.connect(self._delete_selected_text)
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # 全选
        select_all_action = QAction("全选", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self._text_edit.selectAll)
        menu.addAction(select_all_action)
        
        menu.exec(self._text_edit.mapToGlobal(pos))

    def _delete_selected_text(self):
        """删除文本编辑区中选中的文字"""
        cursor = self._text_edit.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
