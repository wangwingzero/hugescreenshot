# -*- coding: utf-8 -*-
"""
工作台管理器

监听系统剪贴板变化，存储历史记录，支持搜索和持久化。

Feature: clipboard-history
Feature: workbench-temporary-preview-python (SQLite 存储迁移)
Requirements: 8.1, 8.2
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from screenshot_tool.core.screenshot_state_manager import AnnotationData

from PySide6.QtCore import QObject, Signal, QTimer, QThread
from PySide6.QtGui import QClipboard, QImage
from PySide6.QtWidgets import QApplication

# SQLite 存储模块
from screenshot_tool.core.sqlite_history_storage import (
    SQLiteHistoryStorage,
    get_sqlite_history_storage,
    HistoryItem as SQLiteHistoryItem,
    ContentType as SQLiteContentType,
)


class ImageSaveWorker(QThread):
    """后台线程保存图片，避免阻塞 UI
    
    Feature: clipboard-history
    """
    finished = Signal(str, bool)  # (item_id, success)
    
    def __init__(
        self,
        image: QImage,
        image_path: str,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._image = image
        self._image_path = image_path
        self._item_id = ""
    
    def set_item_id(self, item_id: str) -> None:
        """设置条目 ID（用于完成信号）"""
        self._item_id = item_id
    
    def run(self) -> None:
        """在后台线程中保存图片"""
        try:
            success = self._image.save(self._image_path, "PNG")
            self.finished.emit(self._item_id, success)
        except Exception:
            self.finished.emit(self._item_id, False)


def get_clipboard_data_dir() -> str:
    """获取工作台数据目录
    
    Returns:
        数据目录路径 (~/.screenshot_tool/)
    """
    return os.path.expanduser("~/.screenshot_tool")


class ContentType(Enum):
    """剪贴板内容类型"""
    TEXT = "text"
    IMAGE = "image"
    HTML = "html"


@dataclass
class HistoryItem:
    """单条工作台记录
    
    Feature: clipboard-history, screenshot-state-restore, background-ocr-cache
    Requirements: 1.3, 6.1, 6.2, 1.1, 1.2
    """
    id: str                          # UUID
    content_type: ContentType        # 内容类型
    text_content: Optional[str]      # 文本内容（TEXT/HTML 类型）
    image_path: Optional[str]        # 图片文件路径（IMAGE 类型）
    preview_text: str                # 预览文本（前50字符）
    timestamp: datetime              # 复制时间
    is_pinned: bool = False          # 是否置顶
    
    # 新增：截图标注数据（Feature: screenshot-state-restore）
    annotations: Optional[List[dict]] = None  # 标注数据列表（JSON 格式）
    selection_rect: Optional[Tuple[int, int, int, int]] = None  # 选区 (x, y, w, h)
    
    # 自定义名称（用于重命名功能）
    custom_name: Optional[str] = None  # 用户自定义的条目名称
    
    # OCR 缓存（Feature: background-ocr-cache）
    # 后台空闲时自动执行 OCR，结果缓存到本地
    ocr_cache: Optional[str] = None  # OCR 识别结果文本
    ocr_cache_timestamp: Optional[datetime] = None  # OCR 缓存时间
    
    def has_ocr_cache(self) -> bool:
        """是否有 OCR 缓存
        
        Feature: background-ocr-cache
        
        Returns:
            True 如果有 OCR 缓存
        """
        return self.ocr_cache is not None and len(self.ocr_cache) > 0
    
    def has_annotations(self) -> bool:
        """是否有标注数据
        
        Feature: screenshot-state-restore
        Requirements: 4.1, 4.4
        
        Returns:
            True 如果有标注数据
        """
        return self.annotations is not None and len(self.annotations) > 0
    
    def get_annotation_count(self) -> int:
        """获取标注数量
        
        Feature: screenshot-state-restore
        Requirements: 4.4
        
        Returns:
            标注数量
        """
        return len(self.annotations) if self.annotations else 0
    
    def to_dict(self) -> dict:
        """序列化为字典
        
        Returns:
            包含所有字段的字典
        """
        result = {
            "id": self.id,
            "content_type": self.content_type.value,
            "text_content": self.text_content,
            "image_path": self.image_path,
            "preview_text": self.preview_text,
            "timestamp": self.timestamp.isoformat(),
            "is_pinned": self.is_pinned,
        }
        
        # 添加标注数据（如果有）
        if self.annotations is not None:
            result["annotations"] = self.annotations
        if self.selection_rect is not None:
            result["selection_rect"] = list(self.selection_rect)
        
        # 添加自定义名称（如果有）
        if self.custom_name is not None:
            result["custom_name"] = self.custom_name
        
        # 添加 OCR 缓存（Feature: background-ocr-cache）
        if self.ocr_cache is not None:
            result["ocr_cache"] = self.ocr_cache
        if self.ocr_cache_timestamp is not None:
            result["ocr_cache_timestamp"] = self.ocr_cache_timestamp.isoformat()
        
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryItem':
        """从字典反序列化
        
        Args:
            data: 包含历史记录数据的字典
            
        Returns:
            HistoryItem 实例
            
        Raises:
            KeyError: 缺少必需字段
            ValueError: 字段值无效
        """
        # 解析标注数据（向后兼容：旧版本没有这些字段）
        annotations = data.get("annotations")
        selection_rect_data = data.get("selection_rect")
        selection_rect = tuple(selection_rect_data) if selection_rect_data else None
        
        # 解析自定义名称（向后兼容）
        custom_name = data.get("custom_name")
        
        # 解析 OCR 缓存（Feature: background-ocr-cache，向后兼容）
        ocr_cache = data.get("ocr_cache")
        ocr_cache_timestamp_str = data.get("ocr_cache_timestamp")
        ocr_cache_timestamp = (
            datetime.fromisoformat(ocr_cache_timestamp_str) 
            if ocr_cache_timestamp_str else None
        )
        
        return cls(
            id=data["id"],
            content_type=ContentType(data["content_type"]),
            text_content=data.get("text_content"),
            image_path=data.get("image_path"),
            preview_text=data["preview_text"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_pinned=data.get("is_pinned", False),
            annotations=annotations,
            selection_rect=selection_rect,
            custom_name=custom_name,
            ocr_cache=ocr_cache,
            ocr_cache_timestamp=ocr_cache_timestamp,
        )
    
    @staticmethod
    def generate_preview(text: Optional[str], max_length: int = 50) -> str:
        """生成预览文本
        
        Args:
            text: 原始文本
            max_length: 最大长度
            
        Returns:
            截断后的预览文本
        """
        if not text:
            return ""
        # 移除换行符，替换为空格
        text = text.replace("\n", " ").replace("\r", "").strip()
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."



class ClipboardHistoryManager(QObject):
    """工作台管理器
    
    监听系统剪贴板变化，存储历史记录，支持搜索和持久化。
    
    Feature: clipboard-history
    Requirements: 1.4, 3.4, 3.5, 3.6, 3.7
    """
    
    # 信号
    history_changed = Signal()  # 历史记录变化时发射
    
    # 默认配置
    DEFAULT_MAX_ITEMS = 100
    HISTORY_FILE = "clipboard_history.json"
    IMAGES_DIR = "clipboard_images"
    
    def __init__(self, max_items: int = DEFAULT_MAX_ITEMS):
        """初始化管理器
        
        自动检测并迁移 JSON 历史数据到 SQLite。
        
        Args:
            max_items: 最大历史记录数量
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1, 8.2, 8.8
        """
        super().__init__()
        self._max_items = max_items
        self._history: List[HistoryItem] = []
        self._monitoring = False
        self._skip_next_change = False  # 用于避免复制到剪贴板时重复记录
        self._paused = False  # 暂停新增条目（工作台可见时）
        
        # 智能监听状态（区分用户意图）
        # Feature: smart-clipboard-monitoring
        self._in_screenshot_mode = False  # 截图模式下暂停监听
        self._history_window_focused = False  # 工作台窗口获得焦点时暂停监听
        
        # 图片缓存（避免重复从磁盘加载）
        self._image_cache: dict[str, QImage] = {}
        self._image_cache_max_size = 10  # 最多缓存 10 张图片
        
        # 数据目录
        self._data_dir = get_clipboard_data_dir()
        self._history_file = os.path.join(self._data_dir, self.HISTORY_FILE)
        self._images_dir = os.path.join(self._data_dir, self.IMAGES_DIR)
        
        # 确保目录存在
        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(self._images_dir, exist_ok=True)
        
        # SQLite 存储（Feature: workbench-temporary-preview-python）
        # Requirements: 8.1, 8.8 - 初始化应在 50ms 内完成
        self._sqlite_storage: Optional[SQLiteHistoryStorage] = None
        self._use_sqlite = True  # 使用 SQLite 存储
        self._init_sqlite_storage()
        
        # 延迟保存定时器（避免频繁 I/O 阻塞主线程）
        # 注意：使用 SQLite 后，此定时器仅用于兼容性，实际保存由 SQLite 处理
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)  # 500ms 延迟
        self._save_timer.timeout.connect(self._do_save_history)
        
        # 后台图片保存线程列表（避免阻塞 UI）
        self._save_workers: List[ImageSaveWorker] = []
        
        # 与截图模式管理器集成
        self._integrate_with_screenshot_mode_manager()
    
    def _init_sqlite_storage(self) -> None:
        """初始化 SQLite 存储并执行迁移
        
        Feature: workbench-temporary-preview-python
        Requirements: 8.1, 8.2, 8.8
        """
        try:
            # 获取 SQLite 存储实例
            self._sqlite_storage = get_sqlite_history_storage(self._data_dir)
            
            # 检查是否需要从 JSON 迁移
            if self._sqlite_storage.check_migration_needed(self._history_file):
                self._migrate_from_json()
            
            self._use_sqlite = True
            self._log_info("SQLite 存储初始化成功")
        except Exception as e:
            # SQLite 初始化失败，回退到 JSON 存储
            self._log_error(f"SQLite 存储初始化失败，回退到 JSON: {e}")
            self._use_sqlite = False
            self._sqlite_storage = None
    
    def _migrate_from_json(self) -> None:
        """从 JSON 迁移到 SQLite
        
        Feature: workbench-temporary-preview-python
        Requirements: 8.2
        """
        if self._sqlite_storage is None:
            return
        
        try:
            result = self._sqlite_storage.migrate_from_json(self._history_file)
            
            if result.success:
                self._log_info(
                    f"JSON 到 SQLite 迁移完成: "
                    f"{result.migrated_items} 条新增, "
                    f"{result.skipped_items} 条已存在"
                )
            else:
                self._log_error(f"JSON 到 SQLite 迁移部分失败: {result.message}")
                for error in result.errors[:5]:  # 只记录前 5 个错误
                    self._log_error(f"  - {error}")
        except Exception as e:
            self._log_error(f"JSON 到 SQLite 迁移异常: {e}")
    
    def _log_info(self, message: str) -> None:
        """记录信息日志
        
        Args:
            message: 信息消息
        """
        try:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger and hasattr(logger, 'log_info'):
                logger.log_info(message)
        except (ImportError, AttributeError):
            pass
    
    def _log_error(self, message: str) -> None:
        """记录错误日志
        
        Args:
            message: 错误消息
        """
        try:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(message)
        except ImportError:
            pass
    
    def _integrate_with_screenshot_mode_manager(self) -> None:
        """与截图模式管理器集成
        
        Feature: smart-clipboard-monitoring
        
        进入截图模式时暂停剪贴板监听，退出时恢复。
        """
        try:
            from screenshot_tool.core.screenshot_mode_manager import (
                get_screenshot_mode_manager
            )
            
            manager = get_screenshot_mode_manager()
            
            # 注册暂停回调：进入截图模式时暂停监听
            manager.register_pause_callback(self._on_screenshot_mode_entered)
            
            # 注册恢复回调：退出截图模式时恢复监听
            manager.register_resume_callback(self._on_screenshot_mode_exited)
        except ImportError:
            # 截图模式管理器不可用时忽略
            pass
    
    def _on_screenshot_mode_entered(self) -> None:
        """截图模式进入回调
        
        Feature: smart-clipboard-monitoring
        """
        self._in_screenshot_mode = True
    
    def _on_screenshot_mode_exited(self) -> None:
        """截图模式退出回调
        
        Feature: smart-clipboard-monitoring
        """
        self._in_screenshot_mode = False
    
    def set_history_window_focused(self, focused: bool) -> None:
        """设置工作台窗口焦点状态
        
        Feature: smart-clipboard-monitoring
        
        当工作台窗口获得焦点时，暂停剪贴板监听，
        避免用户在工作台内操作时触发不必要的保存。
        
        Args:
            focused: 是否获得焦点
        """
        self._history_window_focused = focused
    
    def _should_capture_clipboard(self) -> bool:
        """判断是否应该捕获剪贴板内容
        
        Feature: smart-clipboard-monitoring
        
        智能判断用户意图，只在以下情况下捕获：
        1. 不在截图模式中
        2. 工作台窗口没有焦点
        3. 没有设置跳过标志
        
        Returns:
            是否应该捕获
        """
        # 截图模式下不捕获
        if self._in_screenshot_mode:
            return False
        
        # 工作台窗口有焦点时不捕获
        if self._history_window_focused:
            return False
        
        # 设置了跳过标志时不捕获
        if self._skip_next_change:
            return False
        
        return True
    
    def set_paused(self, paused: bool) -> None:
        """设置暂停状态
        
        已弃用：根据 UX 最佳实践，可见窗口应保持实时更新。
        性能问题应通过优化解决，而非暂停功能。
        
        Args:
            paused: 忽略此参数
        """
        pass  # 不再暂停，保持实时更新
    
    @property
    def is_paused(self) -> bool:
        """获取暂停状态（始终返回 False）"""
        return False
    
    @property
    def max_items(self) -> int:
        """获取最大历史记录数量"""
        return self._max_items
    
    def get_history(self) -> List[HistoryItem]:
        """获取所有历史记录（按时间降序，钉住项不置顶）
        
        钉住功能仅用于清空时保留，不影响排序。
        
        Returns:
            历史记录列表
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1, 8.3
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_items = self._sqlite_storage.get_all_items(offset=0, limit=self._max_items)
                # 转换为本地 HistoryItem 格式
                return [self._convert_from_sqlite_item(item) for item in sqlite_items]
            except Exception as e:
                self._log_error(f"从 SQLite 获取历史记录失败: {e}")
                # 回退到内存缓存
        
        # 回退：使用内存中的历史记录
        sorted_items = sorted(self._history, key=lambda x: x.timestamp, reverse=True)
        return sorted_items
    
    def _convert_from_sqlite_item(self, sqlite_item: SQLiteHistoryItem) -> HistoryItem:
        """将 SQLite HistoryItem 转换为本地 HistoryItem
        
        Args:
            sqlite_item: SQLite 存储的 HistoryItem
            
        Returns:
            本地 HistoryItem 实例
        """
        return HistoryItem(
            id=sqlite_item.id,
            content_type=ContentType(sqlite_item.content_type.value),
            text_content=sqlite_item.text_content,
            image_path=sqlite_item.image_path,
            preview_text=sqlite_item.preview_text,
            timestamp=sqlite_item.timestamp,
            is_pinned=sqlite_item.is_pinned,
            annotations=sqlite_item.annotations,
            selection_rect=sqlite_item.selection_rect,
            custom_name=sqlite_item.custom_name,
            ocr_cache=sqlite_item.ocr_cache,
            ocr_cache_timestamp=sqlite_item.ocr_cache_timestamp,
        )
    
    def _convert_to_sqlite_item(self, item: HistoryItem) -> SQLiteHistoryItem:
        """将本地 HistoryItem 转换为 SQLite HistoryItem
        
        Args:
            item: 本地 HistoryItem
            
        Returns:
            SQLite 存储的 HistoryItem 实例
        """
        return SQLiteHistoryItem(
            id=item.id,
            content_type=SQLiteContentType(item.content_type.value),
            text_content=item.text_content,
            image_path=item.image_path,
            preview_text=item.preview_text,
            timestamp=item.timestamp,
            is_pinned=item.is_pinned,
            annotations=item.annotations,
            selection_rect=item.selection_rect,
            custom_name=item.custom_name,
            ocr_cache=item.ocr_cache,
            ocr_cache_timestamp=item.ocr_cache_timestamp,
        )
    
    def get_item(self, item_id: str) -> Optional[HistoryItem]:
        """根据 ID 获取单条记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            HistoryItem 或 None
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_item = self._sqlite_storage.get_item(item_id)
                if sqlite_item:
                    return self._convert_from_sqlite_item(sqlite_item)
                return None
            except Exception as e:
                self._log_error(f"从 SQLite 获取记录失败: {e}")
                # 回退到内存缓存
        
        # 回退：从内存中查找
        for item in self._history:
            if item.id == item_id:
                return item
        return None
    
    def add_item(self, item: HistoryItem) -> None:
        """添加历史记录
        
        Args:
            item: 要添加的记录
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1, 8.4
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                # 检查是否已存在相同内容（避免重复）
                existing_items = self._sqlite_storage.get_all_items(offset=0, limit=self._max_items)
                for existing in existing_items:
                    if (existing.content_type.value == item.content_type.value and 
                        existing.text_content == item.text_content and
                        existing.image_path == item.image_path):
                        # 已存在相同内容，删除旧记录
                        self._sqlite_storage.delete_item(existing.id)
                        item.is_pinned = existing.is_pinned  # 保留置顶状态
                        break
                
                # 添加到 SQLite
                sqlite_item = self._convert_to_sqlite_item(item)
                self._sqlite_storage.add_item(sqlite_item)
                
                # 检查数量限制，删除最旧的非置顶项
                self._enforce_limit_sqlite()
                
                # 发射信号
                self.history_changed.emit()
                return
            except Exception as e:
                self._log_error(f"添加到 SQLite 失败: {e}")
                # 回退到内存存储
        
        # 回退：使用内存存储
        # 检查是否已存在相同内容（避免重复）
        for existing in self._history:
            if (existing.content_type == item.content_type and 
                existing.text_content == item.text_content and
                existing.image_path == item.image_path):
                # 已存在相同内容，更新时间戳并移到最前
                self._history.remove(existing)
                item.is_pinned = existing.is_pinned  # 保留置顶状态
                break
        
        # 添加到列表
        self._history.append(item)
        
        # 检查数量限制，删除最旧的非置顶项
        self._enforce_limit()
        
        # 发射信号
        self.history_changed.emit()
    
    def _enforce_limit_sqlite(self) -> None:
        """强制执行数量限制（SQLite 版本）
        
        删除最旧的非置顶项，保留 max_items 条记录。
        
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        if self._sqlite_storage is None:
            return
        
        try:
            count = self._sqlite_storage.count_items()
            if count > self._max_items:
                # 删除超出限制的旧记录
                self._sqlite_storage.delete_oldest_unpinned(self._max_items)
        except Exception as e:
            self._log_error(f"执行 SQLite 数量限制失败: {e}")
    
    def delete_item(self, item_id: str) -> bool:
        """删除单条记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            是否删除成功
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 清除图片缓存
        self._clear_image_cache(item_id)
        
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                # 先获取记录以删除图片文件
                sqlite_item = self._sqlite_storage.get_item(item_id)
                if sqlite_item:
                    # 如果是图片，删除图片文件
                    if sqlite_item.content_type == SQLiteContentType.IMAGE and sqlite_item.image_path:
                        image_file = os.path.join(self._data_dir, sqlite_item.image_path)
                        if os.path.exists(image_file):
                            try:
                                os.remove(image_file)
                            except OSError:
                                pass
                    
                    # 从 SQLite 删除
                    success = self._sqlite_storage.delete_item(item_id)
                    if success:
                        self.history_changed.emit()
                    return success
                return False
            except Exception as e:
                self._log_error(f"从 SQLite 删除记录失败: {e}")
                # 回退到内存存储
        
        # 回退：从内存中删除
        for item in self._history:
            if item.id == item_id:
                # 如果是图片，删除图片文件
                if item.content_type == ContentType.IMAGE and item.image_path:
                    image_file = os.path.join(self._data_dir, item.image_path)
                    if os.path.exists(image_file):
                        try:
                            os.remove(image_file)
                        except OSError:
                            pass
                
                self._history.remove(item)
                self.history_changed.emit()
                return True
        return False
    
    def toggle_pin(self, item_id: str) -> bool:
        """切换置顶状态
        
        Args:
            item_id: 记录 ID
            
        Returns:
            新的置顶状态，如果记录不存在返回 False
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_item = self._sqlite_storage.get_item(item_id)
                if sqlite_item:
                    sqlite_item.is_pinned = not sqlite_item.is_pinned
                    self._sqlite_storage.update_item(sqlite_item)
                    self.history_changed.emit()
                    return sqlite_item.is_pinned
                return False
            except Exception as e:
                self._log_error(f"切换 SQLite 置顶状态失败: {e}")
                # 回退到内存存储
        
        # 回退：从内存中操作
        item = self.get_item(item_id)
        if item:
            item.is_pinned = not item.is_pinned
            self.history_changed.emit()
            return item.is_pinned
        return False
    
    def move_to_top(self, item_id: str) -> bool:
        """将指定记录移到最前面（更新时间戳为当前时间）
        
        Args:
            item_id: 记录 ID
            
        Returns:
            是否成功
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_item = self._sqlite_storage.get_item(item_id)
                if sqlite_item:
                    sqlite_item.timestamp = datetime.now()
                    self._sqlite_storage.update_item(sqlite_item)
                    self.history_changed.emit()
                    return True
                return False
            except Exception as e:
                self._log_error(f"更新 SQLite 时间戳失败: {e}")
                # 回退到内存存储
        
        # 回退：从内存中操作
        item = self.get_item(item_id)
        if item:
            item.timestamp = datetime.now()
            self.history_changed.emit()
            return True
        return False
    
    def rename_item(self, item_id: str, new_name: str) -> bool:
        """重命名条目
        
        Args:
            item_id: 记录 ID
            new_name: 新名称，空字符串表示清除自定义名称
            
        Returns:
            是否成功
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 清除空字符串，使用 None 表示无自定义名称
        custom_name = new_name.strip() if new_name and new_name.strip() else None
        
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_item = self._sqlite_storage.get_item(item_id)
                if sqlite_item:
                    sqlite_item.custom_name = custom_name
                    self._sqlite_storage.update_item(sqlite_item)
                    self.history_changed.emit()
                    return True
                return False
            except Exception as e:
                self._log_error(f"重命名 SQLite 记录失败: {e}")
                # 回退到内存存储
        
        # 回退：从内存中操作
        item = self.get_item(item_id)
        if item:
            item.custom_name = custom_name
            self.history_changed.emit()
            return True
        return False
    
    def get_items_without_ocr_cache(self, limit: int = 100) -> List[HistoryItem]:
        """获取没有 OCR 缓存的图片项目
        
        按最近添加顺序返回（最新的优先）。
        用于后台 OCR 缓存任务。
        
        Args:
            limit: 最大返回数量
            
        Returns:
            没有 OCR 缓存的 HistoryItem 列表
            
        Feature: background-ocr-cache-python
        Requirements: 3.4
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_items = self._sqlite_storage.get_items_without_ocr_cache(limit)
                return [self._convert_from_sqlite_item(item) for item in sqlite_items]
            except Exception as e:
                self._log_error(f"从 SQLite 获取无 OCR 缓存记录失败: {e}")
                # 回退到内存过滤
        
        # 回退：从内存中过滤
        # 只返回图片类型且没有 OCR 缓存的项目
        items_without_cache = [
            item for item in self._history
            if (item.content_type == ContentType.IMAGE and 
                not item.has_ocr_cache())
        ]
        
        # 按时间降序排序（最新优先）
        items_without_cache.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 限制返回数量
        return items_without_cache[:limit]
    
    def update_ocr_cache(self, item_id: str, ocr_text: str) -> bool:
        """更新 OCR 缓存
        
        Args:
            item_id: 记录 ID
            ocr_text: OCR 识别结果文本
            
        Returns:
            是否更新成功
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.6
        """
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                success = self._sqlite_storage.update_ocr_cache(item_id, ocr_text)
                if success:
                    self.history_changed.emit()
                return success
            except Exception as e:
                self._log_error(f"更新 SQLite OCR 缓存失败: {e}")
                # 回退到内存存储
        
        # 回退：从内存中操作
        item = self.get_item(item_id)
        if item:
            item.ocr_cache = ocr_text
            item.ocr_cache_timestamp = datetime.now()
            self.history_changed.emit()
            self._save_history()
            return True
        return False
    
    def move_all_pinned_to_top(self) -> int:
        """将所有钉住的记录移到最前面
        
        Returns:
            移动的记录数量
        """
        pinned_items = [item for item in self._history if item.is_pinned]
        if not pinned_items:
            return 0
        
        now = datetime.now()
        for item in pinned_items:
            item.timestamp = now
        
        self.history_changed.emit()
        return len(pinned_items)
    
    def clear_all(self, keep_pinned: bool = True) -> None:
        """清空历史（可选保留置顶项）
        
        Args:
            keep_pinned: 是否保留置顶项
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # 清除图片缓存
        self._clear_image_cache()
        
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                # 获取要删除的记录以删除图片文件
                items_to_delete = self._sqlite_storage.get_all_items(offset=0, limit=10000)
                for item in items_to_delete:
                    if keep_pinned and item.is_pinned:
                        continue
                    # 删除图片文件
                    if item.content_type == SQLiteContentType.IMAGE and item.image_path:
                        image_file = os.path.join(self._data_dir, item.image_path)
                        if os.path.exists(image_file):
                            try:
                                os.remove(image_file)
                            except OSError:
                                pass
                
                # 从 SQLite 清空
                self._sqlite_storage.clear_all(keep_pinned=keep_pinned)
                self.history_changed.emit()
                return
            except Exception as e:
                self._log_error(f"清空 SQLite 历史失败: {e}")
                # 回退到内存存储
        
        # 回退：清空内存
        if keep_pinned:
            # 删除非置顶项的图片文件
            for item in self._history:
                if not item.is_pinned and item.content_type == ContentType.IMAGE and item.image_path:
                    image_file = os.path.join(self._data_dir, item.image_path)
                    if os.path.exists(image_file):
                        try:
                            os.remove(image_file)
                        except OSError:
                            pass
            
            self._history = [item for item in self._history if item.is_pinned]
        else:
            # 删除所有图片文件
            for item in self._history:
                if item.content_type == ContentType.IMAGE and item.image_path:
                    image_file = os.path.join(self._data_dir, item.image_path)
                    if os.path.exists(image_file):
                        try:
                            os.remove(image_file)
                        except OSError:
                            pass
            
            self._history = []
        
        self.history_changed.emit()
    
    def _enforce_limit(self) -> None:
        """强制执行数量限制，删除最旧的非置顶项"""
        while len(self._history) > self._max_items:
            # 找到最旧的非置顶项
            unpinned = [item for item in self._history if not item.is_pinned]
            if not unpinned:
                # 所有项都是置顶的，无法删除
                break
            
            # 按时间排序，删除最旧的
            unpinned.sort(key=lambda x: x.timestamp)
            oldest = unpinned[0]
            
            # 删除图片文件
            if oldest.content_type == ContentType.IMAGE and oldest.image_path:
                image_file = os.path.join(self._data_dir, oldest.image_path)
                if os.path.exists(image_file):
                    try:
                        os.remove(image_file)
                    except OSError:
                        pass
            
            self._history.remove(oldest)

    
    def start_monitoring(self) -> None:
        """开始监听剪贴板变化
        
        Feature: clipboard-history
        Requirements: 1.1, 1.2, 1.3
        """
        if self._monitoring:
            return
        
        app = QApplication.instance()
        if app is None:
            return
        
        clipboard = app.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._monitoring = True
    
    def stop_monitoring(self) -> None:
        """停止监听剪贴板变化"""
        if not self._monitoring:
            return
        
        # 停止延迟保存定时器，避免对象销毁后触发回调
        if self._save_timer.isActive():
            self._save_timer.stop()
        
        app = QApplication.instance()
        if app is None:
            return
        
        try:
            clipboard = app.clipboard()
            clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except RuntimeError:
            # 信号可能已断开
            pass
        
        self._monitoring = False
    
    def _on_clipboard_changed(self) -> None:
        """剪贴板变化回调
        
        使用延迟处理避免在剪贴板操作关键时刻阻塞主线程。
        当用户按 CTRL+X 剪切时，剪贴板可能短暂被锁定，
        延迟 50ms 后再获取数据可以避免 UI 卡顿。
        
        Feature: clipboard-history, smart-clipboard-monitoring
        Requirements: 1.1, 1.2, 1.3
        """
        # 使用智能判断是否应该捕获
        if not self._should_capture_clipboard():
            return
        
        # 延迟处理，避免在剪贴板操作关键时刻阻塞主线程
        # 这可以解决 CTRL+X 剪切时的卡顿问题
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._do_clipboard_capture)
    
    def _do_clipboard_capture(self) -> None:
        """实际执行剪贴板数据捕获
        
        由 _on_clipboard_changed 延迟调用，避免阻塞主线程。
        
        Feature: smart-clipboard-monitoring
        """
        # 再次检查是否应该捕获（可能在延迟期间状态发生变化）
        if not self._should_capture_clipboard():
            return
        
        app = QApplication.instance()
        if app is None:
            return
        
        clipboard = app.clipboard()
        mime_data = clipboard.mimeData()
        
        if mime_data is None:
            return
        
        try:
            # 优先检查图片
            if mime_data.hasImage():
                image = clipboard.image()
                if not image.isNull():
                    self._capture_image(image)
                    return
            
            # 检查文本
            if mime_data.hasText():
                text = mime_data.text()
                if text and text.strip():
                    self._capture_text(text)
                    return
        except Exception as e:
            # 静默处理错误，记录日志
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"剪贴板捕获失败: {e}")
    
    def _capture_text(self, text: str) -> None:
        """捕获文本内容
        
        Args:
            text: 文本内容
        """
        item = HistoryItem(
            id=str(uuid.uuid4()),
            content_type=ContentType.TEXT,
            text_content=text,
            image_path=None,
            preview_text=HistoryItem.generate_preview(text),
            timestamp=datetime.now(),
            is_pinned=False,
        )
        
        self.add_item(item)
        self._save_history()
    
    def _capture_image(self, image: QImage) -> None:
        """捕获图片内容
        
        Args:
            image: QImage 对象
        """
        # 生成唯一 ID
        item_id = str(uuid.uuid4())
        
        # 保存图片文件
        image_filename = f"{item_id}.png"
        image_rel_path = os.path.join(self.IMAGES_DIR, image_filename)
        image_full_path = os.path.join(self._data_dir, image_rel_path)
        
        try:
            image.save(image_full_path, "PNG")
        except Exception as e:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"保存剪贴板图片失败: {e}")
            return
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path=image_rel_path,
            preview_text="[图片]",
            timestamp=datetime.now(),
            is_pinned=False,
        )
        
        self.add_item(item)
        self._save_history()

    
    def _save_history(self) -> None:
        """请求保存历史到文件（延迟执行，避免阻塞主线程）
        
        使用 SQLite 时，数据已实时保存，此方法仅用于兼容性。
        使用 JSON 时，使用定时器延迟 500ms 执行实际保存。
        
        Feature: clipboard-history, workbench-temporary-preview-python
        Requirements: 1.5, 1.6, 6.1, 6.2, 8.1
        """
        # SQLite 模式下数据已实时保存，无需额外操作
        if self._use_sqlite and self._sqlite_storage is not None:
            return
        
        # JSON 模式：重启定时器（如果已在运行则重置）
        self._save_timer.start()
    
    def _do_save_history(self) -> None:
        """实际执行保存历史到文件
        
        由定时器触发，在主线程空闲时执行。
        使用 version 2 格式保存（支持标注数据）。
        
        注意：SQLite 模式下此方法不会被调用。
        """
        # SQLite 模式下不需要保存到 JSON
        if self._use_sqlite and self._sqlite_storage is not None:
            return
        
        try:
            data = {
                "version": 2,  # 升级到 version 2 支持标注数据
                "max_items": self._max_items,
                "items": [item.to_dict() for item in self._history],
            }
            
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log_error(f"保存工作台失败: {e}")
    
    def _load_history(self) -> None:
        """从文件加载历史
        
        SQLite 模式下，数据已在初始化时加载，此方法仅用于兼容性。
        JSON 模式下，支持 version 1 和 version 2 格式（向后兼容）。
        
        Feature: clipboard-history, screenshot-state-restore, workbench-temporary-preview-python
        Requirements: 1.5, 6.1, 6.2, 6.3, 8.1
        """
        # SQLite 模式下不需要从 JSON 加载
        if self._use_sqlite and self._sqlite_storage is not None:
            return
        
        if not os.path.exists(self._history_file):
            return
        
        try:
            with open(self._history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证版本（支持 version 1 和 2）
            version = data.get("version", 1)
            if version not in (1, 2):
                # 未来版本兼容性处理
                self._log_error(f"工作台文件版本不支持: {version}")
            
            # 加载历史记录
            items_data = data.get("items", [])
            for item_data in items_data:
                try:
                    item = HistoryItem.from_dict(item_data)
                    
                    # 验证图片文件是否存在
                    if item.content_type == ContentType.IMAGE and item.image_path:
                        image_full_path = os.path.join(self._data_dir, item.image_path)
                        if not os.path.exists(image_full_path):
                            # 图片文件不存在，跳过此记录
                            continue
                    
                    self._history.append(item)
                except (KeyError, ValueError) as e:
                    # 单条记录损坏，跳过
                    self._log_error(f"加载工作台记录失败: {e}")
                    continue
        except json.JSONDecodeError as e:
            # JSON 解析失败，备份原文件并重新开始
            self._log_error(f"工作台文件损坏: {e}")
            
            # 备份损坏的文件
            backup_file = self._history_file + ".backup"
            try:
                import shutil
                shutil.copy2(self._history_file, backup_file)
            except Exception:
                pass
            
            self._history = []
        except Exception as e:
            self._log_error(f"加载工作台失败: {e}")
            self._history = []
    
    def load(self) -> None:
        """加载历史记录（公开方法）"""
        self._load_history()
    
    def save(self, immediate: bool = False) -> None:
        """保存历史记录（公开方法）
        
        SQLite 模式下数据已实时保存，此方法仅用于兼容性。
        
        Args:
            immediate: 是否立即保存（用于程序退出等场景）
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.1
        """
        # SQLite 模式下数据已实时保存
        if self._use_sqlite and self._sqlite_storage is not None:
            return
        
        if immediate:
            # 停止定时器，立即执行保存
            self._save_timer.stop()
            self._do_save_history()
        else:
            self._save_history()

    
    def search(self, query: str) -> List[HistoryItem]:
        """搜索历史记录
        
        搜索完整内容而非仅预览文本。
        
        Args:
            query: 搜索关键词
            
        Returns:
            匹配的历史记录列表（按时间降序，钉住项不置顶）
            
        Feature: clipboard-history, workbench-temporary-preview-python
        Requirements: 5.1, 5.2, 8.1
        """
        if not query or not query.strip():
            return self.get_history()
        
        # 使用 SQLite 存储
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_items = self._sqlite_storage.search_items(
                    query.strip(), 
                    offset=0, 
                    limit=self._max_items
                )
                return [self._convert_from_sqlite_item(item) for item in sqlite_items]
            except Exception as e:
                self._log_error(f"SQLite 搜索失败: {e}")
                # 回退到内存搜索
        
        # 回退：内存搜索
        query = query.lower().strip()
        
        results = []
        for item in self._history:
            # 搜索完整内容
            if item.text_content and query in item.text_content.lower():
                results.append(item)
            # 也搜索预览文本（用于图片的描述等）
            elif item.preview_text and query in item.preview_text.lower():
                results.append(item)
        
        # 按时间降序排列，钉住不影响排序
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return results

    
    def copy_to_clipboard(self, item_id: str) -> bool:
        """将指定记录复制到剪贴板
        
        Args:
            item_id: 记录 ID
            
        Returns:
            是否复制成功
            
        Feature: clipboard-history
        Requirements: 3.1, 3.2
        """
        item = self.get_item(item_id)
        if item is None:
            return False
        
        app = QApplication.instance()
        if app is None:
            return False
        
        clipboard = app.clipboard()
        
        # 临时禁用监听，避免重复记录
        self._skip_next_change = True
        
        try:
            if item.content_type == ContentType.TEXT or item.content_type == ContentType.HTML:
                if item.text_content:
                    clipboard.setText(item.text_content)
                    return True
            elif item.content_type == ContentType.IMAGE:
                if item.image_path:
                    # 优先使用缓存
                    image = self._get_cached_image(item_id, item.image_path)
                    if image is not None and not image.isNull():
                        clipboard.setImage(image)
                        return True
            return False
        except Exception as e:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"复制到剪贴板失败: {e}")
            return False
    
    def _get_cached_image(self, item_id: str, image_path: str) -> Optional[QImage]:
        """获取缓存的图片，如果不存在则加载并缓存
        
        Args:
            item_id: 记录 ID（用作缓存键）
            image_path: 图片相对路径
            
        Returns:
            QImage 对象，如果失败返回 None
        """
        # 检查缓存
        if item_id in self._image_cache:
            return self._image_cache[item_id]
        
        # 从磁盘加载
        image_full_path = os.path.join(self._data_dir, image_path)
        if not os.path.exists(image_full_path):
            return None
        
        image = QImage(image_full_path)
        if image.isNull():
            return None
        
        # 添加到缓存（LRU 策略：超出限制时删除最早的）
        if len(self._image_cache) >= self._image_cache_max_size:
            # 删除第一个（最早添加的）
            oldest_key = next(iter(self._image_cache))
            del self._image_cache[oldest_key]
        
        self._image_cache[item_id] = image
        return image
    
    def _clear_image_cache(self, item_id: Optional[str] = None):
        """清除图片缓存
        
        Args:
            item_id: 如果指定，只清除该 ID 的缓存；否则清除全部
        """
        if item_id:
            self._image_cache.pop(item_id, None)
        else:
            self._image_cache.clear()

    # ========== 截图历史扩展方法 (Feature: screenshot-state-restore) ==========
    
    def add_screenshot_item(
        self,
        image: QImage,
        annotations: Optional[List[dict]] = None,
        selection_rect: Optional[Tuple[int, int, int, int]] = None,
        item_id: Optional[str] = None,
        ocr_cache: Optional[str] = None,
    ) -> str:
        """添加截图历史条目（带标注数据）- 异步保存图片
        
        Args:
            image: 原始截图图像
            annotations: 标注数据列表（dict 格式）
            selection_rect: 选区坐标 (x, y, width, height)
            item_id: 可选的 ID（用于更新现有条目）
            ocr_cache: OCR 缓存结果（临时预览模式下的 OCR 结果）
            
        Returns:
            条目 ID
            
        Feature: screenshot-state-restore, workbench-temporary-preview-python
        Requirements: 1.1, 1.2, 2.4, 8.6, 8.7
        """
        # 如果提供了 item_id，检查是否存在
        if item_id:
            existing = self.get_item(item_id)
            if existing:
                # 更新现有条目（异步）
                return self._update_screenshot_item(
                    item_id, image, annotations, selection_rect, ocr_cache
                )
        
        # 创建新条目
        new_id = item_id or str(uuid.uuid4())
        
        # 准备图片保存路径
        image_filename = f"{new_id}.png"
        image_rel_path = os.path.join(self.IMAGES_DIR, image_filename)
        image_full_path = os.path.join(self._data_dir, image_rel_path)
        
        # 生成预览文本
        annotation_count = len(annotations) if annotations else 0
        if annotation_count > 0:
            preview_text = f"[截图] {annotation_count}个标注"
        else:
            preview_text = "[截图]"
        
        # 设置 OCR 缓存时间戳（如果有 OCR 缓存）
        ocr_cache_timestamp = datetime.now() if ocr_cache else None
        
        item = HistoryItem(
            id=new_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path=image_rel_path,
            preview_text=preview_text,
            timestamp=datetime.now(),
            is_pinned=False,
            annotations=annotations,
            selection_rect=selection_rect,
            ocr_cache=ocr_cache,
            ocr_cache_timestamp=ocr_cache_timestamp,
        )
        
        # 先添加到历史（UI 立即响应）
        # SQLite 存储会自动保存 ocr_cache 和 annotations（Requirements: 8.6, 8.7）
        self.add_item(item)
        self._save_history()
        
        # 异步保存图片（不阻塞 UI）
        worker = ImageSaveWorker(image, image_full_path, self)
        worker.set_item_id(new_id)
        worker.finished.connect(self._on_image_save_finished)
        self._save_workers.append(worker)
        worker.start()
        
        return new_id
    
    def _on_image_save_finished(self, item_id: str, success: bool) -> None:
        """图片保存完成回调
        
        Args:
            item_id: 条目 ID
            success: 是否成功
        """
        # 清理已完成的 worker
        self._save_workers = [w for w in self._save_workers if w.isRunning()]
        
        if not success:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"异步保存截图图片失败: {item_id}")
    
    def _update_screenshot_item(
        self,
        item_id: str,
        image: QImage,
        annotations: Optional[List[dict]],
        selection_rect: Optional[Tuple[int, int, int, int]],
        ocr_cache: Optional[str] = None,
    ) -> str:
        """更新现有截图条目
        
        Args:
            item_id: 条目 ID
            image: 新的截图图像
            annotations: 新的标注数据
            selection_rect: 新的选区坐标
            ocr_cache: OCR 缓存结果
            
        Returns:
            条目 ID
            
        Feature: screenshot-state-restore, workbench-temporary-preview-python
        Requirements: 8.6, 8.7
        """
        item = self.get_item(item_id)
        if not item:
            return ""
        
        # 异步更新图片文件（不阻塞 UI）
        if item.image_path:
            image_full_path = os.path.join(self._data_dir, item.image_path)
            worker = ImageSaveWorker(image, image_full_path, self)
            worker.set_item_id(item_id)
            worker.finished.connect(self._on_image_save_finished)
            self._save_workers.append(worker)
            worker.start()
        
        # 更新标注数据（Requirement 8.7）
        item.annotations = annotations
        item.selection_rect = selection_rect
        item.timestamp = datetime.now()
        
        # 更新 OCR 缓存（Requirement 8.6）
        if ocr_cache is not None:
            item.ocr_cache = ocr_cache
            item.ocr_cache_timestamp = datetime.now()
        
        # 更新预览文本
        annotation_count = len(annotations) if annotations else 0
        if annotation_count > 0:
            item.preview_text = f"[截图] {annotation_count}个标注"
        else:
            item.preview_text = "[截图]"
        
        # 使用 SQLite 存储更新（如果可用）
        if self._use_sqlite and self._sqlite_storage is not None:
            try:
                sqlite_item = self._convert_to_sqlite_item(item)
                self._sqlite_storage.update_item(sqlite_item)
            except Exception as e:
                self._log_error(f"更新 SQLite 记录失败: {e}")
        
        self.history_changed.emit()
        self._save_history()
        
        return item_id
    
    def get_screenshot_annotations(self, item_id: str) -> Optional[List[dict]]:
        """获取截图的标注数据
        
        Args:
            item_id: 条目 ID
            
        Returns:
            标注数据列表，如果不存在返回 None
            
        Feature: screenshot-state-restore
        Requirements: 2.2
        """
        item = self.get_item(item_id)
        if item and item.content_type == ContentType.IMAGE:
            return item.annotations
        return None
    
    def get_screenshot_selection_rect(self, item_id: str) -> Optional[Tuple[int, int, int, int]]:
        """获取截图的选区坐标
        
        Args:
            item_id: 条目 ID
            
        Returns:
            选区坐标 (x, y, width, height)，如果不存在返回 None
            
        Feature: screenshot-state-restore
        Requirements: 2.2
        """
        item = self.get_item(item_id)
        if item and item.content_type == ContentType.IMAGE:
            return item.selection_rect
        return None
    
    def update_screenshot_annotations(
        self,
        item_id: str,
        annotations: List[dict],
    ) -> bool:
        """更新截图的标注数据（保留原始图像）
        
        Args:
            item_id: 条目 ID
            annotations: 新的标注数据列表
            
        Returns:
            是否更新成功
            
        Feature: screenshot-state-restore
        Requirements: 2.4
        """
        item = self.get_item(item_id)
        if not item or item.content_type != ContentType.IMAGE:
            return False
        
        # 更新标注数据
        item.annotations = annotations
        item.timestamp = datetime.now()
        
        # 更新预览文本
        annotation_count = len(annotations) if annotations else 0
        if annotation_count > 0:
            item.preview_text = f"[截图] {annotation_count}个标注"
        else:
            item.preview_text = "[截图]"
        
        self.history_changed.emit()
        self._save_history()
        
        return True
    
    def get_screenshot_image(self, item_id: str) -> Optional[QImage]:
        """获取截图的原始图像
        
        Args:
            item_id: 条目 ID
            
        Returns:
            QImage 对象，如果失败返回 None
            
        Feature: screenshot-state-restore
        Requirements: 2.2, 3.3
        """
        item = self.get_item(item_id)
        if not item or item.content_type != ContentType.IMAGE or not item.image_path:
            return None
        
        image_full_path = os.path.join(self._data_dir, item.image_path)
        if not os.path.exists(image_full_path):
            return None
        
        image = QImage(image_full_path)
        if image.isNull():
            return None
        
        return image
    
    def render_screenshot_with_annotations(self, item_id: str) -> Optional[QImage]:
        """渲染带标注的截图
        
        Args:
            item_id: 条目 ID
            
        Returns:
            渲染后的图像，如果失败返回 None
            
        Feature: screenshot-state-restore
        Requirements: 3.3
        """
        item = self.get_item(item_id)
        if not item or item.content_type != ContentType.IMAGE:
            return None
        
        # 获取原始图像
        image = self.get_screenshot_image(item_id)
        if image is None:
            return None
        
        # 如果没有标注，直接返回原始图像
        if not item.has_annotations():
            return image
        
        # 使用 AnnotationRenderer 渲染标注
        try:
            from screenshot_tool.core.annotation_renderer import AnnotationRenderer
            return AnnotationRenderer.render(image, item.annotations)
        except ImportError:
            # AnnotationRenderer 尚未实现，返回原始图像
            return image
        except Exception as e:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"渲染截图标注失败: {e}")
            return image
