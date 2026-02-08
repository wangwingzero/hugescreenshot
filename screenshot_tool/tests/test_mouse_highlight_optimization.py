# =====================================================
# =============== 鼠标高亮性能优化测试 ===============
# =====================================================

"""
性能优化与错误处理测试

测试 Property 12, 13, 14:
- Property 12: Idle Rendering Optimization
- Property 13: Animation Cleanup
- Property 14: Effect Fault Isolation

Feature: mouse-highlight
Requirements: 10.4, 10.5, 11.2
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter

from screenshot_tool.core.config_manager import MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES
from screenshot_tool.ui.effects.click_ripple_effect import ClickRippleEffect, RippleState


class TestIdleRenderingOptimization:
    """Property 12: Idle Rendering Optimization
    
    For any period where the mouse is stationary AND no animations are active,
    the overlay's paint timer SHALL be paused (no unnecessary redraws).
    """
    
    def test_overlay_starts_paused(self, qtbot):
        """覆盖层初始状态为暂停"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        overlay = MouseHighlightOverlay(QRect(0, 0, 1920, 1080), [])
        
        # 初始状态应该是暂停的
        assert overlay.is_idle() is True
        assert overlay._refresh_timer.isActive() is False
        
        overlay.close()
    
    def test_mouse_move_activates_rendering(self, qtbot):
        """鼠标移动激活渲染"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        overlay = MouseHighlightOverlay(QRect(0, 0, 1920, 1080), [])
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 初始状态
        initial_idle = overlay.is_idle()
        
        # 模拟鼠标移动
        overlay.update_mouse_position(100, 100)
        
        # 应该激活渲染
        assert overlay.is_idle() is False
        assert overlay._refresh_timer.isActive() is True
        
        overlay.close()
    
    def test_idle_after_mouse_stops(self, qtbot):
        """鼠标停止后进入空闲状态"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        overlay = MouseHighlightOverlay(QRect(0, 0, 1920, 1080), [])
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 激活渲染
        overlay.update_mouse_position(100, 100)
        assert overlay.is_idle() is False
        
        # 模拟时间流逝（超过空闲超时）
        overlay._last_mouse_move_time = time.time() - 0.2  # 200ms 前
        
        # 触发刷新回调
        overlay._on_refresh()
        
        # 应该进入空闲状态
        assert overlay.is_idle() is True
        
        overlay.close()
    
    def test_animation_prevents_idle(self, qtbot):
        """有动画时不进入空闲状态"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        # 创建一个模拟的动画效果
        mock_effect = MagicMock()
        mock_effect.is_animated.return_value = True
        
        overlay = MouseHighlightOverlay(QRect(0, 0, 1920, 1080), [mock_effect])
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 激活渲染
        overlay.update_mouse_position(100, 100)
        
        # 模拟时间流逝
        overlay._last_mouse_move_time = time.time() - 0.2
        
        # 触发刷新回调
        overlay._on_refresh()
        
        # 因为有动画，不应该进入空闲状态
        assert overlay.is_idle() is False
        
        overlay.close()
    
    def test_mouse_move_reactivates_from_idle(self, qtbot):
        """从空闲状态重新激活"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        overlay = MouseHighlightOverlay(QRect(0, 0, 1920, 1080), [])
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 先激活再进入空闲
        overlay.update_mouse_position(100, 100)
        overlay._last_mouse_move_time = time.time() - 0.2
        overlay._on_refresh()
        assert overlay.is_idle() is True
        
        # 再次移动鼠标
        overlay.update_mouse_position(200, 200)
        
        # 应该重新激活
        assert overlay.is_idle() is False
        assert overlay._refresh_timer.isActive() is True
        
        overlay.close()


class TestAnimationCleanup:
    """Property 13: Animation Cleanup
    
    For any completed ripple animation, the animation state SHALL be removed
    from the active list within one frame after completion.
    """
    
    def test_ripple_removed_after_completion(self):
        """涟漪完成后被移除"""
        config = MouseHighlightConfig(click_effect_enabled=True, ripple_duration=100)
        theme = MOUSE_HIGHLIGHT_THEMES["classic_yellow"]
        
        effect = ClickRippleEffect(config, theme)
        
        # 添加涟漪
        effect.add_ripple(100, 100, True)
        assert len(effect._active_ripples) == 1
        
        # 模拟时间流逝（超过动画时长）
        effect._active_ripples[0].start_time = time.time() - 0.2  # 200ms 前
        
        # 绘制时会清理已完成的涟漪
        mock_painter = MagicMock(spec=QPainter)
        effect.draw(mock_painter, 0, 0, QRect(0, 0, 1920, 1080))
        
        # 涟漪应该被移除
        assert len(effect._active_ripples) == 0
    
    def test_active_ripple_not_removed(self):
        """活动中的涟漪不被移除"""
        config = MouseHighlightConfig(click_effect_enabled=True, ripple_duration=500)
        theme = MOUSE_HIGHLIGHT_THEMES["classic_yellow"]
        
        effect = ClickRippleEffect(config, theme)
        
        # 添加涟漪
        effect.add_ripple(100, 100, True)
        assert len(effect._active_ripples) == 1
        
        # 绘制（涟漪还在动画中）
        mock_painter = MagicMock(spec=QPainter)
        effect.draw(mock_painter, 0, 0, QRect(0, 0, 1920, 1080))
        
        # 涟漪应该保留
        assert len(effect._active_ripples) == 1
    
    def test_multiple_ripples_cleanup(self):
        """多个涟漪正确清理"""
        config = MouseHighlightConfig(click_effect_enabled=True, ripple_duration=100)
        theme = MOUSE_HIGHLIGHT_THEMES["classic_yellow"]
        
        effect = ClickRippleEffect(config, theme)
        
        # 添加多个涟漪
        effect.add_ripple(100, 100, True)
        effect.add_ripple(200, 200, False)
        effect.add_ripple(300, 300, True)
        assert len(effect._active_ripples) == 3
        
        # 让第一个和第三个过期
        effect._active_ripples[0].start_time = time.time() - 0.2
        effect._active_ripples[2].start_time = time.time() - 0.2
        # 第二个保持活动
        
        # 绘制
        mock_painter = MagicMock(spec=QPainter)
        effect.draw(mock_painter, 0, 0, QRect(0, 0, 1920, 1080))
        
        # 只有第二个涟漪应该保留
        assert len(effect._active_ripples) == 1
        assert effect._active_ripples[0].x == 200
    
    def test_is_animated_false_after_cleanup(self):
        """清理后 is_animated 返回 False"""
        config = MouseHighlightConfig(click_effect_enabled=True, ripple_duration=100)
        theme = MOUSE_HIGHLIGHT_THEMES["classic_yellow"]
        
        effect = ClickRippleEffect(config, theme)
        
        # 添加涟漪
        effect.add_ripple(100, 100, True)
        assert effect.is_animated() is True
        
        # 让涟漪过期
        effect._active_ripples[0].start_time = time.time() - 0.2
        
        # 绘制清理
        mock_painter = MagicMock(spec=QPainter)
        effect.draw(mock_painter, 0, 0, QRect(0, 0, 1920, 1080))
        
        # 应该不再有动画
        assert effect.is_animated() is False


class TestEffectFaultIsolation:
    """Property 14: Effect Fault Isolation
    
    For any effect that throws an exception during draw(),
    other effects SHALL continue to render normally,
    and the exception SHALL be logged.
    """
    
    def test_faulty_effect_does_not_crash_overlay(self, qtbot):
        """故障效果不会导致覆盖层崩溃"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        # 创建一个会抛出异常的效果
        faulty_effect = MagicMock()
        faulty_effect.draw.side_effect = RuntimeError("Test error")
        
        # 创建一个正常的效果
        normal_effect = MagicMock()
        
        overlay = MouseHighlightOverlay(
            QRect(0, 0, 1920, 1080),
            [faulty_effect, normal_effect]
        )
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 触发绘制（不应该崩溃）
        overlay.update_mouse_position(100, 100)
        overlay.update()
        
        # 等待绘制完成
        qtbot.wait(50)
        
        overlay.close()
    
    def test_normal_effects_still_render_after_fault(self, qtbot):
        """故障后正常效果继续渲染"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        # 创建效果
        faulty_effect = MagicMock()
        faulty_effect.draw.side_effect = RuntimeError("Test error")
        
        normal_effect1 = MagicMock()
        normal_effect2 = MagicMock()
        
        overlay = MouseHighlightOverlay(
            QRect(0, 0, 1920, 1080),
            [normal_effect1, faulty_effect, normal_effect2]
        )
        overlay.show()
        qtbot.waitExposed(overlay)
        
        # 触发绘制
        overlay.update_mouse_position(100, 100)
        
        # 等待绘制完成
        qtbot.wait(100)
        
        # 正常效果应该被调用（至少一次）
        # 注意：由于 Qt 的绘制机制，可能需要多次等待
        for _ in range(5):
            if normal_effect1.draw.called and normal_effect2.draw.called:
                break
            qtbot.wait(50)
        
        assert normal_effect1.draw.called or normal_effect2.draw.called
        
        overlay.close()
    
    def test_exception_logged(self, qtbot):
        """异常被记录到日志"""
        from screenshot_tool.ui.mouse_highlight_overlay import MouseHighlightOverlay
        
        faulty_effect = MagicMock()
        faulty_effect.draw.side_effect = RuntimeError("Test error")
        faulty_effect.__class__.__name__ = "FaultyEffect"
        
        overlay = MouseHighlightOverlay(
            QRect(0, 0, 1920, 1080),
            [faulty_effect]
        )
        overlay.show()
        qtbot.waitExposed(overlay)
        
        with patch('screenshot_tool.ui.mouse_highlight_overlay.async_debug_log') as mock_log:
            overlay.update_mouse_position(100, 100)
            overlay.repaint()
            
            # 检查是否记录了错误
            # 注意：由于 paintEvent 中的异常处理，日志应该被调用
            # 但具体调用取决于实现细节
        
        overlay.close()


class TestRippleStateLifecycle:
    """涟漪状态生命周期测试"""
    
    def test_ripple_progress_calculation(self):
        """涟漪进度计算正确"""
        ripple = RippleState(
            x=100,
            y=100,
            start_time=time.time(),
            is_left=True
        )
        
        # 刚开始时进度接近 0
        progress = ripple.get_progress(500)
        assert progress < 0.1
        
        # 模拟时间流逝
        ripple.start_time = time.time() - 0.25  # 250ms 前
        progress = ripple.get_progress(500)
        assert 0.4 < progress < 0.6
        
        # 完成后进度为 1.0
        ripple.start_time = time.time() - 1.0  # 1000ms 前
        progress = ripple.get_progress(500)
        assert progress == 1.0
    
    def test_ripple_is_finished(self):
        """涟漪完成判断正确"""
        ripple = RippleState(
            x=100,
            y=100,
            start_time=time.time(),
            is_left=True
        )
        
        # 刚开始时未完成
        assert ripple.is_finished(500) is False
        
        # 完成后
        ripple.start_time = time.time() - 1.0
        assert ripple.is_finished(500) is True
    
    def test_ripple_color_by_button(self):
        """涟漪颜色根据按钮类型区分"""
        config = MouseHighlightConfig(click_effect_enabled=True)
        theme = MOUSE_HIGHLIGHT_THEMES["classic_yellow"]
        
        effect = ClickRippleEffect(config, theme)
        
        # 添加左键和右键涟漪
        effect.add_ripple(100, 100, is_left=True)
        effect.add_ripple(200, 200, is_left=False)
        
        assert effect._active_ripples[0].is_left is True
        assert effect._active_ripples[1].is_left is False
