"""热键强制锁定集成测试

Feature: hotkey-force-lock
Requirements: 4.1, 4.2, 4.3

测试配置保存/加载、设置对话框 UI 元素、信号连接
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


@pytest.fixture
def app(qapp):
    """使用 pytest-qt 提供的 qapp fixture"""
    return qapp


@pytest.fixture
def config_manager():
    """创建配置管理器 mock"""
    from screenshot_tool.core.config_manager import ConfigManager, AppConfig, HotkeyConfig
    
    manager = Mock(spec=ConfigManager)
    manager.config = AppConfig()
    manager.config.hotkey = HotkeyConfig()
    return manager


class TestConfigIntegration:
    """配置集成测试"""
    
    def test_hotkey_config_has_force_lock_fields(self):
        """测试 HotkeyConfig 包含强制锁定字段"""
        from screenshot_tool.core.config_manager import HotkeyConfig
        
        config = HotkeyConfig()
        
        assert hasattr(config, 'force_lock')
        assert hasattr(config, 'retry_interval_ms')
        assert hasattr(HotkeyConfig, 'MIN_RETRY_INTERVAL_MS')
        assert hasattr(HotkeyConfig, 'MAX_RETRY_INTERVAL_MS')
    
    def test_config_serialization_includes_force_lock(self):
        """测试配置序列化包含强制锁定字段"""
        from screenshot_tool.core.config_manager import HotkeyConfig
        import json
        from dataclasses import asdict
        
        config = HotkeyConfig(force_lock=True, retry_interval_ms=5000)
        config_dict = asdict(config)
        
        assert 'force_lock' in config_dict
        assert 'retry_interval_ms' in config_dict
        assert config_dict['force_lock'] is True
        assert config_dict['retry_interval_ms'] == 5000
        
        # 测试 JSON 序列化
        json_str = json.dumps(config_dict)
        loaded = json.loads(json_str)
        
        assert loaded['force_lock'] is True
        assert loaded['retry_interval_ms'] == 5000


class TestSettingsDialogUI:
    """设置对话框 UI 测试"""
    
    def test_settings_dialog_has_force_lock_checkbox(self, app, config_manager):
        """测试设置对话框包含强制锁定复选框"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        dialog = SettingsDialog(config_manager.config)
        
        assert hasattr(dialog, '_force_lock_check')
        assert dialog._force_lock_check is not None
    
    def test_settings_dialog_has_retry_interval_input(self, app, config_manager):
        """测试设置对话框包含重试间隔输入框（QLineEdit）"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        dialog = SettingsDialog(config_manager.config)
        
        assert hasattr(dialog, '_retry_interval_input')
        assert dialog._retry_interval_input is not None
    
    def test_retry_interval_input_has_validator(self, app, config_manager):
        """测试重试间隔输入框有正确的验证器"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        from PySide6.QtGui import QIntValidator
        
        dialog = SettingsDialog(config_manager.config)
        
        validator = dialog._retry_interval_input.validator()
        assert validator is not None
        assert isinstance(validator, QIntValidator)
        # 验证范围 1000-30000
        assert validator.bottom() == 1000
        assert validator.top() == 30000
    
    def test_settings_dialog_loads_force_lock_config(self, app, config_manager):
        """测试设置对话框加载强制锁定配置"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        config_manager.config.hotkey.force_lock = True
        config_manager.config.hotkey.retry_interval_ms = 5000
        
        dialog = SettingsDialog(config_manager.config)
        
        assert dialog._force_lock_check.isChecked() is True
        assert dialog._retry_interval_input.text() == "5000"
    
    def test_settings_dialog_has_force_lock_changed_signal(self, app, config_manager):
        """测试设置对话框包含 forceLockChanged 信号"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        dialog = SettingsDialog(config_manager.config)
        
        assert hasattr(dialog, 'forceLockChanged')


class TestSignalConnections:
    """信号连接测试"""
    
    def test_force_lock_changed_signal_emitted(self, app, config_manager, qtbot):
        """测试强制锁定变更时发送信号"""
        from screenshot_tool.ui.dialogs import SettingsDialog
        
        dialog = SettingsDialog(config_manager.config)
        
        # 修改强制锁定设置
        dialog._force_lock_check.setChecked(True)
        dialog._retry_interval_input.setText("5000")
        
        # 监听信号
        with qtbot.waitSignal(dialog.forceLockChanged, timeout=1000) as blocker:
            # 模拟保存（需要设置有效的保存路径）
            dialog._save_path_edit.setText("C:\\temp")
            dialog._on_save()
        
        # 验证信号参数
        assert blocker.args == [True, 5000]


class TestHelpTexts:
    """帮助文本测试"""
    
    def test_hotkey_help_includes_force_lock_info(self):
        """测试热键帮助文本包含强制锁定信息"""
        from screenshot_tool.ui.help_texts import HELP_PANEL_ITEMS
        
        hotkey_help = HELP_PANEL_ITEMS.get('hotkey', [])
        
        # 检查是否包含强制锁定相关的帮助文本
        force_lock_mentioned = any(
            '强制锁定' in item for item in hotkey_help
        )
        
        assert force_lock_mentioned, "热键帮助文本应包含强制锁定相关信息"


class TestGlobalHotkeyManagerIntegration:
    """GlobalHotkeyManager 集成测试"""
    
    def test_hotkey_manager_accepts_force_lock_params(self):
        """测试热键管理器接受强制锁定参数"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            manager = GlobalHotkeyManager(
                callback,
                modifier="alt",
                key="a",
                force_lock=True,
                retry_interval_ms=5000
            )
            
            assert manager._force_lock is True
            assert manager._retry_interval_ms == 5000
    
    def test_hotkey_manager_set_force_lock_method(self):
        """测试热键管理器 set_force_lock 方法"""
        from screenshot_tool.overlay_main import GlobalHotkeyManager
        
        callback = Mock()
        
        with patch.object(GlobalHotkeyManager, '_start_listener_thread'):
            with patch.object(GlobalHotkeyManager, '_schedule_retry'):
                with patch.object(GlobalHotkeyManager, '_cancel_retry'):
                    manager = GlobalHotkeyManager(callback)
                    manager._running = True
                    
                    manager.set_force_lock(True, 5000)
                    
                    assert manager._force_lock is True
                    assert manager._retry_interval_ms == 5000
