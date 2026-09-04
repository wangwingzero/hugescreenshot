/**
 * 文件搜索状态 Store
 *
 * 管理文件搜索对话框的状态持久化：
 * - 保存上次搜索查询
 * - 保存搜索结果（内存级）
 * - 重新打开时恢复状态
 *
 * @validates Requirements 8.5
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

/**
 * 搜索结果项
 */
export interface FileSearchResult {
  /** 文件唯一 ID */
  fileId: string
  /** 文件名 */
  name: string
  /** 完整路径 */
  path: string
  /** 文件大小（字节） */
  size: number
  /** 修改时间 */
  modified: string
  /** 是否为目录 */
  isDirectory: boolean
  /** 匹配分数 */
  score: number
  /** 匹配位置索引 */
  matchIndices: [number, number][]
}

/**
 * 搜索状态
 */
export interface FileSearchState {
  /** 搜索关键词 */
  query: string
  /** 搜索结果 */
  results: FileSearchResult[]
  /** 结果总数 */
  totalCount: number
  /** 搜索耗时 (ms) */
  searchTimeMs: number
  /** 选中的索引 */
  selectedIndex: number
  /** 最后搜索时间 */
  lastSearchTime: number
}

/** 状态过期时间（5分钟） */
const STATE_EXPIRY_MS = 5 * 60 * 1000

/** localStorage key */
const STORAGE_KEY = 'file-search-state'

/**
 * 文件搜索 Store
 */
export const useFileSearchStore = defineStore('fileSearch', () => {
  // ============================================
  // State
  // ============================================

  /** 搜索关键词 */
  const query = ref('')

  /** 搜索结果 */
  const results = ref<FileSearchResult[]>([])

  /** 结果总数 */
  const totalCount = ref(0)

  /** 搜索耗时 */
  const searchTimeMs = ref(0)

  /** 选中的索引 */
  const selectedIndex = ref(0)

  /** 最后搜索时间 */
  const lastSearchTime = ref(0)

  // ============================================
  // Computed
  // ============================================

  /** 是否有有效的搜索状态 */
  const hasValidState = computed(() => {
    if (!query.value || results.value.length === 0) {
      return false
    }
    // 检查状态是否过期
    const now = Date.now()
    return now - lastSearchTime.value < STATE_EXPIRY_MS
  })

  /** 当前选中的结果 */
  const selectedResult = computed(() => {
    if (selectedIndex.value >= 0 && selectedIndex.value < results.value.length) {
      return results.value[selectedIndex.value]
    }
    return null
  })

  // ============================================
  // Methods
  // ============================================

  /**
   * 保存搜索状态
   */
  function saveState(
    newQuery: string,
    newResults: FileSearchResult[],
    newTotalCount: number,
    newSearchTimeMs: number,
    newSelectedIndex: number = 0
  ): void {
    query.value = newQuery
    results.value = newResults
    totalCount.value = newTotalCount
    searchTimeMs.value = newSearchTimeMs
    selectedIndex.value = newSelectedIndex
    lastSearchTime.value = Date.now()

    // 保存到 localStorage（仅保存查询，不保存结果以节省空间）
    saveToStorage()
  }

  /**
   * 更新选中索引
   */
  function setSelectedIndex(index: number): void {
    if (index >= 0 && index < results.value.length) {
      selectedIndex.value = index
    }
  }

  /**
   * 清除搜索状态
   */
  function clearState(): void {
    query.value = ''
    results.value = []
    totalCount.value = 0
    searchTimeMs.value = 0
    selectedIndex.value = 0
    lastSearchTime.value = 0
    clearStorage()
  }

  /**
   * 获取当前状态快照
   */
  function getState(): FileSearchState {
    return {
      query: query.value,
      results: results.value,
      totalCount: totalCount.value,
      searchTimeMs: searchTimeMs.value,
      selectedIndex: selectedIndex.value,
      lastSearchTime: lastSearchTime.value,
    }
  }

  /**
   * 恢复状态
   */
  function restoreState(state: FileSearchState): void {
    query.value = state.query
    results.value = state.results
    totalCount.value = state.totalCount
    searchTimeMs.value = state.searchTimeMs
    selectedIndex.value = state.selectedIndex
    lastSearchTime.value = state.lastSearchTime
  }

  /**
   * 保存到 localStorage
   * 只保存查询关键词，不保存结果（结果可能很大）
   */
  function saveToStorage(): void {
    try {
      const data = {
        query: query.value,
        lastSearchTime: lastSearchTime.value,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.error('保存文件搜索状态失败:', e)
    }
  }

  /**
   * 从 localStorage 加载
   */
  function loadFromStorage(): string {
    try {
      const data = localStorage.getItem(STORAGE_KEY)
      if (data) {
        const parsed = JSON.parse(data)
        // 检查是否过期
        const now = Date.now()
        if (now - parsed.lastSearchTime < STATE_EXPIRY_MS) {
          return parsed.query || ''
        }
      }
    } catch (e) {
      console.error('加载文件搜索状态失败:', e)
    }
    return ''
  }

  /**
   * 清除 localStorage
   */
  function clearStorage(): void {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch (e) {
      console.error('清除文件搜索状态失败:', e)
    }
  }

  /**
   * 初始化 - 从 localStorage 恢复查询关键词
   */
  function initialize(): string {
    const savedQuery = loadFromStorage()
    if (savedQuery) {
      query.value = savedQuery
    }
    return savedQuery
  }

  return {
    // 状态
    query,
    results,
    totalCount,
    searchTimeMs,
    selectedIndex,
    lastSearchTime,

    // 计算属性
    hasValidState,
    selectedResult,

    // 方法
    saveState,
    setSelectedIndex,
    clearState,
    getState,
    restoreState,
    initialize,
  }
})
