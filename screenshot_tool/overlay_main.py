# =====================================================
# =============== 虎哥截图入口 ===============
# =====================================================

"""
虎哥截图 - 类似 Snipaste 的截图体验

直接在屏幕上操作，工具栏贴在选区边缘
全局快捷键: Alt+A 启动截图
"""

import sys
import os
import time
import threading
import gc  # 垃圾回收

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QImage
from PySide6.QtCore import Qt, QRect, QTimer, QObject, Signal, QThread

# 应用信息
from screenshot_tool import __version__, __app_name__

# ========== 性能监控 ==========
# Feature: extreme-performance-optimization
# Requirements: 1.1, 2.1, 2.2
from screenshot_tool.core.performance_monitor import PerformanceMonitor

# ========== 异步调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

def ocr_debug_log(message: str):
    """OCR调试日志（使用异步日志器）"""
    async_debug_log(message, "OCR-MAIN")

# Windows 全局热键支持
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    
    user32 = ctypes.windll.user32
    
    # 热键修饰符
    MOD_ALT = 0x0001
    MOD_CTRL = 0x0002
    MOD_SHIFT = 0x0004
    
    # 虚拟键码映射
    VK_CODES = {
        'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
        'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
        'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
        'z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
        'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
        'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
        'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    }
else:
    # 非Windows平台的占位符，避免引用错误
    MOD_ALT = 0x0001
    MOD_CTRL = 0x0002
    MOD_SHIFT = 0x0004
    VK_CODES = {
        'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
        'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
        'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
        'z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
        'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
        'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
        'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    }

from screenshot_tool.ui.overlay_screenshot import OverlayScreenshot
# 延迟导入以加速 EXE 启动
# from screenshot_tool.ui.ding_window import DingManager
from screenshot_tool.core.file_manager import FileManager, SaveResult
from screenshot_tool.core.config_manager import ConfigManager
from screenshot_tool.core.auto_ocr_popup_manager import AutoOCRPopupManager
# 内存管理器
# Feature: performance-ui-optimization
# Requirements: 4.3, 4.4
from screenshot_tool.core.memory_manager import MemoryManager
# 截图模式管理器
# Feature: extreme-performance-optimization
# Requirements: 12.4, 11.9
from screenshot_tool.core.screenshot_mode_manager import get_screenshot_mode_manager
# 延迟导入以加速 EXE 启动
# from screenshot_tool.services.ocr_manager import OCRManager, UnifiedOCRResult


class SaveWorker(QThread):
    """截图保存后台工作线程
    
    将文件保存操作放到后台线程执行，避免阻塞UI。
    """
    finished = Signal(object)  # SaveResult
    
    def __init__(self, file_manager, image: QImage):
        super().__init__()
        self._file_manager = file_manager
        # 复制图片以确保线程安全
        self._image = image.copy() if image and not image.isNull() else None
    
    def run(self):
        """在后台线程执行保存"""
        try:
            if self._image is None or self._image.isNull():
                self.finished.emit(SaveResult.error_result("图片为空"))
                return
            result = self._file_manager.save_screenshot(self._image)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(SaveResult.error_result(f"保存异常: {str(e)}"))
        finally:
            # 释放图片内存
            self._image = None


class SaveToFileWorker(QThread):
    """保存到指定文件路径的后台工作线程
    
    将文件保存操作放到后台线程执行，避免阻塞UI。
    """
    finished = Signal(object)  # SaveResult
    
    def __init__(self, file_manager, image: QImage, file_path: str):
        super().__init__()
        self._file_manager = file_manager
        # 复制图片以确保线程安全
        self._image = image.copy() if image and not image.isNull() else None
        self._file_path = file_path
    
    def run(self):
        """在后台线程执行保存"""
        try:
            if self._image is None or self._image.isNull():
                self.finished.emit(SaveResult.error_result("图片为空"))
                return
            result = self._file_manager.save_screenshot_to_file(
                self._image, self._file_path
            )
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(SaveResult.error_result(f"保存异常: {str(e)}"))
        finally:
            # 释放图片内存
            self._image = None


class OCRWorker(QThread):
    """OCR后台工作线程"""
    finished = Signal(object)  # UnifiedOCRResult
    
    def __init__(self, ocr_manager: "OCRManager", image: QImage, 
                 mode: str = "full", force_engine: str = None):
        """
        初始化OCR工作线程
        
        Args:
            ocr_manager: OCR管理器
            image: 要识别的图片
            mode: 运行模式
                - "full": 按优先级尝试所有引擎
                - "preprocess": 预处理模式，只运行本地OCR（不消耗在线API）
                - "single": 只运行指定引擎
            force_engine: 指定引擎（mode="single"时使用）
        """
        super().__init__()
        self._ocr_manager = ocr_manager
        self._image = image.copy() if image and not image.isNull() else None
        self._should_stop = False
        self._mode = mode
        self._force_engine = force_engine
    
    def stop(self):
        """请求停止线程"""
        self._should_stop = True
    
    def _safe_emit(self, result):
        """安全地发送信号，避免在模态对话框打开时崩溃
        
        当检测到模态对话框时，等待一小段时间后重试，
        最多重试 5 次，每次等待 100ms。
        """
        if self._should_stop:
            return
        
        # 检查是否有模态对话框
        try:
            from screenshot_tool.core.modal_dialog_detector import ModalDialogDetector
            
            max_retries = 5
            retry_delay_ms = 100
            
            for i in range(max_retries):
                if self._should_stop:
                    return
                
                if not ModalDialogDetector.is_modal_dialog_active():
                    # 没有模态对话框，安全发送信号
                    self.finished.emit(result)
                    return
                
                # 有模态对话框，等待后重试
                if i < max_retries - 1:
                    ocr_debug_log(f"检测到模态对话框，延迟发送 OCR 结果 (重试 {i+1}/{max_retries})")
                    self.msleep(retry_delay_ms)
            
            # 重试次数用尽，仍然发送（可能会有问题，但总比丢失结果好）
            ocr_debug_log("模态对话框持续存在，强制发送 OCR 结果")
            self.finished.emit(result)
            
        except Exception as e:
            # 检测失败时直接发送
            ocr_debug_log(f"模态对话框检测失败: {e}，直接发送 OCR 结果")
            if not self._should_stop:
                self.finished.emit(result)
    
    def run(self):
        """在后台线程执行OCR"""
        from screenshot_tool.services.ocr_manager import UnifiedOCRResult
        try:
            if self._should_stop:
                return
            if self._image is None or self._image.isNull():
                if not self._should_stop:
                    self._safe_emit(UnifiedOCRResult.error_result("图片为空"))
                return
            
            if self._mode == "preprocess":
                # 预处理模式：只运行本地OCR（不消耗在线API配额）
                result = self._ocr_manager.recognize_rapid_only(self._image)
                if not self._should_stop:
                    self._safe_emit(result)
                    
            elif self._mode == "single" and self._force_engine:
                # 单引擎模式
                result = self._ocr_manager.recognize_with_engine(self._image, self._force_engine)
                if not self._should_stop:
                    self._safe_emit(result)
            else:
                # 完整模式：按优先级尝试所有引擎
                result = self._ocr_manager.recognize(self._image)
                if not self._should_stop:
                    self._safe_emit(result)
                    
        except Exception as e:
            if not self._should_stop:
                self._safe_emit(UnifiedOCRResult.error_result(f"OCR线程异常: {str(e)}"))
        finally:
            # 释放图片内存
            self._image = None


def _get_resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容开发环境和打包后环境
    
    Args:
        relative_path: 相对于项目根目录的路径
        
    Returns:
        资源文件的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的路径
        base_path = sys._MEIPASS
    else:
        # 开发环境：overlay_main.py 在 screenshot_tool/ 下，向上一级是项目根目录
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def create_app_icon() -> QIcon:
    """创建应用图标 - 优先使用自定义图标文件
    
    Returns:
        QIcon: 应用图标，优先使用 resources/虎哥截图.ico，
               找不到时使用默认绘制的图标
    """
    # 尝试加载自定义图标
    try:
        icon_path = _get_resource_path(os.path.join("resources", "虎哥截图.ico"))
        if os.path.isfile(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                return icon
    except Exception:
        pass  # 静默失败，使用默认图标
    
    # 如果找不到自定义图标，使用默认绘制的图标
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # 绘制相机主体
    painter.setBrush(QColor("#4A90D9"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(8, 16, 48, 36, 6, 6)
    
    # 绘制镜头
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawEllipse(22, 22, 20, 20)
    
    painter.setBrush(QColor("#4A90D9"))
    painter.drawEllipse(26, 26, 12, 12)
    
    # 绘制闪光灯
    painter.setBrush(QColor("#FFC107"))
    painter.drawRoundedRect(12, 20, 8, 6, 2, 2)
    
    painter.end()
    
    return QIcon(pixmap)


class HotkeySignalEmitter(QObject):
    """热键信号发射器 - 用于线程安全的信号传递
    
    注意：Qt 信号在模态对话框阻塞主线程事件循环时可能无法被处理。
    对于热键触发，我们使用 QApplication.postEvent 发送自定义事件来绕过这个限制。
    
    关键改进：在 event() 方法中直接调用回调函数，而不是通过信号。
    因为 event() 方法已经在主线程的事件循环中被调用了（即使是模态对话框的本地事件循环），
    所以可以直接执行回调，避免信号队列的问题。
    """
    hotkeyPressed = Signal()
    statusChanged = Signal(str)  # 状态变化信号
    
    # 自定义事件类型 ID
    HOTKEY_EVENT_TYPE = 1001  # QEvent.Type.User + 1
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._direct_callback = None  # 直接回调函数
    
    def set_direct_callback(self, callback):
        """设置直接回调函数（用于绕过信号队列）"""
        self._direct_callback = callback
    
    def event(self, event):
        """处理自定义事件
        
        当收到热键触发事件时，直接调用回调函数。
        这个方法会在事件循环中被调用，即使是模态对话框的本地事件循环。
        
        关键：直接调用回调而不是 emit 信号，因为：
        1. event() 已经在主线程的事件循环中执行
        2. 模态对话框的本地事件循环也会调用 event()
        3. 直接调用回调可以绕过信号队列的问题
        """
        # event.type() 返回 QEvent.Type 枚举，需要转换为 int 进行比较
        if int(event.type()) == self.HOTKEY_EVENT_TYPE:
            async_debug_log("收到热键事件，直接调用回调", "HOTKEY-EVENT")
            # 直接调用回调函数，绕过信号队列
            if self._direct_callback:
                try:
                    self._direct_callback()
                except Exception as e:
                    async_debug_log(f"热键回调执行失败: {e}", "HOTKEY-EVENT")
            else:
                # 回退到信号（兼容性）
                self.hotkeyPressed.emit()
            return True
        return super().event(event)


# 热键注册状态枚举
class HotkeyStatus:
    """热键注册状态"""
    UNKNOWN = "unknown"      # 未知状态
    REGISTERED = "registered"  # 已注册成功
    WAITING = "waiting"      # 等待注册中（重试中）
    FAILED = "failed"        # 注册失败（未启用强制锁定）


# Windows 错误码
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


class GlobalHotkeyManager:
    """全局热键管理器 - Windows平台
    
    使用 Windows API 注册全局热键，支持自定义快捷键和强制锁定重试机制
    
    Feature: hotkey-force-lock
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1
    """
    
    HOTKEY_ID_SCREENSHOT = 1
    
    def __init__(self, callback, modifier: str = "alt", key: str = "a",
                 force_lock: bool = False, retry_interval_ms: int = 3000):
        """
        初始化热键管理器
        
        Args:
            callback: 热键触发时的回调函数
            modifier: 修饰键 (alt, ctrl, shift, ctrl+alt, ctrl+shift, alt+shift)
            key: 主键 (a-z, 0-9, f1-f12)
            force_lock: 是否启用强制锁定模式
            retry_interval_ms: 重试间隔（毫秒）
        """
        self._callback = callback
        self._modifier = modifier.lower()
        self._key = key.lower()
        self._registered = False
        self._lock = threading.Lock()
        self._is_capturing = False
        self._listener_thread = None
        self._running = False
        
        # 强制锁定相关属性
        self._force_lock = force_lock
        self._retry_interval_ms = retry_interval_ms
        self._retry_timer = None
        self._registration_status = HotkeyStatus.UNKNOWN
        self._status_callback = None
        self._last_error_code = 0
        self._notification_shown = False  # 是否已显示冲突通知
        
        # 创建信号发射器用于线程安全的回调
        self._signal_emitter = HotkeySignalEmitter()
        # 设置直接回调（用于绕过模态对话框的信号队列问题）
        self._signal_emitter.set_direct_callback(self._on_hotkey_signal)
        # 保留信号连接作为备用
        self._signal_emitter.hotkeyPressed.connect(self._on_hotkey_signal)
        self._signal_emitter.statusChanged.connect(self._on_status_changed_signal)
        
        if sys.platform == 'win32':
            self._start_listener_thread()
    
    def _get_modifier_code(self) -> int:
        """获取修饰键代码"""
        modifier_map = {
            "alt": MOD_ALT,
            "ctrl": MOD_CTRL,
            "shift": MOD_SHIFT,
            "ctrl+alt": MOD_CTRL | MOD_ALT,
            "ctrl+shift": MOD_CTRL | MOD_SHIFT,
            "alt+shift": MOD_ALT | MOD_SHIFT,
        }
        return modifier_map.get(self._modifier, MOD_ALT)
    
    def _get_key_code(self) -> int:
        """获取主键代码"""
        return VK_CODES.get(self._key, VK_CODES['a'])
    
    def _get_hotkey_display(self) -> str:
        """获取快捷键显示文本"""
        modifier_display = self._modifier.replace("+", "+").title()
        key_display = self._key.upper()
        return f"{modifier_display}+{key_display}"
    
    def _on_hotkey_signal(self):
        """处理热键信号（在主线程中执行）"""
        with self._lock:
            if self._is_capturing:
                print(f"热键被忽略: _is_capturing=True")
                return
            self._is_capturing = True
            print(f"热键触发: 设置 _is_capturing=True")
        
        try:
            if self._callback:
                self._callback()
        except Exception as e:
            print(f"热键回调执行失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 回调执行完后重置状态（除非是截图热键，由截图流程控制）
            # 扩展热键（force_lock=False）需要立即重置
            if not self._force_lock:
                with self._lock:
                    self._is_capturing = False
                    print(f"热键回调完成: 重置 _is_capturing=False")
    
    def _start_listener_thread(self):
        """启动热键监听线程"""
        self._running = True
        self._listener_thread = threading.Thread(target=self._hotkey_listener, daemon=True)
        self._listener_thread.start()
        print(f"全局热键监听线程已启动 ({self._get_hotkey_display()})")
    
    def _hotkey_listener(self):
        """热键监听线程 - 在独立线程中运行消息循环
        
        Feature: hotkey-force-lock
        Requirements: 2.1, 2.4, 5.1
        """
        if sys.platform != 'win32':
            return
        
        try:
            # 获取修饰键和主键代码
            mod_code = self._get_modifier_code()
            key_code = self._get_key_code()
            
            # 注册热键 - 必须在同一个线程中注册和处理消息
            result = user32.RegisterHotKey(None, self.HOTKEY_ID_SCREENSHOT, mod_code, key_code)
            if result:
                self._registered = True
                self._update_status(HotkeyStatus.REGISTERED)
                print(f"全局热键 {self._get_hotkey_display()} 注册成功")
            else:
                error_code = ctypes.get_last_error()
                self._last_error_code = error_code
                print(f"全局热键 {self._get_hotkey_display()} 注册失败，错误码: {error_code}")
                
                # 检查是否是热键冲突错误
                if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
                    if self._force_lock:
                        # 启用强制锁定：进入重试模式
                        self._update_status(HotkeyStatus.WAITING)
                        self._schedule_retry()
                    else:
                        # 未启用强制锁定：标记为失败
                        self._update_status(HotkeyStatus.FAILED)
                else:
                    # 其他错误
                    self._update_status(HotkeyStatus.FAILED)
                return
            
            # 消息循环
            msg = wintypes.MSG()
            while self._running:
                # 使用 PeekMessage 非阻塞检查
                ret = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001)  # PM_REMOVE
                if ret != 0:
                    # 检查是否是热键消息
                    if msg.message == 0x0312:  # WM_HOTKEY
                        if msg.wParam == self.HOTKEY_ID_SCREENSHOT:
                            self._trigger_callback_safe()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # 没有消息时短暂休眠
                    time.sleep(0.01)
                    
        except Exception as e:
            print(f"热键监听线程异常: {e}")
        finally:
            if self._registered:
                try:
                    user32.UnregisterHotKey(None, self.HOTKEY_ID_SCREENSHOT)
                except Exception:
                    pass
                self._registered = False
    
    def _trigger_callback_safe(self):
        """安全地触发回调（从子线程调用）
        
        Feature: emergency-esc-exit
        Requirements: 7.1, 7.2, 7.3
        
        使用 QApplication.postEvent 绕过模态对话框的事件循环阻塞。
        
        问题：Qt 信号的 emit() 在模态对话框打开时可能无法被处理，
        因为模态对话框会运行自己的本地事件循环，而信号连接可能
        绑定到主事件循环。
        
        解决方案：
        1. 使用 QApplication.postEvent 发送自定义事件
        2. 在 HotkeySignalEmitter.event() 中直接调用回调函数
        3. 这样可以绕过信号队列，直接在事件循环中执行回调
        """
        async_debug_log("_trigger_callback_safe 被调用", "HOTKEY")
        try:
            from PySide6.QtCore import QEvent, QCoreApplication
            
            # 创建自定义事件并发送到信号发射器
            event = QEvent(QEvent.Type(HotkeySignalEmitter.HOTKEY_EVENT_TYPE))
            
            # postEvent 是线程安全的，会将事件放入目标对象的事件队列
            # 模态对话框的事件循环也会处理这些事件
            # 关键：HotkeySignalEmitter.event() 会直接调用回调，而不是 emit 信号
            QCoreApplication.postEvent(self._signal_emitter, event)
            async_debug_log("postEvent 成功发送到 _signal_emitter", "HOTKEY")
            
        except Exception as e:
            print(f"[HOTKEY] postEvent 失败: {e}, 回退到直接 emit")
            # 回退到直接 emit
            self._signal_emitter.hotkeyPressed.emit()
    
    def _reset_capturing_state(self):
        """重置截图状态"""
        with self._lock:
            self._is_capturing = False
    
    def set_capturing(self, capturing: bool):
        """设置截图状态"""
        with self._lock:
            print(f"set_capturing: {self._is_capturing} -> {capturing}")
            self._is_capturing = capturing
    
    def cleanup(self):
        """清理资源
        
        Feature: hotkey-force-lock
        Requirements: 2.5
        """
        self._running = False
        
        # 取消重试定时器
        self._cancel_retry()
        
        # 发送退出消息给监听线程
        if sys.platform == 'win32' and self._listener_thread and self._listener_thread.is_alive():
            # 等待线程结束
            self._listener_thread.join(timeout=1.0)
            # 如果线程仍在运行，记录警告
            if self._listener_thread.is_alive():
                print("警告: 热键监听线程未能在超时时间内结束")
        
        self._listener_thread = None
    
    def set_force_lock(self, enabled: bool, retry_interval_ms: int = 3000):
        """设置强制锁定模式
        
        Args:
            enabled: 是否启用强制锁定
            retry_interval_ms: 重试间隔（毫秒）
            
        Feature: hotkey-force-lock
        Requirements: 2.1, 2.2
        """
        self._force_lock = enabled
        self._retry_interval_ms = retry_interval_ms
        
        if enabled:
            # 如果当前未注册且启用强制锁定，立即开始重试
            if not self._registered and self._registration_status in (
                HotkeyStatus.FAILED, HotkeyStatus.UNKNOWN
            ):
                self._update_status(HotkeyStatus.WAITING)
                self._schedule_retry()
        else:
            # 禁用强制锁定时取消重试
            self._cancel_retry()
            # 重置通知标志
            self._notification_shown = False
    
    def set_status_callback(self, callback):
        """设置状态变化回调
        
        Args:
            callback: 回调函数，签名为 callback(status: str)
            
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        self._status_callback = callback
    
    def get_registration_status(self) -> str:
        """获取当前注册状态
        
        Returns:
            状态字符串：unknown, registered, waiting, failed
            
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        return self._registration_status
    
    def _update_status(self, status: str):
        """更新注册状态并通知
        
        Args:
            status: 新状态
            
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        if self._registration_status != status:
            self._registration_status = status
            # 使用信号在主线程中执行回调
            self._signal_emitter.statusChanged.emit(status)
    
    def _on_status_changed_signal(self, status: str):
        """处理状态变化信号（在主线程中执行）
        
        Args:
            status: 新状态
            
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception as e:
                print(f"状态回调执行失败: {e}")
    
    def _schedule_retry(self):
        """安排重试
        
        Feature: hotkey-force-lock
        Requirements: 2.1, 2.2
        """
        # 取消现有定时器
        self._cancel_retry()
        
        # 检查是否应该继续重试
        if not self._running or not self._force_lock:
            return
        
        # 创建新的定时器
        interval_sec = self._retry_interval_ms / 1000.0
        self._retry_timer = threading.Timer(interval_sec, self._retry_registration)
        self._retry_timer.daemon = True
        self._retry_timer.start()
        print(f"已安排热键重试，{self._retry_interval_ms}ms 后执行")
    
    def _cancel_retry(self):
        """取消重试
        
        Feature: hotkey-force-lock
        Requirements: 2.3, 2.5
        """
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None
            print("已取消热键重试定时器")
    
    def _retry_registration(self):
        """重试注册热键（在定时器线程中执行）
        
        Feature: hotkey-force-lock
        Requirements: 2.1, 2.2
        """
        if not self._running or not self._force_lock:
            return
        
        if sys.platform != 'win32':
            return
        
        print(f"正在重试注册热键 {self._get_hotkey_display()}...")
        
        # 获取修饰键和主键代码
        mod_code = self._get_modifier_code()
        key_code = self._get_key_code()
        
        # 尝试注册热键
        result = user32.RegisterHotKey(None, self.HOTKEY_ID_SCREENSHOT, mod_code, key_code)
        if result:
            self._registered = True
            self._update_status(HotkeyStatus.REGISTERED)
            self._notification_shown = False  # 重置通知标志
            print(f"热键重试成功！{self._get_hotkey_display()} 已注册")
            # 成功后启动消息循环
            self._start_message_loop()
        else:
            error_code = ctypes.get_last_error()
            self._last_error_code = error_code
            print(f"热键重试失败，错误码: {error_code}")
            # 继续安排下一次重试
            if self._force_lock and self._running:
                self._schedule_retry()
    
    def _start_message_loop(self):
        """启动消息循环（在重试成功后调用）
        
        Feature: hotkey-force-lock
        """
        if sys.platform != 'win32':
            return
        
        try:
            msg = wintypes.MSG()
            while self._running:
                ret = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001)
                if ret != 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        if msg.wParam == self.HOTKEY_ID_SCREENSHOT:
                            self._trigger_callback_safe()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)
        except Exception as e:
            print(f"消息循环异常: {e}")
        finally:
            if self._registered:
                try:
                    user32.UnregisterHotKey(None, self.HOTKEY_ID_SCREENSHOT)
                except Exception:
                    pass
                self._registered = False
    
    def update_hotkey(self, modifier: str, key: str):
        """更新快捷键
        
        Args:
            modifier: 新的修饰键
            key: 新的主键
        """
        # 验证输入
        modifier = modifier.lower()
        key = key.lower()
        
        valid_modifiers = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
        valid_keys = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
        
        if modifier not in valid_modifiers:
            print(f"无效的修饰键: {modifier}，使用默认值 alt")
            modifier = "alt"
        
        if key not in valid_keys:
            print(f"无效的主键: {key}，使用默认值 d")
            key = "d"
        
        # 如果快捷键没有变化，直接返回
        if self._modifier == modifier and self._key == key:
            return
        
        # 先清理旧的热键
        self.cleanup()
        
        # 更新配置
        self._modifier = modifier
        self._key = key
        self._registered = False
        
        # 重新启动监听线程
        if sys.platform == 'win32':
            self._start_listener_thread()


class MarkdownConversionWorker(QThread):
    """Markdown 转换后台工作线程
    
    每次处理一个 URL，完成后发送信号。
    
    Feature: web-to-markdown-dialog
    Requirements: 5.2
    
    注意：Playwright 在 QThread 中运行需要特殊处理：
    1. Windows 平台需要设置 ProactorEventLoop 策略
    2. 每个线程必须有独立的 sync_playwright() 上下文
    3. 不能在线程间共享 browser/page 对象
    """
    
    # 信号：转换完成，参数为 (url, ConversionResult)
    conversion_finished = Signal(str, object)
    
    def __init__(self, url: str, config, save_dir: str = ""):
        """初始化工作线程
        
        Args:
            url: 要转换的单个 URL
            config: Markdown 配置
            save_dir: 自定义保存目录，为空则使用配置中的目录
        """
        super().__init__()
        self._url = url
        self._config = config
        self._save_dir = save_dir
    
    def run(self):
        """执行转换
        
        关键：在 QThread 中运行 Playwright 需要：
        1. 设置 Windows 事件循环策略为 ProactorEventLoop
        2. 每次转换创建新的 MarkdownConverter（确保独立的 Playwright 实例）
        """
        # 在 try 块外导入，确保异常处理中也能使用
        from screenshot_tool.services.markdown_converter import MarkdownConverter, ConversionResult
        
        try:
            # 关键修复：Windows 平台需要设置 ProactorEventLoop 策略
            # Playwright 的同步 API 底层使用 asyncio，需要正确的事件循环策略
            if sys.platform == 'win32':
                import asyncio
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                    async_debug_log("已设置 WindowsProactorEventLoopPolicy", "MARKDOWN-WORKER")
                except Exception as e:
                    async_debug_log(f"设置事件循环策略失败: {e}", "MARKDOWN-WORKER")
            
            async_debug_log(f"开始转换 URL: {self._url}", "MARKDOWN-WORKER")
            
            # 关键：每次转换创建新的 converter 实例
            # 不复用 converter，因为其内部的 browser_fetcher 不是线程安全的
            converter = MarkdownConverter(self._config)
            
            result = converter.convert(self._url, save_dir=self._save_dir)
            
            async_debug_log(f"转换完成: success={result.success}", "MARKDOWN-WORKER")
            self.conversion_finished.emit(self._url, result)
            
        except Exception as e:
            # 记录详细错误信息
            import traceback
            error_msg = str(e)
            stack_trace = traceback.format_exc()
            async_debug_log(f"转换异常: {error_msg}\n{stack_trace}", "MARKDOWN-WORKER")
            
            # 创建失败结果
            result = ConversionResult(success=False, error=error_msg)
            self.conversion_finished.emit(self._url, result)


class OverlayScreenshotApp:
    """虎哥截图应用"""
    
    @staticmethod
    def _format_hotkey_display(hk_config) -> str:
        """格式化快捷键配置为显示字符串
        
        Args:
            hk_config: 快捷键配置对象，需要有 enabled, modifier, key 属性
            
        Returns:
            格式化的快捷键字符串，如 " (Ctrl+Alt+X)"，未启用时返回空字符串
        """
        if not hk_config.enabled:
            return ""
        modifier = "+".join(part.capitalize() for part in hk_config.modifier.split("+"))
        return f" ({modifier}+{hk_config.key.upper()})"
    
    def __init__(self, argv: list):
        """初始化应用"""
        # 开始测量启动时间
        # Feature: extreme-performance-optimization
        # Requirements: 1.1
        self._init_start_time = time.perf_counter()
        
        # 记录启动时间，用于启动保护（防止启动时意外触发截图）
        self._startup_time = time.time()
        
        # 获取错误日志记录器
        from screenshot_tool.core.error_logger import get_error_logger
        self._error_logger = get_error_logger()
        
        if self._error_logger:
            self._error_logger.log_debug("OverlayScreenshotApp 初始化开始")
        
        # 设置高DPI支持（必须在QApplication创建前）
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        self._app = QApplication(argv)
        self._app.setApplicationName(__app_name__)
        self._app.setApplicationVersion(__version__)
        self._app.setOrganizationName("HugeScreenshot")
        self._app.setQuitOnLastWindowClosed(False)
        
        # 安装崩溃处理器
        self._install_crash_handler()
        
        # 设置应用图标
        self._icon = create_app_icon()
        self._app.setWindowIcon(self._icon)
        
        # 配置管理器
        self._config_manager = ConfigManager()
        self._config_manager.load()
        
        # 内存管理器 - 启动内存监控
        # Feature: performance-ui-optimization
        # Requirements: 4.3, 4.4
        self._memory_manager = MemoryManager.instance()
        self._memory_manager.start()
        async_debug_log("内存管理器已启动", "MEMORY")
        
        # 检测并保存安装路径（用于静默更新）
        # Feature: fullupdate-inplace-install
        # Requirements: 1.1
        self._config_manager.detect_and_save_install_path()
        
        # 同步开机自启动状态
        self._sync_autostart()
        
        # 文件管理器
        self._file_manager = FileManager(self._config_manager.get_save_path())
        
        # 初始化OCR管理器
        self._init_ocr_manager()
        
        # 初始化自动OCR弹窗管理器
        self._auto_ocr_popup_manager = AutoOCRPopupManager(
            self._config_manager, 
            self._ocr_manager
        )
        # 连接 OCR 完成信号，保存最近的 OCR 结果（用于托盘菜单"OCR面板"功能）
        self._auto_ocr_popup_manager.ocr_completed.connect(self._on_auto_ocr_completed)
        # 连接分屏视图请求信号（已废弃，保留兼容）
        # Feature: screenshot-ocr-split-view
        # Requirements: 7.1, 7.2, 7.3
        self._auto_ocr_popup_manager.split_view_requested.connect(self._show_split_window)
        # 连接工作台窗口 OCR 请求信号
        # Feature: clipboard-ocr-merge
        # 截图后使用邮箱风格的工作台窗口
        self._auto_ocr_popup_manager.clipboard_history_ocr_requested.connect(
            self._on_clipboard_history_ocr_requested
        )
        
        # 覆盖层截图界面
        self._overlay = OverlayScreenshot(self._auto_ocr_popup_manager, self._config_manager)
        self._overlay.screenshotTaken.connect(self._on_screenshot_taken)
        self._overlay.screenshotCancelled.connect(self._on_screenshot_cancelled)
        self._overlay.pinRequested.connect(self._on_pin_requested)
        self._overlay.selectionReady.connect(self._on_selection_ready)  # 选区确定后自动OCR
        self._overlay.colorChanged.connect(self._on_draw_color_changed)  # 颜色改变时保存（兼容）
        self._overlay.toolColorChanged.connect(self._on_tool_color_changed)  # 工具颜色改变时保存
        self._overlay.toolWidthChanged.connect(self._on_tool_width_changed)  # 工具粗细改变时保存
        self._overlay.ankiRequested.connect(self._on_anki_requested)  # Anki制卡
        self._overlay.screenshotSaveRequested.connect(self._on_screenshot_save_requested)  # 保存到指定文件夹
        self._overlay.recordingRequested.connect(self._on_recording_requested)  # 录屏

        # 录屏组件 - 延迟导入以加速启动
        self._screen_recorder = None  # ScreenRecorder
        self._recording_overlay_manager = None  # RecordingOverlayManager
        self._is_recording = False  # 录制状态标志

        # 从配置加载各工具的颜色
        tool_colors = self._config_manager.get_all_tool_colors()
        self._overlay.set_tool_colors(tool_colors)
        
        # 从配置加载各工具的粗细
        tool_widths = self._config_manager.get_all_tool_widths()
        self._overlay.set_tool_widths(tool_widths)
        
        # 兼容旧配置：加载通用绘制颜色
        saved_color = self._config_manager.get_draw_color()
        if saved_color:
            self._overlay.set_draw_color(saved_color)
        
        # Anki制卡窗口
        self._anki_window = None
        
        # 贴图管理器 - 使用 LazyLoaderManager 延迟加载
        # Feature: performance-ui-optimization
        # Requirements: 1.3, 1.4
        self._ding_manager = None  # 延迟初始化，首次使用时通过 _get_ding_manager() 获取
        
        # 缓存的识别文字结果（用于快速显示）
        # 字典格式：{"paddle": result, "baidu": result}
        self._cached_ocr_results = {}
        self._cached_ocr_image_hash = None  # 用于判断图片是否变化
        self._cached_ocr_image = None  # 缓存的图片，用于后续百度OCR
        self._pending_baidu_image = None  # 等待百度OCR处理的图片
        
        # 最近的 OCR 结果（用于托盘菜单"OCR面板"功能）
        # Note: _standalone_ocr_window 已移除，OCR 功能已集成到工作台窗口
        # Feature: clipboard-ocr-merge, Requirements: 7.1
        self._last_ocr_result = None  # UnifiedOCRResult
        self._last_ocr_image = None  # QImage
        
        # 全局热键管理器 - 从配置加载快捷键和强制锁定设置
        # Feature: hotkey-force-lock
        # Requirements: 2.1, 7.1
        hotkey_config = self._config_manager.config.hotkey
        self._hotkey_manager = GlobalHotkeyManager(
            self.start_capture,
            modifier=hotkey_config.screenshot_modifier,
            key=hotkey_config.screenshot_key,
            force_lock=hotkey_config.force_lock,
            retry_interval_ms=hotkey_config.retry_interval_ms
        )
        # 设置状态回调
        self._hotkey_manager.set_status_callback(self._on_hotkey_status_changed)
        
        # 扩展快捷键管理器
        # Feature: extended-hotkeys
        self._extended_hotkey_managers: dict = {}
        self._init_extended_hotkeys()
        
        # OCR工作线程
        self._ocr_worker = None
        # OCR模型预加载线程
        self._ocr_preload_thread = None
        # 截图保存工作线程
        self._save_worker = None
        # 孤儿线程列表：保存未能及时停止的线程引用，防止 GC 销毁运行中的 QThread 导致崩溃
        self._orphan_threads: list = []
        
        # 后台 OCR 预处理防抖定时器
        from PySide6.QtCore import QTimer
        self._background_ocr_debounce_timer = QTimer()
        self._background_ocr_debounce_timer.setSingleShot(True)
        self._background_ocr_debounce_timer.timeout.connect(self._on_background_ocr_debounce_timeout)
        self._pending_background_ocr_image = None  # 待处理的图片
        self._BACKGROUND_OCR_DEBOUNCE_MS = 500  # 防抖延迟（毫秒）
        
        # 订阅系统管理器（必须在 _setup_tray 之前初始化）
        # Feature: subscription-system
        self._subscription_manager = None
        self._init_subscription_system()
        
        # 工作台管理器
        # Feature: clipboard-history
        self._clipboard_history_manager = None
        self._clipboard_history_window = None
        
        # 工作台临时预览状态锁
        # Feature: workbench-temporary-preview-python
        # 防止 _on_screenshot_taken 和 _on_clipboard_history_ocr_requested 同时触发时
        # 重复打开工作台
        self._workbench_opening = False
        
        # 后台 OCR 缓存管理器
        # Feature: background-ocr-cache
        self._background_ocr_cache_manager = None
        
        # 后台 OCR 缓存组件（新架构）
        # Feature: background-ocr-cache-python
        # Requirements: 4.1, 4.2
        self._system_idle_detector = None
        self._background_ocr_cache_worker = None
        
        self._init_clipboard_history()
        
        # 鼠标高亮管理器
        # Feature: mouse-highlight
        # Requirements: 1.1, 1.2, 1.3, 1.4
        self._mouse_highlight_manager = None
        self._init_mouse_highlight()
        
        # 系统托盘
        self._tray: QSystemTrayIcon = None
        self._setup_tray()
        
        # 公文格式化模式管理器
        self._gongwen_mode_manager = None
        self._init_gongwen_mode()
        
        # Markdown 模式管理器
        self._markdown_mode_manager = None
        self._markdown_converter = None
        self._markdown_dialog = None  # 网页转 MD 对话框引用，防止被垃圾回收
        
        # Markdown 转换队列和工作线程（新的对话框模式）
        self._markdown_url_queue = []  # URL 队列
        self._markdown_worker = None  # 当前工作线程
        
        self._init_markdown_mode()
        
        # 后台 Anki 导入管理器 - 连接完成通知
        self._setup_background_anki_importer()
        
        # 更新服务
        self._update_service = None
        self._init_update_service()
        
        # 下载状态管理器
        # Feature: embedded-download-progress
        # Requirements: 2.5
        from screenshot_tool.services.update_service import DownloadStateManager
        self._download_state_manager = DownloadStateManager()

        # 启动后台线程预加载OCR模型
        self._preload_ocr_model()
        
        # 主界面窗口
        # Feature: main-window
        # Requirements: 1.1, 7.1, 7.2, 7.3, 7.4, 7.5
        self._main_window = None
        self._init_main_window()
        
        # 分屏窗口（截图+OCR）
        # Feature: screenshot-ocr-split-view
        # Requirements: 7.1, 7.2, 7.3
        self._split_window = None
        
        # 极简工具栏
        # Feature: mini-toolbar
        # Requirements: 4.2, 4.4
        self._mini_toolbar = None
        self._init_mini_toolbar()
        
        # 启动时验证截图状态文件完整性
        # Feature: screenshot-state-restore
        # Requirements: 4.4
        self._verify_screenshot_state_on_startup()
        
        # 记录启动时间
        # Feature: extreme-performance-optimization
        # Requirements: 1.1
        startup_duration_ms = (time.perf_counter() - self._init_start_time) * 1000
        PerformanceMonitor.record("app_startup", startup_duration_ms)
        async_debug_log(f"应用启动耗时: {startup_duration_ms:.2f}ms", "PERF")
        
        # 检查是否超过目标（1500ms）
        if startup_duration_ms > 1500:
            async_debug_log(f"警告: 启动时间 {startup_duration_ms:.2f}ms 超过目标 1500ms", "PERF")
        
        if self._error_logger:
            self._error_logger.log_debug("OverlayScreenshotApp 初始化完成")
    
    def _install_crash_handler(self):
        """安装崩溃处理器"""
        try:
            from screenshot_tool.core.crash_handler import CrashHandler
            
            if self._error_logger:
                self._crash_handler = CrashHandler(self._error_logger)
                self._crash_handler.install(self._app)
            else:
                self._crash_handler = None
        except Exception as e:
            if self._error_logger:
                self._error_logger.log_warning(f"安装崩溃处理器失败: {e}")
            self._crash_handler = None
    
    def _setup_background_anki_importer(self):
        """设置后台 Anki 导入管理器"""
        try:
            from screenshot_tool.services.background_anki_importer import BackgroundAnkiImporter
            
            importer = BackgroundAnkiImporter.instance()
            importer.importFinished.connect(self._on_background_anki_import_finished)
        except (ImportError, AttributeError, RuntimeError) as e:
            ocr_debug_log(f"设置后台 Anki 导入管理器失败: {e}")
    
    def _on_background_anki_import_finished(self, result):
        """后台 Anki 导入完成回调"""
        if not self._tray:
            return
        
        # 获取通知开关状态
        notification_enabled = self._config_manager.config.notification.anki
        
        try:
            if result.success:
                # 成功通知可以被关闭
                if not notification_enabled:
                    return
                    
                if result.imported > 0:
                    msg = f"成功导入 {result.imported} 个单词"
                    if result.skipped > 0:
                        msg += f"，跳过 {result.skipped} 个"
                    if result.failed > 0:
                        msg += f"，失败 {result.failed} 个"
                    msg += f"\n牌组: {result.deck_name}"
                else:
                    msg = f"已导入截图到牌组 [{result.deck_name}]"
                
                self._tray.showMessage(
                    "Anki 导入完成",
                    msg,
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                error_msg = result.error or "未知错误"
                if "取消" in error_msg:
                    # 用户取消，不显示错误通知
                    return
                # 失败通知始终显示
                self._tray.showMessage(
                    "Anki 导入失败",
                    error_msg,
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
        except (AttributeError, RuntimeError) as e:
            ocr_debug_log(f"显示 Anki 导入通知失败: {e}")
    
    def _preload_ocr_model(self):
        """在后台线程预加载OCR模型"""
        def _load():
            try:
                ocr_debug_log("开始预加载OCR模型...")
                self._ocr_manager.preload_rapid()
                ocr_debug_log("OCR模型预加载完成")
            except (ImportError, RuntimeError, OSError) as e:
                ocr_debug_log(f"OCR模型预加载失败: {e}")
        
        # 在后台线程中加载，不阻塞UI
        self._ocr_preload_thread = threading.Thread(target=_load, daemon=True, name="OCR-Preload")
        self._ocr_preload_thread.start()
    
    def _init_subscription_system(self):
        """初始化订阅系统（异步）
        
        Feature: subscription-system
        Requirements: 2.3, 7.1
        
        为了加快启动速度，订阅系统初始化在后台线程执行。
        """
        # 先创建管理器实例（不初始化）
        try:
            from screenshot_tool.services.subscription import SubscriptionManager
            self._subscription_manager = SubscriptionManager(self._config_manager)
        except ImportError as e:
            async_debug_log(f"订阅系统模块导入失败: {e}", "SUBSCRIPTION")
            self._subscription_manager = None
            return
        except Exception as e:
            async_debug_log(f"订阅系统创建失败: {e}", "SUBSCRIPTION")
            self._subscription_manager = None
            return
        
        # 在后台线程初始化（避免阻塞启动）
        def init_in_background():
            try:
                if self._subscription_manager.initialize():
                    async_debug_log("订阅系统初始化成功", "SUBSCRIPTION")
                else:
                    async_debug_log("订阅系统初始化失败（可能未配置）", "SUBSCRIPTION")
            except Exception as e:
                async_debug_log(f"订阅系统初始化异常: {e}", "SUBSCRIPTION")
        
        import threading
        init_thread = threading.Thread(target=init_in_background, daemon=True)
        init_thread.start()
    
    def _init_clipboard_history(self):
        """初始化工作台管理器
        
        Feature: clipboard-history, background-ocr-cache
        Requirements: 1.1, 1.5
        """
        try:
            from screenshot_tool.core.clipboard_history_manager import ClipboardHistoryManager
            self._clipboard_history_manager = ClipboardHistoryManager()
            self._clipboard_history_manager.load()
            self._clipboard_history_manager.start_monitoring()
            async_debug_log("工作台管理器初始化成功", "CLIPBOARD")
            
            # 将管理器传递给 overlay（用于截图历史恢复功能）
            # Feature: screenshot-state-restore
            if self._overlay is not None:
                self._overlay.set_clipboard_history_manager(self._clipboard_history_manager)
                async_debug_log("已将工作台管理器传递给 overlay", "CLIPBOARD")
            
            # 预创建工作台窗口（急切初始化）
            # Feature: screenshot-ocr-split-view
            # 在后台创建窗口但不显示，这样截图时可以瞬间弹出
            # 使用 QTimer.singleShot 延迟创建，避免阻塞启动
            QTimer.singleShot(500, self._preload_clipboard_history_window)
            
            # 初始化后台 OCR 缓存管理器
            # Feature: background-ocr-cache
            # 在系统空闲时自动执行 OCR 并缓存结果
            self._init_background_ocr_cache()
            
        except Exception as e:
            async_debug_log(f"工作台管理器初始化失败: {e}", "CLIPBOARD")
            self._clipboard_history_manager = None
    
    def _preload_clipboard_history_window(self):
        """预加载工作台窗口（后台创建但不显示）
        
        Feature: screenshot-ocr-split-view, workbench-lazy-refresh
        
        急切初始化策略：在程序启动后延迟创建窗口，
        窗口创建后保持隐藏状态，截图时直接 show() 即可瞬间显示。
        
        关键改进：
        1. 在创建时就设置好 WindowStaysOnTopHint，避免窗口重建导致的闪烁
        2. 使用 skip_initial_refresh=True 跳过初始刷新，避免阻塞主线程
           历史记录会在窗口首次显示时延迟加载
        """
        if self._clipboard_history_manager is None:
            return
        
        if self._clipboard_history_window is not None:
            return  # 已经创建过了
        
        try:
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            
            # 创建窗口但不显示
            # Feature: workbench-lazy-refresh
            # 使用 skip_initial_refresh=True 跳过初始刷新，避免阻塞
            self._clipboard_history_window = ClipboardHistoryWindow(
                self._clipboard_history_manager,
                skip_initial_refresh=True  # 延迟刷新，首次显示时再加载
            )
            
            # 在创建时就设置好 WindowStaysOnTopHint，避免截图时修改导致闪烁
            # 这是避免 setWindowFlags() 导致窗口重建的关键
            topmost_flags = (
                self._clipboard_history_window._normal_window_flags |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self._clipboard_history_window.setWindowFlags(topmost_flags)
            
            # 设置 OCR 管理器
            if self._ocr_manager is not None:
                self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
            
            # 连接截图编辑和贴图信号
            self._clipboard_history_window.edit_screenshot_requested.connect(
                self._edit_screenshot_from_history
            )
            self._clipboard_history_window.ding_screenshot_requested.connect(
                self._ding_from_history
            )
            
            # 窗口保持隐藏状态，不调用 show()
            async_debug_log("工作台窗口预加载完成（后台隐藏，已设置置顶标志，延迟刷新）", "CLIPBOARD")
            
        except Exception as e:
            async_debug_log(f"工作台窗口预加载失败: {e}", "CLIPBOARD")
            self._clipboard_history_window = None
    
    def _init_background_ocr_cache(self):
        """初始化后台 OCR 缓存组件
        
        Feature: background-ocr-cache-python
        Requirements: 4.1, 4.2
        
        使用新架构：
        - SystemIdleDetector: 系统级空闲检测器
        - BackgroundOCRCacheWorker: 后台 OCR 工作器
        
        在系统空闲时自动执行 OCR 并缓存结果，
        提升工作台 OCR 预览的响应速度。
        """
        if self._clipboard_history_manager is None:
            async_debug_log("工作台管理器未初始化，跳过后台 OCR 缓存初始化", "OCR-CACHE")
            return
        
        try:
            # 1. 创建 SystemIdleDetector 实例
            from screenshot_tool.services.system_idle_detector import SystemIdleDetector
            self._system_idle_detector = SystemIdleDetector()
            async_debug_log("SystemIdleDetector 创建成功", "OCR-CACHE")
            
            # 2. 创建 BackgroundOCRCacheWorker 实例
            from screenshot_tool.services.background_ocr_cache_worker import (
                BackgroundOCRCacheWorker
            )
            self._background_ocr_cache_worker = BackgroundOCRCacheWorker()
            async_debug_log("BackgroundOCRCacheWorker 创建成功", "OCR-CACHE")
            
            # 3. 连接 worker 到 idle detector
            # Requirement 4.1: 使用现有的 RapidOCR_Service（通过 worker 内部调用）
            self._background_ocr_cache_worker.connect_to_idle_detector(
                self._system_idle_detector
            )
            async_debug_log("Worker 已连接到 IdleDetector", "OCR-CACHE")
            
            # 4. 设置历史记录管理器
            # Requirement 4.2: 使用现有的 History_Manager
            self._background_ocr_cache_worker.set_history_manager(
                self._clipboard_history_manager
            )
            async_debug_log("Worker 已设置 HistoryManager", "OCR-CACHE")
            
            # 5. 连接信号用于监控（可选）
            self._background_ocr_cache_worker.ocr_completed.connect(
                self._on_background_ocr_completed
            )
            self._background_ocr_cache_worker.error_occurred.connect(
                self._on_background_ocr_error
            )
            
            # 6. 延迟启动组件，避免影响程序启动速度
            # 使用 QTimer.singleShot 延迟 30 秒启动
            QTimer.singleShot(30000, self._start_background_ocr_components)
            
            async_debug_log("后台 OCR 缓存组件初始化成功，将在 30 秒后启动", "OCR-CACHE")
            
        except Exception as e:
            async_debug_log(f"后台 OCR 缓存组件初始化失败: {e}", "OCR-CACHE")
            self._system_idle_detector = None
            self._background_ocr_cache_worker = None
    
    def _start_background_ocr_components(self):
        """启动后台 OCR 缓存组件
        
        延迟启动，避免影响程序启动速度。
        
        Feature: background-ocr-cache-python
        """
        try:
            # 启动空闲检测器
            if self._system_idle_detector is not None:
                self._system_idle_detector.start_monitoring()
                async_debug_log("SystemIdleDetector 已启动监控", "OCR-CACHE")
            
            # 启动工作器
            if self._background_ocr_cache_worker is not None:
                self._background_ocr_cache_worker.start()
                async_debug_log("BackgroundOCRCacheWorker 已启动", "OCR-CACHE")
                
        except Exception as e:
            async_debug_log(f"启动后台 OCR 缓存组件失败: {e}", "OCR-CACHE")
    
    def _on_background_ocr_completed(self, item_id: str, text: str):
        """后台 OCR 完成回调
        
        Args:
            item_id: 历史记录项目 ID
            text: OCR 识别结果文本
            
        Feature: background-ocr-cache-python
        """
        # 记录日志（可选：可以在这里触发 UI 更新）
        text_preview = text[:50] + "..." if len(text) > 50 else text
        async_debug_log(f"后台 OCR 完成: {item_id}, 文本: {text_preview}", "OCR-CACHE")
    
    def _on_background_ocr_error(self, item_id: str, error: str):
        """后台 OCR 错误回调
        
        Args:
            item_id: 历史记录项目 ID
            error: 错误信息
            
        Feature: background-ocr-cache-python
        """
        async_debug_log(f"后台 OCR 错误: {item_id}, 错误: {error}", "OCR-CACHE")
    
    def _init_mouse_highlight(self):
        """初始化鼠标高亮管理器
        
        Feature: mouse-highlight
        Requirements: 1.1, 1.2, 1.5, 1.6
        """
        self._spotlight_hotkey_registered = False
        try:
            from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager
            self._mouse_highlight_manager = MouseHighlightManager(self._config_manager)
            # 恢复上次状态
            self._mouse_highlight_manager.restore_state()
            async_debug_log("鼠标高亮管理器初始化成功", "MOUSE-HIGHLIGHT")
            
            # 注册聚光灯热键 Alt+S
            self._register_spotlight_hotkey()
        except Exception as e:
            async_debug_log(f"鼠标高亮管理器初始化失败: {e}", "MOUSE-HIGHLIGHT")
            self._mouse_highlight_manager = None
    
    def _register_spotlight_hotkey(self):
        """注册聚光灯切换热键 Alt+S"""
        try:
            import keyboard
            keyboard.add_hotkey('alt+s', self._toggle_spotlight, suppress=False)
            self._spotlight_hotkey_registered = True
            async_debug_log("聚光灯热键 Alt+S 注册成功", "MOUSE-HIGHLIGHT")
        except ImportError:
            async_debug_log("keyboard 库未安装，聚光灯热键不可用", "MOUSE-HIGHLIGHT")
        except Exception as e:
            async_debug_log(f"聚光灯热键注册失败: {e}", "MOUSE-HIGHLIGHT")
    
    def _unregister_spotlight_hotkey(self):
        """注销聚光灯热键"""
        if self._spotlight_hotkey_registered:
            try:
                import keyboard
                keyboard.remove_hotkey('alt+s')
                self._spotlight_hotkey_registered = False
            except Exception:
                pass
    
    def _init_main_window(self):
        """初始化主界面窗口
        
        Feature: main-window
        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
        """
        async_debug_log("开始初始化主界面窗口", "MAIN-WINDOW")
        try:
            from screenshot_tool.ui.main_window import MainWindow
            async_debug_log("MainWindow 模块导入成功", "MAIN-WINDOW")
            
            self._main_window = MainWindow(config_manager=self._config_manager)
            async_debug_log("MainWindow 实例创建成功", "MAIN-WINDOW")
            
            # 连接信号
            self._main_window.screenshot_requested.connect(self.start_capture)
            self._main_window.settings_requested.connect(self._open_settings)
            self._main_window.feature_activated.connect(self._on_main_window_feature)
            
            # 注册功能回调
            self._main_window.register_feature_callback("screenshot", self.start_capture)
            # 录屏功能已移至截图工具栏，从主界面移除
            # Feature: recording-settings-panel, Requirements: 6.2
            self._main_window.register_feature_callback("web_to_md", self._start_markdown_mode)
            self._main_window.register_feature_callback("file_to_md", self._start_pdf_convert)
            self._main_window.register_feature_callback("word_format", self._show_gongwen_dialog)
            self._main_window.register_feature_callback("ocr_panel", self._open_ocr_panel)
            self._main_window.register_feature_callback("regulation", self._open_regulation_search)
            self._main_window.register_feature_callback("clipboard", self._open_clipboard_history)
            self._main_window.register_feature_callback("mouse_highlight", self._open_mouse_highlight_debug_panel)
            # 系统工具功能回调
            # Feature: system-tools
            self._main_window.register_feature_callback("power_manager", self._open_scheduled_shutdown)
            # 扩展快捷键功能回调
            # Feature: extended-hotkeys
            self._main_window.register_feature_callback("main_window", self._show_main_window)
            self._main_window.register_feature_callback("spotlight", self._toggle_spotlight)
            
            # 连接欢迎提示关闭信号
            self._main_window._welcome_overlay.dismissed.connect(self._on_welcome_dismissed)
            
            # 更新热键状态
            if self._hotkey_manager:
                status = self._hotkey_manager.get_registration_status()
                self._main_window.update_hotkey_status(status)
            
            async_debug_log("主界面窗口初始化成功", "MAIN-WINDOW")
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            async_debug_log(f"主界面窗口初始化失败: {e}\n{error_detail}", "MAIN-WINDOW")
            self._main_window = None
    
    def _init_mini_toolbar(self):
        """初始化极简工具栏
        
        Feature: mini-toolbar
        Requirements: 4.2, 4.4
        """
        async_debug_log("开始初始化极简工具栏", "MINI-TOOLBAR")
        try:
            from screenshot_tool.ui.mini_toolbar import MiniToolbar
            async_debug_log("MiniToolbar 模块导入成功", "MINI-TOOLBAR")
            
            self._mini_toolbar = MiniToolbar(config_manager=self._config_manager)
            async_debug_log("MiniToolbar 实例创建成功", "MINI-TOOLBAR")
            
            # 连接信号
            self._mini_toolbar.screenshot_requested.connect(self.start_capture)
            self._mini_toolbar.expand_requested.connect(self._on_mini_toolbar_expand)
            self._mini_toolbar.feature_triggered.connect(self._on_mini_toolbar_feature)
            
            # 注册功能回调
            self._mini_toolbar.register_feature_callback("main_window", self._show_main_window)
            self._mini_toolbar.register_feature_callback("clipboard", self._open_clipboard_history)
            self._mini_toolbar.register_feature_callback("ocr_panel", self._open_ocr_panel)
            self._mini_toolbar.register_feature_callback("spotlight", self._toggle_spotlight)
            
            # 连接主窗口的极简模式请求信号
            if self._main_window:
                self._main_window.mini_mode_requested.connect(self._show_mini_toolbar)
            
            async_debug_log("极简工具栏初始化成功", "MINI-TOOLBAR")
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            async_debug_log(f"极简工具栏初始化失败: {e}\n{error_detail}", "MINI-TOOLBAR")
            self._mini_toolbar = None
    
    def _verify_screenshot_state_on_startup(self):
        """启动时验证截图状态文件完整性
        
        Feature: screenshot-state-restore
        Requirements: 4.4
        
        应用启动时验证状态文件，如果损坏则清理并记录日志。
        """
        try:
            from screenshot_tool.core.screenshot_state_manager import ScreenshotStateManager
            
            state_manager = ScreenshotStateManager()
            
            # 检查是否有保存的状态
            if not state_manager.has_saved_state():
                async_debug_log("启动时无保存的截图状态", "STATE-RESTORE")
                return
            
            # 验证状态文件完整性
            if state_manager.verify_state_integrity():
                async_debug_log("启动时截图状态文件验证通过", "STATE-RESTORE")
            else:
                # 状态文件损坏，清理并记录日志
                async_debug_log("启动时截图状态文件损坏，正在清理", "STATE-RESTORE")
                state_manager.clear_state()
                async_debug_log("损坏的截图状态文件已清理", "STATE-RESTORE")
                
        except Exception as e:
            async_debug_log(f"启动时验证截图状态失败: {e}", "STATE-RESTORE")
    
    def _on_mini_toolbar_expand(self):
        """极简工具栏展开按钮点击回调
        
        切换到主窗口模式。
        
        Feature: mini-toolbar
        Requirements: 4.3
        """
        async_debug_log("极简工具栏请求展开到主窗口", "MINI-TOOLBAR")
        if self._mini_toolbar:
            self._mini_toolbar.hide()
        self._show_main_window()
    
    def _on_mini_toolbar_feature(self, feature_id: str):
        """极简工具栏功能触发回调
        
        Feature: mini-toolbar
        """
        async_debug_log(f"极简工具栏功能触发: {feature_id}", "MINI-TOOLBAR")
    
    def _show_mini_toolbar(self):
        """显示极简工具栏
        
        Feature: mini-toolbar
        Requirements: 4.1, 4.2
        """
        async_debug_log(f"_show_mini_toolbar 被调用, _mini_toolbar={self._mini_toolbar is not None}", "MINI-TOOLBAR")
        
        # 隐藏主窗口
        if self._main_window and self._main_window.isVisible():
            self._main_window.hide()
        
        # 显示极简工具栏
        if self._mini_toolbar:
            self._mini_toolbar.show_and_activate()
            async_debug_log("极简工具栏已显示", "MINI-TOOLBAR")
        else:
            async_debug_log("极简工具栏为 None，无法显示", "MINI-TOOLBAR")
    
    def _on_main_window_feature(self, feature_id: str):
        """主界面功能激活回调
        
        Feature: main-window
        """
        async_debug_log(f"主界面功能激活: {feature_id}", "MAIN-WINDOW")
    
    def _on_welcome_dismissed(self):
        """欢迎提示关闭回调，保存配置
        
        Feature: main-window
        Requirements: 8.5
        """
        self._config_manager.config.main_window.show_welcome = False
        self._config_manager.save()
        async_debug_log("欢迎提示已关闭，配置已保存", "MAIN-WINDOW")
    
    def _show_last_pin(self):
        """显示最近的贴图（从工作台）
        
        Feature: main-window
        """
        if self._clipboard_history_manager:
            from screenshot_tool.core.clipboard_history_manager import ContentType, get_clipboard_data_dir
            from PySide6.QtGui import QCursor
            
            items = self._clipboard_history_manager.get_history()
            # 找到最近的一张图片
            for item in items:
                if item.content_type == ContentType.IMAGE and item.image_path:
                    image_full_path = os.path.join(get_clipboard_data_dir(), item.image_path)
                    if os.path.exists(image_full_path):
                        image = QImage(image_full_path)
                        if not image.isNull():
                            # 使用鼠标当前位置作为贴图位置
                            position = QCursor.pos()
                            self._get_ding_manager().create_ding(image, position)
                            return
        
        # 如果没有历史记录，提示用户
        if self._tray:
            self._tray.showMessage(
                "贴图",
                "没有可用的截图历史，请先截图",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _start_recording_from_main(self):
        """从主界面启动录屏设置面板
        
        Feature: recording-settings-panel
        Requirements: 1.1
        """
        # 导入录屏设置面板
        from screenshot_tool.ui.recording_settings_panel import RecordingSettingsPanel
        
        # 显示录屏设置面板
        panel = RecordingSettingsPanel.show_panel(self._config_manager, self._main_window)
        
        # 连接开始录制信号
        panel.start_recording_requested.connect(self._on_recording_panel_start_requested)
        
        async_debug_log("打开录屏设置面板", "RECORDING")
    
    def _on_recording_panel_start_requested(self):
        """录屏设置面板请求开始录制
        
        Feature: recording-settings-panel
        Requirements: 4.2
        """
        # 隐藏主窗口
        if self._main_window:
            self._main_window.hide()
        
        # 延迟启动录屏，让窗口有时间隐藏
        QTimer.singleShot(100, self._start_recording_mode)
    
    def _start_recording_mode(self):
        """启动录屏模式"""
        # 调用现有的录屏启动逻辑
        self._on_recording_requested(None)
    
    def _init_extended_hotkeys(self):
        """初始化扩展快捷键
        
        为主界面、工作台、OCR面板、聚光灯、状态恢复创建全局热键管理器。
        
        Feature: extended-hotkeys
        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
        """
        async_debug_log("开始初始化扩展快捷键", "EXTENDED-HOTKEYS")
        
        config = self._config_manager.config
        
        # 定义扩展快捷键配置
        hotkey_definitions = [
            ("main_window", config.main_window_hotkey, self._on_main_window_hotkey),
            ("clipboard", config.clipboard_hotkey, self._on_clipboard_hotkey),
            ("ocr_panel", config.ocr_panel_hotkey, self._on_ocr_panel_hotkey),
            ("spotlight", config.spotlight_hotkey, self._on_spotlight_hotkey),
            ("mouse_highlight", config.mouse_highlight_hotkey, self._on_mouse_highlight_hotkey),
            ("state_restore", config.state_restore_hotkey, self._on_state_restore_hotkey),
        ]
        
        for feature_id, hotkey_config, callback in hotkey_definitions:
            if hotkey_config.enabled:
                try:
                    manager = GlobalHotkeyManager(
                        callback,
                        modifier=hotkey_config.modifier,
                        key=hotkey_config.key,
                        force_lock=False,  # 扩展快捷键不使用强制锁定
                        retry_interval_ms=3000
                    )
                    self._extended_hotkey_managers[feature_id] = manager
                    async_debug_log(
                        f"扩展快捷键 {feature_id} 注册成功: {hotkey_config.get_hotkey_string()}",
                        "EXTENDED-HOTKEYS"
                    )
                except Exception as e:
                    async_debug_log(
                        f"扩展快捷键 {feature_id} 注册失败: {e}",
                        "EXTENDED-HOTKEYS"
                    )
        
        async_debug_log(
            f"扩展快捷键初始化完成，已注册 {len(self._extended_hotkey_managers)} 个",
            "EXTENDED-HOTKEYS"
        )
    
    def _update_extended_hotkeys(self):
        """更新扩展快捷键
        
        清理旧的热键管理器，根据新配置重新创建。
        
        Feature: extended-hotkeys
        Requirements: 2.3, 2.4, 2.5
        """
        async_debug_log("开始更新扩展快捷键", "EXTENDED-HOTKEYS")
        
        # 清理旧的热键管理器（先复制 keys 避免迭代时修改字典）
        for feature_id in list(self._extended_hotkey_managers.keys()):
            manager = self._extended_hotkey_managers[feature_id]
            try:
                manager.cleanup()
                async_debug_log(f"扩展快捷键 {feature_id} 已清理", "EXTENDED-HOTKEYS")
            except Exception as e:
                async_debug_log(f"清理扩展快捷键 {feature_id} 失败: {e}", "EXTENDED-HOTKEYS")
        
        self._extended_hotkey_managers.clear()
        
        # 重新初始化
        self._init_extended_hotkeys()
    
    def _on_main_window_hotkey(self):
        """主界面快捷键回调
        
        Feature: extended-hotkeys
        Requirements: 5.1
        
        切换逻辑：按一次打开，再按一次最小化
        """
        async_debug_log("主界面快捷键触发", "EXTENDED-HOTKEYS")
        self._toggle_main_window()
    
    def _on_clipboard_hotkey(self):
        """工作台快捷键回调
        
        Feature: extended-hotkeys
        Requirements: 5.2
        """
        async_debug_log("工作台快捷键触发", "EXTENDED-HOTKEYS")
        self._open_clipboard_history()
    
    def _on_ocr_panel_hotkey(self):
        """OCR面板快捷键回调 - 改为打开工作台窗口
        
        Feature: clipboard-ocr-merge
        Requirements: 7.3
        
        OCR 功能已集成到工作台窗口中，此热键现在打开工作台窗口
        切换逻辑：按一次打开，再按一次最小化
        """
        async_debug_log("OCR面板快捷键触发 -> 打开工作台窗口", "EXTENDED-HOTKEYS")
        self._toggle_clipboard_history()
    
    def _on_spotlight_hotkey(self):
        """聚光灯快捷键回调
        
        Feature: extended-hotkeys
        Requirements: 5.4
        """
        async_debug_log("聚光灯快捷键触发", "EXTENDED-HOTKEYS")
        self._toggle_spotlight()
    
    def _on_mouse_highlight_hotkey(self):
        """鼠标高亮快捷键回调
        
        Feature: extended-hotkeys
        """
        async_debug_log("鼠标高亮快捷键触发", "EXTENDED-HOTKEYS")
        self._toggle_mouse_highlight()
    
    def _on_state_restore_hotkey(self):
        """截图状态恢复快捷键回调
        
        Feature: screenshot-state-restore
        Requirements: 5.1, 5.3
        """
        async_debug_log("截图状态恢复快捷键触发", "STATE-RESTORE")
        self._restore_screenshot_state()
    
    def _restore_screenshot_state(self):
        """恢复上次截图状态
        
        Feature: screenshot-state-restore
        Requirements: 2.1, 2.2, 2.3, 5.1, 5.3
        """
        # 检查是否有活动的截图会话
        if self._overlay and self._overlay.isVisible():
            async_debug_log("截图会话进行中，忽略恢复请求", "STATE-RESTORE")
            return
        
        try:
            from screenshot_tool.core.screenshot_state_manager import ScreenshotStateManager
            
            state_manager = ScreenshotStateManager()
            
            # 检查是否有保存的状态
            if not state_manager.has_saved_state():
                async_debug_log("没有可恢复的截图状态", "STATE-RESTORE")
                if self._tray:
                    self._tray.showMessage(
                        "恢复截图",
                        "没有可恢复的截图状态",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
                return
            
            # 加载状态
            result = state_manager.load_state()
            if result is None:
                async_debug_log("加载截图状态失败", "STATE-RESTORE")
                if self._tray:
                    self._tray.showMessage(
                        "恢复截图",
                        "加载截图状态失败，文件可能已损坏",
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                return
            
            state, image = result
            
            # 恢复到截图界面
            if self._overlay.restore_from_state(state, image):
                # 显示截图界面
                self._overlay.show()
                self._overlay.activateWindow()
                self._overlay.update()
                
                async_debug_log(f"截图状态已恢复: {len(state.annotations)} 个标注", "STATE-RESTORE")
                if self._tray:
                    self._tray.showMessage(
                        "恢复截图",
                        f"已恢复上次截图，包含 {len(state.annotations)} 个标注",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
            else:
                async_debug_log("恢复截图状态到界面失败", "STATE-RESTORE")
                if self._tray:
                    self._tray.showMessage(
                        "恢复截图",
                        "恢复截图状态失败",
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                    
        except Exception as e:
            async_debug_log(f"恢复截图状态异常: {e}", "STATE-RESTORE")
            if self._tray:
                self._tray.showMessage(
                    "恢复截图",
                    f"恢复失败: {str(e)}",
                    QSystemTrayIcon.MessageIcon.Critical,
                    3000
                )
    
    def _show_main_window(self):
        """显示主界面窗口
        
        Feature: main-window
        Requirements: 5.1, 5.2, 5.3
        """
        async_debug_log(f"_show_main_window 被调用, _main_window={self._main_window is not None}", "MAIN-WINDOW")
        if self._main_window:
            # 检查是否首次启动需要显示欢迎提示
            if self._config_manager.config.main_window.show_welcome:
                self._main_window.show_welcome()
            
            self._main_window.show_and_activate()
            async_debug_log("主界面窗口已显示", "MAIN-WINDOW")
        else:
            async_debug_log("主界面窗口为 None，无法显示", "MAIN-WINDOW")
    
    def _toggle_main_window(self):
        """切换主界面窗口显示/最小化
        
        Feature: extended-hotkeys
        
        按一次快捷键打开，再按一次最小化
        - 窗口不可见或最小化：显示并激活
        - 窗口可见且未最小化：最小化
        """
        if not self._main_window:
            async_debug_log("主界面窗口为 None，无法切换", "MAIN-WINDOW")
            return
        
        # 检查窗口状态
        is_visible = self._main_window.isVisible()
        is_minimized = self._main_window.isMinimized()
        
        async_debug_log(f"主界面状态: visible={is_visible}, minimized={is_minimized}", "MAIN-WINDOW")
        
        if is_visible and not is_minimized:
            # 窗口已显示且未最小化，最小化
            self._main_window.showMinimized()
            async_debug_log("主界面窗口已最小化", "MAIN-WINDOW")
        else:
            # 窗口未显示或已最小化，显示并激活
            self._show_main_window()
        
    def _setup_tray(self):
        """设置系统托盘
        
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # 如果没有系统托盘，显示主界面而不是截图
            # 避免启动时意外触发截图导致屏幕卡死
            async_debug_log("系统托盘不可用，将显示主界面", "TRAY")
            QTimer.singleShot(100, self._show_main_window)
            return
        
        # 如果已有托盘图标，只更新菜单而不重新创建
        is_new_tray = self._tray is None
        if is_new_tray:
            self._tray = QSystemTrayIcon(self._icon, self._app)
        
        # 获取当前快捷键显示
        hotkey_modifier = self._config_manager.config.hotkey.screenshot_modifier
        hotkey_key = self._config_manager.config.hotkey.screenshot_key
        hotkey_display = f"{hotkey_modifier.title()}+{hotkey_key.upper()}"
        
        # 根据热键状态设置 tooltip
        tooltip = self._get_tray_tooltip(hotkey_display)
        self._tray.setToolTip(tooltip)
        
        # 保存旧菜单引用，稍后安全删除
        old_menu = None
        if not is_new_tray:
            try:
                old_menu = self._tray.contextMenu()
            except RuntimeError:
                # 菜单对象可能已被删除
                pass
        
        # 托盘菜单 - 注意：QSystemTrayIcon 不接管菜单所有权，需要手动管理
        # 使用 None 作为 parent，因为 QSystemTrayIcon 不是 QWidget
        menu = QMenu()
        
        # 获取扩展快捷键配置
        # Feature: extended-hotkeys
        main_window_hk = self._config_manager.config.main_window_hotkey
        clipboard_hk = self._config_manager.config.clipboard_hotkey
        ocr_panel_hk = self._config_manager.config.ocr_panel_hotkey
        spotlight_hk = self._config_manager.config.spotlight_hotkey
        
        # 显示主界面
        # Feature: main-window
        # Requirements: 5.1, 5.2
        main_window_hotkey_str = self._format_hotkey_display(main_window_hk)
        main_window_action = QAction(f"🏠 显示主界面{main_window_hotkey_str}", menu)
        main_window_action.triggered.connect(self._show_main_window)
        menu.addAction(main_window_action)
        
        # 极简工具栏
        # Feature: mini-toolbar
        # Requirements: 6.1, 6.2
        mini_toolbar_action = QAction("📌 极简工具栏", menu)
        mini_toolbar_action.triggered.connect(self._show_mini_toolbar)
        menu.addAction(mini_toolbar_action)
        
        menu.addSeparator()
        
        # 截图
        capture_action = QAction(f"📷 截图 ({hotkey_display})", menu)
        capture_action.triggered.connect(self.start_capture)
        menu.addAction(capture_action)
        
        # 恢复上次截图
        # Feature: screenshot-state-restore
        # Requirements: 5.2
        state_restore_hk = self._config_manager.config.state_restore_hotkey
        state_restore_hotkey_str = self._format_hotkey_display(state_restore_hk)
        restore_action = QAction(f"↩️ 恢复上次截图{state_restore_hotkey_str}", menu)
        restore_action.triggered.connect(self._restore_screenshot_state)
        menu.addAction(restore_action)
        
        menu.addSeparator()
        
        # Word排版 - 使用对话框模式（不再显示快捷键）
        # Feature: gongwen-dialog
        gongwen_action = QAction("📋 Word排版", menu)
        gongwen_action.triggered.connect(self._show_gongwen_dialog)
        menu.addAction(gongwen_action)
        
        # 网页转MD - 不显示快捷键（使用对话框模式）
        # Feature: web-to-markdown-dialog
        # Requirements: 1.1, 1.2
        markdown_action = QAction("📝 网页转MD", menu)
        markdown_action.triggered.connect(self._start_markdown_mode)
        menu.addAction(markdown_action)
        
        # 文件转MD
        pdf_action = QAction("📄 文件转MD", menu)
        pdf_action.triggered.connect(self._start_pdf_convert)
        menu.addAction(pdf_action)
        
        # 识别文字 - 打开最近的识别结果窗口
        ocr_panel_hotkey_str = self._format_hotkey_display(ocr_panel_hk)
        ocr_panel_action = QAction(f"🔤 识别文字{ocr_panel_hotkey_str}", menu)
        ocr_panel_action.triggered.connect(self._open_ocr_panel)
        menu.addAction(ocr_panel_action)
        
        # 规章查询 - CAAC 规章和规范性文件查询
        # Feature: caac-regulation-search
        # Requirements: 1.1, 1.2
        regulation_action = QAction("📜 规章查询", menu)
        regulation_action.triggered.connect(self._open_regulation_search)
        menu.addAction(regulation_action)
        
        # 工作台
        # Feature: clipboard-history
        # Requirements: 4.1, 4.2
        clipboard_hotkey_str = self._format_hotkey_display(clipboard_hk)
        clipboard_history_action = QAction(f"📋 工作台{clipboard_hotkey_str}", menu)
        clipboard_history_action.triggered.connect(self._open_clipboard_history)
        menu.addAction(clipboard_history_action)
        
        # 鼠标高亮
        # Feature: mouse-highlight
        # Requirements: 1.1, 1.2, 1.3, 1.4
        self._mouse_highlight_action = QAction("🖱️ 鼠标高亮", menu)
        self._mouse_highlight_action.setCheckable(True)
        if self._mouse_highlight_manager:
            self._mouse_highlight_action.setChecked(self._mouse_highlight_manager.is_enabled())
        self._mouse_highlight_action.triggered.connect(self._toggle_mouse_highlight)
        menu.addAction(self._mouse_highlight_action)
        
        # 聚光灯切换（鼠标高亮的子功能）
        spotlight_hotkey_str = self._format_hotkey_display(spotlight_hk)
        self._spotlight_action = QAction(f"🔦 聚光灯{spotlight_hotkey_str}", menu)
        self._spotlight_action.setCheckable(True)
        if self._mouse_highlight_manager:
            self._spotlight_action.setChecked(self._mouse_highlight_manager.is_spotlight_enabled())
        self._spotlight_action.triggered.connect(self._toggle_spotlight)
        menu.addAction(self._spotlight_action)

        menu.addSeparator()
        
        # 订阅系统菜单项
        # Feature: subscription-system
        # Requirements: 1.2, 3.3
        # 订阅相关菜单项已移至设置界面的"账户"标签页
        
        menu.addSeparator()
        
        # 设置
        settings_action = QAction("⚙️ 设置", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        
        # 退出
        quit_action = QAction("❌ 退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self._tray.setContextMenu(menu)
        
        # 安全删除旧菜单（使用 deleteLater 确保不会在菜单显示时删除）
        if old_menu is not None:
            try:
                old_menu.deleteLater()
            except RuntimeError:
                # 菜单对象可能已被删除
                pass
        
        # 只在首次创建时连接信号和显示
        if is_new_tray:
            # 单击托盘图标开始截图
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
    
    def _get_tray_tooltip(self, hotkey_display: str) -> str:
        """获取托盘 tooltip 文本
        
        Args:
            hotkey_display: 热键显示文本，如 "Alt+A"
            
        Returns:
            tooltip 文本
            
        Feature: hotkey-force-lock
        Requirements: 3.1, 3.2, 3.3
        """
        base_tooltip = f"{__app_name__} v{__version__}"
        
        if self._hotkey_manager is None:
            return f"{base_tooltip} - {hotkey_display} 截图"
        
        status = self._hotkey_manager.get_registration_status()
        
        if status == HotkeyStatus.REGISTERED:
            return f"{base_tooltip} - {hotkey_display} 截图"
        elif status == HotkeyStatus.WAITING:
            return f"{base_tooltip} - 等待热键注册..."
        elif status == HotkeyStatus.FAILED:
            return f"{base_tooltip} - 热键冲突！点击托盘打开主界面"
        else:
            return f"{base_tooltip} - {hotkey_display} 截图"
    
    def _on_hotkey_status_changed(self, status: str):
        """热键状态变化回调
        
        Args:
            status: 新状态
            
        Feature: hotkey-force-lock, main-window
        Requirements: 3.1, 3.2, 3.3, 3.4, 5.2, 5.3, 5.4, 6.2, 6.3
        """
        # 更新托盘 tooltip
        if self._tray:
            hotkey_modifier = self._config_manager.config.hotkey.screenshot_modifier
            hotkey_key = self._config_manager.config.hotkey.screenshot_key
            hotkey_display = f"{hotkey_modifier.title()}+{hotkey_key.upper()}"
            tooltip = self._get_tray_tooltip(hotkey_display)
            self._tray.setToolTip(tooltip)
        
        # 更新主窗口状态栏
        # Feature: main-window
        # Requirements: 6.2, 6.3
        if self._main_window:
            self._main_window.update_hotkey_status(status)
        
        # 处理状态变化通知
        if status == HotkeyStatus.REGISTERED:
            # 注册成功，如果之前是等待状态，显示成功通知
            if self._hotkey_manager and self._hotkey_manager._notification_shown:
                self._show_hotkey_notification(
                    "热键注册成功",
                    f"热键 {hotkey_display} 已成功注册",
                    QSystemTrayIcon.MessageIcon.Information
                )
        elif status == HotkeyStatus.FAILED:
            # 注册失败且未启用强制锁定，显示冲突通知
            if self._hotkey_manager and not self._hotkey_manager._notification_shown:
                self._hotkey_manager._notification_shown = True
                self._show_hotkey_notification(
                    "热键冲突",
                    f"热键 {hotkey_display} 被其他软件占用\n"
                    "建议在设置中启用「强制锁定热键」",
                    QSystemTrayIcon.MessageIcon.Warning
                )
        elif status == HotkeyStatus.WAITING:
            # 进入等待状态，首次显示通知
            if self._hotkey_manager and not self._hotkey_manager._notification_shown:
                self._hotkey_manager._notification_shown = True
                self._show_hotkey_notification(
                    "热键冲突",
                    f"热键 {hotkey_display} 被占用，正在尝试重新注册...",
                    QSystemTrayIcon.MessageIcon.Information
                )
    
    def _show_hotkey_notification(self, title: str, message: str,
                                   icon: QSystemTrayIcon.MessageIcon):
        """显示热键相关通知

        Args:
            title: 通知标题
            message: 通知内容
            icon: 通知图标

        Feature: hotkey-force-lock
        Requirements: 5.2, 5.3, 5.4
        """
        if self._tray:
            self._tray.showMessage(title, message, icon, 5000)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """托盘图标激活
        
        Feature: main-window
        Requirements: 4.3
        """
        async_debug_log(f"托盘图标激活: reason={reason}", "TRAY")
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 单击：打开主界面
            async_debug_log("托盘单击，准备显示主界面", "TRAY")
            self._show_main_window()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # 双击：也打开主界面（保持一致性）
            async_debug_log("托盘双击，准备显示主界面", "TRAY")
            self._show_main_window()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # 右键点击显示菜单，不做任何操作（菜单由 Qt 自动处理）
            async_debug_log("托盘右键，显示菜单", "TRAY")
            pass
    
    def _close_blocking_dialogs(self):
        """截图前的准备工作（不再隐藏窗口）
        
        根据截图软件的正确实现原理：
        1. 不需要隐藏任何窗口 - 直接截取屏幕像素快照
        2. 模态对话框只是屏幕上的像素，会被一起截取
        3. 截图覆盖层设置为 TOPMOST，覆盖在所有窗口上方获取控制权
        
        这样可以避免：
        - 隐藏/恢复窗口导致的各种问题
        - 模态对话框恢复失败导致程序卡死
        - 截图中出现透明窗口（隐藏动画未完成）
        """
        # 不再隐藏任何窗口
        # 截图覆盖层会通过 TOPMOST 属性覆盖在所有窗口上方
        self._hidden_windows_for_capture = []
        async_debug_log("截图准备完成（不隐藏窗口，直接截取屏幕像素）", "CAPTURE")
    
    def _restore_hidden_windows(self):
        """截图完成后的清理工作（不再需要恢复窗口）
        
        由于不再隐藏窗口，这个方法现在只是一个空操作。
        保留方法签名是为了兼容性。
        """
        # 不再需要恢复窗口
        self._hidden_windows_for_capture = []
    
    def _restore_modal_dialogs(self, dialogs):
        """已废弃 - 不再需要恢复模态对话框
        
        保留方法签名是为了兼容性。
        """
        pass
            
    def start_capture(self):
        """开始截图
        
        实现原理（参考标准截图软件）：
        1. 系统级全局热键 - 优先级高于应用程序的模态循环
        2. 异步屏幕快照 - 直接截取屏幕像素，模态对话框只是像素的一部分
        3. 置顶窗口 - 截图覆盖层设置为 TOPMOST，覆盖在所有窗口上方
        
        不需要隐藏任何窗口，直接截取当前屏幕状态。
        """
        # 开始测量热键响应时间
        # Feature: extreme-performance-optimization
        # Requirements: 2.1
        hotkey_start_time = time.perf_counter()
        
        # 启动保护：程序启动后 3 秒内禁止截图，避免启动时意外触发
        if hasattr(self, '_startup_time'):
            elapsed = time.time() - self._startup_time
            if elapsed < 3.0:
                async_debug_log(f"启动保护：程序启动后 {elapsed:.2f}s，忽略截图请求", "STARTUP")
                if self._hotkey_manager:
                    self._hotkey_manager.set_capturing(False)
                return
        
        if self._error_logger:
            self._error_logger.log_debug("开始截图")
        
        # 记录用户活动，重置内存管理器的空闲计时器
        # Feature: performance-ui-optimization
        # Requirements: 4.3, 4.4
        if self._memory_manager:
            self._memory_manager.record_user_activity()
        
        # 进入截图模式，暂停非必要的 UI 更新
        # Feature: extreme-performance-optimization
        # Requirements: 12.4, 11.9
        screenshot_mode_manager = get_screenshot_mode_manager()
        screenshot_mode_manager.enter_screenshot_mode()
        
        # 准备截图（不再隐藏窗口）
        self._close_blocking_dialogs()
        
        # 设置热键状态为截图中，防止重复触发
        if self._hotkey_manager:
            self._hotkey_manager.set_capturing(True)
        
        # 记录热键响应时间（从热键触发到准备显示覆盖层）
        # Feature: extreme-performance-optimization
        # Requirements: 2.1
        hotkey_response_ms = (time.perf_counter() - hotkey_start_time) * 1000
        PerformanceMonitor.record("hotkey_response", hotkey_response_ms)
        async_debug_log(f"热键响应耗时: {hotkey_response_ms:.2f}ms", "PERF")
        
        # 检查是否超过目标（100ms）
        if hotkey_response_ms > 100:
            async_debug_log(f"警告: 热键响应 {hotkey_response_ms:.2f}ms 超过目标 100ms", "PERF")
        
        # 保存开始时间，用于测量覆盖层显示时间
        self._overlay_show_start_time = time.perf_counter()
        
        # 直接启动截图，不需要延迟
        # 截图覆盖层会通过 TOPMOST 属性覆盖在所有窗口上方
        self._do_start_capture()
    
    def _do_start_capture(self):
        """实际执行截图捕获"""
        try:
            self._overlay.start_capture()
            
            # 截图开始时不打开工作台
            # 工作台在选区完成后才打开（见 _update_live_preview）
            # Feature: workbench-on-selection-complete
            
            # 记录覆盖层显示时间
            # Feature: extreme-performance-optimization
            # Requirements: 2.2
            if hasattr(self, '_overlay_show_start_time'):
                overlay_display_ms = (time.perf_counter() - self._overlay_show_start_time) * 1000
                PerformanceMonitor.record("overlay_display", overlay_display_ms)
                async_debug_log(f"覆盖层显示耗时: {overlay_display_ms:.2f}ms", "PERF")
                
                # 检查是否超过目标（150ms）
                if overlay_display_ms > 150:
                    async_debug_log(f"警告: 覆盖层显示 {overlay_display_ms:.2f}ms 超过目标 150ms", "PERF")
                
                # 清理临时变量
                del self._overlay_show_start_time
                
        except Exception as e:
            # 捕获截图启动异常，避免程序崩溃
            if self._error_logger:
                self._error_logger.log_error(f"截图启动失败: {e}")
            async_debug_log(f"截图启动异常: {e}", "ERROR")
            # 退出截图模式，恢复非必要的 UI 更新
            # Feature: extreme-performance-optimization
            # Requirements: 12.4, 11.9
            screenshot_mode_manager = get_screenshot_mode_manager()
            screenshot_mode_manager.exit_screenshot_mode()
            # 重置热键状态
            if self._hotkey_manager:
                self._hotkey_manager.set_capturing(False)
    
    def _cleanup_ocr_worker(self, timeout_ms: int = 500, force_terminate: bool = False):
        """清理 OCR 工作线程
        
        Args:
            timeout_ms: 等待线程停止的超时时间（毫秒）
            force_terminate: 已废弃，不再使用 terminate()（会导致崩溃）
        
        Note:
            不再使用 terminate()，因为它会导致 OpenVINO 内部状态不一致，
            最终导致程序崩溃。改为使用 requestInterruption() + 等待的方式。
            如果线程未能及时停止，将其移到孤儿线程列表，防止 GC 销毁运行中的 QThread。
        """
        # 先清理已完成的孤儿线程
        self._cleanup_finished_orphan_threads()
        
        if self._ocr_worker is None:
            return
        
        try:
            self._ocr_worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # 请求停止（设置标志位）
        self._ocr_worker.stop()
        # 使用 Qt 的中断机制
        self._ocr_worker.requestInterruption()
        
        if self._ocr_worker.isRunning():
            self._ocr_worker.quit()
            if not self._ocr_worker.wait(timeout_ms):
                # 不再使用 terminate()，因为它会导致崩溃
                # 将线程移到孤儿列表，保持引用防止 GC 销毁运行中的 QThread
                ocr_debug_log(f"OCR线程未能在{timeout_ms}ms内停止，移入孤儿线程列表")
                orphan = self._ocr_worker
                self._ocr_worker = None
                # 连接 finished 信号，线程完成后自动清理
                # 使用默认参数捕获 orphan 的值，避免闭包问题
                try:
                    orphan.finished.connect(lambda t=orphan: self._on_orphan_thread_finished(t))
                except RuntimeError:
                    pass
                self._orphan_threads.append(orphan)
                return
        
        try:
            self._ocr_worker.deleteLater()
        except RuntimeError:
            pass
        self._ocr_worker = None
    
    def _cleanup_finished_orphan_threads(self):
        """清理已完成的孤儿线程"""
        finished = []
        for thread in self._orphan_threads:
            try:
                if not thread.isRunning():
                    finished.append(thread)
            except RuntimeError:
                # 线程对象已被销毁
                finished.append(thread)
        
        for thread in finished:
            try:
                self._orphan_threads.remove(thread)
                thread.deleteLater()
            except (RuntimeError, ValueError):
                pass
        
        if finished:
            ocr_debug_log(f"清理了 {len(finished)} 个已完成的孤儿线程，剩余 {len(self._orphan_threads)} 个")
    
    def _on_orphan_thread_finished(self, thread):
        """孤儿线程完成时的回调"""
        try:
            if thread in self._orphan_threads:
                self._orphan_threads.remove(thread)
                thread.deleteLater()
                ocr_debug_log(f"孤儿线程已完成并清理，剩余 {len(self._orphan_threads)} 个")
        except (RuntimeError, ValueError):
            pass
        
    def _on_screenshot_taken(self, image: QImage):
        """截图完成 - 使用后台线程保存，避免阻塞UI"""
        if self._error_logger:
            self._error_logger.log_debug(f"截图完成，图片尺寸: {image.width()}x{image.height()}")
        
        # 退出实时预览模式（如果有的话）
        # Feature: screenshot-ocr-split-view
        self._exit_live_preview_mode()
        
        # 退出截图模式，恢复非必要的 UI 更新
        # Feature: extreme-performance-optimization
        # Requirements: 12.4, 11.9
        screenshot_mode_manager = get_screenshot_mode_manager()
        screenshot_mode_manager.exit_screenshot_mode()
        
        # 重置热键状态
        if self._hotkey_manager:
            self._hotkey_manager.set_capturing(False)
        
        # 恢复截图前隐藏的窗口
        self._restore_hidden_windows()
        
        # 打开工作台并显示临时预览（截图确认后才弹出）
        # Feature: workbench-temporary-preview-python
        # 截图不自动保存，用户需要在工作台中确认保存
        self._open_workbench_with_temporary_preview(image)
        
        # 清除缓存的识别文字结果（截图已完成，为下次截图做准备）
        self._cached_ocr_results = {}
        self._cached_ocr_image_hash = None
        self._cached_ocr_image = None
        
        # 停止正在运行的OCR线程（不再强制终止，避免崩溃）
        self._cleanup_ocr_worker(timeout_ms=200)
        
        # 清理之前的保存线程
        if self._save_worker is not None:
            try:
                self._save_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            
            if self._save_worker.isRunning():
                self._save_worker.quit()
                if not self._save_worker.wait(500):
                    # 不再使用 terminate()，放弃等待让线程自然结束
                    self._save_worker = None
            
            if self._save_worker is not None:
                try:
                    self._save_worker.deleteLater()
                except RuntimeError:
                    pass
                self._save_worker = None
        
        # 使用后台线程保存截图，避免阻塞UI
        self._save_worker = SaveWorker(self._file_manager, image)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.start()
    
    def _on_save_finished(self, result: SaveResult):
        """保存完成回调"""
        # 清理保存线程
        if self._save_worker is not None:
            try:
                self._save_worker.finished.disconnect(self._on_save_finished)
            except (RuntimeError, TypeError):
                pass
            
            # 线程应该已经完成，但为安全起见检查一下
            if self._save_worker.isRunning():
                self._save_worker.quit()
                if not self._save_worker.wait(200):
                    # 不应该发生，但如果发生了就放弃清理
                    self._save_worker = None
                    return
            
            try:
                self._save_worker.deleteLater()
            except RuntimeError:
                pass
            self._save_worker = None
        
        # 触发内存释放
        # Feature: performance-ui-optimization
        # Requirements: 4.3
        if self._memory_manager:
            self._memory_manager.trigger_gc(force=True)
            async_debug_log("截图保存完成，已触发内存释放", "MEMORY")
        else:
            # 回退到直接 gc.collect()
            gc.collect()
        
        if not self._tray:
            return
        
        # 检查是否开启了截图保存通知
        notification_enabled = self._config_manager.config.notification.screenshot_save
            
        if result.success:
            # 成功通知可以被关闭
            if notification_enabled:
                self._tray.showMessage(
                    "截图完成",
                    f"已保存到: {result.file_path}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        else:
            # 失败通知始终显示，确保用户知道保存失败
            error_msg = result.error if result.error else "未知错误"
            self._tray.showMessage(
                "保存失败",
                error_msg,
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )

    def _on_screenshot_save_requested(self, image: QImage, file_path: str):
        """处理保存到指定文件的请求
        
        Args:
            image: 截图图片
            file_path: 用户选择的目标文件路径
        """
        if self._error_logger:
            self._error_logger.log_debug(
                f"保存到文件请求，图片尺寸: {image.width()}x{image.height()}, "
                f"目标文件: {file_path}"
            )
        
        # 退出截图模式，恢复非必要的 UI 更新
        # Feature: extreme-performance-optimization
        # Requirements: 12.4, 11.9
        screenshot_mode_manager = get_screenshot_mode_manager()
        screenshot_mode_manager.exit_screenshot_mode()
        
        # 重置热键状态
        if self._hotkey_manager:
            self._hotkey_manager.set_capturing(False)
        
        # 清除缓存的识别文字结果
        self._cached_ocr_results = {}
        self._cached_ocr_image_hash = None
        self._cached_ocr_image = None
        
        # 停止正在运行的OCR线程
        self._cleanup_ocr_worker(timeout_ms=200, force_terminate=True)
        
        # 更新配置中的上次保存文件夹（从文件路径提取目录）
        if self._config_manager:
            import os
            folder_path = os.path.dirname(file_path)
            if folder_path:
                self._config_manager.config.last_save_folder = folder_path
                self._config_manager.save()
        
        # 清理之前的保存线程
        if self._save_worker is not None:
            try:
                self._save_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            
            if self._save_worker.isRunning():
                self._save_worker.quit()
                if not self._save_worker.wait(500):
                    # 不再使用 terminate()，放弃等待让线程自然结束
                    self._save_worker = None
            
            if self._save_worker is not None:
                try:
                    self._save_worker.deleteLater()
                except RuntimeError:
                    pass
                self._save_worker = None
        
        # 使用后台线程保存截图到指定文件
        self._save_worker = SaveToFileWorker(self._file_manager, image, file_path)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.start()
            
    def _on_screenshot_cancelled(self):
        """截图取消"""
        async_debug_log("_on_screenshot_cancelled 被调用", "HOTKEY")
        
        # 退出实时预览模式
        # Feature: screenshot-ocr-split-view
        self._exit_live_preview_mode()
        
        # 退出截图模式，恢复非必要的 UI 更新
        # Feature: extreme-performance-optimization
        # Requirements: 12.4, 11.9
        screenshot_mode_manager = get_screenshot_mode_manager()
        screenshot_mode_manager.exit_screenshot_mode()
        
        # 重置热键状态，允许再次触发
        if self._hotkey_manager:
            async_debug_log("重置 _is_capturing 状态为 False", "HOTKEY")
            self._hotkey_manager.set_capturing(False)
        else:
            async_debug_log("警告: _hotkey_manager 为 None", "HOTKEY")
        
        # 停止正在运行的OCR线程（不再强制终止，避免崩溃）
        self._cleanup_ocr_worker(timeout_ms=200)
        
        # 清除缓存的识别文字结果
        self._cached_ocr_results = {}
        self._cached_ocr_image_hash = None
        self._cached_ocr_image = None
        
        # 恢复截图前隐藏的窗口
        self._restore_hidden_windows()
        
        # 触发内存释放
        # Feature: performance-ui-optimization
        # Requirements: 4.3
        if self._memory_manager:
            self._memory_manager.trigger_gc(force=True)
            async_debug_log("截图取消，已触发内存释放", "MEMORY")
        else:
            # 回退到直接 gc.collect()
            gc.collect()
        
        async_debug_log("_on_screenshot_cancelled 完成", "HOTKEY")
    
    def _get_image_hash(self, image: QImage) -> int:
        """计算图片的哈希值，用于判断图片是否变化
        
        使用图片尺寸和多个采样点的像素值计算哈希，
        比只用单个像素更可靠，同时保持计算效率。
        """
        if image.isNull() or image.width() <= 0 or image.height() <= 0:
            return 0
        
        w, h = image.width(), image.height()
        # 采样多个点：四角 + 中心，提高哈希可靠性
        sample_points = [
            (0, 0),                    # 左上
            (w - 1, 0),                # 右上
            (0, h - 1),                # 左下
            (w - 1, h - 1),            # 右下
            (w // 2, h // 2),          # 中心
        ]
        pixels = tuple(image.pixel(x, y) for x, y in sample_points)
        return hash((w, h) + pixels)
    
    def _on_selection_ready(self, image: QImage):
        """选区确定后自动进行后台OCR预处理（仅本地OCR，不消耗在线API）
        
        使用防抖机制，等待选区稳定后再启动 OCR，避免频繁调整选区时卡死。
        无论 OCR 开关是否开启，都会在后台运行 OCR 预处理。
        """
        ocr_debug_log("选区变化，启动防抖定时器")
        
        # 保存待处理的图片
        self._pending_background_ocr_image = image.copy()
        
        # 更新实时预览（如果历史窗口处于实时预览模式）
        # Feature: screenshot-ocr-split-view
        self._update_live_preview(image)
        
        # 重置防抖定时器
        if self._background_ocr_debounce_timer.isActive():
            self._background_ocr_debounce_timer.stop()
        
        self._background_ocr_debounce_timer.start(self._BACKGROUND_OCR_DEBOUNCE_MS)
    
    def _on_background_ocr_debounce_timeout(self):
        """后台 OCR 防抖定时器超时回调 - 实际执行 OCR"""
        image = self._pending_background_ocr_image
        self._pending_background_ocr_image = None
        
        if image is None or image.isNull():
            ocr_debug_log("防抖超时但图片为空，跳过")
            return
        
        ocr_debug_log("=" * 50)
        ocr_debug_log("防抖超时，开始后台OCR预处理")
        
        # 计算图片哈希
        image_hash = self._get_image_hash(image)
        
        # 如果图片没变化且已有缓存结果，跳过
        if self._cached_ocr_image_hash == image_hash and self._cached_ocr_results:
            ocr_debug_log("图片未变化，使用缓存结果")
            return
        
        # 清除旧的缓存，保存当前图片用于后续百度OCR
        self._cached_ocr_results = {}
        self._cached_ocr_image_hash = image_hash
        self._cached_ocr_image = image.copy()  # 保存图片副本
        
        # 如果已有OCR任务在运行，先停止
        if self._ocr_worker is not None:
            ocr_debug_log("停止之前的OCR任务")
            self._cleanup_ocr_worker(timeout_ms=1000, force_terminate=True)
        
        ocr_debug_log(f"图片尺寸: {image.width()}x{image.height()}")
        ocr_debug_log("启动后台OCR预处理线程（仅本地OCR，不消耗在线API）...")
        
        # 记录 OCR 活动，重置 OCR 空闲计时器
        # Feature: performance-ui-optimization
        # Requirements: 4.3
        if self._memory_manager:
            self._memory_manager.record_ocr_activity()
        
        # 创建并启动后台线程，预处理模式（只运行本地OCR）
        self._ocr_worker = OCRWorker(self._ocr_manager, image, mode="preprocess")
        self._ocr_worker.finished.connect(self._on_background_ocr_finished)
        self._ocr_worker.start()
    
    def _on_background_ocr_finished(self, result):
        """后台OCR完成回调 - 缓存结果并通知 AutoOCRPopupManager"""
        # 后台 OCR 完成，恢复识字按钮状态
        if self._overlay:
            self._overlay.set_ocr_loading(False)
        
        from screenshot_tool.services.ocr_manager import UnifiedOCRResult
        if isinstance(result, UnifiedOCRResult):
            ocr_debug_log(f"后台OCR完成: success={result.success}, engine={result.engine}, 文本长度={len(result.text) if result.text else 0}")
            if result.engine:
                self._cached_ocr_results[result.engine] = result
            
            # 将缓存结果传递给 AutoOCRPopupManager，以便复用
            if self._auto_ocr_popup_manager and self._cached_ocr_image_hash:
                self._auto_ocr_popup_manager.set_cached_ocr_result(result, self._cached_ocr_image_hash)
        
        # 清理OCR工作线程
        if self._ocr_worker:
            try:
                self._ocr_worker.finished.disconnect(self._on_background_ocr_finished)
            except (RuntimeError, TypeError):
                pass
            
            # 线程应该已完成，但为安全起见检查
            if self._ocr_worker.isRunning():
                self._ocr_worker.quit()
                if not self._ocr_worker.wait(200):
                    self._ocr_worker = None
                    return
            
            try:
                self._ocr_worker.deleteLater()
            except RuntimeError:
                pass
            self._ocr_worker = None
        
    def _on_ocr_finished(self, result):
        """OCR完成回调 - 在主线程执行（用于后台预处理）"""
        from screenshot_tool.services.ocr_manager import UnifiedOCRResult
        # 空值检查
        if result is None:
            ocr_debug_log("OCR返回结果为空")
            return
        
        ocr_debug_log(f"OCR返回: success={result.success}, engine={result.engine}, error={result.error}")
        ocr_debug_log(f"识别文本长度: {len(result.text) if result.text else 0}")
        
        # 缓存结果
        if isinstance(result, UnifiedOCRResult) and result.engine:
            self._cached_ocr_results[result.engine] = result
        
        # 清理OCR工作线程
        if self._ocr_worker:
            try:
                self._ocr_worker.finished.disconnect(self._on_ocr_finished)
            except (RuntimeError, TypeError):
                pass
            
            # 线程应该已完成，但为安全起见检查
            if self._ocr_worker.isRunning():
                self._ocr_worker.quit()
                if not self._ocr_worker.wait(200):
                    self._ocr_worker = None
                    return
            
            try:
                self._ocr_worker.deleteLater()
            except RuntimeError:
                pass
            self._ocr_worker = None
    
    def _on_anki_requested(self, image: QImage, marker_rects: list, highlight_color: str, pre_recognized_words: list = None):
        """Anki制卡请求 - 打开 Anki 制卡窗口（使用截图覆盖层中绘制的高亮区域）"""
        ocr_debug_log("=" * 50)
        ocr_debug_log(f"收到Anki制卡请求，高亮区域数: {len(marker_rects)}, 预识别单词数: {len(pre_recognized_words) if pre_recognized_words else 0}")
        
        # 检查功能权限
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import Feature
            
            # 先检查权限
            if self._subscription_manager and self._subscription_manager.is_initialized:
                result = self._subscription_manager.check_access(Feature.ANKI)
                if not result.allowed:
                    # 权限不足，先关闭截图覆盖层再显示升级提示
                    async_debug_log("Anki 制卡功能权限不足，显示升级提示", "ANKI")
                    if self._overlay:
                        self._overlay.cancel()
                    
                    # 获取使用量信息
                    usage_info = None
                    status = self._subscription_manager.get_feature_status(Feature.ANKI)
                    if status.get("is_limited"):
                        usage_info = {
                            "usage": status.get("usage", 0),
                            "limit": status.get("limit", 0),
                            "remaining": status.get("remaining", 0),
                        }
                    
                    self._show_upgrade_prompt("Anki 制卡", result.reason, usage_info)
                    return
        except ImportError:
            pass  # 订阅模块未安装，允许使用
        except Exception as e:
            async_debug_log(f"Anki 权限检查异常: {e}", "ANKI")
            # 权限检查失败时允许使用，避免阻塞用户
        
        try:
            # 导入 Anki 制卡窗口
            from screenshot_tool.ui.anki_card_window import AnkiCardWindow
            from screenshot_tool.core.anki_debug_logger import (
                clear_anki_debug_log, anki_debug_log as anki_log, anki_debug_exception
            )
            
            # 清空之前的调试日志
            clear_anki_debug_log()
            anki_log("_on_anki_requested: 开始处理 Anki 请求")
            anki_log(f"_on_anki_requested: 预识别单词: {pre_recognized_words}")
            
            # 创建或显示 Anki 制卡窗口
            anki_log(f"_on_anki_requested: 当前窗口={self._anki_window}, 类型={type(self._anki_window)}")
            if self._anki_window is None or not isinstance(self._anki_window, AnkiCardWindow):
                # 关闭旧窗口（如果存在）
                if self._anki_window is not None:
                    anki_log("_on_anki_requested: 关闭旧窗口")
                    self._anki_window.close()
                anki_log("_on_anki_requested: 创建新的 AnkiCardWindow")
                self._anki_window = AnkiCardWindow()
                anki_log("_on_anki_requested: 连接 windowClosed 信号")
                self._anki_window.windowClosed.connect(self._on_anki_window_closed)
            
            # 设置数据（包含预识别单词）
            image_valid = image is not None and not image.isNull()
            anki_log(f"_on_anki_requested: 设置数据, image_valid={image_valid}, marker_rects={len(marker_rects)}")
            self._anki_window.set_data(
                image, 
                marker_rects, 
                self._ocr_manager, 
                highlight_color,
                pre_recognized_words
            )
            
            # 隐藏截图覆盖层和工具栏，让 Anki 窗口显示在最上层
            anki_log("_on_anki_requested: 隐藏截图覆盖层")
            if self._overlay:
                self._overlay._close()
            
            # 显示 Anki 窗口
            anki_log("_on_anki_requested: 显示 Anki 窗口")
            self._anki_window.show()
            self._anki_window.raise_()
            self._anki_window.activateWindow()
            anki_log("_on_anki_requested: 完成")
        except (ImportError, AttributeError, RuntimeError) as e:
            ocr_debug_log(f"Anki请求处理异常: {e}")
            import traceback
            ocr_debug_log(traceback.format_exc())
            # 尝试写入 Anki 调试日志
            try:
                from screenshot_tool.core.anki_debug_logger import (
                    anki_debug_log as anki_log, anki_debug_exception
                )
                anki_log(f"_on_anki_requested 异常: {e}")
                anki_debug_exception("ANKI-REQUEST")
            except (ImportError, OSError):
                pass  # 日志失败不影响主程序
    
    def _on_anki_window_closed(self):
        """Anki 窗口关闭后恢复截图覆盖层"""
        ocr_debug_log("Anki窗口关闭，恢复截图覆盖层")
        if self._overlay:
            self._overlay.restore()
            self._overlay.raise_()
            self._overlay.activateWindow()

    # ==================== 录屏相关方法 ====================

    def _init_screen_recorder(self):
        """延迟初始化录屏组件"""
        if self._screen_recorder is not None:
            return

        try:
            from screenshot_tool.services.screen_recorder import ScreenRecorder
            from screenshot_tool.ui.recording_overlay import RecordingOverlayManager

            # 传递录屏配置，确保使用用户设置的保存路径
            self._screen_recorder = ScreenRecorder(config=self._config_manager.config.recording)
            self._screen_recorder.state_changed.connect(self._on_recording_state_changed)
            self._screen_recorder.progress_updated.connect(self._on_recording_progress)
            self._screen_recorder.recording_finished.connect(self._on_recording_finished)

            self._recording_overlay_manager = RecordingOverlayManager()
            self._recording_overlay_manager.pause_requested.connect(self._on_recording_pause_requested)
            self._recording_overlay_manager.resume_requested.connect(self._on_recording_resume_requested)
            self._recording_overlay_manager.stop_requested.connect(self._on_recording_stop_requested)

            async_debug_log("录屏组件初始化完成", "RECORDING")
        except ImportError as e:
            async_debug_log(f"录屏组件导入失败: {e}", "RECORDING")
            self._screen_recorder = None
            self._recording_overlay_manager = None

    def _on_recording_requested(self, region: QRect):
        """录屏请求 - 开始录制指定区域
        
        Args:
            region: 录制区域（物理像素坐标），如果为 None 则启动截图覆盖层让用户选择区域
        """
        # 如果没有指定区域，启动截图覆盖层让用户选择
        if region is None:
            async_debug_log("录屏请求未指定区域，启动截图覆盖层选择区域", "RECORDING")
            # 启动截图覆盖层，用户选择区域后会通过 recordingRequested 信号回调
            self.start_capture()
            return
        
        async_debug_log(f"收到录屏请求，区域: ({region.x()}, {region.y()}, {region.width()}x{region.height()})", "RECORDING")

        # 检查功能权限
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import Feature
            
            # 先检查权限（不显示对话框）
            if self._subscription_manager and self._subscription_manager.is_initialized:
                result = self._subscription_manager.check_access(Feature.SCREEN_RECORDER)
                if not result.allowed:
                    # 权限不足，先关闭截图覆盖层再显示升级提示
                    async_debug_log("录屏功能权限不足，显示升级提示", "RECORDING")
                    if self._overlay:
                        self._overlay.cancel()
                    
                    # 获取使用量信息
                    usage_info = None
                    status = self._subscription_manager.get_feature_status(Feature.SCREEN_RECORDER)
                    if status.get("is_limited"):
                        usage_info = {
                            "usage": status.get("usage", 0),
                            "limit": status.get("limit", 0),
                            "remaining": status.get("remaining", 0),
                        }
                    
                    self._show_upgrade_prompt("录屏", result.reason, usage_info)
                    return
        except ImportError:
            pass  # 订阅模块未安装，允许使用
        except Exception as e:
            async_debug_log(f"录屏权限检查异常: {e}", "RECORDING")
            # 权限检查失败时允许使用，避免阻塞用户

        # 验证录制区域
        if region.width() < 10 or region.height() < 10:
            async_debug_log("录制区域太小，忽略请求", "RECORDING")
            if self._tray:
                self._tray.showMessage(
                    "录屏失败",
                    "录制区域太小，请选择更大的区域",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            return

        # 初始化录屏组件（延迟加载）
        self._init_screen_recorder()

        if self._screen_recorder is None:
            if self._tray:
                self._tray.showMessage(
                    "录屏失败",
                    "录屏组件初始化失败，请检查依赖是否安装",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            return

        # 检查依赖
        available, error = self._screen_recorder.check_dependencies()
        if not available:
            async_debug_log(f"录屏依赖检查失败: {error}", "RECORDING")
            if self._tray:
                self._tray.showMessage(
                    "录屏失败",
                    error,
                    QSystemTrayIcon.MessageIcon.Warning,
                    5000
                )
            return

        # 如果正在录制，忽略请求
        if self._is_recording:
            async_debug_log("已在录制中，忽略请求", "RECORDING")
            return

        # 关闭截图覆盖层
        if self._overlay:
            self._overlay.cancel()

        # 转换区域为元组 (left, top, right, bottom) - 物理像素坐标给录屏器
        recording_region = (
            region.x(),
            region.y(),
            region.x() + region.width(),
            region.y() + region.height()
        )

        # 开始录制
        self._is_recording = True
        success = self._screen_recorder.start_recording(region=recording_region)

        if success:
            async_debug_log("录制已启动", "RECORDING")
            # 显示录制覆盖层 - 需要转换为逻辑坐标
            if self._recording_overlay_manager:
                # 获取设备像素比
                from PySide6.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                dpr = screen.devicePixelRatio() if screen else 1.0
                
                # 将物理像素坐标转换为逻辑坐标（Qt 窗口使用逻辑坐标）
                logical_region = QRect(
                    int(region.x() / dpr),
                    int(region.y() / dpr),
                    int(region.width() / dpr),
                    int(region.height() / dpr)
                )
                async_debug_log(f"边框逻辑坐标: ({logical_region.x()}, {logical_region.y()}, {logical_region.width()}x{logical_region.height()})", "RECORDING")
                self._recording_overlay_manager.start(logical_region)
        else:
            self._is_recording = False
            async_debug_log("录制启动失败", "RECORDING")
            if self._tray:
                self._tray.showMessage(
                    "录屏失败",
                    "无法启动录制",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )

    def _on_recording_state_changed(self, state):
        """录制状态变化"""
        from screenshot_tool.services.screen_recorder import RecordingState
        async_debug_log(f"录制状态变化: {state}", "RECORDING")

        if state == RecordingState.PAUSED:
            if self._recording_overlay_manager:
                self._recording_overlay_manager.set_paused(True)
        elif state == RecordingState.RECORDING:
            if self._recording_overlay_manager:
                self._recording_overlay_manager.set_paused(False)

    def _on_recording_progress(self, frames: int, duration: float):
        """录制进度更新"""
        if self._recording_overlay_manager:
            self._recording_overlay_manager.update_time(duration)

    def _on_recording_pause_requested(self):
        """暂停录制请求"""
        if self._screen_recorder:
            self._screen_recorder.pause_recording()
            async_debug_log("录制已暂停", "RECORDING")

    def _on_recording_resume_requested(self):
        """继续录制请求"""
        if self._screen_recorder:
            self._screen_recorder.resume_recording()
            async_debug_log("录制已继续", "RECORDING")

    def _on_recording_stop_requested(self):
        """停止录制请求"""
        if self._screen_recorder:
            self._screen_recorder.stop_recording()
            async_debug_log("正在停止录制...", "RECORDING")

    def _on_recording_finished(self, result):
        """录制完成"""
        self._is_recording = False

        # 隐藏录制覆盖层
        if self._recording_overlay_manager:
            self._recording_overlay_manager.stop()

        async_debug_log(f"录制完成: success={result.success}, path={result.file_path}", "RECORDING")

        if result.success:
            # 显示预览对话框
            try:
                from screenshot_tool.ui.recording_preview import show_recording_preview
                show_recording_preview(
                    file_path=result.file_path,
                    duration=result.duration_seconds,
                    file_size=result.file_size_bytes
                )
            except ImportError as e:
                async_debug_log(f"预览对话框导入失败: {e}", "RECORDING")
                # 回退：显示托盘通知
                if self._tray:
                    size_mb = result.file_size_bytes / 1024 / 1024
                    self._tray.showMessage(
                        "录屏完成",
                        f"已保存到: {result.file_path}\n时长: {result.duration_seconds:.1f}秒, 大小: {size_mb:.1f}MB",
                        QSystemTrayIcon.MessageIcon.Information,
                        5000
                    )
        else:
            # 录制失败
            if self._tray:
                self._tray.showMessage(
                    "录屏失败",
                    result.error,
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )

    
    def _on_draw_color_changed(self, color_hex: str):
        """绘制颜色改变 - 保存到配置（兼容旧逻辑）"""
        if not color_hex:
            return
        try:
            self._config_manager.set_draw_color(color_hex)
            self._config_manager.save()
        except OSError:
            # 保存失败不影响使用
            pass
    
    def _on_tool_color_changed(self, tool_name: str, color_hex: str):
        """工具颜色改变 - 保存到配置"""
        if not tool_name or not color_hex:
            return
        try:
            self._config_manager.set_tool_color(tool_name, color_hex)
            self._config_manager.save()
        except OSError:
            # 保存失败不影响使用
            pass
    
    def _on_tool_width_changed(self, tool_name: str, width: int):
        """工具粗细改变 - 保存到配置"""
        if not tool_name or width is None:
            return
        try:
            self._config_manager.set_tool_width(tool_name, width)
            self._config_manager.save()
        except OSError:
            # 保存失败不影响使用
            pass
            
    def _on_pin_requested(self, image: QImage, rect: QRect):
        """钉住请求 - 创建贴图窗口"""
        if image.isNull():
            # 失败通知始终显示
            if self._tray:
                self._tray.showMessage(
                    "钉住失败",
                    "图片为空",
                    QSystemTrayIcon.MessageIcon.Warning,
                    2000
                )
            return
        
        # 安全检查：确保 overlay 仍然有效
        if not self._overlay or not self._overlay.isVisible():
            # overlay 已关闭，使用 rect 的原始坐标作为位置
            global_pos = rect.topLeft()
        else:
            # 计算贴图窗口位置（使用选区的全局坐标）
            global_pos = self._overlay.mapToGlobal(rect.topLeft())
        
        # 创建贴图窗口
        self._get_ding_manager().create_ding(image, global_pos)
        
        # 成功通知可以被关闭
        if self._tray and self._config_manager.config.notification.ding:
            count = self._get_ding_manager().get_window_count()
            self._tray.showMessage(
                "已钉住",
                f"当前有 {count} 个贴图窗口",
                QSystemTrayIcon.MessageIcon.Information,
                1500
            )
        
    def _open_settings(self):
        """打开设置
        
        使用非模态方式打开设置对话框，允许在设置界面打开时截图。
        截图覆盖层使用 WindowStaysOnTopHint，会显示在设置对话框之上。
        """
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        # 如果已有设置对话框打开，激活它
        if hasattr(self, '_settings_dialog') and self._settings_dialog is not None:
            try:
                if self._settings_dialog.isVisible():
                    self._settings_dialog.activateWindow()
                    self._settings_dialog.raise_()
                    return
            except RuntimeError:
                # 对话框已被删除
                self._settings_dialog = None
        
        # 创建非模态设置对话框
        self._settings_dialog = SettingsDialog(
            self._config_manager.config,
            update_service=self._update_service,
            download_state_manager=self._download_state_manager,
            subscription_manager=self._subscription_manager
        )
        self._settings_dialog.settingsSaved.connect(self._on_settings_saved)
        self._settings_dialog.hotkeyChanged.connect(self._on_hotkey_changed)
        
        # 连接强制锁定变更信号
        # Feature: hotkey-force-lock
        # Requirements: 4.3, 7.2
        self._settings_dialog.forceLockChanged.connect(self._on_force_lock_changed)
        
        # 连接登录/登出信号
        self._settings_dialog.loginSuccess.connect(self._on_login_success)
        self._settings_dialog.logoutSuccess.connect(self._on_logout_success)
        
        # 对话框关闭时清理引用
        self._settings_dialog.finished.connect(self._on_settings_dialog_closed)
        
        # 设置 WA_DeleteOnClose 属性，确保关闭时自动删除
        from PySide6.QtCore import Qt
        self._settings_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        # 非模态显示
        self._settings_dialog.show()
        self._settings_dialog.activateWindow()
    
    def _on_logout_success(self):
        """登出成功回调
        
        Feature: subscription-system
        """
        async_debug_log("用户已登出", "SUBSCRIPTION")
        
        # 刷新托盘菜单
        self._setup_tray()
        
        if self._tray:
            self._tray.showMessage(
                "已退出登录",
                "您已成功退出登录",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _on_settings_dialog_closed(self):
        """设置对话框关闭时的清理"""
        if self._settings_dialog is not None:
            try:
                # 断开信号连接，防止悬空引用
                self._settings_dialog.settingsSaved.disconnect(self._on_settings_saved)
                self._settings_dialog.hotkeyChanged.disconnect(self._on_hotkey_changed)
                self._settings_dialog.forceLockChanged.disconnect(self._on_force_lock_changed)
                self._settings_dialog.loginSuccess.disconnect(self._on_login_success)
                self._settings_dialog.logoutSuccess.disconnect(self._on_logout_success)
            except (RuntimeError, TypeError):
                # 信号可能已经断开或对象已被删除
                pass
            
            try:
                # 调用对话框的清理方法（断开下载状态管理器信号）
                self._settings_dialog.cleanup()
            except (RuntimeError, AttributeError):
                pass
            
            try:
                # 显式删除对话框
                self._settings_dialog.deleteLater()
            except RuntimeError:
                pass
            
        self._settings_dialog = None
        
    def _on_settings_saved(self, config):
        """设置保存"""
        self._config_manager.set_config(config)
        self._config_manager.save()
        
        # 更新服务
        self._file_manager = FileManager(config.save_path)
        
        # 重新初始化OCR管理器（使用新的API密钥和优先级）
        self._init_ocr_manager()
        
        # 重新初始化公文模式（快捷键可能已更改）
        self._init_gongwen_mode()
        
        # 重新初始化 Markdown 模式（快捷键可能已更改）
        self._init_markdown_mode()
        
        # 更新鼠标高亮配置（热更新，不重启）
        # Feature: mouse-highlight
        # Requirements: 9.7
        if self._mouse_highlight_manager:
            self._mouse_highlight_manager.update_config()
        
        # 更新扩展快捷键
        # Feature: extended-hotkeys
        self._update_extended_hotkeys()
        
        # 刷新托盘菜单（更新快捷键显示）
        self._setup_tray()
        
        # 同步开机自启动状态
        self._sync_autostart()
    
    def _init_ocr_manager(self):
        """初始化或重新初始化OCR管理器
        
        默认使用 RapidOCR（本地引擎），用户可通过OCR面板按钮手动切换到云端OCR。
        云OCR配置优先使用配置文件中的密钥，如果没有则使用环境变量。
        """
        # 延迟导入以加速 EXE 启动
        from screenshot_tool.services.ocr_manager import OCRManager
        
        config = self._config_manager.config
        
        # 腾讯云OCR配置
        tencent_secret_id = config.ocr.tencent_secret_id or os.environ.get("TENCENT_OCR_SECRET_ID", "")
        tencent_secret_key = config.ocr.tencent_secret_key or os.environ.get("TENCENT_OCR_SECRET_KEY", "")
        
        # 百度云OCR配置
        baidu_api_key = config.ocr.baidu_api_key or os.environ.get("BAIDU_OCR_API_KEY", "")
        baidu_secret_key = config.ocr.baidu_secret_key or os.environ.get("BAIDU_OCR_SECRET_KEY", "")
        
        # 预处理配置（从配置文件加载）
        from screenshot_tool.services.image_preprocessor import PreprocessingConfig
        preprocessing_config = PreprocessingConfig.from_dict(config.preprocessing)
        
        self._ocr_manager = OCRManager(
            baidu_api_key=baidu_api_key,
            baidu_secret_key=baidu_secret_key,
            tencent_secret_id=tencent_secret_id,
            tencent_secret_key=tencent_secret_key,
            preprocessing_config=preprocessing_config
        )
        
        # 更新自动OCR弹窗管理器的OCR管理器引用
        if hasattr(self, '_auto_ocr_popup_manager') and self._auto_ocr_popup_manager:
            self._auto_ocr_popup_manager._ocr_manager = self._ocr_manager
    
    def _get_ding_manager(self):
        """获取贴图管理器（延迟加载）
        
        Feature: performance-ui-optimization
        Requirements: 1.3, 1.4
        
        使用 LazyLoaderManager 延迟加载 DingManager，
        仅在用户首次使用贴图功能时才加载模块。
        
        Returns:
            DingManager 实例
        """
        if self._ding_manager is None:
            from screenshot_tool.core.lazy_loader import LazyLoaderManager
            self._ding_manager = LazyLoaderManager.instance().get("ding_manager")
        return self._ding_manager
    
    def _sync_autostart(self):
        """同步开机自启动状态"""
        try:
            from screenshot_tool.core.autostart_manager import get_autostart_manager
            autostart_manager = get_autostart_manager()
            # 先同步路径（如果 exe 位置变化，更新注册表）
            if autostart_manager.sync_path_if_needed():
                print("[Info] 检测到程序位置变化，已更新开机自启动路径")
            # 再同步启用状态
            autostart_manager.sync_with_config(self._config_manager.get_auto_start())
        except (ImportError, OSError, PermissionError) as e:
            print(f"[Warning] 同步开机自启动失败: {e}")
    
    def _init_gongwen_mode(self):
        """初始化公文格式化模式
        
        创建公文模式管理器（不再使用全局热键，通过托盘菜单访问）。
        """
        # 清理旧的公文模式管理器
        if self._gongwen_mode_manager:
            self._gongwen_mode_manager.cleanup()
            self._gongwen_mode_manager = None
        
        try:
            # 创建公文模式管理器
            from screenshot_tool.core.gongwen_mode_manager import GongwenModeManager
            self._gongwen_mode_manager = GongwenModeManager()
            self._gongwen_mode_manager.format_triggered.connect(self._on_gongwen_format_triggered)
            self._gongwen_mode_manager.warning_message.connect(self._on_gongwen_warning)
            
        except (ImportError, AttributeError, RuntimeError) as e:
            print(f"[Warning] 初始化公文模式失败: {e}")
            self._gongwen_mode_manager = None
    
    def _toggle_gongwen_mode(self):
        """切换公文格式化模式"""
        if self._gongwen_mode_manager:
            self._gongwen_mode_manager.toggle()
    
    def _on_auto_ocr_completed(self, text: str):
        """自动 OCR 完成回调 - 保存最近的 OCR 结果
        
        当 AutoOCRPopupManager 完成 OCR 识别时调用，
        保存结果用于托盘菜单"OCR面板"功能。
        """
        try:
            # 保存最近的 OCR 结果
            if not self._auto_ocr_popup_manager:
                return
            
            # 安全获取当前窗口（通过 has_active_window 检查）
            if not self._auto_ocr_popup_manager.has_active_window():
                return
            
            window = self._auto_ocr_popup_manager._current_window
            if window is None:
                return
            
            # 保存图片（深拷贝避免引用问题）
            if hasattr(window, '_current_image') and window._current_image is not None:
                try:
                    self._last_ocr_image = window._current_image.copy()
                except RuntimeError:
                    pass  # 窗口可能已被销毁
            
            # 保存 OCR 结果
            if hasattr(window, '_ocr_cache') and window._ocr_cache:
                engine = getattr(window, '_current_engine', 'rapid') or 'rapid'
                if engine in window._ocr_cache:
                    self._last_ocr_result = window._ocr_cache[engine]
        except (RuntimeError, AttributeError):
            # 窗口可能已被销毁，忽略错误
            pass
    
    def _show_split_window(self, image: QImage, annotations: list = None):
        """显示分屏窗口（截图+OCR）
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
        
        Args:
            image: 截图图像
            annotations: 标注列表
        """
        from screenshot_tool.ui.screenshot_ocr_split_window import ScreenshotOCRSplitWindow
        
        # 检查是否需要关闭现有窗口（非置顶状态）
        if self._split_window is not None:
            try:
                if not self._split_window.is_pinned:
                    self._split_window.close()
                    self._split_window = None
            except RuntimeError:
                # 窗口已被销毁
                self._split_window = None
        
        # 创建新窗口（如果需要）
        if self._split_window is None:
            self._split_window = ScreenshotOCRSplitWindow()
            self._split_window.closed.connect(self._on_split_window_closed)
            
            # 连接剪贴板历史集成信号
            # Feature: screenshot-ocr-split-view
            # Requirements: 7.4, 7.5
            self._split_window.image_copied.connect(self._on_split_window_image_copied)
            self._split_window.image_saved.connect(self._on_split_window_image_saved)
        
        # 显示截图并开始 OCR
        self._split_window.show_screenshot(image, annotations, self._ocr_manager)
    
    def _on_split_window_closed(self):
        """分屏窗口关闭回调
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.3
        """
        # 注意：不要在这里将 _split_window 设为 None
        # 因为窗口可能只是被隐藏而不是销毁
        # 只有在窗口被销毁时才清理引用
        pass
    
    def _on_clipboard_history_ocr_requested(self, image: QImage, annotations: list = None):
        """处理工作台窗口 OCR 请求（手动点击识字按钮或截图后自动触发）
        
        Feature: clipboard-ocr-merge, workbench-temporary-preview-python
        
        打开工作台窗口并触发 OCR：
        1. 确保工作台窗口存在
        2. 进入实时预览模式
        3. 显示图片并自动触发 OCR
        
        Args:
            image: 截图图像
            annotations: 标注列表（暂未使用）
        """
        if image is None or image.isNull():
            return
        
        try:
            # 确保工作台窗口存在
            if self._clipboard_history_window is None:
                if self._clipboard_history_manager is None:
                    async_debug_log("剪贴板管理器未初始化，无法创建工作台窗口", "CLIPBOARD-OCR")
                    return
                
                from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
                self._clipboard_history_window = ClipboardHistoryWindow(
                    self._clipboard_history_manager,
                    skip_initial_refresh=True
                )
                self._clipboard_history_window.edit_screenshot_requested.connect(
                    self._edit_screenshot_from_history
                )
                self._clipboard_history_window.ding_screenshot_requested.connect(
                    self._ding_from_history
                )
                async_debug_log("创建新的工作台窗口", "CLIPBOARD-OCR")
            
            # 确保 OCR 管理器已设置
            if self._ocr_manager is not None:
                self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
            
            # 进入实时预览模式并显示图片，自动触发 OCR
            self._clipboard_history_window.enter_live_preview_mode()
            self._clipboard_history_window.show_live_preview(image)
            
            async_debug_log("工作台 OCR 请求：已打开工作台并触发 OCR", "CLIPBOARD-OCR")
                
        except RuntimeError:
            # 窗口已被销毁
            self._clipboard_history_window = None
            async_debug_log("工作台窗口已被销毁", "CLIPBOARD-OCR")
        except Exception as e:
            import traceback
            async_debug_log(f"处理工作台 OCR 请求失败: {e}", "CLIPBOARD-OCR")
            traceback.print_exc()
            # 出错时仍尝试打开工作台窗口
            self._open_clipboard_history()

    def _on_split_window_image_copied(self, image: QImage):
        """分屏窗口图片复制回调 - 添加到剪贴板历史
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        
        Args:
            image: 复制的图片
        """
        if self._clipboard_history_manager is None:
            return
        
        if image is None or image.isNull():
            return
        
        try:
            # 临时禁用剪贴板监听，避免重复记录
            # 因为复制到剪贴板会触发 clipboard_history_manager 的监听
            self._clipboard_history_manager._skip_next_change = True
            
            # 添加到剪贴板历史
            # 使用 add_screenshot_item 方法，支持标注数据
            annotations = None
            if self._split_window is not None:
                annotations = self._split_window._annotations
            
            self._clipboard_history_manager.add_screenshot_item(
                image=image,
                annotations=annotations,
            )
            
            async_debug_log("分屏窗口图片已添加到剪贴板历史", "SPLIT-WINDOW")
            
        except Exception as e:
            async_debug_log(f"添加图片到剪贴板历史失败: {e}", "SPLIT-WINDOW")
        finally:
            # 延迟恢复监听，确保剪贴板操作完成
            QTimer.singleShot(100, self._restore_clipboard_monitoring)
    
    def _on_split_window_image_saved(self, image: QImage, file_path: str):
        """分屏窗口图片保存回调 - 添加到剪贴板历史
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        
        Args:
            image: 保存的图片
            file_path: 保存路径
        """
        if self._clipboard_history_manager is None:
            return
        
        if image is None or image.isNull():
            return
        
        try:
            # 添加到剪贴板历史
            # 使用 add_screenshot_item 方法，支持标注数据
            annotations = None
            if self._split_window is not None:
                annotations = self._split_window._annotations
            
            self._clipboard_history_manager.add_screenshot_item(
                image=image,
                annotations=annotations,
            )
            
            async_debug_log(f"分屏窗口保存的图片已添加到剪贴板历史: {file_path}", "SPLIT-WINDOW")
            
        except Exception as e:
            async_debug_log(f"添加保存图片到剪贴板历史失败: {e}", "SPLIT-WINDOW")
    
    def _restore_clipboard_monitoring(self):
        """恢复剪贴板监听
        
        Feature: screenshot-ocr-split-view
        Requirements: 7.4, 7.5
        """
        if self._clipboard_history_manager is not None:
            self._clipboard_history_manager._skip_next_change = False
    
    def _toggle_ocr_panel(self):
        """切换 OCR 面板显示/最小化 - 改为切换工作台窗口
        
        Feature: clipboard-ocr-merge
        Requirements: 7.3
        
        OCR 功能已集成到工作台窗口中，此方法现在切换工作台窗口
        按一次快捷键打开，再按一次最小化
        """
        self._toggle_clipboard_history()
    
    def _open_ocr_panel(self):
        """打开 OCR 面板 - 改为打开工作台窗口
        
        Feature: clipboard-ocr-merge
        Requirements: 7.1, 7.3
        
        OCR 功能已集成到工作台窗口中，此方法现在打开工作台窗口。
        从托盘菜单和极简工具栏调用。
        """
        async_debug_log("OCR面板请求 -> 打开工作台窗口", "EXTENDED-HOTKEYS")
        self._open_clipboard_history()

    def _open_regulation_search(self):
        """打开规章查询窗口
        
        Feature: caac-regulation-search
        Requirements: 1.1, 1.2, 8.2, 8.3
        """
        async_debug_log("_open_regulation_search 被调用", "REGULATION")
        # 检查功能权限
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import Feature
            if not self._check_feature_access("规章查询", Feature.CAAC):
                async_debug_log("规章查询权限检查未通过", "REGULATION")
                return
            async_debug_log("规章查询权限检查通过", "REGULATION")
        except ImportError:
            async_debug_log("订阅模块未安装，允许使用", "REGULATION")
            pass  # 订阅模块未安装，允许使用
        
        try:
            # 延迟导入
            from .ui.regulation_search_window import RegulationSearchWindow
            async_debug_log("RegulationSearchWindow 模块导入成功", "REGULATION")
            
            # 使用单例模式显示窗口
            window = RegulationSearchWindow.show_and_activate(self._config_manager)
            async_debug_log(f"RegulationSearchWindow 创建成功: {window}, visible={window.isVisible()}", "REGULATION")
            
            # 连接下载通知信号（使用 blockSignals 避免重复连接警告）
            # 检查是否已经连接过（通过属性标记）
            if not getattr(window, '_signals_connected', False):
                window.downloadCompleted.connect(self._on_regulation_download_complete)
                window.downloadFailed.connect(self._on_regulation_download_failed)
                window._signals_connected = True
                async_debug_log("信号连接完成", "REGULATION")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[规章查询] 打开失败: {e}")
            async_debug_log(f"打开规章查询失败: {e}\n{error_detail}", "REGULATION")
            traceback.print_exc()
            
            if self._tray:
                self._tray.showMessage(
                    "规章查询",
                    f"打开失败: {e}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
    
    def _on_regulation_download_complete(self, file_path: str):
        """规章 PDF 下载完成通知
        
        Feature: caac-regulation-search
        Requirements: 5.8, 8.3
        """
        if self._tray and self._config_manager.config.notification.regulation:
            # 截断过长的路径
            display_path = file_path
            if len(display_path) > 60:
                display_path = "..." + display_path[-57:]
            
            self._tray.showMessage(
                "📜 规章下载完成",
                f"已保存到:\n{display_path}",
                QSystemTrayIcon.MessageIcon.Information,
                5000
            )
    
    def _on_regulation_download_failed(self, error_msg: str):
        """规章 PDF 下载失败通知
        
        Feature: caac-regulation-search
        Requirements: 5.8
        """
        if self._tray:
            self._tray.showMessage(
                "📜 规章下载失败",
                error_msg,
                QSystemTrayIcon.MessageIcon.Warning,
                5000
            )
    
    def _open_clipboard_history_live_preview(self) -> None:
        """打开工作台窗口并进入实时预览模式
        
        Feature: screenshot-ocr-split-view
        
        在截图热键按下时调用，如果工作台窗口已存在则进入实时预览模式。
        如果窗口不存在，则不创建（避免阻塞截图操作）。
        
        注意：创建新窗口会触发 _refresh() 加载历史记录，这是一个耗时操作，
        会阻塞主线程导致截图覆盖层延迟显示。因此只在窗口已存在时才进入实时预览。
        """
        import time
        start_time = time.perf_counter()
        async_debug_log("_open_clipboard_history_live_preview 开始", "LIVE-PREVIEW")
        
        try:
            # 检查管理器是否初始化
            if self._clipboard_history_manager is None:
                async_debug_log("管理器未初始化，跳过", "LIVE-PREVIEW")
                return
            
            # 检查是否启用分屏视图
            use_split_view = True
            if self._config_manager:
                use_split_view = getattr(self._config_manager.config, 'use_split_view', True)
            
            if not use_split_view:
                async_debug_log("分屏视图未启用，跳过", "LIVE-PREVIEW")
                return
            
            # 只有窗口已存在时才进入实时预览模式
            # 不创建新窗口，避免阻塞截图操作
            if self._clipboard_history_window is not None:
                try:
                    # 确保 OCR 管理器已设置
                    if self._ocr_manager is not None:
                        self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
                    self._clipboard_history_window.enter_live_preview_mode()
                    total_ms = (time.perf_counter() - start_time) * 1000
                    async_debug_log(f"_open_clipboard_history_live_preview 完成，总耗时: {total_ms:.2f}ms", "LIVE-PREVIEW")
                except RuntimeError:
                    # 窗口对象已被删除
                    self._clipboard_history_window = None
                    async_debug_log("窗口对象已被删除", "LIVE-PREVIEW")
            else:
                async_debug_log("工作台窗口未预加载，跳过实时预览", "LIVE-PREVIEW")
            
        except Exception as e:
            import traceback
            async_debug_log(f"打开工作台窗口（实时预览）失败: {e}", "CLIPBOARD-OCR")
            traceback.print_exc()
    
    def _update_live_preview(self, image: QImage) -> None:
        """更新实时预览图片（选区完成时打开工作台）
        
        Feature: screenshot-ocr-split-view, workbench-on-selection-complete
        
        在选区确定后调用，打开工作台窗口并显示实时预览。
        工作台在选区完成时才出现，而不是按截图热键时就出现。
        
        注意：只有 always_ocr_on_screenshot 设置开启时才自动打开工作台。
        用户关闭"截图时始终开启文字识别"后，不应自动弹出工作台。
        
        Args:
            image: 截图图片
        """
        from screenshot_tool.core.async_logger import async_debug_log
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        # 检查 always_ocr_on_screenshot 设置，关闭时不自动打开工作台
        if self._config_manager and not self._config_manager.config.always_ocr_on_screenshot:
            async_debug_log("always_ocr_on_screenshot 关闭，跳过实时预览", "LIVE-PREVIEW")
            return
        
        try:
            # 确保工作台窗口存在
            if self._clipboard_history_window is None:
                # 检查管理器是否初始化
                if self._clipboard_history_manager is None:
                    async_debug_log("剪贴板管理器未初始化，无法创建工作台窗口", "LIVE-PREVIEW")
                    return
                
                # 创建工作台窗口（跳过初始刷新，避免阻塞）
                self._clipboard_history_window = ClipboardHistoryWindow(
                    self._clipboard_history_manager,
                    skip_initial_refresh=True
                )
                # 连接截图编辑和贴图信号
                self._clipboard_history_window.edit_screenshot_requested.connect(
                    self._edit_screenshot_from_history
                )
                self._clipboard_history_window.ding_screenshot_requested.connect(
                    self._ding_from_history
                )
                async_debug_log("创建新的工作台窗口", "LIVE-PREVIEW")
            
            # 确保 OCR 管理器已设置
            if self._ocr_manager is not None:
                self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
            
            # 进入实时预览模式并显示图片
            self._clipboard_history_window.enter_live_preview_mode()
            self._clipboard_history_window.show_live_preview(image)
            
            async_debug_log("选区完成，工作台已打开并显示预览", "LIVE-PREVIEW")
            
        except RuntimeError:
            # 窗口已被销毁
            self._clipboard_history_window = None
            async_debug_log("工作台窗口已被销毁", "LIVE-PREVIEW")
        except Exception as e:
            async_debug_log(f"打开工作台预览失败: {e}", "LIVE-PREVIEW")
    
    def _exit_live_preview_mode(self) -> None:
        """退出实时预览模式
        
        Feature: screenshot-ocr-split-view
        
        在截图取消或完成时调用，清理实时预览状态。
        """
        if self._clipboard_history_window is None:
            return
        
        try:
            if hasattr(self._clipboard_history_window, 'exit_live_preview_mode'):
                self._clipboard_history_window.exit_live_preview_mode()
        except RuntimeError:
            # 窗口已被销毁
            self._clipboard_history_window = None
    
    def _open_workbench_with_temporary_preview(self, image: QImage) -> None:
        """打开工作台并显示截图（已禁用）
        
        Feature: workbench-temporary-preview-python
        
        注意：此功能已禁用。截图保存后不再自动打开工作台。
        工作台只能通过快捷键手动打开。
        
        Args:
            image: 截图图片（未使用）
        """
        # 功能已禁用：截图保存后不自动打开工作台
        # 用户可以通过快捷键 Ctrl+Alt+P 手动打开工作台查看历史
        pass
    
    def _toggle_clipboard_history(self):
        """切换工作台窗口显示/最小化
        
        Feature: clipboard-ocr-merge
        Requirements: 7.3
        
        按一次快捷键打开，再按一次最小化
        - 窗口不存在或已销毁：创建新窗口
        - 窗口不可见或最小化：显示并激活
        - 窗口可见且未最小化：最小化
        """
        # 检查工作台窗口是否存在
        if self._clipboard_history_window is not None:
            try:
                is_visible = self._clipboard_history_window.isVisible()
                is_minimized = self._clipboard_history_window.isMinimized()
                
                async_debug_log(f"工作台窗口状态: visible={is_visible}, minimized={is_minimized}", "EXTENDED-HOTKEYS")
                
                if is_visible and not is_minimized:
                    # 窗口已显示且未最小化，最小化
                    self._clipboard_history_window.showMinimized()
                    async_debug_log("工作台窗口已最小化", "EXTENDED-HOTKEYS")
                    return
            except RuntimeError:
                # 窗口已被销毁
                self._clipboard_history_window = None
        
        # 窗口不存在、未显示或已最小化，打开/显示
        self._open_clipboard_history()
    
    def _open_clipboard_history(self):
        """打开工作台窗口
        
        Feature: clipboard-history
        Requirements: 4.1, 4.2, 4.3
        """
        try:
            # 检查管理器是否初始化
            if self._clipboard_history_manager is None:
                if self._tray:
                    self._tray.showMessage(
                        "工作台",
                        "工作台功能未初始化",
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                return
            
            # 延迟导入
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            
            # 如果窗口已存在，激活它
            if self._clipboard_history_window is not None:
                try:
                    # 确保 OCR 管理器已设置
                    if self._ocr_manager is not None:
                        self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
                    # 如果窗口最小化，先恢复正常状态
                    # Bug fix (2026-01-23): show() 不会恢复最小化的窗口
                    if self._clipboard_history_window.isMinimized():
                        self._clipboard_history_window.showNormal()
                    else:
                        self._clipboard_history_window.show()
                    self._clipboard_history_window.activateWindow()
                    self._clipboard_history_window.raise_()
                    return
                except RuntimeError:
                    # 窗口对象已被删除
                    self._clipboard_history_window = None
            
            # 创建新窗口
            self._clipboard_history_window = ClipboardHistoryWindow(
                self._clipboard_history_manager
            )
            
            # 设置 OCR 管理器
            if self._ocr_manager is not None:
                self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
            
            # 连接截图编辑和贴图信号（Feature: screenshot-state-restore, Requirements: 2.1, 3.1）
            self._clipboard_history_window.edit_screenshot_requested.connect(
                self._edit_screenshot_from_history
            )
            self._clipboard_history_window.ding_screenshot_requested.connect(
                self._ding_from_history
            )
            
            self._clipboard_history_window.show()
            
        except Exception as e:
            import traceback
            print(f"[工作台] 打开失败: {e}")
    
    def _open_clipboard_history_with_ocr(self, item_id: str):
        """打开工作台窗口并自动对指定条目执行 OCR
        
        Feature: clipboard-ocr-merge
        Requirements: 9.1
        
        Args:
            item_id: 要自动 OCR 的历史记录条目 ID
        """
        try:
            # 检查管理器是否初始化
            if self._clipboard_history_manager is None:
                return
            
            # 延迟导入
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            
            # 如果窗口已存在，使用 open_with_auto_ocr
            if self._clipboard_history_window is not None:
                try:
                    # 确保 OCR 管理器已设置
                    if self._ocr_manager is not None:
                        self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
                    self._clipboard_history_window.open_with_auto_ocr(item_id)
                    return
                except RuntimeError:
                    # 窗口对象已被删除
                    self._clipboard_history_window = None
            
            # 创建新窗口
            self._clipboard_history_window = ClipboardHistoryWindow(
                self._clipboard_history_manager
            )
            
            # 设置 OCR 管理器
            if self._ocr_manager is not None:
                self._clipboard_history_window.set_ocr_manager(self._ocr_manager)
            
            # 连接截图编辑和贴图信号
            self._clipboard_history_window.edit_screenshot_requested.connect(
                self._edit_screenshot_from_history
            )
            self._clipboard_history_window.ding_screenshot_requested.connect(
                self._ding_from_history
            )
            
            # 使用 open_with_auto_ocr 打开并自动触发 OCR
            self._clipboard_history_window.open_with_auto_ocr(item_id)
            
        except Exception as e:
            import traceback
            async_debug_log(f"打开工作台窗口（自动OCR）失败: {e}", "CLIPBOARD-OCR")
            traceback.print_exc()
            
            if self._tray:
                self._tray.showMessage(
                    "工作台",
                    f"打开失败: {e}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
    
    def _edit_screenshot_from_history(self, item_id: str):
        """从工作台继续编辑截图
        
        Feature: screenshot-state-restore
        Requirements: 2.1, 2.2, 2.3
        
        Args:
            item_id: 历史条目 ID
        """
        try:
            if self._overlay is None:
                return
            
            # 调用 overlay 的恢复方法
            success = self._overlay.restore_from_history(item_id)
            
            if not success and self._tray:
                self._tray.showMessage(
                    "继续编辑",
                    "无法恢复截图，可能图片已被删除",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
        except Exception as e:
            import traceback
            print(f"[继续编辑] 失败: {e}")
            traceback.print_exc()
    
    def _ding_from_history(self, item_id: str):
        """从工作台创建贴图
        
        Feature: screenshot-state-restore
        Requirements: 3.1, 3.2, 3.3
        
        Args:
            item_id: 历史条目 ID
        """
        try:
            if self._clipboard_history_manager is None:
                return
            
            # 获取渲染后的图像（带标注）
            rendered_image = self._clipboard_history_manager.render_screenshot_with_annotations(item_id)
            
            if rendered_image is None:
                # 尝试获取原始图像
                rendered_image = self._clipboard_history_manager.get_screenshot_image(item_id)
            
            if rendered_image is None:
                if self._tray:
                    self._tray.showMessage(
                        "贴图",
                        "无法加载图片，可能已被删除",
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                return
            
            # 创建贴图窗口
            ding_manager = self._get_ding_manager()
            if ding_manager is not None:
                from PySide6.QtCore import QPoint
                from PySide6.QtGui import QCursor
                
                # 在鼠标位置创建贴图
                cursor_pos = QCursor.pos()
                ding_manager.create_ding(rendered_image, cursor_pos)
                
        except Exception as e:
            import traceback
            print(f"[贴图] 失败: {e}")
            traceback.print_exc()
    
    def _toggle_mouse_highlight(self):
        """切换鼠标高亮功能
        
        Feature: mouse-highlight
        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        if self._mouse_highlight_manager is None:
            if self._tray:
                self._tray.showMessage(
                    "鼠标高亮",
                    "鼠标高亮功能未初始化",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            return
        
        # 切换状态
        new_state = self._mouse_highlight_manager.toggle()
        
        # 更新菜单勾选状态
        if hasattr(self, '_mouse_highlight_action') and self._mouse_highlight_action:
            self._mouse_highlight_action.setChecked(new_state)
        
        # 显示通知
        if self._tray:
            if new_state:
                self._tray.showMessage(
                    "鼠标高亮",
                    "鼠标高亮已启用 🖱️✨",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            else:
                self._tray.showMessage(
                    "鼠标高亮",
                    "鼠标高亮已关闭",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
    
    def _open_mouse_highlight_debug_panel(self):
        """打开鼠标高亮调试面板
        
        Feature: mouse-highlight-debug-panel
        Requirements: 7.2
        """
        if self._mouse_highlight_manager is None:
            if self._tray:
                self._tray.showMessage(
                    "鼠标高亮",
                    "鼠标高亮功能未初始化",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            return
        
        from screenshot_tool.ui.mouse_highlight_debug_panel import MouseHighlightDebugPanel
        
        MouseHighlightDebugPanel.show_panel(
            self._config_manager,
            self._mouse_highlight_manager,
            self._main_window if self._main_window else None
        )
    
    def _toggle_spotlight(self):
        """切换聚光灯效果
        
        热键触发，快速开关聚光灯效果。
        
        Feature: mouse-highlight
        """
        if self._mouse_highlight_manager is None:
            return
        
        # 必须先启用鼠标高亮
        if not self._mouse_highlight_manager.is_enabled():
            if self._tray:
                self._tray.showMessage(
                    "聚光灯",
                    "请先启用鼠标高亮功能",
                    QSystemTrayIcon.MessageIcon.Warning,
                    2000
                )
            return
        
        # 切换聚光灯
        new_state = self._mouse_highlight_manager.toggle_spotlight()
        
        # 更新菜单勾选状态
        if hasattr(self, '_spotlight_action') and self._spotlight_action:
            self._spotlight_action.setChecked(new_state)
        
        # 显示通知
        if self._tray:
            if new_state:
                self._tray.showMessage(
                    "聚光灯",
                    "聚光灯已开启 🔦",
                    QSystemTrayIcon.MessageIcon.Information,
                    1500
                )
            else:
                self._tray.showMessage(
                    "聚光灯",
                    "聚光灯已关闭",
                    QSystemTrayIcon.MessageIcon.Information,
                    1500
                )
    
    # ========== 系统工具回调方法 ==========
    # Feature: system-tools
    # Requirements: 6.2
    
    def _open_dialog_safe(self, dialog_factory, title: str, log_name: str):
        """安全打开对话框的通用方法
        
        使用 show() 非模态方式打开对话框，避免 exec() 阻塞主事件循环。
        这样可以确保全局热键在对话框打开时仍然能够正常工作。
        
        Args:
            dialog_factory: 返回对话框实例的可调用对象
            title: 托盘通知标题
            log_name: 日志中显示的功能名称
        """
        async_debug_log(f"_open_dialog_safe 被调用: title={title}, log_name={log_name}", "DIALOG")
        try:
            dialog = dialog_factory()
            async_debug_log(f"对话框工厂返回成功: {type(dialog).__name__}", "DIALOG")
            # 使用 show() 代替 exec()，避免阻塞主事件循环
            # 这样全局热键可以在对话框打开时正常工作
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            # QMainWindow 不设置模态，允许最大化/最小化
            # QDialog 保持模态行为
            from PySide6.QtWidgets import QMainWindow
            if not isinstance(dialog, QMainWindow):
                dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            
            # 保存对话框引用，防止被垃圾回收
            # 使用列表存储，支持同时打开多个对话框
            if not hasattr(self, '_open_dialogs'):
                self._open_dialogs = []
            # 清理已关闭的对话框（安全检查，避免访问已删除的C++对象）
            valid_dialogs = []
            for d in self._open_dialogs:
                try:
                    if d.isVisible():
                        valid_dialogs.append(d)
                except RuntimeError:
                    # C++ 对象已删除，跳过
                    pass
            self._open_dialogs = valid_dialogs
            self._open_dialogs.append(dialog)
            
            # 确保对话框显示在屏幕中央
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                dialog_size = dialog.sizeHint()
                x = screen_geometry.x() + (screen_geometry.width() - dialog_size.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - dialog_size.height()) // 2
                dialog.move(x, y)
                async_debug_log(f"对话框位置: ({x}, {y}), 屏幕: {screen_geometry}", "DIALOG")
            
            dialog.show()
            dialog.raise_()  # 确保窗口在最前
            dialog.activateWindow()
            
            # 记录窗口状态
            async_debug_log(f"对话框已显示: {log_name}, visible={dialog.isVisible()}, geometry={dialog.geometry()}", "DIALOG")
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[系统工具] 打开{log_name}失败: {e}")
            async_debug_log(f"打开{log_name}失败: {e}\n{error_detail}", "DIALOG")
            traceback.print_exc()
            if self._tray:
                self._tray.showMessage(
                    title,
                    f"打开失败: {e}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
    
    def _open_scheduled_shutdown(self):
        """打开预约关机对话框
        
        Feature: system-tools
        Requirements: 1.5, 1.6, 1.7, 1.8
        """
        def factory():
            from screenshot_tool.ui.scheduled_shutdown_dialog import ScheduledShutdownDialog
            return ScheduledShutdownDialog()
        self._open_dialog_safe(factory, "预约关机", "预约关机")
    
    def _init_markdown_mode(self):
        """初始化 Markdown 模式
        
        创建 Markdown 转换器。不再使用热键管理器和模式管理器。
        
        Feature: web-to-markdown-dialog
        Requirements: 2.1, 2.3, 2.4
        """
        # 清理旧的 Markdown 模式管理器（如果存在）
        if self._markdown_mode_manager:
            try:
                self._markdown_mode_manager.cleanup()
            except Exception:
                pass
            self._markdown_mode_manager = None
        
        # 清理旧的转换器
        self._markdown_converter = None
        
        try:
            # 创建 Markdown 转换器
            from screenshot_tool.services.markdown_converter import MarkdownConverter
            self._markdown_converter = MarkdownConverter(self._config_manager.config.markdown)
            
            print("Markdown 模式已初始化（对话框模式）")
            
        except (ImportError, AttributeError, RuntimeError) as e:
            print(f"[Warning] 初始化 Markdown 模式失败: {e}")
            import traceback
            traceback.print_exc()
            self._markdown_converter = None
    
    def _start_markdown_mode(self):
        """启动 Markdown 模式（从托盘菜单调用）
        
        打开 WebToMarkdownDialog 对话框，用户输入 URL 后开始转换。
        
        Feature: web-to-markdown-dialog
        Requirements: 1.3
        """
        # 检查功能权限（使用 check 而非 use，因为实际使用在转换时计数）
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import Feature
            if not self._check_feature_access("网页转 Markdown", Feature.WEB_TO_MARKDOWN):
                return
        except ImportError:
            pass  # 订阅模块未安装，允许使用
        
        from screenshot_tool.ui.web_to_markdown_dialog import WebToMarkdownDialog
        
        # 确保转换器已初始化
        if not self._markdown_converter:
            from screenshot_tool.services.markdown_converter import MarkdownConverter
            self._markdown_converter = MarkdownConverter(self._config_manager.config.markdown)
        
        # 创建并显示对话框（使用 show() 代替 exec()，避免阻塞热键）
        # 注意：必须保存到 self，否则局部变量会被垃圾回收导致闪退
        self._markdown_dialog = WebToMarkdownDialog(self._config_manager.config.markdown)
        self._markdown_dialog.conversion_requested.connect(self._on_markdown_urls_submitted)
        self._markdown_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._markdown_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._markdown_dialog.show()
        self._markdown_dialog.activateWindow()
    
    def _on_markdown_urls_submitted(self, urls: list, save_dir: str):
        """处理 URL 提交
        
        将 URL 添加到队列，如果没有正在运行的转换则启动。
        
        Args:
            urls: URL 列表
            save_dir: 保存目录
            
        Feature: web-to-markdown-dialog
        Requirements: 5.1, 5.2, 5.5
        """
        if not urls:
            return
        
        # 保存目录到配置（记住用户选择）
        self._config_manager.config.markdown.save_dir = save_dir
        self._config_manager.save()
        
        # 记录当前批次的保存目录
        self._markdown_save_dir = save_dir
        
        # 添加到队列
        self._markdown_url_queue.extend(urls)
        
        # 显示通知
        if self._tray:
            count = len(urls)
            queue_size = len(self._markdown_url_queue)
            if queue_size > count:
                self._tray.showMessage(
                    "网页转 Markdown",
                    f"已添加 {count} 个 URL 到队列（共 {queue_size} 个待处理）",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            else:
                self._tray.showMessage(
                    "网页转 Markdown",
                    f"开始转换 {count} 个 URL...",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        
        # 如果没有正在运行的转换，启动下一个
        if self._markdown_worker is None or not self._markdown_worker.isRunning():
            self._start_next_markdown_conversion()
    
    def _start_next_markdown_conversion(self):
        """启动下一个转换任务
        
        从队列中取出 URL 并启动转换。
        
        Feature: web-to-markdown-dialog
        Requirements: 5.2
        """
        if not self._markdown_url_queue:
            return
        
        # 取出下一个 URL
        url = self._markdown_url_queue.pop(0)
        
        # 注意：不再传递 converter 给 Worker，因为 Playwright 不是线程安全的
        # Worker 会在自己的线程中创建新的 converter 实例
        
        # 获取保存目录（使用当前批次的保存目录）
        save_dir = getattr(self, '_markdown_save_dir', '') or self._config_manager.config.markdown.get_save_dir()
        
        # 创建并启动工作线程
        # 注意：不传递 converter，让 Worker 在自己的线程中创建
        self._markdown_worker = MarkdownConversionWorker(
            url,
            self._config_manager.config.markdown,
            save_dir=save_dir
        )
        self._markdown_worker.conversion_finished.connect(self._on_markdown_url_converted)
        self._markdown_worker.start()
    
    def _on_markdown_url_converted(self, url: str, result):
        """单个 URL 转换完成回调
        
        显示系统托盘通知，继续处理队列中的下一个。
        
        Args:
            url: 转换的 URL
            result: ConversionResult 对象
            
        Feature: web-to-markdown-dialog
        Requirements: 6.1, 6.2
        """
        if self._tray:
            if result.success:
                # 转换成功，增加使用量计数
                # Feature: subscription-system
                try:
                    from screenshot_tool.services.subscription import Feature
                    if self._subscription_manager and self._subscription_manager.is_initialized:
                        self._subscription_manager.use_feature(Feature.WEB_TO_MARKDOWN)
                except ImportError:
                    pass
                
                # 成功通知
                title = result.title or "网页"
                if len(title) > 30:
                    title = title[:30] + "..."
                self._tray.showMessage(
                    "转换成功",
                    f"✓ {title} 转换成功",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                # 失败通知
                error = result.error or "未知错误"
                if len(error) > 50:
                    error = error[:50] + "..."
                self._tray.showMessage(
                    "转换失败",
                    f"✗ 转换失败: {error}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
        
        # 清理当前工作线程引用
        if self._markdown_worker:
            self._markdown_worker.deleteLater()
            self._markdown_worker = None
        
        # 继续处理队列中的下一个
        if self._markdown_url_queue:
            self._start_next_markdown_conversion()
    
    def _start_pdf_convert(self):
        """启动 PDF 转 Markdown 功能
        
        Feature: pdf-to-markdown
        """
        from PySide6.QtWidgets import QMessageBox
        from screenshot_tool.ui.file_to_markdown_dialog import FileToMarkdownDialog
        
        config = self._config_manager.config.mineru
        
        # 获取活动窗口作为对话框父窗口，避免 None 导致的 UI 冻结
        parent_widget = self._app.activeWindow()
        
        # 检查 API Token
        if not config.is_configured():
            reply = QMessageBox.question(
                parent_widget,
                "未配置 API Token",
                "MinerU API Token 未配置。\n\n是否打开设置页面配置 Token？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_settings()
            return
        
        # 创建并显示文件选择对话框（使用 show() 代替 exec()，避免阻塞热键）
        dialog = FileToMarkdownDialog(config, parent_widget)
        dialog.conversion_requested.connect(self._on_pdf_files_submitted)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _on_pdf_files_submitted(self, file_paths: list, save_dir: str):
        """处理文件转 Markdown 提交
        
        Args:
            file_paths: 文件路径列表
            save_dir: 保存目录
            
        Feature: file-to-markdown
        """
        if not file_paths:
            return
        
        # 保存目录到配置（记住用户选择）
        self._config_manager.config.mineru.save_dir = save_dir
        self._config_manager.save()
        
        # 开始后台转换
        self._do_pdf_convert(file_paths, save_dir)
    
    def _do_pdf_convert(self, file_paths: list, save_dir: str = ""):
        """执行文件转换（后台线程）
        
        Args:
            file_paths: 文件路径列表
            save_dir: 保存目录，为空则保存到源文件目录
            
        Feature: file-to-markdown
        """
        import os
        import threading
        
        try:
            from screenshot_tool.services.mineru_service import MinerUService, MinerUError
        except ImportError as e:
            ocr_debug_log(f"无法导入 MinerU 服务: {e}")
            return
        
        config = self._config_manager.config.mineru
        notification_enabled = self._config_manager.config.notification.pdf_convert
        
        def convert_in_background():
            """后台线程执行转换"""
            service = MinerUService(
                api_token=config.api_token,
                model_version=config.model_version
            )
            
            total = len(file_paths)
            success_count = 0
            failed_files = []
            
            for file_path in file_paths:
                filename = os.path.basename(file_path)
                try:
                    # 确定输出目录：优先使用指定的保存目录，否则使用源文件目录
                    output_dir = save_dir if save_dir else os.path.dirname(file_path)
                    md_path = service.convert_file(file_path, output_dir=output_dir)
                    success_count += 1
                    ocr_debug_log(f"文件转换成功: {filename} -> {md_path}")
                except MinerUError as e:
                    failed_files.append((filename, str(e)))
                    ocr_debug_log(f"文件转换异常: {filename} - {e}")
                except Exception as e:
                    failed_files.append((filename, str(e)))
                    ocr_debug_log(f"文件转换异常: {filename} - {e}")
            
            # 在主线程显示通知
            if notification_enabled and self._tray:
                if success_count == total:
                    self._tray.showMessage(
                        "文件转换完成",
                        f"成功转换 {success_count} 个文件",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )
                elif success_count > 0:
                    self._tray.showMessage(
                        "文件转换完成",
                        f"成功: {success_count}/{total}，失败: {len(failed_files)}",
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                else:
                    failed_msg = failed_files[0][1] if failed_files else "未知错误"
                    self._tray.showMessage(
                        "文件转换失败",
                        f"全部 {total} 个文件转换失败\n{failed_msg}",
                        QSystemTrayIcon.MessageIcon.Critical,
                        5000
                    )
        
        # 启动后台线程
        thread = threading.Thread(target=convert_in_background, daemon=True)
        thread.start()
        
        # 显示开始转换的通知
        if notification_enabled and self._tray:
            self._tray.showMessage(
                "文件转换开始",
                f"正在后台转换 {len(file_paths)} 个文件...",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _init_update_service(self):
        """初始化更新服务
        
        Feature: auto-update, auto-restart-update
        Requirements: 1.1, 11.1, 11.2, 11.3, 2.1, 3.2
        """
        try:
            from screenshot_tool.services.update_service import UpdateService, UpdateExecutor
            
            self._update_service = UpdateService(
                config_manager=self._config_manager,
                parent=None
            )
            
            # 连接信号
            self._update_service.update_available.connect(self._on_update_available)
            self._update_service.update_error.connect(self._on_update_error)
            self._update_service.check_completed.connect(self._on_update_check_completed)
            # 启动时清理临时文件并更新版本记录
            cleaned = self._update_service.cleanup_on_startup()
            if cleaned > 0:
                ocr_debug_log(f"清理了 {cleaned} 个更新临时文件")
            
            # Feature: auto-restart-update
            # Requirements: 2.1, 3.2
            # 检查是否从更新启动（有 --cleanup-old 参数）
            old_exe_path = UpdateExecutor.parse_cleanup_arg(sys.argv)
            if old_exe_path:
                ocr_debug_log(f"[UPDATE] 检测到更新启动，旧版本路径: {old_exe_path}")
                # 启动后台清理线程
                UpdateExecutor.cleanup_old_version_async(old_exe_path)
                # 显示更新成功通知（延迟显示，等待托盘初始化完成）
                self._pending_update_success_notification = True
            else:
                self._pending_update_success_notification = False
            
            # 启动后延迟自动检查更新
            if self._update_service.should_auto_check():
                QTimer.singleShot(
                    self._update_service.STARTUP_CHECK_DELAY * 1000,
                    self._auto_check_for_updates
                )
            
            ocr_debug_log("更新服务初始化完成")
            
        except (ImportError, AttributeError, RuntimeError, OSError) as e:
            ocr_debug_log(f"初始化更新服务失败: {e}")
            self._update_service = None
            self._pending_update_success_notification = False
    
    def _auto_check_for_updates(self):
        """自动检查更新（静默模式）
        
        Feature: auto-update
        Requirements: 1.1, 11.2
        """
        if self._update_service:
            self._update_service.check_for_updates(silent=True)
    
    def _on_update_available(self, version_info):
        """发现新版本回调 - 通知用户
        
        Feature: auto-update
        Requirements: 5.2
        """
        if not self._tray or not version_info:
            return
        
        # 检查是否应该通知
        if self._update_service and self._update_service.should_notify(version_info.version):
            # 通知用户发现新版本
            self._tray.showMessage(
                "发现新版本",
                f"虎哥截图 v{version_info.version} 可用\n请在设置中检查更新并下载",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
            self._update_service.mark_notified(version_info.version)
    
    def _on_update_error(self, error_msg: str):
        """更新错误回调
        
        Feature: auto-update
        Requirements: 6.1, 6.2
        """
        if self._tray:
            self._tray.showMessage(
                "更新失败",
                error_msg,
                QSystemTrayIcon.MessageIcon.Warning,
                3000
            )
    
    def _on_update_check_completed(self, has_update: bool, version_info):
        """更新检查完成回调
        
        Feature: auto-update
        Requirements: 5.2
        """
        if not self._tray:
            return
        
        # 只有手动检查时才显示"已是最新版本"
        # 自动检查时不显示（避免打扰用户）
        if not has_update and version_info:
            # 这是手动检查的结果
            current_version = self._update_service.current_version if self._update_service else "未知"
            self._tray.showMessage(
                "已是最新版本",
                f"当前版本 v{current_version} 已是最新",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    def _on_markdown_convert_triggered(self, url: str):
        """Markdown 转换触发回调
        
        将转换请求加入队列，由后台线程依次处理。
        支持多个请求排队，确保所有转换都能完成。
        
        Args:
            url: 要转换的网页 URL
            
        Feature: web-to-markdown
        Requirements: 2.5, 4.4, 5.1, 5.2, 5.3
        """
        import queue
        import threading
        from screenshot_tool.core.async_logger import async_debug_log
        
        async_debug_log(f"Markdown 转换触发, url={url}", "MARKDOWN")
        
        # 初始化队列和锁（如果不存在）
        if not hasattr(self, '_markdown_queue'):
            self._markdown_queue = queue.Queue()
            self._markdown_worker_running = False
            self._markdown_worker_lock = threading.Lock()
            self._markdown_batch_total = 0  # 批次总数
            self._markdown_batch_success = 0  # 批次成功数
            self._markdown_batch_failed = 0  # 批次失败数
        
        # 确保转换器已初始化
        if not self._markdown_converter:
            from screenshot_tool.services.markdown_converter import MarkdownConverter
            self._markdown_converter = MarkdownConverter(self._config_manager.config.markdown)
        
        # 将 URL 加入队列
        self._markdown_queue.put(url)
        queue_size = self._markdown_queue.qsize()
        async_debug_log(f"URL 已加入队列，当前队列大小: {queue_size}", "MARKDOWN")
        
        # 更新批次总数
        with self._markdown_worker_lock:
            # 如果工作线程未运行，说明是新批次，重置计数器
            if not self._markdown_worker_running:
                self._markdown_batch_total = 0
                self._markdown_batch_success = 0
                self._markdown_batch_failed = 0
            self._markdown_batch_total += 1
        
        # 显示通知
        if self._tray:
            url_display = url[:50] + '...' if len(url) > 50 else url
            if queue_size > 1:
                self._tray.showMessage(
                    "Markdown 转换",
                    f"已加入队列（排队中: {queue_size}）\n{url_display}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            else:
                self._tray.showMessage(
                    "Markdown 转换",
                    f"正在转换网页...\n{url_display}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        
        # 使用锁保护工作线程启动，防止竞态条件
        with self._markdown_worker_lock:
            if not self._markdown_worker_running:
                self._start_markdown_worker()
    
    def _start_markdown_worker(self):
        """启动 Markdown 转换工作线程
        
        工作线程会持续从队列中取出 URL 进行转换，直到队列为空。
        注意：调用此方法前应持有 _markdown_worker_lock 锁。
        """
        import queue
        import threading
        import weakref
        from screenshot_tool.core.async_logger import async_debug_log
        
        if self._markdown_worker_running:
            return
        
        self._markdown_worker_running = True
        
        # 捕获引用
        converter = self._markdown_converter
        mode_manager = self._markdown_mode_manager
        url_queue = self._markdown_queue
        worker_lock = self._markdown_worker_lock
        weak_self = weakref.ref(self)
        
        if not converter or not mode_manager:
            async_debug_log("错误: 转换器或模式管理器未初始化", "MARKDOWN")
            self._markdown_worker_running = False
            return
        
        def worker_thread():
            """工作线程：依次处理队列中的所有 URL"""
            from screenshot_tool.services.markdown_converter import ConversionResult
            
            async_debug_log("Markdown 工作线程启动", "MARKDOWN")
            
            while True:
                try:
                    # 非阻塞获取，队列空时退出
                    try:
                        url = url_queue.get_nowait()
                    except queue.Empty:
                        # 队列为空，退出循环
                        break
                    
                    url_display = url[:80] + '...' if len(url) > 80 else url
                    async_debug_log(f"开始处理队列中的 URL: {url_display}", "MARKDOWN")
                    
                    try:
                        result = converter.convert(url)
                        async_debug_log(f"转换完成, success={result.success}", "MARKDOWN")
                        
                        # 更新计数器
                        main_app = weak_self()
                        if main_app is not None:
                            with worker_lock:
                                if result.success:
                                    main_app._markdown_batch_success += 1
                                else:
                                    main_app._markdown_batch_failed += 1
                        
                        mode_manager.convert_finished.emit(result)
                    except Exception as e:
                        error_msg = str(e)
                        async_debug_log(f"转换异常: {error_msg}", "MARKDOWN")
                        import traceback
                        async_debug_log(f"异常堆栈:\n{traceback.format_exc()}", "MARKDOWN")
                        
                        # 更新失败计数
                        main_app = weak_self()
                        if main_app is not None:
                            with worker_lock:
                                main_app._markdown_batch_failed += 1
                        
                        error_result = ConversionResult(success=False, error=error_msg)
                        mode_manager.convert_finished.emit(error_result)
                    finally:
                        # 标记任务完成（无论成功失败都要调用）
                        url_queue.task_done()
                    
                except Exception as e:
                    async_debug_log(f"工作线程异常: {e}", "MARKDOWN")
                    break
            
            # 工作线程结束，使用锁保护状态更新
            async_debug_log("Markdown 工作线程结束", "MARKDOWN")
            main_app = weak_self()
            if main_app is not None:
                with worker_lock:
                    main_app._markdown_worker_running = False
                    # 获取批次统计
                    total = main_app._markdown_batch_total
                    success = main_app._markdown_batch_success
                    failed = main_app._markdown_batch_failed
                
                # 如果处理了多个 URL，显示汇总通知
                if total > 1:
                    async_debug_log(f"批次完成: 总计 {total}, 成功 {success}, 失败 {failed}", "MARKDOWN")
                    # 使用 QTimer 在主线程显示通知
                    from PySide6.QtCore import QTimer
                    
                    # 捕获统计数据到闭包（避免引用失效）
                    _total, _success, _failed = total, success, failed
                    _weak_self = weak_self
                    
                    def show_summary():
                        app = _weak_self()
                        if app is not None and app._tray:
                            if _failed == 0:
                                app._tray.showMessage(
                                    "Markdown 批量转换完成",
                                    f"全部完成！共 {_total} 个网页转换成功",
                                    QSystemTrayIcon.MessageIcon.Information,
                                    4000
                                )
                            else:
                                app._tray.showMessage(
                                    "Markdown 批量转换完成",
                                    f"共 {_total} 个网页：{_success} 个成功，{_failed} 个失败",
                                    QSystemTrayIcon.MessageIcon.Warning,
                                    4000
                                )
                    
                    # 延迟显示汇总，避免与最后一个任务的通知重叠
                    QTimer.singleShot(500, show_summary)
        
        # 启动工作线程
        thread = threading.Thread(target=worker_thread, daemon=True)
        thread.start()
    
    def _on_markdown_convert_finished(self, result):
        """Markdown 转换完成回调
        
        Args:
            result: ConversionResult 转换结果
            
        Feature: web-to-markdown
        Requirements: 4.4, 5.1, 5.2, 5.3
        """
        from screenshot_tool.core.async_logger import async_debug_log
        
        async_debug_log(f"_on_markdown_convert_finished 被调用, success={result.success}", "MARKDOWN")
        
        if result.success:
            async_debug_log(f"Markdown 转换成功: {result.file_path}", "MARKDOWN")
            
            # 成功通知
            if self._tray:
                async_debug_log("显示成功通知", "MARKDOWN")
                self._tray.showMessage(
                    "Markdown 转换成功",
                    f"已保存到:\n{result.file_path}\n\n内容已复制到剪贴板",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                async_debug_log("托盘图标不存在，无法显示通知", "MARKDOWN")
        else:
            async_debug_log(f"Markdown 转换失败: {result.error}", "MARKDOWN")
            
            # 失败通知
            if self._tray:
                async_debug_log("显示失败通知", "MARKDOWN")
                self._tray.showMessage(
                    "Markdown 转换失败",
                    result.error,
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            else:
                async_debug_log("托盘图标不存在，无法显示通知", "MARKDOWN")
    
    def _on_markdown_warning(self, message: str):
        """Markdown 模式警告消息
        
        Feature: web-to-markdown
        Requirements: 2.5
        """
        # ToolTip 已在 MarkdownModeManager 中显示，这里可以额外处理
        pass
    
    def _on_markdown_error(self, message: str):
        """Markdown 模式错误消息
        
        Feature: web-to-markdown
        Requirements: 5.3
        """
        # 错误通知始终显示
        if self._tray:
            self._tray.showMessage(
                "Markdown 模式错误",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                3000
            )
    
    def _start_gongwen_mode(self):
        """启动公文格式化模式（从托盘菜单调用）"""
        # 确保公文模式已初始化
        if not self._gongwen_mode_manager:
            self._init_gongwen_mode()
        
        if self._gongwen_mode_manager:
            # 如果已经激活，先停用再激活（确保状态正确）
            if self._gongwen_mode_manager.is_active:
                self._gongwen_mode_manager.deactivate()
            self._gongwen_mode_manager.activate()
    
    def _on_gongwen_format_triggered(self, hwnd: int):
        """公文格式化触发回调
        
        在后台线程执行格式化，显示进度对话框允许用户中止。
        
        Args:
            hwnd: Word 窗口句柄
        """
        import threading
        from screenshot_tool.core.async_logger import async_debug_log
        from PySide6.QtWidgets import QProgressDialog, QApplication
        from PySide6.QtCore import Qt, QTimer
        
        async_debug_log(f"公文格式化触发, hwnd={hwnd}", "GONGWEN")
        
        # 清理之前可能残留的进度对话框
        if hasattr(self, '_gongwen_progress') and self._gongwen_progress is not None:
            try:
                self._gongwen_progress.close()
            except (RuntimeError, AttributeError):
                pass
            self._gongwen_progress = None
        
        # 获取主窗口作为父对象，防止对话框被垃圾回收
        parent_widget = None
        app = QApplication.instance()
        if app:
            parent_widget = app.activeWindow()
        
        # 创建进度对话框
        progress = QProgressDialog("正在格式化公文，请稍候...", "取消", 0, 0, parent_widget)
        progress.setWindowTitle("公文格式化")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)  # 立即显示
        progress.setAutoClose(False)  # 手动控制关闭
        progress.setAutoReset(False)
        progress.setCancelButtonText("取消")
        progress.setMinimumWidth(300)
        
        # 保持对话框引用，防止被垃圾回收
        self._gongwen_progress = progress
        
        # 用于线程间通信的标志
        cancel_flag = threading.Event()
        format_done = threading.Event()
        format_result = [None]  # 用列表存储结果，便于在闭包中修改
        
        def format_in_thread():
            """后台线程执行格式化"""
            try:
                async_debug_log("后台线程开始执行格式化", "GONGWEN")
                from screenshot_tool.services.gongwen_formatter import GongwenFormatter, FormatResult, GongwenFormatResult
                
                # 检查是否已取消
                if cancel_flag.is_set():
                    async_debug_log("格式化已被用户取消（启动前）", "GONGWEN")
                    format_result[0] = GongwenFormatResult(
                        success=False,
                        result=FormatResult.FORMAT_ERROR,
                        message="格式化已取消"
                    )
                    return
                
                formatter = GongwenFormatter()
                # 传入取消标志，允许格式化过程中检查
                result = formatter.format_document_by_hwnd(hwnd, cancel_flag=cancel_flag)
                
                async_debug_log(f"格式化结果: success={result.success}, message={result.message}", "GONGWEN")
                format_result[0] = result
                
            except Exception as e:
                import traceback
                async_debug_log(f"格式化线程异常: {e}", "GONGWEN")
                async_debug_log(f"异常堆栈: {traceback.format_exc()}", "GONGWEN")
                from screenshot_tool.services.gongwen_formatter import FormatResult, GongwenFormatResult
                format_result[0] = GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message=f"格式化失败: {str(e)}"
                )
            finally:
                format_done.set()
        
        def on_cancel():
            """用户点击取消"""
            async_debug_log("用户取消格式化", "GONGWEN")
            cancel_flag.set()
        
        def cleanup_progress():
            """安全清理进度对话框"""
            if hasattr(self, '_gongwen_progress') and self._gongwen_progress is not None:
                try:
                    self._gongwen_progress.close()
                except (RuntimeError, AttributeError):
                    pass
                self._gongwen_progress = None
        
        def check_progress():
            """检查格式化进度"""
            # 检查进度对话框是否还存在
            if not hasattr(self, '_gongwen_progress') or self._gongwen_progress is None:
                # 对话框已清理，但仍需等待线程结束后显示结果
                if format_done.is_set() and format_result[0]:
                    self._show_gongwen_result(format_result[0])
                elif not format_done.is_set():
                    # 线程仍在运行，继续等待
                    QTimer.singleShot(100, check_progress)
                return
            
            try:
                if format_done.is_set():
                    # 格式化完成，关闭对话框并显示结果
                    cleanup_progress()
                    
                    if format_result[0]:
                        self._show_gongwen_result(format_result[0])
                elif self._gongwen_progress.wasCanceled():
                    # 用户取消，设置标志，关闭对话框，继续等待线程结束
                    on_cancel()
                    cleanup_progress()
                    QTimer.singleShot(100, check_progress)
                else:
                    # 继续等待
                    QTimer.singleShot(100, check_progress)
            except RuntimeError:
                # 对话框可能已被销毁
                self._gongwen_progress = None
                # 继续等待线程结束
                if not format_done.is_set():
                    QTimer.singleShot(100, check_progress)
        
        # 连接取消信号
        progress.canceled.connect(on_cancel)
        
        # 在后台线程执行
        thread = threading.Thread(target=format_in_thread, daemon=True)
        thread.start()
        
        # 显示进度对话框
        progress.show()
        
        # 启动进度检查
        QTimer.singleShot(100, check_progress)
    
    def _show_gongwen_result(self, result):
        """显示公文格式化结果（主线程调用）"""
        if not self._tray:
            return
            
        if result.success:
            # 成功通知可以被关闭
            if self._config_manager.config.notification.gongwen:
                self._tray.showMessage(
                    "公文格式化完成",
                    result.message,
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        else:
            # 失败通知始终显示
            self._tray.showMessage(
                "公文格式化失败",
                result.message,
                QSystemTrayIcon.MessageIcon.Warning,
                3000
            )
    
    def _show_gongwen_error(self, error_msg: str):
        """显示公文格式化错误（主线程调用）"""
        # 错误通知始终显示
        if self._tray:
            self._tray.showMessage(
                "公文格式化错误",
                error_msg,
                QSystemTrayIcon.MessageIcon.Critical,
                3000
            )
    
    def _show_gongwen_dialog(self):
        """显示公文格式化对话框
        
        Feature: gongwen-dialog
        """
        from screenshot_tool.core.async_logger import async_debug_log
        from PySide6.QtWidgets import QApplication
        
        # 检查功能权限
        # Feature: subscription-system
        try:
            from screenshot_tool.services.subscription import Feature
            if not self._check_feature_access("Word排版", Feature.GONGWEN):
                return
        except ImportError:
            pass  # 订阅模块未安装，允许使用
        
        async_debug_log("打开公文格式化对话框", "GONGWEN")
        
        try:
            from screenshot_tool.ui.gongwen_dialog import GongwenDialog
            
            # 获取活动窗口作为对话框父窗口
            parent_widget = None
            app = QApplication.instance()
            if app:
                parent_widget = app.activeWindow()
            
            dialog = GongwenDialog(parent=parent_widget)
            dialog.format_requested.connect(self._do_gongwen_format_by_name)
            # 使用 show() 代替 exec()，避免阻塞热键
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.show()
            dialog.activateWindow()
            
        except Exception as e:
            async_debug_log(f"打开公文对话框失败: {e}", "GONGWEN")
            if self._tray:
                self._tray.showMessage(
                    "Word排版",
                    f"无法打开对话框: {str(e)}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
    
    def _do_gongwen_format_by_name(self, doc_name: str):
        """通过文档名称执行公文格式化
        
        在后台线程执行格式化，显示进度对话框允许用户中止。
        
        Args:
            doc_name: 文档名称
            
        Feature: gongwen-dialog
        """
        import threading
        from screenshot_tool.core.async_logger import async_debug_log
        from PySide6.QtWidgets import QProgressDialog, QApplication
        from PySide6.QtCore import Qt, QTimer
        
        async_debug_log(f"公文格式化触发 (对话框模式), doc_name={doc_name}", "GONGWEN")
        
        # 清理之前可能残留的进度对话框
        if hasattr(self, '_gongwen_progress') and self._gongwen_progress is not None:
            try:
                self._gongwen_progress.close()
            except (RuntimeError, AttributeError):
                pass
            self._gongwen_progress = None
        
        # 获取主窗口作为父对象
        parent_widget = None
        app = QApplication.instance()
        if app:
            parent_widget = app.activeWindow()
        
        # 创建进度对话框
        progress = QProgressDialog(f"正在格式化 {doc_name}，请稍候...", "取消", 0, 0, parent_widget)
        progress.setWindowTitle("公文格式化")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setCancelButtonText("取消")
        progress.setMinimumWidth(350)
        
        self._gongwen_progress = progress
        
        # 用于线程间通信的标志
        cancel_flag = threading.Event()
        format_done = threading.Event()
        format_result = [None]
        
        def format_in_thread():
            """后台线程执行格式化"""
            try:
                async_debug_log("后台线程开始执行格式化 (对话框模式)", "GONGWEN")
                from screenshot_tool.services.gongwen_formatter import (
                    GongwenFormatter, FormatResult, GongwenFormatResult
                )
                
                if cancel_flag.is_set():
                    format_result[0] = GongwenFormatResult(
                        success=False,
                        result=FormatResult.FORMAT_ERROR,
                        message="格式化已取消"
                    )
                    return
                
                formatter = GongwenFormatter()
                result = formatter.format_document_by_name(doc_name, cancel_flag=cancel_flag)
                
                async_debug_log(f"格式化结果: success={result.success}, message={result.message}", "GONGWEN")
                format_result[0] = result
                
            except Exception as e:
                import traceback
                async_debug_log(f"格式化线程异常: {e}", "GONGWEN")
                async_debug_log(f"异常堆栈: {traceback.format_exc()}", "GONGWEN")
                from screenshot_tool.services.gongwen_formatter import FormatResult, GongwenFormatResult
                format_result[0] = GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message=f"格式化失败: {str(e)}"
                )
            finally:
                format_done.set()
        
        def on_cancel():
            async_debug_log("用户取消格式化 (对话框模式)", "GONGWEN")
            cancel_flag.set()
        
        def cleanup_progress():
            if hasattr(self, '_gongwen_progress') and self._gongwen_progress is not None:
                try:
                    self._gongwen_progress.close()
                except (RuntimeError, AttributeError):
                    pass
                self._gongwen_progress = None
        
        def check_progress():
            if not hasattr(self, '_gongwen_progress') or self._gongwen_progress is None:
                if format_done.is_set() and format_result[0]:
                    self._show_gongwen_result(format_result[0])
                elif not format_done.is_set():
                    QTimer.singleShot(100, check_progress)
                return
            
            try:
                if format_done.is_set():
                    cleanup_progress()
                    if format_result[0]:
                        self._show_gongwen_result(format_result[0])
                elif self._gongwen_progress.wasCanceled():
                    on_cancel()
                    cleanup_progress()
                    QTimer.singleShot(100, check_progress)
                else:
                    QTimer.singleShot(100, check_progress)
            except RuntimeError:
                self._gongwen_progress = None
                if not format_done.is_set():
                    QTimer.singleShot(100, check_progress)
        
        progress.canceled.connect(on_cancel)
        
        thread = threading.Thread(target=format_in_thread, daemon=True)
        thread.start()
        
        progress.show()
        QTimer.singleShot(100, check_progress)

    def _on_gongwen_warning(self, message: str):
        """公文模式警告消息"""
        # ToolTip 已在 GongwenModeManager 中显示，这里可以额外处理
        pass
    
    def _on_hotkey_changed(self, modifier: str, key: str):
        """快捷键变更"""
        if self._hotkey_manager:
            self._hotkey_manager.update_hotkey(modifier, key)
            
            # 更新托盘菜单显示
            if self._tray:
                hotkey_display = f"{modifier.title()}+{key.upper()}"
                self._tray.setToolTip(f"{__app_name__} v{__version__} - {hotkey_display} 截图")
                
                # 更新托盘菜单
                menu = self._tray.contextMenu()
                if menu:
                    actions = menu.actions()
                    if actions:
                        actions[0].setText(f"📷 截图 ({hotkey_display})")
                
                # 检查是否开启了快捷键更新通知
                if self._config_manager.config.notification.hotkey_update:
                    self._tray.showMessage(
                        "快捷键已更新",
                        f"新的截图快捷键: {hotkey_display}",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
    
    def _on_force_lock_changed(self, enabled: bool, retry_interval_ms: int):
        """强制锁定设置变更
        
        Args:
            enabled: 是否启用强制锁定
            retry_interval_ms: 重试间隔（毫秒）
            
        Feature: hotkey-force-lock
        Requirements: 4.3, 7.2
        """
        if self._hotkey_manager:
            self._hotkey_manager.set_force_lock(enabled, retry_interval_ms)
            
            # 显示通知
            if self._tray and self._config_manager.config.notification.hotkey_update:
                if enabled:
                    self._tray.showMessage(
                        "强制锁定已启用",
                        f"热键冲突时将每 {retry_interval_ms/1000:.1f} 秒重试一次",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
                else:
                    self._tray.showMessage(
                        "强制锁定已禁用",
                        "热键冲突时不再自动重试",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
    
    # ========== 订阅系统方法 ==========
    # Feature: subscription-system
    # Requirements: 1.2, 3.3, 4.5
    
    def _show_login_dialog(self):
        """显示登录对话框
        
        Feature: subscription-system
        Requirements: 1.1, 1.2
        """
        from screenshot_tool.ui.login_dialog import LoginDialog
        
        auth_service = None
        if self._subscription_manager:
            auth_service = self._subscription_manager.auth_service
        
        dialog = LoginDialog(auth_service=auth_service)
        dialog.login_success.connect(self._on_login_success)
        # 使用 show() 代替 exec()，避免阻塞热键
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _on_login_success(self, user_info: dict):
        """登录成功回调
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.1, 1.2, 1.3, 4.2
        """
        async_debug_log(f"登录成功: {user_info.get('email')}", "SUBSCRIPTION")
        
        # 同步订阅管理器状态（创建 LicenseService 并验证许可证）
        # _sync_after_login 会创建 LicenseService、验证许可证、重新初始化 FeatureGate
        if self._subscription_manager:
            self._subscription_manager._sync_after_login(user_info)
        
        # 刷新托盘菜单
        self._setup_tray()
        
        # 显示通知
        if self._tray:
            plan_text = "VIP" if self._subscription_manager and self._subscription_manager.is_vip else "免费版"
            self._tray.showMessage(
                "登录成功",
                f"欢迎回来！当前计划: {plan_text}",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def _do_logout(self):
        """执行登出
        
        Feature: subscription-system
        """
        if self._subscription_manager:
            self._subscription_manager.logout()
        
        # 刷新托盘菜单
        self._setup_tray()
        
        if self._tray:
            self._tray.showMessage(
                "已退出登录",
                "您已成功退出登录",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _show_subscription_info(self):
        """显示订阅信息
        
        Feature: subscription-system
        """
        from PySide6.QtWidgets import QMessageBox
        
        if not self._subscription_manager:
            return
        
        state = self._subscription_manager.state
        
        plan_text = "终身 VIP" if state.is_vip else "免费版"
        email = state.user_email or "未知"
        
        info_text = f"""
账户: {email}
计划: {plan_text}

{"🎉 您已解锁所有功能！" if state.is_vip else "☕ 请作者喝杯咖啡，赞助开发可解锁更多功能"}
"""
        
        QMessageBox.information(
            None,
            "我的订阅",
            info_text.strip()
        )
    
    def _show_device_manager(self):
        """显示设备管理对话框
        
        Feature: subscription-system
        Requirements: 3.3, 3.5
        """
        from screenshot_tool.ui.device_manager_dialog import DeviceManagerDialog
        from screenshot_tool.core.device_manager import DeviceManager
        
        # 获取设备管理器
        device_manager = None
        if self._subscription_manager and self._subscription_manager.license_service:
            # 创建设备管理器实例
            client = self._subscription_manager.client
            user_id = self._subscription_manager.state.user_id
            if client and user_id:
                device_manager = DeviceManager(client, user_id)
        
        dialog = DeviceManagerDialog(device_manager=device_manager)
        # 使用 show() 代替 exec()，避免阻塞热键
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _show_upgrade_prompt(self, feature_name: str, reason: str, usage_info: dict = None):
        """显示升级提示对话框
        
        Feature: subscription-system
        Requirements: 4.5
        
        Args:
            feature_name: 功能名称
            reason: 不可用原因
            usage_info: 使用量信息
        """
        async_debug_log(f"_show_upgrade_prompt 开始: feature={feature_name}, reason={reason}", "SUBSCRIPTION")
        
        try:
            from screenshot_tool.ui.upgrade_prompt import UpgradePromptDialog
            
            # 保存对话框引用，防止被垃圾回收
            self._upgrade_prompt_dialog = UpgradePromptDialog(
                feature_name=feature_name,
                reason=reason,
                usage_info=usage_info
            )
            async_debug_log(f"UpgradePromptDialog 创建成功", "SUBSCRIPTION")
            
            self._upgrade_prompt_dialog.upgrade_clicked.connect(self._on_upgrade_clicked)
            self._upgrade_prompt_dialog.login_clicked.connect(self._show_login_dialog)
            # 使用 show() 代替 exec()，避免阻塞热键
            self._upgrade_prompt_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._upgrade_prompt_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._upgrade_prompt_dialog.show()
            self._upgrade_prompt_dialog.activateWindow()
            self._upgrade_prompt_dialog.raise_()
            
            async_debug_log(f"UpgradePromptDialog 已显示: visible={self._upgrade_prompt_dialog.isVisible()}", "SUBSCRIPTION")
        except Exception as e:
            import traceback
            async_debug_log(f"_show_upgrade_prompt 异常: {e}\n{traceback.format_exc()}", "SUBSCRIPTION")
    
    def _on_upgrade_clicked(self):
        """点击升级按钮
        
        Feature: subscription-system
        """
        # TODO: 打开升级页面或显示赞助信息
        import webbrowser
        # 可以替换为实际的赞助页面
        webbrowser.open("https://github.com/your-repo/screenshot-tool#upgrade")
    
    def _check_feature_access(self, feature_name: str, feature_enum) -> bool:
        """检查功能访问权限
        
        Feature: subscription-system
        Requirements: 4.2, 4.3, 4.4, 4.5
        
        Args:
            feature_name: 功能显示名称
            feature_enum: Feature 枚举值
            
        Returns:
            bool: 是否允许访问
        """
        async_debug_log(f"_check_feature_access: {feature_name}, manager={self._subscription_manager}", "SUBSCRIPTION")
        
        if not self._subscription_manager or not self._subscription_manager.is_initialized:
            async_debug_log(f"订阅管理器未初始化，默认允许", "SUBSCRIPTION")
            return True  # 未初始化时默认允许
        
        result = self._subscription_manager.check_access(feature_enum)
        async_debug_log(f"check_access 结果: allowed={result.allowed}, reason={result.reason}", "SUBSCRIPTION")
        
        if not result.allowed:
            # 获取使用量信息
            usage_info = None
            status = self._subscription_manager.get_feature_status(feature_enum)
            if status.get("is_limited"):
                usage_info = {
                    "usage": status.get("usage", 0),
                    "limit": status.get("limit", 0),
                    "remaining": status.get("remaining", 0),
                }
            
            async_debug_log(f"显示升级提示: {feature_name}", "SUBSCRIPTION")
            self._show_upgrade_prompt(feature_name, result.reason, usage_info)
            return False
        
        return True
    
    def _use_feature(self, feature_name: str, feature_enum) -> bool:
        """使用功能（检查权限并增加使用量）
        
        Feature: subscription-system
        Requirements: 4.5
        
        Args:
            feature_name: 功能显示名称
            feature_enum: Feature 枚举值
            
        Returns:
            bool: 是否允许使用
        """
        if not self._subscription_manager or not self._subscription_manager.is_initialized:
            return True
        
        result = self._subscription_manager.use_feature(feature_enum)
        
        if not result.allowed:
            usage_info = None
            status = self._subscription_manager.get_feature_status(feature_enum)
            if status.get("is_limited"):
                usage_info = {
                    "usage": status.get("usage", 0),
                    "limit": status.get("limit", 0),
                    "remaining": status.get("remaining", 0),
                }
            
            self._show_upgrade_prompt(feature_name, result.reason, usage_info)
            return False
        
        return True
        
    def _quit(self):
        """退出应用"""
        # 保存工作台（立即保存，确保数据不丢失）
        # Feature: clipboard-history
        if self._clipboard_history_manager:
            try:
                self._clipboard_history_manager.stop_monitoring()
                self._clipboard_history_manager.save(immediate=True)
            except Exception:
                pass
        
        # 停止后台 OCR 缓存管理器（旧版本，保留兼容性）
        # Feature: background-ocr-cache
        if self._background_ocr_cache_manager:
            try:
                self._background_ocr_cache_manager.cleanup()
            except Exception:
                pass
        
        # 停止后台 OCR 缓存组件（新架构）
        # Feature: background-ocr-cache-python
        # Requirements: 5.4
        if self._background_ocr_cache_worker:
            try:
                self._background_ocr_cache_worker.cleanup()
            except Exception:
                pass
            self._background_ocr_cache_worker = None
        
        if self._system_idle_detector:
            try:
                self._system_idle_detector.cleanup()
            except Exception:
                pass
            self._system_idle_detector = None
        
        # 停止后台 OCR 防抖定时器
        if hasattr(self, '_background_ocr_debounce_timer') and self._background_ocr_debounce_timer:
            if self._background_ocr_debounce_timer.isActive():
                self._background_ocr_debounce_timer.stop()
        self._pending_background_ocr_image = None
        
        # 清理OCR工作线程
        self._cleanup_ocr_worker(timeout_ms=1000, force_terminate=True)
        
        # 等待所有孤儿线程完成（最多等待 2 秒）
        if self._orphan_threads:
            ocr_debug_log(f"退出时等待 {len(self._orphan_threads)} 个孤儿线程完成...")
            for thread in self._orphan_threads[:]:  # 使用切片复制列表
                try:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait(500)  # 每个线程最多等待 500ms
                except RuntimeError:
                    pass
            self._orphan_threads.clear()
        
        # 清理自动OCR弹窗管理器
        if hasattr(self, '_auto_ocr_popup_manager') and self._auto_ocr_popup_manager:
            self._auto_ocr_popup_manager.cleanup()
            self._auto_ocr_popup_manager = None
        
        # 清理分屏窗口
        # Feature: screenshot-ocr-split-view
        # Requirements: 7.3
        if hasattr(self, '_split_window') and self._split_window:
            try:
                self._split_window.close()
            except RuntimeError:
                pass  # 窗口可能已被销毁
            self._split_window = None
        
        # Note: _standalone_ocr_window 已移除，OCR 功能已集成到工作台窗口
        # Feature: clipboard-ocr-merge, Requirements: 7.1
        
        # 清理最近的 OCR 结果缓存
        self._last_ocr_result = None
        self._last_ocr_image = None
        
        # 清理公文模式管理器
        if hasattr(self, '_gongwen_mode_manager') and self._gongwen_mode_manager:
            self._gongwen_mode_manager.cleanup()
            self._gongwen_mode_manager = None
        
        # 清理 Markdown 模式管理器
        if hasattr(self, '_markdown_mode_manager') and self._markdown_mode_manager:
            try:
                self._markdown_mode_manager.cleanup()
            except Exception:
                pass
            self._markdown_mode_manager = None
        
        # 清理 Markdown 转换器
        if hasattr(self, '_markdown_converter'):
            self._markdown_converter = None
        
        # 清理 Markdown 转换工作线程和队列
        if hasattr(self, '_markdown_worker') and self._markdown_worker:
            if self._markdown_worker.isRunning():
                self._markdown_worker.quit()
                self._markdown_worker.wait(1000)
            self._markdown_worker.deleteLater()
            self._markdown_worker = None
        if hasattr(self, '_markdown_url_queue'):
            self._markdown_url_queue.clear()

        # 清理录屏组件
        if self._is_recording and self._screen_recorder:
            self._screen_recorder.cancel_recording()
        if self._recording_overlay_manager:
            self._recording_overlay_manager.stop()
            self._recording_overlay_manager = None
        self._screen_recorder = None
        self._is_recording = False
        
        # 清理鼠标高亮管理器
        # Feature: mouse-highlight
        self._unregister_spotlight_hotkey()
        if self._mouse_highlight_manager:
            self._mouse_highlight_manager.cleanup()
            self._mouse_highlight_manager = None

        # 清理所有贴图窗口
        if self._ding_manager:
            self._ding_manager.close_all()
            self._ding_manager = None

        # 清理热键
        if hasattr(self, '_hotkey_manager') and self._hotkey_manager:
            self._hotkey_manager.cleanup()
            self._hotkey_manager = None
        
        # 清理覆盖层
        if self._overlay:
            self._overlay.cleanup()
            self._overlay = None
        
        # 停止内存管理器
        # Feature: performance-ui-optimization
        # Requirements: 4.3, 4.4
        if hasattr(self, '_memory_manager') and self._memory_manager:
            self._memory_manager.stop()
            async_debug_log("内存管理器已停止", "MEMORY")
            self._memory_manager = None
        
        if self._tray:
            self._tray.hide()
            self._tray = None
        self._app.quit()
        
    def run(self) -> int:
        """运行应用"""
        # 根据配置决定是否在启动时显示主界面
        # Feature: main-window
        if self._main_window and self._config_manager.config.main_window.show_on_startup:
            # 使用 QTimer 延迟显示，确保托盘图标先初始化完成
            QTimer.singleShot(100, self._show_main_window)
        
        # 显示托盘提示
        if self._tray and self._config_manager.config.notification.startup:
            hotkey_modifier = self._config_manager.config.hotkey.screenshot_modifier
            hotkey_key = self._config_manager.config.hotkey.screenshot_key
            hotkey_display = f"{hotkey_modifier.title()}+{hotkey_key.upper()}"
            
            # Feature: auto-restart-update
            # Requirements: 3.2
            # 如果是从更新启动，显示更新成功通知
            if getattr(self, '_pending_update_success_notification', False):
                self._tray.showMessage(
                    f"{__app_name__} 更新成功",
                    f"已更新到 v{__version__}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                self._tray.showMessage(
                    f"{__app_name__} v{__version__} 已启动",
                    f"按 {hotkey_display} 开始截图，或点击托盘图标",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        return self._app.exec()


def main():
    """主函数"""
    app = OverlayScreenshotApp(sys.argv)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
