# -*- coding: utf-8 -*-
"""
截图预览面板 - 分屏视图左侧组件

功能：
- 显示截图预览（支持缩放）
- 工具栏（缩放控制、编辑、复制、保存按钮）
- 状态栏（缩放级别显示）
- 支持标注渲染

Feature: screenshot-ocr-split-view
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 5.1-5.6

最佳实践:
- QScrollArea + QLabel 实现图片显示
- Ctrl+滚轮缩放，锚定到鼠标位置
- 缓存预缩放 Pixmap 优化性能
- 设置缩放范围限制 (0.1x - 5.0x)
"""

from typing import Optional, List, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QToolButton, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QImage, QPixmap, QPainter, QWheelEvent


# Flat Design 配色 (Productivity Tool)
# Requirements: 5.1-5.6
COLORS = {
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "primary_light": "#EFF6FF",
    "bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "text": "#1E293B",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    "border": "#E2E8F0",
}

FONT = '"Segoe UI", "Microsoft YaHei UI", system-ui, sans-serif'


class ScreenshotPreviewPanel(QWidget):
    """截图预览面板
    
    Feature: screenshot-ocr-split-view
    Requirements: 2.1-2.9, 5.1-5.6
    
    最佳实践:
    - QScrollArea + QLabel 实现图片显示
    - Ctrl+滚轮缩放，锚定到鼠标位置
    - 缓存预缩放 Pixmap 优化性能
    - 设置缩放范围限制 (0.1x - 5.0x)
    """
    
    # 信号
    edit_requested = Signal()  # 请求编辑标注
    copy_requested = Signal()  # 请求复制图片
    save_requested = Signal()  # 请求保存图片
    
    # 缩放范围
    MIN_ZOOM = 0.1
    MAX_ZOOM = 5.0
    ZOOM_STEP = 0.15  # 每次缩放 15%
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化预览面板
        
        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self._zoom_level = 1.0
        self._original_image: Optional[QImage] = None
        self._annotations: List[Any] = []
        self._cached_pixmap: Optional[QPixmap] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI
        
        布局:
        - 顶部工具栏: 缩放控制、编辑、复制、保存按钮
        - 中间: QScrollArea 包含 QLabel 显示图片
        - 底部: 缩放级别显示
        
        Requirements: 2.1, 2.3, 5.1-5.6
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 设置面板背景
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface']};
                font-family: {FONT};
            }}
        """)
        
        # 工具栏
        self._toolbar = self._create_toolbar()
        layout.addWidget(self._toolbar)
        
        # 图片显示区域
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(False)  # 手动控制大小
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLORS['bg']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['text_muted']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                height: 0;
                background: none;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {COLORS['border']};
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {COLORS['text_muted']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                width: 0;
                background: none;
            }}
        """)
        
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(f"background-color: {COLORS['bg']};")
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._scroll_area.setWidget(self._image_label)
        
        layout.addWidget(self._scroll_area, 1)
        
        # 状态栏
        self._status_bar = self._create_status_bar()
        layout.addWidget(self._status_bar)
    
    def _create_toolbar(self) -> QWidget:
        """创建工具栏
        
        包含: 缩放控制、编辑、复制、保存按钮
        
        Requirements: 2.5, 2.8, 2.9, 5.1-5.6
        
        Returns:
            工具栏 Widget
        """
        toolbar = QWidget()
        toolbar.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 缩放控制组
        zoom_group = QHBoxLayout()
        zoom_group.setSpacing(4)
        
        # 缩小按钮
        self._zoom_out_btn = self._create_tool_button("−", "缩小 (Ctrl+滚轮向下)")
        self._zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_group.addWidget(self._zoom_out_btn)
        
        # 缩放级别显示（工具栏内）
        self._zoom_label_toolbar = QLabel("100%")
        self._zoom_label_toolbar.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-size: 12px;
                min-width: 45px;
                padding: 0 4px;
            }}
        """)
        self._zoom_label_toolbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_group.addWidget(self._zoom_label_toolbar)
        
        # 放大按钮
        self._zoom_in_btn = self._create_tool_button("+", "放大 (Ctrl+滚轮向上)")
        self._zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_group.addWidget(self._zoom_in_btn)
        
        # 重置缩放按钮
        self._zoom_reset_btn = self._create_tool_button("1:1", "重置缩放")
        self._zoom_reset_btn.clicked.connect(self.zoom_reset)
        zoom_group.addWidget(self._zoom_reset_btn)
        
        # 适应窗口按钮
        self._zoom_fit_btn = self._create_tool_button("适应", "适应窗口大小")
        self._zoom_fit_btn.clicked.connect(self.zoom_fit)
        zoom_group.addWidget(self._zoom_fit_btn)
        
        layout.addLayout(zoom_group)
        
        # 分隔符
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"background-color: {COLORS['border']};")
        separator.setFixedWidth(1)
        layout.addWidget(separator)
        
        # 编辑按钮 (Requirement 2.5)
        self._edit_btn = self._create_tool_button("编辑", "编辑标注")
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        layout.addWidget(self._edit_btn)
        
        layout.addStretch()
        
        # 复制按钮 (Requirement 2.8)
        self._copy_btn = self._create_tool_button("复制", "复制图片到剪贴板")
        self._copy_btn.setStyleSheet(self._get_primary_button_style())
        self._copy_btn.clicked.connect(self._on_copy_clicked)
        layout.addWidget(self._copy_btn)
        
        # 保存按钮 (Requirement 2.9)
        self._save_btn = self._create_tool_button("保存", "保存图片到文件")
        self._save_btn.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._save_btn)
        
        return toolbar
    
    def _create_status_bar(self) -> QWidget:
        """创建状态栏
        
        显示缩放级别和图片信息
        
        Requirements: 2.3, 5.5, 5.6
        
        Returns:
            状态栏 Widget
        """
        status_bar = QWidget()
        status_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(16)
        
        # 缩放级别
        self._zoom_status_label = QLabel("缩放: 100%")
        self._zoom_status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self._zoom_status_label)
        
        # 图片尺寸
        self._size_label = QLabel("")
        self._size_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_muted']};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self._size_label)
        
        layout.addStretch()
        
        # 提示文字
        self._hint_label = QLabel("Ctrl+滚轮缩放")
        self._hint_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_muted']};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self._hint_label)
        
        return status_bar
    
    def _create_tool_button(self, text: str, tooltip: str) -> QToolButton:
        """创建工具按钮
        
        Args:
            text: 按钮文字
            tooltip: 提示文字
            
        Returns:
            QToolButton 实例
        """
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._get_tool_button_style())
        return btn
    
    def _get_tool_button_style(self) -> str:
        """获取工具按钮样式
        
        Returns:
            样式字符串
        """
        return f"""
            QToolButton {{
                background-color: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: {COLORS['text_secondary']};
            }}
            QToolButton:hover {{
                background-color: {COLORS['primary_light']};
                border-color: {COLORS['primary']};
                color: {COLORS['primary']};
            }}
            QToolButton:pressed {{
                background-color: #DBEAFE;
            }}
            QToolButton:disabled {{
                background-color: #F1F5F9;
                color: {COLORS['text_muted']};
                border-color: {COLORS['border']};
            }}
        """
    
    def _get_primary_button_style(self) -> str:
        """获取主要按钮样式
        
        Returns:
            样式字符串
        """
        return f"""
            QToolButton {{
                background-color: {COLORS['primary']};
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
                color: white;
            }}
            QToolButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QToolButton:pressed {{
                background-color: #1D4ED8;
            }}
            QToolButton:disabled {{
                background-color: #94A3B8;
            }}
        """
    
    # =====================================================
    # 公共接口方法
    # =====================================================
    
    def set_image(self, image: QImage, annotations: List[Any] = None):
        """设置要显示的图片
        
        Args:
            image: 要显示的图片
            annotations: 标注列表
            
        Requirements: 2.1, 2.4
        """
        self._original_image = image.copy() if image and not image.isNull() else None
        self._annotations = annotations or []
        self._zoom_level = 1.0
        self._cached_pixmap = None
        self._update_display()
        self._update_zoom_label()
        self._update_size_label()
    
    def get_rendered_image(self) -> Optional[QImage]:
        """获取渲染后的图像（包含标注）
        
        Returns:
            渲染后的 QImage，如果没有图片则返回 None
            
        Requirements: 2.4
        """
        if self._original_image is None:
            return None
        pixmap = self._render_with_annotations()
        return pixmap.toImage()
    
    def get_zoom_level(self) -> float:
        """获取当前缩放级别
        
        Returns:
            当前缩放级别 (0.1 - 5.0)
        """
        return self._zoom_level
    
    def zoom_in(self):
        """放大
        
        Requirements: 2.2
        """
        self._scale_image(1.0 + self.ZOOM_STEP)
    
    def zoom_out(self):
        """缩小
        
        Requirements: 2.2
        """
        self._scale_image(1.0 - self.ZOOM_STEP)
    
    def zoom_reset(self):
        """重置缩放到 100%
        
        Requirements: 2.2
        """
        self._zoom_level = 1.0
        self._update_display()
        self._update_zoom_label()
    
    def zoom_fit(self):
        """适应窗口大小
        
        Requirements: 2.1
        """
        if self._original_image is None:
            return
        
        # 计算适应窗口的缩放级别
        view_size = self._scroll_area.viewport().size()
        img_size = self._original_image.size()
        
        if img_size.width() == 0 or img_size.height() == 0:
            return
        
        # 留出边距
        margin = 20
        available_width = view_size.width() - margin * 2
        available_height = view_size.height() - margin * 2
        
        scale_x = available_width / img_size.width()
        scale_y = available_height / img_size.height()
        
        # 取较小的缩放比例以确保图片完全可见
        self._zoom_level = min(scale_x, scale_y)
        self._zoom_level = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom_level))
        
        self._update_display()
        self._update_zoom_label()
    
    def has_image(self) -> bool:
        """检查是否有图片
        
        Returns:
            True 如果有图片
        """
        return self._original_image is not None and not self._original_image.isNull()
    
    def clear(self):
        """清空面板内容"""
        self._original_image = None
        self._annotations = []
        self._zoom_level = 1.0
        self._cached_pixmap = None
        self._image_label.clear()
        self._image_label.setText("暂无截图")
        self._image_label.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg']};
                color: {COLORS['text_muted']};
                font-size: 14px;
            }}
        """)
        self._update_zoom_label()
        self._update_size_label()
    
    # =====================================================
    # 事件处理
    # =====================================================
    
    def wheelEvent(self, event: QWheelEvent):
        """滚轮事件处理
        
        最佳实践: Ctrl+滚轮缩放，普通滚轮滚动
        
        Requirements: 2.2
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # 缩放
            factor = 1.0 + self.ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 - self.ZOOM_STEP
            self._scale_image(factor, event.position())
            event.accept()
        else:
            # 默认滚动
            super().wheelEvent(event)
    
    # =====================================================
    # 内部方法
    # =====================================================
    
    def _scale_image(self, factor: float, anchor_point: QPointF = None):
        """缩放图片
        
        最佳实践: 锚定到鼠标位置，调整滚动条保持焦点
        
        Args:
            factor: 缩放因子
            anchor_point: 锚定点（鼠标位置）
            
        Requirements: 2.2
        """
        new_zoom = self._zoom_level * factor
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, new_zoom))
        
        if new_zoom == self._zoom_level:
            return
        
        old_zoom = self._zoom_level
        self._zoom_level = new_zoom
        self._update_display()
        
        # 调整滚动条保持焦点
        if anchor_point:
            self._adjust_scrollbars(factor)
        
        self._update_zoom_label()
    
    def _adjust_scrollbars(self, factor: float):
        """调整滚动条保持焦点
        
        最佳实践: 缩放后调整滚动条位置
        
        Args:
            factor: 缩放因子
        """
        h_bar = self._scroll_area.horizontalScrollBar()
        v_bar = self._scroll_area.verticalScrollBar()
        
        h_bar.setValue(int(factor * h_bar.value() + ((factor - 1) * h_bar.pageStep() / 2)))
        v_bar.setValue(int(factor * v_bar.value() + ((factor - 1) * v_bar.pageStep() / 2)))
    
    def _update_display(self):
        """更新显示
        
        渲染图片和标注，应用缩放
        
        Requirements: 2.1, 2.4
        """
        if self._original_image is None or self._original_image.isNull():
            self._image_label.clear()
            self._image_label.setText("暂无截图")
            self._image_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {COLORS['bg']};
                    color: {COLORS['text_muted']};
                    font-size: 14px;
                }}
            """)
            return
        
        # 渲染带标注的图片
        rendered = self._render_with_annotations()
        
        # 应用缩放
        scaled_width = int(rendered.width() * self._zoom_level)
        scaled_height = int(rendered.height() * self._zoom_level)
        
        scaled = rendered.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self._image_label.setPixmap(scaled)
        self._image_label.resize(scaled.size())
        self._image_label.setStyleSheet(f"background-color: {COLORS['bg']};")
    
    def _render_with_annotations(self) -> QPixmap:
        """渲染带标注的图片
        
        Returns:
            渲染后的 QPixmap
            
        Requirements: 2.4
        """
        if self._cached_pixmap is not None:
            return self._cached_pixmap
        
        if self._original_image is None:
            return QPixmap()
        
        pixmap = QPixmap.fromImage(self._original_image)
        
        if self._annotations:
            # 使用 PaintEngine 渲染标注
            try:
                from screenshot_tool.core.paint_engine import PaintEngine
                painter = QPainter(pixmap)
                PaintEngine.render_annotations(painter, self._annotations)
                painter.end()
            except ImportError:
                # PaintEngine 不可用时跳过标注渲染
                pass
        
        self._cached_pixmap = pixmap
        return pixmap
    
    def _update_zoom_label(self):
        """更新缩放级别显示
        
        Requirements: 2.3
        """
        zoom_percent = int(self._zoom_level * 100)
        self._zoom_label_toolbar.setText(f"{zoom_percent}%")
        self._zoom_status_label.setText(f"缩放: {zoom_percent}%")
    
    def _update_size_label(self):
        """更新图片尺寸显示"""
        if self._original_image is None or self._original_image.isNull():
            self._size_label.setText("")
        else:
            w = self._original_image.width()
            h = self._original_image.height()
            self._size_label.setText(f"{w} × {h}")
    
    def _on_edit_clicked(self):
        """编辑按钮点击
        
        Requirements: 2.5, 2.6
        """
        self.edit_requested.emit()
    
    def _on_copy_clicked(self):
        """复制按钮点击
        
        Requirements: 2.8
        """
        self.copy_requested.emit()
    
    def _on_save_clicked(self):
        """保存按钮点击
        
        Requirements: 2.9
        """
        self.save_requested.emit()
    
    def invalidate_cache(self):
        """使缓存失效
        
        当标注被修改时调用此方法
        
        Requirements: 2.7
        """
        self._cached_pixmap = None
        self._update_display()
