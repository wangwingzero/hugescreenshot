# =====================================================
# =============== 窗口检测器 ===============
# =====================================================

"""
WindowDetector - 窗口智能识别

功能：
- 检测鼠标位置下的窗口边界
- 支持子控件级别检测
- 位置缓存优化性能
- 排除自身窗口（全屏透明覆盖层）

Requirements: 1.1, 1.4, 2.1, 2.2, 5.2, 5.3
"""

import time
from dataclasses import dataclass
from typing import Optional, Tuple, List

from PySide6.QtCore import QRect

# 尝试导入 pywin32，如果不可用则禁用窗口检测
try:
    import win32gui
    import win32con
    import ctypes
    from ctypes import wintypes
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as debug_log
except ImportError:
    def debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


@dataclass
class DetectionResult:
    """窗口检测结果
    
    Attributes:
        rect: 窗口边界矩形（屏幕坐标），None 表示未检测到
        hwnd: 窗口句柄，0 表示无效
        is_control: 是否为子控件（而非顶层窗口）
    """
    rect: Optional[QRect]
    hwnd: int
    is_control: bool
    
    @staticmethod
    def empty() -> 'DetectionResult':
        """创建空结果"""
        return DetectionResult(rect=None, hwnd=0, is_control=False)


class WindowDetector:
    """窗口检测器 - 检测鼠标位置下的窗口边界
    
    使用 Windows API 检测鼠标下方的窗口和控件，
    支持缓存优化和自身窗口排除。
    
    核心策略：
    - 遍历所有顶层窗口（Z-order 从前到后）
    - 找到第一个包含鼠标点且不是自身的可见窗口
    - 支持子控件级别检测
    
    Requirements: 1.1, 1.4, 2.1, 2.2, 5.2, 5.3
    """
    
    # ChildWindowFromPointEx 标志
    CWP_SKIPINVISIBLE = 1   # 跳过不可见窗口
    CWP_SKIPDISABLED = 2    # 跳过禁用窗口
    CWP_SKIPTRANSPARENT = 4 # 跳过透明窗口
    CWP_FLAGS = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED  # 不跳过透明，因为很多窗口有透明边框
    
    # 递归深度限制，防止栈溢出
    MAX_CHILD_DEPTH = 10
    
    # EnumWindows 最大遍历窗口数，防止死循环
    MAX_ENUM_WINDOWS = 50  # 减少遍历数量，加快响应速度
    
    # 检测超时时间（秒）
    DETECTION_TIMEOUT = 0.1  # 100ms 超时
    
    def __init__(self):
        """初始化窗口检测器"""
        self._enabled: bool = True
        self._last_pos: Optional[Tuple[int, int]] = None
        self._cached_result: Optional[DetectionResult] = None
        self._own_hwnd: int = 0  # 自身窗口句柄，用于排除
        self._desktop_hwnd: int = 0  # 桌面窗口句柄
        
        # 初始化桌面窗口句柄
        if PYWIN32_AVAILABLE:
            try:
                self._desktop_hwnd = win32gui.GetDesktopWindow()
            except Exception as e:
                debug_log(f"获取桌面窗口句柄失败: {e}", "WINDOW")
    
    def set_own_hwnd(self, hwnd: int) -> None:
        """设置自身窗口句柄（用于排除检测）
        
        Args:
            hwnd: 自身窗口的句柄
        """
        self._own_hwnd = hwnd
        debug_log(f"设置自身窗口句柄: {hwnd}", "INFO")
    
    def detect_at(self, screen_x: int, screen_y: int) -> Optional[DetectionResult]:
        """检测指定屏幕坐标下的窗口
        
        Args:
            screen_x: 屏幕 X 坐标
            screen_y: 屏幕 Y 坐标
            
        Returns:
            DetectionResult 或 None（如果禁用或未检测到窗口）
            
        Requirements: 1.1, 1.4, 2.1, 2.2, 5.2, 5.3
        """
        # 检查是否启用
        if not self._enabled:
            return None
        
        # 检查 pywin32 是否可用
        if not PYWIN32_AVAILABLE:
            return None
        
        # 检查缓存 - 位置未变则返回缓存结果
        pos = (screen_x, screen_y)
        if self._last_pos == pos and self._cached_result is not None:
            return self._cached_result
        
        # 更新位置
        self._last_pos = pos
        
        try:
            result = self._detect_window(screen_x, screen_y)
            self._cached_result = result
            return result
        except Exception as e:
            debug_log(f"窗口检测异常: {e}", "WINDOW")
            # 出错时返回缓存结果
            return self._cached_result
    
    def _detect_window(self, screen_x: int, screen_y: int) -> Optional[DetectionResult]:
        """执行实际的窗口检测
        
        使用 EnumWindows 遍历所有顶层窗口，按 Z-order 找到第一个
        包含鼠标点且不是自身的可见窗口。
        
        添加超时保护，避免长时间阻塞导致系统卡死。
        
        Args:
            screen_x: 屏幕 X 坐标
            screen_y: 屏幕 Y 坐标
            
        Returns:
            DetectionResult 或 None
        """
        start_time = time.time()
        
        point = (screen_x, screen_y)
        
        # 收集所有符合条件的窗口（带超时检查）
        try:
            found_hwnd = self._find_window_at_point(point)
        except Exception as e:
            debug_log(f"窗口查找异常: {e}", "WINDOW")
            return DetectionResult.empty()
        
        # 检查超时
        if time.time() - start_time > self.DETECTION_TIMEOUT:
            debug_log("窗口检测超时，返回空结果", "WINDOW")
            return DetectionResult.empty()
        
        if found_hwnd == 0:
            return DetectionResult.empty()
        
        # 尝试获取更深层的子控件（带超时检查）
        is_control = False
        if time.time() - start_time < self.DETECTION_TIMEOUT:
            try:
                child_hwnd = self._get_deepest_child(found_hwnd, point)
                
                if child_hwnd != 0 and child_hwnd != found_hwnd:
                    # 检查子控件是否有有效的边界
                    child_rect = self._get_window_rect(child_hwnd)
                    if child_rect is not None and not child_rect.isEmpty():
                        found_hwnd = child_hwnd
                        is_control = True
            except Exception as e:
                debug_log(f"子控件检测异常: {e}", "WINDOW")
        
        # 获取窗口边界
        rect = self._get_window_rect(found_hwnd)
        
        if rect is None or rect.isEmpty():
            return DetectionResult.empty()
        
        return DetectionResult(rect=rect, hwnd=found_hwnd, is_control=is_control)
    
    def _find_window_at_point(self, point: Tuple[int, int]) -> int:
        """找到指定点下的窗口（排除自身）
        
        策略：
        1. 首先尝试使用 WindowFromPoint 获取顶层窗口
        2. 如果是自身窗口，则遍历所有窗口找到下一个包含该点的窗口
        
        Args:
            point: 屏幕坐标点 (x, y)
            
        Returns:
            窗口句柄，如果没找到返回 0
        """
        # 首先尝试 WindowFromPoint
        hwnd = win32gui.WindowFromPoint(point)
        
        if hwnd == 0:
            debug_log(f"WindowFromPoint({point}) 返回 0", "WINDOW")
            return 0
        
        # 如果不是自身窗口且不是桌面，直接返回
        if hwnd != self._own_hwnd and hwnd != self._desktop_hwnd:
            # 检查是否可见
            if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
                return hwnd
            else:
                debug_log(f"窗口 {hwnd} 不可见或最小化", "WINDOW")
        
        # 如果是自身窗口或桌面，需要遍历找到下一个窗口
        debug_log(f"WindowFromPoint 返回自身({self._own_hwnd})或桌面({self._desktop_hwnd})，开始遍历", "WINDOW")
        result = [0]
        enum_count = [0]  # 遍历计数器，防止死循环
        own_hwnd = self._own_hwnd
        desktop_hwnd = self._desktop_hwnd
        max_enum = self.MAX_ENUM_WINDOWS
        
        def enum_callback(hwnd, _):
            # 检查遍历次数，防止死循环
            enum_count[0] += 1
            if enum_count[0] > max_enum:
                debug_log(f"EnumWindows 达到最大遍历次数 {max_enum}，停止", "WINDOW")
                return False  # 停止枚举
            
            try:
                # 跳过自身窗口
                if hwnd == own_hwnd:
                    return True
                
                # 跳过桌面窗口
                if hwnd == desktop_hwnd:
                    return True
                
                # 跳过不可见窗口
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                # 跳过最小化窗口
                if win32gui.IsIconic(hwnd):
                    return True
                
                # 获取窗口边界
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                # 检查点是否在窗口内
                if left <= point[0] < right and top <= point[1] < bottom:
                    result[0] = hwnd
                    return False  # 停止枚举
            except Exception:
                pass
            
            return True
        
        try:
            win32gui.EnumWindows(enum_callback, None)
        except Exception:
            # EnumWindows 在回调返回 False 时会抛出异常
            pass
        
        if result[0] != 0:
            debug_log(f"EnumWindows 找到窗口: {result[0]} (遍历了 {enum_count[0]} 个窗口)", "WINDOW")
        
        return result[0]
    
    def _get_deepest_child(self, parent_hwnd: int, point: Tuple[int, int], depth: int = 0) -> int:
        """递归获取最深层的子控件
        
        Args:
            parent_hwnd: 父窗口句柄
            point: 屏幕坐标点
            depth: 当前递归深度
            
        Returns:
            最深层子控件的句柄，如果没有则返回 0
            
        Requirements: 2.1, 2.2
        """
        # 防止栈溢出
        if depth >= self.MAX_CHILD_DEPTH:
            return 0
        
        try:
            # 将屏幕坐标转换为客户区坐标
            client_point = win32gui.ScreenToClient(parent_hwnd, point)
            
            # 获取子控件
            child_hwnd = win32gui.ChildWindowFromPointEx(
                parent_hwnd, 
                client_point, 
                self.CWP_FLAGS
            )
            
            # 如果没有子控件或子控件就是父窗口本身
            if child_hwnd == 0 or child_hwnd == parent_hwnd:
                return 0
            
            # 递归检测更深层的子控件
            deeper_child = self._get_deepest_child(child_hwnd, point, depth + 1)
            
            if deeper_child != 0:
                return deeper_child
            
            return child_hwnd
            
        except Exception as e:
            debug_log(f"获取子控件失败: {e}", "WINDOW")
            return 0
    
    def _get_window_rect(self, hwnd: int) -> Optional[QRect]:
        """获取窗口边界矩形
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            QRect 或 None
        """
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return None
            
            return QRect(left, top, width, height)
            
        except Exception as e:
            debug_log(f"获取窗口边界失败: {e}", "WINDOW")
            return None
    
    def toggle_enabled(self) -> bool:
        """切换启用状态
        
        Returns:
            新的启用状态
            
        Requirements: 4.1, 4.2
        """
        self._enabled = not self._enabled
        
        # 切换时清除缓存
        if not self._enabled:
            self.clear_cache()
        
        debug_log(f"窗口检测已{'启用' if self._enabled else '禁用'}", "WINDOW")
        return self._enabled
    
    def is_enabled(self) -> bool:
        """获取启用状态
        
        Returns:
            是否启用
        """
        return self._enabled
    
    def set_enabled(self, enabled: bool) -> None:
        """设置启用状态
        
        Args:
            enabled: 是否启用
        """
        self._enabled = enabled
        if not enabled:
            self.clear_cache()
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._last_pos = None
        self._cached_result = None


def is_window_detection_available() -> bool:
    """检查窗口检测功能是否可用
    
    Returns:
        True 如果 pywin32 可用
    """
    return PYWIN32_AVAILABLE


# 支持的文字处理软件窗口类名
# Microsoft Word: "OpusApp" (Word 2016/2019/2021/365)
# WPS Office: "KSOMAIN" (WPS 文字主窗口)
SUPPORTED_WORD_CLASSES = {"OpusApp", "KSOMAIN"}


def is_word_window(hwnd: int) -> bool:
    """检测窗口是否为 Microsoft Word 或 WPS 文字
    
    支持的软件：
    - Microsoft Word: 主窗口类名为 "OpusApp"（适用于 Word 2016/2019/2021/365）
    - WPS Office: 主窗口类名为 "KSOMAIN"
    
    Args:
        hwnd: 窗口句柄
        
    Returns:
        True 如果是 Word 或 WPS 窗口
        
    Requirements: 1.1, 1.2, 1.3
    """
    if not PYWIN32_AVAILABLE:
        return False
    
    # 检查无效句柄（0 或负数）
    if hwnd <= 0:
        return False
    
    try:
        class_name = win32gui.GetClassName(hwnd)
        return class_name in SUPPORTED_WORD_CLASSES
    except Exception:
        return False


@dataclass
class WordWindowInfo:
    """Word/WPS 窗口信息"""
    hwnd: int
    rect: QRect
    title: str


def get_all_word_windows() -> List[WordWindowInfo]:
    """获取所有可见的 Word/WPS 窗口信息
    
    Returns:
        Word/WPS 窗口信息列表
        
    Requirements: 1.1, 1.2
    """
    if not PYWIN32_AVAILABLE:
        return []
    
    word_windows = []
    
    def enum_callback(hwnd, _):
        try:
            # 跳过不可见窗口
            if not win32gui.IsWindowVisible(hwnd):
                return True
            
            # 跳过最小化窗口
            if win32gui.IsIconic(hwnd):
                return True
            
            # 检查是否为 Word/WPS 窗口
            class_name = win32gui.GetClassName(hwnd)
            if class_name in SUPPORTED_WORD_CLASSES:
                # 获取窗口边界
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = right - left
                height = bottom - top
                
                # 跳过无效矩形
                if width <= 0 or height <= 0:
                    return True
                
                rect = QRect(left, top, width, height)
                title = win32gui.GetWindowText(hwnd) or ""
                
                word_windows.append(WordWindowInfo(
                    hwnd=hwnd,
                    rect=rect,
                    title=title
                ))
                # 安全截取标题，避免空字符串问题
                display_title = title[:30] if title else "(无标题)"
                debug_log(f"发现 Word 窗口: hwnd={hwnd}, title={display_title}", "GONGWEN")
        except Exception as e:
            debug_log(f"枚举窗口失败: {e}", "GONGWEN")
        
        return True
    
    try:
        win32gui.EnumWindows(enum_callback, None)
    except Exception as e:
        debug_log(f"EnumWindows 失败: {e}", "GONGWEN")
    
    return word_windows
