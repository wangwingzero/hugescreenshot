# =====================================================
# =============== 图片转换缓存 ===============
# =====================================================

"""
图片转换缓存 - 缓存 QImage 到 numpy 的转换结果

特性：
- 使用图片哈希作为缓存键
- 缓存转换结果，避免重复计算
- LRU 淘汰策略
"""

import hashlib
from typing import Optional, Dict, Any
from collections import OrderedDict
from PySide6.QtGui import QImage

# 尝试导入 numpy
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class ImageConversionCache:
    """图片转换缓存
    
    注意：为减少内存占用，缓存数量已限制为 3 张图片。
    """
    
    MAX_CACHE_SIZE = 3  # 最大缓存数量（减少以降低内存占用）
    
    def __init__(self):
        """初始化缓存"""
        # LRU 缓存：OrderedDict 保持插入顺序
        self._cache: OrderedDict[str, 'np.ndarray'] = OrderedDict()
        
        # 统计信息（用于测试）
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._conversion_count: int = 0
    
    def get_numpy_array(self, image: QImage) -> Optional['np.ndarray']:
        """
        获取 QImage 对应的 numpy 数组（带缓存）
        
        Args:
            image: QImage 对象
            
        Returns:
            numpy 数组或 None（如果 numpy 不可用）
        """
        if not HAS_NUMPY:
            return None
        
        if image.isNull():
            return None
        
        # 计算图片哈希
        image_hash = self._compute_hash(image)
        
        # 检查缓存
        if image_hash in self._cache:
            # 移动到末尾（LRU）
            self._cache.move_to_end(image_hash)
            self._hit_count += 1
            return self._cache[image_hash]
        
        # 缓存未命中，执行转换
        self._miss_count += 1
        arr = self._convert_to_numpy(image)
        
        if arr is not None:
            # 添加到缓存
            self._cache[image_hash] = arr
            self._conversion_count += 1
            
            # 淘汰旧条目
            while len(self._cache) > self.MAX_CACHE_SIZE:
                self._cache.popitem(last=False)
        
        return arr
    
    def _compute_hash(self, image: QImage) -> str:
        """
        计算图片哈希
        
        使用图片的尺寸和多个采样点计算哈希，减少碰撞风险
        """
        # 使用尺寸和格式作为基础
        width = image.width()
        height = image.height()
        format_val = image.format()
        
        # 采样部分像素用于哈希（避免处理整个图片）
        sample_data = f"{width}x{height}x{format_val}"
        
        # 采样更多像素点减少碰撞风险
        if width > 0 and height > 0:
            # 四个角 + 中心 + 四条边的中点 + 额外的网格点
            sample_points = [
                (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1),  # 四角
                (width // 2, height // 2),  # 中心
                (width // 2, 0), (width // 2, height - 1),  # 上下边中点
                (0, height // 2), (width - 1, height // 2),  # 左右边中点
                (width // 4, height // 4), (width * 3 // 4, height // 4),  # 额外网格点
                (width // 4, height * 3 // 4), (width * 3 // 4, height * 3 // 4),
            ]
            for x, y in sample_points:
                # 确保坐标在有效范围内
                x = max(0, min(x, width - 1))
                y = max(0, min(y, height - 1))
                pixel = image.pixel(x, y)
                sample_data += f"_{pixel}"
        
        return hashlib.md5(sample_data.encode()).hexdigest()
    
    def _convert_to_numpy(self, image: QImage) -> Optional['np.ndarray']:
        """
        将 QImage 转换为 numpy 数组
        
        Args:
            image: QImage 对象
            
        Returns:
            numpy 数组或 None
        """
        if not HAS_NUMPY:
            return None
        
        # 转换为 RGB32 格式
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        
        width = image.width()
        height = image.height()
        
        if width <= 0 or height <= 0:
            return None
        
        # 获取图像数据
        ptr = image.bits()
        arr = np.array(ptr).reshape(height, width, 4)
        
        # BGRA -> RGB
        return arr[:, :, [2, 1, 0]].copy()
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息（用于测试）
        
        Returns:
            dict: 包含 hit_count, miss_count, conversion_count, cache_size, hit_rate
        """
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0
        
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "conversion_count": self._conversion_count,
            "cache_size": len(self._cache),
            "hit_rate": hit_rate
        }
    
    def reset_stats(self):
        """重置统计信息（用于测试）"""
        self._hit_count = 0
        self._miss_count = 0
        self._conversion_count = 0


# 全局缓存实例
_global_cache: Optional[ImageConversionCache] = None


def get_image_cache() -> ImageConversionCache:
    """获取全局图片缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = ImageConversionCache()
    return _global_cache


def qimage_to_numpy_cached(image: QImage) -> Optional['np.ndarray']:
    """
    将 QImage 转换为 numpy 数组（使用全局缓存）
    
    Args:
        image: QImage 对象
        
    Returns:
        numpy 数组或 None
    """
    return get_image_cache().get_numpy_array(image)
