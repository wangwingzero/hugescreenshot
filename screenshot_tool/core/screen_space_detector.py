# =====================================================
# =============== 屏幕空间检测器 ===============
# =====================================================

"""
屏幕空间检测器 - 计算OCR窗口的最佳显示位置

Feature: auto-ocr-popup
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from dataclasses import dataclass
from typing import Tuple

from PySide6.QtCore import QRect, QPoint, QSize
from PySide6.QtGui import QGuiApplication


@dataclass
class WindowPosition:
    """窗口位置信息"""
    x: int
    y: int
    side: str  # "left" or "right"


class ScreenSpaceDetector:
    """屏幕空间检测器
    
    用于计算OCR窗口的最佳显示位置，根据截图选区位置
    自动选择在左侧或右侧显示。
    """
    
    # 窗口与选区之间的间距（像素）
    WINDOW_MARGIN = 10
    
    # 默认窗口尺寸
    DEFAULT_WINDOW_WIDTH = 500
    DEFAULT_WINDOW_HEIGHT = 400
    
    def __init__(self):
        pass
    
    def get_screen_rect(self) -> QRect:
        """获取主屏幕的矩形区域
        
        Returns:
            主屏幕的矩形区域
        """
        screen = QGuiApplication.primaryScreen()
        if screen:
            return screen.availableGeometry()
        # 如果无法获取屏幕信息，返回默认值
        return QRect(0, 0, 1920, 1080)
    
    def get_virtual_screen_rect(self) -> QRect:
        """获取虚拟屏幕（所有屏幕合并）的矩形区域
        
        Returns:
            虚拟屏幕的矩形区域
        """
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)
        
        total_rect = QRect()
        for screen in screens:
            total_rect = total_rect.united(screen.availableGeometry())
        
        return total_rect
    
    def _get_side_spaces(
        self, 
        selection_rect: QRect, 
        screen_rect: QRect
    ) -> Tuple[int, int]:
        """获取选区左右两侧的可用空间
        
        Args:
            selection_rect: 截图选区矩形
            screen_rect: 屏幕矩形
            
        Returns:
            (left_space, right_space) 像素值
        """
        # 左侧空间 = 选区左边缘到屏幕左边缘的距离
        left_space = selection_rect.left() - screen_rect.left()
        
        # 右侧空间 = 屏幕右边缘到选区右边缘的距离
        right_space = screen_rect.right() - selection_rect.right()
        
        return max(0, left_space), max(0, right_space)
    
    def calculate_window_position(
        self, 
        selection_rect: QRect, 
        window_size: QSize = None,
        screen_rect: QRect = None,
        avoid_rects: list = None
    ) -> WindowPosition:
        """计算OCR窗口的最佳位置
        
        根据选区位置，自动选择在左侧或右侧显示窗口。
        如果两侧空间相等，默认选择右侧。
        
        Args:
            selection_rect: 截图选区矩形（屏幕坐标）
            window_size: OCR窗口大小，默认使用 DEFAULT_WINDOW_WIDTH x DEFAULT_WINDOW_HEIGHT
            screen_rect: 屏幕矩形，默认使用虚拟屏幕
            avoid_rects: 需要避开的矩形列表（如工具栏位置）
            
        Returns:
            WindowPosition 包含窗口位置和显示侧
            
        Note:
            如果选区无效（空或尺寸为0），将使用屏幕中心作为参考点。
        """
        if window_size is None:
            window_size = QSize(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT)
        
        if screen_rect is None:
            screen_rect = self.get_virtual_screen_rect()
        
        if avoid_rects is None:
            avoid_rects = []
        
        # 处理无效选区
        if selection_rect is None or not selection_rect.isValid():
            # 使用屏幕中心作为参考
            center_x = screen_rect.center().x()
            center_y = screen_rect.center().y()
            selection_rect = QRect(center_x, center_y, 1, 1)
        
        # 获取左右两侧空间
        left_space, right_space = self._get_side_spaces(selection_rect, screen_rect)
        
        # 检查避开矩形对左右空间的影响
        for avoid_rect in avoid_rects:
            if avoid_rect is None or avoid_rect.isEmpty():
                continue
            # 如果避开矩形在选区右侧，减少右侧可用空间
            if avoid_rect.left() > selection_rect.center().x():
                overlap_width = max(0, selection_rect.right() + self.WINDOW_MARGIN + window_size.width() - avoid_rect.left())
                if overlap_width > 0:
                    right_space = max(0, right_space - avoid_rect.width() - self.WINDOW_MARGIN)
            # 如果避开矩形在选区左侧，减少左侧可用空间
            else:
                overlap_width = max(0, avoid_rect.right() + self.WINDOW_MARGIN - (selection_rect.left() - window_size.width() - self.WINDOW_MARGIN))
                if overlap_width > 0:
                    left_space = max(0, left_space - avoid_rect.width() - self.WINDOW_MARGIN)
        
        # 决定显示在哪一侧
        # 右侧空间 >= 左侧空间时，选择右侧（包括相等的情况）
        if right_space >= left_space:
            side = "right"
            # 窗口放在选区右侧
            x = selection_rect.right() + self.WINDOW_MARGIN
        else:
            side = "left"
            # 窗口放在选区左侧
            x = selection_rect.left() - window_size.width() - self.WINDOW_MARGIN
        
        # 垂直位置：与选区顶部对齐
        y = selection_rect.top()
        
        # 确保窗口在屏幕边界内
        x, y = self._clamp_to_screen(x, y, window_size, screen_rect)
        
        # 检查是否与避开矩形重叠，如果重叠则调整位置
        window_rect = QRect(x, y, window_size.width(), window_size.height())
        for avoid_rect in avoid_rects:
            if avoid_rect is None or avoid_rect.isEmpty():
                continue
            if window_rect.intersects(avoid_rect):
                # 尝试调整位置避开重叠
                x, y = self._adjust_to_avoid_overlap(
                    x, y, window_size, avoid_rect, screen_rect, side
                )
                window_rect = QRect(x, y, window_size.width(), window_size.height())
        
        return WindowPosition(x=x, y=y, side=side)
    
    def _adjust_to_avoid_overlap(
        self,
        x: int,
        y: int,
        window_size: QSize,
        avoid_rect: QRect,
        screen_rect: QRect,
        preferred_side: str
    ) -> tuple:
        """调整窗口位置以避开重叠
        
        Args:
            x: 当前 x 坐标
            y: 当前 y 坐标
            window_size: 窗口大小
            avoid_rect: 需要避开的矩形
            screen_rect: 屏幕矩形
            preferred_side: 首选侧 ("left" 或 "right")
            
        Returns:
            调整后的 (x, y) 坐标
        """
        margin = self.WINDOW_MARGIN
        
        # 尝试垂直方向调整
        # 向下移动
        new_y = avoid_rect.bottom() + margin
        if new_y + window_size.height() <= screen_rect.bottom():
            return x, new_y
        
        # 向上移动
        new_y = avoid_rect.top() - window_size.height() - margin
        if new_y >= screen_rect.top():
            return x, new_y
        
        # 尝试水平方向调整
        if preferred_side == "right":
            # 向右移动
            new_x = avoid_rect.right() + margin
            if new_x + window_size.width() <= screen_rect.right():
                return new_x, y
        else:
            # 向左移动
            new_x = avoid_rect.left() - window_size.width() - margin
            if new_x >= screen_rect.left():
                return new_x, y
        
        # 如果都不行，返回原位置
        return x, y
    
    def _clamp_to_screen(
        self, 
        x: int, 
        y: int, 
        window_size: QSize, 
        screen_rect: QRect
    ) -> Tuple[int, int]:
        """确保窗口位置在屏幕边界内
        
        Args:
            x: 窗口左上角 x 坐标
            y: 窗口左上角 y 坐标
            window_size: 窗口大小
            screen_rect: 屏幕矩形
            
        Returns:
            调整后的 (x, y) 坐标
        """
        # 确保不超出左边界
        if x < screen_rect.left():
            x = screen_rect.left()
        
        # 确保不超出右边界
        # 注意：QRect.right() 返回的是 left() + width() - 1
        max_x = screen_rect.left() + screen_rect.width() - window_size.width()
        if x > max_x:
            x = max(screen_rect.left(), max_x)
        
        # 确保不超出上边界
        if y < screen_rect.top():
            y = screen_rect.top()
        
        # 确保不超出下边界
        # 注意：QRect.bottom() 返回的是 top() + height() - 1
        max_y = screen_rect.top() + screen_rect.height() - window_size.height()
        if y > max_y:
            y = max(screen_rect.top(), max_y)
        
        return x, y
    
    def get_window_position_point(
        self, 
        selection_rect: QRect, 
        window_size: QSize = None,
        screen_rect: QRect = None
    ) -> QPoint:
        """计算OCR窗口位置并返回 QPoint
        
        这是 calculate_window_position 的便捷方法。
        
        Args:
            selection_rect: 截图选区矩形
            window_size: OCR窗口大小
            screen_rect: 屏幕矩形
            
        Returns:
            窗口左上角位置的 QPoint
        """
        pos = self.calculate_window_position(selection_rect, window_size, screen_rect)
        return QPoint(pos.x, pos.y)
