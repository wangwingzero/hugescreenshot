# =====================================================
# =============== 错误日志记录器 ===============
# =====================================================

"""
错误日志记录器 - 负责捕获和记录程序异常

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
Property 2: 异常日志完整性
Property 3: 日志文件路径正确性
Property 4: 日志轮转
"""

import os
import sys
import threading
import traceback
from datetime import datetime
from typing import Optional, Callable, TextIO

# 日志文件大小限制（5MB）
MAX_LOG_SIZE = 5 * 1024 * 1024

# 日志保留天数
LOG_RETENTION_DAYS = 30

# 开发环境日志目录（仅用于开发调试）
DEV_LOG_DIR = r"D:\screenshot\日志\Python版本日志"


def get_log_dir() -> str:
    """
    获取日志目录
    
    - 打包环境: 用户数据目录 ~/.screenshot_tool
    - 开发环境: D:\screenshot\日志（方便调试）
    
    Feature: unified-data-storage-path
    Requirements: 4.1, 5.6
    
    Returns:
        日志目录路径
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 exe：使用统一的用户数据目录
        from screenshot_tool.core.config_manager import get_user_data_dir
        return get_user_data_dir()
    else:
        # 开发环境：使用项目日志目录（方便调试）
        return DEV_LOG_DIR


def get_app_dir() -> str:
    """
    获取应用目录（向后兼容，实际调用 get_log_dir）
    
    Returns:
        应用目录路径
    """
    return get_log_dir()


def get_log_filename(version: str) -> str:
    """
    获取日志文件名
    
    Args:
        version: 应用版本号
        
    Returns:
        日志文件名，格式: 虎哥截图{版本号}.log
    """
    return f"虎哥截图{version}.log"


def get_log_path(version: str, app_dir: Optional[str] = None) -> str:
    """
    获取日志文件完整路径
    
    Args:
        version: 应用版本号
        app_dir: 应用目录，默认自动检测
        
    Returns:
        日志文件完整路径
    """
    if app_dir is None:
        app_dir = get_app_dir()
    return os.path.join(app_dir, get_log_filename(version))


class ErrorLogger:
    """错误日志记录器"""
    
    def __init__(self, version: str, app_dir: Optional[str] = None):
        """
        初始化日志记录器
        
        Args:
            version: 应用版本号
            app_dir: 应用目录，默认自动检测
        """
        self._version = version
        self._app_dir = app_dir if app_dir else get_app_dir()
        self._log_path = get_log_path(version, self._app_dir)
        self._original_excepthook: Optional[Callable] = None
        # 打包环境默认启用详细日志，开发环境默认关闭
        self._debug_mode = getattr(sys, 'frozen', False)
        
        # 线程安全：使用可重入锁
        self._lock = threading.RLock()
        self._lock_timeout = 5.0  # 锁超时时间（秒）
        
        # 文件句柄管理：保持打开以便立即刷新
        self._file_handle: Optional[TextIO] = None
        
        # 确保目录存在
        self._ensure_dir()
    
    def set_debug_mode(self, enabled: bool) -> None:
        """
        设置详细日志模式
        
        Args:
            enabled: 是否启用详细日志
        """
        self._debug_mode = enabled
        if enabled:
            self.log_info("详细日志模式已启用")
    
    @property
    def debug_mode(self) -> bool:
        """获取详细日志模式状态"""
        return self._debug_mode
    
    def _ensure_dir(self) -> None:
        """确保日志目录存在"""
        log_dir = os.path.dirname(self._log_path)
        # 如果 log_dir 为空（日志在当前目录），则不需要创建
        if not log_dir:
            return
        
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                # 如果无法创建目录，回退到项目日志目录
                try:
                    os.makedirs(DEV_LOG_DIR, exist_ok=True)
                    self._app_dir = DEV_LOG_DIR
                    self._log_path = get_log_path(self._version, DEV_LOG_DIR)
                except OSError:
                    # 最后回退：使用临时目录
                    import tempfile
                    self._app_dir = tempfile.gettempdir()
                    self._log_path = get_log_path(self._version, self._app_dir)
    
    @property
    def log_path(self) -> str:
        """获取日志文件路径"""
        return self._log_path
    
    @property
    def version(self) -> str:
        """获取版本号"""
        return self._version
    
    def _rotate_if_needed(self) -> None:
        """检查并执行日志轮转（超过 5MB 时）"""
        if not os.path.exists(self._log_path):
            return
        
        try:
            file_size = os.path.getsize(self._log_path)
            if file_size >= MAX_LOG_SIZE:
                # 先关闭当前文件句柄
                if self._file_handle and not self._file_handle.closed:
                    self._file_handle.close()
                    self._file_handle = None
                
                # 轮转：重命名为 .log.1
                backup_path = self._log_path + ".1"
                # 如果备份文件已存在，删除它
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(self._log_path, backup_path)
        except OSError:
            pass  # 忽略轮转错误
    
    def _ensure_file_open(self) -> None:
        """确保文件句柄打开，使用行缓冲模式"""
        if self._file_handle is None or self._file_handle.closed:
            self._rotate_if_needed()
            try:
                self._file_handle = open(
                    self._log_path, 'a',
                    encoding='utf-8',
                    buffering=1  # 行缓冲模式
                )
            except OSError:
                # 如果打开失败，尝试回退到项目日志目录
                try:
                    os.makedirs(DEV_LOG_DIR, exist_ok=True)
                    self._log_path = get_log_path(self._version, DEV_LOG_DIR)
                    self._file_handle = open(
                        self._log_path, 'a',
                        encoding='utf-8',
                        buffering=1
                    )
                except OSError:
                    pass  # 静默失败
    
    def close(self) -> None:
        """安全关闭文件句柄"""
        acquired = self._lock.acquire(timeout=self._lock_timeout)
        try:
            if self._file_handle and not self._file_handle.closed:
                try:
                    self._file_handle.flush()
                    os.fsync(self._file_handle.fileno())
                except OSError:
                    pass
                finally:
                    self._file_handle.close()
                    self._file_handle = None
        finally:
            if acquired:
                self._lock.release()
    
    def _write_log(self, content: str) -> None:
        """
        线程安全的日志写入，立即刷新到磁盘
        
        Args:
            content: 日志内容
        """
        acquired = self._lock.acquire(timeout=self._lock_timeout)
        try:
            self._ensure_file_open()
            if self._file_handle and not self._file_handle.closed:
                self._file_handle.write(content)
                self._file_handle.flush()
                try:
                    os.fsync(self._file_handle.fileno())  # 强制写入磁盘
                except OSError:
                    pass  # fsync 失败时静默继续
        except OSError as e:
            # 写入失败时尝试输出到 stderr
            print(f"[ErrorLogger] 写入日志失败: {e}", file=sys.stderr)
        finally:
            if acquired:
                self._lock.release()
    
    def _format_timestamp(self) -> str:
        """格式化当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def log_startup(self) -> None:
        """记录程序启动"""
        separator = "=" * 80
        content = f"""
{separator}
虎哥截图 v{self._version} 启动
时间: {self._format_timestamp()}
{separator}

"""
        self._write_log(content)
    
    def log_shutdown(self) -> None:
        """记录程序退出"""
        separator = "=" * 80
        content = f"""
{separator}
虎哥截图 v{self._version} 退出
时间: {self._format_timestamp()}
{separator}

"""
        self._write_log(content)
    
    def log_info(self, message: str) -> None:
        """
        记录信息日志
        
        Args:
            message: 日志消息
        """
        content = f"[{self._format_timestamp()}] [INFO] {message}\n"
        self._write_log(content)
    
    def log_debug(self, message: str) -> None:
        """
        记录调试日志（仅在详细日志模式下记录）
        
        Args:
            message: 日志消息
        """
        if not self._debug_mode:
            return
        content = f"[{self._format_timestamp()}] [DEBUG] {message}\n"
        self._write_log(content)
    
    def log_warning(self, message: str) -> None:
        """
        记录警告日志
        
        Args:
            message: 日志消息
        """
        content = f"[{self._format_timestamp()}] [WARNING] {message}\n"
        self._write_log(content)
    
    def log_error(self, message: str) -> None:
        """
        记录错误日志
        
        Args:
            message: 日志消息
        """
        content = f"[{self._format_timestamp()}] [ERROR] {message}\n"
        self._write_log(content)
    
    def log_exception(self, exc_type, exc_value, exc_tb) -> str:
        """
        记录异常
        
        Args:
            exc_type: 异常类型
            exc_value: 异常值
            exc_tb: 异常堆栈
            
        Returns:
            格式化的异常信息字符串
        """
        timestamp = self._format_timestamp()
        
        # 安全获取异常类型名称
        try:
            type_name = exc_type.__name__ if exc_type else 'Unknown'
        except (AttributeError, TypeError):
            type_name = str(exc_type) if exc_type else 'Unknown'
        
        # 安全格式化堆栈跟踪
        try:
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
            tb_str = "".join(tb_lines)
        except Exception:
            tb_str = f"无法格式化堆栈跟踪: {exc_value}"
        
        # 构建日志内容
        content = f"""[{timestamp}] [ERROR] 未处理的异常
类型: {type_name}
消息: {exc_value}
堆栈跟踪:
{tb_str}
"""
        self._write_log(content)
        
        return content
    
    def install_exception_handler(self) -> None:
        """安装全局异常处理器"""
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._exception_handler
    
    def uninstall_exception_handler(self) -> None:
        """卸载全局异常处理器"""
        if self._original_excepthook:
            sys.excepthook = self._original_excepthook
            self._original_excepthook = None
    
    def _exception_handler(self, exc_type, exc_value, exc_tb) -> None:
        """
        全局异常处理器
        
        Args:
            exc_type: 异常类型
            exc_value: 异常值
            exc_tb: 异常堆栈
        """
        # 记录异常
        self.log_exception(exc_type, exc_value, exc_tb)
        
        # 调用原始处理器
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_tb)
    
    def cleanup_old_logs(self) -> None:
        """清理超过保留天数的旧日志（包括轮转的备份文件）"""
        if not os.path.exists(self._app_dir):
            return
        
        try:
            now = datetime.now()
            for filename in os.listdir(self._app_dir):
                # 匹配所有旧版本日志和轮转备份
                # 格式: 虎哥截图*.log.1 或 虎哥截图*.log.old 等
                is_backup = (
                    filename.startswith("虎哥截图") and 
                    ".log" in filename and
                    (filename.endswith(".1") or 
                     filename.endswith(".old") or
                     filename.endswith(".bak"))
                )
                if is_backup:
                    filepath = os.path.join(self._app_dir, filename)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        age_days = (now - mtime).days
                        if age_days > LOG_RETENTION_DAYS:
                            os.remove(filepath)
                    except OSError:
                        pass
        except OSError:
            pass


# 全局实例
_error_logger: Optional[ErrorLogger] = None


def get_error_logger() -> Optional[ErrorLogger]:
    """获取全局错误日志记录器实例"""
    return _error_logger


def init_error_logger(version: str, app_dir: Optional[str] = None) -> ErrorLogger:
    """
    初始化全局错误日志记录器
    
    Args:
        version: 应用版本号
        app_dir: 应用目录，默认自动检测
        
    Returns:
        ErrorLogger 实例
    """
    global _error_logger
    _error_logger = ErrorLogger(version, app_dir)
    return _error_logger
