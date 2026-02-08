# -*- coding: utf-8 -*-
"""
标注恢复保真度属性测试

Feature: screenshot-state-restore
Property 4: Annotation Restoration Fidelity
Validates: Requirements 2.2, 2.3
"""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from screenshot_tool.core.screenshot_state_manager import AnnotationData


# ========== Hypothesis Strategies ==========

@st.composite
def annotation_data_strategy(draw):
    """生成随机 AnnotationData 对象"""
    tool = draw(st.sampled_from([
        "rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"
    ]))
    
    r = draw(st.integers(min_value=0, max_value=255))
    g = draw(st.integers(min_value=0, max_value=255))
    b = draw(st.integers(min_value=0, max_value=255))
    color = f"#{r:02x}{g:02x}{b:02x}"
    
    width = draw(st.integers(min_value=1, max_value=100))
    
    num_points = draw(st.integers(min_value=1, max_value=30))
    points = [
        (draw(st.integers(min_value=0, max_value=2000)),
         draw(st.integers(min_value=0, max_value=2000)))
        for _ in range(num_points)
    ]
    
    text = draw(st.text(min_size=0, max_size=100)) if tool == "text" else ""
    step_number = draw(st.integers(min_value=1, max_value=99)) if tool == "step" else 0
    
    return AnnotationData(
        tool=tool,
        color=color,
        width=width,
        points=points,
        text=text,
        step_number=step_number,
    )


# ========== Property Tests ==========

@settings(max_examples=100)
@given(annotation=annotation_data_strategy())
def test_annotation_round_trip(annotation: AnnotationData):
    """Property 2: Annotation Round-Trip
    
    For any valid AnnotationData object with any tool type,
    serializing to dict then deserializing SHALL produce an equivalent
    AnnotationData with identical tool, color, width, points, text, and step_number.
    
    Feature: screenshot-state-restore
    Validates: Requirements 5.5
    """
    # 序列化
    data = annotation.to_dict()
    
    # 反序列化
    restored = AnnotationData.from_dict(data)
    
    # 验证所有字段
    assert restored.tool == annotation.tool, f"工具类型不匹配: {restored.tool} != {annotation.tool}"
    assert restored.color == annotation.color, f"颜色不匹配: {restored.color} != {annotation.color}"
    assert restored.width == annotation.width, f"线条粗细不匹配: {restored.width} != {annotation.width}"
    assert restored.text == annotation.text, f"文字不匹配: {restored.text} != {annotation.text}"
    assert restored.step_number == annotation.step_number, f"步骤编号不匹配: {restored.step_number} != {annotation.step_number}"
    
    # 验证点列表
    assert len(restored.points) == len(annotation.points), f"点数量不匹配: {len(restored.points)} != {len(annotation.points)}"
    for i, (orig_pt, rest_pt) in enumerate(zip(annotation.points, restored.points)):
        assert rest_pt == orig_pt, f"点 {i} 不匹配: {rest_pt} != {orig_pt}"


@settings(max_examples=100)
@given(annotations=st.lists(annotation_data_strategy(), min_size=1, max_size=10))
def test_annotation_list_restoration_fidelity(annotations):
    """Property 4: Annotation Restoration Fidelity
    
    For any history item with annotations, when restored to the screenshot editor,
    all annotation objects SHALL have their original tool type, color, width, points,
    text, and step_number exactly matching the saved values.
    
    Feature: screenshot-state-restore
    Validates: Requirements 2.2, 2.3
    """
    # 模拟保存过程：转换为 dict 列表
    saved_data = [ann.to_dict() for ann in annotations]
    
    # 模拟恢复过程：从 dict 列表恢复
    restored_annotations = [AnnotationData.from_dict(d) for d in saved_data]
    
    # 验证数量
    assert len(restored_annotations) == len(annotations), "标注数量应该一致"
    
    # 验证每个标注的所有属性
    for orig, restored in zip(annotations, restored_annotations):
        assert restored.tool == orig.tool, f"工具类型不匹配"
        assert restored.color == orig.color, f"颜色不匹配"
        assert restored.width == orig.width, f"线条粗细不匹配"
        assert restored.text == orig.text, f"文字不匹配"
        assert restored.step_number == orig.step_number, f"步骤编号不匹配"
        assert len(restored.points) == len(orig.points), f"点数量不匹配"
        
        for i, (orig_pt, rest_pt) in enumerate(zip(orig.points, restored.points)):
            assert rest_pt == orig_pt, f"点 {i} 不匹配"


# ========== Unit Tests ==========

def test_pen_stroke_points_preserved():
    """测试画笔路径的所有点都被保留"""
    points = [(10, 10), (20, 30), (40, 50), (60, 40), (80, 60), (100, 80)]
    annotation = AnnotationData(
        tool="pen",
        color="#FF0000",
        width=3,
        points=points,
        text="",
        step_number=0,
    )
    
    data = annotation.to_dict()
    restored = AnnotationData.from_dict(data)
    
    assert len(restored.points) == len(points)
    for orig, rest in zip(points, restored.points):
        assert rest == orig


def test_marker_stroke_points_preserved():
    """测试马克笔路径的所有点都被保留"""
    points = [(50, 100), (100, 100), (150, 100), (200, 100)]
    annotation = AnnotationData(
        tool="marker",
        color="#FFFF00",
        width=10,
        points=points,
        text="",
        step_number=0,
    )
    
    data = annotation.to_dict()
    restored = AnnotationData.from_dict(data)
    
    assert len(restored.points) == len(points)
    for orig, rest in zip(points, restored.points):
        assert rest == orig


def test_text_content_preserved():
    """测试文字内容和字体大小被保留"""
    annotation = AnnotationData(
        tool="text",
        color="#000000",
        width=24,  # 字体大小
        points=[(100, 200)],
        text="测试文字内容 Test 123 !@#",
        step_number=0,
    )
    
    data = annotation.to_dict()
    restored = AnnotationData.from_dict(data)
    
    assert restored.text == annotation.text
    assert restored.width == annotation.width


def test_step_number_preserved():
    """测试步骤编号被保留"""
    annotation = AnnotationData(
        tool="step",
        color="#FF0000",
        width=30,
        points=[(150, 150)],
        text="",
        step_number=42,
    )
    
    data = annotation.to_dict()
    restored = AnnotationData.from_dict(data)
    
    assert restored.step_number == 42


def test_all_annotation_types_round_trip():
    """测试所有标注类型的往返序列化"""
    annotations = [
        AnnotationData(tool="rect", color="#FF0000", width=2, points=[(10, 10), (100, 100)], text="", step_number=0),
        AnnotationData(tool="ellipse", color="#00FF00", width=3, points=[(20, 20), (80, 80)], text="", step_number=0),
        AnnotationData(tool="arrow", color="#0000FF", width=2, points=[(0, 0), (50, 50)], text="", step_number=0),
        AnnotationData(tool="line", color="#FFFF00", width=1, points=[(10, 90), (90, 10)], text="", step_number=0),
        AnnotationData(tool="pen", color="#FF00FF", width=2, points=[(10, 10), (20, 30), (40, 20)], text="", step_number=0),
        AnnotationData(tool="marker", color="#00FFFF", width=5, points=[(50, 50), (80, 50)], text="", step_number=0),
        AnnotationData(tool="text", color="#000000", width=16, points=[(30, 70)], text="测试", step_number=0),
        AnnotationData(tool="mosaic", color="#000000", width=10, points=[(60, 60), (90, 90)], text="", step_number=0),
        AnnotationData(tool="step", color="#FF0000", width=30, points=[(80, 20)], text="", step_number=5),
    ]
    
    for annotation in annotations:
        data = annotation.to_dict()
        restored = AnnotationData.from_dict(data)
        
        assert restored.tool == annotation.tool
        assert restored.color == annotation.color
        assert restored.width == annotation.width
        assert restored.points == annotation.points
        assert restored.text == annotation.text
        assert restored.step_number == annotation.step_number


def test_special_characters_in_text():
    """测试文字中的特殊字符被保留"""
    special_text = "特殊字符: \n\t\"'<>&中文日本語한국어"
    annotation = AnnotationData(
        tool="text",
        color="#000000",
        width=16,
        points=[(100, 100)],
        text=special_text,
        step_number=0,
    )
    
    data = annotation.to_dict()
    restored = AnnotationData.from_dict(data)
    
    assert restored.text == special_text

