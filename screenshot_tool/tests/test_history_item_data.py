# =====================================================
# =============== 历史条目数据类测试 ===============
# =====================================================

"""
测试 HistoryItemData 数据类

Feature: extreme-performance-optimization
Requirements: 11.1, 4.6
"""

import pytest
import sys
from typing import Any


class TestHistoryItemData:
    """HistoryItemData 单元测试"""
    
    def test_create_with_required_fields(self):
        """测试使用必需字段创建实例"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="test-123",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30"
        )
        
        assert item.id == "test-123"
        assert item.preview_text == "测试截图"
        assert item.timestamp == "2025-01-15 10:30"
        # 默认值
        assert item.is_pinned is False
        assert item.has_annotations is False
        assert item.thumbnail_path is None
        assert item.content_type == "image"
    
    def test_create_with_all_fields(self):
        """测试使用所有字段创建实例"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="test-456",
            preview_text="带标注的截图",
            timestamp="2025-01-15 11:00",
            is_pinned=True,
            has_annotations=True,
            thumbnail_path="/path/to/thumb.png",
            content_type="text"
        )
        
        assert item.id == "test-456"
        assert item.preview_text == "带标注的截图"
        assert item.timestamp == "2025-01-15 11:00"
        assert item.is_pinned is True
        assert item.has_annotations is True
        assert item.thumbnail_path == "/path/to/thumb.png"
        assert item.content_type == "text"
    
    def test_slots_defined(self):
        """测试 __slots__ 已定义（内存优化）
        
        **Validates: Requirements 4.6**
        """
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        # 验证 __slots__ 存在
        assert hasattr(HistoryItemData, '__slots__')
        
        # 验证所有必需的槽位
        expected_slots = {
            'id', 'preview_text', 'timestamp', 'is_pinned',
            'has_annotations', 'thumbnail_path', 'content_type'
        }
        actual_slots = set(HistoryItemData.__slots__)
        assert actual_slots == expected_slots
    
    def test_no_dict_attribute(self):
        """测试实例没有 __dict__（__slots__ 生效）
        
        **Validates: Requirements 4.6**
        """
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="test-789",
            preview_text="测试",
            timestamp="2025-01-15 12:00"
        )
        
        # 使用 __slots__ 的类实例不应该有 __dict__
        assert not hasattr(item, '__dict__')
    
    def test_memory_efficiency(self):
        """测试内存效率（__slots__ 比普通类更省内存）
        
        **Validates: Requirements 4.6**
        """
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="test-mem",
            preview_text="内存测试",
            timestamp="2025-01-15 13:00"
        )
        
        # 获取实例大小
        item_size = sys.getsizeof(item)
        
        # __slots__ 类的实例通常比普通类小
        # 普通类实例通常 > 100 字节（因为 __dict__）
        # __slots__ 类实例通常 < 100 字节
        assert item_size < 200  # 合理的上限
    
    def test_repr(self):
        """测试字符串表示"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="repr-test",
            preview_text="测试",
            timestamp="2025-01-15 14:00"
        )
        
        repr_str = repr(item)
        assert "HistoryItemData" in repr_str
        assert "repr-test" in repr_str
        assert "测试" in repr_str
    
    def test_equality_by_id(self):
        """测试基于 id 的相等性比较"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item1 = HistoryItemData(
            id="same-id",
            preview_text="文本1",
            timestamp="2025-01-15 15:00"
        )
        
        item2 = HistoryItemData(
            id="same-id",
            preview_text="文本2",  # 不同的文本
            timestamp="2025-01-15 16:00"  # 不同的时间
        )
        
        item3 = HistoryItemData(
            id="different-id",
            preview_text="文本1",
            timestamp="2025-01-15 15:00"
        )
        
        # 相同 id 应该相等
        assert item1 == item2
        # 不同 id 应该不相等
        assert item1 != item3
    
    def test_hash_by_id(self):
        """测试基于 id 的哈希值"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item1 = HistoryItemData(
            id="hash-test",
            preview_text="文本1",
            timestamp="2025-01-15 17:00"
        )
        
        item2 = HistoryItemData(
            id="hash-test",
            preview_text="文本2",
            timestamp="2025-01-15 18:00"
        )
        
        # 相同 id 应该有相同的哈希值
        assert hash(item1) == hash(item2)
        
        # 可以用作字典键或集合元素
        item_set = {item1}
        assert item2 in item_set
    
    def test_to_dict(self):
        """测试转换为字典"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="dict-test",
            preview_text="字典测试",
            timestamp="2025-01-15 19:00",
            is_pinned=True,
            has_annotations=True,
            thumbnail_path="/path/thumb.png",
            content_type="text"
        )
        
        d = item.to_dict()
        
        assert d['id'] == "dict-test"
        assert d['preview_text'] == "字典测试"
        assert d['timestamp'] == "2025-01-15 19:00"
        assert d['is_pinned'] is True
        assert d['has_annotations'] is True
        assert d['thumbnail_path'] == "/path/thumb.png"
        assert d['content_type'] == "text"
    
    def test_from_dict(self):
        """测试从字典创建实例"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        data = {
            'id': 'from-dict-test',
            'preview_text': '从字典创建',
            'timestamp': '2025-01-15 20:00',
            'is_pinned': True,
            'has_annotations': False,
            'thumbnail_path': '/path/to/thumb.png',
            'content_type': 'image'
        }
        
        item = HistoryItemData.from_dict(data)
        
        assert item.id == 'from-dict-test'
        assert item.preview_text == '从字典创建'
        assert item.timestamp == '2025-01-15 20:00'
        assert item.is_pinned is True
        assert item.has_annotations is False
        assert item.thumbnail_path == '/path/to/thumb.png'
        assert item.content_type == 'image'
    
    def test_from_dict_with_defaults(self):
        """测试从字典创建实例（使用默认值）"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        # 只包含必需字段
        data = {
            'id': 'minimal-dict',
            'preview_text': '最小字典',
            'timestamp': '2025-01-15 21:00'
        }
        
        item = HistoryItemData.from_dict(data)
        
        assert item.id == 'minimal-dict'
        assert item.preview_text == '最小字典'
        assert item.timestamp == '2025-01-15 21:00'
        # 默认值
        assert item.is_pinned is False
        assert item.has_annotations is False
        assert item.thumbnail_path is None
        assert item.content_type == 'image'
    
    def test_roundtrip_dict_conversion(self):
        """测试字典转换往返"""
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        original = HistoryItemData(
            id="roundtrip-test",
            preview_text="往返测试",
            timestamp="2025-01-15 22:00",
            is_pinned=True,
            has_annotations=True,
            thumbnail_path="/path/thumb.png",
            content_type="text"
        )
        
        # 转换为字典再转回来
        d = original.to_dict()
        restored = HistoryItemData.from_dict(d)
        
        # 应该相等
        assert original == restored
        assert original.preview_text == restored.preview_text
        assert original.timestamp == restored.timestamp
        assert original.is_pinned == restored.is_pinned
        assert original.has_annotations == restored.has_annotations
        assert original.thumbnail_path == restored.thumbnail_path
        assert original.content_type == restored.content_type
    
    def test_cannot_add_arbitrary_attributes(self):
        """测试不能添加任意属性（__slots__ 限制）
        
        **Validates: Requirements 4.6**
        """
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        item = HistoryItemData(
            id="attr-test",
            preview_text="属性测试",
            timestamp="2025-01-15 23:00"
        )
        
        # 尝试添加不在 __slots__ 中的属性应该失败
        with pytest.raises(AttributeError):
            item.arbitrary_attribute = "should fail"
