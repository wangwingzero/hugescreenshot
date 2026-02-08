# =====================================================
# =============== 帮助组件测试 ===============
# =====================================================

"""
帮助组件单元测试和属性测试

Feature: settings-help-improvement
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# 跳过 GUI 测试如果没有显示器
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from screenshot_tool.ui.ui_components import (
    InfoIconLabel,
    CollapsibleHelpPanel,
    HelpGroupBox,
)
from screenshot_tool.ui.help_texts import (
    SETTINGS_HELP_TEXT,
    GROUP_DESCRIPTIONS,
    HELP_PANEL_ITEMS,
    get_help_text,
    get_group_description,
    get_help_panel_items,
)


# ============================================================
# InfoIconLabel 测试
# ============================================================

class TestInfoIconLabel:
    """InfoIconLabel 组件测试"""
    
    @pytest.fixture
    def label_with_help(self, qtbot):
        """创建带帮助文字的标签"""
        label = InfoIconLabel("测试标签", "这是帮助文字")
        qtbot.addWidget(label)
        return label
    
    @pytest.fixture
    def label_without_help(self, qtbot):
        """创建不带帮助文字的标签"""
        label = InfoIconLabel("测试标签")
        qtbot.addWidget(label)
        return label
    
    def test_init_with_help_text(self, label_with_help):
        """测试带帮助文字的初始化
        
        Feature: settings-help-improvement
        Requirements: 1.1, 1.2
        """
        assert label_with_help.text() == "测试标签"
        assert label_with_help.help_text() == "这是帮助文字"
        assert label_with_help.has_info_icon() is True
    
    def test_init_without_help_text(self, label_without_help):
        """测试不带帮助文字的初始化
        
        Feature: settings-help-improvement
        Requirements: 1.1
        """
        assert label_without_help.text() == "测试标签"
        assert label_without_help.help_text() == ""
        assert label_without_help.has_info_icon() is False
    
    def test_set_help_text(self, label_with_help):
        """测试更新帮助文字
        
        Feature: settings-help-improvement
        Requirements: 1.2
        """
        label_with_help.set_help_text("新的帮助文字")
        assert label_with_help.help_text() == "新的帮助文字"
    
    def test_info_icon_cursor(self, label_with_help):
        """测试信息图标光标样式
        
        Feature: settings-help-improvement
        Requirements: 1.3
        """
        # 信息图标应该有 WhatsThis 光标
        assert label_with_help._info_icon.cursor().shape() == Qt.CursorShape.WhatsThisCursor


# ============================================================
# CollapsibleHelpPanel 测试
# ============================================================

class TestCollapsibleHelpPanel:
    """CollapsibleHelpPanel 组件测试"""
    
    @pytest.fixture
    def panel_few_items(self, qtbot):
        """创建少量项的面板（不折叠）"""
        panel = CollapsibleHelpPanel(
            title="帮助",
            items=["项目1", "项目2"],
            collapsed_threshold=3
        )
        qtbot.addWidget(panel)
        return panel
    
    @pytest.fixture
    def panel_many_items(self, qtbot):
        """创建多项的面板（默认折叠）"""
        panel = CollapsibleHelpPanel(
            title="帮助",
            items=["项目1", "项目2", "项目3", "项目4", "项目5"],
            collapsed_threshold=3
        )
        qtbot.addWidget(panel)
        return panel
    
    def test_init_few_items_not_collapsed(self, panel_few_items):
        """测试少量项时默认不折叠
        
        Feature: settings-help-improvement
        Requirements: 3.2
        """
        assert panel_few_items.is_collapsed() is False
        assert panel_few_items.item_count() == 2
    
    def test_init_many_items_collapsed(self, panel_many_items):
        """测试多项时默认折叠
        
        Feature: settings-help-improvement
        Requirements: 3.2
        """
        assert panel_many_items.is_collapsed() is True
        assert panel_many_items.item_count() == 5
    
    def test_toggle_collapsed(self, panel_many_items):
        """测试切换折叠状态
        
        Feature: settings-help-improvement
        Requirements: 3.3
        """
        # 初始折叠
        assert panel_many_items.is_collapsed() is True
        
        # 展开
        panel_many_items.toggle_collapsed()
        assert panel_many_items.is_collapsed() is False
        
        # 再次折叠
        panel_many_items.toggle_collapsed()
        assert panel_many_items.is_collapsed() is True
    
    def test_toggle_button_click(self, panel_many_items, qtbot):
        """测试点击折叠按钮
        
        Feature: settings-help-improvement
        Requirements: 3.3
        """
        # 初始折叠
        assert panel_many_items.is_collapsed() is True
        
        # 点击展开
        panel_many_items._toggle_btn.click()
        assert panel_many_items.is_collapsed() is False
    
    def test_set_items(self, panel_few_items):
        """测试设置新的帮助项
        
        Feature: settings-help-improvement
        Requirements: 3.1
        """
        new_items = ["新项目1", "新项目2", "新项目3", "新项目4"]
        panel_few_items.set_items(new_items)
        
        assert panel_few_items.item_count() == 4
        # 超过阈值，应该折叠
        assert panel_few_items.is_collapsed() is True
    
    def test_count_label_visibility(self, panel_many_items):
        """测试项数标签可见性
        
        Feature: settings-help-improvement
        Requirements: 3.4
        """
        # 折叠时显示项数（使用 isHidden 因为窗口未显示）
        assert panel_many_items._count_label.isHidden() is False
        assert "(5 项)" in panel_many_items._count_label.text()
        
        # 展开时隐藏项数
        panel_many_items.toggle_collapsed()
        assert panel_many_items._count_label.isHidden() is True


# ============================================================
# HelpGroupBox 测试
# ============================================================

class TestHelpGroupBox:
    """HelpGroupBox 组件测试"""
    
    @pytest.fixture
    def group_with_desc(self, qtbot):
        """创建带描述的分组框"""
        group = HelpGroupBox("测试分组", "这是分组描述")
        qtbot.addWidget(group)
        return group
    
    @pytest.fixture
    def group_without_desc(self, qtbot):
        """创建不带描述的分组框"""
        group = HelpGroupBox("测试分组")
        qtbot.addWidget(group)
        return group
    
    def test_init_with_description(self, group_with_desc):
        """测试带描述的初始化
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        assert group_with_desc.title() == "测试分组"
        assert group_with_desc.description() == "这是分组描述"
    
    def test_init_without_description(self, group_without_desc):
        """测试不带描述的初始化
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        assert group_without_desc.title() == "测试分组"
        assert group_without_desc.description() == ""
    
    def test_set_description(self, group_with_desc):
        """测试设置描述
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        group_with_desc.set_description("新的描述")
        assert group_with_desc.description() == "新的描述"
    
    def test_add_widget(self, group_with_desc, qtbot):
        """测试添加组件
        
        Feature: settings-help-improvement
        Requirements: 4.2
        """
        label = QLabel("测试内容")
        group_with_desc.add_widget(label)
        
        # 检查组件已添加到内容布局
        layout = group_with_desc.content_layout()
        assert layout.count() > 0
    
    def test_content_layout_not_none(self, group_with_desc):
        """测试内容布局不为空
        
        Feature: settings-help-improvement
        Requirements: 4.2
        """
        assert group_with_desc.content_layout() is not None


# ============================================================
# 帮助文本配置测试
# ============================================================

class TestHelpTexts:
    """帮助文本配置测试"""
    
    def test_settings_help_text_not_empty(self):
        """测试设置帮助文本不为空
        
        Feature: settings-help-improvement
        Requirements: 2.1
        """
        assert len(SETTINGS_HELP_TEXT) > 0
    
    def test_group_descriptions_not_empty(self):
        """测试分组描述不为空
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        assert len(GROUP_DESCRIPTIONS) > 0
    
    def test_help_panel_items_not_empty(self):
        """测试帮助面板内容不为空
        
        Feature: settings-help-improvement
        Requirements: 3.1
        """
        assert len(HELP_PANEL_ITEMS) > 0
    
    def test_get_help_text_existing(self):
        """测试获取存在的帮助文本
        
        Feature: settings-help-improvement
        Requirements: 2.1
        """
        text = get_help_text("save_path")
        assert text != ""
        assert isinstance(text, str)
    
    def test_get_help_text_not_existing(self):
        """测试获取不存在的帮助文本
        
        Feature: settings-help-improvement
        Requirements: 2.1
        """
        text = get_help_text("non_existing_key")
        assert text == ""
    
    def test_get_group_description_existing(self):
        """测试获取存在的分组描述
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        desc = get_group_description("general")
        assert desc != ""
        assert isinstance(desc, str)
    
    def test_get_group_description_not_existing(self):
        """测试获取不存在的分组描述
        
        Feature: settings-help-improvement
        Requirements: 4.1
        """
        desc = get_group_description("non_existing_group")
        assert desc == ""
    
    def test_get_help_panel_items_existing(self):
        """测试获取存在的帮助面板内容
        
        Feature: settings-help-improvement
        Requirements: 3.1
        """
        items = get_help_panel_items("ocr")
        assert len(items) > 0
        assert isinstance(items, list)
    
    def test_get_help_panel_items_not_existing(self):
        """测试获取不存在的帮助面板内容
        
        Feature: settings-help-improvement
        Requirements: 3.1
        """
        items = get_help_panel_items("non_existing_tab")
        assert items == []


# ============================================================
# 属性测试 (Hypothesis)
# ============================================================

class TestInfoIconLabelProperty:
    """InfoIconLabel 属性测试
    
    Property 2: Style Compliance
    Validates: Requirements 1.3, 1.4
    """
    
    @given(
        text=st.text(min_size=1, max_size=50),
        help_text=st.text(min_size=0, max_size=200)
    )
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_label_text_preserved(self, text, help_text):
        """Property: 标签文字始终被保留
        
        Validates: Requirements 1.1
        """
        label = InfoIconLabel(text, help_text)
        assert label.text() == text
        assert label.help_text() == help_text
    
    @given(help_text=st.text(min_size=1, max_size=200))
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_info_icon_present_when_help_text(self, help_text):
        """Property: 有帮助文字时显示信息图标
        
        Validates: Requirements 1.2
        """
        label = InfoIconLabel("测试", help_text)
        assert label.has_info_icon() is True


class TestCollapsibleHelpPanelProperty:
    """CollapsibleHelpPanel 属性测试
    
    Property 2: Style Compliance
    Validates: Requirements 3.1, 3.2, 3.3
    """
    
    @given(
        items=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=10),
        threshold=st.integers(min_value=1, max_value=10)
    )
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_collapse_threshold_respected(self, items, threshold):
        """Property: 折叠阈值被正确遵守
        
        Validates: Requirements 3.2
        """
        panel = CollapsibleHelpPanel(
            title="测试",
            items=items,
            collapsed_threshold=threshold
        )
        
        if len(items) > threshold:
            assert panel.is_collapsed() is True
        else:
            assert panel.is_collapsed() is False
    
    @given(items=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=10))
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_item_count_correct(self, items):
        """Property: 项数统计正确
        
        Validates: Requirements 3.4
        """
        panel = CollapsibleHelpPanel(title="测试", items=items)
        assert panel.item_count() == len(items)
    
    @given(items=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10))
    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_toggle_changes_state(self, items):
        """Property: 切换操作改变折叠状态
        
        Validates: Requirements 3.3
        """
        panel = CollapsibleHelpPanel(title="测试", items=items)
        initial_state = panel.is_collapsed()
        
        panel.toggle_collapsed()
        assert panel.is_collapsed() != initial_state
        
        panel.toggle_collapsed()
        assert panel.is_collapsed() == initial_state


class TestHelpGroupBoxProperty:
    """HelpGroupBox 属性测试
    
    Property 2: Style Compliance
    Validates: Requirements 4.2, 4.3
    """
    
    @given(
        title=st.text(min_size=1, max_size=30),
        description=st.text(min_size=0, max_size=100)
    )
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_title_and_description_preserved(self, title, description):
        """Property: 标题和描述始终被保留
        
        Validates: Requirements 4.1
        """
        group = HelpGroupBox(title, description)
        assert group.title() == title
        assert group.description() == description
    
    @given(description=st.text(min_size=0, max_size=100))
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_content_layout_always_available(self, description):
        """Property: 内容布局始终可用
        
        Validates: Requirements 4.2
        """
        group = HelpGroupBox("测试", description)
        assert group.content_layout() is not None


class TestHelpTextsProperty:
    """帮助文本属性测试
    
    Property 2: Style Compliance
    Validates: Requirements 2.1, 2.2
    """
    
    def test_all_help_texts_are_strings(self):
        """Property: 所有帮助文本都是字符串
        
        Validates: Requirements 2.1
        """
        for key, value in SETTINGS_HELP_TEXT.items():
            assert isinstance(key, str), f"Key {key} is not a string"
            assert isinstance(value, str), f"Value for {key} is not a string"
    
    def test_all_group_descriptions_are_strings(self):
        """Property: 所有分组描述都是字符串
        
        Validates: Requirements 4.1
        """
        for key, value in GROUP_DESCRIPTIONS.items():
            assert isinstance(key, str), f"Key {key} is not a string"
            assert isinstance(value, str), f"Value for {key} is not a string"
    
    def test_all_help_panel_items_are_lists(self):
        """Property: 所有帮助面板内容都是列表
        
        Validates: Requirements 3.1
        """
        for key, value in HELP_PANEL_ITEMS.items():
            assert isinstance(key, str), f"Key {key} is not a string"
            assert isinstance(value, list), f"Value for {key} is not a list"
            for item in value:
                assert isinstance(item, str), f"Item in {key} is not a string"
    
    def test_help_texts_not_too_long(self):
        """Property: 帮助文本不超过 100 字符（简洁性）
        
        Validates: Requirements 2.2
        """
        for key, value in SETTINGS_HELP_TEXT.items():
            assert len(value) <= 100, f"Help text for {key} is too long: {len(value)} chars"
    
    def test_group_descriptions_not_too_long(self):
        """Property: 分组描述不超过 50 字符（一行）
        
        Validates: Requirements 4.1
        """
        for key, value in GROUP_DESCRIPTIONS.items():
            assert len(value) <= 50, f"Group description for {key} is too long: {len(value)} chars"
