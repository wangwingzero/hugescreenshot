<template>
  <div class="ocr-content-panel">
    <!-- 临时预览模式：保存工具栏 -->
    <SaveToolbar
      :visible="workbenchStore.isTemporaryMode"
      @save="handleTemporarySave"
      @copy="handleTemporaryCopy"
      @discard="handleTemporaryDiscard"
    />

    <!-- 空状态：未选择任何项目且不在临时模式 -->
    <div v-if="!historyItem && !workbenchStore.isTemporaryMode" class="empty-state">
      <span class="empty-icon icon-container" v-html="getIcon('note')"></span>
      <span class="empty-title">选择截图查看 OCR 结果</span>
      <span class="empty-hint">从左侧列表中选择一个截图，即可在此查看识别的文字内容</span>
    </div>

    <!-- 临时预览模式：显示临时图片 -->
    <template v-else-if="workbenchStore.isTemporaryMode">
      <!-- 工具栏 -->
      <OcrToolbar
        :has-content="hasOcrContent"
        :is-loading="workbenchStore.isOcrLoading"
        :has-changes="workbenchStore.hasTextChanges"
        @copy="handleCopy"
        @format="handleFormat"
        @restore="handleRestore"
        @translate="handleTranslate"
      />

      <!-- 图片预览区域 -->
      <div class="image-preview-section">
        <img
          v-if="workbenchStore.temporaryImageUrl"
          :src="workbenchStore.temporaryImageUrl"
          class="preview-image"
          alt="临时截图预览"
        />
      </div>

      <!-- OCR 文本内容区域 -->
      <div class="content-section">
        <textarea
          ref="textareaRef"
          v-model="ocrTextModel"
          class="ocr-textarea"
          placeholder="点击「识别文字」按钮进行 OCR 识别"
        />
      </div>

      <!-- 状态栏 -->
      <OcrStatusBar
        :char-count="workbenchStore.charCount"
        :status="workbenchStore.ocrStatus"
        :confidence="workbenchStore.ocrStats?.confidence && workbenchStore.ocrStats.confidence > 0 ? workbenchStore.ocrStats.confidence : null"
        :elapsed-time="workbenchStore.ocrStats?.elapsedTime && workbenchStore.ocrStats.elapsedTime > 0 ? workbenchStore.ocrStats.elapsedTime : null"
        :engine="workbenchStore.ocrStats?.engine || null"
      />
    </template>

    <!-- 有选中项目时显示内容 -->
    <template v-else>
      <!-- 工具栏 -->
      <OcrToolbar
        :has-content="hasOcrContent"
        :is-loading="workbenchStore.isOcrLoading"
        :has-changes="workbenchStore.hasTextChanges"
        @copy="handleCopy"
        @format="handleFormat"
        @restore="handleRestore"
        @translate="handleTranslate"
      />

      <!-- 图片预览区域 -->


      <!-- OCR 文本内容区域 -->
      <div class="content-section">
        <textarea
          ref="textareaRef"
          v-model="ocrTextModel"
          class="ocr-textarea"
          placeholder="在此输入或编辑文字..."
        />
      </div>

      <!-- 状态栏 -->
      <OcrStatusBar
        :char-count="workbenchStore.charCount"
        :status="workbenchStore.ocrStatus"
        :confidence="workbenchStore.ocrStats?.confidence && workbenchStore.ocrStats.confidence > 0 ? workbenchStore.ocrStats.confidence : null"
        :elapsed-time="workbenchStore.ocrStats?.elapsedTime && workbenchStore.ocrStats.elapsedTime > 0 ? workbenchStore.ocrStats.elapsedTime : null"
        :engine="workbenchStore.ocrStats?.engine || null"
      />
    </template>

    <!-- 成功提示 Toast -->
    <Transition name="toast">
      <div v-if="showSuccessToast" class="success-toast">
        <span class="toast-icon icon-container" v-html="getIcon('check')"></span>
        <span class="toast-text">{{ toastMessage }}</span>
      </div>
    </Transition>

    <!-- 错误提示 Toast -->
    <Transition name="toast">
      <div v-if="showErrorToast" class="error-toast">
        <span class="toast-icon icon-container" v-html="getIcon('close')"></span>
        <span class="toast-text">{{ errorMessage }}</span>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
/**
 * OCR 内容面板组件
 *
 * 显示选中历史记录的 OCR 内容，包括：
 * - 图片预览
 * - OCR 工具栏（复制、排版、翻译等）
 * - OCR 文本内容
 * - 状态栏（字符数、置信度等）
 *
 * @validates Requirements 4.1, 4.2, 4.3, 4.4, 5.1
 */

import { ref, computed } from 'vue'
import { useWorkbenchStore } from '@/stores/workbench'
import type { HistoryItem } from '@/types'
import type { FormatType } from '@/composables/useOcrTextActions'
import OcrToolbar from './OcrToolbar.vue'
import OcrStatusBar from './OcrStatusBar.vue'
import SaveToolbar from './SaveToolbar.vue'

// ============================================
// Props
// ============================================

interface Props {
  /** 选中的历史记录项 */
  historyItem: HistoryItem | null
}

defineProps<Props>()

// ============================================
// Emits
// ============================================

const emit = defineEmits<{
  /** OCR 完成事件 */
  (e: 'ocr-complete', text: string): void
  /** 复制成功事件 */
  (e: 'copy-success'): void
  /** 错误事件 */
  (e: 'error', message: string): void
}>()

// ============================================
// Store
// ============================================

const workbenchStore = useWorkbenchStore()

// ============================================
// Refs
// ============================================



/** 文本框元素引用 */
const textareaRef = ref<HTMLTextAreaElement | null>(null)



/** 成功提示显示状态 */
const showSuccessToast = ref(false)

/** 成功提示消息 */
const toastMessage = ref('')

/** 错误提示显示状态 */
const showErrorToast = ref(false)

/** 错误提示消息 */
const errorMessage = ref('')

// ============================================
// Computed
// ============================================



/**
 * 是否有 OCR 内容
 */
const hasOcrContent = computed(() => workbenchStore.hasOcrContent)

/**
 * OCR 文本双向绑定模型
 */
const ocrTextModel = computed({
  get: () => workbenchStore.ocrText,
  set: (value: string) => workbenchStore.updateOcrText(value),
})

// ============================================
// Methods - Toast
// ============================================

/**
 * 显示成功提示
 * @param message 提示消息
 * @param duration 显示时长（毫秒）
 */
function showSuccess(message: string, duration = 1500): void {
  toastMessage.value = message
  showSuccessToast.value = true
  setTimeout(() => {
    showSuccessToast.value = false
  }, duration)
}

/**
 * 显示错误提示
 * @param message 错误消息
 * @param duration 显示时长（毫秒）
 */
function showError(message: string, duration = 2000): void {
  errorMessage.value = message
  showErrorToast.value = true
  setTimeout(() => {
    showErrorToast.value = false
  }, duration)
}

// ============================================
// Methods - Event Handlers
// ============================================



/**
 * 处理复制按钮点击
 * 使用 workbenchStore 的 copyText action 复制文本到剪贴板
 * @validates Requirements 5.1
 */
async function handleCopy(): Promise<void> {
  if (!workbenchStore.ocrText) return

  try {
    const success = await workbenchStore.copyText()
    if (success) {
      showSuccess('已复制到剪贴板')
      emit('copy-success')
    } else {
      showError('复制失败：没有可复制的内容')
      emit('error', '复制失败')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '复制失败'
    showError(message)
    emit('error', message)
    console.error('[OcrContentPanel] Copy failed:', error)
  }
}

/**
 * 处理格式化操作
 * @param type 格式化类型
 */
function handleFormat(type: FormatType): void {
  workbenchStore.formatText(type)
  showSuccess('文本已格式化')
}

/**
 * 处理恢复原文操作
 */
function handleRestore(): void {
  workbenchStore.restoreOriginal()
  showSuccess('已恢复原文')
}

/**
 * 处理翻译操作
 */
async function handleTranslate(): Promise<void> {
  try {
    await workbenchStore.translateText()
    showSuccess('翻译完成')
  } catch (error) {
    const message = error instanceof Error ? error.message : '翻译失败'
    showError(message)
    emit('error', message)
  }
}

// ============================================
// Methods - Temporary Preview Mode
// Feature: workbench-temporary-preview
// ============================================

/**
 * 处理临时截图保存
 */
async function handleTemporarySave(): Promise<void> {
  try {
    const historyId = await workbenchStore.confirmAndSave()
    if (historyId !== null) {
      showSuccess('已保存到历史记录')
    } else {
      showError('保存失败')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存失败'
    showError(message)
    emit('error', message)
  }
}

/**
 * 处理临时截图复制
 */
async function handleTemporaryCopy(): Promise<void> {
  try {
    const success = await workbenchStore.copyTemporaryImage()
    if (success) {
      showSuccess('已复制到剪贴板')
    } else {
      showError('复制失败')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '复制失败'
    showError(message)
    emit('error', message)
  }
}

/**
 * 处理临时截图丢弃
 */
function handleTemporaryDiscard(): void {
  workbenchStore.discardTemporary()
  showSuccess('已丢弃截图')
}


// ============================================
// Watchers
// ============================================



/**
 * 获取图标
 */
function getIcon(name: string): string {
  const icons: Record<string, string> = {
    note: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`,
    close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  }
  return icons[name] || ''
}
</script>

<style scoped>
.ocr-content-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-primary);
  position: relative;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--color-text-tertiary);
}

.empty-icon {
  width: 48px;
  height: 48px;
  opacity: 0.6;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.empty-hint {
  font-size: 13px;
  color: var(--color-text-tertiary);
  text-align: center;
  max-width: 280px;
}

/* 图片预览区域 */
.image-preview-section {
  flex-shrink: 0;
  max-height: 200px;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.preview-image {
  max-width: 100%;
  max-height: 176px;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: var(--shadow-sm);
}

/* 内容区域 */
.content-section {
  flex: 1;
  min-height: 0;
  padding: 0; /* Remove padding for seamless look */
  overflow: hidden;
}

.ocr-textarea {
  width: 100%;
  height: 100%;
  padding: 16px; /* Internal padding */
  background: transparent; /* Seamless background */
  border: none; /* Seamless border */
  border-radius: 0;
  color: var(--color-text-primary);
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: background-color 0.15s ease;
}

.ocr-textarea:focus {
  background: var(--color-bg-primary); /* Slight highlight on focus if needed */
  box-shadow: none; /* Clean focus */
}

.ocr-textarea::placeholder {
  color: var(--color-text-tertiary);
}

/* Toast 提示 */
.success-toast,
.error-toast {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  box-shadow: var(--shadow-md);
  z-index: 100;
}

.success-toast {
  background: var(--color-success);
  color: var(--color-text-primary);
}

.error-toast {
  background: var(--color-error);
  color: var(--color-text-primary);
}

.toast-icon {
  width: 16px;
  height: 16px;
}

.toast-text {
  white-space: nowrap;
}

/* Toast 动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.9);
}

.toast-enter-to,
.toast-leave-from {
  opacity: 1;
  transform: translate(-50%, -50%) scale(1);
}
</style>
