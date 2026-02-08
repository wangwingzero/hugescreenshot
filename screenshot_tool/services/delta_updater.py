# =====================================================
# =============== 增量更新器 ===============
# =====================================================

"""
增量更新器 - 下载并应用增量更新

Feature: installer-incremental-update
Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.2, 6.3, 6.4, 6.6
"""

import hashlib
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests
from PySide6.QtCore import QObject, Signal

from screenshot_tool.core.async_logger import async_debug_log
from screenshot_tool.services.manifest_service import (
    FileEntry, Manifest, DeltaResult, ManifestGenerator
)


@dataclass
class DownloadProgress:
    """下载进度"""
    filename: str
    downloaded: int
    total: int
    speed_kbps: float


class DeltaUpdater(QObject):
    """增量更新器 - 下载并应用增量更新
    
    Feature: installer-incremental-update
    Requirements: 5.1, 5.2, 5.3, 6.2, 6.3, 6.4, 6.6
    """
    
    # 信号
    file_progress = Signal(str, int, int, float)  # (filename, downloaded, total, speed)
    overall_progress = Signal(int, int)            # (files_done, total_files)
    update_completed = Signal()
    update_failed = Signal(str)
    
    # 配置
    CHUNK_SIZE = 8192
    CONNECT_TIMEOUT = 30
    READ_TIMEOUT = 120
    MAX_RETRIES = 3
    
    def __init__(self, install_dir: str, parent=None):
        """初始化增量更新器
        
        Args:
            install_dir: 安装目录路径
            parent: 父对象
        """
        super().__init__(parent)
        self._install_dir = Path(install_dir)
        self._backup_dir: Optional[Path] = None
        self._temp_dir: Optional[Path] = None
        self._cancel_flag = False
        self._update_thread: Optional[threading.Thread] = None
    
    @property
    def install_dir(self) -> Path:
        """获取安装目录"""
        return self._install_dir
    
    def cancel(self) -> None:
        """取消更新"""
        self._cancel_flag = True
    
    def start_update(self, delta: DeltaResult, base_url: str) -> None:
        """开始增量更新（后台线程）
        
        Args:
            delta: 增量计算结果
            base_url: 文件下载基础 URL
        """
        self._cancel_flag = False
        self._update_thread = threading.Thread(
            target=self._update_worker,
            args=(delta, base_url),
            daemon=True
        )
        self._update_thread.start()
    
    def _update_worker(self, delta: DeltaResult, base_url: str) -> None:
        """更新工作线程"""
        try:
            # 创建临时目录
            self._temp_dir = Path(tempfile.mkdtemp(prefix='hugescreenshot_update_'))
            self._backup_dir = Path(tempfile.mkdtemp(prefix='hugescreenshot_backup_'))
            
            async_debug_log(f"[DELTA_UPDATE] 临时目录: {self._temp_dir}")
            async_debug_log(f"[DELTA_UPDATE] 备份目录: {self._backup_dir}")
            
            # 1. 下载增量文件
            if not self._download_delta(delta, base_url):
                return
            
            if self._cancel_flag:
                self.update_failed.emit("更新已取消")
                return
            
            # 2. 验证下载文件
            if not self._verify_downloads(delta):
                self.update_failed.emit("文件验证失败")
                return
            
            # 3. 备份将被替换的文件
            if not self._create_backup(delta):
                self.update_failed.emit("备份创建失败")
                return
            
            # 4. 应用更新
            if not self._apply_update(delta):
                # 回滚
                self._rollback()
                self.update_failed.emit("更新应用失败，已回滚")
                return
            
            # 5. 清理
            self._cleanup()
            
            async_debug_log("[DELTA_UPDATE] 更新完成")
            self.update_completed.emit()
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 更新异常: {e}")
            self._rollback()
            self.update_failed.emit(f"更新失败: {str(e)}")
        finally:
            # 清理临时目录
            self._cleanup_temp()
    
    def _download_delta(self, delta: DeltaResult, base_url: str) -> bool:
        """下载增量文件
        
        Feature: installer-incremental-update
        Requirements: 5.1, 5.2
        """
        files_to_download = delta.files_to_download
        total_files = len(files_to_download)
        
        async_debug_log(f"[DELTA_UPDATE] 需要下载 {total_files} 个文件")
        
        for i, file_entry in enumerate(files_to_download):
            if self._cancel_flag:
                return False
            
            # 构建下载 URL
            url = f"{base_url.rstrip('/')}/files/{file_entry.path}"
            save_path = self._temp_dir / file_entry.path
            
            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 下载文件（带重试）
            success = self._download_file_with_retry(
                url, str(save_path), file_entry
            )
            
            if not success:
                async_debug_log(f"[DELTA_UPDATE] 下载失败: {file_entry.path}")
                return False
            
            self.overall_progress.emit(i + 1, total_files)
        
        return True

    def _download_file_with_retry(
        self, url: str, save_path: str, file_entry: FileEntry
    ) -> bool:
        """下载文件（带重试）
        
        Feature: installer-incremental-update
        Requirements: 5.4
        """
        for attempt in range(self.MAX_RETRIES):
            if self._cancel_flag:
                return False
            
            try:
                success = self._download_file(url, save_path, file_entry)
                if success:
                    return True
                    
            except Exception as e:
                async_debug_log(
                    f"[DELTA_UPDATE] 下载尝试 {attempt + 1}/{self.MAX_RETRIES} 失败: {e}"
                )
            
            if attempt < self.MAX_RETRIES - 1:
                time.sleep(1)  # 等待后重试
        
        return False
    
    def _download_file(
        self, url: str, save_path: str, file_entry: FileEntry
    ) -> bool:
        """下载单个文件"""
        try:
            response = requests.get(
                url,
                stream=True,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT)
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', file_entry.size))
            downloaded = 0
            start_time = time.time()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancel_flag:
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算速度
                        elapsed = time.time() - start_time
                        speed = (downloaded / 1024) / elapsed if elapsed > 0 else 0
                        
                        self.file_progress.emit(
                            file_entry.path, downloaded, total_size, speed
                        )
            
            return True
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 下载错误 {file_entry.path}: {e}")
            return False
    
    def _verify_downloads(self, delta: DeltaResult) -> bool:
        """验证下载文件的哈希
        
        Feature: installer-incremental-update
        Requirements: 5.3
        """
        async_debug_log("[DELTA_UPDATE] 验证下载文件...")
        
        for file_entry in delta.files_to_download:
            file_path = self._temp_dir / file_entry.path
            
            if not file_path.exists():
                async_debug_log(f"[DELTA_UPDATE] 文件不存在: {file_entry.path}")
                return False
            
            actual_hash = self._calculate_hash(str(file_path))
            if actual_hash != file_entry.hash:
                async_debug_log(
                    f"[DELTA_UPDATE] 哈希不匹配: {file_entry.path}\n"
                    f"  期望: {file_entry.hash}\n"
                    f"  实际: {actual_hash}"
                )
                return False
        
        async_debug_log("[DELTA_UPDATE] 所有文件验证通过")
        return True
    
    @staticmethod
    def _calculate_hash(file_path: str) -> str:
        """计算文件 SHA-256 哈希"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _create_backup(self, delta: DeltaResult) -> bool:
        """备份将被替换的文件
        
        Feature: installer-incremental-update
        Requirements: 6.2
        """
        async_debug_log("[DELTA_UPDATE] 创建备份...")
        
        # 备份修改的文件
        for file_entry in delta.modified_files:
            src = self._install_dir / file_entry.path
            if src.exists():
                dst = self._backup_dir / file_entry.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst))
                    async_debug_log(f"[DELTA_UPDATE] 备份: {file_entry.path}")
                except Exception as e:
                    async_debug_log(f"[DELTA_UPDATE] 备份失败 {file_entry.path}: {e}")
                    return False
        
        # 备份将被删除的文件
        for path in delta.deleted_files:
            src = self._install_dir / path
            if src.exists():
                dst = self._backup_dir / path
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst))
                    async_debug_log(f"[DELTA_UPDATE] 备份(删除): {path}")
                except Exception as e:
                    async_debug_log(f"[DELTA_UPDATE] 备份失败 {path}: {e}")
                    return False
        
        return True
    
    def _apply_update(self, delta: DeltaResult) -> bool:
        """应用更新（原子替换）
        
        Feature: installer-incremental-update
        Requirements: 6.3
        """
        async_debug_log("[DELTA_UPDATE] 应用更新...")
        
        try:
            # 1. 添加新文件
            for file_entry in delta.added_files:
                src = self._temp_dir / file_entry.path
                dst = self._install_dir / file_entry.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                async_debug_log(f"[DELTA_UPDATE] 添加: {file_entry.path}")
            
            # 2. 替换修改的文件（原子操作）
            for file_entry in delta.modified_files:
                src = self._temp_dir / file_entry.path
                dst = self._install_dir / file_entry.path
                
                # 原子替换：先写入临时文件，再重命名
                temp_dst = dst.with_suffix(dst.suffix + '.new')
                shutil.copy2(str(src), str(temp_dst))
                
                # 删除旧文件并重命名
                if dst.exists():
                    dst.unlink()
                temp_dst.rename(dst)
                
                async_debug_log(f"[DELTA_UPDATE] 替换: {file_entry.path}")
            
            # 3. 删除文件
            for path in delta.deleted_files:
                file_path = self._install_dir / path
                if file_path.exists():
                    file_path.unlink()
                    async_debug_log(f"[DELTA_UPDATE] 删除: {path}")
            
            return True
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 应用更新失败: {e}")
            return False
    
    def _rollback(self) -> bool:
        """回滚到备份
        
        Feature: installer-incremental-update
        Requirements: 6.4
        """
        if not self._backup_dir or not self._backup_dir.exists():
            return False
        
        async_debug_log("[DELTA_UPDATE] 回滚更新...")
        
        try:
            # 恢复所有备份文件
            for backup_file in self._backup_dir.rglob('*'):
                if backup_file.is_file():
                    rel_path = backup_file.relative_to(self._backup_dir)
                    dst = self._install_dir / rel_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(backup_file), str(dst))
                    async_debug_log(f"[DELTA_UPDATE] 恢复: {rel_path}")
            
            return True
            
        except Exception as e:
            async_debug_log(f"[DELTA_UPDATE] 回滚失败: {e}")
            return False
    
    def _cleanup(self) -> None:
        """清理备份文件
        
        Feature: installer-incremental-update
        Requirements: 6.6
        """
        async_debug_log("[DELTA_UPDATE] 清理备份...")
        
        if self._backup_dir and self._backup_dir.exists():
            try:
                shutil.rmtree(str(self._backup_dir))
                async_debug_log(f"[DELTA_UPDATE] 已删除备份目录: {self._backup_dir}")
            except Exception as e:
                async_debug_log(f"[DELTA_UPDATE] 清理备份失败: {e}")
    
    def _cleanup_temp(self) -> None:
        """清理临时目录"""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(str(self._temp_dir))
            except Exception:
                pass


def verify_installation_integrity(install_dir: str, manifest: Manifest) -> bool:
    """验证安装完整性
    
    Feature: installer-incremental-update
    Requirements: 8.5
    
    Args:
        install_dir: 安装目录
        manifest: 版本清单
        
    Returns:
        True 如果所有文件存在且哈希匹配
    """
    install_path = Path(install_dir)
    
    for file_entry in manifest.files:
        file_path = install_path / file_entry.path
        
        # 检查文件存在
        if not file_path.exists():
            async_debug_log(f"[INTEGRITY] 文件缺失: {file_entry.path}")
            return False
        
        # 检查哈希
        actual_hash = DeltaUpdater._calculate_hash(str(file_path))
        if actual_hash != file_entry.hash:
            async_debug_log(f"[INTEGRITY] 哈希不匹配: {file_entry.path}")
            return False
    
    return True
