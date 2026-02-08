# -*- coding: utf-8 -*-
"""
后台任务管理器

Feature: extreme-performance-optimization
Requirements: 6.1, 6.2, 11.5

设计原则：
1. 使用全局 QThreadPool，线程数 = CPU 核心数 - 1
2. 支持任务优先级（HIGH, NORMAL, LOW）
3. 截图模式时暂停低优先级任务
4. 退出截图模式时恢复暂停的任务
5. 单例模式确保全局一致性

使用场景：
- OCR 识别任务（高优先级）
- 缩略图生成任务（低优先级）
- 文件 I/O 操作（普通优先级）
- 截图期间暂停低优先级任务，确保截图流畅
"""

from typing import Callable, Optional, List, Any
from enum import IntEnum
import os

from PySide6.QtCore import QThreadPool, QRunnable, QObject, Signal


class TaskPriority(IntEnum):
    """任务优先级
    
    Feature: extreme-performance-optimization
    Requirements: 6.2
    
    优先级值越高，任务越优先执行。
    """
    LOW = 0       # 低优先级：缩略图生成、预加载等
    NORMAL = 1    # 普通优先级：文件 I/O、一般后台任务
    HIGH = 2      # 高优先级：OCR、用户触发的任务


class BackgroundTaskSignals(QObject):
    """后台任务信号
    
    用于在任务完成或出错时通知主线程。
    """
    finished = Signal(object)  # 任务完成，参数为结果
    error = Signal(str)        # 任务出错，参数为错误信息
    progress = Signal(int)     # 任务进度，参数为百分比 (0-100)


class BackgroundTask(QRunnable):
    """后台任务
    
    Feature: extreme-performance-optimization
    Requirements: 6.1, 6.2
    
    封装一个可在后台线程执行的任务。
    
    Example:
        >>> def my_task(x, y):
        ...     return x + y
        >>> task = BackgroundTask(my_task, 1, 2)
        >>> task.signals.finished.connect(lambda r: print(f"Result: {r}"))
        >>> BackgroundTaskManager.instance().submit(task)
    """
    
    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> None:
        """初始化后台任务
        
        Args:
            func: 要执行的函数
            *args: 函数的位置参数
            **kwargs: 函数的关键字参数
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = BackgroundTaskSignals()
        self._cancelled = False
        
        # 设置自动删除
        self.setAutoDelete(True)
    
    def run(self) -> None:
        """执行任务
        
        在后台线程中执行，完成后发出 finished 或 error 信号。
        """
        if self._cancelled:
            return
        
        try:
            result = self.func(*self.args, **self.kwargs)
            if not self._cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.signals.error.emit(str(e))
    
    def cancel(self) -> None:
        """取消任务
        
        标记任务为已取消，任务执行时会检查此标志。
        注意：已经开始执行的任务无法中断，只能阻止结果发送。
        """
        self._cancelled = True
    
    @property
    def is_cancelled(self) -> bool:
        """任务是否已取消
        
        Returns:
            True 表示任务已取消
        """
        return self._cancelled


class BackgroundTaskManager(QObject):
    """后台任务管理器
    
    Feature: extreme-performance-optimization
    Requirements: 6.1, 6.2, 11.5
    
    优化策略：
    1. 全局线程池，线程数 = CPU 核心数 - 1
    2. 支持任务优先级
    3. 截图模式时暂停低优先级任务
    
    信号：
        low_priority_paused: 低优先级任务被暂停时发出
        low_priority_resumed: 低优先级任务恢复时发出，参数为恢复的任务数量
    
    Example:
        >>> manager = BackgroundTaskManager.instance()
        >>> task = BackgroundTask(lambda: "Hello")
        >>> task.signals.finished.connect(print)
        >>> manager.submit(task, TaskPriority.NORMAL)
    """
    
    # 信号定义
    low_priority_paused = Signal()   # 低优先级任务被暂停
    low_priority_resumed = Signal(int)  # 低优先级任务恢复，参数为任务数量
    
    # 单例实例
    _instance: Optional['BackgroundTaskManager'] = None
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化后台任务管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        
        # 使用全局线程池
        self._pool = QThreadPool.globalInstance()
        
        # 设置最大线程数为 CPU 核心数 - 1，保留一个给主线程
        cpu_count = os.cpu_count()
        max_threads = max(1, cpu_count - 1) if cpu_count else 2
        self._pool.setMaxThreadCount(max_threads)
        
        # 暂停标志
        self._paused = False
        
        # 暂存的低优先级任务
        self._pending_low_priority: List[BackgroundTask] = []
        
        # 与 ScreenshotModeManager 集成
        self._integrate_with_screenshot_mode_manager()
    
    def _integrate_with_screenshot_mode_manager(self) -> None:
        """与 ScreenshotModeManager 集成
        
        进入截图模式时自动暂停低优先级任务。
        """
        try:
            from screenshot_tool.core.screenshot_mode_manager import (
                ScreenshotModeManager
            )
            
            mode_manager = ScreenshotModeManager.instance()
            
            # 注册暂停回调：进入截图模式时暂停低优先级任务
            mode_manager.register_pause_callback(self.pause_low_priority)
            
            # 注册恢复回调：退出截图模式时恢复低优先级任务
            mode_manager.register_resume_callback(self.resume_low_priority)
        except ImportError:
            # ScreenshotModeManager 不可用时忽略
            pass
    
    @classmethod
    def instance(cls) -> 'BackgroundTaskManager':
        """获取单例实例
        
        Returns:
            BackgroundTaskManager 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            # 取消所有暂存的任务
            for task in cls._instance._pending_low_priority:
                task.cancel()
            cls._instance._pending_low_priority.clear()
            cls._instance._paused = False
            cls._instance = None
    
    @property
    def is_paused(self) -> bool:
        """低优先级任务是否被暂停
        
        Returns:
            True 表示低优先级任务被暂停
        """
        return self._paused
    
    @property
    def pending_count(self) -> int:
        """获取暂存的低优先级任务数量
        
        Returns:
            暂存的任务数量
        """
        return len(self._pending_low_priority)
    
    @property
    def max_thread_count(self) -> int:
        """获取最大线程数
        
        Returns:
            线程池的最大线程数
        """
        return self._pool.maxThreadCount()
    
    @property
    def active_thread_count(self) -> int:
        """获取当前活动线程数
        
        Returns:
            当前正在执行任务的线程数
        """
        return self._pool.activeThreadCount()
    
    def submit(
        self,
        task: BackgroundTask,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> bool:
        """提交任务
        
        Args:
            task: 要执行的后台任务
            priority: 任务优先级，默认为 NORMAL
            
        Returns:
            True 表示任务已提交或暂存，False 表示任务被拒绝
        """
        if task.is_cancelled:
            return False
        
        # 截图模式时，低优先级任务暂存
        if self._paused and priority == TaskPriority.LOW:
            self._pending_low_priority.append(task)
            return True
        
        # 提交到线程池
        self._pool.start(task, int(priority))
        return True
    
    def submit_func(
        self,
        func: Callable[..., Any],
        *args: Any,
        priority: TaskPriority = TaskPriority.NORMAL,
        on_finished: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        **kwargs: Any
    ) -> BackgroundTask:
        """便捷方法：提交一个函数作为后台任务
        
        Args:
            func: 要执行的函数
            *args: 函数的位置参数
            priority: 任务优先级，默认为 NORMAL
            on_finished: 任务完成时的回调
            on_error: 任务出错时的回调
            **kwargs: 函数的关键字参数
            
        Returns:
            创建的 BackgroundTask 实例
        """
        task = BackgroundTask(func, *args, **kwargs)
        
        if on_finished:
            task.signals.finished.connect(on_finished)
        if on_error:
            task.signals.error.connect(on_error)
        
        self.submit(task, priority)
        return task
    
    def pause_low_priority(self) -> None:
        """暂停低优先级任务（进入截图模式）
        
        新提交的低优先级任务将被暂存，直到调用 resume_low_priority()。
        """
        if self._paused:
            return
        
        self._paused = True
        self.low_priority_paused.emit()
    
    def resume_low_priority(self) -> None:
        """恢复低优先级任务（退出截图模式）
        
        提交所有暂存的低优先级任务。
        """
        if not self._paused:
            return
        
        self._paused = False
        
        # 获取暂存的任务数量
        pending_count = len(self._pending_low_priority)
        
        # 提交暂存的任务
        for task in self._pending_low_priority:
            if not task.is_cancelled:
                self._pool.start(task, int(TaskPriority.LOW))
        
        self._pending_low_priority.clear()
        
        # 发出信号
        self.low_priority_resumed.emit(pending_count)
    
    def cancel_pending(self) -> int:
        """取消所有暂存的低优先级任务
        
        Returns:
            取消的任务数量
        """
        count = len(self._pending_low_priority)
        
        for task in self._pending_low_priority:
            task.cancel()
        
        self._pending_low_priority.clear()
        return count
    
    def wait_for_done(self, timeout_ms: int = -1) -> bool:
        """等待所有任务完成
        
        Args:
            timeout_ms: 超时时间（毫秒），-1 表示无限等待
            
        Returns:
            True 表示所有任务已完成，False 表示超时
        """
        return self._pool.waitForDone(timeout_ms)
    
    def clear(self) -> None:
        """清除线程池中所有待执行的任务
        
        注意：已经开始执行的任务无法取消。
        """
        self._pool.clear()
        self.cancel_pending()


# 便捷函数
def get_background_task_manager() -> BackgroundTaskManager:
    """获取后台任务管理器实例
    
    Returns:
        BackgroundTaskManager 单例实例
    """
    return BackgroundTaskManager.instance()


def submit_background_task(
    func: Callable[..., Any],
    *args: Any,
    priority: TaskPriority = TaskPriority.NORMAL,
    on_finished: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    **kwargs: Any
) -> BackgroundTask:
    """便捷函数：提交一个后台任务
    
    Args:
        func: 要执行的函数
        *args: 函数的位置参数
        priority: 任务优先级，默认为 NORMAL
        on_finished: 任务完成时的回调
        on_error: 任务出错时的回调
        **kwargs: 函数的关键字参数
        
    Returns:
        创建的 BackgroundTask 实例
        
    Example:
        >>> def process_image(path):
        ...     # 处理图片
        ...     return "done"
        >>> submit_background_task(
        ...     process_image,
        ...     "image.png",
        ...     priority=TaskPriority.LOW,
        ...     on_finished=lambda r: print(f"Result: {r}")
        ... )
    """
    return get_background_task_manager().submit_func(
        func, *args,
        priority=priority,
        on_finished=on_finished,
        on_error=on_error,
        **kwargs
    )
