# =====================================================
# =============== 后台 OCR 管理器 ===============
# =====================================================

"""
BackgroundOCRManager - 后台 OCR 管理器

功能：
- 管理高亮区域的异步 OCR 任务
- 在高亮绘制完成时自动触发 OCR
- 缓存 OCR 结果，支持任务取消

Requirements: 1.1, 1.2, 1.3, 1.4
Property 1: OCR 缓存管理一致性
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum

from PySide6.QtCore import QObject, QThread, Signal, QRect, QMutex, QWaitCondition, QTimer
from PySide6.QtGui import QImage

# 导入调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as debug_log
except ImportError:
    def debug_log(msg, tag=""): print(f"[{tag}] {msg}")


# ========== OCR 裁剪边距常量 ==========
# 水平方向适度扩展，避免截掉字母但不要包含相邻单词
# 垂直方向少量扩展，避免识别到上下行
# 注意：边距太小会导致 OCR 无法识别，太大会包含相邻单词/行
OCR_MARGIN_HORIZONTAL = 20  # 水平边距（左右各20像素）
OCR_MARGIN_VERTICAL = 15    # 垂直边距（上下各15像素）

# ========== OCR 最小尺寸常量 ==========
# RapidOCR 对小图片识别效果差，需要放大到最小尺寸
OCR_MIN_WIDTH = 200   # 最小宽度（像素）
OCR_MIN_HEIGHT = 100  # 最小高度（像素）


class TaskStatus(Enum):
    """OCR 任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class OCRTask:
    """OCR 任务数据"""
    item_id: int                          # 关联的 DrawItem ID
    rect: QRect                           # 高亮区域（相对于截图）
    status: TaskStatus = TaskStatus.PENDING
    result: List[str] = field(default_factory=list)  # 识别出的单词列表
    error: Optional[str] = None           # 错误信息


class OCRWorkerThread(QThread):
    """OCR 工作线程"""
    
    finished = Signal(int, list)   # (item_id, words)
    error = Signal(int, str)       # (item_id, error_msg)
    
    # 类级别的 OCR 服务实例（避免重复加载模型）
    _shared_ocr_service = None
    _ocr_service_lock = QMutex()
    
    def __init__(self, item_id: int, image: QImage, rect: QRect, parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self._image = image.copy() if image and not image.isNull() else None
        self._rect = rect
        self._cancelled = False
    
    @classmethod
    def get_ocr_service(cls):
        """获取共享的 OCR 服务实例（线程安全）"""
        cls._ocr_service_lock.lock()
        try:
            if cls._shared_ocr_service is None:
                from screenshot_tool.services.rapid_ocr_service import RapidOCRService
                cls._shared_ocr_service = RapidOCRService()
                debug_log("创建共享 RapidOCRService 实例", "OCR_MGR")
            return cls._shared_ocr_service
        finally:
            cls._ocr_service_lock.unlock()
    
    def cancel(self):
        """取消任务"""
        self._cancelled = True
    
    def _safe_emit_finished(self, item_id: int, words: list):
        """安全地发送 finished 信号，避免在模态对话框打开时崩溃"""
        if self._cancelled:
            return
        self._wait_for_modal_dialog()
        if not self._cancelled:
            self.finished.emit(item_id, words)
    
    def _safe_emit_error(self, item_id: int, error_msg: str):
        """安全地发送 error 信号，避免在模态对话框打开时崩溃"""
        if self._cancelled:
            return
        self._wait_for_modal_dialog()
        if not self._cancelled:
            self.error.emit(item_id, error_msg)
    
    def _wait_for_modal_dialog(self):
        """等待模态对话框关闭（最多等待 500ms）"""
        try:
            from screenshot_tool.core.modal_dialog_detector import ModalDialogDetector
            
            max_retries = 5
            retry_delay_ms = 100
            
            for i in range(max_retries):
                if self._cancelled:
                    return
                if not ModalDialogDetector.is_modal_dialog_active():
                    return
                if i < max_retries - 1:
                    debug_log(f"检测到模态对话框，延迟发送信号 (重试 {i+1}/{max_retries})", "OCR_WORKER")
                    self.msleep(retry_delay_ms)
            
            debug_log("模态对话框持续存在，强制发送信号", "OCR_WORKER")
        except Exception as e:
            debug_log(f"模态对话框检测失败: {e}", "OCR_WORKER")
    
    def run(self):
        """执行 OCR 识别"""
        if self._cancelled:
            return
        
        try:
            if self._image is None or self._image.isNull():
                if not self._cancelled:
                    self._safe_emit_error(self._item_id, "图片为空")
                return
            
            # 扩展裁剪区域边界，提高 OCR 识别率
            # 水平方向多扩展，避免截掉字母；垂直方向适度扩展，避免识别到上下行
            x = max(0, self._rect.x() - OCR_MARGIN_HORIZONTAL)
            y = max(0, self._rect.y() - OCR_MARGIN_VERTICAL)
            w = min(self._image.width() - x, self._rect.width() + OCR_MARGIN_HORIZONTAL * 2)
            h = min(self._image.height() - y, self._rect.height() + OCR_MARGIN_VERTICAL * 2)
            
            if w <= 0 or h <= 0:
                if not self._cancelled:
                    self._safe_emit_error(self._item_id, "裁剪区域无效")
                return
            
            expanded_rect = QRect(x, y, w, h)
            debug_log(f"裁剪区域 item_id={self._item_id}: 原始=({self._rect.x()},{self._rect.y()},{self._rect.width()}x{self._rect.height()}) 扩展=({x},{y},{w}x{h})", "OCR_WORKER")
            cropped = self._image.copy(expanded_rect)
            
            # 裁剪完成后立即释放原图引用
            self._image = None
            
            if cropped.isNull():
                if not self._cancelled:
                    self._safe_emit_error(self._item_id, "裁剪区域为空")
                return
            
            if self._cancelled:
                return
            
            # 使用共享的 OCR 服务实例
            ocr_service = self.get_ocr_service()
            result = ocr_service.recognize_image(cropped)
            
            # OCR 完成后释放裁剪图片
            del cropped
            
            if self._cancelled:
                return
            
            if result.success and result.text:
                debug_log(f"OCR 原始文本 item_id={self._item_id}: '{result.text}'", "OCR_WORKER")
                words = self._extract_english_words(result.text)
                debug_log(f"提取单词 item_id={self._item_id}: {words}", "OCR_WORKER")
                self._safe_emit_finished(self._item_id, words)
            elif result.success:
                debug_log(f"OCR 成功但无文本 item_id={self._item_id}", "OCR_WORKER")
                self._safe_emit_finished(self._item_id, [])
            else:
                debug_log(f"OCR 失败 item_id={self._item_id}: {result.error}", "OCR_WORKER")
                self._safe_emit_error(self._item_id, result.error or "识别失败")
                
        except ImportError as e:
            if not self._cancelled:
                self._safe_emit_error(self._item_id, f"缺少依赖: {str(e)}")
        except Exception as e:
            if not self._cancelled:
                self._safe_emit_error(self._item_id, f"OCR 异常: {str(e)}")
        finally:
            # 确保图片引用被释放
            self._image = None
    
    def _extract_english_words(self, text: str) -> List[str]:
        """从文本中提取英文单词
        
        只取最长的单词，假设高亮的是完整单词，周围的是干扰
        """
        if not text:
            return []
        
        words = re.findall(r'[a-zA-Z]{2,}', text)
        
        if not words:
            return []
        
        # 只返回最长的单词
        longest_word = max(words, key=len)
        return [longest_word.lower()]


class BackgroundOCRManager(QObject):
    """后台 OCR 管理器 - 管理高亮区域的异步 OCR 任务
    
    Property 1: OCR 缓存管理一致性
    - 创建高亮区域后，应存在对应的 OCR 任务或结果
    - 删除高亮区域后，对应的 OCR 任务应被取消，结果应被清除
    - 清除所有绘制后，缓存应为空
    """
    
    # 信号
    taskCompleted = Signal(int, list)  # (item_id, words)
    taskError = Signal(int, str)       # (item_id, error_msg)
    allTasksCompleted = Signal()       # 所有任务完成
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[int, OCRTask] = {}
        self._workers: Dict[int, OCRWorkerThread] = {}
        self._mutex = QMutex()
        self._base_image: Optional[QImage] = None
    
    def set_base_image(self, image: QImage) -> None:
        """设置基础截图（用于裁剪高亮区域）
        
        注意：设置新图片前会释放旧图片的内存
        """
        # 先释放旧图片
        if self._base_image is not None:
            del self._base_image
            self._base_image = None
        
        # 设置新图片
        self._base_image = image.copy() if image and not image.isNull() else None
        if image and not image.isNull():
            debug_log(f"设置基础截图: {image.width()}x{image.height()}", "OCR_MGR")
        else:
            debug_log("设置基础截图: None", "OCR_MGR")
    
    def submit_task(self, item_id: int, rect: QRect) -> None:
        """提交 OCR 任务
        
        Args:
            item_id: DrawItem 的唯一 ID
            rect: 高亮区域（相对于截图的坐标）
        """
        self._mutex.lock()
        try:
            # 如果已存在相同 ID 的任务，先取消
            if item_id in self._tasks:
                self._cancel_task_internal(item_id)
            
            # 创建新任务
            task = OCRTask(item_id=item_id, rect=rect, status=TaskStatus.PENDING)
            self._tasks[item_id] = task
            
            debug_log(f"提交 OCR 任务: item_id={item_id}, rect=({rect.x()},{rect.y()},{rect.width()}x{rect.height()})", "OCR_MGR")
            
            # 如果有基础图片，立即启动工作线程
            if self._base_image is not None and not self._base_image.isNull():
                self._start_worker(item_id, task)
            else:
                debug_log(f"基础图片为空，任务 {item_id} 等待图片设置", "OCR_MGR")
        finally:
            self._mutex.unlock()
    
    def _start_worker(self, item_id: int, task: OCRTask) -> None:
        """启动工作线程（内部方法，需要在锁内调用）"""
        task.status = TaskStatus.RUNNING
        
        worker = OCRWorkerThread(item_id, self._base_image, task.rect)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        self._workers[item_id] = worker
        worker.start()
    
    def cancel_task(self, item_id: int) -> None:
        """取消指定任务"""
        self._mutex.lock()
        try:
            self._cancel_task_internal(item_id)
        finally:
            self._mutex.unlock()
    
    def _cancel_task_internal(self, item_id: int) -> None:
        """取消任务（内部方法，需要在锁内调用）"""
        if item_id in self._workers:
            worker = self._workers[item_id]
            worker.cancel()
            if worker.isRunning():
                worker.quit()
                # 等待线程结束，超时则放弃（不使用 terminate() 避免崩溃）
                if not worker.wait(1000):
                    debug_log(f"OCR worker {item_id} 等待超时，放弃等待让线程自然结束", "OCR_MGR")
                    # 不使用 terminate()，避免 OpenVINO 推理时崩溃
                    del self._workers[item_id]
                    if item_id in self._tasks:
                        self._tasks[item_id].status = TaskStatus.CANCELLED
                        del self._tasks[item_id]
                    return
            try:
                worker.finished.disconnect()
                worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
            worker.deleteLater()
            del self._workers[item_id]
        
        if item_id in self._tasks:
            self._tasks[item_id].status = TaskStatus.CANCELLED
            del self._tasks[item_id]
        
        debug_log(f"取消 OCR 任务: item_id={item_id}", "OCR_MGR")
    
    def cancel_all_tasks(self) -> None:
        """取消所有任务"""
        self._mutex.lock()
        try:
            item_ids = list(self._tasks.keys())
            for item_id in item_ids:
                self._cancel_task_internal(item_id)
            self._tasks.clear()
            debug_log("取消所有 OCR 任务", "OCR_MGR")
        finally:
            self._mutex.unlock()
    
    def get_result(self, item_id: int) -> Optional[List[str]]:
        """获取指定任务的结果"""
        self._mutex.lock()
        try:
            task = self._tasks.get(item_id)
            if task and task.status == TaskStatus.COMPLETED:
                return task.result.copy()
            return None
        finally:
            self._mutex.unlock()
    
    def get_all_results(self) -> List[str]:
        """获取所有已完成任务的结果（去重）
        
        Property 2: 单词列表去重与完整性
        - 包含所有已完成 OCR 任务识别出的英文单词
        - 不包含重复单词（不区分大小写）
        - 单词顺序与高亮区域创建顺序一致
        """
        self._mutex.lock()
        try:
            all_words = []
            seen = set()
            
            # 按 item_id 排序，保持创建顺序
            for item_id in sorted(self._tasks.keys()):
                task = self._tasks[item_id]
                if task.status == TaskStatus.COMPLETED:
                    for word in task.result:
                        word_lower = word.lower()
                        if word_lower not in seen:
                            seen.add(word_lower)
                            all_words.append(word)
            
            debug_log(f"获取所有 OCR 结果: {len(all_words)} 个单词", "OCR_MGR")
            return all_words
        finally:
            self._mutex.unlock()
    
    def has_pending_tasks(self) -> bool:
        """是否有未完成的任务"""
        self._mutex.lock()
        try:
            return self._has_pending_tasks_internal()
        finally:
            self._mutex.unlock()
    
    def _has_pending_tasks_internal(self) -> bool:
        """是否有未完成的任务（内部方法，需要在锁内调用）"""
        for task in self._tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return True
        return False
    
    def get_pending_count(self) -> int:
        """获取未完成任务数量"""
        self._mutex.lock()
        try:
            count = 0
            for task in self._tasks.values():
                if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    count += 1
            return count
        finally:
            self._mutex.unlock()
    
    def get_task_count(self) -> int:
        """获取任务总数"""
        self._mutex.lock()
        try:
            return len(self._tasks)
        finally:
            self._mutex.unlock()
    
    def wait_all_complete(self, timeout_ms: int = 5000) -> bool:
        """等待所有任务完成
        
        注意：此方法会处理 Qt 事件循环，避免 UI 阻塞
        
        Args:
            timeout_ms: 超时时间（毫秒）
            
        Returns:
            bool: 是否所有任务都已完成
        """
        from PySide6.QtCore import QCoreApplication, QElapsedTimer
        
        timer = QElapsedTimer()
        timer.start()
        
        while self.has_pending_tasks():
            if timer.elapsed() > timeout_ms:
                debug_log(f"等待 OCR 任务超时: {timeout_ms}ms", "OCR_MGR")
                return False
            # 处理事件循环，避免 UI 阻塞
            QCoreApplication.processEvents()
        
        debug_log("所有 OCR 任务已完成", "OCR_MGR")
        return True
    
    def _on_worker_finished(self, item_id: int, words: List[str]) -> None:
        """工作线程完成回调"""
        all_done = False
        self._mutex.lock()
        try:
            if item_id in self._tasks:
                task = self._tasks[item_id]
                task.status = TaskStatus.COMPLETED
                task.result = words
                debug_log(f"OCR 任务完成: item_id={item_id}, words={words}", "OCR_MGR")
            
            # 清理 worker
            if item_id in self._workers:
                worker = self._workers[item_id]
                try:
                    worker.finished.disconnect()
                    worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass
                worker.deleteLater()
                del self._workers[item_id]
            
            # 检查是否所有任务都完成（在锁内检查，避免死锁）
            all_done = not self._has_pending_tasks_internal()
        finally:
            self._mutex.unlock()
        
        # 发送信号（在锁外）
        self.taskCompleted.emit(item_id, words)
        if all_done:
            self.allTasksCompleted.emit()
    
    def _on_worker_error(self, item_id: int, error_msg: str) -> None:
        """工作线程错误回调"""
        all_done = False
        self._mutex.lock()
        try:
            if item_id in self._tasks:
                task = self._tasks[item_id]
                task.status = TaskStatus.ERROR
                task.error = error_msg
                debug_log(f"OCR 任务错误: item_id={item_id}, error={error_msg}", "OCR_MGR")
            
            # 清理 worker
            if item_id in self._workers:
                worker = self._workers[item_id]
                try:
                    worker.finished.disconnect()
                    worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass
                worker.deleteLater()
                del self._workers[item_id]
            
            # 检查是否所有任务都完成（在锁内检查，避免死锁）
            all_done = not self._has_pending_tasks_internal()
        finally:
            self._mutex.unlock()
        
        # 发送信号（在锁外）
        self.taskError.emit(item_id, error_msg)
        if all_done:
            self.allTasksCompleted.emit()
    
    def cleanup(self) -> None:
        """清理资源"""
        self.cancel_all_tasks()
        self._base_image = None
