"""内存管理器

Feature: performance-ui-optimization
Requirements: 4.3, 4.4

提供内存管理功能：
- 空闲 GC 定时器（5 分钟）
- OCR 引擎空闲释放（60 秒）
- 内存压力检测

基于 Property 3: Memory Management:
- 空闲状态: 内存使用 ≤ 150MB
- 活动状态: 内存使用 ≤ 300MB
- 关闭截图后: 5 秒内释放内存
- 空闲 5 分钟后: 触发垃圾回收
"""

from typing import Optional, Callable, List
from dataclasses import dataclass, field
import gc
import time

# 尝试导入 psutil，如果不可用则使用 fallback
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

# 尝试导入 PySide6 QTimer，如果不可用则使用 fallback
try:
    from PySide6.QtCore import QTimer, QObject, Signal
    PYSIDE6_AVAILABLE = True
except ImportError:
    QTimer = None
    QObject = object
    Signal = None
    PYSIDE6_AVAILABLE = False


@dataclass
class MemoryConfig:
    """内存管理配置
    
    Attributes:
        idle_gc_interval_seconds: 空闲 GC 间隔（秒），默认 300 秒（5 分钟）
        ocr_idle_timeout_seconds: OCR 引擎空闲超时（秒），默认 60 秒
        memory_check_interval_seconds: 内存检查间隔（秒），默认 30 秒
        idle_memory_limit_mb: 空闲状态内存限制（MB），默认 150MB
        active_memory_limit_mb: 活动状态内存限制（MB），默认 300MB
        memory_pressure_threshold_mb: 内存压力阈值（MB），默认 250MB
    """
    idle_gc_interval_seconds: int = 300  # 5 分钟
    ocr_idle_timeout_seconds: int = 60   # 60 秒
    memory_check_interval_seconds: int = 30  # 30 秒
    idle_memory_limit_mb: int = 150
    active_memory_limit_mb: int = 300
    memory_pressure_threshold_mb: int = 250


@dataclass
class MemoryStats:
    """内存统计信息
    
    Attributes:
        rss_mb: 常驻内存大小（MB）
        vms_mb: 虚拟内存大小（MB）
        percent: 内存使用百分比
        timestamp: 统计时间戳
    """
    rss_mb: float
    vms_mb: float
    percent: float
    timestamp: float = field(default_factory=time.time)


class MemoryManager(QObject if PYSIDE6_AVAILABLE else object):
    """内存管理器
    
    Feature: performance-ui-optimization
    Requirements: 4.3, 4.4
    
    单例模式，管理应用程序内存：
    - 定期检查内存使用情况
    - 空闲时触发垃圾回收
    - OCR 引擎空闲释放
    - 内存压力检测和降级
    
    Usage:
        # 获取单例实例
        manager = MemoryManager.instance()
        
        # 启动内存管理
        manager.start()
        
        # 记录 OCR 活动
        manager.record_ocr_activity()
        
        # 检查内存压力
        if manager.is_memory_pressure():
            # 执行降级策略
            pass
        
        # 停止内存管理
        manager.stop()
    """
    
    _instance: Optional['MemoryManager'] = None
    
    # Qt 信号（仅在 PySide6 可用时）
    if PYSIDE6_AVAILABLE:
        memory_pressure_detected = Signal()  # 内存压力检测信号
        gc_triggered = Signal()              # GC 触发信号
        ocr_released = Signal()              # OCR 引擎释放信号
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        """初始化内存管理器
        
        Args:
            config: 内存管理配置，如果为 None 则使用默认配置
            
        注意：不要直接调用此构造函数，使用 instance() 类方法获取单例。
        """
        if PYSIDE6_AVAILABLE:
            super().__init__()
        
        self._config = config or MemoryConfig()
        self._started = False
        
        # 时间戳记录
        self._last_gc_time: float = 0.0
        self._last_ocr_activity_time: float = 0.0
        self._last_user_activity_time: float = time.time()
        
        # 定时器（仅在 PySide6 可用时）
        self._gc_timer: Optional[QTimer] = None
        self._ocr_timer: Optional[QTimer] = None
        self._memory_check_timer: Optional[QTimer] = None
        
        # 回调函数列表
        self._memory_pressure_callbacks: List[Callable[[], None]] = []
        self._gc_callbacks: List[Callable[[], None]] = []
        self._ocr_release_callbacks: List[Callable[[], None]] = []
        
        # 内存统计历史
        self._memory_history: List[MemoryStats] = []
        self._max_history_size = 100
    
    @classmethod
    def instance(cls, config: Optional[MemoryConfig] = None) -> 'MemoryManager':
        """获取单例实例
        
        Args:
            config: 内存管理配置（仅在首次创建时使用）
            
        Returns:
            MemoryManager 单例实例
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance.stop()
        cls._instance = None
    
    @property
    def config(self) -> MemoryConfig:
        """获取当前配置"""
        return self._config
    
    @property
    def is_started(self) -> bool:
        """检查是否已启动"""
        return self._started
    
    def start(self) -> None:
        """启动内存管理
        
        启动所有定时器：
        - 空闲 GC 定时器
        - OCR 空闲释放定时器
        - 内存检查定时器
        """
        if self._started:
            return
        
        if not PYSIDE6_AVAILABLE:
            # 没有 PySide6 时，只记录启动状态
            self._started = True
            return
        
        # 创建并启动 GC 定时器
        self._gc_timer = QTimer()
        self._gc_timer.timeout.connect(self._on_gc_timer)
        self._gc_timer.start(self._config.idle_gc_interval_seconds * 1000)
        
        # 创建并启动 OCR 空闲释放定时器
        self._ocr_timer = QTimer()
        self._ocr_timer.timeout.connect(self._on_ocr_timer)
        self._ocr_timer.start(self._config.ocr_idle_timeout_seconds * 1000)
        
        # 创建并启动内存检查定时器
        self._memory_check_timer = QTimer()
        self._memory_check_timer.timeout.connect(self._on_memory_check_timer)
        self._memory_check_timer.start(self._config.memory_check_interval_seconds * 1000)
        
        self._started = True
        self._last_gc_time = time.time()
    
    def stop(self) -> None:
        """停止内存管理
        
        停止所有定时器并清理资源。
        """
        if not self._started:
            return
        
        if PYSIDE6_AVAILABLE:
            if self._gc_timer:
                self._gc_timer.stop()
                self._gc_timer = None
            
            if self._ocr_timer:
                self._ocr_timer.stop()
                self._ocr_timer = None
            
            if self._memory_check_timer:
                self._memory_check_timer.stop()
                self._memory_check_timer = None
        
        self._started = False
    
    def record_user_activity(self) -> None:
        """记录用户活动
        
        调用此方法表示用户有活动，重置空闲计时器。
        """
        self._last_user_activity_time = time.time()
    
    def record_ocr_activity(self) -> None:
        """记录 OCR 活动
        
        调用此方法表示 OCR 引擎被使用，重置 OCR 空闲计时器。
        """
        self._last_ocr_activity_time = time.time()
    
    def get_idle_seconds(self) -> float:
        """获取用户空闲时间（秒）
        
        Returns:
            自上次用户活动以来的秒数
        """
        return time.time() - self._last_user_activity_time
    
    def get_ocr_idle_seconds(self) -> float:
        """获取 OCR 空闲时间（秒）
        
        Returns:
            自上次 OCR 活动以来的秒数，如果从未使用过则返回无穷大
        """
        if self._last_ocr_activity_time == 0:
            return float('inf')
        return time.time() - self._last_ocr_activity_time
    
    def get_memory_stats(self) -> Optional[MemoryStats]:
        """获取当前内存统计信息
        
        Returns:
            MemoryStats 对象，如果 psutil 不可用则返回 None
        """
        if not PSUTIL_AVAILABLE:
            return None
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            stats = MemoryStats(
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                percent=process.memory_percent(),
            )
            
            # 添加到历史记录
            self._memory_history.append(stats)
            if len(self._memory_history) > self._max_history_size:
                self._memory_history.pop(0)
            
            return stats
        except Exception:
            return None
    
    def get_memory_mb(self) -> float:
        """获取当前内存使用量（MB）
        
        Returns:
            RSS 内存使用量（MB），如果无法获取则返回 0
        """
        stats = self.get_memory_stats()
        return stats.rss_mb if stats else 0.0
    
    def is_memory_pressure(self) -> bool:
        """检查是否存在内存压力
        
        当内存使用超过 memory_pressure_threshold_mb（默认 250MB）时返回 True。
        
        Returns:
            True 如果存在内存压力，False 否则
        """
        memory_mb = self.get_memory_mb()
        return memory_mb > self._config.memory_pressure_threshold_mb
    
    def is_memory_critical(self) -> bool:
        """检查内存是否处于临界状态
        
        当内存使用超过 active_memory_limit_mb（默认 300MB）时返回 True。
        
        Returns:
            True 如果内存临界，False 否则
        """
        memory_mb = self.get_memory_mb()
        return memory_mb > self._config.active_memory_limit_mb
    
    def trigger_gc(self, force: bool = False) -> int:
        """触发垃圾回收
        
        Args:
            force: 是否强制执行（忽略空闲时间检查）
            
        Returns:
            回收的对象数量
        """
        if not force:
            # 检查是否满足空闲条件
            idle_seconds = self.get_idle_seconds()
            if idle_seconds < self._config.idle_gc_interval_seconds:
                return 0
        
        # 执行垃圾回收
        collected = gc.collect()
        self._last_gc_time = time.time()
        
        # 触发回调
        for callback in self._gc_callbacks:
            try:
                callback()
            except Exception:
                pass
        
        # 发送信号
        if PYSIDE6_AVAILABLE and hasattr(self, 'gc_triggered'):
            self.gc_triggered.emit()
        
        return collected
    
    def release_ocr_engine(self) -> bool:
        """释放 OCR 引擎
        
        如果 OCR 引擎空闲超过配置的超时时间，则释放它。
        
        Returns:
            True 如果成功释放，False 否则
        """
        ocr_idle = self.get_ocr_idle_seconds()
        if ocr_idle < self._config.ocr_idle_timeout_seconds:
            return False
        
        # 尝试通过 LazyLoaderManager 卸载 OCR 模块
        try:
            from screenshot_tool.core.lazy_loader import LazyLoaderManager
            lazy = LazyLoaderManager.instance()
            if lazy.is_loaded("ocr_manager"):
                lazy.unload("ocr_manager")
                
                # 触发回调
                for callback in self._ocr_release_callbacks:
                    try:
                        callback()
                    except Exception:
                        pass
                
                # 发送信号
                if PYSIDE6_AVAILABLE and hasattr(self, 'ocr_released'):
                    self.ocr_released.emit()
                
                return True
        except Exception:
            pass
        
        return False
    
    def release_memory(self) -> None:
        """释放内存
        
        执行完整的内存释放流程：
        1. 释放 OCR 引擎（如果空闲）
        2. 卸载其他非必要模块
        3. 触发垃圾回收
        """
        # 释放 OCR 引擎
        self.release_ocr_engine()
        
        # 尝试卸载其他非必要模块
        try:
            from screenshot_tool.core.lazy_loader import LazyLoaderManager
            lazy = LazyLoaderManager.instance()
            
            # 卸载不常用的模块
            for module_key in ["translation_service", "anki_connector", 
                               "regulation_service", "markdown_converter"]:
                if lazy.is_loaded(module_key):
                    lazy.unload(module_key)
        except Exception:
            pass
        
        # 强制垃圾回收
        self.trigger_gc(force=True)
    
    def add_memory_pressure_callback(self, callback: Callable[[], None]) -> None:
        """添加内存压力回调
        
        Args:
            callback: 当检测到内存压力时调用的函数
        """
        if callback not in self._memory_pressure_callbacks:
            self._memory_pressure_callbacks.append(callback)
    
    def remove_memory_pressure_callback(self, callback: Callable[[], None]) -> None:
        """移除内存压力回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._memory_pressure_callbacks:
            self._memory_pressure_callbacks.remove(callback)
    
    def add_gc_callback(self, callback: Callable[[], None]) -> None:
        """添加 GC 回调
        
        Args:
            callback: 当触发 GC 时调用的函数
        """
        if callback not in self._gc_callbacks:
            self._gc_callbacks.append(callback)
    
    def remove_gc_callback(self, callback: Callable[[], None]) -> None:
        """移除 GC 回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._gc_callbacks:
            self._gc_callbacks.remove(callback)
    
    def add_ocr_release_callback(self, callback: Callable[[], None]) -> None:
        """添加 OCR 释放回调
        
        Args:
            callback: 当 OCR 引擎被释放时调用的函数
        """
        if callback not in self._ocr_release_callbacks:
            self._ocr_release_callbacks.append(callback)
    
    def remove_ocr_release_callback(self, callback: Callable[[], None]) -> None:
        """移除 OCR 释放回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._ocr_release_callbacks:
            self._ocr_release_callbacks.remove(callback)
    
    def get_memory_history(self) -> List[MemoryStats]:
        """获取内存统计历史
        
        Returns:
            MemoryStats 列表，最多 100 条记录
        """
        return self._memory_history.copy()
    
    def _on_gc_timer(self) -> None:
        """GC 定时器回调
        
        检查是否满足空闲条件，如果满足则触发 GC。
        """
        idle_seconds = self.get_idle_seconds()
        if idle_seconds >= self._config.idle_gc_interval_seconds:
            self.trigger_gc(force=True)
    
    def _on_ocr_timer(self) -> None:
        """OCR 空闲释放定时器回调
        
        检查 OCR 引擎是否空闲，如果空闲则释放。
        """
        self.release_ocr_engine()
    
    def _on_memory_check_timer(self) -> None:
        """内存检查定时器回调
        
        检查内存使用情况，如果存在压力则触发回调。
        """
        if self.is_memory_pressure():
            # 触发内存压力回调
            for callback in self._memory_pressure_callbacks:
                try:
                    callback()
                except Exception:
                    pass
            
            # 发送信号
            if PYSIDE6_AVAILABLE and hasattr(self, 'memory_pressure_detected'):
                self.memory_pressure_detected.emit()
            
            # 如果内存临界，执行紧急释放
            if self.is_memory_critical():
                self.release_memory()


def get_memory_manager(config: Optional[MemoryConfig] = None) -> MemoryManager:
    """获取内存管理器单例的便捷函数
    
    Args:
        config: 内存管理配置（仅在首次创建时使用）
        
    Returns:
        MemoryManager 单例实例
    """
    return MemoryManager.instance(config)
