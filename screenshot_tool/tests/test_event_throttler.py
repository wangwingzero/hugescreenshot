# -*- coding: utf-8 -*-
"""
事件节流器和信号防抖器测试

Feature: extreme-performance-optimization
Requirements: 10.1, 10.2

测试内容：
1. EventThrottler 节流功能
2. SignalDebouncer 防抖功能
3. 便捷函数
4. 边界情况
"""

import pytest
import time
from unittest.mock import MagicMock


class TestEventThrottler:
    """事件节流器测试"""
    
    def test_basic_throttle(self, qtbot):
        """测试基本节流功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=50)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        throttler.throttle(callback, 1)
        throttler.throttle(callback, 2)
        throttler.throttle(callback, 3)
        
        # 等待节流器执行
        qtbot.wait(100)
        
        # 只有最后一次调用应该被执行
        assert len(result_holder) == 1
        assert result_holder[0] == 3
    
    def test_default_interval_is_16ms(self):
        """测试默认间隔为 16ms (60 FPS)
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler()
        
        assert throttler.interval == 16
        assert throttler.DEFAULT_INTERVAL_MS == 16
    
    def test_custom_interval(self):
        """测试自定义间隔
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=100)
        
        assert throttler.interval == 100
    
    def test_interval_setter(self):
        """测试间隔设置器
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=16)
        throttler.interval = 32
        
        assert throttler.interval == 32
    
    def test_interval_setter_validation(self):
        """测试间隔设置器验证
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler()
        
        with pytest.raises(ValueError):
            throttler.interval = 0
        
        with pytest.raises(ValueError):
            throttler.interval = -1
    
    def test_is_pending(self, qtbot):
        """测试 is_pending 属性
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=100)
        
        assert not throttler.is_pending
        
        throttler.throttle(lambda: None)
        
        assert throttler.is_pending
        
        # 等待执行完成
        qtbot.wait(150)
        
        assert not throttler.is_pending
    
    def test_cancel(self, qtbot):
        """测试取消功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=100)
        
        result_holder = []
        
        throttler.throttle(lambda: result_holder.append(1))
        
        assert throttler.is_pending
        
        throttler.cancel()
        
        assert not throttler.is_pending
        
        # 等待确保回调不会执行
        qtbot.wait(150)
        
        assert len(result_holder) == 0
    
    def test_flush(self, qtbot):
        """测试立即执行功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=1000)  # 长间隔
        
        result_holder = []
        
        throttler.throttle(lambda: result_holder.append(1))
        
        assert throttler.is_pending
        assert len(result_holder) == 0
        
        # 立即执行
        throttler.flush()
        
        assert not throttler.is_pending
        assert len(result_holder) == 1
    
    def test_callback_with_args_and_kwargs(self, qtbot):
        """测试带参数的回调
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=50)
        
        result_holder = []
        
        def callback(a, b, c=None):
            result_holder.append((a, b, c))
        
        throttler.throttle(callback, 1, 2, c=3)
        
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == (1, 2, 3)
    
    def test_statistics(self, qtbot):
        """测试统计信息
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=50)
        
        assert throttler.throttled_count == 0
        assert throttler.executed_count == 0
        
        # 快速调用多次
        throttler.throttle(lambda: None)
        throttler.throttle(lambda: None)
        throttler.throttle(lambda: None)
        
        # 等待执行
        qtbot.wait(100)
        
        # 2 次被节流，1 次执行
        assert throttler.throttled_count == 2
        assert throttler.executed_count == 1
    
    def test_reset_stats(self, qtbot):
        """测试重置统计信息
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=50)
        
        throttler.throttle(lambda: None)
        throttler.throttle(lambda: None)
        
        qtbot.wait(100)
        
        assert throttler.throttled_count > 0 or throttler.executed_count > 0
        
        throttler.reset_stats()
        
        assert throttler.throttled_count == 0
        assert throttler.executed_count == 0
    
    def test_callback_exception_handled(self, qtbot):
        """测试回调异常被处理
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=50)
        
        def failing_callback():
            raise ValueError("Test error")
        
        # 不应抛出异常
        throttler.throttle(failing_callback)
        
        qtbot.wait(100)
        
        # 节流器应该继续工作
        assert not throttler.is_pending


class TestSignalDebouncer:
    """信号防抖器测试"""
    
    def test_basic_debounce(self, qtbot):
        """测试基本防抖功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        debouncer.debounce(callback, 1)
        debouncer.debounce(callback, 2)
        debouncer.debounce(callback, 3)
        
        # 等待防抖器执行
        qtbot.wait(100)
        
        # 只有最后一次调用应该被执行
        assert len(result_holder) == 1
        assert result_holder[0] == 3
    
    def test_default_delay_is_200ms(self):
        """测试默认延迟为 200ms
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer()
        
        assert debouncer.delay == 200
        assert debouncer.DEFAULT_DELAY_MS == 200
    
    def test_custom_delay(self):
        """测试自定义延迟
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=500)
        
        assert debouncer.delay == 500
    
    def test_delay_setter(self):
        """测试延迟设置器
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=200)
        debouncer.delay = 300
        
        assert debouncer.delay == 300
    
    def test_delay_setter_validation(self):
        """测试延迟设置器验证
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer()
        
        with pytest.raises(ValueError):
            debouncer.delay = 0
        
        with pytest.raises(ValueError):
            debouncer.delay = -1
    
    def test_is_pending(self, qtbot):
        """测试 is_pending 属性
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=100)
        
        assert not debouncer.is_pending
        
        debouncer.debounce(lambda: None)
        
        assert debouncer.is_pending
        
        # 等待执行完成
        qtbot.wait(150)
        
        assert not debouncer.is_pending
    
    def test_cancel(self, qtbot):
        """测试取消功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=100)
        
        result_holder = []
        
        debouncer.debounce(lambda: result_holder.append(1))
        
        assert debouncer.is_pending
        
        debouncer.cancel()
        
        assert not debouncer.is_pending
        
        # 等待确保回调不会执行
        qtbot.wait(150)
        
        assert len(result_holder) == 0
    
    def test_flush(self, qtbot):
        """测试立即执行功能
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=1000)  # 长延迟
        
        result_holder = []
        
        debouncer.debounce(lambda: result_holder.append(1))
        
        assert debouncer.is_pending
        assert len(result_holder) == 0
        
        # 立即执行
        debouncer.flush()
        
        assert not debouncer.is_pending
        assert len(result_holder) == 1
    
    def test_debounce_resets_timer(self, qtbot):
        """测试防抖重置计时器
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        
        每次调用 debounce 应该重置计时器。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=100)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 第一次调用
        debouncer.debounce(callback, 1)
        
        # 等待 50ms（不到延迟时间）
        qtbot.wait(50)
        
        # 第二次调用，应该重置计时器
        debouncer.debounce(callback, 2)
        
        # 再等待 50ms（从第一次调用算起已经 100ms）
        qtbot.wait(50)
        
        # 此时不应该执行，因为计时器被重置了
        assert len(result_holder) == 0
        
        # 再等待 100ms
        qtbot.wait(100)
        
        # 现在应该执行了
        assert len(result_holder) == 1
        assert result_holder[0] == 2
    
    def test_callback_with_args_and_kwargs(self, qtbot):
        """测试带参数的回调
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        result_holder = []
        
        def callback(a, b, c=None):
            result_holder.append((a, b, c))
        
        debouncer.debounce(callback, 1, 2, c=3)
        
        qtbot.wait(100)
        
        assert len(result_holder) == 1
        assert result_holder[0] == (1, 2, 3)
    
    def test_statistics(self, qtbot):
        """测试统计信息
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        assert debouncer.debounced_count == 0
        assert debouncer.executed_count == 0
        
        # 快速调用多次
        debouncer.debounce(lambda: None)
        debouncer.debounce(lambda: None)
        debouncer.debounce(lambda: None)
        
        # 等待执行
        qtbot.wait(100)
        
        # 2 次被防抖，1 次执行
        assert debouncer.debounced_count == 2
        assert debouncer.executed_count == 1
    
    def test_reset_stats(self, qtbot):
        """测试重置统计信息
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        debouncer.debounce(lambda: None)
        debouncer.debounce(lambda: None)
        
        qtbot.wait(100)
        
        assert debouncer.debounced_count > 0 or debouncer.executed_count > 0
        
        debouncer.reset_stats()
        
        assert debouncer.debounced_count == 0
        assert debouncer.executed_count == 0
    
    def test_callback_exception_handled(self, qtbot):
        """测试回调异常被处理
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        def failing_callback():
            raise ValueError("Test error")
        
        # 不应抛出异常
        debouncer.debounce(failing_callback)
        
        qtbot.wait(100)
        
        # 防抖器应该继续工作
        assert not debouncer.is_pending


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_create_mouse_throttler(self):
        """测试创建鼠标事件节流器
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import create_mouse_throttler
        
        throttler = create_mouse_throttler()
        
        assert throttler.interval == 16  # 60 FPS
    
    def test_create_scroll_throttler(self):
        """测试创建滚动事件节流器
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import create_scroll_throttler
        
        throttler = create_scroll_throttler()
        
        assert throttler.interval == 16  # 60 FPS
    
    def test_create_resize_throttler(self):
        """测试创建窗口大小调整节流器
        
        Feature: extreme-performance-optimization
        Requirements: 10.1
        """
        from screenshot_tool.core.event_throttler import create_resize_throttler
        
        throttler = create_resize_throttler()
        
        assert throttler.interval == 33  # 30 FPS
    
    def test_create_search_debouncer(self):
        """测试创建搜索输入防抖器
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import create_search_debouncer
        
        debouncer = create_search_debouncer()
        
        assert debouncer.delay == 300
    
    def test_create_history_update_debouncer(self):
        """测试创建历史更新防抖器
        
        Feature: extreme-performance-optimization
        Requirements: 10.2
        """
        from screenshot_tool.core.event_throttler import (
            create_history_update_debouncer
        )
        
        debouncer = create_history_update_debouncer()
        
        assert debouncer.delay == 200


class TestThrottlerVsDebouncer:
    """节流器与防抖器对比测试"""
    
    def test_throttler_executes_during_burst(self, qtbot):
        """测试节流器在连续调用期间会执行
        
        Feature: extreme-performance-optimization
        Requirements: 10.1, 10.2
        
        节流器在间隔到达时执行，即使还有新调用。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=30)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 第一次调用
        throttler.throttle(callback, 1)
        
        # 等待间隔时间
        qtbot.wait(50)
        
        # 第一次应该已执行
        assert len(result_holder) == 1
        
        # 继续调用
        throttler.throttle(callback, 2)
        
        qtbot.wait(50)
        
        # 第二次也应该执行
        assert len(result_holder) == 2
    
    def test_debouncer_waits_for_silence(self, qtbot):
        """测试防抖器等待活动停止
        
        Feature: extreme-performance-optimization
        Requirements: 10.1, 10.2
        
        防抖器只有在活动停止后才执行。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=50)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 连续调用，每次间隔小于延迟时间
        for i in range(5):
            debouncer.debounce(callback, i)
            qtbot.wait(20)  # 20ms < 50ms 延迟
        
        # 此时不应该执行
        assert len(result_holder) == 0
        
        # 等待延迟时间
        qtbot.wait(100)
        
        # 只有最后一次调用被执行
        assert len(result_holder) == 1
        assert result_holder[0] == 4

