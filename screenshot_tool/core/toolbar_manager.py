# =====================================================
# =============== 缓存工具栏管理器 ===============
# =====================================================

"""
缓存工具栏管理器 - 优化工具栏位置计算

特性：
- 位置缓存（选区不变时直接返回缓存）
- 50ms 节流控制
- 减少不必要的位置计算
"""

import time
from typing import Optional, Dict, Tuple
from PySide6.QtCore import QPoint, QRect


class CachedToolbarManager:
    """带缓存的工具栏管理器"""
    
    THROTTLE_MS = 50  # 50ms 节流
    
    def __init__(self):
        """初始化工具栏管理器"""
        # 底部工具栏缓存
        self._cached_bottom_position: Optional[QPoint] = None
        self._cached_bottom_selection: Optional[QRect] = None
        
        # 侧边工具栏缓存
        self._cached_side_position: Optional[QPoint] = None
        self._cached_side_selection: Optional[QRect] = None
        
        # 节流控制
        self._last_update_time: float = 0
        
        # 屏幕边界（用于边界检测）
        self._screen_rect: Optional[QRect] = None
        
        # 统计信息（用于测试）
        self._calc_count: int = 0
        self._cache_hit_count: int = 0
        self._throttle_count: int = 0
    
    def set_screen_rect(self, rect: QRect):
        """设置屏幕边界"""
        self._screen_rect = rect
    
    def get_bottom_toolbar_position(
        self, 
        selection: QRect, 
        toolbar_size: Tuple[int, int],
        force: bool = False
    ) -> QPoint:
        """
        获取底部工具栏位置（带缓存）
        
        Args:
            selection: 选区矩形
            toolbar_size: 工具栏尺寸 (width, height)
            force: 是否强制重新计算
            
        Returns:
            QPoint: 工具栏位置
        """
        # 检查缓存
        if not force and self._cached_bottom_selection == selection:
            self._cache_hit_count += 1
            return self._cached_bottom_position
        
        # 节流检查
        now = time.time() * 1000
        if not force and now - self._last_update_time < self.THROTTLE_MS:
            self._throttle_count += 1
            if self._cached_bottom_position:
                return self._cached_bottom_position
        
        # 计算新位置
        position = self._calculate_bottom_position(selection, toolbar_size)
        
        # 更新缓存
        self._cached_bottom_position = position
        self._cached_bottom_selection = QRect(selection)
        self._last_update_time = now
        self._calc_count += 1
        
        return position
    
    def get_side_toolbar_position(
        self, 
        selection: QRect, 
        toolbar_size: Tuple[int, int],
        force: bool = False
    ) -> QPoint:
        """
        获取侧边工具栏位置（带缓存）
        
        Args:
            selection: 选区矩形
            toolbar_size: 工具栏尺寸 (width, height)
            force: 是否强制重新计算
            
        Returns:
            QPoint: 工具栏位置
        """
        # 检查缓存
        if not force and self._cached_side_selection == selection:
            self._cache_hit_count += 1
            return self._cached_side_position
        
        # 节流检查
        now = time.time() * 1000
        if not force and now - self._last_update_time < self.THROTTLE_MS:
            self._throttle_count += 1
            if self._cached_side_position:
                return self._cached_side_position
        
        # 计算新位置
        position = self._calculate_side_position(selection, toolbar_size)
        
        # 更新缓存
        self._cached_side_position = position
        self._cached_side_selection = QRect(selection)
        self._last_update_time = now
        self._calc_count += 1
        
        return position
    
    def _calculate_bottom_position(
        self, 
        selection: QRect, 
        toolbar_size: Tuple[int, int]
    ) -> QPoint:
        """
        计算底部工具栏位置
        
        优先显示在选区下方，空间不足时显示在上方
        """
        toolbar_width, toolbar_height = toolbar_size
        margin = 8
        
        # 默认位置：选区下方居中
        x = selection.left() + (selection.width() - toolbar_width) // 2
        y = selection.bottom() + margin
        
        # 边界检测
        if self._screen_rect:
            # 检查下方空间
            if y + toolbar_height > self._screen_rect.bottom():
                # 空间不足，显示在上方
                y = selection.top() - toolbar_height - margin
            
            # 检查左右边界
            if x < self._screen_rect.left():
                x = self._screen_rect.left() + margin
            elif x + toolbar_width > self._screen_rect.right():
                x = self._screen_rect.right() - toolbar_width - margin
            
            # 检查上边界
            if y < self._screen_rect.top():
                y = self._screen_rect.top() + margin
        
        return QPoint(x, y)
    
    def _calculate_side_position(
        self, 
        selection: QRect, 
        toolbar_size: Tuple[int, int]
    ) -> QPoint:
        """
        计算侧边工具栏位置
        
        优先显示在选区右侧，空间不足时显示在左侧
        """
        toolbar_width, toolbar_height = toolbar_size
        margin = 8
        
        # 默认位置：选区右侧顶部对齐
        x = selection.right() + margin
        y = selection.top()
        
        # 边界检测
        if self._screen_rect:
            # 检查右侧空间
            if x + toolbar_width > self._screen_rect.right():
                # 空间不足，显示在左侧
                x = selection.left() - toolbar_width - margin
            
            # 检查左边界
            if x < self._screen_rect.left():
                x = self._screen_rect.left() + margin
            
            # 检查上下边界
            if y < self._screen_rect.top():
                y = self._screen_rect.top() + margin
            elif y + toolbar_height > self._screen_rect.bottom():
                y = self._screen_rect.bottom() - toolbar_height - margin
        
        return QPoint(x, y)
    
    def invalidate_cache(self):
        """使缓存失效"""
        self._cached_bottom_position = None
        self._cached_bottom_selection = None
        self._cached_side_position = None
        self._cached_side_selection = None
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息（用于测试）
        
        Returns:
            dict: 包含 calc_count, cache_hit_count, throttle_count
        """
        return {
            "calc_count": self._calc_count,
            "cache_hit_count": self._cache_hit_count,
            "throttle_count": self._throttle_count
        }
    
    def reset_stats(self):
        """重置统计信息（用于测试）"""
        self._calc_count = 0
        self._cache_hit_count = 0
        self._throttle_count = 0
