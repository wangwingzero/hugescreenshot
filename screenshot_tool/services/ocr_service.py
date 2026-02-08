# =====================================================
# =============== OCR服务 ===============
# =====================================================

"""
OCR服务 - 负责调用Umi-OCR引擎进行文字识别

Requirements: 4.1, 4.4, 4.5, 4.6
Property 4: OCR Request Formatting
"""

import base64
import json
import io
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer, QIODevice


@dataclass
class OCRBox:
    """OCR文字框"""
    text: str
    box: List[List[int]]  # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
    score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text": self.text,
            "box": self.box,
            "score": self.score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OCRBox":
        """从字典创建"""
        return cls(
            text=data.get("text", ""),
            box=data.get("box", []),
            score=data.get("score", 1.0),
        )


@dataclass
class OCRResult:
    """识别文字结果"""
    success: bool
    text: str = ""
    boxes: List[OCRBox] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "text": self.text,
            "boxes": [box.to_dict() for box in self.boxes],
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OCRResult":
        """从字典创建"""
        boxes = [OCRBox.from_dict(b) for b in data.get("boxes", [])]
        return cls(
            success=data.get("success", False),
            text=data.get("text", ""),
            boxes=boxes,
            error=data.get("error"),
        )
    
    @classmethod
    def error_result(cls, error_msg: str) -> "OCRResult":
        """创建错误结果"""
        return cls(success=False, error=error_msg)
    
    @classmethod
    def empty_result(cls) -> "OCRResult":
        """创建空结果（成功但无文字）"""
        return cls(success=True, text="", boxes=[])


class OCRService:
    """
    OCR服务 - 通过HTTP API调用Umi-OCR进行文字识别
    
    Umi-OCR API文档: http://127.0.0.1:1224/api/ocr
    """
    
    # 默认API地址
    DEFAULT_API_URL = "http://127.0.0.1:1224"
    
    # 支持的语言
    SUPPORTED_LANGUAGES = [
        ("auto", "自动检测"),
        ("ch", "中文"),
        ("en", "英文"),
        ("ja", "日文"),
        ("ko", "韩文"),
        ("fr", "法文"),
        ("de", "德文"),
        ("ru", "俄文"),
    ]
    
    def __init__(self, api_url: str = DEFAULT_API_URL, timeout: int = 30):
        """
        初始化OCR服务
        
        Args:
            api_url: Umi-OCR API地址
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
    
    def set_api_url(self, url: str):
        """设置API地址"""
        self.api_url = url.rstrip("/")
    
    def get_api_url(self) -> str:
        """获取API地址"""
        return self.api_url

    def check_service_available(self) -> Tuple[bool, Optional[str]]:
        """
        检查OCR服务是否可用
        
        Returns:
            Tuple[bool, Optional[str]]: (是否可用, 错误信息)
        """
        try:
            # 尝试访问API根路径
            url = f"{self.api_url}/api/ocr"
            request = Request(url, method="GET")
            request.add_header("Content-Type", "application/json")
            
            with urlopen(request, timeout=5) as response:
                # 只要能连接就认为服务可用
                return True, None
        except HTTPError as e:
            # HTTP错误但服务在运行
            if e.code in [400, 405]:  # Bad Request或Method Not Allowed说明服务在运行
                return True, None
            return False, f"HTTP错误: {e.code} {e.reason}"
        except URLError as e:
            return False, f"无法连接到OCR服务: {e.reason}"
        except Exception as e:
            return False, f"检查服务时出错: {str(e)}"
    
    def _qimage_to_base64(self, image: QImage) -> str:
        """
        将QImage转换为base64字符串
        
        Args:
            image: QImage对象
            
        Returns:
            str: base64编码的图片数据
        """
        if image.isNull():
            return ""
        
        # 转换为PNG格式
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        
        # 转换为base64
        image_data = buffer.data().data()
        base64_data = base64.b64encode(image_data).decode("utf-8")
        
        return base64_data
    
    def _parse_ocr_response(self, response_data: Dict[str, Any]) -> OCRResult:
        """
        解析Umi-OCR API响应
        
        Args:
            response_data: API响应数据
            
        Returns:
            OCRResult: 解析后的结果
        """
        # Umi-OCR响应格式:
        # {
        #     "code": 100,  # 100=成功
        #     "data": [
        #         {"text": "文字", "box": [[x1,y1], [x2,y1], [x2,y2], [x1,y2]], "score": 0.95}
        #     ]
        # }
        
        code = response_data.get("code", -1)
        
        if code == 100:
            # 成功
            data = response_data.get("data", [])
            
            if not data:
                return OCRResult.empty_result()
            
            boxes = []
            text_lines = []
            
            for item in data:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    box = item.get("box", [])
                    score = item.get("score", 1.0)
                    
                    if text:
                        boxes.append(OCRBox(text=text, box=box, score=score))
                        text_lines.append(text)
            
            full_text = "\n".join(text_lines)
            return OCRResult(success=True, text=full_text, boxes=boxes)
        
        elif code == 101:
            # 无文字
            return OCRResult.empty_result()
        
        else:
            # 错误
            error_msg = response_data.get("data", "未知错误")
            return OCRResult.error_result(f"OCR识别失败: {error_msg}")

    def recognize_image(self, image: QImage, language: str = "auto") -> OCRResult:
        """
        识别图片中的文字
        
        Args:
            image: 要识别的QImage
            language: 识别语言 (auto, ch, en, ja, ko, etc.)
            
        Returns:
            OCRResult: 识别文字结果
        """
        if image.isNull():
            return OCRResult.error_result("图片为空")
        
        # 转换图片为base64
        base64_data = self._qimage_to_base64(image)
        if not base64_data:
            return OCRResult.error_result("图片转换失败")
        
        # 构建请求
        request_data = {
            "base64": base64_data,
            "options": {}
        }
        
        # 设置语言（如果不是auto）
        if language and language != "auto":
            request_data["options"]["language"] = language
        
        try:
            # 发送请求
            url = f"{self.api_url}/api/ocr"
            json_data = json.dumps(request_data).encode("utf-8")
            
            request = Request(url, data=json_data, method="POST")
            request.add_header("Content-Type", "application/json")
            
            with urlopen(request, timeout=self.timeout) as response:
                response_text = response.read().decode("utf-8")
                response_data = json.loads(response_text)
                
                return self._parse_ocr_response(response_data)
        
        except HTTPError as e:
            return OCRResult.error_result(f"HTTP错误: {e.code} {e.reason}")
        except URLError as e:
            return OCRResult.error_result(f"无法连接到OCR服务: {e.reason}")
        except json.JSONDecodeError as e:
            return OCRResult.error_result(f"解析响应失败: {str(e)}")
        except Exception as e:
            return OCRResult.error_result(f"OCR识别出错: {str(e)}")
    
    def recognize_region(
        self,
        image: QImage,
        region: Tuple[int, int, int, int],
        language: str = "auto"
    ) -> OCRResult:
        """
        识别图片指定区域的文字
        
        Args:
            image: 原始图片
            region: (x1, y1, x2, y2) 区域坐标
            language: 识别语言
            
        Returns:
            OCRResult: 识别文字结果
        """
        if image.isNull():
            return OCRResult.error_result("图片为空")
        
        x1, y1, x2, y2 = region
        
        # 确保坐标正确
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        
        # 限制在图片范围内
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.width(), x2)
        y2 = min(image.height(), y2)
        
        # 检查区域有效性
        width = x2 - x1
        height = y2 - y1
        
        if width <= 0 or height <= 0:
            return OCRResult.error_result("无效的区域坐标")
        
        # 裁剪图片
        cropped = image.copy(x1, y1, width, height)
        
        if cropped.isNull():
            return OCRResult.error_result("裁剪图片失败")
        
        # 识别裁剪后的图片
        return self.recognize_image(cropped, language)
    
    def recognize_base64(self, base64_data: str, language: str = "auto") -> OCRResult:
        """
        识别base64编码的图片
        
        Args:
            base64_data: base64编码的图片数据
            language: 识别语言
            
        Returns:
            OCRResult: 识别文字结果
        """
        if not base64_data:
            return OCRResult.error_result("base64数据为空")
        
        # 构建请求
        request_data = {
            "base64": base64_data,
            "options": {}
        }
        
        if language and language != "auto":
            request_data["options"]["language"] = language
        
        try:
            url = f"{self.api_url}/api/ocr"
            json_data = json.dumps(request_data).encode("utf-8")
            
            request = Request(url, data=json_data, method="POST")
            request.add_header("Content-Type", "application/json")
            
            with urlopen(request, timeout=self.timeout) as response:
                response_text = response.read().decode("utf-8")
                response_data = json.loads(response_text)
                
                return self._parse_ocr_response(response_data)
        
        except HTTPError as e:
            return OCRResult.error_result(f"HTTP错误: {e.code} {e.reason}")
        except URLError as e:
            return OCRResult.error_result(f"无法连接到OCR服务: {e.reason}")
        except json.JSONDecodeError as e:
            return OCRResult.error_result(f"解析响应失败: {str(e)}")
        except Exception as e:
            return OCRResult.error_result(f"OCR识别出错: {str(e)}")
    
    @staticmethod
    def get_supported_languages() -> List[Tuple[str, str]]:
        """
        获取支持的语言列表
        
        Returns:
            List[Tuple[str, str]]: [(语言代码, 语言名称), ...]
        """
        return OCRService.SUPPORTED_LANGUAGES.copy()
    
    def format_request(self, image: QImage, language: str = "auto") -> Dict[str, Any]:
        """
        格式化OCR请求（用于测试）
        
        Args:
            image: QImage对象
            language: 识别语言
            
        Returns:
            Dict: 格式化的请求数据
        """
        base64_data = self._qimage_to_base64(image)
        
        request_data = {
            "base64": base64_data,
            "options": {}
        }
        
        if language and language != "auto":
            request_data["options"]["language"] = language
        
        return request_data
