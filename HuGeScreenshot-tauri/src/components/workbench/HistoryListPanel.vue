<template>
  <div class="history-list-panel">
    <!-- 头部：标题和总数 -->
    <div class="panel-header">
      <div class="header-title">
        <span class="title-icon icon-container" v-html="getIcon('camera')"></span>
        <span class="title-text">截图历史</span>
        <span class="title-count">({{ displayCount }})</span>
      </div>
      <div class="header-actions">
        <!-- 新建空白文档按钮 -->
        <button
          class="action-btn new-doc-btn"
          title="新建空白文档"
          @click="handleCreateBlankDoc"
        >
          ➕
        </button>
        <!-- 文件搜索按钮 @validates Requirements 8.3 -->
        <button
          class="action-btn file-search-btn"
          title="文件搜索 (Alt+Space)"
          @click="handleOpenFileSearch"
        >
          <span class="btn-icon" v-html="getIcon('file-search')"></span>
        </button>
        <button
          class="action-btn refresh-btn"
          title="刷新"
          :disabled="isLoading"
          @click="handleRefresh"
        >
          <span class="btn-icon" :class="{ 'is-spinning': isLoading }" v-html="getIcon('refresh')"></span>
        </button>
        <button
          class="action-btn clear-btn"
          title="清空未钉住的记录"
          @click="handleClearUnpinned"
        >
          🗑️
        </button>
      </div>
    </div>

    <!-- 搜索和过滤栏 -->
    <div class="filter-bar">
      <!-- 搜索框 -->
      <div class="search-box">
        <span class="search-icon icon-container" v-html="getIcon('search')"></span>
        <input
          ref="searchInputRef"
          v-model="localSearchQuery"
          type="text"
          class="search-input"
          placeholder="搜索截图、文件..."
          @input="handleSearchInput"
          @keydown.enter="handleSearchEnter"
        />
        <button
          v-if="localSearchQuery"
          class="clear-btn"
          @click="handleClearSearch"
        >
          ✕
        </button>
      </div>

      <!-- 日期过滤 -->
      <select
        v-model="localDateFilter"
        class="filter-select"
        @change="handleDateFilterChange"
      >
        <option value="all">全部时间</option>
        <option value="today">今天</option>
        <option value="week">本周</option>
        <option value="month">本月</option>
      </select>
    </div>

    <!-- 虚拟滚动列表容器 -->
    <div
      ref="listContainerRef"
      class="list-container"
      @scroll.passive="handleScroll"
    >
      <!-- 加载状态（仅无搜索时显示） -->
      <div v-if="isLoading && filteredItems.length === 0 && !localSearchQuery.trim()" class="loading-state">
        <div class="loading-spinner" />
        <span class="loading-text">加载中...</span>
      </div>

      <!-- ========== 搜索模式：分段展示截图 + 文件搜索 ========== -->
      <template v-else-if="localSearchQuery.trim()">
        <!-- 第一段：截图/剪贴板历史 -->
        <div class="search-section">
          <div class="section-header">
            <span class="section-icon icon-container" v-html="getIcon('camera')"></span>
            <span class="section-title">截图/剪贴板</span>
            <span class="section-count">({{ filteredItems.length }})</span>
          </div>
          <template v-if="filteredItems.length > 0">
            <div
              v-for="item in filteredItems"
              :key="item.id"
              class="list-item"
              :class="{ 'is-selected': item.id === selectedId }"
              :data-item-id="item.id"
              @click="handleItemClick(item)"
              @dblclick="handleItemDoubleClick(item)"
              @mouseenter="handleItemMouseEnter($event, item)"
              @mouseleave="handleItemMouseLeave"
              @contextmenu.prevent="handleContextMenu($event, item)"
            >
              <div class="item-thumbnail">
                <template v-if="item.contentType === 'text'">
                  <div class="thumbnail-text-icon">
                    <span style="font-size: 20px;">📋</span>
                  </div>
                </template>
                <template v-else>
                  <img
                    v-if="getThumbnailSrc(item)"
                    :src="getThumbnailSrc(item)"
                    :alt="item.ocrText || '截图'"
                    loading="lazy"
                    @error="handleImageError($event, item)"
                  />
                  <div v-else class="thumbnail-placeholder">
                    <span class="placeholder-icon icon-container" v-html="getIcon('image')"></span>
                  </div>
                </template>
              </div>
              <div class="item-info">
                <div class="item-header">
                  <span class="item-date">{{ formatDate(item.createdAt) }}</span>
                  <span v-if="item.contentType !== 'text'" class="item-size">{{ formatSize(item.fileSize) }}</span>
                  <span v-else class="item-size" style="color: var(--color-accent);">文字</span>
                </div>
                <div v-if="item.contentType !== 'text'" class="item-dimensions">{{ item.width }} × {{ item.height }}</div>
                <div v-if="item.contentType === 'text' && item.textContent" class="item-ocr-preview" :title="item.textContent">{{ truncateText(item.textContent, 60) }}</div>
                <div v-else-if="item.ocrText" class="item-ocr-preview" :title="item.ocrText">{{ truncateText(item.ocrText, 40) }}</div>
              </div>
              <span v-if="item.isPinned" class="pin-indicator" title="已钉住" @click.stop="handleTogglePin(item.id)">📌</span>
            </div>
          </template>
          <div v-else class="section-empty">
            <span>无匹配的截图记录</span>
          </div>
        </div>

        <!-- 第二段：文件搜索结果 -->
        <div class="search-section">
          <div class="section-header">
            <span class="section-icon">📁</span>
            <span class="section-title">文件搜索</span>
            <span v-if="!isFileSearching && fileSearchResults.length > 0" class="section-count">
              ({{ fileSearchTotalCount }}<span v-if="fileSearchTimeMs > 0" class="section-time">, {{ fileSearchTimeMs }}ms</span>)
            </span>
            <div v-if="isFileSearching" class="section-loading-indicator">
              <div class="loading-spinner small"></div>
            </div>
          </div>
          <!-- 搜索中 -->
          <div v-if="isFileSearching && fileSearchResults.length === 0" class="section-loading">
            <div class="loading-spinner small"></div>
            <span>搜索中...</span>
          </div>
          <!-- 有结果 -->
          <template v-else-if="fileSearchResults.length > 0">
            <div
              v-for="result in fileSearchResults"
              :key="result.fileId"
              class="file-result-item"
              :title="result.path"
              @click="handleFileResultClick(result)"
              @dblclick="handleFileResultDblClick(result)"
              @contextmenu.prevent="handleFileResultContextMenu($event, result)"
            >
              <div class="file-result-icon">{{ getFileIcon(result.name) }}</div>
              <div class="file-result-info">
                <div class="file-result-name">{{ result.name }}</div>
                <div class="file-result-path">{{ truncateFilePath(result.path) }}</div>
              </div>
              <div class="file-result-meta">
                <span class="file-result-size">{{ formatFileSize(result.size) }}</span>
              </div>
            </div>
            <!-- 查看更多 -->
            <div v-if="fileSearchTotalCount > fileSearchResults.length" class="view-more-btn" @click="handleViewMoreFileResults">
              查看全部 {{ fileSearchTotalCount }} 个文件结果 →
            </div>
          </template>
          <!-- 无结果 -->
          <div v-else class="section-empty">
            <span>无匹配文件</span>
          </div>
        </div>
      </template>

      <!-- ========== 正常模式：虚拟滚动列表 ========== -->

      <!-- 空状态 -->
      <div v-else-if="filteredItems.length === 0" class="empty-state">
        <span class="empty-icon icon-container" v-html="getIcon('empty')"></span>
        <span class="empty-text">暂无截图历史</span>
      </div>

      <!-- 虚拟滚动内容 -->
      <template v-else>
        <!-- 占位元素：撑起总高度 -->
        <div class="scroll-phantom" :style="{ height: `${totalHeight}px` }" />
        
        <!-- 可见项目列表 -->
        <div
          class="visible-list"
          :style="{ transform: `translateY(${offsetY}px)` }"
        >
          <div
            v-for="item in visibleItems"
            :key="item.id"
            class="list-item"
            :class="{ 'is-selected': item.id === selectedId }"
            :data-item-id="item.id"
            @click="handleItemClick(item)"
            @dblclick="handleItemDoubleClick(item)"
            @mouseenter="handleItemMouseEnter($event, item)"
            @mouseleave="handleItemMouseLeave"
            @contextmenu.prevent="handleContextMenu($event, item)"
          >
            <div class="item-thumbnail">
              <template v-if="item.contentType === 'text'">
                <div class="thumbnail-text-icon">
                  <span style="font-size: 20px;">📋</span>
                </div>
              </template>
              <template v-else>
                <img
                  v-if="getThumbnailSrc(item)"
                  :src="getThumbnailSrc(item)"
                  :alt="item.ocrText || '截图'"
                  loading="lazy"
                  @error="handleImageError($event, item)"
                />
                <div v-else class="thumbnail-placeholder">
                  <span class="placeholder-icon icon-container" v-html="getIcon('image')"></span>
                </div>
              </template>
            </div>
            <div class="item-info">
              <div class="item-header">
                <span class="item-date">{{ formatDate(item.createdAt) }}</span>
                <span v-if="item.contentType !== 'text'" class="item-size">{{ formatSize(item.fileSize) }}</span>
                <span v-else class="item-size" style="color: var(--color-accent);">文字</span>
              </div>
              <div v-if="item.contentType !== 'text'" class="item-dimensions">
                {{ item.width }} × {{ item.height }}
              </div>
              <div v-if="item.contentType === 'text' && item.textContent" class="item-ocr-preview" :title="item.textContent">
                {{ truncateText(item.textContent, 60) }}
              </div>
              <div v-else-if="item.ocrText" class="item-ocr-preview" :title="item.ocrText">
                {{ truncateText(item.ocrText, 40) }}
              </div>
            </div>
            <span v-if="item.isPinned" class="pin-indicator" title="已钉住" @click.stop="handleTogglePin(item.id)">📌</span>
          </div>
        </div>

        <!-- 加载更多指示器 -->
        <div v-if="hasMore && !isLoading" class="load-more-indicator">
          <span>滚动加载更多...</span>
        </div>
        <div v-if="isLoading && filteredItems.length > 0" class="loading-more">
          <div class="loading-spinner small" />
        </div>
      </template>
    </div>

    <!-- 悬浮预览窗口 -->
    <Teleport to="body">
      <Transition name="preview-fade">
        <div
          v-if="hoveredItem && previewSrc"
          class="hover-preview-card"
          :style="previewPosition"
        >
          <img :src="previewSrc" class="preview-card-image" />
          <div class="preview-card-info">
            <div class="preview-info-row">
              <span class="info-label">尺寸</span>
              <span class="info-value">{{ hoveredItem.width }} × {{ hoveredItem.height }}</span>
            </div>
            <div class="preview-info-row">
              <span class="info-label">大小</span>
              <span class="info-value">{{ formatSize(hoveredItem.fileSize) }}</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 历史记录右键菜单 -->
    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="context-menu-overlay"
        @click="closeContextMenu"
        @contextmenu.prevent="closeContextMenu"
      />
      <div
        v-if="contextMenu.visible"
        class="context-menu"
        :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      >
        <div class="context-menu-item" @click="contextMenuAction('pin')">
          {{ contextMenu.item?.isPinned ? '📌 取消钉住' : '📍 钉住' }}
        </div>
        <div class="context-menu-item" @click="contextMenuAction('copy')">
          📋 复制内容
        </div>
        <div v-if="contextMenu.item?.contentType !== 'text'" class="context-menu-item" @click="contextMenuAction('ocr')">
          🔍 重新 OCR
        </div>
        <div class="context-menu-separator" />
        <div class="context-menu-item danger" @click="contextMenuAction('delete')">
          🗑️ 删除
        </div>
      </div>
    </Teleport>

    <!-- 文件搜索右键菜单 -->
    <Teleport to="body">
      <div
        v-if="fileContextMenu.visible"
        class="context-menu-overlay"
        @click="closeFileContextMenu"
        @contextmenu.prevent="closeFileContextMenu"
      />
      <div
        v-if="fileContextMenu.visible"
        class="context-menu"
        :style="{ top: fileContextMenu.y + 'px', left: fileContextMenu.x + 'px' }"
      >
        <div class="context-menu-item" @click="fileContextMenuAction('open')">
          📂 打开文件
        </div>
        <div class="context-menu-item" @click="fileContextMenuAction('open-folder')">
          📁 打开所在文件夹
        </div>
        <div class="context-menu-separator" />
        <div class="context-menu-item" @click="fileContextMenuAction('copy-path')">
          📋 复制路径
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * 历史记录列表面板组件
 *
 * 功能：
 * - 显示截图历史记录列表（虚拟滚动）
 * - 搜索和过滤（按日期、OCR 文本）
 * - 选择和导航
 *
 * @validates Requirements 2.1, 2.3, 2.5
 */

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { convertFileSrc, invoke } from '@tauri-apps/api/core'
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import { useHistoryStore } from '@/stores/history'
import { useWorkbenchStore, type DateFilter } from '@/stores/workbench'
import type { HistoryItem } from '@/types'

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 当前选中的项目 ID */
  selectedId: number | null
}

const props = withDefaults(defineProps<Props>(), {
  selectedId: null,
})

const emit = defineEmits<{
  /** 选择项目事件 */
  (e: 'select', id: number): void
  /** 双击项目事件 */
  (e: 'double-click', id: number): void
  /** 打开文件搜索事件 @validates Requirements 8.3
   *  @param query 可选的初始查询关键词（从"查看全部"入口打开时携带当前侧栏搜索词）
   */
  (e: 'open-file-search', query?: string): void
  /** 新建空白文档事件 */
  (e: 'blank-doc-created', id: number): void
}>()

// ============================================
// Stores
// ============================================

const historyStore = useHistoryStore()
const workbenchStore = useWorkbenchStore()

// ============================================
// Refs
// ============================================

/** 列表容器引用 */
const listContainerRef = ref<HTMLDivElement | null>(null)

/** 搜索输入框引用 */
const searchInputRef = ref<HTMLInputElement | null>(null)

// ============================================
// Virtual Scrolling State
// ============================================

/** 每个项目的固定高度 (px) */
const ITEM_HEIGHT = 80

/** 缓冲区项目数量（上下各多渲染几个） */
const BUFFER_SIZE = 5

/** 当前滚动位置 */
const scrollTop = ref(0)

/** 容器高度 */
const containerHeight = ref(400)

// ============================================
// Local State
// ============================================

/** 本地搜索查询（用于防抖） */
const localSearchQuery = ref('')

/** 本地日期过滤 */
const localDateFilter = ref<DateFilter>('all')

/** 搜索防抖定时器 */
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

/** 图片加载错误记录 */
const imageErrors = ref<Set<number>>(new Set())

// ============================================
// File Search Types & State
// ============================================

/** 文件搜索结果项 */
interface FileSearchResult {
  fileId: string
  name: string
  path: string
  size: number
  modified: string
  isDirectory: boolean
  score: number
  matchIndices: [number, number][]
}

/** 文件搜索响应 */
interface FileSearchResponse {
  results: FileSearchResult[]
  totalCount: number
  searchTimeMs: number
}

/** 文件搜索结果列表 */
const fileSearchResults = ref<FileSearchResult[]>([])

/** 文件搜索结果总数 */
const fileSearchTotalCount = ref(0)

/** 文件搜索耗时 */
const fileSearchTimeMs = ref(0)

/** 是否正在文件搜索 */
const isFileSearching = ref(false)

/** 文件搜索防抖定时器 */
let fileSearchDebounceTimer: ReturnType<typeof setTimeout> | null = null

/** 文件搜索请求计数器（取消过期请求） */
let fileSearchRequestId = 0

/** 侧边栏文件搜索最大关键词长度（防止粘贴日志导致卡顿） */
const MAX_FILE_SEARCH_QUERY_LENGTH = 120

/** 长文本提取关键词时最多保留 token 数 */
const MAX_FILE_SEARCH_TOKENS = 6

/** 文件搜索超时时间 */
const FILE_SEARCH_TIMEOUT_MS = 2500

/** 文件搜索右键菜单 */
const fileContextMenu = ref<{ visible: boolean; x: number; y: number; result: FileSearchResult | null }>({
  visible: false, x: 0, y: 0, result: null
})

// ============================================
// Hover Preview State
// ============================================

/** 当前悬停的项目 */
const hoveredItem = ref<HistoryItem | null>(null)

/** 预览窗口位置 */
const previewPosition = ref({ top: '0px', left: '0px' })

/** 预览图片地址 */
const previewSrc = computed(() => {
  if (!hoveredItem.value) return undefined
  return getThumbnailSrc(hoveredItem.value)
})

// ============================================
// Computed - Store Data
// ============================================

/** 历史记录项目列表 */
const items = computed(() => historyStore.items)

/** 总记录数 */
const totalCount = computed(() => historyStore.totalCount)

/** 是否还有更多 */
const hasMore = computed(() => historyStore.hasMore)

/** 是否正在加载 */
const isLoading = computed(() => historyStore.isLoading)

// ============================================
// Computed - Filtering
// ============================================

/**
 * 过滤后的项目列表
 * 根据搜索查询和日期过滤进行本地过滤
 * 自动隐藏文件不存在的记录
 */
const filteredItems = computed(() => {
  let result = items.value

  // 过滤掉文件不存在的图片记录（图片加载失败的项）
  result = result.filter((item) => {
    if (item.contentType === 'text') return true // 文字类型始终保留
    return !imageErrors.value.has(item.id) // 隐藏图片加载失败的项
  })

  // 搜索过滤（OCR 文本和标签）
  if (localSearchQuery.value.trim()) {
    const query = localSearchQuery.value.toLowerCase().trim()
    result = result.filter((item) => {
      const ocrMatch = item.ocrText?.toLowerCase().includes(query)
      const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query))
      return ocrMatch || tagMatch
    })
  }

  return result
})

/**
 * 显示的总数
 * @validates Requirements 2.5
 */
const displayCount = computed(() => {
  if (localSearchQuery.value.trim()) {
    return filteredItems.value.length
  }
  return totalCount.value
})

// ============================================
// Computed - Virtual Scrolling
// ============================================

/**
 * 总高度（用于滚动条）
 */
const totalHeight = computed(() => filteredItems.value.length * ITEM_HEIGHT)

/**
 * 起始索引
 */
const startIndex = computed(() => {
  const index = Math.floor(scrollTop.value / ITEM_HEIGHT)
  return Math.max(0, index - BUFFER_SIZE)
})

/**
 * 可见项目数量
 */
const visibleCount = computed(() => {
  return Math.ceil(containerHeight.value / ITEM_HEIGHT) + BUFFER_SIZE * 2
})

/**
 * 可见项目列表
 * @validates Requirements 2.3
 */
const visibleItems = computed(() => {
  const start = startIndex.value
  const end = Math.min(start + visibleCount.value, filteredItems.value.length)
  return filteredItems.value.slice(start, end)
})

/**
 * Y 轴偏移量（用于定位可见列表）
 */
const offsetY = computed(() => startIndex.value * ITEM_HEIGHT)

// ============================================
// Methods - Formatting
// ============================================

/**
 * 格式化日期
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
  if (date.getDate() === yesterday.getDate() && 
      date.getMonth() === yesterday.getMonth() &&
      date.getFullYear() === yesterday.getFullYear()) {
    return `昨天 ${date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })}`
  }

  // 本周
  if (diff < 7 * 24 * 60 * 60 * 1000) {
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return `${weekdays[date.getDay()]} ${date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })}`
  }

  // 更早
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * 格式化文件大小
 */
function formatSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * 截断文本
 */
// ============================================
// 右键菜单
// ============================================

const contextMenu = ref<{ visible: boolean; x: number; y: number; item: HistoryItem | null }>({
  visible: false, x: 0, y: 0, item: null
})

function handleContextMenu(event: MouseEvent, item: HistoryItem): void {
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    item
  }
}

function closeContextMenu(): void {
  contextMenu.value.visible = false
}

async function contextMenuAction(action: string): Promise<void> {
  const item = contextMenu.value.item
  closeContextMenu()
  if (!item) return

  switch (action) {
    case 'pin':
      await handleTogglePin(item.id)
      break
    case 'copy':
      if (item.textContent) {
        navigator.clipboard.writeText(item.textContent)
      } else if (item.ocrText) {
        navigator.clipboard.writeText(item.ocrText)
      }
      break
    case 'ocr':
      // 先选中该项，再直接触发本地 OCR
      emit('select', item.id)
      if (item.filePath && item.contentType !== 'text') {
        try {
          await workbenchStore.performOcr(item.filePath)
        } catch (error) {
          console.error('[HistoryList] Re-OCR failed:', error)
        }
      }
      break
    case 'delete':
      try {
        await invoke('delete_history_item', { id: item.id })
        await historyStore.loadHistory()
      } catch (error) {
        console.error('[HistoryList] Delete failed:', error)
      }
      break
  }
}

/**
 * 切换钉住状态
 */
async function handleTogglePin(id: number): Promise<void> {
  try {
    await invoke('toggle_pin_history_item', { id })
    // 刷新列表
    await historyStore.loadHistory()
  } catch (error) {
    console.error('[HistoryList] Toggle pin failed:', error)
  }
}

/**
 * 清除所有未钉住的记录
 */
async function handleClearUnpinned(): Promise<void> {
  if (!confirm('确定要清除所有未钉住的记录吗？钉住的记录不会被删除。')) {
    return
  }
  try {
    const count = await invoke<number>('clear_unpinned_history')
    console.log(`[HistoryList] 清除了 ${count} 条记录`)
    await historyStore.loadHistory()
    await historyStore.loadStats()
  } catch (error) {
    console.error('[HistoryList] Clear unpinned failed:', error)
  }
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

/**
 * 获取缩略图 URL
 */
function getThumbnailSrc(item: HistoryItem): string | undefined {
  if (imageErrors.value.has(item.id)) {
    return undefined
  }
  const path = item.thumbnailPath || item.filePath
  if (!path) return undefined
  return convertFileSrc(path)
}

/**
 * 处理图片加载错误
 */
function handleImageError(_event: Event, item: HistoryItem): void {
  imageErrors.value.add(item.id)
}

// ============================================
// Methods - Event Handlers
// ============================================

/**
 * 处理滚动事件
 * 使用 passive 监听器提高性能
 */
function handleScroll(): void {
  if (!listContainerRef.value) return
  
  scrollTop.value = listContainerRef.value.scrollTop

  // 检查是否需要加载更多
  const { scrollHeight, clientHeight } = listContainerRef.value
  if (scrollHeight - scrollTop.value - clientHeight < 200 && hasMore.value && !isLoading.value) {
    historyStore.loadMore()
  }
}

/**
 * 处理项目点击
 */
function handleItemClick(item: HistoryItem): void {
  emit('select', item.id)
}

/**
 * 处理项目双击
 */
function handleItemDoubleClick(item: HistoryItem): void {
  emit('double-click', item.id)
}

/**
 * 处理搜索输入（防抖）
 * 同时触发历史记录过滤和文件搜索
 */
function handleSearchInput(): void {
  if (localSearchQuery.value.length > MAX_FILE_SEARCH_QUERY_LENGTH * 2) {
    localSearchQuery.value = buildSafeFileSearchKeyword(localSearchQuery.value)
  }

  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  if (fileSearchDebounceTimer) {
    clearTimeout(fileSearchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    workbenchStore.setSearchQuery(localSearchQuery.value)
  }, 300)
  // 文件搜索使用稍长的防抖，避免频繁请求
  fileSearchDebounceTimer = setTimeout(() => {
    performFileSearch()
  }, 500)
}

/**
 * 处理搜索回车
 */
function handleSearchEnter(): void {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  if (fileSearchDebounceTimer) {
    clearTimeout(fileSearchDebounceTimer)
  }
  workbenchStore.setSearchQuery(localSearchQuery.value)
  performFileSearch()
}

/**
 * 清除搜索
 */
function handleClearSearch(): void {
  localSearchQuery.value = ''
  workbenchStore.setSearchQuery('')
  // 同时清除文件搜索结果
  fileSearchResults.value = []
  fileSearchTotalCount.value = 0
  fileSearchTimeMs.value = 0
  if (fileSearchDebounceTimer) {
    clearTimeout(fileSearchDebounceTimer)
  }
}

/**
 * 处理日期过滤变化
 */
function handleDateFilterChange(): void {
  workbenchStore.setDateFilter(localDateFilter.value)
  loadHistoryWithFilters()
}

/**
 * 新建空白文档
 * 创建一个空的文字类型记录，方便用户在右侧编辑
 */
async function handleCreateBlankDoc(): Promise<void> {
  try {
    const newItem = await invoke<{ id: number }>('add_history_item', {
      item: {
        filePath: '',
        width: 0,
        height: 0,
        contentType: 'text',
        textContent: '',
        ocrText: '',
      }
    })
    // 刷新列表并选中新创建的记录
    await historyStore.loadHistory()
    await historyStore.loadStats()
    emit('select', newItem.id)
    emit('blank-doc-created', newItem.id)
  } catch (error) {
    console.error('[HistoryList] Create blank doc failed:', error)
  }
}

/**
 * 处理打开文件搜索
 * @validates Requirements 8.3
 */
function handleOpenFileSearch(): void {
  emit('open-file-search')
}

/**
 * 处理刷新
 */
async function handleRefresh(): Promise<void> {
  await refresh()
}

// ============================================
// Methods - Hover Preview
// ============================================

/**
 * 处理鼠标进入项目
 * 计算预览窗口位置（显示在鼠标右侧）
 */
function handleItemMouseEnter(event: MouseEvent, item: HistoryItem): void {
  hoveredItem.value = item
  
  // 计算位置
  const target = event.target as HTMLElement
  const rect = target.getBoundingClientRect()
  
  // 显示在列表项右侧 16px 处
  const left = rect.right + 16
  
  // 如果超出屏幕右侧，显示在左侧（虽然不太可能，因为左侧是列表）
  // 垂直居中于列表项，但要防止超出屏幕上下边界
  let top = rect.top + rect.height / 2 - 100 // 假设预览卡片高度约 200px
  
  // 边界检查
  const windowHeight = window.innerHeight
  const cardHeight = 220 // 预估高度
  
  if (top < 10) top = 10
  if (top + cardHeight > windowHeight - 10) top = windowHeight - cardHeight - 10
  
  previewPosition.value = {
    top: `${top}px`,
    left: `${left}px`
  }
}

/**
 * 处理鼠标离开项目
 */
function handleItemMouseLeave(): void {
  hoveredItem.value = null
}

// ============================================
// Methods - File Search
// ============================================

/**
 * 构建安全关键词，避免把整段日志传给文件搜索
 */
function buildSafeFileSearchKeyword(raw: string): string {
  const normalized = raw.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''

  if (normalized.length <= MAX_FILE_SEARCH_QUERY_LENGTH) {
    return normalized
  }

  const matched = normalized.match(/[\u4e00-\u9fff]{2,}|[A-Za-z0-9._-]{2,}/g) ?? []
  const seen = new Set<string>()
  const tokens: string[] = []

  for (const token of matched) {
    const key = token.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    tokens.push(token)
    if (tokens.length >= MAX_FILE_SEARCH_TOKENS) break
  }

  if (tokens.length > 0) {
    return tokens.join(' ').slice(0, MAX_FILE_SEARCH_QUERY_LENGTH).trim()
  }

  return normalized.slice(0, MAX_FILE_SEARCH_QUERY_LENGTH)
}

/**
 * Promise 超时保护
 */
async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, timeoutMessage: string): Promise<T> {
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

/**
 * 执行文件搜索
 * 在侧边栏搜索框输入时同步触发，展示在历史记录下方
 */
async function performFileSearch(): Promise<void> {
  const keyword = buildSafeFileSearchKeyword(localSearchQuery.value)
  if (!keyword) {
    fileSearchResults.value = []
    fileSearchTotalCount.value = 0
    fileSearchTimeMs.value = 0
    return
  }

  const currentId = ++fileSearchRequestId
  isFileSearching.value = true

  try {
    const query = {
      keyword,
      matchMode: 'fuzzy',
      sortBy: 'relevance',
      sortOrder: 'desc',
      limit: 15,
      offset: 0,
    }
    const response = await withTimeout(
      invoke<FileSearchResponse>('file_search', { query }),
      FILE_SEARCH_TIMEOUT_MS,
      '文件搜索超时'
    )

    // 检查是否是最新的请求
    if (currentId !== fileSearchRequestId) return

    fileSearchResults.value = response.results
    fileSearchTotalCount.value = response.totalCount
    fileSearchTimeMs.value = response.searchTimeMs
  } catch (error) {
    console.error('[HistoryList] File search failed:', error)
    if (currentId === fileSearchRequestId) {
      fileSearchResults.value = []
      fileSearchTotalCount.value = 0
    }
  } finally {
    if (currentId === fileSearchRequestId) {
      isFileSearching.value = false
    }
  }
}

/**
 * 获取文件图标
 */
function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const iconMap: Record<string, string> = {
    pdf: '📕', doc: '📘', docx: '📘', xls: '📗', xlsx: '📗',
    ppt: '📙', pptx: '📙', txt: '📄', md: '📝',
    jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', bmp: '🖼️', svg: '🖼️', webp: '🖼️',
    mp4: '🎬', avi: '🎬', mkv: '🎬', mov: '🎬',
    mp3: '🎵', wav: '🎵', flac: '🎵',
    zip: '📦', rar: '📦', '7z': '📦',
    js: '📜', ts: '📜', py: '🐍', rs: '🦀', vue: '💚', html: '🌐', css: '🎨', json: '📋',
    exe: '⚙️', msi: '⚙️', bat: '⚙️',
  }
  return iconMap[ext] || '📄'
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/**
 * 截断文件路径
 */
function truncateFilePath(path: string): string {
  const maxLength = 50
  if (path.length <= maxLength) return path
  const parts = path.split('\\')
  if (parts.length <= 3) return path
  const drive = parts[0]
  const filename = parts[parts.length - 1]
  const parent = parts[parts.length - 2]
  return `${drive}\\...\\${parent}\\${filename}`
}

/**
 * 处理文件搜索结果点击 → 打开所在文件夹
 */
async function handleFileResultClick(result: FileSearchResult): Promise<void> {
  try {
    await revealItemInDir(result.path)
  } catch (error) {
    console.error('[HistoryList] Reveal file failed:', error)
  }
}

/**
 * 处理文件搜索结果双击 → 用默认程序打开文件
 */
async function handleFileResultDblClick(result: FileSearchResult): Promise<void> {
  try {
    await openPath(result.path)
  } catch (error) {
    console.error('[HistoryList] Open file failed:', error)
  }
}

/**
 * 处理文件搜索结果右键菜单
 */
function handleFileResultContextMenu(event: MouseEvent, result: FileSearchResult): void {
  fileContextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    result
  }
}

/**
 * 关闭文件右键菜单
 */
function closeFileContextMenu(): void {
  fileContextMenu.value.visible = false
}

/**
 * 文件右键菜单操作
 */
async function fileContextMenuAction(action: string): Promise<void> {
  const result = fileContextMenu.value.result
  closeFileContextMenu()
  if (!result) return

  switch (action) {
    case 'open':
      try { await openPath(result.path) } catch (e) { console.error('[HistoryList] Open file failed:', e) }
      break
    case 'open-folder':
      try { await revealItemInDir(result.path) } catch (e) { console.error('[HistoryList] Reveal failed:', e) }
      break
    case 'copy-path':
      try { await writeText(result.path) } catch (e) { console.error('[HistoryList] Copy path failed:', e) }
      break
  }
}

/**
 * 查看更多文件搜索结果 → 打开文件搜索对话框
 * 携带当前侧栏搜索关键词作为初始查询
 */
function handleViewMoreFileResults(): void {
  emit('open-file-search', localSearchQuery.value)
}

// ============================================
// Methods - Data Loading
// ============================================

/**
 * 获取日期范围
 */
function getDateRange(filter: DateFilter): { startDate?: string; endDate?: string } {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())

  switch (filter) {
    case 'today':
      return {
        startDate: today.toISOString(),
        endDate: new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString(),
      }
    case 'week': {
      const weekStart = new Date(today)
      weekStart.setDate(weekStart.getDate() - weekStart.getDay())
      return {
        startDate: weekStart.toISOString(),
      }
    }
    case 'month': {
      const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
      return {
        startDate: monthStart.toISOString(),
      }
    }
    default:
      return {}
  }
}

/**
 * 加载历史记录（带过滤条件）
 */
async function loadHistoryWithFilters(): Promise<void> {
  const dateRange = getDateRange(localDateFilter.value)
  await historyStore.loadHistory({
    query: localSearchQuery.value || undefined,
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  })
}

// ============================================
// Exposed Methods
// ============================================

/**
 * 刷新列表
 */
async function refresh(): Promise<void> {
  imageErrors.value.clear()
  await historyStore.loadStats()
  await loadHistoryWithFilters()
}

/**
 * 选择下一个项目
 */
function selectNext(): void {
  if (filteredItems.value.length === 0) return

  const currentIndex = filteredItems.value.findIndex(
    (item) => item.id === props.selectedId
  )

  if (currentIndex === -1) {
    // 没有选中项，选择第一个
    emit('select', filteredItems.value[0].id)
  } else if (currentIndex < filteredItems.value.length - 1) {
    // 选择下一个
    emit('select', filteredItems.value[currentIndex + 1].id)
  }

  // 确保选中项可见
  nextTick(() => scrollSelectedIntoView())
}

/**
 * 选择上一个项目
 */
function selectPrevious(): void {
  if (filteredItems.value.length === 0) return

  const currentIndex = filteredItems.value.findIndex(
    (item) => item.id === props.selectedId
  )

  if (currentIndex === -1) {
    // 没有选中项，选择最后一个
    emit('select', filteredItems.value[filteredItems.value.length - 1].id)
  } else if (currentIndex > 0) {
    // 选择上一个
    emit('select', filteredItems.value[currentIndex - 1].id)
  }

  // 确保选中项可见
  nextTick(() => scrollSelectedIntoView())
}

/**
 * 滚动选中项到可视区域
 */
function scrollSelectedIntoView(): void {
  if (props.selectedId === null || !listContainerRef.value) return

  const index = filteredItems.value.findIndex((item) => item.id === props.selectedId)
  if (index === -1) return

  const itemTop = index * ITEM_HEIGHT
  const itemBottom = itemTop + ITEM_HEIGHT
  const viewTop = scrollTop.value
  const viewBottom = viewTop + containerHeight.value

  if (itemTop < viewTop) {
    // 项目在视口上方，滚动到项目位置
    listContainerRef.value.scrollTop = itemTop
  } else if (itemBottom > viewBottom) {
    // 项目在视口下方，滚动使项目底部可见
    listContainerRef.value.scrollTop = itemBottom - containerHeight.value
  }
}

// 暴露方法给父组件
defineExpose({
  refresh,
  selectNext,
  selectPrevious,
})

// ============================================
// Lifecycle
// ============================================

onMounted(() => {
  // 初始化容器高度
  if (listContainerRef.value) {
    containerHeight.value = listContainerRef.value.clientHeight
    
    // 监听容器大小变化
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerHeight.value = entry.contentRect.height
      }
    })
    resizeObserver.observe(listContainerRef.value)
  }

  // 同步 store 状态到本地
  localSearchQuery.value = workbenchStore.searchQuery
  localDateFilter.value = workbenchStore.dateFilter
})

onUnmounted(() => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  if (fileSearchDebounceTimer) {
    clearTimeout(fileSearchDebounceTimer)
  }
})

// 监听 store 中的搜索查询变化
watch(
  () => workbenchStore.searchQuery,
  (newQuery) => {
    if (newQuery !== localSearchQuery.value) {
      localSearchQuery.value = newQuery
    }
  }
)

// 监听 store 中的日期过滤变化
watch(
  () => workbenchStore.dateFilter,
  (newFilter) => {
    if (newFilter !== localDateFilter.value) {
      localDateFilter.value = newFilter
    }
  }
)

/**
 * 获取图标
 */
function getIcon(name: string): string {
  const icons: Record<string, string> = {
    camera: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`,
    'file-search': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><circle cx="12" cy="14" r="4"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`,
    search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    empty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
    image: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  }
  return icons[name] || ''
}
</script>

<style scoped>
.history-list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-family: var(--font-family);
}

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  width: 18px;
  height: 18px;
}

.title-text {
  font-size: 16px;
  font-weight: 600;
}

.title-count {
  color: var(--color-text-tertiary);
  font-size: 13px;
}

/* 头部操作按钮组 @validates Requirements 8.3 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.action-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.1s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-btn :deep(svg) {
  width: 16px; /* Icon size */
  height: 16px;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 新建空白文档按钮 */
.new-doc-btn {
  font-size: 13px !important;
}

.new-doc-btn:hover {
  background: var(--color-accent-light);
  color: var(--color-accent);
}

/* 文件搜索按钮特殊样式 */
.file-search-btn:hover {
  background: var(--color-accent-light);
  color: var(--color-accent);
}

.btn-icon.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 过滤栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--color-input-bg);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.search-box:focus-within {
  background: var(--color-bg-primary);
  box-shadow: 0 0 0 2px var(--color-accent);
}

.search-icon {
  width: 14px;
  height: 14px;
  opacity: 0.6;
}

.search-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-text-primary);
  font-size: 12px;
}

.search-input::placeholder {
  color: var(--color-text-tertiary);
}

.clear-btn {
  padding: 2px 4px;
  background: transparent;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 10px;
  cursor: pointer;
  border-radius: 3px;
}

.clear-btn:hover {
  background: var(--color-surface-muted);
  color: var(--color-text-primary);
}

.filter-select {
  padding: 6px 8px;
  background: var(--color-input-bg);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: 11px;
  cursor: pointer;
  outline: none;
}

.filter-select:focus {
  box-shadow: 0 0 0 2px var(--color-accent);
}

.filter-select option {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

/* 列表容器 - 虚拟滚动 */
.list-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
}

.list-container::-webkit-scrollbar {
  width: 6px;
}

.list-container::-webkit-scrollbar-track {
  background: var(--color-surface-subtle);
}

.list-container::-webkit-scrollbar-thumb {
  background: var(--color-surface-strong);
  border-radius: 3px;
}

.list-container::-webkit-scrollbar-thumb:hover {
  background: var(--color-surface-strong);
}

/* 虚拟滚动占位元素 */
.scroll-phantom {
  position: absolute;
  left: 0;
  top: 0;
  right: 0;
  z-index: -1;
}

/* 可见列表 */
.visible-list {
  position: absolute;
  left: 0;
  top: 0;
  right: 0;
  padding: 4px 8px;
}

/* 列表项 */
.list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 72px;
  padding: 8px 12px;
  margin: 4px 8px; /* 增加左右间距 */
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.1s ease;
  user-select: none;
}

.list-item:hover {
  background: var(--color-bg-tertiary);
}

.list-item.is-selected {
  background: var(--color-accent);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-sm);
}

/* 缩略图 */
.item-thumbnail {
  flex-shrink: 0;
  width: 64px;
  height: 48px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-light);
}

.item-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
}

.thumbnail-text-icon {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
  border-radius: 4px;
}

.placeholder-icon {
  width: 24px;
  height: 24px;
  opacity: 0.5;
}

/* 信息区域 */
.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pin-indicator {
  flex-shrink: 0;
  font-size: 12px;
  cursor: pointer;
  align-self: center;
}

.clear-btn {
  font-size: 16px;
}

/* 右键菜单 */
.context-menu-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9998;
}

.context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 160px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 4px;
  box-shadow: var(--shadow-lg);
}

.context-menu-item {
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-primary);
  transition: background-color 0.1s;
}

.context-menu-item:hover {
  background: var(--color-bg-tertiary);
}

.context-menu-item.danger {
  color: var(--color-error);
}

.context-menu-item.danger:hover {
  background: var(--color-error-light);
}

.context-menu-separator {
  height: 1px;
  background: var(--color-border);
  margin: 4px 8px;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.item-date {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
}

.list-item.is-selected .item-date {
  color: var(--color-text-primary);
}

.item-size {
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.list-item.is-selected .item-size {
  color: var(--color-text-primary);
}

.item-dimensions {
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.list-item.is-selected .item-dimensions {
  color: var(--color-text-primary);
}

.item-ocr-preview {
  color: var(--color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-item.is-selected .item-ocr-preview {
  color: var(--color-text-primary);
}

/* 加载状态 */
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
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-spinner.small {
  width: 16px;
  height: 16px;
  border-width: 2px;
}

.loading-text {
  color: var(--color-text-secondary);
  font-size: 13px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  height: 100%;
}

.empty-icon {
  width: 40px;
  height: 40px;
  opacity: 0.5;
}

.empty-text {
  color: var(--color-text-tertiary);
  font-size: 13px;
  text-align: center;
}

.clear-search-btn {
  margin-top: 8px;
  padding: 6px 14px;
  background: var(--color-accent);
  border: none;
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.1s;
}

.clear-search-btn:hover {
  background: var(--color-accent-hover);
}

/* 加载更多 */
.load-more-indicator {
  display: flex;
  justify-content: center;
  padding: 12px;
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.loading-more {
  display: flex;
  justify-content: center;
  padding: 12px;
}
/* 悬浮预览卡片 */
.hover-preview-card {
  position: fixed;
  z-index: 9999;
  width: 280px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xl);
  padding: 8px;
  pointer-events: none; /* 防止遮挡鼠标导致闪烁 */
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-card-image {
  width: 100%;
  height: auto;
  max-height: 200px;
  object-fit: contain;
  border-radius: 4px;
  background: var(--color-bg-tertiary);
}

.preview-card-info {
  display: flex;
  justify-content: space-between;
  padding: 0 4px;
  font-size: 12px;
}

.preview-info-row {
  display: flex;
  gap: 6px;
}

.info-label {
  color: var(--color-text-tertiary);
}

.info-value {
  color: var(--color-text-secondary);
  font-feature-settings: "tnum";
}

/* 预览淡入淡出动画 */
.preview-fade-enter-active,
.preview-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.preview-fade-enter-from,
.preview-fade-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

/* ============================================
 * 搜索模式分段样式
 * ============================================ */

.search-section {
  padding: 0 0 4px 0;
}

.search-section + .search-section {
  border-top: 1px solid var(--color-border-light);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  user-select: none;
  position: sticky;
  top: 0;
  background: var(--color-bg-secondary);
  z-index: 1;
}

.section-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.section-title {
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.section-count {
  color: var(--color-text-tertiary);
  font-size: 11px;
}

.section-time {
  font-size: 10px;
  opacity: 0.7;
}

.section-loading-indicator {
  margin-left: auto;
}

.section-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 12px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.section-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 12px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

/* ============================================
 * 文件搜索结果项样式
 * ============================================ */

.file-result-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background-color 0.1s;
  user-select: none;
}

.file-result-item:hover {
  background: var(--color-bg-tertiary);
}

.file-result-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  border-radius: 6px;
  background: var(--color-bg-tertiary);
}

.file-result-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-result-name {
  color: var(--color-text-primary);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-result-path {
  color: var(--color-text-tertiary);
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-result-meta {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.file-result-size {
  color: var(--color-text-tertiary);
  font-size: 10px;
  font-feature-settings: "tnum";
}

/* 查看更多按钮 */
.view-more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 16px;
  color: var(--color-accent);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  border-radius: var(--radius-sm, 4px);
  margin: 4px 12px;
}

.view-more-btn:hover {
  background: var(--color-accent-light);
  color: var(--color-accent-hover);
}
</style>
