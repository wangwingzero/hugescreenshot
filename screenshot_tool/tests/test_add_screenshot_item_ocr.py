# -*- coding: utf-8 -*-
"""
add_screenshot_item 方法 OCR 缓存测试

Feature: workbench-temporary-preview-python
**Validates: Requirements 8.6, 8.7**

测试 add_screenshot_item 方法支持 ocr_cache 参数，
并验证 OCR 缓存正确存储到 SQLite 数据库。
"""

import os
import tempfile
import shutil
from datetime import datetime
from typing import List, Optional

import pytest
from hypothesis import given, strategies as st, settings, assume
from PySide6.QtGui import QImage, QColor

from screenshot_tool.core.clipboard_history_manager import (
    ClipboardHistoryManager,
    ContentType,
    HistoryItem,
    get_clipboard_data_dir,
)


# ============================================================================
# 测试夹具
# ============================================================================

@pytest.fixture
def temp_data_dir(monkeypatch):
    """创建临时数据目录"""
    temp_dir = tempfile.mkdtemp(prefix="ocr_test_")
    monkeypatch.setattr(
        'screenshot_tool.core.clipboard_history_manager.get_clipboard_data_dir',
        lambda: temp_dir
    )
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def manager(temp_data_dir):
    """创建测试用的管理器实例"""
    return ClipboardHistoryManager(max_items=100)


def create_test_image(width: int = 100, height: int = 100, color: QColor = None) -> QImage:
    """创建测试用的 QImage
    
    Args:
        width: 图像宽度
        height: 图像高度
        color: 填充颜色，默认为红色
        
    Returns:
        QImage 实例
    """
    if color is None:
        color = QColor(255, 0, 0)  # 红色
    
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


# ============================================================================
# 单元测试：add_screenshot_item 支持 ocr_cache
# ============================================================================

class TestAddScreenshotItemOCRCache:
    """add_screenshot_item 方法 OCR 缓存测试
    
    **Validates: Requirements 8.6, 8.7**
    
    测试 add_screenshot_item 方法正确处理 ocr_cache 参数。
    """

    def test_add_screenshot_item_with_ocr_cache(self, manager: ClipboardHistoryManager):
        """测试添加截图时包含 OCR 缓存
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        ocr_text = "这是 OCR 识别的文本内容"
        
        # 添加截图并包含 OCR 缓存
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=ocr_text,
        )
        
        # 验证返回了有效的 ID
        assert item_id is not None
        assert len(item_id) > 0
        
        # 获取保存的记录
        item = manager.get_item(item_id)
        assert item is not None
        
        # 验证 OCR 缓存被正确保存
        assert item.ocr_cache == ocr_text
        assert item.ocr_cache_timestamp is not None

    def test_add_screenshot_item_without_ocr_cache(self, manager: ClipboardHistoryManager):
        """测试添加截图时不包含 OCR 缓存
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        
        # 添加截图，不包含 OCR 缓存
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=None,
        )
        
        # 获取保存的记录
        item = manager.get_item(item_id)
        assert item is not None
        
        # 验证 OCR 缓存为空
        assert item.ocr_cache is None
        assert item.ocr_cache_timestamp is None

    def test_add_screenshot_item_with_annotations_and_ocr_cache(
        self, 
        manager: ClipboardHistoryManager
    ):
        """测试添加截图时同时包含标注和 OCR 缓存
        
        **Validates: Requirements 8.6, 8.7**
        """
        image = create_test_image()
        ocr_text = "OCR 识别结果"
        annotations = [
            {'tool': 'rect', 'color': '#FF0000', 'width': 2},
            {'tool': 'arrow', 'color': '#00FF00', 'width': 3},
        ]
        selection_rect = (100, 200, 300, 400)
        
        # 添加截图
        item_id = manager.add_screenshot_item(
            image=image,
            annotations=annotations,
            selection_rect=selection_rect,
            ocr_cache=ocr_text,
        )
        
        # 获取保存的记录
        item = manager.get_item(item_id)
        assert item is not None
        
        # 验证所有数据都被正确保存
        assert item.ocr_cache == ocr_text
        assert item.annotations == annotations
        assert item.selection_rect == selection_rect
        assert item.content_type == ContentType.IMAGE

    def test_add_screenshot_item_ocr_cache_unicode(self, manager: ClipboardHistoryManager):
        """测试 OCR 缓存支持 Unicode 字符
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        # 包含中文、日文、韩文、emoji 的 OCR 文本
        ocr_text = "中文测试 日本語 한국어 🎉 العربية"
        
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=ocr_text,
        )
        
        item = manager.get_item(item_id)
        assert item is not None
        assert item.ocr_cache == ocr_text

    def test_add_screenshot_item_ocr_cache_large_text(self, manager: ClipboardHistoryManager):
        """测试 OCR 缓存支持大文本
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        # 生成约 50KB 的 OCR 文本
        ocr_text = "这是一段很长的 OCR 识别结果。" * 2500
        
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=ocr_text,
        )
        
        item = manager.get_item(item_id)
        assert item is not None
        assert item.ocr_cache == ocr_text
        assert len(item.ocr_cache) == len(ocr_text)

    def test_update_screenshot_item_with_ocr_cache(self, manager: ClipboardHistoryManager):
        """测试更新截图时添加 OCR 缓存
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        
        # 首先添加没有 OCR 缓存的截图
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=None,
        )
        
        # 验证初始状态没有 OCR 缓存
        item = manager.get_item(item_id)
        assert item.ocr_cache is None
        
        # 使用相同 ID 更新，添加 OCR 缓存
        new_ocr_text = "新的 OCR 识别结果"
        updated_id = manager.add_screenshot_item(
            image=image,
            item_id=item_id,
            ocr_cache=new_ocr_text,
        )
        
        # 验证 ID 相同
        assert updated_id == item_id
        
        # 验证 OCR 缓存已更新
        updated_item = manager.get_item(item_id)
        assert updated_item.ocr_cache == new_ocr_text

    def test_add_screenshot_item_ocr_cache_empty_string(
        self, 
        manager: ClipboardHistoryManager
    ):
        """测试 OCR 缓存为空字符串的情况
        
        **Validates: Requirements 8.6**
        """
        image = create_test_image()
        
        # 空字符串应该被视为有效的 OCR 缓存
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache="",
        )
        
        item = manager.get_item(item_id)
        assert item is not None
        # 空字符串可能被存储为 None 或 ""
        assert item.ocr_cache == "" or item.ocr_cache is None


# ============================================================================
# 属性测试：OCR 缓存往返一致性
# ============================================================================

# OCR 缓存策略 - 避免 NUL 字符
ocr_cache_strategy = st.text(
    min_size=0, 
    max_size=5000,
    alphabet=st.characters(blacklist_categories=['Cs'], blacklist_characters=['\x00'])
)

# 标注策略
annotation_strategy = st.fixed_dictionaries({
    'tool': st.sampled_from(['rect', 'arrow', 'text', 'ellipse', 'line', 'pen']),
    'color': st.from_regex(r'#[0-9A-Fa-f]{6}', fullmatch=True),
    'width': st.integers(min_value=1, max_value=20),
})


class TestAddScreenshotItemOCRCacheProperty:
    """add_screenshot_item OCR 缓存属性测试
    
    **Validates: Requirements 8.6, 8.7**
    
    使用 hypothesis 进行属性测试，验证 OCR 缓存的往返一致性。
    """

    @settings(max_examples=10, deadline=None)
    @given(
        ocr_cache=ocr_cache_strategy,
        annotations=st.lists(annotation_strategy, min_size=0, max_size=5),
    )
    def test_ocr_cache_round_trip(
        self,
        ocr_cache: str,
        annotations: List[dict],
        tmp_path_factory,
    ):
        """Property: OCR 缓存往返一致性
        
        **Validates: Requirements 8.6, 8.7**
        
        *For any* valid OCR cache text and annotations,
        storing via add_screenshot_item and retrieving
        SHALL produce identical data.
        """
        import screenshot_tool.core.clipboard_history_manager as chm
        
        # 使用临时目录
        tmp_path = tmp_path_factory.mktemp("ocr_prop")
        original_func = chm.get_clipboard_data_dir
        chm.get_clipboard_data_dir = lambda: str(tmp_path)
        
        try:
            manager = ClipboardHistoryManager(max_items=100)
            image = create_test_image()
            
            # 添加截图
            item_id = manager.add_screenshot_item(
                image=image,
                annotations=annotations if annotations else None,
                ocr_cache=ocr_cache if ocr_cache else None,
            )
            
            # 获取保存的记录
            item = manager.get_item(item_id)
            assert item is not None
            
            # 验证 OCR 缓存
            if ocr_cache:
                assert item.ocr_cache == ocr_cache, \
                    f"OCR cache mismatch: expected {ocr_cache!r}, got {item.ocr_cache!r}"
            else:
                assert item.ocr_cache is None or item.ocr_cache == ""
            
            # 验证标注数据
            if annotations:
                assert item.annotations == annotations
            else:
                assert item.annotations is None or item.annotations == []
                
        finally:
            chm.get_clipboard_data_dir = original_func


# ============================================================================
# 集成测试：SQLite 存储验证
# ============================================================================

class TestAddScreenshotItemSQLiteIntegration:
    """add_screenshot_item SQLite 集成测试
    
    **Validates: Requirements 8.1, 8.6, 8.7**
    
    验证 add_screenshot_item 正确使用 SQLite 存储 OCR 缓存。
    """

    def test_ocr_cache_persisted_to_sqlite(self, manager: ClipboardHistoryManager):
        """测试 OCR 缓存被持久化到 SQLite
        
        **Validates: Requirements 8.1, 8.6**
        """
        image = create_test_image()
        ocr_text = "持久化测试的 OCR 文本"
        
        # 添加截图
        item_id = manager.add_screenshot_item(
            image=image,
            ocr_cache=ocr_text,
        )
        
        # 验证使用了 SQLite 存储
        assert manager._use_sqlite is True
        assert manager._sqlite_storage is not None
        
        # 直接从 SQLite 存储读取验证
        sqlite_item = manager._sqlite_storage.get_item(item_id)
        assert sqlite_item is not None
        assert sqlite_item.ocr_cache == ocr_text

    def test_annotations_persisted_to_sqlite(self, manager: ClipboardHistoryManager):
        """测试标注数据被持久化到 SQLite
        
        **Validates: Requirements 8.1, 8.7**
        """
        image = create_test_image()
        annotations = [
            {'tool': 'rect', 'color': '#FF0000', 'width': 2, 'x': 10, 'y': 20},
            {'tool': 'text', 'color': '#0000FF', 'width': 1, 'content': '测试文本'},
        ]
        
        # 添加截图
        item_id = manager.add_screenshot_item(
            image=image,
            annotations=annotations,
        )
        
        # 直接从 SQLite 存储读取验证
        sqlite_item = manager._sqlite_storage.get_item(item_id)
        assert sqlite_item is not None
        assert sqlite_item.annotations == annotations

    def test_ocr_cache_survives_manager_recreation(self, temp_data_dir):
        """测试 OCR 缓存在管理器重建后仍然存在
        
        **Validates: Requirements 8.1, 8.6**
        """
        image = create_test_image()
        ocr_text = "重建测试的 OCR 文本"
        
        # 创建第一个管理器并添加数据
        manager1 = ClipboardHistoryManager(max_items=100)
        item_id = manager1.add_screenshot_item(
            image=image,
            ocr_cache=ocr_text,
        )
        
        # 创建新的管理器（模拟应用重启）
        manager2 = ClipboardHistoryManager(max_items=100)
        
        # 验证数据仍然存在
        item = manager2.get_item(item_id)
        assert item is not None
        assert item.ocr_cache == ocr_text
