# =====================================================
# =============== 配置管理器 ===============
# =====================================================

"""
配置管理器 - 负责应用配置的读写和管理

Requirements: 9.1, 9.6
Property 10: Configuration Round-Trip
"""

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from screenshot_tool.services.image_preprocessor import PreprocessingConfig


def get_user_data_dir() -> str:
    """
    获取用户数据目录（固定为 ~/.screenshot_tool）
    
    无论是打包环境还是开发环境，都返回相同的路径。
    如果目录不存在，会自动创建。
    
    Feature: unified-data-storage-path
    Requirements: 1.1, 1.2, 1.3, 1.4
    
    Returns:
        用户数据目录的绝对路径
    """
    # Windows 上 os.path.expanduser("~") 可能返回错误路径（如 Documents）
    # 优先使用 USERPROFILE 环境变量，这是 Windows 上最可靠的方式
    if sys.platform == "win32":
        home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    else:
        home = os.path.expanduser("~")
    
    path = os.path.join(home, ".screenshot_tool")
    os.makedirs(path, exist_ok=True)
    return path


def get_app_dir() -> str:
    """
    获取应用目录（向后兼容，实际调用 get_user_data_dir）
    
    Feature: unified-data-storage-path
    Requirements: 2.4, 5.1, 5.2
    
    Returns:
        应用目录路径（等同于用户数据目录）
    """
    return get_user_data_dir()


def get_config_filename() -> str:
    """
    获取配置文件名
    
    Returns:
        配置文件名，固定为 config.json
    """
    return "config.json"


def get_portable_config_path(app_dir: Optional[str] = None) -> str:
    """
    获取便携式配置文件路径
    
    Args:
        app_dir: 应用目录，默认自动检测
        
    Returns:
        配置文件完整路径
    """
    if app_dir is None:
        app_dir = get_app_dir()
    return os.path.join(app_dir, get_config_filename())


def is_portable_mode() -> bool:
    """
    检查是否为便携模式（打包后的 EXE）
    
    Returns:
        是否为便携模式
    """
    return getattr(sys, 'frozen', False)


@dataclass
class ToolColorsConfig:
    """各绘图工具的颜色配置"""
    rect: str = "#FF0000"      # 矩形 - 红色
    ellipse: str = "#FF0000"   # 椭圆/方块 - 红色
    arrow: str = "#FF0000"     # 箭头 - 红色
    line: str = "#FF0000"      # 直线 - 红色
    pen: str = "#FF0000"       # 画笔 - 红色
    marker: str = "#FFFF00"    # 高亮 - 黄色
    text: str = "#FF0000"      # 文字 - 红色
    mosaic: str = "#000000"    # 马赛克 - 黑色（实际不使用颜色）
    step: str = "#FF0000"      # 步骤编号 - 红色
    
    # 默认颜色常量（供其他模块引用）
    DEFAULT_COLORS = {
        "rect": "#FF0000",
        "ellipse": "#FF0000",
        "arrow": "#FF0000",
        "line": "#FF0000",
        "pen": "#FF0000",
        "marker": "#FFFF00",
        "text": "#FF0000",
        "mosaic": "#000000",
        "step": "#FF0000",
    }
    
    @staticmethod
    def is_valid_color(color: str) -> bool:
        """检查颜色值是否有效"""
        if not color or not isinstance(color, str):
            return False
        # 简单的十六进制颜色验证
        if color.startswith("#") and len(color) in (4, 7, 9):
            try:
                int(color[1:], 16)
                return True
            except ValueError:
                return False
        return False
    
    def __post_init__(self):
        """验证并规范化颜色值"""
        for field_name in ["rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"]:
            color = getattr(self, field_name)
            # 处理 None 值或无效颜色
            if color is None or not ToolColorsConfig.is_valid_color(color):
                setattr(self, field_name, self.DEFAULT_COLORS[field_name])


@dataclass
class ToolWidthsConfig:
    """各绘图工具的粗细配置（粗细级别 1-10）"""
    rect: int = 2       # 矩形
    ellipse: int = 2    # 椭圆/方块
    arrow: int = 2      # 箭头
    line: int = 2       # 直线
    pen: int = 2        # 画笔
    marker: int = 5     # 高亮 - 默认较粗
    text: int = 3       # 文字
    mosaic: int = 5     # 马赛克 - 默认较粗
    step: int = 5       # 步骤编号 - 默认中等大小
    
    # 默认粗细常量（供其他模块引用）
    DEFAULT_WIDTHS = {
        "rect": 2,
        "ellipse": 2,
        "arrow": 2,
        "line": 2,
        "pen": 2,
        "marker": 5,
        "text": 3,
        "mosaic": 5,
        "step": 5,
    }
    
    # 粗细级别范围
    MIN_WIDTH = 1
    MAX_WIDTH = 10
    
    @classmethod
    def is_valid_width(cls, width: int) -> bool:
        """检查粗细值是否有效"""
        if not isinstance(width, int):
            return False
        return cls.MIN_WIDTH <= width <= cls.MAX_WIDTH
    
    def __post_init__(self):
        """验证并规范化粗细值"""
        for field_name in ["rect", "ellipse", "arrow", "line", "pen", "marker", "text", "mosaic", "step"]:
            width = getattr(self, field_name)
            # 处理 None 值或无效粗细
            if width is None or not ToolWidthsConfig.is_valid_width(width):
                setattr(self, field_name, self.DEFAULT_WIDTHS[field_name])


@dataclass
class NotificationConfig:
    """系统通知配置
    
    控制各类系统托盘通知的显示开关，默认全部开启。
    """
    startup: bool = True           # 启动通知
    screenshot_save: bool = True   # 截图保存通知
    ding: bool = True              # 贴图通知
    anki: bool = True              # Anki 导入通知
    gongwen: bool = True           # 公文格式化通知
    hotkey_update: bool = True     # 快捷键更新通知
    software_update: bool = True   # 软件版本更新通知
    pdf_convert: bool = True       # PDF 转换通知
    regulation: bool = True        # 规章下载通知
    recording: bool = True         # 录屏完成通知
    
    # 字段名列表（用于验证）
    _FIELD_NAMES = ("startup", "screenshot_save", "ding", "anki", "gongwen", "hotkey_update", "software_update", "pdf_convert", "regulation", "recording")
    
    def __post_init__(self):
        """确保所有字段都是布尔值，处理 None 和非布尔类型"""
        for field_name in self._FIELD_NAMES:
            value = getattr(self, field_name, None)
            # 处理 None、非布尔值、或其他异常情况
            if value is None or not isinstance(value, bool):
                # 尝试转换为布尔值，失败则默认为 True
                try:
                    setattr(self, field_name, bool(value) if value is not None else True)
                except (ValueError, TypeError):
                    setattr(self, field_name, True)


@dataclass
class UpdateConfig:
    """软件更新配置
    
    用于配置自动更新功能的行为，包括自动下载、检查间隔、GitHub 仓库等。
    
    Feature: auto-update
    Requirements: 4.1, 4.2, 4.4
    """
    auto_download_enabled: bool = True   # 自动后台下载新版本，默认开启
    check_interval_hours: int = 24       # 检查间隔（小时），默认 24 小时
    last_check_time: str = ""            # 上次检查时间 (ISO format: 2026-01-07T10:00:00)
    github_repo: str = "wangwingzero/hugescreenshot"  # GitHub 仓库地址
    use_proxy: bool = True               # 是否使用 GitHub 加速代理，默认开启
    proxy_url: str = "https://ghproxy.net/"  # GitHub 加速代理地址
    skip_version: str = ""               # 跳过的版本（用户选择"跳过此版本"时记录）
    last_notified_version: str = ""      # 上次通知的版本（避免重复通知）
    last_run_version: str = ""           # 上次运行的版本号（用于智能清理更新文件）
    
    # 检查间隔范围
    MIN_INTERVAL_HOURS = 1
    MAX_INTERVAL_HOURS = 168  # 7 天
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保布尔值
        if not isinstance(self.auto_download_enabled, bool):
            self.auto_download_enabled = True
        
        # 验证检查间隔范围
        if self.check_interval_hours is None or not isinstance(self.check_interval_hours, int):
            self.check_interval_hours = 24
        else:
            self.check_interval_hours = max(
                self.MIN_INTERVAL_HOURS, 
                min(self.MAX_INTERVAL_HOURS, self.check_interval_hours)
            )
        
        # 处理 None 值
        if self.last_check_time is None:
            self.last_check_time = ""
        if self.github_repo is None:
            self.github_repo = "wangwingzero/hugescreenshot"
        if not isinstance(self.use_proxy, bool):
            self.use_proxy = True
        # 迁移旧的代理地址到新地址
        old_proxies = (None, "", "https://ghproxy.com/", "https://mirror.ghproxy.com/")
        if self.proxy_url in old_proxies:
            self.proxy_url = "https://ghproxy.net/"
        if self.skip_version is None:
            self.skip_version = ""
        if self.last_notified_version is None:
            self.last_notified_version = ""
        if self.last_run_version is None:
            self.last_run_version = ""
    
    def should_check(self) -> bool:
        """判断是否应该进行自动检查
        
        永远自动检查更新，只检查时间间隔。
        
        Returns:
            bool: 如果距离上次检查超过间隔时间，返回 True
        """
        if not self.last_check_time:
            return True
        
        try:
            from datetime import datetime, timedelta
            last_check = datetime.fromisoformat(self.last_check_time)
            now = datetime.now()
            interval = timedelta(hours=self.check_interval_hours)
            return now - last_check >= interval
        except (ValueError, TypeError):
            return True
    
    def update_last_check_time(self):
        """更新上次检查时间为当前时间"""
        from datetime import datetime
        self.last_check_time = datetime.now().isoformat()


@dataclass
class MinerUConfig:
    """MinerU PDF 转 Markdown 配置
    
    用于配置 MinerU API 的 PDF 转换功能。
    
    Feature: pdf-to-markdown
    """
    api_token: str = ""           # MinerU API Token
    last_pdf_dir: str = ""        # 上次打开的 PDF 目录
    model_version: str = "vlm"    # 模型版本: pipeline 或 vlm
    save_dir: str = ""            # 保存目录，空字符串表示使用源文件目录
    
    # 有效的模型版本
    VALID_MODEL_VERSIONS = {"pipeline", "vlm"}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.api_token is None:
            self.api_token = ""
        if self.last_pdf_dir is None:
            self.last_pdf_dir = ""
        if self.model_version is None or self.model_version not in self.VALID_MODEL_VERSIONS:
            self.model_version = "vlm"
        if self.save_dir is None:
            self.save_dir = ""
    
    def is_configured(self) -> bool:
        """检查 API Token 是否已配置
        
        Returns:
            bool: Token 非空则返回 True
        """
        return bool(self.api_token.strip())
    
    def get_save_dir(self, source_file_dir: str = "") -> str:
        """获取保存目录
        
        Args:
            source_file_dir: 源文件所在目录，作为默认值
            
        Returns:
            保存目录路径
        """
        if self.save_dir:
            return self.save_dir
        if source_file_dir:
            return source_file_dir
        # 默认目录: 桌面
        return os.path.join(os.path.expanduser("~"), "Desktop")


@dataclass
class RegulationConfig:
    """CAAC 规章查询配置
    
    用于配置规章查询功能的行为，包括保存路径、窗口状态等。
    
    Feature: caac-regulation-search
    Requirements: 6.2, 7.2
    """
    save_path: str = ""  # PDF 保存路径，空字符串表示使用默认目录 ~/Documents/CAAC_PDF
    
    # 窗口状态
    window_x: int = 100
    window_y: int = 100
    window_width: int = 800
    window_height: int = 600
    
    # 上次筛选条件
    last_doc_type: str = "all"  # "all", "regulation", "normative"
    last_validity: str = "all"  # "all", "valid", "invalid"
    
    # 通知设置
    notification_enabled: bool = True  # 下载完成通知
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.save_path is None:
            self.save_path = ""
        
        # 验证窗口尺寸
        if self.window_width is None or not isinstance(self.window_width, int) or self.window_width < 400:
            self.window_width = 800
        if self.window_height is None or not isinstance(self.window_height, int) or self.window_height < 300:
            self.window_height = 600
        
        # 验证筛选条件
        if self.last_doc_type not in ("all", "regulation", "normative"):
            self.last_doc_type = "all"
        if self.last_validity not in ("all", "valid", "invalid"):
            self.last_validity = "all"
        
        # 确保布尔值
        if not isinstance(self.notification_enabled, bool):
            self.notification_enabled = True
    
    def get_save_path(self) -> str:
        """获取保存路径，如果未设置则返回默认目录（桌面）
        
        Returns:
            保存目录路径
        """
        if self.save_path:
            return self.save_path
        # 默认目录: 桌面
        return os.path.join(os.path.expanduser("~"), "Desktop")



@dataclass
class HotkeyConfig:
    """快捷键配置
    
    Feature: hotkey-force-lock
    Requirements: 1.1, 1.2, 1.3, 1.4
    """
    screenshot_modifier: str = "alt"  # 修饰键: alt, ctrl, shift, ctrl+alt, ctrl+shift, alt+shift
    screenshot_key: str = "x"  # 主键
    
    # 强制锁定热键配置
    force_lock: bool = False  # 是否启用强制锁定，默认关闭
    retry_interval_ms: int = 3000  # 重试间隔（毫秒），默认 3 秒
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    # 重试间隔范围（毫秒）
    MIN_RETRY_INTERVAL_MS = 1000   # 最小 1 秒
    MAX_RETRY_INTERVAL_MS = 30000  # 最大 30 秒
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.screenshot_modifier is None:
            self.screenshot_modifier = "alt"
        if self.screenshot_key is None:
            self.screenshot_key = "x"
        
        # 规范化为小写
        self.screenshot_modifier = str(self.screenshot_modifier).lower()
        self.screenshot_key = str(self.screenshot_key).lower()
        
        # 验证修饰键
        if self.screenshot_modifier not in self.VALID_MODIFIERS:
            self.screenshot_modifier = "alt"
        
        # 验证主键
        if self.screenshot_key not in self.VALID_KEYS:
            self.screenshot_key = "x"
        
        # 验证强制锁定开关
        if not isinstance(self.force_lock, bool):
            self.force_lock = False
        
        # 验证重试间隔范围
        if self.retry_interval_ms is None or not isinstance(self.retry_interval_ms, int):
            self.retry_interval_ms = 3000
        else:
            self.retry_interval_ms = max(
                self.MIN_RETRY_INTERVAL_MS,
                min(self.MAX_RETRY_INTERVAL_MS, self.retry_interval_ms)
            )


@dataclass
class GongwenHotkeyConfig:
    """公文格式化快捷键配置
    
    用于配置公文格式化功能的快捷键，按下快捷键后进入格式化模式，
    鼠标旁显示特殊图标，点击 Word 窗口后自动格式化。
    
    注意：默认使用 Ctrl+Alt+G，避免与 Word 的 Alt+G（设计选项卡）冲突
    """
    enabled: bool = False  # 功能开关，默认关闭
    modifier: str = "ctrl+alt"  # 修饰键: alt, ctrl, shift, ctrl+alt, ctrl+shift, alt+shift
    key: str = "g"  # 主键，默认 g
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保 enabled 是布尔值
        if not isinstance(self.enabled, bool):
            self.enabled = False
        
        # 处理 None 值
        if self.modifier is None:
            self.modifier = "ctrl+alt"
        if self.key is None:
            self.key = "g"
        
        # 规范化为小写
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        
        # 验证修饰键
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "ctrl+alt"
        
        # 验证主键
        if self.key not in self.VALID_KEYS:
            self.key = "g"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串，如 'alt+g'
        
        Returns:
            热键字符串，格式为 'modifier+key'
        """
        return f"{self.modifier}+{self.key}"


@dataclass
class MainWindowHotkeyConfig:
    """主界面快捷键配置
    
    用于配置打开主界面的快捷键。
    
    Feature: extended-hotkeys
    Requirements: 1.1
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "ctrl+alt"  # 修饰键
    key: str = "q"  # 主键
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if self.modifier is None:
            self.modifier = "ctrl+alt"
        if self.key is None:
            self.key = "q"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "ctrl+alt"
        if self.key not in self.VALID_KEYS:
            self.key = "q"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class ClipboardHistoryHotkeyConfig:
    """工作台快捷键配置
    
    用于配置打开工作台窗口的快捷键。
    
    Feature: extended-hotkeys
    Requirements: 1.2
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "ctrl+alt"  # 修饰
    key: str = "p"  # 主键
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if self.modifier is None:
            self.modifier = "alt"
        if self.key is None:
            self.key = "p"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "alt"
        if self.key not in self.VALID_KEYS:
            self.key = "p"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class OCRPanelHotkeyConfig:
    """识别文字快捷键配置
    
    用于配置打开 OCR 结果面板的快捷键。
    
    Feature: extended-hotkeys
    Requirements: 1.3
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "alt"  # 修饰键
    key: str = "o"  # 主键
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if self.modifier is None:
            self.modifier = "alt"
        if self.key is None:
            self.key = "o"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "alt"
        if self.key not in self.VALID_KEYS:
            self.key = "o"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class SpotlightHotkeyConfig:
    """聚光灯快捷键配置
    
    用于配置切换聚光灯效果的快捷键。
    
    Feature: extended-hotkeys
    Requirements: 1.4
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "alt"  # 修饰键
    key: str = "s"  # 主键
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if self.modifier is None:
            self.modifier = "alt"
        if self.key is None:
            self.key = "s"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "alt"
        if self.key not in self.VALID_KEYS:
            self.key = "s"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class MouseHighlightHotkeyConfig:
    """鼠标高亮快捷键配置
    
    用于配置切换鼠标高亮效果的快捷键。
    
    Feature: extended-hotkeys
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "alt"  # 修饰键
    key: str = "m"  # 主键
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if self.modifier is None:
            self.modifier = "alt"
        if self.key is None:
            self.key = "m"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "alt"
        if self.key not in self.VALID_KEYS:
            self.key = "m"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class StateRestoreHotkeyConfig:
    """截图状态恢复快捷键配置
    
    用于配置恢复上次截图状态的快捷键。
    
    Feature: screenshot-state-restore
    Requirements: 5.1
    """
    enabled: bool = True  # 功能开关，默认开启
    modifier: str = "alt"  # 修饰键
    key: str = "r"  # 主键，默认 r (Restore)
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        if not isinstance(self.enabled, bool):
            self.enabled = True
        if self.modifier is None:
            self.modifier = "alt"
        if self.key is None:
            self.key = "r"
        self.modifier = str(self.modifier).lower()
        self.key = str(self.key).lower()
        if self.modifier not in self.VALID_MODIFIERS:
            self.modifier = "alt"
        if self.key not in self.VALID_KEYS:
            self.key = "r"
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串"""
        return f"{self.modifier}+{self.key}"


@dataclass
class MarkdownConfig:
    """Markdown 转换配置
    
    用于配置网页转 Markdown 功能的行为，包括保存目录、内容选项、超时设置和快捷键。
    
    Feature: web-to-markdown
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    save_dir: str = ""  # 保存目录，空字符串表示使用默认目录 ~/Documents/Markdown
    include_images: bool = True  # 是否包含图片引用
    include_links: bool = True  # 是否包含链接
    timeout: int = 30  # 网络超时时间（秒）
    
    # 快捷键配置
    hotkey_enabled: bool = False  # 快捷键开关，默认关闭
    hotkey_modifier: str = "alt"  # 修饰键: alt, ctrl, shift, ctrl+alt, ctrl+shift, alt+shift
    hotkey_key: str = "m"  # 主键，默认 m
    
    # 超时范围
    MIN_TIMEOUT = 5
    MAX_TIMEOUT = 120
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.save_dir is None:
            self.save_dir = ""
        
        # 确保布尔值
        if not isinstance(self.include_images, bool):
            self.include_images = True
        if not isinstance(self.include_links, bool):
            self.include_links = True
        if not isinstance(self.hotkey_enabled, bool):
            self.hotkey_enabled = False
        
        # 验证超时范围
        if self.timeout is None or not isinstance(self.timeout, int):
            self.timeout = 30
        else:
            self.timeout = max(self.MIN_TIMEOUT, min(self.MAX_TIMEOUT, self.timeout))
        
        # 处理快捷键 None 值
        if self.hotkey_modifier is None:
            self.hotkey_modifier = "alt"
        if self.hotkey_key is None:
            self.hotkey_key = "m"
        
        # 规范化快捷键为小写
        self.hotkey_modifier = str(self.hotkey_modifier).lower()
        self.hotkey_key = str(self.hotkey_key).lower()
        
        # 验证修饰键
        if self.hotkey_modifier not in self.VALID_MODIFIERS:
            self.hotkey_modifier = "alt"
        
        # 验证主键
        if self.hotkey_key not in self.VALID_KEYS:
            self.hotkey_key = "m"
    
    def get_save_dir(self) -> str:
        """获取保存目录，如果未设置则返回默认目录（桌面）
        
        Returns:
            保存目录路径
        """
        if self.save_dir:
            return self.save_dir
        # 默认目录: 桌面
        return os.path.join(os.path.expanduser("~"), "Desktop")
    
    def get_hotkey_string(self) -> str:
        """获取热键字符串，如 'alt+m'

        Returns:
            热键字符串，格式为 'modifier+key'
        """
        return f"{self.hotkey_modifier}+{self.hotkey_key}"


@dataclass
class RecordingConfig:
    """录屏配置"""
    # 保存设置
    save_path: str = ""  # 录屏保存路径，空则使用默认 ~/Videos/Recordings
    auto_save: bool = True  # 录制完成后自动保存

    # 音频设置
    record_system_audio: bool = True   # 录制系统声音
    record_microphone: bool = False    # 录制麦克风

    # 视频设置
    fps: int = 30                      # 帧率：15/30/60
    quality: str = "medium"            # 质量：low/medium/high
    show_cursor: bool = True           # 显示鼠标指针

    # 通知设置
    notification_enabled: bool = True  # 录制完成通知

    # 有效范围
    VALID_FPS = {15, 30, 60}
    VALID_QUALITY = {"low", "medium", "high"}

    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.save_path is None:
            self.save_path = ""

        # 确保布尔值
        if not isinstance(self.auto_save, bool):
            self.auto_save = True
        if not isinstance(self.record_system_audio, bool):
            self.record_system_audio = True
        if not isinstance(self.record_microphone, bool):
            self.record_microphone = False
        if not isinstance(self.show_cursor, bool):
            self.show_cursor = True
        if not isinstance(self.notification_enabled, bool):
            self.notification_enabled = True

        # 验证帧率
        if self.fps not in self.VALID_FPS:
            self.fps = 30

        # 验证质量
        if self.quality not in self.VALID_QUALITY:
            self.quality = "medium"

    def get_save_path(self) -> str:
        """获取保存路径，如果未设置则返回默认目录"""
        if self.save_path:
            return self.save_path
        return os.path.join(os.path.expanduser("~"), "Videos", "Recordings")

    def get_bitrate(self) -> int:
        """根据质量获取比特率（bps）"""
        bitrate_map = {
            "low": 2_000_000,      # 2 Mbps
            "medium": 5_000_000,   # 5 Mbps
            "high": 10_000_000,    # 10 Mbps
        }
        return bitrate_map.get(self.quality, 5_000_000)


@dataclass
class RecordingHotkeyConfig:
    """录屏快捷键配置"""
    enabled: bool = True               # 功能开关
    start_modifier: str = "ctrl+alt"   # 开始/停止录制修饰键
    start_key: str = "r"               # 开始/停止录制主键

    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}

    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保 enabled 是布尔值
        if not isinstance(self.enabled, bool):
            self.enabled = True

        # 处理 None 值
        if self.start_modifier is None:
            self.start_modifier = "ctrl+alt"
        if self.start_key is None:
            self.start_key = "r"

        # 规范化为小写
        self.start_modifier = str(self.start_modifier).lower()
        self.start_key = str(self.start_key).lower()

        # 验证修饰键
        if self.start_modifier not in self.VALID_MODIFIERS:
            self.start_modifier = "ctrl+alt"

        # 验证主键
        if self.start_key not in self.VALID_KEYS:
            self.start_key = "r"

    def get_hotkey_string(self) -> str:
        """获取热键字符串，如 'ctrl+alt+r'"""
        return f"{self.start_modifier}+{self.start_key}"


# 鼠标高亮主题配色
MOUSE_HIGHLIGHT_THEMES = {
    "classic_yellow": {
        "name": "经典黄色",
        "circle_color": "#FFD700",
        "left_click_color": "#FFD700",
        "right_click_color": "#FF6B6B"
    },
    "business_blue": {
        "name": "商务蓝色",
        "circle_color": "#4A90E2",
        "left_click_color": "#4A90E2",
        "right_click_color": "#E24A4A"
    },
    "vibrant_red": {
        "name": "活力红色",
        "circle_color": "#FF4757",
        "left_click_color": "#FF4757",
        "right_click_color": "#FFA502"
    },
    "fresh_green": {
        "name": "清新绿色",
        "circle_color": "#2ECC71",
        "left_click_color": "#2ECC71",
        "right_click_color": "#9B59B6"
    }
}


@dataclass
class MouseHighlightConfig:
    """鼠标高亮配置
    
    用于配置鼠标高亮演示增强功能，包括效果开关、参数和主题。
    
    Feature: mouse-highlight
    Requirements: 8.1, 8.3, 9.6
    """
    # 基本设置
    enabled: bool = False              # 功能开关，默认关闭
    hotkey: str = "alt+m"              # 切换快捷键
    restore_on_startup: bool = True    # 启动时恢复上次状态
    
    # 效果开关
    circle_enabled: bool = True        # 光圈效果
    spotlight_enabled: bool = False    # 聚光灯效果
    cursor_magnify_enabled: bool = False  # 指针放大效果
    click_effect_enabled: bool = True  # 点击涟漪效果
    
    # 主题
    theme: str = "classic_yellow"      # 配色主题
    
    # 光圈参数
    circle_radius: int = 40            # 半径 (px)
    circle_thickness: int = 3          # 线条粗细 (px)
    
    # 聚光灯参数
    spotlight_radius: int = 150        # 半径 (px)
    spotlight_darkness: int = 60       # 暗部透明度 (0-100)
    
    # 指针放大参数
    cursor_scale: float = 2.0          # 放大倍数
    
    # 涟漪参数
    ripple_duration: int = 500         # 动画时长 (ms)
    
    # 有效的主题列表
    VALID_THEMES = {"classic_yellow", "business_blue", "vibrant_red", "fresh_green"}
    
    # 有效的修饰键列表
    VALID_MODIFIERS = {"alt", "ctrl", "shift", "ctrl+alt", "ctrl+shift", "alt+shift"}
    # 有效的主键列表
    VALID_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {f"f{i}" for i in range(1, 13)}
    
    # 参数范围
    MIN_CIRCLE_RADIUS = 10
    MAX_CIRCLE_RADIUS = 100
    MIN_CIRCLE_THICKNESS = 1
    MAX_CIRCLE_THICKNESS = 10
    MIN_SPOTLIGHT_RADIUS = 50
    MAX_SPOTLIGHT_RADIUS = 500
    MIN_SPOTLIGHT_DARKNESS = 0
    MAX_SPOTLIGHT_DARKNESS = 100
    MIN_CURSOR_SCALE = 1.0
    MAX_CURSOR_SCALE = 5.0
    MIN_RIPPLE_DURATION = 100
    MAX_RIPPLE_DURATION = 2000
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保布尔值
        if not isinstance(self.enabled, bool):
            self.enabled = False
        if not isinstance(self.restore_on_startup, bool):
            self.restore_on_startup = True
        if not isinstance(self.circle_enabled, bool):
            self.circle_enabled = True
        if not isinstance(self.spotlight_enabled, bool):
            self.spotlight_enabled = False
        if not isinstance(self.cursor_magnify_enabled, bool):
            self.cursor_magnify_enabled = False
        if not isinstance(self.click_effect_enabled, bool):
            self.click_effect_enabled = True
        
        # 处理 None 值
        if self.hotkey is None:
            self.hotkey = "alt+m"
        if self.theme is None:
            self.theme = "classic_yellow"
        
        # 验证主题
        if self.theme not in self.VALID_THEMES:
            self.theme = "classic_yellow"
        
        # 验证快捷键格式
        self.hotkey = str(self.hotkey).lower()
        parts = self.hotkey.split("+")
        if len(parts) >= 2:
            modifier = "+".join(parts[:-1])
            key = parts[-1]
            if modifier not in self.VALID_MODIFIERS or key not in self.VALID_KEYS:
                self.hotkey = "alt+m"
        else:
            self.hotkey = "alt+m"
        
        # 验证参数范围
        if self.circle_radius is None or not isinstance(self.circle_radius, int):
            self.circle_radius = 40
        else:
            self.circle_radius = max(self.MIN_CIRCLE_RADIUS, min(self.MAX_CIRCLE_RADIUS, self.circle_radius))
        
        if self.circle_thickness is None or not isinstance(self.circle_thickness, int):
            self.circle_thickness = 3
        else:
            self.circle_thickness = max(self.MIN_CIRCLE_THICKNESS, min(self.MAX_CIRCLE_THICKNESS, self.circle_thickness))
        
        if self.spotlight_radius is None or not isinstance(self.spotlight_radius, int):
            self.spotlight_radius = 150
        else:
            self.spotlight_radius = max(self.MIN_SPOTLIGHT_RADIUS, min(self.MAX_SPOTLIGHT_RADIUS, self.spotlight_radius))
        
        if self.spotlight_darkness is None or not isinstance(self.spotlight_darkness, int):
            self.spotlight_darkness = 60
        else:
            self.spotlight_darkness = max(self.MIN_SPOTLIGHT_DARKNESS, min(self.MAX_SPOTLIGHT_DARKNESS, self.spotlight_darkness))
        
        if self.cursor_scale is None or not isinstance(self.cursor_scale, (int, float)):
            self.cursor_scale = 2.0
        else:
            self.cursor_scale = max(self.MIN_CURSOR_SCALE, min(self.MAX_CURSOR_SCALE, float(self.cursor_scale)))
        
        if self.ripple_duration is None or not isinstance(self.ripple_duration, int):
            self.ripple_duration = 500
        else:
            self.ripple_duration = max(self.MIN_RIPPLE_DURATION, min(self.MAX_RIPPLE_DURATION, self.ripple_duration))
    
    def get_theme_colors(self) -> dict:
        """获取当前主题的颜色配置
        
        Returns:
            包含 circle_color, left_click_color, right_click_color 的字典
        """
        return MOUSE_HIGHLIGHT_THEMES.get(self.theme, MOUSE_HIGHLIGHT_THEMES["classic_yellow"])
    
    def get_hotkey_parts(self) -> tuple:
        """解析快捷键为修饰键和主键
        
        Returns:
            (modifier, key) 元组
        """
        parts = self.hotkey.split("+")
        if len(parts) >= 2:
            return "+".join(parts[:-1]), parts[-1]
        return "alt", "m"


@dataclass
class MainWindowConfig:
    """主窗口配置
    
    用于配置主界面窗口的显示状态和位置。
    
    Feature: main-window
    Requirements: 8.5
    """
    show_welcome: bool = True      # 是否显示欢迎提示（首次启动）
    window_x: int = -1             # 窗口位置X（-1表示居中）
    window_y: int = -1             # 窗口位置Y（-1表示居中）
    window_width: int = 900        # 窗口宽度
    window_height: int = 650       # 窗口高度
    show_on_startup: bool = True   # 启动时显示主窗口
    
    # 窗口尺寸范围
    MIN_WIDTH = 800
    MIN_HEIGHT = 600
    MAX_WIDTH = 2560
    MAX_HEIGHT = 1440
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保布尔值
        if not isinstance(self.show_welcome, bool):
            self.show_welcome = True
        if not isinstance(self.show_on_startup, bool):
            self.show_on_startup = True
        
        # 验证窗口尺寸范围
        if self.window_width is None or not isinstance(self.window_width, int):
            self.window_width = 900
        else:
            self.window_width = max(self.MIN_WIDTH, min(self.MAX_WIDTH, self.window_width))
        
        if self.window_height is None or not isinstance(self.window_height, int):
            self.window_height = 650
        else:
            self.window_height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, self.window_height))
        
        # 窗口位置可以是 -1（居中）或有效坐标
        if self.window_x is None or not isinstance(self.window_x, int):
            self.window_x = -1
        if self.window_y is None or not isinstance(self.window_y, int):
            self.window_y = -1


@dataclass
class MiniToolbarConfig:
    """极简工具栏配置
    
    用于配置极简工具栏窗口的显示状态和位置。
    
    Feature: mini-toolbar
    Requirements: 1.3, 1.4, 2.4
    """
    window_x: int = -1             # 窗口位置X（-1表示居中）
    window_y: int = -1             # 窗口位置Y（-1表示居中）
    is_pinned: bool = False        # 是否置顶
    last_mode: str = "main"        # 上次使用的模式 (main/mini)
    
    # 有效的模式
    VALID_MODES = {"main", "mini"}
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保布尔值
        if not isinstance(self.is_pinned, bool):
            self.is_pinned = False
        
        # 窗口位置可以是 -1（居中）或有效坐标
        if self.window_x is None or not isinstance(self.window_x, int):
            self.window_x = -1
        if self.window_y is None or not isinstance(self.window_y, int):
            self.window_y = -1
        
        # 验证模式
        if self.last_mode is None or self.last_mode not in self.VALID_MODES:
            self.last_mode = "main"


@dataclass
class SplitWindowState:
    """分屏窗口状态
    
    使用 bytes 存储 Qt 原生状态数据（QByteArray），
    确保跨版本兼容性和屏幕变化处理。
    
    Feature: screenshot-ocr-split-view
    Requirements: 1.4, 6.7
    """
    geometry: bytes = b""  # saveGeometry() 返回的数据
    splitter_state: bytes = b""  # QSplitter.saveState() 返回的数据
    is_pinned: bool = True  # 是否置顶，默认置顶
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保 geometry 是 bytes 类型
        if self.geometry is None:
            self.geometry = b""
        elif isinstance(self.geometry, str):
            # 从 JSON 加载时可能是 base64 字符串
            try:
                import base64
                self.geometry = base64.b64decode(self.geometry)
            except Exception:
                self.geometry = b""
        elif not isinstance(self.geometry, bytes):
            self.geometry = b""
        
        # 确保 splitter_state 是 bytes 类型
        if self.splitter_state is None:
            self.splitter_state = b""
        elif isinstance(self.splitter_state, str):
            # 从 JSON 加载时可能是 base64 字符串
            try:
                import base64
                self.splitter_state = base64.b64decode(self.splitter_state)
            except Exception:
                self.splitter_state = b""
        elif not isinstance(self.splitter_state, bytes):
            self.splitter_state = b""
        
        # 确保 is_pinned 是布尔值
        if not isinstance(self.is_pinned, bool):
            self.is_pinned = True
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于 JSON 序列化）
        
        bytes 数据使用 base64 编码存储。
        """
        import base64
        return {
            "geometry": base64.b64encode(self.geometry).decode('ascii') if self.geometry else "",
            "splitter_state": base64.b64encode(self.splitter_state).decode('ascii') if self.splitter_state else "",
            "is_pinned": self.is_pinned,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SplitWindowState":
        """从字典创建对象
        
        bytes 数据从 base64 编码解码。
        """
        import base64
        geometry = b""
        splitter_state = b""
        
        if data.get("geometry"):
            try:
                geometry = base64.b64decode(data["geometry"])
            except Exception:
                geometry = b""
        
        if data.get("splitter_state"):
            try:
                splitter_state = base64.b64decode(data["splitter_state"])
            except Exception:
                splitter_state = b""
        
        return cls(
            geometry=geometry,
            splitter_state=splitter_state,
            is_pinned=data.get("is_pinned", True),
        )


@dataclass
class SystemToolsConfig:
    """系统工具配置
    
    用于配置系统工具功能，包括闹钟、番茄钟和测速历史。
    
    Feature: system-tools
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
    """
    # 闹钟列表 (序列化为 dict 列表)
    alarms: list = field(default_factory=list)
    
    # 番茄钟设置
    pomodoro_work_minutes: int = 25
    pomodoro_short_break_minutes: int = 5
    pomodoro_long_break_minutes: int = 15
    
    # 测速历史
    speed_test_history: list = field(default_factory=list)
    
    # 番茄钟时长范围
    MIN_WORK_MINUTES = 1
    MAX_WORK_MINUTES = 120
    MIN_BREAK_MINUTES = 1
    MAX_BREAK_MINUTES = 60
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 确保列表类型
        if not isinstance(self.alarms, list):
            self.alarms = []
        if not isinstance(self.speed_test_history, list):
            self.speed_test_history = []
        
        # 验证番茄钟时长范围
        if not isinstance(self.pomodoro_work_minutes, int):
            self.pomodoro_work_minutes = 25
        else:
            self.pomodoro_work_minutes = max(
                self.MIN_WORK_MINUTES,
                min(self.MAX_WORK_MINUTES, self.pomodoro_work_minutes)
            )
        
        if not isinstance(self.pomodoro_short_break_minutes, int):
            self.pomodoro_short_break_minutes = 5
        else:
            self.pomodoro_short_break_minutes = max(
                self.MIN_BREAK_MINUTES,
                min(self.MAX_BREAK_MINUTES, self.pomodoro_short_break_minutes)
            )
        
        if not isinstance(self.pomodoro_long_break_minutes, int):
            self.pomodoro_long_break_minutes = 15
        else:
            self.pomodoro_long_break_minutes = max(
                self.MIN_BREAK_MINUTES,
                min(self.MAX_BREAK_MINUTES, self.pomodoro_long_break_minutes)
            )


@dataclass
class SubscriptionConfig:
    """订阅系统配置
    
    用于配置 Supabase 连接和订阅缓存。
    
    Feature: subscription-system
    Requirements: 6.1, 7.2
    """
    # Supabase 连接配置
    supabase_url: str = ""
    # 使用 legacy anon key (JWT 格式)，Python SDK 需要此格式
    supabase_key: str = ""
    
    # 缓存配置
    cache_ttl_hours: int = 24  # 缓存有效期（小时）
    grace_period_days: int = 7  # 宽限期（天）
    
    # 用户状态（运行时，不持久化到配置文件）
    # 这些值由 LicenseService 管理
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 处理 None 值
        if self.supabase_url is None:
            self.supabase_url = "https://ttgtdiybtmvdddxanumk.supabase.co"
        if self.supabase_key is None:
            self.supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0Z3RkaXlidG12ZGRkeGFudW1rIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjY4NDUsImV4cCI6MjA4MzYwMjg0NX0.3M8397FMs5opGITupMlHhe0yo2qm7SHKS3ShK0Mjteo"
        
        # 验证缓存 TTL 范围
        if self.cache_ttl_hours is None or not isinstance(self.cache_ttl_hours, int):
            self.cache_ttl_hours = 24
        else:
            self.cache_ttl_hours = max(1, min(168, self.cache_ttl_hours))  # 1小时到7天
        
        # 验证宽限期范围
        if self.grace_period_days is None or not isinstance(self.grace_period_days, int):
            self.grace_period_days = 7
        else:
            self.grace_period_days = max(1, min(30, self.grace_period_days))  # 1天到30天



@dataclass
class OCRConfig:
    """OCR配置

    默认使用 RapidOCR 本地引擎，用户可通过OCR面板按钮手动切换到云端OCR。

    引擎说明：
    - rapid: RapidOCR 本地引擎，基于 OpenVINO，无需网络（默认）
    - tencent: 腾讯云 OCR API，需要网络和 API 密钥，通过按钮手动触发
    - baidu: 百度云 OCR API，需要网络和 API 密钥，通过按钮手动触发

    云端OCR内部降级顺序：高精度版 → 通用版
    """
    # 腾讯云OCR配置
    tencent_secret_id: str = ""  # 腾讯云 SecretId
    tencent_secret_key: str = ""  # 腾讯云 SecretKey
    
    # 百度OCR配置
    baidu_api_key: str = ""  # 百度云OCR API Key
    baidu_secret_key: str = ""  # 百度云OCR Secret Key
    
    # 向后兼容字段（保留但不再使用）
    engine_priority: list = field(default_factory=lambda: ["rapid"])
    tencent_enabled: bool = True
    baidu_enabled: bool = True
    paddle_enabled: bool = True
    rapid_enabled: bool = True
    
    def __post_init__(self):
        """验证并规范化配置"""
        # 清理API密钥（去除首尾空格，处理None值）
        self.tencent_secret_id = (self.tencent_secret_id or "").strip()
        self.tencent_secret_key = (self.tencent_secret_key or "").strip()
        self.baidu_api_key = (self.baidu_api_key or "").strip()
        self.baidu_secret_key = (self.baidu_secret_key or "").strip()
        
        # 确保 engine_priority 是列表类型（向后兼容）
        if self.engine_priority is None or not isinstance(self.engine_priority, list):
            self.engine_priority = ["rapid"]
    
    def is_tencent_configured(self) -> bool:
        """检查腾讯云OCR是否已配置"""
        return bool(self.tencent_secret_id and self.tencent_secret_key)
    
    def is_baidu_configured(self) -> bool:
        """检查百度云OCR是否已配置"""
        return bool(self.baidu_api_key and self.baidu_secret_key)


@dataclass
class DingConfig:
    """贴图配置"""
    default_opacity: float = 1.0
    mouse_through_default: bool = False
    remember_position: bool = True
    
    # 透明度范围
    MIN_OPACITY = 0.1
    MAX_OPACITY = 1.0
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 验证透明度范围
        if self.default_opacity is None or not isinstance(self.default_opacity, (int, float)):
            self.default_opacity = 1.0
        else:
            self.default_opacity = max(self.MIN_OPACITY, min(self.MAX_OPACITY, float(self.default_opacity)))


@dataclass
class FreeTranslationConfig:
    """翻译引擎优先级配置
    
    注意：每个引擎内部都有自动降级机制：
    - google: 原生API → 备用API (findmyip.net)
    - youdao: 原生API (dict.youdao.com)
    - jianxin: 保底翻译 (api.qvqa.cn)
    """
    # 翻译引擎优先级列表（按顺序尝试）
    # 可选值: google, youdao, jianxin
    engine_priority: list = field(default_factory=lambda: ["google", "youdao", "jianxin"])
    
    # 各引擎启用状态
    google_enabled: bool = True    # 谷歌翻译（原生+备用）
    youdao_enabled: bool = True    # 有道翻译
    jianxin_enabled: bool = True   # 简心翻译（保底）
    
    # 兼容旧配置的别名
    @property
    def google_free_enabled(self) -> bool:
        return self.google_enabled
    
    @google_free_enabled.setter
    def google_free_enabled(self, value: bool):
        self.google_enabled = value
    
    @property
    def youdao_free_enabled(self) -> bool:
        return self.youdao_enabled
    
    @youdao_free_enabled.setter
    def youdao_free_enabled(self, value: bool):
        self.youdao_enabled = value
    
    # 有效的引擎列表
    VALID_ENGINES = {"google", "youdao", "jianxin", "google_free", "youdao_free"}
    
    def __post_init__(self):
        """验证并规范化配置"""
        if self.engine_priority is None:
            self.engine_priority = ["google", "youdao", "jianxin"]
        
        # 规范化引擎名称（兼容旧配置）
        normalized = []
        for e in self.engine_priority:
            if e == "google_free":
                normalized.append("google")
            elif e == "youdao_free":
                normalized.append("youdao")
            elif e in {"google", "youdao", "jianxin"}:
                normalized.append(e)
        
        if not normalized:
            normalized = ["google", "youdao", "jianxin"]
        
        self.engine_priority = normalized
    
    def get_enabled_engines(self) -> list:
        """获取启用的引擎列表（按优先级排序）
        
        Returns:
            启用的引擎列表，如果全部禁用则返回默认优先级
        """
        enabled = []
        for engine in self.engine_priority:
            if engine == "google" and self.google_enabled:
                enabled.append(engine)
            elif engine == "youdao" and self.youdao_enabled:
                enabled.append(engine)
            elif engine == "jianxin" and self.jianxin_enabled:
                enabled.append(engine)
        
        # 如果所有引擎都被禁用，返回默认优先级
        if not enabled:
            return ["google", "youdao", "jianxin"]
        
        return enabled


@dataclass
class TranslationConfig:
    """翻译配置"""
    default_engine: str = "google"
    target_language: str = "zh"
    deepl_api_key: str = ""
    baidu_app_id: str = ""
    baidu_secret_key: str = ""
    timed_interval_ms: int = 2000
    cache_enabled: bool = True
    
    # 定时翻译间隔范围（毫秒）
    MIN_INTERVAL_MS = 500
    MAX_INTERVAL_MS = 10000
    
    def __post_init__(self):
        """验证并规范化配置值"""
        # 验证定时翻译间隔范围
        if self.timed_interval_ms is None or not isinstance(self.timed_interval_ms, int):
            self.timed_interval_ms = 2000
        else:
            self.timed_interval_ms = max(self.MIN_INTERVAL_MS, min(self.MAX_INTERVAL_MS, self.timed_interval_ms))


@dataclass
class AppConfig:
    """应用配置"""
    
    # 截图设置
    save_path: str = ""
    last_save_folder: str = ""  # 上次保存的文件夹路径（用于文件夹选择对话框）
    auto_save: bool = False
    
    # OCR设置（旧版兼容）
    ocr_api_url: str = "http://127.0.0.1:1224"
    ocr_language: str = "auto"
    
    # OCR引擎配置（新版）
    ocr: OCRConfig = field(default_factory=OCRConfig)
    
    # 翻译设置
    translation_provider: str = "baidu"
    translation_api_key: str = ""
    translation_secret_key: str = ""
    translation_source_lang: str = "auto"
    translation_target_lang: str = "zh"
    
    # 免费翻译引擎配置
    free_translation: FreeTranslationConfig = field(default_factory=FreeTranslationConfig)
    
    # Anki设置
    anki_host: str = "127.0.0.1"
    anki_port: int = 8765
    anki_default_deck: str = "Default"
    anki_default_model: str = "Basic"
    
    # Anki 单词卡图片 API 设置
    anki_unsplash_keys: str = ""  # Unsplash API Keys（多个用逗号分隔）
    anki_pixabay_key: str = ""    # Pixabay API Key
    
    # 高亮设置
    highlight_color: str = "yellow"
    highlight_opacity: float = 0.3
    auto_select_highlight: bool = True  # 截图时自动启用高亮功能
    
    # 绘制工具设置
    draw_color: str = "#FFFF00"  # 默认黄色（兼容旧配置）
    
    # 各工具独立颜色设置
    tool_colors: ToolColorsConfig = field(default_factory=ToolColorsConfig)
    
    # 各工具独立粗细设置
    tool_widths: ToolWidthsConfig = field(default_factory=ToolWidthsConfig)
    
    # 窗口设置
    window_x: int = 100
    window_y: int = 100
    window_width: int = 1200
    window_height: int = 800
    
    # 贴图设置
    ding: DingConfig = field(default_factory=DingConfig)
    
    # 翻译增强设置
    translation_enhanced: TranslationConfig = field(default_factory=TranslationConfig)
    
    # 快捷键设置
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    
    # 开机自启动设置
    auto_start: bool = True  # 默认开启开机自启动
    
    # 自动OCR弹窗设置
    auto_ocr_popup_enabled: bool = True  # 默认开启自动OCR弹窗（运行时状态，不再持久化）
    always_ocr_on_screenshot: bool = False  # 截图时始终开启OCR，默认关闭（用户需手动在设置中开启）
    
    # 分屏视图设置
    # Feature: screenshot-ocr-split-view
    # Requirements: 7.1
    use_split_view: bool = True  # 使用分屏视图替代弹窗，默认开启
    
    # 系统通知设置
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    
    # 公文格式化快捷键设置
    gongwen_hotkey: GongwenHotkeyConfig = field(default_factory=GongwenHotkeyConfig)
    
    # Markdown 转换配置
    markdown: MarkdownConfig = field(default_factory=MarkdownConfig)
    
    # 软件更新配置
    update: UpdateConfig = field(default_factory=UpdateConfig)
    
    # MinerU PDF 转换配置
    mineru: MinerUConfig = field(default_factory=MinerUConfig)
    
    # CAAC 规章查询配置
    regulation: RegulationConfig = field(default_factory=RegulationConfig)

    # 录屏配置
    recording: RecordingConfig = field(default_factory=RecordingConfig)

    # 录屏快捷键配置
    recording_hotkey: RecordingHotkeyConfig = field(default_factory=RecordingHotkeyConfig)

    # 订阅系统配置
    subscription: SubscriptionConfig = field(default_factory=SubscriptionConfig)

    # 鼠标高亮配置
    mouse_highlight: MouseHighlightConfig = field(default_factory=MouseHighlightConfig)

    # 扩展快捷键配置
    # Feature: extended-hotkeys
    main_window_hotkey: MainWindowHotkeyConfig = field(default_factory=MainWindowHotkeyConfig)
    clipboard_hotkey: ClipboardHistoryHotkeyConfig = field(default_factory=ClipboardHistoryHotkeyConfig)
    ocr_panel_hotkey: OCRPanelHotkeyConfig = field(default_factory=OCRPanelHotkeyConfig)
    spotlight_hotkey: SpotlightHotkeyConfig = field(default_factory=SpotlightHotkeyConfig)
    mouse_highlight_hotkey: MouseHighlightHotkeyConfig = field(default_factory=MouseHighlightHotkeyConfig)

    # 截图状态恢复快捷键配置
    # Feature: screenshot-state-restore
    state_restore_hotkey: StateRestoreHotkeyConfig = field(default_factory=StateRestoreHotkeyConfig)

    # 主窗口配置
    main_window: "MainWindowConfig" = field(default_factory=lambda: MainWindowConfig())

    # 极简工具栏配置
    # Feature: mini-toolbar
    mini_toolbar: "MiniToolbarConfig" = field(default_factory=lambda: MiniToolbarConfig())

    # 分屏窗口状态配置
    # Feature: screenshot-ocr-split-view
    split_window_state: "SplitWindowState" = field(default_factory=lambda: SplitWindowState())

    # 系统工具配置
    # Feature: system-tools
    system_tools: "SystemToolsConfig" = field(default_factory=lambda: SystemToolsConfig())

    # 安装路径（用于全量更新时覆盖安装到原路径）
    # Feature: fullupdate-inplace-install
    # Requirements: 1.1, 1.2
    install_path: str = ""

    # OCR 预处理配置
    preprocessing: dict = field(default_factory=lambda: {
        "enabled": True,
        "contrast_enhancement": True,
        "sharpening": False,  # 默认关闭锐化，避免放大噪点
        "binarization": False,
        "use_otsu": False,  # Otsu 二值化
        "denoise": False,  # 形态学去噪
        "clahe_clip_limit": 2.0,
        "clahe_grid_size": 8,
        "sharpen_strength": 1.0,
        # 扁平图像处理配置
        "auto_upscale": True,
        "min_height": 32,
        "target_height": 300,  # 放大目标高度
        "max_aspect_ratio": 5.0,  # 宽高比阈值，超过此值视为扁平图像
        "extreme_aspect_ratio": 6.0,  # 极端扁平阈值
        "extreme_target_height": 600,  # 极端扁平目标高度
        "upscale_sharpen": True,  # 放大后锐化
        "padding_enabled": True,
        "padding_size": 30,  # 边距大小（专家建议 20-50px）
        # 低对比度模式
        "low_contrast_mode": True,
        "low_contrast_threshold": 0.4,
    })
    
    def __post_init__(self):
        """初始化后处理"""
        # 设置默认保存路径
        if not self.save_path:
            self.save_path = os.path.expanduser("~/Pictures/Screenshots")
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于JSON序列化）"""
        return {
            "save_path": self.save_path,
            "last_save_folder": self.last_save_folder,
            "auto_save": self.auto_save,
            "ocr": {
                "api_url": self.ocr_api_url,
                "language": self.ocr_language,
                "engine_priority": self.ocr.engine_priority,
                "tencent_enabled": self.ocr.tencent_enabled,
                "tencent_secret_id": self.ocr.tencent_secret_id,
                "tencent_secret_key": self.ocr.tencent_secret_key,
                "baidu_enabled": self.ocr.baidu_enabled,
                "baidu_api_key": self.ocr.baidu_api_key,
                "baidu_secret_key": self.ocr.baidu_secret_key,
                "paddle_enabled": self.ocr.paddle_enabled,
                "rapid_enabled": self.ocr.rapid_enabled,
            },
            "translation": {
                "provider": self.translation_provider,
                "api_key": self.translation_api_key,
                "secret_key": self.translation_secret_key,
                "source_lang": self.translation_source_lang,
                "target_lang": self.translation_target_lang,
            },
            "free_translation": {
                "engine_priority": self.free_translation.engine_priority,
                "google_enabled": self.free_translation.google_enabled,
                "youdao_enabled": self.free_translation.youdao_enabled,
                "jianxin_enabled": self.free_translation.jianxin_enabled,
            },
            "anki": {
                "host": self.anki_host,
                "port": self.anki_port,
                "default_deck": self.anki_default_deck,
                "default_model": self.anki_default_model,
                "unsplash_keys": self.anki_unsplash_keys,
                "pixabay_key": self.anki_pixabay_key,
            },
            "highlight": {
                "color": self.highlight_color,
                "opacity": self.highlight_opacity,
                "auto_select": self.auto_select_highlight,
            },
            "draw": {
                "color": self.draw_color,
            },
            "tool_colors": {
                "rect": self.tool_colors.rect,
                "ellipse": self.tool_colors.ellipse,
                "arrow": self.tool_colors.arrow,
                "line": self.tool_colors.line,
                "pen": self.tool_colors.pen,
                "marker": self.tool_colors.marker,
                "text": self.tool_colors.text,
                "mosaic": self.tool_colors.mosaic,
                "step": self.tool_colors.step,
            },
            "tool_widths": {
                "rect": self.tool_widths.rect,
                "ellipse": self.tool_widths.ellipse,
                "arrow": self.tool_widths.arrow,
                "line": self.tool_widths.line,
                "pen": self.tool_widths.pen,
                "marker": self.tool_widths.marker,
                "text": self.tool_widths.text,
                "mosaic": self.tool_widths.mosaic,
                "step": self.tool_widths.step,
            },
            "window": {
                "x": self.window_x,
                "y": self.window_y,
                "width": self.window_width,
                "height": self.window_height,
            },
            "ding": {
                "default_opacity": self.ding.default_opacity,
                "mouse_through_default": self.ding.mouse_through_default,
                "remember_position": self.ding.remember_position,
            },
            "translation_enhanced": {
                "default_engine": self.translation_enhanced.default_engine,
                "target_language": self.translation_enhanced.target_language,
                "deepl_api_key": self.translation_enhanced.deepl_api_key,
                "baidu_app_id": self.translation_enhanced.baidu_app_id,
                "baidu_secret_key": self.translation_enhanced.baidu_secret_key,
                "timed_interval_ms": self.translation_enhanced.timed_interval_ms,
                "cache_enabled": self.translation_enhanced.cache_enabled,
            },
            "hotkey": {
                "screenshot_modifier": self.hotkey.screenshot_modifier,
                "screenshot_key": self.hotkey.screenshot_key,
            },
            "auto_start": self.auto_start,
            "always_ocr_on_screenshot": self.always_ocr_on_screenshot,
            "use_split_view": self.use_split_view,
            "notification": {
                "startup": self.notification.startup,
                "screenshot_save": self.notification.screenshot_save,
                "ding": self.notification.ding,
                "anki": self.notification.anki,
                "gongwen": self.notification.gongwen,
                "hotkey_update": self.notification.hotkey_update,
                "software_update": self.notification.software_update,
                "pdf_convert": self.notification.pdf_convert,
                "regulation": self.notification.regulation,
                "recording": self.notification.recording,
            },
            "gongwen_hotkey": {
                "enabled": self.gongwen_hotkey.enabled,
                "modifier": self.gongwen_hotkey.modifier,
                "key": self.gongwen_hotkey.key,
            },
            "markdown": {
                "save_dir": self.markdown.save_dir,
                "include_images": self.markdown.include_images,
                "include_links": self.markdown.include_links,
                "timeout": self.markdown.timeout,
                "hotkey_enabled": self.markdown.hotkey_enabled,
                "hotkey_modifier": self.markdown.hotkey_modifier,
                "hotkey_key": self.markdown.hotkey_key,
            },
            "update": {
                "auto_download_enabled": self.update.auto_download_enabled,
                "check_interval_hours": self.update.check_interval_hours,
                "last_check_time": self.update.last_check_time,
                "github_repo": self.update.github_repo,
                "use_proxy": self.update.use_proxy,
                "proxy_url": self.update.proxy_url,
                "skip_version": self.update.skip_version,
                "last_notified_version": self.update.last_notified_version,
            },
            "mineru": {
                "api_token": self.mineru.api_token,
                "last_pdf_dir": self.mineru.last_pdf_dir,
                "model_version": self.mineru.model_version,
                "save_dir": self.mineru.save_dir,
            },
            "regulation": {
                "save_path": self.regulation.save_path,
                "window_x": self.regulation.window_x,
                "window_y": self.regulation.window_y,
                "window_width": self.regulation.window_width,
                "window_height": self.regulation.window_height,
                "last_doc_type": self.regulation.last_doc_type,
                "last_validity": self.regulation.last_validity,
                "notification_enabled": self.regulation.notification_enabled,
            },
            "recording": {
                "save_path": self.recording.save_path,
                "auto_save": self.recording.auto_save,
                "record_system_audio": self.recording.record_system_audio,
                "record_microphone": self.recording.record_microphone,
                "fps": self.recording.fps,
                "quality": self.recording.quality,
                "show_cursor": self.recording.show_cursor,
                "notification_enabled": self.recording.notification_enabled,
            },
            "recording_hotkey": {
                "enabled": self.recording_hotkey.enabled,
                "start_modifier": self.recording_hotkey.start_modifier,
                "start_key": self.recording_hotkey.start_key,
            },
            "subscription": {
                "supabase_url": self.subscription.supabase_url,
                "supabase_key": self.subscription.supabase_key,
                "cache_ttl_hours": self.subscription.cache_ttl_hours,
                "grace_period_days": self.subscription.grace_period_days,
            },
            "mouse_highlight": {
                "enabled": self.mouse_highlight.enabled,
                "hotkey": self.mouse_highlight.hotkey,
                "restore_on_startup": self.mouse_highlight.restore_on_startup,
                "circle_enabled": self.mouse_highlight.circle_enabled,
                "spotlight_enabled": self.mouse_highlight.spotlight_enabled,
                "cursor_magnify_enabled": self.mouse_highlight.cursor_magnify_enabled,
                "click_effect_enabled": self.mouse_highlight.click_effect_enabled,
                "theme": self.mouse_highlight.theme,
                "circle_radius": self.mouse_highlight.circle_radius,
                "circle_thickness": self.mouse_highlight.circle_thickness,
                "spotlight_radius": self.mouse_highlight.spotlight_radius,
                "spotlight_darkness": self.mouse_highlight.spotlight_darkness,
                "cursor_scale": self.mouse_highlight.cursor_scale,
                "ripple_duration": self.mouse_highlight.ripple_duration,
            },
            # 扩展快捷键配置
            # Feature: extended-hotkeys
            "main_window_hotkey": {
                "enabled": self.main_window_hotkey.enabled,
                "modifier": self.main_window_hotkey.modifier,
                "key": self.main_window_hotkey.key,
            },
            "clipboard_hotkey": {
                "enabled": self.clipboard_hotkey.enabled,
                "modifier": self.clipboard_hotkey.modifier,
                "key": self.clipboard_hotkey.key,
            },
            "ocr_panel_hotkey": {
                "enabled": self.ocr_panel_hotkey.enabled,
                "modifier": self.ocr_panel_hotkey.modifier,
                "key": self.ocr_panel_hotkey.key,
            },
            "spotlight_hotkey": {
                "enabled": self.spotlight_hotkey.enabled,
                "modifier": self.spotlight_hotkey.modifier,
                "key": self.spotlight_hotkey.key,
            },
            "mouse_highlight_hotkey": {
                "enabled": self.mouse_highlight_hotkey.enabled,
                "modifier": self.mouse_highlight_hotkey.modifier,
                "key": self.mouse_highlight_hotkey.key,
            },
            # 截图状态恢复快捷键配置
            # Feature: screenshot-state-restore
            "state_restore_hotkey": {
                "enabled": self.state_restore_hotkey.enabled,
                "modifier": self.state_restore_hotkey.modifier,
                "key": self.state_restore_hotkey.key,
            },
            "main_window": {
                "show_welcome": self.main_window.show_welcome,
                "window_x": self.main_window.window_x,
                "window_y": self.main_window.window_y,
                "window_width": self.main_window.window_width,
                "window_height": self.main_window.window_height,
                "show_on_startup": self.main_window.show_on_startup,
            },
            # 极简工具栏配置
            # Feature: mini-toolbar
            "mini_toolbar": {
                "window_x": self.mini_toolbar.window_x,
                "window_y": self.mini_toolbar.window_y,
                "is_pinned": self.mini_toolbar.is_pinned,
                "last_mode": self.mini_toolbar.last_mode,
            },
            # 分屏窗口状态配置
            # Feature: screenshot-ocr-split-view
            "split_window_state": self.split_window_state.to_dict(),
            # 系统工具配置
            # Feature: system-tools
            "system_tools": {
                "alarms": self.system_tools.alarms,
                "pomodoro_work_minutes": self.system_tools.pomodoro_work_minutes,
                "pomodoro_short_break_minutes": self.system_tools.pomodoro_short_break_minutes,
                "pomodoro_long_break_minutes": self.system_tools.pomodoro_long_break_minutes,
                "speed_test_history": self.system_tools.speed_test_history,
            },
            "install_path": self.install_path,
            "preprocessing": self.preprocessing,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """从字典创建配置对象"""
        config = cls()
        
        # 基础设置
        config.save_path = data.get("save_path", config.save_path)
        config.last_save_folder = data.get("last_save_folder", config.last_save_folder)
        config.auto_save = data.get("auto_save", config.auto_save)
        
        # OCR设置
        ocr = data.get("ocr", {})
        config.ocr_api_url = ocr.get("api_url", config.ocr_api_url)
        config.ocr_language = ocr.get("language", config.ocr_language)
        
        # OCR引擎配置
        # 注意：默认只使用 RapidOCR，用户通过按钮手动切换云端OCR
        # 向后兼容：如果配置中没有 rapid_enabled，使用 paddle_enabled 的值
        paddle_enabled = ocr.get("paddle_enabled", True)
        rapid_enabled = ocr.get("rapid_enabled", paddle_enabled)  # 默认使用 paddle_enabled 的值
        config.ocr = OCRConfig(
            tencent_secret_id=ocr.get("tencent_secret_id", ""),
            tencent_secret_key=ocr.get("tencent_secret_key", ""),
            baidu_api_key=ocr.get("baidu_api_key", ""),
            baidu_secret_key=ocr.get("baidu_secret_key", ""),
            # 向后兼容字段
            engine_priority=ocr.get("engine_priority", ["rapid"]),
            tencent_enabled=ocr.get("tencent_enabled", True),
            baidu_enabled=ocr.get("baidu_enabled", True),
            paddle_enabled=paddle_enabled,
            rapid_enabled=rapid_enabled,
        )
        
        # 翻译设置
        translation = data.get("translation", {})
        config.translation_provider = translation.get("provider", config.translation_provider)
        config.translation_api_key = translation.get("api_key", config.translation_api_key)
        config.translation_secret_key = translation.get("secret_key", config.translation_secret_key)
        config.translation_source_lang = translation.get("source_lang", config.translation_source_lang)
        config.translation_target_lang = translation.get("target_lang", config.translation_target_lang)
        
        # 免费翻译引擎配置
        free_trans = data.get("free_translation", {})
        # 兼容旧配置字段名
        google_enabled = free_trans.get("google_enabled", free_trans.get("google_free_enabled", True))
        youdao_enabled = free_trans.get("youdao_enabled", free_trans.get("youdao_free_enabled", True))
        config.free_translation = FreeTranslationConfig(
            engine_priority=free_trans.get("engine_priority", ["google", "youdao", "jianxin"]),
            google_enabled=google_enabled,
            youdao_enabled=youdao_enabled,
            jianxin_enabled=free_trans.get("jianxin_enabled", True),
        )
        
        # Anki设置
        anki = data.get("anki", {})
        config.anki_host = anki.get("host", config.anki_host)
        config.anki_port = anki.get("port", config.anki_port)
        config.anki_default_deck = anki.get("default_deck", config.anki_default_deck)
        config.anki_default_model = anki.get("default_model", config.anki_default_model)
        config.anki_unsplash_keys = anki.get("unsplash_keys", "")
        config.anki_pixabay_key = anki.get("pixabay_key", "")
        
        # 高亮设置
        highlight = data.get("highlight", {})
        config.highlight_color = highlight.get("color", config.highlight_color)
        config.highlight_opacity = highlight.get("opacity", config.highlight_opacity)
        config.auto_select_highlight = highlight.get("auto_select", config.auto_select_highlight)
        
        # 绘制工具设置
        draw = data.get("draw", {})
        config.draw_color = draw.get("color", config.draw_color)
        
        # 各工具独立颜色设置
        tool_colors = data.get("tool_colors", {})
        config.tool_colors = ToolColorsConfig(
            rect=tool_colors.get("rect", "#FF0000"),
            ellipse=tool_colors.get("ellipse", "#FF0000"),
            arrow=tool_colors.get("arrow", "#FF0000"),
            line=tool_colors.get("line", "#FF0000"),
            pen=tool_colors.get("pen", "#FF0000"),
            marker=tool_colors.get("marker", "#FFFF00"),
            text=tool_colors.get("text", "#FF0000"),
            mosaic=tool_colors.get("mosaic", "#000000"),
            step=tool_colors.get("step", "#FF0000"),
        )
        
        # 各工具独立粗细设置
        tool_widths = data.get("tool_widths", {})
        config.tool_widths = ToolWidthsConfig(
            rect=tool_widths.get("rect", 2),
            ellipse=tool_widths.get("ellipse", 2),
            arrow=tool_widths.get("arrow", 2),
            line=tool_widths.get("line", 2),
            pen=tool_widths.get("pen", 2),
            marker=tool_widths.get("marker", 5),
            text=tool_widths.get("text", 3),
            mosaic=tool_widths.get("mosaic", 5),
            step=tool_widths.get("step", 5),
        )
        
        # 窗口设置
        window = data.get("window", {})
        config.window_x = window.get("x", config.window_x)
        config.window_y = window.get("y", config.window_y)
        config.window_width = window.get("width", config.window_width)
        config.window_height = window.get("height", config.window_height)
        
        # 贴图设置
        ding = data.get("ding", {})
        config.ding = DingConfig(
            default_opacity=ding.get("default_opacity", 1.0),
            mouse_through_default=ding.get("mouse_through_default", False),
            remember_position=ding.get("remember_position", True),
        )
        
        # 翻译增强设置
        trans_enh = data.get("translation_enhanced", {})
        config.translation_enhanced = TranslationConfig(
            default_engine=trans_enh.get("default_engine", "google"),
            target_language=trans_enh.get("target_language", "zh"),
            deepl_api_key=trans_enh.get("deepl_api_key", ""),
            baidu_app_id=trans_enh.get("baidu_app_id", ""),
            baidu_secret_key=trans_enh.get("baidu_secret_key", ""),
            timed_interval_ms=trans_enh.get("timed_interval_ms", 2000),
            cache_enabled=trans_enh.get("cache_enabled", True),
        )
        
        # 快捷键设置 (新增)
        hotkey = data.get("hotkey", {})
        config.hotkey = HotkeyConfig(
            screenshot_modifier=hotkey.get("screenshot_modifier", "alt"),
            screenshot_key=hotkey.get("screenshot_key", "a"),
        )
        
        # 开机自启动设置
        config.auto_start = data.get("auto_start", True)  # 默认开启
        
        # 截图时始终OCR设置
        config.always_ocr_on_screenshot = data.get("always_ocr_on_screenshot", False)  # 默认关闭
        
        # 分屏视图设置
        # Feature: screenshot-ocr-split-view
        config.use_split_view = data.get("use_split_view", True)  # 默认开启
        
        # 系统通知设置（兼容旧配置）
        notification = data.get("notification", {})
        # 兼容旧的 anki_notification_enabled 字段
        old_anki_notification = data.get("anki_notification_enabled", True)
        config.notification = NotificationConfig(
            startup=notification.get("startup", True),
            screenshot_save=notification.get("screenshot_save", True),
            ding=notification.get("ding", True),
            anki=notification.get("anki", old_anki_notification),  # 兼容旧配置
            gongwen=notification.get("gongwen", True),
            hotkey_update=notification.get("hotkey_update", True),
            software_update=notification.get("software_update", True),
            pdf_convert=notification.get("pdf_convert", True),
        )
        
        # 公文格式化快捷键设置
        gongwen_hotkey = data.get("gongwen_hotkey", {})
        config.gongwen_hotkey = GongwenHotkeyConfig(
            enabled=gongwen_hotkey.get("enabled", False),
            modifier=gongwen_hotkey.get("modifier", "alt"),
            key=gongwen_hotkey.get("key", "g"),
        )
        
        # Markdown 转换配置
        markdown = data.get("markdown", {})
        config.markdown = MarkdownConfig(
            save_dir=markdown.get("save_dir", ""),
            include_images=markdown.get("include_images", True),
            include_links=markdown.get("include_links", True),
            timeout=markdown.get("timeout", 30),
            hotkey_enabled=markdown.get("hotkey_enabled", False),
            hotkey_modifier=markdown.get("hotkey_modifier", "alt"),
            hotkey_key=markdown.get("hotkey_key", "m"),
        )
        
        # 软件更新配置
        update = data.get("update", {})
        config.update = UpdateConfig(
            auto_download_enabled=update.get("auto_download_enabled", True),
            check_interval_hours=update.get("check_interval_hours", 24),
            last_check_time=update.get("last_check_time", ""),
            github_repo=update.get("github_repo", "wangwingzero/hugescreenshot"),
            use_proxy=update.get("use_proxy", True),
            proxy_url=update.get("proxy_url", "https://ghproxy.net/"),
            skip_version=update.get("skip_version", ""),
            last_notified_version=update.get("last_notified_version", ""),
        )
        
        # MinerU PDF 转换配置
        mineru = data.get("mineru", {})
        config.mineru = MinerUConfig(
            api_token=mineru.get("api_token", ""),
            last_pdf_dir=mineru.get("last_pdf_dir", ""),
            model_version=mineru.get("model_version", "vlm"),
            save_dir=mineru.get("save_dir", ""),
        )
        
        # CAAC 规章查询配置
        regulation = data.get("regulation", {})
        config.regulation = RegulationConfig(
            save_path=regulation.get("save_path", ""),
            window_x=regulation.get("window_x", 100),
            window_y=regulation.get("window_y", 100),
            window_width=regulation.get("window_width", 800),
            window_height=regulation.get("window_height", 600),
            last_doc_type=regulation.get("last_doc_type", "all"),
            last_validity=regulation.get("last_validity", "all"),
            notification_enabled=regulation.get("notification_enabled", True),
        )

        # 录屏配置
        recording = data.get("recording", {})
        config.recording = RecordingConfig(
            save_path=recording.get("save_path", ""),
            auto_save=recording.get("auto_save", True),
            record_system_audio=recording.get("record_system_audio", True),
            record_microphone=recording.get("record_microphone", False),
            fps=recording.get("fps", 30),
            quality=recording.get("quality", "medium"),
            show_cursor=recording.get("show_cursor", True),
            notification_enabled=recording.get("notification_enabled", True),
        )

        # 录屏快捷键配置
        recording_hotkey = data.get("recording_hotkey", {})
        config.recording_hotkey = RecordingHotkeyConfig(
            enabled=recording_hotkey.get("enabled", True),
            start_modifier=recording_hotkey.get("start_modifier", "ctrl+alt"),
            start_key=recording_hotkey.get("start_key", "r"),
        )

        # 订阅系统配置
        subscription = data.get("subscription", {})
        config.subscription = SubscriptionConfig(
            supabase_url=subscription.get("supabase_url", "https://ttgtdiybtmvdddxanumk.supabase.co"),
            supabase_key=subscription.get("supabase_key", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0Z3RkaXlidG12ZGRkeGFudW1rIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjY4NDUsImV4cCI6MjA4MzYwMjg0NX0.3M8397FMs5opGITupMlHhe0yo2qm7SHKS3ShK0Mjteo"),
            cache_ttl_hours=subscription.get("cache_ttl_hours", 24),
            grace_period_days=subscription.get("grace_period_days", 7),
        )

        # 鼠标高亮配置
        mouse_highlight = data.get("mouse_highlight", {})
        config.mouse_highlight = MouseHighlightConfig(
            enabled=mouse_highlight.get("enabled", False),
            hotkey=mouse_highlight.get("hotkey", "alt+m"),
            restore_on_startup=mouse_highlight.get("restore_on_startup", True),
            circle_enabled=mouse_highlight.get("circle_enabled", True),
            spotlight_enabled=mouse_highlight.get("spotlight_enabled", False),
            cursor_magnify_enabled=mouse_highlight.get("cursor_magnify_enabled", False),
            click_effect_enabled=mouse_highlight.get("click_effect_enabled", True),
            theme=mouse_highlight.get("theme", "classic_yellow"),
            circle_radius=mouse_highlight.get("circle_radius", 40),
            circle_thickness=mouse_highlight.get("circle_thickness", 3),
            spotlight_radius=mouse_highlight.get("spotlight_radius", 150),
            spotlight_darkness=mouse_highlight.get("spotlight_darkness", 60),
            cursor_scale=mouse_highlight.get("cursor_scale", 2.0),
            ripple_duration=mouse_highlight.get("ripple_duration", 500),
        )

        # 扩展快捷键配置
        # Feature: extended-hotkeys
        main_window_hotkey = data.get("main_window_hotkey", {})
        config.main_window_hotkey = MainWindowHotkeyConfig(
            enabled=main_window_hotkey.get("enabled", False),
            modifier=main_window_hotkey.get("modifier", "ctrl+alt"),
            key=main_window_hotkey.get("key", "x"),
        )

        clipboard_hotkey = data.get("clipboard_hotkey", {})
        config.clipboard_hotkey = ClipboardHistoryHotkeyConfig(
            enabled=clipboard_hotkey.get("enabled", False),
            modifier=clipboard_hotkey.get("modifier", "alt"),
            key=clipboard_hotkey.get("key", "p"),
        )

        ocr_panel_hotkey = data.get("ocr_panel_hotkey", {})
        config.ocr_panel_hotkey = OCRPanelHotkeyConfig(
            enabled=ocr_panel_hotkey.get("enabled", False),
            modifier=ocr_panel_hotkey.get("modifier", "alt"),
            key=ocr_panel_hotkey.get("key", "o"),
        )

        spotlight_hotkey = data.get("spotlight_hotkey", {})
        config.spotlight_hotkey = SpotlightHotkeyConfig(
            enabled=spotlight_hotkey.get("enabled", False),
            modifier=spotlight_hotkey.get("modifier", "alt"),
            key=spotlight_hotkey.get("key", "s"),
        )

        mouse_highlight_hotkey = data.get("mouse_highlight_hotkey", {})
        config.mouse_highlight_hotkey = MouseHighlightHotkeyConfig(
            enabled=mouse_highlight_hotkey.get("enabled", False),
            modifier=mouse_highlight_hotkey.get("modifier", "alt"),
            key=mouse_highlight_hotkey.get("key", "m"),
        )

        # 截图状态恢复快捷键配置
        # Feature: screenshot-state-restore
        state_restore_hotkey = data.get("state_restore_hotkey", {})
        config.state_restore_hotkey = StateRestoreHotkeyConfig(
            enabled=state_restore_hotkey.get("enabled", True),
            modifier=state_restore_hotkey.get("modifier", "alt"),
            key=state_restore_hotkey.get("key", "r"),
        )

        # 主窗口配置
        main_window = data.get("main_window", {})
        config.main_window = MainWindowConfig(
            show_welcome=main_window.get("show_welcome", True),
            window_x=main_window.get("window_x", -1),
            window_y=main_window.get("window_y", -1),
            window_width=main_window.get("window_width", 900),
            window_height=main_window.get("window_height", 650),
            show_on_startup=main_window.get("show_on_startup", True),
        )

        # 极简工具栏配置
        # Feature: mini-toolbar
        mini_toolbar = data.get("mini_toolbar", {})
        config.mini_toolbar = MiniToolbarConfig(
            window_x=mini_toolbar.get("window_x", -1),
            window_y=mini_toolbar.get("window_y", -1),
            is_pinned=mini_toolbar.get("is_pinned", False),
            last_mode=mini_toolbar.get("last_mode", "main"),
        )

        # 分屏窗口状态配置
        # Feature: screenshot-ocr-split-view
        split_window_state = data.get("split_window_state", {})
        if split_window_state:
            config.split_window_state = SplitWindowState.from_dict(split_window_state)
        else:
            config.split_window_state = SplitWindowState()

        # 系统工具配置
        # Feature: system-tools
        system_tools = data.get("system_tools", {})
        config.system_tools = SystemToolsConfig(
            alarms=system_tools.get("alarms", []),
            pomodoro_work_minutes=system_tools.get("pomodoro_work_minutes", 25),
            pomodoro_short_break_minutes=system_tools.get("pomodoro_short_break_minutes", 5),
            pomodoro_long_break_minutes=system_tools.get("pomodoro_long_break_minutes", 15),
            speed_test_history=system_tools.get("speed_test_history", []),
        )

        # 安装路径（用于全量更新时覆盖安装到原路径）
        config.install_path = data.get("install_path", "")

        # OCR 预处理配置（带参数验证）
        preprocessing = data.get("preprocessing", {})
        if not isinstance(preprocessing, dict):
            preprocessing = {}
        
        # 验证并规范化预处理参数
        def _clamp(value, min_val, max_val, default):
            """限制值在范围内"""
            if not isinstance(value, (int, float)):
                return default
            return max(min_val, min(max_val, float(value)))
        
        config.preprocessing = {
            "enabled": bool(preprocessing.get("enabled", True)),
            "contrast_enhancement": bool(preprocessing.get("contrast_enhancement", True)),
            "sharpening": bool(preprocessing.get("sharpening", False)),  # 默认关闭
            "binarization": bool(preprocessing.get("binarization", False)),
            "use_otsu": bool(preprocessing.get("use_otsu", False)),
            "denoise": bool(preprocessing.get("denoise", False)),
            "clahe_clip_limit": _clamp(preprocessing.get("clahe_clip_limit", 2.0), 1.0, 4.0, 2.0),
            "clahe_grid_size": int(_clamp(preprocessing.get("clahe_grid_size", 8), 4, 16, 8)),
            "sharpen_strength": _clamp(preprocessing.get("sharpen_strength", 1.0), 0.0, 2.0, 1.0),
            # 扁平图像处理配置
            "auto_upscale": bool(preprocessing.get("auto_upscale", True)),
            "min_height": int(_clamp(preprocessing.get("min_height", 32), 8, 128, 32)),
            "target_height": int(_clamp(preprocessing.get("target_height", 300), 32, 600, 300)),
            "max_aspect_ratio": _clamp(preprocessing.get("max_aspect_ratio", 5.0), 2.0, 50.0, 5.0),
            "extreme_aspect_ratio": _clamp(preprocessing.get("extreme_aspect_ratio", 6.0), 4.0, 100.0, 6.0),
            "extreme_target_height": int(_clamp(preprocessing.get("extreme_target_height", 600), 100, 800, 600)),
            "upscale_sharpen": bool(preprocessing.get("upscale_sharpen", True)),
            "padding_enabled": bool(preprocessing.get("padding_enabled", True)),
            "padding_size": int(_clamp(preprocessing.get("padding_size", 30), 0, 50, 30)),
            # 低对比度模式
            "low_contrast_mode": bool(preprocessing.get("low_contrast_mode", True)),
            "low_contrast_threshold": _clamp(preprocessing.get("low_contrast_threshold", 0.4), 0.1, 0.8, 0.4),
        }
        
        return config
    
    def __eq__(self, other):
        """比较两个配置是否相等"""
        if not isinstance(other, AppConfig):
            return False
        return self.to_dict() == other.to_dict()


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认自动检测：
                - 打包环境：EXE 所在目录/config.json
                - 开发环境：~/.screenshot_tool/config.json
        """
        if config_path is None:
            if is_portable_mode():
                # 便携模式：使用 EXE 所在目录
                config_path = get_portable_config_path()
            else:
                # 开发环境：使用用户目录
                config_dir = os.path.expanduser("~/.screenshot_tool")
                config_path = os.path.join(config_dir, "config.json")
        
        self.config_path = config_path
        self.config = AppConfig()
    
    def load(self) -> AppConfig:
        """
        加载配置文件
        
        Returns:
            AppConfig: 加载的配置对象
        """
        if not os.path.exists(self.config_path):
            # 配置文件不存在，使用默认配置
            self.config = AppConfig()
            return self.config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            self.config = AppConfig.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            # 配置文件损坏或无法读取，使用默认配置
            print(f"[Warning] 加载配置文件失败: {e}")
            self.config = AppConfig()
        
        return self.config
    
    def save(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 是否保存成功
        """
        try:
            # 确保目录存在
            config_dir = os.path.dirname(self.config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            # 写入配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
            
            return True
        except IOError as e:
            print(f"[Error] 保存配置文件失败: {e}")
            return False
    
    def reset_to_defaults(self):
        """重置为默认配置"""
        self.config = AppConfig()
    
    def get_config(self) -> AppConfig:
        """获取当前配置"""
        return self.config
    
    def set_config(self, config: AppConfig):
        """设置配置"""
        self.config = config
    
    # ========================= 便捷方法 =========================
    
    def get_save_path(self) -> str:
        """获取保存路径"""
        return self.config.save_path
    
    def set_save_path(self, path: str):
        """设置保存路径"""
        self.config.save_path = path
    
    def get_ocr_api_url(self) -> str:
        """获取OCR API URL"""
        return self.config.ocr_api_url
    
    def set_ocr_api_url(self, url: str):
        """设置OCR API URL"""
        self.config.ocr_api_url = url
    
    def get_ocr_language(self) -> str:
        """获取OCR语言"""
        return self.config.ocr_language
    
    def set_ocr_language(self, language: str):
        """设置OCR语言"""
        self.config.ocr_language = language
    
    def get_anki_url(self) -> str:
        """获取Anki连接URL"""
        return f"http://{self.config.anki_host}:{self.config.anki_port}"
    
    def get_highlight_color(self) -> str:
        """获取高亮颜色"""
        return self.config.highlight_color
    
    def set_highlight_color(self, color: str):
        """设置高亮颜色"""
        self.config.highlight_color = color
    
    def get_highlight_opacity(self) -> float:
        """获取高亮透明度"""
        return self.config.highlight_opacity
    
    def set_highlight_opacity(self, opacity: float):
        """设置高亮透明度"""
        self.config.highlight_opacity = max(0.0, min(1.0, opacity))
    
    def get_draw_color(self) -> str:
        """获取绘制颜色"""
        return self.config.draw_color
    
    def set_draw_color(self, color: str):
        """设置绘制颜色"""
        self.config.draw_color = color
    
    def get_tool_color(self, tool_name: str) -> str:
        """获取指定工具的颜色
        
        Args:
            tool_name: 工具名称 (rect, ellipse, arrow, line, pen, marker, text, mosaic)
            
        Returns:
            颜色值（十六进制字符串）
        """
        return getattr(self.config.tool_colors, tool_name, "#FF0000")
    
    def set_tool_color(self, tool_name: str, color: str):
        """设置指定工具的颜色
        
        Args:
            tool_name: 工具名称 (rect, ellipse, arrow, line, pen, marker, text, mosaic)
            color: 颜色值（十六进制字符串）
        """
        if hasattr(self.config.tool_colors, tool_name):
            # 验证颜色有效性
            if ToolColorsConfig.is_valid_color(color):
                setattr(self.config.tool_colors, tool_name, color)
    
    def get_all_tool_colors(self) -> dict:
        """获取所有工具的颜色配置
        
        Returns:
            工具名称到颜色的映射字典
        """
        return {
            "rect": self.config.tool_colors.rect,
            "ellipse": self.config.tool_colors.ellipse,
            "arrow": self.config.tool_colors.arrow,
            "line": self.config.tool_colors.line,
            "pen": self.config.tool_colors.pen,
            "marker": self.config.tool_colors.marker,
            "text": self.config.tool_colors.text,
            "mosaic": self.config.tool_colors.mosaic,
        }
    
    def get_tool_width(self, tool_name: str) -> int:
        """获取指定工具的粗细
        
        Args:
            tool_name: 工具名称 (rect, ellipse, arrow, line, pen, marker, text, mosaic)
            
        Returns:
            粗细级别（1-10）
        """
        return getattr(self.config.tool_widths, tool_name, 2)
    
    def set_tool_width(self, tool_name: str, width: int):
        """设置指定工具的粗细
        
        Args:
            tool_name: 工具名称 (rect, ellipse, arrow, line, pen, marker, text, mosaic)
            width: 粗细级别（1-10）
        """
        if hasattr(self.config.tool_widths, tool_name):
            # 验证粗细有效性
            if ToolWidthsConfig.is_valid_width(width):
                setattr(self.config.tool_widths, tool_name, width)
    
    def get_all_tool_widths(self) -> dict:
        """获取所有工具的粗细配置
        
        Returns:
            工具名称到粗细的映射字典
        """
        return {
            "rect": self.config.tool_widths.rect,
            "ellipse": self.config.tool_widths.ellipse,
            "arrow": self.config.tool_widths.arrow,
            "line": self.config.tool_widths.line,
            "pen": self.config.tool_widths.pen,
            "marker": self.config.tool_widths.marker,
            "text": self.config.tool_widths.text,
            "mosaic": self.config.tool_widths.mosaic,
        }
    
    def get_window_geometry(self) -> tuple:
        """获取窗口几何信息"""
        return (
            self.config.window_x,
            self.config.window_y,
            self.config.window_width,
            self.config.window_height,
        )
    
    def set_window_geometry(self, x: int, y: int, width: int, height: int):
        """设置窗口几何信息"""
        self.config.window_x = x
        self.config.window_y = y
        self.config.window_width = width
        self.config.window_height = height

    def get_auto_start(self) -> bool:
        """获取开机自启动设置"""
        return self.config.auto_start
    
    def set_auto_start(self, enabled: bool):
        """设置开机自启动
        
        Args:
            enabled: 是否开启开机自启动
        """
        self.config.auto_start = enabled

    def get_always_ocr_on_screenshot(self) -> bool:
        """获取截图时始终OCR设置"""
        return self.config.always_ocr_on_screenshot
    
    def set_always_ocr_on_screenshot(self, enabled: bool):
        """设置截图时始终OCR
        
        Args:
            enabled: 是否截图时始终开启OCR
        """
        self.config.always_ocr_on_screenshot = enabled

    # ========================= 通知设置便捷方法 =========================
    
    def get_notification_config(self) -> 'NotificationConfig':
        """获取通知配置"""
        return self.config.notification
    
    def set_notification_startup(self, enabled: bool):
        """设置启动通知"""
        self.config.notification.startup = bool(enabled)
    
    def set_notification_screenshot_save(self, enabled: bool):
        """设置截图保存通知"""
        self.config.notification.screenshot_save = bool(enabled)
    
    def set_notification_ding(self, enabled: bool):
        """设置贴图通知"""
        self.config.notification.ding = bool(enabled)
    
    def set_notification_anki(self, enabled: bool):
        """设置 Anki 导入通知"""
        self.config.notification.anki = bool(enabled)
    
    def set_notification_gongwen(self, enabled: bool):
        """设置公文格式化通知"""
        self.config.notification.gongwen = bool(enabled)
    
    def set_notification_hotkey_update(self, enabled: bool):
        """设置快捷键更新通知"""
        self.config.notification.hotkey_update = bool(enabled)
    
    def get_anki_notification_enabled(self) -> bool:
        """获取 Anki 导入通知开关（向后兼容方法）"""
        return self.config.notification.anki

    def set_notification_software_update(self, enabled: bool):
        """设置软件版本更新通知"""
        self.config.notification.software_update = bool(enabled)
    
    def get_notification_software_update(self) -> bool:
        """获取软件版本更新通知开关"""
        return self.config.notification.software_update

    # ========================= 软件更新便捷方法 =========================
    
    def get_update_config(self) -> 'UpdateConfig':
        """获取更新配置"""
        return self.config.update
    
    def set_update_auto_download_enabled(self, enabled: bool):
        """设置自动后台下载新版本开关
        
        Args:
            enabled: 是否开启自动后台下载
        """
        self.config.update.auto_download_enabled = bool(enabled)
    
    def get_update_auto_download_enabled(self) -> bool:
        """获取自动后台下载新版本开关"""
        return self.config.update.auto_download_enabled
    
    def set_update_last_check_time(self):
        """更新上次检查时间为当前时间"""
        self.config.update.update_last_check_time()
    
    def should_auto_check_update(self) -> bool:
        """判断是否应该进行自动检查更新
        
        Returns:
            bool: 如果距离上次检查超过间隔时间，返回 True
        """
        return self.config.update.should_check()
    
    def set_update_skip_version(self, version: str):
        """设置跳过的版本
        
        Args:
            version: 要跳过的版本号
        """
        self.config.update.skip_version = version if version else ""
    
    def get_update_skip_version(self) -> str:
        """获取跳过的版本"""
        return self.config.update.skip_version
    
    def set_update_last_notified_version(self, version: str):
        """设置上次通知的版本
        
        Args:
            version: 上次通知的版本号
        """
        self.config.update.last_notified_version = version if version else ""
    
    def get_update_last_notified_version(self) -> str:
        """获取上次通知的版本"""
        return self.config.update.last_notified_version
    
    def set_last_run_version(self, version: str):
        """设置上次运行的版本号
        
        Args:
            version: 上次运行的版本号
        """
        self.config.update.last_run_version = version if version else ""
    
    def get_last_run_version(self) -> str:
        """获取上次运行的版本号"""
        return self.config.update.last_run_version
    
    def get_github_repo(self) -> str:
        """获取 GitHub 仓库地址"""
        return self.config.update.github_repo
    
    def get_use_proxy(self) -> bool:
        """获取是否使用 GitHub 加速代理"""
        return self.config.update.use_proxy
    
    def set_use_proxy(self, enabled: bool) -> None:
        """设置是否使用 GitHub 加速代理"""
        self.config.update.use_proxy = enabled
    
    def get_proxy_url(self) -> str:
        """获取 GitHub 加速代理地址"""
        return self.config.update.proxy_url
    
    def set_proxy_url(self, url: str) -> None:
        """设置 GitHub 加速代理地址"""
        self.config.update.proxy_url = url if url else "https://ghproxy.net/"

    # ========================= 安装路径管理方法 =========================
    # Feature: fullupdate-inplace-install
    # Requirements: 1.1, 1.2, 1.3, 1.4
    
    def get_install_path(self) -> str:
        """获取安装路径
        
        Returns:
            安装路径字符串，如果未设置则返回空字符串
        """
        return self.config.install_path
    
    def set_install_path(self, path: str) -> None:
        """设置安装路径
        
        Args:
            path: 安装目录路径
        """
        self.config.install_path = path if path else ""
    
    def detect_and_save_install_path(self) -> str:
        """检测并保存安装路径（首次启动时调用）
        
        检测当前可执行文件所在目录，并保存到配置中。
        如果已有保存的路径且有效，则不覆盖。
        
        Feature: fullupdate-inplace-install
        Requirements: 1.1, 1.2
        
        Returns:
            检测到的安装路径
        """
        # 如果已有有效的安装路径，直接返回
        current_path = self.config.install_path
        if current_path and os.path.isdir(current_path):
            return current_path
        
        # 检测当前可执行文件所在目录
        if getattr(sys, 'frozen', False):
            # 打包环境：使用 EXE 所在目录
            exe_path = sys.executable
            install_dir = os.path.dirname(exe_path)
        else:
            # 开发环境：使用项目根目录
            install_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 保存到配置
        self.config.install_path = install_dir
        return install_dir
    
    def validate_install_path(self) -> str:
        """验证安装路径，不存在则更新为当前目录
        
        Feature: fullupdate-inplace-install
        Requirements: 1.3, 1.4
        
        Returns:
            验证后的安装路径
        """
        current_path = self.config.install_path
        
        # 如果路径存在且有效，直接返回
        if current_path and os.path.isdir(current_path):
            return current_path
        
        # 路径不存在，更新为当前可执行文件目录
        return self.detect_and_save_install_path()
