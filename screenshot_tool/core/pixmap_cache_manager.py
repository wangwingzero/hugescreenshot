# =====================================================
# =============== Pixmap 缓存管理器 ===============
# =====================================================

"""
Pixmap 缓存管理器 - 高性能图像缓存

Feature: extreme-performance-optimization
Requirements: 3.3, 8.2

优化策略：
1. 全局图标缓存（LRU 淘汰）
2. 缩略图缓存（带 LRU 淘汰）
3. 支持缓存大小限制
4. 内存使用估算
"""

from typing import Dict, Optional, Tuple, List
from collections import OrderedDict
from PySide6.QtGui import QPixmap, QIcon, QImage
from PySide6.QtCore import QSize


class PixmapCacheManager:
    """Pixmap 缓存管理器
    
    Feature: extreme-performance-optimization
    Requirements: 3.3, 8.2
    
    提供图标和缩略图的高效缓存，使用 LRU 淘汰策略。
    
    使用示例：
        cache = PixmapCacheManager.instance()
        
        # 获取图标
        icon = cache.get_icon("save", QSize(24, 24))
        if icon is None:
            icon = QIcon("path/to/save.png")
            cache.cache_icon("save", QSize(24, 24), icon)
        
        # 获取缩略图
        thumb = cache.get_thumbnail("/path/to/image.png", QSize(64, 64))
        if thumb is None:
            thumb = create_thumbnail(...)
            cache.cache_thumbnail("/path/to/image.png", QSize(64, 64), thumb)
    """
    
    # 缓存容量限制
    MAX_THUMBNAIL_CACHE = 50
    MAX_ICON_CACHE = 100
    
    # 单例实例
    _instance: Optional['PixmapCacheManager'] = None
    
    def __init__(self):
        """初始化缓存管理器"""
        # 图标缓存：key = (name, width, height)
        # 使用 OrderedDict 实现 LRU
        self._icon_cache: OrderedDict[Tuple[str, int, int], QIcon] = OrderedDict()
        
        # 缩略图缓存：key = (path, width, height)
        # 使用 OrderedDict 实现 LRU
        self._thumbnail_cache: OrderedDict[Tuple[str, int, int], QPixmap] = OrderedDict()
        
        # 统计信息
        self._icon_hits: int = 0
        self._icon_misses: int = 0
        self._thumbnail_hits: int = 0
        self._thumbnail_misses: int = 0
    
    @classmethod
    def instance(cls) -> 'PixmapCacheManager':
        """获取单例实例
        
        Returns:
            PixmapCacheManager 单例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        cls._instance = None
    
    # =====================================================
    # 图标缓存
    # =====================================================
    
    def get_icon(self, name: str, size: QSize) -> Optional[QIcon]:
        """获取缓存的图标
        
        Args:
            name: 图标名称
            size: 图标尺寸
            
        Returns:
            缓存的 QIcon，如果不存在返回 None
        """
        key = (name, size.width(), size.height())
        
        if key in self._icon_cache:
            # 移动到末尾（LRU）
            self._icon_cache.move_to_end(key)
            self._icon_hits += 1
            return self._icon_cache[key]
        
        self._icon_misses += 1
        return None
    
    def cache_icon(self, name: str, size: QSize, icon: QIcon) -> None:
        """缓存图标
        
        Args:
            name: 图标名称
            size: 图标尺寸
            icon: QIcon 对象
        """
        key = (name, size.width(), size.height())
        
        # 如果已存在，先删除（更新 LRU 顺序）
        if key in self._icon_cache:
            del self._icon_cache[key]
        
        # LRU 淘汰
        while len(self._icon_cache) >= self.MAX_ICON_CACHE:
            # 删除最旧的条目（OrderedDict 的第一个）
            self._icon_cache.popitem(last=False)
        
        self._icon_cache[key] = icon
    
    def has_icon(self, name: str, size: QSize) -> bool:
        """检查图标是否已缓存
        
        Args:
            name: 图标名称
            size: 图标尺寸
            
        Returns:
            是否已缓存
        """
        key = (name, size.width(), size.height())
        return key in self._icon_cache
    
    def clear_icons(self) -> None:
        """清除所有图标缓存"""
        self._icon_cache.clear()
    
    # =====================================================
    # 缩略图缓存
    # =====================================================
    
    def get_thumbnail(self, path: str, size: QSize) -> Optional[QPixmap]:
        """获取缓存的缩略图
        
        Args:
            path: 图片路径
            size: 缩略图尺寸
            
        Returns:
            缓存的 QPixmap，如果不存在返回 None
        """
        key = (path, size.width(), size.height())
        
        if key in self._thumbnail_cache:
            # 移动到末尾（LRU）
            self._thumbnail_cache.move_to_end(key)
            self._thumbnail_hits += 1
            return self._thumbnail_cache[key]
        
        self._thumbnail_misses += 1
        return None
    
    def cache_thumbnail(self, path: str, size: QSize, pixmap: QPixmap) -> None:
        """缓存缩略图
        
        Args:
            path: 图片路径
            size: 缩略图尺寸
            pixmap: QPixmap 对象
        """
        key = (path, size.width(), size.height())
        
        # 如果已存在，先删除（更新 LRU 顺序）
        if key in self._thumbnail_cache:
            del self._thumbnail_cache[key]
        
        # LRU 淘汰
        while len(self._thumbnail_cache) >= self.MAX_THUMBNAIL_CACHE:
            # 删除最旧的条目（OrderedDict 的第一个）
            self._thumbnail_cache.popitem(last=False)
        
        self._thumbnail_cache[key] = pixmap
    
    def has_thumbnail(self, path: str, size: QSize) -> bool:
        """检查缩略图是否已缓存
        
        Args:
            path: 图片路径
            size: 缩略图尺寸
            
        Returns:
            是否已缓存
        """
        key = (path, size.width(), size.height())
        return key in self._thumbnail_cache
    
    def clear_thumbnails(self) -> None:
        """清除所有缩略图缓存（释放内存）"""
        self._thumbnail_cache.clear()
    
    # =====================================================
    # 通用方法
    # =====================================================
    
    def clear_all(self) -> None:
        """清除所有缓存"""
        self.clear_icons()
        self.clear_thumbnails()
    
    def get_memory_usage(self) -> int:
        """估算缓存内存使用（字节）
        
        Returns:
            估算的内存使用量（字节）
        """
        total = 0
        
        # 估算缩略图内存
        for pixmap in self._thumbnail_cache.values():
            if pixmap and not pixmap.isNull():
                # 假设 RGBA 格式，每像素 4 字节
                total += pixmap.width() * pixmap.height() * 4
        
        # 图标内存估算较复杂，这里简化处理
        # 假设每个图标平均占用 4KB
        total += len(self._icon_cache) * 4096
        
        return total
    
    def get_memory_usage_mb(self) -> float:
        """获取缓存内存使用（MB）
        
        Returns:
            内存使用量（MB）
        """
        return self.get_memory_usage() / (1024 * 1024)
    
    def get_stats(self) -> Dict[str, any]:
        """获取缓存统计信息
        
        Returns:
            包含缓存统计的字典
        """
        icon_total = self._icon_hits + self._icon_misses
        thumbnail_total = self._thumbnail_hits + self._thumbnail_misses
        
        return {
            "icon_cache_size": len(self._icon_cache),
            "icon_cache_max": self.MAX_ICON_CACHE,
            "icon_hits": self._icon_hits,
            "icon_misses": self._icon_misses,
            "icon_hit_rate": self._icon_hits / icon_total if icon_total > 0 else 0.0,
            "thumbnail_cache_size": len(self._thumbnail_cache),
            "thumbnail_cache_max": self.MAX_THUMBNAIL_CACHE,
            "thumbnail_hits": self._thumbnail_hits,
            "thumbnail_misses": self._thumbnail_misses,
            "thumbnail_hit_rate": self._thumbnail_hits / thumbnail_total if thumbnail_total > 0 else 0.0,
            "memory_usage_bytes": self.get_memory_usage(),
            "memory_usage_mb": self.get_memory_usage_mb(),
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._icon_hits = 0
        self._icon_misses = 0
        self._thumbnail_hits = 0
        self._thumbnail_misses = 0


# =====================================================
# 便捷函数
# =====================================================

def get_pixmap_cache() -> PixmapCacheManager:
    """获取全局 Pixmap 缓存实例
    
    Returns:
        PixmapCacheManager 单例
    """
    return PixmapCacheManager.instance()


def get_cached_icon(name: str, size: QSize) -> Optional[QIcon]:
    """获取缓存的图标（便捷函数）
    
    Args:
        name: 图标名称
        size: 图标尺寸
        
    Returns:
        缓存的 QIcon，如果不存在返回 None
    """
    return PixmapCacheManager.instance().get_icon(name, size)


def cache_icon(name: str, size: QSize, icon: QIcon) -> None:
    """缓存图标（便捷函数）
    
    Args:
        name: 图标名称
        size: 图标尺寸
        icon: QIcon 对象
    """
    PixmapCacheManager.instance().cache_icon(name, size, icon)


def get_cached_thumbnail(path: str, size: QSize) -> Optional[QPixmap]:
    """获取缓存的缩略图（便捷函数）
    
    Args:
        path: 图片路径
        size: 缩略图尺寸
        
    Returns:
        缓存的 QPixmap，如果不存在返回 None
    """
    return PixmapCacheManager.instance().get_thumbnail(path, size)


def cache_thumbnail(path: str, size: QSize, pixmap: QPixmap) -> None:
    """缓存缩略图（便捷函数）
    
    Args:
        path: 图片路径
        size: 缩略图尺寸
        pixmap: QPixmap 对象
    """
    PixmapCacheManager.instance().cache_thumbnail(path, size, pixmap)
