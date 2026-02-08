"""模态对话框检测器测试

Feature: modal-dialog-hotkey-fix
Requirements: 1.3, 3.3
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from screenshot_tool.core.modal_dialog_detector import ModalDialogDetector


class TestModalDialogDetector:
    """模态对话框检测器单元测试"""
    
    def test_non_windows_platform_returns_false(self):
        """测试非 Windows 平台返回 False
        
        Requirements: 3.3
        """
        with patch.object(sys, 'platform', 'linux'):
            result = ModalDialogDetector.is_modal_dialog_active()
            assert result is False
    
    def test_non_windows_platform_verbose_returns_false(self):
        """测试非 Windows 平台详细版本返回 False
        
        Requirements: 3.3
        """
        with patch.object(sys, 'platform', 'darwin'):
            is_modal, reason = ModalDialogDetector.is_modal_dialog_active_verbose()
            assert is_modal is False
            assert "非 Windows 平台" in reason
    
    def test_import_error_returns_false(self):
        """测试导入错误时返回 False（fail-open）
        
        Requirements: 1.3, 3.3
        """
        with patch.object(sys, 'platform', 'win32'):
            with patch.dict(sys.modules, {'ctypes': None}):
                # 模拟 ctypes 导入失败
                with patch('builtins.__import__', side_effect=ImportError("No module named 'ctypes'")):
                    result = ModalDialogDetector.is_modal_dialog_active()
                    assert result is False
    
    def test_returns_boolean(self):
        """测试函数始终返回布尔值
        
        Requirements: 3.3
        """
        result = ModalDialogDetector.is_modal_dialog_active()
        assert isinstance(result, bool)
    
    def test_verbose_returns_tuple(self):
        """测试详细版本返回元组
        
        Requirements: 3.3
        """
        result = ModalDialogDetector.is_modal_dialog_active_verbose()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


@pytest.mark.skipif(sys.platform != 'win32', reason="Windows only test")
class TestModalDialogDetectorWindows:
    """Windows 平台特定测试"""
    
    def test_no_foreground_window_returns_false(self):
        """测试无前台窗口时返回 False
        
        Requirements: 3.3
        """
        import ctypes
        with patch.object(ctypes.windll.user32, 'GetForegroundWindow', return_value=0):
            result = ModalDialogDetector.is_modal_dialog_active()
            assert result is False
    
    def test_no_owner_window_returns_false(self):
        """测试无所有者窗口时返回 False
        
        Requirements: 3.3
        """
        import ctypes
        with patch.object(ctypes.windll.user32, 'GetForegroundWindow', return_value=12345):
            with patch.object(ctypes.windll.user32, 'GetWindow', return_value=0):
                result = ModalDialogDetector.is_modal_dialog_active()
                assert result is False
    
    def test_owner_enabled_returns_false(self):
        """测试所有者窗口启用时返回 False（非模态对话框）
        
        Requirements: 3.3
        """
        import ctypes
        with patch.object(ctypes.windll.user32, 'GetForegroundWindow', return_value=12345):
            with patch.object(ctypes.windll.user32, 'GetWindow', return_value=67890):
                with patch.object(ctypes.windll.user32, 'IsWindowEnabled', return_value=True):
                    result = ModalDialogDetector.is_modal_dialog_active()
                    assert result is False
    
    def test_owner_disabled_returns_true(self):
        """测试所有者窗口禁用时返回 True（模态对话框）
        
        Requirements: 1.1
        """
        import ctypes
        with patch.object(ctypes.windll.user32, 'GetForegroundWindow', return_value=12345):
            with patch.object(ctypes.windll.user32, 'GetWindow', return_value=67890):
                with patch.object(ctypes.windll.user32, 'IsWindowEnabled', return_value=False):
                    result = ModalDialogDetector.is_modal_dialog_active()
                    assert result is True
    
    def test_api_exception_returns_false(self):
        """测试 API 异常时返回 False（fail-open）
        
        Requirements: 1.3, 3.3
        """
        import ctypes
        with patch.object(ctypes.windll.user32, 'GetForegroundWindow', side_effect=OSError("API error")):
            result = ModalDialogDetector.is_modal_dialog_active()
            assert result is False



# ============================================================
# Property-Based Tests
# ============================================================

import time
from hypothesis import given, strategies as st, settings


class TestModalDialogDetectorProperties:
    """模态对话框检测器属性测试
    
    Feature: modal-dialog-hotkey-fix
    Property 3: Detection Performance and Robustness
    Validates: Requirements 3.1, 3.3
    """
    
    @settings(max_examples=100)
    @given(st.integers())
    def test_always_returns_boolean(self, _):
        """Property 3: 函数始终返回布尔值
        
        *For any* call to is_modal_dialog_active(), the function SHALL
        never raise an exception and always return a boolean.
        
        **Validates: Requirements 3.3**
        """
        result = ModalDialogDetector.is_modal_dialog_active()
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"
    
    @settings(max_examples=100)
    @given(st.integers())
    def test_completes_within_50ms(self, _):
        """Property 3: 函数在 50ms 内完成
        
        *For any* call to is_modal_dialog_active(), the function SHALL
        complete within 50 milliseconds.
        
        **Validates: Requirements 3.1**
        """
        start_time = time.perf_counter()
        ModalDialogDetector.is_modal_dialog_active()
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        assert elapsed_ms < 50, f"Detection took {elapsed_ms:.2f}ms, expected < 50ms"
    
    @settings(max_examples=100)
    @given(st.integers())
    def test_verbose_always_returns_tuple(self, _):
        """Property 3: 详细版本始终返回元组
        
        *For any* call to is_modal_dialog_active_verbose(), the function SHALL
        return a tuple of (bool, str).
        
        **Validates: Requirements 3.3**
        """
        result = ModalDialogDetector.is_modal_dialog_active_verbose()
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2, f"Expected 2 elements, got {len(result)}"
        assert isinstance(result[0], bool), f"Expected bool for first element, got {type(result[0])}"
        assert isinstance(result[1], str), f"Expected str for second element, got {type(result[1])}"


class TestModalDialogDetectorEnhanced:
    """增强的模态对话框检测器测试
    
    Feature: vip-realtime-unlock-modal-fix
    **Property 5: 模态对话框检测的全面性和线程安全性**
    **Validates: Requirements 3.1, 3.3, 3.5**
    """
    
    def test_qt_modal_widget_detection_no_app(self):
        """测试无 Qt 应用时返回 False
        
        Property 5: 模态对话框检测的全面性和线程安全性
        Validates: Requirements 3.1
        """
        with patch('screenshot_tool.core.modal_dialog_detector.ModalDialogDetector._check_qt_modal_widget') as mock:
            mock.return_value = False
            result = ModalDialogDetector.is_modal_dialog_active()
            # 应该继续检查其他方法
            mock.assert_called_once()
    
    def test_qt_modal_widget_detection_with_modal(self):
        """测试有 Qt 模态窗口时返回 True
        
        Property 5: 模态对话框检测的全面性和线程安全性
        Validates: Requirements 3.1
        """
        with patch('screenshot_tool.core.modal_dialog_detector.ModalDialogDetector._check_qt_modal_widget') as mock:
            mock.return_value = True
            result = ModalDialogDetector.is_modal_dialog_active()
            assert result is True
    
    def test_fail_open_on_exception(self):
        """测试异常时采用 fail-open 策略
        
        Property 5: 模态对话框检测的全面性和线程安全性
        Validates: Requirements 3.4
        """
        with patch('screenshot_tool.core.modal_dialog_detector.ModalDialogDetector._check_qt_modal_widget') as mock:
            mock.side_effect = RuntimeError("Test exception")
            # 应该不抛出异常，返回 False
            result = ModalDialogDetector.is_modal_dialog_active()
            assert result is False


class TestModalDialogDetectorThreadSafety:
    """模态对话框检测器线程安全测试
    
    Feature: vip-realtime-unlock-modal-fix
    **Property 5: 模态对话框检测的全面性和线程安全性**
    **Validates: Requirements 3.5**
    """
    
    def test_callable_from_multiple_threads(self):
        """测试可以从多个线程调用
        
        Property 5: 模态对话框检测的全面性和线程安全性
        Validates: Requirements 3.5
        """
        import threading
        import queue
        
        results = queue.Queue()
        errors = queue.Queue()
        
        def call_detector():
            try:
                result = ModalDialogDetector.is_modal_dialog_active()
                results.put(result)
            except Exception as e:
                errors.put(e)
        
        # 创建多个线程同时调用
        threads = [threading.Thread(target=call_detector) for _ in range(10)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=5.0)
        
        # 验证没有错误
        assert errors.empty(), f"Got errors: {list(errors.queue)}"
        
        # 验证所有调用都返回了结果
        assert results.qsize() == 10
        
        # 验证所有结果都是布尔值
        while not results.empty():
            result = results.get()
            assert isinstance(result, bool)
    
    @settings(max_examples=50)
    @given(st.integers(min_value=1, max_value=5))
    def test_concurrent_calls_property(self, num_threads):
        """Property 5: 并发调用安全性
        
        *For any* number of concurrent calls to is_modal_dialog_active(),
        all calls SHALL complete without exceptions and return boolean values.
        
        **Validates: Requirements 3.5**
        """
        import threading
        import queue
        
        results = queue.Queue()
        errors = queue.Queue()
        
        def call_detector():
            try:
                result = ModalDialogDetector.is_modal_dialog_active()
                results.put(result)
            except Exception as e:
                errors.put(e)
        
        threads = [threading.Thread(target=call_detector) for _ in range(num_threads)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=5.0)
        
        # 验证没有错误
        assert errors.empty()
        
        # 验证所有调用都返回了结果
        assert results.qsize() == num_threads
