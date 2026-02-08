import sys
import json
import base64
import os
import traceback

# 设置标准输出编码为 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def log(msg):
    # 打印到 stderr 以免干扰 stdout 的 JSON 输出
    print(f"[OCR-Runner] {msg}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        log("Usage: python ocr_runner.py <image_path>")
        return

    image_path = sys.argv[1]
    log(f"Processing: {image_path}")

    try:
        from rapidocr_onnxruntime import RapidOCR

        # 初始化
        ocr = RapidOCR()

        # 运行识别
        result, elapse = ocr(image_path)

        # 确保 elapse 是浮点数
        elapsed_ms = float(elapse) * 1000 if elapse else 0.0

        output = {
            "success": True,
            "text": "",
            "boxes": [],
            "elapsed_ms": elapsed_ms
        }

        if result:
            # 调试：打印第一行结果的结构
            # log(f"First line structure: {result[0]}")

            output_boxes = []
            all_scores = []
            all_txts = []

            for line in result:
                # line通常是 [box_points, text, score]
                # 但有时 score 可能是 list

                box_points = line[0]
                text_content = str(line[1])
                score_val = line[2]

                # 兼容性处理：处理 score 是列表的情况
                if isinstance(score_val, list):
                    try:
                        # 尝试转换为浮点数列表并取平均
                        vals = [float(v) for v in score_val]
                        confidence = sum(vals) / len(vals) if vals else 0.0
                    except:
                        confidence = 0.0
                else:
                    try:
                        confidence = float(score_val)
                    except:
                        confidence = 0.0

                all_scores.append(confidence)
                all_txts.append(text_content)

                output_boxes.append({
                    "text": text_content,
                    "confidence": confidence,
                    "box": box_points
                })

            output["text"] = "\n".join(all_txts)
            output["average_score"] = sum(all_scores) / len(all_scores) if all_scores else 0.0
            output["boxes"] = output_boxes

        # 核心：将结果以 JSON 格式打印到标准输出
        json_output = json.dumps(output, ensure_ascii=False)
        print(json_output)
        log(f"OCR success. Text len: {len(output['text'])}")

    except ImportError:
        err = "Module 'rapidocr_onnxruntime' not found. Please pip install it."
        log(err)
        print(json.dumps({"success": False, "error": err}))
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}"
        log(f"Error: {traceback.format_exc()}")
        print(json.dumps({"success": False, "error": err}))

if __name__ == "__main__":
    main()
