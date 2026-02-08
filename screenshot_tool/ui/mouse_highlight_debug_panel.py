# =====================================================
# =============== 鼠标高亮调试面板 ===============
# =====================================================

"""
鼠标高亮调试面板

独立的非模态窗口，允许用户实时调整鼠标高亮效果的所有参数，
并立即看到效果变化。

Feature: mouse-highlight-debug-panel
Requirements: 1.1-1.5, 2.1-2.5, 3.1-3.4, 4.1-4.4, 5.1-5.7, 6.1-6.4, 7.1-7.3
"""

from typing import Optional, TYPE_CHECKING, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QPushButton, QWidget, QButtonGroup, QLabel, QGridLayout
)

from screenshot_tool.core.async_logger import async_debug_log
from screenshot_tool.core.config_manager import (
    MouseHighlightConfig, MOUSE_HIGHLIGHT_THEMES
)
from screenshot_tool.ui.components.parameter_slider_group import ParameterSliderGroup
from screenshot_tool.ui.components.theme_button import ThemeButton

if TYPE_CHECKING:
    from screenshot_tool.core.config_manager import ConfigManager
    from screenshot_tool.core.mouse_highlight_manager import MouseHighlightManager


class MouseHighlightDebugPanel(QDialog):
    """鼠标高亮调试面板
    
    单例模式，全局只有一个实例。
    非模态窗口，不阻塞其他操作。
    
    PySide6 最佳实践：
    - 使用 setWindowModality(Qt.NonModal) 实现非模态
    - 使用 show() 而非 exec() 显示窗口
    - 使用 activateWindow() + raise_() 激活已存在的窗口
    
    Feature: mouse-highlight-debug-panel
    Requirements: 1.1, 1.2, 1.5, 7.3
    """
    
    _instance: Optional["MouseHighlightDebugPanel"] = None
    
    @classmethod
    def instance(cls) -> Optional["MouseHighlightDebugPanel"]:
        """获取单例实例（可能为 None）"""
        return cls._instance
    
    @classmethod
    def show_panel(
        cls,
        config_manager: "ConfigManager",
        highlight_manager: "MouseHighlightManager",
        parent: Optional[QWidget] = None
    ) -> "MouseHighlightDebugPanel":
        """显示面板（如果已存在则激活）
        
        Args:
            config_manager: 配置管理器
            highlight_manager: 鼠标高亮管理器
            parent: 父窗口
            
        Returns:
            面板实例
            
        Feature: mouse-highlight-debug-panel
        Requirements: 7.3
        """
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(config_manager, highlight_manager, parent)
        
        # 激活已存在的窗口
        cls._instance.show()
        cls._instance.activateWindow()
        cls._instance.raise_()
        return cls._instance
    
    def __init__(
        self,
        config_manager: "ConfigManager",
        highlight_manager: "MouseHighlightManager",
        parent: Optional[QWidget] = None
    ):
        """初始化面板
        
        设置非模态窗口属性，参考 Qt 文档：
        - Qt.NonModal: 不阻塞任何窗口
        - 必须在 show() 之前设置 windowModality
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        self._highlight_manager = highlight_manager
        
        # UI 组件引用
        self._theme_buttons: Dict[str, ThemeButton] = {}
        self._theme_button_group: Optional[QButtonGroup] = None
        self._effect_checkboxes: Dict[str, QCheckBox] = {}
        self._parameter_sliders: Dict[str, ParameterSliderGroup] = {}
        self._parameter_groups: Dict[str, QGroupBox] = {}
        
        # 设置非模态（关键！）
        self.setWindowModality(Qt.WindowModality.NonModal)
        
        # 窗口属性
        self.setWindowTitle("鼠标高亮调试")
        self.setMinimumSize(420, 580)
        
        self._setup_ui()
        self._connect_signals()
        self._update_ui_from_config()
        
        # 自动启用鼠标高亮 (Requirement 1.3)
        if not self._highlight_manager.is_enabled():
            self._highlight_manager.enable()
            async_debug_log("调试面板自动启用鼠标高亮")
    
    def _setup_ui(self):
        """设置 UI 布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 主题选择区域
        layout.addWidget(self._create_theme_section())
        
        # 效果开关区域
        layout.addWidget(self._create_effects_section())
        
        # 参数调整区域
        layout.addWidget(self._create_parameters_section())
        
        # 操作按钮区域
        layout.addWidget(self._create_actions_section())
        
        # 弹性空间
        layout.addStretch()
    
    def _create_theme_section(self) -> QWidget:
        """创建主题选择区域
        
        Feature: mouse-highlight-debug-panel
        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        group = QGroupBox("配色主题")
        layout = QGridLayout(group)
        layout.setSpacing(8)
        
        self._theme_button_group = QButtonGroup(self)
        self._theme_button_group.setExclusive(True)
        
        # 创建主题按钮（2x2 网格）
        for i, (theme_key, theme_data) in enumerate(MOUSE_HIGHLIGHT_THEMES.items()):
            btn = ThemeButton(theme_key, theme_data)
            self._theme_buttons[theme_key] = btn
            self._theme_button_group.addButton(btn)
            
            row = i // 2
            col = i % 2
            layout.addWidget(btn, row, col)
            
            # 连接点击信号
            btn.clicked.connect(
                lambda checked, key=theme_key: self._on_theme_changed(key)
            )
        
        return group
    
    def _create_effects_section(self) -> QWidget:
        """创建效果开关区域
        
        Feature: mouse-highlight-debug-panel
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        group = QGroupBox("效果开关")
        layout = QGridLayout(group)
        layout.setSpacing(8)
        
        effects = [
            ("circle", "光圈"),
            ("click_effect", "点击涟漪"),
            ("spotlight", "聚光灯"),
            ("cursor_magnify", "指针放大"),
        ]
        
        for i, (effect_key, effect_name) in enumerate(effects):
            checkbox = QCheckBox(effect_name)
            checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
            self._effect_checkboxes[effect_key] = checkbox
            
            row = i // 2
            col = i % 2
            layout.addWidget(checkbox, row, col)
            
            # 连接信号
            checkbox.toggled.connect(
                lambda checked, key=effect_key: self._on_effect_toggled(key, checked)
            )
        
        return group
    
    def _create_parameters_section(self) -> QWidget:
        """创建参数调整区域
        
        Feature: mouse-highlight-debug-panel
        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1-5.7
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 光圈效果参数
        circle_group = QGroupBox("光圈效果")
        circle_layout = QVBoxLayout(circle_group)
        circle_layout.setSpacing(6)
        
        self._parameter_sliders["circle_radius"] = ParameterSliderGroup(
            "半径", 
            MouseHighlightConfig.MIN_CIRCLE_RADIUS,
            MouseHighlightConfig.MAX_CIRCLE_RADIUS,
            40, "px"
        )
        self._parameter_sliders["circle_thickness"] = ParameterSliderGroup(
            "粗细",
            MouseHighlightConfig.MIN_CIRCLE_THICKNESS,
            MouseHighlightConfig.MAX_CIRCLE_THICKNESS,
            3, "px"
        )
        circle_layout.addWidget(self._parameter_sliders["circle_radius"])
        circle_layout.addWidget(self._parameter_sliders["circle_thickness"])
        self._parameter_groups["circle"] = circle_group
        layout.addWidget(circle_group)
        
        # 聚光灯效果参数
        spotlight_group = QGroupBox("聚光灯效果")
        spotlight_layout = QVBoxLayout(spotlight_group)
        spotlight_layout.setSpacing(6)
        
        self._parameter_sliders["spotlight_radius"] = ParameterSliderGroup(
            "半径",
            MouseHighlightConfig.MIN_SPOTLIGHT_RADIUS,
            MouseHighlightConfig.MAX_SPOTLIGHT_RADIUS,
            150, "px"
        )
        self._parameter_sliders["spotlight_darkness"] = ParameterSliderGroup(
            "暗度",
            MouseHighlightConfig.MIN_SPOTLIGHT_DARKNESS,
            MouseHighlightConfig.MAX_SPOTLIGHT_DARKNESS,
            60, "%"
        )
        spotlight_layout.addWidget(self._parameter_sliders["spotlight_radius"])
        spotlight_layout.addWidget(self._parameter_sliders["spotlight_darkness"])
        self._parameter_groups["spotlight"] = spotlight_group
        layout.addWidget(spotlight_group)
        
        # 指针放大效果参数
        cursor_group = QGroupBox("指针放大效果")
        cursor_layout = QVBoxLayout(cursor_group)
        cursor_layout.setSpacing(6)
        
        self._parameter_sliders["cursor_scale"] = ParameterSliderGroup(
            "倍数",
            MouseHighlightConfig.MIN_CURSOR_SCALE,
            MouseHighlightConfig.MAX_CURSOR_SCALE,
            2.0, "x",
            is_float=True, decimals=1
        )
        cursor_layout.addWidget(self._parameter_sliders["cursor_scale"])
        self._parameter_groups["cursor_magnify"] = cursor_group
        layout.addWidget(cursor_group)
        
        # 点击涟漪效果参数
        ripple_group = QGroupBox("点击涟漪效果")
        ripple_layout = QVBoxLayout(ripple_group)
        ripple_layout.setSpacing(6)
        
        self._parameter_sliders["ripple_duration"] = ParameterSliderGroup(
            "时长",
            MouseHighlightConfig.MIN_RIPPLE_DURATION,
            MouseHighlightConfig.MAX_RIPPLE_DURATION,
            500, "ms"
        )
        ripple_layout.addWidget(self._parameter_sliders["ripple_duration"])
        self._parameter_groups["click_effect"] = ripple_group
        layout.addWidget(ripple_group)
        
        return container
    
    def _create_actions_section(self) -> QWidget:
        """创建操作按钮区域
        
        Feature: mouse-highlight-debug-panel
        Requirements: 6.3, 6.4
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        
        # 重置默认按钮
        reset_btn = QPushButton("重置默认")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._on_reset_clicked)
        layout.addWidget(reset_btn)
        
        layout.addStretch()
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return container
    
    def _connect_signals(self):
        """连接参数滑块信号"""
        for slider in self._parameter_sliders.values():
            slider.value_changed.connect(self._on_parameter_changed)
    
    def _on_parameter_changed(self, value):
        """参数变化时的回调（实时更新）
        
        Feature: mouse-highlight-debug-panel
        Requirements: 2.1, 2.2
        """
        self._apply_config_to_manager()
    
    def _on_theme_changed(self, theme_key: str):
        """主题变化时的回调
        
        Feature: mouse-highlight-debug-panel
        Requirements: 4.1
        """
        # 更新按钮选中状态
        for key, btn in self._theme_buttons.items():
            btn.set_selected(key == theme_key)
        
        # 更新配置
        self._config_manager.config.mouse_highlight.theme = theme_key
        self._apply_config_to_manager()
        
        async_debug_log(f"主题切换: {theme_key}")
    
    def _on_effect_toggled(self, effect_name: str, enabled: bool):
        """效果开关变化时的回调
        
        Feature: mouse-highlight-debug-panel
        Requirements: 3.1, 3.3
        """
        config = self._config_manager.config.mouse_highlight
        setattr(config, f"{effect_name}_enabled", enabled)
        self._update_parameter_controls_state()
        self._apply_config_to_manager()
        
        async_debug_log(f"效果开关: {effect_name} = {enabled}")
    
    def _on_reset_clicked(self):
        """重置按钮点击回调
        
        Feature: mouse-highlight-debug-panel
        Requirements: 6.3, 6.4
        """
        # 创建默认配置
        default_config = MouseHighlightConfig()
        
        # 保留当前的 enabled 和 hotkey 状态
        current_enabled = self._config_manager.config.mouse_highlight.enabled
        current_hotkey = self._config_manager.config.mouse_highlight.hotkey
        
        # 应用默认配置
        self._config_manager.config.mouse_highlight = default_config
        self._config_manager.config.mouse_highlight.enabled = current_enabled
        self._config_manager.config.mouse_highlight.hotkey = current_hotkey
        
        # 更新 UI
        self._update_ui_from_config()
        
        # 应用到管理器
        self._apply_config_to_manager()
        
        async_debug_log("已重置为默认配置")
    
    def _apply_config_to_manager(self):
        """将当前配置应用到管理器
        
        Feature: mouse-highlight-debug-panel
        Requirements: 2.1, 2.2
        """
        # 从 UI 读取当前值到配置
        config = self._config_manager.config.mouse_highlight
        
        # 更新参数值
        if "circle_radius" in self._parameter_sliders:
            config.circle_radius = int(self._parameter_sliders["circle_radius"].value())
        if "circle_thickness" in self._parameter_sliders:
            config.circle_thickness = int(self._parameter_sliders["circle_thickness"].value())
        if "spotlight_radius" in self._parameter_sliders:
            config.spotlight_radius = int(self._parameter_sliders["spotlight_radius"].value())
        if "spotlight_darkness" in self._parameter_sliders:
            config.spotlight_darkness = int(self._parameter_sliders["spotlight_darkness"].value())
        if "cursor_scale" in self._parameter_sliders:
            config.cursor_scale = self._parameter_sliders["cursor_scale"].value()
        if "ripple_duration" in self._parameter_sliders:
            config.ripple_duration = int(self._parameter_sliders["ripple_duration"].value())
        
        # 调用管理器更新
        self._highlight_manager.update_config(config)
    
    def _update_ui_from_config(self):
        """从配置更新 UI 显示"""
        config = self._config_manager.config.mouse_highlight
        
        # 更新主题按钮
        for key, btn in self._theme_buttons.items():
            btn.set_selected(key == config.theme)
        
        # 更新效果开关
        effect_mapping = {
            "circle": config.circle_enabled,
            "spotlight": config.spotlight_enabled,
            "cursor_magnify": config.cursor_magnify_enabled,
            "click_effect": config.click_effect_enabled,
        }
        for key, checkbox in self._effect_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(effect_mapping.get(key, False))
            checkbox.blockSignals(False)
        
        # 更新参数滑块
        if "circle_radius" in self._parameter_sliders:
            self._parameter_sliders["circle_radius"].set_value(config.circle_radius)
        if "circle_thickness" in self._parameter_sliders:
            self._parameter_sliders["circle_thickness"].set_value(config.circle_thickness)
        if "spotlight_radius" in self._parameter_sliders:
            self._parameter_sliders["spotlight_radius"].set_value(config.spotlight_radius)
        if "spotlight_darkness" in self._parameter_sliders:
            self._parameter_sliders["spotlight_darkness"].set_value(config.spotlight_darkness)
        if "cursor_scale" in self._parameter_sliders:
            self._parameter_sliders["cursor_scale"].set_value(config.cursor_scale)
        if "ripple_duration" in self._parameter_sliders:
            self._parameter_sliders["ripple_duration"].set_value(config.ripple_duration)
        
        # 更新参数控件启用状态
        self._update_parameter_controls_state()
    
    def _update_parameter_controls_state(self):
        """根据效果开关状态更新参数控件的启用状态"""
        effect_to_group = {
            "circle": "circle",
            "spotlight": "spotlight",
            "cursor_magnify": "cursor_magnify",
            "click_effect": "click_effect",
        }
        
        for effect_key, group_key in effect_to_group.items():
            if effect_key in self._effect_checkboxes and group_key in self._parameter_groups:
                enabled = self._effect_checkboxes[effect_key].isChecked()
                self._parameter_groups[group_key].setEnabled(enabled)
    
    def closeEvent(self, event):
        """关闭事件：保存配置
        
        Feature: mouse-highlight-debug-panel
        Requirements: 6.1
        """
        try:
            self._config_manager.save()
            async_debug_log("调试面板关闭，配置已保存")
        except Exception as e:
            async_debug_log(f"保存配置失败: {e}")
        
        MouseHighlightDebugPanel._instance = None
        super().closeEvent(event)
    
    def get_current_config(self) -> MouseHighlightConfig:
        """获取当前配置（用于测试）"""
        return self._config_manager.config.mouse_highlight
