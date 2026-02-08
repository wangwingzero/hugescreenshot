"""
许可证服务测试

Feature: subscription-system
Property 9: Cache and grace period behavior
Validates: Requirements 2.3, 2.4, 2.5, 2.6, 7.1, 7.2, 7.3, 7.4
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
import pytest
from unittest.mock import Mock, MagicMock, patch
from hypothesis import given, strategies as st, assume, settings

from screenshot_tool.services.subscription.license_service import LicenseService
from screenshot_tool.services.subscription.models import Plan, SubscriptionStatus, SubscriptionInfo, LicenseCache


class TestLicenseServiceCache:
    """缓存测试"""
    
    def test_cache_is_saved_after_verify(self):
        """测试验证后缓存被保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            
            # 模拟服务器返回 VIP 订阅
            mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "user_id": "user-123",
                    "plan": "lifetime_vip",
                    "status": "active",
                }]
            )
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            subscription = service.verify(force=True)
            
            # 验证缓存文件存在
            cache_path = os.path.join(tmpdir, "license_cache.json")
            assert os.path.exists(cache_path)
            
            # 验证缓存内容
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            assert cache_data["user_id"] == "user-123"
            assert cache_data["subscription"]["plan"] == "lifetime_vip"
            assert cache_data["subscription"]["status"] == "active"
    
    def test_cache_is_loaded_on_init(self):
        """测试初始化时加载缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 预先创建缓存文件
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": now.isoformat(),
                "last_verified_at": now.isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            # 验证缓存被加载
            assert service._cache is not None
            assert service._cache.subscription.plan == Plan.LIFETIME_VIP
    
    def test_cache_ignored_if_user_mismatch(self):
        """测试用户不匹配时忽略缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建其他用户的缓存
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "other-user",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": now.isoformat(),
                "last_verified_at": now.isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            # 缓存应该被忽略
            assert service._cache is None


class TestCacheAndGracePeriod:
    """缓存和宽限期测试
    
    Property 9: Cache and grace period behavior
    """
    
    @given(
        cache_age_hours=st.integers(min_value=0, max_value=200),
        last_verified_days=st.integers(min_value=0, max_value=14),
    )
    @settings(max_examples=50)
    def test_cache_and_grace_period_property(
        self, cache_age_hours: int, last_verified_days: int
    ):
        """Property 9: 缓存和宽限期行为
        
        Feature: subscription-system, Property 9: Cache and grace period behavior
        Validates: Requirements 2.3, 2.4, 2.5, 2.6, 7.1, 7.2, 7.3, 7.4
        
        - 缓存有效期 24 小时
        - 宽限期 7 天
        - 网络失败时使用缓存或宽限期
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            cached_at = now - timedelta(hours=cache_age_hours)
            last_verified_at = now - timedelta(days=last_verified_days)
            
            # 创建缓存
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": cached_at.isoformat(),
                "last_verified_at": last_verified_at.isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            # 验证缓存有效性逻辑
            cache_valid = cache_age_hours < 24
            in_grace_period = last_verified_days < 7
            
            assert service._is_cache_valid() == cache_valid
            assert service._is_in_grace_period() == in_grace_period
    
    def test_uses_cache_when_valid(self):
        """测试缓存有效时使用缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建有效缓存（1 小时前）
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": (now - timedelta(hours=1)).isoformat(),
                "last_verified_at": (now - timedelta(hours=1)).isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            # 不强制刷新，应该使用缓存
            subscription = service.verify(force=False)
            
            assert subscription.plan == Plan.LIFETIME_VIP
            # 不应该调用服务器
            mock_client.table.assert_not_called()
    
    def test_fetches_from_server_when_cache_expired(self):
        """测试缓存过期时从服务器获取"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建过期缓存（25 小时前）
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": (now - timedelta(hours=25)).isoformat(),
                "last_verified_at": (now - timedelta(hours=25)).isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            # 模拟服务器返回免费计划
            mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "user_id": "user-123",
                    "plan": "free",
                    "status": "active",
                }]
            )
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            subscription = service.verify(force=False)
            
            # 应该从服务器获取
            assert subscription.plan == Plan.FREE
            mock_client.table.assert_called()
    
    def test_uses_grace_period_when_network_fails(self):
        """测试网络失败时使用宽限期"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建过期缓存但在宽限期内（3 天前验证）
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": (now - timedelta(hours=25)).isoformat(),  # 缓存过期
                "last_verified_at": (now - timedelta(days=3)).isoformat(),  # 3 天前验证，在宽限期内
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            # 模拟网络错误
            mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("Network error")
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            subscription = service.verify(force=False)
            
            # 应该使用宽限期内的缓存
            assert subscription.plan == Plan.LIFETIME_VIP
    
    def test_returns_free_when_grace_period_expired(self):
        """测试宽限期过期时返回免费计划"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建过期缓存且宽限期已过（10 天前验证）
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": (now - timedelta(hours=25)).isoformat(),  # 缓存过期
                "last_verified_at": (now - timedelta(days=10)).isoformat(),  # 10 天前验证，宽限期已过
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            # 模拟网络错误
            mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("Network error")
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            subscription = service.verify(force=False)
            
            # 应该返回免费计划
            assert subscription.plan == Plan.FREE


class TestIsVip:
    """VIP 检查测试"""
    
    def test_is_vip_returns_true_for_lifetime_vip(self):
        """测试终身 VIP 返回 True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "user_id": "user-123",
                    "plan": "lifetime_vip",
                    "status": "active",
                }]
            )
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            assert service.is_vip() is True
    
    def test_is_vip_returns_false_for_free(self):
        """测试免费用户返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "user_id": "user-123",
                    "plan": "free",
                    "status": "active",
                }]
            )
            
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            assert service.is_vip() is False


class TestClearCache:
    """清除缓存测试"""
    
    def test_clear_cache_removes_file(self):
        """测试清除缓存删除文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            # 创建缓存文件
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "free",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": now.isoformat(),
                "last_verified_at": now.isoformat(),
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            service.clear_cache()
            
            assert not os.path.exists(cache_path)
            assert service._cache is None


class TestGetCacheInfo:
    """缓存信息测试"""
    
    def test_get_cache_info_no_cache(self):
        """测试无缓存时的信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            info = service.get_cache_info()
            
            assert info["has_cache"] is False
    
    def test_get_cache_info_with_cache(self):
        """测试有缓存时的信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            now = datetime.now()
            
            cache_path = os.path.join(tmpdir, "license_cache.json")
            cache_data = {
                "user_id": "user-123",
                "subscription": {
                    "plan": "lifetime_vip",
                    "status": "active",
                    "purchased_at": None,
                },
                "cached_at": (now - timedelta(hours=1)).isoformat(),
                "last_verified_at": (now - timedelta(hours=1)).isoformat(),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            mock_client = MagicMock()
            service = LicenseService(mock_client, "user-123", cache_dir=tmpdir)
            
            info = service.get_cache_info()
            
            assert info["has_cache"] is True
            assert info["plan"] == "lifetime_vip"
            assert info["is_valid"] is True
