# =====================================================
# =============== BackgroundOCRCacheWorker 空闲检测器集成测试 ===============
# =====================================================

"""
BackgroundOCRCacheWorker 空闲检测器集成测试

测试后台 OCR 工作器与空闲检测器的集成：
- Requirement 2.2: 系统空闲时开始处理未处理的图片
- Requirement 2.3: 检测到用户活动时 100ms 内暂停处理

Task 4.3: 实现空闲检测器集成
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Signal, QObject

from screenshot_tool.services.background_ocr_cache_worker import (
    BackgroundOCRCacheWorker,
    WorkerState,
)
from screenshot_tool.services.system_idle_detector import SystemIdleDetector


class TestIdleDetectorConnection:
    """测试空闲检测器连接"""
    
    def test_connect_to_idle_detector_connects_signals(self):
        """connect_to_idle_detector 应连接 idle_started 和 idle_ended 信号"""
        worker = BackgroundOCRCacheWorker()
        detector = SystemIdleDetector()
        
        # 连接前，信号接收者数量
        # 注意：PySide6 不直接暴露接收者数量，我们通过行为测试
        
        worker.connect_to_idle_detector(detector)
        
        # 验证连接成功：发出信号时应调用对应槽函数
        # 使用 mock 来验证
        with patch.object(worker, 'on_idle_started') as mock_started:
            detector.idle_started.emit()
            mock_started.assert_called_once()
        
        with patch.object(worker, 'on_idle_ended') as mock_ended:
            detector.idle_ended.emit()
            mock_ended.assert_called_once()


class TestOnIdleStarted:
    """测试 on_idle_started 槽函数
    
    注意：这些测试不启动工作线程（不调用 start()），
    直接测试槽函数的逻辑，避免线程相关的复杂性。
    """
    
    def test_on_idle_started_calls_start_processing_when_running(self):
        """Requirement 2.2: 空闲开始时应开始处理"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 RUNNING，不启动线程
        worker._state = WorkerState.RUNNING
        
        with patch.object(worker, '_start_processing') as mock_start:
            worker.on_idle_started()
            mock_start.assert_called_once()
    
    def test_on_idle_started_resumes_from_paused_state(self):
        """空闲开始时应从暂停状态恢复"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 PAUSED
        worker._state = WorkerState.PAUSED
        
        assert worker.get_state() == WorkerState.PAUSED
        
        # 记录状态变化信号
        state_changes = []
        worker.state_changed.connect(lambda s: state_changes.append(s))
        
        with patch.object(worker, '_start_processing'):
            worker.on_idle_started()
        
        assert worker.get_state() == WorkerState.RUNNING
        assert WorkerState.RUNNING.value in state_changes
    
    def test_on_idle_started_ignored_when_stopped(self):
        """工作器停止时应忽略空闲开始信号"""
        worker = BackgroundOCRCacheWorker()
        # 默认状态是 STOPPED
        
        with patch.object(worker, '_start_processing') as mock_start:
            worker.on_idle_started()
            mock_start.assert_not_called()


class TestOnIdleEnded:
    """测试 on_idle_ended 槽函数
    
    注意：这些测试不启动工作线程，直接测试槽函数的逻辑。
    """
    
    def test_on_idle_ended_pauses_worker(self):
        """Requirement 2.3: 空闲结束时应暂停处理"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 RUNNING
        worker._state = WorkerState.RUNNING
        
        assert worker.get_state() == WorkerState.RUNNING
        
        worker.on_idle_ended()
        
        assert worker.get_state() == WorkerState.PAUSED
    
    def test_on_idle_ended_emits_state_changed_signal(self):
        """空闲结束时应发出状态变化信号"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 RUNNING
        worker._state = WorkerState.RUNNING
        
        state_changes = []
        worker.state_changed.connect(lambda s: state_changes.append(s))
        
        worker.on_idle_ended()
        
        assert WorkerState.PAUSED.value in state_changes
    
    def test_on_idle_ended_response_time_is_immediate(self):
        """Requirement 2.3: 暂停响应应该是即时的（同步调用）"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 RUNNING
        worker._state = WorkerState.RUNNING
        
        # on_idle_ended 直接调用 pause()，是同步的
        # 这确保了 100ms 内响应的要求
        # （实际的 100ms 保证由 SystemIdleDetector 的快速检测模式提供）
        
        worker.on_idle_ended()
        
        # 调用后状态应立即变为 PAUSED
        assert worker.get_state() == WorkerState.PAUSED


class TestIdleDetectorIntegration:
    """测试完整的空闲检测器集成流程
    
    注意：这些测试不启动工作线程，直接测试信号连接和状态转换。
    """
    
    def test_full_idle_cycle(self):
        """测试完整的空闲周期：空闲开始 -> 处理 -> 空闲结束 -> 暂停"""
        worker = BackgroundOCRCacheWorker()
        detector = SystemIdleDetector()
        
        worker.connect_to_idle_detector(detector)
        # 直接设置状态为 RUNNING
        worker._state = WorkerState.RUNNING
        
        # 记录状态变化
        state_changes = []
        worker.state_changed.connect(lambda s: state_changes.append(s))
        
        # 模拟空闲开始（已经是 RUNNING，不会改变状态）
        with patch.object(worker, '_start_processing'):
            detector.idle_started.emit()
        
        assert worker.get_state() == WorkerState.RUNNING
        
        # 模拟空闲结束
        detector.idle_ended.emit()
        
        assert worker.get_state() == WorkerState.PAUSED
        assert WorkerState.PAUSED.value in state_changes
        
        # 再次空闲开始
        state_changes.clear()
        with patch.object(worker, '_start_processing'):
            detector.idle_started.emit()
        
        assert worker.get_state() == WorkerState.RUNNING
        assert WorkerState.RUNNING.value in state_changes
    
    def test_multiple_idle_cycles(self):
        """测试多次空闲周期"""
        worker = BackgroundOCRCacheWorker()
        detector = SystemIdleDetector()
        
        worker.connect_to_idle_detector(detector)
        # 直接设置状态为 PAUSED（模拟已启动但暂停的状态）
        worker._state = WorkerState.PAUSED
        
        for _ in range(3):
            # 空闲开始
            with patch.object(worker, '_start_processing'):
                detector.idle_started.emit()
            assert worker.get_state() == WorkerState.RUNNING
            
            # 空闲结束
            detector.idle_ended.emit()
            assert worker.get_state() == WorkerState.PAUSED


class TestWorkerStateTransitions:
    """测试工作器状态转换（Property 3 相关）
    
    注意：这些测试不启动工作线程，直接测试状态转换逻辑。
    """
    
    def test_running_to_paused_on_idle_ended(self):
        """Property 3: 运行状态收到 idle_ended 应转为暂停状态"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 RUNNING
        worker._state = WorkerState.RUNNING
        
        assert worker.get_state() == WorkerState.RUNNING
        
        worker.on_idle_ended()
        
        assert worker.get_state() == WorkerState.PAUSED
    
    def test_paused_to_running_on_idle_started(self):
        """Property 3: 暂停状态收到 idle_started 应转为运行状态"""
        worker = BackgroundOCRCacheWorker()
        # 直接设置状态为 PAUSED
        worker._state = WorkerState.PAUSED
        
        assert worker.get_state() == WorkerState.PAUSED
        
        with patch.object(worker, '_start_processing'):
            worker.on_idle_started()
        
        assert worker.get_state() == WorkerState.RUNNING
