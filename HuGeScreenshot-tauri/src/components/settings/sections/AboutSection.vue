<template>
  <div class="about-section">
    <SettingsGroup :title="$t('settings.about.title')">
      <div class="app-header">
        <img
          :src="appLogoUrl"
          alt="虎哥截图"
          class="app-logo"
          @error="handleLogoError"
        />
        <div class="app-info">
          <h2 class="app-name">{{ appName }}</h2>
          <span class="app-version">{{ $t('settings.about.version', { version: appVersion }) }}</span>
        </div>
      </div>

      <p class="app-description">{{ $t('settings.about.description') }}</p>
    </SettingsGroup>

    <SettingsGroup :title="$t('settings.update.title')">
      <SettingItem
        :label="$t('settings.update.autoCheck')"
        :help-text="$t('settings.update.autoCheckHelp')"
      >
        <ToggleSwitch
          :model-value="updateConfig.autoCheck"
          :aria-label="$t('settings.update.autoCheck')"
          @update:model-value="handleAutoCheckChange"
        />
      </SettingItem>

      <SettingItem :label="$t('settings.update.checkNow')">
        <div class="check-now-wrapper">
          <button
            class="check-now-btn"
            :disabled="isBusy"
            @click="handlePrimaryAction"
          >
            {{ primaryActionText }}
          </button>
          <span v-if="statusMessage" class="check-result" :class="statusClass">
            {{ statusMessage }}
          </span>
        </div>
        <div
          v-if="showInlineProgress"
          class="inline-progress-track"
          :class="{ indeterminate: isIndeterminateProgress }"
        >
          <div
            class="inline-progress-bar"
            :style="{ width: isIndeterminateProgress ? '35%' : progressWidth }"
          ></div>
        </div>
      </SettingItem>

      <SettingItem
        v-if="updateConfig.lastCheckTime"
        :label="$t('settings.update.lastCheck')"
      >
        <span class="last-check-time">{{ formatLastCheckTime }}</span>
      </SettingItem>

      <SettingItem
        :label="$t('settings.update.manualDownload')"
        :help-text="$t('settings.update.manualDownloadHelp')"
      >
        <a
          class="manual-download-link"
          :href="DOWNLOAD_URL"
          @click.prevent="openManualDownloadUrl"
        >
          {{ downloadUrlLabel }}
        </a>
      </SettingItem>
    </SettingsGroup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getVersion } from '@tauri-apps/api/app'
import { open } from '@tauri-apps/plugin-shell'
import { useAutoUpdate } from '@/composables/useAutoUpdate'
import { useSettingsStore } from '@/stores/settings'
import { UPDATE_BASE_URL } from '@/constants/update'
import SettingsGroup from '@/components/settings/controls/SettingsGroup.vue'
import SettingItem from '@/components/settings/controls/SettingItem.vue'
import ToggleSwitch from '@/components/settings/controls/ToggleSwitch.vue'
import appLogoUrl from '@resources/PNG/虎哥截图.png'

const DOWNLOAD_URL = UPDATE_BASE_URL
const downloadUrlLabel = computed(() => DOWNLOAD_URL.replace(/^https?:\/\//, ''))
const appName = '虎哥截图'

const { t } = useI18n()
const appVersion = ref('...')

const settingsStore = useSettingsStore()
const manualActionError = ref('')
const {
  status: updateStatus,
  updateInfo,
  error: updateError,
  progress: updateProgress,
  totalBytes: updateTotalBytes,
  downloadProgressText,
  downloadDetailText,
  checkForUpdate,
  downloadAndInstall,
} = useAutoUpdate()

const updateConfig = computed(() => settingsStore.update)

onMounted(async () => {
  try {
    appVersion.value = await getVersion()
  } catch {
    appVersion.value = '0.0.0'
  }
})

const formatLastCheckTime = computed(() => {
  if (!updateConfig.value.lastCheckTime) return ''
  const date = new Date(updateConfig.value.lastCheckTime)
  if (isNaN(date.getTime())) return updateConfig.value.lastCheckTime
  return date.toLocaleString()
})

const isBusy = computed(() =>
  updateStatus.value === 'checking' ||
  updateStatus.value === 'downloading' ||
  updateStatus.value === 'installing',
)

const isDownloadAction = computed(() =>
  updateStatus.value === 'available' || (updateStatus.value === 'error' && !!updateInfo.value),
)

const primaryActionText = computed(() => {
  if (updateStatus.value === 'checking') return t('settings.update.checking')
  if (updateStatus.value === 'downloading') return `${t('update.downloadAndInstall')} ${downloadProgressText.value}`
  if (updateStatus.value === 'installing') return t('update.installing')
  if (isDownloadAction.value) return t('update.downloadAndInstall')
  return t('settings.update.checkNowBtn')
})

const statusMessage = computed(() => {
  if (manualActionError.value) return manualActionError.value
  if (updateStatus.value === 'available' && updateInfo.value) {
    return `${t('settings.update.statusAvailable')} ${updateInfo.value.version}`
  }
  if (updateStatus.value === 'upToDate') return t('settings.update.statusUpToDate')
  if (updateStatus.value === 'downloading' && updateInfo.value) {
    return `${updateInfo.value.version} · ${downloadDetailText.value}`
  }
  if (updateStatus.value === 'installing' && updateInfo.value) {
    return `${updateInfo.value.version} · ${t('update.installing')}`
  }
  if (updateStatus.value === 'error') {
    return updateError.value
      ? `${t('settings.update.statusError')}: ${updateError.value}`
      : t('settings.update.statusError')
  }
  return ''
})

const statusClass = computed(() => {
  if (manualActionError.value) return 'check-result-error'
  if (updateStatus.value === 'upToDate') return 'check-result-success'
  if (updateStatus.value === 'available' || updateStatus.value === 'downloading' || updateStatus.value === 'installing') {
    return 'check-result-update'
  }
  if (updateStatus.value === 'error') return 'check-result-error'
  return ''
})

const showInlineProgress = computed(() =>
  updateStatus.value === 'downloading' || updateStatus.value === 'installing',
)

const progressWidth = computed(() => {
  if (updateStatus.value === 'installing') return '100%'
  return `${Math.min(100, Math.max(0, updateProgress.value))}%`
})

const isIndeterminateProgress = computed(() =>
  updateStatus.value === 'downloading' && updateTotalBytes.value <= 0,
)

function handleLogoError(event: Event): void {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

function handleAutoCheckChange(value: boolean): void {
  settingsStore.updateUpdate({ autoCheck: value })
}

async function openManualDownloadUrl(): Promise<void> {
  try {
    manualActionError.value = ''
    await open(DOWNLOAD_URL)
  } catch {
    manualActionError.value = t('settings.update.openBrowserFailed')
  }
}

async function handlePrimaryAction(): Promise<void> {
  if (isBusy.value) return
  manualActionError.value = ''

  if (isDownloadAction.value) {
    await downloadAndInstall()
    return
  }

  try {
    await checkForUpdate()
    if (updateStatus.value !== 'error') {
      settingsStore.updateUpdate({ lastCheckTime: new Date().toISOString() })
    }
  } catch (error) {
    manualActionError.value = `${t('settings.update.statusError')}: ${
      error instanceof Error ? error.message : String(error)
    }`
  }
}
</script>

<style scoped>
.about-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.app-logo {
  width: 64px;
  height: 64px;
  border-radius: 12px;
}

.app-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.app-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.app-version {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.app-description {
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.check-now-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: var(--color-accent);
  color: var(--color-text-inverse);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.1s;
}

.check-now-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.check-now-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.check-now-wrapper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.check-result {
  font-size: 12px;
  animation: fadeIn 0.2s ease-in;
}

.check-result-success {
  color: var(--color-success);
}

.check-result-update {
  color: var(--color-accent);
  font-weight: 500;
}

.check-result-error {
  color: var(--color-error);
}

.inline-progress-track {
  margin-top: 10px;
  width: min(420px, 100%);
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
}

.inline-progress-bar {
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
  background: var(--color-accent);
  transition: width 0.2s ease;
}

.inline-progress-track.indeterminate .inline-progress-bar {
  animation: about-update-indeterminate 1.2s ease-in-out infinite;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes about-update-indeterminate {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

.last-check-time {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.manual-download-link {
  color: var(--color-accent);
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: opacity 0.1s;
}

.manual-download-link:hover {
  opacity: 0.8;
  text-decoration: underline;
}
</style>
