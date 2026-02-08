# =====================================================
# =============== 保存文件夹配置测试 ===============
# =====================================================

"""
保存文件夹配置属性测试

Feature: save-to-folder-dialog
Property 2: Configuration Round-Trip

*For any* valid folder path, after saving a screenshot to that folder
and reloading the configuration, the last_save_folder field should
contain the same folder path.

Validates: Requirements 2.1, 2.3
"""

import os
import pytest
from hypothesis import given, strategies as st, settings

from screenshot_tool.core.config_manager import AppConfig


# ========== 策略定义 ==========

# 有效的文件夹路径策略（Windows 风格）
# 生成类似 C:\Users\test\Pictures 的路径
folder_path_strategy = st.one_of(
    st.just(""),  # 空路径
    st.just("C:\\Users\\test\\Pictures"),
    st.just("D:\\Screenshots"),
    st.just("C:\\Users\\test\\Documents\\截图"),
    st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"),
        min_size=1,
        max_size=20
    ).map(lambda s: f"C:\\Users\\test\\{s}"),
)


class TestLastSaveFolderUnit:
    """last_save_folder 单元测试"""
    
    def test_default_value(self):
        """测试默认值为空字符串"""
        config = AppConfig()
        assert config.last_save_folder == ""
    
    def test_set_value(self):
        """测试设置值"""
        config = AppConfig()
        config.last_save_folder = "C:\\Users\\test\\Pictures"
        assert config.last_save_folder == "C:\\Users\\test\\Pictures"
    
    def test_chinese_path(self):
        """测试中文路径"""
        config = AppConfig()
        config.last_save_folder = "C:\\Users\\test\\文档\\截图"
        assert config.last_save_folder == "C:\\Users\\test\\文档\\截图"
    
    def test_to_dict_includes_last_save_folder(self):
        """测试 to_dict 包含 last_save_folder"""
        config = AppConfig()
        config.last_save_folder = "D:\\Screenshots"
        
        d = config.to_dict()
        
        assert "last_save_folder" in d
        assert d["last_save_folder"] == "D:\\Screenshots"
    
    def test_from_dict_loads_last_save_folder(self):
        """测试 from_dict 加载 last_save_folder"""
        data = {
            "last_save_folder": "C:\\Users\\test\\Pictures\\Screenshots"
        }
        
        config = AppConfig.from_dict(data)
        
        assert config.last_save_folder == "C:\\Users\\test\\Pictures\\Screenshots"
    
    def test_from_dict_missing_uses_default(self):
        """测试 from_dict 缺少字段时使用默认值"""
        config = AppConfig.from_dict({})
        
        assert config.last_save_folder == ""


class TestLastSaveFolderProperties:
    """last_save_folder 属性测试
    
    Feature: save-to-folder-dialog
    """
    
    @given(folder_path=folder_path_strategy)
    @settings(max_examples=100)
    def test_property_config_round_trip(self, folder_path: str):
        """
        Property 2: Configuration Round-Trip
        
        *For any* valid folder path, serializing to dict and deserializing
        back SHALL produce an equivalent configuration.
        
        **Feature: save-to-folder-dialog, Property 2: Configuration Round-Trip**
        **Validates: Requirements 2.1, 2.3**
        """
        # 创建原始配置
        original = AppConfig()
        original.last_save_folder = folder_path
        
        # 序列化为字典
        data = original.to_dict()
        
        # 从字典反序列化
        restored = AppConfig.from_dict(data)
        
        # 验证等价性
        assert restored.last_save_folder == original.last_save_folder
    
    @given(
        folder_path=folder_path_strategy,
        save_path=folder_path_strategy,
    )
    @settings(max_examples=50)
    def test_property_independent_of_save_path(self, folder_path: str, save_path: str):
        """
        Property: last_save_folder Independent of save_path
        
        *For any* combination of last_save_folder and save_path values,
        they SHALL be stored and retrieved independently.
        
        **Feature: save-to-folder-dialog**
        **Validates: Requirements 2.1, 2.3**
        """
        # 创建配置
        original = AppConfig()
        original.last_save_folder = folder_path
        original.save_path = save_path
        
        # 序列化
        data = original.to_dict()
        
        # 反序列化
        restored = AppConfig.from_dict(data)
        
        # 验证两个字段独立
        assert restored.last_save_folder == folder_path
        assert restored.save_path == save_path
