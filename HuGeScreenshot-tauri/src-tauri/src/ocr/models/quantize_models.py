#!/usr/bin/env python3
"""
PP-OCRv4 模型 INT8 量化脚本

使用 OpenVINO NNCF 对已注入预处理的 IR 模型进行 INT8 离线量化（PTQ）。
量化后模型推理速度预期提升 2-4 倍，体积减小约 50%-75%。

前置条件：
    pip install openvino nncf opencv-python numpy

使用方法：
    1. 准备校准图片（200-300 张截图），放入 calibration_images/ 目录
    2. 运行脚本：
       cd HuGeScreenshot-tauri/src-tauri/src/ocr/models
       python quantize_models.py

    如果没有校准图片，脚本会自动生成合成数据（效果略差于真实数据）。

注意事项：
    - 模型已内置预处理（BGR->RGB + 归一化），transform_fn 只做 resize，不做归一化
    - 检测模型输入: [N, H, W, 3] u8 NHWC BGR
    - 识别模型输入: [N, 48, W, 3] u8 NHWC BGR
"""

import nncf
import openvino as ov
import numpy as np
import cv2
from pathlib import Path
import sys
import time


# ============================================
# 配置
# ============================================

# 校准图片目录（放你的截图进去）
# 图片放在了前端 src/ 目录下，而非 src-tauri/ 下
# __file__ 在 src-tauri/src/ocr/models/，往上 4 级到 HuGeScreenshot-tauri/
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CALIBRATION_DIR = _PROJECT_ROOT / "src" / "ocr" / "models" / "calibration_images"

# 校准样本数量（真实图片不够时用合成数据补齐）
CALIBRATION_SAMPLES = 200

# 检测模型输入尺寸（与 Rust config.rs 中的 det_input_size 一致）
DET_INPUT_SIZE = 640

# 识别模型输入高度（固定 48）
REC_INPUT_HEIGHT = 48

# 识别模型校准用的宽度桶（与 Rust recognizer.rs 中的一致）
REC_WIDTH_BUCKETS = [160, 320, 640]


# ============================================
# 工具函数
# ============================================

def imread_unicode(path: Path) -> np.ndarray | None:
    """读取含中文路径的图片（解决 OpenCV 中文路径问题）"""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def collect_calibration_images() -> list[np.ndarray]:
    """收集校准图片（BGR 格式的 numpy 数组）"""
    images = []
    
    if CALIBRATION_DIR.exists():
        extensions = [".png", ".jpg", ".jpeg", ".bmp", ".webp"]
        for ext in extensions:
            for img_path in CALIBRATION_DIR.glob(f"*{ext}"):
                img = imread_unicode(img_path)
                if img is not None:
                    images.append(img)
        
        print(f"从 {CALIBRATION_DIR} 加载了 {len(images)} 张校准图片")
    
    if len(images) < 20:
        print(f"⚠️  真实图片不足 20 张（当前 {len(images)} 张），将使用合成数据补齐")
        print(f"   建议：将 200-300 张实际截图放入 {CALIBRATION_DIR}/ 目录以获得最佳量化效果")
        images.extend(generate_synthetic_images(CALIBRATION_SAMPLES - len(images)))
    
    return images


def generate_synthetic_images(count: int) -> list[np.ndarray]:
    """
    生成合成校准图片（模拟截图场景）
    
    生成包含文字的合成图片，模拟常见截图场景：
    - 白底黑字（浅色模式）
    - 黑底白字（深色模式）
    - 不同字号和密度
    """
    images = []
    np.random.seed(42)
    
    for i in range(count):
        # 随机选择尺寸（模拟常见屏幕分辨率）
        h = np.random.choice([720, 800, 900, 1080, 1200])
        w = np.random.choice([1280, 1366, 1440, 1920, 2560])
        
        # 随机选择主题（浅色/深色）
        if i % 3 == 0:
            # 深色模式
            bg_color = np.random.randint(20, 60)
            text_color = np.random.randint(180, 255)
        elif i % 3 == 1:
            # 浅色模式
            bg_color = np.random.randint(230, 255)
            text_color = np.random.randint(0, 60)
        else:
            # 中等对比度
            bg_color = np.random.randint(100, 200)
            text_color = np.random.randint(0, 80) if bg_color > 150 else np.random.randint(200, 255)
        
        # 创建背景
        img = np.full((h, w, 3), bg_color, dtype=np.uint8)
        
        # 添加一些模拟文字行（用矩形模拟）
        font = cv2.FONT_HERSHEY_SIMPLEX
        line_height = np.random.choice([20, 24, 28, 32, 36])
        y = 40
        while y < h - 40:
            # 随机行宽
            line_width = np.random.randint(w // 4, w - 40)
            # 用 putText 模拟文字（ASCII）
            text_len = np.random.randint(10, 80)
            text = ''.join(chr(np.random.randint(33, 127)) for _ in range(text_len))
            font_scale = line_height / 40.0
            cv2.putText(img, text, (20, y), font, font_scale, 
                       (text_color, text_color, text_color), 1, cv2.LINE_AA)
            y += line_height + np.random.randint(4, 16)
        
        # 偶尔添加一些 UI 元素（矩形框、按钮等）
        if i % 5 == 0:
            for _ in range(np.random.randint(1, 5)):
                x1 = np.random.randint(0, w - 100)
                y1 = np.random.randint(0, h - 50)
                x2 = x1 + np.random.randint(50, 200)
                y2 = y1 + np.random.randint(20, 50)
                border_color = np.random.randint(100, 200)
                cv2.rectangle(img, (x1, y1), (x2, y2), 
                            (border_color, border_color, border_color), 1)
        
        images.append(img)
    
    print(f"生成了 {count} 张合成校准图片")
    return images


# ============================================
# 检测模型量化
# ============================================

def resize_for_det(img: np.ndarray, target_size: int) -> np.ndarray:
    """
    检测模型预处理：resize 到目标尺寸（32 的倍数）
    
    注意：只做 resize，不做归一化（归一化已注入模型）
    输出格式: NHWC BGR u8
    """
    h, w = img.shape[:2]
    
    # 计算缩放比例，最长边 = target_size
    scale = target_size / max(h, w)
    
    # 新尺寸，对齐到 32 的倍数
    new_w = int(np.ceil(w * scale / 32) * 32)
    new_h = int(np.ceil(h * scale / 32) * 32)
    
    # resize（保持 BGR u8）
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    # 添加 batch 维度: [H, W, 3] -> [1, H, W, 3]
    return np.expand_dims(resized, axis=0)


def quantize_detection_model():
    """量化检测模型"""
    print("=" * 60)
    print("量化检测模型: ch_PP-OCRv4_det_preprocessed")
    print("=" * 60)
    
    model_path = Path(__file__).parent / "ch_PP-OCRv4_det_preprocessed.xml"
    output_path = Path(__file__).parent / "ch_PP-OCRv4_det_int8.xml"
    
    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        return False
    
    # 1. 加载模型
    core = ov.Core()
    model = core.read_model(str(model_path))
    print(f"模型输入: {model.inputs[0].partial_shape}, 类型: {model.inputs[0].element_type}")
    
    # 2. 准备校准数据
    images = collect_calibration_images()
    
    def det_transform_fn(img: np.ndarray) -> np.ndarray:
        """检测模型校准数据转换：只 resize，不归一化"""
        return resize_for_det(img, DET_INPUT_SIZE)
    
    calibration_dataset = nncf.Dataset(images, det_transform_fn)
    
    # 3. 执行量化
    print(f"\n开始 INT8 量化（校准样本: {len(images)} 张）...")
    start_time = time.time()
    
    quantized_model = nncf.quantize(
        model,
        calibration_dataset,
        # PP-OCRv4 det 不是 Transformer，不设置 model_type
        preset=nncf.QuantizationPreset.MIXED,  # 混合精度，平衡速度和精度
        subset_size=min(len(images), 300),      # 校准子集大小
        fast_bias_correction=True,              # 快速偏置校正
    )
    
    elapsed = time.time() - start_time
    print(f"✅ 检测模型量化完成，耗时: {elapsed:.1f}s")
    
    # 4. 保存
    ov.save_model(quantized_model, str(output_path))
    
    # 5. 对比大小
    original_bin = model_path.with_suffix('.bin')
    quantized_bin = output_path.with_suffix('.bin')
    if original_bin.exists() and quantized_bin.exists():
        orig_size = original_bin.stat().st_size / 1024 / 1024
        quant_size = quantized_bin.stat().st_size / 1024 / 1024
        print(f"   原始大小: {orig_size:.2f} MB")
        print(f"   量化后:   {quant_size:.2f} MB ({quant_size/orig_size*100:.1f}%)")
    
    print(f"✅ 已保存: {output_path}")
    return True


# ============================================
# 识别模型量化
# ============================================

def crop_text_regions(images: list[np.ndarray]) -> list[np.ndarray]:
    """
    从图片中裁剪出模拟的文字区域，用于识别模型校准
    
    模拟 Rust 端的文字裁剪逻辑：
    - 高度固定 48
    - 宽度按原始比例缩放，然后对齐到桶宽度
    """
    crops = []
    
    for img in images:
        h, w = img.shape[:2]
        
        # 从每张图中随机裁剪 3-8 个文字区域
        num_crops = np.random.randint(3, 9)
        for _ in range(num_crops):
            # 随机裁剪区域（模拟文字行）
            crop_h = np.random.randint(16, min(60, h))
            crop_w = np.random.randint(50, min(600, w))
            y = np.random.randint(0, max(1, h - crop_h))
            x = np.random.randint(0, max(1, w - crop_w))
            
            crop = img[y:y+crop_h, x:x+crop_w]
            
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                crops.append(crop)
    
    return crops


def resize_for_rec(crop: np.ndarray, target_height: int = 48) -> np.ndarray:
    """
    识别模型预处理：resize 到固定高度，宽度按比例缩放
    
    注意：只做 resize，不做归一化（归一化已注入模型）
    输出格式: NHWC BGR u8 [1, 48, W, 3]
    """
    h, w = crop.shape[:2]
    
    # 按比例缩放到目标高度
    scale = target_height / h
    new_w = max(1, int(w * scale))
    
    # 对齐到桶宽度（取最近的桶）
    bucket_w = new_w
    for bw in REC_WIDTH_BUCKETS:
        if new_w <= bw:
            bucket_w = bw
            break
    else:
        bucket_w = REC_WIDTH_BUCKETS[-1]
    
    # resize
    resized = cv2.resize(crop, (bucket_w, target_height), interpolation=cv2.INTER_LINEAR)
    
    # 添加 batch 维度
    return np.expand_dims(resized, axis=0)


def quantize_recognition_model():
    """量化识别模型"""
    print("\n" + "=" * 60)
    print("量化识别模型: ch_PP-OCRv4_rec_preprocessed")
    print("=" * 60)
    
    model_path = Path(__file__).parent / "ch_PP-OCRv4_rec_preprocessed.xml"
    output_path = Path(__file__).parent / "ch_PP-OCRv4_rec_int8.xml"
    
    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        return False
    
    # 1. 加载模型
    core = ov.Core()
    model = core.read_model(str(model_path))
    print(f"模型输入: {model.inputs[0].partial_shape}, 类型: {model.inputs[0].element_type}")
    
    # 2. 准备校准数据（从完整图片中裁剪文字区域）
    images = collect_calibration_images()
    crops = crop_text_regions(images)
    print(f"生成了 {len(crops)} 个文字区域裁剪用于校准")
    
    def rec_transform_fn(crop: np.ndarray) -> np.ndarray:
        """识别模型校准数据转换：resize 到固定高度"""
        return resize_for_rec(crop, REC_INPUT_HEIGHT)
    
    calibration_dataset = nncf.Dataset(crops, rec_transform_fn)
    
    # 3. 执行量化
    print(f"\n开始 INT8 量化（校准样本: {len(crops)} 个裁剪）...")
    start_time = time.time()
    
    quantized_model = nncf.quantize(
        model,
        calibration_dataset,
        model_type=nncf.ModelType.TRANSFORMER,  # PP-OCRv4 rec 包含 SVTR (类 Transformer)
        preset=nncf.QuantizationPreset.MIXED,   # 混合精度，保留敏感层为 FP16
        subset_size=min(len(crops), 300),
        fast_bias_correction=True,
    )
    
    elapsed = time.time() - start_time
    print(f"✅ 识别模型量化完成，耗时: {elapsed:.1f}s")
    
    # 4. 保存
    ov.save_model(quantized_model, str(output_path))
    
    # 5. 对比大小
    original_bin = model_path.with_suffix('.bin')
    quantized_bin = output_path.with_suffix('.bin')
    if original_bin.exists() and quantized_bin.exists():
        orig_size = original_bin.stat().st_size / 1024 / 1024
        quant_size = quantized_bin.stat().st_size / 1024 / 1024
        print(f"   原始大小: {orig_size:.2f} MB")
        print(f"   量化后:   {quant_size:.2f} MB ({quant_size/orig_size*100:.1f}%)")
    
    print(f"✅ 已保存: {output_path}")
    return True


# ============================================
# 基准测试
# ============================================

def benchmark(model_path: str, input_data: np.ndarray, num_runs: int = 50) -> float:
    """运行基准测试，返回平均推理时间(ms)"""
    core = ov.Core()
    compiled = core.compile_model(model_path, "CPU",
                                  config={"PERFORMANCE_HINT": "LATENCY"})
    infer_request = compiled.create_infer_request()
    
    # 预热
    for _ in range(5):
        infer_request.infer({0: input_data})
    
    # 计时
    times = []
    for _ in range(num_runs):
        start = time.perf_counter()
        infer_request.infer({0: input_data})
        times.append((time.perf_counter() - start) * 1000)
    
    return np.mean(times)


def run_benchmark():
    """对比量化前后的推理速度"""
    print("\n" + "=" * 60)
    print("基准测试：量化前后对比")
    print("=" * 60)
    
    # 检测模型基准
    det_orig = Path(__file__).parent / "ch_PP-OCRv4_det_preprocessed.xml"
    det_int8 = Path(__file__).parent / "ch_PP-OCRv4_det_int8.xml"
    
    if det_orig.exists() and det_int8.exists():
        # 创建测试输入 [1, 640, 640, 3] u8
        det_input = np.random.randint(0, 256, (1, 640, 640, 3), dtype=np.uint8)
        
        print("\n检测模型 (640x640):")
        orig_time = benchmark(str(det_orig), det_input)
        int8_time = benchmark(str(det_int8), det_input)
        speedup = orig_time / int8_time
        print(f"  FP16 原始: {orig_time:.2f} ms")
        print(f"  INT8 量化: {int8_time:.2f} ms")
        print(f"  加速比:    {speedup:.2f}x")
    
    # 识别模型基准
    rec_orig = Path(__file__).parent / "ch_PP-OCRv4_rec_preprocessed.xml"
    rec_int8 = Path(__file__).parent / "ch_PP-OCRv4_rec_int8.xml"
    
    if rec_orig.exists() and rec_int8.exists():
        # 创建测试输入 [1, 48, 320, 3] u8
        rec_input = np.random.randint(0, 256, (1, 48, 320, 3), dtype=np.uint8)
        
        print("\n识别模型 (48x320):")
        orig_time = benchmark(str(rec_orig), rec_input)
        int8_time = benchmark(str(rec_int8), rec_input)
        speedup = orig_time / int8_time
        print(f"  FP16 原始: {orig_time:.2f} ms")
        print(f"  INT8 量化: {int8_time:.2f} ms")
        print(f"  加速比:    {speedup:.2f}x")


# ============================================
# 主流程
# ============================================

def main():
    print("PP-OCRv4 INT8 量化工具")
    print(f"OpenVINO 版本: {ov.__version__}")
    print(f"NNCF 版本: {nncf.__version__}")
    print()
    
    # 创建校准图片目录
    CALIBRATION_DIR.mkdir(exist_ok=True)
    
    success = True
    
    # 量化检测模型
    if not quantize_detection_model():
        success = False
    
    # 量化识别模型
    if not quantize_recognition_model():
        success = False
    
    # 运行基准测试
    if success:
        run_benchmark()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 量化完成！")
        print()
        print("生成的文件：")
        print("  - ch_PP-OCRv4_det_int8.xml / .bin （检测模型 INT8）")
        print("  - ch_PP-OCRv4_rec_int8.xml / .bin （识别模型 INT8）")
        print()
        print("下一步：")
        print("  1. 确认基准测试结果，检查加速比是否满意")
        print("  2. 用实际截图测试 INT8 模型的 OCR 精度")
        print("  3. 满意后，将 INT8 模型替换掉当前的 preprocessed 模型：")
        print("     - 重命名 ch_PP-OCRv4_det_int8 -> ch_PP-OCRv4_det_preprocessed")
        print("     - 重命名 ch_PP-OCRv4_rec_int8 -> ch_PP-OCRv4_rec_preprocessed")
        print("  4. 重新编译 Rust 项目（cargo build --release）")
        print()
        print("⚠️  如果精度下降明显，可以尝试：")
        print("  - 增加校准图片数量（建议 300 张实际截图）")
        print("  - 将 preset 改为 MIXED（已默认使用）")
        print("  - 使用 nncf.quantize_with_accuracy_control() 精确控制精度损失")
    else:
        print("❌ 量化失败，请检查错误信息")
    print("=" * 60)


if __name__ == "__main__":
    main()
