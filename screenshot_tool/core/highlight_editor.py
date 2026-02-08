# =====================================================
# =============== 高亮编辑器 ===============
# =====================================================

"""
高亮编辑器 - 负责在截图上绘制高亮区域和管理标注

Requirements: 2.1, 2.4, 2.5, 3.1, 3.3, 3.4, 3.5
Property 2: Region Management Invariants
Property 3: Highlight Rendering Preserves Image Dimensions
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from copy import deepcopy

from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush
from PySide6.QtCore import QRect


# 预定义的高亮颜色
HIGHLIGHT_COLORS = {
    "yellow": QColor(255, 243, 205, 80),   # #FFF3CD with alpha
    "green": QColor(212, 237, 218, 80),    # #D4EDDA with alpha
    "pink": QColor(248, 215, 218, 80),     # #F8D7DA with alpha
    "blue": QColor(204, 229, 255, 80),     # #CCE5FF with alpha
}

# 边框颜色
BORDER_COLORS = {
    "yellow": QColor(255, 193, 7),         # #FFC107
    "green": QColor(40, 167, 69),          # #28A745
    "pink": QColor(220, 53, 69),           # #DC3545
    "blue": QColor(74, 144, 217),          # #4A90D9
}


@dataclass
class HighlightRegion:
    """高亮区域数据"""
    id: int
    x1: int
    y1: int
    x2: int
    y2: int
    color: str = "yellow"
    opacity: float = 0.3
    
    def __post_init__(self):
        """初始化后处理，确保坐标正确"""
        # 确保 x1 < x2, y1 < y2
        if self.x1 > self.x2:
            self.x1, self.x2 = self.x2, self.x1
        if self.y1 > self.y2:
            self.y1, self.y2 = self.y2, self.y1
        
        # 限制透明度范围
        self.opacity = max(0.0, min(1.0, self.opacity))
        
        # 验证颜色
        if self.color not in HIGHLIGHT_COLORS:
            self.color = "yellow"
    
    @property
    def width(self) -> int:
        """获取区域宽度"""
        return self.x2 - self.x1
    
    @property
    def height(self) -> int:
        """获取区域高度"""
        return self.y2 - self.y1
    
    @property
    def is_valid(self) -> bool:
        """检查区域是否有效"""
        return self.width > 0 and self.height > 0
    
    def contains_point(self, x: int, y: int) -> bool:
        """检查点是否在区域内"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
    
    def to_rect(self) -> QRect:
        """转换为QRect"""
        return QRect(self.x1, self.y1, self.width, self.height)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "color": self.color,
            "opacity": self.opacity,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HighlightRegion":
        """从字典创建"""
        return cls(
            id=data.get("id", 0),
            x1=data.get("x1", 0),
            y1=data.get("y1", 0),
            x2=data.get("x2", 0),
            y2=data.get("y2", 0),
            color=data.get("color", "yellow"),
            opacity=data.get("opacity", 0.3),
        )
    
    def copy(self) -> "HighlightRegion":
        """创建副本"""
        return HighlightRegion(
            id=self.id,
            x1=self.x1,
            y1=self.y1,
            x2=self.x2,
            y2=self.y2,
            color=self.color,
            opacity=self.opacity,
        )


class HighlightEditor:
    """高亮编辑器"""
    
    def __init__(self):
        """初始化高亮编辑器"""
        self._regions: Dict[int, HighlightRegion] = {}
        self._next_id: int = 1
    
    @property
    def regions(self) -> List[HighlightRegion]:
        """获取所有区域列表"""
        return list(self._regions.values())
    
    @property
    def region_count(self) -> int:
        """获取区域数量"""
        return len(self._regions)
    
    def add_region(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: str = "yellow",
        opacity: float = 0.3
    ) -> int:
        """
        添加高亮区域
        
        Args:
            x1, y1: 左上角坐标
            x2, y2: 右下角坐标
            color: 高亮颜色
            opacity: 透明度
            
        Returns:
            int: 区域ID
        """
        region_id = self._next_id
        self._next_id += 1
        
        region = HighlightRegion(
            id=region_id,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            color=color,
            opacity=opacity,
        )
        
        self._regions[region_id] = region
        return region_id
    
    def remove_region(self, region_id: int) -> bool:
        """
        删除指定区域
        
        Args:
            region_id: 区域ID
            
        Returns:
            bool: 是否删除成功
        """
        if region_id in self._regions:
            del self._regions[region_id]
            return True
        return False
    
    def get_region(self, region_id: int) -> Optional[HighlightRegion]:
        """
        获取指定区域
        
        Args:
            region_id: 区域ID
            
        Returns:
            HighlightRegion: 区域对象，不存在返回None
        """
        return self._regions.get(region_id)
    
    def update_region(self, region_id: int, **kwargs) -> bool:
        """
        更新区域属性
        
        Args:
            region_id: 区域ID
            **kwargs: 要更新的属性
            
        Returns:
            bool: 是否更新成功
        """
        if region_id not in self._regions:
            return False
        
        region = self._regions[region_id]
        
        # 更新坐标
        if "x1" in kwargs:
            region.x1 = kwargs["x1"]
        if "y1" in kwargs:
            region.y1 = kwargs["y1"]
        if "x2" in kwargs:
            region.x2 = kwargs["x2"]
        if "y2" in kwargs:
            region.y2 = kwargs["y2"]
        
        # 确保坐标正确
        if region.x1 > region.x2:
            region.x1, region.x2 = region.x2, region.x1
        if region.y1 > region.y2:
            region.y1, region.y2 = region.y2, region.y1
        
        # 更新颜色
        if "color" in kwargs:
            color = kwargs["color"]
            if color in HIGHLIGHT_COLORS:
                region.color = color
        
        # 更新透明度
        if "opacity" in kwargs:
            region.opacity = max(0.0, min(1.0, kwargs["opacity"]))
        
        return True
    
    def get_region_at_point(self, x: int, y: int) -> Optional[int]:
        """
        获取指定坐标处的区域ID
        
        Args:
            x, y: 坐标
            
        Returns:
            int: 区域ID，不存在返回None
        """
        # 从后往前遍历，返回最上层的区域
        for region_id in reversed(list(self._regions.keys())):
            region = self._regions[region_id]
            if region.contains_point(x, y):
                return region_id
        return None
    
    def get_regions_at_point(self, x: int, y: int) -> List[int]:
        """
        获取指定坐标处的所有区域ID
        
        Args:
            x, y: 坐标
            
        Returns:
            List[int]: 区域ID列表
        """
        result = []
        for region_id, region in self._regions.items():
            if region.contains_point(x, y):
                result.append(region_id)
        return result
    
    def clear_all(self):
        """清除所有区域"""
        self._regions.clear()
    
    def render_highlights(self, image: QImage) -> QImage:
        """
        将所有高亮渲染到图片上
        
        Args:
            image: 原始图片
            
        Returns:
            QImage: 带高亮的图片（新副本）
        """
        if image.isNull():
            return image
        
        # 创建图片副本
        result = image.copy()
        
        if not self._regions:
            return result
        
        # 创建画笔
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制每个高亮区域
        for region in self._regions.values():
            if not region.is_valid:
                continue
            
            # 获取颜色
            fill_color = HIGHLIGHT_COLORS.get(region.color, HIGHLIGHT_COLORS["yellow"])
            border_color = BORDER_COLORS.get(region.color, BORDER_COLORS["yellow"])
            
            # 调整透明度
            fill_color = QColor(fill_color)
            fill_color.setAlphaF(region.opacity)
            
            # 绘制填充
            painter.fillRect(region.to_rect(), fill_color)
            
            # 绘制边框
            pen = QPen(border_color, 2)
            painter.setPen(pen)
            painter.drawRect(region.to_rect())
        
        painter.end()
        return result
    
    def render_single_highlight(
        self,
        image: QImage,
        region_id: int
    ) -> QImage:
        """
        渲染单个高亮区域
        
        Args:
            image: 原始图片
            region_id: 区域ID
            
        Returns:
            QImage: 带高亮的图片
        """
        if image.isNull():
            return image
        
        region = self._regions.get(region_id)
        if not region or not region.is_valid:
            return image.copy()
        
        result = image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 获取颜色
        fill_color = HIGHLIGHT_COLORS.get(region.color, HIGHLIGHT_COLORS["yellow"])
        border_color = BORDER_COLORS.get(region.color, BORDER_COLORS["yellow"])
        
        # 调整透明度
        fill_color = QColor(fill_color)
        fill_color.setAlphaF(region.opacity)
        
        # 绘制
        painter.fillRect(region.to_rect(), fill_color)
        pen = QPen(border_color, 2)
        painter.setPen(pen)
        painter.drawRect(region.to_rect())
        
        painter.end()
        return result
    
    def to_dict_list(self) -> List[Dict[str, Any]]:
        """将所有区域转换为字典列表"""
        return [region.to_dict() for region in self._regions.values()]
    
    def from_dict_list(self, data: List[Dict[str, Any]]):
        """从字典列表加载区域"""
        self.clear_all()
        
        max_id = 0
        for item in data:
            region = HighlightRegion.from_dict(item)
            self._regions[region.id] = region
            if region.id > max_id:
                max_id = region.id
        
        self._next_id = max_id + 1
