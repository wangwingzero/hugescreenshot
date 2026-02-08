# -*- coding: utf-8 -*-
"""
截图状态管理器

保存和恢复截图状态，支持意外关闭后恢复上次截图。

Feature: screenshot-state-restore
Requirements: 1.1, 1.2, 1.3, 2.1, 3.4, 4.1, 4.2
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage

from screenshot_tool.core.config_manager import get_user_data_dir
from screenshot_tool.core.async_logger import async_debug_log


@dataclass
class AnnotationData:
    """标注数据（可序列化）
    
    Feature: screenshot-state-restore
    Requirements: 3.2
    """
    tool: str                           # 工具类型: rect, ellipse, arrow, line, pen, marker, text, mosaic, step
    color: str                          # 颜色 (hex, e.g. "#FF0000")
    width: int                          # 线条粗细或字体大小
    points: List[Tuple[int, int]]       # 点坐标列表
    text: str = ""                      # 文字内容（仅 text 工具）
    step_number: int = 0                # 步骤编号（仅 step 工具）
    
    # 有效的工具类型
    VALID_TOOLS = {"rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step", "none"}
    
    def __post_init__(self):
        """验证并规范化数据"""
        # 验证工具类型
        if self.tool not in self.VALID_TOOLS:
            raise ValueError(f"Invalid tool type: {self.tool}")
        
        # 确保 points 是元组列表
        if self.points:
            self.points = [(int(p[0]), int(p[1])) for p in self.points]
        
        # 确保 width 是正整数
        if self.width is None or self.width < 0:
            self.width = 2
        
        # 确保 text 是字符串
        if self.text is None:
            self.text = ""
        
        # 确保 step_number 是非负整数
        if self.step_number is None or self.step_number < 0:
            self.step_number = 0
    
    def to_dict(self) -> dict:
        """序列化为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "tool": self.tool,
            "color": self.color,
            "width": self.width,
            "points": self.points,
            "text": self.text,
            "step_number": self.step_number,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AnnotationData':
        """从字典反序列化
        
        Args:
            data: 包含标注数据的字典
            
        Returns:
            AnnotationData 实例
            
        Raises:
            KeyError: 缺少必需字段
            ValueError: 字段值无效
        """
        return cls(
            tool=data["tool"],
            color=data["color"],
            width=data["width"],
            points=[tuple(p) for p in data["points"]],
            text=data.get("text", ""),
            step_number=data.get("step_number", 0),
        )


@dataclass
class ScreenshotState:
    """截图状态
    
    Feature: screenshot-state-restore
    Requirements: 3.3, 3.4
    """
    # 选区信息 (x, y, width, height)
    selection_rect: Tuple[int, int, int, int]
    
    # 标注列表
    annotations: List[AnnotationData] = field(default_factory=list)
    
    # 元数据
    timestamp: str = ""                 # ISO 格式时间戳
    screen_index: int = 0               # 截图所在屏幕索引
    
    # 图片文件名（相对于 states 目录）
    image_filename: str = "screenshot.png"
    
    # 版本号（用于兼容性）
    version: str = "1.0"
    
    def __post_init__(self):
        """验证并规范化数据"""
        # 确保 selection_rect 是四元组
        if len(self.selection_rect) != 4:
            raise ValueError("selection_rect must be a 4-tuple (x, y, width, height)")
        self.selection_rect = tuple(int(v) for v in self.selection_rect)
        
        # 设置默认时间戳
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        
        # 确保 annotations 是列表
        if self.annotations is None:
            self.annotations = []
    
    def to_dict(self) -> dict:
        """序列化为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "screen_index": self.screen_index,
            "selection_rect": list(self.selection_rect),
            "image_filename": self.image_filename,
            "annotations": [a.to_dict() for a in self.annotations],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ScreenshotState':
        """从字典反序列化
        
        Args:
            data: 包含状态数据的字典
            
        Returns:
            ScreenshotState 实例
            
        Raises:
            KeyError: 缺少必需字段
            ValueError: 字段值无效
        """
        annotations = [
            AnnotationData.from_dict(a) for a in data.get("annotations", [])
        ]
        return cls(
            selection_rect=tuple(data["selection_rect"]),
            annotations=annotations,
            timestamp=data.get("timestamp", ""),
            screen_index=data.get("screen_index", 0),
            image_filename=data.get("image_filename", "screenshot.png"),
            version=data.get("version", "1.0"),
        )


class ScreenshotStateManager:
    """截图状态管理器
    
    负责截图状态的保存、加载和文件管理。
    
    Feature: screenshot-state-restore
    Requirements: 1.1, 1.2, 1.3, 2.1, 4.1, 4.2, 4.3, 4.4
    """
    
    STATES_DIR = "states"
    STATE_FILE = "state.json"
    IMAGE_FILE = "screenshot.png"
    SAVE_DELAY_MS = 500  # 延迟保存时间（毫秒）
    
    def __init__(self):
        """初始化状态管理器"""
        self._data_dir = get_user_data_dir()
        self._states_dir = os.path.join(self._data_dir, self.STATES_DIR)
        
        # 延迟保存定时器（避免频繁 I/O）
        self._save_timer: Optional[QTimer] = None
        self._pending_state: Optional[ScreenshotState] = None
        self._pending_image: Optional[QImage] = None
        
        # 确保目录存在
        os.makedirs(self._states_dir, exist_ok=True)
    
    @property
    def state_file_path(self) -> str:
        """获取状态文件路径"""
        return os.path.join(self._states_dir, self.STATE_FILE)
    
    @property
    def image_file_path(self) -> str:
        """获取图像文件路径"""
        return os.path.join(self._states_dir, self.IMAGE_FILE)
    
    def _init_save_timer(self):
        """初始化延迟保存定时器"""
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(self.SAVE_DELAY_MS)
            self._save_timer.timeout.connect(self._do_save)
    
    def save_state(self, state: ScreenshotState, image: QImage, immediate: bool = False) -> bool:
        """保存截图状态
        
        Args:
            state: 截图状态数据
            image: 原始截图图像
            immediate: 是否立即保存（跳过延迟）
            
        Returns:
            是否保存成功（延迟保存时返回 True 表示已排队）
        """
        if immediate:
            return self._do_save_internal(state, image)
        
        # 延迟保存
        self._pending_state = state
        self._pending_image = image
        
        self._init_save_timer()
        self._save_timer.start()
        
        return True
    
    def _do_save(self):
        """执行延迟保存"""
        if self._pending_state is not None and self._pending_image is not None:
            self._do_save_internal(self._pending_state, self._pending_image)
            self._pending_state = None
            self._pending_image = None
    
    def _do_save_internal(self, state: ScreenshotState, image: QImage) -> bool:
        """实际执行保存操作
        
        Args:
            state: 截图状态数据
            image: 原始截图图像
            
        Returns:
            是否保存成功
        """
        try:
            # 确保目录存在
            os.makedirs(self._states_dir, exist_ok=True)
            
            # 保存图像为 PNG
            image_path = self.image_file_path
            if not image.save(image_path, "PNG"):
                async_debug_log(f"保存截图图像失败: {image_path}", "STATE")
                return False
            
            # 更新状态中的图像文件名
            state.image_filename = self.IMAGE_FILE
            state.timestamp = datetime.now().isoformat()
            
            # 保存状态为 JSON
            state_path = self.state_file_path
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
            
            async_debug_log(f"截图状态已保存: {state_path}", "STATE")
            return True
            
        except Exception as e:
            async_debug_log(f"保存截图状态失败: {e}", "STATE")
            return False
    
    def load_state(self) -> Optional[Tuple[ScreenshotState, QImage]]:
        """加载保存的状态
        
        Returns:
            (状态数据, 图像) 或 None（如果没有保存的状态或加载失败）
        """
        try:
            # 检查文件是否存在
            if not self.has_saved_state():
                return None
            
            # 加载 JSON 状态
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = ScreenshotState.from_dict(data)
            
            # 加载图像
            image = QImage(self.image_file_path)
            if image.isNull():
                async_debug_log(f"加载截图图像失败: {self.image_file_path}", "STATE")
                self.clear_state()
                return None
            
            async_debug_log(f"截图状态已加载: {self.state_file_path}", "STATE")
            return (state, image)
            
        except json.JSONDecodeError as e:
            async_debug_log(f"状态文件 JSON 解析失败: {e}", "STATE")
            self.clear_state()
            return None
        except (KeyError, ValueError) as e:
            async_debug_log(f"状态文件数据无效: {e}", "STATE")
            self.clear_state()
            return None
        except Exception as e:
            async_debug_log(f"加载截图状态失败: {e}", "STATE")
            return None
    
    def has_saved_state(self) -> bool:
        """检查是否有保存的状态
        
        Returns:
            是否存在有效的保存状态
        """
        return (os.path.exists(self.state_file_path) and 
                os.path.exists(self.image_file_path))
    
    def clear_state(self) -> None:
        """清除保存的状态"""
        try:
            if os.path.exists(self.state_file_path):
                os.remove(self.state_file_path)
            if os.path.exists(self.image_file_path):
                os.remove(self.image_file_path)
            async_debug_log("截图状态已清除", "STATE")
        except Exception as e:
            async_debug_log(f"清除截图状态失败: {e}", "STATE")
    
    def verify_state_integrity(self) -> bool:
        """验证状态文件完整性
        
        Returns:
            状态文件是否完整有效
        """
        try:
            if not self.has_saved_state():
                return False
            
            # 验证 JSON 文件
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证必需字段
            required_fields = ["selection_rect", "annotations"]
            for field in required_fields:
                if field not in data:
                    async_debug_log(f"状态文件缺少必需字段: {field}", "STATE")
                    return False
            
            # 验证图像文件
            image = QImage(self.image_file_path)
            if image.isNull():
                async_debug_log("状态图像文件无效", "STATE")
                return False
            
            return True
            
        except Exception as e:
            async_debug_log(f"状态文件验证失败: {e}", "STATE")
            return False
    
    def flush_pending_save(self) -> bool:
        """立即执行待处理的保存操作
        
        Returns:
            是否有待处理的保存并成功执行
        """
        if self._save_timer and self._save_timer.isActive():
            self._save_timer.stop()
        
        if self._pending_state is not None and self._pending_image is not None:
            result = self._do_save_internal(self._pending_state, self._pending_image)
            self._pending_state = None
            self._pending_image = None
            return result
        
        return False
