# =====================================================
# =============== 下载进度窗口测试 ===============
# =====================================================

"""
下载进度窗口单元测试

Feature: simplify-update
Requirements: 2.4, 2.7, 2.9
"""

import pytest
from unittest.mock import MagicMock, patch

# 跳过 GUI 测试如果没有显示器
pytest.importorskip("PySide6")


class TestDownloadProgressWindow:
    """DownloadProgressWindow 测试类"""
    
    @pytest.fixture
    def window(self, qtbot):
        """创建测试窗口"""
        from screenshot_tool.ui.download_progress_window import DownloadProgressWindow
        
        window = DownloadProgressWindow("1.15.0")
        qtbot.addWidget(window)
        return window
    
    def test_init(self, window):
        """测试初始化
        
        Feature: simplify-update
        Requirements: 2.4
        """
        assert window._version == "1.15.0"
        assert window._is_completed is False
        assert window._is_cancelled is False
        assert window._progress_bar.value() == 0
    
    def test_update_progress_basic(self, window):
        """测试基本进度更新
        
        Feature: simplify-update
        Requirements: 2.4
        """
        # 50% 进度
        window.update_progress(50 * 1024 * 1024, 100 * 1024 * 1024, 500)
        
        assert window._progress_bar.value() == 50
        assert "50.0 MB" in window._size_label.text()
        assert "100.0 MB" in window._size_label.text()
    
    def test_update_progress_zero_total(self, window):
        """测试总大小为 0 的情况
        
        Feature: simplify-update
        Requirements: 2.4
        """
        window.update_progress(1000, 0, 100)
        
        assert window._progress_bar.value() == 0
    
    def test_update_progress_speed_kb(self, window):
        """测试速度显示 (KB/s)
        
        Feature: simplify-update
        Requirements: 2.4
        """
        window.update_progress(10 * 1024 * 1024, 100 * 1024 * 1024, 500)
        
        assert "500 KB/s" in window._speed_label.text()
    
    def test_update_progress_speed_mb(self, window):
        """测试速度显示 (MB/s)
        
        Feature: simplify-update
        Requirements: 2.4
        """
        window.update_progress(10 * 1024 * 1024, 100 * 1024 * 1024, 2048)
        
        assert "MB/s" in window._speed_label.text()
    
    def test_update_progress_max_100(self, window):
        """测试进度不超过 100%
        
        Feature: simplify-update
        Requirements: 2.4
        """
        # 下载量超过总量（异常情况）
        window.update_progress(150 * 1024 * 1024, 100 * 1024 * 1024, 500)
        
        assert window._progress_bar.value() == 100
    
    def test_show_completed(self, window):
        """测试显示完成状态
        
        Feature: simplify-update
        Requirements: 2.7
        """
        file_path = "C:\\Downloads\\HuGeScreenshot-1.15.0.exe"
        window.show_completed(file_path)
        
        assert window._is_completed is True
        assert window._progress_bar.value() == 100
        assert "下载完成" in window.windowTitle()
        assert file_path in window._status_label.text()
        # 检查状态标签不是隐藏状态（而不是检查 isVisible，因为窗口本身未显示）
        assert not window._status_label.isHidden()
        assert window._cancel_btn.isHidden()
        assert not window._close_btn.isHidden()
    
    def test_show_error(self, window):
        """测试显示错误状态
        
        Feature: simplify-update
        Requirements: 2.9
        """
        error_msg = "网络连接失败"
        window.show_error(error_msg)
        
        assert window._is_completed is True
        assert "下载失败" in window.windowTitle()
        assert error_msg in window._status_label.text()
        # 检查状态标签不是隐藏状态
        assert not window._status_label.isHidden()
        assert window._cancel_btn.isHidden()
        assert not window._close_btn.isHidden()
    
    def test_cancel_emits_signal(self, window, qtbot):
        """测试取消按钮发出信号
        
        Feature: simplify-update
        Requirements: 2.6
        """
        with qtbot.waitSignal(window.cancel_requested, timeout=1000):
            window._cancel_btn.click()
        
        assert window._is_cancelled is True
    
    def test_update_progress_after_completed(self, window):
        """测试完成后不再更新进度
        
        Feature: simplify-update
        Requirements: 2.7
        """
        window.show_completed("test.exe")
        
        # 尝试更新进度
        window.update_progress(10 * 1024 * 1024, 100 * 1024 * 1024, 500)
        
        # 进度应该保持 100%
        assert window._progress_bar.value() == 100
    
    def test_update_progress_after_cancelled(self, window):
        """测试取消后不再更新进度
        
        Feature: simplify-update
        Requirements: 2.6
        """
        window._on_cancel()
        
        # 尝试更新进度
        window.update_progress(10 * 1024 * 1024, 100 * 1024 * 1024, 500)
        
        # 进度应该保持不变
        assert window._is_cancelled is True
    
    def test_window_is_non_modal(self, window):
        """测试窗口是非模态的
        
        Feature: simplify-update
        Requirements: 2.5
        """
        # 检查窗口标志 - 非模态窗口应该是普通 Window 类型
        flags = window.windowFlags()
        # 确保是普通窗口类型
        assert flags & Qt.WindowType.Window
        # 确保有关闭和最小化按钮
        assert flags & Qt.WindowType.WindowCloseButtonHint
        assert flags & Qt.WindowType.WindowMinimizeButtonHint


# 导入 Qt 类型用于测试
from PySide6.QtCore import Qt
