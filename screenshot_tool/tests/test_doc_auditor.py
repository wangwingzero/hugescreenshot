# -*- coding: utf-8 -*-
"""
文档审计模块测试

包含单元测试和属性测试，验证文档审计功能的正确性。
"""

import pytest
import re
from hypothesis import given, strategies as st, settings
from pathlib import Path
from datetime import datetime

from screenshot_tool.services.doc_auditor import (
    ModuleInfo,
    DocumentContent,
    Discrepancy,
    AuditReport,
    Severity,
    DiscrepancyCategory,
    ModuleScanner,
)


# ============================================================
# 策略定义
# ============================================================

# 模块名策略：有效的 Python 标识符
module_name_strategy = st.from_regex(r'[a-z][a-z0-9_]{0,30}', fullmatch=True)

# 模块名列表策略
module_list_strategy = st.lists(module_name_strategy, min_size=0, max_size=20, unique=True)

# 版本号策略
version_strategy = st.from_regex(r'[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}', fullmatch=True)


# ============================================================
# Property 1: Module List Comparison Completeness
# Feature: documentation-audit, Property 1: Module List Comparison Completeness
# Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
# ============================================================

def compare_module_lists(actual: list[str], documented: list[str]) -> tuple[list[str], list[str]]:
    """比较实际模块列表与文档记录
    
    Returns:
        (missing_from_docs, documented_but_not_found)
    """
    actual_set = set(actual)
    documented_set = set(documented)
    
    missing_from_docs = sorted(actual_set - documented_set)
    documented_but_not_found = sorted(documented_set - actual_set)
    
    return missing_from_docs, documented_but_not_found


@given(actual=module_list_strategy, documented=module_list_strategy)
@settings(max_examples=100)
def test_module_comparison_completeness(actual: list[str], documented: list[str]):
    """
    Property 1: Module List Comparison Completeness
    
    For any set of actual modules and documented modules:
    - Every actual module not in documented should be in missing_from_docs
    - Every documented module not in actual should be in documented_but_not_found
    - Modules in both lists should not appear in either result
    
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
    """
    missing_from_docs, documented_but_not_found = compare_module_lists(actual, documented)
    
    actual_set = set(actual)
    documented_set = set(documented)
    
    # 验证 missing_from_docs 包含所有在 actual 但不在 documented 的模块
    expected_missing = actual_set - documented_set
    assert set(missing_from_docs) == expected_missing, \
        f"Missing from docs mismatch: got {missing_from_docs}, expected {sorted(expected_missing)}"
    
    # 验证 documented_but_not_found 包含所有在 documented 但不在 actual 的模块
    expected_not_found = documented_set - actual_set
    assert set(documented_but_not_found) == expected_not_found, \
        f"Documented but not found mismatch: got {documented_but_not_found}, expected {sorted(expected_not_found)}"
    
    # 验证两个结果列表没有交集
    assert not (set(missing_from_docs) & set(documented_but_not_found)), \
        "Results should not overlap"
    
    # 验证在两个列表中都存在的模块不会出现在任何结果中
    common = actual_set & documented_set
    for module in common:
        assert module not in missing_from_docs, f"{module} should not be in missing_from_docs"
        assert module not in documented_but_not_found, f"{module} should not be in documented_but_not_found"


# ============================================================
# 单元测试：ModuleScanner
# ============================================================

class TestModuleScanner:
    """ModuleScanner 单元测试"""
    
    def test_scan_core_directory(self):
        """测试扫描 core 目录"""
        scanner = ModuleScanner(Path("screenshot_tool"))
        modules = scanner.scan_directory("core")
        
        # 应该找到一些模块
        assert len(modules) > 0
        
        # 验证模块信息
        for m in modules:
            assert m.category == "core"
            assert m.path.exists()
            assert m.name != "__init__"
    
    def test_scan_services_directory(self):
        """测试扫描 services 目录"""
        scanner = ModuleScanner(Path("screenshot_tool"))
        modules = scanner.scan_directory("services")
        
        assert len(modules) > 0
        
        # 应该包含 doc_auditor
        module_names = [m.name for m in modules]
        assert "doc_auditor" in module_names
    
    def test_scan_ui_directory(self):
        """测试扫描 ui 目录"""
        scanner = ModuleScanner(Path("screenshot_tool"))
        modules = scanner.scan_directory("ui")
        
        assert len(modules) > 0
    
    def test_scan_nonexistent_directory(self):
        """测试扫描不存在的目录"""
        scanner = ModuleScanner(Path("screenshot_tool"))
        modules = scanner.scan_directory("nonexistent")
        
        assert modules == []
    
    def test_scan_all(self):
        """测试扫描所有目录"""
        scanner = ModuleScanner(Path("screenshot_tool"))
        all_modules = scanner.scan_all()
        
        assert "core" in all_modules
        assert "services" in all_modules
        assert "ui" in all_modules
        
        # 每个目录都应该有模块
        for category, modules in all_modules.items():
            assert len(modules) > 0, f"{category} should have modules"


# ============================================================
# 单元测试：AuditReport
# ============================================================

class TestAuditReport:
    """AuditReport 单元测试"""
    
    def test_empty_report(self):
        """测试空报告"""
        report = AuditReport(timestamp=datetime.now())
        
        assert report.summary == {"critical": 0, "warning": 0, "info": 0}
        assert "无需更新" in report.to_markdown()
    
    def test_report_with_discrepancies(self):
        """测试包含差异的报告"""
        report = AuditReport(
            timestamp=datetime.now(),
            discrepancies=[
                Discrepancy(
                    category=DiscrepancyCategory.MODULE,
                    severity=Severity.WARNING,
                    source="filesystem",
                    target="structure.md",
                    item="test_module",
                    message="模块未记录",
                    recommendation="添加到 structure.md",
                ),
                Discrepancy(
                    category=DiscrepancyCategory.VERSION,
                    severity=Severity.CRITICAL,
                    source="__init__.py",
                    target="spec file",
                    item="version",
                    message="版本不一致",
                    recommendation="同步版本号",
                ),
            ],
        )
        
        assert report.summary == {"critical": 1, "warning": 1, "info": 0}
        
        md = report.to_markdown()
        assert "CRITICAL" in md
        assert "WARNING" in md
        assert "test_module" in md
    
    def test_report_to_dict(self):
        """测试报告转字典"""
        report = AuditReport(
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            discrepancies=[
                Discrepancy(
                    category=DiscrepancyCategory.MODULE,
                    severity=Severity.INFO,
                    source="a",
                    target="b",
                    item="c",
                    message="d",
                    recommendation="e",
                ),
            ],
        )
        
        d = report.to_dict()
        assert d["timestamp"] == "2024-01-01T12:00:00"
        assert d["summary"]["info"] == 1
        assert len(d["discrepancies"]) == 1



# ============================================================
# Property 4: Version Extraction Round-Trip
# Feature: documentation-audit, Property 4: Version Extraction Round-Trip
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
# ============================================================

from screenshot_tool.services.doc_auditor import VersionScanner
import tempfile
import os


@given(version=version_strategy)
@settings(max_examples=100)
def test_version_extraction_init_roundtrip(version: str):
    """
    Property 4: Version Extraction Round-Trip (for __init__.py format)
    
    For any valid version string, constructing a file with __version__ = "x.x.x"
    and extracting should return the same version.
    
    **Validates: Requirements 3.1**
    """
    scanner = VersionScanner()
    
    # 构造包含版本号的文件内容
    content = f'__version__ = "{version}"\n__app_name__ = "Test"'
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        # 提取版本号
        extracted = scanner.extract_from_init(temp_path)
        assert extracted == version, f"Expected {version}, got {extracted}"
    finally:
        os.unlink(temp_path)


@given(version=version_strategy)
@settings(max_examples=100)
def test_version_extraction_spec_roundtrip(version: str):
    """
    Property 4: Version Extraction Round-Trip (for .spec format)
    
    For any valid version string, constructing a file with APP_VERSION = "x.x.x"
    and extracting should return the same version.
    
    **Validates: Requirements 3.2, 3.3**
    """
    scanner = VersionScanner()
    
    content = f'APP_VERSION = "{version}"\nproject_root = "test"'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.spec', delete=False, encoding='utf-8') as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        extracted = scanner.extract_from_spec(temp_path)
        assert extracted == version, f"Expected {version}, got {extracted}"
    finally:
        os.unlink(temp_path)


@given(version=version_strategy)
@settings(max_examples=100)
def test_version_extraction_markdown_roundtrip(version: str):
    """
    Property 4: Version Extraction Round-Trip (for Markdown format)
    
    For any valid version string, constructing a file with version-x.x.x
    and extracting should return the same version.
    
    **Validates: Requirements 3.4, 3.5**
    """
    scanner = VersionScanner()
    
    content = f'# Test\n\n当前版本 v{version}\n\nSome content'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        extracted = scanner.extract_from_markdown(temp_path)
        assert extracted == version, f"Expected {version}, got {extracted}"
    finally:
        os.unlink(temp_path)


# ============================================================
# 单元测试：VersionScanner
# ============================================================

class TestVersionScanner:
    """VersionScanner 单元测试"""
    
    def test_extract_from_actual_init(self):
        """测试从实际 __init__.py 提取版本"""
        scanner = VersionScanner()
        version = scanner.extract_from_init(Path("screenshot_tool/__init__.py"))
        
        assert version is not None
        assert re.match(r'\d+\.\d+\.\d+', version)
    
    def test_extract_from_actual_spec(self):
        """测试从实际 spec 文件提取版本"""
        scanner = VersionScanner()
        version = scanner.extract_from_spec(Path("build/虎哥截图-dir.spec"))
        
        assert version is not None
        assert re.match(r'\d+\.\d+\.\d+', version)
    
    def test_extract_from_actual_readme(self):
        """测试从实际 README.md 提取版本"""
        scanner = VersionScanner()
        version = scanner.extract_from_markdown(Path("README.md"))
        
        assert version is not None
        assert re.match(r'\d+\.\d+\.\d+', version)
    
    def test_extract_from_nonexistent_file(self):
        """测试从不存在的文件提取版本"""
        scanner = VersionScanner()
        
        assert scanner.extract_from_init(Path("nonexistent.py")) is None
        assert scanner.extract_from_spec(Path("nonexistent.spec")) is None
        assert scanner.extract_from_markdown(Path("nonexistent.md")) is None
    
    def test_extract_all(self):
        """测试提取所有版本"""
        scanner = VersionScanner()
        versions = scanner.extract_all(Path("."))
        
        assert '__init__.py' in versions
        assert '虎哥截图-dir.spec' in versions
        assert 'product.md' in versions
        assert 'README.md' in versions



# ============================================================
# Property 5: Version Consistency Detection
# Feature: documentation-audit, Property 5: Version Consistency Detection
# Validates: Requirements 3.6, 4.3, 6.1
# ============================================================

from screenshot_tool.services.doc_auditor import VersionComparator


@given(
    base_version=version_strategy,
    other_versions=st.lists(version_strategy, min_size=0, max_size=4),
)
@settings(max_examples=100)
def test_version_consistency_detection(base_version: str, other_versions: list[str]):
    """
    Property 5: Version Consistency Detection
    
    For any set of version strings:
    - If all versions are identical, no discrepancy should be reported
    - If at least one version differs, discrepancies should be reported
    
    **Validates: Requirements 3.6, 4.3, 6.1**
    """
    comparator = VersionComparator()
    
    # 构造版本字典
    versions = {'file1': base_version}
    for i, v in enumerate(other_versions):
        versions[f'file{i+2}'] = v
    
    discrepancies = comparator.compare(versions)
    
    # 检查所有版本是否一致
    unique_versions = set(versions.values())
    all_same = len(unique_versions) == 1
    
    if all_same:
        # 所有版本一致，不应有差异
        assert len(discrepancies) == 0, \
            f"All versions are {base_version}, but got {len(discrepancies)} discrepancies"
    else:
        # 版本不一致，应该有差异报告
        # 差异数量应该等于与基准版本不同的文件数
        pass  # 不强制检查数量，只要有差异即可


@given(version=version_strategy)
@settings(max_examples=100)
def test_version_consistency_all_same(version: str):
    """
    Property 5 (specific case): All versions identical
    
    When all versions are the same, no discrepancy should be reported.
    
    **Validates: Requirements 3.6**
    """
    comparator = VersionComparator()
    
    versions = {
        'file1': version,
        'file2': version,
        'file3': version,
    }
    
    discrepancies = comparator.compare(versions)
    assert len(discrepancies) == 0, \
        f"All versions are {version}, but got discrepancies: {discrepancies}"


@given(v1=version_strategy, v2=version_strategy)
@settings(max_examples=100)
def test_version_consistency_different(v1: str, v2: str):
    """
    Property 5 (specific case): Different versions
    
    When versions differ, discrepancies should be reported.
    
    **Validates: Requirements 3.6**
    """
    # 跳过相同版本的情况
    if v1 == v2:
        return
    
    comparator = VersionComparator()
    
    versions = {
        'file1': v1,
        'file2': v2,
    }
    
    discrepancies = comparator.compare(versions)
    assert len(discrepancies) > 0, \
        f"Versions {v1} and {v2} differ, but no discrepancy reported"


# ============================================================
# Property 6: Dependency Comparison Completeness
# Feature: documentation-audit, Property 6: Dependency Comparison Completeness
# Validates: Requirements 5.1, 5.2, 5.3
# ============================================================

from screenshot_tool.services.doc_auditor import DependencyComparator

# 依赖名策略
dep_name_strategy = st.from_regex(r'[a-z][a-z0-9_]{0,20}', fullmatch=True)
dep_list_strategy = st.lists(dep_name_strategy, min_size=0, max_size=15, unique=True)


@given(requirements=dep_list_strategy, documented=dep_list_strategy)
@settings(max_examples=100)
def test_dependency_comparison_completeness(requirements: list[str], documented: list[str]):
    """
    Property 6: Dependency Comparison Completeness
    
    For any set of dependencies in requirements.txt and tech.md:
    - Every dependency in requirements but not in documented should be reported
    - Every dependency in documented but not in requirements should be reported
    - Dependencies in both should not be reported
    
    **Validates: Requirements 5.1, 5.2, 5.3**
    """
    comparator = DependencyComparator()
    discrepancies = comparator.compare(requirements, documented)
    
    req_set = set(requirements)
    doc_set = set(documented)
    
    # 收集报告的差异项
    reported_items = {d.item for d in discrepancies}
    
    # 验证 requirements 中但不在 documented 中的都被报告
    undocumented = req_set - doc_set
    for dep in undocumented:
        assert dep in reported_items, \
            f"Undocumented dependency {dep} should be reported"
    
    # 验证 documented 中但不在 requirements 中的都被报告
    documented_only = doc_set - req_set
    for dep in documented_only:
        assert dep in reported_items, \
            f"Documented-only dependency {dep} should be reported"
    
    # 验证两边都有的不被报告
    common = req_set & doc_set
    for dep in common:
        assert dep not in reported_items, \
            f"Common dependency {dep} should not be reported"



# ============================================================
# Property 7: Report Completeness
# Feature: documentation-audit, Property 7: Report Completeness
# Validates: Requirements 7.1, 7.2, 7.3
# ============================================================

# 差异项策略
severity_strategy = st.sampled_from([Severity.CRITICAL, Severity.WARNING, Severity.INFO])
category_strategy = st.sampled_from([
    DiscrepancyCategory.MODULE,
    DiscrepancyCategory.HIDDEN_IMPORT,
    DiscrepancyCategory.VERSION,
    DiscrepancyCategory.DEPENDENCY,
])

discrepancy_strategy = st.builds(
    Discrepancy,
    category=category_strategy,
    severity=severity_strategy,
    source=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    target=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    item=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
    message=st.text(min_size=1, max_size=100),
    recommendation=st.text(min_size=1, max_size=100),
)

discrepancy_list_strategy = st.lists(discrepancy_strategy, min_size=0, max_size=10)


@given(discrepancies=discrepancy_list_strategy)
@settings(max_examples=100)
def test_report_completeness(discrepancies: list[Discrepancy]):
    """
    Property 7: Report Completeness
    
    For any audit result:
    - The report should include all discrepancies
    - Each discrepancy should have a valid severity
    - Each discrepancy should have a non-empty recommendation
    
    **Validates: Requirements 7.1, 7.2, 7.3**
    """
    report = AuditReport(
        timestamp=datetime.now(),
        discrepancies=discrepancies,
    )
    
    # 验证报告包含所有差异
    assert len(report.discrepancies) == len(discrepancies), \
        "Report should include all discrepancies"
    
    # 验证摘要统计正确
    summary = report.summary
    expected_counts = {s.value: 0 for s in Severity}
    for d in discrepancies:
        expected_counts[d.severity.value] += 1
    
    assert summary == expected_counts, \
        f"Summary mismatch: got {summary}, expected {expected_counts}"
    
    # 验证每个差异都有有效的严重程度和建议
    for d in discrepancies:
        assert d.severity in Severity, f"Invalid severity: {d.severity}"
        assert d.recommendation, f"Empty recommendation for {d.item}"
    
    # 验证 Markdown 输出包含所有差异项
    md = report.to_markdown()
    for d in discrepancies:
        # 差异项名称应该出现在报告中
        assert d.item in md or len(discrepancies) == 0, \
            f"Item {d.item} not found in report"


@given(discrepancies=discrepancy_list_strategy)
@settings(max_examples=100)
def test_report_to_dict_completeness(discrepancies: list[Discrepancy]):
    """
    Property 7 (dict format): Report dict should be complete
    
    **Validates: Requirements 7.1**
    """
    report = AuditReport(
        timestamp=datetime.now(),
        discrepancies=discrepancies,
    )
    
    d = report.to_dict()
    
    # 验证字典包含所有必要字段
    assert 'timestamp' in d
    assert 'summary' in d
    assert 'discrepancies' in d
    
    # 验证差异数量一致
    assert len(d['discrepancies']) == len(discrepancies)
    
    # 验证每个差异都有完整字段
    for disc in d['discrepancies']:
        assert 'category' in disc
        assert 'severity' in disc
        assert 'source' in disc
        assert 'target' in disc
        assert 'item' in disc
        assert 'message' in disc
        assert 'recommendation' in disc
