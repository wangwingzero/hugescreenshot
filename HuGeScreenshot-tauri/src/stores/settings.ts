/**
 * 设置状态管理 Store
 *
 * 管理应用配置：
 * - 通用设置
 * - 热键配置
 * - 截图设置
 * - 标注设置
 * - OCR 设置
 * - 录屏设置
 *
 * @validates Requirements 17.1, 17.2, 17.3, 17.4
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type {
  AppConfig,
  GeneralConfig,
  HotkeyConfig,
  ScreenshotConfig,
  AnnotationConfig,
  OcrConfig,
  RecordingConfig,
  PinImageConfig,
  MouseHighlightConfig,
  WebToMarkdownConfig,
  FileToMarkdownConfig,
  NotificationConfig,
  UpdateConfig,
  AdvancedConfig,
} from '@/types'
import { DEFAULT_CONFIG } from '@/types'

export const useSettingsStore = defineStore('settings', () => {
  // ============================================
  // State
  // ============================================

  /** 完整配置 */
  const config = ref<AppConfig>(structuredClone(DEFAULT_CONFIG))

  /** 是否已加载 */
  const isLoaded = ref(false)

  /** 是否有未保存的更改 */
  const isDirty = ref(false)

  /** 是否正在保存 */
  const isSaving = ref(false)

  /** 最后一次错误 */
  const lastError = ref<string | null>(null)

  /** 防抖保存定时器 */
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

  /** 自动保存延迟（毫秒） */
  const AUTO_SAVE_DELAY_MS = 500 // 自动保存延迟（毫秒）

  // ============================================
  // 自动保存逻辑
  // ============================================

  /**
   * 触发防抖自动保存
   * 在设置变更后自动保存，避免频繁写入
   */
  function triggerAutoSave(): void {
    // 清除之前的定时器
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
    }

    // 设置新的定时器
    autoSaveTimer = setTimeout(async () => {
      if (isDirty.value && !isSaving.value) {
        try {
          await saveConfig()
        } catch (error) {
          console.error('自动保存失败:', error)
        }
      }
    }, AUTO_SAVE_DELAY_MS)
  }

  // 监听 isDirty 变化，自动触发保存
  watch(isDirty, (newValue) => {
    if (newValue && isLoaded.value) {
      triggerAutoSave()
    }
  })

  // ============================================
  // Getters (便捷访问)
  // ============================================

  /** 通用设置 */
  const general = computed(() => config.value.general)

  /** 热键设置 */
  const hotkeys = computed(() => config.value.hotkeys)

  /** 截图设置 */
  const screenshot = computed(() => config.value.screenshot)

  /** 标注设置 */
  const annotation = computed(() => config.value.annotation)

  /** OCR 设置 */
  const ocr = computed(() => config.value.ocr)

  /** 录屏设置 */
  const recording = computed(() => config.value.recording)

  /** 贴图设置 */
  const pinImage = computed(() => config.value.pinImage)

  /** 鼠标高亮设置 */
  const mouseHighlight = computed(() => config.value.mouseHighlight)

  /** 网页转 Markdown 设置 */
  const webToMarkdown = computed(() => config.value.webToMarkdown)

  /** 文件转 Markdown 设置 */
  const fileToMarkdown = computed(() => config.value.fileToMarkdown)

  /** 通知设置 */
  const notification = computed(() => config.value.notification)

  /** 更新设置 */
  const update = computed(() => config.value.update)

  /** 高级设置 */
  const advanced = computed(() => config.value.advanced)

  /** 当前主题 */
  const currentTheme = computed(() => {
    if (config.value.general.theme === 'system') {
      // 检测系统主题
      if (typeof window !== 'undefined' && window.matchMedia) {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      }
      return 'light'
    }
    return config.value.general.theme
  })

  /** 当前语言 */
  const currentLanguage = computed(() => config.value.general.language)

  // ============================================
  // Actions
  // ============================================

  /**
   * 加载配置
   */
  async function loadConfig(): Promise<void> {
    try {
      lastError.value = null

      const loadedConfig = await invoke<AppConfig>('load_config')
      config.value = loadedConfig
      isLoaded.value = true
      isDirty.value = false
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      // 使用默认配置
      config.value = structuredClone(DEFAULT_CONFIG)
      isLoaded.value = true
      throw error
    }
  }

  /**
   * 保存配置
   */
  async function saveConfig(): Promise<void> {
    try {
      isSaving.value = true
      lastError.value = null

      await invoke('save_config', { config: config.value })
      isDirty.value = false
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    } finally {
      isSaving.value = false
    }
  }

  /**
   * 更新通用设置
   * @param updates 更新内容
   */
  function updateGeneral(updates: Partial<GeneralConfig>): void {
    config.value.general = { ...config.value.general, ...updates }
    isDirty.value = true
  }

  /**
   * 更新热键设置
   * @param updates 更新内容
   */
  async function updateHotkeys(updates: Partial<HotkeyConfig>): Promise<void> {
    const oldHotkeys = { ...config.value.hotkeys }

    try {
      // 先更新本地状态
      config.value.hotkeys = { ...config.value.hotkeys, ...updates }
      isDirty.value = true

      // 通知 Rust 更新热键（后端会处理空字符串的清除逻辑）
      for (const [action, shortcut] of Object.entries(updates)) {
        await invoke('update_hotkey', { action, shortcut: shortcut ?? '' })
      }
    } catch (error) {
      // 回滚
      config.value.hotkeys = oldHotkeys
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 更新截图设置
   * @param updates 更新内容
   */
  function updateScreenshot(updates: Partial<ScreenshotConfig>): void {
    config.value.screenshot = { ...config.value.screenshot, ...updates }
    isDirty.value = true
  }

  /**
   * 更新标注设置
   * @param updates 更新内容
   */
  function updateAnnotation(updates: Partial<AnnotationConfig>): void {
    config.value.annotation = { ...config.value.annotation, ...updates }
    isDirty.value = true
  }

  /**
   * 更新 OCR 设置
   * @param updates 更新内容
   */
  function updateOcr(updates: Partial<OcrConfig>): void {
    config.value.ocr = { ...config.value.ocr, ...updates }
    isDirty.value = true
  }

  /**
   * 更新录屏设置
   * @param updates 更新内容
   */
  function updateRecording(updates: Partial<RecordingConfig>): void {
    config.value.recording = { ...config.value.recording, ...updates }
    isDirty.value = true
  }

  /**
   * 更新贴图设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updatePinImage(updates: Partial<PinImageConfig>): void {
    config.value.pinImage = { ...config.value.pinImage, ...updates }
    isDirty.value = true
  }

  /**
   * 更新鼠标高亮设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateMouseHighlight(updates: Partial<MouseHighlightConfig>): void {
    config.value.mouseHighlight = { ...config.value.mouseHighlight, ...updates }
    isDirty.value = true
  }

  /**
   * 更新网页转 Markdown 设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateWebToMarkdown(updates: Partial<WebToMarkdownConfig>): void {
    config.value.webToMarkdown = { ...config.value.webToMarkdown, ...updates }
    isDirty.value = true
  }

  /**
   * 更新文件转 Markdown 设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateFileToMarkdown(updates: Partial<FileToMarkdownConfig>): void {
    config.value.fileToMarkdown = { ...config.value.fileToMarkdown, ...updates }
    isDirty.value = true
  }

  /**
   * 更新通知设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateNotification(updates: Partial<NotificationConfig>): void {
    config.value.notification = { ...config.value.notification, ...updates }
    isDirty.value = true
  }

  /**
   * 更新更新设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateUpdate(updates: Partial<UpdateConfig>): void {
    config.value.update = { ...config.value.update, ...updates }
    isDirty.value = true
  }

  /**
   * 更新高级设置
   * @param updates 更新内容
   * @validates Requirements 11.1
   */
  function updateAdvanced(updates: Partial<AdvancedConfig>): void {
    config.value.advanced = { ...config.value.advanced, ...updates }
    isDirty.value = true
  }

  /**
   * 重置为默认配置
   */
  function resetToDefault(): void {
    config.value = structuredClone(DEFAULT_CONFIG)
    isDirty.value = true
  }

  /**
   * 重置特定部分为默认值
   * @param section 配置部分
   */
  function resetSection(
    section: keyof AppConfig
  ): void {
    config.value = { ...config.value, [section]: structuredClone(DEFAULT_CONFIG[section]) }
    isDirty.value = true
  }

  /**
   * 导出配置
   * @param filePath 导出文件路径
   */
  async function exportConfig(filePath: string): Promise<void> {
    try {
      lastError.value = null
      await invoke('export_config', { filePath, config: config.value })
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 导入配置
   * @param filePath 导入文件路径
   */
  async function importConfig(filePath: string): Promise<void> {
    try {
      lastError.value = null

      const importedConfig = await invoke<AppConfig>('import_config', { filePath })
      config.value = importedConfig
      isDirty.value = true
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 设置自动启动
   * @param enabled 是否启用
   */
  async function setAutoStart(enabled: boolean): Promise<void> {
    try {
      lastError.value = null

      await invoke('set_auto_start', { enabled })
      config.value.general.autoStart = enabled
      isDirty.value = true
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
      throw error
    }
  }

  /**
   * 检查自动启动状态
   */
  async function checkAutoStart(): Promise<boolean> {
    try {
      const enabled = await invoke<boolean>('check_auto_start')
      config.value.general.autoStart = enabled
      return enabled
    } catch (error) {
      console.error('Failed to check auto start:', error)
      return false
    }
  }

  /**
   * 重置所有状态
   */
  function $reset(): void {
    config.value = structuredClone(DEFAULT_CONFIG)
    isLoaded.value = false
    isDirty.value = false
    isSaving.value = false
    lastError.value = null
  }

  return {
    // State
    config,
    isLoaded,
    isDirty,
    isSaving,
    lastError,

    // Getters
    general,
    hotkeys,
    screenshot,
    annotation,
    ocr,
    recording,
    pinImage,
    mouseHighlight,
    webToMarkdown,
    fileToMarkdown,
    notification,
    update,
    advanced,
    currentTheme,
    currentLanguage,

    // Actions
    loadConfig,
    saveConfig,
    updateGeneral,
    updateHotkeys,
    updateScreenshot,
    updateAnnotation,
    updateOcr,
    updateRecording,
    updatePinImage,
    updateMouseHighlight,
    updateWebToMarkdown,
    updateFileToMarkdown,
    updateNotification,
    updateUpdate,
    updateAdvanced,
    resetToDefault,
    resetSection,
    exportConfig,
    importConfig,
    setAutoStart,
    checkAutoStart,
    $reset,
  }
})
