# -*- coding: utf-8 -*-
"""
保存工具栏 - 临时预览模式专用

用于临时预览模式下显示保存、复制、丢弃按钮。
采用 Flat Design 风格，与工作台窗口保持一致。

Feature: workbench-temporary-preview-python
Requirements: 5.1, 5.2

设计规范:
- 配色: Productivity Tool (#3B82F6 Primary)
- 风格: Flat Design + Micro-interactions
- 字体: Segoe UI / Microsoft YaHei UI
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut


# =====================================================
# 颜色和样式常量
# =====================================================

SAVE_TOOLBAR_COLORS = {
    # 基础色
    "background": "#FFFFFF",
    "border": "#E2E8F0",
    
    # 主色（保存按钮）
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "primary_pressed": "#1D4ED8",
    "primary_text": "#FFFFFF",
    
    # 次要色（复制按钮）
    "secondary_bg": "#FFFFFF",
    "secondary_border": "#E2E8F0",
    "secondary_text": "#1E293B",
    "secondary_hover_bg": "#F1F5F9",
    "secondary_hover_border": "#3B82F6",
    "secondary_hover_text": "#3B82F6",
    
    # 危险色（丢弃按钮）
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "danger_pressed": "#B91C1C",
    "danger_text": "#FFFFFF",
    
    # 状态指示器
    "status_bg": "#FEF3C7",
    "status_text": "#D97706",
    "status_border": "#FDE68A",
}

FONT_FAMILY = '"Segoe UI", "Microsoft YaHei UI", system-ui, sans-serif'


# =====================================================
# SaveToolbar 组件
# =====================================================

class SaveToolbar(QWidget):
    """保存工具栏 - 临时预览模式专用
    
    提供保存、复制、丢弃三个操作按钮，以及未保存状态指示器。
    
    Feature: workbench-temporary-preview-python
    Requirements: 5.1, 5.2
    
    Signals:
        save_clicked: 保存按钮点击
        copy_clicked: 复制按钮点击
        discard_clicked: 丢弃按钮点击
    """
    
    # 信号
    save_clicked = Signal()  # 保存按钮点击
    copy_clicked = Signal()  # 复制按钮点击
    discard_clicked = Signal()  # 丢弃按钮点击
    
    def __init__(self, parent: Optional[QWidget] = None):
        """初始化保存工具栏
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._setup_ui()
        self._setup_shortcuts()
    
    def _setup_ui(self) -> None:
        """设置 UI 布局"""
        # 设置工具栏样式
        self.setStyleSheet(f"""
            QWidget#saveToolbar {{
                background-color: {SAVE_TOOLBAR_COLORS['background']};
                border: 1px solid {SAVE_TOOLBAR_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self.setObjectName("saveToolbar")
        
        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 未保存状态指示器
        self._status_indicator = self._create_status_indicator()
        layout.addWidget(self._status_indicator)
        
        # 弹性空间
        layout.addStretch()
        
        # 丢弃按钮（危险操作，放在左侧）
        self._discard_btn = self._create_discard_button()
        layout.addWidget(self._discard_btn)
        
        # 复制按钮（次要操作）
        self._copy_btn = self._create_copy_button()
        layout.addWidget(self._copy_btn)
        
        # 保存按钮（主要操作，放在最右侧）
        self._save_btn = self._create_save_button()
        layout.addWidget(self._save_btn)
    
    def _create_status_indicator(self) -> QFrame:
        """创建未保存状态指示器
        
        Returns:
            状态指示器 Frame
        """
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {SAVE_TOOLBAR_COLORS['status_bg']};
                border: 1px solid {SAVE_TOOLBAR_COLORS['status_border']};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # 图标
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 12px; border: none; background: transparent;")
        layout.addWidget(icon_label)
        
        # 文字
        text_label = QLabel("未保存")
        text_label.setStyleSheet(f"""
            font-family: {FONT_FAMILY};
            font-size: 12px;
            font-weight: 500;
            color: {SAVE_TOOLBAR_COLORS['status_text']};
            border: none;
            background: transparent;
        """)
        layout.addWidget(text_label)
        
        return frame
    
    def _create_save_button(self) -> QPushButton:
        """创建保存按钮（主要操作）
        
        Returns:
            保存按钮
        """
        btn = QPushButton("💾 保存 (Ctrl+S)")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SAVE_TOOLBAR_COLORS['primary']};
                color: {SAVE_TOOLBAR_COLORS['primary_text']};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                font-weight: 600;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {SAVE_TOOLBAR_COLORS['primary_hover']};
            }}
            QPushButton:pressed {{
                background-color: {SAVE_TOOLBAR_COLORS['primary_pressed']};
            }}
            QPushButton:disabled {{
                background-color: #CBD5E1;
                color: #94A3B8;
            }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("保存截图到历史记录 (Ctrl+S)")
        btn.clicked.connect(self.save_clicked.emit)
        return btn
    
    def _create_copy_button(self) -> QPushButton:
        """创建复制按钮（次要操作）
        
        Returns:
            复制按钮
        """
        btn = QPushButton("📋 复制 (Ctrl+C)")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SAVE_TOOLBAR_COLORS['secondary_bg']};
                color: {SAVE_TOOLBAR_COLORS['secondary_text']};
                border: 1px solid {SAVE_TOOLBAR_COLORS['secondary_border']};
                border-radius: 6px;
                padding: 8px 16px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                font-weight: 500;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {SAVE_TOOLBAR_COLORS['secondary_hover_bg']};
                border-color: {SAVE_TOOLBAR_COLORS['secondary_hover_border']};
                color: {SAVE_TOOLBAR_COLORS['secondary_hover_text']};
            }}
            QPushButton:pressed {{
                background-color: #E2E8F0;
            }}
            QPushButton:disabled {{
                background-color: #F1F5F9;
                color: #94A3B8;
                border-color: #E2E8F0;
            }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("复制截图到剪贴板 (Ctrl+C)")
        btn.clicked.connect(self.copy_clicked.emit)
        return btn
    
    def _create_discard_button(self) -> QPushButton:
        """创建丢弃按钮（危险操作）
        
        Returns:
            丢弃按钮
        """
        btn = QPushButton("🗑️ 丢弃 (Esc)")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SAVE_TOOLBAR_COLORS['danger']};
                color: {SAVE_TOOLBAR_COLORS['danger_text']};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                font-weight: 500;
                min-width: 90px;
            }}
            QPushButton:hover {{
                background-color: {SAVE_TOOLBAR_COLORS['danger_hover']};
            }}
            QPushButton:pressed {{
                background-color: {SAVE_TOOLBAR_COLORS['danger_pressed']};
            }}
            QPushButton:disabled {{
                background-color: #FCA5A5;
                color: #FECACA;
            }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("丢弃截图，不保存 (Esc)")
        btn.clicked.connect(self.discard_clicked.emit)
        return btn
    
    def _setup_shortcuts(self) -> None:
        """设置键盘快捷键"""
        # Ctrl+S 保存
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._on_save_shortcut)
        
        # Ctrl+C 复制
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        copy_shortcut.activated.connect(self._on_copy_shortcut)
        
        # Escape 丢弃
        discard_shortcut = QShortcut(QKeySequence("Escape"), self)
        discard_shortcut.activated.connect(self._on_discard_shortcut)
    
    def _on_save_shortcut(self) -> None:
        """保存快捷键处理"""
        if self.isVisible() and self._save_btn.isEnabled():
            self.save_clicked.emit()
    
    def _on_copy_shortcut(self) -> None:
        """复制快捷键处理"""
        if self.isVisible() and self._copy_btn.isEnabled():
            self.copy_clicked.emit()
    
    def _on_discard_shortcut(self) -> None:
        """丢弃快捷键处理"""
        if self.isVisible() and self._discard_btn.isEnabled():
            self.discard_clicked.emit()
    
    # =====================================================
    # 公共方法
    # =====================================================
    
    def set_visible(self, visible: bool) -> None:
        """设置可见性
        
        Args:
            visible: 是否可见
        """
        self.setVisible(visible)
    
    def set_save_enabled(self, enabled: bool) -> None:
        """设置保存按钮启用状态
        
        Args:
            enabled: 是否启用
        """
        self._save_btn.setEnabled(enabled)
    
    def set_copy_enabled(self, enabled: bool) -> None:
        """设置复制按钮启用状态
        
        Args:
            enabled: 是否启用
        """
        self._copy_btn.setEnabled(enabled)
    
    def set_discard_enabled(self, enabled: bool) -> None:
        """设置丢弃按钮启用状态
        
        Args:
            enabled: 是否启用
        """
        self._discard_btn.setEnabled(enabled)
    
    def set_status_text(self, text: str) -> None:
        """设置状态指示器文字
        
        Args:
            text: 状态文字
        """
        # 查找状态指示器中的文字标签
        layout = self._status_indicator.layout()
        if layout and layout.count() >= 2:
            text_label = layout.itemAt(1).widget()
            if isinstance(text_label, QLabel):
                text_label.setText(text)
    
    def get_save_button(self) -> QPushButton:
        """获取保存按钮（用于测试）
        
        Returns:
            保存按钮
        """
        return self._save_btn
    
    def get_copy_button(self) -> QPushButton:
        """获取复制按钮（用于测试）
        
        Returns:
            复制按钮
        """
        return self._copy_btn
    
    def get_discard_button(self) -> QPushButton:
        """获取丢弃按钮（用于测试）
        
        Returns:
            丢弃按钮
        """
        return self._discard_btn
