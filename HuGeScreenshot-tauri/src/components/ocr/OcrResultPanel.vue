<template>
  <div class="ocr-result-panel" :class="{ 'is-loading': isLoading }">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-overlay">
      <div class="loading-spinner" />
      <span class="loading-text">正在识别文字...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-text">{{ error }}</span>
      <button class="retry-btn" @click="handleRetry">重试</button>
    </div>

    <!-- 无结果状态 -->
    <div v-else-if="!hasResult" class="empty-state">
      <span class="empty-icon">📝</span>
      <span class="empty-text">点击 OCR 按钮识别文字</span>
    </div>

    <!-- OCR 结果 -->
    <template v-else>
      <!-- 图像容器 (带文字区域高亮) -->
      <div 
        ref="imageContainerRef"
        class="image-container"
        :style="imageContainerStyle"
      >
        <img 
          ref="imageRef"
          :src="imageSrc" 
          class="ocr-image"
          @load="handleImageLoad"
        />
        
        <!-- 文字区域高亮层 -->
        <div class="text-boxes-layer">
          <OcrTextBox
            v-for="(box, index) in ocrResult?.boxes ?? []"
            :key="index"
            :box="box"
            :image-width="imageSize.width"
            :image-height="imageSize.height"
            :container-width="containerSize.width"
            :container-height="containerSize.height"
            :is-selected="selectedBoxIndex === index"
            :show-preview="true"
            @click="handleBoxClick(box, index)"
            @hover="handleBoxHover"
          />
        </div>
      </div>

      <!-- 文字结果面板 -->
      <div class="text-result-panel">
        <div class="panel-header">
          <span class="panel-title">识别结果</span>
          <span class="panel-stats">
            {{ ocrResult?.boxes.length ?? 0 }} 个文字区域 · {{ elapsedTime }}
          </span>
        </div>

        <!-- 全文复制区域 -->
        <div class="full-text-area">
          <textarea
            ref="textareaRef"
            class="text-content"
            :value="ocrResult?.text ?? ''"
            readonly
            @focus="handleTextareaFocus"
          />
          <div class="text-actions">
            <button 
              class="action-btn copy-all-btn"
              :class="{ 'is-copied': isCopied }"
              @click="handleCopyAll"
            >
              <span class="btn-icon">{{ isCopied ? '✓' : '📋' }}</span>
              <span class="btn-text">{{ isCopied ? '已复制' : '复制全部' }}</span>
            </button>
            <!-- 翻译按钮 -->
            <button 
              class="action-btn translate-btn"
              :class="{ 'is-active': showTranslation }"
              @click="toggleTranslation"
            >
              <span class="btn-icon">🌐</span>
              <span class="btn-text">{{ showTranslation ? '隐藏翻译' : '翻译' }}</span>
            </button>
          </div>
        </div>

        <!-- 翻译面板 -->
        <TranslationPanel
          v-if="showTranslation"
          :source-text="ocrResult?.text ?? ''"
          :translated-text="translationResult?.translatedText ?? ''"
          :source-lang="translationResult?.sourceLang ?? ''"
          :used-provider="translationResult?.provider ?? currentProvider"
          :is-loading="isTranslating"
          :error="translationError"
          :target-lang="currentTargetLang"
          :provider="currentProvider"
          @translate="handleTranslate"
          @copy="handleTranslationCopy"
          @provider-change="handleProviderChange"
          @target-lang-change="handleTargetLangChange"
        />

        <!-- 单个文字区域列表 -->
        <div class="text-boxes-list">
          <div
            v-for="(box, index) in ocrResult?.boxes ?? []"
            :key="index"
            class="text-box-item"
            :class="{ 
              'is-selected': selectedBoxIndex === index,
              'is-hovered': hoveredBoxIndex === index 
            }"
            @mouseenter="hoveredBoxIndex = index"
            @mouseleave="hoveredBoxIndex = -1"
            @click="handleBoxItemClick(box, index)"
          >
            <span class="box-text">{{ box.text }}</span>
            <span class="box-confidence">{{ Math.round(box.confidence * 100) }}%</span>
            <button 
              class="copy-btn"
              :title="'复制: ' + box.text"
              @click.stop="handleCopyBox(box)"
            >
              📋
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- 复制成功提示 -->
    <Transition name="toast">
      <div v-if="showToast" class="copy-toast">
        {{ toastMessage }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
/**
 * OCR 结果显示面板
 * 
 * 功能：
 * - 显示 OCR 识别结果
 * - 文字区域高亮显示
 * - 点击复制单个文字区域
 * - 复制全部文字
 * - 翻译 OCR 结果
 * - 加载状态和错误处理
 * 
 * @validates Requirements 8.1, 8.4, 9.1, 9.2
 */

import { ref, computed, watch, onUnmounted } from 'vue'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import OcrTextBox from './OcrTextBox.vue'
import TranslationPanel from './TranslationPanel.vue'
import { useTranslation } from '@/composables/useTranslation'
import type { OcrResult, OcrTextBox as OcrTextBoxType, TranslateProvider } from '@/types'

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** OCR 结果 */
  ocrResult?: OcrResult | null
  /** 图像源 URL */
  imageSrc?: string
  /** 图像文件路径 */
  imagePath?: string
  /** 是否正在加载 */
  isLoading?: boolean
  /** 错误信息 */
  error?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  ocrResult: null,
  imageSrc: '',
  imagePath: '',
  isLoading: false,
  error: null,
})

const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'copy', text: string): void
  (e: 'box-select', box: OcrTextBoxType, index: number): void
}>()

// ============================================
// Composables
// ============================================

const {
  translationResult,
  isLoading: isTranslating,
  error: translationError,
  currentProvider,
  currentTargetLang,
  translate,
  setProvider,
  setTargetLang,
  clearResult: clearTranslation,
} = useTranslation()

// ============================================
// Refs
// ============================================

const imageContainerRef = ref<HTMLDivElement | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

// ============================================
// State
// ============================================

/** 图像原始尺寸 (物理像素) */
const imageSize = ref({ width: 1, height: 1 })

/** 容器尺寸 (逻辑像素) */
const containerSize = ref({ width: 1, height: 1 })

/** 选中的文字框索引 */
const selectedBoxIndex = ref(-1)

/** 悬停的文字框索引 */
const hoveredBoxIndex = ref(-1)

/** 是否已复制 */
const isCopied = ref(false)

/** 是否显示复制提示 */
const showToast = ref(false)

/** Toast 消息内容 */
const toastMessage = ref('✓ 已复制到剪贴板')

/** 是否显示翻译面板 */
const showTranslation = ref(false)

// ============================================
// Computed
// ============================================

/** 是否有结果 */
const hasResult = computed(() => 
  props.ocrResult && props.ocrResult.boxes.length > 0
)

/** 耗时显示 */
const elapsedTime = computed(() => {
  if (!props.ocrResult) return ''
  const ms = Math.round(props.ocrResult.elapse * 1000)
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`
})

/** 图像容器样式 */
const imageContainerStyle = computed(() => {
  // 保持图像宽高比
  return {
    maxWidth: '100%',
    maxHeight: '400px',
  }
})

// ============================================
// Methods
// ============================================

/**
 * 处理图像加载完成
 * 获取图像原始尺寸用于坐标转换
 */
function handleImageLoad(): void {
  if (!imageRef.value) return
  
  // 获取图像原始尺寸 (物理像素)
  imageSize.value = {
    width: imageRef.value.naturalWidth,
    height: imageRef.value.naturalHeight,
  }
  
  // 获取容器显示尺寸 (逻辑像素)
  updateContainerSize()
}

/**
 * 更新容器尺寸
 */
function updateContainerSize(): void {
  if (!imageRef.value) return
  
  containerSize.value = {
    width: imageRef.value.clientWidth,
    height: imageRef.value.clientHeight,
  }
}

/**
 * 处理文字框点击
 */
function handleBoxClick(box: OcrTextBoxType, index: number): void {
  selectedBoxIndex.value = index
  handleCopyBox(box)
  emit('box-select', box, index)
}

/**
 * 处理文字框悬停
 */
function handleBoxHover(box: OcrTextBoxType | null): void {
  if (box) {
    const index = props.ocrResult?.boxes.indexOf(box) ?? -1
    hoveredBoxIndex.value = index
  } else {
    hoveredBoxIndex.value = -1
  }
}

/**
 * 处理列表项点击
 */
function handleBoxItemClick(box: OcrTextBoxType, index: number): void {
  selectedBoxIndex.value = index
  emit('box-select', box, index)
}

/**
 * 复制单个文字框
 */
async function handleCopyBox(box: OcrTextBoxType): Promise<void> {
  try {
    await writeText(box.text)
    showCopyToast('✓ 已复制到剪贴板')
    emit('copy', box.text)
  } catch (error) {
    console.error('Failed to copy text:', error)
    showCopyToast('✕ 复制失败，请重试')
  }
}

/**
 * 复制全部文字
 */
async function handleCopyAll(): Promise<void> {
  if (!props.ocrResult) return
  
  try {
    await writeText(props.ocrResult.text)
    isCopied.value = true
    showCopyToast('✓ 已复制到剪贴板')
    emit('copy', props.ocrResult.text)
    
    // 2秒后重置状态
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy text:', error)
    showCopyToast('✕ 复制失败，请重试')
  }
}

/**
 * 显示复制提示
 */
function showCopyToast(message: string = '✓ 已复制到剪贴板'): void {
  toastMessage.value = message
  showToast.value = true
  setTimeout(() => {
    showToast.value = false
  }, 1500)
}

/**
 * 处理文本框聚焦 (全选)
 */
function handleTextareaFocus(): void {
  textareaRef.value?.select()
}

/**
 * 处理重试
 */
function handleRetry(): void {
  emit('retry')
}

/**
 * 切换翻译面板显示
 */
async function toggleTranslation(): Promise<void> {

  showTranslation.value = !showTranslation.value
  
  // 如果显示翻译面板且没有翻译结果，自动开始翻译
  if (showTranslation.value && !translationResult.value && props.ocrResult?.text) {
    const targetLang = currentTargetLang.value ?? 'zh'
    const provider = currentProvider.value ?? 'google'
    handleTranslate(targetLang, provider)
  }
}

/**
 * 处理翻译请求
 */
async function handleTranslate(targetLang: string, provider: TranslateProvider): Promise<void> {
  if (!props.ocrResult?.text) return
  
  await translate(props.ocrResult.text, targetLang, provider)
}

/**
 * 处理翻译结果复制
 */
function handleTranslationCopy(text: string): void {
  showCopyToast('✓ 翻译结果已复制')
  emit('copy', text)
}

/**
 * 处理提供商变更
 */
function handleProviderChange(provider: TranslateProvider): void {
  setProvider(provider)
}

/**
 * 处理目标语言变更
 */
function handleTargetLangChange(lang: string): void {
  setTargetLang(lang)
}

// ============================================
// Watchers
// ============================================

// 监听结果变化，重置选中状态和翻译
watch(() => props.ocrResult, () => {
  selectedBoxIndex.value = -1
  hoveredBoxIndex.value = -1
  isCopied.value = false
  clearTranslation()
  showTranslation.value = false
})

// 监听窗口大小变化
if (typeof window !== 'undefined') {
  window.addEventListener('resize', updateContainerSize)
}

// 组件卸载时清理事件监听
onUnmounted(() => {
  window.removeEventListener('resize', updateContainerSize)
})
</script>

<style scoped>
.ocr-result-panel {
  --color-translate: #9c27b0;
  --color-translate-ring: color-mix(in srgb, #9c27b0 30%, transparent);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--color-bg-elevated);
  border-radius: 8px;
  max-height: 600px;
  overflow: hidden;
  position: relative;
}

/* 加载状态 */
.loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  color: var(--color-text-primary);
  font-size: 14px;
}

/* 错误状态 */
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
}

.error-icon {
  font-size: 32px;
}

.error-text {
  color: var(--color-error);
  font-size: 14px;
  text-align: center;
}

.retry-btn {
  margin-top: 8px;
  padding: 6px 16px;
  background: var(--color-accent);
  border: none;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.retry-btn:hover {
  background: var(--color-accent-hover);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px;
  color: var(--color-text-tertiary);
}

.empty-icon {
  font-size: 32px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
}

/* 图像容器 */
.image-container {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  background: var(--color-bg-primary);
}

.ocr-image {
  display: block;
  width: 100%;
  height: auto;
  max-height: 400px;
  object-fit: contain;
}

.text-boxes-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: auto;
}

/* 文字结果面板 */
.text-result-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px;
}

.panel-title {
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 500;
}

.panel-stats {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

/* 全文复制区域 */
.full-text-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.text-content {
  width: 100%;
  min-height: 80px;
  max-height: 120px;
  padding: 8px;
  background: var(--color-input-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  font-family: 'Microsoft YaHei', sans-serif;
  line-height: 1.5;
  resize: none;
  outline: none;
}

.text-content:focus {
  border-color: var(--color-border-focus);
}

.text-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--color-accent);
  border: none;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--color-accent-hover);
}

.action-btn.is-copied {
  background: var(--color-success);
}

.action-btn.translate-btn {
  background: var(--color-translate);
}

.action-btn.translate-btn:hover {
  background: var(--color-translate);
}

.action-btn.translate-btn.is-active {
  background: var(--color-translate);
  box-shadow: 0 0 0 2px var(--color-translate-ring);
}


.btn-icon {
  font-size: 14px;
}

/* 文字区域列表 */
.text-boxes-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.text-boxes-list::-webkit-scrollbar {
  width: 6px;
}

.text-boxes-list::-webkit-scrollbar-track {
  background: var(--color-surface-subtle);
  border-radius: 3px;
}

.text-boxes-list::-webkit-scrollbar-thumb {
  background: var(--color-surface-strong);
  border-radius: 3px;
}

.text-box-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--color-surface-subtle);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.1s;
}

.text-box-item:hover,
.text-box-item.is-hovered {
  background: var(--color-accent-light);
}

.text-box-item.is-selected {
  background: var(--color-success-light);
  outline: 1px solid var(--color-success);
}

.box-text {
  flex: 1;
  color: var(--color-text-primary);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.box-confidence {
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-family: 'Consolas', monospace;
}

.copy-btn {
  padding: 2px 6px;
  background: transparent;
  border: none;
  border-radius: 3px;
  font-size: 12px;
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.1s;
}

.copy-btn:hover {
  opacity: 1;
  background: var(--color-surface-strong);
}

/* 复制提示 */
.copy-toast {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 16px;
  background: var(--color-success);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  box-shadow: var(--shadow-md);
  z-index: 100;
}

/* Toast 动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
</style>
