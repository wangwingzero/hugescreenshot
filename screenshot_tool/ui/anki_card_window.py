# =====================================================
# =============== Anki 制卡窗口 ===============
# =====================================================

"""
Anki 制卡窗口 - 从高亮区域提取单词并制作 Anki 卡片

功能：
- 对高亮区域进行 OCR 识别
- 提取英文单词
- 批量导入到 Anki
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLabel, QToolButton, QPushButton, QApplication,
    QMessageBox, QProgressDialog, QListWidget, QListWidgetItem,
    QSplitter, QFrame, QRadioButton, QComboBox, QButtonGroup,
    QLineEdit, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QRect, QMutex
from PySide6.QtGui import QFont, QImage, QPixmap, QPainter, QColor, QKeyEvent
from datetime import datetime
from typing import List, Optional
import re
import uuid
import os

from screenshot_tool.ui.zoomable_preview import ZoomablePreviewWidget


class OCRWorker(QThread):
    """OCR 后台线程"""
    finished = Signal(str)  # OCR 结果文本
    error = Signal(str)
    
    def __init__(self, ocr_manager, image: QImage, rect: QRect):
        super().__init__()
        self._ocr_manager = ocr_manager
        self._image = image.copy() if image and not image.isNull() else None
        self._rect = rect
    
    def _safe_emit_finished(self, text: str):
        """安全地发送 finished 信号"""
        if self.isInterruptionRequested():
            return
        self._wait_for_modal_dialog()
        if not self.isInterruptionRequested():
            self.finished.emit(text)
    
    def _safe_emit_error(self, error_msg: str):
        """安全地发送 error 信号"""
        if self.isInterruptionRequested():
            return
        # 注意：移除了模态对话框等待，Anki 窗口使用 WindowStaysOnTopHint
        if not self.isInterruptionRequested():
            self.error.emit(error_msg)
    
    def run(self):
        try:
            # 检查是否已请求中断
            if self.isInterruptionRequested():
                return
            
            if self._image is None or self._image.isNull():
                self._safe_emit_error("图片为空")
                return
            
            # 裁剪高亮区域
            cropped = self._image.copy(self._rect)
            
            # 裁剪完成后释放原图引用
            self._image = None
            
            if cropped.isNull():
                self._safe_emit_error("裁剪区域为空")
                return
            
            # 检查是否已请求中断
            if self.isInterruptionRequested():
                return
            
            # 执行 OCR
            result = self._ocr_manager.recognize(cropped)
            
            # 释放裁剪图片
            del cropped
            
            # OCR 完成后再次检查中断状态，避免发送无用信号
            if self.isInterruptionRequested():
                return
            
            if result.success and result.text:
                self._safe_emit_finished(result.text)
            else:
                self._safe_emit_error(result.error or "识别失败")
        except Exception as e:
            if not self.isInterruptionRequested():
                self._safe_emit_error(str(e))
        finally:
            # 确保图片引用被释放
            self._image = None


class AnkiImportWorker(QThread):
    """Anki 导入后台线程"""
    finished = Signal(object)  # AnkiImportResult
    progress = Signal(int, int, str)  # current, total, word
    
    def __init__(self, words: list, deck_name: str, screenshot_path: str = None):
        super().__init__()
        self._words = words
        self._deck_name = deck_name
        self._screenshot_path = screenshot_path
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        try:
            from screenshot_tool.services.anki_service import AnkiService, AnkiImportResult
            service = AnkiService()
            
            def progress_callback(current, total, word):
                if self._cancelled:
                    raise InterruptedError("用户取消")
                self.progress.emit(current, total, word)
            
            result = service.import_words(
                self._words,
                self._deck_name,
                screenshot_path=self._screenshot_path,
                progress_callback=progress_callback
            )
            self.finished.emit(result)
        except InterruptedError:
            from screenshot_tool.services.anki_service import AnkiImportResult
            self.finished.emit(AnkiImportResult.error_result("已取消导入"))
        except Exception as e:
            from screenshot_tool.services.anki_service import AnkiImportResult
            self.finished.emit(AnkiImportResult.error_result(str(e)))


class AnkiCardWindow(QWidget):
    """Anki 制卡窗口"""
    
    # 窗口关闭信号
    windowClosed = Signal()
    
    # 单选按钮基础样式（类常量，避免重复定义）
    # 隐藏圆圈指示器，但保留点击区域
    _RADIO_BASE_STYLE = """
        QRadioButton {
            border: none;
            spacing: 4px;
            padding: 4px 8px;
            min-height: 20px;
        }
        QRadioButton::indicator {
            width: 0px;
            height: 0px;
            margin: 0px;
            padding: 0px;
            border: none;
            background: transparent;
            image: none;
        }
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: Optional[QImage] = None
        self._image_with_markers: Optional[QImage] = None  # 带高亮标记的截图
        self._marker_rects: List[QRect] = []
        self._highlight_color: str = "#FFFF00"  # 默认黄色
        self._ocr_manager = None
        self._ocr_workers: List[OCRWorker] = []
        self._screenshot_path: Optional[str] = None  # 临时截图文件路径
        self._pending_ocr_count = 0
        self._ocr_results: List[str] = []
        self._ocr_mutex = QMutex()  # 保护 OCR 计数器的互斥锁
        self._import_submitted = False  # 标记是否已提交导入任务
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面"""
        self.setWindowTitle("Anki 单词卡制作")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(500, 400)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("📚 Anki 单词卡制作")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #4CAF50;")
        layout.addWidget(title)
        
        # 说明
        hint = QLabel("高亮区域的单词已自动识别，勾选后点击导入按钮")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：预览图
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        
        preview_title = QLabel("预览 (滚轮缩放，拖动平移)")
        preview_title.setStyleSheet("font-weight: bold; color: #333;")
        preview_layout.addWidget(preview_title)
        
        # 使用可缩放预览组件
        self._preview_widget = ZoomablePreviewWidget()
        self._preview_widget.setMinimumSize(200, 150)
        self._preview_widget.zoomChanged.connect(self._on_preview_zoom_changed)
        preview_layout.addWidget(self._preview_widget, 1)
        
        # 缩放控制栏
        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(6)
        
        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color: #666; font-size: 11px;")
        zoom_layout.addWidget(self._zoom_label)
        
        zoom_layout.addStretch()
        
        self._reset_zoom_btn = QPushButton("重置")
        self._reset_zoom_btn.setFixedHeight(24)
        self._reset_zoom_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 2px 8px;
                background-color: #f5f5f5;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
        """)
        self._reset_zoom_btn.clicked.connect(self._reset_preview_zoom)
        zoom_layout.addWidget(self._reset_zoom_btn)
        
        preview_layout.addLayout(zoom_layout)
        
        splitter.addWidget(preview_frame)
        
        # 右侧：单词列表
        words_frame = QFrame()
        words_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        words_frame.setMinimumWidth(150)  # 最小宽度
        words_layout = QVBoxLayout(words_frame)
        words_layout.setContentsMargins(8, 8, 8, 8)
        
        words_label = QLabel("识别到的单词")
        words_label.setStyleSheet("font-weight: bold; color: #333;")
        words_layout.addWidget(words_label)
        
        self._words_list = QListWidget()
        self._words_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # 支持多选
        self._words_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #fefefe;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #4CAF50;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #e8f5e9;
            }
        """)
        self._words_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._words_list.customContextMenuRequested.connect(self._show_word_context_menu)
        self._words_list.itemChanged.connect(self._on_word_item_changed)
        self._words_list.itemSelectionChanged.connect(self._update_word_count)
        words_layout.addWidget(self._words_list, 1)
        
        # 手动输入区域
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)
        
        self._word_input = QLineEdit()
        self._word_input.setPlaceholderText("输入单词/词组/句子，按回车添加")
        self._word_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 8px;
                background-color: #fff;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)
        self._word_input.returnPressed.connect(self._add_word_from_input)
        input_layout.addWidget(self._word_input, 1)
        
        self._add_word_btn = QPushButton("➕")
        self._add_word_btn.setFixedSize(28, 28)
        self._add_word_btn.setToolTip("添加单词")
        self._add_word_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #4CAF50;
                border-radius: 4px;
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:pressed { background-color: #388E3C; }
        """)
        self._add_word_btn.clicked.connect(self._add_word_from_input)
        input_layout.addWidget(self._add_word_btn)
        
        words_layout.addLayout(input_layout)
        
        # 单词数量统计
        self._count_label = QLabel("共 0 个单词")
        self._count_label.setStyleSheet("color: #666; font-size: 11px;")
        words_layout.addWidget(self._count_label)
        
        splitter.addWidget(words_frame)
        splitter.setSizes([450, 150])  # 预览区域更大，单词列表更小
        
        layout.addWidget(splitter, 1)
        
        # 状态标签
        self._status_label = QLabel("请先用高亮工具标记单词区域")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)
        
        # 牌组选择区域
        deck_frame = QFrame()
        deck_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        deck_frame.setStyleSheet("QFrame { background-color: #fff; border: 1px solid #ddd; border-radius: 4px; }")
        deck_layout = QVBoxLayout(deck_frame)
        deck_layout.setContentsMargins(10, 8, 10, 8)
        deck_layout.setSpacing(6)
        
        deck_title = QLabel("📁 导入到牌组")
        deck_title.setStyleSheet("font-weight: bold; color: #333; border: none;")
        deck_layout.addWidget(deck_title)
        
        # 单选按钮样式（选中绿色，未选中灰色，完全隐藏圆圈指示器）
        radio_style = self._RADIO_BASE_STYLE
        
        # 选项1：日期牌组（默认）
        option1_layout = QHBoxLayout()
        option1_layout.setSpacing(8)
        self._date_radio = QRadioButton("今日日期")
        self._date_radio.setChecked(True)
        self._date_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._date_radio.setStyleSheet(radio_style + "QRadioButton { color: #4CAF50; font-weight: bold; }")
        option1_layout.addWidget(self._date_radio)
        
        self._date_label = QLabel(datetime.now().strftime("%Y年%m月%d日"))
        self._date_label.setStyleSheet("color: #4CAF50; font-weight: bold; border: none;")
        option1_layout.addWidget(self._date_label)
        option1_layout.addStretch()
        deck_layout.addLayout(option1_layout)
        
        # 选项2：选择已有牌组
        option2_layout = QHBoxLayout()
        option2_layout.setSpacing(8)
        self._custom_radio = QRadioButton("选择牌组")
        self._custom_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_radio.setStyleSheet(radio_style + "QRadioButton { color: #666; font-weight: normal; }")
        option2_layout.addWidget(self._custom_radio)
        
        self._deck_combo = QComboBox()
        self._deck_combo.setMinimumWidth(200)
        self._deck_combo.setEnabled(False)
        self._deck_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #fafafa;
            }
            QComboBox:enabled {
                background-color: #fff;
            }
            QComboBox:disabled {
                background-color: #f0f0f0;
                color: #999;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        option2_layout.addWidget(self._deck_combo, 1)
        
        # 刷新按钮
        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setToolTip("刷新牌组列表")
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #fafafa;
            }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton:disabled { background-color: #f0f0f0; color: #999; }
        """)
        self._refresh_btn.clicked.connect(self._refresh_deck_list)
        option2_layout.addWidget(self._refresh_btn)
        
        deck_layout.addLayout(option2_layout)
        
        layout.addWidget(deck_frame)
        
        # 单选按钮组
        self._deck_group = QButtonGroup(self)
        self._deck_group.addButton(self._date_radio, 0)
        self._deck_group.addButton(self._custom_radio, 1)
        self._deck_group.buttonClicked.connect(self._on_deck_option_changed)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_layout.addStretch()
        
        # 导入按钮
        self._import_btn = QPushButton("📥 导入到 Anki")
        self._import_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:pressed { background-color: #388E3C; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._import_btn.clicked.connect(self._do_import)
        self._import_btn.setEnabled(False)
        btn_layout.addWidget(self._import_btn)
        
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("QWidget { background-color: #f5f5f5; }")
    
    def _on_deck_option_changed(self, button):
        """牌组选项改变"""
        is_custom = (button == self._custom_radio)
        self._deck_combo.setEnabled(is_custom)
        self._refresh_btn.setEnabled(is_custom)
        
        # 更新单选按钮样式（选中的绿色加粗，未选中的灰色）
        if is_custom:
            self._date_radio.setStyleSheet(self._RADIO_BASE_STYLE + "QRadioButton { color: #666; font-weight: normal; }")
            self._custom_radio.setStyleSheet(self._RADIO_BASE_STYLE + "QRadioButton { color: #4CAF50; font-weight: bold; }")
            self._date_label.setStyleSheet("color: #999; font-weight: normal; border: none;")
        else:
            self._date_radio.setStyleSheet(self._RADIO_BASE_STYLE + "QRadioButton { color: #4CAF50; font-weight: bold; }")
            self._custom_radio.setStyleSheet(self._RADIO_BASE_STYLE + "QRadioButton { color: #666; font-weight: normal; }")
            self._date_label.setStyleSheet("color: #4CAF50; font-weight: bold; border: none;")
        
        # 首次选择自定义时，加载牌组列表
        if is_custom and self._deck_combo.count() == 0:
            self._refresh_deck_list()
    
    def _show_word_context_menu(self, pos):
        """显示单词列表右键菜单"""
        from PySide6.QtWidgets import QMenu
        
        menu = QMenu(self)
        
        # 删除选中项
        delete_action = menu.addAction("🗑️ 删除")
        delete_action.triggered.connect(self._delete_selected_words)
        
        # 全部删除
        delete_all_action = menu.addAction("🗑️ 全部删除")
        delete_all_action.triggered.connect(self._delete_all_words)
        
        menu.exec(self._words_list.mapToGlobal(pos))
    
    def _delete_selected_words(self):
        """删除选中的单词"""
        selected_items = self._words_list.selectedItems()
        if not selected_items:
            # 如果没有选中，删除当前项
            current = self._words_list.currentItem()
            if current:
                row = self._words_list.row(current)
                self._words_list.takeItem(row)
        else:
            # 删除所有选中项（从后往前删除，避免索引变化问题）
            rows_to_delete = sorted([self._words_list.row(item) for item in selected_items], reverse=True)
            for row in rows_to_delete:
                self._words_list.takeItem(row)
        
        self._update_word_count()
    
    def _delete_all_words(self):
        """删除所有单词"""
        self._words_list.clear()
        self._update_word_count()
    
    def _on_word_item_changed(self, item):
        """单词项内容改变（编辑后触发）"""
        if item is None:
            return
        
        # 如果编辑后内容为空，自动删除该项
        text = item.text().strip()
        if not text:
            # 阻止信号避免递归
            self._words_list.blockSignals(True)
            try:
                row = self._words_list.row(item)
                if row >= 0:
                    self._words_list.takeItem(row)
            finally:
                self._words_list.blockSignals(False)
        
        self._update_word_count()
    
    def _update_word_count(self):
        """更新单词计数"""
        total = self._words_list.count()
        
        if total == 0:
            self._count_label.setText("共 0 个单词")
            self._status_label.setText("没有单词，将使用虎哥原图模板导入")
        else:
            self._count_label.setText(f"共 {total} 个单词")
            self._status_label.setText(f"点击单词可编辑，导入时将导入全部 {total} 个单词")
    
    def _add_word_from_input(self):
        """从输入框添加单词/词组/句子"""
        text = self._word_input.text().strip()
        if not text:
            return
        
        # 限制单次输入长度（防止意外粘贴大量文本）
        if len(text) > 5000:
            text = text[:5000]
        
        # 支持多行输入（用户可能粘贴多行文本）
        lines = text.split('\n')
        added_count = 0
        
        # 构建现有单词的集合（用于快速去重检查）
        existing_words = set()
        for i in range(self._words_list.count()):
            existing_words.add(self._words_list.item(i).text().lower())
        
        # 暂时阻止信号，避免多次触发更新
        self._words_list.blockSignals(True)
        try:
            for line in lines:
                word = line.strip()
                if not word or len(word) > 500:  # 限制单个条目长度
                    continue
                
                # 检查是否已存在（不区分大小写）
                if word.lower() not in existing_words:
                    item = QListWidgetItem(word)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    self._words_list.addItem(item)
                    item.setSelected(True)  # 新添加的单词自动选中
                    existing_words.add(word.lower())
                    added_count += 1
        finally:
            self._words_list.blockSignals(False)
        
        # 清空输入框
        self._word_input.clear()
        
        # 更新计数
        if added_count > 0:
            self._update_word_count()
            # 滚动到最后添加的项
            self._words_list.scrollToBottom()
    
    def _refresh_deck_list(self):
        """刷新牌组列表"""
        from screenshot_tool.services.anki_service import AnkiService
        
        self._deck_combo.clear()
        self._deck_combo.addItem("加载中...")
        self._refresh_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            decks = AnkiService.get_deck_names()
            self._deck_combo.clear()
            
            if decks:
                for deck in sorted(decks):
                    self._deck_combo.addItem(deck)
                self._deck_combo.setCurrentIndex(0)
            else:
                self._deck_combo.addItem("(无牌组)")
        except Exception as e:
            self._deck_combo.clear()
            self._deck_combo.addItem(f"(加载失败: {str(e)[:20]})")
        
        self._refresh_btn.setEnabled(True)
    
    def _get_selected_deck_name(self) -> str:
        """获取选中的牌组名称"""
        if self._date_radio.isChecked():
            return datetime.now().strftime("%Y年%m月%d日")
        else:
            deck = self._deck_combo.currentText()
            if deck and not deck.startswith("("):
                return deck
            # 如果没有有效选择，回退到日期
            return datetime.now().strftime("%Y年%m月%d日")
    
    def set_data(self, image: QImage, marker_rects: list, ocr_manager, highlight_color: str = "#FFFF00", pre_recognized_words: list = None):
        """设置数据并自动开始 OCR 识别
        
        Args:
            image: 截图
            marker_rects: 高亮区域列表
            ocr_manager: OCR 管理器（向后兼容）
            highlight_color: 高亮颜色
            pre_recognized_words: 预识别的单词列表（新增，如果提供则直接显示）
        """
        # 更新日期标签（确保显示当前日期）
        self._date_label.setText(datetime.now().strftime("%Y年%m月%d日"))
        
        # 清理之前的临时文件
        self._cleanup_temp_file()
        
        self._image = image.copy() if image else None
        self._marker_rects = marker_rects or []
        self._ocr_manager = ocr_manager
        self._highlight_color = highlight_color or "#FFFF00"
        self._words_list.clear()
        self._ocr_results.clear()
        self._screenshot_path = None
        self._word_input.clear()  # 清空输入框
        self._import_submitted = False  # 重置导入状态
        
        # 创建带高亮标记的截图
        self._create_marked_image()
        
        # 更新预览图
        self._update_preview()
        
        # 处理预识别单词
        if pre_recognized_words and len(pre_recognized_words) > 0:
            # 有预识别单词，直接显示
            self._display_pre_recognized_words(pre_recognized_words)
        elif not self._marker_rects:
            # 没有高亮区域
            self._status_label.setText("没有高亮区域，可直接导入截图")
            self._import_btn.setEnabled(True)  # 允许导入纯图片
            self._count_label.setText("共 0 个单词")
        else:
            # 有高亮区域但没有预识别单词，回退到原有 OCR 流程
            self._status_label.setText("正在识别单词...")
            self._import_btn.setEnabled(False)
            self._count_label.setText("共 0 个单词")
            # 自动开始 OCR
            self._do_ocr()
    
    def _display_pre_recognized_words(self, words: list):
        """显示预识别的单词列表
        
        Args:
            words: 预识别的单词列表
        """
        self._words_list.clear()
        self._ocr_results.clear()
        
        if not words:
            self._count_label.setText("共 0 个单词")
            self._status_label.setText("没有识别到单词，可直接导入截图")
            # 即使没有单词，也允许导入纯图片
            self._import_btn.setEnabled(True)
            return
        
        for word in words:
            if word and isinstance(word, str) and word.strip():
                word = word.strip()
                self._ocr_results.append(word)
                item = QListWidgetItem(word)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._words_list.addItem(item)
        
        count = len(self._ocr_results)
        self._count_label.setText(f"共 {count} 个单词")
        self._status_label.setText(f"已识别 {count} 个单词（后台预处理）")
        # 无论是否有单词都启用导入按钮
        self._import_btn.setEnabled(True)
    
    def _cleanup_temp_file(self):
        """清理临时截图文件"""
        import os
        if self._screenshot_path and os.path.exists(self._screenshot_path):
            try:
                os.remove(self._screenshot_path)
            except OSError:
                pass  # 删除失败不影响使用
            self._screenshot_path = None
    
    def _create_marked_image(self):
        """创建带高亮标记的截图并保存到临时文件
        
        注意：传入的 image 已经是 _get_result_image() 返回的结果，
        已经包含了在 overlay 中绘制的高亮标记，不需要再次绘制。
        """
        import tempfile
        import os
        
        if self._image is None or self._image.isNull():
            self._image_with_markers = None
            return
        
        # 直接使用传入的图片（已包含高亮标记）
        self._image_with_markers = self._image.copy()
        
        # 保存到临时文件（使用 UUID 避免文件名冲突）
        try:
            temp_dir = tempfile.gettempdir()
            unique_id = uuid.uuid4().hex[:8]
            self._screenshot_path = os.path.join(temp_dir, f"anki_screenshot_{unique_id}.png")
            self._image_with_markers.save(self._screenshot_path, "PNG")
        except Exception as e:
            print(f"[Anki] 保存截图失败: {e}")
            self._screenshot_path = None
    
    def _update_preview(self):
        """更新预览图"""
        # 使用带高亮标记的图片
        preview_image = self._image_with_markers if self._image_with_markers else self._image
        
        if preview_image is None or preview_image.isNull():
            self._preview_widget.set_image(None)
            return
        
        # 设置图片到可缩放预览组件
        self._preview_widget.set_image(preview_image)
    
    def _on_preview_zoom_changed(self, zoom_percent: int):
        """预览缩放变化回调"""
        self._zoom_label.setText(f"{zoom_percent}%")
    
    def _reset_preview_zoom(self):
        """重置预览缩放"""
        self._preview_widget.reset_zoom()
    
    def _do_ocr(self):
        """执行 OCR 识别"""
        if not self._marker_rects or self._ocr_manager is None:
            return
        
        self._status_label.setText("正在识别...")
        self._ocr_results.clear()
        self._words_list.clear()
        
        # 清理之前的 worker（不使用 terminate() 避免崩溃）
        for worker in self._ocr_workers:
            if worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                # 增加等待时间，避免线程销毁问题
                if not worker.wait(1000):
                    # 不再使用 terminate()，放弃等待让线程自然结束
                    continue
        self._ocr_workers.clear()
        
        # 为每个高亮区域创建 OCR 任务
        self._pending_ocr_count = len(self._marker_rects)
        
        for i, rect in enumerate(self._marker_rects):
            worker = OCRWorker(self._ocr_manager, self._image, rect)
            worker.finished.connect(lambda text, idx=i: self._on_ocr_finished(text, idx))
            worker.error.connect(lambda err, idx=i: self._on_ocr_error(err, idx))
            self._ocr_workers.append(worker)
            worker.start()
    
    def _on_ocr_finished(self, text: str, index: int):
        """单个区域 OCR 完成"""
        self._ocr_mutex.lock()
        try:
            self._ocr_results.append(text)
            self._pending_ocr_count -= 1
            should_check = self._pending_ocr_count <= 0
        finally:
            self._ocr_mutex.unlock()
        
        if should_check:
            self._check_ocr_complete()
    
    def _on_ocr_error(self, error: str, index: int):
        """单个区域 OCR 失败"""
        self._ocr_mutex.lock()
        try:
            self._pending_ocr_count -= 1
            should_check = self._pending_ocr_count <= 0
        finally:
            self._ocr_mutex.unlock()
        
        if should_check:
            self._check_ocr_complete()
    
    def _check_ocr_complete(self):
        """检查所有 OCR 是否完成"""
        if self._pending_ocr_count > 0:
            return
        
        # 合并所有 OCR 结果并提取单词
        all_text = " ".join(self._ocr_results)
        words = self._extract_english_words(all_text)
        
        # 更新单词列表
        self._words_list.clear()
        for word in words:
            item = QListWidgetItem(word)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)  # 允许编辑
            self._words_list.addItem(item)
        
        # 更新状态
        self._count_label.setText(f"共 {len(words)} 个单词")
        
        if words:
            self._status_label.setText(f"识别完成，找到 {len(words)} 个单词（可右键删除）")
        else:
            self._status_label.setText("未识别到英文单词，将使用虎哥原图模板导入")
        
        # 无论是否有单词都启用导入按钮（没有单词时可以导入纯图片）
        self._import_btn.setEnabled(True)
        
        # 清理 worker（先断开信号，等待线程结束，再删除）
        for worker in self._ocr_workers:
            try:
                worker.finished.disconnect()
                worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
            if worker.isRunning():
                worker.quit()
                if not worker.wait(500):
                    # 不使用 terminate()，避免崩溃，放弃等待让线程自然结束
                    continue
            worker.deleteLater()
        self._ocr_workers.clear()
    
    def _extract_english_words(self, text: str) -> List[str]:
        """提取英文单词"""
        if not text:
            return []
        words = re.findall(r'[a-zA-Z]{2,}', text)
        seen = set()
        unique_words = []
        for word in words:
            word_lower = word.lower()
            if word_lower not in seen:
                seen.add(word_lower)
                unique_words.append(word_lower)
        return unique_words
    
    def _do_import(self):
        """导入到 Anki（使用后台导入管理器，关闭窗口后仍能继续）"""
        # 获取列表中所有单词（不是只获取选中的）
        words = [self._words_list.item(i).text().strip() 
                 for i in range(self._words_list.count()) 
                 if self._words_list.item(i).text().strip()]
        
        # 检查 Anki 服务
        from screenshot_tool.services.anki_service import AnkiService
        
        if not AnkiService.is_available():
            error_detail = AnkiService.get_import_error()
            msg = "Anki 服务不可用\n请确保 D:\\AnkiTrans\\单词卡工具 存在"
            if error_detail:
                msg += f"\n\n错误详情: {error_detail}"
            QMessageBox.warning(self, "提示", msg)
            return
        
        connected, error = AnkiService.check_connection()
        if not connected:
            QMessageBox.warning(self, "连接失败", f"{error}\n\n请确保 Anki 已启动并安装了 AnkiConnect 插件")
            return
        
        deck_name = self._get_selected_deck_name()
        
        # 检查是否有内容可导入
        has_words = len(words) > 0
        has_screenshot = self._screenshot_path is not None and os.path.exists(self._screenshot_path)
        
        if not has_words and not has_screenshot:
            QMessageBox.warning(self, "提示", "没有单词，也没有截图可导入")
            return
        
        # 使用后台导入管理器提交任务
        from screenshot_tool.services.background_anki_importer import BackgroundAnkiImporter
        
        importer = BackgroundAnkiImporter.instance()
        
        # 提交后台任务
        success = importer.submit_import(
            words=words,
            deck_name=deck_name,
            screenshot_path=self._screenshot_path if has_screenshot else None,
            on_finished=None  # 完成通知由 overlay_main 处理
        )
        
        if not success:
            QMessageBox.warning(self, "提交失败", "无法提交导入任务，请重试")
            return
        
        # 标记已提交导入，closeEvent 不再清理临时文件
        self._import_submitted = True
        
        # 更新状态并关闭窗口
        word_count = len(words)
        if word_count > 0:
            self._status_label.setText(f"已提交 {word_count} 个单词到后台导入...")
        else:
            self._status_label.setText("已提交截图到后台导入...")
        
        # 禁用导入按钮，防止重复提交
        self._import_btn.setEnabled(False)
        
        # 构建提示信息
        info_parts = []
        if has_words:
            info_parts.append(f"单词数: {word_count}")
        if has_screenshot:
            info_parts.append("包含截图")
        info_parts.append(f"牌组: {deck_name}")
        
        # 显示提示并关闭窗口
        QMessageBox.information(
            self,
            "已提交",
            f"导入任务已提交到后台处理\n\n"
            f"{chr(10).join(info_parts)}\n\n"
            f"您可以关闭此窗口，导入将在后台继续完成"
        )
        
        # 关闭窗口（后台任务会继续运行）
        self.close()
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件 - ESC键关闭窗口，Delete键删除选中单词"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Delete:
            # Delete键删除选中的单词
            if self._words_list.hasFocus():
                self._delete_selected_words()
                event.accept()
                return
        super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件
        
        注意：后台导入任务由 BackgroundAnkiImporter 管理，
        关闭窗口不会取消正在进行的导入。
        """
        # 清理 OCR workers（不使用 terminate() 避免崩溃）
        for worker in self._ocr_workers:
            try:
                worker.finished.disconnect()
                worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
            if worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                # 等待线程结束，超时则放弃（不使用 terminate()）
                if not worker.wait(1000):
                    # 放弃等待，让线程自然结束，避免崩溃
                    continue
            worker.deleteLater()
        self._ocr_workers.clear()
        
        # 如果没有提交导入任务，清理临时文件
        # 如果已提交，临时文件由 BackgroundAnkiImporter 管理
        if not self._import_submitted:
            self._cleanup_temp_file()
        
        # 发送关闭信号
        self.windowClosed.emit()
        
        super().closeEvent(event)
    
    def resizeEvent(self, event):
        """窗口大小变化"""
        super().resizeEvent(event)
        # ZoomablePreviewWidget 已有自己的 resizeEvent 处理
        # 不需要额外调用 _update_preview
