"""
支付服务 - 虎皮椒支付集成

负责生成支付链接、验证签名、查询订单等功能。
"""

import hashlib
import time
import secrets
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import requests

from .auth_service import AuthService


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"  # WP - 待支付
    PAID = "paid"        # OD - 已支付
    CANCELLED = "cancelled"  # CD - 已取消
    REFUNDED = "refunded"


@dataclass
class Order:
    """订单信息"""
    id: str
    user_id: str
    trade_order_id: str  # 商户订单号
    open_order_id: Optional[str] = None  # 虎皮椒内部订单号
    amount: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: Optional[str] = None


@dataclass
class PaymentResult:
    """支付请求结果"""
    success: bool
    message: str
    url: Optional[str] = None  # 支付链接
    url_qrcode: Optional[str] = None  # 二维码图片链接
    open_order_id: Optional[str] = None  # 虎皮椒订单号


@dataclass
class OrderQueryResult:
    """订单查询结果"""
    success: bool
    message: str
    status: Optional[str] = None  # OD/WP/CD
    order: Optional[Order] = None


class PaymentService:
    """支付服务 - 虎皮椒支付集成
    
    虎皮椒 API 文档: https://www.xunhupay.com/doc/api/pay.html
    """
    
    # 虎皮椒配置（从环境变量或配置文件读取更安全）
    APPID = "201906176273"
    # 注意：密钥不应硬编码，应从环境变量读取
    
    # API 地址
    API_URL = "https://api.xunhupay.com/payment/do.html"
    QUERY_URL = "https://api.xunhupay.com/payment/query.html"
    
    def __init__(self, auth_service: AuthService, app_secret: Optional[str] = None):
        """初始化支付服务
        
        Args:
            auth_service: 认证服务实例
            app_secret: 虎皮椒密钥（建议从环境变量传入）
        """
        self._auth = auth_service
        self._secret = app_secret
        
        # 从环境变量读取配置
        import os
        self._notify_url = os.environ.get(
            "XUNHU_NOTIFY_URL",
            "https://ttgtdiybtmvdddxanumk.supabase.co/functions/v1/xunhu-webhook"
        )
        self._return_url = os.environ.get(
            "XUNHU_RETURN_URL",
            "https://hudawang.cn/payment-success"
        )
        self._product_title = os.environ.get("XUNHU_PRODUCT_TITLE", "虎哥截图终身VIP")
        self._product_price = os.environ.get("XUNHU_PRODUCT_PRICE", "9.9")
    
    def generate_hash(self, params: dict) -> str:
        """生成虎皮椒签名
        
        签名规则：
        1. 将参数按 key 的 ASCII 码排序
        2. 拼接成 key1=value1&key2=value2 格式
        3. 末尾拼接 APPSECRET
        4. MD5 加密
        
        Args:
            params: 请求参数（不含 hash）
            
        Returns:
            MD5 签名字符串
        """
        if not self._secret:
            raise ValueError("支付密钥未配置")
        
        # 过滤空值，排除 hash 字段
        filtered = {
            k: str(v) for k, v in params.items() 
            if v is not None and v != '' and k != 'hash'
        }
        
        # 按 key 排序
        sorted_keys = sorted(filtered.keys())
        
        # 拼接字符串
        sign_str = '&'.join(f"{k}={filtered[k]}" for k in sorted_keys)
        sign_str += self._secret
        
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def verify_hash(self, params: dict, received_hash: str) -> bool:
        """验证回调签名
        
        Args:
            params: 回调参数（不含 hash）
            received_hash: 收到的签名
            
        Returns:
            签名是否有效
        """
        calculated = self.generate_hash(params)
        return calculated.lower() == received_hash.lower()
    
    def create_trade_order_id(self, user_id: str) -> str:
        """创建商户订单号
        
        格式: {user_id前8位}_{timestamp}_{随机数}
        确保唯一性，且包含用户信息便于追踪
        
        Args:
            user_id: Supabase 用户 ID
            
        Returns:
            商户订单号（最长32位）
        """
        # 取 user_id 前8位
        user_prefix = user_id.replace('-', '')[:8]
        timestamp = int(time.time())
        random_suffix = secrets.token_hex(4)  # 8位随机字符
        
        return f"{user_prefix}_{timestamp}_{random_suffix}"
    
    def parse_trade_order_id(self, trade_order_id: str) -> Optional[str]:
        """从订单号解析用户 ID 前缀
        
        Args:
            trade_order_id: 商户订单号
            
        Returns:
            用户 ID 前缀（8位）或 None
        """
        if not trade_order_id:
            return None
        
        parts = trade_order_id.split('_')
        if len(parts) >= 1:
            return parts[0]
        return None
    
    def create_payment(self, user_id: str, attach: Optional[str] = None) -> PaymentResult:
        """创建支付订单
        
        调用虎皮椒 API 创建支付订单，获取支付链接。
        
        Args:
            user_id: Supabase 用户 ID
            attach: 附加信息（回调时原样返回）
            
        Returns:
            PaymentResult: 包含支付链接的结果
        """
        if not self._secret:
            return PaymentResult(
                success=False,
                message="支付密钥未配置"
            )
        
        trade_order_id = self.create_trade_order_id(user_id)
        timestamp = int(time.time())
        nonce_str = secrets.token_hex(16)
        
        # 构建请求参数
        params = {
            "version": "1.1",
            "appid": self.APPID,
            "trade_order_id": trade_order_id,
            "total_fee": self._product_price,
            "title": self._product_title,
            "time": str(timestamp),
            "notify_url": self._notify_url,
            "return_url": self._return_url,
            "nonce_str": nonce_str,
        }
        
        # 附加用户 ID 信息，回调时用于关联用户
        if attach:
            params["attach"] = attach
        else:
            params["attach"] = user_id
        
        # 生成签名
        params["hash"] = self.generate_hash(params)
        
        try:
            response = requests.post(
                self.API_URL,
                data=params,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("errcode") == 0:
                return PaymentResult(
                    success=True,
                    message="订单创建成功",
                    url=result.get("url"),
                    url_qrcode=result.get("url_qrcode"),
                    open_order_id=result.get("openid") or result.get("open_order_id"),
                )
            else:
                return PaymentResult(
                    success=False,
                    message=result.get("errmsg", "创建订单失败")
                )
                
        except requests.RequestException as e:
            return PaymentResult(
                success=False,
                message=f"网络错误: {str(e)}"
            )
        except Exception as e:
            return PaymentResult(
                success=False,
                message=f"创建订单失败: {str(e)}"
            )
    
    def query_order(self, trade_order_id: Optional[str] = None, 
                    open_order_id: Optional[str] = None) -> OrderQueryResult:
        """查询订单状态
        
        Args:
            trade_order_id: 商户订单号（二选一）
            open_order_id: 虎皮椒订单号（二选一）
            
        Returns:
            OrderQueryResult: 订单查询结果
        """
        if not self._secret:
            return OrderQueryResult(
                success=False,
                message="支付密钥未配置"
            )
        
        if not trade_order_id and not open_order_id:
            return OrderQueryResult(
                success=False,
                message="请提供订单号"
            )
        
        timestamp = int(time.time())
        nonce_str = secrets.token_hex(16)
        
        params = {
            "appid": self.APPID,
            "time": str(timestamp),
            "nonce_str": nonce_str,
        }
        
        if trade_order_id:
            params["out_trade_order"] = trade_order_id
        else:
            params["open_order_id"] = open_order_id
        
        params["hash"] = self.generate_hash(params)
        
        try:
            response = requests.post(
                self.QUERY_URL,
                data=params,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("errcode") == 0:
                data = result.get("data", {})
                status = data.get("status", "WP")
                
                # 映射状态
                status_map = {
                    "OD": OrderStatus.PAID,
                    "WP": OrderStatus.PENDING,
                    "CD": OrderStatus.CANCELLED,
                }
                
                order = Order(
                    id=data.get("open_order_id", ""),
                    user_id="",  # 需要从 attach 解析
                    trade_order_id=trade_order_id or "",
                    open_order_id=data.get("open_order_id"),
                    status=status_map.get(status, OrderStatus.PENDING),
                )
                
                return OrderQueryResult(
                    success=True,
                    message="查询成功",
                    status=status,
                    order=order,
                )
            else:
                return OrderQueryResult(
                    success=False,
                    message=result.get("errmsg", "查询失败")
                )
                
        except Exception as e:
            return OrderQueryResult(
                success=False,
                message=f"查询失败: {str(e)}"
            )
    
    def get_current_user_id(self) -> Optional[str]:
        """获取当前登录用户的 ID"""
        user = self._auth.get_current_user()
        return user.id if user else None
    
    def is_logged_in(self) -> bool:
        """检查用户是否已登录"""
        return self._auth.get_current_user() is not None
