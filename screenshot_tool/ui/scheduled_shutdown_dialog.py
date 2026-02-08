# =====================================================
# =============== 预约关机窗口 v6.0 ===============
# =====================================================

"""
预约关机窗口 - Flat Design 风格 v6.0

改进：
- 从 QDialog 改为 QMainWindow，支持最大化/最小化
- 使用自适应布局，控件不重叠
- 极简大数字 + 线性进度条（替代圆环，更清晰易读）
- 与应用整体设计系统保持一致
"""

import subprocess
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QMessageBox,
    QSlider,
    QWidget,
    QTimeEdit,
    QSizePolicy,
    QScrollArea,
    QProgressBar,
)

# 导入应用设计系统
from .styles import COLORS as APP_COLORS, SPACING, RADIUS, FONT_FAMILY


class TimeChip(QPushButton):
    """时间选择按钮 - Flat Design 风格"""
    
    def __init__(self, minutes: int, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(label, parent)
        self.minutes: int = minutes
        self._selected: bool = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(68)
        self._apply_style()
    
    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()
    
    def _apply_style(self) -> None:
        if self._selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {APP_COLORS['primary']};
                    color: white;
                    border: none;
                    border-radius: {RADIUS['md']}px;
                    padding: 0 {SPACING['md']}px;
                    font-size: 10pt;
                    font-weight: 600;
                    font-family: {FONT_FAMILY};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {APP_COLORS['surface']};
                    color: {APP_COLORS['text']};
                    border: 1px solid {APP_COLORS['border']};
                    border-radius: {RADIUS['md']}px;
                    padding: 0 {SPACING['md']}px;
                    font-size: 10pt;
                    font-weight: 500;
                    font-family: {FONT_FAMILY};
                }}
                QPushButton:hover {{
                    border-color: {APP_COLORS['primary']};
                    color: {APP_COLORS['primary']};
                }}
            """)


class ModeToggle(QFrame):
    """模式切换开关 - Flat Design 风格"""
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mode: str = "countdown"
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {APP_COLORS['bg']};
                border-radius: {RADIUS['lg']}px;
                border: 1px solid {APP_COLORS['border']};
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        self._countdown_btn = QPushButton("倒计时")
        self._countdown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._countdown_btn.setFixedHeight(32)
        layout.addWidget(self._countdown_btn)
        
        self._specific_btn = QPushButton("指定时间")
        self._specific_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._specific_btn.setFixedHeight(32)
        layout.addWidget(self._specific_btn)
        
        self._update_style()
    
    def _update_style(self) -> None:
        active = f"""
            QPushButton {{
                background-color: {APP_COLORS['surface']};
                color: {APP_COLORS['primary']};
                border: none;
                border-radius: {RADIUS['md']}px;
                font-size: 10pt;
                font-weight: 600;
                padding: 0 {SPACING['md']}px;
                font-family: {FONT_FAMILY};
            }}
        """
        inactive = f"""
            QPushButton {{
                background-color: transparent;
                color: {APP_COLORS['text_secondary']};
                border: none;
                border-radius: {RADIUS['md']}px;
                font-size: 10pt;
                padding: 0 {SPACING['md']}px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                color: {APP_COLORS['text']};
            }}
        """
        
        if self._mode == "countdown":
            self._countdown_btn.setStyleSheet(active)
            self._specific_btn.setStyleSheet(inactive)
        else:
            self._countdown_btn.setStyleSheet(inactive)
            self._specific_btn.setStyleSheet(active)
    
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._update_style()
    
    def set_enabled(self, enabled: bool) -> None:
        self._countdown_btn.setEnabled(enabled)
        self._specific_btn.setEnabled(enabled)


class ScheduledShutdownDialog(QMainWindow):
    """预约关机窗口 v6.0 - Flat Design 风格
    
    改进：
    - 支持最大化/最小化/关闭
    - 自适应布局，控件不重叠
    - 极简大数字 + 线性进度条（更清晰易读）
    - 主色 #2563EB
    """
    
    QUICK_OPTIONS = [
        (15, "15分钟"),
        (30, "30分钟"),
        (45, "45分钟"),
        (60, "1小时"),
        (90, "1.5小时"),
        (120, "2小时"),
    ]
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scheduled_time: Optional[datetime] = None
        self._total_seconds: int = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._warning_shown: bool = False
        self._mode: str = "countdown"
        self._selected_minutes: int = 30
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        self.setWindowTitle("预约关机")
        self.setMinimumSize(360, 480)
        self.resize(400, 560)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {APP_COLORS['bg']};
                font-family: {FONT_FAMILY};
            }}
        """)
        
        # 使用滚动区域确保内容不重叠
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        layout.setSpacing(SPACING['md'])
        
        # 标题
        title = QLabel("预约关机")
        title.setStyleSheet(f"""
            font-size: 16pt;
            font-weight: 600;
            color: {APP_COLORS['text']};
            font-family: {FONT_FAMILY};
        """)
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(title)
        
        # 模式切换
        self._mode_toggle = ModeToggle()
        self._mode_toggle._countdown_btn.clicked.connect(lambda: self._switch_mode("countdown"))
        self._mode_toggle._specific_btn.clicked.connect(lambda: self._switch_mode("specific"))
        self._mode_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._mode_toggle)
        
        # 时间选择区域
        self._setup_time_selection(layout)
        
        # 圆形进度环
        self._setup_progress_ring(layout)
        
        # 弹性空间
        layout.addStretch(1)
        
        # 操作按钮
        self._setup_buttons(layout)
        
        scroll_area.setWidget(scroll_content)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

    def _setup_time_selection(self, layout: QVBoxLayout):
        """时间选择区域"""
        # 倒计时模式
        self._countdown_widget = QWidget()
        self._countdown_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        countdown_layout = QVBoxLayout(self._countdown_widget)
        countdown_layout.setContentsMargins(0, 0, 0, 0)
        countdown_layout.setSpacing(12)
        
        # 快捷按钮（两行三列）
        chips_layout1 = QHBoxLayout()
        chips_layout1.setSpacing(10)
        chips_layout2 = QHBoxLayout()
        chips_layout2.setSpacing(10)
        
        self._time_chips: list[TimeChip] = []
        for i, (minutes, label) in enumerate(self.QUICK_OPTIONS):
            chip = TimeChip(minutes, label)
            chip.clicked.connect(lambda _, m=minutes: self._select_time(m))
            self._time_chips.append(chip)
            if i < 3:
                chips_layout1.addWidget(chip)
            else:
                chips_layout2.addWidget(chip)
        
        countdown_layout.addLayout(chips_layout1)
        countdown_layout.addLayout(chips_layout2)
        
        # 自定义滑块
        slider_container = QFrame()
        slider_container.setStyleSheet(f"""
            QFrame {{
                background: {APP_COLORS['surface']};
                border-radius: {RADIUS['lg']}px;
                border: 1px solid {APP_COLORS['border']};
            }}
        """)
        slider_layout = QVBoxLayout(slider_container)
        slider_layout.setContentsMargins(16, 12, 16, 12)
        slider_layout.setSpacing(8)
        
        slider_header = QHBoxLayout()
        slider_label = QLabel("自定义时间")
        slider_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 500;
            color: {APP_COLORS['text']};
            font-family: {FONT_FAMILY};
        """)
        slider_header.addWidget(slider_label)
        slider_header.addStretch()
        
        self._time_display = QLabel("30 分钟")
        self._time_display.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {APP_COLORS['primary']};
            font-family: {FONT_FAMILY};
        """)
        slider_header.addWidget(self._time_display)
        slider_layout.addLayout(slider_header)
        
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(5, 240)
        self._slider.setValue(30)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {APP_COLORS['border']};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {APP_COLORS['primary']};
                width: 20px;
                height: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }}
            QSlider::sub-page:horizontal {{
                background: {APP_COLORS['primary']};
                border-radius: 3px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_slider_change)
        slider_layout.addWidget(self._slider)
        
        countdown_layout.addWidget(slider_container)
        layout.addWidget(self._countdown_widget)

        # 指定时间模式
        self._specific_widget = QWidget()
        self._specific_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        specific_layout = QVBoxLayout(self._specific_widget)
        specific_layout.setContentsMargins(0, 0, 0, 0)
        specific_layout.setSpacing(12)
        
        time_container = QFrame()
        time_container.setStyleSheet(f"""
            QFrame {{
                background: {APP_COLORS['surface']};
                border-radius: {RADIUS['lg']}px;
                border: 1px solid {APP_COLORS['border']};
            }}
        """)
        time_layout = QVBoxLayout(time_container)
        time_layout.setContentsMargins(16, 16, 16, 16)
        time_layout.setSpacing(12)
        
        time_label = QLabel("选择关机时间")
        time_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 500;
            color: {APP_COLORS['text']};
            font-family: {FONT_FAMILY};
        """)
        time_layout.addWidget(time_label)
        
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(datetime.now().time())
        self._time_edit.setStyleSheet(f"""
            QTimeEdit {{
                background: {APP_COLORS['bg']};
                border: 1px solid {APP_COLORS['border']};
                border-radius: {RADIUS['md']}px;
                padding: 12px 16px;
                font-size: 28px;
                font-weight: 600;
                color: {APP_COLORS['text']};
                font-family: {FONT_FAMILY};
            }}
            QTimeEdit:focus {{
                border-color: {APP_COLORS['primary']};
            }}
            QTimeEdit::up-button, QTimeEdit::down-button {{
                width: 24px;
                border: none;
                background: {APP_COLORS['surface']};
                border-radius: {RADIUS['sm']}px;
            }}
        """)
        time_layout.addWidget(self._time_edit)
        
        hint = QLabel("💡 如果时间早于现在，将设置为明天")
        hint.setStyleSheet(f"""
            font-size: 11px;
            color: {APP_COLORS['text_secondary']};
            font-family: {FONT_FAMILY};
        """)
        time_layout.addWidget(hint)
        
        specific_layout.addWidget(time_container)
        
        layout.addWidget(self._specific_widget)
        self._specific_widget.hide()
        
        # 默认选中30分钟
        self._select_time(30)
    
    def _setup_progress_ring(self, layout: QVBoxLayout):
        """倒计时显示区域 - 极简大数字 + 线性进度条"""
        countdown_container = QFrame()
        countdown_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        countdown_container.setStyleSheet(f"""
            QFrame {{
                background: {APP_COLORS['surface']};
                border-radius: {RADIUS['lg']}px;
                border: 1px solid {APP_COLORS['border']};
            }}
        """)
        
        container_layout = QVBoxLayout(countdown_container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)
        
        # 大数字倒计时
        self._time_label = QLabel("--:--")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setStyleSheet(f"""
            font-size: 48px;
            font-weight: 700;
            color: {APP_COLORS['text']};
            font-family: 'Consolas', 'SF Mono', monospace;
            letter-spacing: 2px;
        """)
        container_layout.addWidget(self._time_label)
        
        # 状态文本
        self._status_label = QLabel("未设置定时关机")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"""
            font-size: 13px;
            color: {APP_COLORS['text_secondary']};
            font-family: {FONT_FAMILY};
        """)
        container_layout.addWidget(self._status_label)
        
        # 线性进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {APP_COLORS['border']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {APP_COLORS['primary']};
                border-radius: 4px;
            }}
        """)
        container_layout.addWidget(self._progress_bar)
        
        layout.addWidget(countdown_container)

    def _setup_buttons(self, layout: QVBoxLayout):
        """操作按钮 - 固定在底部"""
        btn_container = QWidget()
        btn_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, SPACING['md'], 0, 0)
        btn_layout.setSpacing(12)
        
        self._cancel_btn = QPushButton("取消定时")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setFixedHeight(48)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {APP_COLORS['surface']};
                color: {APP_COLORS['text']};
                border: 1px solid {APP_COLORS['border']};
                border-radius: {RADIUS['lg']}px;
                font-size: 14px;
                font-weight: 500;
                padding: 0 24px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                border-color: {APP_COLORS['error']};
                color: {APP_COLORS['error']};
            }}
            QPushButton:disabled {{
                color: {APP_COLORS['text_muted']};
                background: {APP_COLORS['bg']};
                border-color: {APP_COLORS['border']};
            }}
        """)
        self._cancel_btn.clicked.connect(self._cancel_shutdown)
        btn_layout.addWidget(self._cancel_btn)
        
        self._start_btn = QPushButton("开始定时")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.setFixedHeight(48)
        self._start_btn.setStyleSheet(f"""
            QPushButton {{
                background: {APP_COLORS['primary']};
                color: white;
                border: none;
                border-radius: {RADIUS['lg']}px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 32px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background: {APP_COLORS['primary_hover']};
            }}
            QPushButton:disabled {{
                background: {APP_COLORS['border']};
            }}
        """)
        self._start_btn.clicked.connect(self._start_shutdown)
        btn_layout.addWidget(self._start_btn)
        
        layout.addWidget(btn_container)
    
    def _switch_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._mode_toggle.set_mode(mode)
        
        if mode == "countdown":
            self._countdown_widget.show()
            self._specific_widget.hide()
        else:
            self._countdown_widget.hide()
            self._specific_widget.show()
            default_time = datetime.now() + timedelta(minutes=30)
            self._time_edit.setTime(default_time.time())
    
    def _select_time(self, minutes: int) -> None:
        self._selected_minutes = minutes
        self._slider.blockSignals(True)
        self._slider.setValue(minutes)
        self._slider.blockSignals(False)
        self._time_display.setText(self._format_duration(minutes))
        
        for chip in self._time_chips:
            chip.set_selected(chip.minutes == minutes)
    
    def _on_slider_change(self, value: int) -> None:
        self._selected_minutes = value
        self._time_display.setText(self._format_duration(value))
        for chip in self._time_chips:
            chip.set_selected(False)
    
    def _format_duration(self, minutes: int) -> str:
        if minutes < 60:
            return f"{minutes} 分钟"
        elif minutes % 60 == 0:
            return f"{minutes // 60} 小时"
        else:
            return f"{minutes // 60}小时{minutes % 60}分"

    def _start_shutdown(self) -> None:
        """开始定时关机"""
        if self._mode == "countdown":
            seconds = self._selected_minutes * 60
            self._scheduled_time = datetime.now() + timedelta(seconds=seconds)
        else:
            target = self._time_edit.time()
            now = datetime.now()
            target_dt = datetime(now.year, now.month, now.day, target.hour(), target.minute())
            if target_dt <= now:
                target_dt += timedelta(days=1)
            self._scheduled_time = target_dt
            seconds = int((target_dt - now).total_seconds())
        
        self._total_seconds = seconds
        
        try:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            result = subprocess.run(
                ["shutdown", "/s", "/t", str(seconds)],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                raise RuntimeError(result.stderr or "未知错误")
            
            self._start_btn.setEnabled(False)
            self._cancel_btn.setEnabled(True)
            self._warning_shown = False
            self._timer.start(1000)
            self._update_countdown()
            
            # 禁用选择控件
            self._countdown_widget.setEnabled(False)
            self._specific_widget.setEnabled(False)
            self._mode_toggle.set_enabled(False)
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"设置失败: {e}")
    
    def _cancel_shutdown(self) -> None:
        """取消定时关机"""
        try:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self._timer.stop()
            self._scheduled_time = None
            self._total_seconds = 0
            self._start_btn.setEnabled(True)
            self._cancel_btn.setEnabled(False)
            self._warning_shown = False
            
            # 重置倒计时显示
            self._time_label.setText("--:--")
            self._status_label.setText("未设置定时关机")
            self._progress_bar.setValue(0)
            self._update_progress_color(1.0)
            
            self._countdown_widget.setEnabled(True)
            self._specific_widget.setEnabled(True)
            self._mode_toggle.set_enabled(True)
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"取消失败: {e}")
    
    def _update_countdown(self) -> None:
        """更新倒计时"""
        if not self._scheduled_time:
            return
        
        remaining = (self._scheduled_time - datetime.now()).total_seconds()
        
        if remaining <= 0:
            self._timer.stop()
            self._time_label.setText("00:00")
            self._status_label.setText("即将关机...")
            self._progress_bar.setValue(0)
            return
        
        remaining = int(remaining)
        progress = remaining / self._total_seconds if self._total_seconds > 0 else 0
        
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        
        # 格式化时间显示
        if hours > 0:
            time_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_text = f"{minutes:02d}:{seconds:02d}"
        
        shutdown_time = self._scheduled_time.strftime("%H:%M")
        
        # 更新显示
        self._time_label.setText(time_text)
        self._status_label.setText(f"将于 {shutdown_time} 关机")
        self._progress_bar.setValue(int(progress * 1000))
        
        # 根据进度更新颜色
        self._update_progress_color(progress)
        
        if remaining <= 60 and not self._warning_shown:
            self._warning_shown = True
            self._show_warning()
    
    def _update_progress_color(self, progress: float) -> None:
        """根据进度更新进度条和数字颜色"""
        if progress > 0.5:
            color = APP_COLORS['primary']
        elif progress > 0.2:
            color = APP_COLORS['warning']
        else:
            color = APP_COLORS['error']
        
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {APP_COLORS['border']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 4px;
            }}
        """)

    def _show_warning(self) -> None:
        """关机前警告"""
        msg = QMessageBox(self)
        msg.setWindowTitle("即将关机")
        msg.setText("⚠️ 电脑将在 1 分钟内关机！")
        msg.setInformativeText("请保存所有未保存的工作。")
        msg.setIcon(QMessageBox.Icon.Warning)
        
        cancel_btn = msg.addButton("取消关机", QMessageBox.ButtonRole.RejectRole)
        extend_btn = msg.addButton("延长 10 分钟", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("确定", QMessageBox.ButtonRole.YesRole)
        
        msg.exec()
        
        if msg.clickedButton() == cancel_btn:
            self._cancel_shutdown()
        elif msg.clickedButton() == extend_btn:
            self._extend_shutdown(10)
    
    def _extend_shutdown(self, minutes: int) -> None:
        """延长关机时间"""
        try:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            seconds = minutes * 60
            self._scheduled_time = datetime.now() + timedelta(seconds=seconds)
            self._total_seconds = seconds
            
            result = subprocess.run(
                ["shutdown", "/s", "/t", str(seconds)],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                raise RuntimeError(result.stderr or "未知错误")
            
            self._warning_shown = False
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"延长失败: {e}")
    
    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
