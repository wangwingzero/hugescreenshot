# =====================================================
# =============== 下载状态管理器测试 ===============
# =====================================================

"""
下载状态管理器单元测试

Feature: embedded-download-progress
Requirements: 3.2
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtCore import QObject

from screenshot_tool.services.update_service import (
    DownloadState,
    DownloadStateManager,
    VersionInfo,
)


class TestDownloadState:
    """DownloadState 枚举测试"""
    
    def test_download_state_values(self):
        """测试下载状态枚举值存在"""
        assert DownloadState.IDLE is not None
        assert DownloadState.DOWNLOADING is not None
        assert DownloadState.COMPLETED is not None
        assert DownloadState.FAILED is not None
        assert DownloadState.CANCELLED is not None
    
    def test_download_state_unique(self):
        """测试下载状态枚举值唯一"""
        states = [
            DownloadState.IDLE,
            DownloadState.DOWNLOADING,
            DownloadState.COMPLETED,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
        ]
        assert len(states) == len(set(states))


class TestDownloadStateManager:
    """DownloadStateManager 类测试"""
    
    @pytest.fixture
    def manager(self, qtbot):
        """创建 DownloadStateManager 实例"""
        return DownloadStateManager()
    
    @pytest.fixture
    def version_info(self):
        """创建测试用版本信息"""
        return VersionInfo(
            version="1.0.0",
            download_url="https://example.com/test.exe",
            release_notes="Test release",
            file_size=1024,
            published_at="2024-01-01",
        )
    
    def test_initial_state(self, manager):
        """测试初始状态为 IDLE"""
        assert manager.state == DownloadState.IDLE
        assert manager.file_path == ""
        assert manager.error_msg == ""
        assert manager.progress == (0, 0, 0.0)
    
    def test_state_property(self, manager):
        """测试状态属性"""
        assert manager.state == DownloadState.IDLE
    
    def test_progress_property(self, manager):
        """测试进度属性"""
        downloaded, total, speed = manager.progress
        assert downloaded == 0
        assert total == 0
        assert speed == 0.0
    
    def test_file_path_property(self, manager):
        """测试文件路径属性"""
        assert manager.file_path == ""
    
    def test_error_msg_property(self, manager):
        """测试错误信息属性"""
        assert manager.error_msg == ""
    
    def test_reset_from_idle(self, manager, qtbot):
        """测试从 IDLE 状态重置"""
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.reset()
        assert manager.state == DownloadState.IDLE
    
    def test_cancel_from_idle(self, manager):
        """测试从 IDLE 状态取消（无效操作）"""
        manager.cancel_download()
        assert manager.state == DownloadState.IDLE
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_start_download(self, mock_dm_class, manager, version_info, qtbot):
        """测试开始下载"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        assert manager.state == DownloadState.DOWNLOADING
        assert manager.version_info == version_info
        mock_dm.start_download.assert_called_once()
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_cancel_download(self, mock_dm_class, manager, version_info, qtbot):
        """测试取消下载"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 先开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 取消下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.cancel_download()
        
        assert manager.state == DownloadState.CANCELLED
        mock_dm.cancel_download.assert_called_once()
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_progress_update(self, mock_dm_class, manager, version_info, qtbot):
        """测试进度更新"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 模拟进度更新
        with qtbot.waitSignal(manager.progress_updated, timeout=1000):
            manager._on_progress(512, 1024, 100.0)
        
        assert manager.progress == (512, 1024, 100.0)
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_download_completed(self, mock_dm_class, manager, version_info, qtbot):
        """测试下载完成"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 模拟下载完成
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager._on_completed("/tmp/test.exe")
        
        assert manager.state == DownloadState.COMPLETED
        assert manager.file_path == "/tmp/test.exe"
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_download_failed(self, mock_dm_class, manager, version_info, qtbot):
        """测试下载失败"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 模拟下载失败
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager._on_error("Network error")
        
        assert manager.state == DownloadState.FAILED
        assert manager.error_msg == "Network error"
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_reset_from_completed(self, mock_dm_class, manager, version_info, qtbot):
        """测试从 COMPLETED 状态重置"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 模拟下载完成
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager._on_completed("/tmp/test.exe")
        
        # 重置
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.reset()
        
        assert manager.state == DownloadState.IDLE
        assert manager.file_path == ""
        assert manager.error_msg == ""
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_reset_from_failed(self, mock_dm_class, manager, version_info, qtbot):
        """测试从 FAILED 状态重置"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 模拟下载失败
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager._on_error("Network error")
        
        # 重置
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.reset()
        
        assert manager.state == DownloadState.IDLE
        assert manager.error_msg == ""
    
    @patch('screenshot_tool.services.update_service.DownloadManager')
    def test_no_duplicate_download(self, mock_dm_class, manager, version_info, qtbot):
        """测试不重复启动下载"""
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm
        
        # 开始下载
        with qtbot.waitSignal(manager.state_changed, timeout=1000):
            manager.start_download(version_info, "/tmp/test.exe")
        
        # 尝试再次开始下载（应该被忽略）
        manager.start_download(version_info, "/tmp/test2.exe")
        
        # 只应该调用一次
        assert mock_dm.start_download.call_count == 1
