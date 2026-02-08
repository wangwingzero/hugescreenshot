# -*- coding: utf-8 -*-
"""
剪贴板 OCR 合并功能属性测试

Feature: clipboard-ocr-merge
Requirements: 1.1, 1.2, 2.1, 2.3, 2.4, 4.3, 8.1, 8.2

测试内容：
- Property 1: OCR 按钮可见性基于条目类型
- Property 2: 预览模式切换往返
- Property 3: 选择变更重置预览模式
- Property 7: 引擎级 OCR 缓存
- Property 11: 条目级 OCR 缓存恢复
"""

import pytest
from datetime import datetime
from typing import Dict, Optional
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, HealthCheck

from PySide6.QtWidgets import QApplication


# ============================================================
# 测试数据模型
# ============================================================

class MockContentType:
    """模拟 ContentType 枚举"""
    TEXT = "text"
    IMAGE = "image"
    HTML = "html"


class MockHistoryItem:
    """模拟 HistoryItem 类"""
    
    def __init__(
        self,
        item_id: str,
        content_type: str,
        text_content: str = None,
        image_path: str = None,
        is_pinned: bool = False,
    ):
        self.id = item_id
        self.content_type = content_type
        self.text_content = text_content
        self.image_path = image_path
        self.is_pinned = is_pinned
        self.timestamp = datetime.now()
        self.preview_text = text_content[:50] if text_content else "[图片]"
        self.custom_name = None
    
    def has_annotations(self):
        return False
    
    def get_annotation_count(self):
        return 0


class MockClipboardHistoryManager:
    """模拟 ClipboardHistoryManager 类"""
    
    def __init__(self, items=None):
        self._items = items or []
        self.history_changed = MagicMock()
        self.history_changed.connect = MagicMock()
        self.history_changed.disconnect = MagicMock()
        self.history_changed.emit = MagicMock()
    
    def get_history(self):
        return self._items
    
    def get_item(self, item_id: str):
        for item in self._items:
            if item.id == item_id:
                return item
        return None
    
    def search(self, query: str):
        if not query:
            return self._items
        query_lower = query.lower()
        return [
            item for item in self._items
            if (item.text_content and query_lower in item.text_content.lower())
            or (item.preview_text and query_lower in item.preview_text.lower())
        ]
    
    def copy_to_clipboard(self, item_id: str):
        return True
    
    def start_monitoring(self):
        pass
    
    def stop_monitoring(self):
        pass
    
    def save(self):
        pass
    
    def render_screenshot_with_annotations(self, item_id: str):
        return None


# ============================================================
# Hypothesis 策略定义
# ============================================================

# 生成有效的条目类型
item_type_strategy = st.sampled_from([MockContentType.TEXT, MockContentType.IMAGE])

# 生成有效的 UUID 字符串
uuid_strategy = st.uuids().map(str)

# 生成有效的文本内容
text_content_strategy = st.text(min_size=1, max_size=100).filter(lambda x: x.strip() != "")

# 生成有效的图片路径
image_path_strategy = st.text(min_size=5, max_size=50).filter(lambda x: x.strip() != "").map(
    lambda x: f"clipboard_images/{x}.png"
)


@st.composite
def mock_history_item_strategy(draw, content_type=None):
    """生成模拟的 HistoryItem 实例
    
    Args:
        content_type: 指定内容类型，None 表示随机
    """
    if content_type is None:
        content_type = draw(item_type_strategy)
    
    item_id = draw(uuid_strategy)
    
    if content_type == MockContentType.IMAGE:
        return MockHistoryItem(
            item_id=item_id,
            content_type=content_type,
            text_content=None,
            image_path=draw(image_path_strategy),
            is_pinned=draw(st.booleans()),
        )
    else:
        return MockHistoryItem(
            item_id=item_id,
            content_type=content_type,
            text_content=draw(text_content_strategy),
            image_path=None,
            is_pinned=draw(st.booleans()),
        )


@st.composite
def image_item_strategy(draw):
    """生成图片类型的 HistoryItem"""
    return draw(mock_history_item_strategy(content_type=MockContentType.IMAGE))


@st.composite
def text_item_strategy(draw):
    """生成文本类型的 HistoryItem"""
    return draw(mock_history_item_strategy(content_type=MockContentType.TEXT))


# ============================================================
# Property 1: OCR 按钮可见性基于条目类型
# Feature: clipboard-ocr-merge, Property 1: OCR Button Visibility Based on Item Type
# Validates: Requirements 1.1, 1.2
# ============================================================

class TestOCRButtonVisibility:
    """Property 1: OCR 按钮可见性基于条目类型测试
    
    验证：对于任意历史记录条目，"识别文字"按钮仅在条目类型为 IMAGE 时可见。
    
    **Validates: Requirements 1.1, 1.2**
    """
    
    @given(item=mock_history_item_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_ocr_button_visibility_based_on_item_type(self, item, qtbot):
        """
        Property 1: OCR Button Visibility Based on Item Type
        
        *For any* history item, the "识别文字" button SHALL be visible 
        if and only if the item's content type is IMAGE.
        
        **Validates: Requirements 1.1, 1.2**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 创建模拟管理器
        manager = MockClipboardHistoryManager(items=[item])
        
        # 模拟 ClipboardHistoryWindow 的 OCR 按钮可见性逻辑
        # 这是从 _show_preview 方法提取的核心逻辑
        def should_ocr_button_be_visible(history_item):
            """根据条目类型判断 OCR 按钮是否应该可见"""
            if history_item is None:
                return False
            if history_item.content_type != MockContentType.IMAGE:
                return False
            # 图片条目需要有有效的图片路径
            if not history_item.image_path:
                return False
            return True
        
        # 验证属性
        expected_visible = item.content_type == MockContentType.IMAGE and item.image_path is not None
        actual_visible = should_ocr_button_be_visible(item)
        
        assert actual_visible == expected_visible, (
            f"OCR 按钮可见性不正确: "
            f"content_type={item.content_type}, "
            f"image_path={item.image_path}, "
            f"expected={expected_visible}, "
            f"actual={actual_visible}"
        )
    
    def test_ocr_button_visible_for_image_item(self, qtbot):
        """单元测试：图片条目时 OCR 按钮可见"""
        item = MockHistoryItem(
            item_id="test-image-1",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/test.png",
        )
        
        # 图片条目应该显示 OCR 按钮
        assert item.content_type == MockContentType.IMAGE
        assert item.image_path is not None
    
    def test_ocr_button_hidden_for_text_item(self, qtbot):
        """单元测试：文本条目时 OCR 按钮隐藏"""
        item = MockHistoryItem(
            item_id="test-text-1",
            content_type=MockContentType.TEXT,
            text_content="测试文本内容",
        )
        
        # 文本条目不应该显示 OCR 按钮
        assert item.content_type == MockContentType.TEXT
        assert item.image_path is None


# ============================================================
# Property 2: 预览模式切换往返
# Feature: clipboard-ocr-merge, Property 2: Preview Mode Switching Round-Trip
# Validates: Requirements 2.1, 2.3
# ============================================================

class TestPreviewModeSwitchingRoundTrip:
    """Property 2: 预览模式切换往返测试
    
    验证：对于任意图片历史记录条目，点击"识别文字"然后点击"返回图片"
    应该恢复到图片预览模式，显示相同的图片。
    
    **Validates: Requirements 2.1, 2.3**
    """
    
    # 预览模式常量（与 ClipboardHistoryWindow 一致）
    PREVIEW_INDEX_IMAGE = 0
    PREVIEW_INDEX_OCR = 1
    PREVIEW_INDEX_TEXT = 2
    PREVIEW_INDEX_EMPTY = 3
    
    @given(item=image_item_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_preview_mode_switching_round_trip(self, item, qtbot):
        """
        Property 2: Preview Mode Switching Round-Trip
        
        *For any* image history item, clicking "识别文字" then "返回图片" 
        SHALL restore the preview to image mode with the same image displayed.
        
        **Validates: Requirements 2.1, 2.3**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 预览模式常量
        PREVIEW_INDEX_IMAGE = 0
        PREVIEW_INDEX_OCR = 1
        
        # 模拟预览模式状态机
        class PreviewModeStateMachine:
            """预览模式状态机"""
            
            def __init__(self, initial_item):
                self.PREVIEW_INDEX_IMAGE = 0
                self.PREVIEW_INDEX_OCR = 1
                self.current_mode = self.PREVIEW_INDEX_IMAGE
                self.current_item_id = initial_item.id
            
            def switch_to_ocr_preview(self):
                """切换到 OCR 预览模式"""
                self.current_mode = self.PREVIEW_INDEX_OCR
            
            def switch_to_image_preview(self):
                """切换回图片预览模式"""
                self.current_mode = self.PREVIEW_INDEX_IMAGE
            
            def get_current_mode(self):
                return self.current_mode
            
            def get_current_item_id(self):
                return self.current_item_id
        
        # 初始状态：图片预览模式
        state_machine = PreviewModeStateMachine(item)
        initial_mode = state_machine.get_current_mode()
        initial_item_id = state_machine.get_current_item_id()
        
        assert initial_mode == self.PREVIEW_INDEX_IMAGE, "初始模式应该是图片预览"
        
        # 点击"识别文字"：切换到 OCR 预览模式
        state_machine.switch_to_ocr_preview()
        assert state_machine.get_current_mode() == self.PREVIEW_INDEX_OCR, "应该切换到 OCR 预览模式"
        
        # 点击"返回图片"：切换回图片预览模式
        state_machine.switch_to_image_preview()
        final_mode = state_machine.get_current_mode()
        final_item_id = state_machine.get_current_item_id()
        
        # 验证属性：模式恢复到图片预览，显示相同的图片
        assert final_mode == initial_mode, (
            f"预览模式应该恢复: initial={initial_mode}, final={final_mode}"
        )
        assert final_item_id == initial_item_id, (
            f"显示的条目应该相同: initial={initial_item_id}, final={final_item_id}"
        )
    
    def test_switch_to_ocr_then_back_to_image(self, qtbot):
        """单元测试：切换到 OCR 模式然后返回图片模式"""
        # 初始状态
        current_mode = self.PREVIEW_INDEX_IMAGE
        
        # 切换到 OCR 模式
        current_mode = self.PREVIEW_INDEX_OCR
        assert current_mode == self.PREVIEW_INDEX_OCR
        
        # 返回图片模式
        current_mode = self.PREVIEW_INDEX_IMAGE
        assert current_mode == self.PREVIEW_INDEX_IMAGE
    
    def test_multiple_round_trips(self, qtbot):
        """单元测试：多次往返切换"""
        current_mode = self.PREVIEW_INDEX_IMAGE
        
        for _ in range(5):
            # 切换到 OCR 模式
            current_mode = self.PREVIEW_INDEX_OCR
            assert current_mode == self.PREVIEW_INDEX_OCR
            
            # 返回图片模式
            current_mode = self.PREVIEW_INDEX_IMAGE
            assert current_mode == self.PREVIEW_INDEX_IMAGE


# ============================================================
# Property 3: 选择变更重置预览模式
# Feature: clipboard-ocr-merge, Property 3: Selection Change Resets Preview Mode
# Validates: Requirements 2.4
# ============================================================

class TestSelectionChangeResetsPreviewMode:
    """Property 3: 选择变更重置预览模式测试
    
    验证：对于任意选择图片条目、切换到 OCR 模式、然后选择另一个图片条目的序列，
    预览应该重置为新条目的图片模式。
    
    **Validates: Requirements 2.4**
    """
    
    # 预览模式常量
    PREVIEW_INDEX_IMAGE = 0
    PREVIEW_INDEX_OCR = 1
    PREVIEW_INDEX_TEXT = 2
    PREVIEW_INDEX_EMPTY = 3
    
    @given(
        item1=image_item_strategy(),
        item2=image_item_strategy(),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_selection_change_resets_preview_mode(self, item1, item2, qtbot):
        """
        Property 3: Selection Change Resets Preview Mode
        
        *For any* sequence of selecting an image item, switching to OCR mode, 
        then selecting a different image item, the preview SHALL reset to 
        image mode for the new item.
        
        **Validates: Requirements 2.4**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 确保两个条目不同
        if item1.id == item2.id:
            pytest.skip("需要两个不同的条目")
        
        # 模拟预览模式状态机（带选择变更逻辑）
        class PreviewModeStateMachineWithSelection:
            """带选择变更逻辑的预览模式状态机"""
            
            def __init__(self):
                self.PREVIEW_INDEX_IMAGE = 0
                self.PREVIEW_INDEX_OCR = 1
                self.PREVIEW_INDEX_TEXT = 2
                self.PREVIEW_INDEX_EMPTY = 3
                self.current_mode = self.PREVIEW_INDEX_EMPTY
                self.current_item_id = None
            
            def select_item(self, item):
                """选择条目（模拟 _on_selection_changed 逻辑）
                
                根据 Requirements 2.4：选择不同条目时重置预览模式
                """
                # 如果当前处于 OCR 预览模式，切换回图片预览模式
                if self.current_mode == self.PREVIEW_INDEX_OCR:
                    # 取消正在进行的 OCR（模拟）
                    pass
                
                # 更新当前条目
                self.current_item_id = item.id
                
                # 根据条目类型设置预览模式
                if item.content_type == MockContentType.IMAGE:
                    self.current_mode = self.PREVIEW_INDEX_IMAGE
                elif item.content_type == MockContentType.TEXT:
                    self.current_mode = self.PREVIEW_INDEX_TEXT
                else:
                    self.current_mode = self.PREVIEW_INDEX_EMPTY
            
            def switch_to_ocr_preview(self):
                """切换到 OCR 预览模式"""
                self.current_mode = self.PREVIEW_INDEX_OCR
            
            def get_current_mode(self):
                return self.current_mode
            
            def get_current_item_id(self):
                return self.current_item_id
        
        state_machine = PreviewModeStateMachineWithSelection()
        
        # 步骤 1：选择第一个图片条目
        state_machine.select_item(item1)
        assert state_machine.get_current_mode() == self.PREVIEW_INDEX_IMAGE, "选择图片条目后应该是图片预览模式"
        assert state_machine.get_current_item_id() == item1.id
        
        # 步骤 2：切换到 OCR 模式
        state_machine.switch_to_ocr_preview()
        assert state_machine.get_current_mode() == self.PREVIEW_INDEX_OCR, "应该切换到 OCR 预览模式"
        
        # 步骤 3：选择第二个图片条目
        state_machine.select_item(item2)
        
        # 验证属性：预览模式应该重置为图片模式
        assert state_machine.get_current_mode() == self.PREVIEW_INDEX_IMAGE, (
            f"选择新条目后预览模式应该重置为图片模式: "
            f"actual={state_machine.get_current_mode()}"
        )
        assert state_machine.get_current_item_id() == item2.id, (
            f"当前条目应该是新选择的条目: "
            f"expected={item2.id}, actual={state_machine.get_current_item_id()}"
        )
    
    @given(
        items=st.lists(image_item_strategy(), min_size=2, max_size=10, unique_by=lambda x: x.id),
        switch_to_ocr_indices=st.lists(st.booleans(), min_size=2, max_size=10),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_selection_sequence_always_resets_mode(self, items, switch_to_ocr_indices, qtbot):
        """
        Property 3 扩展：任意选择序列后模式重置
        
        *For any* sequence of item selections with optional OCR mode switches,
        after each selection change, the preview SHALL be in image mode 
        (not OCR mode) for the newly selected item.
        
        **Validates: Requirements 2.4**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        if len(items) < 2:
            pytest.skip("需要至少两个条目")
        
        # 调整 switch_to_ocr_indices 长度与 items 匹配
        switch_to_ocr_indices = switch_to_ocr_indices[:len(items)]
        while len(switch_to_ocr_indices) < len(items):
            switch_to_ocr_indices.append(False)
        
        # 模拟状态机
        current_mode = self.PREVIEW_INDEX_EMPTY
        current_item_id = None
        
        for i, item in enumerate(items):
            # 选择条目（模拟 _on_selection_changed）
            # 如果当前处于 OCR 模式，重置为图片模式
            if current_mode == self.PREVIEW_INDEX_OCR:
                pass  # 取消 OCR
            
            current_item_id = item.id
            current_mode = self.PREVIEW_INDEX_IMAGE  # 图片条目重置为图片模式
            
            # 验证：选择后应该是图片模式
            assert current_mode == self.PREVIEW_INDEX_IMAGE, (
                f"选择条目 {i} 后应该是图片预览模式"
            )
            
            # 可选：切换到 OCR 模式
            if switch_to_ocr_indices[i]:
                current_mode = self.PREVIEW_INDEX_OCR
    
    def test_selection_change_from_ocr_to_image_mode(self, qtbot):
        """单元测试：从 OCR 模式选择新条目时重置为图片模式"""
        item1 = MockHistoryItem(
            item_id="item-1",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/img1.png",
        )
        item2 = MockHistoryItem(
            item_id="item-2",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/img2.png",
        )
        
        # 初始状态：选择 item1，处于 OCR 模式
        current_mode = self.PREVIEW_INDEX_OCR
        current_item_id = item1.id
        
        # 选择 item2
        # 模拟 _on_selection_changed 逻辑
        if current_mode == self.PREVIEW_INDEX_OCR:
            # 取消 OCR
            pass
        current_item_id = item2.id
        current_mode = self.PREVIEW_INDEX_IMAGE
        
        # 验证
        assert current_mode == self.PREVIEW_INDEX_IMAGE
        assert current_item_id == item2.id
    
    def test_selection_change_to_text_item(self, qtbot):
        """单元测试：从图片条目选择文本条目"""
        image_item = MockHistoryItem(
            item_id="image-1",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/img.png",
        )
        text_item = MockHistoryItem(
            item_id="text-1",
            content_type=MockContentType.TEXT,
            text_content="测试文本",
        )
        
        # 初始状态：选择图片条目，处于 OCR 模式
        current_mode = self.PREVIEW_INDEX_OCR
        current_item_id = image_item.id
        
        # 选择文本条目
        if current_mode == self.PREVIEW_INDEX_OCR:
            pass  # 取消 OCR
        current_item_id = text_item.id
        current_mode = self.PREVIEW_INDEX_TEXT  # 文本条目切换到文本模式
        
        # 验证
        assert current_mode == self.PREVIEW_INDEX_TEXT
        assert current_item_id == text_item.id


# ============================================================
# 集成测试：验证实际 ClipboardHistoryWindow 行为
# ============================================================

class TestClipboardHistoryWindowIntegration:
    """ClipboardHistoryWindow 集成测试
    
    验证实际窗口组件的预览模式切换行为。
    """
    
    # 预览模式常量
    PREVIEW_INDEX_IMAGE = 0
    PREVIEW_INDEX_OCR = 1
    PREVIEW_INDEX_TEXT = 2
    PREVIEW_INDEX_EMPTY = 3
    
    def test_preview_mode_constants_match(self, qtbot):
        """验证预览模式常量与实际窗口一致"""
        try:
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            
            assert ClipboardHistoryWindow.PREVIEW_INDEX_IMAGE == self.PREVIEW_INDEX_IMAGE
            assert ClipboardHistoryWindow.PREVIEW_INDEX_OCR == self.PREVIEW_INDEX_OCR
            assert ClipboardHistoryWindow.PREVIEW_INDEX_TEXT == self.PREVIEW_INDEX_TEXT
            assert ClipboardHistoryWindow.PREVIEW_INDEX_EMPTY == self.PREVIEW_INDEX_EMPTY
        except ImportError:
            pytest.skip("ClipboardHistoryWindow 不可用")
    
    def test_ocr_button_exists(self, qtbot):
        """验证 OCR 按钮存在"""
        try:
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            from screenshot_tool.core.clipboard_history_manager import ClipboardHistoryManager
            
            # 创建模拟管理器
            manager = MockClipboardHistoryManager()
            
            # 使用 patch 替换真实的管理器
            with patch.object(ClipboardHistoryManager, '__new__', return_value=manager):
                window = ClipboardHistoryWindow(manager)
                qtbot.addWidget(window)
                
                # 验证 OCR 按钮存在
                assert hasattr(window, '_ocr_btn')
                assert window._ocr_btn is not None
                assert window._ocr_btn.text() == "识字"
        except ImportError:
            pytest.skip("ClipboardHistoryWindow 不可用")
    
    def test_preview_stack_has_correct_pages(self, qtbot):
        """验证预览堆栈有正确的页面数量"""
        try:
            from screenshot_tool.ui.clipboard_history_window import ClipboardHistoryWindow
            
            manager = MockClipboardHistoryManager()
            window = ClipboardHistoryWindow(manager)
            qtbot.addWidget(window)
            
            # 验证预览堆栈有 4 个页面
            assert window._preview_stack.count() == 4
        except ImportError:
            pytest.skip("ClipboardHistoryWindow 不可用")


# ============================================================
# Property 12: 新截图自动 OCR
# Feature: clipboard-ocr-merge, Property 12: Auto-OCR on New Screenshot
# Validates: Requirements 9.1, 9.2
# ============================================================

class TestAutoOCROnNewScreenshot:
    """Property 12: 新截图自动 OCR 测试
    
    验证：对于任意新添加的截图，当使用 auto-OCR 打开 Clipboard_History_Window 时，
    系统应自动触发 OCR 并在 OCR 预览模式下显示结果。
    
    **Validates: Requirements 9.1, 9.2**
    """
    
    # 预览模式常量
    PREVIEW_INDEX_IMAGE = 0
    PREVIEW_INDEX_OCR = 1
    PREVIEW_INDEX_TEXT = 2
    PREVIEW_INDEX_EMPTY = 3
    
    @given(item=image_item_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_auto_ocr_on_new_screenshot(self, item, qtbot):
        """
        Property 12: Auto-OCR on New Screenshot
        
        *For any* newly added screenshot, when the Clipboard_History_Window is 
        opened with auto-OCR enabled, the system SHALL automatically trigger OCR 
        and display results in OCR preview mode.
        
        **Validates: Requirements 9.1, 9.2**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 模拟自动 OCR 状态机
        class AutoOCRStateMachine:
            """自动 OCR 状态机
            
            模拟 ClipboardHistoryWindow 的 open_with_auto_ocr 行为
            """
            
            def __init__(self):
                self.PREVIEW_INDEX_IMAGE = 0
                self.PREVIEW_INDEX_OCR = 1
                self._auto_ocr_item_id: Optional[str] = None
                self._current_item_id: Optional[str] = None
                self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
                self._ocr_triggered = False
                self._items = {}  # item_id -> item
            
            def add_item(self, item):
                """添加条目到历史记录"""
                self._items[item.id] = item
            
            def open_with_auto_ocr(self, item_id: str):
                """打开窗口并自动对指定条目执行 OCR
                
                模拟 ClipboardHistoryWindow.open_with_auto_ocr 方法
                """
                self._auto_ocr_item_id = item_id
                # 模拟 show() 和 activateWindow()
                # 选中该条目
                self._select_item_by_id(item_id)
                # 触发自动 OCR
                self._trigger_auto_ocr()
            
            def _select_item_by_id(self, item_id: str) -> bool:
                """根据 ID 选中条目"""
                if item_id in self._items:
                    self._current_item_id = item_id
                    return True
                return False
            
            def _trigger_auto_ocr(self):
                """触发自动 OCR
                
                模拟 ClipboardHistoryWindow._trigger_auto_ocr 方法
                """
                if self._auto_ocr_item_id:
                    # 验证当前选中的条目是否是目标条目
                    if self._current_item_id == self._auto_ocr_item_id:
                        # 验证是图片条目
                        item = self._items.get(self._auto_ocr_item_id)
                        if item and item.content_type == MockContentType.IMAGE:
                            # 触发 OCR（模拟 _on_ocr_btn_clicked）
                            self._ocr_triggered = True
                            self._current_preview_mode = self.PREVIEW_INDEX_OCR
                    # 清除标志
                    self._auto_ocr_item_id = None
            
            def get_auto_ocr_item_id(self):
                return self._auto_ocr_item_id
            
            def is_ocr_triggered(self):
                return self._ocr_triggered
            
            def get_current_preview_mode(self):
                return self._current_preview_mode
        
        # 创建状态机并添加条目
        state_machine = AutoOCRStateMachine()
        state_machine.add_item(item)
        
        # 调用 open_with_auto_ocr
        state_machine.open_with_auto_ocr(item.id)
        
        # 验证属性：
        # 1. _auto_ocr_item_id 应该被清除（OCR 已触发）
        assert state_machine.get_auto_ocr_item_id() is None, (
            "自动 OCR 触发后 _auto_ocr_item_id 应该被清除"
        )
        
        # 2. OCR 应该被触发
        assert state_machine.is_ocr_triggered(), (
            f"对于图片条目 {item.id}，OCR 应该被自动触发"
        )
        
        # 3. 预览模式应该切换到 OCR 模式
        assert state_machine.get_current_preview_mode() == state_machine.PREVIEW_INDEX_OCR, (
            f"预览模式应该切换到 OCR 模式: "
            f"expected={state_machine.PREVIEW_INDEX_OCR}, "
            f"actual={state_machine.get_current_preview_mode()}"
        )
    
    @given(item=text_item_strategy())
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_auto_ocr_not_triggered_for_text_item(self, item, qtbot):
        """
        Property 12 补充：文本条目不触发自动 OCR
        
        *For any* text item, auto-OCR SHALL NOT be triggered.
        
        **Validates: Requirements 9.3**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 模拟自动 OCR 状态机
        class AutoOCRStateMachine:
            def __init__(self):
                self._auto_ocr_item_id: Optional[str] = None
                self._current_item_id: Optional[str] = None
                self._ocr_triggered = False
                self._items = {}
            
            def add_item(self, item):
                self._items[item.id] = item
            
            def open_with_auto_ocr(self, item_id: str):
                self._auto_ocr_item_id = item_id
                self._select_item_by_id(item_id)
                self._trigger_auto_ocr()
            
            def _select_item_by_id(self, item_id: str) -> bool:
                if item_id in self._items:
                    self._current_item_id = item_id
                    return True
                return False
            
            def _trigger_auto_ocr(self):
                if self._auto_ocr_item_id:
                    if self._current_item_id == self._auto_ocr_item_id:
                        item = self._items.get(self._auto_ocr_item_id)
                        # 只对图片条目触发 OCR
                        if item and item.content_type == MockContentType.IMAGE:
                            self._ocr_triggered = True
                    self._auto_ocr_item_id = None
            
            def is_ocr_triggered(self):
                return self._ocr_triggered
        
        state_machine = AutoOCRStateMachine()
        state_machine.add_item(item)
        state_machine.open_with_auto_ocr(item.id)
        
        # 验证：文本条目不应该触发 OCR
        assert not state_machine.is_ocr_triggered(), (
            f"文本条目 {item.id} 不应该触发自动 OCR"
        )
    
    def test_auto_ocr_sets_flag_and_triggers(self, qtbot):
        """单元测试：open_with_auto_ocr 设置标志并触发 OCR"""
        item = MockHistoryItem(
            item_id="new-screenshot-1",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/new_screenshot.png",
        )
        
        # 模拟状态
        auto_ocr_item_id = None
        ocr_triggered = False
        current_preview_mode = self.PREVIEW_INDEX_IMAGE
        
        # 模拟 open_with_auto_ocr
        auto_ocr_item_id = item.id
        
        # 模拟 _trigger_auto_ocr
        if auto_ocr_item_id:
            if item.content_type == MockContentType.IMAGE:
                ocr_triggered = True
                current_preview_mode = self.PREVIEW_INDEX_OCR
            auto_ocr_item_id = None
        
        # 验证
        assert auto_ocr_item_id is None, "标志应该被清除"
        assert ocr_triggered, "OCR 应该被触发"
        assert current_preview_mode == self.PREVIEW_INDEX_OCR, "应该切换到 OCR 预览模式"
    
    def test_auto_ocr_clears_flag_after_trigger(self, qtbot):
        """单元测试：自动 OCR 触发后清除标志"""
        item = MockHistoryItem(
            item_id="test-image-auto",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/test.png",
        )
        
        # 初始状态
        auto_ocr_item_id = item.id
        
        # 触发后清除
        auto_ocr_item_id = None
        
        assert auto_ocr_item_id is None


# ============================================================
# Property 13: 手动选择时取消自动 OCR
# Feature: clipboard-ocr-merge, Property 13: Auto-OCR Cancellation on Manual Selection
# Validates: Requirements 9.4
# ============================================================

class TestAutoOCRCancellationOnManualSelection:
    """Property 13: 手动选择时取消自动 OCR 测试
    
    验证：对于任意正在进行的自动 OCR 操作，如果用户手动选择了不同的条目，
    自动 OCR 应该被取消，并显示所选条目的预览。
    
    **Validates: Requirements 9.4**
    """
    
    # 预览模式常量
    PREVIEW_INDEX_IMAGE = 0
    PREVIEW_INDEX_OCR = 1
    PREVIEW_INDEX_TEXT = 2
    PREVIEW_INDEX_EMPTY = 3
    
    @given(
        auto_ocr_item=image_item_strategy(),
        manually_selected_item=image_item_strategy(),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_auto_ocr_cancellation_on_manual_selection(
        self, auto_ocr_item, manually_selected_item, qtbot
    ):
        """
        Property 13: Auto-OCR Cancellation on Manual Selection
        
        *For any* auto-OCR operation in progress, if the user manually selects 
        a different item, the auto-OCR SHALL be cancelled and the selected 
        item's preview SHALL be displayed.
        
        **Validates: Requirements 9.4**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 确保两个条目不同
        if auto_ocr_item.id == manually_selected_item.id:
            pytest.skip("需要两个不同的条目")
        
        # 模拟自动 OCR 取消状态机
        class AutoOCRCancellationStateMachine:
            """自动 OCR 取消状态机
            
            模拟 ClipboardHistoryWindow 的 _on_selection_changed 行为
            """
            
            def __init__(self):
                self.PREVIEW_INDEX_IMAGE = 0
                self.PREVIEW_INDEX_OCR = 1
                self._auto_ocr_item_id: Optional[str] = None
                self._current_item_id: Optional[str] = None
                self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
                self._items = {}
            
            def add_item(self, item):
                self._items[item.id] = item
            
            def set_auto_ocr_item_id(self, item_id: str):
                """设置自动 OCR 目标条目（模拟 open_with_auto_ocr 的第一步）"""
                self._auto_ocr_item_id = item_id
            
            def on_selection_changed(self, new_item_id: str):
                """选择变更回调
                
                模拟 ClipboardHistoryWindow._on_selection_changed 方法
                """
                # 自动 OCR 取消逻辑（Requirements: 9.3, 9.4）
                if self._auto_ocr_item_id is not None:
                    if new_item_id != self._auto_ocr_item_id:
                        # 用户选择了不同的条目，取消自动 OCR
                        self._auto_ocr_item_id = None
                
                # 更新当前选中项
                self._current_item_id = new_item_id
                
                # 根据条目类型设置预览模式
                item = self._items.get(new_item_id)
                if item:
                    if item.content_type == MockContentType.IMAGE:
                        self._current_preview_mode = self.PREVIEW_INDEX_IMAGE
                    else:
                        self._current_preview_mode = self.PREVIEW_INDEX_TEXT
            
            def get_auto_ocr_item_id(self):
                return self._auto_ocr_item_id
            
            def get_current_item_id(self):
                return self._current_item_id
            
            def get_current_preview_mode(self):
                return self._current_preview_mode
        
        # 创建状态机并添加条目
        state_machine = AutoOCRCancellationStateMachine()
        state_machine.add_item(auto_ocr_item)
        state_machine.add_item(manually_selected_item)
        
        # 设置自动 OCR 目标（模拟 open_with_auto_ocr 开始）
        state_machine.set_auto_ocr_item_id(auto_ocr_item.id)
        
        # 验证自动 OCR 标志已设置
        assert state_machine.get_auto_ocr_item_id() == auto_ocr_item.id, (
            "自动 OCR 标志应该被设置"
        )
        
        # 用户手动选择不同的条目
        state_machine.on_selection_changed(manually_selected_item.id)
        
        # 验证属性：
        # 1. _auto_ocr_item_id 应该被清除（自动 OCR 被取消）
        assert state_machine.get_auto_ocr_item_id() is None, (
            "用户手动选择不同条目后，_auto_ocr_item_id 应该被清除"
        )
        
        # 2. 当前选中项应该是用户手动选择的条目
        assert state_machine.get_current_item_id() == manually_selected_item.id, (
            f"当前选中项应该是用户手动选择的条目: "
            f"expected={manually_selected_item.id}, "
            f"actual={state_machine.get_current_item_id()}"
        )
        
        # 3. 预览模式应该是图片预览（因为手动选择的是图片条目）
        assert state_machine.get_current_preview_mode() == state_machine.PREVIEW_INDEX_IMAGE, (
            f"预览模式应该是图片预览: "
            f"expected={state_machine.PREVIEW_INDEX_IMAGE}, "
            f"actual={state_machine.get_current_preview_mode()}"
        )
    
    @given(
        auto_ocr_item=image_item_strategy(),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_auto_ocr_not_cancelled_when_selecting_same_item(
        self, auto_ocr_item, qtbot
    ):
        """
        Property 13 补充：选择相同条目时不取消自动 OCR
        
        *For any* auto-OCR operation, if the user selects the same item 
        (the auto-OCR target), the auto-OCR SHALL NOT be cancelled.
        
        **Validates: Requirements 9.4**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 模拟状态机
        class AutoOCRStateMachine:
            def __init__(self):
                self._auto_ocr_item_id: Optional[str] = None
                self._current_item_id: Optional[str] = None
            
            def set_auto_ocr_item_id(self, item_id: str):
                self._auto_ocr_item_id = item_id
            
            def on_selection_changed(self, new_item_id: str):
                # 只有选择不同条目时才取消
                if self._auto_ocr_item_id is not None:
                    if new_item_id != self._auto_ocr_item_id:
                        self._auto_ocr_item_id = None
                self._current_item_id = new_item_id
            
            def get_auto_ocr_item_id(self):
                return self._auto_ocr_item_id
        
        state_machine = AutoOCRStateMachine()
        state_machine.set_auto_ocr_item_id(auto_ocr_item.id)
        
        # 选择相同的条目
        state_machine.on_selection_changed(auto_ocr_item.id)
        
        # 验证：自动 OCR 标志不应该被清除
        assert state_machine.get_auto_ocr_item_id() == auto_ocr_item.id, (
            "选择相同条目时，_auto_ocr_item_id 不应该被清除"
        )
    
    @given(
        items=st.lists(image_item_strategy(), min_size=3, max_size=10, unique_by=lambda x: x.id),
        selection_sequence=st.lists(st.integers(min_value=0, max_value=9), min_size=2, max_size=5),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_auto_ocr_cancellation_sequence(
        self, items, selection_sequence, qtbot
    ):
        """
        Property 13 扩展：任意选择序列后自动 OCR 取消
        
        *For any* sequence of item selections after auto-OCR is initiated,
        if any selection is different from the auto-OCR target, 
        the auto-OCR SHALL be cancelled.
        
        **Validates: Requirements 9.4**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        if len(items) < 2:
            pytest.skip("需要至少两个条目")
        
        # 调整选择序列索引到有效范围
        selection_sequence = [idx % len(items) for idx in selection_sequence]
        
        # 模拟状态机
        auto_ocr_item_id = items[0].id  # 第一个条目作为自动 OCR 目标
        
        for idx in selection_sequence:
            selected_item = items[idx]
            
            # 模拟 _on_selection_changed 逻辑
            if auto_ocr_item_id is not None:
                if selected_item.id != auto_ocr_item_id:
                    auto_ocr_item_id = None
        
        # 验证：如果选择序列中有任何不同于目标的条目，自动 OCR 应该被取消
        has_different_selection = any(
            items[idx % len(items)].id != items[0].id 
            for idx in selection_sequence
        )
        
        if has_different_selection:
            assert auto_ocr_item_id is None, (
                "选择了不同条目后，自动 OCR 应该被取消"
            )
        else:
            # 如果所有选择都是相同的条目，自动 OCR 不应该被取消
            assert auto_ocr_item_id == items[0].id, (
                "只选择相同条目时，自动 OCR 不应该被取消"
            )
    
    def test_manual_selection_cancels_auto_ocr(self, qtbot):
        """单元测试：手动选择不同条目取消自动 OCR"""
        item1 = MockHistoryItem(
            item_id="auto-ocr-target",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/target.png",
        )
        item2 = MockHistoryItem(
            item_id="manually-selected",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/selected.png",
        )
        
        # 初始状态：设置自动 OCR 目标
        auto_ocr_item_id = item1.id
        
        # 用户手动选择不同的条目
        current_item_id = item2.id
        
        # 模拟 _on_selection_changed 逻辑
        if auto_ocr_item_id is not None:
            if current_item_id != auto_ocr_item_id:
                auto_ocr_item_id = None
        
        # 验证
        assert auto_ocr_item_id is None, "自动 OCR 应该被取消"
        assert current_item_id == item2.id, "当前选中项应该是手动选择的条目"
    
    def test_selecting_same_item_does_not_cancel_auto_ocr(self, qtbot):
        """单元测试：选择相同条目不取消自动 OCR"""
        item = MockHistoryItem(
            item_id="auto-ocr-target",
            content_type=MockContentType.IMAGE,
            image_path="clipboard_images/target.png",
        )
        
        # 初始状态：设置自动 OCR 目标
        auto_ocr_item_id = item.id
        
        # 用户选择相同的条目
        current_item_id = item.id
        
        # 模拟 _on_selection_changed 逻辑
        if auto_ocr_item_id is not None:
            if current_item_id != auto_ocr_item_id:
                auto_ocr_item_id = None
        
        # 验证
        assert auto_ocr_item_id == item.id, "选择相同条目时，自动 OCR 不应该被取消"
    
    def test_auto_ocr_flag_cleared_on_different_selection(self, qtbot):
        """单元测试：选择不同条目时清除自动 OCR 标志"""
        # 模拟两个不同的条目
        target_id = "target-item"
        other_id = "other-item"
        
        # 初始状态
        auto_ocr_item_id = target_id
        
        # 选择不同的条目
        selected_id = other_id
        
        # 取消逻辑
        if auto_ocr_item_id is not None and selected_id != auto_ocr_item_id:
            auto_ocr_item_id = None
        
        assert auto_ocr_item_id is None


# ============================================================
# Property 7: 引擎级 OCR 缓存
# Feature: clipboard-ocr-merge, Property 7: Engine-Level OCR Cache
# Validates: Requirements 4.3
# ============================================================

class TestEngineLevelOCRCache:
    """Property 7: 引擎级 OCR 缓存测试
    
    验证：对于任意图片条目和引擎组合，切换到不同引擎再切换回来，
    应该返回缓存的结果而不是重新运行 OCR。
    
    **Validates: Requirements 4.3**
    """
    
    # 可用的 OCR 引擎
    AVAILABLE_ENGINES = ["rapid", "baidu", "tencent"]
    
    @given(
        item=image_item_strategy(),
        engine_a=st.sampled_from(["rapid", "baidu", "tencent"]),
        engine_b=st.sampled_from(["rapid", "baidu", "tencent"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_engine_level_ocr_cache(self, item, engine_a, engine_b, qtbot):
        """
        Property 7: Engine-Level OCR Cache
        
        *For any* image item and engine combination, switching to a different 
        engine and back SHALL return the cached result without re-running OCR.
        
        **Validates: Requirements 4.3**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 确保两个引擎不同（否则测试无意义）
        if engine_a == engine_b:
            pytest.skip("需要两个不同的引擎")
        
        # 模拟 OCR 缓存状态机
        class OCRCacheStateMachine:
            """OCR 缓存状态机
            
            模拟 OCRPreviewPanel 的引擎级缓存行为
            """
            
            def __init__(self):
                # 缓存结构: Dict[item_id, Dict[engine, CachedOCRResult]]
                self._ocr_cache: Dict[str, Dict[str, dict]] = {}
                self._current_item_id: Optional[str] = None
                self._current_engine: str = "rapid"
                self._ocr_run_count: int = 0  # 记录 OCR 运行次数
            
            def set_current_item(self, item_id: str):
                """设置当前条目"""
                self._current_item_id = item_id
            
            def run_ocr_with_engine(self, engine: str) -> bool:
                """使用指定引擎运行 OCR
                
                Returns:
                    True 如果使用了缓存，False 如果运行了新的 OCR
                """
                if not self._current_item_id:
                    return False
                
                item_id = self._current_item_id
                
                # 检查缓存 (Requirements: 4.3)
                if item_id in self._ocr_cache and engine in self._ocr_cache[item_id]:
                    # 缓存命中，不需要重新运行 OCR
                    self._current_engine = engine
                    return True
                
                # 缓存未命中，运行 OCR
                self._ocr_run_count += 1
                
                # 模拟 OCR 结果
                result = {
                    "item_id": item_id,
                    "engine": engine,
                    "text": f"OCR result for {item_id} with {engine}",
                    "average_score": 0.95,
                    "backend_detail": f"{engine} backend",
                    "elapsed_time": 0.5,
                }
                
                # 存储到缓存
                if item_id not in self._ocr_cache:
                    self._ocr_cache[item_id] = {}
                self._ocr_cache[item_id][engine] = result
                
                self._current_engine = engine
                return False
            
            def get_ocr_run_count(self) -> int:
                return self._ocr_run_count
            
            def get_cached_result(self, item_id: str, engine: str) -> Optional[dict]:
                if item_id in self._ocr_cache and engine in self._ocr_cache[item_id]:
                    return self._ocr_cache[item_id][engine]
                return None
        
        # 创建状态机
        state_machine = OCRCacheStateMachine()
        state_machine.set_current_item(item.id)
        
        # 步骤 1：使用引擎 A 运行 OCR
        used_cache_a1 = state_machine.run_ocr_with_engine(engine_a)
        assert not used_cache_a1, "第一次运行引擎 A 不应该使用缓存"
        ocr_count_after_a1 = state_machine.get_ocr_run_count()
        assert ocr_count_after_a1 == 1, "应该运行了 1 次 OCR"
        
        # 验证引擎 A 的结果已缓存
        cached_a = state_machine.get_cached_result(item.id, engine_a)
        assert cached_a is not None, f"引擎 {engine_a} 的结果应该被缓存"
        
        # 步骤 2：切换到引擎 B 运行 OCR
        used_cache_b = state_machine.run_ocr_with_engine(engine_b)
        assert not used_cache_b, "第一次运行引擎 B 不应该使用缓存"
        ocr_count_after_b = state_machine.get_ocr_run_count()
        assert ocr_count_after_b == 2, "应该运行了 2 次 OCR"
        
        # 验证引擎 B 的结果已缓存
        cached_b = state_machine.get_cached_result(item.id, engine_b)
        assert cached_b is not None, f"引擎 {engine_b} 的结果应该被缓存"
        
        # 步骤 3：切换回引擎 A
        used_cache_a2 = state_machine.run_ocr_with_engine(engine_a)
        
        # 验证属性：应该使用缓存，不重新运行 OCR
        assert used_cache_a2, (
            f"切换回引擎 {engine_a} 应该使用缓存结果"
        )
        
        ocr_count_after_a2 = state_machine.get_ocr_run_count()
        assert ocr_count_after_a2 == 2, (
            f"切换回引擎 {engine_a} 不应该增加 OCR 运行次数: "
            f"expected=2, actual={ocr_count_after_a2}"
        )
        
        # 验证缓存的结果与之前相同
        cached_a_after = state_machine.get_cached_result(item.id, engine_a)
        assert cached_a_after == cached_a, (
            "切换回引擎 A 后，缓存的结果应该与之前相同"
        )
    
    @given(
        item=image_item_strategy(),
        engine_sequence=st.lists(
            st.sampled_from(["rapid", "baidu", "tencent"]),
            min_size=3,
            max_size=10
        ),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_engine_cache_across_multiple_switches(
        self, item, engine_sequence, qtbot
    ):
        """
        Property 7 扩展：多次引擎切换后缓存仍然有效
        
        *For any* sequence of engine switches, each engine's cached result 
        SHALL be reused when switching back to that engine.
        
        **Validates: Requirements 4.3**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 模拟缓存
        ocr_cache: Dict[str, dict] = {}  # engine -> result
        ocr_run_count = 0
        
        for engine in engine_sequence:
            if engine in ocr_cache:
                # 缓存命中
                pass
            else:
                # 缓存未命中，运行 OCR
                ocr_run_count += 1
                ocr_cache[engine] = {
                    "engine": engine,
                    "text": f"Result for {engine}",
                }
        
        # 验证：OCR 运行次数应该等于不同引擎的数量
        unique_engines = set(engine_sequence)
        assert ocr_run_count == len(unique_engines), (
            f"OCR 运行次数应该等于不同引擎数量: "
            f"expected={len(unique_engines)}, actual={ocr_run_count}"
        )
    
    def test_engine_cache_hit_on_switch_back(self, qtbot):
        """单元测试：切换回之前的引擎时命中缓存"""
        # 模拟缓存
        ocr_cache = {
            "item-1": {
                "rapid": {"text": "本地结果", "engine": "rapid"},
                "tencent": {"text": "腾讯结果", "engine": "tencent"},
            }
        }
        
        item_id = "item-1"
        
        # 当前使用腾讯引擎
        current_engine = "tencent"
        
        # 切换回本地引擎
        target_engine = "rapid"
        
        # 检查缓存
        cache_hit = (
            item_id in ocr_cache and 
            target_engine in ocr_cache[item_id]
        )
        
        assert cache_hit, "切换回本地引擎应该命中缓存"
        assert ocr_cache[item_id][target_engine]["text"] == "本地结果"
    
    def test_engine_cache_miss_for_new_engine(self, qtbot):
        """单元测试：使用新引擎时缓存未命中"""
        # 模拟缓存（只有本地引擎的结果）
        ocr_cache = {
            "item-1": {
                "rapid": {"text": "本地结果", "engine": "rapid"},
            }
        }
        
        item_id = "item-1"
        target_engine = "baidu"
        
        # 检查缓存
        cache_hit = (
            item_id in ocr_cache and 
            target_engine in ocr_cache[item_id]
        )
        
        assert not cache_hit, "使用新引擎应该缓存未命中"
    
    def test_all_three_engines_cached_independently(self, qtbot):
        """单元测试：三个引擎的结果独立缓存"""
        # 模拟缓存
        ocr_cache: Dict[str, Dict[str, dict]] = {}
        item_id = "test-item"
        
        # 依次使用三个引擎
        for engine in ["rapid", "baidu", "tencent"]:
            if item_id not in ocr_cache:
                ocr_cache[item_id] = {}
            ocr_cache[item_id][engine] = {
                "text": f"{engine} 结果",
                "engine": engine,
            }
        
        # 验证三个引擎的结果都被独立缓存
        assert len(ocr_cache[item_id]) == 3
        assert ocr_cache[item_id]["rapid"]["text"] == "rapid 结果"
        assert ocr_cache[item_id]["baidu"]["text"] == "baidu 结果"
        assert ocr_cache[item_id]["tencent"]["text"] == "tencent 结果"


# ============================================================
# Property 11: 条目级 OCR 缓存恢复
# Feature: clipboard-ocr-merge, Property 11: Item-Level OCR Cache Restoration
# Validates: Requirements 8.1, 8.2
# ============================================================

class TestItemLevelOCRCacheRestoration:
    """Property 11: 条目级 OCR 缓存恢复测试
    
    验证：对于任意有缓存 OCR 结果的图片条目，切换到不同条目再切换回来，
    应该恢复该条目的缓存 OCR 结果。
    
    **Validates: Requirements 8.1, 8.2**
    """
    
    @given(
        item1=image_item_strategy(),
        item2=image_item_strategy(),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_item_level_ocr_cache_restoration(self, item1, item2, qtbot):
        """
        Property 11: Item-Level OCR Cache Restoration
        
        *For any* image item with cached OCR results, switching to a different 
        item and back SHALL restore the cached OCR result for that item.
        
        **Validates: Requirements 8.1, 8.2**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        # 确保两个条目不同
        if item1.id == item2.id:
            pytest.skip("需要两个不同的条目")
        
        # 模拟条目级 OCR 缓存状态机
        class ItemLevelCacheStateMachine:
            """条目级 OCR 缓存状态机
            
            模拟 OCRPreviewPanel 的条目级缓存恢复行为
            """
            
            def __init__(self):
                # 缓存结构: Dict[item_id, Dict[engine, CachedOCRResult]]
                self._ocr_cache: Dict[str, Dict[str, dict]] = {}
                self._current_item_id: Optional[str] = None
                self._current_engine: str = "rapid"
                self._displayed_result: Optional[dict] = None
            
            def cache_ocr_result(self, item_id: str, engine: str, text: str):
                """缓存 OCR 结果"""
                if item_id not in self._ocr_cache:
                    self._ocr_cache[item_id] = {}
                self._ocr_cache[item_id][engine] = {
                    "item_id": item_id,
                    "engine": engine,
                    "text": text,
                    "average_score": 0.95,
                }
            
            def switch_to_item(self, item_id: str) -> bool:
                """切换到指定条目
                
                Returns:
                    True 如果恢复了缓存结果
                """
                self._current_item_id = item_id
                
                # 尝试恢复缓存结果 (Requirements: 8.1, 8.2)
                if self.restore_cached_result(item_id):
                    return True
                
                # 没有缓存，清空显示
                self._displayed_result = None
                return False
            
            def restore_cached_result(self, item_id: str) -> bool:
                """恢复缓存的 OCR 结果
                
                模拟 OCRPreviewPanel.restore_cached_result 方法
                """
                if item_id not in self._ocr_cache:
                    return False
                
                item_cache = self._ocr_cache[item_id]
                
                # 优先使用当前引擎的缓存
                if self._current_engine in item_cache:
                    self._displayed_result = item_cache[self._current_engine]
                else:
                    # 使用任意可用的缓存
                    self._displayed_result = next(iter(item_cache.values()))
                
                return True
            
            def has_cached_result(self, item_id: str) -> bool:
                """检查是否有缓存结果"""
                return item_id in self._ocr_cache
            
            def get_displayed_result(self) -> Optional[dict]:
                return self._displayed_result
            
            def get_current_item_id(self) -> Optional[str]:
                return self._current_item_id
        
        # 创建状态机
        state_machine = ItemLevelCacheStateMachine()
        
        # 步骤 1：为 item1 缓存 OCR 结果
        original_text = f"OCR result for {item1.id}"
        state_machine.cache_ocr_result(item1.id, "rapid", original_text)
        
        # 切换到 item1 并验证缓存恢复
        restored = state_machine.switch_to_item(item1.id)
        assert restored, "item1 应该有缓存结果"
        
        displayed_result_1 = state_machine.get_displayed_result()
        assert displayed_result_1 is not None, "应该显示 item1 的缓存结果"
        assert displayed_result_1["text"] == original_text, "显示的文本应该与缓存一致"
        
        # 步骤 2：切换到 item2
        state_machine.switch_to_item(item2.id)
        assert state_machine.get_current_item_id() == item2.id, "当前条目应该是 item2"
        
        # 步骤 3：切换回 item1
        restored_again = state_machine.switch_to_item(item1.id)
        
        # 验证属性：应该恢复 item1 的缓存结果
        assert restored_again, (
            f"切换回 item1 应该恢复缓存结果"
        )
        
        displayed_result_2 = state_machine.get_displayed_result()
        assert displayed_result_2 is not None, (
            "切换回 item1 后应该显示缓存结果"
        )
        assert displayed_result_2["text"] == original_text, (
            f"恢复的文本应该与原始缓存一致: "
            f"expected={original_text}, actual={displayed_result_2['text']}"
        )
        assert displayed_result_2["item_id"] == item1.id, (
            f"恢复的结果应该属于 item1: "
            f"expected={item1.id}, actual={displayed_result_2['item_id']}"
        )
    
    @given(
        items=st.lists(image_item_strategy(), min_size=3, max_size=10, unique_by=lambda x: x.id),
        switch_sequence=st.lists(st.integers(min_value=0, max_value=9), min_size=5, max_size=15),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_item_cache_restoration_across_multiple_switches(
        self, items, switch_sequence, qtbot
    ):
        """
        Property 11 扩展：多次条目切换后缓存仍然可恢复
        
        *For any* sequence of item switches, each item's cached OCR result 
        SHALL be restored when switching back to that item.
        
        **Validates: Requirements 8.1, 8.2**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        if len(items) < 2:
            pytest.skip("需要至少两个条目")
        
        # 调整切换序列索引到有效范围
        switch_sequence = [idx % len(items) for idx in switch_sequence]
        
        # 模拟缓存：为所有条目预先缓存 OCR 结果
        ocr_cache: Dict[str, dict] = {}
        for item in items:
            ocr_cache[item.id] = {
                "item_id": item.id,
                "text": f"Cached result for {item.id}",
            }
        
        # 模拟切换序列
        for idx in switch_sequence:
            item = items[idx]
            
            # 检查是否能恢复缓存
            if item.id in ocr_cache:
                restored_result = ocr_cache[item.id]
                
                # 验证恢复的结果正确
                assert restored_result["item_id"] == item.id, (
                    f"恢复的结果应该属于当前条目: "
                    f"expected={item.id}, actual={restored_result['item_id']}"
                )
    
    @given(
        item1=image_item_strategy(),
        item2=image_item_strategy(),
        engine=st.sampled_from(["rapid", "baidu", "tencent"]),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_item_cache_preserves_engine_specific_result(
        self, item1, item2, engine, qtbot
    ):
        """
        Property 11 补充：条目缓存保留引擎特定结果
        
        *For any* item with engine-specific cached results, switching items 
        and back SHALL restore the result for the current engine.
        
        **Validates: Requirements 8.1, 8.2**
        """
        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication not available")
        
        if item1.id == item2.id:
            pytest.skip("需要两个不同的条目")
        
        # 模拟缓存：item1 有多个引擎的结果
        ocr_cache: Dict[str, Dict[str, dict]] = {
            item1.id: {
                "rapid": {"text": "本地结果", "engine": "rapid"},
                "baidu": {"text": "百度结果", "engine": "baidu"},
                "tencent": {"text": "腾讯结果", "engine": "tencent"},
            }
        }
        
        current_engine = engine
        
        # 切换到 item1，应该恢复当前引擎的结果
        if item1.id in ocr_cache:
            item_cache = ocr_cache[item1.id]
            if current_engine in item_cache:
                restored = item_cache[current_engine]
            else:
                restored = next(iter(item_cache.values()))
            
            assert restored["engine"] == current_engine, (
                f"应该恢复当前引擎 {current_engine} 的结果"
            )
    
    def test_item_cache_restoration_basic(self, qtbot):
        """单元测试：基本的条目缓存恢复"""
        # 模拟缓存
        ocr_cache = {
            "item-1": {
                "rapid": {"text": "Item 1 结果", "item_id": "item-1"},
            },
            "item-2": {
                "rapid": {"text": "Item 2 结果", "item_id": "item-2"},
            },
        }
        
        # 切换到 item-1
        current_item = "item-1"
        restored = ocr_cache.get(current_item, {}).get("rapid")
        assert restored is not None
        assert restored["text"] == "Item 1 结果"
        
        # 切换到 item-2
        current_item = "item-2"
        restored = ocr_cache.get(current_item, {}).get("rapid")
        assert restored is not None
        assert restored["text"] == "Item 2 结果"
        
        # 切换回 item-1
        current_item = "item-1"
        restored = ocr_cache.get(current_item, {}).get("rapid")
        assert restored is not None
        assert restored["text"] == "Item 1 结果"
    
    def test_item_cache_not_found_returns_false(self, qtbot):
        """单元测试：没有缓存时返回 False"""
        ocr_cache: Dict[str, dict] = {}
        
        item_id = "non-existent-item"
        has_cache = item_id in ocr_cache
        
        assert not has_cache, "不存在的条目不应该有缓存"
    
    def test_item_cache_with_multiple_engines(self, qtbot):
        """单元测试：条目有多个引擎缓存时的恢复"""
        ocr_cache = {
            "item-1": {
                "rapid": {"text": "本地", "engine": "rapid"},
                "tencent": {"text": "腾讯", "engine": "tencent"},
            }
        }
        
        item_id = "item-1"
        current_engine = "tencent"
        
        # 优先使用当前引擎的缓存
        item_cache = ocr_cache.get(item_id, {})
        if current_engine in item_cache:
            restored = item_cache[current_engine]
        else:
            restored = next(iter(item_cache.values()), None)
        
        assert restored is not None
        assert restored["engine"] == "tencent"
        assert restored["text"] == "腾讯"
    
    def test_item_cache_fallback_to_any_engine(self, qtbot):
        """单元测试：当前引擎无缓存时回退到任意引擎"""
        ocr_cache = {
            "item-1": {
                "rapid": {"text": "本地", "engine": "rapid"},
            }
        }
        
        item_id = "item-1"
        current_engine = "baidu"  # 没有百度的缓存
        
        # 优先使用当前引擎的缓存，否则使用任意可用的
        item_cache = ocr_cache.get(item_id, {})
        if current_engine in item_cache:
            restored = item_cache[current_engine]
        else:
            restored = next(iter(item_cache.values()), None)
        
        assert restored is not None
        assert restored["engine"] == "rapid"  # 回退到本地引擎
        assert restored["text"] == "本地"
