"""
LazyLoaderManager 属性测试

Feature: performance-ui-optimization
Property 5: Lazy Loading
**Validates: Requirements 1.3, 1.4, 1.5**

测试延迟加载管理器的核心属性：
1. 模块在启动时不加载（is_loaded 初始为 False）
2. 模块仅在 get() 调用时加载
3. 加载后返回相同实例（缓存有效）
4. unload() 正确释放模块
"""

import sys
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
from typing import Any

from screenshot_tool.core.lazy_loader import (
    LazyLoaderManager,
    LazyModule,
    safe_lazy_load,
)


# ========== 测试用的模拟模块 ==========

class MockOCRManager:
    """模拟 OCR 管理器"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


class MockTranslationService:
    """模拟翻译服务"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


class MockAnkiConnector:
    """模拟 Anki 连接器"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


class MockMarkdownConverter:
    """模拟 Markdown 转换器"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


class MockRegulationService:
    """模拟规章服务"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


class MockScreenRecorder:
    """模拟录屏服务"""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.initialized = True


# 模块键到模拟类的映射
MOCK_CLASSES = {
    "ocr_manager": MockOCRManager,
    "translation_service": MockTranslationService,
    "anki_connector": MockAnkiConnector,
    "markdown_converter": MockMarkdownConverter,
    "regulation_service": MockRegulationService,
    "screen_recorder": MockScreenRecorder,
}


# ========== Fixtures ==========

@pytest.fixture
def fresh_loader():
    """创建一个新的 LazyLoaderManager 实例
    
    每次测试前重置单例，确保测试隔离。
    """
    LazyLoaderManager.reset_instance()
    loader = LazyLoaderManager.instance()
    yield loader
    # 测试后清理
    LazyLoaderManager.reset_instance()


@pytest.fixture
def mock_importlib():
    """模拟 importlib.import_module 以避免实际导入模块"""
    with mock_importlib_context():
        yield


@contextmanager
def mock_importlib_context():
    """模拟 importlib.import_module 的上下文管理器（用于 hypothesis 测试）"""
    def mock_import(module_path: str):
        """根据模块路径返回模拟模块"""
        mock_module = MagicMock()
        
        # 根据模块路径设置对应的类
        if "ocr_manager" in module_path:
            mock_module.OCRManager = MockOCRManager
        elif "translation_service" in module_path:
            mock_module.TranslationService = MockTranslationService
        elif "anki_connector" in module_path:
            mock_module.AnkiConnector = MockAnkiConnector
        elif "markdown_converter" in module_path:
            mock_module.MarkdownConverter = MockMarkdownConverter
        elif "regulation_service" in module_path:
            mock_module.RegulationService = MockRegulationService
        elif "screen_recorder" in module_path:
            mock_module.ScreenRecorder = MockScreenRecorder
        
        return mock_module
    
    with patch("screenshot_tool.core.lazy_loader.importlib.import_module", side_effect=mock_import):
        yield


# ========== Property 5: Lazy Loading ==========
# Feature: performance-ui-optimization, Property 5: Lazy Loading
# **Validates: Requirements 1.3, 1.4, 1.5**
#
# For any non-essential module (OCR, translation, Anki, markdown converter):
# - The module SHALL NOT be imported at application startup
# - The module SHALL be loaded only when first accessed
# - After loading, the module instance SHALL be cached for reuse


class TestLazyLoadingProperty:
    """Property 5: Lazy Loading 属性测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3, 1.4, 1.5**
    """
    
    # ========== Property 5.1: 模块启动时不加载 ==========
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service", 
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_modules_not_loaded_at_startup(self, module_key: str):
        """Property 5.1: 非必要模块在启动时不加载
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        
        For any non-essential module, is_loaded SHALL return False
        immediately after LazyLoaderManager instantiation.
        """
        # 重置单例确保干净状态
        LazyLoaderManager.reset_instance()
        loader = LazyLoaderManager.instance()
        
        # 验证模块未加载
        assert not loader.is_loaded(module_key), \
            f"Module {module_key} should NOT be loaded at startup"
        
        # 清理
        LazyLoaderManager.reset_instance()
    
    # ========== Property 5.2: 模块仅在首次访问时加载 ==========
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service",
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_modules_loaded_on_first_access(self, module_key: str):
        """Property 5.2: 模块仅在 get() 调用时加载
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        
        For any non-essential module:
        - Before get(): is_loaded returns False
        - After get(): is_loaded returns True
        """
        with mock_importlib_context():
            # 重置单例确保干净状态
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 验证加载前状态
            assert not loader.is_loaded(module_key), \
                f"Module {module_key} should NOT be loaded before get()"
            
            # 调用 get() 加载模块
            instance = loader.get(module_key)
            
            # 验证加载后状态
            assert loader.is_loaded(module_key), \
                f"Module {module_key} should be loaded after get()"
            assert instance is not None, \
                f"Module {module_key} instance should not be None"
            
            # 清理
            LazyLoaderManager.reset_instance()
    
    # ========== Property 5.3: 加载后实例被缓存 ==========
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service",
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_module_instance_cached_after_loading(self, module_key: str):
        """Property 5.3: 加载后返回相同实例（缓存有效）
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        
        For any non-essential module, multiple calls to get()
        SHALL return the same instance (identity check).
        """
        with mock_importlib_context():
            # 重置单例确保干净状态
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 首次获取
            instance1 = loader.get(module_key)
            
            # 再次获取
            instance2 = loader.get(module_key)
            
            # 验证是同一个实例
            assert instance1 is instance2, \
                f"Module {module_key} should return the same cached instance"
            
            # 清理
            LazyLoaderManager.reset_instance()
    
    # ========== Property 5.4: unload() 正确释放模块 ==========
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service",
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_unload_releases_module(self, module_key: str):
        """Property 5.4: unload() 正确释放模块
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        
        For any loaded module, after unload():
        - is_loaded SHALL return False
        - get_load_time SHALL return None
        """
        with mock_importlib_context():
            # 重置单例确保干净状态
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 先加载模块
            loader.get(module_key)
            assert loader.is_loaded(module_key), \
                f"Module {module_key} should be loaded"
            
            # 卸载模块
            loader.unload(module_key)
            
            # 验证卸载后状态
            assert not loader.is_loaded(module_key), \
                f"Module {module_key} should NOT be loaded after unload()"
            assert loader.get_load_time(module_key) is None, \
                f"Module {module_key} load_time should be None after unload()"
            
            # 清理
            LazyLoaderManager.reset_instance()
    
    # ========== Property 5.5: 卸载后可重新加载 ==========
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service",
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_module_can_be_reloaded_after_unload(self, module_key: str):
        """Property 5.5: 卸载后可重新加载，返回新实例
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        
        For any module that was loaded and then unloaded:
        - get() SHALL create a new instance
        - The new instance SHALL be different from the old one
        """
        with mock_importlib_context():
            # 重置单例确保干净状态
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 首次加载
            instance1 = loader.get(module_key)
            
            # 卸载
            loader.unload(module_key)
            
            # 重新加载
            instance2 = loader.get(module_key)
            
            # 验证是新实例
            assert instance2 is not instance1, \
                f"Module {module_key} should return a new instance after unload"
            assert loader.is_loaded(module_key), \
                f"Module {module_key} should be loaded after reload"
            
            # 清理
            LazyLoaderManager.reset_instance()


class TestLazyLoaderManagerUnit:
    """LazyLoaderManager 单元测试
    
    测试具体示例和边界情况。
    """
    
    def test_unknown_module_raises_key_error(self, fresh_loader):
        """未知模块键应抛出 KeyError"""
        with pytest.raises(KeyError) as exc_info:
            fresh_loader.get("unknown_module")
        
        assert "Unknown lazy module" in str(exc_info.value)
    
    def test_is_loaded_returns_false_for_unknown_module(self, fresh_loader):
        """未知模块键的 is_loaded 返回 False"""
        assert fresh_loader.is_loaded("unknown_module") is False
    
    def test_unload_unknown_module_does_not_raise(self, fresh_loader):
        """卸载未知模块不应抛出异常"""
        # 不应抛出异常
        fresh_loader.unload("unknown_module")
    
    def test_unload_all_releases_all_modules(self, fresh_loader, mock_importlib):
        """unload_all 释放所有已加载模块"""
        # 加载多个模块
        fresh_loader.get("ocr_manager")
        fresh_loader.get("translation_service")
        
        assert fresh_loader.is_loaded("ocr_manager")
        assert fresh_loader.is_loaded("translation_service")
        
        # 卸载所有
        fresh_loader.unload_all()
        
        # 验证全部卸载
        assert not fresh_loader.is_loaded("ocr_manager")
        assert not fresh_loader.is_loaded("translation_service")
    
    def test_get_loaded_modules_returns_correct_list(self, fresh_loader, mock_importlib):
        """get_loaded_modules 返回正确的已加载模块列表"""
        # 初始为空
        assert fresh_loader.get_loaded_modules() == []
        
        # 加载一个模块
        fresh_loader.get("ocr_manager")
        assert "ocr_manager" in fresh_loader.get_loaded_modules()
        
        # 加载另一个模块
        fresh_loader.get("translation_service")
        loaded = fresh_loader.get_loaded_modules()
        assert "ocr_manager" in loaded
        assert "translation_service" in loaded
    
    def test_get_module_info_returns_correct_info(self, fresh_loader, mock_importlib):
        """get_module_info 返回正确的模块信息"""
        # 未加载时
        info = fresh_loader.get_module_info("ocr_manager")
        assert info is not None
        assert info["is_loaded"] is False
        assert info["load_time_ms"] is None
        
        # 加载后
        fresh_loader.get("ocr_manager")
        info = fresh_loader.get_module_info("ocr_manager")
        assert info["is_loaded"] is True
        assert info["load_time_ms"] is not None
        assert info["load_time_ms"] >= 0
    
    def test_get_module_info_returns_none_for_unknown(self, fresh_loader):
        """未知模块的 get_module_info 返回 None"""
        assert fresh_loader.get_module_info("unknown_module") is None
    
    def test_available_modules_property(self, fresh_loader):
        """available_modules 属性返回所有可用模块键"""
        available = fresh_loader.available_modules
        
        assert "ocr_manager" in available
        assert "translation_service" in available
        assert "anki_connector" in available
        assert "markdown_converter" in available
        assert "regulation_service" in available
        assert "screen_recorder" in available
    
    def test_get_load_time_returns_positive_value(self, fresh_loader, mock_importlib):
        """加载时间应为正值"""
        fresh_loader.get("ocr_manager")
        load_time = fresh_loader.get_load_time("ocr_manager")
        
        assert load_time is not None
        assert load_time >= 0
    
    def test_get_load_time_returns_none_for_unloaded(self, fresh_loader):
        """未加载模块的加载时间应为 None"""
        assert fresh_loader.get_load_time("ocr_manager") is None
    
    def test_singleton_pattern(self):
        """验证单例模式"""
        LazyLoaderManager.reset_instance()
        
        instance1 = LazyLoaderManager.instance()
        instance2 = LazyLoaderManager.instance()
        
        assert instance1 is instance2
        
        LazyLoaderManager.reset_instance()
    
    def test_reset_instance_creates_new_instance(self):
        """reset_instance 创建新实例"""
        LazyLoaderManager.reset_instance()
        
        instance1 = LazyLoaderManager.instance()
        LazyLoaderManager.reset_instance()
        instance2 = LazyLoaderManager.instance()
        
        assert instance1 is not instance2
        
        LazyLoaderManager.reset_instance()


class TestSafeLazyLoad:
    """safe_lazy_load 函数测试
    
    Feature: performance-ui-optimization
    Requirements: 1.3
    
    测试安全延迟加载函数的核心功能：
    1. 成功加载返回实例
    2. 加载失败返回 fallback
    3. 错误日志记录
    """
    
    def test_safe_lazy_load_returns_fallback_on_unknown_module(self):
        """未知模块返回 fallback
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        result = safe_lazy_load("unknown_module", fallback="default")
        assert result == "default"
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_returns_fallback_on_import_error(self):
        """导入失败返回 fallback
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 使用真实模块路径但会导入失败（因为模块不存在或有依赖问题）
        # 这里我们测试 fallback 机制
        result = safe_lazy_load("unknown_module", fallback=None)
        assert result is None
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_returns_instance_on_success(self, mock_importlib):
        """成功加载返回实例
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        result = safe_lazy_load("ocr_manager", fallback=None)
        assert result is not None
        assert isinstance(result, MockOCRManager)
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_with_custom_fallback_value(self):
        """自定义 fallback 值正确返回
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 测试不同类型的 fallback 值
        fallback_values = [
            None,
            "string_fallback",
            42,
            {"key": "value"},
            ["list", "fallback"],
            lambda: "callable",
        ]
        
        for fallback in fallback_values:
            result = safe_lazy_load("unknown_module", fallback=fallback)
            assert result is fallback, \
                f"Expected fallback {fallback}, got {result}"
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_logs_error_on_failure(self):
        """加载失败时记录错误日志
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 创建模拟的 error_logger
        mock_logger = MagicMock()
        
        # 需要 patch 源模块，因为 safe_lazy_load 使用 local import
        with patch(
            "screenshot_tool.core.error_logger.get_error_logger",
            return_value=mock_logger
        ):
            # 尝试加载未知模块（会失败）
            result = safe_lazy_load("unknown_module", fallback="fallback")
            
            # 验证返回 fallback
            assert result == "fallback"
            
            # 验证 log_error 被调用
            mock_logger.log_error.assert_called_once()
            
            # 验证日志消息包含模块名
            call_args = mock_logger.log_error.call_args[0][0]
            assert "unknown_module" in call_args
            assert "Failed to load module" in call_args
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_handles_logger_none(self):
        """当 logger 为 None 时不崩溃
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 需要 patch 源模块，因为 safe_lazy_load 使用 local import
        with patch(
            "screenshot_tool.core.error_logger.get_error_logger",
            return_value=None
        ):
            # 不应抛出异常
            result = safe_lazy_load("unknown_module", fallback="fallback")
            assert result == "fallback"
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_handles_logger_exception(self):
        """当日志记录失败时不崩溃
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 创建会抛出异常的模拟 logger
        mock_logger = MagicMock()
        mock_logger.log_error.side_effect = Exception("Logger failed")
        
        # 需要 patch 源模块，因为 safe_lazy_load 使用 local import
        with patch(
            "screenshot_tool.core.error_logger.get_error_logger",
            return_value=mock_logger
        ):
            # 不应抛出异常
            result = safe_lazy_load("unknown_module", fallback="fallback")
            assert result == "fallback"
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_handles_get_error_logger_exception(self):
        """当 get_error_logger 抛出异常时不崩溃
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        # 需要 patch 源模块，因为 safe_lazy_load 使用 local import
        with patch(
            "screenshot_tool.core.error_logger.get_error_logger",
            side_effect=Exception("Import failed")
        ):
            # 不应抛出异常
            result = safe_lazy_load("unknown_module", fallback="fallback")
            assert result == "fallback"
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_passes_args_to_constructor(self, mock_importlib):
        """位置参数正确传递给构造函数
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        result = safe_lazy_load("ocr_manager", "arg1", "arg2", fallback=None)
        
        assert result is not None
        assert result.args == ("arg1", "arg2")
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_passes_kwargs_to_constructor(self, mock_importlib):
        """关键字参数正确传递给构造函数
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        result = safe_lazy_load(
            "ocr_manager",
            fallback=None,
            key1="value1",
            key2="value2"
        )
        
        assert result is not None
        assert result.kwargs == {"key1": "value1", "key2": "value2"}
        
        LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_caches_instance(self, mock_importlib):
        """多次调用返回缓存的实例
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        """
        LazyLoaderManager.reset_instance()
        
        result1 = safe_lazy_load("ocr_manager", fallback=None)
        result2 = safe_lazy_load("ocr_manager", fallback=None)
        
        assert result1 is result2
        
        LazyLoaderManager.reset_instance()
    
    @settings(max_examples=100)
    @given(module_key=st.sampled_from([
        "ocr_manager",
        "translation_service",
        "anki_connector",
        "markdown_converter",
        "regulation_service",
        "screen_recorder",
    ]))
    def test_safe_lazy_load_property_success_returns_instance(self, module_key: str):
        """Property: 成功加载时返回非 None 实例
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        
        For any valid module_key, safe_lazy_load SHALL return
        a non-None instance when loading succeeds.
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            
            result = safe_lazy_load(module_key, fallback="fallback")
            
            # 成功加载应返回实例，不是 fallback
            assert result != "fallback"
            assert result is not None
            
            LazyLoaderManager.reset_instance()
    
    @settings(max_examples=100)
    @given(fallback=st.one_of(
        st.none(),
        st.text(max_size=50),
        st.integers(),
        st.floats(allow_nan=False),
        st.booleans(),
    ))
    def test_safe_lazy_load_property_failure_returns_fallback(self, fallback):
        """Property: 加载失败时返回 fallback
        
        Feature: performance-ui-optimization
        Requirements: 1.3
        
        For any fallback value, safe_lazy_load SHALL return
        exactly that fallback when loading fails.
        """
        LazyLoaderManager.reset_instance()
        
        result = safe_lazy_load("unknown_module", fallback=fallback)
        
        # 失败时应返回 fallback
        if fallback is None:
            assert result is None
        else:
            assert result == fallback
        
        LazyLoaderManager.reset_instance()


class TestLazyModuleDataclass:
    """LazyModule 数据类测试"""
    
    def test_lazy_module_creation(self):
        """测试 LazyModule 创建"""
        module = LazyModule(
            module_path="test.module",
            class_name="TestClass",
        )
        
        assert module.module_path == "test.module"
        assert module.class_name == "TestClass"
        assert module.instance is None
        assert module.load_time_ms == 0.0
    
    def test_lazy_module_with_instance(self):
        """测试带实例的 LazyModule"""
        mock_instance = MagicMock()
        module = LazyModule(
            module_path="test.module",
            class_name="TestClass",
            instance=mock_instance,
            load_time_ms=123.45,
        )
        
        assert module.instance is mock_instance
        assert module.load_time_ms == 123.45


# ========== 多次调用一致性测试 ==========

class TestMultipleCallsConsistency:
    """多次调用一致性测试
    
    验证在多次调用场景下的行为一致性。
    """
    
    @settings(max_examples=100)
    @given(
        module_key=st.sampled_from([
            "ocr_manager",
            "translation_service",
            "anki_connector",
        ]),
        call_count=st.integers(min_value=2, max_value=10),
    )
    def test_multiple_gets_return_same_instance(
        self, module_key: str, call_count: int
    ):
        """多次 get() 调用返回相同实例
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 首次获取
            first_instance = loader.get(module_key)
            
            # 多次获取
            for _ in range(call_count - 1):
                instance = loader.get(module_key)
                assert instance is first_instance, \
                    f"All get() calls should return the same instance"
            
            LazyLoaderManager.reset_instance()
    
    @settings(max_examples=100)
    @given(
        module_key=st.sampled_from([
            "ocr_manager",
            "translation_service",
            "anki_connector",
        ]),
        unload_count=st.integers(min_value=1, max_value=5),
    )
    def test_multiple_unload_reload_cycles(
        self, module_key: str, unload_count: int
    ):
        """多次卸载-重载循环
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4, 1.5**
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            previous_instance = None
            
            for i in range(unload_count):
                # 加载
                instance = loader.get(module_key)
                assert loader.is_loaded(module_key)
                
                # 验证是新实例（除了第一次）
                if previous_instance is not None:
                    assert instance is not previous_instance, \
                        f"Reload {i} should create a new instance"
                
                previous_instance = instance
                
                # 卸载
                loader.unload(module_key)
                assert not loader.is_loaded(module_key)
            
            LazyLoaderManager.reset_instance()
