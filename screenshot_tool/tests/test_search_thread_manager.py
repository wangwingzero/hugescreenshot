"""
搜索线程管理器属性测试

Feature: google-search-performance
Property 7: 停止请求幂等性
**Validates: Requirements 3.3**

测试 SearchThreadManager 的停止请求幂等性：
多次调用 request_stop_async 应与调用一次具有相同效果。
第一次调用后，后续调用应被安全忽略。
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, patch, MagicMock
from typing import Optional

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication


# ========== Fixtures ==========

@pytest.fixture(scope="module")
def qapp():
    """创建 QApplication 实例（测试 Qt 组件需要）"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def manager(qapp):
    """创建 SearchThreadManager 实例"""
    from screenshot_tool.services.search_worker import SearchThreadManager
    return SearchThreadManager()


# ========== Property 7: 停止请求幂等性 ==========
# Feature: google-search-performance, Property 7: 停止请求幂等性
# **Validates: Requirements 3.3**
#
# 对于任意 SearchThreadManager，多次调用 request_stop_async 应与调用一次具有相同效果。
# 第一次调用后，后续调用应被安全忽略。


class TestStopRequestIdempotency:
    """Property 7: 停止请求幂等性 属性测试
    
    Feature: google-search-performance, Property 7: 停止请求幂等性
    **Validates: Requirements 3.3**
    
    WHEN 多个停止请求同时到达 THEN SearchThreadManager SHALL 只处理第一个请求，
    忽略后续重复请求
    """
    
    # ========== Property 7.1: 未启动时的幂等性 ==========
    
    @settings(max_examples=100)
    @given(call_count=st.integers(min_value=1, max_value=20))
    def test_stop_request_idempotent_when_not_started(self, qapp, call_count: int):
        """Property 7: 未启动时多次调用 request_stop_async 应安全忽略
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        对于从未启动的 SearchThreadManager，多次调用 request_stop_async
        应该安全地被忽略，不抛出异常，状态保持一致。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 验证初始状态
        assert manager._worker is None
        assert manager._thread is None
        assert not manager._is_ready
        assert not manager._is_searching
        
        # 多次调用停止请求
        for i in range(call_count):
            manager.request_stop_async()  # 不应抛出异常
        
        # 验证状态保持一致（仍然是未启动状态）
        assert manager._worker is None, \
            f"_worker should remain None after {call_count} stop requests"
        assert manager._thread is None, \
            f"_thread should remain None after {call_count} stop requests"
        assert not manager._is_ready, \
            f"_is_ready should remain False after {call_count} stop requests"
        assert not manager._is_searching, \
            f"_is_searching should remain False after {call_count} stop requests"
    
    # ========== Property 7.2: 已停止后的幂等性 ==========
    
    @settings(max_examples=100)
    @given(call_count=st.integers(min_value=2, max_value=20))
    def test_stop_request_idempotent_after_first_stop(self, qapp, call_count: int):
        """Property 7: 第一次停止后，后续调用应被安全忽略
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        对于已经调用过 request_stop_async 的 SearchThreadManager，
        后续的调用应该被安全忽略，状态保持一致。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 模拟已启动状态（通过直接设置内部变量）
        mock_worker = Mock()
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        manager._is_searching = False
        
        # 第一次调用停止请求
        manager.request_stop_async()
        
        # 验证第一次调用后的状态
        assert manager._worker is None, "_worker should be None after first stop"
        assert manager._thread is None, "_thread should be None after first stop"
        assert not manager._is_ready, "_is_ready should be False after first stop"
        
        # 验证 worker.request_stop() 被调用了一次
        mock_worker.request_stop.assert_called_once()
        
        # 后续多次调用停止请求
        for i in range(call_count - 1):
            manager.request_stop_async()  # 不应抛出异常
        
        # 验证状态保持一致
        assert manager._worker is None, \
            f"_worker should remain None after {call_count} stop requests"
        assert manager._thread is None, \
            f"_thread should remain None after {call_count} stop requests"
        assert not manager._is_ready, \
            f"_is_ready should remain False after {call_count} stop requests"
        
        # 验证 worker.request_stop() 仍然只被调用了一次
        mock_worker.request_stop.assert_called_once()
    
    # ========== Property 7.3: 状态一致性 ==========
    
    @settings(max_examples=100)
    @given(call_count=st.integers(min_value=1, max_value=10))
    def test_stop_request_state_consistency(self, qapp, call_count: int):
        """Property 7: 多次调用后状态应与调用一次相同
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        无论调用多少次 request_stop_async，最终状态应该与调用一次相同。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        
        # 创建两个相同初始状态的 manager
        manager_single = SearchThreadManager()
        manager_multiple = SearchThreadManager()
        
        # 设置相同的模拟初始状态
        for mgr in [manager_single, manager_multiple]:
            mock_worker = Mock()
            mock_thread = Mock()
            mock_thread.isRunning.return_value = True
            mgr._worker = mock_worker
            mgr._thread = mock_thread
            mgr._is_ready = True
            mgr._is_searching = True
        
        # manager_single 只调用一次
        manager_single.request_stop_async()
        
        # manager_multiple 调用多次
        for _ in range(call_count):
            manager_multiple.request_stop_async()
        
        # 验证两者状态相同
        assert manager_single._worker == manager_multiple._worker, \
            "_worker state should be identical"
        assert manager_single._thread == manager_multiple._thread, \
            "_thread state should be identical"
        assert manager_single._is_ready == manager_multiple._is_ready, \
            "_is_ready state should be identical"
        assert manager_single._is_searching == manager_multiple._is_searching, \
            "_is_searching state should be identical"
    
    # ========== Property 7.4: 异常安全性 ==========
    
    @settings(max_examples=50)
    @given(call_count=st.integers(min_value=1, max_value=10))
    def test_stop_request_exception_safety(self, qapp, call_count: int):
        """Property 7: 即使 worker.request_stop() 抛出异常，后续调用也应安全
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        如果第一次调用时 worker.request_stop() 抛出异常，
        后续调用应该安全地被忽略（因为引用已被清除）。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置模拟状态，worker.request_stop() 会抛出异常
        mock_worker = Mock()
        mock_worker.request_stop.side_effect = Exception("模拟异常")
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        
        # 第一次调用（会触发异常，但应该被捕获）
        manager.request_stop_async()  # 不应向外抛出异常
        
        # 验证状态已被清除（即使异常发生）
        assert manager._worker is None, "_worker should be None even after exception"
        assert manager._thread is None, "_thread should be None even after exception"
        
        # 后续调用应该安全
        for _ in range(call_count - 1):
            manager.request_stop_async()  # 不应抛出异常
        
        # 状态保持一致
        assert manager._worker is None
        assert manager._thread is None
    
    # ========== Property 7.5: 非阻塞性 ==========
    
    @settings(max_examples=50)
    @given(call_count=st.integers(min_value=1, max_value=5))
    def test_stop_request_non_blocking(self, qapp, call_count: int):
        """Property 7: request_stop_async 应该是非阻塞的
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        request_stop_async 不应调用任何阻塞操作（如 thread.wait()）。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置模拟状态
        mock_worker = Mock()
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        mock_thread.wait = Mock()  # 监控 wait 调用
        mock_thread.quit = Mock()  # 监控 quit 调用
        
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        
        # 多次调用停止请求
        for _ in range(call_count):
            manager.request_stop_async()
        
        # 验证没有调用阻塞方法
        mock_thread.wait.assert_not_called()
        mock_thread.quit.assert_not_called()


class TestStopRequestIdempotencyEdgeCases:
    """Property 7: 停止请求幂等性 - 边界情况测试
    
    Feature: google-search-performance, Property 7: 停止请求幂等性
    **Validates: Requirements 3.3**
    """
    
    def test_stop_request_with_none_worker_and_valid_thread(self, qapp):
        """边界情况：worker 为 None 但 thread 不为 None
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置不一致的状态（理论上不应该发生，但需要处理）
        manager._worker = None
        manager._thread = Mock()
        manager._is_ready = False
        
        # 调用停止请求应该安全处理
        manager.request_stop_async()
        
        # 验证状态被清理
        assert manager._thread is None
    
    def test_stop_request_with_valid_worker_and_none_thread(self, qapp):
        """边界情况：thread 为 None 但 worker 不为 None
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置不一致的状态
        mock_worker = Mock()
        manager._worker = mock_worker
        manager._thread = None
        manager._is_ready = True
        
        # 调用停止请求应该安全处理
        manager.request_stop_async()
        
        # 验证状态被清理
        assert manager._worker is None
        assert not manager._is_ready
        
        # 验证 worker.request_stop() 被调用
        mock_worker.request_stop.assert_called_once()
    
    def test_stop_request_clears_references_before_calling_worker(self, qapp):
        """验证引用在调用 worker.request_stop() 之前被清除
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        这确保了即使 worker.request_stop() 触发回调或异常，
        也不会导致重复调用。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 记录调用时的状态
        state_during_call = {}
        
        def capture_state():
            state_during_call['worker'] = manager._worker
            state_during_call['thread'] = manager._thread
            state_during_call['is_ready'] = manager._is_ready
        
        mock_worker = Mock()
        mock_worker.request_stop.side_effect = capture_state
        mock_thread = Mock()
        
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        
        # 调用停止请求
        manager.request_stop_async()
        
        # 验证在调用 worker.request_stop() 时，引用已被清除
        assert state_during_call['worker'] is None, \
            "_worker should be None when worker.request_stop() is called"
        assert state_during_call['thread'] is None, \
            "_thread should be None when worker.request_stop() is called"
        assert state_during_call['is_ready'] is False, \
            "_is_ready should be False when worker.request_stop() is called"
    
    @settings(max_examples=50)
    @given(
        initial_is_ready=st.booleans(),
        initial_is_searching=st.booleans(),
    )
    def test_stop_request_resets_all_flags(
        self, 
        qapp, 
        initial_is_ready: bool, 
        initial_is_searching: bool
    ):
        """Property 7: request_stop_async 应重置所有状态标志
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        
        无论初始状态如何，调用后 _is_ready 和 _is_searching 都应为 False。
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置初始状态
        mock_worker = Mock()
        mock_thread = Mock()
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = initial_is_ready
        manager._is_searching = initial_is_searching
        
        # 调用停止请求
        manager.request_stop_async()
        
        # 验证所有标志都被重置
        assert manager._is_ready is False, \
            f"_is_ready should be False (was {initial_is_ready})"
        assert manager._is_searching is False, \
            f"_is_searching should be False (was {initial_is_searching})"


class TestStopRequestIdempotencyIntegration:
    """Property 7: 停止请求幂等性 - 集成测试
    
    Feature: google-search-performance, Property 7: 停止请求幂等性
    **Validates: Requirements 3.3**
    
    这些测试验证在更接近真实场景下的幂等性。
    """
    
    def test_rapid_consecutive_stop_requests(self, qapp):
        """快速连续调用 request_stop_async 应该安全
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置模拟状态
        mock_worker = Mock()
        mock_thread = Mock()
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        
        # 快速连续调用 100 次
        for _ in range(100):
            manager.request_stop_async()
        
        # 验证最终状态
        assert manager._worker is None
        assert manager._thread is None
        assert not manager._is_ready
        
        # 验证 worker.request_stop() 只被调用一次
        mock_worker.request_stop.assert_called_once()
    
    def test_stop_request_after_normal_stop(self, qapp):
        """在 stop() 之后调用 request_stop_async 应该安全
        
        Feature: google-search-performance, Property 7: 停止请求幂等性
        **Validates: Requirements 3.3**
        """
        from screenshot_tool.services.search_worker import SearchThreadManager
        manager = SearchThreadManager()
        
        # 设置模拟状态
        mock_worker = Mock()
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        mock_thread.wait.return_value = True
        
        manager._worker = mock_worker
        manager._thread = mock_thread
        manager._is_ready = True
        
        # 先调用 stop()
        manager.stop()
        
        # 再调用 request_stop_async() 应该安全
        manager.request_stop_async()
        
        # 验证状态
        assert manager._worker is None
        assert manager._thread is None

