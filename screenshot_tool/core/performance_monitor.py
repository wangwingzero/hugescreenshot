"""性能监控器

Feature: performance-ui-optimization, extreme-performance-optimization
Requirements: 1.1, 2.1, 2.3, 3.1, 4.1, 4.2, 9.1

提供性能测量和监控功能，用于验证和优化应用性能。
包括内存使用监控和验证功能。
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import deque

# 尝试导入 psutil，如果不可用则使用 fallback
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False


@dataclass
class PerformanceMetric:
    """性能指标
    
    Attributes:
        name: 指标名称
        duration_ms: 耗时（毫秒）
        timestamp: 记录时间戳
    """
    name: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


class PerformanceMonitor:
    """性能监控器
    
    Feature: performance-ui-optimization
    Requirements: 1.1, 2.1, 2.3, 3.1, 9.1
    
    提供代码块执行时间测量、统计分析等功能。
    
    Usage:
        # 测量代码块执行时间
        with PerformanceMonitor.measure("overlay_show"):
            overlay.show()
        
        # 获取统计数据
        avg = PerformanceMonitor.get_average("overlay_show")
        last = PerformanceMonitor.get_last("overlay_show")
        
        # 检查性能阈值
        if PerformanceMonitor.exceeds_threshold("overlay_show", 200):
            print("Warning: overlay_show exceeded 200ms threshold")
    """
    
    _metrics: Dict[str, List[PerformanceMetric]] = {}
    _enabled: bool = True
    _max_samples: int = 100  # 每个指标最多保留的样本数
    
    @classmethod
    def enable(cls) -> None:
        """启用性能监控"""
        cls._enabled = True
    
    @classmethod
    def disable(cls) -> None:
        """禁用性能监控
        
        禁用后，measure() 上下文管理器仍可使用，但不会记录任何数据。
        """
        cls._enabled = False
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查性能监控是否启用"""
        return cls._enabled
    
    @classmethod
    def set_max_samples(cls, max_samples: int) -> None:
        """设置每个指标最多保留的样本数
        
        Args:
            max_samples: 最大样本数，必须 > 0
        """
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        cls._max_samples = max_samples
    
    @classmethod
    @contextmanager
    def measure(cls, name: str):
        """测量代码块执行时间
        
        Args:
            name: 指标名称
            
        Usage:
            with PerformanceMonitor.measure("overlay_show"):
                overlay.show()
        """
        if not cls._enabled:
            yield
            return
        
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = (time.perf_counter() - start) * 1000  # 转换为毫秒
            metric = PerformanceMetric(name, duration)
            
            if name not in cls._metrics:
                cls._metrics[name] = []
            
            cls._metrics[name].append(metric)
            
            # 限制样本数量，避免内存无限增长
            if len(cls._metrics[name]) > cls._max_samples:
                cls._metrics[name] = cls._metrics[name][-cls._max_samples:]
    
    @classmethod
    def record(cls, name: str, duration_ms: float) -> None:
        """手动记录一个性能指标
        
        Args:
            name: 指标名称
            duration_ms: 耗时（毫秒）
        """
        if not cls._enabled:
            return
        
        metric = PerformanceMetric(name, duration_ms)
        
        if name not in cls._metrics:
            cls._metrics[name] = []
        
        cls._metrics[name].append(metric)
        
        # 限制样本数量
        if len(cls._metrics[name]) > cls._max_samples:
            cls._metrics[name] = cls._metrics[name][-cls._max_samples:]
    
    @classmethod
    def get_average(cls, name: str) -> Optional[float]:
        """获取指标的平均耗时
        
        Args:
            name: 指标名称
            
        Returns:
            平均耗时（毫秒），如果没有数据则返回 None
        """
        if name not in cls._metrics or not cls._metrics[name]:
            return None
        durations = [m.duration_ms for m in cls._metrics[name]]
        return sum(durations) / len(durations)
    
    @classmethod
    def get_last(cls, name: str) -> Optional[float]:
        """获取指标的最近一次耗时
        
        Args:
            name: 指标名称
            
        Returns:
            最近一次耗时（毫秒），如果没有数据则返回 None
        """
        if name not in cls._metrics or not cls._metrics[name]:
            return None
        return cls._metrics[name][-1].duration_ms
    
    @classmethod
    def get_min(cls, name: str) -> Optional[float]:
        """获取指标的最小耗时
        
        Args:
            name: 指标名称
            
        Returns:
            最小耗时（毫秒），如果没有数据则返回 None
        """
        if name not in cls._metrics or not cls._metrics[name]:
            return None
        return min(m.duration_ms for m in cls._metrics[name])
    
    @classmethod
    def get_max(cls, name: str) -> Optional[float]:
        """获取指标的最大耗时
        
        Args:
            name: 指标名称
            
        Returns:
            最大耗时（毫秒），如果没有数据则返回 None
        """
        if name not in cls._metrics or not cls._metrics[name]:
            return None
        return max(m.duration_ms for m in cls._metrics[name])
    
    @classmethod
    def get_count(cls, name: str) -> int:
        """获取指标的样本数量
        
        Args:
            name: 指标名称
            
        Returns:
            样本数量
        """
        if name not in cls._metrics:
            return 0
        return len(cls._metrics[name])
    
    @classmethod
    def get_metrics(cls, name: str) -> List[PerformanceMetric]:
        """获取指标的所有样本
        
        Args:
            name: 指标名称
            
        Returns:
            样本列表的副本
        """
        if name not in cls._metrics:
            return []
        return cls._metrics[name].copy()
    
    @classmethod
    def get_all_names(cls) -> List[str]:
        """获取所有已记录的指标名称
        
        Returns:
            指标名称列表
        """
        return list(cls._metrics.keys())
    
    @classmethod
    def get_all_metrics(cls) -> Dict[str, List[PerformanceMetric]]:
        """获取所有指标数据
        
        Returns:
            所有指标数据的副本
        """
        return {name: metrics.copy() for name, metrics in cls._metrics.items()}
    
    @classmethod
    def get_summary(cls, name: str) -> Optional[Dict[str, float]]:
        """获取指标的统计摘要
        
        Args:
            name: 指标名称
            
        Returns:
            包含 count, average, min, max, last 的字典，如果没有数据则返回 None
        """
        if name not in cls._metrics or not cls._metrics[name]:
            return None
        
        durations = [m.duration_ms for m in cls._metrics[name]]
        return {
            "count": len(durations),
            "average": sum(durations) / len(durations),
            "min": min(durations),
            "max": max(durations),
            "last": durations[-1],
        }
    
    @classmethod
    def exceeds_threshold(cls, name: str, threshold_ms: float) -> bool:
        """检查最近一次测量是否超过阈值
        
        Args:
            name: 指标名称
            threshold_ms: 阈值（毫秒）
            
        Returns:
            如果最近一次测量超过阈值返回 True，否则返回 False
        """
        last = cls.get_last(name)
        if last is None:
            return False
        return last > threshold_ms
    
    @classmethod
    def average_exceeds_threshold(cls, name: str, threshold_ms: float) -> bool:
        """检查平均值是否超过阈值
        
        Args:
            name: 指标名称
            threshold_ms: 阈值（毫秒）
            
        Returns:
            如果平均值超过阈值返回 True，否则返回 False
        """
        avg = cls.get_average(name)
        if avg is None:
            return False
        return avg > threshold_ms
    
    @classmethod
    def clear(cls, name: Optional[str] = None) -> None:
        """清除指标数据
        
        Args:
            name: 指标名称，如果为 None 则清除所有指标
        """
        if name is None:
            cls._metrics.clear()
        elif name in cls._metrics:
            del cls._metrics[name]
    
    @classmethod
    def reset(cls) -> None:
        """重置监控器到初始状态
        
        清除所有数据并恢复默认设置。
        """
        cls._metrics.clear()
        cls._enabled = True
        cls._max_samples = 100
    
    @classmethod
    def format_report(cls) -> str:
        """生成性能报告
        
        Returns:
            格式化的性能报告字符串
        """
        if not cls._metrics:
            return "No performance metrics recorded."
        
        lines = ["Performance Report", "=" * 50]
        
        for name in sorted(cls._metrics.keys()):
            summary = cls.get_summary(name)
            if summary:
                lines.append(f"\n{name}:")
                lines.append(f"  Count:   {summary['count']}")
                lines.append(f"  Average: {summary['average']:.2f} ms")
                lines.append(f"  Min:     {summary['min']:.2f} ms")
                lines.append(f"  Max:     {summary['max']:.2f} ms")
                lines.append(f"  Last:    {summary['last']:.2f} ms")
        
        return "\n".join(lines)
    
    # ========== 内存监控方法 ==========
    # Feature: extreme-performance-optimization
    # Requirements: 4.1, 4.2
    
    # 内存限制常量（MB）
    IDLE_MEMORY_LIMIT_MB = 100  # 空闲状态内存限制
    SCREENSHOT_MEMORY_LIMIT_MB = 200  # 截图时内存限制
    
    @classmethod
    def get_memory_mb(cls) -> float:
        """获取当前进程内存使用量（MB）
        
        Feature: extreme-performance-optimization
        Requirements: 4.1, 4.2
        
        Returns:
            RSS 内存使用量（MB），如果 psutil 不可用则返回 0
        """
        if not PSUTIL_AVAILABLE:
            return 0.0
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / 1024 / 1024
        except Exception:
            return 0.0
    
    @classmethod
    def get_memory_stats(cls) -> Optional[Dict[str, float]]:
        """获取详细的内存统计信息
        
        Feature: extreme-performance-optimization
        Requirements: 4.1, 4.2
        
        Returns:
            包含 rss_mb, vms_mb, percent 的字典，如果 psutil 不可用则返回 None
        """
        if not PSUTIL_AVAILABLE:
            return None
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
            }
        except Exception:
            return None
    
    @classmethod
    def verify_idle_memory(cls) -> Tuple[bool, float]:
        """验证空闲状态内存是否在限制内
        
        Feature: extreme-performance-optimization
        Requirements: 4.1
        
        验证空闲内存 < 100MB
        
        Returns:
            (是否通过验证, 当前内存使用量MB)
        """
        memory_mb = cls.get_memory_mb()
        is_valid = memory_mb < cls.IDLE_MEMORY_LIMIT_MB
        
        # 记录验证结果
        cls.record("memory_idle_mb", memory_mb)
        
        return (is_valid, memory_mb)
    
    @classmethod
    def verify_screenshot_memory(cls) -> Tuple[bool, float]:
        """验证截图时内存是否在限制内
        
        Feature: extreme-performance-optimization
        Requirements: 4.2
        
        验证截图时内存 < 200MB
        
        Returns:
            (是否通过验证, 当前内存使用量MB)
        """
        memory_mb = cls.get_memory_mb()
        is_valid = memory_mb < cls.SCREENSHOT_MEMORY_LIMIT_MB
        
        # 记录验证结果
        cls.record("memory_screenshot_mb", memory_mb)
        
        return (is_valid, memory_mb)
    
    @classmethod
    def is_memory_under_limit(cls, limit_mb: float) -> bool:
        """检查内存是否在指定限制内
        
        Args:
            limit_mb: 内存限制（MB）
            
        Returns:
            True 如果内存在限制内，False 否则
        """
        memory_mb = cls.get_memory_mb()
        return memory_mb < limit_mb
    
    @classmethod
    @contextmanager
    def measure_memory(cls, name: str):
        """测量代码块执行前后的内存变化
        
        Feature: extreme-performance-optimization
        Requirements: 4.1, 4.2
        
        Args:
            name: 指标名称
            
        Usage:
            with PerformanceMonitor.measure_memory("screenshot_capture"):
                # 执行截图操作
                pass
            
            # 获取内存变化
            delta = PerformanceMonitor.get_last("screenshot_capture_memory_delta_mb")
        """
        if not cls._enabled or not PSUTIL_AVAILABLE:
            yield
            return
        
        start_memory = cls.get_memory_mb()
        try:
            yield
        finally:
            end_memory = cls.get_memory_mb()
            delta = end_memory - start_memory
            
            # 记录内存变化
            cls.record(f"{name}_memory_start_mb", start_memory)
            cls.record(f"{name}_memory_end_mb", end_memory)
            cls.record(f"{name}_memory_delta_mb", delta)
    
    @classmethod
    def format_memory_report(cls) -> str:
        """生成内存使用报告
        
        Feature: extreme-performance-optimization
        Requirements: 4.1, 4.2
        
        Returns:
            格式化的内存报告字符串
        """
        if not PSUTIL_AVAILABLE:
            return "Memory monitoring not available (psutil not installed)"
        
        stats = cls.get_memory_stats()
        if not stats:
            return "Unable to get memory statistics"
        
        lines = [
            "Memory Usage Report",
            "=" * 50,
            f"RSS Memory:     {stats['rss_mb']:.2f} MB",
            f"VMS Memory:     {stats['vms_mb']:.2f} MB",
            f"Memory Percent: {stats['percent']:.2f}%",
            "",
            "Limits:",
            f"  Idle Limit:       {cls.IDLE_MEMORY_LIMIT_MB} MB",
            f"  Screenshot Limit: {cls.SCREENSHOT_MEMORY_LIMIT_MB} MB",
            "",
            "Status:",
        ]
        
        idle_ok, idle_mem = cls.verify_idle_memory()
        screenshot_ok, screenshot_mem = cls.verify_screenshot_memory()
        
        lines.append(f"  Idle Memory:      {'✓ PASS' if idle_ok else '✗ FAIL'} ({idle_mem:.2f} MB < {cls.IDLE_MEMORY_LIMIT_MB} MB)")
        lines.append(f"  Screenshot Memory: {'✓ PASS' if screenshot_ok else '✗ FAIL'} ({screenshot_mem:.2f} MB < {cls.SCREENSHOT_MEMORY_LIMIT_MB} MB)")
        
        return "\n".join(lines)
