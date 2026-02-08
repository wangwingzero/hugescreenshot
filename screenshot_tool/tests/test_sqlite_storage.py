# -*- coding: utf-8 -*-
"""
SQLite 存储往返属性测试

Feature: workbench-temporary-preview-python
**Validates: Requirements 8.1, 8.6, 8.7**

Property 7: SQLite Storage Round-Trip
- 验证任何有效的 HistoryItem 存储到 SQLite 后再读取，数据保持一致
- 验证 OCR 缓存被正确保存和恢复
- 验证标注数据（JSON 序列化）往返一致

测试策略：
1. 使用 hypothesis 生成随机历史记录数据
2. 存储到 SQLite 数据库
3. 读取并验证数据一致性
4. 使用临时数据库避免污染生产数据
"""

import os
import tempfile
import shutil
from datetime import datetime
from typing import List, Optional, Tuple

import pytest
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.core.sqlite_history_storage import (
    SQLiteHistoryStorage,
    HistoryItem,
    ContentType,
)


# ============================================================================
# Hypothesis 策略定义
# ============================================================================

# 工具类型策略
tool_strategy = st.sampled_from(['rect', 'arrow', 'text', 'ellipse', 'line', 'pen'])

# 颜色策略 - 生成有效的 7 字符颜色字符串 (#RRGGBB)
color_strategy = st.from_regex(r'#[0-9A-Fa-f]{6}', fullmatch=True)

# 宽度策略
width_strategy = st.integers(min_value=1, max_value=20)

# 单个标注策略
annotation_strategy = st.fixed_dictionaries({
    'tool': tool_strategy,
    'color': color_strategy,
    'width': width_strategy,
})

# 标注列表策略
annotations_list_strategy = st.lists(annotation_strategy, min_size=0, max_size=10)

# 选区矩形策略 (x, y, width, height)
selection_rect_strategy = st.tuples(
    st.integers(min_value=0, max_value=10000),
    st.integers(min_value=0, max_value=10000),
    st.integers(min_value=1, max_value=5000),
    st.integers(min_value=1, max_value=5000),
)

# 文本内容策略 - 避免 NUL 字符（SQLite 不支持）
safe_text_strategy = st.text(
    min_size=0, 
    max_size=1000,
    alphabet=st.characters(blacklist_categories=['Cs'], blacklist_characters=['\x00'])
)

# OCR 缓存策略 - 较长文本
ocr_cache_strategy = st.text(
    min_size=0, 
    max_size=5000,
    alphabet=st.characters(blacklist_categories=['Cs'], blacklist_characters=['\x00'])
)

# 预览文本策略 - 非空文本
preview_text_strategy = st.text(
    min_size=1, 
    max_size=200,
    alphabet=st.characters(blacklist_categories=['Cs'], blacklist_characters=['\x00'])
)

# 自定义名称策略
custom_name_strategy = st.one_of(
    st.none(),
    st.text(
        min_size=1, 
        max_size=100,
        alphabet=st.characters(blacklist_categories=['Cs'], blacklist_characters=['\x00'])
    )
)

# 图片路径策略
image_path_strategy = st.one_of(
    st.none(),
    st.from_regex(r'[a-zA-Z0-9_/\\]+\.(png|jpg|jpeg)', fullmatch=True)
)


# ============================================================================
# 测试夹具和辅助函数
# ============================================================================

@pytest.fixture
def temp_storage():
    """创建临时 SQLite 存储实例
    
    使用临时目录，测试结束后自动清理。
    """
    temp_dir = tempfile.mkdtemp(prefix="sqlite_test_")
    storage = SQLiteHistoryStorage(data_dir=temp_dir)
    yield storage
    storage.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


class TempStorageContext:
    """临时存储上下文管理器
    
    用于 hypothesis 测试，每次调用创建新的临时存储。
    """
    
    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sqlite_test_")
        self.storage = SQLiteHistoryStorage(data_dir=self.temp_dir)
        return self.storage
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.storage.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        return False


# ============================================================================
# Property 7: SQLite Storage Round-Trip 属性测试
# ============================================================================

class TestSQLiteStorageRoundTrip:
    """SQLite 存储往返属性测试
    
    **Validates: Requirements 8.1, 8.6, 8.7**
    
    Property 7: SQLite Storage Round-Trip
    *For any* valid HistoryItem, storing to SQLite and retrieving 
    SHALL produce an equivalent item.
    """

    @settings(max_examples=10, deadline=None)
    @given(
        text_content=safe_text_strategy,
        ocr_cache=ocr_cache_strategy,
        annotations=annotations_list_strategy,
    )
    def test_text_item_round_trip(
        self, 
        text_content: str,
        ocr_cache: str,
        annotations: List[dict],
    ):
        """Property 7.1: 文本类型历史记录往返一致性
        
        **Validates: Requirements 8.1, 8.6, 8.7**
        
        *For any* text content, OCR cache, and annotations,
        storing and retrieving SHALL produce identical data.
        """
        with TempStorageContext() as storage:
            # 创建测试历史记录
            item_id = f"test_{datetime.now().timestamp()}"
            timestamp = datetime.now()
            
            item = HistoryItem(
                id=item_id,
                content_type=ContentType.TEXT,
                text_content=text_content,
                image_path=None,
                preview_text=text_content[:50] if text_content else "empty",
                timestamp=timestamp,
                is_pinned=False,
                custom_name=None,
                ocr_cache=ocr_cache if ocr_cache else None,
                ocr_cache_timestamp=timestamp if ocr_cache else None,
                annotations=annotations if annotations else None,
                selection_rect=None,
            )
            
            # 存储
            success = storage.add_item(item)
            assert success, "Failed to add item to storage"
            
            # 读取
            retrieved = storage.get_item(item_id)
            assert retrieved is not None, "Failed to retrieve item"
            
            # 验证核心字段
            assert retrieved.id == item.id
            assert retrieved.content_type == item.content_type
            assert retrieved.text_content == item.text_content
            assert retrieved.preview_text == item.preview_text
            
            # 验证 OCR 缓存 (Requirements 8.6)
            if ocr_cache:
                assert retrieved.ocr_cache == ocr_cache, \
                    f"OCR cache mismatch: expected {ocr_cache!r}, got {retrieved.ocr_cache!r}"
            else:
                assert retrieved.ocr_cache is None or retrieved.ocr_cache == ""
            
            # 验证标注数据 (Requirements 8.7)
            if annotations:
                assert retrieved.annotations == annotations, \
                    f"Annotations mismatch: expected {annotations}, got {retrieved.annotations}"
            else:
                assert retrieved.annotations is None or retrieved.annotations == []

    @settings(max_examples=10, deadline=None)
    @given(
        ocr_cache=ocr_cache_strategy,
        annotations=annotations_list_strategy,
        selection_rect=st.one_of(st.none(), selection_rect_strategy),
        is_pinned=st.booleans(),
        custom_name=custom_name_strategy,
    )
    def test_image_item_round_trip(
        self,
        ocr_cache: str,
        annotations: List[dict],
        selection_rect: Optional[Tuple[int, int, int, int]],
        is_pinned: bool,
        custom_name: Optional[str],
    ):
        """Property 7.2: 图片类型历史记录往返一致性
        
        **Validates: Requirements 8.1, 8.6, 8.7**
        
        *For any* image item with OCR cache, annotations, and selection rect,
        storing and retrieving SHALL produce identical data.
        """
        with TempStorageContext() as storage:
            item_id = f"img_{datetime.now().timestamp()}"
            timestamp = datetime.now()
            image_path = f"clipboard_images/{item_id}.png"
            
            item = HistoryItem(
                id=item_id,
                content_type=ContentType.IMAGE,
                text_content=None,
                image_path=image_path,
                preview_text="Screenshot",
                timestamp=timestamp,
                is_pinned=is_pinned,
                custom_name=custom_name,
                ocr_cache=ocr_cache if ocr_cache else None,
                ocr_cache_timestamp=timestamp if ocr_cache else None,
                annotations=annotations if annotations else None,
                selection_rect=selection_rect,
            )
            
            # 存储
            success = storage.add_item(item)
            assert success, "Failed to add image item"
            
            # 读取
            retrieved = storage.get_item(item_id)
            assert retrieved is not None, "Failed to retrieve image item"
            
            # 验证核心字段
            assert retrieved.id == item.id
            assert retrieved.content_type == ContentType.IMAGE
            assert retrieved.image_path == image_path
            assert retrieved.is_pinned == is_pinned
            assert retrieved.custom_name == custom_name
            
            # 验证 OCR 缓存 (Requirements 8.6)
            if ocr_cache:
                assert retrieved.ocr_cache == ocr_cache
            
            # 验证标注数据 (Requirements 8.7)
            if annotations:
                assert retrieved.annotations == annotations
            
            # 验证选区矩形
            if selection_rect:
                assert retrieved.selection_rect == selection_rect, \
                    f"Selection rect mismatch: expected {selection_rect}, got {retrieved.selection_rect}"

    @settings(max_examples=10, deadline=None)
    @given(
        annotations=st.lists(
            st.fixed_dictionaries({
                'tool': tool_strategy,
                'color': color_strategy,
                'width': width_strategy,
                'points': st.lists(
                    st.tuples(
                        st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False),
                        st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False)
                    ),
                    min_size=0,
                    max_size=20
                ),
            }),
            min_size=1,
            max_size=10
        )
    )
    def test_complex_annotations_round_trip(
        self,
        annotations: List[dict],
    ):
        """Property 7.3: 复杂标注数据 JSON 序列化往返一致性
        
        **Validates: Requirements 8.7**
        
        *For any* complex annotation structure with nested data,
        JSON serialization round-trip SHALL preserve all data.
        """
        with TempStorageContext() as storage:
            item_id = f"complex_{datetime.now().timestamp()}"
            timestamp = datetime.now()
            
            item = HistoryItem(
                id=item_id,
                content_type=ContentType.IMAGE,
                text_content=None,
                image_path="test.png",
                preview_text="Complex annotations test",
                timestamp=timestamp,
                annotations=annotations,
            )
            
            # 存储
            success = storage.add_item(item)
            assert success
            
            # 读取
            retrieved = storage.get_item(item_id)
            assert retrieved is not None
            
            # 验证标注数据完整性
            assert retrieved.annotations is not None
            assert len(retrieved.annotations) == len(annotations)
            
            for i, (orig, retr) in enumerate(zip(annotations, retrieved.annotations)):
                assert orig['tool'] == retr['tool'], f"Tool mismatch at index {i}"
                assert orig['color'] == retr['color'], f"Color mismatch at index {i}"
                assert orig['width'] == retr['width'], f"Width mismatch at index {i}"
                
                # 验证 points 数组
                if 'points' in orig:
                    assert 'points' in retr, f"Points missing at index {i}"
                    assert len(orig['points']) == len(retr['points']), \
                        f"Points length mismatch at index {i}"
                    
                    for j, (orig_pt, retr_pt) in enumerate(zip(orig['points'], retr['points'])):
                        # 浮点数比较使用近似相等
                        assert abs(orig_pt[0] - retr_pt[0]) < 1e-10, \
                            f"Point X mismatch at annotation {i}, point {j}"
                        assert abs(orig_pt[1] - retr_pt[1]) < 1e-10, \
                            f"Point Y mismatch at annotation {i}, point {j}"

    @settings(max_examples=10, deadline=None)
    @given(
        ocr_text=ocr_cache_strategy,
    )
    def test_ocr_cache_update_round_trip(
        self,
        ocr_text: str,
    ):
        """Property 7.4: OCR 缓存更新往返一致性
        
        **Validates: Requirements 8.6**
        
        *For any* OCR text, updating OCR cache and retrieving
        SHALL produce identical text.
        """
        with TempStorageContext() as storage:
            item_id = f"ocr_{datetime.now().timestamp()}"
            timestamp = datetime.now()
            
            # 创建没有 OCR 缓存的记录
            item = HistoryItem(
                id=item_id,
                content_type=ContentType.IMAGE,
                text_content=None,
                image_path="test.png",
                preview_text="OCR test",
                timestamp=timestamp,
                ocr_cache=None,
            )
            
            success = storage.add_item(item)
            assert success
            
            # 更新 OCR 缓存
            if ocr_text:
                update_success = storage.update_ocr_cache(item_id, ocr_text)
                assert update_success, "Failed to update OCR cache"
                
                # 读取并验证
                retrieved = storage.get_item(item_id)
                assert retrieved is not None
                assert retrieved.ocr_cache == ocr_text, \
                    f"OCR cache mismatch after update: expected {ocr_text!r}, got {retrieved.ocr_cache!r}"
                assert retrieved.ocr_cache_timestamp is not None

    @settings(max_examples=10, deadline=None)
    @given(
        items_data=st.lists(
            st.tuples(
                safe_text_strategy,
                ocr_cache_strategy,
                annotations_list_strategy,
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_multiple_items_round_trip(
        self,
        items_data: List[Tuple[str, str, List[dict]]],
    ):
        """Property 7.5: 多条记录批量往返一致性
        
        **Validates: Requirements 8.1, 8.6, 8.7**
        
        *For any* collection of items, storing all and retrieving all
        SHALL produce identical data for each item.
        """
        with TempStorageContext() as storage:
            created_ids = []
            base_time = datetime.now()
            
            # 批量创建
            for i, (text, ocr, annotations) in enumerate(items_data):
                item_id = f"batch_{base_time.timestamp()}_{i}"
                created_ids.append(item_id)
                
                item = HistoryItem(
                    id=item_id,
                    content_type=ContentType.TEXT,
                    text_content=text,
                    image_path=None,
                    preview_text=text[:50] if text else f"item_{i}",
                    timestamp=base_time,
                    ocr_cache=ocr if ocr else None,
                    annotations=annotations if annotations else None,
                )
                
                success = storage.add_item(item)
                assert success, f"Failed to add item {i}"
            
            # 批量验证
            for i, (item_id, (text, ocr, annotations)) in enumerate(zip(created_ids, items_data)):
                retrieved = storage.get_item(item_id)
                assert retrieved is not None, f"Failed to retrieve item {i}"
                assert retrieved.text_content == text
                
                if ocr:
                    assert retrieved.ocr_cache == ocr
                if annotations:
                    assert retrieved.annotations == annotations


class TestSQLiteStorageEdgeCases:
    """SQLite 存储边界情况测试
    
    **Validates: Requirements 8.1, 8.6, 8.7**
    
    测试特殊字符、空值、Unicode 等边界情况。
    """

    def test_empty_annotations_round_trip(self, temp_storage: SQLiteHistoryStorage):
        """测试空标注列表往返
        
        **Validates: Requirements 8.7**
        """
        item_id = f"empty_ann_{datetime.now().timestamp()}"
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path="test.png",
            preview_text="Empty annotations",
            timestamp=datetime.now(),
            annotations=[],
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        # 空列表可能被存储为 None 或 []
        assert retrieved.annotations is None or retrieved.annotations == []

    def test_unicode_text_round_trip(self, temp_storage: SQLiteHistoryStorage):
        """测试 Unicode 文本往返
        
        **Validates: Requirements 8.1, 8.6**
        """
        item_id = f"unicode_{datetime.now().timestamp()}"
        unicode_text = "中文测试 🎉 日本語 한국어 العربية"
        ocr_cache = "识别结果：这是一段中文 OCR 文本 📝"
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.TEXT,
            text_content=unicode_text,
            image_path=None,
            preview_text=unicode_text,
            timestamp=datetime.now(),
            ocr_cache=ocr_cache,
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        assert retrieved.text_content == unicode_text
        assert retrieved.ocr_cache == ocr_cache

    def test_special_characters_in_annotations(self, temp_storage: SQLiteHistoryStorage):
        """测试标注中的特殊字符
        
        **Validates: Requirements 8.7**
        """
        item_id = f"special_{datetime.now().timestamp()}"
        annotations = [
            {
                'tool': 'text',
                'color': '#FF0000',
                'width': 2,
                'text': 'Quote: "Hello" & <World>',
            },
            {
                'tool': 'rect',
                'color': '#00FF00',
                'width': 3,
                'label': "换行\n制表\t反斜杠\\",
            },
        ]
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path="test.png",
            preview_text="Special chars",
            timestamp=datetime.now(),
            annotations=annotations,
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        assert retrieved.annotations == annotations

    def test_none_values_round_trip(self, temp_storage: SQLiteHistoryStorage):
        """测试 None 值往返
        
        **Validates: Requirements 8.1**
        """
        item_id = f"none_{datetime.now().timestamp()}"
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.TEXT,
            text_content=None,
            image_path=None,
            preview_text="None values test",
            timestamp=datetime.now(),
            is_pinned=False,
            custom_name=None,
            ocr_cache=None,
            ocr_cache_timestamp=None,
            annotations=None,
            selection_rect=None,
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        assert retrieved.text_content is None
        assert retrieved.image_path is None
        assert retrieved.custom_name is None
        assert retrieved.ocr_cache is None
        assert retrieved.annotations is None
        assert retrieved.selection_rect is None

    def test_large_ocr_cache_round_trip(self, temp_storage: SQLiteHistoryStorage):
        """测试大型 OCR 缓存往返
        
        **Validates: Requirements 8.6**
        """
        item_id = f"large_ocr_{datetime.now().timestamp()}"
        # 生成约 100KB 的 OCR 文本
        large_ocr = "这是一段很长的 OCR 识别结果。" * 5000
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path="test.png",
            preview_text="Large OCR test",
            timestamp=datetime.now(),
            ocr_cache=large_ocr,
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        assert retrieved.ocr_cache == large_ocr
        assert len(retrieved.ocr_cache) == len(large_ocr)

    def test_selection_rect_boundary_values(self, temp_storage: SQLiteHistoryStorage):
        """测试选区矩形边界值
        
        **Validates: Requirements 8.1**
        """
        item_id = f"rect_{datetime.now().timestamp()}"
        # 测试大坐标值
        selection_rect = (0, 0, 7680, 4320)  # 8K 分辨率
        
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path="test.png",
            preview_text="Large rect",
            timestamp=datetime.now(),
            selection_rect=selection_rect,
        )
        
        assert temp_storage.add_item(item)
        retrieved = temp_storage.get_item(item_id)
        
        assert retrieved is not None
        assert retrieved.selection_rect == selection_rect


class TestSQLiteStorageUpdate:
    """SQLite 存储更新测试
    
    **Validates: Requirements 8.1**
    
    测试更新操作的往返一致性。
    """

    def test_update_preserves_all_fields(self, temp_storage: SQLiteHistoryStorage):
        """测试更新操作保留所有字段
        
        **Validates: Requirements 8.1, 8.6, 8.7**
        """
        item_id = f"update_{datetime.now().timestamp()}"
        timestamp = datetime.now()
        
        # 创建初始记录
        item = HistoryItem(
            id=item_id,
            content_type=ContentType.IMAGE,
            text_content=None,
            image_path="original.png",
            preview_text="Original",
            timestamp=timestamp,
            is_pinned=False,
            ocr_cache="Original OCR",
            annotations=[{'tool': 'rect', 'color': '#FF0000', 'width': 2}],
            selection_rect=(10, 20, 100, 200),
        )
        
        assert temp_storage.add_item(item)
        
        # 更新记录
        item.image_path = "updated.png"
        item.preview_text = "Updated"
        item.is_pinned = True
        item.ocr_cache = "Updated OCR"
        item.annotations = [{'tool': 'arrow', 'color': '#00FF00', 'width': 3}]
        item.selection_rect = (50, 60, 200, 300)
        
        assert temp_storage.update_item(item)
        
        # 验证更新
        retrieved = temp_storage.get_item(item_id)
        assert retrieved is not None
        assert retrieved.image_path == "updated.png"
        assert retrieved.preview_text == "Updated"
        assert retrieved.is_pinned == True
        assert retrieved.ocr_cache == "Updated OCR"
        assert retrieved.annotations == [{'tool': 'arrow', 'color': '#00FF00', 'width': 3}]
        assert retrieved.selection_rect == (50, 60, 200, 300)


# ============================================================================
# Property 8: JSON to SQLite Migration 属性测试
# ============================================================================

class TestJSONToSQLiteMigration:
    """JSON 到 SQLite 迁移测试
    
    **Validates: Requirements 8.2**
    
    Property 8: JSON to SQLite Migration
    *For any* existing JSON history file with valid items:
    - After migration, all items SHALL exist in SQLite database
    - Item data SHALL be preserved (id, content, timestamps, etc.)
    - The original JSON file SHALL be backed up
    """
    
    def _create_json_history_file(
        self, 
        json_path: str, 
        items: List[dict],
        version: int = 2
    ) -> None:
        """创建测试用的 JSON 历史文件
        
        Args:
            json_path: JSON 文件路径
            items: 历史记录列表
            version: JSON 格式版本
        """
        import json
        data = {
            "version": version,
            "max_items": 100,
            "items": items,
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def test_migrate_empty_json(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移空 JSON 文件
        
        **Validates: Requirements 8.2**
        """
        import json
        json_path = os.path.join(temp_storage._data_dir, "empty_history.json")
        
        # 创建空 JSON 文件
        self._create_json_history_file(json_path, [])
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.total_items == 0
        assert result.migrated_items == 0
        assert result.skipped_items == 0
        assert result.failed_items == 0
        
        # 验证备份文件存在
        assert os.path.exists(json_path + ".bak")
    
    def test_migrate_nonexistent_json(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移不存在的 JSON 文件
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "nonexistent.json")
        
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert "不存在" in result.message or "无需迁移" in result.message
        assert result.total_items == 0
    
    def test_migrate_single_text_item(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移单条文本记录
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "single_text.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "text_001",
            "content_type": "text",
            "text_content": "Hello, World!",
            "image_path": None,
            "preview_text": "Hello, World!",
            "timestamp": timestamp,
            "is_pinned": False,
        }]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.total_items == 1
        assert result.migrated_items == 1
        assert result.skipped_items == 0
        assert result.failed_items == 0
        
        # 验证数据已迁移到 SQLite
        retrieved = temp_storage.get_item("text_001")
        assert retrieved is not None
        assert retrieved.text_content == "Hello, World!"
        assert retrieved.content_type == ContentType.TEXT
    
    def test_migrate_single_image_item(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移单条图片记录
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "single_image.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "img_001",
            "content_type": "image",
            "text_content": None,
            "image_path": "clipboard_images/img_001.png",
            "preview_text": "[图片]",
            "timestamp": timestamp,
            "is_pinned": True,
            "ocr_cache": "识别的文字内容",
            "ocr_cache_timestamp": timestamp,
            "annotations": [{"tool": "rect", "color": "#FF0000", "width": 2}],
            "selection_rect": [100, 200, 300, 400],
        }]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.migrated_items == 1
        
        # 验证数据完整性
        retrieved = temp_storage.get_item("img_001")
        assert retrieved is not None
        assert retrieved.content_type == ContentType.IMAGE
        assert retrieved.image_path == "clipboard_images/img_001.png"
        assert retrieved.is_pinned == True
        assert retrieved.ocr_cache == "识别的文字内容"
        assert retrieved.annotations == [{"tool": "rect", "color": "#FF0000", "width": 2}]
        assert retrieved.selection_rect == (100, 200, 300, 400)
    
    def test_migrate_multiple_items(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移多条记录
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "multiple.json")
        timestamp = datetime.now().isoformat()
        
        items = [
            {
                "id": f"item_{i}",
                "content_type": "text",
                "text_content": f"Content {i}",
                "image_path": None,
                "preview_text": f"Content {i}",
                "timestamp": timestamp,
                "is_pinned": i % 2 == 0,
            }
            for i in range(10)
        ]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.total_items == 10
        assert result.migrated_items == 10
        assert result.skipped_items == 0
        
        # 验证所有记录都已迁移
        for i in range(10):
            retrieved = temp_storage.get_item(f"item_{i}")
            assert retrieved is not None
            assert retrieved.text_content == f"Content {i}"
            assert retrieved.is_pinned == (i % 2 == 0)
    
    def test_migrate_idempotent(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移幂等性 - 多次迁移不会重复插入
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "idempotent.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "idempotent_001",
            "content_type": "text",
            "text_content": "Idempotent test",
            "image_path": None,
            "preview_text": "Idempotent test",
            "timestamp": timestamp,
            "is_pinned": False,
        }]
        
        self._create_json_history_file(json_path, items)
        
        # 第一次迁移
        result1 = temp_storage.migrate_from_json(json_path)
        assert result1.success
        assert result1.migrated_items == 1
        
        # 重新创建 JSON 文件（模拟再次迁移）
        self._create_json_history_file(json_path, items)
        
        # 第二次迁移 - 应该跳过已存在的记录
        result2 = temp_storage.migrate_from_json(json_path)
        assert result2.success
        assert result2.migrated_items == 0
        assert result2.skipped_items == 1
        
        # 验证数据库中只有一条记录
        all_items = temp_storage.get_all_items()
        assert len(all_items) == 1
    
    def test_migrate_version_1_format(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移 version 1 格式（无标注数据）
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "v1_format.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "v1_001",
            "content_type": "text",
            "text_content": "Version 1 item",
            "image_path": None,
            "preview_text": "Version 1 item",
            "timestamp": timestamp,
            "is_pinned": False,
            # 没有 annotations 和 selection_rect 字段
        }]
        
        self._create_json_history_file(json_path, items, version=1)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.migrated_items == 1
        
        # 验证数据
        retrieved = temp_storage.get_item("v1_001")
        assert retrieved is not None
        assert retrieved.text_content == "Version 1 item"
        assert retrieved.annotations is None
        assert retrieved.selection_rect is None
    
    def test_migrate_unicode_content(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移 Unicode 内容
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "unicode.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "unicode_001",
            "content_type": "text",
            "text_content": "中文测试 🎉 日本語 한국어",
            "image_path": None,
            "preview_text": "中文测试 🎉",
            "timestamp": timestamp,
            "is_pinned": False,
            "ocr_cache": "OCR 识别结果：这是中文 📝",
        }]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        
        # 验证 Unicode 数据完整性
        retrieved = temp_storage.get_item("unicode_001")
        assert retrieved is not None
        assert retrieved.text_content == "中文测试 🎉 日本語 한국어"
        assert retrieved.ocr_cache == "OCR 识别结果：这是中文 📝"
    
    def test_migrate_invalid_json(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移无效 JSON 文件
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "invalid.json")
        
        # 创建无效 JSON 文件
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json content")
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert not result.success
        assert "格式错误" in result.message or "JSON" in result.message
    
    def test_migrate_partial_invalid_items(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移包含部分无效记录的 JSON
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "partial_invalid.json")
        timestamp = datetime.now().isoformat()
        
        items = [
            # 有效记录
            {
                "id": "valid_001",
                "content_type": "text",
                "text_content": "Valid item",
                "image_path": None,
                "preview_text": "Valid item",
                "timestamp": timestamp,
                "is_pinned": False,
            },
            # 无效记录 - 缺少必需字段
            {
                "id": "invalid_001",
                # 缺少 content_type
                "text_content": "Invalid item",
            },
            # 另一个有效记录
            {
                "id": "valid_002",
                "content_type": "text",
                "text_content": "Another valid item",
                "image_path": None,
                "preview_text": "Another valid",
                "timestamp": timestamp,
                "is_pinned": True,
            },
        ]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        # 应该部分成功
        assert result.migrated_items == 2
        assert result.failed_items == 1
        
        # 验证有效记录已迁移
        assert temp_storage.get_item("valid_001") is not None
        assert temp_storage.get_item("valid_002") is not None
        assert temp_storage.get_item("invalid_001") is None
    
    def test_migrate_backup_file_created(self, temp_storage: SQLiteHistoryStorage):
        """测试迁移后备份文件被创建
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "backup_test.json")
        timestamp = datetime.now().isoformat()
        
        items = [{
            "id": "backup_001",
            "content_type": "text",
            "text_content": "Backup test",
            "image_path": None,
            "preview_text": "Backup test",
            "timestamp": timestamp,
            "is_pinned": False,
        }]
        
        self._create_json_history_file(json_path, items)
        
        # 执行迁移
        result = temp_storage.migrate_from_json(json_path)
        
        assert result.success
        assert result.backup_path is not None
        assert os.path.exists(result.backup_path)
        
        # 原文件应该被重命名（不存在）
        assert not os.path.exists(json_path)
    
    def test_migrate_check_needed(self, temp_storage: SQLiteHistoryStorage):
        """测试检查是否需要迁移
        
        **Validates: Requirements 8.2**
        """
        json_path = os.path.join(temp_storage._data_dir, "check_test.json")
        
        # 文件不存在时
        assert not temp_storage.check_migration_needed(json_path)
        
        # 创建文件后
        self._create_json_history_file(json_path, [])
        assert temp_storage.check_migration_needed(json_path)


# ============================================================================
# Property 8: JSON to SQLite Migration 属性测试 (Property-Based)
# ============================================================================

class TestJSONToSQLiteMigrationProperty:
    """JSON 到 SQLite 迁移属性测试 (Property-Based)
    
    **Validates: Requirements 8.2**
    
    Property 8: JSON to SQLite Migration
    *For any* existing JSON history file with valid items:
    - After migration, all items SHALL exist in SQLite database
    - Item data SHALL be preserved (id, content, timestamps, etc.)
    - The original JSON file SHALL be backed up or removed
    
    使用 hypothesis 生成随机 JSON 历史数据，验证迁移后数据完整性。
    """
    
    @settings(max_examples=10, deadline=None)
    @given(
        items_data=st.lists(
            st.fixed_dictionaries({
                'id': st.text(
                    min_size=1, 
                    max_size=50,
                    alphabet=st.characters(
                        whitelist_categories=['L', 'N'],
                        whitelist_characters=['_', '-']
                    )
                ),
                'content_type': st.sampled_from(['text', 'image']),
                'text_content': st.one_of(
                    st.none(),
                    safe_text_strategy
                ),
                'image_path': st.one_of(
                    st.none(),
                    st.from_regex(r'clipboard_images/[a-zA-Z0-9_]+\.png', fullmatch=True)
                ),
                'preview_text': preview_text_strategy,
                'is_pinned': st.booleans(),
                'custom_name': custom_name_strategy,
                'ocr_cache': st.one_of(st.none(), ocr_cache_strategy),
                'annotations': st.one_of(st.none(), annotations_list_strategy),
                'selection_rect': st.one_of(
                    st.none(),
                    st.lists(
                        st.integers(min_value=0, max_value=10000),
                        min_size=4,
                        max_size=4
                    )
                ),
            }),
            min_size=1,
            max_size=20,
            unique_by=lambda x: x['id']  # 确保 ID 唯一
        )
    )
    def test_json_migration_preserves_all_data(
        self,
        items_data: List[dict],
    ):
        """Property 8: JSON 到 SQLite 迁移保留所有数据
        
        **Validates: Requirements 8.2**
        
        *For any* existing JSON history file with valid items,
        after migration all items SHALL exist in SQLite database
        with preserved data.
        """
        with TempStorageContext() as storage:
            # 1. 准备 JSON 历史文件
            json_path = os.path.join(storage._data_dir, "test_history.json")
            timestamp = datetime.now()
            
            # 为每条记录添加时间戳
            prepared_items = []
            for item in items_data:
                prepared_item = item.copy()
                prepared_item['timestamp'] = timestamp.isoformat()
                
                # 如果有 OCR 缓存，添加 OCR 时间戳
                if prepared_item.get('ocr_cache'):
                    prepared_item['ocr_cache_timestamp'] = timestamp.isoformat()
                
                prepared_items.append(prepared_item)
            
            # 创建 JSON 文件
            import json
            json_data = {
                "version": 2,
                "max_items": 100,
                "items": prepared_items,
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # 2. 执行迁移
            result = storage.migrate_from_json(json_path)
            
            # 3. 验证迁移成功
            assert result.success, f"Migration failed: {result.message}, errors: {result.errors}"
            assert result.total_items == len(prepared_items), \
                f"Total items mismatch: expected {len(prepared_items)}, got {result.total_items}"
            assert result.migrated_items == len(prepared_items), \
                f"Migrated items mismatch: expected {len(prepared_items)}, got {result.migrated_items}"
            assert result.failed_items == 0, \
                f"Some items failed to migrate: {result.errors}"
            
            # 4. 验证所有数据已迁移到 SQLite
            for original_item in prepared_items:
                item_id = original_item['id']
                retrieved = storage.get_item(item_id)
                
                # 验证记录存在
                assert retrieved is not None, \
                    f"Item {item_id} not found in SQLite after migration"
                
                # 验证核心字段
                assert retrieved.id == original_item['id'], \
                    f"ID mismatch for {item_id}"
                assert retrieved.content_type.value == original_item['content_type'], \
                    f"Content type mismatch for {item_id}"
                assert retrieved.preview_text == original_item['preview_text'], \
                    f"Preview text mismatch for {item_id}"
                assert retrieved.is_pinned == original_item['is_pinned'], \
                    f"Is pinned mismatch for {item_id}"
                
                # 验证可选字段
                if original_item.get('text_content'):
                    assert retrieved.text_content == original_item['text_content'], \
                        f"Text content mismatch for {item_id}"
                
                if original_item.get('image_path'):
                    assert retrieved.image_path == original_item['image_path'], \
                        f"Image path mismatch for {item_id}"
                
                if original_item.get('custom_name'):
                    assert retrieved.custom_name == original_item['custom_name'], \
                        f"Custom name mismatch for {item_id}"
                
                # 验证 OCR 缓存 (Requirements 8.6)
                if original_item.get('ocr_cache'):
                    assert retrieved.ocr_cache == original_item['ocr_cache'], \
                        f"OCR cache mismatch for {item_id}"
                
                # 验证标注数据 (Requirements 8.7)
                if original_item.get('annotations'):
                    assert retrieved.annotations == original_item['annotations'], \
                        f"Annotations mismatch for {item_id}"
                
                # 验证选区矩形
                if original_item.get('selection_rect'):
                    expected_rect = tuple(original_item['selection_rect'])
                    assert retrieved.selection_rect == expected_rect, \
                        f"Selection rect mismatch for {item_id}: expected {expected_rect}, got {retrieved.selection_rect}"
            
            # 5. 验证备份文件存在
            assert result.backup_path is not None, "Backup path should not be None"
            assert os.path.exists(result.backup_path), \
                f"Backup file not found at {result.backup_path}"
            
            # 6. 验证原 JSON 文件已被移除（重命名为备份）
            assert not os.path.exists(json_path), \
                "Original JSON file should be removed after migration"
    
    @settings(max_examples=10, deadline=None)
    @given(
        items_data=st.lists(
            st.fixed_dictionaries({
                'id': st.text(
                    min_size=1, 
                    max_size=30,
                    alphabet=st.characters(
                        whitelist_categories=['L', 'N'],
                        whitelist_characters=['_', '-']
                    )
                ),
                'content_type': st.just('image'),
                'text_content': st.none(),
                'image_path': st.from_regex(r'clipboard_images/[a-zA-Z0-9_]+\.png', fullmatch=True),
                'preview_text': st.just('[图片]'),
                'is_pinned': st.booleans(),
                'ocr_cache': ocr_cache_strategy,
                'annotations': st.lists(
                    st.fixed_dictionaries({
                        'tool': tool_strategy,
                        'color': color_strategy,
                        'width': width_strategy,
                        'points': st.lists(
                            st.tuples(
                                st.floats(min_value=0, max_value=5000, allow_nan=False, allow_infinity=False),
                                st.floats(min_value=0, max_value=5000, allow_nan=False, allow_infinity=False)
                            ),
                            min_size=0,
                            max_size=10
                        ),
                    }),
                    min_size=1,
                    max_size=5
                ),
                'selection_rect': st.lists(
                    st.integers(min_value=0, max_value=10000),
                    min_size=4,
                    max_size=4
                ),
            }),
            min_size=1,
            max_size=10,
            unique_by=lambda x: x['id']
        )
    )
    def test_json_migration_preserves_complex_image_items(
        self,
        items_data: List[dict],
    ):
        """Property 8.2: 复杂图片记录迁移保留所有数据
        
        **Validates: Requirements 8.2**
        
        *For any* image items with OCR cache, annotations with points,
        and selection rect, migration SHALL preserve all nested data.
        """
        with TempStorageContext() as storage:
            json_path = os.path.join(storage._data_dir, "complex_images.json")
            timestamp = datetime.now()
            
            # 准备数据
            prepared_items = []
            for item in items_data:
                prepared_item = item.copy()
                prepared_item['timestamp'] = timestamp.isoformat()
                if prepared_item.get('ocr_cache'):
                    prepared_item['ocr_cache_timestamp'] = timestamp.isoformat()
                prepared_items.append(prepared_item)
            
            # 创建 JSON 文件
            import json
            json_data = {
                "version": 2,
                "max_items": 100,
                "items": prepared_items,
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # 执行迁移
            result = storage.migrate_from_json(json_path)
            
            # 验证迁移成功
            assert result.success, f"Migration failed: {result.message}"
            assert result.migrated_items == len(prepared_items)
            
            # 验证复杂数据完整性
            for original_item in prepared_items:
                item_id = original_item['id']
                retrieved = storage.get_item(item_id)
                
                assert retrieved is not None, f"Item {item_id} not found"
                
                # 验证标注数据（包括 points）
                if original_item.get('annotations'):
                    assert retrieved.annotations is not None
                    assert len(retrieved.annotations) == len(original_item['annotations'])
                    
                    for i, (orig_ann, retr_ann) in enumerate(
                        zip(original_item['annotations'], retrieved.annotations)
                    ):
                        assert orig_ann['tool'] == retr_ann['tool']
                        assert orig_ann['color'] == retr_ann['color']
                        assert orig_ann['width'] == retr_ann['width']
                        
                        # 验证 points 数组
                        if 'points' in orig_ann:
                            assert 'points' in retr_ann
                            assert len(orig_ann['points']) == len(retr_ann['points'])
                            
                            for j, (orig_pt, retr_pt) in enumerate(
                                zip(orig_ann['points'], retr_ann['points'])
                            ):
                                # 浮点数比较
                                assert abs(orig_pt[0] - retr_pt[0]) < 1e-6, \
                                    f"Point X mismatch at ann {i}, pt {j}"
                                assert abs(orig_pt[1] - retr_pt[1]) < 1e-6, \
                                    f"Point Y mismatch at ann {i}, pt {j}"
    
    @settings(max_examples=10, deadline=None)
    @given(
        items_data=st.lists(
            st.fixed_dictionaries({
                'id': st.text(
                    min_size=1, 
                    max_size=30,
                    alphabet=st.characters(
                        whitelist_categories=['L', 'N'],
                        whitelist_characters=['_', '-']
                    )
                ),
                'content_type': st.just('text'),
                'text_content': st.text(
                    min_size=1,
                    max_size=500,
                    alphabet=st.characters(
                        whitelist_categories=['L', 'N', 'P', 'S', 'Z'],
                        blacklist_characters=['\x00']
                    )
                ),
                'image_path': st.none(),
                'preview_text': preview_text_strategy,
                'is_pinned': st.booleans(),
            }),
            min_size=1,
            max_size=15,
            unique_by=lambda x: x['id']
        )
    )
    def test_json_migration_idempotent(
        self,
        items_data: List[dict],
    ):
        """Property 8.3: 迁移幂等性
        
        **Validates: Requirements 8.2**
        
        *For any* JSON history file, running migration twice
        SHALL NOT create duplicate records.
        """
        with TempStorageContext() as storage:
            json_path = os.path.join(storage._data_dir, "idempotent.json")
            timestamp = datetime.now()
            
            # 准备数据
            prepared_items = []
            for item in items_data:
                prepared_item = item.copy()
                prepared_item['timestamp'] = timestamp.isoformat()
                prepared_items.append(prepared_item)
            
            # 创建 JSON 文件
            import json
            json_data = {
                "version": 2,
                "max_items": 100,
                "items": prepared_items,
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # 第一次迁移
            result1 = storage.migrate_from_json(json_path)
            assert result1.success
            assert result1.migrated_items == len(prepared_items)
            
            # 重新创建 JSON 文件（模拟再次迁移场景）
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # 第二次迁移
            result2 = storage.migrate_from_json(json_path)
            assert result2.success
            assert result2.migrated_items == 0, \
                f"Second migration should not add new items, but added {result2.migrated_items}"
            assert result2.skipped_items == len(prepared_items), \
                f"All items should be skipped, but only {result2.skipped_items} were skipped"
            
            # 验证数据库中记录数量正确
            all_items = storage.get_all_items(limit=1000)
            assert len(all_items) == len(prepared_items), \
                f"Database should have {len(prepared_items)} items, but has {len(all_items)}"


# ============================================================================
# Property 9: Pagination Returns Correct Subset 属性测试
# ============================================================================

class TestPaginationReturnsCorrectSubset:
    """分页返回正确子集属性测试
    
    **Validates: Requirements 8.3**
    
    Property 9: Pagination Returns Correct Subset
    *For any* history with N items and pagination parameters (offset, limit):
    - `get_all_items(offset, limit)` SHALL return at most `limit` items
    - The returned items SHALL be sorted by timestamp descending
    - The returned items SHALL start from position `offset`
    """

    @settings(max_examples=10, deadline=None)
    @given(
        num_items=st.integers(min_value=1, max_value=50),
        offset=st.integers(min_value=0, max_value=100),
        limit=st.integers(min_value=1, max_value=50),
    )
    def test_pagination_returns_correct_subset(
        self,
        num_items: int,
        offset: int,
        limit: int,
    ):
        """Property 9: Pagination Returns Correct Subset
        
        **Validates: Requirements 8.3**
        
        *For any* history with N items and pagination parameters,
        get_all_items(offset, limit) SHALL return the correct subset.
        """
        with TempStorageContext() as storage:
            # 1. Create N items with known timestamps (descending order)
            # Use distinct timestamps to ensure deterministic ordering
            base_timestamp = datetime(2025, 1, 1, 12, 0, 0)
            created_items = []
            
            for i in range(num_items):
                # Create items with timestamps in ascending order
                # So item 0 has earliest timestamp, item N-1 has latest
                item_timestamp = datetime(
                    2025, 1, 1, 12, 0, 0, 
                    microsecond=i * 1000  # Ensure unique timestamps
                )
                item_id = f"pagination_test_{i:04d}"
                
                item = HistoryItem(
                    id=item_id,
                    content_type=ContentType.TEXT,
                    text_content=f"Content {i}",
                    image_path=None,
                    preview_text=f"Preview {i}",
                    timestamp=item_timestamp,
                    is_pinned=False,
                )
                
                success = storage.add_item(item)
                assert success, f"Failed to add item {i}"
                created_items.append(item)
            
            # 2. Query with offset and limit
            result = storage.get_all_items(offset=offset, limit=limit)
            
            # 3. Verify returned count <= limit
            assert len(result) <= limit, \
                f"Returned {len(result)} items, but limit is {limit}"
            
            # 4. Calculate expected count
            # Items are sorted by timestamp descending, so newest first
            # Expected items: from position `offset` to `offset + limit - 1`
            expected_count = max(0, min(limit, num_items - offset))
            assert len(result) == expected_count, \
                f"Expected {expected_count} items (num_items={num_items}, offset={offset}, limit={limit}), got {len(result)}"
            
            # 5. Verify items are sorted by timestamp descending
            if len(result) > 1:
                for i in range(len(result) - 1):
                    assert result[i].timestamp >= result[i + 1].timestamp, \
                        f"Items not sorted by timestamp descending at index {i}: " \
                        f"{result[i].timestamp} < {result[i + 1].timestamp}"
            
            # 6. Verify items start from correct position
            # Since items are sorted descending, the first item at offset 0
            # should be the item with the latest timestamp (index num_items - 1)
            if len(result) > 0 and offset < num_items:
                # The item at position `offset` in descending order
                # corresponds to item index (num_items - 1 - offset) in our created list
                expected_first_index = num_items - 1 - offset
                expected_first_id = f"pagination_test_{expected_first_index:04d}"
                
                assert result[0].id == expected_first_id, \
                    f"First item should be {expected_first_id}, got {result[0].id}"
                
                # Verify all returned items are in correct order
                for i, item in enumerate(result):
                    expected_index = num_items - 1 - offset - i
                    expected_id = f"pagination_test_{expected_index:04d}"
                    assert item.id == expected_id, \
                        f"Item at position {i} should be {expected_id}, got {item.id}"

    @settings(max_examples=10, deadline=None)
    @given(
        num_items=st.integers(min_value=1, max_value=30),
        page_size=st.integers(min_value=1, max_value=20),
    )
    def test_pagination_covers_all_items(
        self,
        num_items: int,
        page_size: int,
    ):
        """Property 9.2: 分页遍历覆盖所有记录
        
        **Validates: Requirements 8.3**
        
        *For any* history with N items and page size P,
        iterating through all pages SHALL return all N items exactly once.
        """
        with TempStorageContext() as storage:
            # 1. Create N items
            base_timestamp = datetime(2025, 1, 1, 12, 0, 0)
            all_ids = set()
            
            for i in range(num_items):
                item_timestamp = datetime(
                    2025, 1, 1, 12, 0, 0,
                    microsecond=i * 1000
                )
                item_id = f"page_cover_{i:04d}"
                all_ids.add(item_id)
                
                item = HistoryItem(
                    id=item_id,
                    content_type=ContentType.TEXT,
                    text_content=f"Content {i}",
                    image_path=None,
                    preview_text=f"Preview {i}",
                    timestamp=item_timestamp,
                    is_pinned=False,
                )
                
                success = storage.add_item(item)
                assert success
            
            # 2. Iterate through all pages
            collected_ids = set()
            offset = 0
            total_pages = 0
            max_pages = (num_items // page_size) + 2  # Safety limit
            
            while total_pages < max_pages:
                page = storage.get_all_items(offset=offset, limit=page_size)
                
                if not page:
                    break
                
                for item in page:
                    # Verify no duplicates
                    assert item.id not in collected_ids, \
                        f"Duplicate item {item.id} found in pagination"
                    collected_ids.add(item.id)
                
                offset += page_size
                total_pages += 1
            
            # 3. Verify all items were collected
            assert collected_ids == all_ids, \
                f"Missing items: {all_ids - collected_ids}, Extra items: {collected_ids - all_ids}"

    @settings(max_examples=10, deadline=None)
    @given(
        num_items=st.integers(min_value=5, max_value=30),
    )
    def test_pagination_offset_beyond_total(
        self,
        num_items: int,
    ):
        """Property 9.3: 偏移量超出总数返回空列表
        
        **Validates: Requirements 8.3**
        
        *For any* history with N items, when offset >= N,
        get_all_items SHALL return an empty list.
        """
        with TempStorageContext() as storage:
            # 1. Create N items
            for i in range(num_items):
                item = HistoryItem(
                    id=f"offset_test_{i:04d}",
                    content_type=ContentType.TEXT,
                    text_content=f"Content {i}",
                    image_path=None,
                    preview_text=f"Preview {i}",
                    timestamp=datetime(2025, 1, 1, 12, 0, 0, microsecond=i * 1000),
                    is_pinned=False,
                )
                storage.add_item(item)
            
            # 2. Query with offset >= num_items
            result_at_boundary = storage.get_all_items(offset=num_items, limit=10)
            assert len(result_at_boundary) == 0, \
                f"Expected empty list when offset={num_items}, got {len(result_at_boundary)} items"
            
            result_beyond = storage.get_all_items(offset=num_items + 10, limit=10)
            assert len(result_beyond) == 0, \
                f"Expected empty list when offset={num_items + 10}, got {len(result_beyond)} items"

    @settings(max_examples=10, deadline=None)
    @given(
        num_items=st.integers(min_value=1, max_value=50),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_pagination_limit_larger_than_total(
        self,
        num_items: int,
        limit: int,
    ):
        """Property 9.4: limit 大于总数时返回所有记录
        
        **Validates: Requirements 8.3**
        
        *For any* history with N items and limit > N,
        get_all_items(offset=0, limit) SHALL return exactly N items.
        """
        # Only test when limit > num_items
        assume(limit > num_items)
        
        with TempStorageContext() as storage:
            # 1. Create N items
            for i in range(num_items):
                item = HistoryItem(
                    id=f"limit_test_{i:04d}",
                    content_type=ContentType.TEXT,
                    text_content=f"Content {i}",
                    image_path=None,
                    preview_text=f"Preview {i}",
                    timestamp=datetime(2025, 1, 1, 12, 0, 0, microsecond=i * 1000),
                    is_pinned=False,
                )
                storage.add_item(item)
            
            # 2. Query with limit > num_items
            result = storage.get_all_items(offset=0, limit=limit)
            
            # 3. Verify returns exactly num_items
            assert len(result) == num_items, \
                f"Expected {num_items} items when limit={limit}, got {len(result)}"

    @settings(max_examples=10, deadline=None)
    @given(
        num_items=st.integers(min_value=10, max_value=50),
        offset=st.integers(min_value=0, max_value=40),
        limit=st.integers(min_value=1, max_value=20),
    )
    def test_pagination_timestamp_ordering_preserved(
        self,
        num_items: int,
        offset: int,
        limit: int,
    ):
        """Property 9.5: 分页保持时间戳降序排列
        
        **Validates: Requirements 8.3**
        
        *For any* pagination query, returned items SHALL be
        strictly sorted by timestamp in descending order.
        """
        with TempStorageContext() as storage:
            # 1. Create N items with random-ish timestamps
            # (but still unique and deterministic based on index)
            import random
            random.seed(42)  # Deterministic for reproducibility
            
            timestamps = []
            for i in range(num_items):
                # Create timestamps with some variation
                ts = datetime(
                    2025, 1, 1 + (i % 28), 
                    (i * 7) % 24, 
                    (i * 13) % 60, 
                    (i * 17) % 60,
                    microsecond=(i * 1234) % 1000000
                )
                timestamps.append((i, ts))
            
            # Sort by timestamp to know expected order
            timestamps.sort(key=lambda x: x[1], reverse=True)
            
            # Create items
            for i in range(num_items):
                item = HistoryItem(
                    id=f"ts_order_{i:04d}",
                    content_type=ContentType.TEXT,
                    text_content=f"Content {i}",
                    image_path=None,
                    preview_text=f"Preview {i}",
                    timestamp=datetime(
                        2025, 1, 1 + (i % 28),
                        (i * 7) % 24,
                        (i * 13) % 60,
                        (i * 17) % 60,
                        microsecond=(i * 1234) % 1000000
                    ),
                    is_pinned=False,
                )
                storage.add_item(item)
            
            # 2. Query with pagination
            result = storage.get_all_items(offset=offset, limit=limit)
            
            # 3. Verify timestamp ordering
            if len(result) > 1:
                for i in range(len(result) - 1):
                    assert result[i].timestamp >= result[i + 1].timestamp, \
                        f"Timestamp ordering violated at index {i}: " \
                        f"{result[i].timestamp} < {result[i + 1].timestamp}"


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
