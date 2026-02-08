# =====================================================
# =============== SystemIdleDetector 单元测试 ===============
# =====================================================

"""
SystemIdleDetector 单元测试

测试系统级空闲检测器的核心功能：
- Requirement 1.2: 使用 QTimer 每 5 秒检查一次
- Requirement 1.3: 空闲时间超过 60 秒时发出 idle_started 信号
- Requirement 1.4: 用户活动后 100ms 内发出 idle_ended 信号
"""

import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtCore import QTimer

from screenshot_tool.services.system_idle_detector import (
    SystemIdleDetector,
    LASTINPUTINFO,
)


class TestSystemIdleDetectorConstants:
    """测试常量定义"""
    
    def test_default_check_interval_is_5_seconds(self):
        """Requirement 1.2: 默认检查间隔应为 5 秒"""
        assert SystemIdleDetector.DEFAULT_CHECK_INTERVAL_MS == 5000
    
    def test_fast_check_interval_is_100ms(self):
        """Requirement 1.4: 快速检查间隔应为 100ms"""
        assert SystemIdleDetector.FAST_CHECK_INTERVAL_MS == 100
    
    def test_default_idle_threshold_is_60_seconds(self):
        """Requirement 1.3: 默认空闲阈值应为 60 秒"""
        assert SystemIdleDetector.DEFAULT_IDLE_THRESHOLD_MS == 60000


class TestSystemIdleDetectorInitialization:
    """测试初始化"""
    
    def test_initial_state_is_not_idle(self):
        """初始状态应为非空闲"""
        detector = SystemIdleDetector()
        assert detector.is_idle() is False
    
    def test_initial_state_is_not_monitoring(self):
        """初始状态应为未监控"""
        detector = SystemIdleDetector()
        assert detector.is_monitoring() is False
    
    def test_timer_is_created(self):
        """应创建 QTimer"""
        detector = SystemIdleDetector()
        assert hasattr(detector, '_timer')
        assert isinstance(detector._timer, QTimer)


class TestSystemIdleDetectorMonitoring:
    """测试监控功能"""
    
    def test_start_monitoring_sets_monitoring_flag(self):
        """start_monitoring 应设置监控标志"""
        detector = SystemIdleDetector()
        detector.start_monitoring()
        assert detector.is_monitoring() is True
        detector.stop_monitoring()
    
    def test_start_monitoring_uses_default_interval(self):
        """start_monitoring 应使用默认间隔"""
        detector = SystemIdleDetector()
        detector.start_monitoring()
        assert detector._timer.interval() == SystemIdleDetector.DEFAULT_CHECK_INTERVAL_MS
        detector.stop_monitoring()
    
    def test_start_monitoring_with_custom_interval(self):
        """start_monitoring 应支持自定义间隔"""
        detector = SystemIdleDetector()
        detector.start_monitoring(interval_ms=1000)
        assert detector._timer.interval() == 1000
        detector.stop_monitoring()
    
    def test_stop_monitoring_clears_monitoring_flag(self):
        """stop_monitoring 应清除监控标志"""
        detector = SystemIdleDetector()
        detector.start_monitoring()
        detector.stop_monitoring()
        assert detector.is_monitoring() is False
    
    def test_stop_monitoring_stops_timer(self):
        """stop_monitoring 应停止定时器"""
        detector = SystemIdleDetector()
        detector.start_monitoring()
        detector.stop_monitoring()
        assert detector._timer.isActive() is False


class TestSystemIdleDetectorThreshold:
    """测试阈值设置"""
    
    def test_set_idle_threshold_updates_value(self):
        """set_idle_threshold 应更新阈值"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(30000)
        assert detector._idle_threshold_ms == 30000
    
    def test_set_idle_threshold_ignores_invalid_value(self):
        """set_idle_threshold 应忽略无效值"""
        detector = SystemIdleDetector()
        original = detector._idle_threshold_ms
        detector.set_idle_threshold(0)
        assert detector._idle_threshold_ms == original
        detector.set_idle_threshold(-1000)
        assert detector._idle_threshold_ms == original


class TestSystemIdleDetectorStateTransitions:
    """测试状态转换"""
    
    def test_idle_started_signal_emitted_when_threshold_exceeded(self):
        """Requirement 1.3: 空闲时间超过阈值时应发出 idle_started 信号"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)  # 1 秒阈值便于测试
        
        # 记录信号
        signals_received = []
        detector.idle_started.connect(lambda: signals_received.append('idle_started'))
        
        # 模拟空闲时间超过阈值
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
        
        assert 'idle_started' in signals_received
        assert detector.is_idle() is True
    
    def test_idle_ended_signal_emitted_when_activity_detected(self):
        """Requirement 1.4: 用户活动后应发出 idle_ended 信号"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)
        
        # 先进入空闲状态
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
        
        # 记录信号
        signals_received = []
        detector.idle_ended.connect(lambda: signals_received.append('idle_ended'))
        
        # 模拟用户活动（空闲时间变短）
        with patch.object(detector, 'get_idle_time_ms', return_value=100):
            detector._check_idle_status()
        
        assert 'idle_ended' in signals_received
        assert detector.is_idle() is False
    
    def test_timer_switches_to_fast_mode_when_idle(self):
        """Requirement 1.4: 进入空闲状态时应切换到快速检测模式"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)
        detector.start_monitoring()
        
        # 模拟进入空闲状态
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
        
        assert detector._timer.interval() == SystemIdleDetector.FAST_CHECK_INTERVAL_MS
        detector.stop_monitoring()
    
    def test_timer_switches_to_normal_mode_when_active(self):
        """退出空闲状态时应切换回正常检测间隔"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)
        detector.start_monitoring()
        
        # 先进入空闲状态
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
        
        # 再退出空闲状态
        with patch.object(detector, 'get_idle_time_ms', return_value=100):
            detector._check_idle_status()
        
        assert detector._timer.interval() == SystemIdleDetector.DEFAULT_CHECK_INTERVAL_MS
        detector.stop_monitoring()
    
    def test_no_duplicate_signals_when_state_unchanged(self):
        """状态未变化时不应重复发出信号"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)
        
        signals_received = []
        detector.idle_started.connect(lambda: signals_received.append('idle_started'))
        
        # 连续两次检测都是空闲状态
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
            detector._check_idle_status()
        
        # 应该只发出一次信号
        assert signals_received.count('idle_started') == 1


class TestSystemIdleDetectorCleanup:
    """测试资源清理"""
    
    def test_cleanup_stops_monitoring(self):
        """cleanup 应停止监控"""
        detector = SystemIdleDetector()
        detector.start_monitoring()
        detector.cleanup()
        assert detector.is_monitoring() is False
    
    def test_cleanup_emits_idle_ended_if_idle(self):
        """cleanup 时如果处于空闲状态应发出 idle_ended 信号"""
        detector = SystemIdleDetector()
        detector.set_idle_threshold(1000)
        
        # 先连接信号
        signals_received = []
        detector.idle_ended.connect(lambda: signals_received.append('idle_ended'))
        
        # 开始监控并进入空闲状态
        detector.start_monitoring()
        with patch.object(detector, 'get_idle_time_ms', return_value=2000):
            detector._check_idle_status()
        
        # 清空之前的信号记录（idle_started 可能已触发）
        signals_received.clear()
        
        detector.cleanup()
        
        assert 'idle_ended' in signals_received


class TestLASTINPUTINFOStructure:
    """测试 Windows API 结构定义"""
    
    def test_lastinputinfo_has_correct_fields(self):
        """LASTINPUTINFO 应有正确的字段"""
        lii = LASTINPUTINFO()
        assert hasattr(lii, 'cbSize')
        assert hasattr(lii, 'dwTime')
