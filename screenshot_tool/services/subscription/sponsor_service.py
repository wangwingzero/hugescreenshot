"""
赞助服务 - 管理爱发电赞助集成

负责生成赞助链接、验证订单、查询订单等功能。
"""

import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import requests

from .auth_service import AuthService


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"


@dataclass
class Order:
    """订单信息"""
    id: str
    user_id: str
    afdian_order_id: str
    amount: float
    status: OrderStatus
    afdian_user_id: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class OrderVerifyResult:
    """订单验证结果"""
    success: bool
    message: str
    order: Optional[Order] = None


class SponsorService:
    """赞助服务 - 管理爱发电赞助集成"""
    
    # 爱发电配置
    AFDIAN_USER_ID = "d42a69746e7d11ef883552540025c377"
    PLAN_ID = "41124a30ee1a11f0bcab52540025c377"
    SKU_ID = "411b67aaee1a11f0b82752540025c377"
    
    # 爱发电 API 地址
    AFDIAN_API_URL = "https://afdian.com/api/open"
    AFDIAN_ORDER_URL = "https://afdian.com/order/create"
    
    def __init__(self, auth_service: AuthService, afdian_token: Optional[str] = None):
        """初始化赞助服务
        
        Args:
            auth_service: 认证服务实例
            afdian_token: 爱发电 API Token（可选，用于订单验证）
        """
        self._auth = auth_service
        self._token = afdian_token
    
    def create_custom_order_id(self, user_id: str) -> str:
        """创建自定义订单号
        
        格式: {user_id}:{timestamp}
        
        Args:
            user_id: Supabase 用户 ID
            
        Returns:
            自定义订单号
        """
        timestamp = int(time.time())
        return f"{user_id}:{timestamp}"
    
    def parse_custom_order_id(self, custom_order_id: str) -> tuple[Optional[str], Optional[int]]:
        """解析自定义订单号
        
        Args:
            custom_order_id: 自定义订单号
            
        Returns:
            (user_id, timestamp) 或 (None, None) 如果解析失败
        """
        if not custom_order_id:
            return None, None
        
        parts = custom_order_id.split(':')
        if len(parts) != 2:
            return None, None
        
        user_id = parts[0]
        try:
            timestamp = int(parts[1])
        except ValueError:
            return None, None
        
        return user_id, timestamp
    
    def generate_sponsor_url(self, user_id: str) -> str:
        """生成带用户ID的赞助链接
        
        Args:
            user_id: Supabase 用户 ID
            
        Returns:
            爱发电赞助页面 URL，包含 custom_order_id
        """
        custom_order_id = self.create_custom_order_id(user_id)
        
        # 构建 SKU 参数
        sku_data = [{"sku_id": self.SKU_ID, "count": 1}]
        sku_json = json.dumps(sku_data, separators=(',', ':'))
        
        # 构建 URL 参数
        params = {
            "product_type": "1",
            "plan_id": self.PLAN_ID,
            "sku": sku_json,
            "custom_order_id": custom_order_id,
        }
        
        # 生成完整 URL
        query_string = urllib.parse.urlencode(params)
        return f"{self.AFDIAN_ORDER_URL}?{query_string}"
    
    def generate_sign(self, params: dict, ts: int) -> str:
        """生成爱发电 API 签名
        
        签名规则: md5(token + "params" + json(params) + "ts" + ts + "user_id" + user_id)
        
        Args:
            params: 请求参数字典
            ts: 时间戳（秒）
            
        Returns:
            MD5 签名字符串
        """
        if not self._token:
            raise ValueError("API Token not configured")
        
        params_json = json.dumps(params, separators=(',', ':'))
        sign_str = f"{self._token}params{params_json}ts{ts}user_id{self.AFDIAN_USER_ID}"
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def query_orders(self, page: int = 1) -> list[dict]:
        """查询爱发电订单列表
        
        Args:
            page: 页码，从 1 开始
            
        Returns:
            订单列表
        """
        if not self._token:
            raise ValueError("API Token not configured")
        
        ts = int(time.time())
        params = {"page": page}
        sign = self.generate_sign(params, ts)
        
        data = {
            "user_id": self.AFDIAN_USER_ID,
            "params": json.dumps(params, separators=(',', ':')),
            "ts": ts,
            "sign": sign,
        }
        
        try:
            response = requests.post(
                f"{self.AFDIAN_API_URL}/query-order",
                json=data,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("ec") == 200:
                return result.get("data", {}).get("list", [])
            else:
                return []
        except Exception:
            return []
    
    def verify_order(self, afdian_order_id: str) -> OrderVerifyResult:
        """通过爱发电 API 验证订单
        
        用于用户手动验证支付
        
        Args:
            afdian_order_id: 爱发电订单号
            
        Returns:
            验证结果
        """
        if not self._token:
            return OrderVerifyResult(
                success=False,
                message="API Token 未配置，无法验证订单"
            )
        
        ts = int(time.time())
        params = {"out_trade_no": afdian_order_id}
        sign = self.generate_sign(params, ts)
        
        data = {
            "user_id": self.AFDIAN_USER_ID,
            "params": json.dumps(params, separators=(',', ':')),
            "ts": ts,
            "sign": sign,
        }
        
        try:
            response = requests.post(
                f"{self.AFDIAN_API_URL}/query-order",
                json=data,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("ec") != 200:
                return OrderVerifyResult(
                    success=False,
                    message=f"API 错误: {result.get('em', '未知错误')}"
                )
            
            orders = result.get("data", {}).get("list", [])
            if not orders:
                return OrderVerifyResult(
                    success=False,
                    message="订单不存在"
                )
            
            order_data = orders[0]
            if order_data.get("status") != 2:
                return OrderVerifyResult(
                    success=False,
                    message="订单未支付"
                )
            
            # 解析 custom_order_id 获取用户 ID
            custom_order_id = order_data.get("custom_order_id") or order_data.get("remark", "")
            user_id, _ = self.parse_custom_order_id(custom_order_id)
            
            order = Order(
                id="",
                user_id=user_id or "",
                afdian_order_id=order_data.get("out_trade_no", ""),
                amount=float(order_data.get("total_amount", 0)),
                status=OrderStatus.PAID,
                afdian_user_id=order_data.get("user_id"),
            )
            
            return OrderVerifyResult(
                success=True,
                message="订单验证成功",
                order=order
            )
            
        except requests.RequestException as e:
            return OrderVerifyResult(
                success=False,
                message=f"网络错误: {str(e)}"
            )
        except Exception as e:
            return OrderVerifyResult(
                success=False,
                message=f"验证失败: {str(e)}"
            )
    
    def get_current_user_id(self) -> Optional[str]:
        """获取当前登录用户的 ID
        
        Returns:
            用户 ID 或 None
        """
        user = self._auth.get_current_user()
        return user.id if user else None
    
    def is_logged_in(self) -> bool:
        """检查用户是否已登录
        
        Returns:
            是否已登录
        """
        return self._auth.get_current_user() is not None
