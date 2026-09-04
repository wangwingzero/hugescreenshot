<template>
  <div class="mouse-highlight-settings">
    <!-- 功能总开关 -->
    <div class="setting-item main-toggle">
      <label class="setting-label">{{ $t('settings.mouseHighlightEnabled') || '启用鼠标高亮' }}</label>
      <div class="setting-toggle">
        <input
          v-model="localConfig.enabled"
          type="checkbox"
          class="toggle-input"
          @change="handleEnabledChange"
        />
        <span class="toggle-slider"></span>
      </div>
    </div>

    <!-- 配色主题选择 -->
    <div class="settings-group">
      <h4 class="group-title">{{ $t('settings.mouseHighlightTheme') || '配色主题' }}</h4>
      <div class="theme-buttons">
        <button
          v-for="(theme, key) in themes"
          :key="key"
          class="theme-button"
          :class="{ selected: localConfig.theme === key }"
          :title="theme.name"
          @click="handleThemeChange(key as MouseHighlightTheme)"
        >
          <span class="theme-color" :style="{ background: theme.circleColor }"></span>
          <span class="theme-name">{{ theme.name }}</span>
        </button>
      </div>
    </div>

    <!-- 效果开关 -->
    <div class="settings-group">
      <h4 class="group-title">{{ $t('settings.mouseHighlightEffects') || '效果开关' }}</h4>
      <div class="effect-toggles">
        <label class="effect-toggle">
          <input
            v-model="localConfig.circleEnabled"
            type="checkbox"
            @change="handleEffectToggle('circle')"
          />
          <span class="effect-name">{{ $t('settings.circleEffect') || '光圈' }}</span>
        </label>
        <label class="effect-toggle">
          <input
            v-model="localConfig.clickEffectEnabled"
            type="checkbox"
            @change="handleEffectToggle()"
          />
          <span class="effect-name">{{ $t('settings.clickRippleEffect') || '点击涟漪' }}</span>
        </label>
        <label class="effect-toggle">
          <input
            v-model="localConfig.spotlightEnabled"
            type="checkbox"
            @change="handleEffectToggle('spotlight')"
          />
          <span class="effect-name">{{ $t('settings.spotlightEffect') || '聚光灯' }}</span>
        </label>
        <label class="effect-toggle">
          <input
            v-model="localConfig.cursorMagnifyEnabled"
            type="checkbox"
            @change="handleEffectToggle('magnifier')"
          />
          <span class="effect-name">{{ $t('settings.cursorMagnifyEffect') || '指针放大' }}</span>
        </label>
      </div>
    </div>

    <!-- 光圈效果参数 -->
    <div class="settings-group" :class="{ disabled: !localConfig.circleEnabled }">
      <h4 class="group-title">{{ $t('settings.circleParams') || '光圈效果' }}</h4>
      <ParameterSlider
        v-model="localConfig.circleRadius"
        :label="$t('settings.radius') || '半径'"
        :min="limits.circleRadius.min"
        :max="limits.circleRadius.max"
        suffix="px"
        :disabled="!localConfig.circleEnabled"
        @change="handleParamChange"
      />
      <ParameterSlider
        v-model="localConfig.circleThickness"
        :label="$t('settings.thickness') || '粗细'"
        :min="limits.circleThickness.min"
        :max="limits.circleThickness.max"
        suffix="px"
        :disabled="!localConfig.circleEnabled"
        @change="handleParamChange"
      />
    </div>

    <!-- 聚光灯效果参数 -->
    <div class="settings-group" :class="{ disabled: !localConfig.spotlightEnabled }">
      <h4 class="group-title">{{ $t('settings.spotlightParams') || '聚光灯效果' }}</h4>
      <ParameterSlider
        v-model="localConfig.spotlightRadius"
        :label="$t('settings.radius') || '半径'"
        :min="limits.spotlightRadius.min"
        :max="limits.spotlightRadius.max"
        suffix="px"
        :disabled="!localConfig.spotlightEnabled"
        @change="handleParamChange"
      />
      <ParameterSlider
        v-model="localConfig.spotlightDarkness"
        :label="$t('settings.darkness') || '暗度'"
        :min="limits.spotlightDarkness.min"
        :max="limits.spotlightDarkness.max"
        suffix="%"
        :disabled="!localConfig.spotlightEnabled"
        @change="handleParamChange"
      />
    </div>

    <!-- 指针放大效果参数 -->
    <div class="settings-group" :class="{ disabled: !localConfig.cursorMagnifyEnabled }">
      <h4 class="group-title">{{ $t('settings.cursorMagnifyParams') || '指针放大效果' }}</h4>
      <ParameterSlider
        v-model="localConfig.cursorScale"
        :label="$t('settings.scale') || '倍数'"
        :min="limits.cursorScale.min"
        :max="limits.cursorScale.max"
        :step="0.1"
        :decimals="1"
        suffix="x"
        :disabled="!localConfig.cursorMagnifyEnabled"
        @change="handleParamChange"
      />
    </div>

    <!-- 点击涟漪效果参数 -->
    <div class="settings-group" :class="{ disabled: !localConfig.clickEffectEnabled }">
      <h4 class="group-title">{{ $t('settings.clickRippleParams') || '点击涟漪效果' }}</h4>
      <ParameterSlider
        v-model="localConfig.rippleDuration"
        :label="$t('settings.duration') || '时长'"
        :min="limits.rippleDuration.min"
        :max="limits.rippleDuration.max"
        :step="50"
        suffix="ms"
        :disabled="!localConfig.clickEffectEnabled"
        @change="handleParamChange"
      />
    </div>

    <!-- 重置按钮 -->
    <div class="actions">
      <button class="reset-btn" @click="handleReset">
        {{ $t('settings.resetToDefault') || '重置默认' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * MouseHighlightSettings - 鼠标高亮设置组件
 *
 * 提供鼠标高亮功能的完整配置界面：
 * - 功能总开关
 * - 配色主题选择（4种预设主题）
 * - 效果开关（光圈、聚光灯、指针放大、点击涟漪）
 * - 各效果的参数滑块
 *
 * 即时反馈：
 * - 所有参数变化时立即调用后端更新配置
 * - 后端会实时应用新配置到覆盖层
 *
 * @validates Requirements 1.1-1.5, 2.1-2.5, 3.1-3.4, 4.1-4.4, 5.1-5.7
 */
import { reactive, watch, onMounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import ParameterSlider from './controls/ParameterSlider.vue'
import {
  MOUSE_HIGHLIGHT_THEMES,
  MOUSE_HIGHLIGHT_LIMITS,
  DEFAULT_CONFIG,
  type MouseHighlightConfig,
  type MouseHighlightTheme,
} from '@/types/config'

// 主题列表
const themes = MOUSE_HIGHLIGHT_THEMES
const limits = MOUSE_HIGHLIGHT_LIMITS

// Props
interface Props {
  /** 初始配置 */
  config: MouseHighlightConfig
}

const props = defineProps<Props>()

// Events
const emit = defineEmits<{
  (e: 'update:config', config: MouseHighlightConfig): void
}>()

// 本地配置副本（合并默认值，防止 undefined）
const localConfig = reactive<MouseHighlightConfig>({
  ...DEFAULT_CONFIG.mouseHighlight,
  ...props.config,
})

// 监听外部配置变化
watch(
  () => props.config,
  (newConfig) => {
    Object.assign(localConfig, newConfig)
  },
  { deep: true }
)

// 组件挂载时，如果已启用则自动开始
onMounted(async () => {
  if (localConfig.enabled) {
    await applyConfigToBackend()
  }
})

/**
 * 确定当前应该使用的效果类型
 * 后端只支持单一效果，所以需要按优先级选择：
 * 聚光灯 > 放大镜 > 光圈 > 无
 * 
 * 注意：聚光灯优先级最高，因为它是全屏效果，与其他效果不兼容
 */
function determineEffect(): 'none' | 'circle' | 'spotlight' | 'magnifier' {
  if (localConfig.spotlightEnabled) return 'spotlight'
  if (localConfig.cursorMagnifyEnabled) return 'magnifier'
  if (localConfig.circleEnabled) return 'circle'
  return 'none'
}

/**
 * 将配置应用到后端 - 实现即时反馈
 *
 * 注意：Rust 后端使用 #[serde(rename_all = "camelCase")]
 * 所以这里的字段名必须使用 camelCase 格式
 */
async function applyConfigToBackend(): Promise<void> {
  try {
    const effect = determineEffect()
    
    // 转换为 Rust 后端期望的格式 (使用 camelCase)
    const rustConfig = {
      enabled: localConfig.enabled,
      effect: effect,
      clickEffect: localConfig.clickEffectEnabled ? 'ripple' : 'none',
      color: themes[localConfig.theme].circleColor,
      // 根据效果类型选择对应的半径参数
      radius: effect === 'spotlight' ? localConfig.spotlightRadius : localConfig.circleRadius,
      opacity: 0.8,
      spotlightDarkness: localConfig.spotlightDarkness / 100,
      magnifierZoom: localConfig.cursorScale,
      showLeftClick: localConfig.clickEffectEnabled,
      showRightClick: localConfig.clickEffectEnabled,
      leftClickColor: themes[localConfig.theme].leftClickColor,
      rightClickColor: themes[localConfig.theme].rightClickColor,
      clickDuration: localConfig.rippleDuration,
      updateRate: 60,
    }

    console.log('发送鼠标高亮配置到后端:', rustConfig)

    await invoke('set_mouse_highlight_config', { config: rustConfig })

    // 如果启用了功能，确保追踪器正在运行
    if (localConfig.enabled) {
      const isRunning = await invoke<boolean>('get_mouse_highlight_status')
      console.log('鼠标高亮运行状态:', isRunning)
      if (!isRunning) {
        await invoke('start_mouse_highlight', { config: rustConfig })
        console.log('已启动鼠标高亮')
      }
    }

    // 同步到父组件
    emit('update:config', { ...localConfig })
  } catch (error) {
    console.error('更新鼠标高亮配置失败:', error)
  }
}

/**
 * 处理功能开关变化
 */
async function handleEnabledChange(): Promise<void> {
  try {
    if (localConfig.enabled) {
      // 启用时：应用配置并启动（applyConfigToBackend 会处理启动）
      await applyConfigToBackend()
    } else {
      // 禁用时：停止追踪器和 overlay
      await invoke('stop_mouse_highlight')
    }
    emit('update:config', { ...localConfig })
  } catch (error) {
    console.error('切换鼠标高亮失败:', error)
    // 恢复状态
    localConfig.enabled = !localConfig.enabled
  }
}

/**
 * 处理主题变化
 */
async function handleThemeChange(themeKey: MouseHighlightTheme): Promise<void> {
  localConfig.theme = themeKey
  await applyConfigToBackend()
}

/**
 * 处理效果开关变化
 * 聚光灯、放大镜、光圈三者互斥（后端只支持单一效果）
 * 点击涟漪可以与任何效果同时启用
 */
async function handleEffectToggle(changedEffect?: 'circle' | 'spotlight' | 'magnifier'): Promise<void> {
  // 如果是主效果（非点击涟漪），则互斥处理
  if (changedEffect) {
    if (changedEffect === 'spotlight' && localConfig.spotlightEnabled) {
      localConfig.circleEnabled = false
      localConfig.cursorMagnifyEnabled = false
    } else if (changedEffect === 'magnifier' && localConfig.cursorMagnifyEnabled) {
      localConfig.circleEnabled = false
      localConfig.spotlightEnabled = false
    } else if (changedEffect === 'circle' && localConfig.circleEnabled) {
      localConfig.spotlightEnabled = false
      localConfig.cursorMagnifyEnabled = false
    }
  }
  await applyConfigToBackend()
}

/**
 * 处理参数变化 - 即时反馈
 */
async function handleParamChange(): Promise<void> {
  await applyConfigToBackend()
}

/**
 * 重置为默认值
 */
async function handleReset(): Promise<void> {
  localConfig.circleEnabled = true
  localConfig.spotlightEnabled = false
  localConfig.cursorMagnifyEnabled = false
  localConfig.clickEffectEnabled = true
  localConfig.theme = 'classic_yellow'
  localConfig.circleRadius = limits.circleRadius.default
  localConfig.circleThickness = limits.circleThickness.default
  localConfig.spotlightRadius = limits.spotlightRadius.default
  localConfig.spotlightDarkness = limits.spotlightDarkness.default
  localConfig.cursorScale = limits.cursorScale.default
  localConfig.rippleDuration = limits.rippleDuration.default

  await applyConfigToBackend()
}
</script>

<style scoped>
.mouse-highlight-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 主开关 */
.main-toggle {
  padding: 12px 16px;
  background: var(--color-accent-light);
  border-radius: 8px;
  border: 1px solid var(--color-border-focus);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 开关样式 */
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
  background: var(--color-surface-strong);
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
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-input:checked + .toggle-slider {
  background: var(--color-accent);
}

.toggle-input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* 设置分组 */
.settings-group {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  transition: opacity 0.2s;
}

.settings-group.disabled {
  opacity: 0.5;
}

.group-title {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 主题按钮 */
.theme-buttons {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.theme-button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-input-bg);
  border: 2px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.theme-button:hover {
  background: var(--color-surface-muted);
}

.theme-button.selected {
  border-color: var(--accent-primary);
  background: var(--color-accent-light);
}

.theme-color {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  box-shadow: var(--shadow-sm);
}

.theme-name {
  font-size: 12px;
  color: var(--text-primary);
}

/* 效果开关 */
.effect-toggles {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.effect-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--color-surface-subtle);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.effect-toggle:hover {
  background: var(--color-surface-subtle);
}

.effect-toggle input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-primary);
  cursor: pointer;
}

.effect-name {
  font-size: 13px;
  color: var(--text-primary);
}

/* 操作按钮 */
.actions {
  display: flex;
  justify-content: flex-start;
  padding-top: 8px;
}

.reset-btn {
  padding: 8px 16px;
  background: var(--color-surface-muted);
  border: none;
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.reset-btn:hover {
  background: var(--color-surface-strong);
  color: var(--text-primary);
}
</style>
