/**
 * 文件搜索组件导出
 *
 * @module FileSearch
 */

export { default as SearchDialog } from './SearchDialog.vue'
export { default as HighlightedText } from './HighlightedText.vue'

// 类型导出
export interface FileSearchResult {
  fileId: string
  name: string
  path: string
  size: number
  modified: string
  isDirectory: boolean
  score: number
  matchIndices: [number, number][]
}

export interface FileSearchQuery {
  keyword: string
  matchMode: 'exact' | 'wildcard' | 'fuzzy' | 'regex'
  filters?: {
    extensions?: string[]
    minSize?: number
    maxSize?: number
    modifiedAfter?: string
    modifiedBefore?: string
    includeDirectories?: boolean
    volumes?: string[]
  }
  sortBy: 'relevance' | 'name' | 'path' | 'size' | 'modified'
  sortOrder: 'asc' | 'desc'
  limit: number
  offset: number
}

export interface FileSearchResponse {
  results: FileSearchResult[]
  totalCount: number
  searchTimeMs: number
}

export interface FileSearchServiceStatus {
  state: 'starting' | 'running' | 'scanning' | 'stopping' | 'stopped'
  indexedFiles?: number
  lastUpdate?: string
  scanProgress?: number
}
