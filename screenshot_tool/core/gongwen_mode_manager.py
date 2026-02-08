# =====================================================
# =============== 公文格式化模式管理器 ===============
# =====================================================

"""
公文格式化模式管理器 - 管理快捷键触发、鼠标图标、窗口点击检测

用于管理公文格式化模式的激活、鼠标点击检测、格式化触发。

Feature: word-gongwen-format
Requirements: 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5
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
    
    # 父窗口遍历最大深度，防止无限循环
    MAX_PARENT_DEPTH = 50
    
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


class GongwenModeManager(QObject):
    """公文格式化模式管理器
    
    管理公文格式化模式的激活、鼠标点击检测、格式化触发。
    
    信号:
        format_triggered: 格式化触发信号，参数为窗口句柄
        mode_changed: 模式变化信号，参数为是否激活
        warning_message: 警告消息信号
    
    使用方法:
        manager = GongwenModeManager()
        manager.format_triggered.connect(on_format)
        manager.activate()  # 激活模式
        manager.deactivate()  # 停用模式
    """
    
    # 信号定义
    format_triggered = Signal(int)  # 参数为窗口句柄
    mode_changed = Signal(bool)  # 参数为是否激活
    warning_message = Signal(str)  # 警告消息
    
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
    
    def __del__(self):
        """析构函数，确保钩子被卸载"""
        try:
            self.cleanup()
        except Exception:
            pass  # 析构时忽略异常
    
    @property
    def is_active(self) -> bool:
        """是否处于格式化模式
        
        Returns:
            是否激活
        """
        return self._active
    
    def activate(self):
        """激活格式化模式
        
        Requirements: 2.1
        """
        if self._active or self._is_cleaning_up:
            return
        
        _debug_log("激活公文格式化模式", "GONGWEN")
        self._active = True
        self._show_cursor_overlay()
        self._install_mouse_hook()
        self._install_keyboard_hook()
        self.mode_changed.emit(True)
    
    def deactivate(self):
        """停用格式化模式
        
        Requirements: 2.4, 3.5
        """
        if not self._active:
            return
        
        _debug_log("停用公文格式化模式", "GONGWEN")
        self._active = False
        self._hide_cursor_overlay()
        self._uninstall_mouse_hook()
        self._uninstall_keyboard_hook()
        self.mode_changed.emit(False)
    
    def toggle(self):
        """切换格式化模式"""
        if self._active:
            self.deactivate()
        else:
            self.activate()
    
    def _show_cursor_overlay(self):
        """显示鼠标图标
        
        Requirements: 2.2
        """
        if self._cursor_overlay is None:
            from screenshot_tool.ui.cursor_overlay import CursorOverlay
            self._cursor_overlay = CursorOverlay()
        self._cursor_overlay.show_overlay()
    
    def _hide_cursor_overlay(self):
        """隐藏鼠标图标
        
        Requirements: 2.5
        """
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
                if obj is not None and nCode >= 0 and wParam == WM_LBUTTONDOWN:
                    # 获取鼠标位置
                    hook_struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = hook_struct.pt.x, hook_struct.pt.y
                    
                    _debug_log(f"鼠标钩子捕获点击: ({x}, {y})", "GONGWEN")
                    
                    # 使用 QTimer 在主线程处理点击
                    # 使用默认参数捕获当前值，避免闭包问题
                    QTimer.singleShot(0, lambda _x=x, _y=y, _obj=obj: _obj._on_mouse_click(_x, _y) if _obj._active else None)
            except Exception as e:
                _debug_log(f"鼠标钩子回调异常: {e}", "GONGWEN")
            
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
            _debug_log(f"鼠标钩子安装失败, 错误码: {error_code}", "GONGWEN")
            self._hook_proc = None
        else:
            _debug_log(f"鼠标钩子安装成功, handle={self._mouse_hook}", "GONGWEN")
    
    def _uninstall_mouse_hook(self):
        """卸载鼠标钩子"""
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._mouse_hook:
            try:
                _UnhookWindowsHookEx(self._mouse_hook)
                _debug_log("鼠标钩子已卸载", "GONGWEN")
            except Exception as e:
                _debug_log(f"卸载鼠标钩子异常: {e}", "GONGWEN")
            finally:
                self._mouse_hook = None
                self._hook_proc = None
    
    def _install_keyboard_hook(self):
        """安装全局键盘钩子（用于 Esc 取消）"""
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
                    
                    # 检测 Esc 键
                    if vk_code == VK_ESCAPE and obj._active:
                        _debug_log("检测到 Esc 键，取消公文模式", "GONGWEN")
                        # 使用 QTimer 在主线程处理
                        QTimer.singleShot(0, obj.deactivate)
                        # 不阻止事件传递，让其他程序也能收到 Esc
            except Exception as e:
                _debug_log(f"键盘钩子回调异常: {e}", "GONGWEN")
            
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
            _debug_log(f"键盘钩子安装失败, 错误码: {error_code}", "GONGWEN")
            self._kb_hook_proc = None
        else:
            _debug_log(f"键盘钩子安装成功, handle={self._keyboard_hook}", "GONGWEN")
    
    def _uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        if sys.platform != 'win32':
            return  # 非 Windows 平台不支持
        
        if self._keyboard_hook:
            try:
                _UnhookWindowsHookEx(self._keyboard_hook)
                _debug_log("键盘钩子已卸载", "GONGWEN")
            except Exception as e:
                _debug_log(f"卸载键盘钩子异常: {e}", "GONGWEN")
            finally:
                self._keyboard_hook = None
                self._kb_hook_proc = None
    
    def _on_mouse_click(self, x: int, y: int):
        """鼠标点击处理
        
        Args:
            x: 点击X坐标
            y: 点击Y坐标
            
        Requirements: 3.1, 3.2, 3.3
        """
        _debug_log(f"_on_mouse_click 被调用: ({x}, {y}), active={self._active}", "GONGWEN")
        
        if not self._active:
            _debug_log("公文模式未激活，忽略点击", "GONGWEN")
            return
        
        # 获取点击位置的窗口句柄
        hwnd = self._get_window_at_point(x, y)
        _debug_log(f"点击位置窗口句柄: {hwnd}", "GONGWEN")
        
        if hwnd == 0:
            _debug_log("获取窗口句柄失败 (hwnd=0)", "GONGWEN")
            self._show_warning("无法获取窗口信息")
            return
        
        # 获取窗口类名用于调试
        try:
            import win32gui
            class_name = win32gui.GetClassName(hwnd)
            window_text = win32gui.GetWindowText(hwnd)[:50]  # 截取前50字符
            _debug_log(f"窗口信息: class={class_name}, title={window_text}", "GONGWEN")
        except Exception as e:
            _debug_log(f"获取窗口信息失败: {e}", "GONGWEN")
        
        # 检测是否为 Word 窗口
        is_word = self._is_word_window(hwnd)
        _debug_log(f"是否为 Word 窗口: {is_word}", "GONGWEN")
        
        if is_word:
            _debug_log("检测到 Word/WPS 窗口，准备触发格式化", "GONGWEN")
            self.deactivate()
            _debug_log(f"触发格式化信号, hwnd={hwnd}", "GONGWEN")
            self.format_triggered.emit(hwnd)
        else:
            _debug_log("非 Word/WPS 窗口，显示警告", "GONGWEN")
            self._show_warning("请点击 Word 或 WPS 文字窗口")
    
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
            _debug_log(f"获取窗口句柄失败: {e}", "GONGWEN")
            return 0
    
    # 支持的文字处理软件窗口类名
    # Microsoft Word: "OpusApp" (Word 2016/2019/2021/365)
    # WPS Office: "KSOMAIN" (WPS 文字主窗口)
    SUPPORTED_WORD_CLASSES = {"OpusApp", "KSOMAIN"}
    
    def _is_word_window(self, hwnd: int) -> bool:
        """检测是否为 Word 或 WPS 文字窗口
        
        支持的软件：
        - Microsoft Word: 主窗口类名为 "OpusApp"，支持 Word 2016/2019/2021/365
        - WPS Office: 主窗口类名为 "KSOMAIN"
        
        点击可能落在子窗口上，需要遍历父窗口检测。
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            是否为 Word/WPS 窗口
            
        Requirements: 3.1, 3.4
        """
        if hwnd == 0 or sys.platform != 'win32':
            return False
        
        try:
            import win32gui
            
            # 检查当前窗口
            class_name = win32gui.GetClassName(hwnd)
            if class_name in self.SUPPORTED_WORD_CLASSES:
                return True
            
            # 检查父窗口链，限制最大深度防止无限循环
            visited = {hwnd}  # 记录已访问的窗口，防止循环
            parent = win32gui.GetParent(hwnd)
            depth = 0
            
            while parent and depth < MAX_PARENT_DEPTH:
                if parent in visited:
                    # 检测到循环，退出
                    _debug_log(f"检测到窗口父子循环: {parent}", "GONGWEN")
                    break
                
                visited.add(parent)
                
                try:
                    if win32gui.GetClassName(parent) in self.SUPPORTED_WORD_CLASSES:
                        return True
                    parent = win32gui.GetParent(parent)
                    depth += 1
                except Exception:
                    break
            
            return False
        except Exception as e:
            _debug_log(f"检测 Word/WPS 窗口异常: {e}", "GONGWEN")
            return False
    
    def _show_warning(self, message: str):
        """显示警告消息
        
        Args:
            message: 警告消息
            
        Requirements: 3.3
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
