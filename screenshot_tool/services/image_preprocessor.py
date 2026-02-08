# =====================================================
# =============== 图像预处理器 ===============
# =====================================================

"""
图像预处理器 - 在 OCR 识别前对图像进行增强处理

专注于扁平图像优化，追求极速：
- 扁平图像放大：提升矮小图像的 OCR 识别率
- 边距填充：仅对扁平图像添加边距，帮助 OCR 检测文本边界
- 放大后锐化：恢复放大导致的模糊

Requirements: 1.1, 1.2, 1.3
"""

import time
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np

from screenshot_tool.core.async_logger import async_debug_log


def preprocess_log(message: str):
    """预处理器日志"""
    async_debug_log(message, "PREPROC")


@dataclass
class PreprocessingConfig:
    """预处理配置（精简版，专注扁平图像优化）
    
    Attributes:
        enabled: 是否启用预处理
        auto_upscale: 是否自动放大扁平图像
        min_height: 最小高度阈值（像素），低于此值必须放大
        target_height: 放大目标高度（像素），适合中文 OCR
        max_aspect_ratio: 最大宽高比阈值，超过此值且高度不足时触发放大
        extreme_aspect_ratio: 极端宽高比阈值，超过此值使用更激进的放大策略
        extreme_target_height: 极端扁平图像的放大目标高度
        upscale_sharpen: 放大后是否自动锐化（提升放大后的清晰度）
        padding_enabled: 是否启用边距填充（仅对扁平图像）
        padding_size: 边距大小（像素）
    """
    enabled: bool = True
    # 扁平图像处理配置
    auto_upscale: bool = True
    min_height: int = 32
    target_height: int = 300
    max_aspect_ratio: float = 5.0
    extreme_aspect_ratio: float = 6.0
    extreme_target_height: int = 600
    upscale_sharpen: bool = True
    padding_enabled: bool = True
    padding_size: int = 30
    
    # 参数边界常量
    MIN_HEIGHT_LOWER = 8
    MIN_HEIGHT_UPPER = 128
    TARGET_HEIGHT_LOWER = 32
    TARGET_HEIGHT_UPPER = 600
    MAX_ASPECT_RATIO_LOWER = 2.0
    MAX_ASPECT_RATIO_UPPER = 50.0
    EXTREME_ASPECT_RATIO_LOWER = 4.0
    EXTREME_ASPECT_RATIO_UPPER = 100.0
    EXTREME_TARGET_HEIGHT_LOWER = 100
    EXTREME_TARGET_HEIGHT_UPPER = 800
    PADDING_SIZE_LOWER = 0
    PADDING_SIZE_UPPER = 50
    
    # 兼容性：保留旧配置字段（忽略）
    contrast_enhancement: bool = False
    sharpening: bool = False
    binarization: bool = False
    use_otsu: bool = False
    denoise: bool = False
    low_contrast_mode: bool = False
    clahe_clip_limit: float = 2.0
    clahe_grid_size: int = 8
    sharpen_strength: float = 1.0
    low_contrast_threshold: float = 0.4
    
    def __post_init__(self):
        """验证并规范化配置参数"""
        self.enabled = bool(self.enabled)
        self.auto_upscale = bool(self.auto_upscale)
        self.upscale_sharpen = bool(self.upscale_sharpen)
        self.padding_enabled = bool(self.padding_enabled)
        
        # 验证 min_height 范围
        if not isinstance(self.min_height, int):
            try:
                self.min_height = int(self.min_height)
            except (ValueError, TypeError):
                self.min_height = 32
        self.min_height = max(self.MIN_HEIGHT_LOWER, 
                               min(self.MIN_HEIGHT_UPPER, self.min_height))
        
        # 验证 target_height 范围
        if not isinstance(self.target_height, int):
            try:
                self.target_height = int(self.target_height)
            except (ValueError, TypeError):
                self.target_height = 300
        self.target_height = max(self.TARGET_HEIGHT_LOWER, 
                                  min(self.TARGET_HEIGHT_UPPER, self.target_height))
        
        # 验证 max_aspect_ratio 范围
        if not isinstance(self.max_aspect_ratio, (int, float)):
            self.max_aspect_ratio = 5.0
        self.max_aspect_ratio = max(self.MAX_ASPECT_RATIO_LOWER, 
                                     min(self.MAX_ASPECT_RATIO_UPPER, float(self.max_aspect_ratio)))
        
        # 验证 extreme_aspect_ratio 范围
        if not isinstance(self.extreme_aspect_ratio, (int, float)):
            self.extreme_aspect_ratio = 6.0
        self.extreme_aspect_ratio = max(self.EXTREME_ASPECT_RATIO_LOWER,
                                         min(self.EXTREME_ASPECT_RATIO_UPPER, float(self.extreme_aspect_ratio)))
        
        # 验证 extreme_target_height 范围
        if not isinstance(self.extreme_target_height, int):
            try:
                self.extreme_target_height = int(self.extreme_target_height)
            except (ValueError, TypeError):
                self.extreme_target_height = 600
        self.extreme_target_height = max(self.EXTREME_TARGET_HEIGHT_LOWER,
                                          min(self.EXTREME_TARGET_HEIGHT_UPPER, self.extreme_target_height))
        
        # 验证 padding_size 参数
        if not isinstance(self.padding_size, int):
            try:
                self.padding_size = int(self.padding_size)
            except (ValueError, TypeError):
                self.padding_size = 30
        self.padding_size = max(self.PADDING_SIZE_LOWER, 
                                 min(self.PADDING_SIZE_UPPER, self.padding_size))
        
        # 确保 target_height >= min_height
        if self.target_height < self.min_height:
            self.target_height = self.min_height
        
        # 确保 extreme_target_height >= target_height
        if self.extreme_target_height < self.target_height:
            self.extreme_target_height = self.target_height
        
        # 确保 extreme_aspect_ratio > max_aspect_ratio
        if self.extreme_aspect_ratio <= self.max_aspect_ratio:
            self.extreme_aspect_ratio = self.max_aspect_ratio + 2.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于配置存储）"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreprocessingConfig":
        """从字典创建（自动验证参数）"""
        if data is None:
            return cls()
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class PreprocessingMetrics:
    """预处理性能指标（精简版）
    
    Attributes:
        total_time_ms: 总处理时间（毫秒）
        upscale_time_ms: 放大处理时间
        padding_time_ms: 边距填充处理时间
        sharpen_time_ms: 锐化处理时间
        steps_applied: 已应用的处理步骤列表
        original_size: 原始图像尺寸 (height, width)
        upscaled_size: 放大后图像尺寸 (height, width)
        was_upscaled: 是否进行了放大
        is_extreme_flat: 是否为极端扁平图像
        was_padded: 是否进行了边距填充
    """
    total_time_ms: float = 0.0
    upscale_time_ms: float = 0.0
    padding_time_ms: float = 0.0
    sharpen_time_ms: float = 0.0
    steps_applied: List[str] = field(default_factory=list)
    original_size: Tuple[int, int] = (0, 0)
    upscaled_size: Tuple[int, int] = (0, 0)
    was_upscaled: bool = False
    is_extreme_flat: bool = False
    was_padded: bool = False
    
    # 兼容性：保留旧字段（默认值）
    clahe_time_ms: float = 0.0
    binarize_time_ms: float = 0.0
    denoise_time_ms: float = 0.0
    contrast_score: float = 1.0
    is_low_contrast: bool = False


class PreprocessingError(Exception):
    """预处理错误基类"""
    pass


class UpscalingError(PreprocessingError):
    """放大处理错误"""
    pass


class SharpeningError(PreprocessingError):
    """锐化处理错误"""
    pass


class ImagePreprocessor:
    """图像预处理器（精简版，专注扁平图像优化）
    
    在 OCR 识别前对扁平图像进行放大和边距填充，提升识别率。
    对于正常尺寸的图像，直接返回原图，追求极速。
    """
    
    def __init__(self, config: PreprocessingConfig = None):
        """
        初始化预处理器
        
        Args:
            config: 预处理配置，为 None 时使用默认配置
        """
        self.config = config or PreprocessingConfig()
        preprocess_log(f"预处理器初始化，配置: enabled={self.config.enabled}")
    
    def set_config(self, config: PreprocessingConfig):
        """更新预处理配置"""
        self.config = config
        preprocess_log(f"预处理配置已更新: enabled={config.enabled}")
    
    def get_config(self) -> PreprocessingConfig:
        """获取当前配置"""
        return self.config

    def is_flat_image(self, image: np.ndarray) -> bool:
        """
        检测图像是否为扁平图像（需要放大）
        
        扁平图像定义：
        1. 高度 < min_height（太矮）
        2. 高度 < target_height 且 宽高比 > max_aspect_ratio（扁平）
        
        Args:
            image: BGR 格式的 numpy 数组
            
        Returns:
            True 如果图像是扁平图像，否则 False
        """
        if image is None or image.size == 0:
            return False
        
        height = image.shape[0]
        width = image.shape[1]
        
        if height == 0:
            return True
        
        aspect_ratio = width / height
        
        is_flat = (
            height < self.config.min_height or
            (height < self.config.target_height and aspect_ratio > self.config.max_aspect_ratio)
        )
        
        return is_flat

    def upscale_flat_image(self, image: np.ndarray) -> Tuple[np.ndarray, bool, bool]:
        """
        放大扁平图像以提升 OCR 识别效果
        
        Args:
            image: BGR 格式的 numpy 数组
            
        Returns:
            Tuple[放大后的图像, 是否进行了放大, 是否为极端扁平图像]
            
        Raises:
            UpscalingError: 放大处理失败
        """
        if image is None or image.size == 0:
            return image, False, False
        
        height = image.shape[0]
        width = image.shape[1]
        
        if height == 0:
            return image, False, False
        
        aspect_ratio = width / height
        
        # 判断是否为极端扁平图像
        is_extreme_flat = aspect_ratio > self.config.extreme_aspect_ratio
        
        # 选择目标高度
        effective_target_height = (
            self.config.extreme_target_height if is_extreme_flat 
            else self.config.target_height
        )
        
        # 判断是否需要放大
        needs_upscale = (
            height < self.config.min_height or 
            (height < effective_target_height and aspect_ratio > self.config.max_aspect_ratio)
        )
        
        if not needs_upscale:
            return image, False, is_extreme_flat
        
        # 计算放大比例（只放大不缩小）
        scale = effective_target_height / height
        if scale <= 1.0:
            return image, False, is_extreme_flat
        
        new_height = effective_target_height
        new_width = max(1, int(width * scale))
        
        try:
            # 大倍数放大使用 LANCZOS4，小倍数使用 CUBIC
            interpolation = cv2.INTER_LANCZOS4 if scale > 2.0 else cv2.INTER_CUBIC
            upscaled = cv2.resize(image, (new_width, new_height), interpolation=interpolation)
            
            preprocess_log(f"扁平图像放大: {width}x{height} -> {new_width}x{new_height}, "
                          f"比例={scale:.2f}, 极端扁平={is_extreme_flat}")
            
            return upscaled, True, is_extreme_flat
            
        except cv2.error as e:
            raise UpscalingError(f"图像放大失败: {e}")

    def apply_padding(self, image: np.ndarray, is_extreme_flat: bool = False) -> Tuple[np.ndarray, bool]:
        """
        为扁平图像添加边距填充
        
        Args:
            image: BGR 格式的 numpy 数组
            is_extreme_flat: 是否为极端扁平图像
            
        Returns:
            Tuple[填充后的图像, 是否进行了填充]
        """
        if image is None or image.size == 0:
            return image, False
        
        if not self.config.padding_enabled or self.config.padding_size <= 0:
            return image, False
        
        padding = self.config.padding_size
        
        # 极端扁平图像：垂直方向使用更大的边距
        if is_extreme_flat:
            vertical_padding = padding * 3
            horizontal_padding = padding
        else:
            vertical_padding = padding
            horizontal_padding = padding
        
        try:
            h, w = image.shape[:2]
            
            # 检测背景色（取四角平均值）
            if len(image.shape) == 3:
                corners = [image[0, 0], image[0, w-1], image[h-1, 0], image[h-1, w-1]]
                bg_color = tuple(int(np.mean([c[i] for c in corners])) for i in range(3))
            else:
                corners = [image[0, 0], image[0, w-1], image[h-1, 0], image[h-1, w-1]]
                bg_color = int(np.mean(corners))
            
            padded = cv2.copyMakeBorder(
                image,
                vertical_padding, vertical_padding,
                horizontal_padding, horizontal_padding,
                cv2.BORDER_CONSTANT,
                value=bg_color
            )
            
            new_h, new_w = padded.shape[:2]
            preprocess_log(f"边距填充: {w}x{h} -> {new_w}x{new_h}, "
                          f"padding={padding}px, 极端扁平={is_extreme_flat}")
            
            return padded, True
            
        except Exception as e:
            preprocess_log(f"边距填充失败: {e}")
            return image, False

    def apply_sharpening(self, image: np.ndarray, strength: float = 0.5) -> np.ndarray:
        """
        应用锐化滤波（Unsharp Mask）
        
        Args:
            image: BGR 格式的 numpy 数组
            strength: 锐化强度 (0.0-2.0)
            
        Returns:
            锐化后的图像
            
        Raises:
            SharpeningError: 锐化处理失败
        """
        try:
            if image is None or image.size == 0:
                raise SharpeningError("输入图像为空")
            
            if strength <= 0:
                return image
            
            blurred = cv2.GaussianBlur(image, (0, 0), 3)
            sharpened = cv2.addWeighted(image, 1.0 + strength, blurred, -strength, 0)
            
            return sharpened
            
        except cv2.error as e:
            raise SharpeningError(f"锐化处理失败: {e}")

    def preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, PreprocessingMetrics]:
        """
        对图像进行预处理（精简版，专注扁平图像）
        
        处理流程：
        1. 检测是否为扁平图像
        2. 如果是扁平图像：放大 -> 边距填充 -> 锐化
        3. 如果不是扁平图像：直接返回原图（极速）
        
        Args:
            image: BGR 格式的 numpy 数组
            
        Returns:
            Tuple[处理后的图像, 处理指标]
        """
        metrics = PreprocessingMetrics()
        start_time = time.perf_counter()
        
        if image is None or image.size == 0:
            preprocess_log("预处理跳过：图像为空")
            return image, metrics
        
        if not self.config.enabled:
            preprocess_log("预处理已禁用")
            return image, metrics
        
        # 记录原始尺寸
        metrics.original_size = (image.shape[0], image.shape[1])
        metrics.upscaled_size = metrics.original_size
        
        # 检测是否为扁平图像
        is_flat = self.is_flat_image(image)
        
        # 非扁平图像：直接返回原图（极速路径）
        if not is_flat:
            metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
            return image, metrics
        
        result = image.copy()
        
        # 1. 扁平图像放大
        if self.config.auto_upscale:
            step_start = time.perf_counter()
            try:
                result, was_upscaled, is_extreme_flat = self.upscale_flat_image(result)
                metrics.upscale_time_ms = (time.perf_counter() - step_start) * 1000
                metrics.was_upscaled = was_upscaled
                metrics.is_extreme_flat = is_extreme_flat
                if was_upscaled:
                    metrics.upscaled_size = (result.shape[0], result.shape[1])
                    metrics.steps_applied.append("upscale")
            except PreprocessingError as e:
                preprocess_log(f"扁平图像放大失败: {e}")
                is_extreme_flat = False
        else:
            # 即使不放大，也检测是否为极端扁平图像
            h, w = result.shape[:2]
            is_extreme_flat = (w / h) > self.config.extreme_aspect_ratio if h > 0 else False
            metrics.is_extreme_flat = is_extreme_flat
        
        # 2. 放大后锐化（仅对放大后的图像）
        if metrics.was_upscaled and self.config.upscale_sharpen:
            step_start = time.perf_counter()
            try:
                # 极端扁平图像使用更强的锐化
                sharpen_strength = 0.8 if metrics.is_extreme_flat else 0.5
                result = self.apply_sharpening(result, strength=sharpen_strength)
                metrics.sharpen_time_ms = (time.perf_counter() - step_start) * 1000
                metrics.steps_applied.append("upscale_sharpen")
            except PreprocessingError as e:
                preprocess_log(f"放大后锐化失败: {e}")
        
        # 3. 边距填充（仅对扁平图像）
        if self.config.padding_enabled:
            step_start = time.perf_counter()
            result, was_padded = self.apply_padding(result, is_extreme_flat=metrics.is_extreme_flat)
            metrics.padding_time_ms = (time.perf_counter() - step_start) * 1000
            metrics.was_padded = was_padded
            if was_padded:
                metrics.steps_applied.append("padding")
        
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        
        if metrics.steps_applied:
            preprocess_log(f"预处理完成，总耗时: {metrics.total_time_ms:.2f}ms，步骤: {metrics.steps_applied}")
        
        return result, metrics
    
    def preprocess_safe(self, image: np.ndarray) -> Tuple[np.ndarray, PreprocessingMetrics]:
        """
        安全的预处理方法（捕获所有异常）
        
        Args:
            image: BGR 格式的 numpy 数组
            
        Returns:
            Tuple[处理后的图像（或原图）, 处理指标]
        """
        try:
            return self.preprocess(image)
        except Exception as e:
            preprocess_log(f"预处理异常，返回原图: {e}")
            return image, PreprocessingMetrics()
