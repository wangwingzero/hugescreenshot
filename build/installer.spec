# -*- mode: python ; coding: utf-8 -*-
"""
虎哥截图 - 安装器打包配置

打包命令：
    pyinstaller build/installer.spec --noconfirm --clean

输出：
    dist/HuGeScreenshot-{版本号}-Setup.exe
"""

import os
import sys
from pathlib import Path

# 版本号
APP_VERSION = "2.11.0"

# 路径
BUILD_DIR = Path(SPECPATH)
PROJECT_ROOT = BUILD_DIR.parent
DIST_APP_DIR = PROJECT_ROOT / "dist" / "虎哥截图"

block_cipher = None

# 收集应用数据
app_data_files = []
if DIST_APP_DIR.exists():
    for file_path in DIST_APP_DIR.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(DIST_APP_DIR)
            dest_dir = str(Path("app_data") / rel_path.parent)
            app_data_files.append((str(file_path), dest_dir))

# 添加配置文件
config_content = f'{{"version": "{APP_VERSION}"}}'
config_path = BUILD_DIR / "installer_config.json"
with open(config_path, 'w', encoding='utf-8') as f:
    f.write(config_content)
app_data_files.append((str(config_path), '.'))

# 添加 Logo 和图标资源
logo_path = PROJECT_ROOT / "resources" / "PNG" / "虎哥截图.png"
icon_path = PROJECT_ROOT / "resources" / "PNG" / "虎哥截图.ico"
if logo_path.exists():
    app_data_files.append((str(logo_path), '.'))
if icon_path.exists():
    app_data_files.append((str(icon_path), '.'))

a = Analysis(
    [str(BUILD_DIR / 'installer_ui.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=app_data_files,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'rapidocr',
        'openvino',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'HuGeScreenshot-{APP_VERSION}-Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'resources' / 'PNG' / '虎哥截图.ico'),
    version_info=None,
    uac_admin=False,
)
