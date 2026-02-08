# =====================================================
# =============== Anki 调试日志器 ===============
# =====================================================

"""
Anki 调试日志器 - 专门用于追踪 Anki 窗口相关问题

日志文件位置: 日志/anki_debug.log
"""

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# 日志文件最大大小 (1MB)
_MAX_LOG_SIZE = 1 * 1024 * 1024

# 缓存日志路径，避免重复计算
_cached_log_path: Optional[str] = None

# 轮转检查计数器，减少 IO 开销
# 注意：此计数器非线程安全，但仅用于减少检查频率，不影响正确性
_rotate_check_counter: int = 0


def get_anki_debug_log_path() -> str:
    """获取 Anki 调试日志文件路径
    
    Returns:
        日志文件的绝对路径
    """
    global _cached_log_path
    if _cached_log_path is not None:
        return _cached_log_path
    
    # 使用日志目录（相对于项目根目录）
    base_dir = Path(__file__).parent.parent.parent / "日志"
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # 如果无法创建目录，使用临时目录
        import tempfile
        base_dir = Path(tempfile.gettempdir())
    
    _cached_log_path = str(base_dir / "anki_debug.log")
    return _cached_log_path


def _check_and_rotate_log():
    """检查日志文件大小，超过限制时进行轮转"""
    try:
        log_path = get_anki_debug_log_path()
        if os.path.exists(log_path) and os.path.getsize(log_path) > _MAX_LOG_SIZE:
            # 重命名旧日志
            backup_path = log_path + ".old"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(log_path, backup_path)
    except OSError:
        pass  # 轮转失败不影响主程序


def anki_debug_log(message: str, tag: str = "ANKI"):
    """写入 Anki 调试日志
    
    Args:
        message: 日志消息
        tag: 日志标签
    """
    global _rotate_check_counter
    try:
        # 每 20 次写入检查一次轮转，减少 IO 开销
        _rotate_check_counter += 1
        if _rotate_check_counter >= 20:
            _rotate_check_counter = 0
            _check_and_rotate_log()
        
        log_path = get_anki_debug_log_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] [{tag}] {message}\n"
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass  # 日志失败不影响主程序


def anki_debug_exception(tag: str = "ANKI"):
    """记录当前异常的完整堆栈
    
    Args:
        tag: 日志标签
    """
    try:
        log_path = get_anki_debug_log_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        exc_info = traceback.format_exc()
        log_line = f"[{timestamp}] [{tag}] EXCEPTION:\n{exc_info}\n"
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def clear_anki_debug_log():
    """清空 Anki 调试日志"""
    try:
        log_path = get_anki_debug_log_path()
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== Anki 调试日志 - 启动于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
    except Exception:
        pass
