"""
功能门控 - 控制功能访问权限

Feature: subscription-system
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Any

from .license_service import LicenseService
from .usage_tracker import UsageTracker, DAILY_LIMITS

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def gate_log(message: str):
    """功能门控日志"""
    _debug_log(message, "GATE")


class Feature(Enum):
    """功能枚举"""
    # 基础功能（所有用户无限制）
    SCREENSHOT = "screenshot"
    OCR = "ocr"
    HIGHLIGHT = "highlight"
    DING = "ding"
    
    # 受限功能（免费用户有每日限制）
    TRANSLATION = "translation"
    WEB_TO_MARKDOWN = "web_to_markdown"
    
    # VIP 专属功能
    SCREEN_RECORDER = "screen_recorder"
    GONGWEN = "gongwen"
    CAAC = "caac"
    ANKI = "anki"  # Anki 制卡


@dataclass
class AccessResult:
    """访问检查结果"""
    allowed: bool
    reason: str
    remaining: Optional[int] = None  # 剩余次数，None 表示无限制
    upgrade_hint: Optional[str] = None  # 升级提示
    
    @classmethod
    def allow(cls, remaining: Optional[int] = None) -> "AccessResult":
        """允许访问"""
        return cls(allowed=True, reason="允许访问", remaining=remaining)
    
    @classmethod
    def deny(cls, reason: str, upgrade_hint: Optional[str] = None) -> "AccessResult":
        """拒绝访问"""
        return cls(allowed=False, reason=reason, upgrade_hint=upgrade_hint)


# 功能配置
# free: 免费用户是否可用
# vip: VIP 用户是否可用
# limited: 是否有每日限制（仅对免费用户生效）
# limit_key: 限制对应的 key（用于 UsageTracker）
FEATURE_CONFIG: Dict[Feature, Dict[str, Any]] = {
    # 基础功能 - 所有用户无限制
    Feature.SCREENSHOT: {"free": True, "vip": True, "limited": False},
    Feature.OCR: {"free": True, "vip": True, "limited": False},
    Feature.HIGHLIGHT: {"free": True, "vip": True, "limited": False},
    Feature.DING: {"free": True, "vip": True, "limited": False},
    
    # 受限功能 - 免费用户有每日限制
    Feature.TRANSLATION: {"free": True, "vip": True, "limited": True, "limit_key": "translation"},
    Feature.WEB_TO_MARKDOWN: {"free": True, "vip": True, "limited": True, "limit_key": "web_to_markdown"},
    
    # VIP 专属功能
    Feature.SCREEN_RECORDER: {"free": False, "vip": True, "limited": False},
    Feature.GONGWEN: {"free": False, "vip": True, "limited": False},
    Feature.CAAC: {"free": False, "vip": True, "limited": False},
    Feature.ANKI: {"free": False, "vip": True, "limited": False},
}


class FeatureGate:
    """功能门控
    
    控制用户对各功能的访问权限。
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
    
    Attributes:
        _license_service: 许可证服务
        _usage_tracker: 使用量追踪器
        _is_vip_override: VIP 状态覆盖（用于缓存状态）
    """
    
    def __init__(
        self, 
        license_service: Optional[LicenseService] = None,
        usage_tracker: Optional[UsageTracker] = None,
        is_vip_override: Optional[bool] = None
    ):
        """初始化功能门控
        
        Args:
            license_service: 许可证服务（可选，None 表示未登录用户）
            usage_tracker: 使用量追踪器（可选）
            is_vip_override: VIP 状态覆盖（可选，用于从缓存加载时）
        """
        self._license_service = license_service
        self._usage_tracker = usage_tracker
        self._is_vip_override = is_vip_override
    
    def _is_vip(self) -> bool:
        """判断当前用户是否为 VIP
        
        优先使用 override（缓存状态），其次使用 license_service。
        
        Returns:
            bool: 是否为 VIP
        """
        if self._is_vip_override is not None:
            return self._is_vip_override
        if self._license_service:
            return self._license_service.is_vip()
        return False
    
    def check_access(self, feature: Feature) -> AccessResult:
        """检查功能访问权限
        
        Requirements: 4.1, 4.2, 4.3, 4.4
        
        Args:
            feature: 功能枚举
            
        Returns:
            AccessResult: 访问检查结果
        """
        config = FEATURE_CONFIG.get(feature)
        if config is None:
            gate_log(f"未知功能: {feature}")
            return AccessResult.deny("未知功能")
        
        is_vip = self._is_vip()
        
        # 检查基本权限
        if is_vip:
            if not config["vip"]:
                return AccessResult.deny("此功能不可用")
            # VIP 用户无限制
            return AccessResult.allow()
        else:
            # 免费用户
            if not config["free"]:
                return AccessResult.deny(
                    "此功能仅限 VIP 用户",
                    upgrade_hint="☕ 请作者喝杯咖啡，赞助开发可解锁此功能"
                )
        
        # 检查使用量限制（仅免费用户）
        if config.get("limited") and self._usage_tracker:
            limit_key = config.get("limit_key", feature.value)
            remaining = self._usage_tracker.get_remaining(limit_key)
            
            if remaining == 0:
                limit = DAILY_LIMITS.get(limit_key, 0)
                return AccessResult.deny(
                    f"今日使用次数已达上限（{limit} 次）",
                    upgrade_hint="☕ 请作者喝杯咖啡，赞助开发可无限使用"
                )
            
            return AccessResult.allow(remaining=remaining)
        
        return AccessResult.allow()
    
    def can_use(self, feature: Feature) -> bool:
        """简单检查是否可以使用功能
        
        Requirements: 4.1
        
        Args:
            feature: 功能枚举
            
        Returns:
            bool: 是否可以使用
        """
        return self.check_access(feature).allowed
    
    def use(self, feature: Feature) -> AccessResult:
        """使用功能（检查权限并增加使用量）
        
        Requirements: 4.5
        
        Args:
            feature: 功能枚举
            
        Returns:
            AccessResult: 访问检查结果
        """
        result = self.check_access(feature)
        
        if not result.allowed:
            return result
        
        # 增加使用量（仅受限功能且非 VIP）
        config = FEATURE_CONFIG.get(feature, {})
        is_vip = self._is_vip()
        
        if not is_vip and config.get("limited") and self._usage_tracker:
            limit_key = config.get("limit_key", feature.value)
            if not self._usage_tracker.increment(limit_key):
                return AccessResult.deny(
                    "使用次数已达上限",
                    upgrade_hint="☕ 请作者喝杯咖啡，赞助开发可无限使用"
                )
            
            # 更新剩余次数
            result.remaining = self._usage_tracker.get_remaining(limit_key)
        
        gate_log(f"功能 {feature.value} 使用成功")
        return result
    
    def get_feature_status(self, feature: Feature) -> Dict[str, Any]:
        """获取功能状态信息
        
        Requirements: 4.6
        
        Args:
            feature: 功能枚举
            
        Returns:
            Dict: 功能状态信息
        """
        config = FEATURE_CONFIG.get(feature, {})
        is_vip = self._is_vip()
        result = self.check_access(feature)
        
        status = {
            "feature": feature.value,
            "allowed": result.allowed,
            "reason": result.reason,
            "is_vip_only": not config.get("free", True),
            "is_limited": config.get("limited", False) and not is_vip,
        }
        
        # 添加使用量信息（仅受限功能且非 VIP）
        if config.get("limited") and self._usage_tracker and not is_vip:
            limit_key = config.get("limit_key", feature.value)
            status["usage"] = self._usage_tracker.get_usage(limit_key)
            status["limit"] = DAILY_LIMITS.get(limit_key, -1)
            status["remaining"] = self._usage_tracker.get_remaining(limit_key)
        
        return status
    
    def get_all_features_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有功能的状态
        
        Returns:
            Dict: {feature_name: status}
        """
        return {
            feature.value: self.get_feature_status(feature)
            for feature in Feature
        }
    
    def is_vip_only(self, feature: Feature) -> bool:
        """检查功能是否仅限 VIP
        
        Args:
            feature: 功能枚举
            
        Returns:
            bool: 是否仅限 VIP
        """
        config = FEATURE_CONFIG.get(feature, {})
        return not config.get("free", True)
