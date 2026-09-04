<script setup lang="ts">
/**
 * 工作台应用根组件
 *
 * 显示截图历史记录，支持搜索、预览、OCR 等功能
 * 使用双面板布局：左侧历史记录列表，右侧 OCR 内容面板
 *
 * @validates Requirements 7.4, 8.1, 8.3
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { useWorkbenchStore } from '@/stores/workbench'
import { useHistoryStore } from '@/stores/history'
import { WorkbenchLayout, HistoryListPanel, OcrContentPanel } from '@/components/workbench'
import TitleBar from '@/components/workbench/TitleBar.vue'
import SearchDialog from '@/components/FileSearch/SearchDialog.vue'

// ============================================
// Stores
// ============================================

const workbenchStore = useWorkbenchStore()
const historyStore = useHistoryStore()

// ============================================
// File Search State
// ============================================

/** 文件搜索对话框是否可见 @validates Requirements 8.3 */
const isFileSearchVisible = ref(false)

/** 文件搜索初始查询关键词 @validates Requirements 7.2 */
const fileSearchInitialQuery = ref('')

/** 新建的空白文档 ID 列表（关闭时清理未编辑的） */
const blankDocIds = ref<Set<number>>(new Set())

// ============================================
// Event Listeners
// ============================================

/** 事件监听器清理函数 */
let unlistenSelectItem: UnlistenFn | null = null

/** 窗口焦点监听清理函数 */
let unlistenFocus: UnlistenFn | null = null

// ============================================
// Event Handlers
// ============================================

/**
 * 处理历史记录项选择事件
 * @param id 选中的历史记录 ID
 */
function handleSelect(id: number): void {
  workbenchStore.selectItem(id)
}

/**
 * 处理历史记录项双击事件
 * 可用于打开详情或执行其他操作
 * @param id 双击的历史记录 ID
 */
function handleDoubleClick(id: number): void {
  // 双击时可以打开图片详情或执行其他操作
  console.log('[WorkbenchApp] Double clicked item:', id)
}

/**
 * 处理新建空白文档事件
 * 记录 ID，关闭工作台时清理未编辑的空白文档
 */
function handleBlankDocCreated(id: number): void {
  blankDocIds.value.add(id)
}

/**
 * 处理打开文件搜索事件
 * @param query 可选的初始查询关键词（从"查看全部"入口打开时携带侧栏当前搜索词）
 * @validates Requirements 8.3
 */
function handleOpenFileSearch(query?: string): void {
  fileSearchInitialQuery.value = query ?? ''
  isFileSearchVisible.value = true
  console.log('[WorkbenchApp] 打开文件搜索对话框, 初始查询:', fileSearchInitialQuery.value)
}

/**
 * 处理关闭文件搜索事件
 */
function handleCloseFileSearch(): void {
  isFileSearchVisible.value = false
  // 清空初始查询，避免下次打开时残留
  fileSearchInitialQuery.value = ''
}

// ============================================
// Lifecycle
// ============================================

onMounted(async () => {
  try {
    // 暂停剪贴板监听（工作台打开期间不记录新内容）
    await invoke('pause_clipboard_watcher').catch((e) => {
      console.warn('[WorkbenchApp] 暂停剪贴板监听失败:', e)
    })

    // 监听窗口焦点变化：仅用于自动刷新历史列表（不控制剪贴板监听）
    // 截图后工作台重新获得焦点时，自动显示新截图
    unlistenFocus = await getCurrentWindow().onFocusChanged(async ({ payload: focused }) => {
      if (focused) {
        // 窗口重新获得焦点时，静默刷新历史记录
        const prevCount = historyStore.totalCount
        await historyStore.loadStats()
        if (historyStore.totalCount !== prevCount) {
          await historyStore.loadHistory()
        }
      }
    })

    // 加载历史记录数据
    await historyStore.loadHistory()
    await historyStore.loadStats()

    // 初始化工作台状态（恢复上次选中的项目）
    // @validates Requirements 7.4
    await workbenchStore.initialize()

    // 监听从截图 overlay 发来的选中历史记录事件
    unlistenSelectItem = await listen<{ historyId: number; ocrText?: string }>(
      'select-history-item',
      async (event) => {
        console.log('[WorkbenchApp] 收到选中历史记录事件:', event.payload)
        
        // 重新加载历史记录以获取最新数据
        await historyStore.loadHistory()
        
        // 选中指定的历史记录项
        const { historyId, ocrText } = event.payload
        await workbenchStore.selectItem(historyId)
        
        // 如果有 OCR 文本，直接设置（避免重新执行 OCR）
        if (ocrText) {
          workbenchStore.setOcrText(ocrText)
        }
      }
    )

    // 监听临时预览模式事件
    // Feature: workbench-temporary-preview
    const unlistenTemporaryPreview = await listen<{
      imageData: number[]
      width: number
      height: number
      ocrText?: string
      metadata?: {
        captureMode?: string
        monitorId?: number
        hasAnnotations?: boolean
        windowTitle?: string
      }
    }>('enter-temporary-preview', async (event) => {
      console.log('[WorkbenchApp] 收到临时预览事件')
      
      const { imageData, width, height, ocrText, metadata } = event.payload
      
      // 进入临时预览模式
      workbenchStore.enterTemporaryMode({
        id: `temp_${Date.now()}`,
        imageData: new Uint8Array(imageData),
        width,
        height,
        ocrText,
        metadata,
      })
    })

    // 保存清理函数
    const originalUnlisten = unlistenSelectItem
    unlistenSelectItem = async () => {
      if (originalUnlisten) await originalUnlisten()
      await unlistenTemporaryPreview()
    }

    console.log('[WorkbenchApp] 工作台初始化成功')
  } catch (error) {
    console.error('[WorkbenchApp] 初始化失败:', error)
  }
})

onUnmounted(async () => {
  // 清理未编辑的空白文档
  for (const docId of blankDocIds.value) {
    const item = historyStore.items.find(i => i.id === docId)
    // 如果文档仍为空（无 ocrText 且无 textContent），删除它
    if (item && !item.ocrText && !item.textContent) {
      await invoke('delete_history_item', { id: docId }).catch((e) => {
        console.warn('[WorkbenchApp] 删除空白文档失败:', docId, e)
      })
    }
  }
  blankDocIds.value.clear()

  // 恢复剪贴板监听
  invoke('resume_clipboard_watcher').catch((e) => {
    console.warn('[WorkbenchApp] 恢复剪贴板监听失败:', e)
  })

  // 清理事件监听器
  if (unlistenSelectItem) {
    unlistenSelectItem()
    unlistenSelectItem = null
  }
  if (unlistenFocus) {
    unlistenFocus()
    unlistenFocus = null
  }
})
</script>

<template>
  <div class="workbench-container">
    <!-- 自定义标题栏 -->
    <TitleBar />

    <!-- 双面板布局 -->
    <WorkbenchLayout>
      <!-- 左侧面板：历史记录列表 -->
      <template #left>
        <HistoryListPanel
          :selected-id="workbenchStore.selectedItemId"
          @select="handleSelect"
          @double-click="handleDoubleClick"
          @open-file-search="handleOpenFileSearch"
          @blank-doc-created="handleBlankDocCreated"
        />
      </template>

      <!-- 右侧面板：OCR 内容 -->
      <template #right>
        <OcrContentPanel
          :history-item="workbenchStore.selectedItem"
        />
      </template>
    </WorkbenchLayout>

    <!-- 文件搜索对话框 @validates Requirements 8.3, 7.1, 7.2 -->
    <SearchDialog
      :visible="isFileSearchVisible"
      :initial-query="fileSearchInitialQuery"
      @close="handleCloseFileSearch"
    />
  </div>
</template>

<style scoped>
/* @validates Requirements 8.1 - 保持深色主题 */
.workbench-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: var(--color-bg-primary);
}
</style>
