# -*- coding: utf-8 -*-
"""
Anki 卡片模板定义

从 AnkiTrans 集成
"""

# ============================================================
# 虎哥单词卡模板
# ============================================================

MODEL_NAME = "虎哥单词卡"

FIELDS = [
    "单词",
    "音标", 
    "中文释义",
    "单词发音",
    "单词配图",
    "绘本原图",
]

# 卡片1 - 英译中 (看单词猜意思)
CARD1_FRONT = '''
<div id="danci">
<div style='font-family: Arial; font-size: 20px;'>{{绘本原图}}</div>
<div style='font-family: Arial;color:green; font-size: 60px;'>{{单词}}</div>
<div style='font-family: Arial; font-size: 40px;'>{{音标}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{单词发音}}</div>
</div>
'''

CARD1_BACK = '''
<div id="danci">
<div style='font-family: Arial;color:green; font-size: 60px;'>{{中文释义}}</div>
<div style='font-family: Arial; font-size: 40px;'>{{单词}}</div>
<div style='font-family: Arial; font-size: 30px;'>{{音标}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{单词发音}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{单词配图}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{绘本原图}}</div>
</div>
'''

# 卡片2 - 中译英 (看释义猜单词)
CARD2_FRONT = '''
<div id="danci">
<div style='font-family: Arial; font-size: 20px;'>{{单词配图}}</div>
<div style='font-family: Arial;color:green; font-size: 60px;'>{{中文释义}}</div>
</div>
'''

CARD2_BACK = '''
<div id="danci">
<div style='font-family: Arial; font-size: 20px;'>{{绘本原图}}</div>
<div style='font-family: Arial;color:green; font-size: 60px;'>{{单词}}</div>
<div style='font-family: Arial; font-size: 30px;'>{{音标}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{单词发音}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{中文释义}}</div>
<div style='font-family: Arial; font-size: 20px;'>{{单词配图}}</div>
</div>
'''


CSS = '''
.card {
    font-family: arial;
    font-size: 24px;
    color: black;
    background-color: white;
}

#danci, #yinbiao {
    text-align: center;
    font-family: serif;
    font-size: 30px;
}

.back {
    text-align: left;
    line-height: 80%;
}

.back img {
    width: 720px;
}

.example {
    font-size: 20px;
    text-align: left;
    line-height: 95%;
}
'''

# ============================================================
# 虎哥原图模板（纯图片卡片）
# ============================================================

IMAGE_MODEL_NAME = "虎哥原图"

IMAGE_MODEL_TEMPLATE = {
    "modelName": IMAGE_MODEL_NAME,
    "inOrderFields": ["图片"],
    "css": """
.card {
    font-family: arial;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
}
img {
    max-width: 100%;
    max-height: 95vh;
}
""",
    "cardTemplates": [
        {
            "Name": "卡片1",
            "Front": "{{图片}}",
            "Back": "{{图片}}"
        }
    ]
}
