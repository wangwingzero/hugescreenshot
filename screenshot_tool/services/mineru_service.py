# =====================================================
# =============== MinerU 文件转换服务 ===============
# =====================================================

"""
MinerU 文件转 Markdown 服务

使用 MinerU API 将文件转换为 Markdown 格式。
支持格式：PDF、Word(.doc/.docx)、PPT(.ppt/.pptx)、图片(.png/.jpg/.jpeg)、HTML

Feature: file-to-markdown
"""

import os
import time
import tempfile
import zipfile
from typing import Optional, Callable, List, Tuple
from dataclasses import dataclass

import requests


@dataclass
class MinerUError(Exception):
    """MinerU API 错误"""
    message: str
    code: Optional[str] = None
    
    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


@dataclass
class ConvertResult:
    """转换结果"""
    pdf_path: str  # 保留原名以兼容旧代码，实际存储任意文件路径
    markdown_path: Optional[str] = None
    error_message: Optional[str] = None
    
    @property
    def file_path(self) -> str:
        """文件路径（pdf_path 的别名）"""
        return self.pdf_path
    
    @property
    def success(self) -> bool:
        return self.markdown_path is not None and self.error_message is None


class MinerUService:
    """MinerU 文件转 Markdown 服务
    
    使用 MinerU API 将文件转换为 Markdown 格式。
    支持格式：PDF、Word、PPT、图片、HTML
    支持单文件和批量转换。
    """
    
    BASE_URL = "https://mineru.net/api/v4"
    MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
    MAX_PAGES = 600
    POLL_INTERVAL = 2  # 秒
    MAX_POLL_TIME = 300  # 5分钟超时
    
    def __init__(self, api_token: str, model_version: str = "vlm"):
        """初始化服务
        
        Args:
            api_token: MinerU API Token
            model_version: 模型版本，pipeline 或 vlm
        """
        self.api_token = api_token
        self.model_version = model_version
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_token}"
        self._session.headers["Content-Type"] = "application/json"
    
    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = ('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.png', '.jpg', '.jpeg', '.html')
    
    def convert_file(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        output_dir: str = ""
    ) -> str:
        """转换单个文件
        
        Args:
            file_path: 文件路径（支持 PDF、Word、PPT、图片、HTML）
            progress_callback: 进度回调 (status: str, progress: float 0-1)
            output_dir: 输出目录，为空则使用源文件目录
        
        Returns:
            生成的 Markdown 文件路径
        
        Raises:
            MinerUError: 转换失败
            FileNotFoundError: 文件不存在
            ValueError: 文件过大或格式不支持
        """
        # 检查文件
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 检查文件格式
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}，支持格式: PDF、Word、PPT、图片、HTML")
        
        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            raise ValueError(f"文件过大 ({size_mb:.1f}MB)，最大支持 200MB")
        
        if progress_callback:
            progress_callback("上传文件...", 0.1)
        
        # 上传文件（返回 batch_id，系统会自动创建任务）
        batch_id = self._upload_file(file_path)
        
        if progress_callback:
            progress_callback("解析中...", 0.3)
        
        # 轮询批量任务状态
        zip_url = self._poll_batch_task(batch_id, progress_callback)
        
        if progress_callback:
            progress_callback("下载结果...", 0.9)
        
        # 确定输出目录
        actual_output_dir = output_dir if output_dir else os.path.dirname(file_path)
        
        # 下载并提取 Markdown
        md_path = self._download_and_extract(zip_url, actual_output_dir, file_path)
        
        if progress_callback:
            progress_callback("完成", 1.0)
        
        return md_path
    
    # 保留旧方法名作为别名，保持向后兼容
    def convert_pdf(
        self,
        pdf_path: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """转换单个文件（向后兼容别名）"""
        return self.convert_file(pdf_path, progress_callback)
    
    def convert_folder(
        self,
        folder_path: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[ConvertResult]:
        """批量转换文件夹中的文件
        
        Args:
            folder_path: 文件夹路径
            progress_callback: 进度回调
        
        Returns:
            转换结果列表
        """
        # 扫描支持的文件
        files = []
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(self.SUPPORTED_EXTENSIONS):
                files.append(os.path.join(folder_path, filename))
        
        if not files:
            return []
        
        results = []
        total = len(files)
        
        for i, file_path in enumerate(files):
            try:
                # 计算整体进度
                base_progress = i / total
                
                # 使用工厂函数避免闭包陷阱，确保 i 和 total 被正确捕获
                def make_sub_progress(current_i: int, total_count: int):
                    def sub_progress(status: str, progress: float):
                        if progress_callback:
                            overall = (current_i / total_count) + (progress / total_count)
                            progress_callback(f"[{current_i+1}/{total_count}] {status}", overall)
                    return sub_progress
                
                md_path = self.convert_file(file_path, make_sub_progress(i, total))
                results.append(ConvertResult(pdf_path=file_path, markdown_path=md_path))
            except Exception as e:
                results.append(ConvertResult(pdf_path=file_path, error_message=str(e)))
        
        return results
    
    def _upload_file(self, file_path: str) -> str:
        """上传文件获取 URL 并上传文件
        
        MinerU API 流程：
        1. 先调用 /file-urls/batch 获取上传 URL
        2. 用 PUT 请求上传文件到返回的 URL
        3. 系统会自动创建解析任务
        
        Args:
            file_path: 文件路径
        
        Returns:
            batch_id: 批量任务 ID，用于查询结果
        
        Raises:
            MinerUError: 上传失败
        """
        url = f"{self.BASE_URL}/file-urls/batch"
        
        filename = os.path.basename(file_path)
        
        # 第一步：获取上传 URL（JSON 请求）
        payload = {
            "files": [{"name": filename}],
            "model_version": self.model_version
        }
        
        try:
            response = self._session.post(url, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise MinerUError("获取上传链接超时，请检查网络连接")
        except requests.exceptions.RequestException as e:
            raise MinerUError(f"获取上传链接失败: {e}")
        
        data = response.json()
        
        if data.get("code") != 0:
            raise MinerUError(
                data.get("msg", "获取上传链接失败"),
                code=str(data.get("code"))
            )
        
        # 获取上传 URL 和 batch_id
        file_urls = data.get("data", {}).get("file_urls", [])
        batch_id = data.get("data", {}).get("batch_id")
        
        if not file_urls:
            raise MinerUError("获取上传链接成功但未返回 URL")
        if not batch_id:
            raise MinerUError("获取上传链接成功但未返回 batch_id")
        
        upload_url = file_urls[0]
        
        # 第二步：用 PUT 请求上传文件
        try:
            with open(file_path, 'rb') as f:
                # 上传时不需要设置 Content-Type
                upload_response = requests.put(upload_url, data=f, timeout=120)
                if upload_response.status_code != 200:
                    raise MinerUError(f"文件上传失败，状态码: {upload_response.status_code}")
        except requests.exceptions.Timeout:
            raise MinerUError("文件上传超时，请检查网络连接")
        except requests.exceptions.RequestException as e:
            raise MinerUError(f"文件上传失败: {e}")
        
        return batch_id
    
    def _create_task(self, file_url: str) -> str:
        """创建解析任务
        
        Args:
            file_url: 文件 URL
        
        Returns:
            任务 ID
        
        Raises:
            MinerUError: 创建失败
        """
        url = f"{self.BASE_URL}/extract/task"
        
        payload = {
            "url": file_url,
            "model_version": self.model_version
        }
        
        try:
            response = self._session.post(url, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise MinerUError(f"创建任务失败: {e}")
        
        data = response.json()
        
        if data.get("code") != 0:
            raise MinerUError(
                data.get("msg", "创建任务失败"),
                code=str(data.get("code"))
            )
        
        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise MinerUError("创建任务成功但未返回任务 ID")
        
        return task_id
    
    def _poll_task(
        self,
        task_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """轮询单个任务状态
        
        Args:
            task_id: 任务 ID
            progress_callback: 进度回调
        
        Returns:
            ZIP 文件 URL
        
        Raises:
            MinerUError: 任务失败或超时
        """
        url = f"{self.BASE_URL}/extract/task/{task_id}"
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > self.MAX_POLL_TIME:
                raise MinerUError("任务超时，请稍后重试")
            
            try:
                response = self._session.get(url, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise MinerUError(f"查询任务状态失败: {e}")
            
            data = response.json()
            
            if data.get("code") != 0:
                raise MinerUError(
                    data.get("msg", "查询任务状态失败"),
                    code=str(data.get("code"))
                )
            
            task_data = data.get("data", {})
            state = task_data.get("state", "")
            
            if state == "done":
                zip_url = task_data.get("full_zip_url")
                if not zip_url:
                    raise MinerUError("任务完成但未返回结果 URL")
                return zip_url
            
            elif state == "failed":
                err_msg = task_data.get("err_msg", "解析失败，请检查 PDF 文件是否有效")
                raise MinerUError(err_msg)
            
            elif state in ("pending", "running", "converting", "waiting-file"):
                # 更新进度
                if progress_callback:
                    # 根据时间估算进度 (0.3 - 0.9)
                    progress = 0.3 + min(0.6, elapsed / self.MAX_POLL_TIME * 0.6)
                    status_map = {
                        "waiting-file": "等待文件上传...",
                        "pending": "等待处理...",
                        "running": "解析中...",
                        "converting": "转换中..."
                    }
                    progress_callback(status_map.get(state, "处理中..."), progress)
                
                time.sleep(self.POLL_INTERVAL)
            
            else:
                # 未知状态，继续等待
                time.sleep(self.POLL_INTERVAL)
    
    def _poll_batch_task(
        self,
        batch_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """轮询批量任务状态
        
        Args:
            batch_id: 批量任务 ID
            progress_callback: 进度回调
        
        Returns:
            ZIP 文件 URL
        
        Raises:
            MinerUError: 任务失败或超时
        """
        url = f"{self.BASE_URL}/extract-results/batch/{batch_id}"
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > self.MAX_POLL_TIME:
                raise MinerUError("任务超时，请稍后重试")
            
            try:
                response = self._session.get(url, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise MinerUError(f"查询任务状态失败: {e}")
            
            data = response.json()
            
            if data.get("code") != 0:
                raise MinerUError(
                    data.get("msg", "查询任务状态失败"),
                    code=str(data.get("code"))
                )
            
            # 获取第一个文件的结果（单文件上传）
            extract_results = data.get("data", {}).get("extract_result", [])
            if not extract_results:
                # 可能还在等待，继续轮询
                if progress_callback:
                    progress = 0.3 + min(0.6, elapsed / self.MAX_POLL_TIME * 0.6)
                    progress_callback("等待处理...", progress)
                time.sleep(self.POLL_INTERVAL)
                continue
            
            result = extract_results[0]
            state = result.get("state", "")
            
            if state == "done":
                zip_url = result.get("full_zip_url")
                if not zip_url:
                    raise MinerUError("任务完成但未返回结果 URL")
                return zip_url
            
            elif state == "failed":
                err_msg = result.get("err_msg", "解析失败，请检查 PDF 文件是否有效")
                raise MinerUError(err_msg)
            
            elif state in ("pending", "running", "converting", "waiting-file"):
                # 更新进度
                if progress_callback:
                    progress = 0.3 + min(0.6, elapsed / self.MAX_POLL_TIME * 0.6)
                    status_map = {
                        "waiting-file": "等待文件上传...",
                        "pending": "等待处理...",
                        "running": "解析中...",
                        "converting": "转换中..."
                    }
                    progress_callback(status_map.get(state, "处理中..."), progress)
                
                time.sleep(self.POLL_INTERVAL)
            
            else:
                # 未知状态，继续等待
                time.sleep(self.POLL_INTERVAL)
    
    def _download_and_extract(
        self,
        zip_url: str,
        output_dir: str,
        pdf_path: str
    ) -> str:
        """下载 ZIP 并提取 Markdown
        
        Args:
            zip_url: ZIP 文件 URL
            output_dir: 输出目录
            pdf_path: 原始 PDF 路径（用于生成输出文件名）
        
        Returns:
            Markdown 文件路径
        
        Raises:
            MinerUError: 下载或解压失败
        """
        # 下载 ZIP
        try:
            response = requests.get(zip_url, timeout=120)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise MinerUError(f"下载结果失败: {e}")
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name
        
        try:
            # 解压并查找 Markdown 文件
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                md_files = [f for f in zf.namelist() if f.endswith('.md')]
                
                if not md_files:
                    raise MinerUError("ZIP 中未找到 Markdown 文件")
                
                # 提取第一个 Markdown 文件
                md_content = zf.read(md_files[0]).decode('utf-8')
        except zipfile.BadZipFile:
            raise MinerUError("下载的文件不是有效的 ZIP 格式")
        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        
        # 生成输出文件名（与 PDF 同名）
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        md_filename = f"{pdf_basename}.md"
        md_path = os.path.join(output_dir, md_filename)
        
        # 如果文件已存在，添加序号
        counter = 1
        while os.path.exists(md_path):
            md_filename = f"{pdf_basename}_{counter}.md"
            md_path = os.path.join(output_dir, md_filename)
            counter += 1
        
        # 写入 Markdown 文件
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return md_path
