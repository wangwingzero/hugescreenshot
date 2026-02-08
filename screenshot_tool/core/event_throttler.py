# -*- coding: utf-8 -*-
"""
事件节流器和信号防抖器

Feature: extreme-performance-optimization
Requirements: 10.1, 10.2

设计原则：
1. EventThrottler: 限制高频事件处理频率到 60 FPS (16ms)
2. SignalDebouncer: 延迟信号发射直到活动停止
3. 支持可配置的时间间隔
4. 使用 QTimer 进行计时

使用场景：
- 鼠标移动事件节流（截图选区拖动）
- 滚动事件节流（历史列表滚动）
- 窗口大小调整事件节流
- 信号防抖（历史列表更新、搜索输入）
"""

from typing import Callable, Optional, Any, Tuple, Dict
from PySide6.QtCore import QTimer, QObject


class EventThrottler(QObject):
    """事件节流器
    
    Feature: extreme-performance-optimization
    Requirements: 10.1, 10.2
    
    用于限制高频事件（如鼠标移动、滚动）的处理频率。
    在指定时间间隔内只执行最后一次调用。
    
    默认间隔为 16ms，对应 60 FPS。
    
    Example:
        >>> throttler = EventThrottler(interval_ms=16)
        >>> def on_mouse_move(x, y):
        ...     print(f"Mouse at ({x}, {y})")
        >>> # 快速调用多次，只有最后一次会在 16ms 后执行
        >>> throttler.throttle(on_mouse_move, 100, 200)
        >>> throttler.throttle(on_mouse_move, 110, 210)
        >>> throttler.throttle(on_mouse_move, 120, 220)  # 只有这次会执行
    """
    
    # 默认节流间隔：16ms (60 FPS)
    DEFAULT_INTERVAL_MS = 16
    
    def __init__(
        self,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        parent: Optional[QObject] = None
    ) -> None:
        """初始化事件节流器
        
        Args:
            interval_ms: 节流间隔（毫秒），默认 16ms (60 FPS)
            parent: 父对象
        """
        super().__init__(parent)
        
        self._interval = interval_ms
        
        # 单次触发定时器
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        
        # 待执行的回调和参数
        self._pending_callback: Optional[Callable[..., Any]] = None
        self._pending_args: Tuple[Any, ...] = ()
        self._pending_kwargs: Dict[str, Any] = {}
        
        # 统计信息
        self._throttled_count = 0
        self._executed_count = 0
    
    @property
    def interval(self) -> int:
        """获取节流间隔（毫秒）
        
        Returns:
            节流间隔
        """
        return self._interval
    
    @interval.setter
    def interval(self, value: int) -> None:
        """设置节流间隔（毫秒）
        
        Args:
            value: 新的节流间隔，必须 > 0
        """
        if value <= 0:
            raise ValueError("Interval must be positive")
        self._interval = value
    
    @property
    def is_pending(self) -> bool:
        """是否有待执行的回调
        
        Returns:
            True 表示有待执行的回调
        """
        return self._timer.isActive()
    
    @property
    def throttled_count(self) -> int:
        """获取被节流的调用次数
        
        Returns:
            被节流的调用次数
        """
        return self._throttled_count
    
    @property
    def executed_count(self) -> int:
        """获取实际执行的调用次数
        
        Returns:
            实际执行的调用次数
        """
        return self._executed_count
    
    def throttle(
        self,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> None:
        """节流调用
        
        在 interval_ms 内只执行最后一次调用。
        如果定时器已在运行，则更新待执行的回调和参数。
        如果定时器未运行，则启动定时器。
        
        Args:
            callback: 要执行的回调函数
            *args: 回调函数的位置参数
            **kwargs: 回调函数的关键字参数
        """
        # 更新待执行的回调和参数
        self._pending_callback = callback
        self._pending_args = args
        self._pending_kwargs = kwargs
        
        # 如果定时器未运行，启动定时器
        if not self._timer.isActive():
            self._timer.start(self._interval)
        else:
            # 定时器已在运行，记录被节流的调用
            self._throttled_count += 1
    
    def _on_timeout(self) -> None:
        """定时器超时回调
        
        执行待处理的回调函数。
        """
        if self._pending_callback is not None:
            try:
                self._pending_callback(
                    *self._pending_args,
                    **self._pending_kwargs
                )
                self._executed_count += 1
            except Exception:
                # 忽略回调中的异常，避免影响节流器
                pass
            finally:
                # 清除待执行的回调
                self._pending_callback = None
                self._pending_args = ()
                self._pending_kwargs = {}
    
    def cancel(self) -> None:
        """取消待执行的回调
        
        停止定时器并清除待执行的回调。
        """
        self._timer.stop()
        self._pending_callback = None
        self._pending_args = ()
        self._pending_kwargs = {}
    
    def flush(self) -> None:
        """立即执行待处理的回调
        
        如果有待执行的回调，立即执行并停止定时器。
        """
        if self._timer.isActive() and self._pending_callback is not None:
            self._timer.stop()
            self._on_timeout()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._throttled_count = 0
        self._executed_count = 0


class SignalDebouncer(QObject):
    """信号防抖器
    
    Feature: extreme-performance-optimization
    Requirements: 10.2, 11.6, 12.3
    
    用于防止信号频繁触发导致的性能问题。
    延迟执行回调，直到指定时间内没有新的调用。
    
    与 EventThrottler 的区别：
    - EventThrottler: 在间隔内执行最后一次调用（节流）
    - SignalDebouncer: 等待活动停止后才执行（防抖）
    
    Example:
        >>> debouncer = SignalDebouncer(delay_ms=200)
        >>> def on_search(text):
        ...     print(f"Searching: {text}")
        >>> # 快速输入，只有最后一次会在 200ms 后执行
        >>> debouncer.debounce(on_search, "h")
        >>> debouncer.debounce(on_search, "he")
        >>> debouncer.debounce(on_search, "hel")
        >>> debouncer.debounce(on_search, "hell")
        >>> debouncer.debounce(on_search, "hello")  # 200ms 后执行
    """
    
    # 默认防抖延迟：200ms
    DEFAULT_DELAY_MS = 200
    
    def __init__(
        self,
        delay_ms: int = DEFAULT_DELAY_MS,
        parent: Optional[QObject] = None
    ) -> None:
        """初始化信号防抖器
        
        Args:
            delay_ms: 防抖延迟（毫秒），默认 200ms
            parent: 父对象
        """
        super().__init__(parent)
        
        self._delay = delay_ms
        
        # 单次触发定时器
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        
        # 待执行的回调和参数
        self._callback: Optional[Callable[..., Any]] = None
        self._args: Tuple[Any, ...] = ()
        self._kwargs: Dict[str, Any] = {}
        
        # 统计信息
        self._debounced_count = 0
        self._executed_count = 0
    
    @property
    def delay(self) -> int:
        """获取防抖延迟（毫秒）
        
        Returns:
            防抖延迟
        """
        return self._delay
    
    @delay.setter
    def delay(self, value: int) -> None:
        """设置防抖延迟（毫秒）
        
        Args:
            value: 新的防抖延迟，必须 > 0
        """
        if value <= 0:
            raise ValueError("Delay must be positive")
        self._delay = value
    
    @property
    def is_pending(self) -> bool:
        """是否有待执行的回调
        
        Returns:
            True 表示有待执行的回调
        """
        return self._timer.isActive()
    
    @property
    def debounced_count(self) -> int:
        """获取被防抖的调用次数
        
        Returns:
            被防抖的调用次数
        """
        return self._debounced_count
    
    @property
    def executed_count(self) -> int:
        """获取实际执行的调用次数
        
        Returns:
            实际执行的调用次数
        """
        return self._executed_count
    
    def debounce(
        self,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> None:
        """防抖调用
        
        延迟 delay_ms 后执行，期间如有新调用则重新计时。
        
        Args:
            callback: 要执行的回调函数
            *args: 回调函数的位置参数
            **kwargs: 回调函数的关键字参数
        """
        # 如果定时器已在运行，记录被防抖的调用
        if self._timer.isActive():
            self._debounced_count += 1
        
        # 更新待执行的回调和参数
        self._callback = callback
        self._args = args
        self._kwargs = kwargs
        
        # 重新启动定时器（重置计时）
        self._timer.start(self._delay)
    
    def _on_timeout(self) -> None:
        """定时器超时回调
        
        执行待处理的回调函数。
        """
        if self._callback is not None:
            try:
                self._callback(*self._args, **self._kwargs)
                self._executed_count += 1
            except Exception:
                # 忽略回调中的异常，避免影响防抖器
                pass
            finally:
                # 清除待执行的回调
                self._callback = None
                self._args = ()
                self._kwargs = {}
    
    def cancel(self) -> None:
        """取消待执行的回调
        
        停止定时器并清除待执行的回调。
        """
        self._timer.stop()
        self._callback = None
        self._args = ()
        self._kwargs = {}
    
    def flush(self) -> None:
        """立即执行待处理的回调
        
        如果有待执行的回调，立即执行并停止定时器。
        """
        if self._timer.isActive() and self._callback is not None:
            self._timer.stop()
            self._on_timeout()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._debounced_count = 0
        self._executed_count = 0


# 便捷函数：创建预配置的节流器和防抖器

def create_mouse_throttler(parent: Optional[QObject] = None) -> EventThrottler:
    """创建鼠标事件节流器
    
    预配置为 60 FPS (16ms)，适用于鼠标移动事件。
    
    Args:
        parent: 父对象
        
    Returns:
        配置好的 EventThrottler 实例
    """
    return EventThrottler(interval_ms=16, parent=parent)


def create_scroll_throttler(parent: Optional[QObject] = None) -> EventThrottler:
    """创建滚动事件节流器
    
    预配置为 60 FPS (16ms)，适用于滚动事件。
    
    Args:
        parent: 父对象
        
    Returns:
        配置好的 EventThrottler 实例
    """
    return EventThrottler(interval_ms=16, parent=parent)


def create_resize_throttler(parent: Optional[QObject] = None) -> EventThrottler:
    """创建窗口大小调整节流器
    
    预配置为 30 FPS (33ms)，适用于窗口大小调整事件。
    
    Args:
        parent: 父对象
        
    Returns:
        配置好的 EventThrottler 实例
    """
    return EventThrottler(interval_ms=33, parent=parent)


def create_search_debouncer(parent: Optional[QObject] = None) -> SignalDebouncer:
    """创建搜索输入防抖器
    
    预配置为 300ms 延迟，适用于搜索输入。
    
    Args:
        parent: 父对象
        
    Returns:
        配置好的 SignalDebouncer 实例
    """
    return SignalDebouncer(delay_ms=300, parent=parent)


def create_history_update_debouncer(
    parent: Optional[QObject] = None
) -> SignalDebouncer:
    """创建历史更新防抖器
    
    预配置为 200ms 延迟，适用于历史列表更新。
    
    Args:
        parent: 父对象
        
    Returns:
        配置好的 SignalDebouncer 实例
    """
    return SignalDebouncer(delay_ms=200, parent=parent)

