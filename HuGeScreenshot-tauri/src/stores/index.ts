/**
 * Pinia Stores 统一导出
 *
 * 使用方式:
 * import { useScreenshotStore } from '@/stores'
 */

export { useHistoryStore } from './history'
export { useSettingsStore } from './settings'
export { useWorkbenchStore } from './workbench'
export type { DateFilter, OcrStatus, FormatType, OcrStats } from './workbench'
export { useFileSearchStore } from './fileSearch'
export type { FileSearchResult, FileSearchState } from './fileSearch'
