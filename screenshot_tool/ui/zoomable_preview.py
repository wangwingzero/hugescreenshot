# =====================================================
# =============== 可缩放预览组件 ===============
# =====================================================

"""
ZoomablePreviewWidget - 可缩放的图片预览组件

功能：
- 滚轮缩放（0.1x - 5.0x）
- 拖动平移
- 重置缩放
- 适应窗口显示

Requirements: 3.1, 3.2, 3.3, 3.5
Property 3: 预览缩放不变性
"""

from typing import Optional

from PySide6.QtCore import Qt, QPoint, QPointF, Signal
from PySide6.QtGui import QImage, QPainter, QWheelEvent, QMouseEvent, QPaintEvent, QColor
from PySide6.QtWidgets import QWidget


class ZoomablePreviewWidget(QWidget):
    """可缩放的图片预览组件
    
    Property 3: 预览缩放不变性
    - 缩放级别在有效范围内（0.1x - 5.0x）
    - 重置操作后缩放级别恢复到适应窗口的默认值
    - 图片内容不因缩放而失真或丢失
    """
    
    # 信号
    zoomChanged = Signal(int)  # 缩放百分比变化
    
    # 缩放范围常量
    MIN_ZOOM = 0.1
    MAX_ZOOM = 5.0
    ZOOM_STEP = 0.1
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 图片数据
        self._image: Optional[QImage] = None
        self._scaled_cache: Optional[QImage] = None  # 缩放后的图片缓存
        self._cache_zoom: float = 0.0  # 缓存对应的缩放级别
        
        # 缩放和平移状态
        self._zoom_level: float = 1.0
        self._pan_offset: QPointF = QPointF(0, 0)
        
        # 拖动状态
        self._dragging: bool = False
        self._drag_start: QPoint = QPoint()
        self._drag_offset_start: QPointF = QPointF()
        
        # 适应窗口的初始缩放
        self._fit_zoom: float = 1.0
        
        # 设置鼠标追踪和光标
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        
        # 背景色
        self._bg_color = QColor(40, 40, 40)
    
    def set_image(self, image: QImage) -> None:
        """设置图片"""
        if image is None or image.isNull():
            self._image = None
            self._scaled_cache = None
            self._cache_zoom = 0.0
        else:
            self._image = image.copy()
            self._scaled_cache = None  # 清除缓存
            self._cache_zoom = 0.0
        
        # 计算适应窗口的缩放
        self._calculate_fit_zoom()
        
        # 重置到适应窗口
        self.reset_zoom()
        
        self.update()
    
    def get_image(self) -> Optional[QImage]:
        """获取当前图片"""
        return self._image
    
    def zoom_in(self) -> None:
        """放大"""
        new_zoom = min(self._zoom_level + self.ZOOM_STEP, self.MAX_ZOOM)
        self._set_zoom(new_zoom)
    
    def zoom_out(self) -> None:
        """缩小"""
        new_zoom = max(self._zoom_level - self.ZOOM_STEP, self.MIN_ZOOM)
        self._set_zoom(new_zoom)
    
    def reset_zoom(self) -> None:
        """重置缩放到适应窗口"""
        self._zoom_level = self._fit_zoom
        self._pan_offset = QPointF(0, 0)
        self._center_image()
        self.zoomChanged.emit(self.get_zoom_percent())
        self.update()
    
    def set_zoom(self, zoom: float) -> None:
        """设置缩放级别"""
        self._set_zoom(zoom)
    
    def get_zoom_level(self) -> float:
        """获取当前缩放级别"""
        return self._zoom_level
    
    def get_zoom_percent(self) -> int:
        """获取当前缩放百分比"""
        return int(self._zoom_level * 100)
    
    def _set_zoom(self, zoom: float, center: Optional[QPoint] = None) -> None:
        """设置缩放级别（内部方法）"""
        # 限制缩放范围
        zoom = max(self.MIN_ZOOM, min(zoom, self.MAX_ZOOM))
        
        if abs(zoom - self._zoom_level) < 0.001:
            return
        
        # 如果指定了中心点，以该点为中心缩放
        if center is not None and self._image is not None:
            # 计算中心点在图片上的位置
            old_zoom = self._zoom_level
            img_x = (center.x() - self._pan_offset.x()) / old_zoom
            img_y = (center.y() - self._pan_offset.y()) / old_zoom
            
            # 更新缩放
            self._zoom_level = zoom
            
            # 调整偏移，使中心点保持不变
            self._pan_offset = QPointF(
                center.x() - img_x * zoom,
                center.y() - img_y * zoom
            )
        else:
            self._zoom_level = zoom
        
        self.zoomChanged.emit(self.get_zoom_percent())
        self.update()
    
    def _calculate_fit_zoom(self) -> None:
        """计算适应窗口的缩放级别"""
        if self._image is None or self._image.isNull():
            self._fit_zoom = 1.0
            return
        
        widget_w = self.width()
        widget_h = self.height()
        img_w = self._image.width()
        img_h = self._image.height()
        
        if widget_w <= 0 or widget_h <= 0 or img_w <= 0 or img_h <= 0:
            self._fit_zoom = 1.0
            return
        
        # 计算适应窗口的缩放（留一点边距）
        margin = 10
        zoom_w = (widget_w - margin * 2) / img_w
        zoom_h = (widget_h - margin * 2) / img_h
        
        # 选择较小的缩放比例以完全显示图片，不限制最大值
        self._fit_zoom = min(zoom_w, zoom_h)
        self._fit_zoom = max(self._fit_zoom, self.MIN_ZOOM)
    
    def _center_image(self) -> None:
        """将图片居中"""
        if self._image is None or self._image.isNull():
            return
        
        img_w = self._image.width() * self._zoom_level
        img_h = self._image.height() * self._zoom_level
        
        self._pan_offset = QPointF(
            (self.width() - img_w) / 2,
            (self.height() - img_h) / 2
        )
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """滚轮缩放"""
        if self._image is None:
            return
        
        # 获取滚轮方向
        delta = event.angleDelta().y()
        
        if delta > 0:
            # 放大
            new_zoom = min(self._zoom_level * 1.1, self.MAX_ZOOM)
        else:
            # 缩小
            new_zoom = max(self._zoom_level / 1.1, self.MIN_ZOOM)
        
        # 以鼠标位置为中心缩放
        self._set_zoom(new_zoom, event.position().toPoint())
        
        event.accept()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标按下 - 开始拖动"""
        if event.button() == Qt.MouseButton.LeftButton and self._image is not None:
            self._dragging = True
            self._drag_start = event.pos()
            self._drag_offset_start = QPointF(self._pan_offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动 - 拖动平移"""
        if self._dragging:
            delta = event.pos() - self._drag_start
            self._pan_offset = QPointF(
                self._drag_offset_start.x() + delta.x(),
                self._drag_offset_start.y() + delta.y()
            )
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制图片"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 绘制背景
        painter.fillRect(self.rect(), self._bg_color)
        
        if self._image is None or self._image.isNull():
            # 绘制提示文字
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无图片")
            return
        
        # 计算绘制区域
        img_w = int(self._image.width() * self._zoom_level)
        img_h = int(self._image.height() * self._zoom_level)
        
        x = int(self._pan_offset.x())
        y = int(self._pan_offset.y())
        
        # 使用缓存的缩放图片（避免每次 paintEvent 都重新缩放）
        if self._scaled_cache is None or abs(self._cache_zoom - self._zoom_level) > 0.001:
            self._scaled_cache = self._image.scaled(
                img_w, img_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._cache_zoom = self._zoom_level
        
        # 绘制图片
        painter.drawImage(x, y, self._scaled_cache)
    
    def resizeEvent(self, event) -> None:
        """窗口大小变化"""
        super().resizeEvent(event)
        
        # 重新计算适应窗口的缩放
        old_fit = self._fit_zoom
        self._calculate_fit_zoom()
        
        # 清除缩放缓存（尺寸变化后需要重新缩放）
        self._scaled_cache = None
        self._cache_zoom = 0.0
        
        # 如果当前是适应窗口状态，更新缩放
        # 使用相对误差比较，避免 old_fit 为 0 时的问题
        if old_fit > 0 and abs(self._zoom_level - old_fit) / old_fit < 0.05:
            self._zoom_level = self._fit_zoom
            self._center_image()
            self.zoomChanged.emit(self.get_zoom_percent())
        
        self.update()
