# =====================================================
# =============== 对话框组件 ===============
# =====================================================

"""
对话框组件 - 设置对话框和Anki制卡对话框

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 6.2, 6.3, 6.4, 6.5, 6.7
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QComboBox,
    QCheckBox, QTextEdit, QPushButton,
    QGroupBox, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QProgressBar, QTextBrowser,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QImage, QDesktopServices, QIntValidator
from PySide6.QtCore import QUrl

from .styles import (
    COLORS,
    DIALOG_STYLE,
    GROUPBOX_STYLE,
    INPUT_STYLE,
    TABWIDGET_STYLE,
    SCROLLAREA_STYLE,
)
from .ui_components import ModernButton, ModernCheckBox, ModernSwitch, CollapsibleHelpPanel, HelpGroupBox, InfoIconLabel
from .help_texts import get_help_text, get_group_description, get_help_panel_items
from ..core.config_manager import AppConfig
import re


def markdown_to_html(text: str) -> str:
    """简单的 Markdown 转 HTML
    
    支持：标题、粗体、列表、代码块、链接
    """
    if not text:
        return ""
    
    import html
    
    lines = text.split('\n')
    html_lines = []
    in_code_block = False
    in_list = False
    
    for line in lines:
        # 代码块
        if line.strip().startswith('```'):
            if in_code_block:
                html_lines.append('</pre>')
                in_code_block = False
            else:
                html_lines.append('<pre style="background:#f5f5f5;padding:8px;border-radius:4px;overflow-x:auto;">')
                in_code_block = True
            continue
        
        if in_code_block:
            html_lines.append(html.escape(line))
            continue
        
        # 标题
        if line.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h4 style="margin:12px 0 6px 0;color:#333;">{html.escape(line[4:])}</h4>')
            continue
        elif line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h3 style="margin:14px 0 8px 0;color:#222;">{html.escape(line[3:])}</h3>')
            continue
        elif line.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h2 style="margin:16px 0 10px 0;color:#111;">{html.escape(line[2:])}</h2>')
            continue
        
        # 列表项
        if line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list:
                html_lines.append('<ul style="margin:4px 0;padding-left:20px;">')
                in_list = True
            content = line.strip()[2:]
            # 先转义 HTML，再处理 Markdown 格式
            content = _process_inline_markdown(content)
            html_lines.append(f'<li style="margin:2px 0;">{content}</li>')
            continue
        
        # 关闭列表
        if in_list and line.strip() == '':
            html_lines.append('</ul>')
            in_list = False
        
        # 普通段落
        if line.strip():
            content = _process_inline_markdown(line)
            html_lines.append(f'<p style="margin:4px 0;">{content}</p>')
        elif not in_list:
            html_lines.append('<br>')
    
    # 关闭未关闭的标签
    if in_list:
        html_lines.append('</ul>')
    if in_code_block:
        html_lines.append('</pre>')
    
    return '\n'.join(html_lines)


def _process_inline_markdown(text: str) -> str:
    """处理行内 Markdown 格式（粗体、行内代码、链接）"""
    import html
    
    # 先提取并保护链接和代码，避免被转义破坏
    protected = []
    
    # 保护行内代码
    def protect_code(m):
        idx = len(protected)
        protected.append(f'<code style="background:#f0f0f0;padding:1px 4px;border-radius:3px;">{html.escape(m.group(1))}</code>')
        return f'\x00{idx}\x00'
    text = re.sub(r'`([^`]+)`', protect_code, text)
    
    # 保护链接
    def protect_link(m):
        idx = len(protected)
        protected.append(f'<a href="{html.escape(m.group(2))}" style="color:#3B82F6;">{html.escape(m.group(1))}</a>')
        return f'\x00{idx}\x00'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', protect_link, text)
    
    # 转义剩余内容
    text = html.escape(text)
    
    # 处理粗体（转义后处理）
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 恢复保护的内容
    for idx, content in enumerate(protected):
        text = text.replace(f'\x00{idx}\x00', content)
    
    return text


# ========== 嵌入式下载进度组件 ==========

class EmbeddedDownloadProgress(QWidget):
    """嵌入式下载进度组件 - 嵌入在关于页面中显示下载状态
    
    Feature: embedded-download-progress, seamless-update-flow
    Requirements: 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 3.1, 3.4
    """
    
    # 信号
    cancel_requested = Signal()
    retry_requested = Signal()
    update_now_requested = Signal()  # 用户点击"立即更新"
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化嵌入式下载进度组件
        
        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)
        
        # 状态标签
        self._status_label = QLabel("准备下载...")
        self._status_label.setStyleSheet("color: #64748B; font-weight: bold;")
        layout.addWidget(self._status_label)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                text-align: center;
                height: 8px;
                background: #E2E8F0;
            }
            QProgressBar::chunk {
                background: #3B82F6;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._progress_bar)
        
        # 详情行：百分比 + 大小 + 速度
        detail_layout = QHBoxLayout()
        detail_layout.setSpacing(16)
        
        self._percent_label = QLabel("0%")
        self._percent_label.setStyleSheet("color: #3B82F6; font-weight: bold;")
        detail_layout.addWidget(self._percent_label)
        
        self._size_label = QLabel("0 KB / 0 KB")
        self._size_label.setStyleSheet("color: #94A3B8;")
        detail_layout.addWidget(self._size_label)
        
        self._speed_label = QLabel("0 KB/s")
        self._speed_label.setStyleSheet("color: #94A3B8;")
        detail_layout.addWidget(self._speed_label)
        
        detail_layout.addStretch()
        layout.addLayout(detail_layout)
        
        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self._cancel_btn = ModernButton("取消", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        
        self._retry_btn = ModernButton("重试", ModernButton.PRIMARY)
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.setVisible(False)
        btn_layout.addWidget(self._retry_btn)
        
        self._open_folder_btn = ModernButton("打开文件夹", ModernButton.PRIMARY)
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        self._open_folder_btn.setVisible(False)
        btn_layout.addWidget(self._open_folder_btn)
        
        # 立即更新按钮
        # Feature: seamless-update-flow
        # Requirements: 2.1, 2.3
        self._update_now_btn = ModernButton("🚀 立即更新", ModernButton.PRIMARY)
        self._update_now_btn.clicked.connect(self._on_update_now)
        self._update_now_btn.setVisible(False)
        btn_layout.addWidget(self._update_now_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # 启动提示标签（首次启动较慢的提示）
        self._launch_hint_label = QLabel("💡 首次启动新版本可能需要 30-60 秒，耐心等等哦～")
        self._launch_hint_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self._launch_hint_label.setVisible(False)
        layout.addWidget(self._launch_hint_label)
        
        # 保存文件路径
        self._file_path = ""
    
    def set_state(self, state) -> None:
        """设置显示状态
        
        Args:
            state: DownloadState 枚举值
        """
        from screenshot_tool.services.update_service import DownloadState
        
        if state == DownloadState.IDLE:
            self._status_label.setText("准备起飞... 🚀")
            self._status_label.setStyleSheet("color: #64748B; font-weight: bold;")
            self._progress_bar.setValue(0)
            self._percent_label.setText("0%")
            self._size_label.setText("0 KB / 0 KB")
            self._speed_label.setText("0 KB/s")
            self._cancel_btn.setVisible(True)
            self._retry_btn.setVisible(False)
            self._open_folder_btn.setVisible(False)
        
        elif state == DownloadState.DOWNLOADING:
            self._status_label.setText("正在从云端召唤... ☁️")
            self._status_label.setStyleSheet("color: #3B82F6; font-weight: bold;")
            self._cancel_btn.setVisible(True)
            self._retry_btn.setVisible(False)
            self._open_folder_btn.setVisible(False)
        
        elif state == DownloadState.COMPLETED:
            self._status_label.setText("✅ 下载完成！")
            self._status_label.setStyleSheet("color: #10B981; font-weight: bold;")
            self._progress_bar.setValue(100)
            self._percent_label.setText("100%")
            self._cancel_btn.setVisible(False)
            self._retry_btn.setVisible(False)
            self._open_folder_btn.setVisible(True)
        
        elif state == DownloadState.FAILED:
            self._status_label.setText("❌ 下载翻车了...")
            self._status_label.setStyleSheet("color: #EF4444; font-weight: bold;")
            self._cancel_btn.setVisible(False)
            self._retry_btn.setVisible(True)
            self._open_folder_btn.setVisible(False)
        
        elif state == DownloadState.CANCELLED:
            self._status_label.setText("下载被你取消啦～")
            self._status_label.setStyleSheet("color: #94A3B8; font-weight: bold;")
            self._cancel_btn.setVisible(False)
            self._retry_btn.setVisible(True)
            self._open_folder_btn.setVisible(False)
    
    def update_progress(self, downloaded: int, total: int, speed: float) -> None:
        """更新进度显示
        
        Args:
            downloaded: 已下载字节数
            total: 总字节数
            speed: 下载速度 (KB/s)
        """
        # 计算百分比
        if total > 0:
            percent = min(int((downloaded / total) * 100), 100)
        else:
            percent = 0
        
        self._progress_bar.setValue(percent)
        self._percent_label.setText(f"{percent}%")
        
        # 格式化大小
        downloaded_str = self._format_size(downloaded)
        total_str = self._format_size(total)
        self._size_label.setText(f"{downloaded_str} / {total_str}")
        
        # 格式化速度
        speed_str = self._format_speed(speed)
        self._speed_label.setText(speed_str)
    
    def set_completed(self, file_path: str) -> None:
        """设置完成状态 - 显示立即更新按钮
        
        Feature: seamless-update-flow
        Requirements: 2.1, 2.2
        
        Args:
            file_path: 下载完成的文件路径
        """
        from screenshot_tool.services.update_service import DownloadState
        
        self._file_path = file_path
        self.set_state(DownloadState.COMPLETED)
        
        # 显示文件路径
        import os
        filename = os.path.basename(file_path)
        self._status_label.setText(f"✅ 下载完成: {filename}")
        
        # 隐藏打开文件夹，显示立即更新
        self._open_folder_btn.setVisible(False)
        self._update_now_btn.setVisible(True)
        self._update_now_btn.setEnabled(True)
        self._update_now_btn.setText("🚀 立即更新")
        # 显示启动提示
        self._launch_hint_label.setVisible(True)
    
    def set_error(self, error_msg: str) -> None:
        """设置错误状态
        
        Args:
            error_msg: 错误信息
        """
        from screenshot_tool.services.update_service import DownloadState
        
        self.set_state(DownloadState.FAILED)
        self._status_label.setText(f"❌ 下载翻车了：{error_msg}")
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    def _format_speed(self, speed_kbps: float) -> str:
        """格式化下载速度"""
        if speed_kbps < 1024:
            return f"{speed_kbps:.1f} KB/s"
        else:
            return f"{speed_kbps / 1024:.1f} MB/s"
    
    def _on_cancel(self):
        """取消按钮点击"""
        self.cancel_requested.emit()
    
    def _on_retry(self):
        """重试按钮点击"""
        self.retry_requested.emit()
    
    def _on_open_folder(self):
        """打开文件夹按钮点击"""
        if self._file_path:
            import os
            folder = os.path.dirname(self._file_path)
            if os.path.exists(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    
    def _on_update_now(self):
        """立即更新按钮点击
        
        Feature: seamless-update-flow
        Requirements: 2.3
        """
        self.update_now_requested.emit()
    
    def set_updating(self) -> None:
        """设置正在更新状态 - 禁用按钮并显示系统通知
        
        Feature: seamless-update-flow
        Requirements: 3.1
        """
        self._update_now_btn.setEnabled(False)
        self._update_now_btn.setText("正在唤醒...")
        self._status_label.setText("🔄 新版本正在热身，马上就好...")
        self._status_label.setStyleSheet("color: #3B82F6; font-weight: bold;")
        self._launch_hint_label.setText("⏳ 新版本正在穿衣服，首次启动要等 30-60 秒哦...")
        self._launch_hint_label.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold;")
        
        # 显示系统托盘通知
        self._show_update_notification()
    
    def reset_update_button(self) -> None:
        """重置更新按钮状态（启动失败时调用）
        
        Feature: seamless-update-flow
        Requirements: 3.4
        """
        self._update_now_btn.setEnabled(True)
        self._update_now_btn.setText("🚀 立即更新")
        self._status_label.setText("❌ 启动失败了，再试一次？")
        self._status_label.setStyleSheet("color: #EF4444; font-weight: bold;")
        self._launch_hint_label.setText("💡 首次启动新版本可能需要 30-60 秒，耐心等等哦～")
        self._launch_hint_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
    
    def _show_update_notification(self) -> None:
        """显示系统托盘通知
        
        Feature: seamless-update-flow
        """
        try:
            # 尝试获取应用的系统托盘图标来显示通知
            from PySide6.QtWidgets import QApplication, QSystemTrayIcon
            
            app = QApplication.instance()
            if app:
                # 查找系统托盘图标
                for widget in app.allWidgets():
                    if isinstance(widget, QSystemTrayIcon) and widget.isVisible():
                        widget.showMessage(
                            "虎哥截图 - 正在更新 🚀",
                            "新版本正在穿衣服，首次启动要等 30-60 秒哦～",
                            QSystemTrayIcon.MessageIcon.Information,
                            5000  # 显示 5 秒
                        )
                        return
                
                # 如果没有找到托盘图标，尝试通过父窗口链找到主窗口的托盘
                parent = self.parent()
                while parent:
                    if hasattr(parent, '_tray_icon') and parent._tray_icon:
                        parent._tray_icon.showMessage(
                            "虎哥截图 - 正在更新 🚀",
                            "新版本正在穿衣服，首次启动要等 30-60 秒哦～",
                            QSystemTrayIcon.MessageIcon.Information,
                            5000
                        )
                        return
                    parent = parent.parent()
        except Exception:
            # 通知失败不影响更新流程
            pass
    
    @property
    def file_path(self) -> str:
        """获取下载文件路径"""
        return self._file_path


class SettingsDialog(QDialog):
    """设置对话框"""
    
    # 设置保存信号
    settingsSaved = Signal(object)  # AppConfig
    # 快捷键变更信号
    hotkeyChanged = Signal(str, str)  # modifier, key
    # 强制锁定变更信号
    # Feature: hotkey-force-lock
    # Requirements: 4.3
    forceLockChanged = Signal(bool, int)  # enabled, retry_interval_ms
    # 登录成功信号
    loginSuccess = Signal(dict)  # {user_id, email}
    # 登出信号
    logoutSuccess = Signal()
    
    def __init__(
        self,
        config: AppConfig,
        parent: Optional[QWidget] = None,
        update_service=None,
        download_state_manager=None,
        subscription_manager=None
    ):
        """
        初始化设置对话框
        
        Args:
            config: 当前配置
            parent: 父组件
            update_service: 更新服务实例（可选）
            download_state_manager: 下载状态管理器（可选）
            subscription_manager: 订阅管理器实例（可选）
            
        Feature: embedded-download-progress, subscription-system
        Requirements: 2.2
        """
        super().__init__(parent)
        
        # 在设置 WindowFlags 之前先隐藏窗口，避免闪烁
        # Windows 上 setWindowFlags 会导致窗口重建，可能短暂显示
        self.hide()
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        self._config = config
        self._update_service = update_service
        self._download_state_manager = download_state_manager
        self._subscription_manager = subscription_manager
        self._setup_ui()
        self._load_config()
        
        # 连接下载状态管理器信号
        self._connect_download_state_manager()
    
    def _setup_ui(self):
        """设置UI"""
        # 导入应用信息
        from screenshot_tool import __version__, __app_name__
        
        self.setWindowTitle(f"⚙️ {__app_name__} - 设置")
        self.setMinimumSize(700, 600)  # 增加最小尺寸
        self.resize(800, 650)  # 默认大小
        self.setStyleSheet(DIALOG_STYLE)
        
        # WindowFlags 已在 __init__ 中设置，避免窗口重建导致闪烁
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 软件名称和版本号标题
        title_layout = QHBoxLayout()
        title_label = QLabel(f"🐯 {__app_name__}")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #F59E0B; /* 使用稍微柔和的橙色 */
            }
        """)
        # 使用 QFont 设置相对字体大小
        title_font = title_label.font()
        base_size = title_font.pointSize()
        if base_size <= 0:
            base_size = 10  # 默认基础字号
        title_font.setPointSize(base_size + 8)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)
        
        version_label = QLabel(f"v{__version__}")
        version_label.setStyleSheet("""
            QLabel {
                color: #94A3B8;
                padding-left: 8px;
            }
        """)
        title_layout.addWidget(version_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # 标签页 - 传入 self 作为父组件
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setStyleSheet(TABWIDGET_STYLE)
        self._tab_widget.setUsesScrollButtons(True)  # 标签过多时显示滚动按钮
        
        # 各设置页（使用可滚动容器）
        self._tab_widget.addTab(self._create_account_tab(), "👤 账户")
        self._tab_widget.addTab(self._create_general_tab(), "📁 常规")
        self._tab_widget.addTab(self._create_hotkey_tab(), "⌨️ 快捷键")
        self._tab_widget.addTab(self._create_ocr_tab(), "🔍 识别文字")
        self._tab_widget.addTab(self._create_ding_tab(), "📌 贴图")
        self._tab_widget.addTab(self._create_anki_tab(), "📚 Anki")
        self._tab_widget.addTab(self._create_highlight_tab(), "🎨 高亮")
        self._tab_widget.addTab(self._create_markdown_tab(), "📝 网页转MD")
        self._tab_widget.addTab(self._create_pdf_tab(), "📄 文件转MD")
        self._tab_widget.addTab(self._create_about_tab(), "ℹ️ 关于")
        
        layout.addWidget(self._tab_widget, 1)  # stretch=1 让标签页占据剩余空间
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        
        # 一键重置按钮（左侧）
        self._reset_btn = ModernButton("🔄 重置所有设置", ModernButton.SECONDARY)
        self._reset_btn.clicked.connect(self._on_reset_all)
        btn_layout.addWidget(self._reset_btn)
        
        btn_layout.addStretch()
        
        self._cancel_btn = ModernButton("取消", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        
        self._save_btn = ModernButton("保存", ModernButton.PRIMARY)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)
        
        layout.addLayout(btn_layout)
    
    def _create_scrollable_tab(self) -> "Tuple[QScrollArea, QVBoxLayout]":
        """创建可滚动的标签页容器
        
        Returns:
            Tuple[QScrollArea, QVBoxLayout]: 滚动区域和内容布局
        """
        # 不设置父组件，因为 addTab 会自动设置正确的父组件
        # 设置父组件为 self 反而可能导致问题
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(SCROLLAREA_STYLE)
        
        # content 的父组件会在 setWidget 时自动设置为 scroll
        content = QWidget()
        content.setStyleSheet("QWidget { background: transparent; }")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)
        
        scroll.setWidget(content)
        return scroll, content_layout
    
    def _create_account_tab(self) -> QWidget:
        """创建账户设置页
        
        Feature: subscription-system
        Requirements: 1.1, 1.2, 1.5
        """
        scroll, layout = self._create_scrollable_tab()
        
        # 账户状态容器（动态更新）
        self._account_container = QWidget()
        self._account_layout = QVBoxLayout(self._account_container)
        self._account_layout.setContentsMargins(0, 0, 0, 0)
        self._account_layout.setSpacing(12)
        
        # 加载重试计数器
        self._account_load_retry_count = 0
        self._account_max_retries = 10  # 最多重试 10 次（5 秒）
        
        # 根据登录状态显示不同内容
        self._update_account_ui()
        
        layout.addWidget(self._account_container)
        layout.addStretch()
        
        return scroll
    
    def _update_account_ui(self):
        """更新账户 UI（根据登录状态）
        
        Feature: subscription-system
        """
        # 清空现有内容（安全地删除所有子组件）
        while self._account_layout.count():
            item = self._account_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # 递归清理嵌套布局
                self._clear_layout(item.layout())
        
        # 检查订阅管理器状态
        if self._subscription_manager and not self._subscription_manager.is_initialized:
            # 订阅系统正在后台初始化，显示加载状态并定时重试
            self._create_loading_ui()
            return
        
        is_logged_in = (
            self._subscription_manager and 
            self._subscription_manager.is_initialized and 
            self._subscription_manager.is_logged_in
        )
        
        if is_logged_in:
            self._create_logged_in_ui()
        else:
            self._create_login_form_ui()
    
    def _create_loading_ui(self):
        """创建加载中状态的 UI
        
        当订阅系统正在后台初始化时显示。
        """
        # 检查是否超过最大重试次数
        self._account_load_retry_count += 1
        if self._account_load_retry_count > self._account_max_retries:
            # 超过重试次数，显示错误信息
            self._create_error_ui("加载超时，请稍后重试")
            return
        
        loading_group = QGroupBox("")
        loading_group.setStyleSheet("QGroupBox { border: none; }")
        loading_layout = QVBoxLayout(loading_group)
        loading_layout.setSpacing(12)
        
        loading_label = QLabel("⏳ 正在加载账户信息...")
        loading_label.setStyleSheet("font-size: 14px; color: #64748B;")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(loading_label)
        
        self._account_layout.addWidget(loading_group)
        
        # 500ms 后重试检查（使用弱引用避免对象已删除时崩溃）
        import weakref
        weak_self = weakref.ref(self)
        
        def retry_update():
            dialog = weak_self()
            if dialog is not None:
                try:
                    # 额外检查对话框是否仍然可见
                    if dialog.isVisible():
                        dialog._update_account_ui()
                except RuntimeError:
                    # C++ 对象已删除，忽略
                    pass
        
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, retry_update)
    
    def _create_error_ui(self, error_message: str):
        """创建错误状态的 UI
        
        Args:
            error_message: 错误信息
        """
        error_group = QGroupBox("")
        error_group.setStyleSheet("QGroupBox { border: none; }")
        error_layout = QVBoxLayout(error_group)
        error_layout.setSpacing(12)
        
        error_label = QLabel(f"⚠️ {error_message}")
        error_label.setStyleSheet("font-size: 14px; color: #EF4444;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_layout.addWidget(error_label)
        
        # 重试按钮
        retry_btn = QPushButton("🔄 重试")
        retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        retry_btn.clicked.connect(self._retry_account_load)
        error_layout.addWidget(retry_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self._account_layout.addWidget(error_group)
    
    def _retry_account_load(self):
        """重试加载账户信息"""
        self._account_load_retry_count = 0
        self._update_account_ui()
    
    def _clear_layout(self, layout):
        """递归清理布局中的所有组件
        
        Args:
            layout: 要清理的布局
        """
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
    
    def _create_logged_in_ui(self):
        """创建已登录状态的 UI
        
        Feature: subscription-system
        """
        # 用户信息卡片
        user_group = QGroupBox("账户信息")
        user_group.setStyleSheet(GROUPBOX_STYLE)
        user_layout = QVBoxLayout(user_group)
        user_layout.setSpacing(12)
        
        # 获取用户信息
        state = self._subscription_manager.state
        email = state.user_email
        
        # 如果 state 中没有邮箱，尝试从 AuthService 获取
        if not email and self._subscription_manager.auth_service:
            user = self._subscription_manager.auth_service.get_current_user()
            if user and user.email:
                email = user.email
                # 同步更新 state
                state.user_email = email
        
        email = email or "未知"
        is_vip = state.is_vip
        plan_text = "🎖️ 终身 VIP" if is_vip else "免费版"
        
        # 用户头像和邮箱
        user_info_layout = QHBoxLayout()
        
        # 头像占位
        avatar_label = QLabel("👤")
        avatar_label.setStyleSheet("""
            QLabel {
                font-size: 48px;
                padding: 10px;
                background: #f0f0f0;
                border-radius: 8px;
            }
        """)
        user_info_layout.addWidget(avatar_label)
        
        # 用户详情
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)
        
        email_label = QLabel(email)
        email_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        details_layout.addWidget(email_label)
        
        plan_label = QLabel(plan_text)
        plan_label.setStyleSheet(
            "font-size: 12px; color: #F59E0B; font-weight: bold;" if is_vip 
            else "font-size: 12px; color: #94A3B8;"
        )
        details_layout.addWidget(plan_label)
        
        user_info_layout.addLayout(details_layout)
        user_info_layout.addStretch()
        
        user_layout.addLayout(user_info_layout)
        
        # VIP 状态提示
        if is_vip:
            vip_hint = QLabel("🎉 感谢您的支持！所有功能已解锁")
            vip_hint.setStyleSheet("color: #10B981; font-weight: bold; padding: 8px;")
            user_layout.addWidget(vip_hint)
        else:
            upgrade_hint = QLabel(
                "💡 虎哥截图是我业余时间开发的免费工具\n"
                "☕ 如果觉得好用，请作者喝杯咖啡（9.9元）\n"
                "🎁 赞助开发可解锁终身 VIP 权益，感谢支持！"
            )
            upgrade_hint.setStyleSheet("color: #F59E0B; padding: 8px; line-height: 1.5;")
            user_layout.addWidget(upgrade_hint)
            
            # 赞助按钮
            upgrade_btn = ModernButton("☕ 赞助开发", ModernButton.PRIMARY)
            upgrade_btn.clicked.connect(self._on_upgrade_clicked)
            user_layout.addWidget(upgrade_btn)
        
        self._account_layout.addWidget(user_group)
        
        # 设备管理
        device_group = QGroupBox("设备管理")
        device_group.setStyleSheet(GROUPBOX_STYLE)
        device_layout = QVBoxLayout(device_group)
        
        device_hint = QLabel("管理已登录的设备，VIP 用户最多可在 3 台设备上使用")
        device_hint.setStyleSheet("color: #64748B;")
        device_hint.setWordWrap(True)
        device_layout.addWidget(device_hint)
        
        device_btn = ModernButton("📱 管理设备", ModernButton.SECONDARY)
        device_btn.clicked.connect(self._on_device_manager_clicked)
        device_layout.addWidget(device_btn)
        
        self._account_layout.addWidget(device_group)
        
        # 退出登录
        logout_group = QGroupBox("")
        logout_group.setStyleSheet("QGroupBox { border: none; }")
        logout_layout = QVBoxLayout(logout_group)
        
        logout_btn = ModernButton("🚪 退出登录", ModernButton.SECONDARY)
        logout_btn.setStyleSheet("""
            QPushButton {
                color: #EF4444;
                border: 1px solid #EF4444;
            }
            QPushButton:hover {
                background: #FDF2F2;
            }
        """)
        logout_btn.clicked.connect(self._on_logout_clicked)
        logout_layout.addWidget(logout_btn)
        
        self._account_layout.addWidget(logout_group)
    
    def _create_login_form_ui(self):
        """创建登录表单 UI
        
        Feature: subscription-system
        """
        # 欢迎信息
        welcome_group = QGroupBox("")
        welcome_group.setStyleSheet("QGroupBox { border: none; }")
        welcome_layout = QVBoxLayout(welcome_group)
        welcome_layout.setSpacing(12)
        
        welcome_label = QLabel("登录以解锁更多功能")
        welcome_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_label)
        
        benefits_label = QLabel(
            "• 同步设置到多台设备\n"
            "• 解锁 VIP 专属功能\n"
            "• 获取更多每日使用次数"
        )
        benefits_label.setStyleSheet("color: #64748B; padding: 8px;")
        benefits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(benefits_label)
        
        # 登录按钮（打开弹窗）
        login_btn = ModernButton("🔐 登录 / 注册", ModernButton.PRIMARY)
        login_btn.setMinimumHeight(45)
        login_btn.clicked.connect(self._open_login_dialog)
        welcome_layout.addWidget(login_btn)
        
        self._account_layout.addWidget(welcome_group)
    
    def _open_login_dialog(self):
        """打开登录弹窗
        
        Feature: subscription-system
        """
        from screenshot_tool.ui.login_dialog import LoginDialog
        
        auth_service = None
        if self._subscription_manager:
            auth_service = self._subscription_manager.auth_service
        
        dialog = LoginDialog(auth_service=auth_service, parent=self)
        dialog.login_success.connect(self._on_dialog_login_success)
        # 使用 show() 代替 exec()，避免阻塞热键
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _on_dialog_login_success(self, user_info: dict):
        """弹窗登录成功回调
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.1, 1.2, 1.3, 4.1
        """
        # 登录成功后，需要同步 SubscriptionManager 的状态
        # LoginDialog 直接调用 AuthService.login()，但 SubscriptionManager 的状态没有更新
        # 这里需要手动同步状态并创建 LicenseService
        if self._subscription_manager:
            self._subscription_manager._sync_after_login(user_info)
        
        # 更新账户 UI
        self._update_account_ui()
        
        # 发送信号
        self.loginSuccess.emit(user_info)
    
    def _on_forgot_password_clicked(self):
        """忘记密码点击
        
        Feature: subscription-system
        """
        email, ok = QInputDialog.getText(
            self, "重置密码 🔑", "请输入您的邮箱地址:",
            QLineEdit.EchoMode.Normal, ""
        )
        
        if not ok or not email.strip():
            return
        
        if not self._subscription_manager:
            QMessageBox.warning(self, "哎呀 😅", "订阅服务还没睡醒，稍等一下？")
            return
        
        auth_service = self._subscription_manager.auth_service
        if not auth_service:
            QMessageBox.warning(
                self, 
                "认证服务未就绪 😅", 
                "订阅系统正在初始化中，请稍等几秒后重试。"
            )
            return
        
        try:
            success = auth_service.reset_password(email.strip())
            if success:
                QMessageBox.information(
                    self, "发送成功！📨",
                    "重置链接已飞往你的邮箱，快去接收！📬"
                )
            else:
                QMessageBox.warning(self, "发送失败 😢", "发送失败了...喝杯茶等等？🍵")
        except Exception as e:
            QMessageBox.critical(self, "哎呀 😅", f"发送失败了：{e}")
    
    def _on_logout_clicked(self):
        """退出登录点击
        
        Feature: subscription-system
        """
        reply = QMessageBox.question(
            self, "确定要走吗？🥺",
            "真的要退出吗？下次记得回来哦～",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        if self._subscription_manager:
            self._subscription_manager.logout()
        
        # 更新 UI
        self._update_account_ui()
        
        # 发送信号
        self.logoutSuccess.emit()
        
        QMessageBox.information(self, "已退出 👋", "下次再来玩呀～")
    
    def _on_upgrade_clicked(self):
        """升级按钮点击"""
        from screenshot_tool.ui.payment_dialog import PaymentDialog
        
        if not self._subscription_manager:
            QMessageBox.warning(self, "温馨提示 💡", "订阅系统还在睡觉 💤")
            return
        
        user_id = self._subscription_manager.state.user_id
        payment_service = self._subscription_manager.payment_service
        
        dialog = PaymentDialog(
            payment_service=payment_service,
            user_id=user_id,
            parent=self
        )
        dialog.payment_success.connect(self._on_payment_success)
        # 使用 show() 代替 exec()，避免阻塞热键
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _on_payment_success(self):
        """支付成功回调"""
        # 刷新订阅状态（更新 state.is_vip）
        if self._subscription_manager:
            self._subscription_manager.refresh_subscription()
            # 更新 UI
            self._update_account_ui()
    
    def _on_device_manager_clicked(self):
        """设备管理按钮点击
        
        Feature: subscription-system
        """
        from screenshot_tool.ui.device_manager_dialog import DeviceManagerDialog
        from screenshot_tool.core.device_manager import DeviceManager
        
        device_manager = None
        if self._subscription_manager and self._subscription_manager.license_service:
            client = self._subscription_manager.client
            user_id = self._subscription_manager.state.user_id
            if client and user_id:
                device_manager = DeviceManager(client, user_id)
        
        dialog = DeviceManagerDialog(device_manager=device_manager, parent=self)
        # 使用 show() 代替 exec()，避免阻塞热键
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        dialog.activateWindow()
    
    def _create_general_tab(self) -> QWidget:
        """创建常规设置页"""
        scroll, layout = self._create_scrollable_tab()
        
        # 启动设置
        startup_group = QGroupBox("启动设置")
        startup_group.setStyleSheet(GROUPBOX_STYLE)
        startup_layout = QFormLayout(startup_group)
        startup_layout.setSpacing(12)
        
        # 开机自启动
        self._auto_start_check = ModernCheckBox("开机自动启动")
        startup_layout.addRow("", self._auto_start_check)
        
        layout.addWidget(startup_group)
        
        # 保存路径
        group = QGroupBox("保存设置")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # 保存路径
        path_layout = QHBoxLayout()
        self._save_path_edit = QLineEdit()
        self._save_path_edit.setStyleSheet(INPUT_STYLE)
        self._save_path_edit.setPlaceholderText("选择截图保存路径...")
        path_layout.addWidget(self._save_path_edit)
        
        browse_btn = ModernButton("浏览...", ModernButton.SECONDARY)
        browse_btn.clicked.connect(self._browse_save_path)
        path_layout.addWidget(browse_btn)
        
        group_layout.addRow("保存路径:", path_layout)
        
        # 自动保存
        self._auto_save_check = ModernCheckBox("截图后自动保存")
        group_layout.addRow("", self._auto_save_check)
        
        layout.addWidget(group)
        
        # 通知设置
        notify_group = QGroupBox("通知设置")
        notify_group.setStyleSheet(GROUPBOX_STYLE)
        notify_layout = QVBoxLayout(notify_group)
        notify_layout.setSpacing(8)
        
        # 各类通知开关
        self._notify_startup_check = ModernCheckBox("启动通知")
        self._notify_startup_check.setToolTip("程序启动时显示通知")
        notify_layout.addWidget(self._notify_startup_check)
        
        self._notify_screenshot_save_check = ModernCheckBox("截图保存通知")
        self._notify_screenshot_save_check.setToolTip("截图保存成功或失败时显示通知")
        notify_layout.addWidget(self._notify_screenshot_save_check)
        
        self._notify_ding_check = ModernCheckBox("贴图通知")
        self._notify_ding_check.setToolTip("贴图成功时显示通知")
        notify_layout.addWidget(self._notify_ding_check)
        
        self._notify_anki_check = ModernCheckBox("Anki 导入通知")
        self._notify_anki_check.setToolTip("Anki 卡片导入完成时显示通知")
        notify_layout.addWidget(self._notify_anki_check)
        
        self._notify_gongwen_check = ModernCheckBox("公文格式化通知")
        self._notify_gongwen_check.setToolTip("公文格式化完成时显示通知")
        notify_layout.addWidget(self._notify_gongwen_check)
        
        self._notify_hotkey_update_check = ModernCheckBox("快捷键更新通知")
        self._notify_hotkey_update_check.setToolTip("快捷键修改后显示通知")
        notify_layout.addWidget(self._notify_hotkey_update_check)
        
        self._notify_software_update_check = ModernCheckBox("软件版本更新通知")
        self._notify_software_update_check.setToolTip("发现新版本时显示 Windows 通知提醒")
        notify_layout.addWidget(self._notify_software_update_check)
        
        self._notify_pdf_convert_check = ModernCheckBox("PDF 转换通知")
        self._notify_pdf_convert_check.setToolTip("PDF 转 Markdown 完成时显示通知")
        notify_layout.addWidget(self._notify_pdf_convert_check)
        
        self._notify_regulation_check = ModernCheckBox("规章下载通知")
        self._notify_regulation_check.setToolTip("CAAC 规章 PDF 下载完成时显示通知")
        notify_layout.addWidget(self._notify_regulation_check)
        
        self._notify_recording_check = ModernCheckBox("录屏完成通知")
        self._notify_recording_check.setToolTip("录屏完成时显示通知")
        notify_layout.addWidget(self._notify_recording_check)
        
        layout.addWidget(notify_group)
        
        layout.addStretch()
        
        return scroll
    
    def _create_hotkey_tab(self) -> QWidget:
        """创建快捷键设置页
        
        Feature: hotkey-force-lock
        Requirements: 4.1, 4.2, 4.4
        """
        scroll, layout = self._create_scrollable_tab()
        
        # 截图快捷键
        group = QGroupBox("截图快捷键")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # 修饰键选择
        self._hotkey_modifier_combo = QComboBox()
        self._hotkey_modifier_combo.setStyleSheet(INPUT_STYLE)
        self._hotkey_modifier_combo.addItems([
            "Alt",
            "Ctrl",
            "Shift",
            "Ctrl+Alt",
            "Ctrl+Shift",
            "Alt+Shift",
        ])
        self._hotkey_modifier_combo.currentTextChanged.connect(self._update_hotkey_preview)
        group_layout.addRow("修饰键:", self._hotkey_modifier_combo)
        
        # 主键选择
        self._hotkey_key_combo = QComboBox()
        self._hotkey_key_combo.setStyleSheet(INPUT_STYLE)
        # 添加字母键 A-Z
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            self._hotkey_key_combo.addItem(c)
        # 添加功能键 F1-F12
        for i in range(1, 13):
            self._hotkey_key_combo.addItem(f"F{i}")
        # 添加数字键 0-9
        for i in range(10):
            self._hotkey_key_combo.addItem(str(i))
        self._hotkey_key_combo.currentTextChanged.connect(self._update_hotkey_preview)
        group_layout.addRow("主键:", self._hotkey_key_combo)
        
        # 快捷键预览
        self._hotkey_preview_label = QLabel("Alt + A")
        self._hotkey_preview_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #3B82F6;
                padding: 8px 16px;
                background: #F0F7FF;
                border: 1px solid #3B82F6;
                border-radius: 6px;
            }
        """)
        # 使用 QFont 设置相对字体大小
        preview_font = self._hotkey_preview_label.font()
        base_size = preview_font.pointSize()
        if base_size <= 0:
            base_size = 10  # 默认基础字号
        preview_font.setPointSize(base_size + 3)
        preview_font.setBold(True)
        self._hotkey_preview_label.setFont(preview_font)
        group_layout.addRow("当前快捷键:", self._hotkey_preview_label)
        
        layout.addWidget(group)
        
        # 扩展快捷键配置
        # Feature: extended-hotkeys
        # Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
        extended_group = QGroupBox("扩展快捷键")
        extended_group.setStyleSheet(GROUPBOX_STYLE)
        extended_layout = QVBoxLayout(extended_group)
        extended_layout.setSpacing(12)
        
        # 分组描述
        extended_desc = QLabel("为常用功能配置全局快捷键，启用后可在任何界面快速触发")
        extended_desc.setStyleSheet("color: #64748B; font-size: 9pt; padding-bottom: 4px;")
        extended_layout.addWidget(extended_desc)
        
        # 主界面快捷键
        main_window_layout = self._create_extended_hotkey_row(
            "主界面",
            "main_window_hotkey",
            "打开主界面窗口"
        )
        extended_layout.addLayout(main_window_layout)
        
        # 工作台快捷键
        clipboard_layout = self._create_extended_hotkey_row(
            "工作台",
            "clipboard_hotkey",
            "打开工作台窗口"
        )
        extended_layout.addLayout(clipboard_layout)
        
        # 识别文字快捷键
        # Feature: clipboard-ocr-merge, Requirements: 7.3
        # OCR 功能已集成到工作台窗口，此热键现在打开工作台窗口
        ocr_panel_layout = self._create_extended_hotkey_row(
            "识别文字",
            "ocr_panel_hotkey",
            "打开工作台窗口"
        )
        extended_layout.addLayout(ocr_panel_layout)
        
        # 聚光灯快捷键
        spotlight_layout = self._create_extended_hotkey_row(
            "聚光灯",
            "spotlight_hotkey",
            "切换聚光灯效果"
        )
        extended_layout.addLayout(spotlight_layout)
        
        # 鼠标高亮快捷键
        mouse_highlight_layout = self._create_extended_hotkey_row(
            "鼠标高亮",
            "mouse_highlight_hotkey",
            "切换鼠标高亮效果"
        )
        extended_layout.addLayout(mouse_highlight_layout)
        
        # 恢复截图快捷键
        # Feature: screenshot-state-restore
        state_restore_layout = self._create_extended_hotkey_row(
            "恢复截图",
            "state_restore_hotkey",
            "恢复上次截图状态"
        )
        extended_layout.addLayout(state_restore_layout)
        
        # 冲突提示
        self._hotkey_conflict_label = QLabel("")
        self._hotkey_conflict_label.setStyleSheet("""
            color: #DC2626;
            font-size: 10pt;
            padding: 4px 8px;
            background-color: #FEE2E2;
            border-radius: 4px;
        """)
        self._hotkey_conflict_label.setWordWrap(True)
        self._hotkey_conflict_label.hide()
        extended_layout.addWidget(self._hotkey_conflict_label)
        
        layout.addWidget(extended_group)
        
        # 热键冲突处理设置
        # Feature: hotkey-force-lock
        # Requirements: 4.1, 4.2
        force_lock_group = QGroupBox("热键冲突处理")
        force_lock_group.setStyleSheet(GROUPBOX_STYLE)
        force_lock_layout = QVBoxLayout(force_lock_group)
        force_lock_layout.setSpacing(8)
        
        # 数值输入框样式
        number_input_style = f"""
            QLineEdit {{
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
                color: {COLORS['text_primary']};
                font-size: 13px;
                min-width: 80px;
                max-width: 100px;
            }}
            QLineEdit:hover {{
                border-color: #D1D5DB;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
            }}
        """
        
        # 分组描述
        force_lock_desc = QLabel("当热键被其他软件占用时的处理方式")
        force_lock_desc.setStyleSheet("color: #64748B; font-size: 9pt; padding-bottom: 4px;")
        force_lock_layout.addWidget(force_lock_desc)
        
        # 强制锁定开关
        self._force_lock_check = ModernCheckBox("强制锁定热键")
        self._force_lock_check.setToolTip(
            "启用后，当热键被其他软件占用时，\n"
            "本软件会持续尝试注册热键，直到成功抢占。\n"
            "适用于热键经常与其他软件冲突的情况。"
        )
        force_lock_layout.addWidget(self._force_lock_check)
        
        # 重试间隔设置
        retry_layout = QHBoxLayout()
        retry_label = QLabel("重试间隔:")
        retry_label.setStyleSheet("color: #333;")
        retry_layout.addWidget(retry_label)
        
        self._retry_interval_input = QLineEdit()
        self._retry_interval_input.setStyleSheet(number_input_style)
        self._retry_interval_input.setText("3000")
        self._retry_interval_input.setPlaceholderText("1000-30000")
        self._retry_interval_input.setValidator(QIntValidator(1000, 30000))
        self._retry_interval_input.setToolTip("热键注册失败后的重试间隔（1000-30000 毫秒）")
        retry_layout.addWidget(self._retry_interval_input)
        retry_unit = QLabel("ms")
        retry_unit.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-left: 4px;")
        retry_layout.addWidget(retry_unit)
        retry_layout.addStretch()
        force_lock_layout.addLayout(retry_layout)
        
        # 提示信息
        force_lock_hint = QLabel("💡 启用强制锁定后，即使其他软件占用了热键，本软件也会持续尝试抢占")
        force_lock_hint.setStyleSheet("""
            color: #64748B;
            font-size: 10pt;
            padding: 4px 8px;
            background-color: #FFF8E1;
            border-radius: 4px;
        """)
        force_lock_hint.setWordWrap(True)
        force_lock_layout.addWidget(force_lock_hint)
        
        layout.addWidget(force_lock_group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="说明",
            items=get_help_panel_items("hotkey")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        return scroll
    
    def _update_hotkey_preview(self):
        """更新快捷键预览"""
        modifier = self._hotkey_modifier_combo.currentText()
        key = self._hotkey_key_combo.currentText()
        self._hotkey_preview_label.setText(f"{modifier} + {key}")
    
    def _create_extended_hotkey_row(self, label: str, config_attr: str, tooltip: str) -> QHBoxLayout:
        """创建扩展快捷键配置行
        
        Feature: extended-hotkeys
        Requirements: 4.1, 4.2
        
        Args:
            label: 显示标签
            config_attr: 配置属性名
            tooltip: 提示文本
            
        Returns:
            包含控件的水平布局
        """
        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        
        # 启用开关
        enable_check = ModernCheckBox(label)
        enable_check.setToolTip(tooltip)
        enable_check.setMinimumWidth(100)
        row_layout.addWidget(enable_check)
        
        # 修饰键选择
        modifier_combo = QComboBox()
        modifier_combo.setStyleSheet(INPUT_STYLE)
        modifier_combo.setMinimumWidth(90)
        modifier_combo.addItems([
            "Alt",
            "Ctrl",
            "Shift",
            "Ctrl+Alt",
            "Ctrl+Shift",
            "Alt+Shift",
        ])
        row_layout.addWidget(modifier_combo)
        
        # 加号标签
        plus_label = QLabel("+")
        plus_label.setStyleSheet("color: #64748B; font-weight: bold;")
        row_layout.addWidget(plus_label)
        
        # 主键选择
        key_combo = QComboBox()
        key_combo.setStyleSheet(INPUT_STYLE)
        key_combo.setMinimumWidth(60)
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            key_combo.addItem(c)
        for i in range(1, 13):
            key_combo.addItem(f"F{i}")
        for i in range(10):
            key_combo.addItem(str(i))
        row_layout.addWidget(key_combo)
        
        row_layout.addStretch()
        
        # 保存控件引用
        setattr(self, f"_{config_attr}_enable", enable_check)
        setattr(self, f"_{config_attr}_modifier", modifier_combo)
        setattr(self, f"_{config_attr}_key", key_combo)
        
        # 连接信号检查冲突
        enable_check.toggled.connect(self._check_hotkey_conflicts)
        modifier_combo.currentTextChanged.connect(self._check_hotkey_conflicts)
        key_combo.currentTextChanged.connect(self._check_hotkey_conflicts)
        
        return row_layout
    
    def _check_hotkey_conflicts(self):
        """检查快捷键冲突
        
        Feature: extended-hotkeys
        Requirements: 4.3
        """
        # 收集所有启用的快捷键
        hotkeys = []
        
        # 截图快捷键（始终启用）
        screenshot_modifier = self._hotkey_modifier_combo.currentText().lower()
        screenshot_key = self._hotkey_key_combo.currentText().lower()
        hotkeys.append(("截图", f"{screenshot_modifier}+{screenshot_key}"))
        
        # 扩展快捷键
        extended_configs = [
            ("main_window_hotkey", "主界面"),
            ("clipboard_hotkey", "工作台"),
            ("ocr_panel_hotkey", "识别文字"),
            ("spotlight_hotkey", "聚光灯"),
            ("mouse_highlight_hotkey", "鼠标高亮"),
            ("state_restore_hotkey", "恢复截图"),
        ]
        
        for config_attr, name in extended_configs:
            enable_check = getattr(self, f"_{config_attr}_enable", None)
            modifier_combo = getattr(self, f"_{config_attr}_modifier", None)
            key_combo = getattr(self, f"_{config_attr}_key", None)
            
            if enable_check and enable_check.isChecked() and modifier_combo and key_combo:
                modifier = modifier_combo.currentText().lower()
                key = key_combo.currentText().lower()
                hotkeys.append((name, f"{modifier}+{key}"))
        
        # 检查冲突
        conflicts = []
        seen = {}
        for name, hotkey in hotkeys:
            if hotkey in seen:
                conflicts.append(f"「{seen[hotkey]}」和「{name}」使用了相同的快捷键 {hotkey.upper()}")
            else:
                seen[hotkey] = name
        
        # 更新冲突提示
        if hasattr(self, '_hotkey_conflict_label'):
            if conflicts:
                self._hotkey_conflict_label.setText("⚠️ " + "；".join(conflicts))
                self._hotkey_conflict_label.show()
            else:
                self._hotkey_conflict_label.hide()
    
    def _create_ocr_tab(self) -> QWidget:
        """创建OCR设置页"""
        scroll, layout = self._create_scrollable_tab()
        
        # 识别文字行为设置
        behavior_group = QGroupBox("识别文字行为设置")
        behavior_group.setStyleSheet(GROUPBOX_STYLE)
        behavior_layout = QVBoxLayout(behavior_group)
        behavior_layout.setSpacing(8)
        
        # 分组描述
        behavior_desc = QLabel("控制截图时识别面板的默认行为")
        behavior_desc.setStyleSheet("color: #64748B; font-size: 9pt; padding-bottom: 4px;")
        behavior_layout.addWidget(behavior_desc)
        
        # 截图时始终开启识别
        self._always_ocr_check = ModernCheckBox("截图时始终开启文字识别")
        self._always_ocr_check.setToolTip(
            "开启后，每次截图时识别面板默认开启\n"
            "关闭后，每次截图时识别面板默认关闭，需手动点击工具栏按钮开启"
        )
        behavior_layout.addWidget(self._always_ocr_check)
        
        # 提示信息（使用更大字号和更好的样式）
        behavior_hint = QLabel("💡 工具栏的识别文字按钮只影响当前截图，不会改变此设置")
        behavior_hint.setStyleSheet("""
            color: #64748B;
            font-size: 10pt;
            padding: 4px 8px;
            background-color: #F8F9FA;
            border-radius: 4px;
        """)
        behavior_layout.addWidget(behavior_hint)
        
        layout.addWidget(behavior_group)
        
        # 腾讯云文字识别 API设置
        tencent_group = QGroupBox("腾讯云文字识别")
        tencent_group.setStyleSheet(GROUPBOX_STYLE)
        tencent_layout = QFormLayout(tencent_group)
        tencent_layout.setSpacing(12)
        
        # 分组描述
        tencent_desc = QLabel("高精度云端识别，每月 2000 次免费额度")
        tencent_desc.setStyleSheet("color: #64748B; font-size: 9pt;")
        tencent_layout.addRow("", tencent_desc)
        
        # SecretId
        self._tencent_ocr_secret_id_edit = QLineEdit()
        self._tencent_ocr_secret_id_edit.setStyleSheet(INPUT_STYLE)
        self._tencent_ocr_secret_id_edit.setPlaceholderText("输入腾讯云 SecretId...")
        self._tencent_ocr_secret_id_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tencent_layout.addRow("SecretId:", self._tencent_ocr_secret_id_edit)
        
        # SecretKey
        self._tencent_ocr_secret_key_edit = QLineEdit()
        self._tencent_ocr_secret_key_edit.setStyleSheet(INPUT_STYLE)
        self._tencent_ocr_secret_key_edit.setPlaceholderText("输入腾讯云 SecretKey...")
        self._tencent_ocr_secret_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tencent_layout.addRow("SecretKey:", self._tencent_ocr_secret_key_edit)
        
        # 获取API密钥的提示
        tencent_hint = QLabel('<a href="https://console.cloud.tencent.com/cam/capi">前往腾讯云获取API密钥</a>')
        tencent_hint.setOpenExternalLinks(True)
        tencent_hint.setStyleSheet("color: #3B82F6;")
        tencent_layout.addRow("", tencent_hint)
        
        layout.addWidget(tencent_group)
        
        # 百度云文字识别 API设置
        baidu_group = QGroupBox("百度云文字识别")
        baidu_group.setStyleSheet(GROUPBOX_STYLE)
        baidu_layout = QFormLayout(baidu_group)
        baidu_layout.setSpacing(12)
        
        # 分组描述
        baidu_desc = QLabel("高精度云端识别，每月 3500 次免费额度")
        baidu_desc.setStyleSheet("color: #64748B; font-size: 9pt;")
        baidu_layout.addRow("", baidu_desc)
        
        # API Key
        self._baidu_ocr_api_key_edit = QLineEdit()
        self._baidu_ocr_api_key_edit.setStyleSheet(INPUT_STYLE)
        self._baidu_ocr_api_key_edit.setPlaceholderText("输入百度云 API Key...")
        self._baidu_ocr_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        baidu_layout.addRow("API Key:", self._baidu_ocr_api_key_edit)
        
        # Secret Key
        self._baidu_ocr_secret_key_edit = QLineEdit()
        self._baidu_ocr_secret_key_edit.setStyleSheet(INPUT_STYLE)
        self._baidu_ocr_secret_key_edit.setPlaceholderText("输入百度云 Secret Key...")
        self._baidu_ocr_secret_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        baidu_layout.addRow("Secret Key:", self._baidu_ocr_secret_key_edit)
        
        # 获取API密钥的提示
        baidu_hint = QLabel('<a href="https://cloud.baidu.com/product/ocr">前往百度云获取API密钥</a>')
        baidu_hint.setOpenExternalLinks(True)
        baidu_hint.setStyleSheet("color: #3B82F6;")
        baidu_layout.addRow("", baidu_hint)
        
        layout.addWidget(baidu_group)
        
        # 其他设置（兼容）
        group = QGroupBox("其他设置")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # API地址（旧版兼容）
        self._ocr_url_edit = QLineEdit()
        self._ocr_url_edit.setStyleSheet(INPUT_STYLE)
        self._ocr_url_edit.setPlaceholderText("http://127.0.0.1:1224")
        group_layout.addRow("备用API地址:", self._ocr_url_edit)
        
        # 识别语言
        self._ocr_lang_combo = QComboBox()
        self._ocr_lang_combo.setStyleSheet(INPUT_STYLE)
        self._ocr_lang_combo.addItems([
            "auto - 自动检测",
            "chi_sim - 简体中文",
            "chi_tra - 繁体中文",
            "eng - 英语",
            "jpn - 日语",
            "kor - 韩语",
        ])
        group_layout.addRow("识别语言:", self._ocr_lang_combo)
        
        layout.addWidget(group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="说明",
            items=get_help_panel_items("ocr")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        
        return scroll
    
    def _create_ding_tab(self) -> QWidget:
        """创建贴图设置页"""
        scroll, layout = self._create_scrollable_tab()
        
        group = QGroupBox("贴图设置")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # 数值输入框样式
        number_input_style = f"""
            QLineEdit {{
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
                color: {COLORS['text_primary']};
                font-size: 13px;
                min-width: 80px;
                max-width: 100px;
            }}
            QLineEdit:hover {{
                border-color: #D1D5DB;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
            }}
        """
        
        # 默认透明度
        opacity_layout = QHBoxLayout()
        self._ding_opacity_input = QLineEdit()
        self._ding_opacity_input.setStyleSheet(number_input_style)
        self._ding_opacity_input.setText("1.0")
        self._ding_opacity_input.setPlaceholderText("0.1-1.0")
        from PySide6.QtGui import QDoubleValidator
        opacity_validator = QDoubleValidator(0.1, 1.0, 1)
        opacity_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self._ding_opacity_input.setValidator(opacity_validator)
        self._ding_opacity_input.setToolTip("范围: 0.1-1.0")
        opacity_layout.addWidget(self._ding_opacity_input)
        opacity_hint = QLabel("(0.1 = 几乎透明, 1.0 = 完全不透明)")
        opacity_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        opacity_layout.addWidget(opacity_hint)
        opacity_layout.addStretch()
        group_layout.addRow("默认透明度:", opacity_layout)
        
        # 默认鼠标穿透
        self._ding_mouse_through_check = ModernCheckBox("默认启用鼠标穿透")
        group_layout.addRow("", self._ding_mouse_through_check)
        
        # 记住位置
        self._ding_remember_pos_check = ModernCheckBox("记住窗口位置")
        self._ding_remember_pos_check.setChecked(True)
        group_layout.addRow("", self._ding_remember_pos_check)
        
        layout.addWidget(group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="使用说明",
            items=get_help_panel_items("ding")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        return scroll
    
    def _create_anki_tab(self) -> QWidget:
        """创建Anki设置页"""
        scroll, layout = self._create_scrollable_tab()
        
        # Anki 入门指南（新用户引导）
        guide_group = self._create_anki_guide_group()
        layout.addWidget(guide_group)
        
        group = QGroupBox("AnkiConnect设置")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # 主机
        self._anki_host_edit = QLineEdit()
        self._anki_host_edit.setStyleSheet(INPUT_STYLE)
        self._anki_host_edit.setPlaceholderText("127.0.0.1")
        group_layout.addRow("主机:", self._anki_host_edit)
        
        # 端口
        self._anki_port_edit = QLineEdit()
        self._anki_port_edit.setStyleSheet(INPUT_STYLE)
        self._anki_port_edit.setPlaceholderText("8765")
        # 只允许输入数字，范围 1-65535
        self._anki_port_edit.setValidator(QIntValidator(1, 65535))
        group_layout.addRow("端口:", self._anki_port_edit)
        
        layout.addWidget(group)
        
        # Unsplash API Keys 设置
        unsplash_group = QGroupBox("Unsplash API Keys（可选）")
        unsplash_group.setStyleSheet(GROUPBOX_STYLE)
        unsplash_layout = QVBoxLayout(unsplash_group)
        unsplash_layout.setSpacing(8)
        
        # Unsplash Keys 容器
        self._unsplash_keys_container = QVBoxLayout()
        self._unsplash_keys_container.setSpacing(6)
        self._unsplash_key_edits = []  # 存储所有输入框
        unsplash_layout.addLayout(self._unsplash_keys_container)
        
        # 添加按钮行
        unsplash_btn_layout = QHBoxLayout()
        unsplash_add_btn = QPushButton("➕ 添加 Key")
        unsplash_add_btn.setStyleSheet(INPUT_STYLE)
        unsplash_add_btn.clicked.connect(lambda: self._add_api_key_row(
            self._unsplash_keys_container, self._unsplash_key_edits, "Unsplash Key"
        ))
        unsplash_btn_layout.addWidget(unsplash_add_btn)
        unsplash_btn_layout.addStretch()
        unsplash_layout.addLayout(unsplash_btn_layout)
        
        # Unsplash 获取链接
        unsplash_hint = QLabel('<a href="https://unsplash.com/developers">前往 Unsplash 获取 API Key</a>')
        unsplash_hint.setOpenExternalLinks(True)
        unsplash_hint.setStyleSheet("color: #3B82F6;")
        unsplash_layout.addWidget(unsplash_hint)
        
        layout.addWidget(unsplash_group)
        
        # Pixabay API Keys 设置
        pixabay_group = QGroupBox("Pixabay API Keys（可选）")
        pixabay_group.setStyleSheet(GROUPBOX_STYLE)
        pixabay_layout = QVBoxLayout(pixabay_group)
        pixabay_layout.setSpacing(8)
        
        # Pixabay Keys 容器
        self._pixabay_keys_container = QVBoxLayout()
        self._pixabay_keys_container.setSpacing(6)
        self._pixabay_key_edits = []  # 存储所有输入框
        pixabay_layout.addLayout(self._pixabay_keys_container)
        
        # 添加按钮行
        pixabay_btn_layout = QHBoxLayout()
        pixabay_add_btn = QPushButton("➕ 添加 Key")
        pixabay_add_btn.setStyleSheet(INPUT_STYLE)
        pixabay_add_btn.clicked.connect(lambda: self._add_api_key_row(
            self._pixabay_keys_container, self._pixabay_key_edits, "Pixabay Key"
        ))
        pixabay_btn_layout.addWidget(pixabay_add_btn)
        pixabay_btn_layout.addStretch()
        pixabay_layout.addLayout(pixabay_btn_layout)
        
        # Pixabay 获取链接
        pixabay_hint = QLabel('<a href="https://pixabay.com/api/docs/">前往 Pixabay 获取 API Key</a>')
        pixabay_hint.setOpenExternalLinks(True)
        pixabay_hint.setStyleSheet("color: #3B82F6;")
        pixabay_layout.addWidget(pixabay_hint)
        
        layout.addWidget(pixabay_group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="说明",
            items=get_help_panel_items("anki")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        
        return scroll
    
    def _create_anki_guide_group(self) -> QGroupBox:
        """创建 Anki 入门指南分组
        
        Feature: anki-setup-guide
        Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4
        """
        group = QGroupBox("📚 Anki 入门指南")
        group.setStyleSheet(GROUPBOX_STYLE)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        
        # 下载 Anki
        download_section = QLabel(
            '<b>📥 第一步：下载 Anki</b><br>'
            '官方下载地址：<a href="https://apps.ankiweb.net/">https://apps.ankiweb.net/</a>'
        )
        download_section.setOpenExternalLinks(True)
        download_section.setStyleSheet("color: #333;")
        download_section.setWordWrap(True)
        layout.addWidget(download_section)
        
        # 安装 AnkiConnect 插件
        install_section = QLabel(
            '<b>🔌 第二步：安装 AnkiConnect 插件</b><br>'
            '1. 打开 Anki，点击菜单 <b>工具</b> → <b>插件</b><br>'
            '2. 点击 <b>获取插件...</b><br>'
            '3. 输入插件代码：<span style="color: #EF4444; font-weight: bold; font-size: 14px;">2055492159</span><br>'
            '4. 点击 <b>确定</b>，等待安装完成<br>'
            '5. <span style="color: #F59E0B;">重启 Anki</span> 使插件生效'
        )
        install_section.setStyleSheet("color: #333;")
        install_section.setWordWrap(True)
        layout.addWidget(install_section)
        
        # 测试连接按钮
        btn_layout = QHBoxLayout()
        self._test_anki_btn = ModernButton("🔗 测试连接", ModernButton.PRIMARY)
        self._test_anki_btn.clicked.connect(self._test_anki_connection)
        btn_layout.addWidget(self._test_anki_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return group
    
    def _test_anki_connection(self):
        """测试 AnkiConnect 连接
        
        Feature: anki-setup-guide
        Requirements: 3.1, 3.2, 3.3
        """
        from screenshot_tool.services.anki_service import AnkiService
        
        connected, error = AnkiService.check_connection()
        
        if connected:
            QMessageBox.information(
                self,
                "连接成功！🤝",
                "✅ 和 Anki 接上头了！\n\n"
                "现在可以愉快地制卡啦～"
            )
        else:
            QMessageBox.warning(
                self,
                "连接失败 😴",
                f"❌ Anki 好像在睡觉\n\n"
                f"错误信息：{error}\n\n"
                "可能原因：\n"
                "• Anki 还没启动呢\n"
                "• AnkiConnect 插件没装\n"
                "• AnkiConnect 插件没开\n\n"
                "按照上面的步骤装好插件再试试？"
            )
    
    def _add_api_key_row(self, container: QVBoxLayout, edit_list: list, placeholder: str, value: str = ""):
        """添加一行 API Key 输入框
        
        Args:
            container: 容器布局
            edit_list: 输入框列表
            placeholder: 占位符文本
            value: 初始值
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        
        # 输入框
        edit = QLineEdit()
        edit.setStyleSheet(INPUT_STYLE)
        edit.setPlaceholderText(f"输入 {placeholder}...")
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setText(value)
        row_layout.addWidget(edit)
        
        # 删除按钮
        del_btn = QPushButton("🗑️")
        del_btn.setFixedWidth(36)
        del_btn.setStyleSheet(INPUT_STYLE)
        del_btn.setToolTip("删除此 Key")
        del_btn.clicked.connect(lambda: self._remove_api_key_row(container, edit_list, row_widget, edit))
        row_layout.addWidget(del_btn)
        
        container.addWidget(row_widget)
        edit_list.append(edit)
    
    def _remove_api_key_row(self, container: QVBoxLayout, edit_list: list, row_widget: QWidget, edit: QLineEdit):
        """删除一行 API Key 输入框
        
        Args:
            container: 容器布局
            edit_list: 输入框列表
            row_widget: 行组件
            edit: 输入框
        """
        if edit in edit_list:
            edit_list.remove(edit)
        container.removeWidget(row_widget)
        row_widget.deleteLater()
    
    def _create_highlight_tab(self) -> QWidget:
        """创建高亮设置页"""
        scroll, layout = self._create_scrollable_tab()
        
        group = QGroupBox("高亮设置")
        group.setStyleSheet(GROUPBOX_STYLE)
        group_layout = QFormLayout(group)
        group_layout.setSpacing(12)
        
        # 数值输入框样式
        number_input_style = f"""
            QLineEdit {{
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
                color: {COLORS['text_primary']};
                font-size: 13px;
                min-width: 80px;
                max-width: 100px;
            }}
            QLineEdit:hover {{
                border-color: #D1D5DB;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
            }}
        """
        
        # 自动启用高亮功能
        self._auto_select_highlight = ModernCheckBox("截图时自动启用高亮功能")
        self._auto_select_highlight.setChecked(True)
        group_layout.addRow("", self._auto_select_highlight)
        
        # 透明度
        opacity_layout = QHBoxLayout()
        self._highlight_opacity_input = QLineEdit()
        self._highlight_opacity_input.setStyleSheet(number_input_style)
        self._highlight_opacity_input.setText("0.3")
        self._highlight_opacity_input.setPlaceholderText("0.1-1.0")
        from PySide6.QtGui import QDoubleValidator
        highlight_opacity_validator = QDoubleValidator(0.1, 1.0, 1)
        highlight_opacity_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self._highlight_opacity_input.setValidator(highlight_opacity_validator)
        self._highlight_opacity_input.setToolTip("范围: 0.1-1.0")
        opacity_layout.addWidget(self._highlight_opacity_input)
        opacity_hint = QLabel("(0.3 推荐，越小越透明)")
        opacity_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        opacity_layout.addWidget(opacity_hint)
        opacity_layout.addStretch()
        group_layout.addRow("透明度:", opacity_layout)
        
        layout.addWidget(group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="说明",
            items=[
                "启用后，选区确定时自动切换到高亮工具",
                "高亮颜色在截图时通过工具栏选择",
                "透明度设置会应用到所有高亮标记",
            ]
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        
        return scroll
    
    def _create_markdown_tab(self) -> QWidget:
        """创建 Markdown 设置页
        
        Feature: web-to-markdown-dialog
        Requirements: 7.1, 7.2, 7.3
        """
        scroll, layout = self._create_scrollable_tab()
        
        # 数值输入框样式
        number_input_style = f"""
            QLineEdit {{
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: white;
                color: {COLORS['text_primary']};
                font-size: 13px;
                min-width: 80px;
                max-width: 100px;
            }}
            QLineEdit:hover {{
                border-color: #D1D5DB;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
            }}
        """
        
        # 内容选项
        content_group = QGroupBox("内容选项")
        content_group.setStyleSheet(GROUPBOX_STYLE)
        content_layout = QVBoxLayout(content_group)
        content_layout.setSpacing(12)
        
        # 包含图片
        self._markdown_include_images = ModernCheckBox("包含图片引用")
        self._markdown_include_images.setChecked(True)
        content_layout.addWidget(self._markdown_include_images)
        
        # 包含链接
        self._markdown_include_links = ModernCheckBox("包含链接")
        self._markdown_include_links.setChecked(True)
        content_layout.addWidget(self._markdown_include_links)
        
        layout.addWidget(content_group)
        
        # 网络设置
        network_group = QGroupBox("网络设置")
        network_group.setStyleSheet(GROUPBOX_STYLE)
        network_layout = QFormLayout(network_group)
        network_layout.setSpacing(12)
        
        # 超时时间
        timeout_layout = QHBoxLayout()
        self._markdown_timeout_input = QLineEdit()
        self._markdown_timeout_input.setStyleSheet(number_input_style)
        self._markdown_timeout_input.setText("30")
        self._markdown_timeout_input.setPlaceholderText("5-120")
        self._markdown_timeout_input.setValidator(QIntValidator(5, 120))
        self._markdown_timeout_input.setToolTip("范围: 5-120 秒")
        timeout_layout.addWidget(self._markdown_timeout_input)
        timeout_unit = QLabel("秒")
        timeout_unit.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-left: 4px;")
        timeout_layout.addWidget(timeout_unit)
        timeout_layout.addStretch()
        
        network_layout.addRow("超时时间:", timeout_layout)
        
        layout.addWidget(network_group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="使用说明",
            items=get_help_panel_items("markdown")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        
        return scroll
    
    def _create_pdf_tab(self) -> QWidget:
        """创建 文件转MD 设置页
        
        Feature: pdf-to-markdown
        """
        scroll, layout = self._create_scrollable_tab()
        
        # API Token 设置
        token_group = QGroupBox("MinerU API 设置")
        token_group.setStyleSheet(GROUPBOX_STYLE)
        token_layout = QFormLayout(token_group)
        token_layout.setSpacing(12)
        
        # API Token 输入框
        self._mineru_token_edit = QLineEdit()
        self._mineru_token_edit.setStyleSheet(INPUT_STYLE)
        self._mineru_token_edit.setPlaceholderText("输入 MinerU API Token...")
        self._mineru_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token_layout.addRow("API Token:", self._mineru_token_edit)
        
        # 获取 API 链接
        mineru_hint = QLabel('<a href="https://mineru.net/apiManage/token">前往 MinerU 获取 API Token</a>')
        mineru_hint.setOpenExternalLinks(True)
        mineru_hint.setStyleSheet("color: #3B82F6;")
        token_layout.addRow("", mineru_hint)
        
        layout.addWidget(token_group)
        
        # 使用说明（可折叠帮助面板）
        help_panel = CollapsibleHelpPanel(
            title="使用说明",
            items=get_help_panel_items("pdf")
        )
        layout.addWidget(help_panel)
        
        layout.addStretch()
        
        return scroll
    
    def _create_about_tab(self) -> QWidget:
        """创建关于标签页
        
        Feature: auto-update
        Requirements: 5.6, 5.7, 5.9
        """
        from screenshot_tool import __version__, __app_name__
        
        scroll, layout = self._create_scrollable_tab()
        
        # 应用信息
        app_group = QGroupBox("应用信息")
        app_group.setStyleSheet(GROUPBOX_STYLE)
        app_layout = QFormLayout(app_group)
        app_layout.setSpacing(12)
        
        # 应用名称
        app_name_label = QLabel(f"🐯 {__app_name__}")
        app_name_label.setStyleSheet("font-weight: bold; color: #F59E0B;")
        app_layout.addRow("应用名称:", app_name_label)
        
        # 当前版本
        self._about_current_version_label = QLabel(f"v{__version__}")
        self._about_current_version_label.setStyleSheet("font-weight: bold;")
        app_layout.addRow("当前版本:", self._about_current_version_label)
        
        # 作者
        author_label = QLabel("虎大王")
        app_layout.addRow("作者:", author_label)
        
        # 项目主页链接
        homepage_link = QLabel('<a href="https://hudawang.cn/">项目主页</a>')
        homepage_link.setOpenExternalLinks(True)
        homepage_link.setStyleSheet("color: #3B82F6;")
        app_layout.addRow("项目主页:", homepage_link)

        # GitHub 链接
        github_link = QLabel('<a href="https://github.com/wangwingzero/hugescreenshot-releases">GitHub 仓库</a>')
        github_link.setOpenExternalLinks(True)
        github_link.setStyleSheet("color: #3B82F6;")
        app_layout.addRow("项目地址:", github_link)
        
        # 打开配置文件夹按钮
        open_config_btn = QPushButton("📁 打开配置文件夹")
        open_config_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 12px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #999;
            }
        """)
        open_config_btn.clicked.connect(self._open_config_folder)
        app_layout.addRow("配置文件:", open_config_btn)
        
        # 换电脑说明
        migration_tip = QLabel(
            '<span style="color: #64748B; font-size: 12px;">'
            '🔒 您的配置仅保存在本地，我们不会上传任何数据~<br>'
            '💡 换电脑时请手动复制 <b>config.json</b> 到新电脑哦'
            '</span>'
        )
        migration_tip.setWordWrap(True)
        app_layout.addRow("", migration_tip)
        
        layout.addWidget(app_group)
        
        # 版本更新
        update_group = QGroupBox("版本更新")
        update_group.setStyleSheet(GROUPBOX_STYLE)
        update_layout = QVBoxLayout(update_group)
        update_layout.setSpacing(12)
        
        # 版本信息行
        version_row = QHBoxLayout()
        self._about_latest_version_label = QLabel("最新版本: 检查中...")
        self._about_latest_version_label.setStyleSheet("color: #64748B;")
        version_row.addWidget(self._about_latest_version_label)
        version_row.addStretch()
        update_layout.addLayout(version_row)
        
        # 按钮行
        btn_row = QHBoxLayout()
        
        self._about_check_update_btn = ModernButton("🔄 检查更新", ModernButton.SECONDARY)
        self._about_check_update_btn.clicked.connect(self._on_about_check_update)
        btn_row.addWidget(self._about_check_update_btn)
        
        btn_row.addStretch()
        update_layout.addLayout(btn_row)
        
        # 下载站点按钮容器（初始隐藏）
        # Feature: multi-proxy-download
        self._download_sites_container = QWidget()
        self._download_sites_layout = QVBoxLayout(self._download_sites_container)
        self._download_sites_layout.setContentsMargins(0, 8, 0, 0)
        self._download_sites_layout.setSpacing(8)
        
        # 下载站点说明
        sites_hint = QLabel("💡 选择下载站点（推荐优先，备用次之）：")
        sites_hint.setStyleSheet("color: #64748B; font-size: 12px;")
        self._download_sites_layout.addWidget(sites_hint)
        
        # 下载站点按钮行
        self._download_sites_btn_layout = QHBoxLayout()
        self._download_sites_btn_layout.setSpacing(8)
        self._download_site_buttons: List[ModernButton] = []
        self._download_sites_btn_layout.addStretch()
        self._download_sites_layout.addLayout(self._download_sites_btn_layout)
        
        self._download_sites_container.setVisible(False)
        update_layout.addWidget(self._download_sites_container)
        
        # 嵌入式下载进度组件
        # Feature: embedded-download-progress
        # Requirements: 1.2, 3.3, 3.4, 3.5, 3.6
        self._embedded_download_progress = EmbeddedDownloadProgress()
        self._embedded_download_progress.setVisible(False)  # 初始隐藏
        self._embedded_download_progress.cancel_requested.connect(self._on_embedded_download_cancel)
        self._embedded_download_progress.retry_requested.connect(self._on_embedded_download_retry)
        # Feature: seamless-update-flow
        # Requirements: 2.3 - 连接"立即更新"按钮信号
        self._embedded_download_progress.update_now_requested.connect(self._on_update_now_requested)
        update_layout.addWidget(self._embedded_download_progress)
        
        layout.addWidget(update_group)
        
        # 存储版本信息
        self._about_version_info = None
        
        return scroll
    
    def _open_config_folder(self):
        """打开配置文件夹
        
        Feature: unified-data-storage-path
        Requirements: 6.1, 6.2
        """
        import subprocess
        from screenshot_tool.core.config_manager import get_user_data_dir
        
        config_dir = get_user_data_dir()
        try:
            subprocess.Popen(f'explorer "{config_dir}"')
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "哎呀 😅", f"文件夹打不开：{e}")
    
    def _on_about_check_update(self):
        """检查更新按钮点击
        
        Feature: auto-update
        Requirements: 5.6
        """
        self._about_check_update_btn.setEnabled(False)
        self._about_check_update_btn.setText("检查中...")
        self._about_latest_version_label.setText("最新版本: 检查中...")
        
        # 使用 QThread 进行后台检查
        from PySide6.QtCore import QThread, Signal
        
        class CheckUpdateThread(QThread):
            """更新检查线程"""
            update_result = Signal(bool, str, str)  # has_update, version, notes
            update_error = Signal(str)  # error_msg
            
            def __init__(self, parent=None):
                super().__init__(parent)
            
            def run(self):
                try:
                    from screenshot_tool.services.update_service import VersionChecker
                    from screenshot_tool import __version__
                    
                    checker = VersionChecker()
                    # 公开仓库不需要 token
                    version_info = checker.get_latest_version("wangwingzero/hugescreenshot-releases")
                    
                    if version_info:
                        has_update = VersionChecker.is_newer_version(__version__, version_info.version)
                        self.update_result.emit(has_update, version_info.version, version_info.release_notes or "")
                        # 存储版本信息到父对象
                        if self.parent():
                            self.parent()._about_version_info = version_info
                    else:
                        self.update_error.emit("未找到版本信息")
                except Exception as e:
                    self.update_error.emit(str(e))
        
        # 创建并启动线程
        self._check_thread = CheckUpdateThread(self)
        self._check_thread.update_result.connect(self._update_about_ui)
        self._check_thread.update_error.connect(self._update_about_ui_error)
        self._check_thread.finished.connect(self._check_thread.deleteLater)
        self._check_thread.start()
    
    @Slot(bool, str, str)
    def _update_about_ui(self, has_update: bool, version: str, notes: str):
        """更新关于页面 UI（主线程）
        
        Args:
            has_update: 是否有新版本
            version: 最新版本号
            notes: 更新说明
        """
        self._about_check_update_btn.setEnabled(True)
        self._about_check_update_btn.setText("🔄 检查更新")
        
        if has_update:
            self._about_latest_version_label.setText(f"最新版本: v{version} (有新版本可用)")
            self._about_latest_version_label.setStyleSheet("color: #10B981; font-weight: bold;")
            # 显示下载站点按钮
            self._show_download_site_buttons(version)
        else:
            self._about_latest_version_label.setText(f"最新版本: v{version} (已是最新)")
            self._about_latest_version_label.setStyleSheet("color: #64748B;")
            # 隐藏下载站点按钮
            self._download_sites_container.setVisible(False)
    
    def _show_download_site_buttons(self, version: str):
        """显示下载站点按钮
        
        Feature: multi-proxy-download
        
        Args:
            version: 版本号
        """
        from screenshot_tool.services.update_service import GITHUB_PROXIES
        
        # 清除旧按钮
        for btn in self._download_site_buttons:
            btn.deleteLater()
        self._download_site_buttons.clear()
        
        # 移除 stretch
        while self._download_sites_btn_layout.count():
            item = self._download_sites_btn_layout.takeAt(0)
            if item.widget():
                pass  # 按钮已在上面删除
        
        # 创建新按钮（只显示前3个）
        for i, proxy in enumerate(GITHUB_PROXIES[:3]):
            # 提取域名作为显示名称
            domain = proxy.replace("https://", "").replace("http://", "").rstrip("/")
            
            # 前两个是推荐，后面是备用
            if i < 2:
                label = f"⚡ 站点{i+1}（推荐）"
                btn_type = ModernButton.PRIMARY
            else:
                label = f"🔗 站点{i+1}（备用）"
                btn_type = ModernButton.SECONDARY
            
            btn = ModernButton(label, btn_type)
            btn.setToolTip(f"从 {domain} 下载")
            btn.setProperty("proxy_url", proxy)
            btn.setProperty("version", version)
            btn.clicked.connect(self._on_download_site_clicked)
            
            self._download_sites_btn_layout.addWidget(btn)
            self._download_site_buttons.append(btn)
        
        self._download_sites_btn_layout.addStretch()
        self._download_sites_container.setVisible(True)
    
    def _on_download_site_clicked(self):
        """下载站点按钮点击
        
        Feature: multi-proxy-download
        """
        btn = self.sender()
        if not btn:
            return
        
        proxy_url = btn.property("proxy_url")
        version = btn.property("version")
        
        if not proxy_url or not version or not self._about_version_info:
            return
        
        # 构建下载 URL
        original_url = self._about_version_info.download_url
        # 提取原始 GitHub URL
        github_prefix = "https://github.com"
        idx = original_url.find(github_prefix)
        if idx > 0:
            original_url = original_url[idx:]
        
        download_url = f"{proxy_url.rstrip('/')}/{original_url}"
        
        # 自动确定保存路径
        save_path = self._get_auto_save_path(version)
        
        # 使用 DownloadStateManager（如果可用）
        if self._download_state_manager:
            from screenshot_tool.services.update_service import DownloadState
            
            # 显示嵌入式进度组件
            self._embedded_download_progress.setVisible(True)
            self._embedded_download_progress.set_state(DownloadState.IDLE)
            
            # 创建临时版本信息，使用选定的代理 URL
            from screenshot_tool.services.update_service import VersionInfo
            version_info = VersionInfo(
                version=self._about_version_info.version,
                download_url=download_url,
                release_notes=self._about_version_info.release_notes,
                file_size=self._about_version_info.file_size,
                published_at=self._about_version_info.published_at,
            )
            
            # 开始下载
            self._download_state_manager.start_download(version_info, save_path)
            
            # 禁用所有下载按钮
            for b in self._download_site_buttons:
                b.setEnabled(False)
            btn.setText("⬇️ 下载中...")
        else:
            # 回退到旧的下载方式
            self._on_download_site_legacy(download_url, save_path, version)
    
    @Slot(str)
    def _update_about_ui_error(self, error_msg: str):
        """更新关于页面 UI（错误情况）
        
        Args:
            error_msg: 错误信息
        """
        self._about_check_update_btn.setEnabled(True)
        self._about_check_update_btn.setText("🔄 检查更新")
        self._about_latest_version_label.setText(f"检查失败: {error_msg}")
        self._about_latest_version_label.setStyleSheet("color: #EF4444;")
    
    def _on_about_update(self):
        """更新版本按钮点击 - 已废弃，使用多站点按钮
        
        保留此方法以兼容旧代码，实际使用 _on_download_site_clicked
        """
        pass
    
    def _on_download_site_legacy(self, download_url: str, save_path: str, version: str):
        """旧的下载方式（使用独立窗口）
        
        Feature: multi-proxy-download
        
        Args:
            download_url: 下载 URL
            save_path: 保存路径
            version: 版本号
        """
        # 创建非模态进度窗口
        from .download_progress_window import DownloadProgressWindow
        self._download_progress_window = DownloadProgressWindow(version, self)
        
        # 创建下载管理器
        from screenshot_tool.services.update_service import DownloadManager
        self._download_manager = DownloadManager(self)
        
        # 连接信号
        self._download_manager.progress.connect(self._on_download_progress)
        self._download_manager.completed.connect(self._on_download_completed)
        self._download_manager.error.connect(self._on_download_error)
        self._download_progress_window.cancel_requested.connect(self._on_download_cancel)
        
        # 开始下载
        self._download_manager.start_download(download_url, save_path)
        
        # 显示进度窗口
        self._download_progress_window.show()
        
        # 禁用所有下载按钮
        for btn in self._download_site_buttons:
            btn.setEnabled(False)
    
    def _get_auto_save_path(self, version: str) -> str:
        """获取自动保存路径
        
        Feature: seamless-update-flow
        Requirements: 1.1, 1.2
        
        Args:
            version: 版本号
            
        Returns:
            保存路径 {exe_dir}/HuGeScreenshot-{version}.exe
        """
        import sys
        import os
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.getcwd()
        return os.path.join(exe_dir, f"HuGeScreenshot-{version}.exe")
    
    def _on_about_update_legacy(self, save_path: str):
        """旧的更新下载方式（使用独立窗口）
        
        Feature: simplify-update
        Requirements: 2.1, 2.2, 2.3, 2.8
        """
        version = self._about_version_info.version
        
        # 创建非模态进度窗口
        from .download_progress_window import DownloadProgressWindow
        self._download_progress_window = DownloadProgressWindow(version, self)
        
        # 创建下载管理器
        from screenshot_tool.services.update_service import DownloadManager
        self._download_manager = DownloadManager(self)
        
        # 连接信号
        self._download_manager.progress.connect(self._on_download_progress)
        self._download_manager.completed.connect(self._on_download_completed)
        self._download_manager.error.connect(self._on_download_error)
        self._download_progress_window.cancel_requested.connect(self._on_download_cancel)
        
        # 开始下载
        self._download_manager.start_download(
            self._about_version_info.download_url,
            save_path
        )
        
        # 显示进度窗口
        self._download_progress_window.show()
        
        # 禁用所有下载按钮
        for btn in self._download_site_buttons:
            btn.setEnabled(False)
    
    def _on_download_progress(self, downloaded: int, total: int, speed: float):
        """处理下载进度"""
        if hasattr(self, '_download_progress_window') and self._download_progress_window:
            self._download_progress_window.update_progress(downloaded, total, speed)
    
    def _on_download_completed(self, file_path: str):
        """处理下载完成"""
        if hasattr(self, '_download_progress_window') and self._download_progress_window:
            self._download_progress_window.show_completed(file_path)
        
        # 恢复按钮状态
        self._restore_download_site_buttons()
    
    def _on_download_error(self, error_msg: str):
        """处理下载错误"""
        if hasattr(self, '_download_progress_window') and self._download_progress_window:
            self._download_progress_window.show_error(error_msg)
        
        # 恢复按钮状态
        self._restore_download_site_buttons()
    
    def _on_download_cancel(self):
        """处理下载取消"""
        if hasattr(self, '_download_manager') and self._download_manager:
            self._download_manager.cancel_download()
        
        # 恢复按钮状态
        self._restore_download_site_buttons()
    
    def _restore_download_site_buttons(self):
        """恢复下载站点按钮状态
        
        Feature: multi-proxy-download
        """
        from screenshot_tool.services.update_service import GITHUB_PROXIES
        
        for i, btn in enumerate(self._download_site_buttons):
            btn.setEnabled(True)
            if i < 2:
                btn.setText(f"⚡ 站点{i+1}（推荐）")
            else:
                btn.setText(f"🔗 站点{i+1}（备用）")
    
    # ========== 嵌入式下载进度相关方法 ==========
    # Feature: embedded-download-progress
    # Requirements: 2.2, 2.3, 2.4, 3.1
    
    def _connect_download_state_manager(self):
        """连接下载状态管理器信号
        
        Feature: embedded-download-progress
        Requirements: 2.2, 2.3, 2.4, 3.1
        """
        if not self._download_state_manager:
            return
        
        # 连接信号
        self._download_state_manager.state_changed.connect(self._on_download_state_changed)
        self._download_state_manager.progress_updated.connect(self._on_download_progress_updated)
        
        # 同步当前状态
        self._sync_download_state()
    
    def cleanup(self):
        """清理资源，断开信号连接
        
        在对话框关闭时调用，防止悬空引用导致崩溃
        """
        # 断开下载状态管理器信号
        if self._download_state_manager:
            try:
                self._download_state_manager.state_changed.disconnect(self._on_download_state_changed)
                self._download_state_manager.progress_updated.disconnect(self._on_download_progress_updated)
            except (RuntimeError, TypeError):
                # 信号可能已经断开
                pass
    
    def _sync_download_state(self):
        """同步下载状态到 UI
        
        Feature: embedded-download-progress, multi-proxy-download
        Requirements: 2.2, 2.3, 2.4
        """
        if not self._download_state_manager:
            return
        
        # 检查 UI 组件是否存在
        if not hasattr(self, '_embedded_download_progress') or not hasattr(self, '_download_site_buttons'):
            return
        
        from screenshot_tool.services.update_service import DownloadState
        
        state = self._download_state_manager.state
        
        # 根据状态更新 UI
        if state == DownloadState.IDLE:
            self._embedded_download_progress.setVisible(False)
            self._restore_download_site_buttons()
        
        elif state == DownloadState.DOWNLOADING:
            self._embedded_download_progress.setVisible(True)
            self._embedded_download_progress.set_state(state)
            # 同步进度
            downloaded, total, speed = self._download_state_manager.progress
            self._embedded_download_progress.update_progress(downloaded, total, speed)
            # 禁用所有下载按钮
            for btn in self._download_site_buttons:
                btn.setEnabled(False)
        
        elif state == DownloadState.COMPLETED:
            self._embedded_download_progress.setVisible(True)
            self._embedded_download_progress.set_completed(self._download_state_manager.file_path)
            self._restore_download_site_buttons()
        
        elif state == DownloadState.FAILED:
            self._embedded_download_progress.setVisible(True)
            self._embedded_download_progress.set_error(self._download_state_manager.error_msg)
            self._restore_download_site_buttons()
        
        elif state == DownloadState.CANCELLED:
            self._embedded_download_progress.setVisible(True)
            self._embedded_download_progress.set_state(state)
            self._restore_download_site_buttons()
    
    @Slot(object)
    def _on_download_state_changed(self, state):
        """处理下载状态变化
        
        Feature: embedded-download-progress
        Requirements: 2.2, 2.3, 2.4
        """
        self._sync_download_state()
    
    @Slot(int, int, float)
    def _on_download_progress_updated(self, downloaded: int, total: int, speed: float):
        """处理下载进度更新
        
        Feature: embedded-download-progress
        Requirements: 2.2
        """
        if hasattr(self, '_embedded_download_progress'):
            self._embedded_download_progress.update_progress(downloaded, total, speed)
    
    def _on_embedded_download_cancel(self):
        """处理嵌入式下载取消
        
        Feature: embedded-download-progress
        Requirements: 2.4
        """
        if self._download_state_manager:
            self._download_state_manager.cancel_download()
    
    def _on_embedded_download_retry(self):
        """处理嵌入式下载重试
        
        Feature: embedded-download-progress
        Requirements: 2.4
        """
        if self._download_state_manager and self._about_version_info:
            # 重置状态
            self._download_state_manager.reset()
            # 重新触发下载
            self._on_about_update()
    
    def _on_update_now_requested(self):
        """处理立即更新请求 - 运行安装包进行静默覆盖安装
        
        Feature: seamless-update-flow
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        import os
        import subprocess
        import tempfile
        from PySide6.QtWidgets import QApplication, QMessageBox
        from screenshot_tool.services.update_service import UpdateExecutor
        from screenshot_tool.core.async_logger import async_debug_log
        
        # 获取下载的安装包路径
        file_path = ""
        if self._download_state_manager:
            file_path = self._download_state_manager.file_path
        elif hasattr(self, '_embedded_download_progress'):
            file_path = self._embedded_download_progress.file_path
        
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "哎呀 😅", "安装包跑丢了，重新下载一个？🏃")
            return
        
        # 禁用按钮，显示正在安装
        self._embedded_download_progress.set_updating()
        
        # 获取当前安装目录
        current_exe_path = UpdateExecutor.get_current_exe_path()
        install_dir = os.path.dirname(current_exe_path)
        
        async_debug_log(f"[UPDATE] 准备运行安装包: {file_path}")
        async_debug_log(f"[UPDATE] 安装目录: {install_dir}")
        
        try:
            # 构建静默安装命令
            cmd = [
                file_path,
                '/VERYSILENT',
                '/SUPPRESSMSGBOXES',
                '/NORESTART',
                '/CLOSEAPPLICATIONS',
                f'/DIR={install_dir}'
            ]
            
            async_debug_log(f"[UPDATE] 执行命令: {' '.join(cmd)}")
            
            # 启动安装程序（独立进程）
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True,
                start_new_session=True
            )
            
            async_debug_log("[UPDATE] 安装程序已启动，退出当前应用")
            
            # 退出当前应用
            QApplication.quit()
            
        except Exception as e:
            error_msg = f"启动安装程序失败: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            self._embedded_download_progress.reset_update_button()
            QMessageBox.critical(self, "启动失败 😵", f"安装程序启动失败：{error_msg}")
    
    def _start_update_download(self):
        """开始下载更新
        
        Feature: auto-update
        Requirements: 5.3
        """
        if not self._about_version_info:
            return
        
        # 显示下载进度对话框（使用 show() 代替 exec()，避免阻塞热键）
        progress_dialog = UpdateProgressDialog(self._about_version_info, self)
        progress_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dialog.show()
        progress_dialog.activateWindow()
    
    def _browse_save_path(self):
        """浏览保存路径"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择保存路径",
            self._save_path_edit.text()
        )
        if path:
            self._save_path_edit.setText(path)
    
    def _load_config(self):
        """加载配置到UI"""
        # 常规
        self._auto_start_check.setChecked(self._config.auto_start)
        self._save_path_edit.setText(self._config.save_path)
        self._auto_save_check.setChecked(self._config.auto_save)
        
        # 快捷键
        modifier = self._config.hotkey.screenshot_modifier.replace("+", "+").title()
        # 处理组合修饰键
        modifier_map = {
            "Alt": "Alt",
            "Ctrl": "Ctrl",
            "Shift": "Shift",
            "Ctrl+Alt": "Ctrl+Alt",
            "Ctrl+Shift": "Ctrl+Shift",
            "Alt+Shift": "Alt+Shift",
        }
        # 查找匹配的修饰键
        for key, value in modifier_map.items():
            if self._config.hotkey.screenshot_modifier.lower() == key.lower():
                modifier = value
                break
        self._set_combo_by_value(self._hotkey_modifier_combo, modifier)
        
        key = self._config.hotkey.screenshot_key.upper()
        self._set_combo_by_value(self._hotkey_key_combo, key)
        self._update_hotkey_preview()
        
        # 强制锁定热键设置
        # Feature: hotkey-force-lock
        # Requirements: 4.3
        self._force_lock_check.setChecked(self._config.hotkey.force_lock)
        self._retry_interval_input.setText(str(self._config.hotkey.retry_interval_ms))
        
        # 扩展快捷键设置
        # Feature: extended-hotkeys
        # 主界面快捷键
        self._main_window_hotkey_enable.setChecked(self._config.main_window_hotkey.enabled)
        self._set_combo_by_value(self._main_window_hotkey_modifier, 
                                  self._config.main_window_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._main_window_hotkey_key, 
                                  self._config.main_window_hotkey.key.upper())
        
        # 工作台快捷键
        self._clipboard_hotkey_enable.setChecked(self._config.clipboard_hotkey.enabled)
        self._set_combo_by_value(self._clipboard_hotkey_modifier, 
                                  self._config.clipboard_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._clipboard_hotkey_key, 
                                  self._config.clipboard_hotkey.key.upper())
        
        # 识别文字快捷键
        self._ocr_panel_hotkey_enable.setChecked(self._config.ocr_panel_hotkey.enabled)
        self._set_combo_by_value(self._ocr_panel_hotkey_modifier, 
                                  self._config.ocr_panel_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._ocr_panel_hotkey_key, 
                                  self._config.ocr_panel_hotkey.key.upper())
        
        # 聚光灯快捷键
        self._spotlight_hotkey_enable.setChecked(self._config.spotlight_hotkey.enabled)
        self._set_combo_by_value(self._spotlight_hotkey_modifier, 
                                  self._config.spotlight_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._spotlight_hotkey_key, 
                                  self._config.spotlight_hotkey.key.upper())
        
        # 鼠标高亮快捷键
        self._mouse_highlight_hotkey_enable.setChecked(self._config.mouse_highlight_hotkey.enabled)
        self._set_combo_by_value(self._mouse_highlight_hotkey_modifier, 
                                  self._config.mouse_highlight_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._mouse_highlight_hotkey_key, 
                                  self._config.mouse_highlight_hotkey.key.upper())
        
        # 恢复截图快捷键
        # Feature: screenshot-state-restore
        self._state_restore_hotkey_enable.setChecked(self._config.state_restore_hotkey.enabled)
        self._set_combo_by_value(self._state_restore_hotkey_modifier, 
                                  self._config.state_restore_hotkey.modifier.replace("+", "+").title())
        self._set_combo_by_value(self._state_restore_hotkey_key, 
                                  self._config.state_restore_hotkey.key.upper())
        
        # OCR引擎设置
        self._always_ocr_check.setChecked(self._config.always_ocr_on_screenshot)
        self._ocr_url_edit.setText(self._config.ocr_api_url)
        self._set_combo_by_value(self._ocr_lang_combo, self._config.ocr_language)
        
        # 腾讯云OCR API密钥
        self._tencent_ocr_secret_id_edit.setText(self._config.ocr.tencent_secret_id)
        self._tencent_ocr_secret_key_edit.setText(self._config.ocr.tencent_secret_key)
        
        # 百度云OCR API密钥
        self._baidu_ocr_api_key_edit.setText(self._config.ocr.baidu_api_key)
        self._baidu_ocr_secret_key_edit.setText(self._config.ocr.baidu_secret_key)
        
        # 贴图设置
        self._ding_opacity_input.setText(str(self._config.ding.default_opacity))
        self._ding_mouse_through_check.setChecked(self._config.ding.mouse_through_default)
        self._ding_remember_pos_check.setChecked(self._config.ding.remember_position)
        
        # Anki
        self._anki_host_edit.setText(self._config.anki_host)
        self._anki_port_edit.setText(str(self._config.anki_port))
        
        # 加载 Unsplash Keys
        # 先清空现有的容器和列表
        while self._unsplash_keys_container.count():
            item = self._unsplash_keys_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._unsplash_key_edits.clear()
        # 添加已保存的 Keys
        if self._config.anki_unsplash_keys:
            for key in self._config.anki_unsplash_keys.split(','):
                key = key.strip()
                if key:
                    self._add_api_key_row(
                        self._unsplash_keys_container, 
                        self._unsplash_key_edits, 
                        "Unsplash Key", 
                        key
                    )
        
        # 加载 Pixabay Keys
        # 先清空现有的
        while self._pixabay_keys_container.count():
            item = self._pixabay_keys_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pixabay_key_edits.clear()
        # 添加已保存的 Keys
        if self._config.anki_pixabay_key:
            for key in self._config.anki_pixabay_key.split(','):
                key = key.strip()
                if key:
                    self._add_api_key_row(
                        self._pixabay_keys_container, 
                        self._pixabay_key_edits, 
                        "Pixabay Key", 
                        key
                    )
        
        # 通知设置
        self._notify_startup_check.setChecked(self._config.notification.startup)
        self._notify_screenshot_save_check.setChecked(self._config.notification.screenshot_save)
        self._notify_ding_check.setChecked(self._config.notification.ding)
        self._notify_anki_check.setChecked(self._config.notification.anki)
        self._notify_gongwen_check.setChecked(self._config.notification.gongwen)
        self._notify_hotkey_update_check.setChecked(self._config.notification.hotkey_update)
        self._notify_software_update_check.setChecked(self._config.notification.software_update)
        self._notify_pdf_convert_check.setChecked(self._config.notification.pdf_convert)
        self._notify_regulation_check.setChecked(self._config.notification.regulation)
        self._notify_recording_check.setChecked(self._config.notification.recording)
        
        # 高亮
        self._auto_select_highlight.setChecked(self._config.auto_select_highlight)
        self._highlight_opacity_input.setText(str(self._config.highlight_opacity))
        
        # Markdown 设置
        self._markdown_include_images.setChecked(self._config.markdown.include_images)
        self._markdown_include_links.setChecked(self._config.markdown.include_links)
        self._markdown_timeout_input.setText(str(self._config.markdown.timeout))
        
        # 文件转MD 设置
        self._mineru_token_edit.setText(self._config.mineru.api_token)

    def _set_combo_by_value(self, combo: QComboBox, value: str):
        """根据值设置下拉框
        
        Args:
            combo: 下拉框组件
            value: 要匹配的值
        """
        value_lower = value.lower()
        for i in range(combo.count()):
            item_text = combo.itemText(i)
            # 精确匹配：值等于项文本，或值等于项文本的前缀部分（用 " - " 分隔）
            item_value = item_text.split(" - ")[0].lower() if " - " in item_text else item_text.lower()
            if item_value == value_lower:
                combo.setCurrentIndex(i)
                return
        # 如果没有精确匹配，尝试前缀匹配（兼容旧逻辑）
        for i in range(combo.count()):
            if combo.itemText(i).lower().startswith(value_lower):
                combo.setCurrentIndex(i)
                return
    
    def _get_combo_value(self, combo: QComboBox) -> str:
        """获取下拉框的值"""
        text = combo.currentText()
        return text.split(" - ")[0] if " - " in text else text
    
    def _on_save(self):
        """保存设置"""
        # 输入验证
        save_path = self._save_path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "验证有点问题 🤔", "还没设置保存路径呢，截图往哪放？📁")
            self._tab_widget.setCurrentIndex(0)  # 切换到常规选项卡
            self._save_path_edit.setFocus()
            return
        
        # 检查快捷键是否变更
        old_modifier = self._config.hotkey.screenshot_modifier
        old_key = self._config.hotkey.screenshot_key
        new_modifier = self._hotkey_modifier_combo.currentText().lower()
        new_key = self._hotkey_key_combo.currentText().lower()
        hotkey_changed = (old_modifier != new_modifier or old_key != new_key)
        
        # 检查强制锁定设置是否变更
        # Feature: hotkey-force-lock
        # Requirements: 4.3
        old_force_lock = self._config.hotkey.force_lock
        old_retry_interval = self._config.hotkey.retry_interval_ms
        new_force_lock = self._force_lock_check.isChecked()
        try:
            new_retry_interval = int(self._retry_interval_input.text() or "3000")
        except ValueError:
            new_retry_interval = 3000
        force_lock_changed = (
            old_force_lock != new_force_lock or 
            old_retry_interval != new_retry_interval
        )
        
        # 更新配置
        self._config.auto_start = self._auto_start_check.isChecked()
        self._config.save_path = save_path
        self._config.auto_save = self._auto_save_check.isChecked()
        
        # 快捷键设置
        self._config.hotkey.screenshot_modifier = new_modifier
        self._config.hotkey.screenshot_key = new_key
        
        # 强制锁定热键设置
        # Feature: hotkey-force-lock
        # Requirements: 4.3
        self._config.hotkey.force_lock = new_force_lock
        self._config.hotkey.retry_interval_ms = new_retry_interval
        
        # 扩展快捷键设置
        # Feature: extended-hotkeys
        # 主界面快捷键
        self._config.main_window_hotkey.enabled = self._main_window_hotkey_enable.isChecked()
        self._config.main_window_hotkey.modifier = self._main_window_hotkey_modifier.currentText().lower()
        self._config.main_window_hotkey.key = self._main_window_hotkey_key.currentText().lower()
        
        # 工作台快捷键
        self._config.clipboard_hotkey.enabled = self._clipboard_hotkey_enable.isChecked()
        self._config.clipboard_hotkey.modifier = self._clipboard_hotkey_modifier.currentText().lower()
        self._config.clipboard_hotkey.key = self._clipboard_hotkey_key.currentText().lower()
        
        # 识别文字快捷键
        self._config.ocr_panel_hotkey.enabled = self._ocr_panel_hotkey_enable.isChecked()
        self._config.ocr_panel_hotkey.modifier = self._ocr_panel_hotkey_modifier.currentText().lower()
        self._config.ocr_panel_hotkey.key = self._ocr_panel_hotkey_key.currentText().lower()
        
        # 聚光灯快捷键
        self._config.spotlight_hotkey.enabled = self._spotlight_hotkey_enable.isChecked()
        self._config.spotlight_hotkey.modifier = self._spotlight_hotkey_modifier.currentText().lower()
        self._config.spotlight_hotkey.key = self._spotlight_hotkey_key.currentText().lower()
        
        # 鼠标高亮快捷键
        self._config.mouse_highlight_hotkey.enabled = self._mouse_highlight_hotkey_enable.isChecked()
        self._config.mouse_highlight_hotkey.modifier = self._mouse_highlight_hotkey_modifier.currentText().lower()
        self._config.mouse_highlight_hotkey.key = self._mouse_highlight_hotkey_key.currentText().lower()
        
        # 恢复截图快捷键
        # Feature: screenshot-state-restore
        self._config.state_restore_hotkey.enabled = self._state_restore_hotkey_enable.isChecked()
        self._config.state_restore_hotkey.modifier = self._state_restore_hotkey_modifier.currentText().lower()
        self._config.state_restore_hotkey.key = self._state_restore_hotkey_key.currentText().lower()
        
        # OCR设置
        self._config.always_ocr_on_screenshot = self._always_ocr_check.isChecked()
        self._config.ocr_api_url = self._ocr_url_edit.text().strip()
        self._config.ocr_language = self._get_combo_value(self._ocr_lang_combo)
        
        # 腾讯云OCR API密钥（自动去除用户可能粘贴的前缀）
        tencent_id = self._tencent_ocr_secret_id_edit.text().strip()
        tencent_key = self._tencent_ocr_secret_key_edit.text().strip()
        # 兼容用户粘贴 "SecretId AKIDxxx" 或 "SecretKey xxx" 格式
        if tencent_id.lower().startswith("secretid "):
            tencent_id = tencent_id[9:].strip()
        if tencent_key.lower().startswith("secretkey "):
            tencent_key = tencent_key[10:].strip()
        self._config.ocr.tencent_secret_id = tencent_id
        self._config.ocr.tencent_secret_key = tencent_key
        
        # 百度云OCR API密钥
        self._config.ocr.baidu_api_key = self._baidu_ocr_api_key_edit.text().strip()
        self._config.ocr.baidu_secret_key = self._baidu_ocr_secret_key_edit.text().strip()
        
        # 贴图设置 - 确保透明度在有效范围内
        try:
            opacity = float(self._ding_opacity_input.text() or "1.0")
        except ValueError:
            opacity = 1.0
        self._config.ding.default_opacity = max(0.1, min(1.0, opacity))
        self._config.ding.mouse_through_default = self._ding_mouse_through_check.isChecked()
        self._config.ding.remember_position = self._ding_remember_pos_check.isChecked()
        
        self._config.anki_host = self._anki_host_edit.text().strip() or "127.0.0.1"
        port_text = self._anki_port_edit.text().strip()
        self._config.anki_port = int(port_text) if port_text else 8765
        
        # 收集 Unsplash Keys
        unsplash_keys = []
        for edit in self._unsplash_key_edits:
            key = edit.text().strip()
            if key:
                unsplash_keys.append(key)
        self._config.anki_unsplash_keys = ','.join(unsplash_keys)
        
        # 收集 Pixabay Keys
        pixabay_keys = []
        for edit in self._pixabay_key_edits:
            key = edit.text().strip()
            if key:
                pixabay_keys.append(key)
        self._config.anki_pixabay_key = ','.join(pixabay_keys)
        
        # 通知设置
        self._config.notification.startup = self._notify_startup_check.isChecked()
        self._config.notification.screenshot_save = self._notify_screenshot_save_check.isChecked()
        self._config.notification.ding = self._notify_ding_check.isChecked()
        self._config.notification.anki = self._notify_anki_check.isChecked()
        self._config.notification.gongwen = self._notify_gongwen_check.isChecked()
        self._config.notification.hotkey_update = self._notify_hotkey_update_check.isChecked()
        self._config.notification.software_update = self._notify_software_update_check.isChecked()
        self._config.notification.pdf_convert = self._notify_pdf_convert_check.isChecked()
        self._config.notification.regulation = self._notify_regulation_check.isChecked()
        self._config.notification.recording = self._notify_recording_check.isChecked()
        
        self._config.auto_select_highlight = self._auto_select_highlight.isChecked()
        # 从 QLineEdit 获取透明度值
        try:
            opacity = float(self._highlight_opacity_input.text() or "0.3")
        except ValueError:
            opacity = 0.3
        self._config.highlight_opacity = max(0.1, min(1.0, opacity))
        
        # Markdown 设置
        self._config.markdown.include_images = self._markdown_include_images.isChecked()
        self._config.markdown.include_links = self._markdown_include_links.isChecked()
        # 从 QLineEdit 获取超时值
        try:
            timeout = int(self._markdown_timeout_input.text() or "30")
        except ValueError:
            timeout = 30
        self._config.markdown.timeout = max(5, min(120, timeout))
        
        # 文件转MD 设置
        self._config.mineru.api_token = self._mineru_token_edit.text().strip()

        self.settingsSaved.emit(self._config)
        
        # 如果快捷键变更，发送信号
        if hotkey_changed:
            self.hotkeyChanged.emit(new_modifier, new_key)
        
        # 如果强制锁定设置变更，发送信号
        # Feature: hotkey-force-lock
        # Requirements: 4.3
        if force_lock_changed:
            self.forceLockChanged.emit(new_force_lock, new_retry_interval)
        
        self.accept()
    
    def _on_reset_all(self):
        """重置所有设置为默认值"""
        reply = QMessageBox.question(
            self,
            "确定要重置吗？🤔",
            "要把所有设置恢复出厂吗？\n\n这可是不能反悔的哦～",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 创建默认配置
            from ..core.config_manager import AppConfig
            default_config = AppConfig()
            self._config = default_config
            
            # 重新加载UI
            self._load_config()
            
            QMessageBox.information(
                self,
                "重置完成！✨",
                "一切都回到最初的样子啦～\n点击「保存」让它生效吧！"
            )
    
    def get_config(self) -> AppConfig:
        """获取配置"""
        return self._config



class AnkiCardDialog(QDialog):
    """Anki制卡对话框"""
    
    # 创建卡片信号
    cardCreated = Signal(dict)  # 卡片数据
    
    def __init__(
        self,
        ocr_text: str = "",
        translation_text: str = "",
        image: Optional[QImage] = None,
        deck_names: Optional[List[str]] = None,
        model_names: Optional[List[str]] = None,
        default_deck: str = "Default",
        default_model: str = "Basic",
        parent: Optional[QWidget] = None
    ):
        """
        初始化Anki制卡对话框
        
        Args:
            ocr_text: OCR识别文本
            translation_text: 翻译文本
            image: 截图图片
            deck_names: 可用牌组列表
            model_names: 可用笔记类型列表
            default_deck: 默认牌组
            default_model: 默认笔记类型
            parent: 父组件
        """
        super().__init__(parent)
        
        self._ocr_text = ocr_text
        self._translation_text = translation_text
        self._image = image
        self._deck_names = deck_names or ["Default"]
        self._model_names = model_names or ["Basic"]
        self._default_deck = default_deck
        self._default_model = default_model
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """设置UI"""
        self.setWindowTitle("📚 创建Anki卡片")
        self.setMinimumSize(450, 500)
        self.setStyleSheet(DIALOG_STYLE)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 牌组和笔记类型
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        # 牌组选择
        self._deck_combo = QComboBox()
        self._deck_combo.setStyleSheet(INPUT_STYLE)
        form_layout.addRow("牌组:", self._deck_combo)
        
        # 笔记类型选择
        self._model_combo = QComboBox()
        self._model_combo.setStyleSheet(INPUT_STYLE)
        form_layout.addRow("笔记类型:", self._model_combo)
        
        layout.addLayout(form_layout)
        
        # 正面内容
        front_group = QGroupBox("正面 (Front)")
        front_group.setStyleSheet(GROUPBOX_STYLE)
        front_layout = QVBoxLayout(front_group)
        
        self._front_edit = QTextEdit()
        self._front_edit.setStyleSheet(INPUT_STYLE)
        self._front_edit.setPlaceholderText("输入卡片正面内容...")
        self._front_edit.setMaximumHeight(100)
        front_layout.addWidget(self._front_edit)
        
        self._include_image_check = ModernCheckBox("包含截图")
        self._include_image_check.setChecked(True)
        front_layout.addWidget(self._include_image_check)
        
        layout.addWidget(front_group)
        
        # 背面内容
        back_group = QGroupBox("背面 (Back)")
        back_group.setStyleSheet(GROUPBOX_STYLE)
        back_layout = QVBoxLayout(back_group)
        
        self._back_edit = QTextEdit()
        self._back_edit.setStyleSheet(INPUT_STYLE)
        self._back_edit.setPlaceholderText("输入卡片背面内容...")
        self._back_edit.setMaximumHeight(100)
        back_layout.addWidget(self._back_edit)
        
        layout.addWidget(back_group)
        
        # 标签
        tags_layout = QFormLayout()
        self._tags_edit = QLineEdit()
        self._tags_edit.setStyleSheet(INPUT_STYLE)
        self._tags_edit.setPlaceholderText("标签1, 标签2, ...")
        tags_layout.addRow("标签:", self._tags_edit)
        layout.addLayout(tags_layout)
        
        layout.addStretch()
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._cancel_btn = ModernButton("取消", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        
        self._create_btn = ModernButton("创建卡片", ModernButton.PRIMARY)
        self._create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._create_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_data(self):
        """加载数据"""
        # 牌组
        self._deck_combo.addItems(self._deck_names)
        if self._default_deck in self._deck_names:
            self._deck_combo.setCurrentText(self._default_deck)
        
        # 笔记类型
        self._model_combo.addItems(self._model_names)
        if self._default_model in self._model_names:
            self._model_combo.setCurrentText(self._default_model)
        
        # 内容
        self._front_edit.setPlainText(self._ocr_text)
        self._back_edit.setPlainText(self._translation_text)
        
        # 图片选项
        self._include_image_check.setEnabled(self._image is not None)
        if self._image is None:
            self._include_image_check.setChecked(False)
    
    def _on_create(self):
        """创建卡片"""
        front_text = self._front_edit.toPlainText().strip()
        back_text = self._back_edit.toPlainText().strip()
        
        if not front_text:
            QMessageBox.warning(self, "温馨提示 💡", "正面内容空空如也，写点什么？✍️")
            return
        
        # 构建卡片数据
        card_data = {
            "deck_name": self._deck_combo.currentText(),
            "model_name": self._model_combo.currentText(),
            "front": front_text,
            "back": back_text,
            "tags": [t.strip() for t in self._tags_edit.text().split(",") if t.strip()],
            "include_image": self._include_image_check.isChecked() and self._image is not None,
            "image": self._image if self._include_image_check.isChecked() else None,
        }
        
        self.cardCreated.emit(card_data)
        self.accept()
    
    def get_card_data(self) -> Dict[str, Any]:
        """获取卡片数据"""
        return {
            "deck_name": self._deck_combo.currentText(),
            "model_name": self._model_combo.currentText(),
            "front": self._front_edit.toPlainText(),
            "back": self._back_edit.toPlainText(),
            "tags": [t.strip() for t in self._tags_edit.text().split(",") if t.strip()],
            "include_image": self._include_image_check.isChecked(),
        }
    
    def set_deck_names(self, names: List[str]):
        """设置牌组列表"""
        current = self._deck_combo.currentText()
        self._deck_combo.clear()
        self._deck_combo.addItems(names)
        if current in names:
            self._deck_combo.setCurrentText(current)
    
    def set_model_names(self, names: List[str]):
        """设置笔记类型列表"""
        current = self._model_combo.currentText()
        self._model_combo.clear()
        self._model_combo.addItems(names)
        if current in names:
            self._model_combo.setCurrentText(current)



# =====================================================
# =============== 更新对话框 ===============
# =====================================================

class UpdateConfirmDialog(QDialog):
    """更新确认对话框
    
    Feature: auto-update
    Requirements: 5.2, 5.4, 5.5
    """
    
    def __init__(self, version_info, parent: Optional[QWidget] = None):
        """
        初始化更新确认对话框
        
        Args:
            version_info: VersionInfo 对象
            parent: 父组件
        """
        super().__init__(parent)
        
        self._version_info = version_info
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        from screenshot_tool import __version__
        
        self.setWindowTitle("🔄 发现新版本")
        self.setMinimumSize(450, 350)
        self.setStyleSheet(DIALOG_STYLE)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 版本信息
        version_group = QGroupBox("版本信息")
        version_group.setStyleSheet(GROUPBOX_STYLE)
        version_layout = QFormLayout(version_group)
        version_layout.setSpacing(12)
        
        # 当前版本
        current_label = QLabel(f"v{__version__}")
        version_layout.addRow("当前版本:", current_label)
        
        # 新版本
        new_label = QLabel(f"v{self._version_info.version}")
        new_label.setStyleSheet("font-weight: bold; color: #10B981;")
        version_layout.addRow("新版本:", new_label)
        
        # 文件大小
        size_mb = self._version_info.file_size / (1024 * 1024)
        size_label = QLabel(f"{size_mb:.1f} MB")
        version_layout.addRow("文件大小:", size_label)
        
        # 发布时间
        if self._version_info.published_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(self._version_info.published_at.replace('Z', '+00:00'))
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                time_str = self._version_info.published_at
            time_label = QLabel(time_str)
            version_layout.addRow("发布时间:", time_label)
        
        layout.addWidget(version_group)
        
        # 更新说明
        notes_group = QGroupBox("更新说明")
        notes_group.setStyleSheet(GROUPBOX_STYLE)
        notes_layout = QVBoxLayout(notes_group)
        
        notes_browser = QTextBrowser()
        notes_browser.setReadOnly(True)
        notes_browser.setOpenExternalLinks(True)
        notes_browser.setStyleSheet(INPUT_STYLE)
        notes_browser.setHtml(markdown_to_html(self._version_info.release_notes) if self._version_info.release_notes else "<p>暂无更新说明</p>")
        notes_browser.setMaximumHeight(200)
        notes_layout.addWidget(notes_browser)
        
        layout.addWidget(notes_group)
        
        # 提示
        hint_label = QLabel("⚠️ 更新将关闭当前程序，完成后自动重启")
        hint_label.setStyleSheet("color: #E67E22;")
        layout.addWidget(hint_label)
        
        layout.addStretch()
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._later_btn = ModernButton("稍后", ModernButton.SECONDARY)
        self._later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._later_btn)
        
        self._update_btn = ModernButton("立即更新", ModernButton.PRIMARY)
        self._update_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._update_btn)
        
        layout.addLayout(btn_layout)


class UpdateProgressDialog(QDialog):
    """更新进度对话框
    
    Feature: auto-update
    Requirements: 5.3
    """
    
    def __init__(self, version_info, parent: Optional[QWidget] = None):
        """
        初始化更新进度对话框
        
        Args:
            version_info: VersionInfo 对象
            parent: 父组件
        """
        super().__init__(parent)
        
        self._version_info = version_info
        self._update_service = None
        self._setup_ui()
        self._start_download()
    
    def _setup_ui(self):
        """设置UI"""
        self.setWindowTitle("⬇️ 下载更新")
        self.setMinimumSize(450, 280)
        self.resize(450, 280)
        self.setStyleSheet(DIALOG_STYLE)
        
        # 禁止关闭按钮（下载中）
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel(f"正在下载 v{self._version_info.version}...")
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._progress_bar)
        
        # 状态信息
        status_layout = QHBoxLayout()
        
        self._downloaded_label = QLabel("已下载: 0 MB")
        status_layout.addWidget(self._downloaded_label)
        
        status_layout.addStretch()
        
        self._speed_label = QLabel("速度: -- KB/s")
        status_layout.addWidget(self._speed_label)
        
        layout.addLayout(status_layout)
        
        layout.addStretch()
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._cancel_btn = ModernButton("取消", ModernButton.SECONDARY)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        
        self._install_btn = ModernButton("安装", ModernButton.PRIMARY)
        self._install_btn.clicked.connect(self._on_install)
        self._install_btn.setEnabled(False)
        self._install_btn.setVisible(False)
        btn_layout.addWidget(self._install_btn)
        
        layout.addLayout(btn_layout)
    
    def _start_download(self):
        """开始下载"""
        try:
            from screenshot_tool.services.update_service import UpdateService
            
            self._update_service = UpdateService(parent=self)
            
            # 连接信号
            self._update_service.update_progress.connect(self._on_progress)
            self._update_service.update_completed.connect(self._on_completed)
            self._update_service.update_error.connect(self._on_error)
            
            # 开始下载
            self._update_service.download_update(self._version_info)
            
        except Exception as e:
            QMessageBox.critical(self, "哎呀 😅", f"下载启动失败：{str(e)}")
            self.reject()
    
    @Slot(int, int, float)
    def _on_progress(self, downloaded: int, total: int, speed: float):
        """处理下载进度
        
        Args:
            downloaded: 已下载字节数
            total: 总字节数
            speed: 下载速度 (KB/s)
        """
        if total > 0:
            progress = int((downloaded / total) * 100)
            self._progress_bar.setValue(progress)
        
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024) if total > 0 else 0
        
        self._downloaded_label.setText(f"已下载: {downloaded_mb:.1f} / {total_mb:.1f} MB")
        self._speed_label.setText(f"速度: {speed:.1f} KB/s")
    
    @Slot(str)
    def _on_completed(self, version: str):
        """处理下载完成 - 显示确认对话框
        
        Feature: fullupdate-inplace-install
        Requirements: 6.1, 6.2, 6.3
        
        Args:
            version: 新版本号
        """
        self._progress_bar.setValue(100)
        self._downloaded_label.setText("下载完成！")
        self._speed_label.setText("")
        
        self._cancel_btn.setVisible(False)
        self._install_btn.setVisible(False)
        
        # 显示确认对话框
        reply = QMessageBox.question(
            self,
            "安装更新 🎉",
            f"新版本 v{version} 已下载完成！\n\n"
            "点击「是」立即安装，应用将自动重启。\n"
            "点击「否」稍后手动安装。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 用户确认安装，延迟执行以让 UI 有时间更新
            self._downloaded_label.setText("正在应用更新...")
            QTimer.singleShot(500, self._auto_launch_new_version)
        else:
            # 用户选择稍后安装
            QMessageBox.information(
                self,
                "稍后安装",
                "安装包已保存，下次启动时可以手动安装。"
            )
            self.accept()
    
    @Slot(str)
    def _on_error(self, error_msg: str):
        """处理下载错误
        
        Args:
            error_msg: 错误信息
        """
        QMessageBox.critical(self, "下载失败 😢", error_msg)
        self.reject()
    
    def _on_cancel(self):
        """取消下载"""
        reply = QMessageBox.question(
            self,
            "确定要取消吗？",
            "下载进行中，真的要放弃吗？🥺",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self._update_service:
                self._update_service.cancel_download()
            self.reject()
    
    def _auto_launch_new_version(self):
        """运行安装包进行静默覆盖安装
        
        Feature: fullupdate-inplace-install
        Requirements: 3.1, 3.2, 6.1, 6.2, 6.3
        
        下载完成后，显示确认对话框，用户确认后运行安装包
        并传递静默安装参数，自动覆盖安装到原来的安装目录。
        """
        import sys
        import os
        import subprocess
        import tempfile
        
        from screenshot_tool.core.async_logger import async_debug_log
        from screenshot_tool.services.update_service import UpdateExecutor
        
        # 获取安装目录（优先使用配置中保存的路径）
        install_dir = ""
        if self._update_service:
            install_dir = self._update_service.get_install_path()
        
        # 如果配置中没有保存的路径，使用当前 exe 所在目录
        if not install_dir:
            current_exe_path = UpdateExecutor.get_current_exe_path()
            install_dir = os.path.dirname(current_exe_path)
        
        # 获取下载的安装包路径
        if self._version_info:
            temp_dir = tempfile.gettempdir()
            setup_exe_path = os.path.join(temp_dir, f"HuGeScreenshot-{self._version_info.version}-Setup.exe")
        else:
            async_debug_log("[UPDATE] 警告: 没有版本信息，无法确定安装包路径")
            QMessageBox.critical(self, "更新失败 😢", "找不到安装包，更新失败了")
            self.accept()
            return
        
        # 验证安装包存在
        if not os.path.exists(setup_exe_path):
            async_debug_log(f"[UPDATE] 安装包不存在: {setup_exe_path}")
            QMessageBox.critical(self, "更新失败 😢", "安装包不见了，请重新下载")
            self.accept()
            return
        
        async_debug_log(f"[UPDATE] 准备运行安装包: {setup_exe_path}")
        async_debug_log(f"[UPDATE] 安装目录: {install_dir}")
        
        try:
            # 构建静默安装命令
            # /SILENT - 静默安装（显示进度条）
            # /CLOSEAPPLICATIONS - 关闭正在使用的应用
            # /DIR="..." - 指定安装目录（覆盖到原来的位置）
            cmd = [
                setup_exe_path,
                '/SILENT',
                '/CLOSEAPPLICATIONS',
                f'/DIR={install_dir}'
            ]
            
            async_debug_log(f"[UPDATE] 执行命令: {' '.join(cmd)}")
            
            # 启动安装程序（独立进程）
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True,
                start_new_session=True
            )
            
            async_debug_log("[UPDATE] 安装程序已启动，退出当前应用")
            
            # 退出当前应用，让安装程序可以覆盖文件
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
            
        except Exception as e:
            error_msg = f"启动安装程序失败: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            QMessageBox.critical(
                self, 
                "更新失败 😢", 
                f"安装程序启动失败：{error_msg}\n\n没关系，旧版本继续陪你～"
            )
            self.accept()
    
    def _on_install(self):
        """安装更新（保留作为手动触发入口）
        
        Note: 现在下载完成后会自动启动新版本，此方法保留作为备用
        """
        self._auto_launch_new_version()
    
    def _restart_app(self):
        """重启应用并执行更新（已弃用，保留作为回退方案）
        
        Feature: auto-restart-update
        Note: 现在使用 _auto_launch_new_version 方法直接启动新版本
        """
        # 直接调用新的自动启动方法
        self._auto_launch_new_version()
    
    def _restart_app_fallback(self, exe_path: str, current_pid: int):
        """回退方案：使用批处理脚本重启
        
        当新版本启动失败时可以使用此方法。
        """
        import subprocess
        import os
        import tempfile
        
        from screenshot_tool.core.async_logger import async_debug_log
        
        try:
            # 创建批处理脚本等待当前进程退出后再启动新版本
            bat_content = f'''@echo off
:wait_loop
tasklist /FI "PID eq {current_pid}" 2>nul | find /I "{current_pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
timeout /t 1 /nobreak >nul
start "" "{exe_path}"
del "%~f0"
'''
            bat_dir = tempfile.gettempdir()
            bat_path = os.path.join(bat_dir, f"hg_update_{current_pid}.bat")
            
            with open(bat_path, 'w', encoding='ascii', errors='ignore') as f:
                f.write(bat_content)
            
            async_debug_log(f"[UPDATE] 创建回退重启脚本: {bat_path}")
            
            # 启动批处理脚本（隐藏窗口）
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            subprocess.Popen(
                ['cmd', '/c', bat_path],
                startupinfo=startupinfo,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        except Exception as e:
            async_debug_log(f"[UPDATE] 回退方案也失败: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        if self._update_service and self._update_service.is_downloading:
            event.ignore()
            self._on_cancel()
        else:
            event.accept()
