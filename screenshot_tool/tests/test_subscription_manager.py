"""
订阅系统管理器测试

Feature: subscription-system
Validates: Requirements 2.3, 7.1
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from screenshot_tool.services.subscription.manager import (
    SubscriptionManager, SubscriptionState
)
from screenshot_tool.services.subscription.feature_gate import Feature, AccessResult
from screenshot_tool.services.subscription.models import Plan


class TestSubscriptionState:
    """订阅状态测试"""
    
    def test_default_state(self):
        """测试默认状态"""
        state = SubscriptionState()
        
        assert state.is_logged_in is False
        assert state.is_vip is False
        assert state.user_email is None
        assert state.user_id is None
        assert state.plan == Plan.FREE
        assert state.error is None
    
    def test_state_with_values(self):
        """测试带值的状态"""
        state = SubscriptionState(
            is_logged_in=True,
            is_vip=True,
            user_email="test@example.com",
            user_id="user-123",
            plan=Plan.LIFETIME_VIP,
        )
        
        assert state.is_logged_in is True
        assert state.is_vip is True
        assert state.user_email == "test@example.com"
        assert state.user_id == "user-123"
        assert state.plan == Plan.LIFETIME_VIP


class TestSubscriptionManagerInit:
    """订阅管理器初始化测试"""
    
    def test_init_without_config(self):
        """测试无配置初始化"""
        manager = SubscriptionManager()
        
        assert manager.is_initialized is False
        assert manager.is_logged_in is False
        assert manager.is_vip is False
    
    def test_singleton_instance(self):
        """测试单例实例"""
        manager1 = SubscriptionManager()
        manager2 = SubscriptionManager()
        
        # 最后创建的实例成为单例
        assert SubscriptionManager.instance() is manager2


class TestSubscriptionManagerFeatures:
    """订阅管理器功能测试"""
    
    def test_can_use_without_init(self):
        """测试未初始化时 can_use 返回 True"""
        manager = SubscriptionManager()
        
        # 未初始化时默认允许所有功能
        assert manager.can_use(Feature.TRANSLATION) is True
        assert manager.can_use(Feature.SCREEN_RECORDER) is True
    
    def test_use_feature_without_init(self):
        """测试未初始化时 use_feature 返回允许"""
        manager = SubscriptionManager()
        
        result = manager.use_feature(Feature.TRANSLATION)
        assert result.allowed is True
    
    def test_check_access_without_init(self):
        """测试未初始化时 check_access 返回允许"""
        manager = SubscriptionManager()
        
        result = manager.check_access(Feature.TRANSLATION)
        assert result.allowed is True
    
    def test_get_feature_status_without_init(self):
        """测试未初始化时获取功能状态"""
        manager = SubscriptionManager()
        
        status = manager.get_feature_status(Feature.TRANSLATION)
        
        assert status["feature"] == "translation"
        assert status["allowed"] is True
        assert "未初始化" in status["reason"]


class TestSubscriptionManagerAuth:
    """订阅管理器认证测试"""
    
    def test_login_without_init(self):
        """测试未初始化时登录失败"""
        manager = SubscriptionManager()
        
        result = manager.login("test@example.com", "password")
        assert result is False
    
    def test_logout(self):
        """测试登出"""
        manager = SubscriptionManager()
        manager._state.is_logged_in = True
        manager._state.user_email = "test@example.com"
        
        manager.logout()
        
        assert manager.is_logged_in is False
        assert manager.state.user_email is None


class TestSubscriptionManagerSync:
    """订阅管理器同步测试"""
    
    def test_sync_usage_without_tracker(self):
        """测试无追踪器时同步失败"""
        manager = SubscriptionManager()
        
        result = manager.sync_usage()
        assert result is False


class TestSubscriptionManagerProperties:
    """订阅管理器属性测试"""
    
    def test_state_property(self):
        """测试 state 属性"""
        manager = SubscriptionManager()
        
        assert isinstance(manager.state, SubscriptionState)
    
    def test_auth_service_property(self):
        """测试 auth_service 属性"""
        manager = SubscriptionManager()
        
        assert manager.auth_service is None
    
    def test_license_service_property(self):
        """测试 license_service 属性"""
        manager = SubscriptionManager()
        
        assert manager.license_service is None
    
    def test_feature_gate_property(self):
        """测试 feature_gate 属性"""
        manager = SubscriptionManager()
        
        assert manager.feature_gate is None


class TestVIPRealtimeUnlock:
    """VIP 实时解锁测试
    
    Feature: vip-realtime-unlock-modal-fix
    **Property 1: 登录触发 VIP 状态刷新和功能门控重新初始化**
    **Property 2: 登出撤销 VIP 功能访问**
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """
    
    def test_logout_clears_license_service(self):
        """测试登出后清除许可证服务
        
        Property 2: 登出撤销 VIP 功能访问
        Validates: Requirements 1.4
        """
        manager = SubscriptionManager()
        
        # 模拟已登录状态
        manager._state.is_logged_in = True
        manager._state.is_vip = True
        manager._state.user_email = "test@example.com"
        manager._state.user_id = "user-123"
        manager._license_service = Mock()
        
        # 执行登出
        manager.logout()
        
        # 验证状态被清除
        assert manager.is_logged_in is False
        assert manager.is_vip is False
        assert manager._license_service is None
    
    def test_logout_reinitializes_feature_gate(self):
        """测试登出后重新初始化功能门控
        
        Property 2: 登出撤销 VIP 功能访问
        Validates: Requirements 1.4
        """
        manager = SubscriptionManager()
        
        # 模拟已登录状态
        manager._state.is_logged_in = True
        manager._state.is_vip = True
        manager._license_service = Mock()
        
        # 执行登出
        manager.logout()
        
        # 验证功能门控被重新初始化（无许可证服务）
        assert manager._feature_gate is not None
        # 功能门控应该没有许可证服务
        assert manager._feature_gate._license_service is None
    
    def test_logout_revokes_vip_features(self):
        """测试登出后 VIP 功能被撤销
        
        Property 2: 登出撤销 VIP 功能访问
        Validates: Requirements 1.4
        """
        manager = SubscriptionManager()
        
        # 模拟已登录 VIP 状态
        manager._state.is_logged_in = True
        manager._state.is_vip = True
        manager._license_service = Mock()
        manager._license_service.is_vip.return_value = True
        
        # 初始化功能门控（VIP 状态）
        from screenshot_tool.services.subscription.feature_gate import FeatureGate
        manager._feature_gate = FeatureGate(manager._license_service, None)
        
        # 验证 VIP 功能可用
        assert manager._feature_gate.can_use(Feature.GONGWEN) is True
        
        # 执行登出
        manager.logout()
        
        # 验证 VIP 功能不可用
        assert manager._feature_gate.can_use(Feature.GONGWEN) is False
    
    def test_refresh_subscription_reinitializes_feature_gate(self):
        """测试刷新订阅后重新初始化功能门控
        
        Property 1: 登录触发 VIP 状态刷新和功能门控重新初始化
        Validates: Requirements 1.5
        """
        manager = SubscriptionManager()
        
        # 模拟已登录状态
        manager._state.is_logged_in = True
        manager._state.user_id = "user-123"
        
        # 创建 mock 许可证服务
        mock_license = Mock()
        mock_license.verify.return_value = True
        mock_license.is_vip.return_value = True
        manager._license_service = mock_license
        
        # 创建 mock 客户端
        manager._client = Mock()
        
        # 执行刷新
        result = manager.refresh_subscription()
        
        # 验证刷新成功
        assert result is True
        
        # 验证许可证服务被调用
        mock_license.verify.assert_called_once_with(force=True)
        
        # 验证状态被更新
        assert manager._state.is_vip is True
        assert manager._state.plan == Plan.LIFETIME_VIP
        
        # 验证功能门控被重新初始化
        assert manager._feature_gate is not None
