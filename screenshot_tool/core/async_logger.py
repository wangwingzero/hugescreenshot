# =====================================================
# =============== 异步调试日志器 ===============
# =====================================================

"""
异步调试日志器 - 无阻塞的日志记录

特性：
- 异步文件写入，不阻塞主线程
- 批量缓冲，减少IO操作
- 无阻塞日志轮转
"""

import os
import sys
import threading
import queue
import datetime
import atexit
from typing import Optional

# 防止递归调用的标志
_in_error_logger_call = threading.local()


class AsyncDebugLogger:
    """异步调试日志器"""
    
    BATCH_SIZE = 50  # 批量写入阈值
    FLUSH_INTERVAL = 1.0  # 刷新间隔（秒）
    MAX_LINES = 2000  # 最大保留行数
    
    _instance: Optional['AsyncDebugLogger'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls, log_dir: str = None, log_file: str = "screenshot_debug.log") -> 'AsyncDebugLogger':
        """获取单例实例"""
        with cls._lock:
            # 检查实例是否存在且仍在运行
            if cls._instance is None or not cls._instance._running:
                if log_dir is None:
                    # 优先使用环境变量
                    log_dir = os.environ.get("SCREENSHOT_DEBUG_LOG_DIR")
                    if not log_dir:
                        # 打包环境：使用 exe 所在目录
                        if getattr(sys, 'frozen', False):
                            log_dir = os.path.dirname(sys.executable)
                        else:
                            # 开发环境：使用项目日志目录
                            log_dir = r"D:\screenshot\日志\Python版本日志"
                cls._instance = cls(log_dir, log_file)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None
        return cls._instance
    
    def __init__(self, log_dir: str, log_file: str = "screenshot_debug.log"):
        """
        初始化异步日志器
        
        Args:
            log_dir: 日志目录
            log_file: 日志文件名
        """
        self._log_dir = log_dir
        self._log_file = log_file
        self._log_path = os.path.join(log_dir, log_file)
        
        # 消息队列（线程安全）
        self._queue: queue.Queue = queue.Queue()
        
        # 写入线程
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._writer_loop, 
            daemon=True, 
            name="AsyncLogger-Writer"
        )
        self._writer_thread.start()
        
        # 统计信息（用于测试）
        self._write_count = 0
        self._message_count = 0
        self._trim_counter = 0  # 裁剪计数器
        self._stats_lock = threading.Lock()
        
        # 注册退出时刷新（避免重复注册）
        self._atexit_registered = False
        try:
            atexit.register(self.shutdown)
            self._atexit_registered = True
        except Exception:
            pass
    
    def log(self, message: str, category: str = "INFO"):
        """
        记录日志（非阻塞）
        
        Args:
            message: 日志消息
            category: 日志类别
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = f"[{timestamp}] [{category}] {message}\n"
        
        # 放入队列（非阻塞）
        try:
            self._queue.put_nowait(entry)
            with self._stats_lock:
                self._message_count += 1
        except queue.Full:
            # 队列满时丢弃消息，不阻塞
            pass
    
    def _writer_loop(self):
        """后台写入线程"""
        buffer = []
        
        while self._running or not self._queue.empty():
            try:
                # 等待消息，带超时
                try:
                    entry = self._queue.get(timeout=self.FLUSH_INTERVAL)
                    buffer.append(entry)
                    self._queue.task_done()
                except queue.Empty:
                    pass
                
                # 批量获取更多消息
                while len(buffer) < self.BATCH_SIZE:
                    try:
                        entry = self._queue.get_nowait()
                        buffer.append(entry)
                        self._queue.task_done()
                    except queue.Empty:
                        break
                
                # 写入文件
                if buffer:
                    self._write_entries(buffer)
                    buffer.clear()
                    
            except Exception:
                # 写入失败不影响主程序
                buffer.clear()
    
    def _write_entries(self, entries: list):
        """批量写入文件"""
        try:
            # 确保目录存在
            os.makedirs(self._log_dir, exist_ok=True)
            
            # 批量写入
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.writelines(entries)
            
            # 每10次写入检查一次行数限制，避免频繁IO
            self._trim_counter += 1
            if self._trim_counter >= 10:
                self._trim_counter = 0
                self._trim_log_lines()
            
            # 更新统计
            with self._stats_lock:
                self._write_count += 1
                
        except Exception:
            pass  # 日志失败不影响主程序
    
    def _trim_log_lines(self):
        """限制日志文件行数，保留最新的 MAX_LINES 行"""
        try:
            if not os.path.exists(self._log_path):
                return
            
            # 先检查文件大小，避免读取过大文件
            file_size = os.path.getsize(self._log_path)
            # 假设平均每行100字节，超过阈值才需要裁剪
            if file_size < self.MAX_LINES * 100:
                return
            
            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            if len(lines) > self.MAX_LINES:
                # 保留最新的 MAX_LINES 行
                with open(self._log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines[-self.MAX_LINES:])
        except Exception:
            pass
    
    def flush(self):
        """强制刷新缓冲区"""
        # 等待队列清空
        self._queue.join()
    
    def shutdown(self):
        """关闭日志器"""
        if not self._running:
            return
        self._running = False
        self.flush()
        if self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
        # 尝试取消 atexit 注册
        if self._atexit_registered:
            try:
                atexit.unregister(self.shutdown)
            except Exception:
                pass
    
    def get_stats(self) -> dict:
        """获取统计信息（用于测试）"""
        with self._stats_lock:
            return {
                "message_count": self._message_count,
                "write_count": self._write_count
            }
    
    def reset_stats(self):
        """重置统计信息（用于测试）"""
        with self._stats_lock:
            self._message_count = 0
            self._write_count = 0
            self._trim_counter = 0


# 全局日志函数（兼容现有代码）
_logger: Optional[AsyncDebugLogger] = None
_enabled = os.environ.get("SCREENSHOT_DEBUG_ENABLED", "1") == "1"


def get_logger() -> AsyncDebugLogger:
    """获取全局日志器"""
    global _logger
    if _logger is None:
        _logger = AsyncDebugLogger.get_instance()
    return _logger


def async_debug_log(message: str, category: str = "INFO"):
    """
    异步调试日志（全局函数）
    
    Args:
        message: 日志消息
        category: 日志类别
    """
    if not _enabled:
        return
    get_logger().log(message, category)
    
    # 在打包环境下，同时写入到主日志文件
    # 使用线程本地变量防止递归调用
    if getattr(sys, 'frozen', False):
        # 检查是否已经在 error_logger 调用中，防止递归
        if getattr(_in_error_logger_call, 'active', False):
            return
        try:
            _in_error_logger_call.active = True
            from screenshot_tool.core.error_logger import get_error_logger
            error_logger = get_error_logger()
            if error_logger:
                error_logger.log_debug(f"[{category}] {message}")
        except Exception:
            pass  # 忽略错误，不影响主程序
        finally:
            _in_error_logger_call.active = False


def async_ocr_log(message: str):
    """OCR 调试日志"""
    async_debug_log(message, "OCR")


def async_paddle_log(message: str):
    """PaddleOCR 调试日志"""
    async_debug_log(message, "PADDLE")


def async_main_log(message: str):
    """主程序调试日志"""
    async_debug_log(message, "MAIN")
