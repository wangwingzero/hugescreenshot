# =====================================================
# =============== 自动重启更新功能测试 ===============
# =====================================================

"""
自动重启更新功能的单元测试和属性测试

Feature: auto-restart-update
Requirements: 1.4, 2.2, 4.4
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, assume

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from screenshot_tool.services.update_service import UpdateExecutor


# ========== Property 1: Command Line Argument Format ==========
# Feature: auto-restart-update, Property 1: Command Line Argument Format
# Validates: Requirements 1.4

class TestCommandLineArgumentFormat:
    """命令行参数格式测试"""
    
    @given(st.text(min_size=1, max_size=200).filter(lambda x: x.strip() and '\x00' not in x))
    @settings(max_examples=100)
    def test_launch_command_includes_cleanup_arg(self, old_path: str):
        """Property 1: 启动命令应包含 --cleanup-old 参数和旧版本路径
        
        For any valid old exe path, the launch command SHALL include 
        the --cleanup-old argument followed by the path.
        """
        # 模拟 frozen 环境
        with patch.object(sys, 'frozen', True, create=True):
            with patch('os.path.exists', return_value=True):
                with patch('subprocess.Popen') as mock_popen:
                    # 使用有效的 exe 文件名
                    new_exe = "C:\\test\\HuGeScreenshot-2.0.0.exe"
                    
                    UpdateExecutor.launch_new_version(new_exe, old_path)
                    
                    # 验证 Popen 被调用
                    if mock_popen.called:
                        call_args = mock_popen.call_args[0][0]
                        
                        # 验证命令行包含 --cleanup-old 参数
                        assert UpdateExecutor.CLEANUP_ARG in call_args
                        
                        # 验证参数顺序：exe, --cleanup-old, old_path
                        cleanup_idx = call_args.index(UpdateExecutor.CLEANUP_ARG)
                        assert cleanup_idx + 1 < len(call_args)
                        assert call_args[cleanup_idx + 1] == old_path
    
    def test_cleanup_arg_constant(self):
        """验证清理参数常量"""
        assert UpdateExecutor.CLEANUP_ARG == "--cleanup-old"


# ========== Property 2: Exponential Backoff Retry ==========
# Feature: auto-restart-update, Property 2: Exponential Backoff Retry
# Validates: Requirements 2.2

class TestExponentialBackoffRetry:
    """指数退避重试测试"""
    
    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_backoff_time_calculation(self, attempt: int):
        """Property 2: 退避时间应遵循指数增长模式，上限 8 秒
        
        For any number of retry attempts n (where n > 0), the wait time 
        before attempt n SHALL follow exponential backoff pattern: 
        min(2^(n-1), 8) seconds.
        """
        wait_time = UpdateExecutor.calculate_backoff_time(attempt)
        
        # 验证计算公式
        expected = min(2 ** (attempt - 1), 8)
        assert wait_time == expected
        
        # 验证上限
        assert wait_time <= 8
        
        # 验证下限
        assert wait_time >= 1
    
    def test_backoff_sequence(self):
        """验证退避时间序列"""
        expected_sequence = [1, 2, 4, 8, 8, 8, 8, 8]
        
        for i, expected in enumerate(expected_sequence, start=1):
            actual = UpdateExecutor.calculate_backoff_time(i)
            assert actual == expected, f"Attempt {i}: expected {expected}, got {actual}"
    
    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_total_wait_time_bounded(self, num_attempts: int):
        """验证总等待时间在合理范围内"""
        total_wait = sum(
            UpdateExecutor.calculate_backoff_time(i) 
            for i in range(1, num_attempts + 1)
        )
        
        # 前几次的总和：1 + 2 + 4 + 8 = 15，之后每次 +8
        if num_attempts <= 4:
            expected_max = sum(min(2 ** (i - 1), 8) for i in range(1, num_attempts + 1))
        else:
            expected_max = 15 + (num_attempts - 4) * 8
        
        assert total_wait == expected_max


# ========== Property 4: File Pattern Matching ==========
# Feature: auto-restart-update, Property 4: File Pattern Matching
# Validates: Requirements 4.4

class TestFilePatternMatching:
    """文件名模式匹配测试"""
    
    @given(st.text(min_size=1, max_size=50).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_valid_exe_names_match(self, version: str):
        """Property 4: HuGeScreenshot-*.exe 格式的文件名应匹配
        
        For any file path, the cleanup logic SHALL only delete files 
        where the filename matches the pattern HuGeScreenshot-*.exe.
        """
        # 跳过包含特殊字符的版本号
        assume(all(c not in version for c in ['/', '\\', '*', '?', '<', '>', '|', '"']))
        
        filename = f"HuGeScreenshot-{version}.exe"
        assert UpdateExecutor.is_valid_exe_name(filename) == True
    
    @given(st.text(min_size=1, max_size=50).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_case_insensitive_matching(self, version: str):
        """验证大小写不敏感匹配"""
        assume(all(c not in version for c in ['/', '\\', '*', '?', '<', '>', '|', '"']))
        
        # 各种大小写组合
        filenames = [
            f"HuGeScreenshot-{version}.exe",
            f"hugescreenshot-{version}.exe",
            f"HUGESCREENSHOT-{version}.exe",
            f"HuGeScreenshot-{version}.EXE",
        ]
        
        for filename in filenames:
            assert UpdateExecutor.is_valid_exe_name(filename) == True
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_invalid_names_dont_match(self, filename: str):
        """验证不符合格式的文件名不匹配"""
        # 跳过实际符合格式的文件名
        assume(not filename.lower().startswith("hugescreenshot-"))
        assume(not filename.lower().endswith(".exe") or "hugescreenshot" not in filename.lower())
        
        # 不符合格式的文件名应返回 False
        result = UpdateExecutor.is_valid_exe_name(filename)
        
        # 如果文件名不以 hugescreenshot- 开头或不以 .exe 结尾，应该返回 False
        if not (filename.lower().startswith("hugescreenshot-") and filename.lower().endswith(".exe")):
            assert result == False
    
    def test_specific_invalid_names(self):
        """测试特定的无效文件名"""
        invalid_names = [
            "screenshot.exe",
            "HuGeScreenshot.exe",  # 缺少版本号
            "HuGeScreenshot-1.0.0.txt",  # 错误扩展名
            "other-app-1.0.0.exe",
            "HuGeScreenshot-1.0.0",  # 缺少扩展名
            "",
            "test.exe",
        ]
        
        for name in invalid_names:
            assert UpdateExecutor.is_valid_exe_name(name) == False, f"Should reject: {name}"
    
    def test_specific_valid_names(self):
        """测试特定的有效文件名"""
        valid_names = [
            "HuGeScreenshot-1.0.0.exe",
            "HuGeScreenshot-2.1.1.exe",
            "HuGeScreenshot-v1.0.0.exe",
            "HuGeScreenshot-beta.exe",
            "hugescreenshot-1.0.0.exe",
            "HUGESCREENSHOT-1.0.0.EXE",
        ]
        
        for name in valid_names:
            assert UpdateExecutor.is_valid_exe_name(name) == True, f"Should accept: {name}"


# ========== 参数解析测试 ==========

class TestParseCleanupArg:
    """命令行参数解析测试"""
    
    def test_parse_valid_arg(self):
        """测试解析有效参数"""
        args = ["app.exe", "--cleanup-old", "C:\\old\\HuGeScreenshot-1.0.0.exe"]
        result = UpdateExecutor.parse_cleanup_arg(args)
        assert result == "C:\\old\\HuGeScreenshot-1.0.0.exe"
    
    def test_parse_no_arg(self):
        """测试没有清理参数"""
        args = ["app.exe"]
        result = UpdateExecutor.parse_cleanup_arg(args)
        assert result is None
    
    def test_parse_arg_without_value(self):
        """测试参数没有值"""
        args = ["app.exe", "--cleanup-old"]
        result = UpdateExecutor.parse_cleanup_arg(args)
        assert result is None
    
    def test_parse_arg_with_other_flag(self):
        """测试参数值是另一个标志"""
        args = ["app.exe", "--cleanup-old", "--other-flag"]
        result = UpdateExecutor.parse_cleanup_arg(args)
        assert result is None
    
    @given(st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=10))
    @settings(max_examples=100)
    def test_parse_random_args(self, random_args: List[str]):
        """测试随机参数列表"""
        # 不应该崩溃
        result = UpdateExecutor.parse_cleanup_arg(random_args)
        
        # 结果应该是 None 或字符串
        assert result is None or isinstance(result, str)


# ========== 启动新版本测试 ==========

class TestLaunchNewVersion:
    """启动新版本测试"""
    
    def test_launch_in_dev_environment(self):
        """测试开发环境跳过启动"""
        with patch.object(sys, 'frozen', False, create=True):
            success, msg = UpdateExecutor.launch_new_version(
                "new.exe", "old.exe"
            )
            assert success == True
            assert "开发环境" in msg
    
    def test_launch_nonexistent_file(self):
        """测试启动不存在的文件"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch('os.path.exists', return_value=False):
                success, msg = UpdateExecutor.launch_new_version(
                    "nonexistent.exe", "old.exe"
                )
                assert success == False
                assert "不存在" in msg
    
    def test_launch_invalid_filename(self):
        """测试启动无效文件名"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch('os.path.exists', return_value=True):
                success, msg = UpdateExecutor.launch_new_version(
                    "invalid.exe", "old.exe"
                )
                assert success == False
                assert "无效" in msg
    
    def test_launch_success(self):
        """测试成功启动"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch('os.path.exists', return_value=True):
                with patch('subprocess.Popen') as mock_popen:
                    success, msg = UpdateExecutor.launch_new_version(
                        "C:\\test\\HuGeScreenshot-2.0.0.exe",
                        "C:\\test\\HuGeScreenshot-1.0.0.exe"
                    )
                    assert success == True
                    assert msg == ""
                    assert mock_popen.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
