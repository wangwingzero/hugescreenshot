# =====================================================
# =============== 安装路径配置测试 ===============
# =====================================================

"""
安装路径配置测试 - 测试全量更新的安装路径管理功能

Feature: fullupdate-inplace-install
Requirements: 1.1, 1.2, 1.3, 1.4
Property 1: Installation Path Round-Trip
Property 2: Installation Path Validation
"""

import json
import os
import tempfile
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import AppConfig, ConfigManager


# 生成有效的 Windows 路径字符串的策略
# 避免生成包含非法字符的路径
valid_path_chars = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"),
    min_size=1,
    max_size=50
)


class TestInstallPathRoundTrip:
    """测试安装路径序列化往返
    
    Property 1: Installation Path Round-Trip
    *For any* valid directory path, saving it to config and then loading it back 
    SHALL return the exact same path.
    
    **Validates: Requirements 1.1, 1.2**
    """
    
    @given(path_segment=valid_path_chars)
    @settings(max_examples=100)
    def test_install_path_round_trip(self, path_segment: str):
        """Property 1: 任意有效路径保存后加载应返回相同路径"""
        # 构造一个有效的路径
        test_path = f"D:\\TestApp\\{path_segment}"
        
        # 创建配置并设置路径
        config = AppConfig()
        config.install_path = test_path
        
        # 序列化为字典
        data = config.to_dict()
        
        # 序列化为 JSON 再反序列化
        json_str = json.dumps(data, ensure_ascii=False)
        loaded_data = json.loads(json_str)
        
        # 从字典创建新配置
        restored = AppConfig.from_dict(loaded_data)
        
        # 验证路径相同
        assert restored.install_path == test_path
    
    def test_round_trip_with_chinese_path(self):
        """测试中文路径的往返"""
        test_path = "D:\\虎哥截图\\安装目录"
        
        config = AppConfig()
        config.install_path = test_path
        
        data = config.to_dict()
        json_str = json.dumps(data, ensure_ascii=False)
        loaded_data = json.loads(json_str)
        
        restored = AppConfig.from_dict(loaded_data)
        assert restored.install_path == test_path
    
    def test_round_trip_with_empty_path(self):
        """测试空路径的往返"""
        config = AppConfig()
        config.install_path = ""
        
        data = config.to_dict()
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        restored = AppConfig.from_dict(loaded_data)
        assert restored.install_path == ""
    
    def test_round_trip_with_spaces_in_path(self):
        """测试包含空格的路径的往返"""
        test_path = "D:\\Program Files\\HuGe Screenshot"
        
        config = AppConfig()
        config.install_path = test_path
        
        data = config.to_dict()
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)
        
        restored = AppConfig.from_dict(loaded_data)
        assert restored.install_path == test_path


class TestInstallPathConfigManager:
    """测试 ConfigManager 的安装路径管理方法
    
    Property 1: Installation Path Round-Trip (via ConfigManager)
    **Validates: Requirements 1.1, 1.2**
    """
    
    def test_get_set_install_path(self):
        """测试 get/set 安装路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            test_path = "D:\\TestApp\\Installation"
            manager.set_install_path(test_path)
            
            assert manager.get_install_path() == test_path
    
    def test_set_empty_path(self):
        """测试设置空路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            manager.set_install_path("")
            assert manager.get_install_path() == ""
            
            manager.set_install_path(None)
            assert manager.get_install_path() == ""
    
    def test_save_and_load_install_path(self):
        """测试保存和加载安装路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            
            # 创建并保存配置
            manager1 = ConfigManager(config_path)
            test_path = "D:\\虎哥截图"
            manager1.set_install_path(test_path)
            manager1.save()
            
            # 重新加载配置
            manager2 = ConfigManager(config_path)
            manager2.load()
            
            assert manager2.get_install_path() == test_path


class TestInstallPathValidation:
    """测试安装路径验证
    
    Property 2: Installation Path Validation
    *For any* saved installation path that no longer exists on the filesystem, 
    the validation function SHALL update it to the current executable's directory.
    
    **Validates: Requirements 1.3, 1.4**
    """
    
    def test_validate_existing_path(self):
        """测试验证存在的路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            # 设置一个存在的路径
            manager.set_install_path(tmpdir)
            
            # 验证应返回相同路径
            result = manager.validate_install_path()
            assert result == tmpdir
    
    def test_validate_nonexistent_path(self):
        """测试验证不存在的路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            # 设置一个不存在的路径
            nonexistent_path = "Z:\\NonExistent\\Path\\12345"
            manager.set_install_path(nonexistent_path)
            
            # 验证应更新为当前目录
            result = manager.validate_install_path()
            assert result != nonexistent_path
            assert os.path.isdir(result)
    
    def test_validate_empty_path(self):
        """测试验证空路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            # 设置空路径
            manager.set_install_path("")
            
            # 验证应检测并返回当前目录
            result = manager.validate_install_path()
            assert result != ""
            assert os.path.isdir(result)
    
    def test_detect_and_save_install_path(self):
        """测试检测并保存安装路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            # 初始路径为空
            assert manager.get_install_path() == ""
            
            # 检测并保存
            result = manager.detect_and_save_install_path()
            
            # 应返回有效路径
            assert result != ""
            assert os.path.isdir(result)
            
            # 配置应已更新
            assert manager.get_install_path() == result
    
    def test_detect_preserves_valid_path(self):
        """测试检测时保留有效路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            manager = ConfigManager(config_path)
            
            # 设置一个有效路径
            manager.set_install_path(tmpdir)
            
            # 检测应保留原路径
            result = manager.detect_and_save_install_path()
            assert result == tmpdir


class TestInstallPathDefault:
    """测试安装路径默认值"""
    
    def test_default_install_path_is_empty(self):
        """测试默认安装路径为空"""
        config = AppConfig()
        assert config.install_path == ""
    
    def test_from_dict_missing_install_path(self):
        """测试从字典加载时缺少 install_path 字段"""
        data = {"save_path": "D:\\Screenshots"}
        config = AppConfig.from_dict(data)
        assert config.install_path == ""



# =====================================================
# =============== 静默安装命令行测试 ===============
# =====================================================

"""
静默安装命令行测试

Feature: fullupdate-inplace-install
Requirements: 3.1, 3.2, 4.1, 4.2
Property 4: Silent Install Command Construction
"""

from screenshot_tool.services.update_service import UpdateService


class TestSilentInstallCommandConstruction:
    """测试静默安装命令行构建
    
    Property 4: Silent Install Command Construction
    *For any* valid installer path and installation directory, the constructed command 
    SHALL include `/SILENT` flag and `/DIR="<directory>"` parameter with the correct path.
    
    **Validates: Requirements 3.1, 3.2, 4.1, 4.2**
    """
    
    @given(
        installer_name=valid_path_chars,
        install_dir_name=valid_path_chars
    )
    @settings(max_examples=100)
    def test_command_contains_silent_flag(self, installer_name: str, install_dir_name: str):
        """Property 4: 命令行应包含 /SILENT 标志"""
        installer_path = f"C:\\Temp\\{installer_name}.exe"
        install_dir = f"D:\\Apps\\{install_dir_name}"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        # 验证包含 /SILENT
        assert "/SILENT" in cmd
    
    @given(
        installer_name=valid_path_chars,
        install_dir_name=valid_path_chars
    )
    @settings(max_examples=100)
    def test_command_contains_dir_parameter(self, installer_name: str, install_dir_name: str):
        """Property 4: 命令行应包含 /DIR 参数"""
        installer_path = f"C:\\Temp\\{installer_name}.exe"
        install_dir = f"D:\\Apps\\{install_dir_name}"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        # 验证包含 /DIR 参数
        dir_params = [c for c in cmd if c.startswith('/DIR=')]
        assert len(dir_params) == 1
        assert install_dir in dir_params[0]
    
    @given(
        installer_name=valid_path_chars,
        install_dir_name=valid_path_chars
    )
    @settings(max_examples=100)
    def test_command_first_element_is_installer(self, installer_name: str, install_dir_name: str):
        """Property 4: 命令行第一个元素应是安装程序路径"""
        installer_path = f"C:\\Temp\\{installer_name}.exe"
        install_dir = f"D:\\Apps\\{install_dir_name}"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        # 验证第一个元素是安装程序路径
        assert cmd[0] == installer_path
    
    def test_command_with_chinese_path(self):
        """测试中文路径的命令行构建"""
        installer_path = "C:\\Temp\\HuGeScreenshot-2.5.0-Setup.exe"
        install_dir = "D:\\虎哥截图"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        assert cmd[0] == installer_path
        assert "/SILENT" in cmd
        assert any("虎哥截图" in c for c in cmd)
    
    def test_command_with_spaces_in_path(self):
        """测试包含空格的路径的命令行构建"""
        installer_path = "C:\\Temp\\HuGe Screenshot Setup.exe"
        install_dir = "D:\\Program Files\\HuGe Screenshot"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        assert cmd[0] == installer_path
        assert "/SILENT" in cmd
        # /DIR 参数应该用引号包裹路径
        dir_param = [c for c in cmd if c.startswith('/DIR=')][0]
        assert '"' in dir_param
    
    def test_command_contains_closeapplications(self):
        """测试命令行包含 /CLOSEAPPLICATIONS 参数"""
        installer_path = "C:\\Temp\\Setup.exe"
        install_dir = "D:\\App"
        
        cmd = UpdateService.build_installer_command(installer_path, install_dir)
        
        assert "/CLOSEAPPLICATIONS" in cmd
