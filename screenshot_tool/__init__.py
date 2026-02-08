# =====================================================
# =============== 虎哥截图 ===============
# =====================================================

"""
虎哥截图 - 集成截图、OCR、翻译、高亮标注和Anki制卡功能

功能特性:
- 屏幕截图（全屏/区域）
- 高亮标注（多种颜色）
- OCR文字识别
- 翻译功能
- Anki制卡
- 文件保存

技术栈:
- Python + PySide6
- HTTP API (OCR, 翻译, Anki)
"""

__version__ = "2.11.0"
__app_name__ = "虎哥截图"
__author__ = "虎大王"

from .core.config_manager import (
    ConfigManager, 
    AppConfig,
    get_app_dir,
    get_user_data_dir,
    get_config_filename,
    get_portable_config_path,
    is_portable_mode,
)
from .core.screenshot_manager import ScreenshotManager
from .core.highlight_editor import HighlightEditor, HighlightRegion
from .core.file_manager import FileManager

from .services.ocr_service import OCRService, OCRResult
from .services.translation_service import TranslationService, TranslationResult
from .services.anki_connector import AnkiConnector, AnkiNote

__all__ = [
    "ConfigManager",
    "AppConfig",
    "get_app_dir",
    "get_user_data_dir",
    "get_config_filename",
    "get_portable_config_path",
    "is_portable_mode",
    "ScreenshotManager",
    "HighlightEditor",
    "HighlightRegion",
    "FileManager",
    "OCRService",
    "OCRResult",
    "TranslationService",
    "TranslationResult",
    "AnkiConnector",
    "AnkiNote",
]
