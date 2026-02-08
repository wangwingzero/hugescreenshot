# =====================================================
# =============== 时间戳文件名测试 ===============
# =====================================================

"""
时间戳文件名生成属性测试

Feature: save-to-folder-dialog
Property 3: Timestamp Filename Generation
Property 5: Filename Uniqueness

Validates: Requirements 3.1, 3.2, 3.3
"""

import os
import re
import tempfile
import shutil
from datetime import datetime, timedelta
import pytest
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.core.file_manager import FileManager


# ========== 策略定义 ==========

# 有效的时间戳策略
timestamp_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31)
)


class TestTimestampFilenameUnit:
    """时间戳文件名单元测试"""
    
    def setup_method(self):
        """每个测试前创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.file_manager = FileManager()
    
    def teardown_method(self):
        """每个测试后清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_basic_filename_format(self):
        """测试基本文件名格式"""
        timestamp = datetime(2026, 1, 8, 14, 30, 52)
        filepath = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        
        filename = os.path.basename(filepath)
        assert filename == "截图_20260108_143052.png"
    
    def test_filename_in_correct_folder(self):
        """测试文件名在正确的文件夹中"""
        filepath = self.file_manager.generate_timestamp_filename(self.temp_dir)
        
        assert os.path.dirname(filepath) == self.temp_dir
    
    def test_filename_pattern_match(self):
        """测试文件名匹配模式"""
        filepath = self.file_manager.generate_timestamp_filename(self.temp_dir)
        filename = os.path.basename(filepath)
        
        pattern = r"截图_\d{8}_\d{6}\.png"
        assert re.match(pattern, filename) is not None
    
    def test_collision_handling(self):
        """测试文件名冲突处理"""
        timestamp = datetime(2026, 1, 8, 14, 30, 52)
        
        # 创建第一个文件
        filepath1 = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        # 创建空文件模拟已存在
        with open(filepath1, 'w') as f:
            f.write("")
        
        # 生成第二个文件名（同一时间戳）
        filepath2 = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        
        # 应该添加序号
        filename2 = os.path.basename(filepath2)
        assert filename2 == "截图_20260108_143052_1.png"
        assert filepath1 != filepath2
    
    def test_multiple_collisions(self):
        """测试多次文件名冲突"""
        timestamp = datetime(2026, 1, 8, 14, 30, 52)
        
        # 创建多个同时间戳的文件
        for i in range(3):
            filepath = self.file_manager.generate_timestamp_filename(
                self.temp_dir, timestamp
            )
            with open(filepath, 'w') as f:
                f.write("")
        
        # 第四个文件应该是 _3
        filepath4 = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        filename4 = os.path.basename(filepath4)
        assert filename4 == "截图_20260108_143052_3.png"
    
    def test_default_timestamp_is_now(self):
        """测试默认时间戳为当前时间"""
        before = datetime.now()
        filepath = self.file_manager.generate_timestamp_filename(self.temp_dir)
        after = datetime.now()
        
        filename = os.path.basename(filepath)
        # 提取时间戳部分
        match = re.match(r"截图_(\d{8}_\d{6})\.png", filename)
        assert match is not None
        
        time_str = match.group(1)
        file_time = datetime.strptime(time_str, "%Y%m%d_%H%M%S")
        
        # 文件时间应该在 before 和 after 之间
        assert before.replace(microsecond=0) <= file_time <= after.replace(microsecond=0) + timedelta(seconds=1)


class TestTimestampFilenameProperties:
    """时间戳文件名属性测试
    
    Feature: save-to-folder-dialog
    """
    
    def setup_method(self):
        """每个测试前创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.file_manager = FileManager()
    
    def teardown_method(self):
        """每个测试后清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @given(timestamp=timestamp_strategy)
    @settings(max_examples=100)
    def test_property_timestamp_format(self, timestamp: datetime):
        """
        Property 3: Timestamp Filename Generation
        
        *For any* save operation, the generated filename should match
        the pattern 截图_YYYYMMDD_HHMMSS.png where the timestamp
        reflects the provided time.
        
        **Feature: save-to-folder-dialog, Property 3: Timestamp Filename Generation**
        **Validates: Requirements 3.1, 3.2**
        """
        filepath = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        filename = os.path.basename(filepath)
        
        # 验证格式
        pattern = r"截图_(\d{8}_\d{6})(?:_\d+)?\.png"
        match = re.match(pattern, filename)
        assert match is not None, f"文件名 {filename} 不匹配模式"
        
        # 验证时间戳正确
        time_str = match.group(1)
        expected_time_str = timestamp.strftime("%Y%m%d_%H%M%S")
        assert time_str == expected_time_str, f"时间戳 {time_str} != {expected_time_str}"
    
    @given(timestamp=timestamp_strategy)
    @settings(max_examples=50)
    def test_property_filename_uniqueness(self, timestamp: datetime):
        """
        Property 5: Filename Uniqueness
        
        *For any* folder containing existing screenshot files,
        generating a new filename should produce a unique filename
        that does not conflict with existing files.
        
        **Feature: save-to-folder-dialog, Property 5: Filename Uniqueness**
        **Validates: Requirements 3.3**
        """
        # 创建一个已存在的文件
        filepath1 = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        with open(filepath1, 'w') as f:
            f.write("test")
        
        # 生成新文件名
        filepath2 = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        
        # 验证唯一性
        assert filepath1 != filepath2, "生成的文件名应该唯一"
        assert not os.path.exists(filepath2), "新文件名不应该已存在"
    
    @given(
        timestamp=timestamp_strategy,
        num_existing=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50)
    def test_property_uniqueness_with_multiple_files(
        self, timestamp: datetime, num_existing: int
    ):
        """
        Property 5: Filename Uniqueness (Multiple Files)
        
        *For any* number of existing files with the same timestamp,
        the next generated filename should be unique.
        
        **Feature: save-to-folder-dialog, Property 5: Filename Uniqueness**
        **Validates: Requirements 3.3**
        """
        # 创建多个已存在的文件
        existing_files = []
        for _ in range(num_existing):
            filepath = self.file_manager.generate_timestamp_filename(
                self.temp_dir, timestamp
            )
            with open(filepath, 'w') as f:
                f.write("test")
            existing_files.append(filepath)
        
        # 生成新文件名
        new_filepath = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        
        # 验证唯一性
        assert new_filepath not in existing_files, "新文件名不应该与已存在的文件重复"
        assert not os.path.exists(new_filepath), "新文件名不应该已存在"
    
    @given(timestamp=timestamp_strategy)
    @settings(max_examples=30)
    def test_property_filepath_in_folder(self, timestamp: datetime):
        """
        Property: Filepath in Correct Folder
        
        *For any* timestamp, the generated filepath should be
        in the specified folder.
        
        **Feature: save-to-folder-dialog**
        **Validates: Requirements 1.4**
        """
        filepath = self.file_manager.generate_timestamp_filename(
            self.temp_dir, timestamp
        )
        
        assert os.path.dirname(filepath) == self.temp_dir
