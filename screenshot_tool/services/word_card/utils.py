# -*- coding: utf-8 -*-
"""
AnkiConnect 通信工具 & 通用函数

从 AnkiTrans/单词卡工具 集成
"""
import os
import base64
import requests
from hashlib import sha1

ANKI_URL = "http://127.0.0.1:8765"
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# 媒体文件保存目录（使用用户目录，避免权限问题）
MEDIA_DIR = os.path.join(os.path.expanduser('~'), '.screenshot_tool', 'media_cache')
try:
    os.makedirs(MEDIA_DIR, exist_ok=True)
except OSError as e:
    print(f"[word_card] 创建媒体目录失败: {e}")


def get_hex_name(prefix: str, val: str, suffix: str) -> str:
    """生成基于 SHA1 的唯一文件名"""
    hex_digest = sha1(val.encode('utf-8')).hexdigest().lower()
    name = f"{prefix}-{hex_digest[:8]}-{hex_digest[8:16]}.{suffix}"
    return name


def anki_request(action: str, params: dict = None, timeout: int = 30):
    """发送请求到 AnkiConnect"""
    try:
        payload = {'action': action, 'version': 6}
        if params:
            payload['params'] = params
        r = requests.post(ANKI_URL, json=payload, timeout=timeout)
        result = r.json()
        if result.get('error'):
            raise Exception(result['error'])
        return result.get('result')
    except requests.exceptions.ConnectionError:
        return None
    except Exception as e:
        raise e


def check_connection() -> bool:
    """检查 Anki 连接"""
    try:
        result = anki_request('version')
        return result is not None
    except Exception:
        return False


def get_decks() -> list:
    """获取所有牌组"""
    result = anki_request('deckNames')
    return result if result else []


def create_deck(deck_name: str):
    """创建牌组"""
    if not deck_name or not deck_name.strip():
        return None
    return anki_request('createDeck', {'deck': deck_name.strip()})


def get_models() -> list:
    """获取所有模板"""
    result = anki_request('modelNames')
    return result if result else []


def store_media_file(filename: str, data_bytes: bytes):
    """将媒体文件存储到 Anki"""
    b64_data = base64.b64encode(data_bytes).decode('utf-8')
    return anki_request('storeMediaFile', {
        'filename': filename,
        'data': b64_data
    })


def store_media_file_from_path(filepath: str):
    """从本地文件路径存储到 Anki"""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        filename = os.path.basename(filepath)
        with open(filepath, 'rb') as f:
            data = f.read()
        return store_media_file(filename, data)
    except (IOError, OSError) as e:
        print(f"[Anki] 读取媒体文件失败 {filepath}: {e}")
        return None


def add_note(note_or_deck, model_name=None, fields=None, tags=None):
    """
    添加单个笔记
    支持两种调用方式：
    1. add_note(note_dict) - 传入完整的 note 字典
    2. add_note(deck_name, model_name, fields, tags) - 传入各个参数
    """
    if isinstance(note_or_deck, dict):
        note = note_or_deck
    else:
        note = {
            'deckName': note_or_deck,
            'modelName': model_name,
            'fields': fields,
            'options': {'allowDuplicate': False}
        }
        if tags:
            note['tags'] = tags
    return anki_request('addNote', {'note': note})


def add_notes(notes: list):
    """批量添加笔记"""
    return anki_request('addNotes', {'notes': notes})
