# =====================================================
# =============== 开机自启动管理器 ===============
# =====================================================

"""
开机自启动管理器 - 管理 Windows 开机自启动

通过 Windows 注册表实现开机自启动功能
仅支持 Windows 平台
"""

import os
import sys
from typing import Optional

# 平台检查
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import winreg

# 应用信息
APP_NAME = "虎哥截图"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 入口文件名（相对于项目根目录）
ENTRY_FILE = "虎哥截图.pyw"
# 便携版启动脚本
PORTABLE_VBS = "启动.vbs"


class AutoStartManager:
    """开机自启动管理器（仅支持 Windows）"""
    
    def __init__(self, app_name: str = APP_NAME):
        """
        初始化自启动管理器
        
        Args:
            app_name: 应用名称（用于注册表键名）
        """
        self._app_name = app_name
        self._exe_path = self._get_exe_path()
    
    def _get_exe_path(self) -> str:
        """
        获取当前程序的可执行文件路径
        
        支持三种环境：
        1. PyInstaller 打包后的 exe
        2. 便携版（通过 启动.vbs 判断）
        3. 开发环境
        """
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的 exe
            return f'"{sys.executable}"'
        
        # 获取项目根目录
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 检查是否是便携版（存在 启动.vbs）
        vbs_file = os.path.join(script_dir, PORTABLE_VBS)
        if os.path.exists(vbs_file):
            # 便携版：使用 wscript.exe 运行 vbs（静默启动）
            return f'wscript.exe "{vbs_file}"'
        
        # 开发环境：使用 pythonw.exe 运行 pyw 文件
        pyw_file = os.path.join(script_dir, ENTRY_FILE)
        if os.path.exists(pyw_file):
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if os.path.exists(pythonw):
                return f'"{pythonw}" "{pyw_file}"'
            return f'"{sys.executable}" "{pyw_file}"'
        
        return f'"{sys.executable}"'
    
    def is_enabled(self) -> bool:
        """检查是否已启用开机自启动
        
        Returns:
            bool: 是否已启用
        """
        if not IS_WINDOWS:
            return False
        
        key = None
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY,
                0,
                winreg.KEY_READ
            )
            winreg.QueryValueEx(key, self._app_name)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False
        finally:
            if key is not None:
                winreg.CloseKey(key)
    
    def enable(self, exe_path: Optional[str] = None) -> bool:
        """启用开机自启动
        
        Args:
            exe_path: 可选的 exe 路径，如果不提供则使用当前计算的路径
        
        Returns:
            bool: 是否成功
        """
        if not IS_WINDOWS:
            return False
        
        # 如果没有提供路径，重新计算当前路径
        path_to_register = exe_path if exe_path else self._get_exe_path()
        
        key = None
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(
                key,
                self._app_name,
                0,
                winreg.REG_SZ,
                path_to_register
            )
            # 同步更新缓存
            self._exe_path = path_to_register
            return True
        except Exception as e:
            print(f"[Warning] 启用开机自启动失败: {e}")
            return False
        finally:
            if key is not None:
                winreg.CloseKey(key)
    
    def disable(self) -> bool:
        """禁用开机自启动
        
        Returns:
            bool: 是否成功
        """
        if not IS_WINDOWS:
            return False
        
        key = None
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, self._app_name)
            return True
        except FileNotFoundError:
            # 本来就没有，也算成功
            return True
        except Exception as e:
            print(f"[Warning] 禁用开机自启动失败: {e}")
            return False
        finally:
            if key is not None:
                winreg.CloseKey(key)
    
    def set_enabled(self, enabled: bool) -> bool:
        """设置开机自启动状态
        
        Args:
            enabled: 是否启用
            
        Returns:
            bool: 是否成功
        """
        if enabled:
            return self.enable()
        else:
            return self.disable()
    
    def sync_with_config(self, config_enabled: bool) -> bool:
        """同步配置与实际注册表状态
        
        Args:
            config_enabled: 配置中的启用状态
            
        Returns:
            bool: 是否成功
        """
        if not IS_WINDOWS:
            return True  # 非 Windows 平台直接返回成功
        
        current_enabled = self.is_enabled()
        if current_enabled != config_enabled:
            return self.set_enabled(config_enabled)
        return True
    
    def get_registered_path(self) -> Optional[str]:
        """获取注册表中记录的启动路径
        
        Returns:
            注册表中的路径，如果未注册则返回 None
        """
        if not IS_WINDOWS:
            return None
        
        key = None
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY,
                0,
                winreg.KEY_READ
            )
            value, _ = winreg.QueryValueEx(key, self._app_name)
            return value
        except FileNotFoundError:
            return None
        except Exception:
            return None
        finally:
            if key is not None:
                winreg.CloseKey(key)
    
    def sync_path_if_needed(self) -> bool:
        """
        检查并同步注册表中的路径
        
        如果 EXE 被移动到新位置或版本升级导致文件名变化，自动更新注册表中的路径。
        仅在已启用开机自启动时才会更新。
        
        Returns:
            bool: 是否进行了更新
        """
        if not IS_WINDOWS:
            return False
        
        # 检查是否已启用开机自启动
        if not self.is_enabled():
            return False
        
        # 获取注册表中的路径
        registered_path = self.get_registered_path()
        if registered_path is None:
            return False
        
        # 获取当前路径（每次重新计算，确保获取最新的 exe 路径）
        current_path = self._get_exe_path()
        
        # 提取注册表中的 exe 路径（去除引号）
        def extract_exe_path(p: str) -> str:
            """从注册表值中提取 exe 文件路径"""
            if not p:
                return ""
            # 移除引号
            result = p.strip().replace('"', '').replace("'", "")
            # 如果是 wscript.exe 启动的 vbs，提取 vbs 路径
            if result.lower().startswith("wscript.exe "):
                result = result[12:].strip()
            return result
        
        # 检查注册表中的文件是否存在
        registered_exe = extract_exe_path(registered_path)
        if registered_exe and not os.path.exists(registered_exe):
            print(f"[AutoStart] 注册表中的文件不存在: {registered_exe}")
            print(f"[AutoStart] 正在更新为当前路径: {current_path}")
            success = self.enable(current_path)
            if success:
                print(f"[AutoStart] 注册表更新成功")
            else:
                print(f"[AutoStart] 注册表更新失败")
            return success
        
        # 规范化路径用于比较
        def normalize_path(p: str) -> str:
            """
            规范化路径用于比较
            - 移除首尾空格
            - 移除所有引号
            - 转换为小写
            - 规范化路径分隔符
            """
            if not p:
                return ""
            # 移除空格和引号
            result = p.strip().replace('"', '').replace("'", "")
            # 规范化路径分隔符并转小写
            result = os.path.normpath(result).lower()
            return result
        
        registered_normalized = normalize_path(registered_path)
        current_normalized = normalize_path(current_path)
        
        # 如果路径不同，更新注册表
        if registered_normalized != current_normalized:
            print(f"[AutoStart] 检测到路径变化")
            print(f"[AutoStart] 注册表: {registered_normalized}")
            print(f"[AutoStart] 当前: {current_normalized}")
            print(f"[AutoStart] 正在更新注册表...")
            success = self.enable(current_path)
            if success:
                print(f"[AutoStart] 注册表更新成功")
            else:
                print(f"[AutoStart] 注册表更新失败")
            return success
        
        return False


# 全局实例
_autostart_manager: Optional[AutoStartManager] = None


def get_autostart_manager() -> AutoStartManager:
    """获取全局自启动管理器实例"""
    global _autostart_manager
    if _autostart_manager is None:
        _autostart_manager = AutoStartManager()
    return _autostart_manager
