<template>
  <div class="parameter-slider" :class="{ disabled: disabled }">
    <label class="slider-label">{{ label }}</label>
    <div class="slider-container">
      <input
        type="range"
        class="slider-input"
        :value="internalValue"
        :min="min"
        :max="max"
        :step="step"
        :disabled="disabled"
        @input="handleSliderInput"
      />
      <input
        type="number"
        class="number-input"
        :value="displayNumber"
        :min="min"
        :max="max"
        :step="step"
        :disabled="disabled"
        @input="handleNumberInput"
        @blur="handleNumberBlur"
      />
      <span v-if="suffix" class="value-suffix">{{ suffix }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ParameterSlider - 参数滑块组件
 *
 * 包含：标签 + 滑块 + 数值输入框
 * 支持整数和浮点数两种模式，滑块与输入框双向同步。
 *
 * 特性：
 * - 滑块拖动时实时更新数值框
 * - 数值框输入时实时更新滑块
 * - 支持自定义后缀 (px, %, ms, x)
 * - 支持禁用状态
 * - 输入值自动 clamp 到有效范围
 *
 * @validates Requirements 2.4, 2.5, 5.1-5.7
 */
import { computed, ref, watch } from 'vue'

interface Props {
  /** 当前值 (v-model) */
  modelValue: number
  /** 参数标签 */
  label: string
  /** 最小值 */
  min: number
  /** 最大值 */
  max: number
  /** 步进值 (默认: 1) */
  step?: number
  /** 后缀单位 (如 "px", "%", "ms") */
  suffix?: string
  /** 小数位数 (默认: 0 表示整数) */
  decimals?: number
  /** 禁用状态 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  step: 1,
  suffix: '',
  decimals: 0,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
  /** 值变化事件 - 用于即时反馈 */
  (e: 'change', value: number): void
}>()

// 内部值，用于平滑处理输入（防御性：undefined 时使用 min 作为默认值）
const internalValue = ref(props.modelValue ?? props.min)

// 监听外部值变化
watch(
  () => props.modelValue,
  (newValue) => {
    internalValue.value = newValue ?? props.min
  }
)

/**
 * Clamp 值到有效范围
 */
function clampValue(value: number): number {
  if (Number.isNaN(value)) return props.min
  if (value < props.min) return props.min
  if (value > props.max) return props.max
  return value
}

/**
 * 格式化数值显示（防御性：处理 undefined/NaN）
 */
const displayNumber = computed(() => {
  const value = internalValue.value ?? props.min
  if (Number.isNaN(value)) return props.min.toString()
  if (props.decimals > 0) {
    return value.toFixed(props.decimals)
  }
  return Math.round(value).toString()
})

/**
 * 处理滑块输入 - 实时更新
 */
function handleSliderInput(event: Event) {
  const target = event.target as HTMLInputElement
  const rawValue = parseFloat(target.value)
  const clampedValue = clampValue(rawValue)
  internalValue.value = clampedValue
  emit('update:modelValue', clampedValue)
  emit('change', clampedValue)
}

/**
 * 处理数值输入 - 实时更新
 */
function handleNumberInput(event: Event) {
  const target = event.target as HTMLInputElement
  const rawValue = parseFloat(target.value)
  if (!Number.isNaN(rawValue)) {
    const clampedValue = clampValue(rawValue)
    internalValue.value = clampedValue
    emit('update:modelValue', clampedValue)
    emit('change', clampedValue)
  }
}

/**
 * 处理数值框失焦 - 确保值有效
 */
function handleNumberBlur(event: Event) {
  const target = event.target as HTMLInputElement
  const rawValue = parseFloat(target.value)
  const clampedValue = clampValue(rawValue)
  internalValue.value = clampedValue
  emit('update:modelValue', clampedValue)
}
</script>

<style scoped>
.parameter-slider {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.parameter-slider.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.slider-label {
  min-width: 60px;
  font-size: 13px;
  color: var(--text-secondary);
}

.slider-container {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-input {
  flex: 1;
  height: 4px;
  min-width: 100px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--border-color);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.slider-input::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  background: var(--accent-primary);
  border-radius: 50%;
  cursor: pointer;
  margin-top: -6px;
  transition: background 0.15s ease, transform 0.1s ease;
}

.slider-input::-webkit-slider-thumb:hover {
  background: var(--accent-hover, #5a9cf5);
  transform: scale(1.1);
}

.slider-input::-webkit-slider-thumb:active {
  transform: scale(0.95);
}

.slider-input::-moz-range-track {
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
  border: none;
}

.slider-input::-moz-range-thumb {
  width: 16px;
  height: 16px;
  background: var(--accent-primary);
  border-radius: 50%;
  border: none;
  cursor: pointer;
}

.number-input {
  width: 60px;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface-active);
  color: var(--text-primary);
  font-size: 12px;
  text-align: right;
  outline: none;
}

.number-input:focus {
  border-color: var(--accent-primary);
}

/* 隐藏数字输入框的箭头按钮 */
.number-input::-webkit-outer-spin-button,
.number-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.number-input[type='number'] {
  -moz-appearance: textfield;
}

.value-suffix {
  min-width: 24px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
