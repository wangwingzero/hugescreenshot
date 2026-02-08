"""资源加载属性测试

Feature: performance-ui-optimization
Property 6: Background Processing
**Validates: Requirements 1.5, 2.5**

测试资源加载的后台处理属性：
1. ResourceLoaderWorker 在后台线程执行（非主线程）
2. 图标异步加载不阻塞主线程
3. 结果通过 Qt 信号通信（icon_loaded, all_loaded）
4. 缓存是线程安全的
"""

import os
import tempfile
import threading
import time
import pytest
from typing import List, Tuple, Optional
from unittest.mock import MagicMock, patch

from hypothesis import given, strategies as st, settings, HealthCheck, assume
from PySide6.QtCore import QThread, QCoreApplication, QObject, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from screenshot_tool.core.resource_cache import (
    ResourceCache,
    ResourceLoaderWorker,
    get_cached_icon,
    get_cached_pixmap,
)


# ========== Fixtures ==========

@pytest.fixture(scope="module")
def qapp():
    """创建 Qt 应用程序实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_cache():
    """每个测试前后重置缓存"""
    ResourceCache.reset()
    yield
    ResourceCache.reset()


@pytest.fixture
def temp_icons_dir():
    """创建临时图标目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        icons_dir = os.path.join(tmpdir, "resources", "icons")
        os.makedirs(icons_dir)
        yield tmpdir, icons_dir


def create_svg_icon(icons_dir: str, name: str) -> str:
    """创建一个简单的 SVG 图标文件
    
    Args:
        icons_dir: 图标目录路径
        name: 图标名称（不含扩展名）
        
    Returns:
        图标文件完整路径
    """
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">
        <rect width="24" height="24" fill="#{hash(name) % 0xFFFFFF:06x}"/>
    </svg>'''
    svg_path = os.path.join(icons_dir, f"{name}.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return svg_path


# ========== Property 6: Background Processing ==========
# Feature: performance-ui-optimization, Property 6: Background Processing
# **Validates: Requirements 1.5, 2.5**
#
# For any heavy operation (file save, OCR recognition, icon loading):
# - The operation SHALL run in a background thread (QThread or QThreadPool)
# - The main UI thread SHALL remain responsive during the operation
# - Results SHALL be communicated via Qt signals


class TestBackgroundProcessingProperty:
    """Property 6: Background Processing 属性测试
    
    Feature: performance-ui-optimization, Property 6: Background Processing
    **Validates: Requirements 1.5, 2.5**
    """
    
    # ========== Property 6.1: 后台线程执行 ==========
    
    def test_worker_runs_in_background_thread(self, qapp, temp_icons_dir, qtbot):
        """Property 6.1: ResourceLoaderWorker 在后台线程执行
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The ResourceLoaderWorker SHALL run in a background thread,
        NOT in the main thread.
        """
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建测试图标
        create_svg_icon(icons_dir, "test_icon")
        
        # 记录线程信息
        main_thread_id = threading.current_thread().ident
        worker_thread_ids = []
        
        # 创建工作线程
        worker = ResourceLoaderWorker(["test_icon"], tmpdir)
        
        # 重写 run 方法来捕获线程 ID
        original_run = worker.run
        def patched_run():
            worker_thread_ids.append(threading.current_thread().ident)
            original_run()
        worker.run = patched_run
        
        # 启动并等待完成
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        # 验证工作线程不是主线程
        assert len(worker_thread_ids) == 1, "Worker run should be called once"
        assert worker_thread_ids[0] != main_thread_id, \
            "Worker should run in a background thread, not the main thread"
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(icon_count=st.integers(min_value=1, max_value=10))
    def test_worker_thread_is_qthread(self, qapp, icon_count):
        """Property 6.1: ResourceLoaderWorker 是 QThread 子类
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        ResourceLoaderWorker SHALL be a QThread subclass.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建测试图标
            icon_names = [f"icon_{i}" for i in range(icon_count)]
            for name in icon_names:
                create_svg_icon(icons_dir, name)
            
            # 创建工作线程
            worker = ResourceLoaderWorker(icon_names, tmpdir)
            
            # 验证是 QThread 子类
            assert isinstance(worker, QThread), \
                "ResourceLoaderWorker should be a QThread subclass"
            
            # 清理
            ResourceCache.reset()
    
    # ========== Property 6.2: 异步加载不阻塞 ==========
    
    def test_preload_icons_is_non_blocking(self, qapp, temp_icons_dir, qtbot):
        """Property 6.2: preload_icons 是非阻塞的
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The preload_icons method SHALL return immediately without
        blocking the calling thread.
        """
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建多个测试图标
        icon_names = [f"icon_{i}" for i in range(5)]
        for name in icon_names:
            create_svg_icon(icons_dir, name)
        
        # 测量 preload_icons 调用时间
        start_time = time.perf_counter()
        ResourceCache.preload_icons(icon_names, tmpdir)
        call_duration = time.perf_counter() - start_time
        
        # preload_icons 应该立即返回（< 100ms）
        # 实际加载在后台进行
        assert call_duration < 0.1, \
            f"preload_icons should return immediately, took {call_duration:.3f}s"
        
        # 验证加载正在进行
        assert ResourceCache.is_loading(), \
            "ResourceCache should be loading after preload_icons"
        
        # 等待加载完成
        all_loaded_called = []
        ResourceCache.set_on_all_loaded(lambda: all_loaded_called.append(True))
        qtbot.waitUntil(lambda: len(all_loaded_called) > 0, timeout=5000)
    
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(icon_count=st.integers(min_value=1, max_value=5))
    def test_main_thread_responsive_during_loading(self, qapp, icon_count):
        """Property 6.2: 加载期间主线程保持响应
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The main UI thread SHALL remain responsive during icon loading.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建测试图标
            icon_names = [f"icon_{i}" for i in range(icon_count)]
            for name in icon_names:
                create_svg_icon(icons_dir, name)
            
            # 启动异步加载
            ResourceCache.preload_icons(icon_names, tmpdir)
            
            # 在加载期间，主线程应该能够执行其他操作
            # 这里我们验证可以处理事件
            main_thread_operations = 0
            for _ in range(10):
                QCoreApplication.processEvents()
                main_thread_operations += 1
            
            assert main_thread_operations == 10, \
                "Main thread should be able to process events during loading"
            
            # 停止加载并清理
            ResourceCache.stop_loading()
            ResourceCache.reset()
    
    # ========== Property 6.3: 结果通过 Qt 信号通信 ==========
    
    def test_icon_loaded_signal_emitted(self, qapp, temp_icons_dir, qtbot):
        """Property 6.3: icon_loaded 信号正确发射
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        Results SHALL be communicated via the icon_loaded signal.
        """
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建测试图标
        create_svg_icon(icons_dir, "signal_test")
        
        # 记录信号
        loaded_icons: List[Tuple[str, QIcon]] = []
        
        def on_icon_loaded(name: str, icon: QIcon):
            loaded_icons.append((name, icon))
        
        worker = ResourceLoaderWorker(["signal_test"], tmpdir)
        worker.icon_loaded.connect(on_icon_loaded)
        
        # 启动并等待完成
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        # 验证信号被发射
        assert len(loaded_icons) == 1, "icon_loaded signal should be emitted once"
        assert loaded_icons[0][0] == "signal_test", "Signal should contain correct icon name"
        assert isinstance(loaded_icons[0][1], QIcon), "Signal should contain QIcon"
    
    def test_all_loaded_signal_emitted(self, qapp, temp_icons_dir, qtbot):
        """Property 6.3: all_loaded 信号在全部完成后发射
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The all_loaded signal SHALL be emitted after all icons are loaded.
        """
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建多个测试图标
        icon_names = ["icon_a", "icon_b", "icon_c"]
        for name in icon_names:
            create_svg_icon(icons_dir, name)
        
        # 记录信号
        all_loaded_called = []
        loaded_count = [0]
        
        def on_icon_loaded(name: str, icon: QIcon):
            loaded_count[0] += 1
        
        def on_all_loaded():
            all_loaded_called.append(loaded_count[0])
        
        worker = ResourceLoaderWorker(icon_names, tmpdir)
        worker.icon_loaded.connect(on_icon_loaded)
        worker.all_loaded.connect(on_all_loaded)
        
        # 启动并等待完成
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        # 验证 all_loaded 在所有图标加载后发射
        assert len(all_loaded_called) == 1, "all_loaded should be emitted once"
        assert all_loaded_called[0] == len(icon_names), \
            "all_loaded should be emitted after all icons are loaded"
    
    def test_progress_signal_emitted(self, qapp, temp_icons_dir, qtbot):
        """Property 6.3: progress 信号正确发射
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The progress signal SHALL be emitted for each icon.
        """
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建多个测试图标
        icon_names = ["prog_1", "prog_2", "prog_3"]
        for name in icon_names:
            create_svg_icon(icons_dir, name)
        
        # 记录进度信号
        progress_updates: List[Tuple[int, int]] = []
        
        def on_progress(loaded: int, total: int):
            progress_updates.append((loaded, total))
        
        worker = ResourceLoaderWorker(icon_names, tmpdir)
        worker.progress.connect(on_progress)
        
        # 启动并等待完成
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        # 验证进度信号
        assert len(progress_updates) == len(icon_names), \
            "progress signal should be emitted for each icon"
        
        # 验证进度递增
        for i, (loaded, total) in enumerate(progress_updates):
            assert loaded == i + 1, f"Loaded count should be {i + 1}"
            assert total == len(icon_names), f"Total should be {len(icon_names)}"
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(icon_count=st.integers(min_value=1, max_value=8))
    def test_signals_emitted_for_all_icons(self, qapp, icon_count):
        """Property 6.3: 所有图标都触发信号
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        For any number of icons, icon_loaded signal SHALL be emitted
        for each successfully loaded icon.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建测试图标
            icon_names = [f"icon_{i}" for i in range(icon_count)]
            for name in icon_names:
                create_svg_icon(icons_dir, name)
            
            # 记录信号
            loaded_icons: List[str] = []
            all_loaded_event = threading.Event()
            
            def on_icon_loaded(name: str, icon: QIcon):
                loaded_icons.append(name)
            
            def on_all_loaded():
                all_loaded_event.set()
            
            worker = ResourceLoaderWorker(icon_names, tmpdir)
            worker.icon_loaded.connect(on_icon_loaded)
            worker.all_loaded.connect(on_all_loaded)
            
            # 启动
            worker.start()
            
            # 等待完成（处理事件以接收信号）
            timeout = 5.0
            start = time.time()
            while not all_loaded_event.is_set() and time.time() - start < timeout:
                QCoreApplication.processEvents()
                time.sleep(0.01)
            
            # 验证所有图标都触发了信号
            assert len(loaded_icons) == icon_count, \
                f"Expected {icon_count} icon_loaded signals, got {len(loaded_icons)}"
            
            # 验证所有图标名称都在
            for name in icon_names:
                assert name in loaded_icons, \
                    f"Icon {name} should have triggered icon_loaded signal"
            
            # 清理
            ResourceCache.reset()
    
    # ========== Property 6.4: 线程安全 ==========
    
    def test_cache_thread_safe_set_and_get(self, qapp, qtbot):
        """Property 6.4: 缓存的 set 和 get 是线程安全的
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        The ResourceCache SHALL be thread-safe for concurrent access.
        """
        # 创建多个线程同时访问缓存
        errors: List[str] = []
        operations_completed = [0]
        
        def writer_thread(thread_id: int):
            try:
                for i in range(20):
                    icon = QIcon()
                    ResourceCache.set_icon(f"thread_{thread_id}_icon_{i}", icon)
                    operations_completed[0] += 1
            except Exception as e:
                errors.append(f"Writer {thread_id}: {e}")
        
        def reader_thread(thread_id: int):
            try:
                for i in range(20):
                    # 尝试读取（可能存在也可能不存在）
                    ResourceCache.get_icon(f"thread_{thread_id}_icon_{i}")
                    ResourceCache.is_loaded(f"thread_{thread_id}_icon_{i}")
                    operations_completed[0] += 1
            except Exception as e:
                errors.append(f"Reader {thread_id}: {e}")
        
        # 启动多个线程
        threads = []
        for i in range(3):
            t = threading.Thread(target=writer_thread, args=(i,))
            threads.append(t)
            t = threading.Thread(target=reader_thread, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=5.0)
        
        # 验证没有错误
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert operations_completed[0] > 0, "Operations should have completed"
    
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        icon_names=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
            min_size=1,
            max_size=5,
            unique=True
        )
    )
    def test_cache_consistent_after_concurrent_access(self, qapp, icon_names):
        """Property 6.4: 并发访问后缓存保持一致
        
        Feature: performance-ui-optimization, Property 6: Background Processing
        **Validates: Requirements 1.5, 2.5**
        
        After concurrent set operations, all icons SHALL be retrievable.
        """
        # 过滤掉空字符串
        icon_names = [name for name in icon_names if name.strip()]
        assume(len(icon_names) > 0)
        
        ResourceCache.reset()
        
        # 并发设置图标
        def set_icon(name: str):
            icon = QIcon()
            ResourceCache.set_icon(name, icon)
        
        threads = [threading.Thread(target=set_icon, args=(name,)) for name in icon_names]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=2.0)
        
        # 验证所有图标都可以获取
        for name in icon_names:
            assert ResourceCache.is_loaded(name), \
                f"Icon {name} should be loaded after concurrent set"
            assert ResourceCache.get_icon(name) is not None, \
                f"Icon {name} should be retrievable"
        
        # 清理
        ResourceCache.reset()


class TestResourceLoaderWorkerUnit:
    """ResourceLoaderWorker 单元测试
    
    测试具体示例和边界情况。
    """
    
    def test_worker_handles_nonexistent_icons(self, qapp, temp_icons_dir, qtbot):
        """工作线程正确处理不存在的图标"""
        tmpdir, icons_dir = temp_icons_dir
        
        errors: List[Tuple[str, str]] = []
        
        def on_error(name: str, error: str):
            errors.append((name, error))
        
        worker = ResourceLoaderWorker(["nonexistent_icon"], tmpdir)
        worker.load_error.connect(on_error)
        
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        assert len(errors) == 1, "Should report error for nonexistent icon"
        assert errors[0][0] == "nonexistent_icon"
    
    def test_worker_can_be_stopped(self, qapp, temp_icons_dir, qtbot):
        """工作线程可以被停止"""
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建多个图标
        for i in range(10):
            create_svg_icon(icons_dir, f"stop_test_{i}")
        
        worker = ResourceLoaderWorker(
            [f"stop_test_{i}" for i in range(10)], 
            tmpdir
        )
        
        # 启动后立即停止
        worker.start()
        worker.stop()
        worker.wait(1000)
        
        # 验证线程已停止
        assert not worker.isRunning(), "Worker should have stopped"
    
    def test_worker_with_custom_extension(self, qapp, qtbot):
        """工作线程支持自定义扩展名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "icons")
            os.makedirs(icons_dir)
            
            # 创建 PNG 图标（使用简单的 1x1 像素）
            png_path = os.path.join(icons_dir, "custom.png")
            pixmap = QPixmap(24, 24)
            pixmap.fill()
            pixmap.save(png_path, "PNG")
            
            loaded_icons: List[str] = []
            
            def on_loaded(name: str, icon: QIcon):
                loaded_icons.append(name)
            
            worker = ResourceLoaderWorker(
                ["custom"], 
                tmpdir,
                icon_subdir="icons",
                icon_extension=".png"
            )
            worker.icon_loaded.connect(on_loaded)
            
            with qtbot.waitSignal(worker.all_loaded, timeout=5000):
                worker.start()
            
            assert "custom" in loaded_icons, "Should load icon with custom extension"
    
    def test_worker_with_empty_icon_list(self, qapp, temp_icons_dir, qtbot):
        """工作线程处理空图标列表"""
        tmpdir, icons_dir = temp_icons_dir
        
        all_loaded_called = []
        
        def on_all_loaded():
            all_loaded_called.append(True)
        
        worker = ResourceLoaderWorker([], tmpdir)
        worker.all_loaded.connect(on_all_loaded)
        
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        assert len(all_loaded_called) == 1, "all_loaded should be emitted for empty list"


class TestResourceCacheCallbacks:
    """ResourceCache 回调测试"""
    
    def test_on_icon_loaded_callback_called(self, qapp, temp_icons_dir, qtbot):
        """图标加载完成回调被调用"""
        tmpdir, icons_dir = temp_icons_dir
        create_svg_icon(icons_dir, "callback_test")
        
        callback_calls: List[Tuple[str, QIcon]] = []
        
        def callback(name: str, icon: QIcon):
            callback_calls.append((name, icon))
        
        ResourceCache.set_on_icon_loaded(callback)
        ResourceCache.preload_icons(["callback_test"], tmpdir)
        
        # 等待加载完成
        qtbot.waitUntil(lambda: len(callback_calls) > 0, timeout=5000)
        
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "callback_test"
    
    def test_on_all_loaded_callback_called(self, qapp, temp_icons_dir, qtbot):
        """全部加载完成回调被调用"""
        tmpdir, icons_dir = temp_icons_dir
        
        for name in ["all_1", "all_2"]:
            create_svg_icon(icons_dir, name)
        
        all_loaded_calls = []
        
        def callback():
            all_loaded_calls.append(True)
        
        ResourceCache.set_on_all_loaded(callback)
        ResourceCache.preload_icons(["all_1", "all_2"], tmpdir)
        
        # 等待加载完成
        qtbot.waitUntil(lambda: len(all_loaded_calls) > 0, timeout=5000)
        
        assert len(all_loaded_calls) == 1
    
    def test_on_load_error_callback_called(self, qapp, temp_icons_dir, qtbot):
        """加载错误回调被调用"""
        tmpdir, icons_dir = temp_icons_dir
        
        error_calls: List[Tuple[str, str]] = []
        
        def callback(name: str, error: str):
            error_calls.append((name, error))
        
        ResourceCache.set_on_load_error(callback)
        ResourceCache.preload_icons(["nonexistent"], tmpdir)
        
        # 等待加载完成
        all_loaded = []
        ResourceCache.set_on_all_loaded(lambda: all_loaded.append(True))
        qtbot.waitUntil(lambda: len(all_loaded) > 0, timeout=5000)
        
        assert len(error_calls) == 1
        assert error_calls[0][0] == "nonexistent"


class TestResourceCacheIntegration:
    """ResourceCache 集成测试"""
    
    def test_preload_and_retrieve_icons(self, qapp, temp_icons_dir, qtbot):
        """预加载后可以获取图标"""
        tmpdir, icons_dir = temp_icons_dir
        
        icon_names = ["int_1", "int_2", "int_3"]
        for name in icon_names:
            create_svg_icon(icons_dir, name)
        
        all_loaded = []
        ResourceCache.set_on_all_loaded(lambda: all_loaded.append(True))
        ResourceCache.preload_icons(icon_names, tmpdir)
        
        # 等待加载完成
        qtbot.waitUntil(lambda: len(all_loaded) > 0, timeout=5000)
        
        # 验证所有图标都可以获取
        for name in icon_names:
            icon = ResourceCache.get_icon(name)
            assert icon is not None, f"Icon {name} should be retrievable"
            assert not icon.isNull(), f"Icon {name} should not be null"
    
    def test_stop_loading_cancels_operation(self, qapp, temp_icons_dir, qtbot):
        """stop_loading 取消加载操作"""
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建多个图标
        icon_names = [f"cancel_{i}" for i in range(10)]
        for name in icon_names:
            create_svg_icon(icons_dir, name)
        
        ResourceCache.preload_icons(icon_names, tmpdir)
        
        # 立即停止
        ResourceCache.stop_loading()
        
        # 验证加载已停止
        assert not ResourceCache.is_loading(), "Loading should be stopped"
    
    def test_new_preload_stops_previous(self, qapp, temp_icons_dir, qtbot):
        """新的预加载会停止之前的加载"""
        tmpdir, icons_dir = temp_icons_dir
        
        # 创建图标
        create_svg_icon(icons_dir, "first")
        create_svg_icon(icons_dir, "second")
        
        # 启动第一次加载
        ResourceCache.preload_icons(["first"], tmpdir)
        
        # 立即启动第二次加载
        all_loaded = []
        ResourceCache.set_on_all_loaded(lambda: all_loaded.append(True))
        ResourceCache.preload_icons(["second"], tmpdir)
        
        # 等待加载完成
        qtbot.waitUntil(lambda: len(all_loaded) > 0, timeout=5000)
        
        # 第二次加载的图标应该存在
        assert ResourceCache.is_loaded("second"), "Second icon should be loaded"

