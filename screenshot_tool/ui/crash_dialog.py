# =====================================================
# =============== 崩溃对话框 ===============
# =====================================================

"""
崩溃对话框 - 显示友好的错误提示

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import os
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon


class CrashDialog(QDialog):
    """崩溃对话框 - 显示友好的错误提示"""
    
    def __init__(
        self, 
        error_message: str, 
        log_path: str, 
        version: str = "",
        parent=None
    ):
        """
        初始化崩溃对话框
        
        Args:
            error_message: 错误消息（包含堆栈跟踪）
            log_path: 日志文件路径
            version: 应用版本号
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._error_message = error_message
        self._log_path = log_path
        self._version = version
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置界面"""
        self.setWindowTitle("虎哥截图 - 程序错误")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("😢 程序遇到了问题")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 说明文字
        desc_text = (
            "程序发生了意外错误。错误信息已记录到日志文件。\n"
            "请将日志文件发送给开发者以帮助修复问题。"
        )
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)
        
        # 日志文件位置
        log_layout = QHBoxLayout()
        log_label = QLabel("📁 日志文件:")
        log_label.setStyleSheet("font-weight: bold;")
        log_layout.addWidget(log_label)
        
        log_path_label = QLabel(self._log_path)
        log_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        log_path_label.setStyleSheet(
            "color: #0066cc; "
            "background-color: #f0f0f0; "
            "padding: 5px; "
            "border-radius: 3px;"
        )
        log_layout.addWidget(log_path_label, 1)
        layout.addLayout(log_layout)
        
        # 打开日志文件夹按钮
        open_folder_btn = QPushButton("📂 打开日志文件夹")
        open_folder_btn.clicked.connect(self._open_log_folder)
        layout.addWidget(open_folder_btn)
        
        # 错误详情
        detail_label = QLabel("错误详情:")
        detail_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(detail_label)
        
        self._error_text = QTextEdit()
        self._error_text.setPlainText(self._error_message)
        self._error_text.setReadOnly(True)
        self._error_text.setFont(QFont("Consolas", 9))
        self._error_text.setStyleSheet(
            "background-color: #1e1e1e; "
            "color: #d4d4d4; "
            "border: 1px solid #333; "
            "border-radius: 5px; "
            "padding: 10px;"
        )
        layout.addWidget(self._error_text, 1)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 复制错误信息按钮
        copy_btn = QPushButton("📋 复制错误信息")
        copy_btn.clicked.connect(self._copy_error_to_clipboard)
        copy_btn.setStyleSheet(
            "QPushButton { "
            "  background-color: #0078d4; "
            "  color: white; "
            "  border: none; "
            "  padding: 8px 16px; "
            "  border-radius: 4px; "
            "} "
            "QPushButton:hover { "
            "  background-color: #106ebe; "
            "}"
        )
        btn_layout.addWidget(copy_btn)
        
        btn_layout.addStretch()
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { "
            "  background-color: #e0e0e0; "
            "  color: #333; "
            "  border: none; "
            "  padding: 8px 16px; "
            "  border-radius: 4px; "
            "} "
            "QPushButton:hover { "
            "  background-color: #d0d0d0; "
            "}"
        )
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _copy_error_to_clipboard(self):
        """复制错误信息到剪贴板"""
        clipboard = QApplication.clipboard()
        
        # 构建完整的错误报告
        report = f"""虎哥截图 错误报告
版本: {self._version}
日志文件: {self._log_path}

错误详情:
{self._error_message}
"""
        clipboard.setText(report)
        
        # 显示复制成功提示（临时修改按钮文字）
        sender = self.sender()
        if isinstance(sender, QPushButton):
            original_text = sender.text()
            sender.setText("✓ 已复制")
            sender.setEnabled(False)
            
            # 1.5秒后恢复
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self._restore_button(sender, original_text))
    
    def _restore_button(self, button: QPushButton, text: str):
        """恢复按钮状态"""
        try:
            # 检查按钮是否仍然有效（未被销毁）
            if button and not button.isHidden():
                button.setText(text)
                button.setEnabled(True)
        except RuntimeError:
            # 按钮已被销毁，忽略
            pass
    
    def _open_log_folder(self):
        """打开日志文件所在文件夹"""
        import subprocess
        
        log_dir = os.path.dirname(self._log_path)
        # 如果 log_dir 为空，使用日志文件所在的当前目录
        if not log_dir:
            log_dir = os.path.dirname(os.path.abspath(self._log_path))
        
        if os.path.exists(log_dir):
            try:
                subprocess.Popen(['explorer', log_dir])
            except OSError:
                # 如果 explorer 失败，尝试 os.startfile
                try:
                    os.startfile(log_dir)
                except OSError:
                    pass
        else:
            # 如果目录不存在，尝试打开用户目录
            user_dir = os.path.expanduser("~")
            try:
                subprocess.Popen(['explorer', user_dir])
            except OSError:
                pass


def show_crash_dialog(
    error_message: str, 
    log_path: str, 
    version: str = ""
) -> None:
    """
    显示崩溃对话框
    
    Args:
        error_message: 错误消息
        log_path: 日志文件路径
        version: 应用版本号
    """
    # 确保有 QApplication 实例
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    dialog = CrashDialog(error_message, log_path, version)
    dialog.exec()
