# =====================================================
# =============== OpenVINO 优化器测试 ===============
# =====================================================

"""
测试 OpenVINO 优化器的配置功能

测试内容：
- OpenVINOConfig 数据类
- Performance Hints 配置
- 模型缓存目录配置
- 环境变量覆盖
- 错误处理和优雅降级
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from screenshot_tool.services.openvino_optimizer import (
    OpenVINOConfig,
    DEFAULT_CACHE_CAPACITY,
    DEFAULT_PERFORMANCE_HINT,
    DEFAULT_MODEL_CACHE_DIR,
    is_openvino_available,
    reset_core,
    get_global_config,
)


class TestOpenVINOConfig:
    """测试 OpenVINOConfig 数据类"""
    
    def test_default_values(self):
        """测试默认值"""
        config = OpenVINOConfig()
        
        assert config.cache_capacity == DEFAULT_CACHE_CAPACITY
        assert config.performance_hint == DEFAULT_PERFORMANCE_HINT
        assert config.enable_model_cache is True
    
    def test_custom_values(self):
        """测试自定义值"""
        config = OpenVINOConfig(
            cache_capacity=10,
            performance_hint="THROUGHPUT",
            model_cache_dir="/custom/path",
            enable_model_cache=False,
        )
        
        assert config.cache_capacity == 10
        assert config.performance_hint == "THROUGHPUT"
        assert config.model_cache_dir == "/custom/path"
        assert config.enable_model_cache is False
    
    def test_env_override_cache_capacity(self):
        """测试环境变量覆盖 cache_capacity"""
        with patch.dict(os.environ, {"OPENVINO_CPU_CACHE_CAPACITY": "20"}):
            config = OpenVINOConfig()
            assert config.cache_capacity == 20
    
    def test_env_override_cache_dir(self):
        """测试环境变量覆盖 cache_dir"""
        with patch.dict(os.environ, {"SCREENSHOT_OCR_CACHE_DIR": "/env/cache"}):
            config = OpenVINOConfig()
            assert config.model_cache_dir == "/env/cache"
    
    def test_env_override_performance_hint(self):
        """测试环境变量覆盖 performance_hint"""
        with patch.dict(os.environ, {"SCREENSHOT_OCR_PERFORMANCE_HINT": "THROUGHPUT"}):
            config = OpenVINOConfig()
            assert config.performance_hint == "THROUGHPUT"
    
    def test_env_invalid_cache_capacity(self):
        """测试无效的环境变量值不会崩溃"""
        with patch.dict(os.environ, {"OPENVINO_CPU_CACHE_CAPACITY": "invalid"}):
            config = OpenVINOConfig()
            # 应该保持默认值
            assert config.cache_capacity == DEFAULT_CACHE_CAPACITY
    
    def test_env_invalid_performance_hint(self):
        """测试无效的 performance_hint 值不会覆盖"""
        with patch.dict(os.environ, {"SCREENSHOT_OCR_PERFORMANCE_HINT": "INVALID"}):
            config = OpenVINOConfig()
            # 应该保持默认值
            assert config.performance_hint == DEFAULT_PERFORMANCE_HINT
    
    def test_get_resolved_cache_dir(self):
        """测试缓存目录路径解析"""
        config = OpenVINOConfig(model_cache_dir="~/.test_cache")
        resolved = config.get_resolved_cache_dir()
        
        assert resolved is not None
        assert "~" not in str(resolved)
        assert resolved == Path.home() / ".test_cache"
    
    def test_get_resolved_cache_dir_disabled(self):
        """测试禁用缓存时返回 None"""
        config = OpenVINOConfig(enable_model_cache=False)
        assert config.get_resolved_cache_dir() is None
    
    def test_get_resolved_cache_dir_none(self):
        """测试 cache_dir 为 None 时使用默认值"""
        config = OpenVINOConfig()
        resolved = config.get_resolved_cache_dir()
        
        assert resolved is not None
        expected = Path(DEFAULT_MODEL_CACHE_DIR).expanduser()
        assert resolved == expected


class TestOpenVINOAvailability:
    """测试 OpenVINO 可用性检测"""
    
    def test_is_openvino_available_returns_bool(self):
        """测试返回布尔值"""
        result = is_openvino_available()
        assert isinstance(result, bool)


class TestCoreReset:
    """测试 Core 重置功能"""
    
    def test_reset_core_clears_config(self):
        """测试重置后配置被清除"""
        reset_core()
        # 重置后全局配置应该为 None
        assert get_global_config() is None


class TestCacheDirectoryCreation:
    """测试缓存目录创建"""
    
    def test_cache_dir_creation(self):
        """测试缓存目录自动创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache" / "nested"
            config = OpenVINOConfig(model_cache_dir=str(cache_path))
            
            resolved = config.get_resolved_cache_dir()
            assert resolved == cache_path
            
            # 目录应该在 Core 初始化时创建，这里只测试路径解析
            assert not cache_path.exists()  # 还没创建


class TestEnvironmentVariablePriority:
    """测试环境变量优先级"""
    
    def test_env_overrides_constructor_args(self):
        """测试环境变量覆盖构造函数参数"""
        with patch.dict(os.environ, {"SCREENSHOT_OCR_CACHE_DIR": "/env/path"}):
            # 即使传入了 model_cache_dir，环境变量也会覆盖
            config = OpenVINOConfig(model_cache_dir="/constructor/path")
            assert config.model_cache_dir == "/env/path"
    
    def test_clear_env_uses_default(self):
        """测试清除环境变量后使用默认值"""
        # 确保环境变量不存在
        env_vars = {
            "OPENVINO_CPU_CACHE_CAPACITY": "",
            "SCREENSHOT_OCR_CACHE_DIR": "",
            "SCREENSHOT_OCR_PERFORMANCE_HINT": "",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            # 移除这些环境变量
            for key in env_vars:
                os.environ.pop(key, None)
            
            config = OpenVINOConfig()
            assert config.cache_capacity == DEFAULT_CACHE_CAPACITY
            assert config.performance_hint == DEFAULT_PERFORMANCE_HINT
