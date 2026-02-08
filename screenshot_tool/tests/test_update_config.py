# =====================================================
# =============== 软件更新配置测试 ===============
# =====================================================

"""
软件更新配置属性测试

Property: Configuration Round-Trip
*For any* valid UpdateConfig, serializing to dict and deserializing back
SHALL produce an equivalent configuration.

Feature: auto-update
Validates: Requirements 4.1, 4.2
"""

import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import (
    UpdateConfig,
    NotificationConfig,
    AppConfig,
    ConfigManager,
)


# ========== 策略定义 ==========

# 有效的版本号策略
version_strategy = st.from_regex(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', fullmatch=True)

# ISO 时间字符串策略
iso_time_strategy = st.one_of(
    st.just(""),
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31)
    ).map(lambda dt: dt.isoformat())
)



class TestUpdateConfigUnit:
    """UpdateConfig 单元测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = UpdateConfig()
        assert config.auto_download_enabled is True
        assert config.check_interval_hours == 24
        assert config.last_check_time == ""
        assert config.github_repo == "wangwingzero/hugescreenshot-releases"
        assert config.use_proxy is True
        assert config.proxy_url == "https://gh-proxy.com/"
        assert config.skip_version == ""
        assert config.last_notified_version == ""
    
    def test_interval_clamping_min(self):
        """测试检查间隔最小值限制"""
        config = UpdateConfig(check_interval_hours=0)
        assert config.check_interval_hours == UpdateConfig.MIN_INTERVAL_HOURS
    
    def test_interval_clamping_max(self):
        """测试检查间隔最大值限制"""
        config = UpdateConfig(check_interval_hours=1000)
        assert config.check_interval_hours == UpdateConfig.MAX_INTERVAL_HOURS

    def test_none_handling(self):
        """测试 None 值处理"""
        config = UpdateConfig(
            auto_download_enabled=None,
            check_interval_hours=None,
            last_check_time=None,
            github_repo=None,
            use_proxy=None,
            proxy_url=None,
            skip_version=None,
            last_notified_version=None,
        )
        assert config.auto_download_enabled is True
        assert config.check_interval_hours == 24
        assert config.last_check_time == ""
        assert config.github_repo == "wangwingzero/hugescreenshot-releases"
        assert config.use_proxy is True
        assert config.proxy_url == "https://gh-proxy.com/"
        assert config.skip_version == ""
        assert config.last_notified_version == ""
    
    def test_should_check_when_never_checked(self):
        """测试从未检查时应该检查"""
        config = UpdateConfig(last_check_time="")
        assert config.should_check() is True
    
    def test_should_check_after_interval(self):
        """测试超过间隔后应该检查"""
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        config = UpdateConfig(
            check_interval_hours=24,
            last_check_time=old_time
        )
        assert config.should_check() is True
    
    def test_should_not_check_within_interval(self):
        """测试间隔内不应检查"""
        recent_time = (datetime.now() - timedelta(hours=1)).isoformat()
        config = UpdateConfig(
            check_interval_hours=24,
            last_check_time=recent_time
        )
        assert config.should_check() is False
    
    def test_update_last_check_time(self):
        """测试更新检查时间"""
        config = UpdateConfig()
        assert config.last_check_time == ""
        
        config.update_last_check_time()
        
        assert config.last_check_time != ""
        # 验证是有效的 ISO 格式
        parsed = datetime.fromisoformat(config.last_check_time)
        assert (datetime.now() - parsed).total_seconds() < 5


class TestNotificationConfigSoftwareUpdate:
    """NotificationConfig.software_update 测试"""
    
    def test_default_value(self):
        """测试默认值为 True"""
        config = NotificationConfig()
        assert config.software_update is True
    
    def test_explicit_false(self):
        """测试显式设置为 False"""
        config = NotificationConfig(software_update=False)
        assert config.software_update is False
    
    def test_none_handling(self):
        """测试 None 值处理"""
        config = NotificationConfig(software_update=None)
        assert config.software_update is True


class TestAppConfigUpdateIntegration:
    """AppConfig 与 UpdateConfig 集成测试"""
    
    def test_update_field_exists(self):
        """测试 AppConfig 包含 update 字段"""
        config = AppConfig()
        assert hasattr(config, 'update')
        assert isinstance(config.update, UpdateConfig)
    
    def test_to_dict_includes_update(self):
        """测试 to_dict 包含 update 配置"""
        config = AppConfig()
        d = config.to_dict()
        
        assert 'update' in d
        assert 'auto_download_enabled' in d['update']
        assert 'check_interval_hours' in d['update']
        assert 'last_check_time' in d['update']
        assert 'github_repo' in d['update']
        assert 'skip_version' in d['update']
        assert 'last_notified_version' in d['update']
    
    def test_from_dict_loads_update(self):
        """测试 from_dict 加载 update 配置"""
        data = {
            'update': {
                'auto_download_enabled': False,
                'check_interval_hours': 12,
                'last_check_time': '2026-01-07T10:00:00',
                'github_repo': 'test/repo',
                'skip_version': '2.0.0',
                'last_notified_version': '1.9.1',
            }
        }
        
        config = AppConfig.from_dict(data)
        
        assert config.update.auto_download_enabled is False
        assert config.update.check_interval_hours == 12
        assert config.update.last_check_time == '2026-01-07T10:00:00'
        assert config.update.github_repo == 'test/repo'
        assert config.update.skip_version == '2.0.0'
        assert config.update.last_notified_version == '1.9.1'
    
    def test_from_dict_missing_update_uses_defaults(self):
        """测试 from_dict 缺少 update 时使用默认值"""
        config = AppConfig.from_dict({})
        
        assert config.update.auto_download_enabled is True
        assert config.update.check_interval_hours == 24
        assert config.update.github_repo == "wangwingzero/hugescreenshot-releases"
        assert config.update.use_proxy is True
        assert config.update.proxy_url == "https://gh-proxy.com/"
    
    def test_notification_software_update_in_to_dict(self):
        """测试 to_dict 包含 software_update 通知设置"""
        config = AppConfig()
        d = config.to_dict()
        
        assert 'notification' in d
        assert 'software_update' in d['notification']
    
    def test_notification_software_update_from_dict(self):
        """测试 from_dict 加载 software_update 通知设置"""
        data = {
            'notification': {
                'software_update': False,
            }
        }
        
        config = AppConfig.from_dict(data)
        assert config.notification.software_update is False


class TestConfigManagerUpdateMethods:
    """ConfigManager 更新相关便捷方法测试"""
    
    def test_get_update_config(self):
        """测试获取更新配置"""
        manager = ConfigManager()
        manager.load()
        
        update_config = manager.get_update_config()
        assert isinstance(update_config, UpdateConfig)
    
    def test_set_update_auto_download_enabled(self):
        """测试设置自动下载开关"""
        manager = ConfigManager()
        manager.load()
        
        manager.set_update_auto_download_enabled(False)
        assert manager.get_update_auto_download_enabled() is False
        
        manager.set_update_auto_download_enabled(True)
        assert manager.get_update_auto_download_enabled() is True
    
    def test_should_auto_check_update(self):
        """测试是否应该自动检查"""
        manager = ConfigManager()
        manager.load()
        
        # 默认应该检查（从未检查过）
        assert manager.should_auto_check_update() is True
    
    def test_set_update_skip_version(self):
        """测试设置跳过版本"""
        manager = ConfigManager()
        manager.load()
        
        manager.set_update_skip_version("2.0.0")
        assert manager.get_update_skip_version() == "2.0.0"
        
        manager.set_update_skip_version("")
        assert manager.get_update_skip_version() == ""
    
    def test_set_update_last_notified_version(self):
        """测试设置上次通知版本"""
        manager = ConfigManager()
        manager.load()
        
        manager.set_update_last_notified_version("1.9.1")
        assert manager.get_update_last_notified_version() == "1.9.1"
    
    def test_get_github_repo(self):
        """测试获取 GitHub 仓库"""
        manager = ConfigManager()
        manager.load()
        
        assert manager.get_github_repo() == "wangwingzero/hugescreenshot-releases"
    
    def test_get_use_proxy(self):
        """测试获取是否使用代理"""
        manager = ConfigManager()
        manager.load()
        
        # 默认开启代理
        assert manager.get_use_proxy() is True
        
        # 设置关闭代理
        manager.set_use_proxy(False)
        assert manager.get_use_proxy() is False
    
    def test_get_proxy_url(self):
        """测试获取代理地址"""
        manager = ConfigManager()
        manager.load()
        
        # 默认代理地址
        assert manager.get_proxy_url() == "https://gh-proxy.com/"
        
        # 设置新代理地址
        manager.set_proxy_url("https://custom.proxy.com/")
        assert manager.get_proxy_url() == "https://custom.proxy.com/"
    
    def test_notification_software_update_methods(self):
        """测试软件更新通知便捷方法"""
        manager = ConfigManager()
        manager.load()
        
        # 默认开启
        assert manager.get_notification_software_update() is True
        
        # 关闭
        manager.set_notification_software_update(False)
        assert manager.get_notification_software_update() is False
        
        # 开启
        manager.set_notification_software_update(True)
        assert manager.get_notification_software_update() is True



class TestUpdateConfigProperties:
    """UpdateConfig 属性测试
    
    Feature: auto-update
    """
    
    @given(
        auto_download_enabled=st.booleans(),
        check_interval_hours=st.integers(min_value=1, max_value=168),
        last_check_time=iso_time_strategy,
        skip_version=st.one_of(st.just(""), version_strategy),
        last_notified_version=st.one_of(st.just(""), version_strategy),
    )
    @settings(max_examples=50)
    def test_property_update_config_round_trip(
        self,
        auto_download_enabled,
        check_interval_hours,
        last_check_time,
        skip_version,
        last_notified_version,
    ):
        """
        Property: UpdateConfig Round-Trip
        
        *For any* valid UpdateConfig values, creating a config, converting
        to dict, and creating from dict SHALL produce equivalent values.
        
        **Validates: Requirements 4.1, 4.2**
        """
        # 创建原始配置
        original = UpdateConfig(
            auto_download_enabled=auto_download_enabled,
            check_interval_hours=check_interval_hours,
            last_check_time=last_check_time,
            github_repo="wangwingzero/hugescreenshot-releases",
            use_proxy=True,
            proxy_url="https://gh-proxy.com/",
            skip_version=skip_version,
            last_notified_version=last_notified_version,
        )
        
        # 序列化为字典
        data = {
            'auto_download_enabled': original.auto_download_enabled,
            'check_interval_hours': original.check_interval_hours,
            'last_check_time': original.last_check_time,
            'github_repo': original.github_repo,
            'use_proxy': original.use_proxy,
            'proxy_url': original.proxy_url,
            'skip_version': original.skip_version,
            'last_notified_version': original.last_notified_version,
        }
        
        # 从字典反序列化
        restored = UpdateConfig(**data)
        
        # 验证等价性
        assert restored.auto_download_enabled == original.auto_download_enabled
        assert restored.check_interval_hours == original.check_interval_hours
        assert restored.last_check_time == original.last_check_time
        assert restored.github_repo == original.github_repo
        assert restored.skip_version == original.skip_version
        assert restored.last_notified_version == original.last_notified_version
    
    @given(
        auto_download_enabled=st.booleans(),
        check_interval_hours=st.integers(min_value=1, max_value=168),
        software_update_notification=st.booleans(),
    )
    @settings(max_examples=30)
    def test_property_app_config_update_round_trip(
        self,
        auto_download_enabled,
        check_interval_hours,
        software_update_notification,
    ):
        """
        Property: AppConfig Update Round-Trip
        
        *For any* valid update configuration in AppConfig, serializing
        with to_dict() and deserializing with from_dict() SHALL produce
        an equivalent configuration.
        
        **Validates: Requirements 4.1, 4.2**
        """
        # 创建原始配置
        original = AppConfig()
        original.update.auto_download_enabled = auto_download_enabled
        original.update.check_interval_hours = check_interval_hours
        original.notification.software_update = software_update_notification
        
        # 序列化
        data = original.to_dict()
        
        # 反序列化
        restored = AppConfig.from_dict(data)
        
        # 验证更新配置等价性
        assert restored.update.auto_download_enabled == original.update.auto_download_enabled
        assert restored.update.check_interval_hours == original.update.check_interval_hours
        assert restored.notification.software_update == original.notification.software_update
    
    @given(check_interval=st.integers(min_value=-100, max_value=500))
    @settings(max_examples=20)
    def test_property_interval_clamping(self, check_interval):
        """
        Property: Interval Clamping
        
        *For any* integer input, check_interval_hours SHALL be clamped
        to the valid range [MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS].
        
        **Validates: Requirements 4.2**
        """
        config = UpdateConfig(check_interval_hours=check_interval)
        
        assert config.check_interval_hours >= UpdateConfig.MIN_INTERVAL_HOURS
        assert config.check_interval_hours <= UpdateConfig.MAX_INTERVAL_HOURS
    
    @given(check_interval=st.integers(min_value=1, max_value=168))
    @settings(max_examples=10)
    def test_property_should_check_respects_interval(self, check_interval):
        """
        Property: should_check Respects Interval
        
        *For any* check_interval_hours value, when last_check_time is empty,
        should_check() SHALL always return True.
        
        **Validates: Requirements 4.2**
        """
        config = UpdateConfig(
            check_interval_hours=check_interval,
            last_check_time=""  # 从未检查过
        )
        
        # 从未检查过，应该返回 True
        assert config.should_check() is True
