# =====================================================
# =============== 空闲检测器 ===============
# =====================================================

"""
空闲检测器 - 检测用户空闲状态并自动释放非必要缓存

功能：
1. 监测用户活动（鼠标移动、键盘输入等）
2. 空闲超过指定时间后触发回调
3. 用户恢复活动时重置计时器
"""

import time
from typing import Callable, Optional
from PySide6.QtCore import QTimer, QObject, Signal


class IdleDetector(QObject):
    """空闲检测器
    
    检测用户空闲状态，空闲超过指定时间后触发回调。
    
    Attributes:
        idle_timeout_ms: 空闲超时时间（毫秒）
        on_idle: 空闲时触发的回调
        on_active: 恢复活动时触发的回调
    """
    
    # 信号
    idleDetected = Signal()  # 检测到空闲
    activityDetected = Signal()  # 检测到活动
    
    # 默认空闲超时时间（30秒）
    DEFAULT_IDLE_TIMEOUT_MS = 30000
    
    # 检查间隔（1秒）
    CHECK_INTERVAL_MS = 1000
    
    def __init__(
        self, 
        idle_timeout_ms: int = DEFAULT_IDLE_TIMEOUT_MS,
        on_idle: Optional[Callable[[], None]] = None,
        on_active: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None
    ):
        """初始化空闲检测器
        
        Args:
            idle_timeout_ms: 空闲超时时间（毫秒）
            on_idle: 空闲时触发的回调
            on_active: 恢复活动时触发的回调
            parent: 父对象
        """
        super().__init__(parent)
        
        self._idle_timeout_ms = idle_timeout_ms
        self._on_idle = on_idle
        self._on_active = on_active
        
        # 上次活动时间
        self._last_activity_time: float = time.time()
        
        # 是否处于空闲状态
        self._is_idle: bool = False
        
        # 检查定时器
        self._check_timer: Optional[QTimer] = None
        
        # 是否正在运行
        self._running: bool = False
    
    @property
    def idle_timeout_ms(self) -> int:
        """获取空闲超时时间"""
        return self._idle_timeout_ms
    
    @idle_timeout_ms.setter
    def idle_timeout_ms(self, value: int):
        """设置空闲超时时间"""
        self._idle_timeout_ms = max(1000, value)  # 最小1秒
    
    @property
    def is_idle(self) -> bool:
        """是否处于空闲状态"""
        return self._is_idle
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    def start(self):
        """启动空闲检测"""
        if self._running:
            return
        
        self._running = True
        self._is_idle = False
        self._last_activity_time = time.time()
        
        # 创建并启动检查定时器
        if self._check_timer is None:
            self._check_timer = QTimer(self)
            self._check_timer.timeout.connect(self._check_idle)
        
        self._check_timer.start(self.CHECK_INTERVAL_MS)
    
    def stop(self):
        """停止空闲检测"""
        if not self._running:
            return
        
        self._running = False
        
        if self._check_timer:
            self._check_timer.stop()
    
    def record_activity(self):
        """记录用户活动
        
        应该在检测到用户活动时调用（如鼠标移动、键盘输入等）
        """
        self._last_activity_time = time.time()
        
        # 如果之前是空闲状态，触发恢复活动回调
        if self._is_idle:
            self._is_idle = False
            self.activityDetected.emit()
            if self._on_active:
                try:
                    self._on_active()
                except Exception:
                    pass  # 忽略回调异常
    
    def _check_idle(self):
        """检查是否空闲"""
        if not self._running:
            return
        
        now = time.time()
        idle_time_ms = (now - self._last_activity_time) * 1000
        
        # 如果空闲时间超过阈值且之前不是空闲状态
        if idle_time_ms >= self._idle_timeout_ms and not self._is_idle:
            self._is_idle = True
            self.idleDetected.emit()
            if self._on_idle:
                try:
                    self._on_idle()
                except Exception:
                    pass  # 忽略回调异常
    
    def get_idle_time_ms(self) -> float:
        """获取当前空闲时间（毫秒）"""
        return (time.time() - self._last_activity_time) * 1000
    
    def cleanup(self):
        """清理资源"""
        self.stop()
        if self._check_timer:
            self._check_timer.deleteLater()
            self._check_timer = None


class CacheReleaseManager:
    """缓存释放管理器
    
    管理空闲时自动释放缓存的逻辑。
    """
    
    def __init__(self, idle_timeout_ms: int = IdleDetector.DEFAULT_IDLE_TIMEOUT_MS):
        """初始化缓存释放管理器
        
        Args:
            idle_timeout_ms: 空闲超时时间（毫秒）
        """
        self._idle_detector = IdleDetector(
            idle_timeout_ms=idle_timeout_ms,
            on_idle=self._on_idle,
            on_active=self._on_active
        )
        
        # 需要释放的缓存对象列表
        self._cache_objects: list = []
        
        # 缓存释放回调
        self._release_callbacks: list = []
    
    def register_cache(self, cache_obj, release_method: str = "clear"):
        """注册需要管理的缓存对象
        
        Args:
            cache_obj: 缓存对象
            release_method: 释放方法名称
        """
        self._cache_objects.append((cache_obj, release_method))
    
    def register_release_callback(self, callback: Callable[[], None]):
        """注册缓存释放回调
        
        Args:
            callback: 释放回调函数
        """
        self._release_callbacks.append(callback)
    
    def start(self):
        """启动缓存释放管理"""
        self._idle_detector.start()
    
    def stop(self):
        """停止缓存释放管理"""
        self._idle_detector.stop()
    
    def record_activity(self):
        """记录用户活动"""
        self._idle_detector.record_activity()
    
    def _on_idle(self):
        """空闲时释放缓存"""
        # 释放注册的缓存对象
        for cache_obj, release_method in self._cache_objects:
            if cache_obj is not None and hasattr(cache_obj, release_method):
                try:
                    getattr(cache_obj, release_method)()
                except Exception:
                    pass
        
        # 调用释放回调
        for callback in self._release_callbacks:
            try:
                callback()
            except Exception:
                pass
    
    def _on_active(self):
        """恢复活动时的处理（可选）"""
        pass
    
    @property
    def is_idle(self) -> bool:
        """是否处于空闲状态"""
        return self._idle_detector.is_idle
    
    def cleanup(self):
        """清理资源"""
        self._idle_detector.cleanup()
        self._cache_objects.clear()
        self._release_callbacks.clear()
