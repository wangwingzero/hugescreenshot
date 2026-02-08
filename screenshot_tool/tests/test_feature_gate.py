"""
功能门控测试

Feature: subscription-system
Property 4: Free features are always accessible
Property 5: Daily limit enforcement
Property 6: VIP features are blocked for free users
Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import tempfile
import pytest
from unittest.mock import Mock, MagicMock
from hypothesis import given, strategies as st, settings

from screenshot_tool.services.subscription.feature_gate import (
    FeatureGate, Feature, AccessResult, FEATURE_CONFIG
)
from screenshot_tool.services.subscription.usage_tracker import UsageTracker, DAILY_LIMITS


class MockLicenseService:
    """模拟许可证服务"""
    
    def __init__(self, is_vip: bool = False):
        self._is_vip = is_vip
    
    def is_vip(self) -> bool:
        return self._is_vip


class TestFreeFeatures:
    """免费功能测试
    
    Property 4: Free features are always accessible
    """
    
    FREE_FEATURES = [
        Feature.SCREENSHOT,
        Feature.OCR,
        Feature.HIGHLIGHT,
        Feature.DING,
    ]
    
    @given(is_vip=st.booleans())
    @settings(max_examples=10)
    def test_free_features_always_accessible(self, is_vip: bool):
        """Property 4: 免费功能始终可用
        
        Feature: subscription-system, Property 4
        Validates: Requirements 4.1
        
        无论是免费用户还是 VIP 用户，基础功能都应该可用。
        """
        license_service = MockLicenseService(is_vip=is_vip)
        gate = FeatureGate(license_service)
        
        for feature in self.FREE_FEATURES:
            result = gate.check_access(feature)
            assert result.allowed is True, f"{feature} should be accessible"
            assert gate.can_use(feature) is True
    
    def test_free_features_no_limit(self):
        """测试免费功能无使用限制"""
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            # 多次使用截图功能
            for _ in range(100):
                result = gate.use(Feature.SCREENSHOT)
                assert result.allowed is True


class TestDailyLimitEnforcement:
    """每日限制测试
    
    Property 5: Daily limit enforcement
    """
    
    LIMITED_FEATURES = [
        (Feature.TRANSLATION, "translation", 10),
        (Feature.WEB_TO_MARKDOWN, "web_to_markdown", 5),
    ]
    
    def test_limited_features_have_daily_limit_for_free_users(self):
        """Property 5: 免费用户受限功能有每日限制
        
        Feature: subscription-system, Property 5
        Validates: Requirements 4.2, 4.3, 5.1, 5.2
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            for feature, limit_key, limit in self.LIMITED_FEATURES:
                # 重置追踪器
                tracker.reset_today()
                
                # 使用到限制
                for i in range(limit):
                    result = gate.use(feature)
                    assert result.allowed is True, f"Use {i+1} should succeed"
                    assert result.remaining == limit - i - 1
                
                # 超过限制应该失败
                result = gate.use(feature)
                assert result.allowed is False
                assert "上限" in result.reason
                assert result.upgrade_hint is not None
    
    @given(
        feature_idx=st.integers(min_value=0, max_value=1),
        use_count=st.integers(min_value=0, max_value=15),
    )
    @settings(max_examples=30)
    def test_remaining_count_accuracy(self, feature_idx: int, use_count: int):
        """Property 5: 剩余次数准确性
        
        Feature: subscription-system, Property 5
        Validates: Requirements 5.1, 5.2
        """
        feature, limit_key, limit = self.LIMITED_FEATURES[feature_idx]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            # 使用指定次数
            successful = 0
            for _ in range(use_count):
                result = gate.use(feature)
                if result.allowed:
                    successful += 1
            
            # 验证剩余次数
            expected_remaining = max(0, limit - successful)
            status = gate.get_feature_status(feature)
            assert status["remaining"] == expected_remaining
    
    def test_vip_users_no_daily_limit(self):
        """测试 VIP 用户无每日限制"""
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=True)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            # VIP 用户可以无限使用翻译
            for _ in range(50):
                result = gate.use(Feature.TRANSLATION)
                assert result.allowed is True
                assert result.remaining is None  # VIP 无限制


class TestVIPFeatures:
    """VIP 功能测试
    
    Property 6: VIP features are blocked for free users
    """
    
    VIP_FEATURES = [
        Feature.SCREEN_RECORDER,
        Feature.GONGWEN,
        Feature.CAAC,
    ]
    
    def test_vip_features_blocked_for_free_users(self):
        """Property 6: VIP 功能对免费用户不可用
        
        Feature: subscription-system, Property 6
        Validates: Requirements 4.4
        """
        license_service = MockLicenseService(is_vip=False)
        gate = FeatureGate(license_service)
        
        for feature in self.VIP_FEATURES:
            result = gate.check_access(feature)
            assert result.allowed is False
            assert "VIP" in result.reason
            assert result.upgrade_hint is not None
            assert gate.can_use(feature) is False
    
    def test_vip_features_allowed_for_vip_users(self):
        """测试 VIP 功能对 VIP 用户可用"""
        license_service = MockLicenseService(is_vip=True)
        gate = FeatureGate(license_service)
        
        for feature in self.VIP_FEATURES:
            result = gate.check_access(feature)
            assert result.allowed is True
            assert gate.can_use(feature) is True
    
    @given(is_vip=st.booleans())
    @settings(max_examples=10)
    def test_vip_only_check(self, is_vip: bool):
        """测试 is_vip_only 方法"""
        license_service = MockLicenseService(is_vip=is_vip)
        gate = FeatureGate(license_service)
        
        # VIP 专属功能
        for feature in self.VIP_FEATURES:
            assert gate.is_vip_only(feature) is True
        
        # 非 VIP 专属功能
        assert gate.is_vip_only(Feature.SCREENSHOT) is False
        assert gate.is_vip_only(Feature.TRANSLATION) is False


class TestAccessResult:
    """AccessResult 测试"""
    
    def test_allow_result(self):
        """测试允许结果"""
        result = AccessResult.allow(remaining=5)
        assert result.allowed is True
        assert result.remaining == 5
        assert result.upgrade_hint is None
    
    def test_deny_result(self):
        """测试拒绝结果"""
        result = AccessResult.deny("测试原因", "升级提示")
        assert result.allowed is False
        assert result.reason == "测试原因"
        assert result.upgrade_hint == "升级提示"


class TestFeatureStatus:
    """功能状态测试"""
    
    def test_get_feature_status_free_user(self):
        """测试免费用户功能状态"""
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            # 使用一次翻译
            gate.use(Feature.TRANSLATION)
            
            status = gate.get_feature_status(Feature.TRANSLATION)
            assert status["feature"] == "translation"
            assert status["allowed"] is True
            assert status["is_vip_only"] is False
            assert status["is_limited"] is True
            assert status["usage"] == 1
            assert status["limit"] == 10
            assert status["remaining"] == 9
    
    def test_get_feature_status_vip_user(self):
        """测试 VIP 用户功能状态"""
        license_service = MockLicenseService(is_vip=True)
        gate = FeatureGate(license_service)
        
        status = gate.get_feature_status(Feature.TRANSLATION)
        assert status["feature"] == "translation"
        assert status["allowed"] is True
        assert status["is_limited"] is False  # VIP 无限制
        assert "usage" not in status  # VIP 不显示使用量
    
    def test_get_all_features_status(self):
        """测试获取所有功能状态"""
        license_service = MockLicenseService(is_vip=False)
        gate = FeatureGate(license_service)
        
        all_status = gate.get_all_features_status()
        
        assert len(all_status) == len(Feature)
        assert "screenshot" in all_status
        assert "translation" in all_status
        assert "screen_recorder" in all_status


class TestUseFeature:
    """使用功能测试"""
    
    def test_use_increments_usage(self):
        """测试使用功能增加使用量"""
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            assert tracker.get_usage("translation") == 0
            
            gate.use(Feature.TRANSLATION)
            assert tracker.get_usage("translation") == 1
            
            gate.use(Feature.TRANSLATION)
            assert tracker.get_usage("translation") == 2
    
    def test_use_returns_remaining(self):
        """测试使用功能返回剩余次数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            license_service = MockLicenseService(is_vip=False)
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            gate = FeatureGate(license_service, tracker)
            
            result = gate.use(Feature.TRANSLATION)
            assert result.remaining == 9  # 10 - 1
            
            result = gate.use(Feature.TRANSLATION)
            assert result.remaining == 8  # 10 - 2
    
    def test_use_blocked_feature_returns_deny(self):
        """测试使用被阻止的功能返回拒绝"""
        license_service = MockLicenseService(is_vip=False)
        gate = FeatureGate(license_service)
        
        result = gate.use(Feature.SCREEN_RECORDER)
        assert result.allowed is False
        assert "VIP" in result.reason


class TestVIPOverride:
    """VIP 状态覆盖测试
    
    测试 is_vip_override 参数，用于在 license_service 未初始化时
    使用缓存的 VIP 状态。
    
    Feature: subscription-system
    """
    
    def test_vip_override_allows_vip_features_without_license_service(self):
        """测试 is_vip_override=True 时，即使没有 license_service 也能访问 VIP 功能"""
        # 没有 license_service，但有 is_vip_override=True
        gate = FeatureGate(None, None, is_vip_override=True)
        
        # VIP 功能应该可以访问
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is True
        
        result = gate.check_access(Feature.SCREEN_RECORDER)
        assert result.allowed is True
        
        result = gate.check_access(Feature.GONGWEN)
        assert result.allowed is True
    
    def test_vip_override_false_blocks_vip_features(self):
        """测试 is_vip_override=False 时，VIP 功能被阻止"""
        gate = FeatureGate(None, None, is_vip_override=False)
        
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is False
        assert "VIP" in result.reason
    
    def test_vip_override_none_uses_license_service(self):
        """测试 is_vip_override=None 时，使用 license_service 判断"""
        # VIP 用户
        license_service = MockLicenseService(is_vip=True)
        gate = FeatureGate(license_service, None, is_vip_override=None)
        
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is True
        
        # 免费用户
        license_service = MockLicenseService(is_vip=False)
        gate = FeatureGate(license_service, None, is_vip_override=None)
        
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is False
    
    def test_vip_override_takes_precedence_over_license_service(self):
        """测试 is_vip_override 优先于 license_service"""
        # license_service 说是免费用户，但 override 说是 VIP
        license_service = MockLicenseService(is_vip=False)
        gate = FeatureGate(license_service, None, is_vip_override=True)
        
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is True
        
        # license_service 说是 VIP，但 override 说是免费用户
        license_service = MockLicenseService(is_vip=True)
        gate = FeatureGate(license_service, None, is_vip_override=False)
        
        result = gate.check_access(Feature.CAAC)
        assert result.allowed is False
