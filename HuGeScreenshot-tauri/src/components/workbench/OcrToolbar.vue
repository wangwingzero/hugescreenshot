<template>
  <div class="ocr-toolbar">
    <!-- 复制按钮 -->
    <button
      class="toolbar-btn"
      :class="{ 'is-disabled': !hasContent || isLoading }"
      :disabled="!hasContent || isLoading"
      :aria-disabled="!hasContent || isLoading"
      title="复制文本到剪贴板"
      @click="handleCopy"
    >
      <span class="btn-icon" v-html="getIcon('copy')"></span>
      <span class="btn-text">复制</span>
    </button>

    <!-- 排版按钮（带下拉菜单） -->
    <div class="toolbar-dropdown" ref="formatDropdownRef">
      <button
        class="toolbar-btn dropdown-trigger"
        :class="{ 'is-disabled': !hasContent || isLoading, 'is-active': isFormatMenuOpen }"
        :disabled="!hasContent || isLoading"
        :aria-disabled="!hasContent || isLoading"
        :aria-expanded="isFormatMenuOpen"
        title="文本排版选项"
        @click="toggleFormatMenu"
      >
        <span class="btn-icon" v-html="getIcon('format')"></span>
        <span class="btn-text">排版</span>
        <span class="dropdown-arrow" :class="{ 'is-open': isFormatMenuOpen }">▼</span>
      </button>
      
      <!-- 排版下拉菜单 -->
      <Transition name="dropdown">
        <div v-if="isFormatMenuOpen" class="dropdown-menu" role="menu">
          <button
            v-for="option in formatOptions"
            :key="option.type"
            class="dropdown-item"
            role="menuitem"
            @click="handleFormat(option.type)"
          >
            <span class="item-icon icon-container" v-html="getIcon(option.icon)"></span>
            <span class="item-text">{{ option.label }}</span>
          </button>
        </div>
      </Transition>
    </div>

    <!-- 原文按钮 -->
    <button
      class="toolbar-btn"
      :class="{ 'is-disabled': !hasChanges || isLoading }"
      :disabled="!hasChanges || isLoading"
      :aria-disabled="!hasChanges || isLoading"
      title="恢复原始文本"
      @click="handleRestore"
    >
      <span class="btn-icon" v-html="getIcon('restore')"></span>
      <span class="btn-text">原文</span>
    </button>

    <template v-if="canRecognize">
      <!-- 本地重识别 -->
      <button
        class="toolbar-btn"
        :class="{ 'is-disabled': isLoading }"
        :disabled="isLoading"
        :aria-disabled="isLoading"
        title="使用本地 OCR 重新识别"
        @click="handleLocalOcr"
      >
        <span class="btn-icon" v-html="getIcon('scan')"></span>
        <span class="btn-text">本地</span>
      </button>

      <!-- 百度高精度 OCR -->
      <button
        class="toolbar-btn"
        :class="{ 'is-disabled': isLoading }"
        :disabled="isLoading"
        :aria-disabled="isLoading"
        title="使用百度高精度 OCR 重新识别"
        @click="handleBaiduOcr"
      >
        <span class="btn-icon" v-html="getIcon('accurate')"></span>
        <span class="btn-text">高精度</span>
      </button>
    </template>

    <!-- 分隔线 -->
    <div class="toolbar-divider" />

    <!-- 翻译按钮 -->
    <button
      class="toolbar-btn"
      :class="{ 'is-disabled': !hasContent || isLoading }"
      :disabled="!hasContent || isLoading"
      :aria-disabled="!hasContent || isLoading"
      title="翻译文本"
      @click="handleTranslate"
    >
      <span class="btn-icon" v-html="getIcon('translate')"></span>
      <span class="btn-text">翻译</span>
    </button>


  </div>
</template>

<script setup lang="ts">
/**
 * OCR 工具栏组件
 *
 * 提供 OCR 文本操作的快捷按钮：
 * - 复制：复制文本到剪贴板
 * - 排版：文本格式化选项（下拉菜单）
 * - 原文：恢复原始 OCR 文本
 * - 翻译：翻译 OCR 文本
 *
 * @validates Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
 */

import { ref, onMounted, onUnmounted } from 'vue'
import type { FormatType } from '@/composables/useOcrTextActions'

// ============================================
// Types (从共享 composable 导入)
// ============================================

// FormatType 已从 useOcrTextActions 导入
export type { FormatType }

/** 格式化选项配置 */
interface FormatOption {
  type: FormatType
  label: string
  icon: string
}

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 是否有 OCR 内容 */
  hasContent: boolean
  /** 是否正在加载 */
  isLoading: boolean
  /** 文本是否已修改（与原文不同） */
  hasChanges: boolean
  /** 是否有可重新识别的图片 */
  canRecognize?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  hasContent: false,
  isLoading: false,
  hasChanges: false,
  canRecognize: false,
})

const emit = defineEmits<{
  /** 复制事件 */
  (e: 'copy'): void
  /** 格式化事件 */
  (e: 'format', type: FormatType): void
  /** 恢复原文事件 */
  (e: 'restore'): void
  /** 翻译事件 */
  (e: 'translate'): void
  /** 本地 OCR 重新识别事件 */
  (e: 'local-ocr'): void
  /** 百度高精度 OCR 重新识别事件 */
  (e: 'baidu-ocr'): void
}>()

// ============================================
// Constants
// ============================================

/** 排版选项列表 */
const formatOptions: FormatOption[] = [
  { type: 'clean-symbols', label: '清理符号噪声', icon: 'eraser' },
  { type: 'merge-lines', label: '合并为单行', icon: 'merge' },
  { type: 'smart-paragraphs', label: '智能分段', icon: 'paragraph' },
  { type: 'remove-spaces', label: '移除多余空格', icon: 'broom' },
  { type: 'punct-to-en', label: '中文标点转英文', icon: 'text-en' },
  { type: 'punct-to-cn', label: '英文标点转中文', icon: 'text-cn' },
  { type: 'strip-line-numbers', label: '去除行号', icon: 'hash' },
  { type: 'add-line-numbers', label: '添加编号', icon: 'list-ordered' },
  { type: 'remove-cjk-spaces', label: '中文去空格', icon: 'cjk-space' },
]

// ============================================
// Refs
// ============================================

/** 排版下拉菜单容器引用 */
const formatDropdownRef = ref<HTMLDivElement | null>(null)

/** 排版菜单是否打开 */
const isFormatMenuOpen = ref(false)

// 获取图标 SVG
function getIcon(name: string): string {
  const icons: Record<string, string> = {
    eraser: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"></path><path d="M22 21H7"></path><path d="m5 11 9 9"></path></svg>`,
    copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
    format: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="7.5 4.21 12 6.81 16.5 4.21"></polyline><polyline points="7.5 19.79 12 17.19 16.5 19.79"></polyline><polyline points="10 9 9 9 8 9"></polyline></svg>`,
    restore: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>`,
    scan: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7V5a2 2 0 0 1 2-2h2"></path><path d="M17 3h2a2 2 0 0 1 2 2v2"></path><path d="M21 17v2a2 2 0 0 1-2 2h-2"></path><path d="M7 21H5a2 2 0 0 1-2-2v-2"></path><path d="M7 8h10"></path><path d="M7 12h8"></path><path d="M7 16h6"></path></svg>`,
    accurate: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.9 5.8H20l-4.9 3.6 1.9 5.8L12 14.6 7.1 18.2 9 12.4 4 8.8h6.1L12 3z"></path></svg>`,
    translate: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
    merge: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 9l4-4 4 4"></path><path d="M12 5v14"></path></svg>`,
    paragraph: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" y1="10" x2="3" y2="10"></line><line x1="21" y1="6" x2="3" y2="6"></line><line x1="21" y1="14" x2="3" y2="14"></line><line x1="21" y1="18" x2="3" y2="18"></line></svg>`,
    broom: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>`,
    'text-en': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 7 4 4 20 4 20 7"></polyline><line x1="9" y1="20" x2="15" y2="20"></line><line x1="12" y1="4" x2="12" y2="20"></line></svg>`,
    'text-cn': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><text x="8" y="16" font-size="10" fill="currentColor">中</text></svg>`,
    hash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="9" x2="20" y2="9"></line><line x1="4" y1="15" x2="20" y2="15"></line><line x1="10" y1="3" x2="8" y2="21"></line><line x1="16" y1="3" x2="14" y2="21"></line></svg>`,
    'list-ordered': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="10" y1="6" x2="21" y2="6"></line><line x1="10" y1="12" x2="21" y2="12"></line><line x1="10" y1="18" x2="21" y2="18"></line><text x="1" y="9" font-size="8" fill="currentColor" stroke="none" font-weight="bold">1</text><text x="1" y="15" font-size="8" fill="currentColor" stroke="none" font-weight="bold">2</text><text x="1" y="21" font-size="8" fill="currentColor" stroke="none" font-weight="bold">3</text></svg>`,
    'cjk-space': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><text x="2" y="16" font-size="12" fill="currentColor">字</text><path d="M13 8h6"></path><path d="M13 8l3 8 3-8"></path><line x1="11" y1="4" x2="11" y2="20" stroke-dasharray="2 2"></line></svg>`,
  }
  return icons[name] || ''
}

// ============================================
// Methods - Event Handlers
// ============================================

/**
 * 处理复制按钮点击
 * @validates Requirements 5.1, 5.7
 */
function handleCopy(): void {
  if (!props.hasContent || props.isLoading) return
  emit('copy')
}

/**
 * 切换排版菜单显示状态
 * @validates Requirements 5.2, 5.7
 */
function toggleFormatMenu(): void {
  if (!props.hasContent || props.isLoading) return
  isFormatMenuOpen.value = !isFormatMenuOpen.value
}

/**
 * 处理格式化选项点击
 * @param type 格式化类型
 * @validates Requirements 5.2, 5.7
 */
function handleFormat(type: FormatType): void {
  emit('format', type)
  isFormatMenuOpen.value = false
}

/**
 * 处理恢复原文按钮点击
 * @validates Requirements 5.3, 5.7
 */
function handleRestore(): void {
  if (!props.hasChanges || props.isLoading) return
  emit('restore')
}

function handleLocalOcr(): void {
  if (!props.canRecognize || props.isLoading) return
  emit('local-ocr')
}

function handleBaiduOcr(): void {
  if (!props.canRecognize || props.isLoading) return
  emit('baidu-ocr')
}

/**
 * 处理翻译按钮点击
 * @validates Requirements 5.4, 5.7
 */
function handleTranslate(): void {
  if (!props.hasContent || props.isLoading) return
  emit('translate')
}

/**
 * 处理点击外部关闭下拉菜单
 */
function handleClickOutside(event: MouseEvent): void {
  if (
    formatDropdownRef.value &&
    !formatDropdownRef.value.contains(event.target as Node)
  ) {
    isFormatMenuOpen.value = false
  }
}

/**
 * 处理 Escape 键关闭下拉菜单
 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && isFormatMenuOpen.value) {
    isFormatMenuOpen.value = false
  }
}

// ============================================
// Lifecycle
// ============================================

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.ocr-toolbar {
  display: flex;
  align-items: center;
  gap: 4px; /* 更紧凑 */
  padding: 0 8px; /* 减少水平 Padding */
  height: 57px; /* 与左侧列表头部对齐 (12+12+32 + 1px border = 57px) */
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

/* 工具栏按钮基础样式 */
.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px; /* 固定高度 */
  padding: 0 10px;
  background: transparent; /* 默认透明，更像原生工具栏 */
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.1s ease-out; /* 更快的响应 */
  user-select: none;
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary); /* 悬停时显示背景 */
  color: var(--color-text-primary);
}

.toolbar-btn:active:not(:disabled) {
  background: var(--color-border-light); /* 点击时稍深 */
  transform: none; /* 移除缩放，保持稳重 */
}

.toolbar-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

/* 禁用状态 */
.toolbar-btn.is-disabled,
.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

/* 激活状态（下拉菜单打开时） */
.toolbar-btn.is-active {
  background: var(--color-bg-tertiary); /* 保持悬停态 */
  color: var(--color-text-primary);
}

/* 按钮图标 */
.btn-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 2px;
}

.btn-icon :deep(svg) {
  width: 100%;
  height: 100%;
}

/* 按钮文字 */
.btn-text {
  font-weight: 500;
}

/* 下拉箭头 */
.dropdown-arrow {
  font-size: 8px;
  margin-left: 2px;
  transition: transform 0.2s ease;
}

.dropdown-arrow.is-open {
  transform: rotate(180deg);
}

/* 下拉菜单容器 */
.toolbar-dropdown {
  position: relative;
}

/* 下拉菜单 */
.dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 180px;
  padding: 6px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
}

/* 下拉菜单项 */
.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.dropdown-item:hover {
  background: var(--color-accent);
  color: var(--color-text-primary);
}

.dropdown-item:active {
  background: var(--color-accent-active);
}

.dropdown-item:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

.item-icon {
  width: 14px;
  height: 14px;
}

.item-text {
  flex: 1;
}

/* 分隔线 */
.toolbar-divider {
  width: 1px;
  height: 20px;
  margin: 0 8px;
  background: var(--color-border-light);
}

/* 下拉菜单动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.dropdown-enter-to,
.dropdown-leave-from {
  opacity: 1;
  transform: translateY(0);
}

/* 搜索文件按钮特殊样式 @validates Requirements 7.1 */
/* 搜索文件按钮特殊样式 @validates Requirements 7.1 */
.toolbar-btn.search-btn {
  /* 保持一点区别，但不要太跳脱 */
  color: var(--color-accent);
  font-weight: 500;
}

.toolbar-btn.search-btn:hover:not(:disabled) {
  background: var(--color-accent-light);
  color: var(--color-accent);
}

.toolbar-btn.search-btn:active:not(:disabled) {
  background: var(--color-accent-light);
  opacity: 0.8;
}




</style>
