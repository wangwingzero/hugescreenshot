<template>
  <div
    ref="layoutRef"
    class="workbench-layout"
    role="application"
    aria-label="工作台布局"
    @keydown="handleKeyDown"
    tabindex="0"
  >
    <!-- 左侧面板：历史记录列表 -->
    <div
      class="left-panel"
      :style="{ width: `${leftPanelWidth}%` }"
    >
      <slot name="left">
        <!-- 默认左侧面板内容占位 -->
        <div class="panel-placeholder">
          <span class="placeholder-icon">📋</span>
          <span class="placeholder-text">历史记录面板</span>
        </div>
      </slot>
    </div>

    <!-- 可拖拽分隔条 -->
    <div
      class="splitter"
      :class="{ 'is-resizing': isResizing }"
      @mousedown="handleSplitterMouseDown"
      @touchstart.passive="handleSplitterTouchStart"
    >
      <div class="splitter-handle">
        <div class="splitter-line"></div>
      </div>
    </div>

    <!-- 右侧面板：OCR 内容 -->
    <div
      class="right-panel"
      :style="{ width: `${100 - leftPanelWidth}%` }"
    >
      <slot name="right">
        <!-- 默认右侧面板内容占位 -->
        <div class="panel-placeholder">
          <span class="placeholder-icon">📝</span>
          <span class="placeholder-text">OCR 内容面板</span>
        </div>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 工作台双面板布局组件
 *
 * 提供可调整大小的水平分割布局：
 * - 左侧面板：历史记录列表 (默认 35-40%)
 * - 右侧面板：OCR 内容 (默认 60-65%)
 * - 可拖拽分隔条调整面板宽度
 *
 * @validates Requirements 1.1, 1.2, 1.4, 1.5
 */

import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useWorkbenchStore } from '@/stores/workbench'
import { useHistoryStore } from '@/stores/history'

// ============================================
// Store
// ============================================

const workbenchStore = useWorkbenchStore()
const historyStore = useHistoryStore()

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 最小左侧面板宽度百分比 */
  minLeftWidth?: number
  /** 最大左侧面板宽度百分比 */
  maxLeftWidth?: number
  /** 默认左侧面板宽度百分比 */
  defaultLeftWidth?: number
}

const props = withDefaults(defineProps<Props>(), {
  minLeftWidth: 20,
  maxLeftWidth: 60,
  defaultLeftWidth: 25,
})

const emit = defineEmits<{
  /** 面板宽度变化事件 */
  (e: 'resize', leftWidth: number): void
  /** 键盘导航事件 */
  (e: 'navigate', direction: 'up' | 'down'): void
  /** 选择确认事件（Enter/Space 键触发） */
  (e: 'select-confirm', itemId: number): void
}>()

// ============================================
// State
// ============================================

/** 布局容器引用 */
const layoutRef = ref<HTMLDivElement | null>(null)

/** 是否正在调整大小 */
const isResizing = ref(false)

/** 拖拽起始位置 */
const startX = ref(0)

/** 拖拽起始时的左侧面板宽度 */
const startWidth = ref(0)

/** 容器元素引用 */
const containerWidth = ref(0)

// ============================================
// Computed
// ============================================

/**
 * 左侧面板宽度（从 store 获取）
 * @validates Requirements 1.4
 */
const leftPanelWidth = computed(() => workbenchStore.leftPanelWidth)

// ============================================
// Methods - Splitter Resize
// ============================================

/**
 * 处理分隔条鼠标按下事件
 * 开始拖拽调整面板大小
 */
function handleSplitterMouseDown(event: MouseEvent): void {
  event.preventDefault()
  startResize(event.clientX)
  
  // 添加全局事件监听
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

/**
 * 处理分隔条触摸开始事件
 * 支持触摸设备
 */
function handleSplitterTouchStart(event: TouchEvent): void {
  if (event.touches.length !== 1) return
  
  startResize(event.touches[0].clientX)
  
  // 添加全局事件监听
  document.addEventListener('touchmove', handleTouchMove, { passive: false })
  document.addEventListener('touchend', handleTouchEnd)
}

/**
 * 开始调整大小
 * @param clientX 起始 X 坐标
 */
function startResize(clientX: number): void {
  isResizing.value = true
  startX.value = clientX
  startWidth.value = leftPanelWidth.value
  
  // 获取容器宽度
  const container = document.querySelector('.workbench-layout')
  if (container) {
    containerWidth.value = container.clientWidth
  }
  
  // 添加 body 样式防止选中文本
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

/**
 * 处理鼠标移动事件
 * 计算新的面板宽度
 */
function handleMouseMove(event: MouseEvent): void {
  if (!isResizing.value) return
  updatePanelWidth(event.clientX)
}

/**
 * 处理触摸移动事件
 */
function handleTouchMove(event: TouchEvent): void {
  if (!isResizing.value || event.touches.length !== 1) return
  event.preventDefault()
  updatePanelWidth(event.touches[0].clientX)
}

/**
 * 更新面板宽度
 * @param clientX 当前 X 坐标
 * @validates Requirements 1.2
 */
function updatePanelWidth(clientX: number): void {
  if (containerWidth.value === 0) return
  
  // 计算移动距离对应的百分比变化
  const deltaX = clientX - startX.value
  const deltaPercent = (deltaX / containerWidth.value) * 100
  
  // 计算新宽度并限制范围
  let newWidth = startWidth.value + deltaPercent
  newWidth = Math.max(props.minLeftWidth, Math.min(props.maxLeftWidth, newWidth))
  
  // 更新 store 中的宽度
  workbenchStore.setLeftPanelWidth(newWidth)
  
  // 触发 resize 事件
  emit('resize', newWidth)
}

/**
 * 处理鼠标释放事件
 * 结束拖拽
 */
function handleMouseUp(): void {
  stopResize()
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
}

/**
 * 处理触摸结束事件
 */
function handleTouchEnd(): void {
  stopResize()
  document.removeEventListener('touchmove', handleTouchMove)
  document.removeEventListener('touchend', handleTouchEnd)
}

/**
 * 停止调整大小
 */
function stopResize(): void {
  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// ============================================
// Methods - Keyboard Navigation
// ============================================

/**
 * 处理键盘事件
 * 支持上下箭头键导航、Home/End 跳转、Tab 面板切换
 * @validates Requirements 7.2
 */
function handleKeyDown(event: KeyboardEvent): void {
  // 如果焦点在输入框内，不处理导航键
  const target = event.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
    return
  }

  switch (event.key) {
    case 'ArrowUp':
      event.preventDefault()
      workbenchStore.selectPrevious()
      emit('navigate', 'up')
      // 确保选中项可见
      scrollSelectedIntoView()
      break

    case 'ArrowDown':
      event.preventDefault()
      workbenchStore.selectNext()
      emit('navigate', 'down')
      // 确保选中项可见
      scrollSelectedIntoView()
      break

    case 'Home':
      // 跳转到第一个项目
      event.preventDefault()
      selectFirstItem()
      break

    case 'End':
      // 跳转到最后一个项目
      event.preventDefault()
      selectLastItem()
      break

    case 'Enter':
    case ' ':
      // 确认选择（可用于触发详情查看等操作）
      if (workbenchStore.selectedItemId !== null) {
        event.preventDefault()
        emit('select-confirm', workbenchStore.selectedItemId)
      }
      break

    case 'Tab':
      // Tab 键在面板间切换焦点
      handleTabNavigation(event)
      break
  }
}

/**
 * 选择第一个项目
 */
function selectFirstItem(): void {
  if (historyStore.items.length > 0) {
    workbenchStore.selectItem(historyStore.items[0].id)
    scrollSelectedIntoView()
  }
}

/**
 * 选择最后一个项目
 */
function selectLastItem(): void {
  if (historyStore.items.length > 0) {
    workbenchStore.selectItem(historyStore.items[historyStore.items.length - 1].id)
    scrollSelectedIntoView()
  }
}

/**
 * 滚动选中项到可视区域
 * 使用 nextTick 确保 DOM 更新后再滚动
 */
async function scrollSelectedIntoView(): Promise<void> {
  await nextTick()
  
  // 查找选中的列表项元素
  const selectedElement = layoutRef.value?.querySelector('[data-selected="true"]') as HTMLElement
  if (selectedElement) {
    selectedElement.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    })
  }
}

/**
 * 处理 Tab 键面板间导航
 * @param event 键盘事件
 */
function handleTabNavigation(event: KeyboardEvent): void {
  // 获取当前焦点所在的面板
  const activeElement = document.activeElement as HTMLElement
  const leftPanel = layoutRef.value?.querySelector('.left-panel') as HTMLElement
  const rightPanel = layoutRef.value?.querySelector('.right-panel') as HTMLElement

  if (!leftPanel || !rightPanel) return

  const isInLeftPanel = leftPanel.contains(activeElement)
  const isInRightPanel = rightPanel.contains(activeElement)

  if (event.shiftKey) {
    // Shift+Tab: 向左移动焦点
    if (isInRightPanel) {
      event.preventDefault()
      focusFirstInteractiveElement(leftPanel)
    }
  } else {
    // Tab: 向右移动焦点
    if (isInLeftPanel) {
      event.preventDefault()
      focusFirstInteractiveElement(rightPanel)
    }
  }
}

/**
 * 聚焦面板内第一个可交互元素
 * @param panel 面板元素
 */
function focusFirstInteractiveElement(panel: HTMLElement): void {
  const focusableSelector = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  const firstFocusable = panel.querySelector(focusableSelector) as HTMLElement
  
  if (firstFocusable) {
    firstFocusable.focus()
  } else {
    // 如果没有可聚焦元素，聚焦面板本身
    panel.focus()
  }
}

/**
 * 聚焦到布局容器，启用键盘导航
 */
function focusLayout(): void {
  layoutRef.value?.focus()
}

// ============================================
// Lifecycle
// ============================================

onMounted(() => {
  // 初始化工作台状态
  workbenchStore.initialize()
})

onUnmounted(() => {
  // 清理事件监听
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  document.removeEventListener('touchmove', handleTouchMove)
  document.removeEventListener('touchend', handleTouchEnd)
})

// ============================================
// Expose
// ============================================

defineExpose({
  /** 当前左侧面板宽度 */
  leftPanelWidth,
  /** 是否正在调整大小 */
  isResizing,
  /** 聚焦布局容器 */
  focusLayout,
  /** 选择第一个项目 */
  selectFirstItem,
  /** 选择最后一个项目 */
  selectLastItem,
  /** 滚动选中项到可视区域 */
  scrollSelectedIntoView,
})
</script>

<style scoped>
.workbench-layout {
  display: flex;
  width: 100%;
  flex: 1;
  min-height: 0; /* 允许 flex 子元素收缩 */
  background-color: var(--color-bg-primary);
  overflow: hidden;
  outline: none;
}

/* 键盘焦点指示器 - 仅对键盘用户显示 */
.workbench-layout:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

/* 左侧面板 */
.left-panel {
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border-light);
}

/* 右侧面板 */
.right-panel {
  flex: 1;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-primary);
}

/* 分隔条 */
.splitter {
  flex-shrink: 0;
  width: 8px; /* Hit area width */
  margin-left: -4px; /* Center over the border */
  margin-right: -4px;
  height: 100%;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 100;
  transition: none; /* Snappy */
}

.splitter:hover,
.splitter.is-resizing {
  background: var(--color-accent-light);
}

.splitter-handle {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 4px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.splitter-line {
  width: 2px;
  height: 100%;
  background: var(--color-border);
  border-radius: 1px;
  transition: background-color 0.15s ease, height 0.15s ease;
}

.splitter:hover .splitter-line,
.splitter.is-resizing .splitter-line {
  background: var(--color-accent);
  height: 60px;
}

/* 占位符样式 */
.panel-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--color-text-tertiary);
}

.placeholder-icon {
  font-size: 48px;
  opacity: 0.5;
}

.placeholder-text {
  font-size: 14px;
}

/* 调整大小时禁用面板内容的指针事件 */
.workbench-layout:has(.splitter.is-resizing) .left-panel,
.workbench-layout:has(.splitter.is-resizing) .right-panel {
  pointer-events: none;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .splitter {
    width: 8px;
  }
  
  .splitter-handle {
    width: 6px;
    height: 50px;
  }
  
  .splitter-line {
    width: 3px;
  }
}
</style>
