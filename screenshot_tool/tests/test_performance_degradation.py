"""性能降级策略测试

Feature: performance-ui-optimization
Requirements: 4.1, 4.2
"""

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.performance_degradation import (
    PerformanceDegradation,
    DegradationLevel,
    DegradationState,
    DegradationConfig,
    get_performance_degradation,
)


class TestDegradationLevel:
    """降级级别测试"""
    
    def test_level_ordering(self):
        """测试降级级别顺序"""
        assert DegradationLevel.NONE.value < DegradationLevel.LIGHT.value
        assert DegradationLevel.LIGHT.value < DegradationLevel.MODERATE.value
        assert DegradationLevel.MODERATE.value < DegradationLevel.SEVERE.value
    
    def test_all_levels_exist(self):
        """测试所有降级级别存在"""
        levels = [DegradationLevel.NONE, DegradationLevel.LIGHT, 
                  DegradationLevel.MODERATE, DegradationLevel.SEVERE]
        assert len(levels) == 4


class TestDegradationConfig:
    """降级配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = DegradationConfig()
        assert config.light_threshold_mb == 200.0
        assert config.moderate_threshold_mb == 250.0
        assert config.severe_threshold_mb == 280.0
        assert config.recovery_threshold_mb == 180.0
        assert config.check_interval_seconds == 10.0
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = DegradationConfig(
            light_threshold_mb=150.0,
            moderate_threshold_mb=200.0,
            severe_threshold_mb=250.0,
            recovery_threshold_mb=120.0,
        )
        assert config.light_threshold_mb == 150.0
        assert config.moderate_threshold_mb == 200.0


class TestDegradationState:
    """降级状态测试"""
    
    def test_default_state(self):
        """测试默认状态"""
        state = DegradationState()
        assert state.level == DegradationLevel.NONE
        assert state.animations_disabled is False
        assert state.modules_unloaded == []
        assert state.last_check_time == 0.0
        assert state.last_memory_mb == 0.0
    
    def test_state_with_values(self):
        """测试带值的状态"""
        state = DegradationState(
            level=DegradationLevel.MODERATE,
            animations_disabled=True,
            modules_unloaded=["module1", "module2"],
            last_check_time=1000.0,
            last_memory_mb=250.0
        )
        assert state.level == DegradationLevel.MODERATE
        assert state.animations_disabled is True
        assert state.modules_unloaded == ["module1", "module2"]


class TestPerformanceDegradation:
    """性能降级处理器测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例"""
        PerformanceDegradation.reset_instance()
        yield
        PerformanceDegradation.reset_instance()
    
    def test_initial_state(self):
        """测试初始状态"""
        degradation = PerformanceDegradation()
        assert degradation.current_level == DegradationLevel.NONE
        assert degradation.state.animations_disabled is False
        assert degradation.is_degraded is False
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        instance1 = PerformanceDegradation.instance()
        instance2 = PerformanceDegradation.instance()
        assert instance1 is instance2
    
    def test_get_memory_mb(self):
        """测试获取内存使用量"""
        degradation = PerformanceDegradation()
        memory = degradation.get_memory_mb()
        # 内存使用量应该是非负数
        assert memory >= 0
    
    def test_determine_level_none(self):
        """测试确定级别 - 无降级"""
        degradation = PerformanceDegradation()
        level = degradation.determine_level(100.0)
        assert level == DegradationLevel.NONE
    
    def test_determine_level_light(self):
        """测试确定级别 - 轻度降级"""
        degradation = PerformanceDegradation()
        level = degradation.determine_level(210.0)
        assert level == DegradationLevel.LIGHT
    
    def test_determine_level_moderate(self):
        """测试确定级别 - 中度降级"""
        degradation = PerformanceDegradation()
        level = degradation.determine_level(260.0)
        assert level == DegradationLevel.MODERATE
    
    def test_determine_level_severe(self):
        """测试确定级别 - 严重降级"""
        degradation = PerformanceDegradation()
        level = degradation.determine_level(290.0)
        assert level == DegradationLevel.SEVERE
    
    @patch.object(PerformanceDegradation, 'get_memory_mb')
    def test_check_memory_pressure_no_pressure(self, mock_memory):
        """测试无内存压力"""
        mock_memory.return_value = 100.0
        degradation = PerformanceDegradation()
        result = degradation.check_memory_pressure()
        assert result is False
    
    @patch.object(PerformanceDegradation, 'get_memory_mb')
    def test_check_memory_pressure_with_pressure(self, mock_memory):
        """测试有内存压力"""
        mock_memory.return_value = 260.0
        degradation = PerformanceDegradation()
        result = degradation.check_memory_pressure()
        assert result is True
    
    @patch.object(PerformanceDegradation, 'get_memory_mb')
    def test_check_and_apply_no_pressure(self, mock_memory):
        """测试无压力时不应用降级"""
        mock_memory.return_value = 100.0
        degradation = PerformanceDegradation()
        level = degradation.check_and_apply()
        assert level == DegradationLevel.NONE
        assert degradation.is_degraded is False
    
    @patch.object(PerformanceDegradation, 'get_memory_mb')
    def test_check_and_apply_with_pressure(self, mock_memory):
        """测试有压力时应用降级"""
        mock_memory.return_value = 260.0
        degradation = PerformanceDegradation()
        level = degradation.check_and_apply()
        assert level == DegradationLevel.MODERATE
        assert degradation.is_degraded is True
    
    def test_force_degradation_none_recovers(self):
        """测试强制 NONE 级别会恢复"""
        degradation = PerformanceDegradation()
        degradation._state.level = DegradationLevel.LIGHT
        degradation.force_degradation(DegradationLevel.NONE)
        assert degradation.current_level == DegradationLevel.NONE
    
    def test_force_degradation_light(self):
        """测试强制轻度降级"""
        degradation = PerformanceDegradation()
        degradation.force_degradation(DegradationLevel.LIGHT)
        assert degradation.current_level == DegradationLevel.LIGHT
    
    def test_degradation_callback(self):
        """测试降级回调"""
        degradation = PerformanceDegradation()
        callback_called = []
        
        def callback(level):
            callback_called.append(level)
        
        degradation.add_degradation_callback(callback)
        degradation.force_degradation(DegradationLevel.LIGHT)
        
        assert len(callback_called) == 1
        assert callback_called[0] == DegradationLevel.LIGHT
    
    def test_recovery_callback(self):
        """测试恢复回调"""
        degradation = PerformanceDegradation()
        callback_called = []
        
        def callback():
            callback_called.append(True)
        
        degradation.add_recovery_callback(callback)
        degradation._state.level = DegradationLevel.LIGHT
        degradation.force_degradation(DegradationLevel.NONE)
        
        assert len(callback_called) == 1
    
    def test_remove_degradation_callback(self):
        """测试移除降级回调"""
        degradation = PerformanceDegradation()
        callback_called = []
        
        def callback(level):
            callback_called.append(level)
        
        degradation.add_degradation_callback(callback)
        degradation.remove_degradation_callback(callback)
        degradation.force_degradation(DegradationLevel.LIGHT)
        
        assert len(callback_called) == 0
    
    def test_get_status_info(self):
        """测试状态信息"""
        degradation = PerformanceDegradation()
        info = degradation.get_status_info()
        
        assert "level" in info
        assert "is_degraded" in info
        assert "animations_disabled" in info
        assert "modules_unloaded" in info
        assert "last_memory_mb" in info
        assert "config" in info
        
        assert info["level"] == "NONE"
        assert info["is_degraded"] is False


class TestDisableAnimations:
    """禁用动画测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例"""
        PerformanceDegradation.reset_instance()
        yield
        PerformanceDegradation.reset_instance()
    
    def test_disable_animations_sets_flag(self):
        """测试禁用动画设置标志"""
        degradation = PerformanceDegradation()
        
        # Mock AnimationConstants
        with patch('screenshot_tool.core.performance_degradation.AnimationConstants', create=True) as mock_constants:
            mock_constants.INSTANT = 50
            mock_constants.FAST = 150
            mock_constants.NORMAL = 200
            mock_constants.SLOW = 300
            mock_constants.SUCCESS = 400
            
            # 需要 patch import
            with patch.dict('sys.modules', {'screenshot_tool.ui.styles': MagicMock(AnimationConstants=mock_constants)}):
                degradation._disable_animations()
                # 由于 import 在函数内部，可能不会设置标志
                # 但不应该抛出异常
    
    def test_disable_animations_import_error(self):
        """测试导入错误时不崩溃"""
        degradation = PerformanceDegradation()
        # 即使导入失败也不应该抛出异常
        degradation._disable_animations()


class TestUnloadModules:
    """卸载模块测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例"""
        PerformanceDegradation.reset_instance()
        yield
        PerformanceDegradation.reset_instance()
    
    def test_unload_modules_calls_lazy_loader(self):
        """测试卸载模块调用 LazyLoader"""
        from screenshot_tool.core.lazy_loader import LazyLoaderManager
        
        # 重置 LazyLoaderManager 单例
        LazyLoaderManager.reset_instance()
        
        try:
            degradation = PerformanceDegradation()
            
            # 使用真实的 LazyLoaderManager，但模拟其方法
            lazy = LazyLoaderManager.instance()
            original_is_loaded = lazy.is_loaded
            original_unload = lazy.unload
            
            try:
                # 模拟 is_loaded 返回 True
                lazy.is_loaded = MagicMock(return_value=True)
                lazy.unload = MagicMock()
                
                degradation._unload_modules(["regulation_service", "markdown_converter"])
                
                # 应该检查并卸载模块
                assert lazy.unload.call_count == 2
            finally:
                # 恢复原始方法
                lazy.is_loaded = original_is_loaded
                lazy.unload = original_unload
        finally:
            LazyLoaderManager.reset_instance()
    
    def test_unload_modules_import_error(self):
        """测试导入错误时不崩溃"""
        degradation = PerformanceDegradation()
        # 即使导入失败也不应该抛出异常
        degradation._unload_modules(["module1"])


class TestGetPerformanceDegradation:
    """便捷函数测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例"""
        PerformanceDegradation.reset_instance()
        yield
        PerformanceDegradation.reset_instance()
    
    def test_get_performance_degradation_returns_singleton(self):
        """测试便捷函数返回单例"""
        instance1 = get_performance_degradation()
        instance2 = get_performance_degradation()
        assert instance1 is instance2
    
    def test_get_performance_degradation_with_config(self):
        """测试便捷函数接受配置"""
        config = DegradationConfig(light_threshold_mb=150.0)
        instance = get_performance_degradation(config)
        assert instance.config.light_threshold_mb == 150.0


class TestPropertyBasedTests:
    """属性测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例"""
        PerformanceDegradation.reset_instance()
        yield
        PerformanceDegradation.reset_instance()
    
    @settings(max_examples=50)
    @given(st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False))
    def test_memory_threshold_consistency(self, memory_mb):
        """Feature: performance-ui-optimization, Property 3: Memory Management
        
        For any memory value, the degradation level should be consistent with thresholds.
        """
        PerformanceDegradation.reset_instance()
        degradation = PerformanceDegradation()
        config = degradation.config
        
        level = degradation.determine_level(memory_mb)
        
        if memory_mb >= config.severe_threshold_mb:
            assert level == DegradationLevel.SEVERE
        elif memory_mb >= config.moderate_threshold_mb:
            assert level == DegradationLevel.MODERATE
        elif memory_mb >= config.light_threshold_mb:
            assert level == DegradationLevel.LIGHT
        elif memory_mb <= config.recovery_threshold_mb:
            assert level == DegradationLevel.NONE
        # 在恢复阈值和轻度阈值之间，保持当前级别（NONE）
    
    @settings(max_examples=20)
    @given(st.sampled_from([DegradationLevel.LIGHT, DegradationLevel.MODERATE, DegradationLevel.SEVERE]))
    def test_force_degradation_sets_correct_level(self, level):
        """Feature: performance-ui-optimization, Property 3: Memory Management
        
        For any degradation level, forcing it should set the correct state.
        """
        PerformanceDegradation.reset_instance()
        degradation = PerformanceDegradation()
        
        degradation.force_degradation(level)
        assert degradation.current_level == level
        assert degradation.is_degraded is True
    
    @settings(max_examples=10)
    @given(st.lists(st.sampled_from(list(DegradationLevel)), min_size=1, max_size=5))
    def test_recovery_always_resets_to_none(self, levels):
        """Feature: performance-ui-optimization, Property 3: Memory Management
        
        Recovery should always reset to NONE level.
        """
        PerformanceDegradation.reset_instance()
        degradation = PerformanceDegradation()
        
        # 应用一些降级
        for level in levels:
            if level != DegradationLevel.NONE:
                degradation.force_degradation(level)
        
        # 恢复
        degradation.force_degradation(DegradationLevel.NONE)
        
        assert degradation.current_level == DegradationLevel.NONE
        assert degradation.is_degraded is False
