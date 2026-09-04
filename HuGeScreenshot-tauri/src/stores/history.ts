/**
 * 历史记录状态管理 Store
 *
 * 管理截图历史记录：
 * - 历史记录列表
 * - 搜索和过滤
 * - 统计信息
 *
 * @validates Requirements 14.1, 14.2, 14.3, 14.4
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type {
  HistoryItem,
  HistorySearchParams,
  HistorySearchResult,
  HistoryStats,
} from '@/types'

export const useHistoryStore = defineStore('history', () => {
  // ============================================
  // State
  // ============================================

  /** 历史记录列表 */
  const items = ref<HistoryItem[]>([])

  /** 当前搜索参数 */
  const searchParams = ref<HistorySearchParams>({
    sortBy: 'createdAt',
    sortOrder: 'desc',
    offset: 0,
    limit: 50,
  })

  /** 总记录数 */
  const totalCount = ref(0)

  /** 是否还有更多 */
  const hasMore = ref(false)

  /** 是否正在加载 */
  const isLoading = ref(false)

  /** 统计信息 */
  const stats = ref<HistoryStats | null>(null)

  /** 选中的项目 ID 列表 */
  const selectedIds = ref<Set<number>>(new Set())

  /** 最后一次错误 */
  const lastError = ref<string | null>(null)

  // ============================================
  // Getters
  // ============================================

  /** 选中的项目数量 */
  const selectedCount = computed(() => selectedIds.value.size)

  /** 是否有选中项目 */
  const hasSelection = computed(() => selectedIds.value.size > 0)

  /** 选中的项目列表 */
  const selectedItems = computed(() =>
    items.value.filter((item) => selectedIds.value.has(item.id))
  )

  /** 是否全选 */
  const isAllSelected = computed(
    () => items.value.length > 0 && selectedIds.value.size === items.value.length
  )

  // ============================================
  // Actions
  // ============================================

  /**
   * 加载历史记录
   * @param params 搜索参数 (可选，使用当前参数)
   */
  async function loadHistory(params?: Partial<HistorySearchParams>): Promise<void> {
    try {
      isLoading.value = true
      lastError.value = null

      // 合并参数
      if (params) {
        searchParams.value = { ...searchParams.value, ...params, offset: 0 }
      }

      const result = await invoke<HistorySearchResult>('search_history', {
        params: searchParams.value,
      })

      items.value = result.items
      totalCount.value = result.total
      hasMore.value = result.hasMore
      selectedIds.value.clear()
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 加载更多历史记录
   */
  async function loadMore(): Promise<void> {
    if (!hasMore.value || isLoading.value) {
      return
    }

    try {
      isLoading.value = true
      lastError.value = null

      // 更新偏移量
      searchParams.value.offset = items.value.length

      const result = await invoke<HistorySearchResult>('search_history', {
        params: searchParams.value,
      })

      items.value.push(...result.items)
      hasMore.value = result.hasMore
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 搜索历史记录
   * @param query 搜索关键词
   */
  async function search(query: string): Promise<void> {
    await loadHistory({ query, offset: 0 })
  }

  /**
   * 按日期范围过滤
   * @param startDate 开始日期
   * @param endDate 结束日期
   */
  async function filterByDate(startDate?: string, endDate?: string): Promise<void> {
    await loadHistory({ startDate, endDate, offset: 0 })
  }

  /**
   * 按标签过滤
   * @param tags 标签列表
   */
  async function filterByTags(tags: string[]): Promise<void> {
    await loadHistory({ tags, offset: 0 })
  }

  /**
   * 添加历史记录
   * @param item 历史记录项 (不含 id)
   */
  async function addItem(
    item: Omit<HistoryItem, 'id' | 'createdAt'>
  ): Promise<HistoryItem> {
    try {
      lastError.value = null

      const newItem = await invoke<HistoryItem>('add_history_item', { item })

      // 添加到列表开头
      items.value.unshift(newItem)
      totalCount.value++

      return newItem
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 更新历史记录
   * @param id 记录 ID
   * @param updates 更新内容
   */
  async function updateItem(
    id: number,
    updates: Partial<Pick<HistoryItem, 'tags' | 'ocrText' | 'metadata'>>
  ): Promise<void> {
    try {
      lastError.value = null

      await invoke('update_history_item', { id, updates })

      // 更新本地状态
      const index = items.value.findIndex((item) => item.id === id)
      if (index !== -1) {
        items.value[index] = { ...items.value[index], ...updates }
      }
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 删除历史记录
   * @param id 记录 ID
   */
  async function deleteItem(id: number): Promise<void> {
    try {
      lastError.value = null

      await invoke('delete_history_item', { id })

      // 从本地状态移除
      const index = items.value.findIndex((item) => item.id === id)
      if (index !== -1) {
        items.value.splice(index, 1)
        totalCount.value--
      }

      // 从选中列表移除
      selectedIds.value.delete(id)
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 批量删除历史记录
   * @param ids 记录 ID 列表
   */
  async function deleteItems(ids: number[]): Promise<void> {
    try {
      lastError.value = null

      await invoke('delete_history_items', { ids })

      // 从本地状态移除
      items.value = items.value.filter((item) => !ids.includes(item.id))
      totalCount.value -= ids.length

      // 从选中列表移除
      ids.forEach((id) => selectedIds.value.delete(id))
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 删除选中的项目
   */
  async function deleteSelected(): Promise<void> {
    const ids = Array.from(selectedIds.value)
    if (ids.length > 0) {
      await deleteItems(ids)
    }
  }

  /**
   * 加载统计信息
   */
  async function loadStats(): Promise<void> {
    try {
      lastError.value = null
      stats.value = await invoke<HistoryStats>('get_history_stats')
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 选择/取消选择项目
   * @param id 记录 ID
   */
  function toggleSelection(id: number): void {
    if (selectedIds.value.has(id)) {
      selectedIds.value.delete(id)
    } else {
      selectedIds.value.add(id)
    }
  }

  /**
   * 全选/取消全选
   */
  function toggleSelectAll(): void {
    if (isAllSelected.value) {
      selectedIds.value.clear()
    } else {
      items.value.forEach((item) => selectedIds.value.add(item.id))
    }
  }

  /**
   * 清除选择
   */
  function clearSelection(): void {
    selectedIds.value.clear()
  }

  /**
   * 导出选中的项目
   * @param outputDir 输出目录
   */
  async function exportSelected(outputDir: string): Promise<string[]> {
    try {
      lastError.value = null

      const ids = Array.from(selectedIds.value)
      const paths = await invoke<string[]>('export_history_items', {
        ids,
        outputDir,
      })

      return paths
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 重置所有状态
   */
  function $reset(): void {
    items.value = []
    searchParams.value = {
      sortBy: 'createdAt',
      sortOrder: 'desc',
      offset: 0,
      limit: 50,
    }
    totalCount.value = 0
    hasMore.value = false
    isLoading.value = false
    stats.value = null
    selectedIds.value.clear()
    lastError.value = null
  }

  return {
    // State
    items,
    searchParams,
    totalCount,
    hasMore,
    isLoading,
    stats,
    selectedIds,
    lastError,

    // Getters
    selectedCount,
    hasSelection,
    selectedItems,
    isAllSelected,

    // Actions
    loadHistory,
    loadMore,
    search,
    filterByDate,
    filterByTags,
    addItem,
    updateItem,
    deleteItem,
    deleteItems,
    deleteSelected,
    loadStats,
    toggleSelection,
    toggleSelectAll,
    clearSelection,
    exportSelected,
    $reset,
  }
})
