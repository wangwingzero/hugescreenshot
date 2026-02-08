# -*- coding: utf-8 -*-
"""
标注渲染器

将标注数据渲染到图像上。

Feature: screenshot-state-restore
Requirements: 3.3
"""

import math
from typing import List, Optional

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPolygon, QPainterPath
)


# 文字工具常量（与 overlay_screenshot.py 保持一致）
TEXT_FONT_FAMILY = "Microsoft YaHei"


class AnnotationRenderer:
    """标注渲染器
    
    将标注数据渲染到图像上。支持所有标注类型：
    - rect: 矩形
    - ellipse: 椭圆
    - arrow: 箭头
    - line: 直线
    - pen: 画笔
    - marker: 马克笔
    - text: 文字
    - mosaic: 马赛克
    - step: 步骤编号
    
    Feature: screenshot-state-restore
    Requirements: 3.3
    """
    
    # 马赛克块大小
    MOSAIC_BLOCK_SIZE = 10
    
    # 步骤编号默认直径
    STEP_DEFAULT_DIAMETER = 30
    
    @staticmethod
    def render(image: QImage, annotations: List[dict]) -> QImage:
        """渲染标注到图像
        
        Args:
            image: 原始图像
            annotations: 标注数据列表
            
        Returns:
            渲染后的图像（新副本）
        """
        if not annotations:
            return image.copy()
        
        # 创建图像副本
        result = image.copy()
        
        # 确保图像格式支持透明度
        if result.format() != QImage.Format.Format_ARGB32:
            result = result.convertToFormat(QImage.Format.Format_ARGB32)
        
        # 创建 QPainter
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        try:
            # 渲染每个标注
            for annotation in annotations:
                AnnotationRenderer.render_single(painter, annotation, result)
        finally:
            painter.end()
        
        return result
    
    @staticmethod
    def render_single(painter: QPainter, annotation: dict, image: Optional[QImage] = None) -> None:
        """渲染单个标注
        
        Args:
            painter: QPainter 对象
            annotation: 标注数据
            image: 原始图像（仅马赛克需要）
        """
        tool = annotation.get("tool", "")
        color_str = annotation.get("color", "#FF0000")
        width = annotation.get("width", 2)
        points_data = annotation.get("points", [])
        text = annotation.get("text", "")
        step_number = annotation.get("step_number", 0)
        
        # 解析颜色
        color = QColor(color_str)
        
        # 转换点数据
        points = [QPoint(p[0], p[1]) for p in points_data]
        
        if not points:
            return
        
        # 根据工具类型渲染
        if tool == "rect":
            AnnotationRenderer._render_rect(painter, points, color, width)
        elif tool == "ellipse":
            AnnotationRenderer._render_ellipse(painter, points, color, width)
        elif tool == "arrow":
            AnnotationRenderer._render_arrow(painter, points, color, width)
        elif tool == "line":
            AnnotationRenderer._render_line(painter, points, color, width)
        elif tool == "pen":
            AnnotationRenderer._render_pen(painter, points, color, width)
        elif tool == "marker":
            AnnotationRenderer._render_marker(painter, points, color, width)
        elif tool == "text":
            AnnotationRenderer._render_text(painter, points, color, width, text)
        elif tool == "mosaic":
            AnnotationRenderer._render_mosaic(painter, points, image)
        elif tool == "step":
            AnnotationRenderer._render_step(painter, points, color, width, step_number)
    
    @staticmethod
    def _render_rect(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染矩形"""
        if len(points) < 2:
            return
        
        pen = QPen(color, width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        rect = QRect(points[0], points[-1]).normalized()
        painter.drawRect(rect)
    
    @staticmethod
    def _render_ellipse(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染椭圆"""
        if len(points) < 2:
            return
        
        pen = QPen(color, width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        rect = QRect(points[0], points[-1]).normalized()
        painter.drawEllipse(rect)
    
    @staticmethod
    def _render_arrow(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染箭头"""
        if len(points) < 2:
            return
        
        start = points[0]
        end = points[-1]
        
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))
        
        # 绘制线段
        painter.drawLine(start, end)
        
        # 计算箭头
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        
        if length < 1:
            return
        
        # 箭头大小与线条粗细相关
        arrow_size = max(10, width * 3)
        
        # 单位向量
        ux = dx / length
        uy = dy / length
        
        # 箭头两侧的点
        angle = math.pi / 6  # 30度
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        # 左侧点
        lx = end.x() - arrow_size * (ux * cos_a + uy * sin_a)
        ly = end.y() - arrow_size * (uy * cos_a - ux * sin_a)
        
        # 右侧点
        rx = end.x() - arrow_size * (ux * cos_a - uy * sin_a)
        ry = end.y() - arrow_size * (uy * cos_a + ux * sin_a)
        
        # 绘制箭头三角形
        arrow_polygon = QPolygon([
            end,
            QPoint(int(lx), int(ly)),
            QPoint(int(rx), int(ry)),
        ])
        painter.drawPolygon(arrow_polygon)
    
    @staticmethod
    def _render_line(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染直线"""
        if len(points) < 2:
            return
        
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        painter.drawLine(points[0], points[-1])
    
    @staticmethod
    def _render_pen(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染画笔路径"""
        if len(points) < 2:
            return
        
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        # 使用 QPainterPath 绘制平滑曲线
        path = QPainterPath()
        path.moveTo(points[0])
        
        for i in range(1, len(points)):
            path.lineTo(points[i])
        
        painter.drawPath(path)
    
    @staticmethod
    def _render_marker(painter: QPainter, points: List[QPoint], color: QColor, width: int) -> None:
        """渲染马克笔（半透明宽线条）"""
        if len(points) < 2:
            return
        
        # 马克笔使用半透明颜色
        marker_color = QColor(color)
        marker_color.setAlpha(100)
        
        # 马克笔线条更宽
        marker_width = max(width * 3, 15)
        
        pen = QPen(marker_color, marker_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        # 使用 QPainterPath 绘制
        path = QPainterPath()
        path.moveTo(points[0])
        
        for i in range(1, len(points)):
            path.lineTo(points[i])
        
        painter.drawPath(path)
    
    @staticmethod
    def _render_text(painter: QPainter, points: List[QPoint], color: QColor, font_size: int, text: str) -> None:
        """渲染文字"""
        if not points or not text:
            return
        
        # 设置字体
        # font_size 可能是旧格式的粗细级别（1-10）或新格式的字体大小（>10）
        if font_size <= 10:
            actual_font_size = 10 + (font_size - 1) * 2  # 转换为字体大小
        else:
            actual_font_size = font_size
        
        font = QFont(TEXT_FONT_FAMILY, actual_font_size)
        font.setBold(True)
        painter.setFont(font)
        
        # 设置颜色
        painter.setPen(QPen(color))
        
        # 绘制文字（points[0] 是基线位置）
        painter.drawText(points[0], text)
    
    @staticmethod
    def _render_mosaic(painter: QPainter, points: List[QPoint], image: Optional[QImage]) -> None:
        """渲染马赛克"""
        if len(points) < 2 or image is None:
            return
        
        rect = QRect(points[0], points[-1]).normalized()
        
        # 确保矩形在图像范围内
        img_rect = image.rect()
        rect = rect.intersected(img_rect)
        
        if rect.isEmpty():
            return
        
        block_size = AnnotationRenderer.MOSAIC_BLOCK_SIZE
        
        # 遍历每个马赛克块
        for y in range(rect.top(), rect.bottom(), block_size):
            for x in range(rect.left(), rect.right(), block_size):
                # 计算块的实际大小
                block_w = min(block_size, rect.right() - x)
                block_h = min(block_size, rect.bottom() - y)
                
                if block_w <= 0 or block_h <= 0:
                    continue
                
                # 计算块的平均颜色
                total_r, total_g, total_b = 0, 0, 0
                pixel_count = 0
                
                for py in range(y, min(y + block_h, image.height())):
                    for px in range(x, min(x + block_w, image.width())):
                        pixel = image.pixelColor(px, py)
                        total_r += pixel.red()
                        total_g += pixel.green()
                        total_b += pixel.blue()
                        pixel_count += 1
                
                if pixel_count > 0:
                    avg_color = QColor(
                        total_r // pixel_count,
                        total_g // pixel_count,
                        total_b // pixel_count
                    )
                    
                    # 填充块
                    painter.fillRect(x, y, block_w, block_h, avg_color)
    
    @staticmethod
    def _render_step(painter: QPainter, points: List[QPoint], color: QColor, width: int, step_number: int) -> None:
        """渲染步骤编号"""
        if not points:
            return
        
        center = points[0]
        
        # 直径（width 存储直径，如果太小则使用默认值）
        diameter = width if width > 10 else AnnotationRenderer.STEP_DEFAULT_DIAMETER
        diameter = max(20, min(100, diameter))
        radius = diameter // 2
        
        # 绘制圆形背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, radius, radius)
        
        # 绘制数字
        font_size = int(diameter * 0.6)
        font = QFont(TEXT_FONT_FAMILY, font_size)
        font.setBold(True)
        painter.setFont(font)
        
        # 白色文字
        painter.setPen(QPen(QColor(255, 255, 255)))
        
        # 计算文字位置（居中）
        text = str(step_number)
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)
        
        text_x = center.x() - text_rect.width() // 2
        text_y = center.y() + metrics.ascent() // 2 - 2
        
        painter.drawText(QPoint(text_x, text_y), text)
