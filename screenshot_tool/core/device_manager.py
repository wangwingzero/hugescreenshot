"""
设备管理器 - 管理用户设备激活和限制

Feature: subscription-system
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import hashlib
import platform
import uuid
from dataclasses import dataclass
from typing import List, Optional

from supabase import Client

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def device_log(message: str):
    """设备管理日志"""
    _debug_log(message, "DEVICE")


@dataclass
class DeviceInfo:
    """设备信息"""
    id: str
    user_id: str
    machine_id: str
    device_name: str
    os_version: str
    app_version: str
    is_active: bool
    last_seen: Optional[str] = None
    created_at: Optional[str] = None


class DeviceManager:
    """设备管理器
    
    管理用户设备激活、停用和限制检查。
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    
    Attributes:
        _client: Supabase 客户端
        _user_id: 当前用户 ID
        _cached_machine_id: 缓存的设备指纹
    """
    
    # 设备限制配置
    FREE_DEVICE_LIMIT = 2
    VIP_DEVICE_LIMIT = 3
    
    def __init__(self, client: Client, user_id: str):
        """初始化设备管理器
        
        Args:
            client: Supabase 客户端
            user_id: 当前用户 ID
            
        Raises:
            ValueError: 如果 user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        
        self._client = client
        self._user_id = user_id.strip()
        self._cached_machine_id: Optional[str] = None
    
    def get_machine_id(self) -> str:
        """获取设备指纹
        
        Requirements: 3.1
        
        基于硬件信息生成唯一设备标识符。
        使用 MAC 地址 + 主机名 + 处理器信息生成 SHA256 哈希。
        
        Returns:
            str: 设备指纹（64 字符十六进制字符串）
        """
        if self._cached_machine_id:
            return self._cached_machine_id
        
        try:
            # 收集硬件信息
            components = [
                str(uuid.getnode()),  # MAC 地址
                platform.node(),       # 主机名
                platform.processor(), # 处理器信息
                platform.machine(),   # 机器类型
            ]
            
            # 生成 SHA256 哈希
            raw = "|".join(components)
            self._cached_machine_id = hashlib.sha256(raw.encode()).hexdigest()
            
            return self._cached_machine_id
            
        except Exception as e:
            device_log(f"生成设备指纹失败: {e}")
            # 回退：使用随机 UUID（生成 64 字符十六进制）
            fallback_uuid = str(uuid.uuid4()).replace("-", "")
            self._cached_machine_id = hashlib.sha256(fallback_uuid.encode()).hexdigest()
            return self._cached_machine_id
    
    def get_devices(self) -> List[DeviceInfo]:
        """获取用户所有设备
        
        Requirements: 3.3
        
        Returns:
            List[DeviceInfo]: 设备列表
        """
        try:
            response = self._client.table("devices").select("*").eq(
                "user_id", self._user_id
            ).execute()
            
            devices = []
            for row in response.data:
                devices.append(DeviceInfo(
                    id=row.get("id", ""),
                    user_id=row.get("user_id", ""),
                    machine_id=row.get("machine_id", ""),
                    device_name=row.get("device_name", ""),
                    os_version=row.get("os_version", ""),
                    app_version=row.get("app_version", ""),
                    is_active=row.get("is_active", False),
                    last_seen=row.get("last_seen"),
                    created_at=row.get("created_at"),
                ))
            
            return devices
            
        except Exception as e:
            device_log(f"获取设备列表失败: {e}")
            return []
    
    def get_active_devices(self) -> List[DeviceInfo]:
        """获取用户所有激活的设备
        
        Returns:
            List[DeviceInfo]: 激活的设备列表
        """
        try:
            response = self._client.table("devices").select("*").eq(
                "user_id", self._user_id
            ).eq("is_active", True).execute()
            
            devices = []
            for row in response.data:
                devices.append(DeviceInfo(
                    id=row.get("id", ""),
                    user_id=row.get("user_id", ""),
                    machine_id=row.get("machine_id", ""),
                    device_name=row.get("device_name", ""),
                    os_version=row.get("os_version", ""),
                    app_version=row.get("app_version", ""),
                    is_active=True,
                    last_seen=row.get("last_seen"),
                    created_at=row.get("created_at"),
                ))
            
            return devices
            
        except Exception as e:
            device_log(f"获取激活设备列表失败: {e}")
            return []
    
    def activate_device(
        self, 
        machine_id: Optional[str] = None, 
        device_name: Optional[str] = None
    ) -> tuple[bool, str]:
        """激活设备
        
        Requirements: 3.2, 3.4
        
        Args:
            machine_id: 设备 ID，默认使用当前设备
            device_name: 设备名称，默认使用主机名
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        if machine_id is None:
            machine_id = self.get_machine_id()
        
        if device_name is None:
            device_name = platform.node()
        
        try:
            from screenshot_tool import __version__
            
            # 检查设备是否已存在
            existing = self._client.table("devices").select("id, is_active").eq(
                "user_id", self._user_id
            ).eq("machine_id", machine_id).execute()
            
            if existing.data:
                # 设备已存在，更新为激活状态
                device_id = existing.data[0]["id"]
                self._client.table("devices").update({
                    "is_active": True,
                    "device_name": device_name,
                    "os_version": f"{platform.system()} {platform.release()}",
                    "app_version": __version__,
                }).eq("id", device_id).execute()
                
                device_log(f"设备已重新激活: {machine_id[:16]}...")
                return True, "设备已激活"
            
            # 新设备，插入记录
            self._client.table("devices").insert({
                "user_id": self._user_id,
                "machine_id": machine_id,
                "device_name": device_name,
                "os_version": f"{platform.system()} {platform.release()}",
                "app_version": __version__,
                "is_active": True,
            }).execute()
            
            device_log(f"新设备已激活: {machine_id[:16]}...")
            return True, "设备已激活"
            
        except Exception as e:
            device_log(f"激活设备失败: {e}")
            return False, f"激活失败：{str(e)}"
    
    def deactivate_device(self, device_id: str) -> tuple[bool, str]:
        """停用设备
        
        Requirements: 3.5
        
        Args:
            device_id: 设备记录 ID
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 验证设备属于当前用户
            response = self._client.table("devices").select("id").eq(
                "id", device_id
            ).eq("user_id", self._user_id).execute()
            
            if not response.data:
                return False, "设备不存在或无权操作"
            
            # 更新为停用状态
            self._client.table("devices").update({
                "is_active": False
            }).eq("id", device_id).execute()
            
            device_log(f"设备已停用: {device_id}")
            return True, "设备已停用"
            
        except Exception as e:
            device_log(f"停用设备失败: {e}")
            return False, f"停用失败：{str(e)}"
    
    def can_activate(self, is_vip: bool = False) -> tuple[bool, str]:
        """检查是否可以激活新设备
        
        Requirements: 3.2, 3.4
        
        Args:
            is_vip: 是否为 VIP 用户
            
        Returns:
            tuple[bool, str]: (是否可以激活, 消息)
        """
        machine_id = self.get_machine_id()
        
        try:
            # 检查当前设备是否已激活
            existing = self._client.table("devices").select("id, is_active").eq(
                "user_id", self._user_id
            ).eq("machine_id", machine_id).execute()
            
            if existing.data and existing.data[0].get("is_active"):
                return True, "当前设备已激活"
            
            # 获取已激活设备数量
            active_devices = self.get_active_devices()
            active_count = len(active_devices)
            
            # 检查设备限制
            limit = self.VIP_DEVICE_LIMIT if is_vip else self.FREE_DEVICE_LIMIT
            
            if active_count >= limit:
                return False, f"已达到设备上限（{limit} 台），请先停用其他设备"
            
            return True, "可以激活"
            
        except Exception as e:
            device_log(f"检查设备限制失败: {e}")
            # 网络错误时允许激活（宽松策略）
            return True, "无法验证设备限制，允许激活"
    
    def is_current_device_active(self) -> bool:
        """检查当前设备是否已激活
        
        Returns:
            bool: 是否已激活
        """
        machine_id = self.get_machine_id()
        
        try:
            response = self._client.table("devices").select("is_active").eq(
                "user_id", self._user_id
            ).eq("machine_id", machine_id).execute()
            
            if response.data:
                return response.data[0].get("is_active", False)
            
            return False
            
        except Exception as e:
            device_log(f"检查设备状态失败: {e}")
            return False
    
    def update_last_seen(self) -> None:
        """更新当前设备的最后活跃时间"""
        machine_id = self.get_machine_id()
        
        try:
            from datetime import datetime, timezone
            
            self._client.table("devices").update({
                "last_seen": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", self._user_id).eq("machine_id", machine_id).execute()
            
        except Exception as e:
            device_log(f"更新最后活跃时间失败: {e}")
