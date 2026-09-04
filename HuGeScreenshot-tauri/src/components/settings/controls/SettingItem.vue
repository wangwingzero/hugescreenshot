<template>
  <div class="setting-item">
    <div class="item-label-area">
      <div class="label-row">
        <span class="item-label">{{ label }}</span>
        <span v-if="helpText" class="help-icon" :title="helpText">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <path d="M12 17h.01" />
          </svg>
        </span>
      </div>
      <p v-if="helpText && showHelpBelow" class="help-text">{{ helpText }}</p>
    </div>
    <div class="item-control">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SettingItem - Single setting row with label and control slot
 *
 * Provides a consistent row layout for individual settings:
 * - Label on the left side
 * - Control (toggle, slider, input, etc.) on the right side via slot
 * - Optional help text displayed as tooltip or small text below label
 * - Border separator between items (except last item)
 * - Dark theme styling using CSS variables
 *
 * @validates Requirements 12.2, 12.5
 */

interface Props {
  /** Setting label - displayed on the left side */
  label: string
  /** Optional help text - displayed as tooltip on hover icon */
  helpText?: string
  /** Show help text below label instead of just tooltip (default: false) */
  showHelpBelow?: boolean
}

withDefaults(defineProps<Props>(), {
  helpText: '',
  showHelpBelow: false,
})
</script>

<style scoped>
.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--item-height, 40px);
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);
  gap: 16px;
}

/* Remove border from last item */
.setting-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

/* First item doesn't need top padding */
.setting-item:first-child {
  padding-top: 0;
}

.item-label-area {
  flex: 1;
  min-width: 0;
}

.label-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.item-label {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 1.4;
}

.help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  cursor: help;
  transition: color 0.15s ease;
}

.help-icon:hover {
  color: var(--text-secondary);
}

.help-text {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.item-control {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

/* Ensure controls have consistent minimum width */
.item-control :deep(input),
.item-control :deep(select) {
  min-width: 120px;
}

/* Ensure toggle switches don't shrink */
.item-control :deep(.toggle-switch) {
  flex-shrink: 0;
}
</style>
