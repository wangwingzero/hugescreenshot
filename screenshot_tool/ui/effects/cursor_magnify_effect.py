# =====================================================
# =============== 指针放大效果 ===============
# =====================================================

"""
指针放大效果 - 放大显示鼠标指针

使用 Windows API 获取当前鼠标指针图标并放大绘制。

Feature: mouse-highlight
Requirements: 6.1, 6.2, 6.3, 6.4
"""

import ctypes
import ctypes.wintypes as wintypes
from typing import Optional

from PySide6.QtGui import QPainter, QPixmap, QImage
from PySide6.QtCore import QRect, Qt

from screenshot_tool.ui.effects.base_effect import BaseEffect
from screenshot_tool.core.async_logger import async_debug_log


# Windows API 结构和函数
class CURSORINFO(ctypes.Structure):
    """Windows CURSORINFO 结构"""
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("hCursor", ctypes.c_void_p),
        ("ptScreenPos", wintypes.POINT),
    ]


class ICONINFO(ctypes.Structure):
    """Windows ICONINFO 结构"""
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    """Windows BITMAPINFOHEADER 结构"""
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    """Windows BITMAPINFO 结构"""
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class BITMAP(ctypes.Structure):
    """Windows BITMAP 结构"""
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GetCursorInfo = user32.GetCursorInfo
GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
GetCursorInfo.restype = wintypes.BOOL

GetIconInfo = user32.GetIconInfo
GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ICONINFO)]
GetIconInfo.restype = wintypes.BOOL

CopyIcon = user32.CopyIcon
CopyIcon.argtypes = [ctypes.c_void_p]
CopyIcon.restype = ctypes.c_void_p

DestroyIcon = user32.DestroyIcon
DestroyIcon.argtypes = [ctypes.c_void_p]
DestroyIcon.restype = wintypes.BOOL

DrawIconEx = user32.DrawIconEx
DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                       ctypes.c_int, ctypes.c_int, ctypes.c_uint, wintypes.HBRUSH, ctypes.c_uint]
DrawIconEx.restype = wintypes.BOOL

GetObject = gdi32.GetObjectW
GetObject.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
GetObject.restype = ctypes.c_int

DeleteObject = gdi32.DeleteObject
DeleteObject.argtypes = [wintypes.HGDIOBJ]
DeleteObject.restype = wintypes.BOOL

GetDC = user32.GetDC
GetDC.argtypes = [wintypes.HWND]
GetDC.restype = wintypes.HDC

ReleaseDC = user32.ReleaseDC
ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
ReleaseDC.restype = ctypes.c_int

CreateCompatibleDC = gdi32.CreateCompatibleDC
CreateCompatibleDC.argtypes = [wintypes.HDC]
CreateCompatibleDC.restype = wintypes.HDC

CreateCompatibleBitmap = gdi32.CreateCompatibleBitmap
CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
CreateCompatibleBitmap.restype = wintypes.HBITMAP

DeleteDC = gdi32.DeleteDC
DeleteDC.argtypes = [wintypes.HDC]
DeleteDC.restype = wintypes.BOOL

SelectObject = gdi32.SelectObject
SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
SelectObject.restype = wintypes.HGDIOBJ

GetDIBits = gdi32.GetDIBits
GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint, 
                      ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
GetDIBits.restype = ctypes.c_int

# 常量
DI_NORMAL = 0x0003
BI_RGB = 0
DIB_RGB_COLORS = 0

# CreateDIBSection 函数
CreateDIBSection = gdi32.CreateDIBSection
CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_uint, 
                             ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
CreateDIBSection.restype = wintypes.HBITMAP


class CursorMagnifyEffect(BaseEffect):
    """指针放大效果
    
    获取当前鼠标指针图标并放大绘制。
    """
    
    def __init__(self, config, theme):
        super().__init__(config, theme)
        # 缓存的指针图像（实例变量而非类变量）
        self._cached_cursor_handle: Optional[int] = None
        self._cached_pixmap: Optional[QPixmap] = None
        self._cached_hotspot: tuple = (0, 0)
    
    def draw(self, painter: QPainter, mouse_x: int, mouse_y: int, screen_geometry: QRect):
        """绘制放大的鼠标指针
        
        Args:
            painter: QPainter 对象
            mouse_x: 鼠标本地 X 坐标
            mouse_y: 鼠标本地 Y 坐标
            screen_geometry: 屏幕几何区域
        """
        if not self._config.cursor_magnify_enabled:
            return
        
        scale = self._config.cursor_scale
        
        try:
            # 获取当前指针信息
            cursor_info = CURSORINFO()
            cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
            
            if not GetCursorInfo(ctypes.byref(cursor_info)):
                return
            
            # 检查指针是否可见
            CURSOR_SHOWING = 0x00000001
            if not (cursor_info.flags & CURSOR_SHOWING):
                return
            
            h_cursor = cursor_info.hCursor
            if not h_cursor:
                return
            
            # 检查缓存（光标句柄变化时重新获取）
            if h_cursor != self._cached_cursor_handle or self._cached_pixmap is None:
                pixmap, hotspot = self._get_cursor_pixmap(h_cursor)
                if pixmap and not pixmap.isNull():
                    self._cached_cursor_handle = h_cursor
                    self._cached_pixmap = pixmap
                    self._cached_hotspot = hotspot
            
            if self._cached_pixmap is None or self._cached_pixmap.isNull():
                return
            
            # 计算绘制位置（考虑热点和缩放）
            hotspot_x, hotspot_y = self._cached_hotspot
            scaled_width = int(self._cached_pixmap.width() * scale)
            scaled_height = int(self._cached_pixmap.height() * scale)
            
            draw_x = mouse_x - int(hotspot_x * scale)
            draw_y = mouse_y - int(hotspot_y * scale)
            
            # 绘制放大的指针
            painter.drawPixmap(
                draw_x, draw_y,
                scaled_width, scaled_height,
                self._cached_pixmap
            )
            
        except Exception as e:
            async_debug_log(f"指针放大效果绘制失败: {e}")
    
    def _get_cursor_pixmap(self, h_cursor: int) -> tuple:
        """获取指针的 QPixmap
        
        使用 DrawIconEx 将光标绘制到内存 DC，然后转换为 QPixmap。
        
        Args:
            h_cursor: 指针句柄
            
        Returns:
            (QPixmap, (hotspot_x, hotspot_y)) 或 (None, (0, 0))
        """
        h_icon = None
        icon_info = ICONINFO()
        hdc_screen = None
        hdc_mem = None
        h_bitmap = None
        old_bitmap = None
        
        try:
            # 复制指针（避免影响原始指针）
            h_icon = CopyIcon(h_cursor)
            if not h_icon:
                return None, (0, 0)
            
            # 获取图标信息
            if not GetIconInfo(h_icon, ctypes.byref(icon_info)):
                return None, (0, 0)
            
            hotspot = (icon_info.xHotspot, icon_info.yHotspot)
            
            # 获取位图尺寸
            bm = BITMAP()
            h_bm_source = icon_info.hbmColor if icon_info.hbmColor else icon_info.hbmMask
            
            if not h_bm_source:
                return None, (0, 0)
            
            if not GetObject(h_bm_source, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
                return None, (0, 0)
            
            width = bm.bmWidth
            height = bm.bmHeight
            
            # 如果只有 mask，高度是实际高度的两倍
            if not icon_info.hbmColor:
                height = height // 2
            
            # 确保尺寸合理
            if width <= 0 or height <= 0 or width > 256 or height > 256:
                width = 32
                height = 32
            
            # 创建兼容 DC
            hdc_screen = GetDC(None)
            if not hdc_screen:
                return None, (0, 0)
            
            hdc_mem = CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                return None, (0, 0)
            
            # 创建 32 位 DIB 位图（支持 Alpha 通道）
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # 负值表示自上而下
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB
            
            # 创建 DIB Section
            ppvBits = ctypes.c_void_p()
            h_bitmap = CreateDIBSection(
                hdc_screen,
                ctypes.byref(bmi),
                DIB_RGB_COLORS,
                ctypes.byref(ppvBits),
                None,
                0
            )
            
            if not h_bitmap or not ppvBits:
                return None, (0, 0)
            
            old_bitmap = SelectObject(hdc_mem, h_bitmap)
            
            # 填充透明背景（全 0，即透明黑色）
            buffer_size = width * height * 4
            ctypes.memset(ppvBits, 0, buffer_size)
            
            # 绘制光标到内存 DC
            if not DrawIconEx(hdc_mem, 0, 0, h_icon, width, height, 0, None, DI_NORMAL):
                return None, (0, 0)
            
            # 直接从 DIB 内存读取像素数据
            pixel_buffer = (ctypes.c_ubyte * buffer_size).from_address(ppvBits.value)
            
            # 转换为 QImage
            # Windows DIB 是 BGRA 格式，Qt 需要 ARGB32_Premultiplied
            image = QImage(bytes(pixel_buffer), width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied)
            image = image.copy()  # 确保数据独立
            
            pixmap = QPixmap.fromImage(image)
            return pixmap, hotspot
            
        except Exception as e:
            async_debug_log(f"获取指针图像失败: {e}")
            return None, (0, 0)
            
        finally:
            # 清理资源
            if old_bitmap and hdc_mem:
                SelectObject(hdc_mem, old_bitmap)
            if h_bitmap:
                DeleteObject(h_bitmap)
            if hdc_mem:
                DeleteDC(hdc_mem)
            if hdc_screen:
                ReleaseDC(None, hdc_screen)
            if icon_info.hbmMask:
                DeleteObject(icon_info.hbmMask)
            if icon_info.hbmColor:
                DeleteObject(icon_info.hbmColor)
            if h_icon:
                DestroyIcon(h_icon)
