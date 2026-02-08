"""
认证服务 - 封装 Supabase Auth

提供用户注册、登录、登出等功能。

Feature: subscription-system
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import os
import json
import time
import ssl
import socket
from typing import Optional, Callable, TypeVar
from supabase import create_client, Client, AuthApiError

from .models import User, AuthResult

T = TypeVar('T')

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def auth_log(message: str):
    """认证服务日志"""
    _debug_log(message, "AUTH")


def _is_network_error(e: Exception) -> bool:
    """判断是否为网络相关错误（可重试）"""
    error_str = str(e).lower()
    network_keywords = [
        "ssl", "handshake", "timed out", "timeout",
        "connection", "network", "unreachable",
        "reset by peer", "broken pipe", "eof occurred",
    ]
    return (
        isinstance(e, (ssl.SSLError, socket.timeout, ConnectionError, TimeoutError))
        or any(kw in error_str for kw in network_keywords)
    )


def _retry_on_network_error(
    func: Callable[[], T],
    max_retries: int = 2,
    retry_delay: float = 0.5,
    operation_name: str = "操作"
) -> T:
    """网络错误重试装饰器
    
    Args:
        func: 要执行的函数
        max_retries: 最大重试次数（默认 2 次，总共最多 3 次尝试）
        retry_delay: 重试间隔（秒，默认 0.5 秒）
        operation_name: 操作名称（用于日志）
        
    Returns:
        函数执行结果
        
    Raises:
        最后一次尝试的异常
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if _is_network_error(e) and attempt < max_retries - 1:
                auth_log(f"{operation_name}网络错误，第 {attempt + 1} 次重试: {e}")
                time.sleep(retry_delay * (attempt + 1))  # 递增延迟
            else:
                raise
    raise last_error  # type: ignore


class AuthService:
    """认证服务 - 封装 Supabase Auth
    
    提供用户注册、登录、登出等功能。
    支持会话持久化，重启应用后自动恢复登录状态。
    
    Attributes:
        _client: Supabase 客户端
        _current_user: 当前登录用户
        _access_token: 当前访问令牌
        _session_file: 会话文件路径
    """
    
    SESSION_FILE_NAME = "session.json"
    
    def __init__(self, client_or_url, supabase_key: Optional[str] = None, cache_dir: Optional[str] = None, auto_restore: bool = True):
        """初始化认证服务
        
        支持两种初始化方式：
        1. 传入已创建的 Client 对象
        2. 传入 URL 和 Key 创建新客户端
        
        Args:
            client_or_url: Supabase Client 对象或项目 URL
            supabase_key: Supabase anon/publishable key（仅当第一个参数是 URL 时需要）
            cache_dir: 缓存目录，用于保存会话文件
            auto_restore: 是否自动恢复会话（默认 True，设为 False 可延迟到后台执行）
        """
        if isinstance(client_or_url, Client):
            self._client = client_or_url
        else:
            if not supabase_key:
                raise ValueError("使用 URL 初始化时必须提供 supabase_key")
            self._client = create_client(client_or_url, supabase_key)
        self._current_user: Optional[User] = None
        self._access_token: Optional[str] = None
        
        # 设置会话文件路径
        if cache_dir:
            self._cache_dir = cache_dir
        else:
            # 使用统一的用户数据目录
            from screenshot_tool.core.config_manager import get_user_data_dir
            self._cache_dir = get_user_data_dir()
        self._session_file = os.path.join(self._cache_dir, self.SESSION_FILE_NAME)
        
        # 尝试恢复会话（可选）
        if auto_restore:
            self._restore_session()
    
    def restore_session(self) -> bool:
        """公共方法：恢复会话
        
        供外部调用，用于后台恢复会话。
        
        Returns:
            bool: 是否成功恢复
        """
        return self._restore_session()
    
    @property
    def client(self) -> Client:
        """获取 Supabase 客户端"""
        return self._client
    
    def register(self, email: str, password: str, email_redirect_to: str = "") -> AuthResult:
        """注册新用户
        
        Requirements: 1.1
        
        注册流程：
        1. 调用 sign_up 创建用户（邮箱未验证状态）
        2. Supabase 发送确认链接邮件（不是验证码）
        3. 用户点击邮件中的链接完成验证
        4. 验证成功后用户回到应用登录
        
        Args:
            email: 用户邮箱
            password: 密码
            email_redirect_to: 邮件确认后的重定向 URL（可选）
            
        Returns:
            AuthResult: 注册结果
        """
        try:
            options = {}
            if email_redirect_to:
                options["email_redirect_to"] = email_redirect_to
            
            sign_up_params = {
                "email": email,
                "password": password,
            }
            if options:
                sign_up_params["options"] = options
            
            def do_sign_up():
                return self._client.auth.sign_up(sign_up_params)
            
            response = _retry_on_network_error(do_sign_up, operation_name="注册")
            
            if response.user:
                user = User(
                    id=response.user.id,
                    email=response.user.email or email,
                )
                # 注册成功但邮箱未验证，不保存会话
                # 用户需要点击邮件中的确认链接完成验证
                auth_log(f"注册成功，已发送确认邮件: {email}")
                return AuthResult.ok(user, "")
            else:
                return AuthResult.fail("注册失败：未知错误")
                
        except AuthApiError as e:
            auth_log(f"注册失败: {e.message}")
            return AuthResult.fail(self._translate_error(e.message))
        except Exception as e:
            auth_log(f"注册异常: {e}")
            return AuthResult.fail(self._translate_network_error(e))
    
    def verify_signup_otp(self, email: str, otp: str) -> tuple[bool, str]:
        """验证注册邮箱 OTP
        
        Args:
            email: 用户邮箱
            otp: 验证码
            
        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            response = self._client.auth.verify_otp({
                "email": email,
                "token": otp,
                "type": "email",  # 注册验证类型
            })
            
            if response.user and response.session:
                auth_log(f"邮箱验证成功: {email}")
                # 验证成功后自动登录
                self._current_user = User(
                    id=response.user.id,
                    email=response.user.email or email,
                )
                self._access_token = response.session.access_token
                self._save_session(response.session)
                return True, ""
            else:
                return False, "验证失败"
                
        except AuthApiError as e:
            auth_log(f"验证 OTP 失败: {e.message}")
            return False, self._translate_error(e.message)
        except Exception as e:
            auth_log(f"验证 OTP 异常: {e}")
            return False, str(e)
    
    def resend_signup_otp(self, email: str) -> tuple[bool, str]:
        """重新发送注册验证码
        
        Args:
            email: 用户邮箱
            
        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            # 使用 resend 方法重新发送验证邮件
            self._client.auth.resend({
                "type": "signup",
                "email": email,
            })
            auth_log(f"重新发送验证码: {email}")
            return True, ""
        except AuthApiError as e:
            auth_log(f"重新发送验证码失败: {e.message}")
            return False, self._translate_error(e.message)
        except Exception as e:
            auth_log(f"重新发送验证码异常: {e}")
            return False, str(e)
    
    def login(self, email: str, password: str, machine_id: str = "") -> AuthResult:
        """登录
        
        Requirements: 1.2, 1.3, 1.4
        
        Args:
            email: 用户邮箱
            password: 密码
            machine_id: 设备 ID（用于记录设备信息）
            
        Returns:
            AuthResult: 登录结果
        """
        try:
            def do_login():
                return self._client.auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
            
            response = _retry_on_network_error(do_login, operation_name="登录")
            
            if response.user and response.session:
                user = User(
                    id=response.user.id,
                    email=response.user.email or email,
                )
                self._current_user = user
                self._access_token = response.session.access_token
                
                # 保存会话到本地
                self._save_session(response.session)
                
                # 记录设备信息（如果提供了 machine_id）
                if machine_id:
                    self._record_device(user.id, machine_id)
                
                return AuthResult.ok(user, self._access_token)
            else:
                return AuthResult.fail("登录失败：未知错误")
                
        except AuthApiError as e:
            auth_log(f"登录失败: {e.message}")
            return AuthResult.fail(self._translate_error(e.message))
        except Exception as e:
            auth_log(f"登录异常: {e}")
            return AuthResult.fail(self._translate_network_error(e))
    
    def logout(self) -> bool:
        """登出
        
        Returns:
            bool: 是否成功
        """
        try:
            self._client.auth.sign_out()
            self._current_user = None
            self._access_token = None
            # 删除本地会话文件
            self._clear_session()
            return True
        except Exception as e:
            auth_log(f"登出异常: {e}")
            return False
    
    def get_current_user(self) -> Optional[User]:
        """获取当前登录用户
        
        Returns:
            User: 当前用户，未登录返回 None
        """
        if self._current_user:
            return self._current_user
        
        try:
            response = self._client.auth.get_user()
            if response and response.user:
                self._current_user = User(
                    id=response.user.id,
                    email=response.user.email or "",
                )
                return self._current_user
        except Exception:
            pass
        
        return None
    
    def get_access_token(self) -> Optional[str]:
        """获取当前访问令牌
        
        Returns:
            str: 访问令牌，未登录返回 None
        """
        if self._access_token:
            return self._access_token
        
        try:
            session = self._client.auth.get_session()
            if session:
                self._access_token = session.access_token
                return self._access_token
        except Exception:
            pass
        
        return None
    
    def reset_password(self, email: str) -> bool:
        """发送密码重置邮件（旧方式，发送链接）
        
        Requirements: 1.5
        
        Args:
            email: 用户邮箱
            
        Returns:
            bool: 是否成功发送
        """
        try:
            self._client.auth.reset_password_email(email)
            return True
        except AuthApiError as e:
            auth_log(f"密码重置失败: {e.message}")
            return False
        except Exception as e:
            auth_log(f"密码重置异常: {e}")
            return False
    
    def send_password_reset_otp(self, email: str) -> tuple[bool, str]:
        """发送密码重置验证码（OTP 方式，适合桌面应用）
        
        Requirements: 1.5
        
        Args:
            email: 用户邮箱
            
        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            # 使用 signInWithOtp 发送验证码，type=recovery
            self._client.auth.sign_in_with_otp({
                "email": email,
                "options": {
                    "should_create_user": False,  # 不创建新用户
                }
            })
            auth_log(f"密码重置验证码已发送: {email}")
            return True, ""
        except AuthApiError as e:
            auth_log(f"发送验证码失败: {e.message}")
            return False, self._translate_error(e.message)
        except Exception as e:
            auth_log(f"发送验证码异常: {e}")
            return False, str(e)
    
    def verify_otp_and_reset_password(self, email: str, otp: str, new_password: str) -> tuple[bool, str]:
        """验证 OTP 并重置密码
        
        Args:
            email: 用户邮箱
            otp: 验证码
            new_password: 新密码
            
        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            # 先用 OTP 验证登录（Magic Link 类型）
            response = self._client.auth.verify_otp({
                "email": email,
                "token": otp,
                "type": "magiclink",  # Magic Link 的 OTP 类型
            })
            
            if not response.user or not response.session:
                return False, "验证码无效或已过期"
            
            # 验证成功后更新密码
            update_response = self._client.auth.update_user({
                "password": new_password
            })
            
            if update_response.user:
                auth_log(f"密码重置成功: {email}")
                # 登出，让用户用新密码登录
                self._client.auth.sign_out()
                return True, ""
            else:
                return False, "密码更新失败"
                
        except AuthApiError as e:
            auth_log(f"验证 OTP 失败: {e.message}")
            return False, self._translate_error(e.message)
        except Exception as e:
            auth_log(f"重置密码异常: {e}")
            return False, str(e)
    
    def is_logged_in(self) -> bool:
        """检查是否已登录
        
        Returns:
            bool: 是否已登录
        """
        return self.get_current_user() is not None
    
    def refresh_session(self) -> bool:
        """刷新会话
        
        Returns:
            bool: 是否成功
        """
        try:
            response = self._client.auth.refresh_session()
            if response and response.session:
                self._access_token = response.session.access_token
                return True
        except Exception as e:
            auth_log(f"刷新会话失败: {e}")
        return False
    
    def _record_device(self, user_id: str, machine_id: str) -> None:
        """记录设备信息
        
        Requirements: 1.3
        
        Args:
            user_id: 用户 ID
            machine_id: 设备 ID
        """
        try:
            import platform
            from screenshot_tool import __version__
            
            # 使用 upsert 更新或插入设备记录
            self._client.table("devices").upsert({
                "user_id": user_id,
                "machine_id": machine_id,
                "device_name": platform.node(),
                "os_version": f"{platform.system()} {platform.release()}",
                "app_version": __version__,
                "is_active": True,
            }, on_conflict="user_id,machine_id").execute()
        except Exception as e:
            # 设备记录失败不影响登录
            auth_log(f"记录设备信息失败: {e}")
    
    def _translate_error(self, message: str) -> str:
        """翻译错误信息为中文
        
        Args:
            message: 英文错误信息
            
        Returns:
            str: 中文错误信息
        """
        translations = {
            "Invalid login credentials": "邮箱或密码不对，再想想？🤔",
            "Email not confirmed": "邮箱还没验证呢，去收件箱看看？📬",
            "User already registered": "这个邮箱已经有主了，换一个？",
            "Password should be at least 6 characters": "密码太短啦，至少 6 位才安全 🔐",
            "Unable to validate email address: invalid format": "邮箱格式有点奇怪，再检查一下？",
            "Email rate limit exceeded": "太快了太快了，歇一会儿再试～ 🏃",
            "For security purposes, you can only request this once every 60 seconds": "冷却中...60 秒后再来～ ⏰",
            "Token has expired or is invalid": "验证码过期了，重新发一个？",
            "OTP has expired": "验证码过期啦，再发一个？",
            "Invalid OTP": "验证码不对，再看看？",
            "Signups not allowed for otp": "这个邮箱还没注册呢，先去注册？",
            "New password should be different from the old password": "新密码不能和旧密码一样哦～",
        }
        
        for en, zh in translations.items():
            if en.lower() in message.lower():
                return zh
        
        return message
    
    def _translate_network_error(self, e: Exception) -> str:
        """翻译网络错误为友好的中文提示
        
        Args:
            e: 异常对象
            
        Returns:
            str: 中文错误信息
        """
        error_str = str(e).lower()
        
        if "handshake" in error_str and "timed out" in error_str:
            return "网络开小差了，检查一下再试？🌐"
        if "ssl" in error_str or "certificate" in error_str:
            return "安全连接失败，网络设置有点问题？🔒"
        if "timeout" in error_str or "timed out" in error_str:
            return "等太久了，网络是不是睡着了？💤"
        if "connection" in error_str:
            return "服务器联系不上，网络通吗？📡"
        if "unreachable" in error_str:
            return "服务器在摸鱼，稍后再来找它～ 🐟"
        
        return f"翻车了：{str(e)}"
    
    # ========== 会话持久化 ==========
    
    def _save_session(self, session) -> None:
        """保存会话到本地文件
        
        Args:
            session: Supabase Session 对象
        """
        try:
            # 确保目录存在
            os.makedirs(self._cache_dir, exist_ok=True)
            
            session_data = {
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "expires_at": session.expires_at,
            }
            
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f)
            
            auth_log("会话已保存到本地")
        except Exception as e:
            auth_log(f"保存会话失败: {e}")
    
    def _restore_session(self) -> bool:
        """从本地文件恢复会话
        
        Returns:
            bool: 是否成功恢复
        """
        if not os.path.exists(self._session_file):
            return False
        
        try:
            with open(self._session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            
            access_token = session_data.get("access_token")
            refresh_token = session_data.get("refresh_token")
            
            if not access_token or not refresh_token:
                auth_log("会话文件无效，删除")
                self._clear_session()
                return False
            
            # 使用 refresh_token 恢复会话
            response = self._client.auth.set_session(access_token, refresh_token)
            
            if response and response.user:
                self._current_user = User(
                    id=response.user.id,
                    email=response.user.email or "",
                )
                self._access_token = response.session.access_token if response.session else access_token
                
                # 更新本地保存的会话（可能已刷新）
                if response.session:
                    self._save_session(response.session)
                
                auth_log(f"会话已恢复: {self._current_user.email}")
                return True
            else:
                auth_log("会话恢复失败（服务器返回空），删除本地会话")
                self._clear_session()
                return False
                
        except Exception as e:
            # 网络错误时不删除本地会话，保留给下次启动时重试
            # 只有明确的、不可恢复的认证失败才删除
            error_str = str(e).lower()
            
            # "Already Used" 是 refresh token 被重复使用（可能是网络重试导致）
            # 这种情况不应该删除会话，用户重新登录后会获得新 token
            is_already_used = "already used" in error_str
            
            # 明确的、不可恢复的认证错误
            is_fatal_auth_error = any(kw in error_str for kw in [
                "expired", "revoked", "unauthorized", "401",
                "refresh token not found",
                "session not found", "user not found", "jwt expired",
            ]) and not is_already_used
            
            if is_fatal_auth_error:
                auth_log(f"会话已失效: {e}，删除本地会话")
                self._clear_session()
            elif is_already_used:
                # Already Used 不删除会话，提示用户重新登录即可
                auth_log(f"Refresh Token 已被使用: {e}，保留会话文件（需重新登录）")
            else:
                # 网络错误，保留会话文件
                auth_log(f"恢复会话网络异常: {e}，保留本地会话供下次重试")
            
            return False
    
    def _clear_session(self) -> None:
        """清除本地会话文件"""
        try:
            if os.path.exists(self._session_file):
                os.remove(self._session_file)
                auth_log("本地会话已清除")
        except Exception as e:
            auth_log(f"清除会话文件失败: {e}")
