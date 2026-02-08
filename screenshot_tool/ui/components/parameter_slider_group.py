# =====================================================
# =============== 参数滑块组件 ===============
# =====================================================

"""
参数滑块组件，包含标签、滑块和数值输入框。

支持整数和浮点数两种模式，滑块与 SpinBox 双向同步。

Feature: mouse-highlight-debug-panel
Requirements: 2.4, 2.5, 5.1-5.7
"""

from typing import Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QSlider, QSpinBox, QDoubleSpinBox
)


class ParameterSliderGroup(QWidget):
    """参数滑块组件
    
    包含：标签 + 滑块 + SpinBox
    支持整数和浮点数两种模式。
    
    PySide6 信号使用：
    - QSlider.valueChanged(int): 滑块值变化时触发
    - QSpinBox.valueChanged(int): 数值框值变化时触发
    - QDoubleSpinBox.valueChanged(float): 浮点数值框值变化时触发
    
    同步机制：
    - 使用 blockSignals() 防止循环触发
    - 滑块变化 -> 更新 SpinBox（阻塞信号）-> 发射 value_changed
    - SpinBox 变化 -> 更新滑块（阻塞信号）-> 发射 value_changed
    
    Feature: mouse-highlight-debug-panel
    Requirements: 2.4, 2.5, 5.1-5.7
    """
    
    # 值变化信号
    value_changed = Signal(object)
    
    def __init__(
        self,
        label: str,
        min_val: float,
        max_val: float,
        default_val: float,
        suffix: str = "",
        is_float: bool = False,
        decimals: int = 1,
        parent: Optional[QWidget] = None
    ):
        """初始化参数滑块组件
        
        Args:
            label: 参数标签文字
            min_val: 最小值
            max_val: 最大值
            default_val: 默认值
            suffix: 后缀文字（如 "px", "%", "ms"）
            is_float: 是否为浮点数模式
            decimals: 浮点数小数位数
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._is_float = is_float
        self._decimals = decimals
        self._min_val = min_val
        self._max_val = max_val
        self._multiplier = 10 ** decimals if is_float else 1
        
        # 创建布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 标签
        self._label = QLabel(label)
        self._label.setMinimumWidth(60)
        layout.addWidget(self._label)
        
        # 滑块
        self._slider = QSlider(Qt.Orientation.Horizontal)
        if is_float:
            # 浮点数模式：滑块使用整数，乘以 10^decimals
            self._slider.setRange(
                int(min_val * self._multiplier),
                int(max_val * self._multiplier)
            )
            self._slider.setValue(int(default_val * self._multiplier))
        else:
            self._slider.setRange(int(min_val), int(max_val))
            self._slider.setValue(int(default_val))
        layout.addWidget(self._slider, 1)
        
        # 数值框
        if is_float:
            self._spinbox: Union[QSpinBox, QDoubleSpinBox] = QDoubleSpinBox()
            self._spinbox.setDecimals(decimals)
            self._spinbox.setRange(min_val, max_val)
            self._spinbox.setValue(default_val)
            self._spinbox.setSingleStep(0.1)
        else:
            self._spinbox = QSpinBox()
            self._spinbox.setRange(int(min_val), int(max_val))
            self._spinbox.setValue(int(default_val))
        
        self._spinbox.setSuffix(f" {suffix}" if suffix else "")
        self._spinbox.setMinimumWidth(80)
        layout.addWidget(self._spinbox)
        
        # 连接信号
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
    
    def _on_slider_changed(self, value: int):
        """滑块值变化"""
        # 阻塞 SpinBox 信号防止循环
        self._spinbox.blockSignals(True)
        if self._is_float:
            self._spinbox.setValue(value / self._multiplier)
        else:
            self._spinbox.setValue(value)
        self._spinbox.blockSignals(False)
        
        self.value_changed.emit(self.value())
    
    def _on_spinbox_changed(self, value: float):
        """数值框值变化"""
        # 阻塞滑块信号防止循环
        self._slider.blockSignals(True)
        if self._is_float:
            self._slider.setValue(int(value * self._multiplier))
        else:
            self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        
        self.value_changed.emit(self.value())
    
    def value(self) -> float:
        """获取当前值"""
        return self._spinbox.value()
    
    def set_value(self, value: float):
        """设置值（不触发信号）
        
        Args:
            value: 要设置的值，会被限制在有效范围内
        """
        # 限制在有效范围内
        clamped = max(self._min_val, min(self._max_val, value))
        
        self._slider.blockSignals(True)
        self._spinbox.blockSignals(True)
        
        if self._is_float:
            self._slider.setValue(int(clamped * self._multiplier))
            self._spinbox.setValue(clamped)
        else:
            self._slider.setValue(int(clamped))
            self._spinbox.setValue(int(clamped))
        
        self._slider.blockSignals(False)
        self._spinbox.blockSignals(False)
    
    def setEnabled(self, enabled: bool):
        """设置启用状态
        
        禁用时控件变灰，但仍可见。
        """
        super().setEnabled(enabled)
        self._label.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._spinbox.setEnabled(enabled)
    
    @property
    def min_value(self) -> float:
        """获取最小值"""
        return self._min_val
    
    @property
    def max_value(self) -> float:
        """获取最大值"""
        return self._max_val
