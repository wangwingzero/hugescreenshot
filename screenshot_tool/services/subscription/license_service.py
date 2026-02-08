"""
许可证服务 - 管理订阅验证和缓存

Feature: subscription-system
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.1, 7.2, 7.3, 7.4, 7.5
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from supabase import Client

from .models import Plan, SubscriptionStatus, SubscriptionInfo, LicenseCache

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def license_log(message: str):
    """许可证服务日志"""
    _debug_log(message, "LICENSE")


class LicenseService:
    """许可证服务
    
    管理订阅状态验证、本地缓存和宽限期。
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.1, 7.2, 7.3, 7.4, 7.5
    
    Attributes:
        _client: Supabase 客户端
        _user_id: 当前用户 ID
        _cache: 本地缓存
        _cache_path: 缓存文件路径
    """
    
    # 缓存配置
    CACHE_TTL_HOURS = 24  # 24 小时
    GRACE_PERIOD_DAYS = 7  # 7 天宽限期
    
    def __init__(
        self, 
        client: Client, 
        user_id: str,
        cache_dir: Optional[str] = None,
        user_email: Optional[str] = None
    ):
        """初始化许可证服务
        
        Args:
            client: Supabase 客户端
            user_id: 当前用户 ID
            cache_dir: 缓存目录，默认 ~/.screenshot_tool/
            user_email: 用户邮箱（用于缓存显示）
            
        Raises:
            ValueError: 如果 user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        
        self._client = client
        self._user_id = user_id.strip()
        self._user_email = user_email
        
        # 设置缓存路径
        if cache_dir is None:
            # 使用统一的用户数据目录
            from screenshot_tool.core.config_manager import get_user_data_dir
            cache_dir = get_user_data_dir()
        
        self._cache_dir = cache_dir
        self._cache_path = os.path.join(cache_dir, "license_cache.json")
        
        # 加载缓存
        self._cache: Optional[LicenseCache] = self._load_cache()
    
    def _ensure_cache_dir(self) -> None:
        """确保缓存目录存在"""
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> Optional[LicenseCache]:
        """从文件加载缓存
        
        Returns:
            LicenseCache: 缓存数据，不存在返回 None
        """
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 验证用户 ID 匹配
                if data.get("user_id") != self._user_id:
                    license_log("缓存用户不匹配，忽略缓存")
                    return None
                
                return LicenseCache.from_dict(data)
        except Exception as e:
            license_log(f"加载缓存失败: {e}")
        
        return None
    
    def _save_cache(self, cache: LicenseCache) -> None:
        """保存缓存到文件
        
        Args:
            cache: 缓存数据
        """
        try:
            self._ensure_cache_dir()
            
            data = cache.to_dict()
            
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self._cache = cache
            license_log("缓存已保存")
            
        except Exception as e:
            license_log(f"保存缓存失败: {e}")
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效
        
        Requirements: 7.2
        
        只有 VIP 用户的缓存才有效，免费用户每次都从服务器获取最新状态。
        这样用户升级后能立即生效。
        
        Returns:
            bool: 缓存是否在 TTL 内
        """
        if self._cache is None:
            return False
        
        # 免费用户不使用缓存，每次都查服务器（方便升级后立即生效）
        if not self._cache.subscription.is_vip:
            license_log("免费用户，跳过缓存")
            return False
        
        return self._cache.is_valid(ttl_hours=self.CACHE_TTL_HOURS)
    
    def _is_in_grace_period(self) -> bool:
        """检查是否在宽限期内
        
        Requirements: 7.3, 7.4
        
        Returns:
            bool: 是否在宽限期内
        """
        if self._cache is None:
            return False
        
        return self._cache.is_in_grace_period(grace_days=self.GRACE_PERIOD_DAYS)
    
    def verify(self, force: bool = False) -> SubscriptionInfo:
        """验证订阅状态
        
        Requirements: 2.3, 2.4, 2.5, 2.6, 7.1
        
        验证流程：
        1. 如果不强制刷新且缓存有效，返回缓存
        2. 尝试从服务器获取最新状态
        3. 如果网络失败且在宽限期内，返回缓存
        4. 否则返回免费计划
        
        Args:
            force: 是否强制刷新（忽略缓存）
            
        Returns:
            SubscriptionInfo: 订阅信息
        """
        # 1. 检查缓存
        if not force and self._is_cache_valid():
            license_log("使用缓存的订阅信息")
            return self._cache.subscription
        
        # 2. 尝试从服务器获取
        try:
            subscription = self._fetch_from_server()
            
            # 更新缓存（包含 user_email）
            now = datetime.now()
            cache = LicenseCache(
                subscription=subscription,
                cached_at=now,
                last_verified_at=now,
                user_id=self._user_id,
                user_email=self._user_email,
            )
            self._save_cache(cache)
            
            license_log(f"订阅验证成功: {subscription.plan.value}")
            return subscription
            
        except Exception as e:
            license_log(f"服务器验证失败: {e}")
            
            # 3. 检查宽限期
            if self._is_in_grace_period():
                license_log("在宽限期内，使用缓存")
                return self._cache.subscription
            
            # 4. 返回免费计划
            license_log("无法验证，返回免费计划")
            return SubscriptionInfo.free()
    
    def _fetch_from_server(self) -> SubscriptionInfo:
        """从服务器获取订阅信息
        
        Returns:
            SubscriptionInfo: 订阅信息
            
        Raises:
            Exception: 网络或数据库错误
        """
        response = self._client.table("subscriptions").select("*").eq(
            "user_id", self._user_id
        ).execute()
        
        if not response.data:
            # 没有订阅记录，返回免费计划
            return SubscriptionInfo.free()
        
        row = response.data[0]
        
        # 解析计划类型
        plan_str = row.get("plan", "free").lower()
        try:
            plan = Plan(plan_str)
        except ValueError:
            plan = Plan.FREE
        
        # 解析状态
        status_str = row.get("status", "active").lower()
        try:
            status = SubscriptionStatus(status_str)
        except ValueError:
            status = SubscriptionStatus.ACTIVE
        
        # 解析赞助时间
        purchased_at = None
        if row.get("purchased_at"):
            try:
                purchased_at = datetime.fromisoformat(row["purchased_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return SubscriptionInfo(
            plan=plan,
            status=status,
            purchased_at=purchased_at,
        )
    
    def get_subscription(self) -> SubscriptionInfo:
        """获取当前订阅信息（使用缓存）
        
        Returns:
            SubscriptionInfo: 订阅信息
        """
        return self.verify(force=False)
    
    def is_vip(self) -> bool:
        """检查是否为 VIP 用户
        
        Requirements: 2.1, 2.2
        
        Returns:
            bool: 是否为 VIP
        """
        subscription = self.get_subscription()
        return subscription.is_vip
    
    def clear_cache(self) -> None:
        """清除本地缓存"""
        try:
            if os.path.exists(self._cache_path):
                os.remove(self._cache_path)
            self._cache = None
            license_log("缓存已清除")
        except Exception as e:
            license_log(f"清除缓存失败: {e}")
    
    def get_cache_info(self) -> dict:
        """获取缓存信息（用于调试）
        
        Returns:
            dict: 缓存状态信息
        """
        if self._cache is None:
            return {"has_cache": False}
        
        return {
            "has_cache": True,
            "plan": self._cache.subscription.plan.value,
            "status": self._cache.subscription.status.value,
            "cached_at": self._cache.cached_at.isoformat(),
            "is_valid": self._is_cache_valid(),
            "is_in_grace_period": self._is_in_grace_period(),
        }
