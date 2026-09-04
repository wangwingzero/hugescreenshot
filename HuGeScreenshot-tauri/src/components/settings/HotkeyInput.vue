<template>
  <div
    class="hotkey-input"
    :class="{ 'is-recording': isRecording, 'has-error': hasConflict }"
    ref="rootEl"
    tabindex="0"
    @click="startRecording"
  >
    <span v-if="isRecording" class="recording-hint">
      按下快捷键组合...
    </span>
    <span v-else-if="displayValue" class="hotkey-display">
      {{ displayValue }}
    </span>
    <span v-else class="placeholder">
      点击设置热键
    </span>

    <button
      v-if="modelValue && !isRecording"
      class="clear-btn"
      title="清除"
      @click.stop="handleClear"
    >
      ✕
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * 热键输入组件
 *
 * 用于捕获和显示快捷键组合。
 * 支持 Ctrl、Alt、Shift、Meta 修饰键 + 普通键。
 *
 * @validates Requirements 3.5, 3.6
 */

import { ref, computed, watch, onUnmounted } from 'vue'

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 当前热键值（如 "Ctrl+Shift+A"） */
  modelValue: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}>()

// ============================================
// State
// ============================================

const rootEl = ref<HTMLElement | null>(null)

/** 是否正在录制 */
const isRecording = ref(false)

/** 是否有冲突 */
const hasConflict = ref(false)

/** 当前按下的修饰键 */
const modifiers = ref<Set<string>>(new Set())

// ============================================
// Computed
// ============================================

/** 显示用的热键文本 */
const displayValue = computed(() => {
  return formatHotkey(props.modelValue)
})

// ============================================
// Methods
// ============================================

/**
 * 格式化热键显示
 */
function formatHotkey(shortcut: string): string {
  if (!shortcut) return ''

  // 将内部格式转换为显示格式
  return shortcut
    .replace(/Ctrl/g, 'Ctrl')
    .replace(/Alt/g, 'Alt')
    .replace(/Shift/g, 'Shift')
    .replace(/Meta/g, '⌘')
    .replace(/\+/g, ' + ')
}

/**
 * 开始录制
 */
function startRecording(): void {
  isRecording.value = true
  modifiers.value.clear()
  hasConflict.value = false
}

/**
 * 停止录制
 */
function stopRecording(): void {
  isRecording.value = false
  modifiers.value.clear()
}

/**
 * 从 KeyboardEvent 解析主键（Windows 按住 Alt 时 event.key 不可靠，优先用 code）
 */
function resolveMainKey(event: KeyboardEvent): string | null {
  const key = event.key

  if (['Control', 'Alt', 'Shift', 'Meta'].includes(key)) {
    return null
  }

  if (key === 'Escape') {
    return 'Escape'
  }

  const code = event.code
  if (code.startsWith('Key') && code.length === 4) {
    return code.slice(3)
  }
  if (code.startsWith('Digit') && code.length === 6) {
    return code.slice(5)
  }
  if (code.startsWith('Arrow')) {
    return code.replace('Arrow', '')
  }
  if (code === 'Space') {
    return 'Space'
  }
  if (key.length === 1) {
    return key.toUpperCase()
  }
  if (key.startsWith('Arrow')) {
    return key.replace('Arrow', '')
  }
  if (key === ' ') {
    return 'Space'
  }

  return key.length > 0 ? key : null
}

/**
 * 处理键盘按下（window 捕获阶段，避免 Alt 触发菜单导致 blur 丢键）
 */
function handleKeyDown(event: KeyboardEvent): void {
  if (!isRecording.value) return

  event.preventDefault()
  event.stopPropagation()

  const mods: string[] = []
  if (event.ctrlKey) mods.push('Ctrl')
  if (event.altKey) mods.push('Alt')
  if (event.shiftKey) mods.push('Shift')
  if (event.metaKey) mods.push('Meta')

  const mainKey = resolveMainKey(event)

  if (mainKey === 'Escape') {
    hasConflict.value = false
    stopRecording()
    return
  }

  if (mainKey === null) {
    modifiers.value = new Set(mods)
    return
  }

  if (mods.length === 0) {
    hasConflict.value = true
    return
  }

  hasConflict.value = false
  const shortcut = [...mods, mainKey].join('+')

  emit('update:modelValue', shortcut)
  emit('change', shortcut)
  stopRecording()
}

/** 点击组件外取消录制 */
function handleDocumentMouseDown(event: MouseEvent): void {
  if (!isRecording.value) return
  const el = rootEl.value
  if (el && event.target instanceof Node && el.contains(event.target)) {
    return
  }
  hasConflict.value = false
  stopRecording()
}

function bindRecordingListeners(): void {
  window.addEventListener('keydown', handleKeyDown, true)
  window.addEventListener('mousedown', handleDocumentMouseDown, true)
}

function unbindRecordingListeners(): void {
  window.removeEventListener('keydown', handleKeyDown, true)
  window.removeEventListener('mousedown', handleDocumentMouseDown, true)
}

watch(isRecording, (recording) => {
  if (recording) {
    bindRecordingListeners()
    rootEl.value?.focus()
  } else {
    unbindRecordingListeners()
  }
})

onUnmounted(() => {
  unbindRecordingListeners()
})

/**
 * 清除热键
 */
function handleClear(): void {
  emit('update:modelValue', '')
  emit('change', '')
}
</script>

<style scoped>
.hotkey-input {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 150px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-input-bg);
  cursor: pointer;
  transition: all 0.1s;
  user-select: none;
}

.hotkey-input:hover {
  border-color: var(--color-text-tertiary);
}

.hotkey-input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.hotkey-input.is-recording {
  border-color: var(--color-accent);
  background: var(--color-accent-light);
}

.hotkey-input.has-error {
  border-color: var(--color-error);
}

.recording-hint {
  color: var(--color-accent);
  font-size: 12px;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.hotkey-display {
  color: var(--color-text-primary);
  font-size: 12px;
  font-family: monospace;
}

.placeholder {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.clear-btn {
  padding: 2px 6px;
  border: none;
  border-radius: 2px;
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: 10px;
  cursor: pointer;
  transition: all 0.1s;
}

.clear-btn:hover {
  background: var(--color-error-light);
  color: var(--color-text-primary);
}
</style>
