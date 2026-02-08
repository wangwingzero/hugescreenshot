"""
订阅系统模块

提供用户认证、订阅管理、功能门控等功能。

Feature: subscription-system
"""

from .models import (
    Plan,
    SubscriptionStatus,
    User,
    SubscriptionInfo,
    Device,
    UsageStats,
    LicenseCache,
    AuthResult,
)
from .auth_service import AuthService
from .license_service import LicenseService
from .usage_tracker import UsageTracker, DAILY_LIMITS
from .feature_gate import FeatureGate, Feature, AccessResult, FEATURE_CONFIG
from .integration import (
    init_feature_gate,
    get_feature_gate,
    check_feature,
    use_feature,
    can_use,
    get_feature_status,
    require_feature,
    with_feature_check,
    can_translate,
    can_web_to_markdown,
    can_screen_record,
    can_use_gongwen,
    can_use_caac,
    use_translation,
    use_web_to_markdown,
    use_screen_record,
    use_gongwen,
    use_caac,
)
from .manager import SubscriptionManager, SubscriptionState
from .payment_service import PaymentService, Order, OrderStatus, PaymentResult, OrderQueryResult
from .exceptions import (
    SubscriptionError,
    NetworkError,
    AuthError,
    InvalidCredentialsError,
    EmailNotVerifiedError,
    SessionExpiredError,
    DeviceLimitError,
    FeatureNotAvailableError,
    DailyLimitExceededError,
    VIPOnlyError,
    LicenseError,
    LicenseExpiredError,
    GracePeriodExpiredError,
    SponsorError,
    SponsorUrlGenerationError,
    OrderVerificationError,
    OrderNotFoundError,
    OrderAlreadyUsedError,
)

__all__ = [
    # Models
    "Plan",
    "SubscriptionStatus",
    "User",
    "SubscriptionInfo",
    "Device",
    "UsageStats",
    "LicenseCache",
    "AuthResult",
    # Services
    "AuthService",
    "LicenseService",
    "UsageTracker",
    "DAILY_LIMITS",
    # Feature Gate
    "FeatureGate",
    "Feature",
    "AccessResult",
    "FEATURE_CONFIG",
    # Integration
    "init_feature_gate",
    "get_feature_gate",
    "check_feature",
    "use_feature",
    "can_use",
    "get_feature_status",
    "require_feature",
    "with_feature_check",
    "can_translate",
    "can_web_to_markdown",
    "can_screen_record",
    "can_use_gongwen",
    "can_use_caac",
    "use_translation",
    "use_web_to_markdown",
    "use_screen_record",
    "use_gongwen",
    "use_caac",
    # Manager
    "SubscriptionManager",
    "SubscriptionState",
    # Payment
    "PaymentService",
    "Order",
    "OrderStatus",
    "PaymentResult",
    "OrderQueryResult",
    # Exceptions
    "SubscriptionError",
    "NetworkError",
    "AuthError",
    "InvalidCredentialsError",
    "EmailNotVerifiedError",
    "SessionExpiredError",
    "DeviceLimitError",
    "FeatureNotAvailableError",
    "DailyLimitExceededError",
    "VIPOnlyError",
    "LicenseError",
    "LicenseExpiredError",
    "GracePeriodExpiredError",
    "SponsorError",
    "SponsorUrlGenerationError",
    "OrderVerificationError",
    "OrderNotFoundError",
    "OrderAlreadyUsedError",
]
