# =====================================================
# =============== 版本一致性测试 ===============
# =====================================================

"""
版本一致性测试

Property 5: Version Consistency
*For any* release build, the APP_VERSION in spec file SHALL match 
the __version__ in screenshot_tool/__init__.py.

从 v1.9.0 开始，统一使用单一 OpenVINO 后端，只有一个 spec 文件。

Validates: Requirements 4.1, 4.2
"""

import re
import pytest
from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录
    
    从测试文件位置向上查找，直到找到包含 screenshot_tool/__init__.py 的目录。
    
    Returns:
        项目根目录路径
    
    Raises:
        RuntimeError: 无法找到项目根目录
    """
    current = Path(__file__).resolve()
    searched_paths = []
    
    for parent in current.parents:
        searched_paths.append(str(parent))
        if (parent / 'screenshot_tool' / '__init__.py').exists():
            return parent
    
    raise RuntimeError(
        f"无法找到项目根目录。\n"
        f"当前文件: {current}\n"
        f"已搜索路径: {searched_paths}"
    )


def extract_version_from_init(file_path: Path) -> str:
    """从 __init__.py 中提取 __version__"""
    content = file_path.read_text(encoding='utf-8')
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 {file_path} 提取版本号")


def extract_version_from_spec(file_path: Path) -> str:
    """从 spec 文件中提取 APP_VERSION"""
    content = file_path.read_text(encoding='utf-8')
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 {file_path} 提取版本号")


def extract_version_from_product_md(file_path: Path) -> str:
    """从 product.md 中提取当前版本"""
    content = file_path.read_text(encoding='utf-8')
    match = re.search(r'##\s*当前版本\s*\n+v?([^\s\n]+)', content)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 {file_path} 提取版本号")


class TestVersionConsistency:
    """
    Property 5: Version Consistency
    
    验证所有版本号一致
    """
    
    @pytest.fixture
    def project_root(self) -> Path:
        return get_project_root()
    
    def test_init_version_exists(self, project_root):
        """验证 __init__.py 中存在版本号"""
        init_file = project_root / 'screenshot_tool' / '__init__.py'
        assert init_file.exists(), f"文件不存在: {init_file}"
        
        version = extract_version_from_init(init_file)
        assert version, "版本号不能为空"
        assert re.match(r'^\d+\.\d+\.\d+', version), f"版本号格式不正确: {version}"
    
    def test_general_spec_version_exists(self, project_root):
        """验证 spec 文件中存在版本号"""
        spec_file = project_root / 'build' / '虎哥截图-dir.spec'
        assert spec_file.exists(), f"文件不存在: {spec_file}"
        
        version = extract_version_from_spec(spec_file)
        assert version, "版本号不能为空"
    
    def test_product_md_version_exists(self, project_root):
        """验证 product.md 中存在版本号"""
        md_file = project_root / '.kiro' / 'steering' / 'product.md'
        assert md_file.exists(), f"文件不存在: {md_file}"
        
        version = extract_version_from_product_md(md_file)
        assert version, "版本号不能为空"
    
    def test_property_5_all_versions_match(self, project_root):
        """
        Property 5: 所有版本号必须一致
        
        *For any* release build, the APP_VERSION in spec file SHALL match 
        the __version__ in screenshot_tool/__init__.py.
        
        **Validates: Requirements 4.1, 4.2**
        """
        # 提取所有版本号
        init_version = extract_version_from_init(
            project_root / 'screenshot_tool' / '__init__.py'
        )
        spec_version = extract_version_from_spec(
            project_root / 'build' / '虎哥截图-dir.spec'
        )
        product_md_version = extract_version_from_product_md(
            project_root / '.kiro' / 'steering' / 'product.md'
        )
        
        # 验证一致性
        versions = {
            'screenshot_tool/__init__.py': init_version,
            'build/虎哥截图-dir.spec': spec_version,
            '.kiro/steering/product.md': product_md_version,
        }
        
        unique_versions = set(versions.values())
        
        assert len(unique_versions) == 1, \
            f"版本号不一致: {versions}"
    
    def test_init_and_spec_version_match(self, project_root):
        """__init__.py 和 spec 文件的版本号必须一致"""
        init_version = extract_version_from_init(
            project_root / 'screenshot_tool' / '__init__.py'
        )
        spec_version = extract_version_from_spec(
            project_root / 'build' / '虎哥截图-dir.spec'
        )
        
        assert init_version == spec_version, \
            f"版本不一致: __init__.py={init_version}, spec={spec_version}"
