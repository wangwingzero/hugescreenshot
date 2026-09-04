# 测试夹具 (Test Fixtures)

本目录包含 Tauri + Rust + Vue + Python 项目的测试数据。

## 目录结构

```
test-fixtures/
├── images/              # 测试用截图样本
│   ├── simple.png       # 简单图片 (100x100)
│   ├── hdpi.png         # 高 DPI 图片 (200x200 @ 2x)
│   ├── multiline.png    # 多行文字图片
│   ├── chinese.png      # 中文文字图片
│   ├── mixed.png        # 中英混合图片
│   ├── blank.png        # 空白图片
│   ├── single_char.png  # 单字符图片
│   ├── low_contrast.png # 低对比度图片
│   └── special_chars.png # 特殊字符图片
├── ocr/                 # OCR 测试用例
│   └── test_cases.json  # OCR 测试场景定义
├── ocr-samples/         # OCR 测试用文本样本
│   ├── english.txt
│   ├── chinese.txt
│   └── mixed.txt
├── translation/         # 翻译测试用例
│   └── test_cases.json  # 多语言翻译测试
├── screenshot/          # 截图场景测试
│   └── monitor_scenarios.json # 多显示器/高DPI场景
├── annotation/          # 标注工具测试
│   └── test_cases.json  # 形状/文字/隐私工具测试
├── hotkey/              # 热键测试
│   └── test_cases.json  # 热键注册/冲突测试
├── payloads/            # Sidecar IPC 请求样本
│   ├── ocr_request.json
│   ├── translate_request.json
│   └── anki_request.json
├── responses/           # Sidecar IPC 响应样本
│   ├── ocr_response.json
│   ├── translate_response.json
│   └── error_response.json
├── configs/             # 配置文件样本
│   ├── default_config.json
│   └── hotkey_config.json
├── generate_test_images.py  # 图片生成脚本
└── README.md            # 本文件
```

---

## 测试用例说明

### OCR 测试 (`ocr/test_cases.json`)

| 测试 ID | 说明 | 预期 |
|---------|------|------|
| `ocr_english_simple` | 简单英文 | 识别 "TEST" |
| `ocr_english_multiline` | 多行英文 | 识别 4 行文本 |
| `ocr_chinese` | 中文识别 | 识别 "你好，世界！" |
| `ocr_mixed` | 中英混合 | 识别混合内容 |
| `ocr_blank` | 空白图片 | 返回空结果 |
| `ocr_low_contrast` | 低对比度 | 低置信度识别 |
| `ocr_special_chars` | 特殊字符 | 识别邮箱/金额 |

### 翻译测试 (`translation/test_cases.json`)

| 测试 ID | 说明 | 源语言 | 目标语言 |
|---------|------|--------|----------|
| `translate_en_zh` | 英转中 | en | zh-CN |
| `translate_zh_en` | 中转英 | zh-CN | en |
| `translate_ja_zh` | 日转中 | ja | zh-CN |
| `translate_long_text` | 长文本 | en | zh-CN |
| `translate_empty` | 空文本 | en | zh-CN |
| `translate_mixed` | 混合语言 | auto | zh-CN |

### 截图场景 (`screenshot/monitor_scenarios.json`)

| 场景 ID | 说明 | 显示器数量 |
|---------|------|------------|
| `single_monitor_1080p` | 单屏 1080p | 1 |
| `single_monitor_4k` | 单屏 4K 150% | 1 |
| `dual_monitor_horizontal` | 双屏水平 | 2 |
| `dual_monitor_left_secondary` | 副屏在左（负坐标） | 2 |
| `dual_monitor_mixed_dpr` | 双屏不同 DPR | 2 |
| `triple_monitor` | 三屏配置 | 3 |
| `high_dpi_200` | 200% 缩放 | 1 |

### 标注测试 (`annotation/test_cases.json`)

| 类别 | 测试项 |
|------|--------|
| **形状** | 矩形、椭圆、箭头、直线 |
| **文字** | 英文、中文、多行、样式 |
| **隐私** | 马赛克（细/中/粗）、模糊（轻/中/重） |
| **撤销重做** | 7 步操作序列验证 |

### 热键测试 (`hotkey/test_cases.json`)

| 类别 | 测试项 |
|------|--------|
| **有效热键** | 默认热键、替代方案 |
| **无效热键** | 空字符串、单字母、仅修饰键 |
| **冲突场景** | 同应用、系统、其他应用 |

---

## 使用方式

### Rust (src-tauri/tests/)

```rust
// 使用 include_str! 在编译时加载
const OCR_CASES: &str = include_str!("../../test-fixtures/ocr/test_cases.json");

// 解析 JSON
let cases: serde_json::Value = serde_json::from_str(OCR_CASES).unwrap();

// 或使用 include_bytes! 加载二进制文件
const SIMPLE_IMAGE: &[u8] = include_bytes!("../../test-fixtures/images/simple.png");
```

### Vue/TypeScript (src/__tests__/)

```typescript
// 直接导入 JSON
import ocrCases from '../../../test-fixtures/ocr/test_cases.json';
import monitorScenarios from '../../../test-fixtures/screenshot/monitor_scenarios.json';

// 使用测试用例
describe('OCR', () => {
  ocrCases.ocrTestCases.forEach((testCase) => {
    it(testCase.name, async () => {
      // ...
    });
  });
});
```

### Python (python/tests/)

```python
from pathlib import Path
import json

FIXTURES_DIR = Path(__file__).parent.parent.parent / "test-fixtures"

def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))

# 使用
ocr_cases = load_fixture("ocr/test_cases.json")
for case in ocr_cases["ocrTestCases"]:
    print(f"Running: {case['name']}")
```

---

## 图片说明

| 文件 | 尺寸 | DPR | 用途 |
|------|------|-----|------|
| simple.png | 100x100 | 1x | 基础截图测试 |
| hdpi.png | 200x200 | 2x | 高 DPI 坐标转换测试 |
| multiline.png | 400x200 | 1x | OCR 多行识别测试 |
| chinese.png | 300x100 | 1x | OCR 中文识别测试 |
| mixed.png | 400x150 | 1x | OCR 中英混合测试 |
| blank.png | 100x100 | 1x | 空内容边界测试 |
| single_char.png | 50x50 | 1x | 最小识别单元测试 |
| low_contrast.png | 200x50 | 1x | 低对比度识别测试 |
| special_chars.png | 400x80 | 1x | 特殊字符识别测试 |

---

## 生成测试图片

```bash
# 安装依赖
pip install Pillow

# 生成图片
python generate_test_images.py
```

输出示例：

```
📁 输出目录: D:\screenshot\HuGeScreenshot-tauri\test-fixtures\images

✅ simple.png - 100x100 简单测试图
✅ hdpi.png - 200x200 高DPI测试图 (2x)
✅ multiline.png - 400x200 多行英文
✅ chinese.png - 300x100 中文测试
✅ mixed.png - 400x150 中英混合
✅ blank.png - 100x100 空白图
✅ single_char.png - 50x50 单字符
✅ low_contrast.png - 200x50 低对比度
✅ special_chars.png - 400x80 特殊字符

🎉 共生成 9 张测试图片
```

---

## 注意事项

1. **不要提交大文件** - 图片应保持在 100KB 以内
2. **使用相对路径** - 确保 CI 环境兼容
3. **保持 JSON 格式** - 便于多语言解析
4. **更新本文档** - 添加新测试用例时同步更新

---

## 测试覆盖统计

| 模块 | 测试用例数 | 覆盖场景 |
|------|------------|----------|
| OCR | 9 | 中英文、边界情况、性能 |
| 翻译 | 8 | 多语言、长文本、特殊字符 |
| 截图 | 8 | 多显示器、高DPI、坐标转换 |
| 标注 | 18 | 形状、文字、隐私、撤销重做 |
| 热键 | 12 | 有效/无效/冲突场景 |
| **总计** | **55** | - |
