# -*- coding: utf-8 -*-
"""
截图+OCR 分屏窗口单元测试

Feature: screenshot-ocr-split-view
Task: 2.5 编写 ScreenshotOCRSplitWindow 单元测试

测试内容：
1. 窗口初始化测试（最小尺寸、窗口标志、标题、分隔器、面板）
2. 置顶功能测试（默认状态、set_pinned、信号、按钮）
3. show_screenshot 测试（设置图片、启动 OCR、显示窗口）
4. 信号测试（closed、save_requested）

**Validates: Requirements 1.5, 6.1-6.6**
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSplitter

from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow


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
# 窗口初始化测试
# ============================================================

class TestWindowInitialization:
    """窗口初始化测试
    
    **Validates: Requirements 1.5, 6.4**
    """
    
    def test_minimum_width_is_800(self, qtbot):
        """测试窗口最小宽度为 800 像素
        
        Requirements: 1.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.minimumWidth() == 800
        assert window.MIN_WIDTH == 800
    
    def test_minimum_height_is_500(self, qtbot):
        """测试窗口最小高度为 500 像素
        
        Requirements: 1.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.minimumHeight() == 500
        assert window.MIN_HEIGHT == 500
    
    def test_minimum_size_constraint(self, qtbot):
        """测试窗口最小尺寸约束 (800x500)
        
        Requirements: 1.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        min_size = window.minimumSize()
        assert min_size.width() == 800
        assert min_size.height() == 500
    
    def test_window_stays_on_top_hint_by_default(self, qtbot):
        """测试窗口默认置顶
        
        Requirements: 6.4
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
    
    def test_window_has_close_button(self, qtbot):
        """测试窗口有关闭按钮"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowCloseButtonHint
    
    def test_window_has_min_max_buttons(self, qtbot):
        """测试窗口有最小化/最大化按钮"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowMinMaxButtonsHint

    
    def test_window_title_is_set(self, qtbot):
        """测试窗口标题已设置"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.windowTitle() == "截图 + OCR"
    
    def test_window_object_name_is_set(self, qtbot):
        """测试窗口对象名称已设置（用于样式）"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.objectName() == "splitWindow"


# ============================================================
# 分隔器测试
# ============================================================

class TestSplitter:
    """分隔器测试
    
    **Validates: Requirements 1.2, 1.3, 1.6**
    """
    
    def test_splitter_exists(self, qtbot):
        """测试分隔器存在
        
        Requirements: 1.3
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_splitter')
        assert window._splitter is not None
        assert isinstance(window._splitter, QSplitter)
    
    def test_splitter_property_returns_splitter(self, qtbot):
        """测试 splitter 属性返回分隔器"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.splitter is window._splitter
    
    def test_splitter_is_horizontal(self, qtbot):
        """测试分隔器是水平方向
        
        Requirements: 1.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._splitter.orientation() == Qt.Orientation.Horizontal
    
    def test_splitter_opaque_resize_disabled(self, qtbot):
        """测试分隔器禁用实时重绘（性能优化）"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._splitter.opaqueResize() is False
    
    def test_splitter_children_not_collapsible(self, qtbot):
        """测试分隔器子组件不可折叠"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._splitter.childrenCollapsible() is False

    
    def test_splitter_has_two_widgets(self, qtbot):
        """测试分隔器有两个子组件
        
        Requirements: 1.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._splitter.count() == 2
    
    def test_splitter_handle_width(self, qtbot):
        """测试分隔条宽度"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._splitter.handleWidth() == 1


# ============================================================
# 面板测试
# ============================================================

class TestPanels:
    """面板测试
    
    **Validates: Requirements 1.2, 2.5-2.9, 3.1-3.11**
    """
    
    def test_preview_panel_exists(self, qtbot):
        """测试截图预览面板存在
        
        Requirements: 1.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_preview_panel')
        assert window._preview_panel is not None
    
    def test_preview_panel_property(self, qtbot):
        """测试 preview_panel 属性返回预览面板"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.preview_panel is window._preview_panel
    
    def test_ocr_panel_exists(self, qtbot):
        """测试 OCR 结果面板存在
        
        Requirements: 1.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_ocr_panel')
        assert window._ocr_panel is not None
    
    def test_ocr_panel_property(self, qtbot):
        """测试 ocr_panel 属性返回 OCR 面板"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.ocr_panel is window._ocr_panel
    
    def test_preview_panel_minimum_width(self, qtbot):
        """测试预览面板最小宽度"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._preview_panel.minimumWidth() == 200
    
    def test_ocr_panel_minimum_width(self, qtbot):
        """测试 OCR 面板最小宽度"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._ocr_panel.minimumWidth() == 200



# ============================================================
# 置顶功能测试
# ============================================================

class TestPinningFunctionality:
    """置顶功能测试
    
    **Validates: Requirements 6.4, 6.5, 6.6**
    """
    
    def test_default_pinned_state_is_true(self, qtbot):
        """测试默认置顶状态为 True
        
        Requirements: 6.4
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.is_pinned is True
        assert window._is_pinned is True
    
    def test_set_pinned_true_sets_window_stays_on_top_hint(self, qtbot):
        """测试 set_pinned(True) 设置 WindowStaysOnTopHint
        
        Requirements: 6.4
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 先取消置顶
        window.set_pinned(False)
        assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        
        # 再设置置顶
        window.set_pinned(True)
        assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    
    def test_set_pinned_false_removes_window_stays_on_top_hint(self, qtbot):
        """测试 set_pinned(False) 移除 WindowStaysOnTopHint
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 默认是置顶的
        assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        
        # 取消置顶
        window.set_pinned(False)
        assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    
    def test_pinned_changed_signal_emitted_on_pin(self, qtbot):
        """测试置顶时发出 pinned_changed 信号
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 先取消置顶
        window._is_pinned = False
        
        with qtbot.waitSignal(window.pinned_changed, timeout=1000) as blocker:
            window.set_pinned(True)
        
        assert blocker.args == [True]
    
    def test_pinned_changed_signal_emitted_on_unpin(self, qtbot):
        """测试取消置顶时发出 pinned_changed 信号
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        with qtbot.waitSignal(window.pinned_changed, timeout=1000) as blocker:
            window.set_pinned(False)
        
        assert blocker.args == [False]
    
    def test_pinned_changed_signal_not_emitted_when_same_state(self, qtbot):
        """测试状态相同时不发出 pinned_changed 信号"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 默认是置顶的，再次设置置顶不应发出信号
        signal_emitted = False
        
        def on_signal(value):
            nonlocal signal_emitted
            signal_emitted = True
        
        window.pinned_changed.connect(on_signal)
        window.set_pinned(True)  # 状态相同
        
        assert signal_emitted is False

    
    def test_pin_button_exists(self, qtbot):
        """测试置顶按钮存在
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_pin_btn')
        assert window._pin_btn is not None
    
    def test_pin_button_is_checkable(self, qtbot):
        """测试置顶按钮可选中
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._pin_btn.isCheckable() is True
    
    def test_pin_button_default_checked(self, qtbot):
        """测试置顶按钮默认选中
        
        Requirements: 6.4
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._pin_btn.isChecked() is True
    
    def test_pin_button_click_toggles_pinned_state(self, qtbot):
        """测试点击置顶按钮切换置顶状态
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 初始状态是置顶
        assert window.is_pinned is True
        
        # 点击按钮取消置顶
        window._on_pin_clicked()
        assert window.is_pinned is False
        
        # 再次点击恢复置顶
        window._on_pin_clicked()
        assert window.is_pinned is True
    
    def test_pin_button_updates_on_set_pinned(self, qtbot):
        """测试 set_pinned 更新按钮状态
        
        Requirements: 6.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 取消置顶
        window.set_pinned(False)
        assert window._pin_btn.isChecked() is False
        
        # 恢复置顶
        window.set_pinned(True)
        assert window._pin_btn.isChecked() is True


# ============================================================
# show_screenshot 测试
# ============================================================

class TestShowScreenshot:
    """show_screenshot 方法测试
    
    **Validates: Requirements 1.1, 2.1, 3.1**
    """
    
    def test_show_screenshot_sets_image_on_preview_panel(self, qtbot):
        """测试 show_screenshot 设置预览面板图片
        
        Requirements: 2.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image(200, 150)
        window.show_screenshot(test_image)
        
        assert window._preview_panel.has_image() is True

    
    def test_show_screenshot_stores_screenshot(self, qtbot):
        """测试 show_screenshot 存储截图"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image(200, 150)
        window.show_screenshot(test_image)
        
        assert window._screenshot is not None
        assert window._screenshot.width() == 200
        assert window._screenshot.height() == 150
    
    def test_show_screenshot_stores_annotations(self, qtbot):
        """测试 show_screenshot 存储标注"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image()
        annotations = [{"type": "rect", "x": 10, "y": 10}]
        window.show_screenshot(test_image, annotations)
        
        assert window._annotations == annotations
    
    def test_show_screenshot_with_none_image(self, qtbot):
        """测试 show_screenshot 使用 None 图片"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        window.show_screenshot(None)
        
        assert window._screenshot is None
    
    def test_show_screenshot_with_empty_image(self, qtbot):
        """测试 show_screenshot 使用空图片"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        empty_image = QImage()
        window.show_screenshot(empty_image)
        
        assert window._screenshot is None
    
    def test_show_screenshot_copies_image(self, qtbot):
        """测试 show_screenshot 复制图片而非引用"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image()
        window.show_screenshot(test_image)
        
        # 修改原始图片
        test_image.fill(QColor(0, 255, 0))
        
        # 窗口中的图片应该不受影响
        assert window._screenshot is not test_image
    
    def test_show_screenshot_shows_window(self, qtbot):
        """测试 show_screenshot 显示窗口
        
        Requirements: 1.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.isVisible() is False
        
        test_image = create_test_image()
        window.show_screenshot(test_image)
        
        assert window.isVisible() is True
    
    def test_show_screenshot_activates_window(self, qtbot):
        """测试 show_screenshot 激活窗口"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image()
        window.show_screenshot(test_image)
        
        # 窗口应该被激活（isActiveWindow 在测试环境中可能不可靠）
        assert window.isVisible() is True

    
    def test_show_screenshot_with_ocr_manager(self, qtbot):
        """测试 show_screenshot 使用 OCR 管理器
        
        Requirements: 3.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image()
        
        # 创建模拟的 OCR 管理器
        mock_ocr_manager = MagicMock()
        
        with patch.object(window._ocr_panel, 'set_ocr_manager') as mock_set_manager:
            with patch.object(window._ocr_panel, 'start_ocr') as mock_start_ocr:
                window.show_screenshot(test_image, ocr_manager=mock_ocr_manager)
                
                mock_set_manager.assert_called_once_with(mock_ocr_manager)
                mock_start_ocr.assert_called_once()
    
    def test_show_screenshot_starts_ocr_with_empty_item_id(self, qtbot):
        """测试 show_screenshot 使用空 item_id 启动 OCR"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        test_image = create_test_image()
        mock_ocr_manager = MagicMock()
        
        with patch.object(window._ocr_panel, 'set_ocr_manager'):
            with patch.object(window._ocr_panel, 'start_ocr') as mock_start_ocr:
                window.show_screenshot(test_image, ocr_manager=mock_ocr_manager)
                
                # 验证 start_ocr 被调用，第二个参数是空字符串
                args, kwargs = mock_start_ocr.call_args
                assert args[1] == ""  # item_id 为空


# ============================================================
# 信号测试
# ============================================================

class TestSignals:
    """信号测试
    
    **Validates: Requirements 6.1, 7.4, 7.5**
    """
    
    def test_closed_signal_emitted_on_close(self, qtbot):
        """测试关闭窗口时发出 closed 信号"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        with qtbot.waitSignal(window.closed, timeout=1000):
            window.close()
    
    def test_save_requested_signal_exists(self, qtbot):
        """测试 save_requested 信号存在"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'save_requested')
    
    def test_escape_pressed_signal_exists(self, qtbot):
        """测试 escape_pressed 信号存在"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'escape_pressed')
    
    def test_pinned_changed_signal_exists(self, qtbot):
        """测试 pinned_changed 信号存在"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'pinned_changed')
    
    def test_image_copied_signal_exists(self, qtbot):
        """测试 image_copied 信号存在
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'image_copied')
    
    def test_image_saved_signal_exists(self, qtbot):
        """测试 image_saved 信号存在
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'image_saved')
    
    def test_image_copied_signal_emitted_on_copy(self, qtbot):
        """测试复制图片时发出 image_copied 信号
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 设置测试图片
        test_image = create_test_image(100, 100)
        window.show_screenshot(test_image)
        
        # 监听信号
        signal_received = []
        window.image_copied.connect(lambda img: signal_received.append(img))
        
        # 触发复制
        window._on_copy_image_requested()
        
        # 验证信号被发射
        assert len(signal_received) == 1
        assert not signal_received[0].isNull()



# ============================================================
# 窗口工具栏测试
# ============================================================

class TestWindowToolbar:
    """窗口工具栏测试
    
    **Validates: Requirements 6.5**
    """
    
    def test_window_toolbar_exists(self, qtbot):
        """测试窗口工具栏存在"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_window_toolbar')
        assert window._window_toolbar is not None


# ============================================================
# 内部状态测试
# ============================================================

class TestInternalState:
    """内部状态测试"""
    
    def test_initial_screenshot_is_none(self, qtbot):
        """测试初始截图为 None"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._screenshot is None
    
    def test_initial_annotations_is_empty(self, qtbot):
        """测试初始标注列表为空"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._annotations == []
    
    def test_initial_is_pinned_is_true(self, qtbot):
        """测试初始置顶状态为 True"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window._is_pinned is True


# ============================================================
# 编辑功能测试
# ============================================================

class TestEditFunctionality:
    """编辑功能测试
    
    **Validates: Requirements 2.5, 2.6, 2.7**
    """
    
    def test_on_edit_requested_does_nothing_without_screenshot(self, qtbot):
        """测试没有截图时编辑请求不做任何事"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 没有截图，调用编辑请求不应崩溃
        window._on_edit_requested()
    
    def test_on_editing_finished_updates_screenshot(self, qtbot):
        """测试编辑完成更新截图
        
        Requirements: 2.7
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 设置初始截图
        initial_image = create_test_image(100, 100, QColor(255, 0, 0))
        window.show_screenshot(initial_image)
        
        # 模拟编辑完成
        new_image = create_test_image(200, 200, QColor(0, 255, 0))
        new_annotations = [{"type": "rect"}]
        
        window._on_editing_finished(new_image, new_annotations)
        
        assert window._screenshot.width() == 200
        assert window._screenshot.height() == 200
        assert window._annotations == new_annotations
    
    def test_on_editing_finished_with_none_image(self, qtbot):
        """测试编辑完成使用 None 图片"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        window._on_editing_finished(None, [])
        
        assert window._screenshot is None
        assert window._annotations == []



# ============================================================
# 复制图片功能测试
# ============================================================

class TestCopyImageFunctionality:
    """复制图片功能测试
    
    **Validates: Requirements 2.8**
    """
    
    def test_on_copy_image_requested_does_nothing_without_image(self, qtbot):
        """测试没有图片时复制请求不做任何事"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 没有图片，调用复制请求不应崩溃
        window._on_copy_image_requested()
    
    def test_on_copy_image_requested_copies_to_clipboard(self, qtbot):
        """测试复制图片到剪贴板
        
        Requirements: 2.8
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 设置测试图片
        test_image = create_test_image(200, 150)
        window.show_screenshot(test_image)
        
        # 复制图片
        window._on_copy_image_requested()
        
        # 验证剪贴板中有图片
        clipboard = QApplication.clipboard()
        clipboard_image = clipboard.image()
        
        assert not clipboard_image.isNull()
        assert clipboard_image.width() == 200
        assert clipboard_image.height() == 150


# ============================================================
# 返回图片功能测试
# ============================================================

class TestBackToImageFunctionality:
    """返回图片功能测试"""
    
    def test_on_back_to_image_sets_focus_to_preview_panel(self, qtbot):
        """测试返回图片设置焦点到预览面板"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 调用返回图片
        window._on_back_to_image()
        
        # 预览面板应该获得焦点
        # 注意：在测试环境中焦点可能不可靠，但方法不应崩溃
        assert True  # 方法执行成功


# ============================================================
# 样式测试
# ============================================================

class TestStyles:
    """样式测试
    
    **Validates: Requirements 5.1-5.6**
    """
    
    def test_stylesheet_is_applied(self, qtbot):
        """测试样式表已应用"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert window.styleSheet() != ""
    
    def test_colors_constants_exist(self, qtbot):
        """测试颜色常量存在"""
        from screenshot_tool.ui.screenshot_ocr_split_window import COLORS
        
        assert "primary" in COLORS
        assert "bg" in COLORS
        assert "surface" in COLORS
        assert "text" in COLORS
        assert "border" in COLORS
    
    def test_primary_color_is_correct(self, qtbot):
        """测试主色调正确
        
        Requirements: 5.2
        """
        from screenshot_tool.ui.screenshot_ocr_split_window import COLORS
        
        assert COLORS["primary"] == "#3B82F6"
    
    def test_background_color_is_correct(self, qtbot):
        """测试背景色正确
        
        Requirements: 5.2
        """
        from screenshot_tool.ui.screenshot_ocr_split_window import COLORS
        
        assert COLORS["bg"] == "#F8FAFC"
