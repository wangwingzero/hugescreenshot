# =====================================================
# =============== 历史列表模型测试 ===============
# =====================================================

"""
测试 HistoryListModel 高性能历史列表模型

Feature: extreme-performance-optimization
Requirements: 11.1, 11.2, 11.6

测试覆盖：
1. 基本 CRUD 操作
2. 100ms 防抖批量插入
3. beginInsertRows/endInsertRows 批量更新
4. 索引映射正确性
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt, QModelIndex


class TestHistoryListModelBasic:
    """HistoryListModel 基本功能测试"""
    
    def test_create_empty_model(self, qtbot):
        """测试创建空模型"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        assert model.rowCount() == 0
        assert model.get_pending_count() == 0
    
    def test_add_single_item(self, qtbot):
        """测试添加单个条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30"
        )
        
        model.add_item(item)
        
        # 添加后应该在待处理列表中
        assert model.get_pending_count() == 1
        assert model.rowCount() == 0  # 还未刷新
        
        # 强制刷新
        model.force_flush()
        
        assert model.rowCount() == 1
        assert model.get_pending_count() == 0
    
    def test_add_multiple_items(self, qtbot):
        """测试添加多个条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(5):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"截图 {i}",
                timestamp=f"2025-01-15 10:{i:02d}"
            )
            model.add_item(item)
        
        model.force_flush()
        
        assert model.rowCount() == 5
    
    def test_add_duplicate_item_ignored(self, qtbot):
        """测试添加重复条目被忽略"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item1 = HistoryItemData(
            id="same-id",
            preview_text="第一个",
            timestamp="2025-01-15 10:00"
        )
        item2 = HistoryItemData(
            id="same-id",
            preview_text="第二个",
            timestamp="2025-01-15 11:00"
        )
        
        model.add_item(item1)
        model.add_item(item2)  # 应该被忽略
        model.force_flush()
        
        assert model.rowCount() == 1
        # 应该是第一个添加的
        assert model.get_item("same-id").preview_text == "第一个"
    
    def test_add_duplicate_in_pending_ignored(self, qtbot):
        """测试待处理列表中的重复条目被忽略"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # 添加两个相同 ID 的条目（不刷新）
        item1 = HistoryItemData(id="dup-id", preview_text="第一个", timestamp="10:00")
        item2 = HistoryItemData(id="dup-id", preview_text="第二个", timestamp="11:00")
        
        model.add_item(item1)
        model.add_item(item2)
        
        # 待处理列表应该只有一个
        assert model.get_pending_count() == 1
    
    def test_data_display_role(self, qtbot):
        """测试 DisplayRole 返回预览文本"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(
            id="test-1",
            preview_text="测试预览文本",
            timestamp="2025-01-15 10:30"
        )
        model.add_item(item)
        model.force_flush()
        
        index = model.index(0, 0)
        display_text = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert display_text == "测试预览文本"
    
    def test_data_user_role(self, qtbot):
        """测试 UserRole 返回完整数据对象"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(
            id="test-1",
            preview_text="测试",
            timestamp="2025-01-15 10:30",
            is_pinned=True
        )
        model.add_item(item)
        model.force_flush()
        
        index = model.index(0, 0)
        data = model.data(index, Qt.ItemDataRole.UserRole)
        
        assert isinstance(data, HistoryItemData)
        assert data.id == "test-1"
        assert data.is_pinned is True
    
    def test_data_invalid_index(self, qtbot):
        """测试无效索引返回 None"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        # 无效索引
        invalid_index = QModelIndex()
        assert model.data(invalid_index, Qt.ItemDataRole.DisplayRole) is None
        
        # 超出范围的索引
        out_of_range = model.index(100, 0)
        assert model.data(out_of_range, Qt.ItemDataRole.DisplayRole) is None
    
    def test_remove_item(self, qtbot):
        """测试删除条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(3):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"截图 {i}",
                timestamp=f"2025-01-15 10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        assert model.rowCount() == 3
        
        # 删除中间的条目
        result = model.remove_item("test-1")
        
        assert result is True
        assert model.rowCount() == 2
        assert not model.contains("test-1")
        assert model.contains("test-0")
        assert model.contains("test-2")
    
    def test_remove_nonexistent_item(self, qtbot):
        """测试删除不存在的条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        result = model.remove_item("nonexistent")
        
        assert result is False
    
    def test_get_item_by_id(self, qtbot):
        """测试根据 ID 获取条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(
            id="find-me",
            preview_text="找到我",
            timestamp="2025-01-15 10:30"
        )
        model.add_item(item)
        model.force_flush()
        
        found = model.get_item("find-me")
        
        assert found is not None
        assert found.preview_text == "找到我"
    
    def test_get_item_at_row(self, qtbot):
        """测试根据行号获取条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(3):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"截图 {i}",
                timestamp=f"2025-01-15 10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        # 批量插入时保持添加顺序，所以顺序是 0, 1, 2
        item_at_0 = model.get_item_at(0)
        assert item_at_0.id == "test-0"
        
        item_at_2 = model.get_item_at(2)
        assert item_at_2.id == "test-2"
    
    def test_clear_all(self, qtbot):
        """测试清空所有条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(5):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"截图 {i}",
                timestamp=f"2025-01-15 10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        assert model.rowCount() == 5
        
        model.clear_all()
        
        assert model.rowCount() == 0
        assert model.get_pending_count() == 0
    
    def test_clear_all_with_pending(self, qtbot):
        """测试清空时也清除待处理的条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # 添加但不刷新
        item = HistoryItemData(id="pending", preview_text="待处理", timestamp="10:00")
        model.add_item(item)
        
        assert model.get_pending_count() == 1
        
        model.clear_all()
        
        assert model.get_pending_count() == 0
    
    def test_contains(self, qtbot):
        """测试 contains 方法"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(id="exists", preview_text="存在", timestamp="10:00")
        model.add_item(item)
        model.force_flush()
        
        assert model.contains("exists") is True
        assert model.contains("not-exists") is False
    
    def test_get_all_items(self, qtbot):
        """测试获取所有条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(3):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"截图 {i}",
                timestamp=f"2025-01-15 10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        all_items = model.get_all_items()
        
        assert len(all_items) == 3
        # 返回的是副本
        all_items.clear()
        assert model.rowCount() == 3


class TestHistoryListModelDebounce:
    """HistoryListModel 防抖功能测试"""
    
    def test_debounce_timer_interval(self, qtbot):
        """测试防抖定时器间隔为 100ms
        
        **Validates: Requirements 11.2**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        assert model._update_timer.interval() == 100
        assert model._update_timer.isSingleShot() is True
    
    def test_debounce_batches_inserts(self, qtbot):
        """测试防抖合并多次插入
        
        **Validates: Requirements 11.2, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # 快速添加多个条目
        for i in range(10):
            item = HistoryItemData(
                id=f"batch-{i}",
                preview_text=f"批量 {i}",
                timestamp=f"10:{i:02d}"
            )
            model.add_item(item)
        
        # 此时应该都在待处理列表中
        assert model.get_pending_count() == 10
        assert model.rowCount() == 0
        
        # 等待防抖定时器触发
        qtbot.wait(150)  # 等待超过 100ms
        
        # 现在应该都已插入
        assert model.rowCount() == 10
        assert model.get_pending_count() == 0
    
    def test_force_flush_bypasses_debounce(self, qtbot):
        """测试 force_flush 绕过防抖"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(id="immediate", preview_text="立即", timestamp="10:00")
        
        model.add_item(item)
        
        # 不等待，直接强制刷新
        model.force_flush()
        
        assert model.rowCount() == 1
        assert model.get_pending_count() == 0


class TestHistoryListModelBatchUpdate:
    """HistoryListModel 批量更新测试"""
    
    def test_begin_end_insert_rows_called(self, qtbot):
        """测试使用 beginInsertRows/endInsertRows 批量更新
        
        **Validates: Requirements 11.1, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # 监控信号
        rows_about_to_be_inserted = []
        rows_inserted = []
        
        def on_rows_about_to_be_inserted(parent, first, last):
            rows_about_to_be_inserted.append((first, last))
        
        def on_rows_inserted(parent, first, last):
            rows_inserted.append((first, last))
        
        model.rowsAboutToBeInserted.connect(on_rows_about_to_be_inserted)
        model.rowsInserted.connect(on_rows_inserted)
        
        # 添加 5 个条目
        for i in range(5):
            item = HistoryItemData(
                id=f"batch-{i}",
                preview_text=f"批量 {i}",
                timestamp=f"10:{i:02d}"
            )
            model.add_item(item)
        
        model.force_flush()
        
        # 应该只触发一次批量插入信号
        assert len(rows_about_to_be_inserted) == 1
        assert len(rows_inserted) == 1
        
        # 验证插入范围
        first, last = rows_inserted[0]
        assert first == 0
        assert last == 4  # 5 个条目，索引 0-4
    
    def test_index_mapping_after_insert(self, qtbot):
        """测试插入后索引映射正确"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # 先添加一批
        for i in range(3):
            item = HistoryItemData(
                id=f"first-{i}",
                preview_text=f"第一批 {i}",
                timestamp=f"10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        # 再添加一批
        for i in range(2):
            item = HistoryItemData(
                id=f"second-{i}",
                preview_text=f"第二批 {i}",
                timestamp=f"11:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        # 验证索引映射
        # 新批次插入到顶部，所以顺序是 second-0, second-1, first-0, first-1, first-2
        assert model._id_to_index["second-0"] == 0
        assert model._id_to_index["second-1"] == 1
        assert model._id_to_index["first-0"] == 2
        assert model._id_to_index["first-1"] == 3
        assert model._id_to_index["first-2"] == 4
    
    def test_index_mapping_after_remove(self, qtbot):
        """测试删除后索引映射正确"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(5):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"测试 {i}",
                timestamp=f"10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        # 初始顺序: test-0, test-1, test-2, test-3, test-4
        # 删除 test-2 (在索引 2)
        model.remove_item("test-2")
        
        # 验证索引映射更新
        # 删除后顺序: test-0, test-1, test-3, test-4
        assert "test-2" not in model._id_to_index
        assert model._id_to_index["test-0"] == 0
        assert model._id_to_index["test-1"] == 1
        assert model._id_to_index["test-3"] == 2
        assert model._id_to_index["test-4"] == 3


class TestHistoryListModelUpdate:
    """HistoryListModel 更新功能测试"""
    
    def test_update_item(self, qtbot):
        """测试更新条目属性"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(
            id="update-me",
            preview_text="原始文本",
            timestamp="10:00",
            is_pinned=False
        )
        model.add_item(item)
        model.force_flush()
        
        # 更新属性
        result = model.update_item("update-me", is_pinned=True, preview_text="更新后")
        
        assert result is True
        updated = model.get_item("update-me")
        assert updated.is_pinned is True
        assert updated.preview_text == "更新后"
    
    def test_update_nonexistent_item(self, qtbot):
        """测试更新不存在的条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        result = model.update_item("nonexistent", is_pinned=True)
        
        assert result is False
    
    def test_update_emits_data_changed(self, qtbot):
        """测试更新时发出 dataChanged 信号"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(id="signal-test", preview_text="测试", timestamp="10:00")
        model.add_item(item)
        model.force_flush()
        
        # 监控信号
        data_changed_calls = []
        
        def on_data_changed(top_left, bottom_right, roles):
            data_changed_calls.append((top_left.row(), bottom_right.row()))
        
        model.dataChanged.connect(on_data_changed)
        
        model.update_item("signal-test", is_pinned=True)
        
        assert len(data_changed_calls) == 1
        assert data_changed_calls[0] == (0, 0)


class TestHistoryListModelMoveToTop:
    """HistoryListModel 移动到顶部功能测试"""
    
    def test_move_to_top(self, qtbot):
        """测试将条目移动到顶部"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        for i in range(5):
            item = HistoryItemData(
                id=f"test-{i}",
                preview_text=f"测试 {i}",
                timestamp=f"10:{i:02d}"
            )
            model.add_item(item)
        model.force_flush()
        
        # 初始顺序: test-0, test-1, test-2, test-3, test-4
        assert model.get_item_at(0).id == "test-0"
        
        # 将 test-3 移动到顶部
        result = model.move_to_top("test-3")
        
        assert result is True
        assert model.get_item_at(0).id == "test-3"
        assert model.get_item_at(1).id == "test-0"
    
    def test_move_to_top_already_at_top(self, qtbot):
        """测试已在顶部的条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(id="only-one", preview_text="唯一", timestamp="10:00")
        model.add_item(item)
        model.force_flush()
        
        result = model.move_to_top("only-one")
        
        assert result is True
        assert model.get_item_at(0).id == "only-one"
    
    def test_move_to_top_nonexistent(self, qtbot):
        """测试移动不存在的条目"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        result = model.move_to_top("nonexistent")
        
        assert result is False


class TestHistoryListModelRowCount:
    """HistoryListModel rowCount 测试"""
    
    def test_row_count_with_parent(self, qtbot):
        """测试带父索引的 rowCount 返回 0（列表模型无子项）"""
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        item = HistoryItemData(id="test", preview_text="测试", timestamp="10:00")
        model.add_item(item)
        model.force_flush()
        
        # 使用有效的父索引
        parent_index = model.index(0, 0)
        
        # 列表模型的子项数应该为 0
        assert model.rowCount(parent_index) == 0

