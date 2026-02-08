# =====================================================
# =============== 录屏设置面板测试 ===============
# =====================================================

"""
录屏设置面板的单元测试和属性测试

Feature: recording-settings-panel
"""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from screenshot_tool.core.config_manager import ConfigManager, RecordingConfig
from screenshot_tool.ui.recording_settings_panel import RecordingSettingsPanel


@pytest.fixture
def app(qapp):
    """Qt 应用实例"""
    return qapp


@pytest.fixture
def config_manager(tmp_path):
    """创建临时配置管理器"""
    config_file = tmp_path / "config.json"
    with patch('screenshot_tool.core.config_manager.get_portable_config_path', return_value=str(config_file)):
        manager = ConfigManager()
        yield manager


@pytest.fixture
def panel(app, config_manager):
    """创建面板实例"""
    # 确保清除之前的单例
    RecordingSettingsPanel._instance = None
    panel = RecordingSettingsPanel(config_manager)
    yield panel
    panel.close()
    RecordingSettingsPanel._instance = None


class TestRecordingSettingsPanelUI:
    """UI 结构测试"""
    
    def test_panel_is_non_modal(self, panel):
        """测试面板是非模态的
        
        Feature: recording-settings-panel
        Requirements: 1.1
        """
        assert panel.windowModality() == Qt.WindowModality.NonModal
    
    def test_audio_section_exists(self, panel):
        """测试音频设置区域存在
        
        Feature: recording-settings-panel
        Requirements: 2.1, 2.2, 2.3
        """
        assert panel._system_audio_checkbox is not None
        assert panel._microphone_checkbox is not None
    
    def test_video_section_exists(self, panel):
        """测试视频设置区域存在
        
        Feature: recording-settings-panel
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        assert panel._fps_button_group is not None
        assert len(panel._fps_buttons) == 3  # 15, 30, 60
        assert panel._quality_button_group is not None
        assert len(panel._quality_buttons) == 3  # low, medium, high
        assert panel._show_cursor_checkbox is not None
    
    def test_start_button_exists(self, panel):
        """测试开始录制按钮存在
        
        Feature: recording-settings-panel
        Requirements: 4.1
        """
        assert panel._start_button is not None
        assert panel._start_button.text() == "开始录制"


class TestSingletonPattern:
    """单例模式测试
    
    Feature: recording-settings-panel, Property 1: Singleton Pattern Enforcement
    **Validates: Requirements 1.4**
    """
    
    def test_show_panel_returns_same_instance(self, app, config_manager):
        """测试 show_panel 返回相同实例"""
        RecordingSettingsPanel._instance = None
        
        panel1 = RecordingSettingsPanel.show_panel(config_manager)
        panel2 = RecordingSettingsPanel.show_panel(config_manager)
        
        assert panel1 is panel2
        
        panel1.close()
        RecordingSettingsPanel._instance = None
    
    def test_instance_cleared_on_close(self, app, config_manager):
        """测试关闭后实例被清除"""
        RecordingSettingsPanel._instance = None
        
        panel = RecordingSettingsPanel.show_panel(config_manager)
        assert RecordingSettingsPanel._instance is not None
        
        panel.close()
        assert RecordingSettingsPanel._instance is None
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(call_count=st.integers(min_value=2, max_value=10))
    def test_singleton_property(self, app, config_manager, call_count):
        """属性测试：多次调用 show_panel 只产生一个实例
        
        Feature: recording-settings-panel, Property 1: Singleton Pattern Enforcement
        **Validates: Requirements 1.4**
        """
        RecordingSettingsPanel._instance = None
        
        panels = []
        for _ in range(call_count):
            panel = RecordingSettingsPanel.show_panel(config_manager)
            panels.append(panel)
        
        # 所有返回的实例应该是同一个
        first_panel = panels[0]
        for p in panels[1:]:
            assert p is first_panel
        
        first_panel.close()
        RecordingSettingsPanel._instance = None


class TestConfigurationBinding:
    """配置绑定测试"""
    
    def test_ui_loads_from_config(self, panel, config_manager):
        """测试 UI 从配置加载
        
        Feature: recording-settings-panel
        Requirements: 5.2
        """
        config = config_manager.config.recording
        
        assert panel._system_audio_checkbox.isChecked() == config.record_system_audio
        assert panel._microphone_checkbox.isChecked() == config.record_microphone
        assert panel._show_cursor_checkbox.isChecked() == config.show_cursor
    
    def test_setting_change_updates_config(self, panel, config_manager):
        """测试设置变更更新配置
        
        Feature: recording-settings-panel
        Requirements: 2.4, 3.5
        """
        # 切换系统声音
        original = config_manager.config.recording.record_system_audio
        panel._system_audio_checkbox.setChecked(not original)
        
        assert config_manager.config.recording.record_system_audio == (not original)
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        record_system_audio=st.booleans(),
        record_microphone=st.booleans(),
        fps=st.sampled_from([15, 30, 60]),
        quality=st.sampled_from(["low", "medium", "high"]),
        show_cursor=st.booleans()
    )
    def test_config_round_trip(
        self, app, config_manager,
        record_system_audio, record_microphone, fps, quality, show_cursor
    ):
        """属性测试：配置往返一致性
        
        Feature: recording-settings-panel, Property 3: Configuration Round-Trip
        **Validates: Requirements 5.1, 5.2**
        """
        RecordingSettingsPanel._instance = None
        
        # 设置配置
        config = config_manager.config.recording
        config.record_system_audio = record_system_audio
        config.record_microphone = record_microphone
        config.fps = fps
        config.quality = quality
        config.show_cursor = show_cursor
        
        # 创建面板（加载配置）
        panel = RecordingSettingsPanel(config_manager)
        
        # 验证 UI 显示正确
        assert panel._system_audio_checkbox.isChecked() == record_system_audio
        assert panel._microphone_checkbox.isChecked() == record_microphone
        assert panel._fps_buttons[fps].isChecked()
        assert panel._quality_buttons[quality].isChecked()
        assert panel._show_cursor_checkbox.isChecked() == show_cursor
        
        panel.close()
        RecordingSettingsPanel._instance = None


class TestStartRecording:
    """开始录制测试"""
    
    def test_start_recording_emits_signal_when_deps_available(self, panel):
        """测试依赖可用时发出信号
        
        Feature: recording-settings-panel
        Requirements: 4.2
        """
        signal_received = []
        panel.start_recording_requested.connect(lambda: signal_received.append(True))
        
        with patch('screenshot_tool.services.screen_recorder.ScreenRecorder.check_dependencies', return_value=(True, "")):
            panel._on_start_recording_clicked()
        
        assert len(signal_received) == 1
    
    def test_start_recording_shows_error_when_deps_missing(self, panel):
        """测试依赖缺失时显示错误
        
        Feature: recording-settings-panel
        Requirements: 4.4
        """
        signal_received = []
        panel.start_recording_requested.connect(lambda: signal_received.append(True))
        
        with patch('screenshot_tool.services.screen_recorder.ScreenRecorder.check_dependencies', return_value=(False, "缺少 dxcam")):
            with patch('PySide6.QtWidgets.QMessageBox.warning') as mock_warning:
                panel._on_start_recording_clicked()
                mock_warning.assert_called_once()
        
        # 信号不应该发出
        assert len(signal_received) == 0
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(deps_available=st.booleans())
    def test_start_recording_closes_panel_only_when_deps_available(
        self, app, config_manager, deps_available
    ):
        """属性测试：开始录制关闭面板
        
        Feature: recording-settings-panel, Property 4: Start Recording Closes Panel
        **Validates: Requirements 4.2**
        """
        RecordingSettingsPanel._instance = None
        panel = RecordingSettingsPanel(config_manager)
        panel.show()
        
        signal_received = []
        panel.start_recording_requested.connect(lambda: signal_received.append(True))
        
        error_msg = "" if deps_available else "缺少依赖"
        with patch('screenshot_tool.services.screen_recorder.ScreenRecorder.check_dependencies', return_value=(deps_available, error_msg)):
            with patch('PySide6.QtWidgets.QMessageBox.warning'):
                panel._on_start_recording_clicked()
        
        if deps_available:
            # 依赖可用时：信号发出，面板关闭
            assert len(signal_received) == 1
            assert not panel.isVisible()
        else:
            # 依赖不可用时：信号不发出，面板保持打开
            assert len(signal_received) == 0
        
        panel.close()
        RecordingSettingsPanel._instance = None
