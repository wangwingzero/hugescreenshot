# =====================================================
# =============== 推理后端选择器 ===============
# =====================================================

"""
推理后端选择器 - OpenVINO Only

从 v1.9.0 开始，统一使用 OpenVINO 作为唯一的 OCR 推理后端。
实测表明 OpenVINO 在 AMD CPU 上也能正常工作且速度更快。

Requirements: 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.3, 4.4
"""

import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from screenshot_tool.core.async_logger import async_debug_log


def backend_log(message: str):
    """后端选择器日志"""
    async_debug_log(message, "BACKEND")


class BackendType(Enum):
    """推理后端类型 - 仅保留 OpenVINO"""
    OPENVINO = "openvino"


@dataclass
class BackendInfo:
    """后端信息 - 简化版"""
    backend_type: BackendType
    cpu_vendor: str
    openvino_available: bool
    openvino_version: Optional[str] = None
    # OpenVINO 优化相关字段
    performance_hint: Optional[str] = None
    cache_enabled: bool = False
    cache_dir: Optional[str] = None
    cpu_pinning_enabled: bool = False
    inference_threads: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "backend_type": self.backend_type.value,
            "cpu_vendor": self.cpu_vendor,
            "openvino_available": self.openvino_available,
            "openvino_version": self.openvino_version,
            "performance_hint": self.performance_hint,
            "cache_enabled": self.cache_enabled,
            "cache_dir": self.cache_dir,
            "cpu_pinning_enabled": self.cpu_pinning_enabled,
            "inference_threads": self.inference_threads,
        }


# 缓存检测结果
_cached_cpu_vendor: Optional[str] = None
_cached_openvino_available: Optional[bool] = None


class BackendSelector:
    """推理后端选择器 - OpenVINO Only"""
    
    @staticmethod
    def detect_cpu_vendor() -> str:
        """检测 CPU 厂商（仅用于日志）"""
        global _cached_cpu_vendor
        
        if _cached_cpu_vendor is not None:
            return _cached_cpu_vendor
        
        vendor = "Unknown"
        
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["wmic", "cpu", "get", "name"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                cpu_name = result.stdout.lower()
                if "intel" in cpu_name:
                    vendor = "Intel"
                elif "amd" in cpu_name:
                    vendor = "AMD"
                elif "arm" in cpu_name or "qualcomm" in cpu_name:
                    vendor = "ARM"
            else:
                processor = platform.processor().lower()
                if "intel" in processor:
                    vendor = "Intel"
                elif "amd" in processor:
                    vendor = "AMD"
                elif "arm" in processor:
                    vendor = "ARM"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, FileNotFoundError) as e:
            backend_log(f"CPU 检测失败: {e}")
        except Exception as e:
            backend_log(f"CPU 检测异常: {type(e).__name__}: {e}")
        
        _cached_cpu_vendor = vendor
        backend_log(f"检测到 CPU 厂商: {vendor}")
        return vendor
    
    @staticmethod
    def is_openvino_available() -> bool:
        """检查 OpenVINO 是否可用"""
        global _cached_openvino_available
        if _cached_openvino_available is not None:
            return _cached_openvino_available
        
        try:
            import importlib.util
            spec = importlib.util.find_spec("rapidocr_openvino")
            _cached_openvino_available = spec is not None
            if _cached_openvino_available:
                backend_log("OpenVINO 后端可用")
            else:
                backend_log("OpenVINO 后端不可用")
        except Exception as e:
            _cached_openvino_available = False
            backend_log(f"OpenVINO 检测失败: {e}")
        return _cached_openvino_available
    
    @staticmethod
    def get_openvino_version() -> Optional[str]:
        """获取 OpenVINO 版本"""
        try:
            import rapidocr_openvino
            return getattr(rapidocr_openvino, "__version__", "unknown")
        except Exception:
            return None
    
    @staticmethod
    def select_best_backend() -> BackendType:
        """选择后端 - 始终返回 OpenVINO"""
        backend_log("选择 OpenVINO 后端")
        return BackendType.OPENVINO
    
    @staticmethod
    def get_backend_info() -> BackendInfo:
        """获取后端详细信息"""
        cpu_vendor = BackendSelector.detect_cpu_vendor()
        openvino_ok = BackendSelector.is_openvino_available()
        openvino_version = BackendSelector.get_openvino_version() if openvino_ok else None
        
        # 获取 OpenVINO 配置信息
        performance_hint = None
        cache_enabled = False
        cache_dir = None
        cpu_pinning_enabled = False
        inference_threads = None
        
        if openvino_ok:
            try:
                from screenshot_tool.services.openvino_optimizer import (
                    get_global_config, OpenVINOConfig
                )
                config = get_global_config()
                if config is None:
                    config = OpenVINOConfig()
                performance_hint = config.performance_hint
                cache_enabled = config.enable_model_cache
                resolved_dir = config.get_resolved_cache_dir()
                cache_dir = str(resolved_dir) if resolved_dir else None
                cpu_pinning_enabled = config.enable_cpu_pinning
                inference_threads = config.inference_threads
            except ImportError:
                backend_log("OpenVINO 优化器模块未找到")
            except Exception as e:
                backend_log(f"获取 OpenVINO 配置失败: {type(e).__name__}: {e}")
        
        return BackendInfo(
            backend_type=BackendType.OPENVINO,
            cpu_vendor=cpu_vendor,
            openvino_available=openvino_ok,
            openvino_version=openvino_version,
            performance_hint=performance_hint,
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
            cpu_pinning_enabled=cpu_pinning_enabled,
            inference_threads=inference_threads,
        )
    
    @staticmethod
    def clear_cache():
        """清除缓存（用于测试）"""
        global _cached_cpu_vendor, _cached_openvino_available
        _cached_cpu_vendor = None
        _cached_openvino_available = None


def get_backend_display_string(info: BackendInfo = None) -> str:
    """获取后端显示字符串（用于 UI 显示）
    
    Args:
        info: BackendInfo 实例，None 则自动获取
    
    Returns:
        用户友好的后端描述字符串
    
    Examples:
        - "OpenVINO (LATENCY)"
        - "OpenVINO"
    """
    if info is None:
        info = BackendSelector.get_backend_info()
    
    if info.performance_hint:
        return f"OpenVINO ({info.performance_hint})"
    return "OpenVINO"
