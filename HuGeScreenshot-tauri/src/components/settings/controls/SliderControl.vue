<template>
  <div class="slider-control">
    <input
      type="range"
      class="slider-input"
      :value="modelValue"
      :min="min"
      :max="max"
      :step="step"
      @input="handleInput"
    />
    <span class="slider-value">{{ displayValue }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * SliderControl - Range slider with value display
 *
 * Provides a styled range input with:
 * - Configurable min, max, step values
 * - Value display with optional suffix (e.g., "%" or "px")
 * - Value clamping to ensure output is always within [min, max] range
 * - Dark theme styling using CSS variables
 * - Immediate visual feedback on drag
 *
 * Value Clamping Logic:
 * - If input < min, clamp to min
 * - If input > max, clamp to max
 * - Otherwise, use input value
 *
 * @validates Requirements 3.2, 4.4, 4.5, 5.4, 8.3
 */
import { computed } from 'vue'

interface Props {
  /** Current value (v-model) */
  modelValue: number
  /** Minimum value */
  min: number
  /** Maximum value */
  max: number
  /** Step increment (default: 1) */
  step?: number
  /** Optional suffix for display (e.g., "%" or "px") */
  suffix?: string
}

const props = withDefaults(defineProps<Props>(), {
  step: 1,
  suffix: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

/**
 * Clamp a value to the [min, max] range
 * - If value < min, return min
 * - If value > max, return max
 * - Otherwise, return value
 */
function clampValue(value: number): number {
  if (value < props.min) return props.min
  if (value > props.max) return props.max
  return value
}

/**
 * Handle input event from range slider
 * Parses the value and emits clamped result
 */
function handleInput(event: Event) {
  const target = event.target as HTMLInputElement
  const rawValue = parseFloat(target.value)
  const clampedValue = clampValue(rawValue)
  emit('update:modelValue', clampedValue)
}

/**
 * Computed display value with optional suffix
 */
const displayValue = computed(() => {
  const value = props.modelValue
  // Format number: if step is less than 1, show decimal places
  const formattedValue = props.step < 1 ? value.toFixed(1) : value.toString()
  return props.suffix ? `${formattedValue}${props.suffix}` : formattedValue
})
</script>

<style scoped>
.slider-control {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 160px;
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
  transition: background 0.15s ease;
}

/* Track styling for WebKit browsers (Chrome, Safari, Edge) */
.slider-input::-webkit-slider-runnable-track {
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
}

/* Thumb styling for WebKit browsers */
.slider-input::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  background: var(--accent-primary);
  border-radius: 50%;
  border: none;
  cursor: pointer;
  margin-top: -6px;
  transition: background 0.15s ease, transform 0.15s ease;
}

.slider-input::-webkit-slider-thumb:hover {
  background: var(--accent-hover, #5a9cf5);
  transform: scale(1.1);
}

.slider-input::-webkit-slider-thumb:active {
  transform: scale(0.95);
}

/* Track styling for Firefox */
.slider-input::-moz-range-track {
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
  border: none;
}

/* Thumb styling for Firefox */
.slider-input::-moz-range-thumb {
  width: 16px;
  height: 16px;
  background: var(--accent-primary);
  border-radius: 50%;
  border: none;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.15s ease;
}

.slider-input::-moz-range-thumb:hover {
  background: var(--accent-hover, #5a9cf5);
}

/* Focus state */
.slider-input:focus {
  outline: none;
}

.slider-input:focus::-webkit-slider-thumb {
  box-shadow: 0 0 0 3px var(--color-accent-light);
}

.slider-input:focus::-moz-range-thumb {
  box-shadow: 0 0 0 3px var(--color-accent-light);
}

.slider-value {
  min-width: 48px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
