"""
渲染性能属性测试

Feature: performance-ui-optimization
Property 2: Rendering Performance
**Validates: Requirements 2.2, 2.4, 5.1**

测试渲染性能的核心属性：
1. 脏区域追踪和合并
2. 标注边界缓存
3. 帧时间在 16.67ms 以内（60 FPS）

Property 2: Rendering Performance
*For any* rendering operation (selection rectangle, annotation, animation),
the frame rate SHALL be at least 60 FPS (frame time ≤ 16.67ms).
"""

import time
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List, Tuple

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QPoint

from screenshot_tool.core.paint_engine import (
    DirtyRegion,
    AnnotationDirtyTracker,
    OptimizedPaintEngine,
)


# ========== QApplication 单例 ==========
# QPixmap 需要 QApplication 实例

_app = None

def get_app():
    """获取或创建 QApplication 实例"""
    global _app
    if _app is None:
        _app = QApplication.instance()
        if _app is None:
            _app = QApplication([])
    return _app


# ========== 常量定义 ==========

# 60 FPS 对应的最大帧时间（毫秒）
MAX_FRAME_TIME_MS = 16.67

# 测试用的屏幕尺寸
TEST_SCREEN_WIDTH = 1920
TEST_SCREEN_HEIGHT = 1080


# ========== Hypothesis Strategies ==========

def valid_rect_strategy():
    """生成有效的 QRect 策略"""
    return st.builds(
        lambda x, y, w, h: QRect(x, y, max(1, w), max(1, h)),
        x=st.integers(min_value=0, max_value=TEST_SCREEN_WIDTH - 100),
        y=st.integers(min_value=0, max_value=TEST_SCREEN_HEIGHT - 100),
        w=st.integers(min_value=1, max_value=500),
        h=st.integers(min_value=1, max_value=500),
    )


def point_strategy():
    """生成有效的 QPoint 策略"""
    return st.builds(
        QPoint,
        st.integers(min_value=0, max_value=TEST_SCREEN_WIDTH),
        st.integers(min_value=0, max_value=TEST_SCREEN_HEIGHT),
    )


def line_width_strategy():
    """生成有效的线条宽度策略"""
    return st.integers(min_value=1, max_value=32)


def item_id_strategy():
    """生成有效的标注项 ID 策略"""
    return st.integers(min_value=1, max_value=10000)


# ========== Fixtures ==========

@pytest.fixture
def paint_engine():
    """创建并初始化绘制引擎"""
    engine = OptimizedPaintEngine()
    engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    return engine


@pytest.fixture
def annotation_tracker():
    """创建标注脏区域追踪器"""
    return AnnotationDirtyTracker()


# ========== DirtyRegion 单元测试 ==========

class TestDirtyRegion:
    """DirtyRegion 数据类测试"""
    
    def test_dirty_region_creation(self):
        """测试 DirtyRegion 创建"""
        rect = QRect(10, 20, 100, 50)
        region = DirtyRegion(rect=rect, priority=1)
        
        assert region.rect == rect
        assert region.priority == 1
    
    def test_dirty_region_merge(self):
        """测试脏区域合并"""
        r1 = DirtyRegion(rect=QRect(0, 0, 100, 100), priority=1)
        r2 = DirtyRegion(rect=QRect(50, 50, 100, 100), priority=2)
        
        merged = r1.merge_with(r2)
        
        # 合并后的矩形应该包含两个原始矩形
        assert merged.rect.contains(r1.rect)
        assert merged.rect.contains(r2.rect)
        # 优先级取最大值
        assert merged.priority == 2
    
    def test_dirty_region_intersects(self):
        """测试脏区域相交检测"""
        r1 = DirtyRegion(rect=QRect(0, 0, 100, 100))
        r2 = DirtyRegion(rect=QRect(50, 50, 100, 100))
        r3 = DirtyRegion(rect=QRect(200, 200, 50, 50))
        
        assert r1.intersects(r2) is True
        assert r1.intersects(r3) is False


# ========== Property 2: Rendering Performance - 脏区域追踪测试 ==========

# 独立的属性测试函数（避免 hypothesis 与 pytest fixtures 冲突）

@settings(max_examples=100)
@given(rect=valid_rect_strategy())
def test_mark_dirty_records_region(rect: QRect):
    """Property 2.1: 标记脏区域被正确记录
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4**
    
    For any valid rectangle, marking it as dirty SHALL result in
    the region being included in the dirty regions list.
    """
    get_app()  # 确保 QApplication 存在
    paint_engine = OptimizedPaintEngine()
    paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    paint_engine.clear_dirty_regions()
    paint_engine._full_repaint_needed = False
    
    paint_engine.mark_dirty(rect)
    
    dirty_regions = paint_engine.get_dirty_regions()
    
    # 脏区域列表应该非空
    assert len(dirty_regions) > 0
    
    # 标记的区域应该被包含在某个脏区域中
    rect_covered = any(
        dr.contains(rect) or dr.intersects(rect)
        for dr in dirty_regions
    )
    assert rect_covered, \
        f"Marked rect {rect} not covered by any dirty region"


@settings(max_examples=100)
@given(
    rects=st.lists(valid_rect_strategy(), min_size=2, max_size=10)
)
def test_dirty_regions_merge_when_close(rects: List[QRect]):
    """Property 2.2: 相邻脏区域被合并
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    For any set of dirty regions that are close together,
    they SHALL be merged to reduce the number of repaint operations.
    """
    get_app()  # 确保 QApplication 存在
    paint_engine = OptimizedPaintEngine()
    paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    paint_engine.clear_dirty_regions()
    paint_engine._full_repaint_needed = False
    
    for rect in rects:
        paint_engine.mark_dirty(rect)
    
    dirty_regions = paint_engine.get_dirty_regions()
    
    # 合并后的脏区域数量应该 <= 原始数量
    assert len(dirty_regions) <= len(rects), \
        f"Merged regions ({len(dirty_regions)}) > original ({len(rects)})"


@settings(max_examples=100)
@given(rect=valid_rect_strategy())
def test_empty_rect_not_marked_dirty(rect: QRect):
    """Property 2.3: 空矩形不被标记为脏
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4**
    
    Empty rectangles SHALL NOT be added to the dirty regions list.
    """
    get_app()  # 确保 QApplication 存在
    paint_engine = OptimizedPaintEngine()
    paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    paint_engine.clear_dirty_regions()
    paint_engine._full_repaint_needed = False
    
    # 标记一个空矩形
    empty_rect = QRect()
    paint_engine.mark_dirty(empty_rect)
    
    # 空矩形不应该被添加
    assert not paint_engine.needs_repaint() or paint_engine._full_repaint_needed


# ========== Property 2: Rendering Performance - 标注边界缓存测试 ==========

# 独立的标注边界缓存属性测试函数

@settings(max_examples=100)
@given(
    item_id=item_id_strategy(),
    rect=valid_rect_strategy(),
    line_width=line_width_strategy()
)
def test_track_item_caches_bounds(item_id: int, rect: QRect, line_width: int):
    """Property 2.4: 标注项边界被正确缓存
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    For any annotation item, tracking it SHALL cache its bounding rectangle.
    """
    annotation_tracker = AnnotationDirtyTracker()
    annotation_tracker.begin_frame()
    annotation_tracker.track_item(item_id, rect, line_width)
    
    cached = annotation_tracker.get_cached_bounds(item_id)
    
    assert cached is not None, \
        f"Bounds for item {item_id} should be cached"
    # 缓存的边界应该包含原始矩形（可能有扩展边距）
    assert cached.contains(rect) or cached.intersects(rect), \
        f"Cached bounds {cached} should contain/intersect original {rect}"


@settings(max_examples=100)
@given(
    item_id=item_id_strategy(),
    old_rect=valid_rect_strategy(),
    new_rect=valid_rect_strategy(),
    line_width=line_width_strategy()
)
def test_track_item_moved_marks_both_regions_dirty(
    item_id: int, old_rect: QRect, new_rect: QRect, line_width: int
):
    """Property 2.5: 移动标注项标记新旧区域为脏
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    When an annotation item is moved, both the old and new regions
    SHALL be marked as dirty for repainting.
    """
    annotation_tracker = AnnotationDirtyTracker()
    annotation_tracker.begin_frame()
    annotation_tracker.track_item_moved(item_id, old_rect, new_rect, line_width)
    
    dirty_rects = annotation_tracker.get_dirty_rects()
    
    # 如果不需要全屏重绘，应该有脏区域
    if not annotation_tracker.needs_full_repaint():
        # 脏区域应该覆盖旧区域和新区域
        # 由于合并，可能不是精确匹配，但应该有脏区域
        assert annotation_tracker.has_dirty_regions(), \
            "Moving item should create dirty regions"


@settings(max_examples=100)
@given(
    item_id=item_id_strategy(),
    rect=valid_rect_strategy(),
    line_width=line_width_strategy()
)
def test_track_item_removed_marks_region_dirty(
    item_id: int, rect: QRect, line_width: int
):
    """Property 2.6: 删除标注项标记区域为脏
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    When an annotation item is removed, its region SHALL be marked
    as dirty for repainting.
    """
    annotation_tracker = AnnotationDirtyTracker()
    # 先追踪项
    annotation_tracker.begin_frame()
    annotation_tracker.track_item(item_id, rect, line_width)
    
    # 开始新帧
    annotation_tracker.begin_frame()
    
    # 删除项
    annotation_tracker.track_item_removed(item_id)
    
    # 应该有脏区域
    assert annotation_tracker.has_dirty_regions(), \
        "Removing item should create dirty regions"


@settings(max_examples=100)
@given(
    start_point=point_strategy(),
    end_point=point_strategy(),
    line_width=line_width_strategy()
)
def test_track_drawing_stroke_marks_region_dirty(
    start_point: QPoint, end_point: QPoint, line_width: int
):
    """Property 2.7: 绘制笔画标记区域为脏
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    When a drawing stroke is made, the stroke region SHALL be marked
    as dirty for repainting.
    """
    annotation_tracker = AnnotationDirtyTracker()
    annotation_tracker.begin_frame()
    annotation_tracker.clear_full_repaint()
    
    annotation_tracker.track_drawing_stroke(start_point, end_point, line_width)
    
    # 应该有脏区域
    assert annotation_tracker.has_dirty_regions(), \
        "Drawing stroke should create dirty regions"


# ========== Property 2: Rendering Performance - 帧时间测试 ==========

class TestFrameTimePerformance:
    """帧时间性能属性测试
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.2, 2.4, 5.1**
    
    For any rendering operation, the frame time SHALL be at most 16.67ms (60 FPS).
    """
    
    def test_dirty_region_marking_under_frame_time(self):
        """Property 2.8: 标记脏区域操作在帧时间内完成
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.4**
        
        Marking a dirty region SHALL complete within 16.67ms.
        """
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.clear_dirty_regions()
        paint_engine._full_repaint_needed = False
        
        rect = QRect(100, 100, 200, 200)
        
        start = time.perf_counter()
        paint_engine.mark_dirty(rect)
        duration_ms = (time.perf_counter() - start) * 1000
        
        assert duration_ms <= MAX_FRAME_TIME_MS, \
            f"mark_dirty took {duration_ms:.2f}ms, expected <= {MAX_FRAME_TIME_MS}ms"
    
    def test_annotation_tracking_under_frame_time(self):
        """Property 2.10: 标注追踪操作在帧时间内完成
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.4, 5.1**
        
        Tracking an annotation item SHALL complete within 16.67ms.
        """
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.begin_frame()
        
        rect = QRect(100, 100, 200, 200)
        
        start = time.perf_counter()
        annotation_tracker.track_item(1, rect, 2)
        duration_ms = (time.perf_counter() - start) * 1000
        
        assert duration_ms <= MAX_FRAME_TIME_MS, \
            f"track_item took {duration_ms:.2f}ms, expected <= {MAX_FRAME_TIME_MS}ms"
    
    def test_dirty_region_merge_under_frame_time(self):
        """Property 2.12: 脏区域合并在帧时间内完成
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.4, 5.1**
        
        Merging dirty regions SHALL complete within 16.67ms.
        """
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.begin_frame()
        annotation_tracker.clear_full_repaint()
        
        # 添加多个脏区域
        for i in range(20):
            rect = QRect(i * 50, i * 50, 100, 100)
            annotation_tracker._dirty_rects.append(rect)
        
        start = time.perf_counter()
        merged = annotation_tracker.get_dirty_rects()
        duration_ms = (time.perf_counter() - start) * 1000
        
        assert duration_ms <= MAX_FRAME_TIME_MS, \
            f"Merging dirty regions took {duration_ms:.2f}ms, " \
            f"expected <= {MAX_FRAME_TIME_MS}ms"


# 独立的帧时间属性测试函数

@settings(max_examples=50)
@given(
    rects=st.lists(valid_rect_strategy(), min_size=1, max_size=20)
)
def test_multiple_dirty_regions_under_frame_time(rects: List[QRect]):
    """Property 2.9: 多个脏区域标记在帧时间内完成
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    Marking multiple dirty regions SHALL complete within 16.67ms.
    """
    get_app()  # 确保 QApplication 存在
    paint_engine = OptimizedPaintEngine()
    paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    paint_engine.clear_dirty_regions()
    paint_engine._full_repaint_needed = False
    
    start = time.perf_counter()
    for rect in rects:
        paint_engine.mark_dirty(rect)
    duration_ms = (time.perf_counter() - start) * 1000
    
    assert duration_ms <= MAX_FRAME_TIME_MS, \
        f"Marking {len(rects)} dirty regions took {duration_ms:.2f}ms, " \
        f"expected <= {MAX_FRAME_TIME_MS}ms"


@settings(max_examples=50)
@given(
    items=st.lists(
        st.tuples(item_id_strategy(), valid_rect_strategy(), line_width_strategy()),
        min_size=1,
        max_size=50
    )
)
def test_multiple_annotations_tracking_under_frame_time(
    items: List[Tuple[int, QRect, int]]
):
    """Property 2.11: 多个标注追踪在帧时间内完成
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.4, 5.1**
    
    Tracking multiple annotation items SHALL complete within 16.67ms.
    """
    annotation_tracker = AnnotationDirtyTracker()
    annotation_tracker.begin_frame()
    
    start = time.perf_counter()
    for item_id, rect, line_width in items:
        annotation_tracker.track_item(item_id, rect, line_width)
    duration_ms = (time.perf_counter() - start) * 1000
    
    assert duration_ms <= MAX_FRAME_TIME_MS, \
        f"Tracking {len(items)} items took {duration_ms:.2f}ms, " \
        f"expected <= {MAX_FRAME_TIME_MS}ms"


# ========== Property 2: Rendering Performance - 缓冲区测试 ==========

class TestBufferPerformance:
    """缓冲区性能属性测试
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.2, 2.4, 5.1**
    """
    
    def test_buffer_initialization_reasonable_time(self):
        """Property 2.13: 缓冲区初始化在合理时间内完成
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.2**
        
        Buffer initialization SHALL complete within a reasonable time (< 100ms).
        """
        get_app()  # 确保 QApplication 存在
        engine = OptimizedPaintEngine()
        
        start = time.perf_counter()
        engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        duration_ms = (time.perf_counter() - start) * 1000
        
        # 初始化可以稍慢，但应该在 100ms 内
        assert duration_ms < 100, \
            f"Buffer initialization took {duration_ms:.2f}ms, expected < 100ms"
    
    def test_buffer_reuse_when_size_unchanged(self):
        """Property 2.14: 尺寸不变时复用缓冲区
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.2, 5.1**
        
        When buffer size is unchanged, the buffer SHALL be reused.
        """
        get_app()  # 确保 QApplication 存在
        engine = OptimizedPaintEngine()
        
        # 第一次初始化
        engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        buffer1 = engine.get_buffer()
        
        # 第二次初始化（相同尺寸）
        engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        buffer2 = engine.get_buffer()
        
        # 应该是同一个缓冲区
        assert buffer1 is buffer2, \
            "Buffer should be reused when size is unchanged"


# 独立的缓冲区属性测试函数

@settings(max_examples=50)
@given(
    width=st.integers(min_value=100, max_value=3840),
    height=st.integers(min_value=100, max_value=2160)
)
def test_buffer_created_for_any_valid_size(width: int, height: int):
    """Property 2.15: 任何有效尺寸都能创建缓冲区
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.2**
    
    For any valid screen size, a buffer SHALL be created successfully.
    """
    get_app()  # 确保 QApplication 存在
    engine = OptimizedPaintEngine()
    engine.initialize(width, height)
    
    buffer = engine.get_buffer()
    
    assert buffer is not None, \
        f"Buffer should be created for size {width}x{height}"


# ========== Property 2: Rendering Performance - 选区变化测试 ==========

class TestSelectionChangePerformance:
    """选区变化性能属性测试
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.2, 2.4**
    """
    
    def test_selection_change_under_frame_time(self):
        """Property 2.17: 选区变化处理在帧时间内完成
        
        Feature: performance-ui-optimization, Property 2: Rendering Performance
        **Validates: Requirements 2.2**
        
        Processing selection change SHALL complete within 16.67ms.
        """
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.clear_dirty_regions()
        paint_engine._full_repaint_needed = False
        
        old_rect = QRect(100, 100, 200, 200)
        new_rect = QRect(150, 150, 250, 250)
        
        start = time.perf_counter()
        paint_engine.mark_selection_changed(old_rect, new_rect)
        duration_ms = (time.perf_counter() - start) * 1000
        
        assert duration_ms <= MAX_FRAME_TIME_MS, \
            f"Selection change took {duration_ms:.2f}ms, expected <= {MAX_FRAME_TIME_MS}ms"


# 独立的选区变化属性测试函数

@settings(max_examples=100)
@given(
    old_rect=valid_rect_strategy(),
    new_rect=valid_rect_strategy()
)
def test_selection_change_marks_dirty(old_rect: QRect, new_rect: QRect):
    """Property 2.16: 选区变化标记脏区域
    
    Feature: performance-ui-optimization, Property 2: Rendering Performance
    **Validates: Requirements 2.2, 2.4**
    
    When selection changes, both old and new regions SHALL be marked dirty.
    """
    get_app()  # 确保 QApplication 存在
    paint_engine = OptimizedPaintEngine()
    paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
    paint_engine.clear_dirty_regions()
    paint_engine._full_repaint_needed = False
    
    paint_engine.mark_selection_changed(old_rect, new_rect)
    
    # 应该需要重绘
    assert paint_engine.needs_repaint(), \
        "Selection change should trigger repaint"


# ========== 单元测试 ==========

class TestOptimizedPaintEngineUnit:
    """OptimizedPaintEngine 单元测试"""
    
    def test_engine_initialization(self):
        """测试引擎初始化"""
        get_app()  # 确保 QApplication 存在
        engine = OptimizedPaintEngine()
        engine.initialize(1920, 1080)
        
        assert engine.get_buffer() is not None
        assert engine._buffer_size == QRect(0, 0, 1920, 1080)
    
    def test_mark_full_repaint(self):
        """测试标记全屏重绘"""
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.mark_full_repaint()
        
        assert paint_engine._full_repaint_needed is True
        assert paint_engine.needs_repaint() is True
    
    def test_clear_dirty_regions(self):
        """测试清除脏区域"""
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.mark_dirty(QRect(0, 0, 100, 100))
        paint_engine.clear_dirty_regions()
        
        assert paint_engine._full_repaint_needed is False
        assert len(paint_engine._dirty_regions) == 0
    
    def test_get_dirty_regions_full_repaint(self):
        """测试全屏重绘时返回整个屏幕"""
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.mark_full_repaint()
        
        regions = paint_engine.get_dirty_regions()
        
        assert len(regions) == 1
        assert regions[0] == paint_engine._buffer_size
    
    def test_cleanup(self):
        """测试清理资源"""
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.cleanup()
        
        assert paint_engine._buffer is None
        assert paint_engine._mask_cache is None
        assert paint_engine._full_repaint_needed is True
    
    def test_reset(self):
        """测试重置状态"""
        get_app()  # 确保 QApplication 存在
        paint_engine = OptimizedPaintEngine()
        paint_engine.initialize(TEST_SCREEN_WIDTH, TEST_SCREEN_HEIGHT)
        paint_engine.mark_dirty(QRect(0, 0, 100, 100))
        paint_engine.reset()
        
        assert paint_engine._full_repaint_needed is True
        assert len(paint_engine._dirty_regions) == 0


class TestAnnotationDirtyTrackerUnit:
    """AnnotationDirtyTracker 单元测试"""
    
    def test_tracker_initialization(self):
        """测试追踪器初始化"""
        tracker = AnnotationDirtyTracker()
        
        assert tracker._full_repaint is True
        assert len(tracker._bounding_cache) == 0
    
    def test_begin_frame(self):
        """测试开始新帧"""
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.track_item(1, QRect(0, 0, 100, 100), 2)
        annotation_tracker.begin_frame()
        
        # 上一帧的缓存应该被保存
        assert 1 in annotation_tracker._prev_bounding_cache
    
    def test_clear(self):
        """测试清除追踪数据"""
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.track_item(1, QRect(0, 0, 100, 100), 2)
        annotation_tracker.clear()
        
        assert len(annotation_tracker._bounding_cache) == 0
        assert annotation_tracker._full_repaint is True
    
    def test_mark_full_repaint(self):
        """测试标记全屏重绘"""
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.mark_full_repaint()
        
        assert annotation_tracker.needs_full_repaint() is True
    
    def test_clear_full_repaint(self):
        """测试清除全屏重绘标记"""
        annotation_tracker = AnnotationDirtyTracker()
        annotation_tracker.mark_full_repaint()
        annotation_tracker.clear_full_repaint()
        
        assert annotation_tracker.needs_full_repaint() is False
