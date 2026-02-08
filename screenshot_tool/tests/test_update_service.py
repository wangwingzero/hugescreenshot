# =====================================================
# =============== 更新服务测试 ===============
# =====================================================

"""
更新服务属性测试

Property 1: Version Comparison Correctness
Property 2: Download Progress Accuracy
Property 3: File Size Verification
Property 4: Temporary File Cleanup
Property 5: Notification Session Control
Property 6: Check Interval Enforcement

Feature: auto-update
Validates: Requirements 1.3, 1.7, 2.2, 2.3, 3.7, 4.2, 4.3, 4.6
"""

import os
import re
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.services.update_service import (
    VersionInfo,
    VersionChecker,
    DownloadManager,
    UpdateExecutor,
    UpdateService,
    UpdateError,
    ProxySpeedResult,
    ProxySpeedCache,
    ProxySpeedTester,
    GITHUB_PROXIES,
)


# ========== 策略定义 ==========

# 有效的版本号策略
version_strategy = st.tuples(
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}")

# 带前缀的版本号策略
prefixed_version_strategy = st.one_of(
    version_strategy,
    version_strategy.map(lambda v: f"v{v}"),
)

# 文件大小策略
file_size_strategy = st.integers(min_value=0, max_value=1024 * 1024 * 100)  # 0-100MB

# 下载进度策略
download_progress_strategy = st.tuples(
    st.integers(min_value=0, max_value=1024 * 1024 * 100),  # downloaded
    st.integers(min_value=1, max_value=1024 * 1024 * 100),  # total
)

# Windows 路径策略
windows_path_strategy = st.from_regex(
    r'[A-Z]:\\[A-Za-z0-9_\u4e00-\u9fff ]+\\[A-Za-z0-9_\u4e00-\u9fff ]+\.exe',
    fullmatch=True
)


# ========== VersionInfo 测试 ==========

class TestVersionInfo:
    """VersionInfo 数据类测试"""
    
    def test_default_values(self):
        """测试默认值处理"""
        info = VersionInfo(
            version="1.0.0",
            download_url="https://example.com/app.exe",
            release_notes="Test",
            file_size=1000,
            published_at="2026-01-07"
        )
        assert info.version == "1.0.0"
        assert info.file_size == 1000
    
    def test_none_handling(self):
        """测试 None 值处理"""
        info = VersionInfo(
            version=None,
            download_url=None,
            release_notes=None,
            file_size=None,
            published_at=None
        )
        assert info.version == ""
        assert info.download_url == ""
        assert info.release_notes == ""
        assert info.file_size == 0
        assert info.published_at == ""


# ========== VersionChecker 测试 ==========

class TestVersionCheckerUnit:
    """VersionChecker 单元测试"""
    
    def test_parse_version_basic(self):
        """测试基本版本号解析"""
        assert VersionChecker.parse_version("1.9.0") == (1, 9, 0)
        assert VersionChecker.parse_version("0.0.1") == (0, 0, 1)
        assert VersionChecker.parse_version("10.20.30") == (10, 20, 30)
    
    def test_parse_version_with_prefix(self):
        """测试带 v 前缀的版本号"""
        assert VersionChecker.parse_version("v1.9.0") == (1, 9, 0)
        assert VersionChecker.parse_version("V1.9.0") == (1, 9, 0)
    
    def test_parse_version_with_suffix(self):
        """测试带后缀的版本号"""
        assert VersionChecker.parse_version("1.9.0-beta") == (1, 9, 0)
        assert VersionChecker.parse_version("1.9.0-rc1") == (1, 9, 0)
        assert VersionChecker.parse_version("v1.9.0-alpha.1") == (1, 9, 0)
    
    def test_parse_version_invalid(self):
        """测试无效版本号"""
        with pytest.raises(ValueError):
            VersionChecker.parse_version("")
        with pytest.raises(ValueError):
            VersionChecker.parse_version("invalid")
        with pytest.raises(ValueError):
            VersionChecker.parse_version("1.2")
    
    def test_compare_versions_less(self):
        """测试版本比较 - 小于"""
        assert VersionChecker.compare_versions("1.0.0", "1.0.1") == -1
        assert VersionChecker.compare_versions("1.0.0", "1.1.0") == -1
        assert VersionChecker.compare_versions("1.0.0", "2.0.0") == -1
        assert VersionChecker.compare_versions("1.9.0", "1.10.0") == -1
    
    def test_compare_versions_equal(self):
        """测试版本比较 - 相等"""
        assert VersionChecker.compare_versions("1.0.0", "1.0.0") == 0
        assert VersionChecker.compare_versions("v1.0.0", "1.0.0") == 0
    
    def test_compare_versions_greater(self):
        """测试版本比较 - 大于"""
        assert VersionChecker.compare_versions("1.0.1", "1.0.0") == 1
        assert VersionChecker.compare_versions("2.0.0", "1.9.9") == 1
    
    def test_is_newer_version(self):
        """测试是否有新版本"""
        assert VersionChecker.is_newer_version("1.9.0", "1.9.1") is True
        assert VersionChecker.is_newer_version("1.9.0", "1.9.0") is False
        assert VersionChecker.is_newer_version("1.9.1", "1.9.0") is False


class TestVersionCheckerProperties:
    """VersionChecker 属性测试
    
    Feature: auto-update
    """
    
    @given(
        v1=version_strategy,
        v2=version_strategy,
    )
    @settings(max_examples=100)
    def test_property_1_version_comparison_correctness(self, v1, v2):
        """
        Property 1: Version Comparison Correctness
        
        *For any* two valid semantic version strings, the comparison function
        SHALL correctly determine their ordering according to semantic versioning
        rules: major version takes precedence, then minor, then patch.
        
        **Validates: Requirements 1.3, 1.7**
        """
        # 解析版本号
        t1 = VersionChecker.parse_version(v1)
        t2 = VersionChecker.parse_version(v2)
        
        # 比较结果
        result = VersionChecker.compare_versions(v1, v2)
        
        # 验证正确性
        if t1 < t2:
            assert result == -1, f"{v1} should be less than {v2}"
        elif t1 > t2:
            assert result == 1, f"{v1} should be greater than {v2}"
        else:
            assert result == 0, f"{v1} should equal {v2}"
    
    @given(version=prefixed_version_strategy)
    @settings(max_examples=50)
    def test_property_version_parse_roundtrip(self, version):
        """
        Property: Version Parse Consistency
        
        *For any* valid version string (with or without 'v' prefix),
        parsing SHALL produce a valid (major, minor, patch) tuple.
        
        **Validates: Requirements 1.7**
        """
        result = VersionChecker.parse_version(version)
        
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(isinstance(x, int) and x >= 0 for x in result)
    
    @given(v1=version_strategy, v2=version_strategy, v3=version_strategy)
    @settings(max_examples=50)
    def test_property_comparison_transitivity(self, v1, v2, v3):
        """
        Property: Comparison Transitivity
        
        *For any* three versions, if v1 < v2 and v2 < v3, then v1 < v3.
        
        **Validates: Requirements 1.3**
        """
        cmp12 = VersionChecker.compare_versions(v1, v2)
        cmp23 = VersionChecker.compare_versions(v2, v3)
        cmp13 = VersionChecker.compare_versions(v1, v3)
        
        if cmp12 == -1 and cmp23 == -1:
            assert cmp13 == -1, f"Transitivity violated: {v1} < {v2} < {v3} but {v1} not < {v3}"


# ========== DownloadManager 测试 ==========

class TestDownloadManagerUnit:
    """DownloadManager 单元测试"""
    
    def test_calculate_progress_normal(self):
        """测试正常进度计算"""
        assert DownloadManager.calculate_progress(50, 100) == 50.0
        assert DownloadManager.calculate_progress(0, 100) == 0.0
        assert DownloadManager.calculate_progress(100, 100) == 100.0
    
    def test_calculate_progress_zero_total(self):
        """测试总大小为零"""
        assert DownloadManager.calculate_progress(50, 0) == 0.0
        assert DownloadManager.calculate_progress(0, 0) == 0.0
    
    def test_calculate_progress_overflow(self):
        """测试进度不超过 100%"""
        assert DownloadManager.calculate_progress(150, 100) == 100.0
    
    def test_verify_file_exists(self):
        """测试文件验证 - 文件存在"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            file_size = os.path.getsize(temp_path)
            assert DownloadManager.verify_file(temp_path, file_size) is True
            assert DownloadManager.verify_file(temp_path, file_size + 1) is False
        finally:
            os.unlink(temp_path)
    
    def test_verify_file_not_exists(self):
        """测试文件验证 - 文件不存在"""
        assert DownloadManager.verify_file("/nonexistent/file.exe", 1000) is False


class TestDownloadManagerProperties:
    """DownloadManager 属性测试
    
    Feature: auto-update
    """
    
    @given(downloaded=st.integers(min_value=0), total=st.integers(min_value=1))
    @settings(max_examples=100)
    def test_property_2_download_progress_accuracy(self, downloaded, total):
        """
        Property 2: Download Progress Accuracy
        
        *For any* download operation with known total size, the reported
        progress percentage SHALL equal (downloaded_bytes / total_bytes * 100),
        and SHALL never exceed 100%.
        
        **Validates: Requirements 2.2**
        """
        progress = DownloadManager.calculate_progress(downloaded, total)
        
        # 进度不超过 100%
        assert progress <= 100.0, f"Progress {progress}% exceeds 100%"
        
        # 进度不小于 0%
        assert progress >= 0.0, f"Progress {progress}% is negative"
        
        # 如果 downloaded <= total，进度应该准确
        if downloaded <= total:
            expected = (downloaded / total) * 100
            assert abs(progress - expected) < 0.001, \
                f"Progress {progress}% != expected {expected}%"
    
    @given(file_size=file_size_strategy)
    @settings(max_examples=50, deadline=None)  # 文件 I/O 时间不稳定，禁用 deadline
    def test_property_3_file_size_verification(self, file_size):
        """
        Property 3: File Size Verification
        
        *For any* downloaded file, the verification function SHALL return
        true if and only if the actual file size matches the expected size.
        
        **Validates: Requirements 2.3**
        """
        # 创建指定大小的临时文件
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'\x00' * file_size)
            temp_path = f.name
        
        try:
            # 正确大小应该验证通过
            assert DownloadManager.verify_file(temp_path, file_size) is True
            
            # 错误大小应该验证失败
            if file_size > 0:
                assert DownloadManager.verify_file(temp_path, file_size - 1) is False
            assert DownloadManager.verify_file(temp_path, file_size + 1) is False
        finally:
            os.unlink(temp_path)


# ========== UpdateExecutor 测试 ==========

class TestUpdateExecutorUnit:
    """UpdateExecutor 单元测试"""
    
    def test_get_current_exe_path(self):
        """测试获取当前 exe 路径"""
        path = UpdateExecutor.get_current_exe_path()
        assert isinstance(path, str)
        assert len(path) > 0
    
    def test_cleanup_update_files(self):
        """测试清理临时文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建临时文件
            Path(os.path.join(temp_dir, "app.downloading")).touch()
            Path(os.path.join(temp_dir, "keep.exe")).touch()  # 不应删除
            
            # 测试清理临时文件
            cleaned = UpdateExecutor.cleanup_update_files(temp_dir)
            
            assert cleaned == 1
            assert not os.path.exists(os.path.join(temp_dir, "app.downloading"))
            assert os.path.exists(os.path.join(temp_dir, "keep.exe"))
    
    def test_cleanup_update_files_no_temp_files(self):
        """测试清理临时文件 - 没有临时文件时"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 只创建普通文件
            Path(os.path.join(temp_dir, "keep.exe")).touch()
            
            cleaned = UpdateExecutor.cleanup_update_files(temp_dir)
            
            assert cleaned == 0
            assert os.path.exists(os.path.join(temp_dir, "keep.exe"))
    
    def test_cleanup_old_versions(self):
        """测试清理旧版本 exe 文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建多个版本的 exe
            Path(os.path.join(temp_dir, "HuGeScreenshot-1.0.0.exe")).touch()
            Path(os.path.join(temp_dir, "HuGeScreenshot-1.1.0.exe")).touch()
            Path(os.path.join(temp_dir, "other.exe")).touch()  # 不应删除
            
            # 在非打包环境下，cleanup_old_versions 会返回 0
            cleaned = UpdateExecutor.cleanup_old_versions(temp_dir)
            assert cleaned == 0  # 开发环境不执行清理


class TestUpdateExecutorProperties:
    """UpdateExecutor 属性测试
    
    Feature: auto-update
    """
    
    @given(
        num_downloading=st.integers(min_value=0, max_value=10),
        num_other_files=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50, deadline=None)
    def test_property_4_temporary_file_cleanup(self, num_downloading, num_other_files):
        """
        Property 4: Temporary File Cleanup
        
        *For any* directory containing .downloading files and other files,
        cleanup_update_files SHALL remove all and only .downloading files,
        leaving other files untouched.
        
        **Validates: Requirements 3.7, 4.1**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建 .downloading 临时文件
            downloading_files = []
            for i in range(num_downloading):
                f = os.path.join(temp_dir, f"file_{i}.downloading")
                Path(f).touch()
                downloading_files.append(f)
            
            # 创建其他文件（不应被删除）
            other_files = []
            for i in range(num_other_files):
                f = os.path.join(temp_dir, f"other_{i}.exe")
                Path(f).touch()
                other_files.append(f)
            
            # 执行清理
            cleaned = UpdateExecutor.cleanup_update_files(temp_dir)
            
            # 验证：清理数量等于 .downloading 文件数量
            assert cleaned == num_downloading, \
                f"Expected {num_downloading} cleaned, got {cleaned}"
            
            # 验证：所有 .downloading 文件都被删除
            for f in downloading_files:
                assert not os.path.exists(f), \
                    f".downloading file should be deleted: {f}"
            
            # 验证：其他文件保持不变
            for f in other_files:
                assert os.path.exists(f), \
                    f"Other file should not be deleted: {f}"


# ========== UpdateService 测试 ==========

class TestUpdateServiceUnit:
    """UpdateService 单元测试"""
    
    def test_current_version(self):
        """测试获取当前版本"""
        service = UpdateService()
        version = service.current_version
        
        assert isinstance(version, str)
        assert len(version) > 0
        # 应该是有效的版本号格式
        VersionChecker.parse_version(version)
    
    def test_get_github_repo_default(self):
        """测试获取默认 GitHub 仓库"""
        service = UpdateService()
        repo = service.get_github_repo()
        
        assert repo == "wangwingzero/hugescreenshot-releases"
    
    def test_get_github_repo_from_config(self):
        """测试从配置获取 GitHub 仓库"""
        mock_config = MagicMock()
        mock_config.get_github_repo.return_value = "test/repo"
        
        service = UpdateService(config_manager=mock_config)
        repo = service.get_github_repo()
        
        assert repo == "test/repo"
    
    def test_should_notify_first_time(self):
        """测试首次通知"""
        mock_config = MagicMock()
        mock_config.get_notification_software_update.return_value = True
        mock_config.get_update_last_notified_version.return_value = ""
        
        service = UpdateService(config_manager=mock_config)
        
        assert service.should_notify("1.9.1") is True
    
    def test_should_notify_disabled(self):
        """测试通知禁用"""
        mock_config = MagicMock()
        mock_config.get_notification_software_update.return_value = False
        
        service = UpdateService(config_manager=mock_config)
        
        assert service.should_notify("1.9.1") is False
    
    def test_should_notify_already_notified_this_session(self):
        """测试本次会话已通知"""
        mock_config = MagicMock()
        mock_config.get_notification_software_update.return_value = True
        
        service = UpdateService(config_manager=mock_config)
        service._notified_this_session = True
        
        assert service.should_notify("1.9.1") is False
    
    def test_mark_notified(self):
        """测试标记已通知"""
        mock_config = MagicMock()
        
        service = UpdateService(config_manager=mock_config)
        service.mark_notified("1.9.1")
        
        assert service._notified_this_session is True
        mock_config.set_update_last_notified_version.assert_called_once_with("1.9.1")
        mock_config.save.assert_called_once()


class TestUpdateServiceProperties:
    """UpdateService 属性测试
    
    Feature: auto-update
    """
    
    @given(
        hours_since_last_check=st.integers(min_value=0, max_value=100),
        check_interval_hours=st.integers(min_value=1, max_value=168),
    )
    @settings(max_examples=50)
    def test_property_6_check_interval_enforcement(
        self,
        hours_since_last_check,
        check_interval_hours,
    ):
        """
        Property 6: Check Interval Enforcement
        
        *For any* configuration with a last_check_time,
        the automatic check SHALL be skipped if within check_interval_hours.
        Note: auto_check is always enabled, only interval matters.
        
        **Validates: Requirements 4.2, 4.3**
        """
        from datetime import datetime, timedelta
        from screenshot_tool.core.config_manager import UpdateConfig
        
        # 计算上次检查时间
        last_check = datetime.now() - timedelta(hours=hours_since_last_check)
        
        config = UpdateConfig(
            check_interval_hours=check_interval_hours,
            last_check_time=last_check.isoformat(),
        )
        
        should_check = config.should_check()
        
        if hours_since_last_check >= check_interval_hours:
            # 超过间隔应该检查
            assert should_check is True
        else:
            # 间隔内不应检查
            assert should_check is False
    
    @given(version=version_strategy)
    @settings(max_examples=50)
    def test_property_5_notification_session_control(self, version):
        """
        Property 5: Notification Session Control
        
        *For any* version, after mark_notified is called, should_notify SHALL
        return False for the remainder of the session.
        
        **Validates: Requirements 5.1, 5.5**
        """
        mock_config = MagicMock()
        mock_config.get_notification_software_update.return_value = True
        mock_config.get_update_last_notified_version.return_value = ""
        
        service = UpdateService(config_manager=mock_config)
        
        # 首次应该允许通知
        assert service.should_notify(version) is True
        
        # 标记已通知
        service.mark_notified(version)
        
        # 之后应该不再通知
        assert service.should_notify(version) is False
        
        # 即使是不同版本也不应通知（本次会话已通知）
        other_version = f"99.{version}"
        assert service.should_notify(other_version) is False
    
    @given(version=version_strategy)
    @settings(max_examples=50)
    def test_property_notification_settings_respect(self, version):
        """
        Property: Notification Settings Respect
        
        *For any* version, when notification is disabled in settings,
        should_notify SHALL return False regardless of other conditions.
        
        **Validates: Requirements 5.4**
        """
        mock_config = MagicMock()
        mock_config.get_notification_software_update.return_value = False
        mock_config.get_update_last_notified_version.return_value = ""
        
        service = UpdateService(config_manager=mock_config)
        
        # 通知禁用时应该返回 False
        assert service.should_notify(version) is False
        
        # 即使没有通知过也应该返回 False
        assert service._notified_this_session is False
        assert service.should_notify(version) is False



# ========== Old Exe Cleanup Fix 测试 ==========

class TestOldExeCleanupFix:
    """旧版本 exe 清理修复测试
    
    Feature: old-exe-cleanup-fix
    Validates: Requirements 1.1, 2.1, 2.2
    """
    
    def test_cleanup_old_versions_called_on_startup(self):
        """测试每次启动时 cleanup_old_versions 都被调用
        
        Property 1: Startup always triggers cleanup
        每次启动都会清理旧版本 exe 文件，无论版本是否变更
        
        Feature: old-exe-cleanup-fix
        Validates: Requirements 1.1, 2.1
        """
        mock_config = MagicMock()
        mock_config.get_last_run_version.return_value = "1.13.0"  # 旧版本
        
        service = UpdateService(config_manager=mock_config)
        
        # Mock cleanup_old_versions 来验证它被调用
        with patch.object(
            service._update_executor, 
            'cleanup_old_versions', 
            return_value=1
        ) as mock_cleanup:
            with patch.object(
                service._update_executor,
                'cleanup_update_files',
                return_value=0
            ):
                service.cleanup_on_startup()
                
                # 验证 cleanup_old_versions 被调用
                mock_cleanup.assert_called_once()
    
    def test_cleanup_old_versions_called_even_when_version_same(self):
        """测试版本相同时 cleanup_old_versions 也被调用
        
        每次启动都清理旧版本，确保旧的单文件版本残留被清理
        
        Feature: old-exe-cleanup-fix
        Validates: Requirements 2.2
        """
        from screenshot_tool import __version__
        
        mock_config = MagicMock()
        mock_config.get_last_run_version.return_value = __version__  # 相同版本
        
        service = UpdateService(config_manager=mock_config)
        
        with patch.object(
            service._update_executor, 
            'cleanup_old_versions', 
            return_value=0
        ) as mock_cleanup:
            with patch.object(
                service._update_executor,
                'cleanup_update_files',
                return_value=0
            ):
                service.cleanup_on_startup()
                
                # 验证 cleanup_old_versions 被调用（每次启动都清理）
                mock_cleanup.assert_called_once()
    
    def test_cleanup_old_versions_called_on_first_run(self):
        """测试首次运行时也会清理旧版本
        
        Feature: old-exe-cleanup-fix
        Validates: Requirements 2.2
        """
        mock_config = MagicMock()
        mock_config.get_last_run_version.return_value = ""  # 空版本（首次运行）
        
        service = UpdateService(config_manager=mock_config)
        
        with patch.object(
            service._update_executor, 
            'cleanup_old_versions', 
            return_value=0
        ) as mock_cleanup:
            with patch.object(
                service._update_executor,
                'cleanup_update_files',
                return_value=0
            ):
                service.cleanup_on_startup()
                
                # 验证 cleanup_old_versions 被调用（首次运行也清理）
                mock_cleanup.assert_called_once()


class TestOldExeCleanupFixProperties:
    """旧版本 exe 清理修复属性测试
    
    Feature: old-exe-cleanup-fix
    """
    
    @given(
        old_version=version_strategy,
        new_version=version_strategy,
    )
    @settings(max_examples=50)
    def test_property_startup_always_triggers_cleanup(self, old_version, new_version):
        """
        Property 1: Startup always triggers cleanup
        
        *For any* pair of version strings, calling cleanup_on_startup 
        SHALL always invoke cleanup_old_versions to clean up legacy 
        single-file exe versions.
        
        Feature: old-exe-cleanup-fix
        Validates: Requirements 1.1, 2.1, 2.2
        """
        mock_config = MagicMock()
        mock_config.get_last_run_version.return_value = old_version
        
        service = UpdateService(config_manager=mock_config)
        
        # Mock current_version 为新版本
        with patch.object(
            type(service), 
            'current_version', 
            new_callable=lambda: property(lambda self: new_version)
        ):
            with patch.object(
                service._update_executor, 
                'cleanup_old_versions', 
                return_value=1
            ) as mock_cleanup:
                with patch.object(
                    service._update_executor,
                    'cleanup_update_files',
                    return_value=0
                ):
                    service.cleanup_on_startup()

                    # 每次启动都应该调用 cleanup_old_versions
                    mock_cleanup.assert_called_once()


# ========== 代理测速测试 ==========

class TestProxySpeedResult:
    """ProxySpeedResult 数据类测试

    Feature: background-proxy-speed-test
    """

    def test_is_expired_fresh(self):
        """新鲜结果不过期"""
        import time
        result = ProxySpeedResult(
            proxy_url="https://test.com/",
            response_time=1.0,
            tested_at=time.time(),
            is_available=True
        )
        assert not result.is_expired()

    def test_is_expired_old(self):
        """旧结果过期"""
        import time
        result = ProxySpeedResult(
            proxy_url="https://test.com/",
            response_time=1.0,
            tested_at=time.time() - 600,  # 10 分钟前
            is_available=True
        )
        assert result.is_expired(expire_seconds=300)

    def test_is_expired_custom_timeout(self):
        """自定义过期时间"""
        import time
        result = ProxySpeedResult(
            proxy_url="https://test.com/",
            response_time=1.0,
            tested_at=time.time() - 60,  # 1 分钟前
            is_available=True
        )
        # 2 分钟过期：未过期
        assert not result.is_expired(expire_seconds=120)
        # 30 秒过期：已过期
        assert result.is_expired(expire_seconds=30)


class TestProxySpeedCache:
    """ProxySpeedCache 数据类测试

    Feature: background-proxy-speed-test
    """

    def test_get_sorted_proxies_empty(self):
        """空缓存返回空列表"""
        cache = ProxySpeedCache()
        assert cache.get_sorted_proxies() == []

    def test_get_sorted_proxies_order(self):
        """按响应时间排序"""
        import time
        cache = ProxySpeedCache()
        now = time.time()
        cache.results = {
            "slow": ProxySpeedResult("slow", 5.0, now, True),
            "fast": ProxySpeedResult("fast", 1.0, now, True),
            "medium": ProxySpeedResult("medium", 2.5, now, True),
        }
        assert cache.get_sorted_proxies() == ["fast", "medium", "slow"]

    def test_get_sorted_proxies_excludes_unavailable(self):
        """排除不可用的代理"""
        import time
        cache = ProxySpeedCache()
        now = time.time()
        cache.results = {
            "ok": ProxySpeedResult("ok", 1.0, now, True),
            "bad": ProxySpeedResult("bad", float('inf'), now, False),
        }
        assert cache.get_sorted_proxies() == ["ok"]

    def test_get_sorted_proxies_excludes_expired(self):
        """排除过期的代理"""
        import time
        cache = ProxySpeedCache()
        now = time.time()
        cache.results = {
            "fresh": ProxySpeedResult("fresh", 1.0, now, True),
            "expired": ProxySpeedResult("expired", 0.5, now - 600, True),  # 10 分钟前
        }
        # 过期的代理不在排序列表中
        assert cache.get_sorted_proxies() == ["fresh"]

    def test_get_fastest_proxy(self):
        """获取最快代理"""
        import time
        cache = ProxySpeedCache()
        now = time.time()
        cache.results = {
            "slow": ProxySpeedResult("slow", 5.0, now, True),
            "fast": ProxySpeedResult("fast", 1.0, now, True),
        }
        assert cache.get_fastest_proxy() == "fast"

    def test_get_fastest_proxy_empty(self):
        """空缓存返回 None"""
        cache = ProxySpeedCache()
        assert cache.get_fastest_proxy() is None

    def test_is_valid_version_mismatch(self):
        """版本不匹配时缓存无效"""
        import time
        cache = ProxySpeedCache()
        cache.test_version = "1.0.0"
        cache.results = {
            "ok": ProxySpeedResult("ok", 1.0, time.time(), True),
        }
        assert not cache.is_valid("1.0.1")

    def test_is_valid_all_expired(self):
        """全部过期时缓存无效"""
        import time
        cache = ProxySpeedCache()
        cache.test_version = "1.0.0"
        cache.results = {
            "old": ProxySpeedResult("old", 1.0, time.time() - 600, True),
        }
        assert not cache.is_valid("1.0.0")

    def test_is_valid_success(self):
        """有效缓存"""
        import time
        cache = ProxySpeedCache()
        cache.test_version = "1.0.0"
        cache.results = {
            "fresh": ProxySpeedResult("fresh", 1.0, time.time(), True),
        }
        assert cache.is_valid("1.0.0")

    def test_clear(self):
        """清空缓存"""
        import time
        cache = ProxySpeedCache()
        cache.test_version = "1.0.0"
        cache.is_testing = True
        cache.results = {
            "test": ProxySpeedResult("test", 1.0, time.time(), True),
        }
        cache.clear()
        assert cache.results == {}
        assert cache.is_testing == False
        assert cache.test_version == ""


class TestProxySpeedTester:
    """ProxySpeedTester 类测试

    Feature: background-proxy-speed-test
    """

    def test_cache_property(self):
        """测试 cache 属性"""
        tester = ProxySpeedTester()
        assert isinstance(tester.cache, ProxySpeedCache)

    def test_is_testing_initial(self):
        """初始状态不在测速"""
        tester = ProxySpeedTester()
        assert not tester.is_testing

    def test_skip_if_already_testing(self):
        """已在测速中时跳过"""
        tester = ProxySpeedTester()
        tester._cache.is_testing = True

        # 尝试启动测速，应该被跳过
        tester.start_speed_test("https://github.com/test.exe", "1.0.0")

        # 版本号不应该被更新（因为被跳过了）
        assert tester._cache.test_version == ""

    def test_skip_if_cache_valid(self):
        """缓存有效时跳过测速"""
        import time
        tester = ProxySpeedTester()
        tester._cache.test_version = "1.0.0"
        tester._cache.results = {
            "test": ProxySpeedResult("test", 1.0, time.time(), True),
        }

        # 应该跳过测速
        tester.start_speed_test("https://github.com/test.exe", "1.0.0")

        # 不应该进入测速状态
        assert not tester.is_testing

    def test_get_best_download_url_with_cache(self):
        """使用缓存获取最佳下载 URL"""
        import time
        tester = ProxySpeedTester()
        tester._cache.results = {
            "https://fast.proxy/": ProxySpeedResult("https://fast.proxy/", 1.0, time.time(), True),
            "https://slow.proxy/": ProxySpeedResult("https://slow.proxy/", 5.0, time.time(), True),
        }

        url = tester.get_best_download_url("https://github.com/test.exe")
        assert url == "https://fast.proxy/https://github.com/test.exe"

    def test_get_best_download_url_fallback(self):
        """无缓存时使用默认代理"""
        tester = ProxySpeedTester()
        url = tester.get_best_download_url("https://github.com/test.exe")
        assert url.startswith(GITHUB_PROXIES[0])
        assert "https://github.com/test.exe" in url


class TestDownloadManagerWithSpeedCache:
    """DownloadManager 测速缓存集成测试

    Feature: background-proxy-speed-test
    """

    def test_set_proxy_speed_cache(self):
        """设置测速缓存"""
        manager = DownloadManager()
        cache = ProxySpeedCache()
        manager.set_proxy_speed_cache(cache)
        assert manager._proxy_speed_cache is cache

    def test_get_next_proxy_uses_cache(self):
        """切换代理时使用缓存排序"""
        import time
        manager = DownloadManager()

        # 设置缓存，slow 代理比 fast 代理慢
        cache = ProxySpeedCache()
        cache.results = {
            GITHUB_PROXIES[0]: ProxySpeedResult(GITHUB_PROXIES[0], 5.0, time.time(), True),
            GITHUB_PROXIES[1]: ProxySpeedResult(GITHUB_PROXIES[1], 1.0, time.time(), True),
        }
        manager.set_proxy_speed_cache(cache)

        # 当前 URL 使用第一个代理
        current_url = f"{GITHUB_PROXIES[0]}https://github.com/test.exe"

        # 切换代理应该选择测速更快的代理
        next_url = manager._get_next_proxy(current_url)

        # 应该选择测速更快的代理
        assert next_url is not None
        assert GITHUB_PROXIES[1] in next_url

    def test_get_next_proxy_fallback_without_cache(self):
        """无缓存时回退到默认顺序"""
        manager = DownloadManager()

        # 不设置缓存
        current_url = f"{GITHUB_PROXIES[0]}https://github.com/test.exe"

        next_url = manager._get_next_proxy(current_url)

        # 应该使用默认顺序的下一个代理
        assert next_url is not None
        assert GITHUB_PROXIES[1] in next_url


class TestUpdateServiceWithSpeedTest:
    """UpdateService 测速集成测试

    Feature: background-proxy-speed-test
    """

    def test_proxy_speed_cache_property(self):
        """测试 proxy_speed_cache 属性"""
        service = UpdateService()
        assert isinstance(service.proxy_speed_cache, ProxySpeedCache)

    def test_proxy_speed_tester_initialized(self):
        """测速器已初始化"""
        service = UpdateService()
        assert hasattr(service, '_proxy_speed_tester')
        assert isinstance(service._proxy_speed_tester, ProxySpeedTester)
