# =====================================================
# =============== 后台 Anki 导入管理器 ===============
# =====================================================

"""
后台 Anki 导入管理器 - 支持关闭窗口后继续导入

功能：
- 在后台线程中执行 Anki 导入任务
- 窗口关闭后仍能继续导入
- 导入完成后通过信号通知
"""

from PySide6.QtCore import QObject, QThread, Signal, QMutex, QMutexLocker
from typing import List, Optional, Callable
import os
import shutil
import tempfile
import uuid


class BackgroundAnkiWorker(QThread):
    """后台 Anki 导入线程"""
    progress = Signal(int, int, str)  # current, total, word
    finished = Signal(object)  # AnkiImportResult
    
    def __init__(
        self,
        words: List[str],
        deck_name: str,
        screenshot_path: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self._words = list(words) if words else []  # 复制列表，避免外部修改
        self._deck_name = deck_name or ""
        self._screenshot_path = screenshot_path
        self._cancelled = False
    
    @property
    def screenshot_path(self) -> Optional[str]:
        """获取截图路径（只读属性）"""
        return self._screenshot_path
    
    def cancel(self):
        """取消导入"""
        self._cancelled = True
    
    def run(self):
        try:
            from screenshot_tool.services.anki_service import AnkiService, AnkiImportResult
            
            service = AnkiService()
            
            # 如果没有单词，导入纯图片
            if not self._words:
                if self._screenshot_path and os.path.exists(self._screenshot_path):
                    result = service.import_image_only(self._screenshot_path, self._deck_name)
                else:
                    result = AnkiImportResult.error_result("没有单词也没有截图")
                self.finished.emit(result)
                return
            
            # 有单词时，导入单词卡
            def progress_callback(current, total, word):
                if self._cancelled:
                    raise InterruptedError("用户取消")
                self.progress.emit(current, total, word)
            
            result = service.import_words(
                self._words,
                self._deck_name,
                screenshot_path=self._screenshot_path,
                progress_callback=progress_callback
            )
            self.finished.emit(result)
            
        except InterruptedError:
            from screenshot_tool.services.anki_service import AnkiImportResult
            self.finished.emit(AnkiImportResult.error_result("已取消导入"))
        except Exception as e:
            from screenshot_tool.services.anki_service import AnkiImportResult
            self.finished.emit(AnkiImportResult.error_result(str(e)))


class BackgroundAnkiImporter(QObject):
    """后台 Anki 导入管理器（单例）
    
    管理独立于窗口的导入任务，支持：
    - 窗口关闭后继续导入
    - 导入完成后发送通知
    - 线程安全的任务管理
    """
    
    # 导入完成信号
    importFinished = Signal(object)  # AnkiImportResult
    # 导入进度信号
    importProgress = Signal(int, int, str)  # current, total, word
    
    _instance: Optional["BackgroundAnkiImporter"] = None
    _instance_lock = QMutex()  # 单例锁
    _creating_instance = False  # 标记是否正在创建实例
    
    @classmethod
    def instance(cls) -> "BackgroundAnkiImporter":
        """获取单例实例（线程安全）"""
        with QMutexLocker(cls._instance_lock):
            if cls._instance is None:
                cls._creating_instance = True
                try:
                    cls._instance = cls()
                finally:
                    cls._creating_instance = False
            return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        with QMutexLocker(cls._instance_lock):
            if cls._instance is not None:
                cls._instance.cleanup()
                cls._instance = None
    
    def __init__(self, parent=None):
        # 防止直接实例化（应使用 instance() 方法）
        if not BackgroundAnkiImporter._creating_instance and BackgroundAnkiImporter._instance is not None:
            raise RuntimeError("请使用 BackgroundAnkiImporter.instance() 获取实例")
        
        super().__init__(parent)
        self._workers: List[BackgroundAnkiWorker] = []
        self._temp_files: List[str] = []  # 跟踪临时文件
        self._mutex = QMutex()  # 保护 _workers 和 _temp_files
    
    def submit_import(
        self,
        words: List[str],
        deck_name: str,
        screenshot_path: Optional[str] = None,
        on_finished: Optional[Callable] = None
    ) -> bool:
        """提交导入任务
        
        Args:
            words: 要导入的单词列表
            deck_name: 目标牌组名称
            screenshot_path: 截图路径（可选）
            on_finished: 完成回调（可选）
        
        Returns:
            是否成功提交任务
        """
        # 参数验证
        if not deck_name:
            print("[BackgroundAnkiImporter] 牌组名称不能为空")
            return False
        
        # 如果有截图，复制到独立的临时文件（避免原文件被删除）
        managed_screenshot_path = None
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                temp_dir = tempfile.gettempdir()
                unique_id = uuid.uuid4().hex[:8]
                managed_screenshot_path = os.path.join(
                    temp_dir, f"anki_bg_import_{unique_id}.png"
                )
                shutil.copy2(screenshot_path, managed_screenshot_path)
                with QMutexLocker(self._mutex):
                    self._temp_files.append(managed_screenshot_path)
            except Exception as e:
                print(f"[BackgroundAnkiImporter] 复制截图失败: {e}")
                # 复制失败时使用原路径（可能会有问题，但至少尝试）
                managed_screenshot_path = screenshot_path
        
        # 创建后台 worker
        worker = BackgroundAnkiWorker(
            words=words or [],
            deck_name=deck_name,
            screenshot_path=managed_screenshot_path,
            parent=self
        )
        
        # 连接信号
        worker.progress.connect(self._on_progress)
        worker.finished.connect(lambda result: self._on_finished(worker, result, on_finished))
        
        with QMutexLocker(self._mutex):
            self._workers.append(worker)
        
        worker.start()
        
        return True
    
    def _on_progress(self, current: int, total: int, word: str):
        """进度回调"""
        self.importProgress.emit(current, total, word)
    
    def _on_finished(
        self,
        worker: BackgroundAnkiWorker,
        result,
        callback: Optional[Callable]
    ):
        """完成回调"""
        screenshot_path = worker.screenshot_path  # 使用属性访问
        
        with QMutexLocker(self._mutex):
            # 清理 worker
            if worker in self._workers:
                self._workers.remove(worker)
            
            # 清理临时文件
            if screenshot_path and screenshot_path in self._temp_files:
                try:
                    if os.path.exists(screenshot_path):
                        os.remove(screenshot_path)
                    self._temp_files.remove(screenshot_path)
                except Exception as e:
                    print(f"[BackgroundAnkiImporter] 清理临时文件失败: {e}")
        
        # 断开信号并清理（在锁外执行，避免死锁）
        try:
            worker.progress.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # 安全删除 worker
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        
        # 发送全局信号
        self.importFinished.emit(result)
        
        # 调用回调
        if callback:
            try:
                callback(result)
            except Exception as e:
                print(f"[BackgroundAnkiImporter] 回调执行失败: {e}")
    
    def has_pending_tasks(self) -> bool:
        """是否有待处理的任务"""
        with QMutexLocker(self._mutex):
            return len(self._workers) > 0
    
    def cancel_all(self):
        """取消所有任务"""
        with QMutexLocker(self._mutex):
            for worker in self._workers:
                worker.cancel()
    
    def cleanup(self):
        """清理资源"""
        with QMutexLocker(self._mutex):
            # 取消所有任务（不使用 terminate() 避免崩溃）
            for worker in self._workers:
                worker.cancel()
                if worker.isRunning():
                    worker.quit()
                    if not worker.wait(1000):
                        # 超时，放弃等待让线程自然结束（不使用 terminate()）
                        continue
                try:
                    worker.deleteLater()
                except RuntimeError:
                    pass
            self._workers.clear()
            
            # 清理临时文件
            for temp_file in self._temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass
            self._temp_files.clear()
