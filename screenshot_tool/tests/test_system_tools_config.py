# =====================================================
# =============== 系统工具配置测试 ===============
# =====================================================

"""
系统工具配置测试 - 测试 SystemToolsConfig 的配置验证和持久化

Feature: system-tools
Requirements: 7.1, 7.3, 7.4, 7.5
Property 1: Alarm Persistence Round-Trip
"""

import json
import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import (
    SystemToolsConfig,
    AppConfig,
)


# =====================================================
# 策略定义
# =====================================================

# 闹钟数据策略
alarm_strategy = st.fixed_dictionaries({
    "id": st.text(min_size=1, max_size=36, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"),
    "time": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)).map(lambda dt: dt.isoformat()),
    "message": st.text(min_size=0, max_size=200),
    "repeat_daily": st.booleans(),
    "enabled": st.booleans(),
})

# 测速历史数据策略
speed_test_strategy = st.fixed_dictionaries({
    "timestamp": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)).map(lambda dt: dt.isoformat()),
    "download_mbps": st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    "upload_mbps": st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    "ping_ms": st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
})


class TestSystemToolsConfigDefaults:
    """测试 SystemToolsConfig 默认值
    
    Validates: Requirements 7.1, 7.3, 7.4, 7.5
    """
    
    def test_default_alarms_is_empty_list(self):
        """测试 alarms 默认值为空列表"""
        config = SystemToolsConfig()
        assert config.alarms == []
    
    def test_default_pomodoro_work_minutes_is_25(self):
        """测试 pomodoro_work_minutes 默认值为 25"""
        config = SystemToolsConfig()
        assert config.pomodoro_work_minutes == 25
    
    def test_default_pomodoro_short_break_minutes_is_5(self):
        """测试 pomodoro_short_break_minutes 默认值为 5"""
        config = SystemToolsConfig()
        assert config.pomodoro_short_break_minutes == 5
    
    def test_default_pomodoro_long_break_minutes_is_15(self):
        """测试 pomodoro_long_break_minutes 默认值为 15"""
        config = SystemToolsConfig()
        assert config.pomodoro_long_break_minutes == 15
    
    def test_default_speed_test_history_is_empty_list(self):
        """测试 speed_test_history 默认值为空列表"""
        config = SystemToolsConfig()
        assert config.speed_test_history == []


class TestSystemToolsConfigParameterValidation:
    """测试参数范围验证
    
    Validates: Requirements 7.3, 7.4
    """
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_pomodoro_work_minutes_clamped_to_valid_range(self, value: int):
        """任意 pomodoro_work_minutes 值都应被限制在有效范围内"""
        config = SystemToolsConfig(pomodoro_work_minutes=value)
        assert SystemToolsConfig.MIN_WORK_MINUTES <= config.pomodoro_work_minutes <= SystemToolsConfig.MAX_WORK_MINUTES
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_pomodoro_short_break_minutes_clamped_to_valid_range(self, value: int):
        """任意 pomodoro_short_break_minutes 值都应被限制在有效范围内"""
        config = SystemToolsConfig(pomodoro_short_break_minutes=value)
        assert SystemToolsConfig.MIN_BREAK_MINUTES <= config.pomodoro_short_break_minutes <= SystemToolsConfig.MAX_BREAK_MINUTES
    
    @given(st.integers())
    @settings(max_examples=100)
    def test_pomodoro_long_break_minutes_clamped_to_valid_range(self, value: int):
        """任意 pomodoro_long_break_minutes 值都应被限制在有效范围内"""
        config = SystemToolsConfig(pomodoro_long_break_minutes=value)
        assert SystemToolsConfig.MIN_BREAK_MINUTES <= config.pomodoro_long_break_minutes <= SystemToolsConfig.MAX_BREAK_MINUTES
    
    def test_none_pomodoro_values_use_defaults(self):
        """测试 None 值使用默认值"""
        config = SystemToolsConfig(
            pomodoro_work_minutes=None,
            pomodoro_short_break_minutes=None,
            pomodoro_long_break_minutes=None,
        )
        assert config.pomodoro_work_minutes == 25
        assert config.pomodoro_short_break_minutes == 5
        assert config.pomodoro_long_break_minutes == 15
    
    def test_invalid_list_types_become_empty_lists(self):
        """测试无效列表类型变为空列表"""
        config = SystemToolsConfig(
            alarms="not a list",
            speed_test_history={"key": "value"},
        )
        assert config.alarms == []
        assert config.speed_test_history == []


class TestAlarmPersistenceRoundTrip:
    """测试闹钟持久化往返
    
    Property 1: Alarm Persistence Round-Trip
    Validates: Requirements 2.1, 7.1
    """
    
    @given(st.lists(alarm_strategy, min_size=0, max_size=10))
    @settings(max_examples=50)
    def test_alarm_list_round_trip(self, alarms: list):
        """Property 1: 闹钟列表序列化后反序列化应产生等价数据"""
        # 创建原始配置
        original = SystemToolsConfig(alarms=alarms)
        
        # 序列化为字典
        data = {
            "alarms": original.alarms,
            "pomodoro_work_minutes": original.pomodoro_work_minutes,
            "pomodoro_short_break_minutes": original.pomodoro_short_break_minutes,
            "pomodoro_long_break_minutes": original.pomodoro_long_break_minutes,
            "speed_test_history": original.speed_test_history,
        }
        
        # 序列化为 JSON 再反序列化
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        # 从字典创建新配置
        restored = SystemToolsConfig(**loaded_data)
        
        # 验证闹钟列表等价性
        assert len(restored.alarms) == len(original.alarms)
        for i, alarm in enumerate(restored.alarms):
            assert alarm == original.alarms[i]
    
    def test_single_alarm_round_trip(self):
        """测试单个闹钟的往返"""
        alarm = {
            "id": "test-alarm-1",
            "time": "2026-01-15T14:30:00",
            "message": "开会提醒",
            "repeat_daily": True,
            "enabled": True,
        }
        
        config = SystemToolsConfig(alarms=[alarm])
        
        # 序列化
        data = {"alarms": config.alarms}
        json_str = json.dumps(data, ensure_ascii=False)
        loaded_data = json.loads(json_str)
        
        # 反序列化
        restored = SystemToolsConfig(alarms=loaded_data["alarms"])
        
        assert len(restored.alarms) == 1
        assert restored.alarms[0]["id"] == "test-alarm-1"
        assert restored.alarms[0]["message"] == "开会提醒"
        assert restored.alarms[0]["repeat_daily"] is True


class TestSpeedTestHistoryPersistence:
    """测试测速历史持久化
    
    Validates: Requirements 7.5
    """
    
    @given(st.lists(speed_test_strategy, min_size=0, max_size=20))
    @settings(max_examples=50)
    def test_speed_test_history_round_trip(self, history: list):
        """测速历史序列化后反序列化应产生等价数据"""
        # 创建原始配置
        original = SystemToolsConfig(speed_test_history=history)
        
        # 序列化为 JSON 再反序列化
        data = {"speed_test_history": original.speed_test_history}
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        # 从字典创建新配置
        restored = SystemToolsConfig(speed_test_history=loaded_data["speed_test_history"])
        
        # 验证历史记录等价性
        assert len(restored.speed_test_history) == len(original.speed_test_history)


class TestAppConfigSystemToolsIntegration:
    """测试 AppConfig 中 system_tools 的集成
    
    Validates: Requirements 7.1, 7.3, 7.4, 7.5
    """
    
    def test_app_config_has_system_tools(self):
        """测试 AppConfig 包含 system_tools 字段"""
        config = AppConfig()
        assert hasattr(config, "system_tools")
        assert isinstance(config.system_tools, SystemToolsConfig)
    
    def test_app_config_to_dict_includes_system_tools(self):
        """测试 to_dict 包含 system_tools"""
        config = AppConfig()
        data = config.to_dict()
        assert "system_tools" in data
        assert "alarms" in data["system_tools"]
        assert "pomodoro_work_minutes" in data["system_tools"]
        assert "speed_test_history" in data["system_tools"]
    
    def test_app_config_from_dict_loads_system_tools(self):
        """测试 from_dict 正确加载 system_tools"""
        data = {
            "system_tools": {
                "alarms": [{"id": "test", "time": "2026-01-15T10:00:00", "message": "Test", "repeat_daily": False, "enabled": True}],
                "pomodoro_work_minutes": 30,
            }
        }
        config = AppConfig.from_dict(data)
        assert len(config.system_tools.alarms) == 1
        assert config.system_tools.pomodoro_work_minutes == 30
    
    def test_app_config_from_dict_uses_defaults_for_missing(self):
        """测试 from_dict 对缺失字段使用默认值"""
        data = {}
        config = AppConfig.from_dict(data)
        assert config.system_tools.alarms == []
        assert config.system_tools.pomodoro_work_minutes == 25
    
    @given(
        pomodoro_work=st.integers(min_value=1, max_value=120),
        pomodoro_short=st.integers(min_value=1, max_value=60),
        pomodoro_long=st.integers(min_value=1, max_value=60),
    )
    @settings(max_examples=50)
    def test_app_config_system_tools_round_trip(
        self,
        pomodoro_work: int,
        pomodoro_short: int,
        pomodoro_long: int,
    ):
        """测试 AppConfig 中 system_tools 的完整往返"""
        # 创建配置
        config = AppConfig()
        config.system_tools = SystemToolsConfig(
            pomodoro_work_minutes=pomodoro_work,
            pomodoro_short_break_minutes=pomodoro_short,
            pomodoro_long_break_minutes=pomodoro_long,
        )
        
        # 序列化
        data = config.to_dict()
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        # 反序列化
        restored = AppConfig.from_dict(loaded_data)
        
        # 验证
        assert restored.system_tools.pomodoro_work_minutes == pomodoro_work
        assert restored.system_tools.pomodoro_short_break_minutes == pomodoro_short
        assert restored.system_tools.pomodoro_long_break_minutes == pomodoro_long
