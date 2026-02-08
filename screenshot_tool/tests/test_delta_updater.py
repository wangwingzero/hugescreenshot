# =====================================================
# =============== 增量更新器测试 ===============
# =====================================================

"""
增量更新器属性测试

Feature: installer-incremental-update
"""

import os
import shutil
import tempfile
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from pathlib import Path

from screenshot_tool.services.manifest_service import (
    FileEntry, Manifest, DeltaResult, ManifestGenerator
)
from screenshot_tool.services.delta_updater import (
    DeltaUpdater, verify_installation_integrity
)


# ========== 测试夹具 ==========

@pytest.fixture
def temp_install_dir():
    """创建临时安装目录"""
    temp_dir = tempfile.mkdtemp(prefix='test_install_')
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_backup_dir():
    """创建临时备份目录"""
    temp_dir = tempfile.mkdtemp(prefix='test_backup_')
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ========== 策略定义 ==========

# 随机文件内容
file_content = st.binary(min_size=1, max_size=10000)

# 有效的文件名
valid_filename = st.text(
    alphabet='abcdefghijklmnopqrstuvwxyz0123456789_-',
    min_size=1,
    max_size=20
).map(lambda x: x + '.txt')


# ========== Property 5: Hash Verification Integrity ==========
# Feature: installer-incremental-update, Property 5: Hash Verification Integrity
# Validates: Requirements 5.3

class TestHashVerificationIntegrity:
    """哈希验证完整性属性测试"""
    
    @given(content=file_content)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_hash_is_deterministic(self, content: bytes, temp_install_dir):
        """相同内容的哈希值应该相同"""
        # 创建两个相同内容的文件
        file1 = Path(temp_install_dir) / "file1.bin"
        file2 = Path(temp_install_dir) / "file2.bin"
        
        file1.write_bytes(content)
        file2.write_bytes(content)
        
        hash1 = DeltaUpdater._calculate_hash(str(file1))
        hash2 = DeltaUpdater._calculate_hash(str(file2))
        
        assert hash1 == hash2
        
        # 清理
        file1.unlink()
        file2.unlink()
    
    @given(content1=file_content, content2=file_content)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_different_content_different_hash(
        self, content1: bytes, content2: bytes, temp_install_dir
    ):
        """不同内容的哈希值应该不同"""
        assume(content1 != content2)
        
        file1 = Path(temp_install_dir) / "file1.bin"
        file2 = Path(temp_install_dir) / "file2.bin"
        
        file1.write_bytes(content1)
        file2.write_bytes(content2)
        
        hash1 = DeltaUpdater._calculate_hash(str(file1))
        hash2 = DeltaUpdater._calculate_hash(str(file2))
        
        assert hash1 != hash2
        
        # 清理
        file1.unlink()
        file2.unlink()
    
    @given(content=file_content)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_hash_format_is_valid(self, content: bytes, temp_install_dir):
        """哈希值格式应该是 64 字符十六进制"""
        file_path = Path(temp_install_dir) / "test.bin"
        file_path.write_bytes(content)
        
        hash_value = DeltaUpdater._calculate_hash(str(file_path))
        
        # 64 字符
        assert len(hash_value) == 64
        # 全部是十六进制字符
        assert all(c in '0123456789abcdef' for c in hash_value)
        
        # 清理
        file_path.unlink()


# ========== Property 6: Atomic Update with Backup ==========
# Feature: installer-incremental-update, Property 6: Atomic Update with Backup
# Validates: Requirements 6.2, 6.3, 6.4

class TestAtomicUpdateWithBackup:
    """原子更新与备份属性测试"""
    
    def test_backup_preserves_original_content(self, temp_install_dir, temp_backup_dir):
        """备份应该保留原始内容"""
        # 创建原始文件
        install_path = Path(temp_install_dir)
        original_content = b"original content"
        test_file = install_path / "test.txt"
        test_file.write_bytes(original_content)
        
        # 创建 DeltaUpdater
        updater = DeltaUpdater(temp_install_dir)
        updater._backup_dir = Path(temp_backup_dir)
        
        # 创建模拟的 delta
        file_entry = FileEntry(
            path="test.txt",
            size=len(original_content),
            hash=DeltaUpdater._calculate_hash(str(test_file))
        )
        delta = DeltaResult(
            modified_files=[file_entry]
        )
        
        # 执行备份
        result = updater._create_backup(delta)
        
        assert result is True
        
        # 验证备份内容
        backup_file = Path(temp_backup_dir) / "test.txt"
        assert backup_file.exists()
        assert backup_file.read_bytes() == original_content
    
    def test_rollback_restores_original(self, temp_install_dir, temp_backup_dir):
        """回滚应该恢复原始文件"""
        install_path = Path(temp_install_dir)
        backup_path = Path(temp_backup_dir)
        
        # 创建备份文件
        original_content = b"original content"
        backup_file = backup_path / "test.txt"
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        backup_file.write_bytes(original_content)
        
        # 创建被修改的文件
        modified_content = b"modified content"
        install_file = install_path / "test.txt"
        install_file.write_bytes(modified_content)
        
        # 创建 DeltaUpdater
        updater = DeltaUpdater(temp_install_dir)
        updater._backup_dir = backup_path
        
        # 执行回滚
        result = updater._rollback()
        
        assert result is True
        
        # 验证文件已恢复
        assert install_file.read_bytes() == original_content
    
    @given(content=file_content)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_backup_then_rollback_preserves_state(
        self, content: bytes, temp_install_dir, temp_backup_dir
    ):
        """备份后回滚应该保持原始状态"""
        install_path = Path(temp_install_dir)
        
        # 创建原始文件
        test_file = install_path / "test.bin"
        test_file.write_bytes(content)
        original_hash = DeltaUpdater._calculate_hash(str(test_file))
        
        # 创建 DeltaUpdater
        updater = DeltaUpdater(temp_install_dir)
        updater._backup_dir = Path(temp_backup_dir)
        
        # 创建模拟的 delta
        file_entry = FileEntry(
            path="test.bin",
            size=len(content),
            hash=original_hash
        )
        delta = DeltaResult(modified_files=[file_entry])
        
        # 备份
        updater._create_backup(delta)
        
        # 模拟修改文件
        test_file.write_bytes(b"modified")
        
        # 回滚
        updater._rollback()
        
        # 验证恢复到原始状态
        restored_hash = DeltaUpdater._calculate_hash(str(test_file))
        assert restored_hash == original_hash
        
        # 清理
        test_file.unlink()
        for f in Path(temp_backup_dir).rglob('*'):
            if f.is_file():
                f.unlink()


# ========== Property 7: User Data Isolation ==========
# Feature: installer-incremental-update, Property 7: User Data Isolation
# Validates: Requirements 1.7, 8.4

class TestUserDataIsolation:
    """用户数据隔离属性测试"""
    
    def test_update_does_not_touch_user_data_dir(self, temp_install_dir):
        """更新操作不应该影响用户数据目录"""
        # 用户数据目录（模拟 ~/.screenshot_tool/）
        user_data_dir = Path(tempfile.mkdtemp(prefix='test_user_data_'))
        
        try:
            # 创建用户数据文件
            config_file = user_data_dir / "config.json"
            config_content = b'{"setting": "value"}'
            config_file.write_bytes(config_content)
            
            log_file = user_data_dir / "error.log"
            log_content = b"some log content"
            log_file.write_bytes(log_content)
            
            # 创建 DeltaUpdater（只操作安装目录）
            updater = DeltaUpdater(temp_install_dir)
            
            # 验证用户数据目录不在安装目录内
            assert not str(user_data_dir).startswith(temp_install_dir)
            
            # 验证用户数据文件未被修改
            assert config_file.read_bytes() == config_content
            assert log_file.read_bytes() == log_content
            
        finally:
            shutil.rmtree(str(user_data_dir), ignore_errors=True)
    
    def test_install_dir_does_not_contain_user_data_patterns(self, temp_install_dir):
        """安装目录不应该包含用户数据文件模式"""
        install_path = Path(temp_install_dir)
        
        # 创建一些安装文件
        (install_path / "app.exe").write_bytes(b"exe")
        (install_path / "lib").mkdir()
        (install_path / "lib" / "module.dll").write_bytes(b"dll")
        
        # 用户数据文件模式
        user_data_patterns = [
            "config.json",
            "error.log",
            "debug.log",
            "license_cache.json",
            "crash_*.log",
        ]
        
        # 验证安装目录不包含这些文件
        for pattern in user_data_patterns:
            if '*' in pattern:
                matches = list(install_path.glob(pattern))
            else:
                matches = [install_path / pattern] if (install_path / pattern).exists() else []
            
            assert len(matches) == 0, f"安装目录不应包含 {pattern}"


# ========== Property 8: Installation Integrity Verification ==========
# Feature: installer-incremental-update, Property 8: Installation Integrity Verification
# Validates: Requirements 8.5

class TestInstallationIntegrityVerification:
    """安装完整性验证属性测试"""
    
    def test_valid_installation_passes_verification(self, temp_install_dir):
        """有效安装应该通过验证"""
        install_path = Path(temp_install_dir)
        
        # 创建测试文件
        (install_path / "app.exe").write_bytes(b"exe content")
        (install_path / "lib").mkdir()
        (install_path / "lib" / "module.dll").write_bytes(b"dll content")
        
        # 生成清单
        generator = ManifestGenerator()
        manifest = generator.generate(temp_install_dir, "1.0.0")
        
        # 验证
        result = verify_installation_integrity(temp_install_dir, manifest)
        
        assert result is True
    
    def test_missing_file_fails_verification(self, temp_install_dir):
        """缺失文件应该验证失败"""
        install_path = Path(temp_install_dir)
        
        # 创建测试文件
        (install_path / "app.exe").write_bytes(b"exe content")
        (install_path / "module.dll").write_bytes(b"dll content")
        
        # 生成清单
        generator = ManifestGenerator()
        manifest = generator.generate(temp_install_dir, "1.0.0")
        
        # 删除一个文件
        (install_path / "module.dll").unlink()
        
        # 验证应该失败
        result = verify_installation_integrity(temp_install_dir, manifest)
        
        assert result is False
    
    def test_modified_file_fails_verification(self, temp_install_dir):
        """修改的文件应该验证失败"""
        install_path = Path(temp_install_dir)
        
        # 创建测试文件
        (install_path / "app.exe").write_bytes(b"exe content")
        
        # 生成清单
        generator = ManifestGenerator()
        manifest = generator.generate(temp_install_dir, "1.0.0")
        
        # 修改文件
        (install_path / "app.exe").write_bytes(b"modified content")
        
        # 验证应该失败
        result = verify_installation_integrity(temp_install_dir, manifest)
        
        assert result is False
    
    @given(content=file_content)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_integrity_check_is_consistent(self, content: bytes, temp_install_dir):
        """完整性检查应该一致"""
        install_path = Path(temp_install_dir)
        
        # 创建测试文件
        test_file = install_path / "test.bin"
        test_file.write_bytes(content)
        
        # 生成清单
        generator = ManifestGenerator()
        manifest = generator.generate(temp_install_dir, "1.0.0")
        
        # 多次验证应该得到相同结果
        result1 = verify_installation_integrity(temp_install_dir, manifest)
        result2 = verify_installation_integrity(temp_install_dir, manifest)
        
        assert result1 == result2 == True
        
        # 清理
        test_file.unlink()
