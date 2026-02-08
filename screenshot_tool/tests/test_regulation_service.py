#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAAC 规章查询服务测试

Feature: caac-regulation-search
Feature: caac-regulation-download-enhancement
"""

import os
import tempfile
from datetime import timedelta, date
from hypothesis import given, strategies as st, settings, HealthCheck

from screenshot_tool.services.regulation_service import (
    RegulationDocument,
    RegulationService,
    generate_filename,
    get_save_path,
)
from screenshot_tool.ui.regulation_search_window import (
    calculate_date_preset,
    filter_documents_by_date,
)


# ============================================================
# Hypothesis Strategies
# ============================================================

@st.composite
def document_strategy(draw):
    """生成随机的 RegulationDocument"""
    validity = draw(st.sampled_from(["有效", "失效", "废止"]))
    doc_type = draw(st.sampled_from(["regulation", "normative"]))
    
    # 生成合理的文号
    if doc_type == "regulation":
        doc_number = draw(st.sampled_from([
            "CCAR-121-R8", "CCAR-91-R4", "CCAR-61-R5", 
            "CCAR-135R3", "CCAR-145R4", ""
        ]))
    else:
        doc_number = draw(st.sampled_from([
            "AC-121-FS-139", "IB-FS-OPS-017", "AP-137-CA-2025-01",
            "MD-121-FS-101", ""
        ]))
    
    title = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
        min_size=1,
        max_size=50
    ))
    
    # 生成日期
    publish_date = draw(st.sampled_from([
        "2024-01-15", "2023-06-20", "2022-03-10", "2021-12-01", ""
    ]))
    
    return RegulationDocument(
        title=title,
        url=f"http://example.com/{draw(st.integers(min_value=1, max_value=99999))}",
        validity=validity,
        doc_number=doc_number,
        office_unit=draw(st.sampled_from(["政策法规司", "飞行标准司", "机场司", ""])),
        doc_type=doc_type,
        sign_date="",
        publish_date=publish_date,
        file_number="",
    )


# ============================================================
# Property Tests
# ============================================================

class TestFilenameGeneration:
    """文件名生成属性测试
    
    Feature: caac-regulation-download-enhancement
    Property 3: Normative Document Filename Generation
    Property 4: CCAR Regulation Filename Generation
    Validates: Requirements 4.1-4.5, 5.1-5.5
    """
    
    @given(document=document_strategy())
    @settings(max_examples=100)
    def test_filename_follows_convention(self, document: RegulationDocument):
        """Property 3 & 4: 文件名生成遵循命名规范
        
        对于任意文档，生成的文件名应符合以下规则：
        - 有效文档不加前缀
        - 失效/废止文档统一加 "失效!" 前缀
        - 文件名以 .pdf 结尾
        - 文件名不包含非法字符
        
        Feature: caac-regulation-download-enhancement
        Property 3: Normative Document Filename Generation
        Property 4: CCAR Regulation Filename Generation
        Validates: Requirements 4.1-4.5, 5.1-5.5
        """
        filename = generate_filename(document)
        
        # 文件名应以 .pdf 结尾
        assert filename.endswith(".pdf"), f"文件名应以 .pdf 结尾: {filename}"
        
        # 检查有效性前缀
        if document.validity == "有效":
            # 有效文档不应有有效性前缀
            assert not filename.startswith("失效!"), f"有效文档不应有前缀: {filename}"
        elif document.validity in ("失效", "废止"):
            # 失效和废止文档统一使用 "失效!" 前缀
            assert filename.startswith("失效!"), f"失效/废止文档应有 '失效!' 前缀: {filename}"
        
        # 文件名不应包含非法字符
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            assert char not in filename, f"文件名包含非法字符 '{char}': {filename}"
        
        # 文件名长度限制
        assert len(filename) <= 204, f"文件名过长: {len(filename)}"
    
    def test_valid_document_no_prefix(self):
        """有效文档不加前缀"""
        doc = RegulationDocument(
            title="一般运行和飞行规则",
            url="http://example.com/1",
            validity="有效",
            doc_number="CCAR-91-R4",
            office_unit="政策法规司",
            doc_type="regulation",
        )
        filename = generate_filename(doc)
        assert filename == "CCAR-91-R4一般运行和飞行规则.pdf"
    
    def test_invalid_document_has_prefix(self):
        """失效文档加 '失效!' 前缀"""
        doc = RegulationDocument(
            title="民用航空器国籍登记规定",
            url="http://example.com/2",
            validity="失效",
            doc_number="CCAR-45-R2",
            office_unit="政策法规司",
            doc_type="regulation",
        )
        filename = generate_filename(doc)
        assert filename == "失效!CCAR-45-R2民用航空器国籍登记规定.pdf"
    
    def test_abolished_document_has_prefix(self):
        """废止文档统一使用 '失效!' 前缀"""
        doc = RegulationDocument(
            title="大型飞机公共航空运输承运人运行合格审定规则",
            url="http://example.com/3",
            validity="废止",
            doc_number="CCAR-121-R7",
            office_unit="政策法规司",
            doc_type="regulation",
        )
        filename = generate_filename(doc)
        # 废止文档统一使用 "失效!" 前缀
        assert filename == "失效!CCAR-121-R7大型飞机公共航空运输承运人运行合格审定规则.pdf"
    
    def test_normative_valid_filename(self):
        """规范性文件（有效）命名规则
        
        Feature: caac-regulation-download-enhancement
        Property 3: Normative Document Filename Generation
        Validates: Requirements 4.1
        """
        doc = RegulationDocument(
            title="运营人航空器适航检查单",
            url="http://example.com/5",
            validity="有效",
            doc_number="AC-21-AA-2008-15",
            office_unit="飞行标准司",
            doc_type="normative",
        )
        filename = generate_filename(doc)
        assert filename == "AC-21-AA-2008-15运营人航空器适航检查单.pdf"
    
    def test_normative_invalid_filename(self):
        """规范性文件（失效）命名规则
        
        Feature: caac-regulation-download-enhancement
        Property 3: Normative Document Filename Generation
        Validates: Requirements 4.2
        """
        doc = RegulationDocument(
            title="适航培训课程目录",
            url="http://example.com/6",
            validity="失效",
            doc_number="AC-00-AA-2009-02R1",
            office_unit="飞行标准司",
            doc_type="normative",
        )
        filename = generate_filename(doc)
        assert filename == "失效!AC-00-AA-2009-02R1适航培训课程目录.pdf"
    
    def test_special_characters_replaced(self):
        """特殊字符被替换"""
        doc = RegulationDocument(
            title="测试<>:\"/\\|?*文档",
            url="http://example.com/4",
            validity="有效",
            doc_number="TEST-1",
            office_unit="测试司",
            doc_type="regulation",
        )
        filename = generate_filename(doc)
        assert '<' not in filename
        assert '>' not in filename
        assert ':' not in filename
        assert '"' not in filename
        assert '/' not in filename
        assert '\\' not in filename
        assert '|' not in filename
        assert '?' not in filename
        assert '*' not in filename


class TestSavePathGeneration:
    """保存路径生成测试
    
    Feature: caac-regulation-search
    Validates: Requirements 6.1, 6.3, 6.4
    
    注意：当前实现不创建子目录，直接保存到 base_path
    """
    
    def test_save_path_in_base_directory(self):
        """文件直接保存到 base_path 目录"""
        doc = RegulationDocument(
            title="测试规章",
            url="http://example.com/1",
            validity="有效",
            doc_number="CCAR-1",
            office_unit="测试司",
            doc_type="regulation",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = get_save_path(doc, temp_dir)
            # 文件应直接在 base_path 目录下
            assert os.path.dirname(save_path) == temp_dir
            assert save_path.endswith(".pdf")
    
    def test_directory_created(self):
        """目录应该被创建"""
        doc = RegulationDocument(
            title="测试",
            url="http://example.com/1",
            validity="有效",
            doc_number="TEST-1",
            office_unit="测试司",
            doc_type="regulation",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = get_save_path(doc, temp_dir)
            dir_path = os.path.dirname(save_path)
            assert os.path.exists(dir_path), f"目录应该被创建: {dir_path}"
    
    def test_default_base_path(self):
        """默认保存路径为 ~/Documents/CAAC_PDF/"""
        doc = RegulationDocument(
            title="测试",
            url="http://example.com/1",
            validity="有效",
            doc_number="TEST-1",
            office_unit="测试司",
            doc_type="regulation",
        )
        save_path = get_save_path(doc)
        expected_base = os.path.join(os.path.expanduser("~"), "Documents", "CAAC_PDF")
        assert expected_base in save_path


# ============================================================
# Service Tests
# ============================================================

class TestRegulationService:
    """RegulationService 测试
    
    Feature: caac-regulation-search
    """
    
    def test_service_initialization(self):
        """服务初始化"""
        service = RegulationService()
        assert service is not None
        assert service.save_path != ""
    
    def test_save_path_property(self):
        """保存路径属性"""
        service = RegulationService()
        
        # 设置自定义路径
        custom_path = "/custom/path"
        service.save_path = custom_path
        assert service.save_path == custom_path
    
    def test_search_method_exists(self):
        """搜索方法存在"""
        service = RegulationService()
        
        # 验证 search 方法存在
        assert hasattr(service, 'search')
        assert callable(service.search)
        
        # 验证信号存在
        assert hasattr(service, 'searchFinished')
        assert hasattr(service, 'searchError')


# ============================================================
# UI Tests (requires pytest-qt)
# ============================================================

class TestRegulationSearchWindowUI:
    """规章查询窗口 UI 测试
    
    Feature: caac-regulation-search
    Property 1: Singleton Window Behavior
    Validates: Requirements 1.3, 2.7, 3.1
    """
    
    def test_singleton_window_behavior(self, qtbot):
        """Property 1: 单例窗口行为
        
        多次调用 show_and_activate 应返回同一个窗口实例
        """
        from screenshot_tool.ui.regulation_search_window import RegulationSearchWindow
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 清除可能存在的实例
        RegulationSearchWindow._instance = None
        
        config = ConfigManager()
        
        # 第一次调用
        window1 = RegulationSearchWindow.show_and_activate(config)
        qtbot.addWidget(window1)
        
        # 第二次调用应返回同一实例
        window2 = RegulationSearchWindow.show_and_activate(config)
        
        assert window1 is window2, "多次调用应返回同一窗口实例"
        
        # 清理
        window1.close()
        RegulationSearchWindow._instance = None
    
    def test_window_has_search_input(self, qtbot):
        """窗口应有搜索输入框"""
        from screenshot_tool.ui.regulation_search_window import RegulationSearchWindow
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 清除可能存在的实例
        RegulationSearchWindow._instance = None
        
        config = ConfigManager()
        window = RegulationSearchWindow(config)
        qtbot.addWidget(window)
        
        # 验证搜索输入框存在
        assert hasattr(window, '_search_input')
        assert window._search_input is not None
        
        # 清理
        window.close()
        RegulationSearchWindow._instance = None
    
    def test_debounce_timer_setup(self, qtbot):
        """验证防抖定时器已正确配置"""
        from screenshot_tool.ui.regulation_search_window import RegulationSearchWindow
        from screenshot_tool.core.config_manager import ConfigManager
        
        # 清除可能存在的实例
        RegulationSearchWindow._instance = None
        
        config = ConfigManager()
        window = RegulationSearchWindow(config)
        qtbot.addWidget(window)
        
        # 验证定时器配置
        assert hasattr(window, '_debounce_timer')
        assert window._debounce_timer.isSingleShot(), "定时器应为单次触发"
        
        # 清理
        window.close()
        RegulationSearchWindow._instance = None


# ============================================================
# Date Filtering Tests
# ============================================================

class TestDatePresetCalculation:
    """日期预设计算属性测试
    
    Feature: caac-regulation-download-enhancement
    Property 1: Date Preset Calculation
    Validates: Requirements 1.4
    """
    
    @given(preset=st.sampled_from(["1day", "7days", "30days"]))
    @settings(max_examples=100)
    def test_date_preset_calculation(self, preset: str):
        """Property 1: 日期预设计算
        
        对于任意日期预设选择，计算的日期范围应满足：
        - start_date = today - N days
        - end_date = today
        
        Feature: caac-regulation-download-enhancement
        Property 1: Date Preset Calculation
        Validates: Requirements 1.4
        """
        start_date, end_date = calculate_date_preset(preset)
        
        today = date.today()
        expected_end = today.strftime("%Y-%m-%d")
        
        days_map = {"1day": 1, "7days": 7, "30days": 30}
        expected_start = (today - timedelta(days=days_map[preset])).strftime("%Y-%m-%d")
        
        assert end_date == expected_end, f"结束日期应为今天: {end_date} != {expected_end}"
        assert start_date == expected_start, f"起始日期计算错误: {start_date} != {expected_start}"
    
    def test_all_preset_returns_empty(self):
        """全部时间预设返回空日期范围"""
        start, end = calculate_date_preset("all")
        assert start == ""
        assert end == ""
    
    def test_1day_preset(self):
        """近1天预设"""
        start, end = calculate_date_preset("1day")
        today = date.today()
        expected_start = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        expected_end = today.strftime("%Y-%m-%d")
        assert start == expected_start
        assert end == expected_end
    
    def test_7days_preset(self):
        """近7天预设"""
        start, end = calculate_date_preset("7days")
        today = date.today()
        expected_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        expected_end = today.strftime("%Y-%m-%d")
        assert start == expected_start
        assert end == expected_end
    
    def test_30days_preset(self):
        """近30天预设"""
        start, end = calculate_date_preset("30days")
        today = date.today()
        expected_start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        expected_end = today.strftime("%Y-%m-%d")
        assert start == expected_start
        assert end == expected_end


class TestDateRangeFiltering:
    """日期范围筛选属性测试
    
    Feature: caac-regulation-download-enhancement
    Property 2: Date Range Filtering
    Validates: Requirements 1.5, 1.6, 1.7
    """
    
    @given(
        days_offset=st.integers(min_value=0, max_value=365)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_date_range_filtering_property(self, days_offset: int):
        """Property 2: 日期范围筛选
        
        对于任意日期范围，筛选结果应只包含：
        - 没有日期的文档（CCAR 规章可能没有日期字段）
        - publish_date >= start_date (如果指定了 start_date)
        - publish_date <= end_date (如果指定了 end_date)
        
        Feature: caac-regulation-download-enhancement
        Property 2: Date Range Filtering
        Validates: Requirements 1.5, 1.6, 1.7
        """
        # 创建固定的测试文档
        documents = [
            RegulationDocument(
                title="2024年文档", url="http://example.com/1",
                validity="有效", doc_number="CCAR-1",
                office_unit="测试司", doc_type="regulation",
                publish_date="2024-06-15"
            ),
            RegulationDocument(
                title="2023年文档", url="http://example.com/2",
                validity="有效", doc_number="CCAR-2",
                office_unit="测试司", doc_type="regulation",
                publish_date="2023-03-20"
            ),
            RegulationDocument(
                title="无日期文档", url="http://example.com/3",
                validity="有效", doc_number="CCAR-3",
                office_unit="测试司", doc_type="regulation",
                publish_date=""
            ),
        ]
        
        today = date.today()
        start_date = (today - timedelta(days=days_offset)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
        filtered = filter_documents_by_date(documents, start_date, end_date)
        
        for doc in filtered:
            # 没有日期的文档也会显示（CCAR 规章可能没有日期字段）
            if doc.publish_date:
                # 有发布日期的文档必须在范围内
                assert doc.publish_date >= start_date, f"发布日期 {doc.publish_date} 早于起始日期 {start_date}"
                assert doc.publish_date <= end_date, f"发布日期 {doc.publish_date} 晚于结束日期 {end_date}"
    
    def test_no_date_filter_returns_all(self):
        """无日期限制返回所有文档"""
        documents = [
            RegulationDocument(
                title="文档1", url="http://example.com/1",
                validity="有效", doc_number="CCAR-1",
                office_unit="测试司", doc_type="regulation",
                publish_date="2024-01-15"
            ),
            RegulationDocument(
                title="文档2", url="http://example.com/2",
                validity="有效", doc_number="CCAR-2",
                office_unit="测试司", doc_type="regulation",
                publish_date=""  # 无发布日期
            ),
        ]
        
        filtered = filter_documents_by_date(documents, "", "")
        assert len(filtered) == 2
    
    def test_documents_without_date_included_when_filtering(self):
        """有日期限制时，无发布日期的文档也会显示（CCAR 规章可能没有日期字段）
        
        Validates: Requirements 1.7
        """
        documents = [
            RegulationDocument(
                title="有日期文档", url="http://example.com/1",
                validity="有效", doc_number="CCAR-1",
                office_unit="测试司", doc_type="regulation",
                publish_date="2024-06-15"
            ),
            RegulationDocument(
                title="无日期文档", url="http://example.com/2",
                validity="有效", doc_number="CCAR-2",
                office_unit="测试司", doc_type="regulation",
                publish_date=""
            ),
        ]
        
        filtered = filter_documents_by_date(documents, "2024-01-01", "2024-12-31")
        # 无日期的文档也会显示，因为 CCAR 规章可能没有日期字段
        assert len(filtered) == 2
        titles = [d.title for d in filtered]
        assert "有日期文档" in titles
        assert "无日期文档" in titles
    
    def test_start_date_only_filter(self):
        """只有起始日期的筛选"""
        documents = [
            RegulationDocument(
                title="2024年文档", url="http://example.com/1",
                validity="有效", doc_number="CCAR-1",
                office_unit="测试司", doc_type="regulation",
                publish_date="2024-06-15"
            ),
            RegulationDocument(
                title="2023年文档", url="http://example.com/2",
                validity="有效", doc_number="CCAR-2",
                office_unit="测试司", doc_type="regulation",
                publish_date="2023-03-20"
            ),
        ]
        
        filtered = filter_documents_by_date(documents, "2024-01-01", "")
        assert len(filtered) == 1
        assert filtered[0].title == "2024年文档"
    
    def test_end_date_only_filter(self):
        """只有结束日期的筛选"""
        documents = [
            RegulationDocument(
                title="2024年文档", url="http://example.com/1",
                validity="有效", doc_number="CCAR-1",
                office_unit="测试司", doc_type="regulation",
                publish_date="2024-06-15"
            ),
            RegulationDocument(
                title="2023年文档", url="http://example.com/2",
                validity="有效", doc_number="CCAR-2",
                office_unit="测试司", doc_type="regulation",
                publish_date="2023-03-20"
            ),
        ]
        
        filtered = filter_documents_by_date(documents, "", "2023-12-31")
        assert len(filtered) == 1
        assert filtered[0].title == "2023年文档"
