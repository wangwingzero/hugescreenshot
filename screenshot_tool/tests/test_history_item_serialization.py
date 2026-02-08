# -*- coding: utf-8 -*-
"""
HistoryItem 序列化属性测试

Feature: screenshot-state-restore
Property 1: Screenshot History Item Round-Trip
Validates: Requirements 1.4
"""

import pytest
from datetime import datetime
from hypothesis import given, settings, strategies as st

from screenshot_tool.core.clipboard_history_manager import HistoryItem, ContentType


# ========== Hypothesis Strategies ==========

@st.composite
def annotation_strategy(draw):
    """生成随机标注数据"""
    tool = draw(st.sampled_from([
        "rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"
    ]))
    
    # 生成颜色（hex 格式）
    r = draw(st.integers(min_value=0, max_value=255))
    g = draw(st.integers(min_value=0, max_value=255))
    b = draw(st.integers(min_value=0, max_value=255))
    color = f"#{r:02x}{g:02x}{b:02x}"
    
    # 生成线条粗细
    width = draw(st.integers(min_value=1, max_value=100))
    
    # 生成点列表
    num_points = draw(st.integers(min_value=1, max_value=50))
    points = [
        [draw(st.integers(min_value=0, max_value=4000)),
         draw(st.integers(min_value=0, max_value=4000))]
        for _ in range(num_points)
    ]
    
    # 生成文字（仅 text 工具）
    text = draw(st.text(min_size=0, max_size=100)) if tool == "text" else ""
    
    # 生成步骤编号（仅 step 工具）
    step_number = draw(st.integers(min_value=1, max_value=99)) if tool == "step" else 0
    
    return {
        "tool": tool,
        "color": color,
        "width": width,
        "points": points,
        "text": text,
        "step_number": step_number,
    }


@st.composite
def history_item_strategy(draw):
    """生成随机 HistoryItem（带标注）"""
    item_id = draw(st.uuids()).hex
    content_type = draw(st.sampled_from([ContentType.IMAGE, ContentType.TEXT]))
    
    # 根据内容类型生成相应字段
    if content_type == ContentType.IMAGE:
        text_content = None
        image_path = f"clipboard_images/{draw(st.uuids()).hex}.png"
        preview_text = "[截图]"
    else:
        text_content = draw(st.text(min_size=1, max_size=500))
        image_path = None
        preview_text = text_content[:50] if len(text_content) > 50 else text_content
    
    # 生成时间戳
    timestamp = datetime(
        year=draw(st.integers(min_value=2020, max_value=2030)),
        month=draw(st.integers(min_value=1, max_value=12)),
        day=draw(st.integers(min_value=1, max_value=28)),
        hour=draw(st.integers(min_value=0, max_value=23)),
        minute=draw(st.integers(min_value=0, max_value=59)),
        second=draw(st.integers(min_value=0, max_value=59)),
    )
    
    is_pinned = draw(st.booleans())
    
    # 生成标注数据（仅图片类型）
    if content_type == ContentType.IMAGE:
        has_annotations = draw(st.booleans())
        if has_annotations:
            num_annotations = draw(st.integers(min_value=1, max_value=10))
            annotations = [draw(annotation_strategy()) for _ in range(num_annotations)]
        else:
            annotations = None
        
        # 生成选区
        has_selection = draw(st.booleans())
        if has_selection:
            x = draw(st.integers(min_value=0, max_value=3000))
            y = draw(st.integers(min_value=0, max_value=2000))
            w = draw(st.integers(min_value=10, max_value=1000))
            h = draw(st.integers(min_value=10, max_value=1000))
            selection_rect = (x, y, w, h)
        else:
            selection_rect = None
    else:
        annotations = None
        selection_rect = None
    
    return HistoryItem(
        id=item_id,
        content_type=content_type,
        text_content=text_content,
        image_path=image_path,
        preview_text=preview_text,
        timestamp=timestamp,
        is_pinned=is_pinned,
        annotations=annotations,
        selection_rect=selection_rect,
    )


# ========== Property Tests ==========

@settings(max_examples=100)
@given(item=history_item_strategy())
def test_history_item_round_trip(item: HistoryItem):
    """Property 1: Screenshot History Item Round-Trip
    
    For any valid HistoryItem with annotations and selection_rect,
    serializing to JSON then deserializing SHALL produce an equivalent
    HistoryItem with identical id, content_type, image_path, annotations
    (including all fields), and selection_rect.
    
    Feature: screenshot-state-restore
    Validates: Requirements 1.4
    """
    # 序列化
    data = item.to_dict()
    
    # 反序列化
    restored = HistoryItem.from_dict(data)
    
    # 验证基本字段
    assert restored.id == item.id
    assert restored.content_type == item.content_type
    assert restored.text_content == item.text_content
    assert restored.image_path == item.image_path
    assert restored.preview_text == item.preview_text
    assert restored.timestamp == item.timestamp
    assert restored.is_pinned == item.is_pinned
    
    # 验证标注数据
    if item.annotations is None:
        assert restored.annotations is None
    else:
        assert restored.annotations is not None
        assert len(restored.annotations) == len(item.annotations)
        for orig, rest in zip(item.annotations, restored.annotations):
            assert rest["tool"] == orig["tool"]
            assert rest["color"] == orig["color"]
            assert rest["width"] == orig["width"]
            assert rest["points"] == orig["points"]
            assert rest["text"] == orig["text"]
            assert rest["step_number"] == orig["step_number"]
    
    # 验证选区
    if item.selection_rect is None:
        assert restored.selection_rect is None
    else:
        assert restored.selection_rect is not None
        assert tuple(restored.selection_rect) == tuple(item.selection_rect)


@settings(max_examples=100)
@given(item=history_item_strategy())
def test_has_annotations_consistency(item: HistoryItem):
    """验证 has_annotations() 方法的一致性
    
    Feature: screenshot-state-restore
    """
    if item.annotations is None or len(item.annotations) == 0:
        assert item.has_annotations() is False
        assert item.get_annotation_count() == 0
    else:
        assert item.has_annotations() is True
        assert item.get_annotation_count() == len(item.annotations)


# ========== Unit Tests ==========

def test_history_item_without_annotations():
    """测试不带标注的 HistoryItem 序列化"""
    item = HistoryItem(
        id="test-id-123",
        content_type=ContentType.IMAGE,
        text_content=None,
        image_path="clipboard_images/test.png",
        preview_text="[图片]",
        timestamp=datetime(2026, 1, 15, 10, 30, 0),
        is_pinned=False,
        annotations=None,
        selection_rect=None,
    )
    
    data = item.to_dict()
    restored = HistoryItem.from_dict(data)
    
    assert restored.id == item.id
    assert restored.annotations is None
    assert restored.selection_rect is None
    assert restored.has_annotations() is False


def test_history_item_with_annotations():
    """测试带标注的 HistoryItem 序列化"""
    annotations = [
        {
            "tool": "rect",
            "color": "#FF0000",
            "width": 2,
            "points": [[100, 100], [300, 200]],
            "text": "",
            "step_number": 0,
        },
        {
            "tool": "text",
            "color": "#00FF00",
            "width": 16,
            "points": [[150, 150]],
            "text": "测试文字",
            "step_number": 0,
        },
    ]
    
    item = HistoryItem(
        id="test-id-456",
        content_type=ContentType.IMAGE,
        text_content=None,
        image_path="clipboard_images/test2.png",
        preview_text="[截图] 2个标注",
        timestamp=datetime(2026, 1, 15, 11, 0, 0),
        is_pinned=True,
        annotations=annotations,
        selection_rect=(0, 0, 800, 600),
    )
    
    data = item.to_dict()
    restored = HistoryItem.from_dict(data)
    
    assert restored.id == item.id
    assert restored.has_annotations() is True
    assert restored.get_annotation_count() == 2
    assert restored.annotations[0]["tool"] == "rect"
    assert restored.annotations[1]["text"] == "测试文字"
    assert restored.selection_rect == (0, 0, 800, 600)


def test_backward_compatibility_version_1():
    """测试向后兼容：加载 version 1 格式的数据"""
    # version 1 格式没有 annotations 和 selection_rect 字段
    data = {
        "id": "old-item-id",
        "content_type": "image",
        "text_content": None,
        "image_path": "clipboard_images/old.png",
        "preview_text": "[图片]",
        "timestamp": "2025-12-01T10:00:00",
        "is_pinned": False,
    }
    
    item = HistoryItem.from_dict(data)
    
    assert item.id == "old-item-id"
    assert item.annotations is None
    assert item.selection_rect is None
    assert item.has_annotations() is False


def test_empty_annotations_list():
    """测试空标注列表"""
    item = HistoryItem(
        id="test-empty",
        content_type=ContentType.IMAGE,
        text_content=None,
        image_path="clipboard_images/empty.png",
        preview_text="[图片]",
        timestamp=datetime(2026, 1, 15, 12, 0, 0),
        is_pinned=False,
        annotations=[],  # 空列表
        selection_rect=(100, 100, 400, 300),
    )
    
    assert item.has_annotations() is False
    assert item.get_annotation_count() == 0
    
    data = item.to_dict()
    restored = HistoryItem.from_dict(data)
    
    assert restored.annotations == []
    assert restored.has_annotations() is False
