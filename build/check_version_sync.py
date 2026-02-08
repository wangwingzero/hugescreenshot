#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
版本一致性检查脚本

检查以下文件中的版本号是否一致：
- screenshot_tool/__init__.py - __version__
- build/虎哥截图-dir.spec - APP_VERSION
- .kiro/steering/product.md - 当前版本

Requirements: 4.1, 4.2

Usage:
    python build/check_version_sync.py
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def extract_version_from_init(file_path: Path) -> Optional[str]:
    """从 __init__.py 中提取 __version__
    
    Args:
        file_path: __init__.py 文件路径
    
    Returns:
        版本号字符串，提取失败返回 None
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    except FileNotFoundError:
        print(f"  文件不存在: {file_path}")
    except PermissionError:
        print(f"  无权限读取: {file_path}")
    except UnicodeDecodeError:
        print(f"  文件编码错误: {file_path}")
    except OSError as e:
        print(f"  读取 {file_path} 失败: {e}")
    return None


def extract_version_from_spec(file_path: Path) -> Optional[str]:
    """从 spec 文件中提取 APP_VERSION
    
    Args:
        file_path: spec 文件路径
    
    Returns:
        版本号字符串，提取失败返回 None
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    except FileNotFoundError:
        print(f"  文件不存在: {file_path}")
    except PermissionError:
        print(f"  无权限读取: {file_path}")
    except UnicodeDecodeError:
        print(f"  文件编码错误: {file_path}")
    except OSError as e:
        print(f"  读取 {file_path} 失败: {e}")
    return None


def extract_version_from_product_md(file_path: Path) -> Optional[str]:
    """从 product.md 中提取当前版本
    
    Args:
        file_path: product.md 文件路径
    
    Returns:
        版本号字符串，提取失败返回 None
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        # 匹配 "## 当前版本" 后面的版本号
        match = re.search(r'##\s*当前版本\s*\n+v?([^\s\n]+)', content)
        if match:
            return match.group(1)
    except FileNotFoundError:
        print(f"  文件不存在: {file_path}")
    except PermissionError:
        print(f"  无权限读取: {file_path}")
    except UnicodeDecodeError:
        print(f"  文件编码错误: {file_path}")
    except OSError as e:
        print(f"  读取 {file_path} 失败: {e}")
    return None


def check_version_sync() -> Tuple[bool, Dict[str, Optional[str]], List[str]]:
    """
    检查所有版本号是否一致
    
    Returns:
        (is_synced, versions_dict, messages): 是否同步，版本字典，详细信息
    """
    messages = []
    versions = {}
    
    # 定位项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # 定义需要检查的文件
    files_to_check = {
        'screenshot_tool/__init__.py': (
            project_root / 'HuGeScreenshot-python' / 'screenshot_tool' / '__init__.py',
            extract_version_from_init
        ),
        'build/虎哥截图-dir.spec': (
            project_root / 'build' / '虎哥截图-dir.spec',
            extract_version_from_spec
        ),
        '.kiro/steering/product.md': (
            project_root / '.kiro' / 'steering' / 'product.md',
            extract_version_from_product_md
        ),
    }
    
    # 提取所有版本号
    for name, (file_path, extractor) in files_to_check.items():
        if not file_path.exists():
            messages.append(f"❌ 文件不存在: {name}")
            versions[name] = None
        else:
            version = extractor(file_path)
            versions[name] = version
            if version:
                messages.append(f"  {name}: {version}")
            else:
                messages.append(f"❌ 无法提取版本号: {name}")
    
    # 检查一致性
    valid_versions = [v for v in versions.values() if v is not None]
    
    if not valid_versions:
        messages.append("❌ 没有找到任何有效的版本号")
        return False, versions, messages
    
    unique_versions = set(valid_versions)
    
    if len(unique_versions) == 1:
        messages.append(f"\n✅ 所有版本号一致: {valid_versions[0]}")
        return True, versions, messages
    else:
        messages.append(f"\n❌ 版本号不一致:")
        for name, version in versions.items():
            if version:
                messages.append(f"   {name}: {version}")
        return False, versions, messages


def main():
    """主函数"""
    print("=" * 60)
    print("版本一致性检查")
    print("=" * 60)
    print()
    print("检查以下文件的版本号:")
    
    is_synced, versions, messages = check_version_sync()
    
    for msg in messages:
        print(msg)
    
    print()
    print("=" * 60)
    if is_synced:
        print("✅ 版本检查通过")
        return 0
    else:
        print("❌ 版本不一致，请同步更新后重新检查")
        print()
        print("需要同步更新的文件:")
        print("  - screenshot_tool/__init__.py: __version__")
        print("  - build/虎哥截图-dir.spec: APP_VERSION")
        print("  - .kiro/steering/product.md: 当前版本")
        return 1


if __name__ == "__main__":
    sys.exit(main())
