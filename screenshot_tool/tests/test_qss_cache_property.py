# =====================================================
# QSS 缓存属性测试 - QSS Cache Property Tests
# =====================================================

"""
QSS 缓存属性测试

Feature: extreme-performance-optimization
Property 10: QSS Caching and Single Stylesheet

**Validates: Requirements 5.1, 5.2, 5.4**

属性测试验证：
1. 样式从缓存获取（后续调用返回缓存实例）
2. 生成器函数只被调用一次
3. 使用单一预编译样式表

Requirements:
- 5.1: 预编译全局样式表
- 5.2: 样式缓存
- 5.4: 单一样式表应用
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from screenshot_tool.core.qss_cache_manager import QSSCacheManager


def reset_qss_cache_manager():
    """完全重置 QSSCacheManager 单例状态
    
    由于 QSSCacheManager 使用类级别属性，需要在每个测试前完全重置。
    """
    QSSCacheManager._instance = None
    QSSCacheManager._cache = {}
    QSSCacheManager._compiled_stylesheet = None


# =====================================================
# 测试策略定义 - Test Strategies
# =====================================================

# 有效的缓存键策略：使用简单的 ASCII 字符串避免编码问题
cache_key_strategy = st.text(
    alphabet='abcdefghijklmnopqrstuvwxyz0123456789_-',
    min_size=1,
    max_size=30
).filter(lambda x: x.strip() != '')

# 有效的 QSS 样式策略：生成简单的 QSS 样式字符串
qss_style_strategy = st.builds(
    lambda selector, prop, value: f"{selector} {{ {prop}: {value}; }}",
    selector=st.sampled_from(['QPushButton', 'QLabel', 'QWidget', 'QLineEdit', 'QComboBox']),
    prop=st.sampled_from(['color', 'background-color', 'border', 'padding', 'margin']),
    value=st.sampled_from(['#FFFFFF', '#000000', '#2563EB', 'none', '8px', '16px'])
)

# 多个缓存键策略
multiple_keys_strategy = st.lists(
    cache_key_strategy,
    min_size=1,
    max_size=20,
    unique=True
)


# =====================================================
# Property 10: QSS Caching and Single Stylesheet
# =====================================================

class TestQSSCachingProperty:
    """Property 10: QSS Caching and Single Stylesheet
    
    **Validates: Requirements 5.1, 5.2, 5.4**
    
    For any style application operation, the QSS SHALL be retrieved from cache
    (QSSCacheManager), and the application SHALL use a single pre-compiled
    global stylesheet instead of per-widget styles.
    """
    
    @settings(max_examples=100)
    @given(key=cache_key_strategy, style=qss_style_strategy)
    def test_style_retrieved_from_cache_on_subsequent_calls(self, key: str, style: str):
        """Property 10.1: 样式从缓存获取
        
        **Validates: Requirements 5.2, 5.4**
        
        For any cache key and style, subsequent calls to get_cached_style
        SHALL return the cached instance without calling the generator.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        call_count = 0
        
        def generator():
            nonlocal call_count
            call_count += 1
            return style
        
        # 第一次调用 - 应调用 generator
        result1 = manager.get_cached_style(key, generator)
        first_call_count = call_count
        
        # 后续调用 - 应从缓存获取，不调用 generator
        for _ in range(10):
            result = manager.get_cached_style(key, generator)
            assert result == result1, "缓存返回的样式应与首次相同"
        
        # 验证 generator 只被调用一次
        assert call_count == first_call_count == 1, \
            f"Generator 应只被调用一次，实际调用 {call_count} 次"
    
    @settings(max_examples=100)
    @given(key=cache_key_strategy, style=qss_style_strategy)
    def test_generator_called_only_once_per_key(self, key: str, style: str):
        """Property 10.2: 生成器函数只被调用一次
        
        **Validates: Requirements 5.2**
        
        For any cache key, the generator function SHALL be called exactly once,
        regardless of how many times get_cached_style is called.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        call_count = 0
        
        def counting_generator():
            nonlocal call_count
            call_count += 1
            return style
        
        # 多次调用
        num_calls = 50
        for _ in range(num_calls):
            manager.get_cached_style(key, counting_generator)
        
        # 验证 generator 只被调用一次
        assert call_count == 1, \
            f"Generator 应只被调用一次，实际调用 {call_count} 次（共 {num_calls} 次 get_cached_style 调用）"
    
    @settings(max_examples=100)
    @given(keys=multiple_keys_strategy)
    def test_different_keys_cached_independently(self, keys: list):
        """Property 10.3: 不同键独立缓存
        
        **Validates: Requirements 5.2, 5.4**
        
        For any set of distinct cache keys, each key SHALL have its own
        independent cache entry, and accessing one key SHALL NOT affect others.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        call_counts = {key: 0 for key in keys}
        
        def make_generator(key):
            def generator():
                call_counts[key] += 1
                return f"style_for_{key}"
            return generator
        
        # 为每个键创建缓存
        for key in keys:
            manager.get_cached_style(key, make_generator(key))
        
        # 验证每个 generator 只被调用一次
        for key in keys:
            assert call_counts[key] == 1, \
                f"Key '{key}' 的 generator 应只被调用一次，实际调用 {call_counts[key]} 次"
        
        # 再次访问所有键，验证不会再调用 generator
        for key in keys:
            manager.get_cached_style(key, make_generator(key))
        
        for key in keys:
            assert call_counts[key] == 1, \
                f"Key '{key}' 的 generator 在第二次访问时不应被调用"
    
    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=100))
    def test_compiled_stylesheet_is_singleton(self, num_calls: int):
        """Property 10.4: 单一预编译样式表
        
        **Validates: Requirements 5.1**
        
        For any number of calls to get_compiled_stylesheet, the same
        pre-compiled stylesheet instance SHALL be returned.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        # 获取第一个样式表
        first_stylesheet = manager.get_compiled_stylesheet()
        
        # 多次调用应返回相同实例
        for _ in range(num_calls):
            stylesheet = manager.get_compiled_stylesheet()
            assert stylesheet is first_stylesheet, \
                "get_compiled_stylesheet 应返回相同的预编译样式表实例"
    
    @settings(max_examples=50)
    @given(key=cache_key_strategy, style=qss_style_strategy)
    def test_cache_hit_returns_exact_same_object(self, key: str, style: str):
        """Property 10.5: 缓存命中返回完全相同的对象
        
        **Validates: Requirements 5.4**
        
        For any cached style, subsequent accesses SHALL return the exact
        same object (identity check), not just equal content.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        # 首次缓存
        result1 = manager.get_cached_style(key, lambda: style)
        
        # 后续访问应返回相同对象
        result2 = manager.get_cached_style(key, lambda: "different_style")
        
        # 使用 is 检查对象身份
        assert result1 is result2, \
            "缓存命中应返回完全相同的对象实例"
    
    @settings(max_examples=50)
    @given(keys=multiple_keys_strategy)
    def test_has_cached_style_reflects_cache_state(self, keys: list):
        """Property 10.6: has_cached_style 正确反映缓存状态
        
        **Validates: Requirements 5.2**
        
        For any key, has_cached_style SHALL return True if and only if
        the key has been cached.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        # 初始状态：所有键都不在缓存中
        for key in keys:
            assert not manager.has_cached_style(key), \
                f"Key '{key}' 不应在初始缓存中"
        
        # 缓存一半的键
        cached_keys = keys[:len(keys)//2 + 1]
        for key in cached_keys:
            manager.get_cached_style(key, lambda k=key: f"style_{k}")
        
        # 验证缓存状态
        for key in keys:
            expected = key in cached_keys
            actual = manager.has_cached_style(key)
            assert actual == expected, \
                f"Key '{key}' 的缓存状态应为 {expected}，实际为 {actual}"


class TestQSSCachePerformanceProperty:
    """QSS 缓存性能属性测试
    
    **Validates: Requirements 5.2**
    
    验证缓存机制的性能特性。
    """
    
    @settings(max_examples=50)
    @given(num_styles=st.integers(min_value=1, max_value=100))
    def test_cache_avoids_redundant_generation(self, num_styles: int):
        """Property 10.7: 缓存避免冗余生成
        
        **Validates: Requirements 5.2**
        
        For any number of cached styles, the total number of generator
        calls SHALL equal the number of unique keys, not the number of
        get_cached_style calls.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        total_generator_calls = 0
        
        def counting_generator(key):
            nonlocal total_generator_calls
            total_generator_calls += 1
            return f"style_{key}"
        
        # 创建 num_styles 个唯一键
        keys = [f"key_{i}" for i in range(num_styles)]
        
        # 每个键访问多次
        for _ in range(5):
            for key in keys:
                manager.get_cached_style(key, lambda k=key: counting_generator(k))
        
        # 验证 generator 调用次数等于唯一键数量
        assert total_generator_calls == num_styles, \
            f"Generator 调用次数应为 {num_styles}，实际为 {total_generator_calls}"
    
    @settings(max_examples=50)
    @given(key=cache_key_strategy)
    def test_clear_cache_allows_regeneration(self, key: str):
        """Property 10.8: 清除缓存后允许重新生成
        
        **Validates: Requirements 5.2**
        
        After clear_cache is called, subsequent get_cached_style calls
        SHALL call the generator again.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        call_count = 0
        
        def generator():
            nonlocal call_count
            call_count += 1
            return f"style_v{call_count}"
        
        # 首次缓存
        result1 = manager.get_cached_style(key, generator)
        assert call_count == 1
        
        # 清除缓存
        manager.clear_cache()
        
        # 再次访问应重新生成
        result2 = manager.get_cached_style(key, generator)
        assert call_count == 2, \
            "清除缓存后应重新调用 generator"
        assert result1 != result2, \
            "清除缓存后应生成新的样式"


class TestSingleStylesheetProperty:
    """单一样式表属性测试
    
    **Validates: Requirements 5.1, 5.4**
    
    验证应用使用单一预编译样式表。
    """
    
    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=50))
    def test_compiled_stylesheet_compiled_once(self, num_accesses: int):
        """Property 10.9: 预编译样式表只编译一次
        
        **Validates: Requirements 5.1**
        
        For any number of accesses, the stylesheet SHALL be compiled
        exactly once (lazy initialization).
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        # 验证初始状态
        stats_before = manager.get_cache_stats()
        assert not stats_before["has_compiled_stylesheet"], \
            "初始状态不应有预编译样式表"
        
        # 多次访问
        stylesheets = []
        for _ in range(num_accesses):
            stylesheets.append(manager.get_compiled_stylesheet())
        
        # 验证所有返回值相同
        first = stylesheets[0]
        for ss in stylesheets[1:]:
            assert ss is first, \
                "所有 get_compiled_stylesheet 调用应返回相同实例"
        
        # 验证已编译状态
        stats_after = manager.get_cache_stats()
        assert stats_after["has_compiled_stylesheet"], \
            "访问后应有预编译样式表"
    
    def test_compiled_stylesheet_contains_global_styles(self):
        """Property 10.10: 预编译样式表包含全局样式
        
        **Validates: Requirements 5.1**
        
        The compiled stylesheet SHALL contain essential global styles
        (QMainWindow, QWidget, scrollbar, menu).
        """
        # 重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        stylesheet = manager.get_compiled_stylesheet()
        
        # 验证包含必要的全局样式
        required_elements = [
            "QMainWindow",
            "QWidget",
            "font-family",
        ]
        
        for element in required_elements:
            assert element in stylesheet, \
                f"预编译样式表应包含 '{element}'"
    
    @settings(max_examples=50)
    @given(st.booleans())
    def test_clear_cache_resets_compiled_stylesheet(self, access_before_clear: bool):
        """Property 10.11: 清除缓存重置预编译样式表
        
        **Validates: Requirements 5.1**
        
        After clear_cache, the compiled stylesheet SHALL be regenerated
        on next access.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        if access_before_clear:
            # 先访问一次
            manager.get_compiled_stylesheet()
        
        # 清除缓存
        manager.clear_cache()
        
        # 验证已重置
        stats = manager.get_cache_stats()
        assert not stats["has_compiled_stylesheet"], \
            "清除缓存后不应有预编译样式表"
        
        # 再次访问应重新编译
        stylesheet = manager.get_compiled_stylesheet()
        assert stylesheet is not None
        assert len(stylesheet) > 0


class TestCacheStatsProperty:
    """缓存统计属性测试
    
    **Validates: Requirements 5.2**
    """
    
    @settings(max_examples=50)
    @given(keys=multiple_keys_strategy)
    def test_cache_stats_count_matches_cached_keys(self, keys: list):
        """Property 10.12: 缓存统计计数匹配缓存键数量
        
        **Validates: Requirements 5.2**
        
        The cached_styles_count in stats SHALL equal the number of
        unique keys that have been cached.
        """
        # 每个 hypothesis 示例前重置状态
        reset_qss_cache_manager()
        
        manager = QSSCacheManager.instance()
        
        # 初始状态
        stats = manager.get_cache_stats()
        assert stats["cached_styles_count"] == 0
        
        # 逐个添加缓存
        for i, key in enumerate(keys):
            manager.get_cached_style(key, lambda k=key: f"style_{k}")
            stats = manager.get_cache_stats()
            assert stats["cached_styles_count"] == i + 1, \
                f"缓存 {i + 1} 个键后，统计应为 {i + 1}，实际为 {stats['cached_styles_count']}"
