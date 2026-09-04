<template>
  <nav class="settings-sidebar" role="navigation" aria-label="Settings navigation">
    <div class="sidebar-content">
      <template v-for="group in settingsGroups" :key="group.id">
        <!-- Group Header -->
        <div class="group-header">
          {{ t(group.headerKey) }}
        </div>
        
        <!-- Menu Items -->
        <ul class="menu-list" role="menu">
          <li
            v-for="item in group.items"
            :key="item.id"
            role="menuitem"
          >
            <button
              class="menu-item"
              :class="{ active: modelValue === item.id }"
              :aria-current="modelValue === item.id ? 'page' : undefined"
              @click="handleItemClick(item.id)"
            >
              <component
                :is="icons[item.icon]"
                class="menu-icon"
                :size="18"
                :stroke-width="1.5"
              />
              <span class="menu-label">{{ t(item.labelKey) }}</span>
            </button>
          </li>
        </ul>
      </template>
    </div>
  </nav>
</template>

<script setup lang="ts">
/**
 * SettingsSidebar - Grouped sidebar navigation for settings panel
 *
 * Features:
 * - Grouped navigation with section headers
 * - Lucide icons for each menu item
 * - Active state highlighting with accent color
 * - i18n support for all text
 * - Keyboard accessible
 * - Dark theme styling
 *
 * @validates Requirements 1.1, 1.3, 1.4
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { icons, type IconName } from '@/components/icons'

/** Settings menu item definition */
interface SettingsMenuItem {
  id: string
  icon: IconName
  labelKey: string
}

/** Settings group with header and items */
interface SettingsGroup {
  id: string
  headerKey: string
  items: SettingsMenuItem[]
}

interface Props {
  /** Currently active category ID */
  modelValue: string
}

interface Emits {
  /** Emitted when a category is clicked */
  (e: 'update:modelValue', value: string): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()

/**
 * Settings groups configuration
 *
 * Groups are organized by functionality:
 * - 基础设置 (Basic): General, Hotkeys, Screenshot
 * - 功能设置 (Features): Pin Image, Recording
 * - 系统设置 (System): Notification, Update, Account, About
 *
 * Using computed to ensure i18n reactivity when locale changes
 */
const settingsGroups = computed<SettingsGroup[]>(() => [
  {
    id: 'basic',
    headerKey: 'settings.group.basic',
    items: [
      { id: 'general', icon: 'settings', labelKey: 'settings.general' },
      { id: 'hotkeys', icon: 'keyboard', labelKey: 'settings.hotkeys' },
      { id: 'screenshot', icon: 'camera', labelKey: 'settings.screenshot' },
      { id: 'ocr', icon: 'scan-text', labelKey: 'settings.ocr' },
    ]
  },
  {
    id: 'features',
    headerKey: 'settings.group.features',
    items: [
      { id: 'pinImage', icon: 'pin', labelKey: 'settings.pinImage.title' },
      { id: 'recording', icon: 'video', labelKey: 'settings.recording' },
    ]
  },
  {
    id: 'system',
    headerKey: 'settings.group.system',
    items: [
      { id: 'notification', icon: 'bell', labelKey: 'settings.notification.title' },
      { id: 'about', icon: 'info', labelKey: 'settings.about.title' },
    ]
  },
])

/**
 * Handle menu item click
 * Emits update:modelValue for v-model support
 */
function handleItemClick(categoryId: string): void {
  emit('update:modelValue', categoryId)
}
</script>

<style scoped>
.settings-sidebar {
  width: var(--sidebar-width, 200px);
  min-width: var(--sidebar-width, 200px);
  height: 100%;
  background: var(--bg-primary);
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-content {
  padding: 16px 0;
}

/* Group Header */
.group-header {
  padding: 8px 16px;
  margin-top: 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  user-select: none;
}

/* First group doesn't need top margin */
.group-header:first-child {
  margin-top: 0;
}

/* Menu List */
.menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

/* Menu Item Button */
.menu-item {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 400;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.1s ease, color 0.1s ease;
  gap: 10px;
}

/* Hover state - immediate feedback within 16ms */
.menu-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* Focus state for keyboard navigation */
.menu-item:focus {
  outline: none;
  background: var(--bg-hover);
  color: var(--text-primary);
}

.menu-item:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: -2px;
}

/* Active state */
.menu-item.active {
  background: var(--bg-active);
  color: var(--accent-primary);
}

.menu-item.active:hover {
  background: var(--bg-active);
}

/* Menu Icon - uses currentColor for consistent coloring */
.menu-icon {
  flex-shrink: 0;
  color: currentColor;
}

/* Menu Label */
.menu-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Scrollbar styling */
.settings-sidebar::-webkit-scrollbar {
  width: 6px;
}

.settings-sidebar::-webkit-scrollbar-track {
  background: transparent;
}

.settings-sidebar::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.settings-sidebar::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}
</style>
