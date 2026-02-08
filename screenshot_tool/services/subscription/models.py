"""
订阅系统数据模型

定义订阅系统使用的所有数据类和枚举。

Feature: subscription-system
Requirements: 6.1, 6.2, 6.3, 6.4
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Plan(Enum):
    """订阅计划类型"""
    FREE = "free"
    LIFETIME_VIP = "lifetime_vip"


class SubscriptionStatus(Enum):
    """订阅状态"""
    ACTIVE = "active"
    EXPIRED = "expired"


@dataclass
class User:
    """用户信息
    
    Attributes:
        id: 用户唯一标识（UUID）
        email: 用户邮箱
        nickname: 昵称（可选）
        avatar_url: 头像 URL（可选）
    """
    id: str
    email: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


@dataclass
class SubscriptionInfo:
    """订阅信息
    
    Attributes:
        plan: 订阅计划类型
        status: 订阅状态
        purchased_at: VIP 赞助时间（可选）
    
    Property 7: VIP has unlimited access
    Validates: Requirements 4.6
    """
    plan: Plan
    status: SubscriptionStatus
    purchased_at: Optional[datetime] = None
    
    @property
    def is_vip(self) -> bool:
        """是否是 VIP 用户
        
        只有当计划是 LIFETIME_VIP 且状态是 ACTIVE 时才返回 True。
        
        Returns:
            bool: 是否是有效的 VIP 用户
        """
        return self.plan == Plan.LIFETIME_VIP and self.status == SubscriptionStatus.ACTIVE
    
    @classmethod
    def free(cls) -> "SubscriptionInfo":
        """创建免费版订阅信息"""
        return cls(plan=Plan.FREE, status=SubscriptionStatus.ACTIVE)
    
    @classmethod
    def vip(cls, purchased_at: Optional[datetime] = None) -> "SubscriptionInfo":
        """创建 VIP 订阅信息"""
        return cls(
            plan=Plan.LIFETIME_VIP,
            status=SubscriptionStatus.ACTIVE,
            purchased_at=purchased_at or datetime.now()
        )


@dataclass
class Device:
    """设备信息
    
    Attributes:
        id: 设备记录 ID（UUID）
        machine_id: 设备唯一标识（哈希值）
        device_name: 设备名称（可选）
        os_version: 操作系统版本（可选）
        app_version: 应用版本（可选）
        is_active: 是否激活
        last_active_at: 最后活跃时间
        created_at: 创建时间（可选）
    """
    id: str
    machine_id: str
    device_name: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    is_active: bool = True
    last_active_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class UsageStats:
    """使用统计
    
    记录用户每日的功能使用次数。
    
    Attributes:
        date: 日期（YYYY-MM-DD 格式）
        translation_count: 翻译使用次数
        web_to_markdown_count: 网页转 Markdown 使用次数
    """
    date: str  # YYYY-MM-DD
    translation_count: int = 0
    web_to_markdown_count: int = 0
    
    def get_count(self, feature: str) -> int:
        """获取指定功能的使用次数
        
        Args:
            feature: 功能名称（translation, web_to_markdown）
            
        Returns:
            使用次数
        """
        if feature == "translation":
            return self.translation_count
        elif feature == "web_to_markdown":
            return self.web_to_markdown_count
        return 0
    
    def increment(self, feature: str) -> None:
        """增加指定功能的使用次数
        
        Args:
            feature: 功能名称
        """
        if feature == "translation":
            self.translation_count += 1
        elif feature == "web_to_markdown":
            self.web_to_markdown_count += 1


@dataclass
class LicenseCache:
    """许可证缓存
    
    用于本地缓存订阅信息，支持离线使用。
    
    Attributes:
        subscription: 订阅信息
        cached_at: 缓存时间
        last_verified_at: 最后验证时间
        user_id: 用户 ID（可选）
        user_email: 用户邮箱（可选）
    """
    subscription: SubscriptionInfo
    cached_at: datetime
    last_verified_at: datetime
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    
    def is_valid(self, ttl_hours: int = 24) -> bool:
        """检查缓存是否有效
        
        Args:
            ttl_hours: 缓存有效期（小时）
            
        Returns:
            bool: 缓存是否在有效期内
        """
        from datetime import timedelta
        now = datetime.now()
        return now - self.cached_at < timedelta(hours=ttl_hours)
    
    def is_in_grace_period(self, grace_days: int = 7) -> bool:
        """检查是否在宽限期内
        
        Args:
            grace_days: 宽限期天数
            
        Returns:
            bool: 是否在宽限期内
        """
        from datetime import timedelta
        now = datetime.now()
        return now - self.last_verified_at < timedelta(days=grace_days)
    
    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "subscription": {
                "plan": self.subscription.plan.value,
                "status": self.subscription.status.value,
                "purchased_at": self.subscription.purchased_at.isoformat() if self.subscription.purchased_at else None,
            },
            "cached_at": self.cached_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat(),
            "user_id": self.user_id,
            "user_email": self.user_email,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "LicenseCache":
        """从字典创建缓存对象"""
        sub_data = data.get("subscription", {})
        purchased_at = None
        if sub_data.get("purchased_at"):
            purchased_at = datetime.fromisoformat(sub_data["purchased_at"])
        
        subscription = SubscriptionInfo(
            plan=Plan(sub_data.get("plan", "free")),
            status=SubscriptionStatus(sub_data.get("status", "active")),
            purchased_at=purchased_at,
        )
        
        return cls(
            subscription=subscription,
            cached_at=datetime.fromisoformat(data["cached_at"]),
            last_verified_at=datetime.fromisoformat(data["last_verified_at"]),
            user_id=data.get("user_id"),
            user_email=data.get("user_email"),
        )


@dataclass
class AuthResult:
    """认证结果
    
    Attributes:
        success: 是否成功
        user: 用户信息（成功时）
        token: 访问令牌（成功时）
        error: 错误信息（失败时）
    """
    success: bool
    user: Optional[User] = None
    token: Optional[str] = None
    error: Optional[str] = None
    
    @classmethod
    def ok(cls, user: User, token: str) -> "AuthResult":
        """创建成功结果"""
        return cls(success=True, user=user, token=token)
    
    @classmethod
    def fail(cls, error: str) -> "AuthResult":
        """创建失败结果"""
        return cls(success=False, error=error)
