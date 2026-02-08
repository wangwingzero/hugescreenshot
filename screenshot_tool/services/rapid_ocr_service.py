# =====================================================
# =============== RapidOCR服务 ===============
# =====================================================

"""
RapidOCR服务 - 使用 OpenVINO 进行本地 OCR 识别

从 v1.9.0 开始，统一使用 OpenVINO 作为唯一的 OCR 推理后端。
实测表明 OpenVINO 在 Intel 和 AMD CPU 上都能正常工作且性能优秀。

Requirements: 
- pip install rapidocr-openvino

优化功能：
- 图像预处理：CLAHE 对比度增强、锐化滤波、自适应二值化
- OpenVINO 优化：Performance Hints、模型缓存
"""

import time
import threading
import traceback
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtGui import QImage

# ========== 异步调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

# ========== 预处理和后端选择 ==========
from screenshot_tool.services.image_preprocessor import (
    ImagePreprocessor,
    PreprocessingConfig,
    PreprocessingMetrics,
)
from screenshot_tool.services.backend_selector import (
    BackendSelector,
    BackendType,
    BackendInfo,
    get_backend_display_string as _get_backend_display_string,
)


def rapid_debug_log(message: str):
    """RapidOCR调试日志（使用异步日志器）"""
    async_debug_log(message, "RAPID")


# ========== 全局 OCR 实例管理 ==========
_global_ocr_instance = None
_global_ocr_error = None
_global_ocr_lock = threading.Lock()
_global_ocr_infer_lock = threading.Lock()  # 推理锁，防止 OpenVINO 并发冲突
_global_ocr_initialized = False
_global_backend_type: Optional[BackendType] = None

# ========== OCR 请求去重机制 ==========
# Bug fix (2026-01-23): 修复多个 OCR 任务同时运行导致内存暴涨的问题
# 使用图片哈希作为唯一标识，避免同一张图片被多次 OCR
_ocr_processing_lock = threading.Lock()  # 保护 _ocr_processing 和 _ocr_cache
_ocr_processing: dict = {}  # 正在处理的图片哈希 -> threading.Event
_ocr_cache: dict = {}  # 图片哈希 -> (OCRResult, timestamp)
_OCR_CACHE_MAX_SIZE = 10  # 最多缓存 10 个结果
_OCR_CACHE_TTL_SECONDS = 60  # 缓存有效期 60 秒


# ========== 模块隔离层 ==========
import sys

def clean_conflicting_modules(target_backend: Optional[str] = None) -> int:
    """
    清理可能冲突的 rapidocr 相关模块
    
    在导入 rapidocr 后端前调用，确保干净的导入环境。
    从 v1.9.0 开始，统一使用 OpenVINO 后端，此函数主要用于清理
    可能残留的共享子模块。
    
    Args:
        target_backend: 目标后端，默认为 "openvino"
    
    Returns:
        int: 清理的模块数量
    
    Requirements: 4.1, 4.2
    """
    # 共享的子模块（可能需要清理以确保干净的导入环境）
    shared_submodules = [
        'ch_ppocr_v2_cls',
        'ch_ppocr_v3_det',
        'ch_ppocr_v4_rec',
        'ch_ppocr_mobile_v2_cls',
        'ch_ppocr_server_v2_det',
        'ch_ppocr_v2_det',
        'ch_ppocr_v3_rec',
        'ch_ppocr_v4_det',
    ]
    
    prefixes_to_clean = shared_submodules
    
    modules_to_remove = []
    for module_name in list(sys.modules.keys()):
        for prefix in prefixes_to_clean:
            # 精确匹配或子模块匹配（prefix.submodule）
            if module_name == prefix or module_name.startswith(prefix + '.'):
                modules_to_remove.append(module_name)
                break
    
    for module_name in modules_to_remove:
        try:
            del sys.modules[module_name]
            rapid_debug_log(f"[模块隔离] 清理模块: {module_name}")
        except KeyError:
            pass  # 模块可能已被其他线程删除
    
    if modules_to_remove:
        rapid_debug_log(f"[模块隔离] 共清理 {len(modules_to_remove)} 个模块")
    
    return len(modules_to_remove)


def _create_ocr_instance_with_backend(preferred_backend: BackendType = None):
    """
    创建 RapidOCR 实例（内部函数），支持后端选择
    
    Args:
        preferred_backend: 首选后端类型，为 None 时自动选择
    
    Returns:
        tuple: (ocr_instance, error_message, actual_backend_type)
    """
    global _global_backend_type
    
    # 自动选择最优后端
    if preferred_backend is None:
        preferred_backend = BackendSelector.select_best_backend()
    
    rapid_debug_log(f"尝试使用 {preferred_backend.value} 后端...")
    
    errors_collected = []  # 收集所有错误信息，用于最终报告
    
    # 获取后端信息
    backend_info = BackendSelector.get_backend_info()
    
    rapid_debug_log("=" * 60)
    rapid_debug_log("[OCR后端] OCR 后端初始化开始")
    rapid_debug_log(f"[OCR后端] 首选后端: {preferred_backend.value}")
    rapid_debug_log(f"[OCR后端] CPU 厂商: {backend_info.cpu_vendor}, OpenVINO 可用: {backend_info.openvino_available}")
    
    # 清理可能冲突的模块（模块隔离层）
    # Requirements: 4.1, 4.2, 4.3
    # OpenVINO-only 架构：始终使用 OpenVINO
    cleaned_count = clean_conflicting_modules("openvino")
    if cleaned_count > 0:
        rapid_debug_log(f"[OCR后端] 模块隔离：已清理 {cleaned_count} 个冲突模块")
    
    # 使用 OpenVINO 后端
    rapid_debug_log("[OCR后端] 尝试 OpenVINO 后端...")
    try:
        # 先应用 OpenVINO 优化补丁（Performance Hints、模型缓存）
        try:
            from screenshot_tool.services.openvino_optimizer import (
                patch_rapidocr_openvino, OpenVINOConfig
            )
            
            # 创建配置
            config = OpenVINOConfig()
            patch_rapidocr_openvino(config)
            
            rapid_debug_log("[OCR后端] OpenVINO 优化补丁已应用 (设备: CPU)")
        except ImportError:
            rapid_debug_log("[OCR后端] OpenVINO 优化器不可用，使用默认配置")
        except Exception as e:
            rapid_debug_log(f"[OCR后端] 应用 OpenVINO 优化补丁失败: {e}")
        
        from rapidocr_openvino import RapidOCR
        rapid_debug_log("[OCR后端] rapidocr_openvino 导入成功")
        ocr = RapidOCR()
        _global_backend_type = BackendType.OPENVINO
        rapid_debug_log("[OCR后端] ★★★ RapidOCR (OpenVINO) 实例创建成功 ★★★")
        rapid_debug_log("=" * 60)
        return ocr, None, BackendType.OPENVINO
    except ImportError as e:
        error_detail = f"OpenVINO ImportError: {e}"
        rapid_debug_log(f"[OCR后端] OpenVINO 后端不可用: {e}")
        errors_collected.append(error_detail)
    except Exception as e:
        error_detail = f"OpenVINO 初始化失败: {e}\n{traceback.format_exc()}"
        rapid_debug_log(f"[OCR后端] OpenVINO 初始化失败: {e}")
        errors_collected.append(error_detail)
    
    # 所有后端都失败了，返回详细错误信息
    # Requirements: 5.1, 5.2
    rapid_debug_log("[OCR后端] ✗✗✗ OpenVINO 后端初始化失败 ✗✗✗")
    if errors_collected:
        error_details = "\n".join(f"  - {err}" for err in errors_collected)
        error_msg = f"""OCR引擎初始化失败，OpenVINO 后端不可用:
{error_details}

建议解决方案:
1. 检查 rapidocr-openvino 是否正确安装
2. 尝试重新安装: pip install --force-reinstall rapidocr-openvino
3. 如果问题持续，可以使用云端 OCR（百度云/腾讯云）作为备选"""
        for err in errors_collected:
            rapid_debug_log(f"[OCR后端] 错误: {err}")
    else:
        error_msg = """OCR引擎初始化失败: 未知错误

建议解决方案:
1. 检查 rapidocr-openvino 是否正确安装
2. 尝试重新安装: pip install --force-reinstall rapidocr-openvino
3. 如果问题持续，可以使用云端 OCR（百度云/腾讯云）作为备选"""
    
    rapid_debug_log(f"[OCR后端] 最终错误: {error_msg}")
    rapid_debug_log("=" * 60)
    return None, error_msg, None


def _create_ocr_instance():
    """
    创建 RapidOCR 实例（内部函数）- 兼容旧接口
    
    Returns:
        tuple: (ocr_instance, error_message)
    """
    global _global_backend_type
    ocr, error, backend_type = _create_ocr_instance_with_backend()
    # 确保 backend_type 被正确设置
    if backend_type is not None:
        _global_backend_type = backend_type
    return ocr, error


def get_global_ocr():
    """
    获取全局 OCR 实例（线程安全）
    
    Returns:
        tuple: (ocr_instance, error_message)
    """
    global _global_ocr_instance, _global_ocr_error, _global_ocr_initialized
    
    if _global_ocr_initialized:
        return _global_ocr_instance, _global_ocr_error
    
    with _global_ocr_lock:
        if _global_ocr_initialized:
            return _global_ocr_instance, _global_ocr_error
        
        _global_ocr_instance, _global_ocr_error = _create_ocr_instance()
        _global_ocr_initialized = True
        
        return _global_ocr_instance, _global_ocr_error


def warmup_ocr_engine() -> bool:
    """
    预热 OCR 引擎，执行一次 dummy inference
    
    在应用启动时调用，强制 JIT 编译和内存预分配，
    避免首次真实 OCR 请求时的冷启动延迟。
    
    Returns:
        bool: 预热是否成功
    """
    rapid_debug_log("=" * 50)
    rapid_debug_log("[OCR预热] 开始预热 OCR 引擎...")
    
    ocr, error = get_global_ocr()
    if ocr is None:
        rapid_debug_log(f"[OCR预热] OCR 引擎不可用: {error}")
        return False
    
    try:
        import time
        start_time = time.perf_counter()
        
        # 创建一个小的 dummy 图像 (100x30 灰色图像，模拟单行文本)
        # 使用较小的图像以减少预热时间，但足够触发完整的推理流程
        dummy_image = np.full((30, 100, 3), 200, dtype=np.uint8)
        
        # 执行一次推理（加锁防止并发冲突）
        with _global_ocr_infer_lock:
            result, elapse = ocr(dummy_image)
        
        warmup_time = (time.perf_counter() - start_time) * 1000
        rapid_debug_log(f"[OCR预热] 预热完成，耗时: {warmup_time:.2f}ms")
        rapid_debug_log(f"[OCR预热] 推理耗时: {elapse}")
        rapid_debug_log("=" * 50)
        
        # 清理 dummy 图像
        del dummy_image
        
        return True
        
    except Exception as e:
        rapid_debug_log(f"[OCR预热] 预热失败: {e}")
        rapid_debug_log("=" * 50)
        return False


def _compute_image_hash(image: 'QImage') -> int:
    """计算图片哈希值，用于 OCR 请求去重
    
    使用图片尺寸 + 采样像素点计算快速哈希，
    避免对整个图片数据进行哈希计算。
    
    Args:
        image: QImage 对象
        
    Returns:
        int: 图片哈希值
    """
    if image is None or image.isNull():
        return 0
    
    w, h = image.width(), image.height()
    if w == 0 or h == 0:
        return 0
    
    # 采样 5 个点的像素值
    sample_points = [
        (0, 0),                    # 左上
        (w - 1, 0),                # 右上
        (0, h - 1),                # 左下
        (w - 1, h - 1),            # 右下
        (w // 2, h // 2),          # 中心
    ]
    pixels = tuple(image.pixel(x, y) for x, y in sample_points)
    return hash((w, h) + pixels)


def _get_cached_ocr_result(image_hash: int) -> Optional['OCRResult']:
    """获取缓存的 OCR 结果
    
    Args:
        image_hash: 图片哈希值
        
    Returns:
        OCRResult 或 None（如果缓存不存在或已过期）
    """
    with _ocr_processing_lock:
        if image_hash in _ocr_cache:
            result, timestamp = _ocr_cache[image_hash]
            # 检查是否过期
            if time.time() - timestamp < _OCR_CACHE_TTL_SECONDS:
                rapid_debug_log(f"[OCR去重] 命中缓存: hash={image_hash}")
                return result
            else:
                # 过期，删除缓存
                del _ocr_cache[image_hash]
    return None


def _set_cached_ocr_result(image_hash: int, result: 'OCRResult') -> None:
    """设置 OCR 结果缓存
    
    Args:
        image_hash: 图片哈希值
        result: OCR 结果
    """
    with _ocr_processing_lock:
        # 如果缓存已满，删除最旧的条目
        if len(_ocr_cache) >= _OCR_CACHE_MAX_SIZE and _ocr_cache:
            # 找到最旧的条目
            oldest_hash = min(_ocr_cache.keys(), key=lambda k: _ocr_cache[k][1])
            del _ocr_cache[oldest_hash]
        
        _ocr_cache[image_hash] = (result, time.time())
        rapid_debug_log(f"[OCR去重] 缓存结果: hash={image_hash}, 当前缓存数={len(_ocr_cache)}")


def _try_acquire_ocr_slot(image_hash: int) -> Tuple[bool, Optional[threading.Event]]:
    """尝试获取 OCR 处理槽位
    
    如果图片正在被其他线程处理，返回 (False, event)，调用方可以等待 event。
    如果成功获取槽位，返回 (True, None)，调用方负责处理完成后调用 _release_ocr_slot。
    
    Args:
        image_hash: 图片哈希值
        
    Returns:
        (acquired, event): acquired=True 表示获取成功，event 用于等待其他线程完成
    """
    with _ocr_processing_lock:
        if image_hash in _ocr_processing:
            # 图片正在被其他线程处理，返回等待事件
            rapid_debug_log(f"[OCR去重] 图片正在处理中: hash={image_hash}")
            return False, _ocr_processing[image_hash]
        
        # 创建事件并占位
        event = threading.Event()
        _ocr_processing[image_hash] = event
        rapid_debug_log(f"[OCR去重] 获取处理槽位: hash={image_hash}")
        return True, None


def _release_ocr_slot(image_hash: int) -> None:
    """释放 OCR 处理槽位并通知等待的线程
    
    Args:
        image_hash: 图片哈希值
    """
    with _ocr_processing_lock:
        if image_hash in _ocr_processing:
            event = _ocr_processing.pop(image_hash)
            event.set()  # 通知所有等待的线程
            rapid_debug_log(f"[OCR去重] 释放处理槽位: hash={image_hash}")


@dataclass
class OCRBox:
    """OCR文字框"""
    text: str
    box: List[List[int]]  # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
    score: float = 1.0


def get_backend_display_string(
    backend_type: Optional[BackendType],
    backend_info: Optional[BackendInfo] = None
) -> str:
    """
    根据后端类型和配置生成显示字符串
    
    Args:
        backend_type: 后端类型
        backend_info: 后端详细信息
        
    Returns:
        显示字符串，如 "本地OCR"
    """
    # OpenVINO-only 架构：统一显示为 "本地OCR"
    return "本地OCR"


@dataclass
class OCRResult:
    """识别文字结果"""
    success: bool
    text: str = ""
    boxes: List[OCRBox] = field(default_factory=list)
    error: Optional[str] = None
    # 新增字段：OCR 评分和后端信息
    average_score: float = 0.0  # 平均置信度分数 (0.0-1.0)
    backend_type: Optional[str] = None  # 后端类型 (openvino)
    backend_detail: Optional[str] = None  # 后端详细信息（显示字符串）
    preprocessing_metrics: Optional[PreprocessingMetrics] = None  # 预处理指标
    elapsed_time_ms: float = 0.0  # OCR 实际处理耗时（毫秒），包含预处理+推理
    
    @classmethod
    def error_result(cls, error_msg: str) -> "OCRResult":
        """创建错误结果"""
        return cls(success=False, error=error_msg)
    
    @classmethod
    def empty_result(cls) -> "OCRResult":
        """创建空结果（成功但无文字）"""
        return cls(success=True, text="", boxes=[])



class RapidOCRService:
    """RapidOCR服务 - 本地OCR识别
    
    使用全局单例模式管理 OCR 实例，确保整个进程只有一个实例。
    支持图像预处理和后端选择优化。
    """
    
    def __init__(self, lang: str = "ch", 
                 preprocessing_config: PreprocessingConfig = None,
                 enable_preprocessing: bool = True):
        """
        初始化RapidOCR服务
        
        Args:
            lang: 识别语言 (ch, en 等，RapidOCR 默认支持中英文)
            preprocessing_config: 预处理配置，为 None 时使用默认配置
            enable_preprocessing: 是否启用预处理
        """
        self.lang = lang
        
        # 初始化预处理器
        if preprocessing_config is None:
            preprocessing_config = PreprocessingConfig(enabled=enable_preprocessing)
        self._preprocessor = ImagePreprocessor(preprocessing_config)
        
        rapid_debug_log(f"RapidOCR 服务初始化，预处理: {enable_preprocessing}")
    
    def set_preprocessing_config(self, config: PreprocessingConfig):
        """更新预处理配置"""
        self._preprocessor.set_config(config)
    
    def get_preprocessing_config(self) -> PreprocessingConfig:
        """获取预处理配置"""
        return self._preprocessor.get_config()
    
    @staticmethod
    def get_backend_type() -> Optional[BackendType]:
        """获取当前使用的后端类型"""
        return _global_backend_type
    
    @staticmethod
    def get_backend_info() -> BackendInfo:
        """获取后端详细信息"""
        return BackendSelector.get_backend_info()
    
    @staticmethod
    def _get_default_box() -> List[List[int]]:
        """返回默认空边界框的深拷贝"""
        return [[0, 0], [0, 0], [0, 0], [0, 0]]
    
    @classmethod
    def is_initialized(cls) -> bool:
        """检查 OCR 服务是否已初始化"""
        return _global_ocr_initialized
    
    @classmethod
    def has_instance(cls) -> bool:
        """检查是否有可用的 OCR 实例"""
        return _global_ocr_instance is not None
    
    @staticmethod
    def _parse_box_coords(raw_box) -> List[List[int]]:
        """
        解析边界框坐标
        
        Args:
            raw_box: 原始边界框数据
            
        Returns:
            标准化的边界框坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        """
        if raw_box is None:
            return RapidOCRService._get_default_box()
        
        try:
            if hasattr(raw_box, 'tolist'):
                raw_box = raw_box.tolist()
            
            if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
                return RapidOCRService._get_default_box()
            
            box = []
            for p in raw_box[:4]:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    box.append([int(float(p[0])), int(float(p[1]))])
            
            if len(box) < 4:
                return RapidOCRService._get_default_box()
            
            return box
        except (ValueError, TypeError, IndexError):
            return RapidOCRService._get_default_box()
    
    def _get_ocr(self):
        """获取全局 OCR 实例"""
        ocr, error = get_global_ocr()
        if ocr is None:
            raise RuntimeError(error or "OCR 引擎未初始化")
        return ocr
    
    def _qimage_to_numpy(self, image: QImage) -> Optional[np.ndarray]:
        """将QImage转换为numpy数组（BGR格式）
        
        注意：此方法会创建图片数据的副本，调用方应在使用完毕后
        及时删除返回的数组以释放内存。
        """
        if image is None or image.isNull():
            return None
        
        rgb_image = image.convertToFormat(QImage.Format.Format_RGB888)
        
        width = rgb_image.width()
        height = rgb_image.height()
        
        # 图片太小则跳过
        min_size = 10
        if width < min_size or height < min_size:
            rapid_debug_log(f"图片太小 ({width}x{height})，跳过OCR")
            return None
        
        bytes_per_line = rgb_image.bytesPerLine()
        ptr = rgb_image.bits()
        
        # 检查指针是否有效
        if ptr is None:
            rapid_debug_log("图片数据指针为空")
            return None
        
        try:
            # 计算预期的数据大小
            expected_size = height * bytes_per_line
            actual_size = len(ptr)
            
            if actual_size < expected_size:
                rapid_debug_log(f"图片数据不完整: 预期 {expected_size}, 实际 {actual_size}")
                return None
            
            if bytes_per_line == width * 3:
                arr = np.array(ptr, dtype=np.uint8).reshape(height, width, 3)
            else:
                raw_arr = np.array(ptr, dtype=np.uint8).reshape(height, bytes_per_line)
                arr = raw_arr[:, :width * 3].reshape(height, width, 3)
                del raw_arr  # 显式删除中间数组
        except ValueError as e:
            rapid_debug_log(f"图片数据转换失败: {e}")
            return None
        except Exception as e:
            rapid_debug_log(f"图片数据转换异常: {e}")
            return None
        
        # RGB -> BGR（原地操作，避免创建副本）
        # 使用 np.ascontiguousarray 一次性完成转换和内存布局优化
        arr = np.ascontiguousarray(arr[:, :, ::-1])
        
        return arr
    
    def check_service_available(self) -> Tuple[bool, Optional[str]]:
        """检查OCR服务是否可用"""
        ocr, error = get_global_ocr()
        if ocr is not None:
            return True, None
        return False, error or "OCR 引擎初始化失败"
    
    def recognize_image(self, image: QImage, language: str = None) -> OCRResult:
        """
        识别图片中的文字
        
        使用去重机制避免同一张图片被多次 OCR：
        1. 计算图片哈希
        2. 检查缓存是否有结果
        3. 检查是否有其他线程正在处理
        4. 如果都没有，执行 OCR 并缓存结果
        
        Args:
            image: 要识别的QImage
            language: 识别语言（忽略，RapidOCR 默认支持中英文）
            
        Returns:
            OCRResult: 识别文字结果
        """
        total_start = time.perf_counter()
        rapid_debug_log("=" * 50)
        rapid_debug_log("开始OCR识别")
        
        if image.isNull():
            rapid_debug_log("错误: 图片为空")
            return OCRResult.error_result("图片为空")
        
        rapid_debug_log(f"图片尺寸: {image.width()}x{image.height()}")
        
        # ========== OCR 请求去重 ==========
        # Bug fix (2026-01-23): 避免同一张图片被多次 OCR 导致内存暴涨
        image_hash = _compute_image_hash(image)
        
        # 1. 检查缓存
        cached_result = _get_cached_ocr_result(image_hash)
        if cached_result is not None:
            rapid_debug_log(f"[OCR去重] 使用缓存结果，跳过重复 OCR")
            return cached_result
        
        # 2. 尝试获取处理槽位
        acquired, wait_event = _try_acquire_ocr_slot(image_hash)
        if not acquired:
            # 其他线程正在处理，等待完成后返回缓存结果
            rapid_debug_log(f"[OCR去重] 等待其他线程完成...")
            wait_event.wait(timeout=30.0)  # 最多等待 30 秒
            
            # 等待完成后检查缓存
            cached_result = _get_cached_ocr_result(image_hash)
            if cached_result is not None:
                rapid_debug_log(f"[OCR去重] 等待完成，使用缓存结果")
                return cached_result
            else:
                # 其他线程可能失败了，继续执行 OCR
                rapid_debug_log(f"[OCR去重] 等待完成但无缓存，重新执行 OCR")
                # 重新获取槽位
                acquired, _ = _try_acquire_ocr_slot(image_hash)
                if not acquired:
                    # 仍然无法获取，返回错误
                    return OCRResult.error_result("OCR 请求冲突，请稍后重试")
        
        # 3. 执行 OCR（获取到槽位后）
        try:
            result = self._do_recognize_image(image)
            
            # 4. 缓存结果（成功和失败都缓存，避免重复请求）
            _set_cached_ocr_result(image_hash, result)
            
            return result
        except Exception as e:
            # 异常情况也要释放槽位
            rapid_debug_log(f"[OCR去重] OCR 执行异常: {e}")
            return OCRResult.error_result(f"OCR 执行异常: {e}")
        finally:
            # 5. 释放槽位
            _release_ocr_slot(image_hash)
    
    def _do_recognize_image(self, image: QImage) -> OCRResult:
        """实际执行 OCR 识别（内部方法，不含去重逻辑）"""
        total_start = time.perf_counter()
        
        # 检查 OCR 是否可用
        ocr, init_error = get_global_ocr()
        if ocr is None:
            rapid_debug_log(f"OCR 引擎不可用: {init_error}")
            return OCRResult.error_result(init_error or "OCR 引擎初始化失败")
        
        # 记录后端类型
        backend = self.get_backend_type()
        if backend:
            rapid_debug_log(f"使用后端: {backend.value}")
        
        img_array = None
        try:
            rapid_debug_log("转换图片为numpy数组...")
            img_array = self._qimage_to_numpy(image)
            if img_array is None:
                # 图片太小，返回空结果
                if image.width() < 10 or image.height() < 10:
                    rapid_debug_log("图片太小，返回空结果")
                    return OCRResult.empty_result()
                rapid_debug_log("错误: 图片转换失败")
                return OCRResult.error_result("图片转换失败")
            
            rapid_debug_log(f"numpy数组形状: {img_array.shape}")
            
            # 应用预处理
            preprocess_metrics = PreprocessingMetrics()
            if self._preprocessor.config.enabled:
                rapid_debug_log("应用图像预处理...")
                img_array, preprocess_metrics = self._preprocessor.preprocess_safe(img_array)
                if preprocess_metrics.steps_applied:
                    rapid_debug_log(f"预处理完成: {preprocess_metrics.steps_applied}, 耗时: {preprocess_metrics.total_time_ms:.2f}ms")
            
            rapid_debug_log("执行OCR识别...")
            ocr_start = time.perf_counter()
            
            # 检测是否为扁平图像，调整 OCR 参数
            is_flat_image = preprocess_metrics.was_upscaled
            is_extreme_flat = preprocess_metrics.is_extreme_flat
            
            # RapidOCR 调用（加锁防止 OpenVINO 并发冲突）
            with _global_ocr_infer_lock:
                if is_extreme_flat:
                    # 极端扁平图像：使用最激进的参数
                    # - box_thresh: 进一步降低检测阈值
                    # - unclip_ratio: 进一步增大文本框扩展比例
                    # - text_score: 进一步降低识别置信度阈值
                    rapid_debug_log("极端扁平图像模式：使用最激进参数 (box_thresh=0.2, unclip_ratio=2.0, text_score=0.2)")
                    result, elapse = ocr(img_array, box_thresh=0.2, unclip_ratio=2.0, text_score=0.2)
                elif is_flat_image:
                    # 扁平图像优化参数：
                    # - box_thresh: 降低检测阈值，召回更多文本框
                    # - unclip_ratio: 增大文本框扩展比例，避免文字被裁切
                    # - text_score: 降低识别置信度阈值
                    rapid_debug_log("扁平图像模式：使用优化参数 (box_thresh=0.3, unclip_ratio=1.8, text_score=0.3)")
                    result, elapse = ocr(img_array, box_thresh=0.3, unclip_ratio=1.8, text_score=0.3)
                else:
                    result, elapse = ocr(img_array)
            
            ocr_time = (time.perf_counter() - ocr_start) * 1000
            total_time = (time.perf_counter() - total_start) * 1000
            
            rapid_debug_log(f"OCR推理耗时: {ocr_time:.2f}ms")
            rapid_debug_log(f"总处理时间: {total_time:.2f}ms (预处理: {preprocess_metrics.total_time_ms:.2f}ms)")
            
            if result is None or len(result) == 0:
                rapid_debug_log("未识别到文本")
                return OCRResult.empty_result()
            
            # 解析结果
            ocr_result = self._parse_result(result)
            
            # 添加后端信息、预处理指标和实际耗时
            if ocr_result.success:
                ocr_result.backend_type = backend.value if backend else None
                backend_info = self.get_backend_info()
                ocr_result.backend_detail = get_backend_display_string(backend, backend_info)
                ocr_result.preprocessing_metrics = preprocess_metrics
                ocr_result.elapsed_time_ms = total_time  # 存储实际 OCR 处理耗时
            
            return ocr_result
            
        except ImportError as e:
            rapid_debug_log(f"ImportError: {str(e)}")
            return OCRResult.error_result(f"请安装依赖: {str(e)}")
        except Exception as e:
            rapid_debug_log(f"Exception: {str(e)}")
            rapid_debug_log(traceback.format_exc())
            return OCRResult.error_result(f"OCR识别出错: {str(e)}")
        finally:
            # 显式释放 numpy 数组内存
            if img_array is not None:
                del img_array

    
    def _parse_result(self, result: list) -> OCRResult:
        """解析RapidOCR的结果"""
        rapid_debug_log("解析Rapid识别文字结果...")
        
        result_boxes = []
        
        try:
            # RapidOCR 返回格式: [[box, text, score], ...]
            for i, item in enumerate(result):
                if not item or len(item) < 3:
                    continue
                
                box_points = item[0]
                text = str(item[1])
                
                try:
                    score = float(item[2])
                    # 确保分数在有效范围内
                    score = max(0.0, min(1.0, score))
                except (ValueError, TypeError):
                    score = 1.0
                
                box = self._parse_box_coords(box_points)
                result_boxes.append(OCRBox(text=text, box=box, score=score))
                
                text_preview = text[:30] + "..." if len(text) > 30 else text
                rapid_debug_log(f"  [{i}] {text_preview} (score: {score:.2f})")
            
            if not result_boxes:
                rapid_debug_log("未识别到文本")
                return OCRResult.empty_result()
            
            # 符号噪声过滤
            # 截图中 UI 图标（文件夹箭头、文件类型图标、状态图标等）常被误识别为符号字符
            # 过滤条件：文本仅含 1-2 个字符，且全部为非字母/数字/汉字的符号
            before_filter = len(result_boxes)
            result_boxes = [b for b in result_boxes if not self._is_symbol_noise(b.text)]
            noise_removed = before_filter - len(result_boxes)
            if noise_removed > 0:
                rapid_debug_log(f"符号噪声过滤：移除 {noise_removed} 个噪声区域（UI 图标误识别）")
            
            if not result_boxes:
                rapid_debug_log("过滤后无有效文本")
                return OCRResult.empty_result()
            
            # 合并同一行的文字框
            merged_boxes = self._merge_same_line_boxes(result_boxes)
            
            full_text = "\n".join([box.text for box in merged_boxes])
            
            # 计算平均分（使用合并后的 boxes）
            if merged_boxes:
                avg_score = sum(box.score for box in merged_boxes) / len(merged_boxes)
            else:
                avg_score = 0.0
            
            rapid_debug_log(f"识别完成，合并后共 {len(merged_boxes)} 行文本，平均分: {avg_score:.2f}")
            return OCRResult(
                success=True, 
                text=full_text, 
                boxes=merged_boxes,
                average_score=avg_score
            )
            
        except Exception as e:
            rapid_debug_log(f"解析结果异常: {str(e)}")
            rapid_debug_log(traceback.format_exc())
            return OCRResult.error_result(f"解析识别文字结果失败: {str(e)}")
    
    @staticmethod
    def _is_symbol_noise(text: str) -> bool:
        """
        判断 OCR 识别文本是否为符号噪声（UI 图标误识别）
        
        截图 OCR 时，文件夹展开箭头、文件类型图标、状态图标等 UI 元素
        会被模型识别为 ">", "{}", "!", "[]" 等符号字符。
        
        过滤规则：
        1. 去除空白后，文本仅包含 1-2 个字符
        2. 所有字符均非字母（a-z、A-Z）、非数字（0-9）、非汉字
        
        示例:
        - ">"  → True（文件夹箭头）
        - "{}" → True（JSON 文件图标）
        - "!"  → True（警告图标）
        - "Y"  → False（字母，保留）
        - "你好" → False（汉字，保留）
        """
        trimmed = text.strip()
        if len(trimmed) == 0 or len(trimmed) > 2:
            return False
        
        for ch in trimmed:
            # 字母、数字、汉字都不是噪声
            if ch.isalnum():
                return False
            # CJK 汉字范围
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or    # CJK 基本
                0x3400 <= cp <= 0x4DBF or    # CJK 扩展 A
                0xF900 <= cp <= 0xFAFF):     # CJK 兼容
                return False
        
        return True
    
    def _merge_same_line_boxes(self, boxes: List[OCRBox]) -> List[OCRBox]:
        """
        合并同一行的文字框
        
        根据Y坐标判断是否在同一行，然后按X坐标排序合并
        """
        if not boxes:
            return []
        
        # 计算每个box的中心Y坐标和高度
        box_info = []
        for box in boxes:
            if box.box is None or len(box.box) < 4:
                continue
            try:
                y_coords = [p[1] for p in box.box if p is not None and len(p) >= 2]
                x_coords = [p[0] for p in box.box if p is not None and len(p) >= 2]
                
                if not y_coords or not x_coords:
                    continue
                    
                y_min = min(y_coords)
                y_max = max(y_coords)
                x_min = min(x_coords)
                y_center = (y_min + y_max) / 2
                height = y_max - y_min
                box_info.append({
                    'box': box,
                    'y_center': y_center,
                    'y_min': y_min,
                    'y_max': y_max,
                    'x_min': x_min,
                    'height': height
                })
            except (IndexError, TypeError):
                continue
        
        if not box_info:
            return []
        
        # 按Y坐标排序
        box_info.sort(key=lambda x: x['y_center'])
        
        # 合并同一行的文字
        lines = []
        current_line = [box_info[0]]
        
        for i in range(1, len(box_info)):
            curr = box_info[i]
            prev = current_line[-1]
            
            # 确保 min_height 至少为 1，避免除零或无效阈值
            curr_height = curr['height'] if curr['height'] > 0 else 1
            prev_height = prev['height'] if prev['height'] > 0 else 1
            min_height = min(curr_height, prev_height)
            threshold = max(min_height * 0.5, 10)
            
            y_diff = abs(curr['y_center'] - prev['y_center'])
            
            if y_diff <= threshold:
                current_line.append(curr)
            else:
                lines.append(current_line)
                current_line = [curr]
        
        if current_line:
            lines.append(current_line)
        
        # 对每行按X坐标排序，然后智能合并文字
        merged_boxes = []
        for line in lines:
            line.sort(key=lambda x: x['x_min'])
            
            # 智能合并：根据间距决定是否加空格
            # 如果两个文本框间距很小（可能是同一个单词被错误分割），则不加空格
            merged_text = self._smart_merge_texts(line)
            
            all_x = []
            all_y = []
            for item in line:
                for p in item['box'].box:
                    all_x.append(p[0])
                    all_y.append(p[1])
            
            if all_x and all_y:
                merged_box = [
                    [min(all_x), min(all_y)],
                    [max(all_x), min(all_y)],
                    [max(all_x), max(all_y)],
                    [min(all_x), max(all_y)]
                ]
            else:
                merged_box = line[0]['box'].box
            
            avg_score = sum(item['box'].score for item in line) / len(line)
            
            merged_boxes.append(OCRBox(text=merged_text, box=merged_box, score=avg_score))
        
        rapid_debug_log(f"合并前 {len(boxes)} 个框，合并后 {len(merged_boxes)} 行")
        return merged_boxes
    
    def _smart_merge_texts(self, line: List[dict]) -> str:
        """
        智能合并同一行的文本框
        
        根据相邻文本框的间距决定是否加空格：
        - 间距小于字符平均宽度：不加空格（可能是同一单词被错误分割）
        - 间距较大：加空格（正常的单词间隔）
        
        Args:
            line: 已按X坐标排序的文本框信息列表，每个元素包含 'box' 键（OCRBox 对象）
            
        Returns:
            合并后的文本
        """
        if not line:
            return ""
        
        if len(line) == 1:
            text = line[0]['box'].text
            return text if text else ""
        
        result_parts = []
        
        for i, item in enumerate(line):
            text = item['box'].text or ""  # 防止 None
            
            if i == 0:
                result_parts.append(text)
                continue
            
            prev_item = line[i - 1]
            
            # 计算前一个框的右边界和当前框的左边界
            try:
                prev_x_coords = [p[0] for p in prev_item['box'].box if p is not None and len(p) >= 2]
                curr_x_coords = [p[0] for p in item['box'].box if p is not None and len(p) >= 2]
            except (TypeError, IndexError):
                # 坐标解析失败，使用空格分隔
                result_parts.append(" " + text)
                continue
            
            if not prev_x_coords or not curr_x_coords:
                result_parts.append(" " + text)
                continue
            
            # 预先计算 min/max 避免重复调用
            prev_x_min = min(prev_x_coords)
            prev_x_max = max(prev_x_coords)
            curr_x_min = min(curr_x_coords)
            curr_x_max = max(curr_x_coords)
            
            gap = curr_x_min - prev_x_max
            
            # 计算前一个文本框的字符平均宽度
            prev_width = prev_x_max - prev_x_min
            prev_text = prev_item['box'].text or ""
            prev_text_len = len(prev_text) if prev_text else 1
            prev_char_width = prev_width / prev_text_len if prev_text_len > 0 else 10
            
            # 计算当前文本框的字符平均宽度
            curr_width = curr_x_max - curr_x_min
            curr_text_len = len(text) if text else 1
            curr_char_width = curr_width / curr_text_len if curr_text_len > 0 else 10
            
            # 使用两个框的平均字符宽度作为阈值参考
            avg_char_width = (prev_char_width + curr_char_width) / 2
            
            # 阈值：如果间距小于平均字符宽度的 0.8 倍，认为是紧邻的（同一单词被分割）
            threshold = avg_char_width * 0.8
            
            if gap < threshold:
                # 紧邻：不加空格，直接拼接
                result_parts.append(text)
            else:
                # 正常间隔：加空格
                result_parts.append(" " + text)
        
        return "".join(result_parts)
