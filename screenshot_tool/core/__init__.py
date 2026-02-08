# =====================================================
# =============== 核心模块 ===============
# =====================================================

"""
核心模块 - 包含配置管理、截图管理、高亮编辑、文件管理等核心功能
"""

from .config_manager import ConfigManager, AppConfig
from .screenshot_manager import ScreenshotManager, ScreenCapture
from .highlight_editor import HighlightEditor, HighlightRegion
from .file_manager import FileManager
from .paint_engine import OptimizedPaintEngine, DirtyRegion, PaintEngineIntegration
from .idle_detector import IdleDetector, CacheReleaseManager

__all__ = [
    "ConfigManager",
    "AppConfig",
    "ScreenshotManager",
    "ScreenCapture",
    "HighlightEditor",
    "HighlightRegion",
    "FileManager",
    "OptimizedPaintEngine",
    "DirtyRegion",
    "PaintEngineIntegration",
    "IdleDetector",
    "CacheReleaseManager",
]
