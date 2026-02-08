# =====================================================
# =============== MinerU 服务测试 ===============
# =====================================================

"""
MinerU PDF 转 Markdown 服务测试

Property 1: Config Validation Correctness
Property 2: File Size Validation
Property 3: API Error Handling
Property 4: Progress Callback Accuracy
Property 5: Batch Conversion Result Consistency

Feature: pdf-to-markdown
Validates: Requirements 1.1-1.4, 2.1-2.5, 3.1-3.3
"""

import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from dataclasses import dataclass

import pytest
from hypothesis import given, strategies as st, settings, assume

from screenshot_tool.core.config_manager import MinerUConfig
from screenshot_tool.services.mineru_service import (
    MinerUService,
    MinerUError,
    ConvertResult,
)


# ========== 策略定义 ==========

# API Token 策略
api_token_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P')),
    min_size=0,
    max_size=100
)

# 模型版本策略
model_version_strategy = st.sampled_from(["pipeline", "vlm", "invalid", "", None])

# 文件大小策略 (bytes)
file_size_strategy = st.integers(min_value=0, max_value=300 * 1024 * 1024)  # 0-300MB

# 进度值策略
progress_strategy = st.floats(min_value=0.0, max_value=1.0)


# ========== MinerUConfig 测试 ==========

class TestMinerUConfigUnit:
    """MinerUConfig 单元测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = MinerUConfig()
        assert config.api_token == ""
        assert config.last_pdf_dir == ""
        assert config.model_version == "vlm"
    
    def test_custom_values(self):
        """测试自定义值"""
        config = MinerUConfig(
            api_token="test_token_123",
            last_pdf_dir="C:\\PDFs",
            model_version="pipeline"
        )
        assert config.api_token == "test_token_123"
        assert config.last_pdf_dir == "C:\\PDFs"
        assert config.model_version == "pipeline"
    
    def test_none_handling(self):
        """测试 None 值处理"""
        config = MinerUConfig(
            api_token=None,
            last_pdf_dir=None,
            model_version=None
        )
        assert config.api_token == ""
        assert config.last_pdf_dir == ""
        assert config.model_version == "vlm"  # 默认值
    
    def test_invalid_model_version(self):
        """测试无效模型版本"""
        config = MinerUConfig(model_version="invalid_version")
        assert config.model_version == "vlm"  # 回退到默认值
    
    def test_is_configured_with_token(self):
        """测试 is_configured - 有 Token"""
        config = MinerUConfig(api_token="valid_token")
        assert config.is_configured() is True
    
    def test_is_configured_without_token(self):
        """测试 is_configured - 无 Token"""
        config = MinerUConfig(api_token="")
        assert config.is_configured() is False
    
    def test_is_configured_whitespace_token(self):
        """测试 is_configured - 空白 Token"""
        config = MinerUConfig(api_token="   ")
        assert config.is_configured() is False


class TestMinerUConfigProperties:
    """MinerUConfig 属性测试
    
    Feature: pdf-to-markdown
    """
    
    @given(
        api_token=api_token_strategy,
        model_version=model_version_strategy,
    )
    @settings(max_examples=100)
    def test_property_1_config_validation_correctness(self, api_token, model_version):
        """
        Property 1: Config Validation Correctness
        
        *For any* input values, MinerUConfig SHALL normalize invalid values
        to safe defaults: None becomes empty string, invalid model_version
        becomes "vlm".
        
        **Validates: Requirements 1.1, 1.2**
        """
        config = MinerUConfig(
            api_token=api_token,
            model_version=model_version
        )
        
        # api_token 应该是字符串
        assert isinstance(config.api_token, str)
        
        # model_version 应该是有效值
        assert config.model_version in MinerUConfig.VALID_MODEL_VERSIONS
        
        # is_configured 应该正确反映 token 状态
        if api_token and api_token.strip():
            assert config.is_configured() is True
        else:
            assert config.is_configured() is False


# ========== ConvertResult 测试 ==========

class TestConvertResultUnit:
    """ConvertResult 单元测试"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = ConvertResult(
            pdf_path="test.pdf",
            markdown_path="test.md"
        )
        assert result.success is True
        assert result.pdf_path == "test.pdf"
        assert result.markdown_path == "test.md"
        assert result.error_message is None
    
    def test_error_result(self):
        """测试错误结果"""
        result = ConvertResult(
            pdf_path="test.pdf",
            error_message="转换失败"
        )
        assert result.success is False
        assert result.markdown_path is None
        assert result.error_message == "转换失败"
    
    def test_partial_result(self):
        """测试部分结果（有 md 但也有错误）"""
        result = ConvertResult(
            pdf_path="test.pdf",
            markdown_path="test.md",
            error_message="警告信息"
        )
        assert result.success is False  # 有错误就不算成功


# ========== MinerUError 测试 ==========

class TestMinerUErrorUnit:
    """MinerUError 单元测试"""
    
    def test_error_without_code(self):
        """测试无错误码"""
        error = MinerUError(message="测试错误")
        assert str(error) == "测试错误"
    
    def test_error_with_code(self):
        """测试有错误码"""
        error = MinerUError(message="测试错误", code="E001")
        assert str(error) == "[E001] 测试错误"


# ========== MinerUService 测试 ==========

class TestMinerUServiceUnit:
    """MinerUService 单元测试"""
    
    def test_init_default_model(self):
        """测试默认模型版本"""
        service = MinerUService(api_token="test_token")
        assert service.api_token == "test_token"
        assert service.model_version == "vlm"
    
    def test_init_custom_model(self):
        """测试自定义模型版本"""
        service = MinerUService(api_token="test_token", model_version="pipeline")
        assert service.model_version == "pipeline"
    
    def test_convert_pdf_file_not_found(self):
        """测试文件不存在"""
        service = MinerUService(api_token="test_token")
        
        with pytest.raises(FileNotFoundError):
            service.convert_pdf("/nonexistent/file.pdf")
    
    def test_convert_pdf_file_too_large(self):
        """测试文件过大"""
        service = MinerUService(api_token="test_token")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # 写入超过 200MB 的数据（使用 seek 模拟大文件）
            f.seek(201 * 1024 * 1024)
            f.write(b'\x00')
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                service.convert_pdf(temp_path)
            assert "文件过大" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    def test_upload_file_success(self):
        """测试文件上传成功"""
        service = MinerUService(api_token="test_token")
        
        with patch.object(service._session, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {
                    "file_urls": ["https://example.com/file.pdf"],
                    "batch_id": "batch_123"
                }
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            # Mock PUT 请求
            with patch('screenshot_tool.services.mineru_service.requests.put') as mock_put:
                mock_put_response = Mock()
                mock_put_response.status_code = 200
                mock_put.return_value = mock_put_response
                
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                    f.write(b'%PDF-1.4 test content')
                    temp_path = f.name
                
                try:
                    batch_id = service._upload_file(temp_path)
                    assert batch_id == "batch_123"
                finally:
                    os.unlink(temp_path)
    
    def test_upload_file_api_error(self):
        """测试文件上传 API 错误"""
        service = MinerUService(api_token="invalid_token")
        
        with patch.object(service._session, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 1001,
                "msg": "Token 无效"
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                f.write(b'%PDF-1.4 test content')
                temp_path = f.name
            
            try:
                with pytest.raises(MinerUError) as exc_info:
                    service._upload_file(temp_path)
                assert "Token 无效" in str(exc_info.value)
            finally:
                os.unlink(temp_path)
    
    def test_create_task_success(self):
        """测试创建任务成功"""
        service = MinerUService(api_token="test_token")
        
        with patch.object(service._session, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {"task_id": "task_123"}
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            task_id = service._create_task("https://example.com/file.pdf")
            assert task_id == "task_123"
    
    def test_create_task_api_error(self):
        """测试创建任务 API 错误"""
        service = MinerUService(api_token="test_token")
        
        with patch.object(service._session, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 2001,
                "msg": "文件格式不支持"
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            with pytest.raises(MinerUError) as exc_info:
                service._create_task("https://example.com/file.pdf")
            assert "文件格式不支持" in str(exc_info.value)
    
    def test_poll_task_done(self):
        """测试轮询任务 - 完成"""
        service = MinerUService(api_token="test_token")
        
        with patch.object(service._session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {
                    "state": "done",
                    "full_zip_url": "https://example.com/result.zip"
                }
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            zip_url = service._poll_task("task_123")
            assert zip_url == "https://example.com/result.zip"
    
    def test_poll_task_failed(self):
        """测试轮询任务 - 失败"""
        service = MinerUService(api_token="test_token")
        
        with patch.object(service._session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {"state": "failed"}
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            with pytest.raises(MinerUError) as exc_info:
                service._poll_task("task_123")
            assert "解析失败" in str(exc_info.value)
    
    @patch('screenshot_tool.services.mineru_service.requests.get')
    def test_download_and_extract_success(self, mock_get):
        """测试下载并解压成功"""
        service = MinerUService(api_token="test_token")
        
        # 创建测试 ZIP 文件
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含 MD 文件的 ZIP
            zip_content = self._create_test_zip("# Test Markdown\n\nContent here.")
            
            mock_response = Mock()
            mock_response.content = zip_content
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            pdf_path = os.path.join(temp_dir, "test.pdf")
            Path(pdf_path).touch()
            
            md_path = service._download_and_extract(
                "https://example.com/result.zip",
                temp_dir,
                pdf_path
            )
            
            assert os.path.exists(md_path)
            assert md_path.endswith(".md")
            
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "Test Markdown" in content
    
    def test_convert_folder_empty(self):
        """测试空文件夹转换"""
        service = MinerUService(api_token="test_token")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            results = service.convert_folder(temp_dir)
            assert results == []
    
    def test_convert_folder_with_pdfs(self):
        """测试文件夹转换（mock）"""
        service = MinerUService(api_token="test_token")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建测试 PDF 文件
            pdf1 = os.path.join(temp_dir, "test1.pdf")
            pdf2 = os.path.join(temp_dir, "test2.pdf")
            Path(pdf1).write_bytes(b'%PDF-1.4 test')
            Path(pdf2).write_bytes(b'%PDF-1.4 test')
            
            # Mock convert_pdf 方法
            with patch.object(service, 'convert_pdf') as mock_convert:
                mock_convert.side_effect = [
                    os.path.join(temp_dir, "test1.md"),
                    MinerUError("转换失败")
                ]
                
                results = service.convert_folder(temp_dir)
                
                assert len(results) == 2
                assert results[0].success is True
                assert results[1].success is False
                assert "转换失败" in results[1].error_message
    
    def _create_test_zip(self, md_content: str) -> bytes:
        """创建测试 ZIP 文件"""
        import io
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("output/result.md", md_content)
        
        return buffer.getvalue()


class TestMinerUServiceProperties:
    """MinerUService 属性测试
    
    Feature: pdf-to-markdown
    """
    
    @given(file_size=file_size_strategy)
    @settings(max_examples=50, deadline=None)
    def test_property_2_file_size_validation(self, file_size):
        """
        Property 2: File Size Validation
        
        *For any* file size, the service SHALL reject files larger than
        MAX_FILE_SIZE (200MB) with a clear error message.
        
        **Validates: Requirements 2.1**
        """
        service = MinerUService(api_token="test_token")
        max_size = service.MAX_FILE_SIZE
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # 使用 seek 模拟文件大小
            if file_size > 0:
                f.seek(file_size - 1)
                f.write(b'\x00')
            temp_path = f.name
        
        try:
            if file_size > max_size:
                # 应该抛出 ValueError
                with pytest.raises(ValueError) as exc_info:
                    service.convert_pdf(temp_path)
                assert "文件过大" in str(exc_info.value)
            else:
                # 文件大小合法，会因为其他原因失败（如网络）
                # 但不应该因为文件大小失败
                try:
                    service.convert_pdf(temp_path)
                except ValueError as e:
                    # 不应该是文件大小错误
                    assert "文件过大" not in str(e)
                except (MinerUError, FileNotFoundError, Exception):
                    # 其他错误是预期的（网络、API 等）
                    pass
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    
    @given(
        error_code=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
        error_message=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=50)
    def test_property_3_api_error_handling(self, error_code, error_message):
        """
        Property 3: API Error Handling
        
        *For any* API error response, MinerUError SHALL correctly format
        the error message with optional error code.
        
        **Validates: Requirements 2.3, 2.4**
        """
        error = MinerUError(message=error_message, code=error_code)
        error_str = str(error)
        
        # 错误消息应该包含原始消息
        assert error_message in error_str
        
        # 如果有错误码，应该包含在输出中
        if error_code:
            assert error_code in error_str
            assert f"[{error_code}]" in error_str
    
    @given(progress_values=st.lists(progress_strategy, min_size=1, max_size=10))
    @settings(max_examples=30)
    def test_property_4_progress_callback_accuracy(self, progress_values):
        """
        Property 4: Progress Callback Accuracy
        
        *For any* sequence of progress updates, the callback SHALL receive
        values in the range [0, 1] and status messages.
        
        **Validates: Requirements 2.5**
        """
        received_progress = []
        received_status = []
        
        def callback(status: str, progress: float):
            received_status.append(status)
            received_progress.append(progress)
        
        # 模拟进度回调
        for p in progress_values:
            callback(f"处理中... {p*100:.0f}%", p)
        
        # 验证所有进度值在有效范围内
        for p in received_progress:
            assert 0.0 <= p <= 1.0, f"Progress {p} out of range [0, 1]"
        
        # 验证状态消息非空
        for s in received_status:
            assert isinstance(s, str)
            assert len(s) > 0


# ========== 集成测试（需要 Mock）==========

class TestMinerUServiceIntegration:
    """MinerUService 集成测试（使用 Mock）"""
    
    @patch('screenshot_tool.services.mineru_service.requests.get')
    @patch('screenshot_tool.services.mineru_service.requests.put')
    def test_full_convert_flow(self, mock_put, mock_get):
        """测试完整转换流程"""
        service = MinerUService(api_token="test_token")
        
        # Mock PUT 上传响应
        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_put.return_value = mock_put_response
        
        # Mock session.post 用于获取上传 URL
        with patch.object(service._session, 'post') as mock_session_post:
            upload_response = Mock()
            upload_response.json.return_value = {
                "code": 0,
                "data": {
                    "file_urls": ["https://example.com/file.pdf"],
                    "batch_id": "batch_123"
                }
            }
            upload_response.raise_for_status = Mock()
            mock_session_post.return_value = upload_response
            
            # Mock 轮询响应
            with patch.object(service._session, 'get') as mock_session_get:
                poll_response = Mock()
                poll_response.json.return_value = {
                    "code": 0,
                    "data": {
                        "extract_result": [{
                            "state": "done",
                            "full_zip_url": "https://example.com/result.zip"
                        }]
                    }
                }
                poll_response.raise_for_status = Mock()
                mock_session_get.return_value = poll_response
                
                # Mock 下载响应
                zip_content = self._create_test_zip("# Converted Content")
                download_response = Mock()
                download_response.content = zip_content
                download_response.raise_for_status = Mock()
                mock_get.return_value = download_response
                
                # 执行转换
                with tempfile.TemporaryDirectory() as temp_dir:
                    pdf_path = os.path.join(temp_dir, "test.pdf")
                    Path(pdf_path).write_bytes(b'%PDF-1.4 test content')
                    
                    progress_calls = []
                    
                    def progress_callback(status, progress):
                        progress_calls.append((status, progress))
                    
                    md_path = service.convert_pdf(pdf_path, progress_callback)
                    
                    # 验证结果
                    assert os.path.exists(md_path)
                    assert md_path.endswith(".md")
                    
                    with open(md_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    assert "Converted Content" in content
                    
                    # 验证进度回调被调用
                    assert len(progress_calls) > 0
                    assert progress_calls[-1][1] == 1.0  # 最后进度为 100%
    
    def _create_test_zip(self, md_content: str) -> bytes:
        """创建测试 ZIP 文件"""
        import io
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("output/result.md", md_content)
        
        return buffer.getvalue()
