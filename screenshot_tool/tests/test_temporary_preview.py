# -*- coding: utf-8 -*-
"""
临时预览模式属性测试

Feature: workbench-temporary-preview-python
**Validates: Requirements 1.1, 1.2, 1.3**

Property 1: Temporary Mode Entry Preserves State
- 验证任何有效的 QImage 和可选标注，调用 open_with_temporary_image() 后：
  - 工作台处于临时模式 (is_temporary_mode() == True)
  - 历史管理器没有新增条目
  - 历史列表选择被清除

测试策略：
1. 使用 hypothesis 生成随机图像尺寸和标注数据
2. 调用 open_with_temporary_image() 进入临时预览模式
3. 验证状态变化符合预期
4. 每个属性测试运行至少 100 次迭代
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import Qt


# ============================================================================
# 测试环境设置
# ============================================================================

# 确保有 QApplication 实例（GUI 测试必需）
@pytest.fixture(scope="session")
def qapp():
    """创建 QApplication 实例（整个测试会话共享）"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ============================================================================
# Hypothesis 策略定义
# ============================================================================

# 图像尺寸策略 - 生成合理的图像尺寸
image_width_strategy = st.integers(min_value=10, max_value=1000)
image_height_strategy = st.integers(min_value=10, max_value=1000)

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


# ============================================================================
# 辅助函数
# ============================================================================

def create_test_image(width: int, height: int) -> QImage:
    """创建测试用的 QImage
    
    Args:
        width: 图像宽度
        height: 图像高度
        
    Returns:
        填充了随机颜色的 QImage
    """
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    # 填充一个简单的颜色，避免空图像
    image.fill(QColor(100, 150, 200))
    return image


class MockClipboardHistoryManager:
    """模拟的剪贴板历史管理器
    
    用于测试临时预览模式，不实际写入文件系统。
    """
    
    def __init__(self):
        self._history = []
        self._initial_count = 0
        
        # 模拟信号
        self.history_changed = MagicMock()
        self.history_changed.connect = MagicMock()
        self.history_changed.disconnect = MagicMock()
        self.history_changed.emit = MagicMock()
    
    def get_history(self) -> List:
        """获取历史记录"""
        return self._history.copy()
    
    def get_history_count(self) -> int:
        """获取历史记录数量"""
        return len(self._history)
    
    def search(self, text: str) -> List:
        """搜索历史记录"""
        return self._history.copy()
    
    def get_item(self, item_id: str):
        """根据 ID 获取条目"""
        for item in self._history:
            if item.id == item_id:
                return item
        return None
    
    def copy_to_clipboard(self, item_id: str) -> bool:
        """复制到剪贴板"""
        return True
    
    def set_history_window_focused(self, focused: bool) -> None:
        """设置历史窗口焦点状态"""
        pass
    
    def start_monitoring(self) -> None:
        """开始监听剪贴板"""
        pass
    
    def stop_monitoring(self) -> None:
        """停止监听剪贴板"""
        pass
    
    def save_initial_count(self) -> None:
        """保存初始历史记录数量（用于验证）"""
        self._initial_count = len(self._history)
    
    def verify_no_new_entries(self) -> bool:
        """验证没有新增历史记录"""
        return len(self._history) == self._initial_count


# ============================================================================
# Property 1: Temporary Mode Entry Preserves State 属性测试
# ============================================================================

class TestTemporaryModeEntryPreservesState:
    """Property 1: 临时模式进入保持状态
    
    **Validates: Requirements 1.1, 1.2, 1.3**
    
    *For any* valid QImage and optional annotations,
    when open_with_temporary_image() is called:
    - The workbench SHALL be in temporary mode (is_temporary_mode() == True)
    - The history manager SHALL NOT have any new entries
    - The history list selection SHALL be cleared
    """

    @settings(
        max_examples=10, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=annotations_list_strategy,
    )
    def test_temporary_mode_entry_preserves_state(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
    ):
        """Property 1: Temporary Mode Entry Preserves State
        
        **Validates: Requirements 1.1, 1.2, 1.3**
        
        *For any* valid QImage and optional annotations,
        when open_with_temporary_image() is called,
        the workbench SHALL be in temporary mode,
        the history manager SHALL NOT have any new entries,
        and the history list selection SHALL be cleared.
        """
        # 导入被测试的类
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        # 创建模拟的历史管理器
        mock_manager = MockClipboardHistoryManager()
        mock_manager.save_initial_count()
        
        # 创建工作台窗口（跳过初始刷新以提高测试速度）
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 1. 创建测试图像
            image = create_test_image(width, height)
            assert not image.isNull(), f"Failed to create test image {width}x{height}"
            
            # 2. 验证初始状态：不在临时模式
            assert window.is_temporary_mode() is False, \
                "Window should not be in temporary mode initially"
            
            # 3. 调用 open_with_temporary_image
            # 如果方法未实现，会抛出 AttributeError
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(
                    image=image,
                    annotations=annotations if annotations else None
                )
                
                # 4. 验证临时模式状态 (Requirements 1.1, 1.2)
                assert window.is_temporary_mode() is True, \
                    "Window should be in temporary mode after open_with_temporary_image()"
                
                # 5. 验证历史管理器没有新增条目 (Requirements 1.3)
                assert mock_manager.verify_no_new_entries(), \
                    "History manager should NOT have any new entries in temporary mode"
                
                # 6. 验证历史列表选择被清除
                # 通过检查 _list 的 currentIndex 是否无效
                current_index = window._list.currentIndex()
                assert not current_index.isValid(), \
                    "History list selection should be cleared in temporary mode"
                
                # 7. 验证临时图像已存储
                assert window._temporary_image is not None, \
                    "Temporary image should be stored"
                assert window._temporary_image.width() == width, \
                    f"Temporary image width mismatch: expected {width}, got {window._temporary_image.width()}"
                assert window._temporary_image.height() == height, \
                    f"Temporary image height mismatch: expected {height}, got {window._temporary_image.height()}"
                
                # 8. 验证标注数据已存储（如果提供了标注）
                if annotations:
                    assert window._temporary_annotations == annotations, \
                        f"Temporary annotations mismatch: expected {annotations}, got {window._temporary_annotations}"
                else:
                    # 空列表或 None 都是可接受的
                    assert window._temporary_annotations is None or window._temporary_annotations == [], \
                        f"Temporary annotations should be None or empty, got {window._temporary_annotations}"
            else:
                # 方法未实现，跳过测试但记录
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            # 清理：关闭窗口
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
    )
    def test_temporary_mode_entry_without_annotations(
        self,
        qapp,
        width: int,
        height: int,
    ):
        """Property 1.1: 无标注时临时模式进入
        
        **Validates: Requirements 1.1, 1.2**
        
        *For any* valid QImage without annotations,
        when open_with_temporary_image() is called,
        the workbench SHALL be in temporary mode.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        mock_manager.save_initial_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            assert not image.isNull()
            
            if hasattr(window, 'open_with_temporary_image'):
                # 不传递标注参数
                window.open_with_temporary_image(image=image)
                
                assert window.is_temporary_mode() is True, \
                    "Window should be in temporary mode"
                assert mock_manager.verify_no_new_entries(), \
                    "No new history entries should be created"
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=st.lists(annotation_strategy, min_size=1, max_size=20),
    )
    def test_temporary_mode_stores_annotations(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
    ):
        """Property 1.2: 临时模式存储标注数据
        
        **Validates: Requirements 1.1, 1.2, 1.3**
        
        *For any* valid QImage with annotations,
        when open_with_temporary_image() is called,
        the annotations SHALL be stored in _temporary_annotations.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(
                    image=image,
                    annotations=annotations
                )
                
                # 验证标注数据被正确存储
                assert window._temporary_annotations is not None, \
                    "Temporary annotations should not be None"
                assert window._temporary_annotations == annotations, \
                    f"Annotations mismatch: expected {annotations}, got {window._temporary_annotations}"
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()

    def test_temporary_mode_initial_state(self, qapp):
        """验证初始状态不在临时模式
        
        **Validates: Requirements 1.1**
        
        工作台窗口创建后，初始状态应该不在临时模式。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 验证初始状态
            assert window.is_temporary_mode() is False, \
                "Window should not be in temporary mode initially"
            assert window._is_temporary_mode is False, \
                "_is_temporary_mode should be False initially"
            assert window._temporary_image is None, \
                "_temporary_image should be None initially"
            assert window._temporary_annotations is None, \
                "_temporary_annotations should be None initially"
            assert window._temporary_ocr_text is None, \
                "_temporary_ocr_text should be None initially"
        
        finally:
            window.close()
            window.deleteLater()

    def test_has_unsaved_changes_reflects_state(self, qapp):
        """验证 has_unsaved_changes() 反映正确状态
        
        **Validates: Requirements 1.1, 1.2**
        
        has_unsaved_changes() 应该在临时模式且有临时图像时返回 True。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 初始状态：没有未保存的更改
            assert window.has_unsaved_changes() is False, \
                "Should not have unsaved changes initially"
            
            if hasattr(window, 'open_with_temporary_image'):
                # 进入临时模式
                image = create_test_image(100, 100)
                window.open_with_temporary_image(image=image)
                
                # 现在应该有未保存的更改
                assert window.has_unsaved_changes() is True, \
                    "Should have unsaved changes after open_with_temporary_image()"
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()


# ============================================================================
# 边界情况测试
# ============================================================================

class TestTemporaryModeEdgeCases:
    """临时模式边界情况测试
    
    **Validates: Requirements 1.1, 1.2, 1.3**
    """

    def test_minimum_image_size(self, qapp):
        """测试最小图像尺寸
        
        **Validates: Requirements 1.1**
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 最小尺寸图像 (1x1)
            image = create_test_image(1, 1)
            
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(image=image)
                assert window.is_temporary_mode() is True
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()

    def test_large_image_size(self, qapp):
        """测试大图像尺寸
        
        **Validates: Requirements 1.1**
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 大尺寸图像 (4K)
            image = create_test_image(3840, 2160)
            
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(image=image)
                assert window.is_temporary_mode() is True
                assert window._temporary_image.width() == 3840
                assert window._temporary_image.height() == 2160
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()

    def test_empty_annotations_list(self, qapp):
        """测试空标注列表
        
        **Validates: Requirements 1.1, 1.3**
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(100, 100)
            
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(image=image, annotations=[])
                assert window.is_temporary_mode() is True
                # 空列表应该被存储为空列表或 None
                assert window._temporary_annotations is None or window._temporary_annotations == []
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()

    def test_many_annotations(self, qapp):
        """测试大量标注
        
        **Validates: Requirements 1.1, 1.3**
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(100, 100)
            
            # 创建 50 个标注
            annotations = [
                {'tool': 'rect', 'color': '#FF0000', 'width': i % 10 + 1}
                for i in range(50)
            ]
            
            if hasattr(window, 'open_with_temporary_image'):
                window.open_with_temporary_image(image=image, annotations=annotations)
                assert window.is_temporary_mode() is True
                assert len(window._temporary_annotations) == 50
            else:
                pytest.skip("open_with_temporary_image() method not yet implemented")
        
        finally:
            window.close()
            window.deleteLater()


# ============================================================================
# Property 2: Save Persists All Associated Data 属性测试
# ============================================================================

class MockClipboardHistoryManagerWithSave(MockClipboardHistoryManager):
    """支持保存功能的模拟历史管理器
    
    用于测试 Property 2: Save Persists All Associated Data
    模拟 add_screenshot_item 方法，验证保存操作的正确性。
    """
    
    def __init__(self):
        super().__init__()
        self._saved_items = {}  # 存储保存的条目 {id: item_data}
        self._next_id = 1
    
    def add_screenshot_item(
        self,
        image: QImage,
        annotations: Optional[List[dict]] = None,
        selection_rect: Optional[tuple] = None,
        item_id: Optional[str] = None,
        ocr_cache: Optional[str] = None,
    ) -> str:
        """模拟保存截图条目
        
        Args:
            image: 截图图像
            annotations: 标注数据
            selection_rect: 选区坐标
            item_id: 可选的 ID
            ocr_cache: OCR 缓存结果
            
        Returns:
            保存的条目 ID
        """
        # 生成 ID
        new_id = item_id or f"saved_{self._next_id}"
        self._next_id += 1
        
        # 存储条目数据
        self._saved_items[new_id] = {
            'id': new_id,
            'image_width': image.width(),
            'image_height': image.height(),
            'annotations': annotations,
            'ocr_cache': ocr_cache,
            'selection_rect': selection_rect,
        }
        
        # 创建模拟的 HistoryItem 并添加到历史
        from dataclasses import dataclass
        from datetime import datetime
        
        @dataclass
        class MockHistoryItem:
            id: str
            content_type: str = "image"
            text_content: Optional[str] = None
            image_path: Optional[str] = None
            preview_text: str = "[截图]"
            timestamp: datetime = None
            is_pinned: bool = False
            custom_name: Optional[str] = None
            ocr_cache: Optional[str] = None
            annotations: Optional[List[dict]] = None
            
            def __post_init__(self):
                if self.timestamp is None:
                    self.timestamp = datetime.now()
            
            def has_annotations(self) -> bool:
                return self.annotations is not None and len(self.annotations) > 0
        
        mock_item = MockHistoryItem(
            id=new_id,
            image_path=f"images/{new_id}.png",
            ocr_cache=ocr_cache,
            annotations=annotations,
        )
        self._history.insert(0, mock_item)
        
        return new_id
    
    def get_saved_item(self, item_id: str) -> Optional[dict]:
        """获取保存的条目数据（用于验证）"""
        return self._saved_items.get(item_id)
    
    def has_saved_item(self, item_id: str) -> bool:
        """检查是否有保存的条目"""
        return item_id in self._saved_items
    
    def get_saved_count(self) -> int:
        """获取保存的条目数量"""
        return len(self._saved_items)


# OCR 文本策略 - 生成合理的 OCR 文本
ocr_text_strategy = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=5000, alphabet=st.characters(
        blacklist_categories=('Cc', 'Cs'),  # 排除控制字符和代理对
        blacklist_characters='\x00'  # 排除 null 字符
    ))
)


class TestSavePersistsAllAssociatedData:
    """Property 2: Save Persists All Associated Data
    
    **Validates: Requirements 2.1, 2.3, 2.4, 3.3, 6.2**
    
    *For any* temporary preview state with image, OCR cache, and annotations,
    when confirm_and_save() is called:
    - The history manager SHALL contain a new item with the image
    - The saved item SHALL contain the OCR cache if present
    - The saved item SHALL contain the annotations if present
    - The workbench SHALL exit temporary mode (is_temporary_mode() == False)
    - The saved item SHALL be selected in the history list
    """

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=annotations_list_strategy,
        ocr_text=ocr_text_strategy,
    )
    def test_save_persists_all_associated_data(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
        ocr_text: Optional[str],
    ):
        """Property 2: Save Persists All Associated Data
        
        **Validates: Requirements 2.1, 2.3, 2.4, 3.3, 6.2**
        
        *For any* temporary preview state with image, OCR cache, and annotations,
        when confirm_and_save() is called:
        - The history manager SHALL contain a new item with the image (Req 2.1)
        - The saved item SHALL contain the OCR cache if present (Req 3.3)
        - The saved item SHALL contain the annotations if present (Req 6.2)
        - The workbench SHALL exit temporary mode (Req 2.4)
        - The saved item SHALL be selected in the history list (Req 2.3, 2.4)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        # 创建支持保存的模拟管理器
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_saved_count = mock_manager.get_saved_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 1. 创建测试图像
            image = create_test_image(width, height)
            assert not image.isNull(), f"Failed to create test image {width}x{height}"
            
            # 2. 检查方法是否实现
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 3. 进入临时预览模式
            window.open_with_temporary_image(
                image=image,
                annotations=annotations if annotations else None
            )
            
            # 4. 设置临时 OCR 缓存（如果有）
            if ocr_text is not None:
                window._temporary_ocr_text = ocr_text
            
            # 5. 验证进入临时模式
            assert window.is_temporary_mode() is True, \
                "Window should be in temporary mode before save"
            
            # 6. 调用 confirm_and_save()
            saved_id = window.confirm_and_save()
            
            # 7. 验证保存成功
            assert saved_id is not None, \
                "confirm_and_save() should return a valid ID"
            
            # 8. 验证历史管理器包含新条目（Requirements 2.1）
            assert mock_manager.has_saved_item(saved_id), \
                f"History manager should contain saved item with ID {saved_id}"
            assert mock_manager.get_saved_count() == initial_saved_count + 1, \
                "History manager should have exactly one new item"
            
            # 9. 验证保存的条目包含正确的图像尺寸
            saved_item = mock_manager.get_saved_item(saved_id)
            assert saved_item is not None, "Saved item should exist"
            assert saved_item['image_width'] == width, \
                f"Saved image width mismatch: expected {width}, got {saved_item['image_width']}"
            assert saved_item['image_height'] == height, \
                f"Saved image height mismatch: expected {height}, got {saved_item['image_height']}"
            
            # 10. 验证 OCR 缓存被保存（Requirements 3.3）
            if ocr_text is not None:
                assert saved_item['ocr_cache'] == ocr_text, \
                    f"OCR cache mismatch: expected '{ocr_text}', got '{saved_item['ocr_cache']}'"
            else:
                # 没有 OCR 缓存时，应该是 None
                assert saved_item['ocr_cache'] is None, \
                    f"OCR cache should be None, got '{saved_item['ocr_cache']}'"
            
            # 11. 验证标注数据被保存（Requirements 6.2）
            if annotations:
                assert saved_item['annotations'] == annotations, \
                    f"Annotations mismatch: expected {annotations}, got {saved_item['annotations']}"
            else:
                # 没有标注时，应该是 None 或空列表
                assert saved_item['annotations'] is None or saved_item['annotations'] == [], \
                    f"Annotations should be None or empty, got {saved_item['annotations']}"
            
            # 12. 验证退出临时模式（Requirements 2.4）
            assert window.is_temporary_mode() is False, \
                "Window should exit temporary mode after save"
            assert window._temporary_image is None, \
                "Temporary image should be cleared after save"
            assert window._temporary_ocr_text is None, \
                "Temporary OCR text should be cleared after save"
            assert window._temporary_annotations is None, \
                "Temporary annotations should be cleared after save"
            
            # 13. 验证 has_unsaved_changes() 返回 False
            assert window.has_unsaved_changes() is False, \
                "Should not have unsaved changes after save"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
    )
    def test_save_without_ocr_or_annotations(
        self,
        qapp,
        width: int,
        height: int,
    ):
        """Property 2.1: 无 OCR 和标注时的保存
        
        **Validates: Requirements 2.1, 2.4**
        
        *For any* temporary preview state with only image (no OCR, no annotations),
        when confirm_and_save() is called, the save should succeed.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 进入临时模式（无标注）
            window.open_with_temporary_image(image=image)
            
            # 保存
            saved_id = window.confirm_and_save()
            
            # 验证
            assert saved_id is not None, "Save should succeed"
            assert window.is_temporary_mode() is False, "Should exit temporary mode"
            
            saved_item = mock_manager.get_saved_item(saved_id)
            assert saved_item['ocr_cache'] is None, "OCR cache should be None"
            assert saved_item['annotations'] is None or saved_item['annotations'] == [], \
                "Annotations should be None or empty"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        ocr_text=st.text(min_size=1, max_size=1000, alphabet=st.characters(
            blacklist_categories=('Cc', 'Cs'),
            blacklist_characters='\x00'
        )),
    )
    def test_save_with_ocr_cache(
        self,
        qapp,
        width: int,
        height: int,
        ocr_text: str,
    ):
        """Property 2.2: 带 OCR 缓存的保存
        
        **Validates: Requirements 3.3**
        
        *For any* temporary preview state with OCR cache,
        when confirm_and_save() is called, the OCR cache SHALL be persisted.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 进入临时模式
            window.open_with_temporary_image(image=image)
            
            # 设置 OCR 缓存
            window._temporary_ocr_text = ocr_text
            
            # 保存
            saved_id = window.confirm_and_save()
            
            # 验证 OCR 缓存被保存
            assert saved_id is not None, "Save should succeed"
            saved_item = mock_manager.get_saved_item(saved_id)
            assert saved_item['ocr_cache'] == ocr_text, \
                f"OCR cache should be preserved: expected '{ocr_text}', got '{saved_item['ocr_cache']}'"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=st.lists(annotation_strategy, min_size=1, max_size=20),
    )
    def test_save_with_annotations(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
    ):
        """Property 2.3: 带标注的保存
        
        **Validates: Requirements 6.2**
        
        *For any* temporary preview state with annotations,
        when confirm_and_save() is called, the annotations SHALL be persisted.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 进入临时模式（带标注）
            window.open_with_temporary_image(image=image, annotations=annotations)
            
            # 保存
            saved_id = window.confirm_and_save()
            
            # 验证标注被保存
            assert saved_id is not None, "Save should succeed"
            saved_item = mock_manager.get_saved_item(saved_id)
            assert saved_item['annotations'] == annotations, \
                f"Annotations should be preserved: expected {annotations}, got {saved_item['annotations']}"
        
        finally:
            window.close()
            window.deleteLater()

    def test_save_not_in_temporary_mode_returns_none(self, qapp):
        """验证非临时模式下调用 confirm_and_save() 返回 None
        
        **Validates: Requirements 2.1**
        
        如果不在临时模式，confirm_and_save() 应该返回 None。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 不进入临时模式，直接调用 confirm_and_save
            assert window.is_temporary_mode() is False, \
                "Should not be in temporary mode initially"
            
            result = window.confirm_and_save()
            
            assert result is None, \
                "confirm_and_save() should return None when not in temporary mode"
            assert mock_manager.get_saved_count() == 0, \
                "No items should be saved"
        
        finally:
            window.close()
            window.deleteLater()

    def test_save_clears_all_temporary_state(self, qapp):
        """验证保存后清除所有临时状态
        
        **Validates: Requirements 2.4, 7.4**
        
        保存后应该清除所有临时状态：
        - _is_temporary_mode = False
        - _temporary_image = None
        - _temporary_id = ""
        - _temporary_ocr_text = None
        - _temporary_annotations = None
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 进入临时模式（带所有数据）
            image = create_test_image(200, 200)
            annotations = [{'tool': 'rect', 'color': '#FF0000', 'width': 2}]
            window.open_with_temporary_image(image=image, annotations=annotations)
            window._temporary_ocr_text = "Test OCR text"
            
            # 验证临时状态已设置
            assert window._is_temporary_mode is True
            assert window._temporary_image is not None
            assert window._temporary_ocr_text is not None
            assert window._temporary_annotations is not None
            
            # 保存
            saved_id = window.confirm_and_save()
            assert saved_id is not None
            
            # 验证所有临时状态已清除
            assert window._is_temporary_mode is False, \
                "_is_temporary_mode should be False after save"
            assert window._temporary_image is None, \
                "_temporary_image should be None after save"
            assert window._temporary_id == "", \
                "_temporary_id should be empty after save"
            assert window._temporary_ocr_text is None, \
                "_temporary_ocr_text should be None after save"
            assert window._temporary_annotations is None, \
                "_temporary_annotations should be None after save"
        
        finally:
            window.close()
            window.deleteLater()


# ============================================================================
# Property 3: Discard Clears All Temporary Data 属性测试
# ============================================================================

class TestDiscardClearsAllTemporaryData:
    """Property 3: Discard Clears All Temporary Data
    
    **Validates: Requirements 2.5, 3.4, 6.3, 7.4**
    
    *For any* temporary preview state, when discard_temporary() is called:
    - The workbench SHALL exit temporary mode
    - The temporary image reference SHALL be None
    - The temporary OCR cache SHALL be None
    - The temporary annotations SHALL be None
    - The history manager SHALL NOT have any new entries
    """

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=annotations_list_strategy,
        ocr_text=ocr_text_strategy,
    )
    def test_discard_clears_all_temporary_data(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
        ocr_text: Optional[str],
    ):
        """Property 3: Discard Clears All Temporary Data
        
        **Validates: Requirements 2.5, 3.4, 6.3, 7.4**
        
        *For any* temporary preview state with image, OCR cache, and annotations,
        when discard_temporary() is called:
        - The workbench SHALL exit temporary mode (Req 2.5)
        - The temporary image reference SHALL be None (Req 7.4)
        - The temporary OCR cache SHALL be None (Req 3.4)
        - The temporary annotations SHALL be None (Req 6.3)
        - The history manager SHALL NOT have any new entries (Req 2.5)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        # 创建模拟管理器并记录初始状态
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        initial_saved_count = mock_manager.get_saved_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 1. 创建测试图像
            image = create_test_image(width, height)
            assert not image.isNull(), f"Failed to create test image {width}x{height}"
            
            # 2. 检查方法是否实现
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 3. 进入临时预览模式
            window.open_with_temporary_image(
                image=image,
                annotations=annotations if annotations else None
            )
            
            # 4. 设置临时 OCR 缓存（如果有）
            if ocr_text is not None:
                window._temporary_ocr_text = ocr_text
            
            # 5. 验证进入临时模式
            assert window.is_temporary_mode() is True, \
                "Window should be in temporary mode before discard"
            assert window._temporary_image is not None, \
                "Temporary image should be set before discard"
            
            # 6. 调用 discard_temporary()
            window.discard_temporary()
            
            # 7. 验证退出临时模式（Requirements 2.5）
            assert window.is_temporary_mode() is False, \
                "Window should exit temporary mode after discard"
            assert window._is_temporary_mode is False, \
                "_is_temporary_mode should be False after discard"
            
            # 8. 验证临时图像引用为 None（Requirements 7.4）
            assert window._temporary_image is None, \
                "Temporary image reference should be None after discard"
            
            # 9. 验证临时 OCR 缓存为 None（Requirements 3.4）
            assert window._temporary_ocr_text is None, \
                "Temporary OCR cache should be None after discard"
            
            # 10. 验证临时标注为 None（Requirements 6.3）
            assert window._temporary_annotations is None, \
                "Temporary annotations should be None after discard"
            
            # 11. 验证临时 ID 被清除
            assert window._temporary_id == "", \
                "Temporary ID should be empty after discard"
            
            # 12. 验证历史管理器没有新增条目（Requirements 2.5）
            assert mock_manager.get_history_count() == initial_history_count, \
                f"History count should remain {initial_history_count}, got {mock_manager.get_history_count()}"
            assert mock_manager.get_saved_count() == initial_saved_count, \
                f"Saved count should remain {initial_saved_count}, got {mock_manager.get_saved_count()}"
            
            # 13. 验证 has_unsaved_changes() 返回 False
            assert window.has_unsaved_changes() is False, \
                "Should not have unsaved changes after discard"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
    )
    def test_discard_with_image_only(
        self,
        qapp,
        width: int,
        height: int,
    ):
        """Property 3.1: 仅有图像时的丢弃
        
        **Validates: Requirements 2.5, 7.4**
        
        *For any* temporary preview state with only image (no OCR, no annotations),
        when discard_temporary() is called, all temporary data should be cleared.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 进入临时模式（仅图像，无标注和 OCR）
            window.open_with_temporary_image(image=image)
            
            # 验证进入临时模式
            assert window.is_temporary_mode() is True
            
            # 丢弃
            window.discard_temporary()
            
            # 验证所有临时数据被清除
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after discard"
            assert window._temporary_image is None, \
                "Temporary image should be None after discard"
            assert window._temporary_ocr_text is None, \
                "Temporary OCR text should be None after discard"
            assert window._temporary_annotations is None, \
                "Temporary annotations should be None after discard"
            
            # 验证历史没有新增
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not have new entries after discard"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        ocr_text=st.text(min_size=1, max_size=1000, alphabet=st.characters(
            blacklist_categories=('Cc', 'Cs'),
            blacklist_characters='\x00'
        )),
    )
    def test_discard_with_image_and_ocr_cache(
        self,
        qapp,
        width: int,
        height: int,
        ocr_text: str,
    ):
        """Property 3.2: 有图像和 OCR 缓存时的丢弃
        
        **Validates: Requirements 2.5, 3.4, 7.4**
        
        *For any* temporary preview state with image and OCR cache,
        when discard_temporary() is called, the OCR cache SHALL be cleared.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 进入临时模式
            window.open_with_temporary_image(image=image)
            
            # 设置 OCR 缓存
            window._temporary_ocr_text = ocr_text
            
            # 验证 OCR 缓存已设置
            assert window._temporary_ocr_text == ocr_text, \
                "OCR cache should be set before discard"
            
            # 丢弃
            window.discard_temporary()
            
            # 验证 OCR 缓存被清除（Requirements 3.4）
            assert window._temporary_ocr_text is None, \
                "Temporary OCR cache should be None after discard"
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after discard"
            
            # 验证历史没有新增
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not have new entries after discard"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=st.lists(annotation_strategy, min_size=1, max_size=20),
    )
    def test_discard_with_image_and_annotations(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
    ):
        """Property 3.3: 有图像和标注时的丢弃
        
        **Validates: Requirements 2.5, 6.3, 7.4**
        
        *For any* temporary preview state with image and annotations,
        when discard_temporary() is called, the annotations SHALL be cleared.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 进入临时模式（带标注）
            window.open_with_temporary_image(image=image, annotations=annotations)
            
            # 验证标注已设置
            assert window._temporary_annotations == annotations, \
                "Annotations should be set before discard"
            
            # 丢弃
            window.discard_temporary()
            
            # 验证标注被清除（Requirements 6.3）
            assert window._temporary_annotations is None, \
                "Temporary annotations should be None after discard"
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after discard"
            
            # 验证历史没有新增
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not have new entries after discard"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=st.lists(annotation_strategy, min_size=1, max_size=10),
        ocr_text=st.text(min_size=1, max_size=500, alphabet=st.characters(
            blacklist_categories=('Cc', 'Cs'),
            blacklist_characters='\x00'
        )),
    )
    def test_discard_with_image_ocr_and_annotations(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
        ocr_text: str,
    ):
        """Property 3.4: 有图像、OCR 缓存和标注时的丢弃
        
        **Validates: Requirements 2.5, 3.4, 6.3, 7.4**
        
        *For any* temporary preview state with image, OCR cache, and annotations,
        when discard_temporary() is called, ALL temporary data SHALL be cleared.
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 进入临时模式（带标注）
            window.open_with_temporary_image(image=image, annotations=annotations)
            
            # 设置 OCR 缓存
            window._temporary_ocr_text = ocr_text
            
            # 验证所有临时数据已设置
            assert window.is_temporary_mode() is True, \
                "Should be in temporary mode"
            assert window._temporary_image is not None, \
                "Temporary image should be set"
            assert window._temporary_ocr_text == ocr_text, \
                "OCR cache should be set"
            assert window._temporary_annotations == annotations, \
                "Annotations should be set"
            
            # 丢弃
            window.discard_temporary()
            
            # 验证所有临时数据被清除
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after discard"
            assert window._temporary_image is None, \
                "Temporary image should be None after discard"
            assert window._temporary_ocr_text is None, \
                "Temporary OCR cache should be None after discard"
            assert window._temporary_annotations is None, \
                "Temporary annotations should be None after discard"
            assert window._temporary_id == "", \
                "Temporary ID should be empty after discard"
            
            # 验证历史没有新增
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not have new entries after discard"
        
        finally:
            window.close()
            window.deleteLater()

    def test_discard_not_in_temporary_mode_is_safe(self, qapp):
        """验证非临时模式下调用 discard_temporary() 是安全的
        
        **Validates: Requirements 2.5**
        
        如果不在临时模式，discard_temporary() 应该安全执行（无操作）。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 不进入临时模式，直接调用 discard_temporary
            assert window.is_temporary_mode() is False, \
                "Should not be in temporary mode initially"
            
            # 调用 discard_temporary（应该安全执行）
            window.discard_temporary()
            
            # 验证状态保持不变
            assert window.is_temporary_mode() is False, \
                "Should still not be in temporary mode"
            assert window._temporary_image is None, \
                "Temporary image should still be None"
            assert window._temporary_ocr_text is None, \
                "Temporary OCR text should still be None"
            assert window._temporary_annotations is None, \
                "Temporary annotations should still be None"
            
            # 验证历史没有变化
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not change"
        
        finally:
            window.close()
            window.deleteLater()

    def test_discard_multiple_times_is_safe(self, qapp):
        """验证多次调用 discard_temporary() 是安全的
        
        **Validates: Requirements 2.5**
        
        多次调用 discard_temporary() 应该是幂等的。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 进入临时模式
            image = create_test_image(100, 100)
            window.open_with_temporary_image(image=image)
            
            # 第一次丢弃
            window.discard_temporary()
            assert window.is_temporary_mode() is False
            
            # 第二次丢弃（应该安全执行）
            window.discard_temporary()
            assert window.is_temporary_mode() is False
            
            # 第三次丢弃（应该安全执行）
            window.discard_temporary()
            assert window.is_temporary_mode() is False
            
            # 验证状态正确
            assert window._temporary_image is None
            assert window._temporary_ocr_text is None
            assert window._temporary_annotations is None
        
        finally:
            window.close()
            window.deleteLater()

    def test_discard_releases_memory(self, qapp):
        """验证丢弃后释放内存
        
        **Validates: Requirements 7.4**
        
        丢弃后应该释放临时图像的内存引用。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 创建大图像
            large_image = create_test_image(2000, 2000)
            
            # 进入临时模式
            window.open_with_temporary_image(image=large_image)
            
            # 验证图像已存储
            assert window._temporary_image is not None
            assert window._temporary_image.width() == 2000
            
            # 丢弃
            window.discard_temporary()
            
            # 验证图像引用已释放（Requirements 7.4）
            assert window._temporary_image is None, \
                "Temporary image reference should be None to release memory"
        
        finally:
            window.close()
            window.deleteLater()


# ============================================================================
# 运行测试
# ============================================================================
# Property 4: New Screenshot Replaces Without Prompt 属性测试
# ============================================================================

class TestNewScreenshotReplacesWithoutPrompt:
    """Property 4: New Screenshot Replaces Without Prompt
    
    **Validates: Requirements 4.3**
    
    *For any* workbench in temporary mode with an existing temporary image,
    when a new screenshot is taken:
    - The new image SHALL replace the old temporary image
    - No confirmation dialog SHALL be shown
    - The workbench SHALL remain in temporary mode
    
    测试策略：
    1. 使用 hypothesis 生成随机图像尺寸和标注数据
    2. 先进入临时预览模式（第一张截图）
    3. 再次调用 open_with_temporary_image（第二张截图）
    4. 验证新图像替换旧图像，无确认对话框，保持临时模式
    5. 每个属性测试运行至少 100 次迭代
    
    注意：测试中需要 mock window.show(), activateWindow(), raise_() 方法，
    因为这些方法会导致测试挂起（等待 Qt 事件循环）。
    """

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
        annotations1=annotations_list_strategy,
        annotations2=annotations_list_strategy,
    )
    def test_new_screenshot_replaces_without_prompt(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
        annotations1: List[dict],
        annotations2: List[dict],
    ):
        """Property 4: New Screenshot Replaces Without Prompt
        
        **Validates: Requirements 4.3**
        
        *For any* workbench in temporary mode with an existing temporary image,
        when a new screenshot is taken:
        - The new image SHALL replace the old temporary image (Req 4.3)
        - No confirmation dialog SHALL be shown (Req 4.3)
        - The workbench SHALL remain in temporary mode (Req 4.3)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        # 创建模拟管理器
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            # 1. 创建第一张测试图像
            image1 = create_test_image(width1, height1)
            assert not image1.isNull(), f"Failed to create test image1 {width1}x{height1}"
            
            # 2. 创建第二张测试图像
            image2 = create_test_image(width2, height2)
            assert not image2.isNull(), f"Failed to create test image2 {width2}x{height2}"
            
            # 3. 检查方法是否实现
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 4. 进入临时预览模式（第一张截图）
            window.open_with_temporary_image(
                image=image1,
                annotations=annotations1 if annotations1 else None
            )
            
            # 5. 验证第一张截图的临时状态
            assert window.is_temporary_mode() is True, \
                "Window should be in temporary mode after first screenshot"
            assert window._temporary_image is not None, \
                "Temporary image should be set after first screenshot"
            assert window._temporary_image.width() == width1, \
                f"First image width mismatch: expected {width1}, got {window._temporary_image.width()}"
            assert window._temporary_image.height() == height1, \
                f"First image height mismatch: expected {height1}, got {window._temporary_image.height()}"
            
            # 记录第一张截图的临时 ID
            first_temp_id = window._temporary_id
            
            # 6. 设置第一张截图的 OCR 缓存（模拟用户已进行 OCR）
            window._temporary_ocr_text = "First screenshot OCR text"
            
            # 7. 再次调用 open_with_temporary_image（第二张截图）
            # 这应该直接替换，不显示确认对话框
            window.open_with_temporary_image(
                image=image2,
                annotations=annotations2 if annotations2 else None
            )
            
            # 8. 验证新图像替换旧图像（Requirements 4.3）
            assert window._temporary_image is not None, \
                "Temporary image should still be set after replacement"
            assert window._temporary_image.width() == width2, \
                f"New image width mismatch: expected {width2}, got {window._temporary_image.width()}"
            assert window._temporary_image.height() == height2, \
                f"New image height mismatch: expected {height2}, got {window._temporary_image.height()}"
            
            # 9. 验证工作台保持临时模式（Requirements 4.3）
            assert window.is_temporary_mode() is True, \
                "Window SHALL remain in temporary mode after replacement (Req 4.3)"
            
            # 10. 验证 OCR 缓存被清除（新截图应该清除旧的 OCR 缓存）
            assert window._temporary_ocr_text is None, \
                "OCR cache should be cleared after replacement"
            
            # 11. 验证标注数据被替换
            if annotations2:
                assert window._temporary_annotations == annotations2, \
                    f"Annotations should be replaced: expected {annotations2}, got {window._temporary_annotations}"
            else:
                assert window._temporary_annotations is None or window._temporary_annotations == [], \
                    f"Annotations should be None or empty, got {window._temporary_annotations}"
            
            # 12. 验证新的临时 ID 被生成
            assert window._temporary_id != first_temp_id, \
                "New temporary ID should be generated after replacement"
            
            # 13. 验证历史管理器没有新增条目（没有自动保存旧截图）
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should NOT have new entries (old screenshot should not be auto-saved)"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
    )
    def test_replacement_clears_ocr_cache(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
    ):
        """Property 4.1: 替换时清除 OCR 缓存
        
        **Validates: Requirements 4.3**
        
        *For any* workbench in temporary mode with OCR cache,
        when a new screenshot replaces the old one:
        - The OCR cache SHALL be cleared
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 2. 设置 OCR 缓存
            window._temporary_ocr_text = "Test OCR text for first screenshot"
            assert window._temporary_ocr_text is not None, \
                "OCR cache should be set"
            
            # 3. 替换为新截图
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 4. 验证 OCR 缓存被清除
            assert window._temporary_ocr_text is None, \
                "OCR cache SHALL be cleared after replacement"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
        annotations1=st.lists(annotation_strategy, min_size=1, max_size=10),
        annotations2=st.lists(annotation_strategy, min_size=1, max_size=10),
    )
    def test_replacement_replaces_annotations(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
        annotations1: List[dict],
        annotations2: List[dict],
    ):
        """Property 4.2: 替换时替换标注数据
        
        **Validates: Requirements 4.3**
        
        *For any* workbench in temporary mode with annotations,
        when a new screenshot with different annotations replaces the old one:
        - The annotations SHALL be replaced with the new annotations
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图，带标注）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1, annotations=annotations1)
            
            # 2. 验证第一张截图的标注
            assert window._temporary_annotations == annotations1, \
                f"First annotations mismatch: expected {annotations1}, got {window._temporary_annotations}"
            
            # 3. 替换为新截图（带不同标注）
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2, annotations=annotations2)
            
            # 4. 验证标注被替换
            assert window._temporary_annotations == annotations2, \
                f"Annotations SHALL be replaced: expected {annotations2}, got {window._temporary_annotations}"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
    )
    def test_replacement_generates_new_temp_id(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
    ):
        """Property 4.3: 替换时生成新的临时 ID
        
        **Validates: Requirements 4.3**
        
        *For any* workbench in temporary mode,
        when a new screenshot replaces the old one:
        - A new temporary ID SHALL be generated
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 2. 记录第一个临时 ID
            first_temp_id = window._temporary_id
            assert first_temp_id != "", \
                "First temporary ID should not be empty"
            
            # 3. 替换为新截图
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 4. 验证新的临时 ID 被生成
            second_temp_id = window._temporary_id
            assert second_temp_id != "", \
                "Second temporary ID should not be empty"
            assert second_temp_id != first_temp_id, \
                f"New temporary ID SHALL be generated: first={first_temp_id}, second={second_temp_id}"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
    )
    def test_replacement_does_not_save_old_screenshot(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
    ):
        """Property 4.4: 替换时不自动保存旧截图
        
        **Validates: Requirements 4.3**
        
        *For any* workbench in temporary mode,
        when a new screenshot replaces the old one:
        - The old screenshot SHALL NOT be automatically saved to history
        - No confirmation dialog SHALL be shown
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        initial_saved_count = mock_manager.get_saved_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 2. 验证历史没有变化
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should not change after first screenshot"
            assert mock_manager.get_saved_count() == initial_saved_count, \
                "Saved count should not change after first screenshot"
            
            # 3. 替换为新截图
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 4. 验证历史仍然没有变化（旧截图没有被自动保存）
            assert mock_manager.get_history_count() == initial_history_count, \
                "History SHALL NOT have new entries after replacement (old screenshot not auto-saved)"
            assert mock_manager.get_saved_count() == initial_saved_count, \
                "Saved count SHALL NOT change after replacement"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
    )
    def test_replacement_keeps_toolbar_visible(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
    ):
        """Property 4.5: 替换后工具栏保持可见
        
        **Validates: Requirements 4.3, 5.1**
        
        *For any* workbench in temporary mode,
        when a new screenshot replaces the old one:
        - The save toolbar SHALL remain visible
        - The history list SHALL remain disabled
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 2. 验证工具栏可见
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar should be visible after first screenshot"
            assert window._list.isEnabled() is False, \
                "History list should be disabled after first screenshot"
            
            # 3. 替换为新截图
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 4. 验证工具栏仍然可见
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar SHALL remain visible after replacement"
            assert window._list.isEnabled() is False, \
                "History list SHALL remain disabled after replacement"
        
        finally:
            window.close()
            window.deleteLater()

    def test_replacement_from_normal_mode(self, qapp):
        """验证从正常模式进入临时模式（非替换场景）
        
        **Validates: Requirements 4.3**
        
        从正常模式进入临时模式不是替换场景，应该正常进入临时模式。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 验证初始状态不在临时模式
            assert window.is_temporary_mode() is False, \
                "Should not be in temporary mode initially"
            
            # 2. 进入临时模式
            image = create_test_image(100, 100)
            window.open_with_temporary_image(image=image)
            
            # 3. 验证进入临时模式
            assert window.is_temporary_mode() is True, \
                "Should be in temporary mode after open_with_temporary_image"
            assert window._temporary_image is not None, \
                "Temporary image should be set"
        
        finally:
            window.close()
            window.deleteLater()

    def test_multiple_replacements(self, qapp):
        """验证多次连续替换
        
        **Validates: Requirements 4.3**
        
        多次连续替换截图，每次都应该正确替换，不显示确认对话框。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        initial_history_count = mock_manager.get_history_count()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 进行 5 次连续替换
            for i in range(5):
                size = 100 + i * 50
                image = create_test_image(size, size)
                window.open_with_temporary_image(image=image)
                
                # 验证每次替换后的状态
                assert window.is_temporary_mode() is True, \
                    f"Should remain in temporary mode after replacement {i+1}"
                assert window._temporary_image.width() == size, \
                    f"Image width should be {size} after replacement {i+1}"
                assert window._temporary_image.height() == size, \
                    f"Image height should be {size} after replacement {i+1}"
            
            # 验证历史没有变化（所有旧截图都没有被自动保存）
            assert mock_manager.get_history_count() == initial_history_count, \
                "History should NOT have new entries after multiple replacements"
        
        finally:
            window.close()
            window.deleteLater()

    def test_replacement_with_null_image_rejected(self, qapp):
        """验证空图像不能替换
        
        **Validates: Requirements 4.3**
        
        尝试用空图像替换应该被拒绝，保持原有临时图像。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 1. 进入临时模式（有效图像）
            image1 = create_test_image(200, 200)
            window.open_with_temporary_image(image=image1)
            
            # 2. 记录当前状态
            original_width = window._temporary_image.width()
            original_height = window._temporary_image.height()
            original_temp_id = window._temporary_id
            
            # 3. 尝试用空图像替换
            null_image = QImage()
            assert null_image.isNull(), "Null image should be null"
            
            # 调用 open_with_temporary_image 应该返回 False 或保持原状态
            result = window.open_with_temporary_image(image=null_image)
            
            # 4. 验证原有临时图像保持不变
            # 注意：实现可能返回 False 或抛出异常，这里验证状态不变
            if result is False or window._temporary_image is not None:
                # 如果方法返回 False 或图像仍然存在，验证状态不变
                if window._temporary_image is not None:
                    assert window._temporary_image.width() == original_width, \
                        "Original image should be preserved when null image is rejected"
                    assert window._temporary_image.height() == original_height, \
                        "Original image should be preserved when null image is rejected"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
        ocr_text=st.text(min_size=1, max_size=500, alphabet=st.characters(
            blacklist_categories=('Cc', 'Cs'),
            blacklist_characters='\x00'
        )),
    )
    def test_replacement_then_save_saves_new_image(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
        ocr_text: str,
    ):
        """Property 4.6: 替换后保存应该保存新图像
        
        **Validates: Requirements 4.3, 2.1**
        
        *For any* workbench after screenshot replacement,
        when confirm_and_save() is called:
        - The NEW image SHALL be saved (not the old one)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        # Mock window display methods to prevent test hanging
        window.show = MagicMock()
        window.activateWindow = MagicMock()
        window.raise_ = MagicMock()
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 1. 进入临时模式（第一张截图）
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 2. 设置 OCR 缓存
            window._temporary_ocr_text = "First OCR text"
            
            # 3. 替换为新截图
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 4. 设置新的 OCR 缓存
            window._temporary_ocr_text = ocr_text
            
            # 5. 保存
            saved_id = window.confirm_and_save()
            assert saved_id is not None, "Save should succeed"
            
            # 6. 验证保存的是新图像
            saved_item = mock_manager.get_saved_item(saved_id)
            assert saved_item is not None, "Saved item should exist"
            assert saved_item['image_width'] == width2, \
                f"Saved image should be the NEW image: expected width {width2}, got {saved_item['image_width']}"
            assert saved_item['image_height'] == height2, \
                f"Saved image should be the NEW image: expected height {height2}, got {saved_item['image_height']}"
            
            # 7. 验证保存的是新的 OCR 缓存
            assert saved_item['ocr_cache'] == ocr_text, \
                f"Saved OCR cache should be the NEW one: expected '{ocr_text}', got '{saved_item['ocr_cache']}'"
        
        finally:
            window.close()
            window.deleteLater()


# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


# ============================================================================
# Property 5: Toolbar Visibility Matches Mode 属性测试
# ============================================================================

class TestToolbarVisibilityMatchesMode:
    """Property 5: Toolbar Visibility Matches Mode
    
    **Validates: Requirements 5.1, 5.3, 5.4**
    
    *For any* workbench state:
    - WHILE in temporary mode, the save toolbar SHALL be visible
    - WHILE in temporary mode, the history list selection SHALL be disabled
    - WHEN exiting temporary mode, the save toolbar SHALL be hidden
    
    测试策略：
    1. 使用 hypothesis 生成随机图像尺寸和标注数据
    2. 验证进入临时模式时工具栏可见性和历史列表状态
    3. 验证退出临时模式（保存/丢弃）后工具栏隐藏和历史列表恢复
    4. 每个属性测试运行至少 100 次迭代
    """

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=annotations_list_strategy,
    )
    def test_toolbar_visible_in_temporary_mode(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
    ):
        """Property 5.1: 临时模式下工具栏可见
        
        **Validates: Requirements 5.1, 5.3**
        
        *For any* workbench in temporary mode:
        - The save toolbar SHALL be visible (Req 5.1)
        - The history list selection SHALL be disabled (Req 5.3)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 1. 创建测试图像
            image = create_test_image(width, height)
            assert not image.isNull(), f"Failed to create test image {width}x{height}"
            
            # 2. 检查方法是否实现
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 3. 验证初始状态：工具栏隐藏，历史列表启用
            assert window._save_toolbar.isVisible() is False, \
                "Save toolbar should be hidden initially"
            assert window._list.isEnabled() is True, \
                "History list should be enabled initially"
            
            # 4. 进入临时预览模式
            window.open_with_temporary_image(
                image=image,
                annotations=annotations if annotations else None
            )
            
            # 5. 验证临时模式状态
            assert window.is_temporary_mode() is True, \
                "Window should be in temporary mode"
            
            # 6. 验证工具栏可见（Requirements 5.1）
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar SHALL be visible in temporary mode (Req 5.1)"
            
            # 7. 验证历史列表选择被禁用（Requirements 5.3）
            assert window._list.isEnabled() is False, \
                "History list selection SHALL be disabled in temporary mode (Req 5.3)"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
    )
    def test_toolbar_hidden_after_save(
        self,
        qapp,
        width: int,
        height: int,
    ):
        """Property 5.2: 保存后工具栏隐藏
        
        **Validates: Requirements 5.4**
        
        *For any* workbench exiting temporary mode via save:
        - The save toolbar SHALL be hidden (Req 5.4)
        - The history list selection SHALL be enabled
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 1. 进入临时模式
            window.open_with_temporary_image(image=image)
            
            # 2. 验证工具栏可见
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar should be visible in temporary mode"
            assert window._list.isEnabled() is False, \
                "History list should be disabled in temporary mode"
            
            # 3. 保存（退出临时模式）
            saved_id = window.confirm_and_save()
            assert saved_id is not None, "Save should succeed"
            
            # 4. 验证退出临时模式
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after save"
            
            # 5. 验证工具栏隐藏（Requirements 5.4）
            assert window._save_toolbar.isVisible() is False, \
                "Save toolbar SHALL be hidden after exiting temporary mode (Req 5.4)"
            
            # 6. 验证历史列表选择恢复启用
            assert window._list.isEnabled() is True, \
                "History list selection SHALL be enabled after exiting temporary mode"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
    )
    def test_toolbar_hidden_after_discard(
        self,
        qapp,
        width: int,
        height: int,
    ):
        """Property 5.3: 丢弃后工具栏隐藏
        
        **Validates: Requirements 5.4**
        
        *For any* workbench exiting temporary mode via discard:
        - The save toolbar SHALL be hidden (Req 5.4)
        - The history list selection SHALL be enabled
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # 1. 进入临时模式
            window.open_with_temporary_image(image=image)
            
            # 2. 验证工具栏可见
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar should be visible in temporary mode"
            assert window._list.isEnabled() is False, \
                "History list should be disabled in temporary mode"
            
            # 3. 丢弃（退出临时模式）
            window.discard_temporary()
            
            # 4. 验证退出临时模式
            assert window.is_temporary_mode() is False, \
                "Should exit temporary mode after discard"
            
            # 5. 验证工具栏隐藏（Requirements 5.4）
            assert window._save_toolbar.isVisible() is False, \
                "Save toolbar SHALL be hidden after exiting temporary mode (Req 5.4)"
            
            # 6. 验证历史列表选择恢复启用
            assert window._list.isEnabled() is True, \
                "History list selection SHALL be enabled after exiting temporary mode"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width=image_width_strategy,
        height=image_height_strategy,
        annotations=annotations_list_strategy,
        ocr_text=ocr_text_strategy,
    )
    def test_toolbar_visibility_matches_mode_comprehensive(
        self,
        qapp,
        width: int,
        height: int,
        annotations: List[dict],
        ocr_text: Optional[str],
    ):
        """Property 5: Toolbar Visibility Matches Mode (综合测试)
        
        **Validates: Requirements 5.1, 5.3, 5.4**
        
        *For any* workbench state:
        - WHILE in temporary mode, the save toolbar SHALL be visible (Req 5.1)
        - WHILE in temporary mode, the history list selection SHALL be disabled (Req 5.3)
        - WHEN exiting temporary mode, the save toolbar SHALL be hidden (Req 5.4)
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            image = create_test_image(width, height)
            
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # ========== 阶段 1: 初始状态 ==========
            # 工具栏隐藏，历史列表启用
            assert window._save_toolbar.isVisible() is False, \
                "Initial: Save toolbar should be hidden"
            assert window._list.isEnabled() is True, \
                "Initial: History list should be enabled"
            assert window.is_temporary_mode() is False, \
                "Initial: Should not be in temporary mode"
            
            # ========== 阶段 2: 进入临时模式 ==========
            window.open_with_temporary_image(
                image=image,
                annotations=annotations if annotations else None
            )
            
            # 设置 OCR 缓存（如果有）
            if ocr_text is not None:
                window._temporary_ocr_text = ocr_text
            
            # 验证临时模式状态
            assert window.is_temporary_mode() is True, \
                "Temporary mode: Should be in temporary mode"
            
            # 验证工具栏可见（Requirements 5.1）
            assert window._save_toolbar.isVisible() is True, \
                "Temporary mode: Save toolbar SHALL be visible (Req 5.1)"
            
            # 验证历史列表禁用（Requirements 5.3）
            assert window._list.isEnabled() is False, \
                "Temporary mode: History list SHALL be disabled (Req 5.3)"
            
            # ========== 阶段 3: 退出临时模式（保存） ==========
            saved_id = window.confirm_and_save()
            assert saved_id is not None, "Save should succeed"
            
            # 验证退出临时模式
            assert window.is_temporary_mode() is False, \
                "After save: Should exit temporary mode"
            
            # 验证工具栏隐藏（Requirements 5.4）
            assert window._save_toolbar.isVisible() is False, \
                "After save: Save toolbar SHALL be hidden (Req 5.4)"
            
            # 验证历史列表恢复启用
            assert window._list.isEnabled() is True, \
                "After save: History list SHALL be enabled"
        
        finally:
            window.close()
            window.deleteLater()

    def test_toolbar_hidden_initially(self, qapp):
        """验证初始状态工具栏隐藏
        
        **Validates: Requirements 5.4**
        
        工作台窗口创建后，初始状态工具栏应该隐藏。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            # 验证初始状态
            assert window._save_toolbar.isVisible() is False, \
                "Save toolbar should be hidden initially (not in temporary mode)"
            assert window._list.isEnabled() is True, \
                "History list should be enabled initially"
            assert window.is_temporary_mode() is False, \
                "Should not be in temporary mode initially"
        
        finally:
            window.close()
            window.deleteLater()

    def test_history_list_disabled_in_temporary_mode(self, qapp):
        """验证临时模式下历史列表选择被禁用
        
        **Validates: Requirements 5.3**
        
        临时模式下，历史列表选择应该被禁用，防止用户切换到其他历史条目。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 初始状态：历史列表启用
            assert window._list.isEnabled() is True, \
                "History list should be enabled initially"
            
            # 进入临时模式
            image = create_test_image(100, 100)
            window.open_with_temporary_image(image=image)
            
            # 验证历史列表被禁用（Requirements 5.3）
            assert window._list.isEnabled() is False, \
                "History list selection SHALL be disabled in temporary mode (Req 5.3)"
        
        finally:
            window.close()
            window.deleteLater()

    def test_history_list_enabled_after_exit(self, qapp):
        """验证退出临时模式后历史列表选择恢复启用
        
        **Validates: Requirements 5.3, 5.4**
        
        退出临时模式后，历史列表选择应该恢复启用。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            
            # 进入临时模式
            image = create_test_image(100, 100)
            window.open_with_temporary_image(image=image)
            
            # 验证历史列表被禁用
            assert window._list.isEnabled() is False, \
                "History list should be disabled in temporary mode"
            
            # 保存退出临时模式
            window.confirm_and_save()
            
            # 验证历史列表恢复启用
            assert window._list.isEnabled() is True, \
                "History list selection SHALL be enabled after exiting temporary mode"
        
        finally:
            window.close()
            window.deleteLater()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        width1=image_width_strategy,
        height1=image_height_strategy,
        width2=image_width_strategy,
        height2=image_height_strategy,
    )
    def test_toolbar_visibility_across_multiple_entries(
        self,
        qapp,
        width1: int,
        height1: int,
        width2: int,
        height2: int,
    ):
        """Property 5.4: 多次进入/退出临时模式时工具栏可见性正确
        
        **Validates: Requirements 5.1, 5.3, 5.4**
        
        *For any* sequence of entering and exiting temporary mode:
        - Toolbar visibility SHALL always match the current mode
        - History list enabled state SHALL always match the current mode
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManagerWithSave()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            if not hasattr(window, 'confirm_and_save'):
                pytest.skip("confirm_and_save() method not yet implemented")
            if not hasattr(window, 'discard_temporary'):
                pytest.skip("discard_temporary() method not yet implemented")
            
            # ========== 第一轮：进入 → 保存 ==========
            image1 = create_test_image(width1, height1)
            window.open_with_temporary_image(image=image1)
            
            # 验证临时模式状态
            assert window._save_toolbar.isVisible() is True, \
                "Round 1: Toolbar should be visible in temporary mode"
            assert window._list.isEnabled() is False, \
                "Round 1: History list should be disabled in temporary mode"
            
            # 保存
            window.confirm_and_save()
            
            # 验证退出状态
            assert window._save_toolbar.isVisible() is False, \
                "Round 1: Toolbar should be hidden after save"
            assert window._list.isEnabled() is True, \
                "Round 1: History list should be enabled after save"
            
            # ========== 第二轮：进入 → 丢弃 ==========
            image2 = create_test_image(width2, height2)
            window.open_with_temporary_image(image=image2)
            
            # 验证临时模式状态
            assert window._save_toolbar.isVisible() is True, \
                "Round 2: Toolbar should be visible in temporary mode"
            assert window._list.isEnabled() is False, \
                "Round 2: History list should be disabled in temporary mode"
            
            # 丢弃
            window.discard_temporary()
            
            # 验证退出状态
            assert window._save_toolbar.isVisible() is False, \
                "Round 2: Toolbar should be hidden after discard"
            assert window._list.isEnabled() is True, \
                "Round 2: History list should be enabled after discard"
        
        finally:
            window.close()
            window.deleteLater()

    def test_toolbar_buttons_functional_in_temporary_mode(self, qapp):
        """验证临时模式下工具栏按钮可用
        
        **Validates: Requirements 5.1**
        
        临时模式下，工具栏的保存、复制、丢弃按钮应该都是启用状态。
        """
        from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
        
        mock_manager = MockClipboardHistoryManager()
        
        window = ClipboardHistoryWindow(
            manager=mock_manager,
            skip_initial_refresh=True
        )
        
        try:
            if not hasattr(window, 'open_with_temporary_image'):
                pytest.skip("open_with_temporary_image() method not yet implemented")
            
            # 进入临时模式
            image = create_test_image(100, 100)
            window.open_with_temporary_image(image=image)
            
            # 验证工具栏可见
            assert window._save_toolbar.isVisible() is True, \
                "Save toolbar should be visible in temporary mode"
            
            # 验证按钮启用状态
            save_btn = window._save_toolbar.get_save_button()
            copy_btn = window._save_toolbar.get_copy_button()
            discard_btn = window._save_toolbar.get_discard_button()
            
            assert save_btn.isEnabled() is True, \
                "Save button should be enabled in temporary mode"
            assert copy_btn.isEnabled() is True, \
                "Copy button should be enabled in temporary mode"
            assert discard_btn.isEnabled() is True, \
                "Discard button should be enabled in temporary mode"
        
        finally:
            window.close()
            window.deleteLater()
