<template>
  <div class="settings-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <div class="header-title">
        <span class="title-text">{{ $t('settings.title') }}</span>
      </div>
      <div class="header-actions">
        <button
          class="action-btn reset-btn"
          :title="$t('settings.resetToDefault')"
          @click="showResetConfirm = true"
        >
          <span class="btn-icon">↺</span>
          <span class="btn-text">{{ $t('settings.resetToDefault') }}</span>
        </button>
      </div>
    </div>

    <!-- 主体区域：侧边栏 + 内容区 -->
    <div class="panel-body">
      <!-- 侧边栏导航 -->
      <SettingsSidebar v-model="activeCategory" />

      <!-- 设置内容区 -->
      <div class="settings-content">
        <!-- 通用设置 -->
        <div v-show="activeCategory === 'general'" class="settings-section">
          <h3 class="section-title">{{ $t('settings.general') }}</h3>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.language') }}</label>
            <select
              v-model="localConfig.general.language"
              class="setting-select"
              @change="handleLanguageChange"
            >
              <option v-for="locale in supportedLocales" :key="locale.code" :value="locale.code">
                {{ locale.nativeName }}
              </option>
            </select>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.theme') }}</label>
            <select
              v-model="localConfig.general.theme"
              class="setting-select"
              @change="handleGeneralChange"
            >
              <option value="system">{{ $t('settings.themeSystem') }}</option>
              <option value="light">{{ $t('settings.themeLight') }}</option>
              <option value="dark">{{ $t('settings.themeDark') }}</option>
            </select>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.autoStart') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.general.autoStart"
                type="checkbox"
                class="toggle-input"
                @change="handleAutoStartChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>

        </div>

        <!-- 热键设置 -->
        <div v-show="activeCategory === 'hotkeys'" class="settings-section">
          <h3 class="section-title">{{ $t('settings.hotkeys') }}</h3>

          <div class="setting-item">
            <label class="setting-label">{{ $t('screenshot.capture') }}</label>
            <HotkeyInput
              v-model="localConfig.hotkeys.screenshot"
              @change="handleHotkeyChange('screenshot', $event)"
            />
          </div>

          <div class="setting-item">
            <label class="setting-label">工作台</label>
            <HotkeyInput
              v-model="localConfig.hotkeys.workbench"
              @change="handleHotkeyChange('workbench', $event)"
            />
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.mouseHighlight.title') }}</label>
            <HotkeyInput
              v-model="localConfig.hotkeys.mouseHighlight"
              @change="handleHotkeyChange('mouseHighlight', $event)"
            />
          </div>
        </div>

        <!-- 截图设置 -->
        <div v-show="activeCategory === 'screenshot'" class="settings-section">
          <h3 class="section-title">{{ $t('settings.screenshot') }}</h3>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.saveLocation') }}</label>
            <div class="path-input">
              <input
                v-model="localConfig.screenshot.saveLocation"
                type="text"
                class="setting-text"
                :placeholder="$t('settings.browse')"
                readonly
              />
              <button class="browse-btn" @click="handleBrowseSaveLocation">
                {{ $t('settings.browse') }}
              </button>
            </div>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.includeMouseCursor') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.screenshot.includeMouseCursor"
                type="checkbox"
                class="toggle-input"
                @change="handleScreenshotChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.autoCopy') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.screenshot.autoCopy"
                type="checkbox"
                class="toggle-input"
                @change="handleScreenshotChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.autoSave') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.screenshot.autoSave"
                type="checkbox"
                class="toggle-input"
                @change="handleScreenshotChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>
        </div>

        <!-- OCR 设置 -->
        <div v-if="activeCategory === 'ocr'" class="settings-section">
          <OcrSection />
        </div>

        <!-- 录屏设置 -->
        <div v-show="activeCategory === 'recording'" class="settings-section">
          <h3 class="section-title">{{ $t('settings.recording') }}</h3>

          <div class="setting-item">
            <label class="setting-label">{{ $t('recording.outputDir') }}</label>
            <div class="path-input">
              <input
                v-model="localConfig.recording.outputDir"
                type="text"
                class="setting-text"
                :placeholder="$t('settings.browse')"
                readonly
              />
              <button class="browse-btn" @click="handleBrowseRecordingDir">
                {{ $t('settings.browse') }}
              </button>
            </div>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.defaultFps') }}</label>
            <select
              v-model.number="localConfig.recording.defaultFps"
              class="setting-select"
              @change="handleRecordingChange"
            >
              <option :value="15">15 FPS</option>
              <option :value="24">24 FPS</option>
              <option :value="30">30 FPS</option>
              <option :value="60">60 FPS</option>
            </select>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.systemAudioEnabled') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.recording.systemAudio"
                type="checkbox"
                class="toggle-input"
                @change="handleRecordingChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>

          <div class="setting-item">
            <label class="setting-label">{{ $t('settings.micAudioEnabled') }}</label>
            <div class="setting-toggle">
              <input
                v-model="localConfig.recording.micAudio"
                type="checkbox"
                class="toggle-input"
                @change="handleRecordingChange"
              />
              <span class="toggle-slider"></span>
            </div>
          </div>
        </div>

        <!-- 贴图设置 -->
        <div v-if="activeCategory === 'pinImage'" class="settings-section">
          <PinImageSection />
        </div>

        <!-- 通知设置 -->
        <div v-if="activeCategory === 'notification'" class="settings-section">
          <NotificationSection />
        </div>
        <!-- 关于 -->
        <div v-if="activeCategory === 'about'" class="settings-section">
          <AboutSection />
        </div>
      </div>
    </div>

    <!-- 底部状态栏 -->
    <div class="panel-footer">
      <span v-if="settingsStore.lastError" class="error-text">
        {{ settingsStore.lastError }}
      </span>
      <span v-else-if="settingsStore.isSaving" class="saving-text">
        {{ $t('settings.saving') }}
      </span>
      <span v-else class="status-text">
        {{ $t('settings.saved') }}
      </span>
    </div>

    <!-- 重置确认对话框 -->
    <div v-if="showResetConfirm" class="modal-overlay" @click.self="showResetConfirm = false">
      <div class="modal-dialog">
        <div class="modal-header">
          <span class="modal-title">{{ $t('common.confirm') }}</span>
        </div>
        <div class="modal-body">
          {{ $t('settings.resetConfirm') }}
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel-btn" @click="showResetConfirm = false">
            {{ $t('common.cancel') }}
          </button>
          <button class="modal-btn confirm-btn" @click="handleReset">
            {{ $t('common.reset') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 操作反馈提示 -->
    <Transition name="toast">
      <div v-if="settingsToast.visible" :class="['settings-toast', settingsToast.type]">
        {{ settingsToast.message }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
/**
 * 设置面板组件 - 侧边栏布局版本
 *
 * 提供应用配置管理界面：
 * - 左侧：分组侧边栏导航 (SettingsSidebar)
 * - 右侧：动态内容区域
 *
 * 支持的设置类别：
 * - 基础设置：通用、热键、截图
 * - 功能设置：贴图、录屏
 * - 系统设置：通知、更新、关于
 *
 * @validates Requirements 1.1, 1.2, 17.1, 17.2, 17.5, 17.6
 */

import { ref, reactive, onMounted, watch } from 'vue'
import { open } from '@tauri-apps/plugin-dialog'
import { useSettingsStore } from '@/stores/settings'
import { useTheme } from '@/composables/useTheme'
import { useLocale } from '@/composables/useLocale'
import type { AppConfig } from '@/types'
import { DEFAULT_CONFIG } from '@/types'
import HotkeyInput from './HotkeyInput.vue'
import SettingsSidebar from './SettingsSidebar.vue'
import OcrSection from './sections/OcrSection.vue'
import PinImageSection from './sections/PinImageSection.vue'
import NotificationSection from './sections/NotificationSection.vue'
import AboutSection from './sections/AboutSection.vue'

// ============================================
// Store & Composables
// ============================================

const settingsStore = useSettingsStore()
const { setTheme } = useTheme()
const { supportedLocales, changeLocale } = useLocale()

const props = withDefaults(defineProps<{
  initialCategory?: string
}>(), {
  initialCategory: 'general',
})

// ============================================
// State
// ============================================

/** 当前激活的设置类别 - 默认为 'general' */
const validSettingsCategories = new Set([
  'general',
  'hotkeys',
  'screenshot',
  'ocr',
  'recording',
  'pinImage',
  'notification',
  'about',
])

function normalizeSettingsCategory(category: string): string {
  return validSettingsCategories.has(category) ? category : 'general'
}

const activeCategory = ref(normalizeSettingsCategory(props.initialCategory))

/** 本地配置副本 */
const localConfig = reactive<AppConfig>(JSON.parse(JSON.stringify(DEFAULT_CONFIG)))

/** 显示重置确认对话框 */
const showResetConfirm = ref(false)

/** 设置操作反馈 toast */
const settingsToast = reactive({
  visible: false,
  message: '',
  type: 'error' as 'success' | 'error',
})
let settingsToastTimer: ReturnType<typeof setTimeout> | null = null

function showSettingsToast(message: string, type: 'success' | 'error' = 'error'): void {
  if (settingsToastTimer) clearTimeout(settingsToastTimer)
  settingsToast.message = message
  settingsToast.type = type
  settingsToast.visible = true
  settingsToastTimer = setTimeout(() => {
    settingsToast.visible = false
  }, 3000)
}

// ============================================
// Lifecycle
// ============================================

onMounted(async () => {
  await loadSettings()
})

// 监听 store 配置变化，同步到本地
watch(
  () => settingsStore.config,
  (newConfig) => {
    Object.assign(localConfig, JSON.parse(JSON.stringify(newConfig)))
  },
  { deep: true }
)

watch(
  () => props.initialCategory,
  (category) => {
    activeCategory.value = normalizeSettingsCategory(category)
  },
)

// ============================================
// Methods
// ============================================

/** 加载设置 */
async function loadSettings(): Promise<void> {
  try {
    await settingsStore.loadConfig()
    Object.assign(localConfig, JSON.parse(JSON.stringify(settingsStore.config)))
  } catch (error) {
    console.error('Failed to load settings:', error)
    showSettingsToast('加载设置失败，使用默认配置')
  }
}


/** 重置设置 */
function handleReset(): void {
  settingsStore.resetToDefault()
  Object.assign(localConfig, JSON.parse(JSON.stringify(DEFAULT_CONFIG)))
  showResetConfirm.value = false
}

/** 通用设置变更 */
function handleGeneralChange(): void {
  settingsStore.updateGeneral({
    language: localConfig.general.language,
    theme: localConfig.general.theme,
    minimizeToTray: localConfig.general.minimizeToTray,
    closeToTray: localConfig.general.closeToTray,
  })
  // 同步主题到 DOM 和 localStorage
  setTheme(localConfig.general.theme)
}

/** 语言变更（需要同时更新 i18n） */
function handleLanguageChange(): void {
  changeLocale(localConfig.general.language as 'zh-CN' | 'en-US')
  handleGeneralChange()
}

/** 自动启动变更（需要调用特殊 API） */
async function handleAutoStartChange(): Promise<void> {
  try {
    await settingsStore.setAutoStart(localConfig.general.autoStart)
  } catch (error) {
    localConfig.general.autoStart = !localConfig.general.autoStart
    console.error('Failed to set auto start:', error)
    showSettingsToast('设置开机自启动失败')
  }
}

/** 热键变更 */
async function handleHotkeyChange(action: string, shortcut: string): Promise<void> {
  try {
    await settingsStore.updateHotkeys({ [action]: shortcut })
  } catch (error) {
    Object.assign(localConfig.hotkeys, settingsStore.hotkeys)
    console.error('Failed to update hotkey:', error)
    showSettingsToast('更新快捷键失败')
  }
}

/** 截图设置变更 */
function handleScreenshotChange(): void {
  settingsStore.updateScreenshot({
    includeMouseCursor: localConfig.screenshot.includeMouseCursor,
    autoCopy: localConfig.screenshot.autoCopy,
    autoSave: localConfig.screenshot.autoSave,
  })
}

/** 浏览保存位置 */
async function handleBrowseSaveLocation(): Promise<void> {
  const selected = await open({
    directory: true,
    multiple: false,
    title: '选择截图保存目录',
  })

  if (selected && typeof selected === 'string') {
    localConfig.screenshot.saveLocation = selected
    settingsStore.updateScreenshot({ saveLocation: selected })
  }
}

/** 录屏设置变更 */
function handleRecordingChange(): void {
  settingsStore.updateRecording({
    defaultFps: localConfig.recording.defaultFps,
    systemAudio: localConfig.recording.systemAudio,
    micAudio: localConfig.recording.micAudio,
  })
}

/** 浏览录屏输出目录 */
async function handleBrowseRecordingDir(): Promise<void> {
  const selected = await open({
    directory: true,
    multiple: false,
    title: '选择录屏输出目录',
  })

  if (selected && typeof selected === 'string') {
    localConfig.recording.outputDir = selected
    settingsStore.updateRecording({ outputDir: selected })
  }
}
</script>

<style scoped>
/* CSS Variables - 映射到全局主题变量，自动跟随深色/浅色主题 */
.settings-panel {
  --bg-primary: var(--color-bg-primary);
  --bg-secondary: var(--color-bg-secondary);
  --bg-hover: var(--color-bg-tertiary);
  --bg-active: var(--color-accent-light);
  --text-primary: var(--color-text-primary);
  --text-secondary: var(--color-text-secondary);
  --text-muted: var(--color-text-tertiary);
  --accent-primary: var(--color-accent);
  --accent-hover: var(--color-accent-hover);
  --border-color: var(--color-border);
  --sidebar-width: 200px;
  --content-padding: 24px;
}

.settings-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
}

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-text {
  font-size: 16px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  background: var(--bg-hover);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.1s;
}

.action-btn:hover {
  opacity: 0.8;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.save-btn:hover {
  background: var(--color-info-light);
}

.reset-btn:hover {
  background: var(--color-error-light);
}

/* 主体区域：侧边栏 + 内容区 */
.panel-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 设置内容区 */
.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--content-padding);
  background: var(--bg-secondary);
}

.settings-section {
  max-width: 600px;
}

.section-title {
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-color);
}

/* Placeholder text for upcoming sections */
.placeholder-text {
  color: var(--text-muted);
  font-style: italic;
  padding: 24px 0;
}

/* 设置项 */
.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border-light);
}

.setting-label {
  color: var(--text-secondary);
  font-size: 13px;
}

/* 下拉选择 */
.setting-select {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-input-bg);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
}

.setting-select:focus {
  outline: none;
  border-color: var(--color-border-focus);
}

/* 文本输入 */
.setting-text {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-input-bg);
  color: var(--text-primary);
  font-size: 12px;
  width: 200px;
}

.setting-text:focus {
  outline: none;
  border-color: var(--color-border-focus);
}

/* 路径输入 */
.path-input {
  display: flex;
  gap: 8px;
}

.path-input .setting-text {
  flex: 1;
}

.browse-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--bg-hover);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.1s;
}

.browse-btn:hover {
  opacity: 0.8;
}

/* 颜色选择 */
.setting-color {
  width: 60px;
  height: 30px;
  padding: 2px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-input-bg);
  cursor: pointer;
}

/* 开关 */
.setting-toggle {
  position: relative;
  width: 44px;
  height: 24px;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  width: 100%;
  height: 100%;
  cursor: pointer;
  z-index: 1;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-border);
  border-radius: 12px;
  transition: background-color 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: var(--color-bg-elevated);
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.toggle-input:checked + .toggle-slider {
  background: var(--accent-primary);
}

.toggle-input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* 滑块 */
.slider-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.setting-slider {
  width: 150px;
  height: 4px;
  border-radius: 2px;
  background: var(--color-border);
  appearance: none;
  cursor: pointer;
}

.setting-slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent-primary);
  cursor: pointer;
}

.slider-value {
  min-width: 50px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: right;
}

/* 底部状态栏 */
.panel-footer {
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-color);
  font-size: 11px;
  flex-shrink: 0;
}

.error-text {
  color: var(--color-error);
}

.saving-text {
  color: var(--color-info);
}

.status-text {
  color: var(--text-muted);
}

/* 模态对话框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-dialog {
  width: 360px;
  background: var(--color-bg-elevated);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
}

.modal-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.modal-title {
  font-size: 14px;
  font-weight: 600;
}

.modal-body {
  padding: 16px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
}

.modal-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.1s;
}

.cancel-btn {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.cancel-btn:hover {
  opacity: 0.8;
}

.confirm-btn {
  background: var(--color-error);
  color: var(--color-text-inverse);
}

.confirm-btn:hover {
  opacity: 0.9;
}

/* Scrollbar styling for content area */
.settings-content::-webkit-scrollbar {
  width: 6px;
}

.settings-content::-webkit-scrollbar-track {
  background: transparent;
}

.settings-content::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.settings-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}


/* 设置操作反馈 toast */
.settings-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
  box-shadow: var(--shadow-md);
  z-index: 1000;
}

.settings-toast.error {
  background: var(--color-error);
}

.settings-toast.success {
  background: var(--color-success);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>
