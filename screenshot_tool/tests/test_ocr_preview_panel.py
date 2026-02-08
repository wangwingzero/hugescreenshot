# -*- coding: utf-8 -*-
"""
OCR 预览面板单元测试

Feature: clipboard-ocr-merge
Task: 1.4 编写 OCR 预览面板单元测试

测试内容：
1. 按钮可见性测试
2. 缓存逻辑测试
3. 引擎切换测试

**Validates: Requirements 4.1, 4.3, 4.4**
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt

from screenshot_tool.ui.ocr_preview_panel import (
    OCRPreviewPanel,
    CachedOCRResult,
)


# ============================================================
# Mock OCRManager 类
# ============================================================

class MockOCRManager:
    """模拟 OCRManager 用于测试
    
    可配置各引擎的可用状态。
    """
    
    def __init__(
        self,
        rapid_available: bool = True,
        tencent_available: bool = False,
        baidu_available: bool = False
    ):
        self._rapid_available = rapid_available
        self._tencent_available = tencent_available
        self._baidu_available = baidu_available
    
    def get_engine_status(self) -> dict:
        """返回引擎状态"""
        return {
            "rapid": {
                "available": self._rapid_available,
                "message": "已安装" if self._rapid_available else "未安装"
            },
            "tencent": {
                "available": self._tencent_available,
                "message": "已配置" if self._tencent_available else "未配置"
            },
            "baidu": {
                "available": self._baidu_available,
                "message": "已配置" if self._baidu_available else "未配置"
            },
        }
    
    def is_engine_available(self, engine: str) -> bool:
        """检查引擎是否可用"""
        if engine == "rapid":
            return self._rapid_available
        elif engine == "tencent":
            return self._tencent_available
        elif engine == "baidu":
            return self._baidu_available
        return False
    
    def recognize_with_engine(self, image: QImage, engine: str):
        """模拟 OCR 识别"""
        from screenshot_tool.services.ocr_manager import UnifiedOCRResult
        return UnifiedOCRResult(
            success=True,
            text="测试识别结果",
            engine=engine,
            average_score=0.85,
            backend_detail="OpenVINO",
            elapsed_time=0.5
        )


# ============================================================
# 按钮可见性测试
# ============================================================

class TestButtonVisibility:
    """按钮可见性测试
    
    **Validates: Requirements 4.1, 4.4**
    
    注意：Qt 中 isVisible() 只有在 widget 显示后才返回 True。
    对于未显示的 widget，我们使用 isHidden() 来检查是否被显式隐藏。
    - isHidden() == False 表示按钮没有被隐藏（会在父组件显示时可见）
    - isHidden() == True 表示按钮被显式隐藏
    """
    
    def test_back_button_removed(self, qtbot):
        """测试返回按钮已被移除
        
        「返回图片」按钮已移除，右侧默认显示 OCR 内容，
        左侧缩略图已改为高清显示。
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 返回按钮应该为 None（已移除）
        assert panel._back_btn is None
    
    def test_copy_button_not_hidden(self, qtbot):
        """测试复制按钮没有被隐藏
        
        Requirements: 5.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        assert not panel._copy_btn.isHidden()
    
    def test_format_button_not_hidden(self, qtbot):
        """测试排版按钮没有被隐藏
        
        Requirements: 5.2
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        assert not panel._format_btn.isHidden()
    
    def test_translate_button_not_hidden(self, qtbot):
        """测试翻译按钮没有被隐藏
        
        Requirements: 5.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        assert not panel._translate_btn.isHidden()
    
    def test_rapid_button_not_hidden_when_available(self, qtbot):
        """测试本地 OCR 按钮在可用时没有被隐藏
        
        Requirements: 4.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（本地 OCR 可用）
        mock_manager = MockOCRManager(rapid_available=True)
        panel.set_ocr_manager(mock_manager)
        
        # 本地 OCR 按钮不应该被隐藏且应该启用
        assert not panel._rapid_btn.isHidden()
        assert panel._rapid_btn.isEnabled()
    
    def test_rapid_button_disabled_when_unavailable(self, qtbot):
        """测试本地 OCR 按钮在不可用时禁用
        
        Requirements: 4.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（本地 OCR 不可用）
        mock_manager = MockOCRManager(rapid_available=False)
        panel.set_ocr_manager(mock_manager)
        
        # 本地 OCR 按钮应该禁用
        assert not panel._rapid_btn.isEnabled()
    
    def test_tencent_button_hidden_when_not_configured(self, qtbot):
        """测试腾讯 OCR 按钮在未配置时隐藏
        
        Requirements: 4.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（腾讯 OCR 未配置）
        mock_manager = MockOCRManager(tencent_available=False)
        panel.set_ocr_manager(mock_manager)
        
        # 腾讯 OCR 按钮应该被隐藏
        assert panel._tencent_btn.isHidden()
    
    def test_tencent_button_not_hidden_when_configured(self, qtbot):
        """测试腾讯 OCR 按钮在已配置时没有被隐藏
        
        Requirements: 4.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（腾讯 OCR 已配置）
        mock_manager = MockOCRManager(tencent_available=True)
        panel.set_ocr_manager(mock_manager)
        
        # 腾讯 OCR 按钮不应该被隐藏且应该启用
        assert not panel._tencent_btn.isHidden()
        assert panel._tencent_btn.isEnabled()
    
    def test_baidu_button_hidden_when_not_configured(self, qtbot):
        """测试百度 OCR 按钮在未配置时隐藏
        
        Requirements: 4.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（百度 OCR 未配置）
        mock_manager = MockOCRManager(baidu_available=False)
        panel.set_ocr_manager(mock_manager)
        
        # 百度 OCR 按钮应该被隐藏
        assert panel._baidu_btn.isHidden()
    
    def test_baidu_button_not_hidden_when_configured(self, qtbot):
        """测试百度 OCR 按钮在已配置时没有被隐藏
        
        Requirements: 4.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（百度 OCR 已配置）
        mock_manager = MockOCRManager(baidu_available=True)
        panel.set_ocr_manager(mock_manager)
        
        # 百度 OCR 按钮不应该被隐藏且应该启用
        assert not panel._baidu_btn.isHidden()
        assert panel._baidu_btn.isEnabled()
    
    def test_all_cloud_buttons_not_hidden_when_all_configured(self, qtbot):
        """测试所有云端 OCR 按钮在全部配置时都没有被隐藏
        
        Requirements: 4.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器（所有引擎都可用）
        mock_manager = MockOCRManager(
            rapid_available=True,
            tencent_available=True,
            baidu_available=True
        )
        panel.set_ocr_manager(mock_manager)
        
        # 所有按钮都不应该被隐藏
        assert not panel._rapid_btn.isHidden()
        assert not panel._tencent_btn.isHidden()
        assert not panel._baidu_btn.isHidden()


# ============================================================
# 缓存逻辑测试
# ============================================================

class TestCacheLogic:
    """缓存逻辑测试
    
    **Validates: Requirements 4.3, 8.1, 8.2**
    """
    
    def test_cache_stores_result_correctly(self, qtbot):
        """测试缓存正确存储结果
        
        Requirements: 4.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 手动调用缓存方法
        panel._cache_result(
            item_id="test-item-1",
            engine="rapid",
            text="测试文本",
            average_score=0.9,
            backend_detail="OpenVINO",
            elapsed_time=0.5
        )
        
        # 验证缓存结构
        assert "test-item-1" in panel._ocr_cache
        assert "rapid" in panel._ocr_cache["test-item-1"]
        
        cached = panel._ocr_cache["test-item-1"]["rapid"]
        assert cached.item_id == "test-item-1"
        assert cached.engine == "rapid"
        assert cached.text == "测试文本"
        assert cached.average_score == 0.9
        assert cached.backend_detail == "OpenVINO"
        assert cached.elapsed_time == 0.5
    
    def test_cache_key_is_item_id_and_engine(self, qtbot):
        """测试缓存键是 (item_id, engine) 组合
        
        Requirements: 4.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 同一条目，不同引擎
        panel._cache_result("item-1", "rapid", "本地结果", 0.8, "", 0.3)
        panel._cache_result("item-1", "tencent", "腾讯结果", 0.95, "", 0.5)
        
        # 验证两个引擎的结果都被缓存
        assert "rapid" in panel._ocr_cache["item-1"]
        assert "tencent" in panel._ocr_cache["item-1"]
        assert panel._ocr_cache["item-1"]["rapid"].text == "本地结果"
        assert panel._ocr_cache["item-1"]["tencent"].text == "腾讯结果"
    
    def test_restore_cached_result_returns_true_when_exists(self, qtbot):
        """测试 restore_cached_result 在有缓存时返回 True
        
        Requirements: 8.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 先缓存结果
        panel._cache_result("item-1", "rapid", "缓存文本", 0.85, "OpenVINO", 0.4)
        
        # 恢复缓存
        result = panel.restore_cached_result("item-1")
        
        assert result is True
        assert panel._text_edit.toPlainText() == "缓存文本"
    
    def test_restore_cached_result_returns_false_when_no_cache(self, qtbot):
        """测试 restore_cached_result 在无缓存时返回 False
        
        Requirements: 8.2
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 不缓存任何结果，直接尝试恢复
        result = panel.restore_cached_result("non-existent-item")
        
        assert result is False
    
    def test_clear_cache_removes_all_cached_results(self, qtbot):
        """测试 clear_cache 清除所有缓存结果
        
        Requirements: 8.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 缓存多个结果
        panel._cache_result("item-1", "rapid", "文本1", 0.8, "", 0.3)
        panel._cache_result("item-2", "rapid", "文本2", 0.9, "", 0.4)
        panel._cache_result("item-1", "tencent", "文本3", 0.95, "", 0.5)
        
        # 验证缓存不为空
        assert len(panel._ocr_cache) > 0
        
        # 清空缓存
        panel.clear_cache()
        
        # 验证缓存已清空
        assert len(panel._ocr_cache) == 0
    
    def test_cache_limit_enforcement(self, qtbot):
        """测试缓存大小限制（MAX_CACHE_SIZE = 20）
        
        Requirements: 10.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 添加超过限制的缓存条目
        for i in range(25):
            panel._cache_result(
                item_id=f"item-{i}",
                engine="rapid",
                text=f"文本 {i}",
                average_score=0.8,
                backend_detail="",
                elapsed_time=0.3
            )
        
        # 计算总缓存条目数
        total_entries = sum(len(engines) for engines in panel._ocr_cache.values())
        
        # 验证缓存条目数不超过限制
        assert total_entries <= panel.MAX_CACHE_SIZE
    
    def test_has_cached_result_returns_true_when_exists(self, qtbot):
        """测试 has_cached_result 在有缓存时返回 True"""
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        panel._cache_result("item-1", "rapid", "文本", 0.8, "", 0.3)
        
        assert panel.has_cached_result("item-1") is True
    
    def test_has_cached_result_returns_false_when_not_exists(self, qtbot):
        """测试 has_cached_result 在无缓存时返回 False"""
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel.has_cached_result("non-existent") is False
    
    def test_cache_preserves_multiple_engines_per_item(self, qtbot):
        """测试缓存保留同一条目的多个引擎结果
        
        Requirements: 4.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 同一条目，三个引擎
        panel._cache_result("item-1", "rapid", "本地", 0.8, "", 0.3)
        panel._cache_result("item-1", "tencent", "腾讯", 0.9, "", 0.4)
        panel._cache_result("item-1", "baidu", "百度", 0.85, "", 0.5)
        
        # 验证三个引擎的结果都存在
        assert len(panel._ocr_cache["item-1"]) == 3
        assert panel._ocr_cache["item-1"]["rapid"].text == "本地"
        assert panel._ocr_cache["item-1"]["tencent"].text == "腾讯"
        assert panel._ocr_cache["item-1"]["baidu"].text == "百度"


# ============================================================
# 引擎切换测试
# ============================================================

class TestEngineSwitching:
    """引擎切换测试
    
    **Validates: Requirements 4.2, 4.3**
    """
    
    def test_switch_engine_emits_signal(self, qtbot):
        """测试 _switch_engine 发出 engine_switch_requested 信号
        
        Requirements: 4.2
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(
            rapid_available=True,
            tencent_available=True
        )
        panel.set_ocr_manager(mock_manager)
        
        # 设置当前图片（需要有图片才能触发 OCR）
        panel._current_image = QImage(100, 100, QImage.Format.Format_RGB32)
        panel._current_item_id = "test-item"
        
        # 监听信号
        signal_received = []
        panel.engine_switch_requested.connect(lambda e: signal_received.append(e))
        
        # 切换引擎
        panel._switch_engine("tencent")
        
        # 验证信号被发出
        assert "tencent" in signal_received
    
    def test_engine_button_highlighting_updates(self, qtbot):
        """测试引擎按钮高亮正确更新
        
        Requirements: 4.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(
            rapid_available=True,
            tencent_available=True,
            baidu_available=True
        )
        panel.set_ocr_manager(mock_manager)
        
        # 设置当前引擎为 rapid
        panel._current_engine = "rapid"
        panel._highlight_current_engine()
        
        # 验证 rapid 按钮被选中
        assert panel._rapid_btn.isChecked()
        assert not panel._tencent_btn.isChecked()
        assert not panel._baidu_btn.isChecked()
        
        # 切换到 tencent
        panel._current_engine = "tencent"
        panel._highlight_current_engine()
        
        # 验证 tencent 按钮被选中
        assert not panel._rapid_btn.isChecked()
        assert panel._tencent_btn.isChecked()
        assert not panel._baidu_btn.isChecked()
    
    def test_switch_engine_uses_cache_when_available(self, qtbot):
        """测试切换引擎时使用缓存结果
        
        Requirements: 4.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(
            rapid_available=True,
            tencent_available=True
        )
        panel.set_ocr_manager(mock_manager)
        
        # 设置当前图片和条目
        panel._current_image = QImage(100, 100, QImage.Format.Format_RGB32)
        panel._current_item_id = "test-item"
        
        # 预先缓存 tencent 的结果
        panel._cache_result(
            "test-item", "tencent", "腾讯缓存结果", 0.95, "", 0.5
        )
        
        # 切换到 tencent
        panel._switch_engine("tencent")
        
        # 验证使用了缓存结果
        assert panel._text_edit.toPlainText() == "腾讯缓存结果"
    
    def test_switch_engine_without_image_only_updates_current_engine(self, qtbot):
        """测试没有图片时切换引擎只更新当前引擎标记
        
        Requirements: 4.2
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(rapid_available=True, tencent_available=True)
        panel.set_ocr_manager(mock_manager)
        
        # 不设置图片
        panel._current_image = None
        
        # 切换引擎
        panel._switch_engine("tencent")
        
        # 验证当前引擎已更新
        assert panel._current_engine == "tencent"
        assert panel._tencent_btn.isChecked()
    
    def test_engine_button_click_triggers_switch(self, qtbot):
        """测试点击引擎按钮触发切换"""
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(
            rapid_available=True,
            tencent_available=True
        )
        panel.set_ocr_manager(mock_manager)
        
        # 监听信号
        signal_received = []
        panel.engine_switch_requested.connect(lambda e: signal_received.append(e))
        
        # 设置图片以触发完整的切换流程
        panel._current_image = QImage(100, 100, QImage.Format.Format_RGB32)
        panel._current_item_id = "test-item"
        
        # 点击腾讯按钮
        qtbot.mouseClick(panel._tencent_btn, Qt.MouseButton.LeftButton)
        
        # 验证信号被发出
        assert "tencent" in signal_received


# ============================================================
# 文本操作测试
# ============================================================

class TestTextOperations:
    """文本操作测试
    
    **Validates: Requirements 5.4, 5.5**
    """
    
    def test_restore_original_restores_ocr_text(self, qtbot):
        """测试原文按钮恢复 OCR 原始结果
        
        Requirements: 5.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 结果
        panel.set_text("原始 OCR 文本", "rapid", 0.85, "", 0.5)
        
        # 修改文本
        panel._text_edit.setPlainText("修改后的文本")
        panel._toggle_btn.setEnabled(True)
        
        # 点击原文按钮
        panel._restore_original()
        
        # 验证文本已恢复
        assert panel._text_edit.toPlainText() == "原始 OCR 文本"
    
    def test_character_count_accuracy(self, qtbot):
        """测试字符计数准确性
        
        Requirements: 5.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置文本
        panel._text_edit.setPlainText("测试文本")
        
        # 触发计数更新
        panel._update_count()
        
        # 验证字符计数（排除空白字符）
        assert panel._count_label.text() == "4 字"
    
    def test_character_count_excludes_whitespace(self, qtbot):
        """测试字符计数排除空白字符
        
        Requirements: 5.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置包含空白字符的文本
        panel._text_edit.setPlainText("测试 文本\n换行")
        
        # 触发计数更新
        panel._update_count()
        
        # 验证字符计数（排除空格、换行、制表符）
        # "测试文本换行" = 6 个字符
        assert panel._count_label.text() == "6 字"


# ============================================================
# 状态管理测试
# ============================================================

class TestStateManagement:
    """状态管理测试"""
    
    def test_set_loading_state(self, qtbot):
        """测试设置加载状态
        
        Requirements: 3.1
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        panel.set_loading()
        
        assert panel._text_edit.toPlainText() == ""
        assert "识别中" in panel._status_label.text()
    
    def test_set_error_state(self, qtbot):
        """测试设置错误状态
        
        Requirements: 3.3
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        panel.set_error("测试错误")
        
        assert "识别失败" in panel._text_edit.toPlainText()
        assert "测试错误" in panel._text_edit.toPlainText()
    
    def test_clear_resets_all_state(self, qtbot):
        """测试 clear 重置所有状态"""
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置一些状态
        panel.set_text("测试文本", "rapid", 0.85, "OpenVINO", 0.5)
        panel._current_item_id = "test-item"
        
        # 清空
        panel.clear()
        
        # 验证状态已重置
        assert panel._text_edit.toPlainText() == ""
        assert panel._original_text == ""
        assert panel._current_engine == ""
        assert panel._current_item_id == ""
    
    def test_get_text_returns_current_text(self, qtbot):
        """测试 get_text 返回当前文本"""
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        panel._text_edit.setPlainText("当前文本内容")
        
        assert panel.get_text() == "当前文本内容"


# ============================================================
# 信号测试
# ============================================================

class TestSignals:
    """信号测试"""
    
    def test_back_to_image_signal_exists(self, qtbot):
        """测试返回图片信号存在
        
        「返回图片」按钮已移除，但信号仍保留以兼容现有代码。
        信号可通过 _on_back_clicked() 方法触发。
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 信号应该存在
        assert hasattr(panel, 'back_to_image_requested')
        
        # 通过方法触发信号
        with qtbot.waitSignal(panel.back_to_image_requested, timeout=1000):
            panel._on_back_clicked()


# ============================================================
# CachedOCRResult 数据类测试
# ============================================================

class TestCachedOCRResult:
    """CachedOCRResult 数据类测试"""
    
    def test_cached_result_fields(self):
        """测试 CachedOCRResult 包含所有必需字段"""
        now = datetime.now()
        cached = CachedOCRResult(
            item_id="test-id",
            engine="rapid",
            text="测试文本",
            average_score=0.85,
            backend_detail="OpenVINO",
            elapsed_time=0.5,
            timestamp=now
        )
        
        assert cached.item_id == "test-id"
        assert cached.engine == "rapid"
        assert cached.text == "测试文本"
        assert cached.average_score == 0.85
        assert cached.backend_detail == "OpenVINO"
        assert cached.elapsed_time == 0.5
        assert cached.timestamp == now


# ============================================================
# OCR 取消机制测试 (Task 2.4)
# ============================================================

class TestOCRCancellation:
    """OCR 取消机制测试
    
    Feature: clipboard-ocr-merge
    Task: 2.4 实现 OCR 取消机制
    
    **Validates: Requirements 9.4, 10.5**
    
    测试内容：
    1. cancel_ocr() 调用 request_stop()
    2. worker 线程正确清理
    3. 100ms 内响应取消请求
    """
    
    def test_cancel_ocr_calls_request_stop(self, qtbot):
        """测试 cancel_ocr 调用 worker 的 request_stop 方法
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._ocr_worker = mock_worker
        
        # 调用取消
        panel.cancel_ocr()
        
        # 验证 request_stop 被调用
        mock_worker.request_stop.assert_called_once()
    
    def test_cancel_ocr_disconnects_finished_signal(self, qtbot):
        """测试 cancel_ocr 断开 finished 信号连接
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._ocr_worker = mock_worker
        
        # 调用取消
        panel.cancel_ocr()
        
        # 验证 finished.disconnect 被调用
        mock_worker.finished.disconnect.assert_called()
    
    def test_cancel_ocr_waits_500ms_max(self, qtbot):
        """测试 cancel_ocr 最多等待 500ms（修复快速切换崩溃问题）
        
        Requirements: 10.5
        
        修复：增加等待时间从 100ms 到 500ms，确保 OCR 线程完全停止，
        避免快速切换时多个 OCR 线程同时运行导致崩溃。
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        # 模拟 wait 返回 True（线程正常停止）
        mock_worker.wait.return_value = True
        panel._ocr_worker = mock_worker
        
        # 调用取消
        panel.cancel_ocr()
        
        # 验证 wait(500) 被调用（增加等待时间以确保线程完全停止）
        mock_worker.wait.assert_called_with(500)
    
    def test_cancel_ocr_calls_delete_later(self, qtbot):
        """测试 cancel_ocr 调用 deleteLater 清理 worker
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._ocr_worker = mock_worker
        
        # 调用取消
        panel.cancel_ocr()
        
        # 验证 deleteLater 被调用
        mock_worker.deleteLater.assert_called_once()
    
    def test_cancel_ocr_clears_worker_reference(self, qtbot):
        """测试 cancel_ocr 清除 worker 引用
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._ocr_worker = mock_worker
        
        # 调用取消
        panel.cancel_ocr()
        
        # 验证 worker 引用被清除
        assert panel._ocr_worker is None
    
    def test_cancel_ocr_safe_when_no_worker(self, qtbot):
        """测试没有 worker 时 cancel_ocr 安全执行
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 确保没有 worker
        panel._ocr_worker = None
        
        # 调用取消不应抛出异常
        panel.cancel_ocr()
        
        # 验证状态正常
        assert panel._ocr_worker is None
    
    def test_cancel_ocr_safe_when_worker_not_running(self, qtbot):
        """测试 worker 未运行时 cancel_ocr 安全执行
        
        Requirements: 10.5
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建模拟的 OCRWorker（未运行）
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        panel._ocr_worker = mock_worker
        
        # 调用取消不应抛出异常
        panel.cancel_ocr()
        
        # 验证 worker 引用被清除
        assert panel._ocr_worker is None
    
    def test_start_ocr_cancels_previous_ocr(self, qtbot):
        """测试 start_ocr 取消之前正在进行的 OCR
        
        Requirements: 9.4
        """
        panel = OCRPreviewPanel()
        qtbot.addWidget(panel)
        
        # 设置 OCR 管理器
        mock_manager = MockOCRManager(rapid_available=True)
        panel.set_ocr_manager(mock_manager)
        
        # 创建模拟的旧 OCRWorker
        old_worker = MagicMock()
        old_worker.isRunning.return_value = True
        panel._ocr_worker = old_worker
        
        # 创建测试图片
        test_image = QImage(100, 100, QImage.Format.Format_RGB32)
        
        # 使用 patch 来模拟 OCRWorker 的创建
        with patch('screenshot_tool.ui.ocr_preview_panel.OCRWorker') as MockOCRWorker:
            mock_new_worker = MagicMock()
            MockOCRWorker.return_value = mock_new_worker
            
            # 启动新的 OCR
            panel.start_ocr(test_image, "new-item")
            
            # 验证旧 worker 的 request_stop 被调用
            old_worker.request_stop.assert_called_once()


class TestOCRWorkerRequestStop:
    """OCRWorker.request_stop() 测试
    
    Feature: clipboard-ocr-merge
    Task: 2.4 实现 OCR 取消机制
    
    **Validates: Requirements 10.5**
    """
    
    def test_request_stop_sets_flag(self, qtbot):
        """测试 request_stop 设置停止标志
        
        Requirements: 10.5
        """
        from screenshot_tool.ui.ocr_preview_panel import OCRWorker
        
        # 创建 worker（使用 None 作为 OCR 管理器，因为我们只测试标志）
        worker = OCRWorker(None, "rapid", None)
        
        # 初始状态
        assert worker._should_stop is False
        
        # 调用 request_stop
        worker.request_stop()
        
        # 验证标志被设置
        assert worker._should_stop is True
    
    def test_worker_checks_stop_flag_before_ocr(self, qtbot):
        """测试 worker 在 OCR 前检查停止标志
        
        Requirements: 10.5
        """
        from screenshot_tool.ui.ocr_preview_panel import OCRWorker
        
        # 创建 worker
        mock_manager = MagicMock()
        test_image = QImage(100, 100, QImage.Format.Format_RGB32)
        worker = OCRWorker(test_image, "rapid", mock_manager)
        
        # 设置停止标志
        worker.request_stop()
        
        # 运行 worker
        worker.run()
        
        # 验证 OCR 管理器的 recognize_with_engine 没有被调用
        mock_manager.recognize_with_engine.assert_not_called()
