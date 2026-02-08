# -*- coding: utf-8 -*-
"""
截图预览面板单元测试

Feature: screenshot-ocr-split-view
Task: 1.4 编写 ScreenshotPreviewPanel 单元测试

测试内容：
1. 面板初始化测试
2. 图片加载和显示测试
3. 缩放功能测试
4. 标注渲染测试
5. 状态管理测试

**Validates: Requirements 2.1-2.4**
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from screenshot_tool.ui.screenshot_preview_panel import ScreenshotPreviewPanel


# ============================================================
# 辅助函数
# ============================================================

def create_test_image(width: int = 100, height: int = 100, color: QColor = None) -> QImage:
    """创建测试用图片
    
    Args:
        width: 图片宽度
        height: 图片高度
        color: 填充颜色，默认为红色
        
    Returns:
        QImage 实例
    """
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(color or QColor(255, 0, 0))  # 默认红色
    return image


# ============================================================
# 面板初始化测试
# ============================================================

class TestPanelInitialization:
    """面板初始化测试
    
    **Validates: Requirements 2.1, 2.3**
    """
    
    def test_default_zoom_level_is_one(self, qtbot):
        """测试默认缩放级别为 1.0
        
        Requirements: 2.3
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel.get_zoom_level() == 1.0
    
    def test_no_image_on_init(self, qtbot):
        """测试初始化时没有图片
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel.has_image() is False
    
    def test_original_image_is_none_on_init(self, qtbot):
        """测试初始化时原始图片为 None"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._original_image is None
    
    def test_annotations_empty_on_init(self, qtbot):
        """测试初始化时标注列表为空"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._annotations == []
    
    def test_cached_pixmap_is_none_on_init(self, qtbot):
        """测试初始化时缓存 Pixmap 为 None"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._cached_pixmap is None
    
    def test_toolbar_exists(self, qtbot):
        """测试工具栏存在"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._toolbar is not None
    
    def test_scroll_area_exists(self, qtbot):
        """测试滚动区域存在"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._scroll_area is not None
    
    def test_image_label_exists(self, qtbot):
        """测试图片标签存在"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._image_label is not None
    
    def test_status_bar_exists(self, qtbot):
        """测试状态栏存在"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._status_bar is not None
    
    def test_zoom_buttons_exist(self, qtbot):
        """测试缩放按钮存在
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._zoom_in_btn is not None
        assert panel._zoom_out_btn is not None
        assert panel._zoom_reset_btn is not None
        assert panel._zoom_fit_btn is not None
    
    def test_action_buttons_exist(self, qtbot):
        """测试操作按钮存在
        
        Requirements: 2.5, 2.8, 2.9
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._edit_btn is not None
        assert panel._copy_btn is not None
        assert panel._save_btn is not None


# ============================================================
# 图片加载和显示测试
# ============================================================

class TestImageLoading:
    """图片加载和显示测试
    
    **Validates: Requirements 2.1, 2.4**
    """
    
    def test_set_image_with_valid_image(self, qtbot):
        """测试使用有效图片调用 set_image
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image(200, 150)
        panel.set_image(test_image)
        
        assert panel.has_image() is True
        assert panel._original_image is not None
        assert panel._original_image.width() == 200
        assert panel._original_image.height() == 150
    
    def test_set_image_with_none(self, qtbot):
        """测试使用 None 调用 set_image
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        # 先设置一个有效图片
        test_image = create_test_image()
        panel.set_image(test_image)
        assert panel.has_image() is True
        
        # 然后设置 None
        panel.set_image(None)
        assert panel.has_image() is False
    
    def test_set_image_with_empty_image(self, qtbot):
        """测试使用空图片调用 set_image
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        empty_image = QImage()  # 空图片
        panel.set_image(empty_image)
        
        assert panel.has_image() is False
    
    def test_set_image_resets_zoom_level(self, qtbot):
        """测试 set_image 重置缩放级别
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        # 先设置图片并缩放
        test_image = create_test_image()
        panel.set_image(test_image)
        panel.zoom_in()
        assert panel.get_zoom_level() > 1.0
        
        # 重新设置图片
        panel.set_image(test_image)
        assert panel.get_zoom_level() == 1.0
    
    def test_set_image_invalidates_old_cache(self, qtbot):
        """测试 set_image 使旧缓存失效并创建新缓存
        
        注意：set_image 调用 _update_display() 会重新渲染并创建新缓存，
        但旧的缓存对象会被替换。
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置第一张图片
        test_image1 = create_test_image(100, 100, QColor(255, 0, 0))
        panel.set_image(test_image1)
        
        # 获取第一个缓存
        old_cache = panel._cached_pixmap
        assert old_cache is not None
        
        # 设置第二张不同的图片
        test_image2 = create_test_image(200, 200, QColor(0, 255, 0))
        panel.set_image(test_image2)
        
        # 新缓存应该是不同的对象（尺寸不同）
        new_cache = panel._cached_pixmap
        assert new_cache is not None
        assert new_cache.width() == 200
        assert new_cache.height() == 200
    
    def test_set_image_with_annotations(self, qtbot):
        """测试使用标注调用 set_image
        
        Requirements: 2.4
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        annotations = [{"type": "rect", "x": 10, "y": 10, "width": 50, "height": 50}]
        
        panel.set_image(test_image, annotations)
        
        assert panel._annotations == annotations
    
    def test_set_image_copies_image(self, qtbot):
        """测试 set_image 复制图片而非引用
        
        Requirements: 2.1
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 修改原始图片
        test_image.fill(QColor(0, 255, 0))  # 改为绿色
        
        # 面板中的图片应该不受影响（仍为红色）
        # 通过检查是否是不同的对象来验证
        assert panel._original_image is not test_image


# ============================================================
# 缩放功能测试
# ============================================================

class TestZoomFunctionality:
    """缩放功能测试
    
    **Validates: Requirements 2.2, 2.3**
    """
    
    def test_zoom_in_increases_zoom_level(self, qtbot):
        """测试 zoom_in 增加缩放级别
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        initial_zoom = panel.get_zoom_level()
        panel.zoom_in()
        
        assert panel.get_zoom_level() > initial_zoom
    
    def test_zoom_out_decreases_zoom_level(self, qtbot):
        """测试 zoom_out 减少缩放级别
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        initial_zoom = panel.get_zoom_level()
        panel.zoom_out()
        
        assert panel.get_zoom_level() < initial_zoom
    
    def test_zoom_reset_resets_to_one(self, qtbot):
        """测试 zoom_reset 重置缩放级别到 1.0
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 先缩放
        panel.zoom_in()
        panel.zoom_in()
        assert panel.get_zoom_level() != 1.0
        
        # 重置
        panel.zoom_reset()
        assert panel.get_zoom_level() == 1.0
    
    def test_zoom_max_limit(self, qtbot):
        """测试缩放最大限制 (MAX_ZOOM=5.0)
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 多次放大
        for _ in range(50):
            panel.zoom_in()
        
        assert panel.get_zoom_level() <= ScreenshotPreviewPanel.MAX_ZOOM
    
    def test_zoom_min_limit(self, qtbot):
        """测试缩放最小限制 (MIN_ZOOM=0.1)
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 多次缩小
        for _ in range(50):
            panel.zoom_out()
        
        assert panel.get_zoom_level() >= ScreenshotPreviewPanel.MIN_ZOOM
    
    def test_zoom_step_is_correct(self, qtbot):
        """测试缩放步长正确 (ZOOM_STEP=0.15)
        
        Requirements: 2.2
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        initial_zoom = panel.get_zoom_level()
        panel.zoom_in()
        
        expected_zoom = initial_zoom * (1.0 + ScreenshotPreviewPanel.ZOOM_STEP)
        assert abs(panel.get_zoom_level() - expected_zoom) < 0.001
    
    def test_zoom_label_updates(self, qtbot):
        """测试缩放级别标签更新
        
        Requirements: 2.3
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 初始状态
        assert "100%" in panel._zoom_label_toolbar.text()
        
        # 放大后
        panel.zoom_in()
        zoom_percent = int(panel.get_zoom_level() * 100)
        assert f"{zoom_percent}%" in panel._zoom_label_toolbar.text()
    
    def test_zoom_status_label_updates(self, qtbot):
        """测试状态栏缩放级别更新
        
        Requirements: 2.3
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        panel.zoom_in()
        zoom_percent = int(panel.get_zoom_level() * 100)
        assert f"{zoom_percent}%" in panel._zoom_status_label.text()
    
    def test_zoom_constants_are_valid(self, qtbot):
        """测试缩放常量有效"""
        assert ScreenshotPreviewPanel.MIN_ZOOM == 0.1
        assert ScreenshotPreviewPanel.MAX_ZOOM == 5.0
        assert ScreenshotPreviewPanel.ZOOM_STEP == 0.15
        assert ScreenshotPreviewPanel.MIN_ZOOM < ScreenshotPreviewPanel.MAX_ZOOM


# ============================================================
# 标注渲染测试
# ============================================================

class TestAnnotationRendering:
    """标注渲染测试
    
    **Validates: Requirements 2.4**
    """
    
    def test_get_rendered_image_returns_image(self, qtbot):
        """测试 get_rendered_image 返回图像
        
        Requirements: 2.4
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image(200, 150)
        panel.set_image(test_image)
        
        rendered = panel.get_rendered_image()
        
        assert rendered is not None
        assert isinstance(rendered, QImage)
        assert rendered.width() == 200
        assert rendered.height() == 150
    
    def test_get_rendered_image_returns_none_without_image(self, qtbot):
        """测试没有图片时 get_rendered_image 返回 None
        
        Requirements: 2.4
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        rendered = panel.get_rendered_image()
        
        assert rendered is None
    
    def test_render_with_annotations_caches_result(self, qtbot):
        """测试 _render_with_annotations 缓存结果
        
        Requirements: 2.4
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 第一次渲染
        result1 = panel._render_with_annotations()
        assert panel._cached_pixmap is not None
        
        # 第二次渲染应该返回缓存
        result2 = panel._render_with_annotations()
        assert result1 is result2
    
    def test_invalidate_cache_recreates_cache(self, qtbot):
        """测试 invalidate_cache 使缓存失效并重新渲染
        
        Requirements: 2.7
        
        注意：invalidate_cache 调用 _update_display() 会重新渲染，
        所以缓存会被重新创建。这里测试缓存确实被重新生成。
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        # 获取初始缓存
        old_cache = panel._cached_pixmap
        assert old_cache is not None
        old_cache_key = old_cache.cacheKey()
        
        # 手动清除缓存（模拟标注修改）
        panel._cached_pixmap = None
        
        # 调用 invalidate_cache 会重新渲染
        panel.invalidate_cache()
        
        # 缓存应该被重新创建
        assert panel._cached_pixmap is not None


# ============================================================
# has_image 测试
# ============================================================

class TestHasImage:
    """has_image 方法测试
    
    **Validates: Requirements 2.1**
    """
    
    def test_has_image_returns_false_initially(self, qtbot):
        """测试初始状态 has_image 返回 False"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel.has_image() is False
    
    def test_has_image_returns_true_with_valid_image(self, qtbot):
        """测试有有效图片时 has_image 返回 True"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        assert panel.has_image() is True
    
    def test_has_image_returns_false_after_clear(self, qtbot):
        """测试清空后 has_image 返回 False"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        assert panel.has_image() is True
        
        panel.clear()
        assert panel.has_image() is False
    
    def test_has_image_returns_false_with_null_image(self, qtbot):
        """测试空图片时 has_image 返回 False"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        null_image = QImage()
        panel.set_image(null_image)
        
        assert panel.has_image() is False


# ============================================================
# clear 方法测试
# ============================================================

class TestClearMethod:
    """clear 方法测试"""
    
    def test_clear_resets_original_image(self, qtbot):
        """测试 clear 重置原始图片"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        panel.clear()
        
        assert panel._original_image is None
    
    def test_clear_resets_annotations(self, qtbot):
        """测试 clear 重置标注列表"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        annotations = [{"type": "rect"}]
        panel.set_image(test_image, annotations)
        
        panel.clear()
        
        assert panel._annotations == []
    
    def test_clear_resets_zoom_level(self, qtbot):
        """测试 clear 重置缩放级别"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        panel.zoom_in()
        
        panel.clear()
        
        assert panel.get_zoom_level() == 1.0
    
    def test_clear_resets_cached_pixmap(self, qtbot):
        """测试 clear 重置缓存 Pixmap"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        panel._render_with_annotations()
        
        panel.clear()
        
        assert panel._cached_pixmap is None
    
    def test_clear_updates_image_label(self, qtbot):
        """测试 clear 更新图片标签显示"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image()
        panel.set_image(test_image)
        
        panel.clear()
        
        assert "暂无截图" in panel._image_label.text()


# ============================================================
# 信号测试
# ============================================================

class TestSignals:
    """信号测试
    
    **Validates: Requirements 2.5, 2.8, 2.9**
    """
    
    def test_edit_button_emits_signal(self, qtbot):
        """测试编辑按钮发出信号
        
        Requirements: 2.5
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        with qtbot.waitSignal(panel.edit_requested, timeout=1000):
            qtbot.mouseClick(panel._edit_btn, Qt.MouseButton.LeftButton)
    
    def test_copy_button_emits_signal(self, qtbot):
        """测试复制按钮发出信号
        
        Requirements: 2.8
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        with qtbot.waitSignal(panel.copy_requested, timeout=1000):
            qtbot.mouseClick(panel._copy_btn, Qt.MouseButton.LeftButton)
    
    def test_save_button_emits_signal(self, qtbot):
        """测试保存按钮发出信号
        
        Requirements: 2.9
        """
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        with qtbot.waitSignal(panel.save_requested, timeout=1000):
            qtbot.mouseClick(panel._save_btn, Qt.MouseButton.LeftButton)


# ============================================================
# 尺寸显示测试
# ============================================================

class TestSizeDisplay:
    """尺寸显示测试"""
    
    def test_size_label_shows_dimensions(self, qtbot):
        """测试尺寸标签显示图片尺寸"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image(320, 240)
        panel.set_image(test_image)
        
        assert "320" in panel._size_label.text()
        assert "240" in panel._size_label.text()
    
    def test_size_label_empty_without_image(self, qtbot):
        """测试没有图片时尺寸标签为空"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel._size_label.text() == ""
    
    def test_size_label_clears_after_clear(self, qtbot):
        """测试 clear 后尺寸标签清空"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        test_image = create_test_image(320, 240)
        panel.set_image(test_image)
        
        panel.clear()
        
        assert panel._size_label.text() == ""


# ============================================================
# zoom_fit 测试
# ============================================================

class TestZoomFit:
    """zoom_fit 方法测试
    
    **Validates: Requirements 2.1**
    """
    
    def test_zoom_fit_without_image_does_nothing(self, qtbot):
        """测试没有图片时 zoom_fit 不做任何事"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        
        initial_zoom = panel.get_zoom_level()
        panel.zoom_fit()
        
        assert panel.get_zoom_level() == initial_zoom
    
    def test_zoom_fit_respects_min_zoom(self, qtbot):
        """测试 zoom_fit 遵守最小缩放限制"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        panel.resize(800, 600)
        panel.show()
        
        # 创建一个非常大的图片
        large_image = create_test_image(10000, 10000)
        panel.set_image(large_image)
        
        panel.zoom_fit()
        
        assert panel.get_zoom_level() >= ScreenshotPreviewPanel.MIN_ZOOM
    
    def test_zoom_fit_respects_max_zoom(self, qtbot):
        """测试 zoom_fit 遵守最大缩放限制"""
        panel = ScreenshotPreviewPanel()
        qtbot.addWidget(panel)
        panel.resize(800, 600)
        panel.show()
        
        # 创建一个非常小的图片
        small_image = create_test_image(10, 10)
        panel.set_image(small_image)
        
        panel.zoom_fit()
        
        assert panel.get_zoom_level() <= ScreenshotPreviewPanel.MAX_ZOOM
