"""ResourceCache 单元测试

Feature: performance-ui-optimization
Requirements: 1.5

测试资源缓存的基本功能和异步加载。
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from screenshot_tool.core.resource_cache import (
    ResourceCache,
    ResourceLoaderWorker,
    get_cached_icon,
    get_cached_pixmap,
)


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


class TestResourceCache:
    """ResourceCache 单元测试"""
    
    def test_set_and_get_icon(self, qapp):
        """测试设置和获取图标"""
        icon = QIcon()
        ResourceCache.set_icon("test_icon", icon)
        
        result = ResourceCache.get_icon("test_icon")
        assert result is not None
    
    def test_get_nonexistent_icon_returns_none(self, qapp):
        """测试获取不存在的图标返回 None"""
        result = ResourceCache.get_icon("nonexistent")
        assert result is None
    
    def test_set_and_get_pixmap(self, qapp):
        """测试设置和获取像素图"""
        pixmap = QPixmap(10, 10)
        ResourceCache.set_pixmap("test_pixmap", pixmap)
        
        result = ResourceCache.get_pixmap("test_pixmap")
        assert result is not None
    
    def test_get_nonexistent_pixmap_returns_none(self, qapp):
        """测试获取不存在的像素图返回 None"""
        result = ResourceCache.get_pixmap("nonexistent")
        assert result is None
    
    def test_is_loaded(self, qapp):
        """测试 is_loaded 方法"""
        assert not ResourceCache.is_loaded("test_icon")
        
        icon = QIcon()
        ResourceCache.set_icon("test_icon", icon)
        
        assert ResourceCache.is_loaded("test_icon")
    
    def test_is_pixmap_loaded(self, qapp):
        """测试 is_pixmap_loaded 方法"""
        assert not ResourceCache.is_pixmap_loaded("test_pixmap")
        
        pixmap = QPixmap(10, 10)
        ResourceCache.set_pixmap("test_pixmap", pixmap)
        
        assert ResourceCache.is_pixmap_loaded("test_pixmap")
    
    def test_get_all_icons(self, qapp):
        """测试获取所有图标"""
        icon1 = QIcon()
        icon2 = QIcon()
        ResourceCache.set_icon("icon1", icon1)
        ResourceCache.set_icon("icon2", icon2)
        
        all_icons = ResourceCache.get_all_icons()
        assert len(all_icons) == 2
        assert "icon1" in all_icons
        assert "icon2" in all_icons
    
    def test_get_all_pixmaps(self, qapp):
        """测试获取所有像素图"""
        pixmap1 = QPixmap(10, 10)
        pixmap2 = QPixmap(20, 20)
        ResourceCache.set_pixmap("pixmap1", pixmap1)
        ResourceCache.set_pixmap("pixmap2", pixmap2)
        
        all_pixmaps = ResourceCache.get_all_pixmaps()
        assert len(all_pixmaps) == 2
        assert "pixmap1" in all_pixmaps
        assert "pixmap2" in all_pixmaps
    
    def test_get_loaded_icon_names(self, qapp):
        """测试获取已加载图标名称列表"""
        icon1 = QIcon()
        icon2 = QIcon()
        ResourceCache.set_icon("icon1", icon1)
        ResourceCache.set_icon("icon2", icon2)
        
        names = ResourceCache.get_loaded_icon_names()
        assert len(names) == 2
        assert "icon1" in names
        assert "icon2" in names
    
    def test_get_icon_count(self, qapp):
        """测试获取图标数量"""
        assert ResourceCache.get_icon_count() == 0
        
        ResourceCache.set_icon("icon1", QIcon())
        assert ResourceCache.get_icon_count() == 1
        
        ResourceCache.set_icon("icon2", QIcon())
        assert ResourceCache.get_icon_count() == 2
    
    def test_get_pixmap_count(self, qapp):
        """测试获取像素图数量"""
        assert ResourceCache.get_pixmap_count() == 0
        
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        assert ResourceCache.get_pixmap_count() == 1
    
    def test_remove_icon(self, qapp):
        """测试移除图标"""
        ResourceCache.set_icon("test_icon", QIcon())
        assert ResourceCache.is_loaded("test_icon")
        
        result = ResourceCache.remove_icon("test_icon")
        assert result is True
        assert not ResourceCache.is_loaded("test_icon")
    
    def test_remove_nonexistent_icon(self, qapp):
        """测试移除不存在的图标"""
        result = ResourceCache.remove_icon("nonexistent")
        assert result is False
    
    def test_remove_pixmap(self, qapp):
        """测试移除像素图"""
        ResourceCache.set_pixmap("test_pixmap", QPixmap(10, 10))
        assert ResourceCache.is_pixmap_loaded("test_pixmap")
        
        result = ResourceCache.remove_pixmap("test_pixmap")
        assert result is True
        assert not ResourceCache.is_pixmap_loaded("test_pixmap")
    
    def test_clear(self, qapp):
        """测试清空所有缓存"""
        ResourceCache.set_icon("icon1", QIcon())
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        
        ResourceCache.clear()
        
        assert ResourceCache.get_icon_count() == 0
        assert ResourceCache.get_pixmap_count() == 0
    
    def test_clear_icons(self, qapp):
        """测试清空图标缓存"""
        ResourceCache.set_icon("icon1", QIcon())
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        
        ResourceCache.clear_icons()
        
        assert ResourceCache.get_icon_count() == 0
        assert ResourceCache.get_pixmap_count() == 1
    
    def test_clear_pixmaps(self, qapp):
        """测试清空像素图缓存"""
        ResourceCache.set_icon("icon1", QIcon())
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        
        ResourceCache.clear_pixmaps()
        
        assert ResourceCache.get_icon_count() == 1
        assert ResourceCache.get_pixmap_count() == 0
    
    def test_get_stats(self, qapp):
        """测试获取统计信息"""
        ResourceCache.set_icon("icon1", QIcon())
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        
        stats = ResourceCache.get_stats()
        
        assert stats["icon_count"] == 1
        assert stats["pixmap_count"] == 1
        assert stats["load_count"] == 1  # set_icon 增加 load_count
        assert stats["error_count"] == 0
        assert stats["is_loading"] is False
    
    def test_reset_stats(self, qapp):
        """测试重置统计信息"""
        ResourceCache.set_icon("icon1", QIcon())
        
        stats_before = ResourceCache.get_stats()
        assert stats_before["load_count"] == 1
        
        ResourceCache.reset_stats()
        
        stats_after = ResourceCache.get_stats()
        assert stats_after["load_count"] == 0
        assert stats_after["error_count"] == 0
    
    def test_reset(self, qapp):
        """测试完全重置"""
        ResourceCache.set_icon("icon1", QIcon())
        ResourceCache.set_pixmap("pixmap1", QPixmap(10, 10))
        ResourceCache.set_on_icon_loaded(lambda n, i: None)
        
        ResourceCache.reset()
        
        assert ResourceCache.get_icon_count() == 0
        assert ResourceCache.get_pixmap_count() == 0
        stats = ResourceCache.get_stats()
        assert stats["load_count"] == 0
    
    def test_on_icon_loaded_callback(self, qapp):
        """测试图标加载完成回调"""
        callback_called = []
        
        def callback(name, icon):
            callback_called.append((name, icon))
        
        ResourceCache.set_on_icon_loaded(callback)
        ResourceCache.set_icon("test_icon", QIcon())
        
        assert len(callback_called) == 1
        assert callback_called[0][0] == "test_icon"
    
    def test_is_loading_initially_false(self, qapp):
        """测试初始状态下 is_loading 为 False"""
        assert ResourceCache.is_loading() is False


class TestResourceLoaderWorker:
    """ResourceLoaderWorker 单元测试"""
    
    def test_worker_creation(self, qapp):
        """测试工作线程创建"""
        worker = ResourceLoaderWorker(["icon1", "icon2"], "/tmp")
        assert worker is not None
    
    def test_worker_with_nonexistent_icons(self, qapp, qtbot):
        """测试加载不存在的图标"""
        errors = []
        
        def on_error(name, error):
            errors.append((name, error))
        
        worker = ResourceLoaderWorker(["nonexistent"], "/tmp")
        worker.load_error.connect(on_error)
        
        with qtbot.waitSignal(worker.all_loaded, timeout=5000):
            worker.start()
        
        assert len(errors) == 1
        assert errors[0][0] == "nonexistent"
    
    def test_worker_stop(self, qapp):
        """测试停止工作线程"""
        worker = ResourceLoaderWorker(["icon1"], "/tmp")
        worker.stop()
        assert worker._should_stop is True
    
    def test_worker_with_real_icon(self, qapp, qtbot):
        """测试加载真实图标文件"""
        # 创建临时目录和图标文件
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建一个简单的 SVG 文件
            svg_content = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="red"/></svg>'
            svg_path = os.path.join(icons_dir, "test.svg")
            with open(svg_path, "w") as f:
                f.write(svg_content)
            
            loaded_icons = []
            
            def on_loaded(name, icon):
                loaded_icons.append((name, icon))
            
            worker = ResourceLoaderWorker(["test"], tmpdir)
            worker.icon_loaded.connect(on_loaded)
            
            with qtbot.waitSignal(worker.all_loaded, timeout=5000):
                worker.start()
            
            assert len(loaded_icons) == 1
            assert loaded_icons[0][0] == "test"


class TestHelperFunctions:
    """辅助函数测试"""
    
    def test_get_cached_icon_with_fallback(self, qapp):
        """测试 get_cached_icon 带 fallback"""
        fallback = QIcon()
        
        # 图标不存在时返回 fallback
        result = get_cached_icon("nonexistent", fallback)
        assert result is fallback
        
        # 图标存在时返回缓存的图标
        cached_icon = QIcon()
        ResourceCache.set_icon("test", cached_icon)
        result = get_cached_icon("test", fallback)
        assert result is not fallback
    
    def test_get_cached_pixmap_with_fallback(self, qapp):
        """测试 get_cached_pixmap 带 fallback"""
        fallback = QPixmap(10, 10)
        
        # 像素图不存在时返回 fallback
        result = get_cached_pixmap("nonexistent", fallback)
        assert result is fallback
        
        # 像素图存在时返回缓存的像素图
        cached_pixmap = QPixmap(20, 20)
        ResourceCache.set_pixmap("test", cached_pixmap)
        result = get_cached_pixmap("test", fallback)
        assert result is not fallback


class TestPreloadIcons:
    """预加载图标测试"""
    
    def test_preload_icons_with_real_files(self, qapp, qtbot):
        """测试预加载真实图标文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建多个 SVG 文件
            for name in ["icon1", "icon2", "icon3"]:
                svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="blue"/></svg>'
                svg_path = os.path.join(icons_dir, f"{name}.svg")
                with open(svg_path, "w") as f:
                    f.write(svg_content)
            
            all_loaded_called = []
            
            def on_all_loaded():
                all_loaded_called.append(True)
            
            ResourceCache.set_on_all_loaded(on_all_loaded)
            ResourceCache.preload_icons(["icon1", "icon2", "icon3"], tmpdir)
            
            # 等待加载完成
            qtbot.waitUntil(lambda: len(all_loaded_called) > 0, timeout=5000)
            
            # 验证所有图标都已加载
            assert ResourceCache.is_loaded("icon1")
            assert ResourceCache.is_loaded("icon2")
            assert ResourceCache.is_loaded("icon3")
            assert ResourceCache.get_icon_count() == 3
    
    def test_preload_stops_previous_loading(self, qapp, qtbot):
        """测试预加载会停止之前的加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            icons_dir = os.path.join(tmpdir, "resources", "icons")
            os.makedirs(icons_dir)
            
            # 创建图标文件
            svg_content = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="green"/></svg>'
            for name in ["a", "b"]:
                svg_path = os.path.join(icons_dir, f"{name}.svg")
                with open(svg_path, "w") as f:
                    f.write(svg_content)
            
            # 启动第一次加载
            ResourceCache.preload_icons(["a"], tmpdir)
            
            # 立即启动第二次加载（应该停止第一次）
            all_loaded_called = []
            ResourceCache.set_on_all_loaded(lambda: all_loaded_called.append(True))
            ResourceCache.preload_icons(["b"], tmpdir)
            
            # 等待加载完成
            qtbot.waitUntil(lambda: len(all_loaded_called) > 0, timeout=5000)
            
            # 第二次加载的图标应该存在
            assert ResourceCache.is_loaded("b")
