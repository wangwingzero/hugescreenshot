"""
订阅系统自定义异常

Feature: subscription-system
Requirements: 1.4, 3.3, 4.5
"""


class SubscriptionError(Exception):
    """订阅系统基础异常"""
    pass


class NetworkError(SubscriptionError):
    """网络错误
    
    当无法连接到 Supabase 服务器时抛出。
    """
    
    def __init__(self, message: str = "网络连接失败，请检查网络设置"):
        self.message = message
        super().__init__(self.message)


class AuthError(SubscriptionError):
    """认证错误
    
    Requirements: 1.4
    
    当登录、注册或会话验证失败时抛出。
    """
    
    def __init__(self, message: str = "认证失败"):
        self.message = message
        super().__init__(self.message)


class InvalidCredentialsError(AuthError):
    """无效凭证错误
    
    当邮箱或密码错误时抛出。
    """
    
    def __init__(self, message: str = "邮箱或密码错误"):
        super().__init__(message)


class EmailNotVerifiedError(AuthError):
    """邮箱未验证错误"""
    
    def __init__(self, message: str = "请先验证您的邮箱"):
        super().__init__(message)


class SessionExpiredError(AuthError):
    """会话过期错误"""
    
    def __init__(self, message: str = "登录已过期，请重新登录"):
        super().__init__(message)


class DeviceLimitError(SubscriptionError):
    """设备限制错误
    
    Requirements: 3.3
    
    当设备数量超过限制时抛出。
    """
    
    def __init__(
        self, 
        message: str = "设备数量已达上限",
        current_count: int = 0,
        max_count: int = 3
    ):
        self.message = message
        self.current_count = current_count
        self.max_count = max_count
        super().__init__(self.message)


class FeatureNotAvailableError(SubscriptionError):
    """功能不可用错误
    
    Requirements: 4.5
    
    当用户尝试使用无权限的功能时抛出。
    """
    
    def __init__(
        self, 
        feature: str,
        reason: str = "此功能不可用",
        upgrade_hint: str = None
    ):
        self.feature = feature
        self.reason = reason
        self.upgrade_hint = upgrade_hint or "☕ 请作者喝杯咖啡，赞助开发可解锁此功能"
        self.message = f"{feature}: {reason}"
        super().__init__(self.message)


class DailyLimitExceededError(FeatureNotAvailableError):
    """每日限制超出错误
    
    当功能的每日使用次数已用完时抛出。
    """
    
    def __init__(
        self, 
        feature: str,
        limit: int,
        used: int = None
    ):
        self.limit = limit
        self.used = used or limit
        reason = f"今日使用次数已达上限（{limit} 次）"
        upgrade_hint = "☕ 请作者喝杯咖啡，赞助开发可无限使用"
        super().__init__(feature, reason, upgrade_hint)


class VIPOnlyError(FeatureNotAvailableError):
    """VIP 专属功能错误
    
    当免费用户尝试使用 VIP 专属功能时抛出。
    """
    
    def __init__(self, feature: str):
        reason = "此功能仅限 VIP 用户"
        upgrade_hint = "☕ 请作者喝杯咖啡，赞助开发可解锁此功能"
        super().__init__(feature, reason, upgrade_hint)


class LicenseError(SubscriptionError):
    """许可证错误
    
    当许可证验证失败时抛出。
    """
    
    def __init__(self, message: str = "许可证验证失败"):
        self.message = message
        super().__init__(self.message)


class LicenseExpiredError(LicenseError):
    """许可证过期错误"""
    
    def __init__(self, message: str = "许可证已过期"):
        super().__init__(message)


class GracePeriodExpiredError(LicenseError):
    """宽限期过期错误
    
    当离线宽限期已过时抛出。
    """
    
    def __init__(self, message: str = "离线宽限期已过，请连接网络验证"):
        super().__init__(message)


# ============================================================================
# 赞助相关异常
# Feature: afdian-payment-integration
# Requirements: 6.2, 6.3
# ============================================================================

class SponsorError(SubscriptionError):
    """赞助错误基类
    
    所有赞助相关错误的基类。
    """
    
    def __init__(self, message: str = "赞助操作失败"):
        self.message = message
        super().__init__(self.message)


class SponsorUrlGenerationError(SponsorError):
    """赞助链接生成错误
    
    当无法生成赞助链接时抛出。
    """
    
    def __init__(self, message: str = "无法生成赞助链接"):
        super().__init__(message)


class OrderVerificationError(SponsorError):
    """订单验证错误
    
    当订单验证失败时抛出。
    """
    
    def __init__(self, message: str = "订单验证失败"):
        super().__init__(message)


class OrderNotFoundError(OrderVerificationError):
    """订单不存在错误
    
    当指定的订单号不存在时抛出。
    """
    
    def __init__(self, order_id: str = None):
        self.order_id = order_id
        message = f"订单 {order_id} 不存在" if order_id else "订单不存在"
        super().__init__(message)


class OrderAlreadyUsedError(OrderVerificationError):
    """订单已使用错误
    
    当订单已被其他用户使用时抛出。
    """
    
    def __init__(self, order_id: str = None):
        self.order_id = order_id
        message = "此订单已被使用"
        super().__init__(message)
