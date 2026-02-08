# =====================================================
# =============== 腾讯云OCR服务 ===============
# =====================================================

"""
腾讯云OCR服务 - 在线高精度OCR识别

需要配置 SecretId 和 SecretKey
免费额度：
- 通用文字识别(高精度版)：每月1000次（优先使用）
- 通用印刷体识别：每月1000次（备用）
"""

import json
import base64
import hashlib
import hmac
import time
import socket
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
import urllib.request
import urllib.parse
import urllib.error

from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer

# ========== 调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

def tencent_debug_log(message: str):
    """腾讯OCR调试日志"""
    async_debug_log(message, "TENCENT-OCR")


@dataclass
class TencentOCRResult:
    """腾讯识别文字结果"""
    success: bool
    text: str = ""
    text_detections: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    @classmethod
    def error_result(cls, error_msg: str) -> "TencentOCRResult":
        return cls(success=False, error=error_msg)


class TencentOCRService:
    """腾讯云OCR服务"""
    
    # 腾讯云OCR API配置
    HOST = "ocr.tencentcloudapi.com"
    SERVICE = "ocr"
    VERSION = "2018-11-19"
    REGION = "ap-guangzhou"
    
    # API Action（按优先级排列）
    # 通用文字识别(高精度版)：每月1000次免费 - 优先使用
    ACTION_ACCURATE = "GeneralAccurateOCR"
    # 通用印刷体识别：每月1000次免费 - 备用
    ACTION_BASIC = "GeneralBasicOCR"
    
    # 配额耗尽错误码
    QUOTA_EXHAUSTED_CODES = [
        "ResourceUnavailable.InArrears",
        "ResourceUnavailable.ResourcePackageRunOut",
        "ResourcesSoldOut.ChargeStatusException"
    ]
    
    # 图片大小限制（Base64编码后不超过7MB）
    MAX_IMAGE_SIZE_BYTES = 7 * 1024 * 1024
    
    def __init__(self, secret_id: str = "", secret_key: str = "", timeout: int = 10):
        """
        初始化腾讯云OCR服务
        
        Args:
            secret_id: 腾讯云 SecretId
            secret_key: 腾讯云 SecretKey
            timeout: 请求超时时间（秒）
        """
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.timeout = timeout
    
    def is_configured(self) -> bool:
        """检查是否已配置API密钥"""
        return bool(self.secret_id and self.secret_key)

    def _sign(self, key: bytes, msg: str) -> bytes:
        """HMAC-SHA256签名"""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    
    def _qimage_to_base64(self, image: QImage) -> Optional[str]:
        """将QImage转换为Base64编码"""
        if image.isNull():
            return None
        
        try:
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            image_data = buffer.data().data()
            buffer.close()
            return base64.b64encode(image_data).decode("utf-8")
        except Exception as e:
            tencent_debug_log(f"图片转Base64失败: {str(e)}")
            return None
    
    def check_service_available(self) -> Tuple[bool, Optional[str]]:
        """检查服务是否可用"""
        if not self.is_configured():
            return False, "未配置腾讯云API密钥"
        return True, None

    def _call_ocr_api(self, action: str, image_base64: str) -> Tuple[dict, Optional[str]]:
        """
        调用腾讯云OCR API
        
        Args:
            action: API Action (GeneralAccurateOCR 或 GeneralBasicOCR)
            image_base64: 图片Base64编码
            
        Returns:
            (result_dict, error_code) - error_code为None表示成功
        """
        timestamp = int(time.time())
        
        # 构建请求体
        payload = json.dumps({"ImageBase64": image_base64})
        
        # 生成签名
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        algorithm = "TC3-HMAC-SHA256"
        
        # 规范请求串 - 只签名 content-type 和 host
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{self.HOST}\n"
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
        
        # 待签名字符串
        credential_scope = f"{date}/{self.SERVICE}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"
        
        # 计算签名
        secret_date = self._sign(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.SERVICE)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        
        authorization = f"{algorithm} Credential={self.secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        
        # 构建请求
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.HOST,
            "X-TC-Action": action,
            "X-TC-Version": self.VERSION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self.REGION,
            "Authorization": authorization
        }
        
        url = f"https://{self.HOST}"
        req = urllib.request.Request(url, data=payload.encode("utf-8"), headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            # HTTP错误（4xx, 5xx）
            error_body = e.read().decode("utf-8") if e.fp else ""
            tencent_debug_log(f"HTTP错误 {e.code}: {error_body[:200]}")
            try:
                result = json.loads(error_body)
                response = result.get("Response", {})
                error = response.get("Error")
                if error:
                    return result, error.get("Code")
            except json.JSONDecodeError:
                pass
            return {}, f"HTTP{e.code}"
        except urllib.error.URLError as e:
            tencent_debug_log(f"URL错误: {str(e)}")
            return {}, "URLError"
        
        try:
            result = json.loads(response_data)
        except json.JSONDecodeError as e:
            tencent_debug_log(f"JSON解析失败: {str(e)}, 响应内容: {response_data[:200]}")
            return {}, "JSONDecodeError"
        
        # 检查错误
        response = result.get("Response", {})
        error = response.get("Error")
        if error:
            return result, error.get("Code")
        
        return result, None

    def recognize_accurate(self, image: QImage) -> TencentOCRResult:
        """
        使用高精度版OCR识别图片（仅调用高精度API）
        
        高精度版：每月1000次免费
        
        Args:
            image: 要识别的QImage
            
        Returns:
            TencentOCRResult: 识别结果
        """
        return self._recognize_with_action(image, self.ACTION_ACCURATE, "腾讯高精度版")
    
    def recognize_basic(self, image: QImage) -> TencentOCRResult:
        """
        使用通用版OCR识别图片（仅调用通用API）
        
        通用版：每月1000次免费
        
        Args:
            image: 要识别的QImage
            
        Returns:
            TencentOCRResult: 识别结果
        """
        return self._recognize_with_action(image, self.ACTION_BASIC, "腾讯通用版")
    
    def _recognize_with_action(self, image: QImage, action: str, api_name: str) -> TencentOCRResult:
        """
        使用指定的API进行OCR识别
        
        Args:
            image: 要识别的QImage
            action: API Action
            api_name: API名称（用于日志）
            
        Returns:
            TencentOCRResult: 识别结果
        """
        tencent_debug_log("=" * 50)
        tencent_debug_log(f"开始腾讯云OCR识别 - {api_name}")
        
        if image.isNull():
            return TencentOCRResult.error_result("图片为空")
        
        if not self.is_configured():
            return TencentOCRResult.error_result("未配置腾讯云API密钥")
        
        tencent_debug_log(f"图片尺寸: {image.width()}x{image.height()}")
        
        # 图片转Base64
        image_base64 = self._qimage_to_base64(image)
        if not image_base64:
            return TencentOCRResult.error_result("图片编码失败")
        
        tencent_debug_log(f"图片Base64长度: {len(image_base64)}")
        
        # 检查图片大小限制
        if len(image_base64) > self.MAX_IMAGE_SIZE_BYTES:
            tencent_debug_log(f"图片过大: {len(image_base64)} bytes，超过限制 {self.MAX_IMAGE_SIZE_BYTES} bytes")
            return TencentOCRResult.error_result(f"图片过大（{len(image_base64) // 1024 // 1024}MB），请缩小图片后重试")
        
        try:
            tencent_debug_log(f"调用: {api_name}")
            
            result, error_code = self._call_ocr_api(action, image_base64)
            
            # 检查是否配额耗尽
            if error_code in self.QUOTA_EXHAUSTED_CODES:
                tencent_debug_log(f"{api_name} 配额耗尽: {error_code}")
                return TencentOCRResult.error_result(f"{api_name}配额耗尽: {error_code}")
            
            # 其他错误
            if error_code is not None:
                response = result.get("Response", {})
                error = response.get("Error", {})
                error_msg = error.get("Message", error_code)
                tencent_debug_log(f"OCR错误: {error_msg}")
                return TencentOCRResult.error_result(f"腾讯OCR错误: {error_msg}")
            
            # 解析结果
            response = result.get("Response", {})
            text_detections = response.get("TextDetections", [])
            
            tencent_debug_log(f"OCR响应: {json.dumps(result, ensure_ascii=False)[:500]}")
            
            if not text_detections:
                tencent_debug_log("未识别到文字")
                return TencentOCRResult(success=True, text="", text_detections=[])
            
            tencent_debug_log(f"识别到 {len(text_detections)} 个文本框")
            
            # 提取文字
            lines = [item.get("DetectedText", "") for item in text_detections if item.get("DetectedText")]
            full_text = "\n".join(lines)
            
            tencent_debug_log(f"使用 {api_name} 识别成功，共 {len(lines)} 行文字")
            
            return TencentOCRResult(
                success=True,
                text=full_text,
                text_detections=text_detections
            )
            
        except urllib.error.URLError as e:
            tencent_debug_log(f"网络错误: {str(e)}")
            return TencentOCRResult.error_result(f"网络错误: {str(e)}")
        except socket.timeout as e:
            tencent_debug_log(f"请求超时: {str(e)}")
            return TencentOCRResult.error_result(f"请求超时: {str(e)}")
        except Exception as e:
            tencent_debug_log(f"OCR异常: {str(e)}")
            return TencentOCRResult.error_result(f"OCR异常: {str(e)}")
    
    def recognize_image(self, image: QImage) -> TencentOCRResult:
        """
        识别图片中的文字（仅使用高精度版）
        
        注意：此方法仅调用高精度版API，不会自动降级到通用版。
        如需使用通用版作为备用，请在 OCRManager 中配置调用顺序。
        
        Args:
            image: 要识别的QImage
            
        Returns:
            TencentOCRResult: 识别结果
        """
        return self.recognize_accurate(image)
