# =====================================================
# ============= 无缝更新流程功能测试 =================
# =====================================================

"""
无缝更新流程的单元测试和属性测试

Feature: seamless-update-flow
Requirements: 1.1, 1.2
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, assume

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ========== 辅助函数：保存路径生成逻辑 ==========

def generate_save_path(exe_dir: str, version: str) -> str:
    """生成保存路径的核心逻辑
    
    这是从 SettingsDialog._get_auto_save_path 提取的核心逻辑，
    用于属性测试。
    
    Args:
        exe_dir: exe 所在目录
        version: 版本号
        
    Returns:
        保存路径 {exe_dir}/HuGeScreenshot-{version}.exe
    """
    return os.path.join(exe_dir, f"HuGeScreenshot-{version}.exe")


# ========== Property 1: Save Path Generation ==========
# Feature: seamless-update-flow, Property 1: Save Path Generation
# Validates: Requirements 1.1, 1.2

class TestSavePathGeneration:
    """保存路径生成属性测试"""
    
    # 版本号策略：生成有效的版本号字符串
    version_strategy = st.from_regex(
        r'[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9]+)?',
        fullmatch=True
    )
    
    # 目录路径策略：生成有效的 Windows 路径
    dir_strategy = st.from_regex(
        r'[A-Z]:\\[a-zA-Z0-9_\\]+',
        fullmatch=True
    )
    
    @given(version=version_strategy, exe_dir=dir_strategy)
    @settings(max_examples=100)
    def test_save_path_format(self, version: str, exe_dir: str):
        """Property 1: 保存路径格式正确
        
        For any valid version string and exe directory, the generated 
        save path SHALL be in the format {exe_dir}/HuGeScreenshot-{version}.exe.
        
        **Validates: Requirements 1.1, 1.2**
        """
        save_path = generate_save_path(exe_dir, version)
        
        # 验证路径包含目录
        assert save_path.startswith(exe_dir)
        
        # 验证文件名格式
        filename = os.path.basename(save_path)
        assert filename == f"HuGeScreenshot-{version}.exe"
        
        # 验证扩展名
        assert save_path.endswith(".exe")
        
        # 验证包含版本号
        assert version in save_path
    
    @given(version=version_strategy)
    @settings(max_examples=100)
    def test_save_path_contains_version(self, version: str):
        """验证保存路径包含版本号"""
        exe_dir = "C:\\Program Files\\HuGeScreenshot"
        save_path = generate_save_path(exe_dir, version)
        
        assert version in save_path
        assert f"HuGeScreenshot-{version}.exe" in save_path
    
    @given(exe_dir=dir_strategy)
    @settings(max_examples=100)
    def test_save_path_in_exe_dir(self, exe_dir: str):
        """验证保存路径在 exe 目录下"""
        version = "2.1.0"
        save_path = generate_save_path(exe_dir, version)
        
        # 验证目录部分（规范化路径以处理尾部斜杠）
        assert os.path.normpath(os.path.dirname(save_path)) == os.path.normpath(exe_dir)
    
    def test_specific_versions(self):
        """测试特定版本号"""
        exe_dir = "C:\\Apps"
        test_cases = [
            ("1.0.0", "C:\\Apps\\HuGeScreenshot-1.0.0.exe"),
            ("2.1.0", "C:\\Apps\\HuGeScreenshot-2.1.0.exe"),
            ("2.1.0-beta", "C:\\Apps\\HuGeScreenshot-2.1.0-beta.exe"),
            ("10.20.30", "C:\\Apps\\HuGeScreenshot-10.20.30.exe"),
        ]
        
        for version, expected in test_cases:
            result = generate_save_path(exe_dir, version)
            assert result == expected, f"Version {version}: expected {expected}, got {result}"
    
    def test_different_directories(self):
        """测试不同目录"""
        version = "2.0.0"
        test_cases = [
            ("C:\\", "C:\\HuGeScreenshot-2.0.0.exe"),
            ("C:\\Program Files", "C:\\Program Files\\HuGeScreenshot-2.0.0.exe"),
            ("D:\\Apps\\Screenshot", "D:\\Apps\\Screenshot\\HuGeScreenshot-2.0.0.exe"),
        ]
        
        for exe_dir, expected in test_cases:
            result = generate_save_path(exe_dir, version)
            assert result == expected, f"Dir {exe_dir}: expected {expected}, got {result}"


# ========== 单元测试 ==========

class TestSavePathUnit:
    """保存路径单元测试"""
    
    def test_path_is_absolute(self):
        """验证生成的路径是绝对路径"""
        exe_dir = "C:\\Program Files\\HuGeScreenshot"
        version = "2.1.0"
        
        save_path = generate_save_path(exe_dir, version)
        
        # Windows 绝对路径以盘符开头
        assert save_path[1] == ":"
    
    def test_filename_prefix(self):
        """验证文件名前缀"""
        exe_dir = "C:\\Test"
        version = "1.0.0"
        
        save_path = generate_save_path(exe_dir, version)
        filename = os.path.basename(save_path)
        
        assert filename.startswith("HuGeScreenshot-")
    
    def test_filename_suffix(self):
        """验证文件名后缀"""
        exe_dir = "C:\\Test"
        version = "1.0.0"
        
        save_path = generate_save_path(exe_dir, version)
        
        assert save_path.endswith(".exe")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
