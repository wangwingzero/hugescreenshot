# =====================================================
# =============== 系统级空闲检测器 ===============
# =====================================================

"""
系统级空闲检测器 - 使用 Windows GetLastInputInfo API 检测系统空闲状态

与应用内的 IdleDetector 不同，这个检测的是系统级输入（键盘、鼠标等），
而不是应用内活动。用于后台 OCR 缓存功能，在系统空闲时自动处理历史图片。

Requirements:
- Requirement 1.1: 使用 Windows GetLastInputInfo API 检测系统级空闲时间
- Requirement 1.5: 正确处理 49.7 天 tick count 溢出问题

参考：
- MSDN GetLastInputInfo: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo
- MSDN GetTickCount: https://docs.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-gettickcount
"""

import ctypes
from ctypes import wintypes
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

# ========== 异步调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log


def idle_debug_log(message: str):
    """空闲检测器调试日志（使用异步日志器）"""
    async_debug_log(message, "IDLE")


# ========== Windows API 结构定义 ==========

class LASTINPUTINFO(ctypes.Structure):
    """Windows LASTINPUTINFO 结构
    
    用于 GetLastInputInfo API，获取最后一次用户输入的时间戳。
    
    Fields:
        cbSize: 结构体大小（字节），必须在调用前设置为 sizeof(LASTINPUTINFO)
        dwTime: 最后一次输入的系统 tick count（32位无符号整数）
    
    注意：dwTime 是 DWORD 类型（32位无符号），会在系统运行约 49.7 天后溢出。
    """
    _fields_ = [
        ("cbSize", wintypes.UINT),   # 结构体大小
        ("dwTime", wintypes.DWORD),  # 最后输入时间（tick count）
    ]


# ========== 系统级空闲检测器 ==========

class SystemIdleDetector(QObject):
    """系统级空闲检测器
    
    使用 Windows GetLastInputInfo API 检测系统空闲状态。
    与现有的 IdleDetector 不同，这个检测的是系统级输入，
    而不是应用内活动。
    
    Requirement 1.1, 1.2, 1.3, 1.4, 1.5
    
    Signals:
        idle_started: 进入空闲状态时发出
        idle_ended: 退出空闲状态时发出
    
    Usage:
        detector = SystemIdleDetector()
        detector.idle_started.connect(on_idle_started)
        detector.idle_ended.connect(on_idle_ended)
        detector.start_monitoring()
    """
    
    # 信号
    idle_started = Signal()  # 进入空闲状态
    idle_ended = Signal()    # 退出空闲状态
    
    # 常量
    DEFAULT_CHECK_INTERVAL_MS = 5000   # 正常检查间隔 5 秒
    FAST_CHECK_INTERVAL_MS = 100       # 空闲状态下快速检查间隔
    DEFAULT_IDLE_THRESHOLD_MS = 60000  # 空闲阈值 60 秒
    
    # 32位无符号整数最大值，用于溢出处理
    _UINT32_MAX = 0xFFFFFFFF
    
    def __init__(self, parent: Optional[QObject] = None):
        """初始化检测器
        
        Args:
            parent: 父 QObject，用于 Qt 对象树管理
        """
        super().__init__(parent)
        
        # 状态
        self._is_idle = False
        self._is_monitoring = False
        self._idle_threshold_ms = self.DEFAULT_IDLE_THRESHOLD_MS
        
        # 定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_idle_status)
        
        # Windows API 函数引用
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        
        idle_debug_log("SystemIdleDetector 初始化完成")
    
    def start_monitoring(self, interval_ms: int = None) -> None:
        """开始监控空闲状态
        
        Args:
            interval_ms: 检查间隔（毫秒），默认为 DEFAULT_CHECK_INTERVAL_MS
        
        Requirement 1.2: 使用 QTimer 每 5 秒检查一次
        """
        if self._is_monitoring:
            idle_debug_log("已在监控中，忽略重复启动")
            return
        
        if interval_ms is None:
            interval_ms = self.DEFAULT_CHECK_INTERVAL_MS
        
        self._is_monitoring = True
        self._is_idle = False
        self._timer.start(interval_ms)
        
        idle_debug_log(f"开始监控空闲状态，间隔: {interval_ms}ms，阈值: {self._idle_threshold_ms}ms")
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        if not self._is_monitoring:
            return
        
        self._is_monitoring = False
        self._timer.stop()
        
        # 如果当前处于空闲状态，发出结束信号
        if self._is_idle:
            self._is_idle = False
            self.idle_ended.emit()
        
        idle_debug_log("停止监控空闲状态")
    
    def set_idle_threshold(self, threshold_ms: int) -> None:
        """设置空闲阈值
        
        Args:
            threshold_ms: 空闲阈值（毫秒），超过此时间视为空闲
        """
        if threshold_ms <= 0:
            idle_debug_log(f"无效的空闲阈值: {threshold_ms}，忽略")
            return
        
        self._idle_threshold_ms = threshold_ms
        idle_debug_log(f"空闲阈值设置为: {threshold_ms}ms")
    
    def get_idle_time_ms(self) -> int:
        """获取当前空闲时间（毫秒）
        
        使用 Windows GetLastInputInfo API 获取最后一次用户输入的时间，
        然后计算与当前时间的差值。
        
        处理 49.7 天溢出问题：
        - GetTickCount 和 LASTINPUTINFO.dwTime 都是 32 位无符号整数
        - 系统运行约 49.7 天后会溢出（从 0xFFFFFFFF 回到 0）
        - 使用 & 0xFFFFFFFF 掩码确保正确的无符号减法
        
        Requirement 1.1: 使用 Windows GetLastInputInfo API
        Requirement 1.5: 处理 49.7 天 tick count 溢出
        
        Returns:
            int: 空闲时间（毫秒），如果 API 调用失败返回 0
        """
        # 创建 LASTINPUTINFO 结构
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        
        # 调用 GetLastInputInfo API
        if not self._user32.GetLastInputInfo(ctypes.byref(lii)):
            idle_debug_log("GetLastInputInfo API 调用失败")
            return 0
        
        # 获取当前系统 tick count
        # 注意：必须使用 GetTickCount（32位）而不是 GetTickCount64（64位）
        # 因为 LASTINPUTINFO.dwTime 是 32 位的，两者必须保持一致
        current_tick = self._kernel32.GetTickCount()
        
        # 处理溢出的关键：
        # Python 的 int 是无限精度的，直接减可能会得到负数
        # 使用 & 0xFFFFFFFF 模拟 32 位无符号整数的回绕行为
        # 
        # 例如：
        # - last_input_tick = 0xFFFFFFF0（即将溢出）
        # - current_tick = 0x00000005（已溢出）
        # - (0x00000005 - 0xFFFFFFF0) & 0xFFFFFFFF = 21（正确的差值）
        idle_ms = (current_tick - lii.dwTime) & self._UINT32_MAX
        
        return idle_ms
    
    def is_idle(self) -> bool:
        """检查当前是否处于空闲状态
        
        Returns:
            bool: True 表示当前处于空闲状态
        """
        return self._is_idle
    
    def is_monitoring(self) -> bool:
        """检查是否正在监控
        
        Returns:
            bool: True 表示正在监控
        """
        return self._is_monitoring
    
    def _check_idle_status(self) -> None:
        """检查空闲状态（定时器回调）
        
        Requirement 1.3: 空闲时间超过阈值时发出 idle_started 信号
        Requirement 1.4: 用户活动后发出 idle_ended 信号
        """
        idle_time = self.get_idle_time_ms()
        was_idle = self._is_idle
        
        # 判断是否空闲
        is_now_idle = idle_time >= self._idle_threshold_ms
        
        if is_now_idle and not was_idle:
            # 进入空闲状态
            self._is_idle = True
            idle_debug_log(f"进入空闲状态，空闲时间: {idle_time}ms")
            
            # 切换到快速检测模式，以便快速响应用户活动
            self._timer.setInterval(self.FAST_CHECK_INTERVAL_MS)
            
            self.idle_started.emit()
            
        elif not is_now_idle and was_idle:
            # 退出空闲状态
            self._is_idle = False
            idle_debug_log(f"退出空闲状态，空闲时间: {idle_time}ms")
            
            # 切换回正常检测间隔
            self._timer.setInterval(self.DEFAULT_CHECK_INTERVAL_MS)
            
            self.idle_ended.emit()
    
    def cleanup(self) -> None:
        """清理资源
        
        在应用退出时调用，确保定时器停止。
        """
        self.stop_monitoring()
        idle_debug_log("SystemIdleDetector 资源已清理")
