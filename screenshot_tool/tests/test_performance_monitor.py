"""
PerformanceMonitor 单元测试

Feature: performance-ui-optimization
Requirements: 1.1, 2.1, 2.3, 3.1, 9.1

测试性能监控器的核心功能：
1. measure() 上下文管理器正确记录时间
2. get_average() 返回正确的平均值
3. get_last() 返回最近一次测量值
4. clear() 正确清除指标
5. enable/disable 功能正确工作
6. 阈值检查功能正确工作
"""

import time
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List

from screenshot_tool.core.performance_monitor import (
    PerformanceMonitor,
    PerformanceMetric,
)


# ========== Fixtures ==========

@pytest.fixture(autouse=True)
def reset_monitor():
    """每个测试前后重置 PerformanceMonitor 状态"""
    PerformanceMonitor.reset()
    yield
    PerformanceMonitor.reset()


# ========== PerformanceMetric 数据类测试 ==========

class TestPerformanceMetric:
    """PerformanceMetric 数据类测试"""
    
    def test_metric_creation(self):
        """测试 PerformanceMetric 创建"""
        metric = PerformanceMetric(
            name="test_metric",
            duration_ms=123.45,
        )
        
        assert metric.name == "test_metric"
        assert metric.duration_ms == 123.45
        assert metric.timestamp > 0
    
    def test_metric_with_custom_timestamp(self):
        """测试带自定义时间戳的 PerformanceMetric"""
        custom_time = 1234567890.0
        metric = PerformanceMetric(
            name="test_metric",
            duration_ms=100.0,
            timestamp=custom_time,
        )
        
        assert metric.timestamp == custom_time


# ========== measure() 上下文管理器测试 ==========

class TestMeasureContextManager:
    """measure() 上下文管理器测试
    
    **Validates: Requirements 1.1**
    """
    
    def test_measure_records_time(self):
        """measure() 正确记录执行时间"""
        with PerformanceMonitor.measure("test_operation"):
            time.sleep(0.01)  # 10ms
        
        duration = PerformanceMonitor.get_last("test_operation")
        assert duration is not None
        # 允许一定误差，至少应该 >= 10ms
        assert duration >= 10, f"Duration {duration}ms should be >= 10ms"
    
    def test_measure_records_multiple_times(self):
        """measure() 可以多次记录同一指标"""
        for _ in range(3):
            with PerformanceMonitor.measure("repeated_operation"):
                time.sleep(0.005)  # 5ms
        
        count = PerformanceMonitor.get_count("repeated_operation")
        assert count == 3
    
    def test_measure_records_different_metrics(self):
        """measure() 可以记录不同的指标"""
        with PerformanceMonitor.measure("operation_a"):
            time.sleep(0.005)
        
        with PerformanceMonitor.measure("operation_b"):
            time.sleep(0.01)
        
        assert PerformanceMonitor.get_count("operation_a") == 1
        assert PerformanceMonitor.get_count("operation_b") == 1
        
        # operation_b 应该比 operation_a 耗时更长
        duration_a = PerformanceMonitor.get_last("operation_a")
        duration_b = PerformanceMonitor.get_last("operation_b")
        assert duration_b > duration_a
    
    def test_measure_handles_exception(self):
        """measure() 在异常时仍然记录时间"""
        try:
            with PerformanceMonitor.measure("exception_operation"):
                time.sleep(0.005)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # 即使发生异常，时间也应该被记录
        duration = PerformanceMonitor.get_last("exception_operation")
        assert duration is not None
        assert duration >= 5
    
    def test_measure_disabled_does_not_record(self):
        """禁用时 measure() 不记录数据"""
        PerformanceMonitor.disable()
        
        with PerformanceMonitor.measure("disabled_operation"):
            time.sleep(0.005)
        
        # 禁用时不应记录
        assert PerformanceMonitor.get_last("disabled_operation") is None
        assert PerformanceMonitor.get_count("disabled_operation") == 0
    
    def test_measure_nested_operations(self):
        """measure() 支持嵌套操作"""
        with PerformanceMonitor.measure("outer"):
            time.sleep(0.005)
            with PerformanceMonitor.measure("inner"):
                time.sleep(0.005)
        
        outer_duration = PerformanceMonitor.get_last("outer")
        inner_duration = PerformanceMonitor.get_last("inner")
        
        assert outer_duration is not None
        assert inner_duration is not None
        # 外层应该比内层耗时更长
        assert outer_duration > inner_duration


# ========== get_average() 测试 ==========

class TestGetAverage:
    """get_average() 测试
    
    **Validates: Requirements 1.1**
    """
    
    def test_get_average_returns_none_for_unknown_metric(self):
        """未知指标返回 None"""
        assert PerformanceMonitor.get_average("unknown") is None
    
    def test_get_average_single_sample(self):
        """单个样本的平均值等于该样本"""
        PerformanceMonitor.record("single", 100.0)
        
        avg = PerformanceMonitor.get_average("single")
        assert avg == 100.0
    
    def test_get_average_multiple_samples(self):
        """多个样本的平均值计算正确"""
        PerformanceMonitor.record("multi", 100.0)
        PerformanceMonitor.record("multi", 200.0)
        PerformanceMonitor.record("multi", 300.0)
        
        avg = PerformanceMonitor.get_average("multi")
        assert avg == 200.0  # (100 + 200 + 300) / 3
    
    @settings(max_examples=100)
    @given(values=st.lists(
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=50
    ))
    def test_get_average_property(self, values: List[float]):
        """Property: 平均值等于所有值之和除以数量
        
        **Validates: Requirements 1.1**
        """
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record("prop_test", v)
        
        avg = PerformanceMonitor.get_average("prop_test")
        expected = sum(values) / len(values)
        
        assert avg is not None
        assert abs(avg - expected) < 0.0001, f"Average {avg} != expected {expected}"


# ========== get_last() 测试 ==========

class TestGetLast:
    """get_last() 测试
    
    **Validates: Requirements 1.1**
    """
    
    def test_get_last_returns_none_for_unknown_metric(self):
        """未知指标返回 None"""
        assert PerformanceMonitor.get_last("unknown") is None
    
    def test_get_last_returns_most_recent(self):
        """返回最近一次测量值"""
        PerformanceMonitor.record("last_test", 100.0)
        PerformanceMonitor.record("last_test", 200.0)
        PerformanceMonitor.record("last_test", 300.0)
        
        last = PerformanceMonitor.get_last("last_test")
        assert last == 300.0
    
    @settings(max_examples=100)
    @given(values=st.lists(
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=50
    ))
    def test_get_last_property(self, values: List[float]):
        """Property: get_last 返回最后添加的值
        
        **Validates: Requirements 1.1**
        """
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record("last_prop", v)
        
        last = PerformanceMonitor.get_last("last_prop")
        assert last == values[-1]


# ========== get_min() 和 get_max() 测试 ==========

class TestGetMinMax:
    """get_min() 和 get_max() 测试"""
    
    def test_get_min_returns_none_for_unknown(self):
        """未知指标返回 None"""
        assert PerformanceMonitor.get_min("unknown") is None
    
    def test_get_max_returns_none_for_unknown(self):
        """未知指标返回 None"""
        assert PerformanceMonitor.get_max("unknown") is None
    
    def test_get_min_returns_minimum(self):
        """返回最小值"""
        PerformanceMonitor.record("minmax", 200.0)
        PerformanceMonitor.record("minmax", 100.0)
        PerformanceMonitor.record("minmax", 300.0)
        
        assert PerformanceMonitor.get_min("minmax") == 100.0
    
    def test_get_max_returns_maximum(self):
        """返回最大值"""
        PerformanceMonitor.record("minmax", 200.0)
        PerformanceMonitor.record("minmax", 100.0)
        PerformanceMonitor.record("minmax", 300.0)
        
        assert PerformanceMonitor.get_max("minmax") == 300.0
    
    @settings(max_examples=100)
    @given(values=st.lists(
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=50
    ))
    def test_min_max_property(self, values: List[float]):
        """Property: min <= average <= max
        
        **Validates: Requirements 1.1**
        """
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record("minmax_prop", v)
        
        min_val = PerformanceMonitor.get_min("minmax_prop")
        max_val = PerformanceMonitor.get_max("minmax_prop")
        avg_val = PerformanceMonitor.get_average("minmax_prop")
        
        assert min_val is not None
        assert max_val is not None
        assert avg_val is not None
        # Use small epsilon for floating-point comparison
        epsilon = 1e-10
        assert min_val - epsilon <= avg_val <= max_val + epsilon


# ========== clear() 测试 ==========

class TestClear:
    """clear() 测试
    
    **Validates: Requirements 1.1**
    """
    
    def test_clear_specific_metric(self):
        """清除特定指标"""
        PerformanceMonitor.record("metric_a", 100.0)
        PerformanceMonitor.record("metric_b", 200.0)
        
        PerformanceMonitor.clear("metric_a")
        
        assert PerformanceMonitor.get_last("metric_a") is None
        assert PerformanceMonitor.get_last("metric_b") == 200.0
    
    def test_clear_all_metrics(self):
        """清除所有指标"""
        PerformanceMonitor.record("metric_a", 100.0)
        PerformanceMonitor.record("metric_b", 200.0)
        
        PerformanceMonitor.clear()
        
        assert PerformanceMonitor.get_last("metric_a") is None
        assert PerformanceMonitor.get_last("metric_b") is None
        assert PerformanceMonitor.get_all_names() == []
    
    def test_clear_unknown_metric_does_not_raise(self):
        """清除未知指标不抛出异常"""
        # 不应抛出异常
        PerformanceMonitor.clear("unknown_metric")


# ========== enable/disable 测试 ==========

class TestEnableDisable:
    """enable/disable 功能测试
    
    **Validates: Requirements 1.1**
    """
    
    def test_is_enabled_default_true(self):
        """默认启用"""
        assert PerformanceMonitor.is_enabled() is True
    
    def test_disable_stops_recording(self):
        """禁用后停止记录"""
        PerformanceMonitor.record("before_disable", 100.0)
        
        PerformanceMonitor.disable()
        PerformanceMonitor.record("after_disable", 200.0)
        
        assert PerformanceMonitor.get_last("before_disable") == 100.0
        assert PerformanceMonitor.get_last("after_disable") is None
    
    def test_enable_resumes_recording(self):
        """重新启用后恢复记录"""
        PerformanceMonitor.disable()
        PerformanceMonitor.record("while_disabled", 100.0)
        
        PerformanceMonitor.enable()
        PerformanceMonitor.record("after_enable", 200.0)
        
        assert PerformanceMonitor.get_last("while_disabled") is None
        assert PerformanceMonitor.get_last("after_enable") == 200.0
    
    def test_measure_respects_enabled_state(self):
        """measure() 尊重启用状态"""
        PerformanceMonitor.disable()
        
        with PerformanceMonitor.measure("disabled_measure"):
            time.sleep(0.005)
        
        assert PerformanceMonitor.get_last("disabled_measure") is None
        
        PerformanceMonitor.enable()
        
        with PerformanceMonitor.measure("enabled_measure"):
            time.sleep(0.005)
        
        assert PerformanceMonitor.get_last("enabled_measure") is not None


# ========== 阈值检查测试 ==========

class TestThresholdChecking:
    """阈值检查功能测试
    
    **Validates: Requirements 1.1, 2.1**
    """
    
    def test_exceeds_threshold_returns_false_for_unknown(self):
        """未知指标返回 False"""
        assert PerformanceMonitor.exceeds_threshold("unknown", 100.0) is False
    
    def test_exceeds_threshold_true_when_exceeded(self):
        """超过阈值时返回 True"""
        PerformanceMonitor.record("threshold_test", 150.0)
        
        assert PerformanceMonitor.exceeds_threshold("threshold_test", 100.0) is True
    
    def test_exceeds_threshold_false_when_not_exceeded(self):
        """未超过阈值时返回 False"""
        PerformanceMonitor.record("threshold_test", 50.0)
        
        assert PerformanceMonitor.exceeds_threshold("threshold_test", 100.0) is False
    
    def test_exceeds_threshold_checks_last_value(self):
        """检查最近一次值而非平均值"""
        PerformanceMonitor.record("threshold_last", 50.0)
        PerformanceMonitor.record("threshold_last", 150.0)  # 最后一个值
        
        # 平均值是 100，但最后一个值是 150
        assert PerformanceMonitor.exceeds_threshold("threshold_last", 100.0) is True
    
    def test_average_exceeds_threshold_returns_false_for_unknown(self):
        """未知指标返回 False"""
        assert PerformanceMonitor.average_exceeds_threshold("unknown", 100.0) is False
    
    def test_average_exceeds_threshold_true_when_exceeded(self):
        """平均值超过阈值时返回 True"""
        PerformanceMonitor.record("avg_threshold", 150.0)
        PerformanceMonitor.record("avg_threshold", 250.0)
        # 平均值 = 200
        
        assert PerformanceMonitor.average_exceeds_threshold("avg_threshold", 100.0) is True
    
    def test_average_exceeds_threshold_false_when_not_exceeded(self):
        """平均值未超过阈值时返回 False"""
        PerformanceMonitor.record("avg_threshold", 50.0)
        PerformanceMonitor.record("avg_threshold", 70.0)
        # 平均值 = 60
        
        assert PerformanceMonitor.average_exceeds_threshold("avg_threshold", 100.0) is False


# ========== 样本数量限制测试 ==========

class TestMaxSamples:
    """样本数量限制测试"""
    
    def test_set_max_samples_positive(self):
        """设置正数样本限制"""
        PerformanceMonitor.set_max_samples(50)
        # 不应抛出异常
    
    def test_set_max_samples_zero_raises(self):
        """设置 0 抛出异常"""
        with pytest.raises(ValueError):
            PerformanceMonitor.set_max_samples(0)
    
    def test_set_max_samples_negative_raises(self):
        """设置负数抛出异常"""
        with pytest.raises(ValueError):
            PerformanceMonitor.set_max_samples(-1)
    
    def test_samples_limited_to_max(self):
        """样本数量被限制在最大值"""
        PerformanceMonitor.set_max_samples(5)
        
        for i in range(10):
            PerformanceMonitor.record("limited", float(i))
        
        count = PerformanceMonitor.get_count("limited")
        assert count == 5
        
        # 应该保留最后 5 个值 (5, 6, 7, 8, 9)
        last = PerformanceMonitor.get_last("limited")
        assert last == 9.0


# ========== get_summary() 测试 ==========

class TestGetSummary:
    """get_summary() 测试"""
    
    def test_get_summary_returns_none_for_unknown(self):
        """未知指标返回 None"""
        assert PerformanceMonitor.get_summary("unknown") is None
    
    def test_get_summary_returns_correct_values(self):
        """返回正确的统计摘要"""
        PerformanceMonitor.record("summary_test", 100.0)
        PerformanceMonitor.record("summary_test", 200.0)
        PerformanceMonitor.record("summary_test", 300.0)
        
        summary = PerformanceMonitor.get_summary("summary_test")
        
        assert summary is not None
        assert summary["count"] == 3
        assert summary["average"] == 200.0
        assert summary["min"] == 100.0
        assert summary["max"] == 300.0
        assert summary["last"] == 300.0


# ========== get_all_names() 和 get_all_metrics() 测试 ==========

class TestGetAllMethods:
    """get_all_names() 和 get_all_metrics() 测试"""
    
    def test_get_all_names_empty_initially(self):
        """初始为空"""
        assert PerformanceMonitor.get_all_names() == []
    
    def test_get_all_names_returns_recorded_names(self):
        """返回所有已记录的指标名称"""
        PerformanceMonitor.record("metric_a", 100.0)
        PerformanceMonitor.record("metric_b", 200.0)
        
        names = PerformanceMonitor.get_all_names()
        assert "metric_a" in names
        assert "metric_b" in names
    
    def test_get_all_metrics_returns_copy(self):
        """返回数据的副本"""
        PerformanceMonitor.record("copy_test", 100.0)
        
        metrics1 = PerformanceMonitor.get_all_metrics()
        metrics2 = PerformanceMonitor.get_all_metrics()
        
        # 应该是不同的对象
        assert metrics1 is not metrics2
        assert metrics1["copy_test"] is not metrics2["copy_test"]


# ========== get_metrics() 测试 ==========

class TestGetMetrics:
    """get_metrics() 测试"""
    
    def test_get_metrics_returns_empty_for_unknown(self):
        """未知指标返回空列表"""
        assert PerformanceMonitor.get_metrics("unknown") == []
    
    def test_get_metrics_returns_all_samples(self):
        """返回所有样本"""
        PerformanceMonitor.record("samples_test", 100.0)
        PerformanceMonitor.record("samples_test", 200.0)
        
        metrics = PerformanceMonitor.get_metrics("samples_test")
        
        assert len(metrics) == 2
        assert metrics[0].duration_ms == 100.0
        assert metrics[1].duration_ms == 200.0
    
    def test_get_metrics_returns_copy(self):
        """返回列表的副本"""
        PerformanceMonitor.record("copy_test", 100.0)
        
        metrics1 = PerformanceMonitor.get_metrics("copy_test")
        metrics2 = PerformanceMonitor.get_metrics("copy_test")
        
        assert metrics1 is not metrics2


# ========== reset() 测试 ==========

class TestReset:
    """reset() 测试"""
    
    def test_reset_clears_all_data(self):
        """重置清除所有数据"""
        PerformanceMonitor.record("reset_test", 100.0)
        PerformanceMonitor.disable()
        PerformanceMonitor.set_max_samples(50)
        
        PerformanceMonitor.reset()
        
        assert PerformanceMonitor.get_all_names() == []
        assert PerformanceMonitor.is_enabled() is True


# ========== format_report() 测试 ==========

class TestFormatReport:
    """format_report() 测试"""
    
    def test_format_report_empty(self):
        """空数据时的报告"""
        report = PerformanceMonitor.format_report()
        assert "No performance metrics recorded" in report
    
    def test_format_report_with_data(self):
        """有数据时的报告"""
        PerformanceMonitor.record("report_test", 100.0)
        PerformanceMonitor.record("report_test", 200.0)
        
        report = PerformanceMonitor.format_report()
        
        assert "Performance Report" in report
        assert "report_test" in report
        assert "Average" in report
        assert "Min" in report
        assert "Max" in report


# ========== 属性测试 ==========

class TestPerformanceMonitorProperties:
    """PerformanceMonitor 属性测试
    
    Feature: performance-ui-optimization
    **Validates: Requirements 1.1**
    """
    
    @settings(max_examples=100)
    @given(
        metric_name=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('L', 'N'),
            whitelist_characters='_-'
        )),
        values=st.lists(
            st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=20
        )
    )
    def test_count_equals_recorded_values(self, metric_name: str, values: List[float]):
        """Property: 记录的样本数量等于 get_count 返回值
        
        **Validates: Requirements 1.1**
        """
        assume(len(metric_name.strip()) > 0)
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record(metric_name, v)
        
        count = PerformanceMonitor.get_count(metric_name)
        assert count == len(values)
    
    @settings(max_examples=100)
    @given(
        values=st.lists(
            st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=20
        )
    )
    def test_min_less_than_or_equal_max(self, values: List[float]):
        """Property: min <= max 始终成立
        
        **Validates: Requirements 1.1**
        """
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record("minmax_prop", v)
        
        min_val = PerformanceMonitor.get_min("minmax_prop")
        max_val = PerformanceMonitor.get_max("minmax_prop")
        
        assert min_val is not None
        assert max_val is not None
        assert min_val <= max_val
    
    @settings(max_examples=100)
    @given(
        values=st.lists(
            st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=20
        )
    )
    def test_last_equals_final_recorded_value(self, values: List[float]):
        """Property: get_last 返回最后记录的值
        
        **Validates: Requirements 1.1**
        """
        PerformanceMonitor.reset()
        
        for v in values:
            PerformanceMonitor.record("last_prop", v)
        
        last = PerformanceMonitor.get_last("last_prop")
        assert last == values[-1]
    
    @settings(max_examples=100)
    @given(
        threshold=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        value=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_exceeds_threshold_consistency(self, threshold: float, value: float):
        """Property: exceeds_threshold 与手动比较一致
        
        **Validates: Requirements 1.1, 2.1**
        """
        PerformanceMonitor.reset()
        PerformanceMonitor.record("threshold_prop", value)
        
        result = PerformanceMonitor.exceeds_threshold("threshold_prop", threshold)
        expected = value > threshold
        
        assert result == expected


# ========== 边界情况测试 ==========

class TestEdgeCases:
    """边界情况测试"""
    
    def test_very_small_duration(self):
        """非常小的持续时间"""
        PerformanceMonitor.record("tiny", 0.001)
        
        assert PerformanceMonitor.get_last("tiny") == 0.001
    
    def test_very_large_duration(self):
        """非常大的持续时间"""
        PerformanceMonitor.record("huge", 1000000.0)
        
        assert PerformanceMonitor.get_last("huge") == 1000000.0
    
    def test_zero_duration(self):
        """零持续时间"""
        PerformanceMonitor.record("zero", 0.0)
        
        assert PerformanceMonitor.get_last("zero") == 0.0
    
    def test_special_characters_in_name(self):
        """指标名称包含特殊字符"""
        PerformanceMonitor.record("metric-with_special.chars:123", 100.0)
        
        assert PerformanceMonitor.get_last("metric-with_special.chars:123") == 100.0
    
    def test_unicode_metric_name(self):
        """Unicode 指标名称"""
        PerformanceMonitor.record("指标名称", 100.0)
        
        assert PerformanceMonitor.get_last("指标名称") == 100.0
    
    def test_empty_string_metric_name(self):
        """空字符串指标名称"""
        PerformanceMonitor.record("", 100.0)
        
        assert PerformanceMonitor.get_last("") == 100.0
