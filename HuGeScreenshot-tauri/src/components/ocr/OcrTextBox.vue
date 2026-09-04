<template>
  <div
    class="ocr-text-box"
    :class="{ 
      'is-hovered': isHovered,
      'is-selected': isSelected 
    }"
    :style="boxStyle"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @click="handleClick"
    :title="text"
  >
    <!-- 高亮边框 -->
    <div class="box-border" />
    
    <!-- 悬停时显示文字预览 -->
    <div v-if="isHovered && showPreview" class="text-preview">
      <span class="preview-text">{{ text }}</span>
      <span class="preview-confidence">{{ confidencePercent }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * OCR 文字区域组件
 * 
 * 功能：
 * - 显示 OCR 识别的文字区域边界框
 * - 悬停时高亮显示
 * - 点击复制文字到剪贴板
 * - 显示置信度
 * 
 * @validates Requirements 8.1, 8.4
 */

import { ref, computed } from 'vue'
import type { OcrTextBox } from '@/types'

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** OCR 文字框数据 */
  box: OcrTextBox
  /** 图像原始宽度 (物理像素) */
  imageWidth: number
  /** 图像原始高度 (物理像素) */
  imageHeight: number
  /** 容器宽度 (逻辑像素) */
  containerWidth: number
  /** 容器高度 (逻辑像素) */
  containerHeight: number
  /** 是否选中 */
  isSelected?: boolean
  /** 是否显示文字预览 */
  showPreview?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isSelected: false,
  showPreview: true,
})

const emit = defineEmits<{
  (e: 'click', box: OcrTextBox): void
  (e: 'hover', box: OcrTextBox | null): void
}>()

// ============================================
// State
// ============================================

const isHovered = ref(false)

// ============================================
// Computed
// ============================================

/** 文字内容 */
const text = computed(() => props.box.text)

/** 置信度百分比 */
const confidencePercent = computed(() => 
  Math.round(props.box.confidence * 100)
)

/**
 * 计算边界框样式
 * 将物理像素坐标转换为容器内的百分比位置
 */
const boxStyle = computed(() => {
  const { box, imageWidth, imageHeight, containerWidth, containerHeight } = props
  
  // 获取四个角点坐标
  const points = box.box
  if (!points || points.length !== 4) {
    return { display: 'none' }
  }
  
  // 计算边界框的最小外接矩形
  const xs = points.map(p => p[0])
  const ys = points.map(p => p[1])
  
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  
  // 计算缩放比例
  const scaleX = containerWidth / imageWidth
  const scaleY = containerHeight / imageHeight
  
  // 转换为容器内的像素位置
  const left = minX * scaleX
  const top = minY * scaleY
  const width = (maxX - minX) * scaleX
  const height = (maxY - minY) * scaleY
  
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${Math.max(width, 4)}px`,
    height: `${Math.max(height, 4)}px`,
  }
})

// ============================================
// Methods
// ============================================

function handleMouseEnter(): void {
  isHovered.value = true
  emit('hover', props.box)
}

function handleMouseLeave(): void {
  isHovered.value = false
  emit('hover', null)
}

function handleClick(): void {
  emit('click', props.box)
}
</script>

<style scoped>
.ocr-text-box {
  position: absolute;
  cursor: pointer;
  z-index: 10;
  transition: all 0.15s ease;
}

.box-border {
  position: absolute;
  inset: 0;
  border: 1px solid transparent;
  border-radius: 2px;
  transition: all 0.15s ease;
}

.ocr-text-box:hover .box-border,
.ocr-text-box.is-hovered .box-border {
  border-color: var(--color-accent);
  background: var(--color-accent-light);
  box-shadow: 0 0 0 2px var(--color-accent-light);
}

.ocr-text-box.is-selected .box-border {
  border-color: var(--color-success);
  background: var(--color-success-light);
  box-shadow: 0 0 0 2px var(--color-success-light);
}

/* 文字预览 */
.text-preview {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 4px;
  padding: 4px 8px;
  background: var(--color-bg-overlay);
  border-radius: 4px;
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: var(--shadow-md);
  pointer-events: none;
}

.preview-text {
  color: var(--color-text-primary);
  font-size: 12px;
  font-family: 'Microsoft YaHei', sans-serif;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-confidence {
  color: var(--color-text-secondary);
  font-size: 10px;
  font-family: 'Consolas', monospace;
}
</style>
