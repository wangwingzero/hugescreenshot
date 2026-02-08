# =====================================================
# =============== 智能布局管理器 ===============
# =====================================================

"""
智能布局管理器 - 协调截图工具中UI组件的位置

Feature: smart-ui-layout
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4

功能：
- 计算工具栏和OCR面板的最佳位置
- 避免UI组件之间的重叠
- 支持手动定位状态管理
- 边界约束确保组件在屏幕内
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from PySide6.QtCore import QRect, QPoint, QSize


@dataclass
class ComponentLayout:
    """UI组件布局信息"""
    rect: QRect                    # 组件矩形（位置和大小）
    is_manually_positioned: bool = False  # 是否被手动定位
    preferred_side: str = ""       # 首选位置侧 ("left", "right", "top", "bottom")


class SmartLayoutManager:
    """智能布局管理器
    
    负责计算和协调所有UI组件的位置，确保：
    1. 组件之间不重叠
    2. 组件在屏幕边界内
    3. 遵循位置优先级策略
    4. 支持手动定位状态管理
    """
    
    MARGIN = 8  # 组件间距（像素）
    
    def __init__(self, screen_rect: QRect):
        """初始化布局管理器
        
        Args:
            screen_rect: 屏幕边界矩形
        """
        self._screen_rect = screen_rect
        self._components: Dict[str, ComponentLayout] = {}
        self._selection_rect: Optional[QRect] = None
    
    def set_screen_rect(self, rect: QRect) -> None:
        """设置屏幕边界
        
        Args:
            rect: 屏幕边界矩形
        """
        self._screen_rect = rect
    
    def get_screen_rect(self) -> QRect:
        """获取屏幕边界"""
        return self._screen_rect
    
    def set_selection_rect(self, rect: QRect) -> None:
        """设置选区矩形
        
        Args:
            rect: 用户选择的截图区域
        """
        self._selection_rect = rect
    
    def get_selection_rect(self) -> Optional[QRect]:
        """获取选区矩形"""
        return self._selection_rect

    def register_component(
        self, 
        name: str, 
        size: QSize, 
        preferred_side: str = ""
    ) -> None:
        """注册UI组件
        
        Args:
            name: 组件名称（如 "side_toolbar", "bottom_toolbar", "ocr_panel"）
            size: 组件尺寸
            preferred_side: 首选位置侧 ("left", "right", "top", "bottom")
        """
        self._components[name] = ComponentLayout(
            rect=QRect(0, 0, size.width(), size.height()),
            preferred_side=preferred_side
        )
    
    def update_component_size(self, name: str, size: QSize) -> None:
        """更新组件尺寸
        
        Args:
            name: 组件名称
            size: 新的尺寸
        """
        if name in self._components:
            old_pos = self._components[name].rect.topLeft()
            self._components[name].rect = QRect(old_pos, size)
    
    def get_component(self, name: str) -> Optional[ComponentLayout]:
        """获取组件布局信息
        
        Args:
            name: 组件名称
            
        Returns:
            组件布局信息，如果不存在返回 None
        """
        return self._components.get(name)
    
    def get_component_rect(self, name: str) -> Optional[QRect]:
        """获取组件矩形
        
        Args:
            name: 组件名称
            
        Returns:
            组件矩形，如果不存在返回 None
        """
        comp = self._components.get(name)
        return comp.rect if comp else None
    
    def calculate_all_positions(self) -> Dict[str, QPoint]:
        """计算所有组件的位置，避免重叠
        
        按优先级顺序计算位置：
        1. 侧边栏（优先右侧）
        2. 底部工具栏（优先下方，避开侧边栏）
        3. OCR面板（选择空间大的一侧，避开其他组件）
        
        Returns:
            组件名称到位置的映射
        """
        positions = {}
        
        # 1. 计算侧边栏位置
        if "side_toolbar" in self._components:
            if not self._components["side_toolbar"].is_manually_positioned:
                pos = self._calc_side_toolbar_position()
                positions["side_toolbar"] = pos
                self._components["side_toolbar"].rect.moveTo(pos)
        
        # 2. 计算底部工具栏位置（考虑侧边栏）
        if "bottom_toolbar" in self._components:
            if not self._components["bottom_toolbar"].is_manually_positioned:
                pos = self._calc_bottom_toolbar_position()
                positions["bottom_toolbar"] = pos
                self._components["bottom_toolbar"].rect.moveTo(pos)
        
        # 3. 计算OCR面板位置（避开其他组件）
        if "ocr_panel" in self._components:
            if not self._components["ocr_panel"].is_manually_positioned:
                pos = self._calc_ocr_panel_position()
                positions["ocr_panel"] = pos
                self._components["ocr_panel"].rect.moveTo(pos)
        
        return positions
    
    def mark_manually_positioned(self, name: str) -> None:
        """标记组件为手动定位
        
        手动定位的组件不会被自动重新定位。
        
        Args:
            name: 组件名称
        """
        if name in self._components:
            self._components[name].is_manually_positioned = True
    
    def is_manually_positioned(self, name: str) -> bool:
        """检查组件是否被手动定位
        
        Args:
            name: 组件名称
            
        Returns:
            True 如果组件被手动定位
        """
        comp = self._components.get(name)
        return comp.is_manually_positioned if comp else False
    
    def update_component_position(self, name: str, pos: QPoint) -> None:
        """更新组件位置
        
        Args:
            name: 组件名称
            pos: 新位置
        """
        if name in self._components:
            self._components[name].rect.moveTo(pos)
    
    def reset_session(self) -> None:
        """重置会话状态
        
        清除所有组件的手动定位标记。
        应在新截图会话开始时调用。
        """
        for comp in self._components.values():
            comp.is_manually_positioned = False
    
    def clamp_to_screen(self, pos: QPoint, size: QSize) -> QPoint:
        """将位置限制在屏幕边界内
        
        Args:
            pos: 原始位置
            size: 组件尺寸
            
        Returns:
            调整后的位置，确保组件完全在屏幕内
        """
        x = max(self._screen_rect.left(), 
                min(pos.x(), self._screen_rect.right() - size.width()))
        y = max(self._screen_rect.top(), 
                min(pos.y(), self._screen_rect.bottom() - size.height()))
        return QPoint(int(x), int(y))

    def _rects_overlap(self, r1: QRect, r2: QRect) -> bool:
        """检查两个矩形是否重叠
        
        Args:
            r1: 第一个矩形
            r2: 第二个矩形
            
        Returns:
            True 如果两个矩形有重叠区域
        """
        if r1.isEmpty() or r2.isEmpty():
            return False
        return r1.intersects(r2)
    
    def _calc_side_toolbar_position(self) -> QPoint:
        """计算侧边栏位置
        
        优先放在离屏幕左右边缘最近的一侧，紧贴选区。
        - 如果选区中心更靠近左边缘，工具栏放在选区左侧
        - 如果选区中心更靠近右边缘，工具栏放在选区右侧
        - 空间不足时放在另一侧
        
        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
        
        Returns:
            侧边栏位置
        """
        comp = self._components.get("side_toolbar")
        if not comp:
            return QPoint(0, 0)
        
        size = comp.rect.size()
        if size.isEmpty():
            return QPoint(0, 0)
        
        # 使用选区或屏幕中心作为参考
        if self._selection_rect and not self._selection_rect.isEmpty():
            sel = self._selection_rect
        else:
            # 无选区时使用屏幕中心
            center = self._screen_rect.center()
            sel = QRect(center.x(), center.y(), 1, 1)
        
        margin = self.MARGIN
        
        # 计算选区中心到左右屏幕边缘的距离
        sel_center_x = sel.center().x()
        dist_to_left = sel_center_x - self._screen_rect.left()
        dist_to_right = self._screen_rect.right() - sel_center_x
        
        # 计算左右两侧可用空间
        space_right = self._screen_rect.right() - sel.right() - margin
        space_left = sel.left() - self._screen_rect.left() - margin
        
        # 选择离屏幕边缘最近的一侧
        if dist_to_left <= dist_to_right:
            # 选区更靠近左边缘，优先放在选区左侧
            if space_left >= size.width():
                x = sel.left() - size.width() - margin
            elif space_right >= size.width():
                # 左侧空间不足，放在右侧
                x = sel.right() + margin
            else:
                # 两侧都放不下，选择空间较大的一侧
                if space_left >= space_right:
                    x = self._screen_rect.left()
                else:
                    x = self._screen_rect.right() - size.width()
        else:
            # 选区更靠近右边缘，优先放在选区右侧
            if space_right >= size.width():
                x = sel.right() + margin
            elif space_left >= size.width():
                # 右侧空间不足，放在左侧
                x = sel.left() - size.width() - margin
            else:
                # 两侧都放不下，选择空间较大的一侧
                if space_right >= space_left:
                    x = self._screen_rect.right() - size.width()
                else:
                    x = self._screen_rect.left()
        
        # 垂直位置：与选区顶部对齐
        y = sel.top()
        
        # 边界约束
        return self.clamp_to_screen(QPoint(int(x), int(y)), size)
    
    def _calc_bottom_toolbar_position(self) -> QPoint:
        """计算底部工具栏位置
        
        优先放在选区下方，空间不足时放在上方。
        同时避免与侧边栏重叠。
        
        Returns:
            底部工具栏位置
        """
        comp = self._components.get("bottom_toolbar")
        if not comp:
            return QPoint(0, 0)
        
        size = comp.rect.size()
        if size.isEmpty():
            return QPoint(0, 0)
        
        # 使用选区或屏幕中心作为参考
        if self._selection_rect and not self._selection_rect.isEmpty():
            sel = self._selection_rect
        else:
            center = self._screen_rect.center()
            sel = QRect(center.x(), center.y(), 1, 1)
        
        margin = self.MARGIN
        
        # 计算下方和上方可用空间
        space_below = self._screen_rect.bottom() - sel.bottom() - margin
        space_above = sel.top() - self._screen_rect.top() - margin
        
        # 优先下方
        if space_below >= size.height():
            y = sel.bottom() + margin
        elif space_above >= size.height():
            y = sel.top() - size.height() - margin
        else:
            # 两侧都放不下，选择空间较大的一侧
            if space_below >= space_above:
                y = self._screen_rect.bottom() - size.height()
            else:
                y = self._screen_rect.top()
        
        # 水平位置：与选区左侧对齐
        x = sel.left()
        
        # 边界约束
        pos = self.clamp_to_screen(QPoint(int(x), int(y)), size)
        
        # 检查是否与侧边栏重叠
        side_comp = self._components.get("side_toolbar")
        if side_comp and not side_comp.rect.isEmpty():
            toolbar_rect = QRect(pos, size)
            if self._rects_overlap(toolbar_rect, side_comp.rect):
                # 需要调整位置避免重叠
                pos = self._adjust_to_avoid_overlap(
                    pos, size, [side_comp.rect]
                )
        
        return pos
    
    def _calc_ocr_panel_position(self) -> QPoint:
        """计算OCR面板位置
        
        优先放在离屏幕左右边缘最远的一侧，紧贴选区。
        - 如果选区中心更靠近左边缘，OCR面板放在选区右侧
        - 如果选区中心更靠近右边缘，OCR面板放在选区左侧
        - 同时避开侧边栏，确保不重叠
        
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
        
        Returns:
            OCR面板位置
        """
        comp = self._components.get("ocr_panel")
        if not comp:
            return QPoint(0, 0)
        
        size = comp.rect.size()
        if size.isEmpty():
            return QPoint(0, 0)
        
        # 使用选区或屏幕中心作为参考
        if self._selection_rect and not self._selection_rect.isEmpty():
            sel = self._selection_rect
        else:
            center = self._screen_rect.center()
            sel = QRect(center.x(), center.y(), 1, 1)
        
        margin = self.MARGIN
        
        # 收集需要避开的矩形
        avoid_rects = []
        for name in ["side_toolbar", "bottom_toolbar"]:
            other = self._components.get(name)
            if other and not other.rect.isEmpty():
                avoid_rects.append(other.rect)
        
        # 计算选区中心到左右屏幕边缘的距离
        sel_center_x = sel.center().x()
        dist_to_left = sel_center_x - self._screen_rect.left()
        dist_to_right = self._screen_rect.right() - sel_center_x
        
        # 计算左右两侧可用空间
        space_right = self._screen_rect.right() - sel.right() - margin
        space_left = sel.left() - self._screen_rect.left() - margin
        
        # 获取侧边栏位置信息，用于避免重叠
        side_comp = self._components.get("side_toolbar")
        if side_comp and not side_comp.rect.isEmpty():
            side_rect = side_comp.rect
            # 如果侧边栏在右侧，减去其占用的空间
            if side_rect.left() > sel.center().x():
                space_right = min(space_right, side_rect.left() - sel.right() - margin * 2)
            else:
                # 侧边栏在左侧
                space_left = min(space_left, sel.left() - side_rect.right() - margin * 2)
        
        # 选择离屏幕边缘最远的一侧（与侧边栏相反）
        if dist_to_left <= dist_to_right:
            # 选区更靠近左边缘，OCR面板优先放在选区右侧（远离左边缘）
            if space_right >= size.width():
                x = sel.right() + margin
            elif space_left >= size.width():
                # 右侧空间不足，放在左侧
                x = sel.left() - size.width() - margin
            else:
                # 都放不下，选择空间较大的一侧
                if space_right >= space_left:
                    x = sel.right() + margin
                else:
                    x = sel.left() - size.width() - margin
        else:
            # 选区更靠近右边缘，OCR面板优先放在选区左侧（远离右边缘）
            if space_left >= size.width():
                x = sel.left() - size.width() - margin
            elif space_right >= size.width():
                # 左侧空间不足，放在右侧
                x = sel.right() + margin
            else:
                # 都放不下，选择空间较大的一侧
                if space_left >= space_right:
                    x = sel.left() - size.width() - margin
                else:
                    x = sel.right() + margin
        
        # 垂直位置：与选区顶部对齐
        y = sel.top()
        
        # 边界约束
        pos = self.clamp_to_screen(QPoint(int(x), int(y)), size)
        
        # 检查是否与其他组件重叠
        panel_rect = QRect(pos, size)
        for avoid_rect in avoid_rects:
            if self._rects_overlap(panel_rect, avoid_rect):
                pos = self._adjust_to_avoid_overlap(pos, size, avoid_rects)
                break
        
        return pos

    def _adjust_to_avoid_overlap(
        self, 
        pos: QPoint, 
        size: QSize, 
        avoid_rects: List[QRect]
    ) -> QPoint:
        """调整位置以避免与指定矩形重叠
        
        尝试多个方向的调整，选择第一个不重叠的位置。
        优先尝试垂直方向的调整（上下移动），因为水平空间通常更紧张。
        
        Args:
            pos: 原始位置
            size: 组件尺寸
            avoid_rects: 需要避开的矩形列表
            
        Returns:
            调整后的位置
        """
        if not avoid_rects:
            return pos
        
        margin = self.MARGIN
        original_rect = QRect(pos, size)
        
        # 收集所有可能的调整位置
        adjustments = []
        
        for avoid_rect in avoid_rects:
            if not self._rects_overlap(original_rect, avoid_rect):
                continue
            
            # 优先尝试垂直方向的调整（上下移动）
            # 向下移动（避开重叠矩形的下方）
            adjustments.append(QPoint(pos.x(), avoid_rect.bottom() + margin))
            # 向上移动（避开重叠矩形的上方）
            adjustments.append(QPoint(pos.x(), avoid_rect.top() - size.height() - margin))
            # 向右移动（避开重叠矩形的右侧）
            adjustments.append(QPoint(avoid_rect.right() + margin, pos.y()))
            # 向左移动（避开重叠矩形的左侧）
            adjustments.append(QPoint(avoid_rect.left() - size.width() - margin, pos.y()))
            
            # 尝试对角线方向的调整
            # 右下
            adjustments.append(QPoint(avoid_rect.right() + margin, avoid_rect.bottom() + margin))
            # 左下
            adjustments.append(QPoint(avoid_rect.left() - size.width() - margin, avoid_rect.bottom() + margin))
            # 右上
            adjustments.append(QPoint(avoid_rect.right() + margin, avoid_rect.top() - size.height() - margin))
            # 左上
            adjustments.append(QPoint(avoid_rect.left() - size.width() - margin, avoid_rect.top() - size.height() - margin))
        
        # 尝试每个调整，找到第一个不重叠且在屏幕内的位置
        for adj_pos in adjustments:
            clamped = self.clamp_to_screen(adj_pos, size)
            adj_rect = QRect(clamped, size)
            
            # 检查是否与任何避开矩形重叠
            has_overlap = False
            for avoid_rect in avoid_rects:
                if self._rects_overlap(adj_rect, avoid_rect):
                    has_overlap = True
                    break
            
            if not has_overlap:
                return clamped
        
        # 如果所有调整都失败，尝试放在屏幕的四个角落
        corners = [
            QPoint(margin, margin),  # 左上
            QPoint(self._screen_rect.right() - size.width() - margin, margin),  # 右上
            QPoint(margin, self._screen_rect.bottom() - size.height() - margin),  # 左下
            QPoint(self._screen_rect.right() - size.width() - margin, 
                   self._screen_rect.bottom() - size.height() - margin),  # 右下
        ]
        
        for corner_pos in corners:
            clamped = self.clamp_to_screen(corner_pos, size)
            corner_rect = QRect(clamped, size)
            
            has_overlap = False
            for avoid_rect in avoid_rects:
                if self._rects_overlap(corner_rect, avoid_rect):
                    has_overlap = True
                    break
            
            if not has_overlap:
                return clamped
        
        # 如果所有调整都失败，返回原始位置（边界约束后）
        return self.clamp_to_screen(pos, size)
    
    def calculate_position_avoiding(
        self, 
        size: QSize, 
        avoid_rects: List[QRect],
        prefer_side: str = "right"
    ) -> QPoint:
        """计算位置，避开指定的矩形区域
        
        用于外部调用（如 OCR 面板定位）。
        
        Args:
            size: 组件尺寸
            avoid_rects: 需要避开的矩形列表
            prefer_side: 首选侧 ("left" 或 "right")
            
        Returns:
            计算出的位置
        """
        if self._selection_rect and not self._selection_rect.isEmpty():
            sel = self._selection_rect
        else:
            center = self._screen_rect.center()
            sel = QRect(center.x(), center.y(), 1, 1)
        
        margin = self.MARGIN
        
        # 根据首选侧计算初始位置
        if prefer_side == "left":
            x = sel.left() - size.width() - margin
        else:
            x = sel.right() + margin
        
        y = sel.top()
        
        # 边界约束
        pos = self.clamp_to_screen(QPoint(int(x), int(y)), size)
        
        # 检查是否与避开矩形重叠
        rect = QRect(pos, size)
        for avoid_rect in avoid_rects:
            if self._rects_overlap(rect, avoid_rect):
                return self._adjust_to_avoid_overlap(pos, size, avoid_rects)
        
        return pos
    
    def get_all_component_rects(self) -> List[QRect]:
        """获取所有已注册组件的矩形
        
        Returns:
            组件矩形列表
        """
        return [comp.rect for comp in self._components.values() 
                if not comp.rect.isEmpty()]
    
    def get_visible_component_rects(self, exclude: List[str] = None) -> List[QRect]:
        """获取可见组件的矩形（排除指定组件）
        
        Args:
            exclude: 要排除的组件名称列表
            
        Returns:
            组件矩形列表
        """
        exclude = exclude or []
        return [comp.rect for name, comp in self._components.items() 
                if name not in exclude and not comp.rect.isEmpty()]
