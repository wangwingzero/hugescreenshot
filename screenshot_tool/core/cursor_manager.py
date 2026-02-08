# =====================================================
# =============== 节流光标管理器 ===============
# =====================================================

"""
节流光标管理器 - 优化光标更新性能

特性：
- 16ms 节流控制（60fps）
- 光标样式缓存（跳过相同光标）
- 减少不必要的 setCursor 调用
"""

import time
from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QWidget


class ThrottledCursorManager:
    """节流的光标管理器"""
    
    THROTTLE_MS = 16  # 60fps，约 16ms 一帧
    
    def __init__(self):
        """初始化光标管理器"""
        self._last_update_time: float = 0
        self._last_cursor: Optional[Qt.CursorShape] = None
        self._pending_cursor: Optional[Qt.CursorShape] = None
        
        # 统计信息（用于测试）
        self._update_count: int = 0
        self._skip_count: int = 0
        self._throttle_count: int = 0
    
    def update_cursor(self, new_cursor: Qt.CursorShape, widget: QWidget, force: bool = False) -> bool:
        """
        节流更新光标
        
        Args:
            new_cursor: 新的光标样式
            widget: 要设置光标的 widget
            force: 是否强制更新（忽略节流）
            
        Returns:
            bool: 是否实际更新了光标
        """
        now = time.time() * 1000  # 转换为毫秒
        
        # 节流检查（除非强制更新）
        if not force:
            time_since_last = now - self._last_update_time
            if time_since_last < self.THROTTLE_MS:
                self._pending_cursor = new_cursor
                self._throttle_count += 1
                return False
        
        # 跳过相同光标
        if new_cursor == self._last_cursor:
            self._skip_count += 1
            return False
        
        # 实际更新光标
        widget.setCursor(new_cursor)
        self._last_cursor = new_cursor
        self._last_update_time = now
        self._pending_cursor = None
        self._update_count += 1
        
        return True
    
    def flush_pending(self, widget: QWidget) -> bool:
        """
        刷新待处理的光标更新
        
        在节流期间可能有待处理的光标更新，调用此方法强制应用
        
        Args:
            widget: 要设置光标的 widget
            
        Returns:
            bool: 是否有待处理的更新被应用
        """
        if self._pending_cursor is not None and self._pending_cursor != self._last_cursor:
            widget.setCursor(self._pending_cursor)
            self._last_cursor = self._pending_cursor
            self._pending_cursor = None
            self._last_update_time = time.time() * 1000
            self._update_count += 1
            return True
        return False
    
    def reset(self):
        """重置光标管理器状态"""
        self._last_update_time = 0
        self._last_cursor = None
        self._pending_cursor = None
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息（用于测试）
        
        Returns:
            dict: 包含 update_count, skip_count, throttle_count
        """
        return {
            "update_count": self._update_count,
            "skip_count": self._skip_count,
            "throttle_count": self._throttle_count
        }
    
    def reset_stats(self):
        """重置统计信息（用于测试）"""
        self._update_count = 0
        self._skip_count = 0
        self._throttle_count = 0
