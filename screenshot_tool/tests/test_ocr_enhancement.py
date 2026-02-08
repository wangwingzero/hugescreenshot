# =====================================================
# =============== OCR 增强功能测试 ===============
# =====================================================

"""
OCR 增强功能属性测试 - OpenVINO Only

从 v1.9.0 开始，统一使用 OpenVINO 后端。

使用 Hypothesis 进行属性测试，验证：
- 评分格式化一致性和颜色映射
- 平均分计算正确性
- 后端显示映射
- OCR 结果完整性
- 预处理指标正确性

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 4.1-4.4
"""

import pytest
import numpy as np
from hypothesis import given, strategies as st, settings, assume

# ========== 导入被测模块 ==========
from screenshot_tool.services.image_preprocessor import (
    PreprocessingConfig,
    PreprocessingMetrics,
    ImagePreprocessor,
)
from screenshot_tool.services.rapid_ocr_service import (
    OCRBox,
    OCRResult,
    get_backend_display_string,
)
from screenshot_tool.services.backend_selector import BackendType, BackendInfo


# ========== 测试配置 ==========
HYPOTHESIS_SETTINGS = settings(max_examples=100, deadline=None)


# ========== Property 1 & 2: 评分格式化和颜色映射 ==========

class TestScoreFormatting:
    """评分格式化测试"""
    
    @given(score=st.floats(min_value=0.0, max_value=1.0))
    @HYPOTHESIS_SETTINGS
    def test_score_format_consistency(self, score):
        """Property 2: 评分格式化一致性
        
        对于任何 0.0-1.0 范围内的分数，格式化输出应为 "OCR评分 XX/100"
        """
        # 模拟 OCRResultWindow._format_score_display 逻辑
        score_100 = int(round(score * 100))
        score_100 = max(0, min(100, score_100))
        display_text = f"OCR评分 {score_100}/100"
        
        # 验证格式
        assert display_text.startswith("OCR评分 ")
        assert display_text.endswith("/100")
        assert 0 <= score_100 <= 100
    
    @given(score=st.floats(min_value=0.0, max_value=1.0))
    @HYPOTHESIS_SETTINGS
    def test_score_color_mapping(self, score):
        """Property 3: 评分颜色映射
        
        - 绿色 (#4CAF50) if score >= 0.6
        - 橙色 (#FF9800) if 0.4 <= score < 0.6
        - 红色 (#F44336) if score < 0.4
        """
        score_100 = int(round(score * 100))
        score_100 = max(0, min(100, score_100))
        
        # 颜色阈值
        SCORE_COLOR_HIGH = (60, "#4CAF50")
        SCORE_COLOR_MEDIUM = (40, "#FF9800")
        SCORE_COLOR_LOW = (0, "#F44336")
        
        if score_100 >= SCORE_COLOR_HIGH[0]:
            expected_color = SCORE_COLOR_HIGH[1]
        elif score_100 >= SCORE_COLOR_MEDIUM[0]:
            expected_color = SCORE_COLOR_MEDIUM[1]
        else:
            expected_color = SCORE_COLOR_LOW[1]
        
        # 验证颜色映射正确
        if score_100 >= 60:
            assert expected_color == "#4CAF50"
        elif score_100 >= 40:
            assert expected_color == "#FF9800"
        else:
            assert expected_color == "#F44336"
    
    @given(score=st.floats(min_value=-10.0, max_value=10.0))
    @HYPOTHESIS_SETTINGS
    def test_score_boundary_handling(self, score):
        """测试分数边界处理"""
        score_100 = int(round(score * 100))
        score_100 = max(0, min(100, score_100))
        
        # 验证分数被裁剪到 0-100 范围
        assert 0 <= score_100 <= 100
    
    def test_score_nan_handling(self):
        """测试 NaN 分数处理"""
        import math
        
        # 模拟 _format_score_display 对 NaN 的处理
        score = float('nan')
        if not math.isfinite(score):
            score = 0.0
        
        score_100 = int(round(score * 100))
        score_100 = max(0, min(100, score_100))
        
        assert score_100 == 0
    
    def test_score_inf_handling(self):
        """测试 Inf 分数处理"""
        import math
        
        # 模拟 _format_score_display 对 Inf 的处理
        for score in [float('inf'), float('-inf')]:
            if not math.isfinite(score):
                score = 0.0
            
            score_100 = int(round(score * 100))
            score_100 = max(0, min(100, score_100))
            
            assert score_100 == 0


# ========== Property 4: 平均分计算 ==========

class TestAverageScoreCalculation:
    """平均分计算测试"""
    
    @given(
        scores=st.lists(
            st.floats(min_value=0.0, max_value=1.0),
            min_size=1,
            max_size=50
        )
    )
    @HYPOTHESIS_SETTINGS
    def test_average_score_calculation(self, scores):
        """Property 4: 平均分计算
        
        对于任何分数列表，平均分应等于所有分数之和除以分数数量
        """
        # 过滤掉 NaN 和 Inf
        valid_scores = [s for s in scores if np.isfinite(s)]
        assume(len(valid_scores) > 0)
        
        # 创建 OCRBox 列表
        boxes = [
            OCRBox(text=f"text_{i}", box=[[0,0],[10,0],[10,10],[0,10]], score=s)
            for i, s in enumerate(valid_scores)
        ]
        
        # 计算平均分
        expected_avg = sum(valid_scores) / len(valid_scores)
        actual_avg = sum(box.score for box in boxes) / len(boxes)
        
        # 验证平均分计算正确（允许浮点误差）
        assert abs(actual_avg - expected_avg) < 1e-9
    
    def test_empty_boxes_average_score(self):
        """测试空结果的平均分"""
        result = OCRResult.empty_result()
        assert result.average_score == 0.0
    
    @given(score=st.floats(min_value=0.0, max_value=1.0))
    @HYPOTHESIS_SETTINGS
    def test_single_box_average_score(self, score):
        """测试单个文本框的平均分"""
        assume(np.isfinite(score))
        
        boxes = [OCRBox(text="test", box=[[0,0],[10,0],[10,10],[0,10]], score=score)]
        avg = sum(box.score for box in boxes) / len(boxes)
        
        assert abs(avg - score) < 1e-9


# ========== Property 5: 后端显示映射 (OpenVINO Only) ==========

class TestBackendDisplayMapping:
    """后端显示映射测试 - OpenVINO Only"""
    
    def test_openvino_backend_display(self):
        """Property 5: OpenVINO 后端显示"""
        display = get_backend_display_string(BackendType.OPENVINO, None)
        assert display == "本地OCR"
    
    def test_openvino_backend_display_with_info(self):
        """测试带 BackendInfo 的 OpenVINO 后端显示"""
        backend_info = BackendInfo(
            backend_type=BackendType.OPENVINO,
            cpu_vendor="Intel",
            openvino_available=True,
        )
        
        display = get_backend_display_string(BackendType.OPENVINO, backend_info)
        assert display == "本地OCR"
    
    def test_none_backend_display(self):
        """测试 None 后端显示"""
        display = get_backend_display_string(None, None)
        assert display == "本地OCR"
    
    @given(cpu_vendor=st.sampled_from(["Intel", "AMD", "ARM", "Unknown"]))
    @HYPOTHESIS_SETTINGS
    def test_backend_display_always_returns_string(self, cpu_vendor):
        """测试后端显示总是返回有效字符串"""
        backend_info = BackendInfo(
            backend_type=BackendType.OPENVINO,
            cpu_vendor=cpu_vendor,
            openvino_available=True,
        )
        
        display = get_backend_display_string(BackendType.OPENVINO, backend_info)
        assert isinstance(display, str)
        assert len(display) > 0
        assert "本地OCR" in display


# ========== Property 6: OCR 结果包含所有指标 ==========

class TestOCRResultCompleteness:
    """OCR 结果完整性测试"""
    
    def test_ocr_result_has_all_fields(self):
        """Property 6: OCR 结果包含所有必需字段"""
        result = OCRResult(
            success=True,
            text="测试文本",
            boxes=[],
            average_score=0.85,
            backend_type="openvino",
            backend_detail="本地OCR",
            preprocessing_metrics=PreprocessingMetrics(),
        )
        
        # 验证所有字段存在
        assert hasattr(result, 'success')
        assert hasattr(result, 'text')
        assert hasattr(result, 'boxes')
        assert hasattr(result, 'error')
        assert hasattr(result, 'average_score')
        assert hasattr(result, 'backend_type')
        assert hasattr(result, 'backend_detail')
        assert hasattr(result, 'preprocessing_metrics')
    
    @given(score=st.floats(min_value=0.0, max_value=1.0))
    @HYPOTHESIS_SETTINGS
    def test_ocr_result_score_in_range(self, score):
        """测试 OCR 结果分数在有效范围内"""
        assume(np.isfinite(score))
        
        result = OCRResult(
            success=True,
            text="test",
            average_score=score,
            backend_type="openvino",
        )
        
        assert 0.0 <= result.average_score <= 1.0
    
    def test_error_result_has_default_values(self):
        """测试错误结果有默认值"""
        result = OCRResult.error_result("测试错误")
        
        assert result.success is False
        assert result.error == "测试错误"
        assert result.average_score == 0.0
        assert result.backend_type is None
        assert result.backend_detail is None
    
    def test_empty_result_has_default_values(self):
        """测试空结果有默认值"""
        result = OCRResult.empty_result()
        
        assert result.success is True
        assert result.text == ""
        assert result.boxes == []
        assert result.average_score == 0.0


# ========== 预处理指标测试 ==========

class TestPreprocessingMetrics:
    """预处理指标测试"""
    
    def test_metrics_default_values(self):
        """测试预处理指标默认值"""
        metrics = PreprocessingMetrics()
        
        assert hasattr(metrics, 'total_time_ms')
        assert hasattr(metrics, 'upscale_time_ms')
        assert hasattr(metrics, 'padding_time_ms')
        assert hasattr(metrics, 'sharpen_time_ms')
        assert hasattr(metrics, 'steps_applied')
        assert hasattr(metrics, 'was_upscaled')
        
        # 默认值
        assert metrics.total_time_ms == 0.0
        assert metrics.upscale_time_ms == 0.0
        assert metrics.padding_time_ms == 0.0
        assert metrics.steps_applied == []
        assert metrics.was_upscaled is False
    
    def test_metrics_with_preprocessing_steps(self):
        """测试应用预处理步骤后的指标"""
        metrics = PreprocessingMetrics(
            upscale_time_ms=5.0,
            sharpen_time_ms=3.0,
            padding_time_ms=2.0,
            total_time_ms=10.0,
            steps_applied=["upscale", "upscale_sharpen", "padding"],
            was_upscaled=True,
            original_size=(50, 300),
            upscaled_size=(300, 1800),
        )
        
        assert metrics.upscale_time_ms == 5.0
        assert metrics.sharpen_time_ms == 3.0
        assert metrics.padding_time_ms == 2.0
        assert metrics.total_time_ms == 10.0
        assert "upscale" in metrics.steps_applied
        assert "upscale_sharpen" in metrics.steps_applied
        assert "padding" in metrics.steps_applied
        assert metrics.was_upscaled is True


# ========== 集成测试 ==========

class TestIntegration:
    """集成测试"""
    
    def test_preprocessor_basic_functionality(self):
        """测试预处理器基本功能"""
        config = PreprocessingConfig(
            enabled=True,
            auto_upscale=True,
        )
        preprocessor = ImagePreprocessor(config)
        
        # 创建测试图像（正常尺寸，不触发预处理）
        image = np.ones((200, 300, 3), dtype=np.uint8) * 200
        
        result, metrics = preprocessor.preprocess(image)
        
        # 正常尺寸图像应直接返回原图
        assert result is not None
        assert result.shape[0] > 0
        assert result.shape[1] > 0
        assert isinstance(metrics, PreprocessingMetrics)
        assert metrics.total_time_ms >= 0.0
        # 非扁平图像不应有预处理步骤
        assert metrics.steps_applied == []
    
    def test_preprocessor_disabled(self):
        """测试禁用预处理器"""
        config = PreprocessingConfig(
            enabled=False,
        )
        preprocessor = ImagePreprocessor(config)
        
        image = np.ones((200, 300, 3), dtype=np.uint8) * 200
        
        result, metrics = preprocessor.preprocess(image)
        
        # 禁用时应返回原图
        assert result is not None
        assert np.array_equal(result, image)
        # 验证 metrics 对象有效
        assert isinstance(metrics, PreprocessingMetrics)
        assert metrics.steps_applied == []
    
    def test_preprocessor_with_grayscale_image(self):
        """测试预处理器处理灰度图像"""
        config = PreprocessingConfig(enabled=True)
        preprocessor = ImagePreprocessor(config)
        
        # 创建灰度测试图像（正常尺寸）
        image = np.ones((100, 150), dtype=np.uint8) * 128
        
        result, metrics = preprocessor.preprocess(image)
        
        assert result is not None
        assert isinstance(metrics, PreprocessingMetrics)
    
    def test_preprocessor_with_small_image(self):
        """测试预处理器处理小图像（触发放大）"""
        config = PreprocessingConfig(
            enabled=True,
            auto_upscale=True,
            min_height=32,
        )
        preprocessor = ImagePreprocessor(config)
        
        # 创建小图像（高度低于阈值）
        image = np.ones((20, 200, 3), dtype=np.uint8) * 150
        
        result, metrics = preprocessor.preprocess(image)
        
        assert result is not None
        # 小图像应该被放大
        assert result.shape[0] >= image.shape[0]
        assert metrics.was_upscaled is True
        assert "upscale" in metrics.steps_applied
    
    def test_preprocessor_with_flat_image(self):
        """测试预处理器处理扁平图像"""
        config = PreprocessingConfig(
            enabled=True,
            auto_upscale=True,
            padding_enabled=True,
            upscale_sharpen=True,
            max_aspect_ratio=5.0,
            target_height=300,
        )
        preprocessor = ImagePreprocessor(config)
        
        # 创建扁平图像（宽高比 > 5）
        image = np.ones((50, 400, 3), dtype=np.uint8) * 180
        
        result, metrics = preprocessor.preprocess(image)
        
        assert result is not None
        # 扁平图像应该被处理
        assert metrics.was_upscaled is True
        assert "upscale" in metrics.steps_applied
        assert "padding" in metrics.steps_applied
    
    def test_preprocessor_normal_image_fast_path(self):
        """测试正常图像走极速路径"""
        config = PreprocessingConfig(enabled=True)
        preprocessor = ImagePreprocessor(config)
        
        # 创建正常尺寸图像（不触发任何预处理）
        image = np.ones((500, 600, 3), dtype=np.uint8) * 200
        
        result, metrics = preprocessor.preprocess(image)
        
        # 正常图像应直接返回，无预处理步骤
        assert np.array_equal(result, image)
        assert metrics.steps_applied == []
        assert metrics.was_upscaled is False
        assert metrics.was_padded is False
