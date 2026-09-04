<template>
  <div class="ocr-status-bar">
    <!-- 字符数统计 -->
    <div class="status-item char-count">
      <span class="status-icon" v-html="getIcon('chart')"></span>
      <span class="status-label">字数</span>
      <span class="status-value">{{ formattedCharCount }}</span>
    </div>

    <!-- 分隔线 -->
    <div class="status-divider" />

    <!-- OCR 状态 -->
    <div class="status-item ocr-status" :class="statusClass">
      <span class="status-icon" v-html="statusIcon"></span>
      <span class="status-label">状态</span>
      <span class="status-value">{{ statusText }}</span>
    </div>

    <!-- 置信度（仅在有值时显示） -->
    <template v-if="confidence !== null">
      <div class="status-divider" />
      <div class="status-item confidence" :class="confidenceClass">
        <span class="status-icon" v-html="getIcon('target')"></span>
        <span class="status-label">置信度</span>
        <span class="status-value">{{ formattedConfidence }}</span>
      </div>
    </template>

    <!-- 处理耗时（仅在有值时显示） -->
    <template v-if="elapsedTime !== null">
      <div class="status-divider" />
      <div class="status-item elapsed-time">
        <span class="status-icon" v-html="getIcon('clock')"></span>
        <span class="status-label">耗时</span>
        <span class="status-value">{{ formattedElapsedTime }}</span>
      </div>
    </template>

    <!-- OCR 引擎（仅在有值时显示） -->
    <template v-if="engine">
      <div class="status-divider" />
      <div class="status-item engine">
        <span class="status-icon" v-html="getIcon('wrench')"></span>
        <span class="status-label">引擎</span>
        <span class="status-value">{{ engine }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * OCR 状态栏组件
 *
 * 显示 OCR 处理的统计信息和状态：
 * - 字符数：显示 OCR 文本的字符数量
 * - 状态：显示当前 OCR 处理状态（就绪、处理中、完成、错误）
 * - 置信度：显示 OCR 识别的置信度百分比
 * - 耗时：显示 OCR 处理所用时间
 * - 引擎：显示使用的 OCR 引擎名称
 *
 * @validates Requirements 6.1, 6.2, 6.3, 6.4
 */

import { computed } from 'vue'

// ============================================
// Types
// ============================================

/** OCR 状态类型 */
export type OcrStatus = 'ready' | 'processing' | 'completed' | 'error'

// ============================================
// Props
// ============================================

interface Props {
  /** 字符数 */
  charCount: number
  /** OCR 状态 */
  status: OcrStatus
  /** 置信度 (0-100)，null 表示不显示 */
  confidence: number | null
  /** 处理耗时（毫秒），null 表示不显示 */
  elapsedTime: number | null
  /** OCR 引擎名称，null 表示不显示 */
  engine: string | null
}

const props = withDefaults(defineProps<Props>(), {
  charCount: 0,
  status: 'ready',
  confidence: null,
  elapsedTime: null,
  engine: null,
})

// ============================================
// Computed - Formatted Values
// ============================================

/**
 * 格式化字符数
 * 使用千分位分隔符，添加"字"后缀
 * @validates Requirements 6.1
 */
const formattedCharCount = computed(() => {
  return `${props.charCount.toLocaleString('zh-CN')} 字`
})

/**
 * 状态图标
 * @validates Requirements 6.2
 */
const statusIcon = computed(() => {
  const icons: Record<OcrStatus, string> = {
    ready: getIcon('circle'),
    processing: getIcon('refresh'),
    completed: getIcon('check-circle'),
    error: getIcon('x-circle'),
  }
  return icons[props.status]
})

/**
 * 状态文本
 * @validates Requirements 6.2
 */
const statusText = computed(() => {
  const texts: Record<OcrStatus, string> = {
    ready: '就绪',
    processing: '处理中...',
    completed: '完成',
    error: '错误',
  }
  return texts[props.status]
})

/**
 * 状态样式类
 * @validates Requirements 6.2
 */
const statusClass = computed(() => {
  return `status-${props.status}`
})

/**
 * 格式化置信度
 * 显示为百分比格式
 * @validates Requirements 6.3
 */
const formattedConfidence = computed(() => {
  if (props.confidence === null) return ''
  return `${Math.round(props.confidence)}%`
})

/**
 * 置信度样式类
 * 根据置信度高低显示不同颜色
 * @validates Requirements 6.3
 */
const confidenceClass = computed(() => {
  if (props.confidence === null) return ''
  if (props.confidence >= 90) return 'confidence-high'
  if (props.confidence >= 70) return 'confidence-medium'
  return 'confidence-low'
})

/**
 * 格式化处理耗时
 * 毫秒转换为秒，保留一位小数
 * @validates Requirements 6.4
 */
const formattedElapsedTime = computed(() => {
  if (props.elapsedTime === null) return ''
  const seconds = props.elapsedTime / 1000
  if (seconds < 1) {
    return `${props.elapsedTime}ms`
  }
  return `${seconds.toFixed(1)}s`
})

/**
 * 获取图标
 */
function getIcon(name: string): string {
  const icons: Record<string, string> = {
    chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="18" y="3" width="4" height="18"/><rect x="10" y="8" width="4" height="13"/><rect x="2" y="13" width="4" height="8"/></svg>`,
    target: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    wrench: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
    circle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>`,
    'check-circle': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
    'x-circle': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
  }
  return icons[name] || ''
}
</script>

<style scoped>
.ocr-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-light);
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

/* 状态项基础样式 */
.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-icon {
  width: 14px;
  height: 14px;
  display: flex;
  color: var(--color-text-secondary);
}

.status-icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.status-label {
  color: var(--color-text-tertiary);
}

.status-value {
  color: var(--color-text-primary);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* 分隔线 */
.status-divider {
  width: 1px;
  height: 14px;
  background: var(--color-border-light);
}

/* 字符数样式 */
.char-count .status-value {
  color: var(--color-info);
}

/* OCR 状态样式 */
.ocr-status.status-ready .status-value {
  color: var(--color-text-tertiary);
}

.ocr-status.status-processing .status-value {
  color: var(--color-warning);
}

.ocr-status.status-processing .status-icon {
  animation: spin 1s linear infinite;
}

.ocr-status.status-completed .status-value {
  color: var(--color-success);
}

.ocr-status.status-error .status-value {
  color: var(--color-error);
}

/* 置信度样式 */
.confidence.confidence-high .status-value {
  color: var(--color-success);
}

.confidence.confidence-medium .status-value {
  color: var(--color-warning);
}

.confidence.confidence-low .status-value {
  color: var(--color-error);
}

/* 耗时样式 */
.elapsed-time .status-value {
  color: var(--color-text-secondary);
}

/* 引擎样式 */
.engine .status-value {
  color: var(--color-text-secondary);
}

/* 旋转动画 */
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 响应式：窄屏隐藏标签 */
@media (max-width: 600px) {
  .status-label {
    display: none;
  }
  
  .ocr-status-bar {
    gap: 6px;
    padding: 6px 8px;
  }
}
</style>
