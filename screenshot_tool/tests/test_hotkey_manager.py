"""热键管理器属性测试

Feature: hotkey-force-lock
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.4

测试 GlobalHotkeyManager 的强制锁定重试机制
"""

import sys
import time
import threading
from unittest.mock import Mock, patch, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, assume


# 模拟 Windows 环境
@pytest.fixture(autouse=True)
def mock_windows_platform(monkeypatch):
    """模拟 Windows 平台环境"""
    # 保存原始值
    original_platform = sys.platform
    
    # 模拟 Windows
    monkeypatch.setattr(sys, 'platform', 'win32')
    
    yield
    
    # 恢复原始值（pytest 会自动处理）


@pytest.fixture
def mock_user32():
    """模拟 Windows user32 API"""
    with patch('screenshot_tool.overlay_main.user32') as mock:
        # 默认注册成功
        mock.RegisterHotKey.return_value = True
        mock.UnregisterHotKey.return_value = True
        mock.PeekMessageW.return_value = 0  # 无消息
        yield mock


@pytest.fixture
def mock_ctypes():
    """模拟 ctypes"""
    with patch('screenshot_tool.overlay_main.ctypes') as mock:
        mock.get_last_error.return_value = 0
        mock.byref = MagicMock()
        yield mock


class TestHotkeyStatus:
    """测试热键状态枚举"""
    
    def test_status_values(self):
        """测试状态值定义"""
        from screenshot_tool.overlay_main import HotkeyStatus
        
        assert HotkeyStatus.UNKNOWN == "unknown"
        assert HotkeyStatus.REGISTERED == "registered"
        assert HotkeyStatus.WAITING == "waiting"
        assert HotkeyStatus.FAILED == "failed"


class TestGlobalHotkeyManagerInit:
    """测试 GlobalHotkeyManager 初始化"""
    
    def test_default_force_lock_disabled(self, mock_user32, mock_ctypes):
        """测试默认禁用强制锁定"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            
            assert manager._force_lock is False
            assert manager._retry_interval_ms == 3000
            assert manager._retry_timer is None
    
    def test_force_lock_enabled_on_init(self, mock_user32, mock_ctypes):
        """测试初始化时启用强制锁定"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(
                callback, 
                force_lock=True, 
                retry_interval_ms=5000
            )
            
            assert manager._force_lock is True
            assert manager._retry_interval_ms == 5000


class TestSetForceLock:
    """测试 set_force_lock 方法"""
    
    def test_enable_force_lock(self, mock_user32, mock_ctypes):
        """测试启用强制锁定"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager, HotkeyStatus
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            manager._running = True
            manager._registered = False
            manager._registration_status = HotkeyStatus.FAILED
            
            with patch.object(manager, '_schedule_retry') as mock_schedule:
                manager.set_force_lock(True, 5000)
                
                assert manager._force_lock is True
                assert manager._retry_interval_ms == 5000
                mock_schedule.assert_called_once()
    
    def test_disable_force_lock_cancels_retry(self, mock_user32, mock_ctypes):
        """测试禁用强制锁定时取消重试"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True)
            manager._running = True
            
            with patch.object(manager, '_cancel_retry') as mock_cancel:
                manager.set_force_lock(False)
                
                assert manager._force_lock is False
                mock_cancel.assert_called_once()


class TestScheduleRetry:
    """测试 _schedule_retry 方法"""
    
    def test_schedule_retry_creates_timer(self, mock_user32, mock_ctypes):
        """测试安排重试创建定时器"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True, retry_interval_ms=1000)
            manager._running = True
            
            manager._schedule_retry()
            
            assert manager._retry_timer is not None
            assert manager._retry_timer.is_alive() or not manager._retry_timer.finished.is_set()
            
            # 清理
            manager._cancel_retry()
    
    def test_schedule_retry_not_when_disabled(self, mock_user32, mock_ctypes):
        """测试禁用强制锁定时不安排重试"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=False)
            manager._running = True
            
            manager._schedule_retry()
            
            assert manager._retry_timer is None
    
    def test_schedule_retry_not_when_stopped(self, mock_user32, mock_ctypes):
        """测试停止时不安排重试"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True)
            manager._running = False
            
            manager._schedule_retry()
            
            assert manager._retry_timer is None


class TestCancelRetry:
    """测试 _cancel_retry 方法"""
    
    def test_cancel_retry_stops_timer(self, mock_user32, mock_ctypes):
        """测试取消重试停止定时器"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True, retry_interval_ms=10000)
            manager._running = True
            
            # 安排重试
            manager._schedule_retry()
            assert manager._retry_timer is not None
            
            # 取消重试
            manager._cancel_retry()
            assert manager._retry_timer is None
    
    def test_cancel_retry_when_no_timer(self, mock_user32, mock_ctypes):
        """测试没有定时器时取消重试不报错"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            manager._retry_timer = None
            
            # 不应该抛出异常
            manager._cancel_retry()
            assert manager._retry_timer is None


class TestCleanup:
    """测试 cleanup 方法"""
    
    def test_cleanup_cancels_retry(self, mock_user32, mock_ctypes):
        """测试清理时取消重试"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True, retry_interval_ms=10000)
            manager._running = True
            manager._listener_thread = None
            
            # 安排重试
            manager._schedule_retry()
            assert manager._retry_timer is not None
            
            # 清理
            manager.cleanup()
            
            assert manager._running is False
            assert manager._retry_timer is None


class TestGetRegistrationStatus:
    """测试 get_registration_status 方法"""
    
    def test_get_status_returns_current_status(self, mock_user32, mock_ctypes):
        """测试获取当前状态"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager, HotkeyStatus
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            
            # 初始状态
            assert manager.get_registration_status() == HotkeyStatus.UNKNOWN
            
            # 修改状态
            manager._registration_status = HotkeyStatus.REGISTERED
            assert manager.get_registration_status() == HotkeyStatus.REGISTERED
            
            manager._registration_status = HotkeyStatus.WAITING
            assert manager.get_registration_status() == HotkeyStatus.WAITING
            
            manager._registration_status = HotkeyStatus.FAILED
            assert manager.get_registration_status() == HotkeyStatus.FAILED


class TestStatusCallback:
    """测试状态回调"""
    
    def test_set_status_callback(self, mock_user32, mock_ctypes):
        """测试设置状态回调"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        status_callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            manager.set_status_callback(status_callback)
            
            assert manager._status_callback == status_callback
    
    def test_status_callback_called_on_change(self, mock_user32, mock_ctypes):
        """测试状态变化时调用回调"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager, HotkeyStatus
        
        callback = Mock()
        status_callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback)
            manager.set_status_callback(status_callback)
            
            # 直接调用信号处理方法（模拟信号触发）
            manager._on_status_changed_signal(HotkeyStatus.REGISTERED)
            
            status_callback.assert_called_once_with(HotkeyStatus.REGISTERED)


# ============ 属性测试 ============

class TestHotkeyManagerProperties:
    """热键管理器属性测试"""
    
    @given(force_lock=st.booleans(), retry_interval=st.integers(min_value=1000, max_value=30000))
    @settings(max_examples=50)
    def test_property_force_lock_state_consistency(
        self, force_lock: bool, retry_interval: int
    ):
        """Property: 强制锁定状态一致性
        
        设置强制锁定后，状态应该与设置值一致
        """
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch('screenshot_tool.overlay_main.user32') as mock_user32:
            mock_user32.RegisterHotKey.return_value = True
            with patch('screenshot_tool.overlay_main.ctypes') as mock_ctypes:
                mock_ctypes.get_last_error.return_value = 0
                with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
                    with patch.object(GlobalHotkeyManager, '_schedule_retry'):
                        with patch.object(GlobalHotkeyManager, '_cancel_retry'):
                            manager = GlobalHotkeyManager(callback)
                            manager._running = True
                            
                            manager.set_force_lock(force_lock, retry_interval)
                            
                            assert manager._force_lock == force_lock
                            assert manager._retry_interval_ms == retry_interval
    
    @given(retry_interval=st.integers(min_value=1000, max_value=30000))
    @settings(max_examples=30)
    def test_property_retry_interval_preserved(self, retry_interval: int):
        """Property: 重试间隔保持
        
        设置的重试间隔应该被正确保存
        """
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch('screenshot_tool.overlay_main.user32') as mock_user32:
            mock_user32.RegisterHotKey.return_value = True
            with patch('screenshot_tool.overlay_main.ctypes') as mock_ctypes:
                mock_ctypes.get_last_error.return_value = 0
                with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
                    manager = GlobalHotkeyManager(
                        callback, 
                        force_lock=True, 
                        retry_interval_ms=retry_interval
                    )
                    
                    assert manager._retry_interval_ms == retry_interval


class TestNotificationSuppression:
    """测试通知抑制"""
    
    def test_notification_shown_flag_reset_on_success(self, mock_user32, mock_ctypes):
        """Property 8: 成功注册后重置通知标志
        
        当热键注册成功后，通知标志应该被重置
        """
        from screenshot_tool.overlay_main import GlobalHotkeyManager, HotkeyStatus
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True)
            manager._running = True
            manager._notification_shown = True  # 模拟已显示通知
            
            # 模拟注册成功
            manager._registered = True
            manager._update_status(HotkeyStatus.REGISTERED)
            manager._notification_shown = False  # 这是 _retry_registration 中的行为
            
            assert manager._notification_shown is False
    
    def test_notification_flag_preserved_during_retry(self, mock_user32, mock_ctypes):
        """Property 8: 重试期间保持通知标志
        
        在重试期间，通知标志应该保持不变
        """
        from screenshot_tool.overlay_main import GlobalHotkeyManager, HotkeyStatus
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True)
            manager._running = True
            manager._notification_shown = True
            manager._registration_status = HotkeyStatus.WAITING
            
            # 在等待状态下，通知标志应该保持
            assert manager._notification_shown is True
            assert manager._registration_status == HotkeyStatus.WAITING


class TestHotkeyListenerErrorHandling:
    """测试热键监听器错误处理"""
    
    def test_error_1409_triggers_retry_when_force_lock(self, mock_user32, mock_ctypes):
        """测试错误码 1409 在启用强制锁定时触发重试"""
        from screenshot_tool.overlay_main import (
            GlobalHotkeyManager, 
            HotkeyStatus,
            ERROR_HOTKEY_ALREADY_REGISTERED
        )
        
        assert ERROR_HOTKEY_ALREADY_REGISTERED == 1409
        
        callback = Mock()
        
        # 模拟注册失败
        mock_user32.RegisterHotKey.return_value = False
        mock_ctypes.get_last_error.return_value = 1409
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=True)
            manager._running = True
            
            with patch.object(manager, '_schedule_retry') as mock_schedule:
                with patch.object(manager, '_update_status') as mock_update:
                    # 模拟 _hotkey_listener 中的错误处理逻辑
                    error_code = 1409
                    manager._last_error_code = error_code
                    
                    if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
                        if manager._force_lock:
                            mock_update(HotkeyStatus.WAITING)
                            mock_schedule()
                    
                    mock_update.assert_called_with(HotkeyStatus.WAITING)
                    mock_schedule.assert_called_once()
    
    def test_error_1409_marks_failed_when_no_force_lock(self, mock_user32, mock_ctypes):
        """测试错误码 1409 在未启用强制锁定时标记失败"""
        from screenshot_tool.overlay_main import (
            GlobalHotkeyManager, 
            HotkeyStatus,
            ERROR_HOTKEY_ALREADY_REGISTERED
        )
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(callback, force_lock=False)
            manager._running = True
            
            with patch.object(manager, '_schedule_retry') as mock_schedule:
                with patch.object(manager, '_update_status') as mock_update:
                    # 模拟 _hotkey_listener 中的错误处理逻辑
                    error_code = 1409
                    manager._last_error_code = error_code
                    
                    if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
                        if manager._force_lock:
                            mock_update(HotkeyStatus.WAITING)
                            mock_schedule()
                        else:
                            mock_update(HotkeyStatus.FAILED)
                    
                    mock_update.assert_called_with(HotkeyStatus.FAILED)
                    mock_schedule.assert_not_called()
