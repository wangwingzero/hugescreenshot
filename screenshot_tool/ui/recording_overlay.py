# -*- coding: utf-8 -*-
"""
录制覆盖层 UI 模块

提供录制时的红色边框和控制面板。

Feature: screen-recording
"""

import sys
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QPushButton, QVBoxLayout,
    QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QScreen, QKeyEvent

from screenshot_tool.core.topmost_window_manager import TopmostWindowManager


def _exclude_from_capture(widget: QWidget):
    """将窗口从屏幕捕获中排除
    
    使用 Windows API SetWindowDisplayAffinity 让窗口不被录屏软件捕获。
    需要 Windows 10 2004 (Build 19041) 或更高版本。
    
    Args:
        widget: 要排除的 Qt 窗口
    """
    if sys.platform != 'win32':
        return
    
    try:
        import ctypes
        
        # WDA_EXCLUDEFROMCAPTURE = 0x00000011
        # 这个值让窗口在屏幕上正常显示，但不会被屏幕捕获程序录制
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        
        # 获取窗口句柄
        hwnd = int(widget.winId())
        
        # 调用 SetWindowDisplayAffinity
        user32 = ctypes.windll.user32
        result = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        
        if result:
            pass  # 成功，静默处理
        else:
            # 失败可能是因为 Windows 版本太旧，静默忽略
            pass
            
    except Exception:
        # 任何错误都静默忽略，不影响正常功能
        pass


class RecordingBorderOverlay(QWidget):
    """录制区域红色边框覆盖层

    显示在录制区域外围的红色边框，带有闪烁效果。
    使用四个独立的边框条，确保不覆盖录制区域，不会被录进视频。
    """

    def __init__(self, region: QRect, parent=None):
        super().__init__(parent)
        self._region = region
        self._border_width = 3
        self._border_visible = True
        
        # 创建四个边框条（上、下、左、右）
        self._borders = []
        self._create_borders()

        # 闪烁效果定时器（1.5秒一次，更柔和）
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_border)
        self._blink_timer.start(1500)  # 1500ms 闪烁，更慢更舒适

    def _create_borders(self):
        """创建四个边框条"""
        # 清理旧的边框
        for border in self._borders:
            border.deleteLater()
        self._borders = []
        
        region = self._region
        bw = self._border_width
        
        # 四个边框的位置和大小
        # 上边框：在录制区域上方
        top_rect = QRect(region.x() - bw, region.y() - bw, region.width() + bw * 2, bw)
        # 下边框：在录制区域下方
        bottom_rect = QRect(region.x() - bw, region.y() + region.height(), region.width() + bw * 2, bw)
        # 左边框：在录制区域左侧
        left_rect = QRect(region.x() - bw, region.y(), bw, region.height())
        # 右边框：在录制区域右侧
        right_rect = QRect(region.x() + region.width(), region.y(), bw, region.height())
        
        for rect in [top_rect, bottom_rect, left_rect, right_rect]:
            border = _BorderBar(rect, self)
            self._borders.append(border)

    def _toggle_border(self):
        """切换边框可见性"""
        self._border_visible = not self._border_visible
        for border in self._borders:
            border.set_visible(self._border_visible)

    def show(self):
        """显示所有边框"""
        for border in self._borders:
            border.show()

    def hide(self):
        """隐藏所有边框"""
        for border in self._borders:
            border.hide()

    def stop_blinking(self):
        """停止闪烁，保持边框可见"""
        self._blink_timer.stop()
        self._border_visible = True
        for border in self._borders:
            border.set_visible(True)

    def start_blinking(self):
        """开始闪烁"""
        if not self._blink_timer.isActive():
            self._blink_timer.start(500)

    def update_region(self, region: QRect):
        """更新录制区域"""
        self._region = region
        self._create_borders()
        if self._border_visible:
            self.show()

    def cleanup(self):
        """清理资源"""
        self._blink_timer.stop()
        for border in self._borders:
            border.hide()
            border.deleteLater()
        self._borders = []


class _BorderBar(QWidget):
    """单个边框条"""
    
    def __init__(self, rect: QRect, parent=None):
        super().__init__(None)  # 独立窗口，不设置 parent
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        self.setGeometry(rect)
        self.setStyleSheet("background-color: #FF6B6B;")  # 柔和的珊瑚红
        self._visible = True
        self._exclude_applied = False
    
    def show(self):
        """显示边框条，并设置为不被录屏捕获"""
        super().show()
        # 窗口显示后才能设置 DisplayAffinity
        if not self._exclude_applied:
            _exclude_from_capture(self)
            self._exclude_applied = True
    
    def set_visible(self, visible: bool):
        """设置可见性"""
        self._visible = visible
        if visible:
            self.setStyleSheet("background-color: #FF6B6B;")  # 柔和的珊瑚红
        else:
            self.setStyleSheet("background-color: transparent;")


class RecordingControlPanel(QWidget):
    """录制控制面板

    悬浮在录制区域附近，显示录制时间和控制按钮。
    使用 Windows API 排除窗口，不会被录进视频。
    支持拖动移动位置。
    """

    # 信号
    pause_clicked = Signal()
    resume_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_paused = False
        self._elapsed_seconds = 0
        self._exclude_applied = False  # 标记是否已应用排除捕获
        self._drag_position = None  # 拖动起始位置
        self._setup_ui()

        # 时间更新定时器
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time)
        
        # 注册到全局置顶窗口管理器
        # Feature: emergency-esc-exit
        # Requirements: 2.1, 4.1
        TopmostWindowManager.instance().register_window(
            self,
            window_type="RecordingControlPanel",
            can_receive_focus=True
        )
    
    def show(self):
        """显示控制面板，并设置为不被录屏捕获"""
        super().show()
        # 窗口显示后才能设置 DisplayAffinity
        if not self._exclude_applied:
            _exclude_from_capture(self)
            self._exclude_applied = True

    def mousePressEvent(self, event):
        """鼠标按下事件 - 开始拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 拖动窗口"""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 结束拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
            event.accept()
        super().mouseReleaseEvent(event)

    def _setup_ui(self):
        """设置 UI"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.SizeAllCursor)  # 设置拖动光标
        
        # 设置焦点策略，允许接收键盘事件
        # Feature: emergency-esc-exit
        # Requirements: 2.3
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 容器
        container = QWidget()
        container.setObjectName("recording_panel")
        container.setStyleSheet("""
            QWidget#recording_panel {
                background-color: rgba(30, 30, 30, 240);
                border-radius: 8px;
                border: 1px solid rgba(255, 0, 0, 150);
            }
        """)

        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(12)

        # 录制指示器（红色圆点）
        self._indicator = QLabel("🔴")
        self._indicator.setStyleSheet("font-size: 14px;")
        container_layout.addWidget(self._indicator)

        # 录制时间
        self._time_label = QLabel("00:00")
        self._time_label.setStyleSheet("""
            QLabel {
                color: #FF4444;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Consolas', monospace;
                min-width: 50px;
            }
        """)
        container_layout.addWidget(self._time_label)

        # 分隔线
        sep = QWidget()
        sep.setFixedSize(1, 24)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 50);")
        container_layout.addWidget(sep)

        # 暂停/继续按钮
        self._pause_btn = QPushButton("⏸")
        self._pause_btn.setFixedSize(36, 36)
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(80, 80, 80, 200);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(100, 100, 100, 220);
            }
            QPushButton:pressed {
                background-color: rgba(60, 60, 60, 220);
            }
        """)
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        container_layout.addWidget(self._pause_btn)

        # 停止按钮
        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setFixedSize(36, 36)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 50, 50, 220);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(220, 70, 70, 240);
            }
            QPushButton:pressed {
                background-color: rgba(180, 40, 40, 220);
            }
        """)
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        container_layout.addWidget(self._stop_btn)

        layout.addWidget(container)

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 2)
        container.setGraphicsEffect(shadow)

        self.adjustSize()

    def _on_pause_clicked(self):
        """暂停/继续按钮点击"""
        if self._is_paused:
            self._is_paused = False
            self._pause_btn.setText("⏸")
            self._indicator.setText("🔴")
            self.resume_clicked.emit()
        else:
            self._is_paused = True
            self._pause_btn.setText("▶")
            self._indicator.setText("⏸")
            self.pause_clicked.emit()

    def _update_time(self):
        """更新时间显示 - 现在由外部 set_time 调用，此方法保留用于内部更新"""
        self._update_time_display()

    def _update_time_display(self):
        """更新时间标签"""
        minutes = self._elapsed_seconds // 60
        seconds = self._elapsed_seconds % 60
        self._time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def start_timer(self):
        """开始计时 - 不再使用内部定时器递增，完全依赖外部同步"""
        self._elapsed_seconds = 0
        self._is_paused = False
        self._update_time_display()
        # 注意：不再启动内部定时器，时间由外部通过 set_time 同步

    def stop_timer(self):
        """停止计时"""
        self._time_timer.stop()

    def set_time(self, seconds: float):
        """设置时间（从外部同步）- 这是主要的时间更新方式"""
        self._elapsed_seconds = int(seconds)
        self._update_time_display()

    def position_near_region(self, region: QRect, screen: QScreen = None):
        """将控制面板放置在录制区域外部
        
        确保控制面板永远不会出现在录制区域内，避免被录进视频。

        Args:
            region: 录制区域
            screen: 屏幕对象
        """
        if screen is None:
            screen = QApplication.primaryScreen()

        screen_geo = screen.geometry()
        panel_width = self.width()
        panel_height = self.height()
        
        # 计算各个方向的可用空间
        space_below = screen_geo.bottom() - (region.y() + region.height())
        space_above = region.y() - screen_geo.top()
        space_right = screen_geo.right() - (region.x() + region.width())
        space_left = region.x() - screen_geo.left()
        
        # 水平居中位置
        center_x = region.x() + (region.width() - panel_width) // 2
        center_x = max(screen_geo.left() + 10, min(center_x, screen_geo.right() - panel_width - 10))
        
        # 垂直居中位置（用于左右放置时）
        center_y = region.y() + (region.height() - panel_height) // 2
        center_y = max(screen_geo.top() + 10, min(center_y, screen_geo.bottom() - panel_height - 10))

        # 优先级：下方 > 上方 > 右侧 > 左侧
        if space_below >= panel_height + 15:
            # 放在下方
            x = center_x
            y = region.y() + region.height() + 10
        elif space_above >= panel_height + 15:
            # 放在上方
            x = center_x
            y = region.y() - panel_height - 10
        elif space_right >= panel_width + 15:
            # 放在右侧
            x = region.x() + region.width() + 10
            y = center_y
        elif space_left >= panel_width + 15:
            # 放在左侧
            x = region.x() - panel_width - 10
            y = center_y
        else:
            # 所有方向都没有足够空间，放在屏幕右下角（远离录制区域）
            x = screen_geo.right() - panel_width - 20
            y = screen_geo.bottom() - panel_height - 20
            
            # 如果右下角在录制区域内，尝试左下角
            if region.contains(QPoint(x + panel_width // 2, y + panel_height // 2)):
                x = screen_geo.left() + 20
            
            # 如果还是在录制区域内，尝试右上角
            if region.contains(QPoint(x + panel_width // 2, y + panel_height // 2)):
                y = screen_geo.top() + 20

        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件 - ESC 停止录制
        
        Feature: emergency-esc-exit
        Requirements: 2.1, 2.2
        """
        if event.key() == Qt.Key.Key_Escape:
            self.stop_clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def cleanup(self):
        """清理资源"""
        # 从全局置顶窗口管理器注销
        # Feature: emergency-esc-exit
        TopmostWindowManager.instance().unregister_window(self)
        self._time_timer.stop()
        self.hide()
        self.deleteLater()


class RecordingOverlayManager(QWidget):
    """录制覆盖层管理器

    统一管理边框和控制面板。
    """

    # 信号
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._border: RecordingBorderOverlay = None
        self._control_panel: RecordingControlPanel = None
        self._region: QRect = None

    def start(self, region: QRect, screen: QScreen = None):
        """开始显示覆盖层

        Args:
            region: 录制区域
            screen: 屏幕对象
        """
        self._region = region

        # 创建边框
        self._border = RecordingBorderOverlay(region)
        self._border.show()

        # 创建控制面板
        self._control_panel = RecordingControlPanel()
        self._control_panel.pause_clicked.connect(self.pause_requested.emit)
        self._control_panel.resume_clicked.connect(self.resume_requested.emit)
        self._control_panel.stop_clicked.connect(self.stop_requested.emit)
        self._control_panel.position_near_region(region, screen)
        self._control_panel.start_timer()
        self._control_panel.show()

    def stop(self):
        """停止并隐藏覆盖层"""
        if self._border:
            self._border.cleanup()
            self._border = None

        if self._control_panel:
            self._control_panel.cleanup()
            self._control_panel = None

    def update_time(self, seconds: float):
        """更新时间显示"""
        if self._control_panel:
            self._control_panel.set_time(seconds)

    def set_paused(self, paused: bool):
        """设置暂停状态（同步边框闪烁）"""
        if self._border:
            if paused:
                self._border.stop_blinking()
            else:
                self._border.start_blinking()

    @property
    def is_active(self) -> bool:
        """是否处于活动状态"""
        return self._border is not None or self._control_panel is not None


def test_overlay():
    """测试覆盖层"""
    import sys
    app = QApplication(sys.argv)

    # 获取屏幕尺寸
    screen = app.primaryScreen()
    screen_geo = screen.geometry()

    # 创建一个测试区域（屏幕中央 800x600）
    region = QRect(
        screen_geo.x() + (screen_geo.width() - 800) // 2,
        screen_geo.y() + (screen_geo.height() - 600) // 2,
        800, 600
    )

    # 创建覆盖层管理器
    manager = RecordingOverlayManager()

    def on_stop():
        print("停止录制")
        manager.stop()
        app.quit()

    manager.stop_requested.connect(on_stop)
    manager.pause_requested.connect(lambda: print("暂停"))
    manager.resume_requested.connect(lambda: print("继续"))

    manager.start(region, screen)

    sys.exit(app.exec())


if __name__ == "__main__":
    test_overlay()
