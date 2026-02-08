# -*- coding: utf-8 -*-
"""
截图模式管理器测试

Feature: extreme-performance-optimization
Requirements: 11.1, 11.2, 11.3, 12.4

测试 ScreenshotModeManager 类的核心功能：
1. 进入/退出截图模式
2. 暂停/恢复回调注册和触发
3. 与 DeferredHistoryUpdate 的集成
4. 信号发射
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from screenshot_tool.core.screenshot_mode_manager import (
    ScreenshotModeManager,
    get_screenshot_mode_manager
)
from screenshot_tool.core.deferred_history_update import DeferredHistoryUpdate


class TestScreenshotModeManager:
    """ScreenshotModeManager 单元测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
        yield
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
    
    def test_singleton_pattern(self):
        """测试单例模式
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        instance1 = ScreenshotModeManager.instance()
        instance2 = ScreenshotModeManager.instance()
        assert instance1 is instance2
    
    def test_get_screenshot_mode_manager_convenience_function(self):
        """测试便捷函数返回单例
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        instance1 = get_screenshot_mode_manager()
        instance2 = ScreenshotModeManager.instance()
        assert instance1 is instance2
    
    def test_initial_state_not_active(self):
        """测试初始状态不是截图模式
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        assert not manager.is_active
    
    def test_enter_screenshot_mode(self):
        """测试进入截图模式
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        manager.enter_screenshot_mode()
        assert manager.is_active
    
    def test_exit_screenshot_mode(self):
        """测试退出截图模式
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        manager.enter_screenshot_mode()
        manager.exit_screenshot_mode()
        assert not manager.is_active
    
    def test_enter_screenshot_mode_idempotent(self):
        """测试重复进入截图模式是幂等的
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        
        manager.enter_screenshot_mode()
        manager.enter_screenshot_mode()  # 重复调用
        
        assert manager.is_active
        # 回调只应被调用一次
        assert pause_callback.call_count == 1
    
    def test_exit_screenshot_mode_idempotent(self):
        """测试重复退出截图模式是幂等的
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        
        manager.exit_screenshot_mode()  # 未进入就退出
        
        assert not manager.is_active
        # 回调不应被调用
        resume_callback.assert_not_called()
    
    def test_pause_callback_called_on_enter(self):
        """测试进入截图模式时调用暂停回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        
        manager.enter_screenshot_mode()
        
        pause_callback.assert_called_once()
    
    def test_resume_callback_called_on_exit(self):
        """测试退出截图模式时调用恢复回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        
        manager.enter_screenshot_mode()
        manager.exit_screenshot_mode()
        
        resume_callback.assert_called_once()
    
    def test_multiple_pause_callbacks(self):
        """测试多个暂停回调都被调用
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()
        
        manager.register_pause_callback(callback1)
        manager.register_pause_callback(callback2)
        manager.register_pause_callback(callback3)
        
        manager.enter_screenshot_mode()
        
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()
    
    def test_multiple_resume_callbacks(self):
        """测试多个恢复回调都被调用
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()
        
        manager.register_resume_callback(callback1)
        manager.register_resume_callback(callback2)
        manager.register_resume_callback(callback3)
        
        manager.enter_screenshot_mode()
        manager.exit_screenshot_mode()
        
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()
    
    def test_unregister_pause_callback(self):
        """测试取消注册暂停回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        pause_callback = Mock()
        manager.register_pause_callback(pause_callback)
        manager.unregister_pause_callback(pause_callback)
        
        manager.enter_screenshot_mode()
        
        pause_callback.assert_not_called()
    
    def test_unregister_resume_callback(self):
        """测试取消注册恢复回调
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        resume_callback = Mock()
        manager.register_resume_callback(resume_callback)
        manager.unregister_resume_callback(resume_callback)
        
        manager.enter_screenshot_mode()
        manager.exit_screenshot_mode()
        
        resume_callback.assert_not_called()
    
    def test_callback_exception_does_not_break_flow(self):
        """测试回调异常不影响流程
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        def bad_callback():
            raise RuntimeError("Test error")
        
        good_callback = Mock()
        
        manager.register_pause_callback(bad_callback)
        manager.register_pause_callback(good_callback)
        
        # 不应抛出异常
        manager.enter_screenshot_mode()
        
        # 好的回调仍然被调用
        good_callback.assert_called_once()
        assert manager.is_active
    
    def test_resume_callback_exception_does_not_break_flow(self):
        """测试恢复回调异常不影响流程
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        def bad_callback():
            raise RuntimeError("Test error")
        
        good_callback = Mock()
        
        manager.register_resume_callback(bad_callback)
        manager.register_resume_callback(good_callback)
        
        manager.enter_screenshot_mode()
        
        # 不应抛出异常
        manager.exit_screenshot_mode()
        
        # 好的回调仍然被调用
        good_callback.assert_called_once()
        assert not manager.is_active
    
    def test_signals_emitted(self, qtbot):
        """测试信号正确发出
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        entered_signal_received = []
        exited_signal_received = []
        
        manager.mode_entered.connect(lambda: entered_signal_received.append(True))
        manager.mode_exited.connect(lambda: exited_signal_received.append(True))
        
        manager.enter_screenshot_mode()
        manager.exit_screenshot_mode()
        
        assert len(entered_signal_received) == 1
        assert len(exited_signal_received) == 1
    
    def test_get_callback_counts(self):
        """测试获取回调数量
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        assert manager.get_pause_callback_count() >= 0  # 可能有集成回调
        assert manager.get_resume_callback_count() >= 0
        
        callback1 = Mock()
        callback2 = Mock()
        
        initial_pause_count = manager.get_pause_callback_count()
        initial_resume_count = manager.get_resume_callback_count()
        
        manager.register_pause_callback(callback1)
        manager.register_resume_callback(callback2)
        
        assert manager.get_pause_callback_count() == initial_pause_count + 1
        assert manager.get_resume_callback_count() == initial_resume_count + 1
    
    def test_duplicate_callback_registration(self):
        """测试重复注册同一回调只保留一个
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        callback = Mock()
        
        initial_count = manager.get_pause_callback_count()
        
        manager.register_pause_callback(callback)
        manager.register_pause_callback(callback)  # 重复注册
        
        # 使用 Set，所以只保留一个
        assert manager.get_pause_callback_count() == initial_count + 1
        
        manager.enter_screenshot_mode()
        
        # 回调只被调用一次
        callback.assert_called_once()


class TestScreenshotModeManagerDeferredHistoryIntegration:
    """ScreenshotModeManager 与 DeferredHistoryUpdate 集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
        yield
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
    
    def test_integration_with_deferred_history_update(self):
        """测试与 DeferredHistoryUpdate 的集成
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        
        进入截图模式时应自动进入延迟历史更新模式。
        """
        # 先获取 DeferredHistoryUpdate 实例
        deferred_manager = DeferredHistoryUpdate.instance()
        
        # 然后获取 ScreenshotModeManager 实例（会自动集成）
        screenshot_manager = ScreenshotModeManager.instance()
        
        # 初始状态
        assert not deferred_manager.is_deferred
        assert not screenshot_manager.is_active
        
        # 进入截图模式
        screenshot_manager.enter_screenshot_mode()
        
        # DeferredHistoryUpdate 应该也进入延迟模式
        assert deferred_manager.is_deferred
        
        # 退出截图模式
        screenshot_manager.exit_screenshot_mode()
        
        # DeferredHistoryUpdate 应该也退出延迟模式
        assert not deferred_manager.is_deferred
    
    def test_deferred_updates_during_screenshot_mode(self):
        """测试截图模式期间历史更新被延迟
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        """
        deferred_manager = DeferredHistoryUpdate.instance()
        screenshot_manager = ScreenshotModeManager.instance()
        
        # 进入截图模式
        screenshot_manager.enter_screenshot_mode()
        
        # 尝试添加历史更新
        result = deferred_manager.queue_update("item-1")
        assert result is True  # 应该被暂存
        assert deferred_manager.pending_count == 1
        
        # 退出截图模式
        screenshot_manager.exit_screenshot_mode()
        
        # 暂存的更新应该被清空
        assert deferred_manager.pending_count == 0
    
    def test_screenshot_mode_workflow(self):
        """测试完整的截图模式工作流
        
        Feature: extreme-performance-optimization
        Requirements: 11.9, 12.4
        
        模拟截图期间的完整工作流：
        1. 进入截图模式
        2. 历史更新被暂存
        3. 退出截图模式
        4. 暂存的更新被处理
        """
        deferred_manager = DeferredHistoryUpdate.instance()
        screenshot_manager = ScreenshotModeManager.instance()
        
        # 注册恢复回调
        resume_calls = []
        deferred_manager.register_resume_callback(lambda count: resume_calls.append(count))
        
        # 1. 进入截图模式
        screenshot_manager.enter_screenshot_mode()
        assert screenshot_manager.is_active
        assert deferred_manager.is_deferred
        
        # 2. 模拟历史更新（截图期间）
        deferred_manager.queue_update("screenshot-1")
        deferred_manager.queue_update("screenshot-2")
        assert deferred_manager.pending_count == 2
        
        # 3. 退出截图模式
        screenshot_manager.exit_screenshot_mode()
        assert not screenshot_manager.is_active
        assert not deferred_manager.is_deferred
        
        # 4. 验证恢复回调被调用
        assert len(resume_calls) == 1
        assert resume_calls[0] == 2  # 2 个暂存的更新


class TestScreenshotModeManagerEdgeCases:
    """ScreenshotModeManager 边界情况测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
        yield
        ScreenshotModeManager.reset_instance()
        DeferredHistoryUpdate.reset_instance()
    
    def test_unregister_nonexistent_callback(self):
        """测试取消注册不存在的回调不会报错
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        callback = Mock()
        
        # 取消注册一个从未注册的回调
        manager.unregister_pause_callback(callback)
        manager.unregister_resume_callback(callback)
        
        # 不应抛出异常
        assert True
    
    def test_reset_instance_clears_state(self):
        """测试重置实例清空状态
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        callback = Mock()
        manager.register_pause_callback(callback)
        manager.enter_screenshot_mode()
        
        assert manager.is_active
        
        # 重置实例
        ScreenshotModeManager.reset_instance()
        
        # 获取新实例
        new_manager = ScreenshotModeManager.instance()
        
        # 新实例应该是干净的状态
        assert not new_manager.is_active
        # 注意：由于集成，可能有默认的回调
    
    def test_rapid_enter_exit_cycles(self):
        """测试快速进入/退出循环
        
        Feature: extreme-performance-optimization
        Requirements: 12.4
        """
        manager = ScreenshotModeManager.instance()
        
        enter_count = 0
        exit_count = 0
        
        def on_enter():
            nonlocal enter_count
            enter_count += 1
        
        def on_exit():
            nonlocal exit_count
            exit_count += 1
        
        manager.register_pause_callback(on_enter)
        manager.register_resume_callback(on_exit)
        
        # 快速循环 10 次
        for _ in range(10):
            manager.enter_screenshot_mode()
            manager.exit_screenshot_mode()
        
        assert enter_count == 10
        assert exit_count == 10
        assert not manager.is_active
