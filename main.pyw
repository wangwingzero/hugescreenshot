#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
虎哥截图启动器
类似 Snipaste 的截图体验 - 直接在屏幕上操作
"""

import os
import sys
import platform
import traceback

# ========== 崩溃诊断（必须在最开始启用）==========
# 启用 faulthandler 来捕获 C 层面的崩溃（如 OpenVINO 段错误）
# 这样即使程序崩溃也能输出堆栈信息
# Bug fix (2026-01-23): 修复截图 OCR 时程序退出的问题
import faulthandler

# 尝试将崩溃信息写入日志文件（PyInstaller 打包后没有控制台）
_crash_log_path = None
try:
    _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "日志")
    os.makedirs(_log_dir, exist_ok=True)
    _crash_log_path = os.path.join(_log_dir, "crash_dump.log")
    _crash_log_file = open(_crash_log_path, "a", encoding="utf-8")
    faulthandler.enable(file=_crash_log_file)
except Exception:
    # 如果无法写入文件，回退到 stderr
    faulthandler.enable()

# ========== OpenVINO 多线程兼容性修复 ==========
# 设置 OMP_WAIT_POLICY=PASSIVE 避免 TBB/OpenMP 冲突
# 这可以防止 OpenVINO 在多线程环境下的静默崩溃
# Bug fix (2026-01-23): 修复截图 OCR 时程序退出的问题
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

# ========== 单实例锁（防止重复启动）==========
# 必须在最开始检查，避免重复初始化
_instance_lock = None

def _log_single_instance(message: str):
    """记录单实例检测日志（在 async_logger 初始化之前使用）"""
    import datetime
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "日志")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "screenshot_debug.log")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [SINGLE-INSTANCE] {message}\n")
    except Exception:
        pass  # 日志失败不影响程序运行

def _acquire_single_instance_lock():
    """获取单实例锁，如果已有实例运行则退出
    
    使用 Windows Mutex 实现单实例检测。
    如果 Mutex 创建失败或已存在，返回 False。
    """
    global _instance_lock
    
    if sys.platform != 'win32':
        return True
    
    import ctypes
    
    # 使用 Windows Mutex 实现单实例
    # 使用 Global\ 前缀确保跨会话互斥（与旧版本保持一致）
    # 注意：Mutex 名称必须与所有版本保持一致，否则无法检测旧版本
    MUTEX_NAME = "Global\\HuGeScreenshot_SingleInstance_Mutex"
    
    # Windows API
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    
    _log_single_instance(f"尝试创建 Mutex: {MUTEX_NAME}")
    
    # 创建 Mutex
    # 注意：即使 Mutex 已存在，CreateMutexW 也会返回有效句柄
    # 需要通过 GetLastError() 检查是否是 ERROR_ALREADY_EXISTS
    _instance_lock = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()  # 必须立即获取，否则可能被后续操作覆盖
    
    _log_single_instance(f"Mutex 句柄: {_instance_lock}, GetLastError: {last_error}")
    
    # 检查是否创建成功
    if not _instance_lock:
        # Mutex 创建失败，可能是权限问题
        # 为安全起见，假设已有实例运行
        _log_single_instance("Mutex 创建失败（句柄为空），假设已有实例运行")
        return False
    
    if last_error == ERROR_ALREADY_EXISTS:
        # 已有实例在运行
        _log_single_instance("检测到已有实例运行（ERROR_ALREADY_EXISTS），准备退出")
        kernel32.CloseHandle(_instance_lock)
        _instance_lock = None
        return False
    
    _log_single_instance("Mutex 创建成功，这是第一个实例")
    return True

def _release_single_instance_lock():
    """释放单实例锁"""
    global _instance_lock
    
    if _instance_lock and sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.ReleaseMutex(_instance_lock)
        kernel32.CloseHandle(_instance_lock)
        _instance_lock = None

# 检查单实例（更新场景除外）
# 如果带有 --cleanup-old 参数，说明是更新后的新版本启动，需要等待旧版本退出
_is_update_launch = "--cleanup-old" in sys.argv

if _is_update_launch:
    # 更新场景：等待旧版本释放锁（最多等 2 分钟）
    # 旧版本退出可能需要较长时间（清理资源、保存配置等）
    import time
    _max_wait_seconds = 120  # 2 分钟
    _wait_interval = 1.0     # 每秒检查一次
    
    for _wait_attempt in range(int(_max_wait_seconds / _wait_interval)):
        if _acquire_single_instance_lock():
            break
        time.sleep(_wait_interval)
    # 注意：即使超时也继续启动，因为这是更新场景
    # 旧版本可能已经卡死，新版本需要能够启动
elif not _acquire_single_instance_lock():
    # 普通启动：已有实例运行，尝试激活已有窗口后退出
    try:
        import ctypes
        from ctypes import wintypes, WINFUNCTYPE
        
        # 使用 EnumWindows 查找所有以"虎哥截图"开头的窗口
        # 因为主窗口标题是 "虎哥截图 v{version}"，不能用精确匹配
        user32 = ctypes.windll.user32
        
        # 存储找到的窗口句柄
        found_hwnds = []
        
        # EnumWindows 回调函数类型
        WNDENUMPROC = WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        
        def enum_windows_callback(hwnd, lParam):
            """枚举窗口回调函数"""
            try:
                # 获取窗口标题
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    
                    # 检查是否以"虎哥截图"开头（匹配主窗口）
                    if title.startswith("虎哥截图"):
                        # 检查窗口是否可见
                        if user32.IsWindowVisible(hwnd):
                            found_hwnds.append(hwnd)
            except Exception:
                pass
            return True  # 继续枚举
        
        # 枚举所有顶层窗口
        callback = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(callback, 0)
        
        # 激活找到的第一个窗口
        if found_hwnds:
            hwnd = found_hwnds[0]
            SW_RESTORE = 9
            SW_SHOW = 5
            
            # 如果窗口最小化，恢复它
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)
            
            # 将窗口置于前台
            # 使用 SetForegroundWindow 前需要一些技巧来绕过 Windows 的限制
            # 先用 AttachThreadInput 附加到前台线程
            foreground_hwnd = user32.GetForegroundWindow()
            if foreground_hwnd:
                foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
                current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                if foreground_thread != current_thread:
                    user32.AttachThreadInput(current_thread, foreground_thread, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(current_thread, foreground_thread, False)
                else:
                    user32.SetForegroundWindow(hwnd)
            else:
                user32.SetForegroundWindow(hwnd)
            
            # 确保窗口在最前面
            user32.BringWindowToTop(hwnd)
    except Exception:
        pass
    sys.exit(0)

# ========== Windows 工作台编码修复（解决中文乱码）==========
if sys.platform == 'win32':
    try:
        # 设置工作台输出编码为 UTF-8
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ========== PyInstaller 多进程支持（必须在最开始）==========
# 防止打包后多进程导致的重复初始化问题
import multiprocessing
multiprocessing.freeze_support()

# ========== Windows DPI 感知（必须在最开始设置）==========
# 告诉 Windows 本程序具备 DPI 感知能力，直接获取 1:1 物理像素
# 这样截图时不会被系统自动缩放/插值
import ctypes
try:
    # Windows 10/11 - Per Monitor DPI Aware V2
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # Windows 8.1 - Per Monitor DPI Aware
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            # Windows Vista/7/8 - System DPI Aware
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ========== 高DPI支持（必须在QApplication之前设置）==========
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
os.environ['QT_SCALE_FACTOR_ROUNDING_POLICY'] = 'PassThrough'
# 抑制 Qt DPI 相关警告（因为我们已经手动设置了 DPI 感知）
os.environ['QT_LOGGING_RULES'] = 'qt.qpa.window=false'

# ========== ONNX Runtime 环境变量 ==========
# 关闭各种日志输出
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['ONEDNN_VERBOSE'] = '0'  # 禁用 oneDNN 详细日志（防止卡死）

# 检测 CPU 类型和核心数，优化多线程设置
def _get_cpu_info():
    """获取 CPU 信息：(是否Intel, 核心数)"""
    import subprocess
    
    is_intel = False
    cpu_count = os.cpu_count() or 4
    
    try:
        system = platform.system()
        if system == 'Windows':
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'name'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            is_intel = 'intel' in result.stdout.lower()
        elif system in ('Linux', 'Darwin'):
            processor = platform.processor().lower()
            is_intel = 'intel' in processor
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, ValueError):
        pass
    
    return is_intel, cpu_count

_is_intel, _cpu_count = _get_cpu_info()

# 设置 OpenMP 线程数 - OCR 是计算密集型，充分利用 CPU
# 至少用 2 个线程，最多用 12 个（避免线程切换开销），留 2 个核心给系统
_omp_threads = max(2, min(_cpu_count - 2, 12)) if _cpu_count > 4 else max(2, _cpu_count)
os.environ['OMP_NUM_THREADS'] = str(_omp_threads)
os.environ['MKL_NUM_THREADS'] = str(_omp_threads)

# Intel CPU 启用 MKL 加速
if _is_intel:
    os.environ['KMP_AFFINITY'] = 'granularity=fine,compact,1,0'
    os.environ['KMP_BLOCKTIME'] = '0'

# ========== OCR 后端配置 ==========
# 从 v1.9.0 开始，统一使用 OpenVINO 作为唯一的 OCR 推理后端
# OpenVINO 内存泄漏问题已通过 openvino_optimizer.py 修复
# 修复方案：限制 CPU_RUNTIME_CACHE_CAPACITY 为 5（默认可能高达 5000）
# 可通过环境变量调整配置：
#   OPENVINO_CPU_CACHE_CAPACITY - 缓存容量（默认 5，0 为禁用）
#   SCREENSHOT_OCR_CACHE_DIR - 模型缓存目录
#   SCREENSHOT_OCR_PERFORMANCE_HINT - 性能模式（LATENCY/THROUGHPUT）

# ========== Supabase 订阅系统配置 ==========
os.environ.setdefault('SUPABASE_URL', os.environ.get('SUPABASE_URL', ''))
os.environ.setdefault('SUPABASE_KEY', os.environ.get('SUPABASE_KEY', ''))

# ========== 虎皮椒支付配置 ==========
# 支付密钥（生产环境建议从安全存储读取）
os.environ.setdefault('XUNHU_SECRET', os.environ.get('XUNHU_SECRET', ''))
# 支付回调地址（Supabase Edge Function）
os.environ.setdefault('XUNHU_NOTIFY_URL', os.environ.get('XUNHU_NOTIFY_URL', ''))
# 支付成功跳转页面
os.environ.setdefault('XUNHU_RETURN_URL', 'https://hudawang.cn/payment-success')

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# ========== 错误日志系统 ==========
from screenshot_tool import __version__
from screenshot_tool.core.error_logger import init_error_logger, get_error_logger

# 初始化错误日志记录器
_error_logger = init_error_logger(__version__)

def _show_crash_dialog(error_message: str):
    """显示崩溃对话框"""
    try:
        # 检查是否有 Qt 事件循环
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        
        if app is None:
            # 没有 Qt 应用，创建一个临时的
            app = QApplication([])
            
        from screenshot_tool.ui.crash_dialog import CrashDialog
        dialog = CrashDialog(
            error_message=error_message,
            log_path=_error_logger.log_path,
            version=__version__
        )
        dialog.exec()
    except Exception as e:
        # 如果崩溃对话框也失败了，至少打印错误
        print(f"[Fatal Error] {error_message}", file=sys.stderr)
        print(f"[Crash Dialog Error] {e}", file=sys.stderr)

def _exception_handler(exc_type, exc_value, exc_tb):
    """全局异常处理器"""
    # 忽略 KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    
    # 记录异常到日志
    error_message = _error_logger.log_exception(exc_type, exc_value, exc_tb)
    
    # 显示崩溃对话框
    _show_crash_dialog(error_message)

# 安装全局异常处理器
sys.excepthook = _exception_handler

from screenshot_tool.overlay_main import main
from screenshot_tool.core.crash_handler import CrashHandler


def _main_with_logging():
    """带日志记录的主函数"""
    # 记录启动
    _error_logger.log_startup()
    _error_logger.log_info("应用启动中...")
    
    # ========== 启动时清理更新临时文件 ==========
    # 注意：apply_pending_update 方法已移除，更新现在通过独立更新器完成
    # 这里只做临时文件清理，实际的更新逻辑在 UpdateService.cleanup_on_startup() 中
    
    # 记录系统信息
    _error_logger.log_info(f"Python: {platform.python_version()}")
    _error_logger.log_info(f"系统: {platform.system()} {platform.release()}")
    _error_logger.log_info(f"架构: {platform.machine()}")
    
    # 记录 CPU 信息
    _error_logger.log_info(f"CPU: Intel={_is_intel}, 核心数={_cpu_count}, OMP线程={_omp_threads}")
    
    # 默认启用详细日志（测试阶段）
    _error_logger.set_debug_mode(True)
    
    # 预初始化 OCR 并记录后端信息
    try:
        _error_logger.log_info("初始化 OCR 引擎...")
        from screenshot_tool.services.backend_selector import BackendSelector
        backend_info = BackendSelector.get_backend_info()
        _error_logger.log_info(f"CPU 厂商: {backend_info.cpu_vendor}")
        _error_logger.log_info(f"OpenVINO 可用: {backend_info.openvino_available}")
        _error_logger.log_info(f"选择后端: {backend_info.backend_type.value}")
        if backend_info.openvino_version:
            _error_logger.log_info(f"OpenVINO 版本: {backend_info.openvino_version}")
        if backend_info.performance_hint:
            _error_logger.log_info(f"性能模式: {backend_info.performance_hint}")
        if backend_info.cache_enabled:
            _error_logger.log_info(f"模型缓存: 已启用 ({backend_info.cache_dir})")
        
        # 尝试初始化 OCR 实例
        from screenshot_tool.services.rapid_ocr_service import get_global_ocr, warmup_ocr_engine
        ocr, error = get_global_ocr()
        if ocr:
            _error_logger.log_info("OCR 引擎初始化成功")
            # 预热 OCR 引擎，执行一次 dummy inference
            # 避免首次真实 OCR 请求时的冷启动延迟
            if warmup_ocr_engine():
                _error_logger.log_info("OCR 引擎预热完成")
            else:
                _error_logger.log_info("OCR 引擎预热跳过（非关键）")
        else:
            _error_logger.log_error(f"OCR 引擎初始化失败: {error}")
    except Exception as e:
        _error_logger.log_error(f"OCR 初始化异常: {e}")
        _error_logger.log_error(f"堆栈: {traceback.format_exc()}")
    
    try:
        # 清理旧日志
        _error_logger.cleanup_old_logs()
        
        # 运行主程序
        # 注意：CrashHandler 需要在 QApplication 创建后安装
        # 由于 main() 内部创建 QApplication，我们需要在 main() 返回前安装
        # 这里通过修改 overlay_main.py 来实现
        exit_code = main()
        
        # 记录正常退出
        _error_logger.log_info(f"应用正常退出，退出码: {exit_code}")
        _error_logger.log_shutdown()
        
        return exit_code
    except Exception as e:
        # 记录异常
        _error_logger.log_exception(type(e), e, e.__traceback__)
        _error_logger.log_shutdown()
        
        # 显示崩溃对话框
        error_message = f"类型: {type(e).__name__}\n消息: {e}\n\n{traceback.format_exc()}"
        _show_crash_dialog(error_message)
        
        return 1


if __name__ == "__main__":
    try:
        exit_code = _main_with_logging()
    finally:
        # 确保释放单实例锁
        _release_single_instance_lock()
    sys.exit(exit_code)
