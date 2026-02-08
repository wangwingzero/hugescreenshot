# =====================================================
# =============== 图像拼接服务 ===============
# =====================================================

"""
图像拼接服务 - 使用特征匹配算法拼接滚动截屏

Requirements: 2.4, 2.5, 2.7, 2.9, 3.4, 3.5, 6.4, 6.5, 8.1, 11.4
Features:
- 特征点检测 (ORB)
- 重叠区域检测
- 图像拼接算法
- 支持垂直、水平、自由方向
- 支持固定区域排除
- 支持向上/向下拼接
- 支持预览图生成
- 支持拼接失败回退
"""

import cv2
import numpy as np
from PySide6.QtGui import QImage
from typing import Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class StitchDirection(Enum):
    """拼接方向"""
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    FREE = "free"


@dataclass
class StitchFrame:
    """拼接帧数据
    
    用于滚动截图的增强拼接功能
    """
    image: QImage  # 原始图像
    offset: int = 0  # 相对于前一帧的偏移
    overlap_height: int = 0  # 与前一帧的重叠高度
    top_fixed_height: int = 0  # 顶部固定区域高度（需排除）
    bottom_fixed_height: int = 0  # 底部固定区域高度（需排除）
    is_first: bool = False  # 是否是第一帧
    is_last: bool = False  # 是否是最后一帧


@dataclass
class StitchResult:
    """拼接结果"""
    success: bool
    image: Optional[QImage] = None
    error: Optional[str] = None
    frame_count: int = 0
    fallback_frames: List[QImage] = field(default_factory=list)  # 拼接失败时的单独帧


def qimage_to_cv2(qimage: QImage) -> np.ndarray:
    """QImage 转 OpenCV 格式"""
    # 转换为 RGB888 格式
    qimage = qimage.convertToFormat(QImage.Format.Format_RGB888)
    
    width = qimage.width()
    height = qimage.height()
    bytes_per_line = qimage.bytesPerLine()
    
    # 获取图像数据
    ptr = qimage.bits()
    arr = np.array(ptr).reshape(height, bytes_per_line)
    
    # 裁剪到实际宽度（去除填充）
    arr = arr[:, :width * 3].reshape(height, width, 3)
    
    # RGB -> BGR
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv2_to_qimage(cv_img: np.ndarray) -> QImage:
    """OpenCV 格式转 QImage"""
    if len(cv_img.shape) == 2:
        # 灰度图
        height, width = cv_img.shape
        bytes_per_line = width
        return QImage(cv_img.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8).copy()
    else:
        # 彩色图
        height, width, channels = cv_img.shape
        # BGR -> RGB
        rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        bytes_per_line = channels * width
        return QImage(rgb_img.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()


class ImageStitcher:
    """图像拼接服务 - 使用特征匹配算法"""
    
    def __init__(self, direction: StitchDirection = StitchDirection.VERTICAL,
                 overlap_threshold: float = 0.3):
        """
        初始化拼接器
        
        Args:
            direction: 拼接方向
            overlap_threshold: 最小重叠比例阈值
        """
        self._direction = direction
        self._overlap_threshold = overlap_threshold
        self._frames: List[np.ndarray] = []
        
        # 创建 ORB 特征检测器
        self._orb = cv2.ORB_create(nfeatures=1000)
        
        # 创建特征匹配器
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    
    def add_frame(self, image: QImage) -> bool:
        """
        添加一帧图像
        
        Args:
            image: 要添加的图像
        
        Returns:
            bool: 是否成功检测到与前一帧的重叠区域
        """
        if image.isNull():
            return False
        
        cv_img = qimage_to_cv2(image)
        
        if len(self._frames) == 0:
            self._frames.append(cv_img)
            return True
        
        # 检测与前一帧的重叠
        has_overlap = self._detect_overlap(self._frames[-1], cv_img)
        
        if has_overlap:
            self._frames.append(cv_img)
            return True
        
        return False
    
    def _detect_overlap(self, img1: np.ndarray, img2: np.ndarray) -> bool:
        """检测两张图片是否有足够的重叠"""
        try:
            # 转灰度
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            # 检测特征点
            kp1, des1 = self._orb.detectAndCompute(gray1, None)
            kp2, des2 = self._orb.detectAndCompute(gray2, None)
            
            if des1 is None or des2 is None:
                return False
            
            if len(des1) < 10 or len(des2) < 10:
                return False
            
            # 匹配特征点
            matches = self._matcher.match(des1, des2)
            
            # 计算匹配比例
            match_ratio = len(matches) / min(len(kp1), len(kp2))
            
            return match_ratio >= self._overlap_threshold
        except Exception:
            return False

    def stitch(self) -> StitchResult:
        """
        执行拼接
        
        Returns:
            StitchResult: 拼接结果
        """
        if len(self._frames) == 0:
            return StitchResult(success=False, error="没有可拼接的帧")
        
        if len(self._frames) == 1:
            return StitchResult(
                success=True,
                image=cv2_to_qimage(self._frames[0]),
                frame_count=1
            )
        
        try:
            if self._direction == StitchDirection.VERTICAL:
                result = self._stitch_vertical()
            elif self._direction == StitchDirection.HORIZONTAL:
                result = self._stitch_horizontal()
            else:
                result = self._stitch_free()
            
            if result is not None:
                return StitchResult(
                    success=True,
                    image=cv2_to_qimage(result),
                    frame_count=len(self._frames)
                )
            else:
                return StitchResult(
                    success=False,
                    error="拼接失败",
                    frame_count=len(self._frames)
                )
        except Exception as e:
            return StitchResult(
                success=False,
                error=str(e),
                frame_count=len(self._frames)
            )
    
    def _stitch_vertical(self) -> Optional[np.ndarray]:
        """垂直拼接"""
        result = self._frames[0].copy()
        
        for i in range(1, len(self._frames)):
            result = self._stitch_two_images_vertical(result, self._frames[i])
            if result is None:
                return None
        
        return result
    
    def _stitch_horizontal(self) -> Optional[np.ndarray]:
        """水平拼接"""
        result = self._frames[0].copy()
        
        for i in range(1, len(self._frames)):
            result = self._stitch_two_images_horizontal(result, self._frames[i])
            if result is None:
                return None
        
        return result
    
    def _stitch_free(self) -> Optional[np.ndarray]:
        """自由方向拼接（使用 OpenCV Stitcher）"""
        try:
            stitcher = cv2.Stitcher_create(cv2.Stitcher_SCANS)
            status, result = stitcher.stitch(self._frames)
            
            if status == cv2.Stitcher_OK:
                return result
            else:
                # 降级到垂直拼接
                return self._stitch_vertical()
        except Exception:
            return self._stitch_vertical()
    
    def _stitch_two_images_vertical(self, img1: np.ndarray, img2: np.ndarray) -> Optional[np.ndarray]:
        """垂直拼接两张图片"""
        try:
            # 转灰度
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            # 检测特征点
            kp1, des1 = self._orb.detectAndCompute(gray1, None)
            kp2, des2 = self._orb.detectAndCompute(gray2, None)
            
            if des1 is None or des2 is None:
                # 简单拼接
                return np.vstack([img1, img2])
            
            # 匹配特征点
            matches = self._matcher.match(des1, des2)
            
            if len(matches) < 4:
                # 简单拼接
                return np.vstack([img1, img2])
            
            # 按距离排序
            matches = sorted(matches, key=lambda x: x.distance)
            
            # 计算重叠区域
            src_pts = np.float32([kp1[m.queryIdx].pt for m in matches[:50]]).reshape(-1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches[:50]]).reshape(-1, 2)
            
            # 计算 Y 方向偏移
            y_offsets = src_pts[:, 1] - dst_pts[:, 1]
            median_offset = int(np.median(y_offsets))
            
            # 计算重叠高度
            overlap_height = img1.shape[0] - median_offset
            
            if overlap_height <= 0:
                # 没有重叠，简单拼接
                return np.vstack([img1, img2])
            
            # 裁剪重叠区域
            new_height = img1.shape[0] + img2.shape[0] - overlap_height
            result = np.zeros((new_height, max(img1.shape[1], img2.shape[1]), 3), dtype=np.uint8)
            
            # 放置第一张图
            result[:img1.shape[0], :img1.shape[1]] = img1
            
            # 放置第二张图（去除重叠部分）
            start_y = img1.shape[0] - overlap_height
            result[start_y:start_y + img2.shape[0], :img2.shape[1]] = img2
            
            return result
        except Exception:
            # 出错时简单拼接
            return np.vstack([img1, img2])
    
    def _stitch_two_images_horizontal(self, img1: np.ndarray, img2: np.ndarray) -> Optional[np.ndarray]:
        """水平拼接两张图片"""
        try:
            # 转灰度
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            # 检测特征点
            kp1, des1 = self._orb.detectAndCompute(gray1, None)
            kp2, des2 = self._orb.detectAndCompute(gray2, None)
            
            if des1 is None or des2 is None:
                return np.hstack([img1, img2])
            
            # 匹配特征点
            matches = self._matcher.match(des1, des2)
            
            if len(matches) < 4:
                return np.hstack([img1, img2])
            
            matches = sorted(matches, key=lambda x: x.distance)
            
            # 计算重叠区域
            src_pts = np.float32([kp1[m.queryIdx].pt for m in matches[:50]]).reshape(-1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches[:50]]).reshape(-1, 2)
            
            # 计算 X 方向偏移
            x_offsets = src_pts[:, 0] - dst_pts[:, 0]
            median_offset = int(np.median(x_offsets))
            
            # 计算重叠宽度
            overlap_width = img1.shape[1] - median_offset
            
            if overlap_width <= 0:
                return np.hstack([img1, img2])
            
            # 裁剪重叠区域
            new_width = img1.shape[1] + img2.shape[1] - overlap_width
            result = np.zeros((max(img1.shape[0], img2.shape[0]), new_width, 3), dtype=np.uint8)
            
            result[:img1.shape[0], :img1.shape[1]] = img1
            
            start_x = img1.shape[1] - overlap_width
            result[:img2.shape[0], start_x:start_x + img2.shape[1]] = img2
            
            return result
        except Exception:
            return np.hstack([img1, img2])
    
    def get_frame_count(self) -> int:
        """获取已捕获的帧数"""
        return len(self._frames)
    
    def clear(self):
        """清空所有帧"""
        self._frames.clear()
    
    def set_direction(self, direction: StitchDirection):
        """设置拼接方向"""
        self._direction = direction



class EnhancedImageStitcher(ImageStitcher):
    """增强图像拼接器 - 支持滚动截图的高级功能
    
    Features:
    - 固定区域排除
    - 向上/向下拼接
    - 预览图生成
    - 拼接失败回退
    """
    
    def __init__(self, direction: StitchDirection = StitchDirection.VERTICAL,
                 overlap_threshold: float = 0.3):
        super().__init__(direction, overlap_threshold)
        self._stitch_frames: List[StitchFrame] = []
        self._preview_scale: float = 0.2  # 预览图缩放比例
    
    def add_frame(self, image: QImage) -> bool:
        """
        添加一帧图像（强制添加，不检测重叠）
        
        Args:
            image: 要添加的图像
        
        Returns:
            bool: 是否成功添加
        """
        if image.isNull():
            return False
        
        cv_img = qimage_to_cv2(image)
        self._frames.append(cv_img)
        return True
    
    def add_stitch_frame(self, frame: StitchFrame) -> bool:
        """
        添加拼接帧
        
        Args:
            frame: 拼接帧数据
        
        Returns:
            bool: 是否成功添加
        """
        if frame.image.isNull():
            return False
        
        self._stitch_frames.append(frame)
        
        # 同时添加到帧列表
        cv_img = qimage_to_cv2(frame.image)
        self._frames.append(cv_img)
        
        return True
    
    def stitch_with_fixed_regions(self, top_fixed: int = 0, 
                                   bottom_fixed: int = 0) -> StitchResult:
        """
        执行拼接（排除固定区域）
        
        Args:
            top_fixed: 顶部固定区域高度
            bottom_fixed: 底部固定区域高度
        
        Returns:
            StitchResult: 拼接结果
        """
        if len(self._frames) == 0:
            return StitchResult(success=False, error="没有可拼接的帧")
        
        if len(self._frames) == 1:
            return StitchResult(
                success=True,
                image=cv2_to_qimage(self._frames[0]),
                frame_count=1
            )
        
        try:
            result = self._stitch_vertical_with_fixed(top_fixed, bottom_fixed)
            
            if result is not None:
                return StitchResult(
                    success=True,
                    image=cv2_to_qimage(result),
                    frame_count=len(self._frames)
                )
            else:
                # 拼接失败，返回单独帧
                return self._create_fallback_result()
        except Exception as e:
            # 拼接失败，返回单独帧
            return self._create_fallback_result(str(e))
    
    def stitch_downward(self) -> StitchResult:
        """
        向下拼接（正常滚动方向）
        
        Returns:
            StitchResult: 拼接结果
        """
        return self.stitch()
    
    def stitch_upward(self) -> StitchResult:
        """
        向上拼接（反向滚动）
        
        Returns:
            StitchResult: 拼接结果
        """
        if len(self._frames) == 0:
            return StitchResult(success=False, error="没有可拼接的帧")
        
        if len(self._frames) == 1:
            return StitchResult(
                success=True,
                image=cv2_to_qimage(self._frames[0]),
                frame_count=1
            )
        
        try:
            # 反转帧顺序后拼接
            reversed_frames = self._frames[::-1]
            result = self._frames[0].copy()
            
            for i in range(1, len(reversed_frames)):
                result = self._stitch_two_images_vertical(reversed_frames[i], result)
                if result is None:
                    return self._create_fallback_result()
            
            if result is not None:
                return StitchResult(
                    success=True,
                    image=cv2_to_qimage(result),
                    frame_count=len(self._frames)
                )
            else:
                return self._create_fallback_result()
        except Exception as e:
            return self._create_fallback_result(str(e))
    
    def generate_preview(self, max_height: int = 400) -> Optional[QImage]:
        """
        生成预览图
        
        Args:
            max_height: 最大高度
        
        Returns:
            Optional[QImage]: 预览图像
        """
        if len(self._frames) == 0:
            return None
        
        try:
            # 先执行拼接
            result = self.stitch()
            
            if not result.success or result.image is None:
                return None
            
            # 缩放到预览大小
            preview = result.image
            if preview.height() > max_height:
                scale = max_height / preview.height()
                new_width = int(preview.width() * scale)
                preview = preview.scaled(new_width, max_height)
            
            return preview
        except Exception:
            return None
    
    def get_estimated_height(self) -> int:
        """
        获取估计的拼接后高度
        
        Returns:
            int: 估计高度
        """
        if len(self._frames) == 0:
            return 0
        
        if len(self._frames) == 1:
            return self._frames[0].shape[0]
        
        # 估算：第一帧高度 + 后续帧的非重叠部分
        total_height = self._frames[0].shape[0]
        
        for i in range(1, len(self._frames)):
            # 假设 30% 重叠
            non_overlap = int(self._frames[i].shape[0] * 0.7)
            total_height += non_overlap
        
        return total_height
    
    def _stitch_vertical_with_fixed(self, top_fixed: int, 
                                     bottom_fixed: int) -> Optional[np.ndarray]:
        """
        垂直拼接（排除固定区域）
        
        Args:
            top_fixed: 顶部固定区域高度
            bottom_fixed: 底部固定区域高度
        
        Returns:
            Optional[np.ndarray]: 拼接结果
        """
        if len(self._frames) < 2:
            return self._frames[0] if self._frames else None
        
        # 处理第一帧：保留顶部固定区域
        first_frame = self._frames[0].copy()
        
        # 处理中间帧：排除顶部和底部固定区域
        processed_frames = [first_frame]
        
        for i in range(1, len(self._frames)):
            frame = self._frames[i].copy()
            height = frame.shape[0]
            
            # 排除固定区域
            if top_fixed > 0 or bottom_fixed > 0:
                start_y = top_fixed
                end_y = height - bottom_fixed if bottom_fixed > 0 else height
                
                if end_y > start_y:
                    frame = frame[start_y:end_y, :]
            
            processed_frames.append(frame)
        
        # 拼接处理后的帧
        result = processed_frames[0]
        
        for i in range(1, len(processed_frames)):
            result = self._stitch_two_images_vertical(result, processed_frames[i])
            if result is None:
                return None
        
        # 处理最后一帧：保留底部固定区域
        if bottom_fixed > 0 and len(self._frames) > 1:
            last_frame = self._frames[-1]
            bottom_region = last_frame[-bottom_fixed:, :]
            result = np.vstack([result, bottom_region])
        
        return result
    
    def _create_fallback_result(self, error: str = None) -> StitchResult:
        """
        创建回退结果（返回单独帧）
        
        Args:
            error: 错误信息
        
        Returns:
            StitchResult: 包含单独帧的结果
        """
        fallback_frames = [cv2_to_qimage(frame) for frame in self._frames]
        
        return StitchResult(
            success=False,
            error=error or "拼接失败，返回单独帧",
            frame_count=len(self._frames),
            fallback_frames=fallback_frames
        )
    
    def clear(self):
        """清空所有帧"""
        super().clear()
        self._stitch_frames.clear()
    
    def get_stitch_frames(self) -> List[StitchFrame]:
        """获取所有拼接帧"""
        return self._stitch_frames.copy()
