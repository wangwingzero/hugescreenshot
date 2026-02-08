# -*- coding: utf-8 -*-
"""
截图+OCR 分屏视图窗口 - Flat Design 风格

基于 UI/UX Pro Max 设计规范:
- 配色: Productivity Tool (#3B82F6 Primary, #F8FAFC Background)
- 风格: Flat Design + Micro-interactions
- 字体: Segoe UI / Microsoft YaHei UI

Feature: screenshot-ocr-split-view
Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 2.5-2.9, 3.1-3.11, 6.4, 6.5, 6.6

最佳实践:
- QSplitter.setOpaqueResize(False) 优化拖动性能
- saveGeometry()/restoreGeometry() 持久化窗口位置
- QSplitter.saveState()/restoreState() 持久化分隔条位置
- QShortcut 实现 ESC 关闭
"""

from typing import Optional, List, Any, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QApplication, QFileDialog,
    QToolButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal, QByteArray
from PySide6.QtGui import QImage, QClipboard, QKeySequence, QShortcut, QScreen

# 导入面板组件
from screenshot_tool.ui.screenshot_preview_panel import ScreenshotPreviewPanel
from screenshot_tool.ui.ocr_preview_panel import OCRPreviewPanel

if TYPE_CHECKING:
    from screenshot_tool.services.ocr_manager import OCRManager


# UI/UX Pro Max 配色 (Productivity Tool)
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


# 窗口样式表
WINDOW_STYLESHEET = f"""
QWidget {{
    font-family: {FONT};
    color: {COLORS["text"]};
}}
QWidget#splitWindow {{
    background-color: {COLORS["bg"]};
}}
QSplitter {{
    background-color: {COLORS["bg"]};
}}
QSplitter::handle {{
    background-color: {COLORS["border"]};
    width: 1px;
}}
QSplitter::handle:hover {{
    background-color: {COLORS["primary"]};
}}
"""


class ScreenshotOCRSplitWindow(QWidget):
    """截图+OCR 分屏视图窗口
    
    Feature: screenshot-ocr-split-view
    Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 6.4, 6.5, 6.6
    
    最佳实践:
    - QSplitter.setOpaqueResize(False) 优化拖动性能
    - saveGeometry()/restoreGeometry() 持久化窗口位置
    - QSplitter.saveState()/restoreState() 持久化分隔条位置
    - QShortcut 实现 ESC 关闭
    
    Attributes:
        closed: 窗口关闭信号
        escape_pressed: ESC 按键信号
        save_requested: 保存请求信号 (image, file_path)
        pinned_changed: 置顶状态变化信号 (is_pinned)
    """
    
    # 信号
    closed = Signal()
    escape_pressed = Signal()
    save_requested = Signal(QImage, str)  # image, file_path
    pinned_changed = Signal(bool)  # is_pinned
    
    # 剪贴板历史集成信号
    # Feature: screenshot-ocr-split-view
    # Requirements: 7.4, 7.5
    image_copied = Signal(QImage)  # 图片复制到剪贴板时发射
    image_saved = Signal(QImage, str)  # 图片保存到文件时发射 (image, file_path)
    
    # 窗口最小尺寸（紧凑模式）
    MIN_WIDTH = 480
    MIN_HEIGHT = 360
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化分屏窗口
        
        设置窗口标志、最小尺寸、创建 QSplitter 布局。
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        
        # 内部状态
        # 默认置顶 (Requirement 6.4)
        self._is_pinned: bool = True
        self._screenshot: Optional[QImage] = None
        self._annotations: list = []
        
        # 首次显示标志，用于在 showEvent 中恢复 splitter 状态
        self._first_show: bool = True
        
        # 设置窗口
        self._setup_window_flags()
        self._setup_ui()
        self._setup_shortcuts()
        
        # 应用样式
        self.setStyleSheet(WINDOW_STYLESHEET)
        
        # 恢复窗口状态（在 show() 之前调用）
        # Requirements: 1.4, 6.7
        self._restore_state()
    
    def _setup_window_flags(self) -> None:
        """设置窗口标志
        
        Requirements: 1.5 (最小尺寸), 6.4 (置顶)
        
        窗口标志:
        - Window: 独立窗口
        - WindowStaysOnTopHint: 默认置顶
        - WindowCloseButtonHint: 显示关闭按钮
        - WindowMinMaxButtonsHint: 显示最小化/最大化按钮
        """
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        # 设置窗口标题
        self.setWindowTitle("截图 + OCR")
        
        # 设置最小尺寸 (Requirements: 1.5)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        
        # 设置对象名称用于样式
        self.setObjectName("splitWindow")
    
    def _setup_ui(self) -> None:
        """设置 UI 布局
        
        Requirements: 1.1, 1.2, 1.3, 1.6, 2.5-2.9, 3.1-3.11, 6.5
        
        使用 QSplitter 创建左右分栏:
        - 顶部: 窗口工具栏（置顶按钮）
        - 左侧: ScreenshotPreviewPanel
        - 右侧: OCRPreviewPanel
        
        最佳实践:
        - setOpaqueResize(False): 拖动时不实时重绘，只在释放时更新
        - setChildrenCollapsible(False): 防止面板被完全折叠
        - setStretchFactor(): 定义窗口调整时的空间分配
        """
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建窗口工具栏 (Requirements: 6.5)
        self._window_toolbar = self._create_window_toolbar()
        layout.addWidget(self._window_toolbar)
        
        # 创建分隔器 (Requirements: 1.3)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 性能优化: 拖动时不实时重绘 (最佳实践)
        self._splitter.setOpaqueResize(False)
        
        # 防止面板被完全折叠
        self._splitter.setChildrenCollapsible(False)
        
        # 设置分隔条宽度
        self._splitter.setHandleWidth(1)
        
        # 创建截图预览面板 (左侧) - Requirements: 2.5-2.9
        self._preview_panel = ScreenshotPreviewPanel()
        self._preview_panel.setMinimumWidth(200)
        
        # 创建 OCR 结果面板 (右侧) - Requirements: 3.1-3.11
        self._ocr_panel = OCRPreviewPanel()
        self._ocr_panel.setMinimumWidth(200)
        
        # 添加到分隔器
        self._splitter.addWidget(self._preview_panel)
        self._splitter.addWidget(self._ocr_panel)
        
        # 设置伸缩因子 (Requirements: 1.2, 1.6)
        # 两侧面板等比例伸缩，实现 50% 分割
        self._splitter.setStretchFactor(0, 1)  # 左侧面板可伸缩
        self._splitter.setStretchFactor(1, 1)  # 右侧面板可伸缩
        
        # 添加到主布局
        layout.addWidget(self._splitter)
        
        # 连接面板信号
        self._connect_panel_signals()
    
    def _create_window_toolbar(self) -> QWidget:
        """创建窗口工具栏
        
        Requirements: 6.5
        
        包含置顶按钮，用于切换窗口置顶状态。
        
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
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        
        # 窗口标题
        title_label = QLabel("截图 + OCR")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text']};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # 置顶按钮 (Requirement 6.5)
        self._pin_btn = QToolButton()
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(True)  # 默认置顶
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_pin_button_state()
        self._pin_btn.clicked.connect(self._on_pin_clicked)
        layout.addWidget(self._pin_btn)
        
        return toolbar
    
    def _update_pin_button_state(self) -> None:
        """更新置顶按钮状态
        
        Requirements: 6.5
        
        根据当前置顶状态更新按钮的文字、提示和样式。
        """
        if self._is_pinned:
            self._pin_btn.setText("📌 已置顶")
            self._pin_btn.setToolTip("点击取消置顶")
            self._pin_btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: {COLORS['primary']};
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 12px;
                    color: white;
                }}
                QToolButton:hover {{
                    background-color: {COLORS['primary_hover']};
                }}
                QToolButton:pressed {{
                    background-color: #1D4ED8;
                }}
            """)
        else:
            self._pin_btn.setText("📌 置顶")
            self._pin_btn.setToolTip("点击置顶窗口")
            self._pin_btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                    padding: 4px 12px;
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
            """)
    
    def _on_pin_clicked(self) -> None:
        """处理置顶按钮点击
        
        Requirements: 6.5
        
        切换窗口置顶状态。
        """
        self.set_pinned(not self._is_pinned)
    
    @property
    def splitter(self) -> QSplitter:
        """获取分隔器
        
        Returns:
            QSplitter 实例
        """
        return self._splitter
    
    @property
    def is_pinned(self) -> bool:
        """获取置顶状态
        
        Returns:
            是否置顶
        """
        return self._is_pinned
    
    def set_pinned(self, pinned: bool) -> None:
        """设置置顶状态
        
        Requirements: 6.4, 6.5, 6.6
        
        Args:
            pinned: 是否置顶
        """
        if self._is_pinned == pinned:
            return
        
        self._is_pinned = pinned
        
        # 更新窗口标志
        flags = self.windowFlags()
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        
        # 需要重新设置标志并显示
        self.setWindowFlags(flags)
        self.show()
        
        # 更新按钮状态
        if hasattr(self, '_pin_btn'):
            self._pin_btn.setChecked(pinned)
            self._update_pin_button_state()
        
        # 发出信号
        self.pinned_changed.emit(pinned)
    
    def _connect_panel_signals(self) -> None:
        """连接面板信号
        
        Requirements: 2.5-2.9, 3.1-3.11
        
        连接截图预览面板和 OCR 面板的信号到相应的处理方法。
        """
        # 截图预览面板信号 (Requirements: 2.5, 2.8, 2.9)
        self._preview_panel.edit_requested.connect(self._on_edit_requested)
        self._preview_panel.copy_requested.connect(self._on_copy_image_requested)
        self._preview_panel.save_requested.connect(self._on_save_image_requested)
        
        # OCR 面板信号
        # back_to_image_requested 在分屏视图中不需要处理（两个面板同时可见）
        # 但可以用于切换焦点到图片面板
        self._ocr_panel.back_to_image_requested.connect(self._on_back_to_image)
    
    def _setup_shortcuts(self) -> None:
        """设置快捷键
        
        Requirements: 6.1, 6.2, 6.3
        
        最佳实践: 使用 QShortcut 实现独立快捷键
        - ESC: 关闭窗口
        - Ctrl+C: 复制（根据焦点决定复制图片还是文本）
        - Ctrl+S: 保存截图
        """
        # ESC 关闭窗口 (Requirement 6.1)
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.activated.connect(self._on_escape_pressed)
        
        # Ctrl+S 保存 (Requirement 6.3)
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.activated.connect(self._on_save)
        
        # Ctrl+C 复制 (Requirement 6.2)
        # 根据焦点决定复制图片还是文本
        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.activated.connect(self._on_copy)
    
    def _on_escape_pressed(self) -> None:
        """处理 ESC 按键
        
        Requirements: 6.1
        
        关闭窗口并发出 escape_pressed 信号。
        """
        self.escape_pressed.emit()
        self.close()
    
    def _on_copy(self) -> None:
        """处理 Ctrl+C 复制快捷键
        
        Requirements: 6.2
        
        根据焦点决定复制图片还是文本:
        - 如果 OCR 面板的文本编辑器有焦点 → 复制文本
        - 否则 → 复制图片
        """
        # 检查 OCR 面板的文本编辑器是否有焦点
        # OCRPreviewPanel 内部有 _text_edit 属性
        ocr_text_edit = getattr(self._ocr_panel, '_text_edit', None)
        
        if ocr_text_edit is not None and ocr_text_edit.hasFocus():
            # OCR 面板有焦点，复制选中的文本或全部文本
            cursor = ocr_text_edit.textCursor()
            if cursor.hasSelection():
                # 有选中文本，复制选中部分
                selected_text = cursor.selectedText()
                clipboard = QApplication.clipboard()
                clipboard.setText(selected_text, QClipboard.Mode.Clipboard)
            else:
                # 没有选中文本，复制全部文本
                text = ocr_text_edit.toPlainText()
                if text:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(text, QClipboard.Mode.Clipboard)
        else:
            # 其他情况，复制图片
            self._on_copy_image_requested()
    
    def _on_save(self) -> None:
        """处理 Ctrl+S 保存快捷键
        
        Requirements: 6.3
        
        保存截图到文件。
        """
        self._on_save_image_requested()
    
    def show_screenshot(self, image: QImage, annotations: List[Any] = None,
                        ocr_manager: "OCRManager" = None,
                        screenshot_region: tuple = None) -> None:
        """显示截图并开始 OCR

        Requirements: 1.1, 2.1, 3.1

        Args:
            image: 截图图像
            annotations: 标注列表
            ocr_manager: OCR 管理器实例
            screenshot_region: 截图区域 (x, y, width, height)，用于智能定位避开截图
        """
        # 保存截图和标注
        self._screenshot = image.copy() if image and not image.isNull() else None
        self._annotations = annotations or []

        # 设置截图预览面板
        self._preview_panel.set_image(image, annotations)

        # 设置 OCR 管理器并开始识别
        if ocr_manager:
            self._ocr_panel.set_ocr_manager(ocr_manager)
            # 使用空字符串作为 item_id（新截图）
            self._ocr_panel.start_ocr(image, "")

        # 智能定位：避开截图区域
        if screenshot_region:
            self._position_avoiding_region(screenshot_region)

        # 显示窗口
        self.show()
        self.activateWindow()
    
    def _on_edit_requested(self) -> None:
        """处理编辑请求
        
        Requirements: 2.5, 2.6
        
        打开标注编辑器编辑当前截图。
        """
        if self._screenshot is None or self._screenshot.isNull():
            return
        
        try:
            from screenshot_tool.core.highlight_editor import HighlightEditor
            
            # 创建编辑器
            editor = HighlightEditor(self._screenshot, self._annotations, parent=self)
            
            # 连接编辑完成信号
            editor.editing_finished.connect(self._on_editing_finished)
            
            # 显示编辑器
            editor.show()
        except ImportError:
            # HighlightEditor 不可用
            pass
    
    def _on_editing_finished(self, image: QImage, annotations: List[Any]) -> None:
        """编辑完成回调
        
        Requirements: 2.7
        
        Args:
            image: 编辑后的图像
            annotations: 更新后的标注列表
        """
        # 更新截图和标注
        self._screenshot = image.copy() if image and not image.isNull() else None
        self._annotations = annotations or []
        
        # 更新预览面板（使缓存失效并重新渲染）
        self._preview_panel.invalidate_cache()
        self._preview_panel.set_image(image, annotations)
    
    def _on_copy_image_requested(self) -> None:
        """处理复制图片请求
        
        Requirements: 2.8, 7.4, 7.5
        
        将截图（包含标注）复制到剪贴板，并发射信号用于剪贴板历史集成。
        
        Feature: screenshot-ocr-split-view
        """
        rendered_image = self._preview_panel.get_rendered_image()
        if rendered_image is None or rendered_image.isNull():
            return
        
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setImage(rendered_image, QClipboard.Mode.Clipboard)
        
        # 发射信号用于剪贴板历史集成
        # Requirements: 7.4, 7.5
        self.image_copied.emit(rendered_image)
    
    def _on_save_image_requested(self) -> None:
        """处理保存图片请求
        
        Requirements: 2.9, 7.4, 7.5
        
        将截图（包含标注）保存到文件，并发射信号用于剪贴板历史集成。
        
        Feature: screenshot-ocr-split-view
        """
        rendered_image = self._preview_panel.get_rendered_image()
        if rendered_image is None or rendered_image.isNull():
            return
        
        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存截图",
            "",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)"
        )
        
        if file_path:
            # 保存图片
            rendered_image.save(file_path)
            
            # 发出保存完成信号（原有信号）
            self.save_requested.emit(rendered_image, file_path)
            
            # 发射信号用于剪贴板历史集成
            # Requirements: 7.4, 7.5
            self.image_saved.emit(rendered_image, file_path)
    
    def _on_back_to_image(self) -> None:
        """处理返回图片请求
        
        在分屏视图中，两个面板同时可见，
        此信号可用于将焦点切换到图片预览面板。
        """
        # 将焦点设置到预览面板
        self._preview_panel.setFocus()
    
    @property
    def preview_panel(self) -> ScreenshotPreviewPanel:
        """获取截图预览面板
        
        Returns:
            ScreenshotPreviewPanel 实例
        """
        return self._preview_panel
    
    @property
    def ocr_panel(self) -> OCRPreviewPanel:
        """获取 OCR 结果面板
        
        Returns:
            OCRPreviewPanel 实例
        """
        return self._ocr_panel
    
    def _save_state(self) -> None:
        """保存窗口状态到 ConfigManager
        
        Requirements: 1.4, 6.7
        
        保存内容:
        - 窗口位置和大小 (geometry)
        - 分隔条位置 (splitter_state)
        - 置顶状态 (is_pinned)
        
        最佳实践: 在 closeEvent 中调用
        """
        try:
            from screenshot_tool.core.config_manager import get_config_manager
            config = get_config_manager()
            
            # 保存窗口几何信息
            config.split_window_state.geometry = bytes(self.saveGeometry())
            
            # 保存分隔条状态
            config.split_window_state.splitter_state = bytes(self._splitter.saveState())
            
            # 保存置顶状态
            config.split_window_state.is_pinned = self._is_pinned
            
            # 持久化到文件
            config.save()
        except Exception:
            # 保存失败不影响窗口关闭
            pass
    
    def _restore_state(self) -> None:
        """从 ConfigManager 恢复窗口状态
        
        Requirements: 1.4, 6.7
        
        恢复内容:
        - 窗口位置和大小 (geometry)
        - 置顶状态 (is_pinned)
        
        注意: splitter 状态在 showEvent 中恢复，
        因为需要等待父容器布局完成。
        
        最佳实践: 在 show() 之前调用
        """
        try:
            from screenshot_tool.core.config_manager import get_config_manager
            config = get_config_manager()
            
            # 恢复窗口几何信息
            if config.split_window_state.geometry:
                self.restoreGeometry(QByteArray(config.split_window_state.geometry))
            else:
                # 首次运行: 设置紧凑默认大小并居中显示
                self.resize(560, 420)
                self._center_on_screen()
            
            # 恢复置顶状态
            self._is_pinned = config.split_window_state.is_pinned
            
            # 更新窗口标志以反映置顶状态
            flags = self.windowFlags()
            if self._is_pinned:
                flags |= Qt.WindowType.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            
            # 更新置顶按钮状态
            if hasattr(self, '_pin_btn'):
                self._pin_btn.setChecked(self._is_pinned)
                self._update_pin_button_state()
        except Exception:
            # 恢复失败使用紧凑默认值
            self.resize(560, 420)
            self._center_on_screen()
    
    def _center_on_screen(self) -> None:
        """将窗口居中显示在主屏幕上

        Requirements: 1.4 (首次运行居中显示)
        """
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())

    def _position_avoiding_region(self, region: tuple) -> None:
        """智能定位窗口，避开截图区域

        优先级顺序：
        1. 截图区域右侧（如果有足够空间）
        2. 截图区域左侧
        3. 截图区域下方
        4. 截图区域上方
        5. 如果都不够，放在显示器角落

        Args:
            region: 截图区域 (x, y, width, height)
        """
        if not region or len(region) != 4:
            return

        sx, sy, sw, sh = region
        padding = 16  # 窗口与截图区域的间距

        # 获取当前屏幕
        screen = QApplication.primaryScreen()
        if not screen:
            return

        screen_geo = screen.availableGeometry()
        mx, my, mw, mh = screen_geo.x(), screen_geo.y(), screen_geo.width(), screen_geo.height()

        # 窗口尺寸
        ww, wh = self.width(), self.height()

        # 计算各方向可用空间
        space_right = (mx + mw) - (sx + sw) - padding
        space_left = sx - mx - padding
        space_bottom = (my + mh) - (sy + sh) - padding
        space_top = sy - my - padding

        # 垂直居中对齐（相对于截图区域）
        vertical_center = max(my, min(sy + (sh - wh) // 2, my + mh - wh))

        # 水平居中对齐（相对于截图区域）
        horizontal_center = max(mx, min(sx + (sw - ww) // 2, mx + mw - ww))

        # 策略 1: 右侧（首选）
        if space_right >= ww:
            self.move(sx + sw + padding, vertical_center)
            return

        # 策略 2: 左侧
        if space_left >= ww:
            self.move(sx - ww - padding, vertical_center)
            return

        # 策略 3: 下方
        if space_bottom >= wh:
            self.move(horizontal_center, sy + sh + padding)
            return

        # 策略 4: 上方
        if space_top >= wh:
            self.move(horizontal_center, sy - wh - padding)
            return

        # 策略 5: 空间不足，放在显示器右下角
        self.move(mx + mw - ww - padding, my + mh - wh - padding)
    
    def showEvent(self, event) -> None:
        """显示事件
        
        Requirements: 1.4, 6.7
        
        在 showEvent 中恢复 splitter 状态，
        确保父容器布局已完成。
        
        最佳实践: splitter 状态需要在父容器布局完成后恢复
        
        Args:
            event: 显示事件
        """
        super().showEvent(event)
        
        # 只在首次显示时恢复 splitter 状态
        if self._first_show:
            self._first_show = False
            
            try:
                from screenshot_tool.core.config_manager import get_config_manager
                config = get_config_manager()
                
                if config.split_window_state.splitter_state:
                    # 恢复保存的分隔条位置
                    self._splitter.restoreState(
                        QByteArray(config.split_window_state.splitter_state)
                    )
                else:
                    # 首次运行: 50% 分割
                    total_width = self._splitter.width()
                    self._splitter.setSizes([total_width // 2, total_width // 2])
            except Exception:
                # 恢复失败使用默认 50% 分割
                total_width = self._splitter.width()
                self._splitter.setSizes([total_width // 2, total_width // 2])
    
    def closeEvent(self, event) -> None:
        """关闭事件
        
        Requirements: 1.4, 6.7
        
        保存窗口状态并发出 closed 信号。
        
        Args:
            event: 关闭事件
        """
        # 保存窗口状态
        self._save_state()
        
        self.closed.emit()
        super().closeEvent(event)
