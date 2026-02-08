# =====================================================
# =============== 历史条目数据类 ===============
# =====================================================

"""
历史条目数据类 - 高性能历史列表的纯数据模型

Feature: extreme-performance-optimization
Requirements: 11.1, 4.6

设计原则：
1. 使用 __slots__ 减少内存开销（比普通类节省约 40% 内存）
2. 纯数据类，不包含 Qt 对象
3. 支持类型提示
4. 兼容 Python 3.8+（不使用 dataclass + slots）
"""

from typing import Optional


class HistoryItemData:
    """历史条目数据（纯数据，无 Qt 对象）
    
    使用 __slots__ 优化内存使用，适用于大量历史条目的场景。
    
    Attributes:
        id: 唯一标识符
        preview_text: 预览文本（截图描述或 OCR 文本片段）
        timestamp: 时间戳字符串（如 "2025-01-15 10:30"）
        is_pinned: 是否置顶
        has_annotations: 是否有标注
        thumbnail_path: 缩略图路径（可选）
        content_type: 内容类型 ("image" 或 "text")
    
    Example:
        >>> item = HistoryItemData(
        ...     id="abc123",
        ...     preview_text="截图 - 桌面",
        ...     timestamp="2025-01-15 10:30",
        ...     is_pinned=False,
        ...     has_annotations=True,
        ...     thumbnail_path="/path/to/thumb.png",
        ...     content_type="image"
        ... )
        >>> item.preview_text
        '截图 - 桌面'
    """
    
    __slots__ = [
        'id',
        'preview_text', 
        'timestamp',
        'is_pinned',
        'has_annotations',
        'thumbnail_path',
        'content_type'
    ]
    
    def __init__(
        self,
        id: str,
        preview_text: str,
        timestamp: str,
        is_pinned: bool = False,
        has_annotations: bool = False,
        thumbnail_path: Optional[str] = None,
        content_type: str = "image"
    ) -> None:
        """初始化历史条目数据
        
        Args:
            id: 唯一标识符
            preview_text: 预览文本
            timestamp: 时间戳字符串
            is_pinned: 是否置顶，默认 False
            has_annotations: 是否有标注，默认 False
            thumbnail_path: 缩略图路径，默认 None
            content_type: 内容类型，默认 "image"
        """
        self.id = id
        self.preview_text = preview_text
        self.timestamp = timestamp
        self.is_pinned = is_pinned
        self.has_annotations = has_annotations
        self.thumbnail_path = thumbnail_path
        self.content_type = content_type
    
    def __repr__(self) -> str:
        """返回对象的字符串表示"""
        return (
            f"HistoryItemData("
            f"id={self.id!r}, "
            f"preview_text={self.preview_text!r}, "
            f"timestamp={self.timestamp!r}, "
            f"is_pinned={self.is_pinned}, "
            f"has_annotations={self.has_annotations}, "
            f"thumbnail_path={self.thumbnail_path!r}, "
            f"content_type={self.content_type!r})"
        )
    
    def __eq__(self, other: object) -> bool:
        """比较两个历史条目是否相等（基于 id）"""
        if not isinstance(other, HistoryItemData):
            return NotImplemented
        return self.id == other.id
    
    def __hash__(self) -> int:
        """返回哈希值（基于 id）"""
        return hash(self.id)
    
    def to_dict(self) -> dict:
        """转换为字典
        
        Returns:
            包含所有属性的字典
        """
        return {
            'id': self.id,
            'preview_text': self.preview_text,
            'timestamp': self.timestamp,
            'is_pinned': self.is_pinned,
            'has_annotations': self.has_annotations,
            'thumbnail_path': self.thumbnail_path,
            'content_type': self.content_type
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryItemData':
        """从字典创建实例
        
        Args:
            data: 包含属性的字典
            
        Returns:
            HistoryItemData 实例
        """
        return cls(
            id=data['id'],
            preview_text=data['preview_text'],
            timestamp=data['timestamp'],
            is_pinned=data.get('is_pinned', False),
            has_annotations=data.get('has_annotations', False),
            thumbnail_path=data.get('thumbnail_path'),
            content_type=data.get('content_type', 'image')
        )
