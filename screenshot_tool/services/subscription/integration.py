"""
订阅系统集成辅助模块

提供功能门控的便捷集成方法，避免直接修改现有服务代码。

Feature: subscription-system
Requirements: 4.2, 4.3, 4.4, 4.5
"""

from typing import Optional, Callable, Any
from functools import wraps

from .feature_gate import FeatureGate, Feature, AccessResult

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def integration_log(message: str):
    """集成日志"""
    _debug_log(message, "INTEGRATION")


# 全局功能门控实例（由主应用初始化）
_feature_gate: Optional[FeatureGate] = None


def init_feature_gate(gate: FeatureGate) -> None:
    """初始化全局功能门控
    
    Args:
        gate: FeatureGate 实例
    """
    global _feature_gate
    _feature_gate = gate
    integration_log("功能门控已初始化")


def get_feature_gate() -> Optional[FeatureGate]:
    """获取全局功能门控实例"""
    return _feature_gate


def check_feature(feature: Feature) -> AccessResult:
    """检查功能访问权限
    
    Args:
        feature: 功能枚举
        
    Returns:
        AccessResult: 访问检查结果
    """
    if _feature_gate is None:
        # 未初始化时默认允许（开发模式）
        integration_log(f"功能门控未初始化，默认允许 {feature.value}")
        return AccessResult.allow()
    
    return _feature_gate.check_access(feature)


def use_feature(feature: Feature) -> AccessResult:
    """使用功能（检查权限并增加使用量）
    
    Args:
        feature: 功能枚举
        
    Returns:
        AccessResult: 访问检查结果
    """
    if _feature_gate is None:
        integration_log(f"功能门控未初始化，默认允许 {feature.value}")
        return AccessResult.allow()
    
    return _feature_gate.use(feature)


def can_use(feature: Feature) -> bool:
    """简单检查是否可以使用功能
    
    Args:
        feature: 功能枚举
        
    Returns:
        bool: 是否可以使用
    """
    if _feature_gate is None:
        return True
    
    return _feature_gate.can_use(feature)


def get_feature_status(feature: Feature) -> dict:
    """获取功能状态
    
    Args:
        feature: 功能枚举
        
    Returns:
        dict: 功能状态信息
    """
    if _feature_gate is None:
        return {
            "feature": feature.value,
            "allowed": True,
            "reason": "功能门控未初始化",
        }
    
    return _feature_gate.get_feature_status(feature)


def require_feature(feature: Feature):
    """装饰器：要求功能权限
    
    用法:
        @require_feature(Feature.TRANSLATION)
        def translate_text(text):
            ...
    
    如果权限不足，会抛出 PermissionError。
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = use_feature(feature)
            if not result.allowed:
                raise PermissionError(result.reason)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_feature_check(feature: Feature, on_denied: Optional[Callable[[AccessResult], Any]] = None):
    """装饰器：带功能检查（不抛异常）
    
    用法:
        @with_feature_check(Feature.TRANSLATION, on_denied=lambda r: None)
        def translate_text(text):
            ...
    
    如果权限不足，调用 on_denied 回调并返回其结果。
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = check_feature(feature)
            if not result.allowed:
                if on_denied:
                    return on_denied(result)
                return None
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 便捷函数：检查特定功能
def can_translate() -> bool:
    """检查是否可以使用翻译功能"""
    return can_use(Feature.TRANSLATION)


def can_web_to_markdown() -> bool:
    """检查是否可以使用网页转 Markdown 功能"""
    return can_use(Feature.WEB_TO_MARKDOWN)


def can_screen_record() -> bool:
    """检查是否可以使用录屏功能"""
    return can_use(Feature.SCREEN_RECORDER)


def can_use_gongwen() -> bool:
    """检查是否可以使用公文功能"""
    return can_use(Feature.GONGWEN)


def can_use_caac() -> bool:
    """检查是否可以使用 CAAC 功能"""
    return can_use(Feature.CAAC)


# 使用功能的便捷函数
def use_translation() -> AccessResult:
    """使用翻译功能"""
    return use_feature(Feature.TRANSLATION)


def use_web_to_markdown() -> AccessResult:
    """使用网页转 Markdown 功能"""
    return use_feature(Feature.WEB_TO_MARKDOWN)


def use_screen_record() -> AccessResult:
    """使用录屏功能"""
    return use_feature(Feature.SCREEN_RECORDER)


def use_gongwen() -> AccessResult:
    """使用公文功能"""
    return use_feature(Feature.GONGWEN)


def use_caac() -> AccessResult:
    """使用 CAAC 功能"""
    return use_feature(Feature.CAAC)
