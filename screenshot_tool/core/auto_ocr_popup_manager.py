# =====================================================
# =============== 自动OCR弹窗管理器 ===============
# =====================================================

"""
自动OCR弹窗管理器 - 截图完成后自动显示OCR窗口

Feature: auto-ocr-popup
Requirements: 1.1, 1.2, 1.3, 5.1, 5.4
"""

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, QRect, Signal, QThread
from PySide6.QtGui import QImage

from screenshot_tool.core.screen_space_detector import ScreenSpaceDetector
from screenshot_tool.core.async_logger import async_debug_log

def popup_debug_log(message: str):
    """自动OCR弹窗调试日志"""
    async_debug_log(message, "AUTO-OCR-POPUP")

# OCRResultWindow 改为延迟导入，避免 EXE 启动时的模块加载延迟
# 在 _show_ocr_window 方法中按需导入
# 使用线程锁保护延迟导入，避免多线程竞态条件
import threading
_ocr_result_window_lock = threading.Lock()
_OCRResultWindow = None

def _get_ocr_result_window_class():
    """延迟获取 OCRResultWindow 类（线程安全）"""
    global _OCRResultWindow
    if _OCRResultWindow is None:
        with _ocr_result_window_lock:
            # 双重检查锁定模式
            if _OCRResultWindow is None:
                from screenshot_tool.ui.ocr_result_window import OCRResultWindow
                _OCRResultWindow = OCRResultWindow
    return _OCRResultWindow

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import ConfigManager
    from screenshot_tool.services.ocr_manager import OCRManager


class OCRBackgroundWorker(QThread):
    """OCR后台处理线程
    
    在后台线程执行OCR识别，避免阻塞UI。
    """
    finished = Signal(object)  # UnifiedOCRResult
    
    def __init__(self, image: QImage, ocr_manager: "OCRManager"):
        super().__init__()
        # 深拷贝图片以确保线程安全
        # 只在图片有效时复制，避免不必要的内存分配
        if image is not None and not image.isNull():
            self._image = image.copy()
        else:
            self._image = None
        self._ocr_manager = ocr_manager
        self._should_stop = False
    
    def request_stop(self):
        """请求停止线程"""
        self._should_stop = True
    
    def _safe_emit(self, result):
        """安全地发送信号
        
        注意：移除了模态对话框检测，因为 OCR 结果窗口使用 WindowStaysOnTopHint，
        会显示在所有窗口之上，不会与模态对话框冲突。
        """
        if self._should_stop:
            return
        self.finished.emit(result)
    
    def run(self):
        """执行OCR识别"""
        try:
            if self._should_stop:
                return
            
            if self._image is None or self._image.isNull():
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self._safe_emit(UnifiedOCRResult.error_result("图片为空"))
                return
            
            if self._should_stop:
                return
            
            result = self._ocr_manager.recognize(self._image)
            
            # 如果已请求停止，不发送结果
            if not self._should_stop:
                self._safe_emit(result)
            
        except Exception as e:
            if not self._should_stop:
                from screenshot_tool.services.ocr_manager import UnifiedOCRResult
                self._safe_emit(UnifiedOCRResult.error_result(str(e)))
        finally:
            # 释放图片内存
            self._image = None


class AutoOCRPopupManager(QObject):
    """自动OCR弹窗管理器
    
    负责在截图完成后自动显示识别文字结果窗口。
    窗口位置根据截图选区自动选择在左侧或右侧，同时避开工具栏。
    支持复用后台预处理的 OCR 缓存结果，避免重复识别。
    
    Feature: screenshot-ocr-split-view
    当 use_split_view 配置启用时，发出 split_view_requested 信号，
    由 OverlayMain 处理并显示分屏窗口。
    """
    
    # 信号：OCR完成
    ocr_completed = Signal(str)  # 识别文字结果文本
    # 信号：ESC键按下，通知截图界面关闭
    escape_requested = Signal()
    # 信号：请求显示分屏视图（已废弃，保留兼容）
    # Feature: screenshot-ocr-split-view
    # Requirements: 7.1, 7.2
    split_view_requested = Signal(QImage, list)  # image, annotations
    # 信号：请求打开工作台窗口并自动 OCR
    # Feature: clipboard-ocr-merge
    # 截图后使用邮箱风格的工作台窗口
    clipboard_history_ocr_requested = Signal(QImage, list)  # image, annotations
    
    # 防抖延迟（毫秒）- 用户调整选区时，等待一段时间后再启动 OCR
    DEBOUNCE_DELAY_MS = 300
    
    def __init__(
        self, 
        config_manager: "ConfigManager", 
        ocr_manager: "OCRManager",
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        popup_debug_log("AutoOCRPopupManager 初始化")
        self._config_manager = config_manager
        self._ocr_manager = ocr_manager
        self._space_detector = ScreenSpaceDetector()
        self._current_window: Optional["OCRResultWindow"] = None
        self._ocr_worker: Optional[OCRBackgroundWorker] = None
        self._pending_image: Optional[QImage] = None
        self._pending_rect: Optional[QRect] = None
        self._toolbar_rects: list = []  # 工具栏位置列表
        
        # 缓存的 OCR 结果（由外部设置，用于复用后台预处理结果）
        self._cached_ocr_result = None  # UnifiedOCRResult
        self._cached_image_hash = None  # 对应的图片哈希
        
        # 防抖定时器 - 避免频繁调整选区时重复启动 OCR
        from PySide6.QtCore import QTimer
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        self._debounced_image: Optional[QImage] = None
        self._debounced_rect: Optional[QRect] = None
        
        popup_debug_log(f"初始化完成, config_manager={config_manager is not None}, ocr_manager={ocr_manager is not None}")
    
    def _get_image_hash(self, image: QImage) -> int:
        """计算图片的哈希值，用于匹配缓存
        
        使用图片尺寸和多个采样点的像素值计算哈希。
        """
        if image is None or image.isNull() or image.width() <= 0 or image.height() <= 0:
            return 0
        
        w, h = image.width(), image.height()
        sample_points = [
            (0, 0),
            (w - 1, 0),
            (0, h - 1),
            (w - 1, h - 1),
            (w // 2, h // 2),
        ]
        pixels = tuple(image.pixel(x, y) for x, y in sample_points)
        return hash((w, h) + pixels)
    
    def set_cached_ocr_result(self, result, image_hash: int) -> None:
        """设置缓存的 OCR 结果（由后台预处理提供）
        
        Args:
            result: UnifiedOCRResult 对象
            image_hash: 对应图片的哈希值
        """
        self._cached_ocr_result = result
        self._cached_image_hash = image_hash
        popup_debug_log(f"设置缓存 OCR 结果: hash={image_hash}, success={result.success if result else None}")
    
    def clear_cached_ocr_result(self) -> None:
        """清除缓存的 OCR 结果"""
        self._cached_ocr_result = None
        self._cached_image_hash = None
    
    def update_ocr_manager(self, ocr_manager: "OCRManager") -> None:
        """更新OCR管理器引用
        
        当OCR管理器延迟初始化时使用此方法更新引用。
        
        Args:
            ocr_manager: 新的OCR管理器实例
        """
        self._ocr_manager = ocr_manager
    
    def set_toolbar_rects(self, rects: list) -> None:
        """设置工具栏位置列表
        
        OCR窗口定位时会避开这些区域。
        
        Args:
            rects: QRect 列表，表示工具栏的位置
        """
        self._toolbar_rects = [r for r in rects if r is not None and not r.isEmpty()]
        popup_debug_log(f"设置工具栏位置: {len(self._toolbar_rects)} 个")
    
    def clear_toolbar_rects(self) -> None:
        """清除工具栏位置列表"""
        self._toolbar_rects = []
    
    def is_enabled(self) -> bool:
        """检查功能是否启用
        
        注意：OCR 开关状态现在由截图界面的工具栏按钮控制，
        调用方在调用 on_screenshot_confirmed 之前会先检查开关状态。
        此方法保留用于向后兼容，始终返回 True。
        
        Returns:
            始终返回 True
        """
        popup_debug_log("is_enabled() = True (由调用方控制)")
        return True
    
    def on_screenshot_confirmed(self, image: QImage, selection_rect: QRect) -> None:
        """截图确认时的回调
        
        这是主入口点，在截图完成时调用。
        使用防抖机制避免频繁调整选区时重复启动 OCR。
        
        Args:
            image: 截图图片
            selection_rect: 截图选区矩形（屏幕坐标）
        """
        popup_debug_log("=" * 50)
        popup_debug_log("on_screenshot_confirmed 被调用")
        popup_debug_log(f"image={image is not None}, isNull={image.isNull() if image else 'N/A'}")
        popup_debug_log(f"selection_rect={selection_rect}")
        
        if not self.is_enabled():
            popup_debug_log("功能已禁用，跳过")
            return
        
        if image is None or image.isNull():
            popup_debug_log("图片为空，跳过")
            return
        
        popup_debug_log(f"图片尺寸: {image.width()}x{image.height()}")
        
        # 保存待处理数据（用于防抖）
        self._debounced_image = image.copy()
        self._debounced_rect = selection_rect
        
        # 如果定时器已在运行，重置它（防抖）
        if self._debounce_timer.isActive():
            popup_debug_log("防抖: 重置定时器")
            self._debounce_timer.stop()
        
        # 启动防抖定时器
        popup_debug_log(f"防抖: 启动定时器 ({self.DEBOUNCE_DELAY_MS}ms)")
        self._debounce_timer.start(self.DEBOUNCE_DELAY_MS)
    
    def _on_debounce_timeout(self) -> None:
        """防抖定时器超时回调 - 实际执行 OCR
        
        Feature: screenshot-ocr-split-view
        当 use_split_view 配置启用时，发出 split_view_requested 信号，
        由 OverlayMain 处理并显示分屏窗口，而不是显示 OCRResultWindow。
        """
        popup_debug_log("防抖定时器超时，开始执行 OCR")
        
        if self._debounced_image is None or self._debounced_rect is None:
            popup_debug_log("防抖数据为空，跳过")
            return
        
        image = self._debounced_image
        selection_rect = self._debounced_rect
        
        # 清除防抖数据
        self._debounced_image = None
        self._debounced_rect = None
        
        # 检查是否使用分屏视图
        # Feature: screenshot-ocr-split-view, clipboard-ocr-merge
        # Requirements: 7.1
        # 
        # 截图后的 OCR 弹窗模式：
        # - use_split_view=True: 使用工作台窗口（邮箱风格，左侧列表+右侧 OCR）
        # - use_split_view=False: 使用独立 OCR 窗口
        use_split_view = True  # 默认使用工作台窗口模式
        if self._config_manager:
            use_split_view = getattr(self._config_manager.config, 'use_split_view', True)
        
        if use_split_view:
            popup_debug_log("使用工作台窗口模式（邮箱风格）")
            # 发出信号，由 OverlayMain 处理
            # 使用 clipboard_history_ocr_requested 信号打开工作台窗口
            self.clipboard_history_ocr_requested.emit(image, [])  # annotations 为空列表
            return
        
        # 保存待处理数据
        self._pending_image = image
        self._pending_rect = selection_rect
        
        # 停止正在运行的 OCR 任务
        self._stop_current_ocr()
        
        # 关闭现有窗口
        self._close_current_window()
        
        # 创建并显示新窗口
        popup_debug_log("准备显示OCR窗口...")
        self._show_ocr_window(image, selection_rect)
    
    def _stop_current_ocr(self) -> None:
        """停止当前正在运行的 OCR 任务"""
        if self._ocr_worker is None:
            return
        
        popup_debug_log("停止 OCR 任务")
        self._safe_cleanup_worker(self._ocr_worker, timeout_ms=500, force_terminate=True)
        self._ocr_worker = None
    
    def _safe_cleanup_worker(self, worker: OCRBackgroundWorker, timeout_ms: int = 500, 
                             force_terminate: bool = False) -> bool:
        """安全清理 OCR 工作线程
        
        Args:
            worker: 要清理的工作线程
            timeout_ms: 等待超时时间（毫秒）
            force_terminate: 已废弃，不再使用 terminate()
            
        Returns:
            True 如果成功清理，False 如果放弃清理
        """
        if worker is None:
            return True
        
        # 请求停止
        worker.request_stop()
        
        # 断开信号连接
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # 等待线程停止（不使用 terminate() 避免 OpenVINO 推理时崩溃）
        if worker.isRunning():
            worker.quit()
            if not worker.wait(timeout_ms):
                popup_debug_log(f"线程未能在 {timeout_ms}ms 内停止，放弃等待让线程自然结束")
                # 不使用 terminate()，避免崩溃
                # 重要：不调用 deleteLater()，因为线程仍在运行
                # 让线程自然结束后由 Python GC 清理
                return False
        
        # 只有线程已停止时才安全删除
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        
        return True
    
    def _show_ocr_window(self, image: QImage, selection_rect: QRect) -> None:
        """创建并显示识别文字结果窗口
        
        Args:
            image: 截图图片
            selection_rect: 截图选区矩形
        """
        popup_debug_log("_show_ocr_window 开始")
        
        try:
            # 延迟导入 OCRResultWindow，避免 EXE 启动时的模块加载延迟
            OCRResultWindow = _get_ocr_result_window_class()
            popup_debug_log("创建 OCRResultWindow")
            
            # 创建窗口
            window = OCRResultWindow()
            popup_debug_log(f"窗口创建成功: {window}")
            
            window.set_image(image)
            popup_debug_log("set_image 完成")
            
            window.set_ocr_manager(self._ocr_manager)
            popup_debug_log("set_ocr_manager 完成")
            
            window.set_loading()
            popup_debug_log("set_loading 完成")
            
            # 计算窗口位置（避开工具栏）
            window_size = window.size()
            popup_debug_log(f"窗口尺寸: {window_size.width()}x{window_size.height()}")
            popup_debug_log(f"避开工具栏数量: {len(self._toolbar_rects)}")
            
            position = self._space_detector.calculate_window_position(
                selection_rect, 
                window_size,
                avoid_rects=self._toolbar_rects
            )
            popup_debug_log(f"计算位置: x={position.x}, y={position.y}, side={position.side}")
            
            # 移动窗口到计算的位置
            window.move(position.x, position.y)
            popup_debug_log("窗口移动完成")
            
            # 连接关闭信号
            window.closed.connect(self._on_window_closed)
            # 连接ESC键信号，转发给截图界面
            window.escape_pressed.connect(self._on_escape_pressed)
            popup_debug_log("信号连接完成")
            
            # 保存引用
            self._current_window = window
            
            # 显示窗口
            window.show()
            popup_debug_log("window.show() 调用完成")
            
            window.raise_()
            popup_debug_log("window.raise_() 调用完成")
            
            window.activateWindow()
            popup_debug_log("window.activateWindow() 调用完成")
            
            popup_debug_log(f"窗口是否可见: {window.isVisible()}")
            
            # 计算图片哈希，用于匹配缓存
            image_hash = self._get_image_hash(image)
            
            # 开始后台OCR（会检查缓存）
            self._start_ocr(image, image_hash)
            popup_debug_log("_start_ocr 调用完成")
            
        except Exception as e:
            popup_debug_log(f"_show_ocr_window 异常: {e}")
            import traceback
            popup_debug_log(traceback.format_exc())
    
    def _start_ocr(self, image: QImage, image_hash: int = None) -> None:
        """启动后台OCR处理
        
        如果有缓存的 OCR 结果且图片哈希匹配，直接使用缓存结果。
        
        Args:
            image: 要识别的图片
            image_hash: 图片哈希值（用于匹配缓存）
        """
        # 检查是否有缓存结果可用
        if (self._cached_ocr_result is not None and 
            image_hash is not None and 
            self._cached_image_hash == image_hash):
            popup_debug_log(f"使用缓存的 OCR 结果: hash={image_hash}")
            # 直接使用缓存结果
            self._on_ocr_finished(self._cached_ocr_result)
            return
        
        popup_debug_log("无可用缓存，启动新的 OCR 任务")
        
        # 清理之前的worker
        if self._ocr_worker is not None:
            self._safe_cleanup_worker(self._ocr_worker, timeout_ms=500, force_terminate=True)
            self._ocr_worker = None
        
        # 创建新worker
        self._ocr_worker = OCRBackgroundWorker(image, self._ocr_manager)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.start()
    
    def _on_ocr_finished(self, result) -> None:
        """OCR完成回调
        
        Args:
            result: UnifiedOCRResult
        """
        # 检查窗口是否仍然有效
        if self._current_window is None:
            self._cleanup_ocr_worker()
            return
        
        # 检查窗口是否已被销毁（Qt对象可能已删除）
        try:
            if not self._current_window.isVisible():
                self._cleanup_ocr_worker()
                return
        except RuntimeError:
            # 窗口对象已被删除
            self._current_window = None
            self._cleanup_ocr_worker()
            return
        
        if result is None:
            self._current_window.set_error("识别失败: 未知错误")
        elif result.success:
            # 传递评分、后端信息和耗时到 OCR 结果窗口
            average_score = getattr(result, 'average_score', 0.0)
            backend_detail = getattr(result, 'backend_detail', "")
            elapsed_time = getattr(result, 'elapsed_time', 0.0)
            self._current_window.set_text(result.text, result.engine, average_score, backend_detail, elapsed_time)
            self.ocr_completed.emit(result.text)
        else:
            error = result.error or "识别失败"
            self._current_window.set_error(error)
        
        self._cleanup_ocr_worker()
    
    def _cleanup_ocr_worker(self) -> None:
        """清理OCR工作线程"""
        if self._ocr_worker is None:
            return
        
        self._safe_cleanup_worker(self._ocr_worker, timeout_ms=1000, force_terminate=True)
        self._ocr_worker = None
    
    def _close_current_window(self) -> None:
        """关闭当前OCR窗口
        
        增强的清理方法，确保释放所有内存资源：
        - 安全断开信号连接
        - 释放窗口图片引用
        - 关闭并删除窗口
        
        Requirements: 1.4, 4.3, 8.3, 8.4
        """
        if self._current_window is None:
            return
        
        # 安全断开信号连接 (Requirements: 8.3, 8.4)
        try:
            self._current_window.closed.disconnect(self._on_window_closed)
        except (RuntimeError, TypeError):
            pass
        
        try:
            self._current_window.escape_pressed.disconnect(self._on_escape_pressed)
        except (RuntimeError, TypeError):
            pass
        
        try:
            self._current_window.engine_switch_requested.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # 释放窗口图片引用 (Requirements: 1.4)
        try:
            if hasattr(self._current_window, '_current_image'):
                self._current_window._current_image = None
            if hasattr(self._current_window, '_ocr_cache'):
                self._current_window._ocr_cache.clear()
        except (RuntimeError, AttributeError):
            pass
        
        # 关闭并删除窗口 (Requirements: 4.3)
        try:
            self._current_window.close()
            self._current_window.deleteLater()
        except RuntimeError:
            # 窗口可能已被销毁
            pass
        
        self._current_window = None
    
    def _on_window_closed(self) -> None:
        """窗口关闭回调"""
        self._current_window = None
    
    def _on_escape_pressed(self) -> None:
        """OCR窗口ESC键按下回调，转发信号给截图界面"""
        popup_debug_log("OCR窗口ESC键按下，转发escape_requested信号")
        self.escape_requested.emit()
    
    def has_active_window(self) -> bool:
        """检查是否有活动的OCR窗口
        
        Returns:
            True 如果有活动窗口
        """
        if self._current_window is None:
            return False
        try:
            return self._current_window.isVisible()
        except RuntimeError:
            # 窗口对象已被销毁
            self._current_window = None
            return False
    
    def is_window_pinned(self) -> bool:
        """检查OCR窗口是否已置顶
        
        Returns:
            True 如果窗口已置顶
        """
        if self._current_window is None:
            return False
        try:
            return self._current_window.is_pinned()
        except (RuntimeError, AttributeError):
            return False
    
    def close_window(self) -> None:
        """关闭OCR窗口（公开方法）"""
        self._close_current_window()
    
    def show_existing_window(self) -> bool:
        """显示已存在的OCR窗口（如果有）
        
        用于 OCR 按钮切换时，如果窗口已存在且有结果，直接显示而不重新 OCR。
        
        Returns:
            True 如果成功显示了已存在的窗口，False 如果没有可用窗口
        """
        if self._current_window is None:
            popup_debug_log("show_existing_window: 没有现有窗口")
            return False
        
        try:
            if not self._current_window.isVisible() or self._current_window.isMinimized():
                popup_debug_log("show_existing_window: 显示已存在的窗口")
                # Bug fix (2026-01-23): 如果窗口最小化，show() 不会恢复窗口
                if self._current_window.isMinimized():
                    self._current_window.showNormal()
                else:
                    self._current_window.show()
                self._current_window.raise_()
                self._current_window.activateWindow()
            return True
        except RuntimeError:
            # 窗口对象已被销毁
            popup_debug_log("show_existing_window: 窗口已被销毁")
            self._current_window = None
            return False
    
    def cleanup(self) -> None:
        """清理资源
        
        增强的清理方法，确保释放所有内存资源：
        - 停止防抖定时器
        - 释放所有图片引用
        - 关闭窗口
        - 清理工作线程
        - 触发垃圾回收
        
        注意：此方法应在应用退出时调用，会等待后台线程完成。
        
        Requirements: 1.4, 7.3, 8.3
        """
        import gc
        
        # 停止防抖定时器
        try:
            if self._debounce_timer is not None and self._debounce_timer.isActive():
                self._debounce_timer.stop()
        except RuntimeError:
            pass  # 定时器可能已被销毁
        
        # 清理防抖数据（释放内存）(Requirements: 1.4)
        self._debounced_image = None
        self._debounced_rect = None
        
        # 关闭窗口
        self._close_current_window()
        
        # 清理OCR worker（使用较长超时，因为是应用退出）
        if self._ocr_worker is not None:
            # 使用更长的超时时间（2秒），给 OpenVINO 推理足够时间完成
            self._safe_cleanup_worker(self._ocr_worker, timeout_ms=2000, force_terminate=True)
            self._ocr_worker = None
        
        # 清理待处理数据（释放内存）(Requirements: 1.4)
        self._pending_image = None
        self._pending_rect = None
        
        # 清理缓存的 OCR 结果
        self._cached_ocr_result = None
        self._cached_image_hash = None
        
        # 清理工具栏位置列表
        self._toolbar_rects = []
        
        # 触发垃圾回收 (Requirements: 7.3)
        gc.collect()
