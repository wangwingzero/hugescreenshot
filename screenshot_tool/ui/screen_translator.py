# =====================================================
# =============== 屏幕翻译覆盖层 ===============
# =====================================================

"""
屏幕翻译覆盖层 - OCR识别后翻译并覆盖显示

Requirements: 3.1-3.11
Features:
- OCR + 翻译流程
- 翻译覆盖层窗口
- 定时翻译模式
- 点击复制功能
- 保持文本布局结构
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QApplication, QFrame
)
from PySide6.QtCore import Qt, Signal, QRect, QTimer, QPoint
from PySide6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QBrush
from typing import Optional, Callable
from dataclasses import dataclass
import mss
import mss.tools
import requests


@dataclass
class TranslationOverlayConfig:
    """翻译覆盖层配置"""
    font_size: int = 14
    font_family: str = "Microsoft YaHei"
    text_color: str = "#FFFFFF"
    background_color: str = "#333333"
    background_opacity: float = 0.9
    show_source_lang: bool = True
    timed_interval_ms: int = 2000


class ScreenTranslator(QWidget):
    """屏幕翻译覆盖层"""
    
    # 信号
    translationComplete = Signal(str, str)  # (原文, 译文)
    translationError = Signal(str)
    closed = Signal()
    
    def __init__(self, region: QRect, ocr_callback: Callable[[QImage], str],
                 translate_callback: Callable[[str, str, str], tuple],
                 config: Optional[TranslationOverlayConfig] = None,
                 pre_captured_image: Optional[QImage] = None):
        """
        初始化屏幕翻译
        
        Args:
            region: 翻译区域（用于窗口定位）
            ocr_callback: OCR 回调函数，接收 QImage 返回识别文本
            translate_callback: 翻译回调函数，接收 (text, target_lang, source_lang) 返回 (translated_text, detected_lang, success)
            config: 配置
            pre_captured_image: 预截取的图片（如果提供，则不再重新截图）
        """
        super().__init__()
        
        self._region = region
        self._ocr_callback = ocr_callback
        self._translate_callback = translate_callback
        self._config = config or TranslationOverlayConfig()
        self._pre_captured_image = pre_captured_image.copy() if pre_captured_image and not pre_captured_image.isNull() else None
        
        self._target_lang = "zh"
        self._source_lang = "auto"
        self._detected_lang = ""
        self._original_text = ""
        self._translated_text = ""
        
        self._timed_mode = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        
        self._setup_window()
        self._setup_ui()
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 设置位置和大小
        self.setGeometry(self._region)
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 主容器
        self._container = QFrame(self)
        self._container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(51, 51, 51, {int(self._config.background_opacity * 255)});
                border-radius: 4px;
            }}
        """)
        
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(4)
        
        # 头部（显示检测到的语言）
        self._header = QLabel(self)
        self._header.setStyleSheet(f"""
            QLabel {{
                color: #888888;
                font-size: 10px;
            }}
        """)
        self._header.setVisible(self._config.show_source_lang)
        container_layout.addWidget(self._header)
        
        # 翻译文本
        self._text_label = QLabel(self)
        self._text_label.setWordWrap(True)
        self._text_label.setStyleSheet(f"""
            QLabel {{
                color: {self._config.text_color};
                font-size: {self._config.font_size}px;
                font-family: "{self._config.font_family}";
            }}
        """)
        self._text_label.setCursor(Qt.CursorShape.PointingHandCursor)
        container_layout.addWidget(self._text_label)
        
        # 底部按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        
        # 刷新按钮
        self._refresh_btn = QPushButton("🔄", self)
        self._refresh_btn.setFixedSize(24, 24)
        self._refresh_btn.setStyleSheet(self._get_button_style())
        self._refresh_btn.clicked.connect(self.translate_once)
        self._refresh_btn.setToolTip("刷新翻译")
        button_layout.addWidget(self._refresh_btn)
        
        # 定时翻译按钮
        self._timer_btn = QPushButton("⏱", self)
        self._timer_btn.setFixedSize(24, 24)
        self._timer_btn.setStyleSheet(self._get_button_style())
        self._timer_btn.clicked.connect(self._toggle_timed_mode)
        self._timer_btn.setToolTip("定时翻译")
        button_layout.addWidget(self._timer_btn)
        
        button_layout.addStretch()
        
        # 关闭按钮
        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet(self._get_button_style())
        self._close_btn.clicked.connect(self.close)
        button_layout.addWidget(self._close_btn)
        
        container_layout.addLayout(button_layout)
        
        layout.addWidget(self._container)
    
    def _get_button_style(self) -> str:
        """获取按钮样式"""
        return """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """

    def translate_once(self):
        """执行一次翻译"""
        try:
            # 检查回调函数是否有效
            if self._ocr_callback is None or self._translate_callback is None:
                self._show_error("回调函数未设置")
                return
            
            # 优先使用预截取的图片（仅首次），否则重新截取
            if self._pre_captured_image and not self._pre_captured_image.isNull():
                image = self._pre_captured_image
                # 使用后清除预截取图片，后续调用（如定时模式）将重新截图
                self._pre_captured_image = None
            else:
                image = self._capture_region()
            
            if image.isNull():
                self._show_error("截图失败")
                return
            
            # OCR 识别
            text = self._ocr_callback(image)
            if not text or not text.strip():
                self._show_error("未识别到文本")
                return
            
            self._original_text = text
            
            # 翻译
            translated, detected_lang, success = self._translate_callback(
                text, self._target_lang, self._source_lang
            )
            
            if success:
                self._translated_text = translated
                self._detected_lang = detected_lang
                self._update_display()
                self.translationComplete.emit(text, translated)
            else:
                self._show_error(f"翻译失败: {translated}")
                self.translationError.emit(translated)
        except (requests.RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
            self._show_error(f"错误: {str(e)}")
            self.translationError.emit(str(e))
    
    def _capture_region(self) -> QImage:
        """截取指定区域"""
        try:
            # 验证区域有效性
            if self._region.width() <= 0 or self._region.height() <= 0:
                return QImage()
            
            with mss.mss() as sct:
                monitor = {
                    "left": self._region.x(),
                    "top": self._region.y(),
                    "width": self._region.width(),
                    "height": self._region.height(),
                }
                screenshot = sct.grab(monitor)
                
                # 转换为 QImage
                img = QImage(
                    screenshot.raw,
                    screenshot.width,
                    screenshot.height,
                    QImage.Format.Format_BGRA8888
                )
                return img.copy()
        except (OSError, ValueError, AttributeError) as e:
            return QImage()
    
    def _update_display(self):
        """更新显示"""
        # 更新头部
        if self._config.show_source_lang and self._detected_lang:
            lang_names = {
                "en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语",
                "fr": "法语", "de": "德语", "ru": "俄语", "es": "西班牙语"
            }
            lang_name = lang_names.get(self._detected_lang, self._detected_lang)
            self._header.setText(f"检测到: {lang_name}")
            self._header.setVisible(True)
        
        # 更新翻译文本
        self._text_label.setText(self._translated_text)
        
        # 调整窗口大小
        self.adjustSize()
    
    def _show_error(self, message: str):
        """显示错误"""
        self._header.setText("错误")
        self._header.setVisible(True)
        self._text_label.setText(message)
        self._text_label.setStyleSheet(f"""
            QLabel {{
                color: #FF6B6B;
                font-size: {self._config.font_size}px;
                font-family: "{self._config.font_family}";
            }}
        """)
    
    def start_timed_translation(self, interval_ms: int = 2000):
        """开始定时翻译
        
        Args:
            interval_ms: 定时间隔（毫秒），最小100ms，最大60000ms
        """
        # 验证并限制间隔范围
        interval_ms = max(100, min(60000, interval_ms))
        self._timed_mode = True
        self._timer.start(interval_ms)
        self._timer_btn.setText("⏸")
        self._timer_btn.setToolTip("停止定时翻译")
    
    def stop_timed_translation(self):
        """停止定时翻译"""
        self._timed_mode = False
        self._timer.stop()
        self._timer_btn.setText("⏱")
        self._timer_btn.setToolTip("定时翻译")
    
    def _toggle_timed_mode(self):
        """切换定时翻译模式"""
        if self._timed_mode:
            self.stop_timed_translation()
        else:
            self.start_timed_translation(self._config.timed_interval_ms)
    
    def _on_timer_tick(self):
        """定时器触发"""
        self.translate_once()
    
    def set_target_language(self, lang: str):
        """设置目标语言"""
        self._target_lang = lang
    
    def set_source_language(self, lang: str):
        """设置源语言"""
        self._source_lang = lang
    
    def get_original_text(self) -> str:
        """获取原文"""
        return self._original_text
    
    def get_translated_text(self) -> str:
        """获取译文"""
        return self._translated_text
    
    def mousePressEvent(self, event):
        """鼠标点击事件 - 复制译文"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._translated_text:
                clipboard = QApplication.clipboard()
                clipboard.setText(self._translated_text)
                # 简单的视觉反馈
                self._text_label.setStyleSheet(f"""
                    QLabel {{
                        color: #4CAF50;
                        font-size: {self._config.font_size}px;
                        font-family: "{self._config.font_family}";
                    }}
                """)
                QTimer.singleShot(200, self._restore_text_style)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def _restore_text_style(self):
        """恢复文本样式"""
        self._text_label.setStyleSheet(f"""
            QLabel {{
                color: {self._config.text_color};
                font-size: {self._config.font_size}px;
                font-family: "{self._config.font_family}";
            }}
        """)
    
    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件"""
        self.stop_timed_translation()
        self.closed.emit()
        super().closeEvent(event)


def preserve_line_breaks(text: str) -> str:
    """保持换行结构"""
    # 标准化换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text


def count_line_breaks(text: str) -> int:
    """计算换行数量"""
    return text.count('\n')
