<template>
  <div v-if="visible" class="save-toolbar">
    <div class="toolbar-hint">
      <span class="hint-icon icon-container" v-html="infoIcon"></span>
      <span class="hint-text">截图尚未保存到历史记录</span>
    </div>
    <div class="toolbar-actions">
      <button class="btn btn-primary" @click="handleSave" :disabled="isSaving">
        <span v-if="isSaving" class="loading-spinner"></span>
        <span v-else v-html="saveIcon"></span>
        <span>{{ isSaving ? '保存中...' : '保存' }}</span>
      </button>
      <button class="btn btn-secondary" @click="handleCopy" :disabled="isCopying">
        <span v-html="copyIcon"></span>
        <span>复制</span>
      </button>
      <button class="btn btn-danger" @click="handleDiscard">
        <span v-html="trashIcon"></span>
        <span>丢弃</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 保存工具栏组件
 * 
 * Feature: workbench-temporary-preview
 * 在临时预览模式下显示，提供保存、复制、丢弃操作
 */

import { ref } from 'vue'

// ============================================
// Props
// ============================================

interface Props {
  /** 是否显示工具栏 */
  visible: boolean
}

defineProps<Props>()

// ============================================
// Emits
// ============================================

const emit = defineEmits<{
  /** 保存按钮点击 */
  (e: 'save'): void
  /** 复制按钮点击 */
  (e: 'copy'): void
  /** 丢弃按钮点击 */
  (e: 'discard'): void
}>()

// ============================================
// State
// ============================================

const isSaving = ref(false)
const isCopying = ref(false)

// ============================================
// Icons (inline SVG)
// ============================================

const infoIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`

const saveIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>`

const copyIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`

const trashIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`

// ============================================
// Handlers
// ============================================

async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    emit('save')
  } finally {
    // 延迟重置状态，让父组件有时间处理
    setTimeout(() => {
      isSaving.value = false
    }, 500)
  }
}

async function handleCopy(): Promise<void> {
  isCopying.value = true
  try {
    emit('copy')
  } finally {
    setTimeout(() => {
      isCopying.value = false
    }, 300)
  }
}

function handleDiscard(): void {
  emit('discard')
}
</script>

<style scoped>
.save-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, var(--color-accent-light) 0%, var(--color-accent-light) 100%);
  border-bottom: 1px solid var(--color-border-focus);
  gap: 16px;
}

.toolbar-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.hint-icon {
  width: 16px;
  height: 16px;
  color: var(--color-accent);
}

.hint-text {
  white-space: nowrap;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.btn :deep(svg) {
  width: 14px;
  height: 14px;
}

.btn-primary {
  background: var(--color-accent);
  color: var(--color-text-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-bg-hover);
}

.btn-danger {
  background: transparent;
  color: var(--color-text-secondary);
}

.btn-danger:hover {
  background: var(--color-error-light);
  color: var(--color-error);
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-text-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
