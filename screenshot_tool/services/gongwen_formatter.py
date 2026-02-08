# =====================================================
# =============== 公文格式化服务 ===============
# =====================================================

"""
GongwenFormatter - Word 公文格式化服务

通过 COM 自动化将 Word 文档格式化为 GB/T 9704-2012 公文格式

功能：
- 连接运行中的 Word 实例
- 智能识别文档结构（标题、主送机关、正文、落款等）
- 应用完整的公文格式（页面、字体、段落、页码）

格式规范要点：
- 页面：A4纸，上边距37mm，下边距35mm，左边距28mm，右边距26mm
- 行间距：固定值28磅（可调整范围26-30磅）
- 标题：2号小标宋体字，空两行居中，使用梯形或菱形排列
- 正文：3号仿宋体字，结构层次用"一、""（一）""1.""（1）"
  - 第一层用3号黑体字
  - 第二层用3号楷体字
  - 第三层及以下用3号仿宋体字
  - 标题只有两层时，可以使用"一、""1."
- 落款和日期：
  - 不加盖印章：正文下空1行编排发文机关署名，署名下1行编排成文日期
  - 加盖印章：正文下空3行编排发文机关署名，日期右空四字
- 附注：3号仿宋体，居左空2字用括号括起来
- 附件："附件"二字及序号用3号黑体顶格
- 抄送机关：4号仿宋体，左右各空1字，每行末尾均标句号
- 印发机关和日期：4号仿宋体，后加"印发"二字
- 页码：4号半角宋体阿拉伯数字，数字左右各一条横线

Requirements: 3.1, 3.2, 3.3, 4.1-4.5, 5.1-5.3
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any
from enum import Enum
import re

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as debug_log
except ImportError:
    def debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")

# 尝试导入 win32com
try:
    import win32com.client
    import pythoncom
    WIN32COM_AVAILABLE = True
except ImportError:
    WIN32COM_AVAILABLE = False


class FormatResult(Enum):
    """格式化结果类型"""
    SUCCESS = "success"                 # 格式化成功
    WORD_NOT_FOUND = "word_not_found"   # 未找到 Word
    COM_ERROR = "com_error"             # COM 连接错误
    FORMAT_ERROR = "format_error"       # 格式化执行错误
    NO_DOCUMENT = "no_document"         # 没有打开的文档


@dataclass
class GongwenFormatResult:
    """公文格式化结果"""
    success: bool               # 是否成功
    result: FormatResult        # 结果类型
    message: str                # 用户友好的消息


@dataclass
class DocumentInfo:
    """打开的文档信息
    
    用于对话框显示文档列表。
    
    Feature: gongwen-dialog
    """
    name: str                   # 文档名称（如 "文档1.docx"）
    full_path: str = ""         # 完整路径（如果有）
    app_type: str = "word"      # 应用类型 ("word" 或 "wps")


@dataclass
class DocumentStructure:
    """文档结构识别结果"""
    title_index: int = -1                           # 标题段落索引
    recipient_index: int = -1                       # 主送机关段落索引
    body_start_index: int = -1                      # 正文起始索引
    body_end_index: int = -1                        # 正文结束索引
    signature_index: int = -1                       # 落款段落索引
    date_index: int = -1                            # 日期段落索引
    
    # 结构层次序数段落索引
    level1_indices: List[int] = field(default_factory=list)  # 一、
    level2_indices: List[int] = field(default_factory=list)  # (一)
    level3_indices: List[int] = field(default_factory=list)  # 1.
    level4_indices: List[int] = field(default_factory=list)  # (1)
    
    # 小标题段落索引（如"背景"、"基本原理"等短标题）
    subtitle_indices: List[int] = field(default_factory=list)


class GongwenConstants:
    """GB/T 9704-2012 公文格式常量
    
    根据最新公文处理主要格式规范更新
    """
    
    # 纸张尺寸 (mm)
    PAGE_WIDTH_MM = 210
    PAGE_HEIGHT_MM = 297
    
    # 页边距 (mm) - GB/T 9704-2012 标准
    MARGIN_TOP_MM = 37      # 上边距 3.7cm
    MARGIN_BOTTOM_MM = 35   # 下边距 3.5cm
    MARGIN_LEFT_MM = 28     # 左边距 2.8cm（订口）
    MARGIN_RIGHT_MM = 26    # 右边距 2.6cm
    
    # 版心尺寸 (mm)
    TEXT_WIDTH_MM = 156
    TEXT_HEIGHT_MM = 225
    
    # 行数和字数
    LINES_PER_PAGE = 22
    CHARS_PER_LINE = 28
    
    # 行间距 (pt) - 固定值28磅，可调整范围26-30磅
    LINE_SPACING_DEFAULT = 28   # 默认行间距
    LINE_SPACING_MIN = 26       # 最小行间距
    LINE_SPACING_MAX = 30       # 最大行间距
    
    # 字体字号 (pt)
    FONT_SIZE_2HAO = 22     # 2号字（标题）
    FONT_SIZE_3HAO = 16     # 3号字（正文）
    FONT_SIZE_4HAO = 14     # 4号字（版记、页码、抄送机关、印发机关）
    
    # 字体名称
    FONT_FANGSONG = "仿宋_GB2312"     # 正文（推荐使用仿宋_GB2312）
    FONT_XIAOBIAOSONG = "小标宋"     # 标题（如无则用黑体）
    FONT_HEITI = "黑体"              # 一级标题序号、密级等、附件标题
    FONT_KAITI = "楷体"              # 二级标题序号、签发人姓名
    FONT_SONGTI = "宋体"             # 页码（4号半角宋体）
    
    # 页码格式
    PAGE_NUM_MARGIN_MM = 7  # 页码距版心下边缘
    
    # 落款和日期格式
    # 不加盖印章：正文下空1行编排发文机关署名
    # 加盖印章：正文下空3行编排发文机关署名，日期右空四字
    SIGNATURE_SPACE_NO_SEAL = 1     # 不加盖印章时，正文下空行数
    SIGNATURE_SPACE_WITH_SEAL = 3   # 加盖印章时，正文下空行数
    DATE_RIGHT_INDENT_CHARS = 4     # 日期右空字数
    
    # 附注格式
    ANNOTATION_LEFT_INDENT_CHARS = 2  # 附注居左空字数
    
    # 抄送机关格式
    COPY_TO_LEFT_RIGHT_SPACE = 1    # 抄送机关左右各空字数
    
    # 单位转换常量
    POINTS_PER_MM = 72 / 25.4  # 1mm ≈ 2.835 points
    CHAR_WIDTH_3HAO = 16       # 3号字一个汉字宽度（pt）
    
    # 支持的文字处理软件窗口类名
    # Microsoft Word: "OpusApp" (Word 2016/2019/2021/365)
    # WPS Office: "KSOMAIN" (WPS 文字主窗口)
    SUPPORTED_WORD_CLASSES = {"OpusApp", "KSOMAIN"}
    
    # COM 应用程序名称（按优先级排序）
    # 先尝试 Microsoft Word，再尝试 WPS
    COM_APP_NAMES = ["Word.Application", "Kwps.Application", "KET.Application"]


class GongwenFormatter:
    """公文格式化服务 - 通过 COM 自动化格式化 Word/WPS 文档
    
    完整实现 GB/T 9704-2012 公文格式标准
    支持 Microsoft Word 和 WPS Office
    
    Requirements: 3.1, 3.2, 3.3, 4.1-4.5, 5.1-5.3
    """
    
    # 结构层次序数正则表达式
    LEVEL1_PATTERN = re.compile(r'^[一二三四五六七八九十]+、')
    LEVEL2_PATTERN = re.compile(r'^\([一二三四五六七八九十]+\)')
    LEVEL3_PATTERN = re.compile(r'^\d+\.')
    LEVEL4_PATTERN = re.compile(r'^\(\d+\)')
    
    # 日期正则表达式
    DATE_PATTERN = re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日$')
    
    # 支持的文字处理软件窗口类名
    SUPPORTED_WORD_CLASSES = GongwenConstants.SUPPORTED_WORD_CLASSES
    
    def __init__(self):
        """初始化格式化服务"""
        self._word_app: Optional[Any] = None
        self._app_type: Optional[str] = None  # 记录当前连接的应用类型
    
    def format_active_document(self) -> GongwenFormatResult:
        """格式化当前活动的 Word/WPS 文档
        
        Returns:
            GongwenFormatResult 格式化结果
            
        Requirements: 3.1, 3.2, 5.1, 5.2, 5.3
        """
        # 检查 win32com 是否可用
        if not WIN32COM_AVAILABLE:
            return GongwenFormatResult(
                success=False,
                result=FormatResult.COM_ERROR,
                message="未安装 pywin32，无法连接 Word/WPS"
            )
        
        # 连接 Word 或 WPS
        word_app = self._connect_word()
        if word_app is None:
            return GongwenFormatResult(
                success=False,
                result=FormatResult.WORD_NOT_FOUND,
                message="未找到运行中的 Word 或 WPS，请先打开文档"
            )
        
        try:
            # 获取活动文档
            doc = word_app.ActiveDocument
            if doc is None:
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.NO_DOCUMENT,
                    message="Word/WPS 中没有打开的文档"
                )
            
            # 执行格式化
            self._format_document(doc)
            
            return GongwenFormatResult(
                success=True,
                result=FormatResult.SUCCESS,
                message="公文格式化完成"
            )
            
        except Exception as e:
            debug_log(f"格式化失败: {e}", "GONGWEN")
            return GongwenFormatResult(
                success=False,
                result=FormatResult.FORMAT_ERROR,
                message=f"格式化失败: {str(e)}"
            )
        finally:
            # 确保 COM 资源被清理
            self._cleanup_com()
    
    def format_document_by_hwnd(self, hwnd: int, cancel_flag=None) -> GongwenFormatResult:
        """通过窗口句柄格式化 Word/WPS 文档
        
        通过窗口句柄找到对应的 Word/WPS 实例，获取其活动文档并格式化。
        
        Args:
            hwnd: Word/WPS 窗口句柄（主窗口或子窗口）
            cancel_flag: 可选的取消标志（threading.Event），用于中止格式化
            
        Returns:
            GongwenFormatResult 格式化结果
            
        Requirements: 4.1, 4.2
        """
        debug_log(f"format_document_by_hwnd 被调用, hwnd={hwnd}", "GONGWEN")
        
        # 检查 win32com 是否可用
        if not WIN32COM_AVAILABLE:
            debug_log("win32com 不可用", "GONGWEN")
            return GongwenFormatResult(
                success=False,
                result=FormatResult.COM_ERROR,
                message="未安装 pywin32，无法连接 Word/WPS"
            )
        
        if hwnd == 0:
            debug_log("无效的窗口句柄 (hwnd=0)", "GONGWEN")
            return GongwenFormatResult(
                success=False,
                result=FormatResult.WORD_NOT_FOUND,
                message="无效的窗口句柄"
            )
        
        try:
            # 初始化 COM
            debug_log("初始化 COM", "GONGWEN")
            pythoncom.CoInitialize()
            
            # 检查取消
            if cancel_flag and cancel_flag.is_set():
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message="格式化已取消"
                )
            
            # 检测窗口类型（Word 还是 WPS）
            app_type = self._detect_app_type(hwnd)
            debug_log(f"检测到应用类型: {app_type}", "GONGWEN")
            
            # 获取主窗口句柄
            debug_log(f"获取主窗口句柄, 输入 hwnd={hwnd}", "GONGWEN")
            word_hwnd = self._get_word_main_hwnd(hwnd)
            debug_log(f"主窗口句柄: {word_hwnd}", "GONGWEN")
            
            if word_hwnd == 0:
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.WORD_NOT_FOUND,
                    message="未找到 Word/WPS 主窗口"
                )
            
            # 通过 hwnd 获取 Application（仅对 Microsoft Word 有效）
            word_app = None
            if app_type == "word":
                debug_log("尝试通过 hwnd 获取 Word Application", "GONGWEN")
                word_app = self._get_word_app_from_hwnd(word_hwnd)
            
            if word_app is None:
                # 降级：尝试获取任意运行中的 Word/WPS 实例
                debug_log("通过 hwnd 获取失败，尝试降级获取运行中的实例", "GONGWEN")
                word_app = self._connect_word(prefer_type=app_type)
                if word_app is None:
                    return GongwenFormatResult(
                        success=False,
                        result=FormatResult.WORD_NOT_FOUND,
                        message="无法连接到 Word/WPS 应用程序"
                    )
            
            self._word_app = word_app
            debug_log(f"成功获取应用程序实例 (类型: {self._app_type})", "GONGWEN")
            
            # 获取活动文档
            doc = word_app.ActiveDocument
            if doc is None:
                debug_log("没有打开的文档", "GONGWEN")
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.NO_DOCUMENT,
                    message="Word/WPS 中没有打开的文档"
                )
            
            doc_name = doc.Name
            debug_log(f"获取到活动文档: {doc_name}", "GONGWEN")
            
            # 执行格式化
            debug_log("开始执行格式化", "GONGWEN")
            self._format_document(doc, cancel_flag=cancel_flag)
            
            # 检查是否被取消
            if cancel_flag and cancel_flag.is_set():
                debug_log("格式化被用户取消", "GONGWEN")
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message="格式化已取消"
                )
            
            debug_log("格式化成功完成", "GONGWEN")
            return GongwenFormatResult(
                success=True,
                result=FormatResult.SUCCESS,
                message="公文格式化完成"
            )
            
        except Exception as e:
            debug_log(f"通过 hwnd 格式化失败: {e}", "GONGWEN")
            import traceback
            debug_log(f"异常堆栈: {traceback.format_exc()}", "GONGWEN")
            return GongwenFormatResult(
                success=False,
                result=FormatResult.FORMAT_ERROR,
                message=f"格式化失败: {str(e)}"
            )
        finally:
            self._cleanup_com()
    
    def _detect_app_type(self, hwnd: int) -> str:
        """检测窗口所属的应用类型
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            "word" 表示 Microsoft Word，"wps" 表示 WPS Office，"unknown" 表示未知
        """
        try:
            import win32gui
            
            # 检查当前窗口和父窗口链
            current = hwnd
            visited = set()
            
            while current and current not in visited:
                visited.add(current)
                try:
                    class_name = win32gui.GetClassName(current)
                    if class_name == "OpusApp":
                        return "word"
                    elif class_name == "KSOMAIN":
                        return "wps"
                    current = win32gui.GetParent(current)
                except Exception:
                    break
            
            return "unknown"
        except Exception as e:
            debug_log(f"检测应用类型失败: {e}", "GONGWEN")
            return "unknown"
    
    def _get_word_main_hwnd(self, hwnd: int) -> int:
        """获取 Word/WPS 主窗口句柄
        
        从给定的窗口句柄向上遍历，找到支持的主窗口类名。
        Microsoft Word: "OpusApp"
        WPS Office: "KSOMAIN"
        
        Args:
            hwnd: 任意窗口句柄
            
        Returns:
            主窗口句柄，如果未找到返回 0
        """
        try:
            import win32gui
            
            # 检查当前窗口
            class_name = win32gui.GetClassName(hwnd)
            if class_name in self.SUPPORTED_WORD_CLASSES:
                return hwnd
            
            # 向上遍历父窗口
            parent = win32gui.GetParent(hwnd)
            while parent:
                try:
                    if win32gui.GetClassName(parent) in self.SUPPORTED_WORD_CLASSES:
                        return parent
                    parent = win32gui.GetParent(parent)
                except Exception:
                    break
            
            return 0
        except Exception as e:
            debug_log(f"获取主窗口失败: {e}", "GONGWEN")
            return 0
    
    def _get_word_app_from_hwnd(self, hwnd: int) -> Optional[Any]:
        """通过窗口句柄获取 Word Application COM 对象
        
        使用 AccessibleObjectFromWindow API 从窗口句柄获取 COM 对象。
        
        Args:
            hwnd: Word 主窗口句柄
            
        Returns:
            Word.Application COM 对象，如果失败返回 None
        """
        try:
            import win32gui
            import ctypes
            from ctypes import wintypes, byref, POINTER
            from comtypes import GUID
            from comtypes.automation import IDispatch
            import comtypes.client
            
            # 定义 GUID
            IID_IDispatch = GUID("{00020400-0000-0000-C000-000000000046}")
            OBJID_NATIVEOM = -16  # 0xFFFFFFF0
            
            # 加载 oleacc.dll
            oleacc = ctypes.windll.oleacc
            
            # 查找 Word 文档窗口 (_WwG 类)
            def find_wwg_window(parent_hwnd):
                """递归查找 _WwG 类窗口"""
                result = [None]
                
                def enum_callback(hwnd, _):
                    try:
                        class_name = win32gui.GetClassName(hwnd)
                        if class_name == "_WwG":
                            result[0] = hwnd
                            return False  # 停止枚举
                    except Exception:
                        pass
                    return True
                
                try:
                    win32gui.EnumChildWindows(parent_hwnd, enum_callback, None)
                except Exception:
                    pass
                
                return result[0]
            
            wwg_hwnd = find_wwg_window(hwnd)
            if wwg_hwnd is None:
                debug_log("未找到 _WwG 窗口", "GONGWEN")
                return None
            
            # 使用 AccessibleObjectFromWindow 获取 IDispatch
            disp = POINTER(IDispatch)()
            hr = oleacc.AccessibleObjectFromWindow(
                wwg_hwnd,
                OBJID_NATIVEOM,
                byref(IID_IDispatch),
                byref(disp)
            )
            
            if hr != 0 or not disp:
                debug_log(f"AccessibleObjectFromWindow 失败: hr={hr}", "GONGWEN")
                return None
            
            # 获取 Window 对象，然后获取 Application
            window = comtypes.client.GetBestInterface(disp)
            word_app = window.Application
            
            debug_log("成功通过 hwnd 获取 Word Application", "GONGWEN")
            return word_app
            
        except ImportError as e:
            debug_log(f"缺少 comtypes 库: {e}", "GONGWEN")
            return None
        except Exception as e:
            debug_log(f"通过 hwnd 获取 Word Application 失败: {e}", "GONGWEN")
            return None

    def _connect_word(self, prefer_type: str = None) -> Optional[Any]:
        """连接到运行中的 Word 或 WPS 实例
        
        Args:
            prefer_type: 优先连接的应用类型 ("word", "wps", None)
                        None 表示按默认顺序尝试
        
        Returns:
            Application COM 对象，如果连接失败返回 None
            
        Requirements: 3.1, 3.3
        """
        try:
            # 初始化 COM（在同一线程中多次调用是安全的）
            pythoncom.CoInitialize()
            
            # 根据优先类型调整尝试顺序
            app_names = list(GongwenConstants.COM_APP_NAMES)
            if prefer_type == "wps":
                # WPS 优先
                app_names = ["Kwps.Application", "KET.Application", "Word.Application"]
            elif prefer_type == "word":
                # Word 优先（默认顺序）
                pass
            
            # 依次尝试连接
            for app_name in app_names:
                try:
                    word_app = win32com.client.GetActiveObject(app_name)
                    self._word_app = word_app
                    self._app_type = "wps" if "wps" in app_name.lower() or "ket" in app_name.lower() else "word"
                    debug_log(f"成功连接到 {app_name}", "GONGWEN")
                    return word_app
                except pythoncom.com_error:
                    debug_log(f"未找到运行中的 {app_name}", "GONGWEN")
                    continue
                except Exception as e:
                    debug_log(f"连接 {app_name} 失败: {e}", "GONGWEN")
                    continue
            
            debug_log("未找到任何运行中的 Word 或 WPS 实例", "GONGWEN")
            return None
            
        except Exception as e:
            debug_log(f"连接失败: {e}", "GONGWEN")
            return None
    
    def _cleanup_com(self) -> None:
        """清理 COM 资源"""
        try:
            self._word_app = None
            self._app_type = None
            pythoncom.CoUninitialize()
        except Exception:
            pass  # 忽略清理时的错误
    
    def _format_document(self, doc, cancel_flag=None) -> None:
        """执行完整的文档格式化
        
        Args:
            doc: Word Document COM 对象
            cancel_flag: 可选的取消标志（threading.Event）
            
        Requirements: 4.1-4.5
        """
        def check_cancel():
            """检查是否被取消"""
            if cancel_flag and cancel_flag.is_set():
                debug_log("格式化被用户取消", "GONGWEN")
                return True
            return False
        
        try:
            # 获取文档信息用于日志
            para_count = doc.Paragraphs.Count
            debug_log(f"开始格式化文档，共 {para_count} 个段落", "GONGWEN")
            
            # 1. 设置页面格式
            debug_log("步骤1: 设置页面格式", "GONGWEN")
            self._setup_page(doc)
            if check_cancel(): return
            
            # 2. 分析文档结构
            debug_log("步骤2: 分析文档结构", "GONGWEN")
            structure = self._analyze_structure(doc, cancel_flag=cancel_flag)
            if check_cancel(): return
            
            # 3. 格式化标题
            debug_log("步骤3: 格式化标题", "GONGWEN")
            if structure.title_index >= 0:
                self._format_title(doc, structure.title_index)
            if check_cancel(): return
            
            # 4. 格式化主送机关
            debug_log("步骤4: 格式化主送机关", "GONGWEN")
            if structure.recipient_index >= 0:
                self._format_recipient(doc, structure.recipient_index)
            if check_cancel(): return
            
            # 5. 格式化正文
            debug_log(f"步骤5: 格式化正文 ({structure.body_start_index}-{structure.body_end_index})", "GONGWEN")
            self._format_body(doc, structure, cancel_flag=cancel_flag)
            if check_cancel(): return
            
            # 6. 格式化结构层次序数
            debug_log("步骤6: 格式化结构层次序数", "GONGWEN")
            self._format_structure_numbers(doc, structure, cancel_flag=cancel_flag)
            if check_cancel(): return
            
            # 7. 格式化落款和日期
            debug_log("步骤7: 格式化落款和日期", "GONGWEN")
            self._format_signature_date(doc, structure)
            if check_cancel(): return
            
            # 8. 设置页码
            debug_log("步骤8: 设置页码", "GONGWEN")
            self._setup_page_numbers(doc)
            
            debug_log("文档格式化完成", "GONGWEN")
        except Exception as e:
            debug_log(f"文档格式化过程中发生异常: {e}", "GONGWEN")
            raise
    
    @staticmethod
    def _mm_to_points(mm: float) -> float:
        """毫米转换为 Word 点数
        
        Args:
            mm: 毫米值
            
        Returns:
            点数值
            
        Requirements: 4.1, 4.2
        """
        return mm * GongwenConstants.POINTS_PER_MM
    
    def _setup_page(self, doc) -> None:
        """设置页面格式 - GB/T 9704-2012 5.2
        
        页面设置：
        - A4 纸张 (210mm × 297mm)
        - 页边距：上 37mm，下 35mm，左 28mm，右 26mm
        - 每页 22 行，每行 28 字（通过版心尺寸和字号自然实现）
        - 行间距：固定值 28 磅
        
        注意：不使用文档网格，通过固定行距控制每页行数
        版心高度 225mm ÷ 22 行 ≈ 10.23mm/行 ≈ 29pt，使用 28pt 行距
        
        Args:
            doc: Word Document COM 对象
            
        Requirements: 4.1, 4.2, 4.4
        """
        try:
            ps = doc.PageSetup
            
            # 纸张 A4
            ps.PageWidth = self._mm_to_points(GongwenConstants.PAGE_WIDTH_MM)
            ps.PageHeight = self._mm_to_points(GongwenConstants.PAGE_HEIGHT_MM)
            
            # 页边距：上3.7cm 下3.5cm 左2.8cm 右2.6cm
            ps.TopMargin = self._mm_to_points(GongwenConstants.MARGIN_TOP_MM)
            ps.BottomMargin = self._mm_to_points(GongwenConstants.MARGIN_BOTTOM_MM)
            ps.LeftMargin = self._mm_to_points(GongwenConstants.MARGIN_LEFT_MM)
            ps.RightMargin = self._mm_to_points(GongwenConstants.MARGIN_RIGHT_MM)
            
            # 禁用文档网格，使用普通模式
            # LayoutMode = 0 表示无网格（普通模式）
            ps.LayoutMode = 0  # wdLayoutModeDefault - 无网格
            
            debug_log("页面设置完成（无网格模式，行间距28磅）", "GONGWEN")
            
        except Exception as e:
            debug_log(f"页面设置失败: {e}", "GONGWEN")
            raise
    
    def _analyze_structure(self, doc, cancel_flag=None) -> DocumentStructure:
        """智能分析文档结构
        
        识别规则：
        1. 标题：第一个非空段落（通常是文档标题）
        2. 主送机关：标题后，以"："或"："结尾且不是小标题的段落
        3. 正文：标题后到落款前的所有段落（包括小标题）
        4. 结构层次序数：正则匹配 "一、" "(一)" "1." "(1)"
        5. 落款和日期：最后几段
        
        Args:
            doc: Word Document COM 对象
            cancel_flag: 可选的取消标志（threading.Event）
            
        Returns:
            DocumentStructure 文档结构
            
        Requirements: 4.3, 4.4
        """
        def check_cancel():
            return cancel_flag and cancel_flag.is_set()
        
        structure = DocumentStructure()
        paragraphs = doc.Paragraphs
        para_count = paragraphs.Count
        
        if para_count == 0:
            return structure
        
        debug_log(f"开始分析文档结构，共 {para_count} 个段落", "GONGWEN")
        
        # 对于大文档，使用简化的分析策略
        # 只分析前50个和后20个段落，中间部分假设为正文
        MAX_HEAD_PARAS = 50  # 分析前50个段落（找标题、主送机关）
        MAX_TAIL_PARAS = 20  # 分析后20个段落（找落款、日期）
        
        # 1. 分析文档头部（找标题）
        debug_log("分析文档头部...", "GONGWEN")
        head_count = min(MAX_HEAD_PARAS, para_count)
        for i in range(1, head_count + 1):
            if check_cancel(): return structure
            try:
                text = paragraphs.Item(i).Range.Text.strip()
                if text and structure.title_index < 0:
                    structure.title_index = i - 1  # 转换为0-based索引
                    debug_log(f"找到标题: 段落 {i}", "GONGWEN")
                    break
            except Exception:
                pass
        
        # 2. 分析文档尾部（找落款和日期）- 优化：限制遍历次数
        debug_log("分析文档尾部...", "GONGWEN")
        tail_start = max(1, para_count - MAX_TAIL_PARAS + 1)
        checked_count = 0
        max_tail_checks = 30  # 最多检查30个段落
        
        for i in range(para_count, tail_start - 1, -1):
            if check_cancel(): return structure
            checked_count += 1
            if checked_count > max_tail_checks:
                break
                
            try:
                text = paragraphs.Item(i).Range.Text.strip()
                if not text:
                    continue
                
                # 检查是否为日期（从后往前找第一个日期）
                if structure.date_index < 0 and self.DATE_PATTERN.match(text):
                    structure.date_index = i - 1  # 转换为0-based索引
                    debug_log(f"找到日期: 段落 {i}", "GONGWEN")
                # 日期前一段可能是落款
                elif structure.date_index >= 0 and structure.signature_index < 0:
                    if (i - 1) == structure.date_index - 1:
                        structure.signature_index = i - 1
                        debug_log(f"找到落款: 段落 {i}", "GONGWEN")
                        break
            except Exception:
                pass
        
        # 3. 确定正文范围
        start_idx = structure.title_index + 1 if structure.title_index >= 0 else 0
        end_idx = structure.signature_index if structure.signature_index >= 0 else para_count
        
        if start_idx < end_idx:
            structure.body_start_index = start_idx
            structure.body_end_index = end_idx
        
        # 4. 对于大文档，跳过结构层次序数和小标题的识别
        if para_count > 500:
            debug_log(f"大文档模式: 跳过结构层次序数识别 (段落数={para_count})", "GONGWEN")
        else:
            # 小文档：识别结构层次序数和小标题
            debug_log("分析结构层次序数...", "GONGWEN")
            for i in range(structure.body_start_index, structure.body_end_index):
                if check_cancel(): return structure
                try:
                    text = paragraphs.Item(i + 1).Range.Text.strip()
                    if not text:
                        continue
                    
                    if self.LEVEL1_PATTERN.match(text):
                        structure.level1_indices.append(i)
                    elif self.LEVEL2_PATTERN.match(text):
                        structure.level2_indices.append(i)
                    elif self.LEVEL3_PATTERN.match(text):
                        structure.level3_indices.append(i)
                    elif self.LEVEL4_PATTERN.match(text):
                        structure.level4_indices.append(i)
                    elif self._is_subtitle(text):
                        structure.subtitle_indices.append(i)
                except Exception:
                    pass
        
        debug_log(f"文档结构分析完成: 标题={structure.title_index}, "
                  f"主送={structure.recipient_index}, "
                  f"正文={structure.body_start_index}-{structure.body_end_index}, "
                  f"落款={structure.signature_index}, 日期={structure.date_index}, "
                  f"小标题数={len(structure.subtitle_indices)}", "GONGWEN")
        
        return structure
    
    def _is_subtitle(self, text: str) -> bool:
        """判断是否为小标题
        
        小标题特征：
        1. 长度较短（2-15个字符）
        2. 不以句号等标点结尾
        3. 不是数字开头
        
        Args:
            text: 段落文本
            
        Returns:
            是否为小标题
        """
        if not text:
            return False
        
        # 去掉末尾冒号后判断
        clean_text = text.rstrip('：:')
        
        # 长度限制：2-15个字符
        if len(clean_text) < 2 or len(clean_text) > 15:
            return False
        
        # 不能以数字开头
        if text[0].isdigit():
            return False
        
        # 不能包含句号、逗号等正文标点
        if any(p in text for p in ['。', '，', '；', '！', '？']):
            return False
        
        # 不能以句号等结尾
        if text[-1] in ['。', '，', '；', '！', '？']:
            return False
        
        return True

    def _format_title(self, doc, title_index: int) -> None:
        """格式化标题 - GB/T 9704-2012 7.3.1
        
        2号小标宋体字，空两行居中排布
        标题排列应当使用梯形或菱形，不使用沙漏形和长方形
        
        Args:
            doc: Word Document COM 对象
            title_index: 标题段落索引
            
        Requirements: 4.3
        """
        try:
            para = doc.Paragraphs.Item(title_index + 1)  # Word 索引从 1 开始
            rng = para.Range
            
            # 清除列表格式（项目符号和编号）
            # 这可以防止原文档中的列表格式（如中点·）被保留
            try:
                rng.ListFormat.RemoveNumbers()
            except Exception:
                pass  # 忽略清除失败
            
            # 设置字体 - 优先小标宋，降级到黑体
            font_name = GongwenConstants.FONT_XIAOBIAOSONG
            try:
                rng.Font.Name = font_name
                rng.Font.NameFarEast = font_name
            except Exception:
                # 小标宋不可用，使用黑体
                font_name = GongwenConstants.FONT_HEITI
                rng.Font.Name = font_name
                rng.Font.NameFarEast = font_name
                debug_log("小标宋字体不可用，使用黑体", "GONGWEN")
            
            # 设置字号 - 2号字 (22pt)
            rng.Font.Size = GongwenConstants.FONT_SIZE_2HAO
            
            # 设置颜色 - 黑色
            rng.Font.Color = 0  # wdColorBlack
            
            # 设置居中对齐
            para.Format.Alignment = 1  # wdAlignParagraphCenter
            
            # 取消首行缩进
            para.Format.FirstLineIndent = 0
            
            # 设置标题前空两行（段前间距）
            # 2号字高度约 22pt，空两行约 44pt
            para.Format.SpaceBefore = 44  # 空两行
            
            debug_log(f"标题格式化完成: {font_name} {GongwenConstants.FONT_SIZE_2HAO}pt，空两行居中", "GONGWEN")
            
        except Exception as e:
            debug_log(f"标题格式化失败: {e}", "GONGWEN")
    
    def _format_recipient(self, doc, recipient_index: int) -> None:
        """格式化主送机关 - GB/T 9704-2012 7.3.2
        
        3号仿宋体字，顶格
        
        Args:
            doc: Word Document COM 对象
            recipient_index: 主送机关段落索引
            
        Requirements: 4.3
        """
        try:
            para = doc.Paragraphs.Item(recipient_index + 1)
            rng = para.Range
            
            # 设置字体 - 仿宋
            rng.Font.Name = GongwenConstants.FONT_FANGSONG
            rng.Font.NameFarEast = GongwenConstants.FONT_FANGSONG
            
            # 设置字号 - 3号字 (16pt)
            rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
            
            # 设置颜色 - 黑色
            rng.Font.Color = 0
            
            # 设置左对齐，顶格
            para.Format.Alignment = 0  # wdAlignParagraphLeft
            para.Format.FirstLineIndent = 0
            para.Format.LeftIndent = 0
            
            debug_log("主送机关格式化完成", "GONGWEN")
            
        except Exception as e:
            debug_log(f"主送机关格式化失败: {e}", "GONGWEN")
    
    def _format_body(self, doc, structure: DocumentStructure, cancel_flag=None) -> None:
        """格式化正文 - GB/T 9704-2012 7.3.3
        
        3号仿宋体字，首行缩进2字
        
        对于大文档（>500段落），使用批量操作优化性能。
        
        Args:
            doc: Word Document COM 对象
            structure: 文档结构
            cancel_flag: 可选的取消标志（threading.Event）
            
        Requirements: 4.3, 4.4
        """
        if structure.body_start_index < 0:
            debug_log("正文起始索引无效，跳过正文格式化", "GONGWEN")
            return
        
        try:
            total_paras = structure.body_end_index - structure.body_start_index
            debug_log(f"开始格式化正文，共 {total_paras} 个段落", "GONGWEN")
            
            # 计算首行缩进（2个汉字宽度）
            # 3号字 16pt，2个字符 = 32pt ≈ 11.3mm
            first_line_indent = self._mm_to_points(11.3)  # 2字符 = 32pt
            
            # 对于大文档，使用整个文档范围的批量操作
            if total_paras > 500:
                debug_log("大文档模式: 使用批量格式化", "GONGWEN")
                self._format_body_batch(doc, structure, first_line_indent, cancel_flag=cancel_flag)
            else:
                # 小文档：逐段落格式化
                self._format_body_individual(doc, structure, first_line_indent, cancel_flag=cancel_flag)
            
        except Exception as e:
            debug_log(f"正文格式化失败: {e}", "GONGWEN")
    
    def _format_body_batch(self, doc, structure: DocumentStructure, first_line_indent: float, cancel_flag=None) -> None:
        """批量格式化正文（大文档优化）
        
        使用 Word 的 Range 对象一次性设置整个正文区域的格式，
        而不是逐段落设置，大幅提升性能。
        
        Args:
            doc: Word Document COM 对象
            structure: 文档结构
            first_line_indent: 首行缩进值（点数）
            cancel_flag: 可选的取消标志（threading.Event）
        """
        try:
            # 边界检查
            para_count = doc.Paragraphs.Count
            start_index = structure.body_start_index + 1  # 转换为1-based
            # body_end_index 是 0-based 的结束索引（不包含），需要限制在有效范围内
            end_index = min(structure.body_end_index, para_count)
            
            if start_index > end_index or start_index < 1 or end_index < 1:
                debug_log(f"正文范围无效: start={start_index}, end={end_index}, total={para_count}", "GONGWEN")
                return
            
            # 确保索引不超出文档范围
            if start_index > para_count:
                debug_log(f"起始索引超出范围: start={start_index}, total={para_count}", "GONGWEN")
                return
            
            # 获取正文范围（从正文开始到正文结束）
            start_para = doc.Paragraphs.Item(start_index)
            end_para = doc.Paragraphs.Item(end_index)
            
            # 创建包含整个正文的 Range
            body_range = doc.Range(start_para.Range.Start, end_para.Range.End)
            
            debug_log(f"批量设置正文字体 (段落 {start_index}-{end_index})...", "GONGWEN")
            
            # 清除列表格式（项目符号和编号）
            # 这可以防止原文档中的列表格式（如中点·）被保留
            try:
                body_range.ListFormat.RemoveNumbers()
                debug_log("已清除正文列表格式", "GONGWEN")
            except Exception as e:
                debug_log(f"清除列表格式失败（可忽略）: {e}", "GONGWEN")
            
            # 批量设置字体
            body_range.Font.Name = GongwenConstants.FONT_FANGSONG
            body_range.Font.NameFarEast = GongwenConstants.FONT_FANGSONG
            body_range.Font.Size = GongwenConstants.FONT_SIZE_3HAO
            body_range.Font.Color = 0  # 黑色
            
            debug_log("批量设置正文段落格式...", "GONGWEN")
            
            # 批量设置段落格式
            body_range.ParagraphFormat.Alignment = 3  # wdAlignParagraphJustify - 两端对齐
            body_range.ParagraphFormat.FirstLineIndent = first_line_indent
            # 固定值行距 28 磅（可调整范围 26-30 磅）
            body_range.ParagraphFormat.LineSpacingRule = 4  # wdLineSpaceExactly - 固定值
            body_range.ParagraphFormat.LineSpacing = GongwenConstants.LINE_SPACING_DEFAULT  # 28磅
            
            debug_log(f"正文批量格式化完成（行间距{GongwenConstants.LINE_SPACING_DEFAULT}磅）", "GONGWEN")
            
        except Exception as e:
            debug_log(f"批量格式化失败: {e}，回退到逐段落模式", "GONGWEN")
            # 如果批量操作失败，回退到逐段落模式（但限制处理数量）
            self._format_body_individual(doc, structure, first_line_indent, max_paras=200, cancel_flag=cancel_flag)
    
    def _format_body_individual(self, doc, structure: DocumentStructure, 
                                 first_line_indent: float, max_paras: int = None,
                                 cancel_flag=None) -> None:
        """逐段落格式化正文
        
        Args:
            doc: Word Document COM 对象
            structure: 文档结构
            first_line_indent: 首行缩进值（点数）
            max_paras: 最大处理段落数（None 表示不限制）
            cancel_flag: 可选的取消标志（threading.Event）
        """
        def check_cancel():
            return cancel_flag and cancel_flag.is_set()
        
        total_paras = structure.body_end_index - structure.body_start_index
        formatted_count = 0
        
        end_index = structure.body_end_index
        if max_paras is not None:
            end_index = min(structure.body_start_index + max_paras, structure.body_end_index)
            debug_log(f"限制处理前 {max_paras} 个段落", "GONGWEN")
        
        for i in range(structure.body_start_index, end_index):
            if check_cancel():
                debug_log(f"正文格式化被取消，已处理 {formatted_count} 个段落", "GONGWEN")
                return
                
            try:
                para = doc.Paragraphs.Item(i + 1)
                rng = para.Range
                text = rng.Text.strip()
                
                if not text:
                    continue
                
                # 清除列表格式（项目符号和编号）
                # 这可以防止原文档中的列表格式（如中点·）被保留
                try:
                    rng.ListFormat.RemoveNumbers()
                except Exception:
                    pass  # 忽略清除失败
                
                # 设置字体 - 仿宋
                rng.Font.Name = GongwenConstants.FONT_FANGSONG
                rng.Font.NameFarEast = GongwenConstants.FONT_FANGSONG
                
                # 设置字号 - 3号字 (16pt)
                rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
                
                # 设置颜色 - 黑色
                rng.Font.Color = 0
                
                # 设置两端对齐
                para.Format.Alignment = 3  # wdAlignParagraphJustify - 两端对齐
                
                # 设置固定值行距 28 磅（可调整范围 26-30 磅）
                para.Format.LineSpacingRule = 4  # wdLineSpaceExactly - 固定值
                para.Format.LineSpacing = GongwenConstants.LINE_SPACING_DEFAULT  # 28磅
                
                # 设置首行缩进（结构层次序数段落和小标题不缩进）
                if (i not in structure.level1_indices and 
                    i not in structure.level2_indices and
                    i not in structure.level3_indices and
                    i not in structure.level4_indices and
                    i not in structure.subtitle_indices):
                    para.Format.FirstLineIndent = first_line_indent
                else:
                    para.Format.FirstLineIndent = 0
                
                formatted_count += 1
                
                # 每100个段落输出一次进度
                if formatted_count % 100 == 0:
                    debug_log(f"正文格式化进度: {formatted_count}/{total_paras}", "GONGWEN")
                
            except Exception as e:
                debug_log(f"段落 {i} 格式化失败: {e}", "GONGWEN")
        
        debug_log(f"正文格式化完成，共处理 {formatted_count} 个段落", "GONGWEN")
    
    def _format_structure_numbers(self, doc, structure: DocumentStructure, cancel_flag=None) -> None:
        """格式化结构层次序数 - GB/T 9704-2012 7.3.3
        
        结构层次用"一、""（一）""1.""（1）"标注
        - 第一层用3号黑体字
        - 第二层用3号楷体字
        - 第三层和第四层用3号仿宋体字
        
        注意：标题只有两层时，可以使用"一、""1."
        
        Args:
            doc: Word Document COM 对象
            structure: 文档结构
            cancel_flag: 可选的取消标志（threading.Event）
            
        Requirements: 4.3
        """
        def check_cancel():
            return cancel_flag and cancel_flag.is_set()
        
        try:
            # 判断是否只有两层结构（一、和 1.）
            has_level2 = len(structure.level2_indices) > 0  # （一）
            has_level4 = len(structure.level4_indices) > 0  # （1）
            only_two_levels = not has_level2 and not has_level4
            
            if only_two_levels:
                debug_log("检测到只有两层结构，使用 一、/1. 格式", "GONGWEN")
            
            # 一级序号用黑体（一、）
            for idx in structure.level1_indices:
                if check_cancel():
                    debug_log("结构层次序数格式化被取消", "GONGWEN")
                    return
                self._format_sequence_number(doc, idx, self.LEVEL1_PATTERN, 
                                            GongwenConstants.FONT_HEITI)
            
            # 二级序号用楷体（（一））
            for idx in structure.level2_indices:
                if check_cancel():
                    return
                self._format_sequence_number(doc, idx, self.LEVEL2_PATTERN,
                                            GongwenConstants.FONT_KAITI)
            
            # 三级序号（1.）
            # 如果只有两层结构，1. 作为第二层用楷体；否则用仿宋
            level3_font = GongwenConstants.FONT_KAITI if only_two_levels else GongwenConstants.FONT_FANGSONG
            for idx in structure.level3_indices:
                if check_cancel():
                    return
                self._format_sequence_number(doc, idx, self.LEVEL3_PATTERN, level3_font)
            
            # 四级序号保持仿宋（（1））- 已在正文格式化中设置
            
            # 小标题用黑体
            for idx in structure.subtitle_indices:
                if check_cancel():
                    return
                self._format_subtitle(doc, idx)
            
            debug_log("结构层次序数格式化完成", "GONGWEN")
            
        except Exception as e:
            debug_log(f"结构层次序数格式化失败: {e}", "GONGWEN")
    
    def _format_sequence_number(self, doc, para_index: int, 
                                pattern: re.Pattern, font_name: str) -> None:
        """格式化结构层次序数段落
        
        根据 GB/T 9704-2012 7.3.3：
        - 第一层（一、）用黑体字
        - 第二层（（一））用楷体字
        - 第三层（1.）和第四层（(1)）用仿宋体字
        
        注意：整个段落都使用对应字体，不只是序号部分
        
        Args:
            doc: Word Document COM 对象
            para_index: 段落索引
            pattern: 序号正则表达式
            font_name: 字体名称
        """
        try:
            para = doc.Paragraphs.Item(para_index + 1)
            text = para.Range.Text
            
            match = pattern.match(text)
            if match:
                # 设置整个段落的字体（国标要求整行使用对应字体）
                rng = para.Range
                rng.Font.Name = font_name
                rng.Font.NameFarEast = font_name
                
                # 保持3号字
                rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
                
        except Exception as e:
            debug_log(f"序号格式化失败 (段落 {para_index}): {e}", "GONGWEN")
    
    def _format_subtitle(self, doc, para_index: int) -> None:
        """格式化小标题（如"背景"、"基本原理"等）
        
        小标题使用黑体，3号字，不缩进
        
        Args:
            doc: Word Document COM 对象
            para_index: 段落索引
        """
        try:
            para = doc.Paragraphs.Item(para_index + 1)
            rng = para.Range
            
            # 设置字体 - 黑体
            rng.Font.Name = GongwenConstants.FONT_HEITI
            rng.Font.NameFarEast = GongwenConstants.FONT_HEITI
            
            # 设置字号 - 3号字 (16pt)
            rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
            
            # 设置颜色 - 黑色
            rng.Font.Color = 0
            
            # 设置左对齐，不缩进
            para.Format.Alignment = 0  # wdAlignParagraphLeft
            para.Format.FirstLineIndent = 0
            para.Format.LeftIndent = 0
            
            debug_log(f"小标题格式化完成: 段落 {para_index}", "GONGWEN")
            
        except Exception as e:
            debug_log(f"小标题格式化失败 (段落 {para_index}): {e}", "GONGWEN")

    def _format_signature_date(self, doc, structure: DocumentStructure) -> None:
        """格式化落款和日期 - GB/T 9704-2012 7.3.5
        
        根据最新规范：
        - 不加盖印章：正文下空1行编排发文机关署名，署名下1行编排成文日期
          - 发文机关署名长于成文日期时，右空2字编排发文机关署名，成文日期首字比发文机关署名首字右移2字
          - 发文机关署名短于成文日期时，右空2字编排成文日期，发文机关署名首字比成文日期首字左移2字
        - 加盖印章：正文下空3行编排发文机关署名，日期右空四字，发文机关署名以日期为准居中排布
        
        Args:
            doc: Word Document COM 对象
            structure: 文档结构
            
        Requirements: 4.3
        """
        try:
            # 计算右空四字的缩进（从右边距算起）
            # 4个汉字约 64pt (16pt * 4)
            right_indent_4chars = GongwenConstants.CHAR_WIDTH_3HAO * GongwenConstants.DATE_RIGHT_INDENT_CHARS
            
            # 格式化落款
            if structure.signature_index >= 0:
                para = doc.Paragraphs.Item(structure.signature_index + 1)
                rng = para.Range
                
                # 设置字体 - 仿宋
                rng.Font.Name = GongwenConstants.FONT_FANGSONG
                rng.Font.NameFarEast = GongwenConstants.FONT_FANGSONG
                rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
                rng.Font.Color = 0
                
                # 设置右对齐，右空四字（加盖印章时）
                # 默认按加盖印章处理，日期右空四字，发文机关署名以日期为准居中
                para.Format.Alignment = 2  # wdAlignParagraphRight
                para.Format.RightIndent = right_indent_4chars
                para.Format.FirstLineIndent = 0
                
                debug_log("落款格式化完成（右空四字）", "GONGWEN")
            
            # 格式化日期
            if structure.date_index >= 0:
                para = doc.Paragraphs.Item(structure.date_index + 1)
                rng = para.Range
                
                # 设置字体 - 仿宋
                rng.Font.Name = GongwenConstants.FONT_FANGSONG
                rng.Font.NameFarEast = GongwenConstants.FONT_FANGSONG
                rng.Font.Size = GongwenConstants.FONT_SIZE_3HAO
                rng.Font.Color = 0
                
                # 设置右对齐，右空四字
                para.Format.Alignment = 2  # wdAlignParagraphRight
                para.Format.RightIndent = right_indent_4chars
                para.Format.FirstLineIndent = 0
                
                debug_log("日期格式化完成（右空四字）", "GONGWEN")
            
        except Exception as e:
            debug_log(f"落款/日期格式化失败: {e}", "GONGWEN")
    
    def _setup_page_numbers(self, doc) -> None:
        """设置页码 - GB/T 9704-2012 7.5
        
        4号半角宋体阿拉伯数字
        数字左右各放一条一字线（横线）
        单页码居右空一字，双页码居左空一字
        插入页码时对齐方式选择外侧即可
        
        Args:
            doc: Word Document COM 对象
            
        Requirements: 4.5
        """
        try:
            debug_log("开始设置页码...", "GONGWEN")
            
            # 获取节数
            section_count = doc.Sections.Count
            debug_log(f"文档共 {section_count} 个节", "GONGWEN")
            
            # 遍历所有节
            for section_idx in range(1, section_count + 1):
                try:
                    debug_log(f"处理第 {section_idx} 节页码", "GONGWEN")
                    section = doc.Sections(section_idx)
                    
                    # 启用奇偶页不同
                    try:
                        section.PageSetup.OddAndEvenPagesHeaderFooter = True
                        debug_log("已启用奇偶页不同", "GONGWEN")
                    except Exception as e:
                        debug_log(f"启用奇偶页不同失败: {e}", "GONGWEN")
                    
                    # 设置页脚距离
                    try:
                        footer_distance = self._mm_to_points(GongwenConstants.PAGE_NUM_MARGIN_MM)
                        section.PageSetup.FooterDistance = footer_distance
                        debug_log(f"页脚距离设置为 {footer_distance}pt", "GONGWEN")
                    except Exception as e:
                        debug_log(f"设置页脚距离失败: {e}", "GONGWEN")
                    
                    # 计算空一字的缩进（约4.25mm，即一个3号字宽度的一半多一点）
                    one_char_indent = self._mm_to_points(4.25)
                    
                    # 设置奇数页页脚
                    self._setup_footer_page_number(
                        section, 1, "奇数页",
                        alignment=2,  # wdAlignParagraphRight
                        right_indent=one_char_indent,
                        left_indent=0
                    )
                    
                    # 设置偶数页页脚
                    self._setup_footer_page_number(
                        section, 2, "偶数页",
                        alignment=0,  # wdAlignParagraphLeft
                        right_indent=0,
                        left_indent=one_char_indent
                    )
                    
                except Exception as e:
                    debug_log(f"处理第 {section_idx} 节页码失败: {e}", "GONGWEN")
                    continue
            
            debug_log("页码设置完成（4号半角宋体，单页居右双页居左）", "GONGWEN")
            
        except Exception as e:
            debug_log(f"页码设置失败: {e}", "GONGWEN")
    
    def _setup_footer_page_number(self, section, footer_type: int, footer_name: str,
                                   alignment: int, right_indent: float, left_indent: float) -> None:
        """设置单个页脚的页码
        
        使用更安全的方式插入页码，避免 COM 崩溃。
        
        Args:
            section: Word Section COM 对象
            footer_type: 页脚类型 (1=奇数页/主页脚, 2=偶数页)
            footer_name: 页脚名称（用于日志）
            alignment: 对齐方式 (0=左, 1=中, 2=右)
            right_indent: 右缩进（点数）
            left_indent: 左缩进（点数）
        """
        try:
            debug_log(f"设置{footer_name}页脚...", "GONGWEN")
            
            # 获取页脚
            footer = section.Footers(footer_type)
            
            # 清空页脚内容 - 使用 Delete 而不是设置 Text
            try:
                footer_range = footer.Range
                footer_range.Delete()
                debug_log(f"{footer_name}页脚已清空", "GONGWEN")
            except Exception as e:
                debug_log(f"清空{footer_name}页脚失败: {e}，尝试设置空文本", "GONGWEN")
                try:
                    footer.Range.Text = ""
                except Exception:
                    pass
            
            # 重新获取 Range（清空后 Range 可能已改变）
            footer_range = footer.Range
            
            # 使用 TypeText 方式插入内容，更稳定
            try:
                # 先插入左横线
                footer_range.InsertAfter("— ")
                debug_log(f"{footer_name}插入左横线成功", "GONGWEN")
            except Exception as e:
                debug_log(f"{footer_name}插入左横线失败: {e}", "GONGWEN")
            
            # 插入页码域 - 使用更安全的方式
            try:
                # 将光标移到末尾
                footer_range = footer.Range
                footer_range.Collapse(0)  # wdCollapseEnd
                
                # 使用 InsertField 方法插入页码
                # 参数: Range, Type (-1=wdFieldEmpty), Text, PreserveFormatting
                footer_range.Fields.Add(footer_range, 33, "", True)  # 33 = wdFieldPage
                debug_log(f"{footer_name}插入页码域成功", "GONGWEN")
            except Exception as e:
                debug_log(f"{footer_name}插入页码域失败: {e}，尝试备用方法", "GONGWEN")
                # 备用方法：直接插入 PAGE 域代码
                try:
                    footer_range = footer.Range
                    footer_range.Collapse(0)
                    footer_range.InsertAfter(" ")
                    # 使用 InsertField 的另一种方式
                    footer.Range.Fields.Add(footer.Range, -1, "PAGE", False)
                except Exception as e2:
                    debug_log(f"{footer_name}备用方法也失败: {e2}", "GONGWEN")
            
            # 插入右横线
            try:
                footer_range = footer.Range
                footer_range.Collapse(0)
                footer_range.InsertAfter(" —")
                debug_log(f"{footer_name}插入右横线成功", "GONGWEN")
            except Exception as e:
                debug_log(f"{footer_name}插入右横线失败: {e}", "GONGWEN")
            
            # 设置字体 - 4号半角宋体
            try:
                footer.Range.Font.Name = GongwenConstants.FONT_SONGTI
                footer.Range.Font.Size = GongwenConstants.FONT_SIZE_4HAO
                debug_log(f"{footer_name}字体设置成功", "GONGWEN")
            except Exception as e:
                debug_log(f"{footer_name}字体设置失败: {e}", "GONGWEN")
            
            # 设置对齐和缩进
            try:
                footer.Range.ParagraphFormat.Alignment = alignment
                if right_indent > 0:
                    footer.Range.ParagraphFormat.RightIndent = right_indent
                if left_indent > 0:
                    footer.Range.ParagraphFormat.LeftIndent = left_indent
                debug_log(f"{footer_name}对齐和缩进设置成功", "GONGWEN")
            except Exception as e:
                debug_log(f"{footer_name}对齐和缩进设置失败: {e}", "GONGWEN")
            
            debug_log(f"{footer_name}页脚设置完成", "GONGWEN")
            
        except Exception as e:
            debug_log(f"设置{footer_name}页脚失败: {e}", "GONGWEN")
    
    def get_open_documents(self) -> List[DocumentInfo]:
        """获取所有打开的 Word/WPS 文档
        
        遍历所有运行中的 Word 和 WPS 实例，获取打开的文档列表。
        
        Returns:
            DocumentInfo 列表，包含文档名称、路径和应用类型
            
        Feature: gongwen-dialog
        """
        documents = []
        
        if not WIN32COM_AVAILABLE:
            debug_log("win32com 不可用，无法获取文档列表", "GONGWEN")
            return documents
        
        try:
            pythoncom.CoInitialize()
            
            # 尝试获取 Word 文档
            for app_name, app_type in [
                ("Word.Application", "word"),
                ("Kwps.Application", "wps"),
                ("KET.Application", "wps")
            ]:
                try:
                    app = win32com.client.GetActiveObject(app_name)
                    for doc in app.Documents:
                        try:
                            doc_info = DocumentInfo(
                                name=doc.Name,
                                full_path=doc.FullName if hasattr(doc, 'FullName') else "",
                                app_type=app_type
                            )
                            # 避免重复添加（WPS 可能有多个 COM 名称）
                            if not any(d.name == doc_info.name and d.full_path == doc_info.full_path 
                                      for d in documents):
                                documents.append(doc_info)
                                debug_log(f"找到文档: {doc_info.name} ({app_type})", "GONGWEN")
                        except Exception as e:
                            debug_log(f"获取文档信息失败: {e}", "GONGWEN")
                except pythoncom.com_error:
                    # 该应用未运行，跳过
                    pass
                except Exception as e:
                    debug_log(f"连接 {app_name} 失败: {e}", "GONGWEN")
            
            debug_log(f"共找到 {len(documents)} 个打开的文档", "GONGWEN")
            
        except Exception as e:
            debug_log(f"获取文档列表失败: {e}", "GONGWEN")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        
        return documents
    
    def format_document_by_name(self, doc_name: str, cancel_flag=None) -> GongwenFormatResult:
        """通过文档名称格式化指定文档
        
        在所有打开的 Word/WPS 文档中查找指定名称的文档并格式化。
        
        Args:
            doc_name: 文档名称（如 "文档1.docx"）
            cancel_flag: 可选的取消标志（threading.Event）
            
        Returns:
            GongwenFormatResult 格式化结果
            
        Feature: gongwen-dialog
        """
        debug_log(f"format_document_by_name 被调用, doc_name={doc_name}", "GONGWEN")
        
        if not WIN32COM_AVAILABLE:
            return GongwenFormatResult(
                success=False,
                result=FormatResult.COM_ERROR,
                message="未安装 pywin32，无法连接 Word/WPS"
            )
        
        try:
            pythoncom.CoInitialize()
            
            # 检查取消
            if cancel_flag and cancel_flag.is_set():
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message="格式化已取消"
                )
            
            # 在所有应用中查找文档
            target_doc = None
            
            for app_name, app_type in [
                ("Word.Application", "word"),
                ("Kwps.Application", "wps"),
                ("KET.Application", "wps")
            ]:
                try:
                    app = win32com.client.GetActiveObject(app_name)
                    for doc in app.Documents:
                        if doc.Name == doc_name:
                            target_doc = doc
                            self._word_app = app
                            self._app_type = app_type
                            debug_log(f"找到目标文档: {doc_name} ({app_type})", "GONGWEN")
                            break
                    if target_doc:
                        break
                except pythoncom.com_error:
                    pass
                except Exception as e:
                    debug_log(f"搜索 {app_name} 失败: {e}", "GONGWEN")
            
            if target_doc is None:
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.NO_DOCUMENT,
                    message=f"未找到文档: {doc_name}"
                )
            
            # 执行格式化
            debug_log("开始执行格式化", "GONGWEN")
            self._format_document(target_doc, cancel_flag=cancel_flag)
            
            # 检查是否被取消
            if cancel_flag and cancel_flag.is_set():
                return GongwenFormatResult(
                    success=False,
                    result=FormatResult.FORMAT_ERROR,
                    message="格式化已取消"
                )
            
            debug_log("格式化成功完成", "GONGWEN")
            return GongwenFormatResult(
                success=True,
                result=FormatResult.SUCCESS,
                message="公文格式化完成"
            )
            
        except Exception as e:
            debug_log(f"通过名称格式化失败: {e}", "GONGWEN")
            import traceback
            debug_log(f"异常堆栈: {traceback.format_exc()}", "GONGWEN")
            return GongwenFormatResult(
                success=False,
                result=FormatResult.FORMAT_ERROR,
                message=f"格式化失败: {str(e)}"
            )
        finally:
            self._cleanup_com()


def is_gongwen_formatter_available() -> bool:
    """检查公文格式化功能是否可用
    
    Returns:
        True 如果 win32com 可用
    """
    return WIN32COM_AVAILABLE
