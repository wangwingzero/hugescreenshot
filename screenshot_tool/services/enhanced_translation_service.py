# =====================================================
# =============== 增强翻译服务 ===============
# =====================================================

"""
增强翻译服务 - 支持多引擎、缓存、降级

Features:
- 统一接口
- 有道翻译
- MyMemory 翻译（免费API）
- Papago 翻译（Naver）
- 简心翻译（保底）
- 翻译缓存
- 引擎降级
- 自动语言检测
"""

import json
import socket
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
from collections import OrderedDict


class TranslationEngine(Enum):
    """翻译引擎"""
    YOUDAO = "youdao"      # 有道翻译（原生）
    MYMEMORY = "mymemory"  # MyMemory 翻译（免费，每天1000次）
    PAPAGO = "papago"      # Papago 翻译（Naver）
    JIANXIN = "jianxin"    # 简心翻译（保底）


@dataclass
class TranslationResult:
    """翻译结果"""
    success: bool
    source_text: str
    translated_text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    engine: str = ""
    error: Optional[str] = None
    from_cache: bool = False
    
    @classmethod
    def error_result(cls, source_text: str, error_msg: str, engine: str = "") -> "TranslationResult":
        return cls(
            success=False, 
            source_text=source_text,
            error=error_msg, 
            engine=engine
        )


class LRUCache:
    """LRU 缓存"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
    
    def _make_key(self, text: str, target_lang: str, source_lang: str) -> str:
        """生成缓存键"""
        return f"{text}|{target_lang}|{source_lang}"
    
    def get(self, text: str, target_lang: str, source_lang: str) -> Optional[TranslationResult]:
        """获取缓存"""
        key = self._make_key(text, target_lang, source_lang)
        if key in self._cache:
            # 移到末尾（最近使用）
            self._cache.move_to_end(key)
            result = self._cache[key]
            # 标记为来自缓存
            return TranslationResult(
                success=result.success,
                source_text=result.source_text,
                translated_text=result.translated_text,
                source_lang=result.source_lang,
                target_lang=result.target_lang,
                engine=result.engine,
                error=result.error,
                from_cache=True
            )
        return None
    
    def set(self, text: str, target_lang: str, source_lang: str, result: TranslationResult):
        """设置缓存"""
        key = self._make_key(text, target_lang, source_lang)
        self._cache[key] = result
        self._cache.move_to_end(key)
        
        # 超出容量时删除最旧的
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
    
    def size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)


# 中文名称到语言代码的映射
LANG_NAME_TO_CODE = {
    "中文": "zh",
    "英语": "en",
    "英文": "en",
    "日语": "ja",
    "日文": "ja",
    "韩语": "ko",
    "韩文": "ko",
    "法语": "fr",
    "德语": "de",
    "俄语": "ru",
    "西班牙语": "es",
    "繁体中文": "zh-TW",
    "自动": "auto",
}

# 语言代码映射
LANG_CODES = {
    "youdao": {
        "zh": "zh-CHS", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "ru": "ru", "es": "es",
        "auto": "auto"
    },
    "jianxin": {
        "zh": "zh", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "ru": "ru", "es": "es",
        "auto": "auto"
    },
    "mymemory": {
        "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "ru": "ru", "es": "es",
        "zh-TW": "zh-TW", "auto": "en"  # MyMemory 不支持 auto，默认英语
    },
    "papago": {
        "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "ru": "ru", "es": "es",
        "zh-TW": "zh-TW", "auto": "en"  # Papago 不支持 auto，默认英语
    }
}


class EnhancedTranslationService:
    """增强翻译服务 - 支持多引擎、缓存、降级"""
    
    # 最大文本长度限制（字符数）
    MAX_TEXT_LENGTH = 5000
    
    def __init__(self, default_engine: TranslationEngine = TranslationEngine.MYMEMORY,
                 cache_enabled: bool = True, timeout: int = 10):
        """
        初始化翻译服务
        
        Args:
            default_engine: 默认翻译引擎
            cache_enabled: 是否启用缓存
            timeout: 请求超时时间（秒），范围 1-60
        """
        self._default_engine = default_engine
        self._cache_enabled = cache_enabled
        # 验证并限制超时范围
        self._timeout = max(1, min(60, timeout))
        self._cache = LRUCache(max_size=1000)
        
        # 引擎优先级（用于降级）
        # MyMemory 对句子翻译更准确，放在第一位
        # 有道词典主要适合单词翻译
        self._engine_priority = [
            TranslationEngine.MYMEMORY,  # MyMemory 免费API（句子翻译更准确）
            TranslationEngine.YOUDAO,    # 有道翻译（单词翻译）
            TranslationEngine.PAPAGO,    # Papago (Naver)
            TranslationEngine.JIANXIN,   # 简心作为最终保底
        ]
    
    def set_default_engine(self, engine: TranslationEngine):
        """设置默认引擎"""
        self._default_engine = engine
    
    def set_cache_enabled(self, enabled: bool):
        """设置是否启用缓存"""
        self._cache_enabled = enabled
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
    
    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return self._cache.size()
    
    def smart_translate(self, text: str) -> TranslationResult:
        """智能翻译 - 自动检测语言并翻译到另一种语言
        
        - 检测到中文 → 翻译成英语
        - 检测到英文 → 翻译成中文
        
        Args:
            text: 要翻译的文本
        
        Returns:
            TranslationResult: 翻译结果
        """
        if not text or not text.strip():
            return TranslationResult.error_result(text or "", "文本为空")
        
        text = text.strip()
        
        # 检测语言
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        
        if has_chinese:
            # 中文 → 英语
            return self.translate(text, "en", "zh")
        else:
            # 英文 → 中文
            return self.translate(text, "zh", "en")
    
    def translate(self, text: str, target_lang: str = "zh", 
                  source_lang: str = "auto") -> TranslationResult:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            target_lang: 目标语言（支持中文名称如"中文"、"英语"，或代码如"zh"、"en"）
            source_lang: 源语言（auto=自动检测）
        
        Returns:
            TranslationResult: 翻译结果
        """
        if not text or not text.strip():
            return TranslationResult.error_result(text or "", "文本为空")
        
        text = text.strip()
        
        # 转换中文语言名称为语言代码
        target_lang = LANG_NAME_TO_CODE.get(target_lang, target_lang)
        source_lang = LANG_NAME_TO_CODE.get(source_lang, source_lang)
        
        # 文本长度检查
        if len(text) > self.MAX_TEXT_LENGTH:
            return TranslationResult.error_result(
                text, f"文本过长（最大{self.MAX_TEXT_LENGTH}字符）"
            )
        
        # 检查缓存
        if self._cache_enabled:
            cached = self._cache.get(text, target_lang, source_lang)
            if cached:
                return cached
        
        # 构建引擎尝试顺序：默认引擎优先
        engines_to_try = [self._default_engine]
        for engine in self._engine_priority:
            if engine != self._default_engine:
                engines_to_try.append(engine)
        
        # 尝试翻译
        errors = []
        for engine in engines_to_try:
            if not self._is_engine_available(engine):
                continue
            
            try:
                result = self._translate_with_engine(text, target_lang, source_lang, engine)
                if result.success:
                    # 缓存成功结果
                    if self._cache_enabled:
                        self._cache.set(text, target_lang, source_lang, result)
                    return result
                errors.append(f"{engine.value}: {result.error}")
            except Exception as e:
                errors.append(f"{engine.value}: {str(e)}")
        
        return TranslationResult.error_result(text, f"翻译失败: {'; '.join(errors)}")
    
    def _is_engine_available(self, engine: TranslationEngine) -> bool:
        """检查引擎是否可用"""
        if engine == TranslationEngine.YOUDAO:
            return True  # 有道翻译始终可用
        elif engine == TranslationEngine.MYMEMORY:
            return True  # MyMemory 始终可用（免费API）
        elif engine == TranslationEngine.PAPAGO:
            return True  # Papago 始终可用（Naver）
        elif engine == TranslationEngine.JIANXIN:
            return True  # 简心翻译始终可用（保底）
        return False
    
    def get_available_engines(self) -> List[TranslationEngine]:
        """获取可用的翻译引擎"""
        return [e for e in TranslationEngine if self._is_engine_available(e)]
    
    def _translate_with_engine(self, text: str, target_lang: str, 
                                source_lang: str, engine: TranslationEngine) -> TranslationResult:
        """使用指定引擎翻译"""
        if engine == TranslationEngine.YOUDAO:
            return self._translate_youdao(text, target_lang, source_lang)
        elif engine == TranslationEngine.MYMEMORY:
            return self._translate_mymemory(text, target_lang, source_lang)
        elif engine == TranslationEngine.PAPAGO:
            return self._translate_papago(text, target_lang, source_lang)
        elif engine == TranslationEngine.JIANXIN:
            return self._translate_jianxin(text, target_lang, source_lang)
        return TranslationResult.error_result(text, f"未知引擎: {engine}")
    
    def _get_lang_code(self, lang: str, engine: str) -> str:
        """获取语言代码"""
        codes = LANG_CODES.get(engine, {})
        return codes.get(lang, lang)
    
    def _detect_source_language(self, text: str, source_lang: str, engine_lang_code: str) -> str:
        """检测源语言（当源语言为 auto 时）
        
        Args:
            text: 要翻译的文本
            source_lang: 原始源语言参数
            engine_lang_code: 引擎特定的语言代码
        
        Returns:
            检测到的语言代码（zh-CN 或 en）
        """
        # 只有当源语言是 auto 时才进行检测
        if source_lang != "auto" and engine_lang_code != "auto":
            return engine_lang_code
        
        # 简单的语言检测：检查是否包含中文字符
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        return "zh-CN" if has_chinese else "en"
    
    def _is_same_language(self, src: str, tgt: str) -> bool:
        """检查源语言和目标语言是否相同
        
        Args:
            src: 源语言代码
            tgt: 目标语言代码
        
        Returns:
            True 如果语言相同
        """
        if src == tgt:
            return True
        # 中文变体视为相同语言
        if src.startswith("zh") and tgt.startswith("zh"):
            return True
        return False

    def _translate_youdao(self, text: str, target_lang: str, 
                          source_lang: str) -> TranslationResult:
        """有道翻译（原生API + 备用API自动降级）
        
        1. 先尝试原生有道词典 API (dict.youdao.com)
        2. 失败后降级到备用API
        
        注意：有道词典 API 主要支持英汉互译，不支持指定目标语言
        当目标语言是英语时，跳过有道（让其他引擎处理）
        """
        # 有道词典 API 只支持英译中，不支持中译英或英译英
        # 当目标语言是英语时，跳过有道
        tgt = self._get_lang_code(target_lang, "youdao")
        if tgt == "en":
            return TranslationResult.error_result(text, "有道词典不支持翻译到英语", "youdao")
        
        # 先尝试原生有道翻译
        result = self._translate_youdao_native(text, target_lang, source_lang)
        if result.success:
            return result
        
        # 原生失败，尝试备用API（这里可以添加其他备用有道API）
        # 目前有道没有其他免费备用API，直接返回原生结果
        return result
    
    def _translate_youdao_native(self, text: str, target_lang: str, 
                                  source_lang: str) -> TranslationResult:
        """有道翻译原生API（dict.youdao.com）"""
        try:
            # 使用有道词典 API
            encoded_text = urllib.parse.quote(text, encoding='utf-8', safe='')
            url = f"https://dict.youdao.com/jsonapi_s?doctype=json&jsonversion=4&q={encoded_text}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 检测源语言（从 API 响应中获取）
            detected_lang = result.get("lang", source_lang)
            if isinstance(detected_lang, str) and "-" in detected_lang:
                # 格式如 "en-zh" 表示英译中
                detected_lang = detected_lang.split("-")[0]
            
            # 尝试从 fanyi 获取翻译（优先，因为这是完整句子翻译）
            fanyi = result.get("fanyi", {})
            if fanyi:
                tran = fanyi.get("tran", "")
                if tran and isinstance(tran, str) and tran.strip():
                    return TranslationResult(
                        success=True,
                        source_text=text,
                        translated_text=tran.strip(),
                        source_lang=fanyi.get("src", detected_lang),
                        target_lang=target_lang,
                        engine="youdao"
                    )
            
            # 尝试从 ec (英汉词典) 获取翻译
            ec = result.get("ec", {})
            if ec:
                # 优先使用 web_trans（网络释义，更适合短语）
                web_trans = ec.get("web_trans", [])
                if web_trans and len(web_trans) > 0:
                    first_trans = web_trans[0]
                    if isinstance(first_trans, str) and first_trans.strip():
                        return TranslationResult(
                            success=True,
                            source_text=text,
                            translated_text=first_trans.strip(),
                            source_lang=detected_lang,
                            target_lang=target_lang,
                            engine="youdao"
                        )
                
                # 使用词典释义
                word = ec.get("word", {})
                trs = word.get("trs", [])
                if trs and len(trs) > 0:
                    # 获取第一个翻译
                    first_tran = trs[0].get("tran", "")
                    if first_tran and isinstance(first_tran, str) and first_tran.strip():
                        return TranslationResult(
                            success=True,
                            source_text=text,
                            translated_text=first_tran.strip(),
                            source_lang=detected_lang,
                            target_lang=target_lang,
                            engine="youdao"
                        )
            
            # 尝试从 ce (汉英词典) 获取翻译
            ce = result.get("ce", {})
            if ce:
                word = ce.get("word", {})
                trs = word.get("trs", [])
                if trs and len(trs) > 0:
                    first_item = trs[0]
                    if isinstance(first_item, dict):
                        tr = first_item.get("tr", [])
                        if tr and len(tr) > 0:
                            l = tr[0].get("l", {})
                            i_list = l.get("i", [])
                            if i_list and len(i_list) > 0:
                                translated = str(i_list[0]).strip()
                                if translated:
                                    return TranslationResult(
                                        success=True,
                                        source_text=text,
                                        translated_text=translated,
                                        source_lang=detected_lang,
                                        target_lang=target_lang,
                                        engine="youdao"
                                    )
            
            # 尝试从 simple 获取简单翻译
            simple = result.get("simple", {})
            if simple:
                word_list = simple.get("word", [])
                if word_list and len(word_list) > 0:
                    return_phrase = word_list[0].get("return-phrase", {})
                    if return_phrase:
                        l = return_phrase.get("l", {})
                        i = l.get("i", [])
                        if i and len(i) > 0:
                            first_item = i[0]
                            if isinstance(first_item, str) and first_item.strip():
                                return TranslationResult(
                                    success=True,
                                    source_text=text,
                                    translated_text=first_item.strip(),
                                    source_lang=detected_lang,
                                    target_lang=target_lang,
                                    engine="youdao"
                                )
            
            return TranslationResult.error_result(text, "未找到翻译结果", "youdao")
            
        except socket.timeout:
            return TranslationResult.error_result(text, "请求超时", "youdao")
        except json.JSONDecodeError:
            return TranslationResult.error_result(text, "响应格式错误", "youdao")
        except Exception as e:
            return TranslationResult.error_result(text, str(e), "youdao")
    
    def _translate_jianxin(self, text: str, target_lang: str, 
                           source_lang: str) -> TranslationResult:
        """简心翻译API - 保底翻译
        
        API: https://api.qvqa.cn/api/fanyi
        """
        try:
            tgt = self._get_lang_code(target_lang, "jianxin")
            src = self._get_lang_code(source_lang, "jianxin")
            
            # 构建请求URL - 如果是自动检测，不传source参数
            encoded_text = urllib.parse.quote(text, encoding='utf-8', safe='')
            if source_lang == "auto" or src == "auto":
                url = f"https://api.qvqa.cn/api/fanyi?text={encoded_text}&target={tgt}"
            else:
                url = f"https://api.qvqa.cn/api/fanyi?text={encoded_text}&source={src}&target={tgt}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            # 简心翻译不需要代理（国内服务）
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 检查响应状态 - 新版API格式
            # 格式: {"meta": {...}, "data": {"sourceText": "...", "targetText": "..."}}
            data = result.get("data", {})
            if isinstance(data, dict):
                translated = data.get("targetText", "") or data.get("text", "")
                if translated:
                    return TranslationResult(
                        success=True,
                        source_text=text,
                        translated_text=translated.strip(),
                        source_lang=source_lang,
                        target_lang=target_lang,
                        engine="jianxin"
                    )
            
            # 旧版API格式兼容
            code = result.get("code", 0)
            if code == 200 or code == "200":
                old_data = result.get("data", {})
                if isinstance(old_data, dict):
                    translated = old_data.get("targetText", "") or old_data.get("text", "")
                else:
                    translated = str(old_data) if old_data else ""
                
                if translated:
                    return TranslationResult(
                        success=True,
                        source_text=text,
                        translated_text=translated.strip(),
                        source_lang=source_lang,
                        target_lang=target_lang,
                        engine="jianxin"
                    )
            
            error_msg = result.get("message", "") or result.get("msg", "") or "翻译失败"
            return TranslationResult.error_result(text, error_msg, "jianxin")
            
        except socket.timeout:
            return TranslationResult.error_result(text, "请求超时", "jianxin")
        except json.JSONDecodeError:
            return TranslationResult.error_result(text, "响应格式错误", "jianxin")
        except Exception as e:
            return TranslationResult.error_result(text, str(e), "jianxin")

    def _translate_mymemory(self, text: str, target_lang: str, 
                            source_lang: str) -> TranslationResult:
        """MyMemory 翻译API - 免费，每天1000次（匿名）/ 10000次（注册邮箱）
        
        API: https://api.mymemory.translated.net/get
        文档: https://mymemory.translated.net/doc/spec.php
        """
        try:
            tgt = self._get_lang_code(target_lang, "mymemory")
            src = self._get_lang_code(source_lang, "mymemory")
            
            # MyMemory 不支持 auto，需要检测源语言
            src = self._detect_source_language(text, source_lang, src)
            
            # URL 编码文本
            encoded_text = urllib.parse.quote(text, encoding='utf-8', safe='')
            
            # 构建请求URL
            url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair={src}|{tgt}"
            
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            # MyMemory 不需要代理（国内可直接访问）
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 检查响应状态
            response_data = result.get("responseData", {})
            if response_data:
                translated = response_data.get("translatedText", "")
                match = response_data.get("match", 0)
                
                # 检查是否有错误
                if translated and not translated.startswith("MYMEMORY WARNING") and not translated.startswith("PLEASE SELECT"):
                    return TranslationResult(
                        success=True,
                        source_text=text,
                        translated_text=translated.strip(),
                        source_lang=source_lang,
                        target_lang=target_lang,
                        engine="mymemory"
                    )
            
            # 检查错误信息
            error_msg = result.get("responseDetails", "") or "翻译失败"
            return TranslationResult.error_result(text, error_msg, "mymemory")
            
        except socket.timeout:
            return TranslationResult.error_result(text, "请求超时", "mymemory")
        except json.JSONDecodeError:
            return TranslationResult.error_result(text, "响应格式错误", "mymemory")
        except Exception as e:
            return TranslationResult.error_result(text, str(e), "mymemory")
    
    def _translate_papago(self, text: str, target_lang: str, 
                          source_lang: str) -> TranslationResult:
        """Papago 翻译 (Naver) - 免费网页版API
        
        注意：这是非官方API，可能不稳定
        """
        try:
            tgt = self._get_lang_code(target_lang, "papago")
            src = self._get_lang_code(source_lang, "papago")
            
            # Papago 不支持 auto，需要检测源语言
            src = self._detect_source_language(text, source_lang, src)
            
            # 使用 Papago 网页版 API
            url = "https://papago.naver.com/apis/n2mt/translate"
            
            data = {
                "source": src,
                "target": tgt,
                "text": text
            }
            req_data = urllib.parse.urlencode(data).encode("utf-8")
            
            req = urllib.request.Request(url, data=req_data, method="POST")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            
            # Papago 不需要代理
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_text = resp.read().decode("utf-8")
                result = json.loads(response_text)
            
            # 解析结果
            translated = result.get("translatedText", "")
            if translated:
                return TranslationResult(
                    success=True,
                    source_text=text,
                    translated_text=translated.strip(),
                    source_lang=result.get("srcLangType", source_lang),
                    target_lang=result.get("tarLangType", target_lang),
                    engine="papago"
                )
            
            error_msg = result.get("errorMessage", "") or result.get("message", "") or "翻译失败"
            return TranslationResult.error_result(text, error_msg, "papago")
            
        except socket.timeout:
            return TranslationResult.error_result(text, "请求超时", "papago")
        except json.JSONDecodeError:
            return TranslationResult.error_result(text, "响应格式错误", "papago")
        except Exception as e:
            return TranslationResult.error_result(text, str(e), "papago")
