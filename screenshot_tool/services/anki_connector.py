# =====================================================
# =============== Anki连接器 ===============
# =====================================================

"""
Anki连接器 - 负责与Anki通信进行制卡

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
Property 6: Anki Connection Check
Property 7: Anki Note Field Formatting
"""

import base64
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer, QIODevice


@dataclass
class AnkiNote:
    """Anki笔记"""
    deck_name: str
    model_name: str
    fields: Dict[str, str]
    tags: List[str] = field(default_factory=list)
    image_data: Optional[str] = None  # base64编码的图片数据
    image_filename: Optional[str] = None  # 图片文件名
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "deck_name": self.deck_name,
            "model_name": self.model_name,
            "fields": self.fields,
            "tags": self.tags,
            "image_data": self.image_data,
            "image_filename": self.image_filename,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnkiNote":
        """从字典创建"""
        return cls(
            deck_name=data.get("deck_name", "Default"),
            model_name=data.get("model_name", "Basic"),
            fields=data.get("fields", {}),
            tags=data.get("tags", []),
            image_data=data.get("image_data"),
            image_filename=data.get("image_filename"),
        )
    
    def has_image(self) -> bool:
        """检查是否有图片"""
        return bool(self.image_data and self.image_filename)


class AnkiConnector:
    """
    Anki连接器 - 通过AnkiConnect API与Anki通信
    
    AnkiConnect API文档: https://foosoft.net/projects/anki-connect/
    """
    
    # 默认连接参数
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8765
    
    # AnkiConnect API版本
    API_VERSION = 6
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: int = 10):
        """
        初始化Anki连接器
        
        Args:
            host: AnkiConnect主机地址
            port: AnkiConnect端口
            timeout: 请求超时时间（秒）
        """
        self.host = host
        self.port = port
        self.timeout = timeout
    
    @property
    def api_url(self) -> str:
        """获取API URL"""
        return f"http://{self.host}:{self.port}"
    
    def set_connection(self, host: str, port: int):
        """设置连接参数"""
        self.host = host
        self.port = port

    def _invoke(self, action: str, **params) -> Tuple[Any, Optional[str]]:
        """
        调用AnkiConnect API
        
        Args:
            action: API动作名称
            **params: API参数
            
        Returns:
            Tuple[Any, Optional[str]]: (结果, 错误信息)
        """
        request_data = {
            "action": action,
            "version": self.API_VERSION,
        }
        
        if params:
            request_data["params"] = params
        
        try:
            json_data = json.dumps(request_data).encode("utf-8")
            request = Request(self.api_url, data=json_data)
            request.add_header("Content-Type", "application/json")
            
            with urlopen(request, timeout=self.timeout) as response:
                response_text = response.read().decode("utf-8")
                response_data = json.loads(response_text)
                
                error = response_data.get("error")
                result = response_data.get("result")
                
                return result, error
        
        except HTTPError as e:
            return None, f"HTTP错误: {e.code} {e.reason}"
        except URLError as e:
            return None, f"无法连接到Anki: {e.reason}"
        except json.JSONDecodeError as e:
            return None, f"解析响应失败: {str(e)}"
        except Exception as e:
            return None, f"请求出错: {str(e)}"
    
    def check_connection(self) -> Tuple[bool, Optional[str]]:
        """
        检查Anki连接状态
        
        Returns:
            Tuple[bool, Optional[str]]: (是否连接, 错误信息)
        """
        result, error = self._invoke("version")
        
        if error:
            if "无法连接" in error or "Connection refused" in str(error):
                return False, "无法连接到Anki，请确保Anki已启动并安装了AnkiConnect插件"
            return False, error
        
        if result is None:
            return False, "AnkiConnect响应无效"
        
        return True, None
    
    def get_deck_names(self) -> Tuple[List[str], Optional[str]]:
        """
        获取所有牌组名称
        
        Returns:
            Tuple[List[str], Optional[str]]: (牌组列表, 错误信息)
        """
        result, error = self._invoke("deckNames")
        
        if error:
            return [], error
        
        if result is None:
            return [], "获取牌组列表失败"
        
        return result, None
    
    def get_model_names(self) -> Tuple[List[str], Optional[str]]:
        """
        获取所有笔记类型名称
        
        Returns:
            Tuple[List[str], Optional[str]]: (笔记类型列表, 错误信息)
        """
        result, error = self._invoke("modelNames")
        
        if error:
            return [], error
        
        if result is None:
            return [], "获取笔记类型列表失败"
        
        return result, None
    
    def get_model_field_names(self, model_name: str) -> Tuple[List[str], Optional[str]]:
        """
        获取笔记类型的字段名称
        
        Args:
            model_name: 笔记类型名称
            
        Returns:
            Tuple[List[str], Optional[str]]: (字段列表, 错误信息)
        """
        result, error = self._invoke("modelFieldNames", modelName=model_name)
        
        if error:
            return [], error
        
        if result is None:
            return [], "获取字段列表失败"
        
        return result, None

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
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        
        image_data = buffer.data().data()
        base64_data = base64.b64encode(image_data).decode("utf-8")
        
        return base64_data
    
    def add_note(self, note: AnkiNote) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        添加笔记
        
        Args:
            note: AnkiNote对象
            
        Returns:
            Tuple[bool, Optional[int], Optional[str]]: (是否成功, 笔记ID, 错误信息)
        """
        # 构建笔记参数
        note_params = {
            "deckName": note.deck_name,
            "modelName": note.model_name,
            "fields": note.fields,
            "tags": note.tags,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
        }
        
        # 如果有图片，添加图片
        if note.has_image():
            note_params["picture"] = [{
                "data": note.image_data,
                "filename": note.image_filename,
                "fields": list(note.fields.keys()),  # 添加到所有字段
            }]
        
        result, error = self._invoke("addNote", note=note_params)
        
        if error:
            return False, None, error
        
        if result is None:
            return False, None, "添加笔记失败"
        
        return True, result, None
    
    def add_note_with_image(
        self,
        note: AnkiNote,
        image: QImage,
        image_field: str = "Front"
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        添加带图片的笔记
        
        Args:
            note: AnkiNote对象
            image: QImage图片
            image_field: 图片要添加到的字段名
            
        Returns:
            Tuple[bool, Optional[int], Optional[str]]: (是否成功, 笔记ID, 错误信息)
        """
        if image.isNull():
            return False, None, "图片为空"
        
        # 转换图片为base64
        base64_data = self._qimage_to_base64(image)
        if not base64_data:
            return False, None, "图片转换失败"
        
        # 生成文件名
        filename = f"screenshot_{int(time.time() * 1000)}.png"
        
        # 更新笔记的图片数据
        note.image_data = base64_data
        note.image_filename = filename
        
        # 构建笔记参数
        note_params = {
            "deckName": note.deck_name,
            "modelName": note.model_name,
            "fields": note.fields,
            "tags": note.tags,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "picture": [{
                "data": base64_data,
                "filename": filename,
                "fields": [image_field],
            }],
        }
        
        result, error = self._invoke("addNote", note=note_params)
        
        if error:
            return False, None, error
        
        if result is None:
            return False, None, "添加笔记失败"
        
        return True, result, None
    
    def format_note_request(self, note: AnkiNote) -> Dict[str, Any]:
        """
        格式化笔记请求（用于测试）
        
        Args:
            note: AnkiNote对象
            
        Returns:
            Dict: 格式化的请求数据
        """
        note_params = {
            "deckName": note.deck_name,
            "modelName": note.model_name,
            "fields": note.fields,
            "tags": note.tags,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
        }
        
        if note.has_image():
            note_params["picture"] = [{
                "data": note.image_data,
                "filename": note.image_filename,
                "fields": list(note.fields.keys()),
            }]
        
        return {
            "action": "addNote",
            "version": self.API_VERSION,
            "params": {"note": note_params},
        }
    
    def create_basic_note(
        self,
        deck_name: str,
        front: str,
        back: str,
        tags: Optional[List[str]] = None
    ) -> AnkiNote:
        """
        创建基本笔记
        
        Args:
            deck_name: 牌组名称
            front: 正面内容
            back: 背面内容
            tags: 标签列表
            
        Returns:
            AnkiNote: 笔记对象
        """
        return AnkiNote(
            deck_name=deck_name,
            model_name="Basic",
            fields={"Front": front, "Back": back},
            tags=tags or [],
        )
    
    def store_media_file(
        self,
        filename: str,
        data: str
    ) -> Tuple[bool, Optional[str]]:
        """
        存储媒体文件到Anki
        
        Args:
            filename: 文件名
            data: base64编码的文件数据
            
        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        result, error = self._invoke(
            "storeMediaFile",
            filename=filename,
            data=data
        )
        
        if error:
            return False, error
        
        return True, None
