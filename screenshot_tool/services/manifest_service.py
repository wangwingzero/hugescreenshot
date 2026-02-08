# =====================================================
# =============== 清单服务 ===============
# =====================================================

"""
清单服务 - 生成和管理版本清单文件

Feature: installer-incremental-update
Requirements: 3.1, 3.2, 3.3, 3.4, 4.2, 4.3, 4.5
"""

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class FileEntry:
    """文件条目
    
    Feature: installer-incremental-update
    Requirements: 3.1
    """
    path: str       # 相对路径，如 "虎哥截图.exe"
    size: int       # 文件大小（字节）
    hash: str       # SHA-256 哈希值（64 字符十六进制）
    
    def __post_init__(self):
        """验证数据"""
        if not self.path:
            raise ValueError("文件路径不能为空")
        if self.size < 0:
            raise ValueError("文件大小不能为负数")
        if len(self.hash) != 64:
            raise ValueError(f"哈希值长度必须为 64 字符，实际为 {len(self.hash)}")
        # 验证哈希值是有效的十六进制
        try:
            int(self.hash, 16)
        except ValueError:
            raise ValueError("哈希值必须是有效的十六进制字符串")


@dataclass
class Manifest:
    """版本清单
    
    Feature: installer-incremental-update
    Requirements: 3.1, 3.2, 3.4
    """
    version: str                        # 版本号，如 "2.2.1"
    build_time: str                     # 构建时间 ISO 8601 格式
    files: List[FileEntry] = field(default_factory=list)
    total_size: int = 0                 # 总大小（字节）
    
    def __post_init__(self):
        """验证并计算总大小"""
        if not self.version:
            raise ValueError("版本号不能为空")
        if not self.build_time:
            raise ValueError("构建时间不能为空")
        # 验证 ISO 8601 格式
        try:
            datetime.fromisoformat(self.build_time.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"构建时间格式无效: {self.build_time}")
        # 计算总大小
        if self.files and self.total_size == 0:
            self.total_size = sum(f.size for f in self.files)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "version": self.version,
            "build_time": self.build_time,
            "total_size": self.total_size,
            "files": [asdict(f) for f in self.files]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串
        
        Feature: installer-incremental-update
        Requirements: 3.4
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Manifest':
        """从字典创建"""
        files = [FileEntry(**f) for f in data.get("files", [])]
        return cls(
            version=data["version"],
            build_time=data["build_time"],
            files=files,
            total_size=data.get("total_size", 0)
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Manifest':
        """从 JSON 字符串反序列化
        
        Feature: installer-incremental-update
        Requirements: 3.4
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def get_file_by_path(self, path: str) -> Optional[FileEntry]:
        """根据路径获取文件条目"""
        for f in self.files:
            if f.path == path:
                return f
        return None
    
    def get_all_paths(self) -> Set[str]:
        """获取所有文件路径集合"""
        return {f.path for f in self.files}



@dataclass
class DeltaResult:
    """增量计算结果
    
    Feature: installer-incremental-update
    Requirements: 4.2, 4.3
    """
    added_files: List[FileEntry] = field(default_factory=list)      # 新增文件
    modified_files: List[FileEntry] = field(default_factory=list)   # 修改的文件
    deleted_files: List[str] = field(default_factory=list)          # 删除的文件路径
    unchanged_files: List[str] = field(default_factory=list)        # 未变更的文件路径
    delta_size: int = 0                                             # 增量下载大小
    full_size: int = 0                                              # 完整下载大小
    
    def __post_init__(self):
        """计算增量大小"""
        if self.delta_size == 0:
            self.delta_size = (
                sum(f.size for f in self.added_files) +
                sum(f.size for f in self.modified_files)
            )
    
    @property
    def has_changes(self) -> bool:
        """是否有变更"""
        return bool(self.added_files or self.modified_files or self.deleted_files)
    
    @property
    def files_to_download(self) -> List[FileEntry]:
        """需要下载的文件列表"""
        return self.added_files + self.modified_files


class ManifestGenerator:
    """清单生成器 - 构建时生成文件清单
    
    Feature: installer-incremental-update
    Requirements: 3.1, 3.2, 3.3
    """
    
    # 忽略的文件/目录模式
    IGNORE_PATTERNS = {
        '__pycache__',
        '.pyc',
        '.pyo',
        '.git',
        '.gitignore',
        'Thumbs.db',
        '.DS_Store',
    }
    
    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """计算文件 SHA-256 哈希
        
        Args:
            file_path: 文件路径
            
        Returns:
            64 字符十六进制哈希值
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # 分块读取，避免大文件内存问题
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _should_ignore(self, path: str) -> bool:
        """检查是否应该忽略该路径"""
        for pattern in self.IGNORE_PATTERNS:
            if pattern in path:
                return True
        return False
    
    def generate(self, source_dir: str, version: str) -> Manifest:
        """扫描目录生成清单
        
        Args:
            source_dir: 源目录路径
            version: 版本号
            
        Returns:
            Manifest 对象
            
        Feature: installer-incremental-update
        Requirements: 3.1, 3.2, 3.3
        """
        source_path = Path(source_dir)
        if not source_path.exists():
            raise FileNotFoundError(f"源目录不存在: {source_dir}")
        
        files = []
        
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(source_path))
                # 统一使用正斜杠
                rel_path = rel_path.replace('\\', '/')
                
                if self._should_ignore(rel_path):
                    continue
                
                file_size = file_path.stat().st_size
                file_hash = self.calculate_file_hash(str(file_path))
                
                files.append(FileEntry(
                    path=rel_path,
                    size=file_size,
                    hash=file_hash
                ))
        
        # 按路径排序，保证一致性
        files.sort(key=lambda f: f.path)
        
        build_time = datetime.now(timezone.utc).isoformat()
        
        return Manifest(
            version=version,
            build_time=build_time,
            files=files
        )
    
    def save(self, manifest: Manifest, output_path: str) -> None:
        """保存清单为 JSON 文件
        
        Args:
            manifest: Manifest 对象
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(manifest.to_json())
    
    def load(self, file_path: str) -> Manifest:
        """从文件加载清单
        
        Args:
            file_path: 清单文件路径
            
        Returns:
            Manifest 对象
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            return Manifest.from_json(f.read())


class DeltaCalculator:
    """增量计算器
    
    Feature: installer-incremental-update
    Requirements: 4.2, 4.3, 4.5
    """
    
    def calculate(self, local: Manifest, remote: Manifest) -> DeltaResult:
        """计算两个版本之间的差异
        
        Args:
            local: 本地版本清单
            remote: 远程版本清单
            
        Returns:
            DeltaResult 对象
            
        Feature: installer-incremental-update
        Requirements: 4.2, 4.3
        """
        local_paths = local.get_all_paths()
        remote_paths = remote.get_all_paths()
        
        added_files = []
        modified_files = []
        deleted_files = []
        unchanged_files = []
        
        # 检查远程文件
        for remote_file in remote.files:
            local_file = local.get_file_by_path(remote_file.path)
            
            if local_file is None:
                # 新增文件
                added_files.append(remote_file)
            elif local_file.hash != remote_file.hash:
                # 修改的文件
                modified_files.append(remote_file)
            else:
                # 未变更
                unchanged_files.append(remote_file.path)
        
        # 检查删除的文件
        for path in local_paths:
            if path not in remote_paths:
                deleted_files.append(path)
        
        return DeltaResult(
            added_files=added_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            unchanged_files=unchanged_files,
            full_size=remote.total_size
        )
    
    def should_use_delta(self, delta: DeltaResult, threshold: float = 0.5) -> bool:
        """判断是否应该使用增量更新
        
        Args:
            delta: 增量计算结果
            threshold: 阈值，增量大小占完整大小的比例
            
        Returns:
            True 如果应该使用增量更新
            
        Feature: installer-incremental-update
        Requirements: 4.5
        """
        if delta.full_size == 0:
            return False
        
        ratio = delta.delta_size / delta.full_size
        return ratio < threshold
