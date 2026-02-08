# =====================================================
# =============== 后台 OCR 缓存工作器 ===============
# =====================================================

"""
后台 OCR 缓存工作器 - 在系统空闲时自动处理未 OCR 的历史图片

功能：
- 在系统空闲时自动处理未 OCR 的历史图片
- 使用 Worker-Object 模式，将工作逻辑移动到独立线程执行
- 使用最低优先级线程，不影响用户操作
- 用户活动时 100ms 内暂停处理

Requirements:
- Requirement 2.1: 使用低优先级线程避免影响用户操作
- Requirement 2.2: 系统空闲时开始处理未处理的图片
- Requirement 2.3: 检测到用户活动时 100ms 内暂停处理
- Requirement 2.4: 按最近添加顺序处理图片（最新优先）
- Requirement 2.5: 后台 OCR 完成后将结果存入 HistoryItem.ocr_cache

参考：
- C++ 版本的 BackgroundOCRWorker
- background_anki_importer.py 的 Worker 模式
"""

import os
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QMutexLocker, QTimer
from PySide6.QtGui import QImage

# ========== 异步调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

# 类型检查时导入，避免循环导入
if TYPE_CHECKING:
    from screenshot_tool.core.clipboard_history_manager import ClipboardHistoryManager
    from screenshot_tool.services.system_idle_detector import SystemIdleDetector


def ocr_worker_debug_log(message: str):
    """OCR 工作器调试日志（使用异步日志器）"""
    async_debug_log(message, "OCR_WORKER")


# ========== 工作器状态枚举 ==========

class WorkerState(Enum):
    """工作器状态
    
    定义后台 OCR 工作器的三种状态：
    - STOPPED: 已停止，未运行
    - RUNNING: 正在运行，等待空闲或处理中
    - PAUSED: 已暂停，等待恢复
    """
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


# ========== 后台 OCR 缓存工作器 ==========

class BackgroundOCRCacheWorker(QObject):
    """后台 OCR 缓存工作器
    
    在系统空闲时自动处理未 OCR 的历史图片。
    使用 Worker-Object 模式，将工作逻辑移动到独立线程执行。
    
    Requirement 2.1, 2.2, 2.3, 2.4, 2.5
    
    Signals:
        ocr_completed: OCR 完成信号，参数 (item_id, text)
        progress_changed: 进度变化信号，参数 (completed, total)
        state_changed: 状态变化信号，参数 (state_name)
        error_occurred: 错误发生信号，参数 (item_id, error_message)
    
    Usage:
        worker = BackgroundOCRCacheWorker()
        worker.connect_to_idle_detector(idle_detector)
        worker.ocr_completed.connect(on_ocr_completed)
        worker.start()
    """
    
    # 信号定义
    ocr_completed = Signal(str, str)      # (item_id, text)
    progress_changed = Signal(int, int)   # (completed, total)
    state_changed = Signal(str)           # state name
    error_occurred = Signal(str, str)     # (item_id, error_message)
    
    def __init__(self, parent: Optional[QObject] = None):
        """初始化工作器
        
        Args:
            parent: 父 QObject，用于 Qt 对象树管理
        """
        super().__init__(parent)
        
        # 状态管理
        self._state = WorkerState.STOPPED
        self._state_mutex = QMutex()  # 保护状态访问
        
        # 工作线程（将在 start() 中创建）
        self._thread: Optional[QThread] = None
        
        # 待处理队列
        self._pending_items: List[str] = []  # item_id 列表
        self._pending_mutex = QMutex()  # 保护队列访问
        
        # 处理状态
        self._is_processing = False
        self._processing_mutex = QMutex()  # 保护处理状态
        
        # 统计信息
        self._completed_count = 0
        self._total_count = 0
        
        # 历史记录管理器引用（用于获取待处理项目）
        self._history_manager: Optional["ClipboardHistoryManager"] = None
        
        ocr_worker_debug_log("BackgroundOCRCacheWorker 初始化完成")

    # ========== 生命周期方法 ==========
    
    def start(self) -> None:
        """启动工作器
        
        创建工作线程并开始监听空闲状态。
        线程优先级设置为最低。
        
        Requirement 2.1: 使用低优先级线程避免影响用户操作
        """
        with QMutexLocker(self._state_mutex):
            if self._state != WorkerState.STOPPED:
                ocr_worker_debug_log(f"工作器已在运行状态: {self._state.value}，忽略启动请求")
                return
            
            # 创建工作线程
            self._thread = QThread()
            
            # 将自己移动到工作线程
            self.moveToThread(self._thread)
            
            # 连接 started 信号，在线程真正开始运行后设置优先级
            # Bug fix (2026-01-23): 避免 QThread::setPriority: Cannot set priority, thread is not running
            # 注意：使用 lambda 捕获 thread 引用，避免在回调中访问 self._thread（线程安全）
            thread = self._thread
            self._thread.started.connect(lambda: self._set_thread_priority(thread))
            
            # 启动线程
            self._thread.start()
            
            # 更新状态
            self._state = WorkerState.RUNNING
            
        # 发出状态变化信号（在锁外发出，避免死锁）
        self.state_changed.emit(WorkerState.RUNNING.value)
        ocr_worker_debug_log("工作器已启动")
    
    def _set_thread_priority(self, thread: QThread) -> None:
        """设置线程优先级（线程安全）
        
        Args:
            thread: 要设置优先级的线程
            
        Bug fix (2026-01-23): 避免 QThread::setPriority 警告
        """
        if thread is not None and thread.isRunning():
            thread.setPriority(QThread.Priority.IdlePriority)
            ocr_worker_debug_log("线程优先级已设置为 IdlePriority")
    
    def pause(self) -> None:
        """暂停处理
        
        暂停当前的 OCR 处理，但保持线程运行。
        用于响应用户活动。
        
        Requirement 2.3: 检测到用户活动时暂停处理
        """
        with QMutexLocker(self._state_mutex):
            if self._state != WorkerState.RUNNING:
                ocr_worker_debug_log(f"工作器不在运行状态: {self._state.value}，忽略暂停请求")
                return
            
            self._state = WorkerState.PAUSED
        
        # 发出状态变化信号
        self.state_changed.emit(WorkerState.PAUSED.value)
        ocr_worker_debug_log("工作器已暂停")
    
    def resume(self) -> None:
        """恢复处理
        
        从暂停状态恢复，继续处理待处理队列。
        """
        with QMutexLocker(self._state_mutex):
            if self._state != WorkerState.PAUSED:
                ocr_worker_debug_log(f"工作器不在暂停状态: {self._state.value}，忽略恢复请求")
                return
            
            self._state = WorkerState.RUNNING
        
        # 发出状态变化信号
        self.state_changed.emit(WorkerState.RUNNING.value)
        ocr_worker_debug_log("工作器已恢复")

    def stop(self) -> None:
        """停止工作器
        
        停止工作线程并清理资源。
        """
        with QMutexLocker(self._state_mutex):
            if self._state == WorkerState.STOPPED:
                ocr_worker_debug_log("工作器已停止，忽略停止请求")
                return
            
            self._state = WorkerState.STOPPED
        
        # 停止线程
        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(3000):  # 等待最多 3 秒
                ocr_worker_debug_log("线程停止超时，放弃等待让线程自然结束")
                # 不再使用 terminate()，因为它会导致 OpenVINO 崩溃
                # 让线程自然结束后由 Python GC 清理
            
            self._thread.deleteLater()
            self._thread = None
        
        # 发出状态变化信号
        self.state_changed.emit(WorkerState.STOPPED.value)
        ocr_worker_debug_log("工作器已停止")
    
    # ========== 空闲检测器集成 ==========
    
    def connect_to_idle_detector(self, detector: "SystemIdleDetector") -> None:
        """连接到空闲检测器
        
        Args:
            detector: SystemIdleDetector 实例
        """
        detector.idle_started.connect(self.on_idle_started)
        detector.idle_ended.connect(self.on_idle_ended)
        ocr_worker_debug_log("已连接到空闲检测器")
    
    def set_history_manager(self, manager: "ClipboardHistoryManager") -> None:
        """设置历史记录管理器
        
        Args:
            manager: ClipboardHistoryManager 实例
        """
        self._history_manager = manager
        ocr_worker_debug_log("已设置历史记录管理器")
    
    def on_idle_started(self) -> None:
        """空闲开始槽
        
        开始处理未 OCR 的图片。
        
        Requirement 2.2: 系统空闲时开始处理未处理的图片
        """
        ocr_worker_debug_log("收到空闲开始信号")
        
        with QMutexLocker(self._state_mutex):
            if self._state == WorkerState.PAUSED:
                self._state = WorkerState.RUNNING
                self.state_changed.emit(WorkerState.RUNNING.value)
                ocr_worker_debug_log("从暂停状态恢复")
            elif self._state != WorkerState.RUNNING:
                ocr_worker_debug_log(f"工作器不在运行状态: {self._state.value}，忽略空闲开始信号")
                return
        
        # 开始处理
        self._start_processing()
    
    def on_idle_ended(self) -> None:
        """空闲结束槽
        
        100ms 内暂停处理。
        
        Requirement 2.3: 检测到用户活动时 100ms 内暂停处理
        """
        ocr_worker_debug_log("收到空闲结束信号")
        self.pause()

    # ========== 处理逻辑方法 ==========
    
    def _start_processing(self) -> None:
        """开始处理未 OCR 的图片
        
        从 ClipboardHistoryManager 获取未 OCR 的图片列表，
        添加到待处理队列，然后开始处理。
        
        Requirement 2.2: 系统空闲时开始处理未处理的图片
        Requirement 2.4: 按最近添加顺序处理图片（最新优先）
        """
        # 检查是否有历史记录管理器
        if self._history_manager is None:
            ocr_worker_debug_log("历史记录管理器未设置，无法开始处理")
            return
        
        # 检查是否已在处理中
        with QMutexLocker(self._processing_mutex):
            if self._is_processing:
                ocr_worker_debug_log("已在处理中，忽略重复启动请求")
                return
        
        # 获取未 OCR 的图片列表（已按最新优先排序）
        try:
            items = self._history_manager.get_items_without_ocr_cache(limit=100)
            if not items:
                ocr_worker_debug_log("没有需要处理的图片")
                return
            
            # 提取 item_id 列表并添加到待处理队列
            item_ids = [item.id for item in items]
            self.add_pending_items(item_ids)
            
            # 更新统计信息
            self._total_count = len(item_ids)
            self._completed_count = 0
            
            ocr_worker_debug_log(f"开始处理 {len(item_ids)} 个未 OCR 的图片")
            
            # 使用 QTimer.singleShot 触发处理，避免阻塞事件循环
            # 这是 Worker 模式的最佳实践
            QTimer.singleShot(0, self._process_next_item)
            
        except Exception as e:
            ocr_worker_debug_log(f"获取待处理图片失败: {e}")
            self.error_occurred.emit("", str(e))
    
    def _process_next_item(self) -> Optional[str]:
        """处理下一个待处理项目
        
        从待处理队列中获取下一个项目，执行 OCR 识别，
        并将结果存入 HistoryItem.ocr_cache。
        
        Returns:
            str: 处理的 item_id，如果队列为空或状态不允许则返回 None
            
        Requirement 2.1: 使用低优先级线程避免影响用户操作
        Requirement 2.4: 按最近添加顺序处理图片（最新优先）
        Requirement 2.5: 后台 OCR 完成后将结果存入 HistoryItem.ocr_cache
        Requirement 3.3: 跳过已有 OCR 缓存的项目
        Requirement 4.1: 使用单例 RapidOCRService
        Requirement 4.3: 发出进度信号
        Requirement 4.4: 发出错误信号
        """
        # 检查工作器状态（避免嵌套锁，先检查状态再处理）
        should_stop = False
        with QMutexLocker(self._state_mutex):
            if self._state != WorkerState.RUNNING:
                ocr_worker_debug_log(f"工作器不在运行状态: {self._state.value}，停止处理")
                should_stop = True
        
        if should_stop:
            with QMutexLocker(self._processing_mutex):
                self._is_processing = False
            return None
        
        # 从队列中获取下一个项目
        item_id: Optional[str] = None
        queue_empty = False
        with QMutexLocker(self._pending_mutex):
            if not self._pending_items:
                ocr_worker_debug_log("待处理队列为空，处理完成")
                queue_empty = True
            else:
                # 获取队列中的第一个项目（最新添加的优先）
                item_id = self._pending_items.pop(0)
        
        if queue_empty:
            with QMutexLocker(self._processing_mutex):
                self._is_processing = False
            return None
        
        # 标记为处理中
        with QMutexLocker(self._processing_mutex):
            self._is_processing = True
        
        ocr_worker_debug_log(f"开始处理项目: {item_id}")
        
        # 执行 OCR 处理
        try:
            self._perform_ocr(item_id)
        except Exception as e:
            ocr_worker_debug_log(f"处理项目 {item_id} 时发生异常: {e}")
            self.error_occurred.emit(item_id, str(e))
        
        # 更新进度
        self._completed_count += 1
        self.progress_changed.emit(self._completed_count, self._total_count)
        
        # 使用 QTimer.singleShot 触发下一个项目的处理
        # 这允许线程在任务间隙处理事件循环中的其他信号（如 pause/stop）
        QTimer.singleShot(0, self._process_next_item)
        
        return item_id
    
    def _perform_ocr(self, item_id: str) -> None:
        """执行单个项目的 OCR 处理
        
        Args:
            item_id: 历史记录项目 ID
            
        Requirement 2.5: 后台 OCR 完成后将结果存入 HistoryItem.ocr_cache
        Requirement 3.3: 跳过已有 OCR 缓存的项目
        Requirement 4.1: 使用单例 RapidOCRService
        Requirement 4.4: 发出错误信号
        """
        # 检查历史记录管理器
        if self._history_manager is None:
            ocr_worker_debug_log(f"历史记录管理器未设置，跳过项目: {item_id}")
            self.error_occurred.emit(item_id, "历史记录管理器未设置")
            return
        
        # 获取 HistoryItem
        item = self._history_manager.get_item(item_id)
        if item is None:
            ocr_worker_debug_log(f"找不到项目: {item_id}")
            self.error_occurred.emit(item_id, "找不到项目")
            return
        
        # Requirement 3.3: 跳过已有 OCR 缓存的项目
        if item.has_ocr_cache():
            ocr_worker_debug_log(f"项目已有 OCR 缓存，跳过: {item_id}")
            return
        
        # 检查是否有图片路径
        if item.image_path is None:
            ocr_worker_debug_log(f"项目没有图片路径，跳过: {item_id}")
            return
        
        # 构建完整的图片路径
        from screenshot_tool.core.clipboard_history_manager import get_clipboard_data_dir
        data_dir = get_clipboard_data_dir()
        image_full_path = os.path.join(data_dir, item.image_path)
        
        # 检查图片文件是否存在
        if not os.path.exists(image_full_path):
            ocr_worker_debug_log(f"图片文件不存在: {image_full_path}")
            self.error_occurred.emit(item_id, f"图片文件不存在: {image_full_path}")
            return
        
        # 加载图片
        image = QImage(image_full_path)
        if image.isNull():
            ocr_worker_debug_log(f"无法加载图片: {image_full_path}")
            self.error_occurred.emit(item_id, f"无法加载图片: {image_full_path}")
            return
        
        ocr_worker_debug_log(f"图片加载成功: {image.width()}x{image.height()}")
        
        # Requirement 4.1: 使用单例 RapidOCRService
        try:
            from screenshot_tool.services.rapid_ocr_service import RapidOCRService
            
            # 检查 OCR 服务是否可用
            ocr_service = RapidOCRService()
            available, error_msg = ocr_service.check_service_available()
            if not available:
                ocr_worker_debug_log(f"OCR 服务不可用: {error_msg}")
                self.error_occurred.emit(item_id, f"OCR 服务不可用: {error_msg}")
                return
            
            # 执行 OCR 识别
            ocr_worker_debug_log(f"开始 OCR 识别: {item_id}")
            result = ocr_service.recognize_image(image)
            
            # 释放图片引用（Requirement 5.2: 立即释放图片引用）
            del image
            
            if not result.success:
                ocr_worker_debug_log(f"OCR 识别失败: {result.error}")
                self.error_occurred.emit(item_id, f"OCR 识别失败: {result.error}")
                return
            
            # 获取 OCR 结果文本
            ocr_text = result.text if result.text else ""
            ocr_worker_debug_log(f"OCR 识别完成，文本长度: {len(ocr_text)}")
            
            # Requirement 2.5: 将结果存入 HistoryItem.ocr_cache
            success = self._history_manager.update_ocr_cache(item_id, ocr_text)
            if success:
                ocr_worker_debug_log(f"OCR 缓存已更新: {item_id}")
                # Requirement 4.3: 发出完成信号
                self.ocr_completed.emit(item_id, ocr_text)
            else:
                ocr_worker_debug_log(f"更新 OCR 缓存失败: {item_id}")
                self.error_occurred.emit(item_id, "更新 OCR 缓存失败")
                
        except ImportError as e:
            ocr_worker_debug_log(f"导入 RapidOCRService 失败: {e}")
            self.error_occurred.emit(item_id, f"OCR 服务导入失败: {e}")
        except Exception as e:
            ocr_worker_debug_log(f"OCR 处理异常: {e}")
            self.error_occurred.emit(item_id, f"OCR 处理异常: {e}")

    # ========== 状态查询方法 ==========
    
    def is_running(self) -> bool:
        """检查是否正在运行
        
        Returns:
            bool: True 表示工作器处于 RUNNING 或 PAUSED 状态
        """
        with QMutexLocker(self._state_mutex):
            return self._state != WorkerState.STOPPED
    
    def is_processing(self) -> bool:
        """检查是否正在处理 OCR
        
        Returns:
            bool: True 表示正在处理 OCR 任务
        """
        with QMutexLocker(self._processing_mutex):
            return self._is_processing
    
    def get_state(self) -> WorkerState:
        """获取当前状态
        
        Returns:
            WorkerState: 当前工作器状态
        """
        with QMutexLocker(self._state_mutex):
            return self._state
    
    def pending_count(self) -> int:
        """获取待处理项目数量
        
        Returns:
            int: 待处理队列中的项目数量
        """
        with QMutexLocker(self._pending_mutex):
            return len(self._pending_items)
    
    # ========== 队列管理方法 ==========
    
    def add_pending_item(self, item_id: str) -> None:
        """添加待处理项目
        
        Args:
            item_id: 历史记录项目 ID
        """
        with QMutexLocker(self._pending_mutex):
            if item_id not in self._pending_items:
                self._pending_items.append(item_id)
                ocr_worker_debug_log(f"添加待处理项目: {item_id}")
    
    def add_pending_items(self, item_ids: List[str]) -> None:
        """批量添加待处理项目
        
        Args:
            item_ids: 历史记录项目 ID 列表
        """
        with QMutexLocker(self._pending_mutex):
            for item_id in item_ids:
                if item_id not in self._pending_items:
                    self._pending_items.append(item_id)
            ocr_worker_debug_log(f"批量添加 {len(item_ids)} 个待处理项目")
    
    def clear_pending_items(self) -> None:
        """清空待处理队列"""
        with QMutexLocker(self._pending_mutex):
            self._pending_items.clear()
            ocr_worker_debug_log("待处理队列已清空")

    # ========== 资源清理 ==========
    
    def cleanup(self) -> None:
        """清理资源
        
        在应用退出时调用，确保线程正确停止。
        
        Requirement 5.4: 提供 cleanup 方法释放所有资源
        """
        ocr_worker_debug_log("开始清理资源...")
        
        # 停止工作器
        self.stop()
        
        # 清空待处理队列
        self.clear_pending_items()
        
        # 重置统计信息
        self._completed_count = 0
        self._total_count = 0
        
        ocr_worker_debug_log("BackgroundOCRCacheWorker 资源已清理")
