# =====================================================
# =============== 无障碍管理器 ===============
# =====================================================

"""
无障碍功能管理器 - 检测和响应系统无障碍设置

主要功能：
1. 检测 Windows 系统 reduced-motion 偏好设置
2. 管理应用内动画启用/禁用状态
3. 提供统一的无障碍设置接口

Feature: performance-ui-optimization
Requirements: 8.5 - 尊重系统 reduced-motion 偏好

Windows 设置位置：
- Windows 11: 设置 > 辅助功能 > 视觉效果 > 动画效果
- Windows 10: 设置 > 轻松使用 > 显示 > 在 Windows 中显示动画
"""

import sys
from typing import Optional, List, Callable
from dataclasses import dataclass, field

# Windows API 常量
SPI_GETCLIENTAREAANIMATION = 0x1042


@dataclass
class AccessibilitySettings:
    """无障碍设置数据类
    
    Attributes:
        reduced_motion: 是否启用 reduced-motion（禁用动画）
        animations_enabled: 是否启用动画（与 reduced_motion 相反）
    """
    reduced_motion: bool = False
    animations_enabled: bool = True
    
    def __post_init__(self):
        """确保 animations_enabled 与 reduced_motion 一致"""
        self.animations_enabled = not self.reduced_motion


def detect_reduced_motion() -> bool:
    """检测 Windows 系统 reduced-motion 偏好设置
    
    通过 Windows API SystemParametersInfo 检测用户是否禁用了动画效果。
    
    Feature: performance-ui-optimization
    Requirements: 8.5 - 尊重系统 reduced-motion 偏好
    
    Returns:
        bool: True 表示用户偏好减少动画（reduced-motion 启用）
              False 表示用户允许动画（reduced-motion 禁用）
    
    Note:
        - 仅在 Windows 平台有效
        - 非 Windows 平台默认返回 False（允许动画）
        - API 调用失败时默认返回 False（允许动画）
    """
    # 仅在 Windows 平台检测
    if sys.platform != "win32":
        return False
    
    try:
        import ctypes
        from ctypes import wintypes
        
        # 准备接收结果的变量
        animations_enabled = wintypes.BOOL()
        
        # 调用 SystemParametersInfo
        # 参数: action, uiParam, pvParam (output), fWinIni
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION,
            0,
            ctypes.byref(animations_enabled),
            0
        )
        
        if not result:
            # API 调用失败，默认允许动画
            return False
        
        # animations_enabled 为 False 时表示用户禁用了动画
        # 即 reduced-motion 启用
        return not animations_enabled.value
        
    except Exception:
        # 任何异常都默认允许动画
        return False


class AccessibilityManager:
    """无障碍功能管理器（单例模式）
    
    管理应用的无障碍设置，包括：
    - 检测系统 reduced-motion 偏好
    - 管理动画启用/禁用状态
    - 通知已注册的组件更新动画状态
    
    Feature: performance-ui-optimization
    Requirements: 8.5 - 尊重系统 reduced-motion 偏好
    
    Usage:
        # 获取单例实例
        manager = AccessibilityManager.instance()
        
        # 检查是否应该启用动画
        if manager.animations_enabled:
            # 执行动画
            pass
        
        # 注册组件以接收动画状态变化通知
        manager.register_animated_component(my_button)
        
        # 手动刷新设置（例如在应用获得焦点时）
        manager.refresh()
    """
    
    _instance: Optional['AccessibilityManager'] = None
    
    def __init__(self):
        """初始化无障碍管理器
        
        Note:
            请使用 AccessibilityManager.instance() 获取单例实例
        """
        self._settings = AccessibilitySettings()
        self._animated_components: List[object] = []
        self._callbacks: List[Callable[[bool], None]] = []
        
        # 初始化时检测系统设置
        self._detect_system_settings()
    
    @classmethod
    def instance(cls) -> 'AccessibilityManager':
        """获取单例实例
        
        Returns:
            AccessibilityManager: 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        cls._instance = None
    
    def _detect_system_settings(self) -> None:
        """检测系统无障碍设置"""
        reduced_motion = detect_reduced_motion()
        self._settings = AccessibilitySettings(reduced_motion=reduced_motion)
    
    @property
    def settings(self) -> AccessibilitySettings:
        """获取当前无障碍设置
        
        Returns:
            AccessibilitySettings: 当前设置
        """
        return self._settings
    
    @property
    def reduced_motion(self) -> bool:
        """检查是否启用 reduced-motion
        
        Returns:
            bool: True 表示用户偏好减少动画
        """
        return self._settings.reduced_motion
    
    @property
    def animations_enabled(self) -> bool:
        """检查是否应该启用动画
        
        这是 reduced_motion 的反向属性，方便使用。
        
        Returns:
            bool: True 表示应该启用动画
        """
        return self._settings.animations_enabled
    
    def refresh(self) -> bool:
        """刷新系统设置并通知组件
        
        重新检测系统 reduced-motion 设置，如果设置发生变化，
        通知所有已注册的组件更新动画状态。
        
        Returns:
            bool: True 表示设置发生了变化
        """
        old_reduced_motion = self._settings.reduced_motion
        self._detect_system_settings()
        
        if old_reduced_motion != self._settings.reduced_motion:
            self._notify_components()
            self._notify_callbacks()
            return True
        
        return False
    
    def register_animated_component(self, component: object) -> None:
        """注册动画组件
        
        注册的组件必须实现 set_animations_enabled(bool) 方法。
        当 reduced-motion 设置变化时，会自动调用该方法。
        
        Args:
            component: 实现了 set_animations_enabled 方法的组件
        """
        if component not in self._animated_components:
            self._animated_components.append(component)
            # 立即应用当前设置
            self._apply_to_component(component)
    
    def unregister_animated_component(self, component: object) -> None:
        """取消注册动画组件
        
        Args:
            component: 要取消注册的组件
        """
        if component in self._animated_components:
            self._animated_components.remove(component)
    
    def register_callback(self, callback: Callable[[bool], None]) -> None:
        """注册回调函数
        
        当 animations_enabled 状态变化时调用回调。
        
        Args:
            callback: 回调函数，参数为 animations_enabled 状态
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable[[bool], None]) -> None:
        """取消注册回调函数
        
        Args:
            callback: 要取消注册的回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _apply_to_component(self, component: object) -> None:
        """将当前设置应用到组件
        
        Args:
            component: 目标组件
        """
        if hasattr(component, 'set_animations_enabled'):
            try:
                component.set_animations_enabled(self._settings.animations_enabled)
            except Exception:
                # 忽略组件更新失败
                pass
    
    def _notify_components(self) -> None:
        """通知所有已注册的组件更新动画状态"""
        # 使用列表副本避免迭代时修改
        for component in list(self._animated_components):
            self._apply_to_component(component)
    
    def _notify_callbacks(self) -> None:
        """通知所有已注册的回调函数"""
        for callback in list(self._callbacks):
            try:
                callback(self._settings.animations_enabled)
            except Exception:
                # 忽略回调执行失败
                pass
    
    def apply_to_all_components(self) -> None:
        """将当前设置应用到所有已注册的组件
        
        可用于初始化时批量应用设置。
        """
        self._notify_components()
    
    def get_registered_component_count(self) -> int:
        """获取已注册组件数量
        
        Returns:
            int: 已注册的组件数量
        """
        return len(self._animated_components)


# =====================================================
# 便捷函数
# =====================================================

def is_reduced_motion_enabled() -> bool:
    """检查系统是否启用了 reduced-motion
    
    便捷函数，直接检测系统设置而不使用单例。
    
    Returns:
        bool: True 表示用户偏好减少动画
    """
    return detect_reduced_motion()


def should_animate() -> bool:
    """检查是否应该播放动画
    
    便捷函数，返回 reduced_motion 的反向值。
    
    Returns:
        bool: True 表示应该播放动画
    """
    return not detect_reduced_motion()
