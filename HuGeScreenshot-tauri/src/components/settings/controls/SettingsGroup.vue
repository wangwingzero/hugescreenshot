<template>
  <div class="settings-group">
    <div class="group-header">
      <h3 class="group-title">{{ title }}</h3>
      <p v-if="description" class="group-description">{{ description }}</p>
    </div>
    <div class="group-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SettingsGroup - Card-style container for grouping related settings
 *
 * Provides a visually distinct container with:
 * - Title with clear visual hierarchy
 * - Optional description in muted text
 * - Dark theme styling with proper spacing
 * - Card-style appearance with rounded corners and subtle border
 *
 * @validates Requirements 12.1, 12.2
 */

interface Props {
  /** Group title - displayed prominently at the top */
  title: string
  /** Optional description - displayed in muted text below title */
  description?: string
}

defineProps<Props>()
</script>

<style scoped>
.settings-group {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  margin-bottom: var(--group-gap, 24px);
  overflow: hidden;
}

.group-header {
  padding: var(--content-padding, 24px);
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.group-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.group-description {
  margin: 8px 0 0 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

.group-content {
  padding: var(--content-padding, 24px);
  padding-top: 16px;
}

/* Ensure proper spacing for nested setting items */
.group-content :deep(> *:last-child) {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}
</style>
