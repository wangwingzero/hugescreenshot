# =====================================================
# =============== 公文格式化对话框 ===============
# =====================================================

"""
公文格式化对话框

显示当前打开的 Word/WPS 文档列表，让用户选择要格式化的文档。
替代原有的"热键 + 鼠标钩子"方案，提供更简单直观的操作方式。

Feature: gongwen-dialog
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem,
    QGroupBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from .styles import DIALOG_STYLE, GROUPBOX_STYLE
from .ui_components import ModernButton


class GongwenDialog(QDialog):
    """公文格式化对话框
    
    显示当前打开的 Word/WPS 文档列表，让用户选择要格式化的文档。
    
    Feature: gongwen-dialog
    """
    
    # 信号：请求格式化指定文档
    format_requested = Signal(str)  # 参数为文档名称
    
    def __init__(self, parent=None):
        """初始化对话框
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self._documents: List = []  # DocumentInfo 列表
        self._setup_ui()
        self._refresh_documents()
    
    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("📋 Word排版")
        self.setMinimumSize(450, 350)
        self.resize(500, 400)
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
        
        # 文档列表区域
        doc_group = QGroupBox("选择要格式化的文档")
        doc_group.setStyleSheet(GROUPBOX_STYLE)
        doc_layout = QVBoxLayout(doc_group)
        doc_layout.setSpacing(8)
        
        # 文档列表
        self._doc_list = QListWidget()
        self._doc_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background: #f5f5f5;
            }
        """)
        self._doc_list.setMinimumHeight(150)
        self._doc_list.itemDoubleClicked.connect(self._on_format_clicked)
        doc_layout.addWidget(self._doc_list)
        
        # 空状态提示（初始隐藏）
        self._empty_label = QLabel("📭 未检测到打开的 Word/WPS 文档\n\n请先打开要格式化的文档")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; padding: 20px;")
        self._empty_label.hide()
        doc_layout.addWidget(self._empty_label)
        
        layout.addWidget(doc_group)
        
        # 提示信息
        hint_label = QLabel("ℹ️ 格式化将应用 GB/T 9704-2012 公文格式标准")
        hint_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint_label)
        
        # 按钮栏
        btn_layout = QHBoxLayout()
        
        # 刷新按钮
        self._refresh_btn = ModernButton("🔄 刷新", ModernButton.SECONDARY)
        self._refresh_btn.clicked.connect(self._refresh_documents)
        btn_layout.addWidget(self._refresh_btn)
        
        btn_layout.addStretch()
        
        # 关闭按钮
        self._close_btn = ModernButton("关闭", ModernButton.SECONDARY)
        self._close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._close_btn)
        
        # 开始格式化按钮
        self._format_btn = ModernButton("🚀 开始格式化", ModernButton.PRIMARY)
        self._format_btn.clicked.connect(self._on_format_clicked)
        btn_layout.addWidget(self._format_btn)
        
        layout.addLayout(btn_layout)
    
    def _refresh_documents(self):
        """刷新文档列表"""
        self._doc_list.clear()
        self._documents.clear()
        
        try:
            from screenshot_tool.services.gongwen_formatter import (
                GongwenFormatter, is_gongwen_formatter_available
            )
            
            if not is_gongwen_formatter_available():
                self._show_empty_state("⚠️ 未安装 pywin32\n\n无法连接 Word/WPS")
                return
            
            formatter = GongwenFormatter()
            self._documents = formatter.get_open_documents()
            
            if not self._documents:
                self._show_empty_state()
                return
            
            # 显示文档列表
            self._empty_label.hide()
            self._doc_list.show()
            self._format_btn.setEnabled(True)
            
            for doc in self._documents:
                # 根据应用类型选择图标
                icon_text = "📄" if doc.app_type == "word" else "📝"
                app_label = "Word" if doc.app_type == "word" else "WPS"
                
                item = QListWidgetItem(f"{icon_text} {doc.name}  ({app_label})")
                item.setData(Qt.ItemDataRole.UserRole, doc.name)
                self._doc_list.addItem(item)
            
            # 默认选中第一个
            if self._doc_list.count() > 0:
                self._doc_list.setCurrentRow(0)
                
        except Exception as e:
            self._show_empty_state(f"⚠️ 获取文档列表失败\n\n{str(e)}")
    
    def _show_empty_state(self, message: str = None):
        """显示空状态
        
        Args:
            message: 自定义消息，None 使用默认消息
        """
        self._doc_list.hide()
        self._empty_label.setText(
            message or "📭 未检测到打开的 Word/WPS 文档\n\n请先打开要格式化的文档"
        )
        self._empty_label.show()
        self._format_btn.setEnabled(False)
    
    def _on_format_clicked(self):
        """开始格式化"""
        current_item = self._doc_list.currentItem()
        if not current_item:
            QMessageBox.warning(
                self,
                "未选择文档",
                "请先选择要格式化的文档"
            )
            return
        
        doc_name = current_item.data(Qt.ItemDataRole.UserRole)
        if not doc_name:
            return
        
        # 发送格式化请求信号
        self.format_requested.emit(doc_name)
        
        # 关闭对话框
        self.accept()
    
    def get_selected_document(self) -> Optional[str]:
        """获取选中的文档名称
        
        Returns:
            文档名称，如果没有选中则返回 None
        """
        current_item = self._doc_list.currentItem()
        if current_item:
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None
