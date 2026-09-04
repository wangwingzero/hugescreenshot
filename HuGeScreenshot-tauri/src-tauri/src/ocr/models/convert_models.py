#!/usr/bin/env python3
"""
PP-OCRv4 模型转换脚本

使用 OpenVINO PrePostProcessor API 将预处理逻辑注入模型，
生成优化后的 IR 格式模型（.xml/.bin）。

优化效果：
- 预处理在 GPU 上执行，减少 CPU 负载
- Rust 代码只需传入原始 u8 数据
- 预期性能提升 30%-100%

使用方法：
    cd HuGeScreenshot-tauri/src-tauri/src/ocr/models
    python convert_models.py
"""

import openvino as ov
from openvino.preprocess import PrePostProcessor, ColorFormat
from openvino.runtime import Layout, Type
import numpy as np
from pathlib import Path


def convert_detection_model():
    """
    转换检测模型 (DBNet)
    
    预处理步骤：
    1. u8 -> f32 转换
    2. BGR -> RGB 转换（PP-OCR 使用 BGR）
    3. 归一化: (pixel / 255.0 - 0.5) / 0.5 = pixel / 127.5 - 1.0
    """
    print("=" * 60)
    print("转换检测模型: ch_PP-OCRv4_det_infer.onnx")
    print("=" * 60)
    
    model_path = Path(__file__).parent / "ch_PP-OCRv4_det_infer.onnx"
    output_path = Path(__file__).parent / "ch_PP-OCRv4_det_preprocessed"
    
    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        return False
    
    # 加载模型
    core = ov.Core()
    model = core.read_model(str(model_path))
    
    print(f"原始模型输入: {model.inputs}")
    print(f"原始模型输出: {model.outputs}")
    
    # 创建 PrePostProcessor
    ppp = PrePostProcessor(model)
    
    # 配置输入
    # PP-OCR 检测模型输入名称通常是 "x"
    input_info = ppp.input(0)
    
    # 设置输入张量属性（原始数据格式）
    # - 元素类型: u8 (0-255)
    # - 布局: NHWC (Height, Width, Channel) - 这是图像库的常见格式
    # - 颜色格式: BGR (OpenCV/截图库的默认格式)
    input_info.tensor() \
        .set_element_type(Type.u8) \
        .set_layout(Layout("NHWC")) \
        .set_color_format(ColorFormat.BGR)
    
    # 设置预处理步骤
    # 1. 转换颜色格式 BGR -> RGB（如果模型需要 RGB）
    # 2. 转换布局 NHWC -> NCHW（模型期望的格式）
    # 3. 转换元素类型 u8 -> f32
    # 4. 归一化: (x / 255.0 - mean) / std
    #    PP-OCR: mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]
    #    等价于: x / 127.5 - 1.0
    input_info.preprocess() \
        .convert_element_type(Type.f32) \
        .convert_color(ColorFormat.RGB) \
        .mean([127.5, 127.5, 127.5]) \
        .scale([127.5, 127.5, 127.5])
    
    # 设置模型期望的布局
    input_info.model().set_layout(Layout("NCHW"))
    
    # 构建预处理后的模型
    model_with_ppp = ppp.build()
    
    print(f"预处理后模型输入: {model_with_ppp.inputs}")
    
    # 保存为 IR 格式
    ov.save_model(model_with_ppp, str(output_path) + ".xml")
    
    print(f"✅ 检测模型已保存: {output_path}.xml")
    print(f"✅ 检测模型已保存: {output_path}.bin")
    
    return True


def convert_recognition_model():
    """
    转换识别模型 (SVTR)
    
    预处理步骤：
    1. u8 -> f32 转换
    2. 归一化: pixel / 127.5 - 1.0
    
    注意：识别模型的宽度是动态的
    """
    print("\n" + "=" * 60)
    print("转换识别模型: ch_PP-OCRv4_rec_infer.onnx")
    print("=" * 60)
    
    model_path = Path(__file__).parent / "ch_PP-OCRv4_rec_infer.onnx"
    output_path = Path(__file__).parent / "ch_PP-OCRv4_rec_preprocessed"
    
    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        return False
    
    # 加载模型
    core = ov.Core()
    model = core.read_model(str(model_path))
    
    print(f"原始模型输入: {model.inputs}")
    print(f"原始模型输出: {model.outputs}")
    
    # 创建 PrePostProcessor
    ppp = PrePostProcessor(model)
    
    # 配置输入
    input_info = ppp.input(0)
    
    # 设置输入张量属性
    # 识别模型也使用 NHWC 格式的 u8 输入
    input_info.tensor() \
        .set_element_type(Type.u8) \
        .set_layout(Layout("NHWC")) \
        .set_color_format(ColorFormat.BGR)
    
    # 设置预处理步骤
    # PP-OCR 识别模型归一化: (x / 255.0 - 0.5) / 0.5 = x / 127.5 - 1.0
    input_info.preprocess() \
        .convert_element_type(Type.f32) \
        .convert_color(ColorFormat.RGB) \
        .mean([127.5, 127.5, 127.5]) \
        .scale([127.5, 127.5, 127.5])
    
    # 设置模型期望的布局
    input_info.model().set_layout(Layout("NCHW"))
    
    # 构建预处理后的模型
    model_with_ppp = ppp.build()
    
    print(f"预处理后模型输入: {model_with_ppp.inputs}")
    
    # 保存为 IR 格式
    ov.save_model(model_with_ppp, str(output_path) + ".xml")
    
    print(f"✅ 识别模型已保存: {output_path}.xml")
    print(f"✅ 识别模型已保存: {output_path}.bin")
    
    return True


def verify_models():
    """验证转换后的模型"""
    print("\n" + "=" * 60)
    print("验证转换后的模型")
    print("=" * 60)
    
    core = ov.Core()
    
    # 验证检测模型
    det_path = Path(__file__).parent / "ch_PP-OCRv4_det_preprocessed.xml"
    if det_path.exists():
        det_model = core.read_model(str(det_path))
        print(f"\n检测模型:")
        print(f"  输入: {det_model.inputs[0]}")
        print(f"  输入形状: {det_model.inputs[0].partial_shape}")
        print(f"  输入类型: {det_model.inputs[0].element_type}")
    else:
        print(f"❌ 检测模型不存在: {det_path}")
    
    # 验证识别模型
    rec_path = Path(__file__).parent / "ch_PP-OCRv4_rec_preprocessed.xml"
    if rec_path.exists():
        rec_model = core.read_model(str(rec_path))
        print(f"\n识别模型:")
        print(f"  输入: {rec_model.inputs[0]}")
        print(f"  输入形状: {rec_model.inputs[0].partial_shape}")
        print(f"  输入类型: {rec_model.inputs[0].element_type}")
    else:
        print(f"❌ 识别模型不存在: {rec_path}")


def main():
    print("PP-OCRv4 模型转换工具")
    print("将预处理逻辑注入模型，生成优化后的 IR 格式")
    print()
    
    success = True
    
    # 转换检测模型
    if not convert_detection_model():
        success = False
    
    # 转换识别模型
    if not convert_recognition_model():
        success = False
    
    # 验证模型
    if success:
        verify_models()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 所有模型转换完成！")
        print("\n下一步：")
        print("1. 修改 Rust 代码，加载 .xml 模型而不是 .onnx")
        print("2. 修改预处理代码，直接传入 u8 数据")
    else:
        print("❌ 部分模型转换失败")
    print("=" * 60)


if __name__ == "__main__":
    main()
