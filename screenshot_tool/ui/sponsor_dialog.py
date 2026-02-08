"""
赞助对话框

Feature: afdian-payment-integration
Requirements: 5.2, 5.3, 5.4, 5.5
"""

import webbrowser
from io import BytesIO
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap, QImage

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def sponsor_log(message: str):
    """赞助对话框日志"""
    _debug_log(message, "SPONSOR")


class SponsorDialog(QDialog):
    """赞助对话框
    
    Requirements: 5.2, 5.3, 5.4, 5.5
    
    显示赞助二维码和链接，支持手动验证订单。
    
    Signals:
        sponsor_success: 赞助成功（订单验证通过）
    """
    
    sponsor_success = Signal()
    
    def __init__(
        self,
        sponsor_service=None,
        user_id: Optional[str] = None,
        parent=None
    ):
        """初始化赞助对话框
        
        Args:
            sponsor_service: 赞助服务实例
            user_id: 当前用户 ID
            parent: 父窗口
        """
        super().__init__(parent)
        self._sponsor_service = sponsor_service
        self._user_id = user_id
        self._sponsor_url = None
        self._setup_ui()
        self._generate_sponsor_url()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("赞助虎哥 - 虎哥截图")
        self.setFixedSize(420, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("❤️ 赞助虎哥")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 说明
        desc = QLabel(
            "感谢您对虎哥截图的支持！\n"
            "请作者喝杯咖啡（9.9元），即可解锁终身 VIP 权益。"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666; line-height: 1.6;")
        layout.addWidget(desc)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line1)
        
        # 二维码区域
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setMinimumSize(200, 200)
        self._qr_label.setStyleSheet("""
            QLabel {
                background-color: #fafafa;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        self._qr_label.setText("正在生成二维码...")
        layout.addWidget(self._qr_label, alignment=Qt.AlignCenter)
        
        # 提示
        tip = QLabel("使用微信或支付宝扫码赞助")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(tip)
        
        # 打开爱发电按钮
        self._open_btn = QPushButton("🔗 打开爱发电页面")
        self._open_btn.setMinimumHeight(40)
        self._open_btn.setStyleSheet("""
            QPushButton {
                background-color: #946ce6;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #a77ff0;
            }
        """)
        self._open_btn.clicked.connect(self._open_afdian)
        layout.addWidget(self._open_btn)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line2)
        
        # 手动验证区域
        verify_label = QLabel("已赞助？输入订单号验证：")
        verify_label.setStyleSheet("color: #666;")
        layout.addWidget(verify_label)
        
        verify_layout = QHBoxLayout()
        
        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("爱发电订单号")
        self._order_input.setMinimumHeight(38)
        verify_layout.addWidget(self._order_input, 1)
        
        self._verify_btn = QPushButton("验证")
        self._verify_btn.setMinimumHeight(38)
        self._verify_btn.setMinimumWidth(80)
        self._verify_btn.setStyleSheet("""
            QPushButton {
                background-color: #52c41a;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #73d13d;
            }
        """)
        self._verify_btn.clicked.connect(self._verify_order)
        verify_layout.addWidget(self._verify_btn)
        
        layout.addLayout(verify_layout)
        
        # VIP 权益说明
        benefits = QLabel(
            "🎁 赞助后可享受：\n"
            "• 无限次翻译 • 无限次网页转 Markdown\n"
            "• 录屏功能 • 公文格式化 • 更多高级功能"
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
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setMinimumHeight(38)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)
    
    def _generate_sponsor_url(self):
        """生成赞助链接和二维码"""
        if not self._sponsor_service or not self._user_id:
            self._qr_label.setText("请先登录")
            self._open_btn.setEnabled(False)
            return
        
        try:
            self._sponsor_url = self._sponsor_service.generate_sponsor_url(self._user_id)
            sponsor_log(f"生成赞助链接: {self._sponsor_url}")
            self._generate_qr_code(self._sponsor_url)
        except Exception as e:
            sponsor_log(f"生成赞助链接失败: {e}")
            self._qr_label.setText("生成链接失败")
    
    def _generate_qr_code(self, url: str):
        """生成二维码图片
        
        Args:
            url: 要编码的 URL
        """
        try:
            import qrcode
            from PIL import Image
            
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # 转换为 PIL Image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # PIL Image -> QPixmap
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            qimage = QImage()
            qimage.loadFromData(buffer.read())
            pixmap = QPixmap.fromImage(qimage)
            
            # 缩放到合适大小
            pixmap = pixmap.scaled(
                180, 180,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            self._qr_label.setPixmap(pixmap)
            sponsor_log("二维码生成成功")
            
        except ImportError:
            sponsor_log("qrcode 库未安装")
            self._qr_label.setText("请安装 qrcode 库\npip install qrcode[pil]")
        except Exception as e:
            sponsor_log(f"生成二维码失败: {e}")
            self._qr_label.setText("生成二维码失败")
    
    def _open_afdian(self):
        """打开爱发电页面"""
        if self._sponsor_url:
            sponsor_log(f"打开爱发电: {self._sponsor_url}")
            webbrowser.open(self._sponsor_url)
        else:
            QMessageBox.warning(self, "温馨提示 💡", "赞助链接还在路上，稍等一下～ 🚗")
    
    def _verify_order(self):
        """验证订单"""
        order_id = self._order_input.text().strip()
        
        if not order_id:
            QMessageBox.warning(self, "温馨提示 💡", "订单号空空的，填一个呗～")
            return
        
        if not self._sponsor_service:
            QMessageBox.warning(self, "哎呀 😅", "服务还在打盹，稍后再试～")
            return
        
        self._verify_btn.setEnabled(False)
        self._verify_btn.setText("验证中...")
        
        try:
            result = self._sponsor_service.verify_order(order_id)
            
            if result.success:
                sponsor_log(f"订单验证成功: {order_id}")
                QMessageBox.information(
                    self, "验证成功！🎉",
                    "🎉 验证成功！感谢大佬支持！\nVIP 权益已解锁，尽情享用吧～"
                )
                self.sponsor_success.emit()
                self.accept()
            else:
                sponsor_log(f"订单验证失败: {result.message}")
                QMessageBox.warning(self, "验证失败 🤔", result.message)
        except Exception as e:
            sponsor_log(f"订单验证异常: {e}")
            QMessageBox.critical(self, "哎呀 😅", f"验证翻车了：{e}")
        finally:
            self._verify_btn.setEnabled(True)
            self._verify_btn.setText("验证")
