# =====================================================
# =============== 嵌入式下载进度组件测试 ===============
# =====================================================

"""
嵌入式下载进度组件属性测试

Feature: embedded-download-progress
Requirements: 1.3
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.ui.dialogs import EmbeddedDownloadProgress
from screenshot_tool.services.update_service import DownloadState


class TestEmbeddedDownloadProgressProperty:
    """EmbeddedDownloadProgress 属性测试"""
    
    @pytest.fixture
    def widget(self, qtbot):
        """创建 EmbeddedDownloadProgress 实例"""
        w = EmbeddedDownloadProgress()
        qtbot.addWidget(w)
        return w
    
    def test_progress_percentage_correctness_boundary(self, widget):
        """Property 1: 进度百分比计算正确性 - 边界测试
        
        Validates: Requirements 1.3
        """
        # 测试 0%
        widget.update_progress(0, 1000, 100.0)
        assert widget._progress_bar.value() == 0
        assert widget._percent_label.text() == "0%"
        
        # 测试 50%
        widget.update_progress(500, 1000, 100.0)
        assert widget._progress_bar.value() == 50
        assert widget._percent_label.text() == "50%"
        
        # 测试 100%
        widget.update_progress(1000, 1000, 100.0)
        assert widget._progress_bar.value() == 100
        assert widget._percent_label.text() == "100%"
        
        # 测试超过 100%（应该被限制为 100%）
        widget.update_progress(1500, 1000, 100.0)
        assert widget._progress_bar.value() == 100
        assert widget._percent_label.text() == "100%"
    
    def test_progress_with_zero_total(self, widget):
        """测试 total 为 0 时的进度显示"""
        widget.update_progress(1000, 0, 100.0)
        assert widget._progress_bar.value() == 0
        assert widget._percent_label.text() == "0%"
    
    def test_speed_display_format_kb(self, widget):
        """测试速度显示格式 - KB/s"""
        widget.update_progress(1000, 2000, 500.0)
        assert "KB/s" in widget._speed_label.text()
    
    def test_speed_display_format_mb(self, widget):
        """测试速度显示格式 - MB/s"""
        widget.update_progress(1000, 2000, 2048.0)
        assert "MB/s" in widget._speed_label.text()


class TestEmbeddedDownloadProgressPropertyHypothesis:
    """EmbeddedDownloadProgress Hypothesis 属性测试"""
    
    @given(
        downloaded=st.integers(min_value=0, max_value=1_000_000),
        total=st.integers(min_value=1, max_value=1_000_000),
    )
    @settings(
        max_examples=10, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_progress_percentage_in_range(self, downloaded, total):
        """Property: 进度百分比始终在 0-100 范围内
        
        Validates: Requirements 1.3
        """
        widget = EmbeddedDownloadProgress()
        widget.update_progress(downloaded, total, 100.0)
        
        percent = widget._progress_bar.value()
        assert 0 <= percent <= 100, f"Percentage {percent} out of range [0, 100]"


class TestEmbeddedDownloadProgressState:
    """EmbeddedDownloadProgress 状态测试"""
    
    @pytest.fixture
    def widget(self, qtbot):
        """创建 EmbeddedDownloadProgress 实例"""
        w = EmbeddedDownloadProgress()
        qtbot.addWidget(w)
        return w
    
    def test_idle_state(self, widget):
        """测试 IDLE 状态显示"""
        widget.set_state(DownloadState.IDLE)
        
        assert not widget._cancel_btn.isHidden()
        assert widget._retry_btn.isHidden()
        assert widget._open_folder_btn.isHidden()
        assert widget._progress_bar.value() == 0
    
    def test_downloading_state(self, widget):
        """测试 DOWNLOADING 状态显示"""
        widget.set_state(DownloadState.DOWNLOADING)
        
        assert not widget._cancel_btn.isHidden()
        assert widget._retry_btn.isHidden()
        assert widget._open_folder_btn.isHidden()
        assert "正在下载" in widget._status_label.text()
    
    def test_completed_state(self, widget):
        """测试 COMPLETED 状态显示"""
        widget.set_state(DownloadState.COMPLETED)
        
        assert widget._cancel_btn.isHidden()
        assert widget._retry_btn.isHidden()
        assert not widget._open_folder_btn.isHidden()
        assert widget._progress_bar.value() == 100
        assert "下载完成" in widget._status_label.text()
    
    def test_failed_state(self, widget):
        """测试 FAILED 状态显示"""
        widget.set_state(DownloadState.FAILED)
        
        assert widget._cancel_btn.isHidden()
        assert not widget._retry_btn.isHidden()
        assert widget._open_folder_btn.isHidden()
    
    def test_cancelled_state(self, widget):
        """测试 CANCELLED 状态显示"""
        widget.set_state(DownloadState.CANCELLED)
        
        assert widget._cancel_btn.isHidden()
        assert not widget._retry_btn.isHidden()
        assert widget._open_folder_btn.isHidden()
        assert "已取消" in widget._status_label.text()
    
    def test_set_completed_with_path(self, widget):
        """测试设置完成状态并显示文件路径
        
        Feature: seamless-update-flow
        Requirements: 2.1, 2.2
        
        注意：根据 seamless-update-flow 设计，set_completed 现在会：
        - 隐藏"打开文件夹"按钮
        - 显示"立即更新"按钮
        """
        widget.set_completed("/path/to/HuGeScreenshot-1.0.0.exe")
        
        assert widget._file_path == "/path/to/HuGeScreenshot-1.0.0.exe"
        assert "HuGeScreenshot-1.0.0.exe" in widget._status_label.text()
        # seamless-update-flow: 打开文件夹按钮应该隐藏
        assert widget._open_folder_btn.isHidden()
        # seamless-update-flow: 立即更新按钮应该显示
        assert not widget._update_now_btn.isHidden()
    
    def test_set_error_with_message(self, widget):
        """测试设置错误状态并显示错误信息"""
        widget.set_error("网络连接失败")
        
        assert "网络连接失败" in widget._status_label.text()
        assert not widget._retry_btn.isHidden()


class TestEmbeddedDownloadProgressSignals:
    """EmbeddedDownloadProgress 信号测试"""
    
    @pytest.fixture
    def widget(self, qtbot):
        """创建 EmbeddedDownloadProgress 实例"""
        w = EmbeddedDownloadProgress()
        qtbot.addWidget(w)
        return w
    
    def test_cancel_signal(self, widget, qtbot):
        """测试取消信号"""
        with qtbot.waitSignal(widget.cancel_requested, timeout=1000):
            widget._cancel_btn.click()
    
    def test_retry_signal(self, widget, qtbot):
        """测试重试信号"""
        widget.set_state(DownloadState.FAILED)
        
        with qtbot.waitSignal(widget.retry_requested, timeout=1000):
            widget._retry_btn.click()
