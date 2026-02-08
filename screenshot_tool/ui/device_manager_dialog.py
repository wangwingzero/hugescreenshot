"""
设备管理对话框

Feature: subscription-system
Requirements: 3.3, 3.5
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QMessageBox,
    QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


def device_log(message: str):
    """设备管理日志"""
    _debug_log(message, "DEVICE")


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    device_name: str
    machine_id: str
    is_current: bool
    last_active: Optional[datetime] = None


class DeviceListItem(QWidget):
    """设备列表项"""
    
    deactivate_clicked = Signal(str)  # device_id
    
    def __init__(self, device: DeviceInfo, parent=None):
        super().__init__(parent)
        self._device = device
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # 设备图标
        icon = QLabel("💻" if not self._device.is_current else "✅")
        icon.setFont(QFont("Segoe UI Emoji", 16))
        layout.addWidget(icon)
        
        # 设备信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        name_layout = QHBoxLayout()
        name_label = QLabel(self._device.device_name)
        name_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        name_layout.addWidget(name_label)
        
        if self._device.is_current:
            current_badge = QLabel("当前设备")
            current_badge.setStyleSheet("""
                QLabel {
                    background-color: #52c41a;
                    color: white;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                }
            """)
            name_layout.addWidget(current_badge)
        
        name_layout.addStretch()
        info_layout.addLayout(name_layout)
        
        # 最后活跃时间
        if self._device.last_active:
            time_str = self._device.last_active.strftime("%Y-%m-%d %H:%M")
            time_label = QLabel(f"最后活跃: {time_str}")
            time_label.setStyleSheet("color: #999; font-size: 11px;")
            info_layout.addWidget(time_label)
        
        layout.addLayout(info_layout, 1)
        
        # 停用按钮（非当前设备）
        if not self._device.is_current:
            deactivate_btn = QPushButton("停用")
            deactivate_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff4d4f;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 5px 12px;
                }
                QPushButton:hover {
                    background-color: #ff7875;
                }
            """)
            deactivate_btn.clicked.connect(
                lambda: self.deactivate_clicked.emit(self._device.device_id)
            )
            layout.addWidget(deactivate_btn)


class DeviceManagerDialog(QDialog):
    """设备管理对话框
    
    Requirements: 3.3, 3.5
    
    Signals:
        device_deactivated: 设备停用信号
    """
    
    device_deactivated = Signal(str)  # device_id
    
    def __init__(self, device_manager=None, parent=None):
        """初始化设备管理对话框
        
        Args:
            device_manager: 设备管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        self._device_manager = device_manager
        self._devices: List[DeviceInfo] = []
        self._setup_ui()
        self._load_devices()
    
    def _setup_ui(self):
        self.setWindowTitle("设备管理 - 虎哥截图")
        self.setFixedSize(450, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("已激活的设备")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(title)
        
        # 说明
        info = QLabel("终身 VIP 最多可在 3 台设备上使用。如需在新设备上使用，请先停用其他设备。")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)
        
        # 设备数量
        self._count_label = QLabel("已激活 0/3 台设备")
        self._count_label.setStyleSheet("color: #1890ff;")
        layout.addWidget(self._count_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(line)
        
        # 设备列表
        self._device_list = QListWidget()
        self._device_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #d9d9d9;
                border-radius: 4px;
            }
            QListWidget::item {
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:last-child {
                border-bottom: none;
            }
        """)
        layout.addWidget(self._device_list, 1)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._load_devices)
        btn_layout.addWidget(refresh_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_devices(self):
        """加载设备列表"""
        self._device_list.clear()
        
        if self._device_manager is None:
            device_log("未配置设备管理器")
            return
        
        try:
            # 只获取激活的设备
            devices = self._device_manager.get_active_devices()
            current_machine_id = self._device_manager.get_machine_id()
            
            self._devices = []
            for d in devices:
                # d 是 DeviceInfo 对象（dataclass），使用属性访问而非字典
                # 解析 last_seen 时间
                last_active = None
                if d.last_seen:
                    try:
                        # ISO 格式时间字符串
                        last_active = datetime.fromisoformat(d.last_seen.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        pass
                
                device_info = DeviceInfo(
                    device_id=d.id,
                    device_name=d.device_name or "未知设备",
                    machine_id=d.machine_id,
                    is_current=d.machine_id == current_machine_id,
                    last_active=last_active,
                )
                self._devices.append(device_info)
            
            # 更新计数
            self._count_label.setText(f"已激活 {len(self._devices)}/3 台设备")
            
            # 添加到列表
            for device in self._devices:
                item = QListWidgetItem()
                item.setSizeHint(DeviceListItem(device).sizeHint())
                self._device_list.addItem(item)
                
                widget = DeviceListItem(device)
                widget.deactivate_clicked.connect(self._deactivate_device)
                self._device_list.setItemWidget(item, widget)
            
            device_log(f"加载了 {len(self._devices)} 台激活设备")
            
        except Exception as e:
            device_log(f"加载设备列表失败: {e}")
            import traceback
            device_log(f"详细错误: {traceback.format_exc()}")
            QMessageBox.warning(self, "错误", f"加载设备列表失败: {e}")
    
    def _deactivate_device(self, device_id: str):
        """停用设备"""
        reply = QMessageBox.question(
            self, "确认停用",
            "确定要停用此设备吗？停用后该设备将无法使用 VIP 功能。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        if self._device_manager is None:
            return
        
        try:
            success, message = self._device_manager.deactivate_device(device_id)
            
            if success:
                device_log(f"设备已停用: {device_id}")
                self.device_deactivated.emit(device_id)
                self._load_devices()
                QMessageBox.information(self, "成功", "设备已停用")
            else:
                QMessageBox.warning(self, "失败", message or "停用设备失败")
                
        except Exception as e:
            device_log(f"停用设备失败: {e}")
            QMessageBox.critical(self, "错误", f"停用设备失败: {e}")
    
    def set_devices(self, devices: List[DeviceInfo]):
        """设置设备列表（用于测试）"""
        self._devices = devices
        self._device_list.clear()
        
        self._count_label.setText(f"已激活 {len(devices)}/3 台设备")
        
        for device in devices:
            item = QListWidgetItem()
            item.setSizeHint(DeviceListItem(device).sizeHint())
            self._device_list.addItem(item)
            
            widget = DeviceListItem(device)
            widget.deactivate_clicked.connect(self._deactivate_device)
            self._device_list.setItemWidget(item, widget)
