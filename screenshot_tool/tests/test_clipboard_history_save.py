# -*- coding: utf-8 -*-
"""
ClipboardHistoryManager 保存完整性属性测试

Feature: screenshot-state-restore
Property 3: Save Completeness
Validates: Requirements 1.1, 1.2, 1.3
"""

import os
import tempfile
import shutil
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor

from screenshot_tool.core.clipboard_history_manager import (
    ClipboardHistoryManager, HistoryItem, ContentType
)


# 确保 QApplication 存在
@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_data_dir(monkeypatch):
    """创建临时数据目录"""
    temp_dir = tempfile.mkdtemp()
    
    # 模拟 get_clipboard_data_dir 返回临时目录
    monkeypatch.setattr(
        "screenshot_tool.core.clipboard_history_manager.get_clipboard_data_dir",
        lambda: temp_dir
    )
    
    yield temp_dir
    
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


def create_test_image(width: int = 100, height: int = 100) -> QImage:
    """创建测试图像"""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    # 填充随机颜色模式
    for y in range(height):
        for x in range(width):
            image.setPixelColor(x, y, QColor(x % 256, y % 256, (x + y) % 256))
    return image


# ========== Hypothesis Strategies ==========

@st.composite
def annotation_strategy(draw):
    """生成随机标注数据"""
    tool = draw(st.sampled_from([
        "rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"
    ]))
    
    r = draw(st.integers(min_value=0, max_value=255))
    g = draw(st.integers(min_value=0, max_value=255))
    b = draw(st.integers(min_value=0, max_value=255))
    color = f"#{r:02x}{g:02x}{b:02x}"
    
    width = draw(st.integers(min_value=1, max_value=50))
    
    num_points = draw(st.integers(min_value=2, max_value=20))
    points = [
        [draw(st.integers(min_value=0, max_value=500)),
         draw(st.integers(min_value=0, max_value=500))]
        for _ in range(num_points)
    ]
    
    text = draw(st.text(min_size=0, max_size=50)) if tool == "text" else ""
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
def selection_rect_strategy(draw):
    """生成随机选区"""
    x = draw(st.integers(min_value=0, max_value=500))
    y = draw(st.integers(min_value=0, max_value=500))
    w = draw(st.integers(min_value=10, max_value=200))
    h = draw(st.integers(min_value=10, max_value=200))
    return (x, y, w, h)


# ========== Property Tests ==========

@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    annotations=st.lists(annotation_strategy(), min_size=0, max_size=5),
    selection_rect=st.one_of(st.none(), selection_rect_strategy()),
)
def test_save_completeness(qapp, temp_data_dir, annotations, selection_rect):
    """Property 3: Save Completeness
    
    For any screenshot with image, selection_rect, and annotations of any
    supported type, after saving to history, the history item SHALL contain
    the original image file, the exact selection_rect, and all annotations
    with their complete data.
    
    Feature: screenshot-state-restore
    Validates: Requirements 1.1, 1.2, 1.3
    """
    # 创建管理器
    manager = ClipboardHistoryManager()
    
    # 创建测试图像
    image = create_test_image(200, 150)
    
    # 保存到历史
    item_id = manager.add_screenshot_item(
        image=image,
        annotations=annotations if annotations else None,
        selection_rect=selection_rect,
    )
    
    # 等待异步保存完成
    for worker in manager._save_workers:
        worker.wait()
    
    # 验证保存成功
    assert item_id, "保存应该返回有效的 item_id"
    
    # 获取保存的条目
    item = manager.get_item(item_id)
    assert item is not None, "应该能获取到保存的条目"
    
    # 验证图像文件存在
    assert item.image_path is not None, "应该有图像路径"
    image_full_path = os.path.join(temp_data_dir, item.image_path)
    assert os.path.exists(image_full_path), "图像文件应该存在"
    
    # 验证图像可以加载
    loaded_image = manager.get_screenshot_image(item_id)
    assert loaded_image is not None, "应该能加载图像"
    assert loaded_image.width() == image.width(), "图像宽度应该一致"
    assert loaded_image.height() == image.height(), "图像高度应该一致"
    
    # 验证选区
    saved_rect = manager.get_screenshot_selection_rect(item_id)
    if selection_rect is None:
        assert saved_rect is None, "选区应该为 None"
    else:
        assert saved_rect is not None, "选区不应该为 None"
        assert tuple(saved_rect) == tuple(selection_rect), "选区应该完全一致"
    
    # 验证标注数据
    saved_annotations = manager.get_screenshot_annotations(item_id)
    if not annotations:
        assert saved_annotations is None or len(saved_annotations) == 0, "标注应该为空"
    else:
        assert saved_annotations is not None, "标注不应该为 None"
        assert len(saved_annotations) == len(annotations), "标注数量应该一致"
        
        for orig, saved in zip(annotations, saved_annotations):
            assert saved["tool"] == orig["tool"], "工具类型应该一致"
            assert saved["color"] == orig["color"], "颜色应该一致"
            assert saved["width"] == orig["width"], "线条粗细应该一致"
            assert saved["points"] == orig["points"], "点列表应该一致"
            assert saved["text"] == orig["text"], "文字应该一致"
            assert saved["step_number"] == orig["step_number"], "步骤编号应该一致"


# ========== Unit Tests ==========

def test_save_screenshot_without_annotations(qapp, temp_data_dir):
    """测试保存不带标注的截图"""
    manager = ClipboardHistoryManager()
    image = create_test_image()
    
    item_id = manager.add_screenshot_item(
        image=image,
        annotations=None,
        selection_rect=(0, 0, 100, 100),
    )
    
    # 等待异步保存完成
    for worker in manager._save_workers:
        worker.wait()
    
    assert item_id
    item = manager.get_item(item_id)
    assert item is not None
    assert item.has_annotations() is False
    assert item.get_annotation_count() == 0


def test_save_screenshot_with_all_annotation_types(qapp, temp_data_dir):
    """测试保存包含所有标注类型的截图"""
    manager = ClipboardHistoryManager()
    image = create_test_image()
    
    annotations = [
        {"tool": "rect", "color": "#FF0000", "width": 2, "points": [[10, 10], [50, 50]], "text": "", "step_number": 0},
        {"tool": "ellipse", "color": "#00FF00", "width": 3, "points": [[20, 20], [60, 60]], "text": "", "step_number": 0},
        {"tool": "arrow", "color": "#0000FF", "width": 2, "points": [[0, 0], [100, 100]], "text": "", "step_number": 0},
        {"tool": "line", "color": "#FFFF00", "width": 1, "points": [[10, 90], [90, 10]], "text": "", "step_number": 0},
        {"tool": "pen", "color": "#FF00FF", "width": 2, "points": [[10, 10], [20, 30], [40, 20]], "text": "", "step_number": 0},
        {"tool": "marker", "color": "#00FFFF", "width": 5, "points": [[50, 50], [80, 50]], "text": "", "step_number": 0},
        {"tool": "text", "color": "#000000", "width": 16, "points": [[30, 70]], "text": "测试文字", "step_number": 0},
        {"tool": "mosaic", "color": "#000000", "width": 10, "points": [[60, 60], [90, 90]], "text": "", "step_number": 0},
        {"tool": "step", "color": "#FF0000", "width": 30, "points": [[80, 20]], "text": "", "step_number": 1},
    ]
    
    item_id = manager.add_screenshot_item(
        image=image,
        annotations=annotations,
        selection_rect=(0, 0, 100, 100),
    )
    
    # 等待异步保存完成
    for worker in manager._save_workers:
        worker.wait()
    
    assert item_id
    item = manager.get_item(item_id)
    assert item is not None
    assert item.has_annotations() is True
    assert item.get_annotation_count() == 9
    
    # 验证每种类型都保存了
    saved = manager.get_screenshot_annotations(item_id)
    tools = [a["tool"] for a in saved]
    assert "rect" in tools
    assert "ellipse" in tools
    assert "arrow" in tools
    assert "line" in tools
    assert "pen" in tools
    assert "marker" in tools
    assert "text" in tools
    assert "mosaic" in tools
    assert "step" in tools


def test_update_existing_screenshot(qapp, temp_data_dir):
    """测试更新现有截图条目"""
    manager = ClipboardHistoryManager()
    image = create_test_image()
    
    # 首次保存
    item_id = manager.add_screenshot_item(
        image=image,
        annotations=[{"tool": "rect", "color": "#FF0000", "width": 2, "points": [[10, 10], [50, 50]], "text": "", "step_number": 0}],
        selection_rect=(0, 0, 100, 100),
    )
    
    # 等待异步保存完成
    for worker in manager._save_workers:
        worker.wait()
    
    assert item_id
    assert manager.get_item(item_id).get_annotation_count() == 1
    
    # 更新标注
    new_annotations = [
        {"tool": "rect", "color": "#FF0000", "width": 2, "points": [[10, 10], [50, 50]], "text": "", "step_number": 0},
        {"tool": "text", "color": "#000000", "width": 16, "points": [[30, 70]], "text": "新增文字", "step_number": 0},
    ]
    
    success = manager.update_screenshot_annotations(item_id, new_annotations)
    assert success
    
    # 验证更新
    item = manager.get_item(item_id)
    assert item.get_annotation_count() == 2
    
    saved = manager.get_screenshot_annotations(item_id)
    assert saved[1]["text"] == "新增文字"

