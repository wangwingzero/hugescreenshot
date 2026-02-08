# =====================================================
# =============== 录屏设置面板 ===============
# =====================================================

"""
录屏设置面板

独立的非模态窗口，允许用户配置录屏参数并开始录制。
与鼠标高亮调试面板保持一致的 UI 风格。

Feature: recording-settings-panel
Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.3
"""

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QPushButton, QWidget, QButtonGroup, QRadioButton, QLabel,
    QMessageBox
)

from screenshot_tool.core.async_logger import async_debug_log

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import ConfigManager


# 颜色常量（与 main_window.py 保持一致）
COLORS = {
    "primary": "#3B82F6",
    "secondary": "#60A5FA",
    "background": "#F8FAFC",
    "text": "#1E293B",
    "text_muted": "#64748B",
    "border": "#E2E8F0",
    "card_bg": "#FFFFFF",
}


class RecordingSettingsPanel(QDialog):
    """录屏设置面板
    
    单例模式，全局只有一个实例。
    非模态窗口，不阻塞其他操作。
    
    PySide6 最佳实践：
    - 使用 setWindowModality(Qt.NonModal) 实现非模态
    - 使用 show() 而非 exec() 显示窗口
    - 使用 activateWindow() + raise_() 激活已存在的窗口
    
    Feature: recording-settings-panel
    Requirements: 1.1, 1.4
    """
    
    # 信号
    start_recording_requested = Signal()  # 请求开始录制
    cancelled = Signal()  # 用户取消（关闭面板而不开始录制）
    
    # 类变量（单例）
    _instance: Optional["RecordingSettingsPanel"] = None
    
    @classmethod
    def instance(cls) -> Optional["RecordingSettingsPanel"]:
        """获取单例实例（可能为 None）"""
        return cls._instance
    
    @classmethod
    def show_panel(
        cls,
        config_manager: "ConfigManager",
        parent: Optional[QWidget] = None
    ) -> "RecordingSettingsPanel":
        """显示面板（如果已存在则激活）
        
        Args:
            config_manager: 配置管理器
            parent: 父窗口
            
        Returns:
            面板实例
            
        Feature: recording-settings-panel
        Requirements: 1.4
        """
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(config_manager, parent)
        
        # 激活已存在的窗口
        cls._instance.show()
        cls._instance.activateWindow()
        cls._instance.raise_()
        return cls._instance
    
    def __init__(
        self,
        config_manager: "ConfigManager",
        parent: Optional[QWidget] = None
    ):
        """初始化面板
        
        设置非模态窗口属性，参考 Qt 文档：
        - Qt.NonModal: 不阻塞任何窗口
        - 必须在 show() 之前设置 windowModality
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        
        # 标记是否因为开始录制而关闭（用于区分取消和开始录制）
        self._started_recording = False
        
        # UI 组件引用
        self._system_audio_checkbox: Optional[QCheckBox] = None
        self._microphone_checkbox: Optional[QCheckBox] = None
        self._fps_button_group: Optional[QButtonGroup] = None
        self._fps_buttons: dict[int, QRadioButton] = {}
        self._quality_button_group: Optional[QButtonGroup] = None
        self._quality_buttons: dict[str, QRadioButton] = {}
        self._show_cursor_checkbox: Optional[QCheckBox] = None
        self._start_button: Optional[QPushButton] = None
        
        # 设置非模态（关键！）
        self.setWindowModality(Qt.WindowModality.NonModal)
        
        # 窗口属性
        self.setWindowTitle("录屏设置")
        self.setMinimumSize(360, 380)
        self.setMaximumSize(500, 500)
        
        self._setup_ui()
        self._connect_signals()
        self._update_ui_from_config()
    
    def _setup_ui(self):
        """设置 UI 布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 音频设置区域
        layout.addWidget(self._create_audio_section())
        
        # 视频设置区域
        layout.addWidget(self._create_video_section())
        
        # 操作按钮区域
        layout.addWidget(self._create_actions_section())
        
        # 弹性空间
        layout.addStretch()
    
    def _create_audio_section(self) -> QWidget:
        """创建音频设置区域
        
        Feature: recording-settings-panel
        Requirements: 2.1, 2.2, 2.3
        """
        group = QGroupBox("音频设置")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # 录制系统声音
        self._system_audio_checkbox = QCheckBox("录制系统声音")
        self._system_audio_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._system_audio_checkbox)
        
        # 录制麦克风
        self._microphone_checkbox = QCheckBox("录制麦克风")
        self._microphone_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._microphone_checkbox)
        
        return group
    
    def _create_video_section(self) -> QWidget:
        """创建视频设置区域
        
        Feature: recording-settings-panel
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        group = QGroupBox("视频设置")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        
        # 帧率选择
        fps_container = QWidget()
        fps_layout = QHBoxLayout(fps_container)
        fps_layout.setContentsMargins(0, 0, 0, 0)
        fps_layout.setSpacing(8)
        
        fps_label = QLabel("帧率:")
        fps_label.setStyleSheet(f"color: {COLORS['text']};")
        fps_layout.addWidget(fps_label)
        
        self._fps_button_group = QButtonGroup(self)
        for fps in [15, 30, 60]:
            btn = QRadioButton(f"{fps}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._fps_buttons[fps] = btn
            self._fps_button_group.addButton(btn, fps)
            fps_layout.addWidget(btn)
        
        fps_unit = QLabel("FPS")
        fps_unit.setStyleSheet(f"color: {COLORS['text_muted']};")
        fps_layout.addWidget(fps_unit)
        fps_layout.addStretch()
        
        layout.addWidget(fps_container)
        
        # 质量选择
        quality_container = QWidget()
        quality_layout = QHBoxLayout(quality_container)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)
        
        quality_label = QLabel("质量:")
        quality_label.setStyleSheet(f"color: {COLORS['text']};")
        quality_layout.addWidget(quality_label)
        
        self._quality_button_group = QButtonGroup(self)
        quality_options = [("low", "低"), ("medium", "中"), ("high", "高")]
        for i, (key, label) in enumerate(quality_options):
            btn = QRadioButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._quality_buttons[key] = btn
            self._quality_button_group.addButton(btn, i)
            quality_layout.addWidget(btn)
        
        quality_layout.addStretch()
        layout.addWidget(quality_container)
        
        # 显示鼠标指针
        self._show_cursor_checkbox = QCheckBox("显示鼠标指针")
        self._show_cursor_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._show_cursor_checkbox)
        
        return group
    
    def _create_actions_section(self) -> QWidget:
        """创建操作按钮区域
        
        Feature: recording-settings-panel
        Requirements: 4.1
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        
        layout.addStretch()
        
        # 开始录制按钮
        self._start_button = QPushButton("开始录制")
        self._start_button.setFixedSize(120, 40)
        self._start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['secondary']};
            }}
            QPushButton:pressed {{
                background-color: #2563EB;
            }}
        """)
        self._start_button.clicked.connect(self._on_start_recording_clicked)
        layout.addWidget(self._start_button)
        
        layout.addStretch()
        
        return container
    
    def _connect_signals(self):
        """连接所有控件信号"""
        # 音频设置
        if self._system_audio_checkbox:
            self._system_audio_checkbox.toggled.connect(self._on_setting_changed)
        if self._microphone_checkbox:
            self._microphone_checkbox.toggled.connect(self._on_setting_changed)
        
        # 视频设置
        if self._fps_button_group:
            self._fps_button_group.idToggled.connect(self._on_setting_changed)
        if self._quality_button_group:
            self._quality_button_group.idToggled.connect(self._on_setting_changed)
        if self._show_cursor_checkbox:
            self._show_cursor_checkbox.toggled.connect(self._on_setting_changed)
    
    def _on_setting_changed(self, *args):
        """设置变化时的回调（实时更新配置）
        
        Feature: recording-settings-panel
        Requirements: 2.4, 3.5
        """
        self._apply_ui_to_config()
    
    def _apply_ui_to_config(self):
        """将 UI 状态应用到配置"""
        config = self._config_manager.config.recording
        
        # 音频设置
        if self._system_audio_checkbox:
            config.record_system_audio = self._system_audio_checkbox.isChecked()
        if self._microphone_checkbox:
            config.record_microphone = self._microphone_checkbox.isChecked()
        
        # 视频设置 - 帧率
        if self._fps_button_group:
            checked_id = self._fps_button_group.checkedId()
            if checked_id in [15, 30, 60]:
                config.fps = checked_id
        
        # 视频设置 - 质量
        if self._quality_button_group:
            checked_id = self._quality_button_group.checkedId()
            quality_map = {0: "low", 1: "medium", 2: "high"}
            if checked_id in quality_map:
                config.quality = quality_map[checked_id]
        
        # 显示鼠标指针
        if self._show_cursor_checkbox:
            config.show_cursor = self._show_cursor_checkbox.isChecked()
    
    def _on_start_recording_clicked(self):
        """开始录制按钮点击回调
        
        Feature: recording-settings-panel
        Requirements: 4.2, 4.4
        """
        # 检查依赖
        from screenshot_tool.services.screen_recorder import ScreenRecorder
        available, error = ScreenRecorder.check_dependencies()
        
        if not available:
            QMessageBox.warning(
                self,
                "录屏依赖缺失",
                f"无法启动录屏：\n\n{error}\n\n请安装所需依赖后重试。"
            )
            return
        
        # 保存配置
        try:
            self._config_manager.save()
        except Exception as e:
            async_debug_log(f"保存录屏配置失败: {e}")
        
        # 标记为开始录制（不是取消）
        self._started_recording = True
        
        # 关闭面板并发出信号
        self.close()
        self.start_recording_requested.emit()
        async_debug_log("录屏设置面板：请求开始录制")
    
    def _update_ui_from_config(self):
        """从配置更新 UI 显示
        
        Feature: recording-settings-panel
        Requirements: 5.2
        """
        config = self._config_manager.config.recording
        
        # 音频设置
        if self._system_audio_checkbox:
            self._system_audio_checkbox.blockSignals(True)
            self._system_audio_checkbox.setChecked(config.record_system_audio)
            self._system_audio_checkbox.blockSignals(False)
        
        if self._microphone_checkbox:
            self._microphone_checkbox.blockSignals(True)
            self._microphone_checkbox.setChecked(config.record_microphone)
            self._microphone_checkbox.blockSignals(False)
        
        # 视频设置 - 帧率（阻止 button group 信号）
        if self._fps_button_group:
            self._fps_button_group.blockSignals(True)
        if config.fps in self._fps_buttons:
            self._fps_buttons[config.fps].setChecked(True)
        if self._fps_button_group:
            self._fps_button_group.blockSignals(False)
        
        # 视频设置 - 质量（阻止 button group 信号）
        if self._quality_button_group:
            self._quality_button_group.blockSignals(True)
        if config.quality in self._quality_buttons:
            self._quality_buttons[config.quality].setChecked(True)
        if self._quality_button_group:
            self._quality_button_group.blockSignals(False)
        
        # 显示鼠标指针
        if self._show_cursor_checkbox:
            self._show_cursor_checkbox.blockSignals(True)
            self._show_cursor_checkbox.setChecked(config.show_cursor)
            self._show_cursor_checkbox.blockSignals(False)
    
    def closeEvent(self, event):
        """关闭事件：保存配置，如果是取消则发出 cancelled 信号
        
        Feature: recording-settings-panel
        Requirements: 5.1, 7.1
        """
        try:
            self._config_manager.save()
            async_debug_log("录屏设置面板关闭，配置已保存")
        except Exception as e:
            async_debug_log(f"保存录屏配置失败: {e}")
        
        # 如果不是因为开始录制而关闭，则发出取消信号
        if not self._started_recording:
            self.cancelled.emit()
            async_debug_log("录屏设置面板：用户取消")
        
        RecordingSettingsPanel._instance = None
        super().closeEvent(event)
    
    def keyPressEvent(self, event):
        """键盘事件：ESC 键关闭面板
        
        Feature: recording-settings-panel
        Requirements: 7.3
        """
        from PySide6.QtCore import Qt
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    
    def get_current_config(self):
        """获取当前配置（用于测试）"""
        return self._config_manager.config.recording
