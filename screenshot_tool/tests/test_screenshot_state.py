# -*- coding: utf-8 -*-
"""
截图状态管理器测试

Feature: screenshot-state-restore
"""

import json
import os
import tempfile
import shutil
from typing import List, Tuple

import pytest
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.core.screenshot_state_manager import (
    AnnotationData,
    ScreenshotState,
    ScreenshotStateManager,
)


# ============================================================
# Hypothesis Strategies - 智能生成器
# ============================================================

# 有效的工具类型
VALID_TOOLS = ["rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"]

# 颜色策略：生成有效的十六进制颜色
hex_color_strategy = st.from_regex(r"#[0-9A-Fa-f]{6}", fullmatch=True)

# 点坐标策略：生成合理范围内的坐标
point_strategy = st.tuples(
    st.integers(min_value=0, max_value=10000),
    st.integers(min_value=0, max_value=10000)
)

# 点列表策略：生成 1-100 个点
points_list_strategy = st.lists(point_strategy, min_size=1, max_size=100)

# 文本策略：生成各种字符串（包括空字符串、Unicode）
text_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        blacklist_characters='\x00'  # 排除 null 字符
    ),
    min_size=0,
    max_size=500
)

# AnnotationData 策略
@st.composite
def annotation_data_strategy(draw):
    """生成随机 AnnotationData"""
    tool = draw(st.sampled_from(VALID_TOOLS))
    color = draw(hex_color_strategy)
    width = draw(st.integers(min_value=1, max_value=100))
    points = draw(points_list_strategy)
    text = draw(text_strategy) if tool == "text" else ""
    step_number = draw(st.integers(min_value=0, max_value=999)) if tool == "step" else 0
    
    return AnnotationData(
        tool=tool,
        color=color,
        width=width,
        points=points,
        text=text,
        step_number=step_number,
    )


# 选区策略：生成合理的选区矩形
selection_rect_strategy = st.tuples(
    st.integers(min_value=0, max_value=5000),   # x
    st.integers(min_value=0, max_value=5000),   # y
    st.integers(min_value=10, max_value=5000),  # width (至少 10)
    st.integers(min_value=10, max_value=5000),  # height (至少 10)
)

# ScreenshotState 策略
@st.composite
def screenshot_state_strategy(draw):
    """生成随机 ScreenshotState"""
    selection_rect = draw(selection_rect_strategy)
    annotations = draw(st.lists(annotation_data_strategy(), min_size=0, max_size=20))
    screen_index = draw(st.integers(min_value=0, max_value=10))
    
    return ScreenshotState(
        selection_rect=selection_rect,
        annotations=annotations,
        screen_index=screen_index,
    )


# ============================================================
# Property Tests - 属性测试
# ============================================================

class TestAnnotationDataProperties:
    """AnnotationData 属性测试"""
    
    @settings(max_examples=100)
    @given(annotation_data_strategy())
    def test_annotation_data_round_trip(self, annotation: AnnotationData):
        """
        Property 5: Annotation Data Integrity
        
        *For any* AnnotationData, serializing to dict then deserializing
        SHALL produce an equivalent AnnotationData with identical fields.
        
        **Validates: Requirements 1.3, 3.2**
        
        Feature: screenshot-state-restore, Property 5: Annotation Data Integrity
        """
        # 序列化
        data = annotation.to_dict()
        
        # 反序列化
        restored = AnnotationData.from_dict(data)
        
        # 验证等价性
        assert restored.tool == annotation.tool
        assert restored.color == annotation.color
        assert restored.width == annotation.width
        assert restored.points == annotation.points
        assert restored.text == annotation.text
        assert restored.step_number == annotation.step_number
    
    @settings(max_examples=100)
    @given(annotation_data_strategy())
    def test_annotation_data_json_round_trip(self, annotation: AnnotationData):
        """
        Property 5 (Extended): JSON Round-Trip
        
        *For any* AnnotationData, serializing to JSON string then deserializing
        SHALL produce an equivalent AnnotationData.
        
        **Validates: Requirements 3.2**
        
        Feature: screenshot-state-restore, Property 5: Annotation Data Integrity
        """
        # 序列化为 JSON 字符串
        json_str = json.dumps(annotation.to_dict(), ensure_ascii=False)
        
        # 从 JSON 字符串反序列化
        data = json.loads(json_str)
        restored = AnnotationData.from_dict(data)
        
        # 验证等价性
        assert restored.tool == annotation.tool
        assert restored.color == annotation.color
        assert restored.width == annotation.width
        assert restored.points == annotation.points
        assert restored.text == annotation.text
        assert restored.step_number == annotation.step_number


class TestScreenshotStateProperties:
    """ScreenshotState 属性测试"""
    
    @settings(max_examples=100)
    @given(screenshot_state_strategy())
    def test_screenshot_state_round_trip(self, state: ScreenshotState):
        """
        Property 1: State Serialization Round-Trip
        
        *For any* valid ScreenshotState object with any combination of annotations,
        serializing to dict then deserializing SHALL produce an equivalent state
        object with identical selection_rect, annotations, and metadata.
        
        **Validates: Requirements 3.4**
        
        Feature: screenshot-state-restore, Property 1: State Serialization Round-Trip
        """
        # 序列化
        data = state.to_dict()
        
        # 反序列化
        restored = ScreenshotState.from_dict(data)
        
        # 验证选区
        assert restored.selection_rect == state.selection_rect
        
        # 验证屏幕索引
        assert restored.screen_index == state.screen_index
        
        # 验证标注数量
        assert len(restored.annotations) == len(state.annotations)
        
        # 验证每个标注
        for orig, rest in zip(state.annotations, restored.annotations):
            assert rest.tool == orig.tool
            assert rest.color == orig.color
            assert rest.width == orig.width
            assert rest.points == orig.points
            assert rest.text == orig.text
            assert rest.step_number == orig.step_number
    
    @settings(max_examples=100)
    @given(screenshot_state_strategy())
    def test_screenshot_state_json_round_trip(self, state: ScreenshotState):
        """
        Property 1 (Extended): JSON Round-Trip
        
        *For any* valid ScreenshotState, serializing to JSON string then deserializing
        SHALL produce an equivalent state.
        
        **Validates: Requirements 3.4**
        
        Feature: screenshot-state-restore, Property 1: State Serialization Round-Trip
        """
        # 序列化为 JSON 字符串
        json_str = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        
        # 从 JSON 字符串反序列化
        data = json.loads(json_str)
        restored = ScreenshotState.from_dict(data)
        
        # 验证选区
        assert restored.selection_rect == state.selection_rect
        
        # 验证标注数量和内容
        assert len(restored.annotations) == len(state.annotations)
        for orig, rest in zip(state.annotations, restored.annotations):
            assert rest.tool == orig.tool
            assert rest.color == orig.color
            assert rest.width == orig.width
            assert rest.points == orig.points


# ============================================================
# Unit Tests - 单元测试
# ============================================================

class TestAnnotationDataUnit:
    """AnnotationData 单元测试"""
    
    def test_create_rect_annotation(self):
        """测试创建矩形标注"""
        annotation = AnnotationData(
            tool="rect",
            color="#FF0000",
            width=2,
            points=[(100, 100), (200, 200)],
        )
        assert annotation.tool == "rect"
        assert annotation.color == "#FF0000"
        assert annotation.width == 2
        assert annotation.points == [(100, 100), (200, 200)]
        assert annotation.text == ""
        assert annotation.step_number == 0
    
    def test_create_text_annotation(self):
        """测试创建文字标注"""
        annotation = AnnotationData(
            tool="text",
            color="#0000FF",
            width=16,
            points=[(150, 150)],
            text="测试文字",
        )
        assert annotation.tool == "text"
        assert annotation.text == "测试文字"
    
    def test_create_step_annotation(self):
        """测试创建步骤编号标注"""
        annotation = AnnotationData(
            tool="step",
            color="#FF0000",
            width=30,
            points=[(200, 200)],
            step_number=5,
        )
        assert annotation.tool == "step"
        assert annotation.step_number == 5
    
    def test_invalid_tool_raises_error(self):
        """测试无效工具类型抛出异常"""
        with pytest.raises(ValueError):
            AnnotationData(
                tool="invalid_tool",
                color="#FF0000",
                width=2,
                points=[(100, 100)],
            )
    
    def test_empty_points_list(self):
        """测试空点列表"""
        annotation = AnnotationData(
            tool="pen",
            color="#FF0000",
            width=2,
            points=[],
        )
        assert annotation.points == []
    
    def test_special_characters_in_text(self):
        """测试文字中的特殊字符"""
        special_text = "Hello 你好 🎉 <>&\"'"
        annotation = AnnotationData(
            tool="text",
            color="#FF0000",
            width=16,
            points=[(100, 100)],
            text=special_text,
        )
        
        # 序列化往返
        data = annotation.to_dict()
        restored = AnnotationData.from_dict(data)
        
        assert restored.text == special_text


class TestScreenshotStateUnit:
    """ScreenshotState 单元测试"""
    
    def test_create_empty_state(self):
        """测试创建空状态（无标注）"""
        state = ScreenshotState(
            selection_rect=(100, 100, 800, 600),
        )
        assert state.selection_rect == (100, 100, 800, 600)
        assert state.annotations == []
        assert state.screen_index == 0
    
    def test_create_state_with_annotations(self):
        """测试创建带标注的状态"""
        annotations = [
            AnnotationData(tool="rect", color="#FF0000", width=2, points=[(0, 0), (100, 100)]),
            AnnotationData(tool="text", color="#0000FF", width=16, points=[(50, 50)], text="Test"),
        ]
        state = ScreenshotState(
            selection_rect=(0, 0, 1920, 1080),
            annotations=annotations,
            screen_index=1,
        )
        assert len(state.annotations) == 2
        assert state.screen_index == 1
    
    def test_invalid_selection_rect_raises_error(self):
        """测试无效选区抛出异常"""
        with pytest.raises(ValueError):
            ScreenshotState(
                selection_rect=(100, 100, 800),  # 只有 3 个值
            )
    
    def test_timestamp_auto_generated(self):
        """测试时间戳自动生成"""
        state = ScreenshotState(
            selection_rect=(0, 0, 100, 100),
        )
        assert state.timestamp != ""
        # 验证是 ISO 格式
        from datetime import datetime
        datetime.fromisoformat(state.timestamp)


# ============================================================
# ScreenshotStateManager Property Tests
# ============================================================

class TestScreenshotStateManagerProperties:
    """ScreenshotStateManager 属性测试"""
    pass


# 独立的属性测试函数（避免 hypothesis 与 pytest fixtures 冲突）
@settings(max_examples=100)
@given(screenshot_state_strategy())
def test_state_save_completeness(state: ScreenshotState):
    """
    Property 2: State Save Completeness
    
    *For any* screenshot state containing an image and annotations,
    after saving, the state directory SHALL contain both a valid JSON file
    with all annotation data and a valid PNG image file.
    
    **Validates: Requirements 1.3, 3.1, 3.2**
    
    Feature: screenshot-state-restore, Property 2: State Save Completeness
    """
    import screenshot_tool.core.screenshot_state_manager as ssm
    
    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_func = ssm.get_user_data_dir
        ssm.get_user_data_dir = lambda: tmp_dir
        
        try:
            # 创建管理器和测试图像
            manager = ScreenshotStateManager()
            from PySide6.QtGui import QImage, QColor
            sample_image = QImage(100, 100, QImage.Format.Format_RGB32)
            sample_image.fill(QColor(255, 0, 0))
            
            # 保存状态（立即保存）
            result = manager.save_state(state, sample_image, immediate=True)
            assert result is True
            
            # 验证文件存在
            assert os.path.exists(manager.state_file_path)
            assert os.path.exists(manager.image_file_path)
            
            # 验证 JSON 文件有效
            with open(manager.state_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证必需字段
            assert "selection_rect" in data
            assert "annotations" in data
            assert data["selection_rect"] == list(state.selection_rect)
            assert len(data["annotations"]) == len(state.annotations)
            
            # 验证每个标注的字段
            for i, ann_data in enumerate(data["annotations"]):
                orig = state.annotations[i]
                assert ann_data["tool"] == orig.tool
                assert ann_data["color"] == orig.color
                assert ann_data["width"] == orig.width
                # JSON 序列化后 points 变成列表的列表，需要转换比较
                assert [list(p) for p in orig.points] == ann_data["points"]
            
            # 验证图像文件有效
            loaded_image = QImage(manager.image_file_path)
            assert not loaded_image.isNull()
            assert loaded_image.width() == sample_image.width()
            assert loaded_image.height() == sample_image.height()
        finally:
            ssm.get_user_data_dir = original_func


@settings(max_examples=100)
@given(screenshot_state_strategy())
def test_state_restore_completeness(state: ScreenshotState):
    """
    Property 3: State Restore Completeness
    
    *For any* saved screenshot state, loading the state SHALL return
    a ScreenshotState object with selection_rect, annotations, and image
    that are equivalent to the original saved state.
    
    **Validates: Requirements 2.1, 2.2, 2.3**
    
    Feature: screenshot-state-restore, Property 3: State Restore Completeness
    """
    import screenshot_tool.core.screenshot_state_manager as ssm
    
    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_func = ssm.get_user_data_dir
        ssm.get_user_data_dir = lambda: tmp_dir
        
        try:
            # 创建管理器和测试图像
            manager = ScreenshotStateManager()
            from PySide6.QtGui import QImage, QColor
            sample_image = QImage(100, 100, QImage.Format.Format_RGB32)
            sample_image.fill(QColor(255, 0, 0))
            
            # 保存状态
            manager.save_state(state, sample_image, immediate=True)
            
            # 加载状态
            result = manager.load_state()
            assert result is not None
            
            loaded_state, loaded_image = result
            
            # 验证选区
            assert loaded_state.selection_rect == state.selection_rect
            
            # 验证屏幕索引
            assert loaded_state.screen_index == state.screen_index
            
            # 验证标注数量
            assert len(loaded_state.annotations) == len(state.annotations)
            
            # 验证每个标注
            for orig, loaded in zip(state.annotations, loaded_state.annotations):
                assert loaded.tool == orig.tool
                assert loaded.color == orig.color
                assert loaded.width == orig.width
                assert loaded.points == orig.points
                assert loaded.text == orig.text
                assert loaded.step_number == orig.step_number
            
            # 验证图像尺寸
            assert loaded_image.width() == sample_image.width()
            assert loaded_image.height() == sample_image.height()
        finally:
            ssm.get_user_data_dir = original_func


@settings(max_examples=50)
@given(st.lists(screenshot_state_strategy(), min_size=2, max_size=5))
def test_single_state_policy(states: List[ScreenshotState]):
    """
    Property 4: Single State Policy
    
    *For any* sequence of state saves, the states directory SHALL contain
    exactly one state (one JSON file and one image file), with the most
    recent state overwriting any previous state.
    
    **Validates: Requirements 4.2, 4.3**
    
    Feature: screenshot-state-restore, Property 4: Single State Policy
    """
    import screenshot_tool.core.screenshot_state_manager as ssm
    
    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_func = ssm.get_user_data_dir
        ssm.get_user_data_dir = lambda: tmp_dir
        
        try:
            # 创建管理器和测试图像
            manager = ScreenshotStateManager()
            from PySide6.QtGui import QImage, QColor
            sample_image = QImage(100, 100, QImage.Format.Format_RGB32)
            sample_image.fill(QColor(255, 0, 0))
            
            # 连续保存多个状态
            for state in states:
                manager.save_state(state, sample_image, immediate=True)
            
            # 验证目录中只有一个状态文件
            states_dir = manager._states_dir
            files = os.listdir(states_dir)
            
            # 应该只有 state.json 和 screenshot.png
            assert len(files) == 2
            assert ScreenshotStateManager.STATE_FILE in files
            assert ScreenshotStateManager.IMAGE_FILE in files
            
            # 验证加载的是最后一个状态
            result = manager.load_state()
            assert result is not None
            
            loaded_state, _ = result
            last_state = states[-1]
            
            assert loaded_state.selection_rect == last_state.selection_rect
            assert len(loaded_state.annotations) == len(last_state.annotations)
        finally:
            ssm.get_user_data_dir = original_func


class TestScreenshotStateManagerUnit:
    """ScreenshotStateManager 单元测试"""
    
    @pytest.fixture
    def temp_data_dir(self, monkeypatch, tmp_path):
        """使用临时目录作为数据目录"""
        monkeypatch.setattr(
            'screenshot_tool.core.screenshot_state_manager.get_user_data_dir',
            lambda: str(tmp_path)
        )
        return tmp_path
    
    @pytest.fixture
    def manager(self, temp_data_dir):
        """创建使用临时目录的管理器"""
        return ScreenshotStateManager()
    
    @pytest.fixture
    def sample_image(self):
        """创建测试用图像"""
        from PySide6.QtGui import QImage, QColor
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(QColor(255, 0, 0))
        return image
    
    def test_has_saved_state_false_initially(self, manager):
        """测试初始状态下没有保存的状态"""
        assert manager.has_saved_state() is False
    
    def test_has_saved_state_true_after_save(self, manager, sample_image):
        """测试保存后有保存的状态"""
        state = ScreenshotState(selection_rect=(0, 0, 100, 100))
        manager.save_state(state, sample_image, immediate=True)
        assert manager.has_saved_state() is True
    
    def test_clear_state(self, manager, sample_image):
        """测试清除状态"""
        state = ScreenshotState(selection_rect=(0, 0, 100, 100))
        manager.save_state(state, sample_image, immediate=True)
        assert manager.has_saved_state() is True
        
        manager.clear_state()
        assert manager.has_saved_state() is False
    
    def test_load_state_returns_none_when_no_state(self, manager):
        """测试没有状态时加载返回 None"""
        result = manager.load_state()
        assert result is None
    
    def test_verify_state_integrity_false_when_no_state(self, manager):
        """测试没有状态时验证返回 False"""
        assert manager.verify_state_integrity() is False
    
    def test_verify_state_integrity_true_after_save(self, manager, sample_image):
        """测试保存后验证返回 True"""
        state = ScreenshotState(selection_rect=(0, 0, 100, 100))
        manager.save_state(state, sample_image, immediate=True)
        assert manager.verify_state_integrity() is True
    
    def test_corrupted_json_handled(self, manager, sample_image, temp_data_dir):
        """测试损坏的 JSON 文件被正确处理"""
        # 先保存一个有效状态
        state = ScreenshotState(selection_rect=(0, 0, 100, 100))
        manager.save_state(state, sample_image, immediate=True)
        
        # 损坏 JSON 文件
        with open(manager.state_file_path, 'w') as f:
            f.write("invalid json {{{")
        
        # 加载应该返回 None 并清理文件
        result = manager.load_state()
        assert result is None
        assert not os.path.exists(manager.state_file_path)
    
    def test_missing_image_handled(self, manager, sample_image, temp_data_dir):
        """测试缺失图像文件被正确处理"""
        # 先保存一个有效状态
        state = ScreenshotState(selection_rect=(0, 0, 100, 100))
        manager.save_state(state, sample_image, immediate=True)
        
        # 删除图像文件
        os.remove(manager.image_file_path)
        
        # 加载应该返回 None
        result = manager.load_state()
        assert result is None


# ============================================================
# DrawItem Conversion Tests
# ============================================================

class TestDrawItemConversion:
    """DrawItem 与 AnnotationData 转换测试"""
    
    def test_rect_conversion(self):
        """测试矩形标注转换"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        
        original = DrawItem(
            tool=DrawTool.RECT,
            color=QColor("#FF0000"),
            width=2,
            points=[QPoint(100, 100), QPoint(200, 200)],
        )
        
        # 转换为 AnnotationData
        annotation = original.to_annotation_data()
        assert annotation.tool == "rect"
        assert annotation.color == "#ff0000"
        assert annotation.width == 2
        assert annotation.points == [(100, 100), (200, 200)]
        
        # 转换回 DrawItem
        restored = DrawItem.from_annotation_data(annotation)
        assert restored.tool == DrawTool.RECT
        assert restored.color.name() == "#ff0000"
        assert restored.width == 2
        assert len(restored.points) == 2
        assert restored.points[0].x() == 100
        assert restored.points[0].y() == 100
    
    def test_text_conversion(self):
        """测试文字标注转换"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        
        original = DrawItem(
            tool=DrawTool.TEXT,
            color=QColor("#0000FF"),
            width=16,
            points=[QPoint(150, 150)],
            text="测试文字 🎉",
        )
        
        # 转换为 AnnotationData
        annotation = original.to_annotation_data()
        assert annotation.tool == "text"
        assert annotation.text == "测试文字 🎉"
        
        # 转换回 DrawItem
        restored = DrawItem.from_annotation_data(annotation)
        assert restored.tool == DrawTool.TEXT
        assert restored.text == "测试文字 🎉"
    
    def test_step_conversion(self):
        """测试步骤编号转换"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        
        original = DrawItem(
            tool=DrawTool.STEP,
            color=QColor("#FF0000"),
            width=30,
            points=[QPoint(200, 200)],
            step_number=5,
        )
        
        # 转换为 AnnotationData
        annotation = original.to_annotation_data()
        assert annotation.tool == "step"
        assert annotation.step_number == 5
        
        # 转换回 DrawItem
        restored = DrawItem.from_annotation_data(annotation)
        assert restored.tool == DrawTool.STEP
        assert restored.step_number == 5
    
    def test_pen_conversion(self):
        """测试画笔标注转换（多点）"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        
        points = [QPoint(i * 10, i * 10) for i in range(20)]
        original = DrawItem(
            tool=DrawTool.PEN,
            color=QColor("#00FF00"),
            width=3,
            points=points,
        )
        
        # 转换为 AnnotationData
        annotation = original.to_annotation_data()
        assert annotation.tool == "pen"
        assert len(annotation.points) == 20
        
        # 转换回 DrawItem
        restored = DrawItem.from_annotation_data(annotation)
        assert restored.tool == DrawTool.PEN
        assert len(restored.points) == 20
        for i, p in enumerate(restored.points):
            assert p.x() == i * 10
            assert p.y() == i * 10
    
    def test_empty_points_conversion(self):
        """测试空点列表转换"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtGui import QColor
        
        original = DrawItem(
            tool=DrawTool.RECT,
            color=QColor("#FF0000"),
            width=2,
            points=[],
        )
        
        annotation = original.to_annotation_data()
        assert annotation.points == []
        
        restored = DrawItem.from_annotation_data(annotation)
        assert restored.points == []
    
    def test_all_tool_types_conversion(self):
        """测试所有工具类型的转换"""
        from screenshot_tool.ui.overlay_screenshot import DrawItem, DrawTool
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        
        tools = [
            DrawTool.RECT, DrawTool.ELLIPSE, DrawTool.ARROW,
            DrawTool.LINE, DrawTool.PEN, DrawTool.MARKER,
            DrawTool.TEXT, DrawTool.MOSAIC, DrawTool.STEP,
        ]
        
        for tool in tools:
            original = DrawItem(
                tool=tool,
                color=QColor("#FF0000"),
                width=2,
                points=[QPoint(0, 0), QPoint(100, 100)],
                text="test" if tool == DrawTool.TEXT else "",
                step_number=1 if tool == DrawTool.STEP else 0,
            )
            
            annotation = original.to_annotation_data()
            restored = DrawItem.from_annotation_data(annotation)
            
            assert restored.tool == original.tool, f"Tool {tool} conversion failed"
