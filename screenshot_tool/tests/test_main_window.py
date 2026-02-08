# =====================================================
# =============== 主窗口测试 ===============
# =====================================================

"""
主窗口功能测试

Feature: main-window
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.ui.main_window import (
    FeatureDefinition,
    FEATURES,
    FEATURE_GROUPS,
    get_features_by_group,
    COLORS,
    SPACING,
    StatusBar,
)
from screenshot_tool.core.config_manager import MainWindowConfig


class TestFeatureDefinition:
    """FeatureDefinition 数据类测试
    
    Requirements: 2.1
    """
    
    def test_feature_definition_fields(self):
        """测试 FeatureDefinition 包含所有必需字段"""
        feature = FeatureDefinition(
            id="test",
            title="测试功能",
            description="这是一个测试功能",
            icon_name="test-icon",
            group="测试分组"
        )
        
        assert feature.id == "test"
        assert feature.title == "测试功能"
        assert feature.description == "这是一个测试功能"
        assert feature.icon_name == "test-icon"
        assert feature.group == "测试分组"
        assert feature.action is None
        assert feature.hotkey is None
        assert feature.vip_only is False
    
    def test_feature_definition_with_optional_fields(self):
        """测试 FeatureDefinition 可选字段"""
        def dummy_action():
            pass
        
        feature = FeatureDefinition(
            id="test",
            title="测试功能",
            description="这是一个测试功能",
            icon_name="test-icon",
            group="测试分组",
            action=dummy_action,
            hotkey="Alt+T",
            vip_only=True
        )
        
        assert feature.action is dummy_action
        assert feature.hotkey == "Alt+T"
        assert feature.vip_only is True


class TestFeaturesConstant:
    """FEATURES 常量测试
    
    Requirements: 2.1, 2.5
    """
    
    def test_features_not_empty(self):
        """测试 FEATURES 列表不为空"""
        assert len(FEATURES) > 0
    
    def test_all_features_have_required_fields(self):
        """测试所有功能都有必需字段"""
        for feature in FEATURES:
            assert feature.id, f"Feature missing id"
            assert feature.title, f"Feature {feature.id} missing title"
            assert feature.description, f"Feature {feature.id} missing description"
            assert feature.icon_name, f"Feature {feature.id} missing icon_name"
            assert feature.group, f"Feature {feature.id} missing group"
    
    def test_all_features_in_valid_groups(self):
        """测试所有功能都属于有效分组"""
        for feature in FEATURES:
            assert feature.group in FEATURE_GROUPS, \
                f"Feature {feature.id} has invalid group: {feature.group}"
    
    def test_feature_ids_unique(self):
        """测试功能 ID 唯一"""
        ids = [f.id for f in FEATURES]
        assert len(ids) == len(set(ids)), "Duplicate feature IDs found"
    
    def test_expected_features_exist(self):
        """测试预期的功能都存在
        
        注意：record 功能已移至截图工具栏，从主界面移除
        Feature: recording-settings-panel, Requirements: 6.1
        
        注意：ocr_panel 功能已集成到工作台窗口，从主界面移除
        Feature: clipboard-ocr-merge, Requirements: 7.1, 7.2
        """
        expected_ids = [
            "screenshot",
            "web_to_md", "file_to_md", "word_format",
            "regulation", "clipboard", "mouse_highlight"
        ]
        actual_ids = [f.id for f in FEATURES]
        for expected_id in expected_ids:
            assert expected_id in actual_ids, f"Expected feature {expected_id} not found"
    
    def test_ocr_panel_removed_from_features(self):
        """测试 ocr_panel 已从 FEATURES 移除
        
        Feature: clipboard-ocr-merge
        Requirements: 7.1
        
        OCR 功能已集成到工作台窗口，独立的 ocr_panel 入口应该被移除。
        """
        actual_ids = [f.id for f in FEATURES]
        assert "ocr_panel" not in actual_ids, "ocr_panel should be removed from FEATURES"
    
    def test_clipboard_still_in_features(self):
        """测试 clipboard（工作台）仍在 FEATURES 中
        
        Feature: clipboard-ocr-merge
        Requirements: 7.2
        
        工作台作为统一入口应该保留在 FEATURES 中。
        """
        actual_ids = [f.id for f in FEATURES]
        assert "clipboard" in actual_ids, "clipboard should remain in FEATURES as unified entry point"


class TestFeatureGroups:
    """功能分组测试
    
    Requirements: 2.5
    """
    
    def test_feature_groups_not_empty(self):
        """测试分组列表不为空"""
        assert len(FEATURE_GROUPS) > 0
    
    def test_expected_groups_exist(self):
        """测试预期的分组都存在"""
        expected_groups = ["截图工具", "文档处理", "辅助功能"]
        for group in expected_groups:
            assert group in FEATURE_GROUPS, f"Expected group {group} not found"
    
    def test_get_features_by_group(self):
        """测试按分组获取功能"""
        grouped = get_features_by_group()
        
        # 所有分组都应该存在
        for group in FEATURE_GROUPS:
            assert group in grouped
        
        # 每个分组都应该有功能
        for group, features in grouped.items():
            assert len(features) > 0, f"Group {group} has no features"
        
        # 所有功能都应该被分组
        total_features = sum(len(f) for f in grouped.values())
        assert total_features == len(FEATURES)


class TestMainWindowConfig:
    """MainWindowConfig 测试
    
    Requirements: 8.5
    """
    
    def test_default_values(self):
        """测试默认值"""
        config = MainWindowConfig()
        
        assert config.show_welcome is True
        assert config.window_x == -1
        assert config.window_y == -1
        assert config.window_width == 900
        assert config.window_height == 650
        assert config.show_on_startup is True
    
    def test_custom_values(self):
        """测试自定义值"""
        config = MainWindowConfig(
            show_welcome=False,
            window_x=100,
            window_y=200,
            window_width=1000,
            window_height=700,
            show_on_startup=False
        )
        
        assert config.show_welcome is False
        assert config.window_x == 100
        assert config.window_y == 200
        assert config.window_width == 1000
        assert config.window_height == 700
        assert config.show_on_startup is False
    
    def test_width_clamping(self):
        """测试宽度范围限制"""
        # 太小
        config = MainWindowConfig(window_width=100)
        assert config.window_width == MainWindowConfig.MIN_WIDTH
        
        # 太大
        config = MainWindowConfig(window_width=5000)
        assert config.window_width == MainWindowConfig.MAX_WIDTH
    
    def test_height_clamping(self):
        """测试高度范围限制"""
        # 太小
        config = MainWindowConfig(window_height=100)
        assert config.window_height == MainWindowConfig.MIN_HEIGHT
        
        # 太大
        config = MainWindowConfig(window_height=5000)
        assert config.window_height == MainWindowConfig.MAX_HEIGHT


class TestColors:
    """颜色常量测试
    
    Requirements: 7.1
    """
    
    def test_colors_not_empty(self):
        """测试颜色常量不为空"""
        assert len(COLORS) > 0
    
    def test_required_colors_exist(self):
        """测试必需的颜色都存在"""
        required_colors = [
            "primary", "secondary", "cta", "background",
            "text", "text_muted", "border", "success", "warning",
            "card_bg", "card_hover"
        ]
        for color in required_colors:
            assert color in COLORS, f"Required color {color} not found"
    
    def test_colors_are_valid_hex(self):
        """测试所有颜色都是有效的十六进制格式"""
        for name, color in COLORS.items():
            assert color.startswith("#"), f"Color {name} should start with #"
            assert len(color) == 7, f"Color {name} should be 7 characters"
            # 验证是有效的十六进制
            try:
                int(color[1:], 16)
            except ValueError:
                pytest.fail(f"Color {name} is not valid hex: {color}")


class TestSpacing:
    """间距常量测试
    
    Requirements: 7.3
    """
    
    def test_spacing_not_empty(self):
        """测试间距常量不为空"""
        assert len(SPACING) > 0
    
    def test_required_spacing_exist(self):
        """测试必需的间距都存在"""
        required_spacing = ["xs", "sm", "md", "lg", "xl"]
        for spacing in required_spacing:
            assert spacing in SPACING, f"Required spacing {spacing} not found"
    
    def test_spacing_are_positive_integers(self):
        """测试所有间距都是正整数"""
        for name, value in SPACING.items():
            assert isinstance(value, int), f"Spacing {name} should be int"
            assert value > 0, f"Spacing {name} should be positive"
    
    def test_spacing_order(self):
        """测试间距大小顺序正确"""
        assert SPACING["xs"] < SPACING["sm"]
        assert SPACING["sm"] < SPACING["md"]
        assert SPACING["md"] < SPACING["lg"]
        assert SPACING["lg"] < SPACING["xl"]



# =====================================================
# FeatureCard 属性测试
# =====================================================

class TestFeatureCardContent:
    """FeatureCard 内容完整性测试
    
    Property 1: Feature Card Content Completeness
    *For any* FeatureCard instance, the card SHALL contain a non-empty icon,
    a non-empty title, and a non-empty description.
    
    **Validates: Requirements 2.2**
    """
    
    @given(
        feature_id=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        icon_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        title=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        description=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_feature_card_content_completeness(
        self, feature_id, icon_name, title, description, qtbot
    ):
        """Property 1: 功能卡片内容完整性
        
        Feature: main-window, Property 1: Feature Card Content Completeness
        **Validates: Requirements 2.2**
        """
        from screenshot_tool.ui.main_window import FeatureCard
        
        card = FeatureCard(
            feature_id=feature_id,
            icon_name=icon_name,
            title=title,
            description=description
        )
        qtbot.addWidget(card)
        
        # 验证内容完整性
        assert card.feature_id == feature_id
        assert card.title == title
        assert card.description == description
        assert card.icon_name == icon_name
        
        # 验证 UI 元素存在且非空
        assert card._title_label.text()  # 标题标签有文本
        assert card._desc_label.text()   # 描述标签有文本
        assert card._icon_label.pixmap() is not None  # 图标存在


class TestFeatureCardClick:
    """FeatureCard 点击测试
    
    Property 2: Feature Card Click Triggers Action
    *For any* FeatureCard with a valid action callback, clicking the card
    SHALL invoke the associated action exactly once.
    
    **Validates: Requirements 2.4**
    """
    
    def test_feature_card_click_emits_signal(self, qtbot):
        """测试点击卡片发出信号"""
        from screenshot_tool.ui.main_window import FeatureCard
        from PySide6.QtCore import Qt
        
        card = FeatureCard(
            feature_id="test",
            icon_name="test",
            title="测试",
            description="测试描述"
        )
        qtbot.addWidget(card)
        
        # 监听信号
        with qtbot.waitSignal(card.clicked, timeout=1000):
            qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    
    def test_feature_card_enter_key_emits_signal(self, qtbot):
        """测试 Enter 键发出信号"""
        from screenshot_tool.ui.main_window import FeatureCard
        from PySide6.QtCore import Qt
        
        card = FeatureCard(
            feature_id="test",
            icon_name="test",
            title="测试",
            description="测试描述"
        )
        qtbot.addWidget(card)
        card.show()
        card.setFocus()
        
        # 监听信号
        with qtbot.waitSignal(card.clicked, timeout=1000):
            qtbot.keyClick(card, Qt.Key.Key_Return)
    
    @given(
        feature_id=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        title=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_feature_card_click_triggers_action(self, feature_id, title, qtbot):
        """Property 2: 功能卡片点击触发动作
        
        Feature: main-window, Property 2: Feature Card Click Triggers Action
        **Validates: Requirements 2.4**
        """
        from screenshot_tool.ui.main_window import FeatureCard
        from PySide6.QtCore import Qt
        
        card = FeatureCard(
            feature_id=feature_id,
            icon_name="test",
            title=title,
            description="测试描述"
        )
        qtbot.addWidget(card)
        
        # 记录点击次数
        click_count = [0]
        
        def on_click():
            click_count[0] += 1
        
        card.clicked.connect(on_click)
        
        # 点击卡片
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
        
        # 验证动作被调用恰好一次
        assert click_count[0] == 1



# =====================================================
# StatusBar 属性测试
# =====================================================

class TestStatusBarIndicator:
    """StatusBar 状态指示器测试
    
    Property 4: Status Indicator Reflects Hotkey State
    *For any* hotkey registration state (registered, waiting, failed), the StatusBar
    SHALL display the corresponding indicator color and text.
    
    **Validates: Requirements 6.2, 6.3**
    """
    
    def test_status_registered(self, qtbot):
        """测试已注册状态显示"""
        from screenshot_tool.ui.main_window import StatusBar, COLORS
        
        status_bar = StatusBar()
        qtbot.addWidget(status_bar)
        
        status_bar.update_hotkey_status(StatusBar.STATUS_REGISTERED)
        
        assert status_bar.hotkey_status == StatusBar.STATUS_REGISTERED
        assert status_bar.get_indicator_color() == COLORS["success"]
        assert "已注册" in status_bar.get_status_text()
    
    def test_status_waiting(self, qtbot):
        """测试等待状态显示"""
        from screenshot_tool.ui.main_window import StatusBar, COLORS
        
        status_bar = StatusBar()
        qtbot.addWidget(status_bar)
        
        status_bar.update_hotkey_status(StatusBar.STATUS_WAITING)
        
        assert status_bar.hotkey_status == StatusBar.STATUS_WAITING
        assert status_bar.get_indicator_color() == COLORS["warning"]
        assert "等待" in status_bar.get_status_text()
    
    def test_status_failed(self, qtbot):
        """测试失败状态显示"""
        from screenshot_tool.ui.main_window import StatusBar, COLORS
        
        status_bar = StatusBar()
        qtbot.addWidget(status_bar)
        
        status_bar.update_hotkey_status(StatusBar.STATUS_FAILED)
        
        assert status_bar.hotkey_status == StatusBar.STATUS_FAILED
        assert status_bar.get_indicator_color() == COLORS["warning"]
        assert "冲突" in status_bar.get_status_text()
    
    @given(
        status=st.sampled_from([
            StatusBar.STATUS_REGISTERED,
            StatusBar.STATUS_WAITING,
            StatusBar.STATUS_FAILED
        ])
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_status_indicator_reflects_state(self, status, qtbot):
        """Property 4: 状态指示器反映热键状态
        
        Feature: main-window, Property 4: Status Indicator Reflects Hotkey State
        **Validates: Requirements 6.2, 6.3**
        """
        from screenshot_tool.ui.main_window import StatusBar, COLORS
        
        status_bar = StatusBar()
        qtbot.addWidget(status_bar)
        
        status_bar.update_hotkey_status(status)
        
        # 验证状态被正确设置
        assert status_bar.hotkey_status == status
        
        # 验证颜色和文字对应
        if status == StatusBar.STATUS_REGISTERED:
            assert status_bar.get_indicator_color() == COLORS["success"]
            assert "已注册" in status_bar.get_status_text()
        elif status == StatusBar.STATUS_WAITING:
            assert status_bar.get_indicator_color() == COLORS["warning"]
            assert "等待" in status_bar.get_status_text()
        else:  # failed
            assert status_bar.get_indicator_color() == COLORS["warning"]
            assert "冲突" in status_bar.get_status_text()


class TestStatusBarSubscription:
    """StatusBar 订阅状态测试
    
    **Validates: Requirements 6.4**
    """
    


# =====================================================
# QuickActionBar 属性测试
# =====================================================

class TestQuickActionBarClick:
    """QuickActionBar 点击测试
    
    Property 3: Quick Action Click Triggers Action
    *For any* Quick Action button with a valid action callback, clicking the button
    SHALL invoke the associated action exactly once.
    
    **Validates: Requirements 3.4**
    """
    
    def test_screenshot_button_emits_signal(self, qtbot):
        """测试截图按钮点击发出信号"""
        from screenshot_tool.ui.main_window import QuickActionBar
        from PySide6.QtCore import Qt
        
        bar = QuickActionBar(hotkey="Alt+A")
        qtbot.addWidget(bar)
        
        # 监听信号
        with qtbot.waitSignal(bar.screenshot_clicked, timeout=1000):
            qtbot.mouseClick(bar._screenshot_btn, Qt.MouseButton.LeftButton)
    
    def test_settings_button_emits_signal(self, qtbot):
        """测试设置按钮点击发出信号"""
        from screenshot_tool.ui.main_window import QuickActionBar
        from PySide6.QtCore import Qt
        
        bar = QuickActionBar(hotkey="Alt+A")
        qtbot.addWidget(bar)
        
        # 监听信号
        with qtbot.waitSignal(bar.settings_clicked, timeout=1000):
            qtbot.mouseClick(bar._settings_btn, Qt.MouseButton.LeftButton)
    
    @given(
        hotkey=st.text(min_size=1, max_size=10).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_quick_action_click_triggers_action(self, hotkey, qtbot):
        """Property 3: 快捷操作点击触发动作
        
        Feature: main-window, Property 3: Quick Action Click Triggers Action
        **Validates: Requirements 3.4**
        """
        from screenshot_tool.ui.main_window import QuickActionBar
        from PySide6.QtCore import Qt
        
        bar = QuickActionBar(hotkey=hotkey)
        qtbot.addWidget(bar)
        
        # 记录点击次数
        screenshot_count = [0]
        settings_count = [0]
        
        def on_screenshot():
            screenshot_count[0] += 1
        
        def on_settings():
            settings_count[0] += 1
        
        bar.screenshot_clicked.connect(on_screenshot)
        bar.settings_clicked.connect(on_settings)
        
        # 点击截图按钮
        qtbot.mouseClick(bar._screenshot_btn, Qt.MouseButton.LeftButton)
        assert screenshot_count[0] == 1, "截图按钮应该触发恰好一次"
        
        # 点击设置按钮
        qtbot.mouseClick(bar._settings_btn, Qt.MouseButton.LeftButton)
        assert settings_count[0] == 1, "设置按钮应该触发恰好一次"


class TestColorContrastAccessibility:
    """颜色对比度无障碍测试
    
    Property 5: Color Contrast Accessibility
    *For any* text element in the StatusBar, the contrast ratio between text color
    and background color SHALL be at least 4.5:1.
    
    **Validates: Requirements 6.5**
    """
    
    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        """将十六进制颜色转换为 RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    @staticmethod
    def _relative_luminance(rgb: tuple) -> float:
        """计算相对亮度 (WCAG 2.1)"""
        def adjust(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        
        r, g, b = rgb
        return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)
    
    @staticmethod
    def _contrast_ratio(color1: str, color2: str) -> float:
        """计算两个颜色的对比度"""
        rgb1 = TestColorContrastAccessibility._hex_to_rgb(color1)
        rgb2 = TestColorContrastAccessibility._hex_to_rgb(color2)
        
        l1 = TestColorContrastAccessibility._relative_luminance(rgb1)
        l2 = TestColorContrastAccessibility._relative_luminance(rgb2)
        
        lighter = max(l1, l2)
        darker = min(l1, l2)
        
        return (lighter + 0.05) / (darker + 0.05)
    
    def test_text_contrast_on_background(self):
        """测试文本颜色与背景的对比度"""
        from screenshot_tool.ui.main_window import COLORS
        
        # 主文本与背景
        ratio = self._contrast_ratio(COLORS["text"], COLORS["background"])
        assert ratio >= 4.5, f"主文本对比度不足: {ratio:.2f}"
        
        # 次要文本与背景
        ratio = self._contrast_ratio(COLORS["text_muted"], COLORS["background"])
        assert ratio >= 4.5, f"次要文本对比度不足: {ratio:.2f}"
    
    def test_status_indicator_contrast(self):
        """测试状态指示器颜色对比度"""
        from screenshot_tool.ui.main_window import COLORS
        
        # 成功状态（绿色）与背景
        ratio = self._contrast_ratio(COLORS["success"], COLORS["background"])
        # 图标颜色对比度要求可以稍低（3:1）
        assert ratio >= 3.0, f"成功状态对比度不足: {ratio:.2f}"
        
        # 警告状态（橙色）与背景
        ratio = self._contrast_ratio(COLORS["warning"], COLORS["background"])
        assert ratio >= 3.0, f"警告状态对比度不足: {ratio:.2f}"
    
    @given(
        status=st.sampled_from([
            StatusBar.STATUS_REGISTERED,
            StatusBar.STATUS_WAITING,
            StatusBar.STATUS_FAILED
        ])
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_status_bar_contrast_accessibility(self, status, qtbot):
        """Property 5: 状态栏颜色对比度无障碍
        
        Feature: main-window, Property 5: Color Contrast Accessibility
        **Validates: Requirements 6.5**
        """
        from screenshot_tool.ui.main_window import StatusBar, COLORS
        
        status_bar = StatusBar()
        qtbot.addWidget(status_bar)
        
        status_bar.update_hotkey_status(status)
        
        # 获取当前指示器颜色
        indicator_color = status_bar.get_indicator_color()
        
        # 验证指示器颜色与背景的对比度
        ratio = self._contrast_ratio(indicator_color, COLORS["background"])
        assert ratio >= 3.0, f"状态 {status} 的指示器对比度不足: {ratio:.2f}"



# =====================================================
# MainWindow 集成测试
# =====================================================

class TestMainWindowIntegration:
    """MainWindow 集成测试
    
    测试主窗口与各组件的交互。
    
    **Validates: Requirements 4.2, 4.3, 5.2**
    """
    
    def test_main_window_creation(self, qtbot):
        """测试主窗口创建"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证窗口属性
        assert window.windowTitle()
        assert window.minimumWidth() >= 800
        assert window.minimumHeight() >= 600
    
    def test_main_window_with_config_manager(self, qtbot):
        """测试主窗口与配置管理器集成"""
        from screenshot_tool.ui.main_window import MainWindow
        from screenshot_tool.core.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        window = MainWindow(config_manager=config_manager)
        qtbot.addWidget(window)
        
        # 验证配置管理器已设置
        assert window._config_manager is config_manager
    
    def test_main_window_feature_groups_exist(self, qtbot):
        """测试功能分组存在"""
        from screenshot_tool.ui.main_window import MainWindow, FEATURE_GROUPS
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证所有分组都已创建
        for group_name in FEATURE_GROUPS:
            assert group_name in window._feature_groups
    
    def test_main_window_feature_cards_exist(self, qtbot):
        """测试功能卡片存在"""
        from screenshot_tool.ui.main_window import MainWindow, FEATURES
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证所有功能卡片都已创建
        for feature in FEATURES:
            assert feature.id in window._feature_cards
    
    def test_main_window_status_bar_exists(self, qtbot):
        """测试状态栏存在"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证状态栏存在
        assert window._status_bar is not None
    
    def test_main_window_quick_action_bar_exists(self, qtbot):
        """测试快捷操作栏存在"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证快捷操作栏存在
        assert window._quick_action_bar is not None
    
    def test_main_window_welcome_overlay_exists(self, qtbot):
        """测试欢迎覆盖层存在"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证欢迎覆盖层存在
        assert window._welcome_overlay is not None
    
    def test_main_window_show_and_activate(self, qtbot):
        """测试显示并激活窗口"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 调用 show_and_activate
        window.show_and_activate()
        
        # 验证窗口可见
        assert window.isVisible()
    
    def test_main_window_close_hides_window(self, qtbot):
        """测试关闭窗口时隐藏而不是退出"""
        from screenshot_tool.ui.main_window import MainWindow
        from PySide6.QtGui import QCloseEvent
        
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 模拟关闭事件
        event = QCloseEvent()
        window.closeEvent(event)
        
        # 验证事件被忽略（窗口隐藏而不是关闭）
        assert event.isAccepted() is False
    
    def test_main_window_escape_hides_window(self, qtbot):
        """测试 Escape 键隐藏窗口"""
        from screenshot_tool.ui.main_window import MainWindow
        from PySide6.QtCore import Qt
        
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        
        # 按 Escape 键
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        
        # 验证窗口隐藏
        assert window.isVisible() is False
    
    def test_main_window_feature_callback_registration(self, qtbot):
        """测试功能回调注册"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 注册回调
        callback_called = [False]
        
        def test_callback():
            callback_called[0] = True
        
        window.register_feature_callback("screenshot", test_callback)
        
        # 验证回调已注册
        assert "screenshot" in window._feature_callbacks
        
        # 触发回调
        window._feature_callbacks["screenshot"]()
        assert callback_called[0] is True
    
    def test_main_window_screenshot_signal(self, qtbot):
        """测试截图信号"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 监听信号
        with qtbot.waitSignal(window.screenshot_requested, timeout=1000):
            window._quick_action_bar.screenshot_clicked.emit()
    
    def test_main_window_settings_signal(self, qtbot):
        """测试设置信号"""
        from screenshot_tool.ui.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 监听信号
        with qtbot.waitSignal(window.settings_requested, timeout=1000):
            window._quick_action_bar.settings_clicked.emit()
    
    def test_main_window_hotkey_status_update(self, qtbot):
        """测试热键状态更新"""
        from screenshot_tool.ui.main_window import MainWindow, StatusBar
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 更新热键状态
        window.update_hotkey_status(StatusBar.STATUS_FAILED)
        
        # 验证状态栏已更新
        assert window._status_bar.hotkey_status == StatusBar.STATUS_FAILED
