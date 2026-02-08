# -*- coding: utf-8 -*-
"""
后台任务管理器属性测试

Feature: extreme-performance-optimization
**Validates: Requirements 6.1, 6.2**

Property 11: Thread Pool Usage for Background Tasks
- 验证所有后台任务通过 QThreadPool 执行
- 验证任务优先级被正确处理
- 验证截图模式时低优先级任务被暂停
- 验证任务成功完成并返回正确结果

测试策略：
1. 使用 hypothesis 生成随机任务参数
2. 验证任务通过 QThreadPool 执行
3. 验证优先级排序
4. 验证暂停/恢复机制
"""

import pytest
import os
from typing import List, Tuple
from hypothesis import given, strategies as st, settings

from PySide6.QtCore import QThreadPool


# 任务优先级策略
priority_strategy = st.sampled_from([0, 1, 2])  # LOW, NORMAL, HIGH

# 任务参数策略
task_args_strategy = st.tuples(
    st.integers(min_value=-100, max_value=100),
    st.integers(min_value=-100, max_value=100)
)


def reset_managers():
    """重置单例管理器"""
    from screenshot_tool.core.background_task_manager import BackgroundTaskManager
    from screenshot_tool.core.screenshot_mode_manager import ScreenshotModeManager
    
    try:
        if BackgroundTaskManager._instance is not None:
            BackgroundTaskManager._instance.cancel_pending()
            BackgroundTaskManager._instance.wait_for_done(200)
    except Exception:
        pass
    
    BackgroundTaskManager.reset_instance()
    ScreenshotModeManager.reset_instance()


class TestBackgroundTaskProperty:
    """后台任务属性测试

    **Validates: Requirements 6.1, 6.2**

    Property 11: Thread Pool Usage for Background Tasks
    """

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qapp):
        """每个测试前后重置单例"""
        reset_managers()
        yield
        reset_managers()

    @settings(max_examples=100, deadline=None)
    @given(dummy=st.integers(min_value=1, max_value=100))
    def test_uses_global_thread_pool(self, dummy: int):
        """Property 11.1: 使用全局 QThreadPool

        **Validates: Requirements 6.1**

        *For any* BackgroundTaskManager instance, it SHALL use
        the global QThreadPool instance.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )

        manager = BackgroundTaskManager.instance()
        
        assert manager._pool is QThreadPool.globalInstance(), \
            "BackgroundTaskManager must use global QThreadPool"

    @settings(max_examples=100, deadline=None)
    @given(dummy=st.integers(min_value=1, max_value=100))
    def test_thread_pool_thread_count_optimal(self, dummy: int):
        """Property 11.2: 线程池线程数配置正确

        **Validates: Requirements 6.1**

        *For any* system configuration, the thread pool max thread count
        SHALL be CPU cores - 1 (minimum 1).
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )

        manager = BackgroundTaskManager.instance()
        cpu_count = os.cpu_count()
        expected_threads = max(1, cpu_count - 1) if cpu_count else 2

        assert manager.max_thread_count == expected_threads, \
            f"Thread count should be {expected_threads}"

    @settings(max_examples=100, deadline=None)
    @given(priority=priority_strategy)
    def test_task_priority_enum_values(self, priority: int):
        """Property 11.3: 任务优先级枚举值正确

        **Validates: Requirements 6.2**

        *For any* priority value, it SHALL map to correct TaskPriority enum.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import TaskPriority

        priority_enum = TaskPriority(priority)
        
        assert int(priority_enum) == priority
        assert TaskPriority.LOW < TaskPriority.NORMAL < TaskPriority.HIGH

    @settings(max_examples=100, deadline=None)
    @given(dummy=st.integers(min_value=1, max_value=100))
    def test_screenshot_mode_pauses_low_priority(self, dummy: int):
        """Property 11.4: 截图模式暂停低优先级任务

        **Validates: Requirements 6.2**

        *For any* screenshot mode entry, low-priority tasks SHALL be paused.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )

        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()

        assert not task_manager.is_paused, "Should not be paused initially"

        mode_manager.enter_screenshot_mode()
        assert task_manager.is_paused, "Should be paused in screenshot mode"

        mode_manager.exit_screenshot_mode()
        assert not task_manager.is_paused, "Should resume after exit"

    @settings(max_examples=50, deadline=None)
    @given(task_count=st.integers(min_value=1, max_value=10))
    def test_low_priority_tasks_queued_during_screenshot_mode(self, task_count: int):
        """Property 11.5: 截图模式时低优先级任务被暂存

        **Validates: Requirements 6.2**

        *For any* number of low-priority tasks submitted during screenshot mode,
        they SHALL be queued (pending) until screenshot mode exits.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )

        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()

        mode_manager.enter_screenshot_mode()

        for i in range(task_count):
            task = BackgroundTask(lambda: None)
            task_manager.submit(task, TaskPriority.LOW)

        assert task_manager.pending_count == task_count, \
            f"Should have {task_count} pending tasks"

        mode_manager.exit_screenshot_mode()
        assert task_manager.pending_count == 0, "Pending tasks should be submitted"

    @settings(max_examples=50, deadline=None)
    @given(task_count=st.integers(min_value=1, max_value=10))
    def test_high_priority_not_queued_during_screenshot_mode(self, task_count: int):
        """Property 11.6: 截图模式时高优先级任务不被暂存

        **Validates: Requirements 6.2**

        *For any* high-priority task submitted during screenshot mode,
        it SHALL NOT be queued but submitted immediately.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )

        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()

        mode_manager.enter_screenshot_mode()

        for i in range(task_count):
            task = BackgroundTask(lambda: None)
            task_manager.submit(task, TaskPriority.HIGH)

        assert task_manager.pending_count == 0, \
            "High-priority tasks should not be pending"

        mode_manager.exit_screenshot_mode()

    @settings(max_examples=50, deadline=None)
    @given(task_count=st.integers(min_value=1, max_value=10))
    def test_cancelled_task_not_submitted(self, task_count: int):
        """Property 11.7: 已取消的任务不被提交

        **Validates: Requirements 6.1**

        *For any* cancelled task, it SHALL NOT be submitted to the thread pool.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )

        manager = BackgroundTaskManager.instance()

        for i in range(task_count):
            task = BackgroundTask(lambda: None)
            task.cancel()
            assert task.is_cancelled
            success = manager.submit(task, TaskPriority.NORMAL)
            assert not success, "Cancelled task should not be submitted"

    @settings(max_examples=100, deadline=None)
    @given(args=task_args_strategy)
    def test_background_task_stores_arguments(self, args: Tuple[int, int]):
        """Property 11.8: BackgroundTask 正确存储参数

        **Validates: Requirements 6.1**

        *For any* task arguments, they SHALL be correctly stored in the task.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import BackgroundTask

        a, b = args

        def add_func(x, y):
            return x + y

        task = BackgroundTask(add_func, a, b)

        assert task.func is add_func
        assert task.args == (a, b)
        assert not task.is_cancelled

    @settings(max_examples=50, deadline=None)
    @given(priorities=st.lists(priority_strategy, min_size=1, max_size=10))
    def test_mixed_priority_submission(self, priorities: List[int]):
        """Property 11.9: 混合优先级任务提交成功

        **Validates: Requirements 6.1, 6.2**

        *For any* mix of task priorities, all tasks SHALL be submitted successfully.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )

        manager = BackgroundTaskManager.instance()

        for priority in priorities:
            priority_enum = TaskPriority(priority)
            task = BackgroundTask(lambda: None)
            success = manager.submit(task, priority_enum)
            assert success, f"Task with priority {priority} should be submitted"



class TestBackgroundTaskManagerIntegrationProperty:
    """后台任务管理器与截图模式管理器集成属性测试

    **Validates: Requirements 6.1, 6.2**
    """

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qapp):
        """每个测试前后重置单例"""
        reset_managers()
        yield
        reset_managers()

    @settings(max_examples=30, deadline=None)
    @given(
        low_count=st.integers(min_value=1, max_value=5),
        high_count=st.integers(min_value=1, max_value=5)
    )
    def test_screenshot_mode_mixed_priority_queuing(
        self, low_count: int, high_count: int
    ):
        """Property 11.10: 截图模式混合优先级任务队列行为

        **Validates: Requirements 6.1, 6.2**

        *For any* combination of low and high priority tasks during
        screenshot mode, only low-priority tasks SHALL be queued.
        """
        reset_managers()
        
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )

        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()

        mode_manager.enter_screenshot_mode()

        # Submit low-priority tasks
        for i in range(low_count):
            task = BackgroundTask(lambda: None)
            task_manager.submit(task, TaskPriority.LOW)

        # Submit high-priority tasks
        for i in range(high_count):
            task = BackgroundTask(lambda: None)
            task_manager.submit(task, TaskPriority.HIGH)

        # Only low-priority tasks should be pending
        assert task_manager.pending_count == low_count, \
            f"Should have {low_count} pending low-priority tasks"

        mode_manager.exit_screenshot_mode()

        # All pending tasks should be submitted
        assert task_manager.pending_count == 0


class TestBackgroundTaskSignalBehavior:
    """后台任务信号行为测试（使用 qtbot）

    **Validates: Requirements 6.1, 6.2**

    这些测试验证任务完成后信号正确发出。
    """

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后重置单例"""
        reset_managers()
        yield
        reset_managers()

    def test_single_task_completes_with_result(self, qtbot):
        """验证单个任务完成并返回正确结果

        **Validates: Requirements 6.1**
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

        manager.submit(task, TaskPriority.NORMAL)
        manager.wait_for_done(2000)
        qtbot.wait(200)

        assert len(result_holder) == 1
        assert result_holder[0] == 42

    def test_task_with_arguments_completes_correctly(self, qtbot):
        """验证带参数的任务正确完成

        **Validates: Requirements 6.1**
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )

        manager = BackgroundTaskManager.instance()
        result_holder = []

        def add_func(a, b):
            return a + b

        task = BackgroundTask(add_func, 10, 20)
        task.signals.finished.connect(lambda r: result_holder.append(r))

        manager.submit(task, TaskPriority.NORMAL)
        manager.wait_for_done(2000)
        qtbot.wait(200)

        assert len(result_holder) == 1
        assert result_holder[0] == 30

    def test_task_error_emits_error_signal(self, qtbot):
        """验证任务错误发出错误信号

        **Validates: Requirements 6.1**
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )

        manager = BackgroundTaskManager.instance()
        error_holder = []

        def failing_task():
            raise ValueError("Test error")

        task = BackgroundTask(failing_task)
        task.signals.error.connect(lambda e: error_holder.append(e))

        manager.submit(task, TaskPriority.NORMAL)
        manager.wait_for_done(2000)
        qtbot.wait(200)

        assert len(error_holder) == 1
        assert "Test error" in error_holder[0]

    def test_multiple_tasks_complete_sequentially(self, qtbot):
        """验证多个任务顺序完成

        **Validates: Requirements 6.1**
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )

        manager = BackgroundTaskManager.instance()
        results = []

        # Submit tasks one at a time and wait for each
        for i in range(3):
            result_holder = []
            
            def task_func(x=i):
                return x * 2
            
            task = BackgroundTask(task_func)
            task.signals.finished.connect(lambda r: result_holder.append(r))
            
            manager.submit(task, TaskPriority.NORMAL)
            manager.wait_for_done(2000)
            qtbot.wait(200)
            
            if result_holder:
                results.append(result_holder[0])

        assert len(results) == 3
        assert set(results) == {0, 2, 4}

    def test_low_priority_tasks_resume_after_screenshot_mode(self, qtbot):
        """验证截图模式退出后低优先级任务恢复执行

        **Validates: Requirements 6.2**
        """
        from screenshot_tool.core.background_task_manager import (
            BackgroundTaskManager, BackgroundTask, TaskPriority
        )
        from screenshot_tool.core.screenshot_mode_manager import (
            ScreenshotModeManager
        )

        task_manager = BackgroundTaskManager.instance()
        mode_manager = ScreenshotModeManager.instance()
        result_holder = []

        mode_manager.enter_screenshot_mode()

        def task_func():
            return "completed"

        task = BackgroundTask(task_func)
        task.signals.finished.connect(lambda r: result_holder.append(r))
        task_manager.submit(task, TaskPriority.LOW)

        # Task should be pending
        assert task_manager.pending_count == 1
        assert len(result_holder) == 0

        # Exit screenshot mode
        mode_manager.exit_screenshot_mode()

        # Wait for task to complete
        task_manager.wait_for_done(2000)
        qtbot.wait(200)

        assert len(result_holder) == 1
        assert result_holder[0] == "completed"
