"""延迟加载管理器

Feature: performance-ui-optimization
Requirements: 1.3, 1.4

提供非必要模块的延迟加载功能，减少应用启动时间。
模块仅在首次访问时加载，并缓存实例以供后续使用。
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import importlib
import time


@dataclass
class LazyModule:
    """延迟加载模块定义
    
    Attributes:
        module_path: 模块路径 e.g. "screenshot_tool.services.ocr_manager"
        class_name: 类名 e.g. "OCRManager"
        instance: 已加载的实例（None 表示未加载）
        load_time_ms: 加载耗时（毫秒）
    """
    module_path: str
    class_name: str
    instance: Optional[Any] = field(default=None, repr=False)
    load_time_ms: float = 0.0


class LazyLoaderManager:
    """延迟加载管理器
    
    Feature: performance-ui-optimization
    Requirements: 1.3, 1.4
    
    单例模式，管理非必要模块的延迟加载。
    
    Usage:
        # 获取模块实例（首次访问时加载）
        ocr = LazyLoaderManager.instance().get("ocr_manager")
        
        # 检查模块是否已加载
        if LazyLoaderManager.instance().is_loaded("ocr_manager"):
            ...
        
        # 卸载模块释放内存
        LazyLoaderManager.instance().unload("ocr_manager")
    """
    
    _instance: Optional['LazyLoaderManager'] = None
    
    # 非必要模块列表（启动时不加载）
    # 这些模块仅在用户实际使用相关功能时才加载
    LAZY_MODULES: Dict[str, LazyModule] = {
        # OCR 引擎 - 仅在用户触发 OCR 时加载
        "ocr_manager": LazyModule(
            "screenshot_tool.services.ocr_manager", 
            "OCRManager"
        ),
        # 翻译服务 - 仅在用户触发翻译时加载
        "translation_service": LazyModule(
            "screenshot_tool.services.translation_service", 
            "TranslationService"
        ),
        # Anki 连接器 - 仅在用户创建 Anki 卡片时加载
        "anki_connector": LazyModule(
            "screenshot_tool.services.anki_connector", 
            "AnkiConnector"
        ),
        # Markdown 转换器 - 仅在用户使用网页转 MD 功能时加载
        "markdown_converter": LazyModule(
            "screenshot_tool.services.markdown_converter", 
            "MarkdownConverter"
        ),
        # 规章服务 - 仅在用户使用规章查询功能时加载
        "regulation_service": LazyModule(
            "screenshot_tool.services.regulation_service", 
            "RegulationService"
        ),
        # 录屏服务 - 仅在用户使用录屏功能时加载
        "screen_recorder": LazyModule(
            "screenshot_tool.services.screen_recorder", 
            "ScreenRecorder"
        ),
        # 贴图管理器 - 仅在用户使用贴图功能时加载
        "ding_manager": LazyModule(
            "screenshot_tool.ui.ding_window", 
            "DingManager"
        ),
    }
    
    def __init__(self):
        """初始化延迟加载管理器
        
        注意：不要直接调用此构造函数，使用 instance() 类方法获取单例。
        """
        # 创建 LAZY_MODULES 的副本，避免类级别状态污染
        self._modules: Dict[str, LazyModule] = {
            key: LazyModule(
                module_path=mod.module_path,
                class_name=mod.class_name,
                instance=None,
                load_time_ms=0.0
            )
            for key, mod in self.LAZY_MODULES.items()
        }
    
    @classmethod
    def instance(cls) -> 'LazyLoaderManager':
        """获取单例实例
        
        Returns:
            LazyLoaderManager 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        cls._instance = None
    
    def get(self, module_key: str, *args, **kwargs) -> Any:
        """获取延迟加载的模块实例
        
        首次调用时加载模块并创建实例，后续调用返回缓存的实例。
        
        Args:
            module_key: 模块键名（如 "ocr_manager"）
            *args: 传递给构造函数的位置参数
            **kwargs: 传递给构造函数的关键字参数
            
        Returns:
            模块实例
            
        Raises:
            KeyError: 如果 module_key 不在 LAZY_MODULES 中
            ImportError: 如果模块导入失败
            AttributeError: 如果类名不存在
        """
        if module_key not in self._modules:
            raise KeyError(f"Unknown lazy module: {module_key}")
        
        lazy_mod = self._modules[module_key]
        
        if lazy_mod.instance is None:
            start = time.perf_counter()
            
            # 动态导入模块
            module = importlib.import_module(lazy_mod.module_path)
            
            # 获取类
            cls = getattr(module, lazy_mod.class_name)
            
            # 创建实例
            lazy_mod.instance = cls(*args, **kwargs)
            
            # 记录加载时间
            lazy_mod.load_time_ms = (time.perf_counter() - start) * 1000
        
        return lazy_mod.instance
    
    def is_loaded(self, module_key: str) -> bool:
        """检查模块是否已加载
        
        Args:
            module_key: 模块键名
            
        Returns:
            True 如果模块已加载，False 如果未加载或键名不存在
        """
        if module_key not in self._modules:
            return False
        return self._modules[module_key].instance is not None
    
    def unload(self, module_key: str) -> None:
        """卸载模块释放内存
        
        将模块实例设为 None，允许垃圾回收器回收内存。
        下次调用 get() 时会重新加载模块。
        
        Args:
            module_key: 模块键名
        """
        if module_key in self._modules:
            self._modules[module_key].instance = None
            self._modules[module_key].load_time_ms = 0.0
    
    def unload_all(self) -> None:
        """卸载所有已加载的模块"""
        for module_key in self._modules:
            self.unload(module_key)
    
    def get_load_time(self, module_key: str) -> Optional[float]:
        """获取模块加载耗时
        
        Args:
            module_key: 模块键名
            
        Returns:
            加载耗时（毫秒），如果模块未加载或键名不存在则返回 None
        """
        if module_key not in self._modules:
            return None
        lazy_mod = self._modules[module_key]
        if lazy_mod.instance is None:
            return None
        return lazy_mod.load_time_ms
    
    def get_loaded_modules(self) -> list:
        """获取所有已加载的模块键名列表
        
        Returns:
            已加载模块的键名列表
        """
        return [
            key for key, mod in self._modules.items() 
            if mod.instance is not None
        ]
    
    def get_module_info(self, module_key: str) -> Optional[Dict[str, Any]]:
        """获取模块信息
        
        Args:
            module_key: 模块键名
            
        Returns:
            包含模块信息的字典，如果键名不存在则返回 None
        """
        if module_key not in self._modules:
            return None
        
        lazy_mod = self._modules[module_key]
        return {
            "module_path": lazy_mod.module_path,
            "class_name": lazy_mod.class_name,
            "is_loaded": lazy_mod.instance is not None,
            "load_time_ms": lazy_mod.load_time_ms if lazy_mod.instance else None,
        }
    
    @property
    def available_modules(self) -> list:
        """获取所有可用的模块键名列表"""
        return list(self._modules.keys())


def safe_lazy_load(module_key: str, *args, fallback=None, **kwargs) -> Any:
    """安全的延迟加载，失败时返回 fallback
    
    Feature: performance-ui-optimization
    Requirements: 1.3
    
    Args:
        module_key: 模块键名
        *args: 传递给构造函数的位置参数
        fallback: 加载失败时返回的默认值
        **kwargs: 传递给构造函数的关键字参数
        
    Returns:
        模块实例，或加载失败时返回 fallback
    """
    try:
        return LazyLoaderManager.instance().get(module_key, *args, **kwargs)
    except Exception as e:
        # 尝试记录错误日志
        try:
            from screenshot_tool.core.error_logger import get_error_logger
            logger = get_error_logger()
            if logger:
                logger.log_error(f"Failed to load module {module_key}: {e}")
        except Exception:
            # 如果日志记录也失败，静默忽略
            pass
        return fallback
