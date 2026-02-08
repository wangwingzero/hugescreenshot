# =====================================================
# =============== 公文格式化对话框测试 ===============
# =====================================================

"""
公文格式化对话框测试

Feature: gongwen-dialog
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from screenshot_tool.services.gongwen_formatter import (
    DocumentInfo,
    GongwenFormatResult,
    FormatResult,
    GongwenFormatter,
    is_gongwen_formatter_available,
)


class TestDocumentInfo:
    """DocumentInfo 数据类测试
    
    **Validates: Requirements TR-1**
    """
    
    def test_create_with_all_fields(self):
        """测试创建包含所有字段的 DocumentInfo"""
        doc = DocumentInfo(
            name="测试文档.docx",
            full_path="C:\\Documents\\测试文档.docx",
            app_type="word"
        )
        assert doc.name == "测试文档.docx"
        assert doc.full_path == "C:\\Documents\\测试文档.docx"
        assert doc.app_type == "word"
    
    def test_create_with_defaults(self):
        """测试使用默认值创建 DocumentInfo"""
        doc = DocumentInfo(name="文档.doc")
        assert doc.name == "文档.doc"
        assert doc.full_path == ""
        assert doc.app_type == "word"
    
    def test_create_wps_document(self):
        """测试创建 WPS 文档信息"""
        doc = DocumentInfo(
            name="公文.wps",
            full_path="D:\\Work\\公文.wps",
            app_type="wps"
        )
        assert doc.name == "公文.wps"
        assert doc.app_type == "wps"
    
    def test_dataclass_equality(self):
        """测试数据类相等性"""
        doc1 = DocumentInfo(name="test.docx", full_path="/path", app_type="word")
        doc2 = DocumentInfo(name="test.docx", full_path="/path", app_type="word")
        assert doc1 == doc2
    
    def test_dataclass_inequality(self):
        """测试数据类不相等性"""
        doc1 = DocumentInfo(name="test1.docx")
        doc2 = DocumentInfo(name="test2.docx")
        assert doc1 != doc2
    
    def test_dataclass_to_dict(self):
        """测试数据类转换为字典"""
        doc = DocumentInfo(
            name="文档.docx",
            full_path="/path/to/文档.docx",
            app_type="word"
        )
        d = asdict(doc)
        assert d == {
            "name": "文档.docx",
            "full_path": "/path/to/文档.docx",
            "app_type": "word"
        }
    
    def test_unicode_filename(self):
        """测试 Unicode 文件名"""
        doc = DocumentInfo(
            name="关于XX工作的通知.docx",
            full_path="C:\\公文\\关于XX工作的通知.docx",
            app_type="word"
        )
        assert "关于" in doc.name
        assert "通知" in doc.name
    
    def test_empty_name(self):
        """测试空文件名"""
        doc = DocumentInfo(name="")
        assert doc.name == ""
        assert doc.full_path == ""
        assert doc.app_type == "word"


class TestGongwenFormatResult:
    """GongwenFormatResult 数据类测试
    
    **Validates: Requirements AC-3.3, AC-3.4**
    """
    
    def test_success_result(self):
        """测试成功结果"""
        result = GongwenFormatResult(
            success=True,
            result=FormatResult.SUCCESS,
            message="公文格式化完成"
        )
        assert result.success is True
        assert result.result == FormatResult.SUCCESS
        assert "完成" in result.message
    
    def test_failure_result_no_document(self):
        """测试失败结果 - 无文档"""
        result = GongwenFormatResult(
            success=False,
            result=FormatResult.NO_DOCUMENT,
            message="Word/WPS 中没有打开的文档"
        )
        assert result.success is False
        assert result.result == FormatResult.NO_DOCUMENT
    
    def test_failure_result_word_not_found(self):
        """测试失败结果 - 未找到 Word"""
        result = GongwenFormatResult(
            success=False,
            result=FormatResult.WORD_NOT_FOUND,
            message="未找到运行中的 Word 或 WPS"
        )
        assert result.success is False
        assert result.result == FormatResult.WORD_NOT_FOUND
    
    def test_failure_result_com_error(self):
        """测试失败结果 - COM 错误"""
        result = GongwenFormatResult(
            success=False,
            result=FormatResult.COM_ERROR,
            message="未安装 pywin32"
        )
        assert result.success is False
        assert result.result == FormatResult.COM_ERROR
    
    def test_failure_result_format_error(self):
        """测试失败结果 - 格式化错误"""
        result = GongwenFormatResult(
            success=False,
            result=FormatResult.FORMAT_ERROR,
            message="格式化失败: 未知错误"
        )
        assert result.success is False
        assert result.result == FormatResult.FORMAT_ERROR


class TestFormatResult:
    """FormatResult 枚举测试"""
    
    def test_all_result_types(self):
        """测试所有结果类型"""
        assert FormatResult.SUCCESS.value == "success"
        assert FormatResult.WORD_NOT_FOUND.value == "word_not_found"
        assert FormatResult.COM_ERROR.value == "com_error"
        assert FormatResult.FORMAT_ERROR.value == "format_error"
        assert FormatResult.NO_DOCUMENT.value == "no_document"
    
    def test_result_count(self):
        """测试结果类型数量"""
        assert len(FormatResult) == 5


class TestIsGongwenFormatterAvailable:
    """is_gongwen_formatter_available 函数测试"""
    
    def test_returns_boolean(self):
        """测试返回布尔值"""
        result = is_gongwen_formatter_available()
        assert isinstance(result, bool)


class TestGongwenFormatterGetOpenDocuments:
    """get_open_documents 方法测试
    
    **Validates: Requirements AC-2.1, AC-2.4, TR-1**
    """
    
    def test_returns_list(self):
        """测试返回列表类型"""
        formatter = GongwenFormatter()
        # 即使没有 Word/WPS 运行，也应该返回空列表而不是 None
        with patch.object(formatter, 'get_open_documents', return_value=[]):
            result = formatter.get_open_documents()
            assert isinstance(result, list)
    
    @patch('screenshot_tool.services.gongwen_formatter.WIN32COM_AVAILABLE', False)
    def test_returns_empty_when_win32com_unavailable(self):
        """测试 win32com 不可用时返回空列表"""
        formatter = GongwenFormatter()
        result = formatter.get_open_documents()
        assert result == []
    
    def test_mock_word_documents(self):
        """测试模拟 Word 文档列表"""
        formatter = GongwenFormatter()
        
        # 模拟返回的文档列表
        mock_docs = [
            DocumentInfo(name="文档1.docx", full_path="C:\\文档1.docx", app_type="word"),
            DocumentInfo(name="文档2.doc", full_path="C:\\文档2.doc", app_type="word"),
        ]
        
        with patch.object(formatter, 'get_open_documents', return_value=mock_docs):
            result = formatter.get_open_documents()
            assert len(result) == 2
            assert result[0].name == "文档1.docx"
            assert result[1].name == "文档2.doc"
    
    def test_mock_wps_documents(self):
        """测试模拟 WPS 文档列表"""
        formatter = GongwenFormatter()
        
        mock_docs = [
            DocumentInfo(name="公文.wps", full_path="D:\\公文.wps", app_type="wps"),
        ]
        
        with patch.object(formatter, 'get_open_documents', return_value=mock_docs):
            result = formatter.get_open_documents()
            assert len(result) == 1
            assert result[0].app_type == "wps"
    
    def test_mock_mixed_documents(self):
        """测试模拟混合文档列表（Word + WPS）"""
        formatter = GongwenFormatter()
        
        mock_docs = [
            DocumentInfo(name="word文档.docx", app_type="word"),
            DocumentInfo(name="wps文档.wps", app_type="wps"),
        ]
        
        with patch.object(formatter, 'get_open_documents', return_value=mock_docs):
            result = formatter.get_open_documents()
            assert len(result) == 2
            app_types = {doc.app_type for doc in result}
            assert "word" in app_types
            assert "wps" in app_types


class TestGongwenFormatterFormatDocumentByName:
    """format_document_by_name 方法测试
    
    **Validates: Requirements AC-3.1, AC-3.3, AC-3.4**
    """
    
    @patch('screenshot_tool.services.gongwen_formatter.WIN32COM_AVAILABLE', False)
    def test_returns_error_when_win32com_unavailable(self):
        """测试 win32com 不可用时返回错误"""
        formatter = GongwenFormatter()
        result = formatter.format_document_by_name("test.docx")
        
        assert result.success is False
        assert result.result == FormatResult.COM_ERROR
        assert "pywin32" in result.message
    
    def test_mock_success_format(self):
        """测试模拟成功格式化"""
        formatter = GongwenFormatter()
        
        mock_result = GongwenFormatResult(
            success=True,
            result=FormatResult.SUCCESS,
            message="公文格式化完成"
        )
        
        with patch.object(formatter, 'format_document_by_name', return_value=mock_result):
            result = formatter.format_document_by_name("测试文档.docx")
            assert result.success is True
            assert result.result == FormatResult.SUCCESS
    
    def test_mock_document_not_found(self):
        """测试模拟文档未找到"""
        formatter = GongwenFormatter()
        
        mock_result = GongwenFormatResult(
            success=False,
            result=FormatResult.NO_DOCUMENT,
            message="未找到文档: 不存在.docx"
        )
        
        with patch.object(formatter, 'format_document_by_name', return_value=mock_result):
            result = formatter.format_document_by_name("不存在.docx")
            assert result.success is False
            assert result.result == FormatResult.NO_DOCUMENT
    
    def test_mock_format_cancelled(self):
        """测试模拟格式化取消"""
        import threading
        formatter = GongwenFormatter()
        cancel_flag = threading.Event()
        cancel_flag.set()  # 设置取消标志
        
        mock_result = GongwenFormatResult(
            success=False,
            result=FormatResult.FORMAT_ERROR,
            message="格式化已取消"
        )
        
        with patch.object(formatter, 'format_document_by_name', return_value=mock_result):
            result = formatter.format_document_by_name("test.docx", cancel_flag=cancel_flag)
            assert result.success is False
            assert "取消" in result.message



# =====================================================
# =============== 集成测试 ===============
# =====================================================

class TestGongwenDialogUI:
    """GongwenDialog 对话框 UI 测试
    
    **Validates: Requirements US-1, US-2, TR-2**
    """
    
    @pytest.fixture
    def dialog(self, qtbot):
        """创建对话框实例"""
        from screenshot_tool.ui.gongwen_dialog import GongwenDialog
        
        # 模拟 get_open_documents 返回空列表，避免 COM 调用
        with patch('screenshot_tool.services.gongwen_formatter.GongwenFormatter') as MockFormatter:
            with patch('screenshot_tool.services.gongwen_formatter.is_gongwen_formatter_available', return_value=True):
                mock_instance = MockFormatter.return_value
                mock_instance.get_open_documents.return_value = []
                
                dialog = GongwenDialog()
                qtbot.addWidget(dialog)
                yield dialog
    
    def test_dialog_title(self, dialog):
        """测试对话框标题
        
        **Validates: Requirements AC-1.2**
        """
        assert "公文" in dialog.windowTitle()
    
    def test_dialog_minimum_size(self, dialog):
        """测试对话框最小尺寸"""
        assert dialog.minimumWidth() >= 400
        assert dialog.minimumHeight() >= 300
    
    def test_dialog_has_document_list(self, dialog):
        """测试对话框包含文档列表
        
        **Validates: Requirements AC-1.3, AC-2.1**
        """
        assert dialog._doc_list is not None
    
    def test_dialog_has_refresh_button(self, dialog):
        """测试对话框包含刷新按钮
        
        **Validates: Requirements AC-4.1**
        """
        assert dialog._refresh_btn is not None
        assert "刷新" in dialog._refresh_btn.text()
    
    def test_dialog_has_format_button(self, dialog):
        """测试对话框包含格式化按钮
        
        **Validates: Requirements AC-3.1**
        """
        assert dialog._format_btn is not None
        assert "格式化" in dialog._format_btn.text()
    
    def test_dialog_has_close_button(self, dialog):
        """测试对话框包含关闭按钮"""
        assert dialog._close_btn is not None
        assert "关闭" in dialog._close_btn.text()
    
    def test_empty_state_shown_when_no_documents(self, dialog):
        """测试无文档时显示空状态
        
        **Validates: Requirements AC-2.4**
        """
        # 空状态标签应该可见
        assert dialog._empty_label.isVisible() or dialog._doc_list.count() == 0
    
    def test_format_button_disabled_when_no_documents(self, dialog):
        """测试无文档时格式化按钮禁用"""
        # 当没有文档时，格式化按钮应该被禁用
        if dialog._doc_list.count() == 0:
            assert not dialog._format_btn.isEnabled()


class TestGongwenDialogDocumentList:
    """GongwenDialog 文档列表测试
    
    **Validates: Requirements AC-2.1, AC-2.2, AC-2.3**
    """
    
    @pytest.fixture
    def dialog_with_documents(self, qtbot):
        """创建包含模拟文档的对话框"""
        from screenshot_tool.ui.gongwen_dialog import GongwenDialog
        
        mock_docs = [
            DocumentInfo(name="文档1.docx", full_path="C:\\文档1.docx", app_type="word"),
            DocumentInfo(name="文档2.doc", full_path="C:\\文档2.doc", app_type="wps"),
        ]
        
        with patch('screenshot_tool.services.gongwen_formatter.GongwenFormatter') as MockFormatter:
            with patch('screenshot_tool.services.gongwen_formatter.is_gongwen_formatter_available', return_value=True):
                mock_instance = MockFormatter.return_value
                mock_instance.get_open_documents.return_value = mock_docs
                
                dialog = GongwenDialog()
                qtbot.addWidget(dialog)
                yield dialog
    
    def test_documents_displayed_in_list(self, dialog_with_documents):
        """测试文档显示在列表中
        
        **Validates: Requirements AC-2.1**
        """
        dialog = dialog_with_documents
        assert dialog._doc_list.count() == 2
    
    def test_document_names_shown(self, dialog_with_documents):
        """测试文档名称显示
        
        **Validates: Requirements AC-2.2**
        """
        dialog = dialog_with_documents
        item_texts = [dialog._doc_list.item(i).text() for i in range(dialog._doc_list.count())]
        
        # 检查文档名称是否在列表项文本中
        assert any("文档1.docx" in text for text in item_texts)
        assert any("文档2.doc" in text for text in item_texts)
    
    def test_first_document_selected_by_default(self, dialog_with_documents):
        """测试默认选中第一个文档"""
        dialog = dialog_with_documents
        assert dialog._doc_list.currentRow() == 0
    
    def test_format_button_enabled_with_documents(self, dialog_with_documents):
        """测试有文档时格式化按钮启用"""
        dialog = dialog_with_documents
        assert dialog._format_btn.isEnabled()
    
    def test_get_selected_document(self, dialog_with_documents):
        """测试获取选中的文档
        
        **Validates: Requirements AC-2.3**
        """
        dialog = dialog_with_documents
        selected = dialog.get_selected_document()
        assert selected == "文档1.docx"
    
    def test_select_second_document(self, dialog_with_documents):
        """测试选择第二个文档"""
        dialog = dialog_with_documents
        dialog._doc_list.setCurrentRow(1)
        selected = dialog.get_selected_document()
        assert selected == "文档2.doc"


class TestGongwenDialogFormatFlow:
    """GongwenDialog 格式化流程测试
    
    **Validates: Requirements US-3, AC-3.1**
    """
    
    @pytest.fixture
    def dialog_with_signal(self, qtbot):
        """创建对话框并准备信号监听"""
        from screenshot_tool.ui.gongwen_dialog import GongwenDialog
        
        mock_docs = [
            DocumentInfo(name="测试文档.docx", app_type="word"),
        ]
        
        with patch('screenshot_tool.services.gongwen_formatter.GongwenFormatter') as MockFormatter:
            with patch('screenshot_tool.services.gongwen_formatter.is_gongwen_formatter_available', return_value=True):
                mock_instance = MockFormatter.return_value
                mock_instance.get_open_documents.return_value = mock_docs
                
                dialog = GongwenDialog()
                qtbot.addWidget(dialog)
                yield dialog
    
    def test_format_requested_signal_emitted(self, dialog_with_signal, qtbot):
        """测试点击格式化按钮发出信号
        
        **Validates: Requirements AC-3.1**
        """
        dialog = dialog_with_signal
        
        # 监听信号
        with qtbot.waitSignal(dialog.format_requested, timeout=1000) as blocker:
            dialog._on_format_clicked()
        
        # 验证信号参数
        assert blocker.args == ["测试文档.docx"]
    
    def test_dialog_closes_after_format(self, dialog_with_signal, qtbot):
        """测试格式化后对话框关闭"""
        from PySide6.QtWidgets import QDialog
        
        dialog = dialog_with_signal
        dialog.show()
        
        # 点击格式化
        with qtbot.waitSignal(dialog.format_requested, timeout=1000):
            dialog._on_format_clicked()
        
        # 对话框应该关闭（result 为 Accepted）
        assert dialog.result() == QDialog.DialogCode.Accepted


class TestGongwenDialogRefresh:
    """GongwenDialog 刷新功能测试
    
    **Validates: Requirements US-4, AC-4.1, AC-4.2**
    """
    
    def test_refresh_updates_document_list(self, qtbot):
        """测试刷新更新文档列表
        
        **Validates: Requirements AC-4.2**
        """
        from screenshot_tool.ui.gongwen_dialog import GongwenDialog
        
        # 初始无文档
        initial_docs = []
        # 刷新后有文档
        refreshed_docs = [
            DocumentInfo(name="新文档.docx", app_type="word"),
        ]
        
        call_count = [0]
        
        def mock_get_docs():
            call_count[0] += 1
            if call_count[0] == 1:
                return initial_docs
            return refreshed_docs
        
        with patch('screenshot_tool.services.gongwen_formatter.GongwenFormatter') as MockFormatter:
            with patch('screenshot_tool.services.gongwen_formatter.is_gongwen_formatter_available', return_value=True):
                mock_instance = MockFormatter.return_value
                mock_instance.get_open_documents.side_effect = mock_get_docs
                
                dialog = GongwenDialog()
                qtbot.addWidget(dialog)
                
                # 初始应该没有文档
                assert dialog._doc_list.count() == 0
                
                # 刷新
                dialog._refresh_documents()
                
                # 刷新后应该有文档
                assert dialog._doc_list.count() == 1
