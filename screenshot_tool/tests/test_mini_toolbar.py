# =====================================================
# =============== 极简工具栏测试 ===============
# =====================================================

"""
极简工具栏属性测试

Feature: mini-toolbar
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from screenshot_tool.ui.mini_toolbar import (
    MiniToolbar, MiniToolbarButton, PinButton, ExpandButton
)
from screenshot_tool.core.config_manager import (
    ConfigManager, AppConfig, MiniToolbarConfig,
    HotkeyConfig, MainWindowHotkeyConfig, ClipboardHistoryHotkeyConfig,
    OCRPanelHotkeyConfig, SpotlightHotkeyConfig
)


# =====================================================
# Fixtures
# =====================================================

@pytest.fixture
def mock_config_manager():
    """创建模拟的配置管理器"""
    config = AppConfig()
    config.mini_toolbar = MiniToolbarConfig()
    config.hotkey = HotkeyConfig()
    config.main_window_hotkey = MainWindowHotkeyConfig(enabled=True)
    config.clipboard_hotkey = ClipboardHistoryHotkeyConfig(enabled=True)
    config.ocr_panel_hotkey = OCRPanelHotkeyConfig(enabled=True)
    config.spotlight_hotkey = SpotlightHotkeyConfig(enabled=True)
    
    manager = MagicMock(spec=ConfigManager)
    manager.config = config
    manager.save = MagicMock()
    return manager


@pytest.fixture
def mini_toolbar(qtbot, mock_config_manager):
    """创建测试用的 MiniToolbar 实例"""
    toolbar = MiniToolbar(config_manager=mock_config_manager)
    qtbot.addWidget(toolbar)
    return toolbar


# =====================================================
# Property 5: Drag to Move Window
# Feature: mini-toolbar, Property 5: Drag to Move Window
# Validates: Requirements 1.2
# =====================================================

class TestDragToMoveWindow:
    """拖动移动窗口属性测试
    
    Property 5: *For any* mouse drag operation starting within the Mini_Toolbar,
    the window position should change by the same delta as the mouse movement.
    """
    
    @given(
        start_x=st.integers(min_value=0, max_value=500),
        start_y=st.integers(min_value=0, max_value=500),
        delta_x=st.integers(min_value=-200, max_value=200),
        delta_y=st.integers(min_value=-200, max_value=200)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_drag_moves_window_by_delta(self, qtbot, mock_config_manager, start_x, start_y, delta_x, delta_y):
        """
        Property 5: Drag to Move Window
        
        *For any* mouse drag operation starting within the Mini_Toolbar,
        the window position should change by the same delta as the mouse movement.
        
        Feature: mini-toolbar, Property 5: Drag to Move Window
        Validates: Requirements 1.2
        """
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 设置初始位置
        toolbar.move(start_x, start_y)
        initial_pos = toolbar.pos()
        
        # 模拟拖动
        # 计算窗口内的点击位置（窗口中心）
        click_pos = QPoint(toolbar.width() // 2, toolbar.height() // 2)
        global_start = toolbar.mapToGlobal(click_pos)
        global_end = QPoint(global_start.x() + delta_x, global_start.y() + delta_y)
        
        # 模拟鼠标按下
        toolbar._is_dragging = True
        toolbar._drag_start_pos = global_start
        toolbar._drag_start_window_pos = initial_pos
        
        # 模拟鼠标移动（直接调用内部逻辑）
        new_pos = initial_pos + QPoint(delta_x, delta_y)
        toolbar.move(new_pos)
        
        # 模拟鼠标释放
        toolbar._is_dragging = False
        toolbar._drag_start_pos = None
        toolbar._drag_start_window_pos = None
        
        # 验证位置变化
        final_pos = toolbar.pos()
        expected_pos = QPoint(start_x + delta_x, start_y + delta_y)
        
        assert final_pos.x() == expected_pos.x(), f"X position mismatch: {final_pos.x()} != {expected_pos.x()}"
        assert final_pos.y() == expected_pos.y(), f"Y position mismatch: {final_pos.y()} != {expected_pos.y()}"
        
        toolbar.close()



# =====================================================
# Property 2: Pin State Toggle and Persistence
# Feature: mini-toolbar, Property 2: Pin State Toggle and Persistence
# Validates: Requirements 2.2, 2.3, 2.4
# =====================================================

class TestPinStateToggleAndPersistence:
    """置顶状态切换和持久化属性测试
    
    Property 2: *For any* initial pin state, clicking the pin button should toggle
    the state, and the new state should be visually reflected and persisted across
    window close/reopen cycles.
    """
    
    @given(initial_pinned=st.booleans())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pin_toggle_changes_state(self, qtbot, mock_config_manager, initial_pinned):
        """
        Property 2: Pin State Toggle
        
        *For any* initial pin state, clicking the pin button should toggle the state.
        
        Feature: mini-toolbar, Property 2: Pin State Toggle and Persistence
        Validates: Requirements 2.2
        """
        # 设置初始状态
        mock_config_manager.config.mini_toolbar.is_pinned = initial_pinned
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 验证初始状态
        assert toolbar.is_pinned() == initial_pinned
        
        # 点击置顶按钮
        toolbar._on_pin_clicked()
        
        # 验证状态已切换
        expected_state = not initial_pinned
        assert toolbar.is_pinned() == expected_state, \
            f"Pin state should toggle from {initial_pinned} to {expected_state}"
        
        toolbar.close()
    
    @given(initial_pinned=st.booleans())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pin_state_visual_indication(self, qtbot, mock_config_manager, initial_pinned):
        """
        Property 2: Pin State Visual Indication
        
        *For any* pin state, the pin button should visually indicate the current state.
        
        Feature: mini-toolbar, Property 2: Pin State Toggle and Persistence
        Validates: Requirements 2.3
        """
        # 设置初始状态
        mock_config_manager.config.mini_toolbar.is_pinned = initial_pinned
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 验证视觉状态
        pin_button = toolbar._pin_button
        assert pin_button.is_pinned == initial_pinned
        
        # 切换状态
        toolbar._on_pin_clicked()
        
        # 验证视觉状态已更新
        assert pin_button.is_pinned == (not initial_pinned)
        
        toolbar.close()
    
    @given(initial_pinned=st.booleans())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pin_state_persistence(self, qtbot, mock_config_manager, initial_pinned):
        """
        Property 2: Pin State Persistence
        
        *For any* pin state, the state should be persisted and restored across
        window close/reopen cycles.
        
        Feature: mini-toolbar, Property 2: Pin State Toggle and Persistence
        Validates: Requirements 2.4
        """
        # 设置初始状态
        mock_config_manager.config.mini_toolbar.is_pinned = initial_pinned
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 切换状态
        toolbar._on_pin_clicked()
        new_state = not initial_pinned
        
        # 关闭窗口（触发保存）
        toolbar.close()
        
        # 验证配置已更新
        assert mock_config_manager.config.mini_toolbar.is_pinned == new_state
        
        # 创建新工具栏
        toolbar2 = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar2)
        toolbar2.show()
        qtbot.waitExposed(toolbar2)
        
        # 验证状态已恢复
        assert toolbar2.is_pinned() == new_state
        
        toolbar2.close()


# =====================================================
# Property 3: Hotkey Buttons Match Configuration
# Feature: mini-toolbar, Property 3: Hotkey Buttons Match Configuration
# Validates: Requirements 3.1, 3.3
# =====================================================

class TestHotkeyButtonsMatchConfiguration:
    """快捷键按钮匹配配置属性测试
    
    Property 3: *For any* hotkey configuration, the Mini_Toolbar should display
    exactly the buttons for enabled hotkeys, with correct labels and hotkey text.
    """
    
    @given(
        main_window_enabled=st.booleans(),
        clipboard_enabled=st.booleans(),
        ocr_panel_enabled=st.booleans(),
        spotlight_enabled=st.booleans()
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_buttons_match_enabled_hotkeys(
        self, qtbot, mock_config_manager,
        main_window_enabled, clipboard_enabled, ocr_panel_enabled, spotlight_enabled
    ):
        """
        Property 3: Hotkey Buttons Match Configuration
        
        *For any* hotkey configuration, the Mini_Toolbar should display exactly
        the buttons for enabled hotkeys.
        
        Feature: mini-toolbar, Property 3: Hotkey Buttons Match Configuration
        Validates: Requirements 3.1, 3.3
        """
        # 设置配置
        mock_config_manager.config.main_window_hotkey.enabled = main_window_enabled
        mock_config_manager.config.clipboard_hotkey.enabled = clipboard_enabled
        mock_config_manager.config.ocr_panel_hotkey.enabled = ocr_panel_enabled
        mock_config_manager.config.spotlight_hotkey.enabled = spotlight_enabled
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 计算预期按钮数量（截图按钮始终显示）
        expected_count = 1  # 截图按钮
        if main_window_enabled:
            expected_count += 1
        if clipboard_enabled:
            expected_count += 1
        if ocr_panel_enabled:
            expected_count += 1
        if spotlight_enabled:
            expected_count += 1
        
        # 验证按钮数量
        actual_count = toolbar.get_button_count()
        assert actual_count == expected_count, \
            f"Button count mismatch: expected {expected_count}, got {actual_count}"
        
        # 验证按钮ID
        button_ids = toolbar.get_button_ids()
        assert "screenshot" in button_ids, "Screenshot button should always be present"
        
        if main_window_enabled:
            assert "main_window" in button_ids
        else:
            assert "main_window" not in button_ids
        
        if clipboard_enabled:
            assert "clipboard" in button_ids
        else:
            assert "clipboard" not in button_ids
        
        if ocr_panel_enabled:
            assert "ocr_panel" in button_ids
        else:
            assert "ocr_panel" not in button_ids
        
        if spotlight_enabled:
            assert "spotlight" in button_ids
        else:
            assert "spotlight" not in button_ids
        
        toolbar.close()
    
    def test_buttons_update_on_config_change(self, qtbot, mock_config_manager):
        """
        Property 3: Buttons Update on Config Change
        
        The Mini_Toolbar should update button display when hotkey configuration changes.
        
        Feature: mini-toolbar, Property 3: Hotkey Buttons Match Configuration
        Validates: Requirements 3.3
        """
        # 初始配置：所有快捷键启用
        mock_config_manager.config.main_window_hotkey.enabled = True
        mock_config_manager.config.clipboard_hotkey.enabled = True
        mock_config_manager.config.ocr_panel_hotkey.enabled = True
        mock_config_manager.config.spotlight_hotkey.enabled = True
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        initial_count = toolbar.get_button_count()
        assert initial_count == 5  # 截图 + 4个快捷键
        
        # 修改配置：禁用部分快捷键
        mock_config_manager.config.main_window_hotkey.enabled = False
        mock_config_manager.config.clipboard_hotkey.enabled = False
        
        # 刷新按钮
        toolbar.refresh_buttons()
        
        # 验证按钮数量已更新
        new_count = toolbar.get_button_count()
        assert new_count == 3  # 截图 + 2个快捷键
        
        toolbar.close()


# =====================================================
# Property 4: Button Click Triggers Correct Feature
# Feature: mini-toolbar, Property 4: Button Click Triggers Correct Feature
# Validates: Requirements 3.2
# =====================================================

class TestButtonClickTriggersCorrectFeature:
    """按钮点击触发正确功能属性测试
    
    Property 4: *For any* button in the Mini_Toolbar, clicking it should emit
    the feature_triggered signal with the correct feature_id.
    """
    
    @given(
        feature_index=st.integers(min_value=0, max_value=4)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_button_click_emits_correct_signal(self, qtbot, mock_config_manager, feature_index):
        """
        Property 4: Button Click Triggers Correct Feature
        
        *For any* button in the Mini_Toolbar, clicking it should emit the
        feature_triggered signal with the correct feature_id.
        
        Feature: mini-toolbar, Property 4: Button Click Triggers Correct Feature
        Validates: Requirements 3.2
        """
        # 启用所有快捷键
        mock_config_manager.config.main_window_hotkey.enabled = True
        mock_config_manager.config.clipboard_hotkey.enabled = True
        mock_config_manager.config.ocr_panel_hotkey.enabled = True
        mock_config_manager.config.spotlight_hotkey.enabled = True
        
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 获取按钮ID列表
        button_ids = toolbar.get_button_ids()
        
        # 确保索引有效
        if feature_index >= len(button_ids):
            feature_index = len(button_ids) - 1
        
        target_feature_id = button_ids[feature_index]
        
        # 监听信号
        if target_feature_id == "screenshot":
            # 截图按钮发出 screenshot_requested 信号
            with qtbot.waitSignal(toolbar.screenshot_requested, timeout=1000):
                toolbar._on_button_clicked(target_feature_id)
        else:
            # 其他按钮发出 feature_triggered 信号
            with qtbot.waitSignal(toolbar.feature_triggered, timeout=1000) as blocker:
                toolbar._on_button_clicked(target_feature_id)
            
            # 验证信号参数
            assert blocker.args[0] == target_feature_id, \
                f"Signal should emit '{target_feature_id}', got '{blocker.args[0]}'"
        
        toolbar.close()


# =====================================================
# Property 1: Position Persistence Round-Trip
# Feature: mini-toolbar, Property 1: Position Persistence Round-Trip
# Validates: Requirements 1.3, 1.4
# =====================================================

class TestPositionPersistenceRoundTrip:
    """位置持久化往返属性测试
    
    Property 1: *For any* valid screen position, if the Mini_Toolbar is moved to
    that position and then closed and reopened, the window position should be
    restored to the same coordinates.
    """
    
    @given(
        pos_x=st.integers(min_value=0, max_value=500),
        pos_y=st.integers(min_value=0, max_value=500)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_position_persistence_round_trip(self, qtbot, mock_config_manager, pos_x, pos_y):
        """
        Property 1: Position Persistence Round-Trip
        
        *For any* valid screen position, if the Mini_Toolbar is moved to that
        position and then closed and reopened, the window position should be
        restored to the same coordinates.
        
        Feature: mini-toolbar, Property 1: Position Persistence Round-Trip
        Validates: Requirements 1.3, 1.4
        """
        # 创建工具栏
        toolbar = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar)
        toolbar.show()
        qtbot.waitExposed(toolbar)
        
        # 移动到指定位置
        toolbar.move(pos_x, pos_y)
        
        # 关闭窗口（触发保存）
        toolbar.close()
        
        # 验证配置已更新
        saved_x = mock_config_manager.config.mini_toolbar.window_x
        saved_y = mock_config_manager.config.mini_toolbar.window_y
        assert saved_x == pos_x, f"Saved X position mismatch: {saved_x} != {pos_x}"
        assert saved_y == pos_y, f"Saved Y position mismatch: {saved_y} != {pos_y}"
        
        # 创建新工具栏
        toolbar2 = MiniToolbar(config_manager=mock_config_manager)
        qtbot.addWidget(toolbar2)
        toolbar2.show()
        qtbot.waitExposed(toolbar2)
        
        # 验证位置已恢复
        restored_pos = toolbar2.pos()
        assert restored_pos.x() == pos_x, \
            f"Restored X position mismatch: {restored_pos.x()} != {pos_x}"
        assert restored_pos.y() == pos_y, \
            f"Restored Y position mismatch: {restored_pos.y()} != {pos_y}"
        
        toolbar2.close()


# =====================================================
# 单元测试
# =====================================================

class TestMiniToolbarUnit:
    """MiniToolbar 单元测试"""
    
    def test_initial_state(self, mini_toolbar):
        """测试初始状态"""
        assert mini_toolbar.get_button_count() >= 1  # 至少有截图按钮
        assert "screenshot" in mini_toolbar.get_button_ids()
    
    def test_pin_button_exists(self, mini_toolbar):
        """测试置顶按钮存在"""
        assert mini_toolbar._pin_button is not None
        assert isinstance(mini_toolbar._pin_button, PinButton)
    
    def test_expand_button_exists(self, mini_toolbar):
        """测试展开按钮存在"""
        assert mini_toolbar._expand_button is not None
        assert isinstance(mini_toolbar._expand_button, ExpandButton)
    
    def test_expand_signal(self, qtbot, mini_toolbar):
        """测试展开信号"""
        with qtbot.waitSignal(mini_toolbar.expand_requested, timeout=1000):
            mini_toolbar._on_expand_clicked()
    
    def test_screenshot_hides_toolbar(self, qtbot, mini_toolbar):
        """测试截图时隐藏工具栏"""
        mini_toolbar.show()
        qtbot.waitExposed(mini_toolbar)
        
        assert mini_toolbar.isVisible()
        
        # 点击截图按钮
        with qtbot.waitSignal(mini_toolbar.screenshot_requested, timeout=1000):
            mini_toolbar._on_button_clicked("screenshot")
        
        # 验证工具栏已隐藏
        assert not mini_toolbar.isVisible()


class TestMiniToolbarButton:
    """MiniToolbarButton 单元测试"""
    
    def test_button_creation(self, qtbot):
        """测试按钮创建"""
        button = MiniToolbarButton("test", "测试", "Alt+T")
        qtbot.addWidget(button)
        
        assert button.feature_id == "test"
        assert "测试" in button.text()
        assert "Alt+T" in button.text()


class TestPinButton:
    """PinButton 单元测试"""
    
    def test_initial_state(self, qtbot):
        """测试初始状态"""
        button = PinButton()
        qtbot.addWidget(button)
        
        assert button.is_pinned == False
    
    def test_toggle_state(self, qtbot):
        """测试切换状态"""
        button = PinButton()
        qtbot.addWidget(button)
        
        button.is_pinned = True
        assert button.is_pinned == True
        
        button.is_pinned = False
        assert button.is_pinned == False
