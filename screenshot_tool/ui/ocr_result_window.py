# =====================================================
# =============== 识别文字结果窗口 ===============
# =====================================================

"""
识别文字结果窗口 - 显示识别文字结果的独立窗口

功能：
- 显示识别的文字
- 复制、全选
- 简单排版（合并行、去空格等）
- 一键翻译（支持多语言）
- OCR引擎切换（RapidOCR / 百度OCR）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLabel, QToolButton, QMenu, QApplication,
    QStackedWidget, QTextBrowser, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread, QMimeData
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor, QImage
import re
from typing import Optional, TYPE_CHECKING

from screenshot_tool.services.markdown_parser import get_markdown_parser

if TYPE_CHECKING:
    from screenshot_tool.services.ocr_manager import OCRManager


class OCRWorker(QThread):
    """OCR后台线程"""
    finished = Signal(object)  # UnifiedOCRResult
    
    def __init__(self, image: QImage, engine: str, ocr_manager: "OCRManager"):
        super().__init__()
        # 复制图片以避免线程安全问题
        self._image = image.copy() if image and not image.isNull() else None
        self._engine = engine
        self._ocr_manager = ocr_manager
        self._should_stop = False
    
    def request_stop(self):
        """请求停止线程"""
        self._should_stop = True
    
    def _safe_emit(self, result):
        """安全地发送信号
        
        注意：移除了模态对话框检测，因为 OCR 结果窗口使用 WindowStaysOnTopHint，
        会显示在所有窗口之上，不会与模态对话框冲突。
        """
        if self._should_stop:
            return
        self.finished.emit(result)
    
    def run(self):
        """执行OCR识别
        
        在finally块中释放图片引用，确保内存被释放。
        Requirements: 3.1
        """
        try:
            if self._should_stop:
                return
            
            if self._image is None or self._image.isNull():
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self._safe_emit(UnifiedOCRResult.error_result("图片为空", self._engine))
                return
            
            result = self._ocr_manager.recognize_with_engine(self._image, self._engine)
            if not self._should_stop:
                self._safe_emit(result)
        except Exception as e:
            if not self._should_stop:
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self._safe_emit(UnifiedOCRResult.error_result(str(e), self._engine))
        finally:
            # 释放图片内存 (Requirements: 3.1)
            self._image = None


class TranslationWorker(QThread):
    """翻译后台线程"""
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


class OCRResultWindow(QWidget):
    """识别文字结果窗口"""
    
    closed = Signal()
    escape_pressed = Signal()  # ESC键按下信号，通知截图界面也要关闭
    engine_switch_requested = Signal(str)  # 引擎切换请求信号，参数为引擎名称
    
    # OCR引擎显示名称映射（类常量）
    ENGINE_DISPLAY_NAMES = {
        "baidu": "百度OCR",
        "tencent": "腾讯OCR",
        "rapid": "本地OCR",
    }
    
    # 评分颜色阈值（类常量）
    SCORE_COLOR_HIGH = (60, "#4CAF50")    # 绿色，60分及以上
    SCORE_COLOR_MEDIUM = (40, "#FF9800")  # 橙色，40-59分
    SCORE_COLOR_LOW = (0, "#F44336")      # 红色，40分以下
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_text = ""
        self._ocr_text = ""
        self._translated_text = ""
        self._is_showing_translation = False
        self._translation_worker = None
        self._ocr_worker = None
        self._current_engine = ""  # 当前显示的引擎
        self._current_image: Optional[QImage] = None  # 当前图片
        self._ocr_manager: Optional["OCRManager"] = None  # OCR管理器引用
        # 识别文字结果缓存：{engine_name: UnifiedOCRResult}
        # 用于引擎切换时避免重复识别
        self._ocr_cache: dict = {}
        # 翻译缓存：{(原文, 目标语言): 译文}
        # 避免相同内容重复调用翻译 API
        self._translation_cache: dict = {}
        self._pending_translation_key: Optional[tuple] = None  # 待缓存的翻译 key
        self._is_closing = False  # 防止重复关闭
        # Markdown 预览相关
        self._is_preview_mode = False  # 是否处于预览模式
        self._markdown_parser = get_markdown_parser()  # Markdown 解析器
        # 置顶状态
        self._is_pinned = False  # 是否置顶（置顶时截图保存后不关闭窗口）
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面"""
        self.setWindowTitle("识别文字结果")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(400, 300)
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        # 复制按钮
        self._copy_btn = self._create_button("复制", "复制全部文字")
        self._copy_btn.clicked.connect(self._copy_all)
        toolbar.addWidget(self._copy_btn)
        
        # 排版菜单
        self._format_btn = self._create_button("排版", "文字排版选项")
        format_menu = QMenu(self)
        format_menu.addAction("合并为单行", self._merge_to_single_line)
        format_menu.addAction("智能分段", self._smart_paragraphs)
        format_menu.addAction("去除所有空格", self._remove_all_spaces)
        format_menu.addAction("去除多余空格", self._remove_extra_spaces)
        format_menu.addSeparator()
        format_menu.addAction("中文标点→英文", self._chinese_punct_to_english)
        format_menu.addAction("英文标点→中文", self._english_punct_to_chinese)
        format_menu.addSeparator()
        format_menu.addAction("恢复原文", self._reset_text)
        self._format_btn.setMenu(format_menu)
        self._format_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(self._format_btn)
        
        toolbar.addSpacing(10)
        
        # 切换原文/译文按钮（放在翻译按钮左边）
        self._toggle_btn = self._create_button("原文", "恢复OCR原始结果")
        self._toggle_btn.clicked.connect(self._restore_original)
        self._toggle_btn.setEnabled(False)
        toolbar.addWidget(self._toggle_btn)
        
        # 翻译按钮（智能中英互译）
        self._translate_btn = self._create_button("翻译", "智能翻译（中↔英）")
        self._translate_btn.clicked.connect(self._do_smart_translate)
        toolbar.addWidget(self._translate_btn)
        
        toolbar.addStretch()
        
        # OCR引擎切换按钮
        self._rapid_btn = self._create_engine_button("本地", "使用本地OCR重新识别")
        self._rapid_btn.clicked.connect(lambda: self._switch_engine("rapid"))
        toolbar.addWidget(self._rapid_btn)
        
        self._tencent_btn = self._create_engine_button("腾讯", "使用腾讯OCR重新识别")
        self._tencent_btn.clicked.connect(lambda: self._switch_engine("tencent"))
        toolbar.addWidget(self._tencent_btn)
        
        self._baidu_btn = self._create_engine_button("百度", "使用百度OCR重新识别")
        self._baidu_btn.clicked.connect(lambda: self._switch_engine("baidu"))
        toolbar.addWidget(self._baidu_btn)
        
        toolbar.addSpacing(10)
        
        # 字数统计
        self._count_label = QLabel("0 字")
        self._count_label.setStyleSheet("color: #666; font-size: 11px;")
        toolbar.addWidget(self._count_label)
        
        # Markdown 格式按钮
        self._preview_btn = self._create_button("MD格式", "切换 Markdown 格式预览 (Ctrl+P)")
        self._preview_btn.setCheckable(True)
        self._preview_btn.clicked.connect(self._toggle_preview_mode)
        toolbar.addWidget(self._preview_btn)
        
        # 置顶按钮
        self._pin_btn = self._create_button("置顶", "置顶窗口（置顶后截图保存时不关闭此窗口）")
        self._pin_btn.setCheckable(True)
        self._pin_btn.clicked.connect(self._toggle_pin)
        toolbar.addWidget(self._pin_btn)
        
        layout.addLayout(toolbar)
        
        # 内容区域堆栈（编辑/预览切换）
        self._content_stack = QStackedWidget()
        
        # 文本编辑区（索引 0）
        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont("Microsoft YaHei", 11))
        self._text_edit.setPlaceholderText("识别文字结果将显示在这里...")
        self._text_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                background-color: #fefefe;
            }
            QTextEdit:focus { border-color: #4A90D9; }
        """)
        self._text_edit.textChanged.connect(self._update_count)
        self._content_stack.addWidget(self._text_edit)
        
        # Markdown 预览区（索引 1）
        self._preview_browser = QTextBrowser()
        self._preview_browser.setFont(QFont("Microsoft YaHei", 11))
        self._preview_browser.setOpenExternalLinks(True)
        self._preview_browser.setStyleSheet("""
            QTextBrowser {
                border: 2px solid #2563EB;
                border-radius: 4px;
                padding: 8px;
                background-color: #FFFFFF;
            }
        """)
        self._content_stack.addWidget(self._preview_browser)
        
        layout.addWidget(self._content_stack)
        
        # 底部状态栏
        status_bar = QHBoxLayout()
        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        status_bar.addWidget(self._status_label)
        
        self._engine_label = QLabel("")
        self._engine_label.setStyleSheet("color: #4A90D9; font-size: 10px;")
        status_bar.addWidget(self._engine_label)
        
        status_bar.addStretch()
        layout.addLayout(status_bar)
        
        self.setStyleSheet("QWidget { background-color: #f5f5f5; }")
    
    def _create_button(self, text: str, tooltip: str) -> QToolButton:
        """创建工具按钮"""
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QToolButton:hover { background-color: #e8f4fc; border-color: #4A90D9; }
            QToolButton:pressed { background-color: #d0e8f8; }
            QToolButton:disabled { background-color: #f0f0f0; color: #999; }
            QToolButton::menu-indicator { image: none; }
        """)
        return btn
    
    def _create_engine_button(self, text: str, tooltip: str) -> QToolButton:
        """创建引擎切换按钮"""
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QToolButton:hover { background-color: #e8f4fc; border-color: #4A90D9; }
            QToolButton:pressed { background-color: #d0e8f8; }
            QToolButton:checked { background-color: #4A90D9; color: white; border-color: #3a7bc8; }
            QToolButton:disabled { background-color: #f0f0f0; color: #999; }
        """)
        return btn
    
    def set_image(self, image: QImage):
        """设置当前图片（用于引擎切换时重新识别）
        
        Args:
            image: 要保存的图片，会被复制以避免外部修改影响
        """
        if image is not None and not image.isNull():
            self._current_image = image.copy()
        else:
            self._current_image = None
        # 图片变化时清空缓存
        self._ocr_cache = {}
    
    def set_ocr_manager(self, manager: "OCRManager"):
        """设置OCR管理器引用"""
        self._ocr_manager = manager
        self._update_engine_buttons()
    
    def _update_engine_buttons(self):
        """更新引擎按钮状态（未配置API时隐藏按钮）"""
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
        self._rapid_btn.setToolTip(f"本地OCR: {rapid_msg}")
        
        # 腾讯OCR：未配置时隐藏按钮
        tencent_available = status.get("tencent", {}).get("available", False)
        tencent_msg = status.get("tencent", {}).get("message", "")
        if tencent_available:
            self._tencent_btn.show()
            self._tencent_btn.setEnabled(True)
            self._tencent_btn.setToolTip(f"腾讯OCR: {tencent_msg}")
        else:
            self._tencent_btn.hide()
        
        # 百度OCR：未配置时隐藏按钮
        baidu_available = status.get("baidu", {}).get("available", False)
        baidu_msg = status.get("baidu", {}).get("message", "")
        if baidu_available:
            self._baidu_btn.show()
            self._baidu_btn.setEnabled(True)
            self._baidu_btn.setToolTip(f"百度OCR: {baidu_msg}")
        else:
            self._baidu_btn.hide()
        
        # 高亮当前引擎
        self._highlight_current_engine()
    
    def _highlight_current_engine(self):
        """高亮当前使用的引擎按钮"""
        engine = self._current_engine
        
        self._rapid_btn.setChecked(engine == "rapid")
        self._tencent_btn.setChecked(engine == "tencent")
        self._baidu_btn.setChecked(engine == "baidu")
    
    def _format_score_display(self, score: float) -> tuple:
        """
        格式化评分显示
        
        Args:
            score: 0.0-1.0 的置信度分数
            
        Returns:
            Tuple[显示文本, 颜色代码]
        """
        import math
        
        # 处理无效分数（NaN、Inf）
        if not math.isfinite(score):
            score = 0.0
        
        # 转换为百分制并取整
        score_100 = int(round(score * 100))
        # 确保在 0-100 范围内
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
    
    def _format_backend_display(self, backend_detail: str) -> str:
        """
        格式化后端信息显示
        
        Args:
            backend_detail: 后端详细信息字符串
            
        Returns:
            显示文本
        """
        if backend_detail:
            return backend_detail
        return "本地OCR"
    
    def _switch_engine(self, engine: str):
        """切换OCR引擎并重新识别"""
        if self._ocr_manager is None:
            self._status_label.setText("OCR管理器未设置")
            return
        
        if self._current_image is None or self._current_image.isNull():
            self._status_label.setText("没有可识别的图片")
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
        
        cache_key = engine
        
        # 检查缓存：如果已有该引擎的识别结果，直接使用
        if cache_key in self._ocr_cache:
            cached_result = self._ocr_cache[cache_key]
            if cached_result.success:
                self._status_label.setText(f"使用缓存结果 [{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
                # 从缓存中提取完整信息
                average_score = getattr(cached_result, 'average_score', 0.0)
                backend_detail = getattr(cached_result, 'backend_detail', "")
                elapsed_time = getattr(cached_result, 'elapsed_time', 0.0)
                self.set_text(cached_result.text, cached_result.engine, average_score, backend_detail, elapsed_time)
                self._highlight_current_engine()
                return
        
        # 发出引擎切换信号
        self.engine_switch_requested.emit(engine)
        
        # 开始后台识别
        self._status_label.setText(f"正在使用 {self.ENGINE_DISPLAY_NAMES.get(engine, engine)} 识别...")
        # 只禁用可见的按钮，避免对隐藏按钮的无效操作
        self._rapid_btn.setEnabled(False)
        if self._tencent_btn.isVisible():
            self._tencent_btn.setEnabled(False)
        if self._baidu_btn.isVisible():
            self._baidu_btn.setEnabled(False)
        
        self._ocr_worker = OCRWorker(self._current_image, engine, self._ocr_manager)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.start()
    
    def _on_ocr_finished(self, result):
        """OCR识别完成回调"""
        # 恢复按钮状态
        self._update_engine_buttons()
        
        if result is None:
            self._status_label.setText("识别失败: 未知错误")
            self._text_edit.setPlaceholderText("识别失败")
            return
        
        if result.success:
            # 缓存识别结果
            cache_key = result.engine
            if cache_key:
                self._ocr_cache[cache_key] = result
            
            # 提取评分和后端信息
            average_score = getattr(result, 'average_score', 0.0)
            backend_detail = getattr(result, 'backend_detail', "")
            elapsed_time = getattr(result, 'elapsed_time', 0.0)
            
            self.set_text(result.text, result.engine, average_score, backend_detail, elapsed_time)
            self._highlight_current_engine()
        else:
            error = result.error or "识别失败"
            self._status_label.setText(f"识别失败: {error}")
            self._text_edit.setPlaceholderText("识别失败")
        
        # 清理worker
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
    
    def set_text(self, text: str, engine: str = "", average_score: float = 0.0, backend_detail: str = "", elapsed_time: float = 0.0):
        """设置识别文字结果文本
        
        Args:
            text: OCR识别的文本
            engine: 引擎名称 (rapid/baidu/tencent)
            average_score: 平均置信度分数 (0.0-1.0)
            backend_detail: 后端详细信息（如 "本地OCR (OpenVINO加速)"）
            elapsed_time: OCR 耗时（秒）
        """
        self._original_text = text
        self._ocr_text = text
        self._translated_text = ""
        self._is_showing_translation = False
        self._current_engine = engine
        # OCR 内容变化时清空翻译缓存
        self._translation_cache = {}
        self._text_edit.setPlainText(text)
        # 重置 placeholder，避免空结果时仍显示"正在识别中..."
        if text:
            self._text_edit.setPlaceholderText("识别文字结果将显示在这里...")
        else:
            self._text_edit.setPlaceholderText("未识别到文字内容")
        self._toggle_btn.setEnabled(False)
        self._toggle_btn.setText("原文")
        self._status_label.setText("识别完成" if text else "识别完成（无文字）")
        
        # 构建引擎标签显示
        if engine:
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
                    html_parts.append(f"<span style='color: #888;'>耗时 {elapsed_time:.2f}秒</span>")
                
                self._engine_label.setText(" ".join(html_parts))
                self._engine_label.setTextFormat(Qt.TextFormat.RichText)
            else:
                # 云端 OCR 只显示引擎名称
                self._engine_label.setText(f"[{self.ENGINE_DISPLAY_NAMES.get(engine, engine)}]")
                self._engine_label.setTextFormat(Qt.TextFormat.PlainText)
            
            # 缓存结果（如果还没有缓存）
            cache_key = engine
            if cache_key and cache_key not in self._ocr_cache:
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self._ocr_cache[cache_key] = UnifiedOCRResult(
                    success=True, text=text, engine=engine,
                    average_score=average_score, backend_detail=backend_detail,
                    elapsed_time=elapsed_time
                )
        else:
            self._engine_label.setText("")
            self._engine_label.setTextFormat(Qt.TextFormat.PlainText)
    
    def set_loading(self):
        """设置加载状态"""
        self._text_edit.setPlainText("")
        self._text_edit.setPlaceholderText("正在识别中...")
        self._status_label.setText("识别中...")
        self._engine_label.setText("")
    
    def set_error(self, error: str):
        """设置错误状态"""
        self._text_edit.setPlainText(f"识别失败: {error}")
        self._text_edit.setPlaceholderText("识别失败")
        self._status_label.setText("识别失败")
        self._engine_label.setText("")
    
    def _update_count(self):
        """更新字数统计"""
        text = self._text_edit.toPlainText()
        char_count = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        self._count_label.setText(f"{char_count} 字")
    
    def _toggle_preview_mode(self):
        """切换预览/编辑模式
        
        Requirements: 1.1, 1.2, 1.3, 4.1, 4.2
        """
        if self._is_preview_mode:
            # 切换到编辑模式
            self._is_preview_mode = False
            self._content_stack.setCurrentIndex(0)
            self._preview_btn.setText("MD格式")
            self._preview_btn.setChecked(False)
            self._preview_btn.setStyleSheet("""
                QToolButton {
                    background-color: #fff;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                }
                QToolButton:hover { background-color: #e8f4fc; border-color: #4A90D9; }
                QToolButton:pressed { background-color: #d0e8f8; }
            """)
            self._status_label.setText("已切换到编辑模式")
        else:
            # 切换到预览模式
            text = self._text_edit.toPlainText()
            
            # 长文本警告（>50,000 字符）
            if len(text) > 50000:
                reply = QMessageBox.question(
                    self,
                    "长文本警告",
                    f"文本较长（{len(text)} 字符），预览可能需要一些时间，是否继续？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self._preview_btn.setChecked(False)
                    return
            
            self._render_markdown()
            self._is_preview_mode = True
            self._content_stack.setCurrentIndex(1)
            self._preview_btn.setText("普通")
            self._preview_btn.setChecked(True)
            self._preview_btn.setStyleSheet("""
                QToolButton {
                    background-color: #2563EB;
                    color: white;
                    border: 1px solid #1D4ED8;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                }
                QToolButton:hover { background-color: #1D4ED8; }
                QToolButton:pressed { background-color: #1E40AF; }
            """)
            self._status_label.setText("已切换到预览模式")
    
    def _toggle_pin(self):
        """切换置顶状态
        
        置顶后截图保存时不关闭此窗口，方便连续截图识别。
        """
        self._is_pinned = not self._is_pinned
        self._pin_btn.setChecked(self._is_pinned)
        
        if self._is_pinned:
            self._pin_btn.setStyleSheet("""
                QToolButton {
                    background-color: #F59E0B;
                    color: white;
                    border: 1px solid #D97706;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                }
                QToolButton:hover { background-color: #D97706; }
                QToolButton:pressed { background-color: #B45309; }
            """)
            self._status_label.setText("已置顶（截图保存后不关闭此窗口）")
        else:
            self._pin_btn.setStyleSheet("""
                QToolButton {
                    background-color: #fff;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                }
                QToolButton:hover { background-color: #e8f4fc; border-color: #4A90D9; }
                QToolButton:pressed { background-color: #d0e8f8; }
            """)
            self._status_label.setText("已取消置顶")
    
    def is_pinned(self) -> bool:
        """获取置顶状态
        
        Returns:
            True 如果窗口已置顶
        """
        return self._is_pinned
    
    def _render_markdown(self):
        """渲染 Markdown 到预览区域
        
        Requirements: 1.1, 4.3, 4.4, 4.5, 5.3
        """
        text = self._text_edit.toPlainText()
        if not text:
            self._preview_browser.setHtml("<p style='color: #9CA3AF;'>无内容可预览</p>")
            return
        
        # 使用 Markdown 解析器转换
        html = self._markdown_parser.parse(text)
        self._preview_browser.setHtml(html)
    
    def _copy_all(self):
        """复制全部文字
        
        预览模式下复制富文本（HTML + 纯文本双格式），
        编辑模式下复制纯文本。
        
        Requirements: 3.1, 3.4, 3.5
        """
        if self._is_preview_mode:
            # 预览模式：复制富文本
            self._copy_rich_text()
        else:
            # 编辑模式：复制纯文本
            text = self._text_edit.toPlainText()
            if text:
                QApplication.clipboard().setText(text)
                self._status_label.setText("已复制到剪贴板")
            else:
                self._status_label.setText("没有可复制的内容")
    
    def _copy_rich_text(self):
        """复制富文本到剪贴板（HTML + 纯文本双格式）
        
        使用 QMimeData 同时设置 HTML 和纯文本格式，
        确保粘贴到 Word 等应用时保留格式。
        
        Requirements: 3.1, 3.4, 3.5
        """
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
    
    def _do_smart_translate(self):
        """智能翻译 - 自动检测语言并翻译
        
        - 检测到中文 → 翻译成英语
        - 检测到英文 → 翻译成中文
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
        
        # 调用通用翻译方法（跳过重复检查）
        self._do_translate_internal(text, target_lang)
    
    def _do_translate(self, target_lang: str):
        """执行翻译（公共入口，带完整检查）
        
        始终基于原始 OCR 文本进行翻译，而不是当前文本框中的内容。
        这样无论用户当前看的是原文还是译文，翻译结果都是一致的。
        
        Args:
            target_lang: 目标语言（"英语" 或 "中文"）
        """
        text = self._ocr_text.strip() if self._ocr_text else self._text_edit.toPlainText().strip()
        if not text:
            self._status_label.setText("没有可翻译的文字")
            return
        
        if self._translation_worker and self._translation_worker.isRunning():
            self._status_label.setText("翻译进行中，请稍候...")
            return
        
        self._do_translate_internal(text, target_lang)
    
    def _do_translate_internal(self, text: str, target_lang: str):
        """执行翻译（内部实现，假设已完成前置检查）
        
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
        
        # 安全访问属性，防止result为None或属性不存在
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
        """显示登录对话框"""
        from screenshot_tool.ui.login_dialog import LoginDialog
        from screenshot_tool.services.subscription import SubscriptionManager
        
        manager = SubscriptionManager.instance()
        if manager and manager.auth_service:
            dialog = LoginDialog(manager.auth_service, parent=self)
            dialog.login_success.connect(self._on_login_success)
            # 使用 show() 代替 exec()，避免阻塞热键
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.show()
            dialog.activateWindow()
    
    def _on_login_success(self, user_info: dict):
        """登录成功回调
        
        Feature: vip-realtime-unlock-modal-fix
        """
        from screenshot_tool.services.subscription import SubscriptionManager
        
        manager = SubscriptionManager.instance()
        if manager:
            manager._sync_after_login(user_info)
    
    def _toggle_text(self):
        """切换原文/译文 - 已废弃，保留兼容"""
        self._restore_original()
    
    def _restore_original(self):
        """恢复OCR原始结果"""
        if self._ocr_text:
            self._replace_text_with_undo(self._ocr_text)
            self._is_showing_translation = False
            self._toggle_btn.setEnabled(False)
            self._status_label.setText("已恢复原文")
    
    def _replace_text_with_undo(self, new_text: str):
        """替换文本内容，保留撤销历史
        
        使用QTextCursor选中全部文本后插入新文本，
        这样操作会被记录到撤销历史中，支持Ctrl+Z撤销。
        """
        if new_text is None:
            new_text = ""
        cursor = self._text_edit.textCursor()
        cursor.beginEditBlock()  # 将多个操作合并为一个撤销步骤
        cursor.select(QTextCursor.SelectionType.Document)  # 选中全部
        cursor.insertText(new_text)  # 插入新文本（替换选中内容）
        cursor.endEditBlock()
        self._text_edit.setTextCursor(cursor)
    
    def _merge_to_single_line(self):
        text = self._text_edit.toPlainText()
        text = " ".join(text.split())
        self._replace_text_with_undo(text)
        self._status_label.setText("已合并为单行")
    
    def _smart_paragraphs(self):
        """智能分段：根据内容特征识别段落边界，段落内合并换行"""
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
                # 1. 上一行以句号、问号、感叹号等结尾，且当前行有缩进或首字母大写
                if prev_line[-1] in '。！？.!?':
                    # 当前行有缩进（原始行以空格开头）
                    if line.startswith(' ') or line.startswith('\t'):
                        is_new_para = True
                    # 当前行首字母大写（英文段落）
                    elif stripped[0].isupper():
                        is_new_para = True
                # 2. 当前行以数字序号开头（如 1. 2. 一、二、）
                if re.match(r'^[\d一二三四五六七八九十]+[.、．]', stripped):
                    is_new_para = True
                # 3. 当前行以项目符号开头（排除普通连字符）
                if stripped[0] in '•·—●○◆◇▪▫' or re.match(r'^-\s', stripped):
                    is_new_para = True
            
            if is_new_para and current_para:
                paragraphs.append(current_para)
                current_para = []
            
            current_para.append(stripped)
        
        # 处理最后一个段落
        if current_para:
            paragraphs.append(current_para)
        
        # 合并每个段落内的行
        result_paras = []
        for para in paragraphs:
            # 检测是否主要是中文
            para_text = ''.join(para)
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', para_text))
            is_chinese = chinese_chars > len(para_text) * 0.3
            
            if is_chinese:
                # 中文段落：直接连接，不加空格
                merged = ''.join(para)
            else:
                # 英文段落：用空格连接
                merged = ' '.join(para)
            result_paras.append(merged)
        
        # 用双换行连接段落
        result = '\n\n'.join(result_paras)
        # 清理多余空格
        result = re.sub(r' +', ' ', result)
        
        self._replace_text_with_undo(result)
        self._status_label.setText("已智能分段")
    
    def _remove_all_spaces(self):
        text = self._text_edit.toPlainText()
        text = text.replace(" ", "").replace("\t", "")
        self._replace_text_with_undo(text)
        self._status_label.setText("已去除所有空格")
    
    def _remove_extra_spaces(self):
        text = self._text_edit.toPlainText()
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\t+', ' ', text)
        self._replace_text_with_undo(text)
        self._status_label.setText("已去除多余空格")
    
    def _chinese_punct_to_english(self):
        """中文标点符号替换为英文标点符号"""
        text = self._text_edit.toPlainText()
        # 中文标点 -> 英文标点 映射
        punct_map = [
            ('，', ','),
            ('。', '.'),
            ('！', '!'),
            ('？', '?'),
            ('；', ';'),
            ('：', ':'),
            ('"', '"'),
            ('"', '"'),
            (''', "'"),
            (''', "'"),
            ('【', '['),
            ('】', ']'),
            ('（', '('),
            ('）', ')'),
            ('《', '<'),
            ('》', '>'),
            ('、', ','),
            ('—', '-'),
            ('～', '~'),
            ('…', '...'),
        ]
        for cn, en in punct_map:
            text = text.replace(cn, en)
        self._replace_text_with_undo(text)
        self._status_label.setText("已转换为英文标点")
    
    def _english_punct_to_chinese(self):
        """英文标点符号替换为中文标点符号"""
        text = self._text_edit.toPlainText()
        # 英文标点 -> 中文标点 映射
        # 注意：句点和冒号在特定上下文不转换
        punct_map = {
            ',': '，',
            '!': '！',
            '?': '？',
            ';': '；',
            '[': '【',
            ']': '】',
            '(': '（',
            ')': '）',
            '~': '～',
        }
        trans_map = str.maketrans(punct_map)
        text = text.translate(trans_map)
        
        # 句点：只转换句末的（后面是空格、换行或结尾，且前面不是数字）
        text = re.sub(r'(?<![0-9])\.(?=\s|$)', '。', text)
        
        # 冒号：只转换中文语境的（前后有中文字符）
        text = re.sub(r'(?<=[\u4e00-\u9fff]):(?=[\u4e00-\u9fff\s])', '：', text)
        
        # 尖括号：只转换书名号语境（前后有中文）
        text = re.sub(r'(?<=[\u4e00-\u9fff])<', '《', text)
        text = re.sub(r'>(?=[\u4e00-\u9fff])', '》', text)
        
        # 处理引号：简单地交替替换
        # 双引号
        parts = text.split('"')
        if len(parts) > 1:
            result = parts[0]
            for i, part in enumerate(parts[1:], 1):
                result += ('"' if i % 2 == 1 else '"') + part
            text = result
        # 单引号：只处理成对的（避免破坏英文缩写如 don't）
        # 使用正则匹配成对单引号
        text = re.sub(r"'([^']+)'", r"'\1'", text)
        
        # 省略号
        text = text.replace('...', '…')
        
        self._replace_text_with_undo(text)
        self._status_label.setText("已转换为中文标点")
    
    def _reset_text(self):
        self._replace_text_with_undo(self._original_text)
        self._status_label.setText("已恢复原文")
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件 - ESC键关闭窗口并通知截图界面，Ctrl+P 切换预览
        
        如果窗口处于最大化状态，ESC 先恢复窗口大小；
        如果窗口处于正常状态，ESC 关闭窗口。
        Ctrl+P 切换 Markdown 预览模式。
        """
        # 检查是否正在关闭或 C++ 对象是否仍然有效
        if self._is_closing:
            event.accept()
            return
        
        try:
            # 尝试访问一个属性来验证对象有效性
            _ = self.isVisible()
        except RuntimeError:
            # C++ 对象已被删除，直接返回
            return
        
        # Ctrl+P 切换预览模式
        if event.key() == Qt.Key.Key_P and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._toggle_preview_mode()
            event.accept()
            return
        
        if event.key() == Qt.Key.Key_Escape:
            # 最大化状态下，ESC 先恢复窗口
            try:
                if self.isMaximized():
                    self.showNormal()
                    self._status_label.setText("已恢复窗口大小")
                    event.accept()
                    return
            except RuntimeError:
                return
            
            # 正常状态下，ESC 关闭窗口
            # 设置关闭标志，防止重复触发
            self._is_closing = True
            try:
                self.escape_pressed.emit()
                self.close()
            except RuntimeError:
                # 对象已被删除，忽略
                pass
            event.accept()
            return
        super().keyPressEvent(event)
    
    def moveEvent(self, event):
        """窗口移动事件 - 确保窗口位置在屏幕内
        
        Requirements: 4.5
        """
        super().moveEvent(event)
        
        # 获取虚拟屏幕边界
        from PySide6.QtGui import QGuiApplication
        screens = QGuiApplication.screens()
        if not screens:
            return
        
        # 计算所有屏幕的合并区域
        total_rect = screens[0].availableGeometry()
        for screen in screens[1:]:
            total_rect = total_rect.united(screen.availableGeometry())
        
        # 获取当前窗口位置和大小
        pos = self.pos()
        size = self.size()
        
        # 检查是否需要调整位置
        new_x = pos.x()
        new_y = pos.y()
        need_adjust = False
        
        # 确保窗口不超出左边界
        if new_x < total_rect.left():
            new_x = total_rect.left()
            need_adjust = True
        
        # 确保窗口不超出右边界
        if new_x + size.width() > total_rect.right():
            new_x = max(total_rect.left(), total_rect.right() - size.width())
            need_adjust = True
        
        # 确保窗口不超出上边界
        if new_y < total_rect.top():
            new_y = total_rect.top()
            need_adjust = True
        
        # 确保窗口不超出下边界
        if new_y + size.height() > total_rect.bottom():
            new_y = max(total_rect.top(), total_rect.bottom() - size.height())
            need_adjust = True
        
        # 如果需要调整，移动窗口
        if need_adjust:
            self.move(new_x, new_y)
    
    def closeEvent(self, event):
        """关闭事件
        
        增强的清理方法，确保释放所有内存资源：
        - 清理工作线程
        - 释放图片引用
        - 清空OCR缓存
        - 安全断开信号
        
        Requirements: 1.3, 4.1, 4.2, 4.4, 4.5, 8.2, 8.4
        """
        # 设置关闭标志，防止重复关闭
        self._is_closing = True
        
        # 清理翻译线程（不使用 terminate() 避免崩溃）
        if self._translation_worker is not None:
            if self._translation_worker.isRunning():
                self._translation_worker.requestInterruption()
                self._translation_worker.quit()
                if not self._translation_worker.wait(1000):
                    # 不再使用 terminate()，放弃等待让线程自然结束
                    self._translation_worker = None
            if self._translation_worker is not None:
                self._translation_worker.deleteLater()
                self._translation_worker = None
        
        # 清理OCR线程（不使用 terminate() 避免崩溃）
        if self._ocr_worker is not None:
            if self._ocr_worker.isRunning():
                self._ocr_worker.requestInterruption()
                self._ocr_worker.quit()
                if not self._ocr_worker.wait(1000):
                    # 不再使用 terminate()，放弃等待让线程自然结束
                    self._ocr_worker = None
            if self._ocr_worker is not None:
                self._ocr_worker.deleteLater()
                self._ocr_worker = None
        
        # 释放图片引用 (Requirements: 1.3, 4.1)
        self._current_image = None
        
        # 清空OCR缓存 (Requirements: 4.2)
        self._ocr_cache.clear()
        
        # 先发出关闭信号，再断开连接（确保信号能被接收）
        self.closed.emit()
        
        # 安全断开信号 (Requirements: 4.5, 8.2, 8.4)
        # 注意：断开信号是为了防止后续意外触发，不影响上面已发出的信号
        try:
            self.closed.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            self.escape_pressed.disconnect()
        except (RuntimeError, TypeError):
            pass
        # engine_switch_requested 可能没有连接，不需要断开
        
        # 调用deleteLater确保Qt对象被正确清理 (Requirements: 4.4)
        self.deleteLater()
        
        super().closeEvent(event)
