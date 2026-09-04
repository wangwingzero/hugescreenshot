<template>
  <button
    type="button"
    role="switch"
    class="toggle-switch"
    :class="{ 'is-on': modelValue, 'is-disabled': disabled }"
    :aria-checked="modelValue"
    :aria-label="ariaLabel"
    :aria-disabled="disabled"
    :disabled="disabled"
    :tabindex="disabled ? -1 : 0"
    @click="handleToggle"
    @keydown.space.prevent="handleToggle"
    @keydown.enter.prevent="handleToggle"
  >
    <span class="toggle-track">
      <span class="toggle-thumb"></span>
    </span>
  </button>
</template>

<script setup lang="ts">
/**
 * ToggleSwitch - Boolean toggle control
 *
 * Provides a styled toggle switch with:
 * - On/off states with immediate visual feedback
 * - Dark theme styling using CSS variables
 * - Full accessibility support (ARIA attributes, keyboard navigation)
 * - Smooth transition animations
 *
 * @validates Requirements 7.3
 */

interface Props {
  /** Current toggle state (v-model) */
  modelValue: boolean
  /** Accessible label for screen readers */
  ariaLabel?: string
  /** Whether the toggle is disabled */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ariaLabel: 'Toggle',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

/**
 * Handle toggle action (click or keyboard)
 * Immediately emits the new state for instant feedback
 */
function handleToggle() {
  if (props.disabled) return
  emit('update:modelValue', !props.modelValue)
}
</script>

<style scoped>
.toggle-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 12px;
  background: transparent;
  cursor: pointer;
  outline: none;
  -webkit-tap-highlight-color: transparent;
  transition: opacity 0.15s ease;
}

.toggle-switch:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: 2px;
}

.toggle-switch.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-track {
  position: relative;
  width: 100%;
  height: 100%;
  background: var(--bg-hover);
  border-radius: 12px;
  transition: background-color 0.2s ease;
}

.toggle-switch.is-on .toggle-track {
  background: var(--accent-primary);
}

.toggle-switch:hover:not(.is-disabled) .toggle-track {
  background: var(--color-surface-active);
}

.toggle-switch.is-on:hover:not(.is-disabled) .toggle-track {
  background: var(--accent-hover, #5a9cf5);
}

.toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background: white;
  border-radius: 50%;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s ease;
}

.toggle-switch.is-on .toggle-thumb {
  transform: translateX(20px);
}

.toggle-switch:active:not(.is-disabled) .toggle-thumb {
  transform: scale(0.95);
}

.toggle-switch.is-on:active:not(.is-disabled) .toggle-thumb {
  transform: translateX(20px) scale(0.95);
}
</style>
