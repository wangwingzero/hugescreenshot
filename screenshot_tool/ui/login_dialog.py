"""
登录/注册对话框

Feature: subscription-system
Requirements: 1.1, 1.2, 1.5
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QWidget, QMessageBox,
    QCheckBox, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont, QCloseEvent

from typing import Optional

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def login_log(message: str):
    """登录对话框日志"""
    _debug_log(message, "LOGIN")


class LoginWorker(QObject):
    """后台登录工作线程
    
    避免网络请求阻塞 UI 线程。
    """
    finished = Signal(bool, str, dict)  # (success, error, user_info)
    
    def __init__(self, auth_service, email: str, password: str):
        super().__init__()
        self._auth_service = auth_service
        self._email = email
        self._password = password
    
    def run(self):
        """执行登录"""
        try:
            result = self._auth_service.login(self._email, self._password)
            
            if result.success:
                user_info = {
                    "user_id": result.user.id if result.user else None,
                    "email": self._email,
                }
                self.finished.emit(True, "", user_info)
            else:
                self.finished.emit(False, result.error or "登录失败", {})
        except Exception as e:
            login_log(f"登录异常: {e}")
            self.finished.emit(False, str(e), {})


class LoginDialog(QDialog):
    """登录/注册对话框
    
    Requirements: 1.1, 1.2, 1.5
    
    Signals:
        login_success: 登录成功信号，携带用户信息
        register_success: 注册成功信号
    """
    
    login_success = Signal(dict)  # {user_id, email}
    register_success = Signal(str)  # email
    
    def __init__(self, auth_service=None, parent=None):
        """初始化登录对话框
        
        Args:
            auth_service: 认证服务实例
            parent: 父窗口
        """
        super().__init__(parent)
        self._auth_service = auth_service
        self._login_thread: Optional[QThread] = None
        self._login_worker: Optional[LoginWorker] = None
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("登录 - 虎哥截图")
        self.setFixedSize(400, 480)
        # 设置窗口标志：普通对话框 + 关闭按钮，移除帮助按钮
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        # 确保对话框是模态的
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("虎哥截图")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 副标题
        subtitle = QLabel("登录以解锁更多功能")
        subtitle.setStyleSheet("color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # 堆叠窗口（登录/注册/忘记密码）
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)
        
        # 登录页面 (index 0)
        self._login_page = self._create_login_page()
        self._stack.addWidget(self._login_page)
        
        # 注册页面 (index 1)
        self._register_page = self._create_register_page()
        self._stack.addWidget(self._register_page)
        
        # 忘记密码页面 (index 2)
        self._forgot_page = self._create_forgot_page()
        self._stack.addWidget(self._forgot_page)
        
        # 重置密码页面 (index 3)
        self._reset_page = self._create_reset_password_page()
        self._stack.addWidget(self._reset_page)
        
        # 保存待重置的邮箱
        self._reset_email = ""
        
        layout.addStretch()
    
    def _create_login_page(self) -> QWidget:
        """创建登录页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 邮箱输入
        self._login_email = QLineEdit()
        self._login_email.setPlaceholderText("邮箱地址")
        self._login_email.setMinimumHeight(40)
        layout.addWidget(self._login_email)
        
        # 密码输入
        self._login_password = QLineEdit()
        self._login_password.setPlaceholderText("密码")
        self._login_password.setEchoMode(QLineEdit.Password)
        self._login_password.setMinimumHeight(40)
        layout.addWidget(self._login_password)
        
        # 记住我
        self._remember_me = QCheckBox("记住我")
        layout.addWidget(self._remember_me)
        
        # 登录按钮
        self._login_btn = QPushButton("登录")
        self._login_btn.setMinimumHeight(45)
        self._login_btn.setStyleSheet("""
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
            QPushButton:pressed {
                background-color: #096dd9;
            }
            QPushButton:disabled {
                background-color: #d9d9d9;
            }
        """)
        layout.addWidget(self._login_btn)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line)
        
        # 底部链接
        links_layout = QHBoxLayout()
        
        self._to_register_btn = QPushButton("注册账号")
        self._to_register_btn.setFlat(True)
        self._to_register_btn.setStyleSheet("color: #1890ff;")
        links_layout.addWidget(self._to_register_btn)
        
        links_layout.addStretch()
        
        self._to_forgot_btn = QPushButton("忘记密码?")
        self._to_forgot_btn.setFlat(True)
        self._to_forgot_btn.setStyleSheet("color: #1890ff;")
        links_layout.addWidget(self._to_forgot_btn)
        
        layout.addLayout(links_layout)
        
        return page
    
    def _create_register_page(self) -> QWidget:
        """创建注册页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 邮箱输入
        self._register_email = QLineEdit()
        self._register_email.setPlaceholderText("邮箱地址")
        self._register_email.setMinimumHeight(40)
        layout.addWidget(self._register_email)
        
        # 密码输入
        self._register_password = QLineEdit()
        self._register_password.setPlaceholderText("密码（至少 6 位）")
        self._register_password.setEchoMode(QLineEdit.Password)
        self._register_password.setMinimumHeight(40)
        layout.addWidget(self._register_password)
        
        # 确认密码
        self._register_confirm = QLineEdit()
        self._register_confirm.setPlaceholderText("确认密码")
        self._register_confirm.setEchoMode(QLineEdit.Password)
        self._register_confirm.setMinimumHeight(40)
        layout.addWidget(self._register_confirm)
        
        # 注册按钮
        self._register_btn = QPushButton("注册")
        self._register_btn.setMinimumHeight(45)
        self._register_btn.setStyleSheet("""
            QPushButton {
                background-color: #52c41a;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #73d13d;
            }
            QPushButton:pressed {
                background-color: #389e0d;
            }
        """)
        layout.addWidget(self._register_btn)
        
        # 返回登录
        self._back_to_login_btn = QPushButton("← 返回登录")
        self._back_to_login_btn.setFlat(True)
        self._back_to_login_btn.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._back_to_login_btn)
        
        return page
    
    def _create_forgot_page(self) -> QWidget:
        """创建忘记密码页面（步骤1：发送验证码）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 说明
        info = QLabel("输入您的邮箱地址，我们将发送验证码到您的邮箱。")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)
        
        # 邮箱输入
        self._forgot_email = QLineEdit()
        self._forgot_email.setPlaceholderText("邮箱地址")
        self._forgot_email.setMinimumHeight(40)
        layout.addWidget(self._forgot_email)
        
        # 发送按钮
        self._send_reset_btn = QPushButton("发送验证码")
        self._send_reset_btn.setMinimumHeight(45)
        self._send_reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #faad14;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #ffc53d;
            }
            QPushButton:disabled {
                background-color: #d9d9d9;
            }
        """)
        layout.addWidget(self._send_reset_btn)
        
        # 返回登录
        self._back_to_login_btn2 = QPushButton("← 返回登录")
        self._back_to_login_btn2.setFlat(True)
        self._back_to_login_btn2.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._back_to_login_btn2)
        
        return page
    
    def _create_reset_password_page(self) -> QWidget:
        """创建重置密码页面（步骤2：输入验证码和新密码）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 说明
        self._reset_info = QLabel("验证码已发送到您的邮箱，请查收。")
        self._reset_info.setWordWrap(True)
        self._reset_info.setStyleSheet("color: #52c41a;")
        layout.addWidget(self._reset_info)
        
        # 验证码输入
        self._otp_input = QLineEdit()
        self._otp_input.setPlaceholderText("验证码")
        self._otp_input.setMinimumHeight(40)
        self._otp_input.setMaxLength(10)  # Supabase 验证码可能是 6-8 位
        layout.addWidget(self._otp_input)
        
        # 新密码
        self._new_password = QLineEdit()
        self._new_password.setPlaceholderText("新密码（至少 6 位）")
        self._new_password.setEchoMode(QLineEdit.Password)
        self._new_password.setMinimumHeight(40)
        layout.addWidget(self._new_password)
        
        # 确认新密码
        self._confirm_new_password = QLineEdit()
        self._confirm_new_password.setPlaceholderText("确认新密码")
        self._confirm_new_password.setEchoMode(QLineEdit.Password)
        self._confirm_new_password.setMinimumHeight(40)
        layout.addWidget(self._confirm_new_password)
        
        # 重置密码按钮
        self._reset_password_btn = QPushButton("重置密码")
        self._reset_password_btn.setMinimumHeight(45)
        self._reset_password_btn.setStyleSheet("""
            QPushButton {
                background-color: #52c41a;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #73d13d;
            }
            QPushButton:pressed {
                background-color: #389e0d;
            }
            QPushButton:disabled {
                background-color: #d9d9d9;
            }
        """)
        layout.addWidget(self._reset_password_btn)
        
        # 重新发送验证码
        self._resend_otp_btn = QPushButton("重新发送验证码")
        self._resend_otp_btn.setFlat(True)
        self._resend_otp_btn.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._resend_otp_btn)
        
        # 返回登录
        self._back_to_login_btn3 = QPushButton("← 返回登录")
        self._back_to_login_btn3.setFlat(True)
        self._back_to_login_btn3.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._back_to_login_btn3)
        
        return page
    
    def _connect_signals(self):
        """连接信号"""
        # 页面切换
        self._to_register_btn.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        self._to_forgot_btn.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        self._back_to_login_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        self._back_to_login_btn2.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        self._back_to_login_btn3.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        
        # 操作
        self._login_btn.clicked.connect(self._do_login)
        self._register_btn.clicked.connect(self._do_register)
        self._send_reset_btn.clicked.connect(self._do_send_otp)
        self._reset_password_btn.clicked.connect(self._do_reset_password)
        self._resend_otp_btn.clicked.connect(self._do_send_otp)
        
        # 回车登录
        self._login_password.returnPressed.connect(self._do_login)
        self._register_confirm.returnPressed.connect(self._do_register)
        self._confirm_new_password.returnPressed.connect(self._do_reset_password)
    
    def _do_login(self):
        """执行登录（后台线程，避免阻塞 UI）"""
        # 防止重复点击（线程正在运行时忽略）
        if self._login_thread is not None and self._login_thread.isRunning():
            return
        
        email = self._login_email.text().strip()
        password = self._login_password.text()
        
        if not email:
            QMessageBox.warning(self, "温馨提示 💡", "邮箱地址空空的，填一个呗～ 📧")
            return
        
        if not password:
            QMessageBox.warning(self, "温馨提示 💡", "密码还没填呢，来一个？🔑")
            return
        
        if self._auth_service is None:
            login_log("未配置认证服务")
            QMessageBox.warning(
                self, 
                "认证服务未就绪 😅", 
                "订阅系统正在初始化中，请稍等几秒后重试。\n\n"
                "如果问题持续存在，请检查网络连接或重启程序。"
            )
            return
        
        # 禁用按钮，显示加载状态
        self._login_btn.setEnabled(False)
        self._login_btn.setText("登录中...")
        
        # 创建后台线程执行登录
        self._login_thread = QThread()
        self._login_worker = LoginWorker(self._auth_service, email, password)
        self._login_worker.moveToThread(self._login_thread)
        
        # 连接信号
        self._login_thread.started.connect(self._login_worker.run)
        self._login_worker.finished.connect(self._on_login_finished)
        self._login_worker.finished.connect(self._login_thread.quit)
        self._login_worker.finished.connect(self._login_worker.deleteLater)
        self._login_thread.finished.connect(self._login_thread.deleteLater)
        self._login_thread.finished.connect(self._on_thread_finished)
        
        # 启动线程
        self._login_thread.start()
    
    def _on_thread_finished(self):
        """线程结束后清理引用"""
        self._login_thread = None
        self._login_worker = None
    
    def _on_login_finished(self, success: bool, error: str, user_info: dict):
        """登录完成回调（在主线程执行）"""
        # 恢复按钮状态
        self._login_btn.setEnabled(True)
        self._login_btn.setText("登录")
        
        if success:
            login_log(f"登录成功: {user_info.get('email')}")
            self.login_success.emit(user_info)
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败 😅", error or "出了点小状况，再试一次？")
    
    def _do_register(self):
        """执行注册"""
        email = self._register_email.text().strip()
        password = self._register_password.text()
        confirm = self._register_confirm.text()
        
        if not email:
            QMessageBox.warning(self, "温馨提示 💡", "邮箱地址空空的，填一个呗～ 📧")
            return
        
        if not password:
            QMessageBox.warning(self, "温馨提示 💡", "密码还没填呢，来一个？🔑")
            return
        
        if len(password) < 6:
            QMessageBox.warning(self, "温馨提示 💡", "密码太短啦，至少 6 位才安全 🔐")
            return
        
        if password != confirm:
            QMessageBox.warning(self, "温馨提示 💡", "两次密码对不上，再检查一下？🔍")
            return
        
        if self._auth_service is None:
            QMessageBox.warning(
                self, 
                "认证服务未就绪 😅", 
                "订阅系统正在初始化中，请稍等几秒后重试。"
            )
            return
        
        self._register_btn.setEnabled(False)
        self._register_btn.setText("注册中...")
        
        try:
            result = self._auth_service.register(
                email, 
                password,
                email_redirect_to="https://hudawang.cn/confirm.html"
            )
            
            if result.success:
                login_log(f"注册成功，已发送确认邮件: {email}")
                QMessageBox.information(
                    self, "注册成功！🎊",
                    f"确认邮件已飞往 {email} 📬\n\n"
                    "快去邮箱点击确认链接完成验证吧～\n"
                    "验证成功后就能登录啦！"
                )
                # 返回登录页面，自动填入邮箱
                self._stack.setCurrentIndex(0)
                self._login_email.setText(email)
                self._login_password.clear()
                self._login_password.setFocus()
                self.register_success.emit(email)
            else:
                QMessageBox.warning(self, "注册失败 😢", result.error or "出了点小状况，再试一次？")
        except Exception as e:
            login_log(f"注册异常: {e}")
            QMessageBox.critical(self, "哎呀 😅", f"注册翻车了：{e}")
        finally:
            self._register_btn.setEnabled(True)
            self._register_btn.setText("注册")
    
    def _do_send_otp(self):
        """发送验证码"""
        # 从忘记密码页面或重置页面获取邮箱
        if self._stack.currentIndex() == 2:  # 忘记密码页面
            email = self._forgot_email.text().strip()
            btn = self._send_reset_btn
        else:
            email = self._reset_email
            btn = self._resend_otp_btn
        
        if not email:
            QMessageBox.warning(self, "温馨提示 💡", "邮箱地址空空的，填一个呗～ 📧")
            return
        
        if self._auth_service is None:
            QMessageBox.warning(
                self, 
                "认证服务未就绪 😅", 
                "订阅系统正在初始化中，请稍等几秒后重试。"
            )
            return
        
        # 禁用按钮
        btn.setEnabled(False)
        original_text = btn.text()
        btn.setText("发送中...")
        
        try:
            success, error = self._auth_service.send_password_reset_otp(email)
            
            if success:
                login_log(f"验证码已发送: {email}")
                self._reset_email = email
                self._reset_info.setText(f"验证码已飞往 {email}，快去邮箱接收！📬")
                # 切换到重置密码页面 (index 3)
                self._stack.setCurrentIndex(3)
                # 清空输入框
                self._otp_input.clear()
                self._new_password.clear()
                self._confirm_new_password.clear()
                self._otp_input.setFocus()
            else:
                QMessageBox.warning(self, "发送失败 😢", error or "发送失败了...喝杯茶等等？🍵")
        except Exception as e:
            login_log(f"发送验证码异常: {e}")
            QMessageBox.critical(self, "哎呀 😅", f"发送失败了：{e}")
        finally:
            btn.setEnabled(True)
            btn.setText(original_text)
    
    def _do_reset_password(self):
        """执行密码重置"""
        otp = self._otp_input.text().strip()
        new_password = self._new_password.text()
        confirm_password = self._confirm_new_password.text()
        
        if not otp:
            QMessageBox.warning(self, "温馨提示 💡", "验证码还没填呢～")
            return
        
        if len(otp) < 6:
            QMessageBox.warning(self, "温馨提示 💡", "验证码格式不太对，再看看？🔍")
            return
        
        if not new_password:
            QMessageBox.warning(self, "温馨提示 💡", "新密码还没填呢，来一个？🔑")
            return
        
        if len(new_password) < 6:
            QMessageBox.warning(self, "温馨提示 💡", "密码太短啦，至少 6 位才安全 🔐")
            return
        
        if new_password != confirm_password:
            QMessageBox.warning(self, "温馨提示 💡", "两次密码对不上，再检查一下？🔍")
            return
        
        if self._auth_service is None:
            QMessageBox.warning(
                self, 
                "认证服务未就绪 😅", 
                "订阅系统正在初始化中，请稍等几秒后重试。"
            )
            return
        
        self._reset_password_btn.setEnabled(False)
        self._reset_password_btn.setText("重置中...")
        
        try:
            success, error = self._auth_service.verify_otp_and_reset_password(
                self._reset_email, otp, new_password
            )
            
            if success:
                login_log(f"密码重置成功: {self._reset_email}")
                QMessageBox.information(
                    self, "重置成功！🎉",
                    "密码已经换好啦！用新密码登录吧～"
                )
                # 返回登录页面，自动填入邮箱
                self._stack.setCurrentIndex(0)
                self._login_email.setText(self._reset_email)
                self._login_password.clear()
                self._login_password.setFocus()
            else:
                QMessageBox.warning(self, "重置失败 🤔", error or "验证码可能不对，再检查一下？")
        except Exception as e:
            login_log(f"密码重置异常: {e}")
            QMessageBox.critical(self, "哎呀 😅", f"重置翻车了：{e}")
        finally:
            self._reset_password_btn.setEnabled(True)
            self._reset_password_btn.setText("重置密码")
    
    def reject(self):
        """处理对话框关闭（点击 X 按钮或按 Esc）"""
        login_log("用户关闭登录对话框")
        super().reject()
    
    def closeEvent(self, event: QCloseEvent):
        """处理窗口关闭事件
        
        Args:
            event: 关闭事件
        """
        login_log("登录对话框关闭事件")
        # 如果登录线程正在运行，等待它结束
        if self._login_thread is not None and self._login_thread.isRunning():
            login_log("等待登录线程结束...")
            self._login_thread.quit()
            self._login_thread.wait(3000)  # 最多等待 3 秒
        event.accept()
