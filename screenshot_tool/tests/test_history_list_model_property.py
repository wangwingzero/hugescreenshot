# =====================================================
# =============== 历史列表模型属性测试 ===============
# =====================================================

"""
HistoryListModel 属性测试 - 使用 hypothesis 库

Feature: extreme-performance-optimization
Property 17: History List Incremental Update

测试覆盖：
1. 验证使用 beginInsertRows/endInsertRows 而非 clear()
2. 验证 100ms 防抖定时器批量合并多次插入
3. 验证增量更新而非全量重建

**Validates: Requirements 11.1, 11.2, 11.6**
"""

import pytest
import time
from typing import List, Tuple
from unittest.mock import MagicMock, patch, call

from hypothesis import given, strategies as st, settings, assume, HealthCheck
from PySide6.QtCore import Qt, QModelIndex


# 通用设置：允许 function-scoped fixture (qtbot)
# 这是安全的，因为每个测试都创建新的 model 实例
# 同时抑制 too_slow 检查，因为生成唯一 ID 列表需要一些时间
PROPERTY_TEST_SETTINGS = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)


# =====================================================
# =============== 测试策略定义 ===============
# =====================================================

# 生成有效的历史条目 ID（非空字符串，无特殊字符）
valid_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip() != '')

# 生成预览文本
preview_text_strategy = st.text(min_size=0, max_size=200)

# 生成时间戳字符串
timestamp_strategy = st.from_regex(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', fullmatch=True)

# 生成内容类型
content_type_strategy = st.sampled_from(['image', 'text'])


# 生成历史条目数据的策略
@st.composite
def history_item_strategy(draw):
    """生成 HistoryItemData 实例的策略"""
    from screenshot_tool.core.history_item_data import HistoryItemData
    
    return HistoryItemData(
        id=draw(valid_id_strategy),
        preview_text=draw(preview_text_strategy),
        timestamp=draw(timestamp_strategy),
        is_pinned=draw(st.booleans()),
        has_annotations=draw(st.booleans()),
        thumbnail_path=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        content_type=draw(content_type_strategy)
    )


# 生成唯一 ID 列表的策略
@st.composite
def unique_items_strategy(draw, min_count=1, max_count=20):
    """生成具有唯一 ID 的历史条目列表"""
    from screenshot_tool.core.history_item_data import HistoryItemData
    
    count = draw(st.integers(min_value=min_count, max_value=max_count))
    items = []
    used_ids = set()
    
    for i in range(count):
        # 使用索引确保 ID 唯一
        item_id = f"item-{i}-{draw(st.integers(min_value=0, max_value=9999))}"
        if item_id in used_ids:
            item_id = f"item-{i}-unique-{len(used_ids)}"
        used_ids.add(item_id)
        
        items.append(HistoryItemData(
            id=item_id,
            preview_text=draw(preview_text_strategy),
            timestamp=draw(timestamp_strategy),
            is_pinned=draw(st.booleans()),
            has_annotations=draw(st.booleans()),
            thumbnail_path=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
            content_type=draw(content_type_strategy)
        ))
    
    return items


# =====================================================
# =============== Property 17 测试类 ===============
# =====================================================

class TestHistoryListIncrementalUpdate:
    """Property 17: History List Incremental Update
    
    Feature: extreme-performance-optimization, Property 17: History List Incremental Update
    
    验证历史列表使用增量更新（beginInsertRows/endInsertRows）而非 clear() + rebuild。
    
    **Validates: Requirements 11.1, 11.2, 11.6**
    """
    
    @PROPERTY_TEST_SETTINGS
    @given(items=unique_items_strategy(min_count=1, max_count=15))
    def test_incremental_insert_uses_begin_end_insert_rows(self, items, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any history item addition, the list SHALL use beginInsertRows/endInsertRows
        for incremental update instead of clear() + rebuild.
        
        **Validates: Requirements 11.1, 11.2, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        # Track signal emissions
        rows_about_to_be_inserted_calls = []
        rows_inserted_calls = []
        model_reset_calls = []
        
        def on_rows_about_to_be_inserted(parent, first, last):
            rows_about_to_be_inserted_calls.append((first, last))
        
        def on_rows_inserted(parent, first, last):
            rows_inserted_calls.append((first, last))
        
        def on_model_reset():
            model_reset_calls.append(True)
        
        model.rowsAboutToBeInserted.connect(on_rows_about_to_be_inserted)
        model.rowsInserted.connect(on_rows_inserted)
        model.modelReset.connect(on_model_reset)
        
        # Add all items
        for item in items:
            model.add_item(item)
        
        # Force flush to trigger batch insert
        model.force_flush()
        
        # Property: beginInsertRows/endInsertRows should be called (not modelReset)
        assert len(rows_about_to_be_inserted_calls) == 1, \
            "Should call beginInsertRows exactly once for batch insert"
        assert len(rows_inserted_calls) == 1, \
            "Should call endInsertRows exactly once for batch insert"
        assert len(model_reset_calls) == 0, \
            "Should NOT use modelReset (clear+rebuild) for adding items"
        
        # Verify the insert range is correct
        first, last = rows_inserted_calls[0]
        assert first == 0, "Batch insert should start at index 0"
        assert last == len(items) - 1, f"Batch insert should end at index {len(items) - 1}"

    
    @PROPERTY_TEST_SETTINGS
    @given(
        first_batch=unique_items_strategy(min_count=1, max_count=10),
        second_batch_size=st.integers(min_value=1, max_value=10)
    )
    def test_multiple_batches_use_incremental_updates(self, first_batch, second_batch_size, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any sequence of batch additions, each batch SHALL use beginInsertRows/endInsertRows
        independently, never clearing and rebuilding the entire list.
        
        **Validates: Requirements 11.1, 11.2, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # Track signal emissions
        insert_calls = []
        reset_calls = []
        
        def on_rows_inserted(parent, first, last):
            insert_calls.append((first, last, model.rowCount()))
        
        def on_model_reset():
            reset_calls.append(True)
        
        model.rowsInserted.connect(on_rows_inserted)
        model.modelReset.connect(on_model_reset)
        
        # Add first batch
        for item in first_batch:
            model.add_item(item)
        model.force_flush()
        
        first_batch_count = len(first_batch)
        
        # Generate second batch with unique IDs
        second_batch = []
        for i in range(second_batch_size):
            second_batch.append(HistoryItemData(
                id=f"second-batch-{i}-{time.time_ns()}",
                preview_text=f"Second batch item {i}",
                timestamp="2025-01-15 12:00"
            ))
        
        # Add second batch
        for item in second_batch:
            model.add_item(item)
        model.force_flush()
        
        # Property: Should have exactly 2 insert calls (one per batch), no resets
        assert len(insert_calls) == 2, \
            f"Should have 2 insert calls for 2 batches, got {len(insert_calls)}"
        assert len(reset_calls) == 0, \
            "Should NOT use modelReset for batch additions"
        
        # Verify final count
        assert model.rowCount() == first_batch_count + second_batch_size

    
    @PROPERTY_TEST_SETTINGS
    @given(item_count=st.integers(min_value=1, max_value=20))
    def test_debounce_timer_batches_rapid_inserts(self, item_count, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any number of rapid item additions, the 100ms debounce timer SHALL batch
        all additions into a single UI update.
        
        **Validates: Requirements 11.1, 11.2, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # Verify debounce timer configuration
        assert model._update_timer.interval() == 100, \
            "Debounce timer should be 100ms"
        assert model._update_timer.isSingleShot(), \
            "Debounce timer should be single-shot"
        
        # Track insert signals
        insert_calls = []
        
        def on_rows_inserted(parent, first, last):
            insert_calls.append((first, last))
        
        model.rowsInserted.connect(on_rows_inserted)
        
        # Rapidly add items (simulating burst of history additions)
        for i in range(item_count):
            item = HistoryItemData(
                id=f"rapid-{i}-{time.time_ns()}",
                preview_text=f"Rapid item {i}",
                timestamp="2025-01-15 12:00"
            )
            model.add_item(item)
        
        # Before debounce timeout, items should be pending
        assert model.get_pending_count() == item_count, \
            f"All {item_count} items should be pending before flush"
        assert model.rowCount() == 0, \
            "No items should be in model before flush"
        assert len(insert_calls) == 0, \
            "No insert signals should be emitted before flush"
        
        # Force flush (simulates debounce timeout)
        model.force_flush()
        
        # Property: All items should be inserted in a single batch
        assert len(insert_calls) == 1, \
            f"Should have exactly 1 batch insert, got {len(insert_calls)}"
        assert model.rowCount() == item_count, \
            f"Model should have {item_count} items after flush"
        assert model.get_pending_count() == 0, \
            "No items should be pending after flush"

    
    @PROPERTY_TEST_SETTINGS
    @given(items=unique_items_strategy(min_count=2, max_count=15))
    def test_remove_uses_incremental_update_not_rebuild(self, items, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any item removal, the list SHALL use beginRemoveRows/endRemoveRows
        for incremental update instead of clear() + rebuild.
        
        **Validates: Requirements 11.1, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        # Add items first
        for item in items:
            model.add_item(item)
        model.force_flush()
        
        initial_count = model.rowCount()
        
        # Track signals for removal
        remove_calls = []
        reset_calls = []
        
        def on_rows_removed(parent, first, last):
            remove_calls.append((first, last))
        
        def on_model_reset():
            reset_calls.append(True)
        
        model.rowsRemoved.connect(on_rows_removed)
        model.modelReset.connect(on_model_reset)
        
        # Remove the first item
        item_to_remove = items[0]
        result = model.remove_item(item_to_remove.id)
        
        # Property: Should use beginRemoveRows/endRemoveRows, not modelReset
        assert result is True, "Remove should succeed"
        assert len(remove_calls) == 1, \
            "Should call beginRemoveRows/endRemoveRows exactly once"
        assert len(reset_calls) == 0, \
            "Should NOT use modelReset for removal"
        assert model.rowCount() == initial_count - 1, \
            "Row count should decrease by 1"

    
    @PROPERTY_TEST_SETTINGS
    @given(items=unique_items_strategy(min_count=1, max_count=15))
    def test_index_mapping_consistency_after_insert(self, items, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any batch insert, the internal id-to-index mapping SHALL remain consistent
        with the actual item positions in the list.
        
        **Validates: Requirements 11.1, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        # Add items
        for item in items:
            model.add_item(item)
        model.force_flush()
        
        # Property: Every item's index mapping should match its actual position
        for i, item in enumerate(items):
            # Get the mapped index
            mapped_index = model._id_to_index.get(item.id)
            assert mapped_index is not None, \
                f"Item {item.id} should have an index mapping"
            
            # Get the item at that index
            item_at_index = model.get_item_at(mapped_index)
            assert item_at_index is not None, \
                f"Should have item at mapped index {mapped_index}"
            assert item_at_index.id == item.id, \
                f"Item at index {mapped_index} should be {item.id}, got {item_at_index.id}"
        
        # Property: Index mapping count should match item count
        assert len(model._id_to_index) == len(items), \
            "Index mapping count should match item count"

    
    @PROPERTY_TEST_SETTINGS
    @given(
        first_batch=unique_items_strategy(min_count=2, max_count=8),
        second_batch_size=st.integers(min_value=1, max_value=8)
    )
    def test_index_mapping_updated_after_second_batch(self, first_batch, second_batch_size, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any second batch insert, existing items' index mappings SHALL be correctly
        shifted to accommodate new items inserted at the top.
        
        **Validates: Requirements 11.1, 11.2, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # Add first batch
        for item in first_batch:
            model.add_item(item)
        model.force_flush()
        
        first_batch_count = len(first_batch)
        
        # Record original indices
        original_indices = {item.id: model._id_to_index[item.id] for item in first_batch}
        
        # Generate and add second batch
        second_batch = []
        for i in range(second_batch_size):
            second_batch.append(HistoryItemData(
                id=f"second-{i}-{time.time_ns()}",
                preview_text=f"Second {i}",
                timestamp="2025-01-15 12:00"
            ))
            model.add_item(second_batch[-1])
        model.force_flush()
        
        # Property: First batch items should have indices shifted by second_batch_size
        for item in first_batch:
            old_index = original_indices[item.id]
            new_index = model._id_to_index[item.id]
            expected_new_index = old_index + second_batch_size
            assert new_index == expected_new_index, \
                f"Item {item.id} index should shift from {old_index} to {expected_new_index}, got {new_index}"
        
        # Property: Second batch items should be at indices 0 to second_batch_size-1
        for i, item in enumerate(second_batch):
            assert model._id_to_index[item.id] == i, \
                f"Second batch item {item.id} should be at index {i}"

    
    @PROPERTY_TEST_SETTINGS
    @given(items=unique_items_strategy(min_count=3, max_count=15))
    def test_no_clear_method_called_during_normal_operations(self, items, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any normal add/remove operations, the model SHALL NOT call clear() internally.
        Only explicit clear_all() should trigger a model reset.
        
        **Validates: Requirements 11.1, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        
        model = HistoryListModel()
        
        reset_calls = []
        
        def on_model_reset():
            reset_calls.append(True)
        
        model.modelReset.connect(on_model_reset)
        
        # Add items
        for item in items:
            model.add_item(item)
        model.force_flush()
        
        # Remove some items
        items_to_remove = items[:len(items) // 2]
        for item in items_to_remove:
            model.remove_item(item.id)
        
        # Property: No model reset should have occurred during add/remove
        assert len(reset_calls) == 0, \
            "Model reset should NOT be called during normal add/remove operations"
        
        # Now explicitly clear - this SHOULD trigger reset
        model.clear_all()
        
        assert len(reset_calls) == 1, \
            "Model reset should be called exactly once for clear_all()"

    
    @PROPERTY_TEST_SETTINGS
    @given(item_count=st.integers(min_value=1, max_value=50))
    def test_data_retrieval_after_incremental_insert(self, item_count, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any number of incrementally inserted items, data() SHALL return correct
        values for all valid indices.
        
        **Validates: Requirements 11.1, 11.6**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        from PySide6.QtCore import Qt
        
        model = HistoryListModel()
        
        # Generate and add items
        items = []
        for i in range(item_count):
            item = HistoryItemData(
                id=f"data-test-{i}",
                preview_text=f"Preview text {i}",
                timestamp=f"2025-01-15 {i:02d}:00"
            )
            items.append(item)
            model.add_item(item)
        model.force_flush()
        
        # Property: data() should return correct values for all indices
        for i in range(item_count):
            index = model.index(i, 0)
            
            # DisplayRole should return preview_text
            display_data = model.data(index, Qt.ItemDataRole.DisplayRole)
            assert display_data == items[i].preview_text, \
                f"DisplayRole at index {i} should be '{items[i].preview_text}'"
            
            # UserRole should return the full item
            user_data = model.data(index, Qt.ItemDataRole.UserRole)
            assert user_data is not None, f"UserRole at index {i} should not be None"
            assert user_data.id == items[i].id, \
                f"UserRole item id at index {i} should be '{items[i].id}'"



# =====================================================
# =============== 辅助测试 ===============
# =====================================================

class TestHistoryListModelDebounceProperty:
    """Debounce Timer Property Tests
    
    Additional property tests for the 100ms debounce mechanism.
    
    **Validates: Requirements 11.2**
    """
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(burst_count=st.integers(min_value=2, max_value=30))
    def test_debounce_resets_on_each_add(self, burst_count, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any burst of rapid additions, each add_item() call SHALL reset the debounce
        timer, ensuring all items in the burst are batched together.
        
        **Validates: Requirements 11.2**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # Add items rapidly
        for i in range(burst_count):
            item = HistoryItemData(
                id=f"burst-{i}-{time.time_ns()}",
                preview_text=f"Burst {i}",
                timestamp="2025-01-15 12:00"
            )
            model.add_item(item)
            
            # Timer should be active after each add
            assert model._update_timer.isActive(), \
                f"Timer should be active after adding item {i}"
        
        # All items should be pending
        assert model.get_pending_count() == burst_count, \
            f"All {burst_count} items should be pending"
    
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(item_count=st.integers(min_value=1, max_value=20))
    def test_force_flush_stops_timer(self, item_count, qtbot):
        """Feature: extreme-performance-optimization, Property 17: History List Incremental Update
        
        For any pending items, force_flush() SHALL stop the debounce timer and
        immediately process all pending items.
        
        **Validates: Requirements 11.2**
        """
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        model = HistoryListModel()
        
        # Add items
        for i in range(item_count):
            item = HistoryItemData(
                id=f"flush-{i}-{time.time_ns()}",
                preview_text=f"Flush {i}",
                timestamp="2025-01-15 12:00"
            )
            model.add_item(item)
        
        # Timer should be active
        assert model._update_timer.isActive(), "Timer should be active before flush"
        
        # Force flush
        model.force_flush()
        
        # Property: Timer should be stopped after force_flush
        assert not model._update_timer.isActive(), \
            "Timer should be stopped after force_flush"
        assert model.get_pending_count() == 0, \
            "No items should be pending after force_flush"
        assert model.rowCount() == item_count, \
            f"All {item_count} items should be in model after force_flush"
