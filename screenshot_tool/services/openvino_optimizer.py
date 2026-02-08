# =====================================================
# =============== OpenVINO 优化器 ===============
# =====================================================

"""
OpenVINO 优化器 - 提供 OpenVINO 运行时优化配置

功能：
1. 内存优化：限制 CPU_RUNTIME_CACHE_CAPACITY 解决动态形状缓存导致的内存泄漏
2. Performance Hints：设置 LATENCY 模式优化单张图片识别响应时间
3. 模型缓存：缓存编译后的模型到磁盘，加速后续启动

参考：
- https://github.com/openvinotoolkit/openvino/issues/11939
- https://github.com/openvinotoolkit/openvino/issues/24891
- https://docs.openvino.ai/latest/openvino_docs_OV_UG_Performance_Hints.html
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 尝试导入 OpenVINO
_openvino_available = False
_Core = None

try:
    # OpenVINO 2026.0 移除了 openvino.runtime 命名空间
    # 优先使用新的导入方式
    try:
        from openvino import Core as _OVCore
    except ImportError:
        from openvino.runtime import Core as _OVCore
    _Core = _OVCore
    _openvino_available = True
except ImportError:
    pass

# 全局 Core 实例（单例）
_global_core: Optional[object] = None
_core_lock = threading.Lock()

# 标记是否已经 patch 过
_patch_applied = False
_patch_lock = threading.Lock()

# 默认缓存容量（设为较小值以限制内存增长）
# 0 = 完全禁用缓存（可能影响性能）
# 5-20 = 推荐值，平衡性能和内存
DEFAULT_CACHE_CAPACITY = 5

# 默认性能提示模式
DEFAULT_PERFORMANCE_HINT = "LATENCY"

# 默认模型缓存目录
DEFAULT_MODEL_CACHE_DIR = "~/.screenshot_tool/openvino_cache"

# CPU 核心绑定（防止核心切换导致缓存失效）
DEFAULT_ENABLE_CPU_PINNING = True

# 推理线程数（None = 自动，让 OpenVINO 根据 Performance Hints 决定）
DEFAULT_INFERENCE_THREADS = None


@dataclass
class OpenVINOConfig:
    """OpenVINO 优化配置
    
    Attributes:
        cache_capacity: CPU 运行时缓存容量（0=禁用，5-20=推荐）
        performance_hint: 性能提示模式（LATENCY/THROUGHPUT）
        model_cache_dir: 模型缓存目录路径
        enable_model_cache: 是否启用模型缓存
        enable_cpu_pinning: 是否启用 CPU 核心绑定（防止核心切换导致缓存失效）
        inference_threads: 推理线程数（None=自动）
    """
    cache_capacity: int = DEFAULT_CACHE_CAPACITY
    performance_hint: str = DEFAULT_PERFORMANCE_HINT
    model_cache_dir: Optional[str] = None
    enable_model_cache: bool = True
    enable_cpu_pinning: bool = DEFAULT_ENABLE_CPU_PINNING
    inference_threads: Optional[int] = DEFAULT_INFERENCE_THREADS
    
    def __post_init__(self):
        """初始化后处理：从环境变量读取覆盖值"""
        # 环境变量覆盖 cache_capacity
        env_capacity = os.environ.get("OPENVINO_CPU_CACHE_CAPACITY", "")
        if env_capacity:
            try:
                capacity = int(env_capacity)
                # 验证范围：0-100 是合理范围
                if 0 <= capacity <= 100:
                    self.cache_capacity = capacity
            except ValueError:
                pass
        
        # 确保 cache_capacity 在有效范围内
        self.cache_capacity = max(0, min(self.cache_capacity, 100))
        
        # 环境变量覆盖 model_cache_dir
        env_cache_dir = os.environ.get("SCREENSHOT_OCR_CACHE_DIR", "")
        if env_cache_dir:
            self.model_cache_dir = env_cache_dir
        elif self.model_cache_dir is None:
            self.model_cache_dir = DEFAULT_MODEL_CACHE_DIR
        
        # 环境变量覆盖 performance_hint
        env_hint = os.environ.get("SCREENSHOT_OCR_PERFORMANCE_HINT", "")
        if env_hint.upper() in ("LATENCY", "THROUGHPUT"):
            self.performance_hint = env_hint.upper()
        
        # 环境变量覆盖 cpu_pinning
        env_pinning = os.environ.get("SCREENSHOT_OCR_CPU_PINNING", "")
        if env_pinning.lower() in ("true", "1", "yes"):
            self.enable_cpu_pinning = True
        elif env_pinning.lower() in ("false", "0", "no"):
            self.enable_cpu_pinning = False
        
        # 环境变量覆盖 inference_threads
        env_threads = os.environ.get("SCREENSHOT_OCR_INFERENCE_THREADS", "")
        if env_threads:
            try:
                threads = int(env_threads)
                if threads > 0:
                    self.inference_threads = threads
            except ValueError:
                pass
    
    def get_resolved_cache_dir(self) -> Optional[Path]:
        """获取解析后的缓存目录路径（展开 ~ 等）"""
        if not self.enable_model_cache or not self.model_cache_dir:
            return None
        return Path(self.model_cache_dir).expanduser()


# 全局配置实例
_global_config: Optional[OpenVINOConfig] = None


def get_optimized_core(config: OpenVINOConfig = None) -> object:
    """获取优化后的 OpenVINO Core 实例（单例模式）
    
    Args:
        config: OpenVINO 配置，None 使用默认配置
    
    Returns:
        OpenVINO Core 实例
    
    Raises:
        ImportError: 如果 OpenVINO 未安装
    """
    global _global_core, _global_config
    
    if not _openvino_available:
        raise ImportError("OpenVINO 未安装，请运行: pip install openvino")
    
    with _core_lock:
        if _global_core is None:
            if config is None:
                config = OpenVINOConfig()
            _global_config = config
            _global_core = _create_optimized_core(config)
        return _global_core


def _create_optimized_core(config: OpenVINOConfig) -> object:
    """创建优化后的 OpenVINO Core 实例
    
    Args:
        config: OpenVINO 配置
    
    Returns:
        配置好的 Core 实例
    """
    core = _Core()
    
    _log("=" * 50)
    _log("OpenVINO Core 初始化开始")
    _log("目标设备: CPU")
    
    # 1. 设置 CPU 运行时缓存容量（解决动态形状内存泄漏）
    try:
        core.set_property("CPU", {"CPU_RUNTIME_CACHE_CAPACITY": str(config.cache_capacity)})
        _log(f"CPU_RUNTIME_CACHE_CAPACITY = {config.cache_capacity}")
    except Exception as e:
        _log(f"设置 CPU_RUNTIME_CACHE_CAPACITY 失败: {e}")
    
    # 2. 设置 Performance Hints
    try:
        core.set_property("CPU", {"PERFORMANCE_HINT": config.performance_hint})
        _log(f"PERFORMANCE_HINT = {config.performance_hint}")
    except Exception as e:
        _log(f"设置 PERFORMANCE_HINT 失败: {e}")
    
    # 3. 设置 CPU 核心绑定（防止核心切换导致缓存失效）
    if config.enable_cpu_pinning:
        try:
            # OpenVINO 2024+ 支持 ENABLE_CPU_PINNING
            core.set_property("CPU", {"ENABLE_CPU_PINNING": "YES"})
            _log("ENABLE_CPU_PINNING = YES")
        except Exception as e:
            _log(f"设置 ENABLE_CPU_PINNING 失败（可能版本不支持）: {e}")
    
    # 4. 设置推理线程数
    try:
        if config.inference_threads is not None:
            # 使用配置指定的线程数
            core.set_property("CPU", {"INFERENCE_NUM_THREADS": str(config.inference_threads)})
            _log(f"INFERENCE_NUM_THREADS = {config.inference_threads}")
        else:
            # 检查环境变量 OMP_NUM_THREADS
            omp_threads = os.environ.get("OMP_NUM_THREADS")
            if omp_threads:
                core.set_property("CPU", {"INFERENCE_NUM_THREADS": omp_threads})
                _log(f"INFERENCE_NUM_THREADS = {omp_threads} (from OMP_NUM_THREADS)")
            # 否则让 OpenVINO 根据 Performance Hints 自动决定
    except Exception as e:
        _log(f"设置 INFERENCE_NUM_THREADS 失败: {e}")
    
    # 5. 设置模型缓存目录
    if config.enable_model_cache:
        cache_dir = config.get_resolved_cache_dir()
        if cache_dir:
            try:
                # 自动创建缓存目录
                cache_dir.mkdir(parents=True, exist_ok=True)
                # OpenVINO 2024+ 需要使用字典形式设置全局属性
                core.set_property({"CACHE_DIR": str(cache_dir)})
                _log(f"CACHE_DIR = {cache_dir}")
            except PermissionError as e:
                _log(f"创建缓存目录失败（权限不足）: {e}")
            except Exception as e:
                _log(f"设置 CACHE_DIR 失败: {e}")
    
    _log("OpenVINO Core 初始化完成")
    _log("=" * 50)
    
    return core


def get_global_config() -> Optional[OpenVINOConfig]:
    """获取当前全局配置"""
    return _global_config


def reset_core():
    """重置全局 Core 实例（用于测试或强制重新初始化）"""
    global _global_core, _global_config
    with _core_lock:
        _global_core = None
        _global_config = None
        _log("OpenVINO Core 实例已重置")


def is_openvino_available() -> bool:
    """检查 OpenVINO 是否可用"""
    return _openvino_available


def _log(message: str):
    """日志输出"""
    try:
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log(message, "OPENVINO")
    except ImportError:
        print(f"[OPENVINO] {message}")


# ========== Monkey Patch RapidOCR OpenVINO ==========

def patch_rapidocr_openvino(config: OpenVINOConfig = None) -> bool:
    """
    Monkey patch rapidocr_openvino 使用优化后的 Core 实例
    
    这个函数会替换 rapidocr_openvino.utils.OpenVINOInferSession 的 __init__ 方法，
    使其使用我们优化后的 Core 实例（带有 Performance Hints、模型缓存等优化）
    
    Args:
        config: OpenVINO 配置，None 使用默认配置
    
    调用时机：在导入 rapidocr_openvino 之前调用
    
    Returns:
        bool: True 表示 patch 成功或已经 patch 过，False 表示失败
    
    Note:
        此函数是线程安全的，多次调用只会执行一次 patch
        首次调用时的配置会被保存，后续调用的配置会被忽略
    """
    global _patch_applied, _global_config
    
    # 快速检查（无锁）
    if _patch_applied:
        return True
    
    if not _openvino_available:
        _log("OpenVINO 不可用，跳过 patch")
        return False
    
    with _patch_lock:
        # 双重检查（有锁）
        if _patch_applied:
            return True
        
        try:
            import rapidocr_openvino.utils as ov_utils
            
            # 检查是否已经被 patch（防止其他方式的重复 patch）
            if hasattr(ov_utils.OpenVINOInferSession.__init__, '_optimized_patch'):
                _patch_applied = True
                return True
            
            # 保存原始的 __init__ 方法（用于可能的回滚）
            original_init = ov_utils.OpenVINOInferSession.__init__
            
            # 保存配置到全局变量，确保闭包使用正确的配置
            if config is None:
                config = OpenVINOConfig()
            _global_config = config
            
            def patched_init(self, model_config):
                """优化后的 OpenVINOInferSession.__init__
                
                使用全局优化的 Core 实例，包含：
                - CPU_RUNTIME_CACHE_CAPACITY 限制
                - PERFORMANCE_HINT: LATENCY
                - 模型缓存目录
                """
                from pathlib import Path
                
                try:
                    # 使用全局配置（通过 get_global_config 获取，确保一致性）
                    current_config = get_global_config() or OpenVINOConfig()
                    
                    # 使用优化后的全局 Core 实例
                    ie = get_optimized_core(current_config)
                    
                    root_dir = Path(ov_utils.__file__).resolve().parent
                    model_path = str(root_dir / model_config['model_path'])
                    model_config['model_path'] = model_path
                    self._verify_model(model_path)
                    
                    model_onnx = ie.read_model(model_path)
                    
                    # 始终使用 CPU 设备
                    compile_model = ie.compile_model(model=model_onnx, device_name="CPU")
                    _log("模型编译成功 (设备: CPU)")
                    
                    self.session = compile_model.create_infer_request()
                except Exception as e:
                    _log(f"OpenVINOInferSession 初始化失败: {e}")
                    raise
            
            # 标记为已 patch
            patched_init._optimized_patch = True
            patched_init._original_init = original_init
            
            # 应用 patch
            ov_utils.OpenVINOInferSession.__init__ = patched_init
            _patch_applied = True
            _log("已 patch rapidocr_openvino 使用优化后的 Core 实例")
            return True
            
        except ImportError:
            _log("rapidocr_openvino 未安装，跳过 patch")
            return False
        except Exception as e:
            _log(f"patch rapidocr_openvino 失败: {e}")
            return False


def is_patch_applied() -> bool:
    """检查是否已经应用了 patch"""
    return _patch_applied


def reset_patch():
    """重置 patch 状态（仅用于测试）
    
    Warning:
        此函数仅用于测试目的，生产环境中不应调用
        重置后需要重新调用 patch_rapidocr_openvino
    """
    global _patch_applied
    with _patch_lock:
        _patch_applied = False
        _log("Patch 状态已重置（仅用于测试）")
