"""
支付对话框 - 虎皮椒支付

显示支付二维码和链接，支持查询订单状态。
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QPixmap, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def payment_log(message: str):
    """支付对话框日志"""
    _debug_log(message, "PAYMENT")


class PaymentDialog(QDialog):
    """支付对话框
    
    显示虎皮椒支付二维码，支持自动轮询订单状态。
    
    Signals:
        payment_success: 支付成功
    """
    
    payment_success = Signal()
    
    # 轮询间隔（毫秒）
    POLL_INTERVAL = 3000
    # 最大轮询次数（3秒 * 100 = 5分钟）
    MAX_POLL_COUNT = 100
    
    def __init__(
        self,
        payment_service=None,
        user_id: Optional[str] = None,
        parent=None
    ):
        """初始化支付对话框
        
        Args:
            payment_service: 支付服务实例
            user_id: 当前用户 ID
            parent: 父窗口
        """
        super().__init__(parent)
        self._payment_service = payment_service
        self._user_id = user_id
        self._payment_url = None
        self._qrcode_url = None
        self._trade_order_id = None
        self._poll_count = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_order_status)
        self._network_manager = QNetworkAccessManager(self)
        
        self._setup_ui()
        self._create_payment()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("☕ 请作者喝杯咖啡 - 虎哥截图")
        self.setFixedSize(420, 540)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        # 标题
        title = QLabel("☕ 请作者喝杯咖啡")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 价格
        price = QLabel("¥9.9")
        price.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
        price.setStyleSheet("color: #ff4d4f;")
        price.setAlignment(Qt.AlignCenter)
        layout.addWidget(price)

        # 说明
        desc = QLabel(
            "虎哥截图是我业余时间开发的免费工具\n"
            "您的支持是我持续更新的最大动力！\n"
            "赞助后可解锁终身 VIP 权益 ❤️"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666; line-height: 1.5;")
        layout.addWidget(desc)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line1)
        
        # 二维码区域
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setFixedSize(200, 200)
        self._qr_label.setStyleSheet("""
            QLabel {
                background-color: #fafafa;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        self._qr_label.setText("正在创建订单...")
        layout.addWidget(self._qr_label, alignment=Qt.AlignCenter)
        
        # 提示
        self._tip_label = QLabel("使用微信或支付宝扫码支付")
        self._tip_label.setAlignment(Qt.AlignCenter)
        self._tip_label.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self._tip_label)
        
        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._status_label)

        # 打开支付页面按钮
        self._open_btn = QPushButton("🔗 打开支付页面")
        self._open_btn.setMinimumHeight(40)
        self._open_btn.setStyleSheet("""
            QPushButton {
                background-color: #1890ff;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #40a9ff;
            }
            QPushButton:disabled {
                background-color: #d9d9d9;
            }
        """)
        self._open_btn.clicked.connect(self._open_payment_page)
        self._open_btn.setEnabled(False)
        layout.addWidget(self._open_btn)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line2)
        
        # VIP 权益说明
        benefits = QLabel(
            "🎁 赞助后可享受终身 VIP 权益：\n"
            "• 无限次翻译 • 无限次网页转 Markdown\n"
            "• 录屏功能 • 公文格式化 • 更多高级功能\n"
            "💝 一次赞助，终身有效，感谢支持！"
        )
        benefits.setStyleSheet("""
            QLabel {
                color: #52c41a;
                background-color: #f6ffed;
                border: 1px solid #b7eb8f;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        benefits.setAlignment(Qt.AlignCenter)
        layout.addWidget(benefits)
        
        layout.addStretch()
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新状态")
        refresh_btn.setMinimumHeight(38)
        refresh_btn.clicked.connect(self._manual_check_status)
        btn_layout.addWidget(refresh_btn)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setMinimumHeight(38)
        close_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _create_payment(self):
        """创建支付订单"""
        if not self._payment_service or not self._user_id:
            self._qr_label.setText("请先登录")
            return
        
        try:
            result = self._payment_service.create_payment(self._user_id)
            
            if result.success:
                self._payment_url = result.url
                self._qrcode_url = result.url_qrcode
                payment_log(f"订单创建成功: {result.open_order_id}")
                
                # 加载二维码图片
                if result.url_qrcode:
                    self._load_qrcode(result.url_qrcode)
                else:
                    self._qr_label.setText("请点击下方按钮\n打开支付页面")
                
                self._open_btn.setEnabled(True)
                
                # 开始轮询订单状态
                self._start_polling()
            else:
                payment_log(f"订单创建失败: {result.message}")
                self._qr_label.setText(f"创建订单失败\n{result.message}")
                
        except Exception as e:
            payment_log(f"创建订单异常: {e}")
            self._qr_label.setText(f"创建订单失败\n{str(e)}")
    
    def _load_qrcode(self, url: str):
        """加载二维码图片
        
        Args:
            url: 二维码图片 URL
        """
        request = QNetworkRequest(QUrl(url))
        reply = self._network_manager.get(request)
        reply.finished.connect(lambda: self._on_qrcode_loaded(reply))
    
    def _on_qrcode_loaded(self, reply: QNetworkReply):
        """二维码加载完成"""
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            
            if not pixmap.isNull():
                # 缩放到合适大小
                pixmap = pixmap.scaled(
                    180, 180,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._qr_label.setPixmap(pixmap)
                payment_log("二维码加载成功")
            else:
                self._qr_label.setText("二维码加载失败")
        else:
            payment_log(f"二维码加载失败: {reply.errorString()}")
            self._qr_label.setText("二维码加载失败\n请点击下方按钮支付")
        
        reply.deleteLater()
    
    def _open_payment_page(self):
        """打开支付页面"""
        if self._payment_url:
            payment_log(f"打开支付页面: {self._payment_url}")
            QDesktopServices.openUrl(QUrl(self._payment_url))
        else:
            QMessageBox.warning(self, "温馨提示 💡", "支付链接还在生成中，稍等～")
    
    def _start_polling(self):
        """开始轮询订单状态"""
        self._poll_count = 0
        self._poll_timer.start(self.POLL_INTERVAL)
        self._status_label.setText("等待支付...")
    
    def _stop_polling(self):
        """停止轮询"""
        self._poll_timer.stop()
    
    def _poll_order_status(self):
        """轮询订单状态"""
        self._poll_count += 1
        
        if self._poll_count > self.MAX_POLL_COUNT:
            self._stop_polling()
            self._status_label.setText("轮询超时，请手动刷新")
            return
        
        self._check_payment_status()
    
    def _manual_check_status(self):
        """手动检查支付状态"""
        self._status_label.setText("正在查询...")
        self._check_payment_status()
    
    def _check_payment_status(self):
        """检查支付状态"""
        if not self._payment_service:
            return
        
        # 这里需要通过 Supabase 查询订阅状态
        # 因为虎皮椒回调会更新 Supabase 中的订阅记录
        try:
            from screenshot_tool.services.subscription import SubscriptionManager
            
            manager = SubscriptionManager.instance()
            if manager and manager.license_service:
                # 强制刷新订阅状态
                subscription = manager.license_service.verify(force=True)
                
                if subscription.is_vip:
                    self._on_payment_success()
                    return
            
            # 更新状态显示
            elapsed = self._poll_count * self.POLL_INTERVAL // 1000
            self._status_label.setText(f"等待支付... ({elapsed}秒)")
            
        except Exception as e:
            payment_log(f"检查状态失败: {e}")
    
    def _on_payment_success(self):
        """支付成功"""
        self._stop_polling()
        self._status_label.setText("✅ 支付成功！")
        self._status_label.setStyleSheet("color: #52c41a; font-weight: bold;")

        payment_log("支付成功")

        # 使用自定义 QMessageBox 并设置置顶标志，避免被截图窗口覆盖
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("感谢大佬！🎉")
        msg_box.setText(
            "🎉 太感谢啦！您真是太棒了！\n\n"
            "终身 VIP 已解锁，所有高级功能随便用！\n"
            "您的支持让虎哥充满动力 ❤️"
        )
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        msg_box.exec()

        self.payment_success.emit()
        self.accept()
    
    def _on_close(self):
        """关闭对话框"""
        self._stop_polling()
        self.reject()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        self._stop_polling()
        super().closeEvent(event)
