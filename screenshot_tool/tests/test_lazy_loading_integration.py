"""
延迟加载集成测试

Feature: performance-ui-optimization
Property 5: Lazy Loading
**Validates: Requirements 1.3, 1.4**

测试延迟加载机制在组件间的集成：
1. 启动时非必要模块未加载
2. 对话框首次访问时才创建
3. LazyLoaderManager 和 DialogFactory 协同工作
"""

import sys
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import MagicMock, patch, PropertyMock
from contextlib import contextmanager
from typing import Any, List, Set

from screenshot_tool.core.lazy_loader import (
    LazyLoaderManager,
    LazyModule,
    safe_lazy_load,
)
from screenshot_tool.ui.dialog_factory import DialogFactory, DialogIds


# ========== 测试用的模拟类 ==========

class MockOCRManager:
    """模拟 OCR 管理器"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockTranslationService:
    """模拟翻译服务"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockAnkiConnector:
    """模拟 Anki 连接器"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockMarkdownConverter:
    """模拟 Markdown 转换器"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockRegulationService:
    """模拟规章服务"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockScreenRecorder:
    """模拟录屏服务"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


class MockDingManager:
    """模拟贴图管理器"""
    def __init__(self, *args, **kwargs):
        self.initialized = True


# 模块键到模拟类的映射
MOCK_CLASSES = {
    "ocr_manager": MockOCRManager,
    "translation_service": MockTranslationService,
    "anki_connector": MockAnkiConnector,
    "markdown_converter": MockMarkdownConverter,
    "regulation_service": MockRegulationService,
    "screen_recorder": MockScreenRecorder,
    "ding_manager": MockDingManager,
}

# 非必要模块列表（启动时不应加载）
NON_ESSENTIAL_MODULES = [
    "ocr_manager",
    "translation_service",
    "anki_connector",
    "markdown_converter",
    "regulation_service",
    "screen_recorder",
    "ding_manager",
]


# ========== Fixtures ==========

@pytest.fixture(autouse=True)
def clean_state():
    """每个测试前后清理状态"""
    LazyLoaderManager.reset_instance()
    DialogFactory.clear()
    yield
    LazyLoaderManager.reset_instance()
    DialogFactory.clear()


@contextmanager
def mock_importlib_context():
    """模拟 importlib.import_module 的上下文管理器"""
    def mock_import(module_path: str):
        """根据模块路径返回模拟模块"""
        mock_module = MagicMock()
        
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
        elif "ding_window" in module_path:
            mock_module.DingManager = MockDingManager
        
        return mock_module
    
    with patch(
        "screenshot_tool.core.lazy_loader.importlib.import_module",
        side_effect=mock_import
    ):
        yield


# ========== Property 5: Lazy Loading - Integration Tests ==========


class TestLazyLoadingIntegrationProperty:
    """Property 5: Lazy Loading 集成属性测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3, 1.4**
    
    验证启动时非必要模块未加载，以及延迟加载机制的正确性。
    """
    
    # ========== Property 5.1: 启动时所有非必要模块未加载 ==========
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(module_keys=st.lists(
        st.sampled_from(NON_ESSENTIAL_MODULES),
        min_size=1,
        max_size=len(NON_ESSENTIAL_MODULES),
        unique=True
    ))
    def test_all_non_essential_modules_not_loaded_at_startup(
        self, module_keys: List[str]
    ):
        """Property 5.1: 启动时所有非必要模块未加载
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4**
        
        For any subset of non-essential modules, none SHALL be loaded
        immediately after LazyLoaderManager instantiation.
        """
        LazyLoaderManager.reset_instance()
        loader = LazyLoaderManager.instance()
        
        # 验证所有指定模块都未加载
        for module_key in module_keys:
            assert not loader.is_loaded(module_key), \
                f"Module {module_key} should NOT be loaded at startup"
        
        # 验证已加载模块列表为空
        loaded = loader.get_loaded_modules()
        for module_key in module_keys:
            assert module_key not in loaded, \
                f"Module {module_key} should NOT be in loaded modules list"
        
        LazyLoaderManager.reset_instance()

    
    # ========== Property 5.2: 模块仅在首次访问时加载 ==========
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        module_to_load=st.sampled_from(NON_ESSENTIAL_MODULES),
        other_modules=st.lists(
            st.sampled_from(NON_ESSENTIAL_MODULES),
            min_size=0,
            max_size=3,
            unique=True
        )
    )
    def test_only_accessed_module_is_loaded(
        self, module_to_load: str, other_modules: List[str]
    ):
        """Property 5.2: 仅访问的模块被加载，其他模块保持未加载
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4**
        
        When a specific module is accessed via get(), only that module
        SHALL be loaded. All other modules SHALL remain unloaded.
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 加载指定模块
            instance = loader.get(module_to_load)
            
            # 验证指定模块已加载
            assert loader.is_loaded(module_to_load), \
                f"Module {module_to_load} should be loaded after get()"
            assert instance is not None
            
            # 验证其他模块未加载
            for other_module in other_modules:
                if other_module != module_to_load:
                    assert not loader.is_loaded(other_module), \
                        f"Module {other_module} should NOT be loaded"
            
            LazyLoaderManager.reset_instance()

    
    # ========== Property 5.3: 对话框首次访问时才创建 ==========
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(dialog_ids=st.lists(
        st.sampled_from([
            DialogIds.SETTINGS,
            DialogIds.WEB_TO_MARKDOWN,
            DialogIds.FILE_TO_MARKDOWN,
            DialogIds.GONGWEN,
            DialogIds.REGULATION_SEARCH,
        ]),
        min_size=1,
        max_size=5,
        unique=True
    ))
    def test_dialogs_not_created_until_accessed(self, dialog_ids: List[str]):
        """Property 5.3: 对话框首次访问时才创建
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.4**
        
        For any registered dialog, it SHALL NOT be created until
        first accessed via get().
        """
        DialogFactory.clear()
        
        # 注册所有对话框
        creators = {}
        for dialog_id in dialog_ids:
            mock_dialog = MagicMock()
            creator = MagicMock(return_value=mock_dialog)
            creators[dialog_id] = creator
            DialogFactory.register(dialog_id, creator)
        
        # 验证注册后对话框未创建
        for dialog_id in dialog_ids:
            assert not DialogFactory.is_created(dialog_id), \
                f"Dialog {dialog_id} should NOT be created after registration"
            creators[dialog_id].assert_not_called()
        
        DialogFactory.clear()

    
    # ========== Property 5.4: 访问对话框时创建且缓存 ==========
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        dialog_to_access=st.sampled_from([
            DialogIds.SETTINGS,
            DialogIds.WEB_TO_MARKDOWN,
            DialogIds.FILE_TO_MARKDOWN,
        ]),
        access_count=st.integers(min_value=1, max_value=5)
    )
    def test_dialog_created_on_first_access_and_cached(
        self, dialog_to_access: str, access_count: int
    ):
        """Property 5.4: 对话框首次访问时创建并缓存
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.4**
        
        When a dialog is accessed:
        - It SHALL be created on first access
        - Subsequent accesses SHALL return the same cached instance
        - The creator function SHALL be called exactly once
        """
        DialogFactory.clear()
        
        mock_dialog = MagicMock()
        creator = MagicMock(return_value=mock_dialog)
        DialogFactory.register(dialog_to_access, creator)
        
        # 多次访问
        instances = []
        for _ in range(access_count):
            instance = DialogFactory.get(dialog_to_access)
            instances.append(instance)
        
        # 验证创建函数只调用一次
        creator.assert_called_once()
        
        # 验证所有返回的实例相同
        for instance in instances:
            assert instance is mock_dialog, \
                "All get() calls should return the same cached instance"
        
        # 验证对话框已创建
        assert DialogFactory.is_created(dialog_to_access)
        
        DialogFactory.clear()



class TestLazyLoadingCrossComponentIntegration:
    """跨组件集成测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3, 1.4**
    
    验证 LazyLoaderManager 和 DialogFactory 协同工作。
    """
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        modules_to_load=st.lists(
            st.sampled_from(NON_ESSENTIAL_MODULES),
            min_size=0,
            max_size=3,
            unique=True
        ),
        dialogs_to_access=st.lists(
            st.sampled_from([
                DialogIds.SETTINGS,
                DialogIds.WEB_TO_MARKDOWN,
                DialogIds.FILE_TO_MARKDOWN,
            ]),
            min_size=0,
            max_size=3,
            unique=True
        )
    )
    def test_lazy_loading_independence(
        self, modules_to_load: List[str], dialogs_to_access: List[str]
    ):
        """测试模块和对话框延迟加载的独立性
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4**
        
        Loading modules SHALL NOT affect dialog creation state.
        Accessing dialogs SHALL NOT affect module loading state.
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            DialogFactory.clear()
            
            loader = LazyLoaderManager.instance()
            
            # 注册对话框
            dialog_creators = {}
            for dialog_id in dialogs_to_access:
                mock_dialog = MagicMock()
                creator = MagicMock(return_value=mock_dialog)
                dialog_creators[dialog_id] = creator
                DialogFactory.register(dialog_id, creator)
            
            # 加载模块
            for module_key in modules_to_load:
                loader.get(module_key)
            
            # 验证只有指定模块被加载
            for module_key in NON_ESSENTIAL_MODULES:
                if module_key in modules_to_load:
                    assert loader.is_loaded(module_key)
                else:
                    assert not loader.is_loaded(module_key)
            
            # 验证对话框仍未创建
            for dialog_id in dialogs_to_access:
                assert not DialogFactory.is_created(dialog_id)
            
            # 访问对话框
            for dialog_id in dialogs_to_access:
                DialogFactory.get(dialog_id)
            
            # 验证对话框已创建
            for dialog_id in dialogs_to_access:
                assert DialogFactory.is_created(dialog_id)
            
            # 验证模块加载状态未变
            for module_key in NON_ESSENTIAL_MODULES:
                if module_key in modules_to_load:
                    assert loader.is_loaded(module_key)
                else:
                    assert not loader.is_loaded(module_key)
            
            LazyLoaderManager.reset_instance()
            DialogFactory.clear()



class TestStartupStateVerification:
    """启动状态验证测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3, 1.4**
    
    验证应用启动时的初始状态。
    """
    
    def test_fresh_loader_has_no_loaded_modules(self):
        """测试新创建的 LazyLoaderManager 没有已加载模块
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        LazyLoaderManager.reset_instance()
        loader = LazyLoaderManager.instance()
        
        # 验证没有已加载模块
        loaded_modules = loader.get_loaded_modules()
        assert len(loaded_modules) == 0, \
            f"Fresh loader should have no loaded modules, got: {loaded_modules}"
        
        # 验证所有非必要模块都未加载
        for module_key in NON_ESSENTIAL_MODULES:
            assert not loader.is_loaded(module_key), \
                f"Module {module_key} should not be loaded at startup"
        
        LazyLoaderManager.reset_instance()
    
    def test_fresh_factory_has_no_created_dialogs(self):
        """测试新创建的 DialogFactory 没有已创建对话框
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.4**
        """
        DialogFactory.clear()
        
        # 验证没有已创建对话框
        created_ids = DialogFactory.get_created_ids()
        assert len(created_ids) == 0, \
            f"Fresh factory should have no created dialogs, got: {created_ids}"
        
        # 验证统计信息
        stats = DialogFactory.get_stats()
        assert stats["created_count"] == 0
        
        DialogFactory.clear()

    
    def test_all_lazy_modules_are_defined(self):
        """测试所有预期的延迟加载模块都已定义
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        LazyLoaderManager.reset_instance()
        loader = LazyLoaderManager.instance()
        
        expected_modules = {
            "ocr_manager",
            "translation_service",
            "anki_connector",
            "markdown_converter",
            "regulation_service",
            "screen_recorder",
            "ding_manager",
        }
        
        available = set(loader.available_modules)
        
        # 验证所有预期模块都可用
        for module_key in expected_modules:
            assert module_key in available, \
                f"Expected module {module_key} should be available"
        
        LazyLoaderManager.reset_instance()
    
    def test_module_info_available_before_loading(self):
        """测试模块信息在加载前可用
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        LazyLoaderManager.reset_instance()
        loader = LazyLoaderManager.instance()
        
        for module_key in NON_ESSENTIAL_MODULES:
            info = loader.get_module_info(module_key)
            
            assert info is not None, \
                f"Module info for {module_key} should be available"
            assert info["is_loaded"] is False, \
                f"Module {module_key} should not be loaded"
            assert info["load_time_ms"] is None, \
                f"Module {module_key} load_time should be None"
            assert "module_path" in info
            assert "class_name" in info
        
        LazyLoaderManager.reset_instance()



class TestUnloadAndReloadIntegration:
    """卸载和重载集成测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3, 1.4**
    
    验证模块卸载和重载的正确性。
    """
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        modules_to_cycle=st.lists(
            st.sampled_from(NON_ESSENTIAL_MODULES),
            min_size=1,
            max_size=4,
            unique=True
        ),
        cycle_count=st.integers(min_value=1, max_value=3)
    )
    def test_module_unload_reload_cycle(
        self, modules_to_cycle: List[str], cycle_count: int
    ):
        """测试模块卸载-重载循环
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3, 1.4**
        
        For any module, after unload and reload:
        - A new instance SHALL be created
        - The module SHALL be marked as loaded
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            for _ in range(cycle_count):
                previous_instances = {}
                
                # 加载所有模块
                for module_key in modules_to_cycle:
                    instance = loader.get(module_key)
                    previous_instances[module_key] = instance
                    assert loader.is_loaded(module_key)
                
                # 卸载所有模块
                for module_key in modules_to_cycle:
                    loader.unload(module_key)
                    assert not loader.is_loaded(module_key)
                
                # 重新加载并验证是新实例
                for module_key in modules_to_cycle:
                    new_instance = loader.get(module_key)
                    assert loader.is_loaded(module_key)
                    assert new_instance is not previous_instances[module_key], \
                        f"Module {module_key} should have a new instance after reload"
            
            LazyLoaderManager.reset_instance()

    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        dialogs_to_cycle=st.lists(
            st.sampled_from([
                DialogIds.SETTINGS,
                DialogIds.WEB_TO_MARKDOWN,
                DialogIds.FILE_TO_MARKDOWN,
            ]),
            min_size=1,
            max_size=3,
            unique=True
        )
    )
    def test_dialog_destroy_recreate_cycle(self, dialogs_to_cycle: List[str]):
        """测试对话框销毁-重建循环
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.4**
        
        For any dialog, after destroy and recreate:
        - A new instance SHALL be created
        - The dialog SHALL be marked as created
        """
        DialogFactory.clear()
        
        # 为每个对话框创建计数器
        call_counts = {dialog_id: [0] for dialog_id in dialogs_to_cycle}
        dialog_instances = {dialog_id: [] for dialog_id in dialogs_to_cycle}
        
        def make_creator(dialog_id):
            def creator():
                call_counts[dialog_id][0] += 1
                mock_dialog = MagicMock()
                mock_dialog.dialog_id = dialog_id
                mock_dialog.instance_num = call_counts[dialog_id][0]
                dialog_instances[dialog_id].append(mock_dialog)
                return mock_dialog
            return creator
        
        # 注册对话框
        for dialog_id in dialogs_to_cycle:
            DialogFactory.register(dialog_id, make_creator(dialog_id))
        
        # 首次获取
        first_instances = {}
        for dialog_id in dialogs_to_cycle:
            first_instances[dialog_id] = DialogFactory.get(dialog_id)
            assert DialogFactory.is_created(dialog_id)
        
        # 销毁
        for dialog_id in dialogs_to_cycle:
            DialogFactory.destroy(dialog_id)
            assert not DialogFactory.is_created(dialog_id)
        
        # 重新获取
        for dialog_id in dialogs_to_cycle:
            new_instance = DialogFactory.get(dialog_id)
            assert DialogFactory.is_created(dialog_id)
            assert new_instance is not first_instances[dialog_id], \
                f"Dialog {dialog_id} should have a new instance after recreate"
            assert call_counts[dialog_id][0] == 2, \
                f"Creator for {dialog_id} should be called twice"
        
        DialogFactory.clear()



class TestSafeLazyLoadIntegration:
    """safe_lazy_load 集成测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3**
    
    验证安全延迟加载函数的正确性。
    """
    
    def test_safe_lazy_load_success(self):
        """测试成功加载返回实例
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            
            result = safe_lazy_load("ocr_manager", fallback=None)
            
            assert result is not None
            assert isinstance(result, MockOCRManager)
            
            LazyLoaderManager.reset_instance()
    
    def test_safe_lazy_load_fallback_on_unknown_module(self):
        """测试未知模块返回 fallback
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        LazyLoaderManager.reset_instance()
        
        fallback_value = "default_fallback"
        result = safe_lazy_load("unknown_module", fallback=fallback_value)
        
        assert result == fallback_value
        
        LazyLoaderManager.reset_instance()
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        module_key=st.sampled_from(NON_ESSENTIAL_MODULES),
        fallback=st.one_of(st.none(), st.text(min_size=1, max_size=10))
    )
    def test_safe_lazy_load_with_various_fallbacks(
        self, module_key: str, fallback: Any
    ):
        """测试各种 fallback 值
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            
            # 成功加载时不使用 fallback
            result = safe_lazy_load(module_key, fallback=fallback)
            assert result is not None
            assert result != fallback  # 成功时返回实例，不是 fallback
            
            LazyLoaderManager.reset_instance()



class TestLoadTimeTracking:
    """加载时间追踪测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.3**
    
    验证加载时间追踪的正确性。
    """
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(module_key=st.sampled_from(NON_ESSENTIAL_MODULES))
    def test_load_time_tracked_after_loading(self, module_key: str):
        """测试加载后记录加载时间
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.3**
        """
        with mock_importlib_context():
            LazyLoaderManager.reset_instance()
            loader = LazyLoaderManager.instance()
            
            # 加载前无加载时间
            assert loader.get_load_time(module_key) is None
            
            # 加载模块
            loader.get(module_key)
            
            # 加载后有加载时间
            load_time = loader.get_load_time(module_key)
            assert load_time is not None
            assert load_time >= 0
            
            # 卸载后无加载时间
            loader.unload(module_key)
            assert loader.get_load_time(module_key) is None
            
            LazyLoaderManager.reset_instance()


class TestDialogFactoryStats:
    """DialogFactory 统计测试
    
    Feature: performance-ui-optimization, Property 5: Lazy Loading
    **Validates: Requirements 1.4**
    """
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        register_count=st.integers(min_value=0, max_value=5),
        create_count=st.integers(min_value=0, max_value=5)
    )
    def test_stats_accuracy(self, register_count: int, create_count: int):
        """测试统计信息准确性
        
        Feature: performance-ui-optimization, Property 5: Lazy Loading
        **Validates: Requirements 1.4**
        """
        DialogFactory.clear()
        
        # 注册对话框
        for i in range(register_count):
            dialog_id = f"test_dialog_{i}"
            DialogFactory.register(dialog_id, lambda: MagicMock())
        
        # 创建部分对话框
        actual_create = min(create_count, register_count)
        for i in range(actual_create):
            dialog_id = f"test_dialog_{i}"
            DialogFactory.get(dialog_id)
        
        # 验证统计
        stats = DialogFactory.get_stats()
        assert stats["registered_count"] == register_count
        assert stats["created_count"] == actual_create
        
        # 验证 ID 列表
        registered_ids = DialogFactory.get_registered_ids()
        created_ids = DialogFactory.get_created_ids()
        
        assert len(registered_ids) == register_count
        assert len(created_ids) == actual_create
        
        DialogFactory.clear()
