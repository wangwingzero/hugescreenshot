# =====================================================
# =============== 百度云OCR服务 ===============
# =====================================================

"""
百度云OCR服务 - 在线高精度OCR识别

需要配置 API Key 和 Secret Key
免费额度（共用同一个API Key）：
- 高精度版：每月1000次（优先使用）
- 高精度含位置版：每月500次
- 通用标准版：每月1000次
- 通用标准含位置版：每月1000次（最后备用）
"""

import json
import base64
import urllib.request
import urllib.parse
import urllib.error
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any

from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer

# ========== 调试日志 ==========
from screenshot_tool.core.async_logger import async_debug_log

def baidu_debug_log(message: str):
    """百度OCR调试日志"""
    async_debug_log(message, "BAIDU-OCR")


@dataclass
class BaiduOCRResult:
    """百度识别文字结果"""
    success: bool
    text: str = ""
    words_result: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    @classmethod
    def error_result(cls, error_msg: str) -> "BaiduOCRResult":
        return cls(success=False, error=error_msg)


class BaiduOCRService:
    """百度云OCR服务"""
    
    # 百度OCR API地址
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    
    # API地址（按优先级排列）
    # 高精度版（不含位置）：每月1000次免费 - 优先使用
    OCR_ACCURATE_BASIC_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    # 高精度含位置版：每月500次免费
    OCR_ACCURATE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"
    # 通用标准版（不含位置）：每月1000次免费
    OCR_GENERAL_BASIC_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
    # 通用标准含位置版：每月1000次免费 - 最后备用
    OCR_GENERAL_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general"
    
    # 配额耗尽错误码
    QUOTA_EXHAUSTED_CODES = [17, 18, 19]  # 17=每日限额, 18=QPS超限, 19=总量超限
    
    def __init__(self, api_key: str = "", secret_key: str = "", 
                 use_accurate: bool = True, timeout: int = 10):
        """
        初始化百度OCR服务
        
        Args:
            api_key: 百度云 API Key
            secret_key: 百度云 Secret Key
            use_accurate: 是否使用高精度识别
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_accurate = use_accurate
        self.timeout = timeout
        self._access_token = None
        self._token_expires = 0
    
    def is_configured(self) -> bool:
        """检查是否已配置API密钥"""
        return bool(self.api_key and self.secret_key)
    
    def _get_access_token(self) -> Optional[str]:
        """获取或刷新 Access Token"""
        # 检查缓存的token是否有效（提前1小时刷新）
        if self._access_token and time.time() < self._token_expires - 3600:
            return self._access_token
        
        if not self.is_configured():
            baidu_debug_log("未配置API密钥")
            return None
        
        try:
            baidu_debug_log("获取百度云Access Token...")
            
            params = {
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key
            }
            
            url = f"{self.TOKEN_URL}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, method="POST")
            
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            if "access_token" in data:
                self._access_token = data["access_token"]
                expires_in = data.get("expires_in", 2592000)
                self._token_expires = time.time() + expires_in
                baidu_debug_log(f"Access Token获取成功，有效期{expires_in}秒")
                return self._access_token
            else:
                error = data.get("error_description", "未知错误")
                baidu_debug_log(f"获取Token失败: {error}")
                return None
                
        except Exception as e:
            baidu_debug_log(f"获取Token异常: {str(e)}")
            return None
    
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
            baidu_debug_log(f"图片转Base64失败: {str(e)}")
            return None
    
    def check_service_available(self) -> Tuple[bool, Optional[str]]:
        """检查服务是否可用"""
        if not self.is_configured():
            return False, "未配置百度云API密钥"
        
        token = self._get_access_token()
        if not token:
            return False, "获取Access Token失败"
        
        return True, None

    def _get_api_fallback_chain(self) -> List[Tuple[str, str, bool]]:
        """
        获取API降级链
        
        优先级（高精度模式）：
        1. 高精度版（不含位置）- 每月1000次
        2. 高精度含位置版 - 每月500次
        3. 通用标准版（不含位置）- 每月1000次
        4. 通用标准含位置版 - 每月1000次
        
        Returns:
            List of (api_url, api_name, has_location)
        """
        chain = []
        
        if self.use_accurate:
            # 高精度模式：高精度版 -> 高精度含位置版 -> 通用标准版 -> 通用标准含位置版
            chain.append((self.OCR_ACCURATE_BASIC_URL, "高精度版", False))
            chain.append((self.OCR_ACCURATE_URL, "高精度含位置版", True))
            chain.append((self.OCR_GENERAL_BASIC_URL, "通用标准版", False))
            chain.append((self.OCR_GENERAL_URL, "通用标准含位置版", True))
        else:
            # 通用模式：通用标准版 -> 通用标准含位置版
            chain.append((self.OCR_GENERAL_BASIC_URL, "通用标准版", False))
            chain.append((self.OCR_GENERAL_URL, "通用标准含位置版", True))
        
        return chain
    
    def _call_ocr_api(self, ocr_url: str, token: str, image_base64: str, 
                      language: str) -> Tuple[dict, Optional[int]]:
        """
        调用OCR API
        
        Returns:
            (result_dict, error_code) - error_code为None表示成功
        """
        url = f"{ocr_url}?access_token={token}"
        
        params = {
            "image": image_base64,
            "language_type": language,
            "detect_direction": "false",
            "paragraph": "false",
        }
        
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        
        error_code = result.get("error_code")
        return result, error_code

    def recognize_image(self, image: QImage, language: str = "CHN_ENG") -> BaiduOCRResult:
        """
        识别图片中的文字（支持自动降级）
        
        降级策略：
        1. 高精度版（1000次/月）- 优先使用
        2. 高精度含位置版（500次/月）
        3. 通用标准版（1000次/月）
        4. 通用标准含位置版（1000次/月）- 最后备用
        
        当某个API配额耗尽时，自动尝试下一个API
        
        Args:
            image: 要识别的QImage
            language: 识别语言类型
        """
        baidu_debug_log("=" * 50)
        baidu_debug_log("开始百度云OCR识别")
        
        if image.isNull():
            return BaiduOCRResult.error_result("图片为空")
        
        baidu_debug_log(f"图片尺寸: {image.width()}x{image.height()}")
        
        # 获取Access Token
        token = self._get_access_token()
        if not token:
            return BaiduOCRResult.error_result("获取Access Token失败，请检查API密钥配置")
        
        # 图片转Base64
        image_base64 = self._qimage_to_base64(image)
        if not image_base64:
            return BaiduOCRResult.error_result("图片编码失败")
        
        baidu_debug_log(f"图片Base64长度: {len(image_base64)}")
        
        # 获取API降级链
        api_chain = self._get_api_fallback_chain()
        last_error = None
        
        for ocr_url, api_name, has_location in api_chain:
            try:
                baidu_debug_log(f"尝试调用: {api_name}")
                
                result, error_code = self._call_ocr_api(ocr_url, token, image_base64, language)
                
                # 检查是否配额耗尽，需要降级
                if error_code in self.QUOTA_EXHAUSTED_CODES:
                    error_msg = result.get("error_msg", "配额耗尽")
                    baidu_debug_log(f"{api_name} 配额耗尽: {error_msg}，尝试降级...")
                    last_error = f"{api_name}: {error_msg}"
                    continue
                
                # 其他错误，直接返回
                if error_code is not None:
                    error_msg = result.get("error_msg", "未知错误")
                    baidu_debug_log(f"OCR错误: {error_msg}")
                    return BaiduOCRResult.error_result(f"百度OCR错误: {error_msg}")
                
                baidu_debug_log(f"OCR响应: {json.dumps(result, ensure_ascii=False)[:500]}")
                
                # 解析结果
                words_result = result.get("words_result", [])
                if not words_result:
                    baidu_debug_log("未识别到文字")
                    return BaiduOCRResult(success=True, text="", words_result=[])
                
                baidu_debug_log(f"识别到 {len(words_result)} 个文本框")
                
                # 根据是否有位置信息选择合并方式
                if has_location:
                    merged_lines = self._merge_same_line_words(words_result)
                else:
                    # 不含位置版，直接提取文字
                    merged_lines = [item.get("words", "") for item in words_result if item.get("words")]
                
                full_text = "\n".join(merged_lines)
                baidu_debug_log(f"使用 {api_name} 识别成功，共 {len(merged_lines)} 行文字")
                
                return BaiduOCRResult(
                    success=True,
                    text=full_text,
                    words_result=words_result
                )
                
            except urllib.error.URLError as e:
                baidu_debug_log(f"网络错误: {str(e)}")
                return BaiduOCRResult.error_result(f"网络错误: {str(e)}")
            except Exception as e:
                baidu_debug_log(f"OCR异常: {str(e)}")
                last_error = str(e)
                continue
        
        # 所有API都失败
        return BaiduOCRResult.error_result(f"所有API配额已耗尽: {last_error}")

    def _merge_same_line_words(self, words_result: List[Dict[str, Any]]) -> List[str]:
        """
        合并同一行的文字，保持原图排版
        
        百度OCR返回的每个词都有location信息：
        {
            "words": "文字内容",
            "location": {"top": y, "left": x, "width": w, "height": h}
        }
        """
        if not words_result:
            return []
        
        # 提取位置信息
        word_info = []
        for item in words_result:
            words = item.get("words", "")
            location = item.get("location", {})
            
            if not words:
                continue
            
            top = location.get("top", 0)
            left = location.get("left", 0)
            height = max(location.get("height", 20), 1)  # 确保height至少为1，避免异常数据
            
            word_info.append({
                "words": words,
                "top": top,
                "left": left,
                "height": height,
                "y_center": top + height / 2
            })
        
        if not word_info:
            return []
        
        # 按Y坐标排序
        word_info.sort(key=lambda x: x["y_center"])
        
        # 合并同一行的文字
        lines = []
        current_line = [word_info[0]]
        
        for i in range(1, len(word_info)):
            curr = word_info[i]
            prev = current_line[-1]
            
            # 判断是否在同一行：Y坐标中心点距离小于较小高度的50%
            min_height = min(curr["height"], prev["height"])
            threshold = max(min_height * 0.5, 10)  # 至少10像素
            
            y_diff = abs(curr["y_center"] - prev["y_center"])
            
            if y_diff <= threshold:
                # 同一行
                current_line.append(curr)
            else:
                # 新的一行
                lines.append(current_line)
                current_line = [curr]
        
        # 添加最后一行
        if current_line:
            lines.append(current_line)
        
        # 对每行按X坐标排序，然后合并文字
        merged_lines = []
        for line in lines:
            # 按X坐标排序
            line.sort(key=lambda x: x["left"])
            
            # 合并文字（用空格连接）
            texts = [item["words"] for item in line]
            merged_text = " ".join(texts)
            merged_lines.append(merged_text)
        
        baidu_debug_log(f"合并前 {len(words_result)} 个框，合并后 {len(merged_lines)} 行")
        return merged_lines
