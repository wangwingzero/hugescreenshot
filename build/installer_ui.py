# -*- coding: utf-8 -*-
"""
虎哥截图 - 现代化安装器 UI

设计风格：Minimal & Direct (浅色系)
配色方案：Trust blue (#2563EB) + Light background (#F8FAFC)
字体：Microsoft YaHei / Segoe UI
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QProgressBar, QCheckBox,
    QFileDialog, QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QIcon


# Logo 图片路径
def get_logo_path() -> Path:
    """获取 Logo 图片路径"""
    if getattr(sys, 'frozen', False):
        # 打包后 - 文件在 _MEIPASS 根目录
        return Path(sys._MEIPASS) / "虎哥截图.png"
    else:
        # 开发模式
        return Path(__file__).parent.parent / "resources" / "PNG" / "虎哥截图.png"


def get_icon_path() -> Path:
    """获取图标路径"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "虎哥截图.ico"
    else:
        return Path(__file__).parent.parent / "resources" / "PNG" / "虎哥截图.ico"


# =====================================================
# 配色方案 - Light Mode (Productivity Tool)
# 来源: UI/UX Pro Max - colors.csv
# =====================================================
COLORS = {
    # 背景色
    "background": "#F8FAFC",        # 主背景
    "surface": "#FFFFFF",           # 卡片/表面
    "surface_hover": "#F1F5F9",     # 悬停背景
    
    # 边框
    "border": "#E2E8F0",            # 主边框
    "border_focus": "#2563EB",      # 聚焦边框
    
    # 主色调 - Trust Blue
    "primary": "#2563EB",           # 主按钮
    "primary_hover": "#1D4ED8",     # 主按钮悬停
    "primary_light": "#3B82F6",     # 浅蓝
    "primary_bg": "#EFF6FF",        # 主色背景
    
    # 文字色
    "text_primary": "#1E293B",      # 主文字 (slate-800)
    "text_secondary": "#475569",    # 次要文字 (slate-600)
    "text_hint": "#94A3B8",         # 提示文字 (slate-400)
    
    # 状态色
    "success": "#10B981",           # 成功绿
    "error": "#EF4444",             # 错误红
    "cta": "#F97316",               # CTA 橙色
}


# =====================================================
# 样式表 - Minimal & Direct 风格
# =====================================================

# 主窗口样式
WINDOW_STYLE = f"""
QMainWindow {{
    background-color: {COLORS['background']};
}}
"""

# 标题样式 - 使用系统字体确保中文显示
TITLE_LABEL_STYLE = f"""
QLabel {{
    color: {COLORS['text_primary']};
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
"""

SUBTITLE_LABEL_STYLE = f"""
QLabel {{
    color: {COLORS['text_secondary']};
    font-size: 14px;
    font-weight: 400;
}}
"""

VERSION_LABEL_STYLE = f"""
QLabel {{
    color: {COLORS['text_hint']};
    font-size: 13px;
    font-weight: 400;
}}
"""

# 主按钮样式 - 圆角 8px，清晰层次
PRIMARY_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 14px 56px;
    font-size: 15px;
    font-weight: 600;
    min-width: 220px;
    min-height: 48px;
}}
QPushButton:hover {{
    background-color: {COLORS['primary_hover']};
}}
QPushButton:pressed {{
    background-color: #1E40AF;
}}
QPushButton:disabled {{
    background-color: {COLORS['border']};
    color: {COLORS['text_hint']};
}}
"""

# 次要按钮样式
SECONDARY_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLORS['surface_hover']};
    border-color: {COLORS['text_hint']};
    color: {COLORS['text_primary']};
}}
QPushButton:pressed {{
    background-color: {COLORS['border']};
}}
"""

# 输入框样式
PATH_INPUT_STYLE = f"""
QLineEdit {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    selection-background-color: {COLORS['primary_bg']};
}}
QLineEdit:hover {{
    border-color: {COLORS['text_hint']};
}}
QLineEdit:focus {{
    border-color: {COLORS['primary']};
    border-width: 2px;
    padding: 11px 15px;
}}
"""

# 复选框样式
CHECKBOX_STYLE = f"""
QCheckBox {{
    color: {COLORS['text_secondary']};
    font-size: 13px;
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {COLORS['border']};
    border-radius: 4px;
    background-color: {COLORS['surface']};
}}
QCheckBox::indicator:hover {{
    border-color: {COLORS['primary']};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary']};
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTAgM0w0LjUgOC41TDIgNiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=);
}}
"""

# 进度条样式
PROGRESS_STYLE = f"""
QProgressBar {{
    background-color: {COLORS['border']};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLORS['primary']};
    border-radius: 4px;
}}
"""

# 链接按钮样式
LINK_BUTTON_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS['text_hint']};
    border: none;
    font-size: 13px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    color: {COLORS['primary']};
}}
"""


# =====================================================
# 安装工作线程
# =====================================================
class InstallWorker(QThread):
    """后台安装线程"""
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, install_path: str, create_shortcut: bool = True):
        super().__init__()
        self.install_path = install_path
        self.create_shortcut = create_shortcut
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        try:
            if getattr(sys, 'frozen', False):
                base_path = Path(sys._MEIPASS)
            else:
                base_path = Path(__file__).parent.parent / "dist" / "虎哥截图"
            
            app_data_path = base_path / "app_data"
            if not app_data_path.exists():
                app_data_path = base_path
            
            if not app_data_path.exists():
                self.finished.emit(False, f"找不到应用数据")
                return
            
            install_dir = Path(self.install_path)
            
            self.status.emit("检查应用状态...")
            self.progress.emit(5)
            
            if self._is_app_running():
                self.status.emit("正在关闭旧版本...")
                self._close_app()
                self.msleep(1000)
            
            if self._cancelled:
                self.finished.emit(False, "安装已取消")
                return
            
            self.status.emit("准备安装目录...")
            self.progress.emit(10)
            install_dir.mkdir(parents=True, exist_ok=True)
            
            self.status.emit("正在复制文件...")
            total_files = sum(1 for _ in app_data_path.rglob("*") if _.is_file())
            copied = 0
            
            for src_file in app_data_path.rglob("*"):
                if self._cancelled:
                    self.finished.emit(False, "安装已取消")
                    return
                
                rel_path = src_file.relative_to(app_data_path)
                dst_file = install_dir / rel_path
                
                if src_file.is_dir():
                    dst_file.mkdir(parents=True, exist_ok=True)
                else:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    copied += 1
                    progress = 10 + int(80 * copied / max(total_files, 1))
                    self.progress.emit(progress)
            
            if self.create_shortcut:
                self.status.emit("创建快捷方式...")
                self.progress.emit(92)
                self._create_shortcuts(install_dir)
            
            self.status.emit("安装完成！")
            self.progress.emit(100)
            self.finished.emit(True, str(install_dir / "虎哥截图.exe"))
            
        except Exception as e:
            self.finished.emit(False, f"安装失败: {str(e)}")
    
    def _is_app_running(self) -> bool:
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq 虎哥截图.exe'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return '虎哥截图.exe' in result.stdout
        except (subprocess.SubprocessError, OSError):
            return False
    
    def _close_app(self):
        try:
            subprocess.run(
                ['taskkill', '/F', '/IM', '虎哥截图.exe'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except (subprocess.SubprocessError, OSError):
            pass
    
    def _create_shortcuts(self, install_dir: Path):
        try:
            exe_path = install_dir / "虎哥截图.exe"
            desktop = Path(os.environ.get('USERPROFILE', '')) / 'Desktop'
            self._create_shortcut_file(desktop / "虎哥截图.lnk", exe_path)
            
            start_menu = Path(os.environ.get('APPDATA', '')) / \
                'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
            program_folder = start_menu / "虎哥截图"
            program_folder.mkdir(parents=True, exist_ok=True)
            self._create_shortcut_file(program_folder / "虎哥截图.lnk", exe_path)
        except Exception as e:
            print(f"创建快捷方式失败: {e}")
    
    def _create_shortcut_file(self, shortcut_path: Path, target_path: Path):
        try:
            safe_shortcut = str(shortcut_path).replace("'", "''").replace('"', '`"')
            safe_target = str(target_path).replace("'", "''").replace('"', '`"')
            safe_workdir = str(target_path.parent).replace("'", "''").replace('"', '`"')
            
            ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{safe_shortcut}")
$Shortcut.TargetPath = "{safe_target}"
$Shortcut.WorkingDirectory = "{safe_workdir}"
$Shortcut.Save()
'''
            subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"创建快捷方式失败: {e}")


# =====================================================
# 主窗口 - 自适应布局
# =====================================================
class InstallerWindow(QMainWindow):
    """现代化安装器主窗口 - 浅色系自适应布局"""
    
    def __init__(self):
        super().__init__()
        self.worker: Optional[InstallWorker] = None
        self.install_path = "D:\\虎哥截图"
        self.installed_exe_path: Optional[str] = None
        self._drag_pos = None
        
        self._setup_window()
        self._setup_ui()
        self._apply_fonts()
    
    def _apply_fonts(self):
        """应用中文字体确保正确显示"""
        font = QFont()
        font.setFamilies(["Microsoft YaHei", "Segoe UI", "sans-serif"])
        QApplication.instance().setFont(font)
    
    def _setup_window(self):
        """设置窗口属性 - 不固定高度，允许自适应"""
        self.setWindowTitle("虎哥截图 安装程序")
        self.setMinimumSize(520, 400)
        self.resize(520, 480)  # 初始大小，可调整
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(WINDOW_STYLE)
        
        # 设置窗口图标
        icon_path = get_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # 窗口居中
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def _setup_ui(self):
        """设置 UI - 使用弹性布局"""
        central = QWidget()
        self.setCentralWidget(central)
        central.setObjectName("mainContainer")
        central.setStyleSheet(f"""
            #mainContainer {{
                background-color: {COLORS['surface']};
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 8)
        central.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 标题栏
        self._create_title_bar(main_layout)
        
        # 内容区域 - 使用弹性布局
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(48, 32, 48, 40)
        content_layout.setSpacing(0)
        
        # 头部区域
        self._create_header(content_layout)
        
        # 弹性空间
        content_layout.addSpacing(24)
        
        # 安装按钮
        self._create_install_button(content_layout)
        
        # 自定义安装选项
        self._create_custom_options(content_layout)
        
        # 进度区域
        self._create_progress_area(content_layout)
        
        # 底部弹性空间
        content_layout.addStretch(1)
        
        main_layout.addWidget(content, 1)
    
    def _create_title_bar(self, layout: QVBoxLayout):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setFixedHeight(48)
        title_bar.setStyleSheet(f"""
            background-color: {COLORS['background']};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        
        bar_layout = QHBoxLayout(title_bar)
        bar_layout.setContentsMargins(20, 0, 12, 0)
        
        title = QLabel("安装程序")
        title.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
            font-weight: 500;
        """)
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_hint']};
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 400;
            }}
            QPushButton:hover {{
                background-color: {COLORS['error']};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.close)
        bar_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)
        self._title_bar = title_bar
    
    def _create_header(self, layout: QVBoxLayout):
        """创建头部区域"""
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.setAlignment(Qt.AlignCenter)
        
        # Logo - 使用品牌图片
        logo_label = QLabel()
        logo_label.setFixedSize(80, 80)
        logo_label.setAlignment(Qt.AlignCenter)
        
        logo_path = get_logo_path()
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled_pixmap = pixmap.scaled(
                80, 80,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            logo_label.setPixmap(scaled_pixmap)
        else:
            # 备用：使用 emoji
            logo_label.setStyleSheet(f"""
                background-color: {COLORS['primary_bg']};
                border-radius: 16px;
                font-size: 40px;
            """)
            logo_label.setText("📷")
        
        header_layout.addWidget(logo_label, 0, Qt.AlignCenter)
        
        header_layout.addSpacing(16)
        
        # 产品名称
        name_label = QLabel("虎哥截图")
        name_label.setStyleSheet(TITLE_LABEL_STYLE)
        name_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(name_label)
        
        # 副标题
        subtitle = QLabel("极致生产力体验")
        subtitle.setStyleSheet(SUBTITLE_LABEL_STYLE)
        subtitle.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtitle)
        
        # 版本号
        version = QLabel(f"v{self._get_version()}")
        version.setStyleSheet(VERSION_LABEL_STYLE)
        version.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(version)
        
        layout.addWidget(header)
    
    def _create_install_button(self, layout: QVBoxLayout):
        """创建安装按钮"""
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 16, 0, 16)
        btn_layout.setAlignment(Qt.AlignCenter)
        
        self.install_btn = QPushButton("一键安装")
        self.install_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.install_btn.setCursor(Qt.PointingHandCursor)
        self.install_btn.clicked.connect(self._start_install)
        
        # 按钮阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(37, 99, 235, 60))
        shadow.setOffset(0, 4)
        self.install_btn.setGraphicsEffect(shadow)
        
        btn_layout.addWidget(self.install_btn)
        layout.addWidget(btn_container)
    
    def _create_custom_options(self, layout: QVBoxLayout):
        """创建自定义安装选项"""
        self.options_container = QWidget()
        options_layout = QVBoxLayout(self.options_container)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(12)
        
        # 展开按钮
        toggle_container = QWidget()
        toggle_layout = QHBoxLayout(toggle_container)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setAlignment(Qt.AlignRight)
        
        self.toggle_btn = QPushButton("自定义安装 ▾")
        self.toggle_btn.setStyleSheet(LINK_BUTTON_STYLE)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_options)
        toggle_layout.addWidget(self.toggle_btn)
        options_layout.addWidget(toggle_container)
        
        # 可折叠区域
        self.expandable = QWidget()
        self.expandable.setVisible(False)
        expandable_layout = QVBoxLayout(self.expandable)
        expandable_layout.setContentsMargins(0, 8, 0, 0)
        expandable_layout.setSpacing(12)
        
        # 安装位置标签
        path_label = QLabel("安装位置")
        path_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
            font-weight: 500;
        """)
        expandable_layout.addWidget(path_label)
        
        # 路径输入行
        path_row = QWidget()
        path_row_layout = QHBoxLayout(path_row)
        path_row_layout.setContentsMargins(0, 0, 0, 0)
        path_row_layout.setSpacing(8)
        
        self.path_input = QLineEdit(self.install_path)
        self.path_input.setStyleSheet(PATH_INPUT_STYLE)
        self.path_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        path_row_layout.addWidget(self.path_input)
        
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_path)
        path_row_layout.addWidget(browse_btn)
        
        expandable_layout.addWidget(path_row)
        
        # 快捷方式选项
        self.shortcut_cb = QCheckBox("创建桌面快捷方式")
        self.shortcut_cb.setStyleSheet(CHECKBOX_STYLE)
        self.shortcut_cb.setChecked(True)
        self.shortcut_cb.setCursor(Qt.PointingHandCursor)
        expandable_layout.addWidget(self.shortcut_cb)
        
        options_layout.addWidget(self.expandable)
        layout.addWidget(self.options_container)
    
    def _create_progress_area(self, layout: QVBoxLayout):
        """创建进度区域"""
        self.progress_container = QWidget()
        self.progress_container.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 16, 0, 0)
        progress_layout.setSpacing(12)
        
        self.status_label = QLabel("准备安装...")
        self.status_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(PROGRESS_STYLE)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(self.progress_container)
    
    def _toggle_options(self):
        visible = not self.expandable.isVisible()
        self.expandable.setVisible(visible)
        self.toggle_btn.setText("自定义安装 ▴" if visible else "自定义安装 ▾")
        # 调整窗口大小以适应内容
        self.adjustSize()
    
    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择安装位置", self.path_input.text()
        )
        if path:
            self.path_input.setText(path)
    
    def _start_install(self):
        self.install_path = self.path_input.text()
        self.install_btn.setEnabled(False)
        self.install_btn.setText("正在安装...")
        self.options_container.setVisible(False)
        self.progress_container.setVisible(True)
        
        self.worker = InstallWorker(
            self.install_path,
            self.shortcut_cb.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()
    
    def _on_progress(self, value: int):
        self.progress_bar.setValue(value)
    
    def _on_status(self, text: str):
        self.status_label.setText(text)
    
    def _on_finished(self, success: bool, message: str):
        if success:
            self.installed_exe_path = message
            self.install_btn.setText("立即启动")
            self.install_btn.setEnabled(True)
            try:
                self.install_btn.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.install_btn.clicked.connect(self._launch_app)
            self.status_label.setText("✓ 安装完成！")
            self.status_label.setStyleSheet(f"""
                color: {COLORS['success']};
                font-size: 14px;
                font-weight: 600;
            """)
        else:
            self.install_btn.setText("重试")
            self.install_btn.setEnabled(True)
            try:
                self.install_btn.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.install_btn.clicked.connect(self._start_install)
            self.status_label.setText(f"✗ {message}")
            self.status_label.setStyleSheet(f"""
                color: {COLORS['error']};
                font-size: 13px;
            """)
    
    def _launch_app(self):
        if self.installed_exe_path and Path(self.installed_exe_path).exists():
            subprocess.Popen(
                [self.installed_exe_path],
                cwd=Path(self.installed_exe_path).parent
            )
        self.close()
    
    def _get_version(self) -> str:
        try:
            if getattr(sys, 'frozen', False):
                config_path = Path(sys._MEIPASS) / "installer_config.json"
            else:
                config_path = Path(__file__).parent / "installer_config.json"
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('version', '2.5.1')
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        return "2.5.1"
    
    # 窗口拖动
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 48:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
    
    window = InstallerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
