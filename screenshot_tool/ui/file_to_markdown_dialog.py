# =====================================================
# =============== 文件转 Markdown 对话框 ===============
# =====================================================

"""
文件转 Markdown 对话框

用于选择文件和保存目录的对话框。

Feature: file-to-markdown
"""

import os
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox,
    QMessageBox, QLineEdit, QFileDialog,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal

from .styles import DIALOG_STYLE, GROUPBOX_STYLE, INPUT_STYLE
from .ui_components import ModernButton
from ..core.config_manager import MinerUConfig


class FileToMarkdownDialog(QDialog):
    """文件转 Markdown 对话框
    
    用于选择文件和保存目录。
    
    Feature: file-to-markdown
    """
    
    # 信号：请求转换文件列表，参数为 (file_paths, save_dir)
    conversion_requested = Signal(list, str)  # List[str], str
    
    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = ('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.png', '.jpg', '.jpeg', '.html')
    
    def __init__(self, config: MinerUConfig, parent=None):
        """初始化对话框
        
        Args:
            config: MinerU 配置
            parent: 父窗口
        """
        super().__init__(parent)
        self._config = config
        self._file_paths: List[str] = []
        self._setup_ui()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("📄 文件转 Markdown")
        self.setMinimumSize(550, 450)
        self.resize(600, 500)
        self.setStyleSheet(DIALOG_STYLE)
        
        # 允许调整大小
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinMaxButtonsHint
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # 文件选择区域
        file_group = QGroupBox("选择文件")
        file_group.setStyleSheet(GROUPBOX_STYLE)
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(8)
        
        # 文件列表
        self._file_list = QListWidget()
        self._file_list.setStyleSheet(INPUT_STYLE + """
            QListWidget {
                min-height: 150px;
            }
        """)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        file_layout.addWidget(self._file_list)
        
        # 文件操作按钮
        file_btn_layout = QHBoxLayout()
        
        self._add_files_btn = QPushButton("添加文件...")
        self._add_files_btn.setStyleSheet(INPUT_STYLE)
        self._add_files_btn.clicked.connect(self._add_files)
        file_btn_layout.addWidget(self._add_files_btn)
        
        self._add_folder_btn = QPushButton("添加文件夹...")
        self._add_folder_btn.setStyleSheet(INPUT_STYLE)
        self._add_folder_btn.clicked.connect(self._add_folder)
        file_btn_layout.addWidget(self._add_folder_btn)
        
        self._remove_btn = QPushButton("移除选中")
        self._remove_btn.setStyleSheet(INPUT_STYLE)
        self._remove_btn.clicked.connect(self._remove_selected)
        file_btn_layout.addWidget(self._remove_btn)
        
        file_btn_layout.addStretch()
        file_layout.addLayout(file_btn_layout)
        
        # 文件计数
        self._count_label = QLabel("已选择 0 个文件")
        self._count_label.setStyleSheet("color: #666;")
        file_layout.addWidget(self._count_label)
        
        layout.addWidget(file_group)
        
        # 保存路径区域
        save_group = QGroupBox("保存位置")
        save_group.setStyleSheet(GROUPBOX_STYLE)
        save_layout = QHBoxLayout(save_group)
        save_layout.setSpacing(8)
        
        # 保存路径输入框
        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.setStyleSheet(INPUT_STYLE)
        self._save_dir_edit.setPlaceholderText("选择保存文件夹（默认保存到源文件目录）...")
        # 使用配置中的保存目录
        if self._config.save_dir:
            self._save_dir_edit.setText(self._config.save_dir)
        save_layout.addWidget(self._save_dir_edit)
        
        # 浏览按钮
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setStyleSheet(INPUT_STYLE)
        self._browse_btn.clicked.connect(self._browse_save_dir)
        save_layout.addWidget(self._browse_btn)
        
        layout.addWidget(save_group)
        
        # 提示信息
        hint_label = QLabel(
            "支持格式：PDF、Word(.doc/.docx)、PPT(.ppt/.pptx)、图片(.png/.jpg/.jpeg)、HTML\n"
            "如果不选择保存位置，将保存到源文件所在目录"
        )
        hint_label.setStyleSheet("color: #888; font-size: 12px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # 关闭按钮
        self._close_btn = ModernButton("关闭", ModernButton.SECONDARY)
        self._close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._close_btn)
        
        # 开始转换按钮
        self._start_btn = ModernButton("🚀 开始转换", ModernButton.PRIMARY)
        self._start_btn.clicked.connect(self._on_start_conversion)
        btn_layout.addWidget(self._start_btn)
        
        layout.addLayout(btn_layout)
    
    def _add_files(self):
        """添加文件"""
        initial_dir = self._config.last_pdf_dir if self._config.last_pdf_dir else ""
        
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择文件",
            initial_dir,
            "支持的文件 (*.pdf *.doc *.docx *.ppt *.pptx *.png *.jpg *.jpeg *.html);;"
            "PDF 文件 (*.pdf);;Word 文件 (*.doc *.docx);;PPT 文件 (*.ppt *.pptx);;"
            "图片文件 (*.png *.jpg *.jpeg);;HTML 文件 (*.html);;所有文件 (*.*)"
        )
        
        if files:
            # 更新上次打开的目录
            self._config.last_pdf_dir = os.path.dirname(files[0])
            
            for file_path in files:
                if file_path not in self._file_paths:
                    self._file_paths.append(file_path)
                    item = QListWidgetItem(os.path.basename(file_path))
                    item.setToolTip(file_path)
                    self._file_list.addItem(item)
            
            self._update_count()
    
    def _add_folder(self):
        """添加文件夹中的所有支持文件"""
        initial_dir = self._config.last_pdf_dir if self._config.last_pdf_dir else ""
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择包含文件的文件夹",
            initial_dir
        )
        
        if folder:
            # 更新上次打开的目录
            self._config.last_pdf_dir = folder
            
            added_count = 0
            for filename in os.listdir(folder):
                if filename.lower().endswith(self.SUPPORTED_EXTENSIONS):
                    file_path = os.path.join(folder, filename)
                    if file_path not in self._file_paths:
                        self._file_paths.append(file_path)
                        item = QListWidgetItem(filename)
                        item.setToolTip(file_path)
                        self._file_list.addItem(item)
                        added_count += 1
            
            if added_count == 0:
                QMessageBox.information(
                    self,
                    "未找到文件",
                    f"文件夹中没有找到支持的文件：\n{folder}\n\n"
                    f"支持格式：PDF、Word、PPT、图片、HTML"
                )
            
            self._update_count()
    
    def _remove_selected(self):
        """移除选中的文件"""
        selected_items = self._file_list.selectedItems()
        
        # 获取选中项的行号，从大到小排序以避免索引变化问题
        rows_to_remove = sorted(
            [self._file_list.row(item) for item in selected_items],
            reverse=True
        )
        
        for row in rows_to_remove:
            self._file_list.takeItem(row)
            if row < len(self._file_paths):
                self._file_paths.pop(row)
        
        self._update_count()
    
    def _update_count(self):
        """更新文件计数"""
        count = len(self._file_paths)
        self._count_label.setText(f"已选择 {count} 个文件")
    
    def _browse_save_dir(self):
        """浏览选择保存目录"""
        current_dir = self._save_dir_edit.text().strip()
        if not current_dir:
            current_dir = self._config.last_pdf_dir or ""
        
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择保存文件夹",
            current_dir
        )
        
        if dir_path:
            self._save_dir_edit.setText(dir_path)
    
    def _on_start_conversion(self):
        """开始转换"""
        if not self._file_paths:
            QMessageBox.warning(
                self,
                "未选择文件",
                "请先添加要转换的文件"
            )
            return
        
        # 获取保存目录
        save_dir = self._save_dir_edit.text().strip()
        
        # 更新配置中的保存目录（记住用户选择）
        self._config.save_dir = save_dir
        
        # 发送转换请求信号
        self.conversion_requested.emit(self._file_paths.copy(), save_dir)
        
        # 关闭对话框
        self.accept()
