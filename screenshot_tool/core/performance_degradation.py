"""性能降级处理器

Feature: performance-ui-optimization
Requirements: 4.1, 4.2

当系统资源不足时，自动降级以保持响应性。

降级策略：
1. 禁用动画 - 减少 CPU/GPU 负载
2. 卸载非必要模块 - 释放内存
3. 强制 GC - 回收未使用的内存

恢复策略：
- 当内存压力解除后，自动恢复动画
- 模块按需重新加载

基于 Property 3: Memory Management:
- 空闲状态: 内存使用 ≤ 150MB
- 活动状态: 内存使用 ≤ 300MB
- 内存压力阈值: 250MB
"""

from typing import Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum, auto
import gc
import time

# 尝试导入 psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False


class DegradationLevel(Enum):
    """降级级别
    
    Attributes:
        NONE: 无降级，正常运行
        LIGHT: 轻度降级，禁用动画
        MODERATE: 中度降级，卸载部分模块
        SEVERE: 严重降级，卸载所有非必要模块并强制 GC
    """
    NONE = auto()
    LIGHT = auto()
    MODERATE = auto()
    SEVERE = auto()


@dataclass
class DegradationConfig:
    """降级配置
    
    Attributes:
        light_threshold_mb: 轻度降级阈值（MB），默认 200MB
        moderate_threshold_mb: 中度降级阈值（MB），默认 250MB
        severe_threshold_mb: 严重降级阈值（MB），默认 280MB
        recovery_threshold_mb: 恢复阈值（MB），默认 180MB
        check_interval_seconds: 检查间隔（秒），默认 10 秒
    """
    light_threshold_mb: float = 200.0
    moderate_threshold_mb: float = 250.0
    severe_threshold_mb: float = 280.0
    recovery_threshold_mb: float = 180.0
    check_interval_seconds: float = 10.0


@dataclass
class DegradationState:
    """降级状态
    
    Attributes:
        level: 当前降级级别
        animations_disabled: 动画是否已禁用
        modules_unloaded: 已卸载的模块列表
        last_check_time: 上次检查时间
        last_memory_mb: 上次检查的内存使用量
    """
    level: DegradationLevel = DegradationLevel.NONE
    animations_disabled: bool = False
    modules_unloaded: List[str] = field(default_factory=list)
    last_check_time: float = 0.0
    last_memory_mb: float = 0.0


class PerformanceDegradation:
    """性能降级处理器
    
    Feature: performance-ui-optimization
    Requirements: 4.1, 4.2
    
    当系统资源不足时，自动降级以保持响应性。
    支持多级降级和自动恢复。
    
    Usage:
        # 获取单例实例
        degradation = PerformanceDegradation.instance()
        
        # 检查并应用降级
        degradation.check_and_apply()
        
        # 手动检查内存压力
        if degradation.check_memory_pressure():
            # 内存压力存在
            pass
        
        # 注册到 MemoryManager
        from screenshot_tool.core.memory_manager import MemoryManager
        memory_manager = MemoryManager.instance()
        memory_manager.add_memory_pressure_callback(degradation.on_memory_pressure)
    """
    
    _instance: Optional['PerformanceDegradation'] = None
    
    # 非必要模块列表（按优先级排序，优先卸载不常用的）
    NON_ESSENTIAL_MODULES = [
        "regulation_service",    # 规章服务 - 很少使用
        "markdown_converter",    # Markdown 转换器 - 偶尔使用
        "anki_connector",        # Anki 连接器 - 偶尔使用
        "translation_service",   # 翻译服务 - 较常使用
        "screen_recorder",       # 录屏服务 - 偶尔使用
    ]
    
    # 中度降级时卸载的模块
    MODERATE_UNLOAD_MODULES = [
        "regulation_service",
        "markdown_converter",
        "anki_connector",
    ]
    
    # 严重降级时额外卸载的模块
    SEVERE_UNLOAD_MODULES = [
        "translation_service",
        "screen_recorder",
        "ocr_manager",
    ]
    
    def __init__(self, config: Optional[DegradationConfig] = None):
        """初始化性能降级处理器
        
        Args:
            config: 降级配置，如果为 None 则使用默认配置
            
        注意：不要直接调用此构造函数，使用 instance() 类方法获取单例。
        """
        self._config = config or DegradationConfig()
        self._state = DegradationState()
        
        # 原始动画常量值（用于恢复）
        self._original_animation_values: Optional[dict] = None
        
        # 回调函数
        self._degradation_callbacks: List[Callable[[DegradationLevel], None]] = []
        self._recovery_callbacks: List[Callable[[], None]] = []
    
    @classmethod
    def instance(cls, config: Optional[DegradationConfig] = None) -> 'PerformanceDegradation':
        """获取单例实例
        
        Args:
            config: 降级配置（仅在首次创建时使用）
            
        Returns:
            PerformanceDegradation 单例实例
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            # 恢复动画设置
            cls._instance._restore_animations()
        cls._instance = None
    
    @property
    def config(self) -> DegradationConfig:
        """获取当前配置"""
        return self._config
    
    @property
    def state(self) -> DegradationState:
        """获取当前状态"""
        return self._state
    
    @property
    def current_level(self) -> DegradationLevel:
        """获取当前降级级别"""
        return self._state.level
    
    @property
    def is_degraded(self) -> bool:
        """检查是否处于降级状态"""
        return self._state.level != DegradationLevel.NONE
    
    @staticmethod
    def get_memory_mb() -> float:
        """获取当前进程内存使用量（MB）
        
        Returns:
            RSS 内存使用量（MB），如果无法获取则返回 0
        """
        if not PSUTIL_AVAILABLE:
            return 0.0
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def check_memory_pressure(self) -> bool:
        """检查内存压力
        
        当内存使用超过轻度降级阈值时返回 True。
        
        Returns:
            True 如果存在内存压力，False 否则
        """
        memory_mb = self.get_memory_mb()
        self._state.last_memory_mb = memory_mb
        self._state.last_check_time = time.time()
        
        return memory_mb > self._config.light_threshold_mb
    
    def determine_level(self, memory_mb: Optional[float] = None) -> DegradationLevel:
        """根据内存使用量确定降级级别
        
        Args:
            memory_mb: 内存使用量（MB），如果为 None 则自动获取
            
        Returns:
            应该应用的降级级别
        """
        if memory_mb is None:
            memory_mb = self.get_memory_mb()
        
        if memory_mb >= self._config.severe_threshold_mb:
            return DegradationLevel.SEVERE
        elif memory_mb >= self._config.moderate_threshold_mb:
            return DegradationLevel.MODERATE
        elif memory_mb >= self._config.light_threshold_mb:
            return DegradationLevel.LIGHT
        elif memory_mb <= self._config.recovery_threshold_mb:
            return DegradationLevel.NONE
        else:
            # 在恢复阈值和轻度阈值之间，保持当前级别
            return self._state.level
    
    def check_and_apply(self) -> DegradationLevel:
        """检查内存状态并应用适当的降级策略
        
        Returns:
            应用后的降级级别
        """
        memory_mb = self.get_memory_mb()
        self._state.last_memory_mb = memory_mb
        self._state.last_check_time = time.time()
        
        target_level = self.determine_level(memory_mb)
        
        if target_level != self._state.level:
            if target_level == DegradationLevel.NONE:
                self._recover()
            else:
                self._apply_degradation(target_level)
        
        return self._state.level
    
    def _apply_degradation(self, level: DegradationLevel) -> None:
        """应用降级策略
        
        Args:
            level: 目标降级级别
        """
        old_level = self._state.level
        self._state.level = level
        
        # 根据级别应用不同的降级策略
        if level == DegradationLevel.LIGHT:
            self._disable_animations()
        
        elif level == DegradationLevel.MODERATE:
            self._disable_animations()
            self._unload_modules(self.MODERATE_UNLOAD_MODULES)
            gc.collect()
        
        elif level == DegradationLevel.SEVERE:
            self._disable_animations()
            self._unload_modules(self.MODERATE_UNLOAD_MODULES + self.SEVERE_UNLOAD_MODULES)
            # 强制完整 GC
            gc.collect(generation=2)
        
        # 触发回调
        for callback in self._degradation_callbacks:
            try:
                callback(level)
            except Exception:
                pass
    
    def _recover(self) -> None:
        """恢复正常状态"""
        self._state.level = DegradationLevel.NONE
        
        # 恢复动画
        self._restore_animations()
        
        # 清空已卸载模块列表（模块会按需重新加载）
        self._state.modules_unloaded.clear()
        
        # 触发恢复回调
        for callback in self._recovery_callbacks:
            try:
                callback()
            except Exception:
                pass
    
    def _disable_animations(self) -> None:
        """禁用动画
        
        将 AnimationConstants 的时长值设为 0。
        """
        if self._state.animations_disabled:
            return
        
        try:
            from screenshot_tool.ui.styles import AnimationConstants
            
            # 保存原始值
            if self._original_animation_values is None:
                self._original_animation_values = {
                    'INSTANT': AnimationConstants.INSTANT,
                    'FAST': AnimationConstants.FAST,
                    'NORMAL': AnimationConstants.NORMAL,
                    'SLOW': AnimationConstants.SLOW,
                    'SUCCESS': AnimationConstants.SUCCESS,
                }
            
            # 设置为 0
            AnimationConstants.INSTANT = 0
            AnimationConstants.FAST = 0
            AnimationConstants.NORMAL = 0
            AnimationConstants.SLOW = 0
            AnimationConstants.SUCCESS = 0
            
            self._state.animations_disabled = True
            
        except ImportError:
            # styles 模块不可用，忽略
            pass
    
    def _restore_animations(self) -> None:
        """恢复动画设置"""
        if not self._state.animations_disabled:
            return
        
        if self._original_animation_values is None:
            return
        
        try:
            from screenshot_tool.ui.styles import AnimationConstants
            
            # 恢复原始值
            AnimationConstants.INSTANT = self._original_animation_values['INSTANT']
            AnimationConstants.FAST = self._original_animation_values['FAST']
            AnimationConstants.NORMAL = self._original_animation_values['NORMAL']
            AnimationConstants.SLOW = self._original_animation_values['SLOW']
            AnimationConstants.SUCCESS = self._original_animation_values['SUCCESS']
            
            self._state.animations_disabled = False
            
        except ImportError:
            pass
    
    def _unload_modules(self, module_keys: List[str]) -> None:
        """卸载指定模块
        
        Args:
            module_keys: 要卸载的模块键名列表
        """
        try:
            from screenshot_tool.core.lazy_loader import LazyLoaderManager
            lazy = LazyLoaderManager.instance()
            
            for key in module_keys:
                if lazy.is_loaded(key) and key not in self._state.modules_unloaded:
                    lazy.unload(key)
                    self._state.modules_unloaded.append(key)
                    
        except ImportError:
            # lazy_loader 模块不可用，忽略
            pass
    
    def apply_degradation(self) -> None:
        """应用降级策略（兼容设计文档中的静态方法签名）
        
        这是一个便捷方法，自动检测内存状态并应用适当的降级。
        """
        self.check_and_apply()
    
    def force_degradation(self, level: DegradationLevel) -> None:
        """强制应用指定的降级级别
        
        Args:
            level: 要应用的降级级别
        """
        if level == DegradationLevel.NONE:
            self._recover()
        else:
            self._apply_degradation(level)
    
    def on_memory_pressure(self) -> None:
        """内存压力回调
        
        用于注册到 MemoryManager 的内存压力回调。
        """
        self.check_and_apply()
    
    def add_degradation_callback(self, callback: Callable[[DegradationLevel], None]) -> None:
        """添加降级回调
        
        Args:
            callback: 当降级发生时调用的函数，参数为降级级别
        """
        if callback not in self._degradation_callbacks:
            self._degradation_callbacks.append(callback)
    
    def remove_degradation_callback(self, callback: Callable[[DegradationLevel], None]) -> None:
        """移除降级回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._degradation_callbacks:
            self._degradation_callbacks.remove(callback)
    
    def add_recovery_callback(self, callback: Callable[[], None]) -> None:
        """添加恢复回调
        
        Args:
            callback: 当恢复正常时调用的函数
        """
        if callback not in self._recovery_callbacks:
            self._recovery_callbacks.append(callback)
    
    def remove_recovery_callback(self, callback: Callable[[], None]) -> None:
        """移除恢复回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._recovery_callbacks:
            self._recovery_callbacks.remove(callback)
    
    def get_status_info(self) -> dict:
        """获取当前状态信息
        
        Returns:
            包含状态信息的字典
        """
        return {
            "level": self._state.level.name,
            "is_degraded": self.is_degraded,
            "animations_disabled": self._state.animations_disabled,
            "modules_unloaded": self._state.modules_unloaded.copy(),
            "last_memory_mb": self._state.last_memory_mb,
            "last_check_time": self._state.last_check_time,
            "config": {
                "light_threshold_mb": self._config.light_threshold_mb,
                "moderate_threshold_mb": self._config.moderate_threshold_mb,
                "severe_threshold_mb": self._config.severe_threshold_mb,
                "recovery_threshold_mb": self._config.recovery_threshold_mb,
            }
        }


def get_performance_degradation(config: Optional[DegradationConfig] = None) -> PerformanceDegradation:
    """获取性能降级处理器单例的便捷函数
    
    Args:
        config: 降级配置（仅在首次创建时使用）
        
    Returns:
        PerformanceDegradation 单例实例
    """
    return PerformanceDegradation.instance(config)


def setup_degradation_with_memory_manager() -> PerformanceDegradation:
    """设置性能降级并与 MemoryManager 集成
    
    创建 PerformanceDegradation 实例并注册到 MemoryManager 的内存压力回调。
    
    Returns:
        配置好的 PerformanceDegradation 实例
    """
    degradation = PerformanceDegradation.instance()
    
    try:
        from screenshot_tool.core.memory_manager import MemoryManager
        memory_manager = MemoryManager.instance()
        memory_manager.add_memory_pressure_callback(degradation.on_memory_pressure)
    except ImportError:
        # MemoryManager 不可用，忽略
        pass
    
    return degradation
