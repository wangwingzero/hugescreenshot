# =====================================================
# =============== SuccessIndicator 测试 ===============
# =====================================================

"""
SuccessIndicator 组件的单元测试

Feature: performance-ui-optimization
Requirements: 7.3, 7.4
"""

import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from screenshot_tool.ui.components.success_indicator import (
    SuccessIndicator,
    IndicatorState,
)
from screenshot_tool.ui.styles import AnimationConstants


@pytest.fixture(scope="module")
def app():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestSuccessIndicatorBasic:
    """SuccessIndicator 基础功能测试"""
    
    def test_init_default(self, app):
        """测试默认初始化"""
        indicator = SuccessIndicator()
        
        assert indicator.state == IndicatorState.IDLE
        assert indicator._size == 32
        assert indicator._auto_hide is True
        assert indicator._auto_hide_delay == 1500
        assert not indicator.isVisible()
    
    def test_init_custom_size(self, app):
        """测试自定义大小初始化"""
        indicator = SuccessIndicator(size=48)
        
        assert indicator._size == 48
        assert indicator.width() == 48
        assert indicator.height() == 48
    
    def test_init_auto_hide_disabled(self, app):
        """测试禁用自动隐藏"""
        indicator = SuccessIndicator(auto_hide=False)
        
        assert indicator._auto_hide is False
    
    def test_init_custom_auto_hide_delay(self, app):
        """测试自定义自动隐藏延迟"""
        indicator = SuccessIndicator(auto_hide_delay=2000)
        
        assert indicator._auto_hide_delay == 2000


class TestSuccessIndicatorShowSuccess:
    """SuccessIndicator 成功动画测试
    
    Requirements: 7.3 - 成功动画持续 200-500ms
    """
    
    def test_show_success_changes_state(self, app):
        """测试 show_success 改变状态"""
        indicator = SuccessIndicator()
        
        indicator.show_success()
        
        assert indicator.state == IndicatorState.SUCCESS
        assert indicator.isVisible()
    
    def test_show_success_resets_progress(self, app):
        """测试 show_success 重置动画进度"""
        indicator = SuccessIndicator()
        indicator._animation_progress = 0.5
        
        indicator.show_success()
        
        assert indicator._animation_progress == 0.0
    
    def test_show_success_starts_animation(self, app):
        """测试 show_success 启动动画"""
        indicator = SuccessIndicator()
        
        indicator.show_success()
        
        # 动画组应该正在运行
        assert indicator._success_animation.state() == indicator._success_animation.State.Running
    
    def test_success_animation_duration_in_range(self, app):
        """测试成功动画时长在 200-500ms 范围内
        
        Requirements: 7.3 - 成功动画持续 200-500ms
        """
        indicator = SuccessIndicator()
        
        # 计算总动画时长
        total_duration = indicator._success_animation.duration()
        
        # 验证时长在 200-500ms 范围内
        assert 200 <= total_duration <= 500, f"动画时长 {total_duration}ms 不在 200-500ms 范围内"


class TestSuccessIndicatorShowError:
    """SuccessIndicator 错误动画测试
    
    Requirements: 7.4 - 错误时显示 subtle shake 动画
    """
    
    def test_show_error_changes_state(self, app):
        """测试 show_error 改变状态"""
        indicator = SuccessIndicator()
        
        indicator.show_error()
        
        assert indicator.state == IndicatorState.ERROR
        assert indicator.isVisible()
    
    def test_show_error_sets_full_progress(self, app):
        """测试 show_error 设置完整进度（错误图标立即显示）"""
        indicator = SuccessIndicator()
        
        indicator.show_error()
        
        # 错误图标应该立即显示
        assert indicator._animation_progress == 1.0
    
    def test_show_error_starts_animation(self, app):
        """测试 show_error 启动动画"""
        indicator = SuccessIndicator()
        
        indicator.show_error()
        
        # 动画组应该正在运行
        assert indicator._error_animation.state() == indicator._error_animation.State.Running
    
    def test_error_animation_has_shake(self, app):
        """测试错误动画包含 shake 效果
        
        Requirements: 7.4 - subtle shake 动画
        """
        indicator = SuccessIndicator()
        
        # 错误动画应该包含多个子动画（淡入 + shake）
        animation_count = indicator._error_animation.animationCount()
        
        # 至少应该有淡入 + 3次 shake（每次 2 个动画）= 7 个动画
        assert animation_count >= 7, f"错误动画只有 {animation_count} 个子动画，预期至少 7 个"


class TestSuccessIndicatorReset:
    """SuccessIndicator 重置功能测试"""
    
    def test_reset_stops_animations(self, app):
        """测试 reset 停止所有动画"""
        indicator = SuccessIndicator()
        indicator.show_success()
        
        indicator.reset()
        
        assert indicator._success_animation.state() != indicator._success_animation.State.Running
    
    def test_reset_hides_indicator(self, app):
        """测试 reset 隐藏指示器"""
        indicator = SuccessIndicator()
        indicator.show_success()
        
        indicator.reset()
        
        assert not indicator.isVisible()
    
    def test_reset_clears_state(self, app):
        """测试 reset 清除状态"""
        indicator = SuccessIndicator()
        indicator.show_success()
        
        indicator.reset()
        
        assert indicator.state == IndicatorState.IDLE
        assert indicator._animation_progress == 0.0
        assert indicator._shake_offset == 0.0
        assert indicator._opacity == 0.0


class TestSuccessIndicatorAutoHide:
    """SuccessIndicator 自动隐藏功能测试"""
    
    def test_set_auto_hide(self, app):
        """测试设置自动隐藏"""
        indicator = SuccessIndicator(auto_hide=False)
        
        indicator.set_auto_hide(True, delay=2000)
        
        assert indicator._auto_hide is True
        assert indicator._auto_hide_delay == 2000
    
    def test_disable_auto_hide(self, app):
        """测试禁用自动隐藏"""
        indicator = SuccessIndicator(auto_hide=True)
        
        indicator.set_auto_hide(False)
        
        assert indicator._auto_hide is False


class TestSuccessIndicatorReducedMotion:
    """SuccessIndicator reduced-motion 支持测试
    
    Requirements: 8.5 - 尊重系统 reduced-motion 偏好
    """
    
    def test_disable_animations(self, app):
        """测试禁用动画"""
        indicator = SuccessIndicator()
        
        indicator.set_animations_enabled(False)
        
        # 动画时长应该为 0
        assert indicator._success_animation.duration() == 0
        assert indicator._error_animation.duration() == 0
    
    def test_enable_animations(self, app):
        """测试启用动画"""
        indicator = SuccessIndicator()
        indicator.set_animations_enabled(False)
        
        indicator.set_animations_enabled(True)
        
        # 动画时长应该恢复正常
        assert indicator._success_animation.duration() > 0


class TestSuccessIndicatorSignals:
    """SuccessIndicator 信号测试"""
    
    def test_animation_finished_signal_emitted(self, app, qtbot):
        """测试动画完成信号发射"""
        indicator = SuccessIndicator(auto_hide=False)
        
        # 使用 qtbot 等待信号
        with qtbot.waitSignal(indicator.animation_finished, timeout=1000):
            indicator.show_success()


class TestSuccessIndicatorProperties:
    """SuccessIndicator Qt Property 测试"""
    
    def test_animation_progress_property(self, app):
        """测试 animation_progress 属性"""
        indicator = SuccessIndicator()
        
        indicator.set_animation_progress(0.5)
        
        assert indicator.get_animation_progress() == 0.5
        assert indicator._animation_progress == 0.5
    
    def test_shake_offset_property(self, app):
        """测试 shake_offset 属性"""
        indicator = SuccessIndicator()
        
        indicator.set_shake_offset(4.0)
        
        assert indicator.get_shake_offset() == 4.0
        assert indicator._shake_offset == 4.0
    
    def test_opacity_property(self, app):
        """测试 opacity 属性"""
        indicator = SuccessIndicator()
        
        indicator.set_opacity(0.8)
        
        assert indicator.get_opacity() == 0.8
        assert indicator._opacity == 0.8


class TestSuccessIndicatorPainting:
    """SuccessIndicator 绘制测试"""
    
    def test_paint_when_hidden(self, app):
        """测试隐藏时不绘制"""
        indicator = SuccessIndicator()
        indicator._opacity = 0.0
        
        # 不应该抛出异常
        indicator.repaint()
    
    def test_paint_success_state(self, app):
        """测试成功状态绘制"""
        indicator = SuccessIndicator()
        indicator._state = IndicatorState.SUCCESS
        indicator._opacity = 1.0
        indicator._animation_progress = 1.0
        
        # 不应该抛出异常
        indicator.repaint()
    
    def test_paint_error_state(self, app):
        """测试错误状态绘制"""
        indicator = SuccessIndicator()
        indicator._state = IndicatorState.ERROR
        indicator._opacity = 1.0
        indicator._animation_progress = 1.0
        
        # 不应该抛出异常
        indicator.repaint()
    
    def test_paint_with_shake_offset(self, app):
        """测试带 shake 偏移的绘制"""
        indicator = SuccessIndicator()
        indicator._state = IndicatorState.ERROR
        indicator._opacity = 1.0
        indicator._shake_offset = 4.0
        
        # 不应该抛出异常
        indicator.repaint()
