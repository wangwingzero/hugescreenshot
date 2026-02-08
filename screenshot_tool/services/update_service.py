# =====================================================
# =============== 软件更新服务 ===============
# =====================================================

"""
软件更新服务 - 提供版本检查、下载和安装功能

Feature: auto-update
Requirements: 1.1, 1.2, 1.3, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.7, 6.1, 6.2
"""

import os
import re
import sys
import shutil
import threading
import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, TYPE_CHECKING
from pathlib import Path

import requests
from PySide6.QtCore import QObject, Signal, Qt

from screenshot_tool import __version__
from screenshot_tool.core.async_logger import async_debug_log

# 增量更新相关导入（延迟导入以避免循环依赖）
# from screenshot_tool.services.manifest_service import Manifest, DeltaCalculator, ManifestGenerator

# 类型检查时导入（避免循环依赖）
if TYPE_CHECKING:
    from screenshot_tool.services.manifest_service import DeltaResult
# from screenshot_tool.services.delta_updater import DeltaUpdater, verify_installation_integrity


# ========== GitHub 代理列表 ==========

# 可用的 GitHub 加速代理列表（按速度排序，打包前根据 下载测速/result.json 更新）
# 下载时按顺序尝试，失败后自动切换下一个
GITHUB_PROXIES = [
    "https://ghproxy.net/",
    "https://ghfast.top/",
    "https://ghproxy.cc/",
    "https://cf.ghproxy.cc/",
    "https://ghps.cc/",
    "https://gh-proxy.com/",
    "https://github.moeyy.xyz/",
    "https://gh.ddlc.top/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
]


# ========== 下载状态枚举 ==========

from enum import Enum, auto

class DownloadState(Enum):
    """下载状态枚举
    
    Feature: embedded-download-progress
    Requirements: 3.2
    """
    IDLE = auto()        # 空闲，未开始下载
    DOWNLOADING = auto() # 下载中
    COMPLETED = auto()   # 下载完成
    FAILED = auto()      # 下载失败
    CANCELLED = auto()   # 下载已取消


# ========== 数据类 ==========

@dataclass
class VersionInfo:
    """版本信息
    
    Feature: auto-update
    Requirements: 1.2
    """
    version: str           # 版本号，如 "1.9.1"
    download_url: str      # exe 下载链接
    release_notes: str     # 更新说明
    file_size: int         # 文件大小（字节）
    published_at: str      # 发布时间
    
    def __post_init__(self):
        """验证并规范化数据"""
        if self.version is None:
            self.version = ""
        if self.download_url is None:
            self.download_url = ""
        if self.release_notes is None:
            self.release_notes = ""
        if self.file_size is None or not isinstance(self.file_size, int):
            self.file_size = 0
        if self.published_at is None:
            self.published_at = ""


@dataclass
class ProxySpeedResult:
    """代理测速结果

    Feature: background-proxy-speed-test
    """
    proxy_url: str          # 代理地址
    response_time: float    # 响应时间（秒），float('inf') 表示失败
    tested_at: float        # 测试时间戳 (time.time())
    is_available: bool      # 是否可用

    def is_expired(self, expire_seconds: float = 300.0) -> bool:
        """检查测速结果是否过期

        Args:
            expire_seconds: 过期时间（秒），默认 5 分钟

        Returns:
            True 如果已过期
        """
        return time.time() - self.tested_at > expire_seconds


@dataclass
class ProxySpeedCache:
    """代理测速结果缓存

    线程安全的缓存类，支持并发读写。

    Feature: background-proxy-speed-test
    """
    results: Dict[str, ProxySpeedResult] = field(default_factory=dict)
    is_testing: bool = False  # 是否正在测速
    test_version: str = ""    # 测速对应的版本号

    def __post_init__(self):
        """初始化线程锁"""
        self._lock = threading.Lock()

    def set_result(self, proxy_url: str, result: ProxySpeedResult) -> None:
        """线程安全地设置测速结果

        Args:
            proxy_url: 代理地址
            result: 测速结果
        """
        with self._lock:
            self.results[proxy_url] = result

    def get_sorted_proxies(self) -> List[str]:
        """获取按速度排序的代理列表（快到慢）

        Returns:
            排序后的代理地址列表
        """
        with self._lock:
            available = [r for r in self.results.values() if r.is_available and not r.is_expired()]
        available.sort(key=lambda x: x.response_time)
        return [r.proxy_url for r in available]

    def get_fastest_proxy(self) -> Optional[str]:
        """获取最快的可用代理

        Returns:
            最快代理地址，如果没有可用代理返回 None
        """
        sorted_proxies = self.get_sorted_proxies()
        return sorted_proxies[0] if sorted_proxies else None

    def is_valid(self, version: str) -> bool:
        """检查缓存是否有效（版本匹配且未过期）

        Args:
            version: 版本号

        Returns:
            True 如果缓存有效
        """
        with self._lock:
            if self.test_version != version:
                return False
            return any(not r.is_expired() for r in self.results.values() if r.is_available)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self.results.clear()
            self.is_testing = False
            self.test_version = ""

    def set_testing(self, testing: bool, version: str = "") -> None:
        """线程安全地设置测速状态

        Args:
            testing: 是否正在测速
            version: 测速的版本号（仅在 testing=True 时使用）
        """
        with self._lock:
            self.is_testing = testing
            if testing and version:
                self.test_version = version
                self.results.clear()


# ========== 版本检查器 ==========

class VersionChecker:
    """版本检查器 - 调用 GitHub API 获取最新版本信息
    
    Feature: auto-update
    Requirements: 1.2, 1.3, 1.7
    """
    
    # GitHub API 基础 URL
    GITHUB_API_BASE = "https://api.github.com"
    
    # 请求超时（秒）
    REQUEST_TIMEOUT = 30
    
    # User-Agent（GitHub API 要求）
    USER_AGENT = "HuGeScreenshot-UpdateChecker"
    
    @staticmethod
    def parse_version(version_str: str) -> Tuple[int, int, int]:
        """解析版本号为 (major, minor, patch) 元组
        
        支持格式：
        - "1.9.0"
        - "v1.9.0"
        - "1.9.0-beta"（忽略后缀）
        
        Args:
            version_str: 版本号字符串
            
        Returns:
            (major, minor, patch) 元组
            
        Raises:
            ValueError: 版本号格式无效
            
        Feature: auto-update
        Requirements: 1.7
        """
        if not version_str:
            raise ValueError("版本号不能为空")
        
        # 去除 'v' 前缀
        version_str = version_str.strip()
        if version_str.lower().startswith('v'):
            version_str = version_str[1:]
        
        # 去除后缀（如 -beta, -rc1）
        version_str = version_str.split('-')[0]
        
        # 解析版本号
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)', version_str)
        if not match:
            raise ValueError(f"无效的版本号格式: {version_str}")
        
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    
    @staticmethod
    def compare_versions(current: str, latest: str) -> int:
        """比较两个版本号
        
        Args:
            current: 当前版本号
            latest: 最新版本号
            
        Returns:
            -1: current < latest（有新版本）
             0: current == latest（已是最新）
             1: current > latest（当前版本更新）
             
        Feature: auto-update
        Requirements: 1.3, 1.7
        """
        try:
            current_tuple = VersionChecker.parse_version(current)
            latest_tuple = VersionChecker.parse_version(latest)
        except ValueError:
            # 解析失败时返回 0（视为相等）
            return 0
        
        if current_tuple < latest_tuple:
            return -1
        elif current_tuple > latest_tuple:
            return 1
        else:
            return 0
    
    @staticmethod
    def is_newer_version(current: str, latest: str) -> bool:
        """检查是否有新版本
        
        Args:
            current: 当前版本号
            latest: 最新版本号
            
        Returns:
            True 如果 latest 比 current 新
            
        Feature: auto-update
        Requirements: 1.3
        """
        return VersionChecker.compare_versions(current, latest) == -1
    
    def get_latest_version(self, repo: str, use_proxy: bool = False, proxy_url: str = "") -> Optional[VersionInfo]:
        """获取最新版本信息
        
        Args:
            repo: GitHub 仓库，格式为 "owner/repo"
            use_proxy: 是否使用代理
            proxy_url: 代理地址（如 https://ghproxy.com/）
            
        Returns:
            VersionInfo 对象，如果获取失败返回 None
            
        Feature: auto-update
        Requirements: 1.2, 6.1, 6.2
        """
        url = f"{self.GITHUB_API_BASE}/repos/{repo}/releases/latest"
        
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        }
        
        try:
            response = requests.get(
                url, 
                headers=headers, 
                timeout=self.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()
            return self._parse_release_response(data, use_proxy, proxy_url)
            
        except requests.exceptions.Timeout:
            raise UpdateError("网络连接超时，请检查网络")
        except requests.exceptions.ConnectionError:
            raise UpdateError("无法连接到更新服务器")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise UpdateError("未找到发布版本")
            elif e.response.status_code == 403:
                raise UpdateError("请求过于频繁，请稍后重试")
            else:
                raise UpdateError(f"服务器错误: {e.response.status_code}")
        except Exception as e:
            raise UpdateError(f"获取版本信息失败: {str(e)}")
    
    def _parse_release_response(self, data: dict, use_proxy: bool = False, proxy_url: str = "") -> VersionInfo:
        """解析 GitHub Release API 响应
        
        Args:
            data: API 响应 JSON 数据
            use_proxy: 是否使用代理
            proxy_url: 代理地址
            
        Returns:
            VersionInfo 对象
        """
        # 提取版本号（去除 'v' 前缀）
        tag_name = data.get("tag_name", "")
        version = tag_name.lstrip('v') if tag_name else ""
        
        # 提取更新说明
        release_notes = data.get("body", "") or ""
        
        # 提取发布时间
        published_at = data.get("published_at", "")
        
        # 查找 exe 文件
        download_url = ""
        file_size = 0
        
        assets = data.get("assets", [])
        for asset in assets:
            name = asset.get("name", "")
            # 查找 exe 文件（支持多种命名格式）
            if name.endswith(".exe"):
                download_url = asset.get("browser_download_url", "")
                file_size = asset.get("size", 0)
                break
        
        # 如果启用代理，转换下载链接
        if use_proxy and proxy_url and download_url:
            # ghproxy.com 格式: https://ghproxy.com/https://github.com/...
            download_url = f"{proxy_url.rstrip('/')}/{download_url}"
        
        return VersionInfo(
            version=version,
            download_url=download_url,
            release_notes=release_notes,
            file_size=file_size,
            published_at=published_at,
        )


# ========== 下载管理器 ==========

def extract_original_url(proxied_url: str) -> str:
    """从代理 URL 中提取原始 GitHub URL
    
    Args:
        proxied_url: 代理后的 URL，如 https://ghfast.top/https://github.com/...
        
    Returns:
        原始 GitHub URL，如 https://github.com/...
    """
    # 查找 https://github.com 的位置
    github_prefix = "https://github.com"
    idx = proxied_url.find(github_prefix)
    if idx > 0:
        return proxied_url[idx:]
    return proxied_url


class DownloadManager(QObject):
    """下载管理器 - 处理文件下载，支持代理自动切换
    
    Feature: auto-update
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
    """
    
    # 信号
    progress = Signal(int, int, float)  # (downloaded, total, speed_kbps)
    completed = Signal(str)              # (file_path)
    error = Signal(str)                  # (error_message)
    proxy_switched = Signal(str)         # (new_proxy) 代理切换通知
    
    # 下载块大小
    CHUNK_SIZE = 8192
    
    # 请求超时（元组格式：连接超时, 读取超时）
    CONNECT_TIMEOUT = 30  # 连接超时（秒）
    READ_TIMEOUT = 120    # 读取超时（秒），增加到 120 秒以适应慢速网络
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel_flag = False
        self._download_thread: Optional[threading.Thread] = None
        self._temp_file: Optional[str] = None
        self._failed_proxies: List[str] = []  # 记录失败的代理
        self._proxy_speed_cache: Optional[ProxySpeedCache] = None  # 测速缓存

    def set_proxy_speed_cache(self, cache: ProxySpeedCache) -> None:
        """设置代理测速缓存，用于智能切换代理

        Args:
            cache: 测速结果缓存
        """
        self._proxy_speed_cache = cache

    def start_download(self, url: str, save_path: str) -> None:
        """开始下载，支持代理自动切换重试
        
        Args:
            url: 下载 URL（可能已经是代理后的 URL）
            save_path: 保存路径
            
        Feature: auto-update
        Requirements: 2.1
        """
        self._cancel_flag = False
        self._failed_proxies = []  # 重置失败代理列表
        self._download_thread = threading.Thread(
            target=self._download_with_retry,
            args=(url, save_path),
            daemon=True
        )
        self._download_thread.start()
    
    def cancel_download(self) -> None:
        """取消下载
        
        Feature: auto-update
        Requirements: 2.4
        """
        self._cancel_flag = True
        
        # 清理临时文件
        if self._temp_file and os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except OSError:
                pass
    
    def _get_next_proxy(self, current_url: str) -> Optional[str]:
        """获取下一个可用的代理

        优先使用测速缓存的排序结果，按响应时间从快到慢尝试。

        Args:
            current_url: 当前使用的 URL

        Returns:
            新的代理 URL，如果没有可用代理返回 None
        """
        # 提取原始 GitHub URL
        original_url = extract_original_url(current_url)

        # 找到当前使用的代理
        current_proxy = None
        for proxy in GITHUB_PROXIES:
            if current_url.startswith(proxy):
                current_proxy = proxy
                break

        # 记录当前代理为失败
        if current_proxy and current_proxy not in self._failed_proxies:
            self._failed_proxies.append(current_proxy)

        # 优先使用测速缓存的排序结果
        if self._proxy_speed_cache:
            sorted_proxies = self._proxy_speed_cache.get_sorted_proxies()
            for proxy in sorted_proxies:
                if proxy not in self._failed_proxies:
                    new_url = f"{proxy.rstrip('/')}/{original_url}"
                    async_debug_log(f"[UPDATE] 切换到代理 (测速排序): {proxy}")
                    return new_url

        # 回退到默认顺序
        for proxy in GITHUB_PROXIES:
            if proxy not in self._failed_proxies:
                new_url = f"{proxy.rstrip('/')}/{original_url}"
                async_debug_log(f"[UPDATE] 切换到代理 (默认顺序): {proxy}")
                return new_url

        return None
    
    def _download_with_retry(self, url: str, save_path: str) -> None:
        """带代理重试的下载
        
        如果下载超时或失败，自动切换到其他代理重试
        
        Args:
            url: 下载 URL
            save_path: 保存路径
        """
        current_url = url
        max_retries = len(GITHUB_PROXIES)
        
        for attempt in range(max_retries):
            if self._cancel_flag:
                return
            
            async_debug_log(f"[UPDATE] 下载尝试 {attempt + 1}/{max_retries}: {current_url[:80]}...")
            
            success = self._download_worker(current_url, save_path)
            
            if success or self._cancel_flag:
                return
            
            # 下载失败，尝试切换代理
            next_url = self._get_next_proxy(current_url)
            if next_url:
                current_url = next_url
                # 通知 UI 代理已切换
                for proxy in GITHUB_PROXIES:
                    if current_url.startswith(proxy):
                        self.proxy_switched.emit(proxy)
                        break
                async_debug_log(f"[UPDATE] 代理切换，准备重试...")
            else:
                # 没有更多代理可用
                async_debug_log("[UPDATE] 所有代理均失败")
                self.error.emit("下载超时，请检查网络")
                return
        
        # 所有重试都失败
        self.error.emit("下载失败，已尝试所有可用代理")
    
    def _download_worker(self, url: str, save_path: str) -> bool:
        """下载工作线程
        
        Args:
            url: 下载 URL
            save_path: 保存路径
            
        Returns:
            True 如果下载成功，False 如果失败（可重试）
        
        Feature: auto-update
        Requirements: 2.1, 2.2
        """
        async_debug_log(f"[UPDATE] 开始下载: {url}")
        last_logged_progress = 0  # 用于记录上次日志的进度百分比
        
        try:
            # 确保目录存在
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 使用临时文件
            self._temp_file = save_path + ".downloading"
            
            # 构建请求头
            headers = {"User-Agent": VersionChecker.USER_AGENT}
            
            # 使用元组格式超时：(连接超时, 读取超时)
            response = requests.get(
                url,
                stream=True,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
                headers=headers
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            last_progress_time = start_time
            
            with open(self._temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancel_flag:
                        async_debug_log("[UPDATE] 下载已取消")
                        return True  # 取消时返回 True 阻止重试
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算速度（每 0.5 秒更新一次）
                        current_time = time.time()
                        if current_time - last_progress_time >= 0.5:
                            elapsed = current_time - start_time
                            speed_kbps = (downloaded / 1024) / elapsed if elapsed > 0 else 0
                            self.progress.emit(downloaded, total_size, speed_kbps)
                            last_progress_time = current_time
                            
                            # 每 10% 记录一次日志
                            if total_size > 0:
                                progress_pct = int((downloaded / total_size) * 100)
                                if progress_pct >= last_logged_progress + 10:
                                    async_debug_log(f"[UPDATE] 下载进度: {progress_pct}%")
                                    last_logged_progress = progress_pct
            
            if self._cancel_flag:
                async_debug_log("[UPDATE] 下载已取消")
                return True  # 取消时返回 True 阻止重试
            
            # 重命名为最终文件
            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(self._temp_file, save_path)
            self._temp_file = None
            
            async_debug_log(f"[UPDATE] 下载完成: {save_path}")
            self.completed.emit(save_path)
            return True
            
        except requests.exceptions.Timeout:
            async_debug_log("[UPDATE] 下载错误: 超时，将尝试其他代理")
            # 超时可以重试，不发送 error 信号
            return False
        except requests.exceptions.ConnectionError:
            async_debug_log("[UPDATE] 下载错误: 网络连接失败，将尝试其他代理")
            # 连接错误可以重试
            return False
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 0
            async_debug_log(f"[UPDATE] 下载错误: HTTP {status_code}")
            if status_code in (502, 503, 504):
                # 网关错误可以重试
                return False
            # 其他 HTTP 错误不重试
            self.error.emit(f"下载失败: HTTP {status_code}")
            return True  # 返回 True 阻止重试
        except OSError as e:
            # 磁盘错误不重试
            if "No space left" in str(e) or e.errno == 28:
                async_debug_log("[UPDATE] 下载错误: 磁盘空间不足")
                self.error.emit("磁盘空间不足")
            elif e.errno == 13:
                async_debug_log("[UPDATE] 下载错误: 没有写入权限")
                self.error.emit("没有写入权限")
            else:
                async_debug_log(f"[UPDATE] 下载错误: {str(e)}")
                self.error.emit(f"文件操作失败: {str(e)}")
            return True  # 返回 True 阻止重试
        except Exception as e:
            async_debug_log(f"[UPDATE] 下载错误: {str(e)}")
            # 未知错误尝试重试
            return False
        finally:
            # 确保清理临时文件（下载失败或取消时）
            if self._temp_file and os.path.exists(self._temp_file):
                try:
                    os.remove(self._temp_file)
                    async_debug_log(f"[UPDATE] 清理临时文件: {self._temp_file}")
                except OSError:
                    pass
                self._temp_file = None
    
    @staticmethod
    def verify_file(file_path: str, expected_size: int) -> bool:
        """验证文件完整性
        
        Args:
            file_path: 文件路径
            expected_size: 预期文件大小（字节）
            
        Returns:
            True 如果文件大小匹配
            
        Feature: auto-update
        Requirements: 2.3
        """
        if not os.path.exists(file_path):
            return False
        
        actual_size = os.path.getsize(file_path)
        return actual_size == expected_size
    
    @staticmethod
    def calculate_progress(downloaded: int, total: int) -> float:
        """计算下载进度百分比
        
        Args:
            downloaded: 已下载字节数
            total: 总字节数
            
        Returns:
            进度百分比 (0-100)，不会超过 100
            
        Feature: auto-update
        Requirements: 2.2
        """
        if total <= 0:
            return 0.0
        
        progress = (downloaded / total) * 100
        return min(progress, 100.0)


# ========== 更新执行器 ==========

class UpdateExecutor:
    """更新执行器 - 启动时应用更新
    
    Feature: auto-update
    Requirements: 3.1, 3.2, 3.7
    """
    
    @staticmethod
    def get_current_exe_path() -> str:
        """获取当前 exe 路径
        
        Returns:
            当前 exe 的完整路径
        """
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            # 开发环境返回 Python 解释器路径
            return sys.executable
    
    @staticmethod
    def cleanup_update_files(
        exe_dir: str, 
        current_version: str = "", 
        last_run_version: str = ""
    ) -> int:
        """清理更新临时文件
        
        清理 *.downloading 临时文件
        
        Args:
            exe_dir: exe 所在目录
            current_version: 当前版本号（保留参数以兼容调用）
            last_run_version: 上次运行的版本号（保留参数以兼容调用）
            
        Returns:
            清理的文件数量
            
        Feature: auto-update
        Requirements: 3.7
        """
        cleaned = 0
        
        # 清理临时文件
        for file_path in Path(exe_dir).glob("*.downloading"):
            try:
                file_path.unlink()
                cleaned += 1
                async_debug_log(f"[UPDATE] 清理临时文件: {file_path}")
            except OSError:
                pass
        
        return cleaned
    
    @staticmethod
    def cleanup_old_versions(exe_dir: str = None) -> int:
        """清理旧版本 exe 文件
        
        清理 HuGeScreenshot-*.exe 文件（旧的单文件版本残留）
        无论当前是安装版还是单文件版，都会清理这些文件
        
        Args:
            exe_dir: exe 所在目录
            
        Returns:
            清理的文件数量
        """
        if not getattr(sys, 'frozen', False):
            return 0
        
        current_exe = UpdateExecutor.get_current_exe_path()
        if exe_dir is None:
            exe_dir = os.path.dirname(current_exe)
        
        current_exe_name = os.path.basename(current_exe).lower()
        cleaned = 0
        
        # 查找所有 HuGeScreenshot-*.exe 文件（旧的单文件版本）
        # 安装版主程序是 "虎哥截图.exe"，所以这些都是旧版残留，可以安全删除
        for exe_file in Path(exe_dir).glob("HuGeScreenshot-*.exe"):
            # 跳过当前正在运行的 exe（仅当用户还在用单文件版时）
            if exe_file.name.lower() == current_exe_name:
                continue
            
            # 带重试的删除（解决 PCA 服务锁定问题）
            for attempt in range(3):
                try:
                    exe_file.unlink()
                    cleaned += 1
                    async_debug_log(f"[UPDATE] 清理旧版本: {exe_file}")
                    break
                except OSError as e:
                    if attempt < 2:
                        time.sleep(1)  # 等待 1 秒后重试
                    else:
                        async_debug_log(f"[UPDATE] 无法删除旧版本 {exe_file}: {e}")
        
        # 清理 .downloading 临时文件
        for f in Path(exe_dir).glob("*.downloading"):
            try:
                f.unlink()
                cleaned += 1
                async_debug_log(f"[UPDATE] 清理临时文件: {f}")
            except OSError:
                pass
        
        return cleaned
    
    # ========== 自动重启更新功能 ==========
    # Feature: auto-restart-update
    # Requirements: 1.1, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4
    
    # 命令行参数名
    CLEANUP_ARG = "--cleanup-old"
    
    @staticmethod
    def launch_new_version(new_exe_path: str, old_exe_path: str) -> Tuple[bool, str]:
        """启动新版本并传递旧版本路径
        
        Args:
            new_exe_path: 新版本 exe 路径
            old_exe_path: 旧版本 exe 路径（用于清理）
            
        Returns:
            (success, error_message) 元组
            
        Feature: auto-restart-update
        Requirements: 1.1, 1.3, 1.4
        """
        import subprocess
        
        # 开发环境跳过
        if not getattr(sys, 'frozen', False):
            async_debug_log("[UPDATE] 开发环境，跳过启动新版本")
            return (True, "开发环境跳过")
        
        # 验证新版本文件存在
        if not os.path.exists(new_exe_path):
            return (False, f"新版本文件不存在: {new_exe_path}")
        
        # 验证文件名格式
        new_exe_name = os.path.basename(new_exe_path)
        if not UpdateExecutor.is_valid_exe_name(new_exe_name):
            return (False, f"无效的文件名格式: {new_exe_name}")
        
        try:
            # 构建命令行参数
            cmd = [new_exe_path, UpdateExecutor.CLEANUP_ARG, old_exe_path]
            
            async_debug_log(f"[UPDATE] 启动新版本: {' '.join(cmd)}")
            
            # 启动新进程（独立于当前进程）
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True,
                start_new_session=True
            )
            
            return (True, "")
            
        except OSError as e:
            error_msg = f"启动新版本失败: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            return (False, error_msg)
        except Exception as e:
            error_msg = f"启动新版本时发生错误: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            return (False, error_msg)
    
    @staticmethod
    def parse_cleanup_arg(args: List[str]) -> Optional[str]:
        """解析命令行参数，获取需要清理的旧版本路径
        
        Args:
            args: 命令行参数列表（通常是 sys.argv）
            
        Returns:
            旧版本路径，如果没有则返回 None
            
        Feature: auto-restart-update
        Requirements: 2.1
        """
        try:
            if UpdateExecutor.CLEANUP_ARG in args:
                idx = args.index(UpdateExecutor.CLEANUP_ARG)
                if idx + 1 < len(args):
                    old_path = args[idx + 1]
                    # 验证路径格式
                    if old_path and not old_path.startswith("-"):
                        return old_path
        except (ValueError, IndexError):
            pass
        return None
    
    @staticmethod
    def is_valid_exe_name(filename: str) -> bool:
        """检查文件名是否符合 HuGeScreenshot-*.exe 格式
        
        Args:
            filename: 文件名（不含路径）
            
        Returns:
            是否符合格式
            
        Feature: auto-restart-update
        Requirements: 4.4
        """
        import fnmatch
        return fnmatch.fnmatch(filename.lower(), "hugescreenshot-*.exe")
    
    @staticmethod
    def calculate_backoff_time(attempt: int) -> float:
        """计算指数退避等待时间
        
        Args:
            attempt: 当前尝试次数（从 1 开始）
            
        Returns:
            等待时间（秒），上限 8 秒
            
        Feature: auto-restart-update
        Requirements: 2.2
        """
        # 指数退避：1, 2, 4, 8, 8, 8...
        wait_time = min(2 ** (attempt - 1), 8)
        return float(wait_time)
    
    @staticmethod
    def cleanup_old_version_async(old_exe_path: str, max_wait: int = 60) -> None:
        """异步清理旧版本（后台线程）
        
        在后台线程中尝试删除旧版本 exe，使用指数退避重试。
        
        Args:
            old_exe_path: 旧版本 exe 路径
            max_wait: 最大等待时间（秒），默认 60 秒
            
        Feature: auto-restart-update
        Requirements: 2.2, 2.3, 2.4
        """
        # 开发环境跳过
        if not getattr(sys, 'frozen', False):
            async_debug_log("[UPDATE] 开发环境，跳过清理旧版本")
            return
        
        def cleanup_worker():
            """清理工作线程"""
            # 验证文件名格式
            old_exe_name = os.path.basename(old_exe_path)
            if not UpdateExecutor.is_valid_exe_name(old_exe_name):
                async_debug_log(f"[UPDATE] 跳过清理，文件名不符合格式: {old_exe_name}")
                return
            
            # 验证文件存在
            if not os.path.exists(old_exe_path):
                async_debug_log(f"[UPDATE] 旧版本文件不存在，无需清理: {old_exe_path}")
                return
            
            start_time = time.time()
            attempt = 0
            total_waited = 0.0
            
            while total_waited < max_wait:
                attempt += 1
                
                try:
                    os.remove(old_exe_path)
                    elapsed = time.time() - start_time
                    async_debug_log(
                        f"[UPDATE] 成功删除旧版本: {old_exe_path} "
                        f"(尝试 {attempt} 次, 耗时 {elapsed:.1f}s)"
                    )
                    return
                except OSError as e:
                    # 计算下次等待时间
                    wait_time = UpdateExecutor.calculate_backoff_time(attempt)
                    
                    # 检查是否会超时
                    if total_waited + wait_time > max_wait:
                        wait_time = max_wait - total_waited
                    
                    if wait_time <= 0:
                        break
                    
                    async_debug_log(
                        f"[UPDATE] 删除旧版本失败 (尝试 {attempt}): {e}, "
                        f"等待 {wait_time:.1f}s 后重试"
                    )
                    
                    time.sleep(wait_time)
                    total_waited += wait_time
            
            # 超时，记录警告但不影响程序运行
            async_debug_log(
                f"[UPDATE] 警告: 无法删除旧版本 {old_exe_path}，"
                f"已尝试 {attempt} 次，总等待 {total_waited:.1f}s"
            )
        
        # 启动后台线程
        cleanup_thread = threading.Thread(
            target=cleanup_worker,
            daemon=True,
            name="UpdateCleanupThread"
        )
        cleanup_thread.start()
        async_debug_log(f"[UPDATE] 启动后台清理线程: {old_exe_path}")


# ========== 下载状态管理器 ==========

class DownloadStateManager(QObject):
    """下载状态管理器 - 由主应用持有，确保下载在后台持续进行
    
    Feature: embedded-download-progress
    Requirements: 2.1, 2.5, 3.1
    """
    
    # 信号
    state_changed = Signal(object)  # DownloadState
    progress_updated = Signal(int, int, float)  # downloaded, total, speed
    
    def __init__(self, parent=None):
        """初始化下载状态管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        
        self._state = DownloadState.IDLE
        self._download_manager: Optional[DownloadManager] = None
        self._version_info: Optional[VersionInfo] = None
        self._file_path: str = ""
        self._error_msg: str = ""
        self._downloaded: int = 0
        self._total: int = 0
        self._speed: float = 0.0
    
    @property
    def state(self) -> DownloadState:
        """获取当前下载状态"""
        return self._state
    
    @property
    def progress(self) -> Tuple[int, int, float]:
        """获取当前进度 (downloaded, total, speed)"""
        return (self._downloaded, self._total, self._speed)
    
    @property
    def file_path(self) -> str:
        """获取下载完成的文件路径"""
        return self._file_path
    
    @property
    def error_msg(self) -> str:
        """获取错误信息"""
        return self._error_msg
    
    @property
    def version_info(self) -> Optional[VersionInfo]:
        """获取版本信息"""
        return self._version_info
    
    def start_download(self, version_info: VersionInfo, save_path: str) -> None:
        """开始下载
        
        Args:
            version_info: 版本信息
            save_path: 保存路径
            
        Feature: embedded-download-progress
        Requirements: 2.1
        """
        # 如果已经在下载中，不重复启动
        if self._state == DownloadState.DOWNLOADING:
            return
        
        # 重置状态
        self._version_info = version_info
        self._file_path = save_path
        self._error_msg = ""
        self._downloaded = 0
        self._total = version_info.file_size if version_info else 0
        self._speed = 0.0
        
        # 创建下载管理器
        self._download_manager = DownloadManager(self)
        self._download_manager.progress.connect(self._on_progress)
        self._download_manager.completed.connect(self._on_completed)
        self._download_manager.error.connect(self._on_error)
        
        # 更新状态
        self._state = DownloadState.DOWNLOADING
        self.state_changed.emit(self._state)
        
        # 开始下载
        self._download_manager.start_download(version_info.download_url, save_path)
        async_debug_log(f"[UPDATE] DownloadStateManager: 开始下载 v{version_info.version}")
    
    def cancel_download(self) -> None:
        """取消下载
        
        Feature: embedded-download-progress
        Requirements: 2.4
        """
        if self._state != DownloadState.DOWNLOADING:
            return
        
        if self._download_manager:
            self._download_manager.cancel_download()
        
        self._state = DownloadState.CANCELLED
        self.state_changed.emit(self._state)
        async_debug_log("[UPDATE] DownloadStateManager: 下载已取消")
    
    def reset(self) -> None:
        """重置状态为空闲
        
        Feature: embedded-download-progress
        Requirements: 3.2
        """
        # 如果正在下载，先取消
        if self._state == DownloadState.DOWNLOADING:
            self.cancel_download()
        
        self._state = DownloadState.IDLE
        self._version_info = None
        self._file_path = ""
        self._error_msg = ""
        self._downloaded = 0
        self._total = 0
        self._speed = 0.0
        self._download_manager = None
        
        self.state_changed.emit(self._state)
        async_debug_log("[UPDATE] DownloadStateManager: 状态已重置")
    
    def _on_progress(self, downloaded: int, total: int, speed: float) -> None:
        """处理下载进度"""
        self._downloaded = downloaded
        self._total = total
        self._speed = speed
        self.progress_updated.emit(downloaded, total, speed)
    
    def _on_completed(self, file_path: str) -> None:
        """处理下载完成"""
        self._file_path = file_path
        self._state = DownloadState.COMPLETED
        self.state_changed.emit(self._state)
        async_debug_log(f"[UPDATE] DownloadStateManager: 下载完成 {file_path}")
    
    def _on_error(self, error_msg: str) -> None:
        """处理下载错误"""
        self._error_msg = error_msg
        self._state = DownloadState.FAILED
        self.state_changed.emit(self._state)
        async_debug_log(f"[UPDATE] DownloadStateManager: 下载失败 {error_msg}")


# ========== 后台代理测速器 ==========

class ProxySpeedTester(QObject):
    """后台代理测速器

    在发现新版本后，后台对所有下载代理进行测速，
    结果缓存供下载时直接使用。

    Feature: background-proxy-speed-test
    """

    # 信号
    speed_test_completed = Signal(object)  # ProxySpeedCache
    speed_test_progress = Signal(str, float)  # (proxy_url, response_time)

    # 测速配置
    TEST_TIMEOUT = 8.0       # 单个代理超时时间（秒）
    CACHE_EXPIRE = 300.0     # 缓存过期时间（秒，5 分钟）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = ProxySpeedCache()
        self._test_thread: Optional[threading.Thread] = None
        self._cancel_flag = False

    @property
    def cache(self) -> ProxySpeedCache:
        """获取测速缓存"""
        return self._cache

    @property
    def is_testing(self) -> bool:
        """是否正在测速"""
        return self._cache.is_testing

    def start_speed_test(self, download_url: str, version: str) -> None:
        """启动后台测速

        Args:
            download_url: 原始下载 URL（可能已带代理前缀）
            version: 版本号（用于缓存关联）
        """
        if self._cache.is_testing:
            async_debug_log("[PROXY_TEST] 测速已在进行中，跳过")
            return

        # 检查缓存是否有效
        if self._cache.is_valid(version):
            async_debug_log(f"[PROXY_TEST] 缓存有效，跳过测速 (v{version})")
            self.speed_test_completed.emit(self._cache)
            return

        self._cancel_flag = False
        self._cache.set_testing(True, version)

        # 提取原始 GitHub URL
        original_url = extract_original_url(download_url)

        self._test_thread = threading.Thread(
            target=self._speed_test_worker,
            args=(original_url,),
            daemon=True,
            name="ProxySpeedTestThread"
        )
        self._test_thread.start()
        async_debug_log(f"[PROXY_TEST] 启动后台测速 (v{version})")

    def cancel(self) -> None:
        """取消测速"""
        self._cancel_flag = True

    def _speed_test_worker(self, test_url: str) -> None:
        """测速工作线程

        并发测试所有代理的响应时间

        Args:
            test_url: 用于测试的原始 GitHub URL
        """
        def test_single_proxy(proxy_url: str) -> ProxySpeedResult:
            """测试单个代理"""
            try:
                full_url = f"{proxy_url.rstrip('/')}/{test_url}"
                start_time = time.time()
                response = requests.head(
                    full_url,
                    timeout=self.TEST_TIMEOUT,
                    allow_redirects=True
                )
                elapsed = time.time() - start_time
                is_available = response.status_code < 400
                return ProxySpeedResult(
                    proxy_url=proxy_url,
                    response_time=elapsed if is_available else float('inf'),
                    tested_at=time.time(),
                    is_available=is_available
                )
            except Exception as e:
                async_debug_log(f"[PROXY_TEST] {proxy_url} 测试失败: {e}")
                return ProxySpeedResult(
                    proxy_url=proxy_url,
                    response_time=float('inf'),
                    tested_at=time.time(),
                    is_available=False
                )

        try:
            # 并发测试所有代理
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(GITHUB_PROXIES)) as executor:
                futures = {
                    executor.submit(test_single_proxy, proxy): proxy
                    for proxy in GITHUB_PROXIES
                }

                for future in concurrent.futures.as_completed(futures, timeout=self.TEST_TIMEOUT + 2):
                    if self._cancel_flag:
                        break

                    try:
                        result = future.result()
                        self._cache.set_result(result.proxy_url, result)

                        # 发送进度信号
                        self.speed_test_progress.emit(result.proxy_url, result.response_time)

                        if result.is_available:
                            async_debug_log(
                                f"[PROXY_TEST] {result.proxy_url} 响应时间: {result.response_time:.2f}s"
                            )
                    except Exception:
                        pass

            # 输出排序结果
            sorted_proxies = self._cache.get_sorted_proxies()
            if sorted_proxies:
                async_debug_log(f"[PROXY_TEST] 测速完成，最快代理: {sorted_proxies[0]}")
            else:
                async_debug_log("[PROXY_TEST] 测速完成，无可用代理")

        except Exception as e:
            async_debug_log(f"[PROXY_TEST] 测速异常: {e}")
        finally:
            self._cache.set_testing(False)
            self.speed_test_completed.emit(self._cache)

    def get_best_download_url(self, original_url: str) -> str:
        """获取最佳下载 URL（使用缓存的最快代理）

        Args:
            original_url: 原始 GitHub 下载 URL

        Returns:
            带代理前缀的下载 URL
        """
        fastest = self._cache.get_fastest_proxy()
        if fastest:
            return f"{fastest.rstrip('/')}/{original_url}"

        # 无缓存或全部失败，返回默认代理
        return f"{GITHUB_PROXIES[0].rstrip('/')}/{original_url}"


# ========== 更新错误 ==========

class UpdateError(Exception):
    """更新错误
    
    Feature: auto-update
    Requirements: 6.1, 6.2
    """
    pass


# ========== 更新服务 ==========

class UpdateService(QObject):
    """更新服务 - 协调版本检查、下载和安装
    
    Feature: auto-update
    Requirements: 1.1, 1.4, 2.1, 3.1
    """
    
    # 信号
    update_available = Signal(object)     # 发现新版本 (VersionInfo)
    update_progress = Signal(int, int, float)  # 下载进度 (downloaded, total, speed)
    update_completed = Signal(str)        # 更新完成 (new_version)
    update_error = Signal(str)            # 更新错误 (error_message)
    check_completed = Signal(bool, object)  # 检查完成 (has_update, VersionInfo or None)
    proxy_speed_test_completed = Signal(object)  # 代理测速完成 (ProxySpeedCache)
    
    # 启动后延迟检查时间（秒）
    STARTUP_CHECK_DELAY = 10
    
    def __init__(self, config_manager=None, parent=None):
        """初始化更新服务
        
        Args:
            config_manager: 配置管理器实例
            parent: 父对象
        """
        super().__init__(parent)
        
        self._config_manager = config_manager
        self._version_checker = VersionChecker()
        self._download_manager = DownloadManager(self)
        self._update_executor = UpdateExecutor()
        
        # 状态
        self._latest_version_info: Optional[VersionInfo] = None
        self._downloaded_file: Optional[str] = None
        self._is_checking = False
        self._is_downloading = False
        self._notified_this_session = False  # 本次会话是否已通知

        # 后台代理测速器
        self._proxy_speed_tester = ProxySpeedTester(self)
        # 使用 QueuedConnection 确保信号在主线程中处理
        self._proxy_speed_tester.speed_test_completed.connect(
            self._on_speed_test_completed, Qt.QueuedConnection
        )

        # 连接下载管理器信号
        self._download_manager.progress.connect(self._on_download_progress)
        self._download_manager.completed.connect(self._on_download_completed)
        self._download_manager.error.connect(self._on_download_error)
    
    @property
    def current_version(self) -> str:
        """获取当前版本"""
        return __version__
    
    @property
    def latest_version_info(self) -> Optional[VersionInfo]:
        """获取最新版本信息"""
        return self._latest_version_info
    
    @property
    def is_checking(self) -> bool:
        """是否正在检查"""
        return self._is_checking
    
    @property
    def is_downloading(self) -> bool:
        """是否正在下载"""
        return self._is_downloading

    @property
    def proxy_speed_cache(self) -> ProxySpeedCache:
        """获取代理测速缓存"""
        return self._proxy_speed_tester.cache

    def get_github_repo(self) -> str:
        """获取 GitHub 仓库地址"""
        if self._config_manager:
            return self._config_manager.get_github_repo()
        return "wangwingzero/hugescreenshot"
    
    def get_use_proxy(self) -> bool:
        """获取是否使用 GitHub 加速代理"""
        if self._config_manager:
            return self._config_manager.get_use_proxy()
        return True
    
    def get_proxy_url(self) -> str:
        """获取 GitHub 加速代理地址
        
        优先使用用户配置的代理，如果未配置则自动选择最快的代理。
        """
        if self._config_manager:
            url = self._config_manager.get_proxy_url()
            # 如果配置的代理为空或是旧的代理地址，自动选择最快的代理
            if not url or url in ("https://ghproxy.com/", "https://mirror.ghproxy.com/"):
                return select_fastest_proxy()
            return url
        return select_fastest_proxy()
    
    def check_for_updates(self, silent: bool = False) -> None:
        """检查更新（后台线程）
        
        Args:
            silent: 是否静默模式（不显示错误）
            
        Feature: auto-update
        Requirements: 1.1, 1.2, 1.3
        """
        if self._is_checking:
            return
        
        self._is_checking = True
        
        thread = threading.Thread(
            target=self._check_worker,
            args=(silent,),
            daemon=True
        )
        thread.start()
    
    def _check_worker(self, silent: bool) -> None:
        """检查更新工作线程"""
        try:
            repo = self.get_github_repo()
            # 国内环境强制使用代理加速
            use_proxy = True
            proxy_url = self.get_proxy_url()
            async_debug_log(f"[UPDATE] 检查更新: repo={repo}, use_proxy={use_proxy}, proxy_url={proxy_url}")
            version_info = self._version_checker.get_latest_version(repo, use_proxy, proxy_url)
            
            if version_info and version_info.version:
                self._latest_version_info = version_info
                
                # 更新检查时间
                if self._config_manager:
                    self._config_manager.set_update_last_check_time()
                    self._config_manager.save()
                
                # 检查是否有新版本
                has_update = VersionChecker.is_newer_version(
                    self.current_version,
                    version_info.version
                )
                
                # 检查是否跳过此版本
                if has_update and self._config_manager:
                    skip_version = self._config_manager.get_update_skip_version()
                    if skip_version == version_info.version:
                        has_update = False
                
                self.check_completed.emit(has_update, version_info)

                if has_update:
                    self.update_available.emit(version_info)

                    # 发现新版本后，后台启动代理测速
                    self._proxy_speed_tester.start_speed_test(
                        version_info.download_url,
                        version_info.version
                    )
            else:
                self.check_completed.emit(False, None)
                
        except UpdateError as e:
            if not silent:
                self.update_error.emit(str(e))
            self.check_completed.emit(False, None)
        except Exception as e:
            if not silent:
                self.update_error.emit(f"检查更新失败: {str(e)}")
            self.check_completed.emit(False, None)
        finally:
            self._is_checking = False
    
    def should_auto_check(self) -> bool:
        """判断是否应该自动检查
        
        Feature: auto-update
        Requirements: 4.2, 4.3
        """
        if not self._config_manager:
            return True
        
        return self._config_manager.should_auto_check_update()
    
    def should_notify(self, version: str) -> bool:
        """判断是否应该发送通知
        
        通知频率控制：
        - 每次启动最多通知一次
        - 已通知过的版本不再重复通知（除非有更新的版本）
        
        Args:
            version: 新版本号
            
        Returns:
            是否应该通知
            
        Feature: auto-update
        Requirements: 4.6
        """
        # 本次会话已通知
        if self._notified_this_session:
            return False
        
        # 检查通知开关
        if self._config_manager:
            if not self._config_manager.get_notification_software_update():
                return False
            
            # 检查是否已通知过此版本或更新的版本
            # 只有当新版本比上次通知的版本更新时才通知
            last_notified = self._config_manager.get_update_last_notified_version()
            if last_notified:
                # 如果新版本不比上次通知的版本更新，则不通知
                if not VersionChecker.is_newer_version(last_notified, version):
                    return False
        
        return True
    
    def mark_notified(self, version: str) -> None:
        """标记已通知
        
        Args:
            version: 已通知的版本号
        """
        self._notified_this_session = True
        
        if self._config_manager:
            self._config_manager.set_update_last_notified_version(version)
            self._config_manager.save()
    
    def download_update(self, version_info: Optional[VersionInfo] = None) -> None:
        """下载更新

        Args:
            version_info: 版本信息，默认使用最新检查到的版本

        Feature: auto-update
        Requirements: 2.1
        """
        if self._is_downloading:
            return

        if version_info is None:
            version_info = self._latest_version_info

        if not version_info or not version_info.download_url:
            self.update_error.emit("没有可用的下载链接")
            return

        self._is_downloading = True

        # 确定下载 URL：优先使用测速缓存的最快代理
        download_url = version_info.download_url
        cache = self._proxy_speed_tester.cache
        if cache.is_valid(version_info.version):
            original_url = extract_original_url(download_url)
            download_url = self._proxy_speed_tester.get_best_download_url(original_url)
            async_debug_log(f"[UPDATE] 使用测速缓存的最快代理下载: {download_url[:80]}...")

        # 确定保存路径（下载安装包到临时目录）
        import tempfile
        temp_dir = tempfile.gettempdir()
        save_path = os.path.join(temp_dir, f"HuGeScreenshot-{version_info.version}-Setup.exe")

        # 开始下载
        self._download_manager.start_download(download_url, save_path)
    
    def cancel_download(self) -> None:
        """取消下载
        
        Feature: auto-update
        Requirements: 2.4
        """
        self._download_manager.cancel_download()
        self._is_downloading = False
    
    def _on_download_progress(self, downloaded: int, total: int, speed: float) -> None:
        """处理下载进度"""
        self.update_progress.emit(downloaded, total, speed)
    
    def _on_download_error(self, error_msg: str) -> None:
        """处理下载错误"""
        self._is_downloading = False
        self.update_error.emit(error_msg)

    def _on_speed_test_completed(self, cache: ProxySpeedCache) -> None:
        """代理测速完成回调

        Args:
            cache: 测速结果缓存
        """
        self.proxy_speed_test_completed.emit(cache)

        # 更新 version_info 的 download_url 为最快代理
        if self._latest_version_info and cache.get_fastest_proxy():
            original_url = extract_original_url(self._latest_version_info.download_url)
            self._latest_version_info.download_url = self._proxy_speed_tester.get_best_download_url(original_url)
            async_debug_log(f"[UPDATE] 更新下载 URL 为最快代理: {self._latest_version_info.download_url[:80]}...")

        # 同步测速缓存到下载管理器
        self._download_manager.set_proxy_speed_cache(cache)

    def cleanup_after_update(self) -> int:
        """更新后清理临时文件（手动调用）
        
        Returns:
            清理的文件数量
            
        Feature: auto-update
        Requirements: 3.7
        """
        exe_path = self._update_executor.get_current_exe_path()
        exe_dir = os.path.dirname(exe_path)
        
        # 获取版本信息
        current_version = self.current_version
        last_run_version = ""
        if self._config_manager:
            last_run_version = self._config_manager.get_last_run_version()
        
        return self._update_executor.cleanup_update_files(
            exe_dir, current_version, last_run_version
        )
    
    def cleanup_on_startup(self) -> int:
        """启动时清理临时文件
        
        应在应用启动时调用，会：
        1. 清理 .downloading 临时文件
        2. 清理旧版本 HuGeScreenshot-*.exe 文件（每次启动都检查）
        3. 更新 last_run_version 配置
        
        Returns:
            清理的文件数量
            
        Feature: auto-update
        Requirements: 3.7
        """
        exe_path = self._update_executor.get_current_exe_path()
        exe_dir = os.path.dirname(exe_path)
        
        # 获取版本信息
        current_version = self.current_version
        last_run_version = ""
        if self._config_manager:
            last_run_version = self._config_manager.get_last_run_version()
        
        async_debug_log(f"[UPDATE] 启动清理: 当前版本={current_version}, 上次版本={last_run_version}")
        
        # 清理 .downloading 临时文件
        cleaned = self._update_executor.cleanup_update_files(exe_dir)
        
        # 每次启动都清理旧版本 exe 文件（包括旧的单文件版本残留）
        old_cleaned = self._update_executor.cleanup_old_versions(exe_dir)
        cleaned += old_cleaned
        if old_cleaned > 0:
            async_debug_log(f"[UPDATE] 清理了 {old_cleaned} 个旧版本文件")
        
        # 更新 last_run_version
        if self._config_manager and current_version != last_run_version:
            self._config_manager.set_last_run_version(current_version)
            self._config_manager.save()
            async_debug_log(f"[UPDATE] 更新 last_run_version: {last_run_version} -> {current_version}")
        
        if cleaned > 0:
            async_debug_log(f"[UPDATE] 启动时清理了 {cleaned} 个临时文件")
        
        return cleaned
    
    def skip_version(self, version: str) -> None:
        """跳过指定版本
        
        Args:
            version: 要跳过的版本号
        """
        if self._config_manager:
            self._config_manager.set_update_skip_version(version)
            self._config_manager.save()
    
    # ========================= 静默安装方法 =========================
    # Feature: fullupdate-inplace-install
    # Requirements: 3.1, 3.2, 4.1, 4.2
    
    @staticmethod
    def build_installer_command(installer_path: str, install_dir: str) -> List[str]:
        """构建静默安装命令行
        
        Args:
            installer_path: 下载的安装包路径
            install_dir: 目标安装目录
            
        Returns:
            命令行参数列表，如 ["path/to/setup.exe", "/SILENT", "/DIR=D:\\虎哥截图"]
            
        Feature: fullupdate-inplace-install
        Requirements: 3.1, 3.2, 4.1, 4.2
        """
        cmd = [
            installer_path,
            "/SILENT",                    # 静默安装，不显示向导
            "/CLOSEAPPLICATIONS",         # 自动关闭正在运行的应用
            f'/DIR="{install_dir}"',      # 指定安装目录
        ]
        return cmd
    
    def launch_installer(self, installer_path: str, install_dir: str) -> Tuple[bool, str]:
        """启动安装程序进行静默安装
        
        Args:
            installer_path: 下载的安装包路径
            install_dir: 目标安装目录
            
        Returns:
            (success, error_message) 元组
            
        Feature: fullupdate-inplace-install
        Requirements: 3.1, 3.2, 4.1, 4.2
        """
        import subprocess
        
        # 验证安装包存在
        if not os.path.exists(installer_path):
            return (False, f"安装包不存在: {installer_path}")
        
        # 验证安装目录
        if not install_dir:
            return (False, "安装目录未指定")
        
        try:
            # 构建命令行
            cmd = self.build_installer_command(installer_path, install_dir)
            
            async_debug_log(f"[UPDATE] 启动静默安装: {' '.join(cmd)}")
            
            # 启动安装程序（独立进程）
            # 使用 shell=True 以正确处理带空格的路径
            cmd_str = ' '.join(cmd)
            subprocess.Popen(
                cmd_str,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True,
                start_new_session=True
            )
            
            return (True, "")
            
        except OSError as e:
            error_msg = f"启动安装程序失败: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            return (False, error_msg)
        except Exception as e:
            error_msg = f"启动安装程序时发生错误: {e}"
            async_debug_log(f"[UPDATE] {error_msg}")
            return (False, error_msg)
    
    def get_install_path(self) -> str:
        """获取安装路径
        
        Returns:
            安装路径，如果未配置则返回空字符串
            
        Feature: fullupdate-inplace-install
        Requirements: 1.1
        """
        if self._config_manager:
            return self._config_manager.get_install_path()
        return ""
    
    def get_downloaded_installer_path(self) -> Optional[str]:
        """获取已下载的安装包路径
        
        Returns:
            安装包路径，如果未下载则返回 None
        """
        return self._downloaded_file
    
    def _on_download_completed(self, file_path: str) -> None:
        """处理下载完成"""
        self._is_downloading = False
        self._downloaded_file = file_path
        
        # 验证文件
        if self._latest_version_info:
            expected_size = self._latest_version_info.file_size
            if expected_size > 0:
                if not DownloadManager.verify_file(file_path, expected_size):
                    self.update_error.emit("下载的文件大小不匹配，可能已损坏")
                    return
        
        version = self._latest_version_info.version if self._latest_version_info else ""
        self.update_completed.emit(version)
        
        async_debug_log(f"[UPDATE] 下载完成: v{version}")


# ========== 增量更新服务 ==========

class DeltaUpdateService(QObject):
    """增量更新服务 - 支持增量更新的更新服务
    
    Feature: installer-incremental-update
    Requirements: 4.1, 4.4, 4.5, 5.4, 5.5, 5.6
    
    增量更新流程：
    1. 下载远程 manifest.json
    2. 与本地 manifest.json 对比
    3. 计算增量（新增、修改、删除的文件）
    4. 如果增量大小 < 50% 完整大小，使用增量更新
    5. 否则回退到完整更新
    """
    
    # 信号
    delta_progress = Signal(str, int, int, float)  # (filename, downloaded, total, speed)
    delta_overall_progress = Signal(int, int)       # (files_done, total_files)
    delta_completed = Signal()
    delta_failed = Signal(str)
    manifest_downloaded = Signal(object)            # Manifest
    
    # 增量更新阈值（增量大小占完整大小的比例）
    DELTA_THRESHOLD = 0.5
    
    def __init__(self, install_dir: str, parent=None):
        """初始化增量更新服务
        
        Args:
            install_dir: 安装目录路径
            parent: 父对象
        """
        super().__init__(parent)
        self._install_dir = install_dir
        self._local_manifest = None
        self._remote_manifest = None
        self._delta_updater = None
        self._is_updating = False
    
    @property
    def install_dir(self) -> str:
        """获取安装目录"""
        return self._install_dir
    
    @property
    def is_updating(self) -> bool:
        """是否正在更新"""
        return self._is_updating
    
    def load_local_manifest(self) -> bool:
        """加载本地清单
        
        Returns:
            True 如果加载成功
        """
        try:
            from screenshot_tool.services.manifest_service import ManifestGenerator
            
            manifest_path = os.path.join(self._install_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                async_debug_log("[DELTA_UPDATE] 本地清单不存在")
                return False
            
            generator = ManifestGenerator()
            self._local_manifest = generator.load(manifest_path)
            async_debug_log(f"[DELTA_UPDATE] 加载本地清单: v{self._local_manifest.version}")
            return True
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 加载本地清单失败: {e}")
            return False
    
    def download_remote_manifest(self, base_url: str) -> bool:
        """下载远程清单
        
        Args:
            base_url: 远程基础 URL（如 GitHub Release URL）
            
        Returns:
            True 如果下载成功
        """
        try:
            from screenshot_tool.services.manifest_service import Manifest
            
            manifest_url = f"{base_url.rstrip('/')}/manifest.json"
            async_debug_log(f"[DELTA_UPDATE] 下载远程清单: {manifest_url}")
            
            response = requests.get(manifest_url, timeout=30)
            response.raise_for_status()
            
            self._remote_manifest = Manifest.from_json(response.text)
            async_debug_log(f"[DELTA_UPDATE] 远程清单: v{self._remote_manifest.version}")
            
            self.manifest_downloaded.emit(self._remote_manifest)
            return True
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 下载远程清单失败: {e}")
            return False
    
    def should_use_delta_update(self) -> Tuple[bool, Optional['DeltaResult']]:
        """判断是否应该使用增量更新
        
        Returns:
            (should_use, delta_result) 元组
        """
        if not self._local_manifest or not self._remote_manifest:
            return False, None
        
        try:
            from screenshot_tool.services.manifest_service import DeltaCalculator
            
            calculator = DeltaCalculator()
            delta = calculator.calculate(self._local_manifest, self._remote_manifest)
            
            # 检查是否有变更
            if not delta.has_changes:
                async_debug_log("[DELTA_UPDATE] 无变更，已是最新版本")
                return False, delta
            
            # 检查增量大小
            should_use = calculator.should_use_delta(delta, self.DELTA_THRESHOLD)
            
            ratio = delta.delta_size / delta.full_size if delta.full_size > 0 else 1.0
            async_debug_log(
                f"[DELTA_UPDATE] 增量分析: "
                f"增量={delta.delta_size / 1024 / 1024:.1f}MB, "
                f"完整={delta.full_size / 1024 / 1024:.1f}MB, "
                f"比例={ratio:.1%}, "
                f"使用增量={should_use}"
            )
            
            return should_use, delta
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 增量计算失败: {e}")
            return False, None
    
    def start_delta_update(self, delta: 'DeltaResult', base_url: str) -> None:
        """开始增量更新
        
        Args:
            delta: 增量计算结果
            base_url: 文件下载基础 URL
        """
        if self._is_updating:
            return
        
        try:
            from screenshot_tool.services.delta_updater import DeltaUpdater
            
            self._is_updating = True
            self._delta_updater = DeltaUpdater(self._install_dir, self)
            
            # 连接信号
            self._delta_updater.file_progress.connect(self.delta_progress)
            self._delta_updater.overall_progress.connect(self.delta_overall_progress)
            self._delta_updater.update_completed.connect(self._on_delta_completed)
            self._delta_updater.update_failed.connect(self._on_delta_failed)
            
            # 开始更新
            self._delta_updater.start_update(delta, base_url)
            
        except Exception as e:
            self._is_updating = False
            self.delta_failed.emit(f"启动增量更新失败: {e}")
    
    def cancel_update(self) -> None:
        """取消更新"""
        if self._delta_updater:
            self._delta_updater.cancel()
        self._is_updating = False
    
    def _on_delta_completed(self) -> None:
        """增量更新完成"""
        self._is_updating = False
        
        # 保存新的清单
        if self._remote_manifest:
            try:
                from screenshot_tool.services.manifest_service import ManifestGenerator
                
                generator = ManifestGenerator()
                manifest_path = os.path.join(self._install_dir, "manifest.json")
                generator.save(self._remote_manifest, manifest_path)
                async_debug_log(f"[DELTA_UPDATE] 保存新清单: {manifest_path}")
            except Exception as e:
                async_debug_log(f"[DELTA_UPDATE] 保存清单失败: {e}")
        
        self.delta_completed.emit()
    
    def _on_delta_failed(self, error_msg: str) -> None:
        """增量更新失败"""
        self._is_updating = False
        self.delta_failed.emit(error_msg)
    
    def verify_installation(self) -> bool:
        """验证安装完整性
        
        Returns:
            True 如果安装完整
        """
        if not self._local_manifest:
            if not self.load_local_manifest():
                return False
        
        try:
            from screenshot_tool.services.delta_updater import verify_installation_integrity
            
            return verify_installation_integrity(self._install_dir, self._local_manifest)
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 验证安装失败: {e}")
            return False


def select_fastest_proxy() -> str:
    """选择最快的代理（简单实现，返回第一个可用代理）
    
    Returns:
        代理 URL
    """
    return GITHUB_PROXIES[0] if GITHUB_PROXIES else ""
