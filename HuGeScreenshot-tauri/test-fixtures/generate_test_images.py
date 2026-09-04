"""
生成测试夹具图片

运行: python generate_test_images.py
依赖: pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """尝试加载字体，优先使用微软雅黑"""
    font_candidates = [
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",    # 黑体
        "C:/Windows/Fonts/simsun.ttc",    # 宋体
        "C:/Windows/Fonts/arial.ttf",     # Arial
        "msyh.ttc",
        "SimHei",
        "Arial",
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except (IOError, OSError):
            continue
    # 回退到默认字体
    return ImageFont.load_default()


def create_simple_image():
    """1. simple.png - 100x100 简单图片"""
    img = Image.new("RGB", (100, 100), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 90, 90], outline="#333333", width=2)
    draw.text((25, 40), "TEST", fill="#000000", font=get_font(20))
    img.save(OUTPUT_DIR / "simple.png")
    print("✅ simple.png - 100x100 简单测试图")


def create_hdpi_image():
    """2. hdpi.png - 200x200 物理像素 (模拟 100x100 @ 2x DPR)"""
    img = Image.new("RGB", (200, 200), "#F0F0F0")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 180, 180], outline="#0066CC", width=4)
    draw.text((50, 80), "HiDPI", fill="#0066CC", font=get_font(40))
    img.save(OUTPUT_DIR / "hdpi.png")
    print("✅ hdpi.png - 200x200 高DPI测试图 (2x)")


def create_multiline_image():
    """3. multiline.png - 400x200 多行英文文字"""
    img = Image.new("RGB", (400, 200), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    lines = [
        "Hello, World!",
        "This is line 2.",
        "Third line here.",
        "Numbers: 12345",
    ]
    font = get_font(24)
    for i, line in enumerate(lines):
        draw.text((20, 20 + i * 40), line, fill="#000000", font=font)
    img.save(OUTPUT_DIR / "multiline.png")
    print("✅ multiline.png - 400x200 多行英文")


def create_chinese_image():
    """4. chinese.png - 300x100 中文文字"""
    img = Image.new("RGB", (300, 100), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.text((20, 35), "你好，世界！", fill="#000000", font=get_font(28))
    img.save(OUTPUT_DIR / "chinese.png")
    print("✅ chinese.png - 300x100 中文测试")


def create_mixed_image():
    """5. mixed.png - 400x150 中英混合"""
    img = Image.new("RGB", (400, 150), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    font = get_font(24)
    draw.text((20, 20), "Hello 你好", fill="#000000", font=font)
    draw.text((20, 60), "Version 版本: v3.0", fill="#333333", font=font)
    draw.text((20, 100), "2026-01-24", fill="#666666", font=font)
    img.save(OUTPUT_DIR / "mixed.png")
    print("✅ mixed.png - 400x150 中英混合")


def create_edge_cases():
    """6. 额外的边缘情况测试图"""

    # 6.1 空白图片 - 测试空内容处理
    img = Image.new("RGB", (100, 100), "#FFFFFF")
    img.save(OUTPUT_DIR / "blank.png")
    print("✅ blank.png - 100x100 空白图")

    # 6.2 单字符 - 最小识别单元
    img = Image.new("RGB", (50, 50), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.text((15, 10), "A", fill="#000000", font=get_font(30))
    img.save(OUTPUT_DIR / "single_char.png")
    print("✅ single_char.png - 50x50 单字符")

    # 6.3 低对比度 - 测试识别边界
    img = Image.new("RGB", (200, 50), "#E0E0E0")
    draw = ImageDraw.Draw(img)
    draw.text((20, 12), "Low Contrast", fill="#A0A0A0", font=get_font(20))
    img.save(OUTPUT_DIR / "low_contrast.png")
    print("✅ low_contrast.png - 200x50 低对比度")

    # 6.4 带标点和特殊字符
    img = Image.new("RGB", (400, 80), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.text((20, 25), "Email: test@example.com | ￥100.00", fill="#000000", font=get_font(22))
    img.save(OUTPUT_DIR / "special_chars.png")
    print("✅ special_chars.png - 400x80 特殊字符")


def main():
    print(f"📁 输出目录: {OUTPUT_DIR.absolute()}\n")

    create_simple_image()
    create_hdpi_image()
    create_multiline_image()
    create_chinese_image()
    create_mixed_image()
    create_edge_cases()

    print(f"\n🎉 共生成 {len(list(OUTPUT_DIR.glob('*.png')))} 张测试图片")


if __name__ == "__main__":
    main()
