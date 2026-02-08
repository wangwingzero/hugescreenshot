"""模态对话框检测器

检测 Windows 系统是否有模态对话框处于活动状态。
用于防止在模态对话框打开时触发截图热键导致应用卡死。

Feature: vip-realtime-unlock-modal-fix
Requirements: 2.1, 2.2, 3.1, 3.3, 3.4, 3.5
"""

import sys

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def modal_log(message: str):
    """模态对话框检测日志"""
    _debug_log(message, "MODAL")

# Windows API 常量
GW_OWNER = 4  # GetWindow: 获取所有者窗口
GWL_STYLE = -16  # GetWindowLong: 获取窗口样式
GWL_EXSTYLE = -20  # GetWindowLong: 获取扩展窗口样式
WS_DISABLED = 0x08000000  # 窗口被禁用
WS_EX_DLGMODALFRAME = 0x00000001  # 对话框模态框架
WS_EX_TOPMOST = 0x00000008  # 置顶窗口

# 常见的模态对话框类名
MODAL_DIALOG_CLASS_NAMES = {
    "#32770",  # Windows 标准对话框（包括文件选择对话框）
    "Dialog",
    "QDialog",
    "SunAwtDialog",  # Java 对话框
}


class ModalDialogDetector:
    """模态对话框检测器
    
    使用 Windows API 检测当前是否有模态对话框处于活动状态。
    
    检测原理（多重检测）：
    1. 检查 Qt 应用是否有活动的模态窗口（最可靠）
    2. 检查前台窗口是否是已知的模态对话框类名（如 #32770）
    3. 检查前台窗口的所有者窗口是否被禁用
    """
    
    @staticmethod
    def _check_qt_modal_widget() -> bool:
        """检查 Qt 应用是否有活动的模态窗口
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 3.1, 3.5
        
        Returns:
            True 如果有 Qt 模态窗口，False 否则
            
        Note:
            此方法可以从任何线程调用，但只有在主线程时才能正确检测。
            从非主线程调用时返回 False，依赖其他检测方法。
        """
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QThread
            
            app = QApplication.instance()
            if app is None:
                return False
            
            # 检查是否在主线程（Qt GUI 操作必须在主线程）
            if QThread.currentThread() != app.thread():
                # 非主线程，无法可靠检测 Qt 模态窗口
                # 返回 False，让其他检测方法处理
                return False
            
            # 检查是否有活动的模态窗口
            modal_widget = app.activeModalWidget()
            return modal_widget is not None
        except (ImportError, RuntimeError, AttributeError):
            return False
    
    @staticmethod
    def is_modal_dialog_active() -> bool:
        """检测是否有模态对话框处于活动状态
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 2.1, 3.1, 3.3, 3.4, 3.5
        
        Returns:
            True 如果检测到模态对话框，False 否则
            
        Note:
            - 非 Windows 平台始终返回 False
            - 检测失败时返回 False（fail-open 策略，Requirements: 3.4）
            - 设计为线程安全，可从任何线程调用（Requirements: 3.5）
        """
        # 方法0：检查 Qt 模态窗口（最可靠，跨平台）
        try:
            if ModalDialogDetector._check_qt_modal_widget():
                return True
        except Exception:
            # Qt 检测失败，继续其他检测方法（fail-open）
            pass
        
        # 非 Windows 平台直接返回 False
        if sys.platform != 'win32':
            return False
        
        try:
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            
            # 获取前台窗口
            foreground_hwnd = user32.GetForegroundWindow()
            if not foreground_hwnd:
                return False
            
            # 方法1：检查窗口类名是否是已知的模态对话框
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(foreground_hwnd, class_name, 256)
            if class_name.value in MODAL_DIALOG_CLASS_NAMES:
                return True
            
            # 方法2：检查所有者窗口是否被禁用
            owner_hwnd = user32.GetWindow(foreground_hwnd, GW_OWNER)
            if owner_hwnd:
                is_owner_enabled = user32.IsWindowEnabled(owner_hwnd)
                if not is_owner_enabled:
                    return True
            
            # 方法3：检查前台窗口是否有 WS_EX_DLGMODALFRAME 扩展样式
            ex_style = user32.GetWindowLongW(foreground_hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_DLGMODALFRAME:
                # 有模态框架样式，可能是模态对话框
                # 但需要进一步确认所有者窗口被禁用
                if owner_hwnd:
                    is_owner_enabled = user32.IsWindowEnabled(owner_hwnd)
                    if not is_owner_enabled:
                        return True
            
            return False
            
        except (ImportError, OSError, AttributeError):
            return False
        except Exception:
            return False
    
    @staticmethod
    def is_modal_dialog_active_verbose() -> tuple[bool, str]:
        """检测是否有模态对话框处于活动状态（带详细信息）
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 2.4, 3.1, 3.3
        
        Returns:
            (is_modal, reason): 是否有模态对话框，以及原因说明
        """
        # 方法0：检查 Qt 模态窗口
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                modal_widget = app.activeModalWidget()
                if modal_widget is not None:
                    widget_name = modal_widget.__class__.__name__
                    return True, f"Qt 模态窗口: {widget_name}"
        except (ImportError, RuntimeError):
            pass
        
        # 非 Windows 平台直接返回 False
        if sys.platform != 'win32':
            return False, "非 Windows 平台"
        
        try:
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            
            # 获取前台窗口
            foreground_hwnd = user32.GetForegroundWindow()
            if not foreground_hwnd:
                return False, "无前台窗口"
            
            # 获取窗口类名
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(foreground_hwnd, class_name, 256)
            class_name_str = class_name.value
            
            # 方法1：检查窗口类名
            if class_name_str in MODAL_DIALOG_CLASS_NAMES:
                return True, f"前台窗口类名 '{class_name_str}' 是已知的模态对话框类型"
            
            # 方法2：检查所有者窗口
            owner_hwnd = user32.GetWindow(foreground_hwnd, GW_OWNER)
            if owner_hwnd:
                is_owner_enabled = user32.IsWindowEnabled(owner_hwnd)
                if not is_owner_enabled:
                    return True, f"所有者窗口 {owner_hwnd} 被禁用，检测到模态对话框 (类名: {class_name_str})"
            
            # 方法3：检查扩展样式
            ex_style = user32.GetWindowLongW(foreground_hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_DLGMODALFRAME:
                if owner_hwnd:
                    is_owner_enabled = user32.IsWindowEnabled(owner_hwnd)
                    if not is_owner_enabled:
                        return True, f"窗口有模态框架样式且所有者被禁用 (类名: {class_name_str})"
            
            return False, f"未检测到模态对话框 (类名: {class_name_str}, 所有者: {owner_hwnd})"
            
        except (ImportError, OSError, AttributeError) as e:
            return False, f"检测失败: {e}"
        except Exception as e:
            return False, f"未知错误: {e}"
