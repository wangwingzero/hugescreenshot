# -*- coding: utf-8 -*-
"""
AnnotationRenderer 测试

Feature: screenshot-state-restore
Property 5: Rendered Image Contains Annotations
Validates: Requirements 3.3
"""

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QImage, QColor

from screenshot_tool.core.annotation_renderer import AnnotationRenderer


def create_test_image(width: int = 200, height: int = 200, color: QColor = None) -> QImage:
    """创建测试图像"""
    if color is None:
        color = QColor(255, 255, 255)  # 白色背景
    
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


def images_differ_in_region(img1: QImage, img2: QImage, region: QRect) -> bool:
    """检查两个图像在指定区域是否有差异"""
    region = region.intersected(img1.rect())
    region = region.intersected(img2.rect())
    
    if region.isEmpty():
        return False
    
    for y in range(region.top(), region.bottom()):
        for x in range(region.left(), region.right()):
            if img1.pixelColor(x, y) != img2.pixelColor(x, y):
                return True
    
    return False


# ========== Unit Tests ==========

def test_render_empty_annotations():
    """测试空标注列表"""
    original = create_test_image()
    rendered = AnnotationRenderer.render(original, [])
    
    assert rendered.size() == original.size()
    for y in range(original.height()):
        for x in range(original.width()):
            assert rendered.pixelColor(x, y) == original.pixelColor(x, y)


def test_render_rect():
    """测试矩形渲染"""
    original = create_test_image()
    annotation = {
        "tool": "rect",
        "color": "#FF0000",
        "width": 3,
        "points": [[20, 20], [80, 80]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    
    found_red = False
    for x in range(20, 80):
        color = rendered.pixelColor(x, 20)
        if color.red() > 200 and color.green() < 50 and color.blue() < 50:
            found_red = True
            break
    
    assert found_red, "Rectangle should have red pixels on top edge"


def test_render_ellipse():
    """测试椭圆渲染"""
    original = create_test_image()
    annotation = {
        "tool": "ellipse",
        "color": "#00FF00",
        "width": 3,
        "points": [[30, 30], [100, 80]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(30, 30, 70, 50)
    assert images_differ_in_region(original, rendered, region)


def test_render_line():
    """测试直线渲染"""
    original = create_test_image()
    annotation = {
        "tool": "line",
        "color": "#0000FF",
        "width": 3,
        "points": [[10, 10], [100, 100]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(10, 10, 90, 90)
    assert images_differ_in_region(original, rendered, region)


def test_render_arrow():
    """测试箭头渲染"""
    original = create_test_image()
    annotation = {
        "tool": "arrow",
        "color": "#00FF00",
        "width": 3,
        "points": [[20, 20], [150, 150]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(20, 20, 140, 140)
    assert images_differ_in_region(original, rendered, region)


def test_render_pen():
    """测试画笔渲染"""
    original = create_test_image()
    annotation = {
        "tool": "pen",
        "color": "#FF00FF",
        "width": 3,
        "points": [[20, 20], [50, 30], [80, 50], [100, 80]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(20, 20, 80, 60)
    assert images_differ_in_region(original, rendered, region)


def test_render_marker():
    """测试马克笔渲染"""
    original = create_test_image()
    annotation = {
        "tool": "marker",
        "color": "#FFFF00",
        "width": 5,
        "points": [[30, 50], [150, 50]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(30, 40, 120, 20)
    assert images_differ_in_region(original, rendered, region)


@pytest.mark.skip(reason="Font loading may hang in CI environment")
def test_render_text():
    """测试文字渲染"""
    original = create_test_image()
    annotation = {
        "tool": "text",
        "color": "#0000FF",
        "width": 20,
        "points": [[50, 100]],
        "text": "Test",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(50, 70, 100, 50)
    assert images_differ_in_region(original, rendered, region)


@pytest.mark.skip(reason="Font loading may hang in CI environment")
def test_render_step():
    """测试步骤编号渲染"""
    original = create_test_image()
    annotation = {
        "tool": "step",
        "color": "#FF0000",
        "width": 30,
        "points": [[100, 100]],
        "text": "",
        "step_number": 5,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(85, 85, 30, 30)
    assert images_differ_in_region(original, rendered, region)


def test_render_mosaic():
    """测试马赛克渲染"""
    original = QImage(200, 200, QImage.Format.Format_ARGB32)
    for y in range(200):
        for x in range(200):
            original.setPixelColor(x, y, QColor(x, y, 128))
    
    annotation = {
        "tool": "mosaic",
        "color": "#000000",
        "width": 10,
        "points": [[50, 50], [150, 150]],
        "text": "",
        "step_number": 0,
    }
    
    rendered = AnnotationRenderer.render(original, [annotation])
    region = QRect(50, 50, 100, 100)
    assert images_differ_in_region(original, rendered, region)


def test_render_preserves_original():
    """测试渲染不修改原图"""
    original = create_test_image()
    original_copy = original.copy()
    
    annotation = {
        "tool": "rect",
        "color": "#FF0000",
        "width": 5,
        "points": [[10, 10], [100, 100]],
        "text": "",
        "step_number": 0,
    }
    
    AnnotationRenderer.render(original, [annotation])
    
    for y in range(original.height()):
        for x in range(original.width()):
            assert original.pixelColor(x, y) == original_copy.pixelColor(x, y)


def test_render_multiple_annotations():
    """测试多个标注渲染（不含文字类）"""
    original = create_test_image()
    annotations = [
        {"tool": "rect", "color": "#FF0000", "width": 2, "points": [[10, 10], [50, 50]], "text": "", "step_number": 0},
        {"tool": "ellipse", "color": "#00FF00", "width": 2, "points": [[60, 60], [120, 100]], "text": "", "step_number": 0},
        {"tool": "line", "color": "#0000FF", "width": 3, "points": [[130, 130], [180, 180]], "text": "", "step_number": 0},
    ]
    
    rendered = AnnotationRenderer.render(original, annotations)
    
    # 验证每个标注区域都有变化
    assert images_differ_in_region(original, rendered, QRect(10, 10, 40, 40))
    assert images_differ_in_region(original, rendered, QRect(60, 60, 60, 40))
    assert images_differ_in_region(original, rendered, QRect(130, 130, 50, 50))
