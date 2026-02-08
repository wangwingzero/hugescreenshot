# =====================================================
# =============== 清单服务测试 ===============
# =====================================================

"""
清单服务属性测试

Feature: installer-incremental-update
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from datetime import datetime, timezone

from screenshot_tool.services.manifest_service import (
    FileEntry, Manifest, DeltaResult, ManifestGenerator, DeltaCalculator
)


# ========== 策略定义 ==========

# 有效的文件路径（不含特殊字符）
valid_path = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789_-./'),
    min_size=1,
    max_size=100
).filter(lambda x: not x.startswith('/') and '..' not in x and '//' not in x)

# 有效的 SHA-256 哈希（64 字符十六进制）
valid_hash = st.text(
    alphabet='0123456789abcdef',
    min_size=64,
    max_size=64
)

# 有效的文件大小
valid_size = st.integers(min_value=0, max_value=10**12)

# 有效的版本号
valid_version = st.from_regex(r'[0-9]+\.[0-9]+\.[0-9]+', fullmatch=True)

# 有效的 ISO 8601 时间戳
valid_build_time = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31)
).map(lambda dt: dt.replace(tzinfo=timezone.utc).isoformat())


# 有效的 FileEntry
@st.composite
def valid_file_entry(draw):
    return FileEntry(
        path=draw(valid_path),
        size=draw(valid_size),
        hash=draw(valid_hash)
    )


# 有效的 Manifest
@st.composite
def valid_manifest(draw):
    files = draw(st.lists(valid_file_entry(), min_size=0, max_size=50))
    # 确保路径唯一
    seen_paths = set()
    unique_files = []
    for f in files:
        if f.path not in seen_paths:
            seen_paths.add(f.path)
            unique_files.append(f)
    
    return Manifest(
        version=draw(valid_version),
        build_time=draw(valid_build_time),
        files=unique_files
    )


# ========== Property 1: Manifest Format Validation ==========
# Feature: installer-incremental-update, Property 1: Manifest Format Validation
# Validates: Requirements 3.1, 3.2, 3.4

class TestManifestFormatValidation:
    """清单格式验证属性测试"""
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_manifest_has_valid_version(self, manifest: Manifest):
        """清单必须包含有效的版本号"""
        assert manifest.version
        assert isinstance(manifest.version, str)
        # 版本号格式: X.Y.Z
        parts = manifest.version.split('.')
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_manifest_has_valid_build_time(self, manifest: Manifest):
        """清单必须包含有效的 ISO 8601 构建时间"""
        assert manifest.build_time
        # 应该能解析为 datetime
        dt = datetime.fromisoformat(manifest.build_time.replace('Z', '+00:00'))
        assert dt is not None
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_manifest_files_have_valid_entries(self, manifest: Manifest):
        """清单中每个文件条目必须有效"""
        for file_entry in manifest.files:
            # 路径非空
            assert file_entry.path
            assert isinstance(file_entry.path, str)
            # 大小非负
            assert file_entry.size >= 0
            # 哈希是 64 字符十六进制
            assert len(file_entry.hash) == 64
            assert all(c in '0123456789abcdef' for c in file_entry.hash.lower())
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_manifest_total_size_equals_sum(self, manifest: Manifest):
        """清单总大小等于所有文件大小之和"""
        expected_total = sum(f.size for f in manifest.files)
        assert manifest.total_size == expected_total
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_manifest_serializes_to_valid_json(self, manifest: Manifest):
        """清单序列化为有效的 JSON"""
        json_str = manifest.to_json()
        # 应该是有效的 JSON
        data = json.loads(json_str)
        assert 'version' in data
        assert 'build_time' in data
        assert 'files' in data
        assert 'total_size' in data


# ========== Property 2: Manifest Round-Trip Consistency ==========
# Feature: installer-incremental-update, Property 2: Manifest Round-Trip Consistency
# Validates: Requirements 3.4

class TestManifestRoundTrip:
    """清单序列化/反序列化 round-trip 测试"""
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_json_round_trip(self, manifest: Manifest):
        """序列化后反序列化应得到等价对象"""
        json_str = manifest.to_json()
        restored = Manifest.from_json(json_str)
        
        # 版本和时间相等
        assert restored.version == manifest.version
        assert restored.build_time == manifest.build_time
        assert restored.total_size == manifest.total_size
        
        # 文件列表相等
        assert len(restored.files) == len(manifest.files)
        for orig, rest in zip(manifest.files, restored.files):
            assert rest.path == orig.path
            assert rest.size == orig.size
            assert rest.hash == orig.hash
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100)
    def test_dict_round_trip(self, manifest: Manifest):
        """to_dict 后 from_dict 应得到等价对象"""
        data = manifest.to_dict()
        restored = Manifest.from_dict(data)
        
        assert restored.version == manifest.version
        assert restored.build_time == manifest.build_time
        assert len(restored.files) == len(manifest.files)



# ========== Property 3: Delta Calculation Correctness ==========
# Feature: installer-incremental-update, Property 3: Delta Calculation Correctness
# Validates: Requirements 4.2, 4.3

class TestDeltaCalculationCorrectness:
    """增量计算正确性属性测试"""
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delta_covers_all_files(self, local: Manifest, remote: Manifest):
        """增量计算应覆盖所有文件"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        # 所有远程文件应该在 added + modified + unchanged 中
        remote_paths = remote.get_all_paths()
        delta_remote_paths = (
            {f.path for f in delta.added_files} |
            {f.path for f in delta.modified_files} |
            set(delta.unchanged_files)
        )
        assert remote_paths == delta_remote_paths
        
        # 所有本地独有文件应该在 deleted 中
        local_paths = local.get_all_paths()
        for path in local_paths:
            if path not in remote_paths:
                assert path in delta.deleted_files
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_added_files_not_in_local(self, local: Manifest, remote: Manifest):
        """新增文件不应存在于本地清单"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        local_paths = local.get_all_paths()
        for added in delta.added_files:
            assert added.path not in local_paths
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_modified_files_have_different_hash(self, local: Manifest, remote: Manifest):
        """修改的文件哈希应该不同"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        for modified in delta.modified_files:
            local_file = local.get_file_by_path(modified.path)
            assert local_file is not None
            assert local_file.hash != modified.hash
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_unchanged_files_have_same_hash(self, local: Manifest, remote: Manifest):
        """未变更文件哈希应该相同"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        for path in delta.unchanged_files:
            local_file = local.get_file_by_path(path)
            remote_file = remote.get_file_by_path(path)
            assert local_file is not None
            assert remote_file is not None
            assert local_file.hash == remote_file.hash
    
    @given(manifest=valid_manifest())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_same_manifest_no_changes(self, manifest: Manifest):
        """相同清单应该没有变更"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(manifest, manifest)
        
        assert len(delta.added_files) == 0
        assert len(delta.modified_files) == 0
        assert len(delta.deleted_files) == 0
        assert len(delta.unchanged_files) == len(manifest.files)


# ========== Property 4: Delta Size Calculation ==========
# Feature: installer-incremental-update, Property 4: Delta Size Calculation
# Validates: Requirements 4.3, 4.5

class TestDeltaSizeCalculation:
    """增量大小计算属性测试"""
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100)
    def test_delta_size_equals_sum_of_changes(self, local: Manifest, remote: Manifest):
        """增量大小等于新增和修改文件大小之和"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        expected_size = (
            sum(f.size for f in delta.added_files) +
            sum(f.size for f in delta.modified_files)
        )
        assert delta.delta_size == expected_size
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100)
    def test_full_size_equals_remote_total(self, local: Manifest, remote: Manifest):
        """完整大小等于远程清单总大小"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        assert delta.full_size == remote.total_size
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100)
    def test_delta_size_not_greater_than_full(self, local: Manifest, remote: Manifest):
        """增量大小不应超过完整大小"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        # 增量大小可能等于完整大小（全部文件都变了）
        # 但不应该超过
        assert delta.delta_size <= delta.full_size
    
    @given(local=valid_manifest(), remote=valid_manifest())
    @settings(max_examples=100)
    def test_should_use_delta_threshold(self, local: Manifest, remote: Manifest):
        """增量更新推荐逻辑正确"""
        calculator = DeltaCalculator()
        delta = calculator.calculate(local, remote)
        
        if delta.full_size > 0:
            ratio = delta.delta_size / delta.full_size
            # 默认阈值 0.5
            expected = ratio < 0.5
            assert calculator.should_use_delta(delta) == expected


# ========== 单元测试 ==========

class TestFileEntryValidation:
    """FileEntry 验证测试"""
    
    def test_empty_path_raises(self):
        """空路径应该抛出异常"""
        with pytest.raises(ValueError, match="文件路径不能为空"):
            FileEntry(path="", size=100, hash="a" * 64)
    
    def test_negative_size_raises(self):
        """负数大小应该抛出异常"""
        with pytest.raises(ValueError, match="文件大小不能为负数"):
            FileEntry(path="test.txt", size=-1, hash="a" * 64)
    
    def test_invalid_hash_length_raises(self):
        """无效哈希长度应该抛出异常"""
        with pytest.raises(ValueError, match="哈希值长度必须为 64 字符"):
            FileEntry(path="test.txt", size=100, hash="abc")
    
    def test_invalid_hash_chars_raises(self):
        """无效哈希字符应该抛出异常"""
        with pytest.raises(ValueError, match="哈希值必须是有效的十六进制"):
            FileEntry(path="test.txt", size=100, hash="g" * 64)


class TestManifestValidation:
    """Manifest 验证测试"""
    
    def test_empty_version_raises(self):
        """空版本号应该抛出异常"""
        with pytest.raises(ValueError, match="版本号不能为空"):
            Manifest(version="", build_time="2026-01-13T10:00:00+00:00")
    
    def test_empty_build_time_raises(self):
        """空构建时间应该抛出异常"""
        with pytest.raises(ValueError, match="构建时间不能为空"):
            Manifest(version="1.0.0", build_time="")
    
    def test_invalid_build_time_raises(self):
        """无效构建时间应该抛出异常"""
        with pytest.raises(ValueError, match="构建时间格式无效"):
            Manifest(version="1.0.0", build_time="not-a-date")


class TestManifestGenerator:
    """ManifestGenerator 测试"""
    
    def test_calculate_file_hash(self, tmp_path):
        """测试文件哈希计算"""
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        generator = ManifestGenerator()
        hash_value = generator.calculate_file_hash(str(test_file))
        
        # SHA-256 of "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert hash_value == expected
    
    def test_generate_manifest(self, tmp_path):
        """测试清单生成"""
        # 创建测试目录结构
        (tmp_path / "app.exe").write_bytes(b"exe content")
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "module.dll").write_bytes(b"dll content")
        
        generator = ManifestGenerator()
        manifest = generator.generate(str(tmp_path), "1.0.0")
        
        assert manifest.version == "1.0.0"
        assert len(manifest.files) == 2
        
        paths = {f.path for f in manifest.files}
        assert "app.exe" in paths
        assert "lib/module.dll" in paths
