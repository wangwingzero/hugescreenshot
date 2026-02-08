# =====================================================
# =============== 截图画布组件 ===============
# =====================================================

"""
ScreenshotCanvas - 截图画布组件

功能：
- 显示截图
- 支持鼠标绘制高亮区域
- 支持缩放和平移
- 支持撤销和清除高亮区域

坐标系说明：
- 原图坐标：图片的实际像素坐标
- 画布坐标：widget 上的显示坐标
- 转换公式（参考 extractor_manual.py）：
  - 画布 -> 原图: orig = (canvas - offset) / scale
  - 原图 -> 画布: canvas = orig * scale + offset
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, 
    QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent
)
from typing import List, Optional, Tuple

# 导入调试日志
try:
    from screenshot_tool.core.anki_debug_logger import anki_debug_log as _anki_log
except ImportError:
    def _anki_log(msg): print(f"[CANVAS] {msg}")


class ScreenshotCanvas(QWidget):
    """截图画布 - 显示截图并支持绘制高亮区域
    
    完全参考 extractor_manual.py 的实现，使用简单的坐标转换逻辑。
    """
    
    # 信号
    regionCreated = Signal(int, QRect)  # (region_index, rect) 新高亮区域创建
    regionUndone = Signal(int)          # (region_index) 撤销的区域索引
    regionsCleared = Signal()           # 所有区域被清除
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 图片相关
        self._image: Optional[QImage] = None
        self._scaled_image: Optional[QImage] = None  # 缓存缩放后的图片
        
        # 高亮区域列表 (原图坐标系)
        self._highlight_regions: List[Tuple[int, QRect]] = []  # [(index, rect), ...]
        self._next_region_index: int = 0
        
        # 缩放和平移（参考 extractor_manual.py）
        self._base_scale: float = 1.0      # 适应窗口的基础缩放
        self._zoom_level: float = 1.0      # 用户缩放级别
        self._img_scale: float = 1.0       # 实际缩放 = base_scale * zoom_level
        self._img_offset_x: int = 0        # 图片在画布上的 X 偏移
        self._img_offset_y: int = 0        # 图片在画布上的 Y 偏移
        self._img_display_w: int = 0       # 图片显示宽度
        self._img_display_h: int = 0       # 图片显示高度
        self._img_pan_x: int = 0           # 平移偏移 X
        self._img_pan_y: int = 0           # 平移偏移 Y
        
        # 绘制状态
        self._drawing: bool = False
        self._panning: bool = False
        self._start_point: Optional[QPoint] = None
        self._current_rect: Optional[QRect] = None
        self._pan_start: Optional[QPoint] = None
        
        # 延迟计算标记
        self._need_recalculate: bool = False
        self._recalculate_retry_count: int = 0
        
        # 高亮颜色
        self._highlight_fill_color = QColor(255, 255, 0, 100)  # 半透明黄色
        self._highlight_border_color = QColor(255, 165, 0, 200)  # 橙色边框
        self._current_rect_color = QColor(255, 165, 0, 150)  # 当前绘制矩形颜色
        
        # 设置鼠标追踪和光标
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 设置背景色
        self.setStyleSheet("background-color: #e0e0e0;")
    
    def set_image(self, image: QImage) -> None:
        """设置要显示的截图"""
        if image is None or image.isNull():
            self._image = None
            self._scaled_image = None
            self.update()
            return
        
        self._image = image.copy()
        self._scaled_image = None  # 清除缓存
        
        _anki_log(f"[Canvas] set_image: 原图={image.width()}x{image.height()}, "
                  f"widget={self.width()}x{self.height()}")
        
        # 重置状态
        self._highlight_regions.clear()
        self._next_region_index = 0
        self._zoom_level = 1.0
        self._img_pan_x = 0
        self._img_pan_y = 0
        
        # 如果 widget 尺寸为 0，延迟计算
        if self.width() <= 0 or self.height() <= 0:
            _anki_log(f"[Canvas] widget 尺寸为 0，延迟计算缩放")
            self._need_recalculate = True
        else:
            self._need_recalculate = False
            self._calculate_scale()
        
        self.update()
    
    def _calculate_scale(self) -> None:
        """计算缩放比例（参考 extractor_manual.py）"""
        if self._image is None:
            return
        
        canvas_w = self.width() or 400
        canvas_h = self.height() or 300
        img_w = self._image.width()
        img_h = self._image.height()
        
        if img_w <= 0 or img_h <= 0:
            return
        
        # 计算基础缩放（适应窗口）
        self._base_scale = min(canvas_w / img_w, canvas_h / img_h)
        self._img_scale = self._base_scale * self._zoom_level
        self._img_display_w = int(img_w * self._img_scale)
        self._img_display_h = int(img_h * self._img_scale)
        
        # 计算居中偏移（考虑平移）
        self._img_offset_x = (canvas_w - self._img_display_w) // 2 + self._img_pan_x
        self._img_offset_y = (canvas_h - self._img_display_h) // 2 + self._img_pan_y
        
        _anki_log(f"[Canvas] _calculate_scale: canvas={canvas_w}x{canvas_h}, "
                  f"img={img_w}x{img_h}, base_scale={self._base_scale:.3f}, "
                  f"zoom={self._zoom_level:.2f}, scale={self._img_scale:.3f}, "
                  f"display={self._img_display_w}x{self._img_display_h}, "
                  f"offset=({self._img_offset_x},{self._img_offset_y})")
    
    def _canvas_to_image(self, canvas_x: int, canvas_y: int) -> Tuple[int, int]:
        """画布坐标转原图坐标（参考 extractor_manual.py）
        
        公式: orig = (canvas - offset) / scale
        """
        if self._image is None or self._img_scale <= 0:
            return (0, 0)
        
        img_x = int((canvas_x - self._img_offset_x) / self._img_scale)
        img_y = int((canvas_y - self._img_offset_y) / self._img_scale)
        
        # 限制在图片范围内
        img_x = max(0, min(img_x, self._image.width() - 1))
        img_y = max(0, min(img_y, self._image.height() - 1))
        
        return (img_x, img_y)
    
    def _image_to_canvas(self, img_x: int, img_y: int) -> Tuple[int, int]:
        """原图坐标转画布坐标（参考 extractor_manual.py）
        
        公式: canvas = orig * scale + offset
        """
        canvas_x = int(img_x * self._img_scale + self._img_offset_x)
        canvas_y = int(img_y * self._img_scale + self._img_offset_y)
        return (canvas_x, canvas_y)
    
    def _image_rect_to_canvas_rect(self, img_rect: QRect) -> QRect:
        """原图矩形转画布矩形"""
        x1, y1 = self._image_to_canvas(img_rect.x(), img_rect.y())
        x2, y2 = self._image_to_canvas(img_rect.x() + img_rect.width(), 
                                        img_rect.y() + img_rect.height())
        return QRect(x1, y1, x2 - x1, y2 - y1)
    
    # ==================== 高亮区域管理 ====================
    
    def add_region(self, rect: QRect) -> int:
        """添加高亮区域，返回区域索引"""
        index = self._next_region_index
        self._next_region_index += 1
        self._highlight_regions.append((index, rect))
        self.update()
        return index
    
    def get_image_with_highlights(self) -> Optional[QImage]:
        """获取带有高亮区域的图片（用于导出）"""
        if self._image is None or self._image.isNull():
            return None
        
        result = self._image.copy()
        
        if not self._highlight_regions:
            return result
        
        _anki_log(f"[Canvas] get_image_with_highlights: 原图={result.width()}x{result.height()}, "
                  f"高亮区域数={len(self._highlight_regions)}")
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        for idx, img_rect in self._highlight_regions:
            _anki_log(f"[Canvas] 绘制区域 {idx}: ({img_rect.x()},{img_rect.y()}) "
                      f"size={img_rect.width()}x{img_rect.height()}")
            
            # 填充半透明黄色
            painter.setBrush(QBrush(self._highlight_fill_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(img_rect)
            
            # 绘制橙色边框
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._highlight_border_color, 3))
            painter.drawRect(img_rect)
        
        painter.end()
        return result
    
    def undo_region(self) -> Optional[int]:
        """撤销最后一个高亮区域"""
        if not self._highlight_regions:
            return None
        
        index, _ = self._highlight_regions.pop()
        self.update()
        self.regionUndone.emit(index)
        return index
    
    def clear_regions(self) -> List[int]:
        """清除所有高亮区域"""
        indices = [idx for idx, rect in self._highlight_regions]
        self._highlight_regions.clear()
        self._next_region_index = 0
        self.update()
        self.regionsCleared.emit()
        return indices
    
    def get_regions(self) -> List[Tuple[int, QRect]]:
        """获取所有高亮区域"""
        return self._highlight_regions.copy()
    
    def get_region_count(self) -> int:
        """获取高亮区域数量"""
        return len(self._highlight_regions)
    
    # ==================== 缩放和平移 ====================
    
    def zoom_in(self) -> None:
        """放大"""
        self._zoom_level = min(self._zoom_level * 1.25, 5.0)
        self._apply_zoom()
    
    def zoom_out(self) -> None:
        """缩小"""
        self._zoom_level = max(self._zoom_level / 1.25, 0.2)
        self._apply_zoom()
    
    def zoom_reset(self) -> None:
        """重置缩放和平移"""
        self._zoom_level = 1.0
        self._img_pan_x = 0
        self._img_pan_y = 0
        self._apply_zoom()
    
    def _apply_zoom(self) -> None:
        """应用缩放（参考 extractor_manual.py 的 apply_zoom）"""
        if self._image is None:
            return
        
        self._img_scale = self._base_scale * self._zoom_level
        self._img_display_w = int(self._image.width() * self._img_scale)
        self._img_display_h = int(self._image.height() * self._img_scale)
        
        # 重新计算居中偏移
        canvas_w = self.width() or 400
        canvas_h = self.height() or 300
        self._img_offset_x = (canvas_w - self._img_display_w) // 2 + self._img_pan_x
        self._img_offset_y = (canvas_h - self._img_display_h) // 2 + self._img_pan_y
        
        # 清除缓存的缩放图片，下次 paintEvent 时重新生成
        self._scaled_image = None
        
        self.update()
    
    def get_zoom_percent(self) -> int:
        """获取当前缩放百分比"""
        return int(self._zoom_level * 100)
    
    # ==================== 鼠标事件 ====================
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标按下"""
        if self._image is None:
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            # Ctrl+左键 = 平移
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._panning = True
                self._pan_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                # 开始绘制高亮区域
                self._drawing = True
                self._start_point = event.pos()
                self._current_rect = QRect(event.pos(), event.pos())
        
        elif event.button() == Qt.MouseButton.RightButton:
            # 右键撤销
            self.undo_region()
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动"""
        if self._drawing and self._start_point is not None:
            self._current_rect = QRect(self._start_point, event.pos()).normalized()
            self.update()
        
        elif self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._img_pan_x += delta.x()
            self._img_pan_y += delta.y()
            self._pan_start = event.pos()
            
            # 更新居中偏移
            canvas_w = self.width() or 400
            canvas_h = self.height() or 300
            self._img_offset_x = (canvas_w - self._img_display_w) // 2 + self._img_pan_x
            self._img_offset_y = (canvas_h - self._img_display_h) // 2 + self._img_pan_y
            
            self.update()
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """鼠标释放"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drawing and self._current_rect is not None and self._start_point is not None:
                self._drawing = False
                
                # 获取画布坐标
                x1 = min(self._start_point.x(), event.pos().x())
                y1 = min(self._start_point.y(), event.pos().y())
                x2 = max(self._start_point.x(), event.pos().x())
                y2 = max(self._start_point.y(), event.pos().y())
                
                # 转换为原图坐标（参考 extractor_manual.py）
                orig_x1, orig_y1 = self._canvas_to_image(x1, y1)
                orig_x2, orig_y2 = self._canvas_to_image(x2, y2)
                
                img_rect = QRect(orig_x1, orig_y1, orig_x2 - orig_x1, orig_y2 - orig_y1)
                
                _anki_log(f"[Canvas] mouseReleaseEvent: canvas=({x1},{y1})->({x2},{y2}), "
                          f"img=({orig_x1},{orig_y1})->({orig_x2},{orig_y2}), "
                          f"rect={img_rect.width()}x{img_rect.height()}")
                
                # 添加区域并发送信号
                index = self.add_region(img_rect)
                self.regionCreated.emit(index, img_rect)
                
                self._current_rect = None
                self._start_point = None
                self.update()
            
            elif self._panning:
                self._panning = False
                self._pan_start = None
                self.setCursor(Qt.CursorShape.CrossCursor)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """鼠标滚轮缩放 - 固定以图片中心为基准（简化版）"""
        if self._image is None:
            return
        
        # 更新缩放级别
        if event.angleDelta().y() > 0:
            self._zoom_level = min(self._zoom_level * 1.1, 5.0)
        else:
            self._zoom_level = max(self._zoom_level / 1.1, 0.2)
        
        self._apply_zoom()
    
    # ==================== 绘制 ====================
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 绘制背景
        painter.fillRect(self.rect(), QColor("#e0e0e0"))
        
        if self._image is None:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无图片")
            return
        
        # 绘制图片（使用缓存的缩放图片）
        if self._img_display_w > 0 and self._img_display_h > 0:
            # 如果缓存为空或尺寸不匹配，重新生成
            if (self._scaled_image is None or 
                self._scaled_image.width() != self._img_display_w or
                self._scaled_image.height() != self._img_display_h):
                self._scaled_image = self._image.scaled(
                    self._img_display_w, self._img_display_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            painter.drawImage(self._img_offset_x, self._img_offset_y, self._scaled_image)
        
        # 绘制已有的高亮区域
        for index, img_rect in self._highlight_regions:
            canvas_rect = self._image_rect_to_canvas_rect(img_rect)
            
            # 填充
            painter.setBrush(QBrush(self._highlight_fill_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(canvas_rect)
            
            # 边框
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._highlight_border_color, 2))
            painter.drawRect(canvas_rect)
        
        # 绘制当前正在绘制的矩形
        if self._drawing and self._current_rect is not None:
            painter.setBrush(QBrush(QColor(255, 255, 0, 80)))
            painter.setPen(QPen(self._current_rect_color, 2, Qt.PenStyle.DashLine))
            painter.drawRect(self._current_rect)
    
    def resizeEvent(self, event) -> None:
        """窗口大小变化"""
        super().resizeEvent(event)
        if self._need_recalculate or self._image is not None:
            self._recalculate_scale()
    
    def showEvent(self, event) -> None:
        """窗口显示事件"""
        super().showEvent(event)
        if self._image is not None and self._need_recalculate:
            QTimer.singleShot(50, self._recalculate_scale)
    
    def _recalculate_scale(self) -> None:
        """重新计算缩放"""
        if self._image is None:
            return
        
        if self.width() <= 0 or self.height() <= 0:
            if self._recalculate_retry_count < 10:
                self._recalculate_retry_count += 1
                QTimer.singleShot(100, self._recalculate_scale)
            return
        
        self._recalculate_retry_count = 0
        self._need_recalculate = False
        self._calculate_scale()
        self.update()


# ==================== 辅助函数 ====================

def extract_english_words(text: str) -> List[str]:
    """从文本中提取英文单词"""
    import re
    
    if not text:
        return []
    
    words = re.findall(r'[a-zA-Z]{2,}', text)
    
    seen = set()
    unique_words = []
    for word in words:
        word_lower = word.lower()
        if word_lower not in seen:
            seen.add(word_lower)
            unique_words.append(word_lower)
    
    return unique_words


# ==================== OCR 工作线程 ====================

from PySide6.QtCore import QThread, Signal as QtSignal


class RegionOCRWorker(QThread):
    """区域 OCR 工作线程"""
    
    finished = QtSignal(int, list)  # (region_index, words)
    error = QtSignal(int, str)      # (region_index, error_msg)
    
    def __init__(self, image: QImage, region_index: int, rect: QRect, parent=None):
        super().__init__(parent)
        self._image = image.copy() if image and not image.isNull() else None
        self._region_index = region_index
        self._rect = rect
        self._cancelled = False
    
    def cancel(self):
        """取消 OCR 任务"""
        self._cancelled = True
    
    def _safe_emit_finished(self, region_index: int, words: list):
        """安全地发送 finished 信号"""
        if self._cancelled:
            return
        self._wait_for_modal_dialog()
        if not self._cancelled:
            self.finished.emit(region_index, words)
    
    def _safe_emit_error(self, region_index: int, error_msg: str):
        """安全地发送 error 信号"""
        if self._cancelled:
            return
        # 注意：移除了模态对话框等待，截图画布使用 WindowStaysOnTopHint
        if not self._cancelled:
            self.error.emit(region_index, error_msg)
    
    def run(self):
        """执行 OCR 识别"""
        if self._cancelled:
            return
        
        try:
            if self._image is None or self._image.isNull():
                if not self._cancelled:
                    self._safe_emit_error(self._region_index, "图片为空")
                return
            
            # 扩展裁剪区域边界，提高 OCR 识别率
            margin = 10
            x = max(0, self._rect.x() - margin)
            y = max(0, self._rect.y() - margin)
            w = min(self._image.width() - x, self._rect.width() + margin * 2)
            h = min(self._image.height() - y, self._rect.height() + margin * 2)
            
            expanded_rect = QRect(x, y, w, h)
            cropped = self._image.copy(expanded_rect)
            
            # 裁剪完成后释放原图引用
            self._image = None
            
            if cropped.isNull():
                if not self._cancelled:
                    self._safe_emit_error(self._region_index, "裁剪区域为空")
                return
            
            if self._cancelled:
                return
            
            # 使用 BackgroundOCRManager 的共享 OCR 服务实例，避免重复加载模型
            from screenshot_tool.core.background_ocr_manager import OCRWorkerThread
            ocr_service = OCRWorkerThread.get_ocr_service()
            result = ocr_service.recognize_image(cropped)
            
            # 释放裁剪图片
            del cropped
            
            if self._cancelled:
                return
            
            if result.success and result.text:
                words = extract_english_words(result.text)
                self._safe_emit_finished(self._region_index, words)
            elif result.success:
                self._safe_emit_finished(self._region_index, [])
            else:
                self._safe_emit_error(self._region_index, result.error or "识别失败")
                
        except ImportError as e:
            if not self._cancelled:
                self._safe_emit_error(self._region_index, f"缺少依赖: {str(e)}")
        except Exception as e:
            if not self._cancelled:
                self._safe_emit_error(self._region_index, f"OCR 异常: {str(e)}")
        finally:
            # 确保图片引用被释放
            self._image = None
