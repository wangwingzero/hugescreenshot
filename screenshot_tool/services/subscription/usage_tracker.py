"""
使用量追踪器 - 追踪功能使用次数

Feature: subscription-system
Requirements: 5.1, 5.2, 5.3, 5.4
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional

from supabase import Client

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def usage_log(message: str):
    """使用量追踪日志"""
    _debug_log(message, "USAGE")


# 功能每日限制配置
DAILY_LIMITS = {
    "translation": 10,      # 翻译每日 10 次
    "web_to_markdown": 5,   # 网页转 Markdown 每日 5 次
}


class UsageTracker:
    """使用量追踪器
    
    追踪用户每日功能使用次数，支持本地缓存和服务器同步。
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    
    Attributes:
        _client: Supabase 客户端
        _user_id: 当前用户 ID
        _cache: 本地缓存 {date: {feature: count}}
        _cache_path: 缓存文件路径
    """
    
    def __init__(
        self, 
        client: Optional[Client], 
        user_id: str,
        cache_dir: Optional[str] = None
    ):
        """初始化使用量追踪器
        
        Args:
            client: Supabase 客户端（可选，离线模式为 None）
            user_id: 当前用户 ID
            cache_dir: 缓存目录，默认 ~/.screenshot_tool/
            
        Raises:
            ValueError: 如果 user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        
        self._client = client
        self._user_id = user_id.strip()
        
        # 设置缓存路径
        if cache_dir is None:
            # 使用统一的用户数据目录
            from screenshot_tool.core.config_manager import get_user_data_dir
            cache_dir = get_user_data_dir()
        
        self._cache_dir = cache_dir
        self._cache_path = os.path.join(cache_dir, "usage_cache.json")
        
        # 加载缓存
        self._cache: Dict[str, Dict[str, int]] = self._load_cache()
        
        # 检查并执行午夜重置
        self._check_midnight_reset()
    
    def _ensure_cache_dir(self) -> None:
        """确保缓存目录存在"""
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
    
    def _get_today(self) -> str:
        """获取今天的日期字符串"""
        return date.today().isoformat()
    
    def _load_cache(self) -> Dict[str, Dict[str, int]]:
        """从文件加载缓存
        
        Returns:
            缓存数据 {date: {feature: count}}
        """
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 验证用户 ID 匹配
                if data.get("user_id") != self._user_id:
                    usage_log("缓存用户不匹配，忽略缓存")
                    return {}
                
                return data.get("usage", {})
        except Exception as e:
            usage_log(f"加载使用量缓存失败: {e}")
        
        return {}
    
    def _save_cache(self) -> None:
        """保存缓存到文件"""
        try:
            self._ensure_cache_dir()
            
            data = {
                "user_id": self._user_id,
                "usage": self._cache,
                "updated_at": datetime.now().isoformat(),
            }
            
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            usage_log(f"保存使用量缓存失败: {e}")
    
    def _check_midnight_reset(self) -> None:
        """检查并执行午夜重置
        
        Requirements: 5.3
        
        如果缓存中没有今天的数据，清理旧数据。
        """
        today = self._get_today()
        
        # 清理非今天的数据
        old_dates = [d for d in self._cache.keys() if d != today]
        for old_date in old_dates:
            del self._cache[old_date]
        
        # 确保今天的数据存在
        if today not in self._cache:
            self._cache[today] = {}
            self._save_cache()
    
    def get_usage(self, feature: str) -> int:
        """获取指定功能今日使用次数
        
        Requirements: 5.1
        
        Args:
            feature: 功能名称
            
        Returns:
            int: 使用次数
        """
        today = self._get_today()
        return self._cache.get(today, {}).get(feature, 0)
    
    def get_remaining(self, feature: str) -> int:
        """获取指定功能今日剩余次数
        
        Requirements: 5.2
        
        Args:
            feature: 功能名称
            
        Returns:
            int: 剩余次数，-1 表示无限制
        """
        limit = DAILY_LIMITS.get(feature)
        if limit is None:
            return -1  # 无限制
        
        used = self.get_usage(feature)
        return max(0, limit - used)
    
    def get_limit(self, feature: str) -> int:
        """获取指定功能的每日限制
        
        Args:
            feature: 功能名称
            
        Returns:
            int: 每日限制，-1 表示无限制
        """
        return DAILY_LIMITS.get(feature, -1)
    
    def increment(self, feature: str) -> bool:
        """增加指定功能的使用次数
        
        Requirements: 5.1
        
        Args:
            feature: 功能名称
            
        Returns:
            bool: 是否成功（未超限）
        """
        today = self._get_today()
        
        # 确保今天的数据存在
        if today not in self._cache:
            self._cache[today] = {}
        
        # 检查是否超限
        limit = DAILY_LIMITS.get(feature)
        current = self._cache[today].get(feature, 0)
        
        if limit is not None and current >= limit:
            usage_log(f"功能 {feature} 已达到每日限制 {limit}")
            return False
        
        # 增加计数
        self._cache[today][feature] = current + 1
        self._save_cache()
        
        usage_log(f"功能 {feature} 使用次数: {current + 1}/{limit or '∞'}")
        return True
    
    def can_use(self, feature: str) -> bool:
        """检查是否可以使用指定功能
        
        Args:
            feature: 功能名称
            
        Returns:
            bool: 是否可以使用
        """
        limit = DAILY_LIMITS.get(feature)
        if limit is None:
            return True
        
        return self.get_usage(feature) < limit
    
    def sync_to_server(self) -> bool:
        """同步使用量到服务器
        
        Requirements: 5.4
        
        Returns:
            bool: 是否成功
        """
        if self._client is None:
            usage_log("离线模式，跳过同步")
            return False
        
        today = self._get_today()
        today_usage = self._cache.get(today, {})
        
        if not today_usage:
            return True
        
        try:
            # 使用 upsert 更新或插入使用量记录
            for feature, count in today_usage.items():
                self._client.table("usage_stats").upsert({
                    "user_id": self._user_id,
                    "date": today,
                    "feature": feature,
                    "count": count,
                }, on_conflict="user_id,date,feature").execute()
            
            usage_log(f"使用量已同步到服务器: {today_usage}")
            return True
            
        except Exception as e:
            usage_log(f"同步使用量失败: {e}")
            return False
    
    def get_all_usage_today(self) -> Dict[str, int]:
        """获取今日所有功能的使用量
        
        Returns:
            Dict[str, int]: {feature: count}
        """
        today = self._get_today()
        return self._cache.get(today, {}).copy()
    
    def reset_today(self) -> None:
        """重置今日使用量（仅用于测试）"""
        today = self._get_today()
        self._cache[today] = {}
        self._save_cache()
