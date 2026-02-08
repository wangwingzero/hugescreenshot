"""
使用量追踪器测试

Feature: subscription-system
Property 8: Usage tracking accuracy
Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""

import json
import os
import tempfile
from datetime import date, timedelta
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.services.subscription.usage_tracker import (
    UsageTracker, DAILY_LIMITS
)


class TestUsageTracking:
    """使用量追踪测试
    
    Property 8: Usage tracking accuracy
    """
    
    def test_initial_usage_is_zero(self):
        """测试初始使用量为零"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            assert tracker.get_usage("translation") == 0
            assert tracker.get_usage("web_to_markdown") == 0
    
    def test_increment_increases_usage(self):
        """测试增加使用量"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            assert tracker.increment("translation") is True
            assert tracker.get_usage("translation") == 1
            
            assert tracker.increment("translation") is True
            assert tracker.get_usage("translation") == 2
    
    @given(
        feature=st.sampled_from(["translation", "web_to_markdown"]),
        increments=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=30)
    def test_usage_tracking_accuracy_property(
        self, feature: str, increments: int
    ):
        """Property 8: 使用量追踪准确性
        
        Feature: subscription-system, Property 8: Usage tracking accuracy
        Validates: Requirements 5.1, 5.2
        
        - 使用量准确记录
        - 剩余次数正确计算
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            limit = DAILY_LIMITS[feature]
            
            # 执行增量
            successful = 0
            for _ in range(increments):
                if tracker.increment(feature):
                    successful += 1
            
            # 验证使用量
            expected_usage = min(increments, limit)
            assert tracker.get_usage(feature) == expected_usage
            
            # 验证剩余次数
            expected_remaining = max(0, limit - expected_usage)
            assert tracker.get_remaining(feature) == expected_remaining
            
            # 验证成功次数
            assert successful == expected_usage


class TestDailyLimits:
    """每日限制测试"""
    
    def test_translation_limit_is_10(self):
        """测试翻译限制为 10"""
        assert DAILY_LIMITS["translation"] == 10
    
    def test_web_to_markdown_limit_is_5(self):
        """测试网页转 Markdown 限制为 5"""
        assert DAILY_LIMITS["web_to_markdown"] == 5
    
    def test_cannot_exceed_limit(self):
        """测试不能超过限制"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            # 使用完所有翻译次数
            for _ in range(10):
                assert tracker.increment("translation") is True
            
            # 第 11 次应该失败
            assert tracker.increment("translation") is False
            assert tracker.get_usage("translation") == 10
    
    def test_unlimited_feature(self):
        """测试无限制功能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            # 未定义限制的功能应该无限制
            for _ in range(100):
                assert tracker.increment("screenshot") is True
            
            assert tracker.get_usage("screenshot") == 100
            assert tracker.get_remaining("screenshot") == -1


class TestCanUse:
    """可用性检查测试"""
    
    def test_can_use_when_under_limit(self):
        """测试未达限制时可以使用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            assert tracker.can_use("translation") is True
    
    def test_cannot_use_when_at_limit(self):
        """测试达到限制时不能使用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            # 使用完所有次数
            for _ in range(10):
                tracker.increment("translation")
            
            assert tracker.can_use("translation") is False


class TestCachePersistence:
    """缓存持久化测试"""
    
    def test_cache_is_saved(self):
        """测试缓存被保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            tracker.increment("translation")
            
            # 验证缓存文件存在
            cache_path = os.path.join(tmpdir, "usage_cache.json")
            assert os.path.exists(cache_path)
            
            # 验证缓存内容
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert data["user_id"] == "user-123"
            today = date.today().isoformat()
            assert data["usage"][today]["translation"] == 1
    
    def test_cache_is_loaded(self):
        """测试缓存被加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today().isoformat()
            
            # 预先创建缓存
            cache_path = os.path.join(tmpdir, "usage_cache.json")
            cache_data = {
                "user_id": "user-123",
                "usage": {
                    today: {"translation": 5}
                }
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            # 创建新的 tracker
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            assert tracker.get_usage("translation") == 5
    
    def test_cache_ignored_if_user_mismatch(self):
        """测试用户不匹配时忽略缓存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            today = date.today().isoformat()
            
            # 创建其他用户的缓存
            cache_path = os.path.join(tmpdir, "usage_cache.json")
            cache_data = {
                "user_id": "other-user",
                "usage": {
                    today: {"translation": 5}
                }
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            # 创建新的 tracker
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            # 应该忽略缓存
            assert tracker.get_usage("translation") == 0


class TestMidnightReset:
    """午夜重置测试
    
    Requirements: 5.3
    """
    
    def test_old_data_is_cleaned(self):
        """测试旧数据被清理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            today = date.today().isoformat()
            
            # 创建包含昨天数据的缓存
            cache_path = os.path.join(tmpdir, "usage_cache.json")
            cache_data = {
                "user_id": "user-123",
                "usage": {
                    yesterday: {"translation": 10},
                    today: {"translation": 3},
                }
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            
            # 创建新的 tracker（会触发午夜重置检查）
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            # 今天的数据应该保留
            assert tracker.get_usage("translation") == 3
            
            # 昨天的数据应该被清理
            assert yesterday not in tracker._cache


class TestGetAllUsage:
    """获取所有使用量测试"""
    
    def test_get_all_usage_today(self):
        """测试获取今日所有使用量"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(None, "user-123", cache_dir=tmpdir)
            
            tracker.increment("translation")
            tracker.increment("translation")
            tracker.increment("web_to_markdown")
            
            usage = tracker.get_all_usage_today()
            
            assert usage["translation"] == 2
            assert usage["web_to_markdown"] == 1


class TestInputValidation:
    """输入验证测试"""
    
    def test_empty_user_id_raises_error(self):
        """测试空用户 ID 抛出错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="user_id 不能为空"):
                UsageTracker(None, "", cache_dir=tmpdir)
    
    def test_whitespace_user_id_raises_error(self):
        """测试空白用户 ID 抛出错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="user_id 不能为空"):
                UsageTracker(None, "   ", cache_dir=tmpdir)
