"""
打包脚本测试 - OpenVINO Only

从 v1.9.0 开始，统一使用 OpenVINO 后端，只生成一个 EXE 文件。

测试 BuildLogger、EnvironmentManager 和 BuildScript 的核心功能。
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from hypothesis import given, strategies as st, settings

# 添加 build 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "build"))

from build import (
    ValidationResult,
    BuildResult,
    BuildLogger,
    EnvironmentManager,
    REQUIRED_PACKAGES,
    REQUIRED_MODULES,
)


# ============================================================
# BuildLogger 测试
# ============================================================

class TestBuildLogger:
    """BuildLogger 单元测试"""
    
    def test_log_creates_message(self, tmp_path):
        """测试日志记录"""
        logger = BuildLogger(log_dir=str(tmp_path))
        logger.start_build()
        logger.log("测试消息")
        logger.finish_build(True)
        
        # 验证日志文件存在
        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) == 1
        
        # 验证日志内容
        content = log_files[0].read_text(encoding="utf-8")
        assert "测试消息" in content
    
    def test_log_error(self, tmp_path):
        """测试错误日志"""
        logger = BuildLogger(log_dir=str(tmp_path))
        logger.start_build()
        logger.log_error("测试错误")
        logger.finish_build(False)
        
        log_files = list(tmp_path.glob("*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "测试错误" in content
        assert "[ERROR]" in content
    
    def test_log_success(self, tmp_path):
        """测试成功日志"""
        logger = BuildLogger(log_dir=str(tmp_path))
        logger.start_build()
        logger.log_success("操作成功")
        logger.finish_build(True)
        
        log_files = list(tmp_path.glob("*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "操作成功" in content
        assert "[OK]" in content
    
    def test_log_warning(self, tmp_path):
        """测试警告日志"""
        logger = BuildLogger(log_dir=str(tmp_path))
        logger.start_build()
        logger.log_warning("警告信息")
        logger.finish_build(True)
        
        log_files = list(tmp_path.glob("*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "警告信息" in content
        assert "[WARN]" in content
    
    def test_log_progress(self, tmp_path):
        """测试进度日志"""
        logger = BuildLogger(log_dir=str(tmp_path))
        logger.start_build()
        logger.log_progress("正在处理...")
        logger.finish_build(True)
        
        log_files = list(tmp_path.glob("*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "正在处理..." in content
        assert "[PROGRESS]" in content


# ============================================================
# EnvironmentManager 测试
# ============================================================

class TestEnvironmentManager:
    """EnvironmentManager 单元测试"""
    
    @pytest.fixture
    def mock_logger(self):
        """创建 mock logger"""
        logger = Mock(spec=BuildLogger)
        return logger
    
    @pytest.fixture
    def env_manager(self, mock_logger):
        """创建 EnvironmentManager 实例"""
        return EnvironmentManager(mock_logger)
    
    def test_check_package_installed_returns_bool(self, env_manager):
        """测试包检查返回布尔值"""
        # 检查一个肯定存在的包
        result = env_manager.check_package_installed("pip")
        assert isinstance(result, bool)
        assert result is True
    
    def test_check_package_not_installed(self, env_manager):
        """测试检查不存在的包"""
        result = env_manager.check_package_installed("nonexistent-package-xyz")
        assert result is False
    
    def test_check_module_importable_returns_bool(self, env_manager):
        """测试模块导入检查返回布尔值"""
        # 检查一个肯定存在的模块
        result = env_manager.check_module_importable("sys")
        assert isinstance(result, bool)
        assert result is True
    
    def test_check_module_not_importable(self, env_manager):
        """测试检查不存在的模块"""
        result = env_manager.check_module_importable("nonexistent_module_xyz")
        assert result is False


# ============================================================
# EnvironmentManager 属性测试
# ============================================================

class TestEnvironmentManagerProperties:
    """EnvironmentManager 属性测试"""
    
    @given(st.booleans())
    @settings(max_examples=50)
    def test_package_check_consistency(self, pkg_installed: bool):
        """
        Property: Package Check Consistency
        
        对于任意包安装状态，check_package_installed 应该返回一致的结果。
        """
        mock_logger = Mock(spec=BuildLogger)
        env_manager = EnvironmentManager(mock_logger)
        
        # 模拟 subprocess.run 的返回值
        with patch('build.subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0 if pkg_installed else 1
            mock_run.return_value = mock_result
            
            result = env_manager.check_package_installed("test-package")
            
            # 验证结果与模拟状态一致
            assert result == pkg_installed
    
    def test_validate_returns_validation_result(self):
        """
        Property: validate_environment 方法总是返回 ValidationResult
        """
        mock_logger = Mock(spec=BuildLogger)
        env_manager = EnvironmentManager(mock_logger)
        
        with patch.object(env_manager, 'check_package_installed', return_value=True):
            with patch.object(env_manager, 'check_module_importable', return_value=True):
                result = env_manager.validate_environment()
                
                # 验证返回类型
                assert isinstance(result, ValidationResult)
                assert isinstance(result.success, bool)
                assert isinstance(result.errors, list)
                assert isinstance(result.warnings, list)


# ============================================================
# 数据模型测试
# ============================================================

class TestDataModels:
    """数据模型测试"""
    
    def test_validation_result_defaults(self):
        """测试 ValidationResult 默认值"""
        result = ValidationResult(success=True)
        assert result.success is True
        assert result.errors == []
        assert result.warnings == []
    
    def test_build_result_defaults(self):
        """测试 BuildResult 默认值"""
        result = BuildResult(success=True)
        assert result.success is True
        assert result.exe_path is None
        assert result.duration_seconds == 0.0
        assert result.log_file == ""
    
    def test_build_result_with_values(self):
        """测试 BuildResult 带值"""
        result = BuildResult(
            success=True,
            exe_path="dist/test.exe",
            duration_seconds=10.5,
            log_file="build.log"
        )
        assert result.success is True
        assert result.exe_path == "dist/test.exe"
        assert result.duration_seconds == 10.5
        assert result.log_file == "build.log"


# ============================================================
# 配置常量测试
# ============================================================

class TestConfigConstants:
    """配置常量测试 - OpenVINO Only"""
    
    def test_required_packages_openvino_only(self):
        """测试必需包只包含 OpenVINO"""
        assert "rapidocr-openvino" in REQUIRED_PACKAGES
        # 确保没有 ONNX Runtime 相关包
        assert "rapidocr-onnxruntime" not in REQUIRED_PACKAGES
    
    def test_required_modules_openvino_only(self):
        """测试必需模块只包含 OpenVINO"""
        assert "rapidocr_openvino" in REQUIRED_MODULES
        assert "openvino" in REQUIRED_MODULES
        # 确保没有 ONNX Runtime 相关模块
        assert "onnxruntime" not in REQUIRED_MODULES
        assert "onnxruntime_directml" not in REQUIRED_MODULES
    
    def test_no_build_type_enum(self):
        """测试不存在 BuildType 枚举（已移除双版本支持）"""
        # 确保 build.py 中没有 BuildType
        try:
            from build import BuildType
            pytest.fail("BuildType should not exist in OpenVINO-only build")
        except ImportError:
            pass  # 预期行为
    
    def test_no_conflicting_packages_constants(self):
        """测试不存在冲突包常量（已移除双版本支持）"""
        try:
            from build import GENERAL_CONFLICTING_PACKAGES
            pytest.fail("GENERAL_CONFLICTING_PACKAGES should not exist")
        except ImportError:
            pass
        
        try:
            from build import INTEL_CONFLICTING_PACKAGES
            pytest.fail("INTEL_CONFLICTING_PACKAGES should not exist")
        except ImportError:
            pass
