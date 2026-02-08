# =====================================================
# =============== 批量 URL 转 Markdown 对话框 ===============
# =====================================================

"""
批量 URL 转 Markdown 对话框

提供多行 URL 输入、批量转换、进度显示和结果展示功能。

Feature: batch-url-markdown
Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.5
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QPushButton, QGroupBox, QProgressBar,
    QWidget, QMessageBox
)

from .styles import DIALOG_STYLE, GROUPBOX_STYLE, INPUT_STYLE
from .ui_components import ModernButton

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import MarkdownConfig
    from screenshot_tool.services.markdown_converter import ConversionResult


@dataclass
class BatchConversionState:
    """批量转换状态
    
    Feature: batch-url-markdown
    Requirements: 3.3, 5.2
    """
    urls: List[str] = field(default_factory=list)
    results: Dict[str, "ConversionResult"] = field(default_factory=dict)
    current_index: int = 0
    is_running: bool = False
    is_cancelled: bool = False
    
    @property
    def success_count(self) -> int:
        """成功数量"""
        return sum(1 for r in self.results.values() if r.success)
    
    @property
    def failure_count(self) -> int:
        """失败数量"""
        return sum(1 for r in self.results.values() if not r.success)
    
    @property
    def failed_urls(self) -> List[str]:
        """失败的 URL 列表，保持原始顺序
        
        Property 7: Retry List Correctness
        """
        return [url for url in self.urls if url in self.results and not self.results[url].success]
    
    def reset(self):
        """重置状态"""
        self.urls = []
        self.results = {}
        self.current_index = 0
        self.is_running = False
        self.is_cancelled = False


class BatchConversionWorker(QThread):
    """批量转换工作线程
    
    Feature: batch-url-markdown
    Requirements: 2.3, 2.4, 2.6
    """
    
    # 信号定义
    progress_updated = Signal(int, int, str)  # current, total, url
    url_converted = Signal(str, object)  # url, ConversionResult
    all_completed = Signal(int, int)  # success_count, failure_count
    error_occurred = Signal(str)  # error_message
    
    def __init__(self, urls: List[str], config: "MarkdownConfig"):
        """初始化工作线程
        
        Args:
            urls: 要转换的 URL 列表
            config: Markdown 配置对象
        """
        super().__init__()
        self._urls = urls
        self._config = config
        self._cancelled = False
    
    def run(self):
        """执行批量转换"""
        from screenshot_tool.services.markdown_converter import MarkdownConverter
        
        converter = MarkdownConverter(self._config)
        total = len(self._urls)
        success_count = 0
        failure_count = 0
        
        for i, url in enumerate(self._urls):
            if self._cancelled:
                _debug_log(f"批量转换已取消，已完成 {i}/{total}", "BATCH_MD")
                break
            
            # 发送进度更新
            self.progress_updated.emit(i + 1, total, url)
            _debug_log(f"正在转换 {i + 1}/{total}: {url}", "BATCH_MD")
            
            try:
                result = converter.convert(url)
                self.url_converted.emit(url, result)
                
                if result.success:
                    success_count += 1
                else:
                    failure_count += 1
                    
            except Exception as e:
                _debug_log(f"转换异常: {url} - {e}", "BATCH_MD")
                # 创建失败结果
                from screenshot_tool.services.markdown_converter import ConversionResult
                result = ConversionResult(success=False, error=str(e))
                self.url_converted.emit(url, result)
                failure_count += 1
        
        # 发送完成信号
        self.all_completed.emit(success_count, failure_count)
        _debug_log(f"批量转换完成: {success_count} 成功, {failure_count} 失败", "BATCH_MD")
    
    def cancel(self):
        """取消转换"""
        self._cancelled = True
        _debug_log("请求取消批量转换", "BATCH_MD")


class BatchUrlDialog(QDialog):
    """批量 URL 转 Markdown 对话框
    
    Feature: batch-url-markdown
    Requirements: 1.2, 1.3, 1.4, 1.5
    """
    
    # 信号定义
    conversion_started = Signal()
    conversion_finished = Signal()
    
    def __init__(self, config: "MarkdownConfig", parent: Optional[QWidget] = None):
        """初始化对话框
        
        Args:
            config: Markdown 配置对象
            parent: 父窗口
        """
        super().__init__(parent)
        self._config = config
        self._state = BatchConversionState()
        self._worker: Optional[BatchConversionWorker] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("📝 批量 URL 转 Markdown")
        self.setMinimumSize(600, 500)
        self.resize(700, 600)
        self.setStyleSheet(DIALOG_STYLE)
        
        # 允许调整大小
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # URL 输入区域
        input_group = QGroupBox("URL 输入")
        input_group.setStyleSheet(GROUPBOX_STYLE)
        input_layout = QVBoxLayout(input_group)
        
        self._url_input = QTextEdit()
        self._url_input.setStyleSheet(INPUT_STYLE)
        self._url_input.setPlaceholderText(
            "每行输入一个 URL 地址，例如：\n"
            "https://example.com/article1\n"
            "https://example.com/article2\n"
            "https://news.site.com/news/12345\n\n"
            "支持 http:// 和 https:// 开头的网址"
        )
        self._url_input.setMinimumHeight(120)
        input_layout.addWidget(self._url_input)
        
        # URL 计数标签
        self._url_count_label = QLabel("已输入 0 个有效 URL")
        self._url_count_label.setStyleSheet("color: #888;")
        input_layout.addWidget(self._url_count_label)
        
        # 连接文本变化信号
        self._url_input.textChanged.connect(self._on_url_input_changed)
        
        layout.addWidget(input_group)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)
        
        # 结果显示区域
        result_group = QGroupBox("转换结果")
        result_group.setStyleSheet(GROUPBOX_STYLE)
        result_layout = QVBoxLayout(result_group)
        
        self._result_display = QTextEdit()
        self._result_display.setStyleSheet(INPUT_STYLE)
        self._result_display.setReadOnly(True)
        self._result_display.setPlaceholderText("转换结果将显示在这里...")
        self._result_display.setMinimumHeight(150)
        result_layout.addWidget(self._result_display)
        
        layout.addWidget(result_group)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        
        # 开始转换按钮
        self._start_btn = ModernButton("🚀 开始转换", ModernButton.PRIMARY)
        self._start_btn.clicked.connect(self._start_conversion)
        btn_layout.addWidget(self._start_btn)
        
        # 取消按钮（转换时显示）
        self._cancel_btn = ModernButton("⏹ 取消", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self._cancel_conversion)
        self._cancel_btn.setVisible(False)
        btn_layout.addWidget(self._cancel_btn)
        
        # 重试失败项按钮
        self._retry_btn = ModernButton("🔄 重试失败项", ModernButton.SECONDARY)
        self._retry_btn.clicked.connect(self._retry_failed)
        self._retry_btn.setEnabled(False)
        btn_layout.addWidget(self._retry_btn)
        
        btn_layout.addStretch()
        
        # 打开目录按钮
        self._open_dir_btn = ModernButton("📂 打开目录", ModernButton.SECONDARY)
        self._open_dir_btn.clicked.connect(self._open_save_directory)
        self._open_dir_btn.setEnabled(False)
        btn_layout.addWidget(self._open_dir_btn)
        
        # 复制结果按钮
        self._copy_btn = ModernButton("📋 复制结果", ModernButton.SECONDARY)
        self._copy_btn.clicked.connect(self._copy_results)
        self._copy_btn.setEnabled(False)
        btn_layout.addWidget(self._copy_btn)
        
        # 关闭按钮
        self._close_btn = ModernButton("关闭", ModernButton.SECONDARY)
        self._close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self._close_btn)
        
        layout.addLayout(btn_layout)

    def _on_url_input_changed(self):
        """URL 输入变化时更新计数"""
        text = self._url_input.toPlainText()
        urls = self._parse_urls(text)
        count = len(urls)
        self._url_count_label.setText(f"已输入 {count} 个有效 URL")
    
    def _is_valid_url(self, url: str) -> bool:
        """验证 URL 格式
        
        Property 1: URL Validation Correctness
        
        Args:
            url: URL 字符串
            
        Returns:
            是否为有效 URL
            
        Requirements: 1.6
        """
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        
        # 检查协议
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        
        # 基本格式检查
        try:
            # 移除协议前缀
            if url.startswith("https://"):
                rest = url[8:]
            else:
                rest = url[7:]
            
            # 必须有主机名部分
            if not rest or rest.startswith("/"):
                return False
            
            # 主机名不能包含空格或换行
            host_part = rest.split("/")[0].split("?")[0].split("#")[0]
            if not host_part or " " in host_part or "\n" in host_part or "\r" in host_part:
                return False
            
            return True
        except Exception:
            return False
    
    def _parse_urls(self, text: str) -> List[str]:
        """解析文本中的有效 URL
        
        Property 2: URL Parsing Completeness
        
        Args:
            text: 多行文本，每行一个 URL
            
        Returns:
            有效 URL 列表，保持原始顺序
            
        Requirements: 2.1
        """
        if not text:
            return []
        
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if line and self._is_valid_url(line):
                urls.append(line)
        
        return urls
    
    def _format_success_result(self, url: str, filename: str) -> str:
        """格式化成功结果
        
        Property 4: Success Result Formatting
        
        Args:
            url: 原始 URL
            filename: 保存的文件名
            
        Returns:
            格式化的结果字符串
            
        Requirements: 3.1
        """
        return f"✓ {url} → {filename}"
    
    def _format_failure_result(self, url: str, error: str) -> str:
        """格式化失败结果
        
        Property 5: Failure Result Formatting
        
        Args:
            url: 原始 URL
            error: 错误信息
            
        Returns:
            格式化的结果字符串
            
        Requirements: 3.2
        """
        return f"✗ {url} - {error}"
    
    def _generate_summary(self, success_count: int, failure_count: int) -> str:
        """生成转换摘要
        
        Property 3: Summary Generation Accuracy
        
        Args:
            success_count: 成功数量
            failure_count: 失败数量
            
        Returns:
            摘要字符串
            
        Requirements: 2.5
        """
        return f"完成：{success_count} 成功，{failure_count} 失败"
    
    def _cleanup_worker(self):
        """清理工作线程资源
        
        断开信号连接，等待线程结束，释放资源。
        """
        if self._worker is not None:
            # 断开所有信号连接，防止已销毁对象收到信号
            try:
                self._worker.progress_updated.disconnect()
                self._worker.url_converted.disconnect()
                self._worker.all_completed.disconnect()
                self._worker.error_occurred.disconnect()
            except (RuntimeError, TypeError):
                # 信号可能已经断开或对象已销毁
                pass
            
            # 如果线程还在运行，取消并等待
            if self._worker.isRunning():
                self._worker.cancel()
                self._worker.wait(3000)  # 等待最多 3 秒
                if self._worker.isRunning():
                    _debug_log("警告: 工作线程未能在 3 秒内结束", "BATCH_MD")
            
            self._worker = None
    
    def _start_conversion(self):
        """开始批量转换
        
        Requirements: 2.1, 2.2
        """
        text = self._url_input.toPlainText()
        urls = self._parse_urls(text)
        
        if not urls:
            QMessageBox.warning(self, "提示", "未找到有效的 URL 地址")
            return
        
        # 检查保存目录
        save_dir = self._config.get_save_dir()
        try:
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存目录不可访问：{save_dir}\n{e}")
            return
        
        # 清理旧的工作线程（如果存在）
        self._cleanup_worker()
        
        # 重置状态
        self._state.reset()
        self._state.urls = urls
        self._state.is_running = True
        
        # 更新 UI
        self._result_display.clear()
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(len(urls))
        self._progress_bar.setValue(0)
        
        self._start_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._retry_btn.setEnabled(False)
        self._open_dir_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._url_input.setEnabled(False)
        
        # 创建并启动工作线程
        self._worker = BatchConversionWorker(urls, self._config)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.url_converted.connect(self._on_url_converted)
        self._worker.all_completed.connect(self._on_all_completed)
        self._worker.error_occurred.connect(self._on_error_occurred)
        self._worker.start()
        
        self.conversion_started.emit()
        _debug_log(f"开始批量转换 {len(urls)} 个 URL", "BATCH_MD")
    
    def _cancel_conversion(self):
        """取消转换
        
        Requirements: 2.6
        """
        if self._worker and self._worker.isRunning():
            self._state.is_cancelled = True
            self._worker.cancel()
            self._result_display.append("\n⚠ 转换已取消")
    
    def _retry_failed(self):
        """重试失败的 URL
        
        Property 7: Retry List Correctness
        
        Requirements: 5.2, 5.3
        """
        failed_urls = self._state.failed_urls
        if not failed_urls:
            return
        
        # 将失败的 URL 填入输入框
        self._url_input.setPlainText("\n".join(failed_urls))
        self._result_display.clear()
        self._retry_btn.setEnabled(False)
        
        _debug_log(f"准备重试 {len(failed_urls)} 个失败的 URL", "BATCH_MD")
    
    def _on_progress_updated(self, current: int, total: int, url: str):
        """进度更新回调
        
        Requirements: 2.3
        """
        self._progress_bar.setValue(current)
        self._progress_bar.setFormat(f"正在转换 {current}/{total}")
        self._state.current_index = current
    
    def _on_url_converted(self, url: str, result: "ConversionResult"):
        """单个 URL 转换完成回调
        
        Requirements: 2.4, 3.1, 3.2
        """
        self._state.results[url] = result
        
        if result.success:
            # 安全获取文件名，处理空路径情况
            filename = os.path.basename(result.file_path) if result.file_path else "unknown.md"
            line = self._format_success_result(url, filename)
        else:
            line = self._format_failure_result(url, result.error or "未知错误")
        
        self._result_display.append(line)
    
    def _on_all_completed(self, success_count: int, failure_count: int):
        """全部完成回调
        
        Requirements: 2.5, 3.3, 5.2
        """
        self._state.is_running = False
        
        # 更新 UI
        self._progress_bar.setVisible(False)
        self._start_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._url_input.setEnabled(True)
        self._open_dir_btn.setEnabled(True)
        self._copy_btn.setEnabled(True)
        
        # 如果有失败项，启用重试按钮
        if failure_count > 0:
            self._retry_btn.setEnabled(True)
        
        # 显示摘要
        summary = self._generate_summary(success_count, failure_count)
        self._result_display.append(f"\n{'='*50}\n{summary}")
        
        self.conversion_finished.emit()
    
    def _on_error_occurred(self, error_message: str):
        """错误回调
        
        Requirements: 5.1
        """
        _debug_log(f"批量转换错误: {error_message}", "BATCH_MD")
        self._result_display.append(f"\n⚠ 错误: {error_message}")
    
    def _open_save_directory(self):
        """打开保存目录
        
        Requirements: 3.3
        """
        save_dir = self._config.get_save_dir()
        if os.path.exists(save_dir):
            # Windows 下使用 explorer 打开
            subprocess.Popen(['explorer', save_dir])
        else:
            QMessageBox.warning(self, "提示", f"目录不存在：{save_dir}")
    
    def _copy_results(self):
        """复制结果到剪贴板
        
        Requirements: 3.4
        """
        from PySide6.QtWidgets import QApplication
        
        text = self._result_display.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            _debug_log("结果已复制到剪贴板", "BATCH_MD")
    
    def closeEvent(self, event):
        """关闭事件
        
        Requirements: 3.5
        """
        # 清理工作线程资源
        self._cleanup_worker()
        
        # 清理状态
        self._state.reset()
        
        super().closeEvent(event)
