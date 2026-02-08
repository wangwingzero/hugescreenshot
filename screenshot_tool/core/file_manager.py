# =====================================================
# =============== 文件管理器 ===============
# =====================================================

"""
文件管理器 - 负责截图和识别文字结果的保存

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
Property 8: Screenshot Save Produces Valid File
Property 9: Filename Generation Pattern
"""

import os
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple, List

from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer, QIODevice


@dataclass
class SaveResult:
    """保存结果"""
    success: bool
    file_path: str = ""
    error: Optional[str] = None
    
    @classmethod
    def success_result(cls, file_path: str) -> "SaveResult":
        """创建成功结果"""
        return cls(success=True, file_path=file_path)
    
    @classmethod
    def error_result(cls, error_msg: str) -> "SaveResult":
        """创建错误结果"""
        return cls(success=False, error=error_msg)


class FileManager:
    """
    文件管理器 - 负责截图和识别文字结果的保存
    
    文件命名规则:
    - 日期文件夹: YYYY年MM月DD日
    - 截图文件: 截图XXX.png (XXX为序号)
    - 时间戳文件: 截图_YYYYMMDD_HHMMSS.png
    - 识别文字结果: 截图XXX.txt
    """
    
    # 文件名模式
    SCREENSHOT_PATTERN = r"截图(\d+)\.png"
    DATE_FOLDER_FORMAT = "%Y年%m月%d日"
    
    # 时间戳文件名格式
    TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
    TIMESTAMP_PATTERN = r"截图_(\d{8}_\d{6})(?:_(\d+))?\.png"
    
    def __init__(self, base_path: str = ""):
        """
        初始化文件管理器
        
        Args:
            base_path: 基础保存路径
        """
        self.base_path = base_path or os.path.expanduser("~/Pictures/Screenshots")
    
    def set_base_path(self, path: str):
        """设置基础保存路径"""
        self.base_path = path
    
    def get_base_path(self) -> str:
        """获取基础保存路径"""
        return self.base_path
    
    def get_date_folder(self, date: Optional[datetime] = None) -> str:
        """
        获取日期文件夹路径
        
        Args:
            date: 日期，默认为今天
            
        Returns:
            str: 日期文件夹完整路径
        """
        if date is None:
            date = datetime.now()
        
        folder_name = date.strftime(self.DATE_FOLDER_FORMAT)
        return os.path.join(self.base_path, folder_name)
    
    def ensure_folder_exists(self, folder_path: str) -> Tuple[bool, Optional[str]]:
        """
        确保文件夹存在
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        try:
            if not os.path.exists(folder_path):
                os.makedirs(folder_path, exist_ok=True)
            return True, None
        except PermissionError:
            return False, f"没有权限创建文件夹: {folder_path}"
        except OSError as e:
            return False, f"创建文件夹失败: {str(e)}"

    def get_next_filename(self, folder_path: str) -> str:
        """
        获取下一个可用的文件名
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            str: 下一个可用的文件名（不含路径）
        """
        # 获取现有文件的最大序号
        max_num = 0
        
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                match = re.match(self.SCREENSHOT_PATTERN, filename)
                if match:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
        
        # 生成下一个序号
        next_num = max_num + 1
        return f"截图{next_num:03d}.png"
    
    def get_next_filepath(self, date: Optional[datetime] = None) -> str:
        """
        获取下一个可用的完整文件路径
        
        Args:
            date: 日期，默认为今天
            
        Returns:
            str: 完整文件路径
        """
        folder_path = self.get_date_folder(date)
        filename = self.get_next_filename(folder_path)
        return os.path.join(folder_path, filename)
    
    def save_screenshot(
        self,
        image: QImage,
        file_path: Optional[str] = None,
        quality: int = -1
    ) -> SaveResult:
        """
        保存截图
        
        Args:
            image: QImage图片
            file_path: 保存路径，默认自动生成
            quality: PNG质量 (-1为默认)
            
        Returns:
            SaveResult: 保存结果
        """
        if image.isNull():
            return SaveResult.error_result("图片为空")
        
        # 自动生成路径
        if not file_path:
            file_path = self.get_next_filepath()
        
        # 确保目录存在
        folder_path = os.path.dirname(file_path)
        success, error = self.ensure_folder_exists(folder_path)
        if not success:
            return SaveResult.error_result(error)
        
        # 保存图片
        try:
            if image.save(file_path, "PNG", quality):
                return SaveResult.success_result(file_path)
            else:
                return SaveResult.error_result("保存图片失败")
        except Exception as e:
            return SaveResult.error_result(f"保存图片出错: {str(e)}")
    
    def save_screenshot_with_highlights(
        self,
        image: QImage,
        file_path: Optional[str] = None
    ) -> SaveResult:
        """
        保存带高亮的截图
        
        Args:
            image: 已渲染高亮的QImage图片
            file_path: 保存路径，默认自动生成
            
        Returns:
            SaveResult: 保存结果
        """
        # 与普通保存相同，高亮已经渲染到图片上
        return self.save_screenshot(image, file_path)
    
    def save_ocr_results_to_file(
        self,
        text: str,
        file_path: str
    ) -> SaveResult:
        """
        保存识别文字结果到文本文件
        
        Args:
            text: OCR识别的文字
            file_path: 保存路径（.txt文件）
            
        Returns:
            SaveResult: 保存结果
        """
        if not text:
            return SaveResult.error_result("文本为空")
        
        # 确保目录存在
        folder_path = os.path.dirname(file_path)
        if folder_path:
            success, error = self.ensure_folder_exists(folder_path)
            if not success:
                return SaveResult.error_result(error)
        
        # 保存文本
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return SaveResult.success_result(file_path)
        except PermissionError:
            return SaveResult.error_result(f"没有权限写入文件: {file_path}")
        except Exception as e:
            return SaveResult.error_result(f"保存文本出错: {str(e)}")

    def save_screenshot_with_ocr(
        self,
        image: QImage,
        ocr_text: str,
        image_path: Optional[str] = None
    ) -> Tuple[SaveResult, SaveResult]:
        """
        同时保存截图和识别文字结果
        
        Args:
            image: QImage图片
            ocr_text: OCR识别的文字
            image_path: 图片保存路径，默认自动生成
            
        Returns:
            Tuple[SaveResult, SaveResult]: (图片保存结果, 文本保存结果)
        """
        # 保存图片
        image_result = self.save_screenshot(image, image_path)
        
        if not image_result.success:
            return image_result, SaveResult.error_result("图片保存失败，跳过识别文字结果保存")
        
        # 生成对应的文本文件路径
        text_path = os.path.splitext(image_result.file_path)[0] + ".txt"
        
        # 保存识别文字结果
        if ocr_text:
            text_result = self.save_ocr_results_to_file(ocr_text, text_path)
        else:
            text_result = SaveResult.success_result("")  # 空文本不保存
        
        return image_result, text_result
    
    def get_existing_screenshots(
        self,
        date: Optional[datetime] = None
    ) -> List[str]:
        """
        获取指定日期的所有截图文件
        
        Args:
            date: 日期，默认为今天
            
        Returns:
            List[str]: 截图文件路径列表
        """
        folder_path = self.get_date_folder(date)
        
        if not os.path.exists(folder_path):
            return []
        
        screenshots = []
        for filename in os.listdir(folder_path):
            if re.match(self.SCREENSHOT_PATTERN, filename):
                screenshots.append(os.path.join(folder_path, filename))
        
        return sorted(screenshots)
    
    def get_screenshot_count(self, date: Optional[datetime] = None) -> int:
        """
        获取指定日期的截图数量
        
        Args:
            date: 日期，默认为今天
            
        Returns:
            int: 截图数量
        """
        return len(self.get_existing_screenshots(date))
    
    def validate_save_path(self, path: str) -> Tuple[bool, Optional[str]]:
        """
        验证保存路径是否有效
        
        Args:
            path: 保存路径
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        if not path:
            return False, "路径为空"
        
        # 检查目录是否存在或可创建
        folder_path = os.path.dirname(path) or "."
        
        if os.path.exists(folder_path):
            if not os.path.isdir(folder_path):
                return False, f"路径不是目录: {folder_path}"
            if not os.access(folder_path, os.W_OK):
                return False, f"没有写入权限: {folder_path}"
        else:
            # 检查父目录
            parent = os.path.dirname(folder_path)
            if parent and not os.path.exists(parent):
                return False, f"父目录不存在: {parent}"
        
        return True, None
    
    def generate_unique_filename(
        self,
        base_name: str,
        extension: str,
        folder_path: str
    ) -> str:
        """
        生成唯一的文件名
        
        Args:
            base_name: 基础文件名
            extension: 文件扩展名
            folder_path: 文件夹路径
            
        Returns:
            str: 唯一的文件名
        """
        filename = f"{base_name}.{extension}"
        full_path = os.path.join(folder_path, filename)
        
        counter = 1
        while os.path.exists(full_path):
            filename = f"{base_name}_{counter}.{extension}"
            full_path = os.path.join(folder_path, filename)
            counter += 1
        
        return filename

    def generate_timestamp_filename(
        self,
        folder_path: str,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        生成时间戳格式的文件名
        
        格式: 截图_YYYYMMDD_HHMMSS.png
        如果存在同名文件，添加序号: 截图_YYYYMMDD_HHMMSS_1.png
        
        Feature: save-to-folder-dialog
        Requirements: 3.1, 3.2, 3.3
        
        Args:
            folder_path: 目标文件夹路径
            timestamp: 时间戳，默认为当前时间
            
        Returns:
            str: 完整文件路径
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # 生成基础文件名
        time_str = timestamp.strftime(self.TIMESTAMP_FORMAT)
        base_filename = f"截图_{time_str}.png"
        full_path = os.path.join(folder_path, base_filename)
        
        # 检查文件是否存在，如果存在则添加序号
        if not os.path.exists(full_path):
            return full_path
        
        # 文件已存在，添加序号
        counter = 1
        while True:
            filename = f"截图_{time_str}_{counter}.png"
            full_path = os.path.join(folder_path, filename)
            if not os.path.exists(full_path):
                return full_path
            counter += 1
    
    def save_screenshot_to_folder(
        self,
        image: QImage,
        folder_path: str,
        timestamp: Optional[datetime] = None
    ) -> SaveResult:
        """
        保存截图到指定文件夹（使用时间戳文件名）
        
        Feature: save-to-folder-dialog
        Requirements: 1.4, 3.1, 3.2, 3.3
        
        Args:
            image: QImage 图片
            folder_path: 目标文件夹路径
            timestamp: 时间戳，默认为当前时间
            
        Returns:
            SaveResult: 保存结果
        """
        if image.isNull():
            return SaveResult.error_result("图片为空")
        
        if not folder_path:
            return SaveResult.error_result("文件夹路径为空")
        
        # 确保目录存在
        success, error = self.ensure_folder_exists(folder_path)
        if not success:
            return SaveResult.error_result(error)
        
        # 生成时间戳文件名
        file_path = self.generate_timestamp_filename(folder_path, timestamp)
        
        # 保存图片
        try:
            if image.save(file_path, "PNG"):
                return SaveResult.success_result(file_path)
            else:
                return SaveResult.error_result("保存图片失败")
        except Exception as e:
            return SaveResult.error_result(f"保存图片出错: {str(e)}")

    def save_screenshot_to_file(
        self,
        image: QImage,
        file_path: str
    ) -> SaveResult:
        """保存截图到指定文件路径
        
        Args:
            image: QImage 图片
            file_path: 完整文件路径（包含文件名）
            
        Returns:
            SaveResult: 保存结果
        """
        if image.isNull():
            return SaveResult.error_result("图片为空")
        
        if not file_path:
            return SaveResult.error_result("文件路径为空")
        
        # 确保目录存在
        folder_path = os.path.dirname(file_path)
        if folder_path:
            success, error = self.ensure_folder_exists(folder_path)
            if not success:
                return SaveResult.error_result(error)
        
        # 根据文件扩展名确定保存格式
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        # 确定图片格式
        if ext in ('.jpg', '.jpeg'):
            format_name = "JPEG"
        elif ext == '.png':
            format_name = "PNG"
        elif ext == '.bmp':
            format_name = "BMP"
        else:
            # 默认使用 PNG 格式，并确保文件名有 .png 扩展名
            format_name = "PNG"
            if not ext:
                file_path = file_path + ".png"
        
        # 保存图片
        try:
            if image.save(file_path, format_name):
                return SaveResult.success_result(file_path)
            else:
                return SaveResult.error_result("保存图片失败")
        except Exception as e:
            return SaveResult.error_result(f"保存图片出错: {str(e)}")
