# =====================================================
# =============== 热键配置测试 ===============
# =====================================================

"""
热键配置测试 - 测试 HotkeyConfig 的强制锁定功能

Feature: hotkey-force-lock
Requirements: 1.1, 1.2, 1.3, 1.4
Property 1: Configuration Default Values
Property 2: Retry Interval Validation
Property 3: Configuration Round-Trip
"""

import json
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import HotkeyConfig


class TestHotkeyConfigDefaults:
    """测试 HotkeyConfig 默认值
    
    Property 1: Configuration Default Values
    Validates: Requirements 1.1, 1.2
    """
    
    def test_default_force_lock_is_false(self):
        """测试 force_lock 默认值为 False"""
        config = HotkeyConfig()
        assert config.force_lock is False
    
    def test_default_retry_interval_is_3000(self):
        """测试 retry_interval_ms 默认值为 3000"""
        config = HotkeyConfig()
        assert config.retry_interval_ms == 3000
    
    def test_default_screenshot_modifier_is_alt(self):
        """测试 screenshot_modifier 默认值为 alt"""
        config = HotkeyConfig()
        assert config.screenshot_modifier == "alt"
    
    def test_default_screenshot_key_is_a(self):
        """测试 screenshot_key 默认值为 a"""
        config = HotkeyConfig()
        assert config.screenshot_key == "a"


class TestHotkeyConfigRetryIntervalValidation:
    """测试重试间隔验证
    
    Property 2: Retry Interval Validation
    Validates: Requirements 1.3
    """
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_retry_interval_clamped_to_valid_range(self, value: int):
        """Property 2: 任意整数值都应被限制在有效范围内"""
        config = HotkeyConfig(retry_interval_ms=value)
        assert HotkeyConfig.MIN_RETRY_INTERVAL_MS <= config.retry_interval_ms <= HotkeyConfig.MAX_RETRY_INTERVAL_MS
    
    def test_retry_interval_below_minimum_clamped(self):
        """测试低于最小值时被限制"""
        config = HotkeyConfig(retry_interval_ms=500)
        assert config.retry_interval_ms == HotkeyConfig.MIN_RETRY_INTERVAL_MS
    
    def test_retry_interval_above_maximum_clamped(self):
        """测试高于最大值时被限制"""
        config = HotkeyConfig(retry_interval_ms=50000)
        assert config.retry_interval_ms == HotkeyConfig.MAX_RETRY_INTERVAL_MS
    
    def test_retry_interval_none_uses_default(self):
        """测试 None 值使用默认值"""
        config = HotkeyConfig(retry_interval_ms=None)
        assert config.retry_interval_ms == 3000
    
    def test_retry_interval_valid_value_preserved(self):
        """测试有效值被保留"""
        config = HotkeyConfig(retry_interval_ms=5000)
        assert config.retry_interval_ms == 5000


class TestHotkeyConfigRoundTrip:
    """测试配置序列化往返
    
    Property 3: Configuration Round-Trip
    Validates: Requirements 1.4
    """
    
    @given(
        force_lock=st.booleans(),
        retry_interval_ms=st.integers(min_value=1000, max_value=30000)
    )
    @settings(max_examples=100)
    def test_config_round_trip(self, force_lock: bool, retry_interval_ms: int):
        """Property 3: 序列化后反序列化应产生等价配置"""
        # 创建原始配置
        original = HotkeyConfig(
            force_lock=force_lock,
            retry_interval_ms=retry_interval_ms
        )
        
        # 序列化为字典
        data = {
            "screenshot_modifier": original.screenshot_modifier,
            "screenshot_key": original.screenshot_key,
            "force_lock": original.force_lock,
            "retry_interval_ms": original.retry_interval_ms,
        }
        
        # 序列化为 JSON 再反序列化
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        # 从字典创建新配置
        restored = HotkeyConfig(**loaded_data)
        
        # 验证等价性
        assert restored.force_lock == original.force_lock
        assert restored.retry_interval_ms == original.retry_interval_ms
        assert restored.screenshot_modifier == original.screenshot_modifier
        assert restored.screenshot_key == original.screenshot_key
    
    def test_round_trip_with_all_fields(self):
        """测试完整配置的往返"""
        original = HotkeyConfig(
            screenshot_modifier="ctrl+alt",
            screenshot_key="s",
            force_lock=True,
            retry_interval_ms=5000
        )
        
        # 序列化
        data = {
            "screenshot_modifier": original.screenshot_modifier,
            "screenshot_key": original.screenshot_key,
            "force_lock": original.force_lock,
            "retry_interval_ms": original.retry_interval_ms,
        }
        json_str = json.dumps(data)
        
        # 反序列化
        loaded_data = json.loads(json_str)
        restored = HotkeyConfig(**loaded_data)
        
        assert restored.screenshot_modifier == "ctrl+alt"
        assert restored.screenshot_key == "s"
        assert restored.force_lock is True
        assert restored.retry_interval_ms == 5000


class TestHotkeyConfigForceLockValidation:
    """测试强制锁定开关验证"""
    
    def test_force_lock_true(self):
        """测试 force_lock 为 True"""
        config = HotkeyConfig(force_lock=True)
        assert config.force_lock is True
    
    def test_force_lock_false(self):
        """测试 force_lock 为 False"""
        config = HotkeyConfig(force_lock=False)
        assert config.force_lock is False
    
    def test_force_lock_non_bool_converted(self):
        """测试非布尔值被转换为 False"""
        config = HotkeyConfig(force_lock="yes")
        assert config.force_lock is False
    
    def test_force_lock_none_uses_default(self):
        """测试 None 值使用默认值 False"""
        config = HotkeyConfig(force_lock=None)
        assert config.force_lock is False
