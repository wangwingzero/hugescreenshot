# -*- coding: utf-8 -*-
"""
词典服务 - 独立版本，不依赖 Anki 环境
支持本地缓存，避免重复下载

从 AnkiTrans/单词卡工具 集成
"""
import os
import re
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Tuple, Optional, Dict, Any

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from .utils import DEFAULT_UA, MEDIA_DIR, get_hex_name

# 数据缓存目录
DATA_CACHE_DIR = os.path.join(os.path.expanduser('~'), '.screenshot_tool', 'data_cache')
try:
    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
except OSError as e:
    print(f"[word_card] 创建缓存目录失败: {e}")

# 加载配置文件（旧版兼容）
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.screenshot_tool', 'word_card_config.json')
_config = {}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            _config = json.load(f)
    except Exception:
        pass

# 尝试从主配置读取 API Key
def _load_main_config_api_keys():
    """从主配置文件读取 Anki 图片 API Key"""
    main_config_file = os.path.join(os.path.expanduser('~'), '.screenshot_tool', 'config.json')
    if os.path.exists(main_config_file):
        try:
            with open(main_config_file, 'r', encoding='utf-8-sig') as f:
                main_config = json.load(f)
                anki_config = main_config.get('anki', {})
                return {
                    'unsplash_keys': anki_config.get('unsplash_keys', ''),
                    'pixabay_key': anki_config.get('pixabay_key', ''),
                }
        except Exception:
            pass
    return {'unsplash_keys': '', 'pixabay_key': ''}

_main_api_keys = _load_main_config_api_keys()

# Unsplash API 配置（优先从主配置读取，兼容旧配置）
UNSPLASH_ACCESS_KEYS = []
# 先尝试主配置
if _main_api_keys.get('unsplash_keys'):
    UNSPLASH_ACCESS_KEYS = [k.strip() for k in _main_api_keys['unsplash_keys'].split(',') if k.strip()]
# 兼容旧配置
if not UNSPLASH_ACCESS_KEYS:
    UNSPLASH_ACCESS_KEYS = _config.get('unsplash_access_keys', [])
if not UNSPLASH_ACCESS_KEYS and _config.get('unsplash_access_key'):
    UNSPLASH_ACCESS_KEYS = [_config.get('unsplash_access_key')]
_unsplash_key_index = 0

# Pixabay API 配置（优先从主配置读取，兼容旧配置）
PIXABAY_API_KEYS = []
# 先尝试主配置
if _main_api_keys.get('pixabay_key'):
    PIXABAY_API_KEYS = [k.strip() for k in _main_api_keys['pixabay_key'].split(',') if k.strip()]
# 兼容旧配置
if not PIXABAY_API_KEYS and _config.get('pixabay_api_key'):
    PIXABAY_API_KEYS = [_config.get('pixabay_api_key')]
_pixabay_key_index = 0


def get_next_pixabay_key() -> Optional[str]:
    """获取下一个 Pixabay API Key（轮换使用）"""
    global _pixabay_key_index
    if not PIXABAY_API_KEYS:
        return None
    key = PIXABAY_API_KEYS[_pixabay_key_index % len(PIXABAY_API_KEYS)]
    _pixabay_key_index += 1
    return key


def get_next_unsplash_key() -> Optional[str]:
    """获取下一个 Unsplash API Key（轮换使用）"""
    global _unsplash_key_index
    if not UNSPLASH_ACCESS_KEYS:
        return None
    key = UNSPLASH_ACCESS_KEYS[_unsplash_key_index % len(UNSPLASH_ACCESS_KEYS)]
    _unsplash_key_index += 1
    return key


def get_word_cache_path(word: str) -> str:
    """获取单词缓存文件路径"""
    safe_name = hashlib.md5(word.lower().encode('utf-8')).hexdigest()[:16]
    return os.path.join(DATA_CACHE_DIR, f"{safe_name}.json")


def load_word_cache(word: str) -> Optional[Dict[str, Any]]:
    """加载单词缓存"""
    cache_path = get_word_cache_path(word)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_word_cache(word: str, data: Dict[str, Any]) -> None:
    """保存单词缓存"""
    cache_path = get_word_cache_path(word)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[缓存] 保存 {word} 失败: {e}")


# 有道发音接口参数
YOUDAO_PRONOUNCE_BASE = 'https://dict.youdao.com/pronounce/base'
YOUDAO_PRONOUNCE_SECRET = 'U3uACNRWSDWdcsKm'
YOUDAO_PRONOUNCE_KEY_ID = 'voiceDictWeb'
YOUDAO_PRONOUNCE_PRODUCT = 'webdict'
YOUDAO_PRONOUNCE_KEYFROM = 'dick'


class YoudaoService:
    """有道词典服务 - 音标和发音"""
    
    def __init__(self):
        self.cache = {}
    
    def get_phonetic(self, word: str) -> str:
        """获取音标 (美式)"""
        data = self._get_from_api(word)
        return data.get('us_phonetic', '').strip()
    
    def get_audio(self, word: str, audio_type: int = 2) -> Tuple[Optional[str], Optional[str]]:
        """
        下载发音音频
        audio_type: 1=英式, 2=美式
        返回: (本地文件路径, 文件名) 或 (None, None)
        """
        filename = get_hex_name('youdao', word + str(audio_type), 'mp3')
        filepath = os.path.join(MEDIA_DIR, filename)
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath, filename
        
        content = self._request_pronounce_audio(word, audio_type)
        if content and len(content) > 1000:
            with open(filepath, 'wb') as f:
                f.write(content)
            return filepath, filename
        
        legacy_url = f'http://dict.youdao.com/dictvoice?audio={quote(word)}&type={audio_type}'
        try:
            resp = requests.get(legacy_url, headers={'User-Agent': DEFAULT_UA}, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                return filepath, filename
        except Exception:
            pass
        
        return None, None
    
    def _get_from_api(self, word: str) -> Dict[str, str]:
        """从有道 API 获取数据"""
        if word in self.cache:
            return self.cache[word]
        
        url = (f'http://dict.youdao.com/fsearch?client=deskdict'
               f'&keyfrom=chrome.extension&pos=-1'
               f'&doctype=xml&xmlVersion=3.2'
               f'&dogVersion=1.0&vendor=unknown'
               f'&appVer=3.1.17.4208'
               f'&le=eng&q={quote(word)}')
        
        result = {'phonetic': '', 'us_phonetic': '', 'uk_phonetic': '', 'explains': ''}
        
        try:
            resp = requests.get(url, headers={'User-Agent': DEFAULT_UA}, timeout=5)
            doc = ET.fromstring(resp.content)
            
            symbol = doc.findtext(".//phonetic-symbol")
            uk_symbol = doc.findtext(".//uk-phonetic-symbol")
            us_symbol = doc.findtext(".//us-phonetic-symbol")
            
            if uk_symbol and us_symbol:
                result['phonetic'] = f'UK [{uk_symbol}]   US [{us_symbol}]'
                result['us_phonetic'] = f'/{us_symbol}/'
                result['uk_phonetic'] = f'/{uk_symbol}/'
            elif symbol:
                result['phonetic'] = f'/{symbol}/'
                result['us_phonetic'] = f'/{symbol}/'
            
            explains = '<br>'.join([
                node.text for node in doc.findall(".//custom-translation/translation/content")
                if node.text
            ])
            result['explains'] = explains
        except Exception as e:
            print(f"[有道] 获取 {word} 失败: {e}")
        
        self.cache[word] = result
        return result

    
    def get_definition(self, word: str) -> str:
        """获取释义（用于备用）"""
        data = self._get_from_api(word)
        explains = data.get('explains', '')
        if explains:
            return explains
        return self._get_web_definition(word)
    
    def _get_web_definition(self, word: str) -> str:
        """从有道网页版获取释义"""
        if not BS4_AVAILABLE:
            return ''
        try:
            url = f"https://dict.youdao.com/result?word={quote(word)}&lang=en"
            resp = requests.get(url, headers={'User-Agent': DEFAULT_UA}, timeout=5)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            trans_container = soup.find('div', class_='trans-container')
            if trans_container:
                items = trans_container.find_all('li')
                if items:
                    return '<br>'.join([item.get_text().strip() for item in items])
            
            word_exp = soup.find('div', class_='word-exp')
            if word_exp:
                return word_exp.get_text().strip()
            
            basic = soup.find('div', class_='basic')
            if basic:
                return basic.get_text().strip()
        except Exception as e:
            print(f"[有道网页] 获取 {word} 失败: {e}")
        return ''
    
    def _build_pronounce_params(self, text: str, audio_type: int) -> Dict[str, Any]:
        """构建新版有道发音接口签名参数"""
        base_payload = {'word': text, 'type': audio_type, 'rate': 4, 'phonetic': '', 'le': '', 'id': ''}
        params = {
            'product': YOUDAO_PRONOUNCE_PRODUCT, 'appVersion': 1, 'client': 'web',
            'mid': 1, 'vendor': 'web', 'screen': 1, 'model': 1, 'imei': 1,
            'network': 'wifi', 'keyfrom': YOUDAO_PRONOUNCE_KEYFROM,
            'keyid': YOUDAO_PRONOUNCE_KEY_ID, 'mysticTime': int(time.time() * 1000), 'yduuid': 'abcdefg',
        }
        params.update(base_payload)
        params = {k: v for k, v in params.items() if v not in (None, '')}
        
        sorted_keys = sorted(params.keys())
        sorted_keys.append('key')
        sign_base = '&'.join(f'{key}={YOUDAO_PRONOUNCE_SECRET if key == "key" else params[key]}' for key in sorted_keys)
        params['sign'] = hashlib.md5(sign_base.encode('utf-8')).hexdigest()
        params['pointParam'] = ','.join(sorted_keys)
        return params
    
    def _request_pronounce_audio(self, text: str, audio_type: int) -> Optional[bytes]:
        """请求新版发音接口"""
        params = self._build_pronounce_params(text, audio_type)
        try:
            resp = requests.get(YOUDAO_PRONOUNCE_BASE, params=params, headers={
                'User-Agent': DEFAULT_UA, 'Accept': 'audio/mpeg, audio/*, */*',
                'Referer': 'https://dict.youdao.com/'
            }, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except Exception:
            pass
        return None


class MiniDictService:
    """海词迷你词典服务 - 基本释义"""
    
    def __init__(self):
        self.cache = {}
    
    def get_definition(self, word: str) -> str:
        """获取基本释义"""
        data = self._get_from_api(word)
        return data.get('expressions', '')
    
    def _get_from_api(self, word: str) -> Dict[str, str]:
        """从海词 API 获取数据"""
        if word in self.cache:
            return self.cache[word]
        
        result = {'expressions': '', 'phonetic': ''}
        
        if not BS4_AVAILABLE:
            self.cache[word] = result
            return result
        
        try:
            url = f"http://apii.dict.cn/mini.php?q={quote(word)}"
            resp = requests.get(url, headers={'User-Agent': DEFAULT_UA}, timeout=5)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            tag = soup.find('span', class_='p')
            if tag:
                result['phonetic'] = tag.get_text()
                tag.decompose()
            
            tag = soup.find('div', id='e')
            if tag:
                result['expressions'] = str(tag)
        except Exception as e:
            print(f"[海词] 获取 {word} 失败: {e}")
        
        self.cache[word] = result
        return result


class HudawangImageService:
    """虎大王图片服务 - 聚合多个图片源"""
    
    def __init__(self):
        self.cache = {}
    
    def get_image(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """获取单词配图，返回: (本地文件路径, 文件名) 或 (None, None)"""
        if word in self.cache:
            cached = self.cache[word]
            if cached[0] and os.path.exists(cached[0]):
                return cached
        
        sources = [
            ('Langeek', self._try_langeek),
            ('Unsplash', self._try_unsplash),
            ('Pixabay', self._try_pixabay),
            ('Bing', self._try_bing),
            ('360', self._try_360),
        ]
        
        for name, func in sources:
            try:
                filepath, filename = func(word)
                if filepath and os.path.exists(filepath):
                    print(f"[图片] {word} 来源: {name}")
                    self.cache[word] = (filepath, filename)
                    return filepath, filename
            except Exception as e:
                print(f"[图片] {name} 获取 {word} 失败: {e}")
                continue
        
        self.cache[word] = (None, None)
        return None, None
    
    def _quick_download(self, url: str, prefix: str, word: str) -> Tuple[Optional[str], Optional[str]]:
        """快速下载图片，并验证图片格式"""
        if not url:
            return None, None
        
        ext = 'jpg'
        lower = url.lower()
        if '.png' in lower:
            ext = 'png'
        elif '.gif' in lower:
            ext = 'gif'
        elif '.webp' in lower:
            ext = 'webp'
        
        filename = get_hex_name(prefix, word + url, ext)
        filepath = os.path.join(MEDIA_DIR, filename)
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            if self._is_valid_image(filepath):
                return filepath, filename
            else:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
        
        try:
            resp = requests.get(url, timeout=8, stream=True, headers={'User-Agent': DEFAULT_UA})
            if resp.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                
                if os.path.getsize(filepath) > 1000:
                    real_ext = self._detect_image_format(filepath)
                    if real_ext:
                        if real_ext != ext:
                            new_filename = get_hex_name(prefix, word + url, real_ext)
                            new_filepath = os.path.join(MEDIA_DIR, new_filename)
                            try:
                                os.rename(filepath, new_filepath)
                                return new_filepath, new_filename
                            except Exception:
                                pass
                        return filepath, filename
                    else:
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
        except Exception:
            pass
        return None, None

    
    def _detect_image_format(self, filepath: str) -> Optional[str]:
        """通过 magic bytes 检测图片的真实格式"""
        try:
            with open(filepath, 'rb') as f:
                header = f.read(16)
            
            if len(header) < 4:
                return None
            
            if header[:3] == b'\xff\xd8\xff':
                return 'jpg'
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return 'png'
            if header[:4] == b'GIF8':
                return 'gif'
            if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                return 'webp'
            if header[:5] == b'<?xml' or header[:4] == b'<svg' or header[:1] == b'<':
                return None
            if header[:4] == b'II*\x00' or header[:4] == b'MM\x00*':
                return None
            if header[:2] == b'BM':
                return None
            return None
        except Exception:
            return None
    
    def _is_valid_image(self, filepath: str) -> bool:
        """检查文件是否为有效的 Web 图片格式"""
        return self._detect_image_format(filepath) is not None
    
    def _try_unsplash(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试 Unsplash 图片"""
        access_key = get_next_unsplash_key()
        if not access_key:
            return None, None
        
        api_url = 'https://api.unsplash.com/search/photos'
        headers = {'Authorization': f'Client-ID {access_key}', 'User-Agent': DEFAULT_UA}
        params = {'query': word, 'per_page': 3, 'orientation': 'squarish'}
        
        try:
            resp = requests.get(api_url, headers=headers, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for photo in data.get('results', []):
                    urls = photo.get('urls', {})
                    image_url = urls.get('small') or urls.get('regular')
                    if image_url:
                        img_resp = requests.get(image_url, timeout=10, headers={'User-Agent': DEFAULT_UA})
                        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                            filename = get_hex_name('unsplash', word + photo.get('id', ''), 'jpg')
                            filepath = os.path.join(MEDIA_DIR, filename)
                            with open(filepath, 'wb') as f:
                                f.write(img_resp.content)
                            if self._is_valid_image(filepath):
                                return filepath, filename
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
            elif resp.status_code == 403:
                print(f"[Unsplash] API 配额已用尽")
        except Exception as e:
            print(f"[Unsplash] 请求失败: {e}")
        return None, None

    
    def _try_pixabay(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试 Pixabay 图片"""
        api_key = get_next_pixabay_key()
        if not api_key:
            return None, None
        
        api_url = 'https://pixabay.com/api/'
        params = {'key': api_key, 'q': word, 'lang': 'en', 'image_type': 'photo', 'per_page': 5, 'safesearch': 'true'}
        
        try:
            resp = requests.get(api_url, params=params, timeout=8, headers={'User-Agent': DEFAULT_UA})
            if resp.status_code == 200:
                for hit in resp.json().get('hits', []):
                    image_url = hit.get('webformatURL')
                    if not image_url:
                        continue
                    img_resp = requests.get(image_url, timeout=10, headers={'User-Agent': DEFAULT_UA})
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        filename = get_hex_name('pixabay', word + str(hit.get('id', '')), 'jpg')
                        filepath = os.path.join(MEDIA_DIR, filename)
                        with open(filepath, 'wb') as f:
                            f.write(img_resp.content)
                        if self._is_valid_image(filepath):
                            return filepath, filename
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[Pixabay] 请求失败: {e}")
        return None, None
    
    def _try_langeek(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试 Langeek 图片"""
        api_url = 'https://api.langeek.co/v1/cs/en/word/'
        params = {'term': word, 'filter': ',inCategory,photo,withExamples'}
        
        try:
            resp = requests.get(api_url, params=params, timeout=3, headers={'User-Agent': DEFAULT_UA})
            data = resp.json()
            if data and isinstance(data, list):
                photo_url = self._extract_langeek_photo(data[0])
                if photo_url:
                    return self._quick_download(photo_url, 'langeek', word)
        except Exception:
            pass
        return None, None
    
    def _extract_langeek_photo(self, item: dict) -> str:
        """从 Langeek 响应中提取图片 URL"""
        if not isinstance(item, dict):
            return ''
        
        def _from_translation(tr):
            if not isinstance(tr, dict):
                return ''
            word_photo = tr.get('wordPhoto') or {}
            if not isinstance(word_photo, dict):
                return ''
            for key in ['photoOriginal', 'photoHD', 'photoLarge', 'photo']:
                val = word_photo.get(key)
                if isinstance(val, str) and val:
                    return val
            return ''
        
        photo_url = _from_translation(item.get('translation'))
        if photo_url:
            return photo_url
        
        translations = item.get('translations') or {}
        if isinstance(translations, dict):
            for pos_list in translations.values():
                if isinstance(pos_list, list):
                    for tr in pos_list:
                        photo_url = _from_translation(tr)
                        if photo_url:
                            return photo_url
        return ''

    
    def _try_bing(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试 Bing 图片搜索"""
        search_url = 'https://www.bing.com/images/search'
        search_queries = [
            f'{word} meaning illustration',
            f'{word} definition picture',
            f'{word} concept image',
            f'{word} clipart',
        ]
        
        for query in search_queries:
            try:
                params = {'q': query, 'form': 'HDRSC2', 'first': 1}
                resp = requests.get(search_url, params=params, timeout=5, headers={'User-Agent': DEFAULT_UA})
                matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)
                for url in matches[:3]:
                    filepath, filename = self._quick_download(url, 'bing', word)
                    if filepath:
                        return filepath, filename
            except Exception:
                continue
        return None, None
    
    def _try_360(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试 360 图片搜索"""
        search_url = 'https://image.so.com/j'
        search_queries = [f'{word} 含义', f'{word} meaning', word]
        
        for query in search_queries:
            try:
                params = {'q': query, 'src': 'srp', 'sn': 0, 'pn': 10}
                resp = requests.get(search_url, params=params, timeout=5, headers={'User-Agent': DEFAULT_UA})
                for item in resp.json().get('list', [])[:3]:
                    url = item.get('img') or item.get('thumb')
                    if url:
                        filepath, filename = self._quick_download(url, '360', word)
                        if filepath:
                            return filepath, filename
            except Exception:
                continue
        return None, None


class WordCardService:
    """单词卡聚合服务 - 支持本地缓存"""
    
    def __init__(self):
        self.youdao = YoudaoService()
        self.minidict = MiniDictService()
        self.image = HudawangImageService()
    
    def query(self, word: str) -> Dict[str, Any]:
        """
        查询单词的所有字段，优先使用本地缓存
        返回: {
            'word': 单词,
            'phonetic': 音标,
            'definition': 释义,
            'audio_path': 音频本地路径,
            'audio_filename': 音频文件名,
            'image_path': 图片本地路径,
            'image_filename': 图片文件名,
        }
        """
        if not word:
            return {'word': '', 'phonetic': '', 'definition': '', 
                    'audio_path': None, 'audio_filename': None,
                    'image_path': None, 'image_filename': None}
        
        word = word.strip()
        if not word:
            return {'word': '', 'phonetic': '', 'definition': '', 
                    'audio_path': None, 'audio_filename': None,
                    'image_path': None, 'image_filename': None}
        
        cached = load_word_cache(word)
        if cached:
            audio_ok = not cached.get('audio_path') or os.path.exists(cached['audio_path'])
            image_ok = not cached.get('image_path') or os.path.exists(cached['image_path'])
            if audio_ok and image_ok:
                print(f"[缓存] {word} 使用本地缓存")
                return cached
            else:
                print(f"[缓存] {word} 媒体文件缺失，重新查询")
        
        result = self._query_from_network(word)
        save_word_cache(word, result)
        return result
    
    def _query_from_network(self, word: str) -> Dict[str, Any]:
        """从网络查询单词数据"""
        result = {'word': word}
        
        result['phonetic'] = self.youdao.get_phonetic(word)
        
        definition = self.minidict.get_definition(word)
        if not definition or not definition.strip():
            definition = self.youdao.get_definition(word)
            if definition:
                print(f"[释义] {word} 使用有道备用")
        
        if not definition or not definition.strip():
            clean_word = self._clean_phrase(word)
            if clean_word != word:
                definition = self.minidict.get_definition(clean_word)
                if not definition or not definition.strip():
                    definition = self.youdao.get_definition(clean_word)
                if definition:
                    print(f"[释义] {word} -> {clean_word} 清理后查到")
        
        result['definition'] = definition
        
        audio_path, audio_filename = self.youdao.get_audio(word, audio_type=2)
        result['audio_path'] = audio_path
        result['audio_filename'] = audio_filename
        
        image_path, image_filename = self.image.get_image(word)
        result['image_path'] = image_path
        result['image_filename'] = image_filename
        
        return result
    
    def _clean_phrase(self, word: str) -> str:
        """清理短语中的占位符"""
        cleaned = re.sub(r'\s*(sb\.|sth\.|one\'s|sb/sth|sb\.?/sth\.?)\s*', ' ', word)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
