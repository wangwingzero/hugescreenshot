<template>
  <div class="pin-image-section">
    <SettingsGroup :title="$t('settings.pinImage.title')">
      <!-- Default Opacity Slider -->
      <SettingItem
        :label="$t('settings.pinImage.defaultOpacity')"
        :help-text="$t('settings.pinImage.defaultOpacityHelp')"
      >
        <SliderControl
          :model-value="pinImageConfig.defaultOpacity"
          :min="0.1"
          :max="1.0"
          :step="0.1"
          suffix="%"
          @update:model-value="handleOpacityChange"
        />
      </SettingItem>

      <!-- Mouse Through Toggle -->
      <SettingItem
        :label="$t('settings.pinImage.mouseThrough')"
        :help-text="$t('settings.pinImage.mouseThroughHelp')"
      >
        <ToggleSwitch
          :model-value="pinImageConfig.mouseThrough"
          :aria-label="$t('settings.pinImage.mouseThrough')"
          @update:model-value="handleMouseThroughChange"
        />
      </SettingItem>

      <!-- Remember Position Toggle -->
      <SettingItem
        :label="$t('settings.pinImage.rememberPosition')"
        :help-text="$t('settings.pinImage.rememberPositionHelp')"
      >
        <ToggleSwitch
          :model-value="pinImageConfig.rememberPosition"
          :aria-label="$t('settings.pinImage.rememberPosition')"
          @update:model-value="handleRememberPositionChange"
        />
      </SettingItem>
    </SettingsGroup>
  </div>
</template>

<script setup lang="ts">
/**
 * PinImageSection - Pin Image (贴图) Settings Section
 *
 * Provides configuration options for pinned screenshot behavior:
 * - Default opacity slider (0.1-1.0, displayed as percentage)
 * - Mouse-through toggle (allows clicks to pass through the pinned image)
 * - Remember position toggle (saves window position between sessions)
 *
 * Uses the reusable settings control components:
 * - SettingsGroup for card-style grouping
 * - SettingItem for consistent row layout
 * - SliderControl for opacity with value clamping
 * - ToggleSwitch for boolean settings
 *
 * @validates Requirements 3.1, 3.2, 3.3, 3.4, 3.5
 */

import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import SettingsGroup from '@/components/settings/controls/SettingsGroup.vue'
import SettingItem from '@/components/settings/controls/SettingItem.vue'
import SliderControl from '@/components/settings/controls/SliderControl.vue'
import ToggleSwitch from '@/components/settings/controls/ToggleSwitch.vue'

// ============================================
// Store
// ============================================

const settingsStore = useSettingsStore()

// ============================================
// Computed
// ============================================

/**
 * Pin image configuration from store
 * Provides reactive access to current settings
 */
const pinImageConfig = computed(() => settingsStore.pinImage)

// ============================================
// Event Handlers
// ============================================

/**
 * Handle opacity slider change
 * Updates the store with the new opacity value
 * The SliderControl already clamps the value to [0.1, 1.0]
 *
 * @param value - New opacity value (0.1-1.0)
 * @validates Requirements 3.2, 3.5
 */
function handleOpacityChange(value: number): void {
  settingsStore.updatePinImage({ defaultOpacity: value })
}

/**
 * Handle mouse-through toggle change
 * When enabled, mouse clicks pass through the pinned image
 *
 * @param value - New mouse-through state
 * @validates Requirements 3.3
 */
function handleMouseThroughChange(value: boolean): void {
  settingsStore.updatePinImage({ mouseThrough: value })
}

/**
 * Handle remember position toggle change
 * When enabled, the pinned image window position is saved
 *
 * @param value - New remember position state
 * @validates Requirements 3.4
 */
function handleRememberPositionChange(value: boolean): void {
  settingsStore.updatePinImage({ rememberPosition: value })
}
</script>

<style scoped>
.pin-image-section {
  /* Section container - inherits dark theme from parent */
}
</style>
