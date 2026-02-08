# =====================================================
# =============== Pixmap 缓存属性测试 ===============
# =====================================================

"""
Pixmap 缓存管理器属性测试

Feature: extreme-performance-optimization
Property 7: Pixmap and Icon Caching

**Validates: Requirements 3.3, 8.2**

测试内容：
1. 重复访问返回缓存实例
2. LRU 淘汰正确工作
3. 缓存命中/未命中统计准确

使用 hypothesis 库进行属性测试。
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtCore import QSize

from screenshot_tool.core.pixmap_cache_manager import (
    PixmapCacheManager,
)


# =====================================================
# QApplication 单例
# =====================================================

_app = None

def get_app():
    """获取或创建 QApplication 实例"""
    global _app
    if _app is None:
        _app = QApplication.instance()
        if _app is None:
            _app = QApplication([])
    return _app


# 确保 QApplication 在模块加载时初始化
get_app()


# =====================================================
# Strategies
# =====================================================

# 图标名称策略：生成合理的图标名称
icon_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_-'),
    min_size=1,
    max_size=20
)

# 文件路径策略：生成合理的文件路径
file_path_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='/_-.'),
    min_size=1,
    max_size=50
).map(lambda s: f"/path/{s}.png")

# 尺寸策略：生成合理的图像尺寸
size_strategy = st.builds(
    QSize,
    st.integers(min_value=1, max_value=256),
    st.integers(min_value=1, max_value=256)
)


# =====================================================
# Fixtures
# =====================================================

@pytest.fixture(autouse=True)
def reset_cache():
    """每个测试前重置缓存管理器"""
    PixmapCacheManager.reset_instance()
    yield
    PixmapCacheManager.reset_instance()


def create_test_pixmap(width: int = 64, height: int = 64) -> QPixmap:
    """创建测试用 QPixmap"""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(255, 0, 0))
    return pixmap


def create_test_icon(width: int = 24, height: int = 24) -> QIcon:
    """创建测试用 QIcon"""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(0, 0, 255))
    return QIcon(pixmap)


# =====================================================
# Property 7.1: 重复访问图标返回缓存实例
# =====================================================

class TestIconCacheProperty:
    """图标缓存属性测试
    
    **Validates: Requirements 3.3, 8.2**
    """
    
    @settings(max_examples=100)
    @given(
        name=icon_name_strategy,
        width=st.integers(min_value=1, max_value=128),
        height=st.integers(min_value=1, max_value=128)
    )
    def test_repeated_icon_access_returns_cached_instance(self, name, width, height):
        """Property 7: 重复访问同一图标返回缓存实例
        
        **Validates: Requirements 3.3, 8.2**
        
        For any icon name and size, after caching:
        - First access returns the cached instance
        - Second access returns the SAME instance (identity check)
        """
        cache = PixmapCacheManager.instance()
        size = QSize(width, height)
        icon = create_test_icon(width, height)
        
        # 缓存图标
        cache.cache_icon(name, size, icon)
        
        # 第一次访问
        first_access = cache.get_icon(name, size)
        
        # 第二次访问
        second_access = cache.get_icon(name, size)
        
        # 验证返回相同实例
        assert first_access is icon, "First access should return cached icon"
        assert second_access is icon, "Second access should return same cached icon"
        assert first_access is second_access, "Both accesses should return identical instance"

    @settings(max_examples=100)
    @given(
        name=icon_name_strategy,
        width=st.integers(min_value=1, max_value=128),
        height=st.integers(min_value=1, max_value=128),
        access_count=st.integers(min_value=2, max_value=20)
    )
    def test_multiple_icon_accesses_all_return_same_instance(
        self, name, width, height, access_count
    ):
        """Property 7: 多次访问图标都返回相同实例
        
        **Validates: Requirements 3.3, 8.2**
        
        For any number of accesses to a cached icon,
        all accesses should return the identical instance.
        """
        cache = PixmapCacheManager.instance()
        size = QSize(width, height)
        icon = create_test_icon(width, height)
        
        cache.cache_icon(name, size, icon)
        
        # 多次访问
        accesses = [cache.get_icon(name, size) for _ in range(access_count)]
        
        # 所有访问都应该返回相同实例
        for i, access in enumerate(accesses):
            assert access is icon, f"Access {i+1} should return cached icon"


# =====================================================
# Property 7.2: 重复访问缩略图返回缓存实例
# =====================================================

class TestThumbnailCacheProperty:
    """缩略图缓存属性测试
    
    **Validates: Requirements 3.3, 8.2**
    """
    
    @settings(max_examples=100)
    @given(
        path=file_path_strategy,
        width=st.integers(min_value=1, max_value=256),
        height=st.integers(min_value=1, max_value=256)
    )
    def test_repeated_thumbnail_access_returns_cached_instance(
        self, path, width, height
    ):
        """Property 7: 重复访问同一缩略图返回缓存实例
        
        **Validates: Requirements 3.3, 8.2**
        
        For any thumbnail path and size, after caching:
        - First access returns the cached instance
        - Second access returns the SAME instance (identity check)
        """
        cache = PixmapCacheManager.instance()
        size = QSize(width, height)
        pixmap = create_test_pixmap(width, height)
        
        # 缓存缩略图
        cache.cache_thumbnail(path, size, pixmap)
        
        # 第一次访问
        first_access = cache.get_thumbnail(path, size)
        
        # 第二次访问
        second_access = cache.get_thumbnail(path, size)
        
        # 验证返回相同实例
        assert first_access is pixmap, "First access should return cached pixmap"
        assert second_access is pixmap, "Second access should return same cached pixmap"
        assert first_access is second_access, "Both accesses should return identical instance"

    @settings(max_examples=100)
    @given(
        path=file_path_strategy,
        width=st.integers(min_value=1, max_value=256),
        height=st.integers(min_value=1, max_value=256),
        access_count=st.integers(min_value=2, max_value=20)
    )
    def test_multiple_thumbnail_accesses_all_return_same_instance(
        self, path, width, height, access_count
    ):
        """Property 7: 多次访问缩略图都返回相同实例
        
        **Validates: Requirements 3.3, 8.2**
        
        For any number of accesses to a cached thumbnail,
        all accesses should return the identical instance.
        """
        cache = PixmapCacheManager.instance()
        size = QSize(width, height)
        pixmap = create_test_pixmap(width, height)
        
        cache.cache_thumbnail(path, size, pixmap)
        
        # 多次访问
        accesses = [cache.get_thumbnail(path, size) for _ in range(access_count)]
        
        # 所有访问都应该返回相同实例
        for i, access in enumerate(accesses):
            assert access is pixmap, f"Access {i+1} should return cached pixmap"


# =====================================================
# Property 7.3: LRU 淘汰正确工作
# =====================================================

class TestLRUEvictionProperty:
    """LRU 淘汰属性测试
    
    **Validates: Requirements 3.3, 8.2**
    """
    
    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=2, max_value=10),
        extra_items=st.integers(min_value=1, max_value=5)
    )
    def test_icon_lru_eviction_removes_oldest(self, cache_size, extra_items):
        """Property 7: 图标 LRU 淘汰移除最旧条目
        
        **Validates: Requirements 3.3, 8.2**
        
        When cache is full and new items are added:
        - Oldest items (least recently used) are evicted
        - Newest items remain in cache
        """
        # 确保 extra_items 不超过 cache_size，否则测试逻辑会变复杂
        assume(extra_items <= cache_size)
        
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_ICON_CACHE
        cache.MAX_ICON_CACHE = cache_size
        
        try:
            size = QSize(24, 24)
            icons = {}
            
            # 填满缓存
            for i in range(cache_size):
                icon = create_test_icon()
                icons[f"icon_{i}"] = icon
                cache.cache_icon(f"icon_{i}", size, icon)
            
            # 添加额外条目，触发淘汰
            for i in range(extra_items):
                icon = create_test_icon()
                icons[f"extra_{i}"] = icon
                cache.cache_icon(f"extra_{i}", size, icon)
            
            # 验证：最旧的条目被淘汰
            for i in range(extra_items):
                assert not cache.has_icon(f"icon_{i}", size), \
                    f"icon_{i} should be evicted"
            
            # 验证：较新的条目仍在缓存
            for i in range(extra_items, cache_size):
                assert cache.has_icon(f"icon_{i}", size), \
                    f"icon_{i} should still be in cache"
            
            # 验证：新添加的条目在缓存
            for i in range(extra_items):
                assert cache.has_icon(f"extra_{i}", size), \
                    f"extra_{i} should be in cache"
        finally:
            cache.MAX_ICON_CACHE = original_max

    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=2, max_value=10),
        extra_items=st.integers(min_value=1, max_value=5)
    )
    def test_thumbnail_lru_eviction_removes_oldest(self, cache_size, extra_items):
        """Property 7: 缩略图 LRU 淘汰移除最旧条目
        
        **Validates: Requirements 3.3, 8.2**
        
        When cache is full and new items are added:
        - Oldest items (least recently used) are evicted
        - Newest items remain in cache
        """
        # 确保 extra_items 不超过 cache_size，否则测试逻辑会变复杂
        assume(extra_items <= cache_size)
        
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_THUMBNAIL_CACHE
        cache.MAX_THUMBNAIL_CACHE = cache_size
        
        try:
            size = QSize(64, 64)
            
            # 填满缓存
            for i in range(cache_size):
                pixmap = create_test_pixmap()
                cache.cache_thumbnail(f"/path/thumb_{i}.png", size, pixmap)
            
            # 添加额外条目，触发淘汰
            for i in range(extra_items):
                pixmap = create_test_pixmap()
                cache.cache_thumbnail(f"/path/extra_{i}.png", size, pixmap)
            
            # 验证：最旧的条目被淘汰
            for i in range(extra_items):
                assert not cache.has_thumbnail(f"/path/thumb_{i}.png", size), \
                    f"thumb_{i} should be evicted"
            
            # 验证：较新的条目仍在缓存
            for i in range(extra_items, cache_size):
                assert cache.has_thumbnail(f"/path/thumb_{i}.png", size), \
                    f"thumb_{i} should still be in cache"
            
            # 验证：新添加的条目在缓存
            for i in range(extra_items):
                assert cache.has_thumbnail(f"/path/extra_{i}.png", size), \
                    f"extra_{i} should be in cache"
        finally:
            cache.MAX_THUMBNAIL_CACHE = original_max

    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=3, max_value=10),
        access_index=st.integers(min_value=0, max_value=2)
    )
    def test_icon_access_updates_lru_order(self, cache_size, access_index):
        """Property 7: 访问图标更新 LRU 顺序
        
        **Validates: Requirements 3.3, 8.2**
        
        When an item is accessed, it becomes most recently used
        and should not be evicted when cache is full.
        """
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_ICON_CACHE
        cache.MAX_ICON_CACHE = cache_size
        
        try:
            size = QSize(24, 24)
            
            # 填满缓存
            for i in range(cache_size):
                icon = create_test_icon()
                cache.cache_icon(f"icon_{i}", size, icon)
            
            # 访问一个早期添加的条目，使其变为最近使用
            accessed_index = access_index % cache_size
            cache.get_icon(f"icon_{accessed_index}", size)
            
            # 添加新条目，触发淘汰
            new_icon = create_test_icon()
            cache.cache_icon("new_icon", size, new_icon)
            
            # 验证：被访问的条目应该仍在缓存（因为变成了最近使用）
            assert cache.has_icon(f"icon_{accessed_index}", size), \
                f"icon_{accessed_index} was accessed and should not be evicted"
            
            # 验证：新条目在缓存
            assert cache.has_icon("new_icon", size), \
                "new_icon should be in cache"
        finally:
            cache.MAX_ICON_CACHE = original_max

    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=3, max_value=10),
        access_index=st.integers(min_value=0, max_value=2)
    )
    def test_thumbnail_access_updates_lru_order(self, cache_size, access_index):
        """Property 7: 访问缩略图更新 LRU 顺序
        
        **Validates: Requirements 3.3, 8.2**
        
        When an item is accessed, it becomes most recently used
        and should not be evicted when cache is full.
        """
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_THUMBNAIL_CACHE
        cache.MAX_THUMBNAIL_CACHE = cache_size
        
        try:
            size = QSize(64, 64)
            
            # 填满缓存
            for i in range(cache_size):
                pixmap = create_test_pixmap()
                cache.cache_thumbnail(f"/path/thumb_{i}.png", size, pixmap)
            
            # 访问一个早期添加的条目，使其变为最近使用
            accessed_index = access_index % cache_size
            cache.get_thumbnail(f"/path/thumb_{accessed_index}.png", size)
            
            # 添加新条目，触发淘汰
            new_pixmap = create_test_pixmap()
            cache.cache_thumbnail("/path/new_thumb.png", size, new_pixmap)
            
            # 验证：被访问的条目应该仍在缓存
            assert cache.has_thumbnail(f"/path/thumb_{accessed_index}.png", size), \
                f"thumb_{accessed_index} was accessed and should not be evicted"
            
            # 验证：新条目在缓存
            assert cache.has_thumbnail("/path/new_thumb.png", size), \
                "new_thumb should be in cache"
        finally:
            cache.MAX_THUMBNAIL_CACHE = original_max


# =====================================================
# Property 7.4: 缓存命中/未命中统计准确
# =====================================================

class TestCacheStatsProperty:
    """缓存统计属性测试
    
    **Validates: Requirements 3.3, 8.2**
    """
    
    @settings(max_examples=100)
    @given(
        hit_count=st.integers(min_value=0, max_value=20),
        miss_count=st.integers(min_value=0, max_value=20)
    )
    def test_icon_hit_miss_stats_accurate(self, hit_count, miss_count):
        """Property 7: 图标缓存命中/未命中统计准确
        
        **Validates: Requirements 3.3, 8.2**
        
        For any sequence of cache accesses:
        - Hit count equals number of successful cache retrievals
        - Miss count equals number of failed cache retrievals
        """
        cache = PixmapCacheManager.instance()
        cache.reset_stats()
        
        size = QSize(24, 24)
        icon = create_test_icon()
        
        # 缓存一个图标
        cache.cache_icon("cached_icon", size, icon)
        
        # 执行命中访问
        for _ in range(hit_count):
            cache.get_icon("cached_icon", size)
        
        # 执行未命中访问
        for i in range(miss_count):
            cache.get_icon(f"missing_icon_{i}", size)
        
        stats = cache.get_stats()
        
        assert stats["icon_hits"] == hit_count, \
            f"Expected {hit_count} hits, got {stats['icon_hits']}"
        assert stats["icon_misses"] == miss_count, \
            f"Expected {miss_count} misses, got {stats['icon_misses']}"

    @settings(max_examples=100)
    @given(
        hit_count=st.integers(min_value=0, max_value=20),
        miss_count=st.integers(min_value=0, max_value=20)
    )
    def test_thumbnail_hit_miss_stats_accurate(self, hit_count, miss_count):
        """Property 7: 缩略图缓存命中/未命中统计准确
        
        **Validates: Requirements 3.3, 8.2**
        
        For any sequence of cache accesses:
        - Hit count equals number of successful cache retrievals
        - Miss count equals number of failed cache retrievals
        """
        cache = PixmapCacheManager.instance()
        cache.reset_stats()
        
        size = QSize(64, 64)
        pixmap = create_test_pixmap()
        
        # 缓存一个缩略图
        cache.cache_thumbnail("/path/cached.png", size, pixmap)
        
        # 执行命中访问
        for _ in range(hit_count):
            cache.get_thumbnail("/path/cached.png", size)
        
        # 执行未命中访问
        for i in range(miss_count):
            cache.get_thumbnail(f"/path/missing_{i}.png", size)
        
        stats = cache.get_stats()
        
        assert stats["thumbnail_hits"] == hit_count, \
            f"Expected {hit_count} hits, got {stats['thumbnail_hits']}"
        assert stats["thumbnail_misses"] == miss_count, \
            f"Expected {miss_count} misses, got {stats['thumbnail_misses']}"

    @settings(max_examples=100)
    @given(
        hits=st.integers(min_value=1, max_value=50),
        misses=st.integers(min_value=1, max_value=50)
    )
    def test_hit_rate_calculation_accurate(self, hits, misses):
        """Property 7: 命中率计算准确
        
        **Validates: Requirements 3.3, 8.2**
        
        Hit rate should equal hits / (hits + misses).
        """
        cache = PixmapCacheManager.instance()
        cache.reset_stats()
        
        size = QSize(24, 24)
        icon = create_test_icon()
        
        cache.cache_icon("test", size, icon)
        
        # 执行命中访问
        for _ in range(hits):
            cache.get_icon("test", size)
        
        # 执行未命中访问
        for i in range(misses):
            cache.get_icon(f"missing_{i}", size)
        
        stats = cache.get_stats()
        expected_rate = hits / (hits + misses)
        
        assert abs(stats["icon_hit_rate"] - expected_rate) < 0.001, \
            f"Expected hit rate {expected_rate}, got {stats['icon_hit_rate']}"


# =====================================================
# Property 7.5: 缓存大小限制
# =====================================================

class TestCacheSizeLimitProperty:
    """缓存大小限制属性测试
    
    **Validates: Requirements 3.3, 8.2**
    """
    
    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=2, max_value=20),
        items_to_add=st.integers(min_value=1, max_value=50)
    )
    def test_icon_cache_never_exceeds_max(self, cache_size, items_to_add):
        """Property 7: 图标缓存永不超过最大限制
        
        **Validates: Requirements 3.3, 8.2**
        
        For any number of items added, cache size should never exceed MAX_ICON_CACHE.
        """
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_ICON_CACHE
        cache.MAX_ICON_CACHE = cache_size
        
        try:
            size = QSize(24, 24)
            
            for i in range(items_to_add):
                icon = create_test_icon()
                cache.cache_icon(f"icon_{i}", size, icon)
                
                # 每次添加后检查缓存大小
                stats = cache.get_stats()
                assert stats["icon_cache_size"] <= cache_size, \
                    f"Cache size {stats['icon_cache_size']} exceeds max {cache_size}"
        finally:
            cache.MAX_ICON_CACHE = original_max

    @settings(max_examples=50)
    @given(
        cache_size=st.integers(min_value=2, max_value=20),
        items_to_add=st.integers(min_value=1, max_value=50)
    )
    def test_thumbnail_cache_never_exceeds_max(self, cache_size, items_to_add):
        """Property 7: 缩略图缓存永不超过最大限制
        
        **Validates: Requirements 3.3, 8.2**
        
        For any number of items added, cache size should never exceed MAX_THUMBNAIL_CACHE.
        """
        cache = PixmapCacheManager.instance()
        original_max = cache.MAX_THUMBNAIL_CACHE
        cache.MAX_THUMBNAIL_CACHE = cache_size
        
        try:
            size = QSize(64, 64)
            
            for i in range(items_to_add):
                pixmap = create_test_pixmap()
                cache.cache_thumbnail(f"/path/thumb_{i}.png", size, pixmap)
                
                # 每次添加后检查缓存大小
                stats = cache.get_stats()
                assert stats["thumbnail_cache_size"] <= cache_size, \
                    f"Cache size {stats['thumbnail_cache_size']} exceeds max {cache_size}"
        finally:
            cache.MAX_THUMBNAIL_CACHE = original_max
