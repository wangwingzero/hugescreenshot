"""
升级提示组件

Feature: subscription-system
Requirements: 4.5
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QProgressBar
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from typing import Optional, Dict, Any

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


class UsageBar(QWidget):
    """使用量进度条"""
    
    def __init__(self, feature_name: str, parent=None):
        super().__init__(parent)
        self._feature_name = feature_name
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 标签行
        label_layout = QHBoxLayout()
        
        self._name_label = QLabel(self._feature_name)
        label_layout.addWidget(self._name_label)
        
        label_layout.addStretch()
        
        self._count_label = QLabel("0/0")
        self._count_label.setStyleSheet("color: #666;")
        label_layout.addWidget(self._count_label)
        
        layout.addLayout(label_layout)
        
        # 进度条
        self._progress = QProgressBar()
        self._progress.setMaximumHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #1890ff;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._progress)
    
    def set_usage(self, used: int, limit: int):
        """设置使用量
        
        Args:
            used: 已使用次数
            limit: 限制次数
        """
        self._count_label.setText(f"{used}/{limit}")
        self._progress.setMaximum(limit)
        self._progress.setValue(used)
        
        # 根据使用量设置颜色
        if used >= limit:
            color = "#ff4d4f"  # 红色
        elif used >= limit * 0.8:
            color = "#faad14"  # 黄色
        else:
            color = "#1890ff"  # 蓝色
        
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #f0f0f0;
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)


class UpgradePromptDialog(QDialog):
    """升级提示对话框
    
    Requirements: 4.5
    
    Signals:
        upgrade_clicked: 点击升级按钮
        login_clicked: 点击登录按钮
    """
    
    upgrade_clicked = Signal()
    login_clicked = Signal()
    
    def __init__(
        self, 
        feature_name: str,
        reason: str,
        usage_info: Optional[Dict[str, Any]] = None,
        parent=None
    ):
        """初始化升级提示对话框
        
        Args:
            feature_name: 功能名称
            reason: 不可用原因
            usage_info: 使用量信息 {usage, limit, remaining}
            parent: 父窗口
        """
        super().__init__(parent)
        self._feature_name = feature_name
        self._reason = reason
        self._usage_info = usage_info
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("功能限制")
        self.setFixedSize(380, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        
        # 图标和标题
        header_layout = QHBoxLayout()
        
        icon_label = QLabel("⚠️")
        icon_label.setFont(QFont("Segoe UI Emoji", 32))
        header_layout.addWidget(icon_label)
        
        title = QLabel(f"「{self._feature_name}」功能受限")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setWordWrap(True)
        header_layout.addWidget(title, 1)
        
        layout.addLayout(header_layout)
        
        # 原因说明
        reason_label = QLabel(self._reason)
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("""
            QLabel {
                color: #666;
                padding: 10px;
                background-color: #fafafa;
                border-radius: 4px;
            }
        """)
        layout.addWidget(reason_label)
        
        # 使用量信息
        if self._usage_info:
            usage_bar = UsageBar("今日使用量")
            usage_bar.set_usage(
                self._usage_info.get("usage", 0),
                self._usage_info.get("limit", 10)
            )
            layout.addWidget(usage_bar)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line)
        
        # VIP 特权说明
        vip_info = QLabel(
            "☕ 请作者喝杯咖啡（9.9元），您的支持是我持续更新的动力！\n"
            "赞助开发可解锁：\n"
            "• 无限次翻译 • 无限次网页转 Markdown\n"
            "• 录屏、公文、AI 等高级功能"
        )
        vip_info.setStyleSheet("color: #52c41a; line-height: 1.6;")
        layout.addWidget(vip_info)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        upgrade_btn = QPushButton("☕ 赞助开发")
        upgrade_btn.setMinimumHeight(38)
        upgrade_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C00;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFA500;
            }
        """)
        upgrade_btn.clicked.connect(self._on_upgrade)
        btn_layout.addWidget(upgrade_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_upgrade(self):
        """点击升级"""
        from screenshot_tool.services.subscription import SubscriptionManager
        from screenshot_tool.ui.payment_dialog import PaymentDialog
        
        manager = SubscriptionManager.instance()
        if not manager or not manager.is_logged_in:
            # 未登录，发出登录信号
            self.login_clicked.emit()
            self.accept()
            return
        
        # 已登录，打开支付对话框
        user_id = manager.state.user_id
        payment_service = manager.payment_service
        
        dialog = PaymentDialog(
            payment_service=payment_service,
            user_id=user_id,
            parent=self
        )
        dialog.payment_success.connect(self._on_payment_success)
        
        self.accept()  # 先关闭当前对话框
        dialog.exec()
    
    def _on_payment_success(self):
        """支付成功回调"""
        from screenshot_tool.services.subscription import SubscriptionManager
        
        manager = SubscriptionManager.instance()
        if manager and manager.license_service:
            manager.license_service.verify(force=True)
        self.upgrade_clicked.emit()


class FeatureLimitBanner(QWidget):
    """功能限制横幅（嵌入式）
    
    用于在功能界面顶部显示使用量限制提示。
    """
    
    upgrade_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.hide()  # 默认隐藏
    
    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #fff7e6;
                border: 1px solid #ffd591;
                border-radius: 4px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        
        self._icon = QLabel("⚡")
        layout.addWidget(self._icon)
        
        self._message = QLabel()
        self._message.setStyleSheet("color: #d46b08;")
        layout.addWidget(self._message, 1)
        
        self._upgrade_btn = QPushButton("☕ 请喝咖啡")
        self._upgrade_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C00;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #FFA500;
            }
        """)
        self._upgrade_btn.clicked.connect(self.upgrade_clicked.emit)
        layout.addWidget(self._upgrade_btn)
    
    def show_limit(self, remaining: int, limit: int, feature_name: str = "此功能"):
        """显示限制提示
        
        Args:
            remaining: 剩余次数
            limit: 总限制
            feature_name: 功能名称
        """
        if remaining <= 0:
            self._message.setText(f"{feature_name}今日次数已用完")
            self._icon.setText("🚫")
            self.setStyleSheet("""
                QWidget {
                    background-color: #fff1f0;
                    border: 1px solid #ffa39e;
                    border-radius: 4px;
                }
            """)
            self._message.setStyleSheet("color: #cf1322;")
        elif remaining <= limit * 0.3:
            self._message.setText(f"{feature_name}今日剩余 {remaining} 次")
            self._icon.setText("⚠️")
        else:
            self.hide()
            return
        
        self.show()
    
    def hide_limit(self):
        """隐藏限制提示"""
        self.hide()
