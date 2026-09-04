<template>
  <div class="ocr-section">
    <SettingsGroup
      :title="$t('settings.ocr')"
      :description="$t('settings.ocrEngineHelp')"
    >
      <SettingItem
        :label="$t('settings.ocrEngine')"
        :help-text="$t('settings.ocrEngineHelp')"
        show-help-below
      >
        <select
          :value="ocrConfig.engine"
          class="setting-select"
          @change="handleEngineChange"
        >
          <option value="local">{{ $t('settings.ocrEngineLocal') }}</option>
          <option value="baiduAccurate">{{ $t('settings.ocrEngineBaiduAccurate') }}</option>
        </select>
      </SettingItem>

      <SettingItem :label="$t('settings.defaultLanguage')">
        <select
          :value="ocrConfig.defaultLanguage"
          class="setting-select"
          @change="handleLanguageChange"
        >
          <option value="auto">Auto</option>
          <option value="ch">中文</option>
          <option value="en">English</option>
          <option value="japan">日本語</option>
          <option value="korean">한국어</option>
        </select>
      </SettingItem>

      <SettingItem :label="$t('settings.autoTranslate')">
        <ToggleSwitch
          :model-value="ocrConfig.autoTranslate"
          :aria-label="$t('settings.autoTranslate')"
          @update:model-value="handleAutoTranslateChange"
        />
      </SettingItem>

      <SettingItem :label="$t('settings.translateProvider')">
        <select
          :value="ocrConfig.translateProvider"
          class="setting-select"
          @change="handleTranslateProviderChange"
        >
          <option value="google">Google</option>
          <option value="deepl">DeepL</option>
          <option value="baidu">百度</option>
        </select>
      </SettingItem>

      <SettingItem :label="$t('settings.translateTargetLang')">
        <select
          :value="ocrConfig.translateTargetLang"
          class="setting-select"
          @change="handleTranslateTargetChange"
        >
          <option value="zh">中文</option>
          <option value="en">English</option>
          <option value="ja">日本語</option>
          <option value="ko">한국어</option>
        </select>
      </SettingItem>
    </SettingsGroup>

    <SettingsGroup
      :title="$t('settings.baiduOcrTitle')"
      :description="$t('settings.baiduOcrHelp')"
    >
      <SettingItem
        :label="$t('settings.baiduApiKey')"
        :help-text="$t('settings.baiduOcrHelp')"
        show-help-below
      >
        <input
          :value="ocrConfig.baiduApiKey"
          type="password"
          class="setting-input secret-input"
          autocomplete="off"
          spellcheck="false"
          placeholder="API Key"
          @change="handleBaiduApiKeyChange"
        />
      </SettingItem>

      <SettingItem :label="$t('settings.baiduSecretKey')">
        <input
          :value="ocrConfig.baiduSecretKey"
          type="password"
          class="setting-input secret-input"
          autocomplete="off"
          spellcheck="false"
          placeholder="Secret Key"
          @change="handleBaiduSecretKeyChange"
        />
      </SettingItem>

      <SettingItem :label="$t('settings.baiduDetectDirection')">
        <ToggleSwitch
          :model-value="ocrConfig.baiduDetectDirection"
          :aria-label="$t('settings.baiduDetectDirection')"
          @update:model-value="handleBaiduDetectDirectionChange"
        />
      </SettingItem>

      <SettingItem :label="$t('settings.baiduProbability')">
        <ToggleSwitch
          :model-value="ocrConfig.baiduProbability"
          :aria-label="$t('settings.baiduProbability')"
          @update:model-value="handleBaiduProbabilityChange"
        />
      </SettingItem>
    </SettingsGroup>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { OcrEngine, TranslateProvider } from '@/types'
import SettingsGroup from '@/components/settings/controls/SettingsGroup.vue'
import SettingItem from '@/components/settings/controls/SettingItem.vue'
import ToggleSwitch from '@/components/settings/controls/ToggleSwitch.vue'

const settingsStore = useSettingsStore()
const ocrConfig = computed(() => settingsStore.ocr)

function eventValue(event: Event): string {
  return (event.target as HTMLInputElement | HTMLSelectElement).value
}

function handleEngineChange(event: Event): void {
  settingsStore.updateOcr({ engine: eventValue(event) as OcrEngine })
}

function handleLanguageChange(event: Event): void {
  settingsStore.updateOcr({ defaultLanguage: eventValue(event) })
}

function handleAutoTranslateChange(value: boolean): void {
  settingsStore.updateOcr({ autoTranslate: value })
}

function handleTranslateProviderChange(event: Event): void {
  settingsStore.updateOcr({ translateProvider: eventValue(event) as TranslateProvider })
}

function handleTranslateTargetChange(event: Event): void {
  settingsStore.updateOcr({ translateTargetLang: eventValue(event) })
}

function handleBaiduApiKeyChange(event: Event): void {
  settingsStore.updateOcr({ baiduApiKey: eventValue(event).trim() })
}

function handleBaiduSecretKeyChange(event: Event): void {
  settingsStore.updateOcr({ baiduSecretKey: eventValue(event).trim() })
}

function handleBaiduDetectDirectionChange(value: boolean): void {
  settingsStore.updateOcr({ baiduDetectDirection: value })
}

function handleBaiduProbabilityChange(value: boolean): void {
  settingsStore.updateOcr({ baiduProbability: value })
}
</script>

<style scoped>
.ocr-section {
  max-width: 640px;
}

.setting-select,
.setting-input {
  min-width: 180px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-input-bg);
  color: var(--text-primary);
  font-size: 12px;
}

.setting-select:focus,
.setting-input:focus {
  outline: none;
  border-color: var(--color-border-focus);
}

.secret-input {
  width: 260px;
}
</style>
