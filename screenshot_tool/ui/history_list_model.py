# =====================================================
# =============== 高性能历史列表模型 ===============
# =====================================================

"""
高性能历史列表模型 - 使用 QAbstractListModel 实现

Feature: extreme-performance-optimization
Requirements: 11.1, 11.2, 11.6

设计原则：
1. 数据存储在 Python list 中，不创建 Qt 对象
2. 使用 beginInsertRows/endInsertRows 批量更新
3. 只有可见项才会触发 delegate 绘制
4. 100ms 防抖批量插入，避免频繁 UI 更新
"""

from typing import List, Optional, Any
from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QTimer, QObject
)

from screenshot_tool.core.history_item_data import HistoryItemData


class HistoryListModel(QAbstractListModel):
    """高性能历史列表模型
    
    Feature: extreme-performance-optimization
    Requirements: 11.1, 11.2, 11.3, 11.6
    
    优化策略：
    1. 数据存储在 Python list 中，不创建 Qt 对象
    2. 使用 beginInsertRows/endInsertRows 批量更新
    3. 只有可见项才会触发 delegate 绘制
    4. 100ms 防抖合并多次插入操作
    
    Example:
        >>> model = HistoryListModel()
        >>> item = HistoryItemData(
        ...     id="test-1",
        ...     preview_text="截图 1",
        ...     timestamp="2025-01-15 10:30"
        ... )
        >>> model.add_item(item)
        >>> model.force_flush()  # 立即执行插入
        >>> model.rowCount()
        1
    """
    
    # 自定义角色
    ItemDataRole = Qt.ItemDataRole.UserRole + 1
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化历史列表模型
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        
        # 数据存储
        self._items: List[HistoryItemData] = []
        self._id_to_index: dict = {}  # id -> index 映射，用于快速查找
        
        # 防抖定时器：合并多次更新
        self._pending_inserts: List[HistoryItemData] = []
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(100)  # 100ms 防抖
        self._update_timer.timeout.connect(self._flush_inserts)
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """返回行数
        
        Args:
            parent: 父索引（列表模型忽略此参数）
            
        Returns:
            列表中的条目数量
        """
        if parent.isValid():
            return 0  # 列表模型没有子项
        return len(self._items)
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """返回指定索引和角色的数据
        
        Args:
            index: 模型索引
            role: 数据角色
            
        Returns:
            对应角色的数据，无效时返回 None
        """
        if not index.isValid():
            return None
        
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        
        item = self._items[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return item.preview_text
        elif role == Qt.ItemDataRole.UserRole or role == self.ItemDataRole:
            return item  # 返回完整数据对象给 delegate
        elif role == Qt.ItemDataRole.ToolTipRole:
            return f"{item.preview_text}\n{item.timestamp}"
        
        return None
    
    def add_item(self, item: HistoryItemData) -> None:
        """添加条目（延迟批量处理）
        
        使用 100ms 防抖，合并多次添加操作为单次批量插入。
        
        Args:
            item: 要添加的历史条目数据
            
        Note:
            - 如果条目 ID 已存在，则忽略
            - 调用 force_flush() 可立即执行插入
        """
        # 检查是否已存在（包括待插入的）
        if item.id in self._id_to_index:
            return
        
        # 检查待插入列表中是否已有相同 ID
        for pending in self._pending_inserts:
            if pending.id == item.id:
                return
        
        self._pending_inserts.append(item)
        self._update_timer.start()  # 重置定时器
    
    def _flush_inserts(self) -> None:
        """批量插入待处理的条目
        
        内部方法，由定时器触发或 force_flush() 调用。
        使用 beginInsertRows/endInsertRows 进行高效批量更新。
        """
        if not self._pending_inserts:
            return
        
        count = len(self._pending_inserts)
        
        # 批量插入到顶部（最新的在前）
        self.beginInsertRows(QModelIndex(), 0, count - 1)
        
        # 更新现有条目的索引映射（所有索引后移 count 位）
        for item_id, old_index in list(self._id_to_index.items()):
            self._id_to_index[item_id] = old_index + count
        
        # 插入新条目的索引映射
        for i, item in enumerate(self._pending_inserts):
            self._id_to_index[item.id] = i
        
        # 将新条目插入到列表头部
        self._items = self._pending_inserts + self._items
        self._pending_inserts = []
        
        self.endInsertRows()
    
    def remove_item(self, item_id: str) -> bool:
        """删除条目
        
        Args:
            item_id: 要删除的条目 ID
            
        Returns:
            是否成功删除
        """
        if item_id not in self._id_to_index:
            return False
        
        index = self._id_to_index[item_id]
        
        self.beginRemoveRows(QModelIndex(), index, index)
        
        # 删除条目
        del self._items[index]
        del self._id_to_index[item_id]
        
        # 更新后续条目的索引映射
        for i in range(index, len(self._items)):
            self._id_to_index[self._items[i].id] = i
        
        self.endRemoveRows()
        return True
    
    def get_item(self, item_id: str) -> Optional[HistoryItemData]:
        """根据 ID 获取条目
        
        Args:
            item_id: 条目 ID
            
        Returns:
            条目数据，不存在时返回 None
        """
        if item_id not in self._id_to_index:
            return None
        index = self._id_to_index[item_id]
        return self._items[index]
    
    def get_item_at(self, row: int) -> Optional[HistoryItemData]:
        """根据行号获取条目
        
        Args:
            row: 行号
            
        Returns:
            条目数据，无效行号时返回 None
        """
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]
    
    def contains(self, item_id: str) -> bool:
        """检查是否包含指定 ID 的条目
        
        Args:
            item_id: 条目 ID
            
        Returns:
            是否包含
        """
        return item_id in self._id_to_index
    
    def force_flush(self) -> None:
        """强制立即执行更新
        
        停止防抖定时器并立即执行所有待处理的插入操作。
        """
        self._update_timer.stop()
        self._flush_inserts()
    
    def clear_all(self) -> None:
        """清空所有条目
        
        使用 beginResetModel/endResetModel 进行高效重置。
        """
        self.beginResetModel()
        self._items.clear()
        self._id_to_index.clear()
        self._pending_inserts.clear()
        self._update_timer.stop()
        self.endResetModel()
    
    def get_all_items(self) -> List[HistoryItemData]:
        """获取所有条目的副本
        
        Returns:
            条目列表的浅拷贝
        """
        return self._items.copy()
    
    def get_pending_count(self) -> int:
        """获取待处理的插入数量
        
        Returns:
            待插入的条目数量
        """
        return len(self._pending_inserts)
    
    def update_item(self, item_id: str, **kwargs) -> bool:
        """更新条目属性
        
        Args:
            item_id: 条目 ID
            **kwargs: 要更新的属性（如 is_pinned=True）
            
        Returns:
            是否成功更新
        """
        if item_id not in self._id_to_index:
            return False
        
        index = self._id_to_index[item_id]
        item = self._items[index]
        
        # 更新属性
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        # 通知视图数据已更改
        model_index = self.index(index, 0)
        self.dataChanged.emit(model_index, model_index)
        return True
    
    def move_to_top(self, item_id: str) -> bool:
        """将条目移动到顶部
        
        Args:
            item_id: 条目 ID
            
        Returns:
            是否成功移动
        """
        if item_id not in self._id_to_index:
            return False
        
        old_index = self._id_to_index[item_id]
        if old_index == 0:
            return True  # 已经在顶部
        
        # 使用 beginMoveRows/endMoveRows 进行高效移动
        self.beginMoveRows(QModelIndex(), old_index, old_index, QModelIndex(), 0)
        
        # 移动条目
        item = self._items.pop(old_index)
        self._items.insert(0, item)
        
        # 更新索引映射
        for i in range(old_index + 1):
            self._id_to_index[self._items[i].id] = i
        
        self.endMoveRows()
        return True

