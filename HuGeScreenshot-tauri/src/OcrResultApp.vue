<script setup lang="ts">
/**
 * OCR 结果弹窗主组件
 *
 * 参考 Python 版本的 OCRResultWindow，实现：
 * - 文本显示和编辑
 * - 复制功能
 * - 排版功能（合并单行、智能分段等）
 * - 翻译功能
 * - 本地 OCR 重新识别
 * - Markdown 转换
 * - 搜索文件
 * - 置顶功能
 *
 * 工具栏和文本操作逻辑与工作台共享一套代码：
 * - OcrToolbar 组件：共享工具栏 UI
 * - useOcrTextActions：共享文本操作逻辑
 *
 * 焦点管理（Task 4.4: Requirements 5.1, 5.2, 5.3）：
 * - 监听窗口焦点变化
 * - 通过 Tauri Event 广播焦点状态
 * - 与 overlay 窗口协调焦点
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow'
import { invoke } from '@tauri-apps/api/core'
import { listen, emit, type UnlistenFn } from '@tauri-apps/api/event'
import OcrToolbar from './components/workbench/OcrToolbar.vue'
import type { FormatType } from './composables/useOcrTextActions'
import { useOcrTextActions } from './composables/useOcrTextActions'
import { formatOcrUserError } from './utils/ocrError'

// 窗口实例
const appWindow = getCurrentWebviewWindow()

// 状态
const ocrText = ref('')
const originalText = ref('')
const isLoading = ref(true)
const statusMessage = ref('正在加载...')
const isPinned = ref(true) // 默认置顶
const isMaximized = ref(false) // 窗口最大化状态
const lastElapsed = ref<number | null>(null)
const lastBoxCount = ref(0)
const avgConfidence = ref<number | null>(null)
const currentImagePath = ref<string | null>(null)

// 使用共享 composable 处理文本操作
const textActions = useOcrTextActions(ocrText, originalText, {
  getImagePath: () => currentImagePath.value,
  isLoading,
})

const charCount = computed(() => ocrText.value.length)

const metricsText = computed(() => {
  const parts: string[] = []
  if (lastBoxCount.value > 0) {
    parts.push(`${lastBoxCount.value} 区域`)
  }
  if (lastElapsed.value !== null) {
    parts.push(`耗时 ${lastElapsed.value.toFixed(2)}s`)
  }
  if (avgConfidence.value !== null) {
    parts.push(`平均置信度 ${Math.round(avgConfidence.value * 100)}%`)
  }
  return parts.join(' · ')
})

// ============================================
// 版面还原：将 OCR 坐标转换为空格对齐的纯文本
// ============================================

/** 计算字符的显示宽度（CJK 全角字符占 2 列，其余占 1 列） */
function getDisplayWidth(text: string): number {
  let w = 0
  for (const ch of text) {
    const code = ch.codePointAt(0) || 0
    if (
      (code >= 0x4E00 && code <= 0x9FFF) ||   // CJK 基本
      (code >= 0x3400 && code <= 0x4DBF) ||   // CJK 扩展 A
      (code >= 0x3000 && code <= 0x303F) ||   // CJK 标点
      (code >= 0xFF00 && code <= 0xFFEF) ||   // 全角字符
      (code >= 0x2E80 && code <= 0x2FFF) ||   // CJK 部首
      (code >= 0xF900 && code <= 0xFAFF) ||   // CJK 兼容
      (code >= 0xFE30 && code <= 0xFE4F)      // CJK 兼容形式
    ) {
      w += 2
    } else {
      w += 1
    }
  }
  return w
}

/** 从 box_coords 提取矩形 */
function getBoxRect(box: OcrBox) {
  const pts = box.box_coords
  if (!pts || pts.length < 4) return null
  const xs = pts.map(p => p?.[0]).filter((v): v is number => Number.isFinite(v))
  const ys = pts.map(p => p?.[1]).filter((v): v is number => Number.isFinite(v))
  if (xs.length < 2 || ys.length < 2) return null
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
}

/** 对齐项类型（提取的 OCR 文本块及其空间信息） */
interface AlignItem {
  box: OcrBox
  rect: { minX: number; maxX: number; minY: number; maxY: number }
  text: string
  centerY: number
  centerX: number
  height: number
  width: number
}

/**
 * 检测多列布局
 *
 * 分析所有文本区域的水平分布，寻找显著的水平间隙。
 * 如果间隙超过文本区域总宽度的 20%，则认为是多列布局，
 * 将 items 拆分为左右两组分别处理。
 */
function detectColumns(items: AlignItem[]): AlignItem[][] {
  if (items.length < 4) return [items]

  const globalMinX = Math.min(...items.map(b => b.rect.minX))
  const globalMaxX = Math.max(...items.map(b => b.rect.maxX))
  const totalWidth = globalMaxX - globalMinX

  if (totalWidth <= 0) return [items]

  // 按 centerX 排序，查找最大水平间隙
  const sortedByX = [...items].sort((a, b) => a.centerX - b.centerX)

  let maxGap = 0
  let maxGapIndex = -1

  for (let i = 0; i < sortedByX.length - 1; i++) {
    // 间隙 = 下一个项的左边界 - 当前项的右边界
    const gap = sortedByX[i + 1].rect.minX - sortedByX[i].rect.maxX
    if (gap > maxGap) {
      maxGap = gap
      maxGapIndex = i
    }
  }

  // 间隙需超过总宽度的 20% 才认为是多列
  const gapThreshold = totalWidth * 0.2
  if (maxGap < gapThreshold || maxGapIndex < 0) {
    return [items]
  }

  // 分列边界：间隙中点
  const boundaryX = (sortedByX[maxGapIndex].rect.maxX + sortedByX[maxGapIndex + 1].rect.minX) / 2

  const leftColumn = items.filter(item => item.centerX < boundaryX)
  const rightColumn = items.filter(item => item.centerX >= boundaryX)

  // 两列都必须有内容才分列
  if (leftColumn.length === 0 || rightColumn.length === 0) {
    return [items]
  }

  return [leftColumn, rightColumn]
}

/** 列行数据（带 Y 坐标，用于多列并排对齐） */
interface ColumnLine {
  /** 该行的平均 Y 坐标 */
  y: number
  /** 该行的文本内容 */
  text: string
}

/**
 * 构建单列的行数据（带 Y 坐标）
 *
 * 核心逻辑：估算字符宽度 -> 按 Y 分行 -> 行内按 X 空格对齐。
 * 返回 {y, text} 数组，供 buildColumnText 和 buildSideBySideText 使用。
 */
function buildColumnLines(columnItems: AlignItem[]): ColumnLine[] {
  if (columnItems.length === 0) return []

  // 不修改原数组
  const items = [...columnItems]

  // ── 1. 估算字符宽度（IQR 中位数法）──
  const ratios: number[] = []
  for (const b of items) {
    const dw = getDisplayWidth(b.text)
    if (dw >= 2 && b.width > 0 && (b.box.confidence ?? 1) >= 0.5) {
      ratios.push(b.width / dw)
    }
  }

  let charWidth: number
  if (ratios.length >= 5) {
    ratios.sort((a, b) => a - b)
    const lo = Math.floor(ratios.length * 0.2)
    const hi = Math.ceil(ratios.length * 0.8)
    const trimmed = ratios.slice(lo, hi)
    charWidth = trimmed[Math.floor(trimmed.length / 2)]
  } else if (ratios.length >= 1) {
    ratios.sort((a, b) => a - b)
    charWidth = ratios[Math.floor(ratios.length / 2)]
  } else {
    charWidth = 8
  }

  // ── 2. 按 Y 排序并分行 ──
  items.sort((a, b) => a.centerY - b.centerY)

  const avgH = items.reduce((s, b) => s + b.height, 0) / items.length
  const lineThreshold = avgH * 0.55

  const lineGroups: { items: AlignItem[]; avgY: number }[] = []
  let curItems = [items[0]]
  let lineCenterY = items[0].centerY

  for (let i = 1; i < items.length; i++) {
    if (Math.abs(items[i].centerY - lineCenterY) < lineThreshold) {
      curItems.push(items[i])
      lineCenterY = curItems.reduce((s, b) => s + b.centerY, 0) / curItems.length
    } else {
      lineGroups.push({ items: curItems, avgY: lineCenterY })
      curItems = [items[i]]
      lineCenterY = items[i].centerY
    }
  }
  lineGroups.push({ items: curItems, avgY: lineCenterY })

  // ── 3. 列局部最小 X（让左对齐更紧凑）──
  const columnMinX = Math.min(...items.map(b => b.rect.minX))

  // ── 4. 逐行构建文本（像素锚定法 + 间距限制）──
  const MAX_INLINE_GAP = 6

  const result: ColumnLine[] = []
  for (const group of lineGroups) {
    const line = group.items
    line.sort((a, b) => a.rect.minX - b.rect.minX)

    let lineStr = ''
    let curCol = 0

    for (let i = 0; i < line.length; i++) {
      const item = line[i]
      let targetCol = Math.round((item.rect.minX - columnMinX) / charWidth)
      const minCol = i > 0 ? curCol + 1 : 0

      if (i > 0) {
        const maxCol = curCol + MAX_INLINE_GAP
        targetCol = Math.min(targetCol, maxCol)
      }

      const col = Math.max(targetCol, minCol)

      if (col > curCol) {
        lineStr += ' '.repeat(col - curCol)
        curCol = col
      }

      lineStr += item.text
      const textEndCol = curCol + getDisplayWidth(item.text)
      const pixelEndCol = Math.round((item.rect.maxX - columnMinX) / charWidth)
      curCol = Math.max(textEndCol, pixelEndCol)
    }

    result.push({ y: group.avgY, text: lineStr })
  }

  return result
}

/**
 * 构建单列的对齐文本（简单包装 buildColumnLines）
 */
function buildColumnText(columnItems: AlignItem[]): string {
  return buildColumnLines(columnItems).map(l => l.text).join('\n')
}

/**
 * 构建多列并排文本
 *
 * 使用双指针归并法按 Y 坐标顺序合并左右列。
 * 跨列匹配阈值比列内分行更宽松（avgH * 1.0），
 * 因为不同面板的同一行文字在 Y 坐标上可能有偏移。
 */
function buildSideBySideText(columns: AlignItem[][]): string {
  if (columns.length < 2) return buildColumnText(columns[0] || [])

  const leftLines = buildColumnLines(columns[0])
  const rightLines = buildColumnLines(columns[1])

  if (leftLines.length === 0) return buildColumnText(columns[1])
  if (rightLines.length === 0) return buildColumnText(columns[0])

  // 跨列行匹配阈值：比列内分行阈值 (0.55) 更宽松
  const allItems = [...columns[0], ...columns[1]]
  const avgH = allItems.reduce((s, b) => s + b.height, 0) / allItems.length
  const yThreshold = avgH * 1.0

  // 双指针归并：按 Y 顺序配对左右列的行
  interface MergedRow { left: string; right: string }
  const mergedRows: MergedRow[] = []
  let li = 0, ri = 0

  while (li < leftLines.length && ri < rightLines.length) {
    const ly = leftLines[li].y
    const ry = rightLines[ri].y

    if (Math.abs(ly - ry) < yThreshold) {
      // Y 坐标接近 → 合并为同一行
      mergedRows.push({ left: leftLines[li].text, right: rightLines[ri].text })
      li++
      ri++
    } else if (ly < ry) {
      // 左列行在上方，右侧无对应行
      mergedRows.push({ left: leftLines[li].text, right: '' })
      li++
    } else {
      // 右列行在上方，左侧无对应行
      mergedRows.push({ left: '', right: rightLines[ri].text })
      ri++
    }
  }

  // 处理剩余的左列行
  while (li < leftLines.length) {
    mergedRows.push({ left: leftLines[li].text, right: '' })
    li++
  }

  // 处理剩余的右列行
  while (ri < rightLines.length) {
    mergedRows.push({ left: '', right: rightLines[ri].text })
    ri++
  }

  // 计算左列最大显示宽度，用于对齐右列
  const leftMaxWidth = Math.max(0, ...mergedRows.map(r => getDisplayWidth(r.left)))
  const COLUMN_GAP = 4
  const paddedWidth = leftMaxWidth + COLUMN_GAP

  // 构建最终并排文本
  const result: string[] = []
  for (const row of mergedRows) {
    if (row.right) {
      const leftWidth = getDisplayWidth(row.left)
      const padding = Math.max(1, paddedWidth - leftWidth)
      result.push(row.left + ' '.repeat(padding) + row.right)
    } else {
      result.push(row.left)
    }
  }

  return result.join('\n')
}

/**
 * 核心函数：将 OCR boxes 转为对齐的纯文本
 *
 * 改进：
 * 1. 自动检测多列布局（如截图包含左右两个面板）
 * 2. 多列时并排输出，保持左右空间关系
 * 3. 限制行内最大间距，保持文本紧凑可读
 */
function buildAlignedText(boxes: OcrBox[]): string {
  const items: AlignItem[] = boxes
    .map(box => ({ box, rect: getBoxRect(box) }))
    .filter((b): b is { box: OcrBox; rect: NonNullable<ReturnType<typeof getBoxRect>> } =>
      b.rect !== null && b.box.text.trim().length > 0
    )
    .map(b => ({
      ...b,
      text: b.box.text.trim(),
      centerY: (b.rect.minY + b.rect.maxY) / 2,
      centerX: (b.rect.minX + b.rect.maxX) / 2,
      height: b.rect.maxY - b.rect.minY,
      width: b.rect.maxX - b.rect.minX,
    }))

  if (items.length === 0) return ''

  // 检测多列布局
  const columns = detectColumns(items)

  if (columns.length <= 1) {
    return buildColumnText(items)
  }

  // 多列：并排输出，保持左右空间关系
  return buildSideBySideText(columns)
}

// 焦点状态（Task 4.4: Requirements 5.1, 5.2, 5.3）
const isWindowFocused = ref(true)

// 事件监听器（用于窗口已存在时接收新结果）
let unlistenOcrResult: UnlistenFn | null = null

// 焦点变化事件监听器
let unlistenWindowFocus: (() => void) | null = null
let unlistenFocusChange: UnlistenFn | null = null

// 焦点变化事件名称（与 Rust focus_manager.rs 保持一致）
const FOCUS_CHANGED_EVENT = 'focus-changed'

/**
 * 焦点变化事件载荷
 */
interface FocusChangeEvent {
  windowLabel: string
  isFocused: boolean
  timestamp: number
}

// OCR 结果类型
interface OcrResultPayload {
  text: string
  boxes?: OcrBox[]
  elapse?: number
  imagePath?: string
  image_path?: string
}

interface OcrBox {
  text: string
  confidence: number
  box_coords?: number[][]
}

function computeConfidenceStats(boxes?: OcrBox[]) {
  if (!boxes || boxes.length === 0) {
    return { avg: null, count: 0 }
  }
  const confidences = boxes
    .map(box => (typeof box?.confidence === 'number' ? box.confidence : null))
    .filter((value): value is number => value !== null)
  if (confidences.length === 0) {
    return { avg: null, count: boxes.length }
  }
  const sum = confidences.reduce((total, value) => total + value, 0)
  return {
    avg: sum / confidences.length,
    count: boxes.length,
  }
}

function updateMetrics(payload: OcrResultPayload | null) {
  if (!payload) {
    lastElapsed.value = null
    lastBoxCount.value = 0
    avgConfidence.value = null
    return
  }

  lastElapsed.value = typeof payload.elapse === 'number' ? payload.elapse : null
  const stats = computeConfidenceStats(payload.boxes)
  lastBoxCount.value = stats.count
  avgConfidence.value = stats.avg
}

function applyOcrPayload(payload: OcrResultPayload | null): void {
  if (payload) {
    // 保存图片路径（用于本地 OCR 重新识别）
    currentImagePath.value = payload.imagePath || payload.image_path || null

    // 如果有坐标信息，生成空格对齐的版面文本；否则用原始文本
    const boxes = Array.isArray(payload.boxes) ? payload.boxes : []
    const rawText = payload.text ?? ''
    const aligned = boxes.length > 0 ? buildAlignedText(boxes) : rawText
    ocrText.value = aligned || rawText
    originalText.value = ocrText.value
    updateMetrics(payload)

    const boxCount = boxes.length
    const elapsedText = typeof payload.elapse === 'number' ? `${payload.elapse.toFixed(2)}s` : '--'
    statusMessage.value = ocrText.value.trim()
      ? `识别完成：${boxCount} 个区域，耗时 ${elapsedText}`
      : `未识别到文字，耗时 ${elapsedText}`
    isLoading.value = false
  } else {
    updateMetrics(null)
    statusMessage.value = '未获取到 OCR 结果'
    isLoading.value = false
  }
}

onMounted(async () => {
  console.log('[OcrResult] 组件挂载，开始获取 OCR 结果...')

  // 同步初始最大化状态
  isMaximized.value = await appWindow.isMaximized()

  // 监听窗口 resize 事件以同步最大化状态
  appWindow.onResized(async () => {
    isMaximized.value = await appWindow.isMaximized()
  })

  // 【Task 4.4】设置焦点变化事件监听器（Requirements 5.1, 5.2, 5.3）
  await setupFocusEventListeners()

  // 方式1：通过 invoke 获取待处理的 OCR 结果（首次打开窗口）
  try {
    const result = await invoke<OcrResultPayload | null>('get_pending_ocr_result')
    console.log('[OcrResult] invoke 获取结果:', result)
    applyOcrPayload(result)
  } catch (error) {
    console.error('[OcrResult] invoke 获取结果失败:', error)
    updateMetrics(null)
    statusMessage.value = '获取结果失败: ' + error
    isLoading.value = false
  }

  // 方式2：监听事件（窗口已存在时接收新结果）
  unlistenOcrResult = await listen<OcrResultPayload>('ocr-result', event => {
    console.log('[OcrResult] 收到 OCR 结果事件:', event.payload)
    applyOcrPayload(event.payload)
  })
})

onUnmounted(() => {
  unlistenOcrResult?.()
  cleanupFocusEventListeners()
})

// ============================================
// 工具栏事件处理（委托给 composable）
// ============================================

/** 复制全部文本 */
async function handleCopy() {
  if (!ocrText.value) {
    statusMessage.value = '没有可复制的文本'
    return
  }
  const success = await textActions.copyText()
  statusMessage.value = success
    ? `已复制 ${ocrText.value.length} 个字符`
    : '复制失败'
}

/** 格式化文本 */
function handleFormat(type: FormatType) {
  textActions.formatText(type)
  statusMessage.value = '已格式化文本'
}

/** 恢复原文 */
function handleRestore() {
  textActions.restoreOriginal()
  statusMessage.value = '已恢复原文'
}

/** 翻译文本 */
async function handleTranslate() {
  try {
    statusMessage.value = '正在翻译...'
    await textActions.translateText()
    statusMessage.value = '翻译完成'
  } catch (error) {
    const message = error instanceof Error ? error.message : '翻译失败'
    statusMessage.value = message
  }
}

/** 本地 OCR 重新识别 */
async function handleLocalOcr() {
  if (!currentImagePath.value) {
    statusMessage.value = '没有可识别的图片'
    return
  }

  try {
    statusMessage.value = '正在重新识别...'
    const result = await textActions.performLocalOcr()
    statusMessage.value = `识别完成：${result.text.length} 字，置信度 ${result.confidence}%，耗时 ${(result.elapsedTime / 1000).toFixed(2)}s`
  } catch (error) {
    statusMessage.value = formatOcrUserError(error)
  }
}

/** 百度高精度 OCR 重新识别 */
async function handleBaiduOcr() {
  if (!currentImagePath.value) {
    statusMessage.value = '没有可识别的图片'
    return
  }

  try {
    statusMessage.value = '正在使用百度高精度识别...'
    const result = await textActions.performLocalOcr('baiduAccurate')
    statusMessage.value = `高精度识别完成：${result.text.length} 字，置信度 ${result.confidence}%，耗时 ${(result.elapsedTime / 1000).toFixed(2)}s`
  } catch (error) {
    const message = error instanceof Error ? error.message : '百度高精度 OCR 识别失败'
    statusMessage.value = message
  }
}

// 切换置顶
async function togglePin() {
  isPinned.value = !isPinned.value
  await appWindow.setAlwaysOnTop(isPinned.value)
  statusMessage.value = isPinned.value ? '已置顶' : '已取消置顶'
}

// 最小化窗口
async function minimizeWindow() {
  await appWindow.minimize()
}

// 切换最大化/还原
async function toggleMaximize() {
  const maximized = await appWindow.isMaximized()
  if (maximized) {
    await appWindow.unmaximize()
  } else {
    await appWindow.maximize()
  }
  isMaximized.value = !maximized
}

// 关闭窗口
async function closeWindow() {
  await appWindow.close()
}

// 键盘快捷键
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeWindow()
  }
  if (event.ctrlKey && event.key === 'c' && !window.getSelection()?.toString()) {
    handleCopy()
  }
}

// ============================================
// 焦点变化事件监听（Task 4.4: Requirements 5.1, 5.2, 5.3）
// ============================================

async function setupFocusEventListeners(): Promise<void> {
  console.log('[OcrResult] 设置焦点变化事件监听器...')

  const windowLabel = appWindow.label

  try {
    unlistenWindowFocus = await appWindow.onFocusChanged(({ payload: focused }) => {
      if (isWindowFocused.value === focused) {
        return
      }

      isWindowFocused.value = focused
      console.log(`[OcrResult] 窗口焦点变化: ${windowLabel}, focused=${focused}`)

      const focusEvent: FocusChangeEvent = {
        windowLabel: windowLabel,
        isFocused: focused,
        timestamp: Date.now(),
      }

      emit(FOCUS_CHANGED_EVENT, focusEvent).catch(error => {
        console.warn('[OcrResult] 发送焦点变化事件失败:', error)
      })
    })

    unlistenFocusChange = await listen<FocusChangeEvent>(FOCUS_CHANGED_EVENT, event => {
      const { windowLabel: sourceWindow, isFocused } = event.payload

      if (sourceWindow === windowLabel) {
        return
      }

      console.log(`[OcrResult] 收到焦点变化事件: ${sourceWindow}, focused=${isFocused}`)

      if (sourceWindow.startsWith('overlay-') && isFocused) {
        console.log('[OcrResult] Overlay 窗口获得焦点，OCR 面板保持可见')
      }
    })

    console.log('[OcrResult] 焦点变化事件监听器设置完成')
  } catch (error) {
    console.error('[OcrResult] 设置焦点变化事件监听器失败:', error)
  }
}

function cleanupFocusEventListeners(): void {
  if (unlistenWindowFocus) {
    unlistenWindowFocus()
    unlistenWindowFocus = null
    console.log('[OcrResult] 已清理窗口焦点监听器')
  }

  if (unlistenFocusChange) {
    unlistenFocusChange()
    unlistenFocusChange = null
    console.log('[OcrResult] 已清理焦点变化事件监听器')
  }
}
</script>

<template>
  <div class="ocr-result-window" @keydown="handleKeydown" tabindex="0">
    <!-- 自定义标题栏 -->
    <div class="title-bar">
      <div class="title-drag-region" data-tauri-drag-region @dblclick="toggleMaximize">
        <span class="title">识别结果</span>
      </div>
      <div class="title-bar-buttons">
        <button
          class="title-btn pin-btn"
          :class="{ active: isPinned }"
          @click.stop="togglePin"
          @mousedown.stop
          title="置顶"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M12 17v5"></path>
            <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"></path>
          </svg>
        </button>
        <!-- 最小化按钮 -->
        <button class="title-btn minimize-btn" @click.stop="minimizeWindow" @mousedown.stop title="最小化">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
        </button>
        <!-- 最大化/还原按钮 -->
        <button class="title-btn maximize-btn" @click.stop="toggleMaximize" @mousedown.stop :title="isMaximized ? '还原' : '最大化'">
          <!-- 最大化图标 -->
          <svg v-if="!isMaximized" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <rect x="4" y="4" width="16" height="16" rx="1"></rect>
          </svg>
          <!-- 还原图标（双层窗口） -->
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <rect x="6" y="8" width="12" height="12" rx="1"></rect>
            <path d="M8 8V6a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-2"></path>
          </svg>
        </button>
        <button class="title-btn close-btn" @click.stop="closeWindow" @mousedown.stop title="关闭">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>

    <!-- 共享工具栏组件（与工作台一致） -->
    <OcrToolbar
      :has-content="textActions.hasContent.value"
      :is-loading="isLoading"
      :has-changes="textActions.hasChanges.value"
      :can-recognize="!!currentImagePath"
      @copy="handleCopy"
      @format="handleFormat"
      @restore="handleRestore"
      @translate="handleTranslate"
      @local-ocr="handleLocalOcr"
      @baidu-ocr="handleBaiduOcr"
    />

    <!-- 文本编辑区（等宽字体 + 空格对齐版面） -->
    <div class="content">
      <textarea
        v-model="ocrText"
        class="text-area"
        placeholder="识别结果将显示在这里..."
        :disabled="isLoading"
        spellcheck="false"
      ></textarea>
    </div>

    <!-- 状态栏 -->
    <div class="status-bar">
      <span class="status-message">{{ statusMessage }}</span>
      <div class="status-right">
        <span class="char-count">{{ charCount }} 字</span>
        <span v-if="metricsText" class="ocr-metrics">{{ metricsText }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ocr-result-window {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: var(--font-family);
  outline: none;
}

/* 标题栏 */
.title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 8px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-light);
  user-select: none;
  flex-shrink: 0;
}

.title-drag-region {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: center;
  cursor: default;
}

.title {
  font-size: var(--font-size-base);
  font-weight: 500;
}

.title-bar-buttons {
  display: flex;
  gap: 4px;
}

.title-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition-fast);
}

.title-btn:hover {
  background: var(--color-bg-tertiary);
}

.minimize-btn:hover,
.maximize-btn:hover {
  background: var(--color-bg-tertiary);
}

.close-btn:hover {
  background: var(--color-error);
  color: white;
}

.pin-btn.active {
  background: var(--color-accent-light);
  color: var(--color-accent);
}

/* 内容区 */
.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

.text-area {
  width: 100%;
  flex: 1;
  min-height: 160px;
  padding: 16px;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-base);
  line-height: 1.6;
  resize: none;
  outline: none;
  white-space: pre;
  tab-size: 4;
  overflow: auto;
}

.text-area:focus {
  background: var(--color-bg-primary);
}

.text-area::placeholder {
  color: var(--color-text-tertiary);
}

/* 状态栏 */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-light);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.char-count {
  color: var(--color-text-secondary);
}

.ocr-metrics {
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
