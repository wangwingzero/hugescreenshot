# =====================================================
# =============== 覆盖层截图界面 ===============
# =====================================================

"""
覆盖层截图界面 - 类似 Snipaste/微信截图的全屏覆盖操作

直接在截图上操作，工具栏贴在选区边缘
支持绘制图形的选中、拖动、缩放和删除
"""

import math
import os
import re
import time
import datetime
from typing import Optional, List
from enum import Enum
from dataclasses import dataclass, field

# ========== 调试日志配置 ==========
# 使用异步日志器，避免阻塞主线程
from screenshot_tool.core.async_logger import async_debug_log as debug_log
from screenshot_tool.core.window_detector import WindowDetector, DetectionResult, is_window_detection_available
from screenshot_tool.core.topmost_window_manager import TopmostWindowManager
# 性能监控
# Feature: extreme-performance-optimization
# Requirements: 2.2
from screenshot_tool.core.performance_monitor import PerformanceMonitor

from PySide6.QtWidgets import (
    QWidget, QApplication, QToolButton, 
    QHBoxLayout, QVBoxLayout, QLabel, QColorDialog, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QTimer, QObject, QEvent
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush,
    QMouseEvent, QPaintEvent, QKeyEvent, QWheelEvent, QImage,
    QGuiApplication, QPolygon, QFont, QFontMetrics, QInputMethodEvent
)

# 线条粗细常量（模块级别，供多个类使用）
MIN_LINE_WIDTH = 1
MAX_LINE_WIDTH = 20
DEFAULT_LINE_WIDTH = 2

# 文字工具常量
TEXT_FONT_FAMILY = "Microsoft YaHei"  # 文字工具的字体

# 文字项字体大小范围
TEXT_FONT_SIZE_MIN = 10
TEXT_FONT_SIZE_MAX = 200

def get_text_font_size(width_level: int) -> int:
    """根据粗细级别计算文字字体大小（pt）
    
    Args:
        width_level: 粗细级别 (1-10)
        
    Returns:
        字体大小 (pt)，范围 10-28
    """
    # 确保级别在有效范围内
    level = max(1, min(10, width_level))
    # 级别 1-10 对应字体大小 10-28pt
    return 10 + (level - 1) * 2


def font_size_to_width_level(font_size: int) -> int:
    """将字体大小转换为粗细级别（用于侧边栏显示）
    
    Args:
        font_size: 字体大小 (pt)
        
    Returns:
        粗细级别 (1-10)，超出范围时返回边界值
    """
    # 字体大小 = 10 + (level - 1) * 2，反推 level = (font_size - 10) / 2 + 1
    level = (font_size - 10) // 2 + 1
    return max(1, min(10, level))


class DrawTool(Enum):
    """绘制工具"""
    NONE = "none"
    RECT = "rect"
    ELLIPSE = "ellipse"
    ARROW = "arrow"
    LINE = "line"
    PEN = "pen"
    MARKER = "marker"
    TEXT = "text"
    MOSAIC = "mosaic"
    STEP = "step"  # 步骤编号


@dataclass
class DrawItem:
    """绘制项"""
    tool: DrawTool
    color: QColor
    width: int
    points: List[QPoint] = field(default_factory=list)
    text: str = ""
    step_number: int = 0  # 步骤编号（仅用于 STEP 工具）
    
    # 类级别的 ID 计数器，确保唯一性
    _id_counter: int = field(default=0, init=False, repr=False, compare=False)
    _id: int = field(default=0, init=False, repr=False, compare=False)
    
    def __post_init__(self):
        """初始化后分配唯一 ID"""
        DrawItem._id_counter += 1
        object.__setattr__(self, '_id', DrawItem._id_counter)
    
    def __hash__(self) -> int:
        """使 DrawItem 可哈希，基于唯一 ID"""
        return self._id
    
    def __eq__(self, other) -> bool:
        """基于唯一 ID 比较"""
        if not isinstance(other, DrawItem):
            return False
        return self._id == other._id
    
    def get_bounding_rect(self) -> QRect:
        """获取边界矩形"""
        if not self.points:
            return QRect()
        if self.tool in (DrawTool.RECT, DrawTool.ELLIPSE, DrawTool.MOSAIC, DrawTool.LINE, DrawTool.ARROW, DrawTool.MARKER):
            if len(self.points) >= 2:
                return QRect(self.points[0], self.points[-1]).normalized()
        elif self.tool in (DrawTool.PEN,):
            if len(self.points) >= 1:
                min_x = min(p.x() for p in self.points)
                max_x = max(p.x() for p in self.points)
                min_y = min(p.y() for p in self.points)
                max_y = max(p.y() for p in self.points)
                # 确保宽高至少为1，避免空矩形
                width = max(1, max_x - min_x)
                height = max(1, max_y - min_y)
                return QRect(min_x, min_y, width, height)
        elif self.tool == DrawTool.TEXT:
            if len(self.points) >= 1:
                # 根据文字内容计算边界（字体大小由 width 决定）
                # 兼容旧格式（width 存储粗细级别 1-10）和新格式（width 直接存储字体大小 pt）
                if self.width and self.width > 10:
                    font_size = self.width  # 新格式：直接是字体大小
                else:
                    font_size = get_text_font_size(self.width if self.width else 5)  # 旧格式：粗细级别
                font = QFont(TEXT_FONT_FAMILY, font_size)
                font.setBold(True)
                metrics = QFontMetrics(font)
                
                # points[0] 是文字基线位置，边界矩形需要向上偏移 ascent
                rect_x = self.points[0].x()
                rect_y = self.points[0].y() - metrics.ascent()
                
                if self.text:
                    # 有文字时，根据文字内容计算宽度
                    text_rect = metrics.boundingRect(self.text)
                    rect_w = text_rect.width() + 10
                else:
                    # 空文字时，使用最小宽度（光标宽度）
                    rect_w = 10
                
                rect_h = metrics.height() + 6
                return QRect(rect_x, rect_y, rect_w, rect_h)
        elif self.tool == DrawTool.STEP:
            if len(self.points) >= 1:
                # 步骤编号是圆形，width 存储直径
                # 安全处理 width 为 None 或 0 的情况
                width_val = self.width if self.width and self.width > 0 else 30
                diameter = max(20, min(100, width_val if width_val > 10 else 30))
                radius = diameter // 2
                center = self.points[0]
                return QRect(center.x() - radius, center.y() - radius, diameter, diameter)
        return QRect()
    
    def contains_point(self, pos: QPoint, margin: int = 5) -> bool:
        """检查点是否在图形内"""
        rect = self.get_bounding_rect()
        if rect.isEmpty():
            return False
        
        # 直线和箭头使用点到线段距离检测，更精确
        if self.tool in (DrawTool.LINE, DrawTool.ARROW) and len(self.points) >= 2:
            # 计算点到线段的距离
            p1 = self.points[0]
            p2 = self.points[-1]
            distance = self._point_to_line_distance(pos, p1, p2)
            # 检测范围 = margin + 线条粗细的一半
            hit_margin = margin + max(self.width // 2, 3)
            return distance <= hit_margin
        
        # 步骤编号使用圆形检测
        if self.tool == DrawTool.STEP and len(self.points) >= 1:
            center = self.points[0]
            # 安全处理 width 为 None 或 0 的情况
            width_val = self.width if self.width and self.width > 0 else 30
            diameter = max(20, min(100, width_val if width_val > 10 else 30))
            radius = diameter // 2 + margin
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            return (dx * dx + dy * dy) <= (radius * radius)
        
        expanded = rect.adjusted(-margin, -margin, margin, margin)
        return expanded.contains(pos)
    
    def _point_to_line_distance(self, point: QPoint, line_start: QPoint, line_end: QPoint) -> float:
        """计算点到线段的距离"""
        px, py = point.x(), point.y()
        x1, y1 = line_start.x(), line_start.y()
        x2, y2 = line_end.x(), line_end.y()
        
        # 线段长度的平方
        line_len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
        
        if line_len_sq == 0:
            # 线段退化为点
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        
        # 计算投影参数 t（点在线段上的投影位置，0-1 之间表示在线段上）
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / line_len_sq))
        
        # 投影点坐标
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        
        # 返回点到投影点的距离
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
    
    def move_by(self, delta: QPoint):
        """移动图形"""
        self.points = [QPoint(p.x() + delta.x(), p.y() + delta.y()) for p in self.points]
    
    def resize(self, old_rect: QRect, new_rect: QRect):
        """缩放图形
        
        对于文字项，会根据缩放比例调整字体大小（width 属性直接存储字体大小 pt）
        """
        if old_rect.isEmpty() or new_rect.isEmpty() or old_rect.width() == 0 or old_rect.height() == 0:
            return
        scale_x = new_rect.width() / old_rect.width()
        scale_y = new_rect.height() / old_rect.height()
        new_points = []
        for p in self.points:
            rel_x = p.x() - old_rect.left()
            rel_y = p.y() - old_rect.top()
            new_x = new_rect.left() + int(rel_x * scale_x)
            new_y = new_rect.top() + int(rel_y * scale_y)
            new_points.append(QPoint(new_x, new_y))
        self.points = new_points
        
        # 文字项：根据缩放比例调整字体大小
        if self.tool == DrawTool.TEXT and self.width and self.width > 0:
            # 使用较大的缩放比例来调整字体
            scale = max(scale_x, scale_y)
            # 对于文字项，width 直接存储字体大小 (pt)
            # 如果 width 值较小（<= 10），说明是旧的粗细级别格式，需要转换
            if self.width <= 10:
                current_font_size = get_text_font_size(self.width)
            else:
                current_font_size = self.width
            new_font_size = int(current_font_size * scale)
            # 限制字体大小范围
            self.width = max(TEXT_FONT_SIZE_MIN, min(TEXT_FONT_SIZE_MAX, new_font_size))
        
        # 步骤编号：根据缩放比例调整直径
        elif self.tool == DrawTool.STEP and self.width and self.width > 0:
            # 使用较大的缩放比例来调整直径
            scale = max(scale_x, scale_y)
            current_diameter = self.width if self.width > 10 else 30
            new_diameter = int(current_diameter * scale)
            # 限制直径范围 20-100
            self.width = max(20, min(100, new_diameter))
    
    def to_annotation_data(self) -> 'AnnotationData':
        """转换为 AnnotationData（可序列化格式）
        
        Feature: screenshot-state-restore
        Requirements: 1.3, 2.2
        
        Returns:
            AnnotationData 实例
        """
        from screenshot_tool.core.screenshot_state_manager import AnnotationData
        
        return AnnotationData(
            tool=self.tool.value,
            color=self.color.name(),
            width=self.width,
            points=[(p.x(), p.y()) for p in self.points],
            text=self.text,
            step_number=self.step_number,
        )
    
    @classmethod
    def from_annotation_data(cls, data: 'AnnotationData') -> 'DrawItem':
        """从 AnnotationData 创建 DrawItem
        
        Feature: screenshot-state-restore
        Requirements: 1.3, 2.2
        
        Args:
            data: AnnotationData 实例
            
        Returns:
            DrawItem 实例
        """
        from screenshot_tool.core.screenshot_state_manager import AnnotationData
        
        return cls(
            tool=DrawTool(data.tool),
            color=QColor(data.color),
            width=data.width,
            points=[QPoint(p[0], p[1]) for p in data.points],
            text=data.text,
            step_number=data.step_number,
        )


@dataclass
class InlineTextEditor:
    """内联文字编辑器状态
    
    用于在画布上直接输入和编辑文字，替代 QLineEdit 输入框。
    支持光标移动、文字选择、删除等基本编辑操作。
    
    Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.4, 4.1, 4.2, 4.3, 4.4
    """
    active: bool = False              # 是否处于编辑状态
    text: str = ""                    # 当前文字内容
    position: Optional[QPoint] = None # 文字位置（画布坐标）
    cursor_pos: int = 0               # 光标位置（字符索引）
    selection_start: int = -1         # 选择起始位置（-1 表示无选择）
    selection_end: int = -1           # 选择结束位置
    cursor_visible: bool = True       # 光标是否可见（用于闪烁）
    editing_item: Optional[DrawItem] = None  # 正在编辑的已有项（None 表示新建）
    color: Optional[QColor] = None    # 文字颜色
    font_size: int = 12               # 字体大小（pt）
    
    def has_selection(self) -> bool:
        """是否有选中文字"""
        return (self.selection_start >= 0 and 
                self.selection_end >= 0 and 
                self.selection_start != self.selection_end)
    
    def get_selected_text(self) -> str:
        """获取选中的文字"""
        if not self.has_selection():
            return ""
        start = min(self.selection_start, self.selection_end)
        end = max(self.selection_start, self.selection_end)
        return self.text[start:end]
    
    def clear_selection(self):
        """清除选择"""
        self.selection_start = -1
        self.selection_end = -1
    
    def get_selection_range(self) -> tuple:
        """获取选择范围（start, end），确保 start <= end"""
        if not self.has_selection():
            return (-1, -1)
        return (min(self.selection_start, self.selection_end),
                max(self.selection_start, self.selection_end))
    
    def reset(self):
        """重置编辑器状态"""
        self.active = False
        self.text = ""
        self.position = None
        self.cursor_pos = 0
        self.selection_start = -1
        self.selection_end = -1
        self.cursor_visible = True
        self.editing_item = None
        self.color = None
        self.font_size = 12


class DraggableMixin:
    """可拖动混入类
    
    为工具栏添加拖动功能。
    使用时需要在子类中定义 drag_started 和 drag_ended 信号。
    
    拖动只在工具栏的空白区域（非按钮区域）生效。
    
    Requirements: 4.1, 4.2, 4.3, 4.4
    """
    
    # 拖动阈值（像素），超过此距离才认为是拖动
    DRAG_THRESHOLD = 5
    
    def _init_draggable(self):
        """初始化拖动状态（在子类 __init__ 中调用）"""
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_widget_pos: Optional[QPoint] = None
        self._is_dragging = False
        self._drag_confirmed = False  # 是否确认为拖动操作
    
    def _is_on_button(self, pos: QPoint) -> bool:
        """检查点击位置是否在按钮上
        
        Args:
            pos: 相对于工具栏的位置
            
        Returns:
            True 如果点击在按钮上
        """
        child = self.childAt(pos)
        if child is None:
            return False
        # 检查是否是按钮或按钮的子控件
        from PySide6.QtWidgets import QAbstractButton
        while child is not None:
            if isinstance(child, QAbstractButton):
                return True
            child = child.parentWidget()
            if child == self:
                break
        return False
    
    def mousePressEvent(self, event):
        """鼠标按下 - 准备拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击在按钮上
            if self._is_on_button(event.position().toPoint()):
                # 点击在按钮上，不启动拖动，让按钮处理事件
                super().mousePressEvent(event)
                return
            
            # 点击在空白区域，准备拖动
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_widget_pos = self.pos()
            self._is_dragging = True
            self._drag_confirmed = False
            if hasattr(self, 'drag_started'):
                self.drag_started.emit()
            event.accept()  # 接受事件，阻止传递
            return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 执行拖动"""
        if self._is_dragging and self._drag_start_pos is not None:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._drag_start_pos
            
            # 检查是否超过拖动阈值
            if not self._drag_confirmed:
                if abs(delta.x()) > self.DRAG_THRESHOLD or abs(delta.y()) > self.DRAG_THRESHOLD:
                    self._drag_confirmed = True
                else:
                    return  # 还没超过阈值，不移动
            
            new_pos = self._drag_start_widget_pos + delta
            self.move(new_pos)
            event.accept()  # 接受事件，阻止传递
            return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            was_dragging = self._drag_confirmed
            self._is_dragging = False
            self._drag_confirmed = False
            
            # 只有确认为拖动操作时才发出信号
            if was_dragging and hasattr(self, 'drag_ended'):
                self.drag_ended.emit(self.pos())
            
            self._drag_start_pos = None
            self._drag_start_widget_pos = None
            event.accept()  # 接受事件，阻止传递
            return
        super().mouseReleaseEvent(event)


class ToolbarButton(QToolButton):
    """工具栏按钮"""
    def __init__(self, icon: str, label: str, tooltip: str = "", checkable: bool = False, parent=None):
        super().__init__(parent)
        # emoji 图标在上，工具名称在下
        self.setText(f"{icon}\n{label}")
        self.setToolTip(tooltip if tooltip else label)
        self.setCheckable(checkable)
        self.setMinimumHeight(48)
        self.setMinimumWidth(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QToolButton {
                background-color: rgba(50, 50, 50, 200);
                color: #4ADE80;
                border: none;
                border-radius: 4px;
                font-size: 10pt;
                padding: 4px 6px;
            }
            QToolButton:hover { background-color: rgba(80, 80, 80, 220); }
            QToolButton:checked { background-color: rgba(74, 144, 217, 220); }
            QToolButton:pressed { background-color: rgba(60, 60, 60, 220); }
        """)


class FloatingToolbar(DraggableMixin, QWidget):
    """浮动工具栏 - 底部绘图工具（可拖动）"""
    toolSelected = Signal(DrawTool)
    recordingClicked = Signal()  # 录屏按钮
    drag_started = Signal()
    drag_ended = Signal(QPoint)
    
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._init_draggable()
        self._current_tool = DrawTool.NONE
        self._tool_buttons = {}
        self._setup_ui()
        
    def _setup_ui(self):
        # 作为子控件，不设置窗口标志
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: rgba(40, 40, 40, 230); border-radius: 6px; }")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 4, 6, 4)
        container_layout.setSpacing(4)
        
        # 只保留绘图工具（使用 emoji 图标）
        tools = [
            (DrawTool.RECT, "⬜", "矩形"), (DrawTool.ELLIPSE, "🟥", "方块"),
            (DrawTool.ARROW, "➡️", "箭头"), (DrawTool.LINE, "📏", "直线"),
            (DrawTool.PEN, "✏️", "画笔"), (DrawTool.MARKER, "🖍️", "高亮"),
            (DrawTool.TEXT, "🔤", "文字"), (DrawTool.MOSAIC, "🔲", "马赛克"),
            (DrawTool.STEP, "①", "编号"),
        ]
        
        for tool, icon, label in tools:
            btn = ToolbarButton(icon, label, checkable=True)
            btn.clicked.connect(lambda checked, t=tool: self._on_tool_clicked(t))
            self._tool_buttons[tool] = btn
            container_layout.addWidget(btn)
        
        # 添加分隔符
        sep = QWidget()
        sep.setFixedSize(1, 36)
        sep.setStyleSheet("background-color: rgba(100, 100, 100, 150);")
        container_layout.addWidget(sep)
        
        # 录屏按钮
        recording_btn = ToolbarButton("🎬", "录屏", checkable=False)
        recording_btn.clicked.connect(self.recordingClicked.emit)
        container_layout.addWidget(recording_btn)
        
        layout.addWidget(container)
        
    def _on_tool_clicked(self, tool: DrawTool):
        for t, btn in self._tool_buttons.items():
            if t != tool:
                btn.setChecked(False)
        self._current_tool = tool if self._tool_buttons[tool].isChecked() else DrawTool.NONE
        self.toolSelected.emit(self._current_tool)
    
    def deselect_all_tools(self):
        for btn in self._tool_buttons.values():
            btn.setChecked(False)
        self._current_tool = DrawTool.NONE
        self.toolSelected.emit(self._current_tool)
    
    def select_tool(self, tool: DrawTool):
        """从外部设置选中的工具"""
        for t, btn in self._tool_buttons.items():
            btn.setChecked(t == tool)
        self._current_tool = tool
        self.toolSelected.emit(self._current_tool)


# 粗细级别到实际像素的映射（非线性，让差异更明显）
# 级别 1-10 对应实际像素值
WIDTH_LEVEL_TO_PIXELS = {
    1: 1,
    2: 2,
    3: 4,
    4: 6,
    5: 8,
    6: 12,
    7: 16,
    8: 20,
    9: 26,
    10: 32,
}

# 像素值到级别的反向映射（用于从图形宽度反推级别）
PIXELS_TO_WIDTH_LEVEL = {v: k for k, v in WIDTH_LEVEL_TO_PIXELS.items()}

def get_actual_width(level: int) -> int:
    """将粗细级别转换为实际像素值"""
    level = max(1, min(10, level))
    return WIDTH_LEVEL_TO_PIXELS.get(level, level * 2)

def get_step_diameter(level: int) -> int:
    """将粗细级别转换为步骤编号的直径
    
    步骤编号使用独立的直径计算公式：
    - 级别 1 = 20 像素（最小）
    - 级别 5 = 40 像素（默认）
    - 级别 10 = 65 像素（最大）
    
    Args:
        level: 粗细级别 (1-10)
        
    Returns:
        步骤编号圆的直径（像素）
    """
    level = max(1, min(10, level))
    return 20 + (level - 1) * 5

def get_step_level_from_diameter(diameter: int) -> int:
    """从步骤编号直径反推粗细级别
    
    Args:
        diameter: 步骤编号圆的直径（像素）
        
    Returns:
        粗细级别 (1-10)
    """
    if diameter <= 0:
        return 1
    # 反推公式：level = (diameter - 20) / 5 + 1
    level = (diameter - 20) // 5 + 1
    return max(1, min(10, level))

def get_width_level(pixels: int) -> int:
    """将实际像素值转换为粗细级别（反向查找）
    
    如果像素值不在映射表中，返回最接近的级别
    
    Args:
        pixels: 实际像素值
        
    Returns:
        粗细级别 (1-10)
    """
    # 边界检查：无效值返回默认级别
    if pixels <= 0:
        return 1
    
    if pixels in PIXELS_TO_WIDTH_LEVEL:
        return PIXELS_TO_WIDTH_LEVEL[pixels]
    
    # 找最接近的级别
    min_diff = float('inf')
    closest_level = 1
    for px, level in PIXELS_TO_WIDTH_LEVEL.items():
        diff = abs(px - pixels)
        if diff < min_diff:
            min_diff = diff
            closest_level = level
    return closest_level


class WidthSelectorPopup(QWidget):
    """粗细选择器弹窗"""
    widthSelected = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.Popup |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: rgba(40, 40, 40, 240); border-radius: 6px; }")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(6, 6, 6, 6)
        container_layout.setSpacing(2)
        
        # 创建 1-10 的粗细选项
        for level in range(1, 11):
            btn = QToolButton()
            btn.setText(f"{level}")
            btn.setMinimumSize(36, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QToolButton {
                    background-color: transparent;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12pt;
                    padding: 4px 8px;
                }
                QToolButton:hover { background-color: rgba(74, 144, 217, 180); }
            """)
            btn.clicked.connect(lambda checked, l=level: self._on_level_clicked(l))
            container_layout.addWidget(btn)
        
        layout.addWidget(container)
    
    def _on_level_clicked(self, level: int):
        self.widthSelected.emit(level)
        self.hide()


class SideToolbar(DraggableMixin, QWidget):
    """侧边工具栏 - 右侧功能按钮（可拖动）"""
    colorChanged = Signal(QColor)
    widthChanged = Signal(int)  # 发送粗细级别
    undoClicked = Signal()
    redoClicked = Signal()
    saveClicked = Signal()
    cancelClicked = Signal()
    ocrToggled = Signal(bool)  # OCR 按钮点击信号
    pinClicked = Signal()
    ankiClicked = Signal()  # Anki 制卡按钮
    drag_started = Signal()
    drag_ended = Signal(QPoint)
    
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._init_draggable()
        self._current_color = QColor("#FFFF00")  # 默认黄色
        self._current_width_level = DEFAULT_LINE_WIDTH  # 粗细级别 1-10
        self._width_popup: Optional[WidthSelectorPopup] = None
        self._ocr_btn: Optional[QToolButton] = None  # OCR 按钮引用
        self._setup_ui()
        
    def _setup_ui(self):
        # 作为子控件，不设置窗口标志
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: rgba(40, 40, 40, 230); border-radius: 6px; }")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(2)
        
        # 撤销/重做
        undo_btn = self._create_button("↩️", "撤销")
        undo_btn.clicked.connect(self.undoClicked.emit)
        container_layout.addWidget(undo_btn)
        
        redo_btn = self._create_button("↪️", "恢复")
        redo_btn.clicked.connect(self.redoClicked.emit)
        container_layout.addWidget(redo_btn)
        
        self._add_separator(container_layout)
        
        # 颜色选择
        self._color_btn = self._create_button("🎨", "颜色")
        self._update_color_button()
        self._color_btn.clicked.connect(self._on_color_clicked)
        container_layout.addWidget(self._color_btn)
        
        # 粗细调整（显示当前值，点击弹出选择器）
        self._width_btn = self._create_button(f"{self._current_width_level}", "粗细")
        self._width_btn.setText(f"{self._current_width_level}\n粗细")  # 数字在上，名称在下
        self._width_btn.clicked.connect(self._on_width_clicked)
        container_layout.addWidget(self._width_btn)
        
        self._add_separator(container_layout)
        
        # OCR 按钮（点击触发 OCR 面板）
        self._ocr_btn = self._create_button("📝", "识字")
        self._ocr_btn.clicked.connect(self._on_ocr_clicked)
        container_layout.addWidget(self._ocr_btn)
        
        # Anki 制卡
        anki_btn = self._create_button("📚", "Anki")
        anki_btn.clicked.connect(self.ankiClicked.emit)
        container_layout.addWidget(anki_btn)
        
        # 钉住
        pin_btn = self._create_button("📌", "钉住")
        pin_btn.clicked.connect(self.pinClicked.emit)
        container_layout.addWidget(pin_btn)

        self._add_separator(container_layout)
        
        # 取消
        cancel_btn = self._create_button("❌", "取消")
        cancel_btn.clicked.connect(self.cancelClicked.emit)
        container_layout.addWidget(cancel_btn)
        
        # 保存
        save_btn = self._create_button("💾", "保存")
        save_btn.clicked.connect(self.saveClicked.emit)
        container_layout.addWidget(save_btn)
        
        layout.addWidget(container)
    
    def _create_button(self, icon: str, label: str, special_style: str = None) -> QToolButton:
        """创建侧边栏按钮 - emoji图标在上，名称在下"""
        btn = QToolButton()
        btn.setText(f"{icon}\n{label}")
        btn.setToolTip(label)
        btn.setMinimumHeight(48)
        btn.setMinimumWidth(48)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if special_style:
            btn.setStyleSheet(special_style)
        else:
            btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(50, 50, 50, 200);
                    color: #4ADE80;
                    border: none;
                    border-radius: 4px;
                    font-size: 10pt;
                    padding: 4px 6px;
                }
                QToolButton:hover { background-color: rgba(80, 80, 80, 220); }
                QToolButton:pressed { background-color: rgba(60, 60, 60, 220); }
            """)
        return btn
    
    def _add_separator(self, layout):
        sep = QWidget()
        sep.setFixedSize(48, 1)
        sep.setStyleSheet("background-color: rgba(100, 100, 100, 150);")
        layout.addWidget(sep)
        
    def _on_color_clicked(self):
        # 创建颜色对话框并启用屏幕取色功能
        dialog = QColorDialog(self._current_color, self)
        dialog.setWindowTitle("选择颜色")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, False)
        
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            if color.isValid():
                self._current_color = color
                self._update_color_button()
                self.colorChanged.emit(color)
    
    def _update_color_button(self):
        self._color_btn.setStyleSheet(f"""
            QToolButton {{ background-color: rgba(50, 50, 50, 200); color: {self._current_color.name()}; border: none; border-radius: 4px; font-size: 10pt; padding: 4px 6px; }}
            QToolButton:hover {{ background-color: rgba(80, 80, 80, 220); }}
        """)
    
    def _on_width_clicked(self):
        """点击粗细按钮，弹出选择器"""
        if self._width_popup is None:
            self._width_popup = WidthSelectorPopup()
            self._width_popup.widthSelected.connect(self._on_width_selected)
        
        # 在按钮左侧显示弹窗
        btn_pos = self._width_btn.mapToGlobal(QPoint(0, 0))
        popup_width = self._width_popup.sizeHint().width()
        self._width_popup.move(btn_pos.x() - popup_width - 4, btn_pos.y())
        self._width_popup.show()
    
    def _on_width_selected(self, level: int):
        """选择了粗细级别"""
        self._current_width_level = level
        self._width_btn.setText(f"{level}\n粗细")
        self.widthChanged.emit(level)
    
    def update_width(self, level: int):
        """更新粗细显示（级别 1-10）"""
        self._current_width_level = level
        self._width_btn.setText(f"{level}\n粗细")
    
    def update_color(self, color: QColor):
        """更新颜色"""
        self._current_color = color
        self._update_color_button()
    
    def set_ocr_loading(self, loading: bool):
        """设置 OCR 按钮加载状态
        
        Args:
            loading: True 表示 OCR 正在进行中，禁用按钮并显示"识字中"；
                     False 表示 OCR 完成，恢复按钮
        """
        if loading:
            self._ocr_btn.setText("⏳\n识字中")
            self._ocr_btn.setEnabled(False)
            self._ocr_btn.setToolTip("正在后台识别文字...")
            self._ocr_btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(50, 50, 50, 200);
                    color: rgba(150, 150, 150, 180);
                    border: none;
                    border-radius: 4px;
                    font-size: 10pt;
                    padding: 4px 6px;
                }
            """)
        else:
            self._ocr_btn.setText("📝\n识字")
            self._ocr_btn.setEnabled(True)
            self._ocr_btn.setToolTip("识字")
            self._ocr_btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(50, 50, 50, 200);
                    color: #4ADE80;
                    border: none;
                    border-radius: 4px;
                    font-size: 10pt;
                    padding: 4px 6px;
                }
                QToolButton:hover { background-color: rgba(80, 80, 80, 220); }
                QToolButton:pressed { background-color: rgba(60, 60, 60, 220); }
            """)
    
    def _on_ocr_clicked(self):
        """OCR 按钮点击处理 - 直接触发 OCR 面板显示（一次性操作）"""
        # 直接发送信号触发 OCR 面板
        self.ocrToggled.emit(True)
    
    def hide(self):
        """重写 hide 方法"""
        if self._width_popup:
            self._width_popup.hide()
        super().hide()
    
    def cleanup(self):
        """清理资源"""
        if self._width_popup:
            self._width_popup.close()
            self._width_popup.deleteLater()
            self._width_popup = None


class SizeInfoLabel(QWidget):
    """尺寸信息标签"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # 作为子控件，不设置窗口标志
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        self._label.setStyleSheet("QLabel { background-color: rgba(0, 0, 0, 180); color: white; padding: 4px 8px; border-radius: 4px; font-size: 10pt; }")
        layout.addWidget(self._label)
        
    def set_info(self, x: int, y: int, w: int, h: int):
        self._label.setText(f"{x},{y}  {w} × {h}")
        self.adjustSize()


class OverlayScreenshot(QWidget):
    """覆盖层截图界面"""
    screenshotTaken = Signal(QImage)
    screenshotCancelled = Signal()
    ocrRequested = Signal(QImage)
    pinRequested = Signal(QImage, QRect)
    selectionReady = Signal(QImage)  # 选区确定后自动触发，用于后台OCR预处理
    colorChanged = Signal(str)  # 颜色改变信号，参数为颜色的十六进制字符串
    toolColorChanged = Signal(str, str)  # 工具颜色改变信号，参数为工具名称和颜色
    toolWidthChanged = Signal(str, int)  # 工具粗细改变信号，参数为工具名称和粗细级别
    ankiRequested = Signal(QImage, list, str, list)  # Anki制卡请求，参数为截图、高亮区域列表、高亮颜色、预识别单词列表
    screenshotSaveRequested = Signal(QImage, str)  # 保存到指定文件请求，参数为截图和完整文件路径
    recordingRequested = Signal(QRect)  # 录屏请求，参数为录制区域
    
    # 边缘检测范围（像素）- 平衡边缘拖动和选区内绘制的体验
    # 10px 在普通屏幕上足够精确，在高 DPI 屏幕上也不会太小
    EDGE_MARGIN = 10
    
    # 光标样式映射（类常量，避免每次调用时重新创建）
    _ITEM_EDGE_CURSORS = {
        "tl": Qt.CursorShape.SizeFDiagCursor, 
        "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor, 
        "bl": Qt.CursorShape.SizeBDiagCursor, 
        "move": Qt.CursorShape.SizeAllCursor
    }
    
    _SELECTION_EDGE_CURSORS = {
        "tl": Qt.CursorShape.SizeFDiagCursor, 
        "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor, 
        "bl": Qt.CursorShape.SizeBDiagCursor,
        "t": Qt.CursorShape.SizeVerCursor, 
        "b": Qt.CursorShape.SizeVerCursor,
        "l": Qt.CursorShape.SizeHorCursor, 
        "r": Qt.CursorShape.SizeHorCursor
    }
    
    def __init__(self, auto_ocr_popup_manager=None, config_manager=None, clipboard_history_manager=None):
        super().__init__()
        self._auto_ocr_popup_manager = auto_ocr_popup_manager
        self._config_manager = config_manager  # 配置管理器引用
        self._clipboard_history_manager = clipboard_history_manager  # 工作台管理器引用
        
        # 当前编辑的历史条目 ID（用于继续编辑功能）
        self._editing_history_item_id: Optional[str] = None
        
        # 连接 OCR 面板的 ESC 键信号
        if self._auto_ocr_popup_manager is not None:
            self._auto_ocr_popup_manager.escape_requested.connect(self._force_exit)
        
        self._screenshot: Optional[QPixmap] = None
        self._cached_image: Optional[QImage] = None
        self._selecting = False
        self._selected = False
        self._is_closing = False  # 标志：窗口正在关闭，防止被意外恢复
        self._select_start = QPoint()
        self._select_end = QPoint()
        self._selection_rect = QRect()
        self._drawing = False
        self._draw_items: List[DrawItem] = []
        self._current_draw_points: List[QPoint] = []
        self._undo_stack: List[DrawItem] = []
        self._selected_item: Optional[DrawItem] = None
        self._hovered_item: Optional[DrawItem] = None  # 鼠标悬停的图形
        self._item_dragging = False
        self._item_resizing = False
        self._item_resize_edge = ""
        self._item_drag_start = QPoint()
        self._item_original_rect = QRect()
        self._current_tool = DrawTool.NONE
        self._current_color = QColor("#FFFF00")  # 默认黄色
        self._current_width_level = DEFAULT_LINE_WIDTH  # 粗细级别 1-10
        
        # 各工具独立的颜色配置（工具名 -> 颜色）
        # 默认值与 ToolColorsConfig.DEFAULT_COLORS 保持一致
        self._tool_colors = {
            "rect": "#FF0000",      # 矩形 - 红色
            "ellipse": "#FF0000",   # 椭圆/方块 - 红色
            "arrow": "#FF0000",     # 箭头 - 红色
            "line": "#FF0000",      # 直线 - 红色
            "pen": "#FF0000",       # 画笔 - 红色
            "marker": "#FFFF00",    # 高亮 - 黄色
            "text": "#FF0000",      # 文字 - 红色
            "mosaic": "#000000",    # 马赛克 - 黑色
            "step": "#FF0000",      # 步骤编号 - 红色
        }
        
        # 各工具独立的粗细配置（工具名 -> 粗细级别 1-10）
        # 默认值与 ToolWidthsConfig.DEFAULT_WIDTHS 保持一致
        self._tool_widths = {
            "rect": 2,       # 矩形
            "ellipse": 2,    # 椭圆/方块
            "arrow": 2,      # 箭头
            "line": 2,       # 直线
            "pen": 2,        # 画笔
            "marker": 5,     # 高亮 - 默认较粗
            "text": 3,       # 文字
            "mosaic": 5,     # 马赛克 - 默认较粗
            "step": 5,       # 步骤编号 - 默认中等大小
        }
        
        # 步骤编号计数器
        self._step_counter = 0
        
        self._resizing = False
        self._resize_edge = ""
        self._resize_start = QPoint()
        self._original_rect = QRect()
        self._device_pixel_ratio = 1.0
        self._toolbar: Optional[FloatingToolbar] = None
        self._side_toolbar: Optional[SideToolbar] = None
        self._size_label: Optional[SizeInfoLabel] = None
        self._toolbar_timer: Optional[QTimer] = None
        
        # 内联文字编辑器（替代 QLineEdit 输入框）
        # Requirements: 1.1, 2.1, 3.1
        self._inline_editor = InlineTextEditor()
        self._cursor_blink_timer: Optional[QTimer] = None  # 光标闪烁定时器
        
        # 性能优化组件
        self._cursor_manager = None  # 延迟初始化
        self._spatial_index = None   # 延迟初始化
        self._toolbar_manager = None # 延迟初始化
        self._paint_engine = None    # 延迟初始化 - 双缓冲绘制引擎
        self._idle_detector = None   # 延迟初始化 - 空闲检测器
        
        # 渲染优化：缓存常用画笔和画刷
        # Feature: performance-ui-optimization
        # Requirements: 2.2, 2.4
        self._cached_pens = {}       # 缓存画笔 {(color_name, width): QPen}
        self._cached_brushes = {}    # 缓存画刷 {color_name: QBrush}
        self._last_selection_rect = QRect()  # 上次选区矩形（用于脏区域计算）
        self._last_detection_rect = QRect()  # 上次检测矩形（用于脏区域计算）
        
        # 后台 OCR 管理器（用于高亮区域自动识别）
        self._background_ocr_manager = None  # 延迟初始化
        
        # 智能布局管理器（用于协调工具栏和OCR面板位置）
        self._smart_layout = None  # 延迟初始化
        
        # 截图状态管理器（用于保存和恢复截图状态）
        # Feature: screenshot-state-restore
        # Requirements: 1.1, 1.2
        self._state_manager = None  # 延迟初始化
        self._state_save_timer: Optional[QTimer] = None  # 延迟保存定时器
        
        # 窗口检测器（用于智能识别窗口边界）
        # Requirements: 1.1, 1.2, 2.1, 2.2
        self._window_detector: Optional[WindowDetector] = None
        self._detection_rect: Optional[QRect] = None  # 当前检测到的窗口边界
        self._window_detection_enabled = is_window_detection_available()  # 是否启用窗口检测
        self._last_detection_time: float = 0  # 上次检测时间（用于节流）
        self._detection_interval: float = 0.05  # 检测间隔（50ms）
        self._click_detection_rect: Optional[QRect] = None  # 点击时的检测结果
        self._click_start_pos: Optional[QPoint] = None  # 点击起始位置
        
        self._setup_ui()
        
        # 注册到全局置顶窗口管理器
        # Feature: emergency-esc-exit
        # Requirements: 1.1, 4.1
        TopmostWindowManager.instance().register_window(
            self, 
            window_type="OverlayScreenshot",
            can_receive_focus=True
        )
        
        # 安装事件过滤器，确保 ESC 键总是被处理
        # Feature: emergency-esc-exit
        # Requirements: 1.2, 1.3
        self.installEventFilter(self)
        
    def eventFilter(self, obj, event):
        """事件过滤器 - 确保 ESC 键总是被处理
        
        Feature: emergency-esc-exit
        Requirements: 1.2, 1.3
        
        即使在其他事件处理中出现问题，ESC 键也能触发强制退出。
        """
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._force_exit()
                return True
        return super().eventFilter(obj, event)
        
    def _setup_ui(self):
        # 窗口标志说明：
        # - FramelessWindowHint: 无边框窗口
        # - WindowStaysOnTopHint: 保持在最顶层
        # - Tool: 工具窗口，不在任务栏显示
        # 注意：不能使用 WindowDoesNotAcceptFocus，因为需要接收键盘输入
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled)  # 启用输入法支持（中文等）
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 启用强焦点策略，支持键盘输入
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 底部绘图工具栏（作为子控件）
        self._toolbar = FloatingToolbar(self)
        self._toolbar.toolSelected.connect(self._on_tool_selected)
        self._toolbar.recordingClicked.connect(self._recording)  # 录屏
        self._toolbar.drag_ended.connect(lambda pos: self._on_toolbar_dragged("bottom_toolbar", pos))
        self._toolbar.hide()
        
        # 右侧功能工具栏（作为子控件）
        self._side_toolbar = SideToolbar(self)
        self._side_toolbar.colorChanged.connect(self._on_color_changed)
        self._side_toolbar.widthChanged.connect(self._on_width_changed)
        self._side_toolbar.undoClicked.connect(self._undo)
        self._side_toolbar.redoClicked.connect(self._redo)
        self._side_toolbar.saveClicked.connect(self._save)
        self._side_toolbar.cancelClicked.connect(self._cancel)
        self._side_toolbar.ocrToggled.connect(self._on_ocr_toggled)  # OCR 开关切换
        self._side_toolbar.pinClicked.connect(self._pin)
        self._side_toolbar.ankiClicked.connect(self._anki)
        self._side_toolbar.drag_ended.connect(lambda pos: self._on_toolbar_dragged("side_toolbar", pos))
        self._side_toolbar.hide()
        
        # 光标闪烁定时器（用于内联文字编辑器）
        # Requirements: 3.1
        self._cursor_blink_timer = QTimer(self)
        self._cursor_blink_timer.timeout.connect(self._toggle_cursor_blink)
        self._cursor_blink_timer.setInterval(500)  # 500ms 闪烁间隔
        
        # 尺寸信息标签（作为子控件）
        self._size_label = SizeInfoLabel(self)
        self._size_label.hide()
        
        # 定时器确保工具栏保持可见
        self._toolbar_timer = QTimer(self)
        self._toolbar_timer.timeout.connect(self._ensure_toolbar_visible)
        self._toolbar_timer.setInterval(100)  # 每100ms检查一次
        
        # 状态保存延迟定时器
        # Feature: screenshot-state-restore
        # Requirements: 1.2
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.setInterval(500)  # 500ms 延迟
        self._state_save_timer.timeout.connect(self._do_save_state)
    
    def _init_state_manager(self):
        """延迟初始化状态管理器
        
        Feature: screenshot-state-restore
        Requirements: 1.1
        """
        if self._state_manager is None:
            try:
                from screenshot_tool.core.screenshot_state_manager import ScreenshotStateManager
                self._state_manager = ScreenshotStateManager()
                debug_log("截图状态管理器初始化成功", "STATE")
            except Exception as e:
                debug_log(f"截图状态管理器初始化失败: {e}", "STATE")
                self._state_manager = None
    
    def _schedule_save_state(self):
        """调度延迟保存状态
        
        Feature: screenshot-state-restore
        Requirements: 1.2
        """
        if self._state_save_timer:
            self._state_save_timer.start()
    
    def _do_save_state(self):
        """执行状态保存
        
        Feature: screenshot-state-restore
        Requirements: 1.1, 1.3
        """
        if not self._selected or self._selection_rect.isEmpty():
            return
        
        self._init_state_manager()
        if self._state_manager is None:
            return
        
        try:
            from screenshot_tool.core.screenshot_state_manager import ScreenshotState
            
            # 获取原始截图图像
            if self._screenshot is None:
                return
            image = self._screenshot.toImage()
            
            # 转换标注为可序列化格式
            annotations = [item.to_annotation_data() for item in self._draw_items]
            
            # 创建状态对象
            state = ScreenshotState(
                selection_rect=(
                    self._selection_rect.x(),
                    self._selection_rect.y(),
                    self._selection_rect.width(),
                    self._selection_rect.height(),
                ),
                annotations=annotations,
                screen_index=0,  # TODO: 支持多屏幕
            )
            
            # 保存状态
            self._state_manager.save_state(state, image, immediate=True)
            debug_log(f"截图状态已保存: {len(annotations)} 个标注", "STATE")
            
        except Exception as e:
            debug_log(f"保存截图状态失败: {e}", "STATE")
    
    def restore_from_state(self, state: 'ScreenshotState', image: QImage) -> bool:
        """从保存的状态恢复截图
        
        Feature: screenshot-state-restore
        Requirements: 2.2, 2.3
        
        Args:
            state: 截图状态
            image: 原始截图图像
            
        Returns:
            是否恢复成功
        """
        try:
            debug_log("=" * 60, "STATE-RESTORE")
            debug_log("开始恢复截图状态", "STATE-RESTORE")
            
            # 重置关闭标志，允许窗口正常显示
            self._is_closing = False
            
            # 恢复窗口状态（如果之前被 _close() 禁用/移动/透明化）
            if self.windowOpacity() < 1.0:
                self.setWindowOpacity(1.0)
            if not self.isEnabled():
                self.setEnabled(True)
            
            # 获取屏幕信息并设置窗口 geometry
            screens = QGuiApplication.screens()
            if not screens:
                debug_log("没有找到屏幕", "STATE-RESTORE")
                return False
            
            total_rect = QRect()
            for screen in screens:
                total_rect = total_rect.united(screen.geometry())
            
            primary_screen = QGuiApplication.primaryScreen()
            primary_dpr = primary_screen.devicePixelRatio() if primary_screen else 1.0
            
            # 保存屏幕信息
            self._total_rect = total_rect
            self._device_pixel_ratio = primary_dpr
            
            debug_log(f"屏幕区域: {total_rect.x()},{total_rect.y()},{total_rect.width()}x{total_rect.height()}, DPR={primary_dpr}", "STATE-RESTORE")
            
            # 设置窗口 geometry（覆盖整个屏幕区域）
            self.setGeometry(total_rect)
            
            # 设置截图图像
            self._screenshot = QPixmap.fromImage(image)
            self._screenshot.setDevicePixelRatio(primary_dpr)
            self._cached_image = image
            
            debug_log(f"截图图像尺寸: {self._screenshot.width()}x{self._screenshot.height()}", "STATE-RESTORE")
            
            # 恢复选区
            x, y, w, h = state.selection_rect
            self._selection_rect = QRect(x, y, w, h)
            self._select_start = QPoint(x, y)
            self._select_end = QPoint(x + w, y + h)
            self._selected = True
            self._selecting = False
            
            debug_log(f"恢复选区: x={x}, y={y}, w={w}, h={h}", "STATE-RESTORE")
            
            # 恢复标注
            self._draw_items.clear()
            self._undo_stack.clear()
            
            for ann_data in state.annotations:
                item = DrawItem.from_annotation_data(ann_data)
                self._draw_items.append(item)
            
            # 重置步骤计数器
            max_step = 0
            for item in self._draw_items:
                if item.tool == DrawTool.STEP and item.step_number > max_step:
                    max_step = item.step_number
            self._step_counter = max_step
            
            # 重置其他状态
            self._current_tool = DrawTool.NONE
            self._selected_item = None
            self._hovered_item = None
            self._detection_rect = None
            self._click_detection_rect = None
            
            # 重置内联文字编辑器状态
            if self._inline_editor.active:
                self._inline_editor.reset()
            if self._cursor_blink_timer and self._cursor_blink_timer.isActive():
                self._cursor_blink_timer.stop()
            
            # 预初始化绘制引擎的缓冲区
            if self._paint_engine is not None:
                self._paint_engine.initialize(total_rect.width(), total_rect.height(), primary_dpr)
            
            # 启动空闲检测
            self._start_idle_detection()
            
            # 显示窗口
            self.show()
            self.activateWindow()
            self.raise_()
            self.setFocus()
            
            # 使用 Windows API 强制将窗口置于最顶层
            self._force_topmost()
            
            # 设置窗口检测器的自身窗口句柄（用于排除检测）
            if self._window_detector is not None:
                try:
                    own_hwnd = int(self.winId())
                    self._window_detector.set_own_hwnd(own_hwnd)
                    debug_log(f"窗口检测器已设置自身句柄: {own_hwnd}", "STATE-RESTORE")
                except Exception as e:
                    debug_log(f"设置窗口句柄失败: {e}", "STATE-RESTORE")
            
            # 显示工具栏
            self._update_toolbar_position()
            
            # 触发重绘
            self.update()
            
            debug_log(f"截图状态已恢复: 选区 {w}x{h}, {len(self._draw_items)} 个标注", "STATE")
            debug_log(f"窗口 geometry: {self.geometry().x()},{self.geometry().y()},{self.geometry().width()}x{self.geometry().height()}", "STATE-RESTORE")
            debug_log(f"窗口可见: {self.isVisible()}", "STATE-RESTORE")
            return True
            
        except Exception as e:
            debug_log(f"恢复截图状态失败: {e}", "STATE")
            import traceback
            debug_log(traceback.format_exc(), "STATE")
            return False

    def restore_from_history(self, item_id: str) -> bool:
        """从工作台恢复截图编辑
        
        Feature: screenshot-state-restore
        Requirements: 2.2, 2.3
        
        Args:
            item_id: 历史条目 ID
            
        Returns:
            是否恢复成功
        """
        if self._clipboard_history_manager is None:
            debug_log("工作台管理器未设置，无法恢复", "HISTORY")
            return False
        
        try:
            debug_log(f"从历史恢复截图: {item_id}", "HISTORY")
            
            # 获取原始图像
            image = self._clipboard_history_manager.get_screenshot_image(item_id)
            if image is None:
                debug_log(f"无法获取工作台图像: {item_id}", "HISTORY")
                return False
            
            # 获取标注数据
            annotations_data = self._clipboard_history_manager.get_screenshot_annotations(item_id)
            
            # 获取选区
            selection_rect = self._clipboard_history_manager.get_screenshot_selection_rect(item_id)
            
            # 重置关闭标志
            self._is_closing = False
            
            # 恢复窗口状态
            if self.windowOpacity() < 1.0:
                self.setWindowOpacity(1.0)
            if not self.isEnabled():
                self.setEnabled(True)
            
            # 获取屏幕信息
            screens = QGuiApplication.screens()
            if not screens:
                debug_log("没有找到屏幕", "HISTORY")
                return False
            
            total_rect = QRect()
            for screen in screens:
                total_rect = total_rect.united(screen.geometry())
            
            primary_screen = QGuiApplication.primaryScreen()
            primary_dpr = primary_screen.devicePixelRatio() if primary_screen else 1.0
            
            # 保存屏幕信息
            self._total_rect = total_rect
            self._device_pixel_ratio = primary_dpr
            
            # 设置窗口 geometry
            self.setGeometry(total_rect)
            
            # 设置截图图像
            self._screenshot = QPixmap.fromImage(image)
            self._screenshot.setDevicePixelRatio(primary_dpr)
            self._cached_image = image
            
            debug_log(f"截图图像尺寸: {self._screenshot.width()}x{self._screenshot.height()}", "HISTORY")
            
            # 恢复选区
            if selection_rect:
                x, y, w, h = selection_rect
                self._selection_rect = QRect(x, y, w, h)
                self._select_start = QPoint(x, y)
                self._select_end = QPoint(x + w, y + h)
                self._selected = True
                self._selecting = False
                debug_log(f"恢复选区: x={x}, y={y}, w={w}, h={h}", "HISTORY")
            else:
                # 如果没有选区，使用整个图像
                self._selection_rect = QRect(0, 0, image.width(), image.height())
                self._select_start = QPoint(0, 0)
                self._select_end = QPoint(image.width(), image.height())
                self._selected = True
                self._selecting = False
            
            # 恢复标注
            self._draw_items.clear()
            self._undo_stack.clear()
            
            if annotations_data:
                from screenshot_tool.core.screenshot_state_manager import AnnotationData
                for ann_dict in annotations_data:
                    try:
                        ann_data = AnnotationData.from_dict(ann_dict)
                        item = DrawItem.from_annotation_data(ann_data)
                        self._draw_items.append(item)
                    except Exception as e:
                        debug_log(f"恢复标注失败: {e}", "HISTORY")
                        continue
                
                debug_log(f"恢复了 {len(self._draw_items)} 个标注", "HISTORY")
            
            # 重置步骤计数器
            max_step = 0
            for item in self._draw_items:
                if item.tool == DrawTool.STEP and item.step_number > max_step:
                    max_step = item.step_number
            self._step_counter = max_step
            
            # 保存正在编辑的历史条目 ID
            self._editing_history_item_id = item_id
            
            # 重置其他状态
            self._current_tool = DrawTool.NONE
            self._selected_item = None
            self._hovered_item = None
            self._detection_rect = None
            self._click_detection_rect = None
            
            # 重置内联文字编辑器状态
            if self._inline_editor.active:
                self._inline_editor.reset()
            if self._cursor_blink_timer and self._cursor_blink_timer.isActive():
                self._cursor_blink_timer.stop()
            
            # 预初始化绘制引擎的缓冲区
            if self._paint_engine is not None:
                self._paint_engine.initialize(total_rect.width(), total_rect.height(), primary_dpr)
            
            # 启动空闲检测
            self._start_idle_detection()
            
            # 显示窗口
            self.show()
            self.activateWindow()
            self.raise_()
            self.setFocus()
            
            # 使用 Windows API 强制将窗口置于最顶层
            self._force_topmost()
            
            # 设置窗口检测器的自身窗口句柄
            if self._window_detector is not None:
                try:
                    own_hwnd = int(self.winId())
                    self._window_detector.set_own_hwnd(own_hwnd)
                except Exception as e:
                    debug_log(f"设置窗口句柄失败: {e}", "HISTORY")
            
            # 显示工具栏
            self._update_toolbar_position()
            
            # 触发重绘
            self.update()
            
            debug_log(f"从历史恢复成功: {len(self._draw_items)} 个标注", "HISTORY")
            return True
            
        except Exception as e:
            debug_log(f"从历史恢复失败: {e}", "HISTORY")
            import traceback
            debug_log(traceback.format_exc(), "HISTORY")
            return False

    def _force_topmost(self):
        """使用 Windows API 强制将窗口置于最顶层
        
        添加超时保护，避免 Windows API 调用阻塞导致系统卡死。
        """
        import sys
        if sys.platform != 'win32':
            return
        
        try:
            import ctypes
            
            hwnd = int(self.winId())
            
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            SWP_ASYNCWINDOWPOS = 0x4000  # 异步执行，避免阻塞
            
            # 使用异步标志，避免阻塞
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_ASYNCWINDOWPOS
            )
            
            # SetForegroundWindow 可能会阻塞，用 try-except 包裹
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass  # 忽略前台窗口设置失败
            
            debug_log(f"已使用 Windows API 强制置顶窗口: {hwnd}", "INFO")
        except Exception as e:
            debug_log(f"强制置顶窗口失败: {e}", "ERROR")

    def start_capture(self):
        """开始截图"""
        # 开始测量覆盖层显示时间
        # Feature: extreme-performance-optimization
        # Requirements: 2.2
        overlay_start_time = time.perf_counter()
        
        debug_log("=" * 60, "START")
        debug_log("开始新的截图会话", "START")
        
        # 重置关闭标志，允许窗口正常显示
        self._is_closing = False
        
        # 恢复窗口状态（如果之前被 _close() 禁用/移动/透明化）
        if self.windowOpacity() < 1.0:
            self.setWindowOpacity(1.0)
        if not self.isEnabled():
            self.setEnabled(True)
        
        self._cached_image = None
        
        # 直接截取屏幕，不需要等待其他窗口
        # 截图覆盖层会通过 TOPMOST 属性覆盖在所有窗口上方
        self._capture_screens()
        if self._screenshot is None or self._screenshot.isNull():
            debug_log("截图失败，取消操作", "ERROR")
            self.screenshotCancelled.emit()
            return
        self._selecting = False
        self._selected = False
        self._select_start = QPoint()
        self._select_end = QPoint()
        self._selection_rect = QRect()
        # 立即清除窗口检测结果，避免上次截图的绿色高亮框残留
        self._detection_rect = None
        self._click_detection_rect = None
        self._draw_items.clear()
        self._undo_stack.clear()
        self._current_tool = DrawTool.NONE
        self._selected_item = None
        self._hovered_item = None  # 重置悬停状态
        self._step_counter = 0  # 重置编号计数器
        
        # 重置内联文字编辑器状态
        if self._inline_editor.active:
            self._inline_editor.reset()
        if self._cursor_blink_timer and self._cursor_blink_timer.isActive():
            self._cursor_blink_timer.stop()
        
        # 预初始化性能优化组件（避免首次使用时的延迟导入）
        # 使用 try-except 确保单个组件初始化失败不影响整体功能
        try:
            if self._cursor_manager is None:
                from screenshot_tool.core.cursor_manager import ThrottledCursorManager
                self._cursor_manager = ThrottledCursorManager()
            else:
                self._cursor_manager.reset()
        except (ImportError, AttributeError, RuntimeError) as e:
            debug_log(f"光标管理器初始化失败: {e}", "ERROR")
            self._cursor_manager = None
        
        try:
            if self._spatial_index is None:
                from screenshot_tool.core.spatial_index import SpatialIndex
                self._spatial_index = SpatialIndex(cell_size=50)
            else:
                self._spatial_index.clear()
        except (ImportError, AttributeError, RuntimeError) as e:
            debug_log(f"空间索引初始化失败: {e}", "ERROR")
            self._spatial_index = None
        
        try:
            if self._toolbar_manager is None:
                from screenshot_tool.core.toolbar_manager import CachedToolbarManager
                self._toolbar_manager = CachedToolbarManager()
            else:
                self._toolbar_manager.invalidate_cache()
        except (ImportError, AttributeError, RuntimeError) as e:
            debug_log(f"工具栏管理器初始化失败: {e}", "ERROR")
            self._toolbar_manager = None
        
        # 预初始化绘制引擎（避免首次 paintEvent 时的延迟）
        try:
            if self._paint_engine is None:
                from screenshot_tool.core.paint_engine import OptimizedPaintEngine
                self._paint_engine = OptimizedPaintEngine()
            else:
                self._paint_engine.reset()
        except (ImportError, AttributeError, RuntimeError) as e:
            debug_log(f"绘制引擎初始化失败: {e}", "ERROR")
            self._paint_engine = None
        
        # 重置智能布局管理器（清除手动定位标记）
        # Requirements: 5.1, 5.4
        if self._smart_layout is not None:
            self._smart_layout.reset_session()
        
        # 初始化窗口检测器
        # Requirements: 1.1, 2.1
        # 注意：_detection_rect 已在前面重置，这里只需初始化检测器
        if self._window_detection_enabled:
            if self._window_detector is None:
                self._window_detector = WindowDetector()
            self._window_detector.clear_cache()
            self._window_detector.set_enabled(True)
        
        # 启动空闲检测
        self._start_idle_detection()
        
        if self._toolbar:
            self._toolbar.hide()
            self._toolbar.deselect_all_tools()
        if self._side_toolbar:
            self._side_toolbar.hide()
        if self._size_label:
            self._size_label.hide()
        
        # 使用 show() 而不是 showFullScreen()，因为我们已经设置了正确的 geometry
        self.show()
        self.activateWindow()
        self.raise_()
        self.setFocus()  # 确保窗口获得键盘焦点
        
        # 使用 Windows API 强制将窗口置于最顶层
        self._force_topmost()
        
        # 设置窗口检测器的自身窗口句柄（用于排除检测）
        # Requirements: 1.1
        if self._window_detector is not None:
            try:
                own_hwnd = int(self.winId())
                self._window_detector.set_own_hwnd(own_hwnd)
                debug_log(f"窗口检测器已设置自身句柄: {own_hwnd}", "START")
                # 验证句柄是否正确（仅在 pywin32 可用时）
                if is_window_detection_available():
                    try:
                        import win32gui
                        title = win32gui.GetWindowText(own_hwnd)
                        rect = win32gui.GetWindowRect(own_hwnd)
                        debug_log(f"自身窗口验证: title='{title}', rect={rect}", "START")
                    except (ImportError, OSError, AttributeError) as e:
                        debug_log(f"验证自身窗口失败: {e}", "ERROR")
            except (ImportError, OSError, AttributeError) as e:
                debug_log(f"设置窗口句柄失败: {e}", "ERROR")
        
        # 工具栏在选区确定后才显示（不在截图开始时显示）
        # Requirements: 1.1, 1.2
        
        debug_log(f"窗口已显示，geometry: {self.geometry().x()},{self.geometry().y()},{self.geometry().width()}x{self.geometry().height()}", "START")
        
        # 记录覆盖层显示时间（从 start_capture 开始到窗口显示完成）
        # Feature: extreme-performance-optimization
        # Requirements: 2.2
        overlay_display_ms = (time.perf_counter() - overlay_start_time) * 1000
        PerformanceMonitor.record("overlay_display_internal", overlay_display_ms)
        debug_log(f"覆盖层内部显示耗时: {overlay_display_ms:.2f}ms", "PERF")
        
    def _capture_screens(self):
        try:
            debug_log("=" * 60, "CAPTURE")
            debug_log("开始截取屏幕", "CAPTURE")
            
            screens = QGuiApplication.screens()
            if not screens:
                debug_log("没有找到屏幕", "ERROR")
                return
            
            debug_log(f"检测到 {len(screens)} 个屏幕", "CAPTURE")
            
            total_rect = QRect()
            screen_info = []
            for i, screen in enumerate(screens):
                dpr = screen.devicePixelRatio()
                geo = screen.geometry()
                screen_info.append({'screen': screen, 'geometry': geo, 'dpr': dpr})
                total_rect = total_rect.united(geo)
                debug_log(f"屏幕 {i}: geometry={geo.x()},{geo.y()},{geo.width()}x{geo.height()}, DPR={dpr}", "CAPTURE")
            
            # 保存 total_rect 用于坐标转换
            self._total_rect = total_rect
            debug_log(f"合并后的总区域: {total_rect.x()},{total_rect.y()},{total_rect.width()}x{total_rect.height()}", "CAPTURE")
            
            primary_screen = QGuiApplication.primaryScreen()
            primary_dpr = primary_screen.devicePixelRatio() if primary_screen else 1.0
            debug_log(f"主屏幕 DPR: {primary_dpr}", "CAPTURE")
            
            phys_width = int(total_rect.width() * primary_dpr)
            phys_height = int(total_rect.height() * primary_dpr)
            debug_log(f"物理像素尺寸: {phys_width}x{phys_height}", "CAPTURE")
            
            if phys_width <= 0 or phys_height <= 0:
                debug_log("物理像素尺寸无效", "ERROR")
                return
            
            # 创建物理像素大小的 pixmap，设置 devicePixelRatio
            # 这样 Qt 在绘制时会正确处理逻辑像素到物理像素的映射
            self._screenshot = QPixmap(phys_width, phys_height)
            self._screenshot.setDevicePixelRatio(primary_dpr)
            self._screenshot.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(self._screenshot)
            if not painter.isActive():
                debug_log("无法创建 QPainter", "ERROR")
                self._screenshot = None
                return
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            for i, info in enumerate(screen_info):
                screen = info['screen']
                geo = info['geometry']
                pixmap = screen.grabWindow(0)
                if pixmap.isNull():
                    debug_log(f"屏幕 {i} 截图失败", "ERROR")
                    continue
                
                # 由于 _screenshot 设置了 DPR，绘制时使用逻辑坐标
                # 逻辑坐标 = 相对于 total_rect 的偏移
                log_x = geo.x() - total_rect.x()
                log_y = geo.y() - total_rect.y()
                log_w = geo.width()
                log_h = geo.height()
                
                debug_log(f"屏幕 {i} 截图: 逻辑位置=({log_x},{log_y}), 逻辑尺寸={log_w}x{log_h}, 原始pixmap尺寸={pixmap.width()}x{pixmap.height()}, pixmap DPR={pixmap.devicePixelRatio()}", "CAPTURE")
                
                # 绘制到目标位置（使用逻辑坐标，Qt 会自动处理 DPR）
                painter.drawPixmap(log_x, log_y, log_w, log_h, pixmap)
            painter.end()
            
            self.setGeometry(total_rect)
            self._device_pixel_ratio = primary_dpr
            
            # 预初始化绘制引擎的缓冲区（避免首次 paintEvent 时的延迟）
            if self._paint_engine is not None:
                self._paint_engine.initialize(total_rect.width(), total_rect.height(), primary_dpr)
            
            debug_log(f"窗口 geometry 设置为: {total_rect.x()},{total_rect.y()},{total_rect.width()}x{total_rect.height()}", "CAPTURE")
            debug_log(f"最终截图 pixmap 尺寸: {self._screenshot.width()}x{self._screenshot.height()}", "CAPTURE")
            debug_log("屏幕截取完成", "CAPTURE")
            
        except Exception as e:
            debug_log(f"截取屏幕失败: {e}", "ERROR")
            import traceback
            debug_log(traceback.format_exc(), "ERROR")
            print(f"截取屏幕失败: {e}")
            self._screenshot = None

    def paintEvent(self, event: QPaintEvent):
        if self._screenshot is None:
            return
        
        # 绘制引擎应该在 start_capture 中已经初始化
        # 这里只做防御性检查
        if self._paint_engine is None:
            self._paint_direct(event)
            return
        
        # 初始化缓冲区（传递设备像素比，创建物理像素大小的缓冲）
        self._paint_engine.initialize(self.width(), self.height(), self._device_pixel_ratio)
        
        # 获取缓冲
        buffer = self._paint_engine.get_buffer()
        if buffer is None:
            # 回退到直接绘制
            self._paint_direct(event)
            return
        
        # 在缓冲上绘制
        buffer_painter = self._paint_engine.begin_paint()
        if buffer_painter is None:
            self._paint_direct(event)
            return
        
        buffer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        buffer_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 开始新的标注帧（用于脏区域追踪）
        # Feature: performance-ui-optimization
        # Requirements: 2.4, 5.1
        self._paint_engine.begin_annotation_frame()
        
        # 绘制截图背景
        # _screenshot 和 buffer 都设置了 DPR=2，逻辑尺寸都是 1560x1040
        # 直接绘制即可，Qt 会正确处理
        buffer_painter.drawPixmap(0, 0, self._screenshot)
        
        # 绘制窗口检测高亮框（在选区开始前��示）
        # Requirements: 6.1, 6.2
        if self._detection_rect is not None and not self._selecting and not self._selected:
            self._draw_detection_highlight(buffer_painter)
        
        # 绘制遮罩（使用缓存）
        if self._selecting or self._selected:
            self._draw_mask_optimized(buffer_painter)
        
        # 绘制选区边框
        if self._selected or self._selecting:
            self._draw_selection_border(buffer_painter)
        
        # 绘制所有绘制项（带脏区域追踪）
        # Feature: performance-ui-optimization
        # Requirements: 2.4, 5.1
        for item in self._draw_items:
            # 跳过正在编辑的文字项（避免重叠显示）
            if self._inline_editor.active and item == self._inline_editor.editing_item:
                continue
            
            # 追踪标注项边界（用于脏区域计算）
            item_rect = item.get_bounding_rect()
            if not item_rect.isEmpty():
                self._paint_engine.track_annotation(item._id, item_rect, item.width or 2)
            
            self._draw_item(buffer_painter, item)
            # 显示选中或悬停图形的调整手柄
            if item == self._selected_item or item == self._hovered_item:
                self._draw_item_handles(buffer_painter, item)
        
        # 绘制当前正在绘制的项
        if self._drawing and self._current_draw_points:
            current_item = DrawItem(
                tool=self._current_tool, 
                color=self._current_color, 
                width=get_actual_width(self._current_width_level), 
                points=self._current_draw_points.copy()
            )
            self._draw_item(buffer_painter, current_item)
        
        # 绘制内联文字编辑器
        # Requirements: 1.5, 5.3
        self._draw_inline_editor(buffer_painter)
        
        # 绘制选区调整手柄
        if self._selected and not self._selected_item:
            self._draw_resize_handles(buffer_painter)
        
        self._paint_engine.end_paint(buffer_painter)
        
        # 将缓冲复制到屏幕
        screen_painter = QPainter(self)
        screen_painter.drawPixmap(0, 0, buffer)
        screen_painter.end()
    
    def _paint_direct(self, event: QPaintEvent):
        """直接绘制（回退模式）"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # 绘制截图背景，_screenshot 设置了 DPR，Qt 会正确处理
        painter.drawPixmap(0, 0, self._screenshot)
        # 绘制窗口检测高亮框（在选区开始前显示）
        # Requirements: 6.1, 6.2
        if self._detection_rect is not None and not self._selecting and not self._selected:
            self._draw_detection_highlight(painter)
        if self._selecting or self._selected:
            self._draw_mask(painter)
        if self._selected or self._selecting:
            self._draw_selection_border(painter)
        for item in self._draw_items:
            # 跳过正在编辑的文字项（避免重叠显示）
            if self._inline_editor.active and item == self._inline_editor.editing_item:
                continue
            self._draw_item(painter, item)
            # 显示选中或悬停图形的调整手柄
            if item == self._selected_item or item == self._hovered_item:
                self._draw_item_handles(painter, item)
        if self._drawing and self._current_draw_points:
            current_item = DrawItem(tool=self._current_tool, color=self._current_color, width=get_actual_width(self._current_width_level), points=self._current_draw_points.copy())
            self._draw_item(painter, current_item)
        # 绘制内联文字编辑器
        # Requirements: 1.5, 5.3
        self._draw_inline_editor(painter)
        # 始终显示选区调整手柄（只要有选区且没有选中绘制的图形）
        if self._selected and not self._selected_item:
            self._draw_resize_handles(painter)
    
    def _draw_mask_optimized(self, painter: QPainter):
        """使用缓存绘制遮罩"""
        rect = self._get_selection_rect()
        screen_rect = QRect(0, 0, self.width(), self.height())
        
        # 获取或创建遮罩缓存
        mask = self._paint_engine.get_or_create_mask(
            screen_rect,
            rect if not rect.isEmpty() else None,
            QColor(0, 0, 0, 100)
        )
        
        if mask:
            painter.drawPixmap(0, 0, mask)
        else:
            # 回退到直接绘制
            self._draw_mask(painter)

    def _draw_detection_highlight(self, painter: QPainter):
        """绘制窗口检测高亮框（Snipaste 风格：纯边框，无填充）

        Requirements: 6.1, 6.2
        """
        if self._detection_rect is None or self._detection_rect.isEmpty():
            return

        rect = self._detection_rect

        # Snipaste 风格：蓝色细边框，无填充，不遮挡窗口内容
        border_color = QColor(24, 144, 255)  # 蓝色 #1890FF（Ant Design 主色）
        pen = QPen(border_color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def _draw_mask(self, painter: QPainter):
        rect = self._get_selection_rect()
        if rect.isEmpty():
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
            return
        dark = QColor(0, 0, 0, 100)
        painter.fillRect(0, 0, self.width(), rect.top(), dark)
        painter.fillRect(0, rect.bottom() + 1, self.width(), self.height() - rect.bottom() - 1, dark)
        painter.fillRect(0, rect.top(), rect.left(), rect.height(), dark)
        painter.fillRect(rect.right() + 1, rect.top(), self.width() - rect.right() - 1, rect.height(), dark)

    def _draw_selection_border(self, painter: QPainter):
        rect = self._get_selection_rect()
        if rect.isEmpty():
            return
        painter.setPen(QPen(QColor("#4A90D9"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def _draw_resize_handles(self, painter: QPainter):
        rect = self._get_selection_rect()
        if rect.isEmpty():
            return
        # 增大手柄尺寸，更容易点击
        handle_size = 12
        half = handle_size // 2
        handles = [
            (rect.left() - half, rect.top() - half), (rect.right() - half, rect.top() - half),
            (rect.left() - half, rect.bottom() - half), (rect.right() - half, rect.bottom() - half),
            (rect.center().x() - half, rect.top() - half), (rect.center().x() - half, rect.bottom() - half),
            (rect.left() - half, rect.center().y() - half), (rect.right() - half, rect.center().y() - half),
        ]
        painter.setPen(QPen(QColor("#4A90D9"), 2))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for x, y in handles:
            painter.drawRect(int(x), int(y), handle_size, handle_size)

    def _draw_item_handles(self, painter: QPainter, item: DrawItem):
        rect = item.get_bounding_rect()
        if rect.isEmpty():
            return
        painter.setPen(QPen(QColor("#4A90D9"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        handle_size = 8
        half = handle_size // 2
        handles = [(rect.left() - half, rect.top() - half), (rect.right() - half, rect.top() - half),
                   (rect.left() - half, rect.bottom() - half), (rect.right() - half, rect.bottom() - half)]
        painter.setPen(QPen(QColor("#4A90D9"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for x, y in handles:
            painter.drawRect(int(x), int(y), handle_size, handle_size)

    # =====================================================
    # 渲染优化方法
    # Feature: performance-ui-optimization
    # Requirements: 2.2, 2.4
    # =====================================================
    
    def _get_cached_pen(self, color: QColor, width: int) -> QPen:
        """获取缓存的画笔，避免重复创建
        
        Feature: performance-ui-optimization
        Requirements: 2.2, 2.4
        
        Args:
            color: 画笔颜色
            width: 画笔宽度
            
        Returns:
            缓存的 QPen 对象
        """
        key = (color.name(), width)
        if key not in self._cached_pens:
            self._cached_pens[key] = QPen(color, width)
        return self._cached_pens[key]
    
    def _get_cached_brush(self, color: QColor) -> QBrush:
        """获取缓存的画刷，避免重复创建
        
        Feature: performance-ui-optimization
        Requirements: 2.2, 2.4
        
        Args:
            color: 画刷颜色
            
        Returns:
            缓存的 QBrush 对象
        """
        key = color.name()
        if key not in self._cached_brushes:
            self._cached_brushes[key] = QBrush(color)
        return self._cached_brushes[key]
    
    def _update_region(self, rect: QRect, margin: int = 5):
        """局部更新指定区域，避免全屏重绘
        
        Feature: performance-ui-optimization
        Requirements: 2.2, 2.4
        
        Args:
            rect: 需要更新的区域
            margin: 额外边距（用于包含边框等）
        """
        if rect.isEmpty():
            self.update()
            return
        
        # 扩展区域以包含边框和手柄
        expanded = rect.adjusted(-margin, -margin, margin, margin)
        
        # 确保区域在窗口范围内
        expanded = expanded.intersected(self.rect())
        
        if not expanded.isEmpty():
            self.update(expanded)
        else:
            self.update()
    
    def _update_selection_region(self, old_rect: QRect, new_rect: QRect):
        """更新选区变化的区域
        
        Feature: performance-ui-optimization
        Requirements: 2.2, 2.4
        
        Args:
            old_rect: 旧选区
            new_rect: 新选区
        """
        # 计算需要更新的区域（旧选区和新选区的并集）
        if old_rect.isEmpty() and new_rect.isEmpty():
            return
        
        margin = 15  # 包含边框和手柄
        
        if old_rect.isEmpty():
            self._update_region(new_rect, margin)
        elif new_rect.isEmpty():
            self._update_region(old_rect, margin)
        else:
            # 更新两个区域的并集
            combined = old_rect.united(new_rect)
            self._update_region(combined, margin)
    
    def _update_item_region(self, item: DrawItem, margin: int = 10):
        """更新绘制项所在区域
        
        Feature: performance-ui-optimization
        Requirements: 2.2, 2.4
        
        Args:
            item: 绘制项
            margin: 额外边距
        """
        rect = item.get_bounding_rect()
        self._update_region(rect, margin)
    
    def _clear_pen_brush_cache(self):
        """清除画笔和画刷缓存
        
        Feature: performance-ui-optimization
        """
        self._cached_pens.clear()
        self._cached_brushes.clear()

    def _draw_item(self, painter: QPainter, item: DrawItem, log_enabled: bool = False):
        """绘制单个绘制项
        
        Args:
            painter: QPainter对象
            item: 绘制项
            log_enabled: 是否启用调试日志（仅在保存图片时启用）
        """
        if not item.points:
            if log_enabled:
                debug_log(f"绘制项没有点，跳过", "DRAW")
            return
        if log_enabled:
            debug_log(f"开始绘制项: tool={item.tool}, color={item.color.name()}, width={item.width}", "DRAW")
        pen = QPen(item.color, item.width)
        painter.setPen(pen)
        if item.tool == DrawTool.RECT:
            if len(item.points) >= 2:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                rect = QRect(item.points[0], item.points[-1]).normalized()
                if log_enabled:
                    debug_log(f"绘制矩形: {rect.x()},{rect.y()},{rect.width()}x{rect.height()}", "DRAW")
                painter.drawRect(rect)
        elif item.tool == DrawTool.ELLIPSE:
            # 实心填充矩形（方块工具）
            if len(item.points) >= 2:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(item.color))
                rect = QRect(item.points[0], item.points[-1]).normalized()
                if log_enabled:
                    debug_log(f"绘制方块: {rect.x()},{rect.y()},{rect.width()}x{rect.height()}", "DRAW")
                painter.drawRect(rect)
        elif item.tool == DrawTool.LINE:
            if len(item.points) >= 2:
                if log_enabled:
                    debug_log(f"绘制直线: ({item.points[0].x()},{item.points[0].y()}) -> ({item.points[-1].x()},{item.points[-1].y()})", "DRAW")
                painter.drawLine(item.points[0], item.points[-1])
        elif item.tool == DrawTool.ARROW:
            if len(item.points) >= 2:
                if log_enabled:
                    debug_log(f"绘制箭头: ({item.points[0].x()},{item.points[0].y()}) -> ({item.points[-1].x()},{item.points[-1].y()})", "DRAW")
                self._draw_arrow(painter, item.points[0], item.points[-1], item.color, item.width)
        elif item.tool == DrawTool.PEN:
            if len(item.points) >= 2:
                if log_enabled:
                    debug_log(f"绘制画笔: {len(item.points)} 个点", "DRAW")
                for i in range(1, len(item.points)):
                    painter.drawLine(item.points[i-1], item.points[i])
        elif item.tool == DrawTool.MARKER:
            # 矩形高亮工具 - 绘制半透明填充矩形
            if len(item.points) >= 2:
                marker_color = QColor(item.color)
                marker_color.setAlpha(100)  # 半透明
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(marker_color))
                rect = QRect(item.points[0], item.points[-1]).normalized()
                if log_enabled:
                    debug_log(f"绘制高亮: {rect.x()},{rect.y()},{rect.width()}x{rect.height()}, color={marker_color.name()}, alpha={marker_color.alpha()}", "DRAW")
                painter.drawRect(rect)
        elif item.tool == DrawTool.MOSAIC:
            if len(item.points) >= 2:
                if log_enabled:
                    debug_log(f"绘制马赛克", "DRAW")
                self._draw_mosaic(painter, item.points)
        elif item.tool == DrawTool.TEXT:
            if len(item.points) >= 1 and item.text:
                # 绘制文字 - 字体大小由 width 决定
                # 兼容旧格式（width 存储粗细级别 1-10）和新格式（width 直接存储字体大小 pt）
                if item.width and item.width > 10:
                    # 新格式：width 直接是字体大小
                    font_size = item.width
                else:
                    # 旧格式：width 是粗细级别
                    font_size = get_text_font_size(item.width if item.width else 2)
                font = QFont(TEXT_FONT_FAMILY, font_size)
                font.setBold(True)
                painter.setFont(font)
                # 确保颜色有效
                color = item.color if item.color and item.color.isValid() else QColor("#FF0000")
                painter.setPen(QPen(color))
                # 使用基线位置绘制文字（与 _draw_inline_editor 保持一致）
                pos = item.points[0]
                if log_enabled:
                    debug_log(f"绘制文字: '{item.text}' at ({pos.x()},{pos.y()}), font_size={font_size}", "DRAW")
                painter.drawText(pos, item.text)
        elif item.tool == DrawTool.STEP:
            if len(item.points) >= 1 and item.step_number > 0:
                self._draw_step_number(painter, item.points[0], item.step_number, item.color, item.width)

    def _draw_step_number(self, painter: QPainter, center: QPoint, number: int, color: QColor, size: int):
        """绘制步骤编号 - 圆形背景 + 数字
        
        Args:
            painter: 绘图对象
            center: 圆心位置
            number: 步骤编号
            color: 背景颜色
            size: 圆的直径（由 width 决定），可能为 None
        """
        # 确保大小在合理范围内，安全处理 None 值
        size_val = size if size and size > 0 else 30
        diameter = max(20, min(100, size_val if size_val > 10 else 30))
        radius = diameter // 2
        
        # 确保颜色有效
        bg_color = color if color and color.isValid() else QColor("#FF0000")
        
        # 绘制圆形背景
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawEllipse(center, radius, radius)
        
        # 绘制白色数字
        font_size = int(diameter * 0.55)  # 字体大小约为直径的 55%
        font = QFont(TEXT_FONT_FAMILY, font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#FFFFFF")))
        
        # 使用 QRect 和对齐标志实现精确居中
        text = str(number)
        # 创建以圆心为中心的矩形区域
        text_rect = QRect(
            center.x() - radius,
            center.y() - radius,
            diameter,
            diameter
        )
        # 使用 Qt 的对齐功能绘制居中文字
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint, color: QColor, width: int):
        """绘制箭头 - 圆角线条 + 尖锐三角形箭头"""
        if start == end:
            return
        
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        
        angle = math.atan2(dy, dx)
        
        # 箭头三角形的大小（细长尖锐的箭头）
        arrow_length = max(12, width * 4)   # 箭头长度
        arrow_width = max(4, width * 1.2)   # 箭头宽度（较窄，形成尖锐效果）
        
        # 如果箭头太短，只绘制三角形，不绘制线条
        draw_line = length > arrow_length
        
        # 计算箭头三角形的三个顶点
        tip = end
        actual_arrow_length = min(arrow_length, length)
        base_center_x = end.x() - actual_arrow_length * math.cos(angle)
        base_center_y = end.y() - actual_arrow_length * math.sin(angle)
        
        # 箭头底边的两个端点（垂直于线条方向）
        perp_angle = angle + math.pi / 2
        actual_arrow_width = arrow_width * (actual_arrow_length / arrow_length) if arrow_length > 0 else arrow_width
        p1 = QPoint(
            int(base_center_x + actual_arrow_width * math.cos(perp_angle)),
            int(base_center_y + actual_arrow_width * math.sin(perp_angle))
        )
        p2 = QPoint(
            int(base_center_x - actual_arrow_width * math.cos(perp_angle)),
            int(base_center_y - actual_arrow_width * math.sin(perp_angle))
        )
        
        # 绘制圆角线条（仅当长度足够时）
        if draw_line:
            line_end = QPoint(int(base_center_x), int(base_center_y))
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)  # 圆角端点
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(start, line_end)
        
        # 绘制实心三角形箭头
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygon([tip, p1, p2]))

    # 马赛克常量
    MOSAIC_DEFAULT_BLOCK_SIZE = 10  # 默认块大小
    MOSAIC_MAX_BLOCKS = 10000       # 最大块数限制（性能保护）
    MOSAIC_SAMPLE_POINTS = 9        # 每块采样点数 (3x3)
    
    def _draw_mosaic(self, painter: QPainter, points: List[QPoint]):
        """绘制马赛克效果 - 使用区域平均采样避免条纹
        
        Args:
            painter: QPainter 绑定的绘图对象
            points: 马赛克区域的起止点列表
        """
        if not self._screenshot or len(points) < 2:
            return
        
        block_size = self.MOSAIC_DEFAULT_BLOCK_SIZE
        rect = QRect(points[0], points[-1]).normalized()
        
        # 获取并验证选区
        sel_rect = self._get_selection_rect()
        if sel_rect.isEmpty():
            return
        rect = rect.intersected(sel_rect)
        if rect.isEmpty():
            return
        
        # 获取并验证图像
        if self._cached_image is None:
            self._cached_image = self._screenshot.toImage()
        img = self._cached_image
        if img.isNull():
            return
        img_w, img_h = img.width(), img.height()
        if img_w <= 0 or img_h <= 0:
            return
        
        dpr = self._device_pixel_ratio
        
        # 动态调整块大小：大区域使用更大的块以保证性能
        total_blocks = (rect.width() // block_size + 1) * (rect.height() // block_size + 1)
        if total_blocks > self.MOSAIC_MAX_BLOCKS:
            block_size = max(block_size, int(math.sqrt(rect.width() * rect.height() / self.MOSAIC_MAX_BLOCKS)))
        
        # 采样步长：确保每块至少有 3x3 采样点
        sample_step = max(1, block_size // 3)
        
        for x in range(rect.left(), rect.right(), block_size):
            for y in range(rect.top(), rect.bottom(), block_size):
                block_rect = QRect(x, y, block_size, block_size).intersected(rect)
                if block_rect.isEmpty():
                    continue
                
                # 区域平均采样：取块内多个点的平均颜色
                r_sum, g_sum, b_sum, count = 0, 0, 0, 0
                for sx in range(block_rect.left(), block_rect.right() + 1, sample_step):
                    for sy in range(block_rect.top(), block_rect.bottom() + 1, sample_step):
                        px, py = int(sx * dpr), int(sy * dpr)
                        if 0 <= px < img_w and 0 <= py < img_h:
                            color = img.pixelColor(px, py)
                            r_sum += color.red()
                            g_sum += color.green()
                            b_sum += color.blue()
                            count += 1
                
                if count > 0:
                    avg_color = QColor(r_sum // count, g_sum // count, b_sum // count)
                    painter.fillRect(block_rect, avg_color)

    def _get_selection_rect(self) -> QRect:
        if self._selected:
            return self._selection_rect
        elif self._selecting:
            return QRect(self._select_start, self._select_end).normalized()
        return QRect()

    def _get_resize_edge(self, pos: QPoint) -> str:
        """获取鼠标位置对应的选区调整边缘
        
        Returns:
            边缘标识: tl/tr/bl/br (角落), t/b/l/r (边), move (内部), "" (外部)
        """
        rect = self._get_selection_rect()
        if rect.isEmpty():
            return ""
        
        margin = self.EDGE_MARGIN
        
        # 计算鼠标到各边的距离
        dist_left = abs(pos.x() - rect.left())
        dist_right = abs(pos.x() - rect.right())
        dist_top = abs(pos.y() - rect.top())
        dist_bottom = abs(pos.y() - rect.bottom())
        
        # 判断是否在水平和垂直方向的边缘范围内
        near_left = dist_left < margin
        near_right = dist_right < margin
        near_top = dist_top < margin
        near_bottom = dist_bottom < margin
        
        # 判断是否在矩形的水平和垂直范围内（包含边缘margin）
        in_horizontal = rect.left() - margin < pos.x() < rect.right() + margin
        in_vertical = rect.top() - margin < pos.y() < rect.bottom() + margin
        
        # 先检查四个角落（优先级最高）
        if near_left and near_top: return "tl"
        if near_right and near_top: return "tr"
        if near_left and near_bottom: return "bl"
        if near_right and near_bottom: return "br"
        
        # 再检查四条边（需要在对应方向的范围内）
        if near_top and in_horizontal: return "t"
        if near_bottom and in_horizontal: return "b"
        if near_left and in_vertical: return "l"
        if near_right and in_vertical: return "r"
        
        # 最后检查是否在选区内部
        if rect.contains(pos): return "move"
        
        return ""

    def _get_item_resize_edge(self, item: DrawItem, pos: QPoint) -> str:
        """获取鼠标位置对应的图形调整边缘"""
        rect = item.get_bounding_rect()
        if rect.isEmpty():
            return ""
        margin = self.EDGE_MARGIN
        if abs(pos.x() - rect.left()) < margin and abs(pos.y() - rect.top()) < margin: return "tl"
        if abs(pos.x() - rect.right()) < margin and abs(pos.y() - rect.top()) < margin: return "tr"
        if abs(pos.x() - rect.left()) < margin and abs(pos.y() - rect.bottom()) < margin: return "bl"
        if abs(pos.x() - rect.right()) < margin and abs(pos.y() - rect.bottom()) < margin: return "br"
        if rect.adjusted(-margin, -margin, margin, margin).contains(pos): return "move"
        return ""

    def _is_point_on_toolbar(self, pos: QPoint) -> bool:
        """检查点击位置是否在工具栏上
        
        用于避免在点击工具栏按钮时意外触发绘制操作（如 STEP 工具）。
        
        Args:
            pos: 鼠标位置（widget 坐标）
            
        Returns:
            bool: 如果点击在工具栏上返回 True
        """
        # 检查底部工具栏
        if self._toolbar and self._toolbar.isVisible():
            if self._toolbar.geometry().contains(pos):
                return True
        # 检查侧边工具栏
        if self._side_toolbar and self._side_toolbar.isVisible():
            if self._side_toolbar.geometry().contains(pos):
                return True
        return False

    def _update_window_detection(self, pos: QPoint):
        """更新窗口检测
        
        在选区开始前检测鼠标下方的窗口边界。
        使用节流机制避免频繁调用 Windows API。
        
        Args:
            pos: 鼠标位置（widget 坐标）
            
        Requirements: 1.1, 1.2, 1.3, 2.3
        """
        if self._window_detector is None:
            # 窗口检测器未初始化
            if self._detection_rect is not None:
                old_rect = self._detection_rect
                self._detection_rect = None
                # 使用局部更新而非全屏重绘
                # Feature: performance-ui-optimization
                self._update_region(old_rect, 5)
            return
        
        if not self._window_detector.is_enabled():
            # 窗口检测未启用，清除检测结果
            if self._detection_rect is not None:
                old_rect = self._detection_rect
                self._detection_rect = None
                # 使用局部更新而非全屏重绘
                self._update_region(old_rect, 5)
            return
        
        # 节流：限制检测频率
        current_time = time.time()
        if current_time - self._last_detection_time < self._detection_interval:
            return
        self._last_detection_time = current_time
        
        # 获取设备像素比（DPR）用于坐标转换
        # Windows API 返回物理像素坐标，Qt 使用逻辑坐标
        dpr = self.devicePixelRatio()
        
        # 将 widget 坐标转换为屏幕物理像素坐标
        # Qt 的 mapToGlobal 返回逻辑坐标，需要乘以 DPR 得到物理像素
        global_pos = self.mapToGlobal(pos)
        screen_x = int(global_pos.x() * dpr)
        screen_y = int(global_pos.y() * dpr)
        
        # 执行窗口检测（使用物理像素坐标）
        result = self._window_detector.detect_at(screen_x, screen_y)
        
        if result is not None and result.rect is not None:
            # Windows API 返回的是物理像素坐标，需要转换为逻辑坐标
            # 1. 将物理像素坐标除以 DPR 得到逻辑屏幕坐标
            logical_x = int(result.rect.x() / dpr)
            logical_y = int(result.rect.y() / dpr)
            logical_width = int(result.rect.width() / dpr)
            logical_height = int(result.rect.height() / dpr)
            
            # 2. 将逻辑屏幕坐标转换为 widget 坐标
            window_pos = self.mapFromGlobal(QPoint(logical_x, logical_y))
            detection_rect = QRect(
                window_pos.x(),
                window_pos.y(),
                logical_width,
                logical_height
            )
            
            # 只有检测结果变化时才更新
            if self._detection_rect != detection_rect:
                old_rect = self._detection_rect if self._detection_rect else QRect()
                self._detection_rect = detection_rect
                # 使用局部更新而非全屏重绘
                # Feature: performance-ui-optimization
                # Requirements: 2.2, 2.4
                self._update_selection_region(old_rect, detection_rect)
        else:
            # 没有检测到窗口
            if self._detection_rect is not None:
                old_rect = self._detection_rect
                self._detection_rect = None
                # 使用局部更新而非全屏重绘
                self._update_region(old_rect, 5)

    def _update_cursor(self, pos: QPoint):
        """根据鼠标位置更新光标样式（带节流优化）
        
        优先级：已绘制图形边缘 > 选区边缘 > OCR文字框 > 绘图工具 > 选区内部移动
        鼠标靠近已绘制图形时，自动高亮并显示调整光标
        """
        # 只有在选区已确定时才检测
        if not self._selected:
            self._set_cursor_throttled(Qt.CursorShape.CrossCursor)
            return
        
        # 检查是否靠近任何已绘制的图形（优先级最高，包括文字项）
        hovered_item = self._find_item_near(pos)
        if hovered_item:
            # 自动高亮靠近的图形
            if self._hovered_item != hovered_item:
                old_item = self._hovered_item
                self._hovered_item = hovered_item
                # 使用局部更新而非全屏重绘
                # Feature: performance-ui-optimization
                # Requirements: 2.2, 2.4
                if old_item:
                    self._update_item_region(old_item)
                self._update_item_region(hovered_item)
            
            # 所有绘制项（包括文字项）都使用相同的光标逻辑
            # 双击文字项才进入编辑模式
            edge = self._get_item_resize_edge(hovered_item, pos)
            if edge in self._ITEM_EDGE_CURSORS:
                self._set_cursor_throttled(self._ITEM_EDGE_CURSORS[edge])
                return
        else:
            # 清除高亮
            if self._hovered_item is not None:
                old_item = self._hovered_item
                self._hovered_item = None
                # 使用局部更新而非全屏重绘
                self._update_item_region(old_item)
            
        # 检查是否在已选中图形的边缘
        if self._selected_item:
            edge = self._get_item_resize_edge(self._selected_item, pos)
            if edge in self._ITEM_EDGE_CURSORS:
                self._set_cursor_throttled(self._ITEM_EDGE_CURSORS[edge])
                return
        
        # 检查是否在选区边缘
        edge = self._get_resize_edge(pos)
        
        # 在边缘时，无论是否有绘图工具，都显示调整光标
        if edge in self._SELECTION_EDGE_CURSORS:
            self._set_cursor_throttled(self._SELECTION_EDGE_CURSORS[edge])
            return
        
        # 在选区内部
        if edge == "move":
            # 如果有绘图工具，显示十字光标用于绘制
            if self._current_tool != DrawTool.NONE:
                self._set_cursor_throttled(Qt.CursorShape.CrossCursor)
            else:
                # 没有绘图工具时，显示移动光标
                self._set_cursor_throttled(Qt.CursorShape.SizeAllCursor)
            return
        
        # 默认十字光标（选区外部）
        self._set_cursor_throttled(Qt.CursorShape.CrossCursor)
    
    def _set_cursor_throttled(self, cursor: Qt.CursorShape, force: bool = False):
        """节流设置光标（减少 setCursor 调用）"""
        # 光标管理器应该在 start_capture 中已经初始化
        # 这里只做防御性检查
        if self._cursor_manager is None:
            self.setCursor(cursor)
            return
        
        self._cursor_manager.update_cursor(cursor, self, force)
    
    def _find_item_near(self, pos: QPoint) -> Optional[DrawItem]:
        """查找鼠标位置附近的图形（用于悬停高亮，使用空间索引优化）"""
        # 如果没有绘制项，直接返回
        if not self._draw_items:
            return None
        
        margin = self.EDGE_MARGIN
        
        # 使用空间索引加速查找（如果可用）
        if self._spatial_index is not None:
            nearby_items = self._spatial_index.query(pos, radius=margin)
            # 按绘制顺序反向检查（后绘制的优先）
            for item in reversed(self._draw_items):
                if item in nearby_items:
                    # 使用 contains_point 进行精确检测（直线/箭头使用点到线段距离）
                    if item.contains_point(pos, margin):
                        return item
            return None
        
        # 回退到线性搜索
        for item in reversed(self._draw_items):
            # 使用 contains_point 进行精确检测
            if item.contains_point(pos, margin):
                return item
        return None
    
    def _rebuild_spatial_index(self):
        """重建空间索引"""
        # 空间索引应该在 start_capture 中已经初始化
        # 这里只做防御性检查
        if self._spatial_index is None:
            return
        
        self._spatial_index.clear()
        
        for item in self._draw_items:
            rect = item.get_bounding_rect()
            if not rect.isEmpty():
                self._spatial_index.insert(item, rect)
    
    def _add_item_to_index(self, item: DrawItem):
        """添加绘制项到空间索引"""
        # 空间索引应该在 start_capture 中已经初始化
        # 如果为空则跳过（不影响功能，只是性能优化）
        if self._spatial_index is None:
            return
        
        rect = item.get_bounding_rect()
        if not rect.isEmpty():
            self._spatial_index.insert(item, rect)
    
    def _remove_item_from_index(self, item: DrawItem):
        """从空间索引移除绘制项"""
        if self._spatial_index is not None:
            self._spatial_index.remove(item)
    
    def _update_item_in_index(self, item: DrawItem):
        """更新绘制项在空间索引中的边界框（用于大小改变后）"""
        if self._spatial_index is not None:
            self._spatial_index.remove(item)
            rect = item.get_bounding_rect()
            if not rect.isEmpty():
                self._spatial_index.insert(item, rect)

    def _find_item_at(self, pos: QPoint) -> Optional[DrawItem]:
        for item in reversed(self._draw_items):
            if item.contains_point(pos):
                debug_log(f"_find_item_at: 找到图形 tool={item.tool} at pos=({pos.x()},{pos.y()})", "MOUSE")
                return item
        debug_log(f"_find_item_at: 未找到图形 at pos=({pos.x()},{pos.y()}), items={len(self._draw_items)}", "MOUSE")
        return None
    
    def _find_text_item_at(self, pos: QPoint) -> Optional[DrawItem]:
        """查找指定位置的文字项
        
        Args:
            pos: 鼠标位置
            
        Returns:
            找到的文字项，如果没有则返回 None
        
        Requirements: 2.1
        """
        for item in reversed(self._draw_items):
            if item.tool == DrawTool.TEXT and item.contains_point(pos):
                return item
        return None


    def mousePressEvent(self, event: QMouseEvent):
        pos = event.pos()
        
        debug_log(f"mousePressEvent: pos=({pos.x()},{pos.y()}), inline_active={self._inline_editor.active}, tool={self._current_tool}", "MOUSE")
        
        # 如果内联编辑器激活，先完成当前编辑
        if self._inline_editor.active:
            # 检查是否点击了已有的 Text_Item（切换编辑目标）
            if self._current_tool == DrawTool.TEXT:
                clicked_text_item = self._find_text_item_at(pos)
                if clicked_text_item and clicked_text_item != self._inline_editor.editing_item:
                    # 保存当前编辑，切换到新的文字项
                    self._finish_text_input(save=True)
                    self._start_text_input(clicked_text_item.points[0], clicked_text_item)
                    return
            # 点击其他位置，完成当前编辑
            self._finish_text_input(save=True)
            # 如果是文字工具且点击在选区内的空白区域，立即开始新的文字输入
            if self._current_tool == DrawTool.TEXT:
                target_item = self._find_item_at(pos)
                if target_item is None and self._selected:
                    # 检查是否在选区内
                    edge = self._get_resize_edge(pos)
                    if edge == "move":
                        # 点击选区内空白区域，立即开始新输入
                        self._start_text_input(pos)
                        return
            # 继续处理点击事件（选中其他绘制项等）
        
        if event.button() == Qt.MouseButton.RightButton:
            # 检查是否有模态对话框，如果有则忽略右键
            try:
                from screenshot_tool.core.modal_dialog_detector import ModalDialogDetector
                if ModalDialogDetector.is_modal_dialog_active():
                    debug_log("右键点击: 检测到模态对话框，忽略", "MOUSE")
                    return
            except ImportError:
                pass
            
            debug_log(f"右键点击: selected_item={self._selected_item is not None}, selected={self._selected}, draw_items={len(self._draw_items)}", "MOUSE")
            if self._selected_item:
                # 取消选中当前绘制项
                debug_log("右键: 取消选中当前绘制项", "MOUSE")
                self._selected_item = None
                self._hovered_item = None
                self.update()
            elif self._selected:
                # 已有选区时的右键行为：撤销绘图操作
                if self._draw_items:
                    # 有绘制操作，执行撤销
                    debug_log("右键: 有绘制操作，执行撤销", "MOUSE")
                    self._undo()
                else:
                    # 没有任何绘图操作，直接退出截图（同时关闭识别面板，与ESC行为一致）
                    debug_log("右键: 没有绘制操作，退出截图和识别面板", "MOUSE")
                    self._cancel(close_ocr_panel=True)
            else:
                # 没有选区，直接退出（关闭识别面板）
                debug_log("右键: 没有选区，直接退出", "MOUSE")
                self._cancel(close_ocr_panel=True)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        if self._selected_item:
            edge = self._get_item_resize_edge(self._selected_item, pos)
            if edge == "move":
                self._item_dragging = True
                self._item_drag_start = pos
                self._item_original_rect = self._selected_item.get_bounding_rect()
                return
            elif edge in ("tl", "tr", "bl", "br"):
                self._item_resizing = True
                self._item_resize_edge = edge
                self._item_drag_start = pos
                self._item_original_rect = self._selected_item.get_bounding_rect()
                return
            # 点击位置不在选中项的操作区域，稍后决定是否清空选中项
        
        # 检查是否点击了其他图形（即使有绘图工具也可以操作）
        # 如果 _hovered_item 为空，也尝试查找点击位置的图形
        # 排除已选中的项，避免重复检查
        target_item = self._hovered_item or self._find_item_at(pos)
        if target_item and target_item is self._selected_item:
            target_item = None  # 已在上面检查过，不需要重复处理
        debug_log(f"检查点击图形: pos=({pos.x()},{pos.y()}), hovered={self._hovered_item is not None}, target={target_item is not None}, tool={self._current_tool}", "MOUSE")
        if target_item and self._selected:
            edge = self._get_item_resize_edge(target_item, pos)
            debug_log(f"找到目标图形: tool={target_item.tool}, edge={edge}", "MOUSE")
            if edge in ("tl", "tr", "bl", "br", "move"):
                # 选中图形并开始操作
                self._selected_item = target_item
                self._hovered_item = target_item  # 同步更新 _hovered_item
                self._sync_selected_item_properties()  # 同步选中图形的属性到UI
                if edge == "move":
                    self._item_dragging = True
                    self._item_drag_start = pos
                    self._item_original_rect = self._selected_item.get_bounding_rect()
                else:
                    self._item_resizing = True
                    self._item_resize_edge = edge
                    self._item_drag_start = pos
                    self._item_original_rect = self._selected_item.get_bounding_rect()
                debug_log(f"开始操作图形: edge={edge}", "MOUSE")
                return
        
        # 点击位置既不在选中项操作区域，也不在其他图形操作区域，清空选中项
        if self._selected_item:
            self._selected_item = None
        
        # 优先检查选区边缘调整（即使有绘图工具选中也可以调整选区）
        if self._selected:
            edge = self._get_resize_edge(pos)
            debug_log(f"mousePressEvent: pos=({pos.x()},{pos.y()}), edge='{edge}', tool={self._current_tool}", "MOUSE")
            
            # 如果点击在边缘或角落，进行选区调整（优先级最高）
            if edge in ("tl", "tr", "bl", "br", "t", "b", "l", "r"):
                debug_log(f"开始调整选区边缘: {edge}", "MOUSE")
                self._resizing = True
                self._resize_edge = edge
                self._resize_start = pos
                self._original_rect = self._selection_rect.normalized()
                return
            
            # 如果在选区内部
            if edge == "move":
                # 如果有绘图工具，开始绘制
                if self._current_tool != DrawTool.NONE:
                    # 先检查是否点击在工具栏上，避免点击按钮时意外触发绘制
                    if self._is_point_on_toolbar(pos):
                        return
                    # 文字工具特殊处理：只在空白区域开始新输入
                    # 点击已有文字项会被前面的 clicked_item 逻辑处理（选中并拖动）
                    # 双击文字项才进入编辑模式（在 mouseDoubleClickEvent 中处理）
                    if self._current_tool == DrawTool.TEXT:
                        # 开始新的文字输入（此时已确认没有点击到任何绘制项）
                        self._start_text_input(pos)
                        return
                    # 步骤编号工具：单击即创建
                    if self._current_tool == DrawTool.STEP:
                        self._create_step_number(pos)
                        return
                    debug_log(f"开始绘制: tool={self._current_tool}", "MOUSE")
                    self._drawing = True
                    self._current_draw_points = [pos]
                    return
                else:
                    # 没有绘图工具，移动选区
                    debug_log("开始移动选区", "MOUSE")
                    self._resizing = True
                    self._resize_edge = edge
                    self._resize_start = pos
                    self._original_rect = self._selection_rect.normalized()
                    return
        
        # 保存窗口检测结果，用于判断是单击还是拖动
        # 单击时使用检测结果，拖动时让用户自由选择
        self._click_detection_rect = self._detection_rect
        self._click_start_pos = pos
        
        self._selecting = True
        self._selected = False
        self._select_start = pos
        self._select_end = pos
        # 清除检测结果（开始选择时隐藏高亮框）
        self._detection_rect = None
        # 停止工具栏定时器（开始新选区时）
        if self._toolbar_timer and self._toolbar_timer.isActive():
            self._toolbar_timer.stop()
        # 隐藏两个工具栏
        if self._toolbar: 
            self._toolbar.hide()
        if self._side_toolbar:
            self._side_toolbar.hide()
        self._draw_items.clear()
        self._undo_stack.clear()
        self._selected_item = None
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()
        
        # 记录用户活动（用于空闲检测）
        self._record_user_activity()
        
        if self._item_dragging and self._selected_item:
            delta = pos - self._item_drag_start
            # 获取旧边界用于局部更新
            old_rect = self._selected_item.get_bounding_rect()
            # 使用 move_by 移动图形，而不是 resize
            # 计算相对于上一次位置的增量
            self._selected_item.move_by(delta)
            self._item_drag_start = pos  # 更新起始点，避免累积
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            new_rect = self._selected_item.get_bounding_rect()
            
            # 追踪标注项移动（用于脏区域计算）
            if self._paint_engine is not None:
                self._paint_engine.track_annotation_moved(
                    self._selected_item._id, old_rect, new_rect, 
                    self._selected_item.width or 2
                )
            
            self._update_selection_region(old_rect, new_rect)
            return
        if self._item_resizing and self._selected_item:
            old_rect = self._selected_item.get_bounding_rect()
            self._resize_item(pos)
            # 使用局部更新而非全屏重绘
            new_rect = self._selected_item.get_bounding_rect()
            
            # 追踪标注项缩放（用于脏区域计算）
            # Feature: performance-ui-optimization
            # Requirements: 2.4, 5.1
            if self._paint_engine is not None:
                self._paint_engine.track_annotation_resized(
                    self._selected_item._id, old_rect, new_rect,
                    self._selected_item.width or 2
                )
            
            self._update_selection_region(old_rect, new_rect)
            return
        if self._drawing:
            # 计算需要更新的区域
            if len(self._current_draw_points) > 0:
                last_point = self._current_draw_points[-1]
                start_point = self._current_draw_points[0]
                
                # 对于矩形、椭圆、直线、箭头、高亮等形状工具，需要更新整个形状区域
                # 因为预览时显示的是起点到当前点的形状，而不是轨迹线
                if self._current_tool in (DrawTool.RECT, DrawTool.ELLIPSE, DrawTool.LINE, 
                                          DrawTool.ARROW, DrawTool.MARKER, DrawTool.MOSAIC):
                    # 计算旧形状区域（起点到上一个点）
                    old_min_x = min(start_point.x(), last_point.x())
                    old_max_x = max(start_point.x(), last_point.x())
                    old_min_y = min(start_point.y(), last_point.y())
                    old_max_y = max(start_point.y(), last_point.y())
                    
                    # 计算新形状区域（起点到当前点）
                    new_min_x = min(start_point.x(), pos.x())
                    new_max_x = max(start_point.x(), pos.x())
                    new_min_y = min(start_point.y(), pos.y())
                    new_max_y = max(start_point.y(), pos.y())
                    
                    # 合并新旧区域
                    draw_rect = QRect(
                        min(old_min_x, new_min_x),
                        min(old_min_y, new_min_y),
                        max(old_max_x, new_max_x) - min(old_min_x, new_min_x) + 1,
                        max(old_max_y, new_max_y) - min(old_min_y, new_min_y) + 1
                    )
                else:
                    # 画笔工具：只更新上一个点到当前点的区域
                    min_x = min(last_point.x(), pos.x())
                    max_x = max(last_point.x(), pos.x())
                    min_y = min(last_point.y(), pos.y())
                    max_y = max(last_point.y(), pos.y())
                    draw_rect = QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
                
                # 追踪绘制笔画（用于脏区域计算）
                # Feature: performance-ui-optimization
                # Requirements: 2.4, 5.1
                if self._paint_engine is not None:
                    line_width = get_actual_width(self._current_width_level)
                    self._paint_engine.track_drawing_stroke(last_point, pos, line_width)
            else:
                draw_rect = QRect(pos.x(), pos.y(), 1, 1)
            self._current_draw_points.append(pos)
            # 使用局部更新，margin 包含线条宽度
            self._update_region(draw_rect, get_actual_width(self._current_width_level) + 5)
            return
        if self._resizing:
            old_rect = self._get_selection_rect()
            self._resize_selection(pos)
            self._update_toolbar_position()
            self._update_size_label()
            # 使用局部更新而非全屏重绘
            new_rect = self._get_selection_rect()
            self._update_selection_region(old_rect, new_rect)
            return
        if self._selecting:
            old_rect = self._get_selection_rect()
            self._select_end = pos
            self._update_size_label()
            # 使用局部更新而非全屏重绘
            new_rect = self._get_selection_rect()
            self._update_selection_region(old_rect, new_rect)
            return
        
        # 窗口检测：在选区开始前检测鼠标下方的窗口
        # Requirements: 1.1, 1.2, 1.3, 2.3
        if not self._selected and not self._selecting:
            self._update_window_detection(pos)
        
        self._update_cursor(pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        if self._item_dragging or self._item_resizing:
            self._item_dragging = False
            self._item_resizing = False
            self._item_resize_edge = ""
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            if self._selected_item:
                self._update_item_region(self._selected_item)
            return
        if self._drawing:
            self._drawing = False
            if len(self._current_draw_points) >= 2:
                item = DrawItem(tool=self._current_tool, color=QColor(self._current_color), width=get_actual_width(self._current_width_level), points=self._current_draw_points.copy())
                self._draw_items.append(item)
                self._undo_stack.clear()
                # 标记绘制项区域为脏区域
                if self._paint_engine is not None:
                    item_rect = item.get_bounding_rect()
                    if not item_rect.isEmpty():
                        self._paint_engine.mark_dirty(item_rect.adjusted(-5, -5, 5, 5))
                # 添加到空间索引
                self._add_item_to_index(item)
                # 高亮工具不再实时触发OCR，改为点击Anki按钮时统一识别
                # 这样可以避免单词被分割识别的问题
                # 不选中刚绘制的图形，保持工具可以继续绘制
                
                # 触发状态保存
                # Feature: screenshot-state-restore
                # Requirements: 1.2
                self._schedule_save_state()
                
                # 使用局部更新而非全屏重绘
                self._update_item_region(item)
            self._current_draw_points.clear()
            # 确保工具栏保持可见（复用方法避免代码重复）
            self._ensure_toolbar_visible()
            return
        if self._resizing:
            self._resizing = False
            self._resize_edge = ""
            # 选区调整完成后，重新触发后台OCR
            if self._selected:
                self._emit_selection_ready()
            return
        if self._selecting:
            self._selecting = False
            pos = event.position().toPoint()
            rect = QRect(self._select_start, self._select_end).normalized()
            
            # 判断是单击还是拖动：如果移动距离小于阈值，认为是单击
            is_click = False
            if self._click_start_pos is not None:
                delta = pos - self._click_start_pos
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    is_click = True
            
            # 单击且有检测结果时，使用检测结果作为选区
            if is_click and self._click_detection_rect is not None and not self._click_detection_rect.isEmpty():
                debug_log(f"单击使用窗口检测结果: {self._click_detection_rect.x()},{self._click_detection_rect.y()},{self._click_detection_rect.width()}x{self._click_detection_rect.height()}", "SELECT")
                self._selected = True
                self._selection_rect = self._click_detection_rect
                self._select_start = self._click_detection_rect.topLeft()
                self._select_end = self._click_detection_rect.bottomRight()
                self._click_detection_rect = None
                self._click_start_pos = None
                self._show_toolbar()
                self._update_size_label()
                # 根据配置决定是否自动切换到高亮工具
                if self._toolbar and self._config_manager and self._config_manager.config.auto_select_highlight:
                    self._toolbar.select_tool(DrawTool.MARKER)
                self._emit_selection_ready()
                # 触发状态保存
                # Feature: screenshot-state-restore
                # Requirements: 1.1
                self._schedule_save_state()
                self.update()
                return
            
            # 清除点击相关状态
            self._click_detection_rect = None
            self._click_start_pos = None
            
            debug_log("=" * 60, "SELECT")
            debug_log(f"选区创建完成", "SELECT")
            debug_log(f"起点: ({self._select_start.x()}, {self._select_start.y()})", "SELECT")
            debug_log(f"终点: ({self._select_end.x()}, {self._select_end.y()})", "SELECT")
            debug_log(f"选区 (widget坐标): x={rect.x()}, y={rect.y()}, w={rect.width()}, h={rect.height()}", "SELECT")
            
            # 记录全局坐标
            global_start = self.mapToGlobal(self._select_start)
            global_end = self.mapToGlobal(self._select_end)
            debug_log(f"起点 (全局坐标): ({global_start.x()}, {global_start.y()})", "SELECT")
            debug_log(f"终点 (全局坐标): ({global_end.x()}, {global_end.y()})", "SELECT")
            
            if rect.width() > 10 and rect.height() > 10:
                self._selected = True
                self._selection_rect = rect
                debug_log(f"选区有效，已保存", "SELECT")
                self._show_toolbar()
                self._update_size_label()
                # 选区确定后，根据配置决定是否自动切换到高亮工具
                if self._toolbar and self._config_manager and self._config_manager.config.auto_select_highlight:
                    self._toolbar.select_tool(DrawTool.MARKER)
                # 选区确定后，自动触发后台OCR预处理
                self._emit_selection_ready()
                # 触发状态保存
                # Feature: screenshot-state-restore
                # Requirements: 1.1
                self._schedule_save_state()
            else:
                self._selected = False
                debug_log(f"选区太小，已忽略", "SELECT")
                if self._size_label: self._size_label.hide()
            self.update()

    def _resize_item(self, pos: QPoint):
        if not self._selected_item:
            return
        old_rect = self._item_original_rect
        new_rect = QRect(old_rect)
        if self._item_resize_edge == "tl": new_rect.setTopLeft(pos)
        elif self._item_resize_edge == "tr": new_rect.setTopRight(pos)
        elif self._item_resize_edge == "bl": new_rect.setBottomLeft(pos)
        elif self._item_resize_edge == "br": new_rect.setBottomRight(pos)
        new_rect = new_rect.normalized()
        if new_rect.width() >= 10 and new_rect.height() >= 10:
            self._selected_item.resize(old_rect, new_rect)
            self._item_original_rect = new_rect
            
            # 文字项：同步更新工具栏粗细显示（与滚轮缩放逻辑一致）
            if self._selected_item.tool == DrawTool.TEXT:
                new_font_size = self._get_text_item_font_size(self._selected_item)
                self._current_width_level = font_size_to_width_level(new_font_size)
                if self._side_toolbar:
                    self._side_toolbar.update_width(self._current_width_level)
            # 步骤编号：同步更新工具栏粗细显示
            elif self._selected_item.tool == DrawTool.STEP:
                new_diameter = self._selected_item.width
                if new_diameter and new_diameter > 0:
                    self._current_width_level = get_step_level_from_diameter(new_diameter)
                    if self._side_toolbar:
                        self._side_toolbar.update_width(self._current_width_level)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击事件处理
        
        - 双击 Text_Item 进入编辑模式（无需选中文字工具）
        - 双击选区内部复制截图
        
        Requirements: 2.5
        """
        pos = event.pos()
        
        # 检查是否双击了 Text_Item（无需选中文字工具）
        if self._selected:
            text_item = self._find_text_item_at(pos)
            if text_item:
                # 进入编辑模式
                self._start_text_input(text_item.points[0], text_item)
                return
            
            # 双击选区内部复制截图
            self._copy()

    def _resize_selection(self, pos: QPoint):
        old_rect = QRect(self._selection_rect) if self._selection_rect else QRect()
        rect = QRect(self._original_rect)
        delta = pos - self._resize_start
        if self._resize_edge == "move": rect.translate(delta)
        elif self._resize_edge == "tl": rect.setTopLeft(rect.topLeft() + delta)
        elif self._resize_edge == "tr": rect.setTopRight(rect.topRight() + delta)
        elif self._resize_edge == "bl": rect.setBottomLeft(rect.bottomLeft() + delta)
        elif self._resize_edge == "br": rect.setBottomRight(rect.bottomRight() + delta)
        elif self._resize_edge == "t": rect.setTop(rect.top() + delta.y())
        elif self._resize_edge == "b": rect.setBottom(rect.bottom() + delta.y())
        elif self._resize_edge == "l": rect.setLeft(rect.left() + delta.x())
        elif self._resize_edge == "r": rect.setRight(rect.right() + delta.x())
        if rect.width() >= 10 and rect.height() >= 10:
            self._selection_rect = rect.normalized()
            # 标记选区变化的脏区域
            if self._paint_engine is not None:
                self._paint_engine.mark_selection_changed(old_rect, self._selection_rect)

    def _show_toolbar_at_default_position(self):
        """在默认位置显示工具栏（无选区时）
        
        底部工具栏：屏幕底部居中
        侧边工具栏：屏幕右侧居中
        """
        screen_w = self.width()
        screen_h = self.height()
        margin = 20
        
        # 底部工具栏：屏幕底部居中
        if self._toolbar:
            self._toolbar.adjustSize()
            toolbar_w = self._toolbar.sizeHint().width()
            toolbar_h = self._toolbar.sizeHint().height()
            x = (screen_w - toolbar_w) // 2
            y = screen_h - toolbar_h - margin
            self._toolbar.move(x, y)
            self._toolbar.show()
            self._toolbar.raise_()
        
        # 侧边工具栏：屏幕右侧居中
        if self._side_toolbar:
            self._side_toolbar.adjustSize()
            side_w = self._side_toolbar.sizeHint().width()
            side_h = self._side_toolbar.sizeHint().height()
            x = screen_w - side_w - margin
            y = (screen_h - side_h) // 2
            self._side_toolbar.move(x, y)
            self._side_toolbar.show()
            self._side_toolbar.raise_()
        
        # 确保主窗口保持键盘焦点
        self.setFocus()

    def _init_smart_layout(self):
        """初始化智能布局管理器
        
        Requirements: 4.6, 5.2, 5.3
        """
        if self._smart_layout is not None:
            return
        
        from screenshot_tool.core.smart_layout_manager import SmartLayoutManager
        
        self._smart_layout = SmartLayoutManager(
            QRect(0, 0, self.width(), self.height())
        )
        
        # 注册工具栏组件
        if self._toolbar:
            self._smart_layout.register_component(
                "bottom_toolbar",
                self._toolbar.sizeHint(),
                preferred_side="bottom"
            )
        
        if self._side_toolbar:
            self._smart_layout.register_component(
                "side_toolbar",
                self._side_toolbar.sizeHint(),
                preferred_side="right"
            )
    
    def _on_toolbar_dragged(self, name: str, pos: QPoint):
        """工具栏被拖动后的回调
        
        Args:
            name: 组件名称 ("bottom_toolbar" 或 "side_toolbar")
            pos: 拖动后的位置
            
        Requirements: 4.5, 4.6, 5.2
        """
        # 确保智能布局管理器已初始化
        self._init_smart_layout()
        
        if self._smart_layout is None:
            return
        
        # 获取组件尺寸
        if name == "bottom_toolbar" and self._toolbar:
            size = self._toolbar.sizeHint()
            widget = self._toolbar
        elif name == "side_toolbar" and self._side_toolbar:
            size = self._side_toolbar.sizeHint()
            widget = self._side_toolbar
        else:
            return
        
        # 限制在屏幕内
        clamped_pos = self._smart_layout.clamp_to_screen(pos, size)
        
        # 更新布局管理器中的位置
        self._smart_layout.update_component_position(name, clamped_pos)
        self._smart_layout.mark_manually_positioned(name)
        
        # 移动组件到限制后的位置
        widget.move(clamped_pos)
        
        debug_log(f"工具栏 {name} 被拖动到 ({clamped_pos.x()}, {clamped_pos.y()})，已标记为手动定位", "LAYOUT")

    def _show_toolbar(self):
        """显示工具栏 - 只在选区确定后调用
        
        使用智能布局管理器计算位置，避免组件重叠。
        如果组件已被手动定位，则保持其位置不变。
        
        Requirements: 1.3, 1.4, 2.1
        """
        if not self._selected:
            return  # 选区未确定，不显示
        
        # 初始化智能布局管理器
        self._init_smart_layout()
        
        # 使用智能布局管理器计算位置
        if self._smart_layout:
            self._smart_layout.set_screen_rect(QRect(0, 0, self.width(), self.height()))
            self._smart_layout.set_selection_rect(self._get_selection_rect())
            
            # 更新组件尺寸
            if self._toolbar:
                self._smart_layout.update_component_size("bottom_toolbar", self._toolbar.sizeHint())
            if self._side_toolbar:
                self._smart_layout.update_component_size("side_toolbar", self._side_toolbar.sizeHint())
            
            # 计算所有组件位置
            positions = self._smart_layout.calculate_all_positions()
            
            # 应用位置
            if "side_toolbar" in positions and self._side_toolbar:
                self._side_toolbar.move(positions["side_toolbar"])
            if "bottom_toolbar" in positions and self._toolbar:
                self._toolbar.move(positions["bottom_toolbar"])
        else:
            # 回退到原有的位置计算逻辑
            self._update_toolbar_position()
        
        # 显示工具栏
        if self._toolbar:
            self._toolbar.show()
            self._toolbar.raise_()
        if self._side_toolbar:
            self._side_toolbar.show()
            self._side_toolbar.raise_()
        
        # 确保主窗口保持键盘焦点
        self.setFocus()
        # 启动定时器确保工具栏保持可见
        if self._toolbar_timer and not self._toolbar_timer.isActive():
            self._toolbar_timer.start()
    
    def _ensure_toolbar_visible(self):
        """确保工具栏保持可见"""
        if not (self._selected and self.isVisible()):
            return
        if self._toolbar:
            if not self._toolbar.isVisible():
                self._toolbar.show()
            self._toolbar.raise_()
        if self._side_toolbar:
            if not self._side_toolbar.isVisible():
                self._side_toolbar.show()
            self._side_toolbar.raise_()

    def _update_toolbar_position(self, force: bool = False):
        """更新工具栏位置，确保底部工具栏和侧边栏不重叠（带节流优化）"""
        rect = self._get_selection_rect()
        if rect.isEmpty():
            return
        
        # 工具栏管理器应该在 start_capture 中已经初始化
        # 这里只做防御性检查和屏幕尺寸设置
        if self._toolbar_manager is None:
            return
        
        # 确保屏幕尺寸已设置
        self._toolbar_manager.set_screen_rect(QRect(0, 0, self.width(), self.height()))
        
        # 节流检查（除非强制更新）- 使用 QTimer 的时间戳避免导入 time
        if not force:
            from PySide6.QtCore import QDateTime
            now = QDateTime.currentMSecsSinceEpoch()
            if hasattr(self, '_last_toolbar_update') and now - self._last_toolbar_update < 50:
                return
            self._last_toolbar_update = now
        
        # 获取工具栏尺寸
        toolbar_h = self._toolbar.sizeHint().height() if self._toolbar else 0
        toolbar_w = self._toolbar.sizeHint().width() if self._toolbar else 0
        side_h = self._side_toolbar.sizeHint().height() if self._side_toolbar else 0
        side_w = self._side_toolbar.sizeHint().width() if self._side_toolbar else 0
        
        # 计算侧边栏位置
        sx, sy, side_on_right = self._calc_side_toolbar_position(rect, side_w, side_h)
        if self._side_toolbar:
            # 作为子控件，直接使用本地坐标
            self._side_toolbar.move(sx, sy)
            self._side_toolbar.raise_()
        
        # 计算底部工具栏位置（考虑侧边栏避免重叠）
        if self._toolbar:
            x, y = self._calc_bottom_toolbar_position(
                rect, toolbar_w, toolbar_h, 
                sx, sy, side_w, side_h, side_on_right
            )
            # 作为子控件，直接使用本地坐标
            self._toolbar.move(x, y)
            self._toolbar.raise_()
    
    def _calc_side_toolbar_position(self, rect: QRect, side_w: int, side_h: int) -> tuple:
        """
        计算侧边栏位置
        
        Args:
            rect: 选区矩形
            side_w: 侧边栏宽度
            side_h: 侧边栏高度
        
        Returns:
            (x, y, is_on_right): 位置坐标和是否在右侧的标记
        """
        # 边界检查
        if side_w <= 0 or side_h <= 0:
            return rect.right() + 8, rect.top(), True
        
        side_on_right = True
        margin = 8
        
        # 计算可用空间
        space_right = max(0, self.width() - rect.right() - margin)
        space_left = max(0, rect.left() - margin)
        
        # 优先放在选区右侧外部
        if space_right >= side_w:
            sx = rect.right() + margin
            side_on_right = True
        # 其次放在选区左侧外部
        elif space_left >= side_w:
            sx = rect.left() - side_w - margin
            side_on_right = False
        # 如果两侧都放不下，选择空间较大的一侧，贴边显示
        elif space_right >= space_left:
            sx = max(rect.right() + margin, self.width() - side_w)
            side_on_right = True
        else:
            sx = max(0, rect.left() - side_w - margin)
            side_on_right = False
        
        # 确保不超出屏幕边界
        sx = max(0, min(sx, self.width() - side_w))
        
        # 垂直位置：与选区顶部对齐
        sy = rect.top()
        
        # 垂直方向确保不超出边界
        if sy + side_h > self.height():
            sy = max(0, self.height() - side_h - margin)
        if sy < 0:
            sy = margin
        
        return sx, sy, side_on_right
    
    def _calc_bottom_toolbar_position(
        self, rect: QRect, toolbar_w: int, toolbar_h: int,
        sx: int, sy: int, side_w: int, side_h: int, side_on_right: bool
    ) -> tuple:
        """
        计算底部工具栏位置，避免与侧边栏重叠
        
        Args:
            rect: 选区矩形
            toolbar_w: 工具栏宽度
            toolbar_h: 工具栏高度
            sx, sy: 侧边栏位置
            side_w, side_h: 侧边栏尺寸
            side_on_right: 侧边栏是否在右侧
        
        Returns:
            (x, y): 位置坐标
        """
        # 边界检查
        if toolbar_w <= 0 or toolbar_h <= 0:
            return rect.left(), rect.bottom() + 8
        
        margin = 8
        
        # 计算垂直位置
        space_below = max(0, self.height() - rect.bottom() - margin)
        space_above = max(0, rect.top() - margin)
        
        # 优先放在选区下方
        if space_below >= toolbar_h:
            y = rect.bottom() + margin
        # 其次放在选区上方
        elif space_above >= toolbar_h:
            y = rect.top() - toolbar_h - margin
        # 都放不下，选择空间较大的一侧
        elif space_below >= space_above:
            y = max(rect.bottom() + margin, self.height() - toolbar_h)
        else:
            y = max(0, rect.top() - toolbar_h - margin)
        
        # 确保不超出屏幕边界
        y = max(0, min(y, self.height() - toolbar_h))
        
        # 计算水平位置：与选区左侧对齐
        x = rect.left()
        
        # 确保不超出右边界
        if x + toolbar_w > self.width():
            x = max(0, self.width() - toolbar_w - margin)
        if x < 0:
            x = margin
        
        # 检查是否与侧边栏重叠并调整
        if self._side_toolbar and side_w > 0 and side_h > 0:
            toolbar_bottom = y + toolbar_h
            side_bottom = sy + side_h
            toolbar_right = x + toolbar_w
            side_right = sx + side_w
            
            # 检查是否有重叠（矩形相交）
            has_overlap = not (
                toolbar_right <= sx or  # 底部工具栏在侧边栏左侧
                x >= side_right or      # 底部工具栏在侧边栏右侧
                toolbar_bottom <= sy or # 底部工具栏在侧边栏上方
                y >= side_bottom        # 底部工具栏在侧边栏下方
            )
            
            if has_overlap:
                # 计算各方向的避让空间
                space_left_of_side = sx - margin  # 侧边栏左侧可用空间
                space_right_of_side = self.width() - side_right - margin  # 侧边栏右侧可用空间
                space_below_side = self.height() - side_bottom - margin  # 侧边栏下方可用空间
                space_above_side = sy - margin  # 侧边栏上方可用空间
                
                # 尝试水平方向避让
                if side_on_right:
                    # 侧边栏在右侧，底部工具栏向左移动避让
                    new_x = sx - toolbar_w - margin
                    if new_x >= 0:
                        x = new_x
                    elif space_below_side >= toolbar_h:
                        # 左侧空间不够，移到侧边栏下方
                        y = side_bottom + margin
                        x = rect.left()
                        if x + toolbar_w > self.width():
                            x = max(0, self.width() - toolbar_w - margin)
                    elif space_above_side >= toolbar_h:
                        # 移到侧边栏上方
                        y = sy - toolbar_h - margin
                        x = rect.left()
                        if x + toolbar_w > self.width():
                            x = max(0, self.width() - toolbar_w - margin)
                    else:
                        # 都放不下，将底部工具栏放在侧边栏左侧，即使超出屏幕也要避免重叠
                        x = max(0, sx - toolbar_w - margin)
                else:
                    # 侧边栏在左侧，底部工具栏向右移动避让
                    new_x = side_right + margin
                    if new_x + toolbar_w <= self.width():
                        x = new_x
                    elif space_below_side >= toolbar_h:
                        # 右侧空间不够，移到侧边栏下方
                        y = side_bottom + margin
                        x = rect.left()
                        if x < side_right + margin:
                            x = side_right + margin
                    elif space_above_side >= toolbar_h:
                        # 移到侧边栏上方
                        y = sy - toolbar_h - margin
                        x = rect.left()
                    else:
                        # 都放不下，将底部工具栏放在侧边栏右侧
                        x = min(side_right + margin, self.width() - toolbar_w)
        
        # 最终边界检查，确保工具栏完全在屏幕内
        x = max(0, min(x, self.width() - toolbar_w))
        y = max(0, min(y, self.height() - toolbar_h))
        
        return x, y

    def _update_size_label(self):
        if not self._size_label:
            return
        rect = self._get_selection_rect()
        if rect.isEmpty():
            self._size_label.hide()
            return
        
        # 先设置内容，再获取尺寸
        self._size_label.set_info(rect.x(), rect.y(), rect.width(), rect.height())
        
        # 获取标签实际尺寸
        label_height = self._size_label.sizeHint().height()
        label_width = self._size_label.sizeHint().width()
        screen_height = self.height()
        screen_width = self.width()
        margin = 8
        
        # 获取侧边工具栏信息
        side_w = self._side_toolbar.sizeHint().width() if self._side_toolbar else 0
        side_h = self._side_toolbar.sizeHint().height() if self._side_toolbar else 0
        
        # 计算侧边栏位置
        if side_w > 0 and side_h > 0:
            sx, sy, side_on_right = self._calc_side_toolbar_position(rect, side_w, side_h)
        else:
            sx, sy, side_on_right = rect.right() + margin, rect.top(), True
        
        # 计算 x 位置：说明文字始终在侧边栏的外侧
        if side_on_right:
            # 侧边栏在右侧，说明文字显示在侧边栏右侧外侧
            x = sx + side_w + margin
            if x + label_width > screen_width:
                # 右侧空间不足，显示在选区左上角外侧
                x = rect.left() - label_width - margin
                if x < 0:
                    x = rect.left()
        else:
            # 侧边栏在左侧，说明文字显示在侧边栏左侧外侧
            x = sx - label_width - margin
            if x < 0:
                # 左侧空间不足，显示在选区右上角外侧
                x = rect.right() + margin
                if x + label_width > screen_width:
                    x = rect.right() - label_width
        
        # 计算 y 位置：与侧边栏顶部对齐
        y = sy
        
        # 确保不超出屏幕边界
        if y + label_height > screen_height:
            y = screen_height - label_height - margin
        if y < 0:
            y = margin
        
        # 作为子控件，直接使用本地坐标
        self._size_label.move(x, y)
        self._size_label.raise_()
        self._size_label.show()


    def keyPressEvent(self, event: QKeyEvent):
        # 如果内联编辑器激活，优先处理文字编辑键盘事件
        # Requirements: 1.2, 1.3, 1.4
        if self._inline_editor.active:
            self._handle_text_key(event)
            return
        
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Delete:
            if self._selected_item and self._selected_item in self._draw_items:
                # 追踪标注项被删除（用于脏区域计算）
                # Feature: performance-ui-optimization
                # Requirements: 2.4, 5.1
                if self._paint_engine is not None:
                    self._paint_engine.track_annotation_removed(self._selected_item._id)
                
                item_rect = self._selected_item.get_bounding_rect()
                self._draw_items.remove(self._selected_item)
                self._undo_stack.append(self._selected_item)
                self._selected_item = None
                
                # 使用局部更新而非全屏重绘
                if not item_rect.isEmpty():
                    self._update_region(item_rect, 15)
                else:
                    self.update()
            return
        if key == Qt.Key.Key_Escape:
            # ESC 强制退出截图页面和 OCR 面板（紧急退出键）
            self._force_exit()
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C: self._copy(); return
            if key == Qt.Key.Key_S: self._save(); return
            if key == Qt.Key.Key_Z: self._undo(); return
            if key == Qt.Key.Key_Y: self._redo(); return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._copy()
            return
        # Tab 键切换窗口检测功能
        # Requirements: 4.1, 4.2, 4.3
        if key == Qt.Key.Key_Tab:
            self._toggle_window_detection()
            return
        tool_keys = {Qt.Key.Key_R: DrawTool.RECT, Qt.Key.Key_E: DrawTool.ELLIPSE, Qt.Key.Key_A: DrawTool.ARROW,
                     Qt.Key.Key_L: DrawTool.LINE, Qt.Key.Key_P: DrawTool.PEN, Qt.Key.Key_M: DrawTool.MARKER,
                     Qt.Key.Key_T: DrawTool.TEXT, Qt.Key.Key_B: DrawTool.MOSAIC, Qt.Key.Key_I: DrawTool.STEP}
        if key in tool_keys:
            self._on_tool_selected(tool_keys[key])

    def inputMethodEvent(self, event: QInputMethodEvent):
        """处理输入法事件（支持中文等 IME 输入）
        
        输入法输入分为两个阶段：
        1. preeditString: 正在输入的候选文字（如拼音）
        2. commitString: 确认输入的最终文字
        """
        if not self._inline_editor.active:
            event.ignore()
            return
        
        commit_string = event.commitString()
        if commit_string:
            # 有确认的文字，插入到编辑器
            self._insert_text(commit_string)
        
        # 注意：preeditString 是输入法候选状态的文字（如拼音）
        # 这里暂不处理 preedit，只处理最终确认的文字
        # 如果需要显示候选文字，可以在这里添加处理
        
        event.accept()
        self.update()

    def _get_text_item_font_size(self, item: DrawItem) -> int:
        """获取文字项的字体大小
        
        兼容旧格式（width 存储粗细级别 1-10）和新格式（width 直接存储字体大小 pt）
        """
        if not item or item.tool != DrawTool.TEXT or not item.width or item.width <= 0:
            return get_text_font_size(self._current_width_level)
        # 如果 width <= 10，认为是旧的粗细级别格式
        if item.width <= 10:
            return get_text_font_size(item.width)
        # 否则 width 直接是字体大小
        return item.width

    def wheelEvent(self, event: QWheelEvent):
        """鼠标滚轮事件 - 调整线条粗细级别，或调整选中/悬停图形的大小
        
        对于文字项，滚轮会调整字体大小（每次 ±2pt）
        悬停的图形（显示四角手柄）也可以直接用滚轮调整，无需先点击选中
        """
        if not self._selected:
            return
        
        # 获取滚轮滚动方向
        delta = event.angleDelta().y()
        if delta == 0:
            return
        
        step = 2 if delta > 0 else -2
        
        # 如果正在编辑文字，滚轮调整编辑中的字体大小
        if self._inline_editor.active:
            old_size = self._inline_editor.font_size
            new_size = max(TEXT_FONT_SIZE_MIN, min(TEXT_FONT_SIZE_MAX, old_size + step))
            
            if new_size != old_size:
                self._inline_editor.font_size = new_size
                # 同步更新粗细级别（用于侧边栏显示）
                self._current_width_level = font_size_to_width_level(new_size)
                if self._side_toolbar:
                    self._side_toolbar.update_width(self._current_width_level)
                self.update()
            event.accept()
            return
        
        # 实时检测鼠标位置下的图形（确保悬停时滚轮能直接操作）
        mouse_pos = event.position().toPoint()
        item_under_cursor = self._find_item_near(mouse_pos)

        # 确定目标图形：优先鼠标下的图形，其次已选中的
        target_item = item_under_cursor or self._selected_item

        # 调试日志
        debug_log(f"wheelEvent: mouse_pos=({mouse_pos.x()},{mouse_pos.y()}), item_under_cursor={item_under_cursor}, target_item={target_item}, selected_item={self._selected_item}", "WHEEL")
        if target_item:
            debug_log(f"wheelEvent: target_item.tool={target_item.tool}, target_item.width={target_item.width}", "WHEEL")

        # 如果目标是文字项，滚轮调整字体大小
        if target_item and target_item.tool == DrawTool.TEXT:
            current_font_size = self._get_text_item_font_size(target_item)
            new_font_size = max(TEXT_FONT_SIZE_MIN, min(TEXT_FONT_SIZE_MAX, current_font_size + step))
            
            if new_font_size != current_font_size:
                # 直接存储字体大小到 width
                target_item.width = new_font_size
                # 字体大小改变后，边界框也会改变，需要更新空间索引
                self._update_item_in_index(target_item)
                # 同步更新粗细级别（用于侧边栏显示）
                self._current_width_level = font_size_to_width_level(new_font_size)
                if self._side_toolbar:
                    self._side_toolbar.update_width(self._current_width_level)
                self.update()
            event.accept()
            return
        
        # 如果目标是步骤编号，滚轮调整圆的大小
        if target_item and target_item.tool == DrawTool.STEP:
            # 步骤编号的 width 存储圆的直径
            current_diameter = target_item.width if target_item.width and target_item.width > 10 else 30
            # 每次调整 5 像素
            size_step = 5 if delta > 0 else -5
            new_diameter = max(20, min(100, current_diameter + size_step))
            
            if new_diameter != current_diameter:
                target_item.width = new_diameter
                # 大小改变后，边界框也会改变，需要更新空间索引
                self._update_item_in_index(target_item)
                # 同步更新粗细级别（用于侧边栏显示）
                # 将直径转换回粗细级别：diameter = 20 + (level - 1) * 5
                new_level = max(1, min(10, (new_diameter - 20) // 5 + 1))
                self._current_width_level = new_level
                if self._side_toolbar:
                    self._side_toolbar.update_width(self._current_width_level)
                self.update()
            event.accept()
            return
        
        # 其他图形：调整线条粗细
        old_level = self._current_width_level
        if delta > 0:
            self._current_width_level = min(self._current_width_level + 1, 10)
        else:
            self._current_width_level = max(self._current_width_level - 1, 1)
        
        # 只有粗细真正改变时才更新
        if self._current_width_level != old_level:
            actual_width = get_actual_width(self._current_width_level)
            
            # 如果有目标图形（选中或悬停），实时调整其线条粗细
            if target_item:
                target_item.width = actual_width
                self.update()
            
            # 更新侧边栏
            if self._side_toolbar:
                self._side_toolbar.update_width(self._current_width_level)
        
        event.accept()

    def _on_tool_selected(self, tool: DrawTool):
        # 切换工具时，如果内联编辑器激活，先完成输入
        if self._inline_editor.active:
            self._finish_text_input(save=True)
        
        self._current_tool = tool
        self._selected_item = None
        
        # 切换工具时加载该工具保存的颜色和粗细
        if tool != DrawTool.NONE:
            tool_name = tool.value  # 获取工具名称字符串
            # 恢复颜色
            if tool_name in self._tool_colors:
                saved_color = self._tool_colors[tool_name]
                self._current_color = QColor(saved_color)
                # 更新侧边栏颜色显示
                if self._side_toolbar:
                    self._side_toolbar.update_color(self._current_color)
            # 恢复粗细
            if tool_name in self._tool_widths:
                saved_width = self._tool_widths[tool_name]
                self._current_width_level = saved_width
                # 更新侧边栏粗细显示
                if self._side_toolbar:
                    self._side_toolbar.update_width(self._current_width_level)
            # 文字工具使用普通箭头光标，其他工具使用十字光标
            if tool == DrawTool.TEXT:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 确保工具栏保持可见（复用 _ensure_toolbar_visible 避免代码重复）
        self._ensure_toolbar_visible()
        self.update()

    def _on_color_changed(self, color: QColor):
        self._current_color = color
        if self._side_toolbar:
            self._side_toolbar.update_color(color)
        
        # 如果有选中的图形，实时调整其颜色
        if self._selected_item:
            self._selected_item.color = QColor(color)
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            self._update_item_region(self._selected_item)
        
        # 如果内联编辑器激活，实时更新颜色
        if self._inline_editor.active:
            self._inline_editor.color = QColor(color)
            # 使用局部更新
            if self._inline_editor.position:
                text_rect = QRect(self._inline_editor.position.x(), 
                                  self._inline_editor.position.y() - 30,
                                  200, 50)
                self._update_region(text_rect, 10)
        
        # 保存当前工具的颜色
        if self._current_tool != DrawTool.NONE:
            tool_name = self._current_tool.value
            if tool_name in self._tool_colors:
                self._tool_colors[tool_name] = color.name()
                # 发送工具颜色改变信号（用于保存配置）
                self.toolColorChanged.emit(tool_name, color.name())
        
        # 发送通用颜色改变信号（兼容旧逻辑）
        self.colorChanged.emit(color.name())
    
    def set_draw_color(self, color_hex: str):
        """设置绘制颜色（从配置加载时调用，兼容旧配置）"""
        if not color_hex:
            return
        color = QColor(color_hex)
        if color.isValid():
            self._current_color = color
            if self._side_toolbar:
                self._side_toolbar.update_color(color)
    
    def set_ocr_loading(self, loading: bool):
        """设置 OCR 加载状态，更新侧边栏按钮
        
        Args:
            loading: True 表示后台 OCR 正在进行中，False 表示完成
        """
        if self._side_toolbar:
            self._side_toolbar.set_ocr_loading(loading)
    
    def set_auto_ocr_popup_manager(self, manager):
        """设置自动OCR弹窗管理器
        
        Args:
            manager: AutoOCRPopupManager 实例
        """
        # 断开旧的信号连接
        if self._auto_ocr_popup_manager is not None:
            try:
                self._auto_ocr_popup_manager.escape_requested.disconnect(self._force_exit)
            except (RuntimeError, TypeError):
                pass
        
        self._auto_ocr_popup_manager = manager
        
        # 连接新的信号
        if self._auto_ocr_popup_manager is not None:
            self._auto_ocr_popup_manager.escape_requested.connect(self._force_exit)
    
    def set_clipboard_history_manager(self, manager):
        """设置工作台管理器
        
        用于在 OverlayScreenshot 创建后延迟设置管理器引用。
        
        Feature: screenshot-state-restore
        Requirements: 2.2, 2.3
        
        Args:
            manager: ClipboardHistoryManager 实例
        """
        self._clipboard_history_manager = manager
        debug_log(f"工作台管理器已设置: {manager is not None}", "HISTORY")
    
    def set_tool_colors(self, tool_colors: dict):
        """设置各工具的颜色配置
        
        Args:
            tool_colors: 工具名称到颜色的映射字典
        """
        if not tool_colors:
            return
        for tool_name, color_hex in tool_colors.items():
            if tool_name in self._tool_colors and color_hex:
                # 验证颜色格式
                color = QColor(color_hex)
                if color.isValid():
                    self._tool_colors[tool_name] = color_hex
    
    def get_tool_colors(self) -> dict:
        """获取各工具的颜色配置
        
        Returns:
            工具名称到颜色的映射字典
        """
        return self._tool_colors.copy()
    
    def set_tool_widths(self, tool_widths: dict):
        """设置各工具的粗细配置
        
        Args:
            tool_widths: 工具名称到粗细级别的映射字典
        """
        if not tool_widths:
            return
        for tool_name, width in tool_widths.items():
            if tool_name in self._tool_widths and width is not None:
                # 验证粗细范围（1-10）
                if isinstance(width, int) and 1 <= width <= 10:
                    self._tool_widths[tool_name] = width
    
    def get_tool_widths(self) -> dict:
        """获取各工具的粗细配置
        
        Returns:
            工具名称到粗细级别的映射字典
        """
        return self._tool_widths.copy()
    
    def _on_width_changed(self, level: int):
        """从侧边栏选择了粗细级别"""
        self._current_width_level = level
        
        # 如果有选中的图形，实时调整其线条粗细
        if self._selected_item:
            # 步骤编号使用专门的直径计算公式
            if self._selected_item.tool == DrawTool.STEP:
                actual_width = get_step_diameter(level)
            else:
                actual_width = get_actual_width(level)
            self._selected_item.width = actual_width
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            self._update_item_region(self._selected_item)
        
        # 如果内联编辑器激活，实时更新字体大小
        if self._inline_editor.active:
            self._inline_editor.font_size = get_text_font_size(level)
            # 使用局部更新
            if self._inline_editor.position:
                text_rect = QRect(self._inline_editor.position.x(), 
                                  self._inline_editor.position.y() - 30,
                                  200, 50)
                self._update_region(text_rect, 10)
        
        # 保存当前工具的粗细
        if self._current_tool != DrawTool.NONE:
            tool_name = self._current_tool.value
            if tool_name in self._tool_widths:
                self._tool_widths[tool_name] = level
                # 发送工具粗细改变信号（用于保存配置）
                self.toolWidthChanged.emit(tool_name, level)
    
    def _sync_selected_item_properties(self):
        """同步选中图形的属性到UI（粗细、颜色）"""
        if not self._selected_item:
            return
        
        # 从图形的实际宽度反推粗细级别
        actual_width = self._selected_item.width
        # 步骤编号使用专门的反推公式
        if self._selected_item.tool == DrawTool.STEP:
            level = get_step_level_from_diameter(actual_width)
        else:
            level = get_width_level(actual_width)
        self._current_width_level = level
        
        # 更新侧边栏粗细显示
        if self._side_toolbar:
            self._side_toolbar.update_width(level)
        
        # 同步颜色
        item_color = self._selected_item.color
        if item_color.isValid():
            self._current_color = item_color
            if self._side_toolbar:
                self._side_toolbar.update_color(item_color)

    # ========== 内联文字编辑器方法 ==========
    # Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1
    
    def _create_step_number(self, pos: QPoint):
        """创建步骤编号
        
        Args:
            pos: 步骤编号的中心位置
        """
        # 递增步骤计数器
        self._step_counter += 1
        
        # 获取当前工具的颜色和大小
        # 使用当前侧边栏显示的粗细级别（_current_width_level），而不是配置保存的值
        tool_name = "step"
        color_hex = self._tool_colors.get(tool_name, "#FF0000")
        width_level = self._current_width_level
        
        # 将粗细级别转换为圆的直径
        diameter = get_step_diameter(width_level)
        
        # 创建步骤编号项
        item = DrawItem(
            tool=DrawTool.STEP,
            color=QColor(color_hex),
            width=diameter,
            points=[pos],
            step_number=self._step_counter
        )
        
        self._draw_items.append(item)
        self._undo_stack.clear()  # 新绘制后清空重做栈
        self._add_item_to_index(item)
        
        # 选中新创建的步骤编号
        self._selected_item = item
        
        # 触发状态保存
        # Feature: screenshot-state-restore
        # Requirements: 1.2
        self._schedule_save_state()
        
        debug_log(f"创建步骤编号: #{self._step_counter} at ({pos.x()},{pos.y()}), diameter={diameter}", "STEP")
        self.update()

    def _start_text_input(self, pos: QPoint, editing_item: Optional[DrawItem] = None):
        """开始文字输入
        
        Args:
            pos: 文字位置（画布坐标）
            editing_item: 正在编辑的已有项（None 表示新建）
        
        Requirements: 1.1, 2.1, 2.2
        """
        self._inline_editor.active = True
        self._inline_editor.position = pos
        
        if editing_item:
            # 编辑已有文字：使用已有项的颜色和字体大小
            self._inline_editor.text = editing_item.text or ""
            self._inline_editor.cursor_pos = len(self._inline_editor.text)
            self._inline_editor.editing_item = editing_item
            # 使用已有项的颜色
            if editing_item.color and editing_item.color.isValid():
                self._inline_editor.color = QColor(editing_item.color)
            else:
                self._inline_editor.color = QColor(self._current_color)
            # 使用已有项的字体大小
            # 兼容旧格式（width 存储粗细级别 1-10）和新格式（width 直接存储字体大小 pt）
            item_width = editing_item.width if editing_item.width and editing_item.width > 0 else self._current_width_level
            if item_width > 10:
                # 新格式：width 直接是字体大小
                self._inline_editor.font_size = item_width
                self._current_width_level = font_size_to_width_level(item_width)
            else:
                # 旧格式：width 是粗细级别
                self._inline_editor.font_size = get_text_font_size(item_width)
                self._current_width_level = item_width
        else:
            # 新建文字：使用当前选择的颜色和粗细
            self._inline_editor.text = ""
            self._inline_editor.cursor_pos = 0
            self._inline_editor.editing_item = None
            self._inline_editor.color = QColor(self._current_color)
            self._inline_editor.font_size = get_text_font_size(self._current_width_level)
        
        self._inline_editor.clear_selection()
        self._inline_editor.cursor_visible = True
        
        # 启动光标闪烁定时器
        if self._cursor_blink_timer:
            self._cursor_blink_timer.start()
        
        self.update()
    
    def _finish_text_input(self, save: bool = True):
        """完成文字输入
        
        Args:
            save: 是否保存文字（False 表示取消）
        
        Requirements: 1.3, 1.4, 2.3
        """
        if not self._inline_editor.active:
            return
        
        # 停止光标闪烁定时器
        if self._cursor_blink_timer:
            self._cursor_blink_timer.stop()
        
        if save and self._inline_editor.text.strip():
            if self._inline_editor.editing_item:
                # 更新已有项
                editing_item = self._inline_editor.editing_item
                # 先从空间索引移除旧项（边界矩形可能变化）
                self._remove_item_from_index(editing_item)
                # 更新文字内容
                editing_item.text = self._inline_editor.text
                # 重新添加到空间索引
                self._add_item_to_index(editing_item)
            else:
                # 创建新项
                # 确保颜色有效
                color = self._inline_editor.color if self._inline_editor.color and self._inline_editor.color.isValid() else QColor(self._current_color)
                item = DrawItem(
                    tool=DrawTool.TEXT,
                    color=QColor(color),
                    width=self._current_width_level,
                    points=[self._inline_editor.position],
                    text=self._inline_editor.text
                )
                self._draw_items.append(item)
                self._undo_stack.clear()
                # 添加到空间索引（用于悬停检测）
                self._add_item_to_index(item)
        
        # 重置编辑器状态
        self._inline_editor.reset()
        self.update()
    
    def _toggle_cursor_blink(self):
        """切换光标可见性（用于闪烁效果）
        
        Requirements: 3.1
        """
        if self._inline_editor.active:
            self._inline_editor.cursor_visible = not self._inline_editor.cursor_visible
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            if self._inline_editor.position:
                # 只更新光标区域
                cursor_rect = QRect(self._inline_editor.position.x(), 
                                    self._inline_editor.position.y() - 30,
                                    200, 50)
                self._update_region(cursor_rect, 5)
    
    def _handle_text_key(self, event: QKeyEvent):
        """处理文字编辑键盘事件
        
        Requirements: 1.2, 1.3, 1.4, 3.4, 4.1, 4.2, 4.3, 4.4
        """
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key.Key_Escape:
            # 取消输入
            self._finish_text_input(save=False)
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            # 确认输入
            self._finish_text_input(save=True)
        elif key == Qt.Key.Key_Backspace:
            # 删除光标前的字符
            self._delete_char(before_cursor=True)
        elif key == Qt.Key.Key_Delete:
            # 删除光标后的字符
            self._delete_char(before_cursor=False)
        elif key == Qt.Key.Key_Left:
            # 左移光标
            self._move_cursor(-1, bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        elif key == Qt.Key.Key_Right:
            # 右移光标
            self._move_cursor(1, bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        elif key == Qt.Key.Key_Home:
            # 移动到开头
            self._move_cursor_to(0, bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        elif key == Qt.Key.Key_End:
            # 移动到结尾
            self._move_cursor_to(len(self._inline_editor.text), bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        elif key == Qt.Key.Key_A and modifiers & Qt.KeyboardModifier.ControlModifier:
            # 全选
            self._select_all()
        elif event.text() and event.text().isprintable():
            # 插入可打印字符
            self._insert_text(event.text())
        
        self.update()
    
    def _insert_text(self, text: str):
        """在光标位置插入文字
        
        如果有选中文字，先删除选中部分再插入。
        
        Requirements: 1.2, 4.4
        """
        editor = self._inline_editor
        
        # 如果有选中文字，先删除
        if editor.has_selection():
            start, end = editor.get_selection_range()
            editor.text = editor.text[:start] + editor.text[end:]
            editor.cursor_pos = start
            editor.clear_selection()
        
        # 插入文字
        editor.text = editor.text[:editor.cursor_pos] + text + editor.text[editor.cursor_pos:]
        editor.cursor_pos += len(text)
        
        # 重置光标可见性（插入后立即显示光标）
        editor.cursor_visible = True
        if self._cursor_blink_timer:
            self._cursor_blink_timer.start()
    
    def _delete_char(self, before_cursor: bool):
        """删除字符
        
        Args:
            before_cursor: True 删除光标前的字符（Backspace），False 删除光标后的字符（Delete）
        
        Requirements: 4.1, 4.2
        """
        editor = self._inline_editor
        
        # 如果有选中文字，删除选中部分
        if editor.has_selection():
            start, end = editor.get_selection_range()
            editor.text = editor.text[:start] + editor.text[end:]
            editor.cursor_pos = start
            editor.clear_selection()
            return
        
        if before_cursor:
            # Backspace: 删除光标前的字符
            if editor.cursor_pos > 0:
                editor.text = editor.text[:editor.cursor_pos - 1] + editor.text[editor.cursor_pos:]
                editor.cursor_pos -= 1
        else:
            # Delete: 删除光标后的字符
            if editor.cursor_pos < len(editor.text):
                editor.text = editor.text[:editor.cursor_pos] + editor.text[editor.cursor_pos + 1:]
    
    def _move_cursor(self, delta: int, extend_selection: bool = False):
        """移动光标
        
        Args:
            delta: 移动方向（-1 左移，1 右移）
            extend_selection: 是否扩展选择
        
        Requirements: 3.4
        """
        editor = self._inline_editor
        old_pos = editor.cursor_pos
        new_pos = max(0, min(len(editor.text), editor.cursor_pos + delta))
        
        if extend_selection:
            # 扩展选择
            if editor.selection_start < 0:
                editor.selection_start = old_pos
            editor.selection_end = new_pos
        else:
            # 清除选择
            editor.clear_selection()
        
        editor.cursor_pos = new_pos
        
        # 重置光标可见性
        editor.cursor_visible = True
        if self._cursor_blink_timer:
            self._cursor_blink_timer.start()
    
    def _move_cursor_to(self, pos: int, extend_selection: bool = False):
        """移动光标到指定位置
        
        Args:
            pos: 目标位置
            extend_selection: 是否扩展选择
        
        Requirements: 3.4
        """
        editor = self._inline_editor
        old_pos = editor.cursor_pos
        new_pos = max(0, min(len(editor.text), pos))
        
        if extend_selection:
            # 扩展选择
            if editor.selection_start < 0:
                editor.selection_start = old_pos
            editor.selection_end = new_pos
        else:
            # 清除选择
            editor.clear_selection()
        
        editor.cursor_pos = new_pos
        
        # 重置光标可见性
        editor.cursor_visible = True
        if self._cursor_blink_timer:
            self._cursor_blink_timer.start()
    
    def _select_all(self):
        """全选文字
        
        Requirements: 4.3
        """
        editor = self._inline_editor
        if editor.text:
            editor.selection_start = 0
            editor.selection_end = len(editor.text)
            editor.cursor_pos = len(editor.text)
    
    def _draw_inline_editor(self, painter: QPainter):
        """绘制内联文字编辑器
        
        Requirements: 1.5, 3.2, 3.3, 5.3
        """
        if not self._inline_editor.active:
            return
        
        editor = self._inline_editor
        if editor.position is None:
            return
        
        # 确保颜色有效
        color = editor.color if editor.color and editor.color.isValid() else QColor("#FF0000")
        
        font = QFont(TEXT_FONT_FAMILY, editor.font_size)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        
        pos = editor.position  # 基线位置
        text = editor.text
        text_len = len(text)
        
        # 确保光标位置在有效范围内
        cursor_pos = max(0, min(editor.cursor_pos, text_len))
        
        # 绘制选中背景
        if editor.has_selection():
            start, end = editor.get_selection_range()
            # 确保选择范围在有效范围内
            start = max(0, min(start, text_len))
            end = max(0, min(end, text_len))
            
            if start < end:
                before_sel = text[:start]
                selected = text[start:end]
                
                sel_x = pos.x() + metrics.horizontalAdvance(before_sel)
                sel_width = metrics.horizontalAdvance(selected)
                sel_rect = QRect(sel_x, pos.y() - metrics.ascent(), sel_width, metrics.height())
                painter.fillRect(sel_rect, QColor(100, 149, 237, 100))  # 淡蓝色选中背景
        
        # 绘制文字（使用基线位置绘制，与 _draw_item 中的矩形绘制保持视觉一致）
        if text:
            painter.setPen(color)
            painter.drawText(pos, text)
        
        # 绘制光标
        if editor.cursor_visible:
            cursor_x = pos.x() + metrics.horizontalAdvance(text[:cursor_pos])
            cursor_y1 = pos.y() - metrics.ascent()
            cursor_y2 = pos.y() + metrics.descent()
            painter.setPen(QPen(color, 2))
            painter.drawLine(cursor_x, cursor_y1, cursor_x, cursor_y2)

    def _undo(self):
        if self._draw_items:
            item = self._draw_items.pop()
            self._undo_stack.append(item)
            if self._selected_item == item:
                self._selected_item = None
            # 如果是高亮工具，取消对应的 OCR 任务
            if item.tool == DrawTool.MARKER:
                self._cancel_marker_ocr(item)
            
            # 追踪标注项被删除（用于脏区域计算）
            # Feature: performance-ui-optimization
            # Requirements: 2.4, 5.1
            if self._paint_engine is not None:
                self._paint_engine.track_annotation_removed(item._id)
            
            # 使用局部更新而非全屏重绘
            # Feature: performance-ui-optimization
            # Requirements: 2.2, 2.4
            self._update_item_region(item)

    def _redo(self):
        if self._undo_stack:
            item = self._undo_stack.pop()
            self._draw_items.append(item)
            
            # 追踪标注项被恢复（用于脏区域计算）
            # Feature: performance-ui-optimization
            # Requirements: 2.4, 5.1
            if self._paint_engine is not None:
                item_rect = item.get_bounding_rect()
                if not item_rect.isEmpty():
                    self._paint_engine.track_annotation(item._id, item_rect, item.width or 2)
            
            # 使用局部更新而非全屏重绘
            self._update_item_region(item)

    def _get_result_image(self) -> Optional[QImage]:
        """获取结果图片，包含选区内的截图和绘制项
        
        采用 Flameshot 的方法：先在完整截图上绘制所有绘制项，然后裁剪选区
        
        关键点：
        - _screenshot 已设置 devicePixelRatio，Qt 会自动处理逻辑坐标到物理像素的转换
        - 绘制项坐标是 widget 坐标（逻辑像素），直接使用即可
        - 不需要手动 scale，Qt 会根据 pixmap 的 DPR 自动缩放
        """
        rect = self._get_selection_rect()
        if rect.isEmpty() or self._screenshot is None:
            debug_log("选区为空或截图为空", "RESULT")
            return None
        
        try:
            dpr = self._device_pixel_ratio
            # 防御性检查：确保 DPR 有效
            if dpr <= 0:
                dpr = 1.0
                debug_log(f"DPR 无效，使用默认值 1.0", "RESULT")
            
            debug_log("=" * 60, "RESULT")
            debug_log("开始获取结果图片", "RESULT")
            debug_log(f"设备像素比 DPR: {dpr}", "RESULT")
            debug_log(f"选区 (widget坐标): x={rect.x()}, y={rect.y()}, w={rect.width()}, h={rect.height()}", "RESULT")
            debug_log(f"截图 pixmap DPR: {self._screenshot.devicePixelRatio()}", "RESULT")
            
            # 决定使用哪个源图像
            source_pixmap = self._screenshot
            
            # 如果有绘制项，先在完整截图上绘制，然后裁剪
            if self._draw_items:
                debug_log(f"有 {len(self._draw_items)} 个绘制项需要绘制", "RESULT")
                
                # 复制原始截图（保留 DPR 设置）
                screenshot_with_drawings = self._screenshot.copy()
                # 确保复制后的 pixmap 也有正确的 DPR
                screenshot_with_drawings.setDevicePixelRatio(self._screenshot.devicePixelRatio())
                
                # 在完整截图上绘制所有绘制项
                # 由于 pixmap 设置了 DPR，QPainter 会自动将逻辑坐标转换为物理像素
                painter = QPainter(screenshot_with_drawings)
                if painter.isActive():
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    # 不需要手动 scale！pixmap 的 DPR 会让 Qt 自动处理坐标转换
                    
                    for idx, item in enumerate(self._draw_items):
                        if item.points:
                            first_pt = item.points[0]
                            debug_log(f"绘制项 {idx}: tool={item.tool}, first=({first_pt.x()}, {first_pt.y()})", "RESULT")
                        self._draw_item(painter, item, log_enabled=True)
                    
                    painter.end()
                    # 绘制成功，使用带绘制项的截图
                    source_pixmap = screenshot_with_drawings
                else:
                    debug_log("无法创建 QPainter，将使用原始截图（不含绘制项）", "ERROR")
            
            # 转换为 QImage
            source_image = source_pixmap.toImage()
            if source_image.isNull():
                debug_log("源图像为空", "ERROR")
                return None
            
            # 计算物理像素坐标（QImage.copy 使用物理像素坐标）
            phys_x = int(rect.x() * dpr)
            phys_y = int(rect.y() * dpr)
            phys_w = int(rect.width() * dpr)
            phys_h = int(rect.height() * dpr)
            
            src_w, src_h = source_image.width(), source_image.height()
            debug_log(f"源图像尺寸: {src_w}x{src_h}", "RESULT")
            debug_log(f"物理像素坐标 (裁剪区域): x={phys_x}, y={phys_y}, w={phys_w}, h={phys_h}", "RESULT")
            
            # 边界检查和调整
            phys_x = max(0, min(phys_x, src_w - 1))
            phys_y = max(0, min(phys_y, src_h - 1))
            phys_w = min(phys_w, src_w - phys_x)
            phys_h = min(phys_h, src_h - phys_y)
            
            if phys_w <= 0 or phys_h <= 0:
                debug_log("裁剪区域无效", "ERROR")
                return None
            
            # 裁剪选区
            result = source_image.copy(phys_x, phys_y, phys_w, phys_h)
            if result.isNull():
                debug_log("裁剪结果为空", "ERROR")
                return None
            
            debug_log(f"最终图像尺寸: {result.width()}x{result.height()}", "RESULT")
            return result
            
        except Exception as e:
            debug_log(f"获取结果图片失败: {e}", "ERROR")
            import traceback
            debug_log(traceback.format_exc(), "ERROR")
            return None

    def _copy(self):
        debug_log("_copy() 被调用（双击保存）", "COPY")
        debug_log(f"当前绘制项数量: {len(self._draw_items)}", "COPY")
        image = self._get_result_image()
        if image:
            debug_log(f"获取结果图片成功，尺寸: {image.width()}x{image.height()}", "COPY")
            QApplication.clipboard().setImage(image)
            self.screenshotTaken.emit(image)
            
            # 保存到工作台（带标注数据）
            self._save_to_clipboard_history()
            
            # 检查 OCR 窗口是否置顶，如果没有置顶则关闭
            if self._auto_ocr_popup_manager is not None:
                if not self._auto_ocr_popup_manager.is_window_pinned():
                    debug_log("OCR窗口未置顶，关闭窗口", "COPY")
                    self._auto_ocr_popup_manager.close_window()
                else:
                    debug_log("OCR窗口已置顶，保持打开", "COPY")
        else:
            debug_log("获取结果图片失败", "COPY")
        self._close()
    
    def _save_to_clipboard_history(self) -> Optional[str]:
        """保存截图到工作台（带标注数据）
        
        Feature: screenshot-state-restore
        Requirements: 1.1, 1.2, 2.4
        
        Returns:
            保存的条目 ID，失败返回 None
        """
        if self._clipboard_history_manager is None:
            debug_log("工作台管理器未设置，跳过保存", "HISTORY")
            return None
        
        if self._screenshot is None:
            debug_log("截图为空，无法保存到历史", "HISTORY")
            return None
        
        try:
            # 获取原始截图图像（不带标注）
            original_image = self._screenshot.toImage()
            if original_image.isNull():
                debug_log("原始截图转换失败", "HISTORY")
                return None
            
            # 获取选区坐标
            selection_rect = self._get_selection_rect()
            selection_tuple = None
            if not selection_rect.isEmpty():
                selection_tuple = (
                    selection_rect.x(),
                    selection_rect.y(),
                    selection_rect.width(),
                    selection_rect.height(),
                )
            
            # 转换标注数据为 dict 列表
            annotations = None
            if self._draw_items:
                annotations = []
                for item in self._draw_items:
                    annotation_data = item.to_annotation_data()
                    annotations.append(annotation_data.to_dict())
                debug_log(f"保存 {len(annotations)} 个标注到历史", "HISTORY")
            
            # 保存到历史（如果是继续编辑，更新原条目）
            item_id = self._clipboard_history_manager.add_screenshot_item(
                image=original_image,
                annotations=annotations,
                selection_rect=selection_tuple,
                item_id=self._editing_history_item_id,
            )
            
            if item_id:
                debug_log(f"截图已保存到历史，ID: {item_id}", "HISTORY")
                return item_id
            else:
                debug_log("保存到历史失败", "HISTORY")
                return None
                
        except Exception as e:
            debug_log(f"保存到工作台异常: {e}", "HISTORY")
            import traceback
            debug_log(traceback.format_exc(), "HISTORY")
            return None

    def _get_initial_save_folder(self) -> str:
        """获取初始保存文件夹路径
        
        如果配置中有上次保存的文件夹且存在，返回该路径；
        否则返回系统 Pictures 文件夹。
        
        Returns:
            str: 初始文件夹路径
        """
        # 尝试从配置获取上次保存的文件夹
        if self._config_manager:
            last_folder = self._config_manager.config.last_save_folder
            if last_folder and os.path.isdir(last_folder):
                debug_log(f"使用上次保存的文件夹: {last_folder}", "SAVE")
                return last_folder
        
        # 回退到系统 Pictures 文件夹
        from PySide6.QtCore import QStandardPaths
        pictures_locations = QStandardPaths.standardLocations(
            QStandardPaths.StandardLocation.PicturesLocation
        )
        if pictures_locations:
            pictures_folder = pictures_locations[0]
            debug_log(f"使用系统 Pictures 文件夹: {pictures_folder}", "SAVE")
            return pictures_folder
        
        # 最后回退到用户主目录
        home_folder = os.path.expanduser("~")
        debug_log(f"回退到用户主目录: {home_folder}", "SAVE")
        return home_folder

    def _save(self):
        """保存截图 - 弹出文件保存对话框"""
        debug_log("_save() 被调用", "SAVE")
        debug_log(f"当前绘制项数量: {len(self._draw_items)}", "SAVE")
        
        # 获取初始目录
        initial_dir = self._get_initial_save_folder()
        
        # 生成默认文件名（时间戳格式）
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"截图_{timestamp}.png"
        default_path = os.path.join(initial_dir, default_filename)
        
        # 弹出文件保存对话框
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "保存截图",
            default_path,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)"
        )
        
        if not file_path:
            # 用户取消，不做任何操作
            debug_log("用户取消了文件保存", "SAVE")
            return
        
        debug_log(f"用户选择的文件路径: {file_path}", "SAVE")
        
        # 获取结果图片
        image = self._get_result_image()
        if image:
            debug_log(f"获取结果图片成功，尺寸: {image.width()}x{image.height()}", "SAVE")
            # 发出保存到指定文件的信号
            self.screenshotSaveRequested.emit(image, file_path)
            
            # 检查 OCR 窗口是否置顶，如果没有置顶则关闭
            if self._auto_ocr_popup_manager is not None:
                if not self._auto_ocr_popup_manager.is_window_pinned():
                    debug_log("OCR窗口未置顶，关闭窗口", "SAVE")
                    self._auto_ocr_popup_manager.close_window()
                else:
                    debug_log("OCR窗口已置顶，保持打开", "SAVE")
        else:
            debug_log("获取结果图片失败", "SAVE")
        self._close()

    def _trigger_auto_ocr_popup(self, image: QImage, log_tag: str) -> None:
        """触发自动OCR弹窗
        
        Args:
            image: 截图图片
            log_tag: 日志标签（用于区分调用来源）
        """
        if self._auto_ocr_popup_manager is None:
            debug_log("_auto_ocr_popup_manager 为 None，跳过自动OCR弹窗", log_tag)
            return
        
        try:
            selection_rect = self._get_selection_rect()
            if selection_rect.isEmpty():
                debug_log("选区为空，跳过自动OCR弹窗", log_tag)
                return
            
            # 设置工具栏位置，让 OCR 面板避开工具栏
            toolbar_rects = []
            if self._toolbar and self._toolbar.isVisible():
                toolbar_rects.append(self._toolbar.geometry())
            if self._side_toolbar and self._side_toolbar.isVisible():
                toolbar_rects.append(self._side_toolbar.geometry())
            
            self._auto_ocr_popup_manager.set_toolbar_rects(toolbar_rects)
            debug_log(f"设置工具栏位置: {len(toolbar_rects)} 个", log_tag)
            
            debug_log(f"触发自动OCR弹窗，选区: {selection_rect}", log_tag)
            self._auto_ocr_popup_manager.on_screenshot_confirmed(image, selection_rect)
            debug_log("on_screenshot_confirmed 调用完成", log_tag)
        except (AttributeError, RuntimeError) as e:
            debug_log(f"触发自动OCR弹窗失败: {e}", log_tag)

    def _cancel(self, close_ocr_panel: bool = True):
        """取消截图
        
        Args:
            close_ocr_panel: 是否同时关闭 OCR 面板，默认为 True
        """
        debug_log(f"_cancel() 被调用, close_ocr_panel={close_ocr_panel}", "CANCEL")
        try:
            if close_ocr_panel and self._auto_ocr_popup_manager is not None:
                debug_log("_cancel() 关闭 OCR 面板", "CANCEL")
                self._auto_ocr_popup_manager.close_window()
            debug_log("_cancel() 发送 screenshotCancelled 信号", "CANCEL")
            self.screenshotCancelled.emit()
            debug_log("_cancel() 准备调用 _close()", "CANCEL")
            self._close()
            debug_log("_cancel() _close() 调用完成", "CANCEL")
        except Exception as e:
            debug_log(f"_cancel() 异常: {e}", "ERROR")
            import traceback
            debug_log(traceback.format_exc(), "ERROR")
            # 即使出错也要尝试隐藏窗口
            try:
                debug_log("_cancel() 异常后尝试强制隐藏", "CANCEL")
                self.hide()
                self.setVisible(False)
                if self.isVisible():
                    self.move(-10000, -10000)
            except Exception as e2:
                debug_log(f"_cancel() 强制隐藏也失败: {e2}", "ERROR")
    
    def cancel(self, close_ocr_panel: bool = True):
        """取消截图（公共方法）
        
        供外部调用的取消截图方法，例如录屏功能需要先关闭截图界面。
        
        Args:
            close_ocr_panel: 是否同时关闭 OCR 面板，默认为 True
        """
        self._cancel(close_ocr_panel)
    
    def _toggle_window_detection(self):
        """切换窗口检测功能
        
        Requirements: 4.1, 4.2, 4.3
        """
        if self._window_detector is None:
            debug_log("窗口检测器未初始化", "WINDOW")
            return
        
        # 切换状态
        new_state = self._window_detector.toggle_enabled()
        
        # 清除当前检测结果
        self._detection_rect = None
        
        # 显示状态提示
        status_text = "窗口检测: 开" if new_state else "窗口检测: 关"
        debug_log(f"窗口检测切换: {status_text}", "WINDOW")
        
        # 使用尺寸标签临时显示状态提示
        if self._size_label:
            self._size_label._label.setText(status_text)
            self._size_label.adjustSize()
            # 在屏幕中央显示
            label_width = self._size_label.width()
            label_height = self._size_label.height()
            x = (self.width() - label_width) // 2
            y = (self.height() - label_height) // 2
            self._size_label.move(x, y)
            self._size_label.show()
            # 1.5 秒后隐藏
            QTimer.singleShot(1500, self._size_label.hide)
        
        self.update()
    
    def _force_exit(self):
        """强制退出截图页面和 OCR 面板（ESC 紧急退出）
        
        无论当前状态如何，立即关闭所有界面。
        这是防止系统冻结的最后防线。
        """
        debug_log("ESC 强制退出截图和 OCR 面板", "EXIT")
        
        # 立即停止所有可能阻塞的操作
        try:
            # 停止窗口检测
            if self._window_detector is not None:
                self._window_detector.set_enabled(False)
                self._window_detector.clear_cache()
            
            # 停止空闲检测
            self._stop_idle_detection()
            
            # 停止所有定时器
            if self._toolbar_timer and self._toolbar_timer.isActive():
                self._toolbar_timer.stop()
            if self._cursor_blink_timer and self._cursor_blink_timer.isActive():
                self._cursor_blink_timer.stop()
            
            # 取消后台 OCR 任务
            if self._background_ocr_manager is not None:
                self._background_ocr_manager.cancel_all_tasks()
        except (AttributeError, RuntimeError) as e:
            debug_log(f"强制退出时清理资源出错: {e}", "ERROR")
        
        # 释放焦点
        # Feature: emergency-esc-exit
        # Requirements: 6.1
        self.clearFocus()
        
        # 调用正常的取消流程
        debug_log("_force_exit: 准备调用 _cancel()", "EXIT")
        try:
            self._cancel(close_ocr_panel=True)
            debug_log("_force_exit: _cancel() 调用完成", "EXIT")
        except Exception as e:
            debug_log(f"_force_exit: _cancel() 异常: {e}", "ERROR")
            import traceback
            debug_log(traceback.format_exc(), "ERROR")
            # 即使 _cancel 失败，也要强制隐藏窗口
            try:
                debug_log("_force_exit: 尝试强制隐藏窗口", "EXIT")
                self.hide()
                self.setVisible(False)
                if self.isVisible():
                    self.move(-10000, -10000)
                debug_log(f"_force_exit: 强制隐藏后 isVisible={self.isVisible()}", "EXIT")
            except Exception as e2:
                debug_log(f"_force_exit: 强制隐藏也失败: {e2}", "ERROR")
        
        # 从全局置顶窗口管理器注销
        # Feature: emergency-esc-exit
        # Requirements: 4.1
        try:
            TopmostWindowManager.instance().unregister_window(self)
        except Exception as e:
            debug_log(f"从 TopmostWindowManager 注销失败: {e}", "ERROR")
        
        # 强制处理事件队列，确保窗口状态更新
        # Feature: emergency-esc-exit
        # Requirements: 6.2
        QApplication.processEvents()

    def _emit_selection_ready(self):
        """选区确定后，发送信号用于后台OCR预处理，并根据配置触发自动OCR弹窗"""
        image = self._get_result_image()
        if image:
            debug_log(f"选区确定，发送selectionReady信号，图片尺寸: {image.width()}x{image.height()}", "OCR")
            # 设置 OCR 按钮为加载状态，等待后台 OCR 完成后恢复
            self.set_ocr_loading(True)
            self.selectionReady.emit(image)
            
            # 检查配置中的 always_ocr_on_screenshot，只有开启时才触发自动OCR弹窗
            if self._config_manager and self._config_manager.config.always_ocr_on_screenshot:
                self._trigger_auto_ocr_popup(image, "OCR")
            else:
                debug_log("always_ocr_on_screenshot 关闭，跳过自动OCR弹窗", "OCR")

    def _on_ocr_toggled(self, enabled: bool):
        """OCR 按钮点击处理 - 直接显示 OCR 面板
        
        注意：此方法现在只用于手动触发 OCR 面板显示。
        自动 OCR 功能由设置中的"截图时始终OCR"控制。
        
        Args:
            enabled: 始终为 True（保留参数以兼容信号签名）
        """
        debug_log("OCR按钮点击，触发OCR面板显示", "OCR")
        
        # 先尝试显示已有窗口，避免重复 OCR
        if self._auto_ocr_popup_manager is not None:
            if self._auto_ocr_popup_manager.show_existing_window():
                debug_log("复用已有OCR窗口，无需重新识别", "OCR")
                return
        
        # 没有已有窗口，需要触发新的 OCR
        if self._selected:
            image = self._get_result_image()
            if image:
                debug_log("触发OCR面板", "OCR")
                self._trigger_auto_ocr_popup(image, "OCR-MANUAL")

    def _pin(self):
        image = self._get_result_image()
        rect = self._get_selection_rect()
        if image:
            self.pinRequested.emit(image, rect)
        self._close()

    def _anki(self):
        """Anki制卡 - 提取高亮区域进行OCR并制作单词卡"""
        debug_log("Anki按钮被点击", "ANKI")
        
        # 获取选区
        selection_rect = self._get_selection_rect()
        if selection_rect.isEmpty():
            debug_log("选区为空", "ANKI")
            return
        
        # 获取所有高亮标记区域，并转换为相对于选区的坐标
        marker_rects = []
        dpr = self._device_pixel_ratio
        
        # 选区的物理像素尺寸
        sel_phys_w = int(selection_rect.width() * dpr)
        sel_phys_h = int(selection_rect.height() * dpr)
        
        for item in self._draw_items:
            if item.tool == DrawTool.MARKER and len(item.points) >= 2:
                rect = item.get_bounding_rect()
                if not rect.isEmpty():
                    # 将高亮区域坐标转换为相对于选区的坐标
                    rel_x = int((rect.x() - selection_rect.x()) * dpr)
                    rel_y = int((rect.y() - selection_rect.y()) * dpr)
                    rel_w = int(rect.width() * dpr)
                    rel_h = int(rect.height() * dpr)
                    
                    # 裁剪到选区范围内
                    if rel_x < 0:
                        rel_w += rel_x
                        rel_x = 0
                    if rel_y < 0:
                        rel_h += rel_y
                        rel_y = 0
                    if rel_x + rel_w > sel_phys_w:
                        rel_w = sel_phys_w - rel_x
                    if rel_y + rel_h > sel_phys_h:
                        rel_h = sel_phys_h - rel_y
                    
                    # 确保尺寸有效
                    if rel_w > 0 and rel_h > 0:
                        marker_rects.append(QRect(rel_x, rel_y, rel_w, rel_h))
                        debug_log(f"高亮区域: 原始({rect.x()},{rect.y()},{rect.width()}x{rect.height()}) -> 相对({rel_x},{rel_y},{rel_w}x{rel_h})", "ANKI")
        
        debug_log(f"找到 {len(marker_rects)} 个有效高亮区域", "ANKI")
        
        # 点击Anki按钮时统一对所有高亮区域做OCR（不再使用后台预识别）
        # 这样可以避免单词被分割识别的问题
        pre_recognized_words = []
        if marker_rects and self._screenshot is not None:
            debug_log("开始统一OCR识别所有高亮区域...", "ANKI")
            debug_log(f"使用原始截图（不带高亮）进行OCR，尺寸: {self._screenshot.width()}x{self._screenshot.height()}", "ANKI")
            try:
                # 获取原始截图图片（不带高亮标记）
                base_image = self._screenshot.toImage()
                if not base_image.isNull():
                    debug_log(f"原始截图 QImage 尺寸: {base_image.width()}x{base_image.height()}", "ANKI")
                    # 复用 BackgroundOCRManager 中的共享 OCR 服务实例，避免重复加载模型
                    from screenshot_tool.core.background_ocr_manager import (
                        OCRWorkerThread, OCR_MARGIN_HORIZONTAL, OCR_MARGIN_VERTICAL,
                        OCR_MIN_WIDTH, OCR_MIN_HEIGHT
                    )
                    ocr_service = OCRWorkerThread.get_ocr_service()
                    
                    if ocr_service is None:
                        debug_log("OCR服务不可用", "ANKI")
                    else:
                        all_text_parts = []
                        
                        for rect in marker_rects:
                            # rect 是相对于选区的坐标，需要转换为相对于截图的坐标
                            phys_x = int(selection_rect.x() * dpr) + rect.x()
                            phys_y = int(selection_rect.y() * dpr) + rect.y()
                            phys_rect = QRect(phys_x, phys_y, rect.width(), rect.height())
                            
                            # 扩展边界提高识别率（使用共享常量）
                            # 水平方向多扩展，避免截掉字母；垂直方向适度扩展，避免识别到上下行
                            x = max(0, phys_rect.x() - OCR_MARGIN_HORIZONTAL)
                            y = max(0, phys_rect.y() - OCR_MARGIN_VERTICAL)
                            w = min(base_image.width() - x, phys_rect.width() + OCR_MARGIN_HORIZONTAL * 2)
                            h = min(base_image.height() - y, phys_rect.height() + OCR_MARGIN_VERTICAL * 2)
                            
                            if w > 0 and h > 0:
                                debug_log(f"OCR裁剪区域: ({x},{y},{w}x{h}), 原始高亮: ({phys_rect.x()},{phys_rect.y()},{phys_rect.width()}x{phys_rect.height()})", "ANKI")
                                cropped = base_image.copy(QRect(x, y, w, h))
                                if not cropped.isNull() and cropped.width() > 0 and cropped.height() > 0:
                                    # 如果图片太小，放大到最小尺寸以提高 OCR 识别率
                                    if cropped.width() < OCR_MIN_WIDTH or cropped.height() < OCR_MIN_HEIGHT:
                                        scale_w = OCR_MIN_WIDTH / cropped.width()
                                        scale_h = OCR_MIN_HEIGHT / cropped.height()
                                        scale = max(scale_w, scale_h)
                                        new_w = int(cropped.width() * scale)
                                        new_h = int(cropped.height() * scale)
                                        debug_log(f"图片太小，放大 {scale:.1f}x: {cropped.width()}x{cropped.height()} -> {new_w}x{new_h}", "ANKI")
                                        cropped = cropped.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                    
                                    result = ocr_service.recognize_image(cropped)
                                    if result.success and result.text:
                                        debug_log(f"高亮区域OCR原始结果: {result.text}", "ANKI")
                                        # 从 OCR 结果中提取单词，优先选择位于图片中心行的单词
                                        # 因为高亮区域在裁剪图片的中心，边缘的文字是干扰
                                        center_y = cropped.height() // 2
                                        best_word = None
                                        best_distance = float('inf')
                                        
                                        # 优先使用带位置信息的 boxes
                                        if result.boxes:
                                            for box in result.boxes:
                                                # 跳过空文本
                                                if not box.text:
                                                    continue
                                                # 计算文字框的中心 Y 坐标
                                                if box.box and len(box.box) >= 4:
                                                    box_y_coords = [p[1] for p in box.box if p and len(p) >= 2]
                                                    if box_y_coords:
                                                        box_center_y = sum(box_y_coords) / len(box_y_coords)
                                                        distance = abs(box_center_y - center_y)
                                                        # 提取这个框中的英文单词，选择最长的
                                                        words = re.findall(r'[a-zA-Z]{3,}', box.text)
                                                        if words:
                                                            longest_in_box = max(words, key=len)
                                                            # 选择距离中心最近的框中的最长单词
                                                            if distance < best_distance:
                                                                best_word = longest_in_box
                                                                best_distance = distance
                                                                debug_log(f"候选单词: {longest_in_box}, 距中心: {distance:.1f}px", "ANKI")
                                        
                                        # 如果没有找到带位置的单词，回退到取第一行最长单词
                                        if best_word is None:
                                            # 取第一行的单词（假设第一行是高亮的那行）
                                            first_line = result.text.split('\n')[0] if '\n' in result.text else result.text
                                            area_words = re.findall(r'[a-zA-Z]{3,}', first_line)
                                            if area_words:
                                                best_word = max(area_words, key=len)
                                        
                                        if best_word:
                                            all_text_parts.append(best_word)
                                            debug_log(f"高亮区域提取单词: {best_word}", "ANKI")
                        
                        # 去重
                        if all_text_parts:
                            seen = set()
                            for word in all_text_parts:
                                word_lower = word.lower()
                                if word_lower not in seen:
                                    seen.add(word_lower)
                                    pre_recognized_words.append(word_lower)
                            debug_log(f"统一OCR识别到 {len(pre_recognized_words)} 个单词: {pre_recognized_words}", "ANKI")
            except ImportError as e:
                debug_log(f"OCR模块导入失败: {e}", "ANKI")
            except Exception as e:
                debug_log(f"统一OCR识别失败: {e}", "ANKI")
        
        # 获取完整截图
        image = self._get_result_image()
        if image:
            # 获取当前高亮颜色
            highlight_color = self._current_color.name()
            self.ankiRequested.emit(image, marker_rects, highlight_color, pre_recognized_words)
            debug_log(f"已发送ankiRequested信号，颜色: {highlight_color}, 预识别单词: {len(pre_recognized_words)} 个", "ANKI")
        else:
            debug_log("图片为空，未发送信号", "ANKI")

    def _recording(self):
        """录屏 - 显示录屏设置面板，让用户配置后再开始录制
        
        Feature: recording-settings-panel
        Requirements: 1.1, 1.5
        """
        debug_log("录屏按钮被点击，显示设置面板", "RECORDING")
        
        # 检查是否有配置管理器
        if not self._config_manager:
            debug_log("配置管理器不可用，无法显示录屏设置面板", "RECORDING")
            return
        
        # 显示录屏设置面板
        from screenshot_tool.ui.recording_settings_panel import RecordingSettingsPanel
        
        panel = RecordingSettingsPanel.show_panel(self._config_manager, self)
        
        # 连接信号
        panel.start_recording_requested.connect(self._on_recording_start_requested)
        panel.cancelled.connect(self._on_recording_cancelled)
    
    def _on_recording_start_requested(self):
        """处理录屏设置面板的开始录制请求
        
        Feature: recording-settings-panel
        Requirements: 4.2, 4.3
        """
        debug_log("录屏设置面板：开始录制请求", "RECORDING")
        
        # 获取选区
        selection_rect = self._get_selection_rect()
        
        # 获取设备像素比
        dpr = self._device_pixel_ratio

        if selection_rect.isEmpty():
            # 没有选区时，使用全屏
            debug_log("选区为空，使用全屏录制", "RECORDING")
            # 获取当前屏幕的物理尺寸
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                phys_x = int(screen_geometry.x() * dpr)
                phys_y = int(screen_geometry.y() * dpr)
                phys_w = int(screen_geometry.width() * dpr)
                phys_h = int(screen_geometry.height() * dpr)
            else:
                # 备用方案：使用窗口尺寸
                phys_x = 0
                phys_y = 0
                phys_w = int(self.width() * dpr)
                phys_h = int(self.height() * dpr)
        else:
            # 有选区时，使用选区
            # 计算物理像素坐标（录屏需要屏幕物理坐标）
            phys_x = int(selection_rect.x() * dpr)
            phys_y = int(selection_rect.y() * dpr)
            phys_w = int(selection_rect.width() * dpr)
            phys_h = int(selection_rect.height() * dpr)

        recording_region = QRect(phys_x, phys_y, phys_w, phys_h)
        debug_log(f"录屏区域: 物理({phys_x},{phys_y},{phys_w}x{phys_h})", "RECORDING")

        # 发出录屏请求信号
        self.recordingRequested.emit(recording_region)

        # 关闭截图界面
        self._close()
    
    def _on_recording_cancelled(self):
        """处理录屏设置面板的取消操作
        
        Feature: recording-settings-panel
        Requirements: 7.1
        """
        debug_log("录屏设置面板：用户取消，返回截图模式", "RECORDING")
        # 不做任何操作，保持在截图模式

    def _init_background_ocr_manager(self):
        """初始化后台 OCR 管理器"""
        if self._background_ocr_manager is None:
            from screenshot_tool.core.background_ocr_manager import BackgroundOCRManager
            self._background_ocr_manager = BackgroundOCRManager()
            self._ocr_base_image_set = False  # 标记基础图片是否已设置
            debug_log("后台 OCR 管理器已初始化", "OCR_MGR")
    
    def _submit_marker_ocr(self, item: DrawItem):
        """提交高亮区域的 OCR 任务
        
        Args:
            item: 高亮绘制项
        """
        if item.tool != DrawTool.MARKER:
            return
        
        # 延迟初始化 OCR 管理器
        self._init_background_ocr_manager()
        
        # 获取截图图片
        if self._screenshot is None:
            debug_log("截图为空，无法提交 OCR 任务", "OCR_MGR")
            return
        
        # 设置基础图片（只在第一次时设置，避免重复复制）
        if not getattr(self, '_ocr_base_image_set', False):
            image = self._screenshot.toImage()
            if image.isNull():
                debug_log("截图转换失败，无法提交 OCR 任务", "OCR_MGR")
                return
            self._background_ocr_manager.set_base_image(image)
            self._ocr_base_image_set = True
        
        # 获取高亮区域（物理像素坐标）
        rect = item.get_bounding_rect()
        if rect.isEmpty():
            debug_log("高亮区域为空，跳过 OCR", "OCR_MGR")
            return
        
        # 转换为物理像素坐标
        dpr = self._device_pixel_ratio
        phys_rect = QRect(
            int(rect.x() * dpr),
            int(rect.y() * dpr),
            int(rect.width() * dpr),
            int(rect.height() * dpr)
        )
        
        # 提交 OCR 任务
        self._background_ocr_manager.submit_task(item_id=item._id, rect=phys_rect)
        debug_log(f"已提交高亮 OCR 任务: item_id={item._id}, rect=({phys_rect.x()},{phys_rect.y()},{phys_rect.width()}x{phys_rect.height()})", "OCR_MGR")
    
    def _cancel_marker_ocr(self, item: DrawItem):
        """取消高亮区域的 OCR 任务
        
        Args:
            item: 高亮绘制项
        """
        if item.tool != DrawTool.MARKER:
            return
        
        if self._background_ocr_manager is not None:
            self._background_ocr_manager.cancel_task(item_id=item._id)
            debug_log(f"已取消高亮 OCR 任务: item_id={item._id}", "OCR_MGR")

    def _start_idle_detection(self):
        """启动空闲检测"""
        if self._idle_detector is None:
            from screenshot_tool.core.idle_detector import IdleDetector
            self._idle_detector = IdleDetector(
                idle_timeout_ms=30000,  # 30秒空闲后释放缓存
                on_idle=self._on_idle_detected
            )
        self._idle_detector.start()
    
    def _stop_idle_detection(self):
        """停止空闲检测"""
        if self._idle_detector is not None:
            self._idle_detector.stop()
    
    def _on_idle_detected(self):
        """空闲检测回调 - 释放非必要缓存"""
        debug_log("检测到空闲状态，释放非必要缓存", "IDLE")
        
        # 释放图片转换缓存
        self._cached_image = None
        
        # 释放遮罩缓存
        if self._paint_engine is not None:
            self._paint_engine.invalidate_mask_cache()
        
        # 释放空间索引（如果没有绘制项）
        if self._spatial_index is not None and not self._draw_items:
            self._spatial_index.clear()
        
        debug_log("非必要缓存已释放", "IDLE")
    
    def _record_user_activity(self):
        """记录用户活动"""
        if self._idle_detector is not None:
            self._idle_detector.record_activity()

    def _close(self):
        debug_log("_close() 开始执行", "CLOSE")
        
        # 设置标志，防止窗口被意外恢复显示
        self._is_closing = True
        
        # 停止空闲检测
        self._stop_idle_detection()
        # 停止工具栏定时器
        if self._toolbar_timer:
            self._toolbar_timer.stop()
        # 停止光标闪烁定时器并重置内联编辑器
        if self._cursor_blink_timer and self._cursor_blink_timer.isActive():
            self._cursor_blink_timer.stop()
        if self._inline_editor.active:
            self._inline_editor.reset()
        # 确保工具栏完全隐藏
        if self._toolbar:
            self._toolbar.hide()
        if self._side_toolbar:
            self._side_toolbar.hide()
        if self._size_label:
            self._size_label.hide()
        
        # 清理后台 OCR 管理器中的任务，避免 "QThread: Destroyed while thread is still running"
        if self._background_ocr_manager is not None:
            self._background_ocr_manager.cancel_all_tasks()
        
        # 清除窗口检测缓存，避免残留状态
        if self._window_detector is not None:
            self._window_detector.clear_cache()
        
        # 释放焦点，确保其他窗口可以获得焦点
        self.clearFocus()
        
        # 检查窗口的真实可见状态
        window_handle = self.windowHandle()
        is_exposed = window_handle.isExposed() if window_handle else False
        debug_log(f"_close() 隐藏前: isVisible={self.isVisible()}, isHidden={self.isHidden()}, isExposed={is_exposed}", "CLOSE")
        
        # 使用 Windows API 直接隐藏窗口（更可靠）
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                # SW_HIDE = 0
                ctypes.windll.user32.ShowWindow(hwnd, 0)
                debug_log(f"_close() 使用 Windows API ShowWindow(hwnd={hwnd}, SW_HIDE) 隐藏窗口", "CLOSE")
        except Exception as e:
            debug_log(f"_close() Windows API 隐藏失败: {e}", "ERROR")
        
        # Qt 层面的隐藏操作
        self.hide()
        self.setVisible(False)
        
        # 强制移动到屏幕外并设置透明度为 0（双重保险）
        self.move(-10000, -10000)
        self.setWindowOpacity(0)
        
        # 禁用鼠标事件，防止隐藏后仍然接收事件
        self.setEnabled(False)
        
        # 强制处理事件队列，确保窗口状态更新
        QApplication.processEvents()
        
        # 再次检查状态（重新获取 window_handle，因为可能已变化）
        window_handle_after = self.windowHandle()
        is_exposed_after = window_handle_after.isExposed() if window_handle_after else False
        debug_log(f"_close() 隐藏后: isVisible={self.isVisible()}, isHidden={self.isHidden()}, isExposed={is_exposed_after}, enabled={self.isEnabled()}", "CLOSE")
        debug_log("_close() 执行完成", "CLOSE")
    
    def restore(self):
        """恢复显示截图覆盖层和工具栏"""
        debug_log(f"restore() 被调用, _is_closing={self._is_closing}", "RESTORE")
        
        # 如果窗口正在关闭，不要恢复显示
        if self._is_closing:
            debug_log("restore() 被阻止：窗口正在关闭", "RESTORE")
            return
        
        # 显示主窗口
        self.show()
        self.raise_()
        self.activateWindow()
        
        # 只有在有有效选区时才恢复工具栏
        if self._selected and not self._selection_rect.isEmpty():
            # 强制更新工具栏位置（必须在show之后，确保坐标转换正确）
            self._update_toolbar_position(force=True)
            
            # 恢复工具栏显示
            if self._toolbar:
                self._toolbar.show()
                self._toolbar.raise_()
            if self._side_toolbar:
                self._side_toolbar.show()
                self._side_toolbar.raise_()
            
            # 重新启动工具栏定时器，确保工具栏保持可见
            if self._toolbar_timer and not self._toolbar_timer.isActive():
                self._toolbar_timer.start()
        
        # 确保主窗口保持焦点
        self.setFocus()

    def cleanup(self):
        """清理资源
        
        增强的清理方法，确保释放所有内存资源：
        - 释放所有图片引用
        - 停止所有定时器
        - 清理所有子组件
        - 触发垃圾回收
        
        Requirements: 1.1, 1.2, 6.1, 7.3
        """
        import gc
        
        # 释放缓存图片 (Requirements: 1.1, 1.2)
        self._cached_image = None
        
        # 停止工具栏定时器
        if self._toolbar_timer:
            self._toolbar_timer.stop()
            self._toolbar_timer = None
        # 停止光标闪烁定时器
        if self._cursor_blink_timer:
            self._cursor_blink_timer.stop()
            self._cursor_blink_timer = None
        # 重置内联编辑器
        if self._inline_editor.active:
            self._inline_editor.reset()
        if self._toolbar:
            self._toolbar.close()
            self._toolbar.deleteLater()
            self._toolbar = None
        if self._side_toolbar:
            self._side_toolbar.cleanup()  # 先清理内部资源
            self._side_toolbar.close()
            self._side_toolbar.deleteLater()
            self._side_toolbar = None
        if self._size_label:
            self._size_label.close()
            self._size_label.deleteLater()
            self._size_label = None
        
        # 释放截图引用 (Requirements: 1.1, 1.2)
        self._screenshot = None
        self._draw_items.clear()
        self._undo_stack.clear()
        
        # 清理性能优化组件
        self._cursor_manager = None
        if self._spatial_index is not None:
            self._spatial_index.clear()
            self._spatial_index = None
        self._toolbar_manager = None
        
        # 清理绘图引擎 (Requirements: 6.1)
        if self._paint_engine is not None:
            self._paint_engine.cleanup()
            self._paint_engine = None
        if self._idle_detector is not None:
            self._idle_detector.cleanup()
            self._idle_detector = None
        
        # 清理后台 OCR 管理器
        if self._background_ocr_manager is not None:
            self._background_ocr_manager.cleanup()
            self._background_ocr_manager = None
        self._ocr_base_image_set = False
        
        # 触发垃圾回收 (Requirements: 7.3)
        gc.collect()

    def closeEvent(self, event):
        # 从全局置顶窗口管理器注销
        # Feature: emergency-esc-exit
        TopmostWindowManager.instance().unregister_window(self)
        self.cleanup()
        super().closeEvent(event)
