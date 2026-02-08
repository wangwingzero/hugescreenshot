# -*- coding: utf-8 -*-
# =====================================================
# 虎哥截图 - 一键构建安装包脚本
# =====================================================
"""
一键构建安装包

使用方法：
    python build/build_installer.py [--modern]

参数：
    --modern    使用 PySide6 现代化安装器（默认）
    --legacy    使用 Inno Setup 传统安装器

步骤（现代模式）：
    1. 检查版本号一致性
    2. PyInstaller 目录模式打包主程序
    3. PyInstaller 打包安装器（内嵌主程序）

步骤（传统模式）：
    1. 检查版本号一致性
    2. PyInstaller 目录模式打包
    3. Inno Setup 编译安装包

输出：
    dist/HuGeScreenshot-{版本号}-Setup.exe

Feature: fullupdate-inplace-install
Requirements: 5.3
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"


def print_header(title: str):
    """打印标题"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def get_version_from_init() -> str:
    """从 __init__.py 获取版本号"""
    init_file = PROJECT_ROOT / "HuGeScreenshot-python" / "screenshot_tool" / "__init__.py"
    try:
        with open(init_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=")[1].strip().strip('"\'')
    except (FileNotFoundError, IOError):
        pass
    return ""


def get_version_from_spec() -> str:
    """从 spec 文件获取版本号"""
    spec_file = BUILD_DIR / "虎哥截图-dir.spec"
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            for line in f:
                if "APP_VERSION" in line and "=" in line:
                    return line.split("=")[1].strip().strip('"\'')
    except (FileNotFoundError, IOError):
        pass
    return ""


def get_version_from_iss() -> str:
    """从 iss 文件获取版本号"""
    iss_file = BUILD_DIR / "虎哥截图.iss"
    try:
        with open(iss_file, "r", encoding="utf-8") as f:
            for line in f:
                if "#define MyAppVersion" in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        return parts[1]
    except (FileNotFoundError, IOError):
        pass
    return ""


def check_version_sync() -> tuple[bool, str]:
    """检查版本号一致性"""
    print_header("步骤 1: 检查版本号一致性")
    
    v_init = get_version_from_init()
    v_spec = get_version_from_spec()
    v_iss = get_version_from_iss()
    
    print(f"  __init__.py:      {v_init}")
    print(f"  虎哥截图-dir.spec: {v_spec}")
    print(f"  虎哥截图.iss:      {v_iss}")
    
    if v_init == v_spec == v_iss:
        print(f"\n  ✓ 版本号一致: {v_init}")
        return True, v_init
    else:
        print("\n  ✗ 版本号不一致！请先同步版本号。")
        return False, ""


def run_pyinstaller() -> bool:
    """运行 PyInstaller 目录模式打包"""
    print_header("步骤 2: PyInstaller 目录模式打包")
    
    spec_file = BUILD_DIR / "虎哥截图-dir.spec"
    
    # 清理旧的输出
    output_dir = DIST_DIR / "虎哥截图"
    if output_dir.exists():
        print(f"  清理旧输出: {output_dir}")
        shutil.rmtree(output_dir)
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--clean",
    ]
    
    print(f"  执行: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    
    if result.returncode != 0:
        print("\n  ✗ PyInstaller 打包失败！")
        return False
    
    # 验证输出
    exe_file = output_dir / "虎哥截图.exe"
    if not exe_file.exists():
        print(f"\n  ✗ 输出文件不存在: {exe_file}")
        return False
    
    print(f"\n  ✓ 打包完成: {output_dir}")
    return True


# 注意：manifest 生成功能已移除，全量更新不再需要 manifest.json
# Feature: fullupdate-inplace-install
# Requirements: 5.3
# def run_generate_manifest() -> bool:
#     """生成 manifest.json（已弃用）"""
#     pass


def find_inno_setup() -> str:
    """查找 Inno Setup 编译器路径"""
    # 常见安装路径
    possible_paths = [
        r"D:\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"D:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"D:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # 尝试从 PATH 中查找
    result = shutil.which("ISCC")
    if result:
        return result
    
    return ""


def run_inno_setup(version: str) -> bool:
    """运行 Inno Setup 编译安装包"""
    print_header("步骤 3: Inno Setup 编译安装包")
    
    iscc = find_inno_setup()
    if not iscc:
        print("  ✗ 未找到 Inno Setup！")
        print("  请从 https://jrsoftware.org/isinfo.php 下载安装")
        return False
    
    print(f"  Inno Setup: {iscc}")
    
    iss_file = BUILD_DIR / "虎哥截图.iss"
    
    cmd = [iscc, str(iss_file)]
    
    print(f"  执行: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(BUILD_DIR))
    
    if result.returncode != 0:
        print("\n  ✗ Inno Setup 编译失败！")
        return False
    
    # 验证输出
    setup_file = DIST_DIR / f"HuGeScreenshot-{version}-Setup.exe"
    if not setup_file.exists():
        print(f"\n  ✗ 安装包不存在: {setup_file}")
        return False
    
    # 显示文件大小
    size_mb = setup_file.stat().st_size / (1024 * 1024)
    print(f"\n  ✓ 安装包生成完成: {setup_file}")
    print(f"    大小: {size_mb:.1f} MB")
    return True


def update_installer_spec_version(version: str) -> bool:
    """更新安装器 spec 文件中的版本号"""
    spec_file = BUILD_DIR / "installer.spec"
    if not spec_file.exists():
        return False
    
    try:
        content = spec_file.read_text(encoding='utf-8')
        import re
        new_content = re.sub(
            r'APP_VERSION = "[^"]*"',
            f'APP_VERSION = "{version}"',
            content
        )
        spec_file.write_text(new_content, encoding='utf-8')
        return True
    except Exception as e:
        print(f"  更新版本号失败: {e}")
        return False


def run_modern_installer(version: str) -> bool:
    """运行 PySide6 现代化安装器打包"""
    print_header("步骤 3: 打包现代化安装器")
    
    # 更新安装器 spec 中的版本号
    update_installer_spec_version(version)
    
    spec_file = BUILD_DIR / "installer.spec"
    if not spec_file.exists():
        print(f"  ✗ 安装器 spec 文件不存在: {spec_file}")
        return False
    
    # 检查主程序是否已打包
    app_dir = DIST_DIR / "虎哥截图"
    if not app_dir.exists():
        print(f"  ✗ 主程序目录不存在: {app_dir}")
        print("  请先运行 PyInstaller 打包主程序")
        return False
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--clean",
    ]
    
    print(f"  执行: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    
    if result.returncode != 0:
        print("\n  ✗ 安装器打包失败！")
        return False
    
    # 验证输出
    setup_file = DIST_DIR / f"HuGeScreenshot-{version}-Setup.exe"
    if not setup_file.exists():
        print(f"\n  ✗ 安装包不存在: {setup_file}")
        return False
    
    # 显示文件大小
    size_mb = setup_file.stat().st_size / (1024 * 1024)
    print(f"\n  ✓ 安装包生成完成: {setup_file}")
    print(f"    大小: {size_mb:.1f} MB")
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="虎哥截图 - 一键构建安装包")
    parser.add_argument(
        "--modern", action="store_true", default=True,
        help="使用 PySide6 现代化安装器（默认）"
    )
    parser.add_argument(
        "--legacy", action="store_true",
        help="使用 Inno Setup 传统安装器"
    )
    args = parser.parse_args()
    
    use_modern = not args.legacy
    
    print()
    print("╔════════════════════════════════════════════════════════╗")
    print("║          虎哥截图 - 一键构建安装包                     ║")
    print("╚════════════════════════════════════════════════════════╝")
    
    if use_modern:
        print("  模式: PySide6 现代化安装器")
    else:
        print("  模式: Inno Setup 传统安装器")
    
    # 步骤 1: 检查版本号
    ok, version = check_version_sync()
    if not ok:
        sys.exit(1)
    
    # 步骤 2: PyInstaller 打包主程序
    if not run_pyinstaller():
        sys.exit(1)
    
    # 步骤 3: 打包安装器
    if use_modern:
        if not run_modern_installer(version):
            sys.exit(1)
    else:
        if not run_inno_setup(version):
            sys.exit(1)
    
    # 完成
    print_header("构建完成")
    print(f"  版本: {version}")
    print(f"  安装包: dist/HuGeScreenshot-{version}-Setup.exe")
    print(f"  目录包: dist/虎哥截图/")
    print()
    print("  下一步:")
    print("    1. 测试安装包")
    print("    2. 上传到 GitHub Releases")
    print()


if __name__ == "__main__":
    main()
