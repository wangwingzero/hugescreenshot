# =====================================================
# =============== 空间索引 ===============
# =====================================================

"""
空间索引 - 用于快速查找附近图形

特性：
- 网格化空间索引
- O(1) 时间复杂度查询
- 支持插入、删除、查询操作
"""

from typing import List, Dict, Tuple, Set, Any, Optional
from PySide6.QtCore import QPoint, QRect


class SpatialIndex:
    """
    简单的空间索引，用于快速查找附近图形
    
    使用网格划分空间，每个网格单元存储覆盖该单元的图形列表
    """
    
    def __init__(self, cell_size: int = 50):
        """
        初始化空间索引
        
        Args:
            cell_size: 网格单元大小（像素）
        """
        self._cell_size = cell_size
        self._grid: Dict[Tuple[int, int], Set[Any]] = {}
        self._item_cells: Dict[int, Set[Tuple[int, int]]] = {}  # item id -> cells
        
        # 统计信息（用于测试）
        self._query_count: int = 0
        self._insert_count: int = 0
    
    def insert(self, item: Any, rect: QRect):
        """
        插入图形到索引
        
        Args:
            item: 图形对象
            rect: 图形的边界矩形
        """
        if rect.isEmpty():
            return
        
        item_id = id(item)
        cells = self._get_cells(rect)
        
        # 记录 item 所在的 cells
        self._item_cells[item_id] = set(cells)
        
        # 将 item 添加到每个 cell
        for cell in cells:
            if cell not in self._grid:
                self._grid[cell] = set()
            self._grid[cell].add(item)
        
        self._insert_count += 1
    
    def remove(self, item: Any):
        """
        从索引中移除图形
        
        Args:
            item: 要移除的图形对象
        """
        item_id = id(item)
        
        if item_id not in self._item_cells:
            return
        
        # 从所有相关 cells 中移除
        for cell in self._item_cells[item_id]:
            if cell in self._grid:
                self._grid[cell].discard(item)
                # 清理空的 cell
                if not self._grid[cell]:
                    del self._grid[cell]
        
        del self._item_cells[item_id]
    
    def update(self, item: Any, new_rect: QRect):
        """
        更新图形的位置
        
        Args:
            item: 图形对象
            new_rect: 新的边界矩形
        """
        self.remove(item)
        self.insert(item, new_rect)
    
    def query(self, pos: QPoint, radius: int = 0) -> List[Any]:
        """
        查询位置附近的图形
        
        Args:
            pos: 查询位置
            radius: 查询半径（像素）
            
        Returns:
            List[Any]: 附近的图形列表
        """
        self._query_count += 1
        
        if radius <= 0:
            # 只查询点所在的 cell
            cell = (pos.x() // self._cell_size, pos.y() // self._cell_size)
            if cell in self._grid:
                return list(self._grid[cell])
            return []
        
        # 查询范围内的所有 cells
        query_rect = QRect(
            pos.x() - radius, 
            pos.y() - radius, 
            radius * 2, 
            radius * 2
        )
        
        result: Set[Any] = set()
        for cell in self._get_cells(query_rect):
            if cell in self._grid:
                result.update(self._grid[cell])
        
        return list(result)
    
    def query_rect(self, rect: QRect) -> List[Any]:
        """
        查询与矩形相交的图形
        
        Args:
            rect: 查询矩形
            
        Returns:
            List[Any]: 相交的图形列表
        """
        self._query_count += 1
        
        if rect.isEmpty():
            return []
        
        result: Set[Any] = set()
        for cell in self._get_cells(rect):
            if cell in self._grid:
                result.update(self._grid[cell])
        
        return list(result)
    
    def clear(self):
        """清空索引"""
        self._grid.clear()
        self._item_cells.clear()
    
    def _get_cells(self, rect: QRect) -> List[Tuple[int, int]]:
        """
        获取矩形覆盖的网格单元
        
        Args:
            rect: 矩形
            
        Returns:
            List[Tuple[int, int]]: 网格单元坐标列表
        """
        if rect.isEmpty():
            return []
        
        x1 = rect.left() // self._cell_size
        x2 = rect.right() // self._cell_size
        y1 = rect.top() // self._cell_size
        y2 = rect.bottom() // self._cell_size
        
        cells = []
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                cells.append((x, y))
        
        return cells
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息（用于测试）
        
        Returns:
            dict: 包含 query_count, insert_count, cell_count, item_count
        """
        return {
            "query_count": self._query_count,
            "insert_count": self._insert_count,
            "cell_count": len(self._grid),
            "item_count": len(self._item_cells)
        }
    
    def reset_stats(self):
        """重置统计信息（用于测试）"""
        self._query_count = 0
        self._insert_count = 0
