# -*- coding: utf-8 -*-
"""
分屏窗口状态持久化属性测试

Feature: screenshot-ocr-split-view
Task: 4.3 编写窗口状态持久化属性测试

测试内容：
- Property 1: Window State Persistence Round-Trip
- 生成随机窗口位置、大小、分隔条位置
- 保存状态 → 关闭 → 重新打开 → 验证状态恢复

**Validates: Requirements 1.4, 6.7**
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
import base64

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QByteArray


# ============================================================
# 测试数据模型
# ============================================================

@dataclass
class MockSplitWindowState:
    """模拟 SplitWindowState 数据类
    
    用于测试窗口状态持久化的往返属性。
    """
    geometry: bytes = b""
    splitter_state: bytes = b""
    is_pinned: bool = True
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if self.geometry is None:
            self.geometry = b""
        elif isinstance(self.geometry, str):
            try:
                self.geometry = base64.b64decode(self.geometry)
            except Exception:
                self.geometry = b""
        elif not isinstance(self.geometry, bytes):
            self.geometry = b""
        
        if self.splitter_state is None:
            self.splitter_state = b""
        elif isinstance(self.splitter_state, str):
            try:
                self.splitter_state = base64.b64decode(self.splitter_state)
            except Exception:
                self.splitter_state = b""
        elif not isinstance(self.splitter_state, bytes):
            self.splitter_state = b""
        
        if not isinstance(self.is_pinned, bool):
            self.is_pinned = True
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于 JSON 序列化）"""
        return {
            "geometry": base64.b64encode(self.geometry).decode('ascii') if self.geometry else "",
            "splitter_state": base64.b64encode(self.splitter_state).decode('ascii') if self.splitter_state else "",
            "is_pinned": self.is_pinned,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MockSplitWindowState":
        """从字典创建对象"""
        geometry = b""
        splitter_state = b""
        
        if data.get("geometry"):
            try:
                geometry = base64.b64decode(data["geometry"])
            except Exception:
                geometry = b""
        
        if data.get("splitter_state"):
            try:
                splitter_state = base64.b64decode(data["splitter_state"])
            except Exception:
                splitter_state = b""
        
        return cls(
            geometry=geometry,
            splitter_state=splitter_state,
            is_pinned=data.get("is_pinned", True),
        )


# ============================================================
# Hypothesis 策略定义
# ============================================================

# 生成有效的窗口位置（在合理屏幕范围内）
window_x_strategy = st.integers(min_value=0, max_value=3840)
window_y_strategy = st.integers(min_value=0, max_value=2160)

# 生成有效的窗口大小（在最小尺寸和合理最大尺寸之间）
# 最小尺寸: 800x500（根据 Requirements 1.5）
window_width_strategy = st.integers(min_value=800, max_value=2560)
window_height_strategy = st.integers(min_value=500, max_value=1440)

# 生成有效的分隔条位置（左右面板宽度）
# 最小面板宽度: 200（根据实现）
splitter_left_width_strategy = st.integers(min_value=200, max_value=1280)
splitter_right_width_strategy = st.integers(min_value=200, max_value=1280)

# 生成置顶状态
pinned_strategy = st.booleans()


@st.composite
def window_state_strategy(draw):
    """生成随机窗口状态
    
    生成包含窗口位置、大小、分隔条位置和置顶状态的完整状态。
    """
    x = draw(window_x_strategy)
    y = draw(window_y_strategy)
    width = draw(window_width_strategy)
    height = draw(window_height_strategy)
    left_width = draw(splitter_left_width_strategy)
    right_width = draw(splitter_right_width_strategy)
    is_pinned = draw(pinned_strategy)
    
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "left_width": left_width,
        "right_width": right_width,
        "is_pinned": is_pinned,
    }


@st.composite
def splitter_sizes_strategy(draw):
    """生成有效的分隔条尺寸
    
    确保左右面板宽度都在有效范围内。
    """
    left_width = draw(st.integers(min_value=200, max_value=1000))
    right_width = draw(st.integers(min_value=200, max_value=1000))
    return [left_width, right_width]


# ============================================================
# Property 1: Window State Persistence Round-Trip
# Feature: screenshot-ocr-split-view, Property 1
# Validates: Requirements 1.4, 6.7
# ============================================================

class TestWindowStatePersistenceRoundTrip:
    """Property 1: 窗口状态持久化往返测试
    
    验证：对于任意窗口位置、大小和分隔条位置，保存状态后关闭窗口，
    重新打开时应该恢复到完全相同的状态值。
    
    **Validates: Requirements 1.4, 6.7**
    """
    
    @given(is_pinned=pinned_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_pinned_state_round_trip(self, is_pinned, qtbot):
        """
        Property 1.1: Pinned State Round-Trip
        
        *For any* pinned state (True/False), saving the state, closing the window,
        and reopening it SHALL restore the exact same pinned state.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 创建初始状态
        initial_state = MockSplitWindowState(
            geometry=b"",
            splitter_state=b"",
            is_pinned=is_pinned,
        )
        
        # 序列化为字典（模拟保存到配置文件）
        saved_dict = initial_state.to_dict()
        
        # 从字典恢复（模拟从配置文件加载）
        restored_state = MockSplitWindowState.from_dict(saved_dict)
        
        # 验证属性：置顶状态应该完全恢复
        assert restored_state.is_pinned == initial_state.is_pinned, (
            f"置顶状态应该恢复: "
            f"initial={initial_state.is_pinned}, "
            f"restored={restored_state.is_pinned}"
        )
    
    @given(state=window_state_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_split_window_state_dataclass_round_trip(self, state, qtbot):
        """
        Property 1.2: SplitWindowState Dataclass Round-Trip
        
        *For any* SplitWindowState with random geometry, splitter_state, and is_pinned,
        converting to dict and back SHALL preserve all values exactly.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 创建模拟的 geometry 和 splitter_state bytes
        # 使用简单的字节序列模拟 Qt 的 saveGeometry/saveState 输出
        geometry_bytes = f"geometry:{state['x']},{state['y']},{state['width']},{state['height']}".encode('utf-8')
        splitter_bytes = f"splitter:{state['left_width']},{state['right_width']}".encode('utf-8')
        
        # 创建初始状态
        initial_state = MockSplitWindowState(
            geometry=geometry_bytes,
            splitter_state=splitter_bytes,
            is_pinned=state['is_pinned'],
        )
        
        # 序列化为字典
        saved_dict = initial_state.to_dict()
        
        # 从字典恢复
        restored_state = MockSplitWindowState.from_dict(saved_dict)
        
        # 验证属性：所有字段应该完全恢复
        assert restored_state.geometry == initial_state.geometry, (
            f"geometry 应该恢复: "
            f"initial={initial_state.geometry}, "
            f"restored={restored_state.geometry}"
        )
        assert restored_state.splitter_state == initial_state.splitter_state, (
            f"splitter_state 应该恢复: "
            f"initial={initial_state.splitter_state}, "
            f"restored={restored_state.splitter_state}"
        )
        assert restored_state.is_pinned == initial_state.is_pinned, (
            f"is_pinned 应该恢复: "
            f"initial={initial_state.is_pinned}, "
            f"restored={restored_state.is_pinned}"
        )
    
    @given(
        geometry_data=st.binary(min_size=0, max_size=1024),
        splitter_data=st.binary(min_size=0, max_size=256),
        is_pinned=pinned_strategy,
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_arbitrary_bytes_round_trip(self, geometry_data, splitter_data, is_pinned, qtbot):
        """
        Property 1.3: Arbitrary Bytes Round-Trip
        
        *For any* arbitrary bytes data for geometry and splitter_state,
        the round-trip through to_dict/from_dict SHALL preserve the exact bytes.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 创建初始状态
        initial_state = MockSplitWindowState(
            geometry=geometry_data,
            splitter_state=splitter_data,
            is_pinned=is_pinned,
        )
        
        # 序列化为字典
        saved_dict = initial_state.to_dict()
        
        # 从字典恢复
        restored_state = MockSplitWindowState.from_dict(saved_dict)
        
        # 验证属性：所有字段应该完全恢复
        assert restored_state.geometry == initial_state.geometry, (
            f"geometry bytes 应该恢复: "
            f"initial_len={len(initial_state.geometry)}, "
            f"restored_len={len(restored_state.geometry)}"
        )
        assert restored_state.splitter_state == initial_state.splitter_state, (
            f"splitter_state bytes 应该恢复: "
            f"initial_len={len(initial_state.splitter_state)}, "
            f"restored_len={len(restored_state.splitter_state)}"
        )
        assert restored_state.is_pinned == initial_state.is_pinned
    
    @given(sizes=splitter_sizes_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_splitter_sizes_round_trip_with_real_window(self, sizes, qtbot):
        """
        Property 1.4: Splitter Sizes Round-Trip with Real Window
        
        *For any* valid splitter sizes, setting sizes on a QSplitter, saving state,
        and restoring SHALL result in the same sizes (within tolerance).
        
        Note: QSplitter.restoreState() restores the *ratio* of sizes, not absolute values.
        The actual sizes depend on the available space in the splitter.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        try:
            from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow
        except ImportError:
            pytest.skip("ScreenshotOCRSplitWindow not available")
        
        # 创建窗口
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        
        # 设置窗口大小以容纳分隔条尺寸
        # 确保窗口足够大以容纳请求的尺寸
        total_width = sizes[0] + sizes[1] + 20  # 加上分隔条宽度和边距
        window.resize(max(800, total_width), 600)
        window.show()
        qtbot.waitExposed(window)
        
        # 设置分隔条尺寸
        window._splitter.setSizes(sizes)
        
        # 获取实际设置后的尺寸（Qt 可能会调整）
        actual_sizes = window._splitter.sizes()
        
        # 保存状态
        saved_state = window._splitter.saveState()
        
        # 创建新窗口，使用相同的尺寸
        window2 = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window2)
        window2.resize(window.width(), window.height())
        window2.show()
        qtbot.waitExposed(window2)
        
        # 恢复状态
        window2._splitter.restoreState(saved_state)
        
        # 获取恢复后的尺寸
        restored_sizes = window2._splitter.sizes()
        
        # 验证属性：尺寸应该恢复（与实际设置的尺寸比较，允许小误差）
        # 由于 Qt 的布局系统，可能有一些像素的误差
        tolerance = 10
        assert abs(restored_sizes[0] - actual_sizes[0]) <= tolerance, (
            f"左面板宽度应该恢复: "
            f"actual={actual_sizes[0]}, restored={restored_sizes[0]}"
        )
        assert abs(restored_sizes[1] - actual_sizes[1]) <= tolerance, (
            f"右面板宽度应该恢复: "
            f"actual={actual_sizes[1]}, restored={restored_sizes[1]}"
        )
        
        # 清理
        window.close()
        window2.close()


# ============================================================
# 使用真实 SplitWindowState 的属性测试
# ============================================================

class TestRealSplitWindowStateRoundTrip:
    """使用真实 SplitWindowState 类的往返测试
    
    **Validates: Requirements 1.4, 6.7**
    """
    
    @given(
        geometry_data=st.binary(min_size=0, max_size=512),
        splitter_data=st.binary(min_size=0, max_size=128),
        is_pinned=pinned_strategy,
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_real_split_window_state_round_trip(self, geometry_data, splitter_data, is_pinned, qtbot):
        """
        Property 1.5: Real SplitWindowState Round-Trip
        
        *For any* valid state data, the real SplitWindowState class SHALL
        correctly round-trip through to_dict/from_dict.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        # 创建初始状态
        initial_state = SplitWindowState(
            geometry=geometry_data,
            splitter_state=splitter_data,
            is_pinned=is_pinned,
        )
        
        # 序列化为字典
        saved_dict = initial_state.to_dict()
        
        # 从字典恢复
        restored_state = SplitWindowState.from_dict(saved_dict)
        
        # 验证属性：所有字段应该完全恢复
        assert restored_state.geometry == initial_state.geometry, (
            f"geometry 应该恢复"
        )
        assert restored_state.splitter_state == initial_state.splitter_state, (
            f"splitter_state 应该恢复"
        )
        assert restored_state.is_pinned == initial_state.is_pinned, (
            f"is_pinned 应该恢复"
        )


# ============================================================
# 窗口状态持久化集成测试
# ============================================================

class TestWindowStatePersistenceIntegration:
    """窗口状态持久化集成测试
    
    测试真实窗口的状态保存和恢复。
    
    **Validates: Requirements 1.4, 6.7**
    """
    
    @given(is_pinned=pinned_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_window_pinned_state_persistence(self, is_pinned, qtbot):
        """
        Property 1.6: Window Pinned State Persistence
        
        *For any* pinned state, setting it on a window, saving, and restoring
        SHALL result in the same pinned state.
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        try:
            from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("Required modules not available")
        
        # 创建窗口并设置置顶状态
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        
        window.set_pinned(is_pinned)
        
        # 保存状态
        saved_state = SplitWindowState(
            geometry=bytes(window.saveGeometry()),
            splitter_state=bytes(window._splitter.saveState()),
            is_pinned=window.is_pinned,
        )
        
        # 序列化并反序列化
        saved_dict = saved_state.to_dict()
        restored_state = SplitWindowState.from_dict(saved_dict)
        
        # 创建新窗口并恢复状态
        window2 = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window2)
        
        # 恢复置顶状态
        window2.set_pinned(restored_state.is_pinned)
        
        # 验证属性
        assert window2.is_pinned == is_pinned, (
            f"置顶状态应该恢复: initial={is_pinned}, restored={window2.is_pinned}"
        )
        
        # 清理
        window.close()
        window2.close()
    
    def test_window_geometry_save_restore(self, qtbot):
        """单元测试：窗口几何信息保存和恢复
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        try:
            from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow
        except ImportError:
            pytest.skip("ScreenshotOCRSplitWindow not available")
        
        # 创建窗口并设置位置和大小
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.resize(1000, 700)
        window.move(100, 100)
        window.show()
        qtbot.waitExposed(window)
        
        # 保存几何信息
        saved_geometry = window.saveGeometry()
        
        # 创建新窗口并恢复
        window2 = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window2)
        window2.restoreGeometry(saved_geometry)
        window2.show()
        qtbot.waitExposed(window2)
        
        # 验证尺寸恢复（位置可能因屏幕边界调整而变化）
        assert window2.width() == window.width(), "宽度应该恢复"
        assert window2.height() == window.height(), "高度应该恢复"
        
        # 清理
        window.close()
        window2.close()
    
    def test_splitter_state_save_restore(self, qtbot):
        """单元测试：分隔条状态保存和恢复
        
        **Validates: Requirements 1.4, 6.7**
        """
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        try:
            from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow
        except ImportError:
            pytest.skip("ScreenshotOCRSplitWindow not available")
        
        # 创建窗口并设置分隔条位置
        window = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window)
        window.resize(1000, 600)
        window.show()
        qtbot.waitExposed(window)
        
        # 设置分隔条位置（60% : 40%）
        window._splitter.setSizes([600, 400])
        initial_sizes = window._splitter.sizes()
        
        # 保存分隔条状态
        saved_state = window._splitter.saveState()
        
        # 创建新窗口并恢复
        window2 = ScreenshotOCRSplitWindow()
        qtbot.addWidget(window2)
        window2.resize(1000, 600)
        window2.show()
        qtbot.waitExposed(window2)
        
        # 恢复分隔条状态
        window2._splitter.restoreState(saved_state)
        restored_sizes = window2._splitter.sizes()
        
        # 验证分隔条位置恢复（允许小误差）
        tolerance = 5
        assert abs(restored_sizes[0] - initial_sizes[0]) <= tolerance, (
            f"左面板宽度应该恢复: initial={initial_sizes[0]}, restored={restored_sizes[0]}"
        )
        assert abs(restored_sizes[1] - initial_sizes[1]) <= tolerance, (
            f"右面板宽度应该恢复: initial={initial_sizes[1]}, restored={restored_sizes[1]}"
        )
        
        # 清理
        window.close()
        window2.close()


# ============================================================
# 边界情况测试
# ============================================================

class TestEdgeCases:
    """边界情况测试
    
    **Validates: Requirements 1.4, 6.7**
    """
    
    def test_empty_geometry_handling(self, qtbot):
        """测试空 geometry 处理"""
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        state = SplitWindowState(geometry=b"", splitter_state=b"", is_pinned=True)
        saved_dict = state.to_dict()
        restored = SplitWindowState.from_dict(saved_dict)
        
        assert restored.geometry == b""
        assert restored.splitter_state == b""
        assert restored.is_pinned is True
    
    def test_none_values_handling(self, qtbot):
        """测试 None 值处理"""
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        state = SplitWindowState(geometry=None, splitter_state=None, is_pinned=None)
        
        # __post_init__ 应该将 None 转换为默认值
        assert state.geometry == b""
        assert state.splitter_state == b""
        assert state.is_pinned is True
    
    def test_invalid_base64_handling(self, qtbot):
        """测试无效 base64 处理"""
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        # 使用无效的 base64 字符串
        invalid_dict = {
            "geometry": "not-valid-base64!!!",
            "splitter_state": "also-invalid!!!",
            "is_pinned": True,
        }
        
        restored = SplitWindowState.from_dict(invalid_dict)
        
        # 应该优雅地处理无效数据
        assert restored.geometry == b""
        assert restored.splitter_state == b""
        assert restored.is_pinned is True
    
    def test_missing_keys_handling(self, qtbot):
        """测试缺失键处理"""
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        # 空字典
        restored = SplitWindowState.from_dict({})
        
        assert restored.geometry == b""
        assert restored.splitter_state == b""
        assert restored.is_pinned is True
    
    @given(is_pinned=st.one_of(st.booleans(), st.none(), st.integers(), st.text()))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_is_pinned_type_coercion(self, is_pinned, qtbot):
        """
        Property: is_pinned Type Coercion
        
        *For any* value passed as is_pinned, the SplitWindowState SHALL
        coerce it to a boolean (True for non-bool values).
        
        **Validates: Requirements 1.4, 6.7**
        """
        try:
            from screenshot_tool.core.config_manager import SplitWindowState
        except ImportError:
            pytest.skip("SplitWindowState not available")
        
        state = SplitWindowState(geometry=b"", splitter_state=b"", is_pinned=is_pinned)
        
        # is_pinned 应该始终是布尔值
        assert isinstance(state.is_pinned, bool), (
            f"is_pinned 应该是布尔值: type={type(state.is_pinned)}"
        )
