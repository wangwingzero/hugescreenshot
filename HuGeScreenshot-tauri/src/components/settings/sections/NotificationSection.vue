<template>
  <div class="notification-section">
    <SettingsGroup :title="$t('settings.notification.title')">
      <!-- Startup Notification -->
      <SettingItem
        :label="$t('settings.notification.startup')"
        :help-text="$t('settings.notification.startupHelp')"
      >
        <ToggleSwitch
          :model-value="notificationConfig.startup"
          :aria-label="$t('settings.notification.startup')"
          @update:model-value="handleStartupChange"
        />
      </SettingItem>

      <!-- Screenshot Save Notification -->
      <SettingItem
        :label="$t('settings.notification.screenshotSave')"
        :help-text="$t('settings.notification.screenshotSaveHelp')"
      >
        <ToggleSwitch
          :model-value="notificationConfig.screenshotSave"
          :aria-label="$t('settings.notification.screenshotSave')"
          @update:model-value="handleScreenshotSaveChange"
        />
      </SettingItem>

      <!-- Pin Image Notification -->
      <SettingItem
        :label="$t('settings.notification.pinImage')"
        :help-text="$t('settings.notification.pinImageHelp')"
      >
        <ToggleSwitch
          :model-value="notificationConfig.pinImage"
          :aria-label="$t('settings.notification.pinImage')"
          @update:model-value="handlePinImageChange"
        />
      </SettingItem>

      <!-- Recording Complete Notification -->
      <SettingItem
        :label="$t('settings.notification.recordingComplete')"
        :help-text="$t('settings.notification.recordingCompleteHelp')"
      >
        <ToggleSwitch
          :model-value="notificationConfig.recordingComplete"
          :aria-label="$t('settings.notification.recordingComplete')"
          @update:model-value="handleRecordingCompleteChange"
        />
      </SettingItem>

      <!-- Software Update Notification -->
      <SettingItem
        :label="$t('settings.notification.softwareUpdate')"
        :help-text="$t('settings.notification.softwareUpdateHelp')"
      >
        <ToggleSwitch
          :model-value="notificationConfig.softwareUpdate"
          :aria-label="$t('settings.notification.softwareUpdate')"
          @update:model-value="handleSoftwareUpdateChange"
        />
      </SettingItem>
    </SettingsGroup>
  </div>
</template>

<script setup lang="ts">
/**
 * NotificationSection - Notification Settings Section
 *
 * Provides configuration options for system notifications:
 * - Startup notification toggle
 * - Screenshot save notification toggle
 * - Pin image notification toggle
 * - Recording complete notification toggle
 * - Software update notification toggle
 *
 * Uses the reusable settings control components:
 * - SettingsGroup for card-style grouping
 * - SettingItem for consistent row layout
 * - ToggleSwitch for boolean settings
 *
 * @validates Requirements 7.1, 7.2, 7.3, 7.4
 */

import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import SettingsGroup from '@/components/settings/controls/SettingsGroup.vue'
import SettingItem from '@/components/settings/controls/SettingItem.vue'
import ToggleSwitch from '@/components/settings/controls/ToggleSwitch.vue'

// ============================================
// Store
// ============================================

const settingsStore = useSettingsStore()

// ============================================
// Computed
// ============================================

/**
 * Notification configuration from store
 * Provides reactive access to current settings
 */
const notificationConfig = computed(() => settingsStore.notification)

// ============================================
// Event Handlers
// ============================================

/**
 * Handle startup notification toggle change
 * @param value - New startup notification state
 * @validates Requirements 7.1
 */
function handleStartupChange(value: boolean): void {
  settingsStore.updateNotification({ startup: value })
}

/**
 * Handle screenshot save notification toggle change
 * @param value - New screenshot save notification state
 * @validates Requirements 7.2
 */
function handleScreenshotSaveChange(value: boolean): void {
  settingsStore.updateNotification({ screenshotSave: value })
}

/**
 * Handle pin image notification toggle change
 * @param value - New pin image notification state
 */
function handlePinImageChange(value: boolean): void {
  settingsStore.updateNotification({ pinImage: value })
}

/**
 * Handle recording complete notification toggle change
 * @param value - New recording complete notification state
 */
function handleRecordingCompleteChange(value: boolean): void {
  settingsStore.updateNotification({ recordingComplete: value })
}

/**
 * Handle software update notification toggle change
 * @param value - New software update notification state
 */
function handleSoftwareUpdateChange(value: boolean): void {
  settingsStore.updateNotification({ softwareUpdate: value })
}
</script>

<style scoped>
.notification-section {
  /* Section container - inherits dark theme from parent */
}
</style>
