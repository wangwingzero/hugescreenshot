# =====================================================
# =============== 历史条目绘制委托测试 ===============
# =====================================================

"""
测试 HistoryItemDelegate 高性能历史条目绘制委托

Feature: extreme-performance-optimization
Requirements: 11.4, 11.5, 9.2

测试覆盖：
1. 字体缓存（类级别共享）
2. 缩略图缓存（LRU 淘汰）
3. sizeHint 返回正确大小
4. paint 方法正确绘制
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from PySide6.QtCore import Qt, QModelIndex, QRect, QSize
from PySide6.QtGui import QFont, QFontMetrics, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QStyleOptionViewItem, QStyle


class TestHistoryItemDelegateFontCache:
    """HistoryItemDelegate 字体缓存测试"""
    
    def test_font_cache_initialized(self, qtbot):
        """测试字体缓存初始化
        
        **Validates: Requirements 9.2**
        """
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        # 重置缓存以确保测试隔离
        HistoryItemDelegate.reset_font_cache()
        
        delegate = HistoryItemDelegate()
        
        # 验证字体已初始化
        assert HistoryItemDelegate._title_font is not None
        assert HistoryItemDelegate._time_font is not None
        assert HistoryItemDelegate._badge_font is not None
        
        # 验证 QFontMetrics 已初始化
        assert HistoryItemDelegate._title_metrics is not None
        assert HistoryItemDelegate._time_metrics is not None
        assert HistoryItemDelegate._badge_metrics is not None
    
    def test_font_cache_shared_between_instances(self, qtbot):
        """测试字体缓存在实例间共享
        
        **Validates: Requirements 9.2**
        """
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        # 重置缓存
        HistoryItemDelegate.reset_font_cache()
        
        delegate1 = HistoryItemDelegate()
        delegate2 = HistoryItemDelegate()
        
        # 验证两个实例共享同一字体对象
        assert delegate1._title_font is delegate2._title_font
        assert delegate1._time_font is delegate2._time_font
        assert delegate1._badge_font is delegate2._badge_font
    
    def test_font_cache_not_recreated(self, qtbot):
        """测试字体缓存不会重复创建
        
        **Validates: Requirements 9.2**
        """
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        # 重置缓存
        HistoryItemDelegate.reset_font_cache()
        
        delegate1 = HistoryItemDelegate()
        font_id_1 = id(HistoryItemDelegate._title_font)
        
        delegate2 = HistoryItemDelegate()
        font_id_2 = id(HistoryItemDelegate._title_font)
        
        # 字体对象应该是同一个
        assert font_id_1 == font_id_2
    
    def test_reset_font_cache(self, qtbot):
        """测试重置字体缓存"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 确保缓存已初始化
        assert HistoryItemDelegate._title_font is not None
        
        # 重置缓存
        HistoryItemDelegate.reset_font_cache()
        
        # 验证缓存已清除
        assert HistoryItemDelegate._title_font is None
        assert HistoryItemDelegate._time_font is None
        assert HistoryItemDelegate._badge_font is None
        assert HistoryItemDelegate._title_metrics is None
        assert HistoryItemDelegate._time_metrics is None
        assert HistoryItemDelegate._badge_metrics is None
    
    def test_font_properties(self, qtbot):
        """测试字体属性正确设置"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        HistoryItemDelegate.reset_font_cache()
        delegate = HistoryItemDelegate()
        
        # 标题字体应该是 Medium 粗细
        assert HistoryItemDelegate._title_font.weight() == QFont.Weight.Medium
        
        # 字体大小
        assert HistoryItemDelegate._title_font.pointSize() == 10
        assert HistoryItemDelegate._time_font.pointSize() == 9
        assert HistoryItemDelegate._badge_font.pointSize() == 8


class TestHistoryItemDelegateThumbnailCache:
    """HistoryItemDelegate 缩略图缓存测试"""
    
    def test_thumbnail_cache_empty_initially(self, qtbot):
        """测试缩略图缓存初始为空"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        assert delegate.get_thumbnail_cache_size() == 0
    
    def test_set_and_get_thumbnail(self, qtbot):
        """测试设置和获取缩略图"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 创建测试 pixmap
        pixmap = QPixmap(44, 44)
        pixmap.fill(QColor("#FF0000"))
        
        # 设置缩略图
        delegate.set_thumbnail("/path/to/image.png", pixmap)
        
        # 获取缩略图
        result = delegate._get_thumbnail("/path/to/image.png")
        
        assert result is not None
        assert not result.isNull()
        assert result.width() == 44
        assert result.height() == 44
    
    def test_get_thumbnail_not_cached_returns_none(self, qtbot):
        """测试获取未缓存的缩略图返回 None
        
        **Validates: Requirements 11.5**
        """
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        result = delegate._get_thumbnail("/nonexistent/path.png")
        
        assert result is None
    
    def test_has_thumbnail(self, qtbot):
        """测试 has_thumbnail 方法"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        pixmap = QPixmap(44, 44)
        pixmap.fill(QColor("#00FF00"))
        
        assert delegate.has_thumbnail("/path/to/image.png") is False
        
        delegate.set_thumbnail("/path/to/image.png", pixmap)
        
        assert delegate.has_thumbnail("/path/to/image.png") is True
    
    def test_thumbnail_lru_eviction(self, qtbot):
        """测试缩略图 LRU 淘汰策略
        
        **Validates: Requirements 11.5**
        """
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 设置最大缓存为 50
        max_cache = HistoryItemDelegate.MAX_THUMBNAIL_CACHE
        
        # 添加超过最大缓存数量的缩略图
        for i in range(max_cache + 10):
            pixmap = QPixmap(10, 10)
            pixmap.fill(QColor(i % 256, 0, 0))
            delegate.set_thumbnail(f"/path/image_{i}.png", pixmap)
        
        # 缓存大小应该不超过最大值
        assert delegate.get_thumbnail_cache_size() <= max_cache
        
        # 最早添加的应该被淘汰
        assert delegate.has_thumbnail("/path/image_0.png") is False
        
        # 最新添加的应该存在
        assert delegate.has_thumbnail(f"/path/image_{max_cache + 9}.png") is True
    
    def test_thumbnail_lru_access_updates_order(self, qtbot):
        """测试访问缩略图更新 LRU 顺序"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 添加 3 个缩略图
        for i in range(3):
            pixmap = QPixmap(10, 10)
            delegate.set_thumbnail(f"/path/image_{i}.png", pixmap)
        
        # 访问第一个（最旧的）
        delegate._get_thumbnail("/path/image_0.png")
        
        # 现在 image_0 应该是最新的，image_1 是最旧的
        # 验证 LRU 顺序
        assert delegate._thumbnail_lru[-1] == "/path/image_0.png"
    
    def test_clear_thumbnail_cache(self, qtbot):
        """测试清除缩略图缓存"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 添加一些缩略图
        for i in range(5):
            pixmap = QPixmap(10, 10)
            delegate.set_thumbnail(f"/path/image_{i}.png", pixmap)
        
        assert delegate.get_thumbnail_cache_size() == 5
        
        # 清除缓存
        delegate.clear_thumbnail_cache()
        
        assert delegate.get_thumbnail_cache_size() == 0
        assert len(delegate._thumbnail_lru) == 0
    
    def test_get_thumbnail_cache_memory(self, qtbot):
        """测试估算缩略图缓存内存"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 添加一个 44x44 的缩略图
        pixmap = QPixmap(44, 44)
        pixmap.fill(QColor("#0000FF"))
        delegate.set_thumbnail("/path/image.png", pixmap)
        
        # 估算内存：44 * 44 * 4 = 7744 字节
        expected_memory = 44 * 44 * 4
        actual_memory = delegate.get_thumbnail_cache_memory()
        
        assert actual_memory == expected_memory


class TestHistoryItemDelegateSizeHint:
    """HistoryItemDelegate sizeHint 测试"""
    
    def test_size_hint_returns_correct_height(self, qtbot):
        """测试 sizeHint 返回正确高度"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 创建模拟的 option 和 index
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 100)
        
        index = QModelIndex()
        
        size = delegate.sizeHint(option, index)
        
        assert size.height() == HistoryItemDelegate.ITEM_HEIGHT
        assert size.width() == 300  # 使用 option.rect 的宽度
    
    def test_item_height_constant(self, qtbot):
        """测试条目高度是常量"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        assert HistoryItemDelegate.ITEM_HEIGHT == 68


class TestHistoryItemDelegatePaint:
    """HistoryItemDelegate paint 测试"""
    
    def test_paint_with_no_data_returns_early(self, qtbot):
        """测试无数据时 paint 提前返回"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        delegate = HistoryItemDelegate()
        
        # 创建模拟对象
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        # 创建返回 None 的 index
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = None
        
        # 调用 paint
        delegate.paint(painter, option, index)
        
        # 验证无数据时不进行任何绑定操作
        # paint 方法在获取数据后检查，如果为 None 则提前返回
        # 不会调用 fillRect, drawText 等绑定方法
        painter.fillRect.assert_not_called()
        painter.drawText.assert_not_called()
        painter.drawPixmap.assert_not_called()
    
    def test_paint_draws_selected_background(self, qtbot):
        """测试绘制选中状态背景"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        # 创建模拟对象
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_Selected
        
        # 创建测试数据
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            content_type="text"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        # 调用 paint
        delegate.paint(painter, option, index)
        
        # 验证 fillRect 被调用（绘制选中背景）
        painter.fillRect.assert_called()
    
    def test_paint_draws_hover_background(self, qtbot):
        """测试绘制悬停状态背景"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_MouseOver
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            content_type="text"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证 fillRect 被调用
        painter.fillRect.assert_called()
    
    def test_paint_draws_title_and_timestamp(self, qtbot):
        """测试绘制标题和时间戳"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            content_type="text"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证 drawText 被调用（至少两次：标题和时间戳）
        assert painter.drawText.call_count >= 2
    
    def test_paint_draws_annotation_badge(self, qtbot):
        """测试绘制标注徽章"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            has_annotations=True,
            content_type="text"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证绘制了徽章（fillRect 和 drawText）
        # 至少有一次 fillRect 用于徽章背景
        assert painter.fillRect.call_count >= 1
    
    def test_paint_draws_pinned_badge(self, qtbot):
        """测试绘制置顶徽章"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            is_pinned=True,
            content_type="text"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证绘制了置顶徽章
        assert painter.fillRect.call_count >= 1
    
    def test_paint_draws_thumbnail_placeholder_when_not_cached(self, qtbot):
        """测试缩略图未缓存时绘制占位符"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            thumbnail_path="/path/to/thumb.png",
            content_type="image"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证绘制了占位符（fillRect 用于占位符背景）
        assert painter.fillRect.call_count >= 1
    
    def test_paint_draws_cached_thumbnail(self, qtbot):
        """测试绘制已缓存的缩略图"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        delegate = HistoryItemDelegate()
        
        # 预先缓存缩略图
        pixmap = QPixmap(44, 44)
        pixmap.fill(QColor("#FF0000"))
        delegate.set_thumbnail("/path/to/thumb.png", pixmap)
        
        painter = MagicMock(spec=QPainter)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 68)
        option.state = QStyle.StateFlag.State_None
        
        item = HistoryItemData(
            id="test-1",
            preview_text="测试截图",
            timestamp="2025-01-15 10:30",
            thumbnail_path="/path/to/thumb.png",
            content_type="image"
        )
        
        index = MagicMock(spec=QModelIndex)
        index.data.return_value = item
        
        delegate.paint(painter, option, index)
        
        # 验证 drawPixmap 被调用
        painter.drawPixmap.assert_called()


class TestHistoryItemDelegateConstants:
    """HistoryItemDelegate 常量测试"""
    
    def test_layout_constants(self, qtbot):
        """测试布局常量"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        assert HistoryItemDelegate.ITEM_HEIGHT == 120  # 增大以适应高清缩略图
        assert HistoryItemDelegate.THUMB_SIZE == 100   # 高清缩略图
        assert HistoryItemDelegate.PADDING == 12
    
    def test_color_constants(self, qtbot):
        """测试颜色常量"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        # 验证颜色是 QColor 实例
        assert isinstance(HistoryItemDelegate.COLOR_SELECTED_BG, QColor)
        assert isinstance(HistoryItemDelegate.COLOR_HOVER_BG, QColor)
        assert isinstance(HistoryItemDelegate.COLOR_TITLE_TEXT, QColor)
        assert isinstance(HistoryItemDelegate.COLOR_TIME_TEXT, QColor)
        assert isinstance(HistoryItemDelegate.COLOR_BADGE_BG, QColor)
        assert isinstance(HistoryItemDelegate.COLOR_BADGE_TEXT, QColor)
    
    def test_max_thumbnail_cache_constant(self, qtbot):
        """测试最大缩略图缓存常量"""
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        assert HistoryItemDelegate.MAX_THUMBNAIL_CACHE == 50


class TestHistoryItemDelegateIntegration:
    """HistoryItemDelegate 集成测试"""
    
    def test_delegate_with_list_view(self, qtbot):
        """测试委托与 QListView 集成"""
        from PySide6.QtWidgets import QListView
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        from screenshot_tool.ui.history_list_model import HistoryListModel
        from screenshot_tool.core.history_item_data import HistoryItemData
        
        # 创建视图、模型和委托
        view = QListView()
        model = HistoryListModel()
        delegate = HistoryItemDelegate(view)
        
        view.setModel(model)
        view.setItemDelegate(delegate)
        
        # 添加测试数据
        item = HistoryItemData(
            id="test-1",
            preview_text="集成测试截图",
            timestamp="2025-01-15 10:30"
        )
        model.add_item(item)
        model.force_flush()
        
        # 验证设置成功
        assert view.model() is model
        assert view.itemDelegate() is delegate
        assert model.rowCount() == 1
    
    def test_delegate_uniform_item_sizes(self, qtbot):
        """测试委托支持统一条目大小优化"""
        from PySide6.QtWidgets import QListView
        from screenshot_tool.ui.history_item_delegate import HistoryItemDelegate
        
        view = QListView()
        delegate = HistoryItemDelegate(view)
        
        view.setItemDelegate(delegate)
        view.setUniformItemSizes(True)  # 关键优化设置
        
        # 验证统一大小设置
        assert view.uniformItemSizes() is True

