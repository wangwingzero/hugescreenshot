# =====================================================
# =============== 效果基类 ===============
# =====================================================

"""
效果绘制器基类

定义所有效果的公共接口。

Feature: mouse-highlight
Requirements: 4.1, 5.1, 6.1, 7.1
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtGui import QPainter
from PySide6.QtCore import QRect

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import MouseHighlightConfig


class BaseEffect(ABC):
    """效果绘制器基类
    
    所有效果必须继承此类并实现 draw() 方法。
    """
    
    def __init__(self, config: "MouseHighlightConfig", theme: dict):
        """初始化效果
        
        Args:
            config: 鼠标高亮配置
            theme: 主题颜色字典
        """
        self._config = config
        self._theme = theme
    
    @abstractmethod
    def draw(self, painter: QPainter, mouse_x: int, mouse_y: int, screen_geometry: QRect):
        """绘制效果
        
        Args:
            painter: QPainter 对象
            mouse_x: 鼠标本地 X 坐标（相对于覆盖层窗口）
            mouse_y: 鼠标本地 Y 坐标（相对于覆盖层窗口）
            screen_geometry: 屏幕几何区域
        """
        pass
    
    def is_animated(self) -> bool:
        """是否有活动动画（需要持续重绘）
        
        Returns:
            默认返回 False，有动画的效果需要重写此方法
        """
        return False
    
    def update_config(self, config: "MouseHighlightConfig", theme: dict):
        """更新配置
        
        Args:
            config: 新的配置
            theme: 新的主题颜色
        """
        self._config = config
        self._theme = theme
    
    @property
    def config(self) -> "MouseHighlightConfig":
        """获取当前配置"""
        return self._config
    
    @property
    def theme(self) -> dict:
        """获取当前主题"""
        return self._theme
