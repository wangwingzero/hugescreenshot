<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div
        v-if="visible"
        class="search-dialog-overlay"
        @click.self="handleClose"
        @keydown="handleKeyDown"
      >
        <div
          ref="dialogRef"
          class="search-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="search-dialog-title"
        >
          <!-- 搜索头部 -->
          <div class="search-header">
            <div class="search-input-wrapper">
              <span class="search-icon">🔍</span>
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                type="text"
                class="search-input"
                placeholder="搜索文件..."
                aria-label="搜索文件"
                @input="handleSearchInput"
                @keydown.down.prevent="navigateDown"
                @keydown.up.prevent="navigateUp"
                @keydown.enter.prevent="handleEnter"
                @keydown.esc.prevent="handleClose"
              />
              <button
                v-if="searchQuery"
                class="clear-btn"
                title="清除搜索"
                @click="handleClearSearch"
              >
                ✕
              </button>
            </div>
            <button
              class="close-btn"
              title="关闭 (Esc)"
              @click="handleClose"
            >
              ✕
            </button>
          </div>

          <!-- 搜索状态栏 -->
          <div class="search-status-bar">
            <div class="status-left">
              <span v-if="isSearching" class="status-searching">
                <span class="loading-spinner"></span>
                搜索中...
              </span>
              <span v-else-if="searchResults.length > 0" class="status-results">
                找到 <strong>{{ totalCount }}</strong> 个结果
                <span v-if="searchTimeMs > 0" class="search-time">
                  ({{ searchTimeMs }}ms)
                </span>
              </span>
              <span v-else-if="isTimeout && !isSearching" class="status-timeout">
                搜索超时，请缩短关键词后重试
              </span>
              <span v-else-if="searchQuery && !isSearching" class="status-empty">
                未找到匹配的文件
              </span>
              <span v-else class="status-hint">
                输入关键词开始搜索
              </span>
            </div>
            <div class="status-right">
              <span v-if="serviceStatus" class="service-status" :class="serviceStatusClass">
                {{ serviceStatusText }}
              </span>
            </div>
          </div>

          <!-- 搜索结果列表 -->
          <div
            ref="resultsContainerRef"
            class="search-results"
            role="listbox"
            aria-label="搜索结果"
          >
            <!-- 加载状态 -->
            <div v-if="isSearching && searchResults.length === 0" class="loading-state">
              <div class="loading-spinner large"></div>
              <span class="loading-text">正在搜索...</span>
            </div>

            <!-- 超时状态 -->
            <div v-else-if="isTimeout && searchQuery" class="empty-state">
              <span class="empty-icon">⏱</span>
              <span class="empty-text">搜索超时</span>
              <span class="empty-hint">文件数量过多，请尝试使用更精确的关键词</span>
            </div>

            <!-- 空状态 -->
            <div v-else-if="searchResults.length === 0 && searchQuery" class="empty-state">
              <span class="empty-icon">📭</span>
              <span class="empty-text">没有找到匹配的文件</span>
              <span class="empty-hint">尝试使用不同的关键词</span>
            </div>

            <!-- 初始状态 -->
            <div v-else-if="searchResults.length === 0" class="initial-state">
              <span class="initial-icon">🔍</span>
              <span class="initial-text">输入关键词搜索文件</span>
              <div class="keyboard-hints">
                <span class="hint-item"><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
                <span class="hint-item"><kbd>Enter</kbd> 打开</span>
                <span class="hint-item"><kbd>Esc</kbd> 关闭</span>
              </div>
            </div>

            <!-- 结果列表 -->
            <template v-else>
              <div
                v-for="(result, index) in searchResults"
                :key="result.fileId"
                :ref="el => setResultRef(el, index)"
                class="result-item"
                :class="{ 'is-selected': index === selectedIndex }"
                role="option"
                :aria-selected="index === selectedIndex"
                :title="result.path"
                @click="handleResultClick(result)"
                @dblclick="handleResultDoubleClick(result)"
                @contextmenu.prevent="handleResultContextMenu($event, result)"
                @mouseenter="selectedIndex = index"
              >
                <!-- 文件图标 -->
                <div class="result-icon">
                  <span v-if="result.isDirectory">📁</span>
                  <span v-else>{{ getFileIcon(result.name) }}</span>
                </div>

                <!-- 文件信息 -->
                <div class="result-info">
                  <div class="result-name">
                    <HighlightedText
                      :text="result.name"
                      :match-indices="result.matchIndices"
                    />
                  </div>
                  <div class="result-path" :title="result.path">
                    {{ truncatePath(result.path) }}
                  </div>
                </div>

                <!-- 文件元数据 -->
                <div class="result-meta">
                  <span class="result-size">{{ formatSize(result.size) }}</span>
                  <span class="result-date">{{ formatDate(result.modified) }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- 底部提示 -->
          <div class="search-footer">
            <div class="footer-hints">
              <span class="hint-item"><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
              <span class="hint-item"><kbd>Enter</kbd> 打开文件</span>
              <span class="hint-item"><kbd>Ctrl+Enter</kbd> 打开文件夹</span>
              <span class="hint-item"><kbd>Esc</kbd> 关闭</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 右键菜单 -->
    <ContextMenu
      :visible="contextMenu.visible"
      :items="contextMenuItems"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @close="closeContextMenu"
      @select="handleContextMenuSelect"
    />
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 文件搜索对话框组件
 *
 * 功能：
 * - 搜索输入框和结果列表
 * - 键盘导航 (Up/Down/Enter/Esc)
 * - 匹配文本高亮
 * - 显示文件图标、名称、路径、大小、修改日期
 * - 显示搜索结果总数和搜索时间
 *
 * @validates Requirements 6.1, 6.4, 6.6, 6.7
 */

import { ref, computed, watch, nextTick, onUnmounted, type ComponentPublicInstance } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import HighlightedText from './HighlightedText.vue'
import ContextMenu, { type ContextMenuItem } from './ContextMenu.vue'
import { useFileSearchStore } from '@/stores/fileSearch'

// ============================================
// Types
// ============================================

/** 搜索查询参数 */
interface SearchQuery {
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

/** 搜索结果项 */
interface SearchResult {
  fileId: string
  name: string
  path: string
  size: number
  modified: string
  isDirectory: boolean
  score: number
  matchIndices: [number, number][]
}

/** 搜索响应 */
interface SearchResponse {
  results: SearchResult[]
  totalCount: number
  searchTimeMs: number
}

/** 服务状态 */
interface ServiceStatus {
  state: 'starting' | 'running' | 'scanning' | 'stopping' | 'stopped'
  indexedFiles?: number
  scannedFiles?: number
  lastUpdate?: string
  scanProgress?: number
}

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 是否显示对话框 */
  visible: boolean
  /** 初始搜索关键词 */
  initialQuery?: string
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  initialQuery: '',
})

const emit = defineEmits<{
  /** 关闭对话框 */
  (e: 'close'): void
  /** 选择文件 */
  (e: 'select', result: SearchResult): void
  /** 打开文件 */
  (e: 'open', result: SearchResult): void
  /** 打开文件所在文件夹 */
  (e: 'open-folder', result: SearchResult): void
}>()

// ============================================
// Refs
// ============================================

/** 对话框容器引用 */
const dialogRef = ref<HTMLDivElement | null>(null)

/** 搜索输入框引用 */
const searchInputRef = ref<HTMLInputElement | null>(null)

/** 结果列表容器引用 */
const resultsContainerRef = ref<HTMLDivElement | null>(null)

/** 结果项引用数组 */
const resultRefs = ref<(HTMLElement | null)[]>([])

// ============================================
// State
// ============================================

/** 搜索关键词 */
const searchQuery = ref('')

/** 搜索结果列表 */
const searchResults = ref<SearchResult[]>([])

/** 结果总数 */
const totalCount = ref(0)

/** 搜索耗时 (ms) */
const searchTimeMs = ref(0)

/** 当前选中的索引 */
const selectedIndex = ref(0)

/** 是否正在搜索 */
const isSearching = ref(false)

/** 服务状态 */
const serviceStatus = ref<ServiceStatus | null>(null)

/** 右键菜单状态 */
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  result: null as SearchResult | null,
})

/** 右键菜单项 */
const contextMenuItems: ContextMenuItem[] = [
  { id: 'open', label: '打开', icon: '📂', shortcut: 'Enter' },
  { id: 'open-folder', label: '打开所在文件夹', icon: '📁', shortcut: 'Ctrl+Enter' },
  { id: 'copy-path', label: '复制路径', icon: '📋', shortcut: 'Ctrl+C' },
]

/** 搜索防抖定时器 */
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

/** 搜索请求计数器（用于取消过期请求） */
let searchRequestId = 0

/** 搜索关键词最大长度（防止粘贴整段日志触发超重搜索） */
const MAX_SEARCH_QUERY_LENGTH = 120

/** 长文本提取关键词时最多保留的 token 数量 */
const MAX_KEYWORD_TOKENS = 6

/** 搜索防抖间隔 */
const SEARCH_DEBOUNCE_MS = 300

/** 单次搜索超时时间 */
const SEARCH_TIMEOUT_MS = 10000

/** 是否搜索超时 */
const isTimeout = ref(false)

// ============================================
// Store
// ============================================

/** 文件搜索状态 Store */
const fileSearchStore = useFileSearchStore()

// ============================================
// Computed
// ============================================

/** 服务状态样式类 */
const serviceStatusClass = computed(() => {
  if (!serviceStatus.value) return ''
  switch (serviceStatus.value.state) {
    case 'running':
      return 'status-running'
    case 'scanning':
      return 'status-scanning'
    case 'starting':
    case 'stopping':
      return 'status-pending'
    case 'stopped':
      return 'status-stopped'
    default:
      return ''
  }
})

/** 服务状态文本 */
const serviceStatusText = computed(() => {
  if (!serviceStatus.value) return ''
  switch (serviceStatus.value.state) {
    case 'running':
      return `已索引 ${serviceStatus.value.indexedFiles?.toLocaleString() ?? 0} 个文件`
    case 'scanning':
      return `扫描中 ${serviceStatus.value.scannedFiles?.toLocaleString() ?? 0} 个文件`
    case 'starting':
      return '服务启动中...'
    case 'stopping':
      return '服务停止中...'
    case 'stopped':
      return '服务未运行'
    default:
      return ''
  }
})

// ============================================
// Helpers
// ============================================

/**
 * 规范化搜索文本（压缩空白）
 */
function normalizeSearchText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/**
 * 从长文本中提取可用于文件名匹配的关键词
 * 支持中英文和常见文件名字符
 */
function extractKeywordTokens(text: string): string[] {
  const matched = text.match(/[\u4e00-\u9fff]{2,}|[A-Za-z0-9._-]{2,}/g) ?? []
  const unique: string[] = []
  const seen = new Set<string>()

  for (const token of matched) {
    const normalized = token.toLowerCase()
    if (seen.has(normalized)) continue
    seen.add(normalized)
    unique.push(token)
    if (unique.length >= MAX_KEYWORD_TOKENS) {
      break
    }
  }

  return unique
}

/**
 * 构建安全搜索关键词
 * - 普通输入: 直接使用
 * - 超长输入: 提取关键词，避免对百万索引做重负载匹配
 */
function buildSafeSearchKeyword(raw: string): string {
  const normalized = normalizeSearchText(raw)
  if (!normalized) return ''

  if (normalized.length <= MAX_SEARCH_QUERY_LENGTH) {
    return normalized
  }

  const extracted = extractKeywordTokens(normalized)
  if (extracted.length > 0) {
    return extracted.join(' ').slice(0, MAX_SEARCH_QUERY_LENGTH).trim()
  }

  return normalized.slice(0, MAX_SEARCH_QUERY_LENGTH)
}

/**
 * 给异步搜索添加超时保护，避免 UI 一直挂起在 loading 状态
 */
async function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  timeoutMessage: string
): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_resolve, reject) => {
        timeoutId = setTimeout(() => reject(new Error(timeoutMessage)), timeoutMs)
      }),
    ])
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  }
}

// ============================================
// Methods - Search
// ============================================

/**
 * 执行搜索
 * @validates Requirements 6.7, 8.5
 */
async function performSearch(): Promise<void> {
  const keyword = buildSafeSearchKeyword(searchQuery.value)
  
  if (!keyword) {
    searchResults.value = []
    totalCount.value = 0
    searchTimeMs.value = 0
    selectedIndex.value = 0
    return
  }

  const currentRequestId = ++searchRequestId
  isSearching.value = true
  isTimeout.value = false

  try {
    const query: SearchQuery = {
      keyword,
      matchMode: 'fuzzy',
      sortBy: 'relevance',
      sortOrder: 'desc',
      limit: 100,
      offset: 0,
    }

    const response = await withTimeout(
      invoke<SearchResponse>('file_search', { query }),
      SEARCH_TIMEOUT_MS,
      '搜索超时，请缩短关键词后重试'
    )

    // 检查是否是最新的请求
    if (currentRequestId !== searchRequestId) {
      return
    }

    searchResults.value = response.results
    totalCount.value = response.totalCount
    searchTimeMs.value = response.searchTimeMs
    selectedIndex.value = 0

    // 保存状态到 store（用于状态恢复）
    fileSearchStore.saveState(
      keyword,
      response.results,
      response.totalCount,
      response.searchTimeMs,
      0
    )

    // 滚动到顶部
    if (resultsContainerRef.value) {
      resultsContainerRef.value.scrollTop = 0
    }
  } catch (error) {
    console.error('Search failed:', error)
    // 如果是最新请求才显示错误
    if (currentRequestId === searchRequestId) {
      const isTimeoutError = error instanceof Error && error.message.includes('超时')
      isTimeout.value = isTimeoutError
      searchResults.value = []
      totalCount.value = 0
      searchTimeMs.value = 0
    }
  } finally {
    if (currentRequestId === searchRequestId) {
      isSearching.value = false
    }
  }
}

/**
 * 处理搜索输入（防抖）
 */
function handleSearchInput(): void {
  if (searchQuery.value.length > MAX_SEARCH_QUERY_LENGTH * 2) {
    searchQuery.value = buildSafeSearchKeyword(searchQuery.value)
  }

  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    performSearch()
  }, SEARCH_DEBOUNCE_MS)
}

/**
 * 清除搜索
 */
function handleClearSearch(): void {
  searchQuery.value = ''
  searchResults.value = []
  totalCount.value = 0
  searchTimeMs.value = 0
  selectedIndex.value = 0
  searchInputRef.value?.focus()
}

/**
 * 获取服务状态
 */
async function fetchServiceStatus(): Promise<void> {
  try {
    const status = await invoke<ServiceStatus>('get_search_service_status')
    serviceStatus.value = status
  } catch (error) {
    console.error('Failed to get service status:', error)
    serviceStatus.value = null
  }
}

// ============================================
// Methods - Keyboard Navigation
// ============================================

/**
 * 向下导航
 * @validates Requirements 6.6
 */
function navigateDown(): void {
  if (searchResults.value.length === 0) return
  selectedIndex.value = (selectedIndex.value + 1) % searchResults.value.length
  scrollSelectedIntoView()
}

/**
 * 向上导航
 * @validates Requirements 6.6
 */
function navigateUp(): void {
  if (searchResults.value.length === 0) return
  selectedIndex.value = (selectedIndex.value - 1 + searchResults.value.length) % searchResults.value.length
  scrollSelectedIntoView()
}

/**
 * 处理 Enter 键
 * @validates Requirements 6.2, 6.6
 */
function handleEnter(event: KeyboardEvent): void {
  if (searchResults.value.length === 0) return
  
  const selectedResult = searchResults.value[selectedIndex.value]
  if (!selectedResult) return

  if (event.ctrlKey) {
    // Ctrl+Enter: 打开文件夹
    openFolder(selectedResult)
    emit('open-folder', selectedResult)
  } else {
    // Enter: 打开文件
    openFile(selectedResult)
    emit('open', selectedResult)
  }
}

/**
 * 处理全局键盘事件
 */
function handleKeyDown(event: KeyboardEvent): void {
  // 已在输入框中处理的按键不再处理
  if (event.target === searchInputRef.value) return

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      navigateDown()
      break
    case 'ArrowUp':
      event.preventDefault()
      navigateUp()
      break
    case 'Enter':
      event.preventDefault()
      handleEnter(event)
      break
    case 'Escape':
      event.preventDefault()
      handleClose()
      break
  }
}

/**
 * 全局 Esc 兜底监听（捕获阶段）
 * 防止焦点丢失时 Esc 失效
 */
function handleWindowEscape(event: KeyboardEvent): void {
  if (!props.visible || event.key !== 'Escape') {
    return
  }
  event.preventDefault()
  event.stopPropagation()
  handleClose()
}

/**
 * 滚动选中项到可视区域
 */
function scrollSelectedIntoView(): void {
  nextTick(() => {
    const selectedEl = resultRefs.value[selectedIndex.value]
    if (selectedEl) {
      selectedEl.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      })
    }
  })
}

/**
 * 设置结果项引用
 */
function setResultRef(el: Element | ComponentPublicInstance | null, index: number): void {
  resultRefs.value[index] = el as HTMLElement | null
}

// ============================================
// Methods - Result Actions
// ============================================

/**
 * 处理结果项点击
 */
function handleResultClick(result: SearchResult): void {
  emit('select', result)
}

/**
 * 处理结果项双击
 * @validates Requirements 6.2
 */
function handleResultDoubleClick(result: SearchResult): void {
  openFile(result)
  emit('open', result)
}

/**
 * 处理结果项右键菜单
 * @validates Requirements 6.3
 */
function handleResultContextMenu(event: MouseEvent, result: SearchResult): void {
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    result,
  }
}

/**
 * 关闭右键菜单
 */
function closeContextMenu(): void {
  contextMenu.value.visible = false
}

/**
 * 处理右键菜单选择
 * @validates Requirements 6.2, 6.3
 */
async function handleContextMenuSelect(item: ContextMenuItem): Promise<void> {
  const result = contextMenu.value.result
  if (!result) return

  switch (item.id) {
    case 'open':
      await openFile(result)
      break
    case 'open-folder':
      await openFolder(result)
      break
    case 'copy-path':
      await copyPath(result)
      break
  }
}

/**
 * 打开文件（使用默认程序）
 * @validates Requirements 6.2
 */
async function openFile(result: SearchResult): Promise<void> {
  try {
    await openPath(result.path)
  } catch (error) {
    console.error('Failed to open file:', error)
  }
}

/**
 * 打开文件所在文件夹
 * @validates Requirements 6.3
 */
async function openFolder(result: SearchResult): Promise<void> {
  try {
    await revealItemInDir(result.path)
  } catch (error) {
    console.error('Failed to reveal in folder:', error)
  }
}

/**
 * 复制文件路径到剪贴板
 * @validates Requirements 6.3
 */
async function copyPath(result: SearchResult): Promise<void> {
  try {
    await writeText(result.path)
  } catch (error) {
    console.error('Failed to copy path:', error)
  }
}

/**
 * 关闭对话框
 */
function handleClose(): void {
  // 失效当前/历史请求，避免关闭后旧请求回写状态
  searchRequestId += 1
  isSearching.value = false
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
  emit('close')
}

// ============================================
// Methods - Formatting
// ============================================

/**
 * 获取文件图标
 * @validates Requirements 6.1
 */
function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  
  const iconMap: Record<string, string> = {
    // 文档
    pdf: '📕',
    doc: '📘',
    docx: '📘',
    xls: '📗',
    xlsx: '📗',
    ppt: '📙',
    pptx: '📙',
    txt: '📄',
    md: '📝',
    // 图片
    jpg: '🖼️',
    jpeg: '🖼️',
    png: '🖼️',
    gif: '🖼️',
    bmp: '🖼️',
    svg: '🖼️',
    webp: '🖼️',
    // 视频
    mp4: '🎬',
    avi: '🎬',
    mkv: '🎬',
    mov: '🎬',
    wmv: '🎬',
    // 音频
    mp3: '🎵',
    wav: '🎵',
    flac: '🎵',
    aac: '🎵',
    // 压缩包
    zip: '📦',
    rar: '📦',
    '7z': '📦',
    tar: '📦',
    gz: '📦',
    // 代码
    js: '📜',
    ts: '📜',
    py: '🐍',
    rs: '🦀',
    vue: '💚',
    html: '🌐',
    css: '🎨',
    json: '📋',
    // 可执行文件
    exe: '⚙️',
    msi: '⚙️',
    bat: '⚙️',
    sh: '⚙️',
  }

  return iconMap[ext] || '📄'
}

/**
 * 格式化文件大小
 * @validates Requirements 6.1
 */
function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/**
 * 格式化日期
 * @validates Requirements 6.1
 */
function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  // 今天
  if (diff < 24 * 60 * 60 * 1000 && date.getDate() === now.getDate()) {
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  // 昨天
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (
    date.getDate() === yesterday.getDate() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getFullYear() === yesterday.getFullYear()
  ) {
    return '昨天'
  }

  // 本周
  if (diff < 7 * 24 * 60 * 60 * 1000) {
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return weekdays[date.getDay()]
  }

  // 今年
  if (date.getFullYear() === now.getFullYear()) {
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
    })
  }

  // 更早
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * 截断路径显示
 */
function truncatePath(path: string): string {
  const maxLength = 60
  if (path.length <= maxLength) return path
  
  // 保留开头的盘符和结尾的文件名
  const parts = path.split('\\')
  if (parts.length <= 3) return path
  
  const drive = parts[0]
  const filename = parts[parts.length - 1]
  const parent = parts[parts.length - 2]
  
  return `${drive}\\...\\${parent}\\${filename}`
}

// ============================================
// Lifecycle
// ============================================

// 监听 visible 变化
watch(
  () => props.visible,
  async (newVisible) => {
    if (newVisible) {
      window.addEventListener('keydown', handleWindowEscape, true)
      // 打开对话框时
      // 优先使用 initialQuery，否则尝试从 store 恢复
      if (props.initialQuery) {
        searchQuery.value = buildSafeSearchKeyword(props.initialQuery)
      } else if (fileSearchStore.hasValidState) {
        // 从 store 恢复状态
        const state = fileSearchStore.getState()
        searchQuery.value = buildSafeSearchKeyword(state.query)
        searchResults.value = state.results
        totalCount.value = state.totalCount
        searchTimeMs.value = state.searchTimeMs
        selectedIndex.value = state.selectedIndex
      } else {
        // 尝试从 localStorage 恢复查询关键词
        const savedQuery = fileSearchStore.initialize()
        searchQuery.value = buildSafeSearchKeyword(savedQuery)
      }
      
      // 聚焦搜索框
      await nextTick()
      searchInputRef.value?.focus()
      searchInputRef.value?.select()
      
      // 获取服务状态
      fetchServiceStatus()
      
      // 如果有查询但没有结果，执行搜索
      if (searchQuery.value && searchResults.value.length === 0) {
        performSearch()
      }
    } else {
      window.removeEventListener('keydown', handleWindowEscape, true)
      // 关闭对话框时清理定时器（但保留状态）
      if (searchDebounceTimer) {
        clearTimeout(searchDebounceTimer)
        searchDebounceTimer = null
      }
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  window.removeEventListener('keydown', handleWindowEscape, true)
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
})

// ============================================
// Expose
// ============================================

defineExpose({
  /** 聚焦搜索框 */
  focus: () => searchInputRef.value?.focus(),
  /** 清除搜索 */
  clear: handleClearSearch,
  /** 执行搜索 */
  search: performSearch,
})
</script>


<style scoped>
/* ============================================
 * CSS Variables
 * ============================================ */
.search-dialog-overlay {
  --bg-overlay: var(--color-bg-overlay);
  --bg-dialog: var(--color-bg-elevated);
  --bg-input: var(--color-surface-subtle);
  --bg-hover: var(--color-surface-muted);
  --bg-selected: var(--color-accent-light);
  --text-primary: var(--color-text-primary);
  --text-secondary: var(--color-text-secondary);
  --text-muted: var(--color-text-tertiary);
  --accent-primary: var(--color-accent);
  --accent-success: var(--color-success);
  --accent-warning: var(--color-warning);
  --accent-error: var(--color-error);
  --border-color: var(--color-border);
  --border-focus: var(--color-accent);
  --shadow-dialog: var(--shadow-lg);
}

/* ============================================
 * Overlay & Dialog
 * ============================================ */
.search-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 10vh;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.search-dialog {
  width: 680px;
  max-width: 90vw;
  max-height: 70vh;
  background: var(--bg-dialog);
  border-radius: 12px;
  box-shadow: var(--shadow-dialog);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

/* ============================================
 * Search Header
 * ============================================ */
.search-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.search-input-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-input);
  border-radius: 8px;
  border: 1px solid transparent;
  transition: border-color 0.15s ease;
}

.search-input-wrapper:focus-within {
  border-color: var(--border-focus);
}

.search-icon {
  font-size: 16px;
  opacity: 0.6;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 15px;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.clear-btn,
.close-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.1s, color 0.1s;
  flex-shrink: 0;
}

.clear-btn:hover,
.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ============================================
 * Status Bar
 * ============================================ */
.search-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: var(--color-surface-subtle);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  flex-shrink: 0;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-searching {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--accent-primary);
}

.status-results {
  color: var(--text-secondary);
}

.status-results strong {
  color: var(--text-primary);
}

.search-time {
  color: var(--text-muted);
}

.status-empty {
  color: var(--text-muted);
}

.status-timeout {
  color: var(--accent-warning);
}

.status-hint {
  color: var(--text-muted);
}

.status-right {
  display: flex;
  align-items: center;
}

.service-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.service-status.status-running {
  background: var(--color-success-light);
  color: var(--accent-success);
}

.service-status.status-scanning {
  background: var(--color-warning-light);
  color: var(--accent-warning);
}

.service-status.status-pending {
  background: var(--color-accent-light);
  color: var(--accent-primary);
}

.service-status.status-stopped {
  background: var(--color-error-light);
  color: var(--accent-error);
}

/* ============================================
 * Search Results
 * ============================================ */
.search-results {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 200px;
  max-height: 400px;
}

.search-results::-webkit-scrollbar {
  width: 6px;
}

.search-results::-webkit-scrollbar-track {
  background: transparent;
}

.search-results::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.search-results::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  height: 100%;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-border);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-spinner.large {
  width: 32px;
  height: 32px;
  border-width: 3px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-text {
  color: var(--text-muted);
  font-size: 13px;
}

/* Empty State */
.empty-state,
.initial-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  height: 100%;
}

.empty-icon,
.initial-icon {
  font-size: 40px;
  opacity: 0.5;
}

.empty-text,
.initial-text {
  color: var(--text-muted);
  font-size: 14px;
}

.empty-hint {
  color: var(--text-muted);
  font-size: 12px;
  opacity: 0.7;
}

.keyboard-hints {
  display: flex;
  gap: 16px;
  margin-top: 12px;
}

.hint-item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

kbd {
  display: inline-block;
  padding: 2px 6px;
  background: var(--color-surface-muted);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-family: inherit;
  font-size: 10px;
  color: var(--text-secondary);
}

/* Result Item */
.result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background-color 0.1s;
  border-bottom: 1px solid var(--color-surface-subtle);
}

.result-item:hover {
  background: var(--bg-hover);
}

.result-item.is-selected {
  background: var(--bg-selected);
}

.result-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.result-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.result-name {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-path {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-meta {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.result-size {
  color: var(--text-secondary);
  font-size: 11px;
}

.result-date {
  color: var(--text-muted);
  font-size: 10px;
}

/* ============================================
 * Footer
 * ============================================ */
.search-footer {
  padding: 8px 16px;
  background: var(--color-surface-subtle);
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.footer-hints {
  display: flex;
  justify-content: center;
  gap: 20px;
}

.footer-hints .hint-item {
  font-size: 11px;
}

/* ============================================
 * Transitions
 * ============================================ */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.15s ease;
}

.dialog-fade-enter-active .search-dialog,
.dialog-fade-leave-active .search-dialog {
  transition: transform 0.15s ease, opacity 0.15s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-from .search-dialog,
.dialog-fade-leave-to .search-dialog {
  transform: translateY(-20px);
  opacity: 0;
}
</style>
