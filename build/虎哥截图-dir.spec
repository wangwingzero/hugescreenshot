# -*- mode: python ; coding: utf-8 -*-
# =====================================================
# 虎哥截图 - PyInstaller 目录模式打包配置（用于安装版）
# =====================================================
"""
PyInstaller 目录模式打包配置

使用方法：
    pyinstaller build/虎哥截图-dir.spec --noconfirm --clean

输出：
    dist/虎哥截图/
    ├── 虎哥截图.exe
    ├── _internal/
    └── resources/

说明：
    目录模式用于创建安装版，支持增量更新
    配合 Inno Setup 生成安装包
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# 版本号
APP_VERSION = "2.11.0"

# 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
# Python 版本目录（公开仓库：代码在根目录；私有仓库：代码在 HuGeScreenshot-python/）
_private_python_root = os.path.join(project_root, 'HuGeScreenshot-python')
python_root = _private_python_root if os.path.isdir(_private_python_root) else project_root

print("=" * 50)
print(f"虎哥截图 v{APP_VERSION} 目录模式打包 (安装版)")
print("=" * 50)

# ========== 收集依赖 ==========
all_datas = []
all_binaries = []
all_hiddenimports = []

# 需要完整收集的包
packages = [
    'rapidocr_openvino',     # OCR 引擎 (OpenVINO 后端)
    'openvino',              # OpenVINO 运行时
    'pyclipper',             # 多边形裁剪
    'shapely',               # 几何计算
    'cv2',                   # OpenCV
    'PySide6',               # GUI 框架
    'mss',                   # 屏幕截图
    'trafilatura',           # 网页转 Markdown
    'bs4',                   # HTML 解析 (规章查询、单词卡片)
    'lxml',                  # XML/HTML 解析器
]

# PySide6 不需要的模块（节省约 300MB）
# 只排除确定不需要的，保留可能需要的
pyside6_excludes = [
    # 浏览器引擎 (~193MB) - 项目没用
    'WebEngine',
    # QML/Quick (~50MB) - 项目用 Widgets，不用 QML
    'QtQuick', 'QtQml', 'qmlls',
    # 3D 渲染 - 不需要
    'Qt3D', 'Qt6Quick3D',
    # 设计器/帮助 - 开发工具，不需要
    'QtDesigner', 'QtHelp',
    # PDF 渲染 - 不需要
    'QtPdf',
    # 图表/数据可视化 - 不需要
    'QtCharts', 'QtDataVisualization',
    # 硬件相关 - 不需要
    'QtBluetooth', 'QtNfc', 'QtSensors', 'QtSerialPort',
    # 位置服务 - 不需要
    'QtPositioning', 'QtLocation',
    # 其他不需要的
    'QtRemoteObjects', 'QtScxml', 'QtStateMachine', 'QtTest',
    # 软件 OpenGL (~20MB) - 有硬件加速就不需要
    'opengl32sw',
]

def should_exclude_pyside6(path):
    """检查是否应该排除 PySide6 文件"""
    path_lower = path.lower()
    for exc in pyside6_excludes:
        if exc.lower() in path_lower:
            return True
    return False

for pkg in packages:
    try:
        datas, binaries, imports = collect_all(pkg)
        
        # 过滤 PySide6 不需要的模块
        if pkg == 'PySide6':
            orig_datas = len(datas)
            orig_binaries = len(binaries)
            datas = [(src, dst) for src, dst in datas if not should_exclude_pyside6(src)]
            binaries = [(src, dst) for src, dst in binaries if not should_exclude_pyside6(src)]
            print(f"[OK] {pkg}: {len(datas)} 数据 (过滤 {orig_datas - len(datas)}), {len(binaries)} 二进制 (过滤 {orig_binaries - len(binaries)})")
        else:
            print(f"[OK] {pkg}: {len(datas)} 数据, {len(binaries)} 二进制")
        
        all_datas.extend(datas)
        all_binaries.extend(binaries)
        all_hiddenimports.extend(imports)
    except Exception as e:
        print(f"[跳过] {pkg}: {e}")

# 图标
icon_path = os.path.join(project_root, 'resources', '虎哥截图.ico')
if os.path.exists(icon_path):
    all_datas.append((icon_path, 'resources'))
    print(f"[OK] 图标: {icon_path}")
else:
    icon_path = None
    print("[警告] 图标文件不存在")

# 隐藏导入
all_hiddenimports.extend([
    # OCR - OpenVINO 后端
    'rapidocr_openvino',
    'openvino',
    'openvino.runtime',
    'openvino.runtime.opset13',
    
    # GUI
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui', 
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    
    # 图像
    'cv2',
    'mss', 'mss.windows',
    
    # 数值
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.core.multiarray',
    
    # 其他
    'yaml',
    'requests',
    'urllib3',
    
    # HTML 解析
    'bs4',
    'lxml',
    
    # 项目模块 - core
    'screenshot_tool',
    'screenshot_tool.core',
    'screenshot_tool.core.config_manager',
    'screenshot_tool.core.screenshot_manager',
    'screenshot_tool.core.file_manager',
    'screenshot_tool.core.highlight_editor',
    'screenshot_tool.core.paint_engine',
    'screenshot_tool.core.cursor_manager',
    'screenshot_tool.core.toolbar_manager',
    'screenshot_tool.core.spatial_index',
    'screenshot_tool.core.idle_detector',
    'screenshot_tool.core.image_cache',
    'screenshot_tool.core.async_logger',
    'screenshot_tool.core.anki_debug_logger',
    'screenshot_tool.core.autostart_manager',
    'screenshot_tool.core.background_ocr_manager',
    'screenshot_tool.core.auto_ocr_popup_manager',
    'screenshot_tool.core.smart_layout_manager',
    'screenshot_tool.core.screen_space_detector',
    'screenshot_tool.core.error_logger',
    'screenshot_tool.core.crash_handler',
    'screenshot_tool.core.gongwen_mode_manager',
    'screenshot_tool.core.window_detector',
    'screenshot_tool.core.modal_dialog_detector',
    'screenshot_tool.core.clipboard_history_manager',
    
    # 项目模块 - services
    'screenshot_tool.services',
    'screenshot_tool.services.ocr_service',
    'screenshot_tool.services.ocr_manager',
    'screenshot_tool.services.rapid_ocr_service',
    'screenshot_tool.services.image_preprocessor',
    'screenshot_tool.services.backend_selector',
    'screenshot_tool.services.openvino_optimizer',
    'screenshot_tool.services.baidu_ocr_service',
    'screenshot_tool.services.tencent_ocr_service',
    'screenshot_tool.services.translation_service',
    'screenshot_tool.services.enhanced_translation_service',
    'screenshot_tool.services.anki_connector',
    'screenshot_tool.services.anki_service',
    'screenshot_tool.services.image_stitcher',
    'screenshot_tool.services.markdown_converter',
    'screenshot_tool.services.browser_fetcher',
    'screenshot_tool.services.background_anki_importer',
    'screenshot_tool.services.gongwen_formatter',
    'screenshot_tool.services.doc_auditor',
    'screenshot_tool.services.regulation_service',
    'screenshot_tool.services.update_service',
    'screenshot_tool.services.manifest_service',
    'screenshot_tool.services.delta_updater',
    'screenshot_tool.services.mineru_service',
    'screenshot_tool.services.screen_recorder',
    
    # 项目模块 - core (Markdown 模式)
    'screenshot_tool.core.markdown_mode_manager',
    
    # 网页转 Markdown
    'trafilatura',
    'courlan',
    'htmldate',
    'justext',
    
    # 项目模块 - ui
    'screenshot_tool.ui',
    'screenshot_tool.ui.styles',
    'screenshot_tool.ui.components',
    'screenshot_tool.ui.screenshot_canvas',
    'screenshot_tool.ui.overlay_screenshot',
    'screenshot_tool.ui.ding_window',
    'screenshot_tool.ui.ocr_result_window',
    'screenshot_tool.ui.screen_translator',
    'screenshot_tool.ui.anki_card_window',
    'screenshot_tool.ui.dialogs',
    'screenshot_tool.ui.zoomable_preview',
    'screenshot_tool.ui.crash_dialog',
    'screenshot_tool.ui.batch_url_dialog',
    'screenshot_tool.ui.cursor_overlay',
    'screenshot_tool.ui.regulation_search_window',
    'screenshot_tool.ui.clipboard_history_window',
    'screenshot_tool.ui.main_window',
    'screenshot_tool.ui.mini_toolbar',
    'screenshot_tool.ui.mouse_highlight_overlay',
    'screenshot_tool.ui.scheduled_shutdown_dialog',
    'screenshot_tool.ui.recording_overlay',
    'screenshot_tool.ui.recording_preview',
    'screenshot_tool.ui.login_dialog',
    'screenshot_tool.ui.payment_dialog',
    'screenshot_tool.ui.upgrade_prompt',
    'screenshot_tool.ui.device_manager_dialog',
    'screenshot_tool.ui.sponsor_dialog',
    'screenshot_tool.ui.web_to_markdown_dialog',
    'screenshot_tool.ui.file_to_markdown_dialog',
    'screenshot_tool.ui.gongwen_dialog',
    'screenshot_tool.ui.download_progress_window',
    'screenshot_tool.ui.help_texts',
    
    # 鼠标高亮效果
    'screenshot_tool.ui.effects',
    'screenshot_tool.ui.effects.base_effect',
    'screenshot_tool.ui.effects.circle_effect',
    'screenshot_tool.ui.effects.spotlight_effect',
    'screenshot_tool.ui.effects.cursor_magnify_effect',
    'screenshot_tool.ui.effects.click_ripple_effect',
    
    # 鼠标高亮核心
    'screenshot_tool.core.mouse_highlight_manager',
    'screenshot_tool.core.mouse_event_listener',
    'screenshot_tool.core.topmost_window_manager',
    
    # 订阅系统
    'screenshot_tool.services.subscription',
    'screenshot_tool.services.subscription.manager',
    'screenshot_tool.services.subscription.auth_service',
    'screenshot_tool.services.subscription.license_service',
    'screenshot_tool.services.subscription.payment_service',
    'screenshot_tool.services.subscription.feature_gate',
    'screenshot_tool.services.subscription.usage_tracker',
    'screenshot_tool.services.subscription.models',
    'screenshot_tool.services.subscription.exceptions',
    'screenshot_tool.services.subscription.integration',
    
    # 遗漏的 core 模块
    'screenshot_tool.core.annotation_renderer',
    'screenshot_tool.core.screenshot_state_manager',
    'screenshot_tool.core.device_manager',
    
    # 遗漏的 services 模块
    'screenshot_tool.services.markdown_parser',
    'screenshot_tool.services.word_card',
    'screenshot_tool.services.word_card.importer',
    'screenshot_tool.services.word_card.services',
    'screenshot_tool.services.word_card.templates',
    'screenshot_tool.services.word_card.utils',
    
    # 订阅系统依赖
    'supabase',
    'gotrue',
    'postgrest',
    'realtime',
    'storage3',
    'supafunc',
    'httpx',
    
    # 二维码生成
    'qrcode',
    'qrcode.main',
    'qrcode.image.pil',
    
    # COM 自动化（公文格式化）
    'comtypes',
    'comtypes.client',
    'comtypes.automation',
    'pythoncom',
    
    # 图像处理
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    
    # 文档生成（CCAR 规章导出）
    'docx',
    'docx.shared',
    'docx.enum.text',
])

# 排除项（减小体积）
excludes = [
    # 测试
    'pytest', 'hypothesis', 'pytest-qt', '_pytest',
    # 不需要的 GUI
    'tkinter', '_tkinter', 'tcl', 'tk',
    # 科学计算
    'matplotlib', 'scipy', 'pandas',
    # 开发工具
    'IPython', 'jupyter', 'notebook', 'sphinx',
    # 旧 OCR
    'paddle', 'paddleocr', 'paddlex',
    # ONNX Runtime 相关（不再使用）
    'rapidocr_onnxruntime',
    'onnxruntime',
    # 其他
    'setuptools', 'pkg_resources',
    # PySide6 不需要的模块（节省约 250MB）
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQml',
    'PySide6.QtDesigner',
    'PySide6.QtHelp',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DAnimation',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtLocation',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtStateMachine',
    'PySide6.QtTest',
    'PySide6.QtSql',
    'PySide6.QtXml',
    # 注意：QtMultimedia 和 QtMultimediaWidgets 被录屏预览使用，不能排除
]

print("=" * 50)

# ========== 分析 ==========
a = Analysis(
    [os.path.join(python_root, 'main.pyw')],
    pathex=[project_root, python_root],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# ========== 过滤不需要的 PySide6 模块 ==========
# PyInstaller hook 会自动添加依赖，需要在 Analysis 后再次过滤
pyside6_file_excludes = [
    # WebEngine (~193MB)
    'webengine', 'WebEngine',
    # QML/Quick (~50MB) - 注意 Qt6 前缀
    'qtquick', 'QtQuick', 'Qt6Quick', 'qt6quick',
    'qml', 'Qml', 'Qt6Qml', 'qt6qml', 'qmlls',
    # 3D (~15MB) - 注意 Qt63D 格式
    'qt3d', 'Qt3D', 'Qt63D', 'qt63d',
    'quick3d', 'Quick3D',
    # Designer/Help
    'designer', 'Designer', 'Qt6Designer', 'qt6designer',
    'qthelp', 'QtHelp', 'Qt6Help', 'qt6help',
    # PDF
    'qtpdf', 'QtPdf', 'Qt6Pdf', 'qt6pdf',
    # Charts/DataVis
    'qtcharts', 'QtCharts', 'Qt6Charts', 'qt6charts',
    'datavisualization', 'DataVisualization',
    # Hardware
    'bluetooth', 'Bluetooth', 'nfc', 'Nfc', 
    'sensors', 'Sensors', 'serialport', 'SerialPort',
    # Location
    'positioning', 'Positioning', 'location', 'Location',
    # Other
    'remoteobjects', 'RemoteObjects', 'scxml', 'Scxml', 
    'statemachine', 'StateMachine', 'qttest', 'QtTest',
    # Software OpenGL (~20MB)
    'opengl32sw',
    # ShaderTools (Quick 依赖)
    'shadertools', 'ShaderTools', 'Qt6ShaderTools',
]

def should_exclude_file(name):
    """检查文件是否应该被排除"""
    name_lower = name.lower()
    for exc in pyside6_file_excludes:
        if exc.lower() in name_lower:
            return True
    return False

# 过滤 binaries
orig_binaries = len(a.binaries)
a.binaries = [b for b in a.binaries if not should_exclude_file(b[0])]
print(f"[过滤] binaries: {orig_binaries} -> {len(a.binaries)} (移除 {orig_binaries - len(a.binaries)})")

# 过滤 datas
orig_datas = len(a.datas)
a.datas = [d for d in a.datas if not should_exclude_file(d[0])]
print(f"[过滤] datas: {orig_datas} -> {len(a.datas)} (移除 {orig_datas - len(a.datas)})")

pyz = PYZ(a.pure)

# ========== Manifest 文件（解决 PCA 服务锁定问题）==========
manifest_path = os.path.join(project_root, 'build', 'app.manifest')
if os.path.exists(manifest_path):
    print(f"[OK] Manifest: {manifest_path}")
else:
    manifest_path = None
    print("[警告] Manifest 文件不存在")

# ========== 目录模式 EXE ==========
exe = EXE(
    pyz,
    a.scripts,
    [],  # 目录模式：不包含 binaries 和 datas
    exclude_binaries=True,
    name='虎哥截图',  # 中文名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    manifest=manifest_path,
)

# ========== 收集所有文件到目录 ==========
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='虎哥截图',  # 输出目录名
)
