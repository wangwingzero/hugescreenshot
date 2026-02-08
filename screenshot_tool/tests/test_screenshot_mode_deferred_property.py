# -*- coding: utf-8 -*-
"""
截图模式延迟历史更新属性测试

Feature: extreme-performance-optimization
Task: 3.3 编写集成测试

测试内容：
- Property 18: Screenshot Mode Deferred History Update
- 验证截图期间历史更新被延迟
- 验证进入截图模式时历史更新被暂存
- 验证退出截图模式时所有暂存的更新被处理

**Validates: Requirements 11.9**
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import Mock, MagicMock, patch, call
from typing import List, Callable

from screenshot_tool.core.deferred_history_update import (
    DeferredHistoryUpdate,
    get_deferred_history_update
)


# ============================================================
# Hypothesis 策略定义
# ============================================================

# 生成有效的历史条目 ID
item_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=50
).filter(lambda x: len(x.strip()) > 0)

# 生成历史条目 ID 列表
item_ids_strategy = st.lists(
    item_id_strategy,
    min_size=0,
    max_size=20
)

# 生成回调数量
callback_count_strategy = st.integers(min_value=0, max_value=10)

# 生成截图操作序列（进入/退出模式的次数）
screenshot_operations_strategy = st.integers(min_value=1, max_value=5)


@st.composite
def screenshot_capture_scenario(draw):
    """生成截图捕获场景
    
    包含：
    - 截图期间产生的历史更新数量
    - 截图期间产生的回调数量
    """
    update_count = draw(st.integers(min_value=0, max_value=10))
    callback_count = draw(st.integers(min_value=0, max_value=5))
    item_ids = draw(st.lists(item_id_strategy, min_size=update_count, max_size=update_count))
    
    return {
        "update_count": update_count,
        "callback_count": callback_count,
        "item_ids": item_ids,
    }


# ============================================================
# Property 18: Screenshot Mode Deferred History Update
# Feature: extreme-performance-optimization, Property 18
# Validates: Requirements 11.9
# ============================================================

class TestScreenshotModeDeferredHistoryUpdate:
    """Property 18: 截图模式延迟历史更新测试
    
    验证：对于任意截图捕获操作，history_changed 信号处理应该被延迟，
    直到截图完成后才处理，防止 UI 更新阻塞截图捕获。
    
    **Validates: Requirements 11.9**
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    @given(scenario=screenshot_capture_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_history_updates_deferred_during_capture(self, scenario):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* screenshot capture operation, history_changed signal processing
        SHALL be deferred until capture completes.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 1. 进入截图模式（模拟截图开始）
        manager.enter_deferred_mode()
        assert manager.is_deferred, "截图模式应该激活延迟模式"
        
        # 2. 模拟截图期间产生的历史更新
        queued_count = 0
        for item_id in scenario["item_ids"]:
            result = manager.queue_update(item_id)
            if result:
                queued_count += 1
        
        # 3. 模拟截图期间产生的回调
        callbacks_executed = []
        for i in range(scenario["callback_count"]):
            callback = Mock()
            result = manager.queue_callback(callback)
            if result:
                callbacks_executed.append(callback)
        
        # 4. 验证属性：截图期间更新被暂存，不立即处理
        assert manager.has_pending_updates() or (queued_count == 0 and len(callbacks_executed) == 0), \
            "截图期间应该有暂存的更新（除非没有更新）"
        
        # 5. 验证回调在截图期间未被执行
        for callback in callbacks_executed:
            callback.assert_not_called()
        
        # 6. 退出截图模式（模拟截图完成）
        manager.exit_deferred_mode()
        
        # 7. 验证属性：截图完成后，暂存的更新被处理
        assert not manager.is_deferred, "截图完成后应该退出延迟模式"
        assert not manager.has_pending_updates(), "截图完成后暂存的更新应该被清空"
        
        # 8. 验证回调在截图完成后被执行
        for callback in callbacks_executed:
            callback.assert_called_once()
    
    @given(item_ids=item_ids_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_updates_queued_when_entering_screenshot_mode(self, item_ids):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* set of history updates, when entering screenshot mode,
        all updates SHALL be queued instead of processed immediately.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 进入截图模式
        manager.enter_deferred_mode()
        
        # 尝试添加更新
        queued_ids = set()
        for item_id in item_ids:
            result = manager.queue_update(item_id)
            assert result is True, f"更新 {item_id} 应该被暂存"
            queued_ids.add(item_id)
        
        # 验证属性：所有更新都被暂存
        pending_updates = manager.get_pending_updates()
        assert pending_updates == queued_ids, \
            f"暂存的更新应该与添加的更新一致: expected={queued_ids}, actual={pending_updates}"
        
        # 清理
        manager.exit_deferred_mode()
    
    @given(item_ids=item_ids_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_all_queued_updates_processed_on_exit(self, item_ids):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* set of queued updates, when exiting screenshot mode,
        ALL queued updates SHALL be processed.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 记录恢复回调接收到的更新数量
        resume_counts = []
        def on_resume(count):
            resume_counts.append(count)
        
        manager.register_resume_callback(on_resume)
        
        # 进入截图模式并添加更新
        manager.enter_deferred_mode()
        
        unique_ids = set(item_ids)
        for item_id in item_ids:
            manager.queue_update(item_id)
        
        # 添加一些回调
        callbacks = [Mock() for _ in range(3)]
        for callback in callbacks:
            manager.queue_callback(callback)
        
        expected_pending_count = len(unique_ids) + len(callbacks)
        
        # 退出截图模式
        manager.exit_deferred_mode()
        
        # 验证属性：恢复回调被调用，且参数正确
        assert len(resume_counts) == 1, "恢复回调应该被调用一次"
        assert resume_counts[0] == expected_pending_count, \
            f"恢复回调应该收到正确的暂存更新数量: expected={expected_pending_count}, actual={resume_counts[0]}"
        
        # 验证所有回调都被执行
        for callback in callbacks:
            callback.assert_called_once()
        
        # 验证暂存的更新已清空
        assert not manager.has_pending_updates(), "退出后暂存的更新应该被清空"
    
    @given(operations=screenshot_operations_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_multiple_screenshot_operations_isolated(self, operations):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* sequence of screenshot operations, each operation's updates
        SHALL be isolated and processed independently.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        resume_counts = []
        def on_resume(count):
            resume_counts.append(count)
        
        manager.register_resume_callback(on_resume)
        
        # 执行多次截图操作
        for i in range(operations):
            # 进入截图模式
            manager.enter_deferred_mode()
            
            # 添加一些更新
            for j in range(i + 1):
                manager.queue_update(f"item-{i}-{j}")
            
            # 退出截图模式
            manager.exit_deferred_mode()
            
            # 验证属性：每次操作后暂存的更新都被清空
            assert not manager.has_pending_updates(), \
                f"第 {i+1} 次操作后暂存的更新应该被清空"
        
        # 验证属性：每次操作都触发了恢复回调
        assert len(resume_counts) == operations, \
            f"恢复回调应该被调用 {operations} 次: actual={len(resume_counts)}"
    
    @given(callback_count=callback_count_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_callbacks_not_executed_during_capture(self, callback_count):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* number of callbacks queued during screenshot capture,
        NONE of them SHALL be executed until capture completes.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 进入截图模式
        manager.enter_deferred_mode()
        
        # 添加回调
        callbacks = []
        execution_order = []
        
        for i in range(callback_count):
            def make_callback(index):
                def callback():
                    execution_order.append(index)
                return callback
            
            cb = make_callback(i)
            manager.queue_callback(cb)
            callbacks.append(cb)
        
        # 验证属性：截图期间回调未被执行
        assert len(execution_order) == 0, \
            f"截图期间回调不应该被执行: executed={len(execution_order)}"
        
        # 退出截图模式
        manager.exit_deferred_mode()
        
        # 验证属性：截图完成后所有回调都被执行
        assert len(execution_order) == callback_count, \
            f"截图完成后所有回调应该被执行: expected={callback_count}, actual={len(execution_order)}"
        
        # 验证执行顺序（FIFO）
        assert execution_order == list(range(callback_count)), \
            f"回调应该按添加顺序执行: expected={list(range(callback_count))}, actual={execution_order}"


class TestDeferredHistoryUpdateSignals:
    """延迟历史更新信号测试
    
    验证信号在正确的时机发出。
    
    **Validates: Requirements 11.9**
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    @given(scenario=screenshot_capture_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_signals_emitted_at_correct_times(self, scenario, qtbot):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* screenshot capture operation, updates_deferred signal SHALL be
        emitted when entering screenshot mode, and updates_resumed signal SHALL
        be emitted when exiting screenshot mode.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        deferred_signals = []
        resumed_signals = []
        
        manager.updates_deferred.connect(lambda: deferred_signals.append(True))
        manager.updates_resumed.connect(lambda count: resumed_signals.append(count))
        
        # 进入截图模式
        manager.enter_deferred_mode()
        
        # 验证属性：进入时发出 updates_deferred 信号
        assert len(deferred_signals) == 1, "进入截图模式时应该发出 updates_deferred 信号"
        assert len(resumed_signals) == 0, "进入截图模式时不应该发出 updates_resumed 信号"
        
        # 添加更新
        for item_id in scenario["item_ids"]:
            manager.queue_update(item_id)
        
        for _ in range(scenario["callback_count"]):
            manager.queue_callback(lambda: None)
        
        expected_count = len(set(scenario["item_ids"])) + scenario["callback_count"]
        
        # 退出截图模式
        manager.exit_deferred_mode()
        
        # 验证属性：退出时发出 updates_resumed 信号
        assert len(resumed_signals) == 1, "退出截图模式时应该发出 updates_resumed 信号"
        assert resumed_signals[0] == expected_count, \
            f"updates_resumed 信号应该包含正确的暂存更新数量: expected={expected_count}, actual={resumed_signals[0]}"


class TestDeferredHistoryUpdateIdempotency:
    """延迟历史更新幂等性测试
    
    验证重复操作的幂等性。
    
    **Validates: Requirements 11.9**
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    @given(enter_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_enter_deferred_mode_idempotent(self, enter_count):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* number of consecutive enter_deferred_mode calls,
        the state SHALL remain consistent (only first call has effect).
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        
        # 多次进入延迟模式
        for _ in range(enter_count):
            manager.enter_deferred_mode()
        
        # 验证属性：状态一致
        assert manager.is_deferred, "应该处于延迟模式"
        
        # 验证属性：暂停回调只被调用一次
        pause_callback.assert_called_once()
        
        # 清理
        manager.exit_deferred_mode()
    
    @given(exit_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_exit_deferred_mode_idempotent(self, exit_count):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* number of consecutive exit_deferred_mode calls,
        the state SHALL remain consistent (only first call has effect).
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        
        # 先进入延迟模式
        manager.enter_deferred_mode()
        manager.queue_update("test-item")
        
        # 多次退出延迟模式
        for _ in range(exit_count):
            manager.exit_deferred_mode()
        
        # 验证属性：状态一致
        assert not manager.is_deferred, "应该退出延迟模式"
        
        # 验证属性：恢复回调只被调用一次
        resume_callback.assert_called_once()
    
    @given(item_id=item_id_strategy, repeat_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_duplicate_updates_deduplicated(self, item_id, repeat_count):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* item ID queued multiple times, it SHALL only appear once
        in the pending updates set.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        manager.enter_deferred_mode()
        
        # 多次添加相同的更新
        for _ in range(repeat_count):
            manager.queue_update(item_id)
        
        # 验证属性：更新被去重
        pending_updates = manager.get_pending_updates()
        assert len(pending_updates) == 1, \
            f"重复的更新应该被去重: expected=1, actual={len(pending_updates)}"
        assert item_id in pending_updates, \
            f"暂存的更新应该包含 {item_id}"
        
        # 清理
        manager.exit_deferred_mode()


class TestDeferredHistoryUpdateErrorHandling:
    """延迟历史更新错误处理测试
    
    验证异常情况下的行为。
    
    **Validates: Requirements 11.9**
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    @given(good_callback_count=st.integers(min_value=0, max_value=5))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_callback_exception_does_not_break_flow(self, good_callback_count):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* callback that raises an exception, the exception SHALL NOT
        prevent other callbacks from being executed.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        manager.enter_deferred_mode()
        
        # 添加一个会抛出异常的回调
        def bad_callback():
            raise RuntimeError("Test exception")
        
        manager.queue_callback(bad_callback)
        
        # 添加正常的回调
        good_callbacks = [Mock() for _ in range(good_callback_count)]
        for callback in good_callbacks:
            manager.queue_callback(callback)
        
        # 退出截图模式（不应该抛出异常）
        manager.exit_deferred_mode()
        
        # 验证属性：正常的回调都被执行
        for callback in good_callbacks:
            callback.assert_called_once()
        
        # 验证属性：状态正确
        assert not manager.is_deferred, "应该退出延迟模式"
        assert not manager.has_pending_updates(), "暂存的更新应该被清空"


class TestDeferredHistoryUpdateIntegrationScenarios:
    """延迟历史更新集成场景测试
    
    模拟真实使用场景。
    
    **Validates: Requirements 11.9**
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    @given(
        pre_capture_updates=st.integers(min_value=0, max_value=5),
        during_capture_updates=st.integers(min_value=0, max_value=10),
        post_capture_updates=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_complete_screenshot_workflow(
        self, pre_capture_updates, during_capture_updates, post_capture_updates
    ):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        *For any* complete screenshot workflow (before, during, after capture),
        only updates during capture SHALL be deferred.
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 1. 截图前的更新（不应该被暂存）
        pre_capture_results = []
        for i in range(pre_capture_updates):
            result = manager.queue_update(f"pre-{i}")
            pre_capture_results.append(result)
        
        # 验证属性：截图前的更新不被暂存
        assert all(r is False for r in pre_capture_results), \
            "截图前的更新不应该被暂存"
        
        # 2. 进入截图模式
        manager.enter_deferred_mode()
        
        # 3. 截图期间的更新（应该被暂存）
        during_capture_results = []
        for i in range(during_capture_updates):
            result = manager.queue_update(f"during-{i}")
            during_capture_results.append(result)
        
        # 验证属性：截图期间的更新被暂存
        assert all(r is True for r in during_capture_results), \
            "截图期间的更新应该被暂存"
        
        # 4. 退出截图模式
        manager.exit_deferred_mode()
        
        # 5. 截图后的更新（不应该被暂存）
        post_capture_results = []
        for i in range(post_capture_updates):
            result = manager.queue_update(f"post-{i}")
            post_capture_results.append(result)
        
        # 验证属性：截图后的更新不被暂存
        assert all(r is False for r in post_capture_results), \
            "截图后的更新不应该被暂存"
    
    def test_clipboard_history_window_integration_scenario(self):
        """Feature: extreme-performance-optimization, Property 18: Screenshot Mode Deferred History Update
        
        模拟 ClipboardHistoryWindow 与 DeferredHistoryUpdate 的集成场景。
        
        **Validates: Requirements 11.9**
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 模拟 ClipboardHistoryWindow 的行为
        refresh_calls = []
        pause_calls = []
        
        def on_pause():
            pause_calls.append(True)
        
        def on_resume(count):
            if count > 0:
                refresh_calls.append(count)
        
        manager.register_pause_callback(on_pause)
        manager.register_resume_callback(on_resume)
        
        # 1. 用户打开历史窗口（窗口注册回调）
        # 2. 用户按下截图热键
        manager.enter_deferred_mode()
        
        # 验证：暂停回调被调用
        assert len(pause_calls) == 1, "暂停回调应该被调用"
        
        # 3. 截图期间，剪贴板内容变化触发历史更新
        manager.queue_update("new-screenshot-1")
        manager.queue_callback(lambda: None)  # 模拟 UI 刷新回调
        
        # 4. 用户完成截图
        manager.exit_deferred_mode()
        
        # 验证：恢复回调被调用，且参数正确
        assert len(refresh_calls) == 1, "恢复回调应该被调用"
        assert refresh_calls[0] == 2, "恢复回调应该收到 2 个暂存的更新"
        
        # 5. 历史窗口刷新显示新的截图
        # （由恢复回调触发，这里只验证回调被正确调用）

