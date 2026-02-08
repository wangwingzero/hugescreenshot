# -*- coding: utf-8 -*-
"""
延迟历史更新管理器测试

Feature: extreme-performance-optimization
Requirements: 11.9, 12.4

测试 DeferredHistoryUpdate 类的核心功能：
1. 进入/退出延迟模式
2. 暂存更新和回调
3. 恢复时处理暂存的更新
4. 回调注册和触发
"""

import pytest
from unittest.mock import Mock, call

from screenshot_tool.core.deferred_history_update import (
    DeferredHistoryUpdate,
    get_deferred_history_update
)


class TestDeferredHistoryUpdate:
    """DeferredHistoryUpdate 单元测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    def test_singleton_pattern(self):
        """测试单例模式
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        instance1 = DeferredHistoryUpdate.instance()
        instance2 = DeferredHistoryUpdate.instance()
        assert instance1 is instance2
    
    def test_get_deferred_history_update_convenience_function(self):
        """测试便捷函数返回单例
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        instance1 = get_deferred_history_update()
        instance2 = DeferredHistoryUpdate.instance()
        assert instance1 is instance2
    
    def test_initial_state_not_deferred(self):
        """测试初始状态不是延迟模式
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        assert not manager.is_deferred
        assert manager.pending_count == 0
    
    def test_enter_deferred_mode(self):
        """测试进入延迟模式
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        assert manager.is_deferred
    
    def test_exit_deferred_mode(self):
        """测试退出延迟模式
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        manager.exit_deferred_mode()
        assert not manager.is_deferred
    
    def test_enter_deferred_mode_idempotent(self):
        """测试重复进入延迟模式是幂等的
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        manager.enter_deferred_mode()  # 重复调用
        assert manager.is_deferred
    
    def test_exit_deferred_mode_idempotent(self):
        """测试重复退出延迟模式是幂等的
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.exit_deferred_mode()  # 未进入就退出
        assert not manager.is_deferred
    
    def test_queue_update_when_deferred(self):
        """测试延迟模式下暂存更新
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        result = manager.queue_update("item-1")
        
        assert result is True
        assert manager.pending_count == 1
        assert "item-1" in manager.get_pending_updates()
    
    def test_queue_update_when_not_deferred(self):
        """测试非延迟模式下不暂存更新
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        
        result = manager.queue_update("item-1")
        
        assert result is False
        assert manager.pending_count == 0
    
    def test_queue_callback_when_deferred(self):
        """测试延迟模式下暂存回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        callback = Mock()
        result = manager.queue_callback(callback)
        
        assert result is True
        assert manager.pending_count == 1
    
    def test_queue_callback_when_not_deferred(self):
        """测试非延迟模式下不暂存回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        
        callback = Mock()
        result = manager.queue_callback(callback)
        
        assert result is False
        assert manager.pending_count == 0
    
    def test_callbacks_executed_on_exit(self):
        """测试退出延迟模式时执行暂存的回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        callback1 = Mock()
        callback2 = Mock()
        manager.queue_callback(callback1)
        manager.queue_callback(callback2)
        
        manager.exit_deferred_mode()
        
        callback1.assert_called_once()
        callback2.assert_called_once()
    
    def test_pending_updates_cleared_on_exit(self):
        """测试退出延迟模式时清空暂存的更新
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        manager.queue_update("item-1")
        manager.queue_update("item-2")
        
        manager.exit_deferred_mode()
        
        assert manager.pending_count == 0
        assert not manager.has_pending_updates()
    
    def test_pause_callback_called_on_enter(self):
        """测试进入延迟模式时调用暂停回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        
        manager.enter_deferred_mode()
        
        pause_callback.assert_called_once()
    
    def test_resume_callback_called_on_exit(self):
        """测试退出延迟模式时调用恢复回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        
        manager.enter_deferred_mode()
        manager.queue_update("item-1")
        manager.exit_deferred_mode()
        
        resume_callback.assert_called_once_with(1)  # 1 个暂存的更新
    
    def test_unregister_pause_callback(self):
        """测试取消注册暂停回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        manager.unregister_pause_callback(pause_callback)
        
        manager.enter_deferred_mode()
        
        pause_callback.assert_not_called()
    
    def test_unregister_resume_callback(self):
        """测试取消注册恢复回调
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        manager.unregister_resume_callback(resume_callback)
        
        manager.enter_deferred_mode()
        manager.exit_deferred_mode()
        
        resume_callback.assert_not_called()
    
    def test_clear_pending(self):
        """测试清空暂存的更新（不执行）
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        callback = Mock()
        manager.queue_update("item-1")
        manager.queue_callback(callback)
        
        manager.clear_pending()
        
        assert manager.pending_count == 0
        
        # 退出时不应执行已清空的回调
        manager.exit_deferred_mode()
        callback.assert_not_called()
    
    def test_duplicate_updates_deduplicated(self):
        """测试重复的更新 ID 被去重
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        manager.queue_update("item-1")
        manager.queue_update("item-1")  # 重复
        manager.queue_update("item-2")
        
        # 只有 2 个唯一的更新 ID
        assert len(manager.get_pending_updates()) == 2
    
    def test_callback_exception_does_not_break_flow(self):
        """测试回调异常不影响流程
        
        Feature: extreme-performance-optimization
        Requirements: 11.9
        """
        manager = DeferredHistoryUpdate.instance()
        manager.enter_deferred_mode()
        
        def bad_callback():
            raise RuntimeError("Test error")
        
        good_callback = Mock()
        
        manager.queue_callback(bad_callback)
        manager.queue_callback(good_callback)
        
        # 不应抛出异常
        manager.exit_deferred_mode()
        
        # 好的回调仍然被调用
        good_callback.assert_called_once()
    
    def test_signals_emitted(self, qtbot):
        """测试信号正确发出
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        manager = DeferredHistoryUpdate.instance()
        
        deferred_signal_received = []
        resumed_signal_received = []
        
        manager.updates_deferred.connect(lambda: deferred_signal_received.append(True))
        manager.updates_resumed.connect(lambda count: resumed_signal_received.append(count))
        
        manager.enter_deferred_mode()
        manager.queue_update("item-1")
        manager.exit_deferred_mode()
        
        assert len(deferred_signal_received) == 1
        assert len(resumed_signal_received) == 1
        assert resumed_signal_received[0] == 1


class TestDeferredHistoryUpdateIntegration:
    """DeferredHistoryUpdate 集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        DeferredHistoryUpdate.reset_instance()
        yield
        DeferredHistoryUpdate.reset_instance()
    
    def test_screenshot_mode_workflow(self):
        """测试截图模式工作流
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        
        模拟截图期间的完整工作流：
        1. 进入截图模式
        2. 历史更新被暂存
        3. 退出截图模式
        4. 暂存的更新被处理
        """
        manager = DeferredHistoryUpdate.instance()
        
        # 模拟 ClipboardHistoryWindow 的刷新回调
        refresh_calls = []
        def on_resume(count):
            if count > 0:
                refresh_calls.append(count)
        
        manager.register_resume_callback(on_resume)
        
        # 1. 进入截图模式
        manager.enter_deferred_mode()
        assert manager.is_deferred
        
        # 2. 模拟历史更新（截图期间）
        manager.queue_update("screenshot-1")
        manager.queue_callback(lambda: None)
        assert manager.pending_count == 2
        
        # 3. 退出截图模式
        manager.exit_deferred_mode()
        assert not manager.is_deferred
        
        # 4. 验证恢复回调被调用
        assert len(refresh_calls) == 1
        assert refresh_calls[0] == 2  # 2 个暂存的更新
