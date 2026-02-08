# =====================================================
# =============== Anki 制卡服务 ===============
# =====================================================

"""
Anki 制卡服务 - 通过 AnkiConnect 创建单词卡

使用本地集成的 word_card 模块（从 AnkiTrans 项目迁移）
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# 导入本地 word_card 模块
ANKI_AVAILABLE = False
ANKI_IMPORT_ERROR = ""
try:
    from screenshot_tool.services.word_card import (
        check_connection,
        create_deck,
        add_note,
        store_media_file_from_path,
        store_media_file,
        anki_request,
        WordCardService,
        ensure_model_exists,
        MODEL_NAME,
        IMAGE_MODEL_NAME,
        IMAGE_MODEL_TEMPLATE,
    )
    ANKI_AVAILABLE = True
except ImportError as e:
    ANKI_IMPORT_ERROR = str(e)
    print(f"[Anki] 无法导入 word_card 模块: {e}")
except Exception as e:
    ANKI_IMPORT_ERROR = str(e)
    print(f"[Anki] 导入异常: {e}")


@dataclass
class AnkiImportResult:
    """Anki 导入结果"""
    success: bool
    total: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    deck_name: str = ""
    error: Optional[str] = None
    
    @classmethod
    def error_result(cls, error: str) -> "AnkiImportResult":
        return cls(success=False, error=error)


class AnkiService:
    """Anki 制卡服务"""
    
    def __init__(self):
        self._word_service = None
    
    @staticmethod
    def is_available() -> bool:
        """检查 Anki 服务是否可用"""
        return ANKI_AVAILABLE
    
    @staticmethod
    def get_import_error() -> str:
        """获取导入错误信息"""
        return ANKI_IMPORT_ERROR
    
    @staticmethod
    def check_connection() -> Tuple[bool, Optional[str]]:
        """检查 Anki 连接状态"""
        if not ANKI_AVAILABLE:
            return False, "word_card 模块未正确加载"
        
        try:
            if check_connection():
                return True, None
            else:
                return False, "无法连接到 Anki，请确保 Anki 已启动并安装了 AnkiConnect 插件"
        except Exception as e:
            return False, f"连接检查失败: {str(e)}"
    
    @staticmethod
    def get_deck_names() -> List[str]:
        """获取 Anki 中所有牌组名称"""
        if not ANKI_AVAILABLE:
            return []
        
        try:
            decks = anki_request("deckNames")
            return decks if decks else []
        except Exception as e:
            print(f"[Anki] 获取牌组列表失败: {e}")
            return []
    
    def _get_word_service(self) -> "WordCardService":
        """获取单词卡服务（懒加载）"""
        if self._word_service is None:
            self._word_service = WordCardService()
        return self._word_service
    
    @staticmethod
    def extract_english_words(text: str) -> List[str]:
        """从文本中提取英文单词"""
        if not text:
            return []
        words = re.findall(r'[a-zA-Z]{2,}', text)
        seen = set()
        unique_words = []
        for word in words:
            word_lower = word.lower()
            if word_lower not in seen:
                seen.add(word_lower)
                unique_words.append(word_lower)
        return unique_words

    
    def import_words(
        self, 
        words: List[str], 
        deck_name: str,
        screenshot_path: Optional[str] = None,
        progress_callback=None
    ) -> AnkiImportResult:
        """导入单词到 Anki"""
        if not ANKI_AVAILABLE:
            return AnkiImportResult.error_result("word_card 模块未正确加载")
        
        connected, error = self.check_connection()
        if not connected:
            return AnkiImportResult.error_result(error)
        
        valid_words = [w.strip().lower() for w in words if w.strip() and len(w.strip()) >= 2]
        if not valid_words:
            return AnkiImportResult.error_result("没有有效的英文单词")
        
        try:
            create_deck(deck_name)
            ensure_model_exists()
            
            book_image_field = ""
            if screenshot_path and os.path.exists(screenshot_path):
                screenshot_filename = os.path.basename(screenshot_path)
                with open(screenshot_path, 'rb') as f:
                    store_media_file(screenshot_filename, f.read())
                book_image_field = f'<img src="{screenshot_filename}">'
            
            service = self._get_word_service()
            
            imported = 0
            skipped = 0
            failed = 0
            total = len(valid_words)
            
            for i, word in enumerate(valid_words):
                if progress_callback:
                    progress_callback(i + 1, total, word)
                
                try:
                    data = service.query(word)
                    
                    audio_field = ''
                    if data.get('audio_path') and os.path.exists(data['audio_path']):
                        store_media_file_from_path(data['audio_path'])
                        audio_field = f"[sound:{data['audio_filename']}]"
                    
                    image_field = ''
                    if data.get('image_path') and os.path.exists(data['image_path']):
                        store_media_file_from_path(data['image_path'])
                        image_field = f'<img src="{data["image_filename"]}">'
                    
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
                        imported += 1
                    else:
                        skipped += 1
                        
                except Exception as e:
                    print(f"[Anki] 导入 {word} 失败: {e}")
                    failed += 1
            
            return AnkiImportResult(
                success=True,
                total=total,
                imported=imported,
                skipped=skipped,
                failed=failed,
                deck_name=deck_name
            )
            
        except Exception as e:
            return AnkiImportResult.error_result(f"导入失败: {str(e)}")


    def import_image_only(
        self,
        screenshot_path: str,
        deck_name: str
    ) -> AnkiImportResult:
        """导入纯图片到 Anki（使用虎哥原图模板）"""
        if not ANKI_AVAILABLE:
            return AnkiImportResult.error_result("word_card 模块未正确加载")
        
        connected, error = self.check_connection()
        if not connected:
            return AnkiImportResult.error_result(error)
        
        if not screenshot_path or not os.path.exists(screenshot_path):
            return AnkiImportResult.error_result("截图文件不存在")
        
        try:
            create_deck(deck_name)
            
            # 确保虎哥原图模板存在
            models = anki_request("modelNames") or []
            if IMAGE_MODEL_NAME not in models:
                anki_request("createModel", IMAGE_MODEL_TEMPLATE)
            
            # 存储截图到 Anki 媒体库
            screenshot_filename = os.path.basename(screenshot_path)
            with open(screenshot_path, 'rb') as f:
                store_media_file(screenshot_filename, f.read())
            
            # 创建卡片
            note = {
                'deckName': deck_name,
                'modelName': IMAGE_MODEL_NAME,
                'fields': {
                    '图片': f'<img src="{screenshot_filename}">'
                },
                'options': {'allowDuplicate': True}
            }
            
            result = add_note(note)
            if result:
                return AnkiImportResult(
                    success=True,
                    total=1,
                    imported=1,
                    skipped=0,
                    failed=0,
                    deck_name=deck_name
                )
            else:
                return AnkiImportResult.error_result("添加卡片失败")
                
        except Exception as e:
            return AnkiImportResult.error_result(f"导入失败: {str(e)}")
