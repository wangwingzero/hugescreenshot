# -*- coding: utf-8 -*-
"""
截图模式管理器

Feature: extreme-performance-optimization
Requirements: 11.1, 11.2, 11.3, 12.4

设计原则：
1. 进入截图模式时暂停所有非必要的 UI 更新
2. 暂停历史面板的刷新和缩略图生成
3. 暂停剪贴板监听
4. 退出截图模式时恢复所有暂停的操作
5. 单例模式确保全局一致性

使用场景：
- 当用户按下截图热键时，进入截图模式
- 截图完成或取消时，退出截图模式
- 与 DeferredHistoryUpdate 集成，自动触发延迟历史更新
"""

from typing import Set, Callable, Optional
from PySide6.QtCore import QObject, Signal


class ScreenshotModeManager(QObject):
    """截图模式管理器
    
    Feature: extreme-performance-optimization
    Requirements: 11.1, 11.2, 11.3, 12.4
    
    进入截图模式时：
    1. 暂停所有窗口的非必要 UI 更新
    2. 暂停历史面板的刷新和缩略图生成
    3. 暂停剪贴板监听
    
    信号：
        mode_entered: 进入截图模式时发出
        mode_exited: 退出截图模式时发出
    
    Example:
        >>> manager = ScreenshotModeManager.instance()
        >>> manager.register_pause_callback(lambda: print("Paused"))
        >>> manager.register_resume_callback(lambda: print("Resumed"))
        >>> manager.enter_screenshot_mode()  # 输出: Paused
        >>> manager.exit_screenshot_mode()   # 输出: Resumed
    """
    
    # 信号定义
    mode_entered = Signal()   # 进入截图模式
    mode_exited = Signal()    # 退出截图模式
    
    # 单例实例
    _instance: Optional['ScreenshotModeManager'] = None
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化截图模式管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        
        # 截图模式标志
        self._in_screenshot_mode = False
        
        # 暂停回调（进入截图模式时调用）
        self._pause_callbacks: Set[Callable[[], None]] = set()
        
        # 恢复回调（退出截图模式时调用）
        self._resume_callbacks: Set[Callable[[], None]] = set()
        
        # 与 DeferredHistoryUpdate 集成
        self._integrate_with_deferred_history_update()
    
    def _integrate_with_deferred_history_update(self) -> None:
        """与 DeferredHistoryUpdate 集成
        
        进入截图模式时自动触发延迟历史更新。
        """
        try:
            from screenshot_tool.core.deferred_history_update import (
                DeferredHistoryUpdate
            )
            
            deferred_manager = DeferredHistoryUpdate.instance()
            
            # 注册暂停回调：进入截图模式时进入延迟模式
            self.register_pause_callback(deferred_manager.enter_deferred_mode)
            
            # 注册恢复回调：退出截图模式时退出延迟模式
            self.register_resume_callback(deferred_manager.exit_deferred_mode)
        except ImportError:
            # DeferredHistoryUpdate 不可用时忽略
            pass
    
    @classmethod
    def instance(cls) -> 'ScreenshotModeManager':
        """获取单例实例
        
        Returns:
            ScreenshotModeManager 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance._in_screenshot_mode = False
            cls._instance._pause_callbacks.clear()
            cls._instance._resume_callbacks.clear()
            cls._instance = None
    
    @property
    def is_active(self) -> bool:
        """是否处于截图模式
        
        Returns:
            True 表示处于截图模式
        """
        return self._in_screenshot_mode
    
    def register_pause_callback(self, callback: Callable[[], None]) -> None:
        """注册暂停回调（进入截图模式时调用）
        
        Args:
            callback: 回调函数，无参数无返回值
        """
        self._pause_callbacks.add(callback)
    
    def unregister_pause_callback(self, callback: Callable[[], None]) -> None:
        """取消注册暂停回调
        
        Args:
            callback: 回调函数
        """
        self._pause_callbacks.discard(callback)
    
    def register_resume_callback(self, callback: Callable[[], None]) -> None:
        """注册恢复回调（退出截图模式时调用）
        
        Args:
            callback: 回调函数，无参数无返回值
        """
        self._resume_callbacks.add(callback)
    
    def unregister_resume_callback(self, callback: Callable[[], None]) -> None:
        """取消注册恢复回调
        
        Args:
            callback: 回调函数
        """
        self._resume_callbacks.discard(callback)
    
    def enter_screenshot_mode(self) -> None:
        """进入截图模式
        
        截图开始时调用，暂停所有非必要的 UI 更新。
        如果已经处于截图模式，则忽略。
        """
        if self._in_screenshot_mode:
            return
        
        self._in_screenshot_mode = True
        
        # 调用所有暂停回调
        for callback in self._pause_callbacks:
            try:
                callback()
            except Exception:
                pass  # 忽略回调异常，确保不影响截图流程
        
        # 发出信号
        self.mode_entered.emit()
    
    def exit_screenshot_mode(self) -> None:
        """退出截图模式
        
        截图完成或取消时调用，恢复所有暂停的操作。
        如果不处于截图模式，则忽略。
        """
        if not self._in_screenshot_mode:
            return
        
        self._in_screenshot_mode = False
        
        # 调用所有恢复回调
        for callback in self._resume_callbacks:
            try:
                callback()
            except Exception:
                pass  # 忽略回调异常
        
        # 发出信号
        self.mode_exited.emit()
    
    def get_pause_callback_count(self) -> int:
        """获取已注册的暂停回调数量
        
        Returns:
            暂停回调数量
        """
        return len(self._pause_callbacks)
    
    def get_resume_callback_count(self) -> int:
        """获取已注册的恢复回调数量
        
        Returns:
            恢复回调数量
        """
        return len(self._resume_callbacks)


# 便捷函数
def get_screenshot_mode_manager() -> ScreenshotModeManager:
    """获取截图模式管理器实例
    
    Returns:
        ScreenshotModeManager 单例实例
    """
    return ScreenshotModeManager.instance()
