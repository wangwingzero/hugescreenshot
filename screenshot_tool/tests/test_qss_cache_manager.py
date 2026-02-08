# =====================================================
# QSS 缓存管理器测试 - QSS Cache Manager Tests
# =====================================================

"""
QSS 缓存管理器单元测试

Feature: extreme-performance-optimization
Requirements: 5.1, 5.2, 5.4

测试内容：
1. 单例模式正确性
2. 预编译样式表功能
3. 样式缓存功能
4. 缓存清除功能
"""

import pytest
from screenshot_tool.core.qss_cache_manager import QSSCacheManager


class TestQSSCacheManagerSingleton:
    """测试单例模式"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_instance_returns_same_object(self):
        """测试 instance() 返回相同对象"""
        instance1 = QSSCacheManager.instance()
        instance2 = QSSCacheManager.instance()
        
        assert instance1 is instance2
    
    def test_new_returns_same_object(self):
        """测试 __new__ 返回相同对象"""
        obj1 = QSSCacheManager()
        obj2 = QSSCacheManager()
        
        assert obj1 is obj2
    
    def test_instance_and_new_return_same_object(self):
        """测试 instance() 和 __new__ 返回相同对象"""
        instance = QSSCacheManager.instance()
        obj = QSSCacheManager()
        
        assert instance is obj


class TestCompiledStylesheet:
    """测试预编译样式表功能
    
    **Validates: Requirements 5.1**
    """
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_get_compiled_stylesheet_returns_string(self):
        """测试获取预编译样式表返回字符串"""
        manager = QSSCacheManager.instance()
        stylesheet = manager.get_compiled_stylesheet()
        
        assert isinstance(stylesheet, str)
        assert len(stylesheet) > 0
    
    def test_get_compiled_stylesheet_cached(self):
        """测试预编译样式表被缓存
        
        **Validates: Requirements 5.1** - 使用单一预编译样式表
        """
        manager = QSSCacheManager.instance()
        
        # 第一次调用
        stylesheet1 = manager.get_compiled_stylesheet()
        
        # 第二次调用应返回相同对象（缓存）
        stylesheet2 = manager.get_compiled_stylesheet()
        
        assert stylesheet1 is stylesheet2
    
    def test_compiled_stylesheet_contains_required_elements(self):
        """测试预编译样式表包含必要元素"""
        manager = QSSCacheManager.instance()
        stylesheet = manager.get_compiled_stylesheet()
        
        # 应包含基础样式
        assert "QMainWindow" in stylesheet
        assert "QWidget" in stylesheet
        assert "font-family" in stylesheet
    
    def test_compiled_stylesheet_uses_simple_selectors(self):
        """测试使用简单选择器
        
        **Validates: Requirements 5.5** - 使用简单选择器（类名）
        """
        manager = QSSCacheManager.instance()
        stylesheet = manager.get_compiled_stylesheet()
        
        # 不应包含复杂的后代选择器链（超过2层）
        # 简单检查：不应有超过2个空格分隔的选择器
        lines = stylesheet.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('/*') and not line.startswith('*'):
                # 跳过注释和空行
                if '{' in line:
                    selector = line.split('{')[0].strip()
                    # 计算选择器中的空格数（简单的复杂度检查）
                    # 允许 QScrollBar::handle:vertical 这样的伪元素
                    parts = selector.split()
                    # 过滤掉伪元素部分
                    non_pseudo_parts = [p for p in parts if not p.startswith(':')]
                    assert len(non_pseudo_parts) <= 3, f"选择器过于复杂: {selector}"


class TestStyleCaching:
    """测试样式缓存功能
    
    **Validates: Requirements 5.2, 5.4**
    """
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_get_cached_style_generates_on_miss(self):
        """测试缓存未命中时生成样式"""
        manager = QSSCacheManager.instance()
        call_count = 0
        
        def generator():
            nonlocal call_count
            call_count += 1
            return "QPushButton { color: red; }"
        
        style = manager.get_cached_style("test_button", generator)
        
        assert call_count == 1
        assert style == "QPushButton { color: red; }"
    
    def test_get_cached_style_returns_cached_on_hit(self):
        """测试缓存命中时返回缓存
        
        **Validates: Requirements 5.4** - 缓存解析结果
        """
        manager = QSSCacheManager.instance()
        call_count = 0
        
        def generator():
            nonlocal call_count
            call_count += 1
            return "QPushButton { color: blue; }"
        
        # 第一次调用
        style1 = manager.get_cached_style("test_button", generator)
        
        # 第二次调用应使用缓存
        style2 = manager.get_cached_style("test_button", generator)
        
        assert call_count == 1  # generator 只被调用一次
        assert style1 == style2
    
    def test_has_cached_style(self):
        """测试检查样式是否已缓存"""
        manager = QSSCacheManager.instance()
        
        assert not manager.has_cached_style("nonexistent")
        
        manager.get_cached_style("test_key", lambda: "test_style")
        
        assert manager.has_cached_style("test_key")
    
    def test_set_cached_style(self):
        """测试直接设置缓存样式"""
        manager = QSSCacheManager.instance()
        
        manager.set_cached_style("direct_key", "QLabel { color: green; }")
        
        assert manager.has_cached_style("direct_key")
        
        # 使用 get_cached_style 获取，generator 不应被调用
        call_count = 0
        def generator():
            nonlocal call_count
            call_count += 1
            return "different_style"
        
        style = manager.get_cached_style("direct_key", generator)
        
        assert call_count == 0
        assert style == "QLabel { color: green; }"
    
    def test_different_keys_cached_separately(self):
        """测试不同键分别缓存"""
        manager = QSSCacheManager.instance()
        
        style1 = manager.get_cached_style("key1", lambda: "style1")
        style2 = manager.get_cached_style("key2", lambda: "style2")
        
        assert style1 == "style1"
        assert style2 == "style2"
        assert manager.has_cached_style("key1")
        assert manager.has_cached_style("key2")


class TestCacheClear:
    """测试缓存清除功能"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_clear_cache_removes_all_styles(self):
        """测试清除缓存移除所有样式"""
        manager = QSSCacheManager.instance()
        
        # 添加一些缓存
        manager.get_cached_style("key1", lambda: "style1")
        manager.get_cached_style("key2", lambda: "style2")
        manager.get_compiled_stylesheet()
        
        # 清除缓存
        manager.clear_cache()
        
        assert not manager.has_cached_style("key1")
        assert not manager.has_cached_style("key2")
    
    def test_clear_cache_resets_compiled_stylesheet(self):
        """测试清除缓存重置预编译样式表"""
        manager = QSSCacheManager.instance()
        
        # 获取预编译样式表
        stylesheet1 = manager.get_compiled_stylesheet()
        
        # 清除缓存
        manager.clear_cache()
        
        # 再次获取应重新编译
        stylesheet2 = manager.get_compiled_stylesheet()
        
        # 内容应相同，但是新生成的对象
        assert stylesheet1 == stylesheet2
        # 注意：由于字符串驻留，可能是同一对象，这里只验证功能正确
    
    def test_clear_cache_allows_regeneration(self):
        """测试清除缓存后可重新生成"""
        manager = QSSCacheManager.instance()
        
        call_count = 0
        def generator():
            nonlocal call_count
            call_count += 1
            return f"style_{call_count}"
        
        # 第一次生成
        style1 = manager.get_cached_style("test", generator)
        assert style1 == "style_1"
        
        # 清除缓存
        manager.clear_cache()
        
        # 第二次生成（应调用 generator）
        style2 = manager.get_cached_style("test", generator)
        assert style2 == "style_2"
        assert call_count == 2


class TestCacheStats:
    """测试缓存统计功能"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_get_cache_stats_initial(self):
        """测试初始缓存统计"""
        manager = QSSCacheManager.instance()
        stats = manager.get_cache_stats()
        
        assert stats["cached_styles_count"] == 0
        assert stats["has_compiled_stylesheet"] is False
    
    def test_get_cache_stats_after_caching(self):
        """测试缓存后的统计"""
        manager = QSSCacheManager.instance()
        
        manager.get_cached_style("key1", lambda: "style1")
        manager.get_cached_style("key2", lambda: "style2")
        manager.get_compiled_stylesheet()
        
        stats = manager.get_cache_stats()
        
        assert stats["cached_styles_count"] == 2
        assert stats["has_compiled_stylesheet"] is True
    
    def test_get_cache_stats_after_clear(self):
        """测试清除后的统计"""
        manager = QSSCacheManager.instance()
        
        manager.get_cached_style("key1", lambda: "style1")
        manager.get_compiled_stylesheet()
        manager.clear_cache()
        
        stats = manager.get_cache_stats()
        
        assert stats["cached_styles_count"] == 0
        assert stats["has_compiled_stylesheet"] is False


class TestPreloadCommonStyles:
    """测试预加载常用样式功能"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_preload_common_styles(self):
        """测试预加载常用样式"""
        manager = QSSCacheManager.instance()
        
        # 预加载前
        assert not manager.has_cached_style("button_primary")
        
        # 预加载
        manager.preload_common_styles()
        
        # 预加载后
        assert manager.has_cached_style("button_primary")
        assert manager.has_cached_style("button_secondary")
        assert manager.has_cached_style("input")
        assert manager.has_cached_style("checkbox")
        assert manager.has_cached_style("text_area")
    
    def test_preload_styles_are_valid_qss(self):
        """测试预加载的样式是有效的 QSS"""
        manager = QSSCacheManager.instance()
        manager.preload_common_styles()
        
        # 获取预加载的样式
        button_style = manager.get_cached_style("button_primary", lambda: "")
        
        # 应包含 QPushButton 选择器
        assert "QPushButton" in button_style
        assert "{" in button_style
        assert "}" in button_style


class TestNoRuntimeDynamicGeneration:
    """测试避免运行时动态生成
    
    **Validates: Requirements 5.2** - 避免运行时动态 QSS 生成
    """
    
    def setup_method(self):
        """每个测试前重置单例"""
        QSSCacheManager._instance = None
        QSSCacheManager._cache = {}
        QSSCacheManager._compiled_stylesheet = None
    
    def test_cached_style_avoids_regeneration(self):
        """测试缓存样式避免重新生成"""
        manager = QSSCacheManager.instance()
        
        generation_times = []
        import time
        
        def slow_generator():
            start = time.perf_counter()
            # 模拟复杂的样式生成
            result = "QPushButton { " + " ".join([f"prop{i}: value{i};" for i in range(100)]) + " }"
            generation_times.append(time.perf_counter() - start)
            return result
        
        # 第一次调用（生成）
        manager.get_cached_style("slow_style", slow_generator)
        
        # 多次调用（应使用缓存）
        for _ in range(100):
            manager.get_cached_style("slow_style", slow_generator)
        
        # generator 只应被调用一次
        assert len(generation_times) == 1
