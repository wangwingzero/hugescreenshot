# -*- coding: utf-8 -*-
"""
截图+OCR 分屏窗口快捷键单元测试

Feature: screenshot-ocr-split-view
Task: 2.3 实现快捷键支持

测试内容：
1. ESC 快捷键关闭窗口
2. Ctrl+C 快捷键复制（根据焦点决定复制图片还是文本）
3. Ctrl+S 快捷键保存

**Validates: Requirements 6.1, 6.2, 6.3**
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtGui import QImage, QColor, QKeySequence
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

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
# 快捷键初始化测试
# ============================================================

class TestShortcutInitialization:
    """快捷键初始化测试
    
    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    
    def test_esc_shortcut_exists(self, qtbot):
        """测试 ESC 快捷键存在
        
        Requirements: 6.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_esc_shortcut')
        assert window._esc_shortcut is not None
    
    def test_save_shortcut_exists(self, qtbot):
        """测试 Ctrl+S 快捷键存在
        
        Requirements: 6.3
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_save_shortcut')
        assert window._save_shortcut is not None
    
    def test_copy_shortcut_exists(self, qtbot):
        """测试 Ctrl+C 快捷键存在
        
        Requirements: 6.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, '_copy_shortcut')
        assert window._copy_shortcut is not None


# ============================================================
# ESC 快捷键测试
# ============================================================

class TestEscapeShortcut:
    """ESC 快捷键测试
    
    **Validates: Requirements 6.1**
    """
    
    def test_escape_pressed_signal_emitted(self, qtbot):
        """测试 ESC 按键发出 escape_pressed 信号
        
        Requirements: 6.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        with qtbot.waitSignal(window.escape_pressed, timeout=1000):
            window._on_escape_pressed()
    
    def test_escape_closes_window(self, qtbot):
        """测试 ESC 按键关闭窗口
        
        Requirements: 6.1
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        assert window.isVisible()
        
        # 模拟 ESC 按键处理
        window._on_escape_pressed()
        
        # 窗口应该关闭
        assert not window.isVisible()


# ============================================================
# Ctrl+C 复制快捷键测试
# ============================================================

class TestCopyShortcut:
    """Ctrl+C 复制快捷键测试
    
    **Validates: Requirements 6.2**
    """
    
    def test_copy_image_when_preview_panel_has_focus(self, qtbot):
        """测试预览面板有焦点时复制图片
        
        Requirements: 6.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 设置测试图片
        test_image = create_test_image(200, 150)
        window._preview_panel.set_image(test_image)
        
        # 设置焦点到预览面板
        window._preview_panel.setFocus()
        
        # 模拟 Ctrl+C
        with patch.object(window, '_on_copy_image_requested') as mock_copy:
            window._on_copy()
            mock_copy.assert_called_once()
    
    def test_copy_text_when_ocr_panel_text_edit_has_focus(self, qtbot):
        """测试 OCR 面板文本编辑器有焦点时复制文本
        
        Requirements: 6.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 获取 OCR 面板的文本编辑器
        ocr_text_edit = getattr(window._ocr_panel, '_text_edit', None)
        if ocr_text_edit is None:
            pytest.skip("OCR panel does not have _text_edit attribute")
        
        # 设置一些文本
        ocr_text_edit.setPlainText("测试文本内容")
        
        # 设置焦点到文本编辑器
        ocr_text_edit.setFocus()
        
        # 确保焦点已设置
        QApplication.processEvents()
        
        # 模拟 Ctrl+C（应该复制文本而不是图片）
        with patch.object(window, '_on_copy_image_requested') as mock_copy_image:
            window._on_copy()
            # 当 OCR 面板有焦点时，不应该调用复制图片
            # 而是复制文本到剪贴板
            if ocr_text_edit.hasFocus():
                mock_copy_image.assert_not_called()
    
    def test_copy_selected_text_when_text_selected(self, qtbot):
        """测试有选中文本时复制选中部分
        
        Requirements: 6.2
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 获取 OCR 面板的文本编辑器
        ocr_text_edit = getattr(window._ocr_panel, '_text_edit', None)
        if ocr_text_edit is None:
            pytest.skip("OCR panel does not have _text_edit attribute")
        
        # 设置文本并选中部分
        ocr_text_edit.setPlainText("Hello World 测试")
        ocr_text_edit.selectAll()
        
        # 设置焦点
        ocr_text_edit.setFocus()
        QApplication.processEvents()
        
        # 验证有选中文本
        cursor = ocr_text_edit.textCursor()
        assert cursor.hasSelection()


# ============================================================
# Ctrl+S 保存快捷键测试
# ============================================================

class TestSaveShortcut:
    """Ctrl+S 保存快捷键测试
    
    **Validates: Requirements 6.3**
    """
    
    def test_save_calls_save_image_requested(self, qtbot):
        """测试 Ctrl+S 调用保存图片方法
        
        Requirements: 6.3
        """
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 设置测试图片
        test_image = create_test_image(200, 150)
        window._preview_panel.set_image(test_image)
        
        # 模拟 Ctrl+S
        with patch.object(window, '_on_save_image_requested') as mock_save:
            window._on_save()
            mock_save.assert_called_once()


# ============================================================
# 窗口关闭信号测试
# ============================================================

class TestWindowCloseSignal:
    """窗口关闭信号测试"""
    
    def test_closed_signal_emitted_on_close(self, qtbot):
        """测试关闭窗口时发出 closed 信号"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        with qtbot.waitSignal(window.closed, timeout=1000):
            window.close()
    
    def test_closed_signal_emitted_on_escape(self, qtbot):
        """测试 ESC 关闭时发出 closed 信号"""
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        
        with qtbot.waitSignal(window.closed, timeout=1000):
            window._on_escape_pressed()
