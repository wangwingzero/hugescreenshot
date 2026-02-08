# =====================================================
# =============== 崩溃处理器 ===============
# =====================================================

"""
崩溃处理器 - 捕获各种类型的程序崩溃

负责安装以下处理器：
1. Qt 消息处理器 - 捕获 Qt 层面的警告和错误
2. 信号处理器 - 捕获 SIGTERM/SIGINT 信号
3. atexit 处理器 - 程序正常退出时记录
4. aboutToQuit 处理器 - Qt 应用退出时记录

Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3
"""

import sys
import signal
import atexit
import threading
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from screenshot_tool.core.error_logger import ErrorLogger


class CrashHandler:
    """崩溃处理器 - 捕获各种类型的程序崩溃"""
    
    def __init__(self, error_logger: "ErrorLogger"):
        """
        初始化崩溃处理器
        
        Args:
            error_logger: 错误日志记录器实例
        """
        self._error_logger = error_logger
        self._original_qt_handler: Optional[Callable] = None
        self._installed = False
    
    @property
    def installed(self) -> bool:
        """是否已安装"""
        return self._installed
    
    def install(self, app: "QApplication") -> None:
        """
        安装所有崩溃处理器
        
        Args:
            app: QApplication 实例
        """
        if self._installed:
            return
        
        self._install_qt_handler()
        self._install_signal_handlers()
        self._install_atexit_handler()
        self._install_abouttoquit_handler(app)
        
        self._installed = True
        self._error_logger.log_info("[CrashHandler] 崩溃处理器已安装")
    
    def _install_qt_handler(self) -> None:
        """安装 Qt 消息处理器"""
        try:
            from PySide6.QtCore import qInstallMessageHandler, QtMsgType
            
            def qt_message_handler(mode, context, message):
                """Qt 消息处理器"""
                try:
                    # 级别映射
                    level_map = {
                        QtMsgType.QtDebugMsg: "DEBUG",
                        QtMsgType.QtInfoMsg: "INFO",
                        QtMsgType.QtWarningMsg: "WARNING",
                        QtMsgType.QtCriticalMsg: "CRITICAL",
                        QtMsgType.QtFatalMsg: "FATAL",
                    }
                    level = level_map.get(mode, "UNKNOWN")
                    
                    # 只记录 WARNING 及以上级别
                    if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                        log_msg = f"[Qt-{level}] {message}"
                        
                        # 添加上下文信息（如果有）
                        if context.file:
                            log_msg += f" ({context.file}:{context.line})"
                        
                        self._error_logger.log_warning(log_msg)
                        
                        # FATAL 级别时尝试刷新日志
                        if mode == QtMsgType.QtFatalMsg:
                            self._error_logger.close()
                except Exception:
                    pass  # 消息处理器内部出错时静默失败
                
                # 调用原始处理器（如果存在）
                if self._original_qt_handler:
                    try:
                        self._original_qt_handler(mode, context, message)
                    except Exception:
                        pass
            
            self._original_qt_handler = qInstallMessageHandler(qt_message_handler)
        except ImportError:
            pass  # PySide6 未安装时跳过
        except Exception as e:
            self._error_logger.log_warning(f"[CrashHandler] 安装 Qt 消息处理器失败: {e}")
    
    def _install_signal_handlers(self) -> None:
        """安装信号处理器"""
        # 只在主线程中安装
        if threading.current_thread() is not threading.main_thread():
            return
        
        def signal_handler(signum, frame):
            """信号处理器"""
            try:
                sig_name = signal.Signals(signum).name
                self._error_logger.log_error(f"[Signal] 收到信号: {sig_name} ({signum})")
                self._error_logger.close()
            except Exception:
                pass
            finally:
                sys.exit(128 + signum)
        
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except Exception as e:
            self._error_logger.log_warning(f"[CrashHandler] 安装信号处理器失败: {e}")
    
    def _install_atexit_handler(self) -> None:
        """安装 atexit 处理器"""
        def atexit_handler():
            """atexit 处理器"""
            try:
                self._error_logger.log_info("[atexit] 程序正在退出")
                self._error_logger.close()
            except Exception:
                pass
        
        atexit.register(atexit_handler)
    
    def _install_abouttoquit_handler(self, app: "QApplication") -> None:
        """
        安装 aboutToQuit 处理器
        
        Args:
            app: QApplication 实例
        """
        def abouttoquit_handler():
            """aboutToQuit 处理器"""
            try:
                self._error_logger.log_info("[aboutToQuit] Qt 应用即将退出")
            except Exception:
                pass
        
        try:
            app.aboutToQuit.connect(abouttoquit_handler)
        except Exception as e:
            self._error_logger.log_warning(f"[CrashHandler] 安装 aboutToQuit 处理器失败: {e}")
