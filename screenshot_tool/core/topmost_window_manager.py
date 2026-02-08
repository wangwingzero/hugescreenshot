# -*- coding: utf-8 -*-
"""
全局置顶窗口管理器

跟踪所有使用 WindowStaysOnTopHint 的窗口，提供统一的 ESC 退出机制。
这是防止置顶窗口卡死系统的最后防线。

Feature: emergency-esc-exit
Requirements: 4.1, 4.2, 4.3, 4.4
"""

from typing import Optional, List
from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget, QApplication

from screenshot_tool.core.async_logger import async_debug_log as debug_log


@dataclass
class TopmostWindowInfo:
    """置顶窗口信息"""
    window: QWidget
    registered_at: float  # 注册时间戳
    window_type: str      # 窗口类型标识
    can_receive_focus: bool  # 是否能接收焦点


class TopmostWindowManager(QObject):
    """全局置顶窗口管理器
    
    单例模式，跟踪所有使用 WindowStaysOnTopHint 的窗口。
    提供统一的 ESC 退出机制作为最后防线。
    
    使用方法：
    1. 在置顶窗口的 __init__ 中调用 register_window()
    2. 在置顶窗口的 closeEvent 中调用 unregister_window()
    3. 外部可调用 close_topmost() 关闭最顶层窗口
    4. 紧急情况可调用 close_all() 关闭所有置顶窗口
    """
    
    _instance: Optional["TopmostWindowManager"] = None
    
    # 信号
    window_registered = Signal(QWidget)
    window_unregistered = Signal(QWidget)
    all_windows_closed = Signal()
    
    @classmethod
    def instance(cls) -> "TopmostWindowManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance._windows.clear()
            cls._instance = None
    
    def __init__(self):
        super().__init__()
        self._windows: List[TopmostWindowInfo] = []
        debug_log("TopmostWindowManager 初始化", "TOPMOST")
    
    def register_window(self, window: QWidget, window_type: str = "unknown", 
                       can_receive_focus: bool = True) -> None:
        """注册置顶窗口
        
        Args:
            window: 要注册的窗口
            window_type: 窗口类型标识（用于日志）
            can_receive_focus: 窗口是否能接收焦点
        """
        # 检查是否已注册
        for info in self._windows:
            if info.window is window:
                debug_log(f"窗口已注册，跳过: {window_type}", "TOPMOST")
                return
        
        info = TopmostWindowInfo(
            window=window,
            registered_at=time.time(),
            window_type=window_type,
            can_receive_focus=can_receive_focus
        )
        self._windows.append(info)
        debug_log(f"注册置顶窗口: {window_type}, 当前数量: {len(self._windows)}", "TOPMOST")
        self.window_registered.emit(window)
    
    def unregister_window(self, window: QWidget) -> None:
        """注销置顶窗口
        
        Args:
            window: 要注销的窗口
        """
        for i, info in enumerate(self._windows):
            if info.window is window:
                self._windows.pop(i)
                debug_log(f"注销置顶窗口: {info.window_type}, 剩余数量: {len(self._windows)}", "TOPMOST")
                self.window_unregistered.emit(window)
                if not self._windows:
                    self.all_windows_closed.emit()
                return
        debug_log(f"尝试注销未注册的窗口", "TOPMOST")
    
    def close_topmost(self) -> bool:
        """关闭最顶层的置顶窗口（后进先出）
        
        Returns:
            是否成功关闭了窗口
        """
        if not self._windows:
            debug_log("没有置顶窗口需要关闭", "TOPMOST")
            return False
        
        info = self._windows[-1]
        debug_log(f"尝试关闭最顶层窗口: {info.window_type}", "TOPMOST")
        
        try:
            window = info.window
            # 先尝试正常关闭
            window.close()
            return True
        except Exception as e:
            debug_log(f"关闭窗口失败: {e}, 尝试强制隐藏", "TOPMOST")
            try:
                # 强制隐藏并移除
                info.window.hide()
                self._windows.pop()
                return True
            except Exception as e2:
                debug_log(f"强制隐藏也失败: {e2}", "TOPMOST")
                # 最后手段：直接从列表移除
                self._windows.pop()
                return True
    
    def close_all(self) -> None:
        """关闭所有置顶窗口（紧急退出）
        
        按照后进先出的顺序关闭所有窗口。
        即使单个窗口关闭失败，也会继续关闭其他窗口。
        """
        debug_log(f"紧急关闭所有置顶窗口，数量: {len(self._windows)}", "TOPMOST")
        
        # 复制列表，避免迭代时修改
        windows_to_close = self._windows[:]
        
        for info in reversed(windows_to_close):
            try:
                info.window.close()
            except Exception as e:
                debug_log(f"关闭窗口 {info.window_type} 失败: {e}", "TOPMOST")
                try:
                    info.window.hide()
                except Exception:
                    pass
        
        self._windows.clear()
        debug_log("所有置顶窗口已关闭", "TOPMOST")
        self.all_windows_closed.emit()
        
        # 强制处理事件队列
        QApplication.processEvents()
    
    def has_active_overlays(self) -> bool:
        """是否有活动的置顶窗口"""
        return len(self._windows) > 0
    
    def get_window_count(self) -> int:
        """获取当前置顶窗口数量"""
        return len(self._windows)
    
    def get_topmost_window(self) -> Optional[QWidget]:
        """获取最顶层的置顶窗口"""
        if self._windows:
            return self._windows[-1].window
        return None
    
    def get_window_types(self) -> List[str]:
        """获取所有置顶窗口的类型列表"""
        return [info.window_type for info in self._windows]
