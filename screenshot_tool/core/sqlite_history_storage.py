# -*- coding: utf-8 -*-
"""
SQLite 历史存储模块

提供基于 SQLite 的历史记录存储，替代原有的 JSON 文件存储。
支持高性能 CRUD 操作、分页查询和 OCR 缓存。

Feature: workbench-temporary-preview-python
Requirements: 8.1, 8.5, 8.6, 8.7, 8.8
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Generator, List, Optional, Tuple


class ContentType(Enum):
    """剪贴板内容类型"""
    TEXT = "text"
    IMAGE = "image"
    HTML = "html"


@dataclass
class MigrationResult:
    """JSON 到 SQLite 迁移结果
    
    Feature: workbench-temporary-preview-python
    Requirements: 8.2
    """
    success: bool = False
    message: str = ""
    total_items: int = 0
    migrated_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    backup_path: Optional[str] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class HistoryItem:
    """单条历史记录
    
    Feature: workbench-temporary-preview-python
    Requirements: 8.1, 8.5, 8.6, 8.7
    """
    id: str
    content_type: ContentType
    text_content: Optional[str]
    image_path: Optional[str]
    preview_text: str
    timestamp: datetime
    is_pinned: bool = False
    custom_name: Optional[str] = None
    ocr_cache: Optional[str] = None
    ocr_cache_timestamp: Optional[datetime] = None
    annotations: Optional[List[dict]] = None
    selection_rect: Optional[Tuple[int, int, int, int]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
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
            "custom_name": self.custom_name,
            "ocr_cache": self.ocr_cache,
            "ocr_cache_timestamp": (
                self.ocr_cache_timestamp.isoformat() 
                if self.ocr_cache_timestamp else None
            ),
            "annotations": self.annotations,
            "selection_rect": list(self.selection_rect) if self.selection_rect else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryItem':
        """从字典反序列化
        
        Args:
            data: 包含历史记录数据的字典
            
        Returns:
            HistoryItem 实例
        """
        selection_rect_data = data.get("selection_rect")
        selection_rect = tuple(selection_rect_data) if selection_rect_data else None
        
        ocr_cache_timestamp_str = data.get("ocr_cache_timestamp")
        ocr_cache_timestamp = (
            datetime.fromisoformat(ocr_cache_timestamp_str) 
            if ocr_cache_timestamp_str else None
        )
        
        created_at_str = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_str) 
            if created_at_str else None
        )
        
        updated_at_str = data.get("updated_at")
        updated_at = (
            datetime.fromisoformat(updated_at_str) 
            if updated_at_str else None
        )
        
        return cls(
            id=data["id"],
            content_type=ContentType(data["content_type"]),
            text_content=data.get("text_content"),
            image_path=data.get("image_path"),
            preview_text=data["preview_text"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_pinned=data.get("is_pinned", False),
            custom_name=data.get("custom_name"),
            ocr_cache=data.get("ocr_cache"),
            ocr_cache_timestamp=ocr_cache_timestamp,
            annotations=data.get("annotations"),
            selection_rect=selection_rect,
            created_at=created_at,
            updated_at=updated_at,
        )


class SQLiteHistoryStorage:
    """SQLite 历史存储
    
    提供基于 SQLite 的历史记录存储，支持高性能 CRUD 操作。
    
    Feature: workbench-temporary-preview-python
    Requirements: 8.1, 8.5, 8.6, 8.7, 8.8
    
    使用最佳实践：
    - WAL 模式提升并发性能
    - 参数化查询防止 SQL 注入
    - 上下文管理器确保资源释放
    - 线程本地连接避免多线程问题
    """
    
    # 数据库文件名
    DB_FILE = "clipboard_history.db"
    
    # 数据库 Schema 版本
    SCHEMA_VERSION = 1
    
    def __init__(self, data_dir: Optional[str] = None):
        """初始化 SQLite 存储
        
        Args:
            data_dir: 数据目录路径，默认为 ~/.screenshot_tool/
            
        Requirements: 8.8 - 初始化应在 50ms 内完成
        """
        if data_dir is None:
            data_dir = os.path.expanduser("~/.screenshot_tool")
        
        self._data_dir = data_dir
        self._db_path = os.path.join(data_dir, self.DB_FILE)
        
        # 确保目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 线程本地存储，每个线程使用独立连接
        self._local = threading.local()
        
        # 初始化数据库
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接
        
        使用线程本地存储确保每个线程有独立的连接，
        避免多线程共享连接导致的问题。
        
        Returns:
            sqlite3.Connection 对象
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=30.0
            )
            # 启用 WAL 模式提升并发性能
            conn.execute('PRAGMA journal_mode=WAL')
            # 设置同步模式为 NORMAL（平衡性能和安全性）
            conn.execute('PRAGMA synchronous=NORMAL')
            # 增加缓存大小（64MB）
            conn.execute('PRAGMA cache_size=-64000')
            # 临时表存放在内存
            conn.execute('PRAGMA temp_store=MEMORY')
            # 启用外键约束
            conn.execute('PRAGMA foreign_keys=ON')
            # 返回字典形式的行
            conn.row_factory = sqlite3.Row
            
            self._local.connection = conn
        
        return self._local.connection
    
    @contextmanager
    def _get_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """获取数据库游标的上下文管理器
        
        确保游标在使用后正确关闭，事务在异常时回滚。
        
        Yields:
            sqlite3.Cursor 对象
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_database(self) -> None:
        """初始化数据库表结构
        
        创建历史记录表和必要的索引。
        
        Requirements: 8.1, 8.5, 8.6, 8.7
        """
        with self._get_cursor() as cursor:
            # 创建历史记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history_items (
                    id TEXT PRIMARY KEY,
                    content_type TEXT NOT NULL,
                    text_content TEXT,
                    image_path TEXT,
                    preview_text TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    is_pinned INTEGER DEFAULT 0,
                    custom_name TEXT,
                    ocr_cache TEXT,
                    ocr_cache_timestamp DATETIME,
                    annotations TEXT,
                    selection_rect TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引以提升查询性能
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON history_items(timestamp DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_content_type 
                ON history_items(content_type)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_is_pinned 
                ON history_items(is_pinned)
            ''')
            
            # 创建 schema 版本表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            ''')
            
            # 检查并设置 schema 版本
            cursor.execute('SELECT version FROM schema_version LIMIT 1')
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    'INSERT INTO schema_version (version) VALUES (?)',
                    (self.SCHEMA_VERSION,)
                )
    
    def add_item(self, item: HistoryItem) -> bool:
        """添加历史记录
        
        Args:
            item: 要添加的历史记录
            
        Returns:
            是否添加成功
            
        Requirements: 8.1, 8.6, 8.7
        """
        now = datetime.now()
        
        # 序列化 JSON 字段
        annotations_json = (
            json.dumps(item.annotations, ensure_ascii=False) 
            if item.annotations else None
        )
        selection_rect_json = (
            json.dumps(list(item.selection_rect)) 
            if item.selection_rect else None
        )
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    INSERT OR REPLACE INTO history_items (
                        id, content_type, text_content, image_path,
                        preview_text, timestamp, is_pinned, custom_name,
                        ocr_cache, ocr_cache_timestamp, annotations,
                        selection_rect, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item.id,
                    item.content_type.value,
                    item.text_content,
                    item.image_path,
                    item.preview_text,
                    item.timestamp.isoformat(),
                    1 if item.is_pinned else 0,
                    item.custom_name,
                    item.ocr_cache,
                    item.ocr_cache_timestamp.isoformat() if item.ocr_cache_timestamp else None,
                    annotations_json,
                    selection_rect_json,
                    item.created_at.isoformat() if item.created_at else now.isoformat(),
                    now.isoformat(),
                ))
            return True
        except sqlite3.Error as e:
            self._log_error(f"添加历史记录失败: {e}")
            return False
    
    def get_item(self, item_id: str) -> Optional[HistoryItem]:
        """根据 ID 获取单条记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            HistoryItem 或 None
            
        Requirements: 8.1
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute(
                    'SELECT * FROM history_items WHERE id = ?',
                    (item_id,)
                )
                row = cursor.fetchone()
                if row:
                    return self._row_to_item(row)
                return None
        except sqlite3.Error as e:
            self._log_error(f"获取历史记录失败: {e}")
            return None
    
    def get_all_items(
        self, 
        offset: int = 0, 
        limit: int = 100
    ) -> List[HistoryItem]:
        """获取所有历史记录（分页，按时间降序）
        
        Args:
            offset: 偏移量
            limit: 每页数量
            
        Returns:
            历史记录列表
            
        Requirements: 8.1, 8.3
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM history_items 
                    ORDER BY timestamp DESC 
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                rows = cursor.fetchall()
                return [self._row_to_item(row) for row in rows]
        except sqlite3.Error as e:
            self._log_error(f"获取历史记录列表失败: {e}")
            return []
    
    def update_item(self, item: HistoryItem) -> bool:
        """更新历史记录
        
        Args:
            item: 要更新的历史记录
            
        Returns:
            是否更新成功
            
        Requirements: 8.1
        """
        now = datetime.now()
        
        # 序列化 JSON 字段
        annotations_json = (
            json.dumps(item.annotations, ensure_ascii=False) 
            if item.annotations else None
        )
        selection_rect_json = (
            json.dumps(list(item.selection_rect)) 
            if item.selection_rect else None
        )
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    UPDATE history_items SET
                        content_type = ?,
                        text_content = ?,
                        image_path = ?,
                        preview_text = ?,
                        timestamp = ?,
                        is_pinned = ?,
                        custom_name = ?,
                        ocr_cache = ?,
                        ocr_cache_timestamp = ?,
                        annotations = ?,
                        selection_rect = ?,
                        updated_at = ?
                    WHERE id = ?
                ''', (
                    item.content_type.value,
                    item.text_content,
                    item.image_path,
                    item.preview_text,
                    item.timestamp.isoformat(),
                    1 if item.is_pinned else 0,
                    item.custom_name,
                    item.ocr_cache,
                    item.ocr_cache_timestamp.isoformat() if item.ocr_cache_timestamp else None,
                    annotations_json,
                    selection_rect_json,
                    now.isoformat(),
                    item.id,
                ))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self._log_error(f"更新历史记录失败: {e}")
            return False
    
    def delete_item(self, item_id: str) -> bool:
        """删除单条记录
        
        Args:
            item_id: 记录 ID
            
        Returns:
            是否删除成功
            
        Requirements: 8.1
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute(
                    'DELETE FROM history_items WHERE id = ?',
                    (item_id,)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self._log_error(f"删除历史记录失败: {e}")
            return False
    
    def update_ocr_cache(
        self, 
        item_id: str, 
        ocr_text: str
    ) -> bool:
        """更新 OCR 缓存
        
        Args:
            item_id: 记录 ID
            ocr_text: OCR 识别结果文本
            
        Returns:
            是否更新成功
            
        Requirements: 8.6
        """
        now = datetime.now()
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    UPDATE history_items SET
                        ocr_cache = ?,
                        ocr_cache_timestamp = ?,
                        updated_at = ?
                    WHERE id = ?
                ''', (
                    ocr_text,
                    now.isoformat(),
                    now.isoformat(),
                    item_id,
                ))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self._log_error(f"更新 OCR 缓存失败: {e}")
            return False
    
    def get_items_by_content_type(
        self, 
        content_type: ContentType,
        offset: int = 0,
        limit: int = 100
    ) -> List[HistoryItem]:
        """按内容类型获取历史记录
        
        Args:
            content_type: 内容类型
            offset: 偏移量
            limit: 每页数量
            
        Returns:
            历史记录列表
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM history_items 
                    WHERE content_type = ?
                    ORDER BY timestamp DESC 
                    LIMIT ? OFFSET ?
                ''', (content_type.value, limit, offset))
                rows = cursor.fetchall()
                return [self._row_to_item(row) for row in rows]
        except sqlite3.Error as e:
            self._log_error(f"按类型获取历史记录失败: {e}")
            return []
    
    def get_pinned_items(self) -> List[HistoryItem]:
        """获取所有置顶的历史记录
        
        Returns:
            置顶的历史记录列表
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM history_items 
                    WHERE is_pinned = 1
                    ORDER BY timestamp DESC
                ''')
                rows = cursor.fetchall()
                return [self._row_to_item(row) for row in rows]
        except sqlite3.Error as e:
            self._log_error(f"获取置顶记录失败: {e}")
            return []
    
    def get_items_without_ocr_cache(
        self, 
        limit: int = 10
    ) -> List[HistoryItem]:
        """获取没有 OCR 缓存的图片记录
        
        用于后台 OCR 任务。
        
        Args:
            limit: 最大数量
            
        Returns:
            没有 OCR 缓存的图片记录列表
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM history_items 
                    WHERE content_type = 'image' 
                    AND (ocr_cache IS NULL OR ocr_cache = '')
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
                rows = cursor.fetchall()
                return [self._row_to_item(row) for row in rows]
        except sqlite3.Error as e:
            self._log_error(f"获取无 OCR 缓存记录失败: {e}")
            return []
    
    def count_items(self) -> int:
        """获取历史记录总数
        
        Returns:
            记录总数
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM history_items')
                row = cursor.fetchone()
                return row[0] if row else 0
        except sqlite3.Error as e:
            self._log_error(f"获取记录总数失败: {e}")
            return 0
    
    def search_items(
        self, 
        query: str,
        offset: int = 0,
        limit: int = 100
    ) -> List[HistoryItem]:
        """搜索历史记录
        
        搜索文本内容、预览文本和 OCR 缓存。
        
        Args:
            query: 搜索关键词
            offset: 偏移量
            limit: 每页数量
            
        Returns:
            匹配的历史记录列表
        """
        if not query or not query.strip():
            return self.get_all_items(offset, limit)
        
        search_pattern = f'%{query}%'
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM history_items 
                    WHERE text_content LIKE ? 
                    OR preview_text LIKE ?
                    OR ocr_cache LIKE ?
                    ORDER BY timestamp DESC 
                    LIMIT ? OFFSET ?
                ''', (search_pattern, search_pattern, search_pattern, limit, offset))
                rows = cursor.fetchall()
                return [self._row_to_item(row) for row in rows]
        except sqlite3.Error as e:
            self._log_error(f"搜索历史记录失败: {e}")
            return []
    
    def delete_oldest_unpinned(self, keep_count: int) -> int:
        """删除最旧的非置顶记录，保留指定数量
        
        Args:
            keep_count: 保留的记录数量
            
        Returns:
            删除的记录数量
        """
        try:
            with self._get_cursor() as cursor:
                # 获取要删除的记录 ID
                cursor.execute('''
                    SELECT id FROM history_items 
                    WHERE is_pinned = 0
                    ORDER BY timestamp DESC 
                    LIMIT -1 OFFSET ?
                ''', (keep_count,))
                rows = cursor.fetchall()
                
                if not rows:
                    return 0
                
                ids_to_delete = [row['id'] for row in rows]
                
                # 批量删除
                placeholders = ','.join('?' * len(ids_to_delete))
                cursor.execute(
                    f'DELETE FROM history_items WHERE id IN ({placeholders})',
                    ids_to_delete
                )
                return cursor.rowcount
        except sqlite3.Error as e:
            self._log_error(f"删除旧记录失败: {e}")
            return 0
    
    def clear_all(self, keep_pinned: bool = True) -> int:
        """清空所有历史记录
        
        Args:
            keep_pinned: 是否保留置顶项
            
        Returns:
            删除的记录数量
        """
        try:
            with self._get_cursor() as cursor:
                if keep_pinned:
                    cursor.execute(
                        'DELETE FROM history_items WHERE is_pinned = 0'
                    )
                else:
                    cursor.execute('DELETE FROM history_items')
                return cursor.rowcount
        except sqlite3.Error as e:
            self._log_error(f"清空历史记录失败: {e}")
            return 0
    
    def _row_to_item(self, row: sqlite3.Row) -> HistoryItem:
        """将数据库行转换为 HistoryItem
        
        Args:
            row: 数据库行
            
        Returns:
            HistoryItem 实例
        """
        # 解析 JSON 字段
        annotations = None
        if row['annotations']:
            try:
                annotations = json.loads(row['annotations'])
            except json.JSONDecodeError:
                pass
        
        selection_rect = None
        if row['selection_rect']:
            try:
                rect_list = json.loads(row['selection_rect'])
                selection_rect = tuple(rect_list) if rect_list else None
            except json.JSONDecodeError:
                pass
        
        # 解析时间戳
        timestamp = datetime.fromisoformat(row['timestamp'])
        
        ocr_cache_timestamp = None
        if row['ocr_cache_timestamp']:
            try:
                ocr_cache_timestamp = datetime.fromisoformat(row['ocr_cache_timestamp'])
            except ValueError:
                pass
        
        created_at = None
        if row['created_at']:
            try:
                created_at = datetime.fromisoformat(row['created_at'])
            except ValueError:
                pass
        
        updated_at = None
        if row['updated_at']:
            try:
                updated_at = datetime.fromisoformat(row['updated_at'])
            except ValueError:
                pass
        
        return HistoryItem(
            id=row['id'],
            content_type=ContentType(row['content_type']),
            text_content=row['text_content'],
            image_path=row['image_path'],
            preview_text=row['preview_text'],
            timestamp=timestamp,
            is_pinned=bool(row['is_pinned']),
            custom_name=row['custom_name'],
            ocr_cache=row['ocr_cache'],
            ocr_cache_timestamp=ocr_cache_timestamp,
            annotations=annotations,
            selection_rect=selection_rect,
            created_at=created_at,
            updated_at=updated_at,
        )
    
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
            # 错误日志模块不可用时忽略
            pass
    
    def _log_info(self, message: str) -> None:
        """记录信息日志
        
        Args:
            message: 信息消息
        """
        try:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_info(message)
        except (ImportError, AttributeError):
            # 日志模块不可用或没有 log_info 方法时忽略
            pass
    
    def migrate_from_json(
        self, 
        json_file_path: str,
        backup_suffix: str = ".bak"
    ) -> 'MigrationResult':
        """从 JSON 文件迁移历史记录到 SQLite
        
        实现幂等迁移：
        - 检测现有 JSON 历史文件
        - 逐条迁移到 SQLite（跳过已存在的记录）
        - 备份原 JSON 文件
        - 错误处理不丢失数据
        
        Args:
            json_file_path: JSON 历史文件路径
            backup_suffix: 备份文件后缀，默认 ".bak"
            
        Returns:
            MigrationResult 包含迁移统计信息
            
        Feature: workbench-temporary-preview-python
        Requirements: 8.2
        """
        result = MigrationResult()
        
        # 1. 检测 JSON 文件是否存在
        if not os.path.exists(json_file_path):
            result.success = True
            result.message = "JSON 文件不存在，无需迁移"
            return result
        
        # 2. 读取 JSON 文件
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result.success = False
            result.message = f"JSON 文件格式错误: {e}"
            self._log_error(f"迁移失败 - JSON 解析错误: {e}")
            return result
        except IOError as e:
            result.success = False
            result.message = f"无法读取 JSON 文件: {e}"
            self._log_error(f"迁移失败 - 读取文件错误: {e}")
            return result
        
        # 3. 验证 JSON 格式
        version = data.get("version", 1)
        if version not in (1, 2):
            result.success = False
            result.message = f"不支持的 JSON 版本: {version}"
            self._log_error(f"迁移失败 - 不支持的版本: {version}")
            return result
        
        items_data = data.get("items", [])
        result.total_items = len(items_data)
        
        if result.total_items == 0:
            result.success = True
            result.message = "JSON 文件为空，无需迁移"
            # 仍然备份空文件
            self._backup_json_file(json_file_path, backup_suffix)
            return result
        
        # 4. 逐条迁移到 SQLite
        self._log_info(f"开始迁移 {result.total_items} 条记录从 JSON 到 SQLite")
        
        for item_data in items_data:
            try:
                # 解析 JSON 记录
                item = self._parse_json_item(item_data)
                if item is None:
                    result.failed_items += 1
                    result.errors.append(f"无法解析记录: {item_data.get('id', 'unknown')}")
                    continue
                
                # 检查是否已存在（幂等性）
                existing = self.get_item(item.id)
                if existing is not None:
                    result.skipped_items += 1
                    continue
                
                # 插入到 SQLite
                if self.add_item(item):
                    result.migrated_items += 1
                else:
                    result.failed_items += 1
                    result.errors.append(f"插入失败: {item.id}")
                    
            except Exception as e:
                result.failed_items += 1
                item_id = item_data.get('id', 'unknown')
                result.errors.append(f"迁移记录 {item_id} 失败: {e}")
                self._log_error(f"迁移记录失败 [{item_id}]: {e}")
        
        # 5. 备份原 JSON 文件（仅在有成功迁移时）
        if result.migrated_items > 0 or result.skipped_items > 0:
            backup_path = self._backup_json_file(json_file_path, backup_suffix)
            if backup_path:
                result.backup_path = backup_path
        
        # 6. 设置结果
        result.success = result.failed_items == 0
        if result.success:
            result.message = (
                f"迁移完成: {result.migrated_items} 条新增, "
                f"{result.skipped_items} 条已存在"
            )
            self._log_info(result.message)
        else:
            result.message = (
                f"迁移部分完成: {result.migrated_items} 条成功, "
                f"{result.failed_items} 条失败, "
                f"{result.skipped_items} 条已存在"
            )
            self._log_error(result.message)
        
        return result
    
    def _parse_json_item(self, item_data: dict) -> Optional[HistoryItem]:
        """解析 JSON 格式的历史记录
        
        兼容 version 1 和 version 2 格式。
        
        Args:
            item_data: JSON 记录数据
            
        Returns:
            HistoryItem 或 None（解析失败时）
        """
        try:
            # 必需字段
            item_id = item_data.get("id")
            content_type_str = item_data.get("content_type")
            preview_text = item_data.get("preview_text", "")
            timestamp_str = item_data.get("timestamp")
            
            if not item_id or not content_type_str or not timestamp_str:
                return None
            
            # 解析内容类型
            try:
                content_type = ContentType(content_type_str)
            except ValueError:
                return None
            
            # 解析时间戳
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                return None
            
            # 可选字段
            text_content = item_data.get("text_content")
            image_path = item_data.get("image_path")
            is_pinned = item_data.get("is_pinned", False)
            custom_name = item_data.get("custom_name")
            ocr_cache = item_data.get("ocr_cache")
            
            # OCR 缓存时间戳
            ocr_cache_timestamp = None
            ocr_cache_timestamp_str = item_data.get("ocr_cache_timestamp")
            if ocr_cache_timestamp_str:
                try:
                    ocr_cache_timestamp = datetime.fromisoformat(ocr_cache_timestamp_str)
                except ValueError:
                    pass
            
            # 标注数据（version 2）
            annotations = item_data.get("annotations")
            
            # 选区数据（version 2）
            selection_rect = None
            selection_rect_data = item_data.get("selection_rect")
            if selection_rect_data and isinstance(selection_rect_data, (list, tuple)):
                if len(selection_rect_data) == 4:
                    selection_rect = tuple(selection_rect_data)
            
            # 创建时间（如果没有，使用 timestamp）
            created_at = timestamp
            updated_at = timestamp
            
            return HistoryItem(
                id=item_id,
                content_type=content_type,
                text_content=text_content,
                image_path=image_path,
                preview_text=preview_text,
                timestamp=timestamp,
                is_pinned=is_pinned,
                custom_name=custom_name,
                ocr_cache=ocr_cache,
                ocr_cache_timestamp=ocr_cache_timestamp,
                annotations=annotations,
                selection_rect=selection_rect,
                created_at=created_at,
                updated_at=updated_at,
            )
            
        except Exception:
            return None
    
    def _backup_json_file(
        self, 
        json_file_path: str, 
        backup_suffix: str
    ) -> Optional[str]:
        """备份 JSON 文件
        
        将原 JSON 文件重命名为 .bak 后缀。
        如果备份文件已存在，添加数字后缀。
        
        Args:
            json_file_path: 原 JSON 文件路径
            backup_suffix: 备份后缀
            
        Returns:
            备份文件路径，失败返回 None
        """
        try:
            # 生成备份文件路径
            backup_path = json_file_path + backup_suffix
            
            # 如果备份文件已存在，添加数字后缀
            counter = 1
            while os.path.exists(backup_path):
                backup_path = f"{json_file_path}{backup_suffix}.{counter}"
                counter += 1
                if counter > 100:  # 防止无限循环
                    self._log_error("备份文件数量过多，跳过备份")
                    return None
            
            # 重命名原文件为备份
            os.rename(json_file_path, backup_path)
            self._log_info(f"JSON 文件已备份到: {backup_path}")
            return backup_path
            
        except OSError as e:
            self._log_error(f"备份 JSON 文件失败: {e}")
            return None
    
    def check_migration_needed(self, json_file_path: str) -> bool:
        """检查是否需要迁移
        
        Args:
            json_file_path: JSON 历史文件路径
            
        Returns:
            True 如果 JSON 文件存在且需要迁移
        """
        return os.path.exists(json_file_path)
    
    def close(self) -> None:
        """关闭数据库连接
        
        应在程序退出时调用。
        """
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except sqlite3.Error:
                pass
            self._local.connection = None
    
    def __del__(self) -> None:
        """析构函数，确保连接关闭"""
        self.close()


# 全局单例实例
_storage_instance: Optional[SQLiteHistoryStorage] = None
_storage_lock = threading.Lock()


def get_sqlite_history_storage(
    data_dir: Optional[str] = None
) -> SQLiteHistoryStorage:
    """获取 SQLite 历史存储单例
    
    Args:
        data_dir: 数据目录路径，仅在首次调用时有效
        
    Returns:
        SQLiteHistoryStorage 实例
    """
    global _storage_instance
    
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                _storage_instance = SQLiteHistoryStorage(data_dir)
    
    return _storage_instance


def reset_sqlite_history_storage() -> None:
    """重置 SQLite 历史存储单例
    
    主要用于测试。
    """
    global _storage_instance
    
    with _storage_lock:
        if _storage_instance is not None:
            _storage_instance.close()
            _storage_instance = None
