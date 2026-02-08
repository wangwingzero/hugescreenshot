# =====================================================
# =============== Pixmap 缓存管理器测试 ===============
# =====================================================

"""
Pixmap 缓存管理器测试

Feature: extreme-performance-optimization
Requirements: 3.3, 8.2

测试内容：
1. 图标缓存功能
2. 缩略图缓存功能
3. LRU 淘汰策略
4. 内存使用估算
5. 单例模式
"""

import pytest
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtCore import QSize

from screenshot_tool.core.pixmap_cache_manager import (
    PixmapCacheManager,
    get_pixmap_cache,
    get_cached_icon,
    cache_icon,
    get_cached_thumbnail,
    cache_thumbnail,
)


# =====================================================
# Fixtures
# =====================================================

@pytest.fixture
def cache_manager():
    """创建新的缓存管理器实例（每个测试独立）"""
    # 重置单例
    PixmapCacheManager.reset_instance()
    manager = PixmapCacheManager.instance()
    yield manager
    # 清理
    manager.clear_all()
    PixmapCacheManager.reset_instance()


@pytest.fixture
def sample_pixmap():
    """创建测试用 QPixmap"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(255, 0, 0))  # 红色
    return pixmap


@pytest.fixture
def sample_icon(sample_pixmap):
    """创建测试用 QIcon"""
    return QIcon(sample_pixmap)


# =====================================================
# 单例模式测试
# =====================================================

class TestSingleton:
    """单例模式测试"""
    
    def test_instance_returns_same_object(self, cache_manager):
        """测试 instance() 返回相同对象"""
        instance1 = PixmapCacheManager.instance()
        instance2 = PixmapCacheManager.instance()
        assert instance1 is instance2
    
    def test_get_pixmap_cache_returns_singleton(self, cache_manager):
        """测试便捷函数返回单例"""
        instance = PixmapCacheManager.instance()
        assert get_pixmap_cache() is instance
    
    def test_reset_instance_creates_new_object(self):
        """测试 reset_instance 创建新对象"""
        instance1 = PixmapCacheManager.instance()
        PixmapCacheManager.reset_instance()
        instance2 = PixmapCacheManager.instance()
        assert instance1 is not instance2
        # 清理
        PixmapCacheManager.reset_instance()


# =====================================================
# 图标缓存测试
# =====================================================

class TestIconCache:
    """图标缓存测试"""
    
    def test_cache_and_get_icon(self, cache_manager, sample_icon):
        """测试缓存和获取图标"""
        size = QSize(24, 24)
        
        # 初始应该为空
        assert cache_manager.get_icon("test", size) is None
        
        # 缓存图标
        cache_manager.cache_icon("test", size, sample_icon)
        
        # 应该能获取到
        cached = cache_manager.get_icon("test", size)
        assert cached is not None
        assert cached is sample_icon
    
    def test_icon_cache_different_sizes(self, cache_manager, sample_icon):
        """测试不同尺寸的图标分别缓存"""
        size1 = QSize(16, 16)
        size2 = QSize(24, 24)
        
        cache_manager.cache_icon("test", size1, sample_icon)
        
        # 不同尺寸应该返回 None
        assert cache_manager.get_icon("test", size2) is None
        
        # 相同尺寸应该返回缓存
        assert cache_manager.get_icon("test", size1) is sample_icon
    
    def test_icon_cache_different_names(self, cache_manager, sample_icon):
        """测试不同名称的图标分别缓存"""
        size = QSize(24, 24)
        
        cache_manager.cache_icon("icon1", size, sample_icon)
        
        # 不同名称应该返回 None
        assert cache_manager.get_icon("icon2", size) is None
        
        # 相同名称应该返回缓存
        assert cache_manager.get_icon("icon1", size) is sample_icon
    
    def test_has_icon(self, cache_manager, sample_icon):
        """测试 has_icon 方法"""
        size = QSize(24, 24)
        
        assert not cache_manager.has_icon("test", size)
        
        cache_manager.cache_icon("test", size, sample_icon)
        
        assert cache_manager.has_icon("test", size)
    
    def test_clear_icons(self, cache_manager, sample_icon):
        """测试清除图标缓存"""
        size = QSize(24, 24)
        
        cache_manager.cache_icon("test", size, sample_icon)
        assert cache_manager.has_icon("test", size)
        
        cache_manager.clear_icons()
        
        assert not cache_manager.has_icon("test", size)
    
    def test_icon_lru_eviction(self, cache_manager, sample_icon):
        """测试图标 LRU 淘汰"""
        size = QSize(24, 24)
        original_max = cache_manager.MAX_ICON_CACHE
        
        # 临时减小缓存大小以便测试
        cache_manager.MAX_ICON_CACHE = 3
        
        try:
            # 添加 3 个图标
            for i in range(3):
                cache_manager.cache_icon(f"icon{i}", size, sample_icon)
            
            # 所有图标都应该存在
            for i in range(3):
                assert cache_manager.has_icon(f"icon{i}", size)
            
            # 添加第 4 个图标，应该淘汰最旧的 icon0
            cache_manager.cache_icon("icon3", size, sample_icon)
            
            assert not cache_manager.has_icon("icon0", size)  # 被淘汰
            assert cache_manager.has_icon("icon1", size)
            assert cache_manager.has_icon("icon2", size)
            assert cache_manager.has_icon("icon3", size)
        finally:
            cache_manager.MAX_ICON_CACHE = original_max
    
    def test_icon_lru_access_updates_order(self, cache_manager, sample_icon):
        """测试访问图标更新 LRU 顺序"""
        size = QSize(24, 24)
        original_max = cache_manager.MAX_ICON_CACHE
        
        cache_manager.MAX_ICON_CACHE = 3
        
        try:
            # 添加 3 个图标
            for i in range(3):
                cache_manager.cache_icon(f"icon{i}", size, sample_icon)
            
            # 访问 icon0，使其变为最近使用
            cache_manager.get_icon("icon0", size)
            
            # 添加第 4 个图标，应该淘汰 icon1（现在是最旧的）
            cache_manager.cache_icon("icon3", size, sample_icon)
            
            assert cache_manager.has_icon("icon0", size)  # 最近访问，保留
            assert not cache_manager.has_icon("icon1", size)  # 被淘汰
            assert cache_manager.has_icon("icon2", size)
            assert cache_manager.has_icon("icon3", size)
        finally:
            cache_manager.MAX_ICON_CACHE = original_max


# =====================================================
# 缩略图缓存测试
# =====================================================

class TestThumbnailCache:
    """缩略图缓存测试"""
    
    def test_cache_and_get_thumbnail(self, cache_manager, sample_pixmap):
        """测试缓存和获取缩略图"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        # 初始应该为空
        assert cache_manager.get_thumbnail(path, size) is None
        
        # 缓存缩略图
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        
        # 应该能获取到
        cached = cache_manager.get_thumbnail(path, size)
        assert cached is not None
        assert cached is sample_pixmap
    
    def test_thumbnail_cache_different_sizes(self, cache_manager, sample_pixmap):
        """测试不同尺寸的缩略图分别缓存"""
        path = "/path/to/image.png"
        size1 = QSize(64, 64)
        size2 = QSize(128, 128)
        
        cache_manager.cache_thumbnail(path, size1, sample_pixmap)
        
        # 不同尺寸应该返回 None
        assert cache_manager.get_thumbnail(path, size2) is None
        
        # 相同尺寸应该返回缓存
        assert cache_manager.get_thumbnail(path, size1) is sample_pixmap
    
    def test_thumbnail_cache_different_paths(self, cache_manager, sample_pixmap):
        """测试不同路径的缩略图分别缓存"""
        path1 = "/path/to/image1.png"
        path2 = "/path/to/image2.png"
        size = QSize(64, 64)
        
        cache_manager.cache_thumbnail(path1, size, sample_pixmap)
        
        # 不同路径应该返回 None
        assert cache_manager.get_thumbnail(path2, size) is None
        
        # 相同路径应该返回缓存
        assert cache_manager.get_thumbnail(path1, size) is sample_pixmap
    
    def test_has_thumbnail(self, cache_manager, sample_pixmap):
        """测试 has_thumbnail 方法"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        assert not cache_manager.has_thumbnail(path, size)
        
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        
        assert cache_manager.has_thumbnail(path, size)
    
    def test_clear_thumbnails(self, cache_manager, sample_pixmap):
        """测试清除缩略图缓存"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        assert cache_manager.has_thumbnail(path, size)
        
        cache_manager.clear_thumbnails()
        
        assert not cache_manager.has_thumbnail(path, size)
    
    def test_thumbnail_lru_eviction(self, cache_manager, sample_pixmap):
        """测试缩略图 LRU 淘汰"""
        size = QSize(64, 64)
        original_max = cache_manager.MAX_THUMBNAIL_CACHE
        
        cache_manager.MAX_THUMBNAIL_CACHE = 3
        
        try:
            # 添加 3 个缩略图
            for i in range(3):
                cache_manager.cache_thumbnail(f"/path/image{i}.png", size, sample_pixmap)
            
            # 所有缩略图都应该存在
            for i in range(3):
                assert cache_manager.has_thumbnail(f"/path/image{i}.png", size)
            
            # 添加第 4 个缩略图，应该淘汰最旧的
            cache_manager.cache_thumbnail("/path/image3.png", size, sample_pixmap)
            
            assert not cache_manager.has_thumbnail("/path/image0.png", size)  # 被淘汰
            assert cache_manager.has_thumbnail("/path/image1.png", size)
            assert cache_manager.has_thumbnail("/path/image2.png", size)
            assert cache_manager.has_thumbnail("/path/image3.png", size)
        finally:
            cache_manager.MAX_THUMBNAIL_CACHE = original_max
    
    def test_thumbnail_lru_access_updates_order(self, cache_manager, sample_pixmap):
        """测试访问缩略图更新 LRU 顺序"""
        size = QSize(64, 64)
        original_max = cache_manager.MAX_THUMBNAIL_CACHE
        
        cache_manager.MAX_THUMBNAIL_CACHE = 3
        
        try:
            # 添加 3 个缩略图
            for i in range(3):
                cache_manager.cache_thumbnail(f"/path/image{i}.png", size, sample_pixmap)
            
            # 访问 image0，使其变为最近使用
            cache_manager.get_thumbnail("/path/image0.png", size)
            
            # 添加第 4 个缩略图，应该淘汰 image1（现在是最旧的）
            cache_manager.cache_thumbnail("/path/image3.png", size, sample_pixmap)
            
            assert cache_manager.has_thumbnail("/path/image0.png", size)  # 最近访问，保留
            assert not cache_manager.has_thumbnail("/path/image1.png", size)  # 被淘汰
            assert cache_manager.has_thumbnail("/path/image2.png", size)
            assert cache_manager.has_thumbnail("/path/image3.png", size)
        finally:
            cache_manager.MAX_THUMBNAIL_CACHE = original_max


# =====================================================
# 统计和内存测试
# =====================================================

class TestStatsAndMemory:
    """统计和内存测试"""
    
    def test_icon_hit_miss_stats(self, cache_manager, sample_icon):
        """测试图标命中/未命中统计"""
        size = QSize(24, 24)
        
        # 初始统计为 0
        stats = cache_manager.get_stats()
        assert stats["icon_hits"] == 0
        assert stats["icon_misses"] == 0
        
        # 未命中
        cache_manager.get_icon("test", size)
        stats = cache_manager.get_stats()
        assert stats["icon_misses"] == 1
        
        # 缓存后命中
        cache_manager.cache_icon("test", size, sample_icon)
        cache_manager.get_icon("test", size)
        stats = cache_manager.get_stats()
        assert stats["icon_hits"] == 1
    
    def test_thumbnail_hit_miss_stats(self, cache_manager, sample_pixmap):
        """测试缩略图命中/未命中统计"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        # 初始统计为 0
        stats = cache_manager.get_stats()
        assert stats["thumbnail_hits"] == 0
        assert stats["thumbnail_misses"] == 0
        
        # 未命中
        cache_manager.get_thumbnail(path, size)
        stats = cache_manager.get_stats()
        assert stats["thumbnail_misses"] == 1
        
        # 缓存后命中
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        cache_manager.get_thumbnail(path, size)
        stats = cache_manager.get_stats()
        assert stats["thumbnail_hits"] == 1
    
    def test_hit_rate_calculation(self, cache_manager, sample_icon):
        """测试命中率计算"""
        size = QSize(24, 24)
        
        # 1 次未命中
        cache_manager.get_icon("test", size)
        
        # 缓存后 2 次命中
        cache_manager.cache_icon("test", size, sample_icon)
        cache_manager.get_icon("test", size)
        cache_manager.get_icon("test", size)
        
        stats = cache_manager.get_stats()
        # 2 命中 / 3 总计 = 0.666...
        assert abs(stats["icon_hit_rate"] - 2/3) < 0.01
    
    def test_memory_usage_estimation(self, cache_manager, sample_pixmap):
        """测试内存使用估算"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        # 初始内存应该很小
        initial_memory = cache_manager.get_memory_usage()
        
        # 添加缩略图后内存应该增加
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        
        new_memory = cache_manager.get_memory_usage()
        assert new_memory > initial_memory
        
        # 64x64 RGBA = 64*64*4 = 16384 字节
        expected_pixmap_memory = 64 * 64 * 4
        assert new_memory >= expected_pixmap_memory
    
    def test_memory_usage_mb(self, cache_manager, sample_pixmap):
        """测试 MB 单位的内存使用"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        
        memory_bytes = cache_manager.get_memory_usage()
        memory_mb = cache_manager.get_memory_usage_mb()
        
        assert abs(memory_mb - memory_bytes / (1024 * 1024)) < 0.001
    
    def test_reset_stats(self, cache_manager, sample_icon):
        """测试重置统计"""
        size = QSize(24, 24)
        
        # 产生一些统计
        cache_manager.get_icon("test", size)
        cache_manager.cache_icon("test", size, sample_icon)
        cache_manager.get_icon("test", size)
        
        stats = cache_manager.get_stats()
        assert stats["icon_hits"] > 0 or stats["icon_misses"] > 0
        
        # 重置统计
        cache_manager.reset_stats()
        
        stats = cache_manager.get_stats()
        assert stats["icon_hits"] == 0
        assert stats["icon_misses"] == 0
        assert stats["thumbnail_hits"] == 0
        assert stats["thumbnail_misses"] == 0
    
    def test_cache_size_in_stats(self, cache_manager, sample_icon, sample_pixmap):
        """测试统计中的缓存大小"""
        icon_size = QSize(24, 24)
        thumb_size = QSize(64, 64)
        
        stats = cache_manager.get_stats()
        assert stats["icon_cache_size"] == 0
        assert stats["thumbnail_cache_size"] == 0
        
        cache_manager.cache_icon("test", icon_size, sample_icon)
        cache_manager.cache_thumbnail("/path/image.png", thumb_size, sample_pixmap)
        
        stats = cache_manager.get_stats()
        assert stats["icon_cache_size"] == 1
        assert stats["thumbnail_cache_size"] == 1


# =====================================================
# 便捷函数测试
# =====================================================

class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_get_cached_icon_function(self, cache_manager, sample_icon):
        """测试 get_cached_icon 便捷函数"""
        size = QSize(24, 24)
        
        assert get_cached_icon("test", size) is None
        
        cache_icon("test", size, sample_icon)
        
        assert get_cached_icon("test", size) is sample_icon
    
    def test_cache_icon_function(self, cache_manager, sample_icon):
        """测试 cache_icon 便捷函数"""
        size = QSize(24, 24)
        
        cache_icon("test", size, sample_icon)
        
        assert cache_manager.has_icon("test", size)
    
    def test_get_cached_thumbnail_function(self, cache_manager, sample_pixmap):
        """测试 get_cached_thumbnail 便捷函数"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        assert get_cached_thumbnail(path, size) is None
        
        cache_thumbnail(path, size, sample_pixmap)
        
        assert get_cached_thumbnail(path, size) is sample_pixmap
    
    def test_cache_thumbnail_function(self, cache_manager, sample_pixmap):
        """测试 cache_thumbnail 便捷函数"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        cache_thumbnail(path, size, sample_pixmap)
        
        assert cache_manager.has_thumbnail(path, size)


# =====================================================
# 清除测试
# =====================================================

class TestClearOperations:
    """清除操作测试"""
    
    def test_clear_all(self, cache_manager, sample_icon, sample_pixmap):
        """测试清除所有缓存"""
        icon_size = QSize(24, 24)
        thumb_size = QSize(64, 64)
        
        cache_manager.cache_icon("test", icon_size, sample_icon)
        cache_manager.cache_thumbnail("/path/image.png", thumb_size, sample_pixmap)
        
        assert cache_manager.has_icon("test", icon_size)
        assert cache_manager.has_thumbnail("/path/image.png", thumb_size)
        
        cache_manager.clear_all()
        
        assert not cache_manager.has_icon("test", icon_size)
        assert not cache_manager.has_thumbnail("/path/image.png", thumb_size)


# =====================================================
# 边界情况测试
# =====================================================

class TestEdgeCases:
    """边界情况测试"""
    
    def test_cache_same_icon_twice(self, cache_manager, sample_icon):
        """测试重复缓存同一图标"""
        size = QSize(24, 24)
        
        cache_manager.cache_icon("test", size, sample_icon)
        cache_manager.cache_icon("test", size, sample_icon)
        
        stats = cache_manager.get_stats()
        assert stats["icon_cache_size"] == 1  # 不应该重复
    
    def test_cache_same_thumbnail_twice(self, cache_manager, sample_pixmap):
        """测试重复缓存同一缩略图"""
        path = "/path/to/image.png"
        size = QSize(64, 64)
        
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        cache_manager.cache_thumbnail(path, size, sample_pixmap)
        
        stats = cache_manager.get_stats()
        assert stats["thumbnail_cache_size"] == 1  # 不应该重复
    
    def test_zero_size(self, cache_manager, sample_icon, sample_pixmap):
        """测试零尺寸"""
        zero_size = QSize(0, 0)
        
        # 应该能正常缓存（虽然实际使用中不太可能）
        cache_manager.cache_icon("test", zero_size, sample_icon)
        cache_manager.cache_thumbnail("/path/image.png", zero_size, sample_pixmap)
        
        assert cache_manager.has_icon("test", zero_size)
        assert cache_manager.has_thumbnail("/path/image.png", zero_size)
    
    def test_empty_path(self, cache_manager, sample_pixmap):
        """测试空路径"""
        size = QSize(64, 64)
        
        cache_manager.cache_thumbnail("", size, sample_pixmap)
        
        assert cache_manager.has_thumbnail("", size)
    
    def test_empty_name(self, cache_manager, sample_icon):
        """测试空名称"""
        size = QSize(24, 24)
        
        cache_manager.cache_icon("", size, sample_icon)
        
        assert cache_manager.has_icon("", size)
