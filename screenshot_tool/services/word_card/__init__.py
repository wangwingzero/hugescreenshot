# -*- coding: utf-8 -*-
"""
单词卡工具 - 从 AnkiTrans 项目集成

提供单词查询、发音下载、图片获取等功能
"""

from .utils import (
    check_connection,
    create_deck,
    add_note,
    store_media_file,
    store_media_file_from_path,
    anki_request,
    get_hex_name,
    MEDIA_DIR,
)

from .services import WordCardService

from .importer import ensure_model_exists

from .templates import (
    MODEL_NAME,
    FIELDS,
    IMAGE_MODEL_NAME,
    IMAGE_MODEL_TEMPLATE,
)

__all__ = [
    # utils
    'check_connection',
    'create_deck',
    'add_note',
    'store_media_file',
    'store_media_file_from_path',
    'anki_request',
    'get_hex_name',
    'MEDIA_DIR',
    # services
    'WordCardService',
    # importer
    'ensure_model_exists',
    # templates
    'MODEL_NAME',
    'FIELDS',
    'IMAGE_MODEL_NAME',
    'IMAGE_MODEL_TEMPLATE',
]
