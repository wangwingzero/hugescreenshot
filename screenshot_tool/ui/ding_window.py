# =====================================================
# =============== 屏幕贴图窗口 ===============
# =====================================================

"""
屏幕贴图窗口 - 将截图钉在屏幕上方便参考

Requirements: 1.1-1.10
Features:
- 无边框置顶窗口
- 拖拽移动
- 鼠标滚轮缩放 (10%-500%)
- 透明度调节 (10%-100%)
- 右键菜单
- 双击切换大小
- 窗口阴影效果
"""

import gc
from functools import partial

from PySide6.QtWidgets import QWidget, QLabel, QMenu, QApplication, QFileDialog, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QImage, QPixmap, QAction, QMouseEvent, QWheelEvent, QGuiApplication, QColor
from typing import Optional, List


class DingWindow(QWidget):
    """屏幕贴图窗口 - 将截图钉在屏幕上"""
    
    # 信号
    closed = Signal()
    
    # 缩放范围
    MIN_ZOOM = 0.1  # 10%
    MAX_ZOOM = 5.0  # 500%
    
    # 透明度范围
    MIN_OPACITY = 0.1  # 10%
    MAX_OPACITY = 1.0  # 100%
    
    # 阴影边距（用于窗口大小计算）
    SHADOW_MARGIN = 15
    
    # 边框内边距（padding + border）
    BORDER_PADDING = 4  # 3px padding + 1px border
    
    def __init__(self, image: QImage, position: QPoint, parent=None):
        """
        创建贴图窗口
        
        Args:
            image: 要显示的图片（物理像素大小）
            position: 初始位置
        """
        super().__init__(parent)
        
        self._original_image = image.copy()
        self._current_zoom = 1.0
        self._is_original_size = True
        self._drag_position: Optional[QPoint] = None
        
        self._setup_window()
        self._setup_ui()
        self._setup_context_menu()
        
        # 设置初始位置（补偿阴影边距和边框内边距，使图片位置准确）
        total_offset = self.SHADOW_MARGIN + self.BORDER_PADDING
        adjusted_position = QPoint(
            position.x() - total_offset,
            position.y() - total_offset
        )
        self.move(adjusted_position)
        
        # 显示图片
        self._update_display()
    
    def _setup_window(self):
        """设置窗口属性"""
        # 无边框、置顶、工具窗口
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        # 透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    def _setup_ui(self):
        """设置UI"""
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 添加白色边框背景
        self._label.setStyleSheet("""
            background-color: white;
            border: 1px solid #e0e0e0;
            padding: 3px;
        """)
        
        # 添加阴影效果
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setBlurRadius(self.SHADOW_MARGIN)
        self._shadow_effect.setColor(QColor(0, 0, 0, 80))
        self._shadow_effect.setOffset(0, 3)
        self._label.setGraphicsEffect(self._shadow_effect)

    def _setup_context_menu(self):
        """设置右键菜单"""
        self._context_menu = QMenu(self)
        
        # 复制
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self._copy_to_clipboard)
        self._context_menu.addAction(copy_action)
        
        # 保存
        save_action = QAction("保存", self)
        save_action.triggered.connect(self._save_image)
        self._context_menu.addAction(save_action)
        
        self._context_menu.addSeparator()
        
        # 缩放调节
        zoom_menu = self._context_menu.addMenu("缩放")
        for zoom_percent in [500, 300, 200, 150, 100, 75, 50, 25, 10]:
            action = QAction(f"{zoom_percent}%", self)
            action.triggered.connect(lambda checked, z=zoom_percent: self.zoom(z / 100))
            zoom_menu.addAction(action)
        
        # 透明度调节
        opacity_menu = self._context_menu.addMenu("透明度")
        for opacity in [100, 80, 60, 40, 20, 10]:
            action = QAction(f"{opacity}%", self)
            action.triggered.connect(lambda checked, o=opacity: self.set_opacity(o / 100))
            opacity_menu.addAction(action)
        
        self._context_menu.addSeparator()
        
        # 原始大小
        original_size_action = QAction("原始大小", self)
        original_size_action.triggered.connect(self._reset_to_original_size)
        self._context_menu.addAction(original_size_action)
        
        self._context_menu.addSeparator()
        
        # 关闭
        close_action = QAction("关闭", self)
        close_action.triggered.connect(self.close)
        self._context_menu.addAction(close_action)
    
    def _update_display(self):
        """更新显示 - 正确处理高DPI屏幕"""
        if self._original_image.isNull():
            return
        
        # 获取当前窗口所在屏幕的 DPR（支持多显示器不同缩放）
        dpr = self._get_current_screen_dpr()
        
        # 原始图片是物理像素大小，需要转换为逻辑像素显示
        # 逻辑尺寸 = 物理尺寸 / DPR
        original_size = self._original_image.size()
        logical_width = original_size.width() / dpr
        logical_height = original_size.height() / dpr
        
        # 应用用户缩放，确保最小尺寸为 1
        display_width = max(1, int(logical_width * self._current_zoom))
        display_height = max(1, int(logical_height * self._current_zoom))
        
        # 创建 pixmap 并设置设备像素比
        pixmap = QPixmap.fromImage(self._original_image)
        pixmap.setDevicePixelRatio(dpr)
        
        # 如果需要缩放（用户手动缩放了）
        if abs(self._current_zoom - 1.0) > 0.01:
            # 计算缩放后的物理像素尺寸，确保最小为 1
            scaled_phys_width = max(1, int(display_width * dpr))
            scaled_phys_height = max(1, int(display_height * dpr))
            
            # 缩放图片
            scaled_image = self._original_image.scaled(
                scaled_phys_width, scaled_phys_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            pixmap = QPixmap.fromImage(scaled_image)
            pixmap.setDevicePixelRatio(dpr)
        
        # 显示
        self._label.setPixmap(pixmap)
        
        # label 大小 = 图片大小 + 边框内边距
        label_width = display_width + self.BORDER_PADDING * 2
        label_height = display_height + self.BORDER_PADDING * 2
        self._label.setFixedSize(label_width, label_height)
        
        # 窗口大小需要包含阴影边距
        window_width = label_width + self.SHADOW_MARGIN * 2
        window_height = label_height + self.SHADOW_MARGIN * 2
        self.setFixedSize(window_width, window_height)
        
        # 将 label 居中放置（留出阴影空间）
        self._label.move(self.SHADOW_MARGIN, self.SHADOW_MARGIN)
    
    def _get_current_screen_dpr(self) -> float:
        """获取当前窗口所在屏幕的设备像素比"""
        # 尝试获取窗口所在的屏幕
        screen = self.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 1.0
        dpr = screen.devicePixelRatio()
        # 确保 DPR 至少为 1.0，避免除零
        return max(1.0, dpr)
    
    def set_opacity(self, opacity: float):
        """设置透明度 (0.1 - 1.0)"""
        clamped = max(self.MIN_OPACITY, min(self.MAX_OPACITY, opacity))
        self.setWindowOpacity(clamped)
    
    def get_opacity(self) -> float:
        """获取当前透明度"""
        return self.windowOpacity()
    
    def zoom(self, factor: float):
        """缩放图片 (0.1 - 5.0)"""
        clamped = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self._current_zoom = clamped
        self._is_original_size = (abs(clamped - 1.0) < 0.01)
        self._update_display()
    
    def get_zoom(self) -> float:
        """获取当前缩放比例"""
        return self._current_zoom
    
    def fit_to_content(self):
        """调整窗口大小以适应内容"""
        self._label.adjustSize()
        label_size = self._label.size()
        window_width = label_size.width() + self.SHADOW_MARGIN * 2
        window_height = label_size.height() + self.SHADOW_MARGIN * 2
        self.setFixedSize(window_width, window_height)
    
    def toggle_size(self):
        """切换原始大小/适应大小"""
        if abs(self._current_zoom - 1.0) < 0.01:
            # 当前是原始大小，切换到50%
            self.zoom(0.5)
        else:
            # 切换回原始大小
            self.zoom(1.0)
    
    def _copy_to_clipboard(self):
        """复制到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setImage(self._original_image)
    
    def _save_image(self):
        """保存图片"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)"
        )
        if file_path:
            self._original_image.save(file_path)
    
    def _reset_to_original_size(self):
        """重置为原始大小"""
        self.zoom(1.0)

    # ========================= 事件处理 =========================
    
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._context_menu.exec(event.globalPosition().toPoint())
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件 - 拖拽"""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position:
            new_pos = event.globalPosition().toPoint() - self._drag_position
            self.move(new_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        self._drag_position = None
        event.accept()
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击事件 - 切换大小"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_size()
            event.accept()
    
    def wheelEvent(self, event: QWheelEvent):
        """滚轮事件 - 缩放"""
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        
        if delta > 0:
            # 放大
            new_zoom = self._current_zoom * 1.1
        else:
            # 缩小
            new_zoom = self._current_zoom / 1.1
        
        self.zoom(new_zoom)
        event.accept()
    
    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件
        
        增强的清理方法，确保释放所有内存资源：
        - 释放图片引用
        - 清理 UI 组件
        - 断开信号
        - 调用 deleteLater
        
        Requirements: 1.1, 1.2, 1.4
        """
        # 释放图片引用 (Requirements: 1.1)
        self._original_image = None
        
        # 清理 label 的 pixmap
        if hasattr(self, '_label') and self._label:
            self._label.setPixmap(QPixmap())
            # 清理阴影效果
            if hasattr(self, '_shadow_effect') and self._shadow_effect:
                self._label.setGraphicsEffect(None)
                self._shadow_effect = None
        
        # 清理右键菜单
        if hasattr(self, '_context_menu') and self._context_menu:
            self._context_menu.deleteLater()
            self._context_menu = None
        
        # 发出关闭信号（在断开之前）
        try:
            self.closed.emit()
        except RuntimeError:
            # 信号可能已被断开
            pass
        
        # 安全断开信号 (Requirements: 1.4)
        # 注意：使用 partial 连接的信号可能无法正常断开，忽略警告
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Failed to disconnect")
            try:
                self.closed.disconnect()
            except (RuntimeError, TypeError):
                pass
        
        # 调用 deleteLater 确保 Qt 对象被正确清理 (Requirements: 1.2)
        self.deleteLater()
        
        super().closeEvent(event)


class DingManager:
    """管理所有贴图窗口"""
    
    def __init__(self):
        self._windows: List[DingWindow] = []
    
    def create_ding(self, image: QImage, position: QPoint) -> DingWindow:
        """创建新的贴图窗口"""
        window = DingWindow(image, position)
        # 使用 partial 避免 lambda 闭包问题
        window.closed.connect(partial(self._on_window_closed, window))
        self._windows.append(window)
        window.show()
        return window
    
    def _on_window_closed(self, window: DingWindow):
        """窗口关闭回调
        
        增强的清理方法，确保释放内存：
        - 从列表移除窗口引用
        - 触发垃圾回收
        
        Requirements: 1.3, 5.2
        """
        if window in self._windows:
            self._windows.remove(window)
        
        # 触发垃圾回收，释放大图片对象
        gc.collect()
    
    def close_all(self):
        """关闭所有贴图窗口
        
        增强的清理方法，确保释放内存：
        - 关闭所有窗口
        - 清空列表
        - 触发垃圾回收
        
        Requirements: 5.2
        """
        for window in self._windows[:]:  # 使用副本遍历
            window.close()
        self._windows.clear()
        
        # 触发垃圾回收
        gc.collect()
    
    def get_window_count(self) -> int:
        """获取当前贴图窗口数量"""
        return len(self._windows)
    
    def get_windows(self) -> List[DingWindow]:
        """获取所有贴图窗口"""
        return self._windows.copy()
