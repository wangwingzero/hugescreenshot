# -*- coding: utf-8 -*-
"""
后台 OCR 缓存管理器

在系统空闲时自动执行 OCR 并缓存结果，提升工作台 OCR 预览的响应速度。

Feature: background-ocr-cache

设计原则：
1. 用户无感：只在系统空闲且资源充足时执行
2. 优雅中断：用户活动时立即停止
3. 分片处理：每处理一张图片后检查系统状态
4. 低优先级：使用最低优先级线程，不影响前台任务
"""

import ctypes
from ctypes import wintypes
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List

import psutil
from PySide6.QtCore import QObject, Signal, QTimer, QThread

if TYPE_CHECKING:
    from screenshot_tool.core.clipboard_history_manager import (
        ClipboardHistoryManager,
        HistoryItem,
    )
    from screenshot_tool.services.ocr_manager import OCRManager


class LastInputInfo(ctypes.Structure):
    """Windows LASTINPUTINFO 结构体"""
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('dwTime', wintypes.DWORD),
    ]


def get_idle_duration_ms() -> int:
    """获取用户空闲时间（毫秒）
    
    使用 Windows GetLastInputInfo API 检测用户最后一次输入时间。
    
    Returns:
        空闲时间（毫秒）
    """
    try:
        last_input_info = LastInputInfo()
        last_input_info.cbSize = ctypes.sizeof(LastInputInfo)
        
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
            millis = ctypes.windll.kernel32.GetTickCount() - last_input_info.dwTime
            return millis
        return 0
    except Exception:
        return 0


class OCRWorker(QThread):
    """后台 OCR 工作线程
    
    使用最低优先级执行 OCR，避免影响前台任务。
    
    Feature: background-ocr-cache
    """
    
    # 信号
    ocr_completed = Signal(str, str)  # (item_id, ocr_text)
    ocr_failed = Signal(str, str)  # (item_id, error_message)
    batch_completed = Signal()  # 批次完成
    
    def __init__(
        self,
        ocr_manager: 'OCRManager',
        items: List['HistoryItem'],
        data_dir: str,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._ocr_manager = ocr_manager
        self._items = items
        self._data_dir = data_dir
        self._should_stop = False
        
        # 注意：setPriority 必须在线程启动后调用
        # 在 run() 方法开始时设置优先级
        # Bug fix: QThread::setPriority warning (2026-01-23)
    
    def request_stop(self) -> None:
        """请求停止处理"""
        self._should_stop = True
    
    def run(self) -> None:
        """执行后台 OCR 处理"""
        import os
        from PySide6.QtGui import QImage
        
        # 设置最低优先级（必须在线程启动后设置）
        # Bug fix: QThread::setPriority warning (2026-01-23)
        self.setPriority(QThread.Priority.LowestPriority)
        
        for item in self._items:
            # 检查是否应该停止
            if self._should_stop:
                break
            
            # 检查用户是否活动（空闲时间小于 5 秒则停止）
            if get_idle_duration_ms() < 5000:
                break
            
            # 检查内存使用（超过 70% 则停止）
            if psutil.virtual_memory().percent > 70:
                break
            
            # 跳过非图片类型
            if item.image_path is None:
                continue
            
            # 跳过已有缓存的
            if item.has_ocr_cache():
                continue
            
            try:
                # 加载图片
                image_path = os.path.join(self._data_dir, item.image_path)
                if not os.path.exists(image_path):
                    continue
                
                image = QImage(image_path)
                if image.isNull():
                    continue
                
                # 执行 OCR
                ocr_result = self._ocr_manager.recognize(image)
                
                if ocr_result and ocr_result.text:
                    self.ocr_completed.emit(item.id, ocr_result.text)
                else:
                    # OCR 结果为空，也标记为已处理（避免重复处理）
                    self.ocr_completed.emit(item.id, "")
                    
            except Exception as e:
                self.ocr_failed.emit(item.id, str(e))
        
        self.batch_completed.emit()


class BackgroundOCRCacheManager(QObject):
    """后台 OCR 缓存管理器
    
    在系统空闲时自动执行 OCR 并缓存结果。
    
    Feature: background-ocr-cache
    
    工作流程：
    1. 程序启动后延迟启动（避免影响启动速度）
    2. 定期检查系统空闲状态
    3. 空闲且资源充足时，启动后台 OCR 线程
    4. 用户活动时立即停止
    5. OCR 结果缓存到 HistoryItem
    """
    
    # 配置常量
    STARTUP_DELAY_MS = 30000  # 启动延迟 30 秒
    CHECK_INTERVAL_MS = 10000  # 检查间隔 10 秒
    IDLE_THRESHOLD_MS = 30000  # 空闲阈值 30 秒
    MEMORY_THRESHOLD_PERCENT = 70  # 内存阈值 70%
    BATCH_SIZE = 5  # 每批处理数量
    
    def __init__(
        self,
        clipboard_manager: 'ClipboardHistoryManager',
        ocr_manager: 'OCRManager',
        parent: Optional[QObject] = None,
    ):
        """初始化后台 OCR 缓存管理器
        
        Args:
            clipboard_manager: 工作台管理器
            ocr_manager: OCR 管理器
            parent: 父对象
        """
        super().__init__(parent)
        
        self._clipboard_manager = clipboard_manager
        self._ocr_manager = ocr_manager
        self._worker: Optional[OCRWorker] = None
        self._running = False
        
        # 检查定时器
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(self.CHECK_INTERVAL_MS)
        self._check_timer.timeout.connect(self._check_and_process)
        
        # 启动延迟定时器
        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.setInterval(self.STARTUP_DELAY_MS)
        self._startup_timer.timeout.connect(self._delayed_start)
    
    def start(self) -> None:
        """启动后台 OCR 缓存管理器（延迟启动）"""
        if self._running:
            return
        
        # 延迟启动，避免影响程序启动速度
        self._startup_timer.start()
    
    def _delayed_start(self) -> None:
        """延迟启动后的实际启动"""
        self._running = True
        self._check_timer.start()
        
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log("后台 OCR 缓存管理器已启动", "OCR-CACHE")
    
    def stop(self) -> None:
        """停止后台 OCR 缓存管理器"""
        self._running = False
        self._startup_timer.stop()
        self._check_timer.stop()
        
        # 停止正在运行的 worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(1000)  # 等待最多 1 秒
        
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log("后台 OCR 缓存管理器已停止", "OCR-CACHE")
    
    def _check_and_process(self) -> None:
        """检查系统状态并决定是否处理"""
        # 如果已有 worker 在运行，跳过
        if self._worker is not None and self._worker.isRunning():
            return
        
        # 检查用户是否空闲
        idle_ms = get_idle_duration_ms()
        if idle_ms < self.IDLE_THRESHOLD_MS:
            return
        
        # 检查内存使用
        memory_percent = psutil.virtual_memory().percent
        if memory_percent > self.MEMORY_THRESHOLD_PERCENT:
            return
        
        # 获取待处理的图片
        items = self._get_items_without_ocr_cache()
        if not items:
            return
        
        # 限制批次大小
        batch = items[:self.BATCH_SIZE]
        
        # 启动后台处理
        self._start_ocr_worker(batch)
    
    def _get_items_without_ocr_cache(self) -> List['HistoryItem']:
        """获取没有 OCR 缓存的图片条目
        
        Returns:
            待处理的 HistoryItem 列表
        """
        from screenshot_tool.core.clipboard_history_manager import ContentType
        
        items = []
        for item in self._clipboard_manager.get_history():
            # 只处理图片类型
            if item.content_type != ContentType.IMAGE:
                continue
            
            # 跳过已有缓存的
            if item.has_ocr_cache():
                continue
            
            # 跳过没有图片路径的
            if item.image_path is None:
                continue
            
            items.append(item)
        
        return items
    
    def _start_ocr_worker(self, items: List['HistoryItem']) -> None:
        """启动 OCR 工作线程
        
        Args:
            items: 待处理的条目列表
        """
        from screenshot_tool.core.clipboard_history_manager import get_clipboard_data_dir
        
        data_dir = get_clipboard_data_dir()
        
        self._worker = OCRWorker(
            self._ocr_manager,
            items,
            data_dir,
            self,
        )
        
        # 连接信号
        self._worker.ocr_completed.connect(self._on_ocr_completed)
        self._worker.ocr_failed.connect(self._on_ocr_failed)
        self._worker.batch_completed.connect(self._on_batch_completed)
        
        # 线程完成后自动清理（最佳实践：使用 deleteLater 避免内存泄漏）
        self._worker.finished.connect(self._on_worker_finished)
        
        # 启动线程
        self._worker.start()
        
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log(f"后台 OCR 开始处理 {len(items)} 张图片", "OCR-CACHE")
    
    def _on_worker_finished(self) -> None:
        """工作线程完成回调
        
        最佳实践：使用 deleteLater() 在事件循环中安全删除线程对象
        """
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
    
    def _on_ocr_completed(self, item_id: str, ocr_text: str) -> None:
        """OCR 完成回调
        
        Args:
            item_id: 条目 ID
            ocr_text: OCR 结果文本
        """
        # 更新缓存
        item = self._clipboard_manager.get_item(item_id)
        if item is not None:
            item.ocr_cache = ocr_text
            item.ocr_cache_timestamp = datetime.now()
            
            # 保存到文件（延迟保存）
            self._clipboard_manager.save()
    
    def _on_ocr_failed(self, item_id: str, error_message: str) -> None:
        """OCR 失败回调
        
        Args:
            item_id: 条目 ID
            error_message: 错误信息
        """
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log(f"后台 OCR 失败 [{item_id}]: {error_message}", "OCR-CACHE")
    
    def _on_batch_completed(self) -> None:
        """批次完成回调"""
        from screenshot_tool.core.async_logger import async_debug_log
        async_debug_log("后台 OCR 批次处理完成", "OCR-CACHE")
    
    def cleanup(self) -> None:
        """清理资源"""
        self.stop()
        
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
