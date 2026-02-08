"""资源缓存

Feature: performance-ui-optimization
Requirements: 1.5

提供异步资源加载和缓存功能，减少启动时间和 UI 阻塞。
图标和其他资源在后台线程加载，加载完成后通过信号通知。
"""

from typing import Dict, List, Optional, Callable, Any
from PySide6.QtCore import QThread, Signal, QObject, QMutex, QMutexLocker
from PySide6.QtGui import QIcon, QPixmap
import os


class ResourceLoaderWorker(QThread):
    """资源加载工作线程
    
    Feature: performance-ui-optimization
    Requirements: 1.5
    
    在后台线程中加载图标资源，避免阻塞主线程。
    加载完成后通过 icon_loaded 信号通知。
    
    Usage:
        worker = ResourceLoaderWorker(["save", "copy", "paste"], "/path/to/app")
        worker.icon_loaded.connect(on_icon_loaded)
        worker.all_loaded.connect(on_all_loaded)
        worker.start()
    """
    
    # 信号：单个图标加载完成 (icon_name, icon)
    icon_loaded = Signal(str, QIcon)
    
    # 信号：所有图标加载完成
    all_loaded = Signal()
    
    # 信号：加载进度 (loaded_count, total_count)
    progress = Signal(int, int)
    
    # 信号：加载错误 (icon_name, error_message)
    load_error = Signal(str, str)
    
    def __init__(
        self, 
        icon_names: List[str], 
        base_path: str,
        icon_subdir: str = "resources/icons",
        icon_extension: str = ".svg",
        parent: Optional[QObject] = None
    ):
        """初始化资源加载工作线程
        
        Args:
            icon_names: 要加载的图标名称列表
            base_path: 应用程序基础路径
            icon_subdir: 图标子目录（相对于 base_path）
            icon_extension: 图标文件扩展名
            parent: 父对象
        """
        super().__init__(parent)
        self._icon_names = icon_names.copy()
        self._base_path = base_path
        self._icon_subdir = icon_subdir
        self._icon_extension = icon_extension
        self._should_stop = False
    
    def stop(self) -> None:
        """请求停止加载"""
        self._should_stop = True
    
    def run(self) -> None:
        """执行图标加载
        
        在后台线程中依次加载所有图标，每加载完成一个就发送信号。
        """
        total = len(self._icon_names)
        loaded = 0
        
        for name in self._icon_names:
            if self._should_stop:
                break
            
            # 构建图标路径
            icon_path = os.path.join(
                self._base_path, 
                self._icon_subdir, 
                f"{name}{self._icon_extension}"
            )
            
            try:
                if os.path.exists(icon_path):
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.icon_loaded.emit(name, icon)
                    else:
                        self.load_error.emit(name, f"Failed to load icon: {icon_path}")
                else:
                    self.load_error.emit(name, f"Icon file not found: {icon_path}")
            except Exception as e:
                self.load_error.emit(name, str(e))
            
            loaded += 1
            self.progress.emit(loaded, total)
        
        if not self._should_stop:
            self.all_loaded.emit()


class ResourceCache:
    """资源缓存
    
    Feature: performance-ui-optimization
    Requirements: 1.5
    
    提供图标和其他资源的缓存管理，支持异步预加载。
    使用类方法实现，无需实例化。
    
    Usage:
        # 预加载图标（异步）
        ResourceCache.preload_icons(["save", "copy", "paste"], "/path/to/app")
        
        # 获取缓存的图标
        icon = ResourceCache.get_icon("save")
        if icon:
            button.setIcon(icon)
        
        # 检查图标是否已加载
        if ResourceCache.is_loaded("save"):
            ...
        
        # 设置加载完成回调
        ResourceCache.set_on_icon_loaded(lambda name, icon: print(f"Loaded: {name}"))
    """
    
    # 图标缓存
    _icons: Dict[str, QIcon] = {}
    
    # 像素图缓存
    _pixmaps: Dict[str, QPixmap] = {}
    
    # 当前加载器
    _loader: Optional[ResourceLoaderWorker] = None
    
    # 加载完成回调
    _on_icon_loaded: Optional[Callable[[str, QIcon], None]] = None
    _on_all_loaded: Optional[Callable[[], None]] = None
    _on_load_error: Optional[Callable[[str, str], None]] = None
    
    # 线程安全锁
    _mutex = QMutex()
    
    # 统计信息
    _load_count: int = 0
    _error_count: int = 0
    
    @classmethod
    def get_icon(cls, name: str) -> Optional[QIcon]:
        """获取缓存的图标
        
        Args:
            name: 图标名称
            
        Returns:
            缓存的 QIcon，如果未找到则返回 None
        """
        with QMutexLocker(cls._mutex):
            return cls._icons.get(name)
    
    @classmethod
    def set_icon(cls, name: str, icon: QIcon) -> None:
        """设置图标缓存
        
        Args:
            name: 图标名称
            icon: QIcon 对象
        """
        with QMutexLocker(cls._mutex):
            cls._icons[name] = icon
            cls._load_count += 1
        
        # 调用回调（在锁外部）
        if cls._on_icon_loaded:
            try:
                cls._on_icon_loaded(name, icon)
            except Exception:
                pass
    
    @classmethod
    def get_pixmap(cls, name: str) -> Optional[QPixmap]:
        """获取缓存的像素图
        
        Args:
            name: 像素图名称
            
        Returns:
            缓存的 QPixmap，如果未找到则返回 None
        """
        with QMutexLocker(cls._mutex):
            return cls._pixmaps.get(name)
    
    @classmethod
    def set_pixmap(cls, name: str, pixmap: QPixmap) -> None:
        """设置像素图缓存
        
        Args:
            name: 像素图名称
            pixmap: QPixmap 对象
        """
        with QMutexLocker(cls._mutex):
            cls._pixmaps[name] = pixmap
    
    @classmethod
    def is_loaded(cls, name: str) -> bool:
        """检查图标是否已加载
        
        Args:
            name: 图标名称
            
        Returns:
            True 如果图标已加载，否则 False
        """
        with QMutexLocker(cls._mutex):
            return name in cls._icons
    
    @classmethod
    def is_pixmap_loaded(cls, name: str) -> bool:
        """检查像素图是否已加载
        
        Args:
            name: 像素图名称
            
        Returns:
            True 如果像素图已加载，否则 False
        """
        with QMutexLocker(cls._mutex):
            return name in cls._pixmaps
    
    @classmethod
    def get_all_icons(cls) -> Dict[str, QIcon]:
        """获取所有缓存的图标
        
        Returns:
            图标字典的副本
        """
        with QMutexLocker(cls._mutex):
            return cls._icons.copy()
    
    @classmethod
    def get_all_pixmaps(cls) -> Dict[str, QPixmap]:
        """获取所有缓存的像素图
        
        Returns:
            像素图字典的副本
        """
        with QMutexLocker(cls._mutex):
            return cls._pixmaps.copy()
    
    @classmethod
    def get_loaded_icon_names(cls) -> List[str]:
        """获取所有已加载的图标名称
        
        Returns:
            图标名称列表
        """
        with QMutexLocker(cls._mutex):
            return list(cls._icons.keys())
    
    @classmethod
    def get_icon_count(cls) -> int:
        """获取已缓存的图标数量
        
        Returns:
            图标数量
        """
        with QMutexLocker(cls._mutex):
            return len(cls._icons)
    
    @classmethod
    def get_pixmap_count(cls) -> int:
        """获取已缓存的像素图数量
        
        Returns:
            像素图数量
        """
        with QMutexLocker(cls._mutex):
            return len(cls._pixmaps)
    
    @classmethod
    def preload_icons(
        cls, 
        icon_names: List[str], 
        base_path: str,
        icon_subdir: str = "resources/icons",
        icon_extension: str = ".svg"
    ) -> None:
        """预加载图标（异步）
        
        在后台线程中加载指定的图标，加载完成后自动添加到缓存。
        
        Args:
            icon_names: 要加载的图标名称列表
            base_path: 应用程序基础路径
            icon_subdir: 图标子目录（相对于 base_path）
            icon_extension: 图标文件扩展名
        """
        # 停止之前的加载器
        cls.stop_loading()
        
        # 创建新的加载器
        cls._loader = ResourceLoaderWorker(
            icon_names, 
            base_path,
            icon_subdir,
            icon_extension
        )
        
        # 连接信号
        cls._loader.icon_loaded.connect(cls._on_worker_icon_loaded)
        cls._loader.all_loaded.connect(cls._on_worker_all_loaded)
        cls._loader.load_error.connect(cls._on_worker_load_error)
        
        # 启动加载
        cls._loader.start()
    
    @classmethod
    def _on_worker_icon_loaded(cls, name: str, icon: QIcon) -> None:
        """处理工作线程的图标加载完成信号"""
        cls.set_icon(name, icon)
    
    @classmethod
    def _on_worker_all_loaded(cls) -> None:
        """处理工作线程的全部加载完成信号"""
        if cls._on_all_loaded:
            try:
                cls._on_all_loaded()
            except Exception:
                pass
    
    @classmethod
    def _on_worker_load_error(cls, name: str, error: str) -> None:
        """处理工作线程的加载错误信号"""
        with QMutexLocker(cls._mutex):
            cls._error_count += 1
        
        if cls._on_load_error:
            try:
                cls._on_load_error(name, error)
            except Exception:
                pass
    
    @classmethod
    def stop_loading(cls) -> None:
        """停止当前的异步加载"""
        if cls._loader is not None:
            cls._loader.stop()
            cls._loader.wait(1000)  # 等待最多 1 秒
            cls._loader = None
    
    @classmethod
    def is_loading(cls) -> bool:
        """检查是否正在加载
        
        Returns:
            True 如果正在加载，否则 False
        """
        return cls._loader is not None and cls._loader.isRunning()
    
    @classmethod
    def set_on_icon_loaded(cls, callback: Optional[Callable[[str, QIcon], None]]) -> None:
        """设置图标加载完成回调
        
        Args:
            callback: 回调函数，接收 (name, icon) 参数
        """
        cls._on_icon_loaded = callback
    
    @classmethod
    def set_on_all_loaded(cls, callback: Optional[Callable[[], None]]) -> None:
        """设置全部加载完成回调
        
        Args:
            callback: 回调函数，无参数
        """
        cls._on_all_loaded = callback
    
    @classmethod
    def set_on_load_error(cls, callback: Optional[Callable[[str, str], None]]) -> None:
        """设置加载错误回调
        
        Args:
            callback: 回调函数，接收 (name, error) 参数
        """
        cls._on_load_error = callback
    
    @classmethod
    def remove_icon(cls, name: str) -> bool:
        """移除缓存的图标
        
        Args:
            name: 图标名称
            
        Returns:
            True 如果成功移除，False 如果图标不存在
        """
        with QMutexLocker(cls._mutex):
            if name in cls._icons:
                del cls._icons[name]
                return True
            return False
    
    @classmethod
    def remove_pixmap(cls, name: str) -> bool:
        """移除缓存的像素图
        
        Args:
            name: 像素图名称
            
        Returns:
            True 如果成功移除，False 如果像素图不存在
        """
        with QMutexLocker(cls._mutex):
            if name in cls._pixmaps:
                del cls._pixmaps[name]
                return True
            return False
    
    @classmethod
    def clear(cls) -> None:
        """清空所有缓存
        
        停止正在进行的加载，清空图标和像素图缓存。
        """
        cls.stop_loading()
        
        with QMutexLocker(cls._mutex):
            cls._icons.clear()
            cls._pixmaps.clear()
    
    @classmethod
    def clear_icons(cls) -> None:
        """清空图标缓存"""
        with QMutexLocker(cls._mutex):
            cls._icons.clear()
    
    @classmethod
    def clear_pixmaps(cls) -> None:
        """清空像素图缓存"""
        with QMutexLocker(cls._mutex):
            cls._pixmaps.clear()
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            包含 icon_count, pixmap_count, load_count, error_count, is_loading 的字典
        """
        with QMutexLocker(cls._mutex):
            return {
                "icon_count": len(cls._icons),
                "pixmap_count": len(cls._pixmaps),
                "load_count": cls._load_count,
                "error_count": cls._error_count,
                "is_loading": cls._loader is not None and cls._loader.isRunning(),
            }
    
    @classmethod
    def reset_stats(cls) -> None:
        """重置统计信息"""
        with QMutexLocker(cls._mutex):
            cls._load_count = 0
            cls._error_count = 0
    
    @classmethod
    def reset(cls) -> None:
        """重置缓存到初始状态
        
        停止加载，清空所有缓存，重置统计信息和回调。
        """
        cls.stop_loading()
        
        with QMutexLocker(cls._mutex):
            cls._icons.clear()
            cls._pixmaps.clear()
            cls._load_count = 0
            cls._error_count = 0
        
        cls._on_icon_loaded = None
        cls._on_all_loaded = None
        cls._on_load_error = None


def get_cached_icon(name: str, fallback: Optional[QIcon] = None) -> Optional[QIcon]:
    """获取缓存的图标，带 fallback 支持
    
    Args:
        name: 图标名称
        fallback: 如果图标未找到时返回的默认值
        
    Returns:
        缓存的图标或 fallback
    """
    icon = ResourceCache.get_icon(name)
    return icon if icon is not None else fallback


def get_cached_pixmap(name: str, fallback: Optional[QPixmap] = None) -> Optional[QPixmap]:
    """获取缓存的像素图，带 fallback 支持
    
    Args:
        name: 像素图名称
        fallback: 如果像素图未找到时返回的默认值
        
    Returns:
        缓存的像素图或 fallback
    """
    pixmap = ResourceCache.get_pixmap(name)
    return pixmap if pixmap is not None else fallback
