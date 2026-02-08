# =====================================================
# =============== 服务模块 ===============
# =====================================================

"""
服务模块 - 包含OCR服务、翻译服务、Anki连接器等外部服务接口
"""

from .ocr_service import OCRService, OCRResult
from .translation_service import TranslationService, TranslationResult
from .anki_connector import AnkiConnector, AnkiNote

__all__ = [
    "OCRService",
    "OCRResult",
    "TranslationService",
    "TranslationResult",
    "AnkiConnector",
    "AnkiNote",
]
