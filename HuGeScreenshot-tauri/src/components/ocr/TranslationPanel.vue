<template>
  <div class="translation-panel" :class="{ 'is-loading': isLoading }">
    <!-- 翻译控制栏 -->
    <div class="translation-header">
      <div class="header-left">
        <span class="header-title">🌐 翻译</span>
        <span v-if="sourceLang" class="source-lang">{{ sourceLang }}</span>
        <span class="arrow">→</span>
        <!-- 目标语言选择 -->
        <select 
          v-model="selectedTargetLang" 
          class="lang-select"
          :disabled="isLoading"
          @change="handleTargetLangChange"
        >
          <option 
            v-for="lang in availableTargetLangs" 
            :key="lang.code" 
            :value="lang.code"
          >
            {{ lang.name }}
          </option>
        </select>
      </div>
      
      <div class="header-right">
        <!-- 提供商选择 -->
        <select 
          v-model="selectedProvider" 
          class="provider-select"
          :disabled="isLoading"
          @change="handleProviderChange"
        >
          <option 
            v-for="provider in availableProviders" 
            :key="provider" 
            :value="provider"
          >
            {{ getProviderName(provider) }}
          </option>
        </select>
        
        <!-- 翻译按钮 -->
        <button 
          class="translate-btn"
          :class="{ 'is-loading': isLoading }"
          :disabled="isLoading || !sourceText"
          @click="handleTranslate"
        >
          <span v-if="isLoading" class="loading-spinner" />
          <span v-else class="btn-icon">🔄</span>
          <span class="btn-text">{{ isLoading ? '翻译中...' : '翻译' }}</span>
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-overlay">
      <div class="loading-content">
        <div class="loading-spinner-large" />
        <span class="loading-text">正在翻译...</span>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-text">{{ error }}</span>
      <button class="retry-btn" @click="handleTranslate">重试</button>
    </div>

    <!-- 翻译结果 -->
    <div v-else-if="translatedText" class="translation-result">
      <textarea
        ref="resultTextareaRef"
        class="result-text"
        :value="translatedText"
        readonly
        @focus="handleResultFocus"
      />
      <div class="result-actions">
        <span class="provider-badge">
          {{ getProviderName(usedProvider) }}
        </span>
        <button 
          class="action-btn copy-btn"
          :class="{ 'is-copied': isCopied }"
          @click="handleCopy"
        >
          <span class="btn-icon">{{ isCopied ? '✓' : '📋' }}</span>
          <span class="btn-text">{{ isCopied ? '已复制' : '复制' }}</span>
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <span class="empty-icon">💬</span>
      <span class="empty-text">点击翻译按钮翻译 OCR 结果</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 翻译结果面板组件
 * 
 * 功能：
 * - 显示翻译结果
 * - 支持选择翻译提供商
 * - 支持选择目标语言
 * - 复制翻译结果
 * 
 * @validates Requirements 9.1, 9.2
 */

import { ref, watch } from 'vue'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import type { TranslateProvider } from '@/types'

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 源文本（待翻译） */
  sourceText?: string
  /** 翻译后的文本 */
  translatedText?: string
  /** 检测到的源语言 */
  sourceLang?: string
  /** 使用的提供商 */
  usedProvider?: TranslateProvider
  /** 是否正在加载 */
  isLoading?: boolean
  /** 错误信息 */
  error?: string | null
  /** 当前目标语言 */
  targetLang?: string
  /** 当前提供商 */
  provider?: TranslateProvider
}

const props = withDefaults(defineProps<Props>(), {
  sourceText: '',
  translatedText: '',
  sourceLang: '',
  usedProvider: 'google',
  isLoading: false,
  error: null,
  targetLang: 'zh',
  provider: 'google',
})

const emit = defineEmits<{
  (e: 'translate', targetLang: string, provider: TranslateProvider): void
  (e: 'copy', text: string): void
  (e: 'provider-change', provider: TranslateProvider): void
  (e: 'target-lang-change', lang: string): void
}>()

// ============================================
// Refs
// ============================================

const resultTextareaRef = ref<HTMLTextAreaElement | null>(null)

// ============================================
// State
// ============================================

/** 选择的目标语言 */
const selectedTargetLang = ref(props.targetLang)

/** 选择的提供商 */
const selectedProvider = ref<TranslateProvider>(props.provider)

/** 是否已复制 */
const isCopied = ref(false)

// ============================================
// Constants
// ============================================

/** 可用的翻译提供商 */
const availableProviders: TranslateProvider[] = ['google', 'deepl', 'baidu']

/** 可用的目标语言 */
const availableTargetLangs = [
  { code: 'zh', name: '中文' },
  { code: 'en', name: 'English' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'es', name: 'Español' },
  { code: 'ru', name: 'Русский' },
]

// ============================================
// Methods
// ============================================

/**
 * 获取提供商显示名称
 */
function getProviderName(provider: TranslateProvider): string {
  const names: Record<TranslateProvider, string> = {
    google: 'Google',
    deepl: 'DeepL',
    baidu: '百度',
  }
  return names[provider] || provider
}

/**
 * 处理翻译按钮点击
 */
function handleTranslate(): void {
  emit('translate', selectedTargetLang.value, selectedProvider.value)
}

/**
 * 处理目标语言变更
 */
function handleTargetLangChange(): void {
  emit('target-lang-change', selectedTargetLang.value)
}

/**
 * 处理提供商变更
 */
function handleProviderChange(): void {
  emit('provider-change', selectedProvider.value)
}

/**
 * 处理复制
 */
async function handleCopy(): Promise<void> {
  if (!props.translatedText) return
  
  try {
    await writeText(props.translatedText)
    isCopied.value = true
    emit('copy', props.translatedText)
    
    // 2秒后重置状态
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy translation:', error)
  }
}

/**
 * 处理结果文本框聚焦（全选）
 */
function handleResultFocus(): void {
  resultTextareaRef.value?.select()
}

// ============================================
// Watchers
// ============================================

// 同步 props 到本地状态
watch(() => props.targetLang, (newVal) => {
  selectedTargetLang.value = newVal
})

watch(() => props.provider, (newVal) => {
  selectedProvider.value = newVal
})

// 翻译结果变化时重置复制状态
watch(() => props.translatedText, () => {
  isCopied.value = false
})
</script>

<style scoped>
.translation-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  background: var(--color-bg-elevated);
  border-radius: 6px;
  border: 1px solid var(--color-border);
  position: relative;
}

/* 翻译控制栏 */
.translation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
}

.source-lang {
  color: var(--color-text-secondary);
  font-size: 12px;
  padding: 2px 6px;
  background: var(--color-surface-strong);
  border-radius: 3px;
}

.arrow {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 选择框样式 */
.lang-select,
.provider-select {
  padding: 4px 8px;
  background: var(--color-input-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.lang-select:hover,
.provider-select:hover {
  border-color: var(--color-text-tertiary);
}

.lang-select:focus,
.provider-select:focus {
  border-color: var(--color-border-focus);
}

.lang-select:disabled,
.provider-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.lang-select option,
.provider-select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

/* 翻译按钮 */
.translate-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  background: var(--color-accent);
  border: none;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.translate-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.translate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.translate-btn.is-loading {
  background: var(--color-accent);
}

.btn-icon {
  font-size: 12px;
}

/* 加载动画 */
.loading-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-text-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.loading-spinner-large {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 加载覆盖层 */
.loading-overlay {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.loading-text {
  color: var(--color-text-secondary);
  font-size: 13px;
}

/* 错误状态 */
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
}

.error-icon {
  font-size: 24px;
}

.error-text {
  color: var(--color-error);
  font-size: 13px;
  text-align: center;
}

.retry-btn {
  margin-top: 4px;
  padding: 5px 14px;
  background: var(--color-accent);
  border: none;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.retry-btn:hover {
  background: var(--color-accent-hover);
}

/* 翻译结果 */
.translation-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-text {
  width: 100%;
  min-height: 60px;
  max-height: 150px;
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

.result-text:focus {
  border-color: var(--color-border-focus);
}

.result-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.provider-badge {
  padding: 2px 8px;
  background: var(--color-surface-strong);
  border-radius: 3px;
  color: var(--color-text-secondary);
  font-size: 11px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
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

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px;
  color: var(--color-text-tertiary);
}

.empty-icon {
  font-size: 24px;
  opacity: 0.5;
}

.empty-text {
  font-size: 12px;
}
</style>
