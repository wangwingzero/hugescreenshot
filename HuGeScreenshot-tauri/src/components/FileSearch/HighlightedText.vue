<template>
  <span class="highlighted-text">
    <template v-for="(segment, index) in segments" :key="index">
      <mark v-if="segment.isMatch" class="highlight">{{ segment.text }}</mark>
      <span v-else>{{ segment.text }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
/**
 * 高亮文本组件
 *
 * 根据匹配索引高亮显示文本中的匹配部分
 *
 * @validates Requirements 6.4
 */

import { computed } from 'vue'

// ============================================
// Props
// ============================================

interface Props {
  /** 原始文本 */
  text: string
  /** 匹配索引数组 [[start, end], ...] */
  matchIndices: [number, number][]
}

const props = defineProps<Props>()

// ============================================
// Types
// ============================================

interface TextSegment {
  text: string
  isMatch: boolean
}

// ============================================
// Computed
// ============================================

/**
 * 将文本分割为高亮和非高亮片段
 * @validates Requirements 6.4
 */
const segments = computed<TextSegment[]>(() => {
  const { text, matchIndices } = props

  if (!text || !matchIndices || matchIndices.length === 0) {
    return [{ text, isMatch: false }]
  }

  // 合并重叠的索引范围
  const mergedIndices = mergeOverlappingRanges(matchIndices)

  const result: TextSegment[] = []
  let lastEnd = 0

  for (const [start, end] of mergedIndices) {
    // 确保索引在有效范围内
    const safeStart = Math.max(0, Math.min(start, text.length))
    const safeEnd = Math.max(safeStart, Math.min(end, text.length))

    // 添加匹配前的非高亮文本
    if (safeStart > lastEnd) {
      result.push({
        text: text.slice(lastEnd, safeStart),
        isMatch: false,
      })
    }

    // 添加高亮文本
    if (safeEnd > safeStart) {
      result.push({
        text: text.slice(safeStart, safeEnd),
        isMatch: true,
      })
    }

    lastEnd = safeEnd
  }

  // 添加最后的非高亮文本
  if (lastEnd < text.length) {
    result.push({
      text: text.slice(lastEnd),
      isMatch: false,
    })
  }

  return result
})

// ============================================
// Helper Functions
// ============================================

/**
 * 合并重叠的索引范围
 */
function mergeOverlappingRanges(ranges: [number, number][]): [number, number][] {
  if (ranges.length === 0) return []

  // 按起始位置排序
  const sorted = [...ranges].sort((a, b) => a[0] - b[0])

  const merged: [number, number][] = [sorted[0]]

  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i]
    const last = merged[merged.length - 1]

    if (current[0] <= last[1]) {
      // 重叠或相邻，合并
      last[1] = Math.max(last[1], current[1])
    } else {
      // 不重叠，添加新范围
      merged.push(current)
    }
  }

  return merged
}
</script>

<style scoped>
.highlighted-text {
  display: inline;
}

.highlight {
  background-color: var(--color-warning-light);
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
  font-weight: 600;
}
</style>
