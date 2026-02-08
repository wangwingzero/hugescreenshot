# -*- coding: utf-8 -*-
"""
事件节流器和信号防抖器属性测试

Feature: extreme-performance-optimization
Property 16: Event Throttling

**Validates: Requirements 10.1, 10.2**

测试内容：
1. 高频事件被节流到 60 FPS (16ms)
2. 每个间隔内只处理最后一个事件
3. 防抖延迟执行直到活动停止
4. 统计信息准确

使用 hypothesis 库进行属性测试。
"""

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from typing import List, Tuple


# ============================================================================
# Property 16: Event Throttling
# ============================================================================

class TestEventThrottlerProperties:
    """EventThrottler 属性测试
    
    **Validates: Requirements 10.1, 10.2**
    """
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100),
        interval_ms=st.integers(min_value=1, max_value=100)
    )
    def test_throttled_count_plus_executed_equals_total(
        self,
        event_count: int,
        interval_ms: int,
        qtbot
    ):
        """Property 16.1: 节流统计准确性
        
        **Validates: Requirements 10.1**
        
        对于任意数量的事件调用，throttled_count + executed_count 应该等于
        总调用次数（在定时器触发后）。
        
        这验证了节流器正确跟踪所有事件。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=interval_ms)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            throttler.throttle(callback, i)
        
        # 等待足够长时间确保定时器触发
        qtbot.wait(interval_ms + 50)
        
        # 验证统计准确性
        # 第一次调用启动定时器，后续调用被节流
        # throttled_count = event_count - 1 (第一次不算节流)
        # executed_count = 1 (只执行一次)
        assert throttler.throttled_count == event_count - 1
        assert throttler.executed_count == 1
        assert throttler.throttled_count + throttler.executed_count == event_count
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=2, max_value=50),
        interval_ms=st.integers(min_value=10, max_value=50)
    )
    def test_only_last_event_processed(
        self,
        event_count: int,
        interval_ms: int,
        qtbot
    ):
        """Property 16.2: 只处理最后一个事件
        
        **Validates: Requirements 10.1**
        
        对于任意数量的快速连续事件，只有最后一个事件的参数被处理。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=interval_ms)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次，每次传递不同的值
        for i in range(event_count):
            throttler.throttle(callback, i)
        
        # 等待定时器触发
        qtbot.wait(interval_ms + 50)
        
        # 只有最后一个值被处理
        assert len(result_holder) == 1
        assert result_holder[0] == event_count - 1
    
    @settings(max_examples=50)
    @given(
        interval_ms=st.integers(min_value=10, max_value=100)
    )
    def test_default_interval_is_60fps(
        self,
        interval_ms: int
    ):
        """Property 16.3: 默认间隔为 60 FPS (16ms)
        
        **Validates: Requirements 10.1**
        
        EventThrottler 的默认间隔应该是 16ms，对应 60 FPS。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        # 默认构造
        throttler = EventThrottler()
        
        assert throttler.interval == 16
        assert throttler.DEFAULT_INTERVAL_MS == 16
        
        # 自定义间隔
        custom_throttler = EventThrottler(interval_ms=interval_ms)
        assert custom_throttler.interval == interval_ms
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100)
    )
    def test_cancel_prevents_execution(
        self,
        event_count: int,
        qtbot
    ):
        """Property 16.4: 取消阻止执行
        
        **Validates: Requirements 10.1**
        
        调用 cancel() 后，待处理的回调不会被执行。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=100)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            throttler.throttle(callback, i)
        
        # 取消
        throttler.cancel()
        
        # 等待足够长时间
        qtbot.wait(150)
        
        # 不应该有任何执行
        assert len(result_holder) == 0
        assert not throttler.is_pending
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100)
    )
    def test_flush_executes_immediately(
        self,
        event_count: int,
        qtbot
    ):
        """Property 16.5: flush 立即执行
        
        **Validates: Requirements 10.1**
        
        调用 flush() 后，待处理的回调立即执行。
        """
        from screenshot_tool.core.event_throttler import EventThrottler
        
        throttler = EventThrottler(interval_ms=1000)  # 长间隔
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            throttler.throttle(callback, i)
        
        # 立即执行
        throttler.flush()
        
        # 应该立即执行，只有最后一个值
        assert len(result_holder) == 1
        assert result_holder[0] == event_count - 1
        assert not throttler.is_pending


class TestSignalDebouncerProperties:
    """SignalDebouncer 属性测试
    
    **Validates: Requirements 10.2**
    """
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100),
        delay_ms=st.integers(min_value=10, max_value=100)
    )
    def test_debounced_count_plus_executed_equals_total(
        self,
        event_count: int,
        delay_ms: int,
        qtbot
    ):
        """Property 16.6: 防抖统计准确性
        
        **Validates: Requirements 10.2**
        
        对于任意数量的事件调用，debounced_count + executed_count 应该等于
        总调用次数（在定时器触发后）。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=delay_ms)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            debouncer.debounce(callback, i)
        
        # 等待足够长时间确保定时器触发
        qtbot.wait(delay_ms + 50)
        
        # 验证统计准确性
        # 第一次调用不算防抖，后续调用被防抖
        # debounced_count = event_count - 1
        # executed_count = 1
        assert debouncer.debounced_count == event_count - 1
        assert debouncer.executed_count == 1
        assert debouncer.debounced_count + debouncer.executed_count == event_count
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=2, max_value=50),
        delay_ms=st.integers(min_value=10, max_value=50)
    )
    def test_only_last_event_processed_after_silence(
        self,
        event_count: int,
        delay_ms: int,
        qtbot
    ):
        """Property 16.7: 活动停止后只处理最后一个事件
        
        **Validates: Requirements 10.2**
        
        对于任意数量的快速连续事件，只有最后一个事件的参数被处理。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=delay_ms)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次，每次传递不同的值
        for i in range(event_count):
            debouncer.debounce(callback, i)
        
        # 等待定时器触发
        qtbot.wait(delay_ms + 50)
        
        # 只有最后一个值被处理
        assert len(result_holder) == 1
        assert result_holder[0] == event_count - 1
    
    @settings(max_examples=50)
    @given(
        delay_ms=st.integers(min_value=10, max_value=500)
    )
    def test_default_delay_is_200ms(
        self,
        delay_ms: int
    ):
        """Property 16.8: 默认延迟为 200ms
        
        **Validates: Requirements 10.2**
        
        SignalDebouncer 的默认延迟应该是 200ms。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        # 默认构造
        debouncer = SignalDebouncer()
        
        assert debouncer.delay == 200
        assert debouncer.DEFAULT_DELAY_MS == 200
        
        # 自定义延迟
        custom_debouncer = SignalDebouncer(delay_ms=delay_ms)
        assert custom_debouncer.delay == delay_ms
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100)
    )
    def test_cancel_prevents_execution(
        self,
        event_count: int,
        qtbot
    ):
        """Property 16.9: 取消阻止执行
        
        **Validates: Requirements 10.2**
        
        调用 cancel() 后，待处理的回调不会被执行。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=100)
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            debouncer.debounce(callback, i)
        
        # 取消
        debouncer.cancel()
        
        # 等待足够长时间
        qtbot.wait(150)
        
        # 不应该有任何执行
        assert len(result_holder) == 0
        assert not debouncer.is_pending
    
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=100)
    )
    def test_flush_executes_immediately(
        self,
        event_count: int,
        qtbot
    ):
        """Property 16.10: flush 立即执行
        
        **Validates: Requirements 10.2**
        
        调用 flush() 后，待处理的回调立即执行。
        """
        from screenshot_tool.core.event_throttler import SignalDebouncer
        
        debouncer = SignalDebouncer(delay_ms=1000)  # 长延迟
        
        result_holder = []
        
        def callback(value):
            result_holder.append(value)
        
        # 快速调用多次
        for i in range(event_count):
            debouncer.debounce(callback, i)
        
        # 立即执行
        debouncer.flush()
        
        # 应该立即执行，只有最后一个值
        assert len(result_holder) == 1
        assert result_holder[0] == event_count - 1
        assert not debouncer.is_pending


class TestThrottlerVsDebouncerProperties:
    """节流器与防抖器对比属性测试
    
    **Validates: Requirements 10.1, 10.2**
    """
    
    @settings(max_examples=50)
    @given(
        interval_ms=st.integers(min_value=1, max_value=100)
    )
    def test_interval_must_be_positive(
        self,
        interval_ms: int
    ):
        """Property 16.11: 间隔必须为正数
        
        **Validates: Requirements 10.1, 10.2**
        
        EventThrottler 和 SignalDebouncer 的间隔/延迟必须为正数。
        """
        from screenshot_tool.core.event_throttler import (
            EventThrottler, SignalDebouncer
        )
        
        # 正数间隔应该成功
        throttler = EventThrottler(interval_ms=interval_ms)
        assert throttler.interval == interval_ms
        
        debouncer = SignalDebouncer(delay_ms=interval_ms)
        assert debouncer.delay == interval_ms
    
    @settings(max_examples=50)
    @given(
        invalid_interval=st.integers(max_value=0)
    )
    def test_invalid_interval_raises_error(
        self,
        invalid_interval: int
    ):
        """Property 16.12: 无效间隔抛出错误
        
        **Validates: Requirements 10.1, 10.2**
        
        设置非正数间隔应该抛出 ValueError。
        """
        from screenshot_tool.core.event_throttler import (
            EventThrottler, SignalDebouncer
        )
        
        throttler = EventThrottler()
        debouncer = SignalDebouncer()
        
        with pytest.raises(ValueError):
            throttler.interval = invalid_interval
        
        with pytest.raises(ValueError):
            debouncer.delay = invalid_interval
    
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        args=st.tuples(
            st.integers(),
            st.text(min_size=0, max_size=10),
            st.booleans()
        ),
        kwargs_key=st.sampled_from(["key1", "key2", "key3"]),
        kwargs_value=st.integers()
    )
    def test_args_and_kwargs_preserved(
        self,
        args: Tuple,
        kwargs_key: str,
        kwargs_value: int,
        qtbot
    ):
        """Property 16.13: 参数和关键字参数被保留
        
        **Validates: Requirements 10.1, 10.2**
        
        传递给 throttle/debounce 的参数应该被正确传递给回调。
        """
        from screenshot_tool.core.event_throttler import (
            EventThrottler, SignalDebouncer
        )
        
        throttler = EventThrottler(interval_ms=10)
        debouncer = SignalDebouncer(delay_ms=10)
        
        throttler_result = []
        debouncer_result = []
        
        def throttler_callback(*a, **kw):
            throttler_result.append((a, kw))
        
        def debouncer_callback(*a, **kw):
            debouncer_result.append((a, kw))
        
        kwargs = {kwargs_key: kwargs_value}
        
        throttler.throttle(throttler_callback, *args, **kwargs)
        debouncer.debounce(debouncer_callback, *args, **kwargs)
        
        qtbot.wait(50)
        
        # 验证参数被正确传递
        assert len(throttler_result) == 1
        assert throttler_result[0][0] == args
        assert throttler_result[0][1] == kwargs
        
        assert len(debouncer_result) == 1
        assert debouncer_result[0][0] == args
        assert debouncer_result[0][1] == kwargs
    
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        event_count=st.integers(min_value=1, max_value=50)
    )
    def test_reset_stats_clears_counters(
        self,
        event_count: int,
        qtbot
    ):
        """Property 16.14: 重置统计清除计数器
        
        **Validates: Requirements 10.1, 10.2**
        
        调用 reset_stats() 后，所有计数器应该归零。
        """
        from screenshot_tool.core.event_throttler import (
            EventThrottler, SignalDebouncer
        )
        
        throttler = EventThrottler(interval_ms=10)
        debouncer = SignalDebouncer(delay_ms=10)
        
        # 触发一些事件
        for i in range(event_count):
            throttler.throttle(lambda: None)
            debouncer.debounce(lambda: None)
        
        qtbot.wait(50)
        
        # 验证有统计数据
        assert throttler.throttled_count > 0 or throttler.executed_count > 0
        assert debouncer.debounced_count > 0 or debouncer.executed_count > 0
        
        # 重置
        throttler.reset_stats()
        debouncer.reset_stats()
        
        # 验证计数器归零
        assert throttler.throttled_count == 0
        assert throttler.executed_count == 0
        assert debouncer.debounced_count == 0
        assert debouncer.executed_count == 0


class TestConvenienceFunctionsProperties:
    """便捷函数属性测试
    
    **Validates: Requirements 10.1, 10.2**
    """
    
    def test_mouse_throttler_is_60fps(self):
        """Property 16.15: 鼠标节流器为 60 FPS
        
        **Validates: Requirements 10.1**
        """
        from screenshot_tool.core.event_throttler import create_mouse_throttler
        
        throttler = create_mouse_throttler()
        
        # 60 FPS = 1000ms / 60 ≈ 16.67ms，取整为 16ms
        assert throttler.interval == 16
    
    def test_scroll_throttler_is_60fps(self):
        """Property 16.16: 滚动节流器为 60 FPS
        
        **Validates: Requirements 10.1**
        """
        from screenshot_tool.core.event_throttler import create_scroll_throttler
        
        throttler = create_scroll_throttler()
        
        assert throttler.interval == 16
    
    def test_resize_throttler_is_30fps(self):
        """Property 16.17: 窗口大小调整节流器为 30 FPS
        
        **Validates: Requirements 10.1**
        """
        from screenshot_tool.core.event_throttler import create_resize_throttler
        
        throttler = create_resize_throttler()
        
        # 30 FPS = 1000ms / 30 ≈ 33.33ms，取整为 33ms
        assert throttler.interval == 33
    
    def test_search_debouncer_delay(self):
        """Property 16.18: 搜索防抖器延迟为 300ms
        
        **Validates: Requirements 10.2**
        """
        from screenshot_tool.core.event_throttler import create_search_debouncer
        
        debouncer = create_search_debouncer()
        
        assert debouncer.delay == 300
    
    def test_history_update_debouncer_delay(self):
        """Property 16.19: 历史更新防抖器延迟为 200ms
        
        **Validates: Requirements 10.2**
        """
        from screenshot_tool.core.event_throttler import (
            create_history_update_debouncer
        )
        
        debouncer = create_history_update_debouncer()
        
        assert debouncer.delay == 200
