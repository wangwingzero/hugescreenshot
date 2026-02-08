# =====================================================
# =============== 高性能历史条目绘制委托 ===============
# =====================================================

"""
高性能历史条目绘制委托 - 使用 QStyledItemDelegate 直接绘制

Feature: extreme-performance-optimization
Requirements: 11.4, 11.5, 9.2

设计原则：
1. 使用 paint() 直接绘制，不创建 Widget（比 QListWidget 快 4 倍以上）
2. 缓存 QFont 和 QFontMetrics 对象（避免重复创建）
3. 缩略图延迟加载和缓存
4. 只绘制可见项，虚拟滚动自动处理
"""

from typing import Optional, Dict
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PySide6.QtCore import Qt, QModelIndex, QSize, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPixmap

from screenshot_tool.core.history_item_data import HistoryItemData


class HistoryItemDelegate(QStyledItemDelegate):
    """高性能历史条目绘制委托
    
    Feature: extreme-performance-optimization
    Requirements: 11.4, 11.5, 9.2
    
    优化策略：
    1. 使用 paint() 直接绘制，不创建 Widget
    2. 缓存 QFont 和 QFontMetrics（类级别缓存，所有实例共享）
    3. 缩略图延迟加载（返回 None，由后台任务加载后更新）
    4. 缩略图缓存（LRU 淘汰策略）
    
    Example:
        >>> from PySide6.QtWidgets import QListView
        >>> view = QListView()
        >>> delegate = HistoryItemDelegate(view)
        >>> view.setItemDelegate(delegate)
    """
    
    # 布局常量
    ITEM_HEIGHT = 120  # 增大以适应更大的缩略图
    THUMB_SIZE = 100   # 高清缩略图（从 80 增大到 100）
    PADDING = 12
    
    # 颜色常量（Flat Design，零阴影零渐变）
    COLOR_SELECTED_BG = QColor("#EFF6FF")
    COLOR_HOVER_BG = QColor("#F8FAFC")
    COLOR_TITLE_TEXT = QColor("#1E293B")
    COLOR_TIME_TEXT = QColor("#64748B")
    COLOR_BADGE_BG = QColor("#E0F2FE")
    COLOR_BADGE_TEXT = QColor("#0369A1")
    COLOR_PINNED_BG = QColor("#FEF3C7")
    COLOR_PINNED_TEXT = QColor("#92400E")
    
    # 类级别字体缓存（所有实例共享，避免重复创建）
    _title_font: Optional[QFont] = None
    _time_font: Optional[QFont] = None
    _badge_font: Optional[QFont] = None
    _title_metrics: Optional[QFontMetrics] = None
    _time_metrics: Optional[QFontMetrics] = None
    _badge_metrics: Optional[QFontMetrics] = None
    
    # 缩略图缓存容量
    MAX_THUMBNAIL_CACHE = 50
    
    def __init__(self, parent=None) -> None:
        """初始化历史条目绘制委托
        
        Args:
            parent: 父对象（通常是 QListView）
        """
        super().__init__(parent)
        self._init_fonts()
        
        # 实例级别缩略图缓存
        self._thumbnail_cache: Dict[str, QPixmap] = {}
        self._thumbnail_lru: list = []  # LRU 顺序追踪
    
    def _init_fonts(self) -> None:
        """初始化并缓存字体
        
        使用类级别缓存，所有实例共享同一组字体对象。
        这避免了每次创建 delegate 时重复创建字体。
        
        Requirements: 9.2 - 缓存 QFont 对象避免重复字体查找
        """
        if HistoryItemDelegate._title_font is None:
            HistoryItemDelegate._title_font = QFont("Segoe UI", 10)
            HistoryItemDelegate._title_font.setWeight(QFont.Weight.Medium)
            HistoryItemDelegate._title_metrics = QFontMetrics(
                HistoryItemDelegate._title_font
            )
        
        if HistoryItemDelegate._time_font is None:
            HistoryItemDelegate._time_font = QFont("Segoe UI", 9)
            HistoryItemDelegate._time_metrics = QFontMetrics(
                HistoryItemDelegate._time_font
            )
        
        if HistoryItemDelegate._badge_font is None:
            HistoryItemDelegate._badge_font = QFont("Segoe UI", 8)
            HistoryItemDelegate._badge_metrics = QFontMetrics(
                HistoryItemDelegate._badge_font
            )
    
    def sizeHint(
        self, 
        option: QStyleOptionViewItem, 
        index: QModelIndex
    ) -> QSize:
        """返回条目的建议大小
        
        Args:
            option: 样式选项
            index: 模型索引
            
        Returns:
            条目的建议大小（宽度使用视图宽度，高度固定）
        """
        return QSize(option.rect.width(), self.ITEM_HEIGHT)
    
    def paint(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        index: QModelIndex
    ) -> None:
        """直接绘制条目内容（高性能）
        
        不创建任何 Widget，直接使用 QPainter 绘制。
        这比 QListWidget 的 Widget 方式快 4 倍以上。
        
        Args:
            painter: 绘图器
            option: 样式选项（包含状态、矩形等）
            index: 模型索引
            
        Requirements: 11.4 - 使用 paint() 直接绘制
        """
        # 获取数据
        item: Optional[HistoryItemData] = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
        
        painter.save()
        
        try:
            rect = option.rect
            
            # 1. 绘制背景（选中/悬停状态）
            self._draw_background(painter, option, rect)
            
            # 计算内容起始位置
            x = rect.left() + self.PADDING
            y = rect.top() + self.PADDING
            
            # 2. 绘制缩略图（如果是图片类型）
            if item.content_type == "image" and item.thumbnail_path:
                thumb = self._get_thumbnail(item.thumbnail_path)
                if thumb and not thumb.isNull():
                    thumb_rect = QRect(x, y, self.THUMB_SIZE, self.THUMB_SIZE)
                    # 使用平滑缩放绘制缩略图
                    painter.drawPixmap(thumb_rect, thumb)
                    x += self.THUMB_SIZE + self.PADDING
                else:
                    # 缩略图未加载，绘制占位符
                    self._draw_thumbnail_placeholder(painter, x, y)
                    x += self.THUMB_SIZE + self.PADDING
            
            # 3. 绘制标题
            self._draw_title(painter, item, x, y, rect)
            
            # 4. 绘制时间
            self._draw_timestamp(painter, item, x, y, rect)
            
            # 5. 绘制徽章（标注/置顶指示器）
            self._draw_badges(painter, item, x, y)
            
        finally:
            painter.restore()
    
    def _draw_background(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        rect: QRect
    ) -> None:
        """绘制背景
        
        根据选中/悬停状态绘制不同背景色。
        使用纯色填充，无阴影无渐变（Flat Design）。
        
        Args:
            painter: 绘图器
            option: 样式选项
            rect: 绘制区域
        """
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, self.COLOR_SELECTED_BG)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, self.COLOR_HOVER_BG)
    
    def _draw_thumbnail_placeholder(
        self, 
        painter: QPainter, 
        x: int, 
        y: int
    ) -> None:
        """绘制缩略图占位符
        
        当缩略图尚未加载时显示的占位符。
        
        Args:
            painter: 绘图器
            x: X 坐标
            y: Y 坐标
        """
        placeholder_rect = QRect(x, y, self.THUMB_SIZE, self.THUMB_SIZE)
        painter.fillRect(placeholder_rect, QColor("#F1F5F9"))
        
        # 绘制图片图标占位符
        painter.setPen(QColor("#CBD5E1"))
        icon_size = 16
        icon_x = x + (self.THUMB_SIZE - icon_size) // 2
        icon_y = y + (self.THUMB_SIZE - icon_size) // 2
        painter.drawRect(icon_x, icon_y, icon_size, icon_size)
    
    def _draw_title(
        self, 
        painter: QPainter, 
        item: HistoryItemData, 
        x: int, 
        y: int, 
        rect: QRect
    ) -> None:
        """绘制标题文本
        
        使用缓存的字体和 QFontMetrics 进行文本省略。
        
        Args:
            painter: 绘图器
            item: 历史条目数据
            x: X 坐标
            y: Y 坐标
            rect: 条目矩形区域
        """
        painter.setFont(self._title_font)
        painter.setPen(self.COLOR_TITLE_TEXT)
        
        # 计算标题区域
        title_width = rect.right() - x - self.PADDING
        title_rect = QRect(x, y, title_width, 20)
        
        # 使用 QFontMetrics 进行文本省略（避免长文本溢出）
        elided_text = self._title_metrics.elidedText(
            item.preview_text, 
            Qt.TextElideMode.ElideRight, 
            title_rect.width()
        )
        
        painter.drawText(
            title_rect, 
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 
            elided_text
        )
    
    def _draw_timestamp(
        self, 
        painter: QPainter, 
        item: HistoryItemData, 
        x: int, 
        y: int, 
        rect: QRect
    ) -> None:
        """绘制时间戳
        
        Args:
            painter: 绘图器
            item: 历史条目数据
            x: X 坐标
            y: Y 坐标
            rect: 条目矩形区域
        """
        painter.setFont(self._time_font)
        painter.setPen(self.COLOR_TIME_TEXT)
        
        time_rect = QRect(x, y + 24, rect.right() - x - self.PADDING, 16)
        painter.drawText(
            time_rect, 
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 
            item.timestamp
        )
    
    def _draw_badges(
        self, 
        painter: QPainter, 
        item: HistoryItemData, 
        x: int, 
        y: int
    ) -> None:
        """绘制徽章（标注/置顶指示器）
        
        Args:
            painter: 绘图器
            item: 历史条目数据
            x: X 坐标
            y: Y 坐标
        """
        badge_y = y + 44
        badge_x = x
        
        painter.setFont(self._badge_font)
        
        # 绘制置顶徽章
        if item.is_pinned:
            badge_width = self._badge_metrics.horizontalAdvance("置顶") + 8
            painter.fillRect(badge_x, badge_y, badge_width, 16, self.COLOR_PINNED_BG)
            painter.setPen(self.COLOR_PINNED_TEXT)
            painter.drawText(badge_x + 4, badge_y + 12, "置顶")
            badge_x += badge_width + 4
        
        # 绘制标注徽章
        if item.has_annotations:
            badge_width = self._badge_metrics.horizontalAdvance("有标注") + 8
            painter.fillRect(badge_x, badge_y, badge_width, 16, self.COLOR_BADGE_BG)
            painter.setPen(self.COLOR_BADGE_TEXT)
            painter.drawText(badge_x + 4, badge_y + 12, "有标注")
    
    def _get_thumbnail(self, path: str) -> Optional[QPixmap]:
        """获取缩略图（带缓存）
        
        使用 LRU 缓存策略，最多缓存 MAX_THUMBNAIL_CACHE 个缩略图。
        
        Args:
            path: 缩略图文件路径
            
        Returns:
            缩略图 QPixmap，未缓存时返回 None
            
        Note:
            缩略图加载应该在后台线程进行。
            这里返回 None，由后台任务加载后调用 set_thumbnail() 更新。
            
        Requirements: 11.5 - 缩略图延迟加载
        """
        if path in self._thumbnail_cache:
            # 更新 LRU 顺序
            if path in self._thumbnail_lru:
                self._thumbnail_lru.remove(path)
            self._thumbnail_lru.append(path)
            return self._thumbnail_cache[path]
        
        # 缩略图未缓存，返回 None
        # 后台任务应该加载缩略图并调用 set_thumbnail()
        return None
    
    def set_thumbnail(self, path: str, pixmap: QPixmap) -> None:
        """设置缩略图缓存（由后台任务调用）
        
        使用 LRU 淘汰策略，当缓存满时删除最久未使用的缩略图。
        
        Args:
            path: 缩略图文件路径
            pixmap: 缩略图 QPixmap
            
        Note:
            调用此方法后，需要触发视图重绘以显示新缩略图。
            可以通过 model.dataChanged 信号或 view.update() 实现。
        """
        # LRU 淘汰
        while len(self._thumbnail_cache) >= self.MAX_THUMBNAIL_CACHE:
            if self._thumbnail_lru:
                oldest = self._thumbnail_lru.pop(0)
                self._thumbnail_cache.pop(oldest, None)
            else:
                break
        
        self._thumbnail_cache[path] = pixmap
        self._thumbnail_lru.append(path)
    
    def has_thumbnail(self, path: str) -> bool:
        """检查缩略图是否已缓存
        
        Args:
            path: 缩略图文件路径
            
        Returns:
            是否已缓存
        """
        return path in self._thumbnail_cache
    
    def clear_thumbnail_cache(self) -> None:
        """清除缩略图缓存
        
        释放内存时使用。
        """
        self._thumbnail_cache.clear()
        self._thumbnail_lru.clear()
    
    def get_thumbnail_cache_size(self) -> int:
        """获取缩略图缓存数量
        
        Returns:
            缓存的缩略图数量
        """
        return len(self._thumbnail_cache)
    
    def get_thumbnail_cache_memory(self) -> int:
        """估算缩略图缓存内存使用（字节）
        
        Returns:
            估算的内存使用量（字节）
        """
        total = 0
        for pixmap in self._thumbnail_cache.values():
            if not pixmap.isNull():
                # RGBA 格式，每像素 4 字节
                total += pixmap.width() * pixmap.height() * 4
        return total
    
    @classmethod
    def reset_font_cache(cls) -> None:
        """重置字体缓存
        
        主题切换或字体设置更改时使用。
        """
        cls._title_font = None
        cls._time_font = None
        cls._badge_font = None
        cls._title_metrics = None
        cls._time_metrics = None
        cls._badge_metrics = None

