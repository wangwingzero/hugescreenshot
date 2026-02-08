# =====================================================
# =============== OCR管理器 ===============
# =====================================================

"""
OCR管理器 - 统一管理多个OCR引擎

默认行为：
- 自动OCR使用本地OCR（RapidOCR，离线可用，基于 OpenVINO）
- 用户可通过OCR面板按钮手动切换到云端OCR：
  - 腾讯云OCR：高精度版 → 通用版（自动降级）
  - 百度云OCR：高精度版 → 通用版（4个API自动降级）

优化功能：
- 图像预处理：CLAHE 对比度增强、锐化滤波、自适应二值化
- OpenVINO 后端：支持 Intel 和 AMD CPU
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import time

from PySide6.QtGui import QImage


# ========== 调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

# ========== 预处理配置 ==========
from screenshot_tool.services.image_preprocessor import PreprocessingConfig
from screenshot_tool.services.backend_selector import BackendType, BackendInfo

def ocr_manager_log(message: str):
    """OCR管理器日志"""
    async_debug_log(message, "OCR-MGR")


# OCR引擎显示名称映射
ENGINE_DISPLAY_NAMES = {
    "baidu": "百度云OCR",
    "tencent": "腾讯云OCR",
    "rapid": "本地OCR",
}


@dataclass
class EngineStatus:
    """引擎状态"""
    available: bool
    message: str
    
    @classmethod
    def available_status(cls, message: str = "可用") -> "EngineStatus":
        return cls(available=True, message=message)
    
    @classmethod
    def unavailable_status(cls, message: str) -> "EngineStatus":
        return cls(available=False, message=message)
    
    def to_dict(self) -> Dict:
        return {"available": self.available, "message": self.message}


@dataclass
class UnifiedOCRResult:
    """统一的识别文字结果"""
    success: bool
    text: str = ""
    engine: str = ""
    error: Optional[str] = None
    # 新增字段：OCR 评分和后端信息
    average_score: float = 0.0  # 平均置信度分数 (0.0-1.0)
    backend_detail: str = ""  # 后端详细信息（如 "本地OCR"）
    elapsed_time: float = 0.0  # OCR 耗时（秒）
    
    @classmethod
    def error_result(cls, error_msg: str, engine: str = "") -> "UnifiedOCRResult":
        return cls(success=False, error=error_msg, engine=engine)


class OCRManager:
    """OCR管理器 - 默认使用RapidOCR，支持手动切换到云端OCR
    
    支持图像预处理配置和后端选择优化。
    """
    
    def __init__(self, baidu_api_key: str = "", baidu_secret_key: str = "",
                 tencent_secret_id: str = "", tencent_secret_key: str = "",
                 engine_priority: List[str] = None,
                 preprocessing_config: PreprocessingConfig = None):
        # 默认只使用 RapidOCR（本地引擎）
        # engine_priority 参数保留用于向后兼容，但不再使用
        self.engine_priority = ["rapid"]
        
        self._baidu_service = None
        self._tencent_service = None
        self._rapid_service = None  # 本地OCR (RapidOCR)
        self._rapid_available = None  # 缓存本地OCR可用状态
        
        # 预处理配置
        self._preprocessing_config = preprocessing_config or PreprocessingConfig()
        
        # 初始化腾讯云OCR
        if tencent_secret_id and tencent_secret_key:
            try:
                from screenshot_tool.services.tencent_ocr_service import TencentOCRService
                self._tencent_service = TencentOCRService(
                    secret_id=tencent_secret_id,
                    secret_key=tencent_secret_key
                )
                ocr_manager_log("腾讯云OCR已配置")
            except Exception as e:
                ocr_manager_log(f"腾讯云OCR初始化失败: {e}")
        
        # 初始化百度云OCR
        if baidu_api_key and baidu_secret_key:
            try:
                from screenshot_tool.services.baidu_ocr_service import BaiduOCRService
                self._baidu_service = BaiduOCRService(
                    api_key=baidu_api_key,
                    secret_key=baidu_secret_key,
                    use_accurate=True
                )
                ocr_manager_log("百度云OCR已配置")
            except Exception as e:
                ocr_manager_log(f"百度云OCR初始化失败: {e}")
        
        ocr_manager_log(f"OCR管理器初始化完成，预处理: {self._preprocessing_config.enabled}")
    
    # ========== 预处理配置管理 ==========
    
    def get_preprocessing_config(self) -> PreprocessingConfig:
        """获取预处理配置"""
        return self._preprocessing_config
    
    def set_preprocessing_config(self, config: PreprocessingConfig):
        """设置预处理配置（立即生效）"""
        self._preprocessing_config = config
        # 如果 RapidOCR 服务已初始化，更新其配置
        if self._rapid_service is not None:
            self._rapid_service.set_preprocessing_config(config)
        ocr_manager_log(f"预处理配置已更新: enabled={config.enabled}")
    
    def set_engine_priority(self, priority: List[str]):
        """设置引擎优先级（保留用于向后兼容，但不再影响默认行为）"""
        ocr_manager_log(f"set_engine_priority 已弃用，默认使用本地OCR")
    
    def _get_rapid_service(self):
        """获取本地OCR服务（RapidOCR，懒加载）"""
        if self._rapid_service is None:
            from screenshot_tool.services.rapid_ocr_service import RapidOCRService
            self._rapid_service = RapidOCRService(
                lang="ch",
                preprocessing_config=self._preprocessing_config
            )
            ocr_manager_log("本地OCR服务已初始化")
        return self._rapid_service
    
    def preload_rapid(self):
        """预加载本地OCR模型"""
        try:
            service = self._get_rapid_service()
            service._get_ocr()
            ocr_manager_log("本地OCR模型预加载完成")
        except Exception as e:
            ocr_manager_log(f"本地OCR预加载失败: {e}")
    
    def recognize_rapid_only(self, image: QImage) -> UnifiedOCRResult:
        """只使用本地OCR进行识别（用于后台预处理，不消耗在线API配额）"""
        ocr_manager_log("=" * 50)
        ocr_manager_log("后台预处理OCR（仅本地OCR）")
        
        if image is None or image.isNull():
            return UnifiedOCRResult.error_result("图片为空")
        
        return self._recognize_rapid(image)
    
    def recognize(self, image, force_engine: str = None) -> UnifiedOCRResult:
        """识别图片

        Args:
            image: QImage 或 numpy.ndarray
            force_engine: 强制使用的引擎
        """
        ocr_manager_log("=" * 50)
        ocr_manager_log(f"开始OCR识别，指定引擎: {force_engine or 'rapid(默认)'}")

        # 检查图片有效性
        import numpy as np
        if image is None:
            return UnifiedOCRResult.error_result("图片为空")

        if isinstance(image, QImage) and image.isNull():
            return UnifiedOCRResult.error_result("图片为空(QImage)")

        if isinstance(image, np.ndarray) and image.size == 0:
            return UnifiedOCRResult.error_result("图片为空(ndarray)")

        # 指定引擎时，使用该引擎（包含完整降级逻辑）
        if force_engine:
            if force_engine == "tencent":
                return self._recognize_tencent_with_fallback(image)
            elif force_engine == "baidu":
                return self._recognize_baidu(image)
            elif force_engine == "rapid":
                return self._recognize_rapid(image)
            else:
                return UnifiedOCRResult.error_result(f"未知引擎: {force_engine}", force_engine)

        # 默认使用 RapidOCR
        return self._recognize_rapid(image)
    
    def _recognize_tencent_with_fallback(self, image: QImage) -> UnifiedOCRResult:
        """使用腾讯OCR识别（高精度版 -> 通用版降级）
        
        用于 force_engine="tencent" 场景，确保完整的降级逻辑。
        """
        if not self._tencent_service:
            return UnifiedOCRResult.error_result("腾讯OCR未配置（需要API密钥）", "tencent")
        
        # 先尝试高精度版
        result = self._recognize_tencent_accurate(image)
        if result.success:
            return result
        
        ocr_manager_log(f"腾讯高精度版失败，尝试通用版...")
        
        # 高精度版失败，尝试通用版
        return self._recognize_tencent_basic(image)
    
    def recognize_with_engine(self, image: QImage, engine: str) -> UnifiedOCRResult:
        """使用指定引擎进行OCR识别（公开方法）"""
        return self._recognize_with_engine(image, engine)
    
    def _recognize_with_engine(self, image: QImage, engine: str) -> UnifiedOCRResult:
        engine_name = ENGINE_DISPLAY_NAMES.get(engine, engine)
        ocr_manager_log(f"尝试使用 {engine_name}")
        
        try:
            if engine == "baidu":
                return self._recognize_baidu(image)
            elif engine == "tencent":
                return self._recognize_tencent(image)
            elif engine == "rapid":
                return self._recognize_rapid(image)
            else:
                return UnifiedOCRResult.error_result(f"未知引擎: {engine}", engine)
        except Exception as e:
            ocr_manager_log(f"{engine_name} 引擎异常: {e}")
            return UnifiedOCRResult.error_result(str(e), engine)
    
    def _recognize_baidu(self, image: QImage) -> UnifiedOCRResult:
        if not self._baidu_service:
            return UnifiedOCRResult.error_result("百度OCR未配置（需要API密钥）", "baidu")
        
        result = self._baidu_service.recognize_image(image)
        
        if result.success:
            ocr_manager_log(f"百度OCR成功，文本长度: {len(result.text)}")
            return UnifiedOCRResult(success=True, text=result.text, engine="baidu")
        else:
            ocr_manager_log(f"百度OCR失败: {result.error}")
            return UnifiedOCRResult.error_result(result.error or "百度OCR失败", "baidu")
    
    def _recognize_tencent(self, image: QImage) -> UnifiedOCRResult:
        if not self._tencent_service:
            return UnifiedOCRResult.error_result("腾讯OCR未配置（需要API密钥）", "tencent")
        
        result = self._tencent_service.recognize_image(image)
        
        if result.success:
            ocr_manager_log(f"腾讯OCR成功，文本长度: {len(result.text)}")
            return UnifiedOCRResult(success=True, text=result.text, engine="tencent")
        else:
            ocr_manager_log(f"腾讯OCR失败: {result.error}")
            return UnifiedOCRResult.error_result(result.error or "腾讯OCR失败", "tencent")
    
    def _recognize_tencent_accurate(self, image: QImage) -> UnifiedOCRResult:
        """使用腾讯高精度版进行识别"""
        if not self._tencent_service:
            return UnifiedOCRResult.error_result("腾讯OCR未配置（需要API密钥）", "tencent")
        
        result = self._tencent_service.recognize_accurate(image)
        
        if result.success:
            ocr_manager_log(f"腾讯高精度版成功，文本长度: {len(result.text)}")
            return UnifiedOCRResult(success=True, text=result.text, engine="tencent")
        else:
            ocr_manager_log(f"腾讯高精度版失败: {result.error}")
            return UnifiedOCRResult.error_result(result.error or "腾讯高精度版失败", "tencent")
    
    def _recognize_tencent_basic(self, image: QImage) -> UnifiedOCRResult:
        """使用腾讯通用版进行识别（作为最后备用）"""
        if not self._tencent_service:
            return UnifiedOCRResult.error_result("腾讯OCR未配置（需要API密钥）", "tencent")
        
        result = self._tencent_service.recognize_basic(image)
        
        if result.success:
            ocr_manager_log(f"腾讯通用版成功，文本长度: {len(result.text)}")
            return UnifiedOCRResult(success=True, text=result.text, engine="tencent")
        else:
            ocr_manager_log(f"腾讯通用版失败: {result.error}")
            return UnifiedOCRResult.error_result(result.error or "腾讯通用版失败", "tencent")
    
    def _recognize_rapid(self, image: QImage) -> UnifiedOCRResult:
        """使用 RapidOCR 进行识别"""
        start_time = time.perf_counter()
        try:
            service = self._get_rapid_service()
            result = service.recognize_image(image)
            
            # 优先使用 OCRResult 中存储的实际 OCR 处理耗时（毫秒转秒）
            # 当 rapid_ocr_service 内部缓存命中时，外部测量的时间只是缓存查找时间（≈0），
            # 而 OCRResult.elapsed_time_ms 保存了原始 OCR 处理的真实耗时
            if hasattr(result, 'elapsed_time_ms') and result.elapsed_time_ms > 0:
                elapsed = result.elapsed_time_ms / 1000.0
            else:
                elapsed = time.perf_counter() - start_time
            
            if result.success:
                ocr_manager_log(f"本地OCR成功，文本长度: {len(result.text)}，平均分: {result.average_score:.2f}，耗时: {elapsed:.2f}秒")
                return UnifiedOCRResult(
                    success=True, 
                    text=result.text, 
                    engine="rapid",
                    average_score=result.average_score,
                    backend_detail=result.backend_detail or "",
                    elapsed_time=elapsed
                )
            else:
                ocr_manager_log(f"本地OCR失败: {result.error}，耗时: {elapsed:.2f}秒")
                return UnifiedOCRResult.error_result(result.error or "本地OCR失败", "rapid")
        except ImportError as e:
            ocr_manager_log(f"本地OCR未安装: {e}")
            return UnifiedOCRResult.error_result("本地OCR未安装，请运行: pip install rapidocr-openvino", "rapid")
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            ocr_manager_log(f"本地OCR异常: {e}，耗时: {elapsed:.2f}秒")
            return UnifiedOCRResult.error_result(str(e), "rapid")
    
    def has_baidu_configured(self) -> bool:
        """检查百度OCR是否已配置"""
        return self._baidu_service is not None
    
    def has_tencent_configured(self) -> bool:
        """检查腾讯OCR是否已配置"""
        return self._tencent_service is not None
    
    def get_available_engines(self) -> List[str]:
        """获取可用的引擎列表"""
        engines = []
        if self._tencent_service:
            engines.append("tencent")
        if self._baidu_service:
            engines.append("baidu")
        engines.append("rapid")
        return engines
    
    def get_engine_display_name(self, engine: str) -> str:
        return ENGINE_DISPLAY_NAMES.get(engine, engine)
    
    def get_engine_status(self) -> Dict[str, Dict]:
        """获取各引擎状态
        
        Returns:
            各引擎的状态字典，格式：
            {
                "rapid": {"available": True, "message": "已安装", "backend": "openvino"},
                "tencent": {"available": True, "message": "已配置"},
                "baidu": {"available": True, "message": "已配置"},
                "preprocessing": {"enabled": True, ...}
            }
        """
        status = {}
        
        # 本地OCR 状态（包含后端类型）
        rapid_status = self._check_rapid_available()
        rapid_dict = rapid_status.to_dict()
        
        # 添加后端类型信息
        try:
            from screenshot_tool.services.rapid_ocr_service import RapidOCRService
            backend_type = RapidOCRService.get_backend_type()
            if backend_type:
                rapid_dict["backend"] = backend_type.value
            else:
                rapid_dict["backend"] = "unknown"
            
            # 添加后端详细信息
            backend_info = RapidOCRService.get_backend_info()
            rapid_dict["cpu_vendor"] = backend_info.cpu_vendor
            rapid_dict["openvino_available"] = backend_info.openvino_available
        except ImportError:
            rapid_dict["backend"] = "not_installed"
        except Exception as e:
            rapid_dict["backend"] = "error"
            ocr_manager_log(f"获取后端信息失败: {e}")
        
        status["rapid"] = rapid_dict
        
        # 腾讯 OCR 状态
        tencent_status = self._check_tencent_available()
        status["tencent"] = tencent_status.to_dict()
        
        # 百度 OCR 状态
        baidu_status = self._check_baidu_available()
        status["baidu"] = baidu_status.to_dict()
        
        # 预处理配置状态
        status["preprocessing"] = self._preprocessing_config.to_dict()
        
        return status
    
    def is_engine_available(self, engine: str) -> bool:
        """检查指定引擎是否可用
        
        Args:
            engine: 引擎名称 (rapid, tencent, baidu)
            
        Returns:
            引擎是否可用
        """
        if engine == "rapid":
            return self._check_rapid_available().available
        elif engine == "tencent":
            return self._check_tencent_available().available
        elif engine == "baidu":
            return self._check_baidu_available().available
        return False
    
    def _check_rapid_available(self) -> EngineStatus:
        """检查 RapidOCR 是否可用
        
        使用缓存避免重复检查，提高性能。
        """
        # 使用缓存避免重复检查
        if self._rapid_available is not None:
            return self._rapid_available
        
        try:
            from rapidocr_openvino import RapidOCR
            self._rapid_available = EngineStatus.available_status("已安装")
        except ImportError:
            self._rapid_available = EngineStatus.unavailable_status(
                "未安装，请运行: pip install rapidocr-openvino"
            )
        except Exception as e:
            # 处理其他可能的异常（如模块加载错误、依赖缺失等）
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:50] + "..."
            self._rapid_available = EngineStatus.unavailable_status(f"初始化失败: {error_msg}")
        
        return self._rapid_available
    
    def _check_baidu_available(self) -> EngineStatus:
        """检查百度 OCR 是否可用"""
        if self._baidu_service is not None:
            return EngineStatus.available_status("已配置")
        else:
            return EngineStatus.unavailable_status("未配置（需要API密钥）")
    
    def _check_tencent_available(self) -> EngineStatus:
        """检查腾讯 OCR 是否可用"""
        if self._tencent_service is not None:
            return EngineStatus.available_status("已配置")
        else:
            return EngineStatus.unavailable_status("未配置（需要API密钥）")
