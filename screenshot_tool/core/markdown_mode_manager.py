# =====================================================
# =============== Markdown 模式管理器 ===============
# =====================================================

"""
Markdown 模式管理器 - 管理托盘菜单触发、鼠标图标、浏览器窗口点击检测

用于管理 Markdown 模式的激活、鼠标点击检测、URL 提取和转换触发。
点击浏览器窗口时，获取当前 URL 并触发转换信号。

Feature: web-to-markdown
Requirements: 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5
"""

import sys
import weakref
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QToolTip
from PySide6.QtGui import QCursor

# 调试日志（模块级别，避免重复导入）
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")

# 父窗口遍历最大深度，防止无限循环（跨平台常量）
MAX_PARENT_DEPTH = 50

# Windows API 常量和类型（仅在 Windows 上导入）
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    
    WH_MOUSE_LL = 14
    WH_KEYBOARD_LL = 13
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204
    WM_KEYDOWN = 0x0100
    VK_ESCAPE = 0x1B
    
    # 鼠标钩子回调类型 - 使用 use_last_error=True 以便获取错误码
    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long,  # 返回值 LRESULT
        ctypes.c_int,   # nCode
        wintypes.WPARAM,  # wParam
        wintypes.LPARAM,  # lParam
        use_last_error=True
    )
    
    class MSLLHOOKSTRUCT(ctypes.Structure):
        """低级鼠标钩子结构"""
        _fields_ = [
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]
    
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        """低级键盘钩子结构"""
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]
    
    # 定义 SetWindowsHookExW 函数原型
    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _SetWindowsHookExW = _user32.SetWindowsHookExW
    _SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    _SetWindowsHookExW.restype = wintypes.HHOOK
    
    _UnhookWindowsHookEx = _user32.UnhookWindowsHookEx
    _UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    _UnhookWindowsHookEx.restype = wintypes.BOOL
    
    _CallNextHookEx = _user32.CallNextHookEx
    _CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _CallNextHookEx.restype = ctypes.c_long


class MarkdownModeManager(QObject):
    """Markdown 模式管理器
    
    管理 Markdown 模式的激活、鼠标点击检测、URL 提取和转换触发。
    点击浏览器窗口时，获取当前 URL 并触发转换信号。
    
    信号:
        convert_triggered: 转换触发信号，参数为 URL
        mode_changed: 模式变化信号，参数为是否激活
        warning_message: 警告消息信号
        error_occurred: 错误发生信号
    
    使用方法:
        manager = MarkdownModeManager()
        manager.convert_triggered.connect(on_convert)
        manager.activate()  # 激活模式
        manager.deactivate()  # 停用模式
        
    Feature: web-to-markdown
    Requirements: 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5
    """
    
    # 信号定义
    convert_triggered = Signal(str)  # 参数为 URL
    mode_changed = Signal(bool)  # 参数为是否激活
    warning_message = Signal(str)  # 警告消息
    error_occurred = Signal(str)  # 错误消息
    convert_finished = Signal(object)  # 转换完成信号，参数为 ConversionResult
    
    # Markdown 模式图标
    MARKDOWN_ICON = "📝"
    
    # 支持的浏览器窗口类名
    # Property 1: Browser Detection Correctness
    BROWSER_CLASSES = frozenset({
        "Chrome_WidgetWin_1",      # Chrome, Edge (Chromium)
        "MozillaWindowClass",       # Firefox
        "IEFrame",                  # IE
        "ApplicationFrameWindow",   # UWP Edge
    })
    
    def __init__(self, parent=None):
        """初始化模式管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self._active = False
        self._cursor_overlay = None
        self._mouse_hook = None
        self._keyboard_hook = None
        self._hook_proc = None  # 保持回调引用，防止被垃圾回收
        self._kb_hook_proc = None  # 键盘钩子回调引用
        self._is_cleaning_up = False  # 防止重复清理
        self._ignore_esc = False  # 忽略 Esc 键标志（用于模拟按键时）
    
    def __del__(self):
        """析构函数，确保钩子被卸载"""
        try:
            self.cleanup()
        except Exception:
            pass  # 析构时忽略异常
    
    @property
    def is_active(self) -> bool:
        """是否处于 Markdown 模式
        
        Returns:
            是否激活
        """
        return self._active
    
    def activate(self):
        """激活 Markdown 模式
        
        Requirements: 1.2, 1.3
        """
        if self._active or self._is_cleaning_up:
            return
        
        _debug_log("激活 Markdown 模式", "MARKDOWN")
        self._active = True
        self._show_cursor_overlay()
        self._install_mouse_hook()
        self._install_keyboard_hook()
        self.mode_changed.emit(True)
    
    def deactivate(self):
        """停用 Markdown 模式
        
        Requirements: 1.4
        """
        if not self._active:
            return
        
        _debug_log("停用 Markdown 模式", "MARKDOWN")
        self._active = False
        self._hide_cursor_overlay()
        self._uninstall_mouse_hook()
        self._uninstall_keyboard_hook()
        self.mode_changed.emit(False)
    
    def toggle(self):
        """切换 Markdown 模式"""
        if self._active:
            self.deactivate()
        else:
            self.activate()
    
    def _show_cursor_overlay(self):
        """显示鼠标图标
        
        Requirements: 1.3
        """
        if self._cursor_overlay is None:
            from screenshot_tool.ui.cursor_overlay import CursorOverlay
            self._cursor_overlay = CursorOverlay(text=self.MARKDOWN_ICON)
        else:
            self._cursor_overlay.set_text(self.MARKDOWN_ICON)
        self._cursor_overlay.show_overlay()
    
    def _hide_cursor_overlay(self):
        """隐藏鼠标图标"""
        if self._cursor_overlay:
            self._cursor_overlay.hide_overlay()

    def _install_mouse_hook(self):
        """安装全局鼠标钩子"""
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._mouse_hook:
            return
        
        import ctypes
        
        # 使用弱引用避免循环引用，同时在回调中检查对象是否存活
        weak_self = weakref.ref(self)
        
        # 创建回调函数 - 必须返回 LRESULT (c_long)
        def low_level_mouse_proc(nCode, wParam, lParam):
            # 获取当前钩子句柄（在闭包外部捕获）
            current_hook = self._mouse_hook
            
            try:
                obj = weak_self()
                if obj is not None and nCode >= 0:
                    if wParam == WM_LBUTTONDOWN:
                        # 获取鼠标位置
                        hook_struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        x, y = hook_struct.pt.x, hook_struct.pt.y
                        
                        _debug_log(f"Markdown模式鼠标钩子捕获左键点击: ({x}, {y})", "MARKDOWN")
                        
                        # 使用 QTimer 在主线程处理点击
                        QTimer.singleShot(0, lambda _x=x, _y=y, _obj=obj: _obj._on_mouse_click(_x, _y) if _obj._active else None)
                    
                    elif wParam == WM_RBUTTONDOWN:
                        # 右键取消模式
                        _debug_log("Markdown模式检测到右键点击，取消模式", "MARKDOWN")
                        QTimer.singleShot(0, obj.deactivate)
            except Exception as e:
                _debug_log(f"Markdown模式鼠标钩子回调异常: {e}", "MARKDOWN")
            
            # 必须调用 CallNextHookEx，否则会阻塞其他程序
            return _CallNextHookEx(current_hook, nCode, wParam, lParam)
        
        # 保持回调引用
        self._hook_proc = HOOKPROC(low_level_mouse_proc)
        
        # 安装钩子 - 使用 None 作为 hMod 参数（对于低级钩子）
        self._mouse_hook = _SetWindowsHookExW(
            WH_MOUSE_LL,
            self._hook_proc,
            None,  # 低级钩子不需要模块句柄
            0
        )
        
        # 检查钩子是否安装成功
        if not self._mouse_hook:
            error_code = ctypes.get_last_error()
            _debug_log(f"Markdown模式鼠标钩子安装失败, 错误码: {error_code}", "MARKDOWN")
            self._hook_proc = None
        else:
            _debug_log(f"Markdown模式鼠标钩子安装成功, handle={self._mouse_hook}", "MARKDOWN")
    
    def _uninstall_mouse_hook(self):
        """卸载鼠标钩子"""
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._mouse_hook:
            try:
                _UnhookWindowsHookEx(self._mouse_hook)
                _debug_log("Markdown模式鼠标钩子已卸载", "MARKDOWN")
            except Exception as e:
                _debug_log(f"卸载Markdown模式鼠标钩子异常: {e}", "MARKDOWN")
            finally:
                self._mouse_hook = None
                self._hook_proc = None
    
    def _install_keyboard_hook(self):
        """安装全局键盘钩子（用于 Esc 取消）
        
        Requirements: 1.4
        """
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._keyboard_hook:
            return
        
        import ctypes
        
        # 使用弱引用避免循环引用
        weak_self = weakref.ref(self)
        
        # 创建回调函数 - 必须返回 LRESULT (c_long)
        def low_level_keyboard_proc(nCode, wParam, lParam):
            # 获取当前钩子句柄
            current_hook = self._keyboard_hook
            
            try:
                obj = weak_self()
                if obj is not None and nCode >= 0 and wParam == WM_KEYDOWN:
                    # 获取按键
                    hook_struct = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk_code = hook_struct.vkCode
                    
                    # 检测 Esc 键（忽略模拟按键时的 Esc）
                    if vk_code == VK_ESCAPE and obj._active and not obj._ignore_esc:
                        _debug_log("Markdown模式检测到 Esc 键，取消模式", "MARKDOWN")
                        # 使用 QTimer 在主线程处理
                        QTimer.singleShot(0, obj.deactivate)
                        # 不阻止事件传递，让其他程序也能收到 Esc
            except Exception as e:
                _debug_log(f"Markdown模式键盘钩子回调异常: {e}", "MARKDOWN")
            
            # 必须调用 CallNextHookEx，否则会阻塞其他程序
            return _CallNextHookEx(current_hook, nCode, wParam, lParam)
        
        # 保持回调引用
        self._kb_hook_proc = HOOKPROC(low_level_keyboard_proc)
        
        # 安装钩子 - 使用 None 作为 hMod 参数（对于低级钩子）
        self._keyboard_hook = _SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._kb_hook_proc,
            None,  # 低级钩子不需要模块句柄
            0
        )
        
        # 检查钩子是否安装成功
        if not self._keyboard_hook:
            error_code = ctypes.get_last_error()
            _debug_log(f"Markdown模式键盘钩子安装失败, 错误码: {error_code}", "MARKDOWN")
            self._kb_hook_proc = None
        else:
            _debug_log(f"Markdown模式键盘钩子安装成功, handle={self._keyboard_hook}", "MARKDOWN")
    
    def _uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._keyboard_hook:
            try:
                _UnhookWindowsHookEx(self._keyboard_hook)
                _debug_log("Markdown模式键盘钩子已卸载", "MARKDOWN")
            except Exception as e:
                _debug_log(f"卸载Markdown模式键盘钩子异常: {e}", "MARKDOWN")
            finally:
                self._keyboard_hook = None
                self._kb_hook_proc = None
    
    def _on_mouse_click(self, x: int, y: int):
        """鼠标点击处理
        
        Args:
            x: 点击X坐标
            y: 点击Y坐标
            
        Requirements: 2.4, 2.5
        """
        _debug_log(f"Markdown模式 _on_mouse_click 被调用: ({x}, {y}), active={self._active}", "MARKDOWN")
        
        if not self._active:
            return
        
        # 获取点击位置的窗口句柄
        hwnd = self._get_window_at_point(x, y)
        _debug_log(f"Markdown模式点击位置窗口句柄: {hwnd}", "MARKDOWN")
        
        if hwnd == 0:
            _debug_log("获取窗口句柄失败 (hwnd=0)", "MARKDOWN")
            self._show_warning("无法获取窗口信息")
            return
        
        # 检测是否为浏览器窗口
        is_browser = self._is_browser_window(hwnd)
        _debug_log(f"是否为浏览器窗口: {is_browser}", "MARKDOWN")
        
        if is_browser:
            # 获取浏览器 URL
            url = self._get_browser_url(hwnd)
            _debug_log(f"获取到浏览器 URL: {url}", "MARKDOWN")
            
            if url and (url.startswith("http://") or url.startswith("https://")):
                self.deactivate()
                _debug_log(f"触发转换信号, url={url}", "MARKDOWN")
                self.convert_triggered.emit(url)
            else:
                self._show_warning("无法获取网页地址")
        else:
            self._show_warning("请点击浏览器窗口")
    
    def _get_window_at_point(self, x: int, y: int) -> int:
        """获取指定坐标的窗口句柄
        
        Args:
            x: X坐标
            y: Y坐标
            
        Returns:
            窗口句柄，失败返回 0
        """
        if sys.platform != 'win32':
            return 0
        
        try:
            import win32gui
            return win32gui.WindowFromPoint((x, y))
        except Exception as e:
            _debug_log(f"Markdown模式获取窗口句柄失败: {e}", "MARKDOWN")
            return 0

    def _is_browser_window(self, hwnd: int) -> bool:
        """检测是否为浏览器窗口
        
        检查当前窗口或其父窗口链是否为已知浏览器窗口类。
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            是否为浏览器窗口
            
        Requirements: 2.1, 2.2
        Property 1: Browser Detection Correctness
        """
        if hwnd == 0 or sys.platform != 'win32':
            return False
        
        try:
            import win32gui
            
            # 检查当前窗口
            class_name = win32gui.GetClassName(hwnd)
            _debug_log(f"Markdown模式窗口类名: {class_name}", "MARKDOWN")
            
            if class_name in self.BROWSER_CLASSES:
                return True
            
            # 检查父窗口链，限制最大深度防止无限循环
            visited = {hwnd}  # 记录已访问的窗口，防止循环
            parent = win32gui.GetParent(hwnd)
            depth = 0
            
            while parent and depth < MAX_PARENT_DEPTH:
                if parent in visited:
                    # 检测到循环，退出
                    _debug_log(f"Markdown模式检测到窗口父子循环: {parent}", "MARKDOWN")
                    break
                
                visited.add(parent)
                
                try:
                    parent_class = win32gui.GetClassName(parent)
                    if parent_class in self.BROWSER_CLASSES:
                        _debug_log(f"Markdown模式找到浏览器顶层窗口: {parent_class}", "MARKDOWN")
                        return True
                    parent = win32gui.GetParent(parent)
                    depth += 1
                except Exception:
                    break
            
            return False
        except Exception as e:
            _debug_log(f"Markdown模式检测浏览器窗口异常: {e}", "MARKDOWN")
            return False
    
    def _get_browser_url(self, hwnd: int) -> str:
        """从浏览器窗口获取当前 URL
        
        通过模拟 Ctrl+L 聚焦地址栏，然后 Ctrl+C 复制地址栏内容获取 URL。
        无论用户点击浏览器窗口的哪个位置，都能正确获取当前页面的 URL。
        获取成功后会清除剪贴板，防止下次读取到旧 URL。
        
        Args:
            hwnd: 窗口句柄（用于浏览器窗口验证，当前实现中作为前置检查）
            
        Returns:
            URL 字符串，失败返回空字符串
            
        Requirements: 2.3
        Property 2: URL Extraction Validity
        """
        if hwnd == 0 or sys.platform != 'win32':
            return ""
        
        try:
            import win32clipboard
            import win32con
            import time
            
            # 先清除剪贴板，确保不会读到旧内容
            self._clear_clipboard(win32clipboard)
            
            # 模拟 Ctrl+L 聚焦地址栏，然后 Ctrl+C 复制
            _debug_log("Markdown模式: 模拟 Ctrl+L 聚焦地址栏 + Ctrl+C 复制", "MARKDOWN")
            
            # 使用模块级已导入的 ctypes
            VK_CONTROL = 0x11
            VK_L = 0x4C  # L 键
            VK_C = 0x43
            KEYEVENTF_KEYUP = 0x0002
            
            try:
                # Ctrl+L 聚焦地址栏（Chrome/Edge/Firefox 通用快捷键）
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_L, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                
                # 等待地址栏获得焦点并自动全选
                # 增加等待时间到 250ms，确保浏览器有足够时间响应
                time.sleep(0.25)
                
                # Ctrl+C 复制（地址栏内容已被 Ctrl+L 自动全选）
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_C, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                
                # 按 Esc 退出地址栏编辑模式，恢复页面焦点
                # 设置忽略标志，防止键盘钩子捕获这个 Esc 导致模式取消
                VK_ESCAPE = 0x1B
                time.sleep(0.08)
                try:
                    self._ignore_esc = True
                    ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.05)
                finally:
                    self._ignore_esc = False
                
            except Exception as e:
                # 确保按键释放，防止按键卡住
                try:
                    ctypes.windll.user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, 0)
                    ctypes.windll.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
                    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                except Exception:
                    pass
                _debug_log(f"Markdown模式键盘模拟失败: {e}", "MARKDOWN")
                return ""
            
            # 等待剪贴板更新
            time.sleep(0.1)
            
            # 读取剪贴板
            clipboard_text = self._read_clipboard_text(win32clipboard, win32con)
            
            if clipboard_text and self._is_valid_url(clipboard_text.strip()):
                url = clipboard_text.strip()
                _debug_log(f"Markdown模式获取URL成功: {url}", "MARKDOWN")
                # 获取成功后清除剪贴板，防止下次读到旧 URL
                self._clear_clipboard(win32clipboard)
                return url
            
            _debug_log("Markdown模式: 未能获取 URL", "MARKDOWN")
            return ""
            
        except ImportError:
            _debug_log("Markdown模式: win32clipboard 未安装", "MARKDOWN")
            return ""
        except Exception as e:
            _debug_log(f"Markdown模式获取 URL 异常: {e}", "MARKDOWN")
            return ""
    
    def _clear_clipboard(self, win32clipboard) -> None:
        """清除剪贴板内容
        
        Args:
            win32clipboard: win32clipboard 模块
        """
        import time
        
        max_retries = 3
        delay = 0.05
        
        for i in range(max_retries):
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.CloseClipboard()
                _debug_log("Markdown模式: 剪贴板已清除", "MARKDOWN")
                return
            except Exception as e:
                if i < max_retries - 1:
                    time.sleep(delay)
                else:
                    _debug_log(f"Markdown模式: 清除剪贴板失败: {e}", "MARKDOWN")
    
    def _read_clipboard_text(self, win32clipboard, win32con) -> str:
        """读取剪贴板文本内容
        
        Args:
            win32clipboard: win32clipboard 模块
            win32con: win32con 模块
            
        Returns:
            剪贴板文本，失败返回空字符串
        """
        import time
        
        # 安全打开剪贴板（带重试）
        max_retries = 3
        delay = 0.05
        opened = False
        
        for i in range(max_retries):
            try:
                win32clipboard.OpenClipboard()
                opened = True
                break
            except Exception:
                if i < max_retries - 1:
                    time.sleep(delay)
        
        if not opened:
            return ""
        
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                return text if text else ""
            return ""
        except Exception:
            return ""
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
    
    def _is_valid_url(self, url: str) -> bool:
        """检查是否为有效的 URL
        
        验证 URL 格式是否正确，包括协议、主机名等基本检查。
        
        Args:
            url: 待检查的字符串
            
        Returns:
            是否为有效 URL
        """
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        
        # 检查协议
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        
        # 基本格式检查：协议后必须有内容
        try:
            # 移除协议前缀
            if url.startswith("https://"):
                rest = url[8:]
            else:
                rest = url[7:]
            
            # 必须有主机名部分（至少一个字符）
            if not rest or rest.startswith("/"):
                return False
            
            # 主机名不能包含空格或换行
            host_part = rest.split("/")[0].split("?")[0].split("#")[0]
            if not host_part or " " in host_part or "\n" in host_part or "\r" in host_part:
                return False
            
            return True
        except Exception:
            return False
    
    def _show_warning(self, message: str):
        """显示警告消息
        
        Args:
            message: 警告消息
            
        Requirements: 2.5
        """
        # 发送信号
        self.warning_message.emit(message)
        
        # 显示 ToolTip
        from PySide6.QtCore import QRect
        QToolTip.showText(QCursor.pos(), message, None, QRect(), 2000)
    
    def cleanup(self):
        """清理资源
        
        确保钩子被正确卸载，防止资源泄漏。
        可以安全地多次调用。
        """
        if self._is_cleaning_up:
            return
        
        self._is_cleaning_up = True
        try:
            self.deactivate()
            if self._cursor_overlay:
                try:
                    self._cursor_overlay.close()
                except Exception:
                    pass
                self._cursor_overlay = None
        finally:
            self._is_cleaning_up = False
