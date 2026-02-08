import sys
import json
import base64
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import traceback

# 尝试导入 RapidOCR
try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
    print("RapidOCR init success")
except Exception as e:
    print(f"RapidOCR init failed: {e}")
    ocr_engine = None

class OCRHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/api/ocr':
            self.send_error(404)
            return

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        try:
            data = json.loads(post_data.decode('utf-8'))
            base64_str = data.get('base64', '')

            if not base64_str:
                self.send_response(400)
                self.end_headers()
                return

            # 保存临时图片
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                tmp.write(base64.b64decode(base64_str))
                tmp_path = tmp.name

            # 识别
            if ocr_engine:
                result, elapse = ocr_engine(tmp_path)
            else:
                result = None

            # 清理
            try:
                os.remove(tmp_path)
            except:
                pass

            # 构造 Umi-OCR 兼容格式
            response = {
                "code": 100 if result else 101,
                "data": []
            }

            if result:
                for line in result:
                    # line: [box, text, score]
                    # score 可能是 list，取平均
                    score_val = line[2]
                    if isinstance(score_val, list):
                        try:
                            score = sum(map(float, score_val)) / len(score_val)
                        except:
                            score = 0.0
                    else:
                        score = float(score_val)

                    response["data"].append({
                        "text": str(line[1]),
                        "score": score,
                        "box": line[0]  # [[x,y],...]
                    })
            else:
                response["data"] = "No text found"

            # 发送响应
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()
            err_resp = {"code": 300, "data": str(e)}
            self.wfile.write(json.dumps(err_resp).encode('utf-8'))

    def log_message(self, format, *args):
        return # 静默输出

def run(server_class=HTTPServer, handler_class=OCRHandler, port=12240):
    server_address = ('127.0.0.1', port)
    httpd = server_class(server_address, handler_class)
    print(f"OCR Server running on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    # 使用 12240 端口，避免与真正的 Umi-OCR (1224) 冲突
    run()
