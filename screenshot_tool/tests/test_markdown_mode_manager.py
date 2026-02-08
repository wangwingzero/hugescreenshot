# =====================================================
# =============== Markdown 模式管理器测试 ===============
# =====================================================

"""
Markdown 模式管理器属性测试

Feature: web-to-markdown
Property 1: Browser Detection Correctness
Property 2: URL Extraction Validity
Validates: Requirements 2.1, 2.2, 2.3
"""

import sys
import pytest
from unittest.mock import MagicMock, patch

from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.core.markdown_mode_manager import MarkdownModeManager


class TestBrowserDetection:
    """Property 1: Browser Detection Correctness 测试
    
    *For any* window handle, if the window class name matches a known browser class 
    (Chrome_WidgetWin_1, MozillaWindowClass, etc.), the `_is_browser_window` function 
    SHALL return True; otherwise it SHALL return False.
    
    **Validates: Requirements 2.1, 2.2**
    """
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        return MarkdownModeManager()
    
    def test_browser_classes_defined(self, manager):
        """验证浏览器类名集合已定义"""
        assert hasattr(manager, 'BROWSER_CLASSES')
        assert len(manager.BROWSER_CLASSES) > 0
        
        # 验证包含主流浏览器
        assert "Chrome_WidgetWin_1" in manager.BROWSER_CLASSES  # Chrome, Edge
        assert "MozillaWindowClass" in manager.BROWSER_CLASSES  # Firefox
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_is_browser_window_with_zero_hwnd(self, manager):
        """hwnd 为 0 时应返回 False"""
        result = manager._is_browser_window(0)
        assert result is False
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    @patch('win32gui.GetClassName')
    @patch('win32gui.GetParent')
    def test_is_browser_window_chrome(self, mock_get_parent, mock_get_class, manager):
        """Chrome 窗口应被正确检测"""
        mock_get_class.return_value = "Chrome_WidgetWin_1"
        mock_get_parent.return_value = 0
        
        result = manager._is_browser_window(12345)
        assert result is True
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    @patch('win32gui.GetClassName')
    @patch('win32gui.GetParent')
    def test_is_browser_window_firefox(self, mock_get_parent, mock_get_class, manager):
        """Firefox 窗口应被正确检测"""
        mock_get_class.return_value = "MozillaWindowClass"
        mock_get_parent.return_value = 0
        
        result = manager._is_browser_window(12345)
        assert result is True
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    @patch('win32gui.GetClassName')
    @patch('win32gui.GetParent')
    def test_is_browser_window_notepad(self, mock_get_parent, mock_get_class, manager):
        """非浏览器窗口应返回 False"""
        mock_get_class.return_value = "Notepad"
        mock_get_parent.return_value = 0
        
        result = manager._is_browser_window(12345)
        assert result is False
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    @patch('win32gui.GetClassName')
    @patch('win32gui.GetParent')
    def test_is_browser_window_child_of_chrome(self, mock_get_parent, mock_get_class, manager):
        """Chrome 子窗口应被正确检测"""
        # 模拟子窗口 -> Chrome 顶层窗口
        call_count = [0]
        def get_class_side_effect(hwnd):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Chrome_RenderWidgetHostHWND"  # 子窗口
            return "Chrome_WidgetWin_1"  # 父窗口
        
        parent_call_count = [0]
        def get_parent_side_effect(hwnd):
            parent_call_count[0] += 1
            if parent_call_count[0] == 1:
                return 99999  # 返回父窗口句柄
            return 0  # 没有更多父窗口
        
        mock_get_class.side_effect = get_class_side_effect
        mock_get_parent.side_effect = get_parent_side_effect
        
        result = manager._is_browser_window(12345)
        assert result is True


class TestURLExtraction:
    """Property 2: URL Extraction Validity 测试
    
    *For any* valid browser window with a loaded page, the `_get_browser_url` function 
    SHALL return a string that is either empty (if extraction fails) or a valid URL 
    starting with "http://" or "https://".
    
    **Validates: Requirements 2.3**
    """
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        return MarkdownModeManager()
    
    def test_get_browser_url_with_zero_hwnd(self, manager):
        """hwnd 为 0 时应返回空字符串"""
        result = manager._get_browser_url(0)
        assert result == ""
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_get_browser_url_returns_string(self, manager):
        """返回值应为字符串类型"""
        # 使用无效句柄测试
        result = manager._get_browser_url(1)
        assert isinstance(result, str)
    
    @given(st.integers(min_value=1, max_value=1000000))
    @settings(max_examples=10, deadline=500, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_get_browser_url_always_returns_string(self, hwnd):
        """Property 2: URL 提取总是返回字符串
        
        验证对于任意窗口句柄，返回值要么是空字符串，要么是有效 URL
        """
        manager = MarkdownModeManager()
        result = manager._get_browser_url(hwnd)
        
        # 结果必须是字符串
        assert isinstance(result, str)
        
        # 如果非空，必须是有效 URL 格式
        if result:
            assert result.startswith("http://") or result.startswith("https://"), \
                f"URL 格式无效: {result}"


class TestModeActivation:
    """模式激活/停用测试"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        return MarkdownModeManager()
    
    def test_initial_state(self, manager):
        """初始状态应为未激活"""
        assert manager.is_active is False
    
    def test_activate_changes_state(self, manager):
        """激活应改变状态"""
        # Mock cursor overlay to avoid GUI issues in tests
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_install_mouse_hook'):
                with patch.object(manager, '_install_keyboard_hook'):
                    manager.activate()
                    assert manager.is_active is True
    
    def test_deactivate_changes_state(self, manager):
        """停用应改变状态"""
        # 先激活
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_install_mouse_hook'):
                with patch.object(manager, '_install_keyboard_hook'):
                    manager.activate()
        
        # 再停用
        with patch.object(manager, '_hide_cursor_overlay'):
            with patch.object(manager, '_uninstall_mouse_hook'):
                with patch.object(manager, '_uninstall_keyboard_hook'):
                    manager.deactivate()
                    assert manager.is_active is False
    
    def test_toggle(self, manager):
        """切换应正确工作"""
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_hide_cursor_overlay'):
                with patch.object(manager, '_install_mouse_hook'):
                    with patch.object(manager, '_uninstall_mouse_hook'):
                        with patch.object(manager, '_install_keyboard_hook'):
                            with patch.object(manager, '_uninstall_keyboard_hook'):
                                # 初始未激活
                                assert manager.is_active is False
                                
                                # 切换到激活
                                manager.toggle()
                                assert manager.is_active is True
                                
                                # 切换到未激活
                                manager.toggle()
                                assert manager.is_active is False
    
    def test_double_activate_is_safe(self, manager):
        """重复激活应安全"""
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_install_mouse_hook'):
                with patch.object(manager, '_install_keyboard_hook'):
                    manager.activate()
                    manager.activate()  # 第二次激活
                    assert manager.is_active is True
    
    def test_double_deactivate_is_safe(self, manager):
        """重复停用应安全"""
        with patch.object(manager, '_hide_cursor_overlay'):
            with patch.object(manager, '_uninstall_mouse_hook'):
                with patch.object(manager, '_uninstall_keyboard_hook'):
                    manager.deactivate()
                    manager.deactivate()  # 第二次停用
                    assert manager.is_active is False


class TestSignals:
    """信号测试"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        return MarkdownModeManager()
    
    def test_mode_changed_signal_on_activate(self, manager):
        """激活时应发出 mode_changed 信号"""
        signal_received = []
        manager.mode_changed.connect(lambda x: signal_received.append(x))
        
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_install_mouse_hook'):
                with patch.object(manager, '_install_keyboard_hook'):
                    manager.activate()
        
        assert len(signal_received) == 1
        assert signal_received[0] is True
    
    def test_mode_changed_signal_on_deactivate(self, manager):
        """停用时应发出 mode_changed 信号"""
        # 先激活
        with patch.object(manager, '_show_cursor_overlay'):
            with patch.object(manager, '_install_mouse_hook'):
                with patch.object(manager, '_install_keyboard_hook'):
                    manager.activate()
        
        signal_received = []
        manager.mode_changed.connect(lambda x: signal_received.append(x))
        
        with patch.object(manager, '_hide_cursor_overlay'):
            with patch.object(manager, '_uninstall_mouse_hook'):
                with patch.object(manager, '_uninstall_keyboard_hook'):
                    manager.deactivate()
        
        assert len(signal_received) == 1
        assert signal_received[0] is False


class TestCleanup:
    """清理测试"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        return MarkdownModeManager()
    
    def test_cleanup_is_safe(self, manager):
        """cleanup 应安全执行"""
        manager.cleanup()
        assert manager.is_active is False
    
    def test_cleanup_multiple_times_is_safe(self, manager):
        """多次 cleanup 应安全"""
        manager.cleanup()
        manager.cleanup()
        manager.cleanup()
        assert manager.is_active is False
