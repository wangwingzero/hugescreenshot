# -*- coding: utf-8 -*-
"""
后台任务管理器测试

Feature: extreme-performance-optimization
Requirements: 6.1, 6.2, 11.5

测试内容：
1. 单例模式
2. 任务优先级
3. 截图模式暂停/恢复低优先级任务
4. 与 ScreenshotModeManager 集成
"""

import pytest
import time
import os
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThreadPool


class TestBackgroundTaskManager:
    """后台任务管理器测试"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后重置单例"""
        # 重置单例
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        BackgroundTaskManager.reset_instance()
        
        yield
        
        # 测试后重置
        BackgroundTaskManager.reset_instance()
    
    def test_singleton_pattern(self):
        """测试单例模式
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        
        manager1 = BackgroundTaskManager.instance()
        manager2 = BackgroundTaskManager.instance()
        
        assert manager1 is manager2
    
    def test_global_thread_pool(self):
        """测试使用全局 QThreadPool
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        
        manager = BackgroundTaskManager.instance()
        
        # 验证使用全局线程池
        assert manager._pool is QThreadPool.globalInstance()
    
    def test_thread_count_configuration(self):
        """测试线程数配置
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        
        线程数应为 CPU 核心数 - 1，至少为 1。
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        
        manager = BackgroundTaskManager.instance()
        
        cpu_count = os.cpu_count()
        expected_threads = max(1, cpu_count - 1) if cpu_count else 2
        
        assert manager.max_thread_count == expected_threads
    
    def test_task_priority_enum(self):
        """测试任务优先级枚举
        
        Feature: extreme-performance-optimization
        Requirements: 6.2
        """
        from screenshot_tool.core.background_task_manager import TaskPriority
        
        assert TaskPriority.LOW < TaskPriority.NORMAL < TaskPriority.HIGH
        assert int(TaskPriority.LOW) == 0
        assert int(TaskPriority.NORMAL) == 1
        assert int(TaskPriority.HIGH) == 2
    
    def test_submit_task(self, qtbot):
        """测试提交任务
        
        Feature: extreme-performance-optimization
        Requirements: 6.1, 6.2
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        def task_func():
            return 42
        
        task = BackgroundTask(task_func)
        task.signals.finished.connect(lambda r: result_holder.append(r))
        
        success = manager.submit(task, TaskPriority.NORMAL)
        assert success
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)  # 等待信号处理
        
        assert len(result_holder) == 1
        assert result_holder[0] == 42
    
    def test_submit_func_convenience(self, qtbot):
        """测试便捷方法 submit_func
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        def add(a, b):
            return a + b
        
        task = manager.submit_func(
            add, 1, 2,
            priority=TaskPriority.NORMAL,
            on_finished=lambda r: result_holder.append(r)
        )
        
        assert task is not None
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == 3
    
    def test_task_error_handling(self, qtbot):
        """测试任务错误处理
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask
        )
        
        manager = BackgroundTaskManager.instance()
        
        error_holder = []
        
        def failing_task():
            raise ValueError("Test error")
        
        task = BackgroundTask(failing_task)
        task.signals.error.connect(lambda e: error_holder.append(e))
        
        manager.submit(task)
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(error_holder) == 1
        assert "Test error" in error_holder[0]
    
    def test_pause_low_priority_tasks(self):
        """测试暂停低优先级任务
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        # 暂停低优先级任务
        manager.pause_low_priority()
        assert manager.is_paused
        
        # 提交低优先级任务
        task = BackgroundTask(lambda: "low")
        success = manager.submit(task, TaskPriority.LOW)
        
        assert success
        assert manager.pending_count == 1
    
    def test_resume_low_priority_tasks(self, qtbot):
        """测试恢复低优先级任务
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        # 暂停低优先级任务
        manager.pause_low_priority()
        
        # 提交低优先级任务
        task = BackgroundTask(lambda: "low priority result")
        task.signals.finished.connect(lambda r: result_holder.append(r))
        manager.submit(task, TaskPriority.LOW)
        
        assert manager.pending_count == 1
        
        # 恢复低优先级任务
        manager.resume_low_priority()
        assert not manager.is_paused
        assert manager.pending_count == 0
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == "low priority result"
    
    def test_high_priority_not_paused(self, qtbot):
        """测试高优先级任务不被暂停
        
        Feature: extreme-performance-optimization
        Requirements: 6.2, 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        # 暂停低优先级任务
        manager.pause_low_priority()
        
        # 提交高优先级任务
        task = BackgroundTask(lambda: "high priority")
        task.signals.finished.connect(lambda r: result_holder.append(r))
        manager.submit(task, TaskPriority.HIGH)
        
        # 高优先级任务不应被暂存
        assert manager.pending_count == 0
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == "high priority"
    
    def test_normal_priority_not_paused(self, qtbot):
        """测试普通优先级任务不被暂停
        
        Feature: extreme-performance-optimization
        Requirements: 6.2, 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        # 暂停低优先级任务
        manager.pause_low_priority()
        
        # 提交普通优先级任务
        task = BackgroundTask(lambda: "normal priority")
        task.signals.finished.connect(lambda r: result_holder.append(r))
        manager.submit(task, TaskPriority.NORMAL)
        
        # 普通优先级任务不应被暂存
        assert manager.pending_count == 0
        
        # 等待任务完成
        manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == "normal priority"
    
    def test_cancel_pending_tasks(self):
        """测试取消暂存的任务
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        # 暂停低优先级任务
        manager.pause_low_priority()
        
        # 提交多个低优先级任务
        for i in range(3):
            task = BackgroundTask(lambda: f"task {i}")
            manager.submit(task, TaskPriority.LOW)
        
        assert manager.pending_count == 3
        
        # 取消所有暂存的任务
        cancelled = manager.cancel_pending()
        
        assert cancelled == 3
        assert manager.pending_count == 0
    
    def test_task_cancellation(self, qtbot):
        """测试任务取消
        
        Feature: extreme-performance-optimization
        Requirements: 6.1
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask
        )
        
        manager = BackgroundTaskManager.instance()
        
        result_holder = []
        
        def slow_task():
            time.sleep(0.5)
            return "completed"
        
        task = BackgroundTask(slow_task)
        task.signals.finished.connect(lambda r: result_holder.append(r))
        
        # 取消任务
        task.cancel()
        assert task.is_cancelled
        
        # 提交已取消的任务
        success = manager.submit(task)
        assert not success  # 已取消的任务应被拒绝
    
    def test_signals_emitted(self, qtbot):
        """测试信号发出
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        manager = BackgroundTaskManager.instance()
        
        paused_signal_received = []
        resumed_signal_received = []
        
        manager.low_priority_paused.connect(
            lambda: paused_signal_received.append(True)
        )
        manager.low_priority_resumed.connect(
            lambda count: resumed_signal_received.append(count)
        )
        
        # 暂停
        manager.pause_low_priority()
        assert len(paused_signal_received) == 1
        
        # 提交任务
        task = BackgroundTask(lambda: "test")
        manager.submit(task, TaskPriority.LOW)
        
        # 恢复
        manager.resume_low_priority()
        assert len(resumed_signal_received) == 1
        assert resumed_signal_received[0] == 1  # 1 个任务被恢复
    
    def test_double_pause_ignored(self):
        """测试重复暂停被忽略
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        
        manager = BackgroundTaskManager.instance()
        
        signal_count = []
        manager.low_priority_paused.connect(lambda: signal_count.append(1))
        
        # 第一次暂停
        manager.pause_low_priority()
        assert len(signal_count) == 1
        
        # 第二次暂停应被忽略
        manager.pause_low_priority()
        assert len(signal_count) == 1  # 信号不应再次发出
    
    def test_double_resume_ignored(self):
        """测试重复恢复被忽略
        
        Feature: extreme-performance-optimization
        Requirements: 11.5
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        
        manager = BackgroundTaskManager.instance()
        
        signal_count = []
        manager.low_priority_resumed.connect(lambda c: signal_count.append(c))
        
        # 先暂停
        manager.pause_low_priority()
        
        # 第一次恢复
        manager.resume_low_priority()
        assert len(signal_count) == 1
        
        # 第二次恢复应被忽略
        manager.resume_low_priority()
        assert len(signal_count) == 1  # 信号不应再次发出


class TestBackgroundTaskManagerIntegration:
    """后台任务管理器集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后重置单例"""
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )
        
        BackgroundTaskManager.reset_instance()
        ScreenshotModeManager.reset_instance()
        
        yield
        
        BackgroundTaskManager.reset_instance()
        ScreenshotModeManager.reset_instance()
    
    def test_integration_with_screenshot_mode_manager(self, qtbot):
        """测试与 ScreenshotModeManager 集成
        
        Feature: extreme-performance-optimization
        Requirements: 11.5, 12.4
        
        进入截图模式时应自动暂停低优先级任务。
        """
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        
        # 先获取 BackgroundTaskManager 实例（会自动注册回调）
        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()
        
        result_holder = []
        
        # 进入截图模式
        mode_manager.enter_screenshot_mode()
        
        # 验证低优先级任务被暂停
        assert task_manager.is_paused
        
        # 提交低优先级任务
        task = BackgroundTask(lambda: "deferred task")
        task.signals.finished.connect(lambda r: result_holder.append(r))
        task_manager.submit(task, TaskPriority.LOW)
        
        # 任务应被暂存
        assert task_manager.pending_count == 1
        
        # 退出截图模式
        mode_manager.exit_screenshot_mode()
        
        # 验证低优先级任务恢复
        assert not task_manager.is_paused
        assert task_manager.pending_count == 0
        
        # 等待任务完成
        task_manager.wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == "deferred task"


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后重置单例"""
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        BackgroundTaskManager.reset_instance()
        
        yield
        
        BackgroundTaskManager.reset_instance()
    
    def test_get_background_task_manager(self):
        """测试 get_background_task_manager 便捷函数"""
        from screenshot_tool.core.background_task_manager import (
            get_background_task_manager, BackgroundTaskManager
        )
        
        manager = get_background_task_manager()
        assert manager is BackgroundTaskManager.instance()
    
    def test_submit_background_task(self, qtbot):
        """测试 submit_background_task 便捷函数"""
        from screenshot_tool.core.background_task_manager import (
            submit_background_task, TaskPriority, BackgroundTaskManager
        )
        
        result_holder = []
        
        def multiply(a, b):
            return a * b
        
        task = submit_background_task(
            multiply, 3, 4,
            priority=TaskPriority.NORMAL,
            on_finished=lambda r: result_holder.append(r)
        )
        
        assert task is not None
        
        # 等待任务完成
        BackgroundTaskManager.instance().wait_for_done(1000)
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == 12
