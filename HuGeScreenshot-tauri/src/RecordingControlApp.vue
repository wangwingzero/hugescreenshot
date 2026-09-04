<template>
  <div class="recording-control" :class="{ paused: isPaused }" @mousedown="startDrag">
    <!-- 录制指示器 -->
    <div class="indicator" :class="{ recording: isRecording, paused: isPaused }">
      <span class="dot" />
    </div>

    <!-- 时间显示 -->
    <div class="time">{{ formattedTime }}</div>

    <!-- 控制按钮 -->
    <div class="buttons">
      <!-- 暂停/继续 -->
      <button
        class="ctrl-btn pause-btn"
        :title="isPaused ? '继续' : '暂停'"
        @click.stop="togglePause"
      >
        {{ isPaused ? '▶' : '⏸' }}
      </button>

      <!-- 停止 -->
      <button class="ctrl-btn stop-btn" title="停止录制" @click.stop="handleStop">
        ⏹
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'

// State
const recordingState = ref<string>('recording')
const elapsedTime = ref(0)
let pollInterval: ReturnType<typeof setInterval> | null = null
let dragOffset = { x: 0, y: 0 }
let isStopping = false

// Computed
const isRecording = computed(() => recordingState.value === 'recording')
const isPaused = computed(() => recordingState.value === 'paused')

const formattedTime = computed(() => {
  const secs = Math.floor(elapsedTime.value)
  const mins = Math.floor(secs / 60)
  const remainingSecs = secs % 60
  return `${mins.toString().padStart(2, '0')}:${remainingSecs.toString().padStart(2, '0')}`
})

// Methods
async function pollStatus() {
  try {
    const status = await invoke<{
      state: string
      elapsedTime: number
      frameCount: number
      fileSize: number
    }>('get_recording_status')

    recordingState.value = status.state
    elapsedTime.value = status.elapsedTime

    // 录制结束，关闭控制面板（仅当不是手动停止时）
    if (!isStopping && (status.state === 'idle' || status.state === 'finished' || status.state === 'error')) {
      const win = getCurrentWindow()
      await win.close()
    }
  } catch (e) {
    console.error('获取录屏状态失败:', e)
  }
}

async function togglePause() {
  try {
    if (isPaused.value) {
      await invoke('resume_recording')
    } else {
      await invoke('pause_recording')
    }
    await pollStatus()
  } catch (e) {
    console.error('暂停/继续失败:', e)
  }
}

async function handleStop() {
  // 标记正在停止，阻止 poll 竞争关闭窗口
  isStopping = true
  // 立即停止轮询，避免与 handleStop 竞争关闭窗口
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
  try {
    const result = await invoke<{
      outputPath: string
      duration: number
      frameCount: number
      fileSize: number
    }>('stop_recording')
    // 恢复 overlay 正常模式（取消鼠标穿透+恢复捕获）
    await invoke('set_overlay_recording_mode', { enabled: false })
    // 关闭录屏区域边框窗口
    await invoke('close_recording_border')
    // 先打开预览窗口（当前窗口 IPC 仍存活）
    await invoke('open_recording_preview', {
      outputPath: result.outputPath,
      duration: result.duration,
      fileSize: result.fileSize,
    })
    // 最后关闭控制面板
    const win = getCurrentWindow()
    await win.close()
  } catch (e) {
    console.error('停止录制失败:', e)
    // 确保即使失败也恢复 overlay
    try { await invoke('set_overlay_recording_mode', { enabled: false }) } catch (_) { /* ignore */ }
    try { await invoke('close_recording_border') } catch (_) { /* ignore */ }
  }
}

// 拖动支持
function startDrag(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.ctrl-btn')) return
  
  dragOffset.x = e.clientX
  dragOffset.y = e.clientY

  const win = getCurrentWindow()
  win.startDragging()
}

// 键盘事件处理（命名函数，便于移除）
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    handleStop()
  }
}

// Lifecycle
onMounted(() => {
  // 每 500ms 轮询一次状态
  pollInterval = setInterval(pollStatus, 500)
  pollStatus()

  // 监听 Escape 键停止录制
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
  document.removeEventListener('keydown', handleKeyDown)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: transparent;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
}

.recording-control {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: var(--color-bg-elevated);
  border: 1px solid rgba(244, 67, 54, 0.6);
  border-radius: 20px;
  box-shadow: var(--shadow-lg);
  cursor: grab;
  backdrop-filter: blur(10px);
  font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}

.recording-control.paused {
  border-color: rgba(255, 167, 38, 0.6);
}

.recording-control:active {
  cursor: grabbing;
}

/* 录制指示器 */
.indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-surface-strong);
}

.indicator.recording .dot {
  background: var(--color-error);
  animation: pulse 1.5s ease-in-out infinite;
}

.indicator.paused .dot {
  background: var(--color-warning);
  animation: none;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 时间显示 */
.time {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-error);
  letter-spacing: 1px;
  min-width: 50px;
  text-align: center;
}

.recording-control.paused .time {
  color: var(--color-warning);
}

/* 控制按钮 */
.buttons {
  display: flex;
  gap: 4px;
}

.ctrl-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--color-surface-muted);
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.ctrl-btn:hover {
  background: var(--color-surface-strong);
  color: var(--color-text-primary);
}

.stop-btn:hover {
  background: rgba(244, 67, 54, 0.6);
}

.pause-btn:hover {
  background: rgba(255, 167, 38, 0.4);
}
</style>
