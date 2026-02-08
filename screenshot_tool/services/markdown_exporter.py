# =====================================================
# =============== Markdown 导出服务 ===============
# =====================================================

"""
Markdown 导出服务 - 将 Markdown 转换为其他格式

使用 Pandoc 将 Markdown 内容导出为 Word (docx)、PDF、HTML 等格式。
支持 pypandoc 库和 subprocess 两种调用方式。

Feature: markdown-converter
Task: 5.2 在 Python 端实现 Markdown 导出
Requirements: 4.1
"""

import os
import subprocess
import tempfile
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# 调试日志
try:
    from screenshot_tool.core.async_logger import async_debug_log as _debug_log
except ImportError:
    def _debug_log(msg, tag="INFO"): print(f"[{tag}] {msg}")


class ExportFormat(Enum):
    """导出格式枚举"""
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"


@dataclass
class ExportResult:
    """导出结果数据类
    
    Feature: markdown-converter
    Requirements: 4.1
    """
    success: bool
    output_path: str = ""
    error: str = ""


class MarkdownExporter:
    """Markdown 导出器
    
    使用 Pandoc 将 Markdown 内容转换为其他格式。
    优先使用 pypandoc 库，如果不可用则降级到 subprocess 调用。
    
    Feature: markdown-converter
    Task: 5.2 在 Python 端实现 Markdown 导出
    Requirements: 4.1
    """
    
    # 支持的导出格式
    SUPPORTED_FORMATS = {"docx", "pdf", "html"}
    
    # 格式到 Pandoc 输出格式的映射
    FORMAT_MAPPING = {
        "docx": "docx",
        "pdf": "pdf",
        "html": "html",
    }
    
    def __init__(self):
        """初始化导出器"""
        self._pypandoc_available: Optional[bool] = None
        self._pandoc_path: Optional[str] = None
    
    def _check_pypandoc(self) -> bool:
        """检查 pypandoc 是否可用
        
        Returns:
            pypandoc 是否可用
        """
        if self._pypandoc_available is not None:
            return self._pypandoc_available
        
        try:
            import pypandoc
            # 验证 Pandoc 是否已安装
            pypandoc.get_pandoc_version()
            self._pypandoc_available = True
            _debug_log("pypandoc 可用", "MD_EXPORT")
        except ImportError:
            self._pypandoc_available = False
            _debug_log("pypandoc 未安装", "MD_EXPORT")
        except OSError:
            self._pypandoc_available = False
            _debug_log("pypandoc 已安装但 Pandoc 未找到", "MD_EXPORT")
        
        return self._pypandoc_available
    
    def _find_pandoc(self) -> Optional[str]:
        """查找 Pandoc 可执行文件路径
        
        Returns:
            Pandoc 路径，如果未找到返回 None
        """
        if self._pandoc_path is not None:
            return self._pandoc_path
        
        # 尝试在 PATH 中查找
        pandoc_path = shutil.which("pandoc")
        if pandoc_path:
            self._pandoc_path = pandoc_path
            _debug_log(f"找到 Pandoc: {pandoc_path}", "MD_EXPORT")
            return pandoc_path
        
        # Windows 常见安装路径
        common_paths = [
            r"C:\Program Files\Pandoc\pandoc.exe",
            r"C:\Program Files (x86)\Pandoc\pandoc.exe",
            os.path.expanduser(r"~\AppData\Local\Pandoc\pandoc.exe"),
        ]
        
        for path in common_paths:
            if os.path.isfile(path):
                self._pandoc_path = path
                _debug_log(f"找到 Pandoc: {path}", "MD_EXPORT")
                return path
        
        _debug_log("未找到 Pandoc", "MD_EXPORT")
        return None
    
    def is_available(self) -> Tuple[bool, str]:
        """检查导出功能是否可用
        
        Returns:
            (是否可用, 错误信息)
        """
        if self._check_pypandoc():
            return True, ""
        
        if self._find_pandoc():
            return True, ""
        
        return False, "未安装 Pandoc。请从 https://pandoc.org/installing.html 下载安装。"
    
    def export(self, markdown: str, output_path: str, format: str) -> ExportResult:
        """导出 Markdown 到指定格式
        
        Args:
            markdown: Markdown 内容
            output_path: 输出文件路径
            format: 输出格式 ("docx", "pdf", "html")
            
        Returns:
            ExportResult 导出结果
            
        Requirements: 4.1
        """
        _debug_log(f"开始导出 Markdown 到 {format}: {output_path}", "MD_EXPORT")
        
        # 验证格式
        format_lower = format.lower()
        if format_lower not in self.SUPPORTED_FORMATS:
            return ExportResult(
                success=False,
                error=f"不支持的格式: {format}。支持的格式: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        # 验证内容
        if not markdown or not markdown.strip():
            return ExportResult(
                success=False,
                error="Markdown 内容为空"
            )
        
        # 验证输出路径
        if not output_path:
            return ExportResult(
                success=False,
                error="输出路径为空"
            )
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                return ExportResult(
                    success=False,
                    error=f"无法创建输出目录: {e}"
                )
        
        # 检查可用性
        available, error = self.is_available()
        if not available:
            return ExportResult(success=False, error=error)
        
        # 优先使用 pypandoc
        if self._check_pypandoc():
            return self._export_with_pypandoc(markdown, output_path, format_lower)
        
        # 降级到 subprocess
        return self._export_with_subprocess(markdown, output_path, format_lower)
    
    def _export_with_pypandoc(self, markdown: str, output_path: str, 
                               format: str) -> ExportResult:
        """使用 pypandoc 导出
        
        Args:
            markdown: Markdown 内容
            output_path: 输出文件路径
            format: 输出格式
            
        Returns:
            ExportResult 导出结果
        """
        try:
            import pypandoc
            
            _debug_log(f"使用 pypandoc 导出到 {format}", "MD_EXPORT")
            
            # 获取 Pandoc 输出格式
            pandoc_format = self.FORMAT_MAPPING.get(format, format)
            
            # 额外参数
            extra_args = []
            
            # PDF 需要指定 PDF 引擎
            if format == "pdf":
                # 优先使用 xelatex（支持中文）
                extra_args.extend(["--pdf-engine=xelatex"])
                # 如果 xelatex 不可用，尝试其他引擎
                # pypandoc 会自动处理
            
            # HTML 添加独立文档标记
            if format == "html":
                extra_args.append("--standalone")
            
            # 执行转换
            output = pypandoc.convert_text(
                markdown,
                pandoc_format,
                format="markdown",
                outputfile=output_path,
                extra_args=extra_args if extra_args else None
            )
            
            # pypandoc.convert_text 返回空字符串表示成功写入文件
            if output == "" or output is None:
                _debug_log(f"pypandoc 导出成功: {output_path}", "MD_EXPORT")
                return ExportResult(success=True, output_path=output_path)
            else:
                # 如果有返回内容，可能是警告
                _debug_log(f"pypandoc 返回: {output}", "MD_EXPORT")
                return ExportResult(success=True, output_path=output_path)
                
        except Exception as e:
            error_msg = str(e)
            _debug_log(f"pypandoc 导出失败: {error_msg}", "MD_EXPORT")
            
            # 处理常见错误
            if "xelatex" in error_msg.lower() or "pdflatex" in error_msg.lower():
                return ExportResult(
                    success=False,
                    error="导出 PDF 需要安装 LaTeX。请安装 MiKTeX 或 TeX Live。"
                )
            
            return ExportResult(success=False, error=f"导出失败: {error_msg}")
    
    def _export_with_subprocess(self, markdown: str, output_path: str,
                                 format: str) -> ExportResult:
        """使用 subprocess 调用 Pandoc 导出
        
        Args:
            markdown: Markdown 内容
            output_path: 输出文件路径
            format: 输出格式
            
        Returns:
            ExportResult 导出结果
        """
        pandoc_path = self._find_pandoc()
        if not pandoc_path:
            return ExportResult(
                success=False,
                error="未找到 Pandoc 可执行文件"
            )
        
        _debug_log(f"使用 subprocess 调用 Pandoc 导出到 {format}", "MD_EXPORT")
        
        # 创建临时文件存储 Markdown 内容
        temp_md_file = None
        try:
            # 创建临时 Markdown 文件
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.md', 
                delete=False, 
                encoding='utf-8'
            ) as f:
                f.write(markdown)
                temp_md_file = f.name
            
            # 构建命令
            cmd = [pandoc_path, temp_md_file, "-o", output_path]
            
            # PDF 需要指定引擎
            if format == "pdf":
                cmd.extend(["--pdf-engine=xelatex"])
            
            # HTML 添加独立文档标记
            if format == "html":
                cmd.append("--standalone")
            
            _debug_log(f"执行命令: {' '.join(cmd)}", "MD_EXPORT")
            
            # 执行转换
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60 秒超时
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                _debug_log(f"subprocess 导出成功: {output_path}", "MD_EXPORT")
                return ExportResult(success=True, output_path=output_path)
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                _debug_log(f"subprocess 导出失败: {error_msg}", "MD_EXPORT")
                
                # 处理常见错误
                if "xelatex" in error_msg.lower() or "pdflatex" in error_msg.lower():
                    return ExportResult(
                        success=False,
                        error="导出 PDF 需要安装 LaTeX。请安装 MiKTeX 或 TeX Live。"
                    )
                
                return ExportResult(success=False, error=f"导出失败: {error_msg}")
                
        except subprocess.TimeoutExpired:
            return ExportResult(success=False, error="导出超时（60秒）")
        except Exception as e:
            return ExportResult(success=False, error=f"导出失败: {str(e)}")
        finally:
            # 清理临时文件
            if temp_md_file and os.path.exists(temp_md_file):
                try:
                    os.unlink(temp_md_file)
                except Exception:
                    pass


# 单例实例
_exporter_instance: Optional[MarkdownExporter] = None


def get_exporter() -> MarkdownExporter:
    """获取 MarkdownExporter 单例实例
    
    Returns:
        MarkdownExporter 实例
    """
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = MarkdownExporter()
    return _exporter_instance


def export_markdown(markdown: str, output_path: str, format: str) -> ExportResult:
    """导出 Markdown 到指定格式（便捷函数）
    
    Args:
        markdown: Markdown 内容
        output_path: 输出文件路径
        format: 输出格式 ("docx", "pdf", "html")
        
    Returns:
        ExportResult 导出结果
        
    Requirements: 4.1
    """
    return get_exporter().export(markdown, output_path, format)


def is_export_available() -> Tuple[bool, str]:
    """检查导出功能是否可用（便捷函数）
    
    Returns:
        (是否可用, 错误信息)
    """
    return get_exporter().is_available()
