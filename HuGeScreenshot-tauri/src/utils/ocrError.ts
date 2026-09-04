export const LOCAL_OCR_RUNTIME_ERROR_MESSAGE =
  '本地 OCR 运行库加载失败，请重新安装虎哥截图，或安装 Microsoft Visual C++ 2015-2022 Redistributable x64 后重试'

function toErrorText(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  if (error === null || error === undefined) return ''
  return String(error)
}

export function isLocalOcrRuntimeError(error: unknown): boolean {
  const text = toErrorText(error).toLowerCase()
  return (
    text.includes('本地 ocr 运行库加载失败') ||
    text.includes('openvino core 初始化失败') ||
    text.includes('openvino_c.dll') ||
    text.includes('loadlibraryexw failed') ||
    text.includes('could not be opened') ||
    text.includes('shared library') ||
    text.includes('vcruntime140') ||
    text.includes('msvcp140')
  )
}

export function formatOcrUserError(error: unknown): string {
  if (isLocalOcrRuntimeError(error)) {
    return LOCAL_OCR_RUNTIME_ERROR_MESSAGE
  }

  let text = toErrorText(error).trim()
  while (text.startsWith('OCR 识别错误:')) {
    text = text.slice('OCR 识别错误:'.length).trim()
  }

  return text || 'OCR 识别失败'
}
