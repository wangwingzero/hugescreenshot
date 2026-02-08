# =====================================================
# =============== OCR 后端兼容性测试 ===============
# =====================================================

"""
OCR 后端兼容性属性测试 - OpenVINO Only

从 v1.9.0 开始，统一使用 OpenVINO 后端。

Property 1: Backend Always Returns OpenVINO
Property 2: OpenVINO Availability Check
Property 3: Backend Info Correctness

Validates: Requirements 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.3, 4.4
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

from screenshot_tool.services.backend_selector import (
    BackendSelector,
    BackendType,
    BackendInfo,
    get_backend_display_string,
)


class TestBackendSelectorUnit:
    """BackendSelector 单元测试"""
    
    def setup_method(self):
        """每个测试前清除缓存"""
        BackendSelector.clear_cache()
    
    def teardown_method(self):
        """每个测试后清理"""
        BackendSelector.clear_cache()
    
    def test_backend_type_only_openvino(self):
        """测试 BackendType 只有 OpenVINO"""
        assert hasattr(BackendType, 'OPENVINO')
        assert not hasattr(BackendType, 'ONNX_RUNTIME')
        assert not hasattr(BackendType, 'DIRECTML')
    
    def test_select_best_backend_returns_openvino(self):
        """测试 select_best_backend 始终返回 OpenVINO"""
        result = BackendSelector.select_best_backend()
        assert result == BackendType.OPENVINO
    
    def test_detect_cpu_vendor_returns_valid_value(self):
        """测试 CPU 厂商检测返回有效值"""
        vendor = BackendSelector.detect_cpu_vendor()
        assert vendor in ["Intel", "AMD", "ARM", "Unknown"]
    
    def test_is_openvino_available_returns_bool(self):
        """测试 is_openvino_available 返回布尔值"""
        result = BackendSelector.is_openvino_available()
        assert isinstance(result, bool)
    
    def test_get_backend_info_returns_correct_type(self):
        """测试 get_backend_info 返回正确类型"""
        info = BackendSelector.get_backend_info()
        assert isinstance(info, BackendInfo)
        assert info.backend_type == BackendType.OPENVINO
    
    def test_backend_info_has_required_fields(self):
        """测试 BackendInfo 包含必需字段"""
        info = BackendSelector.get_backend_info()
        assert hasattr(info, 'backend_type')
        assert hasattr(info, 'cpu_vendor')
        assert hasattr(info, 'openvino_available')
        assert hasattr(info, 'openvino_version')
        assert hasattr(info, 'performance_hint')
        assert hasattr(info, 'cache_enabled')
        assert hasattr(info, 'cache_dir')
    
    def test_backend_info_no_amd_fields(self):
        """测试 BackendInfo 不包含 AMD 相关字段"""
        info = BackendSelector.get_backend_info()
        assert not hasattr(info, 'is_amd_cpu')
        assert not hasattr(info, 'is_intel_cpu')
        assert not hasattr(info, 'onnx_available')
        assert not hasattr(info, 'directml_available')
        assert not hasattr(info, 'thread_count')
        assert not hasattr(info, 'use_directml')
    
    def test_backend_info_to_dict(self):
        """测试 BackendInfo.to_dict() 方法"""
        info = BackendSelector.get_backend_info()
        d = info.to_dict()
        assert isinstance(d, dict)
        assert 'backend_type' in d
        assert d['backend_type'] == 'openvino'
    
    def test_get_backend_display_string(self):
        """测试 get_backend_display_string 函数"""
        display = get_backend_display_string()
        assert isinstance(display, str)
        assert 'OpenVINO' in display
    
    def test_get_backend_display_string_with_hint(self):
        """测试带 performance_hint 的显示字符串"""
        info = BackendInfo(
            backend_type=BackendType.OPENVINO,
            cpu_vendor="Intel",
            openvino_available=True,
            performance_hint="LATENCY"
        )
        display = get_backend_display_string(info)
        assert display == "OpenVINO (LATENCY)"
    
    def test_get_backend_display_string_without_hint(self):
        """测试不带 performance_hint 的显示字符串"""
        info = BackendInfo(
            backend_type=BackendType.OPENVINO,
            cpu_vendor="AMD",
            openvino_available=True,
            performance_hint=None
        )
        display = get_backend_display_string(info)
        assert display == "OpenVINO"
    
    def test_clear_cache_works(self):
        """测试缓存清除功能"""
        # 先调用一次以填充缓存
        BackendSelector.detect_cpu_vendor()
        BackendSelector.is_openvino_available()
        
        # 清除缓存
        BackendSelector.clear_cache()
        
        # 再次调用应该重新检测
        vendor = BackendSelector.detect_cpu_vendor()
        assert vendor in ["Intel", "AMD", "ARM", "Unknown"]


class TestBackendSelectorProperties:
    """BackendSelector 属性测试
    
    Feature: openvino-only-backend
    """
    
    def setup_method(self):
        BackendSelector.clear_cache()
    
    def teardown_method(self):
        BackendSelector.clear_cache()
    
    @given(cpu_type=st.sampled_from(["Intel", "AMD", "ARM", "Unknown"]))
    @settings(max_examples=10)
    def test_property_1_backend_always_returns_openvino(self, cpu_type):
        """
        Property 1: Backend Always Returns OpenVINO
        
        *For any* CPU type, select_best_backend() SHALL always return
        BackendType.OPENVINO.
        
        **Validates: Requirements 2.5, 4.2**
        """
        # Feature: openvino-only-backend, Property 1: Backend Always Returns OpenVINO
        with patch.object(BackendSelector, 'detect_cpu_vendor', return_value=cpu_type):
            BackendSelector.clear_cache()
            result = BackendSelector.select_best_backend()
            
            assert result == BackendType.OPENVINO, \
                f"Backend should always be OpenVINO, got {result} for CPU type {cpu_type}"
    
    @given(openvino_available=st.booleans())
    @settings(max_examples=5, deadline=500)
    def test_property_2_openvino_availability_check(self, openvino_available):
        """
        Property 2: OpenVINO Availability Check
        
        *For any* OpenVINO availability state, the backend info SHALL
        correctly reflect the availability.
        
        **Validates: Requirements 4.3, 4.4**
        """
        # Feature: openvino-only-backend, Property 2: OpenVINO Availability Check
        with patch.object(BackendSelector, 'is_openvino_available', return_value=openvino_available):
            BackendSelector.clear_cache()
            info = BackendSelector.get_backend_info()
            
            assert info.openvino_available == openvino_available, \
                f"OpenVINO availability should be {openvino_available}, got {info.openvino_available}"
    
    @given(
        cpu_type=st.sampled_from(["Intel", "AMD", "ARM", "Unknown"]),
        openvino_available=st.booleans(),
    )
    @settings(max_examples=10)
    def test_property_3_backend_info_correctness(self, cpu_type, openvino_available):
        """
        Property 3: Backend Info Correctness
        
        *For any* combination of CPU type and OpenVINO availability,
        the backend info SHALL contain correct values.
        
        **Validates: Requirements 4.3, 4.4, 4.6, 4.7, 4.8, 4.9**
        """
        # Feature: openvino-only-backend, Property 3: Backend Info Correctness
        with patch.object(BackendSelector, 'detect_cpu_vendor', return_value=cpu_type):
            with patch.object(BackendSelector, 'is_openvino_available', return_value=openvino_available):
                BackendSelector.clear_cache()
                info = BackendSelector.get_backend_info()
                
                # 验证后端类型始终是 OpenVINO
                assert info.backend_type == BackendType.OPENVINO, \
                    f"Backend type should be OpenVINO, got {info.backend_type}"
                
                # 验证 CPU 厂商
                assert info.cpu_vendor == cpu_type, \
                    f"CPU vendor should be {cpu_type}, got {info.cpu_vendor}"
                
                # 验证 OpenVINO 可用性
                assert info.openvino_available == openvino_available, \
                    f"OpenVINO availability should be {openvino_available}"


class TestModuleIsolation:
    """模块隔离测试
    
    Feature: openvino-only-backend
    """
    
    def test_clean_conflicting_modules_exists(self):
        """
        测试 clean_conflicting_modules 函数存在
        
        **Validates: Requirements 4.1**
        """
        from screenshot_tool.services.rapid_ocr_service import clean_conflicting_modules
        assert callable(clean_conflicting_modules)
    
    def test_clean_conflicting_modules_returns_count(self):
        """
        测试 clean_conflicting_modules 返回清理的模块数量
        
        **Validates: Requirements 4.1, 4.2**
        """
        from screenshot_tool.services.rapid_ocr_service import clean_conflicting_modules
        
        # 第一次调用可能清理一些模块
        count1 = clean_conflicting_modules()
        assert isinstance(count1, int)
        assert count1 >= 0
        
        # 第二次调用应该返回 0（已经清理过了）
        count2 = clean_conflicting_modules()
        assert count2 == 0
