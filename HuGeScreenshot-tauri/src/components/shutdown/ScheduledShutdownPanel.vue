<template>
  <div class="scheduled-shutdown-panel">
    <!-- 模式切换 -->
    <div class="mode-toggle">
      <button
        class="mode-btn"
        :class="{ active: mode === 'countdown' }"
        @click="mode = 'countdown'"
        :disabled="isRunning"
      >
        倒计时
      </button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'specific' }"
        @click="mode = 'specific'"
        :disabled="isRunning"
      >
        指定时间
      </button>
    </div>

    <!-- 倒计时模式 -->
    <div v-if="mode === 'countdown'" class="countdown-mode" :class="{ disabled: isRunning }">
      <!-- 快捷按钮 -->
      <div class="quick-options">
        <button
          v-for="option in quickOptions"
          :key="option.minutes"
          class="time-chip"
          :class="{ selected: selectedMinutes === option.minutes }"
          @click="selectTime(option.minutes)"
          :disabled="isRunning"
        >
          {{ option.label }}
        </button>
      </div>

      <!-- 自定义滑块 -->
      <div class="slider-container">
        <div class="slider-header">
          <span class="slider-label">自定义时间</span>
          <span class="slider-value">{{ formatDuration(selectedMinutes) }}</span>
        </div>
        <input
          type="range"
          v-model.number="selectedMinutes"
          :min="5"
          :max="240"
          class="time-slider"
          :disabled="isRunning"
        />
      </div>
    </div>

    <!-- 指定时间模式 -->
    <div v-else class="specific-mode" :class="{ disabled: isRunning }">
      <div class="time-input-container">
        <label class="time-input-label">选择关机时间</label>
        <input
          type="time"
          v-model="specificTime"
          class="time-input"
          :disabled="isRunning"
        />
        <p class="time-hint">💡 如果时间早于现在，将设置为明天</p>
      </div>
    </div>

    <!-- 倒计时显示 -->
    <div class="countdown-display">
      <div class="time-display">{{ displayTime }}</div>
      <div class="status-text">{{ statusText }}</div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-buttons">
      <button
        class="cancel-btn"
        :disabled="!isRunning"
        @click="cancelShutdown"
      >
        取消定时
      </button>
      <button
        class="start-btn"
        :disabled="isRunning"
        @click="startShutdown"
      >
        开始定时
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ScheduledShutdownPanel - 预约关机面板
 *
 * 功能：
 * - 倒计时模式：选择分钟数后开始倒计时
 * - 指定时间模式：选择具体时间点关机
 * - 实时显示剩余时间和进度
 * - 支持取消和延长关机
 *
 * 参考 Python 版本 scheduled_shutdown_dialog.py 实现
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { confirm } from '@tauri-apps/plugin-dialog'

// 快捷选项
const quickOptions = [
  { minutes: 15, label: '15分钟' },
  { minutes: 30, label: '30分钟' },
  { minutes: 45, label: '45分钟' },
  { minutes: 60, label: '1小时' },
  { minutes: 90, label: '1.5小时' },
  { minutes: 120, label: '2小时' },
]

// 状态
const mode = ref<'countdown' | 'specific'>('countdown')
const selectedMinutes = ref(30)
const specificTime = ref('')
const isRunning = ref(false)
const scheduledTime = ref<Date | null>(null)
const totalSeconds = ref(0)
const remainingSeconds = ref(0)
const warningShown = ref(false)

// 定时器
let timer: ReturnType<typeof setInterval> | null = null

// 计算属性
const displayTime = computed(() => {
  if (!isRunning.value || remainingSeconds.value <= 0) {
    return '--:--'
  }
  const hours = Math.floor(remainingSeconds.value / 3600)
  const minutes = Math.floor((remainingSeconds.value % 3600) / 60)
  const seconds = remainingSeconds.value % 60
  if (hours > 0) {
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  }
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
})

const statusText = computed(() => {
  if (!isRunning.value) {
    return '未设置定时关机'
  }
  if (remainingSeconds.value <= 0) {
    return '即将关机...'
  }
  if (scheduledTime.value) {
    const timeStr = scheduledTime.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return `将于 ${timeStr} 关机`
  }
  return '定时关机中...'
})

const progressPercent = computed(() => {
  if (!isRunning.value || totalSeconds.value <= 0) {
    return 0
  }
  return (remainingSeconds.value / totalSeconds.value) * 100
})

// 方法
function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} 分钟`
  } else if (minutes % 60 === 0) {
    return `${minutes / 60} 小时`
  } else {
    return `${Math.floor(minutes / 60)}小时${minutes % 60}分`
  }
}

function selectTime(minutes: number) {
  selectedMinutes.value = minutes
}

async function startShutdown() {
  let seconds: number
  
  if (mode.value === 'countdown') {
    seconds = selectedMinutes.value * 60
    scheduledTime.value = new Date(Date.now() + seconds * 1000)
  } else {
    // 指定时间模式
    if (!specificTime.value) {
      alert('请选择关机时间')
      return
    }
    const timeParts = specificTime.value.split(':')
    const hours = parseInt(timeParts[0], 10)
    const minutes = parseInt(timeParts[1], 10)
    
    // 验证时间格式
    if (isNaN(hours) || isNaN(minutes)) {
      alert('时间格式无效')
      return
    }
    
    const now = new Date()
    const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes)
    
    // 如果时间已过，设置为明天
    if (target <= now) {
      target.setDate(target.getDate() + 1)
    }
    
    seconds = Math.floor((target.getTime() - now.getTime()) / 1000)
    scheduledTime.value = target
  }
  
  totalSeconds.value = seconds
  remainingSeconds.value = seconds
  
  try {
    // 先取消可能存在的定时关机
    await invoke('cancel_scheduled_shutdown')
    
    // 设置新的定时关机
    await invoke('schedule_shutdown', { seconds })
    
    isRunning.value = true
    warningShown.value = false
    
    // 启动倒计时
    startTimer()
  } catch (error) {
    console.error('设置定时关机失败:', error)
    alert(`设置失败: ${error}`)
  }
}

async function cancelShutdown() {
  try {
    await invoke('cancel_scheduled_shutdown')
    
    stopTimer()
    isRunning.value = false
    scheduledTime.value = null
    totalSeconds.value = 0
    remainingSeconds.value = 0
    warningShown.value = false
  } catch (error) {
    console.error('取消定时关机失败:', error)
    alert(`取消失败: ${error}`)
  }
}

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    if (remainingSeconds.value > 0) {
      remainingSeconds.value--
      
      // 最后 60 秒警告
      if (remainingSeconds.value === 60 && !warningShown.value) {
        warningShown.value = true
        showWarning()
      }
    } else {
      stopTimer()
    }
  }, 1000)
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function showWarning() {
  const result = await confirm('电脑将在 1 分钟内关机！\n\n请保存所有未保存的工作。', {
    title: '⚠️ 即将关机',
    kind: 'warning',
    okLabel: '继续关机',
    cancelLabel: '取消关机'
  })
  if (!result) {
    await cancelShutdown()
  }
}

// 初始化默认时间
onMounted(() => {
  const now = new Date()
  now.setMinutes(now.getMinutes() + 30)
  specificTime.value = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
})

onUnmounted(() => {
  stopTimer()
})
</script>

<style scoped>
.scheduled-shutdown-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px;
  max-width: 400px;
  margin: 0 auto;
}

/* 模式切换 */
.mode-toggle {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--color-bg-primary);
  border-radius: 10px;
  border: 1px solid var(--color-border);
}

.mode-btn {
  flex: 1;
  padding: 10px 16px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--color-text-tertiary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.mode-btn.active {
  background: var(--color-bg-secondary);
  color: var(--color-accent);
  font-weight: 600;
}

.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 倒计时模式 */
.countdown-mode,
.specific-mode {
  transition: opacity 0.2s;
}

.countdown-mode.disabled,
.specific-mode.disabled {
  opacity: 0.5;
  pointer-events: none;
}

/* 快捷选项 */
.quick-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.time-chip {
  padding: 10px 12px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.time-chip:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.time-chip.selected {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-text-primary);
  font-weight: 600;
}

.time-chip:disabled {
  cursor: not-allowed;
}

/* 滑块容器 */
.slider-container {
  margin-top: 16px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
}

.slider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.slider-label {
  font-size: 13px;
  color: var(--color-text-primary);
}

.slider-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-accent);
}

.time-slider {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--color-border);
  border-radius: 3px;
  outline: none;
}

.time-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  background: var(--color-accent);
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.15s;
}

.time-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.time-slider:disabled {
  opacity: 0.5;
}

/* 指定时间模式 */
.time-input-container {
  padding: 16px;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
}

.time-input-label {
  display: block;
  font-size: 13px;
  color: var(--color-text-primary);
  margin-bottom: 12px;
}

.time-input {
  width: 100%;
  padding: 14px 16px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-size: 28px;
  font-weight: 600;
  text-align: center;
}

.time-input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.time-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* 倒计时显示 */
.countdown-display {
  padding: 24px;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
  text-align: center;
}

.time-display {
  font-size: 48px;
  font-weight: 700;
  font-family: 'Consolas', 'SF Mono', monospace;
  color: var(--color-text-primary);
  letter-spacing: 2px;
  margin-bottom: 8px;
}

.status-text {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-bottom: 16px;
}

.progress-bar {
  height: 8px;
  background: var(--color-border);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 4px;
  transition: width 1s linear;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 12px;
}

.cancel-btn,
.start-btn {
  flex: 1;
  padding: 14px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.cancel-btn {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  color: var(--color-text-primary);
}

.cancel-btn:hover:not(:disabled) {
  border-color: #e81123;
  color: #e81123;
}

.cancel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.start-btn {
  background: var(--color-accent);
  border: none;
  color: var(--color-text-primary);
  font-weight: 600;
}

.start-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.start-btn:disabled {
  background: var(--color-border);
  cursor: not-allowed;
}
</style>
