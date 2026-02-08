# =====================================================
# =============== 鼠标事件监听器 ===============
# =====================================================

"""
全局鼠标事件监听器 - 使用 Windows 低级鼠标钩子

使用 SetWindowsHookEx(WH_MOUSE_LL) 安装低级鼠标钩子，
在独立线程中运行消息循环，通过 Qt Signal 将事件发送到主线程。

Feature: mouse-highlight
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from screenshot_tool.core.async_logger import async_debug_log


# Windows API 常量
WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_QUIT = 0x0012

# 钩子回调函数类型
# LRESULT CALLBACK LowLevelMouseProc(int nCode, WPARAM wParam, LPARAM lParam)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,      # 返回值 LRESULT
    ctypes.c_int,       # nCode
    ctypes.c_uint,      # wParam (消息类型)
    ctypes.c_void_p     # lParam (MSLLHOOKSTRUCT 指针)
)


class POINT(ctypes.Structure):
    """Windows POINT 结构"""
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    """低级鼠标钩子数据结构"""
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# Windows API 函数
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SetWindowsHookExW = user32.SetWindowsHookExW
SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
SetWindowsHookExW.restype = wintypes.HHOOK

UnhookWindowsHookEx = user32.UnhookWindowsHookEx
UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
UnhookWindowsHookEx.restype = wintypes.BOOL

# 关键修复：CallNextHookEx 的 lParam 参数在 64 位系统上是 c_void_p
CallNextHookEx = user32.CallNextHookEx
CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
CallNextHookEx.restype = ctypes.c_long

GetMessageW = user32.GetMessageW
GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
GetMessageW.restype = wintypes.BOOL

TranslateMessage = user32.TranslateMessage
TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
TranslateMessage.restype = wintypes.BOOL

DispatchMessageW = user32.DispatchMessageW
DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
DispatchMessageW.restype = ctypes.c_long

PostThreadMessageW = user32.PostThreadMessageW
PostThreadMessageW.argtypes = [wintypes.DWORD, ctypes.c_uint, ctypes.c_uint, ctypes.c_long]
PostThreadMessageW.restype = wintypes.BOOL

GetModuleHandleW = kernel32.GetModuleHandleW
GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
GetModuleHandleW.restype = wintypes.HMODULE

GetCurrentThreadId = kernel32.GetCurrentThreadId
GetCurrentThreadId.argtypes = []
GetCurrentThreadId.restype = wintypes.DWORD


class MouseEventListener(QObject):
    """全局鼠标事件监听器
    
    使用 Windows 低级鼠标钩子监听全局鼠标事件，
    通过 Qt Signal 将事件发送到主线程。
    
    信号:
        mouse_moved(int, int): 鼠标移动，参数为全局坐标 (x, y)
        left_clicked(int, int): 左键点击，参数为全局坐标 (x, y)
        right_clicked(int, int): 右键点击，参数为全局坐标 (x, y)
    
    使用示例:
        listener = MouseEventListener()
        listener.mouse_moved.connect(on_mouse_move)
        listener.left_clicked.connect(on_left_click)
        listener.start()
        # ...
        listener.stop()
    """
    
    # Qt 信号（线程安全，自动跨线程传递）
    mouse_moved = Signal(int, int)      # (global_x, global_y)
    left_clicked = Signal(int, int)     # (global_x, global_y)
    right_clicked = Signal(int, int)    # (global_x, global_y)
    
    # 60 FPS 限流间隔（毫秒）
    THROTTLE_INTERVAL_MS = 16  # ~60 FPS
    
    def __init__(self, parent: Optional[QObject] = None):
        """初始化监听器"""
        super().__init__(parent)
        
        self._hook_id: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._stop_event = threading.Event()
        
        # 限流：上次发射 mouse_moved 的时间
        self._last_move_time: float = 0.0
        
        # 保持回调引用，防止被垃圾回收
        # 这是关键！如果回调被 GC，钩子会崩溃
        self._hook_proc: Optional[HOOKPROC] = None
    
    def start(self) -> bool:
        """启动监听
        
        Returns:
            bool: 是否成功启动
        """
        if self._running:
            async_debug_log("鼠标监听器已在运行")
            return True
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_hook_thread, daemon=True)
        self._thread.start()
        
        # 等待钩子安装完成（最多 2 秒）
        start_time = time.time()
        while not self._running and time.time() - start_time < 2.0:
            time.sleep(0.05)
        
        if self._running:
            async_debug_log("鼠标监听器启动成功")
            return True
        else:
            async_debug_log("鼠标监听器启动失败")
            return False
    
    def stop(self):
        """停止监听并释放钩子"""
        if not self._running:
            return
        
        self._stop_event.set()
        
        # 发送 WM_QUIT 消息终止消息循环
        if self._thread_id:
            PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        
        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        self._running = False
        self._thread = None
        self._thread_id = None
        async_debug_log("鼠标监听器已停止")
    
    def is_running(self) -> bool:
        """返回监听器是否正在运行"""
        return self._running
    
    def _run_hook_thread(self):
        """钩子线程主函数"""
        try:
            # 获取当前线程 ID
            self._thread_id = GetCurrentThreadId()
            
            # 创建钩子回调（必须保持引用）
            self._hook_proc = HOOKPROC(self._low_level_mouse_proc)
            
            # 安装钩子
            # 关键修复：对于低级钩子 (WH_MOUSE_LL)，hmod 参数应该传 None
            # 参考: https://stackoverflow.com/questions/31379169
            self._hook_id = SetWindowsHookExW(
                WH_MOUSE_LL,
                self._hook_proc,
                None,  # 对于低级钩子，不需要模块句柄
                0
            )
            
            if not self._hook_id:
                async_debug_log("SetWindowsHookEx 失败")
                return
            
            self._running = True
            async_debug_log(f"鼠标钩子已安装，hook_id={self._hook_id}")
            
            # 消息循环
            msg = wintypes.MSG()
            while not self._stop_event.is_set():
                # GetMessage 返回 0 表示收到 WM_QUIT
                # 返回 -1 表示错误
                ret = GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                TranslateMessage(ctypes.byref(msg))
                DispatchMessageW(ctypes.byref(msg))
            
        except Exception as e:
            async_debug_log(f"鼠标钩子线程异常: {e}")
        finally:
            # 卸载钩子
            if self._hook_id:
                UnhookWindowsHookEx(self._hook_id)
                self._hook_id = None
                async_debug_log("鼠标钩子已卸载")
            self._running = False
    
    def _low_level_mouse_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        """低级鼠标钩子回调函数
        
        注意：此函数必须快速返回，否则系统会自动卸载钩子！
        """
        try:
            if nCode >= 0 and lParam:
                # 解析鼠标数据
                hook_struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                x = hook_struct.pt.x
                y = hook_struct.pt.y
                
                if wParam == WM_MOUSEMOVE:
                    # 限流：60 FPS
                    current_time = time.time() * 1000  # 转换为毫秒
                    if current_time - self._last_move_time >= self.THROTTLE_INTERVAL_MS:
                        self._last_move_time = current_time
                        # 发射信号（Qt 自动处理跨线程）
                        self.mouse_moved.emit(x, y)
                
                elif wParam == WM_LBUTTONDOWN:
                    self.left_clicked.emit(x, y)
                
                elif wParam == WM_RBUTTONDOWN:
                    self.right_clicked.emit(x, y)
        
        except Exception:
            # 回调中不能抛出异常，否则会导致钩子被卸载
            pass
        
        # 必须调用 CallNextHookEx 传递给下一个钩子
        return CallNextHookEx(self._hook_id, nCode, wParam, lParam)
    
    def __del__(self):
        """析构函数，确保资源释放"""
        self.stop()
