# =====================================================
# =============== 截图管理器 ===============
# =====================================================

"""
截图管理器 - 负责屏幕截图的捕获和管理

Requirements: 1.1, 1.2, 1.4
Property 1: Screenshot Capture Returns Valid Data
"""

import time
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtGui import QGuiApplication, QPixmap, QImage, QClipboard
from PySide6.QtCore import QBuffer, QIODevice


@dataclass
class ScreenCapture:
    """截图数据"""
    pixmap: QPixmap
    screen_name: str
    width: int
    height: int
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """检查截图是否有效"""
        return self.error is None and self.width > 0 and self.height > 0


class ScreenshotManager:
    """截图管理器"""
    
    def __init__(self):
        """初始化截图管理器"""
        self._clipboard = QGuiApplication.clipboard()
    
    def capture_all_screens(self, wait: float = 0) -> List[ScreenCapture]:
        """
        捕获所有屏幕的截图
        
        Args:
            wait: 延迟时间（秒），用于等待窗口最小化等操作
            
        Returns:
            List[ScreenCapture]: 截图列表，每项包含 pixmap, screen_name, width, height
        """
        if wait > 0:
            time.sleep(wait)
        
        captures = []
        
        try:
            screens = QGuiApplication.screens()
            
            if not screens:
                return [ScreenCapture(
                    pixmap=QPixmap(),
                    screen_name="",
                    width=0,
                    height=0,
                    error="[Error] 没有可用的屏幕"
                )]
            
            for screen in screens:
                name = screen.name()
                
                try:
                    # 获取截图
                    pixmap = screen.grabWindow(0)
                    width = pixmap.width()
                    height = pixmap.height()
                    
                    # 检查截图是否有效
                    if width <= 0 or height <= 0:
                        captures.append(ScreenCapture(
                            pixmap=pixmap,
                            screen_name=name,
                            width=width,
                            height=height,
                            error=f"[Error] 截图尺寸无效: width={width}, height={height}"
                        ))
                    else:
                        captures.append(ScreenCapture(
                            pixmap=pixmap,
                            screen_name=name,
                            width=width,
                            height=height,
                            error=None
                        ))
                except Exception as e:
                    captures.append(ScreenCapture(
                        pixmap=QPixmap(),
                        screen_name=name,
                        width=0,
                        height=0,
                        error=f"[Error] 截图失败: {e}"
                    ))
            
            if not captures:
                return [ScreenCapture(
                    pixmap=QPixmap(),
                    screen_name="",
                    width=0,
                    height=0,
                    error="[Error] 截图列表为空"
                )]
            
            return captures
            
        except Exception as e:
            return [ScreenCapture(
                pixmap=QPixmap(),
                screen_name="",
                width=0,
                height=0,
                error=f"[Error] 截图异常: {e}"
            )]
    
    def capture_primary_screen(self, wait: float = 0) -> ScreenCapture:
        """
        捕获主屏幕的截图
        
        Args:
            wait: 延迟时间（秒）
            
        Returns:
            ScreenCapture: 主屏幕截图
        """
        if wait > 0:
            time.sleep(wait)
        
        try:
            screen = QGuiApplication.primaryScreen()
            
            if not screen:
                return ScreenCapture(
                    pixmap=QPixmap(),
                    screen_name="",
                    width=0,
                    height=0,
                    error="[Error] 没有主屏幕"
                )
            
            name = screen.name()
            pixmap = screen.grabWindow(0)
            width = pixmap.width()
            height = pixmap.height()
            
            if width <= 0 or height <= 0:
                return ScreenCapture(
                    pixmap=pixmap,
                    screen_name=name,
                    width=width,
                    height=height,
                    error=f"[Error] 截图尺寸无效: width={width}, height={height}"
                )
            
            return ScreenCapture(
                pixmap=pixmap,
                screen_name=name,
                width=width,
                height=height,
                error=None
            )
            
        except Exception as e:
            return ScreenCapture(
                pixmap=QPixmap(),
                screen_name="",
                width=0,
                height=0,
                error=f"[Error] 截图异常: {e}"
            )
    
    def capture_region(self, pixmap: QPixmap, x: int, y: int, w: int, h: int) -> Optional[QPixmap]:
        """
        从已有截图中裁剪指定区域
        
        Args:
            pixmap: 原始截图
            x, y: 左上角坐标
            w, h: 宽度和高度
            
        Returns:
            QPixmap: 裁剪后的截图，失败返回None
        """
        if pixmap.isNull():
            return None
        
        # 验证坐标
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return None
        
        # 边界检查
        img_width = pixmap.width()
        img_height = pixmap.height()
        
        if x >= img_width or y >= img_height:
            return None
        
        # 调整超出边界的尺寸
        if x + w > img_width:
            w = img_width - x
        if y + h > img_height:
            h = img_height - y
        
        try:
            return pixmap.copy(x, y, w, h)
        except Exception:
            return None
    
    def get_clipboard_image(self) -> Optional[QPixmap]:
        """
        从剪贴板获取图片
        
        Returns:
            QPixmap: 剪贴板中的图片，如果没有图片则返回None
        """
        try:
            mime_data = self._clipboard.mimeData()
            
            if mime_data.hasImage():
                image = self._clipboard.image()
                if not image.isNull():
                    return QPixmap.fromImage(image)
            
            return None
        except Exception:
            return None
    
    def set_clipboard_image(self, pixmap: QPixmap) -> bool:
        """
        将图片设置到剪贴板
        
        Args:
            pixmap: 要复制的图片
            
        Returns:
            bool: 是否成功
        """
        try:
            if pixmap.isNull():
                return False
            
            self._clipboard.setPixmap(pixmap)
            return True
        except Exception:
            return False
    
    @staticmethod
    def pixmap_to_image(pixmap: QPixmap) -> Optional[QImage]:
        """
        将QPixmap转换为QImage
        
        Args:
            pixmap: 要转换的QPixmap
            
        Returns:
            QImage: 转换后的QImage，失败返回None
        """
        if pixmap.isNull():
            return None
        
        try:
            return pixmap.toImage()
        except Exception:
            return None
    
    @staticmethod
    def image_to_pixmap(image: QImage) -> Optional[QPixmap]:
        """
        将QImage转换为QPixmap
        
        Args:
            image: 要转换的QImage
            
        Returns:
            QPixmap: 转换后的QPixmap，失败返回None
        """
        if image.isNull():
            return None
        
        try:
            return QPixmap.fromImage(image)
        except Exception:
            return None
    
    @staticmethod
    def pixmap_to_bytes(pixmap: QPixmap, format: str = "PNG") -> Optional[bytes]:
        """
        将QPixmap转换为字节数据
        
        Args:
            pixmap: 要转换的QPixmap
            format: 图片格式，默认PNG
            
        Returns:
            bytes: 图片字节数据，失败返回None
        """
        if pixmap.isNull():
            return None
        
        try:
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, format)
            return bytes(buffer.data())
        except Exception:
            return None
    
    @staticmethod
    def image_to_bytes(image: QImage, format: str = "PNG") -> Optional[bytes]:
        """
        将QImage转换为字节数据
        
        Args:
            image: 要转换的QImage
            format: 图片格式，默认PNG
            
        Returns:
            bytes: 图片字节数据，失败返回None
        """
        if image.isNull():
            return None
        
        try:
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            image.save(buffer, format)
            return bytes(buffer.data())
        except Exception:
            return None
