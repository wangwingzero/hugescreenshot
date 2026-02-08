# =====================================================
# =============== ParameterSliderGroup 测试 ===============
# =====================================================

"""
ParameterSliderGroup 组件的单元测试和属性测试

Feature: mouse-highlight-debug-panel
Requirements: 2.4, 2.5, 5.1-5.7
"""

import pytest
from hypothesis import given, strategies as st, settings

from PySide6.QtWidgets import QApplication

from screenshot_tool.ui.components.parameter_slider_group import ParameterSliderGroup


@pytest.fixture(scope="module")
def app():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestParameterSliderGroupBasic:
    """ParameterSliderGroup 基础功能测试"""
    
    def test_init_integer_mode(self, app):
        """测试整数模式初始化"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=10,
            max_val=100,
            default_val=50,
            suffix="px"
        )
        
        assert slider.value() == 50
        assert slider.min_value == 10
        assert slider.max_value == 100
    
    def test_init_float_mode(self, app):
        """测试浮点数模式初始化"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=1.0,
            max_val=5.0,
            default_val=2.5,
            suffix="x",
            is_float=True,
            decimals=1
        )
        
        assert abs(slider.value() - 2.5) < 0.01
        assert slider.min_value == 1.0
        assert slider.max_value == 5.0
    
    def test_set_value_integer(self, app):
        """测试整数模式设置值"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=0,
            max_val=100,
            default_val=50
        )
        
        slider.set_value(75)
        assert slider.value() == 75
    
    def test_set_value_float(self, app):
        """测试浮点数模式设置值"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=1.0,
            max_val=5.0,
            default_val=2.0,
            is_float=True,
            decimals=1
        )
        
        slider.set_value(3.5)
        assert abs(slider.value() - 3.5) < 0.01
    
    def test_value_changed_signal(self, app):
        """测试值变化信号"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=0,
            max_val=100,
            default_val=50
        )
        
        received_values = []
        slider.value_changed.connect(lambda v: received_values.append(v))
        
        # 通过滑块改变值
        slider._slider.setValue(75)
        
        assert len(received_values) == 1
        assert received_values[0] == 75
    
    def test_enabled_state(self, app):
        """测试启用/禁用状态"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=0,
            max_val=100,
            default_val=50
        )
        
        slider.setEnabled(False)
        assert not slider.isEnabled()
        assert not slider._slider.isEnabled()
        assert not slider._spinbox.isEnabled()
        
        slider.setEnabled(True)
        assert slider.isEnabled()
        assert slider._slider.isEnabled()
        assert slider._spinbox.isEnabled()


class TestParameterSliderGroupProperty:
    """ParameterSliderGroup 属性测试
    
    Feature: mouse-highlight-debug-panel
    Property 3: 滑块与数值框同步
    Property 6: 参数范围验证
    """
    
    @given(st.integers(min_value=0, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_slider_spinbox_sync_integer(self, app, value):
        """Property 3: 滑块与数值框同步（整数模式）
        
        For any slider value change, the corresponding spinbox 
        SHALL display the same value, and vice versa.
        """
        slider = ParameterSliderGroup(
            label="测试",
            min_val=0,
            max_val=100,
            default_val=50
        )
        
        # 设置滑块值
        slider._slider.setValue(value)
        
        # 验证 SpinBox 同步
        assert slider._spinbox.value() == value
        assert slider.value() == value
    
    @given(st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, deadline=None)
    def test_slider_spinbox_sync_float(self, app, value):
        """Property 3: 滑块与数值框同步（浮点数模式）"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=1.0,
            max_val=5.0,
            default_val=2.0,
            is_float=True,
            decimals=1
        )
        
        # 四舍五入到一位小数
        rounded_value = round(value, 1)
        
        # 设置 SpinBox 值
        slider._spinbox.setValue(rounded_value)
        
        # 验证滑块同步（考虑精度）
        expected_slider_value = int(rounded_value * 10)
        assert slider._slider.value() == expected_slider_value
    
    @given(st.integers(min_value=-100, max_value=200))
    @settings(max_examples=50, deadline=None)
    def test_parameter_range_validation_integer(self, app, value):
        """Property 6: 参数范围验证（整数模式）
        
        For any parameter input, if the value is outside the valid range,
        the system SHALL clamp it to the nearest valid boundary value.
        """
        min_val = 10
        max_val = 100
        
        slider = ParameterSliderGroup(
            label="测试",
            min_val=min_val,
            max_val=max_val,
            default_val=50
        )
        
        # 设置可能超出范围的值
        slider.set_value(value)
        
        # 验证值被限制在有效范围内
        result = slider.value()
        assert min_val <= result <= max_val
        
        # 验证边界情况
        if value < min_val:
            assert result == min_val
        elif value > max_val:
            assert result == max_val
        else:
            assert result == value
    
    @given(st.floats(min_value=-10.0, max_value=20.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, deadline=None)
    def test_parameter_range_validation_float(self, app, value):
        """Property 6: 参数范围验证（浮点数模式）"""
        min_val = 1.0
        max_val = 5.0
        
        slider = ParameterSliderGroup(
            label="测试",
            min_val=min_val,
            max_val=max_val,
            default_val=2.0,
            is_float=True,
            decimals=1
        )
        
        # 设置可能超出范围的值
        slider.set_value(value)
        
        # 验证值被限制在有效范围内
        result = slider.value()
        assert min_val <= result <= max_val
    
    @given(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=30, deadline=None)
    def test_no_circular_signal_emission(self, app, value1, value2):
        """验证不会产生循环信号触发"""
        slider = ParameterSliderGroup(
            label="测试",
            min_val=0,
            max_val=100,
            default_val=50
        )
        
        signal_count = [0]
        slider.value_changed.connect(lambda v: signal_count.__setitem__(0, signal_count[0] + 1))
        
        # 设置滑块值
        slider._slider.setValue(value1)
        count_after_slider = signal_count[0]
        
        # 设置 SpinBox 值
        slider._spinbox.setValue(value2)
        count_after_spinbox = signal_count[0]
        
        # 每次设置应该只触发一次信号（如果值发生变化）
        # Qt 的 valueChanged 只在值实际变化时触发
        expected_slider_signals = 1 if value1 != 50 else 0  # 默认值是 50
        expected_spinbox_signals = 1 if value2 != value1 else 0
        
        assert count_after_slider == expected_slider_signals
        assert count_after_spinbox == expected_slider_signals + expected_spinbox_signals
