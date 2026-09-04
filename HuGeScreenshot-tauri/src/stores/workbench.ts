/**
 * 工作台状态管理 Store
 *
 * 管理工作台双面板布局的状态：
 * - 选中项目状态
 * - OCR 文本和统计信息
 * - UI 偏好设置（面板宽度、搜索、过滤）
 *
 * @validates Requirements 7.1, 7.4
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import { invoke } from '@tauri-apps/api/core'
import { useHistoryStore } from './history'
import type { HistoryItem } from '@/types'

// ============================================
// Types
// ============================================

/** 日期过滤类型 */
export type DateFilter = 'all' | 'today' | 'week' | 'month'

/** OCR 状态 */
export type OcrStatus = 'ready' | 'processing' | 'completed' | 'error'

/** 文本格式化类型（从共享 composable 导入） */
export type { FormatType } from '@/composables/useOcrTextActions'
import type { FormatType } from '@/composables/useOcrTextActions'
import { applyFormat } from '@/composables/useOcrTextActions'
import { formatOcrUserError } from '@/utils/ocrError'

/** OCR 统计信息 */
export interface OcrStats {
  /** 字符数 */
  charCount: number
  /** 置信度 (0-100) */
  confidence: number
  /** 处理耗时 (毫秒) */
  elapsedTime: number
  /** OCR 引擎名称 */
  engine: string
}

/** 本地存储键名 */
const STORAGE_KEYS = {
  SELECTED_ITEM_ID: 'workbench_selected_item_id',
  LEFT_PANEL_WIDTH: 'workbench_left_panel_width',
  DATE_FILTER: 'workbench_date_filter',
} as const

/**
 * 临时预览数据
 * 
 * Feature: workbench-temporary-preview
 * 截图确认后不立即写入历史数据库，而是显示临时预览
 * 用户确认保存时才持久化到历史记录
 */
export interface TemporaryPreviewData {
  /** 临时 ID (temp_timestamp) */
  id: string
  /** 图片数据 (PNG 字节数组) */
  imageData: Uint8Array
  /** 图片宽度 */
  width: number
  /** 图片高度 */
  height: number
  /** OCR 文本（如果已执行 OCR） */
  ocrText?: string
  /** 元数据 */
  metadata?: {
    captureMode?: string
    monitorId?: number
    hasAnnotations?: boolean
    windowTitle?: string
  }
}

// ============================================
// Store Definition
// ============================================

export const useWorkbenchStore = defineStore('workbench', () => {
  // ============================================
  // 依赖的 Stores
  // ============================================
  const historyStore = useHistoryStore()

  // ============================================
  // State - Selection
  // ============================================

  /** 选中项目的 ID */
  const selectedItemId = ref<number | null>(null)

  // ============================================
  // State - OCR
  // ============================================

  /** 当前 OCR 文本 */
  const ocrText = ref('')

  /** 原始 OCR 文本（用于恢复） */
  const originalOcrText = ref('')

  /** OCR 加载状态 */
  const isOcrLoading = ref(false)

  /** OCR 错误信息 */
  const ocrError = ref<string | null>(null)

  /** OCR 状态 */
  const ocrStatus = ref<OcrStatus>('ready')

  /** OCR 统计信息 */
  const ocrStats = ref<OcrStats | null>(null)

  // ============================================
  // State - UI Preferences
  // ============================================

  /** 左侧面板宽度百分比 (0-100) */
  const leftPanelWidth = ref(35)

  /** 搜索查询 */
  const searchQuery = ref('')

  /** 日期过滤 */
  const dateFilter = ref<DateFilter>('all')

  // ============================================
  // State - Temporary Preview Mode
  // Feature: workbench-temporary-preview
  // ============================================

  /** 是否处于临时预览模式 */
  const isTemporaryMode = ref(false)

  /** 临时预览数据 */
  const temporaryData = ref<TemporaryPreviewData | null>(null)

  /** 临时图片的 Blob URL（用于前端显示） */
  const temporaryImageUrl = ref<string | null>(null)

  // ============================================
  // Getters
  // ============================================

  /**
   * 获取选中的历史记录项
   * 通过 ID 从 historyStore 中查找
   */
  const selectedItem = computed<HistoryItem | null>(() => {
    if (selectedItemId.value === null) {
      return null
    }
    return (
      historyStore.items.find((item) => item.id === selectedItemId.value) ?? null
    )
  })

  /**
   * 是否有选中项
   */
  const hasSelection = computed(() => selectedItemId.value !== null)

  /**
   * OCR 文本是否已修改（与原文不同）
   */
  const hasTextChanges = computed(() => ocrText.value !== originalOcrText.value)

  /**
   * 是否有 OCR 内容
   */
  const hasOcrContent = computed(() => ocrText.value.length > 0)

  /**
   * 字符数统计
   */
  const charCount = computed(() => ocrText.value.length)

  /**
   * 是否有未保存的临时截图
   * Feature: workbench-temporary-preview
   */
  const hasUnsavedTemporary = computed(() => isTemporaryMode.value && temporaryData.value !== null)

  // ============================================
  // Actions - Selection
  // ============================================

  /**
   * 选择历史记录项
   * @param id 历史记录 ID
   * @validates Requirements 7.1
   */
  async function selectItem(id: number): Promise<void> {
    // 如果已经选中，不重复处理
    if (selectedItemId.value === id) {
      return
    }

    selectedItemId.value = id

    // 从 historyStore 获取项目
    const item = historyStore.items.find((i) => i.id === id)

    if (item) {
      // 更新 OCR 文本：文字类型优先使用完整的 textContent
      const displayText = item.contentType === 'text'
        ? (item.textContent ?? item.ocrText ?? '')
        : (item.ocrText ?? '')
      setOcrText(displayText)

      // 持久化选中状态
      persistSelectedItemId(id)
    }
  }

  /**
   * 清除选择
   */
  function clearSelection(): void {
    selectedItemId.value = null
    ocrText.value = ''
    originalOcrText.value = ''
    ocrStats.value = null
    ocrStatus.value = 'ready'
    ocrError.value = null

    // 清除持久化
    localStorage.removeItem(STORAGE_KEYS.SELECTED_ITEM_ID)
  }

  /**
   * 选择下一个项目
   */
  function selectNext(): void {
    if (historyStore.items.length === 0) return

    const currentIndex = historyStore.items.findIndex(
      (item) => item.id === selectedItemId.value
    )

    if (currentIndex === -1) {
      // 没有选中项，选择第一个
      selectItem(historyStore.items[0].id)
    } else if (currentIndex < historyStore.items.length - 1) {
      // 选择下一个
      selectItem(historyStore.items[currentIndex + 1].id)
    }
  }

  /**
   * 选择上一个项目
   */
  function selectPrevious(): void {
    if (historyStore.items.length === 0) return

    const currentIndex = historyStore.items.findIndex(
      (item) => item.id === selectedItemId.value
    )

    if (currentIndex === -1) {
      // 没有选中项，选择最后一个
      selectItem(historyStore.items[historyStore.items.length - 1].id)
    } else if (currentIndex > 0) {
      // 选择上一个
      selectItem(historyStore.items[currentIndex - 1].id)
    }
  }

  // ============================================
  // Actions - OCR Text
  // ============================================

  /**
   * 设置 OCR 文本
   * 用于加载已缓存的 OCR 文本，不包含置信度等统计信息
   * @param text OCR 文本
   */
  function setOcrText(text: string): void {
    ocrText.value = text
    originalOcrText.value = text
    ocrStatus.value = text ? 'completed' : 'ready'
    ocrError.value = null

    // 更新统计信息
    // 注意：加载缓存的 OCR 文本时，置信度和耗时信息不可用
    // 只有执行新的 OCR 时才会有这些数据
    if (text) {
      ocrStats.value = {
        charCount: text.length,
        confidence: 0, // 缓存的 OCR 没有置信度信息，设为 0 表示不显示
        elapsedTime: 0, // 缓存的 OCR 没有耗时信息
        engine: '', // 缓存的 OCR 没有引擎信息
      }
    } else {
      ocrStats.value = null
    }
  }

  /** 自动保存防抖定时器 */
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * 更新 OCR 文本（不更新原始文本）
   * 编辑后自动防抖保存到历史记录
   * @param text 新的 OCR 文本
   */
  function updateOcrText(text: string): void {
    ocrText.value = text
    // 更新字符数统计
    if (ocrStats.value) {
      ocrStats.value = {
        ...ocrStats.value,
        charCount: text.length,
      }
    }

    // 防抖自动保存到历史记录（1秒后保存）
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(async () => {
      if (selectedItemId.value !== null) {
        try {
          await historyStore.updateItem(selectedItemId.value, { ocrText: text })
        } catch (error) {
          console.error('[WorkbenchStore] Auto-save failed:', error)
        }
      }
    }, 1000)
  }

  /**
   * 格式化文本
   * 使用共享的 applyFormat 纯函数，确保与 OCR 弹窗逻辑一致
   * @param type 格式化类型
   */
  function formatText(type: FormatType): void {
    if (!ocrText.value) return
    updateOcrText(applyFormat(ocrText.value, type))
  }

  /**
   * 恢复原始文本
   */
  function restoreOriginal(): void {
    ocrText.value = originalOcrText.value
    // 更新字符数统计
    if (ocrStats.value) {
      ocrStats.value = {
        ...ocrStats.value,
        charCount: originalOcrText.value.length,
      }
    }
  }

  /**
   * 执行本地 OCR 识别
   * @param imagePath 图片路径
   */
  async function performOcr(imagePath: string, engine?: 'local' | 'baiduAccurate'): Promise<void> {
    try {
      isOcrLoading.value = true
      ocrStatus.value = 'processing'
      ocrError.value = null

      const startTime = Date.now()

      // 直接使用 Rust 原生 OCR 引擎（无需 Sidecar）
      const result = await invoke<{
        text: string
        boxes: Array<{ text: string; confidence: number; box_coords: number[][] }>
        elapse: number
        engine?: string
      }>('call_ocr', { imagePath, engine: engine ?? null })

      const elapsedTime = Date.now() - startTime

      // 提取文本
      const text = result.boxes && result.boxes.length > 0
        ? result.boxes.map((box) => box.text).join('\n')
        : result.text ?? ''

      // 计算平均置信度
      const avgConfidence =
        result.boxes && result.boxes.length > 0
          ? result.boxes.reduce((sum, box) => sum + (box.confidence ?? 0), 0) /
            result.boxes.length
          : 0

      // 更新状态
      ocrText.value = text
      originalOcrText.value = text
      ocrStatus.value = 'completed'
      ocrStats.value = {
        charCount: text.length,
        confidence: Math.round(avgConfidence * 100),
        elapsedTime,
        engine: result.engine === 'baiduAccurate' ? 'Baidu OCR' : 'RustOCR',
      }

      // 更新历史记录中的 OCR 文本
      if (selectedItemId.value !== null) {
        await historyStore.updateItem(selectedItemId.value, { ocrText: text })
      }
    } catch (error) {
      ocrStatus.value = 'error'
      const message = formatOcrUserError(error)
      ocrError.value = message
      throw new Error(message)
    } finally {
      isOcrLoading.value = false
    }
  }

  /**
   * 翻译 OCR 文本（直接调用 Rust 原生翻译，不依赖 Sidecar）
   *
   * 智能语言检测：中文→英语，非中文→中文
   *
   * @param targetLang 目标语言（可选，不提供时自动检测）
   */
  async function translateText(targetLang?: string): Promise<void> {
    if (!ocrText.value) return

    try {
      isOcrLoading.value = true
      ocrError.value = null

      // 直接调用 Rust 原生翻译命令（不依赖 Sidecar）
      const result = await invoke<{
        translatedText: string
        sourceLang: string
        targetLang: string
        provider: string
      }>('translate_text_direct', {
        text: ocrText.value,
        targetLang: targetLang || null,
      })

      if (result.translatedText) {
        updateOcrText(result.translatedText)
      }
    } catch (error) {
      ocrError.value = error instanceof Error ? error.message : String(error)
      throw error
    } finally {
      isOcrLoading.value = false
    }
  }

  /**
   * 复制 OCR 文本到剪贴板
   * 使用 Tauri clipboard-manager 插件
   * @returns 是否复制成功
   * @validates Requirements 5.1
   */
  async function copyText(): Promise<boolean> {
    if (!ocrText.value) return false

    try {
      await writeText(ocrText.value)
      return true
    } catch (error) {
      ocrError.value = error instanceof Error ? error.message : String(error)
      console.error('[WorkbenchStore] Copy to clipboard failed:', error)
      return false
    }
  }

  // ============================================
  // Actions - UI Preferences
  // ============================================

  /**
   * 设置左侧面板宽度
   * @param width 宽度百分比 (0-100)
   */
  function setLeftPanelWidth(width: number): void {
    // 限制范围在 20-80 之间
    leftPanelWidth.value = Math.max(20, Math.min(80, width))
    // 持久化
    localStorage.setItem(
      STORAGE_KEYS.LEFT_PANEL_WIDTH,
      String(leftPanelWidth.value)
    )
  }

  /**
   * 设置搜索查询
   * @param query 搜索关键词
   */
  function setSearchQuery(query: string): void {
    searchQuery.value = query
  }

  /**
   * 设置日期过滤
   * @param filter 日期过滤类型
   */
  function setDateFilter(filter: DateFilter): void {
    dateFilter.value = filter
    // 持久化
    localStorage.setItem(STORAGE_KEYS.DATE_FILTER, filter)
  }

  // ============================================
  // Actions - Temporary Preview Mode
  // Feature: workbench-temporary-preview
  // ============================================

  /**
   * 进入临时预览模式
   * 
   * 截图确认后调用此方法，不写入历史数据库，而是在工作台显示临时预览。
   * 用户可以在临时预览模式下进行 OCR、编辑等操作，
   * 确认保存时才持久化到历史记录。
   * 
   * @param data 临时预览数据
   */
  function enterTemporaryMode(data: TemporaryPreviewData): void {
    // 如果已经处于临时模式，先清理旧的 Blob URL
    if (temporaryImageUrl.value) {
      URL.revokeObjectURL(temporaryImageUrl.value)
      temporaryImageUrl.value = null
    }

    // 设置临时模式状态
    isTemporaryMode.value = true
    temporaryData.value = data

    // 创建 Blob URL 用于前端显示
    const blob = new Blob([data.imageData], { type: 'image/png' })
    temporaryImageUrl.value = URL.createObjectURL(blob)

    // 清除历史列表选择
    selectedItemId.value = null

    // 设置 OCR 文本（如果有）
    if (data.ocrText) {
      setOcrText(data.ocrText)
    } else {
      ocrText.value = ''
      originalOcrText.value = ''
      ocrStats.value = null
      ocrStatus.value = 'ready'
    }

    console.log('[WorkbenchStore] 进入临时预览模式:', data.id)
  }

  /**
   * 确认保存临时截图到历史记录
   * 
   * @returns 保存的历史记录 ID，失败返回 null
   */
  async function confirmAndSave(): Promise<number | null> {
    if (!isTemporaryMode.value || !temporaryData.value) {
      console.warn('[WorkbenchStore] 不在临时预览模式，无法保存')
      return null
    }

    try {
      // 调用 Rust 命令保存到历史记录
      const result = await invoke<{
        filePath: string
        historyId: number
        thumbnailPath: string | null
      }>('save_screenshot_with_history', {
        imageData: temporaryData.value.imageData,
        format: 'png',
        metadata: temporaryData.value.metadata,
        ocrText: ocrText.value || null,
      })

      console.log('[WorkbenchStore] 临时截图已保存到历史记录:', result)

      // 退出临时模式
      exitTemporaryMode()

      // 刷新历史记录列表
      await historyStore.loadHistory()

      // 选中刚保存的记录
      await selectItem(result.historyId)

      return result.historyId
    } catch (error) {
      console.error('[WorkbenchStore] 保存临时截图失败:', error)
      return null
    }
  }

  /**
   * 丢弃临时截图
   * 
   * 清除所有临时数据并退出临时模式，不会将任何数据写入历史记录。
   */
  function discardTemporary(): void {
    if (!isTemporaryMode.value) {
      return
    }

    console.log('[WorkbenchStore] 丢弃临时截图')
    exitTemporaryMode()

    // 如果历史列表有条目，选中第一个
    if (historyStore.items.length > 0) {
      selectItem(historyStore.items[0].id)
    }
  }

  /**
   * 退出临时预览模式（内部方法）
   * 
   * 清理临时状态，释放资源。
   */
  function exitTemporaryMode(): void {
    // 释放 Blob URL
    if (temporaryImageUrl.value) {
      URL.revokeObjectURL(temporaryImageUrl.value)
      temporaryImageUrl.value = null
    }

    // 清除临时状态
    isTemporaryMode.value = false
    temporaryData.value = null

    // 清除 OCR 状态
    ocrText.value = ''
    originalOcrText.value = ''
    ocrStats.value = null
    ocrStatus.value = 'ready'
    ocrError.value = null
  }

  /**
   * 复制临时截图到剪贴板
   * 
   * @returns 是否复制成功
   */
  async function copyTemporaryImage(): Promise<boolean> {
    if (!isTemporaryMode.value || !temporaryData.value) {
      return false
    }

    try {
      // 使用 PNG 方式复制到剪贴板
      await invoke('copy_png_to_clipboard', {
        pngData: temporaryData.value.imageData,
      })

      console.log('[WorkbenchStore] 临时截图已复制到剪贴板')
      return true
    } catch (error) {
      console.error('[WorkbenchStore] 复制临时截图失败:', error)
      return false
    }
  }

  // ============================================
  // Persistence Helpers
  // ============================================

  /**
   * 持久化选中项 ID
   * @param id 历史记录 ID
   * @validates Requirements 7.4
   */
  function persistSelectedItemId(id: number): void {
    localStorage.setItem(STORAGE_KEYS.SELECTED_ITEM_ID, String(id))
  }

  /**
   * 从本地存储恢复状态
   * @validates Requirements 7.4
   */
  function restoreFromStorage(): void {
    // 恢复选中项 ID
    const savedId = localStorage.getItem(STORAGE_KEYS.SELECTED_ITEM_ID)
    if (savedId) {
      const id = parseInt(savedId, 10)
      if (!isNaN(id)) {
        // 延迟选择，等待 historyStore 加载完成
        selectedItemId.value = id
      }
    }

    // 恢复左侧面板宽度
    const savedWidth = localStorage.getItem(STORAGE_KEYS.LEFT_PANEL_WIDTH)
    if (savedWidth) {
      const width = parseFloat(savedWidth)
      if (!isNaN(width)) {
        leftPanelWidth.value = Math.max(20, Math.min(80, width))
      }
    }

    // 恢复日期过滤
    const savedFilter = localStorage.getItem(STORAGE_KEYS.DATE_FILTER)
    if (savedFilter && ['all', 'today', 'week', 'month'].includes(savedFilter)) {
      dateFilter.value = savedFilter as DateFilter
    }
  }

  /**
   * 初始化工作台
   * 加载历史记录并恢复选中状态
   */
  async function initialize(): Promise<void> {
    // 先恢复本地存储的状态
    restoreFromStorage()

    // 如果有保存的选中项 ID，尝试加载其 OCR 文本
    if (selectedItemId.value !== null) {
      const item = historyStore.items.find((i) => i.id === selectedItemId.value)
      if (item) {
        setOcrText(item.ocrText ?? '')
      }
    }
  }

  // ============================================
  // Watchers
  // ============================================

  // 监听 historyStore.items 变化，确保选中项仍然存在
  watch(
    () => historyStore.items,
    (items) => {
      if (selectedItemId.value !== null) {
        const exists = items.some((item) => item.id === selectedItemId.value)
        if (!exists) {
          // 选中项已被删除，清除选择
          clearSelection()
        }
      }
    }
  )

  // ============================================
  // Reset
  // ============================================

  /**
   * 重置所有状态
   */
  function $reset(): void {
    // 清理自动保存定时器，防止 stale callback
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }

    selectedItemId.value = null
    ocrText.value = ''
    originalOcrText.value = ''
    isOcrLoading.value = false
    ocrError.value = null
    ocrStatus.value = 'ready'
    ocrStats.value = null
    leftPanelWidth.value = 35
    searchQuery.value = ''
    dateFilter.value = 'all'
    
    // 清理临时预览模式状态
    exitTemporaryMode()
  }

  return {
    // State - Selection
    selectedItemId,

    // State - OCR
    ocrText,
    originalOcrText,
    isOcrLoading,
    ocrError,
    ocrStatus,
    ocrStats,

    // State - UI Preferences
    leftPanelWidth,
    searchQuery,
    dateFilter,

    // State - Temporary Preview Mode
    isTemporaryMode,
    temporaryData,
    temporaryImageUrl,

    // Getters
    selectedItem,
    hasSelection,
    hasTextChanges,
    hasOcrContent,
    charCount,
    hasUnsavedTemporary,

    // Actions - Selection
    selectItem,
    clearSelection,
    selectNext,
    selectPrevious,

    // Actions - OCR Text
    setOcrText,
    updateOcrText,
    formatText,
    restoreOriginal,
    performOcr,
    translateText,
    copyText,

    // Actions - UI Preferences
    setLeftPanelWidth,
    setSearchQuery,
    setDateFilter,

    // Actions - Temporary Preview Mode
    enterTemporaryMode,
    confirmAndSave,
    discardTemporary,
    copyTemporaryImage,

    // Lifecycle
    initialize,
    restoreFromStorage,
    $reset,
  }
})
