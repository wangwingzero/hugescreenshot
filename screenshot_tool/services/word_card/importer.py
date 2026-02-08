# -*- coding: utf-8 -*-
"""
单词卡导入逻辑

从 AnkiTrans/单词卡工具 集成
"""
import os
from typing import Tuple, Optional, Callable

from .utils import anki_request, create_deck, store_media_file_from_path, add_note
from .services import WordCardService
from .templates import MODEL_NAME, FIELDS, CARD1_FRONT, CARD1_BACK, CARD2_FRONT, CARD2_BACK, CSS


def ensure_model_exists() -> bool:
    """确保模板存在且包含两个卡片模板"""
    models = anki_request('modelNames') or []
    
    if MODEL_NAME not in models:
        anki_request('createModel', {
            'modelName': MODEL_NAME,
            'inOrderFields': FIELDS,
            'css': CSS,
            'cardTemplates': [
                {'Name': '英译中', 'Front': CARD1_FRONT, 'Back': CARD1_BACK},
                {'Name': '中译英', 'Front': CARD2_FRONT, 'Back': CARD2_BACK}
            ]
        })
        print(f"✓ 已创建模板: {MODEL_NAME} (含2张卡片)")
        return True
    
    templates = anki_request('modelTemplates', {'modelName': MODEL_NAME}) or {}
    existing_names = list(templates.keys())
    updated = False
    
    if '英译中' not in existing_names:
        try:
            anki_request('modelTemplateAdd', {
                'modelName': MODEL_NAME,
                'template': {'Name': '英译中', 'Front': CARD1_FRONT, 'Back': CARD1_BACK}
            })
            print(f"✓ 已添加卡片模板: 英译中")
            updated = True
        except Exception as e:
            print(f"⚠ 添加英译中卡片失败: {e}")
    
    if '中译英' not in existing_names:
        try:
            anki_request('modelTemplateAdd', {
                'modelName': MODEL_NAME,
                'template': {'Name': '中译英', 'Front': CARD2_FRONT, 'Back': CARD2_BACK}
            })
            print(f"✓ 已添加卡片模板: 中译英")
            updated = True
        except Exception as e:
            print(f"⚠ 添加中译英卡片失败: {e}")
    
    try:
        anki_request('updateModelStyling', {'model': {'name': MODEL_NAME, 'css': CSS}})
    except Exception:
        pass
    
    if updated:
        print(f"✓ 已更新模板: {MODEL_NAME}")
    
    return updated


def import_single_word(
    word: str,
    deck_name: str,
    service: WordCardService,
    book_image_path: str = ''
) -> Tuple[bool, str, str]:
    """
    导入单个单词到 Anki
    
    Returns:
        (success: bool, word: str, status: str)
    """
    if not word or not word.strip():
        return False, word or '', "✗ 单词为空"
    
    try:
        data = service.query(word)
    except Exception as e:
        print(f"[Anki] 查询 {word} 失败: {e}")
        return False, word, f"✗ 查询失败"
    
    audio_field = ''
    if data.get('audio_path') and os.path.exists(data['audio_path']):
        store_media_file_from_path(data['audio_path'])
        audio_field = f"[sound:{data['audio_filename']}]"
    
    image_field = ''
    if data.get('image_path') and os.path.exists(data['image_path']):
        store_media_file_from_path(data['image_path'])
        image_field = f'<img src="{data["image_filename"]}">'
    
    book_image_field = ''
    if book_image_path and os.path.exists(book_image_path):
        store_media_file_from_path(book_image_path)
        book_filename = os.path.basename(book_image_path)
        book_image_field = f'<img src="{book_filename}">'
    
    note = {
        'deckName': deck_name,
        'modelName': MODEL_NAME,
        'fields': {
            '单词': word,
            '音标': data.get('phonetic', ''),
            '中文释义': data.get('definition', ''),
            '单词发音': audio_field,
            '单词配图': image_field,
            '绘本原图': book_image_field,
        },
        'options': {'allowDuplicate': False}
    }
    
    result = add_note(note)
    
    if result:
        status = "✓ 已导入"
    elif data.get('definition'):
        status = "⚠ 重复跳过"
    else:
        status = "✗ 无释义"
    
    return result is not None, word, status


def import_words(
    words: list,
    deck_name: str,
    screenshot_path: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Tuple[int, int]:
    """
    导入单词列表到 Anki
    
    Args:
        words: 单词列表
        deck_name: 牌组名称
        screenshot_path: 截图路径（作为绘本原图）
        progress_callback: 进度回调 (current, total, word)
    
    Returns:
        (成功数, 总数)
    """
    create_deck(deck_name)
    ensure_model_exists()
    
    service = WordCardService()
    total = len(words)
    success = 0
    
    for i, word in enumerate(words):
        if progress_callback:
            progress_callback(i + 1, total, word)
        
        ok, _, _ = import_single_word(word, deck_name, service, screenshot_path or '')
        if ok:
            success += 1
    
    return success, total
