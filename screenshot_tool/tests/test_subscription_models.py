"""
订阅系统数据模型测试

Feature: subscription-system
Property 7: VIP has unlimited access
Validates: Requirements 4.6
"""

import pytest
from hypothesis import given, strategies as st
from datetime import datetime, timedelta

from screenshot_tool.services.subscription.models import (
    Plan,
    SubscriptionStatus,
    SubscriptionInfo,
    UsageStats,
    LicenseCache,
)


class TestSubscriptionInfo:
    """SubscriptionInfo 测试"""
    
    # ========== Property 7: VIP has unlimited access ==========
    # For any VIP user, all features should return can_use = True
    # Validates: Requirements 4.6
    
    @given(
        plan=st.sampled_from(list(Plan)),
        status=st.sampled_from(list(SubscriptionStatus)),
    )
    def test_is_vip_property(self, plan: Plan, status: SubscriptionStatus):
        """Property 7: is_vip 只有在 plan=LIFETIME_VIP 且 status=ACTIVE 时为 True
        
        Feature: subscription-system, Property 7: VIP has unlimited access
        Validates: Requirements 4.6
        """
        info = SubscriptionInfo(plan=plan, status=status)
        
        expected = (plan == Plan.LIFETIME_VIP and status == SubscriptionStatus.ACTIVE)
        assert info.is_vip == expected
    
    def test_free_subscription_is_not_vip(self):
        """免费用户不是 VIP"""
        info = SubscriptionInfo.free()
        assert info.is_vip is False
        assert info.plan == Plan.FREE
        assert info.status == SubscriptionStatus.ACTIVE
    
    def test_vip_subscription_is_vip(self):
        """VIP 用户是 VIP"""
        info = SubscriptionInfo.vip()
        assert info.is_vip is True
        assert info.plan == Plan.LIFETIME_VIP
        assert info.status == SubscriptionStatus.ACTIVE
        assert info.purchased_at is not None
    
    def test_expired_vip_is_not_vip(self):
        """过期的 VIP 不是 VIP"""
        info = SubscriptionInfo(
            plan=Plan.LIFETIME_VIP,
            status=SubscriptionStatus.EXPIRED,
        )
        assert info.is_vip is False


class TestUsageStats:
    """UsageStats 测试"""
    
    def test_get_count(self):
        """测试获取使用次数"""
        stats = UsageStats(
            date="2026-01-10",
            translation_count=5,
            web_to_markdown_count=2,
        )
        assert stats.get_count("translation") == 5
        assert stats.get_count("web_to_markdown") == 2
        assert stats.get_count("unknown") == 0
    
    def test_increment(self):
        """测试增加使用次数"""
        stats = UsageStats(date="2026-01-10")
        assert stats.translation_count == 0
        
        stats.increment("translation")
        assert stats.translation_count == 1
        
        stats.increment("translation")
        assert stats.translation_count == 2
        
        stats.increment("web_to_markdown")
        assert stats.web_to_markdown_count == 1


class TestLicenseCache:
    """LicenseCache 测试"""
    
    def test_is_valid_within_ttl(self):
        """缓存在 TTL 内有效"""
        cache = LicenseCache(
            subscription=SubscriptionInfo.free(),
            cached_at=datetime.now(),
            last_verified_at=datetime.now(),
        )
        assert cache.is_valid(ttl_hours=24) is True
    
    def test_is_valid_expired(self):
        """缓存过期后无效"""
        cache = LicenseCache(
            subscription=SubscriptionInfo.free(),
            cached_at=datetime.now() - timedelta(hours=25),
            last_verified_at=datetime.now() - timedelta(hours=25),
        )
        assert cache.is_valid(ttl_hours=24) is False
    
    def test_is_in_grace_period(self):
        """宽限期内有效"""
        cache = LicenseCache(
            subscription=SubscriptionInfo.vip(),
            cached_at=datetime.now() - timedelta(days=2),
            last_verified_at=datetime.now() - timedelta(days=2),
        )
        assert cache.is_in_grace_period(grace_days=7) is True
    
    def test_grace_period_expired(self):
        """宽限期过期"""
        cache = LicenseCache(
            subscription=SubscriptionInfo.vip(),
            cached_at=datetime.now() - timedelta(days=10),
            last_verified_at=datetime.now() - timedelta(days=10),
        )
        assert cache.is_in_grace_period(grace_days=7) is False
    
    def test_to_dict_and_from_dict(self):
        """测试序列化和反序列化"""
        original = LicenseCache(
            subscription=SubscriptionInfo.vip(),
            cached_at=datetime.now(),
            last_verified_at=datetime.now(),
            user_id="test-user-id",
            user_email="test@example.com",
        )
        
        data = original.to_dict()
        restored = LicenseCache.from_dict(data)
        
        assert restored.subscription.plan == original.subscription.plan
        assert restored.subscription.status == original.subscription.status
        assert restored.user_id == original.user_id
        assert restored.user_email == original.user_email
