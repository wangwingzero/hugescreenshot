# =====================================================
# =============== 下载进度窗口 ===============
# =====================================================

"""
下载进度窗口 - 非模态窗口显示下载进度

Feature: simplify-update
Requirements: 2.4, 2.5, 2.6, 2.7, 2.9, 2.10
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal

from .styles import COLORS, DIALOG_STYLE, GROUPBOX_STYLE
from .ui_components import ModernButton


class DownloadProgressWindow(QWidget):
    """非模态下载进度窗口
    
    Feature: simplify-update
    Requirements: 2.4, 2.5, 2.6, 2.7, 2.9, 2.10
    """
    
    # 信号
    cancel_requested = Signal()
    
    def __init__(self, version: str, parent: Optional[QWidget] = None):
        """初始化进度窗口
        
        Args:
            version: 下载的版本号
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._version = version
        self._is_completed = False
        self._is_cancelled = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        # 设置窗口属性 - 非模态
        self.setWindowTitle(f"下载更新 v{self._version}")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumWidth(400)
        self.setStyleSheet(DIALOG_STYLE)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel(f"正在下载 v{self._version}")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #212529;
            }
        """)
        layout.addWidget(title_label)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E9ECEF;
                border-radius: 6px;
                background-color: #F8F9FA;
                height: 24px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4A90D9;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self._progress_bar)
        
        # 进度信息
        info_layout = QHBoxLayout()
        
        # 已下载/总大小
        self._size_label = QLabel("0 MB / 0 MB")
        self._size_label.setStyleSheet("color: #6C757D;")
        info_layout.addWidget(self._size_label)
        
        info_layout.addStretch()
        
        # 下载速度
        self._speed_label = QLabel("0 KB/s")
        self._speed_label.setStyleSheet("color: #6C757D;")
        info_layout.addWidget(self._speed_label)
        
        layout.addLayout(info_layout)
        
        # 状态标签（用于显示完成或错误信息）
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #6C757D;")
        self._status_label.hide()
        layout.addWidget(self._status_label)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #E9ECEF;")
        layout.addWidget(separator)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._cancel_btn = ModernButton("取消下载", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        
        self._close_btn = ModernButton("关闭", ModernButton.PRIMARY)
        self._close_btn.clicked.connect(self.close)
        self._close_btn.hide()
        btn_layout.addWidget(self._close_btn)
        
        layout.addLayout(btn_layout)
        
        # 调整窗口大小
        self.adjustSize()
    
    def update_progress(self, downloaded: int, total: int, speed: float) -> None:
        """更新进度显示
        
        Args:
            downloaded: 已下载字节数
            total: 总字节数
            speed: 下载速度 (KB/s)
            
        Feature: simplify-update
        Requirements: 2.4
        """
        if self._is_completed or self._is_cancelled:
            return
        
        # 计算百分比
        if total > 0:
            percentage = min(int((downloaded / total) * 100), 100)
        else:
            percentage = 0
        
        self._progress_bar.setValue(percentage)
        
        # 格式化大小显示
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        self._size_label.setText(f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB")
        
        # 格式化速度显示
        if speed >= 1024:
            self._speed_label.setText(f"{speed / 1024:.1f} MB/s")
        else:
            self._speed_label.setText(f"{speed:.0f} KB/s")
    
    def show_completed(self, file_path: str) -> None:
        """显示下载完成
        
        Args:
            file_path: 下载文件的保存路径
            
        Feature: simplify-update
        Requirements: 2.7
        """
        self._is_completed = True
        
        # 更新进度条到 100%
        self._progress_bar.setValue(100)
        
        # 更新标题
        self.setWindowTitle(f"下载完成 v{self._version}")
        
        # 显示完成信息
        self._status_label.setText(f"✅ 下载完成！\n\n文件已保存到：\n{file_path}\n\n请关闭当前程序后运行新版本。")
        self._status_label.setStyleSheet("color: #28A745; font-weight: bold;")
        self._status_label.show()
        
        # 隐藏速度标签
        self._speed_label.hide()
        
        # 切换按钮
        self._cancel_btn.hide()
        self._close_btn.show()
    
    def show_error(self, error_msg: str) -> None:
        """显示错误
        
        Args:
            error_msg: 错误信息
            
        Feature: simplify-update
        Requirements: 2.9
        """
        self._is_completed = True
        
        # 更新标题
        self.setWindowTitle(f"下载失败 v{self._version}")
        
        # 显示错误信息
        self._status_label.setText(f"❌ 下载失败\n\n{error_msg}")
        self._status_label.setStyleSheet("color: #DC3545; font-weight: bold;")
        self._status_label.show()
        
        # 隐藏速度标签
        self._speed_label.hide()
        
        # 切换按钮
        self._cancel_btn.hide()
        self._close_btn.show()
    
    def _on_cancel(self):
        """取消按钮点击"""
        self._is_cancelled = True
        self.cancel_requested.emit()
        
        # 更新状态
        self._status_label.setText("下载已取消")
        self._status_label.setStyleSheet("color: #6C757D;")
        self._status_label.show()
        
        # 切换按钮
        self._cancel_btn.hide()
        self._close_btn.show()
    
    def closeEvent(self, event):
        """关闭事件 - 关闭窗口不取消下载
        
        Feature: simplify-update
        Requirements: 2.10
        """
        # 如果下载未完成且未取消，只是隐藏窗口
        if not self._is_completed and not self._is_cancelled:
            # 不取消下载，只是隐藏窗口
            pass
        
        event.accept()
