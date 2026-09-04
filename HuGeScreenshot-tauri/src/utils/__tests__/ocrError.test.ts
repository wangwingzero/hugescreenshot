import { describe, expect, it } from 'vitest'
import { LOCAL_OCR_RUNTIME_ERROR_MESSAGE, formatOcrUserError } from '../ocrError'

describe('formatOcrUserError', () => {
  it('turns OpenVINO DLL load failures into an actionable runtime message', () => {
    const raw =
      'OCR 识别错误: OCR 引擎初始化失败: 模型加载失败: OpenVINO Core 初始化失败: Loading(SystemFailure("the shared library at D:\\虎哥截图\\openvino\\openvino_c.dll could not be opened: LoadLibraryExW failed"))'

    expect(formatOcrUserError(raw)).toBe(LOCAL_OCR_RUNTIME_ERROR_MESSAGE)
  })

  it('keeps non-runtime OCR failures readable without duplicate prefixes', () => {
    const raw = 'OCR 识别错误: OCR 识别失败: 图像文件不存在'

    expect(formatOcrUserError(raw)).toBe('OCR 识别失败: 图像文件不存在')
  })
})
