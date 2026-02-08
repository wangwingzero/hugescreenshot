# =====================================================
# =============== 网络测速服务测试 ===============
# =====================================================

"""
网络测速服务测试 - 测试测速结果和历史记录管理

Feature: system-tools
Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7
Property 7: Speed Test History Ordering
"""

import json
import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings

from screenshot_tool.services.network_speed_service import (
    SpeedTestResult,
    NetworkSpeedService,
)


class TestSpeedTestResult:
    """测试 SpeedTestResult 数据类"""
    
    def test_to_dict_and_from_dict_round_trip(self):
        """测试序列化往返"""
        result = SpeedTestResult(
            timestamp=datetime(2026, 1, 15, 14, 30, 0),
            download_mbps=156.8,
            upload_mbps=45.2,
            ping_ms=12.5,
            server="Cloudflare"
        )
        
        data = result.to_dict()
        restored = SpeedTestResult.from_dict(data)
        
        assert restored.timestamp == result.timestamp
        assert restored.download_mbps == result.download_mbps
        assert restored.upload_mbps == result.upload_mbps
        assert restored.ping_ms == result.ping_ms
        assert restored.server == result.server
    
    @given(
        download=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
        upload=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
        ping=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_round_trip_with_various_values(self, download: float, upload: float, ping: float):
        """测试各种值的序列化往返"""
        result = SpeedTestResult(
            timestamp=datetime.now(),
            download_mbps=download,
            upload_mbps=upload,
            ping_ms=ping,
            server="Test"
        )
        
        data = result.to_dict()
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        restored = SpeedTestResult.from_dict(loaded_data)
        
        # 由于 round() 的影响，允许小误差
        assert abs(restored.download_mbps - round(download, 2)) < 0.01
        assert abs(restored.upload_mbps - round(upload, 2)) < 0.01
        assert abs(restored.ping_ms - round(ping, 1)) < 0.1


class TestNetworkSpeedServiceHistory:
    """测试历史记录管理
    
    Property 7: Speed Test History Ordering
    """
    
    def test_initial_history_is_empty(self):
        """测试初始历史为空"""
        service = NetworkSpeedService()
        assert service.get_history() == []
    
    def test_is_testing_initially_false(self):
        """测试初始状态不在测速"""
        service = NetworkSpeedService()
        assert service.is_testing() is False
    
    def test_get_latest_result_when_empty(self):
        """测试空历史时获取最新结果"""
        service = NetworkSpeedService()
        assert service.get_latest_result() is None
    
    @given(st.lists(
        st.fixed_dictionaries({
            "download": st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
            "upload": st.floats(min_value=1, max_value=500, allow_nan=False, allow_infinity=False),
            "ping": st.floats(min_value=1, max_value=500, allow_nan=False, allow_infinity=False),
        }),
        min_size=1,
        max_size=20
    ))
    @settings(max_examples=20)
    def test_history_ordering(self, results_data: list):
        """Property 7: 历史记录按时间降序排列"""
        service = NetworkSpeedService()
        
        # 添加多个结果（模拟 _add_to_history）
        base_time = datetime.now()
        for i, data in enumerate(results_data):
            result = SpeedTestResult(
                timestamp=base_time + timedelta(minutes=i),
                download_mbps=data["download"],
                upload_mbps=data["upload"],
                ping_ms=data["ping"],
                server="Test"
            )
            service._history.insert(0, result)
        
        # 获取历史并验证排序
        history = service.get_history()
        
        # 验证按时间降序排列
        for i in range(len(history) - 1):
            assert history[i].timestamp >= history[i + 1].timestamp
    
    def test_history_max_limit(self):
        """测试历史记录数量限制"""
        service = NetworkSpeedService()
        
        # 添加超过限制的记录
        for i in range(service.MAX_HISTORY + 10):
            result = SpeedTestResult(
                timestamp=datetime.now() + timedelta(seconds=i),
                download_mbps=100.0,
                upload_mbps=50.0,
                ping_ms=10.0,
                server="Test"
            )
            service._add_to_history(result)
        
        # 验证不超过限制
        assert len(service._history) <= service.MAX_HISTORY
    
    def test_clear_history(self):
        """测试清空历史"""
        service = NetworkSpeedService()
        
        # 添加一些记录
        for i in range(5):
            result = SpeedTestResult(
                timestamp=datetime.now(),
                download_mbps=100.0,
                upload_mbps=50.0,
                ping_ms=10.0,
                server="Test"
            )
            service._history.append(result)
        
        assert len(service._history) == 5
        
        service.clear_history()
        
        assert len(service._history) == 0
        assert service.get_history() == []
    
    def test_get_latest_result(self):
        """测试获取最新结果"""
        service = NetworkSpeedService()
        
        # 添加多个结果
        for i in range(3):
            result = SpeedTestResult(
                timestamp=datetime.now() + timedelta(seconds=i),
                download_mbps=100.0 + i,
                upload_mbps=50.0,
                ping_ms=10.0,
                server="Test"
            )
            service._add_to_history(result)
        
        latest = service.get_latest_result()
        assert latest is not None
        assert latest.download_mbps == 102.0  # 最后添加的


class TestNetworkSpeedServiceProgress:
    """测试进度跟踪"""
    
    def test_get_progress_initial(self):
        """测试初始进度"""
        service = NetworkSpeedService()
        stage, progress = service.get_progress()
        
        assert progress == 0.0
    
    def test_cannot_start_test_while_testing(self):
        """测试正在测速时不能再次开始"""
        service = NetworkSpeedService()
        service._is_testing = True
        
        error_called = []
        
        def on_error(msg):
            error_called.append(msg)
        
        service.start_test(on_error=on_error)
        
        assert len(error_called) == 1
        assert "正在进行中" in error_called[0]


class TestSpeedTestResultFormatting:
    """测试结果格式化"""
    
    def test_to_dict_rounds_values(self):
        """测试 to_dict 对值进行四舍五入"""
        result = SpeedTestResult(
            timestamp=datetime.now(),
            download_mbps=156.789,
            upload_mbps=45.234,
            ping_ms=12.567,
            server="Test"
        )
        
        data = result.to_dict()
        
        assert data["download_mbps"] == 156.79
        assert data["upload_mbps"] == 45.23
        assert data["ping_ms"] == 12.6
