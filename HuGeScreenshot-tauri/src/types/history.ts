/**
 * 历史记录类型定义
 * 对应 Rust: src-tauri/src/database/history.rs
 */

/** 历史记录项 */
export interface HistoryItem {
  /** 唯一 ID */
  id: number
  /** 创建时间 (ISO 8601) */
  createdAt: string
  /** 文件路径 */
  filePath: string
  /** 缩略图路径 */
  thumbnailPath?: string
  /** 图片宽度 */
  width: number
  /** 图片高度 */
  height: number
  /** 文件大小 (字节) */
  fileSize?: number
  /** OCR 识别文本 */
  ocrText?: string
  /** 标签 */
  tags: string[]
  /** 元数据 */
  metadata: HistoryMetadata
  /** 内容类型: image 或 text */
  contentType?: string
  /** 文字内容（仅文字类型有值） */
  textContent?: string
  /** 是否钉住 */
  isPinned?: boolean
}

/** 历史记录元数据 */
export interface HistoryMetadata {
  /** 截图模式 */
  captureMode?: string
  /** 显示器 ID */
  monitorId?: number
  /** 应用名称 (窗口截图) */
  appName?: string
  /** 窗口标题 (窗口截图) */
  windowTitle?: string
  /** 是否有标注 */
  hasAnnotations?: boolean
  /** 其他自定义字段 */
  [key: string]: unknown
}

/** 历史记录搜索参数 */
export interface HistorySearchParams {
  /** 搜索关键词 (OCR 文本、标签) */
  query?: string
  /** 开始日期 */
  startDate?: string
  /** 结束日期 */
  endDate?: string
  /** 标签筛选 */
  tags?: string[]
  /** 排序字段 */
  sortBy?: 'createdAt' | 'fileSize'
  /** 排序方向 */
  sortOrder?: 'asc' | 'desc'
  /** 分页: 偏移量 */
  offset?: number
  /** 分页: 数量 */
  limit?: number
}

/** 历史记录搜索结果 */
export interface HistorySearchResult {
  /** 结果列表 */
  items: HistoryItem[]
  /** 总数量 */
  total: number
  /** 是否还有更多 */
  hasMore: boolean
}

/** 历史记录统计 */
export interface HistoryStats {
  /** 总数量 */
  totalCount: number
  /** 总大小 (字节) */
  totalSize: number
  /** 今日数量 */
  todayCount: number
  /** 本周数量 */
  weekCount: number
  /** 本月数量 */
  monthCount: number
}
