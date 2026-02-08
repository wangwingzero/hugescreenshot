# =====================================================
# =============== DialogFactory 测试 ===============
# =====================================================

"""
DialogFactory 单元测试

Feature: performance-ui-optimization
Requirements: 1.4, 9.1, 9.2
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QDialog, QApplication

from screenshot_tool.ui.dialog_factory import DialogFactory, DialogIds


@pytest.fixture(autouse=True)
def clean_factory():
    """每个测试前后清理工厂状态"""
    DialogFactory.clear()
    yield
    DialogFactory.clear()


@pytest.fixture
def mock_dialog():
    """创建模拟对话框"""
    dialog = MagicMock(spec=QDialog)
    return dialog


class TestDialogFactoryRegister:
    """测试 register 方法"""
    
    def test_register_creator(self):
        """测试注册创建函数"""
        creator = MagicMock(return_value=MagicMock(spec=QDialog))
        
        DialogFactory.register("test_dialog", creator)
        
        assert DialogFactory.is_registered("test_dialog")
        # 注册时不应调用创建函数
        creator.assert_not_called()
    
    def test_register_overwrites_existing(self):
        """测试重复注册会覆盖"""
        creator1 = MagicMock(return_value=MagicMock(spec=QDialog))
        creator2 = MagicMock(return_value=MagicMock(spec=QDialog))
        
        DialogFactory.register("test_dialog", creator1)
        DialogFactory.register("test_dialog", creator2)
        
        # 获取时应使用新的创建函数
        DialogFactory.get("test_dialog")
        creator1.assert_not_called()
        creator2.assert_called_once()


class TestDialogFactoryGet:
    """测试 get 方法"""
    
    def test_get_creates_on_first_access(self):
        """测试首次访问时创建实例"""
        mock_dialog = MagicMock(spec=QDialog)
        creator = MagicMock(return_value=mock_dialog)
        
        DialogFactory.register("test_dialog", creator)
        
        # 首次获取
        result = DialogFactory.get("test_dialog")
        
        assert result is mock_dialog
        creator.assert_called_once()
    
    def test_get_returns_cached_instance(self):
        """测试后续访问返回缓存实例"""
        mock_dialog = MagicMock(spec=QDialog)
        creator = MagicMock(return_value=mock_dialog)
        
        DialogFactory.register("test_dialog", creator)
        
        # 多次获取
        result1 = DialogFactory.get("test_dialog")
        result2 = DialogFactory.get("test_dialog")
        result3 = DialogFactory.get("test_dialog")
        
        # 应该是同一个实例
        assert result1 is result2 is result3
        # 创建函数只调用一次
        creator.assert_called_once()
    
    def test_get_unregistered_returns_none(self):
        """测试获取未注册的对话框返回 None"""
        result = DialogFactory.get("nonexistent")
        
        assert result is None
    
    def test_get_multiple_dialogs(self):
        """测试获取多个不同对话框"""
        dialog1 = MagicMock(spec=QDialog)
        dialog2 = MagicMock(spec=QDialog)
        
        DialogFactory.register("dialog1", lambda: dialog1)
        DialogFactory.register("dialog2", lambda: dialog2)
        
        result1 = DialogFactory.get("dialog1")
        result2 = DialogFactory.get("dialog2")
        
        assert result1 is dialog1
        assert result2 is dialog2
        assert result1 is not result2


class TestDialogFactoryGetOrCreate:
    """测试 get_or_create 方法"""
    
    def test_get_or_create_registers_and_creates(self):
        """测试自动注册并创建"""
        mock_dialog = MagicMock(spec=QDialog)
        creator = MagicMock(return_value=mock_dialog)
        
        result = DialogFactory.get_or_create("test_dialog", creator)
        
        assert result is mock_dialog
        assert DialogFactory.is_registered("test_dialog")
        assert DialogFactory.is_created("test_dialog")
    
    def test_get_or_create_uses_existing_registration(self):
        """测试使用已有注册"""
        dialog1 = MagicMock(spec=QDialog)
        dialog2 = MagicMock(spec=QDialog)
        
        DialogFactory.register("test_dialog", lambda: dialog1)
        
        # 传入不同的创建函数，但应使用已注册的
        result = DialogFactory.get_or_create("test_dialog", lambda: dialog2)
        
        assert result is dialog1


class TestDialogFactoryIsCreated:
    """测试 is_created 方法"""
    
    def test_is_created_false_before_get(self):
        """测试获取前返回 False"""
        DialogFactory.register("test_dialog", lambda: MagicMock(spec=QDialog))
        
        assert not DialogFactory.is_created("test_dialog")
    
    def test_is_created_true_after_get(self):
        """测试获取后返回 True"""
        DialogFactory.register("test_dialog", lambda: MagicMock(spec=QDialog))
        DialogFactory.get("test_dialog")
        
        assert DialogFactory.is_created("test_dialog")
    
    def test_is_created_false_for_unregistered(self):
        """测试未注册的返回 False"""
        assert not DialogFactory.is_created("nonexistent")


class TestDialogFactoryIsRegistered:
    """测试 is_registered 方法"""
    
    def test_is_registered_true(self):
        """测试已注册返回 True"""
        DialogFactory.register("test_dialog", lambda: MagicMock(spec=QDialog))
        
        assert DialogFactory.is_registered("test_dialog")
    
    def test_is_registered_false(self):
        """测试未注册返回 False"""
        assert not DialogFactory.is_registered("nonexistent")


class TestDialogFactoryDestroy:
    """测试 destroy 方法"""
    
    def test_destroy_calls_delete_later(self):
        """测试销毁调用 deleteLater"""
        mock_dialog = MagicMock(spec=QDialog)
        DialogFactory.register("test_dialog", lambda: mock_dialog)
        DialogFactory.get("test_dialog")
        
        result = DialogFactory.destroy("test_dialog")
        
        assert result is True
        mock_dialog.deleteLater.assert_called_once()
        assert not DialogFactory.is_created("test_dialog")
    
    def test_destroy_keeps_registration(self):
        """测试销毁保留注册"""
        mock_dialog = MagicMock(spec=QDialog)
        DialogFactory.register("test_dialog", lambda: mock_dialog)
        DialogFactory.get("test_dialog")
        
        DialogFactory.destroy("test_dialog")
        
        # 注册仍在
        assert DialogFactory.is_registered("test_dialog")
        # 但实例已销毁
        assert not DialogFactory.is_created("test_dialog")
    
    def test_destroy_nonexistent_returns_false(self):
        """测试销毁不存在的返回 False"""
        result = DialogFactory.destroy("nonexistent")
        
        assert result is False
    
    def test_destroy_uncreated_returns_false(self):
        """测试销毁未创建的返回 False"""
        DialogFactory.register("test_dialog", lambda: MagicMock(spec=QDialog))
        
        result = DialogFactory.destroy("test_dialog")
        
        assert result is False


class TestDialogFactoryDestroyAll:
    """测试 destroy_all 方法"""
    
    def test_destroy_all_destroys_all_created(self):
        """测试销毁所有已创建的对话框"""
        dialog1 = MagicMock(spec=QDialog)
        dialog2 = MagicMock(spec=QDialog)
        dialog3 = MagicMock(spec=QDialog)
        
        DialogFactory.register("dialog1", lambda: dialog1)
        DialogFactory.register("dialog2", lambda: dialog2)
        DialogFactory.register("dialog3", lambda: dialog3)
        
        # 只创建前两个
        DialogFactory.get("dialog1")
        DialogFactory.get("dialog2")
        
        count = DialogFactory.destroy_all()
        
        assert count == 2
        dialog1.deleteLater.assert_called_once()
        dialog2.deleteLater.assert_called_once()
        dialog3.deleteLater.assert_not_called()
    
    def test_destroy_all_returns_zero_when_empty(self):
        """测试没有创建时返回 0"""
        count = DialogFactory.destroy_all()
        
        assert count == 0


class TestDialogFactoryUnregister:
    """测试 unregister 方法"""
    
    def test_unregister_removes_registration(self):
        """测试取消注册"""
        DialogFactory.register("test_dialog", lambda: MagicMock(spec=QDialog))
        
        result = DialogFactory.unregister("test_dialog")
        
        assert result is True
        assert not DialogFactory.is_registered("test_dialog")
    
    def test_unregister_destroys_instance(self):
        """测试取消注册同时销毁实例"""
        mock_dialog = MagicMock(spec=QDialog)
        DialogFactory.register("test_dialog", lambda: mock_dialog)
        DialogFactory.get("test_dialog")
        
        DialogFactory.unregister("test_dialog")
        
        mock_dialog.deleteLater.assert_called_once()
        assert not DialogFactory.is_created("test_dialog")
    
    def test_unregister_nonexistent_returns_false(self):
        """测试取消注册不存在的返回 False"""
        result = DialogFactory.unregister("nonexistent")
        
        assert result is False


class TestDialogFactoryGetIds:
    """测试获取 ID 列表方法"""
    
    def test_get_registered_ids(self):
        """测试获取已注册 ID 列表"""
        DialogFactory.register("dialog1", lambda: MagicMock(spec=QDialog))
        DialogFactory.register("dialog2", lambda: MagicMock(spec=QDialog))
        
        ids = DialogFactory.get_registered_ids()
        
        assert set(ids) == {"dialog1", "dialog2"}
    
    def test_get_created_ids(self):
        """测试获取已创建 ID 列表"""
        DialogFactory.register("dialog1", lambda: MagicMock(spec=QDialog))
        DialogFactory.register("dialog2", lambda: MagicMock(spec=QDialog))
        DialogFactory.register("dialog3", lambda: MagicMock(spec=QDialog))
        
        DialogFactory.get("dialog1")
        DialogFactory.get("dialog3")
        
        ids = DialogFactory.get_created_ids()
        
        assert set(ids) == {"dialog1", "dialog3"}


class TestDialogFactoryGetStats:
    """测试 get_stats 方法"""
    
    def test_get_stats(self):
        """测试获取统计信息"""
        DialogFactory.register("dialog1", lambda: MagicMock(spec=QDialog))
        DialogFactory.register("dialog2", lambda: MagicMock(spec=QDialog))
        DialogFactory.register("dialog3", lambda: MagicMock(spec=QDialog))
        
        DialogFactory.get("dialog1")
        
        stats = DialogFactory.get_stats()
        
        assert stats["registered_count"] == 3
        assert stats["created_count"] == 1


class TestDialogFactoryClear:
    """测试 clear 方法"""
    
    def test_clear_removes_all(self):
        """测试清除所有注册和实例"""
        dialog1 = MagicMock(spec=QDialog)
        dialog2 = MagicMock(spec=QDialog)
        
        DialogFactory.register("dialog1", lambda: dialog1)
        DialogFactory.register("dialog2", lambda: dialog2)
        DialogFactory.get("dialog1")
        
        DialogFactory.clear()
        
        assert not DialogFactory.is_registered("dialog1")
        assert not DialogFactory.is_registered("dialog2")
        assert not DialogFactory.is_created("dialog1")
        dialog1.deleteLater.assert_called_once()


class TestDialogFactoryRecreate:
    """测试 recreate 方法"""
    
    def test_recreate_creates_new_instance(self):
        """测试重新创建返回新实例"""
        dialog1 = MagicMock(spec=QDialog)
        dialog2 = MagicMock(spec=QDialog)
        call_count = [0]
        
        def creator():
            call_count[0] += 1
            return dialog1 if call_count[0] == 1 else dialog2
        
        DialogFactory.register("test_dialog", creator)
        
        # 首次获取
        first = DialogFactory.get("test_dialog")
        assert first is dialog1
        
        # 重新创建
        second = DialogFactory.recreate("test_dialog")
        assert second is dialog2
        
        # 旧实例被销毁
        dialog1.deleteLater.assert_called_once()
    
    def test_recreate_unregistered_returns_none(self):
        """测试重新创建未注册的返回 None"""
        result = DialogFactory.recreate("nonexistent")
        
        assert result is None


class TestDialogIds:
    """测试 DialogIds 常量"""
    
    def test_dialog_ids_are_strings(self):
        """测试所有 ID 都是字符串"""
        assert isinstance(DialogIds.SETTINGS, str)
        assert isinstance(DialogIds.WEB_TO_MARKDOWN, str)
        assert isinstance(DialogIds.FILE_TO_MARKDOWN, str)
        assert isinstance(DialogIds.LOGIN, str)
    
    def test_dialog_ids_are_unique(self):
        """测试所有 ID 都是唯一的"""
        ids = [
            DialogIds.SETTINGS,
            DialogIds.WEB_TO_MARKDOWN,
            DialogIds.FILE_TO_MARKDOWN,
            DialogIds.GONGWEN,
            DialogIds.REGULATION_SEARCH,
            DialogIds.RECORDING_SETTINGS,
            DialogIds.RECORDING_PREVIEW,
            DialogIds.CLIPBOARD_HISTORY,
            DialogIds.LOGIN,
            DialogIds.PAYMENT,
            DialogIds.DEVICE_MANAGER,
            DialogIds.CRASH,
            DialogIds.BATCH_URL,
            DialogIds.SCHEDULED_SHUTDOWN,
        ]
        
        assert len(ids) == len(set(ids))


class TestDialogFactoryLazyLoading:
    """测试延迟加载特性
    
    Feature: performance-ui-optimization
    Property 5: Lazy Loading
    Validates: Requirements 1.4, 9.1
    """
    
    def test_creator_not_called_on_register(self):
        """测试注册时不调用创建函数"""
        creator = MagicMock(return_value=MagicMock(spec=QDialog))
        
        DialogFactory.register("test_dialog", creator)
        
        # 注册后创建函数不应被调用
        creator.assert_not_called()
    
    def test_creator_called_only_on_first_get(self):
        """测试创建函数只在首次获取时调用"""
        creator = MagicMock(return_value=MagicMock(spec=QDialog))
        
        DialogFactory.register("test_dialog", creator)
        
        # 多次获取
        for _ in range(10):
            DialogFactory.get("test_dialog")
        
        # 创建函数只调用一次
        creator.assert_called_once()
    
    def test_multiple_dialogs_lazy_loaded_independently(self):
        """测试多个对话框独立延迟加载"""
        creator1 = MagicMock(return_value=MagicMock(spec=QDialog))
        creator2 = MagicMock(return_value=MagicMock(spec=QDialog))
        creator3 = MagicMock(return_value=MagicMock(spec=QDialog))
        
        DialogFactory.register("dialog1", creator1)
        DialogFactory.register("dialog2", creator2)
        DialogFactory.register("dialog3", creator3)
        
        # 只获取 dialog1
        DialogFactory.get("dialog1")
        
        # 只有 dialog1 的创建函数被调用
        creator1.assert_called_once()
        creator2.assert_not_called()
        creator3.assert_not_called()
