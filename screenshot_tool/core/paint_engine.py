# =====================================================
# =============== 优化绘制引擎 ===============
# =====================================================

"""
优化的绘制引擎 - 实现双缓冲、遮罩缓存和脏区域追踪

性能优化策略：
1. 双缓冲：在离屏缓冲上绘制，然后复制到屏幕，避免闪烁
2. 遮罩缓存：缓存遮罩 pixmap，选区变化时只更新变化部分
3. 脏区域追踪：标记需要重绘的区域，只重绘脏区域
4. 标注边界缓存：缓存标注项的边界矩形，高效计算脏区域

Feature: performance-ui-optimization
Requirements: 2.4, 5.1
Property 2: Rendering Performance
"""

from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

from PySide6.QtCore import QRect, QPoint
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage


@dataclass
class DirtyRegion:
    """脏区域，用于局部重绘"""
    rect: QRect
    priority: int = 0  # 优先级，高优先级先绘制
    
    def merge_with(self, other: 'DirtyRegion') -> 'DirtyRegion':
        """合并两个脏区域"""
        return DirtyRegion(
            rect=self.rect.united(other.rect),
            priority=max(self.priority, other.priority)
        )
    
    def intersects(self, other: 'DirtyRegion') -> bool:
        """检查两个脏区域是否相交"""
        return self.rect.intersects(other.rect)


class AnnotationDirtyTracker:
    """标注工具脏区域追踪器
    
    专门用于追踪标注工具（矩形、椭圆、箭头、直线、文字、马赛克等）的变化，
    实现高效的局部重绘。
    
    Feature: performance-ui-optimization
    Requirements: 2.4, 5.1
    Property 2: Rendering Performance
    """
    
    # 边界扩展边距（包含边框、手柄等）
    BOUNDING_MARGIN = 15
    
    # 画笔/线条额外边距（基于线宽）
    LINE_WIDTH_MARGIN_FACTOR = 1.5
    
    def __init__(self):
        # 标注项边界缓存：item_id -> QRect
        self._bounding_cache: Dict[int, QRect] = {}
        
        # 上一帧的边界缓存（用于检测变化）
        self._prev_bounding_cache: Dict[int, QRect] = {}
        
        # 当前帧的脏区域列表
        self._dirty_rects: List[QRect] = []
        
        # 是否需要全量重绘
        self._full_repaint: bool = True
    
    def begin_frame(self):
        """开始新的一帧
        
        保存当前边界缓存作为上一帧，清空脏区域列表。
        """
        self._prev_bounding_cache = self._bounding_cache.copy()
        self._dirty_rects.clear()
    
    def track_item(self, item_id: int, bounding_rect: QRect, line_width: int = 2):
        """追踪标注项的边界
        
        Args:
            item_id: 标注项的唯一 ID
            bounding_rect: 标注项的边界矩形
            line_width: 线条宽度（用于计算额外边距）
        """
        if bounding_rect.isEmpty():
            return
        
        # 计算扩展后的边界（包含边框、手柄、线宽）
        extra_margin = max(
            self.BOUNDING_MARGIN,
            int(line_width * self.LINE_WIDTH_MARGIN_FACTOR)
        )
        expanded = bounding_rect.adjusted(
            -extra_margin, -extra_margin,
            extra_margin, extra_margin
        )
        
        # 检查是否有变化
        prev_rect = self._prev_bounding_cache.get(item_id)
        
        if prev_rect is None:
            # 新增的标注项
            self._dirty_rects.append(expanded)
        elif prev_rect != expanded:
            # 边界发生变化，标记旧区域和新区域都为脏
            self._dirty_rects.append(prev_rect)
            self._dirty_rects.append(expanded)
        
        # 更新缓存
        self._bounding_cache[item_id] = expanded
    
    def track_item_removed(self, item_id: int):
        """追踪标注项被删除
        
        Args:
            item_id: 被删除的标注项 ID
        """
        if item_id in self._bounding_cache:
            # 标记旧区域为脏
            self._dirty_rects.append(self._bounding_cache[item_id])
            del self._bounding_cache[item_id]
        
        if item_id in self._prev_bounding_cache:
            self._dirty_rects.append(self._prev_bounding_cache[item_id])
    
    def track_item_moved(self, item_id: int, old_rect: QRect, new_rect: QRect, line_width: int = 2):
        """追踪标注项移动
        
        Args:
            item_id: 标注项 ID
            old_rect: 移动前的边界
            new_rect: 移动后的边界
            line_width: 线条宽度
        """
        extra_margin = max(
            self.BOUNDING_MARGIN,
            int(line_width * self.LINE_WIDTH_MARGIN_FACTOR)
        )
        
        old_expanded = old_rect.adjusted(
            -extra_margin, -extra_margin,
            extra_margin, extra_margin
        )
        new_expanded = new_rect.adjusted(
            -extra_margin, -extra_margin,
            extra_margin, extra_margin
        )
        
        # 标记旧区域和新区域都为脏
        self._dirty_rects.append(old_expanded)
        self._dirty_rects.append(new_expanded)
        
        # 更新缓存
        self._bounding_cache[item_id] = new_expanded
    
    def track_item_resized(self, item_id: int, old_rect: QRect, new_rect: QRect, line_width: int = 2):
        """追踪标注项缩放
        
        Args:
            item_id: 标注项 ID
            old_rect: 缩放前的边界
            new_rect: 缩放后的边界
            line_width: 线条宽度
        """
        # 缩放和移动的处理逻辑相同
        self.track_item_moved(item_id, old_rect, new_rect, line_width)
    
    def track_drawing_stroke(self, start_point: QPoint, end_point: QPoint, line_width: int):
        """追踪正在绘制的笔画
        
        用于画笔工具的实时绘制，只更新笔画覆盖的区域。
        
        Args:
            start_point: 笔画起点
            end_point: 笔画终点
            line_width: 线条宽度
        """
        # 计算笔画的边界矩形
        min_x = min(start_point.x(), end_point.x())
        max_x = max(start_point.x(), end_point.x())
        min_y = min(start_point.y(), end_point.y())
        max_y = max(start_point.y(), end_point.y())
        
        # 确保宽高至少为 1
        width = max(1, max_x - min_x)
        height = max(1, max_y - min_y)
        
        stroke_rect = QRect(min_x, min_y, width, height)
        
        # 扩展边界以包含线宽
        margin = int(line_width * self.LINE_WIDTH_MARGIN_FACTOR) + 2
        expanded = stroke_rect.adjusted(-margin, -margin, margin, margin)
        
        self._dirty_rects.append(expanded)
    
    def get_dirty_rects(self) -> List[QRect]:
        """获取当前帧的脏区域列表
        
        Returns:
            脏区域列表（已合并相邻区域）
        """
        if self._full_repaint:
            return []  # 返回空列表表示需要全屏重绘
        
        return self._merge_dirty_rects(self._dirty_rects)
    
    def _merge_dirty_rects(self, rects: List[QRect], threshold: int = 50) -> List[QRect]:
        """合并相邻的脏区域
        
        Args:
            rects: 脏区域列表
            threshold: 合并阈值（像素）
            
        Returns:
            合并后的脏区域列表
        """
        if not rects:
            return []
        
        # 过滤空矩形
        valid_rects = [r for r in rects if not r.isEmpty()]
        if not valid_rects:
            return []
        
        # 简单的贪婪合并算法
        merged = [valid_rects[0]]
        
        for rect in valid_rects[1:]:
            merged_with_existing = False
            
            for i, existing in enumerate(merged):
                # 检查是否相交或距离很近
                if existing.intersects(rect) or self._rects_close(existing, rect, threshold):
                    merged[i] = existing.united(rect)
                    merged_with_existing = True
                    break
            
            if not merged_with_existing:
                merged.append(rect)
        
        return merged
    
    def _rects_close(self, r1: QRect, r2: QRect, threshold: int) -> bool:
        """检查两个矩形是否距离很近
        
        Args:
            r1, r2: 两个矩形
            threshold: 距离阈值
            
        Returns:
            是否距离小于阈值
        """
        # 水平距离
        if r1.right() < r2.left():
            h_dist = r2.left() - r1.right()
        elif r2.right() < r1.left():
            h_dist = r1.left() - r2.right()
        else:
            h_dist = 0
        
        # 垂直距离
        if r1.bottom() < r2.top():
            v_dist = r2.top() - r1.bottom()
        elif r2.bottom() < r1.top():
            v_dist = r1.top() - r2.bottom()
        else:
            v_dist = 0
        
        return h_dist <= threshold and v_dist <= threshold
    
    def has_dirty_regions(self) -> bool:
        """检查是否有脏区域"""
        return len(self._dirty_rects) > 0 or self._full_repaint
    
    def needs_full_repaint(self) -> bool:
        """检查是否需要全屏重绘"""
        return self._full_repaint
    
    def mark_full_repaint(self):
        """标记需要全屏重绘"""
        self._full_repaint = True
        self._dirty_rects.clear()
    
    def clear_full_repaint(self):
        """清除全屏重绘标记"""
        self._full_repaint = False
    
    def clear(self):
        """清除所有追踪数据"""
        self._bounding_cache.clear()
        self._prev_bounding_cache.clear()
        self._dirty_rects.clear()
        self._full_repaint = True
    
    def get_cached_bounds(self, item_id: int) -> Optional[QRect]:
        """获取缓存的标注项边界
        
        Args:
            item_id: 标注项 ID
            
        Returns:
            缓存的边界矩形，如果不存在返回 None
        """
        return self._bounding_cache.get(item_id)


class OptimizedPaintEngine:
    """优化的绘制引擎
    
    实现双缓冲、遮罩缓存和脏区域追踪，提高绘制性能。
    
    Feature: performance-ui-optimization
    Requirements: 2.4, 5.1
    Property 2: Rendering Performance
    """
    
    # 脏区域合并阈值（像素）
    MERGE_THRESHOLD = 50
    
    # 最大脏区域数量（超过后强制全屏重绘）
    MAX_DIRTY_REGIONS = 20
    
    def __init__(self):
        # 双缓冲
        self._buffer: Optional[QPixmap] = None
        self._buffer_size: QRect = QRect()
        
        # 设备像素比
        self._device_pixel_ratio: float = 1.0
        
        # 遮罩缓存
        self._mask_cache: Optional[QPixmap] = None
        self._cached_selection: Optional[QRect] = None
        self._cached_screen_size: QRect = QRect()
        
        # 脏区域列表
        self._dirty_regions: List[DirtyRegion] = []
        self._full_repaint_needed: bool = True
        
        # 上次绘制状态（用于检测变化）
        self._last_selection: Optional[QRect] = None
        self._last_draw_items_count: int = 0
        
        # 标注脏区域追踪器
        # Feature: performance-ui-optimization
        # Requirements: 2.4, 5.1
        self._annotation_tracker = AnnotationDirtyTracker()
    
    def initialize(self, width: int, height: int, device_pixel_ratio: float = 1.0):
        """初始化缓冲区
        
        Args:
            width: 屏幕宽度（逻辑像素）
            height: 屏幕高度（逻辑像素）
            device_pixel_ratio: 设备像素比
        """
        new_size = QRect(0, 0, width, height)
        
        # 如果尺寸和 DPR 都没变，不需要重新创建
        if (self._buffer_size == new_size and 
            self._buffer is not None and
            self._device_pixel_ratio == device_pixel_ratio):
            return
        
        # 创建双缓冲（使用物理像素尺寸）
        phys_width = int(width * device_pixel_ratio)
        phys_height = int(height * device_pixel_ratio)
        self._buffer = QPixmap(phys_width, phys_height)
        self._buffer.setDevicePixelRatio(device_pixel_ratio)
        self._buffer_size = new_size
        self._device_pixel_ratio = device_pixel_ratio
        
        # 重置遮罩缓存
        self._mask_cache = None
        self._cached_selection = None
        self._cached_screen_size = new_size
        
        # 标记需要全屏重绘
        self._full_repaint_needed = True
        self._dirty_regions.clear()
    
    def mark_dirty(self, region: QRect, priority: int = 0):
        """标记脏区域
        
        Args:
            region: 需要重绘的区域
            priority: 优先级（高优先级先绘制）
        """
        if region.isEmpty():
            return
        
        # 如果已经需要全屏重绘，忽略新的脏区域
        if self._full_repaint_needed:
            return
        
        new_dirty = DirtyRegion(rect=region.normalized(), priority=priority)
        
        # 尝试与现有脏区域合并
        merged = False
        for i, existing in enumerate(self._dirty_regions):
            # 如果两个区域相交或距离很近，合并它们
            if existing.intersects(new_dirty) or self._should_merge(existing, new_dirty):
                self._dirty_regions[i] = existing.merge_with(new_dirty)
                merged = True
                break
        
        if not merged:
            self._dirty_regions.append(new_dirty)
        
        # 如果脏区域太多，强制全屏重绘
        if len(self._dirty_regions) > self.MAX_DIRTY_REGIONS:
            self._full_repaint_needed = True
            self._dirty_regions.clear()
    
    def _should_merge(self, r1: DirtyRegion, r2: DirtyRegion) -> bool:
        """判断两个脏区域是否应该合并"""
        # 计算两个矩形的距离
        rect1, rect2 = r1.rect, r2.rect
        
        # 水平距离
        if rect1.right() < rect2.left():
            h_dist = rect2.left() - rect1.right()
        elif rect2.right() < rect1.left():
            h_dist = rect1.left() - rect2.right()
        else:
            h_dist = 0
        
        # 垂直距离
        if rect1.bottom() < rect2.top():
            v_dist = rect2.top() - rect1.bottom()
        elif rect2.bottom() < rect1.top():
            v_dist = rect1.top() - rect2.bottom()
        else:
            v_dist = 0
        
        # 如果距离小于阈值，合并
        return h_dist <= self.MERGE_THRESHOLD and v_dist <= self.MERGE_THRESHOLD
    
    def mark_selection_changed(self, old_rect: Optional[QRect], new_rect: Optional[QRect]):
        """标记选区变化
        
        Args:
            old_rect: 旧选区
            new_rect: 新选区
        """
        # 标记旧选区和新选区都需要重绘
        if old_rect and not old_rect.isEmpty():
            # 扩展一点以包含边框
            expanded = old_rect.adjusted(-5, -5, 5, 5)
            self.mark_dirty(expanded, priority=1)
        
        if new_rect and not new_rect.isEmpty():
            expanded = new_rect.adjusted(-5, -5, 5, 5)
            self.mark_dirty(expanded, priority=1)
        
        # 遮罩缓存失效
        self._cached_selection = None
    
    def mark_full_repaint(self):
        """标记需要全屏重绘"""
        self._full_repaint_needed = True
        self._dirty_regions.clear()
        self._cached_selection = None
    
    def needs_repaint(self) -> bool:
        """检查是否需要重绘"""
        return self._full_repaint_needed or len(self._dirty_regions) > 0
    
    def get_dirty_regions(self) -> List[QRect]:
        """获取需要重绘的区域列表
        
        Returns:
            脏区域列表，如果需要全屏重绘则返回包含整个屏幕的列表
        """
        if self._full_repaint_needed:
            return [self._buffer_size]
        
        # 按优先级排序
        sorted_regions = sorted(self._dirty_regions, key=lambda r: -r.priority)
        return [r.rect for r in sorted_regions]
    
    def clear_dirty_regions(self):
        """清除脏区域标记"""
        self._dirty_regions.clear()
        self._full_repaint_needed = False
    
    def get_buffer(self) -> Optional[QPixmap]:
        """获取双缓冲 pixmap"""
        return self._buffer
    
    def begin_paint(self) -> Optional[QPainter]:
        """开始在缓冲上绘制
        
        Returns:
            QPainter 对象，如果缓冲不可用则返回 None
        """
        if self._buffer is None:
            return None
        
        painter = QPainter(self._buffer)
        if not painter.isActive():
            return None
        
        return painter
    
    def end_paint(self, painter: QPainter):
        """结束绘制"""
        if painter and painter.isActive():
            painter.end()
    
    def get_or_create_mask(
        self, 
        screen_rect: QRect, 
        selection_rect: Optional[QRect],
        mask_color: QColor = QColor(0, 0, 0, 100)
    ) -> Optional[QPixmap]:
        """获取或创建遮罩缓存
        
        Args:
            screen_rect: 屏幕区域（逻辑像素）
            selection_rect: 选区（None 表示全屏遮罩，逻辑像素）
            mask_color: 遮罩颜色
        
        Returns:
            遮罩 pixmap（物理像素大小，设置了 devicePixelRatio）
        """
        # 检查缓存是否有效
        if (self._mask_cache is not None and 
            self._cached_selection == selection_rect and
            self._cached_screen_size == screen_rect):
            return self._mask_cache
        
        # 创建新的遮罩（使用物理像素尺寸）
        dpr = self._device_pixel_ratio
        phys_width = int(screen_rect.width() * dpr)
        phys_height = int(screen_rect.height() * dpr)
        
        self._mask_cache = QPixmap(phys_width, phys_height)
        self._mask_cache.setDevicePixelRatio(dpr)
        self._mask_cache.fill(QColor(0, 0, 0, 0))  # 透明背景
        
        painter = QPainter(self._mask_cache)
        if not painter.isActive():
            self._mask_cache = None
            return None
        
        if selection_rect is None or selection_rect.isEmpty():
            # 全屏遮罩（使用逻辑像素坐标，Qt 会自动处理 DPR）
            painter.fillRect(screen_rect, mask_color)
        else:
            # 只遮罩选区外的区域（使用逻辑像素坐标）
            # 上方
            painter.fillRect(0, 0, screen_rect.width(), selection_rect.top(), mask_color)
            # 下方
            painter.fillRect(
                0, selection_rect.bottom() + 1, 
                screen_rect.width(), screen_rect.height() - selection_rect.bottom() - 1, 
                mask_color
            )
            # 左侧
            painter.fillRect(
                0, selection_rect.top(), 
                selection_rect.left(), selection_rect.height(), 
                mask_color
            )
            # 右侧
            painter.fillRect(
                selection_rect.right() + 1, selection_rect.top(), 
                screen_rect.width() - selection_rect.right() - 1, selection_rect.height(), 
                mask_color
            )
        
        painter.end()
        
        # 更新缓存状态
        self._cached_selection = QRect(selection_rect) if selection_rect else None
        self._cached_screen_size = screen_rect
        
        return self._mask_cache
    
    def invalidate_mask_cache(self):
        """使遮罩缓存失效"""
        self._cached_selection = None
    
    def paint_to_screen(self, screen_painter: QPainter):
        """将缓冲绘制到屏幕
        
        Args:
            screen_painter: 屏幕的 QPainter
        """
        if self._buffer is None:
            return
        
        if self._full_repaint_needed:
            # 全屏绘制
            screen_painter.drawPixmap(0, 0, self._buffer)
        else:
            # 只绘制脏区域
            for region in self._dirty_regions:
                rect = region.rect
                screen_painter.drawPixmap(rect, self._buffer, rect)
    
    def cleanup(self):
        """清理资源"""
        self._buffer = None
        self._mask_cache = None
        self._cached_selection = None
        self._dirty_regions.clear()
        self._full_repaint_needed = True
        self._annotation_tracker.clear()
    
    def reset(self):
        """重置状态（开始新的截图会话）"""
        self._dirty_regions.clear()
        self._full_repaint_needed = True
        self._cached_selection = None
        self._last_selection = None
        self._last_draw_items_count = 0
        self._annotation_tracker.clear()
    
    # =====================================================
    # 标注工具脏区域追踪方法
    # Feature: performance-ui-optimization
    # Requirements: 2.4, 5.1
    # =====================================================
    
    @property
    def annotation_tracker(self) -> AnnotationDirtyTracker:
        """获取标注脏区域追踪器"""
        return self._annotation_tracker
    
    def begin_annotation_frame(self):
        """开始新的标注帧
        
        在每次 paintEvent 开始时调用，保存上一帧的边界状态。
        """
        self._annotation_tracker.begin_frame()
    
    def track_annotation(self, item_id: int, bounding_rect: QRect, line_width: int = 2):
        """追踪标注项
        
        Args:
            item_id: 标注项的唯一 ID
            bounding_rect: 标注项的边界矩形
            line_width: 线条宽度
        """
        self._annotation_tracker.track_item(item_id, bounding_rect, line_width)
    
    def track_annotation_removed(self, item_id: int):
        """追踪标注项被删除
        
        Args:
            item_id: 被删除的标注项 ID
        """
        self._annotation_tracker.track_item_removed(item_id)
        # 同时标记脏区域
        cached_bounds = self._annotation_tracker.get_cached_bounds(item_id)
        if cached_bounds:
            self.mark_dirty(cached_bounds, priority=2)
    
    def track_annotation_moved(self, item_id: int, old_rect: QRect, new_rect: QRect, line_width: int = 2):
        """追踪标注项移动
        
        Args:
            item_id: 标注项 ID
            old_rect: 移动前的边界
            new_rect: 移动后的边界
            line_width: 线条宽度
        """
        self._annotation_tracker.track_item_moved(item_id, old_rect, new_rect, line_width)
        # 同时标记脏区域
        margin = max(15, int(line_width * 1.5))
        self.mark_dirty(old_rect.adjusted(-margin, -margin, margin, margin), priority=2)
        self.mark_dirty(new_rect.adjusted(-margin, -margin, margin, margin), priority=2)
    
    def track_annotation_resized(self, item_id: int, old_rect: QRect, new_rect: QRect, line_width: int = 2):
        """追踪标注项缩放
        
        Args:
            item_id: 标注项 ID
            old_rect: 缩放前的边界
            new_rect: 缩放后的边界
            line_width: 线条宽度
        """
        self._annotation_tracker.track_item_resized(item_id, old_rect, new_rect, line_width)
        # 同时标记脏区域
        margin = max(15, int(line_width * 1.5))
        self.mark_dirty(old_rect.adjusted(-margin, -margin, margin, margin), priority=2)
        self.mark_dirty(new_rect.adjusted(-margin, -margin, margin, margin), priority=2)
    
    def track_drawing_stroke(self, start_point: QPoint, end_point: QPoint, line_width: int):
        """追踪正在绘制的笔画
        
        用于画笔工具的实时绘制。
        
        Args:
            start_point: 笔画起点
            end_point: 笔画终点
            line_width: 线条宽度
        """
        self._annotation_tracker.track_drawing_stroke(start_point, end_point, line_width)
        
        # 计算笔画区域并标记为脏
        min_x = min(start_point.x(), end_point.x())
        max_x = max(start_point.x(), end_point.x())
        min_y = min(start_point.y(), end_point.y())
        max_y = max(start_point.y(), end_point.y())
        
        stroke_rect = QRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))
        margin = int(line_width * 1.5) + 2
        self.mark_dirty(stroke_rect.adjusted(-margin, -margin, margin, margin), priority=3)
    
    def get_annotation_dirty_rects(self) -> List[QRect]:
        """获取标注相关的脏区域
        
        Returns:
            标注脏区域列表
        """
        return self._annotation_tracker.get_dirty_rects()


class PaintEngineIntegration:
    """绘制引擎集成辅助类
    
    提供与 OverlayScreenshot 集成的便捷方法。
    """
    
    def __init__(self, engine: OptimizedPaintEngine):
        self._engine = engine
        self._enabled = True
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
    
    def should_use_optimization(self) -> bool:
        """判断是否应该使用优化绘制"""
        return self._enabled and self._engine.get_buffer() is not None
    
    def prepare_paint(
        self, 
        width: int, 
        height: int, 
        screenshot: QPixmap,
        selection_rect: Optional[QRect],
        draw_items_count: int
    ) -> bool:
        """准备绘制
        
        Args:
            width: 窗口宽度
            height: 窗口高度
            screenshot: 截图
            selection_rect: 选区
            draw_items_count: 绘制项数量
        
        Returns:
            是否需要重绘
        """
        if not self._enabled:
            return True
        
        # 初始化缓冲
        self._engine.initialize(width, height)
        
        # 检测变化
        if self._engine._last_selection != selection_rect:
            self._engine.mark_selection_changed(
                self._engine._last_selection, 
                selection_rect
            )
            self._engine._last_selection = QRect(selection_rect) if selection_rect else None
        
        if self._engine._last_draw_items_count != draw_items_count:
            # 绘制项数量变化，需要重绘
            self._engine.mark_full_repaint()
            self._engine._last_draw_items_count = draw_items_count
        
        return self._engine.needs_repaint()
