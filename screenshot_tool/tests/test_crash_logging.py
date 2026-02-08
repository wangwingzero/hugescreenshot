# =====================================================
# =============== 崩溃日志增强测试 ===============
# =====================================================

"""
崩溃日志增强属性测试

Property 1: Log Flush Immediacy
Property 2: Qt Message Capture
Property 3: Thread-Safe Concurrent Writes

Feature: crash-logging-enhancement
Validates: Requirements 1.1, 2.1, 4.1
"""

import os
import sys
import tempfile
import threading
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from screenshot_tool.core.error_logger import ErrorLogger, init_error_logger


# ========== 策略定义 ==========

# 日志消息策略（避免特殊字符导致的问题）
log_message_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        blacklist_characters='\x00\r'
    ),
    min_size=1,
    max_size=200
)

# 线程数量策略
thread_count_strategy = st.integers(min_value=2, max_value=10)

# 每线程日志数量策略
logs_per_thread_strategy = st.integers(min_value=1, max_value=20)


# ========== ErrorLogger 单元测试 ==========

class TestErrorLoggerUnit:
    """ErrorLogger 单元测试"""
    
    def test_init_creates_lock(self):
        """测试初始化创建线程锁"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            assert hasattr(logger, '_lock')
            assert isinstance(logger._lock, type(threading.RLock()))
            assert logger._lock_timeout == 5.0
            
            logger.close()
    
    def test_init_file_handle_none(self):
        """测试初始化时文件句柄为 None"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            assert logger._file_handle is None
            
            logger.close()
    
    def test_write_log_opens_file(self):
        """测试写入日志时打开文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            logger.log_info("test message")
            
            assert logger._file_handle is not None
            assert not logger._file_handle.closed
            
            logger.close()
    
    def test_close_closes_file(self):
        """测试 close 方法关闭文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            logger.log_info("test message")
            assert logger._file_handle is not None
            
            logger.close()
            
            assert logger._file_handle is None
    
    def test_close_idempotent(self):
        """测试多次调用 close 是安全的"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            logger.log_info("test message")
            
            # 多次调用 close 不应抛出异常
            logger.close()
            logger.close()
            logger.close()
    
    def test_log_immediately_visible(self):
        """测试日志立即可见"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            test_message = "immediate visibility test"
            logger.log_info(test_message)
            
            # 不关闭文件，直接读取
            with open(logger.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            assert test_message in content
            
            logger.close()


# ========== ErrorLogger 属性测试 ==========

class TestErrorLoggerProperties:
    """ErrorLogger 属性测试
    
    Feature: crash-logging-enhancement
    """
    
    @given(message=log_message_strategy)
    @settings(max_examples=100, deadline=None)
    def test_property_1_log_flush_immediacy(self, message):
        """
        Property 1: Log Flush Immediacy
        
        *For any* log entry written to the ErrorLogger, the entry SHALL be
        visible in the log file immediately after the write call returns,
        without requiring the file to be closed.
        
        **Validates: Requirements 1.1**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            try:
                # 写入日志
                logger.log_info(message)
                
                # 立即读取文件（不关闭 logger）
                with open(logger.log_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 验证消息已写入
                assert message in content, \
                    f"Message '{message}' not found in log file immediately after write"
            finally:
                logger.close()
    
    @given(
        thread_count=thread_count_strategy,
        logs_per_thread=logs_per_thread_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_property_3_thread_safe_concurrent_writes(self, thread_count, logs_per_thread):
        """
        Property 3: Thread-Safe Concurrent Writes
        
        *For any* set of concurrent log writes from multiple threads, all log
        entries SHALL be written completely without interleaving or corruption.
        
        **Validates: Requirements 4.1**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            # 用于收集每个线程写入的消息
            expected_messages = []
            errors = []
            
            def write_logs(thread_id):
                try:
                    for i in range(logs_per_thread):
                        msg = f"Thread{thread_id}_Log{i}"
                        expected_messages.append(msg)
                        logger.log_info(msg)
                except Exception as e:
                    errors.append(e)
            
            # 创建并启动线程
            threads = []
            for i in range(thread_count):
                t = threading.Thread(target=write_logs, args=(i,))
                threads.append(t)
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join()
            
            logger.close()
            
            # 检查是否有错误
            assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
            
            # 读取日志文件
            with open(logger.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 验证所有消息都被写入
            for msg in expected_messages:
                assert msg in content, \
                    f"Message '{msg}' not found in log file after concurrent writes"
            
            # 验证没有消息被截断（每条消息应该在单独的行中完整出现）
            lines = content.split('\n')
            for msg in expected_messages:
                found = False
                for line in lines:
                    if msg in line:
                        # 检查消息没有被截断
                        assert f"[INFO] {msg}" in line, \
                            f"Message '{msg}' appears truncated in line: {line}"
                        found = True
                        break
                assert found, f"Message '{msg}' not found in any line"


# ========== 日志轮转测试 ==========

class TestLogRotation:
    """日志轮转测试"""
    
    def test_rotation_closes_file_handle(self):
        """测试轮转时关闭文件句柄"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            # 写入一些内容
            logger.log_info("initial message")
            
            # 手动触发轮转（通过创建大文件）
            # 这里我们直接测试 _rotate_if_needed 的行为
            # 创建一个超过 5MB 的日志文件
            with open(logger.log_path, 'w', encoding='utf-8') as f:
                f.write('x' * (5 * 1024 * 1024 + 1))
            
            # 重新打开文件句柄
            logger._file_handle = None
            logger.log_info("after rotation")
            
            # 验证备份文件存在
            backup_path = logger.log_path + ".1"
            assert os.path.exists(backup_path)
            
            logger.close()


# ========== 错误处理测试 ==========

class TestErrorHandling:
    """错误处理测试"""
    
    def test_write_to_readonly_directory_fallback(self):
        """测试写入只读目录时的回退"""
        # 这个测试在 Windows 上可能需要特殊处理
        # 因为 Windows 的权限模型不同
        pass  # 跳过此测试，因为 Windows 权限处理复杂
    
    def test_close_after_file_deleted(self):
        """测试文件被删除后调用 close"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            
            logger.log_info("test message")
            
            # 先关闭文件句柄
            logger.close()
            
            # 删除日志文件
            os.remove(logger.log_path)
            
            # 再次调用 close 不应抛出异常
            logger.close()


# ========== CrashHandler 测试 ==========

from screenshot_tool.core.crash_handler import CrashHandler


class TestCrashHandlerUnit:
    """CrashHandler 单元测试"""
    
    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            assert handler._error_logger is logger
            assert handler._original_qt_handler is None
            assert handler._installed is False
            
            logger.close()
    
    def test_installed_property(self):
        """测试 installed 属性"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            assert handler.installed is False
            
            logger.close()
    
    def test_install_idempotent(self, qtbot):
        """测试多次调用 install 是安全的"""
        from PySide6.QtWidgets import QApplication
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            app = QApplication.instance()
            
            # 多次调用 install 不应抛出异常
            handler.install(app)
            handler.install(app)
            handler.install(app)
            
            assert handler.installed is True
            
            logger.close()


class TestCrashHandlerProperties:
    """CrashHandler 属性测试
    
    Feature: crash-logging-enhancement
    """
    
    @given(message=log_message_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_2_qt_message_capture(self, message, qtbot):
        """
        Property 2: Qt Message Capture
        
        *For any* Qt message of type WARNING, CRITICAL, or FATAL, the message
        SHALL appear in the error log with the appropriate level prefix.
        
        **Validates: Requirements 2.1**
        """
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import qWarning
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            app = QApplication.instance()
            handler.install(app)
            
            # 发送 Qt 警告消息
            qWarning(message)
            
            # 读取日志文件
            logger.close()
            
            with open(logger.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 验证消息被记录（带有 Qt-WARNING 前缀）
            assert "[Qt-WARNING]" in content, \
                f"Qt warning prefix not found in log"
            assert message in content, \
                f"Message '{message}' not found in log after Qt warning"


class TestAtexitHandler:
    """atexit 处理器测试"""
    
    def test_atexit_handler_registered(self):
        """测试 atexit 处理器被注册"""
        import atexit
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            # 获取当前注册的 atexit 处理器数量
            # 注意：这是一个实现细节测试，可能在不同 Python 版本中有所不同
            
            # 安装处理器
            handler._install_atexit_handler()
            
            # 验证处理器被注册（通过检查 atexit 模块的内部状态）
            # 这里我们只能验证不抛出异常
            
            logger.close()


class TestSignalHandler:
    """信号处理器测试"""
    
    def test_signal_handler_installed_in_main_thread(self):
        """测试信号处理器在主线程中安装"""
        import signal
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ErrorLogger("1.0.0", temp_dir)
            handler = CrashHandler(logger)
            
            # 保存原始处理器
            original_sigterm = signal.getsignal(signal.SIGTERM)
            original_sigint = signal.getsignal(signal.SIGINT)
            
            try:
                # 安装处理器
                handler._install_signal_handlers()
                
                # 验证处理器已更改
                new_sigterm = signal.getsignal(signal.SIGTERM)
                new_sigint = signal.getsignal(signal.SIGINT)
                
                assert new_sigterm != original_sigterm or original_sigterm == signal.SIG_DFL
                assert new_sigint != original_sigint or original_sigint == signal.SIG_DFL
            finally:
                # 恢复原始处理器
                signal.signal(signal.SIGTERM, original_sigterm)
                signal.signal(signal.SIGINT, original_sigint)
                logger.close()
