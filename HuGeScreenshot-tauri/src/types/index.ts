/**
 * 类型定义统一导出
 *
 * 使用方式:
 * import type { CaptureResult, AnnotationObject, OcrResult } from '@/types'
 */

// 截图相关
export type {
  Rect,
  CaptureResult,
  MonitorInfo,
  WindowInfo,
  SelectionRegion,
  CaptureMode,
  CaptureState,
} from './screenshot'

// 标注相关
export type {
  AnnotationTool,
  Point,
  AnnotationStyle,
  AnnotationObject,
} from './annotation'
export { DEFAULT_ANNOTATION_STYLE } from './annotation'

// 服务类型
export type {
  // OCR
  OcrRecognizeParams,
  OcrTextBox,
  OcrResult,
  // 翻译
  TranslateProvider,
  TranslateParams,
  TranslateResult,
  // 录屏
  RecordStartParams,
  RecordingState,
  RecordResult,
  // 文件转换
  FileToMarkdownParams,
  FileToMarkdownResult,
  UrlToMarkdownParams,
  UrlToMarkdownResult,
  MarkdownToFileFormat,
  MarkdownToFileParams,
  MarkdownToFileResult,
  MarkdownFileToFileParams,
} from './sidecar'

// 配置
export type {
  GeneralConfig,
  HotkeyConfig,
  ScreenshotConfig,
  AnnotationConfig,
  OcrEngine,
  OcrConfig,
  RecordingConfig,
  PinImageConfig,
  MouseHighlightConfig,
  MouseHighlightTheme,
  MouseHighlightThemeColors,
  WebToMarkdownConfig,
  FileToMarkdownConfig,
  FileToMarkdownEngine,
  NotificationConfig,
  UpdateConfig,
  AdvancedConfig,
  AppConfig,
} from './config'
export { DEFAULT_CONFIG, MOUSE_HIGHLIGHT_THEMES, MOUSE_HIGHLIGHT_LIMITS } from './config'

// 历史记录
export type {
  HistoryItem,
  HistoryMetadata,
  HistorySearchParams,
  HistorySearchResult,
  HistoryStats,
} from './history'
