# =====================================================
# =============== 对话框工厂 ===============
# =====================================================

"""
对话框工厂 - 延迟创建对话框实例

Feature: performance-ui-optimization
Requirements: 1.4, 9.1, 9.2

提供对话框的延迟创建机制，首次访问时才实例化，
减少启动时间和内存占用。
"""

from typing import Dict, Optional, Callable, List, Set
from PySide6.QtWidgets import QDialog, QWidget


class DialogFactory:
    """对话框工厂 - 延迟创建
    
    Feature: performance-ui-optimization
    Requirements: 1.4, 9.1, 9.2
    
    使用方法:
        # 注册对话框创建函数
        DialogFactory.register("settings", lambda: SettingsDialog(config, parent))
        
        # 获取对话框实例（首次调用时创建）
        dialog = DialogFactory.get("settings")
        if dialog:
            dialog.show()
        
        # 检查是否已创建
        if DialogFactory.is_created("settings"):
            ...
        
        # 销毁对话框释放内存
        DialogFactory.destroy("settings")
    """
    
    # 类级别存储，所有实例共享
    _dialogs: Dict[str, QDialog] = {}
    _creators: Dict[str, Callable[[], QDialog]] = {}
    
    @classmethod
    def register(cls, dialog_id: str, creator: Callable[[], QDialog]) -> None:
        """注册对话框创建函数
        
        Args:
            dialog_id: 对话框唯一标识符
            creator: 创建对话框的工厂函数，无参数，返回 QDialog 实例
            
        Example:
            DialogFactory.register("settings", lambda: SettingsDialog(config))
        """
        cls._creators[dialog_id] = creator
    
    @classmethod
    def get(cls, dialog_id: str) -> Optional[QDialog]:
        """获取或创建对话框实例
        
        首次调用时会执行注册的创建函数，后续调用返回缓存的实例。
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            对话框实例，如果未注册则返回 None
        """
        if dialog_id not in cls._dialogs:
            if dialog_id not in cls._creators:
                return None
            cls._dialogs[dialog_id] = cls._creators[dialog_id]()
        return cls._dialogs[dialog_id]
    
    @classmethod
    def get_or_create(cls, dialog_id: str, creator: Callable[[], QDialog]) -> QDialog:
        """获取或创建对话框实例（自动注册）
        
        如果对话框未注册，先注册再获取。便捷方法。
        
        Args:
            dialog_id: 对话框唯一标识符
            creator: 创建对话框的工厂函数
            
        Returns:
            对话框实例
        """
        if dialog_id not in cls._creators:
            cls.register(dialog_id, creator)
        return cls.get(dialog_id)
    
    @classmethod
    def is_created(cls, dialog_id: str) -> bool:
        """检查对话框是否已创建
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            True 如果对话框已创建，否则 False
        """
        return dialog_id in cls._dialogs
    
    @classmethod
    def is_registered(cls, dialog_id: str) -> bool:
        """检查对话框是否已注册
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            True 如果对话框已注册，否则 False
        """
        return dialog_id in cls._creators
    
    @classmethod
    def destroy(cls, dialog_id: str) -> bool:
        """销毁对话框释放内存
        
        调用 QDialog.deleteLater() 安全地销毁对话框。
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            True 如果成功销毁，False 如果对话框不存在
        """
        if dialog_id in cls._dialogs:
            dialog = cls._dialogs.pop(dialog_id)
            dialog.deleteLater()
            return True
        return False
    
    @classmethod
    def destroy_all(cls) -> int:
        """销毁所有已创建的对话框
        
        Returns:
            销毁的对话框数量
        """
        count = len(cls._dialogs)
        for dialog_id in list(cls._dialogs.keys()):
            cls.destroy(dialog_id)
        return count
    
    @classmethod
    def unregister(cls, dialog_id: str) -> bool:
        """取消注册对话框
        
        同时销毁已创建的实例。
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            True 如果成功取消注册，False 如果未注册
        """
        if dialog_id in cls._creators:
            cls.destroy(dialog_id)  # 先销毁实例
            del cls._creators[dialog_id]
            return True
        return False
    
    @classmethod
    def get_registered_ids(cls) -> List[str]:
        """获取所有已注册的对话框 ID
        
        Returns:
            已注册的对话框 ID 列表
        """
        return list(cls._creators.keys())
    
    @classmethod
    def get_created_ids(cls) -> List[str]:
        """获取所有已创建的对话框 ID
        
        Returns:
            已创建的对话框 ID 列表
        """
        return list(cls._dialogs.keys())
    
    @classmethod
    def get_stats(cls) -> Dict[str, int]:
        """获取工厂统计信息
        
        Returns:
            包含 registered_count 和 created_count 的字典
        """
        return {
            "registered_count": len(cls._creators),
            "created_count": len(cls._dialogs),
        }
    
    @classmethod
    def clear(cls) -> None:
        """清除所有注册和实例
        
        主要用于测试清理。会销毁所有已创建的对话框。
        """
        cls.destroy_all()
        cls._creators.clear()
    
    @classmethod
    def recreate(cls, dialog_id: str) -> Optional[QDialog]:
        """重新创建对话框
        
        销毁现有实例并创建新实例。用于需要刷新对话框状态的场景。
        
        Args:
            dialog_id: 对话框唯一标识符
            
        Returns:
            新创建的对话框实例，如果未注册则返回 None
        """
        if dialog_id not in cls._creators:
            return None
        cls.destroy(dialog_id)
        return cls.get(dialog_id)


# =====================================================
# 预定义对话框 ID 常量
# =====================================================

class DialogIds:
    """预定义的对话框 ID 常量
    
    使用常量避免字符串拼写错误。
    
    Example:
        DialogFactory.register(DialogIds.SETTINGS, lambda: SettingsDialog())
        dialog = DialogFactory.get(DialogIds.SETTINGS)
    """
    
    # 设置相关
    SETTINGS = "settings"
    
    # 转换工具
    WEB_TO_MARKDOWN = "web_to_markdown"
    FILE_TO_MARKDOWN = "file_to_markdown"
    GONGWEN = "gongwen"
    
    # 功能对话框
    REGULATION_SEARCH = "regulation_search"
    RECORDING_SETTINGS = "recording_settings"
    RECORDING_PREVIEW = "recording_preview"
    CLIPBOARD_HISTORY = "clipboard_history"
    
    # 账户相关
    LOGIN = "login"
    PAYMENT = "payment"
    DEVICE_MANAGER = "device_manager"
    
    # 其他
    CRASH = "crash"
    BATCH_URL = "batch_url"
    SCHEDULED_SHUTDOWN = "scheduled_shutdown"
