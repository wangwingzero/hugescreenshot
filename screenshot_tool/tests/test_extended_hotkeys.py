# =====================================================
# =============== 扩展快捷键测试 ===============
# =====================================================

"""
扩展快捷键测试 - 测试主界面、工作台、OCR面板、聚光灯快捷键配置

Feature: extended-hotkeys
Requirements: 1.1-1.7, 2.1-2.5, 3.1-3.7, 4.1-4.9
Property 1: Configuration Default Values
Property 2: Configuration Validation
Property 3: Configuration Round-Trip
Property 4: HotkeyChip Display Format
Property 5: QuickActionBar Button Count
Property 6: Hotkey Conflict Detection
"""

import json
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import (
    MainWindowHotkeyConfig,
    ClipboardHistoryHotkeyConfig,
    OCRPanelHotkeyConfig,
    SpotlightHotkeyConfig,
    AppConfig,
)


# =====================================================
# Property 1: Configuration Default Values
# =====================================================

class TestExtendedHotkeyDefaults:
    """测试扩展快捷键配置默认值
    
    Property 1: Configuration Default Values
    Validates: Requirements 1.1, 1.2, 1.3, 1.4
    """
    
    def test_main_window_hotkey_defaults(self):
        """测试主界面快捷键默认值"""
        config = MainWindowHotkeyConfig()
        assert config.enabled is False
        assert config.modifier == "ctrl+alt"
        assert config.key == "x"
    
    def test_clipboard_hotkey_defaults(self):
        """测试工作台快捷键默认值"""
        config = ClipboardHistoryHotkeyConfig()
        assert config.enabled is False
        assert config.modifier == "alt"
        assert config.key == "p"
    
    def test_ocr_panel_hotkey_defaults(self):
        """测试OCR面板快捷键默认值"""
        config = OCRPanelHotkeyConfig()
        assert config.enabled is False
        assert config.modifier == "alt"
        assert config.key == "o"
    
    def test_spotlight_hotkey_defaults(self):
        """测试聚光灯快捷键默认值"""
        config = SpotlightHotkeyConfig()
        assert config.enabled is False
        assert config.modifier == "alt"
        assert config.key == "s"
    
    def test_app_config_has_extended_hotkeys(self):
        """测试 AppConfig 包含扩展快捷键字段"""
        config = AppConfig()
        assert hasattr(config, 'main_window_hotkey')
        assert hasattr(config, 'clipboard_hotkey')
        assert hasattr(config, 'ocr_panel_hotkey')
        assert hasattr(config, 'spotlight_hotkey')
        
        assert isinstance(config.main_window_hotkey, MainWindowHotkeyConfig)
        assert isinstance(config.clipboard_hotkey, ClipboardHistoryHotkeyConfig)
        assert isinstance(config.ocr_panel_hotkey, OCRPanelHotkeyConfig)
        assert isinstance(config.spotlight_hotkey, SpotlightHotkeyConfig)


# =====================================================
# Property 2: Configuration Validation
# =====================================================

class TestExtendedHotkeyValidation:
    """测试扩展快捷键配置验证
    
    Property 2: Configuration Validation
    Validates: Requirements 1.1-1.4 validation logic
    """
    
    def test_invalid_modifier_normalized(self):
        """测试无效修饰键被规范化为默认值"""
        config = MainWindowHotkeyConfig(modifier="invalid")
        assert config.modifier == "ctrl+alt"  # 默认值
    
    def test_invalid_key_normalized(self):
        """测试无效主键被规范化为默认值"""
        config = MainWindowHotkeyConfig(key="invalid")
        assert config.key == "x"  # 默认值
    
    def test_valid_modifiers_accepted(self):
        """测试有效修饰键被接受"""
        valid_modifiers = ["alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"]
        for modifier in valid_modifiers:
            config = MainWindowHotkeyConfig(modifier=modifier)
            assert config.modifier == modifier
    
    def test_valid_keys_accepted(self):
        """测试有效主键被接受"""
        # 测试字母键
        for char in "abcdefghijklmnopqrstuvwxyz":
            config = MainWindowHotkeyConfig(key=char)
            assert config.key == char
        
        # 测试数字键
        for num in "0123456789":
            config = MainWindowHotkeyConfig(key=num)
            assert config.key == num
        
        # 测试功能键
        for i in range(1, 13):
            config = MainWindowHotkeyConfig(key=f"f{i}")
            assert config.key == f"f{i}"
    
    def test_enabled_bool_conversion(self):
        """测试 enabled 字段布尔转换"""
        config = MainWindowHotkeyConfig(enabled=True)
        assert config.enabled is True
        
        config = MainWindowHotkeyConfig(enabled=False)
        assert config.enabled is False
    
    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_arbitrary_modifier_normalized(self, modifier: str):
        """Property 2: 任意修饰键字符串都应被规范化"""
        config = MainWindowHotkeyConfig(modifier=modifier)
        assert config.modifier in MainWindowHotkeyConfig.VALID_MODIFIERS
    
    @given(st.text(min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_arbitrary_key_normalized(self, key: str):
        """Property 2: 任意主键字符串都应被规范化"""
        config = MainWindowHotkeyConfig(key=key)
        assert config.key in MainWindowHotkeyConfig.VALID_KEYS


# =====================================================
# Property 3: Configuration Round-Trip
# =====================================================

class TestExtendedHotkeyRoundTrip:
    """测试扩展快捷键配置序列化往返
    
    Property 3: Configuration Round-Trip
    Validates: Requirements 1.6, 1.7
    """
    
    def test_main_window_hotkey_round_trip(self):
        """测试主界面快捷键配置往返"""
        original = MainWindowHotkeyConfig(
            enabled=True,
            modifier="ctrl+alt",
            key="m"
        )
        
        # 序列化
        data = {
            "enabled": original.enabled,
            "modifier": original.modifier,
            "key": original.key,
        }
        json_str = json.dumps(data)
        
        # 反序列化
        loaded_data = json.loads(json_str)
        restored = MainWindowHotkeyConfig(**loaded_data)
        
        assert restored.enabled == original.enabled
        assert restored.modifier == original.modifier
        assert restored.key == original.key
    
    @given(
        enabled=st.booleans(),
        modifier=st.sampled_from(["alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"]),
        key=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789"))
    )
    @settings(max_examples=50)
    def test_config_round_trip_property(self, enabled: bool, modifier: str, key: str):
        """Property 3: 序列化后反序列化应产生等价配置"""
        original = ClipboardHistoryHotkeyConfig(
            enabled=enabled,
            modifier=modifier,
            key=key
        )
        
        # 序列化
        data = {
            "enabled": original.enabled,
            "modifier": original.modifier,
            "key": original.key,
        }
        json_str = json.dumps(data)
        
        # 反序列化
        loaded_data = json.loads(json_str)
        restored = ClipboardHistoryHotkeyConfig(**loaded_data)
        
        assert restored.enabled == original.enabled
        assert restored.modifier == original.modifier
        assert restored.key == original.key
    
    def test_app_config_extended_hotkeys_round_trip(self):
        """测试 AppConfig 中扩展快捷键的往返"""
        config = AppConfig()
        config.main_window_hotkey = MainWindowHotkeyConfig(enabled=True, modifier="ctrl+alt", key="m")
        config.clipboard_hotkey = ClipboardHistoryHotkeyConfig(enabled=True, modifier="alt", key="c")
        config.ocr_panel_hotkey = OCRPanelHotkeyConfig(enabled=False, modifier="alt", key="o")
        config.spotlight_hotkey = SpotlightHotkeyConfig(enabled=True, modifier="alt", key="l")
        
        # 序列化
        data = config.to_dict()
        json_str = json.dumps(data)
        
        # 反序列化
        loaded_data = json.loads(json_str)
        restored = AppConfig.from_dict(loaded_data)
        
        assert restored.main_window_hotkey.enabled == config.main_window_hotkey.enabled
        assert restored.main_window_hotkey.modifier == config.main_window_hotkey.modifier
        assert restored.main_window_hotkey.key == config.main_window_hotkey.key
        
        assert restored.clipboard_hotkey.enabled == config.clipboard_hotkey.enabled
        assert restored.ocr_panel_hotkey.enabled == config.ocr_panel_hotkey.enabled
        assert restored.spotlight_hotkey.enabled == config.spotlight_hotkey.enabled


# =====================================================
# Property 4: HotkeyChip Display Format
# =====================================================

class TestHotkeyChipDisplayFormat:
    """测试快捷键按钮显示格式
    
    Property 4: HotkeyChip Display Format
    Validates: Requirements 3.4, 3.5, 3.6
    """
    
    def test_get_hotkey_string_format(self):
        """测试 get_hotkey_string() 返回正确格式"""
        config = MainWindowHotkeyConfig(modifier="ctrl+alt", key="x")
        hotkey_str = config.get_hotkey_string()
        assert hotkey_str == "ctrl+alt+x"
    
    def test_get_hotkey_string_single_modifier(self):
        """测试单修饰键格式"""
        config = ClipboardHistoryHotkeyConfig(modifier="alt", key="p")
        hotkey_str = config.get_hotkey_string()
        assert hotkey_str == "alt+p"
    
    def test_get_hotkey_string_function_key(self):
        """测试功能键格式"""
        config = OCRPanelHotkeyConfig(modifier="ctrl", key="f1")
        hotkey_str = config.get_hotkey_string()
        assert hotkey_str == "ctrl+f1"
    
    @given(
        modifier=st.sampled_from(["alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"]),
        key=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz"))
    )
    @settings(max_examples=30)
    def test_hotkey_string_format_consistent(self, modifier: str, key: str):
        """Property 4: 快捷键字符串格式应一致"""
        config = SpotlightHotkeyConfig(modifier=modifier, key=key)
        hotkey_str = config.get_hotkey_string()
        
        # 检查格式为 modifier+key
        assert hotkey_str == f"{modifier}+{key}"


# =====================================================
# Property 5: QuickActionBar Button Count
# =====================================================

class TestQuickActionBarButtonCount:
    """测试快捷操作栏按钮数量
    
    Property 5: QuickActionBar Button Count
    Validates: Requirements 3.1, 3.2, 3.4, 3.7
    
    注意：这些测试需要 Qt 环境，在 CI 中可能需要跳过
    """
    
    @pytest.fixture
    def qt_app(self):
        """创建 Qt 应用实例"""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    
    def test_screenshot_button_always_shown(self, qt_app):
        """测试截图按钮始终显示"""
        from screenshot_tool.ui.main_window import QuickActionBar
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 创建配置管理器（所有扩展快捷键禁用）
        config_manager = ConfigManager()
        config_manager.config.main_window_hotkey.enabled = False
        config_manager.config.clipboard_hotkey.enabled = False
        config_manager.config.ocr_panel_hotkey.enabled = False
        config_manager.config.spotlight_hotkey.enabled = False
        
        # 创建 QuickActionBar
        bar = QuickActionBar(hotkey="Alt+X", config_manager=config_manager)
        
        # 截图按钮应始终存在
        assert bar.get_chip_count() >= 1
        assert "screenshot" in bar._chips
        
        bar.deleteLater()
    
    def test_enabled_hotkeys_shown(self, qt_app):
        """测试启用的快捷键显示为按钮"""
        from screenshot_tool.ui.main_window import QuickActionBar
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 创建配置管理器（启用部分快捷键）
        config_manager = ConfigManager()
        config_manager.config.main_window_hotkey.enabled = True
        config_manager.config.clipboard_hotkey.enabled = True
        config_manager.config.ocr_panel_hotkey.enabled = False
        config_manager.config.spotlight_hotkey.enabled = False
        config_manager.config.mouse_highlight_hotkey.enabled = False
        
        # 创建 QuickActionBar
        bar = QuickActionBar(hotkey="Alt+X", config_manager=config_manager)
        
        # 应有 3 个按钮：截图 + 主界面 + 剪贴板
        assert bar.get_chip_count() == 3
        assert "screenshot" in bar._chips
        assert "main_window" in bar._chips
        assert "clipboard" in bar._chips
        assert "ocr_panel" not in bar._chips
        assert "spotlight" not in bar._chips
        assert "mouse_highlight" not in bar._chips
        
        bar.deleteLater()
    
    def test_all_hotkeys_enabled(self, qt_app):
        """测试所有快捷键启用时的按钮数量"""
        from screenshot_tool.ui.main_window import QuickActionBar
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 创建配置管理器（启用所有快捷键）
        config_manager = ConfigManager()
        config_manager.config.main_window_hotkey.enabled = True
        config_manager.config.clipboard_hotkey.enabled = True
        config_manager.config.ocr_panel_hotkey.enabled = True
        config_manager.config.spotlight_hotkey.enabled = True
        config_manager.config.mouse_highlight_hotkey.enabled = True
        
        # 创建 QuickActionBar
        bar = QuickActionBar(hotkey="Alt+X", config_manager=config_manager)
        
        # 应有 6 个按钮：截图 + 5 个扩展快捷键
        assert bar.get_chip_count() == 6
        
        bar.deleteLater()


# =====================================================
# Property 6: Hotkey Conflict Detection
# =====================================================

class TestHotkeyConflictDetection:
    """测试快捷键冲突检测
    
    Property 6: Hotkey Conflict Detection
    Validates: Requirements 4.6, 4.7
    """
    
    def test_same_hotkey_is_conflict(self):
        """测试相同快捷键被检测为冲突"""
        # 两个配置使用相同的快捷键
        config1 = MainWindowHotkeyConfig(enabled=True, modifier="alt", key="x")
        config2 = ClipboardHistoryHotkeyConfig(enabled=True, modifier="alt", key="x")
        
        # 检查是否冲突
        hotkey1 = config1.get_hotkey_string()
        hotkey2 = config2.get_hotkey_string()
        
        assert hotkey1 == hotkey2  # 相同快捷键
    
    def test_different_hotkeys_no_conflict(self):
        """测试不同快捷键无冲突"""
        config1 = MainWindowHotkeyConfig(enabled=True, modifier="ctrl+alt", key="x")
        config2 = ClipboardHistoryHotkeyConfig(enabled=True, modifier="alt", key="p")
        
        hotkey1 = config1.get_hotkey_string()
        hotkey2 = config2.get_hotkey_string()
        
        assert hotkey1 != hotkey2  # 不同快捷键
    
    def test_disabled_hotkey_no_conflict(self):
        """测试禁用的快捷键不参与冲突检测"""
        # 即使快捷键相同，禁用的不应参与冲突检测
        config1 = MainWindowHotkeyConfig(enabled=True, modifier="alt", key="x")
        config2 = ClipboardHistoryHotkeyConfig(enabled=False, modifier="alt", key="x")
        
        # 只有启用的快捷键才需要检测冲突
        enabled_hotkeys = []
        if config1.enabled:
            enabled_hotkeys.append(config1.get_hotkey_string())
        if config2.enabled:
            enabled_hotkeys.append(config2.get_hotkey_string())
        
        # 只有一个启用的快捷键，无冲突
        assert len(enabled_hotkeys) == len(set(enabled_hotkeys))
    
    def test_conflict_detection_helper(self):
        """测试冲突检测辅助函数"""
        def check_conflicts(hotkey_configs):
            """检测快捷键冲突
            
            Args:
                hotkey_configs: 快捷键配置列表，每项为 (name, config) 元组
                
            Returns:
                冲突列表，每项为 (name1, name2, hotkey_string) 元组
            """
            conflicts = []
            enabled_hotkeys = {}
            
            for name, config in hotkey_configs:
                if config.enabled:
                    hotkey_str = config.get_hotkey_string()
                    if hotkey_str in enabled_hotkeys:
                        conflicts.append((enabled_hotkeys[hotkey_str], name, hotkey_str))
                    else:
                        enabled_hotkeys[hotkey_str] = name
            
            return conflicts
        
        # 测试有冲突的情况
        configs_with_conflict = [
            ("主界面", MainWindowHotkeyConfig(enabled=True, modifier="alt", key="x")),
            ("剪贴板", ClipboardHistoryHotkeyConfig(enabled=True, modifier="alt", key="x")),
        ]
        conflicts = check_conflicts(configs_with_conflict)
        assert len(conflicts) == 1
        assert conflicts[0][2] == "alt+x"
        
        # 测试无冲突的情况
        configs_no_conflict = [
            ("主界面", MainWindowHotkeyConfig(enabled=True, modifier="ctrl+alt", key="x")),
            ("剪贴板", ClipboardHistoryHotkeyConfig(enabled=True, modifier="alt", key="p")),
            ("OCR面板", OCRPanelHotkeyConfig(enabled=True, modifier="alt", key="o")),
            ("聚光灯", SpotlightHotkeyConfig(enabled=True, modifier="alt", key="s")),
        ]
        conflicts = check_conflicts(configs_no_conflict)
        assert len(conflicts) == 0
