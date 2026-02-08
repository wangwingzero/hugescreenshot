"""
订阅系统管理器 - 统一管理订阅系统的所有组件

Feature: subscription-system
Requirements: 2.3, 7.1
"""

import os
from typing import Optional
from dataclasses import dataclass

from supabase import create_client, Client

from .models import Plan, SubscriptionInfo, User
from .auth_service import AuthService
from .license_service import LicenseService
from .usage_tracker import UsageTracker
from .feature_gate import FeatureGate, Feature, AccessResult
from .integration import init_feature_gate
from .payment_service import PaymentService

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def sub_log(message: str):
    """订阅系统日志"""
    _debug_log(message, "SUBSCRIPTION")


@dataclass
class SubscriptionState:
    """订阅状态"""
    is_logged_in: bool = False
    is_vip: bool = False
    user_email: Optional[str] = None
    user_id: Optional[str] = None
    plan: Plan = Plan.FREE
    error: Optional[str] = None


class SubscriptionManager:
    """订阅系统管理器
    
    统一管理认证、许可证、使用量追踪和功能门控。
    
    Requirements: 2.3, 7.1
    
    Usage:
        manager = SubscriptionManager(config_manager)
        manager.initialize()
        
        # 检查功能
        if manager.can_use(Feature.TRANSLATION):
            result = manager.use_feature(Feature.TRANSLATION)
    """
    
    _instance: Optional["SubscriptionManager"] = None
    
    @classmethod
    def instance(cls) -> Optional["SubscriptionManager"]:
        """获取单例实例"""
        return cls._instance
    
    def __init__(self, config_manager=None):
        """初始化订阅管理器
        
        Args:
            config_manager: 配置管理器实例
        """
        self._config_manager = config_manager
        self._client: Optional[Client] = None
        self._auth_service: Optional[AuthService] = None
        self._license_service: Optional[LicenseService] = None
        self._usage_tracker: Optional[UsageTracker] = None
        self._feature_gate: Optional[FeatureGate] = None
        self._payment_service: Optional[PaymentService] = None
        self._initialized = False
        self._state = SubscriptionState()
        
        # 设置单例
        SubscriptionManager._instance = self
    
    def initialize(self) -> bool:
        """初始化订阅系统
        
        优化：先从本地缓存加载状态（秒开），再后台静默验证。
        
        Returns:
            bool: 是否成功初始化
        """
        if self._initialized:
            return True
        
        try:
            # 获取 Supabase 配置
            supabase_url = self._get_supabase_url()
            supabase_key = self._get_supabase_key()
            
            if not supabase_url or not supabase_key:
                sub_log("Supabase 配置缺失，订阅系统未启用")
                self._state.error = "订阅系统未配置"
                self._initialized = True  # 标记为已初始化，避免 UI 无限重试
                return False
            
            # 1. 先从本地缓存加载状态（无网络请求，秒开）
            self._load_cached_state()
            
            # 2. 创建 Supabase 客户端
            # 注意：supabase-py 2.x 版本的 ClientOptions 不支持 postgrest_client_timeout
            # 超时控制由 httpx 默认配置（通常是 5 秒）
            self._client = create_client(supabase_url, supabase_key)
            
            # 3. 初始化认证服务（不自动恢复会话，稍后后台执行）
            cache_dir = self._get_cache_dir()
            self._auth_service = AuthService(
                self._client, 
                cache_dir=cache_dir,
                auto_restore=False  # 不自动恢复，稍后后台执行
            )
            
            # 4. 初始化支付服务（从环境变量获取密钥）
            xunhu_secret = os.environ.get("XUNHU_SECRET")
            self._payment_service = PaymentService(self._auth_service, app_secret=xunhu_secret)
            
            # 5. 初始化功能门控（使用缓存的状态）
            self._init_feature_gate()
            
            # 6. 标记为已初始化（UI 可以立即显示缓存的状态）
            self._initialized = True
            sub_log(f"订阅系统初始化完成（缓存状态: logged_in={self._state.is_logged_in}, vip={self._state.is_vip}）")
            
            # 7. 后台静默验证会话和许可证
            self._background_verify()
            
            return True
            
        except Exception as e:
            sub_log(f"订阅系统初始化失败: {e}")
            self._state.error = str(e)
            self._initialized = True  # 标记为已初始化，避免 UI 无限重试
            return False
    
    def _get_supabase_url(self) -> Optional[str]:
        """获取 Supabase URL"""
        # 优先从环境变量获取
        url = os.environ.get("SUPABASE_URL")
        if url:
            return url
        
        # 从配置获取
        if self._config_manager:
            return getattr(
                self._config_manager.config.subscription, 
                'supabase_url', 
                None
            )
        
        return None
    
    def _get_supabase_key(self) -> Optional[str]:
        """获取 Supabase Key"""
        # 优先从环境变量获取
        key = os.environ.get("SUPABASE_KEY")
        if key:
            return key
        
        # 从配置获取
        if self._config_manager:
            return getattr(
                self._config_manager.config.subscription, 
                'supabase_key', 
                None
            )
        
        return None
    
    def _get_cache_dir(self) -> str:
        """获取缓存目录
        
        使用统一的用户数据目录。
        
        Feature: unified-data-storage-path
        Requirements: 3.4
        """
        from screenshot_tool.core.config_manager import get_user_data_dir
        return get_user_data_dir()
    
    def _load_cached_state(self):
        """从本地缓存加载订阅状态（无网络请求）
        
        在初始化时调用，先用缓存快速显示状态。
        """
        try:
            import json
            import os
            from .models import LicenseCache
            
            cache_dir = self._get_cache_dir()
            license_cache_path = os.path.join(cache_dir, "license_cache.json")
            session_file_path = os.path.join(cache_dir, "session.json")
            
            # 检查是否有会话文件（表示之前登录过）
            if not os.path.exists(session_file_path):
                sub_log("无本地会话，跳过缓存加载")
                return
            
            # 读取会话文件获取基本信息
            with open(session_file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 检查会话文件是否有效
            if not session_data.get("access_token") or not session_data.get("refresh_token"):
                sub_log("会话文件无效，跳过缓存加载")
                return
            
            # 读取许可证缓存
            if os.path.exists(license_cache_path):
                with open(license_cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cache = LicenseCache.from_dict(cache_data)
                
                # 检查缓存是否在宽限期内（7天）
                if cache.is_in_grace_period(grace_days=7):
                    self._state.is_logged_in = True
                    self._state.user_id = cache.user_id
                    self._state.user_email = cache.user_email
                    self._state.is_vip = cache.subscription.is_vip
                    self._state.plan = cache.subscription.plan
                    
                    sub_log(f"从缓存加载状态: {cache.user_email}, VIP={cache.subscription.is_vip}")
                else:
                    sub_log("缓存已超过宽限期，需要重新验证")
            else:
                # 有会话但没有许可证缓存，标记为已登录但需要验证
                self._state.is_logged_in = True
                sub_log("有会话但无许可证缓存，等待后台验证")
                
        except Exception as e:
            sub_log(f"加载缓存状态失败: {e}")
    
    def _background_verify(self):
        """后台静默验证会话和许可证
        
        在单独线程中执行，不阻塞 UI。
        """
        import threading
        
        def verify_task():
            try:
                # 1. 恢复会话（网络请求）
                if self._auth_service:
                    self._auth_service.restore_session()
                
                # 2. 获取当前用户
                user = self._auth_service.get_current_user() if self._auth_service else None
                
                if user:
                    # 更新状态
                    self._state.is_logged_in = True
                    self._state.user_email = user.email
                    self._state.user_id = user.id
                    
                    # 3. 创建许可证服务并验证
                    cache_dir = self._get_cache_dir()
                    self._license_service = LicenseService(
                        self._client,
                        user.id,
                        cache_dir=cache_dir,
                        user_email=user.email
                    )
                    
                    # 验证许可证（会更新缓存）
                    self._license_service.verify(force=False)
                    self._state.is_vip = self._license_service.is_vip()
                    self._state.plan = Plan.LIFETIME_VIP if self._state.is_vip else Plan.FREE
                    
                    # 自动激活当前设备
                    self._activate_current_device()
                    
                    # 重新初始化功能门控
                    self._init_feature_gate()
                    
                    sub_log(f"后台验证完成: {user.email}, VIP={self._state.is_vip}")
                else:
                    # 会话恢复失败，但如果有缓存的 VIP 状态且在宽限期内，保持状态
                    if self._state.is_vip and self._state.is_logged_in:
                        sub_log("会话恢复失败，但在宽限期内，保持 VIP 状态")
                    elif self._state.is_logged_in:
                        # 有登录状态但不是 VIP，清除登录状态
                        self._state.is_logged_in = False
                        self._state.user_email = None
                        self._state.user_id = None
                        sub_log("会话恢复失败，清除登录状态")
                    else:
                        sub_log("会话恢复失败，无缓存状态")
                        
            except Exception as e:
                sub_log(f"后台验证失败: {e}")
                # 验证失败时，如果有缓存的 VIP 状态且在宽限期内，保持不变
                if self._state.is_vip:
                    sub_log("后台验证失败，但在宽限期内，保持 VIP 状态")
        
        # 启动后台线程
        thread = threading.Thread(target=verify_task, daemon=True)
        thread.start()
    
    def _init_feature_gate(self):
        """初始化功能门控"""
        # 初始化使用量追踪器（如果已登录）
        if self._state.is_logged_in and self._state.user_id:
            self._usage_tracker = UsageTracker(
                self._client,
                self._state.user_id,
                cache_dir=self._get_cache_dir()
            )
        
        # 创建功能门控
        # 如果 license_service 还未创建但有缓存的 VIP 状态，使用 is_vip_override
        is_vip_override = None
        if self._license_service is None and self._state.is_vip:
            is_vip_override = True
            sub_log("使用缓存的 VIP 状态初始化功能门控")
        
        self._feature_gate = FeatureGate(
            self._license_service,
            self._usage_tracker,
            is_vip_override=is_vip_override
        )
        
        # 初始化全局功能门控
        init_feature_gate(self._feature_gate)
    
    # ========== 公共 API ==========
    
    @property
    def state(self) -> SubscriptionState:
        """获取当前订阅状态"""
        return self._state
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    @property
    def is_logged_in(self) -> bool:
        """是否已登录"""
        return self._state.is_logged_in
    
    @property
    def is_vip(self) -> bool:
        """是否是 VIP"""
        return self._state.is_vip
    
    @property
    def auth_service(self) -> Optional[AuthService]:
        """获取认证服务"""
        return self._auth_service
    
    @property
    def license_service(self) -> Optional[LicenseService]:
        """获取许可证服务"""
        return self._license_service
    
    @property
    def feature_gate(self) -> Optional[FeatureGate]:
        """获取功能门控"""
        return self._feature_gate
    
    @property
    def client(self) -> Optional[Client]:
        """获取 Supabase 客户端"""
        return self._client
    
    @property
    def payment_service(self) -> Optional[PaymentService]:
        """获取支付服务"""
        return self._payment_service
    
    def get_payment_url(self) -> Optional[str]:
        """获取支付链接
        
        Returns:
            str: 支付链接，未登录或创建失败返回 None
        """
        if not self._payment_service or not self._state.user_id:
            return None
        
        result = self._payment_service.create_payment(self._state.user_id)
        return result.url if result.success else None
    
    def can_use(self, feature: Feature) -> bool:
        """检查是否可以使用功能
        
        Args:
            feature: 功能枚举
            
        Returns:
            bool: 是否可以使用
        """
        if not self._feature_gate:
            return True  # 未初始化时默认允许
        
        return self._feature_gate.can_use(feature)
    
    def use_feature(self, feature: Feature) -> AccessResult:
        """使用功能
        
        Args:
            feature: 功能枚举
            
        Returns:
            AccessResult: 访问结果
        """
        if not self._feature_gate:
            return AccessResult.allow()
        
        return self._feature_gate.use(feature)
    
    def check_access(self, feature: Feature) -> AccessResult:
        """检查功能访问权限
        
        Args:
            feature: 功能枚举
            
        Returns:
            AccessResult: 访问结果
        """
        if not self._feature_gate:
            return AccessResult.allow()
        
        return self._feature_gate.check_access(feature)
    
    def login(self, email: str, password: str) -> bool:
        """登录
        
        登录成功后立即重新初始化 FeatureGate，确保 VIP 状态生效。
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.1, 1.2, 1.3
        
        Args:
            email: 邮箱
            password: 密码
            
        Returns:
            bool: 是否成功
        """
        if not self._auth_service:
            return False
        
        try:
            result = self._auth_service.login(email, password)
            
            if result.success and result.user:
                self._state.is_logged_in = True
                self._state.user_email = result.user.email
                self._state.user_id = result.user.id
                
                # 创建或更新许可证服务
                cache_dir = self._get_cache_dir()
                self._license_service = LicenseService(
                    self._client,
                    result.user.id,
                    cache_dir=cache_dir,
                    user_email=result.user.email
                )
                
                # 验证许可证（强制刷新）
                self._license_service.verify(force=True)
                self._state.is_vip = self._license_service.is_vip()
                self._state.plan = Plan.LIFETIME_VIP if self._state.is_vip else Plan.FREE
                
                # 自动激活当前设备
                self._activate_current_device()
                
                # 重新初始化功能门控
                self._init_feature_gate()
                
                sub_log(f"登录成功: {email}, VIP: {self._state.is_vip}")
                return True
            
            return False
            
        except Exception as e:
            sub_log(f"登录失败: {e}")
            return False
    
    def _activate_current_device(self):
        """激活当前设备
        
        在登录或恢复会话后自动注册当前设备到数据库。
        
        Requirements: 3.2
        """
        if not self._client or not self._state.user_id:
            return
        
        try:
            from screenshot_tool.core.device_manager import DeviceManager
            
            device_manager = DeviceManager(self._client, self._state.user_id)
            
            # 检查是否可以激活（设备数量限制）
            can_activate, message = device_manager.can_activate(is_vip=self._state.is_vip)
            
            if can_activate:
                success, msg = device_manager.activate_device()
                if success:
                    sub_log(f"设备已激活: {msg}")
                else:
                    sub_log(f"设备激活失败: {msg}")
            else:
                sub_log(f"无法激活设备: {message}")
                
        except Exception as e:
            sub_log(f"激活设备异常: {e}")
    
    def logout(self):
        """登出
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.4
        """
        if self._auth_service:
            self._auth_service.logout()

        # 重置状态
        self._state = SubscriptionState()
        self._license_service = None  # 清除许可证服务
        self._usage_tracker = None

        # 重新初始化功能门控（无用户状态，撤销 VIP 权限）
        self._feature_gate = FeatureGate(None, None)
        init_feature_gate(self._feature_gate)

        sub_log("已登出，VIP 权限已撤销")
    
    def _sync_after_login(self, user_info: dict):
        """登录成功后同步状态
        
        当 LoginDialog 直接调用 AuthService.login() 成功后，
        需要同步 SubscriptionManager 的状态并创建 LicenseService。
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.1, 1.2, 1.3
        
        Args:
            user_info: 登录成功返回的用户信息 {"user_id": ..., "email": ...}
        """
        user_id = user_info.get("user_id")
        email = user_info.get("email")
        
        if not user_id:
            sub_log("_sync_after_login: 缺少 user_id")
            return
        
        try:
            # 更新状态
            self._state.is_logged_in = True
            self._state.user_email = email
            self._state.user_id = user_id
            
            # 创建许可证服务
            cache_dir = self._get_cache_dir()
            self._license_service = LicenseService(
                self._client,
                user_id,
                cache_dir=cache_dir,
                user_email=email
            )
            
            # 验证许可证（强制刷新）
            self._license_service.verify(force=True)
            self._state.is_vip = self._license_service.is_vip()
            self._state.plan = Plan.LIFETIME_VIP if self._state.is_vip else Plan.FREE
            
            # 自动激活当前设备
            self._activate_current_device()
            
            # 重新初始化功能门控
            self._init_feature_gate()
            
            sub_log(f"登录状态同步完成: {email}, VIP: {self._state.is_vip}")
            
        except Exception as e:
            sub_log(f"登录状态同步失败: {e}")

    def refresh_subscription(self) -> bool:
        """刷新订阅状态

        在支付成功后调用，强制从服务器获取最新订阅状态并更新本地状态。
        
        Feature: vip-realtime-unlock-modal-fix
        Requirements: 1.5

        Returns:
            bool: 是否刷新成功
        """
        if not self._license_service:
            return False

        try:
            # 强制从服务器验证
            self._license_service.verify(force=True)

            # 更新本地状态
            self._state.is_vip = self._license_service.is_vip()
            self._state.plan = Plan.LIFETIME_VIP if self._state.is_vip else Plan.FREE

            # 重新初始化功能门控以应用新的许可证状态
            self._init_feature_gate()

            sub_log(f"订阅状态已刷新: VIP={self._state.is_vip}")
            return True
        except Exception as e:
            sub_log(f"刷新订阅状态失败: {e}")
            return False
    
    def get_feature_status(self, feature: Feature) -> dict:
        """获取功能状态
        
        Args:
            feature: 功能枚举
            
        Returns:
            dict: 功能状态信息
        """
        if not self._feature_gate:
            return {
                "feature": feature.value,
                "allowed": True,
                "reason": "订阅系统未初始化",
            }
        
        return self._feature_gate.get_feature_status(feature)
    
    def sync_usage(self) -> bool:
        """同步使用量到服务器
        
        Returns:
            bool: 是否成功
        """
        if not self._usage_tracker:
            return False
        
        return self._usage_tracker.sync_to_server()
