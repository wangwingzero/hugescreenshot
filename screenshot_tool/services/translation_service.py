# =====================================================
# =============== 翻译服务 ===============
# =====================================================

"""
翻译服务 - 支持多个免费翻译源

支持的翻译源（无需API密钥）：
- 有道词典（查词）
- 必应翻译
- 谷歌翻译（需要能访问）
"""

import json
import urllib.request
import urllib.parse
import re
import time
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class TranslationSource(Enum):
    """翻译源"""
    YOUDAO_DICT = "youdao_dict"  # 有道词典
    BING = "bing"  # 必应翻译
    GOOGLE = "google"  # 谷歌翻译


@dataclass
class TranslationResult:
    """翻译结果"""
    success: bool
    text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    source: str = ""
    error: Optional[str] = None
    
    @classmethod
    def error_result(cls, error_msg: str, source: str = "") -> "TranslationResult":
        return cls(success=False, error=error_msg, source=source)


# 语言代码映射
LANG_CODES = {
    "bing": {
        "中文": "zh-Hans", "英语": "en", "日语": "ja", "韩语": "ko",
        "法语": "fr", "德语": "de", "俄语": "ru", "西班牙语": "es",
        "繁体中文": "zh-Hant", "自动": "auto-detect"
    },
    "google": {
        "中文": "zh-CN", "英语": "en", "日语": "ja", "韩语": "ko",
        "法语": "fr", "德语": "de", "俄语": "ru", "西班牙语": "es",
        "繁体中文": "zh-TW", "自动": "auto"
    }
}


class TranslationService:
    """翻译服务 - 自动尝试多个免费翻译源"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        # 调整优先级：有道词典最稳定
        self.sources = [
            TranslationSource.YOUDAO_DICT,
            TranslationSource.GOOGLE,
            TranslationSource.BING,
        ]
    
    def translate(self, text: str, target_lang: str = "中文", 
                  source_lang: str = "自动") -> TranslationResult:
        """翻译文本"""
        if not text or not text.strip():
            return TranslationResult.error_result("文本为空")
        
        text = text.strip()
        
        # 如果文本太长，截断
        if len(text) > 5000:
            text = text[:5000]
        
        errors = []
        for source in self.sources:
            try:
                result = self._translate_with_source(text, target_lang, source_lang, source)
                if result.success:
                    return result
                errors.append(f"{source.value}: {result.error}")
            except Exception as e:
                errors.append(f"{source.value}: {str(e)}")
        
        return TranslationResult.error_result(f"翻译失败: {'; '.join(errors)}")
    
    def _translate_with_source(self, text: str, target_lang: str, 
                                source_lang: str, source: TranslationSource) -> TranslationResult:
        """使用指定翻译源"""
        if source == TranslationSource.BING:
            return self._translate_bing(text, target_lang, source_lang)
        elif source == TranslationSource.GOOGLE:
            return self._translate_google(text, target_lang, source_lang)
        elif source == TranslationSource.YOUDAO_DICT:
            return self._translate_youdao_dict(text, target_lang, source_lang)
        return TranslationResult.error_result(f"未知翻译源: {source}")
    
    def _get_lang_code(self, lang: str, source: str) -> str:
        """获取语言代码"""
        codes = LANG_CODES.get(source, {})
        return codes.get(lang, lang)
    
    def _translate_bing(self, text: str, target_lang: str, 
                        source_lang: str) -> TranslationResult:
        """必应翻译 - 使用网页版接口"""
        try:
            tgt = self._get_lang_code(target_lang, "bing")
            
            # 使用必应翻译的简单 GET 接口
            encoded_text = urllib.parse.quote(text)
            url = f"https://api.microsofttranslator.com/v2/ajax.svc/TranslateArray2?appId=&texts=%5B%22{encoded_text}%22%5D&from=&to={tgt}&options=%7B%7D&oncomplete=onComplete&onerror=onError&_={int(time.time()*1000)}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            req.add_header("Referer", "https://www.bing.com/translator")
            
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_text = resp.read().decode("utf-8")
                
                # 解析 JSONP 响应
                match = re.search(r'onComplete\(\s*(\[.*?\])\s*\)', response_text)
                if match:
                    result = json.loads(match.group(1))
                    if result and len(result) > 0:
                        translated = result[0].get("TranslatedText", "")
                        if translated:
                            return TranslationResult(
                                success=True, text=translated,
                                source_lang=source_lang, target_lang=target_lang,
                                source="bing"
                            )
            
            return TranslationResult.error_result("解析结果失败", "bing")
            
        except Exception as e:
            return TranslationResult.error_result(str(e), "bing")
    
    def _translate_google(self, text: str, target_lang: str, 
                          source_lang: str) -> TranslationResult:
        """谷歌翻译（使用 translate.googleapis.com）"""
        try:
            tgt = self._get_lang_code(target_lang, "google")
            src = self._get_lang_code(source_lang, "google")
            
            # 使用谷歌翻译 API
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={tgt}&dt=t&q={urllib.parse.quote(text)}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 解析结果 [[["翻译结果","原文",...],...],...]
            if isinstance(result, list) and len(result) > 0:
                translations = result[0]
                if isinstance(translations, list):
                    translated_parts = []
                    for item in translations:
                        if isinstance(item, list) and len(item) > 0:
                            translated_parts.append(str(item[0]))
                    
                    if translated_parts:
                        return TranslationResult(
                            success=True, text="".join(translated_parts),
                            source_lang=source_lang, target_lang=target_lang,
                            source="google"
                        )
            
            return TranslationResult.error_result("解析结果失败", "google")
            
        except Exception as e:
            return TranslationResult.error_result(str(e), "google")
    
    def _translate_youdao_dict(self, text: str, target_lang: str, 
                               source_lang: str) -> TranslationResult:
        """有道词典（适合单词和短语）"""
        try:
            # 有道词典 API（适合查词）
            url = f"https://dict.youdao.com/suggest?num=1&doctype=json&q={urllib.parse.quote(text)}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 解析结果
            if result.get("result", {}).get("code") == 200:
                entries = result.get("data", {}).get("entries", [])
                if entries:
                    # 获取第一个结果的解释
                    explain = entries[0].get("explain", "")
                    if explain:
                        return TranslationResult(
                            success=True, text=explain,
                            source_lang=source_lang, target_lang=target_lang,
                            source="youdao_dict"
                        )
            
            return TranslationResult.error_result("未找到翻译", "youdao_dict")
            
        except Exception as e:
            return TranslationResult.error_result(str(e), "youdao_dict")
    
    def get_supported_languages(self) -> List[str]:
        """获取支持的目标语言列表"""
        return ["中文", "英语", "日语", "韩语", "法语", "德语", "俄语", "西班牙语", "繁体中文"]
