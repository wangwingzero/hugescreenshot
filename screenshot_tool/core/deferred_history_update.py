# -*- coding: utf-8 -*-
"""
延迟历史更新管理器

Feature: extreme-performance-optimization
Requirements: 11.9, 12.4

设计原则：
1. 截图模式开始时暂停历史更新
2. 截图模式结束时处理所有暂存的更新
3. 使用信号与 ClipboardHistoryWindow 通信
4. 单例模式确保全局一致性

使用场景：
- 当用户在工作台窗口打开时进行截图，避免历史列表刷新导致卡顿
- 截图完成后批量处理所有暂存的更新
"""

from typing import List, Callable, Optional, Set
from PySide6.QtCore import QObject, Signal


class DeferredHistoryUpdate(QObject):
    """延迟历史更新管理器
    
    Feature: extreme-performance-optimization
    Requirements: 11.9, 12.4
    
    截图模式期间暂停历史更新，截图完成后批量处理。
    
    信号：
        updates_deferred: 进入延迟模式时发出
        updates_resumed: 退出延迟模式时发出，参数为暂存的更新数量
    
    Example:
        >>> manager = DeferredHistoryUpdate.instance()
        >>> manager.enter_deferred_mode()
        >>> manager.queue_update("item-1")  # 暂存更新
        >>> manager.queue_update("item-2")  # 暂存更新
        >>> manager.exit_deferred_mode()    # 触发 updates_resumed 信号
    """
    
    # 信号定义
    updates_deferred = Signal()   # 进入延迟模式
    updates_resumed = Signal(int)  # 退出延迟模式，参数为暂存的更新数量
    
    # 单例实例
    _instance: Optional['DeferredHistoryUpdate'] = None
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化延迟历史更新管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        
        # 延迟模式标志
        self._is_deferred = False
        
        # 暂存的更新（条目 ID 集合，避免重复）
        self._pending_updates: Set[str] = set()
        
        # 暂存的回调函数
        self._pending_callbacks: List[Callable[[], None]] = []
        
        # 恢复时的回调（由 ClipboardHistoryWindow 注册）
        self._resume_callbacks: Set[Callable[[int], None]] = set()
        
        # 暂停时的回调
        self._pause_callbacks: Set[Callable[[], None]] = set()
    
    @classmethod
    def instance(cls) -> 'DeferredHistoryUpdate':
        """获取单例实例
        
        Returns:
            DeferredHistoryUpdate 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance._is_deferred = False
            cls._instance._pending_updates.clear()
            cls._instance._pending_callbacks.clear()
            cls._instance = None
    
    @property
    def is_deferred(self) -> bool:
        """是否处于延迟模式
        
        Returns:
            True 表示处于延迟模式，历史更新被暂停
        """
        return self._is_deferred
    
    @property
    def pending_count(self) -> int:
        """获取暂存的更新数量
        
        Returns:
            暂存的更新数量
        """
        return len(self._pending_updates) + len(self._pending_callbacks)
    
    def register_pause_callback(self, callback: Callable[[], None]) -> None:
        """注册暂停回调（进入延迟模式时调用）
        
        Args:
            callback: 回调函数
        """
        self._pause_callbacks.add(callback)
    
    def unregister_pause_callback(self, callback: Callable[[], None]) -> None:
        """取消注册暂停回调
        
        Args:
            callback: 回调函数
        """
        self._pause_callbacks.discard(callback)
    
    def register_resume_callback(self, callback: Callable[[int], None]) -> None:
        """注册恢复回调（退出延迟模式时调用）
        
        Args:
            callback: 回调函数，参数为暂存的更新数量
        """
        self._resume_callbacks.add(callback)
    
    def unregister_resume_callback(self, callback: Callable[[int], None]) -> None:
        """取消注册恢复回调
        
        Args:
            callback: 回调函数
        """
        self._resume_callbacks.discard(callback)
    
    def enter_deferred_mode(self) -> None:
        """进入延迟模式
        
        截图开始时调用，暂停所有历史更新。
        如果已经处于延迟模式，则忽略。
        """
        if self._is_deferred:
            return
        
        self._is_deferred = True
        
        # 调用暂停回调
        for callback in self._pause_callbacks:
            try:
                callback()
            except Exception:
                pass  # 忽略回调异常，确保不影响截图流程
        
        # 发出信号
        self.updates_deferred.emit()
    
    def exit_deferred_mode(self) -> None:
        """退出延迟模式
        
        截图完成时调用，处理所有暂存的更新。
        如果不处于延迟模式，则忽略。
        """
        if not self._is_deferred:
            return
        
        self._is_deferred = False
        
        # 获取暂存的更新数量
        pending_count = self.pending_count
        
        # 执行暂存的回调
        callbacks = self._pending_callbacks.copy()
        self._pending_callbacks.clear()
        
        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass  # 忽略回调异常
        
        # 清空暂存的更新 ID
        self._pending_updates.clear()
        
        # 调用恢复回调
        for callback in self._resume_callbacks:
            try:
                callback(pending_count)
            except Exception:
                pass  # 忽略回调异常
        
        # 发出信号
        self.updates_resumed.emit(pending_count)
    
    def queue_update(self, item_id: str) -> bool:
        """暂存一个更新
        
        如果处于延迟模式，将更新暂存；否则返回 False 表示应立即处理。
        
        Args:
            item_id: 历史条目 ID
            
        Returns:
            True 表示已暂存，False 表示应立即处理
        """
        if not self._is_deferred:
            return False
        
        self._pending_updates.add(item_id)
        return True
    
    def queue_callback(self, callback: Callable[[], None]) -> bool:
        """暂存一个回调
        
        如果处于延迟模式，将回调暂存；否则返回 False 表示应立即执行。
        
        Args:
            callback: 回调函数
            
        Returns:
            True 表示已暂存，False 表示应立即执行
        """
        if not self._is_deferred:
            return False
        
        self._pending_callbacks.append(callback)
        return True
    
    def get_pending_updates(self) -> Set[str]:
        """获取暂存的更新 ID 集合
        
        Returns:
            暂存的更新 ID 集合的副本
        """
        return self._pending_updates.copy()
    
    def has_pending_updates(self) -> bool:
        """是否有暂存的更新
        
        Returns:
            True 表示有暂存的更新
        """
        return len(self._pending_updates) > 0 or len(self._pending_callbacks) > 0
    
    def clear_pending(self) -> None:
        """清空所有暂存的更新（不执行）
        
        用于取消截图等场景。
        """
        self._pending_updates.clear()
        self._pending_callbacks.clear()


# 便捷函数
def get_deferred_history_update() -> DeferredHistoryUpdate:
    """获取延迟历史更新管理器实例
    
    Returns:
        DeferredHistoryUpdate 单例实例
    """
    return DeferredHistoryUpdate.instance()
