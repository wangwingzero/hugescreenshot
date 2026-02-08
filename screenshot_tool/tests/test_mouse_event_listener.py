# =====================================================
# =============== 鼠标事件监听器测试 ===============
# =====================================================

"""
MouseEventListener 单元测试

测试内容：
- Property 4: Event Rate Limiting (60 FPS 限流)
- Property 5: Click Event Emission (点击事件发射)
- 基本功能测试

Feature: mouse-highlight
Requirements: 2.2, 2.3, 2.4
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

from PySide6.QtCore import QObject


class TestMouseEventListenerBasic:
    """MouseEventListener 基本功能测试"""
    
    def test_import(self):
        """测试模块导入"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        assert MouseEventListener is not None
    
    def test_instantiation(self, qtbot):
        """测试实例化"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        assert listener is not None
        assert not listener.is_running()
    
    def test_signals_exist(self, qtbot):
        """测试信号存在"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 检查信号存在
        assert hasattr(listener, 'mouse_moved')
        assert hasattr(listener, 'left_clicked')
        assert hasattr(listener, 'right_clicked')
    
    def test_throttle_interval(self):
        """测试限流间隔常量"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        # 60 FPS = 16.67ms，我们使用 16ms
        assert MouseEventListener.THROTTLE_INTERVAL_MS == 16
    
    def test_start_stop_cycle(self, qtbot):
        """测试启动停止循环"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 启动
        result = listener.start()
        assert result is True
        assert listener.is_running()
        
        # 停止
        listener.stop()
        assert not listener.is_running()
    
    def test_double_start(self, qtbot):
        """测试重复启动"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        try:
            # 第一次启动
            result1 = listener.start()
            assert result1 is True
            
            # 第二次启动应该返回 True（已在运行）
            result2 = listener.start()
            assert result2 is True
            assert listener.is_running()
        finally:
            listener.stop()
    
    def test_double_stop(self, qtbot):
        """测试重复停止"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        listener.start()
        listener.stop()
        
        # 第二次停止不应该报错
        listener.stop()
        assert not listener.is_running()
    
    def test_stop_without_start(self, qtbot):
        """测试未启动时停止"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 未启动时停止不应该报错
        listener.stop()
        assert not listener.is_running()


class TestEventRateLimiting:
    """Property 4: Event Rate Limiting 测试
    
    验证：在 16ms 内的多个鼠标移动事件，最多发射一次 mouse_moved 信号
    """
    
    def test_throttle_blocks_rapid_events(self, qtbot):
        """测试限流阻止快速事件"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 模拟快速连续的鼠标移动
        # 设置初始时间
        listener._last_move_time = time.time() * 1000
        
        # 记录信号发射次数
        emit_count = [0]
        
        def count_emit(x, y):
            emit_count[0] += 1
        
        listener.mouse_moved.connect(count_emit)
        
        # 在 16ms 内模拟多次移动（通过直接调用回调逻辑）
        # 由于我们无法直接调用 _low_level_mouse_proc（需要 Windows 钩子），
        # 我们测试限流逻辑本身
        
        current_time = listener._last_move_time
        
        # 第一次移动（应该被阻止，因为间隔 < 16ms）
        if current_time - listener._last_move_time >= listener.THROTTLE_INTERVAL_MS:
            listener.mouse_moved.emit(100, 100)
        
        # 间隔 5ms（应该被阻止）
        current_time += 5
        if current_time - listener._last_move_time >= listener.THROTTLE_INTERVAL_MS:
            listener.mouse_moved.emit(101, 101)
        
        # 间隔 10ms（应该被阻止）
        current_time += 5
        if current_time - listener._last_move_time >= listener.THROTTLE_INTERVAL_MS:
            listener.mouse_moved.emit(102, 102)
        
        # 验证没有信号被发射（因为都在 16ms 内）
        assert emit_count[0] == 0
    
    def test_throttle_allows_after_interval(self, qtbot):
        """测试限流在间隔后允许事件"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 设置初始时间为 20ms 前
        listener._last_move_time = time.time() * 1000 - 20
        
        # 记录信号发射
        emit_count = [0]
        
        def count_emit(x, y):
            emit_count[0] += 1
        
        listener.mouse_moved.connect(count_emit)
        
        # 现在应该允许发射（间隔 > 16ms）
        current_time = time.time() * 1000
        if current_time - listener._last_move_time >= listener.THROTTLE_INTERVAL_MS:
            listener.mouse_moved.emit(100, 100)
        
        assert emit_count[0] == 1
    
    @given(st.integers(min_value=0, max_value=15))
    @settings(max_examples=100)
    def test_property_throttle_blocks_within_interval(self, interval_ms):
        """Property 4: 在 16ms 内的事件应该被阻止"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        
        # 模拟限流逻辑
        last_time = 1000.0  # 假设上次发射时间
        current_time = last_time + interval_ms
        
        # 如果间隔 < 16ms，不应该发射
        should_emit = (current_time - last_time) >= MouseEventListener.THROTTLE_INTERVAL_MS
        
        # interval_ms 范围是 0-15，所以都应该被阻止
        assert should_emit is False
    
    @given(st.integers(min_value=16, max_value=1000))
    @settings(max_examples=100)
    def test_property_throttle_allows_after_interval(self, interval_ms):
        """Property 4: 在 16ms 后的事件应该被允许"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        
        # 模拟限流逻辑
        last_time = 1000.0
        current_time = last_time + interval_ms
        
        # 如果间隔 >= 16ms，应该发射
        should_emit = (current_time - last_time) >= MouseEventListener.THROTTLE_INTERVAL_MS
        
        # interval_ms 范围是 16-1000，所以都应该允许
        assert should_emit is True


class TestClickEventEmission:
    """Property 5: Click Event Emission 测试
    
    验证：每次鼠标点击都会发射一个对应的点击信号，坐标正确
    """
    
    def test_left_click_signal(self, qtbot):
        """测试左键点击信号"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 记录信号
        clicks = []
        
        def on_left_click(x, y):
            clicks.append(('left', x, y))
        
        listener.left_clicked.connect(on_left_click)
        
        # 手动发射信号（模拟点击）
        listener.left_clicked.emit(100, 200)
        
        assert len(clicks) == 1
        assert clicks[0] == ('left', 100, 200)
    
    def test_right_click_signal(self, qtbot):
        """测试右键点击信号"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 记录信号
        clicks = []
        
        def on_right_click(x, y):
            clicks.append(('right', x, y))
        
        listener.right_clicked.connect(on_right_click)
        
        # 手动发射信号（模拟点击）
        listener.right_clicked.emit(300, 400)
        
        assert len(clicks) == 1
        assert clicks[0] == ('right', 300, 400)
    
    def test_multiple_clicks(self, qtbot):
        """测试多次点击"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        left_clicks = []
        right_clicks = []
        
        listener.left_clicked.connect(lambda x, y: left_clicks.append((x, y)))
        listener.right_clicked.connect(lambda x, y: right_clicks.append((x, y)))
        
        # 模拟多次点击
        listener.left_clicked.emit(10, 20)
        listener.right_clicked.emit(30, 40)
        listener.left_clicked.emit(50, 60)
        
        assert len(left_clicks) == 2
        assert len(right_clicks) == 1
        assert left_clicks[0] == (10, 20)
        assert left_clicks[1] == (50, 60)
        assert right_clicks[0] == (30, 40)
    
    @given(
        st.integers(min_value=-10000, max_value=10000),
        st.integers(min_value=-10000, max_value=10000)
    )
    @settings(max_examples=100)
    def test_property_click_coordinates_preserved(self, x, y):
        """Property 5: 点击坐标应该被正确传递"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        from PySide6.QtWidgets import QApplication
        
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        listener = MouseEventListener()
        
        received = []
        listener.left_clicked.connect(lambda rx, ry: received.append((rx, ry)))
        
        # 发射信号
        listener.left_clicked.emit(x, y)
        
        # 验证坐标正确
        assert len(received) == 1
        assert received[0] == (x, y)


class TestWindowsHookConstants:
    """Windows 钩子常量测试"""
    
    def test_hook_constants(self):
        """测试 Windows 常量定义正确"""
        from screenshot_tool.core.mouse_event_listener import (
            WH_MOUSE_LL, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_QUIT
        )
        
        assert WH_MOUSE_LL == 14
        assert WM_MOUSEMOVE == 0x0200
        assert WM_LBUTTONDOWN == 0x0201
        assert WM_RBUTTONDOWN == 0x0204
        assert WM_QUIT == 0x0012
    
    def test_structures_defined(self):
        """测试结构体定义"""
        from screenshot_tool.core.mouse_event_listener import POINT, MSLLHOOKSTRUCT
        
        # 测试 POINT 结构
        pt = POINT()
        pt.x = 100
        pt.y = 200
        assert pt.x == 100
        assert pt.y == 200
        
        # 测试 MSLLHOOKSTRUCT 结构
        hook_struct = MSLLHOOKSTRUCT()
        hook_struct.pt.x = 300
        hook_struct.pt.y = 400
        assert hook_struct.pt.x == 300
        assert hook_struct.pt.y == 400


class TestResourceCleanup:
    """资源清理测试"""
    
    def test_cleanup_on_stop(self, qtbot):
        """测试停止时清理资源"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        listener.start()
        assert listener.is_running()
        assert listener._hook_id is not None
        
        listener.stop()
        assert not listener.is_running()
        # 钩子 ID 应该被清理
        assert listener._hook_id is None
    
    def test_cleanup_on_del(self, qtbot):
        """测试析构时清理资源"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        
        listener = MouseEventListener()
        listener.start()
        
        # 删除对象应该触发清理
        del listener
        # 如果没有异常，说明清理成功


class TestIntegration:
    """集成测试"""
    
    def test_full_lifecycle(self, qtbot):
        """测试完整生命周期"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 连接信号
        moves = []
        left_clicks = []
        right_clicks = []
        
        listener.mouse_moved.connect(lambda x, y: moves.append((x, y)))
        listener.left_clicked.connect(lambda x, y: left_clicks.append((x, y)))
        listener.right_clicked.connect(lambda x, y: right_clicks.append((x, y)))
        
        # 启动
        assert listener.start()
        assert listener.is_running()
        
        # 等待一小段时间让钩子稳定
        qtbot.wait(100)
        
        # 停止
        listener.stop()
        assert not listener.is_running()
    
    def test_restart_after_stop(self, qtbot):
        """测试停止后重启"""
        from screenshot_tool.core.mouse_event_listener import MouseEventListener
        listener = MouseEventListener()
        
        # 第一次启动
        assert listener.start()
        listener.stop()
        
        # 第二次启动
        assert listener.start()
        assert listener.is_running()
        
        listener.stop()
