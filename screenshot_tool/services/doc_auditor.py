# -*- coding: utf-8 -*-
"""
文档审计模块

用于检查项目文档与实际代码的一致性，包括：
- structure.md 模块列表审计
- spec 文件隐藏导入审计
- 版本号一致性审计
- tech.md 依赖列表审计
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import re


class Severity(Enum):
    """差异严重程度"""
    CRITICAL = "critical"  # 会导致打包失败或运行错误
    WARNING = "warning"    # 文档不准确，可能误导开发者
    INFO = "info"          # 轻微问题，建议修复


class DiscrepancyCategory(Enum):
    """差异分类"""
    MODULE = "module"              # 模块列表一致性
    HIDDEN_IMPORT = "hidden_import"  # 隐藏导入完整性
    VERSION = "version"            # 版本号一致性
    DEPENDENCY = "dependency"      # 依赖列表一致性
    FEATURE = "feature"            # 功能描述完整性


@dataclass
class ModuleInfo:
    """模块信息"""
    name: str           # 模块名（不含 .py）
    path: Path          # 完整路径
    category: str       # 分类：core, services, ui


@dataclass
class DocumentContent:
    """文档内容"""
    path: Path
    modules: list[str] = field(default_factory=list)      # 提取的模块列表
    version: Optional[str] = None                          # 提取的版本号
    dependencies: list[str] = field(default_factory=list)  # 提取的依赖列表
    features: list[str] = field(default_factory=list)      # 提取的功能列表
    hidden_imports: list[str] = field(default_factory=list)  # 隐藏导入列表


@dataclass
class Discrepancy:
    """差异项"""
    category: DiscrepancyCategory  # 分类
    severity: Severity             # 严重程度
    source: str                    # 来源文件
    target: str                    # 目标文件
    item: str                      # 差异项名称
    message: str                   # 描述信息
    recommendation: str            # 修复建议


@dataclass
class AuditReport:
    """审计报告"""
    timestamp: datetime
    discrepancies: list[Discrepancy] = field(default_factory=list)
    
    @property
    def summary(self) -> dict[str, int]:
        """按严重程度统计差异数量"""
        result = {s.value: 0 for s in Severity}
        for d in self.discrepancies:
            result[d.severity.value] += 1
        return result
    
    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            "# 文档审计报告",
            "",
            f"**生成时间**: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 摘要",
            "",
            f"- 🔴 Critical: {self.summary['critical']}",
            f"- 🟡 Warning: {self.summary['warning']}",
            f"- 🔵 Info: {self.summary['info']}",
            f"- **总计**: {len(self.discrepancies)}",
            "",
        ]
        
        if not self.discrepancies:
            lines.append("✅ 所有文档与代码保持一致，无需更新。")
            return "\n".join(lines)
        
        # 按严重程度分组
        for severity in [Severity.CRITICAL, Severity.WARNING, Severity.INFO]:
            items = [d for d in self.discrepancies if d.severity == severity]
            if not items:
                continue
            
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[severity.value]
            lines.append(f"## {icon} {severity.value.upper()} ({len(items)})")
            lines.append("")
            
            for d in items:
                lines.append(f"### {d.item}")
                lines.append("")
                lines.append(f"- **分类**: {d.category.value}")
                lines.append(f"- **来源**: `{d.source}`")
                lines.append(f"- **目标**: `{d.target}`")
                lines.append(f"- **问题**: {d.message}")
                lines.append(f"- **建议**: {d.recommendation}")
                lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "summary": self.summary,
            "discrepancies": [
                {
                    "category": d.category.value,
                    "severity": d.severity.value,
                    "source": d.source,
                    "target": d.target,
                    "item": d.item,
                    "message": d.message,
                    "recommendation": d.recommendation,
                }
                for d in self.discrepancies
            ],
        }



class ModuleScanner:
    """模块扫描器 - 扫描文件系统中的实际模块"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
    
    def scan_directory(self, subdir: str) -> list[ModuleInfo]:
        """扫描指定子目录下的所有 .py 模块
        
        Args:
            subdir: 子目录名，如 'core', 'services', 'ui'
            
        Returns:
            模块信息列表
        """
        dir_path = self.base_path / subdir
        if not dir_path.exists():
            return []
        
        modules = []
        for file_path in dir_path.iterdir():
            # 跳过目录（如 __pycache__、word_card）
            if file_path.is_dir():
                continue
            # 跳过非 Python 文件
            if file_path.suffix != '.py':
                continue
            # 跳过 __init__.py
            if file_path.name == '__init__.py':
                continue
            
            modules.append(ModuleInfo(
                name=file_path.stem,
                path=file_path,
                category=subdir,
            ))
        
        return sorted(modules, key=lambda m: m.name)
    
    def scan_all(self) -> dict[str, list[ModuleInfo]]:
        """扫描所有模块目录
        
        Returns:
            {category: [modules]} 字典
        """
        return {
            'core': self.scan_directory('core'),
            'services': self.scan_directory('services'),
            'ui': self.scan_directory('ui'),
        }
    
    def get_all_module_names(self) -> dict[str, list[str]]:
        """获取所有模块名（不含路径）
        
        Returns:
            {category: [module_names]} 字典
        """
        all_modules = self.scan_all()
        return {
            category: [m.name for m in modules]
            for category, modules in all_modules.items()
        }



class DocumentScanner:
    """文档扫描器 - 解析文档内容，提取模块列表、版本号等信息"""
    
    def parse_structure_md(self, path: Path) -> dict[str, list[str]]:
        """解析 structure.md，提取模块列表
        
        Args:
            path: structure.md 文件路径
            
        Returns:
            {category: [module_names]} 字典
        """
        if not path.exists():
            return {'core': [], 'services': [], 'ui': []}
        
        content = path.read_text(encoding='utf-8')
        
        result = {
            'core': [],
            'services': [],
            'ui': [],
        }
        
        # 将内容按行分割，逐行解析
        lines = content.split('\n')
        current_section = None
        in_word_card = False
        
        for line in lines:
            # 检测目录标记
            if '├── core/' in line or 'core/' in line and '# 核心功能模块' in line:
                current_section = 'core'
                in_word_card = False
                continue
            elif '├── services/' in line or 'services/' in line and '# 服务模块' in line:
                current_section = 'services'
                in_word_card = False
                continue
            elif '├── ui/' in line or 'ui/' in line and '# 用户界面模块' in line:
                current_section = 'ui'
                in_word_card = False
                continue
            elif '├── tests/' in line or '└── tests/' in line:
                # tests 目录后面的内容不属于任何模块目录
                current_section = None
                in_word_card = False
                continue
            elif '├── build/' in line or '└── build/' in line:
                current_section = None
                in_word_card = False
                continue
            
            # 检测 word_card 子目录（services 下的子目录）
            if current_section == 'services' and 'word_card/' in line:
                in_word_card = True
                continue
            
            # 如果在 word_card 子目录中，跳过这些模块
            if in_word_card:
                # 检测是否离开 word_card（遇到同级或更高级的目录）
                if '├── ' in line and 'word_card' not in line and '.py' not in line:
                    in_word_card = False
                elif '└── ' in line and 'word_card' not in line and '.py' not in line:
                    in_word_card = False
                    # word_card 是 services 的最后一个子目录，之后是 ui
                    if 'ui/' in line:
                        current_section = 'ui'
                continue
            
            # 提取 .py 文件
            if current_section and '.py' in line:
                # 匹配 ├── xxx.py 或 └── xxx.py 格式
                match = re.search(r'[├└]── (\w+)\.py', line)
                if match:
                    module_name = match.group(1)
                    if module_name != '__init__':
                        result[current_section].append(module_name)
        
        return result
    
    def parse_spec_file(self, path: Path) -> DocumentContent:
        """解析 .spec 文件，提取隐藏导入列表
        
        Args:
            path: .spec 文件路径
            
        Returns:
            DocumentContent 对象，包含 hidden_imports 和 version
        """
        result = DocumentContent(path=path)
        
        if not path.exists():
            return result
        
        content = path.read_text(encoding='utf-8')
        
        # 提取版本号
        version_match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
        if version_match:
            result.version = version_match.group(1)
        
        # 提取项目模块的隐藏导入
        # 匹配 'screenshot_tool.xxx.yyy' 格式
        hidden_imports = re.findall(r"'(screenshot_tool\.[^']+)'", content)
        result.hidden_imports = sorted(set(hidden_imports))
        
        return result
    
    def parse_tech_md(self, path: Path) -> DocumentContent:
        """解析 tech.md，提取依赖列表
        
        Args:
            path: tech.md 文件路径
            
        Returns:
            DocumentContent 对象，包含 dependencies
        """
        result = DocumentContent(path=path)
        
        if not path.exists():
            return result
        
        content = path.read_text(encoding='utf-8')
        
        # 提取核心依赖表格中的包名
        # 格式: | package_name | description |
        deps = []
        
        # 匹配表格行
        table_rows = re.findall(r'\|\s*([a-zA-Z][a-zA-Z0-9_-]*)\s*\|', content)
        for dep in table_rows:
            # 过滤掉表头
            if dep.lower() not in ['库', '用途', 'lib', 'library', 'package']:
                deps.append(dep.lower().replace('-', '_'))
        
        # 提取测试框架部分的依赖
        # 格式: - pytest - 单元测试
        test_deps = re.findall(r'^-\s+([a-zA-Z][a-zA-Z0-9_-]*)\s+-', content, re.MULTILINE)
        for dep in test_deps:
            deps.append(dep.lower().replace('-', '_'))
        
        result.dependencies = sorted(set(deps))
        return result
    
    def parse_requirements_txt(self, path: Path) -> list[str]:
        """解析 requirements.txt，提取依赖列表
        
        Args:
            path: requirements.txt 文件路径
            
        Returns:
            依赖包名列表（标准化为小写下划线格式）
        """
        if not path.exists():
            return []
        
        content = path.read_text(encoding='utf-8')
        deps = []
        
        for line in content.split('\n'):
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue
            # 提取包名（去掉版本号和条件）
            match = re.match(r'^([a-zA-Z][a-zA-Z0-9_-]*)', line)
            if match:
                # 标准化：小写，连字符转下划线
                dep = match.group(1).lower().replace('-', '_')
                deps.append(dep)
        
        return sorted(set(deps))



class VersionScanner:
    """版本号扫描器 - 从各种文件中提取版本号"""
    
    def extract_from_init(self, path: Path) -> Optional[str]:
        """从 __init__.py 提取 __version__
        
        Args:
            path: __init__.py 文件路径
            
        Returns:
            版本号字符串，如 "1.7.2"
        """
        if not path.exists():
            return None
        
        content = path.read_text(encoding='utf-8')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else None
    
    def extract_from_spec(self, path: Path) -> Optional[str]:
        """从 .spec 文件提取 APP_VERSION
        
        Args:
            path: .spec 文件路径
            
        Returns:
            版本号字符串
        """
        if not path.exists():
            return None
        
        content = path.read_text(encoding='utf-8')
        match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else None
    
    def extract_from_markdown(self, path: Path) -> Optional[str]:
        """从 Markdown 文件提取版本号
        
        支持格式：
        - v1.2.3
        - version-1.2.3
        - 当前版本 v1.2.3
        - version-1.2.3-blue.svg
        
        Args:
            path: Markdown 文件路径
            
        Returns:
            版本号字符串（不含 v 前缀）
        """
        if not path.exists():
            return None
        
        content = path.read_text(encoding='utf-8')
        
        # 尝试多种格式
        patterns = [
            r'当前版本\s*v?(\d+\.\d+\.\d+)',  # 当前版本 v1.2.3
            r'version-(\d+\.\d+\.\d+)',        # version-1.2.3
            r'\bv(\d+\.\d+\.\d+)\b',           # v1.2.3
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def extract_all(self, project_root: Path) -> dict[str, Optional[str]]:
        """从所有相关文件提取版本号
        
        Args:
            project_root: 项目根目录
            
        Returns:
            {file_name: version} 字典
        """
        return {
            '__init__.py': self.extract_from_init(
                project_root / 'screenshot_tool' / '__init__.py'
            ),
            '虎哥截图-dir.spec': self.extract_from_spec(
                project_root / 'build' / '虎哥截图-dir.spec'
            ),
            'product.md': self.extract_from_markdown(
                project_root / '.kiro' / 'steering' / 'product.md'
            ),
            'README.md': self.extract_from_markdown(
                project_root / 'README.md'
            ),
        }



class ModuleComparator:
    """模块比较器 - 比较实际模块与文档记录"""
    
    def compare(
        self,
        actual: list[str],
        documented: list[str],
        category: str,
        doc_file: str,
    ) -> list[Discrepancy]:
        """比较实际模块与文档记录
        
        Args:
            actual: 实际模块名列表
            documented: 文档中记录的模块名列表
            category: 模块分类（core, services, ui）
            doc_file: 文档文件名
            
        Returns:
            差异列表
        """
        discrepancies = []
        actual_set = set(actual)
        documented_set = set(documented)
        
        # 实际存在但文档未记录
        missing_from_docs = actual_set - documented_set
        for module in sorted(missing_from_docs):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.MODULE,
                severity=Severity.WARNING,
                source=f"screenshot_tool/{category}/",
                target=doc_file,
                item=f"{category}/{module}.py",
                message=f"模块 {module}.py 存在于文件系统但未记录在 {doc_file}",
                recommendation=f"在 {doc_file} 的 {category}/ 目录下添加 {module}.py",
            ))
        
        # 文档记录但实际不存在
        documented_but_not_found = documented_set - actual_set
        for module in sorted(documented_but_not_found):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.MODULE,
                severity=Severity.WARNING,
                source=doc_file,
                target=f"screenshot_tool/{category}/",
                item=f"{category}/{module}.py",
                message=f"模块 {module}.py 记录在 {doc_file} 但文件系统中不存在",
                recommendation=f"从 {doc_file} 的 {category}/ 目录下移除 {module}.py",
            ))
        
        return discrepancies


class HiddenImportComparator:
    """隐藏导入比较器 - 比较实际模块与 spec 文件的隐藏导入"""
    
    def compare(
        self,
        actual_modules: dict[str, list[str]],
        hidden_imports: list[str],
        spec_file: str,
    ) -> list[Discrepancy]:
        """比较实际模块与 spec 文件的隐藏导入
        
        Args:
            actual_modules: {category: [module_names]} 字典
            hidden_imports: spec 文件中的隐藏导入列表
            spec_file: spec 文件名
            
        Returns:
            差异列表
        """
        discrepancies = []
        
        # 构建期望的隐藏导入集合
        expected_imports = set()
        for category, modules in actual_modules.items():
            for module in modules:
                expected_imports.add(f"screenshot_tool.{category}.{module}")
        
        # 从 hidden_imports 中提取项目模块
        actual_imports = set()
        for imp in hidden_imports:
            if imp.startswith('screenshot_tool.'):
                actual_imports.add(imp)
        
        # 检查缺失的导入
        missing = expected_imports - actual_imports
        for imp in sorted(missing):
            parts = imp.split('.')
            if len(parts) >= 3:
                category = parts[1]
                module = parts[2]
                discrepancies.append(Discrepancy(
                    category=DiscrepancyCategory.HIDDEN_IMPORT,
                    severity=Severity.CRITICAL,
                    source=f"screenshot_tool/{category}/{module}.py",
                    target=spec_file,
                    item=imp,
                    message=f"模块 {imp} 未添加到 {spec_file} 的 hiddenimports",
                    recommendation=f"在 {spec_file} 的 hiddenimports 列表中添加 '{imp}'",
                ))
        
        return discrepancies
    
    def compare_spec_files(
        self,
        imports1: list[str],
        imports2: list[str],
        file1: str,
        file2: str,
    ) -> list[Discrepancy]:
        """比较两个 spec 文件的项目模块导入是否一致
        
        Args:
            imports1: 第一个 spec 文件的隐藏导入
            imports2: 第二个 spec 文件的隐藏导入
            file1: 第一个 spec 文件名
            file2: 第二个 spec 文件名
            
        Returns:
            差异列表
        """
        discrepancies = []
        
        # 只比较项目模块
        proj_imports1 = {i for i in imports1 if i.startswith('screenshot_tool.')}
        proj_imports2 = {i for i in imports2 if i.startswith('screenshot_tool.')}
        
        # 在 file1 但不在 file2
        only_in_1 = proj_imports1 - proj_imports2
        for imp in sorted(only_in_1):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.HIDDEN_IMPORT,
                severity=Severity.CRITICAL,
                source=file1,
                target=file2,
                item=imp,
                message=f"模块 {imp} 在 {file1} 中但不在 {file2} 中",
                recommendation=f"在 {file2} 的 hiddenimports 列表中添加 '{imp}'",
            ))
        
        # 在 file2 但不在 file1
        only_in_2 = proj_imports2 - proj_imports1
        for imp in sorted(only_in_2):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.HIDDEN_IMPORT,
                severity=Severity.CRITICAL,
                source=file2,
                target=file1,
                item=imp,
                message=f"模块 {imp} 在 {file2} 中但不在 {file1} 中",
                recommendation=f"在 {file1} 的 hiddenimports 列表中添加 '{imp}'",
            ))
        
        return discrepancies


class VersionComparator:
    """版本比较器 - 比较多个文件的版本号"""
    
    def compare(self, versions: dict[str, Optional[str]]) -> list[Discrepancy]:
        """比较多个文件的版本号
        
        Args:
            versions: {file_name: version} 字典
            
        Returns:
            差异列表
        """
        discrepancies = []
        
        # 过滤掉 None 值
        valid_versions = {k: v for k, v in versions.items() if v is not None}
        
        if len(valid_versions) < 2:
            return discrepancies
        
        # 找出最常见的版本（作为基准）
        version_counts: dict[str, int] = {}
        for v in valid_versions.values():
            version_counts[v] = version_counts.get(v, 0) + 1
        
        base_version = max(version_counts.keys(), key=lambda v: version_counts[v])
        
        # 检查不一致的版本
        for file_name, version in valid_versions.items():
            if version != base_version:
                discrepancies.append(Discrepancy(
                    category=DiscrepancyCategory.VERSION,
                    severity=Severity.CRITICAL,
                    source=file_name,
                    target="其他文件",
                    item=f"版本号 {version}",
                    message=f"{file_name} 的版本号 {version} 与其他文件的 {base_version} 不一致",
                    recommendation=f"将 {file_name} 的版本号更新为 {base_version}",
                ))
        
        return discrepancies


class DependencyComparator:
    """依赖比较器 - 比较 requirements.txt 与 tech.md 的依赖"""
    
    def compare(
        self,
        requirements: list[str],
        documented: list[str],
    ) -> list[Discrepancy]:
        """比较 requirements.txt 与 tech.md 的依赖
        
        Args:
            requirements: requirements.txt 中的依赖列表
            documented: tech.md 中记录的依赖列表
            
        Returns:
            差异列表
        """
        discrepancies = []
        req_set = set(requirements)
        doc_set = set(documented)
        
        # 在 requirements.txt 但不在 tech.md
        undocumented = req_set - doc_set
        for dep in sorted(undocumented):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.DEPENDENCY,
                severity=Severity.WARNING,
                source="requirements.txt",
                target="tech.md",
                item=dep,
                message=f"依赖 {dep} 在 requirements.txt 中但未记录在 tech.md",
                recommendation=f"在 tech.md 的依赖表格中添加 {dep}",
            ))
        
        # 在 tech.md 但不在 requirements.txt（可能是可选依赖，降级为 INFO）
        documented_only = doc_set - req_set
        for dep in sorted(documented_only):
            discrepancies.append(Discrepancy(
                category=DiscrepancyCategory.DEPENDENCY,
                severity=Severity.INFO,
                source="tech.md",
                target="requirements.txt",
                item=dep,
                message=f"依赖 {dep} 记录在 tech.md 但不在 requirements.txt 中（可能是可选依赖）",
                recommendation=f"确认 {dep} 是否为可选依赖，如果不是则从 tech.md 移除",
            ))
        
        return discrepancies



class AuditEngine:
    """审计引擎 - 整合所有扫描器和比较器，执行完整审计"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.module_scanner = ModuleScanner(project_root / "screenshot_tool")
        self.document_scanner = DocumentScanner()
        self.version_scanner = VersionScanner()
        self.module_comparator = ModuleComparator()
        self.hidden_import_comparator = HiddenImportComparator()
        self.version_comparator = VersionComparator()
        self.dependency_comparator = DependencyComparator()
    
    def run_audit(self) -> AuditReport:
        """执行完整审计
        
        Returns:
            审计报告
        """
        discrepancies = []
        
        # 1. 审计 structure.md
        discrepancies.extend(self.audit_structure())
        
        # 2. 审计 spec 文件
        discrepancies.extend(self.audit_spec_files())
        
        # 3. 审计版本号
        discrepancies.extend(self.audit_versions())
        
        # 4. 审计依赖
        discrepancies.extend(self.audit_dependencies())
        
        return AuditReport(
            timestamp=datetime.now(),
            discrepancies=discrepancies,
        )
    
    def audit_structure(self) -> list[Discrepancy]:
        """审计 structure.md
        
        Returns:
            差异列表
        """
        discrepancies = []
        
        # 获取实际模块
        actual_modules = self.module_scanner.get_all_module_names()
        
        # 解析 structure.md
        structure_path = self.project_root / '.kiro' / 'steering' / 'structure.md'
        documented_modules = self.document_scanner.parse_structure_md(structure_path)
        
        # 比较每个目录
        for category in ['core', 'services', 'ui']:
            discrepancies.extend(self.module_comparator.compare(
                actual=actual_modules.get(category, []),
                documented=documented_modules.get(category, []),
                category=category,
                doc_file='structure.md',
            ))
        
        return discrepancies
    
    def audit_spec_files(self) -> list[Discrepancy]:
        """审计 spec 文件
        
        Returns:
            差异列表
        """
        discrepancies = []
        
        # 获取实际模块
        actual_modules = self.module_scanner.get_all_module_names()
        
        # 解析 spec 文件
        spec_path = self.project_root / 'build' / '虎哥截图-dir.spec'
        
        spec_content = self.document_scanner.parse_spec_file(spec_path)
        
        # 检查 spec 文件的隐藏导入
        discrepancies.extend(self.hidden_import_comparator.compare(
            actual_modules=actual_modules,
            hidden_imports=spec_content.hidden_imports,
            spec_file='虎哥截图-dir.spec',
        ))
        
        return discrepancies
    
    def audit_versions(self) -> list[Discrepancy]:
        """审计版本号
        
        Returns:
            差异列表
        """
        versions = self.version_scanner.extract_all(self.project_root)
        return self.version_comparator.compare(versions)
    
    def audit_dependencies(self) -> list[Discrepancy]:
        """审计依赖
        
        Returns:
            差异列表
        """
        # 解析 requirements.txt
        req_path = self.project_root / 'screenshot_tool' / 'requirements.txt'
        requirements = self.document_scanner.parse_requirements_txt(req_path)
        
        # 解析 tech.md
        tech_path = self.project_root / '.kiro' / 'steering' / 'tech.md'
        tech_content = self.document_scanner.parse_tech_md(tech_path)
        
        return self.dependency_comparator.compare(
            requirements=requirements,
            documented=tech_content.dependencies,
        )
