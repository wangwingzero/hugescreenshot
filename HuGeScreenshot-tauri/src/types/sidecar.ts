/**
 * Tauri 命令请求/响应类型定义
 * 对应 Rust: src-tauri/src/commands/
 */

// ============================================
// OCR 服务
// ============================================

/** OCR 识别请求参数 */
export interface OcrRecognizeParams {
  /** 图像文件路径 */
  imagePath: string
  /** 语言 (可选) */
  language?: string
  /** OCR 引擎 (可选) */
  engine?: string
}

/** OCR 文本框 */
export interface OcrTextBox {
  /** 识别的文字 */
  text: string
  /** 置信度 (0-1) */
  confidence: number
  /** 边界框坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] */
  box: [number, number][]
}

/** OCR 识别结果 */
export interface OcrResult {
  /** 完整文本 */
  text: string
  /** 文本框列表 */
  boxes: OcrTextBox[]
  /** 耗时 (秒) */
  elapse: number
  /** 使用的 OCR 引擎 */
  engine?: string
}

// ============================================
// 翻译服务
// ============================================

/** 翻译提供商 */
export type TranslateProvider = 'google' | 'deepl' | 'baidu'

/** 翻译请求参数 */
export interface TranslateParams {
  /** 待翻译文本 */
  text: string
  /** 目标语言 */
  targetLang: string
  /** 源语言 (可选，自动检测) */
  sourceLang?: string
  /** 提供商 */
  provider?: TranslateProvider
}

/** 翻译结果 */
export interface TranslateResult {
  /** 翻译后的文本 */
  translatedText: string
  /** 检测到的源语言 */
  sourceLang: string
  /** 目标语言 */
  targetLang: string
  /** 使用的提供商 */
  provider: TranslateProvider
}

// ============================================
// 录屏服务
// ============================================

/** 录屏请求参数 */
export interface RecordStartParams {
  /** 录制区域 (null 表示全屏) */
  region?: {
    x: number
    y: number
    width: number
    height: number
  }
  /** 帧率 */
  fps?: number
  /** 是否录制系统音频 */
  systemAudio?: boolean
  /** 是否录制麦克风 */
  micAudio?: boolean
  /** 输出路径 */
  outputPath: string
}

/** 录屏状态 */
export type RecordingState = 'idle' | 'recording' | 'paused' | 'encoding'

/** 录屏结果 */
export interface RecordResult {
  /** 输出文件路径 */
  outputPath: string
  /** 时长 (秒) */
  duration: number
  /** 文件大小 (字节) */
  fileSize: number
}

// ============================================
// 文件转换服务
// ============================================

/** 文件转 Markdown 参数 */
export interface FileToMarkdownParams {
  /** 文件路径 */
  file_path: string
  /** 转换选项 */
  options?: {
    /** 是否启用 OCR (用于图片) */
    enable_ocr?: boolean
  }
}

/** 文件转 Markdown 结果 */
export interface FileToMarkdownResult {
  /** 是否成功 */
  success: boolean
  /** 原文件路径 */
  file_path: string
  /** Markdown 内容 */
  markdown: string
  /** 文档标题 */
  title: string
  /** 耗时 (秒) */
  elapse: number
}

/** 网页转 Markdown 参数 */
export interface UrlToMarkdownParams {
  /** 网页 URL */
  url: string
  /** 转换选项 */
  options?: {
    /** 抓取引擎 */
    engine?: 'auto' | 'trafilatura' | 'browser'
    /** 等待策略 */
    wait_until?: 'load' | 'domcontentloaded' | 'networkidle'
    /** 超时时间 (毫秒) */
    timeout?: number
    /** 正文选择器 */
    content_selector?: string
    /** 等待特定元素 */
    wait_for_selector?: string
    /** 是否保存图片 */
    save_images?: boolean
    /** 图片保存目录 */
    images_dir?: string
  }
}

/** 网页转 Markdown 结果 */
export interface UrlToMarkdownResult {
  /** 是否成功 */
  success: boolean
  /** 原 URL */
  url: string
  /** 页面标题 */
  title: string
  /** Markdown 内容 */
  markdown: string
  /** 图片列表 */
  images: Array<{
    url: string
    local_path: string
    alt: string
  }>
  /** 耗时 (秒) */
  elapse: number
}

/** Markdown 转文件格式 */
export type MarkdownToFileFormat = 'docx' | 'pdf' | 'html' | 'odt' | 'rtf'

/** Markdown 转文件参数 */
export interface MarkdownToFileParams {
  /** Markdown 内容 */
  markdown: string
  /** 输出文件路径 */
  output_path: string
  /** 输出格式 */
  format: MarkdownToFileFormat
  /** 转换选项 */
  options?: {
    /** 参考文档模板 (用于 docx) */
    reference_doc?: string
    /** CSS 文件路径 (用于 html/pdf) */
    css?: string
    /** 是否生成目录 */
    toc?: boolean
    /** 是否生成独立文档 */
    standalone?: boolean
  }
}

/** Markdown 转文件结果 */
export interface MarkdownToFileResult {
  /** 是否成功 */
  success: boolean
  /** 输出文件路径 */
  output_path: string
  /** 输出格式 */
  format: string
  /** 耗时 (秒) */
  elapse: number
}

/** Markdown 文件转文件参数 */
export interface MarkdownFileToFileParams {
  /** Markdown 文件路径 */
  markdown_path: string
  /** 输出文件路径 */
  output_path: string
  /** 输出格式 */
  format: MarkdownToFileFormat
  /** 转换选项 */
  options?: MarkdownToFileParams['options']
}
